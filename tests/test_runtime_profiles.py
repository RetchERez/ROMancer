import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shutil
import subprocess
import sys


def fake_core(path):
    raw=bytearray(256)
    if os.name=='nt':raw[:2]=b'MZ';raw[60:64]=(128).to_bytes(4,'little');raw[128:132]=b'PE\x00\x00';raw[132:134]=b'\x64\x86'
    else:raw[:6]=b'\x7fELF\x02\x01';raw[18:20]=b'\x3e\x00'
    path.write_bytes(raw)


class RuntimeProfileTests(unittest.TestCase):
    def setUp(self):
        # These tests validate profile metadata with an original non-executable binary.
        self.enterContext(patch('romancer.bundled_cores.packaged_release',return_value=False))

    def test_saved_profile_reopen_and_changed_bios_core_or_added_file_refuse(self):
        from romancer.runtime_profiles import save_profile,load_profile,validate_profile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);workspace=root/'workspace';workspace.mkdir();core=root/'core';fake_core(core);system=root/'system';system.mkdir();bios=system/'own.bin';bios.write_bytes(b'own system file')
            profile=save_profile(workspace,'segacd',str(core),{'region':'Japan'},str(system),{'up':'ArrowUp','a':'z'})
            self.assertFalse(profile['runtime_verified']);self.assertEqual(load_profile(workspace,'segacd')['profile']['options'],{'region':'Japan'})
            verified=validate_profile(profile['profile']);self.assertEqual(verified['system_files'][0]['expected_sha256'],hashlib.sha256(b'own system file').hexdigest())
            bios.write_bytes(b'changed system!')
            with self.assertRaises(ValueError):validate_profile(profile['profile'])
            bios.write_bytes(b'own system file');(system/'extra.bin').write_bytes(b'extra')
            with self.assertRaises(ValueError):validate_profile(profile['profile'])
            (system/'extra.bin').unlink();core.write_bytes(b'changed core')
            with self.assertRaises(ValueError):validate_profile(profile['profile'])

    def test_profiles_cannot_claim_native_pass_or_cross_architecture(self):
        from romancer.runtime_profiles import save_profile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'core';core.write_bytes(b'not a native library')
            with self.assertRaises(ValueError):save_profile(root,'gba',str(core),{},None,{})

    def test_preflight_measures_system_dependencies_and_refuses_changed_bytes(self):
        from romancer.runtime_session import preflight_load
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'core';core.write_bytes(b'core');game=root/'game';game.write_bytes(b'game');system=root/'system';system.mkdir();bios=system/'bios.bin';bios.write_bytes(b'bios')
            load={'core':str(core),'game':str(game),'session_dir':str(root/'session'),'system_dir':str(system),'expected_core_sha256':hashlib.sha256(b'core').hexdigest(),'expected_game_sha256':hashlib.sha256(b'game').hexdigest(),'system_files':[{'source':str(bios),'relative':'bios.bin','expected_sha256':hashlib.sha256(b'bios').hexdigest()}]}
            result=preflight_load(load,root);self.assertEqual(result['system_files'][0]['relative'],'bios.bin')
            bios.write_bytes(b'bad!')
            with self.assertRaises(ValueError):preflight_load(load,root)

    @unittest.skipUnless(shutil.which('node'),'Node is required for the actual browser module check')
    def test_browser_wav_export_has_literal_header_and_exact_pcm(self):
        module=(Path(__file__).parents[1]/'romancer/ui/runtime_setup.js').as_uri()
        script="import assert from 'node:assert/strict';import {wavFromPCM} from "+repr(module)+";const bytes=wavFromPCM('AQD//wIA/v8=',48000),view=new DataView(bytes.buffer);assert.equal(bytes.length,52);assert.equal(new TextDecoder().decode(bytes.slice(0,4)),'RIFF');assert.equal(view.getUint32(24,true),48000);assert.equal(view.getUint32(40,true),8);assert.deepEqual([...bytes.slice(44)],[1,0,255,255,2,0,254,255]);assert.throws(()=>wavFromPCM('AAAA',48000));"
        result=subprocess.run([shutil.which('node'),'--input-type=module','-e',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


@unittest.skipUnless(shutil.which('gcc') and sys.platform!='win32','native GCC fixture runs on Linux/WSL')
class NativeDependencyTests(unittest.TestCase):
    def test_worker_snapshots_system_files_and_rejects_other_option_checkpoint(self):
        from romancer.runtime_client import RuntimeClient
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'mock.so';subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST',str(Path(__file__).with_name('mock_libretro.c')),'-o',str(core)],check=True,capture_output=True)
            game=root/'own.bin';game.write_bytes(b'own game');bios=root/'own.bios';bios.write_bytes(b'own BIOS')
            load={'core':str(core),'game':str(game),'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':hashlib.sha256(game.read_bytes()).hexdigest(),'system_files':[{'source':str(bios),'relative':'bios.bin','expected_sha256':hashlib.sha256(b'own BIOS').hexdigest()}]}
            with RuntimeClient([sys.executable,'-B','-m','romancer.runtime_worker']) as client:
                first=client.request('load',**load,session_dir=str(root/'one'),core_options={'test':'one'});self.assertTrue(first['ok'],first)
                self.assertEqual((root/'one/system/bios.bin').read_bytes(),b'own BIOS')
                snapshot=client.request('save_state');self.assertIn('runtime_identity_sha256',snapshot)
                bios.write_bytes(b'changed!');self.assertEqual((root/'one/system/bios.bin').read_bytes(),b'own BIOS')
            bios.write_bytes(b'own BIOS')
            with RuntimeClient([sys.executable,'-B','-m','romancer.runtime_worker']) as client:
                second=client.request('load',**load,session_dir=str(root/'two'),core_options={'test':'two'});self.assertTrue(second['ok'],second)
                self.assertFalse(client.request('load_state',snapshot=snapshot)['ok'])
