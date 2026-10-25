"""Workspace lifecycle containment, with synthetic native-core coverage on Linux."""
import base64
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from romancer.libretro_frontend import LibretroError, LibretroFrontend
from romancer.runtime_worker import Workspace


class WorkspaceFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.core = self.root / 'core.bin'
        self.core.write_bytes(b'synthetic core')
        self.game = self.root / 'game.bin'
        self.game.write_bytes(b'synthetic game')
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)

    def parameters(self, **extra):
        return {'core': str(self.core), 'game': str(self.game),
                'expected_core_sha256': hashlib.sha256(self.core.read_bytes()).hexdigest(),
                'expected_game_sha256': hashlib.sha256(self.game.read_bytes()).hexdigest(),
                'session_dir': str(self.root / 'session'), **extra}

    def snapshot(self, data, field='save_ram_base64', **extra):
        params = self.parameters()
        binding=self.workspace._binding() if field=='state_base64' and self.workspace.frontend is not None else {}
        return {**binding,field: base64.b64encode(data).decode('ascii'),
                'sha256': hashlib.sha256(data).hexdigest(),
                'core_sha256': params['expected_core_sha256'],
                'game_sha256': params['expected_game_sha256'], **extra}

    def assert_unavailable(self):
        self.assertIsNone(self.workspace.frontend)
        self.assertFalse(self.workspace.handle('hello', {})['core_loaded'])
        for operation in ('advance', 'capture', 'audio', 'save_state', 'save_game', 'load_state'):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, 'load a core first'):
                    self.workspace.handle(operation, {})


class WorkspaceLifecycleTests(WorkspaceFixture):
    def setUp(self):
        super().setUp()
        self.frontend = Mock()
        self.frontend.load_game.return_value = {'loaded': True}
        self.frontend.av_info.return_value = {}
        self.frontend.memory_region.return_value = b'RAM!'
        self.frontend._sram_seed_extent = None
        self.frontend.verify_save_seed.side_effect = lambda seed: LibretroFrontend.verify_save_seed(self.frontend, seed)
        self.frontend.lib.retro_get_memory_size.return_value = 4
        self.factory = self.enterContext(patch('romancer.runtime_worker.LibretroFrontend',
                                              return_value=self.frontend))

    def test_frontend_not_exposed_until_all_load_validation_finishes(self):
        def pending(*args):
            self.assertFalse(self.workspace.handle('hello', {})['core_loaded'])
            return {}
        self.frontend.load_game.side_effect = pending
        self.frontend.av_info.side_effect = pending
        result = self.workspace.load(self.parameters())
        self.assertTrue(result['ok'])
        self.assertIs(self.workspace.frontend, self.frontend)

    def test_long_flat_build_basename_has_a_short_measured_native_snapshot(self):
        self.game=self.root/('a'*64+'.md');self.game.write_bytes(b'synthetic game')
        self.workspace.load(self.parameters())
        staged=self.frontend.load_game.call_args.args[0]
        self.assertEqual(staged.name,'game.md');self.assertEqual(staged.read_bytes(),b'synthetic game')

    def test_short_save_ram_rejected_and_closed(self):
        self.check_bad_save(b'RA')

    def test_long_save_ram_rejected_and_closed(self):
        self.check_bad_save(b'RAM!extra')

    def check_bad_save(self, data):
        with self.assertRaisesRegex(ValueError, 'not loaded exactly'):
            self.workspace.load(self.parameters(game_save=self.snapshot(data)))
        self.assert_unavailable()
        self.frontend.close.assert_called_once()
        self.assertTrue((self.root / 'session' / 'content' / 'game.bin').is_file())

    def test_invalid_ancestor_rejected_before_frontend_construction(self):
        seed = self.snapshot(b'RAM!', provenance={'ancestor_state_sha256': 'invalid'})
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.workspace.load(self.parameters(game_save=seed))
        self.factory.assert_not_called()
        self.assertFalse((self.root / 'session').exists())
        self.assert_unavailable()

    def test_load_game_failure_closes_uncommitted_frontend(self):
        self.frontend.load_game.side_effect = LibretroError('native load failed')
        with self.assertRaisesRegex(LibretroError, 'native load failed'):
            self.workspace.load(self.parameters())
        self.assert_unavailable()
        self.frontend.close.assert_called_once()

    def test_av_failure_closes_uncommitted_frontend(self):
        self.frontend.av_info.side_effect = LibretroError('AV inspection failed')
        with self.assertRaisesRegex(LibretroError, 'AV inspection failed'):
            self.workspace.load(self.parameters())
        self.assert_unavailable()
        self.frontend.close.assert_called_once()

    def test_capability_inspection_failure_closes_uncommitted_frontend(self):
        self.frontend.memory_region.side_effect = OSError('memory inspection failed')
        with self.assertRaisesRegex(OSError, 'memory inspection failed'):
            self.workspace.load(self.parameters())
        self.assert_unavailable()
        self.frontend.close.assert_called_once()

    def test_failed_native_import_invalidates_and_preserves_checkpoints(self):
        self.workspace.load(self.parameters())
        saved = self.workspace.handle('save_game', {})
        artifact = Path(saved['path'])
        metadata = artifact.with_suffix('.json')
        before = (artifact.read_bytes(), metadata.read_bytes())

        def partially_mutate(data):
            self.frontend.memory_region.return_value = b'BAD!'
            raise LibretroError('retro_unserialize failed')
        self.frontend.unserialize.side_effect = partially_mutate
        with self.assertRaisesRegex(LibretroError, 'retro_unserialize failed'):
            self.workspace.handle('load_state', {'snapshot': self.snapshot(b'state', 'state_base64')})
        self.assertEqual(self.frontend.memory_region(), b'BAD!')
        self.assert_unavailable()
        self.frontend.close.assert_called_once()
        self.assertEqual((artifact.read_bytes(), metadata.read_bytes()), before)

    def test_post_import_failure_invalidates(self):
        self.workspace.load(self.parameters())
        self.frontend.drain_audio.side_effect = OSError('post-import failure')
        with self.assertRaisesRegex(OSError, 'post-import failure'):
            self.workspace.handle('load_state', {'snapshot': self.snapshot(b'state', 'state_base64')})
        self.assert_unavailable()
        self.frontend.close.assert_called_once()

    def test_preflight_rejections_preserve_loaded_workspace(self):
        self.workspace.load(self.parameters())
        for changed in ({'sha256': '0' * 64}, {'core_sha256': '0' * 64},
                        {'game_sha256': '0' * 64}, {'state_base64': '!'}):
            with self.subTest(changed=changed):
                snapshot = self.snapshot(b'state', 'state_base64', **changed)
                with self.assertRaises(ValueError):
                    self.workspace.handle('load_state', {'snapshot': snapshot})
                self.assertTrue(self.workspace.handle('hello', {})['core_loaded'])
                self.assertEqual(self.workspace.handle('save_game', {})['run_mode'], 'cold_boot')
        self.frontend.unserialize.assert_not_called()
        self.frontend.close.assert_not_called()

    def test_cleanup_failure_keeps_original_error_and_invalidates(self):
        self.workspace.load(self.parameters())
        self.frontend.unserialize.side_effect = LibretroError('native import failed')
        self.frontend.close.side_effect = OSError('cleanup failed')
        with self.assertRaisesRegex(LibretroError, 'native import failed') as caught:
            self.workspace.handle('load_state', {'snapshot': self.snapshot(b'state', 'state_base64')})
        self.assert_unavailable()
        self.assertTrue(any('cleanup failed' in note for note in caught.exception.__notes__))


@unittest.skipUnless(sys.platform != 'win32' and shutil.which('gcc'), 'requires Linux gcc (run under WSL)')
class CompiledWorkspaceTests(WorkspaceFixture):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.native_core = Path(temporary.name) / 'mock.so'
        source = Path(__file__).with_name('mock_libretro.c').resolve()
        subprocess.run(['gcc', '-shared', '-fPIC', '-O2', '-DROMANCER_V35_TEST',
                        str(source), '-o', str(cls.native_core)], check=True, capture_output=True)
        wrapper = Path(temporary.name) / 'partial_restore.c'
        wrapper.write_text(
            '#define retro_unserialize mock_successful_unserialize\n'
            '#include "mock_libretro.c"\n'
            '#undef retro_unserialize\n'
            'bool retro_unserialize(const void *data, size_t size) {\n'
            '  if (mock_successful_unserialize(data, size)) saveram[0] = 127;\n'
            '  return false;\n'
            '}\n', encoding='ascii')
        cls.partial_core = Path(temporary.name) / 'partial.so'
        subprocess.run(['gcc', '-shared', '-fPIC', '-O2', '-DROMANCER_V35_TEST',
                        '-I', str(source.parent), str(wrapper), '-o', str(cls.partial_core)],
                       check=True, capture_output=True)

    def setUp(self):
        super().setUp()
        self.core = self.native_core

    def check_native_bad_save(self, data):
        instances = []
        def construct(*args, **kwargs):
            frontend = LibretroFrontend(*args, **kwargs)
            instances.append(frontend)
            return frontend
        with patch('romancer.runtime_worker.LibretroFrontend', side_effect=construct):
            with self.assertRaisesRegex(ValueError, 'not loaded exactly'):
                self.workspace.load(self.parameters(game_save=self.snapshot(data)))
        self.assert_unavailable()
        self.assertFalse(instances[0]._loaded)
        self.assertFalse(instances[0]._initialized)

    def test_native_short_save_ram(self):
        self.check_native_bad_save(b'XY')

    def test_native_long_save_ram(self):
        self.check_native_bad_save(b'X' * 65)

    def test_native_failed_import_closes_but_preflight_rejection_does_not(self):
        self.workspace.load(self.parameters())
        frontend = self.workspace.frontend
        checkpoint = self.workspace.handle('save_game', {})
        artifact = Path(checkpoint['path'])
        before = artifact.read_bytes()
        state = self.snapshot(b'too short', 'state_base64')
        with self.assertRaises(ValueError):
            self.workspace.handle('load_state', {'snapshot': {**state, 'sha256': '0' * 64}})
        self.assertTrue(self.workspace.handle('advance', {'frames': 1})['ok'])
        with self.assertRaisesRegex(LibretroError, 'retro_unserialize failed'):
            self.workspace.handle('load_state', {'snapshot': state})
        self.assert_unavailable()
        self.assertFalse(frontend._loaded)
        self.assertFalse(frontend._initialized)
        self.assertEqual(artifact.read_bytes(), before)

    def test_native_partial_restore_is_contained_without_rewriting_checkpoint(self):
        self.core = self.partial_core
        self.workspace.load(self.parameters())
        frontend = self.workspace.frontend
        checkpoint = self.workspace.handle('save_game', {})
        artifact = Path(checkpoint['path'])
        metadata = artifact.with_suffix('.json')
        before = (artifact.read_bytes(), metadata.read_bytes())
        state = self.workspace.handle('save_state', {})
        with self.assertRaisesRegex(LibretroError, 'retro_unserialize failed'):
            self.workspace.handle('load_state', {'snapshot': state})
        self.assert_unavailable()
        self.assertFalse(frontend._loaded)
        self.assertFalse(frontend._initialized)
        self.assertEqual((artifact.read_bytes(), metadata.read_bytes()), before)
        # Close may persist tainted SRAM only in the private working-save directory.
        working_save = self.root / 'session' / 'working-save' / 'game.srm'
        self.assertEqual(working_save.read_bytes()[0], 127)
        self.assertEqual(before[0][0], 0)


if __name__ == '__main__':
    unittest.main()
