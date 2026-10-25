from __future__ import annotations

"""ROMancer v11 address translation helpers.

These helpers only perform mappings that are well-defined from the supplied
system/mapping context. Mapper/bank-dependent cases are returned as unresolved
rather than guessed.
"""

from typing import Any
from .util import parse_int
from .systems.snes import snes_to_offset
from .systems.genesis import classify_68k_address


def gba_bus_to_rom(addr: str | int, rom_size: int | None = None) -> dict[str, Any]:
    a = parse_int(addr) if isinstance(addr, str) else int(addr)
    # GBA Game Pak ROM appears at 0x08000000, with mirrors at 0x0A000000 and
    # 0x0C000000. Each window addresses up to 32 MiB.
    bases = (0x08000000, 0x0A000000, 0x0C000000)
    base = next((b for b in bases if b <= a <= b + 0x01FFFFFF), None)
    if base is None:
        return {"system":"GBA","bus_address":f"0x{a:08X}","resolved":False,
                "reason":"Address is outside documented 32 MiB Game Pak ROM windows."}
    off = a - base
    if rom_size is not None and off >= int(rom_size):
        return {"system":"GBA","bus_address":f"0x{a:08X}","rom_offset":f"0x{off:08X}",
                "resolved":False,"reason":"Mapped ROM offset is beyond supplied ROM size.",
                "window_base":f"0x{base:08X}"}
    return {"system":"GBA","bus_address":f"0x{a:08X}","rom_offset":f"0x{off:08X}",
            "window_base":f"0x{base:08X}","resolved":True,"confidence":"defined mapping"}


def genesis_bus_to_rom(addr: str | int, rom_size: int | None = None) -> dict[str, Any]:
    a = parse_int(addr) if isinstance(addr, str) else int(addr)
    a &= 0xFFFFFF
    cls = classify_68k_address(hex(a))
    if not (0 <= a <= 0x3FFFFF):
        return {**cls,"resolved":False,"reason":"Not in the common direct cartridge ROM window; mapper state may be required."}
    if rom_size is not None and a >= int(rom_size):
        return {**cls,"resolved":False,"rom_offset":f"0x{a:06X}","reason":"Address exceeds supplied ROM size; mapper/banking may be involved."}
    return {**cls,"resolved":True,"rom_offset":f"0x{a:06X}","confidence":"direct cartridge window"}


def translate_address(system: str, addr: str, *, mapping: str | None = None,
                      headered: bool = False, rom_size: int | None = None) -> dict[str, Any]:
    s = system.lower().replace("_","-")
    if s in {"snes","super-nintendo"}:
        if not mapping:
            return {"system":"SNES","address":addr,"resolved":False,"reason":"SNES mapping is required (LoROM/HiROM/ExHiROM)."}
        r = snes_to_offset(addr,mapping,headered)
        return {**r,"resolved":"error" not in r}
    if s in {"genesis","mega-drive","megadrive","md"}:
        return genesis_bus_to_rom(addr,rom_size)
    if s in {"gba","game-boy-advance"}:
        return gba_bus_to_rom(addr,rom_size)
    if s in {"nes"}:
        return {"system":"NES","address":addr,"resolved":False,
                "reason":"NES CPU-to-ROM mapping depends on mapper and active bank state; v11 refuses a mapper-free file offset."}
    if s in {"gb","gbc","game-boy","game-boy-color"}:
        return {"system":"GB/GBC","address":addr,"resolved":False,
                "reason":"GB/GBC cartridge ROM mapping is bank-dependent outside the fixed bank; active MBC state is required."}
    return {"system":system,"address":addr,"resolved":False,"reason":"Unsupported translator."}
