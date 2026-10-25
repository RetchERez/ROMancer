from __future__ import annotations

"""Learned visual state signatures for ROMancer v7.

These signatures identify previously captured observable screen states. They are not OCR,
not a semantic classifier by themselves, and do not assert story meaning unless the label
was supplied with evidence by the profile author.
"""

import base64
import json
from pathlib import Path
from typing import Any

from .frame_analysis import thumbnail_luma
from .libretro_frontend import Frame
from .util import write_json


def capture_state_signature(frame: Frame, name: str, *, context: str="unknown", cols: int=24, rows: int=21, status: str="candidate", evidence: str | None=None) -> dict[str, Any]:
    if status not in {"candidate","verified"}:
        raise ValueError("status must be candidate or verified")
    if status == "verified" and not evidence:
        raise ValueError("verified state signatures require evidence")
    thumb=thumbnail_luma(frame,cols,rows)
    return {
        "name":name,"context":context,"status":status,"evidence":evidence,
        "frame":{"width":frame.width,"height":frame.height,"rgb_sha256":frame.sha256()},
        "visual":{"cols":cols,"rows":rows,"luma_base64":base64.b64encode(thumb).decode("ascii")},
    }


def compare_state_signature(signature: dict[str,Any], frame: Frame, *, threshold: int=12) -> dict[str,Any]:
    vis=signature.get("visual") or {}; cols=int(vis.get("cols",24)); rows=int(vis.get("rows",21))
    raw=base64.b64decode(vis.get("luma_base64","") or "",validate=True)
    live=thumbnail_luma(frame,cols,rows)
    if len(raw)!=len(live) or not raw:
        return {"comparable":False,"reason":"signature dimensions/data invalid"}
    diffs=[abs(a-b) for a,b in zip(raw,live)]
    changed=sum(1 for d in diffs if d>=threshold)
    exact=(signature.get("frame") or {}).get("rgb_sha256")==frame.sha256()
    return {
        "comparable":True,"name":signature.get("name"),"context":signature.get("context"),"status":signature.get("status"),
        "exact_rgb_match":bool(exact),"mean_abs_luma_delta":round(sum(diffs)/len(diffs),4),
        "max_luma_delta":max(diffs),"changed_cell_ratio":round(changed/len(diffs),6),"threshold":threshold,
    }


def load_state_library(path: str | Path) -> list[dict[str,Any]]:
    obj=json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(obj,list): states=obj
    elif isinstance(obj,dict) and isinstance(obj.get("states"),list): states=obj["states"]
    elif isinstance(obj,dict) and obj.get("visual"): states=[obj]
    else: raise ValueError("State library must be a signature object, an array, or {states:[...]}")
    return [x for x in states if isinstance(x,dict)]


def match_state_library(states: list[dict[str,Any]], frame: Frame, *, threshold: int=12, max_results: int=10) -> dict[str,Any]:
    results=[]
    for state in states:
        try: comp=compare_state_signature(state,frame,threshold=threshold)
        except Exception as exc: comp={"comparable":False,"name":state.get("name"),"error":str(exc)}
        results.append(comp)
    results.sort(key=lambda x:(0 if x.get("comparable") else 1,float(x.get("mean_abs_luma_delta",1e9)),float(x.get("changed_cell_ratio",1e9))))
    return {"match_count":len(results),"best":results[0] if results else None,"matches":results[:max_results],
            "interpretation":"Lowest visual delta is the nearest previously captured state. Semantic meaning comes from the evidence-backed label, not from visual similarity alone."}


def save_state_signature(path: str|Path, signature: dict[str,Any])->str:
    write_json(path,signature); return str(path)
