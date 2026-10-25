from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def read_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def crc32_hex(data: bytes) -> str:
    import zlib
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def hexdump(data: bytes, start: int = 0, width: int = 16, max_len: int | None = None) -> str:
    if max_len is not None:
        data = data[:max_len]
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hexs = " ".join(f"{b:02X}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{start+i:08X}  {hexs:<{width*3}}  {text}")
    return "\n".join(lines)


def parse_int(value: str) -> int:
    v = value.strip().replace("_", "")
    if ":" in v:
        bank, addr = v.split(":", 1)
        return (int(bank, 16) << 16) | int(addr, 16)
    if v.lower().startswith("0x"):
        return int(v, 16)
    return int(v, 16)


def printable_score(raw: bytes) -> int:
    score = 0
    for b in raw:
        if b == 0x20:
            score += 1
        elif 0x30 <= b <= 0x39 or 0x41 <= b <= 0x5A or 0x61 <= b <= 0x7A:
            score += 2
        elif b in (0x2D, 0x5F, 0x2E, 0x3A, 0x21, 0x27):
            score += 1
        elif b == 0:
            score -= 1
        else:
            score -= 3
    return score
