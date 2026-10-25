from __future__ import annotations

import re
from pathlib import Path

SEGA_SYSTEM_ID = b"SEGADISCSYSTEM"
SEGA_DATA_ID = b"SEGADATADISC"


def _decode_field(data: bytes) -> str:
    return data.decode("ascii", errors="replace").rstrip(" \x00")


def identify_segacd_bytes(data: bytes) -> dict | None:
    # Cooked 2048-byte images begin user data at byte 0. Raw MODE1/2352 sectors
    # normally place user data after the 16-byte sync/header area.
    starts = [0, 16]
    base = None
    identifier = None
    for off in starts:
        tag = data[off:off + 16]
        if tag.startswith(SEGA_SYSTEM_ID) or tag.startswith(SEGA_DATA_ID):
            base = off; identifier = _decode_field(tag); break
    if base is None:
        return None
    if len(data) < base + 0x100:
        return {"system": "Sega CD / Mega-CD", "disc_identifier": identifier, "header_data_offset": base}
    return {
        "system": "Sega CD / Mega-CD",
        "disc_identifier": identifier,
        "header_data_offset": base,
        "volume_name": _decode_field(data[base + 0x10:base + 0x1C]),
        "system_name": _decode_field(data[base + 0x20:base + 0x2C]),
        "ip_address": f"0x{int.from_bytes(data[base + 0x30:base + 0x34], 'big'):08X}",
        "ip_load_size": f"0x{int.from_bytes(data[base + 0x34:base + 0x38], 'big'):08X}",
        "ip_entry_address": f"0x{int.from_bytes(data[base + 0x38:base + 0x3C], 'big'):08X}",
        "sp_address": f"0x{int.from_bytes(data[base + 0x40:base + 0x44], 'big'):08X}",
        "sp_load_size": f"0x{int.from_bytes(data[base + 0x44:base + 0x48], 'big'):08X}",
        "notes": [
            "Sega CD/Mega-CD System ID recognized from SEGADISCSYSTEM or SEGADATADISC.",
            "CUE files are resolved to their first referenced track only for identification; multi-track runtime loading should use the CUE path in a compatible core.",
        ],
    }


def identify_segacd_path(path: str | Path, data: bytes | None = None) -> dict | None:
    path = Path(path)
    if path.suffix.lower() == ".cue":
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        # CUE FILE "name.bin" BINARY or FILE name.bin BINARY
        m = re.search(r'^\s*FILE\s+(?:"([^"]+)"|([^\s]+))\s+', text, re.IGNORECASE | re.MULTILINE)
        if not m:
            return {"system": "Sega CD / Mega-CD candidate", "container": "CUE", "cue_file": str(path), "warning": "No FILE entry could be resolved"}
        track_name = m.group(1) or m.group(2)
        track = (path.parent / track_name).resolve()
        if not track.is_file():
            return {"system": "Sega CD / Mega-CD candidate", "container": "CUE", "cue_file": str(path), "referenced_track": str(track), "warning": "Referenced track is not present"}
        raw = track.read_bytes()[:0x1000]
        result = identify_segacd_bytes(raw)
        if result:
            result.update({"container": "CUE", "cue_file": str(path), "referenced_track": str(track)})
            return result
        return {"system": "Sega CD / Mega-CD candidate", "container": "CUE", "cue_file": str(path), "referenced_track": str(track), "warning": "Track did not expose a recognized System ID in the first sector"}
    if data is not None:
        return identify_segacd_bytes(data[:0x1000])
    return None
