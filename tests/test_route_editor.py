from romancer.boot_fixtures import make_boot_fixture
import copy
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class RouteEditorTests(unittest.TestCase):
    def test_guided_steps_require_real_assertions_and_budget(self):
        from romancer.route_editor import compile_route
        step={'frames':1,'buttons':['right'],'port':0,'assertions':[{'kind':'memory_eq','region':2,'offset':0,'expected_hex':'0908'}],'transition':None,'checkpoint':False}
        route=compile_route('Check input',[step],600,10);self.assertEqual(route['steps'][0]['assertions'][0]['expected_hex'],'0908')
        bad=copy.deepcopy(step);bad['assertions']=[]
        with self.assertRaises(ValueError):compile_route('No assertion',[bad],600,10)
        with self.assertRaises(ValueError):compile_route('Budget',[step],1,0)
        bad=copy.deepcopy(step);bad['assertions']=[{'kind':'imported_pass','value':True}]
        with self.assertRaises(ValueError):compile_route('Fabricated',[bad],600,10)

    def test_complete_system_file_identity_allows_comparison_and_changed_files_refuse(self):
        from romancer.regression import compare_runs
        identity={'schema_version':2,'tool_version':'test','core_options':{},'effective_core_options':{'mode':'normal'},'game_dependencies':[],
                  'system_files':[{'relative':'bios.bin','expected_sha256':'1'*64}],'initial_state_sha256':None,'game_save_sha256':None,'system_directory_used':True}
        baseline={'status':'PASS','route_sha256':'2'*64,'context':{'core_sha256':'3'*64},'execution_identity':identity,'observations':[]}
        self.assertEqual(compare_runs(baseline,copy.deepcopy(baseline))['status'],'UNCHANGED')
        changed=copy.deepcopy(baseline);changed['execution_identity']['system_files'][0]['expected_sha256']='4'*64
        self.assertEqual(compare_runs(baseline,changed)['status'],'INCONCLUSIVE')
        changed=copy.deepcopy(baseline);changed['execution_identity']['effective_core_options']['mode']='changed'
        self.assertEqual(compare_runs(baseline,changed)['status'],'INCONCLUSIVE')


@unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'compiled route regression fixture requires Linux/WSL')
class NativeRouteEditorTests(unittest.TestCase):
    def test_live_input_recording_replays_with_its_owned_checkpoint(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'mock.so';subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST',str(Path(__file__).with_name('mock_libretro.c')),'-o',str(core)],check=True,capture_output=True)
            source=root/'own.bin';source.write_bytes(make_boot_fixture('nes')['data']);api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Recording'});p={'project_id':project['project_id']}
                row=api.dispatch('source.import',{**p,'path':str(source),'system':None});selection={**p,'artifact_id':row['artifact_id']}
                api.dispatch('profiles.save',{'system_id':'nes','core':str(core),'options':{},'system_dir':None,'input_map':{}})
                self.assertTrue(api.dispatch('runtime.load_profile',{**selection,'system_id':'nes'})['ok'])
                started=api.dispatch('routes.record_start',{**p,'system_id':'nes','name':'Recorded right'});self.assertTrue(started['ok'],started)
                self.assertTrue(api.dispatch('runtime.advance',{**p,'frames':1,'buttons':['right'],'port':0})['ok'])
                assertion=api.dispatch('routes.record_memory',{**p,'region':2,'offset':0,'length':2});self.assertTrue(assertion['ok'],assertion)
                stopped=api.dispatch('routes.record_stop',p);self.assertTrue(stopped['complete'],stopped)
                self.assertEqual(stopped['route']['steps'][0]['assertions'][0]['expected_hex'],'0908')
                api.dispatch('runtime.close',p)
                replayed=api.dispatch('routes.run_saved',{**p,'definition_id':stopped['definition_id'],'selection':{'kind':'artifact','id':row['artifact_id']},'use_checkpoint':True,'timeout':15})
                self.assertEqual(replayed['status'],'PASS',replayed)
            finally:api.close()

    def test_profile_route_detects_seeded_build_regression_and_bisects_it(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.route_editor import compile_route
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'mock.so';code=Path(__file__).with_name('mock_libretro.c').read_text()
            code=code.replace('memcpy(romshadow,game->data,n);','memcpy(romshadow,game->data,n); sysram[2]=romshadow[16];')
            fixture=root/'seeded.c';fixture.write_text(code);subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST',str(fixture),'-o',str(core)],check=True,capture_output=True)
            source=root/'own.bin';raw=bytearray(make_boot_fixture('nes')['data']);raw[16:21]=b'\0ABCD';source.write_bytes(raw);api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Regression'});p={'project_id':project['project_id']}
                row=api.dispatch('source.import',{**p,'path':str(source),'system':None});selection={**p,'artifact_id':row['artifact_id']}
                self.assertTrue(api.dispatch('profiles.save',{'system_id':'nes','core':str(core),'options':{},'system_dir':None,'input_map':{}})['ok'])
                route=compile_route('Seed check',[{'frames':1,'buttons':[],'port':0,'assertions':[{'kind':'memory_eq','region':2,'offset':2,'expected_hex':'00'}],'transition':None,'checkpoint':False}],60,4)
                baseline=api.dispatch('route.run_profile',{**selection,'system_id':'nes','route':route,'timeout':15,'initial_state':None});self.assertEqual(baseline['status'],'PASS',baseline)
                changes=[{'offset':16,'before':'00','after':'01'},{'offset':17,'before':'41','after':'5a'}]
                plan=api.dispatch('bytes.plan',{**selection,'edits':changes});built=api.dispatch('build.apply',{**p,'plan_id':plan['plan_id']})
                candidate=api.dispatch('route.run_profile',{**p,'artifact_id':built['artifact_id'],'system_id':'nes','route':route,'timeout':15,'initial_state':None});self.assertEqual(candidate['status'],'FAIL',candidate)
                comparison=api.dispatch('regression.compare',{**p,'baseline_id':baseline['evidence_id'],'candidate_id':candidate['evidence_id']});self.assertEqual(comparison['status'],'REGRESSION',comparison)
                bisected=api.dispatch('regression.bisect_profile',{**selection,'system_id':'nes','route':route,'changes':changes,'budget':{'max_evaluations':12},'timeout':15})
                self.assertEqual(bisected['failing_subset'],[changes[0]],bisected);self.assertTrue(bisected['minimal_reproduced'])
            finally:api.close()
