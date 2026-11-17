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
    if app.name!='app':return False
    # Windows embeds python314._pth; the Linux release marks its engine folder.
    return (app.parent/'python/python314._pth').is_file() or (app.parent/'cores/LINUX-ENGINES.json').is_file()


def require_reviewed_release_core(path):
    """Official Windows playback accepts only the shipped source/license pins.

    Source developers retain access to original synthetic native test fixtures.
    The distributed runtime never executes an unreviewed replacement library.
    """
    if not packaged_release():return None
    with checked_path(Path(path)).open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    for pin in CORE_PINS.values():
        if sha==pin['sha256'] and pin.get('license') and pin.get('source_url') and pin.get('source_commit'):return pin
    raise ValueError('This release runs only reviewed open-source emulator cores. Select an included engine or reinstall the full ROMancer package; an unknown or changed core is blocked.')


def host_supported():
    if platform.machine().lower() not in ('amd64','x86_64'):return False
    return os.name=='nt' or (pack_root()/'LINUX-ENGINES.json').is_file()


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


TOP_GEAR_3000_DSP4_SHA256 = '6be49983976564f1fd9eff2f14f5bb41d3a0ff48573e39318088ecce286aca62'

SNES_CHIP_CARTRIDGES = frozenset({
    '03d0127f5de3237e22ad00de0c20763274da7b71142dde693240ac96d10983a3',
    '2ada8919688087be60a6a48cace8f877add60c45d2e5d09e2442faa55be62a49',
    '65b03268afac296330e8ff8d60dd0825879e13ed658b37713c034a3bd074f1d7',
    'f3246755f608a1e1dc9c848b61da3b824c7853b29b3be40df6fc7f2793a887ed',
})


def cartridge_engine(system_id, source_sha256=None):
    """Select checked compatibility settings for specific cartridge revisions."""
    if system_id == 'snes' and source_sha256 == TOP_GEAR_3000_DSP4_SHA256:
        return 'snes-dsp4', {'bsnes_violate_accuracy': 'enabled', 'bsnes_chip_hle': 'HLE'}
    if system_id == 'snes' and source_sha256 in SNES_CHIP_CARTRIDGES:
        # Mercury ignores its HLE option unless the accuracy gate is enabled.
        return 'snes', {'bsnes_violate_accuracy': 'enabled', 'bsnes_chip_hle': 'HLE'}
    if system_id == 'genesis' and source_sha256 == '3fdb9dd4e1c98760ec2c57af08f1c172a9f964a695c3f07e8a28c4eb5819082d':
        # Target Earth has a leading space in the system field.
        return 'genesis', {'blastem_system_type': 'gen'}
    if system_id == 'gbc' and source_sha256 == '6cf412aeb1ec60da1a401019d95dee1e76f0297154a7f06b55fb1657a71ed44f':
        return 'gbc-tilt', {'romancer_mbc7_tilt': 'dpad-v1'}
    return {'gbc': 'gb', 'sms': 'genesis'}.get(system_id, system_id), {}


def bundled_profile(system_id, *, source_sha256=None):
    root=pack_root()
    if not host_supported() or not root.exists():return None
    engine_id, compatibility = cartridge_engine(system_id, source_sha256)
    if engine_id not in CORE_PINS:return None
    stamp=_fingerprint(root);_verify_cached(str(root),stamp)
    pin=CORE_PINS[engine_id]
    from .runtime_profiles import _binary,_identity
    binary=_binary(root/pin['file'])
    if binary['sha256']!=pin['sha256']:raise ValueError('bundled engine identity differs; reinstall this version')
    profile={'schema_version':1,'system_id':system_id,'core':str(root/pin['file']),
             'core_identity':binary,'options':{**pin['options'], **compatibility},'system_dir':None,
             'system_files':[],'input_map':dict(DEFAULT_KEYS)}
    if system_id=='sms':profile['options'].update({'blastem_system_type':'sms','blastem_io_1':'gamepad2.1','blastem_io_2':'gamepad2.2'})
    if system_id=='gbc' and engine_id=='gb':profile['options']['gambatte_gb_hwmode']='GBC'
    profile['identity']=_identity(profile)
    return {'ok':True,'status':'BUNDLED','profile':profile,'engine':pin['name'],'runtime_verified':False}
