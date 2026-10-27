from pathlib import Path
import base64,hashlib,tempfile,unittest
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI
from romancer.workbench_evidence import store_evidence,quarantine_restored_evidence
from romancer.replay_journal import execution_context

def frame(rgb):return {'width':8,'height':8,'index':10,'sha256':hashlib.sha256(rgb).hexdigest(),'rgb24_base64':base64.b64encode(rgb).decode()}

class DraftSceneTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()));self.api=WorkbenchAPI(self.root/'work');self.addCleanup(self.api.close)
        p=self.api.dispatch('project.studio',{});self.source=p['sources'][0];self.sp={'project_id':p['project_id'],'artifact_id':self.source['artifact_id']};self.schema=self.source['descriptors']['assets']
        self.doc=self.api.dispatch('assets.inspect',{**self.sp,'schema':self.schema});bitmap=self.doc['bitmaps'][0];before=bitmap['cells'][0]['pixels'];after=[*before];after[0]=1 if not before[0] else 0
        self.edits={'schema_version':1,'document_id':self.doc['document_id'],'changes':[{'kind':'cell','bitmap_id':bitmap['id'],'cell_index':0,'before_pixels':before,'after_pixels':after}],'acknowledged_consumers':[]}
        plan=self.api.dispatch('assets.plan',{**self.sp,'schema':self.schema,'edits':self.edits});self.assertTrue(plan['ok'],plan);self.plan=plan['workbench_plan_id']
        self.cfg={'expected_core_sha256':'c'*64,'core_options':{},'controller_devices':{},'system_files':[]}
        self.original=frame(bytes([0,0,0,255,0,0])*32);self.changed=frame(bytes([0,0,0,0,255,0])*32)
        trace=store_evidence(self.api.project(self.sp),'runtime',{'scope':'gameplay_trace_v1','artifact_id':self.source['artifact_id'],'source_sha256':self.source['sha256'],'frame':self.original,'region':{'x':0,'y':0,'width':8,'height':8},'replay':{'status':'READY','frames':10,'steps':[{'frames':10,'buttons':[],'port':0}],'context':execution_context(self.cfg)}})
        self.args={**self.sp,'plan_id':self.plan,'trace_id':trace['evidence_id']}
    def sample(self,project,row,config,steps,cancelled):
        self.assertTrue(Path(row['path']).is_relative_to(project));self.assertEqual(steps,[{'frames':10,'buttons':[],'port':0}])
        return {'frame':self.original if row['sha256']==self.source['sha256'] else self.changed,'worker_exit_code':0,'state_replay':True,'execution_sha256':'e'*64}
    def preview(self):
        self.assertIn('assets.preview_scene',self.api.routes)
        with patch.object(self.api,'_profile_load_config',return_value=self.cfg),patch('romancer.draft_scene.run_sample',side_effect=self.sample) as run:
            result=self.api.dispatch('assets.preview_scene',self.args)
        self.assertTrue(result['ok'],result);return result,run
    def test_native_draft_scene_uses_checked_plan_and_preserves_original_and_user_build_history(self):
        result,run=self.preview();self.assertEqual(run.call_count,3);self.assertEqual(result['status'],'REVIEW');self.assertGreater(result['changed_pixels'],0)
        self.assertTrue(result['preview_only']);self.assertTrue(result['emulated_frame']);self.assertFalse(result['simulated']);self.assertTrue(result['original_reproduced_twice'])
        self.assertEqual(hashlib.sha256(Path(self.source['path']).read_bytes()).hexdigest(),self.source['sha256'])
        self.assertEqual(self.api.dispatch('project.open',{'project_id':self.sp['project_id']})['builds'],[])
        self.assertFalse(list((self.api.project(self.sp)/'sessions').glob('source-test-*')))
        restored=self.api.dispatch('assets.preview_scene.get',{**self.args,'evidence_id':result['evidence_id'],'schema':self.schema,'edits':self.edits})
        self.assertTrue(restored['ok'],restored);self.assertEqual(restored['draft_sha256'],result['draft_sha256'])
        found=self.api.dispatch('assets.preview_scene.find',{**self.sp,'trace_id':self.args['trace_id'],'schema':self.schema,'edits':self.edits})
        self.assertTrue(found['ok'],found);self.assertTrue(found['found']);self.assertEqual(found['evidence_id'],result['evidence_id'])
        changed={**self.edits,'changes':[]};self.assertFalse(self.api.dispatch('assets.preview_scene.get',{**self.args,'evidence_id':result['evidence_id'],'schema':self.schema,'edits':changed})['ok'])
    def test_context_historical_trace_and_mismatched_plan_are_rejected_before_native_execution(self):
        self.assertIn('assets.preview_scene',self.api.routes)
        with patch.object(self.api,'_profile_load_config',return_value={**self.cfg,'core_options':{'changed':True}}),patch('romancer.draft_scene.run_sample') as run:
            r=self.api.dispatch('assets.preview_scene',self.args);self.assertFalse(r['ok']);run.assert_not_called()
        quarantine_restored_evidence(self.api.project(self.sp))
        with patch.object(self.api,'_profile_load_config',return_value=self.cfg),patch('romancer.draft_scene.run_sample') as run:
            self.assertFalse(self.api.dispatch('assets.preview_scene',self.args)['ok']);run.assert_not_called()
    def test_unstable_original_refuses_draft_preview_and_cancel_releases_capacity_and_scratch(self):
        self.assertIn('assets.preview_scene',self.api.routes)
        samples=[{'frame':f,'worker_exit_code':0,'state_replay':True,'execution_sha256':'e'*64} for f in (self.original,self.changed)]
        with patch.object(self.api,'_profile_load_config',return_value=self.cfg),patch('romancer.draft_scene.run_sample',side_effect=samples) as run:
            r=self.api.dispatch('assets.preview_scene',self.args);self.assertTrue(r['ok'],r);self.assertEqual(r['status'],'INCONCLUSIVE');self.assertNotIn('visual',r);self.assertEqual(run.call_count,2)
        with patch.object(self.api,'_profile_load_config',return_value=self.cfg),patch('romancer.draft_scene.run_sample',side_effect=KeyboardInterrupt):
            self.assertFalse(self.api.dispatch('assets.preview_scene',self.args)['ok'])
        self.assertFalse(list((self.api.project(self.sp)/'sessions').glob('source-test-*')))
        self.preview()
