import hashlib
import importlib
from pathlib import Path
import struct
import tempfile
import unittest
import wave


class AudioExportTests(unittest.TestCase):
    def service(self):
        try: module=importlib.import_module('romancer.audio_export')
        except ModuleNotFoundError:module=None
        self.assertIsNotNone(module,'PCM timing and WAV export are missing')
        return module

    def fixture(self,root):
        raw=bytes.fromhex('0080ff7fffff0100000000003412cced')
        source=root/'original.pcm';source.write_bytes(raw)
        provenance={'origin':'supplied_pcm','note':'handwritten stereo samples','reference':None}
        descriptor={'schema_version':1,'source':{'sha256':hashlib.sha256(raw).hexdigest(),'size':16},'format':'s16le','channels':2,'sample_rate':44100,'provenance':provenance}
        baseline={'schema_version':1,'id':'literal-four-samples','version':'1','sample_rate':44100,
                  'expected_duration':{'numerator':1,'denominator':11025},'tolerance_samples':0,
                  'expected_pcm_sha256':hashlib.sha256(raw).hexdigest(),
                  'provenance':{**provenance,'origin':'synthetic_fixture'}}
        return source,descriptor,baseline

    def test_independent_wave_reader_and_literal_header(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,descriptor,baseline=self.fixture(root)
            result=service.export_audio(source,root/'audio.wav',descriptor,baseline,output_format='wav')
            self.assertTrue(result['ok'],result)
            with wave.open(str(root/'audio.wav'),'rb') as audio:
                self.assertEqual((audio.getnchannels(),audio.getsampwidth(),audio.getframerate(),audio.getnframes()),(2,2,44100,4))
                self.assertEqual(audio.readframes(4),source.read_bytes())
            raw=(root/'audio.wav').read_bytes()
            self.assertEqual(raw[:12],b'RIFF'+struct.pack('<I',52)+b'WAVE')
            self.assertEqual(len(raw),60)

    def test_video_frame_duration_is_not_audio_sample_duration(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,descriptor,baseline=self.fixture(root)
            baseline['expected_duration']={'numerator':1,'denominator':60}
            result=service.export_audio(source,root/'wrong.wav',descriptor,baseline,output_format='wav')
            self.assertFalse(result['ok']);self.assertEqual(result['timing_status'],'FAIL')
            self.assertFalse((root/'wrong.wav').exists())

    def test_stale_waveform_bad_rational_and_existing_output_refuse(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,descriptor,baseline=self.fixture(root)
            baseline['expected_duration']={'numerator':2,'denominator':22050}
            self.assertFalse(service.check_audio(source,descriptor,baseline)['ok'])
            baseline['expected_duration']={'numerator':1,'denominator':11025};baseline['expected_pcm_sha256']='0'*64
            self.assertEqual(service.check_audio(source,descriptor,baseline)['waveform_status'],'FAIL')
            baseline['expected_pcm_sha256']=None
            output=root/'audio.wav';output.write_bytes(b'keep')
            self.assertFalse(service.export_audio(source,output,descriptor,baseline,output_format='wav')['ok'])
            self.assertEqual(output.read_bytes(),b'keep')
