import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_cdrom import sector


class CdCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer CLI space ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'original.bin'
        self.original = sector(0) + sector(1)
        self.source.write_bytes(self.original)
        self.dest = self.root / 'patched.bin'

    def cli(self, *extra):
        return subprocess.run([sys.executable, '-u', '-m', 'romancer', 'sega-cd-patch',
                               str(self.source), '--extent', '0', '--file-offset', '2047',
                               '--out-bin', str(self.dest), '--ascii', 'XY', '--json', *extra],
                              capture_output=True, text=True, timeout=30)

    def test_retired_commands_are_not_registered_and_publish_nothing(self):
        from romancer.cli import main
        import contextlib,io
        for command in ('sega-cd-map','sega-cd-patch','shadowrun-scd-profile','v31-capabilities'):
            with self.subTest(command=command),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as failed:
                main([command])
            self.assertEqual(failed.exception.code,2)
            self.assertFalse(self.dest.exists())
        output=io.StringIO()
        with contextlib.redirect_stdout(output),self.assertRaises(SystemExit):main(['--help'])
        self.assertNotIn('sega-cd',output.getvalue().lower())

    def test_empty_cert_manifest_has_nonzero_exit(self):
        path = self.root / 'empty.json'
        path.write_text('{"gates":[]}', encoding='utf-8')
        response = subprocess.run([sys.executable, '-u', '-m', 'romancer', 'certify-v10', str(path), '--json'],
                                  capture_output=True, text=True, timeout=30)
        self.assertNotEqual(response.returncode, 0)
        self.assertFalse(json.loads(response.stdout)['ok'])

    def test_buffered_python_invocation_still_emits_json(self):
        response = subprocess.run([sys.executable, '-m', 'romancer', 'version', '--json'],
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(response.returncode, 0)
        self.assertTrue(response.stdout.strip(), 'CLI discarded buffered stdout')

    def test_version_identifies_release_build(self):
        response = subprocess.run([sys.executable, '-m', 'romancer', 'version', '--json'],
                                  capture_output=True, text=True, timeout=30)
        from romancer import ROMANCER_VERSION
        self.assertEqual(json.loads(response.stdout)['version'], ROMANCER_VERSION)
        self.assertRegex(ROMANCER_VERSION, r'^\d+\.\d+\.\d+$')


if __name__ == '__main__':
    unittest.main()
