from __future__ import annotations

"""ROMancer v9 autonomous game-understanding and play-intelligence CLI layer."""

import json, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from typing import Any

from .autonomous_play import runtime_autoplay
from .gameplay_beliefs import BeliefLedger, BeliefStatus
from .gameplay_failures import classify_failure
from .gameplay_genres import list_packs, load_pack, hypotheses
from .gameplay_objectives import extract_candidate_objective, compile_structured_objective, objective_information_gaps
from .gameplay_planner import CandidateAction, choose_action
from .gameplay_resources import ResourceLedger, choose_farm, farm_route_metrics, evaluate_purchase
from .gameplay_state import SessionState
from .util import write_json

VERSION="9.0.0"


def _load_json(path:str|Path)->Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _kv(items:list[str]|None)->dict[str,str]:
    out={}
    for item in items or []:
        if "=" not in item: raise ValueError(f"Expected KEY=VALUE, got {item!r}")
        k,v=item.split("=",1); out[k]=v
    return out


def add_v9_parsers(sub)->None:
    s=sub.add_parser("play-session",help="[v9] Initialize, inspect, or update the persistent universal game-session record")
    s.add_argument("action",choices=["init","show","validate"]); s.add_argument("--file",required=True); s.add_argument("--title"); s.add_argument("--platform"); s.add_argument("--version"); s.add_argument("--state",default="UNKNOWN"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("play-belief",help="[v9] Maintain evidence-scoped gameplay beliefs without promoting heuristics to facts")
    s.add_argument("action",choices=["add","hypothesize","contradict","list"]); s.add_argument("--ledger",required=True); s.add_argument("--claim"); s.add_argument("--context",default="global"); s.add_argument("--evidence"); s.add_argument("--source"); s.add_argument("--confidence",type=float,default=.35); s.add_argument("--json",action="store_true")

    s=sub.add_parser("play-objective",help="[v9] Compile an objective from structured evidence or make a conservative candidate from text")
    s.add_argument("action",choices=["extract","structured"]); s.add_argument("--text"); s.add_argument("--file"); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("play-failure",help="[v9] Classify a failed attempt before choosing practice, preparation, farming, navigation, or bug diagnosis")
    s.add_argument("--observation",required=True,help="JSON file containing explicit failure observations"); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("play-plan",help="[v9] Score candidate actions by progress, information gain, reversibility, confidence, resources, and risk")
    s.add_argument("--context",required=True,help="JSON with actions[] and optional beliefs"); s.add_argument("--mode",default="player",choices=["player","qa","explore","blind"]); s.add_argument("--uncertainty",type=float,default=.5); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("play-economy",help="[v9] Evaluate farming routes, resource shortfalls, or a purchase without aimless grinding")
    s.add_argument("action",choices=["ledger","farm","route","purchase"]); s.add_argument("--file",required=True); s.add_argument("--out"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("genre-pack",help="[v9] List/show genre hypothesis packs or emit candidate hypotheses for a state")
    s.add_argument("action",choices=["list","show","hypotheses"]); s.add_argument("name",nargs="?"); s.add_argument("--state"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("runtime-autoplay",help="[v9] Bounded evidence-first autonomous play using verified profile semantics, optional learned visual states, and save-state branching")
    s.add_argument("--core",required=True); s.add_argument("--game",required=True); s.add_argument("--profile"); s.add_argument("--states"); s.add_argument("--out-dir",required=True)
    s.add_argument("--mode",default="qa",choices=["player","qa","explore","blind"]); s.add_argument("--decisions",type=int,default=30); s.add_argument("--boot-frames",type=int,default=120); s.add_argument("--action-frames",type=int,default=1); s.add_argument("--settle-frames",type=int,default=5); s.add_argument("--memory-region",default="system_ram"); s.add_argument("--state-threshold",type=int,default=12)
    s.add_argument("--system-dir"); s.add_argument("--save-dir"); s.add_argument("--assets-dir"); s.add_argument("--core-option",action="append",default=[],metavar="KEY=VALUE"); s.add_argument("--json",action="store_true")

    s=sub.add_parser("v9-self-test",help="[v9] Run deterministic tests for beliefs, objectives, failure reasoning, planning, economics, genre packs, and autonomous runtime")
    s.add_argument("--out"); s.add_argument("--json",action="store_true")


def session_cmd(args)->dict[str,Any]:
    p=Path(args.file)
    if args.action=="init":
        s=SessionState(title=args.title,platform=args.platform,version=args.version,current_state=args.state); s.save(p)
        return {"ok":not s.validate(),"session":s.to_dict(),"issues":s.validate(),"file":str(p)}
    s=SessionState.load(p)
    return {"ok":not s.validate(),"session":s.to_dict(),"issues":s.validate(),"file":str(p)}


def belief_cmd(args)->dict[str,Any]:
    p=Path(args.ledger); ledger=BeliefLedger.load(p) if p.is_file() else BeliefLedger()
    if args.action=="add":
        if not args.claim or not args.evidence: raise ValueError("add requires --claim and --evidence")
        b=ledger.observe(args.claim,args.evidence,context=args.context,source=args.source,direct=True)
    elif args.action=="hypothesize":
        if not args.claim: raise ValueError("hypothesize requires --claim")
        b=ledger.hypothesize(args.claim,context=args.context,source=args.source or "heuristic",confidence=args.confidence)
    elif args.action=="contradict":
        if not args.claim or not args.evidence: raise ValueError("contradict requires --claim and --evidence")
        b=ledger.contradict(args.claim,args.evidence,context=args.context)
    else: b=None
    ledger.save(p)
    return {"ok":True,"changed":b.to_dict() if b else None,"groups":ledger.grouped(),"file":str(p)}


def objective_cmd(args)->dict[str,Any]:
    if args.action=="extract":
        text=args.text if args.text is not None else Path(args.file).read_text(encoding="utf-8") if args.file else ""
        r=extract_candidate_objective(text)
    else:
        if not args.file: raise ValueError("structured requires --file JSON")
        obj=compile_structured_objective(_load_json(args.file)); r={"objective":obj.__dict__,"gaps":objective_information_gaps(obj)}
    if args.out: write_json(args.out,r)
    return r


def plan_cmd(args)->dict[str,Any]:
    obj=_load_json(args.context); ledger=BeliefLedger.from_dict({"beliefs":obj.get("beliefs",[])})
    acts=[CandidateAction(**a) for a in obj.get("actions",[])]
    r=choose_action(acts,ledger,mode=args.mode,uncertainty=args.uncertainty)
    if args.out: write_json(args.out,r)
    return r


def economy_cmd(args)->dict[str,Any]:
    obj=_load_json(args.file)
    if args.action=="ledger": r=ResourceLedger(obj.get("current",{}),obj.get("targets",{}),obj.get("reserves",{})).report()
    elif args.action=="route": r=farm_route_metrics(obj,shortfall=obj.get("shortfall"))
    elif args.action=="farm": r=choose_farm(obj.get("routes",[]),shortfall=float(obj.get("shortfall",0)),progression_likely_to_cover=bool(obj.get("progression_likely_to_cover",False)))
    else: r=evaluate_purchase(obj.get("item",obj),current_currency=float(obj.get("current_currency",0)),reserve=float(obj.get("reserve",0)),bottleneck=obj.get("bottleneck"))
    if args.out: write_json(args.out,r)
    return r


def _test_beliefs()->bool:
    l=BeliefLedger(); l.hypothesize("A confirms",context="menu");
    if l.get("A confirms","menu").status != BeliefStatus.PLAUSIBLE: return False
    l.observe("A confirms","menu transition 3/3",context="menu",direct=True)
    if l.get("A confirms","menu").status != BeliefStatus.VERIFIED: return False
    l.contradict("A confirms","current ROM remaps A",context="menu")
    return l.get("A confirms","menu").status == BeliefStatus.CONTRADICTED


def _test_objectives()->bool:
    r=extract_candidate_objective("Take this letter to the guard at North Gate before sunset.")
    o=r["objective"]; return o["verb"] in {"deliver","obtain"} and r["status"]=="PLAUSIBLE"


def _test_failure()->bool:
    r=classify_failure({"missed_jump":True,"same_cause_failures":4}); return r["category"]=="EXECUTION" and r["adapt_strategy"]


def _test_planner()->bool:
    l=BeliefLedger(); acts=[CandidateAction("inspect",information_gain=.9,reversibility=1),CandidateAction("sell_unique",kind="sell",progress_value=.8,reversibility=.1)]
    r=choose_action(acts,l,uncertainty=.9); return r["selected"]["name"]=="inspect" and any(x["blocked"] for x in r["ranking"] if x["name"]=="sell_unique")


def _test_economy()->bool:
    r=choose_farm([{"name":"safe","reward":100,"minutes":1,"renewable":True,"success_rate":1},{"name":"bad","reward":300,"minutes":1,"renewable":True,"success_rate":.3,"failure_cost":500}],shortfall=450)
    return r["farm"] and r["selected"]["name"]=="safe" and r["selected"]["estimated_successful_equivalent_runs"]==5


def _test_genres()->bool:
    packs=list_packs(); return len(packs)>=10 and bool(hypotheses(load_pack("jrpg"),state="COMBAT"))


def _test_autoplay()->dict[str,Any]:
    gcc=shutil.which("gcc") or shutil.which("cc"); source=Path(__file__).resolve().parent.parent/"tests"/"mock_libretro.c"
    if not gcc: return {"name":"autonomous runtime","ok":True,"skipped":True,"detail":"gcc/cc not found"}
    try:
        temporary=tempfile.TemporaryDirectory(prefix="romancer_v9_auto_")
        try:
            td=Path(temporary.name); so=td/("mock_libretro.dll" if sys.platform=="win32" else "mock_libretro.so"); content=td/"fixture.bin"; content.write_bytes(b"ROMancer v9 fixture")
            cp=subprocess.run([gcc,"-shared","-fPIC","-O2",str(source),"-o",str(so)],capture_output=True,text=True,timeout=30)
            if cp.returncode: return {"name":"autonomous runtime","ok":False,"error":cp.stderr[-2000:]}
            if sys.platform=="win32":
                # Process ownership releases the test DLL before deleting it.
                bootstrap=("import json,sys;sys.path.insert(0,sys.argv[1]);"
                    "from romancer.autonomous_play import runtime_autoplay;"
                    "print(json.dumps(runtime_autoplay(sys.argv[2],sys.argv[3],sys.argv[4],mode='qa',decisions=3,boot_frames=1,action_frames=1,settle_frames=0)))")
                run=subprocess.run([sys.executable,"-I","-B","-c",bootstrap,str(Path(__file__).resolve().parent.parent),str(so),str(content),str(td/"auto")],capture_output=True,text=True,timeout=30)
                if run.returncode: return {"name":"autonomous runtime","ok":False,"error":run.stderr[-2000:]}
                r=json.loads(run.stdout)
            else:
                r=runtime_autoplay(so,content,td/"auto",mode="qa",decisions=3,boot_frames=1,action_frames=1,settle_frames=0)
            return {"name":"autonomous runtime","ok":r.get("decisions_completed",0)>=1,"detail":{"decisions":r.get("decisions_completed")}}
        finally:
            for attempt in range(31):
                try:
                    temporary.cleanup();break
                except PermissionError:
                    if sys.platform!="win32" or attempt==30:raise
                    time.sleep(.1)
    except Exception as exc: return {"name":"autonomous runtime","ok":False,"error":str(exc)}


def v9_self_test(out:str|None=None)->dict[str,Any]:
    tests=[]
    for name,fn in [("belief lifecycle",_test_beliefs),("objective candidate extraction",_test_objectives),("failure classification",_test_failure),("risk-aware planning",_test_planner),("farming economics",_test_economy),("genre policy packs",_test_genres)]:
        try: tests.append({"name":name,"ok":bool(fn())})
        except Exception as exc: tests.append({"name":name,"ok":False,"error":str(exc)})
    tests.append(_test_autoplay())
    ok=all(t.get("ok",False) for t in tests if not t.get("skipped")) and not any(t.get("ok") is False for t in tests)
    r={"tool":"ROMancer","version":VERSION,"feature":"v9 self-test","ok":ok,"tests":tests,
       "notes":["v9 tests validate the decision architecture and a bounded runtime loop against the deterministic source-built mock libretro core.","They do not claim arbitrary-game semantic understanding without exact-game evidence."]}
    if out: write_json(out,r)
    return r


def dispatch_v9(args)->tuple[bool,Any]:
    cmd=getattr(args,"cmd",None)
    if cmd=="play-session": return True,session_cmd(args)
    if cmd=="play-belief": return True,belief_cmd(args)
    if cmd=="play-objective": return True,objective_cmd(args)
    if cmd=="play-failure":
        r=classify_failure(_load_json(args.observation));
        if args.out: write_json(args.out,r)
        return True,r
    if cmd=="play-plan": return True,plan_cmd(args)
    if cmd=="play-economy": return True,economy_cmd(args)
    if cmd=="genre-pack":
        if args.action=="list": return True,{"packs":list_packs()}
        if not args.name: raise ValueError("genre-pack show/hypotheses requires a name")
        p=load_pack(args.name); return True,(p if args.action=="show" else {"pack":p.get("id"),"hypotheses":hypotheses(p,state=args.state)})
    if cmd=="runtime-autoplay":
        return True,runtime_autoplay(args.core,args.game,args.out_dir,profile=args.profile,states=args.states,mode=args.mode,decisions=args.decisions,boot_frames=args.boot_frames,action_frames=args.action_frames,settle_frames=args.settle_frames,memory_region=args.memory_region,state_threshold=args.state_threshold,system_dir=args.system_dir,save_dir=args.save_dir,assets_dir=args.assets_dir,core_options=_kv(args.core_option))
    if cmd=="v9-self-test": return True,v9_self_test(args.out)
    return False,None
