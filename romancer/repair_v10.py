from __future__ import annotations

"""Bounded candidate-repair generation and evaluation for ROMancer v10."""

from pathlib import Path
from typing import Any
import hashlib, json, subprocess, tempfile
from .bisect_v10 import _oracle_args
from .util import parse_int, write_json


def _parse_values(spec:str,width:int,endian:str)->list[bytes]:
    out=[]
    for token in spec.split(","):
        token=token.strip()
        if not token: continue
        v=parse_int(token)
        out.append(int(v).to_bytes(width,endian,signed=False))
    return out


def _oracle(command:str|list[str],path:Path,timeout:int)->dict[str,Any]:
    args=_oracle_args(command,path); cp=subprocess.run(args,capture_output=True,text=True,timeout=timeout,shell=False)
    if cp.returncode not in (0,1): return {"ok":False,"oracle_error":True,"returncode":cp.returncode,"stderr":cp.stderr[-2000:]}
    return {"ok":True,"pass":cp.returncode==0,"returncode":cp.returncode,"stdout":cp.stdout[-2000:],"stderr":cp.stderr[-2000:]}


def parameter_repair(rom:str,offset:str,values:str,oracle_command:str|list[str],*,width:int=1,endian:str="little",expected_before:str|None=None,timeout:int=60,out_dir:str="repair_candidates",out:str|None=None)->dict[str,Any]:
    src=Path(rom).read_bytes(); off=parse_int(offset); candidates=_parse_values(values,width,endian); root=Path(out_dir); root.mkdir(parents=True,exist_ok=True)
    if off<0 or off+width>len(src): raise ValueError("repair offset outside ROM")
    before=src[off:off+width]
    if expected_before is not None:
        exp=bytes.fromhex(expected_before.replace(" ",""))
        if before!=exp: raise ValueError(f"expected-before mismatch: observed {before.hex()} expected {exp.hex()}")
    results=[]
    for i,val in enumerate(candidates):
        if len(val)!=width: continue
        b=bytearray(src); b[off:off+width]=val; p=root/f"candidate_{i:03d}_{val.hex()}.bin"; p.write_bytes(b)
        verdict=_oracle(oracle_command,p,timeout); results.append({"index":i,"value_hex":val.hex(),"value_int":int.from_bytes(val,endian),"path":str(p),"sha256":hashlib.sha256(b).hexdigest(),"oracle":verdict})
    passing=[x for x in results if x["oracle"].get("pass")]
    result={"tool":"ROMancer","feature":"v10 bounded parameter repair","rom":rom,"offset":off,"width":width,"endian":endian,"before_hex":before.hex(),"candidate_count":len(results),"passing_count":len(passing),"candidates":results,"recommended":passing[0] if len(passing)==1 else None,"status":"verified_unique_candidate" if len(passing)==1 else "multiple_candidates" if len(passing)>1 else "no_candidate_passed","warning":"A passing local oracle is not release certification. Run the broader regression/certification suite before accepting a repair."}
    if out: write_json(out,result)
    return result
