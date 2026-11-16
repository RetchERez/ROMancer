"""Bundled engines are pinned inputs, never an implicit download or arbitrary DLL."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_runtime_profiles import fake_core


class BundledCoreTests(unittest.TestCase):
    def test_exact_compatibility_profiles_leave_other_roms_on_their_defaults(self):
        from romancer.bundled_cores import cartridge_engine

        pilotwings = '03d0127f5de3237e22ad00de0c20763274da7b71142dde693240ac96d10983a3'
        target_earth = '3fdb9dd4e1c98760ec2c57af08f1c172a9f964a695c3f07e8a28c4eb5819082d'
        kirby = '6cf412aeb1ec60da1a401019d95dee1e76f0297154a7f06b55fb1657a71ed44f'
        self.assertEqual(cartridge_engine('snes', pilotwings),
                         ('snes', {'bsnes_violate_accuracy':'enabled', 'bsnes_chip_hle':'HLE'}))
        top_gear = '6be49983976564f1fd9eff2f14f5bb41d3a0ff48573e39318088ecce286aca62'
        self.assertEqual(cartridge_engine('snes', top_gear),
                         ('snes-dsp4', {'bsnes_violate_accuracy':'enabled', 'bsnes_chip_hle':'HLE'}))
        self.assertEqual(cartridge_engine('snes', '0'*64), ('snes', {}))
        self.assertEqual(cartridge_engine('genesis', target_earth), ('genesis', {'blastem_system_type':'gen'}))
        self.assertEqual(cartridge_engine('gbc', kirby), ('gbc-tilt', {'romancer_mbc7_tilt':'dpad-v1'}))
        self.assertEqual(cartridge_engine('gbc', '0'*64), ('gb', {}))
        self.assertEqual(cartridge_engine('gb', kirby), ('gb', {}))

    def test_mbc7_sensor_uses_direction_or_neutral_without_touching_joypad(self):
        from romancer.libretro_frontend import LibretroFrontend

        frontend = LibretroFrontend.__new__(LibretroFrontend)
        frontend._joypads = {0: frontend.buttons_to_mask(['right','up','a'])}
        frontend._accelerometer_enabled = False
        self.assertEqual(frontend._sensor_input(0, 0), 0.0)
        self.assertTrue(frontend._set_sensor_state(0, 0, 60))
        self.assertGreater(frontend._sensor_input(0, 0), 0.0)
        self.assertLess(frontend._sensor_input(0, 1), 0.0)
        self.assertEqual(frontend._sensor_input(1, 0), 0.0)
        frontend._joypads[0] = frontend.buttons_to_mask(['right','left'])
        self.assertEqual(frontend._sensor_input(0, 0), 0.0)
        self.assertFalse(frontend._set_sensor_state(0, 4, 60))
    def test_packaged_frontend_refuses_unreviewed_core_before_loading_native_code(self):
        from romancer.bundled_cores import require_reviewed_release_core
        from romancer.libretro_frontend import LibretroFrontend
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'unknown.dll';core.write_bytes(b'unreviewed native code')
            with patch('romancer.bundled_cores.packaged_release',return_value=True):
                with self.assertRaisesRegex(ValueError,'reviewed open-source'):require_reviewed_release_core(core)
                with patch('romancer.libretro_frontend.ctypes.CDLL') as load:
                    with self.assertRaisesRegex(ValueError,'reviewed open-source'):LibretroFrontend(core,save_dir=root/'runtime')
                    load.assert_not_called();self.assertFalse((root/'runtime').exists())
                with patch('romancer.bundled_cores.CORE_PINS',{'test':{'name':'Reviewed test','license':'MIT','source_url':'https://example.invalid/source','source_commit':'a'*40,'sha256':hashlib.sha256(core.read_bytes()).hexdigest()}}):
                    self.assertEqual(require_reviewed_release_core(core)['name'],'Reviewed test')
            with patch('romancer.bundled_cores.packaged_release',return_value=False):
                self.assertIsNone(require_reviewed_release_core(core),'Source development retains native test fixtures; release playback is pinned.')

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
            for system in ('nes','snes','genesis','gb'):
                name=system+'.dll';fake_core(pack/name)
                pins[system]={'name':'Test '+system,'file':name,'sha256':hashlib.sha256((pack/name).read_bytes()).hexdigest(),'options':{},'license':'MIT','source_url':'https://example.invalid/original-test-fixture','source_commit':'a'*40}
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
                sms=load_profile(root/'workspace','sms');self.assertEqual(sms['engine'],pins['genesis']['name']);self.assertEqual(sms['profile']['options']['blastem_io_1'],'gamepad2.1')
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
