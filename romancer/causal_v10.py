from __future__ import annotations

"""Causal evidence and offline trace slicing for ROMancer v10."""

from pathlib import Path
from typing import Any
from .trace_parser import parse_trace
from .v3 import value_flow
from .util import write_json


def _norm(v: Any) -> str:
    return str(v or "").upper().replace("0X", "").replace("$", "").replace(":", "").replace(" ", "")


def trace_writers(trace: str, address: str, *, trace_format: str = "auto", limit: int = 100) -> dict[str, Any]:
    target = _norm(address); events = parse_trace(trace, trace_format=trace_format).get("events", [])
    hits=[]
    for i,e in enumerate(events):
        ma=e.get("memory_access") or {}; a=_norm(ma.get("address")); kind=str(ma.get("kind","")).lower()
        if a and target and (a.endswith(target) or target.endswith(a)) and "write" in kind:
            hits.append({"index":i,"line":e.get("line"),"pc":e.get("pc"),"mnemonic":e.get("mnemonic"),"operands":e.get("operands"),"memory_access":ma,"registers":e.get("registers") or {},"raw":e.get("raw")})
    return {"tool":"ROMancer","feature":"v10 trace writers","trace":trace,"address":address,"writer_count":len(hits),"writers":hits[:limit],"status":"observed_trace_evidence" if hits else "no_writer_observed"}


def causal_slice(trace: str, address: str, *, trace_format: str = "auto", before: int = 80, after: int = 12, out: str | None = None) -> dict[str, Any]:
    parsed=parse_trace(trace, trace_format=trace_format); events=parsed.get("events",[]); target=_norm(address)
    slices=[]
    for i,e in enumerate(events):
        ma=e.get("memory_access") or {}; a=_norm(ma.get("address")); kind=str(ma.get("kind","")).lower()
        if not a or not target or not (a.endswith(target) or target.endswith(a)) or "write" not in kind: continue
        lo=max(0,i-before); hi=min(len(events),i+after+1); window=events[lo:hi]
        candidates=[]
        for j,x in enumerate(window[:i-lo]):
            m=(x.get("mnemonic") or "").upper()
            if m.startswith(("LD","MOV","LEA")) or m in {"LDA","LDX","LDY","PEA","PEI"}:
                candidates.append({"relative_index":j-(i-lo),"line":x.get("line"),"pc":x.get("pc"),"mnemonic":x.get("mnemonic"),"operands":x.get("operands"),"registers":x.get("registers") or {},"memory_access":x.get("memory_access")})
        slices.append({"writer":{"line":e.get("line"),"pc":e.get("pc"),"mnemonic":e.get("mnemonic"),"operands":e.get("operands"),"memory_access":ma,"registers":e.get("registers") or {}},"upstream_load_candidates":candidates[-24:],"following":window[(i-lo)+1:]})
    vf=None
    try: vf=value_flow(trace,address,window=max(before,80))
    except Exception as exc: vf={"error":str(exc)}
    result={"tool":"ROMancer","feature":"v10 causal slice","trace":trace,"address":address,"slice_count":len(slices),"slices":slices[:50],"legacy_value_flow":vf,"confidence":"observed writer; upstream source remains candidate unless independently verified","warnings":["Offline trace slicing cannot reconstruct values omitted by the trace format.","Indirect addressing, bank state and DMA may require a live debugger adapter."]}
    if out: write_json(out,result)
    return result


def causal_report(symptom: str, trace: str, address: str, out: str | None = None) -> dict[str, Any]:
    writers=trace_writers(trace,address); sliced=causal_slice(trace,address)
    result={"tool":"ROMancer","feature":"v10 causal report","symptom":symptom,"target":{"address":address,"status":"user_or_prior-evidence supplied"},"writers":writers,"causal_slice":sliced,"conclusion_status":"candidate" if writers.get("writer_count") else "insufficient_evidence"}
    if writers.get("writer_count")==1:
        result["candidate_direct_cause"]={k:writers["writers"][0].get(k) for k in ("pc","mnemonic","operands","line")}
    if out: write_json(out,result)
    return result
