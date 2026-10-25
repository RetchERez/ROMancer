from __future__ import annotations

import json, math, os, re, shutil, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .util import read_bytes, write_json, read_json, parse_int, sha1, sha256, crc32_hex
from .trace_parser import parse_trace
from .v3 import disasm, cfg_from_disasm, value_flow
from .workflow import correlate_trace, find_routine
from .systems.snes import snes_to_offset

VERSION = "4.0.0"


def _out(obj: Any, out: str | None = None) -> Any:
    if out:
        p = Path(out); p.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() == ".dot" and isinstance(obj, dict) and "dot" in obj:
            p.write_text(obj["dot"], encoding="utf-8")
        elif p.suffix.lower() in {".txt", ".md"} and isinstance(obj, dict) and "text" in obj:
            p.write_text(obj["text"], encoding="utf-8")
        else:
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return obj


def _norm(s: Any) -> str:
    return str(s or "").upper().replace("0X", "").replace("$", "").replace(":", "").replace(" ", "")


def _load_project_db(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    data: dict[str, Any] = {"project": str(root), "project_json": {}, "knowledge": {}, "evidence": {}, "reports": [], "traces": []}
    for name, key, default in [("project.json", "project_json", {}), ("knowledge.json", "knowledge", {"symbols": [], "findings": [], "routines": []}), ("evidence/evidence.json", "evidence", {"evidence": []})]:
        p = root / name
        if p.exists():
            try: data[key] = json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc: data[key] = {"error": str(exc), "path": str(p)}
        else:
            data[key] = default
    for folder in [root / "reports", root / "traces"]:
        if folder.exists():
            for p in folder.rglob("*"):
                if p.is_file():
                    (data["reports"] if folder.name == "reports" else data["traces"]).append(str(p))
    return data


# ---------------------------------------------------------------------------
# Project graph


def graph_build(project: str, out: str | None = None) -> dict[str, Any]:
    db = _load_project_db(project); root = Path(project)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def node(nid: str, kind: str, label: str, **props):
        nodes[nid] = {"id": nid, "kind": kind, "label": label, **props}
        return nid

    def edge(a: str, b: str, kind: str, **props):
        if a in nodes and b in nodes:
            edges.append({"from": a, "to": b, "kind": kind, **props})

    pj = db.get("project_json", {}) or {}
    ident = pj.get("identity", {}) or {}
    rom_node = node("rom:original", "rom", ident.get("internal_title") or ident.get("domestic_title") or Path(str(pj.get("rom_original", "ROM"))).name, sha1=ident.get("sha1"), system=ident.get("system"), mapping=ident.get("mapping_guess"))

    knowledge = db.get("knowledge", {}) or {}
    for i, s in enumerate(knowledge.get("symbols", []) or []):
        sid = node(f"symbol:{i}", "symbol", s.get("name") or f"symbol_{i}", **{("symbol_"+k if k in {"id","kind","label"} else k): v for k, v in s.items()})
        target = s.get("address") or s.get("offset")
        if target:
            tid = node(f"address:{_norm(target)}", "address", str(target))
            edge(sid, tid, "labels")
    for i, f in enumerate(knowledge.get("findings", []) or []):
        fid = node(f"finding:{i}", "finding", f.get("claim") or f"finding_{i}", **{("finding_"+k if k in {"id","kind","label"} else k): v for k, v in f.items()})
        ev = f.get("evidence")
        if ev:
            eid = node(f"evidence_ref:{i}", "evidence_ref", str(ev), path=str(ev))
            edge(eid, fid, "supports")
    for i, r in enumerate(knowledge.get("routines", []) or []):
        rid = node(f"routine:{_norm(r.get('pc') or i)}", "routine", r.get("name") or str(r.get("pc")), **{("routine_"+k if k in {"id","kind","label"} else k): v for k, v in r.items()})
        if r.get("pc"):
            aid = node(f"address:{_norm(r.get('pc'))}", "address", str(r.get("pc")))
            edge(aid, rid, "entry_pc")

    for t in db.get("traces", []):
        tid = node(f"trace:{Path(t).name}", "trace", Path(t).name, path=t)
        edge(rom_node, tid, "debugged_by")
        try:
            parsed = parse_trace(t, max_events=2000)
            pcs = Counter(e.get("pc") for e in parsed.get("events", []) if e.get("pc"))
            for pc, count in pcs.most_common(25):
                aid = node(f"address:{_norm(pc)}", "address", pc)
                edge(tid, aid, "mentions_pc", count=count)
            for e in parsed.get("events", []):
                ma = e.get("memory_access") or {}
                if ma.get("address"):
                    mid = node(f"address:{_norm(ma.get('address'))}", "address", str(ma.get("address")))
                    edge(tid, mid, ma.get("kind", "memory_access"), line=e.get("line"), pc=e.get("pc"))
        except Exception as exc:
            nodes[tid]["parse_error"] = str(exc)

    for rpt in db.get("reports", []):
        rid = node(f"report:{Path(rpt).name}", "report", Path(rpt).name, path=rpt)
        edge(rom_node, rid, "has_report")

    result = {"tool": "ROMancer", "version": VERSION, "feature": "project graph", "project": str(root), "node_count": len(nodes), "edge_count": len(edges), "nodes": list(nodes.values()), "edges": edges}
    graph_path = root / "reports" / "project_graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _out(result, out)


def graph_query(project: str, query: str, out: str | None = None) -> dict[str, Any]:
    graph = graph_build(project)
    q = _norm(query)
    hits = []
    for n in graph["nodes"]:
        blob = json.dumps(n, sort_keys=True).upper()
        if q in _norm(blob) or str(query).upper() in blob:
            related = [e for e in graph["edges"] if e.get("from") == n["id"] or e.get("to") == n["id"]]
            hits.append({"node": n, "related_edges": related[:50]})
    return _out({"tool":"ROMancer","version":VERSION,"feature":"graph query","query":query,"hit_count":len(hits),"hits":hits}, out)


def graph_export(project: str, out: str) -> dict[str, Any]:
    return graph_build(project, out)


def graph_dot(project: str, out: str | None = None) -> dict[str, Any]:
    graph = graph_build(project)
    lines = ["digraph romancer_project {", "  rankdir=LR;"]
    for n in graph["nodes"][:500]:
        label = str(n.get("label", n["id"])).replace('"', "'")[:80]
        lines.append(f'  "{n["id"]}" [label="{label}\n{n.get("kind")}"];')
    for e in graph["edges"][:1000]:
        lines.append(f'  "{e["from"]}" -> "{e["to"]}" [label="{e.get("kind", "rel")}"];')
    lines.append("}")
    return _out({"tool":"ROMancer","version":VERSION,"feature":"graph dot","dot":"\n".join(lines)+"\n","node_count":graph["node_count"],"edge_count":graph["edge_count"]}, out)


# ---------------------------------------------------------------------------
# Confidence engine


def _score_finding(f: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    status = str(f.get("status", "candidate")).lower()
    score = {"confirmed": 0.65, "candidate": 0.45, "suspected": 0.25, "rejected": 0.0}.get(status, 0.35)
    reasons: list[str] = []
    risks: list[str] = []
    if f.get("evidence"):
        score += 0.18; reasons.append("evidence_reference_present")
    else:
        risks.append("no_evidence_reference")
    try:
        conf = float(f.get("confidence"))
        score = max(score, min(0.95, conf))
        reasons.append("existing_confidence_field")
    except Exception:
        pass
    claim = str(f.get("claim", "")).lower()
    if any(x in claim for x in ["trace", "breakpoint", "write", "read", "pc", "offset"]):
        score += 0.05; reasons.append("claim_mentions_verifiable_debug_artifact")
    if "likely" in claim or "maybe" in claim:
        risks.append("hedged_claim_language")
    return max(0.0, min(0.98, score)), reasons, risks


def confidence_recompute(project: str, out: str | None = None) -> dict[str, Any]:
    db = _load_project_db(project); findings = (db.get("knowledge") or {}).get("findings", []) or []
    scored=[]
    for i,f in enumerate(findings):
        score,reasons,risks=_score_finding(f)
        status = "confirmed" if score >= 0.8 else "candidate" if score >= 0.45 else "suspected" if score > 0 else "rejected"
        scored.append({"id": f"finding:{i}", "claim": f.get("claim"), "score": round(score, 3), "status_recomputed": status, "reason_codes": reasons, "remaining_risks": risks})
    result={"tool":"ROMancer","version":VERSION,"feature":"confidence recompute","project":project,"finding_count":len(scored),"findings":scored,"rule":"heuristic, evidence-weighted; not proof"}
    return _out(result,out)


def confidence_explain(project: str, finding: str, out: str | None = None) -> dict[str, Any]:
    recomputed=confidence_recompute(project); target=_norm(finding)
    hits=[f for f in recomputed["findings"] if target in _norm(f.get("id")) or target in _norm(f.get("claim"))]
    return _out({"tool":"ROMancer","version":VERSION,"feature":"confidence explain","query":finding,"hit_count":len(hits),"hits":hits}, out)


# ---------------------------------------------------------------------------
# Multi-trace and routine analysis


def trace_batch_correlate(traces: list[str], addr: str | None = None, out: str | None = None) -> dict[str, Any]:
    per=[]; pc_sets=[]; target=_norm(addr) if addr else None
    for t in traces:
        parsed=parse_trace(t); events=parsed.get("events", [])
        pcs=Counter(e.get("pc") for e in events if e.get("pc"))
        hits=[]
        for e in events:
            ma=e.get("memory_access") or {}
            if target and ma.get("address") and target.endswith(_norm(ma.get("address"))):
                hits.append({"line":e.get("line"),"pc":e.get("pc"),"mnemonic":e.get("mnemonic"),"operands":e.get("operands"),"memory_access":ma})
        pc_sets.append(set(pcs.keys()))
        per.append({"trace":t,"event_count":len(events),"unique_pc_count":len(pcs),"hot_pcs":pcs.most_common(20),"target_hit_count":len(hits),"target_hits":hits[:50]})
    common=set.intersection(*pc_sets) if pc_sets else set()
    unique=[]
    for item,pcs in zip(per,pc_sets): unique.append({"trace":item["trace"],"unique_pcs":sorted(list(pcs-common))[:100]})
    result={"tool":"ROMancer","version":VERSION,"feature":"trace batch correlate","addr":addr,"trace_count":len(traces),"per_trace":per,"common_pcs":sorted(common)[:200],"unique_pc_summary":unique,"recommendation":"Prefer unique upstream PCs over common shared write routines when changing a specific reward/source."}
    return _out(result,out)


def classify_routine(trace: str | None = None, pc: str | None = None, project: str | None = None, out: str | None = None) -> dict[str, Any]:
    target=_norm(pc) if pc else None; signals=Counter(); samples=[]
    if trace:
        parsed=parse_trace(trace)
        for e in parsed.get("events", []):
            if target and target not in _norm(e.get("pc")): continue
            m=(e.get("mnemonic") or "").upper(); ops=(e.get("operands") or "").upper(); ma=e.get("memory_access") or {}
            if ma.get("kind", "").startswith("write") or m in {"STA","STX","STY","MOVE","MOVE.W","MOVE.L"}: signals["writes_memory"] += 1
            if ma.get("address") and _norm(ma.get("address")).startswith("7E09"): signals["inventory_range_write_snes_like"] += 2
            if "C000" in ops or "VDP" in ops: signals["video_register_or_vdp"] += 2
            if m in {"JSR","JSL","BSR"}: signals["calls_other_routines"] += 1
            if m in {"LDA","LDX","LDY","MOVE","LEA"}: signals["loads_values"] += 1
            if len(samples)<12: samples.append({"line":e.get("line"),"pc":e.get("pc"),"instruction":f"{m} {ops}".strip(),"memory_access":ma})
    # classify by signal weights
    classes=[]
    if signals["inventory_range_write_snes_like"]: classes.append(("inventory write", 0.80))
    if signals["video_register_or_vdp"]: classes.append(("graphics/video routine", 0.70))
    if signals["writes_memory"] and not classes: classes.append(("state update/write routine", 0.55))
    if signals["calls_other_routines"] and not classes: classes.append(("dispatcher/caller routine", 0.45))
    if not classes: classes.append(("unknown", 0.20))
    result={"tool":"ROMancer","version":VERSION,"feature":"classify routine","pc":pc,"trace":trace,"likely_class":classes[0][0],"confidence":classes[0][1],"signals":dict(signals),"samples":samples,"limitation":"heuristic classification from trace evidence only"}
    return _out(result,out)


def recommend_patch(project: str | None = None, traces: list[str] | None = None, addr: str | None = None, goal: str = "", out: str | None = None) -> dict[str, Any]:
    traces = traces or []
    candidates=[]
    if traces:
        batch=trace_batch_correlate(traces, addr)
        common=set(batch.get("common_pcs", []))
        for item in batch.get("per_trace", []):
            for hit in item.get("target_hits", []):
                pc=hit.get("pc")
                shared = pc in common
                candidates.append({"pc":pc,"source_trace":item.get("trace"),"kind":"target write routine","risk":"high" if shared else "medium","rank_reason":"shared across traces; likely common write routine" if shared else "trace-local target write; may still be downstream","evidence":hit})
            for pc,count in item.get("hot_pcs", [])[:5]:
                if pc not in common:
                    candidates.append({"pc":pc,"source_trace":item.get("trace"),"kind":"unique hot PC","risk":"medium","rank_reason":"unique to one trace; inspect as upstream candidate","count":count})
    if project:
        db=_load_project_db(project); k=db.get("knowledge",{}) or {}
        for r in k.get("routines",[]) or []:
            candidates.append({"pc":r.get("pc"),"kind":"known routine","risk":"medium","rank_reason":"user/project-known routine, inspect evidence before patching","routine":r})
    def score(c):
        risk={"low":3,"medium":2,"high":1}.get(c.get("risk"),1)
        upstream=1 if "unique" in c.get("kind","") or "upstream" in c.get("rank_reason","") else 0
        return risk+upstream
    ranked=sorted(candidates, key=score, reverse=True)
    result={"tool":"ROMancer","version":VERSION,"feature":"recommend patch","goal":goal,"addr":addr,"candidate_count":len(ranked),"ranked_candidates":ranked[:50],"rule":"Prefer data tables or unique upstream callers. Avoid shared write routines unless global behavior is intended."}
    return _out(result,out)


def patch_rank(project: str | None = None, traces: list[str] | None = None, addr: str | None = None, out: str | None = None) -> dict[str,Any]:
    return recommend_patch(project, traces, addr, goal="rank candidate patch points", out=out)


def code_map(trace: str, out: str | None = None) -> dict[str, Any]:
    parsed=parse_trace(trace); pcs=Counter(); calls=[]; branches=[]; writes=[]
    for e in parsed.get("events", []):
        pc=e.get("pc"); m=(e.get("mnemonic") or "").upper()
        if pc: pcs[pc]+=1
        if m in {"JSR","JSL","BSR"}: calls.append({"line":e.get("line"),"pc":pc,"operands":e.get("operands")})
        if m.startswith("B") or m in {"JMP","BRA"}: branches.append({"line":e.get("line"),"pc":pc,"operands":e.get("operands")})
        ma=e.get("memory_access") or {}
        if ma.get("kind","").startswith("write"): writes.append({"line":e.get("line"),"pc":pc,"memory_access":ma})
    result={"tool":"ROMancer","version":VERSION,"feature":"code map","trace":trace,"hot_pcs":pcs.most_common(50),"calls":calls[:200],"branches":branches[:200],"writes":writes[:200],"limitation":"trace-derived map, not full static code discovery"}
    return _out(result,out)


# ---------------------------------------------------------------------------
# Symbols import/export


def _knowledge_path(project: str|Path)->Path:
    p=Path(project)/"knowledge.json"; p.parent.mkdir(parents=True,exist_ok=True); return p

def _load_knowledge(project: str|Path)->dict[str,Any]:
    p=_knowledge_path(project)
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    return {"symbols":[],"findings":[],"routines":[]}

def _save_knowledge(project: str|Path, db: dict[str,Any]) -> None:
    _knowledge_path(project).write_text(json.dumps(db,indent=2,sort_keys=True)+"\n",encoding="utf-8")


def symbols_import(project: str, path: str, fmt: str = "generic", out: str | None = None) -> dict[str,Any]:
    db=_load_knowledge(project); added=[]
    for line in Path(path).read_text(encoding="utf-8",errors="replace").splitlines():
        raw=line.strip()
        if not raw or raw.startswith("#") or raw.startswith(";"): continue
        name=None; addr=None
        if "=" in raw:
            a,b=[x.strip() for x in raw.split("=",1)]; name=a; addr=b
        else:
            parts=re.split(r"\s+",raw)
            if len(parts)>=2:
                if re.fullmatch(r"[$0-9A-Fa-f:xX:]+", parts[0]): addr=parts[0]; name=parts[1]
                else: name=parts[0]; addr=parts[1]
        if name and addr:
            sym={"name":name,"address":addr,"kind":"imported_symbol","system":"unknown","status":"candidate","notes":f"imported format={fmt}"}
            db.setdefault("symbols",[]).append(sym); added.append(sym)
    _save_knowledge(project,db)
    return _out({"tool":"ROMancer","version":VERSION,"feature":"symbols import","project":project,"source":path,"format":fmt,"added_count":len(added),"added":added[:100]},out)


def symbols_export(project: str, fmt: str = "generic-json", out: str | None = None) -> dict[str,Any]:
    db=_load_knowledge(project); syms=db.get("symbols",[]) or []
    if fmt in {"generic-json","json"}:
        result={"tool":"ROMancer","version":VERSION,"feature":"symbols export","format":fmt,"symbols":syms}
        return _out(result,out)
    lines=[]
    for s in syms:
        name=s.get("name") or "unnamed"; addr=s.get("address") or s.get("offset") or ""
        if fmt.lower().startswith("mesen"):
            lines.append(f"{addr} {name}")
        else:
            lines.append(f"{name} = {addr}")
    text="\n".join(lines)+("\n" if lines else "")
    if out:
        Path(out).parent.mkdir(parents=True,exist_ok=True); Path(out).write_text(text,encoding="utf-8")
    return {"tool":"ROMancer","version":VERSION,"feature":"symbols export","format":fmt,"symbol_count":len(syms),"text":text}


# ---------------------------------------------------------------------------
# Disasm routine, compression, fixtures, state diff


def disasm_routine(rom: str, system: str, pc: str | None = None, offset: str | None = None, mapping: str | None = None, count: int = 160, out: str | None = None) -> dict[str,Any]:
    d=disasm(rom, system, offset, pc, mapping, count)
    instr=d.get("instructions", [])
    calls=[]; branches=[]; stores=[]; loads=[]
    for row in instr:
        m=row.get("mnemonic","").upper(); ops=row.get("operands","")
        item={"offset":row.get("offset"),"mnemonic":m,"operands":ops,"bytes":row.get("bytes")}
        if m in {"JSR","JSL","BSR"}: calls.append(item)
        if m.startswith("B") or m in {"JMP","BRA/BCC","BRA/Bcc"}: branches.append(item)
        if m in {"STA","STX","STY","MOVE"}: stores.append(item)
        if m in {"LDA","LDX","LDY","MOVE","LEA"}: loads.append(item)
    result={"tool":"ROMancer","version":VERSION,"feature":"disasm routine","rom":rom,"system":system,"pc":pc,"offset":offset,"mapping":mapping,"instruction_count":len(instr),"calls":calls,"branches":branches,"stores":stores,"loads":loads,"disasm":d,"routine_boundary":"best-effort only; static analysis cannot distinguish all code/data"}
    return _out(result,out)


def compression_hint(rom: str, system: str = "unknown", window: int = 4096, step: int = 4096, out: str | None = None) -> dict[str,Any]:
    data=read_bytes(rom); regions=[]
    for off in range(0, len(data), step):
        chunk=data[off:off+window]
        if not chunk: break
        counts=Counter(chunk); total=len(chunk)
        entropy=-sum((c/total)*math.log2(c/total) for c in counts.values()) if total else 0
        zero_run=max((len(m.group(0)) for m in re.finditer(rb"\x00+", chunk)), default=0)
        ff_run=max((len(m.group(0)) for m in re.finditer(rb"\xFF+", chunk)), default=0)
        unique=len(counts)
        reason=[]; kind="unknown"
        if entropy > 7.2 and unique > 180: kind="high entropy / possible compressed or packed data"; reason.append("high_entropy")
        elif entropy < 2.5 and max(zero_run,ff_run)>128: kind="blank/filler/repeated region"; reason.append("long_fill_runs")
        elif 3.0 <= entropy <= 5.8: kind="possible tile/table/text region"; reason.append("moderate_entropy")
        if reason:
            regions.append({"offset":f"0x{off:06X}","length":len(chunk),"entropy":round(entropy,3),"unique_bytes":unique,"kind":kind,"reason_codes":reason,"longest_zero_run":zero_run,"longest_ff_run":ff_run})
    result={"tool":"ROMancer","version":VERSION,"feature":"compression hint","rom":rom,"system":system,"window":window,"step":step,"region_count":len(regions),"regions":regions[:300],"limitation":"entropy heuristic only; not a decompressor"}
    return _out(result,out)


def fixture_run(which: str = "all", out: str | None = None) -> dict[str,Any]:
    root=Path(__file__).resolve().parent.parent
    tests=[]
    def test(name, ok, detail=""):
        tests.append({"name":name,"ok":bool(ok),"detail":detail})
    try:
        p=root/"examples"/"bsnes_plus_trace_sample.log"; parsed=parse_trace(str(p)); test("parse bsnes sample", len(parsed.get("events",[]))>0, str(p))
    except Exception as exc: test("parse bsnes sample", False, str(exc))
    try:
        p=root/"examples"/"blastem_trace_sample.log"; parsed=parse_trace(str(p)); test("parse blastem sample", len(parsed.get("events",[]))>0, str(p))
    except Exception as exc: test("parse blastem sample", False, str(exc))
    try:
        # minimal synthetic disasm fixture
        tmp=root/"reports"/"fixture_snes.bin"; tmp.parent.mkdir(exist_ok=True); tmp.write_bytes(bytes([0xA9,0x02,0x06,0x8D,0x22,0x09,0x60]))
        d=disasm_routine(str(tmp),"snes",offset="0",count=4); test("disasm routine synthetic", len(d.get("disasm",{}).get("instructions",[]))>0, str(tmp))
    except Exception as exc: test("disasm routine synthetic", False, str(exc))
    try:
        data=bytes(range(256))*4; tmp=root/"reports"/"fixture_entropy.bin"; tmp.write_bytes(data)
        ch=compression_hint(str(tmp)); test("compression hint synthetic", ch.get("region_count",0)>0, str(tmp))
    except Exception as exc: test("compression hint synthetic", False, str(exc))
    ok=all(t["ok"] for t in tests)
    result={"tool":"ROMancer","version":VERSION,"feature":"fixture run","which":which,"ok":ok,"test_count":len(tests),"tests":tests}
    return _out(result,out)


def state_diff(before: str, after: str, out: str | None = None) -> dict[str,Any]:
    a=read_bytes(before); b=read_bytes(after); changes=[]; max_len=max(len(a),len(b)); i=0
    while i<max_len:
        ba=a[i] if i<len(a) else None; bb=b[i] if i<len(b) else None
        if ba==bb:
            i+=1
            continue
        start=i; av=[]; bv=[]
        # Advance until equality resumes, EOF, or a large region sample is captured.
        while i<max_len:
            ca=a[i] if i<len(a) else None; cb=b[i] if i<len(b) else None
            if ca==cb:
                break
            if len(av)<256 and ca is not None: av.append(ca)
            if len(bv)<256 and cb is not None: bv.append(cb)
            i+=1
        changes.append({"offset":f"0x{start:06X}","before":" ".join(f"{x:02X}" for x in av[:32]),"after":" ".join(f"{x:02X}" for x in bv[:32]),"sample_len":max(len(av),len(bv)),"truncated_sample":len(av)>=256 or len(bv)>=256})
    result={"tool":"ROMancer","version":VERSION,"feature":"state diff","before":before,"after":after,"before_size":len(a),"after_size":len(b),"change_region_count":len(changes),"changes":changes[:500],"limitation":"raw binary diff; emulator-specific save-state decoding not implemented"}
    return _out(result,out)

