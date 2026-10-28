import unittest
from romancer.debugger_protocol import validate_capture,parse_capture
from romancer.native_debugger import make_script
from tests.test_native_debugger import config

class FocusTests(unittest.TestCase):
    def request(self):return {**config(),'stop':{'occurrence':1}}
    def text(self):return 'BEGIN\t1\tnonce\tnes\nE\t1\twrite\t8192\t0\t32774\t-1\t-1\t-1\t-1\t0\nR\t1\tpc\tn\t32777\nEND\t0\t1\t0\t100\taccess\n'
    def test_native_stop_is_authenticated_to_requested_access_and_keeps_context(self):
        r=parse_capture(self.text(),'nonce','nes',bytes(32768),self.request());self.assertEqual(r['status'],'STOPPED');self.assertFalse(r['route_complete']);self.assertEqual(r['focus']['event']['registers']['pc'],32777);self.assertTrue(r['focus']['matched'])
        self.assertIn('emitted>=1',make_script('nes',self.request(),'nonce'))
    def test_forged_ordinal_budget_and_missed_access_never_claim_a_match(self):
        for text,request in [(self.text(),config()),(self.text(),{**config(),'stop':{'occurrence':2}}),(self.text().replace('\t0\t100\taccess','\t1\t100\taccess'),self.request())]:
            with self.subTest(text=text),self.assertRaises(ValueError):parse_capture(text,'nonce','nes',bytes(32768),request)
        r=parse_capture(self.text().replace('END\t0\t1\t0\t100\taccess','END\t4\t1\t0\t100\tframes'),'nonce','nes',bytes(32768),{**config(),'stop':{'occurrence':2}});self.assertEqual(r['status'],'NO_MATCH');self.assertFalse(r['focus']['matched'])
    def test_focus_uses_one_explicit_probe_and_bounded_occurrence_without_snapshot(self):
        for request in ({**config(),'stop':{'occurrence':0}},{**config(),'stop':{'occurrence':33}},{**config(),'stop':{'occurrence':True}},{**self.request(),'probes':config()['probes']*2},{**self.request(),'graphics_snapshot':True},{**config(),'stop':{'code':'anything'}}):
            with self.subTest(request=request),self.assertRaises(ValueError):validate_capture('nes',request)
    def test_genesis_retains_real_bus_context_at_access_stop(self):
        from tests.test_genesis_debugger import GenesisDebuggerTests
        from romancer.genesis_debugger import parse_capture as parse,make_script as script
        t=GenesisDebuggerTests();request={**t.request(),'stop':{'occurrence':1}};text=t.text().replace('END\t4\t1\t0','END\t0\t1\t0\taccess')
        r=parse(text,'','nonce',bytes(65536),request);self.assertEqual(r['status'],'STOPPED');self.assertTrue(r['focus']['matched']);self.assertEqual(r['focus']['event']['execution_context']['pc'],512)
        self.assertIn('emitted>=1',script(request,'nonce'))
