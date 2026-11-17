"""Study the packed graphics the codecs do not recognise yet, and confirm the ones they do.

    python -B trace/codec_survey.py dump   INDEX.json SWEEPDIR DUMPDIR [--system S ...] [--jobs N] [--all]
    python -B trace/codec_survey.py match  INDEX.json DUMPDIR [--system S ...] [--codec NAME ...] [--out FILE]
    python -B trace/codec_survey.py search INDEX.json DUMPDIR MATCHES.json [--system S ...] [--out FILE]
    python -B trace/codec_survey.py family INDEX.json DUMPDIR [--out FILE]
    python -B trace/codec_survey.py verify INDEX.json DUMPDIR OUTDIR [--system S ...] [--jobs N] [--only SHA,...]
    python -B trace/codec_survey.py report OUTDIR [SWEEPDIR]

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
verify  For ROMs that match offline: trace again, plan an edit through the
        codec (plan_block_edit: re-encode in place or relocate) and replay it
        (verify_plan). One JSON per ROM in OUTDIR; the shared sweep results
        are never written.
report  Totals of OUTDIR by system; with SWEEPDIR, the count of ROMs with a
        replay-confirmed codec path before (the sweep) and after (either).
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


def core_for(system):
    return str(CORE_ROOT / CORES[system])


# ---- dump -------------------------------------------------------------------

def pick_targets(gt, scene, system, rom):
    """The sweep's own target first, then other unpacked tiles spread over the ROM."""
    all_tiles = gt.tiles(scene, system, rom)
    used = gt.used_tile_addresses(scene, system)
    live = [t for t in all_tiles if not t.blank]
    shown = [t for t in live if t.addresses[0] in used]
    uses = {}
    for layer in gt.layers(scene, system):
        for c in layer.cells:
            uses[c.tile_address] = uses.get(c.tile_address, 0) + 1
    shown.sort(key=lambda t: -uses.get(t.addresses[0], 0))
    hard = [t for t in shown if t.status == 'derived'] + [t for t in live if t.status == 'derived' and t.addresses[0] not in used]
    hard = [t for t in hard if t.domain != 'chr_rom' and t.addresses[-1] - t.addresses[0] + 1 == len(t.addresses)]
    out, seen = [], set()
    for t in hard:
        offs = [s['offset'] for s in t.sources if s]
        key = (min(offs) >> 9) if offs else None
        if out and key in seen:
            continue
        seen.add(key)
        out.append({'domain': t.domain, 'start': t.addresses[0], 'length': len(t.addresses), 'index': t.index,
                    'on_screen': t.addresses[0] in used, 'format': t.format})
        if len(out) >= TARGETS:
            break
    return out, {'derived_on_screen': sum(t.status == 'derived' for t in shown), 'derived': sum(t.status == 'derived' for t in live)}


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

def match_one(path, index, codecs=None, limit=TARGETS):
    from romancer import graphics_trace as gt
    rec, scene = load_dump(path)
    if scene is None:
        return rec, []
    rom, _ = read_rom(index, rec['sha256'])
    hits = []
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
    rows = []
    for k in targets:
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

def verify_one(sha, index, dumpdir, outdir, frames):
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
        rec = pickle.loads((Path(dumpdir) / f'{sha}.pkl').read_bytes())
        rom, suf = tp.read_rom(entry['zip'] + '!' + entry['member'])
        scenes, fe_for = gs.trace(core_for(system), rom, suf, system, frames, work)
        scene = scenes[-1]
        result['same_scene'] = scene.screen_sha256 == rec.get('screen')
        before = [c for c in scene.checkpoints if c[0] < scene.frame] or scene.checkpoints[:1]
        quick = pv.Scene(scene.id, scene.frame, scene.screen_sha256,
                         sorted({c[0]: c for c in scene.checkpoints[:1] + before[-2:]}.values()), scene.snapshot)
        quick.video = getattr(scene, 'video', None)

        def verify(plan, expect=None):
            return gt.verify_plan(fe_for, rom, plan, quick, expect=expect, buttons_for=gs.explore)
        tries = []
        targets, _ = pick_targets(gt, scene, system, rom)
        for t in targets[:a_targets(system)]:
            tile = gt.tile_at(scene, system, t['start'], domain=t['domain'])
            block = gt.find_compressed_block(scene, rom, system, t['domain'], t['start'], t['length'])
            row = {'tile': t['index'], 'on_screen': t['on_screen'], 'codec': block.codec if block else None}
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
                row.update(path=plan.kind, verified=r['verified'], as_planned=r.get('as_planned'),
                           missed={k: len(v) for k, v in r.get('missed', {}).items()}, unplanned=r.get('unplanned', {}),
                           old_stream=plan.details.get('old_stream'), new_stream=plan.details.get('new_stream'))
            except ValueError as e:
                row['error'] = str(e)[:300]
            if row.get('as_planned'):
                break
        result['tries'] = tries
        good = next((r for r in tries if r.get('as_planned')), None)
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


def a_targets(system):
    return 6


def cmd_verify(a):
    index = json.loads(Path(a.index).read_text())
    Path(a.outdir).mkdir(parents=True, exist_ok=True)
    if a.matches:
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
        code = _spawn(['verify1', a.index, a.dumpdir, a.outdir, sha, '--frames', str(a.frames)], a.timeout)
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
    rows = [json.loads(p.read_text()) for p in Path(a.outdir).glob('*.json')]
    before = {}
    if a.sweepdir:
        for p in Path(a.sweepdir).glob('*.json'):
            try:
                r = json.loads(p.read_text())
            except ValueError:
                continue
            if r.get('ok') and 'tile' in r.get('derived_edit', {}):
                de = r['derived_edit']
                before[r['sha256']] = (r['system'], bool(de.get('as_planned') and de.get('path') in ('reencode', 'relocate')),
                                       de.get('codec'))
    out = {}
    for system in sorted({r['system'] for r in rows} | {v[0] for v in before.values()}):
        rs = [r for r in rows if r['system'] == system]
        good = {r['sha256'] for r in rs if r.get('confirmed')}
        first = {r['sha256'] for r in rs if r.get('tries') and r['tries'][0].get('as_planned')}
        s = {'verified_here': len(rs), 'errors': sum(not r.get('ok') for r in rs), 'confirmed': len(good),
             'confirmed_on_first_target': len(first)}
        s['confirmed_by_codec'] = dict(Counter(r['codec'] for r in rs if r.get('confirmed')).most_common())
        s['confirmed_by_path'] = dict(Counter(r['path'] for r in rs if r.get('confirmed')))
        s['matched_unconfirmed'] = dict(Counter(r.get('codec') or 'none' for r in rs if r.get('ok') and not r.get('confirmed')))
        why = Counter()
        for r in rs:
            if r.get('ok') and not r.get('confirmed'):
                for t in r.get('tries', []):
                    if t.get('codec'):
                        why[(t.get('error') or ('replayed, not as planned' if 'as_planned' in t else 'no plan'))[:70]] += 1
        s['unconfirmed_reasons'] = dict(why.most_common(6))
        if before:
            b = {sha for sha, v in before.items() if v[0] == system}
            was = {sha for sha in b if before[sha][1]}
            s['roms_with_unpacked_tiles'] = len(b)
            s['codec_path_confirmed_before'] = len(was)
            s['codec_path_confirmed_after'] = len(was | good)
            s['confirmed_before_but_not_here'] = len({r['sha256'] for r in rs if r['sha256'] in was} - good)
        out[system] = s
    print(json.dumps(out, indent=1))


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
    p = sub.add_parser('verify1'); p.add_argument('index'); p.add_argument('dumpdir'); p.add_argument('outdir'); p.add_argument('sha')
    p.add_argument('--frames', type=int, default=1800)
    p = sub.add_parser('report'); p.add_argument('outdir'); p.add_argument('sweepdir', nargs='?')
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
        verify_one(a.sha, json.loads(Path(a.index).read_text()), a.dumpdir, a.outdir, a.frames)
    elif a.cmd == 'report':
        cmd_report(a)


if __name__ == '__main__':
    main()
