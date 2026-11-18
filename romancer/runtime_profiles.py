"""Per-system local runtime inputs. Configuration validation is not emulation proof."""
import json
import os
from pathlib import Path


import struct
from .assets import checked_path,digest
from .asset_schema import fields
from .script_schema import canonical_bytes,load_script_json
from .system_registry import SYSTEM_IDS
from .workbench_projects import _measure,write_json
from .libretro_frontend import BUTTON_IDS


def _binary(path):
    path=checked_path(path);measure=_measure(path)
    if measure['size']>256*1024**2 or struct.calcsize('P')!=8:raise ValueError('a matching64-bit native core is required')
    with path.open('rb') as stream:
        header=stream.read(64)
        if os.name=='nt':
            if header[:2]!=b'MZ' or len(header)<64:raise ValueError('choose a Windows x64 libretro DLL')
            offset=int.from_bytes(header[60:64],'little')
            if not 64<=offset<=measure['size']-6:raise ValueError('invalid PE header')
            stream.seek(offset);pe=stream.read(6)
            if pe[:4]!=b'PE\0\0' or pe[4:6]!=b'\x64\x86':raise ValueError('core architecture differs from Windows x64 runtime')
            binary='pe-amd64'
        else:
            if header[:6]!=b'\x7fELF\x02\x01' or header[18:20]!=b'\x3e\x00':raise ValueError('choose a Linux x86_64 libretro library')
            binary='elf-amd64'
    return {**measure,'binary':binary}


def measure_system_files(directory):
    if directory is None:return []
    directory=checked_path(directory)
    if not directory.is_dir():raise ValueError('system-file folder is missing')
    result=[];total=0;names=set()
    for path in sorted(directory.rglob('*')):
        checked_path(path)
        if path.is_dir():continue
        relative=path.relative_to(directory).as_posix()
        if relative.casefold() in names:raise ValueError('duplicate system-file name')
        names.add(relative.casefold());measure=_measure(path);total+=measure['size']
        if len(result)>=256 or total>256*1024**2:raise ValueError('choose a dedicated per-system BIOS folder within 256 MiB/256 files')
        result.append({'source':str(path),'relative':relative,'expected_sha256':measure['sha256'],'size':measure['size']})
    return result


def _options(options,input_map):
    canonical_bytes(options,max_bytes=128*1024)
    if type(options) is not dict or len(options)>128 or any(type(k) is not str or type(v) is not str or not k or len(k)>256 or len(v)>1024 or '\0' in k+v for k,v in options.items()):raise ValueError('core options require bounded names and values')
    if type(input_map) is not dict or len(input_map)>16 or any(k not in BUTTON_IDS or type(v) is not str or not v or len(v)>40 for k,v in input_map.items()):raise ValueError('invalid controller mapping')
    if len(set(input_map.values()))!=len(input_map):raise ValueError('controller keys must be unique')


def save_profile(workspace,system_id,core,options,system_dir,input_map,*,controller_devices=None):
    if system_id not in SYSTEM_IDS:raise ValueError('unknown system')
    _options(options,input_map);core=checked_path(core);binary=_binary(core)
    system_dir=str(checked_path(system_dir)) if system_dir else None;files=measure_system_files(system_dir)
    workspace=checked_path(workspace);path=workspace/'runtime-profiles.json'
    registry=load_script_json(path,max_bytes=1024**2) if path.exists() else {'schema_version':1,'profiles':{}}
    if controller_devices is None:
        previous=registry['profiles'].get(system_id,{})
        if previous.get('core_identity')==binary:controller_devices=previous.get('controller_devices',{})
    profile={'schema_version':1,'system_id':system_id,'core':str(core),'core_identity':binary,'options':json.loads(canonical_bytes(options,max_bytes=128*1024)),'system_dir':system_dir,'system_files':files,'input_map':dict(input_map)}
    if controller_devices is not None:
        from .controller_devices import validate_devices
        selected=validate_devices(controller_devices)
        if selected:profile['controller_devices']=selected
    profile['identity']=_identity(profile)
    workspace.mkdir(parents=True,exist_ok=True)
    registry['profiles'][system_id]=profile;write_json(path,registry,max_bytes=1024**2)
    return {'ok':True,'status':'CONFIGURED','profile':profile,'runtime_verified':False}


def _identity(profile):
    value={'system_id':profile['system_id'],'core':profile['core_identity'],'options':profile['options'],
           'system_files':[{k:f[k] for k in ('relative','expected_sha256','size')} for f in profile['system_files']],'input_map':profile['input_map']}
    if profile.get('controller_devices'):value['controller_devices']=profile['controller_devices']
    return digest(value)


def load_profile(workspace,system_id,*,source_sha256=None):
    if system_id not in SYSTEM_IDS:raise ValueError('unknown system')
    path=checked_path(Path(workspace)/'runtime-profiles.json')
    value=load_script_json(path,max_bytes=1024**2) if path.exists() else {'schema_version':1,'profiles':{}}
    if value.get('schema_version')!=1:raise ValueError('unsupported runtime profile version')
    if system_id not in value['profiles']:
        from .bundled_cores import bundled_profile
        default=bundled_profile(system_id,source_sha256=source_sha256)
        if default:return default
    saved=value['profiles'].get(system_id)
    if saved and source_sha256 and not saved.get('system_dir'):
        from .bundled_cores import CORE_PINS,bundled_profile,cartridge_engine
        default_engine,_=cartridge_engine(system_id)
        _,compatibility=cartridge_engine(system_id,source_sha256)
        if compatibility and saved['core_identity']['sha256']==CORE_PINS[default_engine]['sha256']:
            validate_profile(saved)
            selected=bundled_profile(system_id,source_sha256=source_sha256)
            if selected:
                profile=selected['profile']
                if profile['core_identity']['sha256']==saved['core_identity']['sha256']:
                    profile['options']={**profile['options'],**saved['options'],**compatibility}
                profile['input_map']=saved['input_map']
                if saved.get('controller_devices'):
                    profile['controller_devices']=saved['controller_devices']
                profile['identity']=_identity(profile)
                return selected
    return {'ok':True,'status':'CONFIGURED' if saved else 'NOT_CONFIGURED','profile':saved,'runtime_verified':False}


def validate_profile(profile):
    fields({k:v for k,v in profile.items() if k!='controller_devices'},'schema_version system_id core core_identity options system_dir system_files input_map identity')
    from .controller_devices import validate_devices
    devices=validate_devices(profile.get('controller_devices',{}))
    if type(profile['schema_version']) is not int or profile['schema_version']!=1 or profile['system_id'] not in SYSTEM_IDS or profile['identity']!=_identity(profile):raise ValueError('runtime profile identity/schema changed')
    _options(profile['options'],profile['input_map'])
    if _binary(profile['core'])!=profile['core_identity']:raise ValueError('core changed; choose and save its new revision')
    from .bundled_cores import require_reviewed_release_core
    require_reviewed_release_core(profile['core'])
    actual=measure_system_files(profile['system_dir'])
    if actual!=profile['system_files']:raise ValueError('system files changed; review and save the new configuration')
    return {'ok':True,'status':'INPUTS_VERIFIED','profile_identity':profile['identity'],'core':profile['core'],'core_options':profile['options'],'expected_core_sha256':profile['core_identity']['sha256'],
            'system_dir':profile['system_dir'],'system_files':[{k:f[k] for k in ('source','relative','expected_sha256')} for f in actual],'input_map':profile['input_map'],'controller_devices':devices,'runtime_verified':False}
