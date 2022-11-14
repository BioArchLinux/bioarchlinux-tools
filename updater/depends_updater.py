#!/usr/bin/python
'''
Update the `depends` and `optdepends` part of an R package PKGBUILD listed in  `pkgname.txt`
'''
from packaging import version
import configparser
import logging
from lilac2 import api as lilac
import argparse
import os
import yaml
from typing import Optional
import sqlite3
from dbmanager import get_bioc_versions
from pkg_archiver import archive_pkg_yaml, archive_pkg_pkgbuild

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


class PkgInfo:
    def __init__(self, pkgname=None, depends=None, optdepends=None,
                 bioc_meta_mirror="https://bioconductor.org",
                 bioc_versions=[],
                 bioc_min_version="3.0",):
        '''
        pkgname: name of the package, style in CRAN and Bioconductor, e.g. "Rcpp",
        depends: depends of the package, style in PKGBUILD, e.g. "r-base". Updated automatically if not provided.
        optdepends: optdepends of the package, style in PKGBUILD, e.g. "r-rmarkdown: for vignettes". Updated automatically if not provided.
        bioc_mirror: remote mirror of Bioconductor, default to "https://bioconductor.org"
        bioc_versions: list of Bioconductor versions to be supported, default to empty list. Updated automatically if not provided.
        bioc_min_version: minimum version of Bioconductor we want to support, default to "3.0".
        '''
        self.pkgname = pkgname
        self.depends = depends
        self.optdepends = optdepends

        self.pkgver = None
        self.new_depends = []
        self.new_optdepends = []
        # newly introduced depends, may be missing in BioArchLinux, need to be added
        self.added_depends = []  # named in  CRAN style

        self.bioc_versions = bioc_versions
        self.bioc_meta_mirror = bioc_meta_mirror
        self.bioc_min_version = bioc_min_version
        # for BIOC pkgs, the latest BIOC version that contains the pkg.
        self.bioc_ver = None

        self.depends_changed = False
        self.optdepends_changed = False

        if self.bioc_versions == []:
            self.bioc_versions = get_bioc_versions(self.bioc_meta_mirror)

    def build_body(self, conn_cursor):
        self.parse_pkgbuild()
        desc = self.get_desc(conn_cursor)
        if desc:
            self.update_info(desc)
            self.merge_depends()

    def __str__(self) -> str:
        return f"""
        Pkgname: {self.pkgname}
        Pkgver: {self.pkgver}
        Depends: {self.depends}
        Optdepends: {self.optdepends}
        new_depends: {self.new_depends}
        new_optdepends: {self.new_optdepends}
        """

    def parse_pkgbuild(self) -> None:
        '''
        use lilac to get _pkgname and depends  and optdepends of PKGBUILD, set the value to self
        '''
        with open('PKGBUILD', 'r') as f:
            lines = f.readlines()
        for line in lines:
            if line.startswith('_pkgname'):
                self.pkgname = line.split(
                    '=')[-1].strip().strip("'").strip('"')
                break
        depends = lilac.obtain_depends()
        optdepends = lilac.obtain_optdepends(parse_dict=False)
        self.depends = depends
        self.optdepends = optdepends

    def get_desc(self, conn_cursor) -> Optional[str]:
        '''
        Get description of the package from database
        conn_cursor: sqlite3 cursor, e.g., `conn = sqlite3.connect('sqlite.db'); conn_cursor = conn.cursor()`
        '''
        c = conn_cursor
        cursor = c.execute(
            "SELECT desc,bioc_ver from pkgmeta where name = ?", (self.pkgname,))
        descall = cursor.fetchone()
        if descall:
            desc, self.bioc_ver = descall
            self.bioc_ver = version.parse(
                self.bioc_ver) if self.bioc_ver else None
            return desc
        else:
            return None

    def is_archived(self) -> bool:
        '''
        Check if the package is archived in CRAN or BIOC
        '''
        if not self.desc:  # not in database, archived in CRAN
            return True
        # not in the latest BIOC version, archived in BIOC
        elif self.bioc_ver and self.bioc_ver != max(self.bioc_versions):
            return True
        return False

    def update_info(self, desc) -> None:
        '''
        obtain new depends and optdepends from `desc`, and write them to `self`
        '''
        if not desc:
            logging.warning(f"Description of {self.pkgname} is empty")
            return
        logging.debug(f"Updating {self.pkgname} using \n {desc}")
        config = configparser.ConfigParser()
        config.read_string('[pkg]\n'+desc)
        self.pkgver = config['pkg'].get('version')
        r_deps = []
        r_optdeps = []
        # depends
        dep_depends = config['pkg'].get('depends')
        if dep_depends:
            r_deps.extend(dep_depends.split(','))
        dep_imports = config['pkg'].get('imports')
        if dep_imports:
            r_deps.extend(dep_imports.split(','))
        dep_linkingto = config['pkg'].get('linkingto')
        if dep_linkingto:
            r_deps.extend(dep_linkingto.split(','))

        r_deps = [_.split('(')[0].strip() for _ in r_deps]
        r_deps = list(set(r_deps) - EXCLUDED_PKGS)

        if '' in r_deps:
            r_deps.remove('')
        # now r_deps contains all depends in named CRAN style
        self.added_depends = [
            x for x in r_deps if f"r-{x.lower()}" not in self.depends]

        self.new_depends += [f"r-{_.lower()}" for _ in r_deps]
        self.new_depends.sort()
        if 'r' in self.new_depends:
            self.new_depends.remove('r')

        # opt depends
        dep_optdepends = config['pkg'].get('suggests')
        if dep_optdepends:
            r_optdeps.extend(dep_optdepends.split(','))
        dep_enhances = config['pkg'].get('enhances')
        if dep_enhances:
            r_optdeps.extend(dep_enhances.split(','))

        r_optdeps = [_.split('(')[0].strip() for _ in r_optdeps]
        if '' in r_optdeps:
            r_optdeps.remove('')

        self.new_optdepends += [f"r-{_.lower()}" for _ in r_optdeps]
        self.new_optdepends.sort()

    def merge_depends(self):
        '''
        Merge old `depends` and `optdepends` in to the new ones
        '''
        system_reqs = [x for x in self.depends if not x.startswith('r-')]
        system_reqs.sort()
        self.new_depends = system_reqs+self.new_depends

        if sorted(self.new_depends) != sorted(self.depends):
            self.depends_changed = True

        # no optdepends
        if not self.optdepends:
            self.optdepends_changed = bool(self.new_optdepends)
            return
        if not self.new_optdepends:
            self.optdepends_changed = bool(self.optdepends)
            return

        # keep explanation of optdepends
        if any(map(lambda x: ':' in x, self.optdepends)):
            self.new_optdepends = [
                x+': ' for x in self.new_optdepends if ':' not in x]
            opt_dict = {pkg.strip(): desc.strip() for (pkg, desc) in
                        (item.split(':', 1) for item in self.optdepends)}

            if sorted(self.new_optdepends) != sorted(opt_dict.keys()):
                self.optdepends_changed = True
            for i in range(len(self.new_optdepends)):
                val = opt_dict.get(self.optdepends[i])
                if val:
                    self.new_optdepends[i] += ': '+val
        else:
            if sorted(self.new_optdepends) != sorted(self.optdepends):
                self.optdepends_changed = True

    def update_pkgbuild(self) -> list[str]:
        '''
        write new depends to PKGBUILD if depends change
        return the newly added depends which may not be in BioArchLinux Repo.
        '''
        if not self.depends_changed and not self.optdepends_changed:
            return
        with open("PKGBUILD", "r") as f:
            lines = f.readlines()

        depends_interval = [-1, -1]
        optdepends_interval = [-1, -1]
        for i, line in enumerate(lines):
            if line.strip().startswith("depends"):
                depends_interval[0] = i
            elif line.strip().startswith("optdepends"):
                optdepends_interval[0] = i

            if depends_interval[0] > -1 and depends_interval[1] == -1:
                if ')' in line:
                    # end depends
                    depends_interval[1] = i
            if optdepends_interval[0] > -1 and optdepends_interval[1] == -1:
                if ')' in line:
                    # end optdepends
                    optdepends_interval[1] = i
        if not (depends_interval[1] < optdepends_interval[0] or optdepends_interval[1] < depends_interval[0]):
            logging.error(
                "depends and optdepends overlap, please fix it manually")
            return

        if self.depends_changed:
            for i in range(depends_interval[0], depends_interval[1]):
                lines[i] = ''
            lines[depends_interval[1]] = '\n'.join(
                ['depends=(', '\n'.join(['  ' + _ for _ in self.new_depends]), ')\n'])

        # new lines for new optdepends
        if self.new_optdepends:
            new_optdepends_line = '\n'.join(
                ['optdepends=(', '\n'.join(
                    ['  ' + _ for _ in self.new_optdepends]), ')\n'])
        if self.optdepends_changed:
            # no old, but has new
            if optdepends_interval[0] == -1:
                # add optdepends
                lines.insert(depends_interval[1]+1, new_optdepends_line)
                optdepends_interval[0] = depends_interval[1]+1
                optdepends_interval[1] = depends_interval[1]+1

            # has old,
            for i in range(optdepends_interval[0], optdepends_interval[1]):
                lines[i] = ''
            if self.new_optdepends:
                lines[optdepends_interval[1]] = new_optdepends_line

        logging.info(f"Writing new PKGBUILD for {self.pkgname}")
        with open("PKGBUILD", "w") as f:
            f.writelines(lines)
        return self.added_depends

    def update_yaml(self, yaml_file='lilac.yaml'):
        '''
        update the `repo_depends` part of pkg, repo_depends will be sorted (systemlibs first, then r-pkgs)
        '''
        with open(yaml_file, "r") as f:
            docs = yaml.load(f, Loader=yaml.FullLoader)
        old_depends = docs.get('repo_depends', [])
        non_r_depends = [x for x in old_depends if not x.startswith('r-')]
        # only keep non-r depends also in new_depends
        non_r_depends = [x for x in non_r_depends if x in self.new_depends]
        non_r_depends.sort()
        r_new_depends = [x for x in self.new_depends if x.startswith('r-')]
        r_new_depends.sort()
        new_deps = non_r_depends+r_new_depends
        if new_deps:
            docs['repo_depends'] = new_deps
        with open(yaml_file, 'w') as f:
            yaml.dump(docs, f, sort_keys=False)


def update_depends_by_file(file, bioarch_path="BioArchLinux", db="sqlite.db",
                           auto_archive=False,
                           bioc_min_ver="3.0", bioc_meta_mirror="https://bioconductor.org", output_file="added_depends.txt"):
    '''
    Update depends of packages listed in `file`, one package name per line, CRAN style(e.g. `Rcpp`) and pkgname style (`r-rcpp`) are both supported.

    file: file containing package names
    bioarch_path: path to BioArchLinux
    db: path to the database to be read
    auto_archive: whether to archive the package if it is not in CRAN or the latest BIOC
    bioc_min_ver: minimum version of Bioconductor to be supported.
    bioc_meta_mirror: The server used to get all version numbers of BIOC
    output_file: file to write the added depends to.
    '''
    bioc_versions = get_bioc_versions(bioc_meta_mirror)
    current_dir = os.getcwd()
    # where the name are _pkgname (May have upper letters) or pkgname (r-xxx)
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    added_deps = []
    with open(file, "r") as f:
        for pkgname in f:
            pkgname = pkgname.strip()
            if not pkgname.strip().startswith("r-"):
                pkgname = "r-"+pkgname.lower()
            logging.info(f"Updating {pkgname}")
            os.chdir(f"{bioarch_path}/{pkgname}")
            pkginfo = PkgInfo(bioc_min_version=bioc_min_ver,
                              bioc_meta_mirror=bioc_meta_mirror, bioc_versions=bioc_versions)
            pkginfo.build_body(cursor)
            pkginfo.update_pkgbuild()
            pkginfo.update_yaml()
            if auto_archive and pkginfo.is_archived():
                archive_pkg_yaml(bioconductor_version=pkginfo.bioc_ver)
                archive_pkg_pkgbuild(bioconductor_version=pkginfo.bioc_ver)
            lilac.update_pkgrel()
            if pkginfo.added_depends:
                added_deps += pkginfo.added_depends
            os.chdir(current_dir)
    conn.close()
    with open(output_file, "w") as f:
        f.write('\n'.join(set(added_deps)))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description='update the depends of R packages from CRAN and Bioconductor automatically',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '-f', '--file', help='The file that contains the pkgname to be archived, one pkgname per line')
    parser.add_argument(
        '-p', '--bioarch_path', help='The path of BioArchLinux repo', default="BioArchLinux")
    parser.add_argument(
        '-db', help="The database file used to query metadata of packages", default="/tmp/dbmanager/sqlite.db")
    parser.add_argument(
        '--bioc_min_ver', help="The minimum version of Bioconductor supported, must be greater than 3.0", default="3.0")
    parser.add_argument(
        '--bioc_meta_mirror', help="The server used to get all version numbers of BIOC", default="https://bioconductor.org")
    parser.add_argument(
        '-o', '--output', help='The file to save newly added depends name', default="added_depends.txt")
    parser.add_argument(
        '-a', '--auto-archive', help='Automatically archive pkgs that are not in CRAN or the latest BIOC release', action='store_true')

    args = parser.parse_args()

    if args.file:
        update_depends_by_file(args.file, args.bioarch_path, args.db,
                               args.bioc_min_ver, bioc_meta_mirror=args.bioc_meta_mirror, output_file=args.output, auto_archive=args.auto_archive)
    else:
        parser.print_help()
