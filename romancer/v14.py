from __future__ import annotations
import json, tempfile, sys
from pathlib import Path
from .util import write_json
from .qa_lab_v14 import coverage_next, generate_boundary_tests, qa_run, balance_report, pacing_report, save_torture_plan, cross_core_matrix
VERSION="14.0.0"

def add_v14_parsers(sub):
    s=sub.add_parser("qa-next",help="[v14] Select the next declared uncovered QA target"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("qa-boundaries",help="[v14] Generate boundary tests from explicitly declared mechanics"); s.add_argument("mechanics"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("qa-run",help="[v14] Run an explicit local QA command manifest in parallel"); s.add_argument("manifest"); s.add_argument("--workers",type=int,default=4); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("balance-report",help="[v14] Aggregate controlled battle observations by encounter/level/strategy"); s.add_argument("observations"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("pacing-report",help="[v14] Measure natural-play time distribution from categorized segments"); s.add_argument("events"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("save-torture-plan",help="[v14] Generate a real-save-system QA plan from a profile"); s.add_argument("profile"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("cross-core-matrix",help="[v14] Classify multi-emulator QA agreement/disagreement"); s.add_argument("results"); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("v14-self-test",help="[v14] Test QA scheduling, boundaries, parallel runner, balance, pacing and cross-core aggregation"); s.add_argument("--out"); s.add_argument("--json",action="store_true")

def v14_self_test(out=None):
    tests=[]
    with tempfile.TemporaryDirectory(prefix="romancer_v14_") as td:
        td=Path(td)
        cov=td/"cov.json"; cov.write_text(json.dumps({"categories":{"maps":{"known":[1,2],"hit":[1],"priority":2},"bosses":{"known":["a"],"hit":[],"priority":3}}}))
        q=coverage_next(str(cov)); tests.append({"name":"coverage-directed target","ok":q["next"]["category"]=="bosses"})
        mech=td/"mech.json"; mech.write_text(json.dumps({"numeric_fields":[{"name":"hp","min":0,"max":99}],"purchases":[{"item":"Potion","price":50}],"inventories":[{"capacity":10}]})); b=generate_boundary_tests(str(mech)); tests.append({"name":"boundary generation","ok":b["test_count"]>=10})
        man=td/"tasks.json"; man.write_text(json.dumps({"tasks":[{"id":"a","command":[sys.executable,"-c","pass"]},{"id":"b","command":[sys.executable,"-c","pass"]}]})); qr=qa_run(str(man),workers=2); tests.append({"name":"parallel QA runner","ok":qr["ok"] and qr["passed"]==2})
        bal=td/"bal.json"; bal.write_text(json.dumps({"battles":[{"encounter":"boss","level":5,"strategy":"careful","win":True,"turns":8},{"encounter":"boss","level":5,"strategy":"careful","win":False,"turns":10}]})); br=balance_report(str(bal)); tests.append({"name":"balance aggregation","ok":br["groups"][0]["win_rate_percent"]==50.0})
        pace=td/"pace.json"; pace.write_text(json.dumps({"segments":[{"category":"battle","seconds":60},{"category":"dialogue","seconds":60}]})); pr=pacing_report(str(pace)); tests.append({"name":"pacing aggregation","ok":pr["total_minutes"]==2.0})
        cc=td/"cc.json"; cc.write_text(json.dumps({"results":[{"test":"boot","backend":"A","ok":True},{"test":"boot","backend":"B","ok":False}]})); cr=cross_core_matrix(str(cc)); tests.append({"name":"cross-core classification","ok":cr["tests"][0]["classification"]=="backend_specific_difference"})
    ok=all(t["ok"] for t in tests); r={"tool":"ROMancer","version":VERSION,"feature":"v14 self-test","ok":ok,"tests":tests}
    if out: write_json(out,r)
    return r

def dispatch_v14(args):
    c=getattr(args,"cmd","")
    if c=="qa-next": return True,coverage_next(args.manifest,args.out)
    if c=="qa-boundaries": return True,generate_boundary_tests(args.mechanics,args.out)
    if c=="qa-run": return True,qa_run(args.manifest,args.workers,args.out)
    if c=="balance-report": return True,balance_report(args.observations,args.out)
    if c=="pacing-report": return True,pacing_report(args.events,args.out)
    if c=="save-torture-plan": return True,save_torture_plan(args.profile,args.out)
    if c=="cross-core-matrix": return True,cross_core_matrix(args.results,args.out)
    if c=="v14-self-test": return True,v14_self_test(args.out)
    return False,None
