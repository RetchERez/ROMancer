"""Find the ROM data a level reads because of WHERE the player is (objects, items, level data), not WHEN (music, timers).

    python -B trace/level_objects.py <corpus index.json> <sha256 or name prefix> <out.json>

Records a level, puts a wall in the player's path that is known to stop the player (trace/level_collision.py does the
same), and replays the same inputs from power-on on the original ROM and on the ROM with the wall. Every few frames it
reads which ROM byte each RAM byte came from (the tracing engine tags every byte with its source).

A RAM byte whose ROM source keeps moving in both replays is driven by time (music keeps playing when the player is
stopped). One whose source moves in the original but stops moving soon after the player is stopped is driven by the
player's position: the game reads the next part of the level, or the next object, as the screen scrolls. Those are
grouped by the ROM area they read from; the area the level's block list lives in is marked, and the others are the
candidates for the object and item lists.
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


def tagged_ram(snapshot):
    """{ram address: rom offset} for RAM bytes copied or worked out from the ROM."""
    from romancer import provenance as pv
    for name in ('wram', 'ram'):
        domain = snapshot.domains.get(name)
        if domain is not None and domain.data is not None and domain.tags is not None:
            out = {}
            for at in range(len(domain.data)):
                tag = domain.tags[at]
                if pv.tag_kind(tag) in (pv.RT_ROM, pv.RT_DERIVED):
                    out[at] = pv.tag_offset(tag)
            return out
    return {}


def sources_over_time(frames):
    """[(frame, {ram: rom})] from replay frames (level_map Frames whose graphics hold the scene)."""
    out = []
    for frame in frames:
        scene = getattr(frame.graphics, 'scene', None)
        if scene is not None:
            out.append((frame.frame, tagged_ram(scene.snapshot)))
    return out


def movers(series, after=None):
    """{ram: number of times its ROM source changed} (only counting from frame `after` when given)."""
    count, last = {}, {}
    for frame, tags in series:
        for at, off in tags.items():
            if at in last and last[at] != off and (after is None or frame >= after):
                count[at] = count.get(at, 0) + 1
            last[at] = off
    return count


def measure(index: Path, key: str, out_path: Path) -> dict:
    from png_roundtrip import load_rom, settle
    from level_blocks import record_level, START_PRESSES
    from level_collision import replay_screens, progress
    from level_block_roles import blocks_of, paint
    from romancer.edit_session import EditSession
    from romancer import level_layout as ll
    sha, name, system, data, suffix = load_rom(index, key)
    out = {'sha256': sha, 'name': name, 'system': system}
    temp = Path(tempfile.mkdtemp(prefix='romancer-objects-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    try:
        level = record_level(session, 10, 8, START_PRESSES.get(sha[:12], 0))
        if level is None:
            out['error'] = 'no level map'
            return out
        view = session.level_view(level['id'], 0)
        px = view['cell']
        by_place, grid, plane = blocks_of(session, level, system)
        bw, bh = grid
        rows = sorted({r for _, r in by_place})
        counts = {row: [k for (c, r), (k, _) in by_place.items() if r == row] for row in rows}
        floor_row = max(row for row in rows if len(counts[row]) * bw >= view['width'] * 0.4)
        floor_kind = max(set(counts[floor_row]), key=counts[floor_row].count)
        floor_places = next(got for (c, r), (k, got) in by_place.items() if r == floor_row and k == floor_kind)
        # the stretch the player starts on: the section of the earliest capture (a room drawn later sits elsewhere on the map)
        ordered = sorted(plane.windows.items(), key=lambda item: session.meta[level['scene_ids'][item[0]]]['frame'])
        first_section = ordered[0][1].section
        windows = sorted((session.meta[level['scene_ids'][n]]['frame'], w.across) for n, w in ordered if w.section == first_section)
        start_x, end_x = windows[0][1], windows[-1][1]
        path_row = max(r for r in rows if r < floor_row)
        aim = start_x + (end_x - start_x) // 3 + 160
        column = min((c for (c, r) in by_place if r == path_row and start_x + 64 <= c * px <= end_x), key=lambda c: abs(c * px - aim))
        wall = [by_place[(column, r)] for r in sorted((r for r in rows if r < floor_row), reverse=True)[:3]
                if (column, r) in by_place and by_place[(column, r)][0] != floor_kind]
        kept, listed, tried = paint(session, level, wall, floor_places, settle)
        out['wall'] = {'map_x': column * px, 'kept': len(kept), 'in_list': listed}
        if not kept:
            out['error'] = 'the wall could not be placed'
            return out
        edited = temp / ('wall' + suffix)
        edited.write_bytes(session._rom_with(list(session.changes)))
        meta = session.meta[level['scene_ids'][0]]
        run_dir = session.store / 'runs' / meta['run']
        inputs = array('H')
        inputs.frombytes((run_dir / 'inputs.bin').read_bytes())
        checkpoint = min(meta['checkpoints'])
        state = zlib.decompress((run_dir / f'{checkpoint}.st').read_bytes())
        end = min(len(inputs), windows[-1][0] + 120)
        job = session._cfg()
        watch = windows[0][0] - 30
        plain_frames, _ = replay_screens(job, rom, session.rom, state, checkpoint, end, inputs, system, watch, 8)
        wall_frames, _ = replay_screens(job, edited, edited.read_bytes(), state, checkpoint, end, inputs, system, watch, 8)
        plain_pos, wall_pos = progress(plain_frames, system), progress(wall_frames, system)
        if not plain_pos or not wall_pos:
            out['error'] = 'the replays could not be laid out'
            return out
        reach_plain, reach_wall = max(plain_pos.values()), max(wall_pos.values())
        out['reach'] = {'original': reach_plain, 'with_wall': reach_wall}
        if reach_wall + 32 >= reach_plain:
            out['error'] = 'the wall did not stop the player, so position and time cannot be told apart this way'
            return out
        # when was the player stopped? the first sample at which the walled replay is within 8 pixels of where it ends up
        stuck = min(f for f, x in wall_pos.items() if x >= reach_wall - 8)
        plain = sources_over_time(plain_frames)
        walled = sources_over_time(wall_frames)
        moved_plain = movers(plain, after=stuck + 60)
        moved_wall = movers(walled, after=stuck + 60)
        position = {at: n for at, n in moved_plain.items() if n >= 2 and moved_wall.get(at, 0) == 0}
        timed = {at: n for at, n in moved_plain.items() if n >= 2 and moved_wall.get(at, 0) >= 2}
        # where the level's own block list is, to tell level data from objects
        listed_area = None
        for change in session.changes:
            for offset, _, _ in change['writes']:
                listed_area = offset if listed_area is None else min(listed_area, offset)
        last = {at: off for at, off in plain[-1][1].items()}
        areas = {}
        for at in position:
            offs = sorted({tags[at] for _, tags in plain if at in tags})
            area = offs[0] // 0x100
            areas.setdefault(area, {'ram': [], 'rom_first': offs[0], 'rom_last': offs[-1]})
            areas[area]['ram'].append(at)
            areas[area]['rom_first'] = min(areas[area]['rom_first'], offs[0])
            areas[area]['rom_last'] = max(areas[area]['rom_last'], offs[-1])
        out['stopped_at_frame'] = stuck
        out['time_driven_ram'] = len(timed)
        out['position_driven'] = [{'rom_from': hex(a['rom_first']), 'rom_to': hex(a['rom_last']), 'ram': [hex(x) for x in sorted(a['ram'])][:24],
                                   'near_the_block_list': listed_area is not None and abs(a['rom_first'] - listed_area) < 0x400}
                                  for area, a in sorted(areas.items(), key=lambda item: -len(item[1]['ram']))]
        out['block_list_write_at'] = hex(listed_area) if listed_area is not None else None
        # for working out the objects offline: every sample of the normal replay (RAM, sprite table, ROM sources), and
        # where the screen was at that moment
        samples = []
        for frame in plain_frames:
            snap = frame.graphics.scene.snapshot
            ram = next((snap.domains[n].data for n in ('wram', 'ram') if n in snap.domains and snap.domains[n].data is not None), None)
            oam = snap.domains.get('oam')
            samples.append({'frame': frame.frame, 'x': plain_pos.get(frame.frame), 'ram': bytes(ram).hex() if ram is not None else '',
                            'oam': bytes(oam.data).hex() if oam is not None and oam.data is not None else '',
                            'from_rom': {str(at): off for at, off in tagged_ram(snap).items()}})
        Path(str(out_path) + '.samples.json').write_text(json.dumps(samples))
        return out
    finally:
        session.close()
        shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('key')
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    try:
        result = measure(args.index, args.key, args.out)
    except Exception as error:
        import traceback
        result = {'sha256': args.key, 'error': f'{type(error).__name__}: {error}'[:400], 'trace': traceback.format_exc()[-1500:]}
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
