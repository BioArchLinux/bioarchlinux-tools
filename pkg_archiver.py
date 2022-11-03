#!/usr/bin/python

'''
Update the PKGBUILD and lilac.yaml of archived pkgs in `pkgname.txt`
'''
import os
import fileinput
import re
import yaml
import argparse


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
            bump_pkgrel(step)
            archive_pkg_yaml(biconductor_version)
            archive_pkg_pkgbuild(biconductor_version)
            os.chdir(current_dir)


def bump_pkgrel(step=1):
    with fileinput.input(r"PKGBUILD", inplace=True) as f:
        for line in f:
            if line.startswith("pkgrel="):
                new_pkgrel = int(line.split("=")[1])+step
                line = re.sub(
                    r'pkgrel=\d+', f'pkgrel={new_pkgrel}', line)
                break
            print(line.rstrip())


def archive_pkg_yaml(bioconductor_version=3.15, yaml_file="lilac.yaml"):
  '''
  archive pkg in CRAN and bioconductor (the latest bioconductor_version that contains the pkg  needed)
  '''
    with open(yaml_file, "r") as f:
        docs = yaml.load(f, Loader=yaml.FullLoader)
        print(docs)
    url_idx = -1
    for i in range(len(docs['update_on'])):
        if "url" in docs['update_on'][i].keys():
            url = docs['update_on'][i]['url']
            url_idx = i
            break

    pkg = url.rstrip('/').split('/')[-1]
    # CRAN ARCHIVE
    if 'cran.r-project.org' in url:
        archive_url = f"https://cran.r-project.org/src/contrib/Archive/{pkg}"
    # Bioconductor ARCHIVE
    elif 'bioconductor.org' in url:
        archive_url = f"https://bioconductor.org/packages/{bioconductor_version}/{pkg}"

    docs['update_on'][url_idx]['url'] = archive_url
    with open(yaml_file, 'w') as f:
        yaml.dump(docs, f)


def archive_pkg_pkgbuild(bioconductor_version=3.15, _pkgname="_pkgname"):
    '''
    Under some cases, _pkgname maybe _cranname
    '''
    with open("PKGBUILD", "r") as f:
        lines = f.readlines()

    flag = False
    for i in range(len(lines)):
        if lines[i].startswith("source="):
            flag = True
        if flag:
            if 'cran.r-project.org' in lines[i] and "src/contrib/Archive" not in lines[i]:
                # https://cran.r-project.org/src/contrib/${_pkgname}_${pkgver}.tar.gz
                # to
                # https://cran.r-project.org/src/contrib/Archive/${_pkgname}/${_pkgname}_${pkgver}.tar.gz
                lines[i] = lines[i].replace(
                    "src/contrib", r"src/contrib/Archive/${" + _pkgname + '}')
            elif '//bioconductor.org' in lines[i]:
                # https://bioconductor.org/packages/release/bioc/src/contrib/${_pkgname}_${_pkgver}.tar.gz
                # to
                # https://bioconductor.org/packages/3.14/bioc/src/contrib/ABAEnrichment_1.24.0.tar.gz
                lines[i] = lines[i].replace(
                    "packages/release/bioc", f"packages/{bioconductor_version}/bioc")
    with open("PKGBUILD", "w") as f:
        f.writelines(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--file', help='The file that contains the pkgname to be archived, one pkgname per line')
    parser.add_argument('--bioarch_path', help='The path of BioArchLinux repo')
    parser.add_argument(
        '--bico_ver', help='The Bioconductor version to be used in archived url, default 3.15')
    args = parser.parse_args()
    if args.file:
        archive_pkg_by_file_list(args.file, args.bioarch_path, args.bico_ver)
    else:
        parser.print_help()