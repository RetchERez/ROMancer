from pathlib import Path
import tempfile
import unittest
from romancer.boot_fixtures import make_boot_fixture
from romancer.workbench_api import WorkbenchAPI


class StructureToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.api=WorkbenchAPI(self.root/'workspace');self.addCleanup(self.api.close)
        s=self.api.dispatch('settings.get',{});self.api.dispatch('settings.save',{'revision':s['revision'],'values':{**s['values'],'autoDeepScan':False}})
        p=self.api.dispatch('project.create',{'name':'Unfamiliar cartridge'})
        raw=bytearray(make_boot_fixture('nes')['data']);raw[0x1000:0x1080]=b'\xff'*128
        for i,target in enumerate((0x1500,0x1510,0x1520,0x1530)):
            raw[0x1001+i*4:0x1003+i*4]=target.to_bytes(2,'little')
        self.source=self.root/'original.nes';self.source.write_bytes(raw)
        a=self.api.dispatch('source.import',{'project_id':p['project_id'],'path':str(self.source),'system':None})
        self.p={'project_id':p['project_id'],'artifact_id':a['artifact_id']};self.sha=a['sha256']

    def test_neutral_editor_is_derived_again_from_exact_source_bytes(self):
        result=self.api.dispatch('structures.survey',{**self.p,'offset':0x1000,'length':128})
        self.assertTrue(result['ok'],result)
        c=next(c for c in result['candidates'] if c['offset']==0x1001 and c['width']==2 and c['stride']==4 and c['endian']=='little')
        params={**self.p,'offset':0x1000,'length':128,'candidate_id':c['candidate_id'],'interpretation':'numeric'}
        opened=self.api.dispatch('structures.definition',params)
        self.assertTrue(opened['ok'],opened);self.assertFalse(opened['game_semantics_verified'])
        self.assertEqual(opened['inspection']['rows'][0]['cells'][0]['value'],0x1500)
        self.assertIsNone(opened['definition']['fields'][0]['pointer_base'])
        self.assertEqual(opened['source_sha256'],self.sha)
        self.assertFalse(self.api.dispatch('structures.definition',{**params,'candidate_id':'a'*64})['ok'])
        self.assertFalse(self.api.dispatch('structures.survey',{**self.p,'offset':0,'length':65537})['ok'])
        self.assertFalse(self.api.dispatch('structures.definition',{**params,'candidate':c})['ok'])
        self.assertEqual(self.source.read_bytes(),Path(self.api.source(self.p)[1]['path']).read_bytes())
        from romancer.mcp_server import READ_OPERATIONS,_investigation_properties
        self.assertTrue({'structures.survey','structures.definition'}<=READ_OPERATIONS)
        self.assertIn('candidate_id',_investigation_properties('structures.definition'))

    def test_deep_scan_includes_bounded_universal_structure_experiments(self):
        result=self.api.dispatch('rom.scan.run',self.p)
        self.assertTrue(result['ok'],result);lab=result['structural_lab']
        self.assertEqual(lab['source_sha256'],self.sha);self.assertFalse(lab['dereference_observed'])
        self.assertTrue(lab['coverage']);self.assertLessEqual(len(lab['candidates']),32)
        self.assertEqual(lab['coverage'][0]['length'],4096)
