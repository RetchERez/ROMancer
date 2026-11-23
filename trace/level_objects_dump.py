"""Exploration: record a level and dump, for every capture, the camera position, the RAM bytes that came from the ROM
(with the ROM offset each came from) and the sprites on screen. Used to work out how a game keeps its objects.

    python -B trace/level_objects_dump.py <corpus index.json> <sha256 or name prefix> <out.json>
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'trace'))


def main() -> None:
    from png_roundtrip import load_rom
    from level_blocks import record_level, START_PRESSES
    from romancer.edit_session import EditSession
    from romancer import provenance as pv
    from romancer import graphics_trace as gt
    index, key, out_path = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    sha, name, system, data, suffix = load_rom(index, key)
    temp = Path(tempfile.mkdtemp(prefix='romancer-objects-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    result = {'name': name, 'system': system, 'skip': gt.rom_skip(data, system), 'captures': []}
    try:
        level = record_level(session, 8, 8, START_PRESSES.get(sha[:12], 0))
        plane = session._level_plane(level, 0)
        for number, window in sorted(plane.windows.items()):
            scene_id = level['scene_ids'][number]
            scene = session._scene(scene_id)
            snap = scene.snapshot
            row = {'frame': session.meta[scene_id]['frame'], 'across': window.across, 'section': window.section, 'domains': {}}
            for dname, domain in snap.domains.items():
                if domain.data is None:
                    continue
                entry = {'size': len(domain.data)}
                if dname in ('wram', 'ram', 'hram', 'oam'):
                    entry['data'] = bytes(domain.data).hex()
                if dname in ('wram', 'ram', 'hram') and domain.tags is not None:
                    tagged = []
                    for at in range(len(domain.data)):
                        tag = domain.tags[at]
                        kind = pv.tag_kind(tag)
                        if kind in (pv.RT_ROM, pv.RT_DERIVED):
                            tagged.append([at, domain.data[at], kind, pv.tag_offset(tag)])
                    entry['from_rom'] = tagged
                row['domains'][dname] = entry
            result['captures'].append(row)
    finally:
        session.close()
        shutil.rmtree(temp, ignore_errors=True)
    out_path.write_text(json.dumps(result))
    print('captures', len(result['captures']))


if __name__ == '__main__':
    main()
