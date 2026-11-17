"""Trace every ROM in the corpus and record palette/graphics coverage.

    python -B trace/coverage_sweep.py INDEX.json OUTDIR --system gbc --core PATH [--jobs N] [--frames F]

For each ROM: boot with the default input script, take a scene at the end,
and record, per domain, how many bytes trace to ROM data, code values,
derived (computed/compressed) sources or nothing. One causal replay per ROM
confirms that a sampled palette source really drives the screen.
Results are one JSON per ROM, so the sweep can be resumed.
"""
import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))


STEP = 900


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


def one(sha, entry, core, system, frames, outdir):
    import trace_probe as tp
    from romancer import provenance as pv, palette_trace as pt
    out = Path(outdir) / f'{sha}.json'
    if out.exists():
        return sha, 'cached'
    t0 = time.perf_counter()
    result = {'sha256': sha, 'system': system, 'member': entry['member'], 'core': Path(core).name, 'frames': frames}
    try:
        rom, suf = tp.read_rom(entry['zip'] + '!' + entry['member'])
        work = Path(tempfile.mkdtemp(prefix='rt'))

        def fe_for(data):
            p = work / f'g{abs(hash(data)) % 999999}{suf}'
            p.write_bytes(data)
            fe = tp.LibretroFrontend(core, save_dir=work / 'rt')
            fe.load_game(p)
            return fe

        s = pv.TraceSession(fe_for(rom), checkpoint_every=300)
        s.start()
        scenes = []
        for _ in range(frames // STEP):
            s.run(STEP, explore)
            scenes.append(pv.scene_from_session(s))
        s.fe.close()
        scene = scenes[-1]
        # Union of ROM sources seen across all snapshots, per domain and kind.
        seen = {}
        for sc in scenes:
            for name, d in sc.snapshot.domains.items():
                for kind, label in ((pv.RT_ROM, 'rom'), (pv.RT_IMM, 'code'), (pv.RT_DERIVED, 'derived')):
                    seen.setdefault(name, {}).setdefault(label, set()).update(d.sources((kind,)))
        result['sources_union'] = {n: {k: len(v) for k, v in kinds.items()} for n, kinds in seen.items()}
        result['distinct_screens'] = len({sc.screen_sha256 for sc in scenes})
        result['screen_sha256'] = scene.screen_sha256
        result['domains'] = scene.snapshot.kind_counts()
        sw = pt.swatches(scene, system)
        status = {}
        for x in sw:
            status[x.status] = status.get(x.status, 0) + 1
        result['palette_entries'] = status
        live = [x for x in sw if any(x.stored)]  # skip never-used black entries
        result['palette_live'] = {k: sum(1 for x in live if x.status == k) for k in ('rom', 'code', 'derived', 'unknown')}
        target = next((x for x in live if x.editable and not any(s['weak'] for s in x.sources)), None)
        if target:
            new = [[255 - c for c in target.rgb[0]]] * 4 if target.format == 'dmg-shades' else [255 - c for c in target.rgb[0]]
            try:
                writes = pt.plan_color_edit(target, new, rom)
                edited = bytearray(rom)
                for o, _, n in writes:
                    edited[o] = n
                r = pv.verify_edit(fe_for, rom, bytes(edited), scene, buttons_for=explore) if writes else {'verified': False}
                result['causal'] = {'entry': target.entry, 'domain': target.domain, 'writes': len(writes), 'verified': r['verified'],
                                    'changed': {k: len(v) for k, v in r.get('changed', {}).items()}}
            except ValueError as e:
                result['causal'] = {'error': str(e)}
        result['ok'] = True
    except Exception as e:  # recorded, never hidden
        result['ok'] = False
        result['error'] = f'{type(e).__name__}: {e}'
        result['trace'] = traceback.format_exc()[-1500:]
    result['seconds'] = round(time.perf_counter() - t0, 1)
    out.write_text(json.dumps(result, indent=1))
    return sha, 'ok' if result['ok'] else 'error'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('index'); ap.add_argument('outdir')
    ap.add_argument('--system', required=True, action='append')
    ap.add_argument('--core', required=True)
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('--frames', type=int, default=1800)
    ap.add_argument('--only', help='comma-separated sha256 prefixes')
    a = ap.parse_args()
    index = json.loads(Path(a.index).read_text())
    Path(a.outdir).mkdir(parents=True, exist_ok=True)
    todo = [(sha, e) for sha, e in index.items() if e['system_id'] in a.system]
    if a.only:
        todo = [(s, e) for s, e in todo if any(s.startswith(p) for p in a.only.split(','))]
    done = 0
    with ProcessPoolExecutor(a.jobs) as pool:
        futures = [pool.submit(one, sha, e, a.core, e['system_id'], a.frames, a.outdir) for sha, e in todo]
        for f in as_completed(futures):
            sha, state = f.result(); done += 1
            print(f'{done}/{len(todo)} {sha[:12]} {state}', flush=True)


if __name__ == '__main__':
    main()
