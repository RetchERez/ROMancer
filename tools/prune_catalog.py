"""Remove or relabel exact revisions in the built-in ROM catalog, consistently.

    python -B tools/prune_catalog.py --remove SHA256 [SHA256 ...]
    python -B tools/prune_catalog.py --remove-file removals.txt --relabel labels.json
    python -B tools/prune_catalog.py --check

The catalog is one set of exact file identities kept in four files:

    knowledge/rom_samples.json       measured facts and labels
    knowledge/game_support.json      coverage targets
    knowledge/corpus_evidence.json   relationships between entries
    knowledge/catalog_playtest.json  recorded engine observations

and it is pinned by hash in romancer/game_coverage.py and
romancer/corpus_evidence.py. This tool edits all of them together:

* removed entries leave every file, and other entries' `related` lists and
  the confirmed playtest routes no longer refer to them;
* a relabel map {sha256: "new label"} replaces the label everywhere;
* the target count, catalog/showcase counts, target pin, target-set name,
  source count, identity pin and database pin are recomputed;
* the total written in the documents listed in DOCUMENTS is updated;
* knowledge/ROM-CATALOG.md is rendered again.

A removal file has one SHA-256 per line; anything after the hash is a comment.
Nothing is written with --dry-run. --check only verifies that the files agree.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / 'knowledge'
SYSTEMS = ('nes', 'snes', 'genesis', 'sms', 'gb', 'gbc')
SET_PREFIX = 'romancer-v1.1-catalog-'
HASH = re.compile('[0-9a-f]{64}')

# name: (indent, separators, ensure_ascii) reproduces each file byte for byte.
FILES = {
    'rom_samples': (None, (',', ':'), True),
    'game_support': (2, None, True),
    'corpus_evidence': (None, (',', ':'), False),
    'catalog_playtest': (None, (',', ':'), True),
}
# Prose that states the catalog total. Only the exact old total is replaced.
DOCUMENTS = ('README.txt', '.github/README.md', 'user-guide/guide.json', 'user-guide/index.html', 'trace/DESIGN.md')


def encode(name, data):
    indent, separators, ascii_only = FILES[name]
    return (json.dumps(data, indent=indent, separators=separators, ensure_ascii=ascii_only) + '\n').encode('utf-8')


def load():
    return {name: json.loads((KNOWLEDGE / f'{name}.json').read_bytes()) for name in FILES}


def check_label(text):
    if (type(text) is not str or not 1 <= len(text) <= 256 or text != text.strip()
            or any(ord(c) < 32 or c in '/\\:' for c in text)):
        raise SystemExit(f'Unusable label: {text!r}')


def identities(data):
    """The identity set every file must share: sha256 -> (system, size)."""
    sets = {
        'rom_samples': {r['sha256']: (r['system_id'], r['size']) for r in data['rom_samples']['records']},
        'game_support': {r['sha256']: (r['system_id'], r['size']) for r in data['game_support']['targets']},
        'corpus_evidence': {r['sha256']: (r['system_id'], r['size']) for r in data['corpus_evidence']['records']},
        'catalog_playtest': {r['sha256']: (r['system_id'], r['size']) for r in data['catalog_playtest']['records']},
    }
    first = sets['rom_samples']
    for name, rows in sets.items():
        if rows != first:
            odd = sorted(set(rows) ^ set(first))[:5]
            raise SystemExit(f'knowledge/{name}.json lists a different set than rom_samples.json: {odd}')
    return first


def labels(data):
    return {r['sha256']: r['labels'][0] for r in data['rom_samples']['records']}


def apply(data, remove, relabel):
    remove = set(remove)
    samples, support, evidence, playtest = (data[name] for name in FILES)
    for row in samples['records']:
        if row['sha256'] in relabel:
            row['labels'] = [relabel[row['sha256']]]
    for row in support['targets']:
        if row['sha256'] in relabel:
            row['labels'] = [relabel[row['sha256']]]
    for row in evidence['records']:
        if row['sha256'] in relabel:
            row['label'] = relabel[row['sha256']]
    if remove:
        samples['records'] = [r for r in samples['records'] if r['sha256'] not in remove]
        support['targets'] = [r for r in support['targets'] if r['sha256'] not in remove]
        evidence['records'] = [r for r in evidence['records'] if r['sha256'] not in remove]
        for row in evidence['records']:
            row['related'] = [e for e in row['related'] if e['sha256'] not in remove]
        playtest['records'] = [r for r in playtest['records'] if r['sha256'] not in remove]
        if 'confirmed_routes' in playtest:
            playtest['confirmed_routes'] = [r for r in playtest['confirmed_routes'] if r['sha256'] not in remove]


def pins(data, set_changed):
    """Recompute every stored count and pin; returns the module constants."""
    support, evidence = data['game_support'], data['corpus_evidence']
    targets = support['targets']
    count = len(targets)
    if set_changed:
        support['target_set_id'] = f'{SET_PREFIX}{count}'
    rows = sorted([r['sha256'], r['system_id'], r['size'], sorted(r['origin'])] for r in targets)
    target_pin = hashlib.sha256(json.dumps(rows, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
    sources = sorted([r['sha256'], r['system_id'], r['size']] for r in evidence['records'])
    identity_pin = hashlib.sha256(json.dumps(sources, separators=(',', ':')).encode()).hexdigest()
    evidence['source_count'] = len(evidence['records'])
    evidence['source_identity_sha256'] = identity_pin
    catalog = sum('catalog' in r['origin'] for r in targets)
    showcase = sum('showcase' in r['origin'] for r in targets)
    return {
        'romancer/game_coverage.py': {
            'TARGET_SET_ID': repr(support['target_set_id']),
            'TARGET_COUNT': str(count),
            'CATALOG_COUNT': str(catalog),
            'SHOWCASE_COUNT': str(showcase),
            'ADDITIONAL_SHOWCASE_COUNT': str(count - catalog),
            'TARGET_PIN': repr(target_pin),
        },
        'romancer/corpus_evidence.py': {
            'IDENTITY_PIN': repr(identity_pin),
            'DATABASE_PIN': repr(hashlib.sha256(encode('corpus_evidence', evidence)).hexdigest()),
        },
    }


def set_constants(path, values, write):
    """Rewrite `NAME=value` module constants; each must exist exactly once."""
    text = (ROOT / path).read_bytes().decode('utf-8')
    changed = []
    for name, value in values.items():
        pattern = re.compile(rf'^{name}=(.*)$', re.M)
        found = pattern.findall(text)
        if len(found) != 1:
            raise SystemExit(f'{path}: expected exactly one {name}= line, found {len(found)}')
        if found[0] != value:
            changed.append(f'{path}: {name} {found[0]} -> {value}')
            text = pattern.sub(lambda m: f'{name}={value}', text)
    if changed and write:
        (ROOT / path).write_bytes(text.encode('utf-8'))
    return changed


def update_documents(old_total, new_total, old_loaded, new_loaded, write):
    """Replace the stated total (and the playtest 'loaded N of M' pair) in prose."""
    notes = []
    old, new = f'{old_total:,}', f'{new_total:,}'
    for name in DOCUMENTS:
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_bytes().decode('utf-8')
        updated = text.replace(f'loaded {old_loaded:,} of the {old}', f'loaded {new_loaded:,} of the {new}')
        updated = re.sub(rf'(?<![\d,.]){re.escape(old)}(?![\d,])', new, updated)
        if updated != text:
            notes.append(f'{name}: {text.count(old)} mention(s) of {old} -> {new}')
            if write:
                path.write_bytes(updated.encode('utf-8'))
    return notes


def verify():
    """Load every file through the application's own validators, in a fresh process."""
    code = (
        'import json;'
        'from romancer import rom_sample_db, game_coverage, corpus_evidence, catalog_playtest;'
        'rows=rom_sample_db.load_database()["records"];targets=game_coverage.load_manifest();'
        'by=corpus_evidence._load(str(corpus_evidence.DATABASE_PATH),corpus_evidence.fingerprint());'
        'play=catalog_playtest.records();'
        'ids={r["sha256"] for r in rows};'
        'assert ids=={r["sha256"] for r in targets}==set(by)==set(play),"identity sets differ";'
        'assert len(rows)==game_coverage.TARGET_COUNT;'
        'assert game_coverage.TARGET_SET_ID.endswith(str(len(rows)));'
        'print(len(rows))'
    )
    done = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit('Catalog files do not validate:\n' + done.stderr[-2000:])
    return int(done.stdout.strip())


def read_hashes(args):
    values = list(args.remove or [])
    for path in args.remove_file or []:
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            line = line.split('#', 1)[0].strip()
            if line:
                values.append(line.split()[0])
    values = [v.lower() for v in values]
    for value in values:
        if not HASH.fullmatch(value):
            raise SystemExit(f'Not a SHA-256: {value}')
    return list(dict.fromkeys(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--remove', nargs='+', metavar='SHA256', help='entries to remove')
    parser.add_argument('--remove-file', action='append', metavar='FILE', help='text file, one SHA-256 per line')
    parser.add_argument('--relabel', action='append', metavar='JSON', help='JSON object {sha256: new label}')
    parser.add_argument('--allow-missing', action='store_true', help='ignore hashes that are not in the catalog')
    parser.add_argument('--dry-run', action='store_true', help='report what would change; write nothing')
    parser.add_argument('--check', action='store_true', help='verify the catalog files, pins and counts; change nothing')
    args = parser.parse_args()
    if args.check:
        print(f'{verify():,} entries; files, pins and counts agree.')
        return 0
    remove = read_hashes(args)
    relabel = {}
    for path in args.relabel or []:
        loaded = json.loads(Path(path).read_text(encoding='utf-8'))
        if type(loaded) is not dict:
            raise SystemExit(f'{path}: expected an object of sha256: label')
        relabel.update({k.lower(): v for k, v in loaded.items()})
    if not remove and not relabel:
        parser.error('Nothing to do: give --remove, --remove-file, --relabel or --check.')

    data = load()
    before = identities(data)
    names = labels(data)
    missing = sorted((set(remove) | set(relabel)) - set(before))
    if missing and not args.allow_missing:
        raise SystemExit('Not in the catalog (use --allow-missing to skip):\n  ' + '\n  '.join(missing))
    remove = [v for v in remove if v in before]
    relabel = {k: v for k, v in relabel.items() if k in before and k not in remove and names[k] != v}
    for value in relabel.values():
        check_label(value)
    old_loaded = sum(r['loaded'] for r in data['catalog_playtest']['records'])

    apply(data, remove, relabel)
    after = identities(data)
    constants = pins(data, set_changed=bool(remove))
    new_loaded = sum(r['loaded'] for r in data['catalog_playtest']['records'])
    write = not args.dry_run

    for sha in remove:
        print(f'remove  {before[sha][0]:8}{names[sha]}  {sha}')
    for sha, value in sorted(relabel.items(), key=lambda item: names[item[0]].casefold()):
        print(f'relabel {before[sha][0]:8}{names[sha]}\n     -> {value}')
    if write:
        for name in FILES:
            (KNOWLEDGE / f'{name}.json').write_bytes(encode(name, data[name]))
    for path, values in constants.items():
        for note in set_constants(path, values, write):
            print(note)
    if len(after) != len(before):
        for note in update_documents(len(before), len(after), old_loaded, new_loaded, write):
            print(note)
    if write:
        verify()
        subprocess.run([sys.executable, '-B', str(ROOT / 'tools/render_rom_catalog.py'),
                        '--markdown', str(KNOWLEDGE / 'ROM-CATALOG.md')], cwd=ROOT, check=True)
    per_system = collections.Counter(system for system, _ in after.values())
    print(f"{'Would have' if args.dry_run else 'Catalog now has'} {len(after):,} entries "
          f"({len(remove)} removed, {len(relabel)} relabeled): "
          + ', '.join(f'{system} {per_system[system]}' for system in SYSTEMS))
    if not args.dry_run and len(after) != len(before):
        print('Rebuild generated documents that state the total (user guide PDF, packaged ROM Catalog.html).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
