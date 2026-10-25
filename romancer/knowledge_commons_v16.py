
from __future__ import annotations
"""ROMancer v16 collaborative knowledge commons.

Knowledge capsules are JSON-only technical metadata bundles. They deliberately
avoid ROM/disc/save bytes and keep imported facts unverified unless the target
ROM hash or an explicit revalidation record supports promotion.
"""
import base64, hashlib, json
from pathlib import Path
from typing import Any
from .util import write_json

FORBIDDEN_SUFFIXES={'.sfc','.smc','.nes','.gba','.gb','.gbc','.gen','.md','.bin','.iso','.chd','.cue','.srm','.sav','.state','.rom'}
SAFE_COLLECTIONS=('facts','routines','tables','event_opcodes','control_profiles','regressions','known_bugs','fixed_bugs','schemas','tests','evidence')


def _load(x: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(x, dict): return x
    return json.loads(Path(x).read_text(encoding='utf-8'))

def _sha_obj(obj: Any) -> str:
    data=json.dumps(obj, sort_keys=True, separators=(',',':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()

def _looks_like_binary_payload(v: Any) -> bool:
    if isinstance(v,(bytes,bytearray)): return True
    if isinstance(v,str):
        if len(v)>2048 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n\r' for c in v):
            try:
                raw=base64.b64decode(v, validate=False)
                return len(raw)>1024 and sum(1 for b in raw if b<9 or (13<b<32))/max(1,len(raw))>0.05
            except Exception:
                return False
    if isinstance(v,dict): return any(_looks_like_binary_payload(x) for x in v.values())
    if isinstance(v,list): return any(_looks_like_binary_payload(x) for x in v)
    return False

def _sanitize_collection(items: Any) -> tuple[list[Any], list[str]]:
    kept=[]; warnings=[]
    if not isinstance(items,list):
        warnings.append('collection_not_list')
        return kept,warnings
    for i,item in enumerate(items):
        if _looks_like_binary_payload(item):
            warnings.append(f'item_{i}_possible_binary_payload_skipped')
            continue
        kept.append(item)
    return kept,warnings

def export_capsule(source: str | dict[str,Any], out: str|None=None) -> dict[str,Any]:
    src=_load(source)
    warnings=[]; collections={}
    for name in SAFE_COLLECTIONS:
        if name in src:
            kept,w=_sanitize_collection(src.get(name,[])); collections[name]=kept; warnings += [f'{name}:{x}' for x in w]
    game=src.get('game',{}) or {'title':src.get('title'), 'platform':src.get('platform'), 'rom_sha256':src.get('rom_sha256')}
    cap={'tool':'ROMancer','version':'16.0.0','feature':'v16 knowledge capsule','format':'rkc-json-v1','game':game,'collections':collections,'policy':'Capsules contain technical metadata and evidence only. Imported knowledge is not verified for a different ROM until revalidated.','warnings':warnings}
    cap['capsule_sha256']=_sha_obj({'game':game,'collections':collections,'format':cap['format']})
    if out: write_json(out, cap)
    return cap

def import_capsule(capsule: str | dict[str,Any], target: str | dict[str,Any], out: str|None=None) -> dict[str,Any]:
    cap=_load(capsule); tgt=_load(target)
    src_hash=(cap.get('game') or {}).get('rom_sha256')
    tgt_hash=(tgt.get('game') or {}).get('rom_sha256') or tgt.get('rom_sha256')
    same=bool(src_hash and tgt_hash and src_hash==tgt_hash)
    revalidated=set(tgt.get('revalidated_ids',[]))
    imported=[]
    for cname, items in (cap.get('collections') or {}).items():
        for item in items:
            iid=str(item.get('id') or item.get('name') or f'{cname}_{len(imported)}') if isinstance(item,dict) else f'{cname}_{len(imported)}'
            status='VERIFIED' if same or iid in revalidated else 'INHERITED_UNVERIFIED'
            imported.append({'collection':cname,'id':iid,'target_status':status,'source_status':(item or {}).get('status','UNKNOWN') if isinstance(item,dict) else 'UNKNOWN','requires_revalidation':status!='VERIFIED'})
    result={'tool':'ROMancer','version':'16.0.0','feature':'v16 capsule import','source_rom_sha256':src_hash,'target_rom_sha256':tgt_hash,'same_rom_hash':same,'imported_count':len(imported),'verified_count':sum(1 for x in imported if x['target_status']=='VERIFIED'),'candidate_count':sum(1 for x in imported if x['target_status']!='VERIFIED'),'imported':imported,'policy':'Cross-project facts are inherited unverified unless exact hash/revalidation supports them.'}
    if out: write_json(out,result)
    return result

def diff_capsules(a: str|dict[str,Any], b: str|dict[str,Any], out: str|None=None)->dict[str,Any]:
    ca=_load(a); cb=_load(b)
    def idx(cap):
        d={}
        for cname,items in (cap.get('collections') or {}).items():
            for item in items:
                if not isinstance(item,dict): continue
                iid=str(item.get('id') or item.get('name'))
                d[(cname,iid)]=_sha_obj(item)
        return d
    ia,ib=idx(ca),idx(cb)
    added=sorted([{'collection':k[0],'id':k[1]} for k in ib.keys()-ia.keys()], key=lambda x:(x['collection'],x['id']))
    removed=sorted([{'collection':k[0],'id':k[1]} for k in ia.keys()-ib.keys()], key=lambda x:(x['collection'],x['id']))
    changed=sorted([{'collection':k[0],'id':k[1]} for k in ia.keys()&ib.keys() if ia[k]!=ib[k]], key=lambda x:(x['collection'],x['id']))
    res={'tool':'ROMancer','version':'16.0.0','feature':'v16 capsule diff','added_count':len(added),'removed_count':len(removed),'changed_count':len(changed),'added':added,'removed':removed,'changed':changed}
    if out: write_json(out,res)
    return res

def audit_capsule(capsule: str|dict[str,Any], out: str|None=None)->dict[str,Any]:
    cap=_load(capsule); warnings=[]; entry_count=0
    for cname,items in (cap.get('collections') or {}).items():
        if cname not in SAFE_COLLECTIONS: warnings.append(f'unknown_collection:{cname}')
        if not isinstance(items,list): warnings.append(f'not_list:{cname}'); continue
        entry_count += len(items)
        for i,item in enumerate(items):
            if _looks_like_binary_payload(item): warnings.append(f'possible_payload:{cname}[{i}]')
            if isinstance(item,dict):
                for key,val in item.items():
                    if key.endswith('_path') and Path(str(val)).suffix.lower() in FORBIDDEN_SUFFIXES:
                        warnings.append(f'forbidden_path_reference:{cname}[{i}].{key}')
    ok=not warnings and cap.get('format')=='rkc-json-v1'
    res={'tool':'ROMancer','version':'16.0.0','feature':'v16 capsule audit','ok':ok,'entry_count':entry_count,'warning_count':len(warnings),'warnings':warnings[:100],'policy':'Audit checks capsule shape and possible asset leakage; it does not prove legal status of arbitrary text.'}
    if out: write_json(out,res)
    return res
