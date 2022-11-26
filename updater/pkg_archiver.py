#!/usr/bin/python

'''
Update the PKGBUILD and lilac.yaml of archived pkgs in `pkgname.txt`
'''
import os
import yaml
import argparse
from lilac2.api import update_pkgrel
import re


def archive_pkg_by_file_list(file, bioarch_path="BioArchLinux", biconductor_version=3.15, step=1):
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
            archive_pkg_yaml(biconductor_version)
            changed = archive_pkg_pkgbuild(biconductor_version)
            if changed:
                update_pkgrel()
            os.chdir(current_dir)


def archive_pkg_yaml(bioconductor_version=3.15, yaml_file="lilac.yaml"):
    '''
    archive pkg in CRAN and bioconductor (the latest bioconductor_version that contains the pkg  needed)
    '''
    with open(yaml_file, "r") as f:
        docs = yaml.load(f, Loader=yaml.FullLoader)
    url_idx = -1
    url = None
    for i in range(len(docs['update_on'])):
        if "url" in docs['update_on'][i].keys():
            url = docs['update_on'][i]['url']
            url_idx = i
            break

    if not url:
        return
    pkg = url.rstrip('/').split('/')[-1]
    archive_url = None
    # CRAN ARCHIVE
    if 'cran.r-project.org' in url:
        archive_url = f"https://cran.r-project.org/src/contrib/Archive/{pkg}"
    # Bioconductor ARCHIVE
    elif 'bioconductor.org' in url:
        archive_url = url.replace('release', f"{bioconductor_version}")
    if archive_url:
        docs['update_on'][url_idx]['url'] = archive_url
    with open(yaml_file, 'w') as f:
        yaml.dump(docs, f, sort_keys=False)


def archive_pkg_pkgbuild(bioconductor_version=3.15, _pkgname="_pkgname"):
    '''
    Under some cases, _pkgname maybe _cranname
    '''
    with open("PKGBUILD", "r") as f:
        lines = f.readlines()

    changed = False
    flag = False
    for i in range(len(lines)):

        if lines[i].startswith("url=") and '//bioconductor.org' in lines[i] and not re.search("packages/[\d.]+", lines[i]):
            lines[i] = lines[i].replace(
                "packages/", f"packages/{bioconductor_version}/")
            changed = True

        if lines[i].startswith("source="):
            flag = True
        if flag:
            new_line = lines[i]
            if 'cran.r-project.org' in lines[i] and "src/contrib/Archive" not in lines[i]:
                # https://cran.r-project.org/src/contrib/${_pkgname}_${pkgver}.tar.gz
                # to
                # https://cran.r-project.org/src/contrib/Archive/${_pkgname}/${_pkgname}_${pkgver}.tar.gz
                new_line = lines[i].replace(
                    "src/contrib", "src/contrib/Archive/${_pkgname}")
            elif '//bioconductor.org' in lines[i] and bioconductor_version != None:
                # https://bioconductor.org/packages/release/bioc/src/contrib/${_pkgname}_${_pkgver}.tar.gz
                # to
                # https://bioconductor.org/packages/3.14/bioc/src/contrib/ABAEnrichment_1.24.0.tar.gz
                new_line = lines[i].replace(
                    "packages/release/bioc", f"packages/{bioconductor_version}/bioc")
            else:
                NotImplemented
            if new_line != lines[i]:
                changed = True
                lines[i] = new_line
    with open("PKGBUILD", "w") as f:
        f.writelines(lines)
    return changed


def unarchive_cran():
    unarchive_cran_pkgbuild()
    unarchive_cran_yaml()


def unarchive_cran_pkgbuild():
    with open("PKGBUILD", "r") as f:
        lines = f.readlines()
    for i in range(len(lines)):
        if lines[i].startswith("source="):
            if "src/contrib/Archive" in lines[i]:
                lines[i] = lines[i].replace(
                    "src/contrib/Archive/${_pkgname}", "src/contrib")
    with open("PKGBUILD", "w") as f:
        f.writelines(lines)


def unarchive_cran_yaml():
    with open("lilac.yaml", "r") as f:
        docs = yaml.load(f, Loader=yaml.FullLoader)
    url_idx = -1
    url = None
    for i in range(len(docs['update_on'])):
        if "url" in docs['update_on'][i].keys():
            url = docs['update_on'][i]['url']
            url_idx = i
            break
    if not url:
        return
    pkg = url.rstrip('/')
    pkg = re.split('/|=', pkg)[-1]
    archive_url = None
    # CRAN ARCHIVE
    if 'cran.r-project.org' in url:
        archive_url = f"https://cran.r-project.org/package={pkg}"
    if archive_url:
        docs['update_on'][url_idx]['url'] = archive_url
    with open("lilac.yaml", 'w') as f:
        yaml.dump(docs, f, sort_keys=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--file', help='The file that contains the pkgname to be archived, one pkgname per line')
    parser.add_argument(
        '--bioarch_path', help='The path of BioArchLinux repo', default="BioArchLinux")
    parser.add_argument(
        '--bioc_ver', help="The Bioconductor version to be used in archived url", default="3.15")
    args = parser.parse_args()

    if args.file:
        archive_pkg_by_file_list(args.file, args.bioarch_path, args.bioc_ver)
    else:
        parser.print_help()
