from __future__ import annotations


import re
from pathlib import Path
from typing import Any

from .trace_parser import parse_trace
from .systems.snes import snes_to_offset
from .systems.genesis import classify_68k_address
from .util import parse_int, write_json, read_json

CALL_MNEMS = {"JSR", "JSL", "BSR", "JSR.W", "JSR.L"}
RETURN_MNEMS = {"RTS", "RTL", "RTI", "RTE"}
BRANCH_MNEMS = {"BRA", "BEQ", "BNE", "BCC", "BCS", "BMI", "BPL", "BVC", "BVS", "JMP", "DBRA"}
LOAD_MNEMS = {"LDA", "LDX", "LDY", "MOVE", "MOVE.B", "MOVE.W", "MOVE.L", "MOV", "LEA"}
STORE_MNEMS = {"STA", "STX", "STY", "STZ", "MOVE", "MOVE.B", "MOVE.W", "MOVE.L", "MOV", "CLR", "CLR.B", "CLR.W", "CLR.L"}
IMM_RE = re.compile(r"#?\$?([0-9A-Fa-f]{1,8})")


def clean_hex(value: str | None) -> str | None:
    if value is None:
        return None
    return value.upper().replace("$", "").replace("0X", "").replace(":", "")


def addr_variants(addr: str) -> set[str]:
    a = clean_hex(addr) or ""
    out = {a}
    if len(a) > 4:
        out.add(a[-4:])
    if len(a) == 4:
        out.update({"7E" + a, "7F" + a, "00" + a, "FF" + a})
    return out


def addr_matches(candidate: str | None, target: str) -> bool:
    c = clean_hex(candidate)
    if not c:
        return False
    variants = addr_variants(target)
    if c in variants:
        return True
    t = clean_hex(target) or ""
    return len(t) > 4 and c == t[-4:]


def event_addresses(event: dict[str, Any]) -> list[str]:
    out = []
    ma = event.get("memory_access") or {}
    if ma.get("address"):
        out.append(ma["address"])
    for ann in event.get("memory_annotations", []) or []:
        if ann.get("address"):
            out.append(ann["address"])
    return out


def plan_breakpoints(system: str, addr: str, access: str = "write", goal: str = "", backend: str | None = None) -> dict[str, Any]:
    system_l = system.lower()
    access_l = access.lower()
    steps = [
        "Identify and hash the ROM before debugging.",
        f"Set a {access_l} breakpoint on {addr}.",
        "Enable CPU trace logging shortly before reproducing the event.",
        "Reproduce the in-game action that should touch the address.",
        "Stop as soon as the breakpoint hits, then export the trace log.",
        f"Run: ./run.sh correlate-trace TRACE.log --addr {addr}",
        "Extract the nearby trace window and validate any candidate PC before patching.",
    ]
    caveats = []
    if system_l == "nes":
        caveats.append("NES CPU ROM addresses can be bank-switched. Capture mapper and active PRG bank state before resolving PC to file offset.")
    elif system_l == "snes":
        caveats.append("For SNES WRAM, some debuggers use full bus addresses like 7E0922 while others use local offsets like 0922.")
        caveats.append("Confirm LoROM, HiROM, or ExHiROM mapping before converting PC addresses to ROM offsets.")
    elif system_l == "genesis":
        caveats.append("Genesis 68K RAM is usually FF0000-FFFFFF. VDP ports and Z80 space need separate interpretation.")
    else:
        caveats.append("Unknown system. Treat all address mapping as unverified.")
    return {
        "tool": "ROMancer",
        "version_feature": "v0.3 breakpoint planner",
        "system": system_l,
        "backend": backend or "not specified",
        "goal": goal,
        "target_address": addr,
        "access": access_l,
        "recommended_steps": steps,
        "caveats": caveats,
        "followup_commands": [
            "./run.sh trace-window TRACE.log --line BREAKPOINT_LINE --before 80 --after 20 --out reports/window.txt",
            f"./run.sh find-routine TRACE.log --addr {addr}",
            f"./run.sh report-trace TRACE.log --addr {addr} --out reports/trace_report.txt",
        ],
    }


def debugger_guide(backend: str, system: str, addr: str, access: str = "write") -> dict[str, Any]:
    b = backend.lower()
    s = system.lower()
    access_l = access.lower()
    common = [
        "Open the ROM in the selected emulator/debugger.",
        "Open the debugger and breakpoint panel.",
        f"Create a {access_l} breakpoint for the target address {addr}.",
        "Enable trace logging only around the test event to avoid giant logs.",
        "Reproduce the behavior, stop when the breakpoint hits, and save the trace.",
        f"Import the trace with: ./run.sh correlate-trace TRACE.log --addr {addr}",
    ]
    backend_notes: list[str]
    if b in {"mesen", "mesen2", "mesen-s"}:
        backend_notes = [
            "Use the Debugger window, then add a CPU/Work RAM breakpoint depending on the target address.",
            "For SNES WRAM, try full 7E/7F bus addressing first. If rejected, use the local WRAM offset.",
            "Use the trace logger with a narrow condition if available.",
        ]
    elif b == "bsnes-plus":
        backend_notes = [
            "Use the CPU debugger and breakpoint editor.",
            "For WRAM targets, check whether the breakpoint UI expects bus address or memory-domain local address.",
            "Use instruction trace logging to disk near the breakpoint hit.",
        ]
    elif b == "blastem":
        backend_notes = [
            "Use the BlastEm command-line debugger.",
            "For Genesis RAM, 68K work RAM is commonly addressed in FF0000-FFFFFF.",
            "Use breakpoints/watchpoints and command hooks where practical, then save the debugger log.",
        ]
    elif b == "fceux":
        backend_notes = [
            "Use the debugger and trace logger.",
            "For NES ROM addresses, record mapper and active bank state. CPU $8000-$FFFF is not always a unique file offset.",
        ]
    else:
        backend_notes = ["Generic backend. Manually set breakpoint and export a text trace log."]
    return {
        "backend": b,
        "system": s,
        "target_address": addr,
        "access": access_l,
        "steps": common,
        "backend_notes": backend_notes,
        "output_expected": "A plain text instruction trace or breakpoint log that ROMancer can parse or partially parse.",
    }


def trace_window(path: str | Path, line: int | None = None, addr: str | None = None, before: int = 80, after: int = 20, out: str | None = None) -> dict[str, Any]:
    p = Path(path)
    lines = p.read_text(errors="replace").splitlines()
    chosen = line
    reason = "explicit line"
    if chosen is None and addr:
        parsed = parse_trace(p)
        for e in parsed["events"]:
            if any(addr_matches(a, addr) for a in event_addresses(e)):
                chosen = int(e["line"])
                reason = f"first parsed event touching {addr}"
                break
    if chosen is None:
        return {"error": "No line supplied and no address match found.", "trace": str(p), "addr": addr}
    start = max(1, chosen - before)
    end = min(len(lines), chosen + after)
    block_lines = []
    for n in range(start, end + 1):
        marker = "=>" if n == chosen else "  "
        block_lines.append(f"{marker} {n:08d}: {lines[n-1]}")
    text = "\n".join(block_lines) + "\n"
    result = {"trace": str(p), "selected_line": chosen, "reason": reason, "start_line": start, "end_line": end, "text": text}
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text)
        result["out"] = out
    return result


def _recent_immediates(events: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    found = []
    for e in reversed(events):
        ops = e.get("operands") or ""
        if "#" in ops:
            m = IMM_RE.search(ops)
            if m:
                found.append({"line": e.get("line"), "pc": e.get("pc"), "mnemonic": e.get("mnemonic"), "operands": ops, "immediate": clean_hex(m.group(1))})
        if len(found) >= limit:
            break
    return list(reversed(found))


def _candidate_score(event: dict[str, Any], target: str) -> tuple[int, str]:
    ma = event.get("memory_access") or {}
    mnemonic = (event.get("mnemonic") or "").upper()
    score = 0
    reasons = []
    if any(addr_matches(a, target) for a in event_addresses(event)):
        score += 40
        reasons.append("address match")
    if "write" in str(ma.get("kind", "")):
        score += 30
        reasons.append("write candidate")
    if mnemonic in STORE_MNEMS:
        score += 15
        reasons.append("store/move mnemonic")
    if ma.get("value"):
        score += 10
        reasons.append("value captured")
    return score, ", ".join(reasons) if reasons else "weak match"


def correlate_trace(path: str | Path, addr: str, trace_format: str = "auto", window: int = 80, max_candidates: int = 25) -> dict[str, Any]:
    parsed = parse_trace(path, trace_format=trace_format)
    events = parsed["events"]
    candidates = []
    for idx, e in enumerate(events):
        if any(addr_matches(a, addr) for a in event_addresses(e)):
            score, reasons = _candidate_score(e, addr)
            before_events = events[max(0, idx - window):idx]
            recent_calls = [x for x in before_events if (x.get("mnemonic") or "").upper() in CALL_MNEMS][-8:]
            recent_branches = [x for x in before_events if (x.get("mnemonic") or "").upper() in BRANCH_MNEMS][-8:]
            candidates.append({
                "line": e.get("line"),
                "pc": e.get("pc"),
                "mnemonic": e.get("mnemonic"),
                "operands": e.get("operands"),
                "registers": e.get("registers", {}),
                "memory_access": e.get("memory_access"),
                "score": score,
                "reasons": reasons,
                "recent_immediates": _recent_immediates(before_events),
                "recent_calls": [{"line": x.get("line"), "pc": x.get("pc"), "mnemonic": x.get("mnemonic"), "operands": x.get("operands")} for x in recent_calls],
                "recent_branches": [{"line": x.get("line"), "pc": x.get("pc"), "mnemonic": x.get("mnemonic"), "operands": x.get("operands")} for x in recent_branches],
                "raw": e.get("raw"),
            })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    candidates = candidates[:max_candidates]
    return {
        "trace": str(path),
        "target_address": clean_hex(addr),
        "parsed_format": parsed.get("format_requested_or_detected"),
        "event_count": parsed.get("event_count"),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "interpretation_rules": [
            "A candidate is evidence of a possible read/write only if the trace contains enough information to parse the memory access.",
            "SNES WRAM full addresses may match local 16-bit operands by low word only. Confirm in the debugger before patching.",
            "A PC must be resolved through the correct ROM mapping before editing bytes.",
        ],
    }


def find_routine(path: str | Path, addr: str, trace_format: str = "auto", window: int = 120) -> dict[str, Any]:
    parsed = parse_trace(path, trace_format=trace_format)
    events = parsed["events"]
    targets = []
    for idx, e in enumerate(events):
        if any(addr_matches(a, addr) for a in event_addresses(e)):
            start = max(0, idx - window)
            prev = events[start:idx]
            calls = [x for x in prev if (x.get("mnemonic") or "").upper() in CALL_MNEMS]
            branches = [x for x in prev if (x.get("mnemonic") or "").upper() in BRANCH_MNEMS]
            returns = [x for x in prev if (x.get("mnemonic") or "").upper() in RETURN_MNEMS]
            loads = [x for x in prev if (x.get("mnemonic") or "").upper() in LOAD_MNEMS]
            stores = [x for x in prev if (x.get("mnemonic") or "").upper() in STORE_MNEMS]
            routine_start = calls[-1] if calls else (branches[-1] if branches else None)
            targets.append({
                "target_line": e.get("line"),
                "target_pc": e.get("pc"),
                "target_instruction": f"{e.get('mnemonic','')} {e.get('operands','')}",
                "candidate_routine_anchor": {"line": routine_start.get("line"), "pc": routine_start.get("pc"), "mnemonic": routine_start.get("mnemonic"), "operands": routine_start.get("operands")} if routine_start else None,
                "last_calls": [{"line": x.get("line"), "pc": x.get("pc"), "mnemonic": x.get("mnemonic"), "operands": x.get("operands")} for x in calls[-10:]],
                "last_branches": [{"line": x.get("line"), "pc": x.get("pc"), "mnemonic": x.get("mnemonic"), "operands": x.get("operands")} for x in branches[-10:]],
                "last_returns_before_target": [{"line": x.get("line"), "pc": x.get("pc"), "mnemonic": x.get("mnemonic"), "operands": x.get("operands")} for x in returns[-5:]],
                "recent_immediates": _recent_immediates(prev),
                "recent_load_count": len(loads),
                "recent_store_count": len(stores),
            })
    return {
        "trace": str(path),
        "target_address": clean_hex(addr),
        "window": window,
        "candidate_routine_count": len(targets),
        "candidates": targets[:25],
        "caveat": "This finds trace-local routine anchors. Confirm with a debugger/disassembler before patching.",
    }


def resolve_pc(system: str, pc: str, rom: str | None = None, mapping: str | None = None, headered: bool = False) -> dict[str, Any]:
    s = system.lower()
    result: dict[str, Any]
    if s == "snes":
        if not mapping:
            return {"error": "SNES PC resolution requires --mapping lorom|hirom|exhirom.", "system": s, "pc": pc}
        result = snes_to_offset(pc, mapping, headered)
        if rom and "rom_offset_file" in result:
            off = parse_int(result["rom_offset_file"])
            data = Path(rom).read_bytes()
            result["rom"] = str(rom)
            result["rom_size"] = len(data)
            if 0 <= off < len(data):
                result["byte_at_offset"] = f"0x{data[off]:02X}"
                result["offset_in_range"] = True
            else:
                result["offset_in_range"] = False
                result["warning"] = "Resolved offset is outside the ROM file. Mapping/header assumption may be wrong."
        return result
    if s == "genesis":
        result = classify_68k_address(pc)
        if rom:
            addr = parse_int(pc)
            data = Path(rom).read_bytes()
            result["rom"] = str(rom)
            result["rom_size"] = len(data)
            if result.get("region") == "Cartridge ROM" and 0 <= addr < len(data):
                result["rom_offset_file"] = f"0x{addr:06X}"
                result["byte_at_offset"] = f"0x{data[addr]:02X}"
                result["offset_in_range"] = True
            elif result.get("region") == "Cartridge ROM":
                result["offset_in_range"] = False
        return result
    if s == "nes":
        return {
            "system": "nes",
            "pc": pc,
            "confidence": "partial",
            "warning": "NES CPU $8000-$FFFF addresses often require mapper and active PRG bank state. ROMancer v0.3 does not resolve mapper-state PC addresses automatically.",
            "recommended_next_step": "Capture mapper/bank state from Mesen/FCEUX at the breakpoint, then correlate the banked PRG window manually.",
        }
    return {"error": f"Unknown system: {system}", "pc": pc}


def report_trace(path: str | Path, addr: str | None = None, trace_format: str = "auto", out: str | None = None) -> str:
    parsed = parse_trace(path, trace_format=trace_format)
    lines = [
        "ROMancer v0.3 Trace Report",
        "===========================",
        f"Trace: {path}",
        f"Format: {parsed.get('format_requested_or_detected')}",
        f"Lines: {parsed.get('line_count')}",
        f"Parsed events: {parsed.get('event_count')}",
        "",
        "Top mnemonics:",
    ]
    for k, v in (parsed.get("summary", {}).get("top_mnemonics", {}) or {}).items():
        lines.append(f"- {k}: {v}")
    lines.extend(["", "Top touched addresses:"])
    for k, v in (parsed.get("summary", {}).get("top_touched_addresses", {}) or {}).items():
        lines.append(f"- {k}: {v}")
    if addr:
        corr = correlate_trace(path, addr, trace_format=trace_format)
        lines.extend(["", f"Correlation target: {addr}", f"Candidate count: {corr['candidate_count']}"])
        for c in corr["candidates"][:10]:
            lines.append(f"- line {c.get('line')} PC {c.get('pc')} {c.get('mnemonic')} {c.get('operands')} score={c.get('score')} reasons={c.get('reasons')}")
    text = "\n".join(lines) + "\n"
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text)
    return text


def ai_bundle_v2(project: str | Path, traces: list[str] | None = None, findings: list[str] | None = None, out: str | None = None) -> dict[str, Any]:
    project_p = Path(project)
    bundle: dict[str, Any] = {
        "tool": "ROMancer",
        "bundle_version": "v0.3-ai-evidence-pack-v2",
        "instruction": "Use only the supplied evidence. Separate confirmed facts from hypotheses. Do not invent offsets or claim runtime validation unless a validation artifact is included.",
        "project_path": str(project_p),
        "project": None,
        "evidence": [],
        "trace_summaries": [],
        "extra_findings": [],
    }
    project_json = project_p / "project.json"
    evidence_json = project_p / "evidence" / "evidence.json"
    if project_json.exists():
        bundle["project"] = read_json(project_json)
    if evidence_json.exists():
        bundle["evidence"] = read_json(evidence_json)
    for t in traces or []:
        try:
            parsed = parse_trace(t)
            bundle["trace_summaries"].append({
                "trace": t,
                "format": parsed.get("format_requested_or_detected"),
                "line_count": parsed.get("line_count"),
                "event_count": parsed.get("event_count"),
                "summary": parsed.get("summary"),
            })
        except Exception as exc:
            bundle["trace_summaries"].append({"trace": t, "error": str(exc)})
    for f in findings or []:
        fp = Path(f)
        if fp.exists():
            bundle["extra_findings"].append({"file": str(fp), "text": fp.read_text(errors="replace")[:20000]})
        else:
            bundle["extra_findings"].append({"text": f})
    if out:
        write_json(out, bundle)
    return bundle
