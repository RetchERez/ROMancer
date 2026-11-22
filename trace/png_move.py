"""Measure a background PNG that rearranges cells, on one catalog ROM.

    python -B trace/png_move.py <corpus index.json> <sha256 or name prefix> <out.json> [--steps 8] [--tries 4]

Records scenes, takes the scene with the most pictures on screen, saves a
background layer as PNG, copies the 8x8 square of one cell that is on screen
over another cell that is on screen and shows a different picture, and loads
the PNG. The result says whether ROMancer read that as a cell that was given
another picture (not as a picture drawn on) and whether a replay confirmed it.
"""
from __future__ import annotations

import argparse
import io
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


def measure(index: Path, key: str, steps: int, tries: int) -> dict:
    from PIL import Image
    from png_roundtrip import load_rom, settle
    from romancer.edit_session import EditSession
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system}
    temp = Path(tempfile.mkdtemp(prefix='romancer-move-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    try:
        session.record(steps, wait=True)
        best = None
        for scene_id in session.scenes:
            view = session.graphics_view(scene_id)
            score = sum(1 for t in view['tiles'] if t['on_screen'] and not t['blank'])
            if best is None or score > best[0]:
                best = (score, scene_id)
        if best is None:
            out['error'] = 'no scene was recorded'
            return out
        scene_id = best[1]
        graphics = session._graphics(scene_id)
        out['tried'] = 0
        for number, view in enumerate(graphics.layers()):
            if view.px != 8 or view.layer.tile_format == 'snes-mode7' or view.source == 'none':
                continue
            cells = [c for c in graphics._on_screen(view) if c.status != 'unknown']
            kinds = {}
            for cell in cells:
                kinds.setdefault((cell.tile_address, cell.hflip, cell.vflip, cell.palette), []).append(cell)
            if len(kinds) < 2:
                continue
            try:
                saved = session.export_picture(scene_id, 'layer', number)
            except ValueError as error:
                out.setdefault('errors', []).append(str(error)[:160])
                continue
            common = sorted(kinds.values(), key=lambda group: -len(group))
            for turn in range(min(tries, len(common) - 1)):
                source = common[turn][0]
                target = common[(turn + 1) % len(common)][len(common[(turn + 1) % len(common)]) // 2]
                image = Image.open(io.BytesIO(saved['png']))
                square = image.crop((source.x * 8, source.y * 8, source.x * 8 + 8, source.y * 8 + 8))
                image.paste(square, (target.x * 8, target.y * 8))
                raw = io.BytesIO()
                image.save(raw, format='PNG')
                out['tried'] += 1
                started = time.time()
                try:
                    result = session.import_picture(scene_id, 'layer', number, raw.getvalue())
                except ValueError as error:
                    out.setdefault('errors', []).append(str(error)[:200])
                    continue
                row = {'layer': view.layer.name, 'moved': result.get('moved', 0), 'pictures': result.get('pictures'),
                       'status': target.status}
                if result.get('change'):
                    done = settle(session, result['change'])
                    row.update(seconds=round(time.time() - started, 1), verified=done['verified'], error=done['error'][:200],
                               method=done.get('method'), kind=done['kind'])
                    if done['verified'] and not done['error'] and result.get('moved'):
                        out['confirmed'] = True
                    session.remove(done['id'])
                out.setdefault('results', []).append(row)
                if out.get('confirmed'):
                    return out
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
    parser.add_argument('--tries', type=int, default=4)
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:
        result = measure(args.index, args.key, args.steps, args.tries)
    except Exception as error:
        result = {'sha256': args.key, 'error': f'{type(error).__name__}: {error}'[:300]}
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
