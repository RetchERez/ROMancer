from pathlib import Path
import tempfile
import unittest


class AddressTests(unittest.TestCase):
    def test_literal_cartridge_vectors_and_unmapped_regions(self):
        from romancer.system_addresses import translate
        cases=[('nes',0x8000,{'id':'nrom','prg_offset':16,'prg_size':16384},None,24592,16),
               ('nes',0xc001,{'id':'nrom','prg_offset':528,'prg_size':16384},None,25104,529),
               ('snes',0x808000,{'id':'lorom','copier_header':512},None,33280,512),
               ('snes',0xc01234,{'id':'hirom','copier_header':0},None,65536,0x1234),
               ('genesis',0x1234,{'id':'linear'},None,32768,0x1234),
               ('gba',0x0a000123,{'id':'rom'},None,32768,0x123),
               ('segacd',0x200008,{'id':'declared-window','cpu_start':0x200000,'file_offset':43008,'length':32},None,49152,43016)]
        for system,address,mapping,bank,size,want in cases:
            with self.subTest(system=system,address=address):self.assertEqual(translate(system,address,mapping,bank,size)['offset'],want)
        for system,address,mapping,size in [('snes',0x7e8000,{'id':'lorom','copier_header':0},4194304),('snes',0x800010,{'id':'lorom','copier_header':0},4194304),('genesis',0xa10000,{'id':'linear'},32768),('gba',0x07000000,{'id':'rom'},32768)]:
            with self.assertRaises(ValueError):translate(system,address,mapping,None,size)

    def test_explicit_bank_is_required_and_cannot_escape_source(self):
        from romancer.system_addresses import translate
        mapping={'id':'prg-bank','prg_offset':16,'bank_size':8192,'window_start':0x8000,'window_size':8192}
        with self.assertRaises(ValueError):translate('nes',0x8001,mapping,None,32784)
        self.assertEqual(translate('nes',0x8001,mapping,2,32784)['offset'],16401)
        with self.assertRaises(ValueError):translate('nes',0x8001,mapping,4,32784)

    def test_seeded_byte_comparison_names_exact_offsets(self):
        from romancer.system_addresses import compare_bytes
        from romancer import workbench_projects as p
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'own';source.write_bytes(b'0123456789');project=Path(p.create_project(root/'projects','Compare')['path']);row=p.register_source(project,source,None)
            plan=p.plan_byte_edits(project,row['artifact_id'],[{'offset':4,'before':'34','after':'58'}]);build=p.apply_build(project,plan['plan_id'])
            result=compare_bytes(project,row['artifact_id'],build['artifact_id'],2,6)
            self.assertEqual(result['differences'],[{'offset':4,'before':'34','after':'58'}]);self.assertEqual(result['length'],6)
