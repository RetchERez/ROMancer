import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import ModuleType

from romancer.libretro_frontend import write_rgb_png


class CaptureCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='capture cli ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project with spaces'
        self.project.mkdir()
        self.png = self.root / 'native looking fixture.png'
        write_rgb_png(self.png, 2, 2, bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255]))
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps({
            'build_id': None, 'annotations': [],
            'declared_context': {'captured_utc': None, 'game_sha256': None, 'core_sha256': None,
                                 'run_mode': None, 'state_derived': None, 'source_note': None},
        }), encoding='utf-8')

    def cli(self, *args, ok=True):
        process = subprocess.run([sys.executable, '-B', '-m', 'romancer', *map(str, args), '--json'],
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0 if ok else 1, process.stderr + process.stdout)
        result = json.loads(process.stdout)
        self.assertIs(result['ok'], ok)
        return result

    def initialize(self):
        self.cli('capture-init', self.project)

    def import_image(self):
        self.initialize()
        return self.cli('capture-import', self.project, self.png, self.manifest)['capture_id']

    @staticmethod
    def annotation(text, supersedes=None):
        return {'kind': 'text', 'text': text, 'method': 'manual', 'author': 'Synthetic tester',
                'locator': None, 'region': None, 'resource': None, 'supersedes': supersedes}

    def test_empty_store_is_searchable_without_claiming_game_coverage(self):
        self.initialize()
        result = self.cli('capture-search', self.project, '--text', 'unknown dialogue')
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['scope'], 'capture_search')
        self.assertNotIn('CERTIFIED', json.dumps(result))

    @unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('gcc'),
                         'actual native CLI capture requires Linux and GCC')
    def test_documented_native_configuration_runs_and_persists_real_frame(self):
        from romancer import history
        application = Path(__file__).resolve().parents[1]
        core = self.root / 'mock.so'
        subprocess.run(['gcc', '-shared', '-fPIC', '-O2', '-DROMANCER_V35_TEST',
                        str(application / 'tests' / 'mock_libretro.c'), '-o', str(core)],
                       check=True, capture_output=True, timeout=20)
        game = self.root / 'game.bin'
        game.write_bytes(b'synthetic CLI game fixture')
        original = self.root / 'original.bin'
        original.write_bytes(b'synthetic CLI original fixture')
        history.init_history(self.project)
        build = history.register_build(self.project, {
            'inputs': [{'role': 'original', 'path': str(original)}], 'output': str(game),
            'adapter': {'name': 'generic', 'version': '1'},
            'profile': {'name': 'synthetic', 'version': '1'}, 'settings': {},
        }, self.root)
        self.initialize()
        readme=application/'README.txt'
        if not readme.exists():readme=application.parent/'README.txt'
        text=readme.read_text(encoding='utf-8')
        config=json.loads(text.split('BEGIN CAPTURE JSON',1)[1].split('END CAPTURE JSON',1)[0])
        config['load'].update(core=core.name, game=game.name,
                              expected_core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                              expected_game_sha256=hashlib.sha256(game.read_bytes()).hexdigest())
        path = self.root / 'native-config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        captured = self.cli('capture-run', self.project, build['build_id'], path)
        shown = self.cli('capture-show', self.project, captured['capture_id'])
        self.assertEqual(shown['record']['origin'], 'native_worker')
        self.assertEqual(shown['record']['run']['frame']['index'], 60)
        self.assertFalse(shown['record']['natural_progress_verified'])
        self.assertEqual(shown['image_integrity'], 'PASS')
        self.assertEqual(original.read_bytes(), b'synthetic CLI original fixture')

    def test_import_search_show_and_no_clobber_export(self):
        capture_id = self.import_image()
        self.png.unlink()
        result = self.cli('capture-search', self.project, '--origin', 'imported_image')
        self.assertEqual([row['capture_id'] for row in result['matches']], [capture_id])
        row = result['matches'][0]
        self.assertFalse(row['natural_progress_verified'])
        self.assertEqual(row['image_integrity'], 'NOT_CHECKED')
        shown = self.cli('capture-show', self.project, capture_id)
        self.assertEqual(shown['image_integrity'], 'PASS')
        self.assertNotIn('png_bytes', shown)
        output = self.root / 'exported screenshot.png'
        self.cli('capture-show', self.project, capture_id, '--image-out', output)
        before = output.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), shown['record']['image']['blob_sha256'])
        self.cli('capture-show', self.project, capture_id, '--image-out', output, ok=False)
        self.assertEqual(output.read_bytes(), before)

    def test_annotations_supersede_without_rewriting_history(self):
        capture_id = self.import_image()
        annotations = self.root / 'annotations.json'
        annotations.write_text(json.dumps([self.annotation('The gate opens.')]), encoding='utf-8')
        original = self.cli('capture-annotate', self.project, capture_id, annotations)['annotation_ids'][0]
        self.assertEqual(len(self.cli('capture-search', self.project, '--text', 'GATE')['matches']), 1)
        annotations.write_text(json.dumps([self.annotation('The door opens.', original)]), encoding='utf-8')
        self.cli('capture-annotate', self.project, capture_id, annotations)
        self.assertEqual(self.cli('capture-search', self.project, '--text', 'gate')['matches'], [])
        self.assertEqual(len(self.cli('capture-search', self.project, '--text', 'gate', '--include-superseded')['matches']), 1)
        self.assertEqual(len(self.cli('capture-search', self.project, '--text', 'door')['matches']), 1)

    def test_cli_retains_exact_original_manifest_provenance(self):
        self.initialize()
        first = self.cli('capture-import', self.project, self.png, self.manifest)['capture_id']
        before = self.manifest.read_bytes()
        parsed = json.loads(before)
        self.manifest.write_text(json.dumps(parsed, indent=2, sort_keys=True), encoding='utf-8')
        second = self.cli('capture-import', self.project, self.png, self.manifest)['capture_id']
        for capture_id, raw in [(first, before), (second, self.manifest.read_bytes())]:
            source = self.cli('capture-show', self.project, capture_id)['record']['import_source']
            self.assertEqual(source['manifest_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(source['manifest_kind'], 'original_file')

    def test_malformed_and_oversized_configs_fail_before_runtime_launch(self):
        for raw in [b'{"load":{},"load":{}}', b'{"timeout":1e999}', b'x' * (1024 * 1024 + 1)]:
            self.manifest.write_bytes(raw)
            result = self.cli('capture-run', self.project, '0' * 64, self.manifest, ok=False)
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertFalse(result['written'])
        self.assertFalse((self.project / '.romancer-evidence').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows path spellings')
    def test_windows_ambiguous_inputs_rejected_before_open(self):
        from romancer.capture_cli import load_document
        for name in [str(self.manifest) + '.', str(self.manifest) + ' ',
                     '\\\\?\\' + str(self.manifest), '\\\\.\\' + str(self.manifest)]:
            with self.subTest(name=name), patch.object(Path, 'open') as opened:
                with self.assertRaises(ValueError):
                    load_document(Path(name))
                opened.assert_not_called()
        self.assertEqual(load_document(self.manifest)['annotations'], [])

    def test_emitted_response_budget_includes_indentation_and_envelope(self):
        from romancer.cli import main
        payload = {'ok': True, 'matches': [{'nested': ['x'] * 100000}]}
        self.assertLess(len(json.dumps(payload).encode()), 1024 * 1024)
        self.assertGreater(len(json.dumps(payload, indent=2).encode()), 1024 * 1024)
        module = ModuleType('romancer.capture_store')
        module.search_captures = Mock(return_value=payload)
        for mode in ([], ['--json']):
            with self.subTest(mode=mode), patch.dict(sys.modules, {'romancer.capture_store': module}):
                output = io.BytesIO()
                stream = io.TextIOWrapper(output, encoding='utf-8')
                with patch('sys.stdout', stream):
                    status = main(['capture-search', str(self.project), *mode])
                stream.flush()
                raw = output.getvalue()
                stream.detach()
                self.assertEqual(status, 1)
                self.assertLessEqual(len(raw), 1024 * 1024)
                self.assertFalse(json.loads(raw)['ok'])

    def test_exact_output_limit_and_one_over(self):
        from romancer.capture_cli import encode_result, JSON_LIMIT
        overhead = len(encode_result({'ok': True, 'text': ''}))
        result = {'ok': True, 'text': 'x' * (JSON_LIMIT - overhead)}
        self.assertEqual(len(encode_result(result)), JSON_LIMIT)
        result['text'] += 'x'
        with self.assertRaises(ValueError):
            encode_result(result)

    def test_export_sizing_and_post_publication_accounting(self):
        from romancer.cli import main
        module = ModuleType('romancer.capture_store')
        destination = self.root / 'new-export.png'
        for case in ('before', 'after'):
            with self.subTest(case=case), patch.dict(sys.modules, {'romancer.capture_store': module}):
                module.get_capture = Mock(return_value={
                    'ok': True, 'record': {'text': 'x' * (1024 * 1024) if case == 'before' else 'small'},
                    'png_bytes': b''})

                def export(*_):
                    destination.write_bytes(b'published synthetic capture')
                    return {'ok': True, 'note': 'x' * (1024 * 1024)}

                module.export_capture = Mock(side_effect=export)
                output = io.BytesIO()
                stream = io.TextIOWrapper(output, encoding='utf-8')
                with patch('sys.stdout', stream):
                    status = main(['capture-show', str(self.project), '0' * 32,
                                   '--image-out', str(destination), '--json'])
                stream.flush()
                result = json.loads(output.getvalue())
                stream.detach()
                self.assertEqual(status, 1)
                self.assertEqual(result['written'], case == 'after')
                if case == 'before':
                    module.export_capture.assert_not_called()
                    self.assertFalse(destination.exists())
                else:
                    self.assertEqual(result['export_path'], str(destination))
                    self.assertEqual(destination.read_bytes(), b'published synthetic capture')


if __name__ == '__main__':
    unittest.main()
