from __future__ import annotations

"""Minimal evidence-oriented libretro frontend used by ROMancer v7.

This is intentionally not a replacement for RetroArch.  It implements the subset of
libretro needed for deterministic headless validation of software-rendering console
cores: content loading, one-frame execution, standard joypad input, software video
capture, core options through the legacy variable interface, save states, and exposed
memory regions.

No emulator core, BIOS, ROM, disc image, save state, or copyrighted game asset is
bundled with ROMancer.  The caller supplies those paths.
"""

import ctypes
import hashlib
import os
import platform
import struct
import zlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from .audio_capture import AudioCapture

# libretro ABI v1 constants used by this frontend.
RETRO_API_VERSION = 1
RETRO_DEVICE_JOYPAD = 1
RETRO_DEVICE_ID_JOYPAD_B = 0
RETRO_DEVICE_ID_JOYPAD_Y = 1
RETRO_DEVICE_ID_JOYPAD_SELECT = 2
RETRO_DEVICE_ID_JOYPAD_START = 3
RETRO_DEVICE_ID_JOYPAD_UP = 4
RETRO_DEVICE_ID_JOYPAD_DOWN = 5
RETRO_DEVICE_ID_JOYPAD_LEFT = 6
RETRO_DEVICE_ID_JOYPAD_RIGHT = 7
RETRO_DEVICE_ID_JOYPAD_A = 8
RETRO_DEVICE_ID_JOYPAD_X = 9
RETRO_DEVICE_ID_JOYPAD_L = 10
RETRO_DEVICE_ID_JOYPAD_R = 11
RETRO_DEVICE_ID_JOYPAD_L2 = 12
RETRO_DEVICE_ID_JOYPAD_R2 = 13
RETRO_DEVICE_ID_JOYPAD_L3 = 14
RETRO_DEVICE_ID_JOYPAD_R3 = 15
RETRO_DEVICE_ID_JOYPAD_MASK = 256

BUTTON_IDS = {
    "b": RETRO_DEVICE_ID_JOYPAD_B,
    "y": RETRO_DEVICE_ID_JOYPAD_Y,
    "select": RETRO_DEVICE_ID_JOYPAD_SELECT,
    "start": RETRO_DEVICE_ID_JOYPAD_START,
    "up": RETRO_DEVICE_ID_JOYPAD_UP,
    "down": RETRO_DEVICE_ID_JOYPAD_DOWN,
    "left": RETRO_DEVICE_ID_JOYPAD_LEFT,
    "right": RETRO_DEVICE_ID_JOYPAD_RIGHT,
    "a": RETRO_DEVICE_ID_JOYPAD_A,
    "x": RETRO_DEVICE_ID_JOYPAD_X,
    "l": RETRO_DEVICE_ID_JOYPAD_L,
    "r": RETRO_DEVICE_ID_JOYPAD_R,
    "l2": RETRO_DEVICE_ID_JOYPAD_L2,
    "r2": RETRO_DEVICE_ID_JOYPAD_R2,
    "l3": RETRO_DEVICE_ID_JOYPAD_L3,
    "r3": RETRO_DEVICE_ID_JOYPAD_R3,
}

RETRO_MEMORY_SAVE_RAM = 0
RETRO_MEMORY_RTC = 1
RETRO_MEMORY_SYSTEM_RAM = 2
RETRO_MEMORY_VIDEO_RAM = 3
RETRO_MEMORY_ROM = 4
MEMORY_TYPES = {
    "save_ram": RETRO_MEMORY_SAVE_RAM,
    "rtc": RETRO_MEMORY_RTC,
    "system_ram": RETRO_MEMORY_SYSTEM_RAM,
    "video_ram": RETRO_MEMORY_VIDEO_RAM,
    "rom": RETRO_MEMORY_ROM,
}

RETRO_PIXEL_FORMAT_0RGB1555 = 0
RETRO_PIXEL_FORMAT_XRGB8888 = 1
RETRO_PIXEL_FORMAT_RGB565 = 2
PIXEL_FORMAT_NAMES = {
    0: "0RGB1555",
    1: "XRGB8888",
    2: "RGB565",
}

RETRO_ENVIRONMENT_GET_CAN_DUPE = 3
RETRO_ENVIRONMENT_SHUTDOWN = 7
RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY = 9
RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10
RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS = 11
RETRO_ENVIRONMENT_SET_DISK_CONTROL_INTERFACE = 13
RETRO_ENVIRONMENT_GET_VARIABLE = 15
RETRO_ENVIRONMENT_SET_VARIABLES = 16
RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE = 17
RETRO_ENVIRONMENT_GET_LIBRETRO_PATH = 19
RETRO_ENVIRONMENT_GET_CORE_ASSETS_DIRECTORY = 30
RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY = 31
RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO = 32
RETRO_ENVIRONMENT_SET_CONTROLLER_INFO = 35
RETRO_ENVIRONMENT_SET_MEMORY_MAPS = 36 | 0x10000
RETRO_ENVIRONMENT_SET_GEOMETRY = 37
RETRO_ENVIRONMENT_GET_USERNAME = 38
RETRO_ENVIRONMENT_GET_LANGUAGE = 39
RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS = 42
RETRO_ENVIRONMENT_GET_INPUT_BITMASKS = 51
RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION = 52

# Software frame sentinel used by hardware-rendering cores.
RETRO_HW_FRAME_BUFFER_VALID = ctypes.c_void_p(-1).value


class RetroSystemInfo(ctypes.Structure):
    _fields_ = [
        ("library_name", ctypes.c_char_p),
        ("library_version", ctypes.c_char_p),
        ("valid_extensions", ctypes.c_char_p),
        ("need_fullpath", ctypes.c_bool),
        ("block_extract", ctypes.c_bool),
    ]


class RetroGameGeometry(ctypes.Structure):
    _fields_ = [
        ("base_width", ctypes.c_uint),
        ("base_height", ctypes.c_uint),
        ("max_width", ctypes.c_uint),
        ("max_height", ctypes.c_uint),
        ("aspect_ratio", ctypes.c_float),
    ]


class RetroSystemTiming(ctypes.Structure):
    _fields_ = [("fps", ctypes.c_double), ("sample_rate", ctypes.c_double)]


class RetroSystemAVInfo(ctypes.Structure):
    _fields_ = [("geometry", RetroGameGeometry), ("timing", RetroSystemTiming)]


class RetroGameInfo(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_char_p),
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
        ("meta", ctypes.c_char_p),
    ]


class RetroVariable(ctypes.Structure):
    _fields_ = [("key", ctypes.c_char_p), ("value", ctypes.c_char_p)]


class RetroInputDescriptor(ctypes.Structure):
    _fields_ = [
        ("port", ctypes.c_uint),
        ("device", ctypes.c_uint),
        ("index", ctypes.c_uint),
        ("id", ctypes.c_uint),
        ("description", ctypes.c_char_p),
    ]


DiskSetEject = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_bool)
DiskGetEject = ctypes.CFUNCTYPE(ctypes.c_bool)
DiskGetIndex = ctypes.CFUNCTYPE(ctypes.c_uint)
DiskSetIndex = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
DiskGetNum = ctypes.CFUNCTYPE(ctypes.c_uint)
DiskReplace = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.POINTER(RetroGameInfo))
DiskAdd = ctypes.CFUNCTYPE(ctypes.c_bool)


class RetroDiskControlCallback(ctypes.Structure):
    _fields_ = [
        ("set_eject_state", DiskSetEject),
        ("get_eject_state", DiskGetEject),
        ("get_image_index", DiskGetIndex),
        ("set_image_index", DiskSetIndex),
        ("get_num_images", DiskGetNum),
        ("replace_image_index", DiskReplace),
        ("add_image_index", DiskAdd),
    ]


EnvironmentCB = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)
VideoCB = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t)
AudioCB = ctypes.CFUNCTYPE(None, ctypes.c_int16, ctypes.c_int16)
AudioBatchCB = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t)
InputPollCB = ctypes.CFUNCTYPE(None)
InputStateCB = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)


def _decode_cstr(value: bytes | None) -> str:
    if not value:
        return ""
    return value.decode("utf-8", errors="replace")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def write_rgb_png(path: str | Path, width: int, height: int, rgb: bytes) -> str:
    """Write RGB24 bytes to a PNG using only the Python standard library."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if width <= 0 or height <= 0 or len(rgb) != width * height * 3:
        raise ValueError("Invalid RGB frame size for PNG output")
    raw = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    return str(path)


@dataclass
class Frame:
    index: int
    width: int
    height: int
    pitch: int
    pixel_format: str
    rgb: bytes

    def sha256(self) -> str:
        return hashlib.sha256(self.rgb).hexdigest()

    def save_png(self, path: str | Path) -> str:
        return write_rgb_png(path, self.width, self.height, self.rgb)

    def summary(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "width": self.width,
            "height": self.height,
            "pitch": self.pitch,
            "pixel_format": self.pixel_format,
            "sha256": self.sha256(),
        }


@dataclass
class CoreInfo:
    path: str
    api_version: int
    library_name: str
    library_version: str
    valid_extensions: list[str]
    need_fullpath: bool
    block_extract: bool


class LibretroError(RuntimeError):
    pass


class LibretroFrontend:
    """Headless single-core libretro host.

    The frontend is deliberately deterministic and evidence-oriented.  It does not
    display a window or play audio.  It captures the most recent software frame and
    accepts scripted joypad state.  Hardware-rendering cores are detected and rejected
    for frame evidence rather than silently producing invalid screenshots.
    """

    def __init__(
        self,
        core_path: str | Path,
        *,
        system_dir: str | Path | None = None,
        save_dir: str | Path | None = None,
        assets_dir: str | Path | None = None,
        core_options: dict[str, str] | None = None,
    ):
        self.core_path = str(Path(core_path).resolve())
        if not Path(self.core_path).is_file():
            raise FileNotFoundError(self.core_path)
        self.runtime_root = Path(save_dir or Path.cwd() / ".romancer_runtime").resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.system_dir = Path(system_dir or self.runtime_root / "system").resolve()
        self.save_dir = Path(save_dir or self.runtime_root / "save").resolve()
        self.assets_dir = Path(assets_dir or self.runtime_root / "assets").resolve()
        for d in (self.system_dir, self.save_dir, self.assets_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._system_dir_b = os.fsencode(str(self.system_dir))
        self._save_dir_b = os.fsencode(str(self.save_dir))
        self._assets_dir_b = os.fsencode(str(self.assets_dir))
        self._core_path_b = os.fsencode(self.core_path)
        self._username_b = b"ROMancer"

        self._user_core_options = {str(k): str(v) for k, v in (core_options or {}).items()}
        self._core_option_values: dict[str, str] = dict(self._user_core_options)
        self._core_option_buffers: dict[str, bytes] = {}
        self._core_variables_seen: dict[str, str] = {}
        self.messages: list[str] = []
        self.shutdown_requested = False
        self.pixel_format = RETRO_PIXEL_FORMAT_0RGB1555
        self.hardware_video_seen = False
        self.frame_index = 0
        self.last_frame: Frame | None = None
        self._joypads: dict[int, int] = {0: 0}
        self._game_buffer = None
        self._game_path_b: bytes | None = None
        self._loaded = False
        self._initialized = False
        self._content_path: Path | None = None
        self.input_descriptors: list[dict[str, Any]] = []
        self._disk_control: RetroDiskControlCallback | None = None
        self._sram_loaded_from: str | None = None
        self._sram_saved_to: str | None = None
        self._sram_seed_extent = None
        self._sram_write_ready = False
        self._audio_capture = AudioCapture()

        # Callback objects must be retained for the lifetime of the core.
        self._environment_cb = EnvironmentCB(self._environment)
        self._video_cb = VideoCB(self._video_refresh)
        self._audio_cb = AudioCB(self._audio_sample)
        self._audio_batch_cb = AudioBatchCB(self._audio_batch)
        self._input_poll_cb = InputPollCB(self._input_poll)
        self._input_state_cb = InputStateCB(self._input_state)

        try:
            self.lib = ctypes.CDLL(self.core_path)
        except OSError as exc:
            raise LibretroError(f"Could not load libretro core: {exc}") from exc
        self._bind_symbols()
        self.lib.retro_set_environment(self._environment_cb)
        self.lib.retro_set_video_refresh(self._video_cb)
        self.lib.retro_set_audio_sample(self._audio_cb)
        self.lib.retro_set_audio_sample_batch(self._audio_batch_cb)
        self.lib.retro_set_input_poll(self._input_poll_cb)
        self.lib.retro_set_input_state(self._input_state_cb)

    def _require(self, name: str):
        try:
            return getattr(self.lib, name)
        except AttributeError as exc:
            raise LibretroError(f"Core is missing required libretro symbol: {name}") from exc

    def _bind_symbols(self) -> None:
        required = [
            "retro_api_version", "retro_init", "retro_deinit", "retro_get_system_info",
            "retro_get_system_av_info", "retro_set_environment", "retro_set_video_refresh",
            "retro_set_audio_sample", "retro_set_audio_sample_batch", "retro_set_input_poll",
            "retro_set_input_state", "retro_load_game", "retro_unload_game", "retro_run",
            "retro_reset", "retro_serialize_size", "retro_serialize", "retro_unserialize",
            "retro_get_memory_data", "retro_get_memory_size", "retro_set_controller_port_device",
        ]
        for name in required:
            self._require(name)

        self.lib.retro_api_version.restype = ctypes.c_uint
        self.lib.retro_get_system_info.argtypes = [ctypes.POINTER(RetroSystemInfo)]
        self.lib.retro_get_system_av_info.argtypes = [ctypes.POINTER(RetroSystemAVInfo)]
        self.lib.retro_load_game.argtypes = [ctypes.POINTER(RetroGameInfo)]
        self.lib.retro_load_game.restype = ctypes.c_bool
        self.lib.retro_serialize_size.restype = ctypes.c_size_t
        self.lib.retro_serialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.lib.retro_serialize.restype = ctypes.c_bool
        self.lib.retro_unserialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.lib.retro_unserialize.restype = ctypes.c_bool
        self.lib.retro_get_memory_data.argtypes = [ctypes.c_uint]
        self.lib.retro_get_memory_data.restype = ctypes.c_void_p
        self.lib.retro_get_memory_size.argtypes = [ctypes.c_uint]
        self.lib.retro_get_memory_size.restype = ctypes.c_size_t
        self.lib.retro_set_controller_port_device.argtypes = [ctypes.c_uint, ctypes.c_uint]

    def core_info(self) -> CoreInfo:
        info = RetroSystemInfo()
        self.lib.retro_get_system_info(ctypes.byref(info))
        api = int(self.lib.retro_api_version())
        return CoreInfo(
            path=self.core_path,
            api_version=api,
            library_name=_decode_cstr(info.library_name),
            library_version=_decode_cstr(info.library_version),
            valid_extensions=[x for x in _decode_cstr(info.valid_extensions).split("|") if x],
            need_fullpath=bool(info.need_fullpath),
            block_extract=bool(info.block_extract),
        )

    def av_info(self) -> dict[str, Any]:
        info = RetroSystemAVInfo()
        self.lib.retro_get_system_av_info(ctypes.byref(info))
        g = info.geometry
        t = info.timing
        return {
            "geometry": {
                "base_width": int(g.base_width), "base_height": int(g.base_height),
                "max_width": int(g.max_width), "max_height": int(g.max_height),
                "aspect_ratio": float(g.aspect_ratio),
            },
            "timing": {"fps": float(t.fps), "sample_rate": float(t.sample_rate)},
        }

    def initialize(self) -> None:
        if self._initialized:
            return
        api = int(self.lib.retro_api_version())
        if api != RETRO_API_VERSION:
            raise LibretroError(f"Unsupported libretro API version {api}; ROMancer supports ABI {RETRO_API_VERSION}")
        self.lib.retro_init()
        self._initialized = True

    def load_game(self, game_path: str | Path) -> dict[str, Any]:
        self._sram_write_ready = False
        self.initialize()
        game = Path(game_path).resolve()
        if not game.is_file():
            raise FileNotFoundError(game)
        info = self.core_info()
        ext = game.suffix.lower().lstrip(".")
        extension_warning = bool(info.valid_extensions and ext and ext not in {e.lower() for e in info.valid_extensions})
        self._game_path_b = os.fsencode(str(game))
        gi = RetroGameInfo()
        gi.path = self._game_path_b
        gi.meta = None
        if info.need_fullpath:
            gi.data = None
            gi.size = 0
        else:
            raw = game.read_bytes()
            self._game_buffer = ctypes.create_string_buffer(raw)
            gi.data = ctypes.cast(self._game_buffer, ctypes.c_void_p)
            gi.size = len(raw)
        self._audio_capture.reset()
        ok = bool(self.lib.retro_load_game(ctypes.byref(gi)))
        if not ok:
            raise LibretroError(f"Core rejected content: {game}")
        self._loaded = True
        self._content_path = game
        self.lib.retro_set_controller_port_device(0, RETRO_DEVICE_JOYPAD)
        self._load_save_ram()
        return {
            "loaded": True,
            "game": str(game),
            "extension_warning": extension_warning,
            "core": asdict(info),
            "av_info": self.av_info(),
            "pixel_format": PIXEL_FORMAT_NAMES.get(self.pixel_format, str(self.pixel_format)),
            "core_options": dict(sorted(self._core_option_values.items())),
            "input_descriptors": list(self.input_descriptors),
            "save_ram_loaded_from": self._sram_loaded_from,
            "disk_control_available": self._disk_control is not None,
        }

    def _save_ram_path(self) -> Path | None:
        if self._content_path is None:
            return None
        return self.save_dir / (self._content_path.stem + ".srm")

    def _load_save_ram(self) -> None:
        self._sram_write_ready = False
        path = self._save_ram_path()
        if path is None or not path.is_file():
            self._sram_write_ready = True
            return
        size = int(self.lib.retro_get_memory_size(RETRO_MEMORY_SAVE_RAM))
        ptr = self.lib.retro_get_memory_data(RETRO_MEMORY_SAVE_RAM)
        if not ptr or size <= 0:
            return
        raw = path.read_bytes()
        self._sram_seed_extent = None
        if len(raw) != size:
            # mGBA exposes its maximum flash allocation while the GBA save type
            # is AUTODETECT. Its actual SRAM/EEPROM extent is known later. This
            # is not permission to truncate saves or accept arbitrary prefixes.
            tail = ctypes.string_at(ptr + len(raw), size-len(raw)) if 0 < len(raw) < size else b''
            if (self.core_info().library_name.casefold() != 'mgba'
                    or self._content_path.suffix.lower() != '.gba'
                    or size != 131072 or len(raw) not in (512, 8192, 32768, 65536)
                    or not tail or len(set(tail)) != 1 or tail[0] not in (0, 255)):
                raise ValueError('normal save RAM was not loaded exactly: save size differs from the core allocation')
            self._sram_seed_extent = (len(raw), size, tail)
        ctypes.memmove(ptr, raw, len(raw))
        self.verify_save_seed(raw)
        self._sram_loaded_from = str(path)

    def verify_save_seed(self, seed: bytes) -> dict:
        """Read back every supplied byte without executing hidden game frames."""
        # A refusal must never let close() replace a supplied save with blank
        # or partially loaded RAM. Cleanup still unloads/deinitializes the core.
        self._sram_write_ready = False
        actual = self.memory_region('save_ram')
        if actual == seed:
            self._sram_write_ready = True
            return {'mode':'exact_region', 'save_bytes':len(seed), 'allocation_bytes':len(actual)}
        extent = self._sram_seed_extent
        if (extent is not None and extent[:2] == (len(seed), len(actual))
                and actual[:len(seed)] == seed and actual[len(seed):] == extent[2]):
            self._sram_write_ready = True
            return {'mode':'mgba_autodetect_allocation', 'save_bytes':len(seed), 'allocation_bytes':len(actual)}
        raise ValueError('normal save RAM was not loaded exactly; check core and save format')

    def _persist_save_ram(self) -> None:
        if not self._sram_write_ready:
            return
        path = self._save_ram_path()
        if path is None:
            return
        size = int(self.lib.retro_get_memory_size(RETRO_MEMORY_SAVE_RAM))
        ptr = self.lib.retro_get_memory_data(RETRO_MEMORY_SAVE_RAM)
        if not ptr or size <= 0:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ctypes.string_at(ptr, size))
        self._sram_saved_to = str(path)

    def close(self) -> None:
        failure = None
        try:
            if self._loaded:
                try:
                    self._persist_save_ram()
                except BaseException as exc:
                    failure = exc
                try:
                    self.lib.retro_unload_game()
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                finally:
                    self._loaded = False
            if self._initialized:
                try:
                    self.lib.retro_deinit()
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                finally:
                    self._initialized = False
        finally:
            self._audio_capture.reset()
        if failure is not None:
            raise failure

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ----------------------------- input -----------------------------
    @staticmethod
    def buttons_to_mask(buttons: Iterable[str]) -> int:
        mask = 0
        for button in buttons:
            key = str(button).lower().strip()
            if key not in BUTTON_IDS:
                raise ValueError(f"Unknown libretro joypad button: {button}")
            mask |= 1 << BUTTON_IDS[key]
        return mask

    def set_buttons(self, buttons: Iterable[str], port: int = 0) -> None:
        self._joypads[int(port)] = self.buttons_to_mask(buttons)

    def clear_buttons(self, port: int = 0) -> None:
        self._joypads[int(port)] = 0

    def run_frame(self, buttons: Iterable[str] | None = None, port: int = 0) -> Frame | None:
        if not self._loaded:
            raise LibretroError("No game is loaded")
        if buttons is not None:
            self.set_buttons(buttons, port)
        self.lib.retro_run()
        return self.last_frame

    def run_frames(self, frames: int, buttons: Iterable[str] | None = None, port: int = 0, release_after: bool = False) -> Frame | None:
        if frames < 0:
            raise ValueError("frames must be non-negative")
        if buttons is not None:
            self.set_buttons(buttons, port)
        for _ in range(frames):
            self.lib.retro_run()
            if self.shutdown_requested:
                break
        if release_after:
            self.clear_buttons(port)
        return self.last_frame

    def tap(self, buttons: Iterable[str], *, hold_frames: int = 1, settle_frames: int = 1, port: int = 0) -> Frame | None:
        self.set_buttons(buttons, port)
        self.run_frames(max(1, hold_frames))
        self.clear_buttons(port)
        return self.run_frames(max(0, settle_frames))

    # ----------------------------- save states -----------------------------
    def serialize(self) -> bytes:
        if not self._loaded:
            raise LibretroError("No game is loaded")
        size = int(self.lib.retro_serialize_size())
        if size <= 0:
            raise LibretroError("Core reports that serialization/save states are unsupported")
        buf = ctypes.create_string_buffer(size)
        if not bool(self.lib.retro_serialize(buf, size)):
            raise LibretroError("retro_serialize failed")
        return bytes(buf.raw[:size])

    def unserialize(self, data: bytes) -> None:
        if not self._loaded:
            raise LibretroError("No game is loaded")
        buf = ctypes.create_string_buffer(data, len(data))
        if not bool(self.lib.retro_unserialize(buf, len(data))):
            raise LibretroError("retro_unserialize failed")
        self._audio_capture.reset()
        self.last_frame = None

    def save_state(self, path: str | Path) -> dict[str, Any]:
        data = self.serialize()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"path": str(path), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def load_state(self, path: str | Path) -> dict[str, Any]:
        data = Path(path).read_bytes()
        self.unserialize(data)
        return {"path": str(path), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    # ----------------------------- memory -----------------------------
    def memory_region(self, memory_type: str | int = "system_ram") -> bytes:
        if isinstance(memory_type, str):
            key = memory_type.lower()
            if key not in MEMORY_TYPES:
                raise ValueError(f"Unknown memory type: {memory_type}")
            mem_id = MEMORY_TYPES[key]
        else:
            mem_id = int(memory_type)
        size = int(self.lib.retro_get_memory_size(mem_id))
        ptr = self.lib.retro_get_memory_data(mem_id)
        if not ptr or size <= 0:
            return b""
        return ctypes.string_at(ptr, size)

    def memory_summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, mem_id in MEMORY_TYPES.items():
            try:
                size = int(self.lib.retro_get_memory_size(mem_id))
                ptr = self.lib.retro_get_memory_data(mem_id)
                out[name] = {"size": size, "available": bool(ptr and size > 0)}
                if ptr and size > 0:
                    sample = ctypes.string_at(ptr, min(size, 4096))
                    out[name]["sample_sha256"] = hashlib.sha256(sample).hexdigest()
            except Exception as exc:
                out[name] = {"size": 0, "available": False, "error": str(exc)}
        return out

    # ----------------------------- disc control -----------------------------
    def disk_status(self) -> dict[str, Any]:
        dc = self._disk_control
        if dc is None:
            return {"available": False}
        return {
            "available": True,
            "ejected": bool(dc.get_eject_state()),
            "image_index": int(dc.get_image_index()),
            "image_count": int(dc.get_num_images()),
        }

    def disk_set_index(self, index: int) -> bool:
        if self._disk_control is None:
            raise LibretroError("Core did not expose the libretro disk-control interface")
        return bool(self._disk_control.set_image_index(int(index)))

    def disk_eject(self, ejected: bool = True) -> bool:
        if self._disk_control is None:
            raise LibretroError("Core did not expose the libretro disk-control interface")
        return bool(self._disk_control.set_eject_state(bool(ejected)))

    # ----------------------------- callbacks -----------------------------
    def _environment(self, cmd: int, data: int) -> bool:
        try:
            if cmd == RETRO_ENVIRONMENT_GET_CAN_DUPE:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
                return True
            if cmd == RETRO_ENVIRONMENT_SHUTDOWN:
                self.shutdown_requested = True
                return True
            if cmd == RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = self._system_dir_b
                return True
            if cmd == RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = self._save_dir_b
                return True
            if cmd == RETRO_ENVIRONMENT_GET_CORE_ASSETS_DIRECTORY:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = self._assets_dir_b
                return True
            if cmd == RETRO_ENVIRONMENT_GET_LIBRETRO_PATH:
                ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = self._core_path_b
                return True
            if cmd == RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
                value = int(ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0])
                if value not in PIXEL_FORMAT_NAMES:
                    return False
                self.pixel_format = value
                return True
            if cmd == RETRO_ENVIRONMENT_GET_INPUT_BITMASKS:
                # This call is often made with a NULL data pointer and uses the return value only.
                return True
            if cmd == RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
                # Advertise legacy variables only.  Cores using libretro's option helper then
                # fall back to RETRO_ENVIRONMENT_SET_VARIABLES, which this frontend supports.
                if data:
                    ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
                return True
            if cmd == RETRO_ENVIRONMENT_SET_VARIABLES:
                if not data:
                    return True
                arr = ctypes.cast(data, ctypes.POINTER(RetroVariable))
                i = 0
                while i < 4096:
                    item = arr[i]
                    if not item.key:
                        break
                    key = _decode_cstr(item.key)
                    spec = _decode_cstr(item.value)
                    self._core_variables_seen[key] = spec
                    if key not in self._core_option_values:
                        # Legacy format: "Description; default|choice2|choice3"
                        choices = spec.split(";", 1)[1].strip() if ";" in spec else spec
                        default = choices.split("|", 1)[0].strip() if choices else ""
                        self._core_option_values[key] = default
                    i += 1
                return True
            if cmd == RETRO_ENVIRONMENT_GET_VARIABLE:
                if not data:
                    return False
                item = ctypes.cast(data, ctypes.POINTER(RetroVariable))[0]
                key = _decode_cstr(item.key)
                value = self._core_option_values.get(key)
                if value is None:
                    item.value = None
                else:
                    buf = value.encode("utf-8")
                    self._core_option_buffers[key] = buf
                    item.value = buf
                return True
            if cmd == RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
                if data:
                    ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = False
                return True
            if cmd == RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
                self.input_descriptors = []
                if not data:
                    return True
                arr = ctypes.cast(data, ctypes.POINTER(RetroInputDescriptor))
                for i in range(4096):
                    item = arr[i]
                    if not item.description:
                        break
                    self.input_descriptors.append({
                        "port": int(item.port), "device": int(item.device),
                        "index": int(item.index), "id": int(item.id),
                        "retropad_button": next((k for k, v in BUTTON_IDS.items() if v == int(item.id)), None),
                        "description": _decode_cstr(item.description),
                    })
                return True
            if cmd == RETRO_ENVIRONMENT_SET_DISK_CONTROL_INTERFACE:
                if not data:
                    return False
                self._disk_control = ctypes.cast(data, ctypes.POINTER(RetroDiskControlCallback))[0]
                return True
            if cmd in {
                RETRO_ENVIRONMENT_SET_CONTROLLER_INFO,
                RETRO_ENVIRONMENT_SET_MEMORY_MAPS,
                RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS,
            }:
                return True
            if cmd == RETRO_ENVIRONMENT_GET_USERNAME:
                if data:
                    ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = self._username_b
                return True
            if cmd == RETRO_ENVIRONMENT_GET_LANGUAGE:
                if data:
                    ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0  # English
                return True
            if cmd in {RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO, RETRO_ENVIRONMENT_SET_GEOMETRY}:
                # Acknowledge dynamic software geometry.  Width/height for evidence are taken
                # directly from the subsequent video callback, so no driver reinit is needed.
                return True
        except Exception as exc:
            self.messages.append(f"environment callback {cmd} failed: {exc}")
            del self.messages[:-64]
            return False
        return False

    def _video_refresh(self, data: int, width: int, height: int, pitch: int) -> None:
        self.frame_index += 1
        if not data:
            return  # duplicate previous frame
        ptr_value = int(ctypes.cast(data, ctypes.c_void_p).value or 0)
        if ptr_value == RETRO_HW_FRAME_BUFFER_VALID:
            self.hardware_video_seen = True
            return
        width = int(width); height = int(height); pitch = int(pitch)
        if width <= 0 or height <= 0 or pitch <= 0:
            return
        raw = ctypes.string_at(data, pitch * height)
        rgb = self._convert_frame(raw, width, height, pitch, self.pixel_format)
        self.last_frame = Frame(
            index=self.frame_index,
            width=width,
            height=height,
            pitch=pitch,
            pixel_format=PIXEL_FORMAT_NAMES.get(self.pixel_format, str(self.pixel_format)),
            rgb=rgb,
        )

    @staticmethod
    def _convert_frame(raw: bytes, width: int, height: int, pitch: int, pixel_format: int) -> bytes:
        out = bytearray(width * height * 3)
        oi = 0
        if pixel_format == RETRO_PIXEL_FORMAT_XRGB8888:
            for y in range(height):
                row = raw[y * pitch:y * pitch + width * 4]
                for x in range(width):
                    # Native-endian 0x00RRGGBB.  On the little-endian desktop platforms
                    # targeted by the original ROMancer release, bytes are BB GG RR XX.
                    word = int.from_bytes(row[x * 4:x * 4 + 4], byteorder=os.sys.byteorder, signed=False)
                    out[oi] = (word >> 16) & 0xFF
                    out[oi + 1] = (word >> 8) & 0xFF
                    out[oi + 2] = word & 0xFF
                    oi += 3
        elif pixel_format in (RETRO_PIXEL_FORMAT_0RGB1555, RETRO_PIXEL_FORMAT_RGB565):
            for y in range(height):
                row = raw[y * pitch:y * pitch + width * 2]
                for x in range(width):
                    word = int.from_bytes(row[x * 2:x * 2 + 2], byteorder=os.sys.byteorder, signed=False)
                    if pixel_format == RETRO_PIXEL_FORMAT_RGB565:
                        r5 = (word >> 11) & 0x1F
                        g6 = (word >> 5) & 0x3F
                        b5 = word & 0x1F
                        r = (r5 * 255 + 15) // 31
                        g = (g6 * 255 + 31) // 63
                        b = (b5 * 255 + 15) // 31
                    else:
                        r5 = (word >> 10) & 0x1F
                        g5 = (word >> 5) & 0x1F
                        b5 = word & 0x1F
                        r = (r5 * 255 + 15) // 31
                        g = (g5 * 255 + 15) // 31
                        b = (b5 * 255 + 15) // 31
                    out[oi:oi + 3] = bytes((r, g, b))
                    oi += 3
        else:
            raise LibretroError(f"Unsupported pixel format: {pixel_format}")
        return bytes(out)

    def _audio_sample(self, left: int, right: int) -> None:
        self._audio_capture.sample(left, right)

    def _audio_batch(self, samples, frames: int) -> int:
        return self._audio_capture.batch(samples, frames)

    def audio_summary(self) -> dict[str, Any]:
        return self._audio_capture.summary()

    def drain_audio(self) -> dict[str, Any]:
        return self._audio_capture.drain()

    def _input_poll(self) -> None:
        return

    def _input_state(self, port: int, device: int, index: int, control_id: int) -> int:
        if int(device) != RETRO_DEVICE_JOYPAD or int(index) != 0:
            return 0
        mask = int(self._joypads.get(int(port), 0)) & 0xFFFF
        if int(control_id) == RETRO_DEVICE_ID_JOYPAD_MASK:
            return ctypes.c_int16(mask).value
        cid = int(control_id)
        if 0 <= cid <= 15:
            return 1 if (mask & (1 << cid)) else 0
        return 0


def runtime_platform_report() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
        "libretro_api_supported": RETRO_API_VERSION,
        "shared_library_suffixes": [".so", ".dll", ".dylib"],
        "pixel_formats": list(PIXEL_FORMAT_NAMES.values()),
        "memory_types": list(MEMORY_TYPES.keys()),
        "joypad_buttons": list(BUTTON_IDS.keys()),
    }
