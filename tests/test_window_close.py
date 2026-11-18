import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from romancer import workbench_server as ws

ROOT = Path(__file__).resolve().parents[1]


class WindowCloseTests(unittest.TestCase):
    def test_when_every_window_counts_as_closed(self):
        gone = ws.window_gone
        self.assertFalse(gone(None, None, 10_000))                    # no window ever opened: an API client keeps the service
        self.assertFalse(gone(100, None, 100 + ws.WINDOW_QUIET - 1))  # a window that is only quiet (minimised, asleep)
        self.assertTrue(gone(100, None, 100 + ws.WINDOW_QUIET + 1))   # closed with no chance to say so
        self.assertFalse(gone(100, 110, 110 + ws.WINDOW_GRACE - 1))   # said it was closing a moment ago: may be a reload
        self.assertTrue(gone(100, 110, 110 + ws.WINDOW_GRACE + 1))
        self.assertFalse(gone(120, 110, 110 + ws.WINDOW_GRACE + 1))   # another window, or the reloaded page, spoke since

    def test_the_service_stops_after_its_window_closed_and_only_when_asked_to(self):
        with tempfile.TemporaryDirectory() as folder:
            code = ('import sys; from pathlib import Path; from romancer import workbench_server as ws; '
                    'ws.WINDOW_GRACE = 1; ws.serve(Path(sys.argv[1]), 0, False, sys.argv[2] == "stop")')
            for mode, stops in (('stop', True), ('stay', False)):
                workspace = Path(folder) / mode
                workspace.mkdir()
                process = subprocess.Popen([sys.executable, '-B', '-c', code, str(workspace), mode], cwd=ROOT,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                try:
                    process.stdout.readline()
                    url = process.stdout.readline().strip()
                    base, token = url.split('/#token=')

                    def call(operation):
                        request = urllib.request.Request(base + '/api/call', json.dumps({'operation': operation, 'parameters': {}}).encode(),
                                                         {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                        return json.loads(urllib.request.urlopen(request, timeout=20).read())
                    self.assertTrue(call('system.ui_alive')['ok'])
                    self.assertTrue(call('system.ui_closed')['ok'])
                    deadline = time.monotonic() + 15
                    while process.poll() is None and time.monotonic() < deadline and stops:
                        time.sleep(0.2)
                    if stops:
                        self.assertEqual(process.poll(), 0, 'the service should have stopped by itself')
                    else:
                        time.sleep(3)
                        self.assertIsNone(process.poll(), 'without --stop-when-closed the service keeps running')
                        self.assertTrue(call('system.ui_alive')['ok'])
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(10)
                    process.stdout.close()


if __name__ == '__main__':
    unittest.main()
