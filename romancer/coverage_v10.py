from __future__ import annotations
from pathlib import Path
from typing import Any
import json
from .util import write_json


def coverage_report(manifest:str,out:str|None=None)->dict[str,Any]:
    obj=json.loads(Path(manifest).read_text(encoding="utf-8")); cats=[]; total_known=total_hit=0
    for name,rec in (obj.get("categories") or {}).items():
        known=set(str(x) for x in rec.get("known",[])); hit=set(str(x) for x in rec.get("hit",[])); reachable=known-set(str(x) for x in rec.get("excluded",[])); covered=hit & reachable
        pct=100.0 if not reachable else 100.0*len(covered)/len(reachable); total_known+=len(reachable); total_hit+=len(covered)
        cats.append({"category":name,"known":len(known),"eligible":len(reachable),"hit":len(covered),"coverage_percent":round(pct,2),"uncovered":sorted(reachable-covered)})
    result={"tool":"ROMancer","feature":"v10 behavior coverage","categories":cats,"overall":{"eligible":total_known,"hit":total_hit,"coverage_percent":round(100.0 if total_known==0 else 100.0*total_hit/total_known,2)}}
    if out: write_json(out,result)
    return result
