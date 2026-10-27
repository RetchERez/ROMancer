"""Original boundary examples; no game bytes or inferred game semantics."""
import unittest
from pathlib import Path
import tempfile

from romancer.hardware_reference import reference_for,classify_address


class HardwareReferenceTests(unittest.TestCase):
    def test_supported_systems_have_sources_and_separate_address_domains(self):
        for system in ('nes','snes','genesis','gb','gbc','gba','sms'):
            doc=reference_for(system)
            self.assertTrue(doc['references']);self.assertIn('cpu',doc['domains'])
            self.assertFalse(doc['write_authorized'])
            self.assertEqual(set(doc['storage_formats']),{'tiles','palettes','maps'})
            self.assertTrue(all(isinstance(value,str) and value for value in doc['storage_formats'].values()))
        with self.assertRaises(ValueError):reference_for('unsupported')

    def test_sms_documented_windows_are_distinct_from_mapper_and_file_bytes(self):
        self.assertEqual(reference_for('sms')['domains']['vram'],0x3fff)
        for address in (0,0x4000,0xbfff):
            result=classify_address('sms',address);self.assertEqual(result['kind'],'cartridge');self.assertTrue(result['requires_mapping']);self.assertIsNone(result['file_offset'])
        self.assertEqual(classify_address('sms',0xc000)['kind'],'ram')
        self.assertEqual(classify_address('sms',0xe000)['kind'],'ram-mirror')
        self.assertIn('mapper',classify_address('sms',0xffff)['note'])

    def test_gb_bank_window_and_cartridge_storage_are_not_file_offsets(self):
        for system in ('gb','gbc'):
            rom=classify_address(system,0x4567,'cpu')
            self.assertEqual(rom['kind'],'rom-window');self.assertTrue(rom['requires_mapping'])
            self.assertIsNone(rom['file_offset'])
            external=classify_address(system,0xa000,'cpu')
            self.assertEqual(external['kind'],'cartridge');self.assertIn('RTC',external['note'])
        self.assertEqual(classify_address('gb',0xe123,'cpu')['kind'],'ram-mirror')
        self.assertEqual(classify_address('gbc',0xfea0,'cpu')['kind'],'unusable')

    def test_nes_cpu_and_ppu_same_number_mean_different_things(self):
        self.assertEqual(classify_address('nes',0x2007,'cpu')['kind'],'io')
        self.assertEqual(classify_address('nes',0x2007,'ppu')['kind'],'graphics')
        self.assertEqual(classify_address('nes',0x8000,'cpu')['kind'],'rom-window')
        self.assertIsNone(classify_address('nes',0x8000,'cpu')['file_offset'])

    def test_snes_io_mirrors_wram_and_audio_ram_stay_separate(self):
        for address in (0x002140,0x802140,0x002144,0x80217f):
            self.assertEqual(classify_address('snes',address,'cpu')['kind'],'io')
        self.assertEqual(classify_address('snes',0x7e2140,'cpu')['kind'],'ram')
        self.assertEqual(classify_address('snes',0x402140,'cpu')['kind'],'cartridge')
        self.assertEqual(classify_address('snes',0xf4,'apu')['kind'],'io')
        self.assertEqual(classify_address('snes',0x2100,'vram')['kind'],'graphics')

    def test_genesis_bus_and_big_endian_words(self):
        self.assertEqual(reference_for('genesis')['endian'],'big')
        self.assertEqual(classify_address('genesis',0xa00000,'cpu')['kind'],'coprocessor-window')
        self.assertEqual(classify_address('genesis',0xc00004,'cpu')['kind'],'io')
        self.assertEqual(classify_address('genesis',0xff0000,'cpu')['kind'],'ram')
        self.assertEqual(classify_address('genesis',0x100,'cpu')['kind'],'rom-window')

    def test_gba_rom_mirrors_video_io_and_saves_are_distinct(self):
        for address in (0x08000000,0x0a000000,0x0c000000):
            self.assertEqual(classify_address('gba',address,'cpu')['kind'],'rom-window')
        self.assertEqual(classify_address('gba',0x06000000,'cpu')['kind'],'graphics')
        self.assertEqual(classify_address('gba',0x04000000,'cpu')['kind'],'io')
        self.assertEqual(classify_address('gba',0x0e000000,'cpu')['kind'],'cartridge')
        for address in (0x02040000,0x03008000):self.assertEqual(classify_address('gba',address,'cpu')['kind'],'ram-mirror')
        for address in (0x05000400,0x06018000,0x07000400):self.assertEqual(classify_address('gba',address,'cpu')['kind'],'graphics')

    def test_strict_system_domain_address_bounds_and_no_write_authority(self):
        for args in (('nes',65536,'cpu'),('gb',-1,'cpu'),('snes',True,'cpu'),('gba',0,'ppu'),('gb',0,'file')):
            with self.subTest(args=args),self.assertRaises(ValueError):classify_address(*args)
        for system in ('nes','snes','genesis','gb','gbc','gba'):
            doc=classify_address(system,0,'cpu')
            self.assertFalse(doc['write_authorized']);self.assertFalse(doc['game_semantics_verified'])

    def test_read_only_api_and_ai_tools_publish_hardware_context(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.mcp_server import READ_OPERATIONS,_schema
        with tempfile.TemporaryDirectory() as tmp:
            api=WorkbenchAPI(Path(tmp));self.addCleanup(api.close)
            doc=api.dispatch('systems.classify_address',{'system_id':'nes','address':0x2007,'domain':'cpu'})
            self.assertTrue(doc['ok']);self.assertEqual(doc['kind'],'io');self.assertIsNone(doc['file_offset'])
            self.assertTrue(api.dispatch('systems.reference',{'system_id':'sms'})['ok'])
            self.assertIn('systems.classify_address',READ_OPERATIONS);self.assertIn('systems.reference',READ_OPERATIONS)
            schema=_schema(['system_id','address','domain'],'systems.classify_address')
            self.assertEqual(schema['properties']['address']['type'],'integer')
            self.assertIn('sms',schema['properties']['system_id']['enum'])


if __name__=='__main__':unittest.main()
