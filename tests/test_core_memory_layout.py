import importlib.util
import unittest
from romancer.core_pins import CORE_PINS


class CoreMemoryLayoutTests(unittest.TestCase):
    def resolve(self,system,offset,width=1,**overrides):
        self.assertIsNotNone(importlib.util.find_spec('romancer.core_memory_layout'),'owned core-buffer mapping is missing')
        from romancer.core_memory_layout import memory_probe
        packet={'core_sha256':CORE_PINS['gb' if system=='gbc' else system]['sha256'],'region':2,'region_size':{'nes':2048,'snes':131072,'genesis':65536,'gb':8192,'gbc':32768,'gba':32768}[system],**overrides}
        return memory_probe(system,packet,offset,width)

    def test_unbanked_exposed_ram_addresses_follow_pinned_core_layouts(self):
        for system,offset,address in [('nes',16,16),('snes',0x12345,0x7f2345),('gba',0x1234,0x02001234),('gb',0x234,0xc234)]:
            with self.subTest(system=system):
                r=self.resolve(system,offset,2);self.assertEqual(r['cpu_addresses'],[address,address+1])
                self.assertFalse(r['active_bank_observed']);self.assertEqual(r['evidence'],'pinned_core_interface_and_hardware_mapping')

    def test_gbc_physical_bank_is_a_required_observation_not_a_guessed_active_bank(self):
        r=self.resolve('gbc',0x2123,2)
        self.assertEqual(r['cpu_addresses'],[0xd123,0xd124]);self.assertEqual(r['physical_offsets'],[0x2123,0x2124])
        self.assertTrue(r['requires_observed_bank']);self.assertFalse(r['active_bank_observed'])

    def test_blastem_host_little_endian_word_buffer_is_not_cpu_byte_order(self):
        byte=self.resolve('genesis',0x100)
        self.assertEqual(byte['cpu_addresses'],[0xff0101])
        word=self.resolve('genesis',0x100,2)
        self.assertEqual(word['cpu_addresses'],[0xff0101,0xff0100]);self.assertEqual(word['probe'],{'kind':'write','start':0xff0100,'end':0xff0101})

    def test_unknown_core_unexposed_region_or_out_of_range_never_guesses(self):
        for kwargs in [{'core_sha256':'0'*64},{'region':0},{'region_size':999999}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.resolve('nes',16,**kwargs)
        with self.assertRaises(ValueError):self.resolve('gb',8192)
        with self.assertRaises(ValueError):self.resolve('gba',32767,2)
