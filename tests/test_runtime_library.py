import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

class LibraryTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.runtime_library'),'local library discovery missing')
        from romancer import runtime_library
        return runtime_library

    def test_bounded_scan_matches_known_names_and_keeps_ambiguous_choices(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cores=root/'cores';cores.mkdir()
            for name in ('fceumm_libretro.dll','fceumm_libretro.so','private.rom'):(cores/name).write_bytes(b'fixture')
            with patch('romancer.runtime_library._binary',return_value={'sha256':'a'*64,'size':7,'binary':'test'}):
                result=service.scan_core_library(root,[str(cores)])
                self.assertEqual(len(result['candidates']),2);self.assertEqual(result['candidates'][0]['systems'],['nes']);self.assertFalse(result['runtime_verified'])
                with self.assertRaises(ValueError):service.scan_core_library(root,[str(cores)]*9)

    def test_wrong_architecture_and_missing_folder_are_reported(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'gambatte_libretro.dll').write_bytes(b'wrong')
            result=service.scan_core_library(root,[str(root),str(root/'missing')])
            self.assertFalse(result['candidates']);self.assertEqual(len(result['issues']),2)

    def test_changed_selected_core_refuses_before_saving(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'gambatte_libretro.dll';path.write_bytes(b'core')
            with patch('romancer.runtime_library._binary',return_value={'sha256':'a'*64,'size':4,'binary':'test'}):selected=service.scan_core_library(root,[str(root)])['candidates'][0]
            with patch('romancer.runtime_library._binary',return_value={'sha256':'b'*64,'size':4,'binary':'test'}):
                with self.assertRaisesRegex(ValueError,'changed'):service.configure_local_core(root,'gb',selected)
            self.assertFalse((root/'runtime-profiles.json').exists())
