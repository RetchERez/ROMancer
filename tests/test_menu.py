import copy
import importlib
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.menu_fixtures import menu_fixture, digest_json


def field(codec='uint', width=2, endian='little', maximum=65535, digits=5, pad='none'):
    return {'id': 'value', 'source': {'kind': 'case_bytes'}, 'codec': codec, 'width': width,
            'endian': endian, 'maximum': maximum,
            'format': {'digits': digits, 'pad': pad, 'prefix': '', 'suffix': ''},
            'role': 'value', 'provenance': {'origin': 'synthetic_fixture',
                                          'note': 'Literal numeric value', 'reference': None}}


class MenuNumberTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.menu'), 'menu service is absent')
        self.module = importlib.import_module('romancer.menu')

    def test_literal_numeric_values_and_endian(self):
        for raw, definition, expected in (
            (bytes.fromhex('ff00'), field(), 255),
            (bytes.fromhex('ff00'), field(endian='big'), 65280),
            (bytes.fromhex('1234'), field('packed-bcd', 2, 'big', 9999, 4), 1234),
            (b'0012', field('ascii-decimal', 4, None, 9999, 4), 12),
            (bytes.fromhex('ffffffff'), field(width=4, maximum=4294967295, digits=10), 4294967295),
            (bytes.fromhex('99999999'), field('packed-bcd', 4, 'big', 99999999, 8), 99999999),
            (b'9999999999', field('ascii-decimal', 10, None, 9999999999, 10), 9999999999),
        ):
            with self.subTest(raw=raw, codec=definition['codec']):
                before = copy.deepcopy(definition)
                self.assertEqual(self.module.decode_menu_number(raw, definition), expected)
                self.assertEqual(definition, before)

    def test_invalid_bcd_nibbles_and_ascii_bytes_refuse(self):
        for byte in [n << 4 for n in range(10, 16)] + list(range(10, 16)):
            with self.subTest(byte=byte), self.assertRaises(ValueError) as raised:
                self.module.decode_menu_number(bytes([byte]), field('packed-bcd', 1, 'big', 99, 2))
            self.assertEqual(raised.exception.code, 'NUMERIC_ENCODING')
        for raw in (b'+012', b'-012', b' 012', b'12.3', b'001\x00', b'\xff123'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.module.decode_menu_number(raw, field('ascii-decimal', 4, None, 9999, 4))

    def test_zero_maximum_maximum_plus_one_and_storage_width(self):
        definition = field(maximum=255)
        self.assertEqual(self.module.decode_menu_number(b'\x00\x00', definition), 0)
        self.assertEqual(self.module.decode_menu_number(b'\xff\x00', definition), 255)
        with self.assertRaises(ValueError) as raised:
            self.module.decode_menu_number(b'\x00\x01', definition)
        self.assertEqual(raised.exception.code, 'VALUE_RANGE')
        for raw in (b'', b'\x01', b'\x01\x00\x00'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.module.decode_menu_number(raw, definition)

    def test_decimal_padding_prefix_and_digit_overflow(self):
        for value, pad, expected in ((7, 'zero', '0007'), (0, 'space', '   0'),
                                     (0, 'none', '0'), (12, 'none', '12')):
            self.assertEqual(self.module.format_menu_number(value, field(digits=4, pad=pad)), expected)
        definition = field(digits=4, pad='zero')
        definition['format'].update(prefix='$', suffix='AB')
        self.assertEqual(self.module.format_menu_number(12, definition), '$0012AB')
        with self.assertRaises(ValueError) as raised:
            self.module.format_menu_number(10000, definition)
        self.assertEqual(raised.exception.code, 'DIGIT_OVERFLOW')
        for value in (True, -1, 256):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.module.format_menu_number(value, field(maximum=255))


class MenuServiceTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('romancer.menu')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'menu.bin'
        self.font = Path(self.temp.name) / 'font.bin'
        self.fx = menu_fixture()
        for entry in self.fx['profile']['entries']:
            for cells in entry['states'].values():
                for cell in cells:
                    if cell['id'] == 'quantity':
                        cell['box']['width'] = 32
                    if cell['id'] == 'fee':
                        cell['box']['x'] = 96
        self.rebind()
        self.source.write_bytes(self.fx['raw'])
        self.font.write_bytes(self.fx['font'])

    def rebind(self, *, resource=False):
        if resource:
            schema = self.fx['script_schema']
            schema['profile']['accepted_sha256'] = [hashlib.sha256(self.fx['raw']).hexdigest()]
            for rule in schema['profile']['rules']:
                rule['expected_hex'] = self.fx['raw'][rule['offset']:rule['offset'] + rule['length']].hex()
            self.source.write_bytes(self.fx['raw'])
        self.fx['profile']['script_schema_sha256'] = digest_json(self.fx['script_schema'])
        self.fx['cases']['profile_sha256'] = digest_json(self.fx['profile'])

    def inspect(self):
        self.assertTrue(callable(getattr(self.module, 'inspect_menu', None)), 'inspection service missing')
        return self.module.inspect_menu(self.source, self.fx['script_schema'], self.fx['profile'])

    def preview(self):
        self.assertTrue(callable(getattr(self.module, 'preview_menu', None)), 'preview service missing')
        return self.module.preview_menu(self.source, self.fx['script_schema'], self.fx['profile'],
                                        self.fx['cases'], self.fx['font_schema'], self.font)

    def assert_unwritten(self, result):
        self.assertFalse(result['written'])
        self.assertEqual(self.source.read_bytes(), self.fx['raw'])
        self.assertEqual(self.font.read_bytes(), self.fx['font'])
        self.assertEqual(result['transaction_status'], 'NOT_RUN')
        self.assertEqual(result['comparison_status'], 'NOT_RUN')
        self.assertFalse(result['actual_transaction_verified'])
        self.assertFalse(result['native_render_verified'])

    def test_inspection_retains_lossless_names_and_measured_numeric_guards(self):
        result = self.inspect()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'INSPECTED')
        self.assertEqual(result['preview_status'], 'NOT_RUN')
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.fx['raw']).hexdigest())
        self.assertEqual(result['source_size'], 32)
        self.assertEqual([row['raw_hex'] for row in result['script']['records']],
                         ['414200ffffffffff', '424100ffffffffff'])
        fields = {row['id']: row for row in result['numeric_fields']}
        self.assertEqual((fields['price']['raw_hex'], fields['price']['value']), ('1234', 1234))
        self.assertEqual((fields['quantity']['raw_hex'], fields['quantity']['value']), ('ff00', 255))
        self.assertEqual(fields['fee']['status'], 'NOT_RUN')
        self.assertIsNone(fields['fee']['value'])
        self.assertIsNone(result['metrics_id'])
        self.assertIsNone(result['preview_id'])
        self.assert_unwritten(result)

    def test_preview_literal_states_numbers_geometry_and_separate_status(self):
        result = self.preview()
        self.assertTrue(result['ok'], result)
        self.assertEqual((result['status'], result['preview_status']), ('PASS', 'PASS'))
        cases = {row['id']: row for row in result['cases']}
        first = cases['selected']['cells']
        self.assertEqual([row['text'] for row in first], ['BA', '1234', '255', '$0012', 'BA', '1234', '255'])
        self.assertEqual(first[0]['advance_px'], 10)
        self.assertEqual(first[0]['ink_bounds'], [0, 0, 9, 5])
        self.assertEqual(first[1]['pen_origin'], [32, 0])
        self.assertEqual(first[2]['declared_maximum_probe']['text'], '65535')
        self.assertEqual(first[2]['declared_maximum_probe']['advance_px'], 30)
        self.assertEqual(cases['unselected']['cells'][0]['text'], 'AB')
        self.assertEqual(cases['empty']['cells'][0]['placements'], [])
        self.assertEqual(result['coverage']['entries']['spell']['selected'], 'NOT_RUN')
        self.assertEqual(result['coverage']['fields']['fee']['zero'], 'PASS')
        self.assertEqual(result['coverage']['fields']['fee']['maximum'], 'NOT_RUN')
        self.assertEqual(result['coverage']['fields']['fee']['declared_maximum_probe'], 'PASS')
        self.assertEqual(result['coverage']['empty_list'], 'PASS')
        rows = {row['id']: row for row in result['glyphs']}
        self.assertEqual(rows['digit-0']['advance_origin'], 'measured_u8')
        self.assertEqual(rows['digit-0']['ink_pixels'], 12)
        self.assertFalse(result['state_semantics_verified'])
        self.assert_unwritten(result)

    def test_current_fits_but_declared_maximum_fails(self):
        for entry in self.fx['profile']['entries']:
            for cells in entry['states'].values():
                next(cell for cell in cells if cell['id'] == 'quantity')['box']['width'] = 20
        self.rebind()
        result = self.preview()
        self.assertFalse(result['ok'])
        self.assertEqual((result['status'], result['preview_status']), ('FAIL', 'FAIL'))
        quantity = result['cases'][0]['cells'][2]
        self.assertEqual(quantity['geometry_status'], 'PASS')
        self.assertEqual(quantity['declared_maximum_probe']['status'], 'FAIL')
        self.assertIn('ADVANCE_OVERFLOW', [row['code'] for row in quantity['declared_maximum_probe']['diagnostics']])
        self.assert_unwritten(result)

    def test_unknown_model_inspects_read_only_and_preview_blocks(self):
        self.fx['profile']['model'] = 'future-menu'
        self.rebind()
        inspected = self.inspect()
        self.assertTrue(inspected['ok'], inspected)
        self.assertEqual(inspected['status'], 'READ_ONLY')
        self.assertEqual(inspected['numeric_fields'], [])
        self.assertEqual(inspected['preview_status'], 'NOT_RUN')
        result = self.preview()
        self.assertEqual((result['status'], result['preview_status']), ('BLOCKED', 'BLOCKED'))
        self.assertFalse(result['ok'])

    def test_stale_revision_is_rejected_before_offset_parsing(self):
        self.source.write_bytes(b'X' + self.fx['raw'][1:])
        from romancer import script
        with mock.patch.object(script, 'parse_slot', side_effect=AssertionError('offset parsing too early')):
            result = self.preview()
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'REVISION_MISMATCH')
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(result['preview_status'], 'BLOCKED')

    def test_unsupported_name_is_not_silently_truncated(self):
        self.fx['raw'] = self.fx['raw'][:8] + b'\x99' + self.fx['raw'][9:]
        self.rebind(resource=True)
        result = self.preview()
        self.assertFalse(result['ok'])
        self.assertEqual(result['preview_status'], 'BLOCKED')
        self.assertIn('UNSUPPORTED_NAME_CONTROL', json.dumps(result))
        self.assert_unwritten(result)

    def test_no_cases_and_cancelled_font_are_not_successful_empty_previews(self):
        self.fx['cases']['cases'] = []
        result = self.preview()
        self.assertEqual(result['preview_status'], 'BLOCKED')
        self.assertEqual(result['error']['code'], 'NO_CASES')
        self.fx['cases']['cases'] = menu_fixture()['cases']['cases']
        from romancer import font_metrics
        with mock.patch.object(font_metrics, 'measure_font_stream', side_effect=KeyboardInterrupt):
            result = self.preview()
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertEqual(result['preview_status'], 'BLOCKED')
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.fx['raw']).hexdigest())

    def test_mapping_changes_preview_identity_but_not_font_identity(self):
        first = self.preview()
        self.fx['profile']['glyph_map'].reverse()
        # Reordering alone normalizes to the same profile; keep the canonical binding.
        same = self.preview()
        self.assertEqual(first['preview_id'], same['preview_id'])
        next(row for row in self.fx['profile']['glyph_map'] if row['scalar'] == 'A')['glyph_id'] = 'letter-b'
        self.fx['profile']['glyph_map'].sort(key=lambda row: ord(row['scalar']))
        self.rebind()
        changed = self.preview()
        self.assertTrue(changed['ok'], changed)
        for key in ('glyph_map_sha256', 'profile_sha256', 'menu_document_id', 'preview_id'):
            self.assertNotEqual(first[key], changed[key])
        for key in ('font_sha256', 'font_schema_sha256', 'metrics_id'):
            self.assertEqual(first[key], changed[key])
        self.assertEqual(changed['cases'][0]['cells'][0]['advance_px'], 8)

    def test_missing_or_dangling_glyph_is_blocked_even_if_other_geometry_fails(self):
        for dangling in (False, True):
            with self.subTest(dangling=dangling):
                self.fx['profile']['glyph_map'] = menu_fixture()['profile']['glyph_map']
                if dangling:
                    self.fx['profile']['glyph_map'][0]['glyph_id'] = 'absent'
                else:
                    self.fx['profile']['glyph_map'] = [row for row in self.fx['profile']['glyph_map'] if row['scalar'] != '5']
                self.fx['profile']['line_height_px'] = 6
                self.rebind()
                result = self.preview()
                self.assertEqual(result['status'], 'BLOCKED', result)
                self.assertIn('MISSING_GLYPH', json.dumps(result))
                self.assertEqual(result['source_size'], 32)
                self.assertEqual(result['font_sha256'], hashlib.sha256(self.fx['font']).hexdigest())
                self.assertIsNotNone(result['metrics_id'])

    def test_empty_name_empty_list_without_message_and_control_refusal(self):
        self.fx['raw'] = self.fx['raw'][:20] + b'\x00' + b'\xff' * 7 + self.fx['raw'][28:]
        self.fx['profile']['empty'] = None
        self.rebind(resource=True)
        result = self.preview()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['cases'][0]['cells'][0]['text'], '')
        self.assertEqual(result['cases'][0]['cells'][0]['name_span']['used_bytes'], 1)
        self.assertEqual(result['cases'][2]['cells'], [])
        self.assertEqual(result['coverage']['empty_list'], 'PASS')
        self.fx['raw'] = self.fx['raw'][:20] + b'\x10\x00' + b'\xff' * 6 + self.fx['raw'][28:]
        self.fx['script_schema']['format']['controls'] = [
            {'id': 'explicit-control', 'opcode': 16, 'argument_length': 0,
             'position_independent': True, 'layout_role': 'opaque'}]
        self.rebind(resource=True)
        result = self.preview()
        self.assertEqual(result['preview_status'], 'BLOCKED')
        self.assertIn('UNSUPPORTED_NAME_CONTROL', json.dumps(result))

    def test_ink_half_open_edge_overhang_bearing_and_blank_advance(self):
        for entry in self.fx['profile']['entries']:
            for cells in entry['states'].values():
                cells[0]['box']['width'] = 11
        self.rebind()
        self.assertTrue(self.preview()['ok'])
        for entry in self.fx['profile']['entries']:
            for cells in entry['states'].values():
                cells[0]['box']['width'] = 10
        self.rebind()
        result = self.preview()
        name = result['cases'][1]['cells'][0]  # AB: advance10, ink exclusive edge11.
        self.assertEqual(name['advance_px'], 10)
        self.assertEqual(name['ink_bounds'], [0, 0, 11, 5])
        self.assertEqual([row['code'] for row in name['diagnostics']], ['INK_CLIP'])
        next(row for row in self.fx['font_schema']['glyphs'] if row['id'] == 'letter-b')['bearing']['x'] = -1
        result = self.preview()
        self.assertEqual(result['cases'][0]['cells'][0]['ink_bounds'][0], -1)
        self.fx['profile']['empty']['text'] = ' ' * 9
        self.rebind()
        result = self.preview()
        empty = result['cases'][2]['cells'][0]
        self.assertIsNone(empty['ink_bounds'])
        self.assertEqual(empty['advance_px'], 27)
        self.assertIn('ADVANCE_OVERFLOW', [row['code'] for row in empty['diagnostics']])

    def test_row_overlap_viewport_and_reserved_line_height(self):
        self.fx['profile']['row_step_px'] = 4
        self.rebind()
        result = self.preview()
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('CELL_OVERLAP', json.dumps(result['cases'][0]['diagnostics']))
        self.fx['profile']['row_step_px'] = 64
        self.fx['profile']['line_height_px'] = 6
        self.rebind()
        result = self.preview()
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('VIEWPORT_OVERFLOW', json.dumps(result))
        self.assertIn('LINE_HEIGHT_OVERFLOW', json.dumps(result))

    def test_source_and_font_held_through_consumer_and_final_sweep_then_closed(self):
        from romancer import script, font_metrics, menu_metrics
        streams, sweeps = [], []
        inspect, measure, stable = script.inspect_stream, font_metrics.measure_font_stream, menu_metrics._HeldFile.assert_stable
        after_yield = False

        def inspect_record(stream, schema):
            streams.append(stream)
            return inspect(stream, schema)

        def measure_record(stream, schema):
            streams.append(stream)
            return measure(stream, schema)

        def check(held):
            if after_yield:
                sweeps.append((held.path.name, [stream.closed for stream in streams]))
            return stable(held)

        for failure in (None, ValueError('consumer error'), KeyboardInterrupt()):
            streams.clear()
            sweeps.clear()
            after_yield = False
            with mock.patch.object(script, 'inspect_stream', side_effect=inspect_record), mock.patch.object(
                    font_metrics, 'measure_font_stream', side_effect=measure_record), mock.patch.object(
                    menu_metrics._HeldFile, 'assert_stable', check):
                try:
                    with self.module._preview_inputs(self.source, self.fx['script_schema'], self.fx['profile'],
                            self.fx['cases'], self.fx['font_schema'], self.font) as fresh:
                        self.assertTrue(fresh['ok'], fresh)
                        self.assertEqual([stream.closed for stream in streams], [False, False])
                        after_yield = True
                        if failure is not None:
                            raise failure
                except (ValueError, KeyboardInterrupt) as exc:
                    self.assertIs(exc, failure)
            self.assertEqual([stream.closed for stream in streams], [True, True])
            if failure is None:
                self.assertEqual(sweeps[:2], [('menu.bin', [False, False]), ('font.bin', [False, False])])

    def test_late_source_and_font_changes_block_context_completion(self):
        for target in (self.source, self.font):
            with self.subTest(target=target), self.assertRaises(ValueError) as caught:
                with self.module._preview_inputs(self.source, self.fx['script_schema'], self.fx['profile'],
                        self.fx['cases'], self.fx['font_schema'], self.font) as fresh:
                    self.assertTrue(fresh['ok'])
                    with target.open('ab') as stream:
                        stream.write(b'X')
            self.assertEqual(caught.exception.code, 'SOURCE_CHANGED')
            self.assertEqual(caught.exception.menu_context['source_size'], 32)
            self.source.write_bytes(self.fx['raw'])
            self.font.write_bytes(self.fx['font'])

    def test_source_change_during_last_measurement_blocks_public_success(self):
        from romancer import menu_metrics
        real = menu_metrics.MenuMetrics.measure

        def change(metrics, text):
            result = real(metrics, text)
            if text == '':  # Last empty-list cell, after all source content work.
                with self.source.open('ab') as stream:
                    stream.write(b'X')
            return result

        with mock.patch.object(menu_metrics.MenuMetrics, 'measure', change):
            result = self.preview()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['error']['code'], 'SOURCE_CHANGED')
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.fx['raw']).hexdigest())

    def test_all_declarations_detached_before_reading_and_stale_cases_refuse(self):
        original = self.preview()
        from romancer import script
        inspect = script.inspect_stream

        def mutate(stream, schema):
            self.fx['profile']['numeric_fields'][0]['maximum'] = 1
            self.fx['cases']['cases'].clear()
            self.fx['font_schema']['glyphs'].clear()
            self.fx['script_schema']['format']['encoding']['glyphs'].clear()
            return inspect(stream, schema)

        with mock.patch.object(script, 'inspect_stream', side_effect=mutate):
            detached = self.preview()
        self.assertTrue(detached['ok'], detached)
        self.assertEqual(detached['preview_id'], original['preview_id'])
        self.fx = menu_fixture()
        self.fx['cases']['profile_sha256'] = '0' * 64
        result = self.preview()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIsNone(result['source_sha256'])

    def test_pretty_report_exact_bound_and_node_budget(self):
        baseline = self.preview()
        length = len(json.dumps(baseline, ensure_ascii=True, sort_keys=True, indent=2).encode('ascii')) + 1
        with mock.patch.object(self.module, 'MAX_REPORT', length):
            self.assertTrue(self.preview()['ok'])
        with mock.patch.object(self.module, 'MAX_REPORT', length - 1):
            result = self.preview()
        self.assertEqual(result['error']['code'], 'REPORT_LIMIT')
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['source_sha256'], baseline['source_sha256'])
        self.assertLess(len(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2)) + 1, length)
        with self.assertRaises(ValueError) as caught:
            self.module._bounded({'rows': [None] * 100001})
        self.assertEqual(caught.exception.code, 'REPORT_LIMIT')

    @unittest.skipUnless(os.name == 'nt', 'Windows raw spelling rule')
    def test_drive_relative_input_refused_before_open(self):
        spelling = self.source.drive + os.path.relpath(self.source)
        with mock.patch.object(Path, 'open', side_effect=AssertionError('ambiguous spelling opened')):
            result = self.module.inspect_menu(spelling, self.fx['script_schema'], self.fx['profile'])
        self.assertEqual(result['error']['code'], 'UNSAFE_PATH')

    def test_unsupported_script_encoding_is_read_only_not_a_missing_record_crash(self):
        self.fx['script_schema']['format']['encoding'] = {'kind': 'future-encoding'}
        self.rebind()
        inspected = self.inspect()
        self.assertEqual(inspected['status'], 'READ_ONLY')
        self.assertEqual(inspected['numeric_fields'], [])
        self.assertIn('raw_rules', inspected['script'])
        result = self.preview()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['error']['code'], 'READ_ONLY')

    def large_name(self, length, cases=1):
        self.fx = menu_fixture()
        self.fx['raw'] = self.fx['raw'][:20] + b'A' * length + b'\x00' + self.fx['raw'][28:]
        schema = self.fx['script_schema']
        schema['artifact']['size'] = len(self.fx['raw'])
        for rule in schema['profile']['rules']:
            if rule['resource'] == 'b-slot':
                rule['length'] = length + 1
            elif rule['offset'] >= 28:
                rule['offset'] += length - 7
        profile = self.fx['profile']
        profile['viewport']['width'] = 1024
        profile['numeric_fields'] = []
        profile['entries'] = [profile['entries'][1]]
        for state in ('selected', 'unselected'):
            cell = profile['entries'][0]['states'][state][0]
            cell['box']['width'] = 1024
            profile['entries'][0]['states'][state] = [cell]
        self.fx['cases']['cases'] = [{'id': f'case-{index}', 'entries': ['spell'],
            'selected_entry': 'spell', 'dynamic_values': [], 'provenance': profile['provenance']}
            for index in range(cases)]
        self.rebind(resource=True)

    def test_name_scalar_limit_exact_and_one_over(self):
        self.large_name(128)
        result = self.preview()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['cases'][0]['cells'][0]['advance_px'], 768)
        self.large_name(129)
        result = self.preview()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('NAME_LIMIT', json.dumps(result))
        self.assert_unwritten(result)

    def test_actual_placement_limit_includes_names_missing_from_preflight(self):
        self.large_name(128, cases=16)
        result = self.preview()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['placement_count'], 2048)
        self.large_name(128, cases=17)
        result = self.preview()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['placement_count'], 2048)
        self.assertIn('PLACEMENT_LIMIT', json.dumps(result))

    def test_numeric_failures_keep_raw_data_and_fail_without_clamping(self):
        self.fx['raw'] = self.fx['raw'][:16] + bytes.fromhex('1a34') + self.fx['raw'][18:]
        self.rebind(resource=True)
        result = self.inspect()
        self.assertEqual(result['status'], 'FAIL')
        price = result['numeric_fields'][0]
        self.assertEqual(price['raw_hex'], '1a34')
        self.assertIsNone(price['value'])
        result = self.preview()
        self.assertEqual(result['preview_status'], 'FAIL')
        self.assertIn('NUMERIC_ENCODING', json.dumps(result))
        self.fx['raw'] = menu_fixture()['raw']
        self.fx['profile']['numeric_fields'][1]['maximum'] = 254
        self.fx['profile']['numeric_fields'][0]['format']['digits'] = 3
        self.rebind(resource=True)
        result = self.preview()
        self.assertIn('VALUE_RANGE', json.dumps(result))
        self.assertIn('DIGIT_OVERFLOW', json.dumps(result))
        self.assertEqual(result['status'], 'FAIL')
        self.assert_unwritten(result)

    def test_identity_formulas_and_changed_maximum_case_and_tool_version(self):
        first = self.preview()
        self.assertEqual(first['menu_document_id'], digest_json({'menu_version': 1,
            'tool_version': first['tool_version'], 'document_id': first['document_id'],
            'profile_sha256': first['profile_sha256']}))
        self.assertEqual(first['preview_id'], digest_json({'preview_version': 1,
            'tool_version': first['tool_version'], 'menu_document_id': first['menu_document_id'],
            'metrics_id': first['metrics_id'], 'cases_sha256': first['cases_sha256']}))
        self.fx['profile']['numeric_fields'][1]['maximum'] = 65534
        self.rebind()
        maximum = self.preview()
        self.assertNotEqual(first['preview_id'], maximum['preview_id'])
        self.fx['cases']['cases'][0]['dynamic_values'][0]['raw_hex'] = '30303133'
        case = self.preview()
        self.assertNotEqual(maximum['preview_id'], case['preview_id'])
        self.assertEqual(maximum['menu_document_id'], case['menu_document_id'])
        with mock.patch.object(self.module, 'ROMANCER_VERSION', 'test-version'):
            version = self.preview()
        self.assertNotEqual(case['menu_document_id'], version['menu_document_id'])
        self.assertNotEqual(case['preview_id'], version['preview_id'])
        self.assertEqual(case['metrics_id'], version['metrics_id'])

    def test_missing_truncated_sources_and_font_measurement_failure(self):
        self.source.unlink()
        missing = self.preview()
        self.assertEqual(missing['status'], 'BLOCKED')
        self.assertIsNone(missing['source_sha256'])
        self.source.write_bytes(self.fx['raw'][:-1])
        short = self.preview()
        self.assertEqual(short['error']['code'], 'SOURCE_BOUNDS')
        self.source.write_bytes(self.fx['raw'])
        self.fx['font_schema']['codec'] = 'future-codec'
        unsupported = self.preview()
        self.assertEqual(unsupported['status'], 'BLOCKED')
        self.assertEqual(unsupported['error']['code'], 'UNSUPPORTED_CODEC')
        self.fx['font_schema'] = menu_fixture()['font_schema']
        self.font.write_bytes(b'X' + self.fx['font'][1:])
        wrong = self.preview()
        self.assertEqual(wrong['status'], 'BLOCKED')
        self.assertEqual(wrong['error']['phase'], 'source_validation')
        self.assertFalse(wrong['ok'])

    def test_bounded_reads_through_real_upstream_streams(self):
        from romancer import script, font_metrics
        sizes = []

        class Reads:
            def __init__(self, stream):
                self.stream = stream

            def read(self, size=-1):
                self_outer.assertGreaterEqual(size, 0)
                self_outer.assertLessEqual(size, 65536)
                sizes.append(size)
                return self.stream.read(size)

            def __getattr__(self, name):
                return getattr(self.stream, name)

        self_outer = self
        inspect, measure = script.inspect_stream, font_metrics.measure_font_stream
        with mock.patch.object(script, 'inspect_stream', side_effect=lambda stream, schema: inspect(Reads(stream), schema)), mock.patch.object(
                font_metrics, 'measure_font_stream', side_effect=lambda stream, schema: measure(Reads(stream), schema)):
            result = self.preview()
        self.assertTrue(result['ok'], result)
        self.assertIn(32, sizes)
        self.assertIn(len(self.fx['font']), sizes)

    def test_inspection_retains_identity_when_guard_changes_after_parse(self):
        from romancer import script
        inspect = script.inspect_stream

        def change(stream, schema):
            document = inspect(stream, schema)
            with self.source.open('r+b') as writing:
                writing.seek(16)
                writing.write(b'\x00\x00')
            return document

        with mock.patch.object(script, 'inspect_stream', side_effect=change):
            result = self.inspect()
        self.assertEqual(result['error']['code'], 'SOURCE_CHANGED')
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.fx['raw']).hexdigest())
        self.assertFalse(result['ok'])


if __name__ == '__main__':
    unittest.main()
