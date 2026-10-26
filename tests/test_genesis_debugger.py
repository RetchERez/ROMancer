from pathlib import Path
import importlib.util
import tempfile
import unittest
from tests.test_native_debugger import config


class GenesisDebuggerTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.genesis_debugger'),'Genesis native access capture is missing')
        from romancer import genesis_debugger
        return genesis_debugger

    def request(self,**overrides):
        return {**config(),'steps':[{'frames':4,'buttons':['b'],'port':0}],
            'probes':[{'kind':'write','start':0x103,'end':0x103,'domain':'genesisWorkRam'}],**overrides}

    def text(self):
        return 'BEGIN\t1\tnonce\tgenesis\nE\t1\twrite\t16711939\t86\t512\t0\t16711938\t22102\t255\t13fc005600ff010313fc005600ff0102\nEND\t4\t1\t0\n'

    def test_native_lane_event_retains_cpu_context_and_candidate_only_source_association(self):
        m=self.module();raw=bytes(512)+bytes.fromhex('13fc005600ff010313fc005600ff0102')+bytes(100)
        r=m.parse_capture(self.text(),'','nonce',raw,self.request())
        e=r['events'][0];self.assertEqual(e['address'],0xff0103);self.assertEqual(e['physical_offset'],0x103)
        self.assertEqual(e['value'],86);self.assertEqual(e['raw_mask'],255);self.assertEqual(e['bus_width'],16)
        self.assertIsNone(e['file_offset']);self.assertIsNone(e['execution_context']['file_offset'])
        self.assertEqual(e['execution_context']['source_candidate_offset'],512)
        self.assertEqual(e['execution_context']['source_association'],'UNIQUE_PATTERN_MATCH_CANDIDATE')
        self.assertFalse(e['causation_proven']);self.assertTrue(r['route_complete'])

    def test_pattern_ambiguity_and_ram_code_never_become_verified_rom_mapping(self):
        m=self.module();code=bytes.fromhex('13fc005600ff010313fc005600ff0102')
        r=m.parse_capture(self.text(),'','nonce',code+code,self.request())
        self.assertIsNone(r['events'][0]['execution_context']['source_candidate_offset'])
        self.assertEqual(r['events'][0]['execution_context']['source_association'],'AMBIGUOUS_PATTERN_MATCH')

    def test_incomplete_forged_outside_window_or_bad_lane_records_are_rejected(self):
        m=self.module()
        for text in [self.text().replace('nonce','forged'),self.text().split('END')[0],
                self.text().replace('END\t4\t1','END\t4\t2'),self.text().replace('\t16711939\t','\t16711938\t'),
                self.text().replace('\t22102\t255\t','\t22102\t65280\t'),self.text()+'E\tbad\n']:
            with self.subTest(text=text),self.assertRaises(ValueError):m.parse_capture(text,'','nonce',bytes(65536),self.request())
        with self.assertRaises(ValueError):m.parse_capture(self.text(),'','nonce',bytes(65536),self.request(start_frame=1))

    def test_native_instruction_samples_are_bounded_separate_and_not_memory_data_reads(self):
        m=self.module();instructions='EXEC n=1 curpc=000200 pc=000202\n000200: move #$2700, SR\nEXEC n=2 curpc=000204 pc=000206\n000204: bra $204\n'
        r=m.parse_capture(self.text(),instructions,'nonce',bytes(65536),self.request())
        self.assertEqual(len(r['instruction_samples']),2);self.assertEqual(r['instruction_samples'][0]['pc'],512)
        self.assertEqual(r['instruction_samples'][0]['assembly'],'move #$2700, SR')
        self.assertEqual(len(r['events']),1);self.assertFalse(r['merged_instruction_access_order_known'])
        with self.assertRaises(ValueError):m.parse_capture(self.text(),instructions.replace('n=2','n=8'),'nonce',bytes(65536),self.request())

    def test_original_adapter_filters_debug_reads_aligns_taps_and_has_safe_trace_stop(self):
        m=self.module();script=m.make_script(self.request(),'nonce')
        self.assertIn('manager.machine:side_effects_disabled()',script)
        self.assertIn('observer_depth>0',script);self.assertIn('memory_value',script)
        self.assertNotIn('read_direct_u8',script);self.assertIn('rpset',script);self.assertIn('rpdisable',script)
        self.assertIn('noloop',script);self.assertIn('CURPC',script)
        self.assertNotIn('write_u',script)
        args=m.arguments(Path('C:/owned/job'),4,10)
        self.assertIn('-debugger',args);self.assertEqual(args[args.index('-debugger')+1],'none')
        self.assertEqual(args[args.index('-video')+1],'none');self.assertIn('-noreadconfig',args)
        self.assertIn('-noplugins',args);self.assertIn('-noconsole',args)

    def test_missing_backend_is_rejected(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):m.verify_backend(Path(d))
