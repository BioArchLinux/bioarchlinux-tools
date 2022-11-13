#!/usr/bin/python
from lilac2.api import update_pkgrel
import argparse
import os


def main(file, path):
    current_dir = os.getcwd()
    with open(file, "r") as f:
        for pkgname in f.readlines():
            pkgname = pkgname.strip()
            if not pkgname.startswith("r-"):
                pkgname = "r-" + pkgname.lower()
            os.chdir(f"{path}/{pkgname}")
            update_pkgrel()
            os.chdir(current_dir)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='update pkgrel for a list of R packages',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '-f', '--file', help='file contains pkgname, one per line, CRAN name style or aur name style are both ok')
    parser.add_argument('-b', '--bioarch-path',
                        help='path to BioArchLinux', default='BioArchLinux')
    args = parser.parse_args()
    if not args.file:
        parser.print_help()
        exit(1)

    main(args.file, args.bioarch_path)
