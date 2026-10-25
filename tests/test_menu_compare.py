"""Exact pixel and stored-evidence checks for menu comparisons."""
import copy
from contextlib import closing
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib

from romancer import capture_ingest, capture_runtime, capture_store, history


def chunk(kind, payload=b''):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload)))


def png_rgb(width, height, rgb):
    rows = b''.join(b'\0' + rgb[y * width * 3:(y + 1) * width * 3]
                    for y in range(height))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND'))


def image_metadata(raw, rgb, width=2, height=2):
    return dict(blob_sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw),
                width=width, height=height, rgb_sha256=hashlib.sha256(rgb).hexdigest(),
                media_type='image/png', normalization='rgb24')


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.menu_compare'),
                             'Task 4 comparator has not been implemented')
        self.compare = importlib.import_module('romancer.menu_compare')
        self.rgb = bytes.fromhex('000000 ff0000 00ff00 0000ff')

    def test_literal_pixel_difference_and_half_open_bounds(self):
        other = bytes.fromhex('000000 ff0000 00ff00 000000')
        self.assertEqual(self.compare.compare_rgb_region(self.rgb, other, 2, 2, [0, 0, 2, 2]),
                         dict(total_pixels=4, different_pixels=1,
                              difference_bounds=[1, 1, 2, 2]))
        self.assertEqual(self.compare.compare_rgb_region(self.rgb, other, 2, 2, [0, 0, 2, 1]),
                         dict(total_pixels=2, different_pixels=0, difference_bounds=None))

    def test_bounds_are_absolute_not_roi_relative(self):
        other = bytes.fromhex('000000 000000 00ff00 000000')
        self.assertEqual(self.compare.compare_rgb_region(self.rgb, other, 2, 2, [1, 0, 1, 2]),
                         dict(total_pixels=2, different_pixels=2,
                              difference_bounds=[1, 0, 2, 2]))

    def test_region_rejects_invalid_geometry_and_bool(self):
        for region in ([], [0, 0, 0, 1], [-1, 0, 1, 1], [0, 0, 3, 1],
                       [0, 2, 1, 1], [False, 0, 1, 1], [0, 0, 1.0, 1],
                       [0, 0, 1, 1, 1], (0, 0, 1, 1)):
            with self.subTest(region=region), self.assertRaises(ValueError):
                self.compare.compare_rgb_region(self.rgb, self.rgb, 2, 2, region)

    def test_rgb_length_dimensions_and_work_bounds(self):
        for width, height, a, b in ((True, 2, self.rgb, self.rgb),
                                     (0, 2, b'', b''), (4097, 1, b'', b''),
                                     (2, 2, self.rgb[:-1], self.rgb),
                                     (2, 2, self.rgb, self.rgb + b'\0'),
                                     (4096, 4096, b'', b'')):
            with self.subTest(width=width, height=height), self.assertRaises(ValueError):
                self.compare.compare_rgb_region(a, b, width, height, [0, 0, 1, 1])
        raw = b'\0' * (1025 * 1024 * 3)
        with self.assertRaises(ValueError):
            self.compare.compare_rgb_region(raw, raw, 1025, 1024, [0, 0, 1025, 1024])

    def test_decode_exact_rgb_and_ancillary_png(self):
        raw = png_rgb(2, 2, self.rgb)
        ancillary = raw[:-12] + chunk(b'tEXt', b'note\0not menu semantics') + raw[-12:]
        for encoded in (raw, ancillary):
            self.assertEqual(self.compare._decode_capture_png(
                encoded, image_metadata(encoded, self.rgb)), self.rgb)

    def test_decode_checks_file_and_pixel_identity(self):
        raw = png_rgb(2, 2, self.rgb)
        for key, value in (('width', 1), ('height', 1), ('rgb_sha256', '0' * 64),
                           ('blob_sha256', '0' * 64), ('byte_size', len(raw) + 1)):
            metadata = image_metadata(raw, self.rgb)
            metadata[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.compare._decode_capture_png(raw, metadata)

    def test_complete_chunk_crc_and_terminal_iend_required(self):
        raw = png_rgb(2, 2, self.rgb)
        variants = (raw[:-1], raw[:-12], raw + b'trailing',
                    raw[:-4] + b'\0\0\0\0',
                    raw[:-12] + chunk(b'IEND', b'x'),
                    raw[:-12] + struct.pack('>I', 100) + b'tEXt' + raw[-12:],
                    raw[:40] + bytes([raw[40] ^ 1]) + raw[41:])
        for index, encoded in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.compare._decode_capture_png(encoded, image_metadata(encoded, self.rgb))

    def test_decode_corrupt_compressed_pixels(self):
        raw = png_rgb(2, 2, self.rgb)
        corrupt = raw[:33] + chunk(b'IDAT', b'not a zlib stream') + chunk(b'IEND')
        with self.assertRaises(ValueError):
            self.compare._decode_capture_png(corrupt, image_metadata(corrupt, self.rgb))

    def test_decode_refuses_animation_including_single_frame_apng(self):
        raw = png_rgb(2, 2, self.rgb)
        for frames in (1, 2):
            animated = (raw[:33] + chunk(b'acTL', struct.pack('>II', frames, 0))
                        + chunk(b'fcTL', struct.pack('>IIIIIHHBB', 0, 2, 2, 0, 0, 1, 10, 0, 0))
                        + raw[33:])
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                self.compare._decode_capture_png(animated, image_metadata(animated, self.rgb))

    def test_decode_bounds_before_pixel_allocation(self):
        for width, height in ((4097, 1), (4096, 4096), (0, 2)):
            raw = (b'\x89PNG\r\n\x1a\n'
                   + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                   + chunk(b'IDAT', zlib.compress(b'')) + chunk(b'IEND'))
            with self.subTest(width=width), self.assertRaises(ValueError):
                self.compare._decode_capture_png(raw, image_metadata(raw, b'', width, height))
        raw = b'x' * (16 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError):
            self.compare._decode_capture_png(raw, image_metadata(raw, b''))

    def test_missing_pillow_does_not_use_hash_fallback(self):
        raw = png_rgb(2, 2, self.rgb)
        with mock.patch.dict('sys.modules', {'PIL': None, 'PIL.Image': None}):
            with self.assertRaisesRegex(ValueError, 'Pillow'):
                self.compare._decode_capture_png(raw, image_metadata(raw, self.rgb))

    def test_pillow_bomb_warning_is_a_refusal(self):
        from PIL import Image
        raw = png_rgb(2, 2, self.rgb)
        with mock.patch.object(Image, 'MAX_IMAGE_PIXELS', 3):
            with self.assertRaises(ValueError):
                self.compare._decode_capture_png(raw, image_metadata(raw, self.rgb))

    def test_report_budget_includes_pretty_whitespace_and_final_newline(self):
        literal = b'{\n  "value": "x"\n}\n'
        with mock.patch.object(self.compare, 'MAX_REPORT', len(literal)):
            self.compare._check_report({'value': 'x'})
        with mock.patch.object(self.compare, 'MAX_REPORT', len(literal) - 1):
            with self.assertRaises(ValueError):
                self.compare._check_report({'value': 'x'})
        with self.assertRaises(ValueError):
            self.compare._check_report({'too_many_nodes': [None] * 100000})


class RequestPreflightTests(unittest.TestCase):
    def test_raised_preview_errors_keep_status_phase_code_and_no_capture_claim(self):
        from romancer import menu, menu_compare
        from romancer.menu_metrics import MenuError
        from tests.menu_fixtures import comparison_fixture
        for status in ('FAIL', 'BLOCKED', 'CANCELLED'):
            failure = MenuError('FONT_REFUSAL', 'test-only preview refusal',
                                phase='font_measurement', status=status)
            with self.subTest(status=status), mock.patch.object(menu, '_preview_inputs',
                    side_effect=failure, create=True), mock.patch.object(capture_store, 'get_capture') as get:
                result = menu_compare.compare_menu_captures(None, None, {}, {}, {}, {}, None,
                                                            comparison_fixture())
            self.assertEqual(result['status'], status, result)
            self.assertEqual(result['preview_status'], status)
            self.assertEqual(result['comparison_status'], 'NOT_RUN')
            self.assertEqual(result['error']['phase'], 'font_measurement')
            self.assertEqual(result['error']['code'], 'FONT_REFUSAL')
            self.assertFalse(result['native_capture_verified'])
            self.assertFalse(result['ok'])
            get.assert_not_called()

    def test_invalid_requests_never_retrieve_capture_or_open_preview(self):
        from romancer import menu_compare
        from tests.menu_fixtures import comparison_fixture
        for case in ('empty', 'over_pairs', 'over_pixels', 'extra', 'bool', 'oversize', 'self'):
            request = comparison_fixture()
            if case == 'empty':
                request['pairs'] = []
            elif case == 'over_pairs':
                request['pairs'] = [dict(request['pairs'][0], id=str(i)) for i in range(17)]
            elif case == 'over_pixels':
                request['pairs'] = [dict(request['pairs'][0], id=str(i), region=[0, 0, 1024, 1024])
                                    for i in range(2)]
            elif case == 'extra':
                request['pairs'][0]['native_capture_verified'] = True
            elif case == 'bool':
                request['pairs'][0]['region'][0] = False
            elif case == 'oversize':
                request['pairs'][0]['provenance']['note'] = 'x' * (1024 * 1024)
            else:
                request['pairs'][0]['reference']['capture_id'] = request['pairs'][0]['target']['capture_id']
            with self.subTest(case=case), mock.patch.object(capture_store, 'get_capture') as get:
                result = menu_compare.compare_menu_captures(None, None, {}, {}, {}, {}, None, request)
                self.assertEqual(result['status'], 'BLOCKED', result)
                self.assertEqual(result['preview_status'], 'NOT_RUN')
                self.assertFalse(result['ok'])
                self.assertFalse(result['native_capture_verified'])
                get.assert_not_called()


class StoreFixture(unittest.TestCase):
    def setUp(self):
        self.compare = importlib.import_module('romancer.menu_compare')
        self.temp = tempfile.TemporaryDirectory(prefix='menu comparison ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        history.init_history(self.project)
        capture_store.init_capture_store(self.project)
        self.rgb = bytes.fromhex('000000 ff0000 00ff00 0000ff')

    def imported(self, raw=None, build_id=None):
        path = self.root / 'import.png'
        path.write_bytes(png_rgb(2, 2, self.rgb) if raw is None else raw)
        result = capture_ingest.import_capture(self.project, path, {
            'build_id': build_id, 'declared_context': {
                'captured_utc': None, 'game_sha256': None, 'core_sha256': None,
                'run_mode': 'cold_boot', 'state_derived': False,
                'source_note': 'Synthetic supplied label, not native evidence'},
            'annotations': []}, self.root)
        return capture_store.get_capture(self.project, result['capture_id'])

    @staticmethod
    def selector(record, target=False):
        result = dict(capture_id=record['capture_id'],
                      build_id=record['build']['build_id'] if record['build'] else '0' * 64,
                      png_sha256=record['image']['blob_sha256'],
                      rgb_sha256=record['image']['rgb_sha256'])
        if target:
            result.update(source_role='menu', font_role='font')
        return result

    def database_bytes(self):
        return (self.project / '.romancer-evidence/captures.sqlite3').read_bytes()


class StoredPngTests(StoreFixture):
    def test_decode_actual_get_capture_bytes_without_store_changes(self):
        stored = self.imported()
        before = self.database_bytes()
        self.assertEqual(self.compare._decode_capture_png(stored['png_bytes'],
                                                         stored['record']['image']), self.rgb)
        self.assertEqual(self.database_bytes(), before)

    def test_imported_origin_refused_before_decode(self):
        stored = self.imported()
        self.assertTrue(hasattr(self.compare, '_read_native_capture'), 'native retrieval not implemented')
        before = self.database_bytes()
        with mock.patch.object(self.compare, '_decode_capture_png') as decode:
            with self.assertRaisesRegex(ValueError, 'native_worker'):
                self.compare._read_native_capture(self.project, self.selector(stored['record']))
            decode.assert_not_called()
        self.assertEqual(self.database_bytes(), before)


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('gcc'),
                     'actual synthetic native captures require Linux Python and gcc')
class NativeFixture(StoreFixture):
    @classmethod
    def setUpClass(cls):
        cls.core_temp = tempfile.TemporaryDirectory(prefix='menu native core ')
        cls.addClassCleanup(cls.core_temp.cleanup)
        cls.core = Path(cls.core_temp.name) / 'mock.so'
        subprocess.run(['gcc', '-shared', '-fPIC', '-O2', '-DROMANCER_V35_TEST',
                        str(Path(__file__).with_name('mock_libretro.c')), '-o', str(cls.core)],
                       check=True, capture_output=True)

    def setUp(self):
        super().setUp()
        from tests.menu_fixtures import menu_fixture, write_menu_fixture
        self.fixture = menu_fixture()
        self.paths = write_menu_fixture(self.root / 'inputs', self.fixture)
        self.game = self.root / 'game.bin'
        self.game.write_bytes(b'synthetic game')
        self.build = self.register_build()
        self.session_number = 0

    def register_build(self, settings=None):
        return history.register_build(self.project, {
            'inputs': [{'role': 'menu', 'path': str(self.paths['source'])},
                       {'role': 'font', 'path': str(self.paths['font'])}],
            'output': str(self.game), 'adapter': {'name': 'generic', 'version': '1'},
            'profile': {'name': 'synthetic', 'version': '1'},
            'settings': {} if settings is None else settings}, self.root)

    def native(self, *, buttons=None, frames=1, build_id=None, options=None, state=None):
        self.session_number += 1
        config = {'load': {'core': str(self.core), 'game': str(self.game),
                          'expected_core_sha256': hashlib.sha256(self.core.read_bytes()).hexdigest(),
                          'expected_game_sha256': hashlib.sha256(self.game.read_bytes()).hexdigest(),
                          'session_dir': str(self.root / ('session' + str(self.session_number)))},
                  'steps': [{'frames': frames, 'buttons': [] if buttons is None else buttons, 'port': 0}],
                  'initial_state_file': state, 'timeout': 10}
        if options is not None:
            config['load']['core_options'] = options
        result = capture_runtime.capture_run(self.project, build_id or self.build['build_id'],
                                             config, self.root)
        self.assertTrue(result['ok'], result)
        return capture_store.get_capture(self.project, result['capture_id'])


class NativeRetrievalTests(NativeFixture):
    def test_real_separate_captures_retrieve_and_compare_pixels(self):
        first, second = self.native(), self.native()
        self.assertTrue(hasattr(self.compare, '_read_native_capture'), 'native retrieval not implemented')
        before = self.database_bytes()
        record, pixels = self.compare._read_native_capture(self.project, self.selector(first['record']))
        other, other_pixels = self.compare._read_native_capture(self.project, self.selector(second['record']))
        self.assertNotEqual(record['capture_id'], other['capture_id'])
        self.assertEqual(record, first['record'])
        self.assertEqual(pixels, other_pixels)
        self.assertTrue(any(pixels))
        self.assertEqual(self.compare.compare_rgb_region(pixels, other_pixels,
                         record['image']['width'], record['image']['height'], [0, 0, 2, 2]),
                         dict(total_pixels=4, different_pixels=0, difference_bounds=None))
        self.assertEqual(self.database_bytes(), before)

    def test_exact_native_selector_mismatches_refuse(self):
        stored = self.native()
        self.assertTrue(hasattr(self.compare, '_read_native_capture'), 'native retrieval not implemented')
        for key in ('capture_id', 'build_id', 'png_sha256', 'rgb_sha256'):
            selector = self.selector(stored['record'])
            selector[key] = '0' * len(selector[key])
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.compare._read_native_capture(self.project, selector)

    def test_same_output_different_build_selector_is_not_interchangeable(self):
        stored = self.native()
        self.assertTrue(hasattr(self.compare, '_read_native_capture'), 'native retrieval not implemented')
        different = self.register_build({'revision': 'different registration'})
        self.assertNotEqual(different['build_id'], self.build['build_id'])
        selector = self.selector(stored['record'])
        selector['build_id'] = different['build_id']
        with self.assertRaisesRegex(ValueError, 'selector'):
            self.compare._read_native_capture(self.project, selector)

    def test_identical_imported_copy_is_not_native(self):
        stored = self.native()
        imported = self.imported(stored['png_bytes'], self.build['build_id'])
        self.assertEqual(imported['png_bytes'], stored['png_bytes'])
        self.assertTrue(hasattr(self.compare, '_read_native_capture'), 'native retrieval not implemented')
        with self.assertRaisesRegex(ValueError, 'native_worker'):
            self.compare._read_native_capture(self.project, self.selector(imported['record']))

    def test_fresh_role_membership_matches_size_and_hash(self):
        record = self.native()['record']
        self.assertTrue(hasattr(self.compare, '_check_membership'), 'role validation not implemented')
        selector = self.selector(record, target=True)
        source = (hashlib.sha256(self.fixture['raw']).hexdigest(), len(self.fixture['raw']))
        font = (hashlib.sha256(self.fixture['font']).hexdigest(), len(self.fixture['font']))
        self.compare._check_membership(record, selector, source, font)
        for field, value in (('source_role', 'font'), ('font_role', 'menu'),
                             ('source_role', 'missing'), ('source_role', 'output')):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.compare._check_membership(record, dict(selector, **{field: value}), source, font)
        for source_id, font_id in (((source[0], source[1] + 1), font),
                                   (source, ('0' * 64, font[1]))):
            with self.assertRaises(ValueError):
                self.compare._check_membership(record, selector, source_id, font_id)
        output = record['build']['identity']['output']
        self.compare._check_membership(record, dict(selector, source_role='output'),
                                       (output['sha256'], output['size']), font)

    def test_ambiguous_registered_output_role_refused(self):
        record = self.native()['record']
        self.assertTrue(hasattr(self.compare, '_check_membership'), 'role validation not implemented')
        output = record['build']['identity']['output']
        # Negative control only: ambiguous record must never establish acceptance.
        record['build']['identity']['inputs'].append(dict(output, role='output'))
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.compare._check_membership(record, dict(self.selector(record, True), source_role='output'),
                                           (output['sha256'], output['size']), ('0' * 64, 1))

    def test_required_context_mismatches_block(self):
        first, second = self.native()['record'], self.native()['record']
        self.assertTrue(hasattr(self.compare, '_check_pair_context'), 'context validation not implemented')
        changes = (('run', 'core_sha256', '0' * 64), ('run', 'core_options', {'different': '1'}),
                   ('run', 'run_mode', 'imported_save_state'), ('image', 'width', 1),
                   ('image', 'height', 1))
        for section, key, value in changes:
            other = copy.deepcopy(second)
            other[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.compare._check_pair_context(first, other)
        with self.assertRaisesRegex(ValueError, 'same capture'):
            self.compare._check_pair_context(first, first)

    def test_frame_run_and_build_differences_are_explicit_not_state_equivalence(self):
        first = self.native()['record']
        different_build = self.register_build({'historical': True})
        second = self.native(frames=2, build_id=different_build['build_id'])['record']
        self.assertTrue(hasattr(self.compare, '_check_pair_context'), 'context validation not implemented')
        differences = self.compare._check_pair_context(first, second)
        self.assertIn('build_id', differences)
        self.assertIn('run.frame', differences)
        self.assertIn('run.run_id', differences)
        self.assertIn('run.steps', differences)


class NativeComparisonTests(NativeFixture):
    def preview(self):
        from romancer import menu
        from tests.menu_fixtures import digest_json
        # Passing geometry variant of the intentionally overflowing shared fixture.
        for entry in self.fixture['profile']['entries']:
            for cells in entry['states'].values():
                for cell in cells:
                    if cell['id'] == 'quantity':
                        cell['box']['width'] = 32
                    elif cell['id'] == 'fee':
                        cell['box']['x'] = 96
        self.fixture['cases']['profile_sha256'] = digest_json(self.fixture['profile'])
        result = menu.preview_menu(self.paths['source'], self.fixture['script_schema'],
                                   self.fixture['profile'], self.fixture['cases'],
                                   self.fixture['font_schema'], self.paths['font'])
        self.assertTrue(result['ok'], result)
        return result

    def request(self, first, second, relation='equal', region=None):
        self.assertTrue(hasattr(self.compare, 'compare_menu_captures'), 'public comparison not implemented')
        return {'schema_version': 1, 'expected_preview_id': self.preview()['preview_id'], 'pairs': [{
            'id': 'fee-region', 'case_id': 'selected', 'target': self.selector(first['record'], True),
            'reference': self.selector(second['record']), 'region': [0, 0, 16, 16] if region is None else region,
            'relation': relation, 'provenance': {'origin': 'synthetic_fixture',
                'note': 'Synthetic capture region association, not menu behavior', 'reference': None}}]}

    def run_comparison(self, request):
        before_db = self.database_bytes()
        history_path = self.project / '.romancer-history/history.sqlite3'
        before_history = history_path.read_bytes()
        before_source, before_font = self.paths['source'].read_bytes(), self.paths['font'].read_bytes()
        result = self.compare.compare_menu_captures(self.project, self.paths['source'],
            self.fixture['script_schema'], self.fixture['profile'], self.fixture['cases'],
            self.fixture['font_schema'], self.paths['font'], request)
        self.assertEqual(self.database_bytes(), before_db)
        self.assertEqual(history_path.read_bytes(), before_history)
        self.assertEqual(self.paths['source'].read_bytes(), before_source)
        self.assertEqual(self.paths['font'].read_bytes(), before_font)
        self.assertIs(result['written'], False)
        return result

    def test_public_actual_native_equality_never_proves_fee_or_menu_semantics(self):
        first, second = self.native(), self.native()
        request = self.request(first, second)
        before = copy.deepcopy(request)
        result = self.run_comparison(request)
        self.assertEqual(request, before)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['preview_status'], 'PASS')
        self.assertEqual(result['comparison_status'], 'PASS')
        self.assertEqual(result['transaction_status'], 'NOT_RUN')
        self.assertIs(result['actual_transaction_verified'], False)
        self.assertIs(result['native_render_verified'], False)
        self.assertIs(result['state_semantics_verified'], False)
        self.assertEqual(result['build_currentness'], 'NOT_CHECKED')
        pair = result['comparisons'][0]
        self.assertEqual(pair['scope'], 'captured_region_pixels')
        self.assertIs(pair['native_capture_verified'], True)
        self.assertEqual(pair['different_pixels'], 0)
        self.assertIsNone(pair['difference_bounds'])
        self.assertIs(pair['outside_region_compared'], False)
        coverage = {row['case_id']: row['comparison_status'] for row in result['case_coverage']}
        self.assertEqual(coverage, {'selected': 'PASS', 'unselected': 'NOT_RUN', 'empty': 'NOT_RUN'})
        self.assertEqual(result['capture_records'][first['record']['capture_id']]['record'], first['record'])
        self.assertNotIn('rgb_bytes', json.dumps(result))
        self.assertNotIn('png_bytes', json.dumps(result))
        self.assertEqual(len(result['comparison_id']), 64)
        self.assertEqual(self.run_comparison(request)['comparison_id'], result['comparison_id'])

    def test_actual_one_pixel_difference_and_excluded_roi(self):
        first, second = self.native(), self.native(buttons=['A'])
        request = self.request(first, second, relation='different')
        result = self.run_comparison(request)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['comparisons'][0]['different_pixels'], 1)
        self.assertEqual(result['comparisons'][0]['difference_bounds'], [8, 8, 9, 9])
        request['pairs'][0]['relation'] = 'equal'
        failed = self.run_comparison(request)
        self.assertEqual(failed['comparison_status'], 'FAIL')
        self.assertFalse(failed['ok'])
        self.assertTrue(failed['native_capture_verified'])
        request['pairs'][0]['region'] = [0, 0, 8, 16]
        excluded = self.run_comparison(request)
        self.assertTrue(excluded['ok'], excluded)
        self.assertEqual(excluded['comparisons'][0]['different_pixels'], 0)

    def test_imported_identical_copy_blocks_public_comparison(self):
        first, second = self.native(), self.native()
        imported = self.imported(second['png_bytes'], self.build['build_id'])
        result = self.run_comparison(self.request(first, imported))
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['comparison_status'], 'BLOCKED')
        self.assertFalse(result['native_capture_verified'])

    def test_public_stale_identity_roles_and_self_comparison_block(self):
        first, second = self.native(), self.native()
        valid = self.request(first, second)
        for field, value in (('expected_preview_id', '0' * 64), ('source_role', 'font'),
                             ('font_role', 'menu'), ('build_id', '0' * 64),
                             ('png_sha256', '0' * 64), ('rgb_sha256', '0' * 64),
                             ('case_id', 'unknown')):
            request = copy.deepcopy(valid)
            if field == 'expected_preview_id':
                request[field] = value
            elif field == 'case_id':
                request['pairs'][0][field] = value
            else:
                request['pairs'][0]['target'][field] = value
            with self.subTest(field=field):
                result = self.run_comparison(request)
                self.assertEqual(result['status'], 'BLOCKED', result)
        valid['pairs'][0]['reference'] = self.selector(first['record'])
        self.assertEqual(self.run_comparison(valid)['status'], 'BLOCKED')

    def test_empty_pairs_invalid_roi_and_request_budgets_stop_retrieval(self):
        first, second = self.native(), self.native()
        valid = self.request(first, second)
        invalid = []
        request = copy.deepcopy(valid)
        request['pairs'] = []
        invalid.append(request)
        request = copy.deepcopy(valid)
        request['pairs'][0]['region'] = [0, 0, 0, 1]
        invalid.append(request)
        request = copy.deepcopy(valid)
        request['pairs'] = [dict(request['pairs'][0], id=str(i)) for i in range(17)]
        invalid.append(request)
        request = copy.deepcopy(valid)
        request['pairs'][0]['provenance']['note'] = 'x' * (1024 * 1024)
        invalid.append(request)
        request = copy.deepcopy(valid)
        request['pairs'] = [dict(request['pairs'][0], id=str(i), region=[0, 0, 1024, 1024])
                            for i in range(2)]
        invalid.append(request)
        for request in invalid:
            with self.subTest(pairs=len(request['pairs'])), mock.patch.object(capture_store, 'get_capture') as get:
                result = self.run_comparison(request)
                self.assertEqual(result['status'], 'BLOCKED', result)
                get.assert_not_called()

    def test_no_annotations_or_supplied_pass_can_establish_native_semantics(self):
        first, second = self.native(), self.native()
        request = self.request(first, second)
        before = self.run_comparison(request)
        capture_ingest.add_annotations(self.project, first['record']['capture_id'], [{
            'kind': 'text', 'text': 'PASS fee deducted correctly', 'method': 'manual',
            'author': 'synthetic test', 'locator': None, 'region': None,
            'resource': None, 'supersedes': None}])
        after = self.run_comparison(request)
        self.assertEqual(after['comparison_id'], before['comparison_id'])
        self.assertFalse(after['actual_transaction_verified'])
        self.assertNotIn('fee deducted correctly', json.dumps(after))
        request['pairs'][0]['status'] = 'PASS'
        self.assertEqual(self.run_comparison(request)['status'], 'BLOCKED')

    def test_actual_option_mismatch_and_explicit_historical_build(self):
        first = self.native()
        second = self.native(options={'fixture_option': 'different'})
        self.assertEqual(self.run_comparison(self.request(first, second))['status'], 'BLOCKED')
        historical = self.register_build({'historical': True})
        reference = self.native(frames=2, build_id=historical['build_id'])
        result = self.run_comparison(self.request(first, reference))
        self.assertTrue(result['ok'], result)
        self.assertIn('build_id', result['comparisons'][0]['context_differences'])
        self.assertIn('run.frame', result['comparisons'][0]['context_differences'])
        self.assertEqual(result['capture_records'][reference['record']['capture_id']]['record'],
                         reference['record'])

    def test_cancellation_and_missing_decoder_never_return_success(self):
        first, second = self.native(), self.native()
        request = self.request(first, second)
        with mock.patch.object(self.compare, '_decode_capture_png', side_effect=KeyboardInterrupt):
            result = self.run_comparison(request)
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertTrue(result['cancelled'])
        self.assertFalse(result['ok'])
        with mock.patch.dict('sys.modules', {'PIL': None, 'PIL.Image': None}):
            result = self.run_comparison(request)
        self.assertEqual(result['status'], 'BLOCKED')

    def test_source_or_font_change_during_decode_blocks_final_return(self):
        first, second = self.native(), self.native()
        request = self.request(first, second)
        real_decode = self.compare._decode_capture_png
        for name in ('source', 'font'):
            original = self.paths[name].read_bytes()
            def changed(*args):
                pixels = real_decode(*args)
                self.paths[name].write_bytes(original + b'x')
                return pixels
            try:
                with self.subTest(name=name), mock.patch.object(self.compare, '_decode_capture_png', changed):
                    result = self.compare.compare_menu_captures(self.project, self.paths['source'],
                        self.fixture['script_schema'], self.fixture['profile'], self.fixture['cases'],
                        self.fixture['font_schema'], self.paths['font'], request)
                self.assertEqual(result['status'], 'BLOCKED', result)
                self.assertFalse(result['ok'])
                self.assertIsNone(result['comparison_id'])
            finally:
                self.paths[name].write_bytes(original)

    def test_nonpassing_preview_never_retrieves_captures(self):
        from tests.menu_fixtures import digest_json
        first, second = self.native(), self.native()
        request = self.request(first, second)
        self.fixture['profile']['entries'][0]['states']['selected'][2]['box']['width'] = 20
        self.fixture['cases']['profile_sha256'] = digest_json(self.fixture['profile'])
        with mock.patch.object(capture_store, 'get_capture') as get:
            result = self.run_comparison(request)
        self.assertEqual(result['status'], 'FAIL', result)
        self.assertEqual(result['preview_status'], 'FAIL')
        self.assertEqual(result['comparison_status'], 'NOT_RUN')
        self.assertFalse(result['native_capture_verified'])
        get.assert_not_called()

    def test_blocked_dominates_failed_relation_without_conflating_native_origin(self):
        first, second = self.native(), self.native()
        request = self.request(first, second, relation='different')
        additional = copy.deepcopy(request['pairs'][0])
        additional.update(id='bad-role', case_id='unselected')
        additional['target']['source_role'] = 'font'
        request['pairs'].append(additional)
        result = self.run_comparison(request)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual([row['status'] for row in result['comparisons']], ['FAIL', 'BLOCKED'])
        self.assertTrue(result['native_capture_verified'])
        self.assertFalse(result['ok'])

    def test_both_source_font_handles_live_through_actual_decode_then_close(self):
        first, second = self.native(), self.native()
        request = self.request(first, second)
        opening, decoding = Path.open, self.compare._decode_capture_png
        handles = {'source': [], 'font': []}
        def tracked(path, *args, **kwargs):
            stream = opening(path, *args, **kwargs)
            for key in handles:
                if path == self.paths[key] and args == ('rb',):
                    handles[key].append(stream)
            return stream
        def decode(*args):
            self.assertTrue(any(not stream.closed for stream in handles['source']))
            self.assertTrue(any(not stream.closed for stream in handles['font']))
            return decoding(*args)
        with mock.patch.object(Path, 'open', tracked), mock.patch.object(self.compare, '_decode_capture_png', decode):
            result = self.run_comparison(request)
        self.assertTrue(result['ok'], result)
        self.assertTrue(all(stream.closed for values in handles.values() for stream in values))

    def test_corrupt_stored_pixel_identity_cannot_pass_verified_png_bytes(self):
        first, second = self.native(), self.native()
        request = self.request(first, second)
        record = copy.deepcopy(second['record'])
        record['image']['rgb_sha256'] = '0' * 64
        record['run']['frame']['sha256'] = '0' * 64
        text = history.canonical_json(record)
        # Negative store corruption: keep metadata hashing valid to reach independent RGB decoding.
        with closing(sqlite3.connect(self.project / '.romancer-evidence/captures.sqlite3')) as connection:
            connection.execute('UPDATE captures SET record_json=?,record_sha256=? WHERE capture_id=?',
                (text, hashlib.sha256(text.encode()).hexdigest(), record['capture_id']))
            connection.commit()
        stored = capture_store.get_capture(self.project, record['capture_id'])
        self.assertEqual(stored['image_integrity'], 'PASS')
        request['pairs'][0]['reference'] = self.selector(record)
        result = self.run_comparison(request)
        self.assertEqual(result['status'], 'BLOCKED', result)
        self.assertFalse(result['native_capture_verified'])
        self.assertIn('RGB identity', result['comparisons'][0]['error']['message'])

    def test_actual_checkpoint_ancestry_retained_and_run_mode_mismatch_blocked(self):
        from romancer.runtime_client import RuntimeClient
        with RuntimeClient([sys.executable, '-m', 'romancer.runtime_worker']) as client:
            result = client.request('load', core=str(self.core), game=str(self.game),
                expected_core_sha256=hashlib.sha256(self.core.read_bytes()).hexdigest(),
                expected_game_sha256=hashlib.sha256(self.game.read_bytes()).hexdigest(),
                session_dir=str(self.root / 'checkpoint source'))
            self.assertTrue(result['ok'], result)
            state = client.request('save_state')
            self.assertTrue(state['ok'], state)
        path = self.root / 'state.json'
        path.write_text(json.dumps(state), encoding='utf-8')
        first, second = self.native(state=str(path)), self.native(state=str(path))
        result = self.run_comparison(self.request(first, second))
        self.assertTrue(result['ok'], result)
        for captured in result['capture_records'].values():
            run = captured['record']['run']
            self.assertEqual(run['run_mode'], 'imported_save_state')
            self.assertTrue(run['provenance']['state_derived'])
            self.assertEqual(run['provenance']['ancestor_state_sha256'], state['sha256'])
            self.assertEqual(run['dependency_coverage'], 'supplied_paths_only')
        cold = self.native()
        result = self.run_comparison(self.request(first, cold))
        self.assertEqual(result['status'], 'BLOCKED')

    def test_reporting_failure_never_presents_success(self):
        first, second = self.native(), self.native()
        request = self.request(first, second)
        with mock.patch.object(self.compare, 'MAX_REPORT', 1024):
            result = self.run_comparison(request)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertFalse(result['ok'])
        self.assertIsNone(result['comparison_id'])
        self.assertEqual(result['error']['phase'], 'response_encoding')
        self.assertEqual(result['comparisons'], [])

    def test_historical_reference_does_not_reopen_or_require_current_input_paths(self):
        old_source, old_font = self.root / 'historical menu.bin', self.root / 'historical font.bin'
        old_source.write_bytes(b'historical synthetic resource, not current preview')
        old_font.write_bytes(b'historical synthetic font, not current metrics')
        old_build = history.register_build(self.project, {
            'inputs': [{'role': 'menu', 'path': str(old_source)}, {'role': 'font', 'path': str(old_font)}],
            'output': str(self.game), 'adapter': {'name': 'generic', 'version': '1'},
            'profile': {'name': 'historical', 'version': '1'}, 'settings': {}}, self.root)
        historical = self.native(build_id=old_build['build_id'])
        old_source.unlink()
        old_font.unlink()
        current = self.native()
        result = self.run_comparison(self.request(current, historical))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['capture_records'][historical['record']['capture_id']]['record'],
                         historical['record'])
        self.assertEqual(result['build_currentness'], 'NOT_CHECKED')


if __name__ == '__main__':
    unittest.main()
if __name__ == '__main__':
    unittest.main()
