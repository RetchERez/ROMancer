import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.script_fixtures import fixed_fixture


def api():
    return importlib.import_module('romancer.script_schema')


def changed(schema, path, value):
    result = copy.deepcopy(schema)
    parent = result
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    return result


class ScriptSchemaTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.schema = fixed_fixture()

    def test_fixture_is_literal_independent_and_fresh(self):
        self.assertEqual(self.raw.hex(), '08000014deadbeef41f0034200ffffffffffffff424100ffffffffff11223344')
        self.assertEqual(len(self.raw), 32)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),
                         'e5f0ca597cdda5a3f9eb69bce7e4734e63eb1e64be61ef29d4e51e4e51db39b4')
        for rule in self.schema['profile']['rules']:
            self.assertEqual(self.raw[rule['offset']:rule['offset'] + rule['length']],
                             bytes.fromhex(rule['expected_hex']))
        self.assertEqual(int.from_bytes(self.raw[:2], 'little'), 8)
        self.assertEqual(int.from_bytes(self.raw[2:4], 'big'), 20)
        self.schema['format']['records'][0]['annotations']['label'] = 'changed'
        self.assertIsNone(self.schema['format']['records'][1]['annotations']['label'])
        self.assertIsNone(fixed_fixture()[1]['format']['records'][0]['annotations']['label'])

    def test_public_interfaces_and_budget_constants(self):
        for name in ('load_script_json', 'canonical_bytes', 'validate_schema'):
            self.assertTrue(callable(getattr(api(), name, None)), name)
        expected = {'SCHEMA_VERSION': 1, 'MAX_SCHEMA_JSON_BYTES': 4 * 1024 * 1024,
                    'MAX_EDITS_JSON_BYTES': 1024 * 1024, 'MAX_OUTPUT_JSON_BYTES': 8 * 1024 * 1024,
                    'MAX_JSON_DEPTH': 32, 'MAX_JSON_NODES': 100000,
                    'MAX_ARTIFACT_BYTES': 64 * 1024 * 1024, 'READ_CHUNK_BYTES': 64 * 1024,
                    'MAX_REVISIONS': 16, 'MAX_RECORDS': 256, 'MAX_POINTERS': 512,
                    'MAX_RULES': 1024, 'MAX_SLOT_BYTES': 64 * 1024,
                    'MAX_TOTAL_RULE_BYTES': 256 * 1024, 'MAX_GLYPHS': 256,
                    'MAX_CONTROLS': 64, 'MAX_TOKENS': 4096, 'MAX_CHANGES': 1024,
                    'MAX_REPLACEMENT_SCALARS': 65536}
        for key, value in expected.items():
            self.assertEqual(getattr(api(), key, None), value, key)

    def test_supported_schema_detaches_and_hashes_exact_normalized_data(self):
        result = api().validate_schema(self.schema)
        self.assertEqual(set(result), {'normalized_schema', 'schema_sha256', 'write_supported', 'read_only_reasons'})
        self.assertTrue(result['write_supported'])
        self.assertEqual(result['read_only_reasons'], [])
        expected = json.dumps(self.schema, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
        self.assertEqual(result['schema_sha256'], hashlib.sha256(expected).hexdigest())
        self.schema['format']['encoding']['glyphs'][0]['text'] = 'Z'
        self.assertEqual(result['normalized_schema']['format']['encoding']['glyphs'][0]['text'], 'A')
        result['normalized_schema']['format']['records'].clear()
        self.assertEqual(len(fixed_fixture()[1]['format']['records']), 2)

    def test_v34_profile_normalization_and_json_key_order_are_canonical(self):
        first = api().validate_schema(self.schema)
        self.schema['profile']['rules'].reverse()
        self.schema['profile']['accepted_sha256'][0] = self.schema['profile']['accepted_sha256'][0].upper()
        self.schema['profile']['rules'][2]['expected_hex'] = 'DEADBEEF'
        second = api().validate_schema(dict(reversed(list(self.schema.items()))))
        self.assertEqual(first, second)

    def test_annotations_rules_and_profile_details_bind_schema_hash(self):
        original = api().validate_schema(self.schema)['schema_sha256']
        for path, value in [
            (('format', 'records', 0, 'annotations', 'label'), 'Declared label'),
            (('profile', 'rules', 2, 'expected_hex'), '01020304'),
            (('profile', 'accepted_sha256'), ['0' * 64]),
            (('profile', 'provenance'), {'claim': 'inert'}),
            (('format', 'controls', 0, 'layout_role'), 'opaque'),
        ]:
            with self.subTest(path=path):
                self.assertNotEqual(api().validate_schema(changed(self.schema, path, value))['schema_sha256'], original)

    def test_unsupported_declarations_are_explicit_read_only(self):
        for path, value in [
            (('format',), {'family': 'banked-events', 'version': 1, 'opaque': [1, 2]}),
            (('format', 'version'), 2),
            (('artifact', 'kind'), 'rom-container'),
            (('artifact', 'integrity'), 'checksum-required'),
            (('format', 'encoding'), {'kind': 'multibyte', 'opaque': {'table': 'inert'}}),
            (('format', 'controls', 0, 'position_independent'), False),
        ]:
            with self.subTest(path=path):
                schema = changed(self.schema, path, value)
                result = api().validate_schema(schema)
                self.assertFalse(result['write_supported'])
                self.assertTrue(result['read_only_reasons'])
                self.assertTrue(all(type(reason) is str and reason for reason in result['read_only_reasons']))
                self.assertEqual(result['normalized_schema']['format'], schema['format'])

    def test_known_grammar_errors_do_not_become_read_only(self):
        self.schema['artifact']['kind'] = 'rom-container'
        self.schema['format']['pointers'][0]['width'] = True
        with self.assertRaises(ValueError):
            api().validate_schema(self.schema)

    def test_exact_fields_required_in_every_supported_object(self):
        paths = [(), ('artifact',), ('profile',), ('profile', 'rules', 0), ('format',),
                 ('format', 'encoding'), ('format', 'encoding', 'glyphs', 0),
                 ('format', 'controls', 0), ('format', 'terminator'), ('format', 'padding'),
                 ('format', 'records', 0), ('format', 'records', 0, 'annotations'),
                 ('format', 'pointers', 0)]
        for path in paths:
            original = self.schema
            for key in path:
                original = original[key]
            variants = [{**original, 'unknown': 1}]
            variants.extend({key: value for key, value in original.items() if key != removed}
                            for removed in original)
            for variant in variants:
                with self.subTest(path=path, keys=tuple(variant)), self.assertRaises(ValueError):
                    api().validate_schema(changed(self.schema, path, variant) if path else variant)

    def test_known_field_types_ranges_and_labels(self):
        cases = [
            (('schema_version',), [True, 0, 2, '1']),
            (('id',), ['', ' ', 'x' * 129, 'bad\x00', 'bad\x7f', 'bad\x85', 1]),
            (('version',), ['', True, 'x' * 129]),
            (('artifact', 'kind'), ['', 1]), (('artifact', 'integrity'), ['', False]),
            (('artifact', 'size'), [True, 0, -1, 64 * 1024 * 1024 + 1, 1.0]),
            (('format', 'family'), ['', 1]), (('format', 'version'), [True, 0, -1, '1']),
            (('format', 'encoding', 'kind'), ['', 1]),
            (('format', 'encoding', 'glyphs', 0, 'byte'), [True, -1, 256, 65.0]),
            (('format', 'encoding', 'glyphs', 0, 'text'), ['', 'AB', '\x00', '\x1f', '\x7f', '\x9f', 65]),
            (('format', 'controls', 0, 'id'), ['', 'x' * 129, 'bad\x85']),
            (('format', 'controls', 0, 'opcode'), [True, -1, 256]),
            (('format', 'controls', 0, 'argument_length'), [True, -1, 17, 1.0]),
            (('format', 'controls', 0, 'position_independent'), [1, None, 'true']),
            (('format', 'controls', 0, 'layout_role'), ['unknown', None]),
            (('format', 'terminator', 'byte'), [True, -1, 256]),
            (('format', 'padding', 'byte'), [True, -1, 256]),
            (('format', 'records', 0, 'id'), ['', 'x' * 129]),
            (('format', 'records', 0, 'annotations', 'label'), ['', 'x' * 257, 'bad\x85', 1]),
            (('format', 'records', 0, 'annotations', 'speaker_label'), ['unpaired']),
            (('format', 'records', 0, 'annotations', 'speaker_provenance'), ['unpaired']),
            (('format', 'pointers', 0, 'id'), ['', 'x' * 129]),
            (('format', 'pointers', 0, 'width'), [True, 1, 5, '2']),
            (('format', 'pointers', 0, 'endian'), ['native', 1]),
            (('format', 'pointers', 0, 'base'), [True, -1, 1.0]),
            (('profile', 'rules', 0, 'offset'), [True, -1, 32, 2**100]),
            (('profile', 'rules', 0, 'length'), [True, 0, -1, 33]),
            (('profile', 'rules', 0, 'expected_hex'), ['08', '08 00', 'xxxx']),
        ]
        for path, values in cases:
            for value in values:
                with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                    api().validate_schema(changed(self.schema, path, value))

    def test_collections_and_complete_unique_rule_ownership(self):
        for path, value in [
            (('format', 'records'), []), (('format', 'pointers'), []),
            (('format', 'guards'), None), (('format', 'controls'), {}),
            (('format', 'encoding', 'glyphs'), {}),
            (('format', 'records', 1, 'id'), 'a'),
            (('format', 'records', 1, 'rule'), 'a-slot'),
            (('format', 'records', 0, 'rule'), 'missing'),
            (('format', 'pointers', 1, 'id'), 'pa'),
            (('format', 'pointers', 1, 'rule'), 'pa'),
            (('format', 'pointers', 0, 'rule'), 'guard'),
            (('format', 'pointers', 0, 'target_record'), 'missing'),
            (('format', 'guards'), []), (('format', 'guards'), ['guard', 'guard']),
            (('format', 'guards'), ['guard', 'pa']), (('format', 'guards'), ['missing']),
            (('profile', 'rules', 1, 'resource'), 'pa'),
            (('profile', 'rules', 2, 'offset'), 3),
            (('format', 'pointers'), [self.schema['format']['pointers'][0]]),
        ]:
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                api().validate_schema(changed(self.schema, path, value))

    def test_byte_classes_and_reverse_map_are_disjoint(self):
        for path, value in [
            (('format', 'encoding', 'glyphs', 1, 'byte'), 65),
            (('format', 'encoding', 'glyphs', 1, 'text'), 'A'),
            (('format', 'controls'), self.schema['format']['controls'] * 2),
            (('format', 'controls', 0, 'opcode'), 65),
            (('format', 'terminator', 'byte'), 65),
            (('format', 'terminator', 'byte'), 240),
            (('format', 'padding', 'byte'), 65),
            (('format', 'padding', 'byte'), 240),
            (('format', 'padding', 'byte'), 0),
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                api().validate_schema(changed(self.schema, path, value))
        for field in ('id', 'opcode'):
            schema = copy.deepcopy(self.schema)
            second = {**schema['format']['controls'][0], 'id': 'other', 'opcode': 241}
            second[field] = schema['format']['controls'][0][field]
            schema['format']['controls'].append(second)
            with self.subTest(field=field), self.assertRaises(ValueError):
                api().validate_schema(schema)

    def test_unicode_scalars_are_not_normalized_or_case_folded(self):
        self.schema['format']['encoding']['glyphs'] = [
            {'byte': 65, 'text': '\U0001f600'}, {'byte': 66, 'text': '\u0301'},
            {'byte': 67, 'text': 'a'}, {'byte': 68, 'text': 'A'}]
        annotations = self.schema['format']['records'][0]['annotations']
        annotations.update(speaker_label='Declared', speaker_provenance='Profile assertion')
        result = api().validate_schema(self.schema)
        self.assertTrue(result['write_supported'])
        self.assertEqual(result['normalized_schema']['format'], self.schema['format'])

    def test_space_and_other_noncontrol_whitespace_are_valid_glyphs(self):
        for text in (' ', '\u00a0', '\u2028'):
            with self.subTest(text=repr(text)):
                self.schema['format']['encoding']['glyphs'][0]['text'] = text
                result = api().validate_schema(self.schema)
                self.assertTrue(result['write_supported'])
                self.assertEqual(result['normalized_schema']['format']['encoding']['glyphs'][0]['text'], text)

    def test_inclusive_slot_total_rule_artifact_and_revision_budgets(self):
        self.schema['artifact']['size'] = 64 * 1024 * 1024
        self.schema['profile']['accepted_sha256'] += [f'{i:064x}' for i in range(15)]
        self.schema['profile']['rules'] = [
            {'resource': 'pa', 'offset': 0, 'length': 2, 'expected_hex': '0200'},
            {'resource': 'a-slot', 'offset': 2, 'length': 65536,
             'expected_hex': '4100' + 'ff' * 65534},
            {'resource': 'guard', 'offset': 65538, 'length': 196606,
             'expected_hex': '00' * 196606}]
        self.schema['format']['records'] = self.schema['format']['records'][:1]
        self.schema['format']['pointers'] = self.schema['format']['pointers'][:1]
        self.assertTrue(api().validate_schema(self.schema)['write_supported'])

    def test_unsupported_api_data_still_obeys_scalar_cycle_and_schema_byte_limits(self):
        cycle = {}
        cycle['self'] = cycle
        for value in (cycle, '\ud800', 'a' * (4 * 1024 * 1024)):
            schema = copy.deepcopy(self.schema)
            schema['format'] = {'family': 'unknown', 'version': 1, 'opaque': value}
            with self.subTest(kind=type(value)), patch('romancer.contracts.validate_contract',
                    side_effect=AssertionError('v34 called on over-budget/invalid JSON')):
                with self.assertRaises(ValueError):
                    api().validate_schema(schema)

    def test_pointer_expected_bytes_must_target_exact_start_and_fit_width(self):
        for path, value in [
            (('profile', 'rules', 0, 'expected_hex'), '0900'),
            (('profile', 'rules', 0, 'expected_hex'), 'ffff'),
            (('format', 'pointers', 0, 'base'), 9),
            (('format', 'pointers', 0, 'endian'), 'big'),
        ]:
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                api().validate_schema(changed(self.schema, path, value))
        self.schema['artifact']['size'] = 70000
        self.schema['profile']['rules'][3]['offset'] = 65536
        with self.assertRaises(ValueError):
            api().validate_schema(self.schema)

    def test_pointer_widths_endians_nonzero_bases_and_shared_starts(self):
        for width in (2, 3, 4):
            for endian in ('little', 'big'):
                schema = copy.deepcopy(self.schema)
                schema['artifact']['size'] = 40
                schema['profile']['rules'][0].update(offset=32, length=width,
                                                     expected_hex=(3).to_bytes(width, endian).hex())
                schema['format']['pointers'][0].update(width=width, endian=endian, base=5)
                schema['profile']['rules'].append({'resource': 'shared', 'offset': 36,
                                                  'length': 4, 'expected_hex': '00000008'})
                schema['format']['pointers'].append({'id': 'shared', 'rule': 'shared',
                    'target_record': 'a', 'width': 4, 'endian': 'big', 'base': 0})
                with self.subTest(width=width, endian=endian):
                    self.assertTrue(api().validate_schema(schema)['write_supported'])

    def test_tighter_budgets_reject_before_v34_expansion_even_if_unsupported(self):
        mutations = [
            (('profile', 'accepted_sha256'), [f'{index:064x}' for index in range(17)]),
            (('profile', 'rules'), self.schema['profile']['rules'][:1] * 1025),
            (('format', 'records'), self.schema['format']['records'][:1] * 257),
            (('format', 'pointers'), self.schema['format']['pointers'][:1] * 513),
            (('format', 'controls'), self.schema['format']['controls'] * 65),
            (('format', 'encoding', 'glyphs'), [{'byte': 65, 'text': 'A'}] * 257),
        ]
        total_rules = [{'resource': str(i), 'offset': i * 65536, 'length': 65536,
                        'expected_hex': '00' * 65536} for i in range(5)]
        for path, value in mutations + [(('profile', 'rules'), total_rules)]:
            schema = changed(self.schema, path, value)
            schema['artifact']['size'] = 1024 * 1024
            schema['artifact']['integrity'] = 'unsupported'
            with self.subTest(path=path), patch('romancer.contracts.validate_contract',
                    side_effect=AssertionError('v34 called before budget rejection')):
                with self.assertRaises(ValueError):
                    api().validate_schema(schema)
        schema = copy.deepcopy(self.schema)
        schema['artifact']['size'] = 1024 * 1024
        schema['profile']['rules'][3].update(length=65537, expected_hex='00' * 65537)
        with patch('romancer.contracts.validate_contract', side_effect=AssertionError('v34 expanded oversized slot')):
            with self.assertRaises(ValueError):
                api().validate_schema(schema)


class ScriptJsonTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='script schema ')
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'schema.json'

    def test_canonical_exact_bytes_and_size_boundary(self):
        value = {'z': '\U0001f600', 'a': [True, None, 1.25]}
        expected = b'{"a":[true,null,1.25],"z":"\\ud83d\\ude00"}'
        self.assertEqual(api().canonical_bytes(value, max_bytes=len(expected)), expected)
        with self.assertRaises(ValueError):
            api().canonical_bytes(value, max_bytes=len(expected) - 1)
        for limit in (True, 0, -1, 1.0):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                api().canonical_bytes({}, max_bytes=limit)

    def test_non_json_cycles_nonfinite_and_surrogates_rejected(self):
        cycle = []
        cycle.append(cycle)
        for value in (cycle, (1,), {1: 'key'}, b'bytes', {1, 2}, float('nan'), float('inf'),
                      '\ud800', {'\udfff': 1}):
            with self.subTest(kind=type(value)), self.assertRaises(ValueError):
                api().canonical_bytes(value, max_bytes=4 * 1024 * 1024)
        shared = {'x': []}
        self.assertEqual(api().canonical_bytes([shared, shared], max_bytes=100), b'[{"x":[]},{"x":[]}]')

    def test_depth_and_node_budgets_include_api_objects(self):
        value = 0
        for _ in range(32):
            value = [value]
        api().canonical_bytes(value, max_bytes=1000)
        with self.assertRaises(ValueError):
            api().canonical_bytes([value], max_bytes=1000)
        api().canonical_bytes([None] * 99999, max_bytes=1024 * 1024)
        with self.assertRaises(ValueError):
            api().canonical_bytes([None] * 100000, max_bytes=1024 * 1024)
        schema = fixed_fixture()[1]
        schema['format'] = {'family': 'unknown', 'version': 1, 'opaque': [None] * 100000}
        with self.assertRaises(ValueError):
            api().validate_schema(schema)

    def test_literal_json_rejects_duplicates_nonfinite_surrogates_and_nonobjects(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":{"x":1,"x":2}}', b'{"x":NaN}',
                    b'{"x":Infinity}', b'{"x":1e999}', b'{"x":"\\ud800"}',
                    b'{"\\udfff":1}', b'{"x":"\xff"}', b'[]', b'null', b'{} trailing'):
            self.path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                api().load_script_json(self.path, max_bytes=1024)

    def test_literal_json_actual_bytes_depth_and_nodes_are_bounded(self):
        for raw in (b'{}' + b' ' * 1023, b'{"x":' + b'[' * 33 + b'0' + b']' * 33 + b'}',
                    b'{"x":[' + b'null,' * 99999 + b'null]}'):
            self.path.write_bytes(raw)
            limit = 1024 if len(raw) == 1025 else 1024 * 1024
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                api().load_script_json(self.path, max_bytes=limit)

    def test_loader_detaches_and_bounds_each_read(self):
        raw = b'{"x":"' + b'a' * 70000 + b'"}'
        self.path.write_bytes(raw)
        original_open = Path.open
        sizes = []
        class Stream:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def __getattr__(self, name):
                return getattr(self.stream, name)
            def read(self, size=-1):
                sizes.append(size)
                return self.stream.read(size)
        with patch.object(Path, 'open', lambda path, *args, **kwargs: Stream(original_open(path, *args, **kwargs))):
            result = api().load_script_json(self.path, max_bytes=len(raw))
        self.assertEqual(result, {'x': 'a' * 70000})
        self.assertTrue(sizes and all(0 < size <= 65536 for size in sizes))
        self.path.write_bytes(b'{"x":"changed"}')
        self.assertEqual(len(result['x']), 70000)

    def test_mid_read_same_size_rewrite_with_restored_mtime_rejected(self):
        raw = b'{"x":"before"}'
        self.path.write_bytes(raw)
        initial = self.path.stat()
        original_open = Path.open
        mutated = []
        target = self.path
        class Stream:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def __getattr__(self, name):
                return getattr(self.stream, name)
            def read(self, size=-1):
                chunk = self.stream.read(size)
                if chunk and not mutated:
                    mutated.append(True)
                    with original_open(target, 'wb') as writer:
                        writer.write(b'{"x":"after!"}')
                    os.utime(target, ns=(initial.st_atime_ns, initial.st_mtime_ns))
                return chunk
        with patch.object(Path, 'open', lambda path, *args, **kwargs: Stream(original_open(path, *args, **kwargs))):
            with self.assertRaises(ValueError):
                api().load_script_json(self.path, max_bytes=1024)
        self.assertEqual(self.path.read_bytes(), b'{"x":"after!"}')

    def test_loader_rejects_replaced_or_missing_path_after_content_passes(self):
        for action in ('replace', 'remove'):
            self.path.write_bytes(b'{"x":1}')
            replacement = self.path.with_name('replacement.json')
            replacement.write_bytes(b'{"x":1}')
            initial = self.path.stat()
            os.utime(replacement, ns=(initial.st_atime_ns, initial.st_mtime_ns))
            original_stat = Path.stat
            target = self.path
            calls = []
            def path_stat(path, *args, **kwargs):
                if path == target:
                    calls.append(path)
                    if len(calls) == 3:
                        if action == 'replace':
                            return original_stat(replacement)
                        raise FileNotFoundError('path disappeared after capture')
                return original_stat(path, *args, **kwargs)
            with self.subTest(action=action), patch.object(Path, 'stat', path_stat):
                with self.assertRaises((ValueError, OSError)):
                    api().load_script_json(self.path, max_bytes=1024)

    def test_loader_counts_actual_growth_not_only_initial_size(self):
        self.path.write_bytes(b'{}')
        original_open = Path.open
        target = self.path
        grown = []
        class Stream:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def __getattr__(self, name):
                return getattr(self.stream, name)
            def read(self, size=-1):
                if not grown:
                    grown.append(True)
                    with original_open(target, 'ab') as writer:
                        writer.write(b' ' * 128)
                return self.stream.read(size)
        with patch.object(Path, 'open', lambda path, *args, **kwargs: Stream(original_open(path, *args, **kwargs))):
            with self.assertRaisesRegex(ValueError, 'byte budget'):
                api().load_script_json(self.path, max_bytes=64)


if __name__ == '__main__':
    unittest.main()
