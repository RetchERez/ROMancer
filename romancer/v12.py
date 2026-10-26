from __future__ import annotations
import json, tempfile
from pathlib import Path

from .util import write_json
from .architecture_v12 import reconstruct_call_graph, infer_record_schema, learn_event_opcodes, architecture_reference, ghidra_export

VERSION="12.0.0"

def add_v12_parsers(sub):
    s=sub.add_parser("architecture-callgraph",help="[v12] Reconstruct direct dynamic call relationships from a trace")
    s.add_argument("trace"); s.add_argument("--format",default="auto"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("architecture-schema",help="[v12] Infer candidate fixed-record fields from repeated labelled observations")
    s.add_argument("observations"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("event-opcodes",help="[v12] Learn candidate event opcode semantics from repeated observations")
    s.add_argument("observations"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("architecture-reference",help="[v12] Build an evidence-scoped technical reference from an architecture manifest")
    s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("ghidra-export",help="[v12] Export verified/candidate symbols for a user-installed Ghidra headless workflow")
    s.add_argument("manifest"); s.add_argument("--out-dir",required=True); s.add_argument("--json",action="store_true")
    s=sub.add_parser("v12-self-test",help="[v12] Test architecture reconstruction primitives")
    s.add_argument("--out"); s.add_argument("--json",action="store_true")


def v12_self_test(out=None):
    tests=[]
    with tempfile.TemporaryDirectory(prefix="romancer_v12_") as td:
        td=Path(td)
        tr=td/"trace.log"; tr.write_text("C2:1000 JSR $2000    A:0000\nC2:1003 NOP          A:0000\nC2:2000 RTS          A:0000\n",encoding="utf-8")
        cg=reconstruct_call_graph(str(tr),"bsnes-plus")
        tests.append({"name":"dynamic direct call graph","ok":cg.get("direct_call_edge_count")==1 and cg["calls"][0]["callee"]=="2000","detail":cg.get("calls")})
        obs=[{"record":i,"offset":0,"width":2,"label":"hp","value":100+i} for i in range(3)]+[{"record":i,"offset":2,"width":1,"label":"attack","value":10+i} for i in range(3)]
        sc=infer_record_schema(obs); tests.append({"name":"record schema inference","ok":len(sc["fields"])==2 and all(f["status"]=="verified_observation_pattern" for f in sc["fields"])})
        ev=learn_event_opcodes([{"opcode":"4B","effect":"show_dialogue"} for _ in range(3)]+[{"opcode":"D0","effect":"set_flag"} for _ in range(3)])
        tests.append({"name":"event opcode learning","ok":all(x["status"]=="high_confidence" for x in ev["opcodes"])})
        mf=td/"arch.json"; mf.write_text(json.dumps({"game":{"title":"Fixture"},"routines":[{"pc":"C21000","name":"Main","status":"verified"}],"structures":[],"events":[]}),encoding="utf-8")
        ge=ghidra_export(str(mf),str(td/"ghidra")); tests.append({"name":"Ghidra evidence handoff","ok":ge["symbol_count"]==1 and Path(ge["files"][0]).exists()})
    ok=all(t["ok"] for t in tests); r={"tool":"ROMancer","version":VERSION,"feature":"v12 self-test","ok":ok,"tests":tests}
    if out: write_json(out,r)
    return r


def dispatch_v12(args):
    c=getattr(args,"cmd","")
    if c=="architecture-callgraph": return True,reconstruct_call_graph(args.trace,args.format,args.out)
    if c=="architecture-schema": return True,infer_record_schema(args.observations,args.out)
    if c=="event-opcodes": return True,learn_event_opcodes(args.observations,args.out)
    if c=="architecture-reference": return True,architecture_reference(args.manifest,args.out)
    if c=="ghidra-export": return True,ghidra_export(args.manifest,args.out_dir)
    if c=="v12-self-test": return True,v12_self_test(args.out)
    return False,None
