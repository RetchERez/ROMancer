"""Original synthetic codewords; no publisher archive or game data fixtures."""
import importlib.util
import unittest


class CheatDecodeTests(unittest.TestCase):
    def decode(self,system,code,**kwargs):
        self.assertIsNotNone(importlib.util.find_spec('romancer.cheat_decode'),
                             'the bounded format-only decoder is missing')
        from romancer.cheat_decode import decode_code
        return decode_code(system,code,**kwargs)

    def test_nes_synthetic_bits_and_optional_compare(self):
        cases=[('AAAAAA',0x8000,0,None),('PAAAAA',0x8000,1,None),
               ('EAAAAA',0x8000,128,None),('APAAAA',0x8000,16,None),
               ('AEAAAA',0x8080,0,None),('AAAPAA',0x9000,0,None),
               ('AAAEAA',0x8008,0,None),('AAAAPA',0x8001,0,None),
               ('AAAAEA',0x8800,0,None),('AAAAAP',0x8100,0,None),
               ('AAAAAE',0x8000,8,None),('AAAAAAAA',0x8000,0,0),
               ('AAAAAEAA',0x8000,0,8),('AAAAAAEA',0x8000,0,128),
               ('AAAAAAAP',0x8000,0,16),('AAAAAAAE',0x8000,8,0),
               ('NNNNNNNN',0xffff,255,255)]
        for code,address,value,compare in cases:
            with self.subTest(code=code):
                result=self.decode('nes',code)
                self.assertEqual((result['address'],result['value'],result['compare']),
                                 (address,value,compare))
                self.assertEqual(result['width'],1)

    def test_snes_substitution_and_scattered_address_bits(self):
        cases=[('DDDD-DDDD',0,0),('FDDD-DDDD',0,16),('DFDD-DDDD',0,1),
               ('DDDD-DDDF',0x400,0),('DDDD-DDD4',0x800,0),
               ('DDDD-DDD0',0x10000,0),('DDDD-DDD6',0x20000,0),
               ('DDDD-DDFD',0x40000,0),('DDDD-DD4D',0x80000,0),
               ('DDDD-DD0D',1,0),('DDDD-DD6D',2,0),
               ('DDFD-DDDD',0x1000,0),('DDDD-FDDD',0x400000,0),
               ('DDDF-DDDD',0x10,0),('DDDD-D0DD',0x100000,0),('EEEE-EEEE',0xffffff,255)]
        for code,address,value in cases:
            with self.subTest(code=code):
                result=self.decode('snes',code)
                self.assertEqual((result['address'],result['value'],result['compare']),
                                 (address,value,None))

    def test_genesis_synthetic_word_bits_and_big_endian(self):
        cases=[('AAAA-AAAA',0,0),('BAAA-AAAA',0,8),('ABAA-AAAA',0x4000,0),
               ('AEAA-AAAA',0,1),('AABA-AAAA',0x200,0),('AAAB-AAAA',0x100000,0),
               ('AAAA-BAAA',0,0x1000),('AAAA-CAAA',0x10000,0),
               ('AAAA-ABAA',0,0x8000),('AAAA-ACAA',0,0x100),
               ('AAAA-AABA',0x20,0),('AAAA-AAJA',0,0x2000),
               ('AAAA-AAAB',1,0),('9999-9999',0xffffff,0xffff)]
        for code,address,value in cases:
            with self.subTest(code=code):
                result=self.decode('genesis',code)
                self.assertEqual((result['address'],result['value'],result['width'],result['endian']),
                                 (address,value,2,'big'))
                self.assertIsNone(result['compare'])

    def test_gb_gbc_address_comparison_rotation_and_no_bank_guess(self):
        cases=[('12A-BCF',0xabc,0x12,None),('12A-BC8',0x7abc,0x12,None),
               ('12A-BCF-000',0xabc,0x12,0xba),('12A-BCF-040',0xabc,0x12,0xba),
               ('12A-BCF-004',0xabc,0x12,0xbb),('FFF-FFF-FFF',0xfff,255,0x45)]
        for system in ('gb','gbc'):
            for code,address,value,compare in cases:
                with self.subTest(system=system,code=code):
                    result=self.decode(system,code)
                    self.assertEqual((result['address'],result['value'],result['compare']),
                                     (address,value,compare))
                    self.assertNotIn('rom_offset',result)

    def test_returns_format_evidence_without_runtime_or_mapping_claims(self):
        result=self.decode('GEN',' aaaa-aaaa ')
        self.assertEqual(result['system_id'],'genesis');self.assertEqual(result['code'],'AAAA-AAAA')
        self.assertEqual(result['operation'],'rom-read');self.assertEqual(result['address_space'],'cpu')
        self.assertTrue(result['mapping_required']);self.assertFalse(result['semantic_verified'])
        self.assertTrue(result['reference'].startswith('https://github.com/'))

    def test_rejects_invalid_letters_separators_placeholders_and_unsupported_formats(self):
        cases=[('nes','AAAAAB'),('nes','AAAAA'),('nes','AAAAAAA'),('nes','AAA-AAA'),
               ('snes','00000000'),('snes','DDDDXDDDD'),('snes','DDDD-DDDG'),
               ('genesis','AAAA-AAA'),('genesis','AAAA-IAAA'),('genesis','AAAA-OAAA'),
               ('gb','XA2-538-27F'),('gb','12A-BCF+12A-BCF'),('gb','12A-BCF-00'),
               ('gba','AAAA-AAAA'),('unknown','AAAAAA'),('nes',None),('nes','A'*1024)]
        for system,code in cases:
            with self.subTest(system=system,code=code):
                with self.assertRaises(ValueError):self.decode(system,code)
        with self.assertRaises(ValueError):self.decode('nes','AAAAAA',format='action-replay')


if __name__=='__main__':unittest.main()
