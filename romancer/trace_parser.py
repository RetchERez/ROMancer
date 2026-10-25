from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

HEX = r"[0-9A-Fa-f]"

MESEN_6502_RE = re.compile(
    rf"^\s*(?P<pc>{HEX}{{4,6}})\s+"
    rf"(?P<bytes>(?:{HEX}{{2}}\s+){{0,4}})"
    rf"(?P<mnemonic>[A-Za-z]{{3}})\s*(?P<operands>.*?)"
    rf"(?:\s{{2,}}|$)(?P<trailer>.*)$"
)
MESEN_COLON_RE = re.compile(
    rf"^\s*(?P<pc>{HEX}{{4,6}}):\s+"
    rf"(?P<bytes>(?:{HEX}{{2}}\s+){{0,6}})"
    rf"(?P<mnemonic>[A-Za-z]{{3,5}})\s*(?P<operands>.*?)"
    rf"(?:\s{{2,}}|$)(?P<trailer>.*)$"
)
BSNES_RE = re.compile(
    rf"^\s*(?P<pc>{HEX}{{2}}:{HEX}{{4}})\s+"
    rf"(?P<mnemonic>[A-Za-z]{{3,5}})\s*(?P<operands>.*?)"
    rf"(?:\s{{2,}}|\s+A:|\s+a:|$)(?P<trailer>.*)$"
)
BLASTEM_68K_RE = re.compile(
    rf"^\s*(?P<pc>{HEX}{{6,8}})[:\s]+"
    rf"(?:(?P<bytes>(?:(?:{HEX}{{2}}|{HEX}{{4}}|{HEX}{{8}})\s+){{0,6}}))?"
    rf"(?P<mnemonic>[A-Za-z.][A-Za-z0-9_.]{{1,9}})\s*(?P<operands>.*?)"
    rf"(?:\s{{2,}}|\s+D0=|\s+d0=|$)(?P<trailer>.*)$"
)
GENERIC_PC_RE = re.compile(r"(?i)(?:PC\s*[:=]\s*|^\s*)(?:\$|0x)?(?P<pc>[0-9A-F]{4,8})")
REG_COLON_RE = re.compile(r"\b(?P<name>A|X|Y|S|SP|P|D|DB|PB|PC|SR)\s*[:=]\s*(?:\$|0x)?(?P<value>[0-9A-Fa-f]{1,8})\b")
REG_68K_RE = re.compile(r"\b(?P<name>[DA][0-7]|SR|PC|USP|SSP)\s*=\s*(?:\$|0x)?(?P<value>[0-9A-Fa-f]{1,8})\b")
MEM_ANNOT_RE = re.compile(r"(?:@|addr(?:ess)?\s*[:=])\s*(?:\$|0x)?(?P<addr>[0-9A-Fa-f]{4,8})(?:\s*(?:=|->|<-|value\s*)\s*(?:#?\$?|0x)?(?P<value>[0-9A-Fa-f]{1,8}))?", re.I)
WRITE_RE = re.compile(r"(?i)\b(?:write|wrote|stored)\b.*?(?:\$|0x)?(?P<addr>[0-9A-F]{4,8}).*?(?:=|value|val|<-|->).*?(?:#?\$|0x)?(?P<value>[0-9A-F]{1,8})")
READ_RE = re.compile(r"(?i)\b(?:read|loaded)\b.*?(?:\$|0x)?(?P<addr>[0-9A-F]{4,8}).*?(?:=|value|val).*?(?:#?\$|0x)?(?P<value>[0-9A-F]{1,8})")

STORE_MNEMONICS = {"STA", "STX", "STY", "STZ", "MOV", "MOVE", "MOVE.B", "MOVE.W", "MOVE.L", "CLR", "CLR.B", "CLR.W", "CLR.L"}
LOAD_MNEMONICS = {"LDA", "LDX", "LDY", "MOV", "MOVE", "MOVE.B", "MOVE.W", "MOVE.L", "LEA"}
BRANCH_MNEMONICS = {"BRA", "BEQ", "BNE", "BCC", "BCS", "BMI", "BPL", "BVC", "BVS", "JMP", "JSR", "RTS", "RTL", "RTI", "BSR", "DBRA"}


def _clean_hex(value: str | None) -> str | None:
    if value is None:
        return None
    return value.upper().replace("$", "").replace("0X", "")


def _registers(text: str) -> dict[str, str]:
    regs: dict[str, str] = {}
    for m in REG_COLON_RE.finditer(text):
        regs[m.group("name").upper()] = _clean_hex(m.group("value")) or ""
    for m in REG_68K_RE.finditer(text):
        regs[m.group("name").upper()] = _clean_hex(m.group("value")) or ""
    return regs


def _memory_annotations(text: str) -> list[dict[str, Any]]:
    out = []
    for m in MEM_ANNOT_RE.finditer(text):
        item = {"address": _clean_hex(m.group("addr")) or ""}
        if m.group("value"):
            item["value"] = _clean_hex(m.group("value"))
        out.append(item)
    return out


def _addr_in_text(text: str) -> str | None:
    m = re.search(r"(?<!#)(?:\$|0x)([0-9A-Fa-f]{4,8})", text)
    if m:
        return _clean_hex(m.group(1))
    m = re.search(r"\b([0-9A-Fa-f]{4,8})\b", text)
    if m and not re.fullmatch(r"[DA][0-7]", text.strip(), re.I):
        return _clean_hex(m.group(1))
    return None


def _access_from_line(line: str, mnemonic: str | None = None, operands: str = "", registers: dict[str, str] | None = None) -> dict[str, Any] | None:
    registers = registers or {}
    up = mnemonic.upper() if mnemonic else None

    if up:
        anns = _memory_annotations(line)
        if anns:
            if up in STORE_MNEMONICS:
                return {"kind": "write_candidate", **anns[-1], "confidence": "mnemonic+annotation"}
            if up in LOAD_MNEMONICS:
                return {"kind": "read_candidate", **anns[-1], "confidence": "mnemonic+annotation"}

        if up in {"STA", "STX", "STY", "STZ"}:
            addr = _addr_in_text(operands)
            if addr:
                reg = {"STA": "A", "STX": "X", "STY": "Y", "STZ": None}[up]
                item = {"kind": "write_candidate", "address": addr, "confidence": "mnemonic+operand"}
                if reg and reg in registers:
                    item["value"] = registers[reg]
                elif up == "STZ":
                    item["value"] = "00"
                return item

        if up in {"LDA", "LDX", "LDY"} and not operands.strip().startswith("#"):
            addr = _addr_in_text(operands)
            if addr:
                return {"kind": "read_candidate", "address": addr, "confidence": "mnemonic+operand"}

        if up.startswith("MOVE") or up == "MOV":
            parts = [x.strip() for x in operands.split(",")]
            if len(parts) >= 2:
                src = ",".join(parts[:-1])
                dst = parts[-1]
                dst_addr = _addr_in_text(dst)
                src_addr = _addr_in_text(src)
                if dst_addr:
                    src_key = src.upper().split(".")[-1]
                    item = {"kind": "write_candidate", "address": dst_addr, "confidence": "move-destination"}
                    if src_key in registers:
                        item["value"] = registers[src_key]
                    return item
                if src_addr and not src.strip().startswith("#"):
                    return {"kind": "read_candidate", "address": src_addr, "confidence": "move-source"}

    for kind, regex in (("write", WRITE_RE), ("read", READ_RE)):
        m = regex.search(line)
        if m:
            return {"kind": kind, "address": _clean_hex(m.group("addr")), "value": _clean_hex(m.group("value")), "confidence": "explicit-log"}
    return None


def _event_from_match(line: str, lineno: int, match: re.Match[str], parser: str, cpu: str) -> dict[str, Any]:
    gd = match.groupdict()
    pc = _clean_hex(gd.get("pc"))
    mnemonic = (gd.get("mnemonic") or "").upper()
    operands = (gd.get("operands") or "").strip()
    trailer = gd.get("trailer") or ""
    byte_text = (gd.get("bytes") or "").strip()
    full = f"{operands} {trailer}".strip()
    regs = _registers(full)
    event: dict[str, Any] = {
        "line": lineno,
        "type": "instruction",
        "parser": parser,
        "cpu": cpu,
        "pc": pc,
        "mnemonic": mnemonic,
        "operands": operands,
        "raw_bytes": " ".join(byte_text.split()) if byte_text else None,
        "registers": regs,
        "memory_annotations": _memory_annotations(full),
        "raw": line[:500],
    }
    access = _access_from_line(line, mnemonic, operands, regs)
    if access:
        event["memory_access"] = access
    if mnemonic in BRANCH_MNEMONICS:
        event["control_flow"] = "branch_or_call_or_return"
    return event


def detect_trace_format(path: str | Path, sample_lines: int = 200) -> dict[str, Any]:
    p = Path(path)
    counts = Counter()
    total = 0
    for line in p.read_text(errors="replace").splitlines()[:sample_lines]:
        if not line.strip():
            continue
        total += 1
        if BSNES_RE.match(line):
            counts["bsnes-plus"] += 1
        if BLASTEM_68K_RE.match(line) and ("D0=" in line.upper() or "A0=" in line.upper() or re.match(rf"^\s*{HEX}{{6,8}}[:\s]", line)):
            counts["blastem"] += 1
        if MESEN_6502_RE.match(line) or MESEN_COLON_RE.match(line):
            counts["mesen"] += 1
        if GENERIC_PC_RE.search(line):
            counts["generic"] += 1
    # Prefer specific parsers over generic on ties.
    priority = {"bsnes-plus": 4, "blastem": 3, "mesen": 2, "generic": 1}
    best = max(counts.keys(), key=lambda k: (counts[k], priority.get(k, 0))) if counts else "generic"
    return {"trace": str(p), "sampled_nonblank_lines": total, "detected_format": best, "scores": dict(counts)}


def parse_trace(path: str | Path, trace_format: str = "auto", max_events: int | None = None) -> dict[str, Any]:
    p = Path(path)
    detected = detect_trace_format(p)
    fmt = detected["detected_format"] if trace_format == "auto" else trace_format
    events: list[dict[str, Any]] = []
    lines = p.read_text(errors="replace").splitlines()

    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        event = None
        if trace_format == "auto":
            formats = [fmt, "bsnes-plus", "blastem", "mesen", "generic"]
        elif fmt != "generic":
            formats = [fmt, "generic"]
        else:
            formats = ["generic"]

        for candidate in formats:
            if candidate == "mesen":
                m = MESEN_6502_RE.match(line) or MESEN_COLON_RE.match(line)
                if m:
                    event = _event_from_match(line, lineno, m, "mesen", "6502/2A03-or-65C816-like")
                    break
            elif candidate == "bsnes-plus":
                m = BSNES_RE.match(line)
                if m:
                    event = _event_from_match(line, lineno, m, "bsnes-plus", "65C816")
                    break
            elif candidate == "blastem":
                m = BLASTEM_68K_RE.match(line)
                if m:
                    event = _event_from_match(line, lineno, m, "blastem", "68000")
                    break
            elif candidate == "generic":
                pc_match = GENERIC_PC_RE.search(line)
                access = _access_from_line(line)
                regs = _registers(line)
                if pc_match or access or regs:
                    event = {"line": lineno, "type": "generic_trace_line", "parser": "generic", "cpu": "unknown", "pc": _clean_hex(pc_match.group("pc")) if pc_match else None, "registers": regs, "raw": line[:500]}
                    if access:
                        event["memory_access"] = access
                    break
        if event:
            events.append(event)
            if max_events is not None and len(events) >= max_events:
                break

    return _with_summary(str(p), fmt, detected, events, len(lines))


def _with_summary(trace: str, fmt: str, detected: dict[str, Any], events: list[dict[str, Any]], line_count: int) -> dict[str, Any]:
    mnemonic_counts = Counter(e.get("mnemonic") for e in events if e.get("mnemonic"))
    parser_counts = Counter(e.get("parser") for e in events if e.get("parser"))
    access_counts = Counter((e.get("memory_access") or {}).get("kind") for e in events if e.get("memory_access"))
    touched = Counter((e.get("memory_access") or {}).get("address") for e in events if (e.get("memory_access") or {}).get("address"))
    pcs = [e.get("pc") for e in events if e.get("pc")]
    return {"trace": trace, "line_count": line_count, "format_requested_or_detected": fmt, "detection": detected, "event_count": len(events), "summary": {"parser_counts": dict(parser_counts), "top_mnemonics": dict(mnemonic_counts.most_common(25)), "memory_access_counts": {str(k): v for k, v in access_counts.items()}, "top_touched_addresses": dict(touched.most_common(25)), "first_pc": pcs[0] if pcs else None, "last_pc": pcs[-1] if pcs else None}, "events": events}


def trace_summary(path: str | Path, trace_format: str = "auto") -> dict[str, Any]:
    parsed = parse_trace(path, trace_format=trace_format)
    return {k: parsed[k] for k in ("trace", "line_count", "format_requested_or_detected", "detection", "event_count", "summary")}


def filter_trace(path: str | Path, trace_format: str = "auto", addr: str | None = None, mnemonic: str | None = None, pc: str | None = None, max_events: int | None = None) -> dict[str, Any]:
    parsed = parse_trace(path, trace_format=trace_format)
    addr_n = _clean_hex(addr) if addr else None
    mnem_n = mnemonic.upper() if mnemonic else None
    pc_n = _clean_hex(pc) if pc else None
    out = []
    for e in parsed["events"]:
        if addr_n:
            access_addr = (e.get("memory_access") or {}).get("address")
            ann_addrs = [a.get("address") for a in e.get("memory_annotations", [])]
            if addr_n not in [access_addr, *ann_addrs]:
                continue
        if mnem_n and e.get("mnemonic") != mnem_n:
            continue
        if pc_n and e.get("pc") != pc_n:
            continue
        out.append(e)
        if max_events is not None and len(out) >= max_events:
            break
    return {"trace": parsed["trace"], "filters": {"addr": addr_n, "mnemonic": mnem_n, "pc": pc_n}, "match_count": len(out), "events": out}
