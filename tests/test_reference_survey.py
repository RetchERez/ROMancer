import unittest
from tests.test_debugger_tools import DebuggerAPITests
from tests.test_data_relocation import DataRelocationTests

class SurveyTests(unittest.TestCase):
    setUp=DebuggerAPITests.setUp
    def test_exact_encoding_has_explicit_coverage_and_never_claims_reference_completeness(self):
        from romancer.reference_survey import survey_references
        raw=b'\0\x00\x10\0\x08\xff\x00\x10\0\x08'
        r=survey_references(raw,0x1000,4,'little',0x08000000,1,start=100)
        self.assertEqual([v['offset'] for v in r['candidates']],[101,106])
        self.assertEqual(r['tested_range'],{'offset':100,'length':10});self.assertFalse(r['references_complete'])
        aligned=survey_references(raw,0x1000,4,'little',0x08000000,2,start=100)
        self.assertEqual([v['offset'] for v in aligned['candidates']],[106])
        for args in [(True,4,'little',0,1),(0,1,'little',0,1),(0,4,'invalid',0,1)]:
            with self.assertRaises(ValueError):survey_references(raw,*args)
    def test_budget_reports_truncation_instead_of_losing_coverage(self):
        from romancer.reference_survey import survey_references
        r=survey_references(b'\x01\0'*300,1,2,'little',0,2)
        self.assertEqual(len(r['candidates']),256);self.assertEqual(r['total_matches'],300);self.assertTrue(r['truncated'])
    def test_api_mcp_and_source_identity_are_consistent(self):
        result=self.api.dispatch('references.survey',{**self.params,'target_offset':0x1000,'width':2,'endian':'little','base':0,'offset':0,'length':8192,'alignment':1})
        self.assertTrue(result['ok'],result);self.assertEqual(result['source_sha256'],self.sha)
        from romancer.mcp_server import READ_OPERATIONS,_investigation_properties
        self.assertIn('references.survey',READ_OPERATIONS);self.assertEqual(_investigation_properties('references.survey')['width']['minimum'],2)

class SMSRelocationTests(unittest.TestCase):
    def test_declared_same_bank_sms_data_moves_preserve_header_and_boot_regions(self):
        from romancer.data_relocation import prepare_edits
        raw=bytearray(b'\xff'*32768);raw[0x1000:0x1010]=bytes(range(16));raw[0x400:0x402]=(0x1000).to_bytes(2,'little');raw[0x7ff0:0x7ff8]=b'TMR SEGA'
        spec=DataRelocationTests().spec(source_offset=0x1000,source_length=16,target_offset=0x1800,target_capacity=32,bank_size=16384,bank_origin=0,references=[{'offset':0x400,'width':2,'endian':'little','base':0,'target_delta':0}])
        r=prepare_edits(bytes(raw),'sms',spec);self.assertEqual(r['relocation']['pointer_updates'][0]['after'],0x1800)
        for updates in ({'bank_size':0},{'target_offset':0x7fe0,'target_capacity':32},{'source_offset':0},{'references':[{'offset':0x7ff0,'width':2,'endian':'little','base':0,'target_delta':0}]}):
            with self.subTest(updates=updates),self.assertRaises(ValueError):prepare_edits(bytes(raw),'sms',{**spec,**updates})
