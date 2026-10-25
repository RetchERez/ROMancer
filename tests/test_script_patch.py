from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_script import literal_fixture, request


def api():
    return importlib.import_module('romancer.script_patch')


class ScriptPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer script transaction ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'original.bin'
        self.output = self.root / 'new.bin'
        self.raw, self.schema = literal_fixture()
        self.source.write_bytes(self.raw)

    def prepare(self, changes=None):
        service = importlib.import_module('romancer.script')
        doc = service.inspect_script(self.source, self.schema)
        edits = request(doc, [{'record_id': 'a', 'segment': 0, 'text': 'BA'}]
                        if changes is None else changes)
        plan = service.plan_script(self.source, self.schema, edits)
        self.assertTrue(plan['ok'], plan)
        return edits, plan['plan_id']

    def apply(self, changes=None, **kwargs):
        edits, plan_id = self.prepare(changes)
        return api().apply_script(self.source, self.output, self.schema, edits,
                                  expected_plan_id=plan_id, **kwargs)

    def assert_unpublished(self, result):
        self.assertFalse(result['ok'], result)
        self.assertIs(result['written'], False, result)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(list(self.root.glob('.romancer-script-*')), [])

    def test_service_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.script_patch'))

    def test_full_literal_output_and_verified_model(self):
        result = self.apply()
        expected = self.raw[:8] + b'BA\xf0\x03B\x00' + b'\xff' * 6 + self.raw[20:]
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['written'])
        self.assertEqual(result['publication_status'], 'PUBLISHED')
        self.assertEqual(result['output_verification_status'], 'PASS')
        self.assertEqual(self.output.read_bytes(), expected)
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(result['out_sha256'], hashlib.sha256(expected).hexdigest())
        self.assertEqual(result['final_records'][0]['raw_hex'], expected[8:20].hex())
        self.assertEqual(result['final_document']['source_sha256'], result['out_sha256'])
        self.assertEqual(list(self.root.glob('.romancer-script-*')), [])

    def test_noop_publishes_real_byte_exact_copy(self):
        result = self.apply([])
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['written'])
        self.assertEqual(self.output.read_bytes(), self.raw)
        self.assertEqual(result['changed_record_count'], 0)
        self.assertEqual(result['changed_byte_count'], 0)

    def test_existing_destination_and_hardlink_are_preserved(self):
        for hardlink in (False, True):
            if hardlink:
                os.link(self.source, self.output)
            else:
                self.output.write_bytes(b'previous output')
            before = self.output.read_bytes()
            result = self.apply()
            self.assertFalse(result['ok'])
            self.assertFalse(result['written'])
            self.assertEqual(self.output.read_bytes(), before)
            self.assertEqual(self.source.read_bytes(), self.raw)
            self.output.unlink()

    def test_same_source_and_ancestor_destinations_rejected(self):
        for destination in (self.source, self.source / 'child', self.root, self.root / 'absent' / 'out'):
            with self.subTest(destination=destination):
                self.output = destination
                result = self.apply()
                self.assertFalse(result['ok'])
                self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertFalse((self.root / 'absent').exists())

    def test_protected_schema_path_and_ancestor_cannot_be_output(self):
        protected = self.root / 'schema.json'
        protected.write_bytes(b'private schema')
        self.output = protected
        result = self.apply(protected_inputs=(protected,))
        self.assertFalse(result['ok'])
        self.assertEqual(protected.read_bytes(), b'private schema')
        self.output = self.root / 'future'
        result = self.apply(protected_inputs=(self.output / 'edits.json',))
        self.assertFalse(result['ok'])
        self.assertFalse(self.output.exists())

    def test_stale_approval_never_creates_temp_or_output(self):
        edits, plan_id = self.prepare()
        result = api().apply_script(self.source, self.output, self.schema, edits,
                                    expected_plan_id='0' * 64)
        self.assert_unpublished(result)
        edits['changes'][0]['text'] = 'BB'
        result = api().apply_script(self.source, self.output, self.schema, edits,
                                    expected_plan_id=plan_id)
        self.assert_unpublished(result)

    def test_postinspection_apply_failures_retain_measured_identity(self):
        model = importlib.import_module('romancer.script')
        doc = model.inspect_script(self.source, self.schema)
        for code in ('CAPACITY', 'STALE_REQUEST', 'STALE_APPROVAL'):
            with self.subTest(code=code):
                edits = request(doc, [{'record_id': 'a', 'segment': 0, 'text': 'A' * 9}]
                                if code == 'CAPACITY' else [])
                if code == 'STALE_REQUEST':
                    edits.update(source_sha256='0' * 64, schema_sha256='0' * 64)
                result = api().apply_script(self.source, self.output, self.schema, edits,
                                            expected_plan_id='0' * 64)
                self.assert_unpublished(result)
                self.assertEqual(result['error_code'], code)
                self.assertEqual(result['source_sha256'], hashlib.sha256(self.raw).hexdigest())
                self.assertEqual(result['schema_sha256'], doc['schema_sha256'])
                self.assertEqual(result['source_size'], len(self.raw))

    def test_changed_source_does_not_use_saved_plan_authority(self):
        edits, plan_id = self.prepare()
        changed = self.raw[:-1] + b'X'
        self.source.write_bytes(changed)
        result = api().apply_script(self.source, self.output, self.schema, edits,
                                    expected_plan_id=plan_id)
        self.assertFalse(result['ok'])
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), changed)

    def test_wrong_neighbor_and_control_output_fail_independent_verifier(self):
        module = api()
        real_copy = module._copy_output
        for offset, byte in ((31, b'X'), (10, b'\x00'), (0, b'\x09')):
            with self.subTest(offset=offset):
                def corrupt(source, output, size, hunks):
                    digest = real_copy(source, output, size, hunks)
                    output.seek(offset)
                    output.write(byte)
                    return digest
                with patch.object(module, '_copy_output', side_effect=corrupt):
                    self.assert_unpublished(self.apply())

    def test_copy_fsync_verification_and_publication_errors_preserve_original(self):
        module = api()
        for target in ('_copy_output', '_verify_output', 'os.fsync', 'os.link'):
            with self.subTest(target=target):
                with patch('romancer.script_patch.' + target, side_effect=OSError('injected failure')):
                    self.assert_unpublished(self.apply())

    def test_fdopen_failure_closes_raw_descriptor_and_allows_retry(self):
        descriptors = []
        def fail(fd, *args, **kwargs):
            descriptors.append(fd)
            raise OSError('fdopen failed')
        with patch('romancer.script_patch.os.fdopen', side_effect=fail):
            self.assert_unpublished(self.apply())
        with self.assertRaises(OSError):
            os.fstat(descriptors[0])
        self.assertTrue(self.apply()['ok'])

    def test_precommit_cancellation_does_not_publish(self):
        for target in ('_copy_output', '_verify_output', 'os.link'):
            with self.subTest(target=target):
                with patch('romancer.script_patch.' + target, side_effect=KeyboardInterrupt):
                    result = self.apply()
                self.assert_unpublished(result)
                self.assertTrue(result['cancelled'])

    def test_cancellation_after_link_reports_preserved_verified_output(self):
        real_link = os.link
        def commit_then_interrupt(*args, **kwargs):
            real_link(*args, **kwargs)
            raise KeyboardInterrupt
        with patch('romancer.script_patch.os.link', side_effect=commit_then_interrupt):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertTrue(result['cancelled'])
        self.assertTrue(result['written'])
        self.assertEqual(result['publication_status'], 'PUBLISHED')
        self.assertTrue(self.output.is_file())
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), result['out_sha256'])
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_competing_destination_is_not_deleted(self):
        def competing_link(source, destination):
            destination.write_bytes(b'competitor')
            raise FileExistsError('competing output')
        with patch('romancer.script_patch.os.link', side_effect=competing_link):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertFalse(result['written'])
        self.assertEqual(self.output.read_bytes(), b'competitor')
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_concurrent_same_destination_has_exactly_one_winner(self):
        edits, plan_id = self.prepare()
        def run(_):
            return api().apply_script(self.source, self.output, self.schema, edits,
                                       expected_plan_id=plan_id)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, range(4)))
        self.assertEqual(sum(row['written'] is True for row in results), 1)
        self.assertEqual(self.output.read_bytes(), self.raw[:8] + b'BA\xf0\x03B\x00' + b'\xff' * 6 + self.raw[20:])
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_source_change_during_final_temp_hash_blocks_publish(self):
        module = api()
        real_hash = module._hash_temporary
        changed = self.raw[:-1] + b'X'
        def mutate(path, size):
            result = real_hash(path, size)
            self.source.write_bytes(changed)
            return result
        with patch.object(module, '_hash_temporary', side_effect=mutate):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertFalse(result['written'])
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), changed)

    def test_temp_change_during_final_source_hash_blocks_publish(self):
        module = api()
        real_hash = module._rehash_source
        def mutate(stream, size):
            result = real_hash(stream, size)
            temporary, = self.root.glob('.romancer-script-*')
            with temporary.open('r+b') as output:
                output.seek(31)
                output.write(b'X')
            return result
        with patch.object(module, '_rehash_source', side_effect=mutate):
            self.assert_unpublished(self.apply())

    def test_descriptor_cleanup_error_still_cleans_owned_temporary(self):
        real_close = os.close
        def close(fd):
            real_close(fd)
            raise OSError('injected descriptor close diagnostic')
        with patch('romancer.script_patch.os.fdopen', side_effect=OSError('setup failed')):
            with patch('romancer.script_patch.os.close', side_effect=close):
                result = self.apply()
        self.assert_unpublished(result)
        self.assertTrue(result['warnings'])

    def test_foreign_replacement_temporary_is_preserved(self):
        module = api()
        foreign = self.root / 'foreign'
        foreign.write_bytes(b'foreign bytes')
        seen = []
        def replace(source, temporary, *args):
            os.replace(foreign, temporary)
            seen.append(temporary)
            raise OSError('temporary was replaced')
        with patch.object(module, '_verify_output', side_effect=replace):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertFalse(self.output.exists())
        self.assertEqual(seen[0].read_bytes(), b'foreign bytes')
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertTrue(result['warnings'])

    def test_cleanup_interruption_retains_committed_output(self):
        real_unlink = Path.unlink
        interrupted = []
        def unlink(path, *args, **kwargs):
            if path.name.startswith('.romancer-script-') and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt
            return real_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', new=unlink):
            result = self.apply()
        self.assertTrue(result['written'])
        self.assertTrue(result['cancelled'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['publication_status'], 'PUBLISHED')
        self.assertEqual(result['phase'], 'cleanup')
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), result['out_sha256'])
        self.assertEqual(list(self.root.glob('.romancer-script-*')), [])

    def test_unknown_publication_outcome_never_deletes_destination(self):
        module = api()
        real_link, real_owns = os.link, module._owns
        def link(*args):
            real_link(*args)
            raise OSError('lost publication acknowledgement')
        def owns(path, info):
            if path == self.output:
                raise OSError('cannot inspect published path')
            return real_owns(path, info)
        with patch.object(module, '_owns', side_effect=owns), patch('romancer.script_patch.os.link', side_effect=link):
            result = self.apply()
        self.assertFalse(result['ok'])
        self.assertIsNone(result['written'])
        self.assertEqual(result['publication_status'], 'UNKNOWN')
        self.assertTrue(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_slot_across_copy_chunk_boundary_keeps_every_neighbor(self):
        raw = bytearray(b'\xcc' * 70000)
        raw[:4] = bytes.fromhex('fcff0000')
        raw[4:8] = bytes.fromhex('00010018')
        raw[8:12] = bytes.fromhex('deadbeef')
        raw[65532:65544] = self.raw[8:20]
        raw[65560:65568] = self.raw[20:28]
        offsets = {'pa': (0, 4), 'pb': (4, 4), 'guard': (8, 4),
                   'a-slot': (65532, 12), 'b-slot': (65560, 8)}
        for rule in self.schema['profile']['rules']:
            offset, size = offsets[rule['resource']]
            rule.update(offset=offset, length=size, expected_hex=raw[offset:offset + size].hex())
        for pointer in self.schema['format']['pointers']:
            pointer['width'] = 4
        self.raw = bytes(raw)
        self.source.write_bytes(self.raw)
        self.schema['artifact']['size'] = len(raw)
        self.schema['profile']['accepted_sha256'] = [hashlib.sha256(raw).hexdigest()]
        result = self.apply()
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.output.read_bytes(), self.raw[:65532] + b'BA\xf0\x03B\x00'
                         + b'\xff' * 6 + self.raw[65544:])
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_write_and_flush_failure_close_stream_before_cleanup(self):
        for operation in ('write', 'flush'):
            for error in (OSError, KeyboardInterrupt):
                with self.subTest(operation=operation, error=error):
                    real_fdopen = os.fdopen
                    descriptors = []
                    class Stream:
                        def __init__(self, stream):
                            self.stream = stream
                        def fileno(self):
                            return self.stream.fileno()
                        def write(self, data):
                            if operation == 'write':
                                raise error('write failed')
                            return self.stream.write(data)
                        def flush(self):
                            if operation == 'flush':
                                raise error('flush failed')
                            return self.stream.flush()
                        def close(self):
                            self.stream.close()
                    def fdopen(fd, *args, **kwargs):
                        descriptors.append(fd)
                        return Stream(real_fdopen(fd, *args, **kwargs))
                    with patch('romancer.script_patch.os.fdopen', side_effect=fdopen):
                        result = self.apply()
                    self.assert_unpublished(result)
                    with self.assertRaises(OSError):
                        os.fstat(descriptors[0])

    def test_report_budget_blocks_before_publication(self):
        edits, plan_id = self.prepare()
        with patch('romancer.script.MAX_REPORT', 8192):
            result = api().apply_script(self.source, self.output, self.schema, edits,
                                        expected_plan_id=plan_id)
        self.assert_unpublished(result)
        self.assertEqual(result['error_code'], 'REPORT_LIMIT')

    def test_final_report_budget_after_unicode_cleanup_preserves_outcome(self):
        module = api()
        self.raw = bytes.fromhex('04000000') + b'A' * 35276 + b'\x00'
        self.source.write_bytes(self.raw)
        self.schema['artifact']['size'] = len(self.raw)
        self.schema['profile']['accepted_sha256'] = [hashlib.sha256(self.raw).hexdigest()]
        self.schema['profile']['rules'] = [
            {'resource': 'pa', 'offset': 0, 'length': 4, 'expected_hex': '04000000'},
            {'resource': 'a-slot', 'offset': 4, 'length': len(self.raw) - 4,
             'expected_hex': self.raw[4:].hex()},
        ]
        self.schema['format']['records'] = self.schema['format']['records'][:1]
        self.schema['format']['pointers'] = self.schema['format']['pointers'][:1]
        self.schema['format']['pointers'][0]['width'] = 4
        self.schema['format']['guards'] = []
        edits, plan_id = self.prepare([])
        real_unlink, real_link, real_owns = Path.unlink, os.link, module._owns
        diagnostic = chr(0x1f600) * 2048

        def unlink(path, *args, **kwargs):
            if path.name.startswith('.romancer-script-'):
                raise OSError(diagnostic)
            return real_unlink(path, *args, **kwargs)

        for outcome in ('published', 'cancelled', 'unknown', 'precommit'):
            with self.subTest(outcome=outcome):
                def link(*args, **kwargs):
                    real_link(*args, **kwargs)
                    if outcome == 'cancelled':
                        raise KeyboardInterrupt
                    if outcome == 'unknown':
                        raise OSError('lost publication acknowledgement')

                def owns(path, info):
                    if outcome == 'unknown' and path == self.output:
                        raise OSError(diagnostic)
                    return real_owns(path, info)

                with ExitStack() as stack:
                    stack.enter_context(patch.object(Path, 'unlink', new=unlink))
                    stack.enter_context(patch.object(module, '_owns', side_effect=owns))
                    stack.enter_context(patch('romancer.script_patch.os.link', side_effect=link))
                    if outcome == 'precommit':
                        stack.enter_context(patch.object(module, '_copy_output', side_effect=OSError(diagnostic)))
                    result = module.apply_script(self.source, self.output, self.schema, edits,
                                                 expected_plan_id=plan_id)
                try:
                    self.assertEqual(self.source.read_bytes(), self.raw)
                    if outcome == 'precommit':
                        self.assertIs(result['written'], False)
                        self.assertFalse(self.output.exists())
                    else:
                        self.assertEqual(self.output.read_bytes(), self.raw)
                        self.assertEqual(result['out_sha256'], hashlib.sha256(self.raw).hexdigest())
                        self.assertIs(result['written'], None if outcome == 'unknown' else True)
                        self.assertEqual(result['publication_status'],
                                         'UNKNOWN' if outcome == 'unknown' else 'PUBLISHED')
                    self.assertEqual(result['cancelled'], outcome == 'cancelled')
                    encoded = json.dumps(result, sort_keys=True, ensure_ascii=True,
                                         allow_nan=False, indent=2).encode('ascii') + b'\n'
                    self.assertLessEqual(len(encoded), 8 * 1024 * 1024)
                    self.assertFalse(result['ok'])
                    self.assertEqual(result['report_status'], 'FAIL')
                    self.assertEqual(result['report_error_code'], 'REPORT_LIMIT')
                    self.assertTrue(Path(result['temporary_path']).is_file())
                finally:
                    if self.output.exists():
                        self.output.unlink()
                    for path in self.root.glob('.romancer-script-*'):
                        path.unlink()

    def test_cancellation_during_final_report_check_retains_publication(self):
        model = importlib.import_module('romancer.script')
        real_size = model._report_size
        interrupted = []

        def report_size(result):
            if self.output.exists() and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt
            return real_size(result)

        with patch.object(model, '_report_size', side_effect=report_size):
            try:
                result = self.apply()
            except KeyboardInterrupt:
                self.fail('final report cancellation escaped without the published outcome')
        self.assertFalse(result['ok'])
        self.assertTrue(result['cancelled'])
        self.assertIs(result['written'], True)
        self.assertEqual(result['publication_status'], 'PUBLISHED')
        self.assertEqual(result['error_code'], 'CANCELLED')
        self.assertEqual(result['phase'], 'reporting')
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), result['out_sha256'])
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertLessEqual(len(json.dumps(result, indent=2, sort_keys=True,
                                            ensure_ascii=True).encode('ascii')) + 1, 8 * 1024 * 1024)
        self.assertEqual(list(self.root.glob('.romancer-script-*')), [])

    def test_linked_source_or_destination_parent_is_refused(self):
        alias = self.root / 'linked'
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'directory symlinks unavailable: {exc}')
        edits, plan_id = self.prepare()
        for source, output in ((alias / self.source.name, self.output),
                               (self.source, alias / self.output.name)):
            result = api().apply_script(source, output, self.schema, edits, expected_plan_id=plan_id)
            self.assert_unpublished(result)

    @unittest.skipUnless(os.name == 'nt', 'Windows path semantics')
    def test_windows_reserved_and_ads_output_spellings_reject(self):
        for name in ('NUL', 'original.bin:stream', 'ambiguous.', 'ambiguous '):
            with self.subTest(name=name):
                self.output = self.root / name
                result = self.apply()
                self.assertFalse(result['ok'])
                self.assertFalse(result['written'])
                self.assertEqual(self.source.read_bytes(), self.raw)


if __name__ == '__main__':
    unittest.main()
