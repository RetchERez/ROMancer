from __future__ import annotations

"""ROMancer v12 automatic game architecture reconstruction primitives."""

import json, re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from .trace_parser import parse_trace
from .util import write_json, parse_int

CALL_MNEMONICS={"JSR","JSL","BSR","CALL"}
RETURN_MNEMONICS={"RTS","RTL","RTI","RTE"}


def _norm_pc(v:str|None)->str|None:
    if not v: return None
    return v.upper().replace("0X","").replace("$","").replace(":","")


def _operand_target(ops:str)->str|None:
    # Conservative absolute target extraction only. Indirect calls remain unknown.
    if not ops or "(" in ops or "[" in ops: return None
    m=re.search(r"(?:\$|0x)?([0-9A-Fa-f]{4,8})",ops)
    return _norm_pc(m.group(1)) if m else None


def reconstruct_call_graph(trace:str, trace_format:str="auto", out:str|None=None)->dict[str,Any]:
    parsed=parse_trace(trace,trace_format=trace_format)
    events=parsed.get("events",[])
    nodes=Counter(); edges=Counter(); returns=0; calls=[]
    for e in events:
        pc=_norm_pc(e.get("pc")); m=(e.get("mnemonic") or "").upper(); ops=e.get("operands") or ""
        if pc: nodes[pc]+=1
        if m in CALL_MNEMONICS and pc:
            tgt=_operand_target(ops)
            if tgt:
                edges[(pc,tgt)]+=1; calls.append({"caller":pc,"callee":tgt,"line":e.get("line"),"evidence":"direct call operand"})
            else:
                calls.append({"caller":pc,"callee":None,"line":e.get("line"),"evidence":"indirect/unresolved call"})
        if m in RETURN_MNEMONICS: returns+=1
    incoming=Counter(); outgoing=Counter()
    for (a,b),c in edges.items(): outgoing[a]+=c; incoming[b]+=c
    routines=[]
    for pc,count in nodes.most_common():
        if incoming[pc] or outgoing[pc]:
            routines.append({"pc":pc,"executions":count,"incoming_calls":incoming[pc],"outgoing_calls":outgoing[pc],"label":f"Routine_{pc}","status":"candidate"})
    result={"tool":"ROMancer","feature":"v12 dynamic call graph","trace":trace,"node_count":len(nodes),"direct_call_edge_count":len(edges),
            "return_instruction_count":returns,"calls":calls[:1000],"routines":routines[:1000],
            "limitations":["Only direct call operands visible in the normalized trace are resolved.","Tail calls, indirect calls and bank-dependent targets require debugger/static corroboration."]}
    if out: write_json(out,result)
    return result


def infer_record_schema(observations:str|list[dict[str,Any]], out:str|None=None)->dict[str,Any]:
    """Infer a candidate fixed-stride record schema from labelled observations.

    Input records: {"record":0,"offset":0,"width":2,"value":300,"label":"hp"}.
    Multiple independent records are required before a field is promoted from one-off.
    """
    obs=json.loads(Path(observations).read_text()) if isinstance(observations,str) else observations
    if isinstance(obs,dict): obs=obs.get("observations",[])
    by_field=defaultdict(list)
    for o in obs:
        key=(int(o["offset"]),int(o.get("width",1)),str(o.get("endian","little")))
        by_field[key].append(o)
    fields=[]
    for (off,width,endian),rows in sorted(by_field.items()):
        labels=Counter(str(r.get("label","unknown")) for r in rows)
        records={r.get("record") for r in rows}
        top,n=labels.most_common(1)[0]
        status="verified_observation_pattern" if len(records)>=3 and n==len(rows) and top!="unknown" else "candidate"
        fields.append({"offset":off,"width":width,"endian":endian,"candidate_name":top,"observation_count":len(rows),"distinct_records":len(records),"status":status})
    stride=max((f["offset"]+f["width"] for f in fields),default=0)
    result={"tool":"ROMancer","feature":"v12 record schema inference","candidate_stride_min":stride,"fields":fields,
            "policy":"Labels summarize supplied/observed correlations. They are not proof of all records or full structure size."}
    if out: write_json(out,result)
    return result


def learn_event_opcodes(observations:str|list[dict[str,Any]], out:str|None=None)->dict[str,Any]:
    """Correlate event opcode bytes with observed semantic effects.

    Input: {"opcode":"4B","effect":"show_dialogue","context":"..."}
    """
    obs=json.loads(Path(observations).read_text()) if isinstance(observations,str) else observations
    if isinstance(obs,dict): obs=obs.get("observations",[])
    per=defaultdict(list)
    for o in obs: per[str(o["opcode"]).upper().replace("0X","")].append(o)
    learned=[]
    for op,rows in sorted(per.items()):
        eff=Counter(str(r.get("effect","unknown")) for r in rows)
        top,n=eff.most_common(1)[0]
        conflicting=len(eff)>1
        status="high_confidence" if len(rows)>=3 and n==len(rows) and top!="unknown" else ("contradicted" if conflicting and n<len(rows) else "plausible")
        learned.append({"opcode":op,"candidate_effect":top,"observations":len(rows),"effects":dict(eff),"status":status})
    result={"tool":"ROMancer","feature":"v12 event opcode learner","opcodes":learned,
            "policy":"Runtime correlation generates semantic candidates; exact operand length/control flow still requires bytecode-specific verification."}
    if out: write_json(out,result)
    return result


def architecture_reference(manifest:str, out:str|None=None)->dict[str,Any]:
    m=json.loads(Path(manifest).read_text())
    systems=[]
    for section in ("engines","structures","routines","events","assets","memory","maps"):
        vals=m.get(section,[])
        systems.append({"section":section,"count":len(vals) if isinstance(vals,list) else len(vals or {}),"items":vals})
    result={"tool":"ROMancer","feature":"v12 technical reference","game":m.get("game",{}),"sections":systems,
            "evidence_policy":m.get("evidence_policy","Every semantic label should retain its evidence status and source ROM hash.")}
    if out: write_json(out,result)
    return result


def ghidra_export(manifest:str, out_dir:str)->dict[str,Any]:
    m=json.loads(Path(manifest).read_text()); root=Path(out_dir); root.mkdir(parents=True,exist_ok=True)
    syms=[]
    for r in m.get("routines",[]):
        if r.get("pc") and r.get("name"): syms.append((r["pc"],r["name"],r.get("status","candidate")))
    csv=root/"symbols.csv"; csv.write_text("address,name,status\n"+"\n".join(f"{a},{n},{s}" for a,n,s in syms)+("\n" if syms else ""),encoding="utf-8")
    args=root/"analyzeHeadless.args.txt"
    args.write_text("# ROMancer v12 Ghidra handoff\n# Supply Ghidra install/project paths and the legally supplied binary.\n# Import symbols.csv with a project-specific post-script.\n",encoding="utf-8")
    note=root/"README.txt"; note.write_text("ROMancer does not bundle Ghidra. This handoff exports evidence-scoped symbols for a user-installed Ghidra headless workflow.\n",encoding="utf-8")
    return {"tool":"ROMancer","feature":"v12 Ghidra handoff","out_dir":str(root),"symbol_count":len(syms),"files":[str(csv),str(args),str(note)]}
