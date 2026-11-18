"""Measure the level map on one catalog ROM.

    python -B trace/level_roundtrip.py <corpus index.json> <sha256 or name prefix> <out.json> [--steps 6] [--png folder]

Lets the game play by itself, as Record more scenes does, while a level is
recorded; puts the map together; then paints on it and waits for the replay
checks:

  1. one place gets the picture of another place of the map (the most common
     picture goes onto a place that shows a different one);
  2. the result says how large the map is, how many captures it kept, whether
     the painted place was confirmed by replay and how many other places of
     the level changed with it.
"""
from __future__ import annotations

import argparse
import collections
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


def wait_for(test, limit, what):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        value = test()
        if value:
            return value
        time.sleep(0.3)
    raise TimeoutError(what)


def measure(index: Path, key: str, steps: int, png, intro: int = 8) -> dict:
    from png_roundtrip import load_rom, settle
    from romancer.edit_session import EditSession
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system}
    temp = Path(tempfile.mkdtemp(prefix='romancer-level-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    try:
        started = time.time()
        session.record(intro, wait=True)               # the same play that Record more scenes uses gets through the menus
        for scene_id in list(session.scenes):
            session.forget_scene(scene_id)
        while session.play(1, []).get('busy'):
            time.sleep(0.2)
        session.level_start('Measured level')
        for attempt in range(3):                        # a game left paused by the menu presses does not move: press Start once
            session.level_auto(2, wait=True)
            if len(session.level_rec['scene_ids']) >= 3:
                break
            for buttons, frames in ((['start'], 4), ([], 90)):
                while session.play(frames, buttons).get('busy'):
                    time.sleep(0.2)
        session.level_auto(max(1, steps - 2), wait=True)
        out['captures'] = len(session.level_rec['scene_ids'])
        out['play_seconds'] = round(time.time() - started, 1)
        started = time.time()
        if os.environ.get('LEVEL_KEEP'):
            import pickle
            Path(os.environ['LEVEL_KEEP']).write_bytes(pickle.dumps(list(session.level_rec['scene_ids'])))
        session.level_stop(wait=True)
        job = session.level_job
        out['build_seconds'] = round(time.time() - started, 1)
        if job['state'] != 'finished':
            out['level'] = {'error': job['message']}
            return out
        level = session._level(job['level_id'])
        view = session.level_view(level['id'], 0)
        screen = session.meta[level['scene_ids'][0]]
        out['level'] = {'scenes': len(level['scene_ids']), 'planes': [
            {'name': p['name'], 'width': p['width'], 'height': p['height'], 'cell': p['px'], 'sections': len(p['sections']),
             'placed': len(p['cells'])} for p in level['planes']],
            'screens': round(view['width'] * view['cell'] / screen['width'], 2)}
        if png:
            (Path(png) / f'{sha[:12]}.png').write_bytes(session.level_image(level['id'], 0))
        # paint: the most common picture onto a place that shows another one, as far into the level as there is one
        mapped = session._level_plane(level, 0)
        by_scene = collections.defaultdict(list)
        for place, spot in mapped.cells.items():
            by_scene[spot.frame].append((place, spot))
        tiles = {}
        for frame, items in by_scene.items():
            graphics = session._graphics(level['scene_ids'][frame])
            layers = graphics.layers()
            for place, spot in items:
                cell = layers[spot.layer].layer.cell(spot.x, spot.y)
                pixels = graphics.tile_pixels(layers[spot.layer].layer.tile_domain, cell.tile_address, layers[spot.layer].layer.tile_format)
                tiles[place] = (pixels, cell.hflip, cell.vflip, cell.palette, cell.status)
        common = collections.Counter(t[:4] for t in tiles.values() if t[0] is not None).most_common(3)
        if len(common) < 2:
            out['paint'] = {'skipped_test': 'the map shows only one picture'}
            return out
        trials = []
        for want, _ in common[:2]:
            source = next(place for place, t in sorted(tiles.items()) if t[:4] == want)
            targets = [place for place, t in sorted(tiles.items(), key=lambda item: (-item[0][0], item[0][1]))
                       if t[0] != want[0] and t[0] is not None and t[4] != 'unknown']
            for target in targets[:1] + targets[len(targets) // 2:len(targets) // 2 + 1]:
                trials.append((source, target))
        out['paint'] = {'tried': 0}
        for source, target in trials[:4]:
            out['paint']['tried'] += 1
            started = time.time()
            try:
                change = session.propose_level(level['id'], 0, [{'col': target[0], 'row': target[1], 'from': list(source)}])
                done = settle(session, change)
            except (ValueError, TimeoutError) as error:
                out['paint'].setdefault('errors', []).append(str(error)[:300])
                continue
            result = {'seconds': round(time.time() - started, 1), 'error': done['error'][:300], 'verified': done['verified'],
                      'method': done.get('method'), 'scenes': done['scene_count'], 'visible': done['visible_count'],
                      'checks': [[c.get('name') or c.get('label'), c.get('state') or c.get('status'), c.get('text', '')[:160]] for c in done.get('checks', [])]}
            if not done['error']:
                after = session.level_view(level['id'], 0)
                if after['after']:
                    from PIL import Image, ImageChops
                    import io
                    a = Image.open(io.BytesIO(session.level_image(level['id'], 0))).convert('RGB')
                    b = Image.open(io.BytesIO(session.image(after['after']))).convert('RGB')
                    px = view['cell']
                    places = sum(1 for row in range(view['height']) for col in range(view['width'])
                                 if ImageChops.difference(a.crop((col * px, row * px, col * px + px, row * px + px)),
                                                          b.crop((col * px, row * px, col * px + px, row * px + px))).getbbox())
                    result['places_changed'] = places
                    if png:
                        b.save(Path(png) / f'{sha[:12]}-after.png')
            out['paint'].setdefault('results', []).append(result)
            if done['verified'] and not done['error']:
                out['paint']['confirmed'] = True
                out['paint']['places_changed'] = result.get('places_changed')
                break
            session.remove(done['id'])
        return out
    finally:
        session.close()
        shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('key')
    parser.add_argument('out', type=Path)
    parser.add_argument('--steps', type=int, default=6)
    parser.add_argument('--png', type=Path)
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:
        result = measure(args.index, args.key, args.steps, args.png)
    except Exception as error:      # the measurement itself failed; say so in the result
        result = {'sha256': args.key, 'error': f'{type(error).__name__}: {error}'[:400]}
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
