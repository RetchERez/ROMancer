"""Summarize coverage_sweep results per system.

    python -B trace/coverage_report.py SWEEPDIR INDEX.json [--catalog knowledge/rom_samples.json]
                                       [--markdown OUT.md] [--no-chips]

With --catalog, only ROMs that are in the catalog are reported, under their catalog names,
and the "in catalog" column counts catalog entries.

Palette status per ROM (first that applies):
  verified  - a traced palette source was edited, the planned color arrived in palette
              RAM and the replayed screen differs from the unedited replay
  ram-only  - the planned color arrived in palette RAM, but no sampled scene shows it
  traced    - live palette entries trace to ROM bytes or code values; no edit reproduced
  located   - colors are computed; replays measured which ROM bytes move them, but they
              are not plain colors there (compressed or generated)
  derived   - colors are computed by the game and no source was found
  none      - no live palette entries traced
  error     - the engine failed on this ROM
Graphics status per ROM, from VRAM tags:
  direct    - most traced VRAM bytes are plain ROM copies (editable in place)
  derived   - most are computed: compressed or generated (needs a codec or relocation)
  none      - VRAM was not traced

Every ROM that is not verified is listed with the reason, and the verified ones are counted by
how the edit was found:
  traced       - the entry's own tags led to the ROM bytes (one entry, or a whole scene at once)
  other scene  - another scene of the same run traced the same color straight to the ROM
  plain copy   - the palette line sits in the ROM as plain colors (palette_trace.stored_copies);
                 this is how colors prepared by an SNES coprocessor or faded through RAM are reached
  code number  - the color is a number in the program (palette_trace.constant_places)
  measured     - put together from several ROM bytes; each bit's effect was measured by replay
The same searches serve the editor's "let ROMancer look for it" (scene_graphics._plan_color).
"""
import argparse
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

PALETTE = ('verified', 'ram-only', 'traced', 'located', 'derived', 'none', 'error')

# SNES coprocessors that prepare data themselves. The hooks follow the main CPU's ROM reads through
# their bus handlers, but not what the chip's own processor reads, computes or decompresses.
UNTRACED_CHIPS = ('SA-1', 'SuperFX', 'S-DD1', 'SPC7110', 'Cx4')


def classify(r):
    if not r.get('ok'):
        return 'error', 'error'
    live = r.get('palette_live', {})
    causal = r.get('causal') or {}
    if causal.get('verified'):
        pal = 'verified'
    elif causal.get('entry_changed'):
        pal = 'ram-only'
    elif live.get('rom', 0) + live.get('code', 0):
        pal = 'traced'
    elif causal.get('derived_located'):
        pal = 'located'
    elif live.get('derived', 0):
        pal = 'derived'
    else:
        pal = 'none'
    v = r.get('domains', {}).get('vram') or r.get('domains', {}).get('chr') or {}
    direct, derived = v.get('rom', 0) + v.get('code', 0), v.get('derived', 0)
    gfx = 'none' if direct + derived == 0 else 'direct' if direct >= derived else 'derived'
    return pal, gfx


HOW = ('traced', 'other scene', 'plain copy', 'code number', 'measured')

# What a closer look at an unverified ROM found, by SHA-256. Added to the measured cause, never instead of it.
STUDIED = {
    '1af2d4b29552': 'Looked at by hand: one table byte is the final value of all three shade registers, and the program also '
                    'compares the palette with that same number in six places to end its fades, so changing the table byte '
                    'alone changes how the game runs. An edit would have to change those compares too.',
    '44c96f106b96': 'Looked at by hand: the game never writes video memory in this engine with this dump, so there is '
                    'nothing to trace or replay.',
}


def how_verified(r):
    """Which search verified this ROM's edit (see the module text), and whether it needed the second input script."""
    causal = r.get('causal') or {}
    mode, how = causal.get('mode', ''), causal.get('how', '')
    if mode == 'measured':
        found = 'measured'
    elif mode == 'search':
        found = 'other scene' if how == 'other scene' else 'code number' if how == 'constant in code' else 'plain copy'
    elif mode == 'search-bulk':
        found = 'plain copy'
    else:
        found = 'traced'
    return found, r.get('script', 'explore') != 'explore', causal.get('scenes') == 'between'


def snes_chip(rom):
    """Coprocessor named by the SNES cartridge header, or ''."""
    if len(rom) % 1024 == 512:
        rom = rom[512:]
    best = None
    for base in (0x7FC0, 0xFFC0, 0x40FFC0):
        if base + 0x30 > len(rom):
            continue
        h = rom[base:base + 0x30]
        score = (((h[0x1C] | h[0x1D] << 8) ^ (h[0x1E] | h[0x1F] << 8)) == 0xFFFF) * 4 \
            + all(32 <= c < 127 for c in h[:21]) * 2 + ((h[0x15] & 0x0F) % 2 == (base == 0xFFC0)) + (h[0x17] < 0x0E)
        if best is None or score > best[0]:
            best = (score, base, h)
    if not best:
        return ''
    _score, base, h = best
    kind, sub = h[0x16], rom[base - 1]
    if kind in (0x03, 0x04, 0x05):
        return 'DSP'
    if 0x13 <= kind <= 0x1A:
        return 'SuperFX'
    if kind in (0x23, 0x25):
        return 'OBC1'
    if kind in (0x32, 0x33, 0x34, 0x35, 0x36):
        return 'SA-1'
    if kind in (0x43, 0x45):
        return 'S-DD1'
    if kind == 0x55:
        return 'S-RTC'
    if kind in (0xF3,):
        return 'Cx4'
    if kind in (0xF5, 0xF9):
        return 'ST018' if kind == 0xF5 and sub == 0x02 else 'SPC7110'
    if kind == 0xF6:
        return 'ST010'
    return ''


_ARCHIVES = {}


def read_member(entry):
    archive, members = entry['zip'], re.split(r'(?<=\.zip)!', entry['member'], flags=re.I)
    if archive not in _ARCHIVES:
        _ARCHIVES[archive] = zipfile.ZipFile(archive)
    data = _ARCHIVES[archive].read(members[0])
    for member in members[1:]:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            data = z.read(member)
    return data


def cause(r, pal, chip):
    """Why this ROM's palette is not verified, in one line."""
    causal = r.get('causal') or {}
    attempts = causal.get('attempts', [])
    if chip in UNTRACED_CHIPS and pal != 'verified':
        return f'coprocessor: the {chip} chip prepares these colors itself; only the main CPU is traced'
    if pal == 'error':
        e = r.get('error', '')
        if e.startswith('Timeout'):
            return 'engine: no result within the time limit'
        if 'rejected content' in e:
            return 'engine: the core rejected this ROM'
        return 'engine: ' + e.split('\n')[0][:110]
    if pal == 'ram-only':
        return 'not on screen: edited colors reached palette RAM, but no sampled scene draws with them'
    if pal == 'none' and not (r.get('palette_live') or {}).get('unknown') and len(r.get('runs') or ()) > 1 and all(
            run.get('distinct_screens', 0) <= 1 for run in r['runs']):
        return 'no picture: the game never left a blank or static screen with either input script (it may not run in this engine)'
    if pal == 'traced':
        if any(a.get('entry_moved') or a.get('entries_moved') for a in attempts):
            return 'inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source)'
        if attempts:
            return 'no effect: editing the traced bytes did not change the color (data already copied before the first checkpoint, or a value coincidence)'
        return 'no plan: traced entries could not be planned (ROM byte differs from the stored color)'
    if pal == 'located':
        return 'computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors'
    if pal == 'derived':
        return 'computed: palette is decompressed or generated and no nearby ROM byte moved it'
    live = r.get('palette_live', {})
    if live.get('unknown'):
        return 'untraced: palette RAM was written from a source the hooks did not follow'
    if r.get('distinct_screens', 0) <= 1:
        return 'no picture: the game never left a blank or static screen with the scripted input'
    return 'no colors: palette RAM stayed empty in every sampled scene'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sweep'); ap.add_argument('index'); ap.add_argument('--markdown')
    ap.add_argument('--catalog', help='rom_samples.json: report only the ROMs in this catalog')
    ap.add_argument('--no-chips', action='store_true', help='skip reading SNES headers from the corpus')
    a = ap.parse_args()
    index = json.loads(Path(a.index).read_text())
    rows = [json.loads(p.read_text()) for p in sorted(Path(a.sweep).glob('*.json'))]
    catalog = None
    if a.catalog:
        catalog = {r['sha256']: r for r in json.loads(Path(a.catalog).read_text(encoding='utf-8'))['records']}
        rows = [r for r in rows if r.get('sha256') in catalog]
    per = defaultdict(lambda: {'pal': Counter(), 'gfx': Counter(), 'n': 0, 'how': Counter()})
    unverified = defaultdict(list)
    chips = defaultdict(list)
    for r in rows:
        pal, gfx = classify(r)
        s = per[r['system']]; s['n'] += 1; s['pal'][pal] += 1; s['gfx'][gfx] += 1
        if pal == 'verified':
            found, second, between = how_verified(r)
            s['how'][found] += 1; s['how']['second script'] += second; s['how']['scene between'] += between
        chip = ''
        if r['system'] == 'snes' and not a.no_chips and r.get('sha256') in index:
            try:
                chip = snes_chip(read_member(index[r['sha256']]))
            except Exception:  # an unreadable archive only loses the chip note
                chip = ''
        name = re.split(r'(?<=\.zip)!', r['member'], flags=re.I)[-1]
        if catalog:
            name = catalog[r['sha256']]['labels'][0]
        if chip:
            chips[chip].append((name, pal))
        if pal != 'verified':
            studied = next((text for prefix, text in STUDIED.items() if r.get('sha256', '').startswith(prefix)), '')
            unverified[r['system']].append((name, pal, cause(r, pal, chip) + ('. ' + studied if studied else '')))
    total = Counter(v['system_id'] for v in (catalog or index).values())
    lines = [f"| System | Traced / in {'catalog' if catalog else 'corpus'} | Palette verified | ram-only | traced | located | derived | none | errors | Graphics direct | derived | none |",
             '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for system in sorted(total):
        s = per.get(system)
        if not s:
            lines.append(f'| {system} | 0 / {total[system]} | | | | | | | | | | |'); continue
        p, g = s['pal'], s['gfx']
        lines.append(f"| {system} | {s['n']} / {total[system]} | {p['verified']} | {p['ram-only']} | {p['traced']} | {p['located']} | {p['derived']} | {p['none']} | {p['error']} | {g['direct']} | {g['derived']} | {g['none']} |")
    lines.append(f"| all | {sum(s['n'] for s in per.values())} / {sum(total.values())} | " + ' | '.join(
        str(sum(s[k][v] for s in per.values())) for k, v in
        [('pal', x) for x in PALETTE] + [('gfx', x) for x in ('direct', 'derived', 'none')]) + ' |')
    text = '\n'.join(lines)
    if catalog:
        missing = sorted(catalog[sha]['labels'][0] for sha in set(catalog) - {r.get('sha256') for r in rows})
        if missing:
            text += f'\n\nIn the catalog but not swept ({len(missing)}): ' + '; '.join(missing)
    columns = HOW + ('second script', 'scene between')
    text += ('\n\n## How the verified edits were found\n\n| System | ' + ' | '.join(HOW)
             + ' | needed the second input script | needed a scene between the main ones |\n|---|' + '---|' * len(columns) + '\n')
    text += '\n'.join(f"| {system} | " + ' | '.join(str(per[system]['how'][k]) for k in columns) + ' |' for system in sorted(per))
    text += '\n| all | ' + ' | '.join(str(sum(v['how'][k] for v in per.values())) for k in columns) + ' |'
    for system in sorted(unverified):
        items = unverified[system]
        groups = Counter(c.split(':')[0] for _n, _p, c in items)
        text += f'\n\n## {system}: {len(items)} not verified\n\n'
        text += 'By cause: ' + ', '.join(f'{k} {v}' for k, v in groups.most_common()) + '\n\n'
        text += '| ROM | Palette | Cause |\n|---|---|---|\n'
        text += '\n'.join(f'| {n} | {p} | {c} |' for n, p, c in sorted(items, key=lambda x: (x[2].split(':')[0], x[0])))
    if chips:
        text += '\n\n## SNES coprocessor cartridges\n\n| Chip | Hooks cover | ROMs | Palette verified |\n|---|---|---|---|\n'
        for chip in sorted(chips):
            items = chips[chip]
            text += f"| {chip} | {'main CPU only' if chip in UNTRACED_CHIPS else 'everything'} | {len(items)} | {sum(p == 'verified' for _n, p in items)} |\n"
        text += '\n' + '\n'.join(f'- {chip}: ' + '; '.join(f'{n} ({p})' for n, p in sorted(items)) for chip, items in sorted(chips.items()) if chip in UNTRACED_CHIPS)
    print(text)
    if a.markdown:
        Path(a.markdown).write_text(text + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
