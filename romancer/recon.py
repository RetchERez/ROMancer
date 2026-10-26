from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import math

from .util import read_bytes, write_json, parse_int


PNG_SIG = b'\x89PNG\r\n\x1a\n'

def _hex(n:int)->str: return f"0x{n:06X}"

def load_tbl(path: str|None) -> dict[int,str]:
    table: dict[int,str] = {}
    if not path: return table
    for raw in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v = line.split('=',1)
        try: table[int(k.strip().replace('$',''),16)] = v.rstrip('\n')
        except ValueError: continue
    return table

def _decode_tbl(data: bytes, table: dict[int,str]) -> str:
    return ''.join(table.get(b, '.') for b in data)

def text_scan(rom: str, system: str='unknown', encoding: str='ascii', tbl: str|None=None, min_length:int=5, terminators: str='00,F7,FF', out: str|None=None)->dict[str,Any]:
    data=read_bytes(rom); terms={int(x.strip().replace('0x',''),16) for x in terminators.split(',') if x.strip()}
    table=load_tbl(tbl); runs=[]
    i=0
    while i<len(data):
        start=i; buf=bytearray()
        while i<len(data):
            b=data[i]
            ok=False
            if table: ok=b in table and b not in terms
            else: ok=(32<=b<127) or b in (9,)
            if not ok: break
            buf.append(b); i+=1
        if len(buf)>=min_length:
            term=data[i] if i<len(data) else None
            text=_decode_tbl(bytes(buf),table) if table else bytes(buf).decode('ascii','replace')
            runs.append({'offset':_hex(start),'length':len(buf),'terminator':f'{term:02X}' if term is not None and term in terms else None,'text':text[:240],'confidence':'high' if len(buf)>=12 else 'medium'})
        i=max(i+1,start+1)
    regions=[]
    if runs:
        cur=[runs[0]]
        for r in runs[1:]:
            if int(r['offset'],16)-int(cur[-1]['offset'],16)<512: cur.append(r)
            else:
                if len(cur)>=3: regions.append({'start':cur[0]['offset'],'end':_hex(int(cur[-1]['offset'],16)+cur[-1]['length']),'strings':len(cur),'confidence':'medium'})
                cur=[r]
        if len(cur)>=3: regions.append({'start':cur[0]['offset'],'end':_hex(int(cur[-1]['offset'],16)+cur[-1]['length']),'strings':len(cur),'confidence':'medium'})
    result={'tool':'ROMancer','feature':'v0.5 text-scan','rom':rom,'system':system,'encoding':encoding,'tbl':tbl,'string_count':len(runs),'regions':regions[:100],'strings':runs[:1000],'warnings':['ASCII/TBL scanning is reconnaissance only. Confirm text encoding and pointer usage before patching.']}
    if out: write_json(out,result)
    return result

def _target_offset_to_snes_ptrs(offset:int, mapping:str)->list[bytes]:
    ptrs=[]
    # brute map ROM offset to common CPU ranges for LoROM/HiROM candidates
    m=mapping.lower()
    if m=='hirom':
        bank=(offset//0x10000)+0xC0; addr=offset&0xFFFF; ptrs += [bytes([bank, addr>>8, addr&0xFF]), bytes([addr&0xFF, addr>>8, bank])]
    elif m=='lorom':
        bank=(offset//0x8000)+0x80; addr=(offset&0x7FFF)|0x8000; ptrs += [bytes([bank, addr>>8, addr&0xFF]), bytes([addr&0xFF, addr>>8, bank]), bytes([addr&0xFF, addr>>8])]
    else:
        ptrs += _target_offset_to_snes_ptrs(offset,'hirom') + _target_offset_to_snes_ptrs(offset,'lorom')
    return list(dict.fromkeys(ptrs))

def pointer_scan(rom:str, system:str, target:str, mapping:str='auto', window:int=0, out:str|None=None)->dict[str,Any]:
    data=read_bytes(rom); target_i=parse_int(target); pats=[]; sys=system.lower()
    if sys=='snes': pats=_target_offset_to_snes_ptrs(target_i,mapping)
    elif sys=='genesis': pats=[target_i.to_bytes(4,'big',signed=False), (target_i&0xFFFFFF).to_bytes(3,'big')]
    elif sys=='nes': pats=[(target_i&0xFFFF).to_bytes(2,'little')]
    else: pats=[target_i.to_bytes(4,'little',signed=False), target_i.to_bytes(4,'big',signed=False), (target_i&0xFFFF).to_bytes(2,'little')]
    matches=[]
    for pat in pats:
        pos=0
        while True:
            idx=data.find(pat,pos)
            if idx<0: break
            matches.append({'offset':_hex(idx),'bytes':' '.join(f'{b:02X}' for b in pat),'size':len(pat),'confidence':'high' if len(pat)>=3 else 'medium'})
            pos=idx+1
    result={'tool':'ROMancer','feature':'v0.5 pointer-scan','rom':rom,'system':system,'target':target,'mapping':mapping,'matches':matches[:2000],'match_count':len(matches),'warnings':['Pointer matches are candidates. Confirm table structure and active bank/mapping before editing.']}
    if out: write_json(out,result)
    return result

def _tile_2bpp(tile:bytes)->list[int]:
    pix=[]
    for y in range(8):
        p0=tile[y]; p1=tile[y+8]
        for x in range(8): pix.append(((p0>>(7-x))&1)|(((p1>>(7-x))&1)<<1))
    return pix

def _tile_4bpp_snes(tile:bytes)->list[int]:
    pix=[]
    for y in range(8):
        p0=tile[y*2]; p1=tile[y*2+1]; p2=tile[16+y*2]; p3=tile[16+y*2+1]
        for x in range(8): pix.append(((p0>>(7-x))&1)|(((p1>>(7-x))&1)<<1)|(((p2>>(7-x))&1)<<2)|(((p3>>(7-x))&1)<<3))
    return pix

def _tile_4bpp_genesis(tile:bytes)->list[int]:
    pix=[]
    for b in tile:
        pix.append((b>>4)&0xF); pix.append(b&0xF)
    return pix[:64]

def _write_png_gray(path: str, pixels:list[int], w:int,h:int, maxval:int):
    import zlib, struct
    raw=bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            v=pixels[y*w+x] if y*w+x<len(pixels) else 0
            g=int(255*(v/max(1,maxval)))
            raw.extend([g,g,g,255])
    def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    png=PNG_SIG+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(raw)))+chunk(b'IEND',b'')
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_bytes(png)

def tile_dump(rom:str, system:str, offset:str, count:int=128, bpp:int=4, columns:int=16, out:str='tiles.png')->dict[str,Any]:
    data=read_bytes(rom); off=parse_int(offset); sys=system.lower(); tile_size={2:16,4:32,8:64}.get(bpp,32)
    rows=math.ceil(count/columns); w=columns*8; h=rows*8; sheet=[0]*(w*h); maxval=(1<<bpp)-1
    for n in range(count):
        chunk=data[off+n*tile_size:off+(n+1)*tile_size]
        if len(chunk)<tile_size: break
        if bpp==2: pix=_tile_2bpp(chunk)
        elif bpp==4 and sys=='genesis': pix=_tile_4bpp_genesis(chunk)
        elif bpp==4: pix=_tile_4bpp_snes(chunk)
        else: pix=[0]*64
        tx=(n%columns)*8; ty=(n//columns)*8
        for y in range(8):
            for x in range(8): sheet[(ty+y)*w+(tx+x)]=pix[y*8+x]
    _write_png_gray(out,sheet,w,h,maxval)
    return {'tool':'ROMancer','feature':'v0.5 tile-dump','rom':rom,'system':system,'offset':_hex(off),'count':count,'bpp':bpp,'out':out,'warnings':['Grayscale tile dump only. Palette-correct rendering requires confirmed palette/VRAM context.']}

def _snes_color(v:int):
    r=(v&31)<<3; g=((v>>5)&31)<<3; b=((v>>10)&31)<<3; return (r,g,b)

def _gen_color(v:int):
    r=((v>>1)&7)*36; g=((v>>5)&7)*36; b=((v>>9)&7)*36; return (r,g,b)

def palette_dump(rom:str, system:str, offset:str, count:int=16, out:str|None=None)->dict[str,Any]:
    data=read_bytes(rom); off=parse_int(offset); sys=system.lower(); colors=[]
    for i in range(count):
        raw=data[off+i*2:off+i*2+2]
        if len(raw)<2: break
        v=int.from_bytes(raw,'little')
        rgb=_gen_color(v) if sys=='genesis' else _snes_color(v)
        colors.append({'index':i,'raw':f'{raw[0]:02X} {raw[1]:02X}','rgb':rgb,'hex':'#%02X%02X%02X'%rgb})
    if out:
        w=count*16; h=16; pix=[]
        for y in range(h):
            for i,c in enumerate(colors): pix.extend([i]*16)
        # custom write colored png
        import zlib, struct
        raw=bytearray()
        for y in range(h):
            raw.append(0)
            for x in range(w):
                rgb=colors[min(x//16,len(colors)-1)]['rgb']; raw.extend([*rgb,255])
        def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
        Path(out).parent.mkdir(parents=True,exist_ok=True); Path(out).write_bytes(PNG_SIG+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(raw)))+chunk(b'IEND',b''))
    return {'tool':'ROMancer','feature':'v0.5 palette-dump','rom':rom,'system':system,'offset':_hex(off),'count':len(colors),'colors':colors,'out':out}

def record_scan(rom:str, start:str, end:str, stride:int, out:str|None=None)->dict[str,Any]:
    data=read_bytes(rom); s=parse_int(start); e=parse_int(end); recs=[]; 
    for off in range(s,min(e,len(data)),stride):
        raw=data[off:off+stride]
        if len(raw)<stride: break
        recs.append({'offset':_hex(off),'bytes':' '.join(f'{b:02X}' for b in raw)})
    # simple repeated field detection
    repeats=[]
    for pos in range(stride):
        vals=[bytes.fromhex(r['bytes'].replace(' ',''))[pos] for r in recs if len(bytes.fromhex(r['bytes'].replace(' ','')))>pos]
        if vals and len(set(vals))<=max(3,len(vals)//3): repeats.append({'+offset':pos,'unique_values':len(set(vals)),'note':'low variation field candidate'})
    result={'tool':'ROMancer','feature':'v0.5 record-scan','rom':rom,'start':_hex(s),'end':_hex(e),'stride':stride,'record_count':len(recs),'repeated_field_candidates':repeats,'records':recs[:1000],'warnings':['Record structure inference is heuristic. Confirm with trace or known table behavior.']}
    if out: write_json(out,result)
    return result

def table_report(scan_json:str, out:str|None=None)->str:
    obj=json.loads(Path(scan_json).read_text(encoding='utf-8'))
    lines=['ROMancer Table Report',f"Source: {scan_json}",f"Feature: {obj.get('feature','unknown')}",'']
    for k in ['rom','system','start','end','stride','record_count','match_count','string_count']:
        if k in obj: lines.append(f"{k}: {obj[k]}")
    lines.append('')
    for w in obj.get('warnings',[]): lines.append('WARNING: '+w)
    text='\n'.join(lines)+'\n'
    if out: Path(out).parent.mkdir(parents=True,exist_ok=True); Path(out).write_text(text,encoding='utf-8')
    return text
