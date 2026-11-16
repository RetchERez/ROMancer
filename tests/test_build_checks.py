import base64,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI

def frame(raw):return {'width':8,'height':8,'index':10,'sha256':hashlib.sha256(raw).hexdigest(),'rgb24_base64':base64.b64encode(raw).decode()}

class BuildCheckTests(unittest.TestCase):
    def test_comparison_never_passes_changed_unstable_blank_or_dimension_changed_frames_as_unchanged(self):
        from romancer.build_checks import compare_frames
        a=frame(bytes([0,0,0,255,0,0])*32);b=frame(bytes([0,0,0,0,255,0])*32);blank=frame(bytes(192))
        self.assertEqual(compare_frames(a,a,a,None,'review_changes')['status'],'PASS')
        self.assertEqual(compare_frames(a,a,b,None,'review_changes')['status'],'REVIEW')
        changed=compare_frames(a,a,b,None,'unchanged');self.assertEqual(changed['status'],'REGRESSION');self.assertGreater(changed['changed_pixels'],0);self.assertTrue(changed['visual']['difference_png_base64'])
        self.assertEqual(compare_frames(a,b,b,None,'unchanged')['status'],'INCONCLUSIVE')
        self.assertEqual(compare_frames(blank,blank,blank,None,'unchanged')['status'],'INCONCLUSIVE')
        with self.assertRaises(ValueError):compare_frames(a,a,a,{'x':8,'y':0,'width':1,'height':1},'unchanged')

    def test_configured_build_queues_checks_and_enqueue_failure_preserves_the_successful_build(self):
        folder=self.enterContext(tempfile.TemporaryDirectory());api=WorkbenchAPI(Path(folder)/'work');self.addCleanup(api.close)
        p=api.dispatch('project.demo_system',{'system_id':'nes'});sp={'project_id':p['project_id'],'artifact_id':p['sources'][0]['artifact_id']}
        config={'name':'Opening picture','automatic':True,'mode':'review_changes','steps':[{'frames':60,'buttons':[],'port':0}],'region':None,'route_ids':[]}
        saved=api.dispatch('checks.configure',{**sp,'config':config});self.assertTrue(saved['ok'],saved)
        source=Path(p['sources'][0]['path']);before=source.read_bytes()[16384];plan=api.dispatch('bytes.plan',{**sp,'edits':[{'offset':16384,'before':f'{before:02x}','after':f'{before^1:02x}'}]});self.assertTrue(plan['ok'],plan)
        with patch.object(api.jobs,'submit',return_value={'job_id':'1'*32,'status':'QUEUED'}) as submit:
            built=api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']})
        self.assertTrue(built['ok'],built);self.assertEqual(built['automatic_check']['status'],'QUEUED');self.assertEqual(submit.call_args.args[0],'checks.run')
        next_plan=api.dispatch('bytes.plan',{**sp,'edits':[{'offset':16384,'before':f'{before:02x}','after':f'{before^2:02x}'}]})
        with patch.object(api.jobs,'submit',side_effect=ValueError('queue full')):
            other=api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':next_plan['plan_id']})
        self.assertTrue(other['ok'],other);self.assertEqual(other['automatic_check']['status'],'NOT_QUEUED')
        self.assertEqual(source.read_bytes()[16384],before)

    def test_configuration_rejects_unbounded_steps_bad_modes_and_silent_string_booleans(self):
        from romancer.build_checks import validate_config
        good={'name':'Test','automatic':True,'mode':'unchanged','steps':[{'frames':60,'buttons':[],'port':0}],'region':None,'route_ids':[]}
        self.assertEqual(validate_config(good)['mode'],'unchanged')
        for change in ({'automatic':'yes'},{'mode':'guess'},{'steps':[{'frames':6001,'buttons':[],'port':0}]},{'route_ids':['a'*32]*9}):
            with self.assertRaises(ValueError):validate_config({**good,**change})

    def test_edit_check_uses_authenticated_trace_and_refuses_unrelated_build_or_changed_context(self):
        from romancer.workbench_evidence import store_evidence
        from romancer.replay_journal import execution_context
        folder=self.enterContext(tempfile.TemporaryDirectory());api=WorkbenchAPI(Path(folder)/'work');self.addCleanup(api.close)
        demo=api.dispatch('project.demo_system',{'system_id':'nes'});sp={'project_id':demo['project_id'],'artifact_id':demo['sources'][0]['artifact_id']}
        source=demo['sources'][0];raw=Path(source['path']).read_bytes()
        plan=api.dispatch('bytes.plan',{**sp,'edits':[{'offset':4096,'before':raw[4096:4097].hex(),'after':bytes([raw[4096]^1]).hex()}]})
        target=api.dispatch('build.apply',{'project_id':sp['project_id'],'plan_id':plan['plan_id']})
        cfg={'expected_core_sha256':'c'*64,'core_options':{},'controller_devices':{},'system_files':[]}
        pic=frame(bytes([0,0,0,255,0,0])*32)
        trace=store_evidence(api.project(sp),'runtime',{'scope':'gameplay_trace_v1','source_sha256':source['sha256'],'artifact_id':source['artifact_id'],'frame':pic,'region':{'x':0,'y':0,'width':8,'height':8},'replay':{'status':'READY','steps':[{'frames':10,'buttons':['a'],'port':0}],'frames':10,'context':execution_context(cfg)}})
        args={'project_id':sp['project_id'],'source_id':source['artifact_id'],'target_id':target['artifact_id'],'trace_id':trace['evidence_id']}
        sample={'frame':pic,'state_replay':True,'worker_exit_code':0,'execution_sha256':'e'*64}
        with patch.object(api,'_profile_load_config',return_value=cfg),patch('romancer.build_checks.run_sample',return_value=sample) as run:
            result=api.dispatch('checks.from_trace',args)
        self.assertTrue(result['ok'],result);self.assertEqual(result['trace_id'],trace['evidence_id']);self.assertEqual(run.call_args.args[3],[{'frames':10,'buttons':['a'],'port':0}])
        rules=[{'name':'Held value','region':2,'offset':0,'length':1,'endian':'little','mode':'same','original':None,'build':None}]
        with patch.object(api,'_profile_load_config',return_value=cfg),patch('romancer.build_checks.run_sample',return_value={**sample,'values':[1]}):
            checked=api.dispatch('checks.from_trace',{**args,'expectations':rules})
        self.assertTrue(checked['gameplay_verified'],checked)
        self.assertTrue(checked['replay_verified'],checked)
        saved=api.dispatch('discoveries.save',{**sp,'evidence_id':checked['evidence_id'],'kind':'byte','name':'Test byte','offset':4096,'resource':None})
        self.assertEqual(saved['status'],'REPLAY_CHECKED',saved)
        opened=api.dispatch('discoveries.open',{**sp,'discovery_id':saved['discovery_id']})
        self.assertEqual(opened['inspection']['rows'][0]['cells'][0]['value'],raw[4096])
        wrong=api.dispatch('discoveries.save',{**sp,'evidence_id':checked['evidence_id'],'kind':'byte','name':'Unused','offset':4098,'resource':None})
        self.assertFalse(wrong['ok'])
        forged={**opened['document'],'source_sha256':'0'*64}
        self.assertFalse(api.dispatch('discoveries.import',{**sp,'document':forged})['ok'])
        again=api.dispatch('discoveries.import',{**sp,'document':opened['document']})
        self.assertEqual(again['status'],'REPLAY_CHECKED')
        release=api.dispatch('release.proof',{**args,'evidence_id':checked['evidence_id'],'title':'Replay','description':'', 'screenshots':False})
        self.assertFalse(release['ok'])  # Extra parameters must not enter the public serializer.
        release=api.dispatch('release.proof',{'project_id':sp['project_id'],'source_id':source['artifact_id'],'target_id':target['artifact_id'],
            'evidence_id':checked['evidence_id'],'title':'Replay','description':'','screenshots':False})
        self.assertTrue(release['ok'],release)
        self.assertEqual(release['proof']['observed_values'],[[1],[1]])
        with patch.object(api,'_profile_load_config',return_value=cfg):
            rejected=api.dispatch('checks.from_trace',{**args,'target_id':source['artifact_id']})
        self.assertFalse(rejected['ok'])
        with patch.object(api,'_profile_load_config',return_value={**cfg,'core_options':{'changed':'yes'}}):
            rejected=api.dispatch('checks.from_trace',args)
        self.assertFalse(rejected['ok']);self.assertRegex(rejected['error'],'context|setup')

    def test_gameplay_values_distinguish_expected_delta_unchanged_and_unstable_repeats(self):
        from romancer.build_checks import evaluate_expectations, validate_expectations

        rules = validate_expectations([
            {'name':'Distance','region':2,'offset':1,'length':1,'endian':'little','mode':'delta','original':24,'build':48},
            {'name':'Health','region':2,'offset':8,'length':1,'endian':'little','mode':'same','original':None,'build':None},
        ])
        self.assertEqual(evaluate_expectations(rules,[[24,5],[24,5],[48,5]])['status'],'PASS')
        self.assertEqual(evaluate_expectations(rules,[[24,5],[24,5],[47,5]])['status'],'FAIL')
        self.assertEqual(evaluate_expectations(rules,[[24,5],[23,5],[48,5]])['status'],'INCONCLUSIVE')
        self.assertEqual(evaluate_expectations(rules,[[24,5],[24,5],[48,4]])['status'],'FAIL')
        with self.assertRaises(ValueError):
            validate_expectations([{**rules[0],'length':3}])
