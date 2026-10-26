"""Small workspace preferences and resume metadata; never ROM bytes or paths."""
from contextlib import contextmanager
import math
import os
from pathlib import Path
import re
import threading
from .assets import checked_path
from .script_schema import load_script_json
from .workbench_projects import write_json

DEFAULT_SETTINGS={'theme':'romancer','scale':100,'autoDeepScan':True,'autoGraphics':True,
                  'rememberWorkspace':True,'volume':80,'startMuted':False,'loopPreview':False,
                  'reduceMotion':False,'advancedTools':False}
_PAGES={'overview','resources','scripts','assets','tables','levels','sound','playtest','release',
        'automation','help','settings','debug','routes','regression','tutorials'}
_LOCATION_FIELDS={'version','project_id','artifact_id','sha256','page','offset','selected','scroll',
                  'assetPage','scriptPage','catalogPage','catalogQuery'}
_locks={}
_guard=threading.Lock()
_MAX_REVISION=2**53-1


def validate_settings(values):
    if type(values) is not dict or set(values)!=set(DEFAULT_SETTINGS):raise ValueError('Settings contain missing or unknown fields')
    if type(values['theme']) is not str or values['theme'] not in ('romancer','dark','light'):raise ValueError('Choose a valid theme')
    if type(values['scale']) is not int or values['scale'] not in (100,125,150,200):raise ValueError('Choose a supported interface scale')
    if type(values['volume']) is not int or not 0<=values['volume']<=100:raise ValueError('Volume must be a whole number from 0 to 100')
    for key in DEFAULT_SETTINGS.keys()-{'theme','scale','volume'}:
        if type(values[key]) is not bool:raise ValueError(key+' must be true or false')
    return dict(values)


def _revision(value):
    if type(value) is not int or not 0<=value<=_MAX_REVISION:raise ValueError('Settings revision must be a nonnegative safe integer')
    return value


@contextmanager
def _locked(workspace):
    workspace=checked_path(Path(workspace));workspace.mkdir(parents=True,exist_ok=True)
    with _guard:lock=_locks.setdefault(os.path.normcase(str(workspace)),threading.RLock())
    with lock:
        path=checked_path(workspace/'settings.lock')
        with path.open('a+b') as stream:
            # OS locks also serialize separate local server processes sharing a workspace.
            if os.name=='nt':
                import msvcrt
                if os.fstat(stream.fileno()).st_size==0:stream.write(b'0');stream.flush()
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
                try:yield workspace
                finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
                try:yield workspace
                finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def _read_settings(workspace):
    path=checked_path(workspace/'settings.json')
    if not path.exists():return {'revision':0,'values':dict(DEFAULT_SETTINGS)}
    stored=load_script_json(path,max_bytes=4096)
    if set(stored)!={'schema_version','revision','values'} or type(stored['schema_version']) is not int or stored['schema_version']!=1:raise ValueError('Stored settings format is invalid')
    return {'revision':_revision(stored['revision']),'values':validate_settings(stored['values'])}


def get_settings(workspace):
    with _locked(workspace) as root:return {'ok':True,**_read_settings(root)}


def save_settings(workspace,revision,values):
    revision=_revision(revision);values=validate_settings(values)
    with _locked(workspace) as root:
        current=_read_settings(root)
        if current['revision']!=revision:raise ValueError('Settings changed in another window. Reopen Settings before applying changes.')
        if revision==_MAX_REVISION:raise ValueError('Settings revision limit reached')
        stored={'schema_version':1,'revision':revision+1,'values':values}
        write_json(root/'settings.json',stored,max_bytes=4096)
        return {'ok':True,'revision':stored['revision'],'values':dict(values)}


def validate_location(value):
    if value is None:return None
    if type(value) is not dict or set(value)!=_LOCATION_FIELDS:raise ValueError('Workspace location contains missing or unknown metadata')
    if type(value['version']) is not int or value['version']!=1:raise ValueError('Unknown workspace location version')
    for key,size in (('project_id',32),('artifact_id',32),('sha256',64)):
        if type(value[key]) is not str or not re.fullmatch('[0-9a-f]{'+str(size)+'}',value[key]):raise ValueError('Invalid workspace '+key)
    if type(value['page']) is not str or value['page'] not in _PAGES:raise ValueError('Invalid workspace page')
    for key in ('offset','selected','assetPage','scriptPage','catalogPage'):
        maximum=64*1024**2 if key in ('offset','selected') else 100000
        if type(value[key]) is not int or not 0<=value[key]<=maximum:raise ValueError('Invalid workspace '+key)
    if type(value['scroll']) not in (int,float) or not math.isfinite(value['scroll']) or not 0<=value['scroll']<=1e7:raise ValueError('Invalid workspace scroll')
    if type(value['catalogQuery']) is not str or len(value['catalogQuery'])>256 or any(ord(char)<32 for char in value['catalogQuery']):raise ValueError('Invalid workspace catalog query')
    return dict(value)


def get_workspace_location(workspace):
    with _locked(workspace) as root:
        path=checked_path(root/'workspace-location.json')
        if not path.exists():return {'ok':True,'location':None}
        stored=load_script_json(path,max_bytes=8192)
        if set(stored)!={'schema_version','location'} or type(stored['schema_version']) is not int or stored['schema_version']!=1:raise ValueError('Stored workspace location format is invalid')
        return {'ok':True,'location':validate_location(stored['location'])}


def save_workspace_location(workspace,location):
    location=validate_location(location)
    with _locked(workspace) as root:write_json(root/'workspace-location.json',{'schema_version':1,'location':location},max_bytes=8192)
    return {'ok':True}
