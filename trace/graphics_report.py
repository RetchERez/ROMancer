"""Total graphics_sweep results for the ROMs that are in the catalog.

    python -B trace/graphics_report.py SWEEPDIR [--catalog knowledge/rom_samples.json] [--json OUT.json]
                                       [--markdown trace/COVERAGE.md] [--before OLD.json] [--before-label TEXT]

Uses graphics_sweep.report on the results whose SHA-256 is in the catalog, then prints one
line per system and a total: ROMs traced, a tile edit confirmed by any path (in place,
re-packed or run-time patch), an in-place tile edit, a background-cell edit, re-packed
graphics, run-time patches and how many of those are also clean from power-on, and
"only in this scene" private copies.

--markdown writes the graphics section of the coverage document: the same table, how the
background-cell edits were confirmed (in place, re-packed, through a stored piece), and
every ROM whose background-cell edit is not confirmed with its cause. The section sits
between two marker lines and only that part of the file is replaced (it is added at the
end when the markers are not there yet). --before names the --json output of an earlier
sweep; the section then also says how the background-cell count moved.

--not-shipped TEXT (repeatable) names an engine that is not part of the released tracing
packs: a result whose engine file name contains TEXT is left out of every count and listed
as not available, because a user of the release cannot trace that ROM.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import graphics_sweep  # noqa: E402

COLUMNS = (('ROMs', 'roms'), ('traced', 'traced'), ('any tile path', 'any_tile_path_confirmed'),
           ('tile in place', 'tile_edit_as_planned'), ('background cell', 'map_edit_as_planned'),
           ('hard tile re-packed', None), ('packed block re-packed', 'repack_confirmed'), ('run-time patch', 'overlay_as_planned'), ('patch clean from power-on', 'overlay_clean_from_boot'),
           ('only this scene tried', 'private_copy_tried'), ('only this scene', 'private_copy_as_planned'))
BEGIN = '<!-- graphics coverage: begin (written by trace/graphics_report.py; do not edit by hand) -->'
END = '<!-- graphics coverage: end -->'
CELL_PATHS = (('in place', 'direct'), ('re-packed', 'reencode'), ('moved and re-packed', 'relocate'), ('stored piece', 'cell-source'))


def table(totals) -> list:
    rows = []
    for system, s in totals.items():
        rows.append([system] + [s.get('hard_tile_confirmed_path', {}).get('reencode', 0) if key is None else s.get(key, 0)
                                for _name, key in COLUMNS])
    rows.append(['all'] + [sum(r[i] for r in rows) for i in range(1, len(COLUMNS) + 1)])
    out = ['| System | ' + ' | '.join(name for name, _ in COLUMNS) + ' |', '|---' * (len(COLUMNS) + 1) + '|']
    return out + ['| ' + ' | '.join(map(str, r)) + ' |' for r in rows]


def rom_name(result: dict, titles: dict) -> str:
    name = titles.get(result['sha256']) or result['member'].split('.zip!')[-1]
    return name.rsplit('.', 1)[0] if '.' in name[-5:] else name


def section(totals: dict, results: list, titles: dict, before: dict | None = None, before_label: str = 'the sweep before this one',
            unavailable: list | None = None) -> str:
    """The graphics part of the coverage document, as Markdown."""
    lines = [BEGIN, '', '## Graphics: what a replay confirmed', '',
             'From `trace/graphics_sweep.py` (one result per ROM; totals by `trace/graphics_report.py`). Every count is an '
             'edit that was made in the ROM, replayed in the real engine from a checkpoint of the same run, and found in '
             'video memory exactly as planned, compared with the unedited run. Header checksums are repaired first '
             '(`graphics_trace.fix_checksums`). Nothing else is counted.', '',
             '- **any tile path**: one picture (8x8 tile) on screen was redrawn by some path: in place, re-packed, or the '
             'run-time patch.',
             '- **tile in place**: the tile is ROM bytes and was written where it is.',
             '- **background cell**: one cell of a background map was made to show another tile (see below for how).',
             '- **hard tile re-packed**: the one tile picked as hardest to write in place (computed by the game, most '
             'used on screen) was changed by unpacking, editing and packing its data again in the same place.',
             '- **packed block re-packed**: one packed block of the ROM was recognised, unpacked, edited, packed again '
             '(in place, or moved with its pointer) and replayed. The tiles tried are picked as `trace/codec_survey.py` '
             'picks them: tiles with a picture first, tiles made of stream literals as well as computed ones, in every '
             'sampled scene. Counted only when the tile came out as planned, nothing else in the block changed, what '
             'follows a bare stream still unpacks as before, and no unrelated byte of video memory changed (a whole '
             'second copy of the same edit elsewhere is related, and is counted below).',
             '- **run-time patch**: the fallback routine on the vertical-blank interrupt swapped the tile in; '
             '**clean from power-on** when the whole run from power-on then differs only as planned.',
             '- **only this scene**: a private copy of shared tile data, with the one reference moved.', '']
    lines += table(totals)
    lines += ['', '### Packed blocks', '',
              'A block that turns out to be stored as it is (no packing) is a plain write and is counted apart.', '',
              '| System | block recognised | re-packed, confirmed | of those: moved | of those: a second copy changed too '
              '| stored as it is, confirmed | as planned, but unrelated bytes changed | as planned, but the block was not left sound |',
              '|---' * 8 + '|']
    keys = ('repack_block_recognised', 'repack_confirmed', None, 'repack_with_a_second_copy_elsewhere', 'repack_stored_as_it_is',
            'repack_as_planned_but_unrelated_bytes_changed', 'repack_as_planned_but_block_not_sound')
    sums = [0] * len(keys)
    for system, s in totals.items():
        row = [s.get('repack_path', {}).get('relocate', 0) if key is None else s.get(key, 0) for key in keys]
        sums = [a + b for a, b in zip(sums, row)]
        lines.append(f'| {system} | ' + ' | '.join(map(str, row)) + ' |')
    lines.append('| all | ' + ' | '.join(map(str, sums)) + ' |')
    codecs = {}
    for s in totals.values():
        for name, n in s.get('repack_codec', {}).items():
            codecs[name] = codecs.get(name, 0) + n
    if codecs:
        lines += ['', 'Confirmed re-packs by codec: ' + ', '.join(f'{name} {n}' for name, n in sorted(codecs.items(), key=lambda kv: (-kv[1], kv[0]))) + '.']
    lines += ['', '### Background cells', '',
              'The edit is the smallest there is: one cell, tile number plus one. Every layer of the scene is looked '
              'at, and when the scene chosen for the tile edit has no cell that can be changed, the other sampled '
              'scenes of the same run are (frames 450, 900, 1350 and 1800 of the scripted play).', '',
              '- **in place**: the cell\'s tile number is a ROM byte (or a value in code) and was written there.',
              '- **re-packed**: the map is packed in the ROM with a codec ROMancer knows.',
              '- **stored piece**: the game builds the cell from a block definition, a table it adds a base to, or a '
              'literal inside packed data. The ROM bytes at and around the traced source were tried one at a time; the '
              'place counts only when the cell then held exactly the planned value and nothing outside the background '
              'maps changed. Every other cell built from the same piece changes with it (the "other cells" column '
              'counts the ROMs where that happened, by any path).',
              '- **on a blank tile**: of the confirmed edits, those made on a cell that shows a tile of one flat color, '
              'because no sampled scene had a stored cell with a picture in it (a cleared screen). They are counted in '
              '"confirmed" and "in place".',
              '- **also from power-on**: of the confirmed edits, those where the whole recorded run, replayed from '
              'power-on with the edited ROM, also ends with the cell as planned. A separate fact from "confirmed" '
              '(which is the replay from a checkpoint before the scene), except for a stored piece: because that '
              'place is found by trying, it is counted only when it holds from power-on too with nothing outside the '
              'background maps changed.', '',
              '| System | traced | confirmed | ' + ' | '.join(name for name, _ in CELL_PATHS)
              + ' | in another scene than the tile edit | other cells change too | on a blank tile | also from power-on '
              '| not confirmed |',
              '|---' * (len(CELL_PATHS) + 8) + '|']
    total = [0] * (len(CELL_PATHS) + 7)
    for system, s in totals.items():
        paths = s.get('map_edit_path', {})
        row = [s['traced'], s['map_edit_as_planned']] + [paths.get(key, 0) for _, key in CELL_PATHS] + [
            s.get('map_edit_in_another_scene', 0), s.get('map_edit_other_cells_change_too', 0),
            s.get('map_edit_on_a_blank_tile', 0), s.get('map_edit_as_planned_from_power_on_too', 0),
            s['traced'] - s['map_edit_as_planned']]
        total = [a + b for a, b in zip(total, row)]
        lines.append(f'| {system} | ' + ' | '.join(map(str, row)) + ' |')
    lines.append('| all | ' + ' | '.join(map(str, total)) + ' |')
    if before:
        was = {k: v.get('map_edit_as_planned', 0) for k, v in before.items()}
        lines += ['', f'Background cells confirmed in {before_label}: '
                  + ', '.join(f'{k} {was.get(k, 0)}' for k in totals) + f' (all {sum(was.get(k, 0) for k in totals)}).']
    failing = sorted(((r['system'], rom_name(r, titles), graphics_sweep.map_cause(r)) for r in results
                      if r.get('ok') and not r['map_edit'].get('as_planned')), key=lambda row: (row[0], row[2][0], row[1].lower()))
    errors = sorted((r['system'], rom_name(r, titles), r.get('error', '')) for r in results if not r.get('ok'))
    lines += ['', f'### Background cell not confirmed ({len(failing)})', '']
    by_cause = {}
    for system, _, cause in failing:
        by_cause.setdefault(cause[0], {}).setdefault(system, 0)
        by_cause[cause[0]][system] += 1
    for cause, systems in sorted(by_cause.items(), key=lambda item: -sum(item[1].values())):
        lines.append(f'- **{cause}** ({sum(systems.values())}: ' + ', '.join(f'{k} {v}' for k, v in sorted(systems.items()))
                     + f'): {graphics_sweep.MAP_CAUSES[cause]}.')
    lines += ['', '| System | ROM | Cause |', '|---|---|---|']
    for system, name, cause in failing:
        lines.append(f'| {system} | {name} | {cause[0]}' + (f' ({cause[1]})' if cause[1] else '') + ' |')
    if errors:
        lines += ['', f'### Not traced ({len(errors)})', '', '| System | ROM | Error |', '|---|---|---|']
        lines += [f'| {system} | {name} | {error[:120]} |' for system, name, error in errors]
    if unavailable:
        lines += ['', f'### Not available ({len(unavailable)})', '',
                  'Swept with a tracing engine that is not shipped, so not counted anywhere above.', '',
                  '| System | ROM | Engine |', '|---|---|---|']
        lines += [f'| {r["system"]} | {rom_name(r, titles)} | {r.get("core", "")} |'
                  for r in sorted(unavailable, key=lambda r: (r['system'], rom_name(r, titles).lower()))]
    lines += ['', END]
    return '\n'.join(lines)


def write_section(path: Path, text: str) -> None:
    """Replace the marked section of `path` with `text`, or add it at the end."""
    old = path.read_text(encoding='utf-8') if path.exists() else ''
    if BEGIN in old and END in old:
        new = old[:old.index(BEGIN)] + text + old[old.index(END) + len(END):]
    else:
        new = old.rstrip('\n') + ('\n\n' if old.strip() else '') + text + '\n'
    path.write_text(new, encoding='utf-8', newline='\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sweep'); ap.add_argument('--catalog'); ap.add_argument('--json')
    ap.add_argument('--markdown', help='coverage document whose graphics section is rewritten')
    ap.add_argument('--not-shipped', action='append', default=[],
                    help='text in the file name of an engine that is not shipped; its results are not counted (repeatable)')
    ap.add_argument('--before', help='--json output of an earlier sweep, for the before/after line')
    ap.add_argument('--before-label', default='the sweep before this one', help='what to call that earlier sweep')
    a = ap.parse_args()
    keep, titles = None, {}
    if a.catalog:
        records = json.loads(Path(a.catalog).read_text(encoding='utf-8'))['records']
        keep = {r['sha256'] for r in records}
        titles = {r['sha256']: (r.get('labels') or [''])[0] for r in records}
    results, unavailable = [], []
    with tempfile.TemporaryDirectory() as folder:
        for p in Path(a.sweep).glob('*.json'):
            if keep is None or p.stem in keep:
                result = json.loads(p.read_text())
                if any(text.lower() in result.get('core', '').lower() for text in a.not_shipped):
                    unavailable.append(result)
                    continue
                shutil.copyfile(p, Path(folder) / p.name)
                results.append(result)
        totals = graphics_sweep.report(folder)
    if a.json:
        Path(a.json).write_text(json.dumps(totals, indent=1) + '\n', encoding='utf-8', newline='\n')
    if a.markdown:
        before = json.loads(Path(a.before).read_text(encoding='utf-8')) if a.before else None
        write_section(Path(a.markdown), section(totals, results, titles, before, a.before_label, unavailable))
    print('\n'.join(table(totals)))


if __name__ == '__main__':
    main()
