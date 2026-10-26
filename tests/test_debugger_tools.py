from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI
from romancer.boot_fixtures import make_boot_fixture
from tests.test_native_debugger import config


class DebuggerAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.api=WorkbenchAPI(self.root/'workspace');self.addCleanup(self.api.close)
        s=self.api.dispatch('settings.get',{});self.api.dispatch('settings.save',{'revision':s['revision'],'values':{**s['values'],'autoDeepScan':False}})
        p=self.api.dispatch('project.create',{'name':'Native investigation'})
        path=self.root/'Original.nes';path.write_bytes(make_boot_fixture('nes')['data'])
        a=self.api.dispatch('source.import',{'project_id':p['project_id'],'path':str(path),'system':None})
        self.params={'project_id':p['project_id'],'artifact_id':a['artifact_id']};self.sha=a['sha256']

    def test_genesis_execution_watch_is_rejected_through_api_and_mcp_before_launch(self):
        from romancer.mcp_server import MCPServer
        demo=self.api.dispatch('project.demo_system',{'system_id':'genesis'})
        row=self.api.dispatch('project.open',{'project_id':demo['project_id']})['sources'][0]
        request={'project_id':demo['project_id'],'artifact_id':row['artifact_id'],
            'config':{**config(),'probes':[{'kind':'exec','start':512,'end':515}]}}
        with patch('romancer.native_debugger.capture_native') as launch:
            result=self.api.dispatch('debugger.capture',request)
            self.assertFalse(result['ok']);self.assertIn('execution range watches are unavailable',result['error'])
            server=MCPServer(self.api.workspace,allow_writes=True)
            try:
                server.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'review-test','version':'1'}}})
                server.handle({'jsonrpc':'2.0','method':'notifications/initialized'})
                result=server.handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'romancer_debugger_capture','arguments':request}})['result']
                self.assertTrue(result['isError']);self.assertIn('execution range watches are unavailable',result['content'][0]['text'])
            finally:server.close()
            launch.assert_not_called()

    def test_capture_is_owned_authenticated_and_paginated(self):
        result={'ok':True,'status':'CAPTURED','system_id':'nes','source_sha256':self.sha,
            'artifact_id':self.params['artifact_id'],'native_callbacks_observed':True,
            'events':[{'id':i+1,'kind':'write','address':8192,'value':i,'file_offset':None,
                'execution_context':{'pc':32768,'file_offset':16},'registers':{'pc':32771}} for i in range(130)],
            'backend':{'backend':'MesenCE','version':'2.2.1'},'route_complete':True,'omitted_events':0,'write_authorized':False}
        with patch('romancer.native_debugger.capture_native',return_value=result):
            r=self.api.dispatch('debugger.capture',{**self.params,'config':{**config(),'event_limit':200}})
        self.assertTrue(r['ok'],r);self.assertEqual(r['total_events'],130);self.assertEqual(len(r['events']),100)
        page=self.api.dispatch('debugger.get',{**self.params,'evidence_id':r['evidence_id'],'offset':100,'limit':30})
        self.assertTrue(page['ok'],page);self.assertEqual(len(page['events']),30);self.assertTrue(page['runtime_trusted'])
        self.assertEqual(page['summary']['execution_contexts'][0]['pc'],32768)
        self.assertFalse(page['summary']['causation_proven'])
        forged=self.api.dispatch('debugger.capture',{**self.params,'config':config(),'executable':'C:/evil.exe'})
        self.assertFalse(forged['ok'])

    def test_changed_source_and_historical_records_are_not_current_native_proof(self):
        from romancer.workbench_evidence import store_evidence,quarantine_restored_evidence
        report={'kind':'native-debugger-capture-v1','source_sha256':self.sha,'artifact_id':self.params['artifact_id'],
            'events':[],'status':'CAPTURED','system_id':'nes','backend':{},'route_complete':True,'omitted_events':0}
        project=self.api.project(self.params);evidence=store_evidence(project,'runtime',report)
        quarantine_restored_evidence(project)
        r=self.api.dispatch('debugger.get',{**self.params,'evidence_id':evidence['evidence_id'],'offset':0,'limit':20})
        self.assertTrue(r['ok'],r);self.assertFalse(r['runtime_trusted'])
        self.assertEqual(r['authentication'],'historical_import')
        report['source_sha256']='f'*64;evidence=store_evidence(project,'runtime',report)
        self.assertFalse(self.api.dispatch('debugger.get',{**self.params,'evidence_id':evidence['evidence_id'],'offset':0,'limit':20})['ok'])

    def test_api_and_mcp_report_actual_backend_and_typed_capabilities(self):
        from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS,_investigation_properties
        self.assertIn('debugger.capabilities',READ_OPERATIONS);self.assertIn('debugger.get',READ_OPERATIONS)
        self.assertIn('debugger.capture',WRITE_OPERATIONS)
        properties=_investigation_properties('debugger.capture')
        self.assertEqual(properties['config']['type'],'object');self.assertNotIn('executable',str(properties))
        with patch('romancer.native_debugger.verify_backend',side_effect=ValueError('not installed')):
            r=self.api.dispatch('debugger.capabilities',self.params)
        self.assertTrue(r['ok'],r);self.assertFalse(r['available']);self.assertIn('not installed',r['reason'])

    def test_instruction_sequences_are_paged_separately_without_inventing_event_order(self):
        from romancer.workbench_evidence import store_evidence
        report={'kind':'native-debugger-capture-v1','source_sha256':self.sha,'artifact_id':self.params['artifact_id'],
            'events':[],'instruction_samples':[{'id':i+1,'pc':512,'assembly':'bra $200'} for i in range(150)],
            'status':'CAPTURED','system_id':'genesis','merged_instruction_access_order_known':False}
        evidence=store_evidence(self.api.project(self.params),'runtime',report)
        result=self.api.dispatch('debugger.get',{**self.params,'evidence_id':evidence['evidence_id'],'offset':100,'limit':30})
        self.assertTrue(result['ok'],result);self.assertEqual(len(result['instruction_samples']),30)
        self.assertEqual(result['total_instruction_samples'],150);self.assertEqual(result['events'],[])
