from romancer.boot_fixtures import make_boot_fixture
from contextlib import ExitStack
import threading
import base64
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock,MagicMock
from romancer.workbench_runtime import RuntimePool


class LiveStepTests(unittest.TestCase):
    def test_step_batches_under_one_lock_and_preserves_capture_identity_path(self):
        pool=RuntimePool();self.addCleanup(pool.close)
        pool.sessions['project']={'runtime':MagicMock(),'load':{},'touched':0}
        pool.request=Mock(side_effect=[{'complete':False,'captured_frames':48000},{'ok':True,'frame_index':3},{'sha256':'f'*64},{'captured_frames':2}])
        pool.sessions['project']['runtime'].load_result={'av':{'timing':{'fps':60,'sample_rate':44100}}}
        result=pool.step('project',3,['a'],0)
        self.assertEqual([call.args[1] for call in pool.request.call_args_list],['audio','advance','capture','audio'])
        self.assertEqual(pool.request.call_args_list[1].args[2],{'frames':3,'buttons':['a'],'port':0})
        self.assertEqual(result['timing']['fps'],60);self.assertEqual(result['advanced']['frame_index'],3)
        for frames in (0,13,True):
            with self.assertRaises(ValueError):pool.step('project',frames,[],0)

    def test_live_step_excludes_accumulated_manual_audio_and_rejects_invalid_input_before_drain(self):
        pool=RuntimePool();self.addCleanup(pool.close)
        runtime=MagicMock();runtime.load_result={'av':{'timing':{'fps':60,'sample_rate':44100}}}
        pool.sessions['project']={'runtime':runtime,'load':{},'touched':0}
        pending=60000
        def request(project,operation,parameters,**kwargs):
            nonlocal pending
            if operation=='advance':pending+=parameters['frames']*735;return {'frame_index':844}
            if operation=='capture':return {'sha256':'f'*64}
            if operation=='audio':
                count=pending;pending=0
                return {'complete':count<=48000,'captured_frames':min(count,48000),'dropped_frames':max(0,count-48000)}
        pool.request=Mock(side_effect=request)
        result=pool.step('project',3,[],0)
        self.assertTrue(result['audio']['complete']);self.assertEqual(result['audio']['captured_frames'],2205)
        pool.request.reset_mock()
        with self.assertRaises(ValueError):pool.step('project',3,['not-a-button'],0)
        pool.request.assert_not_called()

    def test_no_active_session_refuses(self):
        pool=RuntimePool();self.addCleanup(pool.close)
        with self.assertRaises(ValueError):pool.step('missing',1,[],0)

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'compiled native ROM check')
    def test_smoke_check_is_measured_and_does_not_claim_gameplay_correctness(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.boot_fixtures import make_boot_fixture
        with tempfile.TemporaryDirectory() as folder, ExitStack() as resources:
            root=Path(folder);core=root/'mock_libretro.so';game=root/'original.gb';game.write_bytes(make_boot_fixture('gb')['data'])
            subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST','tests/mock_libretro.c','-o',str(core)],check=True)
            api=WorkbenchAPI(root/'workspace');resources.callback(api.close)
            project=api.dispatch('project.create',{'name':'ROM check'});p={'project_id':project['project_id']};source=api.dispatch('source.import',{**p,'path':str(game),'system':None})
            api.dispatch('profiles.save',{'system_id':'gb','core':str(core),'options':{},'system_dir':None,'input_map':{}})
            api.dispatch('runtime.load_profile',{**p,'artifact_id':source['artifact_id'],'system_id':'gb'});existing=api.runtime.sessions.copy()
            checked=api.dispatch('runtime.smoke_profile',{**p,'artifact_id':source['artifact_id'],'system_id':'gb'})
            self.assertTrue(checked['ok'],checked);self.assertEqual(checked['status'],'OBSERVED');self.assertFalse(checked['gameplay_verified']);self.assertEqual(checked['frames_advanced'],120);self.assertEqual(checked['worker_exit_code'],0)
            self.assertEqual(api.runtime.sessions,existing);self.assertTrue(checked['audio']['sample_bytes_nonzero'])

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'compiled native callback fixture')
    def test_real_native_step_and_literal_pcm(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder, ExitStack() as resources:
            root=Path(folder);core=root/'core.so';game=root/'game.bin';game.write_bytes(make_boot_fixture('nes')['data'])
            subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST','tests/mock_libretro.c','-o',str(core)],check=True)
            api=WorkbenchAPI(root/'workspace');resources.callback(api.close)
            project=api.dispatch('project.create',{'name':'Live test'});p={'project_id':project['project_id']}
            source=api.dispatch('source.import',{**p,'path':str(game),'system':None})
            loaded=api.dispatch('runtime.load',{**p,'artifact_id':source['artifact_id'],'core':str(core),'options':{}})
            self.assertTrue(loaded['ok'],loaded)
            result=api.dispatch('runtime.step',{**p,'frames':1,'buttons':['a'],'port':0})
            self.assertTrue(result['ok'],result);self.assertEqual(result['advanced']['frame_index'],1)
            raw=base64.b64decode(result['frame']['rgb24_base64']);self.assertEqual(hashlib.sha256(raw).hexdigest(),result['frame']['sha256'])
            self.assertEqual(base64.b64decode(result['audio']['pcm_s16le_base64']),bytes.fromhex('0080ff7fffff0100000000003412cced'))
