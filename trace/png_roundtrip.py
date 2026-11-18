"""Measure the scene PNG export and import on one catalog ROM.

    python -B trace/png_roundtrip.py <corpus index.json> <sha256 or name prefix> <out.json> [--steps 10] [--tiles 6]

Records scenes with the tracing engine, then for the scene with the most
pictures on screen:

  1. saves the picture sheet and every background layer as PNG;
  2. reads each PNG straight back in: nothing may be reported as changed;
  3. draws on up to --tiles pictures that are on screen (one pixel pair each,
     colors of the picture's own palette line), reads the sheet in, and waits
     for the replay checks;
  4. draws on one background layer PNG the same way and reads that in.

The JSON result says what was saved, how many pictures were confirmed and by
which way, and the reason for each picture that was left out.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_rom(index_path: Path, key: str):
    index = json.loads(index_path.read_text())
    for sha, entry in index.items():
        name = Path(entry['member'].split('!')[-1]).name
        if sha.startswith(key) or name.startswith(key):
            data = Path(entry['zip']).read_bytes()
            members = re.split(r'(?<=\.zip)!', entry['member'], flags=re.I)
            for member in members:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    data = archive.read(member)
            return sha, name, entry['system_id'], data, Path(members[-1]).suffix
    raise SystemExit(f'no corpus ROM matches {key!r}')


def settle(session, change, limit=900):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        view = session.change(change['id'])
        if not view['working']:
            return view
        time.sleep(0.3)
    raise TimeoutError('the change never settled')


def draw(png: bytes, squares: list) -> bytes:
    """Swap two palette numbers that the square already uses, in each 8x8 square given as (left, top)."""
    from PIL import Image
    image = Image.open(io.BytesIO(png))
    pixels = image.load()
    done = 0
    for left, top in squares:
        seen = []
        for y in range(8):
            for x in range(8):
                value = pixels[left + x, top + y]
                if value not in seen:
                    seen.append(value)
        if len(seen) < 2:
            continue
        a, b = seen[0], seen[1]
        for y in range(2, 6):
            for x in range(2, 6):
                value = pixels[left + x, top + y]
                pixels[left + x, top + y] = b if value == a else a if value == b else value
        done += 1
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue(), done


def measure(index: Path, key: str, steps: int, tiles: int) -> dict:
    from romancer import scene_png as sp
    from romancer.edit_session import EditSession
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system}
    temp = Path(tempfile.mkdtemp(prefix='romancer-png-'))
    session = None
    try:
        rom = temp / ('game' + suffix)
        rom.write_bytes(data)
        session = EditSession(temp / 'store', rom, system)
        session.record(steps, wait=True)
        if not session.scenes:
            out['error'] = 'no scene was recorded'
            return out
        best, best_view = None, None
        for scene_id in session.scenes:
            view = session.graphics_view(scene_id)
            score = sum(1 for t in view['tiles'] if t['on_screen'] and t['editable'] and not t['blank'])
            if best is None or score > best[0]:
                best, best_view = (score, scene_id), view
        scene_id, view = best[1], best_view
        out['scenes'] = len(session.scenes)
        out['pictures'] = len(view['tiles'])
        # 1 + 2: save, read straight back
        sheet = session.export_picture(scene_id, 'sheet')
        out['sheet'] = {k: sheet[k] for k in ('width', 'height', 'pictures', 'indexed', 'colors')}
        out['sheet']['bytes'] = len(sheet['png'])
        back = session.import_picture(scene_id, 'sheet', 0, sheet['png'])
        out['sheet']['same_when_read_back'] = back['pictures'] == 0 and not back['colors'] and back['change'] is None
        from PIL import Image
        rgb = io.BytesIO()
        Image.open(io.BytesIO(sheet['png'])).convert('RGB').save(rgb, format='PNG')
        back = session.import_picture(scene_id, 'sheet', 0, rgb.getvalue())
        out['sheet']['same_as_plain_rgb'] = back['pictures'] == 0 and not back['colors']
        out['layers'] = []
        for layer in view['layers']:
            row = {'name': layer['name'], 'cells': layer['width'] * layer['height']}
            try:
                picture = session.export_picture(scene_id, 'layer', layer['index'])
                row.update(width=picture['width'], height=picture['height'], bytes=len(picture['png']), indexed=picture['indexed'])
                back = session.import_picture(scene_id, 'layer', layer['index'], picture['png'])
                row['same_when_read_back'] = back['pictures'] == 0 and not back['colors']
                row['png'] = picture['png']
            except ValueError as error:
                row['not_saved'] = str(error)
            out['layers'].append(row)
        # 3: draw on pictures of the sheet
        layout = sp.sheet_layout(view)
        order = {'direct': 0, 'packed': 1, 'patch': 2}
        wanted, per_kind = [], {}
        for number, tile in enumerate(layout['tiles']):
            if tile['on_screen'] and tile['editable'] and not tile['blank'] and len(set(tile['pixels'])) > 1:
                per_kind.setdefault(tile['how'], []).append(number)
        share = max(1, tiles // max(1, len(per_kind)))
        for how in sorted(per_kind, key=lambda h: order.get(h, 9)):
            wanted += per_kind[how][:share]
        wanted = wanted[:tiles]
        if not wanted:
            out['import'] = {'skipped_test': 'no picture on screen can be changed in this scene'}
        else:
            edited, drawn = draw(sheet['png'], [(n % sp.COLUMNS * 8, n // sp.COLUMNS * 8) for n in wanted])
            started = time.monotonic()
            result = session.import_picture(scene_id, 'sheet', 0, edited)
            row = {'drawn': drawn, 'read_as_changed': result['pictures'], 'off_colors': result['off_colors'],
                   'kinds': {how: len([n for n in numbers if n in wanted]) for how, numbers in per_kind.items()}}
            if result['change'] is None:
                row['error'] = result['summary']
            else:
                final = settle(session, result['change'])
                row.update(seconds=round(time.monotonic() - started, 1), error=final['error'], verified=final['verified'],
                           confirmed=len(final['tiles']) if not final['error'] else 0,
                           ways=(final.get('import') or {}).get('ways', {}), together=(final.get('import') or {}).get('together'), replays=(final.get('import') or {}).get('replays'),
                           skipped=[entry['reason'] for entry in (final.get('import') or {}).get('skipped', ())],
                           checks=[[c['name'], c['state']] for c in final['checks']], bytes=final['bytes'])
                if not final['error']:
                    session.keep(result['change']['id'])
                    again = session.export_picture(scene_id, 'sheet')
                    row['kept_shows_in_next_export'] = again['png'] != sheet['png']
                    same = session.import_picture(scene_id, 'sheet', 0, again['png'])
                    row['reading_it_back_changes_nothing'] = same['change'] is None
                    session.remove(result['change']['id'])
            out['import'] = row
        # 4: draw on a background layer
        target = next((row for row in out['layers'] if row.get('same_when_read_back')), None)
        if target is not None:
            layer = next(l for l in view['layers'] if l['name'] == target['name'])
            status = layer['cells']['status']
            by_address = {(t['address']): t for t in view['tiles'] if t['domain'] == layer['tile_domain'] and t['format'] == layer['tile_format']}
            squares = []
            for i, address in enumerate(layer['cells']['tile']):
                tile = by_address.get(address)
                if tile and tile['editable'] and tile['on_screen'] and not tile['blank'] and len(set(tile['pixels'])) > 1:
                    squares.append((i % layer['width'] * layer['cell'], i // layer['width'] * layer['cell']))
                    if len(squares) >= 2:
                        break
            if squares:
                edited, drawn = draw(target['png'], squares)
                started = time.monotonic()
                result = session.import_picture(scene_id, 'layer', layer['index'], edited)
                row = {'layer': layer['name'], 'drawn': drawn, 'read_as_changed': result['pictures'], 'summary': result['summary']}
                if result['change'] is not None:
                    final = settle(session, result['change'])
                    row.update(seconds=round(time.monotonic() - started, 1), error=final['error'], verified=final['verified'],
                               confirmed=len(final['tiles']) if not final['error'] else 0,
                               skipped=[entry['reason'] for entry in (final.get('import') or {}).get('skipped', ())])
                out['layer_import'] = row
        for row in out['layers']:
            row.pop('png', None)
        return out
    except Exception as error:
        out['error'] = f'{type(error).__name__}: {error}'
        return out
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('rom')
    parser.add_argument('out', type=Path)
    parser.add_argument('--steps', type=int, default=10)
    parser.add_argument('--tiles', type=int, default=6)
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:                                         # workers end with this process, however it ends
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import graphics_sweep
        graphics_sweep._tie_children_to_this_process()
    except Exception:
        pass
    result = measure(args.index, args.rom, args.steps, args.tiles)
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
