"""Fetch/extract the pinned public engine pack for a Windows release build."""
import argparse
import hashlib
from pathlib import Path
import sys
import tempfile
import zipfile

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from romancer.core_pins import CORE_ARCHIVE,CORE_FILES
from romancer.bundled_cores import core_members
from tools.fetch_runtime import fetch_pin
from tools.install_windows import safe_name


def extract_pack(archive,destination):
    archive=Path(archive);destination=Path(destination).absolute()
    if archive.stat().st_size>64*1024**2:raise ValueError('engine archive exceeds budget')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=CORE_ARCHIVE['sha256']:raise ValueError('engine archive hash differs from release pin')
    if destination.exists():core_members(destination);return destination
    for part in (destination,*destination.parents):
        if part.is_symlink() or part.is_junction():raise ValueError('linked engine directory')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        seen=set()
        for item in z.infolist():
            name=safe_name(item.filename)
            if name not in CORE_FILES or name in seen or item.is_dir() or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('unlisted or duplicate engine member')
            if item.file_size!=CORE_FILES[name]['size']:raise ValueError('engine member size differs')
            seen.add(name)
        if seen!=set(CORE_FILES):raise ValueError('missing engine/source/license member')
        with tempfile.TemporaryDirectory(prefix='.engine-pack-',dir=destination.parent) as temp:
            stage=Path(temp)/'cores';stage.mkdir()
            for item in z.infolist():
                path=stage/item.filename;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(item))
            core_members(stage)
            from romancer.patch_sets import _publish_directory
            _publish_directory(stage,destination)
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--downloads',type=Path,required=True)
    parser.add_argument('--archive',type=Path,help='Previously downloaded official engine archive')
    args=parser.parse_args();archive=args.archive or fetch_pin(args.downloads,CORE_ARCHIVE,allowed_hosts=('github.com',))
    print(extract_pack(archive,args.downloads/'cores'))
