"""Study the packed graphics the codecs do not recognise yet, and confirm the ones they do.

    python -B trace/codec_survey.py dump   INDEX.json SWEEPDIR DUMPDIR [--system S ...] [--jobs N] [--all]
    python -B trace/codec_survey.py match  INDEX.json DUMPDIR [--system S ...] [--codec NAME ...] [--out FILE]
    python -B trace/codec_survey.py search INDEX.json DUMPDIR MATCHES.json [--system S ...] [--out FILE]
    python -B trace/codec_survey.py family INDEX.json DUMPDIR [--out FILE]
    python -B trace/codec_survey.py verify INDEX.json DUMPDIR OUTDIR [--system S ...] [--jobs N] [--only SHA,...] [--list FILE]
    python -B trace/codec_survey.py report OUTDIR [SWEEPDIR] [--also OLDOUTDIR ...] [--catalog FILE] [--json OUT]

dump    For every ROM whose sweep result (SWEEPDIR/<sha>.json) has a tile the
        game unpacks itself, run the tracing engine as the sweep does and keep
        the final scene's traced memory (contents, source tags, writer PCs) and
        a handful of unpacked target tiles in DUMPDIR/<sha>.pkl. Everything
        after that works offline from the dumps.
match   Run find_compressed_block on every dumped target with the codecs as
        they are now. This is the quick loop while writing a codec.
search  For ROMs `match` left unexplained, try every layout of the parameterised
        codec families (gfx_codecs.search_families). A hit names a concrete
        codec to add to gfx_codecs.
family  Group the ROMs no codec explains by the code around the instruction
        that wrote the tile (the unpacker): ROMs whose code shares enough byte
        runs are one family.
verify  For ROMs that match offline (or those named in --list): trace again and,
        in each scene from the last back, plan an edit through the codec
        (plan_block_edit: re-encode in place or relocate) and replay it
        (verify_plan). `confirmed`: the planned bytes arrived; `clean`: and no
        other byte of the block's stretch of video memory changed. One JSON per
        ROM in OUTDIR; the shared sweep results are never written.
report  Totals of OUTDIR by system; with SWEEPDIR (and --also, earlier verify
        runs), the count of ROMs with a replay-confirmed codec path before
        and after.
"""
import argparse
import json
import pickle
import subprocess
import sys
import tempfile
import time
import traceback
import zlib
from array import array
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))

CORES = {'gb': 'gambatte/gambatte_libretro.dll', 'gbc': 'gambatte/gambatte_libretro.dll',
         'nes': 'out/fceumm_libretro.dll', 'snes': 'out/bsnes_mercury_balanced_libretro.dll',
         'genesis': 'out/blastem_libretro.dll', 'sms': 'out/blastem_libretro.dll'}
CORE_ROOT = HERE.parent.parent / 'trace-win'
TARGETS = 10


# The pinned tracing engines (romancer/trace_core_pins.py), where a pack of them is unpacked beside the repository.
PINNED = {'gb': 'gambatte_trace_libretro', 'gbc': 'gambatte_trace_libretro', 'nes': 'fceumm_trace_libretro',
          'snes': 'bsnes_mercury_balanced_trace_libretro', 'genesis': 'blastem_trace_libretro',
          'sms': 'blastem_trace_libretro'}
PACK_ROOT = HERE.parent.parent / 'trace-packs'


def core_for(system):
    """The pinned engine when its pack is there (so that results are from the engines that ship), else a local build."""
    import os
    folder, suffix = ('windows-amd64', '.dll') if os.name == 'nt' else ('linux-x86_64', '.so')
    pinned = PACK_ROOT / folder / (PINNED[system] + suffix)
    if pinned.exists():
        return str(pinned)
    return str(CORE_ROOT / CORES[system])


# ---- dump -------------------------------------------------------------------

def informative(tile):
    """The tile has enough bytes other than 00 and FF, and enough different ones, to tell a codec's output from chance."""
    stored = tile.stored
    return len(set(stored)) >= 6 and 3 * sum(b not in (0x00, 0xFF) for b in stored) >= len(stored)


def pick_targets(gt, scene, system, rom):
    """Tiles to recognise a packed block from: the sweep's own kind of target (a tile the game
    computes) and tiles whose bytes are literals of a packed stream, spread over the ROM.

    A byte-oriented packer copies literals straight from the stream, so the tracer names a ROM
    byte for every byte of such a tile ("rom", layout "scattered") and the sweep edits the
    literals where they are. That changes every other place the stream copies them to; a
    block that is recognised can be re-packed instead, which is what is measured here.
    """
    all_tiles = gt.tiles(scene, system, rom)
    used = gt.used_tile_addresses(scene, system)
    live = [t for t in all_tiles if not t.blank]
    shown = [t for t in live if t.addresses[0] in used]
    uses = {}
    for layer in gt.layers(scene, system):
        for c in layer.cells:
            uses[c.tile_address] = uses.get(c.tile_address, 0) + 1
    shown.sort(key=lambda t: -uses.get(t.addresses[0], 0))
    ordered = shown + [t for t in live if t.addresses[0] not in used]
    ordered = [t for t in ordered if t.domain != 'chr_rom' and t.addresses[-1] - t.addresses[0] + 1 == len(t.addresses)]
    hard = [t for t in ordered if t.status == 'derived']
    # Tiles that hold a picture first: a tile of two flat colors is all 00 and FF bytes, whose tags
    # say little, and it is as often cleared by code as unpacked. (The sorts are stable: on screen and
    # most used still lead within each class.)
    computed = [t for t in hard if informative(t)]
    literal = [t for t in ordered if t.status == 'rom' and t.layout == 'scattered' and informative(t)
               and t.addresses[0] in used]
    mixed = [t for pair in zip(computed, literal) for t in pair]
    n = min(len(computed), len(literal))
    hard = mixed + computed[n:] + literal[n:] + [t for t in hard if not informative(t)]
    out, seen = [], set()
    for t in hard:
        offs = [s['offset'] for s in t.sources if s]
        key = (min(offs) >> 9) if offs else None
        if out and key in seen:
            continue
        seen.add(key)
        out.append({'domain': t.domain, 'start': t.addresses[0], 'length': len(t.addresses), 'index': t.index,
                    'on_screen': t.addresses[0] in used, 'format': t.format, 'status': t.status})
        if len(out) >= TARGETS:
            break
    return out, {'derived_on_screen': sum(t.status == 'derived' for t in shown), 'derived': sum(t.status == 'derived' for t in live),
                 'literal_on_screen': len(literal)}


def dump_one(sha, index, dumpdir, frames):
    import trace_probe as tp
    import graphics_sweep as gs
    from romancer import graphics_trace as gt
    entry = index[sha]
    system = entry['system_id']
    out = Path(dumpdir) / f'{sha}.pkl'
    rec = {'sha256': sha, 'system': system, 'member': entry['member']}
    work = Path(tempfile.mkdtemp(prefix='cs'))
    try:
        rom, suf = tp.read_rom(entry['zip'] + '!' + entry['member'])
        scenes, fe_for = gs.trace(core_for(system), rom, suf, system, frames, work)
        scene = scenes[-1]
        targets, counts = pick_targets(gt, scene, system, rom)
        rec.update(frame=scene.frame, screen=scene.screen_sha256, video=getattr(scene, 'video', None), targets=targets,
                   counts=counts, ok=True)
        rec['domains'] = {name: (zlib.compress(bytes(d.data)) if d.data is not None else None,
                                 zlib.compress(d.tags.tobytes()), zlib.compress(d.pcs.tobytes()))
                          for name, d in scene.snapshot.domains.items()}
    except Exception as e:
        rec.update(ok=False, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-1500:])
    out.write_bytes(pickle.dumps(rec))
    import shutil
    shutil.rmtree(work, ignore_errors=True)


def load_dump(path):
    """(record, Scene) from a dump; the scene has no checkpoints (offline use only)."""
    from romancer import provenance as pv
    rec = pickle.loads(Path(path).read_bytes())
    if not rec.get('ok'):
        return rec, None
    doms = {}
    for name, (data, tags, pcs) in rec['domains'].items():
        t = array('I'); t.frombytes(zlib.decompress(tags))
        p = array('I'); p.frombytes(zlib.decompress(pcs))
        doms[name] = pv.DomainSnapshot(name, zlib.decompress(data) if data is not None else None, t, p)
    scene = pv.Scene(rec['sha256'][:12], rec['frame'], rec['screen'], [], pv.Snapshot(rec['frame'], doms, rec['screen']))
    scene.video = rec.get('video')
    return rec, scene


def read_rom(index, sha):
    import trace_probe as tp
    e = index[sha]
    return tp.read_rom(e['zip'] + '!' + e['member'])


def _spawn(args, timeout):
    try:
        return subprocess.run([sys.executable, '-B', str(Path(__file__).resolve())] + args, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        return 'timeout'


def cmd_dump(a):
    index = json.loads(Path(a.index).read_text())
    Path(a.dumpdir).mkdir(parents=True, exist_ok=True)
    todo = []
    for p in sorted(Path(a.sweepdir).glob('*.json')):
        try:
            r = json.loads(p.read_text())
        except ValueError:
            continue
        if not r.get('ok') or 'tile' not in r.get('derived_edit', {}):
            continue
        if a.system and r['system'] not in a.system:
            continue
        if not a.all and r['derived_edit'].get('as_planned') and r['derived_edit'].get('path') in ('reencode', 'relocate'):
            continue
        if r['sha256'] in index and not (Path(a.dumpdir) / f"{r['sha256']}.pkl").exists():
            todo.append(r['sha256'])
    from concurrent.futures import ThreadPoolExecutor

    def run(sha):
        code = _spawn(['dump1', a.index, a.dumpdir, sha, '--frames', str(a.frames)], a.timeout)
        return sha, code
    done = 0
    with ThreadPoolExecutor(a.jobs) as pool:
        for sha, code in pool.map(run, todo):
            done += 1
            print(f'{done}/{len(todo)} {sha[:12]} {code}', flush=True)


# ---- match ------------------------------------------------------------------

def repick(gt, rec, scene, rom):
    """Choose the dump's targets again, as verify will choose them in the live scene (dumps made
    before the order of pick_targets changed are then read the new way)."""
    try:
        rec['targets'] = pick_targets(gt, scene, rec['system'], rom)[0]
    except Exception:
        pass        # a dump without the video registers: keep the targets it was made with


def match_one(path, index, codecs=None, limit=TARGETS):
    from romancer import graphics_trace as gt
    rec, scene = load_dump(path)
    if scene is None:
        return rec, []
    rom, _ = read_rom(index, rec['sha256'])
    hits = []
    repick(gt, rec, scene, rom)
    for t in rec['targets'][:limit]:
        try:
            block = gt.find_compressed_block(scene, rom, rec['system'], t['domain'], t['start'], t['length'], codecs)
        except Exception as e:  # a codec bug must not hide the others
            hits.append({'error': f'{type(e).__name__}: {e}'})
            continue
        hits.append(block.to_dict() if block else None)
    return rec, hits


def _match_worker(args):
    path, index_path, codecs, limit = args
    index = _INDEX.get(index_path)
    if index is None:
        index = _INDEX[index_path] = json.loads(Path(index_path).read_text())
    try:
        rec, hits = match_one(path, index, codecs, limit)
    except Exception as e:
        return {'sha256': Path(path).stem, 'error': f'{type(e).__name__}: {e}'}
    return {'sha256': rec['sha256'], 'system': rec['system'], 'member': rec['member'], 'hits': hits}


_INDEX = {}


def cmd_match(a):
    from concurrent.futures import ProcessPoolExecutor
    paths = sorted(Path(a.dumpdir).glob('*.pkl'))
    if a.system:
        index = json.loads(Path(a.index).read_text())
        paths = [p for p in paths if index.get(p.stem, {}).get('system_id') in a.system]
    if a.only:
        paths = [p for p in paths if any(p.stem.startswith(x) for x in a.only.split(','))]
    jobs = [(str(p), a.index, a.codec, a.targets) for p in paths]
    rows = []
    with ProcessPoolExecutor(a.jobs) as pool:
        for row in pool.map(_match_worker, jobs, chunksize=2):
            rows.append(row)
    summary = defaultdict(Counter)
    for r in rows:
        if 'hits' not in r:
            continue
        first = r['hits'][0] if r['hits'] else None
        any_hit = next((h for h in r['hits'] if h and 'codec' in h), None)
        summary[r['system']]['roms'] += 1
        summary[r['system']]['first:' + (first['codec'] if first and 'codec' in first else 'none')] += 1
        summary[r['system']]['any:' + (any_hit['codec'] if any_hit else 'none')] += 1
        if a.verbose and any_hit:
            print(r['system'], r['sha256'][:12], any_hit['codec'], any_hit.get('transform'), r['member'].split('!')[-1][:60])
    for s in sorted(summary):
        print(s, dict(sorted(summary[s].items())))
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=1))


# ---- search -----------------------------------------------------------------

def _search_worker(args):
    path, index_path, targets = args
    from romancer import graphics_trace as gt, gfx_codecs
    index = _INDEX.get(index_path)
    if index is None:
        index = _INDEX[index_path] = json.loads(Path(index_path).read_text())
    rec, scene = load_dump(path)
    rom, _ = read_rom(index, rec['sha256'])
    skip = gt.rom_skip(rom, rec['system'])
    repick(gt, rec, scene, rom)
    rows = []
    for k in targets:
        if k >= len(rec['targets']):
            break
        t = rec['targets'][k]
        t0 = time.perf_counter()
        try:
            hit = gfx_codecs.search_families(scene.snapshot.domains[t['domain']], rom, skip, rec['system'], t['start'], t['length'])
        except Exception as e:
            hit = {'error': f'{type(e).__name__}: {e}'}
        if hit:
            hit.pop('decoded', None)
        rows.append({'sha256': rec['sha256'], 'system': rec['system'], 'name': rec['member'].split('!')[-1], 'target': k,
                     'hit': hit, 'seconds': round(time.perf_counter() - t0, 1)})
    return rows


def cmd_search(a):
    from concurrent.futures import ProcessPoolExecutor
    matches = {r['sha256']: r for r in json.loads(Path(a.matches).read_text()) if 'hits' in r}
    jobs = []
    for p in sorted(Path(a.dumpdir).glob('*.pkl')):
        r = matches.get(p.stem)
        if r is None or (a.system and r['system'] not in a.system):
            continue
        if a.only and not any(p.stem.startswith(x) for x in a.only.split(',')):
            continue
        if any(h and 'codec' in h for h in r['hits']):
            continue
        todo = list(range(min(a.targets, len(r['hits']))))
        if todo:
            jobs.append((str(p), a.index, todo))
    rows = []
    done = 0
    with ProcessPoolExecutor(a.jobs) as pool:
        for part in pool.map(_search_worker, jobs):
            done += 1
            rows += part
            for r in part:
                if r['hit']:
                    print(f"{done}/{len(jobs)}", r['system'], r['sha256'][:12], r['target'], r['hit'].get('codec') or r['hit'], r['name'][:50], flush=True)
            if a.out:
                Path(a.out).write_text(json.dumps(rows, indent=1))
    found = Counter((r['system'], r['hit']['codec']) for r in rows if r['hit'] and 'codec' in r['hit'])
    for (system, codec), n in found.most_common():
        print(system, codec, n)


# ---- family -----------------------------------------------------------------

def writer_window(rec, scene, rom, skip, target, before=64, after=96):
    """ROM bytes around the instruction that produced the target: the one that wrote the same
    source offsets into work RAM when there is one (the unpacker; video memory is then filled
    by a copy loop or DMA that says little), else the one that wrote video memory."""
    from romancer.provenance import tag_offset, tag_kind
    d = scene.snapshot.domains[target['domain']]
    span = range(target['start'], target['start'] + target['length'])
    offs = {tag_offset(d.tags[i]) for i in span if tag_kind(d.tags[i]) in (1, 3) and d.data[i] not in (0, 0xFF)}
    pcs = Counter()
    via = 'direct'
    for name, w in scene.snapshot.domains.items():
        if name in (target['domain'], 'palette', 'oam', 'dmg_palette', 'hram') or w.data is None or not offs:
            continue
        for i, t in enumerate(w.tags):
            if (t >> 28) & 7 in (1, 3) and (t & 0x0FFFFFFF) in offs and w.pcs[i] != 0xFFFFFFFF and w.data[i] not in (0, 0xFF):
                pcs[w.pcs[i]] += 1
        if pcs:
            via = name
            break
    if not pcs:
        pcs = Counter(d.pcs[i] for i in span if d.pcs[i] != 0xFFFFFFFF)
    if not pcs:
        return None, None, 'dma'
    pc = pcs.most_common(1)[0][0]
    return pc, rom[skip + max(0, pc - before):skip + pc + after], via


def cmd_family(a):
    from romancer import graphics_trace as gt
    index = json.loads(Path(a.index).read_text())
    matched = {}
    if a.matches:
        for r in json.loads(Path(a.matches).read_text()):
            matched[r['sha256']] = any(h and 'codec' in h for h in r.get('hits', []))
    rows = []
    for p in sorted(Path(a.dumpdir).glob('*.pkl')):
        rec, scene = load_dump(p)
        if scene is None or not rec['targets']:
            continue
        if matched.get(rec['sha256']):
            continue
        rom, _ = read_rom(index, rec['sha256'])
        skip = gt.rom_skip(rom, rec['system'])
        pc, win, via = writer_window(rec, scene, rom, skip, rec['targets'][0])
        rows.append({'sha256': rec['sha256'], 'system': rec['system'], 'name': rec['member'].split('!')[-1], 'pc': pc,
                     'via': via, 'grams': {win[i:i + a.gram] for i in range(len(win) - a.gram + 1)} if win else set()})
    # union-find: same system and enough shared byte runs
    parent = list(range(len(rows)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    by_gram = defaultdict(list)
    for i, r in enumerate(rows):
        for g in r['grams']:
            if len(set(g)) > 3:
                by_gram[(r['system'] in ('gb', 'gbc') and 'gb' or r['system'], g)].append(i)
    share = Counter()
    for members in by_gram.values():
        if len(members) > 60:
            continue    # boilerplate every game has
        for x in members[1:]:
            share[(members[0], x)] += 1
    for (x, y), n in share.items():
        if n >= a.share:
            parent[find(x)] = find(y)
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[find(i)].append(r)
    table = []
    for members in sorted(groups.values(), key=lambda m: -len(m)):
        table.append({'system': members[0]['system'], 'roms': len(members), 'no_writer': members[0]['pc'] is None,
                      'via': Counter(m['via'] for m in members).most_common(1)[0][0],
                      'examples': [m['name'][:60] for m in members[:6]],
                      'members': [(m['sha256'][:12], m['pc']) for m in members]})
    for row in table[:a.top]:
        print(row['system'], row['roms'], row['via'], '|', '; '.join(row['examples'][:4]))
    solo = Counter(row['system'] for row in table if row['roms'] == 1)
    print('families of one:', dict(solo))
    if a.out:
        Path(a.out).write_text(json.dumps(table, indent=1))


# ---- verify -----------------------------------------------------------------

def verify_one(sha, index, dumpdir, outdir, frames, codecs=None):
    import trace_probe as tp
    import graphics_sweep as gs
    from romancer import graphics_trace as gt, provenance as pv, gfx_codecs
    entry = index[sha]
    system = entry['system_id']
    out = Path(outdir) / f'{sha}.json'
    result = {'sha256': sha, 'system': system, 'member': entry['member'], 'frames': frames}
    t0 = time.perf_counter()
    work = Path(tempfile.mkdtemp(prefix='cv'))
    try:
        dump = Path(dumpdir) / f'{sha}.pkl'
        rec = pickle.loads(dump.read_bytes()) if dump.exists() else {}
        rom, suf = tp.read_rom(entry['zip'] + '!' + entry['member'])
        scenes, fe_for = gs.trace(core_for(system), rom, suf, system, frames, work)
        result['same_scene'] = scenes[-1].screen_sha256 == rec.get('screen')
        tries = []
        # The last scene first (the one the sweep measured), then the earlier ones: what a game has
        # unpacked differs from screen to screen, and one confirmed block is what is asked.
        for scene in reversed(scenes):
            before = [c for c in scene.checkpoints if c[0] < scene.frame] or scene.checkpoints[:1]
            quick = pv.Scene(scene.id, scene.frame, scene.screen_sha256,
                             sorted({c[0]: c for c in scene.checkpoints[:1] + before[-2:]}.values()), scene.snapshot)
            quick.video = getattr(scene, 'video', None)

            def verify(plan, expect=None, quick=quick):
                return gt.verify_plan(fe_for, rom, plan, quick, expect=expect, buttons_for=gs.explore)
            targets, _ = pick_targets(gt, scene, system, rom)
            for t in targets[:a_targets(system)]:
                tile = gt.tile_at(scene, system, t['start'], domain=t['domain'])
                block = gt.find_compressed_block(scene, rom, system, t['domain'], t['start'], t['length'], codecs)
                row = {'frame': scene.frame, 'tile': t['index'], 'on_screen': t['on_screen'], 'status': t.get('status'),
                       'codec': block.codec if block else None}
                tries.append(row)
                if block is None:
                    continue
                row['block'] = block.to_dict()
                new = gt.encode_tile(gs.redraw(tile), tile.format)
                changes = {}
                layout = gfx_codecs.CODECS[block.codec].get('map')
                for k, addr in enumerate(tile.addresses):
                    if new[k] != tile.stored[k]:
                        try:
                            at = block.decoded_index(addr)
                        except ValueError:
                            continue     # a byte the game makes up itself (3bpp padding)
                        if layout and gfx_codecs.map_index(layout, at) is None:
                            continue     # the same, for a layout carried by the codec name
                        changes[addr] = new[k]
                if not changes:
                    row['error'] = 'nothing to change'
                    continue
                try:
                    plan = gt.plan_block_edit(block, changes, rom, system, verify=verify,
                                              max_candidates=24 if gt.CPU[system] in ('sm83', '6502') else 6)
                    r = verify(plan)
                    # Other bytes that changed: inside the stretch of video memory the block was loaded to (the
                    # re-packed stream did not unpack to the edited block: a fault) or elsewhere (the same data
                    # loaded a second time, or a picture that moves and was caught a frame apart).
                    span = range(block.domain_start, block.domain_start + block.last - block.first)
                    inside = sum(i in span and i not in changes for i in r.get('changed', {}).get(block.domain, ()))
                    row.update(path=plan.kind, verified=r['verified'], as_planned=r.get('as_planned'),
                               missed={k: len(v) for k, v in r.get('missed', {}).items()}, unplanned=r.get('unplanned', {}),
                               unplanned_in_block=inside,
                               reads_on_alike=(plan.kind != 'reencode' or gfx_codecs.CODECS[block.codec]['terminated']
                                               or gfx_codecs.reads_on_alike(block.codec, rom, plan.apply(rom), block.start,
                                                                            len(block.decoded))),
                               old_stream=plan.details.get('old_stream'), new_stream=plan.details.get('new_stream'))
                except ValueError as e:
                    row['error'] = str(e)[:300]
                if row.get('as_planned') and sound(row):
                    break
            if any(r.get('as_planned') and sound(r) for r in tries):
                break
        result['tries'] = tries
        good = (next((r for r in tries if r.get('as_planned') and sound(r)), None)
                or next((r for r in tries if r.get('as_planned')), None))
        result['clean'] = bool(good and sound(good))
        result['confirmed'] = bool(good)
        result['codec'] = good['codec'] if good else next((r['codec'] for r in tries if r['codec']), None)
        result['path'] = good['path'] if good else None
        result['transform'] = good['block']['transform'] if good else None
        result['ok'] = True
    except Exception as e:
        result.update(ok=False, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-1500:])
    result['seconds'] = round(time.perf_counter() - t0, 1)
    out.write_text(json.dumps(result, indent=1))
    import shutil
    shutil.rmtree(work, ignore_errors=True)


def sound(row):
    """A replayed edit left the rest of its block alone, and what follows a bare stream still unpacks as before."""
    return not row.get('unplanned_in_block') and row.get('reads_on_alike', True)


def a_targets(system):
    return 6


def cmd_verify(a):
    index = json.loads(Path(a.index).read_text())
    Path(a.outdir).mkdir(parents=True, exist_ok=True)
    hints = {}
    if a.matches:
        # the codecs that explained a tile of the dumped scene: only those are tried (far quicker)
        for r in json.loads(Path(a.matches).read_text()):
            names = sorted({h['codec'] for h in r.get('hits', []) if h and 'codec' in h})
            if names:
                hints[r['sha256']] = names
    if a.list:
        shas = [line.split()[0] for line in Path(a.list).read_text().splitlines() if line.strip()]
    elif a.matches:
        shas = [r['sha256'] for r in json.loads(Path(a.matches).read_text())
                if any(h and 'codec' in h for h in r.get('hits', []))]
    else:
        shas = [p.stem for p in sorted(Path(a.dumpdir).glob('*.pkl'))]
    if a.system:
        shas = [s for s in shas if index[s]['system_id'] in a.system]
    if a.only:
        shas = [s for s in shas if any(s.startswith(x) for x in a.only.split(','))]
    shas = [s for s in shas if a.redo or not (Path(a.outdir) / f'{s}.json').exists()]
    from concurrent.futures import ThreadPoolExecutor

    def run(sha):
        more = [x for name in hints.get(sha, a.codec or ()) for x in ('--codec', name)]
        code = _spawn(['verify1', a.index, a.dumpdir, a.outdir, sha, '--frames', str(a.frames)] + more, a.timeout)
        out = Path(a.outdir) / f'{sha}.json'
        if not out.exists():
            out.write_text(json.dumps({'sha256': sha, 'system': index[sha]['system_id'], 'member': index[sha]['member'],
                                       'ok': False, 'error': f'no result ({code})'}, indent=1))
        return sha, code
    done = 0
    with ThreadPoolExecutor(a.jobs) as pool:
        for sha, code in pool.map(run, shas):
            done += 1
            print(f'{done}/{len(shas)} {sha[:12]} {code}', flush=True)


def cmd_report(a):
    """Per system: ROMs whose packed graphics were re-packed (or moved) and replayed as planned.

    before  the sweep's own result or an earlier verify run (--also DIR, repeatable)
    after   before, or a result in OUTDIR that is confirmed and sound (see `sound`)
    """
    keep = None
    if a.catalog:
        keep = {r['sha256'] for r in json.loads(Path(a.catalog).read_text(encoding='utf-8'))['records']}

    def load(folder):
        out = []
        for p in Path(folder).glob('*.json'):
            try:
                r = json.loads(p.read_text())
            except ValueError:
                continue
            if keep is None or r.get('sha256') in keep:
                out.append(r)
        return out
    rows = load(a.outdir)
    system_of, before = {}, set()
    if a.sweepdir:
        for r in load(a.sweepdir):
            if r.get('ok'):
                system_of[r['sha256']] = r['system']
                de = r.get('derived_edit', {})
                if de.get('as_planned') and de.get('path') in ('reencode', 'relocate'):
                    before.add(r['sha256'])
    for folder in a.also or ():
        for r in load(folder):
            system_of.setdefault(r['sha256'], r['system'])
            if r.get('confirmed'):
                before.add(r['sha256'])
    for r in rows:
        system_of.setdefault(r['sha256'], r['system'])
    out = {}
    for system in sorted(set(system_of.values())):
        rs = [r for r in rows if r['system'] == system]
        good = {r['sha256'] for r in rs if r.get('confirmed') and r.get('clean', True)}
        was = {sha for sha in before if system_of[sha] == system}
        new = good - was
        s = {'roms': sum(v == system for v in system_of.values()), 'verified_here': len(rs),
             'errors': sum(not r.get('ok') for r in rs), 'confirmed_before': len(was), 'confirmed_after': len(was | good),
             'new_here': len(new),
             'new_by_codec': dict(Counter(r['codec'] for r in rs if r['sha256'] in new).most_common()),
             'new_by_path': dict(Counter(r['path'] for r in rs if r['sha256'] in new)),
             'confirmed_here_not_sound': sum(bool(r.get('confirmed')) and not r.get('clean', True) for r in rs)}
        s['matched_unconfirmed'] = dict(Counter(r.get('codec') or 'none' for r in rs
                                                if r.get('ok') and not r.get('confirmed') and r['sha256'] not in was).most_common())
        why = Counter()
        for r in rs:
            if r.get('ok') and not r.get('confirmed'):
                for t in r.get('tries', []):
                    if t.get('codec'):
                        why[(t.get('error') or ('replayed, not as planned' if 'as_planned' in t else 'no plan'))[:70]] += 1
        s['unconfirmed_reasons'] = dict(why.most_common(6))
        out[system] = s
    total = {k: sum(s[k] for s in out.values()) for k in ('roms', 'verified_here', 'confirmed_before', 'confirmed_after', 'new_here')}
    out['all'] = total
    print(json.dumps(out, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8', newline='\n')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('dump'); p.add_argument('index'); p.add_argument('sweepdir'); p.add_argument('dumpdir')
    p.add_argument('--system', action='append'); p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--frames', type=int, default=1800); p.add_argument('--timeout', type=int, default=600)
    p.add_argument('--all', action='store_true', help='also ROMs whose codec path is already confirmed')
    p = sub.add_parser('dump1'); p.add_argument('index'); p.add_argument('dumpdir'); p.add_argument('sha')
    p.add_argument('--frames', type=int, default=1800)
    p = sub.add_parser('match'); p.add_argument('index'); p.add_argument('dumpdir')
    p.add_argument('--system', action='append'); p.add_argument('--codec', action='append'); p.add_argument('--out')
    p.add_argument('--jobs', type=int, default=3); p.add_argument('--targets', type=int, default=3)
    p.add_argument('--only'); p.add_argument('--verbose', action='store_true')
    p = sub.add_parser('search'); p.add_argument('index'); p.add_argument('dumpdir'); p.add_argument('matches')
    p.add_argument('--system', action='append'); p.add_argument('--out'); p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--targets', type=int, default=1); p.add_argument('--only')
    p = sub.add_parser('family'); p.add_argument('index'); p.add_argument('dumpdir'); p.add_argument('--out')
    p.add_argument('--matches', help='match --out file: ROMs matched there are left out')
    p.add_argument('--gram', type=int, default=8); p.add_argument('--share', type=int, default=24)
    p.add_argument('--top', type=int, default=40)
    p = sub.add_parser('verify'); p.add_argument('index'); p.add_argument('dumpdir'); p.add_argument('outdir')
    p.add_argument('--system', action='append'); p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--frames', type=int, default=1800); p.add_argument('--timeout', type=int, default=900)
    p.add_argument('--only'); p.add_argument('--matches'); p.add_argument('--redo', action='store_true')
    p.add_argument('--list', help='file of SHA-256s, one per line: verify these (a dump is not needed)')
    p.add_argument('--codec', action='append', help='codecs to try on ROMs that --matches gives no codec for')
    p = sub.add_parser('verify1'); p.add_argument('index'); p.add_argument('dumpdir'); p.add_argument('outdir'); p.add_argument('sha')
    p.add_argument('--frames', type=int, default=1800); p.add_argument('--codec', action='append')
    p = sub.add_parser('report'); p.add_argument('outdir'); p.add_argument('sweepdir', nargs='?')
    p.add_argument('--also', action='append', help='an earlier verify OUTDIR whose confirmations count as before')
    p.add_argument('--catalog', help='rom_samples.json: count only the ROMs in this catalog'); p.add_argument('--json')
    a = ap.parse_args()
    if a.cmd == 'dump':
        cmd_dump(a)
    elif a.cmd == 'dump1':
        dump_one(a.sha, json.loads(Path(a.index).read_text()), a.dumpdir, a.frames)
    elif a.cmd == 'match':
        cmd_match(a)
    elif a.cmd == 'search':
        cmd_search(a)
    elif a.cmd == 'family':
        cmd_family(a)
    elif a.cmd == 'verify':
        cmd_verify(a)
    elif a.cmd == 'verify1':
        verify_one(a.sha, json.loads(Path(a.index).read_text()), a.dumpdir, a.outdir, a.frames, a.codec)
    elif a.cmd == 'report':
        cmd_report(a)


if __name__ == '__main__':
    main()
