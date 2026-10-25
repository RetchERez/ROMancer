from __future__ import annotations

from ..util import parse_int


def identify_genesis(data: bytes) -> dict | None:
    if len(data) < 0x200:
        return None
    if data[0x100:0x104] != b"SEGA":
        return None
    console = data[0x100:0x110].decode("ascii", errors="replace").rstrip(" \x00")
    domestic = data[0x120:0x150].decode("ascii", errors="replace").rstrip(" \x00")
    overseas = data[0x150:0x180].decode("ascii", errors="replace").rstrip(" \x00")
    product = data[0x180:0x18E].decode("ascii", errors="replace").rstrip(" \x00")
    checksum = int.from_bytes(data[0x18E:0x190], "big")
    io = data[0x190:0x1A0].decode("ascii", errors="replace").rstrip(" \x00")
    rom_start = int.from_bytes(data[0x1A0:0x1A4], "big")
    rom_end = int.from_bytes(data[0x1A4:0x1A8], "big")
    ram_start = int.from_bytes(data[0x1B4:0x1B8], "big")
    ram_end = int.from_bytes(data[0x1B8:0x1BC], "big")
    region = data[0x1F0:0x200].decode("ascii", errors="replace").rstrip(" \x00")
    return {
        "system": "Genesis/Mega Drive",
        "console": console,
        "domestic_title": domestic,
        "overseas_title": overseas,
        "product_code": product,
        "checksum_header": f"0x{checksum:04X}",
        "io_support": io,
        "rom_range": f"0x{rom_start:08X}-0x{rom_end:08X}",
        "ram_range": f"0x{ram_start:08X}-0x{ram_end:08X}",
        "region": region,
        "notes": [
            "68K ROM is commonly mapped from 0x000000 upward, but mapper hardware and bank switching can alter behavior."
        ],
    }


def classify_68k_address(addr: str) -> dict:
    a = parse_int(addr) & 0xFFFFFF
    if 0x000000 <= a <= 0x3FFFFF:
        kind = "68K ROM window, common cartridge area"
        confidence = "medium"
    elif 0xA00000 <= a <= 0xA0FFFF:
        kind = "Z80 address/control area"
        confidence = "medium"
    elif 0xC00000 <= a <= 0xC0001F:
        kind = "VDP ports"
        confidence = "high"
    elif 0xE00000 <= a <= 0xFFFFFF:
        kind = "68K work RAM mirror/range"
        confidence = "high"
    else:
        kind = "unclassified or hardware-specific area"
        confidence = "low"
    return {
        "system": "Genesis/Mega Drive",
        "address": f"0x{a:06X}",
        "classification": kind,
        "confidence": confidence,
    }
