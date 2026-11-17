"""Trace every ROM in the corpus and measure graphics editing coverage.

    python -B trace/graphics_sweep.py INDEX.json OUTDIR --system gb --system gbc --core PATH [--jobs N] [--frames F]

For each ROM: boot with the exploring input script, take a scene, and record

* tiles by status (ROM bytes / code values / derived / unknown), for every
  tile slot, for tiles that hold a picture, and for tiles on screen;
* background map cells by status;
* one causal tile edit: a tile on screen is redrawn, the ROM writes are
  planned (plan_tile_edit) and the scene is replayed with the edited ROM;
  the edit counts only when video memory then holds the planned bytes;
* one causal map-cell edit, the same way;
* for a tile that cannot be written in place (computed or packed): which
  codec, if any, reproduces it, and whether the re-encode / relocate /
  overlay path replays as planned;
* whether the codec-independent overlay fallback works for this game.

Results are one JSON per ROM, so the sweep can be resumed.
"""
import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))

STEP = 900


def explore(frame):
    """Deterministic play: get through menus, then walk, jump and attack (same as coverage_sweep)."""
    if frame < 240:
        return []
    phase = frame % 600
    if frame < 1800 or phase < 30:
        return ['start'] if frame % 90 < 4 and (frame // 90) % 3 == 0 else ['a'] if frame % 45 < 4 else []
    direction = ('right', 'down', 'left', 'up')[(frame // 600) % 4]
    held = [direction] if phase < 480 else []
    if frame % 40 < 6:
        held.append('a')
    if frame % 70 < 4:
        held.append('b')
    return held


class BootOnly:
    """Frontend for an engine build without savestates: the only checkpoint is power-on.

    serialize() returns an empty state and unserialize() of it does nothing,
    so a replay "from the checkpoint" is a fresh boot. The session must then
    keep no later checkpoints (trace() sees to that).
    """

    def __init__(self, fe):
        self.__dict__['_fe'] = fe

    def __getattr__(self, name):
        return getattr(self._fe, name)

    def __setattr__(self, name, value):
        setattr(self._fe, name, value)

    def serialize(self):
        return b''

    def unserialize(self, state):
        if state:
            raise ValueError('this engine build cannot load savestates')


def opener(core, suffix, work):
    """make_frontend(rom bytes) for provenance.verify_edit and graphics_trace.verify_plan."""
    import trace_probe as tp
    work = Path(work)
    count = [0]

    def fe_for(data):
        count[0] += 1
        p = work / f'g{count[0]}{suffix}'
        p.write_bytes(data)
        fe = tp.LibretroFrontend(core, save_dir=work / 'rt')
        fe.load_game(p)
        if not fe.lib.retro_serialize_size():
            fe_for.savestates = False
            return BootOnly(fe)
        return fe
    fe_for.savestates = True
    return fe_for


def trace(core, rom, suffix, system, frames, work, step=STEP, buttons=explore):
    """Run the tracing engine and return (scenes, make_frontend)."""
    from romancer import provenance as pv, graphics_trace as gt
    fe_for = opener(core, suffix, work)
    fe = fe_for(rom)
    s = pv.TraceSession(fe, checkpoint_every=300 if fe_for.savestates else 10 ** 9)
    s.start()
    scenes = []
    for _ in range(max(1, frames // step)):
        s.run(step, buttons)
        scenes.append(gt.scene_from_session(s, system))
    s.fe.close()
    return scenes, fe_for


def soak(fe_for, rom, plan, scene, buttons=explore, slack=12):
    """Run the edited ROM from power-on and look for the scene, changed only as planned.

    An added routine costs a little time each frame, so a game may reach the
    same moment a frame or two later. The edited run therefore passes when,
    at some frame within `slack` of the scene's, video memory equals the
    scene's except for the planned bytes holding their planned values.
    """
    import ctypes
    from romancer import provenance as pv
    edited = plan.apply(rom)
    start, state = scene.checkpoints[0]
    fe = fe_for(edited)
    best = None
    try:
        fe.unserialize(state)
        s = pv.TraceSession(fe, checkpoint_every=10 ** 9)
        s.frame = start
        s.start()
        names = [n for n in plan.expect if n in scene.snapshot.domains]
        want = {}
        for n in names:
            w = bytearray(scene.snapshot.domains[n].data)
            for i, v in plan.expect[n].items():
                w[int(i)] = v
            want[n] = bytes(w)
        s.run(max(0, scene.frame - start - 2), buttons)
        for extra in range(slack):
            got = {}
            for i in range(s.lib.romancer_trace_domain_count()):
                d = s.lib.romancer_trace_domain(i).contents
                if d.name.decode() in want:
                    got[d.name.decode()] = ctypes.string_at(d.data, d.size)
            diff = sum(sum(a != b for a, b in zip(got[n], want[n])) for n in want)
            if best is None or diff < best[1]:
                best = (s.frame, diff)
            if diff == 0:
                break
            s.run(1, buttons)
    finally:
        fe.close()
    return {'frames': scene.frame, 'clean': bool(best and best[1] == 0), 'at_frame': best[0] if best else None,
            'closest_diff': best[1] if best else None}


def redraw(tile):
    """A visibly different picture for a tile: every color index mirrored."""
    top = max(1, (1 << {'gb-2bpp': 2, 'nes-2bpp': 2, 'snes-2bpp': 2}.get(tile.format, 4)) - 1)
    return [top - p for p in tile.pixels]


def measure(rom, system, scenes, fe_for, result, buttons=explore):
    from romancer import graphics_trace as gt
    scene = scenes[-1]

    # Replays start at the last two checkpoints and, failing those, at power-on; that bounds the cost
    # of an edit that turns out not to reach the scene.
    from romancer import provenance as pv
    before = [c for c in scene.checkpoints if c[0] < scene.frame] or scene.checkpoints[:1]
    quick = pv.Scene(scene.id, scene.frame, scene.screen_sha256,
                     sorted({c[0]: c for c in scene.checkpoints[:1] + before[-2:]}.values()), scene.snapshot)
    quick.video = getattr(scene, 'video', None)

    def verify(plan, expect=None):
        return gt.verify_plan(fe_for, rom, plan, quick, expect=expect, buttons_for=buttons)

    all_tiles = gt.tiles(scene, system, rom)
    used = gt.used_tile_addresses(scene, system)
    live = [t for t in all_tiles if not t.blank]
    shown = [t for t in live if t.addresses[0] in used]

    def count(ts):
        out = {k: 0 for k in ('rom', 'code', 'derived', 'unknown')}
        for t in ts:
            out[t.status] += 1
        return out
    result['video'] = getattr(scene, 'video', None)
    result['tiles'] = {'all': count(all_tiles), 'with_picture': count(live), 'on_screen': count(shown),
                       'rom_plain': sum(t.layout == 'plain' for t in live), 'rom_scattered': sum(t.layout == 'scattered' for t in live)}
    lay = gt.layers(scene, system)
    uses = {}
    for layer in lay:
        for c in layer.cells:
            uses[c.tile_address] = uses.get(c.tile_address, 0) + 1
    shown.sort(key=lambda t: -uses.get(t.addresses[0], 0))  # most used on screen first
    result['layers'] = [{'name': l.name, 'size': [l.width, l.height], 'layout_source': l.layout_source,
                         'cells': l.status_counts()} for l in lay]

    def brief(r):
        return {'verified': r['verified'], 'as_planned': r.get('as_planned'), 'by': r.get('by'),
                'repeatable': r.get('replay_is_repeatable'),
                'missed': {k: len(v) for k, v in r.get('missed', {}).items()}, 'unplanned': r.get('unplanned', {}),
                'changed': {k: len(v) for k, v in r.get('changed', {}).items()}}

    # ---- one direct tile edit, replayed -----------------------------------
    pool = shown or live
    direct = {'candidates': sum(t.editable for t in pool)}
    packed_fail = None
    for tile in [t for t in pool if t.editable][:4]:
        new = redraw(tile)
        try:
            writes = gt.plan_tile_edit(tile, new, rom)
        except ValueError as e:
            direct.setdefault('refused', []).append(str(e)[:80])
            packed_fail = packed_fail or tile
            continue
        r = verify(gt.with_checksums(rom, writes, system), gt.expect_for(tile, gt.encode_tile(new, tile.format)))
        direct.update(tile=tile.index, address=tile.addresses[0], layout=tile.layout, writes=len(writes), **brief(r))
        if r.get('as_planned') or (tile.domain == 'chr_rom' and r['verified']):
            break
    result['tile_edit'] = direct

    # ---- "change only this one": private copy of a plainly stored tile ------
    private = {}
    if direct.get('as_planned') and direct.get('layout') == 'plain' and fe_for.savestates and gt.CPU[system] in ('sm83', '6502'):
        tile = next(t for t in pool if t.index == direct['tile'] and t.addresses[0] == direct['address'])
        new = gt.encode_tile(redraw(tile), tile.format)
        try:
            plan = gt.plan_private_copy(tile, new, rom, scene, verify=verify, max_candidates=8)
            private.update(pointer=plan.details['pointer']['encoding'], block=plan.details['new_size'], **brief(plan.verified))
        except ValueError as e:
            private['error'] = str(e)[:120]
    result['private_copy'] = private

    # ---- one map cell edit, replayed --------------------------------------
    cell_result = {}
    for layer in lay[:1]:
        cands = [c for c in layer.cells if c.editable and c.sources[0] and not c.sources[0]['weak']]
        cell_result['candidates'] = len(cands)
        for c in cands[len(cands) // 2:len(cands) // 2 + 3]:
            if system in ('gb', 'gbc', 'nes'):
                number = (c.stored[0] + 1) & 0xFF
            else:
                number = (c.tile + 1) & 0xFF
            try:
                writes = gt.plan_tilemap_edit(c, rom, tile=number)
            except ValueError as e:
                cell_result['refused'] = str(e)[:80]
                continue
            new = bytearray(c.stored)
            for o, _, n in writes:
                for k, src in enumerate(c.sources):
                    if src and src['offset'] + gt.rom_skip(rom, system) == o:
                        new[k] = n
            r = verify(gt.with_checksums(rom, writes, system), gt.expect_for(c, bytes(new)))
            cell_result.update(cell=[c.x, c.y], writes=len(writes), **brief(r))
            if r.get('as_planned'):
                break
    result['map_edit'] = cell_result

    # ---- tiles that cannot be written in place ----------------------------
    hard = [t for t in shown if t.status == 'derived'] or [t for t in live if t.status == 'derived']
    target = hard[0] if hard else packed_fail
    derived = {'tiles_on_screen': sum(t.status == 'derived' for t in shown)}
    if target is not None and target.domain != 'chr_rom':
        block = gt.find_compressed_block(scene, rom, system, target.domain, target.addresses[0], len(target.addresses))
        derived['tile'] = target.index
        derived['codec'] = block.codec if block else None
        if block:
            derived['block'] = block.to_dict()
        try:
            plan = gt.plan_derived_tile_edit(target, redraw(target), rom, scene, verify=verify,
                                             max_candidates=24 if gt.CPU[system] in ('sm83', '6502') else 6)
            derived.update(path=plan.kind, **brief(plan.verified))
        except ValueError as e:
            derived['error'] = str(e)[:300]
    result['derived_edit'] = derived

    # ---- the overlay fallback on its own -----------------------------------
    overlay = {}
    if gt.CPU[system] in ('sm83', '65816', '68000'):
        tile = next((t for t in shown if t.domain == 'vram'), None) or next((t for t in live if t.domain == 'vram'), None)
        if tile is not None:
            try:
                plan = gt.plan_overlay_patch([(tile, redraw(tile))], rom, system, scene=scene)
                overlay.update(tile=tile.index, routine=plan.details['routine_size'],
                               placement=plan.details['placement'], **brief(verify(plan)))
                overlay['soak'] = soak(fe_for, rom, plan, scene, buttons)
                if gt.CPU[system] == '68000' and not overlay.get('as_planned'):
                    plan2 = gt.plan_overlay_patch([(tile, redraw(tile))], rom, system, scene=scene, guard=False)
                    overlay['unguarded'] = {**brief(verify(plan2)), 'soak': soak(fe_for, rom, plan2, scene, buttons)}
                if gt.CPU[system] == '65816' and not (overlay.get('as_planned') and overlay['soak']['clean']):
                    plan2 = gt.plan_overlay_patch([(tile, redraw(tile))], rom, system, scene=scene, after_handler=True)
                    overlay['after_handler'] = {**brief(verify(plan2)), 'soak': soak(fe_for, rom, plan2, scene, buttons)}
            except ValueError as e:
                overlay['error'] = str(e)[:120]
    else:
        overlay['status'] = gt.OVERLAY_STATUS[gt.CPU[system]]
    result['overlay'] = overlay


def one(sha, entry, core, system, frames, outdir):
    import trace_probe as tp
    out = Path(outdir) / f'{sha}.json'
    if out.exists():
        return sha, 'cached'
    t0 = time.perf_counter()
    result = {'sha256': sha, 'system': system, 'member': entry['member'], 'core': Path(core).name, 'frames': frames}
    try:
        rom, suf = tp.read_rom(entry['zip'] + '!' + entry['member'])
        work = Path(tempfile.mkdtemp(prefix='gfx'))
        scenes, fe_for = trace(core, rom, suf, system, frames, work)
        result['distinct_screens'] = len({sc.screen_sha256 for sc in scenes})
        result['savestates'] = fe_for.savestates
        measure(rom, system, scenes, fe_for, result)
        result['ok'] = True
    except Exception as e:  # recorded, never hidden
        result['ok'] = False
        result['error'] = f'{type(e).__name__}: {e}'
        result['trace'] = traceback.format_exc()[-1500:]
    result['seconds'] = round(time.perf_counter() - t0, 1)
    out.write_text(json.dumps(result, indent=1))
    try:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    except Exception:
        pass
    return sha, 'ok' if result['ok'] else 'error'


def report(outdir):
    """Totals over every result in OUTDIR, by system."""
    rows = [json.loads(p.read_text()) for p in Path(outdir).glob('*.json')]
    out = {}
    for system in sorted({r['system'] for r in rows}):
        rs = [r for r in rows if r['system'] == system]
        ok = [r for r in rs if r.get('ok')]
        s = {'roms': len(rs), 'traced': len(ok), 'errors': len(rs) - len(ok)}
        for key in ('with_picture', 'on_screen'):
            tot = {k: sum(r['tiles'][key][k] for r in ok) for k in ('rom', 'code', 'derived', 'unknown')}
            s[f'tiles_{key}'] = tot
        s['tile_edit_as_planned'] = sum(bool(r['tile_edit'].get('as_planned') or (r['tile_edit'].get('by') == 'screen' and r['tile_edit'].get('verified'))) for r in ok)
        s['tile_edit_reaches_scene'] = sum(bool(r['tile_edit'].get('verified')) for r in ok)
        s['tile_edit_no_candidate'] = sum(not r['tile_edit'].get('candidates') for r in ok)
        s['map_edit_as_planned'] = sum(bool(r['map_edit'].get('as_planned')) for r in ok)
        s['map_edit_no_candidate'] = sum(not r['map_edit'].get('candidates') for r in ok)
        hard = [r for r in ok if 'tile' in r['derived_edit']]
        s['hard_tile_roms'] = len(hard)
        codecs = {}
        for r in hard:
            c = r['derived_edit'].get('codec') or 'none'
            codecs[c] = codecs.get(c, 0) + 1
        s['hard_tile_codec'] = codecs
        paths = {}
        for r in hard:
            p = r['derived_edit'].get('path') if r['derived_edit'].get('as_planned') else 'unconfirmed'
            paths[p] = paths.get(p, 0) + 1
        s['hard_tile_confirmed_path'] = paths
        tried = [r for r in ok if r.get('private_copy')]
        s['private_copy_tried'] = len(tried)
        s['private_copy_as_planned'] = sum(bool(r['private_copy'].get('as_planned')) for r in tried)
        shown = sum(sum(r['tiles']['on_screen'].values()) for r in ok)
        direct = sum(r['tiles']['on_screen']['rom'] + r['tiles']['on_screen']['code'] for r in ok)
        derived_ok = sum(r['tiles']['on_screen']['derived'] for r in ok
                         if r['derived_edit'].get('as_planned') or r['overlay'].get('as_planned')
                         or r['overlay'].get('after_handler', {}).get('as_planned')
                         or r['overlay'].get('unguarded', {}).get('as_planned'))
        s['on_screen_tiles'] = shown
        s['on_screen_tiles_traced_to_rom_or_code'] = direct
        s['on_screen_derived_tiles_in_roms_with_a_confirmed_derived_path'] = derived_ok
        s['overlay_as_planned'] = sum(bool(r['overlay'].get('as_planned')) for r in ok)
        def clean(o):
            return bool(o.get('as_planned') and o.get('soak', {}).get('clean'))
        s['overlay_clean_from_boot'] = sum(clean(r['overlay']) for r in ok)
        s['overlay_clean_from_boot_either_timing'] = sum(clean(r['overlay']) or clean(r['overlay'].get('after_handler', {})) for r in ok)
        s['overlay_unguarded_as_planned'] = sum(bool(r['overlay'].get('unguarded', {}).get('as_planned')) for r in ok)
        s['overlay_unguarded_clean_from_boot'] = sum(clean(r['overlay'].get('unguarded', {})) for r in ok)
        place = {}
        for r in ok:
            if r['overlay'].get('as_planned'):
                place[r['overlay'].get('placement')] = place.get(r['overlay'].get('placement'), 0) + 1
        s['overlay_placement'] = place
        s['overlay_refused'] = sum('error' in r['overlay'] for r in ok)
        s['any_tile_path_confirmed'] = sum(bool(r['tile_edit'].get('as_planned') or (r['tile_edit'].get('by') == 'screen' and r['tile_edit'].get('verified'))
                                                or r['derived_edit'].get('as_planned') or r['overlay'].get('as_planned')) for r in ok)
        out[system] = s
    return out


def _run_one(args):
    """Run one ROM in its own process, so an engine crash or hang costs only that ROM."""
    import subprocess
    sha, a = args
    out = Path(a.outdir) / f'{sha}.json'
    if out.exists():
        return sha, 'cached'
    cmd = [sys.executable, '-B', str(Path(__file__).resolve()), a.index, a.outdir, '--core', a.core,
           '--frames', str(a.frames), '--one', sha]
    try:
        code = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=a.timeout).returncode
        problem = None if out.exists() else f'the engine process ended with code {code} and left no result'
    except subprocess.TimeoutExpired:
        problem = f'no result after {a.timeout} seconds'
    if problem and not out.exists():
        entry = json.loads(Path(a.index).read_text())[sha]
        out.write_text(json.dumps({'sha256': sha, 'system': entry['system_id'], 'member': entry['member'],
                                   'core': Path(a.core).name, 'frames': a.frames, 'ok': False, 'error': problem,
                                   'seconds': a.timeout if 'seconds' in problem else 0}, indent=1))
    return sha, 'error' if problem else json.loads(out.read_text()).get('ok') and 'ok' or 'error'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('index'); ap.add_argument('outdir')
    ap.add_argument('--system', action='append')
    ap.add_argument('--core')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--frames', type=int, default=1800)
    ap.add_argument('--timeout', type=int, default=900, help='seconds allowed per ROM')
    ap.add_argument('--only', help='comma-separated sha256 prefixes')
    ap.add_argument('--one', help='run this one sha256 in this process (used by the sweep itself)')
    ap.add_argument('--report', action='store_true', help='print totals for OUTDIR and exit')
    a = ap.parse_args()
    if a.report:
        print(json.dumps(report(a.outdir), indent=1))
        return
    index = json.loads(Path(a.index).read_text())
    if a.one:
        entry = index[a.one]
        one(a.one, entry, a.core, entry['system_id'], a.frames, a.outdir)
        return
    if not a.system or not a.core:
        ap.error('--system and --core are required')
    Path(a.outdir).mkdir(parents=True, exist_ok=True)
    todo = [(sha, e) for sha, e in index.items() if e['system_id'] in a.system]
    if a.only:
        todo = [(s, e) for s, e in todo if any(s.startswith(p) for p in a.only.split(','))]
    from concurrent.futures import ThreadPoolExecutor
    done = 0
    with ThreadPoolExecutor(a.jobs) as pool:
        for sha, state in pool.map(_run_one, [(sha, a) for sha, _ in todo]):
            done += 1
            print(f'{done}/{len(todo)} {sha[:12]} {state}', flush=True)


if __name__ == '__main__':
    main()
