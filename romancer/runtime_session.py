"""Shared preflight and owned, deadline-bounded worker lifecycle."""
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from .asset_schema import number
from .assets import checked_path, hash_stream
from .cd_patch import check_output_paths
from .libretro_frontend import BUTTON_IDS
from .runtime_client import RuntimeClient
from .script_schema import canonical_bytes


def snapshot_json(value):
    return json.loads(canonical_bytes(value,max_bytes=1024*1024))


def validate_steps(steps):
    if type(steps) is not list or not 1<=len(steps)<=100:raise ValueError('runtime requires 1..100 steps')
    total=0
    for step in steps:
        if type(step) is not dict or set(step)!={'frames','buttons','port'}:raise ValueError('invalid runtime step fields')
        total+=number(step['frames'],1,600);number(step['port'],0,3)
        if (type(step['buttons']) is not list or len(step['buttons'])>16
                or any(type(button) is not str or button not in BUTTON_IDS for button in step['buttons'])
                or len(set(step['buttons']))!=len(step['buttons'])):raise ValueError('invalid controller buttons')
    if total>6000:raise ValueError('total runtime frame budget exceeded')
    return steps


def validate_timeout(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=120:
        raise ValueError('runtime deadline must be positive and at most 120 seconds')
    return value


def preflight_load(load,base,*,allow_game_save=False):
    if allow_game_save:
        load=json.loads(canonical_bytes(load,max_bytes=12*1024**2))
        ordinary={k:v for k,v in load.items() if k!='game_save'}
        snapshot_json(ordinary)  # Keep the ordinary configuration budget unchanged.
        if load.get('game_save') is not None:
            from .runtime_worker import _payload
            _payload(load['game_save'],'save_ram_base64')
    else:load=snapshot_json(load)
    base=Path(base).absolute()
    required={'core','game','expected_core_sha256','expected_game_sha256','session_dir'}
    allowed=required|{'system_dir','core_options','game_dependencies','system_files','controller_devices'}|({'game_save'} if allow_game_save else set())
    if type(load) is not dict or not required<=set(load) or set(load)-allowed:raise ValueError('invalid worker load fields')
    for name in ('core','game','session_dir','system_dir'):
        if name in load and load[name] is not None:
            if type(load[name]) is not str or not load[name] or len(load[name])>4096:raise ValueError('invalid runtime path')
            path=Path(load[name]);load[name]=str(checked_path(path if path.is_absolute() else base/path))
    session=Path(load['session_dir'])
    if session.exists():raise ValueError('worker session must be new')
    total=0
    for name in ('core','game'):
        path=Path(load[name]);check_output_paths(path,[session])
        if not path.is_file() or path.stat().st_nlink!=1:raise ValueError('runtime input must be an ordinary file')
        size=path.stat().st_size;total+=size
        if size>(256*1024*1024 if name=='core' else 8*1024*1024*1024):raise ValueError('runtime input too large')
        expected=load['expected_'+name+'_sha256']
        if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('invalid expected runtime hash')
        with path.open('rb') as stream:
            if hash_stream(stream)!=expected:raise ValueError('runtime input revision mismatch')
    if load.get('system_dir') is not None:
        system=Path(load['system_dir'])
        if not system.is_dir() or system==session or system in session.parents or session in system.parents:
            raise ValueError('system directory must exist separately from the session')
    options=load.get('core_options',{})
    from .controller_devices import validate_devices
    validate_devices(load.get('controller_devices',{}))
    if (type(options) is not dict or len(options)>128 or any(type(k) is not str or type(v) is not str
            or not k or len(k)>256 or len(v)>1024 or '\x00' in k+v for k,v in options.items())):
        raise ValueError('invalid bounded core options')
    dependencies=load.get('game_dependencies',[]);names={Path(load['game']).name.casefold()}
    if type(dependencies) is not list or len(dependencies)>512:raise ValueError('too many runtime dependencies')
    for entry in dependencies:
        if type(entry) is not dict or set(entry)!={'source','relative','expected_sha256'}:raise ValueError('invalid runtime dependency')
        relative=entry['relative']
        if (type(relative) is not str or not relative or '\\' in relative or ':' in relative or relative.startswith('/')
                or any(p in ('','.','..') for p in relative.split('/')) or relative.casefold() in names):raise ValueError('unsafe dependency path')
        names.add(relative.casefold());path=Path(entry['source']);path=checked_path(path if path.is_absolute() else base/path)
        if not path.is_file():raise ValueError('missing runtime dependency')
        check_output_paths(path,[session]);entry['source']=str(path);total+=path.stat().st_size
        with path.open('rb') as stream:
            if hash_stream(stream)!=entry['expected_sha256']:raise ValueError('dependency revision mismatch')
    if total>8*1024*1024*1024:raise ValueError('runtime aggregate input budget exceeded')
    if load.get('system_dir') is not None and 'system_files' not in load:
        from .runtime_profiles import measure_system_files
        load['system_files']=[{k:row[k] for k in ('source','relative','expected_sha256')} for row in measure_system_files(load['system_dir'])]
    if 'system_files' in load:
        system_files=load['system_files'];names=set()
        if type(system_files) is not list or len(system_files)>256:raise ValueError('too many system files')
        for entry in system_files:
            if type(entry) is not dict or set(entry)!={'source','relative','expected_sha256'}:raise ValueError('invalid system file')
            relative=entry['relative']
            if type(relative) is not str or not relative or '\\' in relative or ':' in relative or relative.startswith('/') or any(p in ('','.','..') for p in relative.split('/')) or relative.casefold() in names:raise ValueError('unsafe system-file name')
            names.add(relative.casefold());path=Path(entry['source']);path=checked_path(path if path.is_absolute() else base/path)
            if not path.is_file() or path.stat().st_nlink!=1:raise ValueError('system dependency is missing or linked')
            check_output_paths(path,[session]);entry['source']=str(path);total+=path.stat().st_size
            with path.open('rb') as stream:
                if hash_stream(stream)!=entry['expected_sha256']:raise ValueError('system dependency revision mismatch')
        if total>8*1024**3:raise ValueError('runtime input set exceeds8GiB')
    return load


class OwnedRuntime:
    def __init__(self,load,timeout,*,cancelled=None):
        self.load=load;self.timeout=validate_timeout(timeout);self.client=None
        self.cancelled=cancelled
        self.deadline=None;self.close_acknowledged=False;self.exit_code=None

    def remaining(self):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('runtime execution/publication deadline expired')
        return remaining

    def __enter__(self):
        self.deadline=time.monotonic()+self.timeout
        root=str(Path(__file__).resolve().parents[1])
        bootstrap='import sys,runpy;sys.path.insert(0,'+repr(root)+');runpy.run_module("romancer.runtime_worker",run_name="__main__")'
        self.client=RuntimeClient([sys.executable,'-I','-B','-c',bootstrap],timeout=self.remaining(),cancelled=self.cancelled)
        try:
            self.remaining();self.load_result=self.request('load',**self.load);return self
        except BaseException:
            self.__exit__(*sys.exc_info());raise

    def request(self,operation,**parameters):
        self.client.timeout=self.remaining();result=self.client.request(operation,**parameters)
        self.remaining()
        if result.get('ok') is not True:raise ValueError(result.get('error','runtime operation refused'))
        if operation not in ('hello','close'):
            for key in ('core_sha256','game_sha256'):
                if result.get(key)!=self.load['expected_'+key]:raise ValueError('worker binding changed')
        return result

    def close_verified(self):
        self.client.cancelled=None  # Cancellation still requires bounded owned cleanup.
        result=self.request('close')
        if result.get('closed') is not True:raise ValueError('worker did not acknowledge close')
        self.close_acknowledged=True
        self.exit_code=self.client.process.wait(timeout=self.remaining())
        if type(self.exit_code) is not int or self.exit_code!=0:raise ValueError('worker exit was not clean')
        self.remaining()

    def __exit__(self,*exc):
        if self.client is not None:
            self.client.cancelled=None
            self.client.timeout=1.0;self.client.close()
