import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import io

from romancer.mcp_server import MCPServer


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.server=MCPServer(self.root/'workspace')
        self.addCleanup(self.server.close)

    def start(self,server=None):
        server=server or self.server
        result=server.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}})
        self.assertEqual(result['result']['protocolVersion'],'2025-11-25')
        server.handle({'jsonrpc':'2.0','method':'notifications/initialized'})

    def call(self,name,arguments=None,server=None):
        return (server or self.server).handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':name,'arguments':arguments or {}}})

    def test_handshake_discovery_and_readonly_default(self):
        self.assertIn('error',self.call('romancer_projects_list'))
        self.start();tools=self.server.handle({'jsonrpc':'2.0','id':3,'method':'tools/list'})['result']['tools']
        self.assertIn('romancer_projects_list',[t['name'] for t in tools])
        self.assertNotIn('romancer_project_create',[t['name'] for t in tools])
        self.assertTrue(self.call('romancer_project_create',{'name':'Blocked'})['result']['isError'])
        result=self.call('romancer_projects_list');self.assertFalse(result['result']['isError']);self.assertIn('structuredContent',result['result'])

    def test_write_opt_in_preserves_backend_validation_and_rejects_external_paths(self):
        server=MCPServer(self.root/'writing',allow_writes=True);self.addCleanup(server.close);self.start(server)
        created=self.call('romancer_project_create',{'name':'AI workshop'},server)['result']['structuredContent']
        self.assertIn('project_id',created)
        blocked=self.call('romancer_source_import',{'project_id':created['project_id'],'path':str(self.root/'secret'),'system':None},server)
        self.assertTrue(blocked['result']['isError']);self.assertIn('allowed',blocked['result']['content'][0]['text'])
        unknown=self.call('romancer_call',{'operation':'system.pick_file','parameters':{}},server)
        self.assertTrue(unknown['result']['isError'])
        forged=self.call('romancer_build_apply',{'project_id':created['project_id'],'plan_id':'missing'},server)
        self.assertTrue(forged['result']['isError'])

    def test_local_paths_require_explicit_roots_and_tool_errors_are_structured(self):
        server=MCPServer(self.root/'importing',allow_writes=True,read_roots=[self.root/'roms']);self.addCleanup(server.close);self.start(server)
        (self.root/'roms').mkdir();from romancer.boot_fixtures import make_boot_fixture
        path=self.root/'roms/original.nes';raw=make_boot_fixture('nes')['data'];path.write_bytes(raw)
        created=self.call('romancer_project_create',{'name':'ROM import'},server)['result']['structuredContent']
        result=self.call('romancer_source_import',{'project_id':created['project_id'],'path':str(path),'system':None},server)['result']
        self.assertFalse(result['isError'],result);self.assertEqual(path.read_bytes(),raw)
        bad=self.call('romancer_resource_inspect',{'project_id':created['project_id'],'artifact_id':result['structuredContent']['artifact_id'],'offset':0,'length':100000},server)
        self.assertTrue(bad['result']['isError'])

    def test_stdio_survives_malformed_cancel_and_never_answers_notifications(self):
        from romancer.mcp_server import serve
        messages=[{'jsonrpc':'2.0','method':'notifications/cancelled','params':[]},
                  {'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':[]}},
                  {'jsonrpc':'2.0','method':'ping'},
                  {'jsonrpc':'2.0','id':9,'method':'ping'}]
        reader=io.BytesIO(b'\xff\n'+b'\n'.join(json.dumps(m).encode() for m in messages)+b'\n');writer=io.BytesIO()
        serve(self.server,reader,writer);responses=[json.loads(l) for l in writer.getvalue().splitlines()]
        self.assertEqual(len(responses),2);self.assertEqual(responses[0]['error']['code'],-32700);self.assertEqual(responses[1]['id'],9)

    def test_actual_stdio_process_handshake_tool_and_clean_exit_from_another_folder(self):
        script=Path(__file__).parents[1]/'romancer/mcp_server.py'
        process=subprocess.Popen([sys.executable,'-I','-B',str(script),'--workspace',str(self.root/'stdio')],cwd=self.root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        try:
            def send(message):process.stdin.write((json.dumps(message)+'\n').encode());process.stdin.flush()
            send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}})
            self.assertEqual(json.loads(process.stdout.readline())['id'],1)
            send({'jsonrpc':'2.0','method':'notifications/initialized'})
            send({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'romancer_projects_list','arguments':{}}})
            response=json.loads(process.stdout.readline());self.assertEqual(response['id'],2);self.assertFalse(response['result']['isError'])
            process.stdin.close();self.assertEqual(process.wait(timeout=15),0,process.stderr.read().decode())
            self.assertEqual(process.stdout.read(),b'')
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stdout.close();process.stderr.close()

    def test_advertised_schemas_accept_real_object_array_and_boolean_parameters(self):
        server=MCPServer(self.root/'schema',allow_writes=True);self.addCleanup(server.close)
        schemas={t['name']:t['inputSchema'] for t in server.tools()}
        cases=[('profiles_controller','controller_devices','object'),('resources_declare_assets','config','object'),
               ('tables_plan','changes','array'),('hex_bookmark','remove','boolean'),('rom_scan_start','rescan','boolean'),
               ('assets_plan','edits','object'),('systems_plan_edits','edits','array')]
        for tool,field,kind in cases:
            with self.subTest(tool=tool):self.assertEqual(schemas['romancer_'+tool]['properties'][field]['type'],kind)


if __name__=='__main__':unittest.main()
