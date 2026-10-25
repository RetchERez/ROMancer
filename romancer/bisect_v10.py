from __future__ import annotations

"""Binary-delta hunk construction and delta-debugging for ROMancer v10."""

from pathlib import Path
from typing import Any, Callable
import hashlib, json, math, shlex, subprocess, tempfile
from .util import write_json


def diff_hunks(original: bytes, candidate: bytes, merge_gap:int=0)->list[dict[str,Any]]:
    n=max(len(original),len(candidate)); changed=[]
    i=0
    while i<n:
        a=original[i] if i<len(original) else None; b=candidate[i] if i<len(candidate) else None
        if a==b: i+=1; continue
        s=i; last=i; i+=1
        while i<n:
            aa=original[i] if i<len(original) else None; bb=candidate[i] if i<len(candidate) else None
            if aa!=bb: last=i; i+=1; continue
            gap=0; k=i
            while k<n and gap<=merge_gap:
                aaa=original[k] if k<len(original) else None; bbb=candidate[k] if k<len(candidate) else None
                if aaa!=bbb: last=k; i=k+1; break
                gap+=1; k+=1
            else: break
            if k>=n or gap>merge_gap: break
        e=last
        changed.append({"id":len(changed),"start":s,"end":e,"length":e-s+1,"before":original[s:min(e+1,len(original))].hex(),"after":candidate[s:min(e+1,len(candidate))].hex()})
        i=max(i,e+1)
    return changed


def apply_hunks(original:bytes,candidate:bytes,hunks:list[dict[str,Any]],selected:set[int])->bytes:
    size=max(len(original),len(candidate)); out=bytearray(original + b"\x00"*(size-len(original)))
    for h in hunks:
        if int(h["id"]) not in selected: continue
        s,e=int(h["start"]),int(h["end"]); out[s:e+1]=candidate[s:e+1]
    # Preserve candidate length only when selected hunks touch the extension; otherwise baseline length.
    extension_selected=any(int(h["id"]) in selected and int(h["end"])>=len(original) for h in hunks)
    target_len=len(candidate) if extension_selected else len(original)
    return bytes(out[:target_len])


def ddmin(hunks:list[dict[str,Any]], fails:Callable[[set[int]],bool])->dict[str,Any]:
    """Return a 1-minimal failure-inducing hunk set using classic delta debugging."""
    current={int(h["id"]) for h in hunks}
    if not fails(current): return {"ok":False,"error":"full candidate does not reproduce failure","selected":sorted(current),"tests":1}
    tests=1; n=2
    while len(current)>=2:
        items=sorted(current); chunks=[set(items[i::n]) for i in range(n)]; reduced=False
        for chunk in chunks:
            if not chunk: continue
            tests+=1
            if fails(chunk): current=chunk; n=max(2,n-1); reduced=True; break
        if reduced: continue
        for chunk in chunks:
            comp=current-chunk
            if not comp: continue
            tests+=1
            if fails(comp): current=comp; n=max(2,n-1); reduced=True; break
        if reduced: continue
        if n>=len(current): break
        n=min(len(current),n*2)
    return {"ok":True,"selected":sorted(current),"tests":tests,"minimality":"1-minimal under supplied oracle"}


def _oracle_args(command:str|list[str],rom_path:Path)->list[str]:
    """Tokenize POSIX command strings before inserting literal ROM paths."""
    tokens=shlex.split(command) if isinstance(command,str) else command
    return [token.replace("{rom}",str(rom_path)) for token in tokens]


def _run_oracle(command:str|list[str],rom_path:Path, timeout:int=60)->tuple[bool,dict[str,Any]]:
    """Run argv or a POSIX-quoted command template without a shell."""
    args=_oracle_args(command,rom_path)
    cp=subprocess.run(args,capture_output=True,text=True,timeout=timeout,shell=False)
    # Contract: exit 1 means defect reproduced; exit 0 means passes/no defect. Other codes are oracle errors.
    if cp.returncode not in (0,1): raise RuntimeError(f"oracle exit {cp.returncode}: {cp.stderr[-1000:]}")
    return cp.returncode==1,{"command":args,"returncode":cp.returncode,"stdout":cp.stdout[-2000:],"stderr":cp.stderr[-2000:]}


def patch_bisect(original:str,candidate:str,oracle_command:str|list[str],*,merge_gap:int=0,timeout:int=60,out:str|None=None)->dict[str,Any]:
    a=Path(original).read_bytes(); b=Path(candidate).read_bytes(); hunks=diff_hunks(a,b,merge_gap); log=[]
    with tempfile.TemporaryDirectory(prefix="romancer_v10_bisect_") as td:
        td=Path(td)
        def fails(sel:set[int])->bool:
            rom=td/"candidate.bin"; rom.write_bytes(apply_hunks(a,b,hunks,sel)); bad,detail=_run_oracle(oracle_command,rom,timeout); detail["selected"]=sorted(sel); log.append(detail); return bad
        minimized=ddmin(hunks,fails)
    result={"tool":"ROMancer","feature":"v10 patch bisect","original":original,"candidate":candidate,"hunk_count":len(hunks),"hunks":hunks,"result":minimized,"selected_hunks":[h for h in hunks if int(h["id"]) in set(minimized.get("selected",[]))],"oracle_contract":"exit 1=defect reproduced; exit 0=defect absent; other=error","oracle_log":log}
    if out: write_json(out,result)
    return result
