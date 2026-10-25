
from __future__ import annotations
"""ROMancer v17 formal proof and invariant certification."""
import hashlib, json, shutil
from pathlib import Path
from typing import Any
from .util import write_json

def _load(x: str|dict[str,Any])->dict[str,Any]:
    if isinstance(x,dict): return x
    return json.loads(Path(x).read_text(encoding='utf-8'))

def _sha_obj(obj: Any)->str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def evaluate_invariants(manifest: str|dict[str,Any], out: str|None=None)->dict[str,Any]:
    m=_load(manifest)
    rows=[]; failures=[]; warnings=[]
    for inv in m.get('invariants',[]):
        name=inv.get('name','unnamed'); required=bool(inv.get('required',True)); status=str(inv.get('status','UNKNOWN')).upper()
        ok=status in ('PASS','VALID','VERIFIED')
        row={'name':name,'category':inv.get('category','general'),'required':required,'status':status,'ok':ok,'evidence':inv.get('evidence')}
        rows.append(row)
        if required and not ok: failures.append(row)
        elif not required and not ok: warnings.append(row)
    diffs=m.get('differences',[]); unexplained=[d for d in diffs if str(d.get('mode','')).lower() not in ('intentional-different','accepted','documented') and not d.get('accepted')]
    valid=not failures and not unexplained
    res={'tool':'ROMancer','version':'17.0.0','feature':'v17 invariant proof','valid':valid,'invariant_count':len(rows),'required_failure_count':len(failures),'optional_warning_count':len(warnings),'unexplained_difference_count':len(unexplained),'invariants':rows,'failures':failures,'warnings':warnings,'unexplained_differences':unexplained,'proof_hash':_sha_obj({'invariants':rows,'differences':diffs}),'policy':'A proof is valid only for declared gates and declared accepted differences.'}
    if out: write_json(out,res)
    return res

def compare_modes(baseline: str|dict[str,Any], candidate: str|dict[str,Any], out: str|None=None)->dict[str,Any]:
    a=_load(baseline); b=_load(candidate)
    rows=[]
    for key in sorted(set(a.keys())|set(b.keys())):
        av=a.get(key); bv=b.get(key)
        mode='byte-identical' if av==bv else 'different'
        if isinstance(av,dict) and isinstance(bv,dict) and av.get('semantic')==bv.get('semantic') and av!=bv:
            mode='semantically-equivalent'
        rows.append({'field':key,'mode':mode,'baseline':av,'candidate':bv})
    res={'tool':'ROMancer','version':'17.0.0','feature':'v17 comparison modes','all_identical':all(r['mode']=='byte-identical' for r in rows),'rows':rows}
    if out: write_json(out,res)
    return res

def build_proof_bundle(manifest: str|dict[str,Any], out_dir: str, out: str|None=None)->dict[str,Any]:
    m=_load(manifest); outp=Path(out_dir); outp.mkdir(parents=True,exist_ok=True)
    proof=evaluate_invariants(m)
    (outp/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True),encoding='utf-8')
    (outp/'proof.json').write_text(json.dumps(proof,indent=2,sort_keys=True),encoding='utf-8')
    copied=[]
    for art in m.get('artifacts',[]):
        p=Path(art.get('path',''))
        if p.exists() and p.is_file() and p.suffix.lower() not in {'.sfc','.smc','.nes','.gba','.gb','.gbc','.gen','.iso','.chd','.bin','.srm','.sav','.state'}:
            dest=outp/p.name; shutil.copy2(p,dest); copied.append(dest.name)
    bundle={'tool':'ROMancer','version':'17.0.0','feature':'v17 proof bundle','dir':str(outp),'valid':proof['valid'],'copied_artifacts':copied,'proof_hash':proof['proof_hash']}
    if out: write_json(out,bundle)
    return bundle
