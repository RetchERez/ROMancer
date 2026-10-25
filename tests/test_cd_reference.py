import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import check_cd_reference


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer reference ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checker = self.root / 'checker'
        self.checker.write_bytes(b'synthetic checker stand-in')
        self.output = self.root / 'vectors.json'
        fixture = Path(__file__).parent / 'fixtures' / 'mode1_vectors.json'
        self.frozen = json.loads(fixture.read_text(encoding='utf-8'))

    def run_generator(self, during_check=None):
        controls = iter(('good', 'bad'))

        def run(args, **kwargs):
            control = next(controls)
            if during_check is not None:
                during_check(control)
            evidence = self.frozen[control]
            return subprocess.CompletedProcess(args, evidence['exit_code'],
                                               evidence['stdout'], evidence['stderr'])

        with patch.object(sys, 'argv', ['check_cd_reference', str(self.checker), str(self.output)]), \
                patch('tools.check_cd_reference.subprocess.run', side_effect=run), \
                contextlib.redirect_stdout(io.StringIO()):
            check_cd_reference.main()

    def assert_no_output(self):
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.romancer-*.tmp')), [])

    def test_reference_output_created_during_check_is_preserved(self):
        def competing_writer(control):
            if control == 'good':
                self.output.write_bytes(b'other process')

        with self.assertRaises((ValueError, FileExistsError)):
            self.run_generator(competing_writer)
        self.assertEqual(self.output.read_bytes(), b'other process')
        self.assertEqual(list(self.root.glob('.romancer-*.tmp')), [])

    def test_reference_output_created_at_commit_is_preserved(self):
        real_link = os.link

        def competing_writer(source, destination):
            self.output.write_bytes(b'other process')
            real_link(source, destination)

        with patch('os.link', side_effect=competing_writer):
            with self.assertRaises(FileExistsError):
                self.run_generator()
        self.assertEqual(self.output.read_bytes(), b'other process')
        self.assertEqual(list(self.root.glob('.romancer-*.tmp')), [])

    def test_complete_vectors_are_atomically_published(self):
        real_link = os.link
        published = []

        def publish(source, destination):
            self.assertFalse(self.output.exists())
            self.assertEqual(Path(source).parent, self.output.parent)
            data = json.loads(Path(source).read_text(encoding='utf-8'))
            self.assertEqual(data['vectors'], self.frozen['vectors'])
            real_link(source, destination)
            published.append(self.output.read_bytes())

        with patch('os.link', side_effect=publish):
            self.run_generator()
        self.assertEqual(published, [self.output.read_bytes()])
        self.assertEqual(list(self.root.glob('.romancer-*.tmp')), [])

    def test_unavailable_atomic_publication_fails_without_output(self):
        with patch('os.link', side_effect=OSError('link unsupported')):
            with self.assertRaises(OSError):
                self.run_generator()
        self.assert_no_output()

    def test_unrelated_checker_does_not_claim_pinned_commit(self):
        measured_hash = hashlib.sha256(self.checker.read_bytes()).hexdigest()
        self.run_generator()
        data = json.loads(self.output.read_text(encoding='utf-8'))
        self.assertIsNone(data.get('checker_commit'))
        self.assertEqual(data['checker_sha256'], measured_hash)
        self.assertEqual(data.get('checker_identity_status'), 'MEASURED_UNPINNED')
        self.assertEqual(data['good'], self.frozen['good'])
        self.assertEqual(data['bad'], self.frozen['bad'])

    def test_checker_content_change_during_either_control_blocks_evidence(self):
        for changed_control in ('good', 'bad'):
            with self.subTest(control=changed_control):
                self.output.unlink(missing_ok=True)
                self.checker.write_bytes(b'synthetic checker stand-in')

                def mutate(control):
                    if control == changed_control:
                        previous = self.checker.stat()
                        self.checker.write_bytes(b'Synthetic checker stand-in')
                        os.utime(self.checker, ns=(previous.st_atime_ns, previous.st_mtime_ns))

                with self.assertRaisesRegex(ValueError, 'checker.*changed'):
                    self.run_generator(mutate)
                self.assert_no_output()

    def test_checker_replaced_with_identical_bytes_blocks_evidence(self):
        def replace(control):
            if control == 'good':
                previous = self.checker.stat()
                other = self.root / 'replacement-checker'
                other.write_bytes(self.checker.read_bytes())
                os.utime(other, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                os.replace(other, self.checker)

        with self.assertRaisesRegex(ValueError, 'checker.*changed'):
            self.run_generator(replace)
        self.assert_no_output()

    def test_invalid_control_does_not_publish(self):
        self.frozen['bad']['stdout'] = 'Total errors.... 0\n'
        with self.assertRaises(RuntimeError):
            self.run_generator()
        self.assert_no_output()


if __name__ == '__main__':
    unittest.main()
