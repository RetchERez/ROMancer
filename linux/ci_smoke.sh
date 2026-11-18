#!/usr/bin/env bash
# Build the Linux package from this checkout and run it the way a user would.
#
#   linux/ci_smoke.sh <released-linux-archive> <new-work-dir>
#
# <released-linux-archive>  a published ROMancer-v*-Linux-x86_64.tar.gz. Its engines, engine
#                           sources, licenses and tracing engines are reused unchanged; they
#                           must match the pins in this checkout. The app, launcher and
#                           Python runtime come from this checkout and the pinned downloads.
# <new-work-dir>            must not exist yet
#
# Steps: package (linux/package_linux.sh), check the engine pins did not move, extract the
# new archive into a folder with a space and a non-ASCII letter, ROMancer.sh --check, the
# playtest-engine and tracing-engine acceptance tools with the packaged Python, then start
# the server with ROMancer.sh --no-browser, call the local API and stop it again.
# Used by .github/workflows/ci.yml; works the same on any x86-64 Linux with bash, git,
# curl and python3.
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd -P)"
DONOR="$(readlink -f "$1")"; WORK="$(readlink -m "$2")"
[ -f "$DONOR" ] || { echo "no such archive: $1" >&2; exit 2; }
[ ! -e "$WORK" ] || { echo "choose a new work directory" >&2; exit 2; }
mkdir -p "$WORK/donor" "$WORK/engines" "$WORK/out"
# Python's tarfile also works on kernels where GNU tar's newer syscalls do not (WSL1).
untar() { python3 -c 'import sys,tarfile;tarfile.open(sys.argv[1]).extractall(sys.argv[2],filter="tar")' "$1" "$2"; }

echo "== reuse the released engines"
untar "$DONOR" "$WORK/donor"
OLD="$(echo "$WORK"/donor/ROMancer-v*-Linux-x86_64/"ROMancer Files"/Runtime)"
[ -d "$OLD/cores" ] && [ -d "$OLD/trace-cores" ] || { echo "the archive has no engines" >&2; exit 1; }
cp "$OLD"/cores/*_libretro.so "$WORK/engines/"
cp "$OLD/cores/LINUX-ENGINES.json" "$WORK/engines/BUILD-INFO.json"

echo "== package"
PINS="$REPO/romancer/core_pins_linux.py"; cp "$PINS" "$WORK/core_pins_linux.before"
bash "$REPO/linux/package_linux.sh" "$WORK/engines" "$OLD/cores" "$WORK/out" "$OLD/trace-cores"
cmp "$PINS" "$WORK/core_pins_linux.before" || { echo "the released engines differ from romancer/core_pins_linux.py" >&2; exit 1; }

VERSION="$(python3 -c 'import re,sys;print(re.search(r"ROMANCER_VERSION = \"([^\"]+)\"",open(sys.argv[1]).read()).group(1))' "$REPO/romancer/__init__.py")"
NAME="ROMancer-v$VERSION-Linux-x86_64"
TEST="$WORK/pkg test é"; mkdir -p "$TEST"
untar "$WORK/out/$NAME.tar.gz" "$TEST"
RT="$TEST/$NAME/ROMancer Files/Runtime"; PY="$RT/python/bin/python3"
unset ROMANCER_TRACE_CORES ROMANCER_WORKSPACE

echo "== launcher --check"
PROBE="$("$TEST/$NAME/ROMancer.sh" --check)"; echo "$PROBE"
"$PY" -I -c 'import json,sys;p=json.loads(sys.argv[1]);sys.exit(0 if p["product"]=="ROMancer" and p["version"]==sys.argv[2] else "version differs")' "$PROBE" "$VERSION"
cmp "$TEST/$NAME/README.txt" "$REPO/linux/README-LINUX.txt"
cmp "$RT/app/README.txt" "$REPO/README.txt"

echo "== playtest engines"
"$PY" -I -B "$RT/app/tools/verify_engines.py" --workspace "$WORK/engines-ws" --output "$WORK/engines.json" > /dev/null 2> "$WORK/engines.stderr.log" \
    || { tail -n 30 "$WORK/engines.stderr.log" >&2; exit 1; }
"$PY" -I -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1]))["ok"] else "playtest engines failed")' "$WORK/engines.json"

echo "== tracing engines"
"$PY" -I -B "$RT/app/tools/verify_trace_engines.py" --workspace "$WORK/trace-ws" --output "$WORK/trace.json" > /dev/null 2> "$WORK/trace.stderr.log" \
    || { tail -n 30 "$WORK/trace.stderr.log" >&2; exit 1; }
"$PY" -I - "$WORK/trace.json" "$VERSION" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
ok = (r['ok'] and r['packaged_release'] and r['version'] == sys.argv[2] and len(r['systems']) == 6
      and all(s['pinned'] and s['scenes'] for s in r['systems']))
print(', '.join(f"{s['system']}: {s['scenes']} scene(s)" for s in r['systems']))
sys.exit(0 if ok else 'tracing engines failed')
PY

echo "== start, call the local API, stop"
WS="$WORK/ws"
"$TEST/$NAME/ROMancer.sh" --no-browser --workspace "$WS"
SERVER="$("$PY" -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["pid"])' "$WS/connection.json")"
trap 'kill "$SERVER" 2>/dev/null || true' EXIT
"$PY" -I -B - "$WS/connection.json" "$VERSION" "$RT/app" <<'PY'
import json, sys, urllib.request
from pathlib import Path
from urllib.parse import urlsplit
c = json.load(open(sys.argv[1], encoding='utf-8'))
u = urlsplit(c['url']); base = f'http://127.0.0.1:{u.port}'
token = u.fragment.replace('token=', '', 1)
def call(operation, **parameters):
    req = urllib.request.Request(base + '/api/call', method='POST',
        data=json.dumps({'operation': operation, 'parameters': parameters}).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    return json.load(urllib.request.urlopen(req, timeout=30))
caps = call('system.capabilities')
assert caps['ok'] and caps['product'] == 'ROMancer' and caps['version'] == sys.argv[2], caps
page = urllib.request.urlopen(base + '/', timeout=30).read()
assert b'ROMancer' in page, 'main page'
app = Path(sys.argv[3])
for name in ('index.html', 'guide.pdf'):
    served = urllib.request.urlopen(base + '/user-guide/' + name, timeout=30).read()
    assert served == (app / 'user-guide' / name).read_bytes(), name
print('server', caps['version'], 'answered; main page and guide served')
PY
kill "$SERVER"; trap - EXIT
for _ in $(seq 1 50); do kill -0 "$SERVER" 2>/dev/null || break; sleep 0.1; done
! kill -0 "$SERVER" 2>/dev/null || { echo "the server did not stop" >&2; exit 1; }

echo "OK: $NAME built and ran on $(uname -sr), glibc $(getconf GNU_LIBC_VERSION | cut -d' ' -f2)"
