from __future__ import annotations

from ..util import printable_score, parse_int

HEADER_CANDIDATES = {
    "LoROM": 0x7FC0,
    "HiROM": 0xFFC0,
    "ExHiROM": 0x40FFC0,
}


def has_copier_header(data: bytes) -> bool:
    return len(data) % 0x8000 == 512


def strip_copier_header(data: bytes) -> tuple[bytes, int]:
    if has_copier_header(data):
        return data[512:], 512
    return data, 0


def _score_header(data: bytes, off: int) -> tuple[int, dict]:
    if off + 0x40 > len(data):
        return (-9999, {})
    h = data[off:off + 0x40]
    title = h[0:21]
    map_mode = h[0x15]
    rom_type = h[0x16]
    rom_size = h[0x17]
    sram_size = h[0x18]
    region = h[0x19]
    checksum_comp = int.from_bytes(h[0x1C:0x1E], "little")
    checksum = int.from_bytes(h[0x1E:0x20], "little")
    score = printable_score(title)
    if ((checksum + checksum_comp) & 0xFFFF) == 0xFFFF:
        score += 20
    if map_mode in (0x20, 0x21, 0x25, 0x30, 0x31, 0x35):
        score += 8
    if 0 <= rom_size <= 0x0F:
        score += 3
    if 0 <= sram_size <= 0x08:
        score += 2
    if region <= 0x0D:
        score += 2
    return score, {
        "title": title.decode("ascii", errors="replace").rstrip(" \x00"),
        "map_mode_byte": f"0x{map_mode:02X}",
        "rom_type_byte": f"0x{rom_type:02X}",
        "rom_size_byte": f"0x{rom_size:02X}",
        "sram_size_byte": f"0x{sram_size:02X}",
        "region_byte": f"0x{region:02X}",
        "checksum": f"0x{checksum:04X}",
        "checksum_complement": f"0x{checksum_comp:04X}",
        "checksum_pair_valid": ((checksum + checksum_comp) & 0xFFFF) == 0xFFFF,
    }


def identify_snes(data: bytes) -> dict | None:
    body, header_skip = strip_copier_header(data)
    best = None
    for mapping, off in HEADER_CANDIDATES.items():
        score, meta = _score_header(body, off)
        if meta:
            candidate = (score, mapping, off, meta)
            if best is None or candidate[0] > best[0]:
                best = candidate
    if not best or best[0] < 5:
        return None
    score, mapping, off, meta = best
    return {
        "system": "SNES",
        "copier_header_bytes": header_skip,
        "mapping_guess": mapping,
        "header_offset_body": f"0x{off:06X}",
        "header_offset_file": f"0x{off + header_skip:06X}",
        "confidence_score": score,
        **meta,
        "notes": [
            "Mapping is heuristic. Confirm with debugger traces before patching code.",
            "Headered ROMs need 0x200 added to raw file offsets when manually hex-editing."
        ],
    }


def snes_to_offset(addr: str, mapping: str, headered: bool = False) -> dict:
    value = parse_int(addr)
    bank = (value >> 16) & 0xFF
    a = value & 0xFFFF
    mapping_l = mapping.lower()
    hdr = 512 if headered else 0
    if mapping_l == "hirom":
        if bank < 0xC0:
            return {"error": "HiROM ROM addresses are usually banks C0-FF for direct file mapping.", "confidence": "low"}
        off = ((bank - 0xC0) << 16) | a
    elif mapping_l == "exhirom":
        if bank >= 0xC0:
            off = ((bank - 0xC0) << 16) | a
        elif 0x40 <= bank <= 0x7D:
            off = 0x400000 + ((bank - 0x40) << 16) + a
        else:
            return {"error": "Address outside common ExHiROM ROM ranges.", "confidence": "low"}
    elif mapping_l == "lorom":
        if a < 0x8000:
            return {"error": "LoROM CPU address low half is not direct ROM window.", "confidence": "low"}
        off = ((bank & 0x7F) << 15) | (a & 0x7FFF)
    else:
        return {"error": f"Unknown SNES mapping: {mapping}", "confidence": "none"}
    return {
        "system": "SNES",
        "mapping": mapping,
        "cpu_address": f"{bank:02X}:{a:04X}",
        "rom_offset_headerless": f"0x{off:06X}",
        "rom_offset_file": f"0x{off + hdr:06X}",
        "headered": headered,
        "confidence": "mapping-dependent",
    }
