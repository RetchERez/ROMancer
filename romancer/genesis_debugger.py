"""Pinned headless Genesis bus observations and separately ordered instructions."""
import hashlib
import math
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import time
import uuid
from .asset_schema import number
from .assets import checked_path
from .debugger_protocol import validate_capture
from .workbench_projects import _measure

VERSION='0.289'
COMMIT='f34f02505e32c1993c6a782b6814232cbfc74e36'
UPSTREAM='https://github.com/mamedev/mame'
MEMBERS={'mame.exe':(316431360,'af6966108d9b52c22465c6d50f4e5d50cc371b50f2d27dc443935f287aad37a3')}


def backend_root():return Path(__file__).resolve().parents[2]/'debuggers'/'mame-0.289'


def verify_backend(root):
    for name,(size,digest) in MEMBERS.items():
        path=checked_path(Path(root)/name)
        if not path.is_file() or path.stat().st_size!=size or path.stat().st_nlink!=1:raise ValueError('Pinned Genesis debugger is missing or changed: '+name)
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=digest:raise ValueError('Pinned Genesis debugger hash differs: '+name)
    return {'backend':'MAME','version':VERSION,'source_commit':COMMIT,'executable_sha256':MEMBERS['mame.exe'][1],
        'license':'GPL-2.0-or-later','upstream':UPSTREAM}


def backend_capabilities():
    return {'ok':True,'system_id':'genesis','backend':'MAME','version':VERSION,'supported_system':True,
        'host_supported':os.name=='nt' and platform.machine().lower() in ('amd64','x86_64'),
        'instruction_events':True,'memory_access_events':True,'observed_mapping':False,'continuous_live_control':False,
        'access_width_available':False,'bus_lane_masks_available':True,'dma_actor_available':False,
        'transport':'bounded headless cold-start capture','instruction_sample_limit':2000,
        'controller':'3-button pad','upstream':UPSTREAM,
        'host_requirement':'Windows 10 or later, x86-64-v2 CPU; executable compatibility is confirmed only by a completed capture.'}


def make_script(config,nonce):
    v=validate_capture('genesis',config)
    if type(nonce) is not str or re.fullmatch('[a-zA-Z0-9_-]{1,64}',nonce) is None:raise ValueError('invalid native capture nonce')
    steps=['{frames='+str(s['frames'])+',buttons={'+','.join(b+'=true' for b in s['buttons'])+'}}' for s in v['steps']]
    probes=['{kind="'+p['kind']+'",start='+str(p['start'])+',finish='+str(p['end'])+',domain="'+p.get('domain','cpu')+'"}' for p in v['probes']]
    replacements={'STEPS':'{'+','.join(steps)+'}','PROBES':'{'+','.join(probes)+'}','NONCE':nonce,
        'FRAMES':str(v['frames']),'START_FRAME':str(v['start_frame']),'EVENT_LIMIT':str(v['event_limit']),
        'TRACE_LIMIT':str(min(v['instruction_limit'],2000))}
    script=Path(__file__).with_name('genesis_capture.lua').read_text(encoding='utf-8')
    for key,value in replacements.items():script=script.replace('@'+key+'@',value)
    if re.search('@[A-Z_]+@',script):raise ValueError('Genesis observer template is incomplete')
    return script


def arguments(job,frames,timeout):
    return ['genesis','-cart','input.md','-noreadconfig','-video','none','-sound','none','-nothrottle',
        '-debug','-debugger','none','-skip_gameinfo','-noconsole','-autoboot_delay','0','-autoboot_script','capture.lua',
        '-seconds_to_run',str(math.ceil(frames/50)+2),'-watchdog',str(timeout),'-noplugins',
        '-nvram_directory',str(job/'nvram'),'-cfg_directory',str(job/'cfg'),'-state_directory',str(job/'states'),
        '-snapshot_directory',str(job/'snapshots'),'-diff_directory',str(job/'diff')]


def parse_capture(text,instructions,nonce,raw,config):
    v=validate_capture('genesis',config)
    if type(text) is not str or type(instructions) is not str or max(len(text.encode()),len(instructions.encode()))>2*1024**2:raise ValueError('Genesis capture exceeds its output budget')
    lines=text.splitlines()
    if not lines or lines[0]!='BEGIN\t1\t'+nonce+'\tgenesis':raise ValueError('Genesis capture identity differs')
    events=[];end=None;windows={}
    def integer(text,low,high):
        if re.fullmatch('[0-9]{1,16}',text) is None:raise ValueError('invalid native integer')
        return number(int(text),low,high)
    for line in lines[1:]:
        if end is not None:raise ValueError('unexpected data after native end record')
        p=line.split('\t')
        if p[0]=='E' and len(p)==11:
            ident=integer(p[1],1,v['event_limit']);kind=p[2]
            if ident!=len(events)+1 or kind not in ('read','write'):raise ValueError('Genesis event order or kind differs')
            address=integer(p[3],0,0xffffff);value=integer(p[4],0,255);pc=integer(p[5],0,0xffffff)
            frame=integer(p[6],v['start_frame'],v['frames']-1);base=integer(p[7],0,0xfffffe)
            data=integer(p[8],0,65535);mask=integer(p[9],0,65535);lane=address-base
            if base%2 or lane not in (0,1) or mask not in (255,65280,65535):raise ValueError('invalid Genesis bus lane')
            shift=8 if lane==0 else 0
            if not mask&(255<<shift) or value!=((data>>shift)&255):raise ValueError('Genesis bus data differs from its byte lane')
            physical=address&65535 if address>=0xe00000 else None
            if not any(probe['kind']==kind and ((probe.get('domain','cpu')=='cpu' and probe['start']<=address<=probe['end']) or
                probe.get('domain')=='genesisWorkRam' and physical is not None and probe['start']<=physical<=probe['end']) for probe in v['probes']):raise ValueError('Genesis event probe scope differs')
            window=p[10];candidate=None;association='UNRESOLVED'
            if window!='-':
                if re.fullmatch('[0-9a-f]{32}',window) is None:raise ValueError('invalid mapped program window')
                if window not in windows:
                    pattern=bytes.fromhex(window);first=raw.find(pattern);second=raw.find(pattern,first+1) if first>=0 else -1
                    windows[window]=(first if first>=0 and second<0 else None,'UNIQUE_PATTERN_MATCH_CANDIDATE' if first>=0 and second<0 else 'AMBIGUOUS_PATTERN_MATCH' if second>=0 else 'NO_PATTERN_MATCH')
                candidate,association=windows[window]
            events.append({'id':ident,'kind':kind,'address':address,'value':value,'frame':frame,'bus_width':16,
                'raw_bus_address':base,'raw_data':data,'raw_mask':mask,'physical_offset':physical,
                'domain':'genesisWorkRam' if physical is not None else 'cpu','file_offset':None,
                'execution_context':{'pc':pc,'file_offset':None,'source_candidate_offset':candidate,'source_association':association,
                    'mapped_program_window_at_callback':None if window=='-' else window,'mapping_observed_at':'access_callback'},
                'registers':{},'access_width':None,'actor':None,'causation_proven':False})
        elif p[0]=='R' and len(p)==4:
            ident=integer(p[1],1,len(events));name=p[2]
            if ident!=len(events) or ident>16 or name not in ('CURPC','PC','SR',*[f'D{i}' for i in range(8)],*[f'A{i}' for i in range(8)]) or name in events[-1]['registers']:raise ValueError('invalid native register')
            events[-1]['registers'][name]=integer(p[3],0,2**32-1)
        elif p[0]=='END' and len(p)==4:
            frame=integer(p[1],v['frames'],v['frames']);emitted=integer(p[2],0,v['event_limit']);omitted=integer(p[3],0,2**53-1)
            if emitted!=len(events):raise ValueError('Genesis native event count differs')
            end={'frames_observed':frame,'route_complete':True,'omitted_events':omitted}
        else:raise ValueError('unknown Genesis native record')
    if end is None:raise ValueError('Genesis capture did not produce its end record')
    samples=[];pending=None;limit=min(v['instruction_limit'],2000)
    for line in instructions.splitlines():
        if not line.strip():continue
        marker=re.fullmatch(r'EXEC n=([0-9]+) curpc=([0-9A-Fa-f]{6,8}) pc=([0-9A-Fa-f]{6,8})',line)
        assembly=re.fullmatch(r'([0-9A-Fa-f]{6,8}): (.{1,1000})',line)
        if marker and pending is None:
            ident,pc,prefetched=int(marker[1]),int(marker[2],16),int(marker[3],16)
            if ident!=len(samples)+1 or ident>limit or max(pc,prefetched)>0xffffff:raise ValueError('native instruction sample order or budget differs')
            pending={'id':ident,'pc':pc,'prefetched_pc':prefetched,'file_offset':None}
        elif assembly and pending is not None and int(assembly[1],16)==pending['pc']:
            samples.append({**pending,'assembly':assembly[2]});pending=None
        else:raise ValueError('malformed native instruction output')
    if pending is not None:raise ValueError('incomplete native instruction output')
    limited=len(samples)>=limit
    return {'ok':True,'system_id':'genesis','status':'BUDGET_EXCEEDED' if end['omitted_events'] or limited else 'CAPTURED',
        'events':events,'instruction_samples':samples,'instruction_sample_limit':limit,'instruction_samples_truncated':limited,
        'native_callbacks_observed':bool(events or samples),'merged_instruction_access_order_known':False,
        'observer_reads_filtered':True,'write_authorized':False,'memory_written':False,**end,
        'runtime_scope':'side-effects-enabled main CPU program-bus callbacks; opcode prefetch may be included',
        'limitations':['Instruction and access sequences have separate ordering; no invented merged timeline.',
            'Source pattern matches are candidates, not mapper observations. Bank timing, decrypted opcode spaces and DMA ownership remain unresolved.',
            'Native instruction sampling stops after at most 2000 records. Remaining replay work is bounded by frames and wall-clock time, not an observed total instruction count.',
            'Controller input uses a three-button pad. Frame notifier input may take effect on the following frame.']}


def capture_genesis(project,row,config,*,root=None,cancelled=lambda:False):
    v=validate_capture('genesis',config)
    if not backend_capabilities()['host_supported']:raise ValueError('This pinned Genesis debugger requires Windows x64.')
    root=checked_path(Path(root) if root is not None else backend_root());backend=verify_backend(root)
    source=checked_path(Path(row['path']));_measure(source,row,cancelled=cancelled)
    if row['size']>64*1024**2:raise ValueError('native source exceeds 64 MiB')
    parent=checked_path(Path(project)/'sessions'/'native-debugger');parent.mkdir(parents=True,exist_ok=True)
    job=parent/uuid.uuid4().hex;job.mkdir();process=None
    try:
        shutil.copyfile(root/'mame.exe',job/'mame.exe');verify_backend(job)
        shutil.copyfile(source,job/'input.md');_measure(job/'input.md',row,cancelled=cancelled)
        nonce=secrets.token_hex(16);script=make_script(config,nonce);(job/'capture.lua').write_text(script,encoding='utf-8',newline='\n')
        if cancelled():raise KeyboardInterrupt
        with (job/'stdout.txt').open('wb') as stdout,(job/'stderr.txt').open('wb') as stderr:
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
            process=subprocess.Popen([str(job/'mame.exe'),*arguments(job,v['frames'],v['timeout'])],cwd=job,
                stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW,startupinfo=startup)
            deadline=time.monotonic()+v['timeout']+3
            while process.poll() is None:
                if cancelled():raise KeyboardInterrupt
                if time.monotonic()>deadline:raise ValueError('Genesis debugger exceeded its wall-clock budget')
                if any(p.stat().st_size>2*1024**2 for p in (job/'trace.tsv',job/'instructions.log',job/'stdout.txt',job/'stderr.txt') if p.exists()):raise ValueError('Genesis debugger exceeded its output budget')
                time.sleep(.025)
        if process.returncode!=0:raise ValueError('Genesis debugger did not complete (exit '+str(process.returncode)+'). Check host CPU compatibility.')
        def read(name,optional=False):
            path=checked_path(job/name)
            if optional and not path.exists():return ''
            if not path.is_file() or path.stat().st_size>2*1024**2 or path.stat().st_nlink!=1:raise ValueError('Genesis output is missing or invalid')
            return path.read_text(encoding='utf-8')
        result=parse_capture(read('trace.tsv'),read('instructions.log',True),nonce,(job/'input.md').read_bytes(),config)
        _measure(job/'input.md',row,cancelled=cancelled);_measure(source,row,cancelled=cancelled);verify_backend(root)
        return {**result,'backend':backend,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],
            'adapter_sha256':hashlib.sha256(script.encode()).hexdigest(),'request':config,'worker_exit_code':process.returncode,'original_unchanged':True}
    finally:
        if process is not None and process.poll() is None:process.kill();process.wait(timeout=5)
        if job.resolve().parent!=parent.resolve() or re.fullmatch('[0-9a-f]{32}',job.name) is None:raise ValueError('Genesis cleanup target escaped owned sessions')
        shutil.rmtree(job)
