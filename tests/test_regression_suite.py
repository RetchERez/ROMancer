from romancer.boot_fixtures import make_boot_fixture
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

class SuiteValidationTests(unittest.TestCase):
    def test_invalid_route_budgets_refuse_before_any_native_run(self):
        from romancer.workbench_api import WorkbenchAPI
        folder=self.enterContext(tempfile.TemporaryDirectory())
        root=Path(folder);source=root/'original.bin';source.write_bytes(make_boot_fixture('nes')['data']);api=WorkbenchAPI(root/'workspace');self.addCleanup(api.close)
        project=api.dispatch('project.create',{'name':'Suite'});row=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(source),'system':None});api._run_saved_route=Mock(side_effect=AssertionError('should not run'))
        params={'project_id':project['project_id'],'source_id':row['artifact_id'],'target_id':row['artifact_id'],'definition_ids':[],'timeout':10}
        for ids in ([],['a'*32]*9,['a'*32,'a'*32]):
            result=api.dispatch('regression.run_suite',{**params,'definition_ids':ids});self.assertFalse(result['ok'],result)
        api._run_saved_route.assert_not_called()
        self.assertNotEqual(api.dispatch('regression.run_suite',params).get('error'),'unknown workbench operation')

@unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'compiled native suite')
class NativeSuiteTests(unittest.TestCase):
    def test_suite_finds_real_regression_and_refuses_to_pass_a_bad_baseline(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.route_editor import compile_route
        folder=self.enterContext(tempfile.TemporaryDirectory())
        root=Path(folder);core=root/'mock.so';code=Path('tests/mock_libretro.c').read_text(encoding='utf-8').replace('memcpy(romshadow,game->data,n);','memcpy(romshadow,game->data,n); sysram[2]=romshadow[16];');fixture=root/'seeded.c';fixture.write_text(code,encoding='utf-8')
        subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST',str(fixture),'-o',str(core)],check=True,capture_output=True)
        source=root/'original.bin';raw=bytearray(make_boot_fixture('nes')['data']);raw[16:21]=b'\0ABCD';source.write_bytes(raw);api=WorkbenchAPI(root/'workspace');self.addCleanup(api.close)
        project=api.dispatch('project.create',{'name':'Native suite'});p={'project_id':project['project_id']};row=api.dispatch('source.import',{**p,'path':str(source),'system':None});api.dispatch('profiles.save',{'system_id':'nes','core':str(core),'options':{},'system_dir':None,'input_map':{}})
        route=compile_route('Seed check',[{'frames':1,'buttons':[],'port':0,'assertions':[{'kind':'memory_eq','region':2,'offset':2,'expected_hex':'00'}],'transition':None,'checkpoint':False}],60,4)
        saved=api.dispatch('routes.save',{**p,'selection':{'kind':'artifact','id':row['artifact_id']},'system_id':'nes','route':route,'initial_state_id':None});self.assertTrue(saved['ok'],saved)
        plan=api.dispatch('bytes.plan',{**p,'artifact_id':row['artifact_id'],'edits':[{'offset':16,'before':'00','after':'01'}]});built=api.dispatch('build.apply',{**p,'plan_id':plan['plan_id']})
        params={**p,'source_id':row['artifact_id'],'target_id':built['artifact_id'],'definition_ids':[saved['definition_id']],'timeout':15}
        result=api.dispatch('regression.run_suite',params);self.assertTrue(result['ok'],result);self.assertEqual(result['status'],'REGRESSION');self.assertEqual(result['counts']['regression'],1);self.assertTrue(result['runtime_evidence_authenticated'])
        unchanged=api.dispatch('regression.run_suite',{**params,'target_id':row['artifact_id']});self.assertEqual(unchanged['status'],'PASS',unchanged)
        bad=api.dispatch('regression.run_suite',{**params,'source_id':built['artifact_id']});self.assertEqual(bad['status'],'INCONCLUSIVE',bad);self.assertEqual(bad['tests'][0]['reason'],'Baseline assertions failed; candidate was not run.')
        self.assertEqual(api.dispatch('regression.run_suite',params,cancelled=lambda:True)['status'],'CANCELLED')
        self.assertEqual(api.runtime.sessions,{})
