from __future__ import annotations

"""ROMancer v10 autonomous ROM engineering orchestration layer."""

import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path
from typing import Any

from .debug_adapter_v10 import list_debug_backends, debug_backend_profile, debugger_plan, MockDebugAdapter
from .causal_v10 import trace_writers, causal_slice, causal_report
from .patch_ledger_v10 import ledger_add, ledger_check, free_space_scan, free_space_attest
from .bisect_v10 import diff_hunks, ddmin, patch_bisect
from .minimize_v10 import minimize_sequence, testcase_minimize
from .repair_v10 import parameter_repair
from .coverage_v10 import coverage_report
from .certify_v10 import certify
from .util import write_json

VERSION="10.0.0"


def add_v10_parsers(sub)->None:
    s=sub.add_parser("debug-backends",help="[v10] List capability-negotiated deep-debugger backend profiles")
    s.add_argument("name",nargs="?"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("debug-plan",help="[v10] Build a truthful backend-specific breakpoint/watchpoint integration plan")
    s.add_argument("--backend",required=True); s.add_argument("--addr",required=True); s.add_argument("--access",choices=["read","write","execute"],default="write"); s.add_argument("--goal",default=""); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("causal-writers",help="[v10] Identify observed trace instructions that wrote a target address")
    s.add_argument("trace"); s.add_argument("--addr",required=True); s.add_argument("--format",default="auto"); s.add_argument("--limit",type=int,default=100); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("causal-slice",help="[v10] Build an evidence-scoped offline backward slice around target writes")
    s.add_argument("trace"); s.add_argument("--addr",required=True); s.add_argument("--format",default="auto"); s.add_argument("--before",type=int,default=80); s.add_argument("--after",type=int,default=12); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("diagnose-cause",help="[v10] Produce a causal diagnosis bundle for a symptom and verified/candidate target address")
    s.add_argument("--symptom",required=True); s.add_argument("--trace",required=True); s.add_argument("--addr",required=True); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("patch-ledger",help="[v10] Maintain non-overlapping ownership records for ROM allocations")
    s.add_argument("action",choices=["add","check"]); s.add_argument("--ledger",required=True); s.add_argument("--start"); s.add_argument("--end"); s.add_argument("--owner"); s.add_argument("--purpose",default=""); s.add_argument("--introduced",default=""); s.add_argument("--source",default=""); s.add_argument("--json",action="store_true")

    s=sub.add_parser("free-space",help="[v10] Scan or attest conservative free-space evidence; fill bytes alone remain candidates")
    s.add_argument("action",choices=["scan","attest"]); s.add_argument("--rom"); s.add_argument("--ledger"); s.add_argument("--start"); s.add_argument("--end"); s.add_argument("--min-run",type=int,default=256); s.add_argument("--evidence",action="append",default=[]); s.add_argument("--status",default="high_confidence_candidate"); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("patch-bisect",help="[v10] Delta-debug changed ROM hunks against a reproducibility oracle")
    s.add_argument("--original",required=True); s.add_argument("--candidate",required=True); s.add_argument("--oracle",required=True,help="Command template containing {rom}; exit 1=reproduces defect, 0=does not"); s.add_argument("--merge-gap",type=int,default=0); s.add_argument("--timeout",type=int,default=60); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("testcase-minimize",help="[v10] Delta-minimize steps[] in a reproducer JSON using an oracle")
    s.add_argument("--case",required=True); s.add_argument("--oracle",required=True,help="Command template containing {case}; exit 1=reproduces defect, 0=does not"); s.add_argument("--timeout",type=int,default=60); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("repair-search",help="[v10] Evaluate bounded parameter repair candidates against a local oracle")
    s.add_argument("--rom",required=True); s.add_argument("--offset",required=True); s.add_argument("--values",required=True,help="Comma-separated integers/hex values"); s.add_argument("--oracle",required=True,help="Command template containing {rom}; exit 0=passes local defect oracle"); s.add_argument("--width",type=int,default=1); s.add_argument("--endian",choices=["little","big"],default="little"); s.add_argument("--expected-before"); s.add_argument("--timeout",type=int,default=60); s.add_argument("--out-dir",default="repair_candidates"); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("behavior-coverage",help="[v10] Compute game-behavior/content coverage from a known/hit/excluded manifest")
    s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("certify-v10",help="[v10] Evaluate explicit release gates and block certification on required failures")
    s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("v10-self-test",help="[v10] Run deterministic causal-debug, bisection, ownership, minimization, repair, coverage, and certification tests")
    s.add_argument("--out"); s.add_argument("--json",action="store_true")


def _emit_to_out(result:dict[str,Any],out:str|None)->dict[str,Any]:
    if out: write_json(out,result)
    return result


def _test_debug_api()->dict[str,Any]:
    p=[
        {"pc":0x1000,"instruction":"LDA #$05","a":5},
        {"pc":0x1002,"instruction":"STA $2000","write":(0x2000,5)},
        {"pc":0x1005,"instruction":"RTS"},
    ]; a=MockDebugAdapter(p); a.set_write_watchpoint(0x2000); stop=a.run_until_stop()
    return {"name":"debug adapter/watchpoint","ok":bool(stop.get("watchpoint_hit")) and a.read_memory(0x2000)==b"\x05","detail":stop}


def _test_bisect()->dict[str,Any]:
    a=bytes([0]*24); b=bytearray(a); b[2]=1; b[10]=7; b[18]=9; b=bytes(b); h=diff_hunks(a,b)
    bad_id=next(x["id"] for x in h if x["start"]==10)
    r=ddmin(h,lambda selected: bad_id in selected)
    return {"name":"patch delta bisection","ok":r.get("ok") and r.get("selected")==[bad_id],"detail":r}


def _test_minimize()->dict[str,Any]:
    steps=["up","left","A","right","B","down"]
    r=minimize_sequence(steps,lambda x:"A" in x and "B" in x)
    return {"name":"testcase minimization","ok":r.get("ok") and set(r.get("steps",[]))=={"A","B"},"detail":r}


def _test_ledger(td:Path)->dict[str,Any]:
    p=td/"ledger.json"; a=ledger_add(str(p),"0x100","0x1ff","mockery","handler"); b=ledger_add(str(p),"0x180","0x220","portrait","data"); c=ledger_check(str(p))
    return {"name":"patch ownership ledger","ok":a.get("ok") and not b.get("ok") and c.get("ok"),"detail":{"first":a,"conflict":b,"check":c}}


def _test_repair(td:Path)->dict[str,Any]:
    rom=td/"repair.bin"; rom.write_bytes(bytes([0,1,2,3,4]))
    oracle=td/"repair_oracle.py"; oracle.write_text("import sys\nb=open(sys.argv[1],'rb').read()\nsys.exit(0 if b[2]==5 else 1)\n",encoding="utf-8")
    r=parameter_repair(str(rom),"2","4,5,6",[sys.executable,str(oracle),"{rom}"],out_dir=str(td/"candidates"))
    return {"name":"bounded parameter repair","ok":r.get("status")=="verified_unique_candidate" and r.get("recommended",{}).get("value_int")==5,"detail":{"status":r.get("status"),"passing":r.get("passing_count")}}



def _test_causal_trace(td:Path)->dict[str,Any]:
    trace=td/"cause.log"
    trace.write_text(
        "C2:1000 LDA #$05    A:0005 X:0000\n"
        "C2:1003 STA $2000    A:0005 X:0000\n"
        "C2:1006 RTS          A:0005 X:0000\n",encoding="utf-8")
    w=trace_writers(str(trace),"2000",trace_format="bsnes-plus")
    c=causal_slice(str(trace),"2000",trace_format="bsnes-plus",before=4,after=1)
    return {"name":"offline causal writer/slice","ok":w.get("writer_count")==1 and c.get("slice_count")==1 and str(c["slices"][0]["writer"].get("pc")).replace(":","")=="C21003","detail":{"writers":w.get("writers"),"slice_count":c.get("slice_count")}}


def _test_cli_bisect(td:Path)->dict[str,Any]:
    original=td/"base.bin"; candidate=td/"bad.bin"
    a=bytearray([0]*32); b=bytearray(a); b[3]=1; b[11]=0x7E; b[21]=2
    original.write_bytes(a); candidate.write_bytes(b)
    oracle=td/"bisect_oracle.py"
    oracle.write_text("import sys\nb=open(sys.argv[1],'rb').read()\nsys.exit(1 if len(b)>11 and b[11]==0x7e else 0)\n",encoding="utf-8")
    r=patch_bisect(str(original),str(candidate),[sys.executable,str(oracle),"{rom}"])
    selected=r.get("selected_hunks",[])
    return {"name":"end-to-end patch bisection oracle","ok":len(selected)==1 and selected[0].get("start")==11,"detail":{"hunk_count":r.get("hunk_count"),"selected":selected,"tests":r.get("result",{}).get("tests")}}

def _test_coverage_cert(td:Path)->dict[str,Any]:
    cov=td/"coverage.json"; cov.write_text(json.dumps({"categories":{"maps":{"known":[1,2,3],"hit":[1,2,3]},"bosses":{"known":["a"],"hit":["a"]}}},indent=2)+"\n",encoding="utf-8")
    cv=coverage_report(str(cov)); gate=td/"gate.json"; gate.write_text(json.dumps({"ok":True})+"\n",encoding="utf-8"); manifest=td/"cert.json"; manifest.write_text(json.dumps({"gates":[{"name":"fixture","kind":"json","path":str(gate)},{"name":"coverage","kind":"coverage","path":str(cov),"minimum":100}]},indent=2)+"\n",encoding="utf-8"); cr=certify(str(manifest))
    return {"name":"coverage and certification","ok":cv["overall"]["coverage_percent"]==100.0 and cr.get("release_status")=="GATES_PASSED","detail":{"coverage":cv["overall"],"certification":cr.get("release_status")}}


def _test_free_space(td:Path)->dict[str,Any]:
    rom=td/"space.bin"; rom.write_bytes(b"A"*64+b"\xff"*512+b"B"*64); r=free_space_scan(str(rom),min_run=256)
    return {"name":"conservative free-space discovery","ok":len(r.get("candidates",[]))==1 and r["candidates"][0]["status"]=="likely_empty_pattern_only","detail":r["candidates"][:1]}


def v10_self_test(out:str|None=None)->dict[str,Any]:
    tests=[_test_debug_api(),_test_bisect(),_test_minimize()]
    with tempfile.TemporaryDirectory(prefix="romancer_v10_test_") as td0:
        td=Path(td0); tests.extend([_test_ledger(td),_test_causal_trace(td),_test_cli_bisect(td),_test_repair(td),_test_coverage_cert(td),_test_free_space(td)])
    ok=all(bool(t.get("ok")) for t in tests)
    r={"tool":"ROMancer","version":VERSION,"feature":"v10 self-test","ok":ok,"tests":tests,"notes":["All v10 self-tests use synthetic fixtures. They prove ROMancer orchestration logic, not compatibility with an unconfigured external debugger.","Backend profiles distinguish documented emulator capability from live automation actually configured in ROMancer."]}
    if out: write_json(out,r)
    return r


def dispatch_v10(args)->tuple[bool,Any]:
    c=getattr(args,"cmd",None)
    if c=="debug-backends": return True,(debug_backend_profile(args.name) if args.name else list_debug_backends())
    if c=="debug-plan": return True,_emit_to_out(debugger_plan(args.backend,address=args.addr,access=args.access,goal=args.goal),args.out)
    if c=="causal-writers": return True,_emit_to_out(trace_writers(args.trace,args.addr,trace_format=args.format,limit=args.limit),args.out)
    if c=="causal-slice": return True,causal_slice(args.trace,args.addr,trace_format=args.format,before=args.before,after=args.after,out=args.out)
    if c=="diagnose-cause": return True,causal_report(args.symptom,args.trace,args.addr,args.out)
    if c=="patch-ledger":
        if args.action=="check": return True,ledger_check(args.ledger)
        if not all([args.start,args.end,args.owner]): raise ValueError("patch-ledger add requires --start --end --owner")
        return True,ledger_add(args.ledger,args.start,args.end,args.owner,args.purpose,args.introduced,args.source)
    if c=="free-space":
        if args.action=="scan":
            if not args.rom: raise ValueError("free-space scan requires --rom")
            return True,free_space_scan(args.rom,min_run=args.min_run,out=args.out)
        if not all([args.ledger,args.start,args.end]) or not args.evidence: raise ValueError("free-space attest requires --ledger --start --end and at least one --evidence")
        return True,free_space_attest(args.ledger,args.start,args.end,args.evidence,args.status)
    if c=="patch-bisect": return True,patch_bisect(args.original,args.candidate,args.oracle,merge_gap=args.merge_gap,timeout=args.timeout,out=args.out)
    if c=="testcase-minimize": return True,testcase_minimize(args.case,args.oracle,timeout=args.timeout,out=args.out)
    if c=="repair-search": return True,parameter_repair(args.rom,args.offset,args.values,args.oracle,width=args.width,endian=args.endian,expected_before=args.expected_before,timeout=args.timeout,out_dir=args.out_dir,out=args.out)
    if c=="behavior-coverage": return True,coverage_report(args.manifest,args.out)
    if c=="certify-v10": return True,certify(args.manifest,args.out)
    if c=="v10-self-test": return True,v10_self_test(args.out)
    return False,None
