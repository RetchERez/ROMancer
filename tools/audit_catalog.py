"""Compare the built-in ROM catalog with No-Intro reference lists.

    python -B tools/audit_catalog.py DAT_DIR [--roms INDEX.json]
        [--json rows.json] [--relabel-out labels.json]

DAT_DIR holds clrmamepro-format reference lists (*.dat), one per system; they
are not part of this repository. Every catalog entry is looked up by SHA-1:

* Genesis, Master System, Game Boy and Game Boy Color files are compared whole;
* NES and SNES lists also describe the data without its container header, so
  those entries are compared whole first and then without the header. That
  needs the file itself: INDEX.json maps sha256 to {"zip": ..., "member": ...}
  (member may name nested ZIPs: inner.zip!game.nes) or to {"path": ...};
* a NES entry whose file is not available is still checked by CRC-32: the
  recorded whole-file CRC must equal a plain iNES header followed by a listed
  headerless dump. That result is reported as probable, not exact.

The report lists entries that are not in the reference lists, labels that
differ from the reference name, and reference names that mark an unusual dump
(prototype, unlicensed, pirate, re-release and so on) for a person to judge.
--relabel-out writes {sha256: reference name} for tools/prune_catalog.py.
Exit status is 1 when an entry is unverified or a label differs.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
DAT_SYSTEMS = (
    ('nintendo entertainment system', ('nes',)),   # must precede the Super Nintendo test
    ('game boy color', ('gb', 'gbc')),
    ('game boy advance', ()),
    ('game boy', ('gb', 'gbc')),                   # Color games that also run on Game Boy use either list
    ('mega drive', ('genesis',)),
    ('master system', ('sms',)),
)
ROM_LINE = re.compile(r'rom \( name "(.*)" size (\d+) crc ([0-9A-Fa-f]{8})(?: md5 [0-9A-Fa-f]{32})? sha1 ([0-9A-Fa-f]{40})')
PATCH_TAG = re.compile(r'\[(T-|T\+|Add by|Hack by|h\b)')
UNUSUAL = re.compile(
    r'\((Proto[^)]*|Beta[^)]*|Demo[^)]*|Sample[^)]*|Unl|Pirate|Aftermarket|Homebrew|Hack|Alt[^)]*|'
    r'Debug[^)]*|Kiosk[^)]*|Promo[^)]*|Program|Test Program|'
    r'[^)]*(Virtual Console|Collection|Classics|Sega Ages|Mini|Online|Anniversary|Arcade Archives|'
    r'Evercade|Limited Run|Retro-Bit|iam8bit|Piko|GameCube|Wii|Switch|Steam|Namcot|Reprint|Rerelease)[^)]*)\)')


def dat_systems(path):
    with path.open(encoding='utf-8', errors='replace') as stream:
        head = ''.join(stream.readline() for _ in range(6)).lower()
    if 'super nintendo' in head:
        return ('snes',)
    for key, systems in DAT_SYSTEMS:
        if key in head:
            return systems
    return ()


def load_dats(folder):
    """system -> {sha1: (name, size, crc)} for every rom line of every list."""
    by_system = {}
    for path in sorted(Path(folder).glob('*.dat')):
        systems = dat_systems(path)
        if not systems:
            print(f'Skipped {path.name}: not one of the six systems.', file=sys.stderr)
            continue
        with path.open(encoding='utf-8', errors='replace') as stream:
            for line in stream:
                found = ROM_LINE.search(line)
                if found:
                    name, size, crc, sha1 = found.groups()
                    for system in systems:
                        by_system.setdefault(system, {}).setdefault(sha1.lower(), (name, int(size), int(crc, 16)))
    return by_system


def read_indexed(entry):
    if 'path' in entry:
        return Path(entry['path']).read_bytes()
    data = Path(entry['zip']).read_bytes()
    for member in re.split(r'(?<=\.zip)!', entry['member'], flags=re.I):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            data = archive.read(member)
    return data


def _times(matrix, vector):
    total = index = 0
    while vector:
        if vector & 1:
            total ^= matrix[index]
        vector >>= 1
        index += 1
    return total


def crc_shift(length):
    """Matrix M with crc32(a + b) == M*crc32(a) ^ crc32(b) for len(b) == length (zlib's crc32_combine)."""
    square = lambda m: [_times(m, row) for row in m]
    odd = [0xEDB88320] + [1 << n for n in range(31)]
    even = square(odd)
    odd = square(even)
    result = [1 << n for n in range(32)]
    while True:
        even = square(odd)
        if length & 1:
            result = [_times(even, row) for row in result]
        length >>= 1
        if not length:
            return result
        odd = square(even)
        if length & 1:
            result = [_times(odd, row) for row in result]
        length >>= 1
        if not length:
            return result


def nes_by_crc(record, listed):
    """Reference dumps whose data, behind a plain iNES header, has this entry's whole-file CRC-32."""
    numbers = record.get('header_numbers', {})
    prg, chr_ = numbers.get('prg_rom_bytes', 0), numbers.get('chr_rom_bytes', 0)
    body = record['size'] - 16
    if record['format'] != 'ines' or prg + chr_ != body or prg % 16384 or chr_ % 8192 or prg > 255 * 16384:
        return []
    by_crc = {}
    for name, size, crc in listed.values():
        if size == body and name.lower().endswith('.unh'):
            by_crc.setdefault(crc, []).append(name)
    shift, target, mapper = crc_shift(body), int(record['crc32'], 16), numbers.get('mapper', 0)
    names = []
    for low in range(16):  # mirroring, battery, trainer and four-screen bits
        flags6, flags7 = (mapper & 15) << 4 | low, mapper & 0xF0
        for tail in (bytes(8), b'\0' * 7 + b'\1'):
            header = b'NES\x1a' + bytes([prg // 16384, chr_ // 8192, flags6, flags7]) + tail
            names += by_crc.get(target ^ _times(shift, zlib.crc32(header)), [])
    return sorted(set(names))


def audit(records, dats, index):
    rows = []
    for record in records:
        system, label = record['system_id'], record['labels'][0]
        listed = dats.get(system, {})
        row = {'sha256': record['sha256'], 'system': system, 'label': label, 'nointro': None,
               'match': None, 'in_corpus': record['sha256'] in index}
        found = listed.get(record.get('sha1', ''))
        if found:
            row.update(nointro=found[0], match='file')
        elif system in ('nes', 'snes'):
            skip = 16 if system == 'nes' else 512 if record['size'] % 1024 == 512 else 0
            if skip and row['in_corpus']:
                data = read_indexed(index[record['sha256']])
                if hashlib.sha256(data).hexdigest() != record['sha256']:
                    raise SystemExit(f"Indexed file for {label} has a different SHA-256.")
                found = listed.get(hashlib.sha1(data[skip:]).hexdigest())
                if found:
                    row.update(nointro=found[0], match='headerless')
            elif system == 'nes':
                names = nes_by_crc(record, listed)
                if len(names) == 1:
                    row.update(nointro=names[0], match='crc-probable')
        rows.append(row)
    return rows


def reference_name(row):
    return Path(row['nointro']).stem if row['nointro'] else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('dat_dir', type=Path)
    parser.add_argument('--roms', type=Path, metavar='INDEX', help='JSON: sha256 -> {zip, member} or {path}')
    parser.add_argument('--json', type=Path, help='write one row per entry')
    parser.add_argument('--relabel-out', type=Path, help='write {sha256: reference name} for labels that differ')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from romancer.rom_sample_db import load_database
    records = load_database()['records']
    dats = load_dats(args.dat_dir)
    missing = sorted({r['system_id'] for r in records} - set(dats))
    if missing:
        raise SystemExit(f'No reference list in {args.dat_dir} for: ' + ', '.join(missing))
    index = json.loads(args.roms.read_text(encoding='utf-8')) if args.roms else {}
    rows = audit(records, dats, index)
    rows.sort(key=lambda r: (r['system'], r['label'].casefold()))

    exact = [r for r in rows if r['match'] in ('file', 'headerless')]
    probable = [r for r in rows if r['match'] == 'crc-probable']
    patched = [r for r in rows if not r['match'] and PATCH_TAG.search(r['label'])]
    unverified = [r for r in rows if not r['match'] and not PATCH_TAG.search(r['label'])]
    differs = [r for r in rows if r['match'] and reference_name(r) != r['label']]
    unusual = [r for r in rows if r['match'] and UNUSUAL.search(reference_name(r))]

    print(f'{len(rows):,} catalog entries: {len(exact):,} exact reference dumps, {len(probable)} probable (CRC-32 only), '
          f'{len(patched)} labeled patches, {len(unverified)} unverified.')

    def section(title, items, line):
        if items:
            print(f'\n{title} ({len(items)})')
            for row in items:
                print('  ' + line(row))

    section('UNVERIFIED: not a reference dump and not labeled as a patch', unverified,
            lambda r: f"{r['system']:8}{r['label']}  {r['sha256']}"
                      + ('' if r['in_corpus'] or r['system'] not in ('nes', 'snes') else '  (file not available)'))
    section('Probable: header differs from the reference; data matches by CRC-32 only', probable,
            lambda r: f"{r['system']:8}{r['label']}  ~  {reference_name(r)}")
    section('Label differs from the reference name', differs,
            lambda r: f"{r['system']:8}{r['label']}\n{'':10}-> {reference_name(r)}")
    section('Reference name marks an unusual dump (review)', unusual,
            lambda r: f"{r['system']:8}{reference_name(r)}")
    section('Labeled patches (pre-patched translations and add-ons)', patched,
            lambda r: f"{r['system']:8}{r['label']}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=1) + '\n', encoding='utf-8', newline='\n')
    if args.relabel_out:
        args.relabel_out.write_text(
            json.dumps({r['sha256']: reference_name(r) for r in differs}, indent=1) + '\n', encoding='utf-8', newline='\n')
    return 1 if unverified or differs else 0


if __name__ == '__main__':
    raise SystemExit(main())
