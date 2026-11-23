"""Know every change: scenes, live palettes, and edits checked by real replays.

An EditSession belongs to one ROM. It

* runs the ROM in its tracing engine (a separate process), exploring on its
  own or following the person's play, and records scenes: a savestate trail,
  the provenance tags of every traced domain, and the screen;
* keeps the scenes and their impact index in a store folder, so they are
  there next time;
* lists a scene's live palette as swatches, each either editable or locked
  with a plain reason;
* turns a color pick (or any list of ROM writes, such as a tile edit from
  graphics_trace) into a change: the bytes to write, every recorded scene
  that uses those bytes, and for each one a screenshot re-rendered by
  replaying the patched ROM in the real engine. Replays run in a small pool
  of worker processes and report as they finish;
* holds the change list, renders the final review, and only then saves
  through the exporter it is given.

Nothing here predicts a picture. A change is "verified" in a scene only when
a replay from an earlier savestate, with the changed ROM loaded, changes the
video memory that the tags said it would.
"""
from __future__ import annotations

import base64
import hashlib
import json
import multiprocessing
import os
import shutil
import struct
import tempfile
import threading
import time
import uuid
import zlib
from array import array
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import palette_trace as pt
from . import provenance as pv
from . import scene_graphics as sg
from . import scene_png as sp
from .level_session import LEVEL_EVERY, LEVEL_GAP, LevelTools
from .libretro_frontend import BUTTON_IDS, LibretroError
from .trace_cores import SYSTEM_LABELS, TraceCoreMissing, TraceFrontend, core_options, header_skip, trace_core_for

STEP_FRAMES = 300          # auto-explore looks at the screen this often
MAX_SCENES = 160
GRAPHICS_KEPT = 8          # scenes whose worked-out pictures and layers stay in memory
VIEWS_KEPT = 24            # scenes whose list of pictures stays ready, so going back to one does not wait
CHECKPOINT_EVERY = 60
MEMORY_DOMAINS = ('wram', 'hram', 'ram', 'sram')   # traced, but not what the screen is drawn from
_BUTTON_NAMES = sorted(BUTTON_IDS, key=BUTTON_IDS.get)
_NAME_CACHE: dict[int, tuple] = {}

LOCK_REASONS = {
    'derived': 'The game works this color out while it runs (a fade or a blend, for example), so there is no single '
               'stored color to change yet.',
    'unknown': "ROMancer has not seen where this color comes from. It was set before recording started, or this slot is unused.",
}


# ----------------------------------------------------------------- input

def explore(frame: int, variant: int = 0):
    """Deterministic play: get through menus, then walk, jump and attack (after trace/coverage_sweep.py)."""
    if frame < 240:
        return []
    phase = frame % 600
    if frame < 1800 or phase < 30:
        return ['start'] if frame % 90 < 4 and (frame // 90) % 3 == 0 else ['a'] if frame % 45 < 4 else []
    direction = ('right', 'down', 'left', 'up')[(frame // 600 + variant) % 4]
    held = [direction] if phase < 480 else []
    if frame % 40 < 6:
        held.append('b' if variant % 2 else 'a')
    if frame % 70 < 4:
        held.append('a' if variant % 2 else 'b')
    return held


def walk(frame: int, direction: str = 'right'):
    """Deterministic play for recording a level: keep going one way and jump now and then. No Start, so nothing pauses."""
    held = [direction]
    if frame % 48 < 14:
        held.append('a' if (frame // 48) % 2 else 'b')
    return held


def _mask(buttons) -> int:
    value = 0
    for name in buttons:
        key = str(name).lower()
        if key not in BUTTON_IDS:
            raise ValueError('Unknown controller button.')
        value |= 1 << BUTTON_IDS[key]
    return value


def _names(mask: int) -> tuple:
    names = _NAME_CACHE.get(mask)
    if names is None:
        names = _NAME_CACHE[mask] = tuple(n for n in _BUTTON_NAMES if mask >> BUTTON_IDS[n] & 1)
    return names


# ----------------------------------------------------------------- images

def png_bytes(width: int, height: int, rgb: bytes) -> bytes:
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xFFFFFFFF)
    stride = width * 3
    raw = b''.join(b'\x00' + rgb[y * stride:(y + 1) * stride] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def _fingerprint(width: int, height: int, rgb: bytes) -> bytes:
    """A 16x12 sample of the screen, for telling near-identical moments apart."""
    out = bytearray()
    for gy in range(12):
        y = (gy * 2 + 1) * height // 24
        for gx in range(16):
            x = (gx * 2 + 1) * width // 32
            i = (y * width + x) * 3
            out += rgb[i:i + 3]
    return bytes(out)


def _same_look(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        return False
    same = sum(1 for i in range(0, len(a), 3) if a[i:i + 3] == b[i:i + 3])
    return same * 100 >= (len(a) // 3) * 85


def _pixel_diff(a: bytes, b: bytes) -> int:
    if a == b:
        return 0
    if len(a) != len(b):
        return max(len(a), len(b)) // 3
    count = 0
    for start in range(0, len(a), 768):       # compare in rows of chunks; most chunks are equal
        if a[start:start + 768] != b[start:start + 768]:
            for i in range(start, min(start + 768, len(a)), 3):
                if a[i:i + 3] != b[i:i + 3]:
                    count += 1
    return count


# ----------------------------------------------------------------- tracing engine helpers

class _Session(pv.TraceSession):
    """TraceSession whose snapshot survives a domain that advertises more bytes than it has."""

    def snapshot(self):
        try:
            return super().snapshot()
        except OSError:
            return self._guarded_snapshot()

    def _guarded_snapshot(self):
        import ctypes
        domains = {}
        for i in range(self.lib.romancer_trace_domain_count()):
            d = self.lib.romancer_trace_domain(i).contents
            n, name = d.size, d.name.decode()

            def read(pointer, width):
                if not pointer:
                    return None
                out = bytearray()
                base = ctypes.cast(pointer, ctypes.c_void_p).value
                for start in range(0, n * width, 4096):
                    try:
                        out += ctypes.string_at(base + start, min(4096, n * width - start))
                    except OSError:
                        break
                return bytes(out) + bytes(n * width - len(out))
            tags, pcs = array('I'), array('I')
            tags.frombytes(read(d.tag, 4) or bytes(n * 4))
            pcs.frombytes(read(d.pc, 4) or bytes(n * 4))
            domains[name] = pv.DomainSnapshot(name, read(d.data, 1), tags, pcs)
        frame = self.fe.last_frame
        return pv.Snapshot(self.frame, domains, frame.sha256() if frame else None)


class _Engine(TraceFrontend):
    """A tracing engine with its own empty save folder, removed when it closes."""

    def close(self) -> None:
        try:
            super().close()
        finally:
            shutil.rmtree(getattr(self, '_romancer_save_dir', ''), ignore_errors=True)
            self._unload()

    def _unload(self) -> None:
        """Unload the engine library so the next engine in this process starts with clean statics.

        Engines keep some memory (a palette shadow, for one) in static storage
        that neither closing a game nor loading a savestate resets. Left
        loaded, one replay's leftovers would show up in the next.
        """
        lib, self.lib = getattr(self, 'lib', None), None
        handle = getattr(lib, '_handle', None)
        if handle is None:
            return
        try:
            import ctypes
            if os.name == 'nt':
                free = ctypes.WinDLL('kernel32').FreeLibrary
                free.argtypes = [ctypes.c_void_p]
                free(handle)
            else:
                import _ctypes
                _ctypes.dlclose(handle)
        except Exception:
            pass


def _frontend(cfg: dict, rom_path) -> _Engine:
    work = Path(cfg['store']) / 'work'
    work.mkdir(parents=True, exist_ok=True)
    save_dir = Path(tempfile.mkdtemp(prefix='engine-', dir=work))   # empty: battery saves must not leak between runs
    fe = _Engine(cfg['core'], save_dir=save_dir, core_options=cfg['options'])
    fe._romancer_save_dir = save_dir
    try:
        fe.load_game(rom_path)
    except BaseException:
        _close(fe)
        raise
    return fe


def _close(fe) -> None:
    try:
        fe.close()
    except Exception:
        pass


def _begin(session) -> int:
    """Start tracing with a power-on savestate; returns how many frames had to run first.

    Some engines cannot save a state until they have run a frame. Tracing is
    switched on before that frame, so nothing it loads goes untagged.
    """
    try:
        session.start()
        return 0
    except LibretroError:
        session.lib.romancer_trace_reset()
        session.lib.romancer_trace_enable(1)
        session.fe.run_frame([])
        session.frame += 1
        session.checkpoints = [(session.frame, session.fe.serialize())]
        return 1


def _video_domains(snapshot) -> list[str]:
    return [name for name in snapshot.domains if name not in MEMORY_DOMAINS]


def _thin(checkpoints, frame: int) -> list:
    """The savestates a replay may start from: the latest, then twice as far back each time, then power-on."""
    earlier = [(f, s) for f, s in checkpoints if f < frame]
    if not earlier:
        return []
    chosen = {earlier[-1][0]: earlier[-1][1], earlier[0][0]: earlier[0][1]}
    distance = 2 * CHECKPOINT_EVERY
    while distance < frame:
        candidates = [(f, s) for f, s in earlier if f <= frame - distance]
        if not candidates:
            break
        chosen[candidates[-1][0]] = candidates[-1][1]
        distance *= 2
    return sorted(chosen.items())


# ----------------------------------------------------------------- scene files

MAGIC = b'RSC1'


def write_scene(path: Path, scene: pv.Scene, meta: dict, width: int, height: int, rgb: bytes) -> None:
    header = dict(meta, width=width, height=height,
                  domains=[[name, len(d.tags), d.data is not None] for name, d in scene.snapshot.domains.items()])
    body = bytearray()
    for d in scene.snapshot.domains.values():
        if d.data is not None:
            body += d.data
        body += d.tags.tobytes() + d.pcs.tobytes()
    body += rgb
    head = json.dumps(header, sort_keys=True).encode()
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(MAGIC + struct.pack('<I', len(head)) + head + zlib.compress(bytes(body), 1))
    os.replace(temporary, path)


def read_scene_header(path: Path) -> dict:
    with Path(path).open('rb') as stream:
        if stream.read(4) != MAGIC:
            raise ValueError('not a ROMancer scene')
        return json.loads(stream.read(struct.unpack('<I', stream.read(4))[0]))


def read_scene(path: Path):
    """(Scene without savestates, header, screen RGB)."""
    raw = Path(path).read_bytes()
    if raw[:4] != MAGIC:
        raise ValueError('not a ROMancer scene')
    size = struct.unpack('<I', raw[4:8])[0]
    header = json.loads(raw[8:8 + size])
    body = zlib.decompress(raw[8 + size:])
    at = 0
    domains = {}
    for name, count, has_data in header['domains']:
        data = None
        if has_data:
            data = body[at:at + count]
            at += count
        tags, pcs = array('I'), array('I')
        tags.frombytes(body[at:at + 4 * count]); at += 4 * count
        pcs.frombytes(body[at:at + 4 * count]); at += 4 * count
        domains[name] = pv.DomainSnapshot(name, data, tags, pcs)
    rgb = body[at:at + header['width'] * header['height'] * 3]
    snapshot = pv.Snapshot(header['frame'], domains, header['screen_sha256'])
    scene = pv.Scene(header['id'], header['frame'], header['screen_sha256'], [], snapshot, header.get('label', ''))
    scene.video = header.get('video')       # the video registers, when the engine exposed them (graphics_trace.capture_video)
    return scene, header, rgb


# ----------------------------------------------------------------- the live engine (its own process)

class _Host:
    def __init__(self, cfg: dict, conn):
        self.cfg, self.conn = cfg, conn
        self.store = Path(cfg['store'])
        self.run_dir = self.store / 'runs' / cfg['run']
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.store / 'scenes').mkdir(parents=True, exist_ok=True)
        self.fe = _frontend(cfg, cfg['rom'])
        self.session = _Session(self.fe, checkpoint_every=CHECKPOINT_EVERY, keep=400)
        primed = _begin(self.session)
        size = len(self.session.checkpoints[0][1])
        self.session.keep = max(40, min(600, 96 * 1024 ** 2 // max(size, 1)))
        self.inputs = array('H', [0] * primed)
        self.level_look, self.level_frame = None, -10 ** 9
        self.known = []     # (palette source hash, fingerprint) of scenes already in the store
        for path in (self.store / 'scenes').glob('*.scene'):
            try:
                header = read_scene_header(path)
                self.known.append((header.get('palette_sources'), bytes.fromhex(header.get('fingerprint', ''))))
            except (ValueError, OSError, KeyError):
                continue
        saved = self.run_dir / 'inputs.bin'
        if cfg.get('from_run'):
            source = self.store / 'runs' / cfg['from_run']
            masks = array('H')
            masks.frombytes((source / 'inputs.bin').read_bytes())
            target = min(len(masks), int(cfg['from_frame']))
            start = max([f for f in cfg.get('from_checkpoints') or [] if f <= target and (source / f'{f}.st').exists()], default=None)
            if start is not None and start > self.session.frame:
                self.fe.unserialize(zlib.decompress((source / f'{start}.st').read_bytes()))
                self.session.frame = start
                self.session.checkpoints = [(start, self.fe.serialize())]
                self.inputs = masks[:start]
            rest = masks[self.session.frame:target]
            for at in range(0, len(rest), 600):
                self.advance(rest[at:at + 600])
                conn.send(('progress', min(at + 600, len(rest)), len(rest)))
        elif cfg.get('resume') and saved.exists():
            masks = array('H')
            masks.frombytes(saved.read_bytes())
            masks = masks[primed:]
            for start in range(0, len(masks), 600):
                self.advance(masks[start:start + 600])
                conn.send(('progress', min(start + 600, len(masks)), len(masks)))

    def advance(self, masks) -> None:
        start = self.session.frame
        self.session.run(len(masks), lambda f: _names(masks[f - start]))
        self.inputs.extend(masks)

    def play_level(self, masks, label: str) -> list:
        """Advance, looking at the screen every few frames and keeping a scene whenever it has moved."""
        metas = []
        for start in range(0, len(masks), LEVEL_EVERY):
            self.advance(masks[start:start + LEVEL_EVERY])
            frame = self.frame()
            look = _fingerprint(frame.width, frame.height, frame.rgb)
            last = self.level_look
            if last is not None and len(last) == len(look) and sum(
                    1 for i in range(0, len(look), 3) if look[i:i + 3] != last[i:i + 3]) < 3:
                continue                                  # the screen stood still (a few blinking pixels at most)
            if len(set(frame.rgb[i:i + 3] for i in range(0, len(frame.rgb), 3 * 97))) < 2:
                continue                                  # a blank screen between rooms
            if self.session.frame - self.level_frame < LEVEL_GAP:
                continue                                  # the last capture is still close enough to place this one
            metas.append(self.record(label, 'level', only_new=False))
            self.level_look, self.level_frame = look, self.session.frame
        return metas

    def frame(self):
        if self.fe.last_frame is None:
            self.advance(array('H', [0]))
        return self.fe.last_frame

    def record(self, label: str, origin: str, *, only_new: bool):
        frame = self.frame()
        scene = pv.scene_from_session(self.session, label)
        if only_new and len(set(frame.rgb[i:i + 3] for i in range(0, len(frame.rgb), 3 * 97))) < 2:
            return None                                   # a blank screen between scenes
        sources = set()
        for name, d in scene.snapshot.domains.items():
            if 'pal' in name or 'cram' in name:
                sources.update((name, o) for o in d.sources())
        palette_sources = hashlib.sha1(repr(sorted(sources)).encode()).hexdigest()
        fingerprint = _fingerprint(frame.width, frame.height, frame.rgb)
        if only_new and any(p == palette_sources and _same_look(f, fingerprint) for p, f in self.known):
            return None
        scene.id = hashlib.sha256(f"{self.cfg['run']}:{scene.frame}:{scene.screen_sha256}".encode()).hexdigest()[:16]
        path = self.store / 'scenes' / (scene.id + '.scene')
        thin = _thin(self.session.checkpoints, scene.frame)
        for start, state in thin:
            target = self.run_dir / f'{start}.st'
            if not target.exists():
                target.write_bytes(zlib.compress(state, 1))
        temporary = self.run_dir / 'inputs.tmp'
        temporary.write_bytes(self.inputs.tobytes())
        os.replace(temporary, self.run_dir / 'inputs.bin')
        try:
            from . import graphics_trace
            video = graphics_trace.capture_video(self.session, self.cfg['system'])
        except Exception:
            video = None                                   # layers() then infers the layout and says so
        meta = {'id': scene.id, 'frame': scene.frame, 'screen_sha256': scene.screen_sha256, 'label': label,
                'origin': origin, 'run': self.cfg['run'], 'created': time.time(), 'checkpoints': [f for f, _ in thin],
                'palette_sources': palette_sources, 'fingerprint': fingerprint.hex(), 'video': video}
        if not path.exists():
            write_scene(path, scene, meta, frame.width, frame.height, frame.rgb)
            (self.store / 'scenes' / (scene.id + '.png')).write_bytes(png_bytes(frame.width, frame.height, frame.rgb))
        self.known.append((palette_sources, fingerprint))
        return meta

    def serve(self) -> None:
        conn = self.conn
        while True:
            try:
                command = conn.recv()
            except (EOFError, OSError):
                return
            kind = command[0]
            if kind == 'close':
                return
            if kind == 'stop':
                continue
            if kind == 'explore':
                _, steps, variant, *level = command
                for step in range(steps):
                    if conn.poll() and conn.recv()[0] in ('stop', 'close'):
                        break
                    start = self.session.frame
                    if level and level[0]:              # a level is being recorded: walk on, and capture as the screen moves
                        masks = array('H', [_mask(walk(f, level[1] if len(level) > 1 else 'right'))
                                            for f in range(start, start + STEP_FRAMES)])
                    else:
                        masks = array('H', [_mask(explore(f, variant)) for f in range(start, start + STEP_FRAMES)])
                    if level and level[0]:
                        conn.send(('step', step + 1, steps, None, self.session.frame, self.play_level(masks, level[0])))
                        continue
                    self.advance(masks)
                    conn.send(('step', step + 1, steps, self.record('', 'explore', only_new=True), self.session.frame))
                conn.send(('done', self.session.frame))
            elif kind == 'play':
                _, frames, mask, *level = command
                metas = []
                if level and level[0]:
                    metas = self.play_level(array('H', [mask]) * frames, level[0])
                else:
                    self.advance(array('H', [mask]) * frames)
                frame = self.frame()
                conn.send(('frame', png_bytes(frame.width, frame.height, frame.rgb), self.session.frame, frame.width, frame.height, metas))
            elif kind == 'capture':
                conn.send(('scene', self.record(command[1], 'play', only_new=False), self.session.frame))


def _host_main(conn, cfg: dict) -> None:
    host = None
    try:
        host = _Host(cfg, conn)
        conn.send(('ready', host.session.frame))
        host.serve()
    except BaseException as error:      # reported to the workbench, never hidden
        try:
            conn.send(('error', f'{type(error).__name__}: {error}'))
        except OSError:
            pass
    finally:
        if host is not None:
            _close(host.fe)


# ----------------------------------------------------------------- replays (worker processes)

def _replay(fe, state: bytes, start: int, scene: pv.Scene, buttons, settled=None, slack: int = 0):
    """Replay to the scene's frame. With `settled`, run up to `slack` more frames until it accepts the snapshot.

    A routine added to the game costs a little time each frame, so a patched
    game may reach the same moment a frame or two late. Returns the snapshot,
    the screen, and how many frames late it was (None when it never settled).
    """
    if int(fe.lib.retro_serialize_size()) <= 0:
        fe.run_frame([])                # some engines accept a savestate only after their first frame
    fe.unserialize(state)
    session = _Session(fe, checkpoint_every=10 ** 9)
    session.frame = start
    session.lib.romancer_trace_reset()
    session.lib.romancer_trace_enable(1)
    session.run(scene.frame - start, buttons)
    first = snapshot, frame = session.snapshot(), fe.last_frame
    if settled is None or settled(snapshot):
        return snapshot, frame, 0
    for late in range(1, slack + 1):
        session.run(1, buttons)
        snapshot = session.snapshot()
        if settled(snapshot):
            return snapshot, fe.last_frame, late
    return first[0], first[1], None


class _Trail:
    """One scene's savestates, and what replaying the unchanged game from each one gives.

    A replay is judged against a baseline: the same replay with the unchanged
    ROM, in a freshly loaded engine. Comparing like with like matters for two
    reasons. A savestate does not always hold everything, so from some states
    even the unchanged game draws a different frame; those states are never
    used. And an engine's view of palette memory after loading a savestate
    only holds what the game has written since, so it cannot be compared
    with the recording itself.
    """

    def __init__(self, job: dict, scene: pv.Scene, header: dict, rgb: bytes):
        self.job, self.scene, self.header, self.rgb = job, scene, header, rgb
        self.run_dir = Path(job['store']) / 'runs' / header['run']
        self.inputs = array('H')
        self.inputs.frombytes((self.run_dir / 'inputs.bin').read_bytes())

    def buttons(self, frame: int):
        return _names(self.inputs[frame]) if frame < len(self.inputs) else ()

    def state(self, start: int) -> bytes:
        return zlib.decompress((self.run_dir / f'{start}.st').read_bytes())

    def replay(self, rom_path, start: int, want=None, slack: int = 0):
        """(video memory, screen) after replaying `rom_path` from `start`; with `want`, also how many frames late it matched."""
        video = lambda snapshot: {name: snapshot.domains[name].data for name in _video_domains(snapshot)
                                  if snapshot.domains[name].data is not None}
        settled = None if want is None else (lambda snapshot: all(video(snapshot).get(name) == value for name, value in want.items()))
        fe = _frontend(self.job, rom_path)
        try:
            snapshot, frame, late = _replay(fe, self.state(start), start, self.scene, self.buttons, settled, slack)
        finally:
            _close(fe)
        return (video(snapshot), frame) if want is None else (video(snapshot), frame, late)

    def baseline(self, start: int):
        """Video memory after replaying the unchanged ROM from `start`, or None if that does not redraw the recorded screen."""
        path = self.run_dir / f"base-{self.header['id']}-{start}.bin"
        try:
            raw = path.read_bytes()
            size = struct.unpack('<I', raw[:4])[0]
            head = json.loads(raw[4:4 + size])
            if not head['faithful']:
                return None
            body, at, data = zlib.decompress(raw[4 + size:]), 0, {}
            for name, length in head['domains']:
                data[name] = body[at:at + length]
                at += length
            return data
        except (OSError, ValueError, KeyError, struct.error, zlib.error):
            pass
        data, frame = self.replay(self.job['base_rom'], start)
        faithful = frame is not None and frame.rgb == self.rgb
        head = json.dumps({'faithful': faithful, 'domains': [[name, len(value)] for name, value in data.items()]}).encode()
        temporary = path.with_suffix(f'.{os.getpid()}.tmp')
        temporary.write_bytes(struct.pack('<I', len(head)) + head + zlib.compress(b''.join(data.values()) if faithful else b'', 1))
        os.replace(temporary, path)
        return data if faithful else None

    def faithful(self, start: int) -> bool:
        return self.baseline(start) is not None


def _differences(before: dict, after: dict) -> dict:
    out = {}
    for name, a in before.items():
        b = after.get(name)
        if b is None or a == b:
            continue
        out[name] = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return out


def replay_task(job: dict) -> dict:
    """Replay one scene with a changed ROM and report what the engine drew.

    Starts at the latest savestate and steps back until the change reaches the
    scene (provenance.verify_edit's rule), because data the game had already
    copied into video memory before a savestate would hide the edit. Only
    savestates that replay the unchanged game exactly are used.
    """
    started = time.perf_counter()
    store = Path(job['store'])
    out = store / 'renders' / (job['key'] + '.png')
    side = out.with_suffix('.json')
    if out.exists() and side.exists():
        try:
            return json.loads(side.read_text())
        except ValueError:
            pass
    result = {'scene_id': job['scene_id'], 'key': job['key'], 'rom_sha': job['rom_sha'], 'verified': False,
              'confidence': 'none', 'from_frame': None, 'changed': {}, 'pixels': 0, 'tried': [], 'unfaithful': []}
    try:
        scene, header, rgb = read_scene(store / 'scenes' / (job['scene_id'] + '.scene'))
        trail = _Trail(job, scene, header, rgb)
        starts = sorted(header['checkpoints'], reverse=True)
        hint = job.get('hint')
        if hint is not None and any(f <= hint for f in starts):
            starts = [f for f in starts if f <= hint]
        if job.get('thorough'):
            starts = starts[-1:]          # from power-on: the whole truth, for edits that touch many bytes
        expected = {name: set(indices) for name, indices in job.get('expected', {}).items()}
        plan = {name: {int(i): v for i, v in cells.items()} for name, cells in (job.get('plan_expect') or {}).items()}
        final = quiet = None
        for start in starts:
            base = trail.baseline(start)
            if base is None:
                result['unfaithful'].append(start)
                continue
            if plan and all(name in base for name in plan):
                # The edited scene: the planned bytes should hold their planned values and nothing else should move.
                want = {name: bytearray(value) for name, value in base.items() if name in plan}
                for name, cells in plan.items():
                    for i, v in cells.items():
                        want[name][i] = v
                data, frame, late = trail.replay(job['rom'], start, {name: bytes(value) for name, value in want.items()}, 12)
                moved = _differences(base, data)
                result.update(as_planned=all(data[name][i] == v for name, cells in plan.items() for i, v in cells.items()),
                              unplanned={name: count for name, indices in moved.items()
                                         if (count := sum(i not in plan.get(name, ()) for i in indices))},
                              late=late)
            else:
                data, frame = trail.replay(job['rom'], start)
            result['tried'].append(start)
            changed = _differences(base, data)
            pixels = _pixel_diff(rgb, frame.rgb)
            final = (start, changed, pixels, frame)
            exact = any(i in expected.get(name, ()) for name, indices in changed.items() for i in indices)
            confidence = 'exact' if exact else 'replay'    # 'replay': it changed, though not at the bytes the tags named
            if pixels or (job.get('fixed') and changed):
                result.update(verified=True, confidence=confidence)
                break
            if changed:
                # Memory changed but the picture did not. An earlier savestate may still show it
                # (the game may have drawn with the old value already), so keep stepping back;
                # the earliest replay is the one to believe.
                quiet = (final, confidence)
            if job.get('fixed'):
                break
        if not result['verified'] and quiet is not None:
            final = quiet[0]
            result.update(verified=True, confidence=quiet[1])
        if final is not None:
            start, changed, pixels, frame = final
            frame_rgb = frame.rgb
            if not result['verified']:
                changed, pixels, frame_rgb = {}, 0, rgb          # the change never reached this scene
            result.update(from_frame=start if result['verified'] else None,
                          changed={name: len(indices) for name, indices in changed.items()}, pixels=pixels)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(png_bytes(header['width'], header['height'], frame_rgb))
        else:
            result['error'] = ('This scene does not replay the same way twice in the engine, so a picture of it cannot be trusted.'
                               if result['unfaithful'] else 'This scene has no savestate to replay from.')
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result['seconds'] = round(time.perf_counter() - started, 2)
    if 'error' not in result:
        side.write_text(json.dumps(result))
    return result


def private_copy_task(job: dict) -> dict:
    """Plan "only this scene": graphics_trace copies the data and repoints the one use, checking by replay."""
    try:
        from types import SimpleNamespace
        from . import graphics_trace as gt
        store = Path(job['store'])
        scene, header, _ = read_scene(store / 'scenes' / (job['scene_id'] + '.scene'))
        trail = _Trail(job, scene, header, _)
        inputs = trail.inputs
        scene.checkpoints = [(f, trail.state(f)) for f in sorted(header['checkpoints']) if trail.faithful(f)]
        if not scene.checkpoints:
            return {'error': 'This scene does not replay the same way twice in the engine, so a private copy cannot be checked.'}
        rom = Path(job['base_rom']).read_bytes()
        item = SimpleNamespace(system=job['system'], domain=job['domain'], addresses=list(job['addresses']),
                               stored=bytes(job['stored']), status=job['status'], layout='plain')

        def make(data):
            path = store / 'work' / (hashlib.sha256(data).hexdigest()[:24] + job['suffix'])
            if not path.exists():
                path.write_bytes(data)
            return _frontend(job, path)
        domains = list(dict.fromkeys([job['domain'], 'palette', 'vram', 'chr', 'vram4']))
        verify = lambda plan: gt.verify_plan(make, rom, plan, scene, domains=domains,
                                             buttons_for=lambda f: _names(inputs[f]) if f < len(inputs) else ())
        plan = gt.plan_private_copy(item, bytes(job['new_stored']), rom, scene, verify=verify)
        if plan.rom_size != len(rom) or any(old is None for _, old, _ in plan.writes):
            return {'error': 'A private copy needs more room than this ROM has free. Change it everywhere instead.'}
        if not (plan.verified or {}).get('as_planned'):
            return {'error': 'A private copy was planned, but the replay did not show the new color in this scene.'}
        return {'writes': [[int(o), int(a), int(b)] for o, a, b in plan.writes if a != b], 'notes': [str(n) for n in plan.notes]}
    except ValueError as error:
        return {'error': str(error)}
    except Exception as error:
        return {'error': f'{type(error).__name__}: {error}'}


# ----------------------------------------------------------------- color pickers

def picker_for(fmt: str) -> dict:
    """What the hardware can show, so the picker offers nothing else."""
    if fmt == 'nes-index':
        return {'kind': 'master', 'label': 'NES colors', 'colors': [list(c) for c in pt.NES_RGB],
                'hidden': [i for i in range(64) if i & 0x0F in (0x0D, 0x0E, 0x0F)],
                'help': 'The NES has one fixed set of colors. Pick one of them.'}
    if fmt == 'dmg-shades':
        return {'kind': 'shades', 'label': 'Game Boy shades', 'colors': [[255] * 3, [170] * 3, [85] * 3, [0] * 3],
                'help': 'The original Game Boy shows four shades. Choose which shade each of the four slots uses.'}
    bits = {'rgb555-le': 5, 'rgb555-be': 5, 'genesis': 3, 'sms-rgb222': 2}.get(fmt, 8)
    top = (1 << bits) - 1
    names = {5: '32 levels of red, green and blue', 3: '8 levels of red, green and blue', 2: '4 levels of red, green and blue'}
    return {'kind': 'levels', 'label': names.get(bits, 'Full color'), 'levels': [round(i * 255 / top) for i in range(top + 1)],
            'help': f'This system stores {names.get(bits, "full color")}. The picker snaps to the nearest color it can show.'}


# ----------------------------------------------------------------- the session

class EditSession(LevelTools):
    """Scenes, palettes and the pending change list for one ROM."""

    def __init__(self, store, rom_path, system_id: str, *, core=None, workers=None, options=None):
        self.store = Path(store)
        self.rom_path = Path(rom_path)
        self.system = system_id
        self.suffix = self.rom_path.suffix or '.bin'
        self.rom = self.rom_path.read_bytes()
        self.rom_sha = hashlib.sha256(self.rom).hexdigest()
        self.skip = header_skip(self.rom, self.suffix)
        self.core = str(core) if core else None
        self.core_error = ''
        if self.core is None:
            try:
                self.core = str(trace_core_for(system_id, self.rom_sha))
            except TraceCoreMissing as error:
                self.core_error = str(error)
        self.options = options if options is not None else core_options(system_id, self.rom_sha)
        self.workers = max(1, min(4, int(workers or os.environ.get('ROMANCER_TRACE_WORKERS') or min(3, (os.cpu_count() or 2) - 1))))
        self.lock = threading.RLock()
        self.host_lock = threading.Lock()
        self.scenes: dict[str, pv.Scene] = {}
        self.meta: dict[str, dict] = {}
        self.rgb: dict[str, bytes] = {}
        self.impact = pv.ImpactIndex()
        self._sources: dict[tuple, dict] = {}
        self._roms: dict[str, bytes] = {}
        self.changes: list[dict] = []
        self.preview: dict | None = None
        self.revision = 0
        self.review_state: dict | None = None
        self.renders: dict[tuple, dict] = {}
        self.pending: set = set()
        self._graphics_cache: dict[str, sg.SceneGraphics] = {}
        self._views: dict[tuple, dict] = {}
        self._editable: dict[str, dict] = {}
        self._chr_used: dict[str, set] = {}
        self._checksum_bytes: set | None = None
        self._read_ranges: tuple | None = None
        self.live = {'state': 'off', 'message': '', 'frame': 0, 'progress': None}
        self.recording: dict | None = None
        self._host = None
        self._pool = None
        self._closed = False
        for folder in ('scenes', 'runs', 'renders', 'work'):
            (self.store / folder).mkdir(parents=True, exist_ok=True)
        self._load()
        self._levels_init()

    # ---- store

    def _load(self) -> None:
        headers = []
        for path in (self.store / 'scenes').glob('*.scene'):
            try:
                headers.append((read_scene_header(path), path))
            except (ValueError, OSError):
                continue
        for header, path in sorted(headers, key=lambda item: item[0].get('created', 0)):
            try:
                self._add_scene(path)
            except (ValueError, OSError, KeyError, zlib.error):
                continue
        saved = self.store / 'changes.json'
        if saved.exists():
            try:
                value = json.loads(saved.read_text())
                if value.get('rom_sha') == self.rom_sha:
                    self.changes = [c for c in value['changes'] if c.get('scene_id') in self.scenes]
                    self.revision = int(value.get('revision', 0))
                    for change in self.changes:
                        for result in change['affected'].values():
                            if result.get('state') != 'done':   # a replay was cut short by closing the app
                                result.update(state='failed', error='Not finished; remove and repeat this change.')
            except (ValueError, KeyError, TypeError):
                self.changes = []

    def _persist(self) -> None:
        temporary = self.store / 'changes.tmp'
        temporary.write_text(json.dumps({'rom_sha': self.rom_sha, 'revision': self.revision, 'changes': self.changes}))
        os.replace(temporary, self.store / 'changes.json')

    def _add_scene(self, path: Path) -> dict:
        scene, header, rgb = read_scene(path)
        with self.lock:
            if scene.id not in self.scenes:
                self.scenes[scene.id] = scene
                self.meta[scene.id] = header
                self.rgb[scene.id] = rgb
                self.impact.add(scene)
        return header

    def _scene(self, scene_id: str) -> pv.Scene:
        if scene_id not in self.scenes:
            raise ValueError('That scene is no longer recorded. Choose another scene.')
        return self.scenes[scene_id]

    def _label(self, scene_id: str) -> str:
        meta = self.meta[scene_id]
        if meta.get('label'):
            return meta['label']
        number = list(self.scenes).index(scene_id) + 1
        seconds = meta['frame'] // 60
        return f'Scene {number} ({seconds // 60}:{seconds % 60:02d} into play)'

    # ---- the live engine

    def _require_core(self) -> None:
        if not self.core:
            raise TraceCoreMissing(self.core_error)

    def _current_run(self) -> tuple[str, bool]:
        pointer = self.store / 'current_run'
        if pointer.exists():
            run = pointer.read_text().strip()
            if (self.store / 'runs' / run / 'inputs.bin').exists():
                return run, True
        run = uuid.uuid4().hex
        pointer.write_text(run)
        return run, False

    def _cfg(self) -> dict:
        return {'core': self.core, 'options': self.options, 'system': self.system, 'suffix': self.suffix,
                'store': str(self.store), 'rom': str(self.rom_path)}

    def _start_host(self) -> None:
        """Start the live engine and bring it back to where play left off. Call with host_lock held."""
        if self._host and self._host[0].is_alive():
            if not self.live.get('playtest'):
                return
            self._drop_host()
        self._require_core()
        run, resume = self._current_run()
        variant = sum(1 for p in (self.store / 'runs').iterdir() if p.is_dir()) - 1
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        process = context.Process(target=_host_main, args=(child, dict(self._cfg(), run=run, resume=resume)), daemon=True)
        self.live.update(state='starting', message='Catching up to where you left off…' if resume else 'Starting the game…', progress=None)
        process.start()
        child.close()
        self._host = (process, parent, max(0, variant))
        while True:
            event = self._receive()
            if event[0] == 'progress':
                self.live['progress'] = [event[1], event[2]]
            elif event[0] == 'ready':
                self.live.update(state='ready', message='', frame=event[1], progress=None)
                return

    def _receive(self):
        process, conn, _ = self._host
        while not conn.poll(0.25):
            if not process.is_alive() and not conn.poll(0):
                self._drop_host('The tracing engine stopped unexpectedly. Try again.')
                raise RuntimeError(self.live['message'])
        try:
            event = conn.recv()
        except (EOFError, OSError):
            self._drop_host('The tracing engine stopped unexpectedly. Try again.')
            raise RuntimeError(self.live['message']) from None
        if event[0] == 'error':
            self._drop_host('The tracing engine could not run this game: ' + event[1])
            raise RuntimeError(self.live['message'])
        return event

    def _drop_host(self, message: str = '') -> None:
        host, self._host = self._host, None
        self.live.update(state='off', message=message, progress=None, playtest=None)
        if host:
            process, conn, _ = host
            try:
                conn.send(('close',))
            except OSError:
                pass
            process.join(2)
            if process.is_alive():
                process.terminate()
            conn.close()

    def record(self, steps: int = 40, *, restart: bool = False, wait: bool = False) -> dict:
        """Auto-explore: play the game by itself and keep each new-looking moment as a scene."""
        self._require_core()
        steps = max(1, min(400, int(steps)))
        with self.lock:
            if self.recording and self.recording['state'] == 'running':
                return self.summary()
            if len(self.scenes) - len(self.level_scene_ids()) >= MAX_SCENES:
                raise ValueError(f'This game already has {MAX_SCENES} recorded scenes. Remove some before recording more.')
            self.recording = {'state': 'running', 'done': 0, 'total': steps, 'found': 0, 'message': 'Starting the game…'}
        thread = threading.Thread(target=self._record_worker, args=(steps, restart), name='romancer-scenes', daemon=True)
        thread.start()
        if wait:
            thread.join()
        return self.summary()

    def _record_worker(self, steps: int, restart: bool) -> None:
        recording = self.recording
        try:
            with self.host_lock:
                if restart:
                    self._drop_host()
                    (self.store / 'current_run').unlink(missing_ok=True)
                self._start_host()
                _, conn, variant = self._host
                recording['message'] = 'Playing the game and watching for new scenes…'
                conn.send(('explore', steps, variant))
                while True:
                    event = self._receive()
                    if event[0] == 'step':
                        _, done, total, meta, frame = event
                        self.live['frame'] = frame
                        if meta:
                            self._add_scene(self.store / 'scenes' / (meta['id'] + '.scene'))
                            recording['found'] += 1
                        recording['done'] = done
                        if len(self.scenes) - len(self.level_scene_ids()) >= MAX_SCENES or recording.get('stop'):
                            conn.send(('stop',))
                    elif event[0] == 'done':
                        self.live['frame'] = event[1]
                        break
            found = recording['found']
            recording.update(state='finished', message=f'Recorded {found} new scene{"s" if found != 1 else ""}.' if found else
                             'No new scenes this time. Play the game yourself and capture the moments you want.')
        except (RuntimeError, ValueError, OSError) as error:
            recording.update(state='failed', message=str(error))

    def stop_recording(self) -> dict:
        with self.lock:
            if self.recording and self.recording['state'] == 'running':
                self.recording['stop'] = True
                self.recording['message'] = 'Stopping…'
        return self.summary()

    def _live_busy(self) -> dict | None:
        if self.recording and self.recording['state'] == 'running':
            return {'busy': True, 'message': 'ROMancer is recording scenes. Wait for it to finish, or stop it.'}
        return None

    def play(self, frames: int, buttons) -> dict:
        """Advance the live game with these buttons held and return its screen."""
        self._require_core()
        frames = max(1, min(120, int(frames)))
        mask = _mask(buttons)
        busy = self._live_busy()
        if busy:
            return busy
        if not self.host_lock.acquire(timeout=0.05):
            return {'busy': True, 'message': self.live.get('message') or 'The game is starting…', 'progress': self.live.get('progress')}
        try:
            if not (self._host and self._host[0].is_alive()):
                run, resume = self._current_run()
                if resume:      # replaying earlier play can take a while; do it off this request
                    threading.Thread(target=self._start_in_background, name='romancer-live', daemon=True).start()
                    return {'busy': True, 'message': 'Catching up to where you left off…', 'progress': None}
                self._start_host()
            self._host[1].send(('play', frames, mask, None if self.live.get('playtest') else self.level_play_label()))
            _, png, frame, width, height, metas = self._receive()
            self.live['frame'] = frame
            self._level_captured(metas)
            return {'busy': False, 'png_base64': base64.b64encode(png).decode(), 'frame': frame, 'width': width, 'height': height,
                    'level_captures': len(self.level_rec['scene_ids']) if self.level_rec and not self.live.get('playtest') else None,
                    'playtest': self.live.get('playtest')}
        finally:
            self.host_lock.release()

    def play_stop(self) -> dict:
        """End a playtest of the edited build, so the next play is the original game again."""
        with self.host_lock:
            if self.live.get('playtest'):
                self._drop_host()
        return {'playtest': None}

    def _start_playtest(self, rom_path: Path, meta: dict, label: str) -> None:
        """Start the live engine on another ROM at a recorded moment. Call with host_lock held."""
        self._drop_host()
        self._require_core()
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        cfg = dict(self._cfg(), rom=str(rom_path), run='playtest', resume=False,
                   from_run=meta['run'], from_frame=meta['frame'], from_checkpoints=list(meta.get('checkpoints') or []))
        process = context.Process(target=_host_main, args=(child, cfg), daemon=True)
        self.live.update(state='starting', message='Starting your changed game at that spot…', progress=None)
        process.start()
        child.close()
        self._host = (process, parent, 0)
        while True:
            event = self._receive()
            if event[0] == 'progress':
                self.live['progress'] = [event[1], event[2]]
            elif event[0] == 'ready':
                self.live.update(state='ready', message='', frame=event[1], progress=None, playtest=label)
                return

    def _start_in_background(self) -> None:
        with self.host_lock:
            try:
                self._start_host()
            except (RuntimeError, ValueError, OSError):
                pass

    def capture(self, label: str = '') -> dict:
        """Keep the live game's current moment as a scene."""
        self._require_core()
        busy = self._live_busy()
        if busy:
            raise ValueError(busy['message'])
        with self.host_lock:
            if not (self._host and self._host[0].is_alive()):
                raise ValueError('Play the game first, then capture the moment you want.')
            if self.live.get('playtest'):
                raise ValueError('This is a playtest of your changes. Scenes are captured from the original game, so stop the playtest first.')
            if len(self.scenes) - len(self.level_scene_ids()) >= MAX_SCENES:
                raise ValueError(f'This game already has {MAX_SCENES} recorded scenes. Remove some before capturing more.')
            self._host[1].send(('capture', str(label)[:80]))
            _, meta, frame = self._receive()
        self._add_scene(self.store / 'scenes' / (meta['id'] + '.scene'))
        return {'scene_id': meta['id'], **self.summary()}

    def forget_scene(self, scene_id: str) -> dict:
        with self.lock:
            self._scene(scene_id)
            if scene_id in self.level_scene_ids():
                raise ValueError('This scene is part of a level map. Remove the level map to remove its scenes.')
            if any(c['scene_id'] == scene_id for c in self._active()):
                raise ValueError('A pending change was made in this scene. Undo that change first.')
            for suffix in ('.scene', '.png'):
                (self.store / 'scenes' / (scene_id + suffix)).unlink(missing_ok=True)
            for table in (self.scenes, self.meta, self.rgb):
                table.pop(scene_id, None)
            self.impact = pv.ImpactIndex()
            for scene in self.scenes.values():
                self.impact.add(scene)
            self._sources = {k: v for k, v in self._sources.items() if k[0] != scene_id}
            for cache in (self._graphics_cache, self._editable, self._chr_used):
                cache.pop(scene_id, None)
            self._views.clear()
            for change in self.changes:
                change['affected'].pop(scene_id, None)
            self._persist()
        return self.summary()

    # ---- what the UI lists

    def summary(self) -> dict:
        with self.lock:
            scenes = [{'id': sid, 'label': self._label(sid), 'frame': m['frame'], 'origin': m.get('origin', 'explore'),
                       'image': 'scene:' + sid, 'width': m['width'], 'height': m['height']} for sid, m in self.meta.items()]
            levels = self.level_summary()
            recording = dict(self.recording) if self.recording else None
            return {'system': self.system, 'system_label': SYSTEM_LABELS.get(self.system, self.system),
                    'engine': {'installed': bool(self.core), 'reason': self.core_error},
                    'scenes': scenes, 'scene_limit': MAX_SCENES, 'recording': recording, 'live': dict(self.live),
                    'changes': self.change_list(), 'preview': self._change_view(self.preview) if self.preview else None,
                    'private_copy': _private_copy_support(), **levels}

    def _swatch_key(self, swatch: pt.Swatch) -> str:
        return 'color:' + ','.join(str(s['offset'] + self.skip) for s in swatch.sources if s)

    def _swatches(self, scene_id: str) -> list[pt.Swatch]:
        every = pt.swatches(self._scene(scene_id), self.system)
        known = {s.domain for s in every if s.status != 'unknown'}
        if 'palette' in known and self.system in ('gb', 'gbc'):
            # A Game Boy Color game draws from its color palettes; the old shade registers are idle.
            return [s for s in every if s.domain == 'palette']
        if known:
            return [s for s in every if s.domain in known]
        return every

    def _findable(self, swatch: pt.Swatch) -> bool:
        """A locked color the search may still find: computed ones, and ones in use whose origin was not seen
        (set by a cartridge coprocessor, or before recording started)."""
        return bool(self.core) and (swatch.status == 'derived' or (swatch.status == 'unknown' and any(swatch.stored)))

    def _traced_elsewhere(self, swatch: pt.Swatch) -> list:
        """Tracing offsets where another recorded scene loads this entry, holding this same color, straight from the ROM."""
        size = len(swatch.stored)
        first, found = swatch.entry * size, []
        for scene in self.scenes.values():
            domain = scene.snapshot.domains.get(swatch.domain)
            if domain is None or domain.data is None or bytes(domain.data[first:first + size]) != swatch.stored:
                continue
            tags = domain.tags[first:first + size]
            if all(pv.tag_kind(t) in (pv.RT_ROM, pv.RT_IMM) and not t & pv.RT_WEAK for t in tags):
                offsets = [pv.tag_offset(t) for t in tags]
                if offsets not in found:
                    found.append(offsets)
        return found[:4]

    def _uses(self, swatch: pt.Swatch) -> set:
        scenes = set()
        for source in swatch.sources:
            if source:
                scenes.update(self.impact.users(source['offset'], source['offset'] + 1))
        return scenes

    def scene_view(self, scene_id: str) -> dict:
        """The scene's screen, its live palette with each color's status, and what is pending on it."""
        with self.lock:
            scene = self._scene(scene_id)
            meta = self.meta[scene_id]
            active = {c['key']: c for c in self._active()}
            line = {layout[0]: layout[3] for layout in pt.LAYOUTS.get(self.system, [])}
            swatches, pickers = [], {}
            for swatch in self._swatches(scene_id):
                key = self._swatch_key(swatch)
                pickers.setdefault(swatch.format, picker_for(swatch.format))
                uses = self._uses(swatch) if swatch.status != 'unknown' else set()
                reason = '' if swatch.editable else LOCK_REASONS.get(swatch.status, LOCK_REASONS['unknown'])
                change = active.get(key) if swatch.editable else next(
                    (c for c in active.values() if c.get('found') and c.get('swatch') == f'{swatch.domain}:{swatch.entry}'
                     and c['scene_id'] == scene_id and not c.get('planning') and not c.get('error')), None)
                swatches.append({
                    'id': f'{swatch.domain}:{swatch.entry}', 'domain': swatch.domain, 'entry': swatch.entry, 'group': swatch.group,
                    'name': _swatch_name(swatch, line.get(swatch.domain, 16)), 'format': swatch.format, 'colors': swatch.rgb,
                    'editable': swatch.editable, 'status': swatch.status, 'locked_reason': reason,
                    'findable': self._findable(swatch),
                    'elsewhere': [] if swatch.editable else self._elsewhere(scene_id, swatch),
                    'uses': len(uses), 'notes': list(swatch.notes),
                    'pending': change['to_rgb'] if change else None, 'pending_change': change['id'] if change else None,
                    'details': [{'file_offset': s['offset'] + self.skip, 'kind': s['kind'], 'code_address': s['pc']} if s else None
                                for s in swatch.sources]})
            return {'scene': {'id': scene_id, 'label': self._label(scene_id), 'frame': scene.frame, 'origin': meta.get('origin'),
                              'image': 'scene:' + scene_id, 'width': meta['width'], 'height': meta['height']},
                    'swatches': swatches, 'pickers': pickers, 'line': line, 'look': self._look(scene_id),
                    'recorded_scenes': len(self.scenes)}

    def _elsewhere(self, scene_id: str, swatch: pt.Swatch) -> list[dict]:
        """Other recorded scenes in which this same palette slot can be changed (a moment where it is not faded)."""
        out = []
        for sid in self.scenes:
            if sid == scene_id:
                continue
            table = self._editable.get(sid)
            if table is None:
                table = self._editable[sid] = {(s.domain, s.entry): s.rgb for s in pt.swatches(self.scenes[sid], self.system) if s.editable}
            colors = table.get((swatch.domain, swatch.entry))
            if colors:
                out.append({'scene_id': sid, 'label': self._label(sid), 'colors': colors, 'swatch': f'{swatch.domain}:{swatch.entry}'})
                if len(out) == 3:
                    break
        return out

    def image(self, key: str) -> bytes:
        kind, _, name = str(key).partition(':')
        if kind in ('level', 'levelafter'):
            parts = name.split(':')
            if len(parts) != (2 if kind == 'level' else 3) or not all(part.isalnum() for part in parts):
                raise ValueError('unknown picture')
            return self.level_image(parts[0], int(parts[1]), parts[2] if kind == 'levelafter' else '')
        if kind not in ('scene', 'render') or not name.isalnum():
            raise ValueError('unknown picture')
        path = self.store / ('scenes' if kind == 'scene' else 'renders') / (name + '.png')
        if not path.is_file():
            raise ValueError('That picture is no longer stored. Reopen the scene.')
        return path.read_bytes()

    # ---- changes

    def _active(self) -> list[dict]:
        return self.changes + ([self.preview] if self.preview else [])

    def _rom_with(self, changes) -> bytes:
        """The ROM as it would be saved with these changes: their bytes, and the cartridge checksum brought up to date.

        The checksum matters for the pictures: a game that tests it (Sonic the
        Hedgehog stops on a red screen) would otherwise fail in every replay
        from power-on, though the saved build runs.
        """
        key = hashlib.sha1(repr([change['writes'] for change in changes]).encode()).hexdigest()
        cached = self._roms.get(key)
        if cached is None:
            rom = bytearray(self.rom)
            size = max([len(rom)] + [change.get('rom_size') or 0 for change in changes])
            rom += bytes([0xFF]) * (size - len(rom))             # a change that needs more room makes the ROM longer
            for change in changes:
                for offset, _, new in change['writes']:
                    rom[offset] = new
            cached = _with_checksums(bytes(rom), self.rom, self.system)
            if len(self._roms) >= 4:
                self._roms.pop(next(iter(self._roms)))
            self._roms[key] = cached
        return cached

    def _domain_sources(self, scene_id: str, name: str) -> dict:
        cached = self._sources.get((scene_id, name))
        if cached is None:
            cached = self._sources[(scene_id, name)] = self.scenes[scene_id].snapshot.domains[name].sources()
        return cached

    def _expected(self, scene_id: str, offsets) -> dict:
        """Video-memory bytes of a scene that the tags say come from these ROM offsets (tracing offsets)."""
        out = {}
        for name in _video_domains(self.scenes[scene_id].snapshot):
            sources = self._domain_sources(scene_id, name)
            indices = sorted({i for offset in offsets for i in sources.get(offset, ())})
            if indices:
                out[name] = indices
        return out

    def _submit(self, scene_id: str, rom: bytes, offsets, sink, *, hint=None, fixed=False, thorough=False, plan_expect=None) -> str:
        rom_sha = hashlib.sha256(rom).hexdigest()
        cached = self.renders.get((scene_id, rom_sha))
        if cached is not None and (not plan_expect or 'as_planned' in cached):
            sink(scene_id, cached)
            return cached['key']
        path = self.store / 'work' / (rom_sha[:24] + self.suffix)
        if not path.exists():
            path.write_bytes(rom)
        key = hashlib.sha1(f'{scene_id}:{rom_sha}:{int(fixed)}:{hint}:{int(bool(plan_expect))}'.encode()).hexdigest()[:24]
        job = dict(self._cfg(), rom=str(path), base_rom=str(self.rom_path), scene_id=scene_id, key=key, rom_sha=rom_sha,
                   expected=self._expected(scene_id, offsets), hint=hint, fixed=fixed, thorough=thorough, plan_expect=plan_expect)
        self.pending.add(key)
        future = self._ensure_pool().submit(replay_task, job)

        def finished(done):
            try:
                result = done.result()
            except BaseException as error:      # a worker died; say so on the scene
                result = {'scene_id': scene_id, 'key': key, 'rom_sha': rom_sha, 'verified': False, 'pixels': 0,
                          'error': f'{type(error).__name__}: {error}'}
            with self.lock:
                self.pending.discard(key)
                if 'error' not in result:
                    self.renders[(scene_id, rom_sha)] = result
                sink(scene_id, result)
        future.add_done_callback(finished)
        return key

    def _ensure_pool(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(self.workers, mp_context=multiprocessing.get_context('spawn'))
        return self._pool

    def _propose(self, change: dict) -> dict:
        with self.lock:
            self._require_core()
            if change.get('planning'):
                change.update(id=uuid.uuid4().hex, state='preview', recorded_scenes=len(self.scenes), affected={}, created=time.time())
                self.preview = change
                job = dict(self._cfg(), base_rom=str(self.rom_path), **change.pop('plan_job'))
                task = private_copy_task
                if change.pop('plan_task', None) == 'graphics':
                    task = sg.plan_task
                    change['progress'] = job['progress'] = str(self.store / 'work' / f"plan-{change['id']}.json")
                future = self._ensure_pool().submit(task, job)

                def planned(done, change=change):
                    try:
                        result = done.result()
                    except BaseException as error:
                        result = {'error': f'{type(error).__name__}: {error}'}
                    with self.lock:
                        change['planning'] = False
                        if 'error' in result:
                            change['error'] = result['error']
                            return
                        try:
                            self._planned(change, result)
                        except ValueError as error:
                            change['error'] = str(error)
                            return
                        if self.preview is change:
                            self._propose(change)
                future.add_done_callback(planned)
                return self._change_view(change)
            tracing = change.get('expect_offsets') or [offset - self.skip for offset, _, _ in change['writes']]
            users = set(change.get('extra_scenes', ()))
            for offset in tracing:
                users.update(self.impact.users(offset, offset + 1))
            users.add(change['scene_id'])
            order = [change['scene_id']] + [sid for sid in self.scenes if sid in users and sid != change['scene_id']]
            if change.get('every_scene'):          # an added routine runs everywhere, so every recorded scene is re-rendered
                order += [sid for sid in self.scenes if sid not in users]
            change.update(id=change.get('id') or uuid.uuid4().hex, state='preview', recorded_scenes=len(self.scenes),
                          affected={sid: {'state': 'working'} for sid in order}, created=time.time())
            self.preview = change
            rom = self._rom_with([change])

            def sink(scene_id, result, change=change):
                entry = change['affected'].get(scene_id)
                if entry is None:
                    return
                entry.clear()
                entry.update(result, state='failed' if 'error' in result else 'done')
                if change['state'] == 'kept' and all(e['state'] != 'working' for e in change['affected'].values()):
                    self._persist()
            for sid in order:
                self._submit(sid, rom, tracing, sink, thorough=change['kind'] != 'color' or change.get('scope') != 'all',
                             plan_expect=change.get('expect') if sid == change['scene_id'] else None)
            return self._change_view(change)

    def _planned(self, change: dict, result: dict) -> None:
        """Take a finished plan into the change: its bytes, how it was made, and which scenes must be re-rendered."""
        checksum = self._checksum_offsets()
        writes = sorted(([int(o), None if a is None else int(a), int(b)] for o, a, b in result['writes'] if int(o) not in checksum),
                        key=lambda w: w[0])
        if not writes:
            raise ValueError('This change leaves the ROM as it is.')
        change['writes'] = writes
        change['notes'] = result.get('notes', [])
        if (result.get('rom_size') or 0) > len(self.rom):
            change['rom_size'] = int(result['rom_size'])
            if any((c.get('rom_size') or 0) > len(self.rom) for c in self.changes if c['key'] != change['key']
                   and c.get('block') != result.get('block')):
                raise ValueError('This change needs room added at the end of the ROM, and another change in your list already '
                                 'added room there. ROMancer cannot combine the two yet. Undo the other change first.')
        if change.get('plan_kind') == 'color':
            change['key'] = 'color:' + ','.join(str(o) for o in result.get('place') or [o for o, _, _ in writes])
            change['as_planned'] = bool(result.get('as_planned'))
            change['shown_rgb'] = result.get('shown')
            return
        if 'method' not in result:
            return                                   # a private copy of a color, planned by private_copy_task
        change.update(method=result['method'], in_scene=result.get('in_scene'), expect=result.get('expect') or {},
                      block=result.get('block'), decoded=result.get('decoded'), tried=result.get('tried', []))
        if change['method'] == 'import':
            self._planned_import(change, result, writes)
            return
        if change.get('level'):
            self._planned_level(change, result)
        offsets = set(change.get('expect_offsets') or ())
        if result.get('block_range'):
            first, last = result['block_range']
            offsets.update(range(first - self.skip, last - self.skip))
        change['expect_offsets'] = sorted(offsets) or None
        others = [c for c in self.changes if c['key'] != change['key']]
        merged = []
        if change['method'] in ('reencode', 'relocate') and change.get('block') is not None:
            merged = [c for c in others if c.get('block') == change['block'] and c.get('method') in ('reencode', 'relocate')]
        elif change['method'] == 'overlay':
            merged = [c for c in others if c.get('method') == 'overlay']
        if merged:
            mine = {(t['domain'], t['address']) for t in change['tiles']}
            change['tiles'] = [t for c in merged for t in c['tiles'] if (t['domain'], t['address']) not in mine] + change['tiles']
            change['replaces'] = [c['id'] for c in merged]
            change['title'] = f"{len(change['tiles'])} pictures " + ('packed together' if change['method'] != 'overlay' else 'in one patch')
            change['extra_scenes'] = sorted(set(change.get('extra_scenes', ())) | {sid for c in merged for sid in c['affected']})
        if change['method'] == 'overlay':
            change['every_scene'] = True
        mine = {o for o, _, _ in writes}
        clash = next((c for c in others if c not in merged and any(o in mine for o, _, _ in c['writes'])), None)
        if clash is not None:
            raise ValueError(f"This change needs the same place in the ROM as \u201c{clash['title']}\u201d, which is already in your "
                             'change list. Undo that change first, then try this one again.')

    def _planned_import(self, change: dict, result: dict, writes: list) -> None:
        """A PNG's pictures, planned in groups: remember the groups, leave out what was not confirmed, and take over
        kept changes that had to be packed or patched together with them."""
        by_id = {sg.tile_id(t['domain'], t['address'], t['format']): t for t in change['tiles']}
        done = [ident for ident in result.get('done', ()) if ident in by_id]
        info = change.setdefault('import', {})
        names = {}
        try:
            names = {tile['id']: tile['name'] for tile in self.graphics_view(change['scene_id'])['tiles']}
        except ValueError:
            pass
        info['skipped'] = list(info.get('skipped', ())) + [{'tile': entry['tile'], 'name': names.get(entry['tile'], entry['tile']),
                                                             'reason': entry['reason']} for entry in result.get('skipped', ())]
        info['replays'] = result.get('replays', 0)
        info['together'] = result.get('together')
        change['tiles'] = [by_id[ident] for ident in done]
        change['parts'] = [{'method': part['method'], 'block': part.get('block'), 'decoded': part.get('decoded'),
                            'tiles': [by_id[ident] for ident in part['tiles'] if ident in by_id], 'expect': part.get('expect') or {}}
                           for part in result.get('parts', ())]
        info['ways'] = {}
        for part in change['parts']:
            info['ways'][part['method']] = info['ways'].get(part['method'], 0) + len(part['tiles'])
        offsets = set(change.get('expect_offsets') or ())
        for first, last in result.get('block_ranges', ()):
            offsets.update(range(first - self.skip, last - self.skip))
        change['expect_offsets'] = sorted(offsets) or None
        others = [c for c in self.changes if c['key'] != change['key']]
        blocks = {part['block'] for part in change['parts'] if part['method'] in ('reencode', 'relocate') and part['block'] is not None}
        patch = any(part['method'] == 'overlay' for part in change['parts'])
        merged = [c for c in others if (c.get('method') in ('reencode', 'relocate') and c.get('block') in blocks)
                  or (patch and c.get('method') == 'overlay')]
        if merged:
            mine = {(t['domain'], t['address']) for t in change['tiles']}
            taken_over = [t for c in merged for t in c['tiles'] if (t['domain'], t['address']) not in mine]
            change['tiles'] = taken_over + change['tiles']
            change['replaces'] = [c['id'] for c in merged]
            change['extra_scenes'] = sorted(set(change.get('extra_scenes', ())) | {sid for c in merged for sid in c['affected']})
            for part in change['parts']:
                for c in merged:
                    if (part['method'] == 'overlay' and c.get('method') == 'overlay') or \
                            (part['block'] is not None and c.get('block') == part['block']):
                        part['tiles'] = [t for t in c['tiles'] if (t['domain'], t['address']) not in
                                         {(x['domain'], x['address']) for x in part['tiles']}] + part['tiles']
        if patch:
            change['every_scene'] = True
        count = len(change['tiles'])
        change['title'] = f'{count} picture{"s" if count != 1 else ""} from a PNG'
        mine = {o for o, _, _ in writes}
        clash = next((c for c in others if c not in merged and any(o in mine for o, _, _ in c['writes'])), None)
        if clash is not None:
            raise ValueError(f"These pictures need the same place in the ROM as \u201c{clash['title']}\u201d, which is already in your "
                             'change list. Undo that change first, then read the PNG in again.')

    def _checksum_offsets(self) -> set:
        """File offsets of the cartridge checksum; the session brings them up to date itself, so plans leave them out."""
        if self._checksum_bytes is None:
            found = set()
            middle, early = len(self.rom) // 2, min(len(self.rom) - 2, 0x1000 + self.skip)
            for at in (middle, middle + 1, early, early + 1, len(self.rom) - 2, len(self.rom) - 1):   # odd and even: a word sum has two bytes
                probe = bytearray(self.rom)
                probe[at] ^= 0x55
                fixed = _with_checksums(bytes(probe), self.rom, self.system)
                found.update(i for start in range(0, len(fixed), 4096) if fixed[start:start + 4096] != probe[start:start + 4096]
                             for i in range(start, min(start + 4096, len(fixed))) if fixed[i] != probe[i])
            if self.system == 'genesis':
                found.update(range(0x1A4, 0x1A8))        # the header's "end of ROM" field follows the ROM's size
                if found - set(range(0x1A4, 0x1A8)):
                    found.update((0x18E, 0x18F))         # both bytes of the checksum word, whichever the probes moved
            self._checksum_bytes = sg.whole_checksums(found, self.system)
        return self._checksum_bytes

    def _avoid(self, key: str = '') -> list:
        """File ranges a plan must not use as free space: bytes a recorded scene reads, and bytes other kept changes write."""
        if self._read_ranges is None or self._read_ranges[0] != len(self.scenes):
            self._read_ranges = (len(self.scenes), pv.merge_ranges((o + self.skip, o + self.skip + 1) for o in self.impact._by_offset))
        taken = [(o, o + 1) for c in self.changes if c['key'] != key for o, _, _ in c['writes']]
        return [list(r) for r in pv.merge_ranges(list(self._read_ranges[1]) + taken)]

    # ---- pictures and backgrounds

    def _graphics(self, scene_id: str) -> sg.SceneGraphics:
        found = self._graphics_cache.get(scene_id)
        if found is None:
            meta = self.meta[scene_id]
            found = sg.SceneGraphics(self._scene(scene_id), self.system, self.rom, self.rgb[scene_id], meta['width'], meta['height'])
            while len(self._graphics_cache) >= GRAPHICS_KEPT:
                self._graphics_cache.pop(next(iter(self._graphics_cache)))
            self._graphics_cache[scene_id] = found
        return found

    def _chr_tiles(self, scene_id: str) -> set:
        """ROM offsets (tracing) of the pictures a scene shows straight from the ROM (NES CHR-ROM)."""
        found = self._chr_used.get(scene_id)
        if found is None:
            from . import graphics_trace as gt
            found, scene = set(), self.scenes[scene_id]
            table = scene.snapshot.domains.get('chr_map')
            if table is not None and scene.snapshot.domains.get('chr') is None:
                try:
                    for address in gt.used_tile_addresses(scene, self.system):
                        slot, k = address // 16 // 64, address // 16 % 64
                        if 0 <= slot < len(table.tags) and pv.tag_kind(table.tags[slot]) == pv.RT_ROM:
                            found.add(pv.tag_offset(table.tags[slot]) + k * 16)
                except Exception:
                    pass
            self._chr_used[scene_id] = found
        return found

    def _tile_users(self, tile) -> set:
        if tile.domain == 'chr_rom':
            first = tile.sources[0]['offset']
            return {sid for sid in self.scenes if first in self._chr_tiles(sid)}
        users, by_offset = set(), self.impact._by_offset
        for source in tile.sources:
            if source:
                for scene_id, _ in by_offset.get(source['offset'], ()):
                    users.add(scene_id)
        return users

    def graphics_view(self, scene_id: str) -> dict:
        """The scene's pictures (tiles) and background layers, each with its status and what is pending on it."""
        with self.lock:
            graphics = self._graphics(scene_id)
            key = (scene_id, len(self.scenes))
            base = self._views.get(key)
            if base is None:
                base = graphics.view(lambda tile: len(self._tile_users(tile)), {}, {})
                if len(self._views) >= VIEWS_KEPT:
                    self._views.pop(next(iter(self._views)))
                self._views[key] = base
            pending, cells = {}, {}
            for change in self._active():
                if change.get('planning') or change.get('error'):
                    continue
                for record in change.get('tiles', ()):
                    pending[sg.tile_id(record['domain'], record['address'], record['format'])] = (record, change['id'])
                if change['kind'] == 'background':
                    for cell in change.get('cells', ()):
                        if cell.get('scene_id', change['scene_id']) == scene_id:
                            cells.setdefault(int(cell['layer']), []).append({**cell, 'change': change['id']})
            tiles = []
            for tile in base['tiles']:
                hit = pending.get(tile['id'])
                if hit and hit[0]['from'] == tile['pixels']:
                    tile = {**tile, 'pending': {'pixels': hit[0]['pixels'], 'change': hit[1]}}
                tiles.append(tile)
            layers = [{**layer, 'pending': cells.get(layer['index'], [])} for layer in base['layers']]
            return {**base, 'tiles': tiles, 'layers': layers, 'scene_id': scene_id, 'private_copy': _private_copy_support()}

    def tile_at(self, scene_id: str, x: int, y: int) -> dict:
        """The pictures the recorded screen shows at one pixel: a sprite and/or background cells, topmost first."""
        with self.lock:
            hits = self._graphics(scene_id).lookup(int(x), int(y))
            return {'x': int(x), 'y': int(y), 'hits': hits,
                    'message': '' if hits else 'ROMancer could not tell which picture is under that pixel. '
                                               'Choose it from the list of pictures in this scene instead.'}

    def propose_tile(self, scene_id: str, tile: str, pixels, scope: str = 'all') -> dict:
        """Plan new pixels for one 8x8 picture. The way is chosen for it: in place, re-packed, or a swap-in patch.

        The plan is made and replay-checked in a worker; then every scene that loads the picture is re-rendered.
        """
        with self.lock:
            self._require_core()
            graphics = self._graphics(scene_id)
            domain, address, fmt = sg.parse_tile_id(tile)
            item = graphics.tile(domain, address, fmt)
            pixels = sg.parse_pixels(pixels, fmt)
            how, can, reason = sg.tile_reason(item, self.system)
            if not can:
                raise ValueError(reason)
            if pixels == list(item.pixels):
                raise ValueError('That is the picture it already has. Draw something different first.')
            if any('8 colors' in note for note in item.notes) and any(p > 7 for p in pixels):
                raise ValueError('The ROM stores this picture with 8 colors, so only the first 8 colors of its palette can be used in it.')
            only = scope != 'all'
            if only:
                support = _private_copy_support()
                if not support['available']:
                    raise ValueError(support['reason'])
                if domain == 'chr_rom':
                    raise ValueError("On this cartridge the game's picture chip reads pictures straight from the ROM, so one "
                                     'scene cannot be given its own copy. Change it everywhere instead.')
            record = {'domain': domain, 'address': address, 'format': fmt, 'stored': item.stored.hex(),
                      'from': sg.pixel_text(item.pixels, fmt), 'pixels': sg.pixel_text(pixels, fmt)}
            first = next((s['offset'] for s in item.sources if s), None)
            key = (f'tile:{first}' if how == 'direct' and first is not None else 'tile:' + tile + ':' + item.stored.hex()[:16])
            key += ('@' + scene_id) if only else ''
            holders = []
            if domain != 'chr_rom' and not only:      # scenes that hold this exact picture in this slot, however they loaded it
                for sid, scene in self.scenes.items():
                    memory = scene.snapshot.domains.get(domain)
                    if memory is not None and memory.data is not None and item.addresses[-1] < len(memory.data) \
                            and bytes(memory.data[a] for a in item.addresses) == item.stored:
                        holders.append(sid)
            earlier = next((c for c in self.changes if c['key'] == 'import:' + scene_id), None)
            if earlier is not None and not only:
                # This scene already has pictures read in from a PNG: the new picture joins them, so they stay one change.
                wanted = {sg.tile_id(t['domain'], t['address'], t['format']): sg.parse_pixels(t['pixels'], t['format'])
                          for t in earlier['tiles']}
                wanted[tile] = pixels
                return self._propose_tiles(scene_id, wanted, dict(earlier.get('import') or {}, summary='', colors=[], skipped=[]))
            companions = self._companions(key, scene_id)
            change = {'kind': 'graphics', 'key': key, 'scene_id': scene_id, 'title': f'Picture {item.index}',
                      'swatch': None, 'from_rgb': None, 'to_rgb': None, 'writes': [], 'scope': 'only_this' if only else 'all',
                      'tiles': [record], 'planning': True, 'plan_task': 'graphics',
                      'expect_offsets': [s['offset'] for s in item.sources if s] if domain != 'chr_rom' else None,
                      'extra_scenes': sorted((self._tile_users(item) if not only else set()) | set(holders)),
                      'plan_job': {'what': 'tile', 'scene_id': scene_id, 'domain': domain, 'address': address, 'format': fmt,
                                   'pixels': record['pixels'], 'scope': 'only_this' if only else 'all',
                                   'avoid': self._avoid(key), 'companions': companions}}
            return self._propose(change)

    def _companions(self, key: str, scene_id: str) -> list:
        """Kept changes a new plan may have to be packed or patched together with."""
        out = []
        for c in self.changes:
            if c['key'] == key:
                continue
            here = c['scene_id'] == scene_id
            if c.get('method') in ('reencode', 'relocate', 'overlay'):
                out.append({'block': c.get('block'), 'decoded': c.get('decoded'), 'method': c.get('method'),
                            'tiles': c.get('tiles', []), 'expect': c.get('expect') if here else None})
            elif c.get('method') == 'import':
                for part in c.get('parts', ()):
                    if part['method'] in ('reencode', 'relocate', 'overlay'):
                        out.append({'block': part.get('block'), 'decoded': part.get('decoded'), 'method': part['method'],
                                    'tiles': part.get('tiles', []), 'expect': part.get('expect') if here else None})
        return out

    def export_picture(self, scene_id: str, what: str, layer: int = 0) -> dict:
        """A PNG of the scene's pictures ('sheet') or of one background layer ('layer'), with the changes you kept."""
        with self.lock:
            graphics = self._graphics(scene_id)
            view = self.graphics_view(scene_id)
            if what == 'sheet':
                out = sp.export_sheet(graphics, view)
                name = 'pictures'
            elif what == 'layer':
                out = sp.export_layer(graphics, view, int(layer))
                name = 'background-' + ''.join(ch if ch.isalnum() else '-' for ch in out['layer']).strip('-').lower()
            elif what == 'sprites':
                out = sp.export_sprites(graphics, view)
                name = 'sprites'
            else:
                raise ValueError('Choose the pictures, the sprites or a background layer to save.')
            number = list(self.scenes).index(scene_id) + 1
            return {**out, 'what': what, 'name': f'scene-{number}-{name}.png'}

    def export_everything(self) -> dict:
        """One ZIP with the graphics of every recorded scene and every level map, each as PNG.

        For each scene: its pictures as one sheet, and every background layer
        laid out the way the game shows it (the files Save pictures as PNG and
        Save background as PNG give, so any of them can be drawn on and loaded
        back in its scene). For each level map: the whole map. A text file
        lists what is in the ZIP.
        """
        import io
        import zipfile
        with self.lock:
            out = io.BytesIO()
            listing, scenes, files = [], 0, 0
            level_scenes = self.level_scene_ids()
            with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
                for scene_id in list(self.scenes):
                    if scene_id in level_scenes:
                        continue                              # a level's captures are in its map
                    try:
                        sheet = self.export_picture(scene_id, 'sheet')
                    except ValueError:
                        continue
                    scenes += 1
                    folder = sheet['name'].rsplit('-pictures.png', 1)[0]
                    archive.writestr(f'{folder}/{sheet["name"]}', sheet['png'])
                    files += 1
                    listing.append(f'{folder}: {self._label(scene_id)}')
                    listing.append(f'  {sheet["name"]}  {sheet["width"]} by {sheet["height"]} pixels, {sheet["pictures"]} pictures')
                    try:
                        whole = self.export_picture(scene_id, 'sprites')
                        archive.writestr(f'{folder}/{whole["name"]}', whole['png'])
                        files += 1
                        listing.append(f'  {whole["name"]}  {whole["width"]} by {whole["height"]} pixels, {whole["objects"]} objects made of sprites')
                    except ValueError:
                        pass                                  # no sprites on that screen
                    for layer in self.graphics_view(scene_id)['layers']:
                        try:
                            picture = self.export_picture(scene_id, 'layer', layer['index'])
                        except ValueError:
                            continue                          # a layer with no flat picture (Mode 7)
                        archive.writestr(f'{folder}/{picture["name"]}', picture['png'])
                        files += 1
                        listing.append(f'  {picture["name"]}  {picture["width"]} by {picture["height"]} pixels, background layer {layer["name"]}')
                for level in self.levels:
                    for number, plane in enumerate(level['planes']):
                        picture = self.export_level(level['id'], number)
                        tail = 'all-layers' if number == 0 else ''.join(ch if ch.isalnum() else '-' for ch in plane['name']).strip('-').lower()
                        name = f'level-maps/{picture["name"].rsplit(".png", 1)[0]}-{tail}.png'
                        archive.writestr(name, picture['png'])
                        files += 1
                        listing.append(f'{name}  {picture["width"]} by {picture["height"]} pixels, level map {level["name"]}')
                if not files:
                    raise ValueError('There is nothing to save yet. Record a scene first.')
                archive.writestr('CONTENTS.txt', '\r\n'.join(
                    ['Graphics saved by ROMancer from the recorded scenes of one game.',
                     'A scene folder holds the pictures of that scene as one sheet and each background layer.',
                     'To change the game, draw on one of these PNGs, keep its size, and load it back in that scene',
                     'with Load pictures PNG or Load background PNG. Level maps are for looking at.', ''] + listing) + '\r\n')
            return {'zip': out.getvalue(), 'name': 'romancer-graphics.zip', 'scenes': scenes, 'levels': len(self.levels), 'files': files}

    def import_picture(self, scene_id: str, what: str, layer: int, raw: bytes) -> dict:
        """Read a PNG saved by export_picture back in and plan every picture that differs as one change.

        Returns {'summary', 'colors', 'skipped', 'pictures', 'change'}; 'change' is None when nothing is to be changed.
        """
        with self.lock:
            self._require_core()
            graphics = self._graphics(scene_id)
            view = self.graphics_view(scene_id)
            moves = []
            if what == 'sheet':
                wanted, report = sp.read_sheet(graphics, view, raw)
            elif what == 'layer':
                wanted, report, moves = sp.read_layer(graphics, view, int(layer), raw)
            elif what == 'sprites':
                wanted, report = sp.read_sprites(graphics, view, raw)
            else:
                raise ValueError('Choose the pictures, the sprites or a background layer to read in.')
            refused = []
            if moves:                # a picture the layer cannot show in that cell is not a move: it is left out, with the reason
                layers = graphics.layers()
                able = []
                for move in moves:
                    current = layers[move['layer']].layer.cell(move['x'], move['y'])
                    try:
                        sg.hardware_tile(layers[move['layer']], current, *sg.parse_tile_id(move['tile']))
                        if current.status == 'unknown':
                            raise ValueError(sg.CELL_REASONS['unknown'])
                        able.append(move)
                    except ValueError as error:
                        refused.append({'tile': move['tile'], 'name': f"Cell {move['x'] + 1}, {move['y'] + 1}", 'reason': str(error)})
                moves = able
            if refused and not moves and not wanted:
                return {'what': what, 'summary': 'PNG read. ' + refused[0]['reason'], 'colors': [], 'off_colors': 0,
                        'by_number': bool(report.by_number), 'skipped': refused, 'pictures': 0, 'change': None}
            if moves:
                # Cells that were given another picture of the scene: a background change, checked by replay like one
                # painted in the Background editor. Pictures that were also drawn on are read in after this is kept.
                if len(moves) > 2048:
                    raise ValueError(f'This PNG gives {len(moves):,} cells another picture. ROMancer checks up to 2,048 at a '
                                     'time. Rearrange a smaller part, keep it, then load the rest.')
                count = len(moves)
                text = (f'PNG read: {count:,} cell{"s" if count != 1 else ""} of the background now show{"" if count != 1 else "s"} '
                        'another picture that this scene already has, so the background is changed and no picture is redrawn.')
                if report.recolored:
                    text += (f' {report.recolored:,} of them keep{"s" if report.recolored == 1 else ""} the colors of the place '
                             'they were put: on the NES one palette choice covers a block of 2 by 2 cells.')
                if wanted:
                    text += (f' {len(wanted):,} picture{"s were" if len(wanted) != 1 else " was"} also drawn on: keep this change, '
                             'then load the same PNG again to change ' + ('them.' if len(wanted) != 1 else 'it.'))
                info = {'what': what, 'summary': text, 'colors': [], 'off_colors': 0, 'by_number': bool(report.by_number),
                        'skipped': refused, 'moved': count, 'redrawn': len(wanted)}
                change = self.propose_cells(scene_id, moves)
                if self.preview is not None and self.preview['id'] == change['id']:
                    self.preview['title'] = f'{count:,} background cell{"s" if count != 1 else ""} from a PNG'
                    change = self._change_view(self.preview)
                return {**info, 'pictures': 0, 'change': change}
            key = 'import:' + scene_id
            earlier = next((c for c in self.changes if c['key'] == key), None)
            if earlier is not None:                  # pictures of the earlier PNG that this one does not show stay as they are
                for t in earlier['tiles']:
                    ident = sg.tile_id(t['domain'], t['address'], t['format'])
                    if ident not in report.covered:
                        wanted.setdefault(ident, sg.parse_pixels(t['pixels'], t['format']))
            names = {tile['id']: tile['name'] for tile in view['tiles']}
            skipped = []
            for change in self.changes:
                if change['key'] == key:
                    continue
                for t in change.get('tiles', ()):
                    ident = sg.tile_id(t['domain'], t['address'], t['format'])
                    if ident not in wanted:
                        continue
                    if sg.pixel_text(wanted[ident], t['format']) != t['pixels']:
                        skipped.append({'tile': ident, 'name': names.get(ident, ident),
                                        'reason': f"\u201c{change['title']}\u201d in your change list already changes this picture. "
                                                  'Undo that change to read in a different version.'})
                    del wanted[ident]
            for ident in list(wanted):
                domain, address, fmt = sg.parse_tile_id(ident)
                item = graphics.tile(domain, address, fmt)
                how, can, reason = sg.tile_reason(item, self.system)
                if can and any('8 colors' in note for note in item.notes) and any(p > 7 for p in wanted[ident]):
                    can, reason = False, ('The ROM stores this picture with 8 colors, so only the first 8 colors of its palette '
                                          'can be used in it.')
                if not can:
                    skipped.append({'tile': ident, 'name': names.get(ident, ident), 'reason': reason})
                    del wanted[ident]
            info = {'what': what, 'summary': sp.summary(report, len(wanted), skipped), 'colors': report.rows(),
                    'off_colors': len(report.off), 'by_number': bool(report.by_number), 'skipped': skipped}
            if earlier is not None and {sg.tile_id(t['domain'], t['address'], t['format']): t['pixels'] for t in earlier['tiles']} == \
                    {ident: sg.pixel_text(pixels, sg.parse_tile_id(ident)[2]) for ident, pixels in wanted.items()}:
                wanted = {}
                info['summary'] = 'PNG read. It is the same as the pictures you already read in, so there is nothing new to change.'
            if not wanted:
                return {**info, 'pictures': 0, 'change': None}
            if len(wanted) > sg.MAX_IMPORT_TILES:
                raise ValueError(f'This PNG changes {len(wanted):,} pictures. ROMancer checks up to {sg.MAX_IMPORT_TILES:,} at a time. '
                                 'Change fewer pictures, keep them, then read in the rest.')
            change = self._propose_tiles(scene_id, wanted, info)
            return {**info, 'pictures': len(wanted), 'change': change}

    def _propose_tiles(self, scene_id: str, wanted: dict, info: dict) -> dict:
        """Plan new pixels for many pictures as one change ({tile id: pixels})."""
        graphics = self._graphics(scene_id)
        key = 'import:' + scene_id
        records, offsets, users = [], set(), set()
        for ident, pixels in wanted.items():
            domain, address, fmt = sg.parse_tile_id(ident)
            item = graphics.tile(domain, address, fmt)
            records.append({'domain': domain, 'address': address, 'format': fmt, 'stored': item.stored.hex(),
                            'from': sg.pixel_text(item.pixels, fmt), 'pixels': sg.pixel_text(pixels, fmt)})
            if domain != 'chr_rom':
                offsets.update(s['offset'] for s in item.sources if s)
                for sid, scene in self.scenes.items():
                    memory = scene.snapshot.domains.get(domain)
                    if memory is not None and memory.data is not None and item.addresses[-1] < len(memory.data) \
                            and bytes(memory.data[a] for a in item.addresses) == item.stored:
                        users.add(sid)
            users.update(self._tile_users(item))
        count = len(records)
        change = {'kind': 'graphics', 'key': key, 'scene_id': scene_id,
                  'title': f'{count} picture{"s" if count != 1 else ""} from a PNG',
                  'swatch': None, 'from_rgb': None, 'to_rgb': None, 'writes': [], 'scope': 'all',
                  'tiles': records, 'planning': True, 'plan_task': 'graphics', 'import': info,
                  'expect_offsets': sorted(offsets) or None, 'extra_scenes': sorted(users),
                  'plan_job': {'what': 'tiles', 'scene_id': scene_id, 'tiles': records, 'avoid': self._avoid(key),
                               'companions': self._companions(key, scene_id)}}
        return self._propose(change)

    def propose_cells(self, scene_id: str, cells) -> dict:
        """Plan a change to background cells (which picture, flips, palette line), painted as one change."""
        with self.lock:
            self._require_core()
            graphics = self._graphics(scene_id)
            layers = graphics.layers()
            clean, seen = [], set()
            for cell in cells:
                layer, x, y = int(cell['layer']), int(cell['x']), int(cell['y'])
                if not 0 <= layer < len(layers) or not (0 <= x < layers[layer].layer.width and 0 <= y < layers[layer].layer.height):
                    raise ValueError('A painted cell is outside the background.')
                if (layer, x, y) in seen:
                    continue
                seen.add((layer, x, y))
                current = layers[layer].layer.cell(x, y)
                if current.status == 'unknown':
                    raise ValueError(sg.CELL_REASONS['unknown'])
                item = {'layer': layer, 'x': x, 'y': y}
                if cell.get('tile') is not None:
                    item['tile'] = str(cell['tile'])
                    sg.hardware_tile(layers[layer], current, *sg.parse_tile_id(item['tile']))      # refuses plainly when it cannot be shown there
                for name in ('hflip', 'vflip'):
                    if cell.get(name) is not None:
                        item[name] = bool(cell[name])
                if cell.get('line') is not None:
                    item['line'] = int(cell['line'])
                item['from'] = {'tile': sg.tile_id(layers[layer].layer.tile_domain, current.tile_address, layers[layer].layer.tile_format),
                                'hflip': current.hflip, 'vflip': current.vflip, 'line': current.palette}
                clean.append(item)
            if not clean:
                raise ValueError('Paint at least one background cell first.')
            if len(clean) > 2048:
                raise ValueError('That is too many cells for one change. Paint a smaller area.')
            key = 'cells:' + scene_id + ':' + hashlib.sha1(repr(sorted((c['layer'], c['x'], c['y']) for c in clean)).encode()).hexdigest()[:16]
            count = len(clean)
            offsets = sorted({s['offset'] for c in clean for s in layers[c['layer']].layer.cell(c['x'], c['y']).sources if s})
            change = {'kind': 'background', 'key': key, 'scene_id': scene_id,
                      'title': f'{count} background cell{"s" if count != 1 else ""}',
                      'swatch': None, 'from_rgb': None, 'to_rgb': None, 'writes': [], 'scope': 'all', 'cells': clean,
                      'planning': True, 'plan_task': 'graphics', 'expect_offsets': offsets or None,
                      'plan_job': {'what': 'cells', 'scene_id': scene_id, 'cells': clean, 'avoid': self._avoid(key)}}
            return self._propose(change)

    def find_color(self, scene_id: str, domain: str, entry: int, colors) -> dict:
        """For a color the game computes: search for the stored color behind it, and if a replay confirms it, change that."""
        with self.lock:
            self._require_core()
            swatch = next((s for s in self._swatches(scene_id) if s.domain == domain and s.entry == entry), None)
            if swatch is None:
                raise ValueError('That color is not part of this scene.')
            if not self._findable(swatch):
                raise ValueError(LOCK_REASONS['unknown'] if not swatch.editable else 'This color can be changed directly.')
            colors = [[max(0, min(255, int(v))) for v in rgb] for rgb in colors]
            if len(colors) != len(swatch.rgb) or any(len(rgb) != 3 for rgb in colors):
                raise ValueError('Choose a color for every slot.')
            wanted = pt.encode_swatch(swatch, colors if swatch.format == 'dmg-shades' else colors[0])
            if wanted == swatch.stored:
                raise ValueError('That is the color it already has. Choose a different color.')
            line = {layout[0]: layout[3] for layout in pt.LAYOUTS.get(self.system, [])}.get(domain, 16)
            change = {'kind': 'color', 'key': f'find:{domain}:{entry}@{scene_id}', 'scene_id': scene_id, 'title': _swatch_name(swatch, line),
                      'swatch': f'{domain}:{entry}', 'from_rgb': swatch.rgb, 'to_rgb': _decode_stored(swatch.format, wanted),
                      'writes': [], 'scope': 'all', 'found': True, 'planning': True, 'plan_task': 'graphics', 'plan_kind': 'color',
                      'plan_job': {'what': 'color', 'scene_id': scene_id, 'domain': domain, 'entry': int(entry), 'colors': colors,
                                   'hints': self._traced_elsewhere(swatch)}}
            return self._propose(change)

    def propose_color(self, scene_id: str, domain: str, entry: int, colors, scope: str = 'all') -> dict:
        """Plan a new color for one palette entry and start re-rendering every scene that uses it.

        `colors` is a list of RGB triples: one color, or four shades for a Game Boy shade register.
        """
        with self.lock:
            swatch = next((s for s in self._swatches(scene_id) if s.domain == domain and s.entry == entry), None)
            if swatch is None:
                raise ValueError('That color is not part of this scene.')
            if not swatch.editable:
                raise ValueError(LOCK_REASONS.get(swatch.status, LOCK_REASONS['unknown']))
            colors = [[max(0, min(255, int(v))) for v in rgb] for rgb in colors]
            if len(colors) != len(swatch.rgb) or any(len(rgb) != 3 for rgb in colors):
                raise ValueError('Choose a color for every slot.')
            body = self.rom[self.skip:]
            try:
                writes = pt.plan_color_edit(swatch, colors if swatch.format == 'dmg-shades' else colors[0], body)
            except ValueError:
                raise ValueError('The game no longer stores this color where it was traced. Record this scene again.') from None
            if not writes:
                raise ValueError('That is the color it already has. Choose a different color.')
            new = bytearray(swatch.stored)
            for k, source in enumerate(swatch.sources):
                for offset, _, value in writes:
                    if source['offset'] == offset:
                        new[k] = value
            line = {layout[0]: layout[3] for layout in pt.LAYOUTS.get(self.system, [])}.get(domain, 16)
            change = {'kind': 'color', 'key': self._swatch_key(swatch), 'scene_id': scene_id,
                      'title': _swatch_name(swatch, line), 'swatch': f'{domain}:{entry}',
                      'from_rgb': swatch.rgb, 'to_rgb': _decode_stored(swatch.format, bytes(new)),
                      'writes': [[offset + self.skip, old, value] for offset, old, value in writes], 'scope': 'all'}
            if scope != 'all':
                support = _private_copy_support()
                if not support['available']:
                    raise ValueError(support['reason'])
                size = len(swatch.stored)
                change.update(scope='only_this', key=change['key'] + '@' + scene_id, planning=True,
                              expect_offsets=[s['offset'] for s in swatch.sources],
                              plan_job={'scene_id': scene_id, 'domain': domain, 'status': swatch.status,
                                        'addresses': list(range(entry * size, (entry + 1) * size)),
                                        'stored': list(swatch.stored), 'new_stored': list(new)})
            return self._propose(change)

    def propose_writes(self, scene_id: str, writes, title: str, kind: str = 'graphics') -> dict:
        """The same pipeline for any edit: `writes` is [(file offset, old byte, new byte)].

        Graphics, tile and tilemap changes planned by graphics_trace arrive here.
        """
        with self.lock:
            self._scene(scene_id)
            clean = []
            for offset, old, new in writes:
                offset, old, new = int(offset), int(old), int(new)
                if not 0 <= offset < len(self.rom) or not 0 <= new <= 255:
                    raise ValueError('A change reaches outside the ROM.')
                if self.rom[offset] != old:
                    raise ValueError('The ROM does not hold the bytes this change expects. Record the scene again.')
                if old != new:
                    clean.append([offset, old, new])
            if not clean:
                raise ValueError('This change leaves the ROM as it is.')
            if len(clean) > 65536:
                raise ValueError('This change is too large for one edit.')
            key = kind + ':' + hashlib.sha1(repr(sorted(o for o, _, _ in clean)).encode()).hexdigest()[:16]
            return self._propose({'kind': kind, 'key': key, 'scene_id': scene_id, 'title': str(title)[:120] or 'Graphics change',
                                  'swatch': None, 'from_rgb': None, 'to_rgb': None, 'writes': sorted(clean), 'scope': 'all'})

    def _find(self, change_id: str) -> dict:
        for change in self._active():
            if change['id'] == change_id:
                return change
        raise ValueError('That change is no longer pending.')

    def change(self, change_id: str) -> dict:
        with self.lock:
            return self._change_view(self._find(change_id))

    def keep(self, change_id: str) -> dict:
        """Move the previewed change into the change list (replacing an earlier change to the same thing)."""
        with self.lock:
            change = self._find(change_id)
            if change.get('planning') or change.get('error'):
                raise ValueError('This change is not ready to keep.')
            if change is self.preview:
                gone = set(change.get('replaces', ()))
                self.changes = [c for c in self.changes if c['key'] != change['key'] and c['id'] not in gone] + [change]
                change['state'] = 'kept'
                self.preview = None
                self.revision += 1
                self.review_state = None
                self._persist()
            return self.summary()

    def remove(self, change_id: str) -> dict:
        """Undo one change: drop it from the preview or the change list."""
        with self.lock:
            change = self._find(change_id)
            if change is self.preview:
                self.preview = None
            else:
                self.changes.remove(change)
                self.revision += 1
                self.review_state = None
                self._persist()
            return self.summary()

    def _change_view(self, change: dict, full: bool = True) -> dict:
        affected = []
        for sid, result in change['affected'].items():
            if sid not in self.scenes:
                continue
            visible = result.get('pixels', 0) > 0
            if result['state'] == 'working':
                status = 'Redrawing…'
            elif result['state'] == 'failed':
                status = 'Could not be replayed'
            elif not result.get('verified'):
                status = 'Uses this data, but the replay showed no change here'
            elif visible:
                status = 'Looks different'
            else:
                status = 'Changed in memory, nothing visible in this moment'
            affected.append({'scene_id': sid, 'label': self._label(sid), 'state': result['state'], 'status': status,
                             'verified': bool(result.get('verified')), 'confidence': result.get('confidence', 'none'),
                             'visible': visible, 'pixels': result.get('pixels', 0), 'edited_here': sid == change['scene_id'],
                             'before': 'scene:' + sid, 'after': 'render:' + result['key'] if result.get('key') and result['state'] == 'done' else None,
                             'note': result.get('note') or result.get('error') or '', 'replayed_from_frame': result.get('from_frame'),
                             'width': self.meta[sid]['width'], 'height': self.meta[sid]['height']})
        affected.sort(key=lambda a: (not a['edited_here'], -a['pixels']))
        planning, failed = bool(change.get('planning')), change.get('error', '')
        if failed and change.get('scope') == 'only_this':
            failed += ' You can still change it everywhere it is used.'
        working = sum(1 for a in affected if a['state'] == 'working') + planning
        done = [a for a in affected if a['state'] == 'done']
        verified = bool(done) and any(a['verified'] for a in done) and not working
        own = next((a for a in affected if a['edited_here']), None)
        picture = change['kind'] in ('graphics', 'background') and 'method' in change
        checks, method, progress = [], change.get('method'), None
        if planning and change.get('progress'):
            progress = sg.read_progress(change['progress'])
        if picture and not failed:
            checks, verified = self._checks(change, working)
        if change.get('object_check') and not failed:
            # an enemy or candle change is checked by watching the game's own spawn slots, not by redrawing scenes
            check = change['object_check']
            checks = [{'name': 'In the game', 'state': check['state'], 'text': check['text']}]
            verified = check['state'] == 'good'
            working = working or (1 if check['state'] == 'working' else 0)
        total = len(self.scenes)
        count = len(affected)
        visible = sum(1 for a in affected if a['visible'])
        return {'id': change['id'], 'kind': change['kind'], 'title': change['title'], 'state': change['state'],
                'scene_id': change['scene_id'], 'swatch': change.get('swatch'), 'from_rgb': change.get('from_rgb'),
                'to_rgb': change.get('to_rgb'), 'scope': change.get('scope', 'all'), 'bytes': len(change['writes']),
                'affected': affected if full else [], 'working': working, 'scene_count': count, 'visible_count': visible,
                'verified': verified, 'verified_here': bool(own and own['verified']),
                'badge': f'Used in {count} scene{"s" if count != 1 else ""}',
                'coverage': f'Seen in {count} of {total} recorded scene{"s" if total != 1 else ""}'
                            + ('' if working else f'; {visible} look{"s" if visible == 1 else ""} different') +
                            ". Scenes you haven't recorded can't be shown.",
                'planning': planning, 'error': failed, 'notes': change.get('notes', []),
                'verdict': ((progress or {}).get('text') or ('Finding where this scene loads its data from, so only this scene changes…'
                                                               if change.get('scope') == 'only_this' else
                                                               'Looking for where the game keeps this color…' if change.get('found') else
                                                               'Working out how to make this change…') if planning else
                            failed if failed else
                            self._summary(checks) if checks else
                            'Redrawing every scene that uses this…' if working else
                            'This change works. The game was replayed and the color changed.' if verified else
                            "This change didn't show up when the game was replayed, so it may not do what you expect."),
                'summary': self._summary(checks) if checks else '',
                'checks': checks, 'method': method, 'method_text': sg.METHODS.get(method, '') if picture else '',
                'progress': progress, 'found': bool(change.get('found')), 'shown_rgb': change.get('shown_rgb'),
                'tiles': [{'id': sg.tile_id(t['domain'], t['address'], t['format']), 'from': t['from'], 'to': t['pixels']}
                          for t in change.get('tiles', ())] if full else [],
                'cells': change.get('cells', []) if full else [], 'cell_count': len(change.get('cells', ())),
                'every_scene': bool(change.get('every_scene')), 'tried': change.get('tried', []) if full else [],
                'grows': max(0, (change.get('rom_size') or 0) - len(self.rom)),
                'import': change.get('import') if full else None, 'level': change.get('level'),
                'details': [{'file_offset': o, 'before': a, 'after': b} for o, a, b in change['writes'][:64]] if full else []}

    def _checks(self, change: dict, working: int) -> tuple[list, bool]:
        """The two separate facts about a picture or background change: what the replay of this scene showed, and what a
        replay of the whole game from power-on showed. Neither stands in for the other."""
        here = change.get('in_scene') or {}
        by_screen = here.get('by') == 'screen'
        planned = bool(here.get('as_planned') or (by_screen and here.get('verified')))
        what = 'background' if change['kind'] == 'background' else 'picture'
        extra = sum(here.get('unplanned', {}).values())
        text = ('The game was replayed to this moment and the screen changed.' if planned and by_screen else
                'The game was replayed to this moment and the change came out exactly as you drew it.' if planned else
                "When the game was replayed to this moment, the change didn't come out as you drew it.")
        if planned and extra:
            text += f' It also changed {extra} other byte{"s" if extra != 1 else ""} of video memory here.'
        checks = [{'name': 'In this scene', 'state': 'good' if planned and not extra else 'warn' if planned else 'bad', 'text': text}]
        own = change['affected'].get(change['scene_id'], {})
        if own.get('state') == 'working' or not own:
            power = {'state': 'working', 'text': 'Playing the whole game from the start to see what else changes…'}
        elif own.get('state') == 'failed':
            power = {'state': 'bad', 'text': "The game couldn't be played from the start to check this. " + str(own.get('error', ''))}
        elif by_screen or 'as_planned' not in own:
            power = ({'state': 'good', 'text': 'Played from the start, the change shows here too.'} if own.get('verified') and own.get('pixels') else
                     {'state': 'bad', 'text': "Played from the start, the change doesn't show here."})
        else:
            others = sum(own.get('unplanned', {}).values())
            late = own.get('late')
            if own.get('as_planned') and not others:
                power = {'state': 'good', 'text': 'Played from the start, only what you changed is different.'
                         + (f' The game gets to this moment {late} frame{"s" if late != 1 else ""} later.' if late else '')}
            elif own.get('as_planned'):
                power = {'state': 'warn', 'text': f'Played from the start, your change is there, but {others} other '
                         f'byte{"s" if others != 1 else ""} of video memory changed as well. Look at the pictures below before you keep it.'}
            else:
                power = {'state': 'bad', 'text': "Played from the start, the change doesn't come out as you drew it. It only works "
                         'when the game is started from just before this moment.'}
        checks.append({'name': 'From the start', **power})
        other_scenes = [r for sid, r in change['affected'].items() if sid != change['scene_id'] and sid in self.scenes]
        if other_scenes and not working:
            seen = sum(1 for r in other_scenes if r.get('pixels'))
            checks.append({'name': 'Other scenes', 'state': 'warn' if seen else 'good',
                           'text': (f'{seen} other recorded scene{"s" if seen != 1 else ""} look{"s" if seen == 1 else ""} different. '
                                    f'{"It is" if seen == 1 else "They are"} shown below.') if seen else
                                   (f'The other recorded scene looks the same.' if len(other_scenes) == 1 else
                                    f'The other {len(other_scenes)} recorded scenes look the same.')})
        return checks, planned and power['state'] in ('good', 'warn') and not working

    @staticmethod
    def _summary(checks: list) -> str:
        """One plain line for the result of a check; the separate checks go under Details."""
        states = {check['name']: check['state'] for check in checks}
        here, start = states.get('In this scene'), states.get('From the start')
        game = states.get('In the game')
        if game == 'working':
            return 'Checking the change in the game…'
        if game == 'good':
            return 'This change works. The game was played from the start to check it.'
        if game in ('bad', 'warn'):
            return "This change couldn't be confirmed in the game. Look at the details before you keep it."
        if here == 'bad':
            return "This change didn't show up when the game was replayed."
        if start == 'working':
            return 'Checking the change in the game…'
        if start == 'bad':
            return 'This change only shows when the game starts from just before this moment.'
        if here == 'warn' or start == 'warn' or states.get('Other scenes') == 'warn':
            return 'This change works, but other things changed too. Look at the pictures before you keep it.'
        return 'This change works. The game was replayed to check it.'

    def change_list(self) -> dict:
        with self.lock:
            views = [self._change_view(c, full=False) for c in self.changes]
            scenes = {sid for c in self.changes for sid in c['affected'] if sid in self.scenes}
            count = len(views)
            return {'revision': self.revision, 'changes': views, 'scene_count': len(scenes),
                    'summary': (f'{count} change{"s" if count != 1 else ""}: affects {len(scenes)} scene{"s" if len(scenes) != 1 else ""}'
                                if count else 'No changes yet')}

    # ---- how a scene looks with everything pending

    def _look(self, scene_id: str) -> dict:
        """The scene's picture with every pending change applied, re-rendered when more than one reaches it."""
        hits = [c for c in self._active() if c['affected'].get(scene_id, {}).get('verified')]
        waiting = any(c['affected'].get(scene_id, {}).get('state') == 'working' for c in self._active())
        if not hits:
            return {'image': 'scene:' + scene_id, 'state': 'working' if waiting else 'original', 'pixels': 0}
        if len(hits) == 1:
            only = hits[0]['affected'][scene_id]
            return {'image': 'render:' + only['key'], 'state': 'working' if waiting else 'changed', 'pixels': only.get('pixels', 0)}
        rom = self._rom_with(self._active())
        rom_sha = hashlib.sha256(rom).hexdigest()
        cached = self.renders.get((scene_id, rom_sha))
        if cached is None:
            offsets = [o - self.skip for c in hits for o, _, _ in c['writes']]
            hint = min(c['affected'][scene_id]['from_frame'] for c in hits)
            key = hashlib.sha1(f'{scene_id}:{rom_sha}:1:{hint}'.encode()).hexdigest()[:24]
            if key not in self.pending:
                self._submit(scene_id, rom, offsets, lambda sid, result: None, hint=hint, fixed=True)
            return {'image': 'render:' + hits[-1]['affected'][scene_id]['key'], 'state': 'working', 'pixels': 1}
        return {'image': 'render:' + cached['key'], 'state': 'working' if waiting else 'changed', 'pixels': cached.get('pixels', 0)}

    # ---- review and save

    def review(self) -> dict:
        """Everything that will be written and every scene it changes, rendered with all changes together."""
        with self.lock:
            if self.preview:
                raise ValueError('Keep or cancel the change you are trying before reviewing.')
            if not self.changes:
                raise ValueError('There are no changes to save yet.')
            views = [self._change_view(c, full=False) for c in self.changes]
            scene_ids = [sid for sid in self.scenes if any(sid in c['affected'] for c in self.changes)]
            scenes, working = [], 0
            for sid in scene_ids[:MAX_SCENES]:
                look = self._look(sid)
                working += look['state'] == 'working'
                names = [c['title'] for c in self.changes if c['affected'].get(sid, {}).get('verified')]
                scenes.append({'scene_id': sid, 'label': self._label(sid), 'before': 'scene:' + sid, 'after': look['image'],
                               'state': look['state'], 'changes': names, 'width': self.meta[sid]['width'], 'height': self.meta[sid]['height'],
                               'visible': look.get('pixels', 0) > 0})
            scenes.sort(key=lambda s: not s['visible'])
            unverified = [v['title'] for v in views if not v['verified']]
            edits = self._edits()
            total = len(self.scenes)
            ready = working == 0 and not any(v['working'] for v in views)
            self.review_state = {'revision': self.revision, 'ready': ready}
            count = len(views)
            return {'revision': self.revision, 'ready': ready, 'changes': views, 'scenes': scenes,
                    'bytes': sum(len(e['after']) // 2 for e in edits) + (grown := len(self._rom_with(self.changes)) - len(self.rom)),
                    'grows': grown, 'unverified': unverified,
                    'details': [{'title': c['title'], 'writes': [{'file_offset': o, 'before': a, 'after': b} for o, a, b in c['writes'][:64]]}
                                for c in self.changes],
                    'headline': f'{"These" if count != 1 else "This"} {count} change{"s" if count != 1 else ""} will be written. '
                                f'Here is everything that changes.',
                    'coverage': f'{sum(1 for s in scenes if s["visible"])} of {total} recorded scene{"s" if total != 1 else ""} '
                                'look different' + (f'; {quiet} more use the same data with nothing visible at that moment'
                                                    if (quiet := sum(1 for s in scenes if not s["visible"])) else '') +
                                ". Scenes you haven't recorded can't be shown.",
                    'writes_note': 'Your original ROM is not touched. Saving makes a separate, playable build and updates '
                                   'the cartridge checksum when the system has one.'}

    def _edits(self) -> list[dict]:
        """Merged byte edits (file offsets, lowercase hex) for every kept change."""
        final = self._rom_with(self.changes)
        offsets = sorted({o for c in self.changes for o, _, _ in c['writes'] if o < len(self.rom) and final[o] != self.rom[o]})
        edits, start = [], None
        for index, offset in enumerate(offsets):
            if start is None:
                start = offset
            if index + 1 == len(offsets) or offsets[index + 1] != offset + 1:
                edits.append({'offset': start, 'before': self.rom[start:offset + 1].hex(), 'after': final[start:offset + 1].hex()})
                start = None
        return edits

    def save(self, exporter, revision: int) -> dict:
        """Write the reviewed change list through `exporter(edits, annotations)`.

        Refuses unless review() has shown exactly this change list with every replay finished.
        """
        with self.lock:
            state = self.review_state
            if not state or state['revision'] != self.revision or revision != self.revision:
                raise ValueError('The change list changed after you reviewed it. Review it again before saving.')
            if not self.review()['ready']:
                raise ValueError('The scenes are still being redrawn, so wait for that to finish.')
            edits = self._edits()
            if not edits:
                raise ValueError('These changes leave the ROM as it is.')
            final = self._rom_with(self.changes)
            self.final_rom = final
            annotations = {'kind': 'traced-edit-v1', 'grown_to': len(final) if len(final) != len(self.rom) else None, 'changes': [
                {'title': c['title'], 'kind': c['kind'], 'bytes': len(c['writes']), 'scenes': len(c['affected']),
                 'method': c.get('method', ''), 'verified': self._change_view(c, full=False)['verified']} for c in self.changes]}
            result = exporter(edits, annotations)
            saved = {'saved': time.time(), 'changes': self.changes, 'result': {k: result.get(k) for k in ('artifact_id', 'sha256', 'name')}}
            history = self.store / 'saved.json'
            try:
                previous = json.loads(history.read_text()) if history.exists() else []
            except ValueError:
                previous = []
            history.write_text(json.dumps((previous + [saved])[-50:]))
            self.changes = []
            self.revision += 1
            self.review_state = None
            self._persist()
            return result

    def wait(self, timeout: float = 120) -> bool:
        """Block until no replay is running (for tests and scripts)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if not self.pending:
                    return True
            time.sleep(0.05)
        return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self.lock:
            if self.recording:
                self.recording['stop'] = True
        if self.host_lock.acquire(timeout=10):
            try:
                self._drop_host()
            finally:
                self.host_lock.release()
        elif self._host:
            self._host[0].terminate()
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
        for path in (self.store / 'work').glob('*'):
            if path.is_file():
                path.unlink(missing_ok=True)
            else:
                shutil.rmtree(path, ignore_errors=True)


def _with_checksums(rom: bytes, original: bytes, system: str) -> bytes:
    """`rom` with the header checksums the original had valid recomputed (Game Boy and Mega Drive at least)."""
    if rom == original:
        return rom
    try:
        from .graphics_trace import fix_checksums
        return fix_checksums(rom, original, system)
    except Exception:
        pass
    out = bytearray(rom)
    if system in ('gb', 'gbc') and len(out) >= 0x150:
        total = lambda b: (sum(b) - b[0x14E] - b[0x14F]) & 0xFFFF
        if int.from_bytes(original[0x14E:0x150], 'big') == total(original):
            out[0x14E:0x150] = total(out).to_bytes(2, 'big')
    elif system == 'genesis' and len(out) >= 0x200:
        total = lambda b: sum(int.from_bytes(b[i:i + 2], 'big') for i in range(0x200, len(b) & ~1, 2)) & 0xFFFF
        if int.from_bytes(original[0x18E:0x190], 'big') == total(original):
            out[0x18E:0x190] = total(out).to_bytes(2, 'big')
    return bytes(out)


def _decode_stored(fmt: str, raw: bytes) -> list:
    from .level_palette import decode_palette
    if fmt == 'nes-index':
        return [list(pt.NES_RGB[raw[0] & 0x3F])]
    return decode_palette(raw, fmt, 4 if fmt == 'dmg-shades' else 1)


def _swatch_name(swatch: pt.Swatch, line: int) -> str:
    if swatch.format == 'dmg-shades':
        return swatch.group
    return f'{swatch.group}, color {swatch.entry % line + 1}'


def _private_copy_support() -> dict:
    """Whether "only this scene" can be offered: graphics_trace.plan_private_copy moves a private copy and repoints one use."""
    try:
        from . import graphics_trace
    except Exception:
        graphics_trace = None
    if graphics_trace is not None and callable(getattr(graphics_trace, 'plan_private_copy', None)):
        return {'available': True, 'reason': ''}
    return {'available': False, 'reason': 'Changing only this scene needs ROMancer to give it a private copy of the data and '
                                          'point this one use at it. That tool is not part of this build yet, so a '
                                          'change applies everywhere the data is used.'}


# ----------------------------------------------------------------- workbench operations

class EditSessionTools:
    """`edits.*` operations: one EditSession per open ROM, stored inside its project."""

    def __init__(self, api):
        self.api = api
        self.sessions: dict[tuple, EditSession] = {}
        self.lock = threading.Lock()

    def routes(self) -> dict:
        base = 'project_id artifact_id'
        return {
            'edits.engines': ('', self._engines),
            'edits.open': (base, lambda p, c: self._summary(self.session(p))),
            'edits.record': (base + ' steps restart', lambda p, c: self._summary(self.session(p), self.session(p).record(p['steps'], restart=bool(p['restart'])))),
            'edits.record_stop': (base, lambda p, c: self._summary(self.session(p), self.session(p).stop_recording())),
            'edits.level_play_from': (base + ' level_id x y', lambda p, c: {'ok': True, **self.session(p).level_play_from(
                p['level_id'], p['x'], p['y'])}),
            'edits.play_stop': (base, lambda p, c: {'ok': True, **self.session(p).play_stop()}),
            'edits.level_compare': (base + ' level_id', lambda p, c: {'ok': True, **self.session(p).level_compare(
                p['level_id'], p.get('x'), p.get('y'))}),
            'edits.level_compare_file': (base + ' level_id', self._compare_file),
            'edits.level_secret': (base + ' level_id kind number stage floor', lambda p, c: {'ok': True, 'change': self.session(p).propose_level_secret(
                p['level_id'], p['kind'], p['number'], p['stage'], p['floor'], p.get('item'), p.get('treasure'), p.get('trigger'))}),
            'edits.play': (base + ' frames buttons', lambda p, c: {'ok': True, **self.session(p).play(p['frames'], p['buttons'])}),
            'edits.capture': (base + ' label', lambda p, c: {'ok': True, **self.session(p).capture(p['label'])}),
            'edits.forget_scene': (base + ' scene_id', lambda p, c: self._summary(self.session(p), self.session(p).forget_scene(p['scene_id']))),
            'edits.scene': (base + ' scene_id', lambda p, c: {'ok': True, **self.session(p).scene_view(p['scene_id'])}),
            'edits.image': (base + ' key', lambda p, c: {'ok': True, 'key': p['key'],
                                                          'png_base64': base64.b64encode(self.session(p).image(p['key'])).decode()}),
            'edits.propose_color': (base + ' scene_id domain entry colors scope', lambda p, c: {'ok': True, 'change': self.session(p).propose_color(
                p['scene_id'], p['domain'], p['entry'], p['colors'], p['scope'])}),
            'edits.propose_writes': (base + ' scene_id title writes', lambda p, c: {'ok': True, 'change': self.session(p).propose_writes(
                p['scene_id'], p['writes'], p['title'])}),
            'edits.graphics': (base + ' scene_id', lambda p, c: {'ok': True, **sg.compact(self.session(p).graphics_view(p['scene_id']))}),
            'edits.tile_at': (base + ' scene_id x y', lambda p, c: {'ok': True, **self.session(p).tile_at(p['scene_id'], p['x'], p['y'])}),
            'edits.propose_tile': (base + ' scene_id tile pixels scope', lambda p, c: {'ok': True, 'change': self.session(p).propose_tile(
                p['scene_id'], p['tile'], p['pixels'], p['scope'])}),
            'edits.export_picture': (base + ' scene_id what layer', self._export_picture),
            'edits.import_picture': (base + ' scene_id what layer png_base64', self._import_picture),
            'edits.export_everything': (base, self._export_everything),
            'edits.propose_cells': (base + ' scene_id cells', lambda p, c: {'ok': True, 'change': self.session(p).propose_cells(
                p['scene_id'], p['cells'])}),
            'edits.find_color': (base + ' scene_id domain entry colors', lambda p, c: {'ok': True, 'change': self.session(p).find_color(
                p['scene_id'], p['domain'], p['entry'], p['colors'])}),
            'edits.level_start': (base + ' name', lambda p, c: self._summary(self.session(p), self.session(p).level_start(p['name']))),
            'edits.level_auto': (base + ' steps direction', lambda p, c: self._summary(self.session(p), self.session(p).level_auto(p['steps'], p['direction']))),
            'edits.level_stop': (base, lambda p, c: self._summary(self.session(p), self.session(p).level_stop())),
            'edits.level_forget': (base + ' level_id', lambda p, c: self._summary(self.session(p), self.session(p).level_forget(p['level_id']))),
            'edits.level': (base + ' level_id plane', lambda p, c: {'ok': True, **self.session(p).level_view(p['level_id'], p['plane'])}),
            'edits.level_place': (base + ' level_id plane col row', lambda p, c: {'ok': True, **self.session(p).level_place(
                p['level_id'], p['plane'], p['col'], p['row'])}),
            'edits.level_paint': (base + ' level_id plane cells layers', lambda p, c: {'ok': True, 'change': self.session(p).propose_level(
                p['level_id'], p['plane'], p['cells'], p['layers'])}),
            'edits.level_export': (base + ' level_id plane edited', self._export_level),
            'edits.level_objects': (base + ' level_id', lambda p, c: {'ok': True, **self.session(p).level_objects(p['level_id'])}),
            'edits.level_object_choices': (base + ' level_id zone stage floor', lambda p, c: {'ok': True, **self.session(p).level_object_choices(
                p['level_id'], p['zone'], p['stage'], p['floor'])}),
            'edits.level_object': (base + ' level_id zone kind index stage floor', lambda p, c: {'ok': True, 'change': self.session(p).propose_level_object(
                p['level_id'], p['zone'], p['kind'], p['index'], p['stage'], p['floor'])}),
            'edits.change': (base + ' change_id', lambda p, c: {'ok': True, 'change': self.session(p).change(p['change_id'])}),
            'edits.keep': (base + ' change_id', lambda p, c: self._summary(self.session(p), self.session(p).keep(p['change_id']))),
            'edits.remove': (base + ' change_id', lambda p, c: self._summary(self.session(p), self.session(p).remove(p['change_id']))),
            'edits.review': (base, lambda p, c: {'ok': True, **self.session(p).review()}),
            'edits.save': (base + ' revision', self._save),
            'edits.close': (base, self._close),
        }

    def _export_picture(self, p, c):
        out = self.session(p).export_picture(p['scene_id'], p['what'], p['layer'])
        return {'ok': True, **{k: v for k, v in out.items() if k != 'png'}, 'png_base64': base64.b64encode(out['png']).decode()}

    def _export_everything(self, p, c):
        out = self.session(p).export_everything()
        return {'ok': True, **{k: v for k, v in out.items() if k != 'zip'}, 'zip_base64': base64.b64encode(out['zip']).decode()}

    def _compare_file(self, p, c):
        out = self.session(p).level_compare_file(p['level_id'])
        return {'ok': True, 'name': out['name'], 'gif_base64': base64.b64encode(out['gif']).decode()}

    def _export_level(self, p, c):
        out = self.session(p).export_level(p['level_id'], p['plane'], bool(p['edited']))
        return {'ok': True, **{k: v for k, v in out.items() if k != 'png'}, 'png_base64': base64.b64encode(out['png']).decode()}

    def _import_picture(self, p, c):
        text = p['png_base64']
        if type(text) is not str or len(text) > sp.MAX_PNG * 4 // 3 + 8:
            raise ValueError(f'That PNG is larger than {sp.MAX_PNG // 1024} KB. Save it as an 8-bit (palette) PNG and try again.')
        try:
            raw = base64.b64decode(text, validate=True)
        except ValueError:
            raise ValueError('That file is not a PNG picture ROMancer can read.') from None
        return {'ok': True, **self.session(p).import_picture(p['scene_id'], p['what'], p['layer'], raw)}

    def _engines(self, p, c):
        from .trace_cores import available
        return {'ok': True, 'engines': available()}

    def _summary(self, session, value=None):
        return {'ok': True, **(value or session.summary())}

    def session(self, p) -> EditSession:
        from . import workbench_projects as projects
        from .release_scope import SYSTEMS
        project, row, path = self.api.source(p)
        if row.get('system_id') not in SYSTEMS:
            raise ValueError('Scene editing works with NES, Super NES, Mega Drive, Master System, Game Boy and Game Boy Color games.')
        key = (projects.identifier(p['project_id']), row['sha256'])
        with self.lock:
            session = self.sessions.get(key)
            if session is None:
                while len(self.sessions) >= 2:              # keep at most two games' engines alive
                    self.sessions.pop(next(iter(self.sessions))).close()
                store = project / 'trace-scenes' / row['sha256'][:32]
                session = self.sessions[key] = EditSession(store, path, row['system_id'])
            return session

    def _save(self, p, c):
        from . import workbench_projects as projects
        session = self.session(p)
        project, row, path = self.api.source(p)
        note = {}

        def exporter(edits, annotations):
            from .system_integrity import integrity_edits
            if annotations.get('grown_to'):
                # A change needed more room than the ROM had, so the build is a longer file: write it whole.
                from .workbench_files import register_completed_build
                final = session.final_rom
                target = project / 'builds' / (uuid.uuid4().hex + Path(row['path']).suffix)
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(final)
                note['checksum'] = ('The ROM is %d bytes longer, and its header and checksum were updated to match.'
                                    % (len(final) - len(session.rom)))
                number = len(projects.read_project(project)['builds']) + 1
                return register_completed_build(project, row['artifact_id'], target, hashlib.sha256(final).hexdigest(),
                                                'traced-edit', f'Build {number}', expected_parent_sha256=row['sha256'])
            try:
                complete = integrity_edits(path, row['sha256'], row['system_id'], edits)
                note['checksum'] = ('The cartridge checksum was updated to match.' if len(complete) > len(edits)
                                    else 'No checksum update was needed.')
            except ValueError as error:
                complete = edits
                note['checksum'] = 'The cartridge checksum was left as it is: ' + str(error)
            plan = projects.plan_byte_edits(project, row['artifact_id'], sorted(complete, key=lambda e: e['offset']), annotations=annotations)
            return self.api._apply_byte_build({'project_id': p['project_id'], 'plan_id': plan['plan_id']}, c)
        result = session.save(exporter, p['revision'])
        result['checksum_note'] = note.get('checksum', '')
        try:
            name = projects.read_project(project)['name']
            patch = self.api._patch({'project_id': p['project_id'], 'source_id': row['artifact_id'], 'target_id': result['artifact_id'],
                                     'title': name + ' scene edits', 'description': 'Made with ROMancer scene editing.'}, c)
            result['patch_export'] = patch.get('export')
        except (ValueError, OSError, KeyError) as error:
            result['patch_export'] = None
            result['patch_note'] = str(error)[:200]
        return {**result, 'ok': True, 'session': session.summary()}

    def _close(self, p, c):
        from . import workbench_projects as projects
        _, row, _ = self.api.source(p)
        with self.lock:
            session = self.sessions.pop((projects.identifier(p['project_id']), row['sha256']), None)
        if session:
            session.close()
        return {'ok': True}

    def close(self) -> None:
        with self.lock:
            sessions, self.sessions = list(self.sessions.values()), {}
        for session in sessions:
            session.close()
