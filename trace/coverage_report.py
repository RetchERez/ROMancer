"""Summarize coverage_sweep results per system.

    python -B trace/coverage_report.py SWEEPDIR INDEX.json [--markdown OUT.md]

Palette status per ROM:
  verified  - a traced palette source was edited and the replay changed the screen
  traced    - live palette entries trace to ROM bytes or code values, replay not yet confirmed
  derived   - live colors are computed by the game (fades, lookups); needs source search
  none      - no live palette entries traced
Graphics status per ROM, from VRAM tags:
  direct    - most traced VRAM bytes are plain ROM copies (editable in place)
  derived   - most are computed: compressed or generated (needs a codec or relocation)
  none      - VRAM was not traced
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def classify(r):
    if not r.get('ok'):
        return 'error', 'error'
    live = r.get('palette_live', {})
    if r.get('causal', {}).get('verified'):
        pal = 'verified'
    elif live.get('rom', 0) + live.get('code', 0):
        pal = 'traced'
    elif live.get('derived', 0):
        pal = 'derived'
    else:
        pal = 'none'
    v = r.get('domains', {}).get('vram') or r.get('domains', {}).get('chr') or {}
    direct, derived = v.get('rom', 0) + v.get('code', 0), v.get('derived', 0)
    gfx = 'none' if direct + derived == 0 else 'direct' if direct >= derived else 'derived'
    return pal, gfx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sweep'); ap.add_argument('index'); ap.add_argument('--markdown')
    a = ap.parse_args()
    index = json.loads(Path(a.index).read_text())
    rows = [json.loads(p.read_text()) for p in Path(a.sweep).glob('*.json')]
    per = defaultdict(lambda: {'pal': Counter(), 'gfx': Counter(), 'n': 0})
    errors = []
    for r in rows:
        pal, gfx = classify(r)
        s = per[r['system']]; s['n'] += 1; s['pal'][pal] += 1; s['gfx'][gfx] += 1
        if pal == 'error':
            errors.append((r['system'], r['member'], r.get('error', '')))
    total = Counter(v['system_id'] for v in index.values())
    lines = ['| System | Traced / in corpus | Palette verified | traced | derived | none | errors | Graphics direct | derived | none |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for system in sorted(total):
        s = per.get(system)
        if not s:
            lines.append(f'| {system} | 0 / {total[system]} | | | | | | | | |'); continue
        p, g = s['pal'], s['gfx']
        lines.append(f"| {system} | {s['n']} / {total[system]} | {p['verified']} | {p['traced']} | {p['derived']} | {p['none']} | {p['error']} | {g['direct']} | {g['derived']} | {g['none']} |")
    text = '\n'.join(lines)
    if errors:
        text += '\n\nErrors:\n' + '\n'.join(f'- {s}: {m}: {e}' for s, m, e in sorted(errors)[:40])
    print(text)
    if a.markdown:
        Path(a.markdown).write_text(text + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
