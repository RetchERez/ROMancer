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
