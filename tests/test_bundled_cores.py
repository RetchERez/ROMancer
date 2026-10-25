"""Bundled engines are pinned inputs, never an implicit download or arbitrary DLL."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_runtime_profiles import fake_core


class BundledCoreTests(unittest.TestCase):
    def test_missing_pack_is_optional_for_source_installations(self):
        from romancer.bundled_cores import bundled_profile
        with tempfile.TemporaryDirectory() as temp:
            with patch('romancer.bundled_cores.pack_root',return_value=Path(temp)/'absent'):
                self.assertIsNone(bundled_profile('nes'))

    def test_all_five_defaults_are_verified_and_saved_choices_take_precedence(self):
        from romancer.bundled_cores import bundled_profile,core_members
        from romancer.runtime_profiles import load_profile,save_profile,validate_profile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pack=root/'cores';pack.mkdir();pins={};files={}
            for system in ('nes','snes','genesis','gb','gba'):
                name=system+'.dll';fake_core(pack/name)
                pins[system]={'name':'Test '+system,'file':name,'sha256':hashlib.sha256((pack/name).read_bytes()).hexdigest(),'options':{}}
            (pack/'CORE-SOURCES.zip').write_bytes(b'original source fixture')
            (pack/'THIRD_PARTY_NOTICES.txt').write_text('Test licenses retained')
            for p in pack.iterdir():files[p.name]={'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            with patch('romancer.bundled_cores.CORE_PINS',pins),patch('romancer.bundled_cores.CORE_FILES',files),patch('romancer.bundled_cores.pack_root',return_value=pack),patch('romancer.bundled_cores.host_supported',return_value=True):
                self.assertEqual(set(core_members(pack)),set(files))
                for system in pins:
                    found=load_profile(root/'workspace',system)
                    self.assertEqual(found['status'],'BUNDLED');self.assertFalse(found['runtime_verified'])
                    self.assertEqual(found['engine'],pins[system]['name'])
                    self.assertTrue(validate_profile(found['profile'])['ok'])
                custom=root/'custom.dll';fake_core(custom)
                saved=save_profile(root/'workspace','nes',str(custom),{},None,{'a':'z'})['profile']
                self.assertEqual(load_profile(root/'workspace','nes')['profile'],saved)
                (pack/'nes.dll').write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError,'identity'):bundled_profile('nes')
                self.assertEqual(load_profile(root/'workspace','nes')['profile'],saved)

    def test_missing_sources_and_unlisted_files_refuse_distribution(self):
        from romancer.bundled_cores import core_members
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'engine.dll').write_bytes(b'engine')
            pins={'engine.dll':{'size':6,'sha256':hashlib.sha256(b'engine').hexdigest()},'CORE-SOURCES.zip':{'size':1,'sha256':hashlib.sha256(b's').hexdigest()}}
            with patch('romancer.bundled_cores.CORE_FILES',pins):
                with self.assertRaisesRegex(ValueError,'missing'):core_members(root)
                (root/'CORE-SOURCES.zip').write_bytes(b's');(root/'private.rom').write_bytes(b'private')
                with self.assertRaisesRegex(ValueError,'unlisted'):core_members(root)


if __name__=='__main__':unittest.main()
