"""Render the bundled exact-revision catalog for GitHub and offline use."""
import argparse
from html import escape
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from romancer import ROMANCER_RELEASE_NAME
from romancer.rom_sample_db import load_database

SYSTEM_LABELS = {
    'nes': 'NES',
    'snes': 'SNES',
    'genesis': 'Genesis / Mega Drive',
    'sms': 'Master System',
    'gb': 'Game Boy',
    'gbc': 'Game Boy Color',
}
TESTED_GAMES = 'https://github.com/RetchERez/ROMancer/releases/download/v1.0.0/TESTED-GAMES.txt'
PORTABLE = 'https://github.com/RetchERez/ROMancer/releases/download/v1.0.0/ROMancer-v1.0.0-Windows.zip'


def grouped(records):
    rows = {system: [] for system in SYSTEM_LABELS}
    for record in records:
        rows[record['system_id']].append(record)
    for values in rows.values():
        values.sort(key=lambda row: (row['labels'][0].casefold(), row['sha256']))
    return rows


def markdown_label(text):
    return escape(text, quote=False).replace('|', '&#124;').replace('[', '&#91;').replace(']', '&#93;').replace('*', '&#42;').replace('_', '&#95;').replace('\x60', '&#96;')


def render_markdown(records):
    systems = grouped(records)
    lines = [
        '# ROM catalog',
        '',
        f'{ROMANCER_RELEASE_NAME} identifies **{len(records):,} exact ROM revisions** across six systems.',
        'Each row represents one file hash. Different releases, regions or revisions of a game can have separate rows.',
        '',
        'All cataloged revisions passed the controlled byte-edit, undo/redo, build and BPS verification workflow.',
        'Game-specific visual and named editors use checked definitions for the selected revision.',
        f'[See game-specific edits and playtest results]({TESTED_GAMES}).',
        '',
        f'Use Ctrl+F to search here, or open **ROM Catalog.html** in the extracted [portable ZIP]({PORTABLE})',
        'to search by title or hash and filter by system offline.',
        '',
        '| System | Revisions |',
        '| --- | ---: |',
    ]
    lines.extend(f'| [{name}](#{system}) | {len(systems[system])} |' for system, name in SYSTEM_LABELS.items())
    for system, name in SYSTEM_LABELS.items():
        lines += ['', f'<a name="{system}"></a>', f'## {name}', '',
                  '| ROM revision | Bytes | CRC32 | SHA-256 |', '| --- | ---: | --- | --- |']
        for row in systems[system]:
            labels = '<br>'.join(map(markdown_label, row['labels']))
            lines.append(f"| {labels} | {row['size']:,} | {row['crc32']} | " + '\x60' + row['sha256'] + '\x60 |')
    return '\n'.join(lines) + '\n'


PAGE_START = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ROM Catalog | ROMancer</title>
<style>
:root{color-scheme:dark;--bg:#10191f;--panel:#18242b;--line:#3b5159;--text:#e6eeeb;--muted:#b9c9c8;--accent:#85e0c4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,sans-serif}
main{max-width:1120px;margin:auto;padding:32px clamp(16px,4vw,48px)}h1{font-size:2rem;margin:0}
h2{font-size:1.25rem;margin:1.5rem 0 .5rem}p{max-width:78ch;margin:.5rem 0}.muted,caption{color:var(--muted)}
a{color:var(--accent)}a:focus-visible,input:focus-visible,select:focus-visible,.table-wrap:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.filters{display:grid;grid-template-columns:minmax(0,2fr) minmax(12rem,1fr);gap:12px;padding:16px;background:var(--panel);border:1px solid var(--line);border-radius:10px;margin-top:20px}
.filters label{display:grid;gap:6px}input,select{width:100%;font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);padding:.55rem .7rem;border-radius:.35rem}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:.5rem}table{width:100%;border-collapse:collapse;text-align:left}th,td{padding:.5rem .75rem;border-bottom:1px solid var(--line);vertical-align:top}thead{background:var(--panel)}tbody tr:last-child td{border-bottom:0}
th:first-child{min-width:12rem}th:nth-child(2),td:nth-child(2){text-align:right;white-space:nowrap}td:last-child{min-width:14rem}code{overflow-wrap:anywhere}
[hidden]{display:none!important}
@media(max-width:600px){.filters{grid-template-columns:1fr}main{padding-top:20px}}
</style>
<main>
"""


def render_html(records):
    systems = grouped(records)
    parts = [
        PAGE_START,
        '<h1>ROM catalog</h1>',
        f'<p class="muted">{escape(ROMANCER_RELEASE_NAME)} · {len(records):,} exact revisions</p>',
        '<p>Search the ROM revisions recognized by the offline catalog. A row identifies one exact file.</p>',
        '<p>Every listed revision passed a byte edit, undo/redo, build and BPS verification. '
        'Game-specific editors depend on checked definitions for your revision. '
        f'<a href="{TESTED_GAMES}">See the separate game-specific test results</a>.</p>',
        '<div class="filters" id="filters" hidden>',
        '<label>Find a title or hash<input id="query" type="search" placeholder="Castlevania or CRC32" maxlength="128"></label>',
        '<label>System<select id="system"><option value="all">All six systems</option>',
    ]
    for system, name in SYSTEM_LABELS.items():
        parts.append(f'<option value="{system}">{escape(name)} ({len(systems[system])})</option>')
    parts.extend(['</select></label></div>', f'<p id="results" role="status">{len(records):,} revisions shown</p>'])
    for system, name in SYSTEM_LABELS.items():
        parts += [
            f'<section data-system="{system}" aria-labelledby="{system}">',
            f'<h2 id="{system}">{escape(name)}</h2>',
            f'<div class="table-wrap" role="region" tabindex="0" aria-label="{escape(name)} revisions">',
            '<table><thead><tr><th scope="col">ROM revision</th><th scope="col">Bytes</th>'
            '<th scope="col">CRC32</th><th scope="col">SHA-256</th></tr></thead><tbody>',
        ]
        for row in systems[system]:
            labels = '<br>'.join(map(escape, row['labels']))
            parts.append(
                f"<tr><td>{labels}</td><td>{row['size']:,}</td><td><code>{row['crc32']}</code></td>"
                f"<td><code>{row['sha256']}</code></td></tr>"
            )
        parts.append('</tbody></table></div></section>')
    parts.append("""</main>
<script>
const query = document.getElementById('query');
const system = document.getElementById('system');
const results = document.getElementById('results');
const groups = Array.from(document.querySelectorAll('section[data-system]'), section => ({
  section,
  entries: Array.from(section.querySelectorAll('tbody tr'), row => ({
    row,
    text: row.textContent.toLowerCase(),
  })),
}));
function showMatches() {
  const terms = query.value.toLowerCase().trim().split(/\\s+/);
  let count = 0;
  for (const {section, entries} of groups) {
    const matchesSystem = system.value === 'all' || system.value === section.dataset.system;
    let sectionCount = 0;
    for (const {row, text} of entries) {
      row.hidden = !matchesSystem || !terms.every(term => text.includes(term));
      if (!row.hidden) sectionCount += 1;
    }
    section.hidden = !sectionCount;
    count += sectionCount;
  }
  results.textContent = count
    ? count.toLocaleString() + (count === 1 ? ' revision shown' : ' revisions shown')
    : 'No matching revisions. Try another title or hash.';
}
query.addEventListener('input', showMatches);
system.addEventListener('change', showMatches);
document.getElementById('filters').hidden = false;
</script>
</html>
""")
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--markdown', type=Path)
    parser.add_argument('--html', type=Path)
    args = parser.parse_args()
    if not args.markdown and not args.html:
        parser.error('Choose --markdown or --html.')
    records = load_database()['records']
    if args.markdown:
        args.markdown.write_text(render_markdown(records), encoding='utf-8', newline='\n')
    if args.html:
        args.html.write_text(render_html(records), encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
