#!/usr/bin/env bash
# Rebuild the six reviewed engines for Linux x86-64 from the release CORE-SOURCES.zip.
#
#   linux/build_cores_linux.sh <CORE-SOURCES.zip> <new-output-dir>
#
# Needs: bash, make, cmake, patch, python3, curl, binutils (strip/objdump).
# Uses Zig 0.13.0 as a cross compiler so the engines only require glibc 2.28
# (Ubuntu 20.04+, Debian 10+, Fedora 29+, SteamOS 3). Zig is downloaded once and
# verified by SHA-256. Rebuilt binaries can differ with toolchain and paths; the
# shipped identities are pinned in romancer/core_pins_linux.py.
set -euo pipefail

SOURCES="$(readlink -f "$1")"; OUT="$(readlink -m "$2")"
[ ! -e "$OUT" ] || { echo "choose a new output directory" >&2; exit 1; }
WORK="$OUT.work"; rm -rf "$WORK"; mkdir -p "$WORK/bin" "$OUT"
JOBS="${JOBS:-$(nproc)}"

ZIG_URL="https://ziglang.org/download/0.13.0/zig-linux-x86_64-0.13.0.tar.xz"
ZIG_SHA="d45312e61ebcc48032b77bc4cf7fd6915c11fa16e4aad116b66c9468211230ea"
ZIG_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/romancer-build"; mkdir -p "$ZIG_CACHE"
if [ ! -x "$ZIG_CACHE/zig-linux-x86_64-0.13.0/zig" ]; then
    curl -fsSL -o "$ZIG_CACHE/zig.tar.xz" "$ZIG_URL"
    echo "$ZIG_SHA  $ZIG_CACHE/zig.tar.xz" | sha256sum -c --quiet -
    # Python's tarfile also works on kernels where GNU tar's newer syscalls do not (WSL1).
    python3 -c 'import sys,tarfile;tarfile.open(sys.argv[1]).extractall(sys.argv[2],filter="tar")' "$ZIG_CACHE/zig.tar.xz" "$ZIG_CACHE"
fi
ZIG="$ZIG_CACHE/zig-linux-x86_64-0.13.0/zig"

# Compiler wrappers: pin the glibc floor and drop GNU-ld-only flags zig's linker rejects.
for pair in "zcc:cc" "zcxx:c++"; do
    cat > "$WORK/bin/${pair%%:*}" <<W
#!/usr/bin/env bash
args=()
for a in "\$@"; do case "\$a" in -Wl,-no-undefined|-Wl,--no-undefined|-Wl,-z,defs|-static-libgcc|-static-libstdc++|-Wl,--as-needed) ;; *) args+=("\$a");; esac; done
exec "$ZIG" ${pair#*:} -target x86_64-linux-gnu.2.28 "\${args[@]}" \${ZCC_EXTRA:-}
W
done
printf '#!/bin/sh\nexec "%s" ar "$@"\n' "$ZIG" > "$WORK/bin/zar"
chmod +x "$WORK/bin/"*
export PATH="$WORK/bin:$PATH"
M=(CC=zcc CXX=zcxx AR=zar)

python3 -c 'import sys,zipfile;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$SOURCES" "$WORK/src"
S="$WORK/src"
log() { echo "== $1"; }

log "nes (FCEUmm)"
make -C "$S/fceumm" -f Makefile.libretro platform=unix "${M[@]}" -j"$JOBS" > "$WORK/nes.log" 2>&1
cp "$S/fceumm/fceumm_libretro.so" "$OUT/"

log "snes (bsnes-mercury balanced)"
make -C "$S/bsnes-mercury" platform=unix PROFILE=balanced "${M[@]}" -j"$JOBS" > "$WORK/snes.log" 2>&1
cp "$S/bsnes-mercury/bsnes_mercury_balanced_libretro.so" "$OUT/"

log "snes-dsp4 (bsnes-mercury balanced, DSP-4 state)"
make -C "$S/bsnes-mercury" platform=unix PROFILE=balanced "${M[@]}" clean > /dev/null 2>&1
make -C "$S/bsnes-mercury" platform=unix PROFILE=balanced "${M[@]}" TARGET=bsnes_mercury_dsp4_libretro.so \
    EXTRA_INCLUDES=-DROMANCER_DSP4_STATE -j"$JOBS" > "$WORK/dsp4.log" 2>&1
cp "$S/bsnes-mercury/bsnes_mercury_dsp4_libretro.so" "$OUT/"

log "genesis (BlastEm)"
# rom.db and systems.cfg have mixed CRLF endings; clang ends a string literal at a bare CR.
# Generate the embedded C once and drop the CRs (the config parser treats CR as whitespace).
make -C "$S/blastem" -f Makefile rom.db.c systems.cfg.c > "$WORK/genesis.log" 2>&1
sed -i 's/\r//g' "$S/blastem/rom.db.c" "$S/blastem/systems.cfg.c"
# Zig/LLD cannot relocate __builtin_cpu_supports' __cpu_model inside a shared object;
# linux/patches/blastem-linux-cpuid.patch reads the same CPUID bits via <cpuid.h> when ROMANCER_CPUID_H is set.
patch -d "$S" -p1 --binary < "$(dirname "$(readlink -f "$0")")/patches/blastem-linux-cpuid.patch" >> "$WORK/genesis.log"
ZCC_EXTRA=-DROMANCER_CPUID_H make -C "$S/blastem" -f Makefile.libretro "${M[@]}" OPT=-O2 -j"$JOBS" >> "$WORK/genesis.log" 2>&1
cp "$S/blastem/blastem_libretro.so" "$OUT/"

log "gb (Gambatte)"
make -C "$S/gambatte" -f Makefile.libretro platform=unix "${M[@]}" -j"$JOBS" > "$WORK/gb.log" 2>&1
cp "$S/gambatte/gambatte_libretro.so" "$OUT/"

log "gbc-tilt (mGBA, Game Boy only)"
cmake -S "$S/mgba" -B "$S/mgba/build-romancer" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER="$WORK/bin/zcc" -DCMAKE_CXX_COMPILER="$WORK/bin/zcxx" \
    -DBUILD_LIBRETRO=ON -DBUILD_QT=OFF -DBUILD_SDL=OFF -DBUILD_SHARED=OFF -DBUILD_STATIC=OFF \
    -DSKIP_LIBRARY=ON -DDISABLE_DEPS=ON -DENABLE_SCRIPTING=OFF -DUSE_PTHREADS=OFF \
    -DM_CORE_GBA=OFF -DM_CORE_GB=ON > "$WORK/gbc.log" 2>&1
cmake --build "$S/mgba/build-romancer" --target mgba_libretro -j "$JOBS" >> "$WORK/gbc.log" 2>&1
cp "$S/mgba/build-romancer/mgba_libretro.so" "$OUT/mgba_gbc_libretro.so"

log "strip and check"
for f in "$OUT"/*.so; do
    strip --strip-unneeded "$f"
    floor="$(objdump -T "$f" | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1)"
    if [ "$(printf '%s\nGLIBC_2.28\n' "$floor" | sort -V | tail -1)" != "GLIBC_2.28" ]; then
        echo "$(basename "$f") needs $floor (> 2.28)" >&2; exit 1
    fi
    echo "$(basename "$f")  $floor  $(sha256sum "$f" | cut -c1-16)"
done
python3 - "$OUT" "$SOURCES" <<'PY'
import hashlib, json, sys
from pathlib import Path
out, src = Path(sys.argv[1]), Path(sys.argv[2])
info = {"schema_version": 1, "platform": "linux-x86_64", "glibc_minimum": "2.28",
        "toolchain": "zig 0.13.0 (clang/LLVM 18) -target x86_64-linux-gnu.2.28",
        "core_sources_sha256": hashlib.sha256(src.read_bytes()).hexdigest()}
(out / "BUILD-INFO.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
PY
echo "Engines are in $OUT (build logs in $WORK)"
