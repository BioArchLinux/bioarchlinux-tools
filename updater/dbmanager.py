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


def get_bioc_versions(url="https://bio.askk.cc") -> list[str]:
    '''
    get all Bioconductor versions
    '''
    version_page = requests.get(
        f"{url}/bioc_version")
    if version_page.status_code != requests.codes.ok:
        raise RuntimeError(
            f"Failed to get Bioconductor versions due to: {version_page.status_code}: {version_page.reason}")
    z = version_page.text.split(',')
    return z


def update_DB(engine, path='bioc', min_ver='3.0', verion_file_url="https://bio.askk.cc"):
    bioc_vers = get_bioc_versions(verion_file_url)
    bioc_vers = [version.parse(v) for v in bioc_vers]
    bioc_vers.sort()
    with Session(engine) as session:
        for ver in bioc_vers:
            if ver < version.parse(min_ver):
                continue
            for cat in ['bioc', 'data/annotation', 'data/experiment']:
                with open(f"{path}/packages/{ver}/{cat}/src/contrib/PACKAGES") as f:
                    descs = f.read().split('\n\n')
                    pkgmetas = map(
                        lambda x: from_str(x, ver, cat), descs)
                    # insert or update
                    for pkgmeta in pkgmetas:
                        add_or_update(session, PkgMeta, pkgmeta)
        # CRAN
        with open(f"{path}/src/contrib/PACKAGES") as f:
            descs = f.read().split('\n\n')
            pkgmetas = map(
                lambda x: from_str(x, None, None), descs)
            # insert or update
            for pkgmeta in pkgmetas:
                add_or_update(session, PkgMeta, pkgmeta)


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
    parser = argparse.ArgumentParser(
        description='Manage the  meta info database (only sqlite are supported) of CRAN and Bioconductor packages',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--db', help='Where the database should be placed', default='/tmp/dbmanager/sqlite.db')
    parser.add_argument(
        '--bioarch_path', help='The path of BioArchLinux repo', default="BioArchLinux")
    parser.add_argument(
        '--bioc_min_ver', help="The minimum version of Bioconductor supported, must be greater than 3.0", default="3.0")

    args = parser.parse_args()
    db_dir = os.path.dirname(args.db)
    os.makedirs(db_dir, exist_ok=True)

    # 创建一个 SQLite 的内存数据库，必须加上 check_same_thread=False，否则无法在多线程中使用
    engine = create_engine(f"sqlite:///{args.db}", echo=True, future=True,
                           connect_args={"check_same_thread": False})

    Base.metadata.create_all(engine)
    update_DB(engine=engine, min_ver=args.bioc_min_ver)
