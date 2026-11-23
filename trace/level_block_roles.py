"""What does each block of a level DO? Two experiments per block, each a replay of the same walk from power-on.

    python -B trace/level_block_roles.py <corpus index.json> <sha256 or name prefix> <out.json> [--kinds 5] [--steps 10]

For the commonest blocks of a recorded level:
  wall:  a wall three blocks high made of this block, put in the player's path. Does it stop the player?
  floor: a stretch of the floor ahead (three blocks) made of this block. Does the player still get across, or fall?
Then each block is labelled:
  solid       - stops the player and holds the player up
  platform    - holds the player up but does not stop the player from the side (jump-through)
  open        - neither: the player passes through it (sky, decoration)
  stops only  - stops the player from the side but does not hold them up (unusual; worth a look)
How far the player got is read from the screen: the replay is laid out like a level map (trace/level_collision.py).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zlib
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'trace'))


def blocks_of(session, level, system):
    """{(column, row) of a block's corner: (kind, [map places row by row])} for blocks the map shows whole, and the grid."""
    from romancer import graphics_trace as gt
    from romancer import level_layout as ll
    plane = session._level_plane(level, 0)
    where = {(spot.frame, spot.layer, spot.x, spot.y): place for place, spot in plane.cells.items()}
    skip = gt.rom_skip(session.rom, system)
    by_place, grid_size = {}, None
    for frame_no in sorted({spot.frame for spot in plane.cells.values()}):
        graphics = session._graphics(level['scene_ids'][frame_no])
        for number, layer_view in enumerate(graphics.layers()):
            layer = layer_view.layer
            grid = ll.find_grid(ll.cell_sources(layer, skip), layer.width, layer.height)
            if grid is None:
                continue
            grid_size = grid_size or (grid.width, grid.height)
            for at, first in grid.first.items():
                x, y = grid.left + at[0] * grid.width, grid.top + at[1] * grid.height
                got = [where.get((frame_no, number, x + dx, y + dy)) for dy in range(grid.height) for dx in range(grid.width)]
                if all(p is not None for p in got):
                    by_place.setdefault(got[0], (first, got))
    return by_place, grid_size, plane


def paint(session, level, targets, source_places, settle):
    """Paint every target block (its places) with the block at source_places, one block per change; keep the confirmed ones.
    Returns (kept change ids, how many went into the level's own list, how many were tried)."""
    kept, listed = [], 0
    for _, got in targets:
        cells = [{'col': p[0], 'row': p[1], 'from': list(q)} for p, q in zip(got, source_places)]
        try:
            change = session.propose_level(level['id'], 0, cells)
            done = settle(session, change)
        except (ValueError, TimeoutError):
            continue
        if done['error'] or not done['verified']:
            session.remove(done['id'])
            continue
        session.keep(done['id'])
        kept.append(done['id'])
        listed += done.get('method') == 'layout'
    return kept, listed, len(targets)


def measure(index: Path, key: str, kinds_wanted: int, steps: int) -> dict:
    from png_roundtrip import load_rom, settle
    from level_blocks import record_level, START_PRESSES
    from level_collision import replay_screens, progress
    from romancer.edit_session import EditSession
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system, 'blocks': []}
    temp = Path(tempfile.mkdtemp(prefix='romancer-roles-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    try:
        level = record_level(session, steps, 8, START_PRESSES.get(sha[:12], 0))
        if level is None:
            out['error'] = 'no level map: ' + session.level_job['message']
            return out
        view = session.level_view(level['id'], 0)
        px = view['cell']
        by_place, grid, plane = blocks_of(session, level, system)
        if not by_place:
            out['error'] = 'the level is not built from blocks copied from the ROM'
            return out
        bw, bh = grid
        rows = sorted({r for _, r in by_place})
        counts = {row: [k for (c, r), (k, _) in by_place.items() if r == row] for row in rows}
        wide_rows = [row for row in rows if len(counts[row]) * bw >= view['width'] * 0.4]
        if not wide_rows:
            out['error'] = 'no block row runs along the level'
            return out
        floor_row = max(wide_rows)
        path_row = max((r for r in rows if r < floor_row), default=None)
        floor_kind = max(set(counts[floor_row]), key=counts[floor_row].count)
        sample = {}                                    # one place of each block kind, to copy from
        for (c, r), (k, got) in sorted(by_place.items()):
            sample.setdefault(k, got)
        tally = {}
        for (c, r), (k, _) in by_place.items():
            tally[k] = tally.get(k, 0) + 1
        kinds = sorted(tally, key=lambda k: -tally[k])[:kinds_wanted]
        if floor_kind not in kinds:
            kinds.append(floor_kind)
        out['floor'] = {'row': floor_row, 'block': floor_kind, 'path_row': path_row}
        # the walk, and where the player is a third of the way along it
        # the stretch the player starts on: the section of the earliest capture (a room drawn later sits elsewhere on the map)
        ordered = sorted(plane.windows.items(), key=lambda item: session.meta[level['scene_ids'][item[0]]]['frame'])
        first_section = ordered[0][1].section
        windows = sorted((session.meta[level['scene_ids'][n]]['frame'], w.across) for n, w in ordered if w.section == first_section)
        start_x, end_x = windows[0][1], windows[-1][1]
        if end_x - start_x < 200:
            out['error'] = 'the walk did not get far enough along the level for the tests'
            return out
        aim = start_x + (end_x - start_x) // 3 + 160
        path_columns = sorted(c for (c, r) in by_place if r == path_row and start_x + 64 <= c * px <= end_x)
        floor_columns = sorted(c for (c, r) in by_place if r == floor_row and start_x + 64 <= c * px <= end_x)
        if not path_columns or not floor_columns:
            out['error'] = 'no blocks along the walk to test with'
            return out
        wall_column = min(path_columns, key=lambda c: abs(c * px - aim))
        # three floor blocks in a row: a one-block gap can be walked or jumped over, so it says nothing
        runs = [c for c in floor_columns if all((c + k * bw, floor_row) in by_place for k in range(3))]
        if not runs:
            out['error'] = 'no three floor blocks in a row along the walk'
            return out
        floor_start = min(runs, key=lambda c: abs(c * px - aim))
        meta = session.meta[level['scene_ids'][0]]
        run_dir = session.store / 'runs' / meta['run']
        inputs = array('H')
        inputs.frombytes((run_dir / 'inputs.bin').read_bytes())
        checkpoint = min(meta['checkpoints'])
        state = zlib.decompress((run_dir / f'{checkpoint}.st').read_bytes())
        end = min(len(inputs), windows[-1][0] + 120)
        job = session._cfg()
        watch = windows[0][0] - 30

        def reach(rom_path, rom_bytes):
            frames, _ = replay_screens(job, rom_path, rom_bytes, state, checkpoint, end, inputs, system, watch, 8)
            got = progress(frames, system)
            return max(got.values()) if got else None
        base = reach(rom, session.rom)
        out['walk'] = {'reach': base, 'wall_at': wall_column * px - start_x, 'floor_at': floor_start * px - start_x}
        if base is None:
            out['error'] = 'the replay could not be laid out as a level'
            return out

        def trial(targets, kind):
            kept, listed, tried = paint(session, level, targets, sample[kind], settle)
            if not kept:
                for change_id in kept:
                    session.remove(change_id)
                return None, listed, tried
            edited = temp / f'trial{suffix}'
            edited.write_bytes(session._rom_with([c for c in session.changes if c['id'] in kept]))
            got = reach(edited, edited.read_bytes())
            for change_id in kept:
                session.remove(change_id)
            return got, listed, tried

        stretch = [by_place[(floor_start + k * bw, floor_row)] for k in range(3)]
        # the control: the same stretch made of the level's commonest open block (what the player sees above the floor)
        above = [k for (c, r), (k, _) in by_place.items() if r < floor_row]
        sky = max(set(above), key=above.count) if above else None
        control, _, _ = trial(stretch, sky) if sky is not None and sky != floor_kind else (None, 0, 0)
        out['control'] = {'block': sky, 'reach': control, 'player_falls': None if control is None else control + 32 < base}
        floor_test_works = bool(out['control']['player_falls'])
        for kind in kinds:
            row = {'block': kind, 'uses': tally[kind], 'is_floor': kind == floor_kind}
            # wall: the three blocks of the path column above the floor (path row and the two above it)
            wall = [by_place[(wall_column, r)] for r in sorted((r for r in rows if r < floor_row), reverse=True)[:3]
                    if (wall_column, r) in by_place and by_place[(wall_column, r)][0] != kind]
            if wall:
                got, listed, tried = trial(wall, kind)
                row['wall'] = {'reach': got, 'in_list': listed, 'tried': tried,
                               'stops': None if got is None else got + 32 < base}
            # floor: three floor blocks ahead, made of this block
            if kind != floor_kind and not floor_test_works:
                row['floor'] = {'holds': None, 'note': 'the floor test cannot tell here: the player got across even a gap of open blocks'}
            elif kind != floor_kind:
                got, listed, tried = trial(stretch, kind)
                row['floor'] = {'reach': got, 'in_list': listed, 'tried': tried,
                                'holds': None if got is None else got + 32 >= base}
            else:
                row['floor'] = {'holds': True, 'note': 'the level floor itself'}
            stops = (row.get('wall') or {}).get('stops')
            holds = row['floor'].get('holds')
            row['role'] = ('solid' if stops and holds else 'platform' if holds and stops is False else
                           'open' if stops is False and holds is False else 'stops only' if stops and holds is False else 'not decided')
            out['blocks'].append(row)
        return out
    finally:
        session.close()
        shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('key')
    parser.add_argument('out', type=Path)
    parser.add_argument('--kinds', type=int, default=5)
    parser.add_argument('--steps', type=int, default=10)
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:
        result = measure(args.index, args.key, args.kinds, args.steps)
    except Exception as error:
        import traceback
        result = {'sha256': args.key, 'error': f'{type(error).__name__}: {error}'[:400], 'trace': traceback.format_exc()[-1500:]}
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
