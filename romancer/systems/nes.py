from __future__ import annotations


def identify_nes(data: bytes) -> dict | None:
    if len(data) < 16 or data[:4] != b"NES\x1A":
        return None
    prg_units = data[4]
    chr_units = data[5]
    flags6 = data[6]
    flags7 = data[7]
    mapper = (flags6 >> 4) | (flags7 & 0xF0)
    nes2 = (flags7 & 0x0C) == 0x08
    mirroring = "four-screen" if flags6 & 0x08 else ("vertical" if flags6 & 1 else "horizontal")
    trainer = bool(flags6 & 0x04)
    battery = bool(flags6 & 0x02)
    prg_size = prg_units * 16 * 1024
    chr_size = chr_units * 8 * 1024
    return {
        "system": "NES",
        "format": "NES 2.0" if nes2 else "iNES",
        "header_size": 16,
        "mapper": mapper,
        "prg_rom_bytes": prg_size,
        "chr_rom_bytes": chr_size,
        "mirroring": mirroring,
        "battery_backed_ram": battery,
        "trainer_present": trainer,
        "notes": [
            "NES CPU $8000-$FFFF mapping may be bank-switched. Exact file offset depends on mapper state."
        ],
    }
