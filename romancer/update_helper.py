"""Swap in a new version of ROMancer after the old one has closed, then start it. Standard library only.

ROMancer copies this file beside the unpacked new version and runs it with a copy of the new version's Python, so it
never runs from the files it moves. Run as:

    python apply_update.py --kind windows-portable|linux-portable|windows-installed --folder <program folder>
        --new <unpacked new version> --pid <old service> --log <log file> --state <workspace update.json>

Portable copies: each top-level item of the new package (ROMancer.exe or ROMancer.sh, ROMancer Files, README.txt,
ROM Catalog.html) replaces the same item in the program folder; the old ones go to <folder>/.romancer-previous until
the new version has started. Nothing else in the folder is touched. If any step fails, every item is put back and the
old version starts again. Installed copies: the new version is installed beside the old one (its own versions slot)
by the new version's own installer, which keeps the old one for Rollback ROMancer.cmd.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PREVIOUS = '.romancer-previous'
WAIT_FOR_EXIT = 120      # seconds for the old service to stop
RETRY_LOCKED = 60        # seconds to keep retrying a file Windows still holds


def log(path: Path, text: str):
    try:
        with path.open('a', encoding='utf-8') as stream:
            stream.write(time.strftime('%Y-%m-%d %H:%M:%S ') + text + '\n')
    except OSError:
        pass


def alive(pid: int) -> bool:
    if os.name == 'nt':
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)      # SYNCHRONIZE | QUERY_LIMITED
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x102            # WAIT_TIMEOUT: still running
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_exit(pid: int, logfile: Path) -> bool:
    deadline = time.monotonic() + WAIT_FOR_EXIT
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.25)
    log(logfile, f'the old service (process {pid}) did not stop within {WAIT_FOR_EXIT} s')
    return False


def move(source: Path, target: Path):
    """Rename, retrying while Windows still holds a file in the folder (an engine or antivirus closing it)."""
    deadline = time.monotonic() + RETRY_LOCKED
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def swap_portable(folder: Path, new: Path, logfile: Path):
    previous = folder / PREVIOUS
    if previous.exists():
        shutil.rmtree(previous)
    previous.mkdir()
    items = sorted(entry.name for entry in new.iterdir())
    done = []          # (name, old existed)
    try:
        for name in items:
            existed = (folder / name).exists()
            if existed:
                move(folder / name, previous / name)
            done.append((name, existed))
            move(new / name, folder / name)
            log(logfile, f'replaced {name}')
    except Exception as error:
        log(logfile, f'failed while replacing: {error!r}; putting the old files back')
        for name, existed in reversed(done):
            try:
                if (folder / name).exists() and not (new / name).exists():
                    move(folder / name, new / name)          # the new item goes back where it came from
                if existed:
                    move(previous / name, folder / name)
            except Exception as again:
                log(logfile, f'could not put back {name}: {again!r} (the old file is in {previous})')
        raise


def install_new(folder: Path, new: Path, logfile: Path):
    app = new / 'ROMancer Files' / 'Runtime' / 'app'
    sys.path.insert(0, str(app))
    from tools.install_windows import install      # the NEW version's installer
    result = install(new / 'ROMancer Files' / 'Runtime', folder)
    log(logfile, 'installed ' + json.dumps(result))


def relaunch(kind: str, folder: Path, workspace: Path, logfile: Path):
    """Start ROMancer again on the same workspace, the way its own launcher does."""
    window = os.environ.get('ROMANCER_UPDATE_NO_WINDOW') != '1'          # tests start it without a window
    if kind == 'linux-portable':
        command = [str(folder / 'ROMancer.sh'), '--workspace', str(workspace)] + ([] if window else ['--no-browser'])
    else:
        script = folder / 'ROMancer Files' / 'Runtime' / 'Open ROMancer.ps1' if kind == 'windows-portable' else folder / 'Open ROMancer.ps1'
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
        command = [str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
                   '-File', str(script), '-Workspace', str(workspace)] + ([] if window else ['-NoBrowser'])
    log(logfile, 'starting ' + ' '.join(command))
    # What the launcher says goes to a file in the workspace, not the update log: the service it starts inherits the
    # handle and keeps it open while it runs, and a file held open in the update folder stops it being removed.
    output = (workspace / 'update-start.log').open('w', encoding='utf-8')
    if os.name == 'nt':
        # A hidden console, not none: the launcher's Start-Process needs one.
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(command, cwd=str(folder), creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=output, stderr=output)
    else:
        subprocess.Popen(command, cwd=str(folder), start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=output, stderr=output)


def record_failure(state: Path, message: str):
    try:
        data = json.loads(state.read_text(encoding='utf-8'))
        data['failure'] = message[:500]
        state.write_text(json.dumps(data), encoding='utf-8')
    except (OSError, ValueError):
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', required=True, choices=('windows-portable', 'linux-portable', 'windows-installed'))
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--new', type=Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--no-relaunch', action='store_true', help='for tests')
    args = parser.parse_args(argv)
    try:
        os.chdir(args.new.parent)            # never stand inside the files being moved
    except OSError:
        pass
    log(args.log, f'update of {args.folder} ({args.kind}) from {args.new}')
    ok = False
    try:
        if not wait_for_exit(args.pid, args.log):
            raise RuntimeError('ROMancer did not close, so the update was not applied. Close every ROMancer window and try again.')
        if args.kind == 'windows-installed':
            install_new(args.folder, args.new, args.log)
        else:
            swap_portable(args.folder, args.new, args.log)
        ok = True
    except Exception as error:
        message = str(error) if isinstance(error, RuntimeError) else (
            'The update could not replace ROMancer\u2019s files, so the old version was kept. '
            'Another program may be using them. Details are in ' + str(args.log))
        log(args.log, f'not applied: {error!r}')
        record_failure(args.state, message)
    if not args.no_relaunch:
        try:
            relaunch(args.kind, args.folder, args.workspace, args.log)
        except Exception as error:
            log(args.log, f'could not start ROMancer again: {error!r}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
