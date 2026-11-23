"""Does a block painted on a level map change how the game PLAYS, not only how it looks?

    python -B trace/level_collision.py <corpus index.json> <sha256 or name prefix> <out.json> [--png folder]

Records a level the way trace/level_blocks.py does. Then:

1. Finds the camera in RAM: the recorded scenes hold the game's memory, and the level map knows how far along the level
   each capture was (its window). A byte (or byte pair) of RAM that moves with that position, by the same amount at every
   capture, is the camera. A side-scrolling camera follows the player, so it says how far the player got.
2. Paints a wall across the player's path: at a place the original walk passed, every block of one block column from the
   top of the map down to the floor gets the level's floor block, the block the player walks on.
3. Replays the identical inputs from the same savestate on the original ROM and on the ROM with the wall, and reads the
   camera every few frames.

The wall is SOLID when the original camera goes past it and the camera with the wall stops before it. It is only a
picture when both runs move the same. The result also counts how much of RAM came out different at the end.
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
import zlib
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'trace'))

SAMPLE = 4          # read the camera every this many frames
WALL_BLOCKS = 3     # blocks of wall above the floor: taller than a jump


def ram_of(snapshot) -> bytes | None:
    for name in ('wram', 'ram'):
        domain = snapshot.domains.get(name)
        if domain is not None and domain.data:
            return bytes(domain.data)
    return None


def _close_together(values, span, slack=3):
    """Whether these offsets (modulo span) all lie within `slack` of one another; returns their middle or None."""
    values = sorted(v % span for v in values)
    for start in values:                        # try each value as the low end of a window that may wrap round
        inside = [(v - start) % span for v in values]
        if max(inside) <= slack:
            return (start + max(inside) // 2) % span
    return None


def find_camera(samples):
    """[(ram, map x)] -> (lo index, hi index or None, offset) where ram[lo] + 256 * ram[hi] - map x is the same at every
    capture, give or take a few pixels (the memory and the screen of a capture can be a frame apart while the screen
    moves); lo alone (modulo 256) when no high byte fits. None when nothing moves with the map."""
    xs = [x for _, x in samples]
    if len(set(xs)) < 3:
        return None
    size = min(len(ram) for ram, _ in samples)
    paired, single = [], []
    for lo in range(size):
        low = _close_together([ram[lo] - x for ram, x in samples], 256)
        if low is None or len({ram[lo] for ram, _ in samples}) < 3:
            continue
        for hi in range(size):
            if hi != lo:
                whole = _close_together([ram[lo] + 256 * ram[hi] - x for ram, x in samples], 65536)
                if whole is not None:
                    paired.append((lo, hi, whole))
        single.append((lo, None, low))
    found = paired or single
    return found[0] if found else None


def camera_value(ram: bytes, camera) -> int:
    lo, hi, offset = camera
    if hi is None:
        return (ram[lo] - offset) % 256
    return (ram[lo] + 256 * ram[hi] - offset) % 65536


def replay_screens(job, rom_path, rom_bytes: bytes, state: bytes, start: int, end: int, inputs, system: str, watch_from: int,
                   every: int):
    """Replay the inputs and keep, every `every` frames from `watch_from`, the frame as level_map frames (screen +
    graphics), plus the RAM at the end."""
    from romancer import edit_session as es
    from romancer import provenance as pv
    from romancer import scene_graphics as sg
    from romancer import level_map as lm
    names = lambda frame: es._names(inputs[frame]) if frame < len(inputs) else ()
    fe = es._frontend(job, rom_path)
    frames, ram = [], None
    try:
        if int(fe.lib.retro_serialize_size()) <= 0:
            fe.run_frame([])
        fe.unserialize(state)
        session = es._Session(fe, checkpoint_every=10 ** 9)
        session.frame = start
        session.lib.romancer_trace_reset()
        session.lib.romancer_trace_enable(1)
        frame = start
        while frame < end:
            step = min(every if frame >= watch_from else max(1, watch_from - frame), end - frame)
            session.run(step, names)
            frame += step
            if frame < watch_from:
                continue
            picture = fe.last_frame
            scene = pv.scene_from_session(session, '')
            try:
                video = __import__('romancer.graphics_trace', fromlist=['x']).capture_video(session, system)
            except Exception:
                video = None
            graphics = sg.SceneGraphics(scene, system, rom_bytes, picture.rgb, picture.width, picture.height)
            if video:
                graphics.video = video
            graphics.layers()
            frames.append(lm.Frame(f'r{frame}', graphics, frame))
            ram = ram_of(scene.snapshot)
        return frames, ram
    finally:
        es._close(fe)


def progress(frames, system: str):
    """{frame: map x of the screen's left edge} from stitching these frames like a level map. The first frame is at 0."""
    from romancer import level_map as lm
    planes = lm.stitch(frames, system)
    if not planes:
        return {}
    plane = planes[0]
    out = {}
    for number, window in plane.windows.items():
        out[frames[number].frame] = window.across
    if not out:
        return {}
    first = out[min(out)]
    return {f: x - first for f, x in sorted(out.items())}


def unwrap(series, span):
    """Camera values that wrap round (one byte) made continuous."""
    out, last, base = [], None, 0
    for frame, value in series:
        if last is not None:
            delta = value - last
            if delta > span // 2:
                base -= span
            elif delta < -span // 2:
                base += span
        out.append((frame, value + base))
        last = value
    return out


def measure(index: Path, key: str, png) -> dict:
    from png_roundtrip import load_rom, settle
    from level_blocks import record_level, START_PRESSES
    from romancer.edit_session import EditSession
    from romancer import graphics_trace as gt
    from romancer import level_layout as ll
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system}
    temp = Path(tempfile.mkdtemp(prefix='romancer-collision-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    try:
        level = record_level(session, 6, 8, START_PRESSES.get(sha[:12], 0))
        if level is None:
            out['error'] = 'no level map: ' + session.level_job['message']
            return out
        view = session.level_view(level['id'], 0)
        px = view['cell']
        out['map'] = [view['width'], view['height']]
        plane = session._level_plane(level, 0)
        # 1. the camera
        samples, frames = [], []
        sections = [w.section for w in plane.windows.values()]
        main = max(set(sections), key=sections.count)          # another area sits elsewhere on the map: leave it out
        for number, window in sorted(plane.windows.items()):
            if window.section != main:
                continue
            scene_id = level['scene_ids'][number]
            ram = ram_of(session._scene(scene_id).snapshot)
            if ram is not None:
                samples.append((ram, window.across))
                frames.append((session.meta[scene_id]['frame'], window.across, scene_id))
        camera = find_camera(samples)
        if camera is not None:
            out['camera_in_ram'] = {'low_byte': camera[0], 'high_byte': camera[1], 'offset': camera[2]}
        frames.sort()
        # 2. the wall: blocks of the level grid, one column of them, filled with the floor block
        mapped = plane
        where = {(spot.frame, spot.layer, spot.x, spot.y): place for place, spot in mapped.cells.items()}
        skip = gt.rom_skip(session.rom, system)
        blocks = []           # (block kind, [map places row by row], top-left place)
        for frame_no in sorted({spot.frame for spot in mapped.cells.values()}):
            graphics = session._graphics(level['scene_ids'][frame_no])
            for number, layer_view in enumerate(graphics.layers()):
                layer = layer_view.layer
                grid = ll.find_grid(ll.cell_sources(layer, skip), layer.width, layer.height)
                if grid is None:
                    continue
                out.setdefault('grid', [grid.width, grid.height])
                for at, first in grid.first.items():
                    x, y = grid.left + at[0] * grid.width, grid.top + at[1] * grid.height
                    got = [where.get((frame_no, number, x + dx, y + dy)) for dy in range(grid.height) for dx in range(grid.width)]
                    if all(p is not None for p in got):
                        blocks.append((first, got, got[0]))
        if not blocks:
            out['error'] = 'the level is not built from blocks copied from the ROM'
            return out
        bw, bh = out['grid']
        by_place = {}
        for kind, got, corner in blocks:
            by_place.setdefault(corner, (kind, got))
        rows = sorted({corner[1] for corner in by_place})
        # the floor: the lowest block row that the level shows across most of the map; its commonest block
        counts = {row: [k for (c, r), (k, _) in by_place.items() if r == row] for row in rows}
        wide_rows = [row for row in rows if len(counts[row]) * bw >= view['width'] * 0.4]
        if not wide_rows:
            out['error'] = 'no block row runs along the level'
            return out
        floor_row = max(wide_rows)
        kinds = counts[floor_row]
        floor_kind = max(set(kinds), key=kinds.count)
        floor_places = next(got for (c, r), (k, got) in by_place.items() if r == floor_row and k == floor_kind)
        out['floor'] = {'row': floor_row, 'block': floor_kind}
        # where: ahead of where the player is at a capture a third of the way along, and behind where the walk ends
        start_x, end_x = frames[0][1], frames[-1][1]
        if end_x - start_x < 160:
            out['error'] = 'the walk did not get far enough along the level to put a wall in its way'
            return out
        wall_x = start_x + (end_x - start_x) // 3 + 160            # map pixel: a screen's half and more ahead of the camera
        # a column where the block row just above the floor (the player's path) is on the map and is not floor already
        path_row = max((r for r in rows if r < floor_row), default=None)
        columns = sorted({c for c, r in by_place if r == path_row and by_place[(c, r)][0] != floor_kind
                          and start_x + 64 <= c * px <= end_x + 64})
        if path_row is None or not columns:
            out['error'] = 'no block in the row above the floor can be painted along the walk'
            return out
        column = min(columns, key=lambda c: abs(c * px - wall_x))
        targets = []          # blocks of that column above the floor, lowest first: the player's path is just above it
        for row in sorted((r for r in rows if r < floor_row), reverse=True):
            target = by_place.get((column, row))
            if target is not None and target[0] != floor_kind:
                targets.append(target)
        if not targets:
            out['error'] = 'no blocks above the floor in that column to turn into a wall'
            return out
        out['wall'] = {'column': column, 'map_x': column * px, 'blocks': []}
        for kind, got in targets[:WALL_BLOCKS]:
            cells = [{'col': p[0], 'row': p[1], 'from': list(q)} for p, q in zip(got, floor_places)]
            change = session.propose_level(level['id'], 0, cells)
            done = settle(session, change)
            row = {'row': got[0][1], 'method': done.get('method'), 'verified': done['verified'], 'error': done['error'][:160]}
            out['wall']['blocks'].append(row)
            if done['error'] or not done['verified']:
                session.remove(done['id'])
                continue
            session.keep(done['id'])
        kept = [c for c in session.changes]
        if not kept:
            out['error'] = 'no block of the wall was confirmed by replay'
            return out
        out['wall']['kept'] = len(kept)
        out['wall']['in_the_level_list'] = sum(1 for b in out['wall']['blocks'] if b['method'] == 'layout' and b['verified'] and not b['error'])
        edited = temp / ('wall' + suffix)
        edited.write_bytes(session._rom_with(kept))
        out['wall']['bytes_changed'] = sum(1 for a, b in zip(session.rom, edited.read_bytes()) if a != b)
        if png:
            after = session.level_view(level['id'], 0)
            if after.get('after'):
                Path(png, f'{sha[:12]}-wall.png').write_bytes(session.image(after['after']))
        # 3. the same walk on both
        first_scene = frames[0][2]
        meta = session.meta[first_scene]
        run_dir = session.store / 'runs' / meta['run']
        inputs = array('H')
        inputs.frombytes((run_dir / 'inputs.bin').read_bytes())
        # from power-on: a game that loads the level into RAM when it starts would not see a ROM change made after that
        checkpoint = min(meta['checkpoints'])
        state = zlib.decompress((run_dir / f'{checkpoint}.st').read_bytes())
        end = min(len(inputs), frames[-1][0] + 120)
        job = session._cfg()
        watch = frames[0][0] - 30
        every = 8
        plain_frames, ram_a = replay_screens(job, rom, session.rom, state, checkpoint, end, inputs, system, watch, every)
        wall_frames, ram_b = replay_screens(job, edited, edited.read_bytes(), state, checkpoint, end, inputs, system, watch, every)
        plain, walled = progress(plain_frames, system), progress(wall_frames, system)
        if not plain or not walled:
            out['error'] = 'the replays could not be laid out as a level'
            return out
        reach_plain, reach_wall = max(plain.values()), max(walled.values())
        # where the wall is, on the replay's own scale: the recording's first capture is at map x frames[0][1]
        wall_on_replay = column * px - frames[0][1]
        out['replay'] = {'from_frame': checkpoint, 'to_frame': end, 'every': every,
                         'reach_original': reach_plain, 'reach_with_wall': reach_wall, 'wall_at': wall_on_replay,
                         'ram_bytes_different_at_end': sum(1 for a, b in zip(ram_a or b'', ram_b or b'') if a != b)}
        passed = reach_plain + 64 > wall_on_replay
        stopped = reach_wall + 32 < reach_plain
        out['solid'] = bool(passed and stopped)
        out['verdict'] = ('the wall stopped the player: the screen got %d pixels along with the wall and %d without it (wall at %d)'
                          % (reach_wall, reach_plain, wall_on_replay)) if out['solid'] else (
                          'the player went on as before: %d pixels along with the wall, %d without it (wall at %d)'
                          % (reach_wall, reach_plain, wall_on_replay)) if passed else (
                          'not decided: the original walk did not get past the wall (%d pixels along, wall at %d)' % (reach_plain, wall_on_replay))
        return out
    finally:
        session.close()
        shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('key')
    parser.add_argument('out', type=Path)
    parser.add_argument('--png', type=Path)
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:
        result = measure(args.index, args.key, args.png)
    except Exception as error:
        import traceback
        result = {'sha256': args.key, 'error': f'{type(error).__name__}: {error}'[:400], 'trace': traceback.format_exc()[-1500:]}
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
