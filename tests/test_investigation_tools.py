import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from romancer.boot_fixtures import make_boot_fixture
from romancer.workbench_api import WorkbenchAPI
from tests.test_observation_series import observation


class InvestigationAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.api=WorkbenchAPI(self.root/'workspace');self.addCleanup(self.api.close)
        settings=self.api.dispatch('settings.get',{});values={**settings['values'],'autoDeepScan':False}
        self.assertTrue(self.api.dispatch('settings.save',{'revision':settings['revision'],'values':values})['ok'])
        p=self.api.dispatch('project.create',{'name':'Universal investigation'})
        self.original=self.root/'Unnamed cartridge.nes';self.original.write_bytes(make_boot_fixture('nes')['data'])
        source=self.api.dispatch('source.import',{'project_id':p['project_id'],'path':str(self.original),'system':None})
        self.params={'project_id':p['project_id'],'artifact_id':source['artifact_id']};self.source=source

    def packet(self,n,value):
        p=observation(bytes([n])+value.to_bytes(2,'little')+b'\0',n)['snapshot'];p['game_sha256']=self.source['sha256'];return p

    def start(self):
        return self.api.dispatch('investigations.start',{**self.params,'title':'The number I am watching','region':2,'offset':16,'length':4,'value':1000})

    def test_owned_series_is_durable_and_rejects_raw_client_observations(self):
        before=self.original.read_bytes()
        with patch.object(self.api.studio,'observe',return_value=self.packet(1,1000)):
            started=self.start()
        self.assertTrue(started['ok'],started);self.assertEqual(started['status'],'NEEDS_MORE')
        ident=started['investigation_id']
        with patch.object(self.api.studio,'observe',return_value=self.packet(2,950)):
            captured=self.api.dispatch('investigations.capture',{**self.params,'investigation_id':ident,'label':'After the change','value':950,'relation':'decreased','delta':None})
        self.assertTrue(captured['ok'],captured);self.assertNotEqual(captured['investigation_id'],ident)
        self.assertTrue(any(c['offset']==17 and c['width']==2 and c['model']=='exact' for c in captured['candidates']))
        read=self.api.dispatch('investigations.get',{**self.params,'investigation_id':captured['investigation_id']})
        self.assertEqual(read['history'],captured['history']);self.assertTrue(read['runtime_trusted'])
        self.assertNotIn('raw_hex',str(read));self.assertEqual(before,self.original.read_bytes())
        forged=self.api.dispatch('investigations.start',{**self.params,'title':'Forged','region':2,'offset':16,'length':4,'value':1,'snapshot':self.packet(3,1)})
        self.assertFalse(forged['ok'])

    def test_stale_epoch_and_different_selected_artifact_are_blocked(self):
        with patch.object(self.api.studio,'observe',return_value=self.packet(1,1000)):started=self.start()
        self.assertTrue(started['ok'],started)
        packet=self.packet(2,950);packet['epoch']=1
        with patch.object(self.api.studio,'observe',return_value=packet):
            r=self.api.dispatch('investigations.capture',{**self.params,'investigation_id':started['investigation_id'],'label':'After reset','value':950,'relation':'decreased','delta':None})
        self.assertFalse(r['ok']);self.assertIn('state',r['error'])
        other=self.api.dispatch('source.import',{'project_id':self.params['project_id'],'path':str(self.original),'system':None})
        r=self.api.dispatch('investigations.get',{**self.params,'artifact_id':other['artifact_id'],'investigation_id':started['investigation_id']})
        self.assertFalse(r['ok'])

    def test_authenticated_history_cannot_be_replaced_or_reused_as_fresh_after_restore(self):
        from romancer.workbench_evidence import quarantine_restored_evidence
        with patch.object(self.api.studio,'observe',return_value=self.packet(1,1000)):started=self.start()
        self.assertTrue(started['ok'],started);project=self.api.project(self.params)
        quarantine_restored_evidence(project)
        historic=self.api.dispatch('investigations.get',{**self.params,'investigation_id':started['investigation_id']})
        self.assertTrue(historic['ok'],historic);self.assertFalse(historic['runtime_trusted'])
        with patch.object(self.api.studio,'observe',side_effect=AssertionError('restored history cannot append native evidence')):
            r=self.api.dispatch('investigations.capture',{**self.params,'investigation_id':started['investigation_id'],'label':'New','value':950,'relation':'decreased','delta':None})
        self.assertFalse(r['ok']);self.assertIn('historical',r['error'])
        import json
        path=project/'reports'/(started['investigation_id']+'.json');record=json.loads(path.read_bytes());record['report']['title']='Forged';path.write_text(json.dumps(record),encoding='utf-8')
        self.assertFalse(self.api.dispatch('investigations.get',{**self.params,'investigation_id':started['investigation_id']})['ok'])

    def test_ai_operations_describe_actual_persistence_and_typed_inputs(self):
        from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS,_investigation_properties
        self.assertIn('investigations.get',READ_OPERATIONS)
        self.assertTrue({'investigations.start','investigations.capture'}<=WRITE_OPERATIONS)
        properties=_investigation_properties('investigations.capture')
        self.assertEqual(properties['value']['type'],['integer','null'])
        self.assertNotIn('snapshot',properties)

    def correlated(self):
        from romancer.core_pins import CORE_PINS
        def packet(n,value):
            p=self.packet(n,value);p.update(core_sha256=CORE_PINS['nes']['sha256'],region_size=2048);return p
        with patch.object(self.api.studio,'observe',return_value=packet(1,1000)):started=self.start()
        with patch.object(self.api.studio,'observe',return_value=packet(2,950)):
            result=self.api.dispatch('investigations.capture',{**self.params,'investigation_id':started['investigation_id'],
                'label':'Changed','value':950,'relation':'decreased','delta':None})
        self.assertTrue(result['ok'],result)
        candidate=next(c for c in result['candidates'] if c['offset']==17 and c['width']==2 and c['model']=='exact')
        return {**self.params,'investigation_id':result['investigation_id'],'candidate_id':candidate['candidate_id']}

    def test_candidate_becomes_a_source_bound_physical_watch_without_game_profile(self):
        p=self.correlated();result=self.api.dispatch('investigations.probe',p)
        self.assertTrue(result['ok'],result);self.assertEqual(result['source_sha256'],self.source['sha256'])
        self.assertEqual(result['physical_probe'],{'kind':'write','start':17,'end':18,'domain':'nesInternalRam'})
        self.assertFalse(result['same_runtime_state_claimed']);self.assertFalse(result['causation_proven'])
        self.assertEqual(result['candidate']['candidate_id'],p['candidate_id'])
        forged=self.api.dispatch('investigations.probe',{**p,'candidate_id':'f'*64})
        self.assertFalse(forged['ok'])
        from romancer.workbench_evidence import quarantine_restored_evidence
        quarantine_restored_evidence(self.api.project(p))
        self.assertFalse(self.api.dispatch('investigations.probe',p)['ok'])

    def test_native_investigation_derives_probe_server_side_and_retains_provenance(self):
        p=self.correlated();replay={'steps':[{'frames':8,'buttons':[],'port':0}],
            'start_frame':4,'event_limit':30,'instruction_limit':100000,'timeout':10}
        def native(project,row,config,**kwargs):
            self.assertEqual(config['probes'],[{'kind':'write','start':17,'end':18,'domain':'nesInternalRam'}])
            return {'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'system_id':'nes',
                'events':[],'status':'CAPTURED','route_complete':True}
        with patch('romancer.native_debugger.capture_native',side_effect=native) as worker:
            result=self.api.dispatch('debugger.investigate',{**p,'replay':replay})
        self.assertTrue(result['ok'],result);worker.assert_called_once()
        self.assertEqual(result['investigation_link']['candidate_id'],p['candidate_id'])
        self.assertFalse(result['investigation_link']['same_runtime_state_claimed'])
        with patch('romancer.native_debugger.capture_native',side_effect=AssertionError('invalid replay must not execute')):
            self.assertFalse(self.api.dispatch('debugger.investigate',{**p,'replay':{**replay,'probes':[]}})['ok'])

    def test_linked_ai_operations_have_typed_evidence_inputs_and_no_client_mapping(self):
        from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS,_investigation_properties
        self.assertIn('investigations.probe',READ_OPERATIONS);self.assertIn('debugger.investigate',WRITE_OPERATIONS)
        props=_investigation_properties('debugger.investigate')
        self.assertIn('candidate_id',props);self.assertNotIn('probes',props['replay']['properties'])
