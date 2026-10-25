import ctypes
import importlib
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from romancer.libretro_frontend import AudioCB, AudioBatchCB, LibretroError, LibretroFrontend


PCM = bytes.fromhex('0080ff7fffff0100000000003412cced')
SAMPLES = (-32768, 32767, -1, 1, 0, 0, 4660, -4660)


class AudioCaptureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.audio_capture'),
                             'bounded AudioCapture service is not implemented')
        self.module = importlib.import_module('romancer.audio_capture')
        self.capture = self.module.AudioCapture()

    def test_single_sample_callback_preserves_signed_stereo_order(self):
        callback = AudioCB(self.capture.sample)
        callback(-32768, 32767)
        callback(-1, 1)
        self.assertEqual(self.capture.drain()['pcm_s16le'], PCM[:8])

    def test_batch_callback_copies_native_stereo_data(self):
        data = (ctypes.c_int16 * 8)(*SAMPLES)
        callback = AudioBatchCB(self.capture.batch)
        self.assertEqual(callback(data, 4), 4)
        data[0] = 123
        result = self.capture.drain()
        self.assertEqual(result['pcm_s16le'], PCM)
        self.assertEqual(result['captured_frames'], 4)
        self.assertEqual(result['dropped_frames'], 0)
        self.assertEqual(result['invalid_batches'], 0)

    def test_big_endian_native_bytes_are_normalized(self):
        raw = struct.pack('>8h', *SAMPLES)
        data = (ctypes.c_int16 * 8).from_buffer_copy(raw)
        with patch.object(self.module, '_NATIVE_BYTEORDER', 'big'):
            self.assertEqual(AudioBatchCB(self.capture.batch)(data, 4), 4)
        self.assertEqual(self.capture.drain()['pcm_s16le'], PCM)

    def test_overflow_retains_oldest_and_acknowledges_discarded_frames(self):
        capture = self.module.AudioCapture(max_frames=2)
        capture.sample(10, -10)
        data = (ctypes.c_int16 * 8)(*SAMPLES)
        self.assertEqual(AudioBatchCB(capture.batch)(data, 4), 4)
        capture.sample(20, -20)
        result = capture.drain()
        self.assertEqual(result['pcm_s16le'], struct.pack('<hh', 10, -10) + PCM[:4])
        self.assertEqual(result['captured_frames'], 2)
        self.assertEqual(result['dropped_frames'], 4)

    def test_default_capacity_is_one_mib(self):
        data = (ctypes.c_int16 * (262144 * 2))()
        callback = AudioBatchCB(self.capture.batch)
        self.assertEqual(callback(data, 262144), 262144)
        AudioCB(self.capture.sample)(1, 2)
        result = self.capture.drain()
        self.assertEqual(len(result['pcm_s16le']), 1024 * 1024)
        self.assertEqual(result['captured_frames'], 262144)
        self.assertEqual(result['dropped_frames'], 1)

    def test_batch_reads_only_retained_frames_and_never_reads_when_full(self):
        capture = self.module.AudioCapture(max_frames=2)
        capture.sample(10, -10)
        data = (ctypes.c_int16 * 8)(*SAMPLES)
        read_sizes = []
        real_string_at = ctypes.string_at

        def bounded_read(pointer, size):
            self.assertLessEqual(size, 4)
            read_sizes.append(size)
            return real_string_at(pointer, size)

        callback = AudioBatchCB(capture.batch)
        with patch.object(self.module.ctypes, 'string_at', side_effect=bounded_read):
            self.assertEqual(callback(data, 4), 4)
            self.assertEqual(callback(data, 4), 4)
        self.assertEqual(read_sizes, [4])
        result = capture.drain()
        self.assertEqual(result['pcm_s16le'], struct.pack('<hh', 10, -10) + PCM[:4])
        self.assertEqual(result['dropped_frames'], 7)

    def test_drain_resets_segment_counters_and_summary_does_not_consume(self):
        self.capture.sample(1, -1)
        self.capture.batch(None, 1)
        for _ in range(2):
            summary = self.capture.summary()
            self.assertEqual(summary['captured_frames'], 1)
            self.assertEqual(summary['invalid_batches'], 1)
            self.assertNotIn('pcm_s16le', summary)
        self.capture.drain()
        result = self.capture.drain()
        self.assertEqual(result['pcm_s16le'], b'')
        self.assertEqual((result['captured_frames'], result['dropped_frames'], result['invalid_batches']), (0, 0, 0))

    def test_reset_discards_audio_and_errors(self):
        self.capture.sample(1, -1)
        self.capture.batch(None, 1)
        self.capture.reset()
        result = self.capture.drain()
        self.assertEqual(result['pcm_s16le'], b'')
        self.assertEqual((result['captured_frames'], result['dropped_frames'], result['invalid_batches']), (0, 0, 0))

    def test_null_and_empty_batches_do_not_dereference(self):
        callback = AudioBatchCB(self.capture.batch)
        self.assertEqual(callback(None, 0), 0)
        self.assertEqual(self.capture.summary()['invalid_batches'], 0)
        self.assertEqual(callback(None, 2), 0)
        self.assertEqual(self.capture.summary()['invalid_batches'], 1)

    def test_malformed_counts_and_pointers_are_rejected_before_reading(self):
        invalid = ctypes.cast(ctypes.c_void_p(1), ctypes.POINTER(ctypes.c_int16))
        callback = AudioBatchCB(self.capture.batch)
        self.assertEqual(callback(invalid, 262145), 0)
        self.assertEqual(callback(invalid, ctypes.c_size_t(-1).value), 0)
        self.assertEqual(callback(invalid, 1), 0)
        for frames in (-1, True, 1.5, '1'):
            self.assertEqual(self.capture.batch(invalid, frames), 0)
        for pointer in (1, object(), ctypes.c_void_p(1)):
            self.assertEqual(self.capture.batch(pointer, 1), 0)
        self.assertEqual(self.capture.summary()['invalid_batches'], 10)
        self.assertEqual(self.capture.drain()['pcm_s16le'], b'')

    def test_short_ctypes_array_is_rejected(self):
        self.assertEqual(self.capture.batch((ctypes.c_int16 * 2)(1, 2), 2), 0)
        self.assertEqual(self.capture.summary()['invalid_batches'], 1)

    def test_invalid_capacities_are_rejected(self):
        for capacity in (0, -1, True, 1.5, '2', 262145):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                self.module.AudioCapture(capacity)

    def test_concurrent_callbacks_and_drains_keep_complete_stereo_frames(self):
        capture = self.module.AudioCapture(max_frames=8)
        callback = AudioCB(capture.sample)
        start = threading.Barrier(5)

        def produce():
            start.wait()
            for _ in range(250):
                callback(1234, -1234)

        producers = [threading.Thread(target=produce) for _ in range(4)]
        for producer in producers:
            producer.start()
        start.wait()
        segments = []
        while any(producer.is_alive() for producer in producers):
            segments.append(capture.drain())
            for producer in producers:
                producer.join(timeout=0.001)
        segments.append(capture.drain())
        self.assertEqual(sum(s['captured_frames'] + s['dropped_frames'] for s in segments), 1000)
        for segment in segments:
            self.assertEqual(segment['pcm_s16le'], struct.pack('<hh', 1234, -1234) * segment['captured_frames'])
            self.assertLessEqual(segment['captured_frames'], 8)
            self.assertEqual(segment['invalid_batches'], 0)


class FrontendAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        core = root / 'placeholder.core'
        core.write_bytes(b'synthetic core placeholder')
        self.game = root / 'content.bin'
        self.game.write_bytes(b'synthetic content')
        self.lib = Mock()
        self.lib.retro_api_version.return_value = 1
        self.lib.retro_load_game.return_value = True
        self.lib.retro_get_memory_size.return_value = 0
        self.lib.retro_unserialize.return_value = True
        with patch('romancer.libretro_frontend.ctypes.CDLL', return_value=self.lib):
            self.host = LibretroFrontend(core, save_dir=root / 'save')

    def test_constructor_callbacks_deliver_real_ctypes_audio(self):
        self.host._audio_cb(-32768, 32767)
        self.assertEqual(self.host._audio_batch_cb((ctypes.c_int16 * 4)(-1, 1, 0, 0), 2), 2)
        self.assertEqual(self.host.audio_summary()['captured_frames'], 3)
        self.assertEqual(self.host.drain_audio()['pcm_s16le'], PCM[:12])

    def test_async_and_float_audio_are_not_advertised(self):
        self.assertFalse(self.host._environment_cb(22, None))
        self.assertFalse(self.host._environment_cb(85 | 0x10000, None))

    def test_content_load_resets_previous_capture(self):
        self.host._audio_cb(1, -1)
        self.host.load_game(self.game)
        self.assertEqual(self.host.drain_audio()['pcm_s16le'], b'')

    def test_successful_state_import_resets_audio_and_stale_video(self):
        self.host.load_game(self.game)
        self.host.last_frame = object()
        self.host._audio_cb(1, -1)
        self.host.unserialize(b'synthetic state')
        self.assertEqual(self.host.drain_audio()['pcm_s16le'], b'')
        self.assertIsNone(self.host.last_frame)

    def test_failed_state_import_retains_existing_segment(self):
        self.host.load_game(self.game)
        self.host._audio_cb(1, -1)
        self.lib.retro_unserialize.return_value = False
        with self.assertRaises(LibretroError):
            self.host.unserialize(b'rejected')
        self.assertEqual(self.host.drain_audio()['pcm_s16le'], struct.pack('<hh', 1, -1))

    def test_close_clears_audio_even_when_unload_emits_samples(self):
        self.host.load_game(self.game)
        self.lib.retro_unload_game.side_effect = lambda: self.host._audio_cb(7, -7)
        self.host.close()
        self.assertEqual(self.host.drain_audio()['pcm_s16le'], b'')

    def test_close_clears_audio_when_save_persistence_fails(self):
        self.host.load_game(self.game)
        self.host._audio_cb(1, -1)
        with patch.object(self.host, '_persist_save_ram', side_effect=OSError('synthetic save failure')):
            with self.assertRaises(OSError):
                self.host.close()
        self.assertEqual(self.host.drain_audio()['pcm_s16le'], b'')


class CompiledAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('gcc') or shutil.which('cc')
        if not compiler:
            raise unittest.SkipTest('native C compiler unavailable; run compiled cases under WSL')
        cls.tmp = tempfile.TemporaryDirectory(prefix='romancer audio compiled ')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        source = Path(__file__).resolve().parent / 'mock_libretro.c'
        cls.cores = {}
        for flag in (False, True):
            core = cls.root / ('v35' if flag else 'default')
            core = core.with_suffix('.dll' if sys.platform == 'win32' else '.so')
            command = [compiler, '-shared', '-fPIC', '-O2']
            if flag:
                command.append('-DROMANCER_V35_TEST')
            result = subprocess.run(command + [str(source), '-o', str(core)], capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.cores[flag] = core

    def test_v35_mock_emits_known_batch_and_normal_save_action(self):
        game = self.root / 'audio.bin'
        game.write_bytes(b'synthetic audio fixture')
        saves = self.root / 'audio saves'
        with LibretroFrontend(self.cores[True], save_dir=saves) as host:
            host.load_game(game)
            host.run_frame(['a'])
            self.assertEqual(host.drain_audio()['pcm_s16le'], PCM)
            self.assertEqual(host.memory_region('save_ram')[0], 1)
            saved = host.serialize()
            host.run_frame([])
            host.unserialize(saved)
            self.assertEqual(host.drain_audio()['pcm_s16le'], b'')
            self.assertIsNone(host.last_frame)
            host.run_frame([])
            self.assertEqual(host.drain_audio()['pcm_s16le'], PCM)
        self.assertEqual((saves / 'audio.srm').read_bytes()[0], 1)
        with LibretroFrontend(self.cores[True], save_dir=saves) as host:
            host.load_game(game)
            self.assertEqual(host.memory_region('save_ram')[0], 1)

    def test_default_mock_still_has_no_audio_or_save_action(self):
        game = self.root / 'default.bin'
        game.write_bytes(b'synthetic default fixture')
        with LibretroFrontend(self.cores[False], save_dir=self.root / 'default saves') as host:
            host.load_game(game)
            host.run_frame(['a'])
            self.assertEqual(host.drain_audio()['pcm_s16le'], b'')
            self.assertEqual(host.memory_region('save_ram')[0], 0)
            self.assertEqual(host.memory_region('system_ram')[2], 1)


if __name__ == '__main__':
    unittest.main()
