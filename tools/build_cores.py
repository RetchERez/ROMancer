"""Rebuild the separately licensed engines from their pinned source archive.

Requires Windows x64, MSYS2 UCRT64 GCC/G++, GNU make, CMake and Ninja.
Output hashes can differ with the toolchain; this does not replace release pins.
"""
import argparse
import hashlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import zipfile

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.install_windows import safe_name
from romancer.core_pins import CORE_FILES,CORE_PINS

SNES_MAKE = ['make','platform=win','PROFILE=balanced','CC=gcc','CXX=g++','LIBS=-static','-j3']

MAKE_RECIPES={
    'nes':['make','-f','Makefile.libretro','platform=win','CC=gcc','CXX=g++','-j3'],
    'snes':SNES_MAKE,
    'snes-dsp4':[*SNES_MAKE,'TARGET=bsnes_mercury_dsp4_libretro.dll','EXTRA_INCLUDES=-DROMANCER_DSP4_STATE'],
    'genesis':['make','-f','Makefile.libretro','CC=gcc','OPT=-O2 -flto=4','-j4'],
    'gb':['make','-f','Makefile.libretro','platform=win','CC=gcc','CXX=g++','LDFLAGS=-static -lws2_32','-j3'],
}
GBC_CONFIG = ['cmake','-S','.','-B','build-romancer','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
    '-DBUILD_LIBRETRO=ON','-DBUILD_QT=OFF','-DBUILD_SDL=OFF','-DBUILD_SHARED=OFF',
    '-DBUILD_STATIC=OFF','-DSKIP_LIBRARY=ON','-DDISABLE_DEPS=ON','-DENABLE_SCRIPTING=OFF',
    '-DUSE_PTHREADS=OFF','-DCMAKE_SHARED_LINKER_FLAGS=-static-libgcc -static-libstdc++',
    '-DM_CORE_GBA=OFF','-DM_CORE_GB=ON']


def extract_sources(archive,destination):
    archive=Path(archive);destination=Path(destination).absolute()
    expected=CORE_FILES.get('CORE-SOURCES.zip')
    if not expected or archive.stat().st_size!=expected['size']:raise ValueError('source archive size differs from release pin')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=expected['sha256']:raise ValueError('source archive hash differs from release pin')
    if destination.exists():raise ValueError('choose a new build directory')
    # Validate the entire inventory before publishing any source files.
    with zipfile.ZipFile(archive) as z:
        names=set();total=0
        for item in z.infolist():
            name=safe_name(item.filename);total+=item.file_size
            if item.is_dir() or name.casefold() in names or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('invalid source archive member')
            if item.file_size>32*1024**2 or total>256*1024**2 or len(names)>=10000:raise ValueError('source archive budget exceeded')
            names.add(name.casefold())
        destination.mkdir(parents=True)
        for item in z.infolist():
            target=destination/item.filename;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(item))
    return destination


def rebuild(archive, destination, msys):
    if os.name != 'nt':
        raise ValueError('this recipe builds Windows x64 engines; use upstream build files for other hosts')
    msys = Path(msys).absolute()
    root = extract_sources(archive, destination)
    paths = [msys / 'ucrt64/bin', msys / 'usr/bin']
    environment = os.environ.copy()
    environment['PATH'] = os.pathsep.join(map(str, paths)) + os.pathsep + environment.get('PATH', '')
    environment['MSYSTEM'] = 'MINGW64'
    environment['PYTHON'] = shlex.quote(sys.executable.replace('\\', '/'))
    tools = {'make': msys / 'usr/bin/make.exe', 'cmake': msys / 'ucrt64/bin/cmake.exe'}

    def run(args, cwd):
        command = [str(tools[args[0]]), *args[1:]]
        with (root / (cwd.name + '-build.log')).open('ab') as output:
            subprocess.run(command, cwd=cwd, env=environment, stdout=output, stderr=subprocess.STDOUT, check=True)
    result = {}
    for system, pin in CORE_PINS.items():
        directory = root / pin['source_directory']
        if system == 'snes':
            header = directory / 'nall/platform.hpp'
            text = header.read_text(encoding='utf-8')
            old = '  #undef  __MSVCRT_VERSION__\n  #define __MSVCRT_VERSION__ 0x0601\n'
            if text.count(old) != 1:
                raise ValueError('SNES UCRT compatibility patch precondition differs')
            header.write_text(text.replace(old, ''), encoding='utf-8', newline='\n')
        if system == 'snes-dsp4':
            # Both SNES DLLs share source. Recompile with the DSP-4 serializer enabled.
            run([*SNES_MAKE,'clean'], directory)
        if system == 'gbc-tilt':
            args = [*GBC_CONFIG, '-DCMAKE_C_COMPILER='+str(paths[0]/'gcc.exe'),
                    '-DCMAKE_CXX_COMPILER='+str(paths[0]/'g++.exe'),
                    '-DCMAKE_MAKE_PROGRAM='+str(paths[0]/'ninja.exe')]
            run(args, directory)
            run(['cmake','--build','build-romancer','--target','mgba_libretro','-j','6'], directory)
            binary = directory / 'build-romancer' / 'mgba_libretro.dll'
        else:
            run(MAKE_RECIPES[system], directory)
            binary = directory / pin['file']
            if system == 'snes':
                # Keep the default output intact when cleaning the shared object tree.
                preserved = root / pin['file']
                binary.replace(preserved)
                binary = preserved
        with binary.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        result[system] = {'path': str(binary), 'sha256': sha, 'matches_release_binary': sha == pin['sha256']}
    (root / 'build-results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--msys',type=Path,default=Path('C:/msys64'))
    args=parser.parse_args();print(json.dumps(rebuild(args.sources,args.output,args.msys),indent=2))
