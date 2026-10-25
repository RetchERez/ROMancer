from __future__ import annotations
from pathlib import Path
from typing import Any
import json, time

def _db(project:str)->Path:
    p=Path(project)/'knowledge.json'; p.parent.mkdir(parents=True,exist_ok=True); return p

def _load(project:str)->dict[str,Any]:
    p=_db(project)
    if p.exists(): return json.loads(p.read_text(encoding='utf-8'))
    return {'symbols':[],'findings':[],'routines':[]}

def _save(project:str,obj): _db(project).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def symbol_cmd(project, action, name=None, addr=None, offset=None, kind='unknown', system='unknown', status='candidate', notes=''):
    db=_load(project)
    if action=='add':
        db['symbols'].append({'name':name,'address':addr,'offset':offset,'kind':kind,'system':system,'status':status,'notes':notes,'added':time.time()}); _save(project,db)
    if action=='list': return {'symbols':db.get('symbols',[])}
    if action=='export': return '\n'.join(f"{s.get('name')} = {s.get('address') or s.get('offset')}" for s in db.get('symbols',[]))+'\n'
    return {'symbols':db.get('symbols',[])}

def finding_cmd(project, action, claim=None, status='candidate', evidence=None, confidence=0.5, notes=''):
    db=_load(project)
    if action=='add':
        db['findings'].append({'claim':claim,'status':status,'evidence':evidence,'confidence':confidence,'notes':notes,'added':time.time()}); _save(project,db)
    if action=='audit':
        issues=[]
        for f in db.get('findings',[]):
            if f.get('status')=='confirmed' and not f.get('evidence'): issues.append({'claim':f.get('claim'),'issue':'confirmed finding lacks evidence reference'})
        return {'issues':issues,'finding_count':len(db.get('findings',[]))}
    return {'findings':db.get('findings',[])}

def routine_cmd(project, action, pc=None, name=None, status='candidate', notes=''):
    db=_load(project)
    if action=='add':
        db['routines'].append({'pc':pc,'name':name,'status':status,'notes':notes,'added':time.time()}); _save(project,db)
    return {'routines':db.get('routines',[])}

def ai_prompt(project:str, goal:str, out:str|None=None)->str:
    db=_load(project)
    lines=['ROMancer AI Debug Prompt','',f'Goal: {goal}','', 'Project knowledge summary:',f"Symbols: {len(db.get('symbols',[]))}",f"Findings: {len(db.get('findings',[]))}",f"Routines: {len(db.get('routines',[]))}",'', 'Rules:','- Treat confirmed claims as usable only when evidence is attached.','- Do not invent offsets or mappings.','- Prefer debugger-first validation and minimal IPS patches.','', 'Symbols:']
    for s in db.get('symbols',[])[:80]: lines.append(f"- {s.get('name')}: {s.get('address') or s.get('offset')} [{s.get('status')}] {s.get('notes','')}")
    lines.append('Findings:')
    for f in db.get('findings',[])[:80]: lines.append(f"- {f.get('claim')} [{f.get('status')}] evidence={f.get('evidence')}")
    text='\n'.join(lines)+'\n'
    if out: Path(out).parent.mkdir(parents=True,exist_ok=True); Path(out).write_text(text,encoding='utf-8')
    return text
