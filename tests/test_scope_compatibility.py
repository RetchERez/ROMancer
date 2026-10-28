"""Existing projects retain their supported resources after a scope change."""
import json,tempfile,unittest
from pathlib import Path
from romancer.boot_fixtures import make_boot_fixture
from romancer.workbench_api import WorkbenchAPI
from romancer.resource_compression import encode_stream
from romancer import workbench_projects as projects

class ScopeCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.api=WorkbenchAPI(self.root/'work');self.addCleanup(self.api.close)
        settings=self.api.dispatch('settings.get',{})
        self.api.dispatch('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
    def call(self,op,p):
        result=self.api.dispatch(op,p);self.assertTrue(result['ok'],result);return result
    def source(self,raw):
        path=self.root/'original.nes';path.write_bytes(raw)
        project=self.call('project.create',{'name':'Existing project'})
        p={'project_id':project['project_id']}
        parent=self.call('source.import',{**p,'path':str(path),'system':None})
        return project,p,parent
    def test_legacy_generic_codec_children_can_edit_and_reinsert_with_neutral_output(self):
        for codec in ('rle','lz10'):
            with self.subTest(codec=codec):
                raw=bytearray(make_boot_fixture('nes')['data']);stream=encode_stream(b'AAAAABCD',codec)
                raw[0x500:0x500+len(stream)]=stream
                project,p,parent=self.source(raw)
                args={**p,'artifact_id':parent['artifact_id'],'offset':0x500,'allocation':32,'codec':codec}
                child=self.call('compression.extract',args)['artifact']
                stored=Path(project['path'])/'project.json';value=json.loads(stored.read_text())
                next(r for r in value['sources'] if r['artifact_id']==child['artifact_id'])['compressed_parent']['codec']='gba-'+codec
                projects.write_json(stored,value)
                plan=self.call('bytes.plan',{**p,'artifact_id':child['artifact_id'],'edits':[{'offset':5,'before':'42','after':'5a'}]})
                edited=self.call('build.apply',{**p,'plan_id':plan['plan_id']})
                reinsert={**p,'parent_id':parent['artifact_id'],'decoded_id':child['artifact_id'],'edited_id':edited['artifact_id'],'offset':0x500,'allocation':32,'codec':codec}
                preview=self.call('compression.preview_reinsert',reinsert);self.assertEqual(preview['codec'],codec)
                planned=self.call('compression.plan_reinsert',reinsert)
                built=self.call('build.apply',{**p,'plan_id':planned['plan_id']})
                from romancer.compression_oracle import verify_encoded
                packed=Path(built['path']).read_bytes()[0x500:0x500+preview['packed_size']]
                self.assertTrue(verify_encoded(packed,codec,b'AAAAAZCD')['verified'])
                self.assertEqual(Path(parent['path']).read_bytes(),raw)
                self.assertEqual(json.loads(stored.read_text())['sources'][1]['compressed_parent']['codec'],'gba-'+codec)
    def test_mixed_legacy_project_keeps_supported_overview_and_blocks_removed_edits(self):
        project,p,parent=self.source(make_boot_fixture('nes')['data'])
        extra=projects.register_source(Path(project['path']),Path(parent['path']),None)
        value=projects.read_project(Path(project['path']))
        next(r for r in value['sources'] if r['artifact_id']==extra['artifact_id'])['system_id']='gba'
        projects.write_json(Path(project['path'])/'project.json',value)
        self.assertTrue(self.call('project.readiness',p)['steps'])
        blocked=self.api.dispatch('bytes.plan',{**p,'artifact_id':extra['artifact_id'],'edits':[{'offset':0x500,'before':'00','after':'01'}]})
        self.assertFalse(blocked['ok']);self.assertIn('Inspect',blocked['error'])
