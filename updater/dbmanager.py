#!/usr/bin/python
# -*- coding: utf-8 -*-
from sqlalchemy import Column, String, Text,  create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
import requests
from packaging import version
import argparse
import logging
import os
import datetime
from dateutil.parser import parse as parsedate
import re

EXCLUDED_PKGS = {
    "base",
    "boot",
    "class",
    "cluster",
    "codetools",
    "compiler",
    "datasets",
    "foreign",
    "graphics",
    "grDevices",
    "grid",
    "KernSmooth",
    "lattice",
    "MASS",
    "Matrix",
    "methods",
    "mgcv",
    "nlme",
    "nnet",
    "parallel",
    "rpart",
    "spatial",
    "splines",
    "stats",
    "stats4",
    "survival",
    "tcltk",
    "tools",
    "utils",
    "R"
}

Base = declarative_base()


class PkgMeta(Base):
    # 表的名字:
    __tablename__ = 'pkgmeta'

    # 表的结构:
    # currently max is 48, r-illuminahumanmethylationepicanno.ilm10b4.hg19, so 50 is OK
    name = Column(String(50),  primary_key=True)
    desc = Column(Text)
    repo = Column(String(4))  # CRAN or BIOC
    bioc_ver = Column(String(8))  # 3.0 to 3.16
    # bioc, data/annotation, data/experiment
    bioc_category = Column(String(16))

    def __init__(self, name, desc, repo, bioc_ver, bioc_category) -> None:
        super().__init__()
        self.name = name
        self.desc = desc
        self.repo = repo
        self.bioc_ver = bioc_ver
        self.bioc_category = bioc_category


def from_str(data, bioc_ver, bioc_cat):
    '''
    construct pkgmeta from string.
    '''
    for line in data.split('\n'):
        if line.startswith('Package:'):
            pkgname = line.split(':')[-1].strip()
            if bioc_ver:
                pkgmeta = PkgMeta(
                    pkgname, data, 'BIOC', str(bioc_ver), bioc_cat)
            else:
                pkgmeta = PkgMeta(
                    pkgname, data, 'CRAN', None, None)
            return pkgmeta


def get_bioc_versions(bioc_mirror="https://bioconductor.org") -> list[str]:
    '''
    parse all available Bioconductor versions from remote mirror.
    '''
    version_page = requests.get(
        f"{bioc_mirror}/about/release-announcements/#release-versions/")
    if version_page.status_code != requests.codes.ok:
        raise RuntimeError(
            f"Failed to get Bioconductor versions due to: {version_page.status_code}: {version_page.reason}")
    z = re.findall(r"/packages/(\d.\d+)/", version_page.text)
    # mannually add 1.7 to 1.0 to the list.
    for i in range(7, -1, -1):
        z.append(f"1.{i}")
    bioc_versions = list(map(lambda x: version.parse(x), z))
    return bioc_versions


def get_package_meta(url, mtime=None, compare=False):
    '''
    get  package metadata from Bioconductor and CRAN.
    url: the url to be downloaded, e.g. https://bioconductor.org/packages/3.16/bioc/src/contrib/PACKAGES
    mtime: the last modified time of the local file. if remote is older than mtime, ignore it.
    '''
    if compare and not remote_is_newer(url, mtime):
        return None
    meta = requests.get(url)
    if meta.status_code != requests.codes.ok:
        logging.error(
            f"failed to download Package List due to {meta.status_code}: {meta.reason}")
    else:
        return meta.text
    return None


def remote_is_newer(url, mtime) -> bool:
    '''
    whether the remote file is newer than local file.
    return True if mitime is None.
    returns False if remote does not provide `Last-Modified` header.
    '''
    if not mtime:
        return True
    r = requests.head(url)
    url_time = r.headers.get('last-modified')
    if not url_time:
        return False

    url_date = parsedate(url_time)
    file_time = datetime.datetime.fromtimestamp(
        mtime)
    return url_date > file_time.astimezone()


def remove_all_cran_pkg(engine):
    '''
    remove all CRAN packages from database.
    '''
    session = Session(engine)
    session.query(PkgMeta).filter_by(repo='CRAN').delete()
    session.commit()


def update_DB(engine, min_ver=None, first_run=False, mtime=None,
              bioc_mirror="https://bioconductor.org", cran_mirror="https://cran.r-project.org"):
    '''
    update the database.
    engine: the sqlalchemy engine. engine = create_engine(f"sqlite:///{args.db}")
    min_ver: the minimum Bioconductor version accepted.
    first_run: whether this is the first run. if so, download all packages.
    mtime: the last modified time of the local file. if remote is older than mtime, ignore it.
    bioc_mirror: the Bioconductor mirror to use.
    cran_mirror: the CRAN mirror to use.
    '''
    bioc_vers = get_bioc_versions(bioc_mirror)
    bioc_vers.sort()
    if min_ver:
        min_ver = version.parse(min_ver)
    else:
        if first_run:
            min_ver = bioc_vers[0]
        else:
            min_ver = bioc_vers[-2]
    min_ver = max(min_ver, version.parse("1.8"))

    with Session(engine) as session:

        # BIOC
        for ver in bioc_vers:
            if ver < min_ver:
                continue
            for cat in ['bioc', 'data/annotation', 'data/experiment']:
                logging.info(
                    f"Downloading Bioconductor Package List for {ver} {cat}")

                url = f"{bioc_mirror}/packages/{ver}/{cat}/src/contrib/PACKAGES"
                f = get_package_meta(url, mtime)
                if not f:
                    continue
                descs = f.split('\n\n')
                pkgmetas = map(lambda x: from_str(x, ver, cat), descs)

                # insert or skip
                for pkgmeta in pkgmetas:
                    add_or_update(session, PkgMeta, pkgmeta)
        # CRAN
        logging.info("Removing old package list for CRAN")
        remove_all_cran_pkg(engine)
        url = f"{cran_mirror}/src/contrib/PACKAGES"
        logging.info("Downloading CRAN Package List")
        f = get_package_meta(url, mtime)
        if f:
            descs = f.split('\n\n')
            pkgmetas = map(lambda x: from_str(x, None, None), descs)

            # insert or skip
            for pkgmeta in pkgmetas:
                # we already deleted all CRAN packages, so we can just add them.
                add_or_update(session, PkgMeta, pkgmeta)


def add_or_skip(session, table, pkgmeta):
    '''
    add pkgmeta to table if it does not exist.
    '''
    if not pkgmeta:
        return
    if not session.get(table, pkgmeta.name):
        session.add(pkgmeta)
    session.commit()


def add_or_update(session, table, pkgmeta):
    if not pkgmeta:
        return
    if session.get(table, pkgmeta.name):

        pkg = session.query(table).filter_by(
            name=pkgmeta.name).first()
        pkg.desc = pkgmeta.desc
        pkg.repo = pkgmeta.repo
        pkg.bioc_ver = pkgmeta.bioc_ver
        pkg.bioc_category = pkgmeta.bioc_category
    else:
        session.add(pkgmeta)
    session.commit()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('sqlalchemy').setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(
        description='Manage the  meta info database (only sqlite are supported) of CRAN and Bioconductor packages',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--db', help='Where the database should be placed', default='/tmp/dbmanager/sqlite.db')
    parser.add_argument('-c',
                        '--cran_mirror', help='The mirror of CRAN', default="https://cran.r-project.org")
    parser.add_argument('-b',
                        '--bioc_mirror', help='The mirror of biocoductor', default="https://bioconductor.org")

    parser.add_argument('-m',
                        '--bioc_min_ver', help="The minimum version of Bioconductor supported, must be greater than 3.0", default=None)
    parser.add_argument('-f',
                        '--first_run', help="If this is the first run, the database will be created", action='store_true')
    parser.add_argument(
        '--compare', help="Compare mtime of database and remote, if database is newer, skip remote (This can be buggy)", action='store_true')

    args = parser.parse_args()
    if not args:
        parser.print_help()
        exit(1)

    db_dir = os.path.dirname(args.db)
    if not os.path.exists(args.db):
        args.first_run = True
    else:
        if args.first_run:
            os.remove(args.db)
    os.makedirs(db_dir, exist_ok=True)

    # 创建一个 SQLite 的内存数据库，必须加上 check_same_thread=False，否则无法在多线程中使用
    engine = create_engine(f"sqlite:///{args.db}", future=True,
                           connect_args={"check_same_thread": False})

    if args.first_run:
        Base.metadata.create_all(engine)
    mtime = os.path.getmtime(args.db)
    if args.first_run:
        mtime = None

    update_DB(engine=engine, min_ver=args.bioc_min_ver,
              first_run=args.first_run, mtime=mtime, cran_mirror=args.cran_mirror, bioc_mirror=args.bioc_mirror)
