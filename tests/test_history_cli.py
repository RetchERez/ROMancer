import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class HistoryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer history CLI ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_dir = self.root / 'config folder'
        self.config_dir.mkdir()
        (self.config_dir / 'original.bin').write_bytes(b'original')
        self.output = self.config_dir / 'output.bin'
        self.output.write_bytes(b'translated')
        self.config = self.config_dir / 'build.json'
        self.data = {'inputs': [{'role': 'original', 'path': 'original.bin'}],
                     'output': 'output.bin', 'adapter': {'name': 'generic', 'version': '1'},
                     'profile': {'name': 'fixture', 'version': '1'}, 'settings': {}}
        self.config.write_text(json.dumps(self.data), encoding='utf-8')

    def cli(self, command, *args):
        result = subprocess.run([sys.executable, '-m', 'romancer', command, str(self.root),
                                 *map(str, args), '--json'], capture_output=True, text=True, timeout=30)
        self.assertTrue(result.stdout, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def initialize_and_register(self):
        code, initialized = self.cli('history-init')
        self.assertEqual(code, 0, initialized)
        code, registered = self.cli('build-register', self.config)
        self.assertEqual(code, 0, registered)
        return registered['build_id']

    def test_config_relative_paths_and_stale_evidence(self):
        build_id = self.initialize_and_register()
        code, checked = self.cli('build-check', build_id)
        self.assertEqual(code, 0, checked)
        self.assertEqual(checked['status'], 'PASS')
        code, result = self.cli('build-status', build_id, '--evidence', checked['evidence_id'])
        self.assertEqual(code, 0, result)
        self.output.write_bytes(b'changed')
        code, stale = self.cli('build-status', build_id, '--evidence', checked['evidence_id'])
        self.assertNotEqual(code, 0)
        self.assertFalse(stale['ok'])

    def test_empty_and_cross_build_evidence_do_not_pass(self):
        first = self.initialize_and_register()
        code, check = self.cli('build-check', first)
        self.assertEqual(code, 0, check)
        self.data['settings'] = {'layout': 'changed'}
        self.config.write_text(json.dumps(self.data), encoding='utf-8')
        code, second = self.cli('build-register', self.config)
        self.assertEqual(code, 0, second)
        self.assertNotEqual(first, second['build_id'])
        for options in [[], ['--evidence', check['evidence_id']]]:
            code, result = self.cli('build-status', second['build_id'], *options)
            self.assertNotEqual(code, 0, result)
            self.assertFalse(result['ok'])

    def test_malformed_config_returns_json_without_store_mutation(self):
        for content in ['{"output":"a","output":"b"}', '{"settings":NaN}',
                        '{"settings":{"nested":[1e999]}}',
                        '{"settings":{"nested":[-1e999]}}', '[]', '{']:
            with self.subTest(content=content):
                self.config.write_text(content, encoding='utf-8')
                code, result = self.cli('build-register', self.config)
                self.assertEqual(code, 1, result)
                self.assertFalse(result['ok'])
                self.assertFalse((self.root / '.romancer-history').exists())

    def test_loader_rejects_overflow_but_accepts_finite_floats(self):
        from romancer.history_cli import load_config
        for number in ('1e999', '-1e999'):
            self.config.write_text('{"nested":[' + number + ']}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                load_config(self.config)
        self.config.write_text('{"nested":[1.25e2]}', encoding='utf-8')
        self.assertEqual(load_config(self.config), {'nested': [125.0]})

    def test_missing_store_returns_structured_error(self):
        code, result = self.cli('build-check', 'a' * 64)
        self.assertEqual(code, 1, result)
        self.assertFalse(result['ok'])

    def test_config_size_limit_is_enforced_before_decoding(self):
        self.config.write_bytes(b' ' * (8 * 1024 * 1024 + 1))
        code, result = self.cli('build-register', self.config)
        self.assertEqual(code, 1, result)
        self.assertIn('8 MiB', result['error'])


if __name__ == '__main__':
    unittest.main()
