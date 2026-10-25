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

from tests.menu_fixtures import menu_fixture, digest_json, write_menu_fixture
from tests import test_menu_compare as capture_tests


class MenuCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='menu cli ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = Path(__file__).resolve().parents[1]
        self.env = dict(os.environ)
        self.env['PYTHONPATH'] = str(self.app) + os.pathsep + self.env.get('PYTHONPATH', '')
        self.fixture = menu_fixture()
        for entry in self.fixture['profile']['entries']:
            for cells in entry['states'].values():
                for cell in cells:
                    if cell['id'] == 'quantity':
                        cell['box']['width'] = 32
                    if cell['id'] == 'fee':
                        cell['box']['x'] = 96
        self.fixture['cases']['profile_sha256'] = digest_json(self.fixture['profile'])
        self.paths = write_menu_fixture(self.root / 'input files', self.fixture)

    def path(self, name):
        return str(self.paths[name].relative_to(self.root))

    def save(self, name):
        self.paths[name].write_text(json.dumps(self.fixture[name]), encoding='utf-8')

    def cli(self, *args, ok=True, json_mode=True):
        process = subprocess.run([sys.executable, '-B', '-m', 'romancer', *args,
                                  *(['--json'] if json_mode else [])],
                                 cwd=self.root, env=self.env, capture_output=True,
                                 text=True, timeout=30)
        self.assertEqual(process.returncode, 0 if ok else 1,
                         (process.stderr + process.stdout)[-3000:])
        if not json_mode:
            return process.stdout
        result = json.loads(process.stdout)
        self.assertIs(result['ok'], ok)
        return result

    def inspect(self, **kwargs):
        return self.cli('menu-inspect', self.path('script_schema'), self.path('source'),
                        self.path('profile'), **kwargs)

    def preview(self, **kwargs):
        return self.cli('menu-preview', self.path('script_schema'), self.path('source'),
                        self.path('profile'), self.path('cases'), self.path('font_schema'),
                        self.path('font'), **kwargs)

    def test_caller_relative_inspection_and_preview_are_not_runtime_proof(self):
        inspected = self.inspect()
        self.assertEqual(inspected['source_sha256'], hashlib.sha256(self.fixture['raw']).hexdigest())
        self.assertEqual(inspected['status'], 'INSPECTED')
        preview = self.preview()
        self.assertFalse(preview['written'])
        self.assertFalse(preview['native_render_verified'])
        self.assertFalse(preview['actual_transaction_verified'])
        self.assertEqual(preview['transaction_status'], 'NOT_RUN')
        self.assertEqual(preview['comparison_status'], 'NOT_RUN')
        self.assertEqual(self.paths['source'].read_bytes(), self.fixture['raw'])
        self.assertEqual(self.paths['font'].read_bytes(), self.fixture['font'])

    def test_maximum_width_failure_does_not_disguise_current_value_fit(self):
        for entry in self.fixture['profile']['entries']:
            for cells in entry['states'].values():
                for cell in cells:
                    if cell['id'] == 'quantity':
                        cell['box']['width'] = 20
        self.fixture['cases']['profile_sha256'] = digest_json(self.fixture['profile'])
        self.save('profile')
        self.save('cases')
        preview = self.preview(ok=False)
        self.assertEqual(preview['status'], 'FAIL')
        self.assertFalse(preview['actual_transaction_verified'])

    def test_malformed_input_returns_bounded_phase_error(self):
        self.paths['profile'].write_text('{"x":1,"x":2}')
        result = self.inspect(ok=False)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['error']['phase'], 'menu_profile_load')
        self.assertFalse(result['written'])

    def test_comparison_request_load_is_caller_relative_and_read_only(self):
        request = self.root / 'comparison request.json'
        request.write_text('{"x":1,"x":2}')
        result = self.cli('menu-compare', 'missing project', self.path('script_schema'),
                          self.path('source'), self.path('profile'), self.path('cases'),
                          self.path('font_schema'), self.path('font'), request.name, ok=False)
        self.assertEqual(result['error']['phase'], 'comparison_request_load')
        self.assertFalse(result['written'])
        self.assertFalse((self.root / 'missing project').exists())

    def test_human_summary_separates_declared_preview_pixels_and_transaction(self):
        summary = self.preview(json_mode=False)
        self.assertIn('Declared preview: PASS', summary)
        self.assertIn('Captured pixels: NOT_RUN', summary)
        self.assertIn('Actual transaction: NOT_RUN', summary)

    def test_load_cancellation_and_broken_stdout_keep_exit_130(self):
        from romancer.cli import main
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding='utf-8')
        argv = ['menu-inspect', str(self.paths['script_schema']),
                str(self.paths['source']), str(self.paths['profile']), '--json']
        with patch('romancer.menu_cli.load_script_json', side_effect=KeyboardInterrupt), \
                patch('sys.stdout', stream):
            self.assertEqual(main(argv), 130)
        self.assertEqual(json.loads(buffer.getvalue())['status'], 'CANCELLED')

        def broken(result, json_mode):
            self.assertEqual(result['status'], 'CANCELLED')
            raise BrokenPipeError('closed consumer')

        with patch('romancer.menu_cli.load_script_json', side_effect=KeyboardInterrupt), \
                patch('romancer.cli.emit_menu', side_effect=broken):
            self.assertEqual(main(argv), 130)

    def test_name_edit_keeps_numeric_neighbors_and_font_identity(self):
        before = self.preview()
        document = self.cli('script-inspect', self.path('script_schema'), self.path('source'))
        edits = {key: document[key] for key in ('document_id', 'source_sha256', 'schema_sha256')}
        edits.update(schema_version=1, changes=[{'record_id': 'a', 'segment': 0, 'text': 'A'}])
        edit_path = self.root / 'reviewed edits.json'
        edit_path.write_text(json.dumps(edits), encoding='utf-8')
        plan = self.cli('script-plan', self.path('script_schema'), self.path('source'), edit_path.name)
        applied = self.cli('script-apply', self.path('script_schema'), self.path('source'),
                           edit_path.name, '--expected-plan', plan['plan_id'], '--out', 'new menu.bin')
        self.assertTrue(applied['written'])
        expected = self.fixture['raw'][:8] + b'A\x00' + b'\xff' * 6 + self.fixture['raw'][16:]
        self.assertEqual((self.root / 'new menu.bin').read_bytes(), expected)
        self.assertEqual(self.paths['source'].read_bytes(), self.fixture['raw'])
        self.paths['source'] = self.root / 'new menu.bin'
        self.preview(ok=False)
        self.fixture['script_schema']['profile']['accepted_sha256'] = [hashlib.sha256(expected).hexdigest()]
        for rule in self.fixture['script_schema']['profile']['rules']:
            if rule['resource'] == 'a-slot':
                rule['expected_hex'] = expected[8:16].hex()
        self.fixture['profile']['script_schema_sha256'] = digest_json(self.fixture['script_schema'])
        self.fixture['cases']['profile_sha256'] = digest_json(self.fixture['profile'])
        for key in ('script_schema', 'profile', 'cases'):
            self.save(key)
        after = self.preview()
        self.assertEqual(before['metrics_id'], after['metrics_id'])
        self.assertEqual(before['font_schema_sha256'], after['font_schema_sha256'])
        self.assertNotEqual(before['preview_id'], after['preview_id'])
        self.assertEqual(self.paths['font'].read_bytes(), self.fixture['font'])


class NativeMenuCliTests(capture_tests.NativeFixture):
    def test_real_capture_to_cli_pixel_comparison(self):
        for entry in self.fixture['profile']['entries']:
            for cells in entry['states'].values():
                for cell in cells:
                    if cell['id'] == 'quantity':
                        cell['box']['width'] = 32
                    if cell['id'] == 'fee':
                        cell['box']['x'] = 96
        self.fixture['cases']['profile_sha256'] = digest_json(self.fixture['profile'])
        self.paths = write_menu_fixture(self.root / 'input files', self.fixture)
        first, second = self.native(), self.native()
        self.app = Path(__file__).resolve().parents[1]
        self.env = dict(os.environ)
        self.env['PYTHONPATH'] = str(self.app) + os.pathsep + self.env.get('PYTHONPATH', '')
        args = [str(self.paths[key].relative_to(self.root)) for key in
                ('script_schema', 'source', 'profile', 'cases', 'font_schema', 'font')]
        preview = MenuCliTests.cli(self, 'menu-preview', *args)
        request = {'schema_version': 1, 'expected_preview_id': preview['preview_id'],
                   'pairs': [{'id': 'same', 'case_id': 'selected',
                              'target': self.selector(first['record'], target=True),
                              'reference': self.selector(second['record']),
                              'region': [0, 0, 16, 16], 'relation': 'equal',
                              'provenance': {'origin': 'synthetic_fixture',
                                             'note': 'Actual synthetic worker pixels', 'reference': None}}]}
        (self.root / 'comparison request.json').write_text(json.dumps(request), encoding='utf-8')
        database_before = self.database_bytes()
        result = MenuCliTests.cli(self, 'menu-compare', str(self.project.relative_to(self.root)),
                                 *args, 'comparison request.json')
        self.assertEqual(result['comparison_status'], 'PASS')
        self.assertEqual(result['comparisons'][0]['different_pixels'], 0)
        self.assertEqual(result['comparisons'][0]['total_pixels'], 256)
        self.assertFalse(result['actual_transaction_verified'])
        self.assertFalse(result['native_render_verified'])
        self.assertEqual(result['transaction_status'], 'NOT_RUN')
        self.assertEqual(self.database_bytes(), database_before)
        self.assertEqual(self.paths['source'].read_bytes(), self.fixture['raw'])


if __name__ == '__main__':
    unittest.main()
