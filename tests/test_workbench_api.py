import importlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import sys
import shutil
import subprocess
import hashlib


class APITests(unittest.TestCase):
    def test_invalid_job_directory_does_not_leave_a_runtime_reaper_alive(self):
        import gc,time
        from romancer.workbench_api import WorkbenchAPI
        before=set(threading.enumerate())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'jobs').write_bytes(b'not a directory')
            with self.assertRaises(OSError):WorkbenchAPI(root)
            gc.collect();time.sleep(.05)
            self.assertEqual([t for t in threading.enumerate() if t not in before],[])

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'compiled API workflow')
    def test_native_capture_audio_and_local_state_round_trip(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'mock.so'
            subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST','tests/mock_libretro.c','-o',str(core)],check=True)
            api=WorkbenchAPI(root/'workspace')
            try:
                demo=api.dispatch('project.demo',{});row=demo['sources'][0];p={'project_id':demo['project_id']};src={**p,'artifact_id':row['artifact_id']}
                load={'core':str(core),'game':row['path'],'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':row['sha256'],'session_dir':str(root/'capture')}
                recorded=api.dispatch('captures.record',{**src,'config':{'load':load,'steps':[{'frames':1,'buttons':['right'],'port':0}],'initial_state_file':None,'timeout':10}})
                self.assertTrue(recorded['ok'],recorded)
                found=api.dispatch('captures.search',{**p,'query':{'origin':'native_worker'}});self.assertEqual(len(found['matches']),1,found)
                got=api.dispatch('captures.get',{**p,'capture_id':recorded['capture_id']});self.assertTrue(got['png_base64']);self.assertEqual(got['image_integrity'],'PASS')
                config={'schema_version':1,'load':{**load,'session_dir':str(root/'audio')},'steps':[{'frames':1,'buttons':[],'port':0}],'timeout_seconds':10}
                baseline={'schema_version':1,'id':'literal','version':'1','sample_rate':44100,'expected_duration':{'numerator':1,'denominator':11025},'tolerance_samples':0,'expected_pcm_sha256':None,'provenance':{'origin':'synthetic_fixture','note':'literal four sample frames','reference':None}}
                audio=api.dispatch('audio.capture',{**p,'config':config,'baseline':baseline,'format':'wav'});self.assertTrue(audio['ok'],audio)
                loaded=api.dispatch('runtime.load',{**src,'core':str(core),'options':{}});self.assertTrue(loaded['ok'],loaded)
                advanced=api.dispatch('runtime.advance',{**p,'frames':1,'buttons':['right'],'port':0});self.assertTrue(advanced['ok'],advanced)
                drained=api.dispatch('runtime.audio',p);self.assertTrue(drained['ok'],drained)
                self.assertEqual(drained['captured_frames'],4);self.assertEqual(len(api.runtime.sessions),1)
                state=api.dispatch('runtime.save_state',p);self.assertTrue(state['ok'],state);self.assertNotIn('state_base64',state)
                restored=api.dispatch('runtime.load_state',{**p,'snapshot_id':state['snapshot_id']});self.assertTrue(restored['ok'],restored)
                closed=api.dispatch('runtime.close',p);self.assertEqual(closed['worker_exit_code'],0,closed)
                loaded=api.dispatch('runtime.load',{**src,'core':str(core),'options':{}});self.assertTrue(loaded['ok'],loaded)
                with self.assertRaises(KeyboardInterrupt):api.runtime.request(Path(demo['path']),'advance',{'frames':1,'buttons':[],'port':0},cancelled=lambda:True)
                self.assertEqual(api.runtime.sessions,{})
            finally:api.close()

    def test_capture_store_and_audio_route_are_connected(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.history import get_build
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp))
            try:
                demo=api.dispatch('project.demo',{});p={'project_id':demo['project_id']}
                row=demo['sources'][0]
                self.assertEqual(get_build(Path(demo['path']),row['build_id'])['identity']['output']['sha256'],row['sha256'])
                found=api.dispatch('captures.search',{**p,'query':{'limit':20}})
                self.assertEqual(found.get('matches'),[],found)
                audio=api.dispatch('audio.capture',{**p,'config':{},'baseline':{},'format':'wav'})
                self.assertFalse(audio['ok']);self.assertNotIn('unexpected keyword',audio.get('error',''))
            finally:api.close()

    def test_demo_structured_edit_patch_export_reopen_and_package(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp))
            try:
                demo=api.dispatch('project.demo',{});p={'project_id':demo['project_id'],'artifact_id':demo['sources'][0]['artifact_id']}
                schema=demo['descriptors']['script'];doc=api.dispatch('script.inspect',{**p,'schema':schema})
                self.assertTrue(doc['ok'],doc)
                edits={'schema_version':1,'document_id':doc['document_id'],'source_sha256':doc['source_sha256'],
                    'schema_sha256':doc['schema_sha256'],'changes':[{'record_id':'welcome','segment':0,'text':'WELCOME ABOARD.'}]}
                plan=api.dispatch('script.plan',{**p,'schema':schema,'edits':edits});self.assertTrue(plan['ok'],plan)
                build=api.dispatch('structured.apply',{'project_id':demo['project_id'],'plan_id':plan['workbench_plan_id']});self.assertTrue(build['ok'],build)
                rebound=api.dispatch('script.inspect',{'project_id':demo['project_id'],'artifact_id':build['artifact_id'],'schema':build['descriptors']['script']})
                self.assertTrue(rebound['ok'],rebound);self.assertEqual(rebound['records'][0]['segments'][0]['text'],'WELCOME ABOARD.')
                patch=api.dispatch('release.prepare',{'project_id':demo['project_id'],'source_id':p['artifact_id'],'target_id':build['artifact_id'],'title':'Demo','description':'Literal dialogue edit'})
                self.assertTrue(patch['ok'],patch)
                rows=api.dispatch('exports.list',{'project_id':demo['project_id']});self.assertTrue(rows['ok'],rows)
                package=api.dispatch('release.package',{'project_id':demo['project_id'],'export_ids':[r['export_id'] for r in rows['exports']],'title':'Demo'})
                self.assertTrue(package['ok'],package)
                self.assertEqual(len(api.dispatch('exports.list',{'project_id':demo['project_id']})['exports']),3)
            finally:api.close()

    def test_file_chooser_pipe_uses_utf8(self):
        from unittest.mock import patch
        from romancer.workbench_api import WorkbenchAPI
        class Picker:
            returncode=0
            def __init__(self,args,**kwargs):
                import io
                self.stdout=io.BytesIO('C:/Games/\u03a9 \u00e9.bin\n'.encode('utf-8'));self.args=args
                self.test_utf8=args[1:3]==['-X','utf8'] or (Path(args[0]).name=='powershell.exe' and '[Console]::OutputEncoding=[System.Text.UTF8Encoding]' in args[-1])
            def poll(self):return 0
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp));instances=[]
            def spawn(*args,**kwargs):
                value=Picker(*args,**kwargs);instances.append(value);return value
            try:
                with patch('romancer.workbench_api.subprocess.Popen',spawn):result=api.dispatch('system.pick_file',{})
                self.assertEqual(result['path'],'C:/Games/\u03a9 \u00e9.bin');self.assertTrue(instances[0].test_utf8)
            finally:api.close()

    def test_real_http_auth_origin_limits_and_build_workflow(self):
        try:m=importlib.import_module('romancer.workbench_server')
        except ModuleNotFoundError:m=None
        self.assertIsNotNone(m,'authenticated loopback server is missing')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'original Ω.bin';raw=bytearray(1024);raw[:4]=b'ABCD';raw[0x100:0x110]=b'SEGA MEGA DRIVE ';raw[0x1a4:0x1a8]=(1023).to_bytes(4,'big');original_bytes=bytes(raw);source.write_bytes(original_bytes)
            server=m.create_server(root/'workspace',0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            def request(operation,parameters,token=True,origin=None,raw=None):
                headers={'Content-Type':'application/json'}
                if token:headers['Authorization']='Bearer '+server.session_token
                if origin:headers['Origin']=origin
                req=urllib.request.Request(base+'/api/call',data=raw if raw is not None else json.dumps({'operation':operation,'parameters':parameters}).encode(),headers=headers)
                return json.load(urllib.request.urlopen(req,timeout=5))
            try:
                for token,origin,raw,code in ((False,None,None,401),(True,'https://evil.example',None,403),(True,None,b'{',400),(True,None,b' '* (1024**2+1),413)):
                    with self.assertRaises(urllib.error.HTTPError) as caught:request('projects.list',{},token,origin,raw)
                    self.assertEqual(caught.exception.code,code)
                    caught.exception.close()
                project=request('project.create',{'name':'HTTP Ω'})['project_id']
                artifact=request('source.import',{'project_id':project,'path':str(source),'system':None})['artifact_id']
                inspected=request('resource.inspect',{'project_id':project,'artifact_id':artifact,'offset':0,'length':4})
                self.assertEqual(inspected['hex'],'41424344')
                planned=request('bytes.plan',{'project_id':project,'artifact_id':artifact,'edits':[{'offset':1,'before':'42','after':'58'}]})
                built=request('build.apply',{'project_id':project,'plan_id':planned['plan_id']})
                self.assertEqual(Path(built['path']).read_bytes(),b'AX'+original_bytes[2:]);self.assertEqual(source.read_bytes(),original_bytes)
                unknown=request('execute.shell',{'command':'x'});self.assertFalse(unknown['ok'])
                self.assertEqual(server.server_address[0],'127.0.0.1')
            finally:server.shutdown();server.server_close();server.api.close();thread.join(3)
