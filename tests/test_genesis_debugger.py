from pathlib import Path
import importlib.util
import tempfile
import unittest
import os
from tests.test_native_debugger import config


@unittest.skipUnless(os.environ.get('ROMANCER_GENESIS_TEST_OBSERVER'),'Reviewed native Genesis observer not supplied')
class GenesisObserverLifetimeTests(unittest.TestCase):
    def test_repeated_captures_exit_cleanly_after_snapshot_and_map_watches(self):
        from romancer.boot_fixtures import make_boot_fixture
        from romancer import workbench_projects as projects
        from romancer.genesis_debugger import capture_genesis
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rom=root/'original.md';rom.write_bytes(make_boot_fixture('genesis')['data'])
            project=Path(projects.create_project(root/'workspace','Observer lifetime')['path'])
            row=projects.register_source(project,rom,None)
            request={'steps':[{'frames':240,'buttons':[],'port':0}],
                'probes':[{'kind':'read','start':0x1000,'end':0x101f},{'kind':'write','start':0xc00000,'end':0xc0001f}],
                'start_frame':0,'event_limit':2000,'instruction_limit':20000000,'timeout':60,'graphics_snapshot':True}
            for attempt in range(5):
                with self.subTest(attempt=attempt):
                    result=capture_genesis(project,row,request,root=Path(os.environ['ROMANCER_GENESIS_TEST_OBSERVER']))
                    self.assertEqual(result['worker_exit_code'],0)
                    self.assertTrue(result['route_complete']);self.assertTrue(result['graphics_snapshot']['frame'])


class GenesisDebuggerTests(unittest.TestCase):
    def test_bounded_observer_suspends_collection_before_creating_native_handles(self):
        from romancer.genesis_debugger import make_script
        script=make_script(self.request(),'lifetime-test')
        self.assertLess(script.index("collectgarbage('stop')"),script.index('manager.machine'))
        self.assertEqual(script.count("collectgarbage('stop')"),1)
        self.assertNotIn("collectgarbage('restart')",script)

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

    def test_execution_range_probe_is_rejected_instead_of_silently_ignored(self):
        from romancer.debugger_protocol import validate_capture
        request=self.request(probes=[{'kind':'exec','start':0x200,'end':0x203}])
        with self.assertRaisesRegex(ValueError,'execution.*unavailable'):
            validate_capture('genesis',request)
        self.assertFalse(self.module().backend_capabilities()['execution_range_probes'])
        self.assertTrue(self.module().backend_capabilities()['instruction_events'])
        self.assertEqual(validate_capture('nes',request)['probes'][0]['kind'],'exec')

    def test_missing_backend_is_rejected(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):m.verify_backend(Path(d))
