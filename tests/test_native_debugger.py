"""Protocol/boundary tests; genuine native acceptance is recorded separately."""
from pathlib import Path
import copy
import importlib.util
import tempfile
import unittest


def config():
    return {'steps':[{'frames':4,'buttons':[],'port':0}],
        'probes':[{'kind':'write','start':0x2000,'end':0x2007}],
        'event_limit':32,'instruction_limit':2000000,'timeout':10}


class NativeDebuggerTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.native_debugger'),'genuine native debugger adapter is missing')
        from romancer import native_debugger
        return native_debugger

    def test_capture_request_is_bounded_system_scoped_and_has_no_code_or_paths(self):
        m=self.module();v=m.validate_capture('nes',config());self.assertEqual(v['frames'],4)
        for key,value in [('event_limit',2001),('instruction_limit',20000001),('timeout',61),('script','print(1)'),('executable','C:/evil.exe')]:
            bad={**config(),key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_capture('nes',bad)
        for steps in [[],[{'frames':0,'buttons':[],'port':0}],[{'frames':4,'buttons':['unknown'],'port':0}],[{'frames':4,'buttons':[],'port':1}]]:
            with self.subTest(steps=steps),self.assertRaises(ValueError):m.validate_capture('nes',{**config(),'steps':steps})
        with self.assertRaises(ValueError):m.validate_capture('nes',{**config(),'probes':[{'kind':'write','start':0,'end':0x10000}]})
        self.assertFalse(m.backend_capabilities('genesis')['instruction_events'])

    def test_protocol_keeps_execution_context_separate_from_post_access_register_pc(self):
        m=self.module();raw=bytearray(16+16384+8192);raw[:6]=b'NES\x1a\x01\x01'
        text='BEGIN\t1\tnonce\tnes\nDOMAIN\tnesPrgRom\t20\nE\t1\twrite\t8192\t0\t32774\t-1\t-1\t20\t6\t0\nR\t1\tpc\tn\t32777\nEND\t4\t1\t0\t100\tframes\n'
        r=m.parse_capture(text,'nonce','nes',bytes(raw),config())
        e=r['events'][0];self.assertEqual(e['execution_context']['pc'],32774)
        self.assertEqual(e['execution_context']['file_offset'],22)
        self.assertEqual(e['registers']['pc'],32777)
        self.assertIsNone(e['access_width']);self.assertIsNone(e['actor'])
        self.assertFalse(e['causation_proven']);self.assertTrue(r['native_callbacks_observed'])

    def test_ambiguous_or_non_rom_mappings_never_become_file_offsets(self):
        m=self.module();raw=bytes(32768)
        text='BEGIN\t1\tnonce\tgb\nDOMAIN\tgbBootRom\t21\nDOMAIN\tgbPrgRom\t22\nE\t1\tread\t256\t0\t100\t21\t0\t21\t100\t0\nE\t2\tread\t16384\t0\t200\t22\t32768\t22\t200\t0\nEND\t4\t2\t0\t100\tframes\n'
        c={**config(),'probes':[{'kind':'read','start':0,'end':65535}]}
        r=m.parse_capture(text,'nonce','gb',raw,c)
        self.assertIsNone(r['events'][0]['file_offset']);self.assertIsNone(r['events'][1]['file_offset'])
        self.assertIsNone(r['events'][0]['execution_context']['file_offset'])

    def test_nonce_end_record_event_count_probe_scope_and_budget_are_verified(self):
        m=self.module();base='BEGIN\t1\tnonce\tnes\nE\t1\twrite\t8192\t0\t32774\t-1\t-1\t-1\t-1\t0\nEND\t4\t1\t0\t100\tframes\n'
        for text in [base.replace('nonce','other'),base.split('END')[0],base.replace('END\t4\t1','END\t4\t2'),base.replace('\t8192\t','\t1\t'),base.replace('END\t4','END\t3'),base+'EXTRA\tbad\n']:
            with self.subTest(text=text),self.assertRaises(ValueError):m.parse_capture(text,'nonce','nes',bytes(32768),config())
        limited=base.replace('END\t4\t1\t0\t100\tframes','END\t1\t1\t5\t2000000\tinstruction_limit')
        r=m.parse_capture(limited,'nonce','nes',bytes(32768),config())
        self.assertEqual(r['status'],'BUDGET_EXCEEDED');self.assertFalse(r['route_complete']);self.assertEqual(r['omitted_events'],5)

    def test_generated_lua_is_observational_and_uses_a_fixed_output_file(self):
        m=self.module();script=m.make_script('nes',config(),'a'*32)
        self.assertIn('emu.addMemoryCallback',script);self.assertIn('emu.setInput',script)
        self.assertIn('emu.stop(0)',script);self.assertNotIn('emu.exit',script)
        self.assertNotIn('emu.write',script);self.assertNotIn('loadfile',script)
        self.assertIn('trace.tsv',script);self.assertIn('instruction_limit',script)
        settings=m.portable_settings('gbc')
        self.assertFalse(settings['Debug']['ScriptWindow']['AllowNetworkAccess'])
        self.assertTrue(settings['Debug']['ScriptWindow']['AllowIoOsAccess'])
        self.assertEqual(settings['Gameboy']['Model'],5)

    def test_missing_or_changed_backend_is_rejected_before_execution(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError):m.verify_backend(root)
            (root/'Mesen.exe').write_bytes(b'not an emulator')
            with self.assertRaises(ValueError):m.verify_backend(root)

    def test_native_physical_snes_rom_mapping_uses_the_checked_payload(self):
        from romancer.boot_fixtures import make_boot_fixture
        m=self.module();raw=make_boot_fixture('snes')['data']
        text='BEGIN\t1\tnonce\tsnes\nDOMAIN\tsnesPrgRom\t1\nE\t1\tread\t36864\t224\t32768\t1\t4096\t1\t0\t0\nEND\t4\t1\t0\t100\tframes\n'
        c={**config(),'probes':[{'kind':'read','start':36864,'end':36864}]}
        r=m.parse_capture(text,'nonce','snes',raw,c)
        self.assertEqual(r['events'][0]['file_offset'],4096)
        self.assertTrue(r['events'][0]['source_byte_agrees'])

    def test_capture_window_skips_boot_noise_and_is_checked_on_output(self):
        m=self.module();c={**config(),'start_frame':2};self.assertEqual(m.validate_capture('nes',c)['start_frame'],2)
        self.assertIn('frames<2',m.make_script('nes',c,'nonce'))
        text='BEGIN\t1\tnonce\tnes\nE\t1\twrite\t8192\t0\t32774\t-1\t-1\t-1\t-1\t0\nEND\t4\t1\t0\t100\tframes\n'
        with self.assertRaises(ValueError):m.parse_capture(text,'nonce','nes',bytes(32768),c)
        with self.assertRaises(ValueError):m.validate_capture('nes',{**config(),'start_frame':4})

    def test_physical_ram_probe_follows_cpu_mirrors_without_inventing_rom_offsets(self):
        m=self.module();c={**config(),'probes':[{'kind':'write','start':16,'end':16,'domain':'nesInternalRam'}]}
        m.validate_capture('nes',c)
        self.assertIn('nesInternalRam',m.make_script('nes',c,'nonce'))
        text='BEGIN\t1\tnonce\tnes\nDOMAIN\tnesInternalRam\t42\nE\t1\twrite\t2064\t1\t32774\t42\t16\t-1\t-1\t0\nEND\t4\t1\t0\t100\tframes\n'
        r=m.parse_capture(text,'nonce','nes',bytes(32768),c)
        self.assertEqual(r['events'][0]['address'],0x810);self.assertEqual(r['events'][0]['physical_offset'],16)
        self.assertIsNone(r['events'][0]['file_offset'])
        with self.assertRaises(ValueError):m.parse_capture(text.replace('\t42\t16\t','\t42\t17\t'),'nonce','nes',bytes(32768),c)
