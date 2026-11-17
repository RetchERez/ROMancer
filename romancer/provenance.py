"""Where on-screen data comes from in the ROM, and what an edit changes.

A tracing engine (see trace/romancer_trace.h) tags each byte of palette RAM,
video RAM and work RAM with the ROM byte its value came from. This module
turns those tags into scenes and an impact index, and checks edits by
replaying the real engine.

* TraceSession runs a tracing engine, keeps rolling savestate checkpoints and
  takes snapshots of every traced domain.
* Scene is one moment: a checkpoint plus the ROM sources of its domains.
* ImpactIndex inverts scenes: for a ROM range, which scenes use it.
* verify_edit replays a scene with an edited ROM and reports exactly which
  domain bytes changed. It is the causal check that turns a tag (a claim)
  into a verified effect.
"""
from __future__ import annotations

import ctypes
import hashlib
from array import array
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

RT_NONE, RT_ROM, RT_IMM, RT_DERIVED = 0, 1, 2, 3
RT_WEAK = 0x80000000
RT_OFFSET_MASK = 0x0FFFFFFF
KIND_NAMES = {RT_NONE: 'none', RT_ROM: 'rom', RT_IMM: 'code', RT_DERIVED: 'derived'}
TRACE_VERSION = 1


class _Domain(ctypes.Structure):
    _fields_ = [('name', ctypes.c_char_p), ('size', ctypes.c_uint32),
                ('tag', ctypes.POINTER(ctypes.c_uint32)), ('pc', ctypes.POINTER(ctypes.c_uint32)),
                ('data', ctypes.POINTER(ctypes.c_uint8))]


def tag_kind(tag: int) -> int:
    return (tag >> 28) & 7


def tag_offset(tag: int) -> int:
    return tag & RT_OFFSET_MASK


@dataclass(frozen=True)
class DomainSnapshot:
    name: str
    data: bytes | None
    tags: array  # 'I'
    pcs: array   # 'I'

    def sources(self, kinds=(RT_ROM, RT_IMM, RT_DERIVED), include_weak=True):
        """{rom_offset: [domain indices]} for tagged bytes of the given kinds."""
        out: dict[int, list[int]] = {}
        for i, t in enumerate(self.tags):
            if tag_kind(t) in kinds and (include_weak or not t & RT_WEAK):
                out.setdefault(tag_offset(t), []).append(i)
        return out


@dataclass
class Snapshot:
    frame: int
    domains: dict[str, DomainSnapshot]
    screen_sha256: str | None = None

    def kind_counts(self) -> dict[str, dict[str, int]]:
        result = {}
        for name, d in self.domains.items():
            counts = {v: 0 for v in KIND_NAMES.values()}
            for t in d.tags:
                counts[KIND_NAMES.get(tag_kind(t), 'none')] += 1
            result[name] = counts
        return result


class TraceSession:
    """A tracing engine with a loaded game, rolling checkpoints and snapshots."""

    def __init__(self, frontend, *, checkpoint_every: int = 60, keep: int = 600):
        self.fe = frontend
        lib = frontend.lib
        for name in ('romancer_trace_version', 'romancer_trace_enable', 'romancer_trace_reset',
                     'romancer_trace_domain_count', 'romancer_trace_domain', 'romancer_trace_writes'):
            if not hasattr(lib, name):
                raise ValueError('This engine is not a ROMancer tracing build.')
        lib.romancer_trace_domain.restype = ctypes.POINTER(_Domain)
        lib.romancer_trace_writes.restype = ctypes.c_uint64
        if lib.romancer_trace_version() != TRACE_VERSION:
            raise ValueError('Tracing engine version differs from this ROMancer.')
        self.lib = lib
        self.frame = 0
        self.every = checkpoint_every
        self.keep = keep
        self.checkpoints: list[tuple[int, bytes]] = []

    def start(self):
        self.lib.romancer_trace_reset()
        self.lib.romancer_trace_enable(1)
        self.checkpoints = [(self.frame, self.fe.serialize())]

    def run(self, frames: int, buttons_for: Callable[[int], Iterable[str]] = lambda f: ()):
        for _ in range(frames):
            self.fe.run_frame(list(buttons_for(self.frame)))
            self.frame += 1
            if self.frame % self.every == 0:
                self.checkpoints.append((self.frame, self.fe.serialize()))
                if len(self.checkpoints) > self.keep:
                    del self.checkpoints[1]  # keep the boot checkpoint
        return self.fe.last_frame

    def snapshot(self) -> Snapshot:
        domains = {}
        for i in range(self.lib.romancer_trace_domain_count()):
            d = self.lib.romancer_trace_domain(i).contents
            n = d.size
            name = d.name.decode()
            domains[name] = DomainSnapshot(
                name,
                ctypes.string_at(d.data, n) if d.data else None,
                array('I', ctypes.cast(d.tag, ctypes.POINTER(ctypes.c_uint32 * n)).contents),
                array('I', ctypes.cast(d.pc, ctypes.POINTER(ctypes.c_uint32 * n)).contents))
        frame = self.fe.last_frame
        return Snapshot(self.frame, domains, frame.sha256() if frame else None)

    def checkpoint_before(self, frame: int) -> tuple[int, bytes]:
        frames = [f for f, _ in self.checkpoints]
        i = bisect_right(frames, frame) - 1
        if i < 0:
            raise ValueError('No checkpoint precedes that frame.')
        return self.checkpoints[i]


@dataclass
class Scene:
    """One traced moment, identified by game, frame and screen."""
    id: str
    frame: int
    screen_sha256: str | None
    checkpoints: list[tuple[int, bytes]]
    snapshot: Snapshot
    label: str = ''
    inputs: list[list[str]] = field(default_factory=list)  # buttons per frame since the first checkpoint

    def ranges(self, domain: str, kinds=(RT_ROM, RT_IMM, RT_DERIVED)) -> list[tuple[int, int]]:
        """Merged half-open ROM ranges that feed `domain` in this scene."""
        d = self.snapshot.domains.get(domain)
        if not d:
            return []
        return merge_ranges((o, o + 1) for o in d.sources(kinds))


def merge_ranges(pairs: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for a, b in sorted(pairs):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def scene_from_session(session: TraceSession, label: str = '', inputs=None) -> Scene:
    snap = session.snapshot()
    ident = hashlib.sha256(f'{snap.frame}:{snap.screen_sha256}'.encode()).hexdigest()[:16]
    return Scene(ident, snap.frame, snap.screen_sha256, list(session.checkpoints), snap, label, inputs or [])


class ImpactIndex:
    """ROM range -> scenes and domain bytes that use it."""

    def __init__(self):
        self.scenes: dict[str, Scene] = {}
        self._by_offset: dict[int, set[tuple[str, str]]] = {}

    def add(self, scene: Scene):
        self.scenes[scene.id] = scene
        for name, d in scene.snapshot.domains.items():
            for offset in d.sources():
                self._by_offset.setdefault(offset, set()).add((scene.id, name))

    def users(self, start: int, end: int) -> dict[str, set[str]]:
        """{scene id: {domain names}} for scenes that use any byte in [start, end)."""
        out: dict[str, set[str]] = {}
        for offset in range(start, end):
            for scene_id, name in self._by_offset.get(offset, ()):
                out.setdefault(scene_id, set()).add(name)
        return out

    def readers_of(self, start: int, end: int) -> int:
        return sum(1 for o in range(start, end) if o in self._by_offset)


def verify_edit(make_frontend: Callable[[bytes], object], original: bytes, edited: bytes, scene: Scene,
                domains: Iterable[str] = ('palette', 'vram'), buttons_for=None) -> dict:
    """Replay `scene` with `edited` loaded and report which domain bytes differ.

    The replay starts from the latest checkpoint at which the change still
    reaches the scene: data the game already copied into video memory before
    a checkpoint would hide the edit, so earlier checkpoints are tried until
    the change shows or the boot checkpoint is reached.
    """
    domains = list(domains)
    baseline = scene.snapshot.domains
    tried = []
    for start, state in reversed(scene.checkpoints):
        fe = make_frontend(edited)
        try:
            fe.unserialize(state)
            session = TraceSession(fe)
            session.frame = start
            session.start()
            session.run(scene.frame - start, buttons_for or (lambda f: ()))
            snap = session.snapshot()
            changed = {}
            for name in domains:
                before, after = baseline.get(name), snap.domains.get(name)
                if before is None or after is None or before.data is None or after.data is None:
                    continue
                idx = [i for i, (a, b) in enumerate(zip(before.data, after.data)) if a != b]
                if idx:
                    changed[name] = idx
            tried.append(start)
            if changed:
                return {'verified': True, 'from_frame': start, 'changed': changed,
                        'screen_sha256': snap.screen_sha256, 'checkpoints_tried': tried}
        finally:
            fe.close()
    return {'verified': False, 'changed': {}, 'checkpoints_tried': tried}
