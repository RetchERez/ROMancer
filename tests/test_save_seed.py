import ctypes
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from romancer.libretro_frontend import LibretroFrontend


class SaveSeedTests(unittest.TestCase):
    def test_save_write_failure_still_unloads_and_deinitializes_core(self):
        f=LibretroFrontend.__new__(LibretroFrontend);f._loaded=True;f._initialized=True
        f._persist_save_ram=MagicMock(side_effect=OSError('disk full'));f._audio_capture=MagicMock()
        f.lib=SimpleNamespace(retro_unload_game=MagicMock(),retro_deinit=MagicMock())
        with self.assertRaisesRegex(OSError,'disk full'):f.close()
        f.lib.retro_unload_game.assert_called_once();f.lib.retro_deinit.assert_called_once();f._audio_capture.reset.assert_called_once()
        self.assertFalse(f._loaded);self.assertFalse(f._initialized)
        f.close();f.lib.retro_unload_game.assert_called_once()

    def test_interactive_pool_preserves_measured_save_continuation_mode(self):
        from romancer.workbench_runtime import RuntimePool
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);core=root/'core.so';core.write_bytes(b'core');game=root/'game';game.write_bytes(b'game')
            row={'artifact_id':'a'*32,'path':str(game),'size':4,'sha256':__import__('hashlib').sha256(b'game').hexdigest()}
            runtime=MagicMock();runtime.load_result={'run_mode':'game_save_continuation'};runtime.request.return_value={'ok':True}
            pool=RuntimePool()
            try:
                with patch('romancer.workbench_runtime.artifact',return_value=row),patch('romancer.workbench_runtime.preflight_load',side_effect=lambda load,*a,**k:load),patch('romancer.workbench_runtime.OwnedRuntime',return_value=runtime):
                    result=pool.load(root,row['artifact_id'],core,{})
                    self.assertEqual(result['run_mode'],'game_save_continuation')
            finally:pool.close()

    def frontend(self, folder, size, name='Gambatte', suffix='.gb', fill=255):
        f=LibretroFrontend.__new__(LibretroFrontend)
        f._content_path=Path(folder)/('game'+suffix);f.save_dir=Path(folder)
        f._sram_loaded_from=None;f._sram_seed_extent=None
        f._buffer=(ctypes.c_ubyte*size)(*([fill]*size))
        f.lib=SimpleNamespace(retro_get_memory_size=lambda _:size,retro_get_memory_data=lambda _:ctypes.addressof(f._buffer))
        f.core_info=lambda:SimpleNamespace(library_name=name)
        return f

    def test_refused_seed_survives_frontend_cleanup(self):
        for corrupt_after_load in (False, True):
            with self.subTest(corrupt_after_load=corrupt_after_load),tempfile.TemporaryDirectory() as d:
                f=self.frontend(d,32768,'Other')
                seed=b'S'*(32768 if corrupt_after_load else 65536)
                path=Path(d)/'game.srm';path.write_bytes(seed)
                f._loaded=True;f._initialized=True;f._audio_capture=MagicMock()
                f.lib.retro_unload_game=MagicMock();f.lib.retro_deinit=MagicMock()
                try:
                    if corrupt_after_load:
                        f._load_save_ram();f._buffer[0]^=1
                        with self.assertRaises(ValueError):f.verify_save_seed(seed)
                    else:
                        with self.assertRaises(ValueError):f._load_save_ram()
                finally:f.close()
                self.assertEqual(path.read_bytes(),seed,'refusal must preserve the original save')
                f.lib.retro_unload_game.assert_called_once();f.lib.retro_deinit.assert_called_once()

    def test_successful_seed_can_still_persist_game_changes(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.frontend(d,8192,'Other');path=Path(d)/'game.srm';path.write_bytes(b'S'*8192)
            f._load_save_ram();f._buffer[0]=71;f._persist_save_ram()
            self.assertEqual(path.read_bytes(),b'G'+b'S'*8191)


    def test_generic_or_unsupported_partial_allocations_are_not_accepted(self):
        for name,suffix,length in [('Other','.gb',32768),('Gambatte','.gb',32768),('Gambatte','.gb',4096)]:
            with self.subTest(name=name,suffix=suffix,length=length),tempfile.TemporaryDirectory() as d:
                f=self.frontend(d,131072,name,suffix);seed=b'S'*length
                (Path(d)/'game.srm').write_bytes(seed)
                with self.assertRaises(ValueError):f._load_save_ram()

    def test_seed_is_never_truncated_and_nonuniform_unused_ram_is_refused(self):
        for size,length,dirty in [(32768,65536,False),(131072,32768,True)]:
            with self.subTest(size=size,length=length),tempfile.TemporaryDirectory() as d:
                f=self.frontend(d,size)
                if dirty:f._buffer[-1]=73
                (Path(d)/'game.srm').write_bytes(b'S'*length)
                with self.assertRaises(ValueError):f._load_save_ram()

    def test_equal_size_seed_uses_exact_whole_region_check(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.frontend(d,8192,'Other','.sfc');seed=b'S'*8192
            (Path(d)/'game.srm').write_bytes(seed);f._load_save_ram()
            self.assertEqual(f.verify_save_seed(seed)['mode'],'exact_region')
            with self.assertRaises(ValueError):f.verify_save_seed(seed[:-1])
