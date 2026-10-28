"""Pinned, isolated, genuinely headless MesenCE capture; no mock bridge claims."""
import hashlib
import ctypes
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import time
import uuid
from .assets import checked_path
from .workbench_projects import _measure
from .debugger_protocol import validate_capture,parse_capture,LIMITS,BUTTONS

VERSION='2.2.1'
SOURCE_COMMIT='20ba206cef5ba207c21203176d02cb9f43dda9fb'
UPSTREAM='https://github.com/nesdev-org/MesenCE'
ARCHIVE_URL=UPSTREAM+'/releases/download/2.2.1/Mesen_2.2.1_Windows.zip'
ARCHIVE_SHA256='c19e10b3b3865eb0e86e4d01bf09a5027a4452081c04b5bd5b6cbbf76e346fd6'
MEMBERS={
 'Mesen.exe':(70753792,'8ef403d6b9af32075416193914d7993ce8480b347fe1f20a0cfd9815374933e7'),
 'MesenCore.dll':(7224320,'55a5f918c8ead04d4a401fc12f0ce9e4de69bebbc484f1ca3a7c018916b1fad1'),
 'libHarfBuzzSharp.dll':(1804872,'eb76238c9e8e41d44b5a5b18167c4c5b39ca5db4277af5dbe92d730f0fc14a7d'),
 'libSkiaSharp.dll':(9414216,'9a0d95e8caaa852c70d085af6a40a744242172ad9ea3fd6bc7599875a8a1dbcd'),
 'MesenNesDB.txt':(559276,'200e19903f1b2eeda1f59a7f3bcdacf388d0f8d228f6f842373477ddc2f5a3e1')}
GRAPHICS_CORE=(7239680,'62e4c8a1b152e8d94adeb54335e1b0966c38c1f26db2ae4007b1a5e558077445')
CPU={'nes':('nes','nesMemory'),'snes':('snes','snesMemory'),'gb':('gameboy','gameboyMemory'),
 'gbc':('gameboy','gameboyMemory'),'gba':('gba','gbaMemory'),'sms':('sms','smsMemory')}


def remove_owned_job(job,parent):
    job=Path(job);parent=Path(parent)
    if job.resolve().parent!=parent.resolve() or not re.fullmatch('[0-9a-f]{32}',job.name):raise ValueError('Native cleanup target escaped its owned sessions.')
    for delay in (0,.05,.1,.2,.4,.8):
        if delay:time.sleep(delay)
        try:shutil.rmtree(job);return
        except FileNotFoundError:return
        except PermissionError:
            if delay==.8:raise


def backend_root(system=None):
    if system=='genesis':
        from .genesis_debugger import backend_root as genesis_root
        return genesis_root()
    return Path(__file__).resolve().parents[2]/'debuggers'/'mesence-2.2.1'


def verify_backend(root,system=None):
    from .bundled_debuggers import verify_installed
    verify_installed(root)
    if system=='genesis':
        from .genesis_debugger import verify_backend as genesis_verify
        return genesis_verify(root)
    root=checked_path(Path(root))
    patched=False
    for name,(size,digest) in MEMBERS.items():
        path=checked_path(root/name)
        if name=='MesenCore.dll' and path.is_file() and path.stat().st_size==GRAPHICS_CORE[0]:
            size,digest=GRAPHICS_CORE;patched=True
        if not path.is_file() or path.stat().st_size!=size or path.stat().st_nlink!=1:
            raise ValueError('Pinned native debugger is missing or changed: '+name)
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=digest:raise ValueError('Pinned native debugger hash differs: '+name)
    result={'backend':'MesenCE','version':VERSION,'source_commit':SOURCE_COMMIT,
        'executable_sha256':MEMBERS['Mesen.exe'][1],'core_sha256':GRAPHICS_CORE[1] if patched else MEMBERS['MesenCore.dll'][1],
        'license':'GPL-3.0-or-later','upstream':UPSTREAM}
    if patched:result.update(romancer_patch='physical-ppu-access-v2',physical_ppu_callbacks=True,native_access_details=True)
    return result


def backend_capabilities(system):
    if system=='genesis':
        from .genesis_debugger import backend_capabilities as genesis_capabilities
        return genesis_capabilities()
    supported=system in CPU;host=os.name=='nt' and platform.machine().lower() in ('amd64','x86_64')
    return {'ok':True,'system_id':system,'backend':'MesenCE','version':VERSION,
        'supported_system':supported,'host_supported':host,'instruction_events':supported,
        'execution_range_probes':supported,'memory_access_events':supported,'observed_mapping':supported,
        'transport':'bounded headless cold-start capture','continuous_live_control':False,'focused_access_stop':supported,
        'access_width_available':False,'dma_actor_available':False,'upstream':UPSTREAM}


def portable_settings(system):
    return {'Version':VERSION,'Debug':{'ScriptWindow':{'AllowIoOsAccess':True,'AllowNetworkAccess':False,'ScriptTimeout':5}},
        'Gameboy':{'Model':5 if system=='gbc' else 4,'Controller':{'Type':40}},
        'Gba':{'SkipBootScreen':True,'Controller':{'Type':48}},
        'Nes':{'Port1':{'Type':9}},'Snes':{'Port1':{'Type':1}}}


def make_script(system,config,nonce):
    v=validate_capture(system,config)
    if type(nonce) is not str or re.fullmatch('[a-zA-Z0-9_-]{1,64}',nonce) is None:raise ValueError('invalid native capture nonce')
    steps=[]
    for step in v['steps']:
        buttons=','.join(b+'='+('true' if b in step['buttons'] else 'false') for b in sorted(BUTTONS[system]))
        steps.append('{frames='+str(step['frames'])+',buttons={'+buttons+'}}')
    probes=['{kind="'+p['kind']+'",start='+str(p['start'])+',finish='+str(p['end'])+
        (',domain="'+p['domain']+'"' if p.get('domain','cpu')!='cpu' else '')+'}' for p in v['probes']]
    replacements={'CPU':CPU[system][0],'MEMORY':CPU[system][1],'STEPS':'{'+','.join(steps)+'}',
        'PROBES':'{'+','.join(probes)+'}','NONCE':nonce,'SYSTEM':system,'FRAMES':str(v['frames']),'START_FRAME':str(v['start_frame']),
        'EVENT_LIMIT':str(v['event_limit']),'INSTRUCTION_LIMIT':str(v['instruction_limit']),'MAX_ADDRESS':str(LIMITS[system]),'GRAPHICS_SNAPSHOT':'true' if v.get('graphics_snapshot') else 'false'}
    from .graphics_snapshot import SNAPSHOT_DOMAINS
    replacements['STOP_AT']=str(v.get('stop',{}).get('occurrence',0))
    replacements['SNAPSHOT_DOMAINS']='{'+','.join('{name="'+name+'",size='+str(size)+'}' for name,size in SNAPSHOT_DOMAINS[system].items())+'}'
    script=(Path(__file__).with_name('debugger_capture.lua')).read_text(encoding='utf-8')
    for key,value in replacements.items():script=script.replace('@'+key+'@',value)
    if re.search('@[A-Z_]+@',script):raise ValueError('native adapter template is incomplete')
    return script


def capture_native(project,row,config,*,root=None,cancelled=lambda:False):
    if row.get('system_id')=='genesis':
        from .genesis_debugger import capture_genesis
        return capture_genesis(project,row,config,root=root,cancelled=cancelled)
    system=row.get('system_id');v=validate_capture(system,config)
    if not backend_capabilities(system)['host_supported']:raise ValueError('this pinned native debugger build requires Windows x64')
    root=checked_path(Path(root) if root is not None else backend_root());backend=verify_backend(root)
    source=checked_path(Path(row['path']));_measure(source,row,cancelled=cancelled)
    if row['size']>64*1024**2:raise ValueError('native debugger source exceeds 64 MiB')
    parent=checked_path(Path(project)/'sessions'/'native-debugger');parent.mkdir(parents=True,exist_ok=True)
    job=parent/uuid.uuid4().hex;job.mkdir();assert job.resolve().parent==parent.resolve()
    process=None;core_lock=None
    try:
        for name in MEMBERS:
            if cancelled():raise KeyboardInterrupt
            shutil.copyfile(root/name,job/name)
        verify_backend(job)
        if backend.get('physical_ppu_callbacks'):
            # The upstream self-contained launcher extracts its own embedded DLL.
            # Keep our reviewed snapshot readable but deny replacement for the
            # entire child lifetime; the launcher tolerates existing locked DLLs.
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
            kernel.CreateFileW.restype=ctypes.c_void_p;kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle.restype=ctypes.c_int
            core_lock=kernel.CreateFileW(str(job/'MesenCore.dll'),0x80000000,1,None,3,0x80,None)
            if core_lock in (None,ctypes.c_void_p(-1).value):core_lock=None;raise OSError('Could not hold the verified graphics observer core snapshot.')
        settings=portable_settings(system);(job/'settings.json').write_text(json.dumps(settings),encoding='utf-8')
        nonce=secrets.token_hex(16);script=make_script(system,config,nonce)
        (job/'capture.lua').write_text(script,encoding='utf-8',newline='\n')
        suffix={'nes':'.nes','snes':'.sfc','gb':'.gb','gbc':'.gbc','gba':'.gba','sms':'.sms'}[system]
        game=job/('input'+suffix);shutil.copyfile(source,game)
        _measure(game,row,cancelled=cancelled)
        if not (job/'settings.json').is_file():raise ValueError('isolated portable settings must exist before launching')
        with (job/'stdout.txt').open('wb') as stdout,(job/'stderr.txt').open('wb') as stderr:
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
            process=subprocess.Popen([str(job/'Mesen.exe'),'--testrunner','--timeout='+str(v['timeout']),
                'capture.lua',game.name],cwd=job,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW,startupinfo=startup)
            deadline=time.monotonic()+v['timeout']+3
            while process.poll() is None:
                if cancelled():raise KeyboardInterrupt
                if time.monotonic()>deadline:raise ValueError('native debugger exceeded its wall-clock budget')
                if any(p.stat().st_size>2*1024**2 for p in (job/'trace.tsv',job/'stdout.txt',job/'stderr.txt') if p.exists()):
                    raise ValueError('native debugger output exceeded its byte budget')
                time.sleep(.025)
        if process.returncode!=0:
            from .debugger_failures import process_failure,capture_output
            raise process_failure('Native observer',process.returncode,capture_output(job))
        if verify_backend(job)!=backend:raise ValueError('The executed debugger core identity changed.')
        trace=checked_path(job/'trace.tsv')
        if not trace.is_file() or trace.stat().st_size>2*1024**2 or trace.stat().st_nlink!=1:raise ValueError('native capture output is missing or invalid')
        raw=game.read_bytes();_measure(game,row,cancelled=cancelled)
        result=parse_capture(trace.read_text(encoding='utf-8'),nonce,system,raw,config)
        _measure(source,row,cancelled=cancelled);verify_backend(root)
        return {**result,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'backend':backend,
            'configuration_sha256':hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest(),
            'adapter_sha256':hashlib.sha256(script.encode()).hexdigest(),'request':config,
            'firmware_scope':'No external firmware supplied. GBA BIOS-dependent behavior is not certified.',
            'worker_exit_code':process.returncode,'original_unchanged':True}
    finally:
        if process is not None and process.poll() is None:process.kill();process.wait(timeout=5)
        if core_lock is not None:kernel.CloseHandle(core_lock)
        # Only this freshly created direct child may be recursively removed.
        remove_owned_job(job,parent)
