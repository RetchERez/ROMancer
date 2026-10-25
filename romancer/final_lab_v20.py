
from __future__ import annotations
"""ROMancer v20 final autonomous ROM laboratory orchestration."""
import json, hashlib
from pathlib import Path
from typing import Any
from .util import write_json
from .creator_studio_v19 import feature_plan
from .proof_v17 import evaluate_invariants

FORBIDDEN_SUFFIXES={'.sfc','.smc','.nes','.gba','.gb','.gbc','.gen','.bin','.iso','.chd','.cue','.srm','.sav','.state','.rom'}

def _load(x: str|dict[str,Any])->dict[str,Any]:
    if isinstance(x,dict): return x
    return json.loads(Path(x).read_text(encoding='utf-8'))

def _sha_obj(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def lab_lifecycle(manifest: str|dict[str,Any], out: str|None=None)->dict[str,Any]:
    m=_load(manifest)
    stages=['identify','research','plan_feature','build','playtest','diagnose','repair','prove','certify','package','publish_report']
    rows=[]; blocked=False
    evidence=set(m.get('evidence',[]))
    for st in stages:
        required={
            'identify':['source_hash'],
            'research':['baseline_profile'],
            'plan_feature':['feature_request'],
            'build':['patch_plan'],
            'playtest':['runtime_scenario'],
            'diagnose':['failure_oracle'],
            'repair':['repair_bounds'],
            'prove':['proof_manifest'],
            'certify':['certification_manifest'],
            'package':['hygiene_scan'],
            'publish_report':['release_report']
        }[st]
        missing=[r for r in required if r not in evidence]
        status='READY' if not missing and not blocked else 'BLOCKED'
        if missing: blocked=True
        rows.append({'stage':st,'required_evidence':required,'missing':missing,'status':status})
    res={'tool':'ROMancer','version':'20.0.0','feature':'v20 project lifecycle','project':m.get('project'),'ready':not blocked,'stages':rows,'policy':'The lab advances only through stages whose required evidence exists; skipped evidence blocks automation.'}
    if out: write_json(out,res)
    return res

def final_certify(manifest: str|dict[str,Any], out: str|None=None)->dict[str,Any]:
    m=_load(manifest)
    proof=evaluate_invariants({'invariants':m.get('invariants',[]),'differences':m.get('differences',[])})
    gates=[]; fail=[]
    for gate in m.get('gates',[]):
        ok=bool(gate.get('ok',False)); row={'name':gate.get('name'),'ok':ok,'required':gate.get('required',True),'evidence':gate.get('evidence')}; gates.append(row)
        if row['required'] and not ok: fail.append(row)
    release_status='CERTIFIED' if proof['valid'] and not fail else 'BLOCKED'
    res={'tool':'ROMancer','version':'20.0.0','feature':'v20 final certification','release_status':release_status,'proof_valid':proof['valid'],'gate_count':len(gates),'required_gate_failures':fail,'gates':gates,'proof_hash':proof['proof_hash'],'certification_hash':_sha_obj({'proof':proof['proof_hash'],'gates':gates}),'policy':'Final certification covers only declared proof invariants and gates. Missing gates are not silently assumed.'}
    if out: write_json(out,res)
    return res

def self_certify(root: str, out: str|None=None)->dict[str,Any]:
    rootp=Path(root); forbidden=[]; py_count=0; docs=[]
    for p in rootp.rglob('*'):
        if not p.is_file(): continue
        rel=str(p.relative_to(rootp))
        if '.romancer_runtime' in p.parts or p.suffix.lower() in FORBIDDEN_SUFFIXES and p.name not in {'original_dummy.bin','modified_dummy.bin'}:
            forbidden.append(rel)
        if p.suffix=='.py': py_count+=1
        if p.suffix.lower() in ('.md','.txt') and 'docs' in p.parts: docs.append(rel)
    gates=[{'name':'python_sources_present','ok':py_count>0,'required':True},{'name':'documentation_present','ok':len(docs)>0,'required':True},{'name':'forbidden_artifact_scan','ok':not forbidden,'required':True,'evidence':forbidden[:50]}]
    res=final_certify({'invariants':[{'name':'source tree scan','status':'PASS','required':True}], 'gates':gates})
    res.update({'feature':'v20 self-certification','root':str(rootp),'python_file_count':py_count,'doc_count':len(docs),'forbidden_artifacts':forbidden[:100]})
    if out: write_json(out,res)
    return res

def publish_report(manifest: str|dict[str,Any], out: str|None=None)->dict[str,Any]:
    m=_load(manifest)
    sections=[]
    for name in ['project','source','knowledge','gameplay','technical','regression','cross_emulator','balance','packaging','known_limitations']:
        sections.append({'section':name,'content':m.get(name,{})})
    res={'tool':'ROMancer','version':'20.0.0','feature':'v20 release report','sections':sections,'report_hash':_sha_obj(sections),'policy':'Report separates claims by supplied evidence section; absent sections remain absent.'}
    if out: write_json(out,res)
    return res

def lab_plan(request: str, out: str|None=None)->dict[str,Any]:
    plan=feature_plan(request)
    stages=['identify','research','plan','build','test','diagnose','repair','prove','certify','package']
    res={'tool':'ROMancer','version':'20.0.0','feature':'v20 lab plan','feature_plan':plan,'lab_stages':[{'stage':s,'status':'planned'} for s in stages],'policy':'Lab plan integrates creator feature planning with proof, QA and package certification.'}
    if out: write_json(out,res)
    return res
