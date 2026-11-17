#!/usr/bin/env bash
# ROMancer portable launcher for Linux x86-64 — By RetchEWretched (MIT)
# Usage: ./ROMancer.sh [--check] [--no-browser] [--workspace PATH] [--install-desktop]
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"
RUNTIME="$HERE/ROMancer Files/Runtime"
APP="$RUNTIME/app"
PY="$RUNTIME/python/bin/python3"

CHECK=0; NO_BROWSER=0; INSTALL_DESKTOP=0
WORKSPACE="${ROMANCER_WORKSPACE:-${XDG_DATA_HOME:-$HOME/.local/share}/ROMancer/workspace}"
while [ $# -gt 0 ]; do
    case "$1" in
        --check) CHECK=1; NO_BROWSER=1 ;;
        --no-browser) NO_BROWSER=1 ;;
        --workspace) shift; [ $# -gt 0 ] || { echo "--workspace needs a path" >&2; exit 2; }; WORKSPACE="$(readlink -m "$1")" ;;
        --install-desktop) INSTALL_DESKTOP=1 ;;
        -h|--help) sed -n '2,3p' "$0"; exit 0 ;;
        *) echo "Use ROMancer.sh, --check, --no-browser, --workspace <path> or --install-desktop." >&2; exit 2 ;;
    esac
    shift
done

fail() {
    echo "ROMancer: $1" >&2
    if [ "$NO_BROWSER" = 0 ] && [ -z "${TERM:-}" ]; then
        command -v zenity >/dev/null 2>&1 && zenity --error --title=ROMancer --text="$1" 2>/dev/null || true
        command -v kdialog >/dev/null 2>&1 && kdialog --title ROMancer --error "$1" 2>/dev/null || true
    fi
    exit 1
}

[ -x "$PY" ] && [ -f "$APP/romancer/__init__.py" ] || fail "Extract the full archive, then run ROMancer.sh from the extracted folder."
[ "$(uname -m)" = "x86_64" ] || fail "This build is for 64-bit x86 Linux."

if [ "$INSTALL_DESKTOP" = 1 ]; then
    dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"; mkdir -p "$dir"
    cat > "$dir/romancer.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=ROMancer
Comment=Retro ROM editor for NES, SNES, Genesis, Game Boy and Game Boy Color
Exec="$HERE/ROMancer.sh"
Icon=$RUNTIME/romancer.png
Terminal=false
Categories=Development;Game;
DESKTOP
    echo "Added ROMancer to your application menu: $dir/romancer.desktop"
    exit 0
fi

PROBE="$("$PY" -I -B -c 'import json,sys,PIL;from romancer import ROMANCER_VERSION;print(json.dumps(dict(product="ROMancer",version=ROMANCER_VERSION,python=sys.version.split()[0],pillow=PIL.__version__)))' 2>&1)" \
    || fail "The bundled runtime failed its startup check: $PROBE"
if [ "$CHECK" = 1 ]; then echo "$PROBE"; exit 0; fi
VERSION="$("$PY" -I -c 'import json,sys;print(json.loads(sys.argv[1])["version"])' "$PROBE")"

mkdir -p "$WORKSPACE"
CONNECTION="$WORKSPACE/connection.json"

open_window() {
    local url="$1" launch base
    launch="$("$PY" -I -c 'import uuid;print(uuid.uuid4().hex)')"
    base="${url%%#*}"; base="${base%/}"
    local app_url="$base/?launch=$launch#${url#*#}"
    [ "$NO_BROWSER" = 1 ] && return 0
    local profile; profile="$(dirname "$WORKSPACE")/browser-profile"
    for b in microsoft-edge microsoft-edge-stable google-chrome google-chrome-stable chromium chromium-browser brave-browser vivaldi-stable; do
        if command -v "$b" >/dev/null 2>&1; then
            setsid "$b" --app="$app_url" --user-data-dir="$profile" --no-first-run >/dev/null 2>&1 < /dev/null &
            return 0
        fi
    done
    if command -v xdg-open >/dev/null 2>&1; then setsid xdg-open "$app_url" >/dev/null 2>&1 < /dev/null & return 0; fi
    echo "Open this address in your browser: $app_url"
}

# Reuse a running session of this exact install and version.
if [ -f "$CONNECTION" ]; then
    if EXISTING="$("$PY" -I -B - "$CONNECTION" "$APP" "$VERSION" <<'PY' 2>/dev/null
import json, sys, urllib.request
from urllib.parse import urlsplit
c = json.load(open(sys.argv[1], encoding='utf-8'))
u = urlsplit(c['url'])
if c.get('application_root') != sys.argv[2] or u.scheme != 'http' or u.hostname != '127.0.0.1':
    sys.exit(1)
token = u.fragment.replace('token=', '', 1)
req = urllib.request.Request(f'http://127.0.0.1:{u.port}/api/call', method='POST',
    data=b'{"operation":"system.capabilities","parameters":{}}',
    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
r = json.load(urllib.request.urlopen(req, timeout=2))
if r.get('ok') and r.get('product') == 'ROMancer' and r.get('version') == sys.argv[3]:
    print(c['url'])
else:
    sys.exit(1)
PY
)"; then
        open_window "$EXISTING"
        echo "Reopened the existing local ROMancer session."
        exit 0
    fi
fi

cd "$APP"
setsid "$PY" -I -B -m romancer.workbench_server --workspace "$WORKSPACE" --port 0 --no-browser \
    > "$WORKSPACE/server.log" 2> "$WORKSPACE/server-errors.log" < /dev/null &
PID=$!

URL=""
for _ in $(seq 1 130); do
    kill -0 "$PID" 2>/dev/null || break
    if [ -f "$CONNECTION" ]; then
        URL="$("$PY" -I -c 'import json,sys;c=json.load(open(sys.argv[1]));print(c["url"] if c.get("pid")==int(sys.argv[2]) else "")' "$CONNECTION" "$PID" 2>/dev/null || true)"
        [ -n "$URL" ] && break
    fi
    sleep 0.15
done
if [ -z "$URL" ]; then
    kill "$PID" 2>/dev/null || true
    fail "ROMancer could not start. Details: $WORKSPACE/server-errors.log"
fi
open_window "$URL"
PORT="$("$PY" -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["port"])' "$CONNECTION")"
echo "ROMancer is ready at http://127.0.0.1:$PORT/ — By RetchEWretched"
