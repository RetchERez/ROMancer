from __future__ import annotations

"""ROMancer v13 semantic, minimal, evidence-scoped repair engineering."""

import json, subprocess, tempfile
from pathlib import Path
from typing import Any
from .util import write_json, parse_int
from .bisect_v10 import diff_hunks, ddmin

RISK_ORDER={"data":1,"pointer":2,"event":3,"graphics":3,"control_flow":4,"assembly":5,"relocation":5,"unknown":99}


def classify_repair(evidence:str|dict[str,Any], out:str|None=None)->dict[str,Any]:
    e=json.loads(Path(evidence).read_text()) if isinstance(evidence,str) else evidence
    hints=[]
    if e.get("table") or e.get("field") or e.get("parameter"): hints.append(("data","Verified/candidate structured field or parameter identified."))
    if e.get("pointer_target") or e.get("bad_pointer"): hints.append(("pointer","Pointer provenance is implicated."))
    if e.get("event_opcode") or e.get("event_flag"): hints.append(("event","Event bytecode/flag evidence is implicated."))
    if e.get("asset") or e.get("tilemap") or e.get("palette"): hints.append(("graphics","Graphics asset/pipeline evidence is implicated."))
    if e.get("branch") or e.get("condition"): hints.append(("control_flow","Branch/condition evidence is implicated."))
    if e.get("missing_logic") or e.get("new_code_required"): hints.append(("assembly","Existing structured data/control flow is insufficient according to supplied evidence."))
    if e.get("needs_space") or e.get("relocation"): hints.append(("relocation","Repair requires new storage/relocation."))
    if not hints: hints=[("unknown","Insufficient evidence to choose a repair class.")]
    hints.sort(key=lambda x:RISK_ORDER[x[0]])
    chosen=hints[0]
    r={"tool":"ROMancer","feature":"v13 repair classification","repair_class":chosen[0],"reason":chosen[1],"alternatives":[{"class":a,"reason":b} for a,b in hints[1:]],
       "policy":"Choose the lowest-risk repair class supported by evidence; do not escalate to code insertion when a data repair is sufficient."}
    if out: write_json(out,r)
    return r


def semantic_field_patch(rom:str, *, record_base:str|int, stride:int, record_index:int, field_offset:int,
                         value:int, width:int=1, endian:str="little", expected_before:int|None=None,
                         out_rom:str|None=None)->dict[str,Any]:
    data=bytearray(Path(rom).read_bytes()); base=parse_int(record_base) if isinstance(record_base,str) else int(record_base)
    off=base+int(stride)*int(record_index)+int(field_offset)
    if off<0 or off+width>len(data): raise ValueError("semantic field patch is outside ROM")
    before=int.from_bytes(data[off:off+width],endian)
    if expected_before is not None and before!=int(expected_before):
        return {"tool":"ROMancer","feature":"v13 semantic field patch","ok":False,"reason":"expected-before mismatch","offset":f"0x{off:X}","observed_before":before,"expected_before":int(expected_before)}
    data[off:off+width]=int(value).to_bytes(width,endian,signed=False)
    target=Path(out_rom) if out_rom else Path(rom).with_name(Path(rom).stem+".semantic_candidate"+Path(rom).suffix)
    target.write_bytes(data)
    return {"tool":"ROMancer","feature":"v13 semantic field patch","ok":True,"source":rom,"out":str(target),"record_base":f"0x{base:X}","stride":stride,"record_index":record_index,"field_offset":field_offset,"absolute_offset":f"0x{off:X}","before":before,"after":int(value),"width":width,"endian":endian}


def semantic_merge(manifests:list[str]|str, out:str|None=None)->dict[str,Any]:
    if isinstance(manifests,str): manifests=[x for x in manifests.split(",") if x]
    ops=[]
    for path in manifests:
        m=json.loads(Path(path).read_text());
        for op in m.get("operations",[]): ops.append({**op,"source_manifest":path})
    conflicts=[]; dedup=[]
    for i,a in enumerate(ops):
        ar=(int(a["offset"],0) if isinstance(a["offset"],str) else int(a["offset"]), int(a.get("length",len(a.get("bytes",[])) or 1)))
        a0,a1=ar[0],ar[0]+ar[1]
        duplicate=False
        for b in dedup:
            b0=int(b["offset"],0) if isinstance(b["offset"],str) else int(b["offset"]); b1=b0+int(b.get("length",len(b.get("bytes",[])) or 1))
            if max(a0,b0)<min(a1,b1):
                if a0==b0 and a1==b1 and a.get("bytes")==b.get("bytes"):
                    duplicate=True; break
                conflicts.append({"a":a,"b":b,"overlap":[max(a0,b0),min(a1,b1)]})
        if not duplicate: dedup.append(a)
    r={"tool":"ROMancer","feature":"v13 semantic patch merge","ok":not conflicts,"operation_count":len(dedup),"operations":dedup,"conflicts":conflicts,
       "policy":"Byte overlap is only auto-merged when the operations are identical. Semantic equivalence is not guessed."}
    if out: write_json(out,r)
    return r


def minimize_repair(original:str,candidate:str,oracle:str,*,timeout:int=60,out_rom:str|None=None)->dict[str,Any]:
    a=Path(original).read_bytes(); b=Path(candidate).read_bytes()
    if len(a)!=len(b): return {"tool":"ROMancer","feature":"v13 repair minimization","ok":False,"reason":"length-changing repairs are not minimized by this byte-hunk path"}
    hunks=diff_hunks(a,b)
    tests=0
    def fails(selected):
        nonlocal tests
        tests+=1; data=bytearray(a)
        for h in hunks:
            if h["id"] in selected:
                st=h["start"]; data[st:h["end"]+1]=bytes.fromhex(h["after"])
        with tempfile.TemporaryDirectory(prefix="romancer_v13_min_") as td:
            p=Path(td)/"candidate.bin"; p.write_bytes(data)
            cmd=oracle.format(rom=str(p)); rc=subprocess.run(cmd,shell=True,timeout=timeout).returncode
            return rc==0
    ids=[h["id"] for h in hunks]
    if not fails(ids): return {"tool":"ROMancer","feature":"v13 repair minimization","ok":False,"reason":"full candidate does not pass oracle"}
    # ddmin expects predicate True when condition persists.
    result=ddmin(hunks,lambda selected:fails(selected))
    selected=set(result.get("selected",[])); data=bytearray(a)
    kept=[]
    for h in hunks:
        if h["id"] in selected:
            data[h["start"]:h["end"]+1]=bytes.fromhex(h["after"]); kept.append(h)
    target=Path(out_rom) if out_rom else Path(candidate).with_name(Path(candidate).stem+".minimal"+Path(candidate).suffix)
    target.write_bytes(data)
    return {"tool":"ROMancer","feature":"v13 repair minimization","ok":True,"original_hunks":len(hunks),"minimal_hunks":len(kept),"selected_hunks":kept,"oracle_tests":tests,"out":str(target),"minimality":"1-minimal under supplied hunk partition/oracle"}


def assembly_repair_recipe(recipe:str,out:str|None=None)->dict[str,Any]:
    r=json.loads(Path(recipe).read_text())
    required=["system","offset","expected_before","replacement","reason"]
    missing=[k for k in required if k not in r]
    status="ready_for_external_assembler_or_byte_validation" if not missing else "incomplete"
    result={"tool":"ROMancer","feature":"v13 assembly repair recipe","status":status,"missing":missing,"recipe":r,
            "policy":"v13 validates evidence and byte contracts but does not invent assembly or claim an external assembler ran unless an assembler result is supplied."}
    if out: write_json(out,result)
    return result
