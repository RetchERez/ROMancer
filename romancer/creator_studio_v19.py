
from __future__ import annotations
"""ROMancer v19 creator-facing semantic feature planning."""
import json, re
from pathlib import Path
from typing import Any
from .util import write_json

def _read(x: str)->str:
    p=Path(str(x))
    return p.read_text(encoding='utf-8') if p.exists() else str(x)

def feature_plan(request: str, out: str|None=None)->dict[str,Any]:
    text=_read(request); low=text.lower(); tasks=[]
    def add(name, req, risk='medium'):
        tasks.append({'task':name,'evidence_required':req,'risk':risk,'status':'planned'})
    add('Verify source ROM identity and project baseline','exact hash, region, platform','high')
    add('Create focused runtime scenario for the feature','reproducible state and success oracle','high')
    if any(w in low for w in ['command','skill','ability','spell','mockery']):
        add('Locate command table and dispatcher','verified table and dispatch trace','high')
        add('Define command semantics and edge cases','effect, target rules, stacking, immunity, failure cases','medium')
    if any(w in low for w in ['portrait','sprite','animation','graphics','laugh']):
        add('Trace graphics/animation/audio provenance','asset to renderer/VRAM/OAM/audio evidence','high')
    if any(w in low for w in ['shop','price','item','inventory']):
        add('Validate economy and inventory effects','currency, item quantity, equipment/use semantics','medium')
    if any(w in low for w in ['dialogue','npc','story','quest']):
        add('Compile objective/dialogue trigger model','speaker, text ID, event flags, route coverage','medium')
    add('Check platform constraints','name length, bank space, VRAM/palette, free space, save compatibility','high')
    add('Generate semantic patch plan','lowest-risk data/pointer/event/code change','high')
    add('Run focused feature tests','single case, edge cases, negative cases','high')
    add('Run full certification gates','static, runtime, proof, QA, regression','high')
    blocked=[t for t in tasks if 'verified' in t['evidence_required'] or t['risk']=='high']
    res={'tool':'ROMancer','version':'19.0.0','feature':'v19 feature plan','request':text,'task_count':len(tasks),'blocked_until_evidence_count':len(blocked),'tasks':tasks,'policy':'Creator requests are decomposed into evidence-scoped engineering tasks. ROMancer does not build unsupported features blindly.'}
    if out: write_json(out,res)
    return res

def constraint_check(manifest: str|dict[str,Any], out: str|None=None)->dict[str,Any]:
    if not isinstance(manifest,dict): manifest=json.loads(Path(manifest).read_text(encoding='utf-8'))
    warnings=[]; failures=[]
    name=manifest.get('command_name') or manifest.get('name')
    max_len=int(manifest.get('max_name_length', 999))
    if name and len(name)>max_len: failures.append({'constraint':'name_length','actual':len(name),'max':max_len})
    for key in ('free_space_bytes','required_space_bytes'):
        if key not in manifest: warnings.append({'constraint':key,'status':'unknown'})
    if manifest.get('free_space_bytes') is not None and manifest.get('required_space_bytes') is not None and int(manifest['free_space_bytes'])<int(manifest['required_space_bytes']):
        failures.append({'constraint':'free_space','free':manifest['free_space_bytes'],'required':manifest['required_space_bytes']})
    for r in manifest.get('required_verified_facts',[]):
        if str(r.get('status','UNKNOWN')).upper()!='VERIFIED': failures.append({'constraint':'verified_fact','id':r.get('id'),'status':r.get('status','UNKNOWN')})
    res={'tool':'ROMancer','version':'19.0.0','feature':'v19 design constraint check','ok':not failures,'failure_count':len(failures),'warning_count':len(warnings),'failures':failures,'warnings':warnings}
    if out: write_json(out,res)
    return res

def compile_feature_source(source: str, out: str|None=None)->dict[str,Any]:
    text=_read(source)
    fields={}
    for line in text.splitlines():
        m=re.match(r'\s*([A-Za-z_][\w-]*)\s*[:=]\s*(.+?)\s*$', line)
        if m: fields[m.group(1).replace('-','_')]=m.group(2).strip().strip('"')
    plan=feature_plan(text)
    constraints=constraint_check({'name':fields.get('name') or fields.get('command_name'),'command_name':fields.get('command_name'),'max_name_length':int(fields.get('max_name_length',999)) if str(fields.get('max_name_length','999')).isdigit() else 999,'free_space_bytes':int(fields['free_space_bytes']) if fields.get('free_space_bytes','').isdigit() else None,'required_space_bytes':int(fields['required_space_bytes']) if fields.get('required_space_bytes','').isdigit() else None,'required_verified_facts':[]})
    res={'tool':'ROMancer','version':'19.0.0','feature':'v19 semantic feature compile','parsed_fields':fields,'plan':plan,'constraints':constraints,'build_status':'PLAN_ONLY' if constraints['ok'] else 'BLOCKED','policy':'Semantic feature source compiles to a plan/proof request, not ROM bytes, until required evidence and constraints pass.'}
    if out: write_json(out,res)
    return res
