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
SETTLE = 45          # frames before a scene at which video memory is sampled once more
SWEEP_VERSION = 4
VIDEO_DOMAINS = ('vram', 'chr', 'vram4')


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


def opener(core, suffix, work, options=None):
    """make_frontend(rom bytes) for provenance.verify_edit and graphics_trace.verify_plan."""
    import trace_probe as tp
    work = Path(work)
    count = [0]

    def fe_for(data):
        count[0] += 1
        p = work / f'g{count[0]}{suffix}'
        p.write_bytes(data)
        fe = tp.LibretroFrontend(core, save_dir=work / 'rt', core_options=dict(options or {}))
        try:
            fe.load_game(p)
        except Exception:
            fe.close()
            raise
        if not fe.lib.retro_serialize_size():
            fe_for.savestates = False
            return BootOnly(fe)
        return fe
    fe_for.savestates = True
    return fe_for


def trace(core, rom, suffix, system, frames, work, step=STEP, buttons=explore, options=None):
    """Run the tracing engine and return (scenes, make_frontend).

    Each scene also carries `earlier`: video memory SETTLE frames before it,
    which tells tiles that have been in place for a while from tiles the
    game was just loading or animates every frame.
    """
    from romancer import provenance as pv, graphics_trace as gt
    fe_for = opener(core, suffix, work, options)
    fe = fe_for(rom)
    s = pv.TraceSession(fe, checkpoint_every=300 if fe_for.savestates else 10 ** 9)
    s.start()
    scenes = []
    for _ in range(max(1, frames // step)):
        s.run(step - SETTLE, buttons)
        earlier = video_memory(s.lib)
        s.run(SETTLE, buttons)
        scene = gt.scene_from_session(s, system)
        scene.earlier = earlier
        scenes.append(scene)
    s.fe.close()
    return scenes, fe_for


def video_memory(lib, names=VIDEO_DOMAINS):
    """{domain: bytes} of the engine's video memory right now."""
    import ctypes
    from romancer import provenance as pv
    lib.romancer_trace_domain.restype = ctypes.POINTER(pv._Domain)
    out = {}
    for i in range(lib.romancer_trace_domain_count()):
        d = lib.romancer_trace_domain(i).contents
        if d.name.decode() in names and d.data:
            out[d.name.decode()] = ctypes.string_at(d.data, d.size)
    return out


def soak(fe_for, rom, plan, scene, buttons=explore, slack=12):
    """Run the edited ROM from power-on and look for the scene, changed only as planned
    (graphics_trace.verify_from_power_on)."""
    from romancer import graphics_trace as gt
    return gt.verify_from_power_on(fe_for, rom, plan, scene, buttons_for=buttons, slack=slack)


def redraw(tile):
    """A visibly different picture for a tile: every color index mirrored.

    Only the bit planes the tile uses are touched: a plane that is zero in
    every pixel stays zero. Games store some tiles with fewer planes than
    the hardware format has (3 of 4 on Super NES, for one) and make up the
    rest; an edit that needs a plane the ROM does not store would be refused
    for that reason alone, which is not what this sweep measures.
    """
    used = 0
    for p in tile.pixels:
        used |= p
    top = (1 << max(1, used.bit_length())) - 1
    return [top - p for p in tile.pixels]


# Overlay variants per processor, default first. The sweep stops at the first that replays as planned and is
# clean from power-on; otherwise every one is tried and recorded.
OVERLAY_VARIANTS = {
    'sm83': [{}, {'after_handler': True}],
    '6502': [{}, {'guard': False}],
    'z80': [{}, {'guard': False}, {'after_handler': True}, {'hook': 'poll'}],
    '68000': [{'guard': 'idle'}, {'guard': 'idle', 'after_handler': True}, {'guard': 'idle-wide'}, {}, {'guard': False},
              {'guard': False, 'after_handler': True}],
    '65816': [{'guard': 'idle'}, {'guard': 'idle', 'after_handler': True}, {'guard': 'idle-wide'}, {}, {'after_handler': True},
              {'hook': 'irq'}, {'hook': 'irq', 'after_handler': True}, {'hook': 'poll'}],
}


def brief(r):
    return {'verified': r['verified'], 'as_planned': r.get('as_planned'), 'by': r.get('by'),
            'repeatable': r.get('replay_is_repeatable'),
            'missed': {k: len(v) for k, v in r.get('missed', {}).items()}, 'unplanned': r.get('unplanned', {}),
            'changed': {k: len(v) for k, v in r.get('changed', {}).items()}}


def confirmed(sections):
    """True when one tile edit path of a measured scene replayed as planned."""
    te, de, ov = sections['tile_edit'], sections['derived_edit'], sections['overlay']
    return bool(te.get('as_planned') or (te.get('by') == 'screen' and te.get('verified')) or de.get('as_planned')
                or ov.get('as_planned') or any(v.get('as_planned') for v in ov.get('variants', [])))


def measure(rom, system, scenes, fe_for, result, buttons=explore):
    """Measure the last scene; when no tile edit is confirmed there, the earlier scenes too.

    The sections of the first scene with a confirmed tile edit path (else of
    the last scene) become the result; `scene_frame` says which scene that
    was and `scenes_tried` lists every frame measured.
    """
    tried = []
    chosen = None
    for scene in reversed(scenes):
        sections = measure_scene(rom, system, scene, fe_for, buttons)
        tried.append(scene.frame)
        if chosen is None:
            chosen = (scene, sections)
        if confirmed(sections):
            chosen = (scene, sections)
            break
    result.update(chosen[1])
    result['scene_frame'] = chosen[0].frame
    result['scenes_tried'] = tried


def measure_scene(rom, system, scene, fe_for, buttons=explore):
    from romancer import graphics_trace as gt
    from romancer import provenance as pv
    result = {}
    cpu = gt.CPU[system]
    slow = cpu in ('65816', '68000')

    # Replays start at the last two checkpoints and, failing those, at power-on; that bounds the cost
    # of an edit that turns out not to reach the scene.
    before = [c for c in scene.checkpoints if c[0] < scene.frame] or scene.checkpoints[:1]
    quick = pv.Scene(scene.id, scene.frame, scene.screen_sha256,
                     sorted({c[0]: c for c in scene.checkpoints[:1] + before[-2:]}.values()), scene.snapshot)
    quick.video = getattr(scene, 'video', None)

    # An overlay works every frame, so its replay is tried from the last two checkpoints first. When nothing at
    # all changes from there (a scene in which the game no longer takes the interrupt, though it did when the
    # tile was loaded), the run from the first checkpoint is the test.
    recent = pv.Scene(scene.id, scene.frame, scene.screen_sha256, before[-2:], scene.snapshot)
    recent.video = quick.video
    first = pv.Scene(scene.id, scene.frame, scene.screen_sha256, scene.checkpoints[:1], scene.snapshot)
    first.video = quick.video

    def verify(plan, expect=None):
        if getattr(plan, 'kind', '') != 'overlay':
            return gt.verify_plan(fe_for, rom, plan, quick, expect=expect, buttons_for=buttons)
        r = gt.verify_plan(fe_for, rom, plan, recent, expect=expect, buttons_for=buttons)
        if not r['verified'] and scene.checkpoints[0][0] < recent.checkpoints[0][0]:
            r = gt.verify_plan(fe_for, rom, plan, first, expect=expect, buttons_for=buttons)
        return r

    all_tiles = gt.tiles(scene, system, rom)
    used = gt.used_tile_addresses(scene, system)
    live = [t for t in all_tiles if not t.blank]
    shown = [t for t in live if t.addresses[0] in used]
    earlier = getattr(scene, 'earlier', None) or {}

    def settled(t):
        """The tile slot held the same bytes SETTLE frames before the scene."""
        mem = earlier.get(t.domain)
        return mem is None or bytes(mem[a] for a in t.addresses) == t.stored

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
    shown.sort(key=lambda t: (not settled(t), -uses.get(t.addresses[0], 0)))  # in place for a while, then most used
    result['layers'] = [{'name': l.name, 'size': [l.width, l.height], 'layout_source': l.layout_source,
                         'cells': l.status_counts()} for l in lay]

    # ---- one direct tile edit, replayed -----------------------------------
    pool = shown or live
    direct = {'candidates': sum(t.editable for t in pool)}
    packed_fail = None
    done = False
    for tile in [t for t in pool if t.editable][:4]:
        new = redraw(tile)
        try:
            writes = gt.plan_tile_edit(tile, new, rom)
        except ValueError as e:
            direct.setdefault('refused', []).append(str(e)[:80])
            packed_fail = packed_fail or tile
            continue
        r = verify(gt.with_checksums(rom, writes, system), gt.expect_for(tile, gt.encode_tile(new, tile.format)))
        direct.update(tile=tile.index, address=tile.addresses[0], layout=tile.layout, writes=len(writes),
                      from_frame=r.get('from_frame'), **brief(r))
        if r.get('as_planned') or (tile.domain == 'chr_rom' and r['verified']):
            done = True
            break
    if not done and pool and pool[0].domain == 'chr_rom':
        # Tiles the picture chip reads straight from ROM leave no trace in memory, and the list of tiles "on
        # screen" is only as good as the scroll position and the bank mapped when the scene was taken. Edit
        # every candidate at once; if the picture then changes, halve the set until one tile is left, and
        # count that single tile only if its own replay changes the picture.
        group = [t for t in pool if t.editable]

        def writes_for(ts):
            out = {}
            for t in ts:
                for o, a, b in gt.plan_tile_edit(t, redraw(t), rom):
                    out[o] = (o, a, b)
            return sorted(out.values())
        replays = 1
        hit = bool(group) and verify(writes_for(group), {})['verified']
        if group and not hit and len(live) > len(group):
            # not among the tiles the scene's registers point at: try every tile the cartridge has mapped
            group = [t for t in live if t.editable]
            replays += 1
            direct['widened'] = 'to every mapped tile, since no tile counted as on screen changes the picture'
            hit = verify(writes_for(group), {})['verified']
        if group and not hit:
            direct['all_at_once'] = 'editing every candidate tile together does not change the picture either'
        if hit:
            while len(group) > 1:
                half = group[:len(group) // 2]
                replays += 1
                group = half if verify(writes_for(half), {})['verified'] else group[len(half):]
            tile = group[0]
            r = verify(gt.with_checksums(rom, writes_for([tile]), system), {})
            direct.update(tile=tile.index, address=tile.addresses[0], layout=tile.layout, writes=16, found_by='halving',
                          replays=replays + 1, **brief(r))
    result['tile_edit'] = direct

    # ---- "change only this one": private copy of a plainly stored tile ------
    private = {}
    if direct.get('as_planned') and direct.get('layout') == 'plain' and fe_for.savestates:
        tile = next(t for t in pool if t.index == direct['tile'] and t.addresses[0] == direct['address'])
        new = gt.encode_tile(redraw(tile), tile.format)
        # The direct edit showed from which checkpoint a change to this data reaches the scene; a moved pointer
        # is judged from that one checkpoint, so a wrong candidate costs one replay and not three.
        at = [c for c in quick.checkpoints if c[0] == direct.get('from_frame')] or quick.checkpoints
        single = pv.Scene(scene.id, scene.frame, scene.screen_sha256, at, scene.snapshot)

        def verify_pointer(plan, expect=None):
            return gt.verify_plan(fe_for, rom, plan, single, expect=expect, buttons_for=buttons)
        try:
            plan = gt.plan_private_copy(tile, new, rom, scene, verify=verify_pointer, max_candidates=4 if slow else 12)
            private.update(pointer=plan.details['pointer']['encoding'], block=plan.details['new_size'],
                           repointed=plan.details.get('repointed'), grew=plan.rom_size > len(rom), **brief(plan.verified))
        except ValueError as e:
            private['error'] = str(e)[:240]
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
    hard.sort(key=lambda t: not settled(t))
    target = hard[0] if hard else packed_fail
    derived = {'tiles_on_screen': sum(t.status == 'derived' for t in shown)}
    if target is not None and target.domain != 'chr_rom':
        block = gt.find_compressed_block(scene, rom, system, target.domain, target.addresses[0], len(target.addresses))
        derived['tile'] = target.index
        derived['settled'] = settled(target)
        derived['codec'] = block.codec if block else None
        if block:
            derived['block'] = block.to_dict()
        try:
            plan = gt.plan_derived_tile_edit(target, redraw(target), rom, scene, verify=verify,
                                             max_candidates=6 if slow else 24)
            derived.update(path=plan.kind, **brief(plan.verified))
            if plan.kind == 'overlay':
                derived['overlay_options'] = {k: plan.details.get(k) for k in ('placement', 'hook', 'timing', 'guard')
                                              if plan.details.get(k) is not None}
        except ValueError as e:
            derived['error'] = str(e)[:400]
    result['derived_edit'] = derived

    # ---- the overlay fallback on its own -----------------------------------
    overlay = {}
    domain = 'chr' if system == 'nes' else 'vram'
    tile = (next((t for t in shown if t.domain == domain and settled(t)), None)
            or next((t for t in shown if t.domain == domain), None)
            or next((t for t in live if t.domain == domain and settled(t)), None)
            or next((t for t in live if t.domain == domain), None))
    if tile is None:
        if system == 'nes' and any(t.domain == 'chr_rom' for t in all_tiles):
            overlay['not_needed'] = 'tiles are read straight from ROM (CHR-ROM) and edited in place'
    else:
        overlay.update(tile=tile.index, settled=settled(tile))
        variants = []
        controls = {}
        edits = [(tile, redraw(tile))]
        fired = False
        for n, options in enumerate(OVERLAY_VARIANTS[cpu]):
            if options.get('hook') in ('irq', 'poll') and fired:
                continue        # the vertical-blank hook does run in this game
            entry = {'options': options}
            try:
                plan = gt.plan_overlay_patch(edits, rom, system, scene=scene, **options)
                entry.update(routine=plan.details.get('routine_size'), placement=plan.details.get('placement'),
                             **brief(verify(plan)))
                if entry.get('as_planned'):
                    # From power-on too; when that differs: is it the overlay, or does any added code change this run?
                    safety = gt.overlay_safety(fe_for, rom, plan, scene, system, edits=edits, options=options,
                                               buttons_for=buttons, cache=controls)
                    entry['soak'] = safety['run']
                    entry['safety'] = safety['state']
                    if 'hook_only' in safety:
                        entry['hook_only_soak'] = safety['hook_only']
                    if 'control' in safety:
                        entry['control_soak'] = safety['control']
            except ValueError as e:
                entry['error'] = str(e)[:160]
            variants.append(entry)
            fired = fired or bool(entry.get('verified'))
            if entry.get('as_planned') and entry['soak']['clean']:
                break
            if entry.get('as_planned') and 'hook_only_soak' in entry and not entry['hook_only_soak'].get('clean', True):
                break       # even the bare hook changes this game's run: no variant can reproduce the original run
            if 'error' in entry and n == 0 and cpu not in ('65816', '6502', 'sm83'):
                break       # a refusal that no other variant of this processor would lift
        overlay.update({k: v for k, v in variants[0].items() if k != 'options'})
        overlay['variants'] = variants
        # the older names for two of the variants, kept for readers of earlier results
        for v in variants[1:]:
            if v['options'] == {'guard': False}:
                overlay['unguarded'] = v
            if v['options'] == {'after_handler': True}:
                overlay['after_handler'] = v
    result['overlay'] = overlay
    return result


def one(sha, entry, core, system, frames, outdir, options=None, retry_options=None, fallback_cores=(), core_for=()):
    """Trace and measure one ROM.

    The engine is first asked to load the ROM as it is. When it refuses the
    content, the same engine is tried with `retry_options` (special-chip
    games need the engine's high-level chip emulation), then each of
    `fallback_cores` (a build for another chip, or another engine).
    `core_for` is [(text, engine)]: a ROM whose file name contains the text
    is given that engine first (a game that needs a special build).
    """
    import trace_probe as tp
    out = Path(outdir) / f'{sha}.json'
    if out.exists():
        return sha, 'cached'
    t0 = time.perf_counter()
    result = {'sha256': sha, 'system': system, 'member': entry['member'], 'core': Path(core).name, 'frames': frames,
              'sweep_version': SWEEP_VERSION}
    work = None
    try:
        rom, suf = tp.read_rom(entry['zip'] + '!' + entry['member'])
        work = Path(tempfile.mkdtemp(prefix='gfx'))
        attempts = [(core, dict(options or {}))]
        for text, special in core_for:
            if text.lower() in entry['member'].lower():
                attempts = [(special, dict(options or {})), (special, {**(options or {}), **(retry_options or {})})] + attempts
        if retry_options:
            attempts.append((core, {**(options or {}), **retry_options}))
        attempts += [(c, {**(options or {}), **(retry_options or {})}) for c in fallback_cores]
        rejected = []
        for n, (use_core, use_options) in enumerate(attempts):
            try:
                scenes, fe_for = trace(use_core, rom, suf, system, frames, work, options=use_options)
            except Exception as e:
                if 'rejected content' not in str(e) or n == len(attempts) - 1:
                    raise
                rejected.append(f'{Path(use_core).name} {use_options or ""}'.strip())
                continue
            result['core'], result['options'] = Path(use_core).name, use_options
            break
        if rejected:
            result['engines_that_refused'] = rejected
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
    if work is not None:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    return sha, 'ok' if result['ok'] else 'error'


AS_PLANNED = ('clean', 'timing', 'differs', 'unmeasured', 'disturbed')


def overlay_outcome(overlay):
    """One word for how the overlay fallback fared on a ROM, and the variant that got it there.

    clean        a variant replays as planned and a run from power-on reaches the scene changed only as planned
    timing       as planned in the scene; the run from power-on differs from the original run, but so does a run
                 with the bare interrupt hook, or with a routine of the same cost that touches nothing: any added
                 code changes this game's course, so the original run is no reference and nothing can be
                 attributed to the overlay
    disturbed    as planned in the scene; the run from power-on differs although the controls reproduce the
                 original run (or come far closer to it): the overlay's video access changes something else
                 (graphics_trace.overlay_safety has the exact rule)
    differs      as planned in the scene; the run from power-on differs while the bare hook reproduces the
                 original run, on a processor with no cost-matched control: time or video access, not known which
    unmeasured   as planned in the scene; the power-on comparison could not be made
    not-planned  the routine was added but the scene did not come out as planned
    refused      no routine could be placed (no free space, no handler, ...)
    none         no tile to try it on (or not needed: NES CHR-ROM)
    """
    variants = overlay.get('variants')
    if variants is None:       # results written before variants were recorded
        variants = [dict(overlay, options={})] if ('as_planned' in overlay or 'error' in overlay) else []
        for name, options in (('unguarded', {'guard': False}), ('after_handler', {'after_handler': True})):
            if name in overlay:
                variants.append(dict(overlay[name], options=options))
    if not variants:
        return 'none', None
    rank = {'clean': 0, 'timing': 1, 'differs': 2, 'unmeasured': 3, 'disturbed': 4, 'not-planned': 5, 'refused': 6}
    best = None
    for v in variants:
        if 'error' in v:
            state = 'refused'
        elif not v.get('as_planned'):
            state = 'not-planned'
        elif v.get('soak', {}).get('clean'):
            state = 'clean'
        elif 'safety' in v:
            state = v['safety']
        elif 'hook_only_soak' not in v or 'error' in v['hook_only_soak']:
            state = 'unmeasured'
        else:
            state = 'disturbed' if v['hook_only_soak'].get('clean') else 'timing'
        if best is None or rank[state] < rank[best[0]]:
            best = (state, v)
    return best


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

        def direct_ok(r):
            return bool(r['tile_edit'].get('as_planned') or (r['tile_edit'].get('by') == 'screen' and r['tile_edit'].get('verified')))
        s['tile_edit_as_planned'] = sum(direct_ok(r) for r in ok)
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
        outcomes = {r['sha256']: overlay_outcome(r['overlay']) for r in ok}
        shown = sum(sum(r['tiles']['on_screen'].values()) for r in ok)
        direct = sum(r['tiles']['on_screen']['rom'] + r['tiles']['on_screen']['code'] for r in ok)
        derived_ok = sum(r['tiles']['on_screen']['derived'] for r in ok
                         if r['derived_edit'].get('as_planned') or outcomes[r['sha256']][0] in AS_PLANNED)
        s['on_screen_tiles'] = shown
        s['on_screen_tiles_traced_to_rom_or_code'] = direct
        s['on_screen_derived_tiles_in_roms_with_a_confirmed_derived_path'] = derived_ok
        tally = {}
        for state, _ in outcomes.values():
            tally[state] = tally.get(state, 0) + 1
        s['overlay_outcome'] = tally
        as_planned = AS_PLANNED
        s['overlay_as_planned'] = sum(tally.get(k, 0) for k in as_planned)
        s['overlay_default_variant_as_planned'] = sum(bool(r['overlay'].get('as_planned')) for r in ok)
        s['overlay_clean_from_boot'] = tally.get('clean', 0)
        s['overlay_differs_from_boot_as_a_control_does'] = tally.get('timing', 0)
        s['overlay_differs_from_boot_though_the_controls_are_clean'] = tally.get('disturbed', 0)
        s['overlay_differs_from_boot_cause_not_separable'] = tally.get('differs', 0) + tally.get('unmeasured', 0)
        s['overlay_refused'] = tally.get('refused', 0)
        reasons = {}
        for r in ok:
            if outcomes[r['sha256']][0] == 'refused':
                why = outcomes[r['sha256']][1]['error']
                why = ''.join(c for c in why if not c.isdigit())[:70]
                reasons[why] = reasons.get(why, 0) + 1
        s['overlay_refusals'] = reasons
        place, options = {}, {}
        for r in ok:
            state, v = outcomes[r['sha256']]
            if state in as_planned:
                place[v.get('placement')] = place.get(v.get('placement'), 0) + 1
                key = json.dumps(v.get('options', {}), sort_keys=True)
                options[key] = options.get(key, 0) + 1
        s['overlay_placement'] = place
        s['overlay_variant_used'] = options
        s['any_tile_path_confirmed'] = sum(confirmed(r) for r in ok)
        s['scene_other_than_the_last'] = sum(r.get('scene_frame', r['frames']) != r['frames'] for r in ok)
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
    for flag, values in (('--option', a.option), ('--retry-option', a.retry_option), ('--fallback-core', a.fallback_core),
                         ('--core-for', a.core_for)):
        for v in values or []:
            cmd += [flag, v]
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
    ap.add_argument('--option', action='append', help='core option key=value, always applied (repeatable)')
    ap.add_argument('--retry-option', action='append',
                    help='core option key=value applied only when the engine refuses the ROM without it (repeatable)')
    ap.add_argument('--fallback-core', action='append',
                    help='another engine to try when the first refuses the ROM (repeatable)')
    ap.add_argument('--core-for', action='append', help='TEXT=ENGINE: ROMs whose name contains TEXT use this engine (repeatable)')
    ap.add_argument('--only', help='comma-separated sha256 prefixes')
    ap.add_argument('--reverse', action='store_true', help='take the ROMs in reverse order (a second sweep helping the first)')
    ap.add_argument('--one', help='run this one sha256 in this process (used by the sweep itself)')
    ap.add_argument('--report', action='store_true', help='print totals for OUTDIR and exit')
    a = ap.parse_args()
    if a.report:
        print(json.dumps(report(a.outdir), indent=1))
        return
    index = json.loads(Path(a.index).read_text())
    if a.one:
        entry = index[a.one]
        pairs = lambda xs: dict(o.split('=', 1) for o in xs or [])
        one(a.one, entry, a.core, entry['system_id'], a.frames, a.outdir, pairs(a.option), pairs(a.retry_option),
            a.fallback_core or (), [tuple(x.split('=', 1)) for x in a.core_for or []])
        return
    if not a.system or not a.core:
        ap.error('--system and --core are required')
    Path(a.outdir).mkdir(parents=True, exist_ok=True)
    todo = [(sha, e) for sha, e in index.items() if e['system_id'] in a.system]
    if a.only:
        todo = [(s, e) for s, e in todo if any(s.startswith(p) for p in a.only.split(','))]
    if a.reverse:
        todo.reverse()
    from concurrent.futures import ThreadPoolExecutor
    done = 0
    with ThreadPoolExecutor(a.jobs) as pool:
        for sha, state in pool.map(_run_one, [(sha, a) for sha, _ in todo]):
            done += 1
            print(f'{done}/{len(todo)} {sha[:12]} {state}', flush=True)


if __name__ == '__main__':
    main()
