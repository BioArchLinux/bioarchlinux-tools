#!/usr/bin/python
'''
Update the `depends` and `optdepends` part of an R package PKGBUILD listed in  `pkgname.txt`
'''
import requests
from re import findall
from packaging import version
import configparser
import logging
from lilac2 import api as lilac
import argparse
import os
import yaml
from typing import Optional

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
                 cran_meta_mirror="https://cran.r-project.org",
                 bioc_meta_mirror="https://bioconductor.org",
                 bioc_versions=[],
                 bioc_min_version="3.0",):
        '''
        pkgname: name of the package, style in CRAN and Bioconductor, e.g. "Rcpp",
        depends: depends of the package, style in PKGBUILD, e.g. "r-base". Updated automatically if not provided.
        optdepends: optdepends of the package, style in PKGBUILD, e.g. "r-rmarkdown: for vignettes". Updated automatically if not provided.
        cran_meta_mirror: remote mirror of CRAN use to download PACKAGES file, default to "https://cran.r-project.org"
        bioc_meta_mirror: remote mirror of Bioconductor use to download PACKAGES file, default to "https://bioconductor.org"
        bioc_versions: list of Bioconductor versions to be supported, default to empty list. Updated automatically if not provided.
        bioc_min_version: minimum version of Bioconductor we want to support, default to "3.0".
        '''
        self.pkgname = pkgname
        self.depends = depends
        self.optdepends = optdepends

        self.pkgver = None
        self.new_depends = []
        self.new_optdepends = []

        self.bioc_versions = bioc_versions
        self.cran_meta_mirror = cran_meta_mirror
        self.bioc_meta_mirror = bioc_meta_mirror
        self.bioc_min_version = bioc_min_version

        self.depends_changed = False
        self.optdepends_changed = False

        if self.bioc_versions == []:
            self.set_bioc_versions()
        self.parse_pkgbuild()
        desc = self.get_desc()
        self.update_info(desc)
        self.merge_depends()

    def set_bioc_versions(self) -> None:
        '''
        get all Bioconductor versions
        '''
        version_page = requests.get(
            f"{self.bioc_meta_mirror}/bioc_version")
        if version_page.status_code != requests.codes.ok:
            raise RuntimeError(
                f"Failed to get Bioconductor versions due to: {version_page.status_code}: {version_page.reason}")
        z = version_page.text.split(',')

        self.bioc_versions = list(map(lambda x: version.parse(x), z))

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

    def get_desc(self) -> Optional[str]:
        '''
        get new depends from CRAN or Bioconductor
        '''
        pkgname = self.pkgname
        CRAN_URL = f"{self.cran_meta_mirror}/src/contrib/PACKAGES"

        # try cran first
        r_cran = requests.get(CRAN_URL)
        if r_cran.status_code == requests.codes.ok:
            self.cran_descs = r_cran.text.split('\n\n')
            for desc in self.cran_descs:
                if desc.startswith(f'Package: {pkgname}'):
                    logging.info(f"Found {pkgname} in CRAN")
                    return desc
        else:
            raise RuntimeError(
                f"Failed to get CRAN descriptions due to: {r_cran.status_code}: {r_cran.reason}")

        # try bioconductor
        for ver in self.bioc_versions:
            if ver < version.parse(self.bioc_min_version):
                continue
            for p in ['bioc', 'data/annotation', 'data/experiment']:
                url = f"{self.bioc_meta_mirror}/packages/{ver}/{p}/src/contrib/PACKAGES"
                bioconductor_descs = requests.get(url)
                if bioconductor_descs.status_code == requests.codes.ok:
                    bioconductor_descs = bioconductor_descs.text.split('\n\n')
                    for desc in bioconductor_descs:
                        if desc.startswith(f'Package: {pkgname}'):
                            logging.info(
                                f"Found {pkgname} in Bioconductor {ver}: {p}")
                            return desc
                else:
                    logging.error(
                        f'Failed to get Bioconductor descriptions for version: {ver}, {p}, due to: {bioconductor_descs.status_code}: {bioconductor_descs.reason}')
                    continue

    def update_info(self, desc) -> None:
        '''
        obtain new depends and optdepends from `desc`, and write them to `self`
        '''
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

    def update_pkgbuild(self):
        '''
        write new depends to PKGBUILD if depends change
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
        if self.optdepends_changed:
            for i in range(optdepends_interval[0], optdepends_interval[1]):
                lines[i] = ''
            if self.new_optdepends:
                lines[optdepends_interval[1]] = '\n'.join(
                    ['optdepends=(', '\n'.join(['  ' + _ for _ in self.new_optdepends]), ')\n'])

        logging.info(f"Writing new PKGBUILD for {self.pkgname}")
        with open("PKGBUILD", "w") as f:
            f.writelines(lines)

    def update_yaml(self, yaml_file='lilac.yaml'):
        '''
        update the `repo_depends` part of pkg
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


def update_depends_by_file(file, bioarch_path="BioArchLinux", bioc_min_ver="3.0", cran_meta_mirror="https://cran.r-project.org",
                           bioc_meta_mirror="https://bioconductor.org",):
    '''
    Update depends of packages listed in `file`, one package name per line, CRAN style(e.g. `Rcpp`) and pkgname style (`r-rcpp`) are both supported.
    file: file containing package names
    bioarch_path: path to BioArchLinux
    bioc_min_ver: minimum version of Bioconductor to be supported, generally not needed to be changed
    cran_meta_mirror: mirror of CRAN metadata, recommended to be changed to a local https mirror.
    bioc_meta_mirror: mirror of Bioconductor metadata, recommended to be changed to a local https mirror.
    '''
    current_dir = os.getcwd()
    # where the name are _pkgname (May have upper letters) or pkgname (r-xxx)
    case = "_pkgname"
    with open(file, "r") as f:
        for pkgname in f:
            pkgname = pkgname.strip()
            if pkgname.startswith("r-"):
                case = "pkgname"
                break
    with open(file, "r") as f:
        for pkgname in f:
            pkgname = pkgname.strip()
            if case == '_pkgname':
                pkgname = 'r-'+pkgname.lower()
            os.chdir(f"{bioarch_path}/{pkgname}")
            pkginfo = PkgInfo(bioc_min_version=bioc_min_ver,
                              bioc_meta_mirror=bioc_meta_mirror, cran_meta_mirror=cran_meta_mirror)
            pkginfo.update_pkgbuild()
            pkginfo.update_yaml()
            os.chdir(current_dir)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='update the depends of R packages from CRAN and Bioconductor automatically',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--file', help='The file that contains the pkgname to be archived, one pkgname per line')
    parser.add_argument(
        '--bioarch_path', help='The path of BioArchLinux repo', default="BioArchLinux")
    parser.add_argument(
        '--bioc_min_ver', help="The minimum version of Bioconductor supported, must be greater than 3.0", default="3.0")
    parser.add_argument(
        '--cran_meta_mirror', help="The mirror of CRAN metadata, recommended to be changed to a local https mirror. Only http(s) is supported", default="https://cran.r-project.org")
    parser.add_argument(
        '--bioc_meta_mirror', help="The mirror of Bioconductor metadata, recommended to be changed to a local https mirror. Only http(s) is supported", default="https://bioconductor.org")

    args = parser.parse_args()

    if args.file:
        update_depends_by_file(args.file, args.bioarch_path, args.bioc_min_ver,
                               cran_meta_mirror=args.cran_meta_mirror, bioc_meta_mirror=args.bioc_meta_mirror)
    else:
        parser.print_help()
