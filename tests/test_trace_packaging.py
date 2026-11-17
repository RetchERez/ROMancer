"""Tracing-engine packs: release pins, the pack inventory, the pin tool and the Windows bundle."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def built_folder(folder, platform_id='windows-amd64', *, stale=None):
    """A stand-in for tools/build_trace_cores.py output: marker-only libraries and an honest build record."""
    from romancer.core_pins import WINDOWS_CORE_FILES
    from tools.build_trace_cores import BUILD_INFO, HEADER, MARKER, TRACE_ENGINES, library_suffix
    folder.mkdir(parents=True)
    info = {'schema_version': 1, 'platform': platform_id, 'toolchain': 'test', 'recipe': 'tools/build_trace_cores.py',
            'core_sources_sha256': WINDOWS_CORE_FILES['CORE-SOURCES.zip']['sha256'], 'engines': {}}
    for engine, spec in TRACE_ENGINES.items():
        raw = b'\0' + MARKER + b'\0' + engine.encode() + platform_id.encode()
        name = spec['base'] + library_suffix(platform_id)
        (folder / name).write_bytes(raw)
        info['engines'][engine] = {'file': name, 'sha256': _sha(raw), 'size': len(raw), 'patch': 'trace/' + spec['patch'],
                                   'patch_sha256': 'f' * 64 if engine == stale else _sha((ROOT / 'trace' / spec['patch']).read_bytes()),
                                   'header_sha256': _sha((ROOT / 'trace' / HEADER).read_bytes())}
    (folder / BUILD_INFO).write_text(json.dumps(info), encoding='utf-8')
    return folder


def license_folder(folder):
    """Stand-in license texts, and the inventory rows that make them the reviewed ones."""
    from romancer.core_pins import WINDOWS_CORE_FILES
    folder.mkdir(parents=True)
    rows = dict(WINDOWS_CORE_FILES)
    for name in WINDOWS_CORE_FILES:
        if name.startswith('licenses/'):
            raw = ('license text for ' + name).encode()
            (folder / name.split('/', 1)[1]).write_bytes(raw)
            rows[name] = {'size': len(raw), 'sha256': _sha(raw)}
    return rows


class PinToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        from tools import pin_trace_cores
        self.tool = pin_trace_cores
        self.pins_file = self.root / 'trace_core_pins.py'
        self.pins_file.write_text('TRACE_CORE_PINS = {}\nTRACE_CORE_FILES = {}\n', encoding='utf-8')
        rows = license_folder(self.root / 'licenses')
        for patcher in (mock.patch.object(pin_trace_cores, 'PINS_FILE', self.pins_file),
                        mock.patch.object(pin_trace_cores, 'WINDOWS_CORE_FILES', rows)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def test_pack_is_completed_pinned_per_platform_and_a_second_run_changes_nothing(self):
        windows = built_folder(self.root / 'win', 'windows-amd64')
        linux = built_folder(self.root / 'linux', 'linux-x86_64')
        self.tool.pin([windows], self.root / 'licenses')
        pins, files = self.tool.current_pins()
        self.assertEqual(set(files), {'windows-amd64'})
        self.assertEqual(len(pins), 5)
        for sha, pin in pins.items():
            self.assertEqual(_sha((windows / pin['file']).read_bytes()), sha)
            self.assertTrue(pin['license'] and pin['source_url'] and pin['source_commit'] and pin['romancer_patch'].startswith('trace/patch_'))
            self.assertTrue(pin['file'].endswith('_trace_libretro.dll'))
        inventory = files['windows-amd64']
        for name in ('TRACE-ORIGINS.json', 'TRACE-BUILD-INFO.json', 'THIRD_PARTY_NOTICES.txt', 'licenses/gambatte.txt',
                     'licenses/toolchain-libgcc-COPYING3.txt', 'source-changes/patch_blastem.py', 'source-changes/patch_bsnes.py',
                     'source-changes/patch_fceumm.py', 'source-changes/patch_gambatte.py', 'source-changes/romancer_trace.h',
                     'source-changes/build_trace_cores.py'):
            self.assertIn(name, inventory)
        self.assertEqual((windows / 'source-changes/patch_gambatte.py').read_bytes(), (ROOT / 'trace/patch_gambatte.py').read_bytes())
        self.assertNotIn('source-changes/blastem-linux-cpuid.patch', inventory)
        # The Linux pack is pinned separately; the Windows entries stay.
        (linux / 'left-over.txt').write_text('stray')
        self.tool.pin([linux], self.root / 'licenses')
        pins, files = self.tool.current_pins()
        self.assertEqual(set(files), {'windows-amd64', 'linux-x86_64'})
        self.assertEqual(sorted(p['platform'] for p in pins.values()), ['linux-x86_64'] * 5 + ['windows-amd64'] * 5)
        self.assertIn('source-changes/blastem-linux-cpuid.patch', files['linux-x86_64'])
        self.assertIn('licenses/toolchain-llvm-runtime-LICENSE.txt', files['linux-x86_64'])
        self.assertNotIn('left-over.txt', files['linux-x86_64'])
        before = self.pins_file.read_bytes()
        self.tool.pin([windows, linux], self.root / 'licenses')
        self.assertEqual(self.pins_file.read_bytes(), before)

    def test_stale_changed_or_incomplete_builds_are_refused_and_pin_nothing(self):
        before = self.pins_file.read_bytes()
        stale = built_folder(self.root / 'stale', stale='genesis')
        with self.assertRaisesRegex(SystemExit, 'stale.*--only genesis'):
            self.tool.pin([stale], self.root / 'licenses')
        changed = built_folder(self.root / 'changed')
        (changed / 'gambatte_trace_libretro.dll').write_bytes(b'another build')
        with self.assertRaisesRegex(SystemExit, 'differs from its build record'):
            self.tool.pin([changed], self.root / 'licenses')
        partial = built_folder(self.root / 'partial')
        info = json.loads((partial / 'TRACE-BUILD-INFO.json').read_text())
        del info['engines']['nes']
        (partial / 'TRACE-BUILD-INFO.json').write_text(json.dumps(info))
        with self.assertRaisesRegex(SystemExit, 'engines missing: nes'):
            self.tool.pin([partial], self.root / 'licenses')
        good = built_folder(self.root / 'good')
        (self.root / 'licenses/gambatte.txt').write_text('edited')
        with self.assertRaisesRegex(SystemExit, 'reviewed license'):
            self.tool.pin([good], self.root / 'licenses')
        self.assertEqual(self.pins_file.read_bytes(), before)


class PackAcceptanceTests(unittest.TestCase):
    """A packaged release accepts exactly the pinned pack."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        from tools import pin_trace_cores
        pins_file = self.root / 'trace_core_pins.py'
        pins_file.write_text('TRACE_CORE_PINS = {}\nTRACE_CORE_FILES = {}\n', encoding='utf-8')
        rows = license_folder(self.root / 'licenses')
        self.pack = built_folder(self.root / 'trace-cores')
        with mock.patch.object(pin_trace_cores, 'PINS_FILE', pins_file), mock.patch.object(pin_trace_cores, 'WINDOWS_CORE_FILES', rows):
            pin_trace_cores.pin([self.pack], self.root / 'licenses')
            self.pins, self.files = pin_trace_cores.current_pins()
        from romancer import trace_cores
        self.tc = trace_cores
        for patcher in (mock.patch.dict(trace_cores.TRACE_CORE_PINS, self.pins, clear=True),
                        mock.patch.dict(trace_cores.TRACE_CORE_FILES, self.files, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_release_loads_each_pinned_engine_and_refuses_everything_else(self):
        from romancer import bundled_cores
        with mock.patch.object(bundled_cores, 'packaged_release', return_value=True):
            for pin in self.pins.values():
                self.assertEqual(self.tc.require_reviewed_trace_core(self.pack / pin['file'])['engine'], pin['engine'])
            library = self.pack / 'gambatte_trace_libretro.dll'
            library.write_bytes(library.read_bytes() + b'\0')
            with self.assertRaisesRegex(ValueError, 'reviewed tracing engines'):
                self.tc.require_reviewed_trace_core(library)
            # Another platform's or an older release's pins are not this pack's.
            with mock.patch.dict(self.tc.TRACE_CORE_PINS, {}, clear=True):
                with self.assertRaisesRegex(ValueError, 'reviewed tracing engines'):
                    self.tc.require_reviewed_trace_core(self.pack / 'fceumm_trace_libretro.dll')
            ordinary = self.root / 'gambatte_libretro.dll'
            ordinary.write_bytes(b'a playtest engine')
            with self.assertRaisesRegex(ValueError, 'not a ROMancer tracing build'):
                self.tc.require_reviewed_trace_core(ordinary)
            # The tracing pins never widen what Playtest loads.
            with self.assertRaisesRegex(ValueError, 'reviewed open-source'):
                bundled_cores.require_reviewed_release_core(self.pack / 'fceumm_trace_libretro.dll')

    def test_pack_inventory_is_exact(self):
        members = self.tc.trace_pack_members(self.pack)
        self.assertEqual(set(members), set(self.files['windows-amd64']))
        self.assertEqual(self.tc.trace_pack_members(self.pack, 'windows-amd64').keys(), members.keys())
        with self.assertRaisesRegex(ValueError, 'no reviewed inventory'):
            self.tc.trace_pack_members(self.pack, 'linux-x86_64')
        extra = self.pack / 'extra_trace_libretro.dll'
        extra.write_bytes(self.tc.MARKER)
        with self.assertRaisesRegex(ValueError, 'unlisted or missing'):
            self.tc.trace_pack_members(self.pack)
        extra.unlink()
        notice = self.pack / 'THIRD_PARTY_NOTICES.txt'
        original = notice.read_bytes()
        notice.unlink()
        with self.assertRaisesRegex(ValueError, 'unlisted or missing'):
            self.tc.trace_pack_members(self.pack)
        notice.write_bytes(original + b'x')
        with self.assertRaisesRegex(ValueError, 'identity differs: THIRD_PARTY_NOTICES.txt'):
            self.tc.trace_pack_members(self.pack)
        notice.write_bytes(original)
        script = self.pack / 'source-changes/patch_fceumm.py'
        script.write_bytes(script.read_bytes() + b'\n# changed\n')
        with self.assertRaisesRegex(ValueError, 'identity differs: source-changes/patch_fceumm.py'):
            self.tc.trace_pack_members(self.pack)

    def test_lookup_prefers_the_release_name_and_finds_the_pack_beside_the_app(self):
        with mock.patch.dict(os.environ, {self.tc.ENV: str(self.pack)}), mock.patch.object(self.tc, '_suffix', return_value='.dll'):
            self.assertEqual(self.tc.trace_core_for('gbc').name, 'gambatte_trace_libretro.dll')
            self.assertEqual(self.tc.trace_core_for('sms').name, 'blastem_trace_libretro.dll')
            self.assertEqual(self.tc.trace_core_for('snes').name, 'bsnes_mercury_balanced_trace_libretro.dll')
            from romancer.bundled_cores import TOP_GEAR_3000_DSP4_SHA256
            self.assertEqual(self.tc.trace_core_for('snes', TOP_GEAR_3000_DSP4_SHA256).name, 'bsnes_mercury_dsp4_trace_libretro.dll')
            (self.pack / 'gambatte_libretro.dll').write_bytes(self.tc.MARKER)
            self.assertEqual(self.tc.trace_core_for('gb').name, 'gambatte_trace_libretro.dll', 'the release name wins over a developer build')
            self.assertTrue(all(row['installed'] for row in self.tc.available().values()))
        with mock.patch.dict(os.environ):
            os.environ.pop(self.tc.ENV, None)
            self.assertEqual([p.name for p in self.tc.search_roots()], ['trace-cores', 'trace-cores'])
            self.assertEqual(self.tc.search_roots()[1].parent, ROOT.parent, 'a release keeps trace-cores beside app, like cores')

    def test_windows_bundle_carries_the_pack_and_the_audit_ties_it_to_the_source(self):
        from tools.package_source import package
        from tools.package_windows import build_bundle, package_bundle
        from tools.audit_release import audit_windows
        runtime = {'python': [('LICENSE.txt', b'Python notice')],
                   'pillow': [('pillow-12.3.0.dist-info/licenses/LICENSE', b'Pillow notice')]}
        source = self.root / 'source.zip'
        package(ROOT, source)
        with mock.patch('tools.package_windows.runtime_members', side_effect=lambda _p, _sha, kind: runtime[kind]), \
                mock.patch('romancer.patch_sets._publish_directory', side_effect=lambda a, b: a.rename(b)):
            result = build_bundle(ROOT, self.root, self.root / 'bundle', trace_cores=self.pack)
            self.assertTrue(result['trace_engines_bundled'])
            bundle = self.root / 'bundle'
            manifest = json.loads((bundle / 'BUNDLE.json').read_text(encoding='utf-8'))
            self.assertEqual(set(manifest['trace_engines']['engines']), {'gb', 'nes', 'snes', 'snes-dsp4', 'genesis'})
            listed = {row['path'] for row in manifest['files']}
            for name in self.files['windows-amd64']:
                self.assertIn('trace-cores/' + name, listed)
                self.assertEqual((bundle / 'trace-cores' / name).read_bytes(), (self.pack / name).read_bytes())
            self.assertEqual((bundle / 'app/trace/patch_blastem.py').read_bytes(), (bundle / 'trace-cores/source-changes/patch_blastem.py').read_bytes())
            package_bundle(bundle, self.root / 'windows.zip')
            # The tracing engines' source is the playtest pack's CORE-SOURCES.zip, so they never ship without it.
            with self.assertRaisesRegex(ValueError, 'need the engine pack'):
                audit_windows(self.root / 'windows.zip', source, self.root, trace_cores=self.pack)
            # Without the pack named, its files are unexpected.
            with self.assertRaises(ValueError):
                audit_windows(self.root / 'windows.zip', source, self.root)
            (self.pack / 'left-over.dll').write_bytes(b'unreviewed')
            with self.assertRaisesRegex(ValueError, 'unlisted or missing'):
                build_bundle(ROOT, self.root, self.root / 'bundle2', trace_cores=self.pack)


class ReleasePinTests(unittest.TestCase):
    """The pins that ship: complete, distinct from the playtest engines, and built from today's hook scripts."""

    def test_pins_are_complete_and_never_collide_with_playtest_engines(self):
        from romancer import core_pins, core_pins_linux, trace_cores
        from tools.build_trace_cores import TRACE_ENGINES
        playtest_names = set(core_pins.WINDOWS_CORE_FILES) | set(core_pins_linux.CORE_FILES)
        playtest_hashes = {row['sha256'] for rows in (core_pins.WINDOWS_CORE_FILES, core_pins_linux.CORE_FILES) for row in rows.values()}
        for spec in TRACE_ENGINES.values():
            for suffix in ('.dll', '.so'):
                self.assertNotIn(spec['base'] + suffix, playtest_names)
        self.assertEqual({system for spec in TRACE_ENGINES.values() for system in spec['systems']}, set(trace_cores.SYSTEM_CORES))
        for sha, pin in trace_cores.TRACE_CORE_PINS.items():
            self.assertRegex(sha, '^[0-9a-f]{64}$')
            self.assertNotIn(sha, playtest_hashes)
            self.assertNotIn(pin['file'], playtest_names)
            for field in ('name', 'license', 'source_url', 'source_commit', 'romancer_patch', 'patch_sha256', 'platform'):
                self.assertTrue(pin.get(field), field)
            self.assertEqual(trace_cores.TRACE_CORE_FILES[pin['platform']][pin['file']]['sha256'], sha)
        for platform_id, files in trace_cores.TRACE_CORE_FILES.items():
            libraries = {name for name in files if name.endswith(('.dll', '.so'))}
            self.assertEqual(libraries, {pin['file'] for pin in trace_cores.TRACE_CORE_PINS.values() if pin['platform'] == platform_id})
            self.assertEqual(len(libraries), len(TRACE_ENGINES), platform_id)
            for required in ('THIRD_PARTY_NOTICES.txt', 'TRACE-ORIGINS.json', 'TRACE-BUILD-INFO.json'):
                self.assertIn(required, files)

    def test_pinned_engines_were_built_from_the_hook_scripts_in_this_source(self):
        from romancer import trace_cores
        for sha, pin in trace_cores.TRACE_CORE_PINS.items():
            with self.subTest(engine=pin['engine'], platform=pin['platform']):
                self.assertEqual(_sha((ROOT / pin['romancer_patch']).read_bytes()), pin['patch_sha256'],
                                 f'{pin["romancer_patch"]} changed after {pin["file"]} was built: rebuild it '
                                 '(tools/build_trace_cores.py --update --only ' + pin['engine'] + ') and run tools/pin_trace_cores.py')
                self.assertEqual(_sha((ROOT / 'trace/romancer_trace.h').read_bytes()), pin['header_sha256'])
                changes = trace_cores.TRACE_CORE_FILES[pin['platform']]
                script = 'source-changes/' + pin['romancer_patch'].split('/')[-1]
                self.assertEqual(changes[script]['sha256'], pin['patch_sha256'], 'the pack ships the same hook script')

    def test_source_package_ships_the_gpl_source_changes_and_notices(self):
        from tools.package_source import APPROVED_FILES
        from tools.build_trace_cores import TRACE_ENGINES
        for spec in TRACE_ENGINES.values():
            self.assertIn('trace/' + spec['patch'], APPROVED_FILES)
        for name in ('trace/romancer_trace.h', 'trace/ENGINES-NOTICES.txt', 'tools/build_trace_cores.py', 'tools/pin_trace_cores.py',
                     'tools/verify_trace_engines.py', 'romancer/trace_core_pins.py'):
            self.assertIn(name, APPROVED_FILES)
        notices = (ROOT / 'trace/ENGINES-NOTICES.txt').read_text(encoding='utf-8')
        for spec in TRACE_ENGINES.values():
            self.assertIn('source-changes/' + spec['patch'], notices)
        self.assertIn('Modified by ROMancer', notices)
        self.assertIn('tracing', (ROOT / 'THIRD_PARTY_NOTICES.txt').read_text(encoding='utf-8'))

    def test_build_recipe_refuses_other_sources_and_unapplied_hooks(self):
        from tools import build_trace_cores as recipe
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'CORE-SOURCES.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('gambatte/Makefile.libretro', 'all:\n')
            with self.assertRaisesRegex(ValueError, 'release pin'):
                recipe.build(archive, Path(folder) / 'out')
            self.assertFalse((Path(folder) / 'out').exists())
            tree = recipe.extract_engine(archive, 'gambatte', Path(folder) / 'work')
            self.assertTrue((tree / 'Makefile.libretro').is_file())
            with (Path(folder) / 'log').open('wb') as log:
                with self.assertRaisesRegex(ValueError, 'patch_gambatte.py did not apply'):
                    recipe.apply_hooks('patch_gambatte.py', tree, log)
            with self.assertRaisesRegex(ValueError, 'unknown engine'):
                recipe.build(archive, Path(folder) / 'out', only=['gba'])


class SceneBackupTests(unittest.TestCase):
    def test_backup_keeps_recorded_scenes_and_restore_puts_them_back_for_the_same_rom(self):
        from tests.test_streaming_release import require_directory_publication
        require_directory_publication(self)
        from romancer import workbench_projects as p
        from romancer.project_portability import backup_project, restore_project
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'own.bin'
            source.write_bytes(b'01234567')
            project = Path(p.create_project(root / 'original', 'Scenes')['path'])
            row = p.register_source(project, source, None)
            store = project / 'trace-scenes' / row['sha256'][:32]      # where EditSessionTools keeps a ROM's scenes
            kept = {'scenes/0123456789abcdef.scene': b'scene', 'scenes/0123456789abcdef.png': b'png', 'changes.json': b'{"changes": []}',
                    'current_run': b'r1', 'runs/r1/inputs.bin': b'inputs', 'runs/r1/000060.state': b'state'}
            rebuilt = {'renders/abc.png': b'preview', 'work/abc.gbc': b'patched copy', 'work/engine-x/game.sav': b'save'}
            for name, raw in {**kept, **rebuilt}.items():
                (store / name).parent.mkdir(parents=True, exist_ok=True)
                (store / name).write_bytes(raw)
            everything = ['sources', 'builds', 'reports', 'sessions', 'captures']
            archive = root / 'backup.zip'
            backup_project(project, archive, everything)
            prefix = 'trace-scenes/' + row['sha256'][:32] + '/'
            with zipfile.ZipFile(archive) as z:
                members = {name[len(prefix):] for name in z.namelist() if name.startswith(prefix)}
            self.assertEqual(members, set(kept))
            restored = Path(restore_project(archive, root / 'moved')['path'])
            for name, raw in kept.items():
                self.assertEqual((restored / prefix / name).read_bytes(), raw)
            self.assertFalse((restored / prefix / 'renders').exists())
            # Scenes are private session data: a backup without that role leaves them out.
            partial = root / 'partial.zip'
            backup_project(project, partial, ['sources', 'builds'])
            with zipfile.ZipFile(partial) as z:
                self.assertFalse([name for name in z.namelist() if name.startswith('trace-scenes/')])


if __name__ == '__main__':
    unittest.main()
