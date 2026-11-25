"""Measure block placement on a level map of one catalog ROM.

    python -B trace/level_blocks.py <corpus index.json> <sha256 or name prefix> <out.json> [--steps 6] [--png folder]

Records a level the way trace/level_roundtrip.py does, then puts one whole
block of the level where another block is, through the level map, and waits
for the replay checks. Up to --tries places are tried. The result says which
way the change was made ('layout' is the level's own list of blocks: only
that place changes), whether replay confirmed it, and how many places of the
map changed.
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


# Games whose title, story or name entry the automatic play does not get through: how many times to press Start
# (4 frames held, then 150 frames) before the level is recorded. A player starts recording in the stage; the
# automatic play needs to be told how to get there. Each was found by looking at the screen after every press.
START_PRESSES = {
    '085ec6395681': 5,          # Castlevania III: title, story, name entry, then Block 1-01
    '22ac359d66da': 2,          # Castlevania II: title, then GAME START (a third press opens the status screen)
    '49fbd2f61f95': 1,          # Super Mario Land: title, then 1-1
    '42045a1642f7': 2,          # Super Mario Land 2: title, file select (the recorder's own extra press enters the level)
    '0838e531fe22': 2,          # Super Mario World: with 5 intro steps this reaches Yoshi's Island 2
    'ce3245591dd6': 1,          # Ninja Gaiden: the automatic play reaches 1-1 paused
    '9b7ebd1d6fd2': 1,          # Ninja Gaiden II: the same
    '8d5e3d9ce20f': 3,          # Chip 'n Dale: title, character select, then Start skips the story
    '7aaaf89257b1': 1,          # Super Mario Bros. 2: title, then character select (see ROUTES)
    '46160baa0636': 1,          # Sonic The Hedgehog (Mega Drive): Start at the title
    '568e5e9557c4': 1,          # Sonic The Hedgehog 2 (Mega Drive): the same
    'd50c957bd76c': 2,          # Mega Man 3: title, stage select (see ROUTES: Top Man)
    '1e06f2224792': 7,          # Mega Man 4: the title arrives at different times (see ROUTES: Pharaoh Man)
    '010673ff28a6': 5,          # Mega Man 5: (see ROUTES: Charge Man)
    '23f395b26644': 3,          # DuckTales: title, then the land select (Amazon)
    '6f74e8a7575a': 1,          # Mega Man: title, then the stage select (see ROUTES: Bomb Man)
    '9f5fa2106293': 3,          # Mega Man 2: title, story, stage select (see ROUTES: Flash Man)
    '0b3d9e1f01ed': 1,          # Super Mario Bros.: title, then World 1-1
    '1ddc4b429490': 3,          # Super Mario Bros. 3: title, then the World 1 map (see ROUTES)
    '6791433fd1c6': 5,          # Mega Man 6: Plant Man
}


# Games whose first level is reached from a map: the inputs (buttons, frames) played after the Start presses.
# Games where the automatic play before recording (intro steps) already starts a level the walk cannot use.
INTROS = {'6f74e8a7575a': 1, '9f5fa2106293': 1, '0838e531fe22': 5, 'a13fa8164a0a': 1, '7aaaf89257b1': 1, 'd50c957bd76c': 1, '1e06f2224792': 1, '010673ff28a6': 1, '6791433fd1c6': 1, 'f2db2cbdaaed': 1}

ROUTES = {
    'd50c957bd76c': [([], 120), (['right'], 4), ([], 30), (['start'], 4)] + [([], 100)] * 5,                    # Mega Man 3: Top Man
    '1e06f2224792': [([], 120), (['left'], 4), ([], 30), (['start'], 4)] + [([], 120)] * 5,                     # Mega Man 4: Pharaoh Man
    '010673ff28a6': [([], 120), (['left'], 4), ([], 30), (['start'], 4)] + [([], 120)] * 5,                     # Mega Man 5: Charge Man
    '7aaaf89257b1': [(['a'], 4)] + [([], 100)] * 4 + [([], 120), ([], 60), (['right'], 70), ([], 10), (['up'], 10), ([], 120), ([], 60),
                                                        (['right'], 110), ([], 20), (['up'], 10), ([], 120), ([], 120)],       # SMB2: Mario, then the door into 1-1's main area
    'a13fa8164a0a': [([], 120)] * 2 + [(['b'], 4)] + [([], 120)] * 3 + [(['b'], 4)] + [([], 120)] * 4,                      # Wonder Boy: button 1 starts
    '6f74e8a7575a': [([], 120)] + [(['right'], 4), ([], 30)] * 3 + [(['start'], 4)] + [([], 100)] * 4,          # Mega Man: Bomb Man
    '9f5fa2106293': [([], 120), (['down'], 4), ([], 30), (['start'], 4)] + [([], 100)] * 6,                      # Mega Man 2: Flash Man
    '1ddc4b429490': [(['right'], 20), ([], 40), (['up'], 20), ([], 40), (['a'], 4), ([], 200)],   # Super Mario Bros. 3: World 1 map into 1-1
    '6791433fd1c6': [([], 120), (['left'], 4), ([], 30), (['start'], 4)] + [([], 120)] * 5,   # Mega Man 6: Plant Man
    'f2db2cbdaaed': [([], 120)] * 3 + [(['b'], 4), ([], 150), (['down'], 4), ([], 30), (['b'], 4)] + [([], 120)] * 10,   # Wonder Boy III: button 1 starts, then the first room
}

# Longer routes are kept as JSON files in trace/routes/<key>.json: [[buttons, frames], ...]
for _file in (Path(__file__).resolve().parent / 'routes').glob('*.json'):
    ROUTES.setdefault(_file.stem, [tuple(step) for step in json.loads(_file.read_text())])


def record_level(session, steps: int, intro: int, presses: int = 0, route=None) -> dict | None:
    session.record(intro, wait=True)
    for scene_id in list(session.scenes):
        session.forget_scene(scene_id)
    while session.play(1, []).get('busy'):
        time.sleep(0.2)
    for _ in range(presses):
        for buttons, frames in ((['start'], 4), ([], 150)):
            while session.play(frames, buttons).get('busy'):
                time.sleep(0.2)
    if route:
        for buttons, frames in route:
            while session.play(frames, buttons).get('busy'):
                time.sleep(0.2)
        session.level_start('Measured level')
        session.level_auto(steps, wait=True)
        session.level_stop(wait=True)
        job = session.level_job
        return session._level(job['level_id']) if job['state'] == 'finished' else None
    session.level_start('Measured level')
    for attempt in range(3):
        session.level_auto(2, wait=True)
        if len(session.level_rec['scene_ids']) >= 3:
            break
        for buttons, frames in ((['start'], 4), ([], 90)):
            while session.play(frames, buttons).get('busy'):
                time.sleep(0.2)
    session.level_auto(max(1, steps - 2), wait=True)
    session.level_stop(wait=True)
    job = session.level_job
    return session._level(job['level_id']) if job['state'] == 'finished' else None


def measure(index: Path, key: str, steps: int, png, tries: int, intro: int = 8) -> dict:
    from png_roundtrip import load_rom, settle
    from romancer.edit_session import EditSession
    from romancer import graphics_trace as gt
    from romancer import level_layout as ll
    from PIL import Image, ImageChops
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system}
    temp = Path(tempfile.mkdtemp(prefix='romancer-blocks-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    try:
        level = record_level(session, steps, INTROS.get(sha[:12], intro), START_PRESSES.get(sha[:12], 0), ROUTES.get(sha[:12]))
        if level is None:
            out['error'] = session.level_job['message']
            return out
        view = session.level_view(level['id'], 0)
        out['map'] = [view['width'], view['height'], len(level['scene_ids'])]
        mapped = session._level_plane(level, 0)
        where = {(spot.frame, spot.layer, spot.x, spot.y): place for place, spot in mapped.cells.items()}
        skip = gt.rom_skip(session.rom, system)
        small, large = [], []           # (first offset in its table, [map places row by row]) of blocks the map shows whole
        for frame in sorted({spot.frame for spot in mapped.cells.values()}):
            graphics = session._graphics(level['scene_ids'][frame])
            for number, layer_view in enumerate(graphics.layers()):
                layer = layer_view.layer
                grid = ll.find_grid(ll.cell_sources(layer, skip), layer.width, layer.height)
                if grid is None:
                    continue
                out.setdefault('grid', [grid.width, grid.height, grid.step, round(grid.share, 2)])

                def places(x, y, wide, tall):
                    found = [where.get((frame, number, x + dx, y + dy)) for dy in range(tall) for dx in range(wide)]
                    return None if any(p is None for p in found) else found
                for at, first in grid.first.items():
                    got = places(grid.left + at[0] * grid.width, grid.top + at[1] * grid.height, grid.width, grid.height)
                    if got:
                        small.append((first, got))
                table = ll.find_entries(session.rom, grid)
                if table is None:
                    continue
                larger = ll.find_grid(table.placed, max(a[0] for a in grid.first) + 1, max(a[1] for a in grid.first) + 1)
                out.setdefault('larger', [table.width, table.height])
                if larger is None:
                    continue
                for at, first in larger.first.items():
                    got = places(grid.left + (larger.left + at[0] * larger.width) * grid.width,
                                 grid.top + (larger.top + at[1] * larger.height) * grid.height,
                                 larger.width * grid.width, larger.height * grid.height)
                    if got:
                        large.append((first, got))

        def pairs(blocks, count):
            """Paint jobs: a block onto a place that shows a different block, spread over the map."""
            jobs = []
            kinds = {}
            for first, got in blocks:
                kinds.setdefault(first, []).append(got)
            common = sorted(kinds, key=lambda k: -len(kinds[k]))
            # the commonest block is often empty space, and its number may mean something else to the game: start with
            # the blocks after it, and come to it last
            order = [(1, 2), (2, 3), (3, 1), (2, 1), (4, 2), (3, 4), (5, 1), (1, 3), (4, 1), (2, 4), (1, 0), (0, 1)]
            for turn, (target_kind, source_kind) in enumerate(order):
                if max(target_kind, source_kind) >= len(common):
                    continue
                first, other = common[target_kind], common[source_kind]
                places = kinds[first]
                target, source = places[(turn * 7 + len(places) // 2) % len(places)], kinds[other][0]      # a different place each time
                jobs.append([{'col': p[0], 'row': p[1], 'from': list(q)} for p, q in zip(target, source)])
            return jobs[:count]
        out['whole_blocks'] = [len(small), len(large)]
        trials = pairs(large, tries) + pairs(small, tries)
        if 'grid' not in out:
            out['blocks'] = {'skipped_test': 'the level is not built from blocks that are copied from the ROM'}
            return out
        out['blocks'] = {'tried': 0, 'results': []}
        before = Image.open(io.BytesIO(session.level_image(level['id'], 0))).convert('RGB')
        if png:
            before.save(Path(png) / f'{sha[:12]}-blocks-before.png')
        for cells in trials:
            out['blocks']['tried'] += 1
            started = time.time()
            try:
                change = session.propose_level(level['id'], 0, cells)
                done = settle(session, change)
            except (ValueError, TimeoutError) as error:
                out['blocks']['results'].append({'error': str(error)[:300]})
                continue
            result = {'cells': len(cells), 'seconds': round(time.time() - started, 1), 'error': done['error'][:300], 'verified': done['verified'],
                      'method': done.get('method'), 'notes': [n[:200] for n in done.get('notes', [])],
                      'checks': [[c.get('name'), c.get('state')] for c in done.get('checks', [])]}
            if not done['error']:
                after = session.level_view(level['id'], 0)
                result['painted_places_that_did_not_change'] = after['unshown']
                if after['after']:
                    picture = Image.open(io.BytesIO(session.image(after['after']))).convert('RGB')
                    px = view['cell']
                    result['places_changed'] = sum(
                        1 for row in range(view['height']) for col in range(view['width'])
                        if ImageChops.difference(before.crop((col * px, row * px, col * px + px, row * px + px)),
                                                 picture.crop((col * px, row * px, col * px + px, row * px + px))).getbbox())
                    if png:
                        picture.save(Path(png) / f'{sha[:12]}-blocks-after.png')
            out['blocks']['results'].append(result)
            if done.get('method') == 'layout' and done['verified'] and not done['error'] and not result.get('painted_places_that_did_not_change'):
                out['blocks']['layout_confirmed'] = True
                out['blocks']['places_changed'] = result.get('places_changed')
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
    parser.add_argument('--tries', type=int, default=4)
    parser.add_argument('--png', type=Path)
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:
        result = measure(args.index, args.key, args.steps, args.png, args.tries)
    except Exception as error:
        result = {'sha256': args.key, 'error': f'{type(error).__name__}: {error}'[:400]}
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
