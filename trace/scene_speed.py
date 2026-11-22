"""Time the things a person waits for in Scenes & colors, on one catalog ROM.

    python -B trace/scene_speed.py <corpus index.json> <sha256 or name prefix> <out.json> [--steps 8]

Records scenes, then times: opening the graphics of every scene for the
first time, opening them all again, saving the pictures PNG of every scene,
and Save all graphics (ZIP). Times are wall-clock seconds on this computer.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'trace'))


def measure(index: Path, key: str, steps: int) -> dict:
    from png_roundtrip import load_rom
    from romancer.edit_session import EditSession
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system}
    temp = Path(tempfile.mkdtemp(prefix='romancer-speed-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)

    def timed(label, work):
        started = time.perf_counter()
        work()
        out[label] = round(time.perf_counter() - started, 2)
    try:
        timed('record', lambda: session.record(steps, wait=True))
        scenes = list(session.scenes)
        out['scenes'] = len(scenes)
        if not scenes:
            return out
        timed('open_every_scene', lambda: [session.graphics_view(s) for s in scenes])
        timed('open_them_again', lambda: [session.graphics_view(s) for s in scenes])
        timed('go_back_and_forth', lambda: [session.graphics_view(s) for s in (scenes + scenes[::-1])])
        timed('pictures_png_of_every_scene', lambda: [session.export_picture(s, 'sheet') for s in scenes])
        timed('save_all_graphics_zip', session.export_everything)
        return out
    finally:
        session.close()
        shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('key')
    parser.add_argument('out', type=Path)
    parser.add_argument('--steps', type=int, default=8)
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:
        result = measure(args.index, args.key, args.steps)
    except Exception as error:
        result = {'sha256': args.key, 'error': f'{type(error).__name__}: {error}'[:300]}
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
