from __future__ import annotations

"""ROMancer v14 whole-game QA laboratory primitives."""

import json, shlex, subprocess, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean
from typing import Any
from .util import write_json


def coverage_next(manifest:str, out:str|None=None)->dict[str,Any]:
    m=json.loads(Path(manifest).read_text()); cats=m.get("categories",{})
    candidates=[]
    for name,c in cats.items():
        known=list(c.get("known",[])); hit=set(c.get("hit",[])); excluded=set(c.get("excluded",[])); priority=float(c.get("priority",1.0))
        missing=[x for x in known if x not in hit and x not in excluded]
        denom=max(1,len([x for x in known if x not in excluded])); cov=(denom-len(missing))/denom
        for item in missing:
            candidates.append({"category":name,"target":item,"priority":priority,"category_coverage":round(cov*100,2),"score":priority*(1.0-cov+0.01)})
    candidates.sort(key=lambda x:(-x["score"],x["category"],str(x["target"])))
    r={"tool":"ROMancer","feature":"v14 coverage-directed target selection","remaining":len(candidates),"next":candidates[0] if candidates else None,"ranked":candidates[:100],
       "policy":"Select uncovered declared targets; this does not invent unknown content."}
    if out: write_json(out,r)
    return r


def generate_boundary_tests(mechanics:str, out:str|None=None)->dict[str,Any]:
    m=json.loads(Path(mechanics).read_text()); tests=[]
    for f in m.get("numeric_fields",[]):
        name=f["name"]; lo=int(f.get("min",0)); hi=int(f["max"])
        vals=[]
        for v in (lo,lo+1,max(lo,hi-1),hi):
            if lo<=v<=hi and v not in vals: vals.append(v)
        for v in vals: tests.append({"kind":"numeric_boundary","field":name,"value":v,"expected":f.get("expected","valid state or explicit rejection")})
    for p in m.get("purchases",[]):
        price=int(p["price"])
        for money in sorted(set(max(0,x) for x in (0,price-1,price,price+1))): tests.append({"kind":"purchase_boundary","item":p.get("item"),"money":money,"price":price})
    for inv in m.get("inventories",[]):
        cap=int(inv["capacity"])
        for count in sorted(set(max(0,x) for x in (0,1,cap-1,cap))): tests.append({"kind":"inventory_boundary","inventory":inv.get("name","inventory"),"count":count,"capacity":cap})
    for tr in m.get("transitions",[]):
        for direction in tr.get("approaches",["up","down","left","right"]): tests.append({"kind":"transition_boundary","transition":tr["name"],"approach":direction,"return_check":True})
    r={"tool":"ROMancer","feature":"v14 boundary test generator","test_count":len(tests),"tests":tests,
       "policy":"Generated from explicitly declared mechanics only; expected behavior still requires game-specific assertions."}
    if out: write_json(out,r)
    return r


def qa_run(manifest:str, workers:int=4, out:str|None=None)->dict[str,Any]:
    """Run manifest commands as argv lists or POSIX-quoted strings, without a shell."""
    m=json.loads(Path(manifest).read_text()); tasks=m.get("tasks",[]); start=time.time()
    def run_one(i,t):
        command=t["command"]; args=shlex.split(command) if isinstance(command,str) else command
        if not isinstance(args,list) or not args or not all(isinstance(arg,str) for arg in args):
            raise ValueError("command must be a POSIX-quoted string or a nonempty list of strings")
        timeout=int(t.get("timeout",60)); cp=subprocess.run(args,capture_output=True,text=True,timeout=timeout,shell=False)
        expected=t.get("expected_exit",0); return {"id":t.get("id",i),"name":t.get("name",t.get("id",str(i))),"returncode":cp.returncode,"expected_exit":expected,"ok":cp.returncode==expected,"stdout":cp.stdout[-3000:],"stderr":cp.stderr[-3000:]}
    results=[]
    with ThreadPoolExecutor(max_workers=max(1,int(workers))) as ex:
        futs=[ex.submit(run_one,i,t) for i,t in enumerate(tasks)]
        for f in as_completed(futs):
            try: results.append(f.result())
            except Exception as e: results.append({"ok":False,"error":str(e)})
    results.sort(key=lambda x:str(x.get("id",""))); ok=all(r.get("ok",False) for r in results)
    r={"tool":"ROMancer","feature":"v14 parallel QA runner","ok":ok,"task_count":len(tasks),"passed":sum(1 for x in results if x.get("ok")),"failed":sum(1 for x in results if not x.get("ok")),"elapsed_seconds":round(time.time()-start,3),"workers":workers,"results":results}
    if out: write_json(out,r)
    return r


def balance_report(observations:str,out:str|None=None)->dict[str,Any]:
    rows=json.loads(Path(observations).read_text()); rows=rows.get("battles",rows) if isinstance(rows,dict) else rows
    groups={}
    for row in rows:
        key=(str(row.get("encounter","unknown")),int(row.get("level",0)),str(row.get("strategy","normal")))
        groups.setdefault(key,[]).append(row)
    summary=[]
    for (enc,lvl,strat),rs in sorted(groups.items()):
        wins=[bool(x.get("win")) for x in rs]; turns=[float(x["turns"]) for x in rs if x.get("turns") is not None]; dmg=[float(x["damage_taken"]) for x in rs if x.get("damage_taken") is not None]
        summary.append({"encounter":enc,"level":lvl,"strategy":strat,"attempts":len(rs),"wins":sum(wins),"win_rate_percent":round(100*sum(wins)/len(rs),2),"mean_turns":round(mean(turns),2) if turns else None,"mean_damage_taken":round(mean(dmg),2) if dmg else None})
    r={"tool":"ROMancer","feature":"v14 balance laboratory","groups":summary,"warning":"Observed/simulated sample rates are empirical results, not exact game probabilities unless the full model is proven."}
    if out: write_json(out,r)
    return r


def pacing_report(events:str,out:str|None=None)->dict[str,Any]:
    rows=json.loads(Path(events).read_text()); rows=rows.get("segments",rows) if isinstance(rows,dict) else rows
    totals={}; total=0.0
    for x in rows:
        d=float(x.get("seconds",0)); total+=d; k=str(x.get("category","unknown")); totals[k]=totals.get(k,0)+d
    cats=[{"category":k,"seconds":round(v,2),"minutes":round(v/60,2),"percent":round(100*v/total,2) if total else 0} for k,v in sorted(totals.items(),key=lambda kv:-kv[1])]
    r={"tool":"ROMancer","feature":"v14 natural-play pacing","total_seconds":round(total,2),"total_minutes":round(total/60,2),"categories":cats,"segment_count":len(rows)}
    if out: write_json(out,r)
    return r


def save_torture_plan(profile:str,out:str|None=None)->dict[str,Any]:
    p=json.loads(Path(profile).read_text()); kinds=set(p.get("save_systems",[])); tests=[]
    if "manual" in kinds or "save_point" in kinds:
        tests += ["create save -> cold boot -> load -> verify state","save before event -> progress -> reload -> verify rollback","multiple save slots remain isolated"]
    if "autosave" in kinds: tests += ["trigger autosave -> wait for completion -> cold boot -> verify persisted state","verify exact autosave granularity"]
    if "sram" in kinds: tests += ["persist SRAM across emulator process restart","new game does not corrupt existing slot unless game specifies it"]
    if "password" in kinds: tests += ["record password -> cold boot -> enter password -> verify reconstructed progress"]
    tests += ["do not substitute emulator savestate for real in-game persistence verification","game over/retry/load recovery path"]
    r={"tool":"ROMancer","feature":"v14 save-system torture plan","save_systems":sorted(kinds),"tests":tests,"test_count":len(tests)}
    if out: write_json(out,r)
    return r


def cross_core_matrix(results:str,out:str|None=None)->dict[str,Any]:
    rj=json.loads(Path(results).read_text()); rows=rj.get("results",rj) if isinstance(rj,dict) else rj
    by_test={}
    for x in rows: by_test.setdefault(str(x["test"]),[]).append(x)
    classes=[]
    for test,rs in sorted(by_test.items()):
        failures=[x for x in rs if not x.get("ok",False)]; passes=[x for x in rs if x.get("ok",False)]
        if failures and not passes: cls="fails_across_all_tested_backends"
        elif failures and passes: cls="backend_specific_difference"
        else: cls="passes_across_all_tested_backends"
        classes.append({"test":test,"classification":cls,"backends":[{"backend":x.get("backend"),"ok":bool(x.get("ok"))} for x in rs]})
    result={"tool":"ROMancer","feature":"v14 cross-core matrix","tests":classes,"warning":"Agreement across tested emulators supports but does not mathematically prove hardware correctness."}
    if out: write_json(out,result)
    return result
