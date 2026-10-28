import re
import unittest
from romancer.boot_fixtures import make_boot_fixture


class PopularReferenceTests(unittest.TestCase):
    def library(self):
        from romancer import popular_references
        return popular_references

    def test_popular_game_library_has_pinned_primary_sources_and_no_edit_authority(self):
        result=self.library().catalog('pokemon','all')
        self.assertEqual(len(result['references']),2)
        self.assertFalse(result['write_authorized'])
        for row in result['references']:
            self.assertEqual(row['status'],'DOCUMENTED_REFERENCE')
            self.assertTrue(re.fullmatch('[0-9a-f]{40}',row['commit']))
            self.assertIn(row['commit'],row['url'])
            self.assertFalse(row['rom_revision_verified'])
        mario=self.library().catalog('mario','all')
        self.assertEqual(len(mario['references']),2)
        smb=next(r for r in mario['references'] if r['id']=='smb1')
        lives=next(r for r in smb['addresses'] if r['name']=='Lives counter')
        self.assertEqual((lives['address'],lives['domain']),(0x75a,'cpu_ram'))
        self.assertFalse(lives['rom_file_offset_known'])

    def test_documented_stat_prefixes_are_distinct_and_stride_must_be_declared(self):
        lib=self.library()
        red=lib.table_template('pokemon-red-blue',0,1,28,1024,'gb')
        crystal=lib.table_template('pokemon-crystal',0,1,32,1024,'gbc')
        field=lambda d,n:next(f['offset'] for f in d['fields'] if f['name']==n)
        self.assertEqual((field(red,'HP'),field(crystal,'Sp. attack')),(1,5))
        with self.assertRaises(ValueError):lib.table_template('pokemon-crystal',0,1,9,1024,'gbc')
        with self.assertRaises(ValueError):lib.table_template('pokemon-crystal',0,1,28,1024,'snes')
        with self.assertRaises(ValueError):lib.table_template('pokemon-crystal',1000,2,28,1024,'gbc')

    def test_dispatch_accepts_all_system_reference_filter_without_claiming_a_rom_system(self):
        import tempfile
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as d:
            api=WorkbenchAPI(d)
            try:
                result=api.dispatch('references.catalog',{'query':'pokemon','system_filter':'all'})
                self.assertTrue(result['ok'],result);self.assertEqual(len(result['references']),2)
            finally:api.close()

    def test_checked_template_opens_original_fixture_table_without_saving_or_claiming_pokemon(self):
        import tempfile
        from pathlib import Path
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'original.gbc';raw=bytearray(make_boot_fixture('gbc')['data']);raw[0x1000]=40;path.write_bytes(raw)
            api=WorkbenchAPI(Path(d)/'work')
            try:
                p=api.dispatch('project.create',{'name':'Original layout test'});source=api.dispatch('source.import',{'project_id':p['project_id'],'path':str(path),'system':None})
                sp={'project_id':p['project_id'],'artifact_id':source['artifact_id']}
                result=api.dispatch('references.template',{**sp,'template_id':'pokemon-crystal','offset':0x1000,'count':1,'stride':28})
                self.assertTrue(result['ok'],result);self.assertFalse(result['rom_revision_verified'])
                self.assertEqual(result['inspection']['rows'][0]['cells'][0]['value'],40)
                self.assertNotIn('tables',api.dispatch('project.open',{'project_id':p['project_id']})['sources'][0].get('descriptors',{}))
                self.assertEqual(path.read_bytes(),bytes(raw))
            finally:api.close()
