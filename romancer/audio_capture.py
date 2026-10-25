"""Bounded synchronous libretro int16 stereo capture; no speaker playback."""

from array import array
import ctypes
import struct
import sys
import threading

MAX_CAPTURE_FRAMES = 262144
MAX_BATCH_FRAMES = 262144
_NATIVE_BYTEORDER = sys.byteorder
_SAMPLE_POINTER = ctypes.POINTER(ctypes.c_int16)
_POINTER_MAX = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1


class AudioCapture:
    def __init__(self, max_frames=MAX_CAPTURE_FRAMES):
        if type(max_frames) is not int or not 1 <= max_frames <= MAX_CAPTURE_FRAMES:
            raise ValueError('max_frames must be an integer from 1 to 262144')
        self._max_frames = max_frames
        self._buffer = bytearray(max_frames * 4)
        self._lock = threading.Lock()
        self._clear()

    def _clear(self):
        self._captured_frames = 0
        self._dropped_frames = 0
        self._invalid_batches = 0

    def sample(self, left, right):
        if any(type(value) is not int or not -32768 <= value <= 32767 for value in (left, right)):
            raise ValueError('samples must be signed 16-bit integers')
        with self._lock:
            if self._captured_frames == self._max_frames:
                self._dropped_frames += 1
                return
            struct.pack_into('<hh', self._buffer, self._captured_frames * 4, left, right)
            self._captured_frames += 1

    def batch(self, pointer, frames):
        with self._lock:
            if type(frames) is not int or not 0 <= frames <= MAX_BATCH_FRAMES:
                self._invalid_batches += 1
                return 0
            if frames == 0:
                return 0
            if isinstance(pointer, ctypes.Array):
                valid_type = pointer._type_ is ctypes.c_int16 and len(pointer) >= frames * 2
            else:
                valid_type = isinstance(pointer, _SAMPLE_POINTER)
            if not valid_type or not pointer:
                self._invalid_batches += 1
                return 0
            address = ctypes.cast(pointer, ctypes.c_void_p).value
            if (address < 4096 or address % ctypes.alignment(ctypes.c_int16)
                    or address > _POINTER_MAX - frames * 4):
                self._invalid_batches += 1
                return 0
            retained = min(frames, self._max_frames - self._captured_frames)
            if retained:
                # Never read discarded overflow. Valid native storage is supplied
                # by the trusted core; ctypes cannot prove arbitrary pointer safety.
                try:
                    raw = ctypes.string_at(pointer, retained * 4)
                    if _NATIVE_BYTEORDER == 'big':
                        native = array('h')
                        native.frombytes(raw)
                        native.byteswap()
                        raw = native.tobytes()
                except (OSError, TypeError, ValueError):
                    self._invalid_batches += 1
                    return 0
                start = self._captured_frames * 4
                self._buffer[start:start + len(raw)] = raw
                self._captured_frames += retained
            self._dropped_frames += frames - retained
            return frames

    def _summary(self):
        return {
            'format': 's16le', 'channels': 2, 'max_frames': self._max_frames,
            'captured_frames': self._captured_frames,
            'dropped_frames': self._dropped_frames,
            'invalid_batches': self._invalid_batches,
            'observed': bool(self._captured_frames or self._dropped_frames),
        }

    def summary(self):
        with self._lock:
            return self._summary()

    def drain(self):
        with self._lock:
            result = self._summary()
            result['pcm_s16le'] = bytes(memoryview(self._buffer)[:self._captured_frames * 4])
            self._clear()
            return result

    def reset(self):
        with self._lock:
            self._clear()
