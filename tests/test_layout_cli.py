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

from tests.layout_fixtures import layout_fixture


class LayoutCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='layout cli ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = Path(__file__).resolve().parents[1]
        self.env = dict(os.environ)
        self.env['PYTHONPATH'] = str(self.app) + os.pathsep + self.env.get('PYTHONPATH', '')
        self.fixture([b'SORRY FOR', b'THE WAIT!'], 102)

    def fixture(self, lines, width, **kwargs):
        self.raw, self.font, self.schema, self.font_schema, self.policy = layout_fixture(
            lines, width, **kwargs)
        (self.root / 'source file.bin').write_bytes(self.raw)
        (self.root / 'font file.bin').write_bytes(self.font)
        self.save('script schema.json', self.schema)
        self.save('font schema.json', self.font_schema)
        self.save('layout policy.json', self.policy)

    def save(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding='utf-8')

    def cli(self, *args, ok=True, json_mode=True):
        process = subprocess.run([sys.executable, '-B', '-m', 'romancer', *args,
                                  *(['--json'] if json_mode else [])],
                                 cwd=self.root, env=self.env, capture_output=True,
                                 text=True, timeout=30)
        self.assertEqual(process.returncode, 0 if ok else 1,
                         (process.stderr + process.stdout)[-3000:])
        result = json.loads(process.stdout)
        self.assertIs(result['ok'], ok)
        return result

    def check(self, **kwargs):
        return self.cli('layout-check', 'script schema.json', 'source file.bin',
                        'font schema.json', 'font file.bin', 'layout policy.json', **kwargs)

    def plan(self, checked=None, **kwargs):
        checked = checked or self.check()
        self.save('request file.json', {'schema_version': 1,
                  'analysis_id': checked['analysis_id'], 'editorial_replacements': []})
        return self.cli('layout-plan', 'script schema.json', 'source file.bin',
                        'font schema.json', 'font file.bin', 'layout policy.json',
                        'request file.json', **kwargs)

    def test_font_measure_uses_native_bytes_and_distinguishes_advance(self):
        measured = self.cli('font-measure', 'font schema.json', 'font file.bin')
        self.assertEqual(measured['scope'], 'native_font_metrics')
        self.assertEqual(measured['source_sha256'], hashlib.sha256(self.font).hexdigest())
        glyph = next(row for row in measured['glyphs'] if row['id'] == 'g65')
        self.assertEqual(glyph['ink_bounds'], [0, 0, 5, 5])
        self.assertEqual(glyph['ink_pixels'], 14)
        self.assertEqual(glyph['advance_pixels'], 6)
        self.assertEqual(glyph['advance_origin'], 'measured_u8')
        self.assertFalse(measured['native_render_verified'])

    def test_service_cancellation_keeps_cli_exit_130(self):
        from romancer.cli import main
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding='utf-8')
        with patch('romancer.font_metrics._hash_stream', side_effect=KeyboardInterrupt), \
                patch('sys.stdout', stream):
            status = main(['font-measure', str(self.root / 'font schema.json'),
                           str(self.root / 'font file.bin'), '--json'])
        self.assertEqual(status, 130)
        self.assertEqual(json.loads(buffer.getvalue())['status'], 'CANCELLED')

    def test_malformed_font_json_and_unsupported_codec_are_structured_failures(self):
        self.font_schema['codec'] = 'unknown-codec'
        self.save('font schema.json', self.font_schema)
        result = self.cli('font-measure', 'font schema.json', 'font file.bin', ok=False)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertFalse(result['native_render_verified'])
        (self.root / 'font schema.json').write_text('{"x":1,"x":2}')
        result = self.cli('font-measure', 'font schema.json', 'font file.bin', ok=False)
        self.assertEqual(result['error']['phase'], 'font_schema_load')
        self.assertEqual((self.root / 'font file.bin').read_bytes(), self.font)

    def test_reflow_proposal_applies_through_existing_writer_with_exact_bytes(self):
        checked = self.check()
        self.assertEqual(checked['analysis']['records'][0]['pages'][0]['used_line_count'], 2)
        proposal = self.plan(checked)
        page = proposal['candidate']['records'][0]['pages'][0]
        self.assertEqual([line['text'] for line in page['lines']], ['SORRY FOR THE WAIT!', ''])
        self.assertEqual([line['advance_px'] for line in page['lines']], [102, 0])
        self.assertEqual(page['reserved_height_px'], 10)
        self.save('reviewed edits.json', proposal['script_edits'])
        planned = self.cli('script-plan', 'script schema.json', 'source file.bin', 'reviewed edits.json')
        self.assertEqual(planned['plan_id'], proposal['script_plan_id'])
        applied = self.cli('script-apply', 'script schema.json', 'source file.bin',
                           'reviewed edits.json', '--expected-plan', planned['plan_id'],
                           '--out', 'new output.bin')
        self.assertTrue(applied['written'])
        slot = b'SORRY FOR THE WAIT!\xe1\x00' + b'\xff' * 7
        self.assertEqual((self.root / 'new output.bin').read_bytes(),
                         self.raw[:8] + slot + self.raw[8 + len(slot):])
        self.assertEqual((self.root / 'source file.bin').read_bytes(), self.raw)
        self.assertEqual((self.root / 'font file.bin').read_bytes(), self.font)

    def test_three_lines_collapse_without_removing_controls(self):
        self.fixture([b'ARE THERE', b'ORKS UP', b'AHEAD?'], 129)
        proposal = self.plan()
        page = proposal['candidate']['records'][0]['pages'][0]
        self.assertEqual([line['text'] for line in page['lines']],
                         ['ARE THERE ORKS UP AHEAD?', '', ''])
        self.assertEqual(page['reserved_height_px'], 15)

    def test_left_fill_is_not_balanced_and_default_output_is_json(self):
        self.fixture([b'AA A A', b'A A A'], 40)
        proposal = self.plan(json_mode=False)
        lines = proposal['candidate']['records'][0]['pages'][0]['lines']
        self.assertEqual([line['text'] for line in lines], ['AA A A A', 'A A'])
        self.assertEqual([line['advance_px'] for line in lines], [39, 15])

    def test_existing_empty_suffix_is_no_changes(self):
        self.fixture([b'SORRY FOR THE WAIT!', b''], 102)
        proposal = self.plan()
        self.assertEqual(proposal['status'], 'NO_CHANGES')
        self.assertEqual(proposal['script_edits']['changes'], [])

    def test_stale_font_and_malformed_policy_refuse_without_writes(self):
        checked = self.check()
        before = set(self.root.iterdir())
        changed_font = bytes([self.font[0] ^ 1]) + self.font[1:]
        self.assertNotEqual(changed_font, self.font)
        (self.root / 'font file.bin').write_bytes(changed_font)
        result = self.plan(checked, ok=False)
        self.assertFalse(result.get('written', False))
        self.assertEqual(set(self.root.iterdir()) - before, {self.root / 'request file.json'})
        (self.root / 'font file.bin').write_bytes(self.font)
        (self.root / 'layout policy.json').write_text('{"schema_version":1,"schema_version":1}')
        self.check(ok=False)
        self.assertEqual((self.root / 'source file.bin').read_bytes(), self.raw)

    def test_long_word_overflow_is_not_silently_shortened(self):
        self.fixture([b'SHADOWRUNNERS'], 20)
        checked = self.check(ok=False)
        self.assertEqual(checked['analysis']['geometry_status'], 'FAIL')
        proposal = self.plan(checked, ok=False)
        self.assertFalse(proposal.get('written', False))
        self.assertEqual((self.root / 'source file.bin').read_bytes(), self.raw)


if __name__ == '__main__':
    unittest.main()
