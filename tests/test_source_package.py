import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


class SourcePackageTests(unittest.TestCase):
    def setUp(self):
        module = Path(__file__).resolve().parents[1] / 'tools' / 'package_source.py'
        self.assertTrue(module.exists(), 'verified source package builder missing')
        spec = importlib.util.spec_from_file_location('package_source', module)
        self.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.builder)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'source'
        (self.root / 'romancer').mkdir(parents=True)
        (self.root / 'README.txt').write_text('Synthetic fixture', encoding='utf-8')
        (self.root / 'romancer' / '__init__.py').write_text('VERSION = 1\n', encoding='utf-8')
        self.output = Path(self.tmp.name) / 'source.zip'

    def test_manifest_and_members_match_source(self):
        result = self.builder.package(self.root, self.output)
        self.assertTrue(result['ok'])
        with zipfile.ZipFile(self.output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), {'README.txt', 'romancer/__init__.py'})
        self.assertEqual(len(result['members']), 2)

    def test_bundle_reuses_one_root_readme_without_copying_a_second_guide(self):
        app=self.root/'app';(app/'romancer').mkdir(parents=True)
        (app/'romancer/__init__.py').write_text('VERSION=1',encoding='utf-8')
        (self.root/'BUNDLE.json').write_text('{}',encoding='utf-8')
        result=self.builder.package(app,self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read('README.txt'),(self.root/'README.txt').read_bytes())
        self.assertFalse((app/'README.txt').exists())

    def test_shell_launcher_has_posix_executable_metadata(self):
        (self.root / 'run.sh').write_bytes(b'#!/usr/bin/env bash\nexit 0\n')
        self.builder.package(self.root, self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.getinfo('run.sh').create_system, 3)
            self.assertEqual((archive.getinfo('run.sh').external_attr >> 16) & 0o777, 0o755)
            self.assertEqual((archive.getinfo('README.txt').external_attr >> 16) & 0o777, 0o644)

    def test_shell_launcher_rejects_crlf_instead_of_publishing_broken_bytes(self):
        (self.root / 'run.sh').write_bytes(b'#!/usr/bin/env bash\r\nset -euo pipefail\r\n')
        with self.assertRaisesRegex(ValueError, 'shell.*LF'):
            self.builder.package(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_actual_shell_launcher_is_lf(self):
        launcher = Path(__file__).resolve().parents[1] / 'run.sh'
        self.assertNotIn(b'\r', launcher.read_bytes())

    @unittest.skipUnless(os.name == 'posix', 'Bash launcher on POSIX')
    def test_actual_shell_launcher_preserves_caller_directory(self):
        app = Path(__file__).resolve().parents[1]
        launcher = app / 'run.sh'
        for args in (['version', '--json'], ['--help']):
            process = subprocess.run(['bash', str(launcher), *args], cwd=self.root,
                                     capture_output=True, text=True, timeout=20)
            self.assertEqual(process.returncode, 0, process.stderr)
            if args[0] == 'version':
                from romancer import ROMANCER_VERSION
                self.assertEqual(json.loads(process.stdout)['version'], ROMANCER_VERSION)
            else:
                self.assertIn('script-inspect', process.stdout)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell launcher on Windows')
    def test_powershell_launcher_does_not_import_caller_shadow_package(self):
        launcher = Path(__file__).resolve().parents[1] / 'run.ps1'
        process = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                  '-File', str(launcher), 'version', '--json'], cwd=self.root,
                                 capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        from romancer import ROMANCER_VERSION
        self.assertEqual(json.loads(process.stdout)['version'], ROMANCER_VERSION)

    def test_private_and_bytecode_directories_are_excluded(self):
        for directory in ['reports', 'work_private', 'romancer/__pycache__', 'docs/.romancer-history',
                          'docs/.romancer-evidence', 'tests/.ROMANCER-EVIDENCE']:
            path = self.root / directory
            path.mkdir(parents=True)
            (path / 'private.json').write_text('private', encoding='utf-8')
        result = self.builder.package(self.root, self.output)
        self.assertEqual(len(result['members']), 2)

    def test_patch_byte_report_is_not_distributable(self):
        docs = self.root / 'docs'
        docs.mkdir()
        (docs / 'local-patch.json').write_text(json.dumps({
            'schema_version': 1, 'tool': 'ROMancer',
            'before_hex': '0001', 'after_hex': '0203',
        }), encoding='utf-8')
        result=self.builder.package(self.root,self.output)
        self.assertNotIn('docs/local-patch.json',[r['path'] for r in result['members']])

    def test_private_directory_exclusions_are_case_insensitive(self):
        for directory in ['docs/Reports', 'docs/Private', 'tests/WORK_PRIVATE',
                          'examples/Evidence', 'romancer/__PYCACHE__']:
            path = self.root / directory
            path.mkdir(parents=True)
            (path / 'local.json').write_text('{"before_hex":"0001"}', encoding='utf-8')
        result = self.builder.package(self.root, self.output)
        self.assertEqual({row['path'] for row in result['members']},
                         {'README.txt', 'romancer/__init__.py'})

    def test_unknown_text_and_fixture_files_need_explicit_approval(self):
        for name in ['tests/local-fixture.json',
                     'examples/captured.log', 'romancer/private_export.py']:
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic private content', encoding='utf-8')
                try:
                    with self.assertRaisesRegex(ValueError, 'unapproved source member'):
                        self.builder.package(self.root, self.output)
                finally:
                    path.unlink()
                    self.output.unlink(missing_ok=True)

    def test_approved_document_is_included(self):
        path = self.root / 'docs' / 'V32_SAFETY.md'
        path.parent.mkdir()
        path.write_text('Synthetic safety documentation', encoding='utf-8')
        result = self.builder.package(self.root, self.output)
        self.assertNotIn('docs/V32_SAFETY.md', [row['path'] for row in result['members']])
        self.assertEqual([r['path'] for r in result['members'] if r['path'].endswith(('.md','.txt'))],['README.txt'])

    def test_runtime_source_and_synthetic_tests_are_explicit_members(self):
        names = ['romancer/runtime_client.py', 'romancer/runtime_worker.py',
                 'romancer/runtime_protocol.py', 'romancer/audio_capture.py',
                 'tests/test_runtime_worker.py', 'tests/test_runtime_workspace.py',
                 'tests/test_audio_capture.py', 'tests/mock_worker_hang.c']
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Synthetic source-selection fixture', encoding='utf-8')
        result = self.builder.package(self.root, self.output)
        self.assertTrue(set(names).issubset({row['path'] for row in result['members']}))

    def test_capture_and_script_sources_are_explicit_members(self):
        names = ['romancer/capture_cli.py', 'romancer/capture_ingest.py',
                 'romancer/capture_runtime.py', 'romancer/capture_store.py',
                 'romancer/script.py', 'romancer/script_cli.py',
                 'romancer/script_patch.py', 'romancer/script_schema.py',
                 'tests/test_capture_cli.py', 'tests/test_capture_ingest.py',
                 'tests/test_capture_runtime.py', 'tests/test_capture_search.py',
                 'tests/test_capture_store.py', 'tests/script_fixtures.py',
                 'tests/test_script.py', 'tests/test_script_cli.py',
                 'tests/test_script_patch.py', 'tests/test_script_schema.py']
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Synthetic source-selection fixture', encoding='utf-8')
        result = self.builder.package(self.root, self.output)
        self.assertTrue(set(names).issubset({row['path'] for row in result['members']}))

    def test_source_reads_are_bounded(self):
        original_open = Path.open
        test = self
        requests = []

        class ObservedReader:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def read(self, size=-1):
                test.assertGreater(size, 0, 'source reads must be bounded')
                test.assertLessEqual(size, 64 * 1024)
                requests.append(size)
                return self.stream.read(size)

        def observe(path, mode='r', *args, **kwargs):
            stream = original_open(path, mode, *args, **kwargs)
            return ObservedReader(stream) if mode == 'rb' and path.is_relative_to(self.root) else stream

        with patch.object(Path, 'open', observe):
            result = self.builder.package(self.root, self.output)
        self.assertTrue(result['ok'])
        self.assertTrue(requests)

    def test_growing_member_cannot_bypass_package_budget(self):
        member = self.root / 'README.txt'
        member.write_bytes(b'R')
        original_open = Path.open
        grown = False

        def grow(path, mode='r', *args, **kwargs):
            nonlocal grown
            if path == member and mode == 'rb' and not grown:
                grown = True
                with original_open(path, 'ab') as stream:
                    stream.write(b'X' * 32)
            return original_open(path, mode, *args, **kwargs)

        with patch.object(self.builder, 'MAX_MEMBER_BYTES', 32, create=True), patch.object(Path, 'open', grow):
            with self.assertRaisesRegex(ValueError, 'budget|changed|exceeds'):
                self.builder.package(self.root, self.output)
        self.assertTrue(grown)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.glob('.romancer-package-*')), [])

    def test_aggregate_growth_cannot_bypass_package_budget(self):
        members = [self.root / 'README.txt', self.root / 'romancer' / '__init__.py']
        for member in members:
            member.write_bytes(b'R')
        original_open = Path.open
        grown = set()

        def grow(path, mode='r', *args, **kwargs):
            if path in members and mode == 'rb' and path not in grown:
                grown.add(path)
                with original_open(path, 'ab') as stream:
                    stream.write(b'X' * 20)
            return original_open(path, mode, *args, **kwargs)

        with patch.object(self.builder, 'MAX_MEMBER_BYTES', 32, create=True), \
                patch.object(self.builder, 'MAX_TOTAL_BYTES', 40, create=True), \
                patch.object(Path, 'open', grow):
            with self.assertRaisesRegex(ValueError, 'budget|changed|exceeds'):
                self.builder.package(self.root, self.output)
        self.assertTrue(grown)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.glob('.romancer-package-*')), [])

    def test_exact_actual_budgets_succeed(self):
        (self.root / 'README.txt').write_bytes(b'ABCD')
        (self.root / 'romancer' / '__init__.py').write_bytes(b'XYZ')
        with patch.object(self.builder, 'MAX_MEMBER_BYTES', 4, create=True), \
                patch.object(self.builder, 'MAX_TOTAL_BYTES', 7, create=True):
            result = self.builder.package(self.root, self.output)
        self.assertEqual(sum(row['bytes'] for row in result['members']), 7)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read('README.txt'), b'ABCD')
            self.assertEqual(archive.read('romancer/__init__.py'), b'XYZ')

    def test_source_change_after_read_blocks_publication(self):
        member = self.root / 'README.txt'
        original_open = Path.open
        original_close = zipfile.ZipFile.close
        changed = False

        def change(archive):
            nonlocal changed
            result = original_close(archive)
            if archive.mode == 'w' and not changed:
                changed = True
                with original_open(member, 'ab') as stream:
                    stream.write(b'changed')
            return result

        with patch.object(zipfile.ZipFile, 'close', change):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.builder.package(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_unexpected_binary_in_source_blocks_package(self):
        (self.root / 'romancer' / 'game.bin').write_bytes(b'private')
        with self.assertRaises(ValueError):
            self.builder.package(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            self.builder.package(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b'keep')

    @unittest.skipUnless(os.name == 'nt', 'Windows path rules')
    def test_reserved_output_is_rejected_before_staging(self):
        for name in ['NUL', 'source.zip:private', 'source.zip.', 'source.zip ']:
            with self.subTest(name=name), patch.object(
                    self.builder.tempfile, 'mkstemp',
                    side_effect=AssertionError('invalid output reached staging')):
                with self.assertRaisesRegex(ValueError, 'reserved|ambiguous'):
                    self.builder.package(self.root, self.output.parent / name)

    def test_output_parent_file_is_rejected_before_staging(self):
        parent = self.output.parent / 'occupied'
        parent.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'parent|directory'):
            self.builder.package(self.root, parent / 'source.zip')
        self.assertEqual(parent.read_bytes(), b'keep')
        self.assertEqual(list(self.output.parent.glob('.romancer-package-*')), [])

    def test_source_member_cannot_be_output_or_output_parent(self):
        member = self.root / 'README.txt'
        before = member.read_bytes()
        for output in [member, member / 'source.zip']:
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    self.builder.package(self.root, output)
                self.assertEqual(member.read_bytes(), before)

    def test_destination_created_during_publication_is_preserved(self):
        original_link = os.link

        def race(source, destination):
            Path(destination).write_bytes(b'concurrent output')
            return original_link(source, destination)

        with patch.object(self.builder.os, 'link', race):
            with self.assertRaises(FileExistsError):
                self.builder.package(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b'concurrent output')
        self.assertEqual(list(self.output.parent.glob('.romancer-package-*')), [])

    def test_standalone_tool_runs_outside_application_directory(self):
        result = subprocess.run(
            [sys.executable, str(Path(self.builder.__file__)), str(self.root), str(self.output)],
            cwd=self.tmp.name, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertTrue(self.output.is_file())

    def test_clean_extraction_preserves_v9_genre_policies(self):
        application = Path(__file__).resolve().parents[1]
        self.builder.package(application, self.output)
        extracted = Path(self.tmp.name) / 'clean extraction'
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(extracted)
        bootstrap = (
            'import runpy, sys; sys.path.insert(0, sys.argv[1]); '
            "sys.argv = ['romancer', 'v9-self-test', '--json']; "
            "runpy.run_module('romancer', run_name='__main__')"
        )
        result = subprocess.run(
            [sys.executable, '-I', '-B', '-c', bootstrap, str(extracted)],
            cwd=extracted, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['ok'], report)
        genres = next(check for check in report['tests'] if check['name'] == 'genre policy packs')
        self.assertTrue(genres['ok'], genres)
        self.assertEqual(
            {path.stem for path in (extracted / 'knowledge' / 'genre_packs').glob('*.json')},
            {'action', 'action_rpg', 'adventure', 'fighting', 'jrpg', 'metroidvania',
             'platformer', 'puzzle', 'racing', 'roguelike', 'shooter', 'srpg',
             'stealth', 'strategy', 'survival_horror', 'universal', 'visual_novel'},
        )

    def test_unknown_knowledge_files_are_not_approved(self):
        for name in ['knowledge/local-vault.json', 'knowledge/genre_packs/local-game.json']:
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"before_hex":"0001"}', encoding='utf-8')
                try:
                    with self.assertRaisesRegex(ValueError, 'unapproved source member'):
                        self.builder.package(self.root, self.output)
                finally:
                    path.unlink()
                    self.output.unlink(missing_ok=True)

    def test_private_knowledge_directories_remain_excluded(self):
        for name in ['knowledge/Private', 'knowledge/Reports', 'knowledge/genre_packs/Work_Private']:
            path = self.root / name
            path.mkdir(parents=True, exist_ok=True)
            (path / 'local.json').write_text('{"before_hex":"0001"}', encoding='utf-8')
        result = self.builder.package(self.root, self.output)
        self.assertEqual({row['path'] for row in result['members']},
                         {'README.txt', 'romancer/__init__.py'})


if __name__ == '__main__':
    unittest.main()
