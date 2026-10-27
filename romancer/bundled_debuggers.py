"""Pinned full Windows observers, with matching sources and retained notices."""
from functools import lru_cache
import hashlib
from pathlib import Path
from .assets import checked_path
from .observer_pins import OBSERVER_FILES

def _stamp(root):
    root=checked_path(Path(root));actual=set()
    for p in root.rglob('*'):
        checked_path(p)
        if p.is_file():actual.add(p.relative_to(root).as_posix())
    if actual!=set(OBSERVER_FILES):raise ValueError('Native observer pack has missing or unlisted files. Reinstall the complete package.')
    result=[]
    for name,pin in sorted(OBSERVER_FILES.items()):
        p=checked_path(root/name);s=p.stat()
        if s.st_size!=pin['size'] or s.st_nlink!=1:raise ValueError('Native observer source or binary extent differs: '+name)
        result.append((name,s.st_size,s.st_mtime_ns,s.st_ino,pin['sha256']))
    return tuple(result)

@lru_cache(maxsize=2)
def _verify(root,stamp):
    root=Path(root)
    for name,size,mtime,inode,sha in stamp:
        with (root/name).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=sha:raise ValueError('Native observer pinned bytes differ: '+name)
    if _stamp(root)!=stamp:raise ValueError('Native observer pack changed while checking')
    return True

def observer_files(root):
    root=Path(root);stamp=_stamp(root);_verify(str(root),stamp)
    return {name:root/name for name,*_ in stamp}

def verify_installed(root):
    root=Path(root)
    if root.parent.name=='debuggers' and (root.parent.parent/'BUNDLE.json').is_file():
        observer_files(root.parent)
