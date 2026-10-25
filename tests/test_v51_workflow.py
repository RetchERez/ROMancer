from romancer import ROMANCER_VERSION
from pathlib import Path
import tempfile
import unittest
from tests.test_system_identify import nes_bytes,gba_bytes


class FoundationAPITests(unittest.TestCase):
    def test_executable_foundation_acceptance_reports_measured_scope(self):
        from tools.verify_v51 import verify_v51
        with tempfile.TemporaryDirectory() as temp:
            report=verify_v51(Path(temp))
            self.assertTrue(report['ok'],report)
            self.assertEqual(report['tool_version'],ROMANCER_VERSION)
            self.assertEqual(set(report['families']),{'nes','snes','genesis','gb','gba'})
            self.assertEqual(report['nes_edit']['independent_bytes'],'PASS')
            self.assertEqual(report['nes_edit']['independent_patch'],'PASS')
            self.assertFalse(report['runtime_verified']);self.assertFalse(report['full_game_compatibility_claimed'])
            self.assertEqual(report['credit'],'By RetchEWretched')

    def test_import_uses_content_not_extension_or_human_label(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'System tools Ω'});p={'project_id':project['project_id']}
                unknown=root/'misleading.nes';unknown.write_bytes(b'UNKNOWN BYTES')
                row=api.dispatch('source.import',{**p,'path':str(unknown),'system':'NES'})
                self.assertTrue(row['ok'],row);self.assertIsNone(row['system_id'])
                self.assertEqual(row['system_assessment']['status'],'UNKNOWN')
                gba=root/'GBA with spaces.bin';gba.write_bytes(gba_bytes())
                row=api.dispatch('source.import',{**p,'path':str(gba),'system':None})
                self.assertEqual(row['system_id'],'gba');self.assertEqual(row['system'],'GBA')
                params={**p,'artifact_id':row['artifact_id']}
                fresh=api.dispatch('systems.identify',params);self.assertEqual(fresh['source']['sha256'],row['sha256'])
                self.assertFalse(fresh['write_authorized']);self.assertFalse(fresh['runtime_verified'])
                caps=api.dispatch('system.capabilities',{});self.assertEqual(caps['version'],__import__('romancer').ROMANCER_VERSION)
                self.assertEqual(caps['target_version'],'1.0');self.assertIn('adapters',caps)
                inventory=api.dispatch('systems.list',{});self.assertEqual(len(inventory['systems']),5)
                with self.assertRaises(ValueError):api.jobs.submit('systems.list',{})
                self.assertFalse(api.dispatch('systems.identify',{**params,'path':str(gba)})['ok'])
                self.assertFalse(api.dispatch('systems.identify',{**p,'artifact_id':'0'*32})['ok'])
                owned=Path(row['path']);raw=bytearray(owned.read_bytes());raw[-1]^=1;owned.write_bytes(raw)
                self.assertEqual(api.dispatch('systems.identify',params)['status'],'BLOCKED')
                self.assertEqual(gba.read_bytes(),gba_bytes())
            finally:api.close()

    def test_legacy_record_without_assessment_can_be_identified(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.workbench_projects import read_project,write_json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'fixture.nes';source.write_bytes(nes_bytes());api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Legacy'});p={'project_id':project['project_id']}
                row=api.dispatch('source.import',{**p,'path':str(source),'system':None})
                directory=Path(project['path']);value=read_project(directory)
                value['sources'][0].pop('system_id',None);value['sources'][0].pop('system_assessment',None)
                write_json(directory/'project.json',value);before=(directory/'project.json').read_bytes()
                result=api.dispatch('systems.identify',{**p,'artifact_id':row['artifact_id']})
                self.assertEqual(result['system_id'],'nes',result)
                self.assertEqual((directory/'project.json').read_bytes(),before)
                self.assertEqual(api.dispatch('systems.identify',{**p,'artifact_id':row['artifact_id']},cancelled=lambda:True)['status'],'CANCELLED')
            finally:api.close()

    def test_system_routes_require_authentication_and_owned_artifact(self):
        import json,threading,urllib.request,urllib.error
        from romancer.workbench_server import create_server
        with tempfile.TemporaryDirectory() as temp:
            server=create_server(Path(temp),0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(token=None,origin=None):
                headers={'Content-Type':'application/json'}
                if token:headers['Authorization']='Bearer '+token
                if origin:headers['Origin']=origin
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/call',
                    data=json.dumps({'operation':'systems.list','parameters':{}}).encode(),headers=headers)
                with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
            try:
                for token,origin,code in ((None,None,401),(server.session_token,'https://example.invalid',403)):
                    with self.assertRaises(urllib.error.HTTPError) as caught:request(token,origin)
                    self.assertEqual(caught.exception.code,code);caught.exception.close()
                self.assertEqual(len(request(server.session_token)['systems']),5)
            finally:server.shutdown();server.server_close();server.api.close();thread.join(3)


if __name__=='__main__':unittest.main()
