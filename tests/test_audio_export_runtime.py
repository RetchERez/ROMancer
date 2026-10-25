import hashlib
import importlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave


class RuntimeAudioTests(unittest.TestCase):
    def service(self):
        try:module=importlib.import_module('romancer.audio_export_runtime')
        except ModuleNotFoundError:module=None
        self.assertIsNotNone(module,'owned worker-to-WAV capture is missing')
        return module.capture_audio

    def test_malformed_config_refuses_before_session_or_output(self):
        capture=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=capture({'schema_version':1,'load':{},'steps':[],'timeout_seconds':True},{},root/'audio.wav',base=root,output_format='wav')
            self.assertFalse(result['ok']);self.assertFalse((root/'audio.wav').exists())
            self.assertEqual(list(root.iterdir()),[])

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'native compiled Linux audio pipeline')
    def test_real_compiled_core_wav_and_clean_worker_exit(self):
        capture=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'mock.so';game=root/'game.bin';game.write_bytes(b'fixture')
            subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST','tests/mock_libretro.c','-o',str(core)],check=True)
            config={'schema_version':1,'load':{'core':str(core),'game':str(game),'session_dir':str(root/'session'),
                'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':hashlib.sha256(game.read_bytes()).hexdigest()},
                'steps':[{'frames':1,'buttons':[],'port':0}],'timeout_seconds':10}
            raw=bytes.fromhex('0080ff7fffff0100000000003412cced')
            baseline={'schema_version':1,'id':'mock-four-frames','version':'1','sample_rate':44100,
                      'expected_duration':{'numerator':1,'denominator':11025},'tolerance_samples':0,'expected_pcm_sha256':hashlib.sha256(raw).hexdigest(),
                      'provenance':{'origin':'synthetic_fixture','note':'literal callback samples','reference':None}}
            result=capture(config,baseline,root/'audio.wav',base=root,output_format='wav')
            self.assertTrue(result['ok'],result);self.assertEqual(result['worker_exit_code'],0)
            self.assertEqual(result['capture_origin'],'runtime_worker')
            with wave.open(str(root/'audio.wav'),'rb') as audio:self.assertEqual(audio.readframes(4),raw)
