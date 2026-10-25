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


def literal_font():
    raw = bytes.fromhex('80800000c0400302')
    provenance = {'origin': 'synthetic_fixture', 'note': 'Literal menu glyphs', 'reference': None}
    schema = {'schema_version': 1, 'id': 'menu-font', 'version': '1',
              'source': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)},
              'codec': 'mono-row-msb-v1', 'provenance': dict(provenance), 'glyphs': []}
    for identifier, offset, bearing, advance in (
        ('bar', 0, {'x': 0, 'y': 0}, {'kind': 'u8', 'offset': 6}),
        ('gap', 2, {'x': 0, 'y': 0}, {'kind': 'declared', 'pixels': 2, 'provenance': dict(provenance)}),
        ('wide', 4, {'x': -1, 'y': 1}, {'kind': 'u8', 'offset': 7}),
    ):
        schema['glyphs'].append({'id': identifier, 'bitmap': {'offset': offset, 'width': 2,
            'height': 2, 'row_stride': 1}, 'bearing': bearing, 'advance': advance,
            'provenance': dict(provenance)})
    mapping = [{'scalar': scalar, 'glyph_id': identifier, 'provenance': dict(provenance)}
               for scalar, identifier in [('A', 'bar'), ('B', 'wide'), (' ', 'gap'), ('0', 'wide')]]
    return raw, schema, mapping


class MenuMetricsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.menu_metrics'), 'menu metrics adapter is absent')
        self.module = importlib.import_module('romancer.menu_metrics')
        self.temp = tempfile.TemporaryDirectory(prefix='menu metrics ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.font = self.root / 'font.bin'
        self.raw, self.schema, self.mapping = literal_font()
        self.font.write_bytes(self.raw)

    def opened(self):
        return self.module.open_menu_metrics(self.font, self.schema, self.mapping)

    def test_literal_run_uses_measured_bearings_and_blank_advance(self):
        with self.opened() as metrics:
            self.assertEqual(metrics.measure('A B'), {'advance_px': 7, 'ink_bounds': [0, 0, 6, 3],
                'placements': [
                    {'scalar_index': 0, 'scalar': 'A', 'glyph_id': 'bar', 'x': 0, 'y': 0,
                     'advance_px': 3, 'ink_bounds': [0, 0, 1, 2]},
                    {'scalar_index': 1, 'scalar': ' ', 'glyph_id': 'gap', 'x': 3, 'y': 0,
                     'advance_px': 2, 'ink_bounds': None},
                    {'scalar_index': 2, 'scalar': 'B', 'glyph_id': 'wide', 'x': 5, 'y': 0,
                     'advance_px': 2, 'ink_bounds': [4, 1, 6, 3]},
                ]})
            self.assertEqual(metrics.measure(''), {'advance_px': 0, 'ink_bounds': None, 'placements': []})
            self.assertEqual(metrics.measure('00')['advance_px'], 4)
        self.assertEqual(self.font.read_bytes(), self.raw)

    def test_identity_and_advance_provenance_are_preserved(self):
        with self.opened() as metrics:
            self.assertEqual(metrics.identity['font_sha256'], hashlib.sha256(self.raw).hexdigest())
            self.assertEqual(metrics.identity['font_size'], 8)
            bar, gap = metrics.glyphs_by_id['bar'], metrics.glyphs_by_id['gap']
            self.assertEqual(bar['advance_origin'], 'measured_u8')
            self.assertEqual(bar['advance_field'], {'offset': 6, 'raw_hex': '03'})
            self.assertEqual(gap['advance_origin'], 'declared_pixels')
            self.assertIsNone(gap['advance_field'])
            self.assertEqual(bar['provenance']['glyph'], self.schema['glyphs'][0]['provenance'])
            self.assertEqual(gap['provenance']['advance'], self.schema['glyphs'][1]['advance']['provenance'])

    def test_mapping_detached_and_hashed_independently_of_font(self):
        with self.opened() as before:
            first_id = before.identity['metrics_id']
            first_map = before.glyph_map_sha256
            self.mapping[0]['glyph_id'] = 'wide'
            self.schema['glyphs'][0]['bearing']['x'] = 20
            self.assertEqual(before.measure('A')['ink_bounds'], [0, 0, 1, 2])
        self.schema['glyphs'][0]['bearing']['x'] = 0
        with self.opened() as after:
            self.assertEqual(first_id, after.identity['metrics_id'])
            self.assertNotEqual(first_map, after.glyph_map_sha256)
            self.assertEqual(after.measure('A')['ink_bounds'], [-1, 1, 1, 3])
            expected = sorted(self.mapping, key=lambda row: ord(row['scalar']))
            digest = hashlib.sha256(json.dumps(expected, sort_keys=True, ensure_ascii=True,
                separators=(',', ':')).encode('ascii')).hexdigest()
            self.assertEqual(after.glyph_map_sha256, digest)

    def test_missing_duplicate_and_dangling_mapping_refuse(self):
        with self.opened() as metrics:
            with self.assertRaises(ValueError):
                metrics.measure('X')
        for change in ('duplicate', 'dangling'):
            raw, schema, mapping = literal_font()
            self.mapping = mapping
            if change == 'duplicate':
                self.mapping.append(copy.deepcopy(mapping[0]))
            else:
                self.mapping[0]['glyph_id'] = 'absent'
            with self.subTest(change=change), self.assertRaises(ValueError):
                with self.opened():
                    self.fail('invalid mapping was accepted')

    def test_cumulative_placement_budget(self):
        with self.opened() as metrics:
            self.assertEqual(len(metrics.measure('A' * 2048)['placements']), 2048)
            with self.assertRaises(ValueError):
                metrics.measure('A')

    def test_unsupported_wrong_revision_and_cancelled_measurement_refuse(self):
        self.schema['codec'] = 'unknown'
        with self.assertRaises(ValueError):
            with self.opened():
                self.fail('unsupported measurement was accepted')
        self.schema['codec'] = 'mono-row-msb-v1'
        self.font.write_bytes(self.raw[:-1] + b'\x04')
        with self.assertRaises(ValueError):
            with self.opened():
                self.fail('wrong revision was accepted')
        self.font.write_bytes(self.raw)
        with patch('romancer.font_metrics.measure_bitmap', side_effect=KeyboardInterrupt):
            with self.assertRaises(ValueError) as raised:
                with self.opened():
                    self.fail('cancelled measurement was accepted')
        self.assertEqual(raised.exception.code, 'CANCELLED')
        self.assertEqual(raised.exception.phase, 'measurement')

    def test_actual_font_handle_remains_open_and_closes_on_error(self):
        real_measure = importlib.import_module('romancer.font_metrics').measure_font_stream
        streams = []
        def measure(stream, schema):
            streams.append(stream)
            return real_measure(stream, schema)
        with patch('romancer.font_metrics.measure_font_stream', side_effect=measure):
            with self.assertRaisesRegex(ValueError, 'consumer failure'):
                with self.opened() as metrics:
                    self.assertFalse(streams[0].closed)
                    metrics.assert_stable()
                    raise ValueError('consumer failure')
        self.assertTrue(streams[0].closed)

    def test_late_font_change_refuses_context_completion(self):
        with self.assertRaises(ValueError):
            with self.opened():
                self.font.write_bytes(self.raw + b'X')

    def test_linked_font_ancestry_is_refused(self):
        link = self.root / 'alias'
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        self.font = link / 'font.bin'
        with self.assertRaises(ValueError):
            with self.opened():
                self.fail('linked font accepted')


if __name__ == '__main__':
    unittest.main()
