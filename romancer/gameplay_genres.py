from __future__ import annotations

"""Genre policy packs for ROMancer v9.

These packs are hypothesis generators.  They never override exact-game evidence.
"""

from pathlib import Path
from typing import Any
import json


def pack_dir()->Path:
    return Path(__file__).resolve().parent.parent / "knowledge" / "genre_packs"


def list_packs()->list[dict[str,Any]]:
    out=[]
    for p in sorted(pack_dir().glob("*.json")):
        try:
            o=json.loads(p.read_text(encoding="utf-8")); out.append({"id":o.get("id",p.stem),"name":o.get("name",p.stem),"path":str(p),"states":o.get("states",[])})
        except Exception as exc: out.append({"id":p.stem,"error":str(exc)})
    return out


def load_pack(name_or_path:str|Path)->dict[str,Any]:
    p=Path(name_or_path)
    if not p.is_file(): p=pack_dir()/f"{name_or_path}.json"
    if not p.is_file(): raise FileNotFoundError(name_or_path)
    return json.loads(p.read_text(encoding="utf-8"))


def hypotheses(pack:dict[str,Any], *, state:str|None=None)->list[dict[str,Any]]:
    vals=[]
    for h in pack.get("hypotheses",[]):
        if not isinstance(h,dict): continue
        if state and h.get("states") and state not in h.get("states",[]): continue
        vals.append({**h,"status":"PLAUSIBLE","source":f"genre_pack:{pack.get('id')}"})
    return vals
