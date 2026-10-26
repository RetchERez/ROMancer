from __future__ import annotations
import json, tempfile, shutil
from pathlib import Path

from .util import write_json
from .repair_engine_v13 import classify_repair, semantic_field_patch, semantic_merge, minimize_repair, assembly_repair_recipe

VERSION="13.0.0"

def add_v13_parsers(sub):
    s=sub.add_parser("repair-classify",help="[v13] Select the lowest-risk repair class supported by an evidence manifest"); s.add_argument("evidence"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("semantic-patch",help="[v13] Patch a verified fixed-record field semantically"); s.add_argument("rom"); s.add_argument("--record-base",required=True); s.add_argument("--stride",type=int,required=True); s.add_argument("--record-index",type=int,required=True); s.add_argument("--field-offset",type=int,required=True); s.add_argument("--value",type=lambda x:int(x,0),required=True); s.add_argument("--width",type=int,default=1); s.add_argument("--endian",choices=["little","big"],default="little"); s.add_argument("--expected-before",type=lambda x:int(x,0)); s.add_argument("--out-rom"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("semantic-merge",help="[v13] Merge semantic patch manifests, rejecting non-identical overlaps"); s.add_argument("manifests",nargs="+"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("repair-minimize",help="[v13] Minimize a successful same-size repair using a behavioral oracle"); s.add_argument("--original",required=True); s.add_argument("--candidate",required=True); s.add_argument("--oracle",required=True); s.add_argument("--timeout",type=int,default=60); s.add_argument("--out-rom"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("assembly-recipe",help="[v13] Validate an evidence-scoped assembly repair recipe without pretending an assembler ran"); s.add_argument("recipe"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("v13-self-test",help="[v13] Test semantic repair, merge conflict, classification, and repair minimization"); s.add_argument("--out"); s.add_argument("--json",action="store_true")

def v13_self_test(out=None):
    tests=[]
    with tempfile.TemporaryDirectory(prefix="romancer_v13_") as td:
        td=Path(td); rom=td/"base.bin"; rom.write_bytes(bytes(range(32)))
        sp=semantic_field_patch(str(rom),record_base=0,stride=4,record_index=2,field_offset=1,value=99,expected_before=9,out_rom=str(td/"field.bin"))
        tests.append({"name":"semantic fixed-record repair","ok":sp.get("ok") and Path(sp["out"]).read_bytes()[9]==99})
        e=classify_repair({"field":"enemy_x","branch":"later possibility"}); tests.append({"name":"lowest-risk repair classification","ok":e["repair_class"]=="data"})
        m1=td/"m1.json"; m2=td/"m2.json"; m1.write_text(json.dumps({"operations":[{"offset":"0x10","length":1,"bytes":[1]}]})); m2.write_text(json.dumps({"operations":[{"offset":"0x10","length":1,"bytes":[2]}]})); mg=semantic_merge([str(m1),str(m2)])
        tests.append({"name":"semantic conflict refusal","ok":not mg["ok"] and len(mg["conflicts"])==1})
        cand=td/"candidate.bin"; b=bytearray(rom.read_bytes()); b[3]=55; b[10]=77; b[20]=88; cand.write_bytes(b)
        oracle=td/"oracle.py"; oracle.write_text("import sys\nb=open(sys.argv[1],'rb').read()\nsys.exit(0 if b[10]==77 else 1)\n")
        py=shutil.which("python3") or "python3"; mn=minimize_repair(str(rom),str(cand),f"{py} {oracle} {{rom}}",out_rom=str(td/"min.bin"))
        tests.append({"name":"repair minimization","ok":mn.get("ok") and mn.get("minimal_hunks")==1 and Path(mn["out"]).read_bytes()[10]==77})
    ok=all(t["ok"] for t in tests); r={"tool":"ROMancer","version":VERSION,"feature":"v13 self-test","ok":ok,"tests":tests}
    if out: write_json(out,r)
    return r

def dispatch_v13(args):
    c=getattr(args,"cmd","")
    if c=="repair-classify": return True,classify_repair(args.evidence,args.out)
    if c=="semantic-patch": return True,semantic_field_patch(args.rom,record_base=args.record_base,stride=args.stride,record_index=args.record_index,field_offset=args.field_offset,value=args.value,width=args.width,endian=args.endian,expected_before=args.expected_before,out_rom=args.out_rom)
    if c=="semantic-merge": return True,semantic_merge(args.manifests,args.out)
    if c=="repair-minimize": return True,minimize_repair(args.original,args.candidate,args.oracle,timeout=args.timeout,out_rom=args.out_rom)
    if c=="assembly-recipe": return True,assembly_repair_recipe(args.recipe,args.out)
    if c=="v13-self-test": return True,v13_self_test(args.out)
    return False,None
