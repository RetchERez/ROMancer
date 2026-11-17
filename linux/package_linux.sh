#!/usr/bin/env bash
# Build the portable ROMancer Linux x86-64 archive.
#
#   linux/package_linux.sh <engines-dir> <windows-cores-dir> <output-dir>
#
# <engines-dir>        output of linux/build_cores_linux.sh (six *_libretro.so files)
# <windows-cores-dir>  the Windows release "cores" folder (CORE-SOURCES.zip and licenses are reused unchanged)
# <output-dir>         receives ROMancer-v<version>-Linux-x86_64.tar.gz
#
# Run from a git checkout. Downloads are pinned by SHA-256 and cached in <output-dir>/cache.
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd -P)"
ENGINES="$(readlink -f "$1")"; WINCORES="$(readlink -f "$2")"; OUT="$(readlink -m "$3")"

PY_FILE="cpython-3.14.9+20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.14.9%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PY_SHA="561e91c1cadf30e84aec94d1917384ae3267e5f3e6e135e51fd1578bb19f4064"
PIL_FILE="pillow-12.3.0-cp314-cp314-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
PIL_URL="https://files.pythonhosted.org/packages/5c/44/c85361f65dbe00eea8576ee467c768d25129989efb76e94f205e9ca9bb46/$PIL_FILE"
PIL_SHA="251bf95b67017e27b13d82f5b326234ca62d70f9cf4c2b9032de2358a3b12c7b"

VERSION="$(python3 -c 'import re,sys;print(re.search(r"ROMANCER_VERSION = \"([^\"]+)\"",open(sys.argv[1]).read()).group(1))' "$REPO/romancer/__init__.py")"
NAME="ROMancer-v$VERSION-Linux-x86_64"
STAGE="$OUT/$NAME"; RT="$STAGE/ROMancer Files/Runtime"
mkdir -p "$OUT/cache"; rm -rf "$STAGE"; mkdir -p "$RT"

fetch() { # file url sha
    local f="$OUT/cache/$1"
    if [ ! -f "$f" ]; then curl -fsSL -o "$f.part" "$2"; mv "$f.part" "$f"; fi
    echo "$3  $f" | sha256sum -c --quiet - || { rm -f "$f"; echo "hash mismatch: $1" >&2; exit 1; }
}
fetch "$PY_FILE" "$PY_URL" "$PY_SHA"
fetch "$PIL_FILE" "$PIL_URL" "$PIL_SHA"

echo "== engines: pins and inventory"
for f in fceumm_libretro.so bsnes_mercury_balanced_libretro.so bsnes_mercury_dsp4_libretro.so blastem_libretro.so gambatte_libretro.so mgba_gbc_libretro.so; do
    [ -f "$ENGINES/$f" ] || { echo "missing engine $f" >&2; exit 1; }
done
mkdir -p "$RT/cores/licenses"
cp "$ENGINES"/*_libretro.so "$RT/cores/"
cp "$WINCORES/CORE-SOURCES.zip" "$RT/cores/"
for l in blastem bsnes-mercury fceumm gambatte mgba; do cp "$WINCORES/licenses/$l.txt" "$RT/cores/licenses/"; done
cp "$REPO/linux/engine-licenses/"*.txt "$RT/cores/licenses/"
mkdir -p "$RT/cores/linux-build-patches" && cp "$REPO/linux/patches/"*.patch "$RT/cores/linux-build-patches/"
[ -f "$ENGINES/BUILD-INFO.json" ] && cp "$ENGINES/BUILD-INFO.json" "$RT/cores/LINUX-ENGINES.json"
[ -f "$RT/cores/LINUX-ENGINES.json" ] || { echo "engines dir lacks BUILD-INFO.json (run build_cores_linux.sh)" >&2; exit 1; }
cp "$REPO/linux/ENGINES-NOTICES.txt" "$RT/cores/THIRD_PARTY_NOTICES.txt"
python3 "$REPO/linux/write_linux_pins.py" "$REPO" "$RT/cores"

echo "== app"
mkdir -p "$RT/app"
(cd "$REPO" && git -c safe.directory='*' ls-files -z --cached --others --exclude-standard | grep -zv '^linux/' \
    | xargs -0 -I{} cp --parents -- "{}" "$RT/app/")
rm -rf "$RT/app/node_modules"

echo "== python runtime"
python3 -c 'import sys,tarfile;tarfile.open(sys.argv[1]).extractall(sys.argv[2],filter="tar")' "$OUT/cache/$PY_FILE" "$RT"
SITE="$(echo "$RT"/python/lib/python3.14/site-packages)"
python3 -c 'import sys,zipfile;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$OUT/cache/$PIL_FILE" "$SITE"
chmod +x "$SITE"/PIL/*.so "$SITE"/pillow.libs/*.so* 2>/dev/null || true
printf '../../../../app\n' > "$SITE/romancer-app.pth"
rm -rf "$RT"/python/include "$RT"/python/share "$RT"/python/lib/python3.14/ensurepip "$SITE"/pip "$SITE"/pip-*.dist-info "$RT"/python/bin/pip*
rm -rf "$RT"/python/lib/python3.14/test "$RT"/python/lib/python3.14/idlelib "$RT"/python/lib/python3.14/turtledemo

echo "== launcher and metadata"
cp "$REPO/linux/ROMancer.sh" "$STAGE/"; chmod +x "$STAGE/ROMancer.sh"
cp "$REPO/linux/README-LINUX.txt" "$STAGE/README.txt"
cp "$REPO/LICENSE" "$RT/LICENSE"
"$RT/python/bin/python3" -I -c 'import sys;from PIL import Image;Image.open(sys.argv[1]).save(sys.argv[2])' "$REPO/linux/romancer.ico" "$RT/romancer.png" 2>/dev/null \
    || cp "$REPO/linux/romancer.png" "$RT/romancer.png" 2>/dev/null || true
python3 - "$RT" "$VERSION" "$PY_FILE" "$PY_URL" "$PY_SHA" "$PIL_FILE" "$PIL_URL" "$PIL_SHA" <<'PY'
import json, sys
rt, version, pyf, pyu, pys, pf, pu, ps = sys.argv[1:]
origins = {
    "python": {"file": pyf, "sha256": pys, "url": pyu, "version": "3.14.9",
               "license": "PSF-2.0 and bundled notices (python-build-standalone)"},
    "pillow": {"file": pf, "sha256": ps, "url": pu, "version": "12.3.0", "license": "MIT-CMU and bundled notices"},
}
json.dump(origins, open(f"{rt}/RUNTIME-ORIGINS.json", "w"), indent=2)
bundle = {"schema_version": 1, "product": "ROMancer", "version": version, "release_name": f"ROMancer v{version}",
          "credit": "By RetchEWretched", "platform": "linux-x86_64", "runtime": origins,
          "engines": json.load(open(f"{rt}/cores/CORE-ORIGINS.json"))}
json.dump(bundle, open(f"{rt}/BUNDLE.json", "w"), indent=2)
PY

echo "== smoke test"
"$STAGE/ROMancer.sh" --check

echo "== archive"
(cd "$OUT" && rm -f "$NAME.tar.gz" && python3 - "$NAME" <<'PY'
import os, sys, tarfile
name = sys.argv[1]
def norm(t):
    t.uid = t.gid = 0; t.uname = t.gname = "root"
    if t.isdir():
        t.mode = 0o755
    elif t.isfile():
        # Staging under /mnt/c marks everything executable; keep +x only for ELF files and scripts.
        with open(t.name, "rb") as stream:
            head = stream.read(4)
        t.mode = 0o755 if head == b"\x7fELF" or head[:2] == b"#!" else 0o644
    return t
with tarfile.open(name + ".tar.gz", "w:gz", compresslevel=9) as tar:
    tar.add(name, filter=norm)
PY
)
sha256sum "$OUT/$NAME.tar.gz" | tee "$OUT/$NAME.tar.gz.sha256"
du -h "$OUT/$NAME.tar.gz"
