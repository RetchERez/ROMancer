from __future__ import annotations


def identify_gba(data: bytes) -> dict | None:
    """Identify a Game Boy Advance cartridge image from the standard 0xC0-byte header."""
    if len(data) < 0xC0 or data[0xB2] != 0x96:
        return None
    title = data[0xA0:0xAC].decode("ascii", errors="replace").rstrip(" \x00")
    game_code = data[0xAC:0xB0].decode("ascii", errors="replace").rstrip(" \x00")
    maker = data[0xB0:0xB2].decode("ascii", errors="replace").rstrip(" \x00")
    expected = (-sum(data[0xA0:0xBD]) - 0x19) & 0xFF
    actual = data[0xBD]
    printable = all((32 <= b <= 126) or b == 0 for b in data[0xA0:0xB2])
    if not printable and expected != actual:
        return None
    return {
        "system": "Game Boy Advance",
        "title": title,
        "game_code": game_code,
        "maker_code": maker,
        "fixed_value": "0x96",
        "unit_code": f"0x{data[0xB3]:02X}",
        "device_type": f"0x{data[0xB4]:02X}",
        "software_version": data[0xBC],
        "header_checksum": f"0x{actual:02X}",
        "header_checksum_expected": f"0x{expected:02X}",
        "header_checksum_valid": actual == expected,
        "notes": [
            "GBA cartridge header identified using the fixed 0x96 byte and header complement check.",
            "Runtime memory addresses still require core-specific or debugger-verified mapping.",
        ],
    }
