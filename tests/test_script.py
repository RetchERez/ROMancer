import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.script_fixtures import fixed_fixture as literal_fixture


def service():
    return importlib.import_module('romancer.script')


def request(document, changes):
    return {'schema_version': 1, 'document_id': document['document_id'],
            'source_sha256': document['source_sha256'],
            'schema_sha256': document['schema_sha256'], 'changes': changes}


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer script ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'script.bin'
        self.raw, self.schema = literal_fixture()
        self.source.write_bytes(self.raw)

    def inspect(self):
        return service().inspect_script(self.source, self.schema)

    def plan(self, changes):
        return service().plan_script(self.source, self.schema, request(self.inspect(), changes))

    def rebind(self, raw):
        self.raw = bytes(raw)
        self.source.write_bytes(self.raw)
        self.schema['artifact']['size'] = len(self.raw)
        self.schema['profile']['accepted_sha256'] = [hashlib.sha256(self.raw).hexdigest()]
        for rule in self.schema['profile']['rules']:
            rule['expected_hex'] = self.raw[rule['offset']:rule['offset'] + rule['length']].hex()

    def test_service_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.script'))

    def test_literal_model_roundtrips_without_encoding(self):
        doc = self.inspect()
        self.assertTrue(doc['ok'])
        self.assertTrue(doc['write_supported'])
        self.assertEqual(doc['source_sha256'],
                         'e5f0ca597cdda5a3f9eb69bce7e4734e63eb1e64be61ef29d4e51e4e51db39b4')
        record = doc['records'][0]
        self.assertEqual(service().serialize_original(record), self.raw[8:20])
        self.assertEqual([x['text'] for x in record['segments']], ['A', 'B'])
        controls = [x for x in record['tokens'] if x['kind'] == 'control']
        self.assertEqual(controls[0]['raw_hex'], 'f003')
        self.assertEqual(controls[0]['offset'], 1)
        self.assertEqual((record['used_bytes'], record['padding_bytes']), (5, 7))

    def test_text_edit_has_literal_bytes_and_protects_control(self):
        plan = self.plan([{'record_id': 'a', 'segment': 0, 'text': 'BA'}])
        self.assertTrue(plan['ok'])
        self.assertEqual(plan['hunks'], [{'record_id': 'a', 'offset': 8,
                                         'before_hex': self.raw[8:20].hex(),
                                         'after_hex': (b'BA\xf0\x03B\x00' + b'\xff' * 6).hex()}])
        self.assertEqual(plan['final_records'][0]['segments'][1]['text'], 'B')
        self.assertEqual(plan['pointers'][0]['target_offset'], 8)

    def test_empty_and_identical_changes_are_explicit_roundtrips(self):
        for changes in ([], [{'record_id': 'a', 'segment': 0, 'text': 'A'}]):
            plan = self.plan(changes)
            self.assertTrue(plan['ok'])
            self.assertEqual(plan['status'], 'NO_CHANGES')
            self.assertEqual(plan['hunks'], [])

    def test_capacity_exact_and_overflow(self):
        exact = self.plan([{'record_id': 'a', 'segment': 0, 'text': 'A' * 8}])
        self.assertTrue(exact['ok'])
        self.assertEqual(bytes.fromhex(exact['hunks'][0]['after_hex']), b'A' * 8 + b'\xf0\x03B\x00')
        overflow = self.plan([{'record_id': 'a', 'segment': 0, 'text': 'A' * 9}])
        self.assertFalse(overflow['ok'])
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_reserved_control_arguments_and_empty_segments(self):
        self.rebind(self.raw[:8] + b'\xf0\x00\xf0\xff\x00' + b'\xff' * 7 + self.raw[20:])
        record = self.inspect()['records'][0]
        self.assertEqual([x['text'] for x in record['segments']], ['', '', ''])
        self.assertEqual(service().serialize_original(record), self.raw[8:20])
        plan = self.plan([{'record_id': 'a', 'segment': 1, 'text': 'AB'}])
        self.assertTrue(plan['ok'])
        self.assertEqual(bytes.fromhex(plan['hunks'][0]['after_hex']),
                         b'\xf0\x00AB\xf0\xff\x00' + b'\xff' * 5)

    def test_malformed_slots_stay_lossless_read_only(self):
        for slot in (b'\x99\x00' + b'\xff' * 10, b'A' * 12,
                     b'A' * 11 + b'\xf0', b'A\x00X' + b'\xff' * 9):
            with self.subTest(slot=slot):
                self.rebind(self.raw[:8] + slot + self.raw[20:])
                doc = self.inspect()
                self.assertTrue(doc['ok'])
                self.assertFalse(doc['write_supported'])
                self.assertEqual(doc['status'], 'READ_ONLY')
                self.assertEqual(service().serialize_original(doc['records'][0]), slot)
                self.assertFalse(service().plan_script(self.source, self.schema, request(doc, []))['ok'])

    def test_unsupported_family_never_compiles(self):
        self.schema['format']['family'] = 'unknown-events'
        doc = self.inspect()
        self.assertEqual(doc['status'], 'READ_ONLY')
        self.assertFalse(doc['write_supported'])
        self.assertFalse(service().plan_script(self.source, self.schema, request(doc, []))['ok'])

    def test_invalid_edits_cannot_inject_bytes_or_controls(self):
        doc = self.inspect()
        cases = [
            [{'record_id': 'a', 'segment': 0, 'text': '<F0>'}],
            [{'record_id': 'a', 'segment': 0, 'text': 'A\nB'}],
            [{'record_id': 'a', 'segment': True, 'text': 'A'}],
            [{'record_id': 'unknown', 'segment': 0, 'text': 'A'}],
            [{'record_id': 'a', 'segment': 99, 'text': 'A'}],
            [{'record_id': 'a', 'segment': 0, 'text': 'A', 'after_hex': '00'}],
            [{'record_id': 'a', 'segment': 0, 'text': 'A'}] * 2,
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                result = service().plan_script(self.source, self.schema, request(doc, changes))
                self.assertFalse(result['ok'])

    def test_bindings_and_untrusted_authority_are_rejected(self):
        doc = self.inspect()
        for field in ('document_id', 'source_sha256', 'schema_sha256'):
            edits = request(doc, [])
            edits[field] = '0' * 64
            self.assertFalse(service().plan_script(self.source, self.schema, edits)['ok'])
        edits = request(doc, [])
        edits['hunks'] = [{'offset': 0, 'after_hex': 'ffff'}]
        edits['ok'] = True
        self.assertFalse(service().plan_script(self.source, self.schema, edits)['ok'])

    def test_pointer_interior_and_wrong_targets_block(self):
        for pointer in (b'\x09\x00', b'\xff\xff', b'\x07\x00'):
            with self.subTest(pointer=pointer):
                self.rebind(pointer + self.raw[2:])
                self.assertFalse(self.inspect()['ok'])

    def test_pointer_nonzero_base_and_shared_target(self):
        self.schema['format']['pointers'][0]['base'] = 4
        self.rebind(b'\x04\x00' + self.raw[2:])
        self.assertEqual(self.inspect()['pointers'][0]['target_offset'], 8)
        self.schema['profile']['rules'][2] = {'resource': 'guard', 'offset': 4,
                                             'length': 2, 'expected_hex': '0800'}
        self.schema['format']['guards'] = []
        self.schema['format']['pointers'].append({'id': 'shared', 'rule': 'guard',
            'target_record': 'a', 'width': 2, 'endian': 'little', 'base': 0})
        self.rebind(self.raw[:4] + b'\x08\x00' + self.raw[6:])
        self.assertTrue(self.inspect()['write_supported'])

    def test_wrong_revision_blocks_before_reading_slot(self):
        self.source.write_bytes(b'wrong revision')
        with patch('romancer.script.parse_slot', side_effect=AssertionError('must not parse')):
            self.assertFalse(self.inspect()['ok'])

    def test_wrong_revision_retains_measured_hash_in_diagnostic(self):
        changed = self.raw[:-1] + b'X'
        self.source.write_bytes(changed)
        result = self.inspect()
        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], 'REVISION_MISMATCH')
        self.assertEqual(result['source_sha256'], hashlib.sha256(changed).hexdigest())
        self.assertEqual(result['source_size'], len(changed))

    def test_postinspection_plan_failures_retain_measured_identity(self):
        doc = self.inspect()
        for code in ('CAPACITY', 'STALE_REQUEST'):
            with self.subTest(code=code):
                edits = request(doc, [{'record_id': 'a', 'segment': 0, 'text': 'A' * 9}]
                                if code == 'CAPACITY' else [])
                if code == 'STALE_REQUEST':
                    edits.update(source_sha256='0' * 64, schema_sha256='0' * 64)
                result = service().plan_script(self.source, self.schema, edits)
                self.assertFalse(result['ok'])
                self.assertEqual(result['error_code'], code)
                self.assertEqual(result['source_sha256'], hashlib.sha256(self.raw).hexdigest())
                self.assertEqual(result['schema_sha256'], doc['schema_sha256'])
                self.assertEqual(result['source_size'], len(self.raw))
                self.assertEqual(self.source.read_bytes(), self.raw)

    def test_plan_before_inspection_does_not_invent_measured_identity(self):
        edits = request(self.inspect(), [])
        self.source.unlink()
        result = service().plan_script(self.source, self.schema, edits)
        self.assertFalse(result['ok'])
        for key in ('source_sha256', 'schema_sha256', 'source_size'):
            self.assertIsNone(result[key])

    def test_report_budget_counts_pretty_printed_json(self):
        doc = self.inspect()
        compact_size = len(json.dumps(doc, ensure_ascii=True, sort_keys=True).encode('ascii'))
        with patch('romancer.script.MAX_REPORT', compact_size + 1):
            result = self.inspect()
        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], 'REPORT_LIMIT')

    def test_independent_document_identity_and_plan_sorting(self):
        doc = self.inspect()
        identity = {key: doc[key] for key in ('parser_version', 'schema_sha256',
                                             'source_sha256', 'source_size')}
        expected = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                                             ensure_ascii=True).encode('ascii')).hexdigest()
        self.assertEqual(doc['document_id'], expected)
        changes = [{'record_id': 'b', 'segment': 0, 'text': 'A'},
                   {'record_id': 'a', 'segment': 0, 'text': 'BA'}]
        self.assertEqual(self.plan(changes)['plan_id'], self.plan(changes[::-1])['plan_id'])
        old = self.plan(changes)['plan_id']
        with patch('romancer.script.ROMANCER_VERSION', 'future'):
            self.assertNotEqual(self.plan(changes)['plan_id'], old)

    def test_large_guard_is_read_in_bounded_chunks(self):
        self.schema['profile']['rules'].append({'resource': 'tail', 'offset': 32,
            'length': 65537, 'expected_hex': '00' * 65537})
        self.schema['format']['guards'].append('tail')
        self.rebind(self.raw + b'\x00' * 65537)
        real_open = Path.open
        case = self
        class Reader:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def seek(self, *args):
                return self.stream.seek(*args)
            def read(self, size):
                case.assertLessEqual(size, 65536)
                case.assertGreaterEqual(size, 0)
                return self.stream.read(size)
        def open_path(path, *args, **kwargs):
            stream = real_open(path, *args, **kwargs)
            return Reader(stream) if path == self.source else stream
        with patch.object(Path, 'open', new=open_path):
            self.assertTrue(self.inspect()['ok'])

    def test_source_change_during_slot_parsing_blocks_inspection(self):
        module = service()
        real_parse = module.parse_slot
        changed = self.raw[:-1] + b'X'
        def parse(*args):
            result = real_parse(*args)
            self.source.write_bytes(changed)
            return result
        with patch.object(module, 'parse_slot', side_effect=parse):
            result = self.inspect()
        self.assertFalse(result['ok'])
        self.assertEqual(self.source.read_bytes(), changed)

    def test_pointer_three_and_four_byte_both_endian(self):
        for width in (3, 4):
            for endian in ('little', 'big'):
                with self.subTest(width=width, endian=endian):
                    self.raw, self.schema = literal_fixture()
                    self.schema['profile']['rules'] = [row for row in self.schema['profile']['rules']
                                                        if row['resource'] != 'guard']
                    self.schema['format']['guards'] = []
                    for pointer, offset, target in zip(self.schema['format']['pointers'], (0, 4), (8, 20)):
                        pointer.update(width=width, endian=endian)
                        rule = next(row for row in self.schema['profile']['rules'] if row['resource'] == pointer['rule'])
                        rule.update(offset=offset, length=width)
                        self.raw = self.raw[:offset] + target.to_bytes(width, endian) + self.raw[offset + width:]
                    self.rebind(self.raw)
                    self.assertEqual([row['target_offset'] for row in self.inspect()['pointers']], [8, 20])

    def test_plan_freezes_caller_request_before_source_reads(self):
        doc = self.inspect()
        edits = request(doc, [{'record_id': 'a', 'segment': 0, 'text': 'BA'}])
        module = service()
        real_inspect = module.inspect_stream
        def inspect(*args):
            edits['changes'][0]['text'] = 'B' * 100
            self.schema['format']['records'][0]['annotations']['label'] = 'later caller mutation'
            return real_inspect(*args)
        with patch.object(module, 'inspect_stream', side_effect=inspect):
            result = module.plan_script(self.source, self.schema, edits)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['normalized_changes'][0]['text'], 'BA')
        self.assertIsNone(result['final_records'][0]['annotations']['label'])


if __name__ == '__main__':
    unittest.main()
