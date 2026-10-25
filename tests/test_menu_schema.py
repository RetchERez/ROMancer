import copy
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tests.menu_fixtures import (RGB_A, RGB_B, comparison_fixture, digest_json,
                                menu_fixture, write_menu_fixture)


class MenuSchemaTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.menu_schema'),
                             'Task 1 menu schema service is not implemented')
        self.model = importlib.import_module('romancer.menu_schema')
        self.fixture = menu_fixture()
        self.profile = self.fixture['profile']
        self.script = self.fixture['script_schema']
        self.cases = self.fixture['cases']

    def validate(self, profile=None):
        return self.model.validate_menu_profile(self.profile if profile is None else profile, self.script)

    def validate_cases(self, cases=None):
        profile = self.validate()
        return self.model.validate_menu_cases(self.cases if cases is None else cases, profile['normalized'])

    def rebind_cases(self):
        self.cases['profile_sha256'] = self.validate()['sha256']

    def test_profile_binds_schema_and_separate_guard_fields(self):
        result = self.validate()
        self.assertEqual(result, {'normalized': self.profile, 'sha256': digest_json(self.profile),
            'supported': True, 'read_only_reasons': [],
            'glyph_map_sha256': digest_json(self.profile['glyph_map'])})
        fields = result['normalized']['numeric_fields']
        self.assertEqual([(f['id'], f['source']) for f in fields], [
            ('price', {'kind': 'resource_guard', 'rule': 'price'}),
            ('quantity', {'kind': 'resource_guard', 'rule': 'quantity'}),
            ('fee', {'kind': 'case_bytes'})])
        result['normalized']['entries'][0]['states']['selected'][0]['record_id'] = 'caller-change'
        self.assertEqual(self.profile['entries'][0]['states']['selected'][0]['record_id'], 'b')

    def test_fixture_literals_and_existing_schema_font_contracts(self):
        from romancer.script_schema import validate_schema
        from romancer.font_metrics import measure_font, validate_font_schema
        raw = self.fixture['raw']
        self.assertEqual(raw, bytes.fromhex('08001400deadbeef414200ffffffffff1234a55a'
                                            '424100ffffffffff ff00c33c'))
        self.assertEqual(len(raw), 32)
        self.assertEqual(raw[16:20], bytes.fromhex('1234a55a'))
        self.assertEqual(raw[28:32], bytes.fromhex('ff00c33c'))
        self.assertEqual(validate_schema(self.script)['schema_sha256'], self.profile['script_schema_sha256'])
        self.assertEqual(self.script['format']['encoding']['glyphs'],
                         [{'byte': 65, 'text': 'A'}, {'byte': 66, 'text': 'B'}])
        with tempfile.TemporaryDirectory(prefix='ROMancer menu ') as directory:
            paths = write_menu_fixture(Path(directory) / 'files with spaces', self.fixture)
            self.assertEqual(set(paths), {'source', 'font', 'script_schema', 'profile', 'cases', 'font_schema'})
            self.assertEqual(paths['source'].read_bytes(), raw)
            self.assertEqual(json.loads(paths['profile'].read_text()), self.profile)
            metrics = measure_font(paths['font'], self.fixture['font_schema'])
            self.assertTrue(metrics['ok'], metrics)
            rows = {g['id']: g for g in metrics['glyphs']}
            self.assertEqual((rows['digit-0']['ink_bounds'], rows['digit-0']['ink_pixels'],
                              rows['digit-0']['advance_pixels']), ([0, 0, 5, 5], 12, 6))
            self.assertEqual((rows['blank']['ink_bounds'], rows['blank']['advance_pixels']), (None, 3))
            self.assertEqual((rows['letter-b']['ink_bounds'], rows['letter-b']['advance_pixels']),
                             ([0, 0, 5, 5], 4))
        self.assertTrue(validate_font_schema(self.fixture['font_schema'])['measurement_supported'])
        self.assertEqual((RGB_A, RGB_B), (bytes.fromhex('000000ff000000ff000000ff'),
                                        bytes.fromhex('000000ff000000ff00000000')))

    def test_map_is_sorted_detached_and_hashed_with_provenance(self):
        original = self.validate()
        self.profile['glyph_map'].reverse()
        reordered = self.validate()
        self.assertEqual(reordered, original)
        self.assertNotEqual(self.profile['glyph_map'], reordered['normalized']['glyph_map'])
        self.profile['glyph_map'][0]['glyph_id'] = 'other-explicit-glyph'
        changed = self.validate()
        self.assertNotEqual(changed['glyph_map_sha256'], original['glyph_map_sha256'])
        self.assertNotEqual(changed['sha256'], original['sha256'])
        self.profile['glyph_map'][0]['provenance']['note'] = 'Different declaration'
        self.assertNotEqual(self.validate()['glyph_map_sha256'], changed['glyph_map_sha256'])

    def test_mapping_accepts_explicit_aliases_and_defers_font_resolution(self):
        self.profile['glyph_map'][1]['glyph_id'] = self.profile['glyph_map'][0]['glyph_id']
        self.profile['glyph_map'][2]['glyph_id'] = 'not-in-any-measured-font'
        result = self.validate()
        self.assertTrue(result['supported'])
        self.assertEqual(result['normalized']['glyph_map'][2]['glyph_id'], 'not-in-any-measured-font')

    def test_mapping_rejects_duplicates_invalid_scalars_and_count_overflow(self):
        for scalar in ('AB', '', '\ud800', '\x00', '\x85', True):
            with self.subTest(scalar=repr(scalar)):
                profile = copy.deepcopy(self.profile)
                profile['glyph_map'][0]['scalar'] = scalar
                with self.assertRaises(ValueError):
                    self.validate(profile)
        profile = copy.deepcopy(self.profile)
        profile['glyph_map'].append(copy.deepcopy(profile['glyph_map'][0]))
        with self.assertRaises(ValueError):
            self.validate(profile)
        for count in (0, 256, 257):
            profile = copy.deepcopy(self.profile)
            row = profile['glyph_map'][0]
            profile['glyph_map'] = [{**copy.deepcopy(row), 'scalar': chr(0x100 + i)} for i in range(count)]
            if count == 256:
                self.assertTrue(self.validate(profile)['supported'])
            else:
                with self.assertRaises(ValueError):
                    self.validate(profile)

    def test_unknown_model_is_bounded_unsupported_without_interpreting_offsets(self):
        self.profile['model'] = 'future-menu-v2'
        self.profile['entries'] = [{'opaque_future_data': {'offset': -999}}]
        self.profile['numeric_fields'] = [{'future_field': 'not interpreted'}]
        result = self.validate()
        self.assertFalse(result['supported'])
        self.assertTrue(result['read_only_reasons'])
        self.assertEqual(result['normalized'], self.profile)
        self.assertEqual(result['sha256'], digest_json(self.profile))
        self.profile['extra_root_field'] = 1
        with self.assertRaises(ValueError):
            self.validate()

    def test_unsupported_artifact_does_not_hide_bad_known_menu_references(self):
        from romancer.script_schema import validate_schema
        self.script['artifact']['kind'] = 'unsupported-container'
        self.profile['script_schema_sha256'] = validate_schema(self.script)['schema_sha256']
        self.assertFalse(self.validate()['supported'])
        self.profile['entries'][0]['states']['selected'][0]['record_id'] = 'missing'
        with self.assertRaises(ValueError):
            self.validate()

    def test_profile_rejects_malformed_envelope_labels_and_stale_binding(self):
        for key, value in [('schema_version', True), ('schema_version', 2), ('extra', None),
                           ('id', ''), ('version', 'x' * 129), ('model', '\x00'),
                           ('script_schema_sha256', '0' * 64), ('script_schema_sha256', 'A' * 64),
                           ('row_step_px', 0), ('row_step_px', 1025), ('line_height_px', 65),
                           ('line_height_px', True)]:
            with self.subTest(key=key, value=value):
                profile = copy.deepcopy(self.profile)
                profile[key] = value
                with self.assertRaises(ValueError):
                    self.validate(profile)
        for key in self.profile:
            profile = copy.deepcopy(self.profile)
            del profile[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                self.validate(profile)

    def test_numeric_fields_reject_pointer_text_wrong_width_and_duplicate_guard(self):
        for rule in ('pa', 'a-slot', 'missing'):
            profile = copy.deepcopy(self.profile)
            profile['numeric_fields'][0]['source']['rule'] = rule
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                self.validate(profile)
        profile = copy.deepcopy(self.profile)
        profile['numeric_fields'][1]['source']['rule'] = 'price'
        with self.assertRaises(ValueError):
            self.validate(profile)
        profile = copy.deepcopy(self.profile)
        profile['numeric_fields'][0]['width'] = 1
        with self.assertRaises(ValueError):
            self.validate(profile)

    def test_numeric_codec_width_endian_maximum_and_format_tables(self):
        field = copy.deepcopy(self.profile['numeric_fields'][2])
        good = [('uint', 1, 'little', 255), ('uint', 4, 'big', 4294967295),
                ('packed-bcd', 1, 'big', 99), ('packed-bcd', 4, 'big', 99999999),
                ('ascii-decimal', 1, None, 9), ('ascii-decimal', 10, None, 9999999999)]
        for codec, width, endian, maximum in good:
            for delta in (0, 1):
                profile = copy.deepcopy(self.profile)
                profile['numeric_fields'][2] = {**field, 'codec': codec, 'width': width,
                                               'endian': endian, 'maximum': maximum + delta}
                with self.subTest(codec=codec, width=width, delta=delta):
                    if delta:
                        with self.assertRaises(ValueError):
                            self.validate(profile)
                    else:
                        self.assertTrue(self.validate(profile)['supported'])
        bad = [('codec', 'float'), ('width', True), ('width', 0), ('width', 11),
               ('endian', 'little'), ('maximum', -1), ('maximum', True), ('role', 'charge'),
               ('source', {'kind': 'case_bytes', 'path': 'input.bin'})]
        for key, value in bad:
            profile = copy.deepcopy(self.profile)
            profile['numeric_fields'][2][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(profile)
        for key, value in [('digits', 0), ('digits', 11), ('digits', True), ('pad', 'truncate'),
                           ('prefix', 'x' * 33), ('suffix', '\n'), ('extra', 1)]:
            profile = copy.deepcopy(self.profile)
            profile['numeric_fields'][2]['format'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(profile)

    def test_cells_require_exact_states_one_name_unique_ids_and_number_references(self):
        modifications = [
            lambda p: p['entries'][0]['states'].pop('selected'),
            lambda p: p['entries'][0]['states'].update(hover=[]),
            lambda p: p['entries'][0]['states'].update(selected=[]),
            lambda p: p['entries'][0]['states']['selected'].pop(0),
            lambda p: p['entries'][0]['states']['selected'][0].update(record_id='missing'),
            lambda p: p['entries'][0]['states']['selected'][1].update(field_id='missing'),
            lambda p: p['entries'][0]['states']['selected'][1].update(id='name'),
            lambda p: p['entries'][0]['states']['selected'][2].update(field_id='price'),
            lambda p: p['entries'][0]['states']['selected'][0].update(text='AB'),
            lambda p: p['entries'][0].update(kind='inferred'),
            lambda p: p['entries'][1].update(id='item'),
        ]
        for i, change in enumerate(modifications):
            profile = copy.deepcopy(self.profile)
            change(profile)
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.validate(profile)

    def test_cell_rectangles_half_open_edges_and_overlap(self):
        profile = copy.deepcopy(self.profile)
        cells = profile['entries'][0]['states']['selected']
        cells[0]['box']['width'] = 28
        self.assertTrue(self.validate(profile)['supported'])
        cells[0]['box']['width'] = 29
        with self.assertRaises(ValueError):
            self.validate(profile)
        for key, value in [('x', -1), ('y', True), ('width', 0), ('height', 1025), ('x', 128)]:
            profile = copy.deepcopy(self.profile)
            profile['entries'][0]['states']['selected'][0]['box'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(profile)

    def test_empty_menu_declaration_and_zero_entry_profile(self):
        for empty in (None, self.profile['empty'], self.profile['entries'][0]['states']['selected'][0]):
            profile = copy.deepcopy(self.profile)
            profile['empty'] = copy.deepcopy(empty)
            profile['entries'] = []
            self.assertTrue(self.validate(profile)['supported'])
        self.profile['empty'] = self.profile['entries'][0]['states']['selected'][1]
        with self.assertRaises(ValueError):
            self.validate()

    def test_cases_roundtrip_detachment_selection_and_exact_dynamic_values(self):
        before = copy.deepcopy(self.cases)
        result = self.validate_cases()
        self.assertEqual(result, {'normalized': before, 'sha256': digest_json(before)})
        result['normalized']['cases'][0]['dynamic_values'].clear()
        self.assertEqual(self.cases, before)
        for key, value in [('selected_entry', 'absent'), ('entries', ['item', 'item']),
                           ('entries', ['missing']), ('dynamic_values', []),
                           ('dynamic_values', [{'field_id': 'fee', 'raw_hex': '3030'}]),
                           ('dynamic_values', [{'field_id': 'fee', 'raw_hex': 'ABCDABCD'}]),
                           ('dynamic_values', [{'field_id': 'price', 'raw_hex': '1234'}])]:
            cases = copy.deepcopy(self.cases)
            cases['cases'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate_cases(cases)

    def test_case_dynamic_requirements_follow_only_chosen_states(self):
        self.profile['entries'][0]['states']['unselected'].pop()
        self.rebind_cases()
        self.cases['cases'][1]['dynamic_values'] = []
        self.assertEqual(len(self.validate_cases()['normalized']['cases']), 3)
        self.cases['cases'][1]['dynamic_values'] = [{'field_id': 'fee', 'raw_hex': '30303030'}]
        with self.assertRaises(ValueError):
            self.validate_cases()

    def test_case_stale_binding_duplicates_and_empty_selection(self):
        for modify in (
                lambda c: c.update(profile_sha256='0' * 64),
                lambda c: c['cases'][1].update(id='selected'),
                lambda c: c['cases'][2].update(selected_entry='item'),
                lambda c: c['cases'][2].update(dynamic_values=[{'field_id': 'fee', 'raw_hex': '30303030'}]),
                lambda c: c['cases'][0]['dynamic_values'].append({'field_id': 'fee', 'raw_hex': '30303132'})):
            cases = copy.deepcopy(self.cases)
            modify(cases)
            with self.assertRaises(ValueError):
                self.validate_cases(cases)
        self.cases['cases'] = []
        self.assertEqual(self.validate_cases()['normalized']['cases'], [])

    def test_case_count_and_emitted_cell_multiplicative_bounds(self):
        template = self.cases['cases'][0]
        for count in (32, 33):
            cases = copy.deepcopy(self.cases)
            cases['cases'] = [{**copy.deepcopy(template), 'id': str(i)} for i in range(count)]
            if count == 32:
                self.assertEqual(len(self.validate_cases(cases)['normalized']['cases']), 32)
            else:
                with self.assertRaises(ValueError):
                    self.validate_cases(cases)
        # 32 cases * 32 one-cell rows is exactly 1024 cells; names are measured later.
        row = copy.deepcopy(self.profile['entries'][0])
        for state in row['states']:
            row['states'][state] = [row['states'][state][0]]
        self.profile['entries'] = [{**copy.deepcopy(row), 'id': str(i)} for i in range(33)]
        template = {'id': '', 'entries': [str(i) for i in range(32)], 'selected_entry': None,
                    'dynamic_values': [], 'provenance': copy.deepcopy(self.profile['provenance'])}
        self.cases['cases'] = [{**copy.deepcopy(template), 'id': str(i)} for i in range(32)]
        self.rebind_cases()
        self.assertEqual(len(self.validate_cases()['normalized']['cases']), 32)
        self.cases['cases'][0]['entries'].append('32')
        with self.assertRaises(ValueError):
            self.validate_cases()

    def test_profile_entry_field_and_state_cell_exact_bounds(self):
        for count in (64, 65):
            profile = copy.deepcopy(self.profile)
            template = profile['entries'][0]
            profile['entries'] = [{**copy.deepcopy(template), 'id': str(i)} for i in range(count)]
            with self.subTest(entries=count):
                if count == 64:
                    self.assertEqual(len(self.validate(profile)['normalized']['entries']), count)
                else:
                    with self.assertRaises(ValueError):
                        self.validate(profile)
        for count in (128, 129):
            profile = copy.deepcopy(self.profile)
            template = profile['numeric_fields'][2]
            profile['entries'] = []
            profile['numeric_fields'] = [{**copy.deepcopy(template), 'id': str(i)} for i in range(count)]
            with self.subTest(fields=count):
                if count == 128:
                    self.assertEqual(len(self.validate(profile)['normalized']['numeric_fields']), count)
                else:
                    with self.assertRaises(ValueError):
                        self.validate(profile)
        for count in (8, 9):
            profile = copy.deepcopy(self.profile)
            name = copy.deepcopy(profile['entries'][0]['states']['selected'][0])
            name['box']['width'] = 1
            profile['entries'][0]['states']['selected'] = [name] + [
                {'id': str(i), 'kind': 'literal', 'text': '',
                 'box': {'x': i, 'y': 0, 'width': 1, 'height': 1}, 'align': 'left', 'style': 'plain'}
                for i in range(1, count)]
            with self.subTest(cells=count):
                if count == 8:
                    self.assertTrue(self.validate(profile)['supported'])
                else:
                    with self.assertRaises(ValueError):
                        self.validate(profile)

    def test_all_numeric_endian_tags_reject_incompatible_values(self):
        for codec, endian, width in [('uint', None, 2), ('packed-bcd', 'little', 2),
                                     ('packed-bcd', None, 2), ('ascii-decimal', 'big', 2),
                                     ('uint', 'little', 5), ('packed-bcd', 'big', 5)]:
            profile = copy.deepcopy(self.profile)
            profile['numeric_fields'][2].update(codec=codec, endian=endian, width=width, maximum=9)
            with self.subTest(codec=codec, endian=endian, width=width), self.assertRaises(ValueError):
                self.validate(profile)

    def test_comparison_all_32_unique_captures_and_shared_roles_are_explicit(self):
        request = comparison_fixture()
        template = request['pairs'][0]
        request['pairs'] = []
        for index in range(16):
            pair = copy.deepcopy(template)
            pair['id'] = str(index)
            pair['target']['capture_id'] = f'{index * 2:032x}'
            pair['reference']['capture_id'] = f'{index * 2 + 1:032x}'
            pair['target']['source_role'] = pair['target']['font_role'] = 'output'
            request['pairs'].append(pair)
        validated = self.model.validate_menu_comparison(request)
        self.assertEqual(validated['normalized'], request)

    def test_strict_json_loader_rejects_duplicate_input_keys_before_validation(self):
        from romancer.script_schema import load_script_json
        with tempfile.TemporaryDirectory(prefix='ROMancer menu JSON ') as directory:
            path = Path(directory) / 'profile.json'
            path.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                load_script_json(path, max_bytes=self.model.MAX_MENU_JSON_BYTES)

    def test_known_literal_glyph_expansion_is_preflighted(self):
        self.profile['entries'] = []
        self.profile['empty']['text'] = 'A' * 32
        self.cases['cases'] = [{'id': str(i), 'entries': [], 'selected_entry': None,
                               'dynamic_values': [], 'provenance': copy.deepcopy(self.profile['provenance'])}
                              for i in range(32)]
        self.rebind_cases()
        self.assertEqual(len(self.validate_cases()['normalized']['cases']), 32)
        # Three literals per rendered row alone exceed 2048, even before any names.
        row = menu_fixture()['profile']['entries'][0]
        row['states'] = {state: [copy.deepcopy(row['states'][state][0])] + [
            {'id': str(i), 'kind': 'literal', 'text': 'A' * 32,
             'box': {'x': 25 + i * 32, 'y': 0, 'width': 32, 'height': 5},
             'align': 'left', 'style': 'plain'} for i in range(3)] for state in ('selected', 'unselected')}
        self.profile['entries'] = [row]
        for case in self.cases['cases']:
            case['entries'] = ['item']
        self.rebind_cases()
        with self.assertRaises(ValueError):
            self.validate_cases()

    def test_comparison_roundtrip_detached_selectors_and_pixel_bound(self):
        request = comparison_fixture()
        result = self.model.validate_menu_comparison(request)
        self.assertEqual(result, {'normalized': request, 'sha256': digest_json(request)})
        result['normalized']['pairs'][0]['region'][0] = 9
        self.assertEqual(request['pairs'][0]['region'], [0, 0, 2, 2])
        request['pairs'][0]['region'] = [0, 0, 1024, 1024]
        self.assertEqual(self.model.validate_menu_comparison(request)['normalized'], request)
        request['pairs'][0]['region'] = [0, 0, 1025, 1024]
        with self.assertRaises(ValueError):
            self.model.validate_menu_comparison(request)

    def test_comparison_rejects_bad_selectors_self_comparison_and_unknown_predicates(self):
        changes = [
            (('target',), 'capture_id', 'a' * 64), (('target',), 'build_id', 'g' * 64),
            (('reference',), 'rgb_sha256', 'F' * 64), (('target',), 'source_role', ''),
            (('reference',), 'source_role', 'output'), (('target',), 'path', 'capture.png'),
            ((), 'relation', 'looks_correct'), ((), 'expected_text', 'AB'),
            ((), 'region', [0, 0, 0, 2]), ((), 'region', [True, 0, 1, 1]),
            ((), 'region', [4095, 0, 2, 1]), ((), 'region', [0, 0, 1]),
        ]
        for path, key, value in changes:
            request = comparison_fixture()
            target = request['pairs'][0]
            for part in path:
                target = target[part]
            target[key] = value
            with self.subTest(path=path, key=key), self.assertRaises(ValueError):
                self.model.validate_menu_comparison(request)
        request = comparison_fixture()
        request['pairs'][0]['reference']['capture_id'] = request['pairs'][0]['target']['capture_id']
        with self.assertRaises(ValueError):
            self.model.validate_menu_comparison(request)

    def test_comparison_pair_counts_uniqueness_and_aggregate_pixels(self):
        original = comparison_fixture()
        for count in (0, 16, 17):
            request = copy.deepcopy(original)
            request['pairs'] = [{**copy.deepcopy(original['pairs'][0]), 'id': str(i)} for i in range(count)]
            if count == 16:
                self.assertEqual(len(self.model.validate_menu_comparison(request)['normalized']['pairs']), 16)
            else:
                with self.assertRaises(ValueError):
                    self.model.validate_menu_comparison(request)
        duplicate = copy.deepcopy(original)
        duplicate['pairs'] *= 2
        with self.assertRaises(ValueError):
            self.model.validate_menu_comparison(duplicate)
        original['pairs'][0]['region'] = [0, 0, 1024, 1024]
        original['pairs'].append({**copy.deepcopy(original['pairs'][0]), 'id': 'extra', 'region': [0, 0, 1, 1]})
        with self.assertRaises(ValueError):
            self.model.validate_menu_comparison(original)

    def test_all_inputs_enforce_plain_finite_bounded_json_and_provenance(self):
        for factory, validate in ((lambda: copy.deepcopy(self.profile), self.validate),
                                  (lambda: copy.deepcopy(self.cases), self.validate_cases),
                                  (comparison_fixture, self.model.validate_menu_comparison)):
            for value in (float('inf'), '\ud800', [None] * 100001, 'x' * 1048577):
                item = factory()
                item['bad'] = value
                with self.assertRaises(ValueError):
                    validate(item)
            item = factory()
            item['cycle'] = item
            with self.assertRaises(ValueError):
                validate(item)
            item = factory()
            nested = item
            for _ in range(33):
                nested['nest'] = {}
                nested = nested['nest']
            with self.assertRaises(ValueError):
                validate(item)
        for key, value in [('origin', 'measured_runtime'), ('note', ' '), ('note', 'x' * 513),
                           ('reference', 'x' * 257), ('reference', '\x7f')]:
            profile = copy.deepcopy(self.profile)
            profile['glyph_map'][0]['provenance'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(profile)


if __name__ == '__main__':
    unittest.main()
