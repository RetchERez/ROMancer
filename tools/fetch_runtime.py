"""Fetch only the pinned public runtime inputs; never replace an existing cache file."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.package_windows import PINS

MAX_DOWNLOAD=64*1024**2


def fetch_pin(directory,pin,*,opener=urlopen,allowed_hosts=('www.python.org','files.pythonhosted.org')):
    name=pin['file'];url=urlsplit(pin['url'])
    if (type(name) is not str or Path(name).name!=name or '/' in name or '\\' in name or ':' in name
            or not re.fullmatch('[0-9a-f]{64}',pin['sha256']) or url.scheme!='https'
            or url.hostname not in allowed_hosts or url.username or url.password):
        raise ValueError('unsafe runtime name, URL or hash')
    directory=Path(directory).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (directory,*directory.parents)):raise ValueError('linked runtime cache is not supported')
    directory.mkdir(parents=True,exist_ok=True);target=directory/name
    if target.exists():
        if target.is_symlink() or not target.is_file() or target.stat().st_nlink!=1:raise ValueError('invalid runtime cache file')
        if target.stat().st_size>MAX_DOWNLOAD:raise ValueError('runtime cache exceeds byte budget')
        with target.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=pin['sha256']:raise ValueError('existing runtime cache hash differs from pin; choose a fresh cache directory')
        return target
    fd,temporary=tempfile.mkstemp(prefix='.runtime-',dir=directory);temporary=Path(temporary)
    try:
        total=0;digest=hashlib.sha256()
        with os.fdopen(fd,'wb') as output,opener(pin['url'],timeout=30) as response:
            while chunk:=response.read(65536):
                total+=len(chunk)
                if total>MAX_DOWNLOAD:raise ValueError('runtime download exceeds byte budget')
                digest.update(chunk);output.write(chunk)
        if digest.hexdigest()!=pin['sha256']:raise ValueError('downloaded runtime hash differs from pin')
        os.link(temporary,target)
        return target
    finally:temporary.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--downloads',type=Path,required=True);args=parser.parse_args()
    for name,pin in PINS.items():
        result=fetch_pin(args.downloads,pin);print(f'{name}: verified {result.name}')


if __name__=='__main__':main()
