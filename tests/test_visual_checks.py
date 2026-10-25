from romancer.boot_fixtures import make_boot_fixture
import base64
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


def frame(raw,width=2,height=2):return {'ok':True,'rgb24_base64':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),'width':width,'height':height,'index':1}


class VisualCheckpointTests(unittest.TestCase):
    def test_literal_region_difference_and_png_pixels(self):
        from romancer.visual_checks import make_assertion,compare_frame
        from PIL import Image
        original=frame(bytes.fromhex('ff0000 00ff00 0000ff ffffff'));assertion=make_assertion(original,{'x':1,'y':0,'width':1,'height':2})
        self.assertEqual(base64.b64decode(assertion['expected_rgb24_base64']),bytes.fromhex('00ff00 ffffff'))
        self.assertTrue(compare_frame(original,assertion)['pass'])
        actual=frame(bytes.fromhex('ff0000 000000 0000ff ffffff'));result=compare_frame(actual,assertion)
        self.assertFalse(result['pass']);self.assertEqual(result['changed_pixels'],1)
        for name,expected in (('expected_png_base64',[(0,255,0),(255,255,255)]),('actual_png_base64',[(0,0,0),(255,255,255)]),('difference_png_base64',[(0,255,0),(0,0,0)])):
            image=Image.open(io.BytesIO(base64.b64decode(result['visual'][name])));self.assertEqual(list(image.get_flattened_data()),expected)

    def test_region_payload_dimensions_and_hash_are_strict(self):
        from romancer.visual_checks import make_assertion,validate_assertion
        original=frame(b'\0'*12)
        for region in ({'x':-1,'y':0,'width':1,'height':1},{'x':1,'y':0,'width':2,'height':1},{'x':0,'y':0,'width':257,'height':1},{'x':True,'y':0,'width':1,'height':1}):
            with self.assertRaises(ValueError):make_assertion(original,region)
        assertion=make_assertion(original,{'x':0,'y':0,'width':1,'height':1});assertion['expected_sha256']='0'*64
        with self.assertRaises(ValueError):validate_assertion(assertion)
        original['sha256']='0'*64
        with self.assertRaises(ValueError):make_assertion(original,{'x':0,'y':0,'width':1,'height':1})

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'native checkpoint recording/replay')
    def test_owned_recording_and_authenticated_visual_failure_report(self):
        from romancer.visual_checks import make_assertion
        from romancer.workbench_api import WorkbenchAPI
        from romancer.replay import run_route
        from romancer import workbench_projects as p
        from romancer.workbench_evidence import load_evidence
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);core=root/'mock.so';subprocess.run(['gcc','-shared','-fPIC','-O2','tests/mock_libretro.c','-o',str(core)],check=True)
            api=WorkbenchAPI(root/'workspace');game=root/'game.bin';game.write_bytes(make_boot_fixture('nes')['data'])
            try:
                project=Path(p.create_project(api.projects,'Visual')['path']);row=p.register_source(project,game,None);params={'project_id':project.name}
                api.runtime.load(project,row['artifact_id'],str(core),{})
                start=api.dispatch('routes.record_start',{**params,'system_id':'nes','name':'Right'});self.assertTrue(start['ok'],start)
                packet=api.runtime.step(project,1,['right'],0)
                wrong=api.dispatch('routes.record_region',{**params,'region':{'x':8,'y':8,'width':3,'height':1},'frame_sha256':'0'*64});self.assertFalse(wrong['ok'],wrong)
                recorded=api.dispatch('routes.record_region',{**params,'region':{'x':8,'y':8,'width':3,'height':1},'frame_sha256':packet['frame']['sha256']});self.assertTrue(recorded['ok'],recorded)
                stopped=api.runtime.stop_recording(project);route=stopped['route'];api.runtime.close_session(project)
                config={'core':str(core),'game':row['path'],'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':row['sha256'],'session_dir':str(project/'sessions'/'replay-pass')}
                passed=run_route(project,route,config,project);self.assertEqual(passed['status'],'PASS',passed)
                route['steps'][0]['buttons']=['left'];config['session_dir']=str(project/'sessions'/'replay-fail');failed=run_route(project,route,config,project)
                self.assertEqual(failed['status'],'FAIL',failed);self.assertTrue(failed['worker_close_acknowledged']);self.assertEqual(failed['worker_exit_code'],0)
                evidence=load_evidence(project,failed['evidence_id'],'route');self.assertTrue(evidence['runtime_trusted']);self.assertTrue(evidence['report']['observations'][0]['visual']['difference_png_base64'])
            finally:api.close()
