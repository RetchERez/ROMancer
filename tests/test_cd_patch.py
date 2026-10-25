import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_cdrom import sector


def subject():
    from romancer import cd_patch
    return cd_patch


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.cd_patch'),
                             'safe transactional CD writer missing')
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer space ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'original.bin'
        self.dest = self.root / 'modified.bin'
        self.original = b''.join(sector(seed, seed) for seed in range(4))
        self.source.write_bytes(self.original)
        self.digest = hashlib.sha256(self.original).hexdigest()

    def apply(self, offset=2047, replacement=b'XY', **kwargs):
        logical = b''.join(self.original[i + 16:i + 2064] for i in range(0, len(self.original), 2352))
        settings = {'expected_sha256': self.digest,
                    'expected_before': logical[offset:offset + len(replacement)]}
        settings.update(kwargs)
        return subject().patch_mode1(self.source, self.dest, 0, offset, replacement, **settings)

    def assert_preserved(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.root.glob('.romancer-*')), [])

    def test_cross_sector_write_does_not_touch_headers(self):
        result = self.apply()
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['written'])
        self.assertEqual(result['validation_status'], 'PASS')
        self.assertEqual(result.get('output_verification_status'), 'PASS')
        self.assertEqual(result['publication_status'], 'PUBLISHED')
        data = self.dest.read_bytes()
        self.assertEqual(result['out_sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(data[2063], ord('X'))
        self.assertEqual(data[2352 + 16], ord('Y'))
        self.assertEqual(data[2352:2368], self.original[2352:2368])
        self.assertEqual(data[4704:], self.original[4704:])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_long_write_three_sectors_reads_back_exactly(self):
        replacement = b'B' * 2060
        result = self.apply(2040, replacement)
        self.assertTrue(result['ok'], result)
        raw = self.dest.read_bytes()
        logical = b''.join(raw[i + 16:i + 2064] for i in range(0, len(raw), 2352))
        self.assertEqual(logical[2040:4100], replacement)
        self.assertEqual(len(raw), len(self.original))

    def test_last_byte_is_writable(self):
        self.assertTrue(self.apply(8191, b'Z')['ok'])

    def test_wrong_hash_or_prefix_or_missing_preconditions_rejected(self):
        for kwargs in [{'expected_sha256': '0' * 64}, {'expected_before': b'X'},
                       {'expected_sha256': ''}, {'expected_before': None}]:
            with self.subTest(kwargs=kwargs):
                self.assertFalse(self.apply(**kwargs)['ok'])
                self.assert_preserved()

    def test_resource_bounds_and_track_bounds(self):
        for offset, data, kwargs in [(2047, b'AB', {'resource_size': 2048}),
                                     (0, b'', {}), (-1, b'X', {})]:
            with self.subTest(offset=offset):
                self.assertFalse(self.apply(offset, data, **kwargs)['ok'])
                self.assert_preserved()

    def test_track_bounds_with_complete_expected_byte(self):
        result = self.apply(8192, b'A', expected_before=b'\0')
        self.assertFalse(result['ok'])
        self.assertIn('track bounds', result['error'])
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assert_preserved()

    def test_same_length_wrong_expected_byte_rejected(self):
        result = self.apply(0, b'X', expected_before=b'\x01')
        self.assertFalse(result['ok'])
        self.assertIn('expected original payload mismatch', result['error'])
        self.assertEqual(result['validation_status'], 'FAIL')
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assert_preserved()

    def test_source_as_destination_rejected(self):
        result = subject().patch_mode1(self.source, self.source, 0, 0, b'X',
                                      expected_sha256=self.digest, expected_before=b'\0')
        self.assertFalse(result['ok'])
        self.assert_preserved()

    @unittest.skipUnless(os.name == 'nt', 'Windows output naming rules')
    def test_windows_ads_output_and_report_names_rejected_without_opening(self):
        for name in ('original.bin:report.json', 'new.bin:stream', 'new.bin::$DATA'):
            for report in (False, True):
                with self.subTest(name=name, report=report):
                    candidate = self.root / name
                    outputs = [self.dest, candidate] if report else [candidate]
                    with self.assertRaisesRegex(ValueError, 'Windows.*output'):
                        subject().check_output_paths(self.source, outputs)
        self.assert_preserved()

    @unittest.skipUnless(os.name == 'nt', 'Windows output naming rules')
    def test_windows_device_and_trailing_dot_space_output_names_rejected(self):
        names = ('NUL', 'nul.json', 'CON', 'con .json', 'PRN', 'AUX', 'COM1',
                 'LPT9.json', 'new.bin.', 'new.bin ', 'directory. /report.json',
                 'directory./report.json', 'NUL/report.json')
        for name in names:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'Windows.*output'):
                    subject().check_output_paths(self.source, [self.root / name])
        self.assert_preserved()

    @unittest.skipUnless(os.name == 'nt', 'Windows output naming rules')
    def test_windows_ordinary_drive_paths_remain_valid(self):
        output = self.root / 'COM10.bin'
        report = self.root / 'reports with spaces' / '..' / 'report.json'
        subject().check_output_paths(self.source, [output, report])
        self.assert_preserved()

    @unittest.skipUnless(os.name == 'nt', 'Windows output naming rules')
    def test_windows_device_namespace_outputs_rejected(self):
        for name in (r'\\.\NUL', r'\\.\PhysicalDrive0', r'\\?\C:\new.bin'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'Windows.*output'):
                    subject().check_output_paths(self.source, [Path(name)])
        self.assert_preserved()

    def test_hardlink_alias_and_existing_destination_rejected(self):
        os.link(self.source, self.dest)
        self.assertFalse(self.apply()['ok'])
        self.assertEqual(self.dest.read_bytes(), self.original)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_dry_run_discovers_without_writing(self):
        result = self.apply(expected_sha256='', expected_before=None, dry_run=True)
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['written'])
        self.assertEqual(result.get('output_verification_status'), 'NOT_RUN')
        self.assertEqual(result['publication_status'], 'NOT_APPLICABLE')
        self.assertEqual(result['source_sha256'], self.digest)
        self.assertEqual(len(bytes.fromhex(result['before_hex'])), 2)
        self.assert_preserved()

    def test_corrupt_untouched_sector_blocks_write(self):
        damaged = bytearray(self.original)
        damaged[-1] ^= 1
        self.source.write_bytes(damaged)
        result = self.apply(expected_sha256=hashlib.sha256(damaged).hexdigest())
        self.assertFalse(result['ok'])
        self.assertIn('integrity', result['error'].lower())
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.source.read_bytes(), damaged)

    def test_publication_failure_cleans_owned_temp(self):
        with patch('romancer.cd_patch.os.link', side_effect=OSError('publication denied')):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertEqual(result.get('output_verification_status'), 'PASS')
        self.assertEqual(result['publication_status'], 'FAILED')
        self.assert_preserved()

    def test_destination_created_during_build_is_not_overwritten(self):
        real_link = os.link
        def competing_writer(source, dest):
            Path(dest).write_bytes(b'other process')
            return real_link(source, dest)
        with patch('romancer.cd_patch.os.link', side_effect=competing_writer):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertEqual(self.dest.read_bytes(), b'other process')
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_verification_failure_blocks_publication(self):
        with patch('romancer.cd_patch._verify_output', side_effect=ValueError(
                'output payload or header mismatch at sector 0')):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertEqual(result['validation_status'], 'PASS')
        self.assertEqual(result.get('output_verification_status'), 'FAIL')
        self.assertEqual(result.get('output_integrity'), 'FAIL')
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assert_preserved()

    def test_source_changed_during_build_blocks_publication(self):
        real_verify = subject()._verify_output
        def mutate(*args):
            result = real_verify(*args)
            self.source.write_bytes(sector(99) + self.original[2352:])
            return result
        with patch('romancer.cd_patch._verify_output', side_effect=mutate):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertEqual(result['validation_status'], 'FAIL')
        self.assertEqual(result.get('output_verification_status'), 'PASS')
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assertFalse(self.dest.exists())

    def test_copy_failure_does_not_publish(self):
        with patch('romancer.cd_patch._write_output', side_effect=OSError('disk full')):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertEqual(result['validation_status'], 'PASS')
        self.assertEqual(result.get('output_verification_status'), 'NOT_RUN')
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assert_preserved()

    def test_destination_directory_failure_keeps_validated_source_status(self):
        with patch.object(Path, 'mkdir', side_effect=OSError('directory denied')):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertEqual(result['validation_status'], 'PASS')
        self.assertEqual(result.get('output_verification_status'), 'NOT_RUN')
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assert_preserved()

    def test_source_change_during_final_output_hash_blocks_publish(self):
        real_hash = subject()._hash_file

        def mutate(path):
            digest = real_hash(path)
            if path != self.source:
                previous = self.source.stat()
                self.source.write_bytes(sector(99) + self.original[2352:])
                os.utime(self.source, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1000000000))
            return digest

        with patch('romancer.cd_patch._hash_file', side_effect=mutate):
            result = self.apply()
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['validation_status'], 'FAIL')
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assertFalse(self.dest.exists())

    def test_temp_mutation_during_final_source_hash_blocks_publish(self):
        real_hash = subject()._hash_file

        def mutate(path):
            digest = real_hash(path)
            if path == self.source:
                temporary, = self.root.glob('.romancer-*.tmp')
                previous = temporary.stat()
                with temporary.open('r+b') as stream:
                    stream.seek(16)
                    stream.write(b'Y')
                # A content check must work even when size/mtime are unchanged.
                os.utime(temporary, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            return digest

        with patch('romancer.cd_patch._hash_file', side_effect=mutate):
            result = self.apply(0, b'X')
        self.assertFalse(result['ok'], result)
        self.assertEqual(result.get('output_verification_status'), 'FAIL')
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assert_preserved()

    def test_temp_replacement_with_identical_bytes_blocks_publish_and_is_preserved(self):
        real_hash = subject()._hash_file
        replacement = self.root / 'other.tmp'
        replaced = []

        def replace(path):
            digest = real_hash(path)
            if path == self.source:
                temporary, = self.root.glob('.romancer-*.tmp')
                previous = temporary.stat()
                replacement.write_bytes(temporary.read_bytes())
                os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                os.replace(replacement, temporary)
                replaced.append(temporary)
            return digest

        with patch('romancer.cd_patch._hash_file', side_effect=replace):
            result = self.apply()
        self.assertFalse(result['ok'], result)
        self.assertEqual(result.get('output_verification_status'), 'FAIL')
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assertFalse(self.dest.exists())
        self.assertTrue(replaced[0].exists(), 'cleanup must not delete a replacement file')
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_interrupt_during_copy_returns_cancelled_without_output(self):
        with patch('romancer.cd_patch._write_output', side_effect=KeyboardInterrupt):
            try:
                result = self.apply()
            except KeyboardInterrupt:
                self.fail('precommit cancellation must return a structured result')
        self.assertFalse(result['ok'])
        self.assertTrue(result.get('cancelled'))
        self.assertFalse(result['written'])
        self.assertEqual(result['publication_status'], 'NOT_RUN')
        self.assert_preserved()

    def test_interrupt_before_link_preserves_competing_output(self):
        def cancel(source, destination):
            Path(destination).write_bytes(b'other process')
            raise KeyboardInterrupt

        with patch('romancer.cd_patch.os.link', side_effect=cancel):
            try:
                result = self.apply()
            except KeyboardInterrupt:
                self.fail('publication cancellation must return a structured result')
        self.assertFalse(result['ok'])
        self.assertTrue(result.get('cancelled'))
        self.assertFalse(result['written'])
        self.assertEqual(result['publication_status'], 'CANCELLED')
        self.assertEqual(self.dest.read_bytes(), b'other process')
        self.assertEqual(list(self.root.glob('.romancer-*')), [])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_interrupt_after_link_reports_committed_output(self):
        # Interrupt the first Python line after the real filesystem commit.
        previous_trace = sys.gettrace()
        interrupted = []

        def trace(frame, event, arg):
            if (frame.f_code is subject().patch_mode1.__code__ and event == 'line'
                    and self.dest.exists() and not interrupted):
                interrupted.append(True)
                raise KeyboardInterrupt
            return trace

        try:
            sys.settrace(trace)
            result = self.apply()
        except KeyboardInterrupt:
            self.fail('committed output must be reported even after cancellation')
        finally:
            sys.settrace(previous_trace)
        self.assertTrue(interrupted)
        self.assertFalse(result['ok'])
        self.assertTrue(result.get('cancelled'))
        self.assertTrue(result['written'])
        self.assertEqual(result['publication_status'], 'PUBLISHED')
        self.assertEqual(result.get('output_verification_status'), 'PASS')
        self.assertEqual(result['out_bin'], str(self.dest))
        self.assertEqual(result['out_sha256'], hashlib.sha256(self.dest.read_bytes()).hexdigest())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('.romancer-*')), [])

    def test_interrupt_during_cleanup_reports_commit_and_retries_owned_cleanup(self):
        real_unlink = Path.unlink
        interrupted = []

        def cancel_once(path, *args, **kwargs):
            if path.name.startswith('.romancer-') and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, 'unlink', new=cancel_once):
            try:
                result = self.apply()
            except KeyboardInterrupt:
                self.fail('cleanup cancellation must retain the publication result')
        self.assertTrue(interrupted)
        self.assertFalse(result['ok'])
        self.assertTrue(result.get('cancelled'))
        self.assertTrue(result['written'])
        self.assertEqual(result['publication_status'], 'PUBLISHED')
        self.assertEqual(result['out_sha256'], hashlib.sha256(self.dest.read_bytes()).hexdigest())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('.romancer-*')), [])

    def test_identity_uses_inode_size_and_mtime_not_inconsistent_ctime(self):
        first = SimpleNamespace(st_dev=1, st_ino=2, st_size=9408, st_mtime_ns=50, st_ctime_ns=49)
        second = SimpleNamespace(st_dev=1, st_ino=2, st_size=9408, st_mtime_ns=50, st_ctime_ns=50)
        self.assertEqual(subject()._identity(first), subject()._identity(second))


if __name__ == '__main__':
    unittest.main()
