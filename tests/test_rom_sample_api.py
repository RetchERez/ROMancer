import hashlib,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from romancer.boot_fixtures import make_boot_fixture
from romancer.workbench_api import WorkbenchAPI

class RomSampleAPITests(unittest.TestCase):
    def test_database_is_used_by_real_checks_scans_and_read_only_ai_discovery(self):
        from romancer import rom_sample_db,rom_archive_scan
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=make_boot_fixture('nes')['data'];archive=root/'source.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('Measured Example.nes',raw)
            rom_archive_scan.scan_archives([archive],root/'facts.json',root/'report.json',jobs=1)
            api=WorkbenchAPI(root/'work')
            try:
                with patch.object(rom_sample_db,'DATABASE_PATH',root/'facts.json'):
                    p=api.dispatch('project.create',{'name':'Measured source'});source=root/'original.nes';source.write_bytes(raw)
                    selected=api.dispatch('source.import',{'project_id':p['project_id'],'path':str(source),'system':None});self.assertTrue(selected['ok'],selected)
                    args={'project_id':p['project_id'],'artifact_id':selected['artifact_id']}
                    listed=api.dispatch('rom.samples',{'query':'Measured','system_filter':'all','page':0,'limit':20})
                    self.assertTrue(listed['ok'],listed);self.assertEqual(listed['total'],1);self.assertFalse(listed['write_authorized'])
                    scan=api.dispatch('rom.scan.run',args);self.assertTrue(scan['ok'],scan)
                    sample=scan['recorded_facts'];self.assertEqual(sample['status'],'RECORDED_SAMPLE');self.assertFalse(sample['canonical_revision_verified'])
                    checked=api.dispatch('rom.check',{**args,'expected_crc32':'','crc_scope':'file'})
                    self.assertEqual(checked['recorded_facts']['record']['sha256'],hashlib.sha256(raw).hexdigest())
                    self.assertEqual(api.dispatch('games.inspect',args)['status'],'UNSUPPORTED','A sample match does not invent a game-specific editor.')
                    plan=api.dispatch('bytes.plan',{**args,'edits':[{'offset':0x3000,'before':'00','after':'01'}]});self.assertTrue(plan['ok'],plan)
                    built=api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']});self.assertTrue(built['ok'],built)
                    changed=api.dispatch('rom.check',{**args,'artifact_id':built['artifact_id'],'expected_crc32':'','crc_scope':'file'})
                    self.assertEqual(changed['recorded_facts']['status'],'NOT_RECORDED')
                    from romancer.mcp_server import READ_OPERATIONS,_investigation_properties
                    self.assertIn('rom.samples',READ_OPERATIONS);self.assertIn('system_filter',_investigation_properties('rom.samples'))
            finally:api.close()
