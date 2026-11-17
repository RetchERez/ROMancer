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
from .libretro_frontend import BUTTON_IDS, LibretroError
from .trace_cores import SYSTEM_LABELS, TraceCoreMissing, TraceFrontend, core_options, header_skip, trace_core_for

STEP_FRAMES = 300          # auto-explore looks at the screen this often
MAX_SCENES = 160
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
    return pv.Scene(header['id'], header['frame'], header['screen_sha256'], [], snapshot, header.get('label', '')), header, rgb


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
        self.known = []     # (palette source hash, fingerprint) of scenes already in the store
        for path in (self.store / 'scenes').glob('*.scene'):
            try:
                header = read_scene_header(path)
                self.known.append((header.get('palette_sources'), bytes.fromhex(header.get('fingerprint', ''))))
            except (ValueError, OSError, KeyError):
                continue
        saved = self.run_dir / 'inputs.bin'
        if cfg.get('resume') and saved.exists():
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
        meta = {'id': scene.id, 'frame': scene.frame, 'screen_sha256': scene.screen_sha256, 'label': label,
                'origin': origin, 'run': self.cfg['run'], 'created': time.time(), 'checkpoints': [f for f, _ in thin],
                'palette_sources': palette_sources, 'fingerprint': fingerprint.hex()}
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
                _, steps, variant = command
                for step in range(steps):
                    if conn.poll() and conn.recv()[0] in ('stop', 'close'):
                        break
                    start = self.session.frame
                    self.advance(array('H', [_mask(explore(f, variant)) for f in range(start, start + STEP_FRAMES)]))
                    conn.send(('step', step + 1, steps, self.record('', 'explore', only_new=True), self.session.frame))
                conn.send(('done', self.session.frame))
            elif kind == 'play':
                _, frames, mask = command
                self.advance(array('H', [mask]) * frames)
                frame = self.frame()
                conn.send(('frame', png_bytes(frame.width, frame.height, frame.rgb), self.session.frame, frame.width, frame.height))
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

def _replay(fe, state: bytes, start: int, scene: pv.Scene, buttons):
    if int(fe.lib.retro_serialize_size()) <= 0:
        fe.run_frame([])                # some engines accept a savestate only after their first frame
    fe.unserialize(state)
    session = _Session(fe, checkpoint_every=10 ** 9)
    session.frame = start
    session.lib.romancer_trace_reset()
    session.lib.romancer_trace_enable(1)
    session.run(scene.frame - start, buttons)
    return session.snapshot(), fe.last_frame


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

    def replay(self, rom_path, start: int):
        fe = _frontend(self.job, rom_path)
        try:
            snapshot, frame = _replay(fe, self.state(start), start, self.scene, self.buttons)
        finally:
            _close(fe)
        data = {name: snapshot.domains[name].data for name in _video_domains(snapshot) if snapshot.domains[name].data is not None}
        return data, frame

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
        final = quiet = None
        for start in starts:
            base = trail.baseline(start)
            if base is None:
                result['unfaithful'].append(start)
                continue
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

class EditSession:
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
        self.live = {'state': 'off', 'message': '', 'frame': 0, 'progress': None}
        self.recording: dict | None = None
        self._host = None
        self._pool = None
        self._closed = False
        for folder in ('scenes', 'runs', 'renders', 'work'):
            (self.store / folder).mkdir(parents=True, exist_ok=True)
        self._load()

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
            return
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
        self.live.update(state='off', message=message, progress=None)
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
            if len(self.scenes) >= MAX_SCENES:
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
                        if len(self.scenes) >= MAX_SCENES or recording.get('stop'):
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
            self._host[1].send(('play', frames, mask))
            _, png, frame, width, height = self._receive()
            self.live['frame'] = frame
            return {'busy': False, 'png_base64': base64.b64encode(png).decode(), 'frame': frame, 'width': width, 'height': height}
        finally:
            self.host_lock.release()

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
            if len(self.scenes) >= MAX_SCENES:
                raise ValueError(f'This game already has {MAX_SCENES} recorded scenes. Remove some before capturing more.')
            self._host[1].send(('capture', str(label)[:80]))
            _, meta, frame = self._receive()
        self._add_scene(self.store / 'scenes' / (meta['id'] + '.scene'))
        return {'scene_id': meta['id'], **self.summary()}

    def forget_scene(self, scene_id: str) -> dict:
        with self.lock:
            self._scene(scene_id)
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
            for change in self.changes:
                change['affected'].pop(scene_id, None)
            self._persist()
        return self.summary()

    # ---- what the UI lists

    def summary(self) -> dict:
        with self.lock:
            scenes = [{'id': sid, 'label': self._label(sid), 'frame': m['frame'], 'origin': m.get('origin', 'explore'),
                       'image': 'scene:' + sid, 'width': m['width'], 'height': m['height']} for sid, m in self.meta.items()]
            recording = dict(self.recording) if self.recording else None
            return {'system': self.system, 'system_label': SYSTEM_LABELS.get(self.system, self.system),
                    'engine': {'installed': bool(self.core), 'reason': self.core_error},
                    'scenes': scenes, 'scene_limit': MAX_SCENES, 'recording': recording, 'live': dict(self.live),
                    'changes': self.change_list(), 'preview': self._change_view(self.preview) if self.preview else None,
                    'private_copy': _private_copy_support()}

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
                change = active.get(key) if swatch.editable else None
                swatches.append({
                    'id': f'{swatch.domain}:{swatch.entry}', 'domain': swatch.domain, 'entry': swatch.entry, 'group': swatch.group,
                    'name': _swatch_name(swatch, line.get(swatch.domain, 16)), 'format': swatch.format, 'colors': swatch.rgb,
                    'editable': swatch.editable, 'status': swatch.status, 'locked_reason': reason,
                    'uses': len(uses), 'notes': list(swatch.notes),
                    'pending': change['to_rgb'] if change else None, 'pending_change': change['id'] if change else None,
                    'details': [{'file_offset': s['offset'] + self.skip, 'kind': s['kind'], 'code_address': s['pc']} if s else None
                                for s in swatch.sources]})
            return {'scene': {'id': scene_id, 'label': self._label(scene_id), 'frame': scene.frame, 'origin': meta.get('origin'),
                              'image': 'scene:' + scene_id, 'width': meta['width'], 'height': meta['height']},
                    'swatches': swatches, 'pickers': pickers, 'line': line, 'look': self._look(scene_id),
                    'recorded_scenes': len(self.scenes)}

    def image(self, key: str) -> bytes:
        kind, _, name = str(key).partition(':')
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

    def _submit(self, scene_id: str, rom: bytes, offsets, sink, *, hint=None, fixed=False, thorough=False) -> str:
        rom_sha = hashlib.sha256(rom).hexdigest()
        cached = self.renders.get((scene_id, rom_sha))
        if cached is not None:
            sink(scene_id, cached)
            return cached['key']
        path = self.store / 'work' / (rom_sha[:24] + self.suffix)
        if not path.exists():
            path.write_bytes(rom)
        key = hashlib.sha1(f'{scene_id}:{rom_sha}:{int(fixed)}:{hint}'.encode()).hexdigest()[:24]
        job = dict(self._cfg(), rom=str(path), base_rom=str(self.rom_path), scene_id=scene_id, key=key, rom_sha=rom_sha,
                   expected=self._expected(scene_id, offsets), hint=hint, fixed=fixed, thorough=thorough)
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
                future = self._ensure_pool().submit(private_copy_task, job)

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
                        change['writes'] = sorted(result['writes'])
                        change['notes'] = result.get('notes', [])
                        if self.preview is change:
                            self._propose(change)
                future.add_done_callback(planned)
                return self._change_view(change)
            tracing = change.get('expect_offsets') or [offset - self.skip for offset, _, _ in change['writes']]
            users = set()
            for offset in tracing:
                users.update(self.impact.users(offset, offset + 1))
            users.add(change['scene_id'])
            order = [change['scene_id']] + [sid for sid in self.scenes if sid in users and sid != change['scene_id']]
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
                self._submit(sid, rom, tracing, sink, thorough=change['kind'] != 'color' or change.get('scope') != 'all')
            return self._change_view(change)

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
                self.changes = [c for c in self.changes if c['key'] != change['key']] + [change]
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
                status = 'Re-rendering…'
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
                'verdict': ('Finding where this scene loads the data from, so only this scene changes…' if planning else
                            failed if failed else
                            'Re-rendering every scene that uses this…' if working else
                            'Checked: the real game was replayed with this change and the color changed.' if verified else
                            'Not confirmed: the replay did not show this change. It may not do what you expect.'),
                'details': [{'file_offset': o, 'before': a, 'after': b} for o, a, b in change['writes'][:64]] if full else []}

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
                raise ValueError('Keep or cancel the color you are trying before reviewing.')
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
                    'bytes': sum(len(e['after']) // 2 for e in edits), 'unverified': unverified,
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
        offsets = sorted({o for c in self.changes for o, _, _ in c['writes'] if final[o] != self.rom[o]})
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
                raise ValueError('Scenes are still being re-rendered. Wait for the review to finish.')
            edits = self._edits()
            if not edits:
                raise ValueError('These changes leave the ROM as it is.')
            annotations = {'kind': 'traced-edit-v1', 'changes': [
                {'title': c['title'], 'kind': c['kind'], 'bytes': len(c['writes']), 'scenes': len(c['affected']),
                 'verified': any(r.get('verified') for r in c['affected'].values())} for c in self.changes]}
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
                                          'point this one use at it. That tool is not part of this preview build yet, so a '
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
            'edits.change': (base + ' change_id', lambda p, c: {'ok': True, 'change': self.session(p).change(p['change_id'])}),
            'edits.keep': (base + ' change_id', lambda p, c: self._summary(self.session(p), self.session(p).keep(p['change_id']))),
            'edits.remove': (base + ' change_id', lambda p, c: self._summary(self.session(p), self.session(p).remove(p['change_id']))),
            'edits.review': (base, lambda p, c: {'ok': True, **self.session(p).review()}),
            'edits.save': (base + ' revision', self._save),
            'edits.close': (base, self._close),
        }

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
                                     'title': name + ' colors', 'description': 'Made with ROMancer scene editing.'}, c)
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
