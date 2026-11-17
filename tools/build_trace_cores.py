"""Build the tracing engines for "Scenes & colors" from the pinned engine sources.

    python tools/build_trace_cores.py --sources CORE-SOURCES.zip --output <new folder>

Each tracing engine is the same pinned source as the playtest engine (the
release CORE-SOURCES.zip, checked by SHA-256) with one hook script from
trace/ applied and -DROMANCER_TRACE defined:

    pinned source  ->  trace/patch_<engine>.py  ->  build  ->  <name>_trace_libretro.dll / .so

Windows x64 needs MSYS2 UCRT64 GCC/G++, GNU make and Python (the same tools as
tools/build_cores.py). Linux x86-64 needs bash, make, patch, binutils and
Python 3.11+; Zig 0.13.0 is the compiler (downloaded once and checked by
SHA-256, or pass --zig), so the engines need only glibc 2.28, exactly like
linux/build_cores_linux.sh.

The output folder receives the libraries and TRACE-BUILD-INFO.json, which
records the hash of every input. tools/pin_trace_cores.py turns that folder
into the trace-cores pack and writes the release pins. Rebuilt binaries can
differ with toolchain, paths and timestamps; the pins name the reviewed ones.

--generated-cc gcc (Linux only) compiles BlastEm's three generated interpreter
sources, m68k.c, sh2.c and z80.c (about 1.9 million, 0.9 million and 0.1
million lines), with the host's GCC; Zig still compiles every other file and
links, and the glibc 2.28 check still applies to the finished library. Use it
on WSL1, where Zig's clang spends hours on those files, most of it in
memory-management system calls (measured: m68k.c unfinished after two hours,
against six minutes with GCC). The choice is recorded in TRACE-BUILD-INFO.json.

--only rebuilds some engines (ids: gb, nes, snes, snes-dsp4, genesis); with
--update they replace those engines in an existing output folder.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import zipfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from romancer.core_pins import WINDOWS_CORE_FILES, WINDOWS_CORE_PINS

REPO = Path(__file__).resolve().parents[1]
TRACE = REPO / 'trace'
HEADER = 'romancer_trace.h'
MARKER = b'romancer_trace_version'
BUILD_INFO = 'TRACE-BUILD-INFO.json'
# Engine id (as in core_pins) -> hook script, library base name and the systems it traces.
# The base names differ from the playtest engines' so the two can never be mistaken for each other.
TRACE_ENGINES = {
    'gb': {'patch': 'patch_gambatte.py', 'base': 'gambatte_trace_libretro', 'systems': ['gb', 'gbc']},
    'nes': {'patch': 'patch_fceumm.py', 'base': 'fceumm_trace_libretro', 'systems': ['nes']},
    'snes': {'patch': 'patch_bsnes.py', 'base': 'bsnes_mercury_balanced_trace_libretro', 'systems': ['snes']},
    'snes-dsp4': {'patch': 'patch_bsnes.py', 'base': 'bsnes_mercury_dsp4_trace_libretro', 'systems': ['snes']},
    'genesis': {'patch': 'patch_blastem.py', 'base': 'blastem_trace_libretro', 'systems': ['genesis', 'sms']},
}
ZIG_URL = 'https://ziglang.org/download/0.13.0/zig-linux-x86_64-0.13.0.tar.xz'
ZIG_SHA256 = 'd45312e61ebcc48032b77bc4cf7fd6915c11fa16e4aad116b66c9468211230ea'
GLIBC_FLOOR = (2, 28)
WRAPPER = '''#!/usr/bin/env bash
# Pin the glibc floor and drop GNU-ld-only flags zig's linker rejects.
args=()
for a in "$@"; do case "$a" in -Wl,-no-undefined|-Wl,--no-undefined|-Wl,-z,defs|-static-libgcc|-static-libstdc++|-Wl,--as-needed) ;; *) args+=("$a");; esac; done
exec "{zig}" {mode} -target x86_64-linux-gnu.2.28 "${{args[@]}}" ${{ZCC_EXTRA:-}}
'''


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def library_suffix(platform_id):
    return '.dll' if platform_id == 'windows-amd64' else '.so'


def host_platform():
    return 'windows-amd64' if os.name == 'nt' else 'linux-x86_64'


def check_sources(archive):
    expected = WINDOWS_CORE_FILES['CORE-SOURCES.zip']   # one source archive serves both platforms
    if Path(archive).stat().st_size != expected['size'] or sha256(archive) != expected['sha256']:
        raise ValueError('source archive differs from the release pin (CORE-SOURCES.zip)')
    return expected['sha256']


def extract_engine(archive, directory, destination):
    """Extract one engine's source folder from the pinned archive into a fresh `destination`."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    prefix = directory + '/'
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            name = item.filename
            if not name.startswith(prefix) or item.is_dir():
                continue
            if '..' in name.split('/') or '\\' in name or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('invalid source archive member')
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(item))
    if not (destination / directory).is_dir():
        raise ValueError('source archive lacks ' + directory)
    return destination / directory


def apply_hooks(script, tree, log):
    """Run a trace/patch_*.py script; it must exit 0 and end with its "... hooks applied" line."""
    done = subprocess.run([sys.executable, '-B', str(TRACE / script), str(tree)], capture_output=True, text=True)
    log.write((done.stdout + done.stderr).encode('utf-8', 'replace'))
    lines = done.stdout.strip().splitlines()
    if done.returncode != 0 or not lines or not lines[-1].endswith('hooks applied'):
        raise ValueError(f'{script} did not apply: ' + (done.stderr.strip() or done.stdout.strip() or 'no output')[-600:])


class Toolchain:
    """Runs make with the platform's compiler; `flags` reach every compile."""

    def __init__(self, platform_id, work, include, *, msys=None, zig=None, jobs=3, generated_cc=None):
        self.platform = platform_id
        self.generated_cc = None
        self.jobs = str(jobs)
        self.flags = f'-DROMANCER_TRACE -I{include.as_posix()}'
        self.env = os.environ.copy()
        if platform_id == 'windows-amd64':
            msys = Path(msys).absolute()
            self.bin = msys / 'ucrt64/bin'
            self.make = str(msys / 'usr/bin/make.exe')
            self.strip = str(self.bin / 'strip.exe')
            self.env['PATH'] = os.pathsep.join([str(self.bin), str(msys / 'usr/bin'), self.env.get('PATH', '')])
            self.env['MSYSTEM'] = 'MINGW64'   # selects the Windows branch of the makefiles; the compiler is UCRT64 GCC
            self.env['PYTHON'] = shlex.quote(sys.executable.replace('\\', '/'))
            version = subprocess.run([str(self.bin / 'gcc.exe'), '--version'], capture_output=True, text=True, check=True)
            self.description = 'MSYS2 UCRT64 ' + version.stdout.splitlines()[0].strip()
        else:
            zig = Path(zig) if zig else fetch_zig()
            tools = work / 'bin'
            tools.mkdir(parents=True, exist_ok=True)
            for name, mode in (('zcc', 'cc'), ('zcxx', 'c++')):
                (tools / name).write_text(WRAPPER.format(zig=zig, mode=mode), encoding='utf-8', newline='\n')
            (tools / 'zar').write_text(f'#!/bin/sh\nexec "{zig}" ar "$@"\n', encoding='utf-8', newline='\n')
            for tool in tools.iterdir():
                tool.chmod(0o755)
            self.make, self.strip = 'make', 'strip'
            self.env['PATH'] = str(tools) + os.pathsep + self.env.get('PATH', '')
            self.description = 'zig 0.13.0 (clang/LLVM 18) -target x86_64-linux-gnu.2.28'
            if generated_cc:
                version = subprocess.run([generated_cc, '--version'], capture_output=True, text=True, check=True)
                self.generated_cc = generated_cc
                self.generated_cc_version = version.stdout.splitlines()[0].strip()

    def run(self, args, cwd, log, extra=''):
        env = dict(self.env)
        if self.platform != 'windows-amd64':
            env['ZCC_EXTRA'] = (self.flags + ' ' + extra).strip()
        log.write(('\n$ ' + ' '.join(args) + '\n').encode())
        log.flush()
        subprocess.run([self.make if args[0] == 'make' else args[0], *args[1:]], cwd=cwd, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)

    def compilers(self, extra=''):
        """make variables that select the compiler and carry the tracing flags."""
        if self.platform == 'windows-amd64':
            flags = (self.flags + ' ' + extra).strip()
            return [f'CC=gcc {flags}', f'CXX=g++ {flags}']
        return ['CC=zcc', 'CXX=zcxx', 'AR=zar']


def fetch_zig():
    import tarfile
    import urllib.request
    cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'romancer-build'
    zig = cache / 'zig-linux-x86_64-0.13.0/zig'
    if not zig.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        archive = cache / 'zig.tar.xz'
        with urllib.request.urlopen(ZIG_URL, timeout=120) as response, archive.open('wb') as stream:
            shutil.copyfileobj(response, stream)
        if sha256(archive) != ZIG_SHA256:
            archive.unlink()
            raise ValueError('Zig download differs from its pinned SHA-256')
        # Python's tarfile also works on kernels where GNU tar's newer syscalls do not (WSL1).
        with tarfile.open(archive) as tar:
            tar.extractall(cache, filter='tar')
    return zig


def build_engine(engine, tree, tool, log):
    """Build one patched tree; returns the library the makefile produced."""
    unix = tool.platform != 'windows-amd64'
    jobs = '-j' + tool.jobs
    pin = WINDOWS_CORE_PINS[engine]
    made = pin['file'].removesuffix('.dll') + library_suffix(tool.platform)
    if engine == 'gb':
        link = [] if unix else ['LDFLAGS=-static -lws2_32']
        tool.run(['make', '-f', 'Makefile.libretro', 'platform=' + ('unix' if unix else 'win'), *tool.compilers(), *link, jobs], tree, log)
    elif engine == 'nes':
        link = [] if unix else ['LDFLAGS=-static']
        tool.run(['make', '-f', 'Makefile.libretro', 'platform=' + ('unix' if unix else 'win'), *tool.compilers(), *link, jobs], tree, log)
    elif engine in ('snes', 'snes-dsp4'):
        if not unix:
            # Same UCRT compatibility change as the playtest build (tools/build_cores.py).
            header = tree / 'nall/platform.hpp'
            text = header.read_text(encoding='utf-8')
            old = '  #undef  __MSVCRT_VERSION__\n  #define __MSVCRT_VERSION__ 0x0601\n'
            if text.count(old) != 1:
                raise ValueError('SNES UCRT compatibility patch precondition differs')
            header.write_text(text.replace(old, ''), encoding='utf-8', newline='\n')
        dsp4 = ['-DROMANCER_DSP4_STATE'] if engine == 'snes-dsp4' else []
        target = ['TARGET=' + made] if engine == 'snes-dsp4' else []
        if unix:
            includes = ['EXTRA_INCLUDES=' + ' '.join(dsp4)] if dsp4 else []
            tool.run(['make', 'platform=unix', 'PROFILE=balanced', *tool.compilers(), *target, *includes, jobs], tree, log)
        else:
            # The hooks are plain C symbols; export them all beside the retro_* entry points.
            tool.run(['make', 'platform=win', 'PROFILE=balanced', 'CC=gcc', 'CXX=g++', 'LIBS=-static -Wl,--export-all-symbols',
                      *target, 'EXTRA_INCLUDES=' + ' '.join([tool.flags, *dsp4]), jobs], tree, log)
    elif engine == 'genesis':
        # The hooks live in the generated 68000/Z80 interpreters (NEW_CORE=1). ABI=generic keeps the
        # x86 JIT helpers, which the interpreter build leaves out, from being referenced.
        for generated in ('m68k.c', 'm68k.h', 'z80.c', 'z80.h'):
            (tree / generated).unlink(missing_ok=True)
        extra = ''
        if unix:
            # Same two Linux steps as linux/build_cores_linux.sh: drop bare CRs from the embedded
            # tables, and read CPUID through <cpuid.h> (linux/patches/blastem-linux-cpuid.patch).
            tool.run(['make', '-f', 'Makefile', 'rom.db.c', 'systems.cfg.c'], tree, log)
            for name in ('rom.db.c', 'systems.cfg.c'):
                (tree / name).write_bytes((tree / name).read_bytes().replace(b'\r', b''))
            with (REPO / 'linux/patches/blastem-linux-cpuid.patch').open('rb') as patch:
                subprocess.run(['patch', '-d', str(tree.parent), '-p1', '--binary'], stdin=patch, stdout=log, stderr=subprocess.STDOUT, check=True)
            extra = '-DROMANCER_CPUID_H'
            if tool.generated_cc:
                # The inner make that Makefile.libretro would run, for the three generated interpreters only,
                # with the host compiler. The main build below then finds those objects up to date.
                tool.run(['make', '-f', 'Makefile', *('obj/release/lib/' + name + '.o' for name in ('m68k', 'sh2', 'z80')),
                          'OS=Linux', f'CC={tool.generated_cc} {tool.flags} {extra}', 'CPU=generic', 'LIBRETRO=1',
                          'ABI=generic', 'NEW_CORE=1', 'OPT=-O2', '-j3'], tree, log)
        compilers = tool.compilers()[:1] if not unix else tool.compilers()
        tool.run(['make', '-f', 'Makefile.libretro', *compilers, 'ABI=generic', 'NEW_CORE=1', 'OPT=-O2', jobs], tree, log, extra)
    else:
        raise ValueError('unknown engine ' + engine)
    return tree / made


def glibc_floor(library):
    import re
    dump = subprocess.run(['objdump', '-T', str(library)], capture_output=True, text=True, check=True).stdout
    versions = {tuple(int(part) for part in v.split('.')) for v in re.findall(r'GLIBC_([0-9.]+)', dump)}
    return max(versions) if versions else (0,)


def build(sources, output, *, only=None, update=False, msys='C:/msys64', zig=None, jobs=3, generated_cc=None):
    platform_id = host_platform()
    sources = Path(sources).resolve()
    output = Path(output).absolute()
    engines = [e for e in TRACE_ENGINES if not only or e in only]
    if only and set(only) - set(TRACE_ENGINES):
        raise ValueError('unknown engine: ' + ', '.join(sorted(set(only) - set(TRACE_ENGINES))))
    if output.exists() and not update:
        raise ValueError('choose a new output folder, or pass --update to replace engines in this one')
    source_sha = check_sources(sources)
    work = Path(str(output) + '.work')
    if any(c.isspace() for c in str(work)):
        raise ValueError('the output path must not contain spaces (it is passed to the compiler)')
    output.mkdir(parents=True, exist_ok=True)
    include = work / 'include'
    include.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TRACE / HEADER, include / HEADER)
    if generated_cc and platform_id != 'linux-x86_64':
        raise ValueError('--generated-cc applies to the Linux build only')
    tool = Toolchain(platform_id, work, include, msys=msys, zig=zig, jobs=jobs, generated_cc=generated_cc)
    info_path = output / BUILD_INFO
    info = json.loads(info_path.read_text(encoding='utf-8')) if info_path.is_file() else {}
    if info and (info.get('platform') != platform_id or info.get('core_sources_sha256') != source_sha):
        raise ValueError('the output folder was built for another platform or source archive')
    info = {'schema_version': 1, 'platform': platform_id, 'toolchain': tool.description, 'core_sources_sha256': source_sha,
            'recipe': 'tools/build_trace_cores.py', 'engines': info.get('engines', {})}
    if platform_id == 'linux-x86_64':
        info['glibc_minimum'] = '.'.join(map(str, GLIBC_FLOOR))
    suffix = library_suffix(platform_id)
    for engine in engines:
        spec = TRACE_ENGINES[engine]
        pin = WINDOWS_CORE_PINS[engine]
        print(f'== {engine}: {pin["name"]} + trace/{spec["patch"]}', flush=True)
        with (work / (engine + '-build.log')).open('wb') as log:
            tree = extract_engine(sources, pin['source_directory'], work / engine)
            apply_hooks(spec['patch'], tree, log)
            built = build_engine(engine, tree, tool, log)
            subprocess.run([tool.strip, '--strip-unneeded', str(built)], stdout=log, stderr=subprocess.STDOUT, check=True)
        if MARKER not in built.read_bytes():
            raise ValueError(f'{engine}: the built library has no tracing entry points')
        if platform_id == 'linux-x86_64' and glibc_floor(built) > GLIBC_FLOOR:
            raise ValueError(f'{engine}: needs a newer glibc than {info["glibc_minimum"]}')
        target = output / (spec['base'] + suffix)
        shutil.copyfile(built, target)
        info['engines'][engine] = {'file': target.name, 'sha256': sha256(target), 'size': target.stat().st_size,
                                   'patch': 'trace/' + spec['patch'], 'patch_sha256': sha256(TRACE / spec['patch']),
                                   'header_sha256': sha256(TRACE / HEADER)}
        if engine == 'genesis' and tool.generated_cc:
            info['engines'][engine]['generated_interpreters_compiler'] = tool.generated_cc_version
        info_path.write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(f'   {target.name}  {target.stat().st_size} bytes  {info["engines"][engine]["sha256"][:16]}', flush=True)
    return info


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sources', type=Path, required=True, help='the release CORE-SOURCES.zip')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', help='comma-separated engine ids')
    parser.add_argument('--update', action='store_true', help='replace engines in an existing output folder')
    parser.add_argument('--msys', type=Path, default=Path('C:/msys64'))
    parser.add_argument('--zig', type=Path, help='an existing Zig 0.13.0 binary (Linux)')
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--generated-cc', help="host C compiler for BlastEm's generated m68k.c, sh2.c and z80.c (Linux; see above)")
    args = parser.parse_args()
    result = build(args.sources, args.output, only=args.only.split(',') if args.only else None, update=args.update,
                   msys=args.msys, zig=args.zig, jobs=args.jobs, generated_cc=args.generated_cc)
    print(json.dumps({'ok': True, 'output': str(args.output), 'engines': sorted(result['engines'])}))
