"""Automatic, local engine defaults with an explicit redistribution inventory."""
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import platform

from .assets import checked_path
from .core_pins import CORE_PINS,CORE_FILES

DEFAULT_KEYS={'up':'ArrowUp','down':'ArrowDown','left':'ArrowLeft','right':'ArrowRight',
              'a':'z','b':'x','x':'a','y':'s','l':'q','r':'w','start':'Enter','select':'Shift'}


def pack_root():
    return Path(__file__).resolve().parents[2]/'cores'


def packaged_release():
    app=Path(__file__).resolve().parents[1]
    return app.name=='app' and (app.parent/'python/python314._pth').is_file()


def require_reviewed_release_core(path):
    """Official Windows playback accepts only the shipped source/license pins.

    Source developers retain access to original synthetic native test fixtures.
    The distributed runtime never executes an unreviewed replacement library.
    """
    if not packaged_release():return None
    with checked_path(Path(path)).open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    for pin in CORE_PINS.values():
        if sha==pin['sha256'] and pin.get('license') and pin.get('source_url') and pin.get('source_commit'):return pin
    raise ValueError('This release runs only reviewed open-source emulator cores. Select an included engine or reinstall the full Windows package; an unknown or changed core is blocked.')


def host_supported():
    return os.name=='nt' and platform.machine().lower() in ('amd64','x86_64')


def _fingerprint(root):
    root=checked_path(root)
    if not CORE_FILES:raise ValueError('bundled engines have no reviewed inventory')
    actual=set()
    for path in root.rglob('*'):
        checked_path(path)
        if path.is_file():actual.add(path.relative_to(root).as_posix())
    if actual!=set(CORE_FILES):raise ValueError('bundled engine pack has unlisted or missing files; reinstall this version')
    stamps=[]
    for name,expected in sorted(CORE_FILES.items()):
        path=root/name;stat=path.stat()
        if stat.st_size!=expected['size'] or stat.st_nlink!=1:raise ValueError('bundled engine identity differs; reinstall this version')
        stamps.append((name,stat.st_size,stat.st_mtime_ns,stat.st_ino,expected['sha256']))
    return tuple(stamps)


def core_members(root):
    """Build-time verification also requires the corresponding source and notices."""
    root=Path(root);stamp=_fingerprint(root);result={}
    for name,size,mtime,inode,sha in stamp:
        path=root/name
        with path.open('rb') as stream:raw=stream.read(64*1024**2+1)
        if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('bundled engine identity differs: '+name)
        result[name]=raw
    if _fingerprint(root)!=stamp:raise ValueError('bundled engine pack changed while reading')
    return result


@lru_cache(maxsize=4)
def _verify_cached(root,stamp):
    core_members(root)
    return True


def bundled_profile(system_id):
    root=pack_root()
    if not host_supported() or not root.exists():return None
    engine_id='gb' if system_id=='gbc' else 'genesis' if system_id=='sms' else system_id
    if engine_id not in CORE_PINS:return None
    stamp=_fingerprint(root);_verify_cached(str(root),stamp)
    pin=CORE_PINS[engine_id]
    from .runtime_profiles import _binary,_identity
    binary=_binary(root/pin['file'])
    if binary['sha256']!=pin['sha256']:raise ValueError('bundled engine identity differs; reinstall this version')
    profile={'schema_version':1,'system_id':system_id,'core':str(root/pin['file']),
             'core_identity':binary,'options':dict(pin['options']),'system_dir':None,
             'system_files':[],'input_map':dict(DEFAULT_KEYS)}
    if system_id=='sms':profile['options'].update({'blastem_system_type':'sms','blastem_io_1':'gamepad2.1','blastem_io_2':'gamepad2.2'})
    if system_id=='gbc':profile['options']['gambatte_gb_hwmode']='GBC'
    profile['identity']=_identity(profile)
    return {'ok':True,'status':'BUNDLED','profile':profile,'engine':pin['name'],'runtime_verified':False}
