#!/usr/bin/python
# -*- coding: utf-8 -*-
import requests
import re
from pathlib import Path
from packaging import version
import logging
from distutils.dir_util import copy_tree
import os
import datetime
from dateutil.parser import parse as parsedate
import argparse


class Downloader:
    def __init__(self, bioc_mirror="https://bioconductor.org", cran_mirror="https://cran.r-project.org", bioc_min_ver="3.0") -> None:
        '''
        bioc_mirror: remote Bioconductor mirror, default https://bioconductor.org
        cran_mirror: remote CRAN mirror, default https://cran.r-project.org
        bioc_min_ver: minimum version of Bioconductor to download, default 3.0
        '''
        self.bioc_mirror = bioc_mirror
        self.cran_mirror = cran_mirror
        self.bioc_min_ver = bioc_min_ver
        self.bioc_versions = []
        self.set_bioc_versions()

    def set_bioc_versions(self):
        '''
        obtain and set all available Bioconductor versions from remote mirror.
        '''
        version_page = requests.get(
            f"{self.bioc_mirror}/about/release-announcements/#release-versions/")
        if version_page.status_code != requests.codes.ok:
            raise RuntimeError(
                f"Failed to get Bioconductor versions due to: {version_page.status_code}: {version_page.reason}")
        z = re.findall(r"/packages/(\d.\d+)/", version_page.text)

        # mannually add 1.7 to 1.0 to the list.
        for i in range(7, -1, -1):
            z.append(f"1.{i}")

        self.bioc_versions = list(map(lambda x: version.parse(x), z))

    def download_package_meta(self, path='bioc'):
        '''
        Download package metadata from Bioconductor and CRAN.

        min_ver: minimum version of Bioconductor to download, default 3.0.
        path: path to save metadata, default 'bioc' under current directory.
        '''
        min_ver = self.bioc_min_ver
        if path and not path.endswith('/'):
            path = path+'/'
        else:
            path = ''

        # BIOC
        latestver = self.bioc_versions[0]
        for p in ['bioc', 'data/annotation', 'data/experiment']:
            for ver in self.bioc_versions:
                logging.info(f"Downloading Bioconductor {ver} {p}...")
                if ver >= version.parse(min_ver):
                    Path(
                        path+f'packages/{ver}/{p}/src/contrib/'
                    ).mkdir(parents=True, exist_ok=True)
                    url = f"{self.bioc_mirror}/packages/{ver}/{p}/src/contrib/PACKAGES"
                    dstFile = path+f'packages/{ver}/{p}/src/contrib/PACKAGES'
                    if not remote_is_newer(url, dstFile):
                        logging.info(
                            f"Local Package List for Bioconductor below {ver}: {p} is newer than remote, skip.")
                        break
                    meta = requests.get(url)
                    if meta.status_code != requests.codes.ok:
                        logging.error(
                            f"failed to download Package List for Bioconductor {ver}: {p} due to {meta.status_code}: {meta.reason}")
                    else:
                        with open(dstFile, 'w') as f:
                            f.write(meta.text)
        copy_tree(path+f'packages/{latestver}', path+f'packages/release')

        bioc_ver_file = path+'bioc_version'
        with open(bioc_ver_file, 'w') as f:
            f.write(','.join(map(lambda x: str(x), self.bioc_versions)))

        # CRAN
        logging.info("Downloading CRAN metadata...")
        url = f"{self.cran_mirror}/src/contrib/PACKAGES"
        dstFile = path+f'src/contrib/PACKAGES'
        if remote_is_newer(url, dstFile):
            meta = requests.get(url)
            if meta.status_code != requests.codes.ok:
                logging.error(
                    f"failed to download Package List for CRAN due to {meta.status_code}: {meta.reason}")
            else:
                Path(path+f'src/contrib/').mkdir(parents=True, exist_ok=True)
                with open(dstFile, 'w') as f:
                    f.write(meta.text)
        else:  # skip if local is newer
            logging.info(
                "Local Package List for CRAN is newer than remote, skip.")


def remote_is_newer(url, dstFile) -> bool:
    '''
    whether the remote file is newer than local file.
    return True if dstFile does not exist.
    returns False if remote does not provide `Last-Modified` header.
    '''
    if not os.path.exists(dstFile):
        return True
    r = requests.head(url)
    url_time = r.headers.get('last-modified')
    if not url_time:
        return False

    url_date = parsedate(url_time)
    file_time = datetime.datetime.fromtimestamp(
        os.path.getmtime(dstFile))
    return url_date > file_time.astimezone()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = Downloader()
    download_path = os.getenv('BIO_META_PATH', 'bioc')
    parser = argparse.ArgumentParser(
        description='Sync metadata of R packages from CRAN and Bioconductor to a local path',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--path', help='The path to store the metadata files. '
        "if not given the environment variable BIO_META_PATH will be read, if it's not set, the default (bioc) will be used.",
        default='bioc')
    parser.add_argument(
        '--bioc_min_ver', help="The minimum version of Bioconductor supported, must be greater than 3.0", default="3.0")
    parser.add_argument(
        '--cran_meta_mirror', help="The remote mirror of CRAN metadata, only http(s) is supported", default="https://cran.r-project.org")
    parser.add_argument(
        '--bioc_meta_mirror', help="The remote mirror of Bioconductor metadata, only http(s) is supported", default="https://bioconductor.org")

    args = parser.parse_args()

    d.download_package_meta(download_path)
