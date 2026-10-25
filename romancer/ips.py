from __future__ import annotations

from pathlib import Path
from .util import read_bytes

MAX_IPS_HUNK = 0xFFFF


def _diff_hunks(a: bytes, b: bytes):
    if len(b) > 0xFFFFFF:
        raise ValueError("IPS supports offsets up to 0xFFFFFF. Use BPS for larger targets.")
    max_len = max(len(a), len(b))
    i = 0
    while i < max_len:
        av = a[i] if i < len(a) else None
        bv = b[i] if i < len(b) else None
        if av == bv:
            i += 1
            continue
        start = i
        out = bytearray()
        while i < max_len:
            av = a[i] if i < len(a) else None
            bv = b[i] if i < len(b) else None
            if av == bv:
                break
            if bv is not None:
                out.append(bv)
            i += 1
        if out:
            yield start, bytes(out)


def create_ips(original: str | Path, modified: str | Path, out: str | Path) -> dict:
    a = read_bytes(original)
    b = read_bytes(modified)
    chunks = []
    patch = bytearray(b"PATCH")
    for start, payload in _diff_hunks(a, b):
        pos = 0
        while pos < len(payload):
            part = payload[pos:pos + MAX_IPS_HUNK]
            off = start + pos
            if off > 0xFFFFFF:
                raise ValueError("IPS hunk offset exceeds 0xFFFFFF.")
            patch += off.to_bytes(3, "big")
            patch += len(part).to_bytes(2, "big")
            patch += part
            chunks.append({"offset": f"0x{off:06X}", "length": len(part)})
            pos += len(part)
    patch += b"EOF"
    outp = Path(out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_bytes(bytes(patch))
    return {"patch": str(outp), "format": "IPS", "hunks": chunks, "hunk_count": len(chunks)}
