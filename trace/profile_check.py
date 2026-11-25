"""Check a level profile the way the app uses it: record a level automatically, put the profile's objects on the map,
and run edits through the real session and its watcher, with a control on the unchanged game.

    python -B trace/profile_check.py <corpus index.json> <key> <out folder> [--presses N] [--steps N]
        [--edit 'PART|OBJECT|VALUES|remove'] ... [--length 'PART|SCREEN|DELTA'] ... [--add 'PART|KIND|X|Y|VALUES'] ...
        [--layout 'PART|[[COLUMN, ROW, BLOCK], ...]'] ...
        [--control]

--layout puts blocks into a packed layout (profile.packed_layout / profile.set_packed_layout) and checks it the way the
Level Editor does. --add puts a new object of KIND at the part's pixel X, Y (profile.addable / profile.add). PART and VALUES are JSON ({"stage": 1} and {"record": 84}); add |remove to remove the object. Writes to the out folder:
map.png (the map with every object's box, style colour and name), objects.json, results.json. --control also runs each
edit's watcher on the unchanged game: a good watcher says "bad" (or "warn") there.

Uses the same automatic recording as trace/level_blocks.py (walk right and jump, Start pressed N times first).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'trace'))
COLOURS = {'enemy': (255, 90, 90), 'item': (255, 209, 102), 'secret': (94, 230, 176), 'block': (199, 146, 255)}


def wait_change(session, change_id, limit=900):
    stored = session._find(change_id)
    start = time.time()
    while stored.get('object_check', {}).get('state') == 'working' and time.time() - start < limit:
        time.sleep(0.5)
    while session.change(change_id)['working'] and time.time() - start < limit:
        time.sleep(0.5)
    return stored.get('object_check')


def control(session, level, watcher):
    """The same watcher on the unchanged game (a change with no writes)."""
    fake = {'id': 'control', 'writes': []}
    session._watch_change(fake, level, watcher)
    return fake['object_check']


def draw_map(session, level, objects, path):
    from PIL import Image, ImageDraw
    png = session.export_level(level['id'], 0, False)['png']
    base = Image.open(io.BytesIO(png)).convert('RGB')
    z = 2
    img = base.resize((base.width * z, base.height * z), Image.NEAREST)
    d = ImageDraw.Draw(img)
    for o in objects:
        if o.get('picture'):
            pic = Image.open(io.BytesIO(base64.b64decode(o['picture']))).convert('RGBA')
            l, t, w, h = o['picture_box']
            pic = pic.resize((w * z, h * z), Image.NEAREST)
            img.paste(pic, (l * z, t * z), pic)
    for o in objects:
        x, y = o['map_x'] * z, o['map_y'] * z
        d.rectangle([x - 16, y - 32, x + 16, y], outline=COLOURS.get(o['style'], (255, 255, 255)), width=2)
        d.text((x - 16, y + 2), o['id'], fill=(255, 255, 255))
    img.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('key')
    parser.add_argument('out', type=Path)
    parser.add_argument('--presses', type=int, default=0)
    parser.add_argument('--steps', type=int, default=10)
    parser.add_argument('--intro', type=int, default=8)
    parser.add_argument('--edit', action='append', default=[])
    parser.add_argument('--length', action='append', default=[])
    parser.add_argument('--add', action='append', default=[])
    parser.add_argument('--layout', action='append', default=[])
    parser.add_argument('--control', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('ROMANCER_TRACE_CORES', str(ROOT.parent / 'release-v1.3.9' / 'work' / 'trace-pack-windows'))
    os.environ.setdefault('ROMANCER_TRACE_WORKERS', '2')
    from png_roundtrip import load_rom
    from level_blocks import record_level, START_PRESSES, ROUTES, INTROS
    from romancer.edit_session import EditSession
    sha, name, system, data, suffix = load_rom(args.index, args.key)
    args.out.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='romancer-profile-'))
    rom = temp / ('game' + suffix)
    rom.write_bytes(data)
    session = EditSession(temp / 'store', rom, system)
    out = {'name': name, 'sha256': sha}
    try:
        level = record_level(session, args.steps, INTROS.get(sha[:12], args.intro), args.presses or START_PRESSES.get(sha[:12], 0), ROUTES.get(sha[:12]))
        if level is None:
            out['error'] = session.level_job['message']
            print(json.dumps(out, indent=1))
            return
        view = session.objects = session.level_objects(level['id'])
        out['profile'] = view['profile']
        out['parts'] = view['parts']
        out['objects'] = [{k: o.get(k) for k in ('id', 'style', 'name', 'detail', 'part', 'x', 'y', 'map_x', 'map_y')} for o in view['objects']]
        out['captures'] = len(level['scene_ids'])
        draw_map(session, level, view['objects'], args.out / 'map.png')
        (args.out / 'objects.json').write_text(json.dumps(out['objects'], indent=1))
        from romancer import level_profiles
        profile = level_profiles.profile_for(session.rom)
        results = []
        for spec in args.edit:
            bits = spec.split('|')
            part, object_id, values = json.loads(bits[0]), bits[1], json.loads(bits[2]) if len(bits) > 2 and bits[2] else {}
            remove = len(bits) > 3 and bits[3] == 'remove'
            row = {'edit': spec}
            try:
                change = session.propose_level_edit(level['id'], part, object_id, values, remove)
                row['title'] = change['title']
                row['bytes'] = len(session._find(change['id'])['writes'])
                row['check'] = wait_change(session, change['id'])
                if args.control:
                    plan = profile.edit(part, object_id, values, remove)
                    row['control'] = control(session, level, profile.watcher(plan['watch']))
                session.remove(change['id']) if any(c['id'] == change['id'] for c in session.changes) else None
                session.preview = None
            except ValueError as error:
                row['error'] = str(error)
            results.append(row)
            print(json.dumps(row), flush=True)
        for spec in args.add:
            bits = spec.split('|')
            part, kind, x, y = json.loads(bits[0]), bits[1], int(bits[2]), int(bits[3])
            values = json.loads(bits[4]) if len(bits) > 4 and bits[4] else {}
            row = {'add': spec}
            try:
                change = session.propose_level_add(level['id'], part, kind, x, y, values)
                row['title'] = change['title']
                row['bytes'] = len(session._find(change['id'])['writes'])
                row['check'] = wait_change(session, change['id'])
                if args.control:
                    plan = profile.add(part, kind, x, y, values)
                    row['control'] = control(session, level, profile.watcher(plan['watch']))
                session.remove(change['id']) if any(c['id'] == change['id'] for c in session.changes) else None
                session.preview = None
            except ValueError as error:
                row['error'] = str(error)
            results.append(row)
            print(json.dumps(row), flush=True)
        for spec in args.layout:
            part_text, changes_text = spec.split('|', 1)
            part, changes = json.loads(part_text), [tuple(c) for c in json.loads(changes_text)]
            row = {'layout': spec}
            try:
                plan = profile.set_packed_layout(part, changes)
                change = session.propose_writes(level['scene_ids'][0], plan['writes'], plan['title'], kind='level-object')
                stored = session._find(change['id'])
                row['title'], row['bytes'] = plan['title'], len(plan['writes'])
                session._watch_change(stored, level, lambda: profile.watcher(plan['watch']))
                row['check'] = stored['object_check']
                if args.control:
                    row['control'] = control(session, level, profile.watcher(plan['watch']))
                session.remove(change['id']) if any(c['id'] == change['id'] for c in session.changes) else None
                session.preview = None
            except ValueError as error:
                row['error'] = str(error)
            results.append(row)
            print(json.dumps(row), flush=True)
        for spec in args.length:
            part, screen, delta = spec.split('|')
            row = {'length': spec}
            try:
                change = session.propose_level_length(level['id'], json.loads(part), int(screen), int(delta))
                row['title'] = change['title']
                row['check'] = wait_change(session, change['id'], 1800)
                session.preview = None
            except ValueError as error:
                row['error'] = str(error)
            results.append(row)
            print(json.dumps(row), flush=True)
        out['results'] = results
        (args.out / 'results.json').write_text(json.dumps(out, indent=1))
        print(json.dumps({k: out[k] for k in ('name', 'profile', 'parts', 'captures')}, indent=1))
        print(len(out['objects']), 'objects; map.png written')
    finally:
        session.close() if hasattr(session, 'close') else None


if __name__ == '__main__':
    main()
