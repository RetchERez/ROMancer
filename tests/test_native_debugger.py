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
        self.assertTrue(m.backend_capabilities('genesis')['instruction_events'])
        self.assertFalse(m.backend_capabilities('genesis')['observed_mapping'])

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

    def test_owned_gameboy_capture_does_not_blend_a_fresh_frame_with_black(self):
        m=self.module()
        for system,model in [('gb',4),('gbc',5)]:
            settings=m.portable_settings(system)
            self.assertIs(settings['Gameboy'].get('BlendFrames'),False)
            self.assertEqual(settings['Gameboy']['Model'],model)
            self.assertFalse(settings['Debug']['ScriptWindow']['AllowNetworkAccess'])
            settings['Gameboy']['BlendFrames']=True
            self.assertIs(m.portable_settings(system)['Gameboy']['BlendFrames'],False)
        self.assertNotIn('BlendFrames',m.portable_settings('nes')['Gameboy'])

    def test_sms_physical_rom_and_video_memory_are_observed_without_cpu_address_guessing(self):
        m=self.module();self.assertTrue(m.backend_capabilities('sms')['supported_system'])
        cfg={'steps':[{'frames':4,'buttons':['one'],'port':0}],'probes':[{'kind':'read','domain':'smsPrgRom','start':0x100,'end':0x101},{'kind':'write','domain':'smsVideoRam','start':0,'end':31}],'event_limit':32,'instruction_limit':2000000,'timeout':10}
        script=m.make_script('sms',cfg,'a'*32);self.assertIn('smsVideoRam',script)
        raw=bytearray(32768);raw[0x7ff0:0x7ff8]=b'TMR SEGA';raw[0x7fff]=0x4c;raw[0x100]=42
        text='BEGIN\t1\tnonce\tsms\nDOMAIN\tsmsPrgRom\t70\nDOMAIN\tsmsVideoRam\t71\nE\t1\tread\t256\t42\t0\t70\t256\t70\t0\t0\nE\t2\twrite\t0\t42\t3\t71\t0\t70\t3\t0\nEND\t4\t2\t0\t100\tframes\n'
        r=m.parse_capture(text,'nonce','sms',bytes(raw),cfg);self.assertEqual(r['events'][0]['file_offset'],256);self.assertTrue(r['events'][0]['source_byte_agrees']);self.assertIsNone(r['events'][1]['file_offset']);self.assertEqual(r['events'][1]['domain'],'smsVideoRam');self.assertFalse(r['events'][1]['causation_proven'])

    def test_native_operation_details_preserve_dma_and_callback_width_without_inventing_a_channel(self):
        m=self.module();raw=bytearray(32768);raw[256]=42
        cfg={**config(),'probes':[{'kind':'read','start':256,'end':256}]}
        text='BEGIN\t1\tnonce\tgb\nDOMAIN\tgbPrgRom\t20\nE\t1\tread\t256\t42\t300\t20\t256\t20\t300\t0\nN\t1\tDmaRead\t1\t20\t256\nEND\t4\t1\t0\t100\tframes\n'
        result=m.parse_capture(text,'nonce','gb',bytes(raw),cfg);e=result['events'][0];self.assertEqual(e['operation_kind'],'DmaRead');self.assertEqual(e['actor'],'dma');self.assertEqual(e['callback_value_bytes'],1);self.assertIsNone(e['access_width']);self.assertIsNone(e['dma_channel']);self.assertEqual(e['file_offset'],256)
        with self.assertRaises(ValueError):m.parse_capture(text.replace('DmaRead','DmaWrite'),'nonce','gb',bytes(raw),cfg)

    def test_owned_cleanup_retries_a_transient_loader_lock_and_refuses_other_directories(self):
        from unittest.mock import patch
        import shutil
        from romancer.native_debugger import remove_owned_job
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder);job=parent/('a'*32);job.mkdir();(job/'owned.txt').write_text('owned');real=shutil.rmtree;calls=[]
            def transient(path):
                calls.append(path)
                if len(calls)==1:raise PermissionError('simulated Windows loader lock')
                return real(path)
            with patch('romancer.native_debugger.shutil.rmtree',side_effect=transient):remove_owned_job(job,parent)
            self.assertFalse(job.exists());self.assertEqual(len(calls),2)
            foreign=parent/'user-project';foreign.mkdir();(foreign/'keep').write_text('keep')
            with self.assertRaises(ValueError):remove_owned_job(foreign,parent)
            self.assertTrue((foreign/'keep').is_file())

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
