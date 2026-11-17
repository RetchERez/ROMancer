"""Tracing engines: where they live, which system each one serves, and how they load.

A tracing engine is a second build of a playtest engine that tags every byte
of palette and video memory with the ROM byte it came from (see
trace/DESIGN.md). They are optional and separate from the pinned playback
engines:

* ``ROMANCER_TRACE_CORES`` names a directory that holds them; otherwise a
  ``trace-cores`` directory beside the application is used.
* Normal play never loads one. ``TraceFrontend`` is the only loader, and in a
  packaged release it accepts only the builds listed in ``TRACE_CORE_PINS``.
  The playback check in ``bundled_cores`` is unchanged.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import sys
from array import array
from pathlib import Path

from .libretro_frontend import Frame, LibretroError, LibretroFrontend, PIXEL_FORMAT_NAMES, RETRO_HW_FRAME_BUFFER_VALID

ENV = 'ROMANCER_TRACE_CORES'
MARKER = b'romancer_trace_version'
SYSTEM_LABELS = {'nes': 'NES', 'snes': 'Super NES', 'genesis': 'Mega Drive / Genesis', 'sms': 'Master System',
                 'gb': 'Game Boy', 'gbc': 'Game Boy Color'}
# Library base names, in order of preference, for each supported system.
SYSTEM_CORES = {
    'gb': ('gambatte_libretro',),
    'gbc': ('gambatte_libretro',),
    'nes': ('fceumm_libretro',),
    'snes': ('bsnes_mercury_balanced_libretro', 'bsnes_mercury_accuracy_libretro', 'bsnes_libretro'),
    'genesis': ('blastem_libretro',),
    'sms': ('blastem_libretro',),
}
# Reviewed tracing builds for packaged releases: {sha256: {'name', 'source_url', 'source_commit', 'license', ...}}
# for Windows and Linux together, and each platform's complete trace-cores folder inventory. Both are
# written by tools/pin_trace_cores.py. A source checkout loads any tracing build it is pointed at.
from .trace_core_pins import TRACE_CORE_FILES, TRACE_CORE_PINS  # noqa: E402


class TraceCoreMissing(ValueError):
    """No tracing engine is installed for a system."""


def _suffix() -> str:
    return '.dll' if os.name == 'nt' else '.dylib' if os.uname().sysname == 'Darwin' else '.so'


def search_roots() -> list[Path]:
    configured = os.environ.get(ENV)
    if configured:
        return [Path(configured)]
    app = Path(__file__).resolve().parents[1]
    return [app / 'trace-cores', app.parent / 'trace-cores']


def _is_tracing_build(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size > 256 * 1024 ** 2:
            return False
        return MARKER in path.read_bytes()
    except OSError:
        return False


def _candidates(root: Path, name: str, depth: int = 2):
    """Files called `name` in `root` or up to `depth` folders below it, shallowest first."""
    level = [root]
    for _ in range(depth + 1):
        deeper = []
        for folder in level:
            candidate = folder / name
            if candidate.is_file():
                yield candidate
            try:
                deeper += sorted(p for p in folder.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith('.'))
            except OSError:
                continue
        level = deeper[:256]


def trace_core_for(system_id: str, source_sha256: str | None = None) -> Path:
    """The tracing engine for `system_id`, or TraceCoreMissing with a plain reason."""
    if system_id not in SYSTEM_CORES:
        raise TraceCoreMissing('Scene tracing supports NES, Super NES, Mega Drive, Master System, Game Boy and Game Boy Color games.')
    names = SYSTEM_CORES[system_id]
    if source_sha256:
        from .bundled_cores import cartridge_engine
        if cartridge_engine(system_id, source_sha256)[0] == 'snes-dsp4':
            names = ('bsnes_mercury_dsp4_libretro',)
    for root in search_roots():
        if not root.is_dir():
            continue
        for base in names:
            # Released packs name the library *_trace_libretro so it cannot be mistaken for the
            # playtest engine; a developer's own build may keep the makefile's name.
            for file in (base.replace('_libretro', '_trace_libretro') + _suffix(), base + _suffix()):
                found = [c for c in _candidates(root, file) if _is_tracing_build(c)]
                if found:   # nearest to the folder first; among equals, the newest build
                    depth = lambda c: len(c.relative_to(root).parts)
                    return min(found, key=lambda c: (depth(c), -c.stat().st_mtime)).resolve()
    label = SYSTEM_LABELS[system_id]
    raise TraceCoreMissing(f'The tracing engine is not installed for {label}. Scene editing for {label} games '
                           'becomes available when its tracing engine is added to the trace-cores folder.')


def available() -> dict[str, dict]:
    """{system id: {'installed', 'label', 'reason'}} for every supported system."""
    result = {}
    for system_id, label in SYSTEM_LABELS.items():
        try:
            trace_core_for(system_id)
            result[system_id] = {'installed': True, 'label': label, 'reason': ''}
        except TraceCoreMissing as error:
            result[system_id] = {'installed': False, 'label': label, 'reason': str(error)}
    return result


def require_reviewed_trace_core(path) -> dict | None:
    """Packaged releases load only pinned tracing builds; source checkouts load any tracing build."""
    path = Path(path)
    if not _is_tracing_build(path):
        raise ValueError('This engine is not a ROMancer tracing build.')
    from .bundled_cores import packaged_release
    if not packaged_release():
        return None
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    pin = TRACE_CORE_PINS.get(sha)
    if pin and pin.get('license') and pin.get('source_url') and pin.get('source_commit'):
        return pin
    raise ValueError('This release runs only reviewed tracing engines. Reinstall the tracing engine pack; '
                     'an unknown or changed engine is blocked.')


def trace_pack_members(root, platform_id: str | None = None) -> dict[str, bytes]:
    """Every file of a reviewed trace-cores folder, or ValueError when it differs from the pinned inventory.

    Used when a release is built and audited: the folder must hold exactly the
    pinned libraries with their origins, notices and source changes.
    """
    root = Path(root)
    if platform_id is None:
        import json
        try:
            platform_id = json.loads((root / 'TRACE-BUILD-INFO.json').read_text(encoding='utf-8'))['platform']
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError('tracing engine pack has no build record') from None
    expected = TRACE_CORE_FILES.get(platform_id)
    if not expected:
        raise ValueError('tracing engines have no reviewed inventory for ' + str(platform_id))
    actual = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('linked file in the tracing engine pack')
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(expected):
        raise ValueError('tracing engine pack has unlisted or missing files: ' + ', '.join(sorted(actual ^ set(expected))[:6]))
    result = {}
    for name, row in sorted(expected.items()):
        raw = (root / name).read_bytes()
        if len(raw) != row['size'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('tracing engine pack identity differs: ' + name)
        if name.endswith(('.dll', '.so')) and hashlib.sha256(raw).hexdigest() not in TRACE_CORE_PINS:
            raise ValueError('tracing engine is not pinned: ' + name)
        result[name] = raw
    return result


def core_options(system_id: str, source_sha256: str | None = None) -> dict[str, str]:
    """Engine options for tracing: the playback options, with colors shown as stored."""
    from .bundled_cores import cartridge_engine
    engine_id, compatibility = cartridge_engine(system_id, source_sha256)
    options = dict(compatibility)
    if system_id == 'snes':
        options.setdefault('bsnes_chip_hle', 'HLE')
    if system_id == 'sms':
        options.update({'blastem_system_type': 'sms', 'blastem_io_1': 'gamepad2.1', 'blastem_io_2': 'gamepad2.2'})
    if system_id in ('gb', 'gbc'):
        # Show palette colors as the cartridge stores them, so a picked color matches the screen.
        options.update({'gambatte_gbc_color_correction': 'disabled', 'gambatte_gb_colorization': 'disabled'})
    return options


def header_skip(data: bytes, suffix: str) -> int:
    """Bytes of container header before the ROM image that tracing offsets count from."""
    suffix = suffix.lower()
    if suffix == '.nes' and data[:4] == b'NES\x1a':
        return 16 + (512 if data[6] & 4 else 0)
    if suffix in ('.smc', '.sfc', '.swc', '.fig') and len(data) % 1024 == 512:
        return 512
    return 0


_TABLES: dict[int, list[bytes]] = {}


def _convert(raw: bytes, width: int, height: int, pitch: int, pixel_format: int) -> bytes:
    """RGB24 for a libretro frame; same values as LibretroFrontend._convert_frame, table driven."""
    if sys.byteorder != 'little' or pixel_format not in (0, 1, 2):
        return LibretroFrontend._convert_frame(raw, width, height, pitch, pixel_format)
    if pixel_format == 1:  # XRGB8888, stored BB GG RR XX
        out = bytearray(width * height * 3)
        for y in range(height):
            row = raw[y * pitch:y * pitch + width * 4]
            base = y * width * 3
            out[base:base + width * 3:3] = row[2::4]
            out[base + 1:base + width * 3:3] = row[1::4]
            out[base + 2:base + width * 3:3] = row[0::4]
        return bytes(out)
    table = _TABLES.get(pixel_format)
    if table is None:
        if pixel_format == 2:
            table = [bytes((((w >> 11 & 31) * 255 + 15) // 31, ((w >> 5 & 63) * 255 + 31) // 63, ((w & 31) * 255 + 15) // 31))
                     for w in range(65536)]
        else:
            table = [bytes((((w >> 10 & 31) * 255 + 15) // 31, ((w >> 5 & 31) * 255 + 15) // 31, ((w & 31) * 255 + 15) // 31))
                     for w in range(65536)]
        _TABLES[pixel_format] = table
    rows = []
    for y in range(height):
        rows.append(b''.join(map(table.__getitem__, array('H', raw[y * pitch:y * pitch + width * 2]))))
    return b''.join(rows)


class TraceFrontend(LibretroFrontend):
    """A headless host for tracing engines.

    Video frames are kept raw and converted only when read, so long replays
    run at the engine's speed.
    """

    def _require_reviewed_core(self) -> None:
        require_reviewed_trace_core(self.core_path)

    def _video_refresh(self, data: int, width: int, height: int, pitch: int) -> None:
        self.frame_index += 1
        if not data:
            return
        if int(ctypes.cast(data, ctypes.c_void_p).value or 0) == RETRO_HW_FRAME_BUFFER_VALID:
            self.hardware_video_seen = True
            return
        width, height, pitch = int(width), int(height), int(pitch)
        if width <= 0 or height <= 0 or pitch <= 0:
            return
        self._raw_video = (self.frame_index, ctypes.string_at(data, pitch * height), width, height, pitch, self.pixel_format)
        self._frame = None

    def run_frame(self, buttons=None, port: int = 0) -> None:
        """One frame. The picture is not returned; read `last_frame` when it is wanted."""
        if not self._loaded:
            raise LibretroError('No game is loaded')
        if buttons is not None:
            self.set_buttons(buttons, port)
        self.lib.retro_run()

    @property
    def last_frame(self) -> Frame | None:
        raw = getattr(self, '_raw_video', None)
        if getattr(self, '_frame', None) is None and raw is not None:
            index, pixels, width, height, pitch, pixel_format = raw
            self._frame = Frame(index=index, width=width, height=height, pitch=pitch,
                                pixel_format=PIXEL_FORMAT_NAMES.get(pixel_format, str(pixel_format)),
                                rgb=_convert(pixels, width, height, pitch, pixel_format))
        return getattr(self, '_frame', None)

    @last_frame.setter
    def last_frame(self, value: Frame | None) -> None:
        self._frame = value
        self._raw_video = None
