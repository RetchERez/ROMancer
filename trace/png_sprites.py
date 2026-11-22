"""Measure the sprites PNG (whole characters and objects, put together) on one catalog ROM.

    python -B trace/png_sprites.py <corpus index.json> <sha256 or name prefix> <out.json> [--steps 8] [--save picture.png]

Records scenes, takes the scene whose sprites make the most pictures, saves
the sprites as one PNG, reads it straight back (nothing may be reported as
changed), then draws on the biggest object and loads that. The result says
how many objects were found and whether a replay of the game confirmed the
drawn object.
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


def measure(index: Path, key: str, steps: int, save) -> dict:
    from png_roundtrip import draw, load_rom, settle
    from romancer import scene_png as sp
    from romancer.edit_session import EditSession
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system}
    temp = Path(tempfile.mkdtemp(prefix='romancer-sprites-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    try:
        session.record(steps, wait=True)
        best = None
        for scene_id in session.scenes:
            view = session.graphics_view(scene_id)
            objects, known = sp.sprite_objects(session._graphics(scene_id), view)
            score = len({ident for obj in objects for _, ids in obj['sprites'] for ident in ids if not known[ident]['blank']})
            if best is None or score > best[0]:
                best = (score, scene_id, view, objects, known)
        if best is None:
            out['error'] = 'no scene was recorded'
            return out
        score, scene_id, view, objects, known = best
        out.update(scenes=len(session.scenes), objects=len(objects), pictures=score,
                   biggest=max((len(obj['sprites']) for obj in objects), default=0))
        if not objects or not score:
            out['no_sprites'] = True
            return out
        saved = session.export_picture(scene_id, 'sprites')
        out.update(width=saved['width'], height=saved['height'], indexed=saved['indexed'])
        if save:
            Path(save).write_bytes(saved['png'])
        back = session.import_picture(scene_id, 'sprites', 0, saved['png'])
        out['same_when_read_back'] = back['pictures'] == 0 and not back['colors'] and back['change'] is None
        # draw on the object with the most pictures that can be changed
        places, _, _ = sp.sprite_layout(objects)
        ranked = sorted(range(len(objects)), key=lambda n: -sum(1 for _, ids in objects[n]['sprites'] for ident in ids
                                                                 if known[ident]['editable'] and not known[ident]['blank']))
        for number in ranked[:3]:
            obj, (left, top) = objects[number], places[number]
            squares = []
            for sprite, ids in obj['sprites']:
                for k, ident in enumerate(ids):
                    if known[ident]['editable'] and not known[ident]['blank'] and not (sprite.hflip or sprite.vflip):
                        squares.append((left + sprite.x - obj['left'] + (k % sprite.cols) * 8, top + sprite.y - obj['top'] + (k // sprite.cols) * 8))
            if not squares:
                continue
            edited, drawn = draw(saved['png'], squares[:6])
            if not drawn:
                continue
            started = time.monotonic()
            try:
                result = session.import_picture(scene_id, 'sprites', 0, edited)
            except ValueError as error:
                out.setdefault('errors', []).append(str(error)[:200])
                continue
            row = {'pieces': len(obj['sprites']), 'drawn': drawn, 'read_as_changed': result['pictures']}
            if result['change'] is None:
                row['error'] = result['summary'][:200]
            else:
                final = settle(session, result['change'])
                row.update(seconds=round(time.monotonic() - started, 1), error=final['error'][:200], verified=final['verified'],
                           confirmed=len(final['tiles']) if not final['error'] else 0)
                if final['verified'] and not final['error']:
                    out['confirmed'] = True
                session.remove(final['id'])
            out.setdefault('results', []).append(row)
            if out.get('confirmed'):
                break
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
    parser.add_argument('--save')
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:
        result = measure(args.index, args.key, args.steps, args.save)
    except Exception as error:
        result = {'sha256': args.key, 'error': f'{type(error).__name__}: {error}'[:300]}
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
