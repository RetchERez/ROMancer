"""Trace every ROM in the corpus and record palette/graphics coverage.

    python -B trace/coverage_sweep.py INDEX.json OUTDIR --system gbc --core PATH
        [--jobs N] [--frames F] [--option key=value ...] [--only SHA,SHA] [--timeout S]

For each ROM: boot with the `explore` input script and take a scene every
FINE frames. Each scene records, per domain, how many bytes trace to ROM
data, code values, derived (computed/compressed) sources or nothing. The
scenes every STEP frames are the main ones; the ones between them are used
only when the main ones did not verify an edit.

The causal check then edits palette sources and replays the real engine from
a checkpoint of the scene:

* every edited replay is compared with an unedited replay from the same
  checkpoint, so only the edit can explain a difference;
* single-entry edits are tried on several candidate entries over all scenes
  (a game is judged by its best scene: fades and blank screens come and go);
* if an entry changes in palette RAM but is not on screen, one bulk edit of
  every traced entry of a scene is replayed;
* colors without a usable tag (faded, prepared by a cartridge coprocessor,
  copied before the scene's first checkpoint) are looked for in the ROM
  itself: the place another scene traced the same color to, or a plain copy
  of the palette line (palette_trace.stored_copies). These are proposals like
  any other and count only when the replay confirms them;
* if every live color is derived (faded/computed), nearby ROM bytes are
  searched with palette_trace.locate_derived_source;
* a ROM that is still not verified is played again with a second input
  script, and judged by the better of the two runs.

`causal.verified` is true only when the edited entry took the planned value
in palette RAM *and* the replayed screen differs from the unedited replay.

Engine options are the ones the editor uses (romancer.trace_cores.core_options)
plus any --option given here.

Results are one JSON per ROM, so the sweep can be resumed. Every ROM runs in
its own process: an engine crash or hang is recorded for that ROM only, and
every worker still running is stopped when the sweep exits.
"""
import argparse
import atexit
import dataclasses
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))


STEP = 900           # main scenes
FINE = 300           # scenes between them, used when the main ones do not verify
MAX_SINGLE = 8       # single-entry causal attempts per pass
MAX_BULK = 2         # bulk (whole scene palette) attempts per pass
MAX_DERIVED = 2      # derived swatches searched per ROM
MAX_SEARCH = 12      # single-entry attempts at places found by searching the ROM
LIVE_KINDS = ('rom', 'code', 'derived', 'unknown')


def explore(frame):
    """Deterministic play: get through menus, then walk, jump and attack."""
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


def explore_b(frame):
    """A second way through: every face button on the menus, then play from early on, mostly to the right."""
    if frame < 150:
        return []
    if frame < 900 or frame % 600 < 20:
        tap = frame // 30
        return [('start', 'a', 'b', 'start', 'y', 'x')[tap % 6]] if frame % 30 < 5 else []
    direction = ('right', 'right', 'up', 'right', 'down', 'left')[(frame // 300) % 6]
    held = [direction] if frame % 300 < 250 else []
    if frame % 36 < 8:
        held.append('b')
    if frame % 52 < 5:
        held.append('a')
    if frame % 190 < 4:
        held.append('y')
    return held


SCRIPTS = (('explore', explore), ('explore-b', explore_b))


def _inverse(sw):
    return [[255 - c for c in rgb] for rgb in sw.rgb] if sw.format == 'dmg-shades' else [255 - c for c in sw.rgb[0]]


def _live(swatches):
    return [x for x in swatches if any(x.stored)]  # skip never-used black entries


def _screen_colors(frame):
    """Colors on screen, five bits per channel: a hint for which palette entries are visible."""
    if frame is None:
        return frozenset()
    rgb = frame.rgb
    return frozenset((r >> 3, g >> 3, b >> 3) for r, g, b in set(zip(rgb[0::3], rgb[1::3], rgb[2::3])))


def _replay(pv, fe_for, data, scene, checkpoint, script=explore):
    """Run `data` from one checkpoint of `scene` to the scene's frame; return the snapshot."""
    start, state = checkpoint
    fe = fe_for(data)
    try:
        fe.unserialize(state)
        session = pv.TraceSession(fe)
        session.frame = start
        session.start()
        session.run(scene.frame - start, script)
        return session.snapshot()
    finally:
        fe.close()


def _checkpoints(scene):
    """Latest first, then one about a third of the way back, then boot."""
    cps = [c for c in scene.checkpoints if c[0] < scene.frame]  # a replay must run at least one frame
    if not cps:
        return []
    picks = [cps[-1]]
    mid = [c for c in cps if c[0] <= scene.frame - 1200]
    if mid:
        picks.append(mid[-1])
    picks.append(cps[0])
    out, seen = [], set()
    for c in picks:
        if c[0] not in seen:
            seen.add(c[0]); out.append(c)
    return out


def _diff(scene, snap, domain):
    a, b = scene.snapshot.domains.get(domain), snap.domains.get(domain)
    if a is None or b is None or a.data is None or b.data is None:
        return set()
    return {i for i, (x, y) in enumerate(zip(a.data, b.data)) if x != y}


class _Controls:
    """Unedited replays, one per (scene, checkpoint): the baseline every edited replay is compared with.

    A savestate taken at an awkward moment can replay slightly differently from the
    original run, so an edited replay is never compared with the original run, only
    with an unedited replay from the same checkpoint. A checkpoint whose unedited
    replay does not match the original run must reproduce itself twice to be used.
    """

    def __init__(self, pv, fe_for, rom, script=explore):
        self.pv, self.fe_for, self.rom, self.cache, self.script = pv, fe_for, rom, {}, script

    def get(self, scene, cp):
        key = (scene.frame, cp[0])
        if key not in self.cache:
            snap = _replay(self.pv, self.fe_for, self.rom, scene, cp, self.script)
            same = snap.screen_sha256 == scene.screen_sha256 and not any(_diff(scene, snap, n) for n in ('palette', 'dmg_palette'))
            if not same:
                again = _replay(self.pv, self.fe_for, self.rom, scene, cp, self.script)
                if again.screen_sha256 != snap.screen_sha256 or any(
                        a.data != again.domains[n].data for n, a in snap.domains.items() if n in ('palette', 'dmg_palette')):
                    snap = None  # this checkpoint does not replay reproducibly
            self.cache[key] = (snap, same)
        return self.cache[key]


def _attempt(controls, scene, targets, writes, need=1):
    """Replay `writes`; report whether the targeted entries took their planned bytes and the screen changed.

    targets: [(swatch, planned stored bytes)]. Stops at the first checkpoint
    where at least `need` targets hold exactly the planned bytes.
    """
    edited = bytearray(controls.rom)
    for off, _old, new in writes:
        edited[off] = new
    edited = bytes(edited)
    if getattr(controls, 'system', None):  # the saved ROM carries a repaired header checksum; games that check it need it
        from romancer import graphics_trace as gt
        edited = gt.fix_checksums(edited, controls.rom, controls.system)
    best = {'entries_changed': 0, 'entries_exact': 0, 'screen_changed': False, 'from_frame': None, 'baseline': None}
    for cp in _checkpoints(scene):
        control, same = controls.get(scene, cp)
        if control is None:
            continue
        snap = _replay(controls.pv, controls.fe_for, edited, scene, cp, controls.script)
        changed = exact = 0
        for sw, planned in targets:
            d, c = snap.domains.get(sw.domain), control.domains.get(sw.domain)
            if d is None or d.data is None or c is None or c.data is None:
                continue
            width = len(sw.stored)
            now = bytes(d.data[sw.entry * width:(sw.entry + 1) * width])
            if bytes(c.data[sw.entry * width:(sw.entry + 1) * width]) != sw.stored:
                continue  # the unedited replay does not show this entry as the scene had it
            changed += now != sw.stored
            exact += now == planned
        screen = snap.screen_sha256 != control.screen_sha256
        result = {'entries_changed': changed, 'entries_exact': exact, 'screen_changed': screen, 'from_frame': cp[0],
                  'baseline': 'original run' if same else 'unedited replay'}
        if (exact, screen) > (best['entries_exact'], best['screen_changed']) or best['from_frame'] is None:
            best = result
        if exact >= need:
            break  # the edit reached palette RAM; an earlier checkpoint would end in the same state
    return best


def _plan(pt, sw, rom):
    """(writes, planned stored bytes) for inverting one swatch, or None.

    Derived entries are planned only when the game currently stores the ROM
    bytes unchanged (plan_derived_edit); the replay then decides.
    """
    try:
        plan = pt.plan_derived_edit if sw.status == 'derived' else pt.plan_color_edit
        writes = plan(sw, _inverse(sw), rom)
    except (ValueError, TypeError, IndexError):
        return None
    if not writes:
        return None
    return writes, pt.encode_swatch(sw, _inverse(sw))


def _weak(x):
    return any(q and q['weak'] for q in x.sources)


def _judge(pv, pt, fe_for, rom, system, frames, script):
    """Play `frames` with `script`, then try to verify one palette edit. Returns this run's part of the result."""
    part = {}
    s = pv.TraceSession(fe_for(rom), checkpoint_every=300)
    s.start()
    scenes, screen_colors = [], {}
    for _ in range(frames // FINE):
        s.run(FINE, script)
        scenes.append(pv.scene_from_session(s))
        screen_colors[scenes[-1].frame] = _screen_colors(s.fe.last_frame)
    s.fe.close()
    main = [sc for sc in scenes if sc.frame % STEP == 0]
    scene = main[-1]
    # Union of ROM sources seen across the main snapshots, per domain and kind.
    seen = {}
    for sc in main:
        for name, d in sc.snapshot.domains.items():
            for kind, label in ((pv.RT_ROM, 'rom'), (pv.RT_IMM, 'code'), (pv.RT_DERIVED, 'derived')):
                seen.setdefault(name, {}).setdefault(label, set()).update(d.sources((kind,)))
    part['sources_union'] = {n: {k: len(v) for k, v in kinds.items()} for n, kinds in seen.items()}
    part['distinct_screens'] = len({sc.screen_sha256 for sc in main})
    part['screen_sha256'] = scene.screen_sha256
    part['domains'] = scene.snapshot.kind_counts()

    def describe(sc):
        sw = pt.swatches(sc, system)
        live = _live(sw)
        return {'scene': sc, 'swatches': sw, 'live': live,
                'counts': {k: sum(1 for x in live if x.status == k) for k in LIVE_KINDS},
                'weak': sum(1 for x in live if x.editable and _weak(x))}

    every = [describe(sc) for sc in scenes]
    per_scene = [p for p in every if p['scene'].frame % STEP == 0]
    extra = [p for p in every if p['scene'].frame % STEP]
    part['scenes'] = [{'frame': p['scene'].frame, 'screen_sha256': p['scene'].screen_sha256,
                       'palette_live': p['counts'], 'weak_editable': p['weak']} for p in per_scene]
    # A ROM is judged by its best scene: the one with the most directly traced live colors.
    best = max(per_scene, key=lambda p: (p['counts']['rom'] + p['counts']['code'], p['counts']['derived'], p['scene'].frame))
    status = {}
    for x in best['swatches']:
        status[x.status] = status.get(x.status, 0) + 1
    part['palette_entries'] = status
    part['palette_live'] = best['counts']
    part['best_scene_frame'] = best['scene'].frame

    # Control: an unedited replay must reproduce the scene, or "the screen changed" means nothing.
    controls = _Controls(pv, fe_for, rom, script); controls.system = system
    control, _same = controls.get(scene, _checkpoints(scene)[0])
    part['deterministic'] = {'screen': bool(control) and control.screen_sha256 == scene.screen_sha256,
                             'domains': bool(control) and all(not _diff(scene, control, n) for n in scene.snapshot.domains),
                             'replay_reproducible': control is not None}

    attempts = []
    causal = {'verified': False, 'entry_changed': False, 'screen_changed': False, 'attempts': attempts}
    part['causal'] = causal

    # On Game Boy Color the DMG shade registers do not reach the screen, so they go last.
    cgb = any(x.domain == 'palette' for p in every for x in p['live'])
    plans = {}

    def plan_for(x):
        key = (x.domain, x.entry, x.stored, tuple(q['offset'] if q else None for q in x.sources))
        if key not in plans:
            plans[key] = _plan(pt, x, rom) if x.status in ('rom', 'code', 'derived') else None
        return plans[key]

    def visible(p, x):
        shown = screen_colors.get(p['scene'].frame, ())
        return any((c[0] >> 3, c[1] >> 3, c[2] >> 3) in shown for c in x.rgb)

    def rank_of(p, x):
        r = 3 if _weak(x) else {'rom': 0, 'code': 1, 'derived': 2}[x.status]
        if cgb and x.domain == 'dmg_palette':
            return r + 8
        return r if visible(p, x) else r + 4  # colors seen on screen first

    tried = set()

    def traced_pass(group, label):
        """Single edits of traced entries, then one bulk edit per scene, over the scenes in `group`."""
        # Candidates: later scenes first (gameplay). Strong ROM data, then code values, then
        # computed entries that currently equal their ROM bytes, then weak (00/FF) matches.
        order = sorted(group, key=lambda p: -p['scene'].frame)
        queue = []
        for rank in range(12):
            for p in order:
                picked = 0
                for x in p['live']:
                    if x.status not in ('rom', 'code', 'derived') or rank_of(p, x) != rank:
                        continue
                    key = tuple(q['offset'] if q else None for q in x.sources)
                    if key in tried or not plan_for(x):
                        continue
                    tried.add(key)
                    queue.append((p, x))
                    picked += 1
                    if picked >= 2:
                        break
        for p in group:
            p['plannable'] = sum(1 for x in p['live'] if x.status in ('rom', 'code', 'derived') and plan_for(x))
        for p, x in queue[:MAX_SINGLE]:
            writes, planned = plan_for(x)
            r = _attempt(controls, p['scene'], [(x, planned)], writes)
            ok_entry = r['entries_exact'] == 1
            ok = ok_entry and r['screen_changed']
            attempts.append({'mode': 'single', 'frame': p['scene'].frame, 'domain': x.domain, 'entry': x.entry, 'status': x.status,
                             'weak': _weak(x), 'offsets': [w[0] for w in writes],
                             'entry_changed': ok_entry, 'entry_moved': bool(r['entries_changed']),
                             'screen_changed': r['screen_changed'], 'from_frame': r['from_frame'], 'baseline': r['baseline']})
            if ok_entry:
                causal['entry_changed'] = True
            if ok:
                causal.update(verified=True, screen_changed=True, mode='single', entry=x.entry, domain=x.domain,
                              frame=p['scene'].frame, writes=len(writes), baseline=r['baseline'], scenes=label)
                return len(queue)

        # An entry can be loaded yet unused on screen: edit every traced entry of a scene at once.
        bulk = sorted((p for p in group if p['plannable']), key=lambda p: (-p['plannable'], -p['scene'].frame))
        done_screens = set()
        for p in bulk:
            if len(done_screens) >= MAX_BULK:
                break
            if p['scene'].screen_sha256 in done_screens:
                continue
            done_screens.add(p['scene'].screen_sha256)
            merged, targets = {}, []
            # ROM data only: a weak (00/FF) match or a shared code value edited in bulk can break the game.
            strong = [x for x in p['live'] if x.status in ('rom', 'derived') and not _weak(x)
                      and not (cgb and x.domain == 'dmg_palette')]
            for x in strong or p['live']:
                plan = plan_for(x) if x.status in ('rom', 'code', 'derived') and not (cgb and x.domain == 'dmg_palette') else None
                if not plan or any(w[0] in merged and merged[w[0]][2] != w[2] for w in plan[0]):
                    continue
                for w in plan[0]:
                    merged[w[0]] = w
                targets.append((x, plan[1]))
            if not targets:
                continue
            r = _attempt(controls, p['scene'], targets, list(merged.values()), need=(len(targets) + 1) // 2)
            # Most targeted entries must take exactly the planned value: a crash also changes the screen.
            ok_entry = r['entries_exact'] * 2 >= len(targets)
            attempts.append({'mode': 'bulk', 'frame': p['scene'].frame, 'targets': len(targets), 'writes': len(merged),
                             'entries_exact': r['entries_exact'], 'entries_moved': r['entries_changed'],
                             'screen_changed': r['screen_changed'], 'from_frame': r['from_frame'], 'baseline': r['baseline']})
            if ok_entry:
                causal['entry_changed'] = True
            if ok_entry and r['screen_changed']:
                causal.update(verified=True, screen_changed=True, mode='bulk', frame=p['scene'].frame,
                              writes=len(merged), targets=len(targets), entries_exact=r['entries_exact'], baseline=r['baseline'],
                              scenes=label)
                break
        return len(queue)

    part['candidates'] = traced_pass(per_scene, 'main')
    for i, p in enumerate(per_scene):
        part['scenes'][i]['plannable'] = p['plannable']
        part['scenes'][i]['passthrough'] = sum(1 for x in p['live'] if x.status == 'derived' and plan_for(x))
    if not causal['verified'] and extra:
        part['candidates_between'] = traced_pass(extra, 'between')

    # Colors the tags do not lead to: look for the stored color in the ROM itself.
    if not causal['verified']:
        _search_pass(pt, controls, every, rom, system, cgb, visible, causal)

    # Every live color is computed: measure which nearby ROM bytes move a derived entry.
    if not causal['entry_changed']:
        cands = sorted((p for p in per_scene if p['counts']['derived']), key=lambda p: (-p['counts']['derived'], -p['scene'].frame))
        located, searched = [], 0
        for p in cands[:1]:
            sc = p['scene']
            pruned = dataclasses.replace(sc, checkpoints=_checkpoints(sc)[::-1][:2])  # boot, then one later

            def verify(edited, sc=pruned):
                return pv.verify_edit(fe_for, rom, edited, sc, domains=tuple(sc.snapshot.domains), buttons_for=script)

            seen_off = set()
            for x in p['live']:
                if x.status != 'derived' or searched >= MAX_DERIVED:
                    continue
                key = tuple(q['offset'] for q in x.sources if q)
                if key in seen_off:
                    continue
                seen_off.add(key); searched += 1
                hits = pt.locate_derived_source(verify, rom, x, sc, radius=2)
                if hits:
                    located.append({'frame': sc.frame, 'domain': x.domain, 'entry': x.entry, 'hits': hits[:8]})
        causal['derived_searched'] = searched
        if located:
            causal['derived_located'] = located
            # The color may be put together from several of those bytes: measure each bit's effect and solve.
            for found in located:
                p = cands[0]
                x = next(x for x in p['live'] if x.domain == found['domain'] and x.entry == found['entry'])
                if _measured(pt, controls, p['scene'], x, [h['offset'] for h in found['hits']], rom, causal):
                    break
    return part


def _measured(pt, controls, scene, x, offsets, rom, causal):
    """Plan an entry from the measured effect of each ROM bit near `offsets` (palette_trace.plan_by_measurement)."""
    from romancer import graphics_trace as gt
    width = len(x.stored)
    points = _checkpoints(scene)[::-1][:2][::-1]     # one later checkpoint, then boot: as the search that found the bytes
    state = {'from': None, 'probes': 0}

    def measure(writes):
        edited = bytearray(rom)
        for off, _old, new in writes:
            edited[off] = new
        edited = gt.fix_checksums(bytes(edited), rom, controls.system)
        state['probes'] += 1
        for cp in points:
            if state['from'] is not None and cp[0] != state['from']:
                continue
            control, _same = controls.get(scene, cp)
            if control is None or control.domains[x.domain].data is None:
                continue
            if bytes(control.domains[x.domain].data[x.entry * width:(x.entry + 1) * width]) != x.stored:
                continue
            snap = _replay(controls.pv, controls.fe_for, edited, scene, cp, controls.script)
            now = bytes(snap.domains[x.domain].data[x.entry * width:(x.entry + 1) * width])
            if now != x.stored:
                state['from'] = cp[0]
                return now
        return None

    planned = pt.encode_swatch(x, _inverse(x))
    writes = pt.plan_by_measurement(measure, rom, offsets, x.stored, planned)
    record = {'mode': 'measured', 'frame': scene.frame, 'domain': x.domain, 'entry': x.entry, 'status': x.status,
              'probes': state['probes'], 'offsets': [w[0] for w in writes or ()], 'entry_changed': False, 'entry_moved': False,
              'screen_changed': False}
    causal['attempts'].append(record)
    if not writes:
        return False
    r = _attempt(controls, scene, [(x, planned)], writes)
    ok_entry = r['entries_exact'] == 1
    record.update(entry_changed=ok_entry, entry_moved=bool(r['entries_changed']), screen_changed=r['screen_changed'],
                  from_frame=r['from_frame'], baseline=r['baseline'])
    if ok_entry:
        causal['entry_changed'] = True
    if ok_entry and r['screen_changed']:
        causal.update(verified=True, screen_changed=True, mode='measured', entry=x.entry, domain=x.domain,
                      frame=scene.frame, writes=len(writes), baseline=r['baseline'])
    return causal['verified']


def _search_pass(pt, controls, every, rom, system, cgb, visible, causal):
    """Edit colors at places found in the ROM by content: single entries first, then a whole scene at once."""
    attempts = causal['attempts']
    # Where any scene traced a color directly: a fade tags the same entry 'derived' a moment later.
    known = {}
    for p in every:
        for x in p['live']:
            if x.status in ('rom', 'code') and not _weak(x):
                known.setdefault((x.domain, x.entry, x.stored), []).append(tuple(q['offset'] for q in x.sources))
    cache, found = {}, {}

    def places(p, x):
        """[(how, writes, planned bytes)] for this entry, best first."""
        key = (p['scene'].frame, x.domain, x.entry)
        if key not in found:
            plans, starts = [], set()
            # The editor's own search (palette_trace.found_places), so the sweep measures what the editor can do.
            for place in pt.found_places(x, p['swatches'], rom, system, known.get((x.domain, x.entry, x.stored), ()), cache=cache):
                try:
                    writes = pt.plan_at(x, _inverse(x), rom, place['offsets'])
                except (ValueError, TypeError, IndexError):
                    continue
                if writes and writes[0][0] not in starts:
                    starts.add(writes[0][0])
                    plans.append((place['how'], writes, pt.encode_swatch(x, _inverse(x))))
            found[key] = plans
        return found[key]

    order = sorted(every, key=lambda p: -p['scene'].frame)
    queue, tried = [], set()
    for shown in (True, False):
        for alternative in range(2):
            for p in order:
                picked = 0
                for x in p['live']:
                    if (cgb and x.domain == 'dmg_palette') or visible(p, x) != shown:
                        continue
                    options = places(p, x)
                    if len(options) <= alternative:
                        continue
                    how, writes, planned = options[alternative]
                    key = tuple(w[0] for w in writes)
                    if key in tried:
                        continue
                    tried.add(key)
                    queue.append((p, x, how, writes, planned))
                    picked += 1
                    if picked >= 2:
                        break
    causal['search_candidates'] = len(queue)
    for p, x, how, writes, planned in queue[:MAX_SEARCH]:
        r = _attempt(controls, p['scene'], [(x, planned)], writes)
        ok_entry = r['entries_exact'] == 1
        attempts.append({'mode': 'search', 'how': how, 'frame': p['scene'].frame, 'domain': x.domain, 'entry': x.entry,
                         'status': x.status, 'offsets': [w[0] for w in writes], 'entry_changed': ok_entry,
                         'entry_moved': bool(r['entries_changed']), 'screen_changed': r['screen_changed'],
                         'from_frame': r['from_frame'], 'baseline': r['baseline']})
        if ok_entry:
            causal['entry_changed'] = True
        if ok_entry and r['screen_changed']:
            causal.update(verified=True, screen_changed=True, mode='search', how=how, entry=x.entry, domain=x.domain,
                          frame=p['scene'].frame, writes=len(writes), baseline=r['baseline'])
            return

    # The found colors may all be loaded yet unused on screen: edit every found entry of a scene at once.
    counted = sorted(((sum(1 for x in p['live'] if not (cgb and x.domain == 'dmg_palette') and places(p, x)), p) for p in every),
                     key=lambda c: (-c[0], -c[1]['scene'].frame))
    done_screens = set()
    for count, p in counted:
        if not count or len(done_screens) >= MAX_BULK:
            break
        if p['scene'].screen_sha256 in done_screens:
            continue
        done_screens.add(p['scene'].screen_sha256)
        merged, targets = {}, []
        for x in p['live']:
            if cgb and x.domain == 'dmg_palette':
                continue
            for how, writes, planned in places(p, x)[:1]:
                if any(w[0] in merged and merged[w[0]][2] != w[2] for w in writes):
                    continue
                for w in writes:
                    merged[w[0]] = w
                targets.append((x, planned))
        if not targets:
            continue
        r = _attempt(controls, p['scene'], targets, list(merged.values()), need=(len(targets) + 1) // 2)
        ok_entry = r['entries_exact'] * 2 >= len(targets)   # most must take exactly the planned value: a crash also changes the screen
        attempts.append({'mode': 'search-bulk', 'frame': p['scene'].frame, 'targets': len(targets), 'writes': len(merged),
                         'entries_exact': r['entries_exact'], 'entries_moved': r['entries_changed'],
                         'screen_changed': r['screen_changed'], 'from_frame': r['from_frame'], 'baseline': r['baseline']})
        if ok_entry:
            causal['entry_changed'] = True
        if ok_entry and r['screen_changed']:
            causal.update(verified=True, screen_changed=True, mode='search-bulk', frame=p['scene'].frame,
                          writes=len(merged), targets=len(targets), entries_exact=r['entries_exact'], baseline=r['baseline'])
            return


def _standing(part):
    """How far a run got, for choosing between two runs of one ROM (as coverage_report.classify orders them)."""
    causal, live = part.get('causal') or {}, part.get('palette_live') or {}
    return (4 if causal.get('verified') else 3 if causal.get('entry_changed') else 2 if live.get('rom', 0) + live.get('code', 0)
            else 1 if causal.get('derived_located') or live.get('derived', 0) else 0)


def one(sha, entry, core, system, frames, outdir, options=None):
    import trace_probe as tp
    from romancer import provenance as pv, palette_trace as pt
    out = Path(outdir) / f'{sha}.json'
    if out.exists():
        return sha, 'cached'
    t0 = time.perf_counter()
    result = {'sha256': sha, 'system': system, 'member': entry['member'], 'core': Path(core).name, 'frames': frames,
              'options': options or {}, 'sweep_version': 8}
    work = Path(tempfile.mkdtemp(prefix='rt'))
    try:
        rom, suf = tp.read_rom(entry['zip'] + '!' + entry['member'])
        made = [0]

        def fe_for(data):
            made[0] += 1
            p = work / f'g{made[0]}{suf}'
            p.write_bytes(data)
            fe = tp.LibretroFrontend(core, save_dir=work / 'rt', core_options=dict(options or {}))
            fe.load_game(p)
            return fe

        runs = []
        for name, script in SCRIPTS:
            part = _judge(pv, pt, fe_for, rom, system, frames, script)
            part['script'] = name
            runs.append({'script': name, 'standing': _standing(part), 'distinct_screens': part['distinct_screens'],
                         'palette_live': part['palette_live'], 'attempts': len(part['causal']['attempts'])})
            if len(runs) == 1 or _standing(part) > _standing(result):
                result.update(part)
            if result['causal']['verified']:
                break
        result['runs'] = runs
        result['ok'] = True
    except Exception as e:  # recorded, never hidden
        result['ok'] = False
        result['error'] = f'{type(e).__name__}: {e}'
        result['trace'] = traceback.format_exc()[-1500:]
    result['seconds'] = round(time.perf_counter() - t0, 1)
    out.write_text(json.dumps(result, indent=1))
    shutil.rmtree(work, ignore_errors=True)
    return sha, 'ok' if result['ok'] else 'error'


_WORKERS = set()
_WORKERS_LOCK = threading.Lock()
_STOPPING = threading.Event()


def _stop_workers():
    """Stop every worker still running: the sweep never leaves an engine process behind."""
    _STOPPING.set()
    with _WORKERS_LOCK:
        running = list(_WORKERS)
    for p in running:
        try:
            if os.name == 'nt':  # the whole tree: a worker may be inside an engine call
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)], capture_output=True)
            else:
                p.kill()
        except OSError:
            pass
    for p in running:
        try:
            p.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _options_for(a, system, sha):
    """The editor's engine options for this ROM, then the ones given on the command line."""
    from romancer.trace_cores import core_options
    options = {} if a.plain_options else dict(core_options(system, sha))
    options.update(o.split('=', 1) for o in a.option or [])
    return options


def _spawn(sha, entry, a):
    """Run one ROM in its own process so a crash or hang cannot stop the sweep."""
    out = Path(a.outdir) / f'{sha}.json'
    if out.exists():
        return sha, 'cached'
    if _STOPPING.is_set():
        return sha, 'stopped'
    cmd = [sys.executable, '-B', str(Path(__file__).resolve()), a.index, a.outdir, '--core', a.core,
           '--frames', str(a.frames), '--worker', sha]
    for s in a.system:
        cmd += ['--system', s]
    for o in a.option or []:
        cmd += ['--option', o]
    if a.plain_options:
        cmd.append('--plain-options')
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors='replace')
    with _WORKERS_LOCK:
        _WORKERS.add(p)
    try:
        try:
            _out, err = p.communicate(timeout=a.timeout)
            failure = None if out.exists() else f'EngineCrash: worker exited with code {p.returncode}: {(err or "")[-600:]}'
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            failure = None if out.exists() else f'Timeout: no result after {a.timeout} s'
    finally:
        with _WORKERS_LOCK:
            _WORKERS.discard(p)
    if _STOPPING.is_set() and not out.exists():
        return sha, 'stopped'
    if failure:
        out.write_text(json.dumps({'sha256': sha, 'system': entry['system_id'], 'member': entry['member'],
                                   'core': Path(a.core).name, 'frames': a.frames, 'ok': False, 'error': failure,
                                   'seconds': round(time.perf_counter() - t0, 1)}, indent=1))
        return sha, 'error'
    return sha, 'ok' if json.loads(out.read_text()).get('ok') else 'error'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('index'); ap.add_argument('outdir')
    ap.add_argument('--system', required=True, action='append')
    ap.add_argument('--core', required=True)
    ap.add_argument('--jobs', type=int, default=max(1, min(6, (os.cpu_count() or 2) - 1)))
    ap.add_argument('--frames', type=int, default=3600)
    ap.add_argument('--only', help='comma-separated sha256 prefixes')
    ap.add_argument('--catalog', help='rom_samples.json: sweep only the ROMs in this catalog')
    ap.add_argument('--option', action='append', help="core option key=value (repeatable), on top of the editor's options")
    ap.add_argument('--plain-options', action='store_true', help="do not start from the editor's engine options")
    ap.add_argument('--timeout', type=int, default=2400, help='seconds per ROM')
    ap.add_argument('--reverse', action='store_true', help='work from the end of the list (a second sweep meeting the first)')
    ap.add_argument('--worker', help=argparse.SUPPRESS)
    a = ap.parse_args()
    index = json.loads(Path(a.index).read_text())
    Path(a.outdir).mkdir(parents=True, exist_ok=True)
    if a.worker:
        e = index[a.worker]
        one(a.worker, e, a.core, e['system_id'], a.frames, a.outdir, _options_for(a, e['system_id'], a.worker))
        return
    todo = [(sha, e) for sha, e in index.items() if e['system_id'] in a.system]
    if a.catalog:
        wanted = {r['sha256'] for r in json.loads(Path(a.catalog).read_text(encoding='utf-8'))['records']}
        todo = [(s, e) for s, e in todo if s in wanted]
    if a.only:
        todo = [(s, e) for s, e in todo if any(s.startswith(p) for p in a.only.split(','))]
    if a.reverse:
        todo.reverse()
    done = 0
    atexit.register(_stop_workers)
    for sig in (signal.SIGINT, signal.SIGTERM) + ((signal.SIGBREAK,) if hasattr(signal, 'SIGBREAK') else ()):
        signal.signal(sig, lambda *_: (_stop_workers(), os._exit(1)))
    pool = ThreadPoolExecutor(a.jobs)
    try:
        futures = [pool.submit(_spawn, sha, e, a) for sha, e in todo]
        for f in as_completed(futures):
            sha, state = f.result(); done += 1
            print(f'{done}/{len(todo)} {sha[:12]} {state}', flush=True)
    finally:
        _stop_workers()
        pool.shutdown(wait=True, cancel_futures=True)


if __name__ == '__main__':
    main()
