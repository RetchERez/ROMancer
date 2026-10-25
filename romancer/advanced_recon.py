from __future__ import annotations
from pathlib import Path
from typing import Any
import math, os
from .recon import tile_dump, text_scan
from .util import write_json

def tile_hunt(rom:str,system:str,bpp:int=4,step:str='0x1000',count:int=64,out_dir:str='tile_hunt')->dict[str,Any]:
    data=Path(rom).read_bytes(); st=int(str(step).replace('0x',''),16) if isinstance(step,str) else int(step)
    od=Path(out_dir); od.mkdir(parents=True,exist_ok=True); sheets=[]
    for off in range(0,len(data),max(1,st)):
        out=od/f'tiles_{off:06X}.png'
        try:
            tile_dump(rom,system,f'0x{off:X}',count=count,bpp=bpp,columns=16,out=str(out))
            sheets.append({'offset':f'0x{off:06X}','out':str(out)})
        except Exception as e:
            sheets.append({'offset':f'0x{off:06X}','error':str(e)})
    result={'tool':'ROMancer','feature':'tile hunt','rom':rom,'system':system,'bpp':bpp,'step':hex(st),'sheet_count':len(sheets),'sheets':sheets[:500],
            'warnings':['Tile hunt is visual reconnaissance. Correct palettes and tilemaps require separate confirmation.']}
    write_json(str(od/'tile_hunt_manifest.json'),result)
    return result

def font_hunt(rom:str,system:str='unknown',out:str|None=None)->dict[str,Any]:
    # Conservative heuristic: text-like regions and repeated byte-range runs are font candidates, not confirmations.
    ts=text_scan(rom,system=system,min_length=8)
    data=Path(rom).read_bytes(); candidates=[]
    for off in range(0,len(data)-256,256):
        block=data[off:off+256]
        nonzero=sum(1 for b in block if b); uniq=len(set(block))
        if 20 < uniq < 180 and nonzero>96:
            candidates.append({'offset':f'0x{off:06X}','unique_bytes':uniq,'nonzero_bytes':nonzero,'reason':'dense medium-entropy block'})
    result={'tool':'ROMancer','feature':'font hunt','rom':rom,'system':system,'text_regions':ts.get('regions',[])[:50],'font_like_blocks':candidates[:500],
            'warnings':['Font hunt is heuristic. Use tile-dump/tile-hunt and emulator VRAM tracing to confirm.']}
    if out: write_json(out,result)
    return result
