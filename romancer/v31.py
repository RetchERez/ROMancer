from __future__ import annotations

"""ROMancer v31 Shadowrun Sega/Mega-CD forensic patching layer.

This module converts the lessons from the Shadowrun Sega/Mega-CD audit into
reusable tooling.  It is intentionally narrow and evidence-oriented:

* raw Mode1/2352 sector math for CUE/BIN Track 1 patching,
* Shadowrun Sega-CD file-family and safety profile,
* BTL actor/name row encoding, decoding, scanning, and reporting,
* route templates for the proven Busora tactical route,
* marker-test manifests for cold-route/runtime proof.

No command packages or emits ROMs, BIOS files, emulator cores, save states,
screenshots, CD audio, or extracted commercial resources.  Local patch commands
write only to paths the caller explicitly supplies.
"""

import csv
import hashlib
import json
import re
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .util import write_json
from . import ROMANCER_VERSION

VERSION = "31.0.0"

SHADOWRUN_SCD_SAFETY = {
    "ADV_*.D": "story/dialogue candidate; patch only mapped rows or proven tables",
    "BTL_*.D": "battle data; actor/name rows and tactical records are mixed; no broad high-bit scrub",
    "COM_*.P": "program/overlay candidate; code/data separation required before patching",
    "SRUN_*.P": "program/overlay candidate; code/data separation required before patching",
    "MSG_*.K": "8x16 1bpp glyph bank, not plain text script",
    "BMSG*.K": "8x16 1bpp battle glyph bank, not plain text script",
    "TMSG01.K": "8x16 1bpp glyph bank, not plain text script",
    "XMSG01.K": "8x16 1bpp glyph bank, not plain text script",
}

SHADOWRUN_PROVEN_FACTS = [
    "Track 1 patching must use raw Mode1/2352 sector math, not extent*2048 flat offsets.",
    "BTL actor/name records are live data and must not be overwritten by broad tactical text cleanup.",
    "For the proven Busora route, BTL_10.D is the runtime source for the visible m2cn1 actor-name row.",
    "Actor-name rows and result grammar/labels are separate systems; changing BTL_10.D actor rows does not translate の攻撃, 目標値, or 成功数.",
    "MSG/BMSG/TMSG/XMSG .K files are glyph banks, not plain text scripts.",
    "Save-state marker tests can be hidden by cached resources; cold-route marker proof is stronger.",
    "CIRCUS/DATANET reaches its welcome panel but does not return under the tested route; treat it as a runtime handoff issue, not a missing text row.",
]

BUSORA_ROUTE_TEMPLATE = [
    {"step": 1, "label": "Silver Moon to Yokohama", "action": "Follow verified Scenario 1 route to Yokohama after Hajime/Bartender setup", "status": "route-dependent"},
    {"step": 2, "label": "Yokohama passers", "action": "Use TALK passer sequence to unlock Hibunro/Gyakushimaya investigation leads", "status": "verified route family"},
    {"step": 3, "label": "CONTACT NAT", "action": "At Hibunro interior, CONTACT NAT until Busora/Gyakushimaya clue appears", "status": "verified"},
    {"step": 4, "label": "Shibuya", "action": "MOVE to Shibuya", "status": "verified"},
    {"step": 5, "label": "Backstreet clue", "action": "LOOK AREA, then TALK PASSER 3 until Gyakushimaya/Busora clue is complete", "status": "verified"},
    {"step": 6, "label": "Correct menu-state warning", "action": "After PASSER 3 the menu may return with TALK highlighted. Do not assume LOOK is selected.", "status": "critical"},
    {"step": 7, "label": "Gyakushimaya", "action": "Open MOVE from the correct menu row and select GYAKUSHIMAYA/backstreet old bar", "status": "verified"},
    {"step": 8, "label": "Busora confrontation", "action": "At Busora exterior, TALK BUSO to enter the tactical battle", "status": "verified"},
    {"step": 9, "label": "Tactical gate", "action": "Capture battle command menu, green roll/result overlay, ITEMS, STATUS, and actor names", "status": "open certification"},
]

# Known fixed actor/name row field locations from the 0.95aa forensic comparison.
# field_offset is relative to the BTL file, not raw Track 1.
KNOWN_BTL_ACTOR_ROWS = {
    "BTL_10.D": [
        {"row": 0, "field_offset": 21396, "field_length": 8, "intended": "RIKUDO", "note": "record starts at 21394 and includes a 2-byte prefix"},
        {"row": 1, "field_offset": 21406, "field_length": 8, "intended": "SHIUN", "note": "actor/name row"},
        {"row": 2, "field_offset": 21416, "field_length": 8, "intended": "MAO", "note": "actor/name row"},
        {"row": 3, "field_offset": 21426, "field_length": 8, "intended": "D-HEAD", "note": "actor/name row"},
        {"row": 4, "field_offset": 21436, "field_length": 8, "intended": "SHA", "note": "actor/name row"},
    ],
    "BTL_11.D": [
        {"row": 0, "field_offset": 21314, "field_length": 8, "intended": "RIKUDO", "note": "record starts at 21312 and includes a 2-byte prefix"},
        {"row": 1, "field_offset": 21324, "field_length": 8, "intended": "SHIUN", "note": "actor/name row"},
        {"row": 2, "field_offset": 21334, "field_length": 8, "intended": "MAO", "note": "actor/name row"},
        {"row": 3, "field_offset": 21344, "field_length": 8, "intended": "D-HEAD", "note": "actor/name row"},
        {"row": 4, "field_offset": 21354, "field_length": 8, "intended": "SHA", "note": "actor/name row"},
    ],
    "BTL_12.D": [
        {"row": 0, "field_offset": 21182, "field_length": 8, "intended": "RIKUDO", "note": "record starts at 21180 and includes a 2-byte prefix"},
        {"row": 1, "field_offset": 21192, "field_length": 8, "intended": "SHIUN", "note": "actor/name row"},
        {"row": 2, "field_offset": 21202, "field_length": 8, "intended": "MAO", "note": "actor/name row"},
        {"row": 3, "field_offset": 21212, "field_length": 8, "intended": "D-HEAD", "note": "actor/name row"},
        {"row": 4, "field_offset": 21222, "field_length": 8, "intended": "SHA", "note": "actor/name row"},
    ],
    "BTL_13.D": [
        {"row": 0, "field_offset": 22318, "field_length": 8, "intended": "RIKUDO", "note": "record starts at 22316 and includes a 2-byte prefix"},
        {"row": 1, "field_offset": 22328, "field_length": 8, "intended": "SHIUN", "note": "actor/name row"},
        {"row": 2, "field_offset": 22338, "field_length": 8, "intended": "MAO", "note": "actor/name row"},
        {"row": 3, "field_offset": 22348, "field_length": 8, "intended": "D-HEAD", "note": "actor/name row"},
        {"row": 4, "field_offset": 22358, "field_length": 8, "intended": "SHA", "note": "actor/name row"},
    ],
    "BTL_14.D": [
        {"row": 0, "field_offset": 21888, "field_length": 8, "intended": "RIKUDO", "note": "record starts at 21886 and includes a 2-byte prefix"},
        {"row": 1, "field_offset": 21898, "field_length": 8, "intended": "SHIUN", "note": "actor/name row"},
        {"row": 2, "field_offset": 21908, "field_length": 8, "intended": "MAO", "note": "actor/name row"},
        {"row": 3, "field_offset": 21918, "field_length": 8, "intended": "D-HEAD", "note": "actor/name row"},
        {"row": 4, "field_offset": 21928, "field_length": 8, "intended": "SHA", "note": "actor/name row"},
    ],
}

# Shadowrun Sega-CD BTL high-bit uppercase alphabet observed in 0.95aa actor rows.
BTL_HIGHBIT_ENCODE = {chr(ord("A") + i): 0xBB + i for i in range(26)}
BTL_HIGHBIT_ENCODE.update({"-": 0xA7, " ": 0x9A})
BTL_HIGHBIT_DECODE = {v: k for k, v in BTL_HIGHBIT_ENCODE.items()}
BTL_HIGHBIT_DECODE.update({0x9A: " "})


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_if(out: str | None, data: Any) -> Any:
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            p.write_text(data, encoding="utf-8", newline="\n")
        else:
            write_json(str(p), data)
    return data


def parse_int(value: int | str) -> int:
    if isinstance(value, int):
        return value
    s = str(value).strip().replace("_", "")
    if s.lower().startswith("0x"):
        return int(s, 16)
    if s.startswith("$"):
        return int(s[1:], 16)
    # Accept plain hex if letters are present.
    if re.search(r"[a-fA-F]", s):
        return int(s, 16)
    return int(s, 10)


def clean_hex(s: str) -> str:
    h = re.sub(r"[^0-9A-Fa-f]", "", s or "")
    if len(h) % 2:
        raise ValueError("hex string has odd number of nibbles")
    return h.lower()


def parse_bytes(*, bytes_hex: str = "", ascii_text: str = "", shadowrun_text: str = "", length: int | None = None, pad_byte: int = 0x9A) -> bytes:
    supplied = [bool(bytes_hex), ascii_text != "", shadowrun_text != ""]
    if sum(1 for x in supplied if x) != 1:
        raise ValueError("supply exactly one of bytes_hex, ascii_text, or shadowrun_text")
    if bytes_hex:
        data = bytes.fromhex(clean_hex(bytes_hex))
    elif ascii_text != "":
        data = ascii_text.encode("ascii", errors="strict")
    else:
        data = encode_btl_text(shadowrun_text, length=None, pad_byte=pad_byte)
    if length is not None:
        if len(data) > length:
            raise ValueError(f"encoded bytes length {len(data)} exceeds requested field length {length}")
        data = data + bytes([pad_byte]) * (length - len(data))
    return data


def raw_mode1_2352_offset(extent: int, file_offset: int, sector_size: int = 2352, payload_offset: int = 16, payload_size: int = 2048) -> int:
    from .cdrom import payload_spans
    if (sector_size, payload_offset, payload_size) != (2352, 16, 2048):
        raise ValueError('only Mode1/2352 with 2048-byte payload at offset 16 is supported')
    return payload_spans(extent, file_offset, 1)[0]['raw_offset']


def sega_cd_map(extent: str, file_offset: str, sector_size: int = 2352, payload_offset: int = 16, payload_size: int = 2048, out: str | None = None) -> dict[str, Any]:
    e = parse_int(extent)
    o = parse_int(file_offset)
    raw = raw_mode1_2352_offset(e, o, sector_size, payload_offset, payload_size)
    result = {
        "tool": "ROMancer",
        "version": VERSION,
        "feature": "v31 raw Mode1/2352 file-to-track mapping",
        "ok": True,
        "formula": "(extent + file_offset // 2048) * 2352 + 16 + (file_offset % 2048)",
        "extent": e,
        "file_offset": o,
        "sector_size": sector_size,
        "payload_offset": payload_offset,
        "payload_size": payload_size,
        "raw_track_offset": raw,
        "raw_track_offset_hex": hex(raw),
        "sector_index": e + o // payload_size,
        "intra_sector_payload_offset": o % payload_size,
    }
    return write_if(out, result)


def sega_cd_patch(track_bin: str, extent: str, file_offset: str, out_bin: str, bytes_hex: str = "", ascii_text: str = "", shadowrun_text: str = "", field_length: int | None = None, before_hex: str = "", dry_run: bool = False, sector_size: int = 2352, payload_offset: int = 16, payload_size: int = 2048, report_out: str | None = None, out: str | None = None, expected_sha256: str = '', resource_size: int | None = None, pad_byte: int | None = None) -> dict[str, Any]:
    from .cd_patch import MAX_REPLACEMENT, check_output_paths, patch_mode1
    result = {'schema_version': 1, 'tool': 'ROMancer', 'version': ROMANCER_VERSION,
              'ok': False, 'written': False, 'dry_run': dry_run}
    try:
        reports = [Path(path) for path in (report_out, out) if path]
        check_output_paths(Path(track_bin), [Path(out_bin), *reports])
        e, fo = parse_int(extent), parse_int(file_offset)
        raw_mode1_2352_offset(e, fo, sector_size, payload_offset, payload_size)
        if field_length is not None and (type(field_length) is not int or not 0 < field_length <= MAX_REPLACEMENT):
            raise ValueError('field length must be between 1 and 16777216')
        if pad_byte is not None and (type(pad_byte) is not int or not 0 <= pad_byte <= 255):
            raise ValueError('padding byte must be between 0 and 255')
        # The CD write path does not silently strip junk from hexadecimal input.
        if bytes_hex:
            bytes.fromhex(bytes_hex)
        chosen_pad = pad_byte if pad_byte is not None else (0x9A if shadowrun_text else 0x20)
        data = parse_bytes(bytes_hex=bytes_hex, ascii_text=ascii_text, shadowrun_text=shadowrun_text)
        if field_length is not None:
            if len(data) > field_length:
                raise ValueError('encoded replacement exceeds field length')
            if bytes_hex and len(data) < field_length and pad_byte is None:
                raise ValueError('hex field padding requires an explicit --pad-byte')
            data += bytes([chosen_pad]) * (field_length - len(data))
        result = patch_mode1(Path(track_bin), Path(out_bin), e, fo, data,
                             expected_sha256=expected_sha256,
                             expected_before=bytes.fromhex(before_hex) if before_hex else None,
                             dry_run=dry_run, resource_size=resource_size)
        result['version'] = ROMANCER_VERSION
        for path in reports:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, indent=2)
                stream.write('\n')
    except (ValueError, OSError) as exc:
        result.update({'ok': False, 'error': str(exc), 'error_code': type(exc).__name__})
    return result


def encode_btl_text(text: str, length: int | None = None, pad_byte: int = 0x9A) -> bytes:
    data = bytearray()
    for ch in text.upper():
        if ch not in BTL_HIGHBIT_ENCODE:
            raise ValueError(f"unsupported BTL high-bit character {ch!r}; supported: A-Z, space, hyphen")
        data.append(BTL_HIGHBIT_ENCODE[ch])
    if length is not None:
        if len(data) > length:
            raise ValueError(f"encoded text length {len(data)} exceeds field length {length}")
        data.extend([pad_byte] * (length - len(data)))
    return bytes(data)


def decode_btl_bytes(data: bytes) -> str:
    chars = []
    for b in data:
        if b in BTL_HIGHBIT_DECODE:
            chars.append(BTL_HIGHBIT_DECODE[b])
        elif 0x20 <= b <= 0x7E:
            chars.append(chr(b))
        elif b == 0x00:
            chars.append("<00>")
        else:
            chars.append(f"<{b:02X}>")
    return "".join(chars).rstrip()


def shadowrun_btl_encode(text: str, length: int | None = None, out: str | None = None) -> dict[str, Any]:
    data = encode_btl_text(text, length=length)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v31 Shadowrun BTL text encode", "ok": True, "text": text, "length": len(data), "hex": data.hex(), "safety": "BTL high-bit uppercase actor/name encoding only"}
    return write_if(out, result)


def shadowrun_btl_decode(bytes_hex: str, out: str | None = None) -> dict[str, Any]:
    data = bytes.fromhex(clean_hex(bytes_hex))
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v31 Shadowrun BTL text decode", "ok": True, "hex": data.hex(), "decoded": decode_btl_bytes(data)}
    return write_if(out, result)


def shadowrun_scd_profile(out: str | None = None) -> dict[str, Any]:
    result = {
        "tool": "ROMancer",
        "version": VERSION,
        "feature": "v31 Shadowrun Sega/Mega-CD profile",
        "ok": True,
        "system": "Sega/Mega-CD",
        "game": "Shadowrun (Japan)",
        "patching_rule": "Mode1/2352 raw Track 1 patching must use extent-aware 2048-payload to 2352-raw mapping",
        "file_families": SHADOWRUN_SCD_SAFETY,
        "proven_facts": SHADOWRUN_PROVEN_FACTS,
        "known_btl_actor_rows": KNOWN_BTL_ACTOR_ROWS,
        "verified_route_templates": {"busora_tactical_battle": BUSORA_ROUTE_TEMPLATE},
        "release_gate": [
            "No ROM, BIOS, core, save state, commercial screenshot, CUE/BIN, CD audio, or extracted resource in safe packages",
            "No broad high-bit BTL scrub",
            "BTL actor-name rows patched only after row/source proof",
            "Tactical result grammar translated only after renderer/source proof",
            "Runtime evidence required before release claim",
        ],
    }
    return write_if(out, result)


def shadowrun_busora_route_template(out: str | None = None) -> dict[str, Any]:
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v31 Busora tactical route template", "ok": True, "route": BUSORA_ROUTE_TEMPLATE}
    return write_if(out, result)


def shadowrun_btl_actor_report(btl_file: str, battle_file: str = "", out: str | None = None) -> dict[str, Any]:
    p = Path(btl_file)
    if not p.exists():
        raise FileNotFoundError(p)
    key = (battle_file or p.name).upper()
    rows = KNOWN_BTL_ACTOR_ROWS.get(key, [])
    data = p.read_bytes()
    report_rows = []
    for r in rows:
        off = int(r["field_offset"])
        ln = int(r["field_length"])
        raw = data[off:off + ln]
        report_rows.append({**r, "actual_hex": raw.hex(), "decoded": decode_btl_bytes(raw), "matches_intended": decode_btl_bytes(raw).strip() == str(r["intended"]).strip()})
    result = {
        "tool": "ROMancer",
        "version": VERSION,
        "feature": "v31 Shadowrun BTL actor row report",
        "ok": bool(rows),
        "file": str(p),
        "file_name_key": key,
        "sha256": sha256_file(p),
        "rows_known": len(rows),
        "rows": report_rows,
        "warning": "Known row report covers proven actor/name rows only; it is not a full BTL parser.",
    }
    return write_if(out, result)


def shadowrun_btl_scan(binary: str, patterns: list[str] | None = None, out: str | None = None) -> dict[str, Any]:
    p = Path(binary)
    if not p.exists():
        raise FileNotFoundError(p)
    data = p.read_bytes()
    pats = patterns or ["RIKUDO", "SHIUN", "MAO", "D-HEAD", "SHA", "BUSORA", "TEST1", "m2cn1", "m2cn2", "m2cn3", "WAIT", "MELEE", "ITEMS", "STATUS"]
    rows = []
    for pat in pats:
        variants: list[tuple[str, bytes]] = []
        try:
            variants.append(("ascii", pat.encode("ascii")))
        except Exception:
            pass
        try:
            variants.append(("btl_highbit", encode_btl_text(pat)))
        except Exception:
            pass
        seen_offsets = set()
        for enc, blob in variants:
            start = 0
            while blob:
                idx = data.find(blob, start)
                if idx < 0:
                    break
                key = (pat, enc, idx)
                if key not in seen_offsets:
                    rows.append({"pattern": pat, "encoding": enc, "offset": idx, "offset_hex": hex(idx), "length": len(blob), "hex": blob.hex()})
                    seen_offsets.add(key)
                start = idx + 1
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v31 Shadowrun BTL/string pattern scan", "ok": True, "file": str(p), "sha256": sha256_file(p), "pattern_count": len(pats), "match_count": len(rows), "matches": rows}
    return write_if(out, result)


def shadowrun_marker_manifest(candidates: str | None = None, out: str | None = None) -> dict[str, Any]:
    # candidates can be a JSON list of dicts with file, extent, file_offset, marker_text/marker_hex.
    cand_data: list[dict[str, Any]] = []
    if candidates:
        raw = Path(candidates).read_text("utf-8", errors="replace") if Path(candidates).exists() else candidates
        loaded = json.loads(raw)
        if isinstance(loaded, list):
            cand_data = loaded
        elif isinstance(loaded, dict):
            cand_data = loaded.get("candidates", [])
    if not cand_data:
        cand_data = [
            {"candidate_id": "busora_btl10_m2cn1_marker", "file": "BTL_10.D", "evidence_status": "runtime-proven source for visible m2cn1 actor-name row", "marker": "TEST1", "required_route": "busora_tactical_battle"},
            {"candidate_id": "green_result_suffix_unknown", "file": "unknown", "evidence_status": "open; do not patch without renderer/table proof", "marker": "not assigned", "required_route": "busora_tactical_battle"},
            {"candidate_id": "battle_items_status_unknown", "file": "unknown", "evidence_status": "open; likely management UI source separate from actor rows", "marker": "not assigned", "required_route": "busora_tactical_battle"},
        ]
    rows = []
    for i, c in enumerate(cand_data):
        row = dict(c)
        row.setdefault("candidate_id", f"candidate_{i:03d}")
        row.setdefault("proof_mode", "cold-route preferred; save-state route is inconclusive if resources are cached")
        row.setdefault("expected_evidence", "before/after frame hash, crop hash, route script hash, patched byte report")
        row.setdefault("safety", "local-only marker build; never package patched Track 1 BIN")
        rows.append(row)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v31 Shadowrun marker-patch manifest", "ok": True, "created_utc": now_iso(), "candidates": rows}
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() == ".csv":
            fields = sorted({k for row in rows for k in row})
            with p.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader(); w.writerows(rows)
        else:
            write_json(str(p), result)
    return result


def v31_capabilities(out: str | None = None) -> dict[str, Any]:
    result = {
        "tool": "ROMancer",
        "version": VERSION,
        "feature": "v31 capabilities",
        "ok": True,
        "commands": [
            "sega-cd-map",
            "sega-cd-patch",
            "shadowrun-scd-profile",
            "shadowrun-busora-route",
            "shadowrun-btl-encode",
            "shadowrun-btl-decode",
            "shadowrun-btl-scan",
            "shadowrun-btl-actor-report",
            "shadowrun-marker-manifest",
            "v31-capabilities",
            "v31-self-test",
        ],
        "primary_lessons": SHADOWRUN_PROVEN_FACTS,
    }
    return write_if(out, result)


def v31_self_test(out: str | None = None) -> dict[str, Any]:
    checks = []
    try:
        raw = raw_mode1_2352_offset(10, 0)
        checks.append({"name": "raw sector zero payload mapping", "ok": raw == 10 * 2352 + 16, "value": raw})
        raw2 = raw_mode1_2352_offset(10, 2048)
        checks.append({"name": "raw sector carry mapping", "ok": raw2 == 11 * 2352 + 16, "value": raw2})
    except Exception as e:
        checks.append({"name": "raw sector mapping", "ok": False, "error": str(e)})
    try:
        enc = encode_btl_text("BUSORA", length=8)
        checks.append({"name": "BTL encode BUSORA", "ok": enc.hex() == "bccfcdc9ccbb9a9a", "hex": enc.hex(), "decoded": decode_btl_bytes(enc)})
    except Exception as e:
        checks.append({"name": "BTL encode", "ok": False, "error": str(e)})
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            from .cdrom import SYNC, repair_mode1
            raw_sector = SYNC + bytes([0, 2, 0, 1]) + bytes(2336)
            data = bytearray(repair_mode1(raw_sector) * 3)
            off = raw_mode1_2352_offset(1, 5)
            data[off:off + 4] = b"ABCD"
            data[2352:4704] = repair_mode1(data[2352:4704])
            src = root / "track.bin"; dst = root / "track_patched.bin"
            src.write_bytes(bytes(data))
            rep = sega_cd_patch(str(src), "1", "5", str(dst), ascii_text="WXYZ", before_hex="41424344", expected_sha256=sha256_file(src))
            patched = dst.read_bytes()[off:off + 4]
            checks.append({"name": "raw-sector patch writes expected bytes", "ok": bool(rep["ok"] and patched == b"WXYZ"), "offset": off})
    except Exception as e:
        checks.append({"name": "raw-sector patch", "ok": False, "error": str(e)})
    ok = all(c.get("ok") for c in checks)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v31 deterministic self-test", "ok": ok, "checks": checks}
    return write_if(out, result)


def add_v31_parsers(sub):
    s = sub.add_parser("sega-cd-map", help="[v31] Convert ISO file extent + file offset to raw Mode1/2352 Track 1 offset"); s.add_argument("--extent", required=True); s.add_argument("--file-offset", required=True); s.add_argument("--sector-size", type=int, default=2352); s.add_argument("--payload-offset", type=int, default=16); s.add_argument("--payload-size", type=int, default=2048); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("sega-cd-patch", help="[v31] Locally patch a raw Mode1/2352 Track 1 BIN using extent-aware mapping"); s.add_argument("track_bin"); s.add_argument("--extent", required=True); s.add_argument("--file-offset", required=True); s.add_argument("--out-bin", required=True); s.add_argument("--bytes-hex", default=""); s.add_argument("--ascii", default=""); s.add_argument("--shadowrun-text", default=""); s.add_argument("--field-length", type=int); s.add_argument("--before-hex", default=""); s.add_argument("--dry-run", action="store_true"); s.add_argument("--sector-size", type=int, default=2352); s.add_argument("--payload-offset", type=int, default=16); s.add_argument("--payload-size", type=int, default=2048); s.add_argument("--report-out"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s.add_argument('--expected-sha256', default='', help='Required for writing: exact source SHA-256')
    s.add_argument('--resource-size', type=parse_int, help='Known logical resource length for bounds checks')
    s.add_argument('--pad-byte', type=parse_int, help='Explicit padding byte (ASCII defaults to space, BTL to 0x9A)')
    s = sub.add_parser("shadowrun-scd-profile", help="[v31] Emit Shadowrun Sega/Mega-CD file-family, safety, and proof profile"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("shadowrun-busora-route", help="[v31] Emit verified Busora tactical route template"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("shadowrun-btl-encode", help="[v31] Encode uppercase Shadowrun BTL actor/name text"); s.add_argument("text"); s.add_argument("--length", type=int); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("shadowrun-btl-decode", help="[v31] Decode Shadowrun BTL actor/name bytes"); s.add_argument("--bytes-hex", required=True); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("shadowrun-btl-scan", help="[v31] Scan a BTL/file blob for ASCII and high-bit BTL candidate strings"); s.add_argument("binary"); s.add_argument("--pattern", action="append"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("shadowrun-btl-actor-report", help="[v31] Report known 0.95aa actor/name rows for BTL_10.D through BTL_14.D"); s.add_argument("btl_file"); s.add_argument("--battle-file", default=""); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("shadowrun-marker-manifest", help="[v31] Build a safe marker-patch manifest for cold-route/runtime proof"); s.add_argument("--candidates"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("v31-capabilities", help="[v31] List v31 Shadowrun Sega-CD forensic capabilities"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("v31-self-test", help="[v31] Run deterministic tests for raw-sector mapping, patching, and BTL encoding"); s.add_argument("--out"); s.add_argument("--json", action="store_true")


def dispatch_v31(args):
    c = getattr(args, "cmd", "")
    if c == "sega-cd-map": return True, sega_cd_map(args.extent, args.file_offset, args.sector_size, args.payload_offset, args.payload_size, args.out)
    if c == "sega-cd-patch": return True, sega_cd_patch(args.track_bin, args.extent, args.file_offset, args.out_bin, bytes_hex=args.bytes_hex, ascii_text=args.ascii, shadowrun_text=args.shadowrun_text, field_length=args.field_length, before_hex=args.before_hex, dry_run=args.dry_run, sector_size=args.sector_size, payload_offset=args.payload_offset, payload_size=args.payload_size, report_out=args.report_out, out=args.out, expected_sha256=args.expected_sha256, resource_size=args.resource_size, pad_byte=args.pad_byte)
    if c == "shadowrun-scd-profile": return True, shadowrun_scd_profile(args.out)
    if c == "shadowrun-busora-route": return True, shadowrun_busora_route_template(args.out)
    if c == "shadowrun-btl-encode": return True, shadowrun_btl_encode(args.text, args.length, args.out)
    if c == "shadowrun-btl-decode": return True, shadowrun_btl_decode(args.bytes_hex, args.out)
    if c == "shadowrun-btl-scan": return True, shadowrun_btl_scan(args.binary, args.pattern, args.out)
    if c == "shadowrun-btl-actor-report": return True, shadowrun_btl_actor_report(args.btl_file, args.battle_file, args.out)
    if c == "shadowrun-marker-manifest": return True, shadowrun_marker_manifest(args.candidates, args.out)
    if c == "v31-capabilities": return True, v31_capabilities(args.out)
    if c == "v31-self-test": return True, v31_self_test(args.out)
    return False, None
