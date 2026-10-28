import unittest
from romancer.workbench_evidence import store_evidence,quarantine_restored_evidence
from tests.test_debugger_tools import DebuggerAPITests


class FollowTests(DebuggerAPITests):
    def evidence(self,**updates):
        report={'kind':'native-debugger-capture-v1','source_sha256':self.sha,'artifact_id':self.params['artifact_id'],
            'status':'CAPTURED','system_id':'nes','route_complete':True,'omitted_events':0,
            'events':[{'id':i+1,'kind':'write','address':17,'value':i,'file_offset':None,
                'execution_context':{'pc':32768,'file_offset':16}} for i in range(130)]+[
                {'id':131,'kind':'read','address':0x9000,'value':3,'file_offset':4112,'execution_context':{'pc':32790,'file_offset':38}},
                {'id':132,'kind':'write','address':18,'value':5,'file_offset':None,'execution_context':{'pc':0x8001,'file_offset':None,'source_candidate_offset':17}}],**updates}
        return store_evidence(self.api.project(self.params),'runtime',report)['evidence_id']

    def test_full_authenticated_capture_distinguishes_writer_code_from_read_data(self):
        result=self.api.dispatch('debugger.follow',{**self.params,'evidence_id':self.evidence()})
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['writers'][0]['sampled_writes'],130)
        self.assertEqual(result['writers'][0]['file_offset'],16)
        self.assertEqual(result['source_reads'][0]['file_offset'],4112)
        self.assertEqual(result['unmapped_write_events'],1)
        self.assertFalse(result['causation_proven']);self.assertFalse(result['write_authorized'])
        self.assertEqual(result['coverage']['access_events'],132)
        self.assertIn('writer',result['writers'][0]['scope'].lower())

    def test_history_partial_and_wrong_revision_never_become_current_proof(self):
        ident=self.evidence(route_complete=False,omitted_events=17)
        result=self.api.dispatch('debugger.follow',{**self.params,'evidence_id':ident})
        self.assertTrue(result['coverage']['partial']);self.assertEqual(result['coverage']['omitted_events'],17)
        quarantine_restored_evidence(self.api.project(self.params))
        result=self.api.dispatch('debugger.follow',{**self.params,'evidence_id':ident})
        self.assertFalse(result['runtime_trusted']);self.assertEqual(result['status'],'HISTORICAL')
        self.assertFalse(self.api.dispatch('debugger.follow',{**self.params,'evidence_id':self.evidence(source_sha256='f'*64)})['ok'])

    def test_mcp_follow_is_read_only_and_typed(self):
        from romancer.mcp_server import READ_OPERATIONS,_investigation_properties
        self.assertIn('debugger.follow',READ_OPERATIONS)
        self.assertEqual(_investigation_properties('debugger.follow')['evidence_id']['type'],'string')


class SMSMappingTests(unittest.TestCase):
    def test_pinned_sms_byte_buffer_is_direct_unbanked_8k_ram(self):
        from romancer.core_memory_layout import memory_probe
        from romancer.core_pins import CORE_PINS
        packet={'core_sha256':CORE_PINS['genesis']['sha256'],'region':2,'region_size':8192}
        result=memory_probe('sms',packet,0x123,2)
        self.assertEqual(result['cpu_addresses'],[0xc123,0xc124]);self.assertEqual(result['physical_probe'],{'kind':'write','start':0x123,'end':0x124,'domain':'smsWorkRam'})
        self.assertFalse(result['requires_observed_bank'])
        with self.assertRaises(ValueError):memory_probe('sms',{**packet,'region_size':65536},0,1)
