import copy
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.layout_fixtures import digest_json, layout_fixture


class ShortReadFile:
    """Real held descriptor with deliberately short reads and a bounded-read guard."""

    def __init__(self, stream):
        self.stream = stream
        self.seeks = []

    def fileno(self):
        return self.stream.fileno()

    def seek(self, offset):
        self.seeks.append(offset)
        return self.stream.seek(offset)

    def read(self, size):
        if not 0 < size <= 65536:
            raise AssertionError('every font read must have a positive <=64 KiB bound')
        return self.stream.read(min(size, 113))


class FontMetricsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.font_metrics'),
                             'Task 1 font metrics service is not implemented')
        self.model = importlib.import_module('romancer.font_metrics')
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer font ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'toy font.bin'
        self.raw, self.font, self.script_schema, self.schema, self.policy = layout_fixture(
            [b'SORRY FOR', b'THE WAIT!'], 102)
        self.source.write_bytes(self.font)

    def measure(self):
        return self.model.measure_font(self.source, self.schema)

    def assert_blocked(self, result, status='BLOCKED'):
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['status'], status)
        self.assertEqual(result['glyphs'], [])
        self.assertIsNone(result['metrics_id'])
        self.assertFalse(result['native_font_usage_verified'])
        self.assertFalse(result['native_render_verified'])
        self.assertEqual(set(result['error']), {'phase', 'code', 'message'})
        self.assertTrue(result['error']['code'])

    def test_literal_bitmap_bounds_and_all_meaningful_bits(self):
        cases = [
            ('7088f88888', 5, 5, 1, [0, 0, 5, 5], 14),
            ('0000000000', 5, 5, 1, None, 0),
            ('00804000', 8, 4, 1, [0, 1, 2, 3], 2),
            ('010080800000', 9, 3, 2, [0, 0, 9, 2], 3),
            ('01', 8, 1, 1, [7, 0, 8, 1], 1),
        ]
        for hex_text, width, height, stride, bounds, pixels in cases:
            with self.subTest(raw=hex_text):
                raw = bytes.fromhex(hex_text)
                self.assertEqual(self.model.measure_bitmap(raw, width=width, height=height,
                    row_stride=stride), {'ink_bounds': bounds, 'ink_pixels': pixels,
                                        'bitmap_sha256': hashlib.sha256(raw).hexdigest()})

    def test_bitmap_rejects_bad_padding_length_dimensions_and_bool(self):
        cases = [(b'\x01', 5, 1, 1), (b'\x00\x01', 9, 1, 2),
                 (b'', 5, 1, 1), (b'\x00\x00', 5, 1, 1),
                 (b'\x00', True, 1, 1), (b'\x00', 5, False, 1),
                 (b'\x00', 5, 1, True), (b'\x00', 0, 1, 1),
                 (b'\x00' * 5, 33, 1, 5), (b'\x00' * 33, 5, 33, 1),
                 (b'\x00\x00', 5, 1, 2), (bytearray(b'\x00'), 5, 1, 1)]
        for raw, width, height, stride in cases:
            with self.subTest(raw=raw, width=width, height=height, stride=stride):
                with self.assertRaises(ValueError):
                    self.model.measure_bitmap(raw, width=width, height=height, row_stride=stride)

    def test_schema_roundtrip_detachment_and_ordered_identity(self):
        original = copy.deepcopy(self.schema)
        validated = self.model.validate_font_schema(self.schema)
        self.assertEqual(validated, {'normalized_schema': original,
            'font_schema_sha256': digest_json(original), 'measurement_supported': True,
            'read_only_reasons': []})
        validated['normalized_schema']['glyphs'][0]['bearing']['x'] = 9
        self.assertEqual(self.schema, original)
        reversed_schema = copy.deepcopy(original)
        reversed_schema['glyphs'].reverse()
        self.assertNotEqual(self.model.validate_font_schema(reversed_schema)['font_schema_sha256'],
                            validated['font_schema_sha256'])

    def test_schema_strict_nested_fields_types_ranges_and_provenance(self):
        cases = [
            ((), 'extra', 1), ((), 'schema_version', True), ((), 'schema_version', 2),
            ((), 'id', ''), ((), 'version', 'v\x85'), ((), 'id', 'x' * 129),
            (('source',), 'size', 0), (('source',), 'size', 16777217),
            (('source',), 'size', True), (('source',), 'sha256', 'A' * 64),
            (('source',), 'sha256', '0' * 63), (('source',), 'other', None),
            (('glyphs', 0), 'id', ' '), (('glyphs', 0), 'extra', 1),
            (('glyphs', 0, 'bitmap'), 'width', 33),
            (('glyphs', 0, 'bitmap'), 'row_stride', 2),
            (('glyphs', 0, 'bitmap'), 'offset', -1),
            (('glyphs', 0, 'bitmap'), 'offset', len(self.font)),
            (('glyphs', 0, 'bitmap'), 'height', True),
            (('glyphs', 0, 'bearing'), 'x', -65),
            (('glyphs', 0, 'bearing'), 'y', 65),
            (('glyphs', 0, 'bearing'), 'x', False),
            (('glyphs', 0, 'advance'), 'offset', len(self.font)),
            (('glyphs', 0, 'advance'), 'pixels', 6),
            (('glyphs', 0, 'advance'), 'kind', 'inferred'),
            (('provenance',), 'origin', 'verified_native'),
            (('provenance',), 'note', ' '), (('provenance',), 'note', 'x' * 513),
            (('provenance',), 'reference', 'x' * 257),
            (('glyphs', 0, 'provenance'), 'reference', 'a\x00b'),
        ]
        for path, key, value in cases:
            with self.subTest(path=path, key=key, value=value):
                schema = copy.deepcopy(self.schema)
                target = schema
                for part in path:
                    target = target[part]
                target[key] = value
                with self.assertRaises(ValueError):
                    self.model.validate_font_schema(schema)
        missing = copy.deepcopy(self.schema)
        del missing['glyphs'][0]['provenance']
        with self.assertRaises(ValueError):
            self.model.validate_font_schema(missing)

    def test_schema_duplicate_and_overlapping_ranges(self):
        for kind in ('id', 'bitmap', 'advance', 'bitmap_advance'):
            with self.subTest(kind=kind):
                schema = copy.deepcopy(self.schema)
                first, second = schema['glyphs'][:2]
                if kind == 'id':
                    second['id'] = first['id']
                elif kind == 'bitmap':
                    second['bitmap']['offset'] = 4
                elif kind == 'advance':
                    second['advance']['offset'] = first['advance']['offset']
                else:
                    first['advance']['offset'] = 4
                with self.assertRaises(ValueError):
                    self.model.validate_font_schema(schema)

    def test_schema_json_and_count_budgets(self):
        for value in (float('inf'), '\ud800', {'a': object()}):
            schema = copy.deepcopy(self.schema)
            schema['provenance']['reference'] = value
            with self.assertRaises(ValueError):
                self.model.validate_font_schema(schema)
        for value in ([], [None] * 257):
            schema = copy.deepcopy(self.schema)
            schema['glyphs'] = value
            with self.assertRaises(ValueError):
                self.model.validate_font_schema(schema)
        cyclic = copy.deepcopy(self.schema)
        cyclic['cycle'] = cyclic
        with self.assertRaises(ValueError):
            self.model.validate_font_schema(cyclic)
        for value in ('x' * 1048577, [None] * 100001):
            schema = copy.deepcopy(self.schema)
            schema['extra'] = value
            with self.assertRaises(ValueError):
                self.model.validate_font_schema(schema)

    def test_unknown_codec_is_unsupported_not_fake_measurement(self):
        self.schema['codec'] = 'other-row-codec'
        validated = self.model.validate_font_schema(self.schema)
        self.assertFalse(validated['measurement_supported'])
        self.assertTrue(validated['read_only_reasons'])
        self.assertEqual(validated['normalized_schema'], self.schema)
        self.assert_blocked(self.measure())

    def test_measured_rows_exact_shapes_identity_and_preservation(self):
        from romancer import ROMANCER_VERSION
        result = self.measure()
        self.assertTrue(result['ok'], result)
        self.assertEqual(set(result), {'schema_version', 'scope', 'operation', 'tool_version',
            'metrics_version', 'ok', 'status', 'source_sha256', 'source_size',
            'font_schema_sha256', 'metrics_id', 'glyphs', 'native_font_usage_verified',
            'native_render_verified', 'warnings', 'error'})
        self.assertEqual((result['scope'], result['operation'], result['status']),
                         ('native_font_metrics', 'measure', 'MEASURED'))
        self.assertEqual(result['tool_version'], ROMANCER_VERSION)
        self.assertIsNone(result['error'])
        self.assertFalse(result['native_font_usage_verified'])
        self.assertFalse(result['native_render_verified'])
        rows = {row['id']: row for row in result['glyphs']}
        descriptor = next(g for g in self.schema['glyphs'] if g['id'] == 'g65')
        prov = {'origin': 'synthetic_fixture', 'note': 'Declared toy model', 'reference': None}
        self.assertEqual(rows['g65'], {'id': 'g65',
            'bitmap': {**descriptor['bitmap'], 'raw_hex': '7088f88888',
                       'bitmap_sha256': hashlib.sha256(bytes.fromhex('7088f88888')).hexdigest()},
            'ink_bounds': [0, 0, 5, 5], 'ink_pixels': 14, 'bearing': {'x': 0, 'y': 0},
            'advance_pixels': 6, 'advance_origin': 'measured_u8',
            'advance_field': {'offset': descriptor['advance']['offset'], 'raw_hex': '06'},
            'provenance': {'glyph': prov, 'advance': prov}})
        self.assertEqual((rows['g32']['ink_bounds'], rows['g32']['ink_pixels'],
                          rows['g32']['advance_pixels']), (None, 0, 3))
        self.assertEqual(rows['g48']['advance_pixels'], 6)
        self.assertEqual(result['metrics_id'], digest_json({'metrics_version': 1,
            'font_schema_sha256': digest_json(self.schema),
            'source_sha256': hashlib.sha256(self.font).hexdigest(),
            'source_size': len(self.font), 'glyphs': result['glyphs']}))
        self.assertEqual(self.source.read_bytes(), self.font)
        result['glyphs'][0]['provenance']['glyph']['note'] = 'caller mutation'
        self.assertEqual(self.schema['glyphs'][0]['provenance'], prov)

    def test_declared_and_measured_advances_never_infer_ink_width(self):
        glyph = next(g for g in self.schema['glyphs'] if g['id'] == 'g65')
        original = self.measure()['metrics_id']
        identities = {original}
        for pixels in (0, 2, 128):
            glyph['advance'] = {'kind': 'declared', 'pixels': pixels,
                                'provenance': {'origin': 'profile_assertion',
                                               'note': 'Explicit spacing', 'reference': 'table-note'}}
            glyph['bearing'] = {'x': -2, 'y': 3}
            result = self.measure()
            self.assertTrue(result['ok'], result)
            row = next(g for g in result['glyphs'] if g['id'] == 'g65')
            self.assertEqual((row['advance_pixels'], row['advance_origin'], row['advance_field']),
                             (pixels, 'declared_pixels', None))
            self.assertEqual(row['ink_bounds'], [0, 0, 5, 5])
            self.assertEqual(row['bearing'], {'x': -2, 'y': 3})
            self.assertEqual(row['provenance']['advance'], glyph['advance']['provenance'])
            identities.add(result['metrics_id'])
        self.assertEqual(len(identities), 4)
        for pixels in (True, -1, 129):
            glyph['advance']['pixels'] = pixels
            with self.assertRaises(ValueError):
                self.model.validate_font_schema(self.schema)

    def test_wrong_revision_stops_before_range_measurement(self):
        self.source.write_bytes(bytes([self.font[0] ^ 1]) + self.font[1:])
        with patch.object(self.model, 'measure_bitmap', side_effect=AssertionError('offset use before binding')):
            result = self.measure()
        self.assert_blocked(result)
        self.assertEqual(result['error']['code'], 'REVISION_MISMATCH')

    def test_size_mismatch_missing_directory_and_empty_file_block(self):
        for value in (self.font[:-1], self.font + b'x', b''):
            self.source.write_bytes(value)
            self.assert_blocked(self.measure())
        self.source.unlink()
        self.assert_blocked(self.measure())
        self.source.mkdir()
        self.assert_blocked(self.measure())

    def test_bound_source_padding_and_u8_value_errors_are_not_partial_success(self):
        for offset, value in ((0, 1), (len(self.font) - 1, 129)):
            raw = bytearray(self.font)
            raw[offset] = value
            self.source.write_bytes(raw)
            self.schema['source']['sha256'] = hashlib.sha256(raw).hexdigest()
            self.assert_blocked(self.measure())

    def test_held_stream_identity_and_caller_ownership(self):
        with self.source.open('rb', buffering=0) as stream:
            info = os.fstat(stream.fileno())
            result = self.model.measure_font_stream(stream, self.schema)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['source_identity'],
                             [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns])
            self.assertFalse(stream.closed)
            self.schema['source']['sha256'] = '0' * 64
            self.assert_blocked(self.model.measure_font_stream(stream, self.schema))
            self.assertFalse(stream.closed)

    def test_final_content_hash_catches_same_size_rewrite_with_restored_mtime(self):
        original_measure = self.model.measure_bitmap
        before = self.source.stat()
        done = False

        def mutate(*args, **kwargs):
            nonlocal done
            result = original_measure(*args, **kwargs)
            if not done:
                done = True
                raw = bytearray(self.font)
                raw[-1] = 7
                self.source.write_bytes(raw)
                os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
            return result

        with patch.object(self.model, 'measure_bitmap', side_effect=mutate):
            result = self.measure()
        self.assert_blocked(result)
        self.assertEqual(result['error']['code'], 'SOURCE_CHANGED')

    def test_file_cancellation_closes_owned_handle_and_keeps_input(self):
        opened = []
        original_open = Path.open

        def track(path, *args, **kwargs):
            handle = original_open(path, *args, **kwargs)
            opened.append(handle)
            return handle

        with patch.object(Path, 'open', track), patch.object(self.model, 'measure_bitmap',
                                                            side_effect=KeyboardInterrupt):
            result = self.measure()
        self.assert_blocked(result, 'CANCELLED')
        self.assertTrue(opened)
        self.assertTrue(all(handle.closed for handle in opened))
        self.assertEqual(self.source.read_bytes(), self.font)

    def test_symlink_and_linked_ancestor_are_rejected_without_modifying_target(self):
        link = self.root / 'alias'
        try:
            link.symlink_to(self.source)
        except OSError as exc:
            self.skipTest(f'symlink creation unavailable: {exc}')
        self.assert_blocked(self.model.measure_font(link, self.schema))
        link.unlink()
        directory = self.root / 'linked directory'
        directory.symlink_to(self.root, target_is_directory=True)
        self.assert_blocked(self.model.measure_font(directory / self.source.name, self.schema))
        self.assertEqual(self.source.read_bytes(), self.font)

    @unittest.skipUnless(os.name == 'nt', 'Windows aliases only')
    def test_windows_reserved_and_ads_paths_reject_before_open(self):
        for name in ('font.bin:stream', 'NUL', 'font.bin.', 'font.bin '):
            with self.subTest(name=name), patch.object(Path, 'open',
                    side_effect=AssertionError('ambiguous path must never open')):
                self.assert_blocked(self.model.measure_font(self.root / name, self.schema))

    @unittest.skipUnless(os.name == 'nt', 'Windows drive-relative semantics only')
    def test_windows_drive_relative_spelling_rejects_before_any_open(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            drive = self.root.drive
            for spelling in (drive + self.source.name, drive.lower() + '.\\' + self.source.name,
                             drive + '..\\' + self.source.name, drive):
                with self.subTest(spelling=spelling), patch.object(Path, 'open',
                        side_effect=AssertionError('drive-relative font must never open')):
                    result = self.model.measure_font(Path(spelling), self.schema)
                    self.assert_blocked(result)
                    self.assertEqual(result['error']['code'], 'UNSAFE_PATH')
        finally:
            os.chdir(previous)
        self.assertEqual(self.source.read_bytes(), self.font)

    def test_ordinary_relative_and_absolute_paths_remain_measurable(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            for path in (Path(self.source.name), Path('.') / self.source.name, self.source):
                with self.subTest(path=path):
                    result = self.model.measure_font(path, self.schema)
                    self.assertTrue(result['ok'], result)
                    self.assertEqual(result['status'], 'MEASURED')
        finally:
            os.chdir(previous)
        self.assertEqual(self.source.read_bytes(), self.font)

    def test_independent_fixture_matches_v37_schema_and_literal_trailing_segments(self):
        from romancer.script_schema import validate_schema
        from romancer.script import inspect_script
        raw, font, schema, font_schema, policy = layout_fixture(
            [b'ARE THERE ORKS UP AHEAD?', b'', b''], 129)
        self.assertEqual(raw, b'\x08\x00GUARD!ARE THERE ORKS UP AHEAD?\xe1\xe1\x00'
                             + b'\xff' * 8 + bytes.fromhex('11223344'))
        self.assertEqual(validate_schema(schema)['schema_sha256'], policy['script_schema_sha256'])
        script = self.root / 'script.bin'
        script.write_bytes(raw)
        doc = inspect_script(script, schema)
        self.assertTrue(doc['ok'], doc)
        self.assertEqual(doc['document_id'], policy['document_id'])
        self.assertEqual([s['text'] for s in doc['records'][0]['segments']],
                         ['ARE THERE ORKS UP AHEAD?', '', ''])
        self.assertEqual(self.model.validate_font_schema(font_schema)['font_schema_sha256'],
                         policy['font_schema_sha256'])
        self.assertEqual(font, self.font)

    def test_bounded_short_reads_and_exactly_two_complete_hash_passes(self):
        raw = self.font + b'\x7f' * 140000
        self.source.write_bytes(raw)
        self.schema['source'] = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
        original_hash = self.model._hash_stream
        passes = []

        def count_pass(stream, size):
            passes.append(size)
            return original_hash(stream, size)

        with self.source.open('rb', buffering=0) as stream:
            reader = ShortReadFile(stream)
            with patch.object(self.model, '_hash_stream', side_effect=count_pass):
                result = self.model.measure_font_stream(reader, self.schema)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(passes, [len(raw), len(raw)])
            self.assertFalse(stream.closed)
            raw = raw[:-1] + b'\x7e'
            self.source.write_bytes(raw)
            reader.seeks.clear()
            rejected = self.model.measure_font_stream(reader, self.schema)
            self.assert_blocked(rejected)
            self.assertEqual(rejected['error']['code'], 'REVISION_MISMATCH')
            self.assertEqual(reader.seeks, [0], 'revision failure must precede every range seek')

    def test_replacement_during_open_rejects_even_identical_bytes_and_mtime(self):
        info = self.source.stat()
        replacement = self.root / 'replacement.bin'
        replacement.write_bytes(self.font)
        os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
        old = self.root / 'old.bin'
        original_open = Path.open

        def substitute(path, *args, **kwargs):
            self.source.rename(old)
            replacement.rename(self.source)
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', substitute):
            result = self.measure()
        self.assert_blocked(result)
        self.assertEqual(result['error']['code'], 'SOURCE_CHANGED')
        self.assertEqual(old.read_bytes(), self.font)
        self.assertEqual(self.source.read_bytes(), self.font)

    def test_final_identity_checks_follow_result_computation_with_handle_still_open(self):
        original_bound = self.model._bounded_result
        opened = []
        original_open = Path.open

        def track(path, *args, **kwargs):
            handle = original_open(path, *args, **kwargs)
            opened.append(handle)
            return handle

        def touch_after_result(result):
            result = original_bound(result)
            self.assertTrue(opened)
            self.assertFalse(opened[0].closed)
            before = self.source.stat()
            os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns + 2000000000))
            return result

        with patch.object(Path, 'open', track), patch.object(self.model, '_bounded_result',
                                                            side_effect=touch_after_result):
            result = self.measure()
        self.assert_blocked(result)
        self.assertEqual(result['error']['code'], 'SOURCE_CHANGED')
        self.assertTrue(all(handle.closed for handle in opened))

    @unittest.skipIf(os.name == 'nt', 'Windows denies replacing an open non-delete-shared file')
    def test_final_path_sweep_catches_replacement_and_absence_after_last_hash(self):
        original_bound = self.model._bounded_result
        for replace in (False, True):
            with self.subTest(replace=replace):
                self.source.write_bytes(self.font)
                old = self.root / ('old-' + str(replace))
                replacement = self.root / 'next.bin'
                replacement.write_bytes(b'x' * len(self.font))
                changed = False

                def change_after_hash(result):
                    nonlocal changed
                    result = original_bound(result)
                    if not changed:
                        changed = True
                        self.source.rename(old)
                        if replace:
                            replacement.rename(self.source)
                    return result

                with patch.object(self.model, '_bounded_result', side_effect=change_after_hash):
                    result = self.measure()
                self.assert_blocked(result)
                self.assertEqual(old.read_bytes(), self.font)
                if replace:
                    self.assertEqual(self.source.read_bytes(), b'x' * len(self.font))
                else:
                    self.assertFalse(self.source.exists())

    def test_source_growth_and_truncation_during_measurement_block(self):
        original_measure = self.model.measure_bitmap
        for changed in (self.font + b'x', self.font[:-1]):
            with self.subTest(size=len(changed)):
                self.source.write_bytes(self.font)

                def change_size(*args, **kwargs):
                    result = original_measure(*args, **kwargs)
                    self.source.write_bytes(changed)
                    return result

                with patch.object(self.model, 'measure_bitmap', side_effect=change_size):
                    self.assert_blocked(self.measure())

    def test_held_cancellation_and_oserror_preserve_caller_handle(self):
        for exc, status in ((KeyboardInterrupt(), 'CANCELLED'), (OSError('read failed'), 'BLOCKED')):
            with self.subTest(status=status), self.source.open('rb', buffering=0) as stream:
                with patch.object(self.model, 'measure_bitmap', side_effect=exc):
                    result = self.model.measure_font_stream(stream, self.schema)
                self.assert_blocked(result, status)
                self.assertEqual(result['error']['phase'], 'measurement')
                self.assertIsNone(result['source_identity'])
                self.assertFalse(stream.closed)

    def test_report_budget_covers_pretty_json_not_just_compact_payload(self):
        result = self.measure()
        compact_size = len(json.dumps(result, sort_keys=True, separators=(',', ':'),
                                      ensure_ascii=True))
        with patch.object(self.model, 'MAX_REPORT_BYTES', compact_size + 512):
            rejected = self.measure()
        self.assert_blocked(rejected)
        self.assertEqual(rejected['error']['code'], 'REPORT_LIMIT')

    def test_oversize_actual_source_rejects_without_reading(self):
        with self.source.open('r+b') as stream:
            stream.truncate(16777217)
        with patch.object(Path, 'open', side_effect=AssertionError('oversize file must not open')):
            result = self.measure()
        self.assert_blocked(result)
        self.assertEqual(result['error']['code'], 'SOURCE_BOUNDS')

    def test_maximum_cell_and_glyph_count_are_measurable(self):
        prov = {'origin': 'synthetic_fixture', 'note': 'Maximum toy cells', 'reference': None}
        raw = b'\xff' * (128 * 256)
        schema = {'schema_version': 1, 'id': 'max-font', 'version': '1',
            'source': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)},
            'codec': 'mono-row-msb-v1', 'provenance': prov, 'glyphs': [
                {'id': str(i), 'bitmap': {'offset': i * 128, 'width': 32, 'height': 32, 'row_stride': 4},
                 'bearing': {'x': -64, 'y': 64}, 'advance': {'kind': 'declared', 'pixels': 128,
                 'provenance': prov}, 'provenance': prov} for i in range(256)]}
        self.source.write_bytes(raw)
        result = self.model.measure_font(self.source, schema)
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['glyphs']), 256)
        for row in result['glyphs']:
            self.assertEqual(row['ink_bounds'], [0, 0, 32, 32])
            self.assertEqual(row['ink_pixels'], 1024)
        schema['glyphs'].append(copy.deepcopy(schema['glyphs'][0]))
        with self.assertRaises(ValueError):
            self.model.validate_font_schema(schema)

    def test_schema_capture_prevents_mutation_during_long_file_work(self):
        original_hash = self.model._hash_stream
        before = copy.deepcopy(self.schema)

        def caller_mutates(stream, size):
            self.schema['glyphs'].clear()
            self.schema['source']['sha256'] = '0' * 64
            return original_hash(stream, size)

        with patch.object(self.model, '_hash_stream', side_effect=caller_mutates):
            result = self.measure()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['font_schema_sha256'], digest_json(before))
        self.assertEqual(len(result['glyphs']), len(before['glyphs']))


if __name__ == '__main__':
    unittest.main()
