"""Finish tracing-engine packs and write their release pins. Safe to run again after any rebuild.

    python tools/pin_trace_cores.py --licenses <cores/licenses> <built folder> [<built folder> ...]

Each <built folder> is the output of tools/build_trace_cores.py for one
platform (Windows x64 or Linux x86-64). For each one this:

1. refuses a stale build: the hook script and header recorded in
   TRACE-BUILD-INFO.json must be the ones in trace/ now;
2. completes the folder into the trace-cores pack that ships beside the app:
   TRACE-ORIGINS.json, THIRD_PARTY_NOTICES.txt, licenses/ and source-changes/
   (the hook scripts, header and build recipe: the corresponding source
   changes for the GPL engines);
3. replaces that platform's entries in romancer/trace_core_pins.py. The other
   platform's entries are kept, so the two packs can be pinned separately.

--licenses is the reviewed playtest engine pack's licenses folder; its files
are checked against romancer/core_pins.py before they are copied.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import pprint
import shutil
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from romancer.core_pins import WINDOWS_CORE_FILES, WINDOWS_CORE_PINS
from tools.build_trace_cores import BUILD_INFO, HEADER, MARKER, TRACE_ENGINES, library_suffix, sha256

REPO = Path(__file__).resolve().parents[1]
PINS_FILE = REPO / 'romancer/trace_core_pins.py'
PLATFORMS = ('windows-amd64', 'linux-x86_64')
ENGINE_LICENSES = ('blastem.txt', 'bsnes-mercury.txt', 'fceumm.txt', 'gambatte.txt')


def current_pins():
    spec = importlib.util.spec_from_file_location('trace_core_pins_now', PINS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.TRACE_CORE_PINS), dict(module.TRACE_CORE_FILES)


def finish_pack(folder, licenses):
    """Complete one built folder; returns (platform, {sha: pin}, {name: {'size', 'sha256'}})."""
    folder = Path(folder)
    try:
        info = json.loads((folder / BUILD_INFO).read_text(encoding='utf-8'))
    except OSError:
        raise SystemExit(f'{folder}: no {BUILD_INFO}; build it with tools/build_trace_cores.py') from None
    platform_id = info.get('platform')
    if platform_id not in PLATFORMS or info.get('core_sources_sha256') != WINDOWS_CORE_FILES['CORE-SOURCES.zip']['sha256']:
        raise SystemExit(f'{folder}: not built from the pinned CORE-SOURCES.zip')
    if set(info.get('engines', {})) != set(TRACE_ENGINES):
        raise SystemExit(f'{folder}: engines missing: ' + ', '.join(sorted(set(TRACE_ENGINES) - set(info.get('engines', {})))))
    suffix = library_suffix(platform_id)
    pins, origins = {}, {}
    for engine, spec in TRACE_ENGINES.items():
        row, base = info['engines'][engine], WINDOWS_CORE_PINS[engine]
        library = folder / (spec['base'] + suffix)
        if row.get('file') != library.name or not library.is_file() or sha256(library) != row['sha256']:
            raise SystemExit(f'{folder}: {library.name} is missing or differs from its build record')
        if MARKER not in library.read_bytes():
            raise SystemExit(f'{library}: not a tracing build')
        if row['patch_sha256'] != sha256(REPO / row['patch']) or row['header_sha256'] != sha256(REPO / 'trace' / HEADER):
            raise SystemExit(f'{folder}: {library.name} is stale. {row["patch"]} or trace/{HEADER} changed after it was built. '
                             f'Rebuild it: python tools/build_trace_cores.py --sources CORE-SOURCES.zip --output "{folder}" --update --only {engine}')
        pin = {'name': base['name'] + ' (tracing)', 'engine': engine, 'file': library.name, 'platform': platform_id,
               'systems': spec['systems'], 'license': base['license'], 'source_url': base['source_url'],
               'source_commit': base['source_commit'], 'source_directory': base['source_directory'],
               'romancer_patch': row['patch'], 'patch_sha256': row['patch_sha256'], 'header_sha256': row['header_sha256']}
        if base.get('romancer_patch'):
            pin['base_patch'] = base['romancer_patch']
        if row.get('generated_interpreters_compiler'):
            pin['generated_interpreters_compiler'] = row['generated_interpreters_compiler']
        pins[row['sha256']] = pin
        origins[engine] = {**pin, 'sha256': row['sha256']}
    # Anything else in the folder is regenerated, so a second run gives the same pack.
    keep = {BUILD_INFO} | {spec['base'] + suffix for spec in TRACE_ENGINES.values()}
    for path in sorted(folder.iterdir()):
        if path.name not in keep:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    (folder / 'TRACE-ORIGINS.json').write_text(json.dumps(origins, indent=2) + '\n', encoding='utf-8', newline='\n')
    shutil.copyfile(REPO / 'trace/ENGINES-NOTICES.txt', folder / 'THIRD_PARTY_NOTICES.txt')
    changes = folder / 'source-changes'
    changes.mkdir()
    for name in sorted({spec['patch'] for spec in TRACE_ENGINES.values()} | {HEADER}):
        shutil.copyfile(REPO / 'trace' / name, changes / name)
    shutil.copyfile(REPO / 'tools/build_trace_cores.py', changes / 'build_trace_cores.py')
    target = folder / 'licenses'
    target.mkdir()
    names = list(ENGINE_LICENSES)
    if platform_id == 'windows-amd64':
        names += sorted(n.split('/', 1)[1] for n in WINDOWS_CORE_FILES if n.startswith('licenses/toolchain-'))
    else:
        shutil.copyfile(REPO / 'linux/patches/blastem-linux-cpuid.patch', changes / 'blastem-linux-cpuid.patch')
        shutil.copyfile(REPO / 'linux/engine-licenses/toolchain-llvm-runtime-LICENSE.txt', target / 'toolchain-llvm-runtime-LICENSE.txt')
    for name in names:
        source = Path(licenses) / name
        if not source.is_file() or sha256(source) != WINDOWS_CORE_FILES['licenses/' + name]['sha256']:
            raise SystemExit(f'{source}: missing or not the reviewed license text')
        shutil.copyfile(source, target / name)
    files = {p.relative_to(folder).as_posix(): {'size': p.stat().st_size, 'sha256': sha256(p)}
             for p in sorted(folder.rglob('*')) if p.is_file()}
    return platform_id, pins, files


def write_pins(pins, files):
    PINS_FILE.write_text(
        '"""Reviewed tracing engines (Windows x64 and Linux x86-64): same pinned sources as the playtest\n'
        'engines plus the trace/patch_*.py hooks, built with tools/build_trace_cores.py.\n'
        'Generated by tools/pin_trace_cores.py; do not edit."""\n'
        'TRACE_CORE_PINS = ' + pprint.pformat(pins, width=110, sort_dicts=True) + '\n'
        'TRACE_CORE_FILES = ' + pprint.pformat(files, width=110, sort_dicts=True) + '\n',
        encoding='utf-8', newline='\n')


def pin(folders, licenses):
    pins, files = current_pins()
    done = []
    for folder in folders:
        platform_id, new_pins, new_files = finish_pack(folder, licenses)
        pins = {sha: row for sha, row in pins.items() if row.get('platform') != platform_id}
        pins.update(new_pins)
        files[platform_id] = new_files
        done.append({'platform': platform_id, 'folder': str(folder), 'engines': len(new_pins), 'files': len(new_files)})
    write_pins(pins, files)
    return done


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folders', type=Path, nargs='+')
    parser.add_argument('--licenses', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({'ok': True, 'pins': str(PINS_FILE), 'packs': pin(args.folders, args.licenses)}, indent=2))
