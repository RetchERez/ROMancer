from __future__ import annotations

from pathlib import Path
from .util import read_bytes, sha1, sha256, crc32_hex
from .systems.nes import identify_nes
from .systems.snes import identify_snes
from .systems.genesis import identify_genesis
from .systems.gba import identify_gba
from .systems.segacd import identify_segacd_path, identify_segacd_bytes


def identify_rom(path: str | Path) -> dict:
    p = Path(path)
    data = read_bytes(p)
    base = {
        "file": str(p),
        "size_bytes": len(data),
        "sha1": sha1(data),
        "sha256": sha256(data),
        "crc32": crc32_hex(data),
    }
    # CUE is a descriptor rather than a ROM image. Resolve its first referenced track
    # for Sega CD identification while preserving hashes for the user-supplied CUE.
    if p.suffix.lower() == ".cue":
        result = identify_segacd_path(p, data)
        if result:
            return {**base, **result}
    for detector in (identify_nes, identify_snes, identify_gba, identify_segacd_bytes, identify_genesis):
        result = detector(data)
        if result:
            return {**base, **result}
    return {**base, "system": "Unknown", "notes": ["No supported ROM/disc header or signature detected."]}
