"""Original startup words/vectors; no commercial assets or manufacturer logos."""
import copy
import struct
import unittest


def candidate(system, format, *, header=0, metadata=None, regions=None):
    return {'system_id': system, 'format': format, 'header_offset': header,
            'layout_valid': True, 'metadata': metadata or {}, 'regions': regions or []}


def nes(mapper=0, size=16384, trainer=False):
    start = 16+(512 if trainer else 0)
    raw = bytearray(start+size+8192)
    raw[:4] = b'NES\x1a'
    raw[4:8] = bytes((size//16384, 1, (mapper << 4) | (4 if trainer else 0), 0))
    for i, value in enumerate((0xc100, 0xc200, 0xc300)):
        struct.pack_into('<H', raw, start+size-6+i*2, value)
    return raw, candidate('nes', 'ines', metadata={'mapper': mapper, 'trainer_present': trainer,
        'prg_rom_bytes': size}, regions=[{'id':'prg-rom', 'offset':start, 'length':size}])


def snes(format='lorom', prefix=0):
    raw = bytearray(prefix+65536)
    h = prefix+(0x7fc0 if format=='lorom' else 0xffc0)
    raw[h+21] = 0x20 if format=='lorom' else 0x21
    struct.pack_into('<H', raw, h+0x3c, 0x8234)
    return raw, candidate('snes', format, header=h,
        metadata={'copier_header_bytes':prefix, 'map_mode':raw[h+21]})


def genesis():
    raw = bytearray(4096)
    struct.pack_into('>II', raw, 0, 0x00ffff00, 0x00000200)
    return raw, candidate('genesis', 'genesis-linear', header=0x100,
                          metadata={'rom_start':0, 'rom_end':len(raw)-1})


def gb(system='gb', cart_type=0):
    raw = bytearray(32768)
    raw[0x100:0x104] = bytes((0, 0xc3, 0x80, 1))
    raw[0x147] = cart_type
    return raw, candidate(system, 'gbc-cartridge' if system=='gbc' else 'gb-cartridge',
                          header=0x100, metadata={'cartridge_type':cart_type})


def gba(destination=0x100):
    raw = bytearray(4096)
    displacement = (destination-8)//4
    struct.pack_into('<I', raw, 0, 0xea000000 | (displacement & 0xffffff))
    return raw, candidate('gba', 'gba-linear')


class CartridgeStartupTests(unittest.TestCase):
    def setUp(self):
        from romancer.cartridge_startup import inspect_startup
        self.inspect = inspect_startup

    def check_named(self, raw, cart, name):
        return next(c for c in self.inspect(raw,cart) if c['name']==name)

    def test_nrom16_vectors_and_mirror_targets_ignore_chr_and_trailing_bytes(self):
        raw, cart = nes()
        checks = self.inspect(raw, cart)
        self.assertEqual([c['status'] for c in checks], ['PASS']*3)
        reset = self.check_named(raw,cart,'NES reset vector')
        self.assertEqual(reset['value'],0xc200)
        self.assertEqual(reset['locations'][0]['offset'],16+16384-4)
        self.assertEqual(reset['locations'][1]['offset'],16+0x200)

    def test_nrom32_and_trainer_move_only_file_locations(self):
        raw, cart = nes(size=32768,trainer=True)
        reset = self.check_named(raw,cart,'NES reset vector')
        self.assertEqual(reset['locations'][0]['offset'],528+32768-4)
        self.assertEqual(reset['locations'][1]['offset'],528+0x4200)
        self.assertEqual(reset['cpu_address'],0xc200)

    def test_uxrom_fixed_bank_mapping_and_switched_bank_abstention(self):
        raw,cart=nes(mapper=2,size=131072)
        reset=self.check_named(raw,cart,'NES reset vector')
        self.assertEqual(reset['status'],'PASS')
        self.assertEqual(reset['locations'][1]['offset'],16+131072-16384+0x200)
        struct.pack_into('<H',raw,16+131072-4,0x8100)
        reset=self.check_named(raw,cart,'NES reset vector')
        self.assertEqual(reset['status'],'NOT_CHECKED')
        self.assertEqual(len(reset['locations']),1)

    def test_unknown_nes_mapper_does_not_read_assumed_last_vectors(self):
        raw,cart=nes(mapper=4,size=32768)
        checks=self.inspect(raw,cart)
        self.assertTrue(checks)
        self.assertTrue(all(c['status']=='NOT_CHECKED' and not c['locations'] for c in checks))

    def test_unknown_nes2_submapper_does_not_inherit_a_standard_mapping(self):
        raw,cart=nes(mapper=2,size=32768)
        cart['format']='nes2';cart['metadata']['submapper']=15
        self.assertTrue(all(c['status']=='NOT_CHECKED' and not c['locations']
                            for c in self.inspect(raw,cart)))

    def test_unsupported_nrom_capacity_and_truncated_prg_abstain(self):
        raw,cart=nes(size=49152)
        self.assertEqual(self.inspect(raw,cart)[0]['status'],'NOT_CHECKED')
        raw,cart=nes()
        self.assertTrue(all(c['status']!='PASS' for c in self.inspect(raw[:100],cart)))

    def test_nes_vector_to_ram_is_warning_not_corruption_claim(self):
        raw,cart=nes()
        struct.pack_into('<H',raw,16+16384-4,0x200)
        self.assertEqual(self.check_named(raw,cart,'NES reset vector')['status'],'WARN')

    def test_snes_lorom_hirom_and_copier_header_target_mapping(self):
        for format in ('lorom','hirom'):
            for prefix in (0,512):
                with self.subTest(format=format,prefix=prefix):
                    raw,cart=snes(format,prefix)
                    c=self.check_named(raw,cart,'SNES reset vector')
                    self.assertEqual(c['status'],'PASS')
                    self.assertEqual(c['locations'][0]['offset'],cart['header_offset']+0x3c)
                    self.assertEqual(c['locations'][1]['offset'],prefix+(0x234 if format=='lorom' else 0x8234))

    def test_snes_special_mapping_or_coprocessor_is_unresolved(self):
        raw,cart=snes()
        cart['format']='exhirom-candidate'
        self.assertEqual(self.inspect(raw,cart)[0]['status'],'NOT_CHECKED')
        raw,cart=snes()
        raw[cart['header_offset']+22]=0x13
        self.assertEqual(self.inspect(raw,cart)[0]['status'],'NOT_CHECKED')

    def test_snes_vector_below_supported_rom_window_is_warning(self):
        raw,cart=snes()
        struct.pack_into('<H',raw,cart['header_offset']+0x3c,0x7e00)
        self.assertEqual(self.inspect(raw,cart)[0]['status'],'WARN')

    def test_genesis_big_endian_vectors_and_work_ram_mirrors(self):
        for ssp in (0x00ffff00,0x00e00100,0xfffffe00):
            raw,cart=genesis()
            struct.pack_into('>I',raw,0,ssp)
            stack=self.check_named(raw,cart,'Genesis initial stack pointer')
            self.assertEqual(stack['status'],'PASS')
            self.assertEqual(stack['value'],ssp)
            reset=self.check_named(raw,cart,'Genesis reset vector')
            self.assertEqual(reset['locations'][1]['offset'],0x200)

    def test_odd_68000_reset_pc_fails_alignment_only(self):
        raw,cart=genesis()
        struct.pack_into('>I',raw,4,0x201)
        reset=self.check_named(raw,cart,'Genesis reset vector')
        self.assertEqual(reset['status'],'FAIL')
        self.assertIn('align',reset['detail'].lower())

    def test_genesis_outside_dump_or_mapping_is_warning_including_small_rom_mirrors(self):
        for pc in (0x200000,0xe00100):
            raw,cart=genesis()
            struct.pack_into('>I',raw,4,pc)
            reset=self.check_named(raw,cart,'Genesis reset vector')
            self.assertEqual(reset['status'],'WARN')
            self.assertEqual(len(reset['locations']),1)

    def test_genesis_sp_outside_ram_or_odd_is_warning(self):
        for ssp in (0x100,0x00ffff01):
            raw,cart=genesis()
            struct.pack_into('>I',raw,0,ssp)
            self.assertEqual(self.check_named(raw,cart,'Genesis initial stack pointer')['status'],'WARN')

    def test_gb_optional_nop_absolute_jump_and_fixed_target(self):
        for system in ('gb','gbc'):
            raw,cart=gb(system,0x1b)
            branch=self.check_named(raw,cart,'Game Boy entry branch')
            target=self.check_named(raw,cart,'Game Boy entry target')
            self.assertEqual(branch['status'],'PASS')
            self.assertEqual(branch['cpu_address'],0x180)
            self.assertEqual(target['status'],'PASS')
            self.assertEqual(target['locations'][-1]['offset'],0x180)

    def test_gb_direct_jp_and_signed_jr_use_correct_instruction_pc(self):
        raw,cart=gb()
        raw[0x100:0x103]=bytes((0xc3,0x80,1))
        self.assertEqual(self.inspect(raw,cart)[0]['value'],0x180)
        raw[0x100:0x103]=bytes((0,0x18,0x80))
        self.assertEqual(self.inspect(raw,cart)[0]['value'],0x83)

    def test_mbc1_target_mapping_is_explicitly_unobserved(self):
        raw,cart=gb(cart_type=3)
        self.assertEqual(self.check_named(raw,cart,'Game Boy entry branch')['status'],'PASS')
        target=self.check_named(raw,cart,'Game Boy entry target')
        self.assertEqual(target['status'],'NOT_CHECKED')
        self.assertFalse(any(l['label']=='Entry target byte' for l in target['locations']))

    def test_gb_switched_target_unknown_controller_and_unknown_opcode_abstain(self):
        for cart_type,target in ((0x1b,0x4567),(0xff,0x180)):
            raw,cart=gb(cart_type=cart_type)
            struct.pack_into('<H',raw,0x102,target)
            self.assertEqual(self.check_named(raw,cart,'Game Boy entry target')['status'],'NOT_CHECKED')
        raw,cart=gb()
        raw[0x100:0x104]=bytes((0x31,0,0,0))
        self.assertEqual(self.inspect(raw,cart)[0]['status'],'NOT_CHECKED')

    def test_gba_arm_branch_signed_displacement_and_pc_pipeline(self):
        for destination in (0x100,4):
            raw,cart=gba(destination)
            c=self.inspect(raw,cart)[0]
            self.assertEqual(c['status'],'PASS')
            self.assertEqual(c['value'],0x08000000+destination)
            self.assertEqual(c['locations'][1]['offset'],destination)

    def test_gba_entry_unknown_conditional_bl_or_truncated_is_not_checked(self):
        for word in (0xe12fff1e,0xeb000010,0x0a000010):
            raw,cart=gba()
            struct.pack_into('<I',raw,0,word)
            self.assertEqual(self.inspect(raw,cart)[0]['status'],'NOT_CHECKED')
        raw,cart=gba()
        self.assertEqual(self.inspect(raw[:3],cart)[0]['status'],'NOT_CHECKED')

    def test_gba_outside_image_and_self_branch_are_warnings(self):
        for destination in (0x2000,-4,0):
            raw,cart=gba(destination)
            self.assertEqual(self.inspect(raw,cart)[0]['status'],'WARN')

    def test_untrusted_candidate_and_system_cannot_assert_a_check(self):
        raw,cart=nes()
        cart['layout_valid']=False
        self.assertTrue(all(c['status']=='NOT_CHECKED' for c in self.inspect(raw,cart)))
        self.assertEqual(self.inspect(raw,candidate('sms','raw'))[0]['status'],'NOT_CHECKED')

    def test_output_locations_are_bounded_and_input_is_preserved(self):
        for factory in (nes,snes,genesis,gb,gba):
            raw,cart=factory();before=bytes(raw);original=copy.deepcopy(cart)
            checks=self.inspect(raw,cart)
            for c in checks:
                self.assertIn(c['status'],('PASS','WARN','NOT_CHECKED','FAIL'))
                self.assertTrue(c['name']);self.assertTrue(c['detail'])
                for l in c['locations']:
                    self.assertGreaterEqual(l['offset'],0)
                    self.assertLessEqual(l['offset']+l['length'],len(raw))
                    self.assertTrue(l['label'])
            self.assertEqual(bytes(raw),before);self.assertEqual(cart,original)


if __name__=='__main__':
    unittest.main()
