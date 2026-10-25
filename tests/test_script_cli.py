import hashlib
import io
import json
import os
from argparse import Namespace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from script_fixtures import fixed_fixture


class ScriptCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='script cli ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = Path(__file__).resolve().parents[1]
        self.raw, self.schema = fixed_fixture()
        (self.root / 'source file.bin').write_bytes(self.raw)
        self.schema_path = self.root / 'schema file.json'
        self.schema_path.write_text(json.dumps(self.schema), encoding='utf-8')
        self.edits_path = self.root / 'edits file.json'
        self.env = dict(os.environ)
        self.env['PYTHONPATH'] = str(self.app) + os.pathsep + self.env.get('PYTHONPATH', '')

    def cli(self, *args, ok=True, json_mode=True, wrapper=False):
        argv = [sys.executable, '-B', '-m', 'romancer']
        if wrapper:
            argv = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(self.app / 'run.ps1')]
        process = subprocess.run([*argv, *map(str, args), *(['--json'] if json_mode else [])],
                                 cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0 if ok else 1, (process.stderr + process.stdout)[-3000:])
        result = json.loads(process.stdout)
        self.assertIs(result['ok'], ok)
        self.assertEqual(result['scope'], 'structured_script')
        return result

    def inspect(self, **kwargs):
        return self.cli('script-inspect', self.schema_path.name, 'source file.bin', **kwargs)

    def edits(self, document, changes=None):
        value = {key: document[key] for key in ('document_id', 'source_sha256', 'schema_sha256')}
        value.update(schema_version=1, changes=changes if changes is not None else [
            {'record_id': 'a', 'segment': 0, 'text': 'BA'}])
        self.edits_path.write_text(json.dumps(value), encoding='utf-8')

    def test_full_caller_relative_workflow_and_protected_neighbors(self):
        document = self.inspect()
        self.assertEqual(document['source_sha256'], hashlib.sha256(self.raw).hexdigest())
        self.edits(document)
        plan = self.cli('script-plan', self.schema_path.name, 'source file.bin', self.edits_path.name)
        result = self.cli('script-apply', self.schema_path.name, 'source file.bin', self.edits_path.name,
                          '--expected-plan', plan['plan_id'], '--out', 'new output.bin')
        expected = self.raw[:8] + b'BA\xf0\x03B\x00' + b'\xff' * 6 + self.raw[20:]
        self.assertEqual((self.root / 'new output.bin').read_bytes(), expected)
        self.assertEqual((self.root / 'source file.bin').read_bytes(), self.raw)
        self.assertTrue(result['written'])
        self.assertEqual(result['publication_status'], 'PUBLISHED')

    def test_no_changes_produces_real_identical_output(self):
        self.edits(self.inspect(json_mode=False), [])
        plan = self.cli('script-plan', self.schema_path.name, 'source file.bin', self.edits_path.name,
                        json_mode=False)
        self.assertEqual(plan['status'], 'NO_CHANGES')
        result = self.cli('script-apply', self.schema_path.name, 'source file.bin', self.edits_path.name,
                          '--expected-plan', plan['plan_id'], '--out', 'same bytes.bin', json_mode=False)
        self.assertTrue(result['written'])
        self.assertEqual((self.root / 'same bytes.bin').read_bytes(), self.raw)

    def test_stale_plan_and_input_aliases_never_overwrite(self):
        self.edits(self.inspect())
        plan = self.cli('script-plan', self.schema_path.name, 'source file.bin', self.edits_path.name)
        result = self.cli('script-apply', self.schema_path.name, 'source file.bin', self.edits_path.name,
                          '--expected-plan', '0' * 64, '--out', 'stale.bin', ok=False)
        self.assertFalse(result['written'])
        self.assertFalse((self.root / 'stale.bin').exists())
        for output in (self.schema_path.name, self.edits_path.name, 'source file.bin'):
            path = self.root / output
            before = path.read_bytes()
            result = self.cli('script-apply', self.schema_path.name, 'source file.bin', self.edits_path.name,
                              '--expected-plan', plan['plan_id'], '--out', output, ok=False)
            self.assertFalse(result['written'])
            self.assertEqual(path.read_bytes(), before)

    def test_read_only_family_does_not_authorize_writing(self):
        self.schema['format']['family'] = 'unsupported-family'
        self.schema_path.write_text(json.dumps(self.schema), encoding='utf-8')
        document = self.inspect()
        self.assertEqual(document['status'], 'READ_ONLY')
        self.assertFalse(document['write_supported'])
        self.edits(document, [])
        self.cli('script-plan', self.schema_path.name, 'source file.bin', self.edits_path.name, ok=False)

    def test_capacity_unknown_glyph_and_malformed_schema_refuse(self):
        document = self.inspect()
        for text in ('C', 'A' * 30):
            self.edits(document, [{'record_id': 'a', 'segment': 0, 'text': text}])
            self.cli('script-plan', self.schema_path.name, 'source file.bin', self.edits_path.name, ok=False)
        for raw in ('{"schema_version":1,"schema_version":1}', '{"value":1e999}'):
            self.schema_path.write_text(raw, encoding='utf-8')
            self.inspect(ok=False)
        self.assertEqual((self.root / 'source file.bin').read_bytes(), self.raw)

    @unittest.skipUnless(os.name == 'nt', 'Windows wrapper')
    def test_windows_wrapper_preserves_caller_directory(self):
        document = self.inspect(wrapper=True)
        self.assertEqual(document['source_sha256'], hashlib.sha256(self.raw).hexdigest())

    def test_exact_emitted_budget_and_one_over(self):
        from romancer.script_cli import encode_result
        limit = 8192
        overhead = len(encode_result({'text': ''}))
        result = {'text': 'x' * (limit - overhead)}
        self.assertEqual(len(encode_result(result, limit=limit)), limit)
        result['text'] += 'x'
        with self.assertRaises(ValueError):
            encode_result(result, limit=limit)

    def test_report_failure_preserves_actual_publication_outcome(self):
        from romancer.cli import main
        from romancer.script_patch import apply_script
        self.edits(self.inspect())
        plan = self.cli('script-plan', self.schema_path.name, 'source file.bin', self.edits_path.name)
        destination = self.root / 'published.bin'

        def oversized(*args, **kwargs):
            result = apply_script(*args, **kwargs)
            self.assertTrue(result['written'])
            result['oversized_diagnostic'] = 'x' * (8 * 1024 * 1024)
            return result

        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding='utf-8')
        with patch('romancer.script_patch.apply_script', side_effect=oversized), patch('sys.stdout', stream):
            status = main(['script-apply', str(self.schema_path), str(self.root / 'source file.bin'),
                           str(self.edits_path), '--expected-plan', plan['plan_id'], '--out', str(destination)])
        stream.flush()
        result = json.loads(buffer.getvalue())
        stream.detach()
        self.assertEqual(status, 1)
        self.assertFalse(result['ok'])
        self.assertTrue(result['written'])
        self.assertEqual(result['publication_status'], 'PUBLISHED')
        self.assertEqual(result['out_sha256'], hashlib.sha256(destination.read_bytes()).hexdigest())

    def test_loader_cancellation_returns_130_without_writing(self):
        from romancer.cli import main
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding='utf-8')
        with patch('romancer.script_cli.load_script_json', side_effect=KeyboardInterrupt), patch('sys.stdout', stream):
            status = main(['script-inspect', str(self.schema_path), str(self.root / 'source file.bin')])
        stream.flush()
        result = json.loads(buffer.getvalue())
        stream.detach()
        self.assertEqual(status, 130)
        self.assertTrue(result['cancelled'])
        self.assertFalse(result['written'])

    def test_cancelled_service_result_stays_cancelled_after_report_failure(self):
        from romancer.cli import main
        self.edits(self.inspect(), [])
        for written, publication in ((True, 'PUBLISHED'), (None, 'UNKNOWN')):
            for mode in ([], ['--json']):
                result = {'ok': False, 'scope': 'structured_script', 'cancelled': True,
                          'written': written, 'publication_status': publication,
                          'write_supported': True, 'warnings': ['cleanup interrupted'],
                          'oversized': 'x' * (8 * 1024 * 1024)}
                buffer = io.BytesIO()
                stream = io.TextIOWrapper(buffer, encoding='utf-8')
                with self.subTest(written=written, mode=mode), patch(
                        'romancer.script_patch.apply_script', return_value=result), patch('sys.stdout', stream):
                    status = main(['script-apply', str(self.schema_path), str(self.root / 'source file.bin'),
                                   str(self.edits_path), '--expected-plan', '0' * 64,
                                   '--out', str(self.root / 'unused.bin'), *mode])
                stream.flush()
                failure = json.loads(buffer.getvalue())
                stream.detach()
                self.assertEqual(status, 130)
                self.assertTrue(failure['cancelled'])
                self.assertIs(failure['written'], written)
                self.assertEqual(failure['publication_status'], publication)
                self.assertTrue(failure['write_supported'])
                self.assertEqual(failure['warnings'], ['cleanup interrupted'])
                self.assertEqual(failure['phase'], 'response_encoding')

    def test_input_failures_identify_loader_and_conservative_capability(self):
        from romancer.script_cli import dispatch
        args = Namespace(cmd='script-plan', schema=self.schema_path, edits=self.edits_path,
                         source=self.root / 'source file.bin')
        self.edits(self.inspect(), [])
        valid_schema = self.schema_path.read_bytes()
        for phase in ('schema_load', 'edits_load'):
            self.schema_path.write_bytes(b'[]' if phase == 'schema_load' else valid_schema)
            self.edits_path.write_bytes(b'[]')
            result = dispatch(args)
            self.assertEqual(result['phase'], phase)
            self.assertFalse(result['write_supported'])
            self.assertEqual(result['warnings'], [])
            self.assertFalse(result['written'])
            self.assertFalse(result['ok'])


if __name__ == '__main__':
    unittest.main()
