from __future__ import annotations

"""Input/testcase delta minimization for ROMancer v10."""

from typing import Any, Callable
from pathlib import Path
import json, shlex, subprocess, tempfile
from .util import write_json


def minimize_sequence(steps:list[Any], fails:Callable[[list[Any]],bool])->dict[str,Any]:
    current=list(steps); tests=0
    if not fails(current): return {"ok":False,"error":"original sequence does not reproduce failure","steps":current,"tests":1}
    tests=1; n=2
    while len(current)>=2:
        length=len(current); chunk=max(1,(length+n-1)//n); reduced=False
        groups=[current[i:i+chunk] for i in range(0,length,chunk)]
        for g in groups:
            tests+=1
            if fails(g): current=g; n=max(2,n-1); reduced=True; break
        if reduced: continue
        for idx,g in enumerate(groups):
            comp=[]
            for j,h in enumerate(groups):
                if j!=idx: comp.extend(h)
            if not comp: continue
            tests+=1
            if fails(comp): current=comp; n=max(2,n-1); reduced=True; break
        if reduced: continue
        if n>=len(current): break
        n=min(len(current),n*2)
    return {"ok":True,"steps":current,"original_count":len(steps),"minimized_count":len(current),"tests":tests,"minimality":"1-minimal under supplied oracle"}


def testcase_minimize(input_json:str,oracle_command:str,*,timeout:int=60,out:str|None=None)->dict[str,Any]:
    obj=json.loads(Path(input_json).read_text(encoding="utf-8")); steps=obj.get("steps")
    if not isinstance(steps,list): raise ValueError("Input JSON must contain steps[]")
    logs=[]
    with tempfile.TemporaryDirectory(prefix="romancer_v10_min_") as td:
        td=Path(td)
        def fails(candidate:list[Any])->bool:
            p=td/"case.json"; p.write_text(json.dumps({**obj,"steps":candidate},indent=2)+"\n",encoding="utf-8")
            cmd=shlex.split(oracle_command.replace("{case}",str(p))); cp=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
            if cp.returncode not in (0,1): raise RuntimeError(f"oracle exit {cp.returncode}: {cp.stderr[-1000:]}")
            logs.append({"returncode":cp.returncode,"step_count":len(candidate),"stdout":cp.stdout[-1000:],"stderr":cp.stderr[-1000:]})
            return cp.returncode==1
        r=minimize_sequence(steps,fails)
    result={"tool":"ROMancer","feature":"v10 testcase minimizer","input":input_json,"oracle_contract":"exit 1=defect reproduced; exit 0=defect absent","result":r,"oracle_log":logs}
    if out: write_json(out,result)
    return result
