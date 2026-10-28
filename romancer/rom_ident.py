from __future__ import annotations

from pathlib import Path
from .util import read_bytes, sha1, sha256, crc32_hex
from .systems.nes import identify_nes
from .systems.snes import identify_snes
from .systems.genesis import identify_genesis
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
    for detector in (identify_nes, identify_snes, identify_genesis):
        result=detector(data)
        if result:return {**base,**result}
    from .system_identify import identify_system
    result=identify_system(p,expected_sha256=base['sha256'])
    labels={'gb':'Game Boy','gbc':'Game Boy Color','sms':'Master System'}
    if result['status']=='IDENTIFIED' and result['system_id'] in labels:
        candidate=next(c for c in result['candidates'] if c['layout_valid'])
        return {**base,'system':labels[result['system_id']],'system_id':result['system_id'],'format':candidate['format'],'notes':result['warnings']}
    return {**base,'system':'Unknown','notes':['No unique supported cartridge layout was recognized.']}
