from __future__ import annotations

from pathlib import Path
from .util import read_bytes


def byte_diff(original: str | Path, modified: str | Path) -> dict:
    a = read_bytes(original)
    b = read_bytes(modified)
    max_len = max(len(a), len(b))
    hunks = []
    i = 0
    while i < max_len:
        av = a[i] if i < len(a) else None
        bv = b[i] if i < len(b) else None
        if av == bv:
            i += 1
            continue
        start = i
        old = []
        new = []
        while i < max_len:
            av = a[i] if i < len(a) else None
            bv = b[i] if i < len(b) else None
            if av == bv:
                break
            if av is not None:
                old.append(av)
            if bv is not None:
                new.append(bv)
            i += 1
        hunks.append({
            "offset": f"0x{start:06X}",
            "length_old": len(old),
            "length_new": len(new),
            "old_bytes": " ".join(f"{x:02X}" for x in old[:64]) + (" ..." if len(old) > 64 else ""),
            "new_bytes": " ".join(f"{x:02X}" for x in new[:64]) + (" ..." if len(new) > 64 else ""),
        })
    return {
        "original": str(original),
        "modified": str(modified),
        "original_size": len(a),
        "modified_size": len(b),
        "hunk_count": len(hunks),
        "changed_byte_regions": hunks,
    }
