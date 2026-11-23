"""Updates: release check, download and checksum, unpacking, the swap helper and putting things back on failure.

A fake release is served from 127.0.0.1 (ROMANCER_UPDATE_URL), so nothing here touches the network.
"""
import hashlib
import http.server
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from romancer import ROMANCER_VERSION, updater, update_helper

NEXT = '.'.join(map(str, (lambda k: (k[0], k[1], k[2] + 1))(updater.version_key(ROMANCER_VERSION))))


def bundle_files(version, marker=b'new'):
    """The files of a tiny Windows package: launcher, readme and a runtime with a checked manifest."""
    runtime = {'app/romancer/__init__.py': b'ROMANCER_VERSION = "' + version.encode() + b'"\n', 'python/python.exe': b'fake python ' + marker}
    manifest = {'schema_version': 1, 'product': 'ROMancer', 'version': version,
                'files': [{'path': p, 'size': len(d), 'sha256': hashlib.sha256(d).hexdigest()} for p, d in runtime.items()]}
    files = {'ROMancer.exe': b'launcher ' + marker, 'README.txt': b'readme ' + marker,
             'ROMancer Files/Runtime/BUNDLE.json': json.dumps(manifest).encode()}
    files.update({'ROMancer Files/Runtime/' + p: d for p, d in runtime.items()})
    return files


def make_zip(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def write_tree(root: Path, files):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class FakeRelease:
    """A local server with /latest, the package and SHA256SUMS."""

    def __init__(self, version=NEXT, package=None, sums=None):
        self.version = version
        self.package = package if package is not None else make_zip(bundle_files(version))
        name = f'ROMancer-v{version}-Windows.zip'
        self.sums = sums if sums is not None else f'{hashlib.sha256(self.package).hexdigest()}  {name}\n'
        files = {name: self.package, 'SHA256SUMS': self.sums.encode()}
        release = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == '/latest':
                    base = f'http://127.0.0.1:{self.server.server_port}/'
                    body = json.dumps({'tag_name': 'v' + release.version, 'body': 'Notes', 'html_url': base + 'page',
                                       'assets': [{'name': n, 'browser_download_url': base + n, 'size': len(d)} for n, d in files.items()]}).encode()
                else:
                    body = files.get(self.path.lstrip('/'))
                    if body is None:
                        self.send_response(404)
                        self.end_headers()
                        return
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/latest'

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def dead_pid():
    process = subprocess.Popen([sys.executable, '-c', 'pass'])
    process.wait()
    return process.pid


def wait_idle(u, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not u.task:
            return
        time.sleep(0.05)
    raise AssertionError('update step did not finish')


class VersionTests(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(updater.newer('1.4.1', '1.4.0'))
        self.assertTrue(updater.newer('v1.10.0', '1.9.9'))
        self.assertFalse(updater.newer('1.4.0', '1.4.0'))
        self.assertFalse(updater.newer('1.3.9', '1.4.0'))
        self.assertFalse(updater.newer('beta', '1.4.0'))

    def test_sums(self):
        self.assertEqual(updater.parse_sums('a' * 64 + '  X.zip\n' + 'B' * 64 + ' *Y.tar.gz\n'), {'X.zip': 'a' * 64, 'Y.tar.gz': 'b' * 64})


class KindTests(unittest.TestCase):
    def test_kinds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = root / 'portable' / 'ROMancer Files' / 'Runtime' / 'app'
            app.mkdir(parents=True)
            (root / 'portable' / 'ROMancer.exe').write_bytes(b'')
            self.assertEqual(updater.install_kind(app)['kind'], 'windows-portable')
            (root / 'portable' / 'ROMancer.exe').unlink()
            (root / 'portable' / 'ROMancer.sh').write_bytes(b'')
            self.assertEqual(updater.install_kind(app)['kind'], 'linux-portable')
            slot = root / 'installed' / 'versions' / '1.4.0-abc' / 'app'
            slot.mkdir(parents=True)
            (root / 'installed' / 'active.json').write_text('{}')
            self.assertEqual(updater.install_kind(slot)['kind'], 'windows-installed')
            self.assertEqual(updater.install_kind(root / 'checkout')['kind'], 'source')


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        here = os.getcwd()                       # the helper changes folder; put it back before the temp folder goes
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(os.chdir, here)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'ROMancer'
        write_tree(self.folder, bundle_files(ROMANCER_VERSION, b'old'))
        (self.folder / 'my notes.txt').write_bytes(b'mine')                 # a file of the user's: never touched
        self.workspace = self.root / 'workspace'
        self.app = self.folder / 'ROMancer Files' / 'Runtime' / 'app'

    def tearDown(self):
        pass

    def updater(self, release, **kw):
        os.environ['ROMANCER_UPDATE_URL'] = release.url
        self.addCleanup(os.environ.pop, 'ROMANCER_UPDATE_URL', None)
        return updater.Updater(self.workspace, app_root=self.app, **kw)

    def test_check_finds_newer_and_remembers_the_day(self):
        release = FakeRelease()
        self.addCleanup(release.close)
        u = self.updater(release)
        u.check()
        wait_idle(u)
        status = u.status()
        self.assertTrue(status['available'])
        self.assertTrue(status['can_apply'])
        self.assertEqual(status['latest']['version'], NEXT)
        with mock.patch.object(updater, 'fetch_latest') as fetch:
            u2 = self.updater(release)
            u2.check()
            fetch.assert_not_called()                                    # checked less than a day ago

    def test_setting_off_means_no_automatic_check(self):
        release = FakeRelease()
        self.addCleanup(release.close)
        u = self.updater(release, enabled=lambda: False)
        with mock.patch.object(updater, 'fetch_latest') as fetch:
            u.check()
            fetch.assert_not_called()
        u.check(force=True)                                              # Check for updates now still works
        wait_idle(u)
        self.assertTrue(u.status()['available'])

    def test_offline_says_so(self):
        os.environ['ROMANCER_UPDATE_URL'] = 'http://127.0.0.1:9/latest'
        self.addCleanup(os.environ.pop, 'ROMANCER_UPDATE_URL', None)
        u = updater.Updater(self.workspace, app_root=self.app)
        u.check(force=True)
        wait_idle(u)
        self.assertFalse(u.status()['available'])
        self.assertIn('Could not check for updates', u.status()['error'])

    def test_bad_checksum_changes_nothing(self):
        release = FakeRelease(sums='0' * 64 + f'  ROMancer-v{NEXT}-Windows.zip\n')
        self.addCleanup(release.close)
        u = self.updater(release)
        u.check(force=True)
        wait_idle(u)
        u.start()
        wait_idle(u)
        self.assertIn('does not match the release checksum', u.status()['error'])
        self.assertFalse(u.status()['ready'])
        self.assertEqual((self.folder / 'ROMancer.exe').read_bytes(), b'launcher old')

    def test_tampered_file_inside_the_package_is_refused(self):
        files = bundle_files(NEXT)
        files['ROMancer Files/Runtime/python/python.exe'] = b'changed after the manifest'
        release = FakeRelease(package=make_zip(files))
        self.addCleanup(release.close)
        u = self.updater(release)
        u.check(force=True)
        wait_idle(u)
        u.start()
        wait_idle(u)
        self.assertIn('wrong size', u.status()['error'])

    def test_busy_waits(self):
        release = FakeRelease()
        self.addCleanup(release.close)
        u = self.updater(release, busy=lambda: 'A level map is being recorded.')
        u.check(force=True)
        wait_idle(u)
        u.start()
        wait_idle(u)
        self.assertTrue(u.status()['ready'])
        with mock.patch.object(updater, 'spawn') as spawn:
            result = u.apply()
            spawn.assert_not_called()
        self.assertFalse(result['ok'])
        self.assertEqual(result['busy'], 'A level map is being recorded.')

    def test_whole_update_then_next_start(self):
        release = FakeRelease()
        self.addCleanup(release.close)
        u = self.updater(release)
        stopped = []
        u.shutdown = lambda: stopped.append(True)
        u.check(force=True)
        wait_idle(u)
        u.start()
        wait_idle(u)
        self.assertTrue(u.status()['ready'], u.status()['error'])
        commands = []
        with mock.patch.object(updater, 'spawn', commands.append):
            result = u.apply()
        self.assertTrue(result['restarting'])
        command = commands[0]
        self.assertTrue(Path(command[0]).is_file())                     # the copied Python of the new version
        self.assertNotIn('ROMancer Files', command[0])
        args = command[4:]                                              # after python -I -B helper
        args[args.index('--pid') + 1] = str(dead_pid())
        self.assertEqual(update_helper.main(args + ['--no-relaunch']), 0)
        self.assertEqual((self.folder / 'ROMancer.exe').read_bytes(), b'launcher new')
        self.assertEqual((self.folder / 'ROMancer Files' / 'Runtime' / 'python' / 'python.exe').read_bytes(), b'fake python new')
        self.assertEqual((self.folder / 'my notes.txt').read_bytes(), b'mine')
        self.assertEqual((self.folder / '.romancer-previous' / 'ROMancer.exe').read_bytes(), b'launcher old')
        time.sleep(1.7)
        self.assertEqual(stopped, [True])
        # the new version starts: it reports the update and removes the old files and the download
        os.chdir(self.root)                                              # the helper process has exited by then
        with mock.patch.object(updater, 'ROMANCER_VERSION', NEXT):
            after = updater.Updater(self.workspace, app_root=self.app)
        self.assertEqual(after.finished, {'updated': True, 'from': ROMANCER_VERSION, 'to': NEXT})
        self.assertFalse((self.folder / '.romancer-previous').exists())
        self.assertFalse((self.folder / '.romancer-update').exists())
        self.assertFalse((self.workspace / 'updates').exists())

    def test_failed_swap_puts_everything_back(self):
        new = self.root / 'new'
        write_tree(new, bundle_files(NEXT))
        state = self.workspace / 'update.json'
        self.workspace.mkdir()
        state.write_text(json.dumps({'checked': 0, 'latest': None, 'applying': {'from': ROMANCER_VERSION, 'to': NEXT}, 'failure': ''}))
        real = update_helper.move
        calls = []

        def flaky(source, target):
            calls.append(source)
            if len(calls) == 4:                                          # partway through the second item
                raise PermissionError('in use')
            real(source, target)
        with mock.patch.object(update_helper, 'move', flaky):
            code = update_helper.main(['--kind', 'windows-portable', '--folder', str(self.folder), '--new', str(new),
                                       '--pid', str(dead_pid()), '--log', str(self.root / 'u.log'), '--state', str(state), '--workspace', str(self.workspace), '--no-relaunch'])
        self.assertEqual(code, 1)
        self.assertEqual((self.folder / 'ROMancer.exe').read_bytes(), b'launcher old')
        self.assertEqual((self.folder / 'README.txt').read_bytes(), b'readme old')
        self.assertEqual((self.folder / 'ROMancer Files' / 'Runtime' / 'python' / 'python.exe').read_bytes(), b'fake python old')
        self.assertEqual((self.folder / 'my notes.txt').read_bytes(), b'mine')
        # the old version starts again and says why
        again = updater.Updater(self.workspace, app_root=self.app)
        self.assertFalse(again.finished['updated'])
        self.assertIn('old version was kept', again.finished['message'])

    def test_unwritable_folder_offers_the_page(self):
        release = FakeRelease()
        self.addCleanup(release.close)
        u = self.updater(release)
        u.check(force=True)
        wait_idle(u)
        with mock.patch.object(updater, 'writable', return_value=False):
            status = u.status()
        self.assertFalse(status['can_apply'])
        self.assertIn('cannot write', status['reason'])


class SettingsTests(unittest.TestCase):
    def test_settings_saved_by_an_older_version_still_load(self):
        from romancer.app_settings import DEFAULT_SETTINGS, get_settings
        with tempfile.TemporaryDirectory() as temp:
            old = {k: v for k, v in DEFAULT_SETTINGS.items() if k != 'checkUpdates'}
            Path(temp, 'settings.json').write_text(json.dumps({'schema_version': 1, 'revision': 3, 'values': old}))
            got = get_settings(temp)
            self.assertTrue(got['values']['checkUpdates'])
            self.assertEqual(got['revision'], 3)


if __name__ == '__main__':
    unittest.main()
