from __future__ import annotations
import json, tempfile
from pathlib import Path
from .util import write_json
from .knowledge_v15 import inherit_knowledge, generate_profile, self_evaluate, knowledge_vault, platform_sdk_check, project_plan

VERSION="15.0.0"


def add_v15_parsers(sub):
    s=sub.add_parser("knowledge-inherit",help="[v15] Inherit cross-project knowledge as candidates unless target revalidation exists"); s.add_argument("source"); s.add_argument("target"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("profile-generate",help="[v15] Generate a conservative game profile from structured observations"); s.add_argument("observations"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("self-evaluate",help="[v15] Block or permit autonomous action based on declared evidence/capabilities"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("knowledge-vault",help="[v15] Index portable project knowledge while skipping ROM/disc/save content"); s.add_argument("root"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("platform-sdk",help="[v15] Check a modular platform pack against ROMancer SDK contracts"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("project-plan",help="[v15] Decompose a ROM engineering request into evidence-scoped tasks"); s.add_argument("request"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("v15-self-test",help="[v15] Test knowledge inheritance, profile generation, self-evaluation, vault hygiene and platform SDK checks"); s.add_argument("--out"); s.add_argument("--json",action="store_true")


def v15_self_test(out=None):
    tests=[]
    with tempfile.TemporaryDirectory(prefix="romancer_v15_") as td0:
        td=Path(td0)
        source=td/"source.json"; target=td/"target.json"
        source.write_text(json.dumps({"game":{"title":"Fixture","rom_sha256":"aaa"},"facts":[{"id":"battle_main","claim":"Routine handles battle","status":"VERIFIED","domain":"routine"}]}))
        target.write_text(json.dumps({"game":{"title":"Fixture Hack","rom_sha256":"bbb"},"revalidated_fact_ids":[]}))
        inh=inherit_knowledge(str(source),str(target))
        tests.append({"name":"cross-ROM knowledge inherited as candidate","ok":inh["facts"][0]["target_status"]=="INHERITED_CANDIDATE"})
        obs=td/"obs.json"; obs.write_text(json.dumps({"observations":[
            {"kind":"control","state":"exploration","semantic":"interact","input":"A","status":"VERIFIED"},
            {"kind":"state_transition","from":"EXPLORATION","to":"DIALOGUE","trigger":"A","status":"VERIFIED"},
            {"kind":"resource","name":"HP","status":"VERIFIED"},
            {"kind":"resource","name":"currency","status":"VERIFIED"},
            {"kind":"save_system","system":"sram","status":"VERIFIED"},
            {"kind":"movement","model":"4-direction","directions":4,"status":"VERIFIED"}
        ]}))
        prof=generate_profile(str(obs)); tests.append({"name":"automatic profile generation","ok":"EXPLORATION" in prof["profile"]["known_states"] and "HP" in prof["profile"]["resources"]})
        ev=td/"eval.json"; ev.write_text(json.dumps({"required_capabilities":[{"name":"live_debug","available":False}],"required_facts":[{"id":"x","claim":"unknown opcode","status":"PLAUSIBLE"}],"risks":[]}))
        se=self_evaluate(str(ev)); tests.append({"name":"self-evaluation blocks missing evidence","ok":se["mode"]=="BLOCK_AUTONOMOUS_ACTION" and se["blocker_count"]==2})
        vault=td/"vault"; vault.mkdir(); (vault/"fact.json").write_text(json.dumps({"tool":"ROMancer","feature":"fixture"})); (vault/"bad.sfc").write_bytes(b"not real but should be skipped")
        vi=knowledge_vault(str(vault)); tests.append({"name":"knowledge vault skips content suffixes","ok":vi["entry_count"]==1 and vi["skipped_content_count"]==1})
        sdk=td/"sdk.json"; sdk.write_text(json.dumps({"platform":"fixture","modules":{"identity":"ok","address_translation":"ok","memory_regions":"ok","input":"ok","graphics":"partial","audio":"ok","debug_adapter":"ok","assembler":"missing","disassembler":"ok"}}))
        ps=platform_sdk_check(str(sdk)); tests.append({"name":"platform SDK reports missing module","ok":not ps["ok"] and any(x["module"]=="assembler" and x["status"]=="missing" for x in ps["modules"])})
        plan=project_plan("Give Kefka a Mockery command and portrait fix"); tests.append({"name":"project planning decomposes feature request","ok":plan["task_count"]>=7 and any("command" in x["task"].lower() for x in plan["tasks"]) and any("graphics" in x["task"].lower() for x in plan["tasks"])})
    ok=all(t["ok"] for t in tests); r={"tool":"ROMancer","version":VERSION,"feature":"v15 self-test","ok":ok,"tests":tests}
    if out: write_json(out,r)
    return r


def dispatch_v15(args):
    c=getattr(args,"cmd","")
    if c=="knowledge-inherit": return True,inherit_knowledge(args.source,args.target,args.out)
    if c=="profile-generate": return True,generate_profile(args.observations,args.out)
    if c=="self-evaluate": return True,self_evaluate(args.manifest,args.out)
    if c=="knowledge-vault": return True,knowledge_vault(args.root,args.out)
    if c=="platform-sdk": return True,platform_sdk_check(args.manifest,args.out)
    if c=="project-plan": return True,project_plan(args.request,args.out)
    if c=="v15-self-test": return True,v15_self_test(args.out)
    return False,None
