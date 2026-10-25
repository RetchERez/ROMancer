from __future__ import annotations

"""Patch ownership and conservative free-space evidence for ROMancer v10."""

from pathlib import Path
from typing import Any
import json
from .util import write_json, parse_int


def _load(path: str|Path) -> dict[str,Any]:
    p=Path(path)
    if not p.exists(): return {"schema":"romancer.patch_ledger.v1","allocations":[],"free_space_evidence":[]}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(path: str|Path,obj:dict[str,Any])->None: write_json(path,obj)

def _ival(v: Any)->int:
    if isinstance(v,int): return v
    return parse_int(str(v))

def _range(rec:dict[str,Any])->tuple[int,int]:
    s=_ival(rec["start"]); e=_ival(rec["end"]); return s,e


def ledger_add(path:str, start:str, end:str, owner:str, purpose:str="", introduced:str="", source:str="", status:str="allocated") -> dict[str,Any]:
    obj=_load(path); s=_ival(start); e=_ival(end)
    if e < s: raise ValueError("end must be >= start")
    conflicts=[]
    for a in obj.get("allocations",[]):
        x,y=_range(a)
        if not (e < x or s > y): conflicts.append(a)
    if conflicts:
        return {"ok":False,"error":"allocation_overlap","requested":{"start":s,"end":e,"owner":owner},"conflicts":conflicts}
    rec={"start":s,"end":e,"length":e-s+1,"owner":owner,"purpose":purpose,"introduced":introduced,"source":source,"status":status}
    obj.setdefault("allocations",[]).append(rec); obj["allocations"].sort(key=lambda x:_ival(x["start"])); _save(path,obj)
    return {"ok":True,"allocation":rec,"ledger":path}


def ledger_check(path:str)->dict[str,Any]:
    obj=_load(path); alloc=sorted(obj.get("allocations",[]),key=lambda x:_ival(x["start"])); overlaps=[]
    for i,a in enumerate(alloc):
        sa,ea=_range(a)
        for b in alloc[i+1:]:
            sb,eb=_range(b)
            if sb>ea: break
            if not (eb<sa or sb>ea): overlaps.append({"a":a,"b":b})
    return {"ok":not overlaps,"allocation_count":len(alloc),"overlaps":overlaps,"allocations":alloc,"free_space_evidence":obj.get("free_space_evidence",[])}


def free_space_scan(rom:str, *, byte_values=(0x00,0xFF), min_run:int=256, exclude:list[tuple[int,int]]|None=None, out:str|None=None)->dict[str,Any]:
    data=Path(rom).read_bytes(); exclude=exclude or []; runs=[]; i=0
    while i<len(data):
        if data[i] not in byte_values: i+=1; continue
        b=data[i]; j=i+1
        while j<len(data) and data[j]==b: j+=1
        if j-i>=min_run:
            s,e=i,j-1
            overlaps=any(not(e<x or s>y) for x,y in exclude)
            runs.append({"start":s,"end":e,"length":j-i,"fill_byte":b,"status":"likely_empty_pattern_only","excluded_overlap":overlaps,"evidence":["repeated fill byte"],"warnings":["Fill pattern alone does not prove unused ROM space."]})
        i=j
    result={"tool":"ROMancer","feature":"v10 free-space scan","rom":rom,"min_run":min_run,"candidates":[r for r in runs if not r["excluded_overlap"]],"policy":"candidate only until reference/execution/resource evidence supports allocation"}
    if out: write_json(out,result)
    return result


def free_space_attest(ledger:str,start:str,end:str,evidence:list[str],status:str="high_confidence_candidate")->dict[str,Any]:
    allowed={"candidate","high_confidence_candidate","verified_by_project_policy"}
    if status not in allowed: raise ValueError(f"status must be one of {sorted(allowed)}")
    if not evidence: raise ValueError("At least one evidence statement is required")
    obj=_load(ledger); rec={"start":_ival(start),"end":_ival(end),"status":status,"evidence":list(evidence)}; obj.setdefault("free_space_evidence",[]).append(rec); _save(ledger,obj); return {"ok":True,"record":rec}
