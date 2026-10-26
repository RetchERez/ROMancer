from __future__ import annotations
from pathlib import Path
from typing import Any
import json, shutil, subprocess

CONFIG=Path.home()/'.config'/'romancer'/'backends.json'

def _load():
    if CONFIG.exists(): return json.loads(CONFIG.read_text(encoding='utf-8'))
    return {}

def _save(obj):
    CONFIG.parent.mkdir(parents=True,exist_ok=True); CONFIG.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def backend_config(action:str, name:str|None=None, path:str|None=None)->dict[str,Any]:
    cfg=_load()
    if action=='init': _save(cfg); return {'config':str(CONFIG),'backends':cfg}
    if action=='set':
        if not name or not path: raise ValueError('set requires name and path')
        cfg[name]=path; _save(cfg)
    return {'config':str(CONFIG),'backends':cfg}

def backend_capabilities()->dict[str,Any]:
    cfg=_load(); names=['mesen','mesen2','bsnes-plus','blastem','fceux']
    caps={}
    for n in names:
        exe=cfg.get(n) or shutil.which(n)
        caps[n]={'configured_path':cfg.get(n),'detected_path':exe,'launch_helper':bool(exe),'trace_import':'yes','live_control':'no' if n!='blastem' else 'experimental','notes':'ROMancer imports evidence; it does not guarantee stable live debugger control.'}
    return {'tool':'ROMancer','feature':'v0.6 backend-capabilities','config':str(CONFIG),'backends':caps}

def launch(backend:str, rom:str, dry_run:bool=False, extra:list[str]|None=None)->dict[str,Any]:
    cfg=_load(); exe=cfg.get(backend) or shutil.which(backend)
    if not exe: return {'ok':False,'error':f'Backend not found: {backend}. Configure with backend-config set.', 'backend':backend}
    cmd=[exe, rom]+(extra or [])
    if dry_run: return {'ok':True,'dry_run':True,'cmd':cmd}
    p=subprocess.Popen(cmd)
    return {'ok':True,'backend':backend,'pid':p.pid,'cmd':cmd}

def session_template(system:str, backend:str, addr:str, access:str='write', goal:str='', out:str|None=None)->str:
    lines=['ROMancer Debug Session Template','',f'System: {system}',f'Backend: {backend}',f'Goal: {goal or "unspecified"}',f'Target: {addr}',f'Access: {access}','',
           'Before launching:','- Confirm ROM hash and header status with identify.','- Confirm mapping for SNES or mapper caveats for NES.','',
           'Debugger setup:',f'- Set {access} breakpoint on {addr}.','- Enable trace logging shortly before reproducing the behavior.','- Trigger the event.','- Save the trace under project/traces/.','',
           'After session:',f'- run.sh correlate-trace traces/session.log --addr {addr}',f'- run.sh trace-window traces/session.log --addr {addr} --before 100 --after 25','- run.sh patch-plan only after candidate evidence exists.']
    text='\n'.join(lines)+'\n'
    if out: Path(out).parent.mkdir(parents=True,exist_ok=True); Path(out).write_text(text,encoding='utf-8')
    return text

def watch_traces(folder:str, addr:str|None=None, once:bool=True)->dict[str,Any]:
    from .workflow import correlate_trace
    from .trace_parser import trace_summary
    p=Path(folder); p.mkdir(parents=True,exist_ok=True)
    processed=[]
    for f in sorted(p.glob('*.log')):
        item={'file':str(f),'summary':trace_summary(str(f))}
        if addr: item['correlation']=correlate_trace(str(f),addr)
        out=f.with_suffix('.romancer.json'); out.write_text(json.dumps(item,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        processed.append(str(out))
    return {'tool':'ROMancer','feature':'v0.6 watch-traces','folder':folder,'processed':processed,'mode':'single-pass' if once else 'single-pass-for-safety'}
