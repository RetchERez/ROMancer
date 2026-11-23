"""Change bytes of the ROM, replay a recorded level walk from power-on on the original and the changed ROM, and list the
objects in the game's object slots in both (for games whose slot layout is known).

    python -B trace/level_rom_experiment.py <corpus index.json> <key> <out.json> --set OFFSET=VALUE [--set ...] --slots castlevania

Used to prove what a byte of a level's object data does before a level profile relies on it.
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

SLOTS = {
    # object slot layout: (first slot, last slot, type array, x array, y array, attribute array, camera low, camera high)
    'castlevania': dict(first=3, last=0x17, type=0x434, x=0x38C, y=0x354, attr=0x300, cam_lo=0x2E, cam_hi=0x2F),
}


def objects(frames, layout):
    """{(type, world x // 16): (first frame, slot, type, world x, y)} for objects in view in these replay frames."""
    seen = {}
    for frame in frames:
        snap = frame.graphics.scene.snapshot
        ram = next((snap.domains[n].data for n in ('wram', 'ram') if n in snap.domains and snap.domains[n].data is not None), None)
        if ram is None:
            continue
        cam = ram[layout['cam_lo']] | ram[layout['cam_hi']] << 8
        for slot in range(layout['first'], layout['last'] + 1):
            kind = ram[layout['type'] + slot]
            if kind and ram[layout['attr'] + slot] & 1:
                wx = cam + ram[layout['x'] + slot]
                seen.setdefault((kind, wx // 16), (frame.frame, slot, kind, wx, ram[layout['y'] + slot]))
    return seen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('key')
    parser.add_argument('out', type=Path)
    parser.add_argument('--set', action='append', default=[], help='ROM offset (no header) = value, both hex')
    parser.add_argument('--slots', required=True, choices=sorted(SLOTS))
    parser.add_argument('--steps', type=int, default=10)
    parser.add_argument('--crops', type=Path, help='save a picture of each new object type the first time it is on screen (original replay)')
    parser.add_argument('--watch', default='', help='RAM addresses (hex, comma separated) whose changes to list in the changed replay')
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'trace-win'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    from png_roundtrip import load_rom
    from level_blocks import record_level, START_PRESSES
    from level_collision import replay_screens
    from romancer.edit_session import EditSession
    from romancer import graphics_trace as gt
    sha, name, system, data, suffix = load_rom(args.index, args.key)
    temp = Path(tempfile.mkdtemp(prefix='romancer-experiment-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    out = {'name': name, 'changes': []}
    try:
        level = record_level(session, args.steps, 8, START_PRESSES.get(sha[:12], 0))
        skip = gt.rom_skip(data, system)
        changed = bytearray(data)
        for item in args.set:
            offset, value = (int(part, 16) for part in item.split('='))
            out['changes'].append({'offset': hex(offset), 'before': hex(changed[skip + offset]), 'after': hex(value)})
            changed[skip + offset] = value
        edited = temp / ('edited' + suffix)
        edited.write_bytes(bytes(changed))
        meta = session.meta[level['scene_ids'][0]]
        run_dir = session.store / 'runs' / meta['run']
        inputs = array('H')
        inputs.frombytes((run_dir / 'inputs.bin').read_bytes())
        checkpoint = min(meta['checkpoints'])
        state = zlib.decompress((run_dir / f'{checkpoint}.st').read_bytes())
        frames_all = sorted(session.meta[sid]['frame'] for sid in level['scene_ids'])
        end = min(len(inputs), frames_all[-1] + 120)
        job = session._cfg()
        watch = frames_all[0] - 30
        layout = SLOTS[args.slots]
        a, _ = replay_screens(job, rom, data, state, checkpoint, end, inputs, system, watch, 8)
        b, _ = replay_screens(job, edited, bytes(changed), state, checkpoint, end, inputs, system, watch, 8)
        before, after = objects(a, layout), objects(b, layout)
        fmt = lambda v: {'frame': v[0], 'slot': v[1], 'type': hex(v[2]), 'world_x': v[3], 'y': v[4]}
        out['original'] = [fmt(v) for v in sorted(before.values())]
        out['changed'] = [fmt(v) for v in sorted(after.values())]
        out['only_in_original'] = [fmt(before[k]) for k in sorted(set(before) - set(after))]
        out['only_in_changed'] = [fmt(after[k]) for k in sorted(set(after) - set(before))]
        if args.crops:
            from PIL import Image
            args.crops.mkdir(parents=True, exist_ok=True)
            done = set()
            for frame in (b if args.set else a):             # with a change, what the changed game shows
                g = frame.graphics
                snap = g.scene.snapshot
                ram = next((snap.domains[n].data for n in ('wram', 'ram') if n in snap.domains and snap.domains[n].data is not None), None)
                for slot in range(layout['first'], layout['last'] + 1):
                    kind = ram[layout['type'] + slot]
                    if not kind or kind in done or ram[layout['y'] + slot] >= 0xF0:
                        continue                    # an empty slot keeps y $F4
                    done.add(kind)
                    x, y = ram[layout['x'] + slot], ram[layout['y'] + slot]
                    pal = [tuple(c) for c in g.reps] + [(0, 0, 0)] * (256 - len(g.reps))
                    shot = Image.new('RGB', (g.width, g.height))
                    shot.putdata([pal[v] if v < len(pal) else (0, 0, 0) for line in g.screen for v in line])
                    box = (max(0, x - 32), max(0, y - 48), min(g.width, x + 32), min(g.height, y + 16))
                    shot.crop(box).resize(((box[2] - box[0]) * 3, (box[3] - box[1]) * 3), Image.NEAREST).save(
                        args.crops / f'type_{kind:02x}_slot{slot}_f{frame.frame}.png')
            out['crops'] = sorted(p.name for p in args.crops.glob('*.png'))
        watch = [int(x, 16) for x in args.watch.split(',') if x]
        if watch:
            def timeline(frames):
                rows, last = [], None
                for frame in frames:
                    snap = frame.graphics.scene.snapshot
                    ram = next((snap.domains[n].data for n in ('wram', 'ram') if n in snap.domains and snap.domains[n].data is not None), None)
                    now = tuple(ram[a] for a in watch)
                    if now != last:
                        rows.append({'frame': frame.frame, **{hex(a): v for a, v in zip(watch, now)}})
                        last = now
                return rows
            out['watch_original'] = timeline(a)
            out['watch_changed'] = timeline(b)
    finally:
        session.close()
        shutil.rmtree(temp, ignore_errors=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ('changes', 'only_in_original', 'only_in_changed', 'watch_changed') if k in out}, indent=1))


if __name__ == '__main__':
    main()
