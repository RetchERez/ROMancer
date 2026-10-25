from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any

from .diffing import byte_diff
from .ips import create_ips
from .rom_ident import identify_rom
from .trace_parser import parse_trace
from .workflow import correlate_trace, resolve_pc
from .util import read_bytes, sha1, sha256, crc32_hex, write_json, read_json, parse_int

ROMANCER_VERSION = "31.0.0"


def _hex_bytes(s: str) -> bytes:
    cleaned = s.replace(",", " ").replace("0x", " ").replace("$", " ")
    parts = [p.strip() for p in cleaned.split() if p.strip()]
    out = bytearray()
    for p in parts:
        if len(p) > 2:
            # allow compact strings like 02060706
            if len(p) % 2:
                raise ValueError(f"Odd-length byte token: {p}")
            for i in range(0, len(p), 2):
                out.append(int(p[i:i+2], 16))
        else:
            out.append(int(p, 16))
    return bytes(out)


def _bytes_to_hex(data: bytes, limit: int = 64) -> str:
    shown = data[:limit]
    text = " ".join(f"{b:02X}" for b in shown)
    if len(data) > limit:
        text += " ..."
    return text


def _infer_patch_risk(system: str, offset: str | None = None, change_len: int | None = None, trace_candidate: dict[str, Any] | None = None, change_desc: str = "") -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    s = (system or "unknown").lower()
    desc = (change_desc or "").lower()
    if s == "nes":
        score += 2
        reasons.append("NES ROM addresses may be mapper/bank dependent unless active PRG bank is confirmed.")
    if change_len is not None:
        if change_len <= 2:
            score += 1
            reasons.append("Small byte replacement.")
        elif change_len <= 8:
            score += 2
            reasons.append("Short patch, but multi-byte behavior should be validated.")
        else:
            score += 4
            reasons.append("Large patch hunk increases behavior risk.")
    if trace_candidate:
        mnemonic = (trace_candidate.get("mnemonic") or "").upper()
        operands = (trace_candidate.get("operands") or "").upper()
        if mnemonic in {"STA", "STX", "STY", "MOVE", "MOVE.B", "MOVE.W", "MOVE.L"}:
            score += 3
            reasons.append("Candidate touches a live store/move instruction, which may be shared by multiple callers.")
        if "#" in operands:
            score += 2
            reasons.append("Immediate-value patch candidate. Confirm whether it is data-specific or shared routine logic.")
    if any(word in desc for word in ["table", "record", "palette", "text"]):
        score -= 1
        reasons.append("Description suggests data-table style patch, usually lower risk than code edits.")
    if any(word in desc for word in ["routine", "branch", "jump", "jsr", "jsl", "code", "dma"]):
        score += 3
        reasons.append("Description suggests code/control-flow/DMA patch, which requires runtime validation.")
    if score <= 2:
        level = "low"
    elif score <= 5:
        level = "medium"
    else:
        level = "high"
    return {"risk_level": level, "risk_score": score, "reasons": reasons or ["No specific risk signals supplied."]}


def patch_plan(system: str, rom: str | None = None, trace: str | None = None, addr: str | None = None, goal: str = "", mapping: str | None = None, pc: str | None = None, headered: bool = False, out: str | None = None) -> dict[str, Any]:
    """Create a conservative patch-planning report from trace/address evidence."""
    result: dict[str, Any] = {
        "tool": "ROMancer",
        "version_feature": "v0.4 patch planner",
        "system": system.lower(),
        "goal": goal,
        "status": "candidate_only",
        "rom": None,
        "target_address": addr,
        "trace": trace,
        "candidate_patch_points": [],
        "required_validation": [
            "Confirm the candidate PC in a debugger/disassembler.",
            "Confirm the correct ROM mapping/header state before editing bytes.",
            "Create a duplicate modified ROM and compare before/after traces.",
            "Do not publish a patch until behavior is tested in-game or in a deterministic emulator test.",
        ],
        "warnings": [
            "ROMancer v0.4 does not claim a patch is correct from trace evidence alone.",
        ],
    }
    if rom:
        try:
            result["rom"] = identify_rom(rom)
        except Exception as exc:
            result["rom_error"] = str(exc)
    candidates: list[dict[str, Any]] = []
    if trace and addr:
        corr = correlate_trace(trace, addr)
        for c in corr.get("candidates", [])[:10]:
            entry: dict[str, Any] = {
                "source": "trace_correlation",
                "line": c.get("line"),
                "pc": c.get("pc"),
                "instruction": f"{c.get('mnemonic','')} {c.get('operands','')}`".replace("`", "").strip(),
                "score": c.get("score"),
                "reasons": c.get("reasons"),
                "recent_immediates": c.get("recent_immediates", []),
                "risk": _infer_patch_risk(system, trace_candidate=c, change_desc=goal),
                "notes": [
                    "Treat this as a candidate patch point, not proof.",
                    "If recent immediates contain the desired value, inspect nearby ROM bytes before patching.",
                ],
            }
            if mapping and c.get("pc"):
                try:
                    entry["pc_resolution"] = resolve_pc(system, c.get("pc"), rom=rom, mapping=mapping, headered=headered)
                except Exception as exc:
                    entry["pc_resolution_error"] = str(exc)
            candidates.append(entry)
    if pc:
        entry = {"source": "explicit_pc", "pc": pc, "risk": _infer_patch_risk(system, change_desc=goal)}
        if mapping:
            try:
                entry["pc_resolution"] = resolve_pc(system, pc, rom=rom, mapping=mapping, headered=headered)
            except Exception as exc:
                entry["pc_resolution_error"] = str(exc)
        candidates.append(entry)
    result["candidate_patch_points"] = candidates
    if not candidates:
        result["warnings"].append("No patch candidates found. Provide --trace and --addr, or --pc with mapping details.")
    if out:
        write_json(out, result)
    return result


def validate_patch(original: str, modified: str, trace_before: str | None = None, trace_after: str | None = None, addr: str | None = None, out: str | None = None) -> dict[str, Any]:
    a = read_bytes(original)
    b = read_bytes(modified)
    diff = byte_diff(original, modified)
    result: dict[str, Any] = {
        "tool": "ROMancer",
        "version_feature": "v0.4 patch validator",
        "validation_status": "structural_only",
        "original": {"file": original, "size": len(a), "sha1": sha1(a), "sha256": sha256(a), "crc32": crc32_hex(a)},
        "modified": {"file": modified, "size": len(b), "sha1": sha1(b), "sha256": sha256(b), "crc32": crc32_hex(b)},
        "diff": diff,
        "trace_comparison": None,
        "warnings": [
            "Structural validation does not prove in-game correctness.",
            "Runtime validation requires emulator/gameplay testing.",
        ],
    }
    if trace_before and trace_after:
        before = parse_trace(trace_before)
        after = parse_trace(trace_after)
        comparison: dict[str, Any] = {
            "trace_before": trace_before,
            "trace_after": trace_after,
            "before_event_count": before.get("event_count"),
            "after_event_count": after.get("event_count"),
            "before_format": before.get("format_requested_or_detected"),
            "after_format": after.get("format_requested_or_detected"),
            "target_address": addr,
        }
        if addr:
            comparison["before_correlation"] = correlate_trace(trace_before, addr, max_candidates=10)
            comparison["after_correlation"] = correlate_trace(trace_after, addr, max_candidates=10)
        result["trace_comparison"] = comparison
        result["validation_status"] = "structural_plus_trace_comparison"
    if out:
        write_json(out, result)
    return result


def risk_score(system: str, offset: str | None = None, change: str = "", change_len: int | None = None, out: str | None = None) -> dict[str, Any]:
    before = after = None
    inferred_len = change_len
    if "->" in change:
        left, right = change.split("->", 1)
        try:
            before = _bytes_to_hex(_hex_bytes(left.strip()))
            after_bytes = _hex_bytes(right.strip())
            after = _bytes_to_hex(after_bytes)
            inferred_len = len(after_bytes)
        except Exception:
            pass
    result = {
        "tool": "ROMancer",
        "version_feature": "v0.4 patch risk score",
        "system": system.lower(),
        "offset": offset,
        "change": change,
        "before": before,
        "after": after,
        "analysis": _infer_patch_risk(system, offset=offset, change_len=inferred_len, change_desc=change),
        "caveat": "Risk score is a triage aid, not proof of safety.",
    }
    if out:
        write_json(out, result)
    return result


def asar_skeleton(mapping: str, offset: str | None = None, addr: str | None = None, bytes_text: str = "", comment: str = "ROMancer candidate patch", out: str | None = None) -> str:
    m = mapping.lower()
    if m not in {"lorom", "hirom", "exhirom"}:
        raise ValueError("mapping must be lorom, hirom, or exhirom")
    patch_bytes = _hex_bytes(bytes_text)
    if not patch_bytes:
        raise ValueError("--bytes must contain at least one byte")
    if not addr:
        if not offset:
            raise ValueError("Provide --addr or --offset")
        off = parse_int(offset)
        if m == "hirom":
            addr = f"${0xC00000 + off:06X}"
        elif m == "lorom":
            bank = off // 0x8000
            bank_addr = 0x8000 + (off % 0x8000)
            addr = f"${0x800000 + bank * 0x10000 + bank_addr:06X}"
        else:
            addr = f"; TODO: ExHiROM address for file offset 0x{off:06X} must be confirmed manually"
    elif not addr.startswith("$"):
        addr = "$" + addr.replace(":", "")
    asm = [
        "; ROMancer v0.4 generated Asar skeleton",
        f"; Status: candidate only, requires debugger/runtime validation",
        f"; Note: {comment}",
        f"; Mapping: {m}",
    ]
    if offset:
        asm.append(f"; Source file offset: {offset}")
    asm.extend([
        "",
        m,
        "",
        f"org {addr}",
        "db " + ",".join(f"${b:02X}" for b in patch_bytes),
        "",
    ])
    text = "\n".join(asm)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
    return text


def ips_manifest(original: str, modified: str, patch_out: str, manifest_out: str | None = None, report_out: str | None = None, reason: str = "") -> dict[str, Any]:
    patch_info = create_ips(original, modified, patch_out)
    a = read_bytes(original)
    b = read_bytes(modified)
    diff = byte_diff(original, modified)
    manifest = {
        "tool": "ROMancer",
        "version_feature": "v0.4 IPS manifest",
        "format": "IPS",
        "patch": patch_info,
        "original": {"file": original, "size": len(a), "sha1": sha1(a), "sha256": sha256(a), "crc32": crc32_hex(a)},
        "modified": {"file": modified, "size": len(b), "sha1": sha1(b), "sha256": sha256(b), "crc32": crc32_hex(b)},
        "reason": reason,
        "changes": diff.get("changed_byte_regions", []),
        "validation_status": "unverified_runtime",
    }
    if manifest_out:
        write_json(manifest_out, manifest)
    if report_out:
        lines = [
            "ROMancer v0.4 IPS Manifest Report",
            "=================================",
            f"Patch: {patch_out}",
            f"Reason: {reason or 'not specified'}",
            f"Original SHA1: {manifest['original']['sha1']}",
            f"Modified SHA1: {manifest['modified']['sha1']}",
            f"Changed regions: {len(manifest['changes'])}",
            "",
        ]
        for h in manifest["changes"][:50]:
            lines.append(f"- {h['offset']} old({h['length_old']}): {h['old_bytes']} -> new({h['length_new']}): {h['new_bytes']}")
        Path(report_out).parent.mkdir(parents=True, exist_ok=True)
        Path(report_out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def doctor() -> dict[str, Any]:
    tools = ["python3", "asar", "flips", "mesen", "Mesen", "bsnes-plus", "blastem"]
    found = {t: shutil.which(t) for t in tools}
    return {
        "tool": "ROMancer",
        "version": ROMANCER_VERSION,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
        "external_tools": found,
        "notes": [
            "External emulator/tool paths are optional in v0.4.",
            "Missing asar/flips does not prevent ROMancer's internal IPS generation.",
        ],
    }


def self_test(base_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parents[1]
    examples = root / "examples"
    results: dict[str, Any] = {"tool": "ROMancer", "version": ROMANCER_VERSION, "tests": []}
    try:
        for name in ["mesen_trace_sample.log", "bsnes_plus_trace_sample.log", "blastem_trace_sample.log"]:
            p = examples / name
            parsed = parse_trace(p)
            results["tests"].append({"name": f"parse {name}", "ok": parsed.get("event_count", 0) > 0, "event_count": parsed.get("event_count")})
        risk = risk_score("snes", offset="0x0555C0", change="02 06 -> 07 06")
        results["tests"].append({"name": "risk-score", "ok": "analysis" in risk, "risk_level": risk.get("analysis", {}).get("risk_level")})
        asm = asar_skeleton("hirom", offset="0x0555C0", bytes_text="07 06")
        results["tests"].append({"name": "asar-skeleton", "ok": "db $07,$06" in asm})
    except Exception as exc:
        results["tests"].append({"name": "exception", "ok": False, "error": str(exc)})
    results["ok"] = all(t.get("ok") for t in results["tests"])
    return results


def project_status(project: str | Path) -> dict[str, Any]:
    p = Path(project)
    status: dict[str, Any] = {
        "tool": "ROMancer",
        "version": ROMANCER_VERSION,
        "project": str(p),
        "exists": p.exists(),
        "project_json": None,
        "evidence_count": 0,
        "trace_files": [],
        "report_files": [],
        "patch_files": [],
        "open_questions": [],
    }
    pj = p / "project.json"
    if pj.exists():
        status["project_json"] = read_json(pj)
    ev = p / "evidence" / "evidence.json"
    if ev.exists():
        data = read_json(ev)
        status["evidence_count"] = len(data) if isinstance(data, list) else 0
    for sub, key, pats in [("traces", "trace_files", ["*.log", "*.txt"]), ("reports", "report_files", ["*.txt", "*.json"]), ("patches", "patch_files", ["*.ips", "*.bps", "*.asm", "*.json"] )]:
        d = p / sub
        if d.exists():
            items = []
            for pat in pats:
                items.extend(str(x.relative_to(p)) for x in d.glob(pat))
            status[key] = sorted(set(items))
    if not status["project_json"]:
        status["open_questions"].append("No project.json found. Was this created with romancer init?")
    if status["evidence_count"] == 0:
        status["open_questions"].append("No evidence claims recorded yet.")
    return status
