"""Run trace/png_roundtrip.py over every ROM of a finished sweep folder (one JSON per ROM, named by SHA-256).

    python -B trace/png_sweep.py <corpus index.json> <folder with <sha>.json names> <out folder> [--jobs 7] [--report]

A ROM that already has a result is not run again, so the sweep can be stopped and started. --report only prints the totals.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMIT = 1500


def run(index: Path, sha: str, out: Path) -> str:
    target = out / f'{sha}.json'
    if target.exists():
        return 'kept'
    log = (out / f'{sha}.log').open('w')
    process = subprocess.Popen([sys.executable, '-B', str(HERE / 'png_roundtrip.py'), str(index), sha, str(target), '--steps', '8'],
                               stdout=log, stderr=subprocess.STDOUT)
    try:
        process.wait(LIMIT)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True)
        target.write_text(json.dumps({'sha256': sha, 'error': f'not finished in {LIMIT} seconds'}))
        return 'timeout'
    finally:
        log.close()
    if not target.exists():
        target.write_text(json.dumps({'sha256': sha, 'error': 'the measurement stopped without a result (see the log)'}))
        return 'failed'
    (out / f'{sha}.log').unlink(missing_ok=True)
    return 'done'


def report(out: Path, names: list) -> dict:
    rows = [json.loads((out / f'{sha}.json').read_text()) for sha in names if (out / f'{sha}.json').exists()]
    ran = [r for r in rows if not r.get('error')]
    tried = [r for r in ran if 'drawn' in r.get('import', {})]
    confirmed = [r for r in tried if r['import'].get('confirmed')]
    total = {
        'roms': len(names), 'measured': len(rows), 'recorded': len(ran),
        'sheet_saved': sum(1 for r in ran if r.get('sheet')),
        'sheet_palette_png': sum(1 for r in ran if r.get('sheet', {}).get('indexed')),
        'sheet_reads_back_same': sum(1 for r in ran if r.get('sheet', {}).get('same_when_read_back') and r['sheet'].get('same_as_plain_rgb')),
        'layer_saved': sum(1 for r in ran if any('width' in l for l in r.get('layers', []))),
        'layers_read_back_same': sum(1 for r in ran if r.get('layers') and all(l.get('same_when_read_back') for l in r['layers'] if 'width' in l)
                                     and any('width' in l for l in r['layers'])),
        'import_tried': len(tried),
        'import_confirmed_some': len(confirmed),
        'import_confirmed_all_drawn': sum(1 for r in tried if r['import'].get('confirmed') and r['import']['confirmed'] >= r['import']['read_as_changed']),
        'import_good_from_power_on': sum(1 for r in confirmed if any(c[0] == 'From power-on' and c[1] in ('good', 'warn') for c in r['import'].get('checks', []))),
        'pictures_drawn': sum(r['import']['read_as_changed'] for r in tried),
        'pictures_confirmed': sum(r['import'].get('confirmed') or 0 for r in tried),
        'layer_import_tried': sum(1 for r in ran if 'layer_import' in r),
        'layer_import_confirmed': sum(1 for r in ran if (r.get('layer_import') or {}).get('confirmed')),
        'no_picture_to_draw_on': sum(1 for r in ran if r.get('import', {}).get('skipped_test')),
        'errors': sum(1 for r in rows if r.get('error')),
    }
    return total


NL = chr(10)
HEAD = '## PNG out and back in'
SYSTEMS = [('nes', 'NES'), ('snes', 'Super NES'), ('genesis', 'Mega Drive'), ('sms', 'Master System'), ('gb', 'Game Boy'), ('gbc', 'Game Boy Color')]


def markdown(out: Path, names: list) -> str:
    rows = [json.loads((out / f'{sha}.json').read_text()) for sha in names if (out / f'{sha}.json').exists()]
    t = report(out, names)
    ran = [r for r in rows if not r.get('error')]
    tried = [r for r in ran if 'drawn' in r.get('import', {})]
    lines = [HEAD, '',
             f'Measured with `trace/png_sweep.py` on {t["measured"]} of the {t["roms"]} catalog ROMs. For each ROM, scenes were recorded, '
             'the scene with the most pictures on screen was saved as PNG (the pictures and every background layer), each PNG was read '
             'straight back, then up to 6 pictures on screen were drawn on in the pictures PNG and it was loaded. A picture counts as '
             'confirmed only when a replay of the real game shows it as drawn.', '',
             '| What | ROMs |', '|---|---|',
             f'| Scenes recorded | {t["recorded"]} of {t["measured"]} |',
             f'| Pictures saved as PNG | {t["sheet_saved"]} |',
             f'| ... as a palette PNG with the colors of the scene | {t["sheet_palette_png"]} |',
             f'| ... read straight back with nothing reported as changed (as saved, and converted to plain RGB) | {t["sheet_reads_back_same"]} |',
             f'| At least one background layer saved as PNG | {t["layer_saved"]} |',
             f'| ... every saved layer read straight back unchanged | {t["layers_read_back_same"]} |',
             f'| Loaded an edited pictures PNG | {t["import_tried"]} |',
             f'| ... at least one drawn picture confirmed by replay | {t["import_confirmed_some"]} |',
             f'| ... every drawn picture confirmed | {t["import_confirmed_all_drawn"]} |',
             f'| ... and the change also holds when the game is played from power-on | {t["import_good_from_power_on"]} |',
             f'| Loaded an edited background PNG | {t["layer_import_tried"]} |',
             f'| ... at least one drawn picture confirmed | {t["layer_import_confirmed"]} |', '',
             f'Pictures drawn on across all ROMs: {t["pictures_drawn"]:,}; confirmed: {t["pictures_confirmed"]:,}.', '',
             '| System | Loaded | Some confirmed | All confirmed |', '|---|---|---|---|']
    for key, label in SYSTEMS:
        mine = [r for r in tried if r['system'] == key]
        lines.append(f'| {label} | {len(mine)} | {sum(1 for r in mine if r["import"].get("confirmed"))} | '
                     f'{sum(1 for r in mine if r["import"].get("confirmed") and r["import"]["confirmed"] >= r["import"]["read_as_changed"])} |')
    ways: dict = {}
    for r in tried:
        for way, count in (r['import'].get('ways') or {}).items():
            ways[way] = ways.get(way, 0) + count
    label = {'direct': 'written in place', 'direct-packed': 'written in place inside packed data', 'reencode': 'packed again',
             'relocate': 'packed again and moved', 'overlay': 'swapped in by a patch'}
    lines += ['', 'How the confirmed pictures were changed: ' + ', '.join(f'{label.get(w, w)} {n:,}' for w, n in sorted(ways.items(), key=lambda i: -i[1])) + '.', '']
    none = [r for r in tried if not r['import'].get('confirmed')]
    if none:
        lines += [f'### No drawn picture confirmed: {len(none)}', '', '| ROM | System | Why |', '|---|---|---|']
        for r in sorted(none, key=lambda r: (r['system'], r['name'])):
            why = r['import'].get('error') or '; '.join(dict.fromkeys(r['import'].get('skipped', []))) or 'not confirmed'
            why = why.replace('None of the pictures you changed could be changed in a way the real game confirmed, so nothing is changed. ', '')
            lines.append(f'| {r["name"].rsplit(".", 1)[0]} | {r["system"]} | {why[:220].replace("|", "/")} |')
        lines.append('')
    failed = [r for r in rows if r.get('error')]
    if failed:
        lines += [f'### Not measured: {len(failed)}', '', '| ROM | Why |', '|---|---|']
        for r in failed:
            lines.append(f'| {r.get("name", r["sha256"][:16]).rsplit(".", 1)[0]} | {str(r["error"])[:200].replace("|", "/")} |')
        lines.append('')
    return NL.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('names', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--jobs', type=int, default=7)
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--markdown', type=Path, help='COVERAGE.md to put the PNG section in (replaces an earlier one)')
    args = parser.parse_args()
    names = sorted(p.stem for p in args.names.glob('*.json') if len(p.stem) == 64)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.markdown:
        page = args.markdown.read_text(encoding='utf-8')
        if HEAD in page:
            page = page[:page.index(HEAD)]
        args.markdown.write_text(page.rstrip() + NL + NL + markdown(args.out, names).rstrip() + NL, encoding='utf-8', newline=NL)
        print(json.dumps(report(args.out, names), indent=1))
        return
    if not args.report:
        started, done = time.time(), [0]

        def one(sha):
            state = run(args.index.resolve(), sha, args.out.resolve())
            done[0] += 1
            print(f'[{done[0]}/{len(names)}] {sha[:12]} {state} ({time.time() - started:.0f}s)', flush=True)
        with ThreadPoolExecutor(args.jobs) as pool:
            list(pool.map(one, names))
    print(json.dumps(report(args.out, names), indent=1))


if __name__ == '__main__':
    main()
