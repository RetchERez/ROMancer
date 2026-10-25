import hashlib
import importlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from test_debug import DebugServiceTests


class DebugRuntimeTests(unittest.TestCase):
    def service(self):
        try:module=importlib.import_module('romancer.debug_runtime')
        except ModuleNotFoundError:module=None
        self.assertIsNotNone(module,'live before/after case observations are missing')
        return module.observe_debug_case

    def test_unknown_probe_blocks_before_runtime_session(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,project,fixture=DebugServiceTests.fixture(self,root)
            result=service(project,source,fixture['case'],fixture['trace'],{
                'load':{},'steps':[{'frames':1,'buttons':[],'port':0}],'initial_state_file':None,
                'timeout':10,'frame_region':[0,0,1,1],'memory_probe_ids':['unknown']},root)
            self.assertFalse(result['ok']);self.assertEqual(source.read_bytes(),fixture['raw'])

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'native compiled live diagnosis')
    def test_real_memory_difference_and_roi_are_not_causal_proof(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,project,fixture=DebugServiceTests.fixture(self,root)
            fixture['case']['probes'][3]['length']=2
            core=root/'mock.so'
            subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST','tests/mock_libretro.c','-o',str(core)],check=True)
            result=service(project,source,fixture['case'],fixture['trace'],{
                'load':{'core':str(core),'game':str(source),'session_dir':str(root/'session'),
                        'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':hashlib.sha256(source.read_bytes()).hexdigest()},
                'steps':[{'frames':1,'buttons':['right'],'port':0}],'initial_state_file':None,'timeout':10,
                'frame_region':[9,8,1,1],'memory_probe_ids':['cursor']},root)
            self.assertTrue(result['ok'],result)
            self.assertEqual(result['memory'][0]['before']['raw_hex'],'0808')
            self.assertEqual(result['memory'][0]['after']['raw_hex'],'0908')
            self.assertEqual(result['memory'][0]['relation'],'DIFFERENT')
            self.assertEqual(result['frame']['roi_rgb_hex'],'ffffff')
            self.assertEqual(result['causation'],'NOT_RUN')
            self.assertEqual(source.read_bytes(),fixture['raw'])
