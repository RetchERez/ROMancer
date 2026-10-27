import unittest


class SourceSymbolTests(unittest.TestCase):
    def module(self):
        from romancer import source_symbols
        return source_symbols

    def test_rgbds_keeps_cpu_ram_separate_from_file_offsets_and_uses_explicit_bank(self):
        result=self.module().parse('00:0100 Entry\n02:4000 Table\n01:d000 wParty\n00:4000 Ambiguous\n','rgbds','gbc',65536)
        by={r['name']:r for r in result['symbols']}
        self.assertEqual(by['Entry']['file_offset'],0x100)
        self.assertEqual(by['Table']['file_offset'],0x8000)
        self.assertIsNone(by['wParty']['file_offset'])
        self.assertIsNone(by['Ambiguous']['file_offset'])
        self.assertFalse(result['rom_match_proven'])

    def test_gnu_nm_maps_gba_rom_data_but_not_ram_or_odd_code_addresses(self):
        result=self.module().parse('08001000 R gSpeciesInfo\n02000000 B gParty\n08001001 T ThumbEntry\n       U Undefined\n','gnu-nm','gba',65536)
        by={r['name']:r for r in result['symbols']}
        self.assertEqual(by['gSpeciesInfo']['file_offset'],4096)
        self.assertIsNone(by['gParty']['file_offset']);self.assertIsNone(by['ThumbEntry']['file_offset'])
        self.assertEqual(result['ignored_lines'],1)
        with self.assertRaises(ValueError):self.module().parse('08000000 R X','gnu-nm','nes',1024)

    def test_import_requires_review_and_source_acknowledgement_and_never_changes_rom(self):
        import tempfile
        from pathlib import Path
        from romancer.workbench_api import WorkbenchAPI
        from romancer.boot_fixtures import make_boot_fixture
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=make_boot_fixture('gba')['data'];rom=root/'original.gba';rom.write_bytes(raw);sym=root/'symbols.txt';sym.write_text('08001000 R gSpeciesInfo\n02000000 B gParty\n')
            api=WorkbenchAPI(root/'work')
            def call(op,**p):
                r=api.dispatch(op,p);self.assertTrue(r['ok'],r);return r
            try:
                p={'project_id':call('project.create',name='Symbols')['project_id']};s=call('source.import',**p,path=str(rom),system=None);sp={**p,'artifact_id':s['artifact_id']}
                item=call('inputs.import',**p,path=str(sym),name=sym.name,kind='symbols')
                preview=call('symbols.preview',**sp,input_id=item['input_id'],format='gnu-nm')
                bad=api.dispatch('symbols.import',{**sp,'input_id':item['input_id'],'format':'gnu-nm','review_id':preview['review_id'],'acknowledged':False});self.assertFalse(bad['ok'])
                call('symbols.import',**sp,input_id=item['input_id'],format='gnu-nm',review_id=preview['review_id'],acknowledged=True)
                found=call('symbols.search',**sp,query='gSpecies',page=0)
                self.assertEqual(found['symbols'][0]['file_offset'],4096)
                stale=api.dispatch('symbols.import',{**sp,'input_id':item['input_id'],'format':'gnu-nm','review_id':preview['review_id'],'acknowledged':True});self.assertFalse(stale['ok'])
                self.assertEqual(rom.read_bytes(),raw)
            finally:api.close()
