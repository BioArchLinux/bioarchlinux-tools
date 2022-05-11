from pathlib import Path
import time

MY_GITHUB = 'BioArchLinuxBot'
REPO_NAME = 'BioArchLinux/Packages'

ADMIN_GH = 'starsareintherose'

REPO_URL = f'git@github.com:{REPO_NAME}.git'
MYMAIL = 'lilac@bioarchlinux.org'
REPODIR = Path('/usr/share/archgitrepo-webhook/bioarchlinux').expanduser()

def gen_log_comment(pkgs: list[str]) -> str:
  ss = ['''\
| pkgbase | build history | last build log |
| --- | --- | --- |''']
  t = int(time.time())
  for pkg in set(pkgs):
    ss.append(f'''\
| {pkg} \
| [build history](https://build.bioarchlinux.org/#{pkg}) \
| [last build log](https://build.bioarchlinux.org/api/pkg/{pkg}/log/{t}) |''')
  return '\n'.join(ss)
