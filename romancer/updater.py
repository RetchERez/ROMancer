"""Updates: find a newer release on GitHub, download it, check it, and swap it in after ROMancer closes.

The service asks GitHub for the latest release at most once a day (Settings > Check for updates turns this off). When
a newer version exists the window shows it. Update and restart downloads the package for this kind of copy, checks it
against the release's SHA256SUMS, unpacks it beside the current copy, and starts a small helper from the NEW copy's
own Python. The service then stops; the helper waits for it to exit, moves the old files aside, moves the new ones in,
and starts ROMancer again. If anything fails the old files are put back and the old version starts. The next start of
the new version removes the old files.

Projects are never touched: they live in the workspace, outside the program folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from . import ROMANCER_VERSION

REPOSITORY = 'RetchERez/ROMancer'
LATEST_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES_PAGE = f'https://github.com/{REPOSITORY}/releases/latest'
CHECK_EVERY = 24 * 3600                 # seconds between automatic checks
USER_AGENT = 'ROMancer-updater'
MAX_PACKAGE = 1024 ** 3                  # refuse anything larger than 1 GiB
STAGE = '.romancer-update'               # beside the program files: the unpacked new version
PREVIOUS = '.romancer-previous'          # beside the program files: the old version until the new one has started
VERSION_TAG = re.compile(r'v?([0-9]+)\.([0-9]+)\.([0-9]+)')


def version_key(text: str):
    match = VERSION_TAG.fullmatch(str(text).strip())
    return tuple(int(part) for part in match.groups()) if match else None


def newer(candidate: str, current: str = ROMANCER_VERSION) -> bool:
    a, b = version_key(candidate), version_key(current)
    return bool(a and b and a > b)


# ---- what kind of copy this is

def install_kind(app_root: Path | None = None) -> dict:
    """Where ROMancer runs from and how it can be updated.

    windows-portable: <folder>/ROMancer.exe + <folder>/ROMancer Files/Runtime/app
    linux-portable:   <folder>/ROMancer.sh  + <folder>/ROMancer Files/Runtime/app
    windows-installed: <root>/versions/<slot>/app with <root>/active.json (Install ROMancer.cmd)
    source:           anything else (a git checkout); it can only be told about a new version
    """
    app = Path(app_root or Path(__file__).resolve().parents[1]).resolve()
    runtime = app.parent
    if runtime.name == 'Runtime' and runtime.parent.name == 'ROMancer Files':
        folder = runtime.parent.parent
        if (folder / 'ROMancer.exe').is_file():
            return {'kind': 'windows-portable', 'folder': folder, 'runtime': runtime}
        if (folder / 'ROMancer.sh').is_file():
            return {'kind': 'linux-portable', 'folder': folder, 'runtime': runtime}
    if runtime.parent.name == 'versions' and (runtime.parent.parent / 'active.json').is_file():
        return {'kind': 'windows-installed', 'folder': runtime.parent.parent, 'runtime': runtime}
    return {'kind': 'source', 'folder': app, 'runtime': None}


def asset_name(kind: str, version: str) -> str | None:
    if kind in ('windows-portable', 'windows-installed'):
        return f'ROMancer-v{version}-Windows.zip'
    if kind == 'linux-portable':
        return f'ROMancer-v{version}-Linux-x86_64.tar.gz'
    return None


def writable(folder: Path) -> bool:
    try:
        probe = folder / f'.romancer-write-test-{os.getpid()}'
        probe.write_bytes(b'')
        probe.unlink()
        return True
    except OSError:
        return False


# ---- talking to GitHub

def _get(url: str, timeout: float = 20):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_latest(url: str | None = None) -> dict:
    """The newest published release: version, notes, page and the download address of each file."""
    with _get(url or os.environ.get('ROMANCER_UPDATE_URL') or LATEST_URL) as response:
        raw = response.read(2 * 1024 ** 2 + 1)
    if len(raw) > 2 * 1024 ** 2:
        raise ValueError('The release description is too large.')
    data = json.loads(raw.decode('utf-8'))
    key = version_key(data.get('tag_name', ''))
    if not key or data.get('draft') or data.get('prerelease'):
        raise ValueError('The latest release has no version number.')
    assets = {}
    for row in data.get('assets') or []:
        if isinstance(row, dict) and isinstance(row.get('name'), str) and isinstance(row.get('browser_download_url'), str):
            if row['browser_download_url'].startswith(('https://', 'http://127.0.0.1')):
                assets[row['name']] = {'url': row['browser_download_url'], 'size': int(row.get('size') or 0)}
    return {'version': '.'.join(map(str, key)), 'notes': str(data.get('body') or '')[:20000],
            'page': str(data.get('html_url') or RELEASES_PAGE), 'published': str(data.get('published_at') or ''), 'assets': assets}


def parse_sums(text: str) -> dict:
    sums = {}
    for line in text.splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *]?(.+)', line.strip())
        if match:
            sums[match.group(2).strip()] = match.group(1).lower()
    return sums


# ---- the state kept in the workspace

class Updater:
    """One per service. All network work runs on background threads; the window polls status()."""

    def __init__(self, workspace: Path, enabled=lambda: True, busy=lambda: None, app_root: Path | None = None):
        self.workspace = Path(workspace)
        self.enabled = enabled
        self.busy = busy
        self.place = install_kind(app_root)
        self.lock = threading.Lock()
        self.state_path = self.workspace / 'update.json'
        self.task = None                  # 'checking' | 'downloading' | 'unpacking' | 'restarting'
        self.progress = None
        self.error = ''
        self.latest = None
        self.checked = 0.0
        self.ready = None                 # {'version', 'stage'} once unpacked and checked
        self.shutdown = None              # set by the server: stops the service after a reply has gone out
        self._load()
        self.finished = self._finish_previous()

    # state file
    def _load(self):
        try:
            stored = json.loads(self.state_path.read_text(encoding='utf-8'))
            self.checked = float(stored.get('checked') or 0)
            latest = stored.get('latest')
            self.latest = latest if isinstance(latest, dict) and version_key(latest.get('version', '')) else None
            self.applying = stored.get('applying') if isinstance(stored.get('applying'), dict) else None
            self.last_failure = str(stored.get('failure') or '')[:500]
        except (OSError, ValueError, TypeError):
            self.applying, self.last_failure = None, ''

    def _save(self, **extra):
        data = {'checked': self.checked, 'latest': self.latest, 'applying': extra.get('applying'),
                'failure': extra.get('failure', '')}
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.state_path.with_suffix('.tmp')
            temp.write_text(json.dumps(data), encoding='utf-8')
            os.replace(temp, self.state_path)
        except OSError:
            pass

    def _finish_previous(self) -> dict | None:
        """After an update: say how it went, and remove the old files and the download once the new version runs."""
        note = None
        applying = getattr(self, 'applying', None)
        if applying:
            if applying.get('to') == ROMANCER_VERSION:
                note = {'updated': True, 'from': applying.get('from'), 'to': ROMANCER_VERSION}
            else:
                failure = self.last_failure or f'The update to v{applying.get("to")} was not applied; this is still v{ROMANCER_VERSION}.'
                note = {'updated': False, 'to': applying.get('to'), 'message': failure}
            self._save(failure='')
        folder = self.place['folder']
        leftovers = [self.workspace / 'updates']
        if self.place['kind'] != 'source':
            leftovers += [folder / PREVIOUS, folder / STAGE]
        if not _remove(leftovers):
            # the helper that started this version may still be closing (it runs from the update folder)
            def later():
                for _ in range(6):
                    time.sleep(5)
                    if _remove(leftovers):
                        return
            threading.Thread(target=later, name='romancer-update-cleanup', daemon=True).start()
        return note

    # what the window shows
    def status(self) -> dict:
        with self.lock:
            available = bool(self.latest and newer(self.latest['version']))
            kind = self.place['kind']
            can_apply = kind != 'source' and asset_name(kind, self.latest['version'] if self.latest else ROMANCER_VERSION) is not None
            reason = ''
            if available and kind == 'source':
                reason = 'This copy runs from source files. Download the new version from the release page.'
            elif available and kind != 'windows-installed' and not writable(self.place['folder']):
                can_apply, reason = False, 'ROMancer cannot write to its own folder, so it cannot update itself there. Download the new version from the release page.'
            elif available and self.latest and asset_name(kind, self.latest['version']) not in self.latest['assets']:
                can_apply, reason = False, 'The new release has no package for this computer yet. Download it from the release page.'
            return {'ok': True, 'current': ROMANCER_VERSION, 'enabled': bool(self.enabled()), 'kind': kind,
                    'available': available, 'latest': {k: self.latest[k] for k in ('version', 'notes', 'page', 'published')} if self.latest else None,
                    'can_apply': available and can_apply, 'reason': reason, 'task': self.task, 'progress': self.progress,
                    'error': self.error, 'ready': bool(self.ready), 'checked': self.checked, 'finished': self.finished,
                    'busy': self.busy() if available else None}

    def seen_finished(self) -> dict:
        self.finished = None
        return self.status()

    # checking
    def check(self, force: bool = False) -> dict:
        with self.lock:
            due = force or time.time() - self.checked >= CHECK_EVERY
            go = not self.task and due and (force or self.enabled())
            if go:
                self.task, self.error = 'checking', ''
        if go:
            threading.Thread(target=self._check, name='romancer-update-check', daemon=True).start()
        return self.status()

    def _check(self):
        try:
            latest = fetch_latest()
            with self.lock:
                self.latest, self.checked = latest, time.time()
                self._save()
        except Exception as error:      # offline, GitHub down, rate limited: say so, try again next time
            with self.lock:
                self.error = 'Could not check for updates: ' + (str(error) or type(error).__name__)[:200]
        finally:
            with self.lock:
                self.task = None

    # downloading and unpacking
    def start(self) -> dict:
        """Update and restart: download, check and unpack now; restart when nothing is in progress."""
        with self.lock:
            if self.task:
                return {'ok': False, 'error': 'An update step is already running.'}
            if not (self.latest and newer(self.latest['version'])):
                return {'ok': False, 'error': 'There is no newer version.'}
            self.task, self.error, self.progress = 'downloading', '', 0.0
        threading.Thread(target=self._prepare, name='romancer-update', daemon=True).start()
        return self.status()

    def _prepare(self):
        try:
            latest = self.latest
            kind = self.place['kind']
            name = asset_name(kind, latest['version'])
            if not name or name not in latest['assets'] or 'SHA256SUMS' not in latest['assets']:
                raise ValueError('The release does not have a package and checksums for this computer.')
            with _get(latest['assets']['SHA256SUMS']['url']) as response:
                sums = parse_sums(response.read(65536).decode('utf-8', 'replace'))
            expected = sums.get(name)
            if not expected:
                raise ValueError(f'SHA256SUMS does not list {name}.')
            downloads = self.workspace / 'updates'
            downloads.mkdir(parents=True, exist_ok=True)
            package = downloads / name
            self._download(latest['assets'][name], package, expected)
            with self.lock:
                self.task, self.progress = 'unpacking', None
            stage = self._unpack(package, latest['version'])
            with self.lock:
                self.ready = {'version': latest['version'], 'stage': str(stage), 'package': str(package)}
                self.task = None
        except Exception as error:
            with self.lock:
                self.task, self.progress = None, None
                self.error = 'The update could not be prepared: ' + (str(error) or type(error).__name__)[:300]

    def _download(self, asset: dict, target: Path, expected: str):
        part = target.with_suffix(target.suffix + '.part')
        digest = hashlib.sha256()
        done = 0
        with _get(asset['url'], timeout=60) as response, part.open('wb') as stream:
            total = int(response.headers.get('Content-Length') or asset.get('size') or 0)
            if total > MAX_PACKAGE:
                raise ValueError('The package is larger than expected.')
            while chunk := response.read(1024 * 256):
                done += len(chunk)
                if done > MAX_PACKAGE:
                    raise ValueError('The package is larger than expected.')
                digest.update(chunk)
                stream.write(chunk)
                with self.lock:
                    self.progress = (done / total) if total else None
        if digest.hexdigest() != expected:
            part.unlink(missing_ok=True)
            raise ValueError('The download does not match the release checksum. Nothing was changed.')
        os.replace(part, target)

    def _unpack(self, package: Path, version: str) -> Path:
        """Unpack beside the program files (same drive, so moving them in is a rename) and check every file."""
        folder = self.place['folder']
        stage = folder / STAGE
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        new = stage / 'new'
        if package.name.endswith('.zip'):
            with zipfile.ZipFile(package) as archive:
                for entry in archive.infolist():
                    _safe_member(entry.filename)
                archive.extractall(new)
        else:
            with tarfile.open(package, 'r:gz') as archive:
                members = archive.getmembers()
                for entry in members:
                    _safe_member(entry.name)
                    if entry.issym() or entry.islnk() or entry.isdev():
                        if not (entry.issym() and entry.name.startswith(f'ROMancer-v{version}-Linux-x86_64/ROMancer Files/Runtime/python/')):
                            raise ValueError('The package holds a link outside its runtime.')
                archive.extractall(new, filter='tar')
            top = new / f'ROMancer-v{version}-Linux-x86_64'
            if not top.is_dir():
                raise ValueError('The Linux package does not have the expected folder.')
            new = top
        runtime = new / 'ROMancer Files' / 'Runtime'
        launcher = 'ROMancer.exe' if package.name.endswith('.zip') else 'ROMancer.sh'
        if not (new / launcher).is_file() or not (runtime / 'BUNDLE.json').is_file():
            raise ValueError('The package is not a complete ROMancer.')
        manifest = json.loads((runtime / 'BUNDLE.json').read_text(encoding='utf-8'))
        if manifest.get('product') != 'ROMancer' or manifest.get('version') != version:
            raise ValueError('The package says it is a different version.')
        _verify_bundle(runtime, manifest)
        return new

    # restarting
    def apply(self) -> dict:
        """Close and swap: start the helper from the new copy, then stop this service."""
        with self.lock:
            if not self.ready:
                return {'ok': False, 'error': 'The update is not ready yet.'}
            if self.task:
                return {'ok': False, 'error': 'An update step is already running.'}
        busy = self.busy()
        if busy:
            return {'ok': False, 'busy': busy, 'error': busy}
        with self.lock:
            ready, self.task = self.ready, 'restarting'
        try:
            command = helper_command(self.place, Path(ready['stage']), os.getpid(), self.state_path)
            self._save(applying={'from': ROMANCER_VERSION, 'to': ready['version']})
            spawn(command)
        except Exception as error:
            with self.lock:
                self.task = None
                self.error = 'The update could not start: ' + (str(error) or type(error).__name__)[:300]
            self._save()
            return {'ok': False, 'error': self.error}
        if self.shutdown:
            threading.Timer(1.5, self.shutdown).start()     # let the reply and the window's last poll go out first
        return {'ok': True, 'restarting': True, 'version': ready['version']}


def _remove(paths) -> bool:
    for path in paths:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    return not any(path.exists() for path in paths)


def _safe_member(name: str):
    parts = name.replace('\\', '/').split('/')
    if name.startswith(('/', '\\')) or ':' in parts[0] or '..' in parts:
        raise ValueError('The package holds an unsafe file name.')


def _verify_bundle(runtime: Path, manifest: dict):
    """Every file the package lists is present with its size and checksum, and nothing extra is in the runtime."""
    listed = set()
    for row in manifest.get('files') or []:
        path = runtime / row['path']
        listed.add(row['path'])
        if not path.is_file() or path.stat().st_size != row['size']:
            raise ValueError('A file of the new version is missing or has the wrong size: ' + row['path'])
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != row['sha256']:
            raise ValueError('A file of the new version does not match its checksum: ' + row['path'])
    if not listed:
        raise ValueError('The package lists no files.')


def helper_python(stage: Path) -> Path:
    """A copy of the new version's Python outside the files that get moved: Windows cannot move a folder whose
    python.exe is running."""
    source = stage / 'ROMancer Files' / 'Runtime' / 'python'
    if not source.is_dir():
        raise ValueError('The new version has no Python.')
    copy = stage.parent / 'helper-python'
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(source, copy, symlinks=True)
    for candidate in (copy / 'python.exe', copy / 'bin' / 'python3'):
        if candidate.is_file():
            return candidate
    raise ValueError('The new version has no Python.')


def helper_command(place: dict, stage: Path, pid: int, state: Path) -> list:
    helper = stage.parent / 'apply_update.py'
    shutil.copyfile(Path(__file__).with_name('update_helper.py'), helper)
    command = [str(helper_python(stage)), '-I', '-B', str(helper), '--kind', place['kind'], '--folder', str(place['folder']),
               '--new', str(stage), '--pid', str(pid), '--log', str(stage.parent / 'update.log'),
               '--state', str(state), '--workspace', str(state.parent)]
    return command


def spawn(command: list):
    # The helper starts in its own folder, outside the files it moves: Windows will not move a folder that a running
    # program has as its current folder (the service runs from inside the program files).
    where = str(Path(command[3]).parent)
    if os.name == 'nt':
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(command, cwd=where, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(command, cwd=where, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
