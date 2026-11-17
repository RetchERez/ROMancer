"""Total graphics_sweep results for the ROMs that are in the catalog.

    python -B trace/graphics_report.py SWEEPDIR [--catalog knowledge/rom_samples.json] [--json OUT.json]

Uses graphics_sweep.report on the results whose SHA-256 is in the catalog, then prints one
line per system and a total: ROMs traced, a tile edit confirmed by any path (in place,
re-packed or run-time patch), an in-place tile edit, a background-cell edit, re-packed
graphics, run-time patches and how many of those are also clean from power-on, and
"only in this scene" private copies.
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
           ('re-packed', None), ('run-time patch', 'overlay_as_planned'), ('patch clean from power-on', 'overlay_clean_from_boot'),
           ('only this scene tried', 'private_copy_tried'), ('only this scene', 'private_copy_as_planned'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sweep'); ap.add_argument('--catalog'); ap.add_argument('--json')
    a = ap.parse_args()
    keep = None
    if a.catalog:
        keep = {r['sha256'] for r in json.loads(Path(a.catalog).read_text(encoding='utf-8'))['records']}
    with tempfile.TemporaryDirectory() as folder:
        for p in Path(a.sweep).glob('*.json'):
            if keep is None or p.stem in keep:
                shutil.copyfile(p, Path(folder) / p.name)
        totals = graphics_sweep.report(folder)
    if a.json:
        Path(a.json).write_text(json.dumps(totals, indent=1) + '\n', encoding='utf-8', newline='\n')
    rows = []
    for system, s in totals.items():
        rows.append([system] + [s.get('hard_tile_confirmed_path', {}).get('reencode', 0) if key is None else s.get(key, 0)
                                for _name, key in COLUMNS])
    rows.append(['all'] + [sum(r[i] for r in rows) for i in range(1, len(COLUMNS) + 1)])
    print('| System | ' + ' | '.join(name for name, _ in COLUMNS) + ' |')
    print('|---' * (len(COLUMNS) + 1) + '|')
    for r in rows:
        print('| ' + ' | '.join(map(str, r)) + ' |')


if __name__ == '__main__':
    main()
