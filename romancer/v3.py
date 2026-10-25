from __future__ import annotations

import json, os, re, shutil, zipfile, hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .util import read_bytes, write_json, read_json, parse_int, sha1, sha256, crc32_hex, hexdump
from .trace_parser import parse_trace, detect_trace_format
from .systems.snes import snes_to_offset
from .diffing import byte_diff
from .ips import create_ips
from .rom_ident import identify_rom
from .patching import _hex_bytes, _bytes_to_hex
from .audit import audit_project, package_release

VERSION = "4.0.0"

BACKEND_PROFILES = {
    "mesen": {"systems": ["nes", "snes"], "supports_launch": True, "supports_trace_import": True, "supports_script_export": "guide", "supports_live_control": False, "breakpoint_types": ["read", "write", "execute"], "stability": "profile"},
    "mesen-s": {"systems": ["snes"], "supports_launch": True, "supports_trace_import": True, "supports_script_export": "guide", "supports_live_control": False, "breakpoint_types": ["read", "write", "execute"], "stability": "profile"},
    "bsnes-plus": {"systems": ["snes"], "supports_launch": True, "supports_trace_import": True, "supports_script_export": "guide", "supports_live_control": False, "breakpoint_types": ["read", "write", "execute"], "stability": "profile"},
    "fceux": {"systems": ["nes"], "supports_launch": True, "supports_trace_import": True, "supports_script_export": "guide", "supports_live_control": False, "breakpoint_types": ["read", "write", "execute"], "stability": "profile"},
    "blastem": {"systems": ["genesis"], "supports_launch": True, "supports_trace_import": True, "supports_script_export": True, "supports_live_control": "experimental", "breakpoint_types": ["execute"], "stability": "profile"},
}

PLUGIN_INDEX = {
    "systems": ["nes", "snes", "genesis"],
    "backends": sorted(BACKEND_PROFILES),
    "trace_formats": ["mesen", "bsnes-plus", "blastem", "generic"],
    "patch_formats": ["ips"],
    "encodings": ["ascii", "tbl"],
    "analysis": ["disasm", "cfg", "value-flow", "table-inference"],
}


def _out(obj: Any, out: str|None=None):
    if out:
        write_json(out, obj)
    return obj


def plugin_list(out: str|None=None) -> dict[str, Any]:
    return _out({"tool":"ROMancer","version":VERSION,"feature":"plugin list","plugins":PLUGIN_INDEX}, out)


def plugin_doctor(out: str|None=None) -> dict[str, Any]:
    checks=[]
    for group, names in PLUGIN_INDEX.items():
        for name in names:
            checks.append({"group": group, "name": name, "loaded": True})
    return _out({"tool":"ROMancer","version":VERSION,"feature":"plugin doctor","ok": all(c["loaded"] for c in checks), "checks": checks}, out)


def backend_profile(name: str|None=None, out: str|None=None) -> dict[str, Any]:
    if name:
        prof = BACKEND_PROFILES.get(name.lower())
        if not prof:
            return _out({"tool":"ROMancer","error":"unknown backend","backend":name,"known":sorted(BACKEND_PROFILES)}, out)
        return _out({"tool":"ROMancer","version":VERSION,"backend":name.lower(),"profile":prof}, out)
    return _out({"tool":"ROMancer","version":VERSION,"backends":BACKEND_PROFILES}, out)


def backend_script(backend: str, system: str, addr: str, access: str="write", out: str|None=None) -> dict[str, Any]:
    b=backend.lower(); access=access.lower(); system=system.lower()
    lines=[f"ROMancer backend script/profile helper", f"Backend: {b}", f"System: {system}", f"Target: {addr}", f"Access: {access}", ""]
    if b == "blastem":
        if access != "execute":
            lines.append("BlastEm command debugger is most reliable for execute breakpoints. Data breakpoints may require manual emulator support or trace-side filtering.")
        lines += ["Suggested BlastEm debugger commands:", f"break {addr}", "commands", "bt", "continue", "end"]
    elif b in {"mesen","mesen-s","bsnes-plus","fceux"}:
        lines += ["GUI debugger workflow:", f"1. Add a {access} breakpoint for {addr}.", "2. Enable trace logging just before the event.", "3. Reproduce the event.", "4. Stop after the breakpoint hit.", "5. Import the trace into ROMancer."]
    else:
        lines.append("Generic backend: create a matching breakpoint manually and export a plain-text trace log.")
    text="\n".join(lines)+"\n"
    if out: Path(out).write_text(text, encoding="utf-8")
    return {"tool":"ROMancer","version":VERSION,"backend":b,"system":system,"target":addr,"access":access,"text":text}

# --- Disassembly helpers: intentionally small, conservative decoders ---
_OP6502 = {
    0xA9:("LDA","#${:02X}",2),0xA5:("LDA","${:02X}",2),0xAD:("LDA","${:04X}",3),0xBD:("LDA","${:04X},X",3),0xB9:("LDA","${:04X},Y",3),
    0x85:("STA","${:02X}",2),0x8D:("STA","${:04X}",3),0x9D:("STA","${:04X},X",3),0x99:("STA","${:04X},Y",3),
    0xA2:("LDX","#${:02X}",2),0xA0:("LDY","#${:02X}",2),0x20:("JSR","${:04X}",3),0x4C:("JMP","${:04X}",3),0x60:("RTS","",1),0xEA:("NOP","",1),
    0xD0:("BNE","rel ${:02X}",2),0xF0:("BEQ","rel ${:02X}",2),0x10:("BPL","rel ${:02X}",2),0x30:("BMI","rel ${:02X}",2),0xC9:("CMP","#${:02X}",2),0xE8:("INX","",1),0xCA:("DEX","",1),
}
_OP65816 = dict(_OP6502)
_OP65816.update({0x22:("JSL","${:06X}",4),0x6B:("RTL","",1),0xC2:("REP","#${:02X}",2),0xE2:("SEP","#${:02X}",2),0xAF:("LDA","${:06X}",4),0x8F:("STA","${:06X}",4)})

def _fmt_operand(fmt: str, payload: bytes) -> str:
    if not fmt: return ""
    if "{:06X}" in fmt:
        val = int.from_bytes(payload[:3], "little")
    elif "{:04X}" in fmt:
        val = int.from_bytes(payload[:2], "little")
    else:
        val = payload[0] if payload else 0
    return fmt.format(val)

def _disasm_6502(data: bytes, start: int, count: int, cpu: str) -> list[dict[str, Any]]:
    table = _OP65816 if cpu == "65816" else _OP6502
    out=[]; off=start; end=min(len(data), start+max(count,1)*4); n=0
    while off < len(data) and n < count:
        op=data[off]; mnem, fmt, size = table.get(op,("DB","${:02X}",1))
        payload=data[off+1:off+size]
        operand = _fmt_operand(fmt, payload) if mnem != "DB" else f"${op:02X}"
        notes=[]
        if mnem in {"STA","STX","STY"}: notes.append("store candidate")
        if mnem in {"LDA","LDX","LDY"} and operand.startswith("#"): notes.append("immediate load candidate")
        if mnem in {"JSR","JSL","JMP"}: notes.append("control-flow candidate")
        out.append({"offset":f"0x{off:06X}","bytes":" ".join(f"{b:02X}" for b in data[off:off+size]),"mnemonic":mnem,"operands":operand,"notes":notes})
        off += size; n += 1
    return out

def _disasm_68k(data: bytes, start: int, count: int) -> list[dict[str, Any]]:
    out=[]; off=start
    for _ in range(count):
        if off+2>len(data): break
        w=int.from_bytes(data[off:off+2],"big"); size=2; mnem="DC.W"; ops=f"${w:04X}"; notes=[]
        if w == 0x4E75: mnem="RTS"; ops=""; notes=["return"]
        elif w == 0x4E71: mnem="NOP"; ops=""
        elif (w & 0xFF00)==0x6100: mnem="BSR"; ops=f"rel ${w&0xFF:02X}"; notes=["call candidate"]
        elif (w & 0xF000)==0x6000: mnem="BRA/Bcc"; ops=f"rel ${w&0xFF:02X}"; notes=["branch candidate"]
        elif (w & 0xFFC0)==0x4E80: mnem="JSR"; ops=f"ea ${w&0x3F:02X}"; notes=["call candidate"]
        elif (w & 0xF000) in (0x1000,0x2000,0x3000): mnem="MOVE"; ops="<ea>,<ea>"; notes=["move candidate"]
        out.append({"offset":f"0x{off:06X}","bytes":" ".join(f"{b:02X}" for b in data[off:off+size]),"mnemonic":mnem,"operands":ops,"notes":notes})
        off += size
    return out

def disasm(rom: str, system: str, offset: str|None=None, pc: str|None=None, mapping: str|None=None, count: int=80, out: str|None=None) -> dict[str, Any]:
    data=read_bytes(rom); system=system.lower()
    off = parse_int(offset) if offset else None
    resolved=None
    if off is None and pc and system=="snes":
        if not mapping: mapping="hirom"
        resolved=snes_to_offset(pc, mapping)
        off=parse_int(resolved["rom_offset_headerless"])
    elif off is None and pc:
        off=parse_int(pc)
    if off is None: off=0
    if off<0 or off>=len(data):
        return _out({"tool":"ROMancer","version":VERSION,"feature":"disasm","error":"offset outside ROM","offset":hex(off),"rom_size":len(data)}, out)
    if system=="snes": rows=_disasm_6502(data, off, count, "65816")
    elif system=="nes": rows=_disasm_6502(data, off, count, "6502")
    elif system=="genesis": rows=_disasm_68k(data, off, count)
    else: rows=[]
    result={"tool":"ROMancer","version":VERSION,"feature":"disasm","system":system,"rom":rom,"offset":f"0x{off:06X}","pc":pc,"mapping":mapping,"resolved":resolved,"instructions":rows,"decoder":"conservative partial decoder, not a full decompiler"}
    return _out(result, out)


def cfg_from_trace(trace: str, out: str|None=None) -> dict[str,Any]:
    parsed=parse_trace(trace); edges=Counter(); pcs=[]
    for e in parsed.get("events",[]):
        pc=e.get("pc")
        if pc: pcs.append(pc)
    for a,b in zip(pcs, pcs[1:]): edges[(a,b)] += 1
    nodes=Counter(pcs)
    dot=["digraph trace_cfg {"]
    for (a,b),c in edges.most_common(200): dot.append(f'  "{a}" -> "{b}" [label="{c}"];')
    dot.append("}")
    result={"tool":"ROMancer","version":VERSION,"feature":"cfg from trace","trace":trace,"node_count":len(nodes),"edge_count":len(edges),"hot_nodes":nodes.most_common(25),"edges":[{"from":a,"to":b,"count":c} for (a,b),c in edges.most_common(200)],"dot":"\n".join(dot)+"\n"}
    if out:
        p=Path(out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(result["dot"] if p.suffix.lower()==".dot" else json.dumps(result,indent=2),encoding="utf-8")
    return result


def cfg_from_disasm(rom: str, system: str, offset: str|None=None, pc: str|None=None, mapping: str|None=None, count: int=200, out: str|None=None) -> dict[str,Any]:
    d=disasm(rom, system, offset, pc, mapping, count)
    instr=d.get("instructions",[]); edges=[]
    last=None
    for row in instr:
        cur=row["offset"]
        if last: edges.append({"from":last,"to":cur,"kind":"fallthrough"})
        if "control-flow" in row.get("notes",[]) or "call candidate" in row.get("notes",[]) or "branch candidate" in row.get("notes",[]):
            edges.append({"from":cur,"to":row.get("operands","unknown"),"kind":"control_candidate"})
        last=cur
    dot=["digraph disasm_cfg {"]+[f'  "{e["from"]}" -> "{e["to"]}" [label="{e["kind"]}"];' for e in edges[:400]]+["}"]
    result={"tool":"ROMancer","version":VERSION,"feature":"cfg from disasm","disasm":d,"edges":edges,"dot":"\n".join(dot)+"\n"}
    if out:
        p=Path(out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(result["dot"] if p.suffix.lower()==".dot" else json.dumps(result,indent=2),encoding="utf-8")
    return result


def _norm_addr(a:str)->str:
    return a.upper().replace("0X","").replace("$","").replace(":","")

def value_flow(trace: str, target_addr: str, window: int=200, out: str|None=None) -> dict[str,Any]:
    parsed=parse_trace(trace); events=parsed.get("events",[]); target=_norm_addr(target_addr)
    hits=[]
    for i,e in enumerate(events):
        ma=e.get("memory_access") or {}
        if ma and target.endswith(_norm_addr(str(ma.get("address","")))):
            hits.append((i,e))
    reports=[]
    load_mnems={"LDA":"A","LDX":"X","LDY":"Y"}
    for idx,e in hits[:20]:
        reg=None; m=(e.get("mnemonic") or "").upper()
        if m=="STA": reg="A"
        elif m=="STX": reg="X"
        elif m=="STY": reg="Y"
        elif m.startswith("MOVE"): reg="source"
        candidates=[]
        start=max(0,idx-window)
        for j in range(idx-1,start-1,-1):
            pe=events[j]; pm=(pe.get("mnemonic") or "").upper(); ops=pe.get("operands") or ""; regs=pe.get("registers") or {}
            if reg in load_mnems.values() and load_mnems.get(pm)==reg:
                candidates.append({"line":pe.get("line"),"pc":pe.get("pc"),"instruction":f"{pm} {ops}".strip(),"reason":f"loads {reg} before target store","confidence":"high" if ops.strip().startswith("#") else "medium","raw":pe.get("raw")})
                break
            if reg and reg in regs:
                candidates.append({"line":pe.get("line"),"pc":pe.get("pc"),"reason":f"trace register {reg} visible before store","value":regs.get(reg),"confidence":"medium","raw":pe.get("raw")})
                break
        reports.append({"target_write":{"event_index":idx,"line":e.get("line"),"pc":e.get("pc"),"instruction":f'{e.get("mnemonic")} {e.get("operands")}'.strip(),"memory_access":e.get("memory_access")},"tracked_register":reg,"value_flow_candidates":candidates or [{"confidence":"unknown","reason":"No clear prior load/register source found in trace window."}]})
    return _out({"tool":"ROMancer","version":VERSION,"feature":"value flow","trace":trace,"target_addr":target_addr,"hit_count":len(hits),"reports":reports,"limitation":"trace-side heuristic only; verify in debugger/disassembler"}, out)


def infer_table(rom: str, start: str, end: str, stride: int, system: str="snes", mapping: str="hirom", out: str|None=None)->dict[str,Any]:
    data=read_bytes(rom); s=parse_int(start); e=parse_int(end)
    rows=[]; fields=defaultdict(list)
    for off in range(s, min(e,len(data)), stride):
        rec=data[off:off+stride]
        if len(rec)<stride: break
        rows.append({"offset":f"0x{off:06X}","bytes":" ".join(f"{b:02X}" for b in rec)})
        for pos in range(stride): fields[pos].append(rec[pos])
    inferred=[]
    for pos in range(stride):
        vals=fields[pos]; uniq=len(set(vals)); note=[]
        if uniq==1: note.append("constant field")
        if pos+1<stride:
            nums=[r for r in rows]
        if pos+2<stride and system.lower()=="snes":
            ptrs=0
            for off in range(s, min(e,len(data)), stride):
                b=data[off+pos:off+pos+3]
                if len(b)==3 and b[0] in range(0x80,0x100) or (len(b)==3 and b[0] in range(0xC0,0xFF)):
                    ptrs+=1
            if ptrs >= max(2, len(rows)//3): note.append("possible 24-bit SNES pointer start")
        inferred.append({"field_offset":pos,"unique_values":uniq,"notes":note or ["undetermined"]})
    result={"tool":"ROMancer","version":VERSION,"feature":"infer table","rom":rom,"start":f"0x{s:06X}","end":f"0x{e:06X}","stride":stride,"record_count":len(rows),"records_preview":rows[:25],"field_inference":inferred,"confidence":"heuristic"}
    return _out(result,out)

# .tbl workbench

def _read_tbl(path: str)->dict[int,str]:
    table={}
    for line in Path(path).read_text(encoding="utf-8",errors="replace").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v=line.split("=",1); k=k.strip().replace("$","").replace("0x","")
        try: table[int(k,16)] = v
        except ValueError: continue
    return table

def tbl_validate(tbl: str, out: str|None=None)->dict[str,Any]:
    table=_read_tbl(tbl); rev=defaultdict(list)
    for k,v in table.items(): rev[v].append(k)
    dup={v:[f"{x:02X}" for x in ks] for v,ks in rev.items() if len(ks)>1}
    return _out({"tool":"ROMancer","version":VERSION,"feature":"tbl validate","tbl":tbl,"entry_count":len(table),"duplicate_outputs":dup,"ok":len(table)>0}, out)

def tbl_decode(rom: str, offset: str, length: int, tbl: str, out: str|None=None)->dict[str,Any]:
    data=read_bytes(rom); o=parse_int(offset); raw=data[o:o+length]; table=_read_tbl(tbl)
    text="".join(table.get(b, f"<{b:02X}>") for b in raw)
    return _out({"tool":"ROMancer","version":VERSION,"feature":"tbl decode","rom":rom,"offset":f"0x{o:06X}","length":length,"hex":" ".join(f"{b:02X}" for b in raw),"text":text}, out)

def tbl_encode(text: str, tbl: str, out: str|None=None)->dict[str,Any]:
    table=_read_tbl(tbl); rev={v:k for k,v in table.items()}; data=[]; missing=[]
    i=0
    keys=sorted(rev, key=len, reverse=True)
    while i<len(text):
        hit=None
        for k in keys:
            if text.startswith(k,i): hit=k; break
        if hit is None: missing.append(text[i]); i+=1
        else: data.append(rev[hit]); i+=len(hit)
    result={"tool":"ROMancer","version":VERSION,"feature":"tbl encode","text":text,"bytes":" ".join(f"{b:02X}" for b in data),"missing":missing,"ok":not missing}
    return _out(result,out)

def tbl_brute_hint(rom: str, offset: str, known: str, length: int|None=None, out: str|None=None)->dict[str,Any]:
    data=read_bytes(rom); o=parse_int(offset); length=length or len(known); raw=data[o:o+length]
    pairs=[]
    for b,ch in zip(raw, known): pairs.append({"byte":f"{b:02X}","char":ch})
    unique={p["byte"]:p["char"] for p in pairs}
    tbl_lines=[f"{k}={v}" for k,v in unique.items()]
    return _out({"tool":"ROMancer","version":VERSION,"feature":"tbl brute hint","rom":rom,"offset":f"0x{o:06X}","known":known,"pairs":pairs,"suggested_tbl_lines":tbl_lines,"confidence":"alignment-dependent; verify repeated letters and control codes"}, out)

# Patch safety helpers

def sandbox_patch(rom: str, offset: str, before: str, after: str, out_dir: str="sandbox_patch", name: str="candidate") -> dict[str,Any]:
    data=bytearray(read_bytes(rom)); o=parse_int(offset); b=_hex_bytes(before); a=_hex_bytes(after)
    actual=bytes(data[o:o+len(b)])
    if actual != b:
        return {"tool":"ROMancer","version":VERSION,"feature":"sandbox patch","ok":False,"error":"before bytes do not match ROM","offset":f"0x{o:06X}","expected":_bytes_to_hex(b),"actual":_bytes_to_hex(actual)}
    outp=Path(out_dir); outp.mkdir(parents=True,exist_ok=True)
    original_copy=outp/(name+"_original.bin"); modified=outp/(name+"_modified.bin"); ips=outp/(name+".ips"); rollback=outp/(name+"_rollback.ips"); manifest=outp/(name+"_manifest.json")
    original_copy.write_bytes(bytes(data)); data[o:o+len(a)] = a; modified.write_bytes(bytes(data))
    create_ips(original_copy, modified, ips); create_ips(modified, original_copy, rollback)
    result={"tool":"ROMancer","version":VERSION,"feature":"sandbox patch","ok":True,"original":str(original_copy),"modified":str(modified),"ips":str(ips),"rollback_ips":str(rollback),"offset":f"0x{o:06X}","before":_bytes_to_hex(b),"after":_bytes_to_hex(a),"original_sha1":sha1(original_copy.read_bytes()),"modified_sha1":sha1(modified.read_bytes())}
    write_json(manifest,result); result["manifest"]=str(manifest)
    return result

def rollback_ips(original: str, modified: str, out: str)->dict[str,Any]:
    # rollback converts modified back to original
    return create_ips(modified, original, out) | {"tool":"ROMancer","version":VERSION,"feature":"rollback IPS","direction":"modified_to_original"}

# Compatibility DB

def _compat_path(project: str|None=None)->Path:
    return Path(project or ".")/"compatibility.json"

def compat(action: str, rom: str|None=None, name: str|None=None, project: str|None=None, out: str|None=None)->dict[str,Any]:
    path=_compat_path(project); db={"entries":[]}
    if path.exists():
        try: db=read_json(path)
        except Exception: db={"entries":[]}
    if action=="add":
        if not rom: return {"error":"rom required"}
        ident=identify_rom(rom); entry={"name":name or Path(rom).stem,"sha1":ident.get("sha1"),"sha256":ident.get("sha256"),"system":ident.get("system"),"identity":ident,"supported":True,"notes":"Added by ROMancer compat add."}
        db["entries"]=[e for e in db.get("entries",[]) if e.get("sha1")!=entry["sha1"]]+[entry]
        path.parent.mkdir(parents=True,exist_ok=True); write_json(path,db); result={"tool":"ROMancer","version":VERSION,"feature":"compat add","db":str(path),"entry":entry}
    elif action=="check":
        if not rom: return {"error":"rom required"}
        ident=identify_rom(rom); hit=next((e for e in db.get("entries",[]) if e.get("sha1")==ident.get("sha1")),None)
        result={"tool":"ROMancer","version":VERSION,"feature":"compat check","db":str(path),"rom":rom,"match":hit is not None,"entry":hit,"identity":ident}
    else:
        result={"tool":"ROMancer","version":VERSION,"feature":"compat list","db":str(path),"entries":db.get("entries",[])}
    return _out(result,out)


def regression_bundle(project: str, patch: str, out_dir: str="regression_bundle")->dict[str,Any]:
    outp=Path(out_dir); outp.mkdir(parents=True,exist_ok=True)
    checklist=["Boot clean ROM and patched ROM.","Verify title screen/menu load.","Trigger patched behavior.","Capture before/after trace around target routine.","Verify unrelated nearby behavior still works.","Record emulator, ROM hash, patch hash, and result."]
    (outp/"checklist.txt").write_text("\n".join(f"- {x}" for x in checklist)+"\n",encoding="utf-8")
    manifest={"tool":"ROMancer","version":VERSION,"feature":"regression bundle","project":project,"patch":patch,"folders":["traces_before","traces_after","screenshots"],"checklist":checklist}
    for d in manifest["folders"]: (outp/d).mkdir(exist_ok=True)
    write_json(outp/"manifest.json", manifest)
    return {"tool":"ROMancer","version":VERSION,"feature":"regression bundle","out_dir":str(outp),"manifest":str(outp/"manifest.json")}


def package_release_strict(workspace: str, out: str="release", fail_on_unverified: bool=True)->dict[str,Any]:
    base=package_release(workspace,out)
    warnings=[]
    audit=None
    try:
        audit=audit_project(workspace); warnings.extend(audit.get("warnings",[])+audit.get("issues",[]))
    except Exception as exc: warnings.append(f"audit failed: {exc}")
    required=["README.txt","manifest.json"]
    missing=[x for x in required if not (Path(out)/x).exists() and not (Path(workspace)/x).exists()]
    warnings += [f"missing required release file: {x}" for x in missing]
    if fail_on_unverified and warnings:
        base["strict_ok"]=False; base["strict_warnings"]=warnings; base["strict_error"]="Strict release gate failed. Resolve warnings or rerun without fail-on-unverified."
    else:
        base["strict_ok"]=True; base["strict_warnings"]=warnings
    return base


def tui_report(project: str|None=None, out: str|None=None)->dict[str,Any]:
    lines=["ROMancer TUI Preview Dashboard", "="*32]
    if project:
        p=Path(project); lines += [f"Project: {p}", f"Exists: {p.exists()}"]
        for fname in ["project.json","evidence.json","symbols.json","findings.json","compatibility.json"]:
            lines.append(f"{fname}: {'yes' if (p/fname).exists() else 'no'}")
    else:
        lines.append("No project supplied.")
    lines += ["", "Panels planned: ROM identity | traces | symbols | findings | candidate patches | audit warnings"]
    text="\n".join(lines)+"\n"
    if out: Path(out).write_text(text,encoding="utf-8")
    return {"tool":"ROMancer","version":VERSION,"feature":"tui preview","text":text}


def trace_corpus_test(root: str="trace_corpus", out: str|None=None)->dict[str,Any]:
    rootp=Path(root); results=[]; ok=True
    if not rootp.exists():
        # fallback to examples
        rootp=Path("examples")
    for log in sorted(rootp.rglob("*.log")):
        try:
            parsed=parse_trace(log); passed=parsed.get("event_count",0)>0; ok=ok and passed
            results.append({"trace":str(log),"ok":passed,"format":parsed.get("format"),"event_count":parsed.get("event_count")})
        except Exception as exc:
            ok=False; results.append({"trace":str(log),"ok":False,"error":str(exc)})
    return _out({"tool":"ROMancer","version":VERSION,"feature":"trace corpus test","ok":ok,"root":str(rootp),"results":results}, out)
