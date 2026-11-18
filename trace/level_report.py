"""Put the level map measurements (trace/level_blocks.py results, one JSON per ROM) into trace/COVERAGE.md.

    python -B trace/level_report.py <folder with <sha>.json> [--markdown trace/COVERAGE.md]

Prints the totals; with --markdown, writes the "Level maps" section (replacing an earlier one).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HEAD = '## Level maps'
NL = chr(10)
SYSTEMS = {'nes': 'NES', 'snes': 'Super NES', 'genesis': 'Mega Drive', 'sms': 'Master System', 'gb': 'Game Boy', 'gbc': 'Game Boy Color'}


def rows(folder: Path) -> list:
    return sorted((json.loads(path.read_text()) for path in folder.glob('*.json')), key=lambda r: r.get('name', ''))


def outcome(row: dict) -> tuple:
    """(what happened, places of the map that then looked different) for one ROM."""
    blocks = row.get('blocks') or {}
    results = [r for r in blocks.get('results', []) if not r.get('error') and r.get('verified') and not r.get('painted_places_that_did_not_change')]
    listed = next((r for r in results if r.get('method') == 'layout'), None)
    if listed:
        return 'list', listed.get('places_changed')
    if results:
        return 'block', results[0].get('places_changed')
    if row.get('map') and row.get('grid'):
        return 'blocks seen', None
    if row.get('map'):
        return 'map', None
    return 'none', None


def totals(found: list) -> dict:
    kinds = [outcome(r)[0] for r in found]
    return {'games': len(found), 'maps': sum(1 for r in found if r.get('map')), 'built_from_blocks': sum(1 for r in found if r.get('grid')),
            'changed_in_the_list': kinds.count('list'), 'changed_the_block': kinds.count('block')}


def markdown(found: list) -> str:
    t = totals(found)
    names = {'list': "In the level's own list of blocks", 'block': 'The block itself, everywhere it is used',
             'blocks seen': 'Blocks found, no change confirmed', 'map': 'Map only', 'none': 'No map'}
    lines = [HEAD, '',
             f'Measured with `trace/level_blocks.py` on {t["games"]} well-known games. For each one the game played by itself '
             '(the menu presses of Record more scenes, then walking right and jumping) while a level was recorded, the map was put together, '
             'and one whole block of the level was painted onto a place that showed another block, through the level map. A change counts '
             'only when a replay of the real game from the start of the recording showed the painted block in video memory and the painted places then looked different on the map. The play is automatic, so a game '
             'whose menus it does not get through, or that needs more than walking right, is measured on whatever screen it reached.', '',
             '| What | Games |', '|---|---|',
             f'| A level map was put together | {t["maps"]} of {t["games"]} |',
             f'| The level is built from blocks that are copied from a table in the ROM | {t["built_from_blocks"]} |',
             f"| A block was changed in the level's own list of blocks, confirmed by replay | {t['changed_in_the_list']} |",
             f'| Otherwise the block itself was changed (every place that uses it), confirmed by replay | {t["changed_the_block"]} |', '',
             'Places that looked different afterwards are counted over the whole map. A count equal to the size of the block means only that '
             'place changed. A larger count means the game uses the changed entry in more places, or that the change sent the automatic play '
             'another way (it walks into the new block), so later captures show other things.', '',
             '| Game | System | Map (cells) | Blocks | Result | Places that looked different |', '|---|---|---|---|---|---|']
    for row in found:
        kind, places = outcome(row)
        size = row.get('map')
        grid = row.get('grid')
        larger = row.get('larger')
        blocks = '' if not grid else f'{grid[0]} by {grid[1]}' + (f', in larger blocks of {grid[0] * larger[0]} by {grid[1] * larger[1]}' if larger else '')
        lines.append(f"| {row.get('name', row.get('sha256', ''))[:-4] if '.' in row.get('name', '')[-5:] else row.get('name', '')} | "
                     f"{SYSTEMS.get(row.get('system'), '')} | {'' if not size else f'{size[0]} by {size[1]}'} | {blocks} | {names[kind]} | "
                     f"{'' if places is None else places} |")
    return NL.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--markdown', type=Path)
    args = parser.parse_args()
    found = rows(args.folder)
    if args.markdown:
        page = args.markdown.read_text(encoding='utf-8')
        if HEAD in page:
            page = page[:page.index(HEAD)]
        args.markdown.write_text(page.rstrip() + NL + NL + markdown(found).rstrip() + NL, encoding='utf-8', newline=NL)
    print(json.dumps(totals(found), indent=1))
    print(', '.join(sorted(r['name'].rsplit('.', 1)[0] for r in found if outcome(r)[0] == 'list')))


if __name__ == '__main__':
    main()
