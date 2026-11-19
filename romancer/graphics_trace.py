"""Live tiles and background maps from a tracing engine, mapped to ROM bytes.

The graphics counterpart of romancer.palette_trace. A Scene (see
romancer.provenance) holds video memory plus, for every byte, the ROM byte it
came from. This module turns that into tiles and tilemap cells, plans ROM
writes for an edit, and confirms the plan by replaying the real engine.

Reading
    tiles(scene, system, rom=None)            -> [Tile]
    layers(scene, system, video=None)         -> [Layer] of MapCell
    capture_video(session, system)            -> video registers, when the engine exposes them
    scene_from_session(session, system)       -> Scene with .video attached

Editing, simplest first
    plan_tile_edit(tile, pixels, rom)         -> [(offset, old, new)]  tile bytes that are ROM bytes
    plan_tilemap_edit(cell, rom, tile=...)    -> [(offset, old, new)]  map cells that are ROM bytes
    find_compressed_block / plan_block_edit   -> EditPlan: decode, edit, re-encode; in place when it
                                                 fits, else relocate and repoint
    plan_overlay_patch                        -> EditPlan: codec-independent fallback; a small routine
                                                 on the vertical-blank interrupt rewrites the edited
                                                 tile after the game's own loader has run (every
                                                 processor: see OVERLAY_STATUS; the 6502 and Z80
                                                 routines live in romancer.gfx_overlay8)
    plan_private_copy                         -> EditPlan: "change only this one" by copying the data
                                                 and repointing the single reference
    plan_derived_tile_edit                    -> tries the three paths above in that order

Every plan ends in verify_plan, which replays the scene with the edited ROM
(provenance.verify_edit) and reports whether the planned bytes took their
planned values, and every other byte that changed.

Two facts are kept apart for an overlay, because they are different facts:
    verify_plan            the scene, replayed from a checkpoint shortly before it, comes out as planned
    verify_from_power_on   the whole recorded run with the edited ROM reaches the scene changed only as planned
overlay_safety runs the second and, when it fails, says whether the overlay
is to blame: it compares with plan_hook_only (the interrupt hook alone) and
plan_overlay_control (the routine's cost without its video access).

Offsets: tags hold ROM offsets with the file header removed (16-byte iNES
header, 512-byte SNES copier header). Every offset this module returns in a
write list is a FILE offset: the header is added back. Tile and cell
`.sources` keep the raw tag offsets, as palette_trace.Swatch does;
`rom_skip(rom, system)` is the difference.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from . import gfx_codecs
from . import provenance as pv
from .provenance import RT_WEAK, Scene, tag_kind, tag_offset

KIND = ('', 'rom', 'code', 'derived')
CPU = {'gb': 'sm83', 'gbc': 'sm83', 'nes': '6502', 'snes': '65816', 'genesis': '68000', 'sms': 'z80', 'gg': 'z80'}

# ---------------------------------------------------------------------------
# 1. Tile pixel formats
# ---------------------------------------------------------------------------

# format -> (bits per pixel, stored bytes)
TILE_FORMATS = {
    'gb-2bpp': (2, 16), 'nes-2bpp': (2, 16),
    'snes-2bpp': (2, 16), 'snes-4bpp': (4, 32), 'snes-8bpp': (8, 64), 'snes-mode7': (8, 64),
    'genesis-4bpp': (4, 32), 'sms-4bpp': (4, 32),
}
SYSTEM_TILE_FORMAT = {'gb': 'gb-2bpp', 'gbc': 'gb-2bpp', 'nes': 'nes-2bpp', 'snes': 'snes-4bpp',
                      'genesis': 'genesis-4bpp', 'sms': 'sms-4bpp', 'gg': 'sms-4bpp'}


def _plane_offset(fmt: str, plane: int, y: int) -> int:
    if fmt == 'nes-2bpp':
        return plane * 8 + y
    if fmt == 'sms-4bpp':
        return y * 4 + plane
    return (plane // 2) * 16 + y * 2 + (plane & 1)  # Game Boy and SNES: plane pairs interleaved by row


def decode_tile(raw: bytes, fmt: str) -> list[int]:
    """64 color indices, row by row, for one 8x8 tile."""
    bpp, size = TILE_FORMATS[fmt]
    if len(raw) != size:
        raise ValueError(f'{fmt} tiles are {size} bytes')
    if fmt == 'snes-mode7':
        return list(raw)
    if fmt == 'genesis-4bpp':
        return [(raw[y * 4 + x // 2] >> (0 if x & 1 else 4)) & 15 for y in range(8) for x in range(8)]
    return [sum(((raw[_plane_offset(fmt, p, y)] >> (7 - x)) & 1) << p for p in range(bpp))
            for y in range(8) for x in range(8)]


def encode_tile(pixels: Iterable[int], fmt: str) -> bytes:
    bpp, size = TILE_FORMATS[fmt]
    pixels = list(pixels)
    if len(pixels) != 64 or any(type(p) is not int or not 0 <= p < (1 << bpp) for p in pixels):
        raise ValueError(f'{fmt} tiles are 64 pixels of 0..{(1 << bpp) - 1}')
    if fmt == 'snes-mode7':
        return bytes(pixels)
    out = bytearray(size)
    for y in range(8):
        for x in range(8):
            v = pixels[y * 8 + x]
            if fmt == 'genesis-4bpp':
                out[y * 4 + x // 2] |= v << (0 if x & 1 else 4)
            else:
                for p in range(bpp):
                    out[_plane_offset(fmt, p, y)] |= ((v >> p) & 1) << (7 - x)
    return bytes(out)


def rom_skip(rom: bytes, system: str) -> int:
    """Bytes of file header in front of the ROM image the tags index."""
    if system == 'nes' and rom[:4] == b'NES\x1a':
        return 16
    if system == 'snes' and len(rom) % 1024 == 512:
        return 512
    return 0


# ---------------------------------------------------------------------------
# 2. Scene -> tiles and tilemap cells
# ---------------------------------------------------------------------------

def _source(d, i):
    t = d.tags[i]
    kind = tag_kind(t)
    if kind == 0 or kind > 3:
        return None
    return {'offset': tag_offset(t), 'kind': KIND[kind], 'weak': bool(t & RT_WEAK), 'pc': d.pcs[i]}


def _status(sources) -> str:
    kinds = {s['kind'] for s in sources if s}
    if not kinds or any(s is None for s in sources):
        return 'unknown'
    return 'derived' if 'derived' in kinds else 'code' if 'code' in kinds else 'rom'


@dataclass
class Tile:
    system: str
    domain: str          # 'vram', 'chr' (NES CHR-RAM) or 'chr_rom' (NES pattern slot mapped straight from ROM)
    index: int           # tile number within the domain (see `group` for how the hardware names it)
    addresses: list      # domain byte index of each stored byte
    format: str
    stored: bytes
    pixels: list         # 64 color indices
    sources: list        # per stored byte: {'offset', 'kind', 'weak', 'pc'} or None
    status: str = ''     # 'rom', 'code', 'derived', 'unknown'
    layout: str = ''     # for 'rom': 'plain' (consecutive ROM bytes) or 'scattered' (packed stream literals, shared bytes)
    group: str = ''
    notes: list = field(default_factory=list)

    @property
    def editable(self) -> bool:
        return self.status in ('rom', 'code')

    @property
    def blank(self) -> bool:
        return len(set(self.stored)) == 1

    def to_dict(self) -> dict:
        return {'system': self.system, 'domain': self.domain, 'index': self.index, 'addresses': list(self.addresses),
                'format': self.format, 'stored': self.stored.hex(), 'pixels': list(self.pixels),
                'sources': self.sources, 'status': self.status, 'layout': self.layout, 'group': self.group,
                'editable': self.editable, 'notes': list(self.notes)}


def _make_tile(system, d, domain, index, addresses, fmt, group) -> Tile:
    stored = bytes(d.data[a] for a in addresses)
    sources = [_source(d, a) for a in addresses]
    status = _status(sources)
    three = False
    if fmt == 'snes-4bpp' and status in ('derived', 'unknown') and not any(stored[17::2]):
        # Stored in the ROM with 3 bits per pixel: the game writes 24 ROM bytes and fills the fourth plane with zeros.
        kept = sources[:16] + sources[16::2]
        if _status(kept) in ('rom', 'code'):
            status, three = _status(kept), True
    tile = Tile(system, domain, index, list(addresses), fmt, stored, decode_tile(stored, fmt), sources, status, '', group)
    if three:
        tile.notes.append('The ROM stores this tile with 8 colors (3 bits per pixel); colors 8-15 cannot be used in it.')
    if status in ('rom', 'code'):
        offs = [s['offset'] for s in (sources[:16] + sources[16::2] if three else sources)]
        plain = all(b - a == 1 for a, b in zip(offs, offs[1:]))
        tile.layout = 'plain' if plain else 'scattered'
        if len(set(offs)) < len(offs):
            tile.notes.append('Some bytes of this tile come from the same ROM byte (run-length or packed data); '
                              'they can only change together.')
        elif not plain:
            tile.notes.append('The bytes of this tile are not consecutive in the ROM (packed data or separate loads).')
        if any(s and s['weak'] for s in sources):
            tile.notes.append('Some stored values are 00 or FF, so their source match needs the replay check.')
    elif status == 'derived':
        tile.notes.append('The game computes or unpacks this tile; use plan_derived_tile_edit.')
    return tile


def tiles(scene: Scene, system: str, rom: bytes | None = None, fmt: str | None = None, chr_bases: dict | None = None) -> list[Tile]:
    """Every tile slot the video hardware holds in this scene.

    NES games with CHR-ROM keep no tile copy in RAM: the pattern slots map
    ROM directly, so `rom` is needed to read them. `fmt` overrides the tile
    format (SNES video memory holds 2, 4 and 8 bpp tiles side by side; the
    default lists it as 4bpp, and layers() names the format each layer uses).
    """
    doms = scene.snapshot.domains
    fmt = fmt or SYSTEM_TILE_FORMAT[system]
    size = TILE_FORMATS[fmt][1]
    out: list[Tile] = []
    if system in ('gb', 'gbc'):
        d = doms.get('vram')
        if d is None or d.data is None:
            return out
        for bank in (0, 1):
            base = bank * 0x2000
            if bank and not any(d.tags[base:base + 0x1800]):
                continue  # second bank never written: a Game Boy (not Color) game
            for n in range(384):
                a = base + n * 16
                out.append(_make_tile(system, d, 'vram', bank * 384 + n, range(a, a + 16), fmt,
                                      f'bank {bank} ' + ('$8000' if n < 128 else '$8800' if n < 256 else '$9000')))
        return out
    if system == 'nes':
        d = doms.get('chr')
        if d is not None and d.data is not None:
            for n in range(len(d.data) // 16):
                out.append(_make_tile(system, d, 'chr', n, range(n * 16, n * 16 + 16), fmt,
                                      f'pattern table ${(n // 256 % 2) * 0x1000:04X}'))
            return out
        m = doms.get('chr_map')
        if m is None or rom is None:
            return out
        skip = rom_skip(rom, system)
        for slot in range(min(8, len(m.tags))):
            t = m.tags[slot]
            if tag_kind(t) != pv.RT_ROM:
                continue
            base = tag_offset(t)
            shown = None if chr_bases is None else chr_bases.get(slot)
            if shown is not None and shown != base:      # the bank the screen was drawn from (scene_graphics works it out)
                base = shown
            for k in range(64):
                o = base + k * 16
                raw = rom[skip + o:skip + o + 16]
                if len(raw) < 16:
                    break
                n = slot * 64 + k
                sources = [{'offset': o + j, 'kind': 'rom', 'weak': False, 'pc': m.pcs[slot]} for j in range(16)]
                out.append(Tile(system, 'chr_rom', n, list(range(n * 16, n * 16 + 16)), fmt, bytes(raw),
                                decode_tile(bytes(raw), fmt), sources, 'rom', 'plain',
                                f'pattern table ${(slot // 4) * 0x1000:04X}',
                                ['The picture chip reads this tile straight from the ROM.'] +
                                (['The game switches picture banks while the screen is drawn. This is the bank the recorded '
                                  'screen shows.'] if shown is not None and shown == base and shown != tag_offset(t) else [])))
        return out
    d = doms.get('vram')
    if d is None or d.data is None:
        return out
    if fmt == 'snes-mode7':
        for n in range(256):
            out.append(_make_tile(system, d, 'vram', n, range(n * 128 + 1, n * 128 + 129, 2), fmt, 'mode 7'))
        return out
    for n in range(len(d.data) // size):
        out.append(_make_tile(system, d, 'vram', n, range(n * size, n * size + size), fmt, ''))
    return out


def tile_at(scene: Scene, system: str, address: int, fmt: str | None = None, domain: str = 'vram') -> Tile:
    """The tile whose first byte is at `address` in the domain."""
    fmt = fmt or SYSTEM_TILE_FORMAT[system]
    size = TILE_FORMATS[fmt][1]
    d = scene.snapshot.domains[domain]
    if system in ('gb', 'gbc'):
        index = (address >> 13) * 384 + (address & 0x1FFF) // 16
    else:
        index = address // size
    return _make_tile(system, d, domain, index, range(address, address + size), fmt, '')


@dataclass
class MapCell:
    system: str
    domain: str
    layer: str
    x: int
    y: int
    addresses: list      # domain byte index of each stored byte
    stored: bytes
    tile: int            # tile number as the layer counts it
    tile_address: int    # first byte of that tile in the tile domain (-1 when not known)
    hflip: bool = False
    vflip: bool = False
    palette: int = 0
    priority: bool = False
    sources: list = field(default_factory=list)
    status: str = ''
    notes: list = field(default_factory=list)

    @property
    def editable(self) -> bool:
        return self.status in ('rom', 'code')

    def to_dict(self) -> dict:
        return {'system': self.system, 'domain': self.domain, 'layer': self.layer, 'x': self.x, 'y': self.y,
                'addresses': list(self.addresses), 'stored': self.stored.hex(), 'tile': self.tile,
                'tile_address': self.tile_address, 'hflip': self.hflip, 'vflip': self.vflip, 'palette': self.palette,
                'priority': self.priority, 'sources': self.sources, 'status': self.status,
                'editable': self.editable, 'notes': list(self.notes)}


@dataclass
class Layer:
    system: str
    name: str
    width: int           # cells
    height: int
    tile_format: str
    tile_domain: str
    cells: list          # MapCell, row by row
    layout_source: str   # 'registers' (read from the engine), 'inferred' or 'assumed'
    scroll_x: int = 0
    scroll_y: int = 0
    notes: list = field(default_factory=list)
    shown: bool | None = None    # False when the registers say the chip does not draw this layer now; None when not known

    def cell(self, x: int, y: int) -> MapCell:
        return self.cells[y * self.width + x]

    def status_counts(self) -> dict:
        out = {'rom': 0, 'code': 0, 'derived': 0, 'unknown': 0}
        for c in self.cells:
            out[c.status] += 1
        return out

    def to_dict(self) -> dict:
        return {'system': self.system, 'name': self.name, 'width': self.width, 'height': self.height,
                'tile_format': self.tile_format, 'tile_domain': self.tile_domain, 'layout_source': self.layout_source,
                'scroll_x': self.scroll_x, 'scroll_y': self.scroll_y, 'notes': list(self.notes), 'shown': self.shown,
                'cells': [c.to_dict() for c in self.cells]}


def capture_video(session, system: str) -> dict | None:
    """Video registers the layout depends on, read from a live engine.

    Returns None when this engine build does not expose them; layers() then
    infers what it can and says so in Layer.layout_source.

    Game Boy / Gambatte: the object-memory domain points at the start of the
    engine's $FE00-$FFFF block, so the I/O registers sit 0x100 bytes after it.
    """
    lib = session.lib
    core = Path(getattr(session.fe, 'core_path', '')).name.lower()
    if system in ('gb', 'gbc') and 'gambatte' in core:
        for i in range(lib.romancer_trace_domain_count()):
            d = lib.romancer_trace_domain(i).contents
            if d.name == b'oam' and d.data:
                io = ctypes.string_at(ctypes.addressof(d.data.contents) + 0x100, 0x80)
                return {'system': system, 'source': 'registers', 'lcdc': io[0x40], 'scy': io[0x42], 'scx': io[0x43],
                        'wy': io[0x4A], 'wx': io[0x4B]}
    if system in ('gb', 'gbc') and 'mgba' in core:
        # mGBA Game Boy savestates are a fixed structure (gb/serialize.h): a version word whose upper half is
        # $0040, and the I/O registers $FF00-$FF7F at offset $300.
        state = session.fe.serialize()
        if len(state) >= 0x380 and int.from_bytes(state[0:4], 'little') >> 16 == 0x0040:
            io = state[0x300:0x380]
            return {'system': system, 'source': 'savestate', 'lcdc': io[0x40], 'scy': io[0x42], 'scx': io[0x43],
                    'wy': io[0x4A], 'wx': io[0x4B]}
    if system == 'nes':
        # FCEUmm savestates are tagged chunks; "PPUR" holds PPUCTRL, PPUMASK, PPUSTATUS, OAMADDR.
        state = session.fe.serialize()
        at = state.find(b'PPUR\x04\x00\x00\x00')
        if at >= 0:
            return {'system': system, 'source': 'savestate', 'ppuctrl': state[at + 8], 'ppumask': state[at + 9]}
    if system == 'snes' and 'bsnes' in core and 'balanced' in core:
        # bsnes-mercury (balanced PPU) savestates are a fixed sequence: video memory, object memory,
        # palette, then the PPU registers (sfc/alt/ppu-balanced/serialization.cpp).
        vram = cgram = None
        for i in range(lib.romancer_trace_domain_count()):
            d = lib.romancer_trace_domain(i).contents
            if d.name == b'vram' and d.data:
                vram = ctypes.string_at(d.data, d.size)
            if d.name == b'palette' and d.data:
                cgram = ctypes.string_at(d.data, d.size)
        state = session.fe.serialize()
        at = state.find(vram) if vram else -1
        # the engine keeps 128 KB for video memory (64 KB used), then 544 bytes of objects, then the palette
        r = next((at + gap + 512 for gap in (0x20220, 0x10220)
                  if at >= 0 and cgram and state[at + gap:at + gap + 512] == cgram), -1)
        if r >= 0:

            def u16(o, n=1):
                return [state[r + o + 2 * k] | state[r + o + 2 * k + 1] << 8 for k in range(n)]
            mode = state[r + 51]
            if mode <= 7:
                video = {'system': system, 'source': 'savestate', 'bg_mode': mode, 'bg3_priority': state[r + 50],
                         'bg_tilesize': list(state[r + 46:r + 50]), 'bg_scaddr': u16(59, 4),
                         'bg_scsize': list(state[r + 67:r + 71]), 'bg_tdaddr': u16(71, 4), 'bg_hofs': u16(84, 4),
                         'bg_vofs': u16(92, 4), 'oam_tdaddr': u16(37)[0], 'oam_nameselect': state[r + 36],
                         'display_disabled': state[r + 33]}
                # Which layers the main and the sub screen draw ($212C/$212D): five flags each, BG1-BG4 and objects.
                enabled = state[r + 158:r + 168]
                if len(enabled) == 10 and all(v in (0, 1) for v in enabled):
                    video['bg_enabled'], video['bgsub_enabled'] = list(enabled[:5]), list(enabled[5:])
                return video
    if system in ('genesis', 'sms', 'gg') and 'blastem' in core:
        video = blastem_video(session.fe.serialize(), system)
        if video:
            return video
    return None


_BLASTEM_VDP_SECTION = 3


def blastem_video(state: bytes, system: str) -> dict | None:
    """Video chip registers from a BlastEm savestate (Mega Drive and Master System), or None.

    The libretro state is a length word followed by sections, each a
    two-byte id, a four-byte size and that many bytes (serialize.c). The
    video chip's section holds: a version byte, the video memory size in KB,
    64 KB of video memory, 64 colors and 64 scroll words of two bytes each,
    a 320-byte copy of the sprite table, registers 0-23, the address the
    next access goes to, the address of a serial transfer and the access
    code (vdp_serialize in vdp.c). All numbers are big-endian.
    """
    at = 8
    while at + 6 <= len(state):
        ident = int.from_bytes(state[at:at + 2], 'big')
        size = int.from_bytes(state[at + 2:at + 6], 'big')
        body = at + 6
        if ident > 0x40 or body + size > len(state):
            return None
        if ident == _BLASTEM_VDP_SECTION:
            r = body + 2 + 0x10000 + 128 + 128 + 320
            if state[body + 1] != 64 or r + 33 > body + size:
                return None
            regs = list(state[r:r + 24])
            if system == 'genesis' and not regs[1] & 4:      # Mega Drive games run the chip in mode 5
                return None
            return {'system': system, 'source': 'savestate', 'regs': regs,
                    'address': int.from_bytes(state[r + 24:r + 28], 'big'), 'code': state[r + 32]}
        at = body + size
    return None


def scene_from_session(session, system: str, label: str = '', inputs=None) -> Scene:
    """provenance.scene_from_session, plus the video registers as scene.video."""
    scene = pv.scene_from_session(session, label, inputs)
    scene.video = capture_video(session, system)
    return scene


def _blank_score(d, addresses_of, entries):
    """How many of the referenced tiles hold a picture (used to infer a layout)."""
    score = 0
    for n in set(entries):
        a = addresses_of(n)
        chunk = d.data[a:a + 16]
        score += len(set(chunk)) > 1
    return score


def _cell(system, d, layer, x, y, addresses, **kw) -> MapCell:
    sources = [_source(d, a) for a in addresses]
    c = MapCell(system, d.name, layer, x, y, list(addresses), bytes(d.data[a] for a in addresses),
                sources=sources, status=_status(sources), **kw)
    if any(s and s['weak'] for s in sources):
        c.notes.append('Stored value is 00 or FF, so the source match needs the replay check.')
    return c


def _gb_layers(scene, system, video):
    d = scene.snapshot.domains.get('vram')
    if d is None or d.data is None:
        return []
    cgb = any(d.tags[0x2000 + 0x1800:0x4000])
    if video:
        lcdc, source = video['lcdc'], 'registers'
        choices = [('background', 0x1C00 if lcdc & 8 else 0x1800, bool(lcdc & 0x10))]
        if lcdc & 0x20:
            choices.append(('window', 0x1C00 if lcdc & 0x40 else 0x1800, bool(lcdc & 0x10)))
    else:
        source = 'inferred'
        best = None
        for base in (0x1800, 0x1C00):
            for unsigned in (True, False):
                entries = d.data[base:base + 0x400]
                score = _blank_score(d, lambda n: (n if unsigned or n >= 128 else 256 + n) * 16, entries)
                if best is None or score > best[0]:
                    best = (score, base, unsigned)
        choices = [('background', best[1], best[2])]
    out = []
    for name, base, unsigned in choices:
        cells = []
        for y in range(32):
            for x in range(32):
                a = base + y * 32 + x
                n = d.data[a]
                attr = d.data[a + 0x2000] if cgb else 0
                tile = n if unsigned or n >= 128 else 256 + n
                bank = attr >> 3 & 1
                cells.append(_cell(system, d, name, x, y, [a, a + 0x2000] if cgb else [a], tile=tile + bank * 384,
                                   tile_address=bank * 0x2000 + tile * 16, hflip=bool(attr & 0x20), vflip=bool(attr & 0x40),
                                   palette=attr & 7, priority=bool(attr & 0x80)))
        layer = Layer(system, name, 32, 32, 'gb-2bpp', 'vram', cells, source)
        if video:
            if name == 'background':
                layer.scroll_x, layer.scroll_y = video['scx'], video['scy']
            else:
                layer.scroll_x, layer.scroll_y = 7 - video['wx'], -video['wy']
                layer.shown = video['wy'] < 144 and video['wx'] < 167      # switched on, but parked off the screen
                if not layer.shown:
                    layer.notes.append('The window is switched on but placed off the screen at this moment.')
        else:
            layer.notes.append('Which map and tile block are on screen was inferred from the tiles they use.')
        out.append(layer)
    return out


def _nes_layers(scene, system, video):
    doms = scene.snapshot.domains
    d = doms.get('vram')
    if d is None or d.data is None:
        return []
    chr_d = doms.get('chr')
    tile_domain = 'chr' if chr_d is not None and chr_d.data is not None else 'chr_rom'
    if video:
        table, source = (1 if video['ppuctrl'] & 0x10 else 0), 'registers'
    elif tile_domain == 'chr':
        entries = d.data[:0x3C0]
        scores = [_blank_score(chr_d, lambda n, t=t: (t * 256 + n) * 16, entries) for t in (0, 1)]
        table, source = (1 if scores[1] > scores[0] else 0), 'inferred'
    else:
        table, source = 0, 'assumed'
    out = []
    tables = [('nametable 0', d, 0), ('nametable 1', d, 0x400)]
    extra = doms.get('vram4')
    if extra is not None and extra.data is not None:
        tables += [('nametable 2', extra, 0), ('nametable 3', extra, 0x400)]
    for name, dom, base in tables:
        cells = []
        for y in range(30):
            for x in range(32):
                a = base + y * 32 + x
                attr_a = base + 0x3C0 + (y // 4) * 8 + x // 4
                shift = ((y // 2) & 1) * 4 + ((x // 2) & 1) * 2
                n = dom.data[a]
                c = _cell(system, dom, name, x, y, [a, attr_a], tile=table * 256 + n,
                          tile_address=(table * 256 + n) * 16, palette=dom.data[attr_a] >> shift & 3)
                c.notes.append('The second stored byte is the attribute byte; it holds the palettes of a 4x4 cell block.')
                cells.append(c)
        layer = Layer(system, name, 32, 30, 'nes-2bpp', tile_domain, cells, source)
        if video:
            layer.scroll_x = (video['ppuctrl'] & 1) * 256
            layer.scroll_y = (video['ppuctrl'] >> 1 & 1) * 240
        if source != 'registers':
            layer.notes.append('Which pattern table the background uses was not read from the engine.')
        out.append(layer)
    return out


_SNES_MODE_BPP = {0: (2, 2, 2, 2), 1: (4, 4, 2), 2: (4, 4), 3: (8, 4), 4: (8, 2), 5: (4, 2), 6: (4,), 7: (8,)}


def _snes_layers(scene, system, video):
    d = scene.snapshot.domains.get('vram')
    if d is None or d.data is None or not video:
        return []  # the map position, size and depth are all register state on this system
    mode = video['bg_mode'] & 7
    out = []
    if mode == 7:
        cells = []
        for y in range(128):
            for x in range(128):
                a = (y * 128 + x) * 2
                n = d.data[a]
                cells.append(_cell(system, d, 'mode 7', x, y, [a], tile=n, tile_address=n * 128 + 1))
        return [Layer(system, 'mode 7', 128, 128, 'snes-mode7', 'vram', cells, 'registers')]
    for k, bpp in enumerate(_SNES_MODE_BPP[mode]):
        base = video['bg_scaddr'][k] & 0xFFFF
        wide, tall = bool(video['bg_scsize'][k] & 1), bool(video['bg_scsize'][k] & 2)
        chars = video['bg_tdaddr'][k] & 0xFFFF
        w, h = (64 if wide else 32), (64 if tall else 32)
        fmt = f'snes-{bpp}bpp'
        cells = []
        for y in range(h):
            for x in range(w):
                screen = (x >= 32) + (y >= 32) * (2 if wide else 1)
                a = (base + screen * 0x800 + ((y & 31) * 32 + (x & 31)) * 2) & 0xFFFF
                e = d.data[a] | d.data[(a + 1) & 0xFFFF] << 8
                cells.append(_cell(system, d, f'BG{k + 1}', x, y, [a, (a + 1) & 0xFFFF], tile=e & 0x3FF,
                                   tile_address=(chars + (e & 0x3FF) * 8 * bpp) & 0xFFFF, hflip=bool(e & 0x4000),
                                   vflip=bool(e & 0x8000), palette=e >> 10 & 7, priority=bool(e & 0x2000)))
        layer = Layer(system, f'BG{k + 1}', w, h, fmt, 'vram', cells, 'registers')
        layer.scroll_x, layer.scroll_y = video['bg_hofs'][k], video['bg_vofs'][k]
        if 'bg_enabled' in video:
            layer.shown = bool(video['bg_enabled'][k] or video['bgsub_enabled'][k])
            if not layer.shown:
                layer.notes.append('The game has this layer switched off at this moment.')
        if video['bg_tilesize'][k]:
            layer.notes.append('This layer draws 16x16 tiles: each cell also shows the three tiles after it.')
        out.append(layer)
    return out


def _genesis_layers(scene, system, video):
    d = scene.snapshot.domains.get('vram')
    if d is None or d.data is None:
        return []
    if video:
        regs, source = video['regs'], 'registers'
        a_base, b_base, w_base = (regs[2] & 0x38) << 10, (regs[4] & 7) << 13, (regs[3] & 0x3E) << 10
        w = {0: 32, 1: 64, 3: 128}.get(regs[16] & 3, 32)
        h = {0: 32, 1: 64, 3: 128}.get(regs[16] >> 4 & 3, 32)
        planes = [('plane A', a_base, w, h), ('plane B', b_base, w, h),
                  ('window', w_base & (0xF000 if regs[12] & 1 else 0xF800), 64 if regs[12] & 1 else 32, 32)]
    else:
        source = 'assumed'
        planes = [('plane A', 0xC000, 64, 32), ('plane B', 0xE000, 64, 32)]
    out = []
    for name, base, w, h in planes:
        cells = []
        for y in range(h):
            for x in range(w):
                a = (base + (y * w + x) * 2) & 0xFFFF
                e = d.data[a] << 8 | d.data[(a + 1) & 0xFFFF]
                cells.append(_cell(system, d, name, x, y, [a, (a + 1) & 0xFFFF], tile=e & 0x7FF,
                                   tile_address=(e & 0x7FF) * 32, hflip=bool(e & 0x800), vflip=bool(e & 0x1000),
                                   palette=e >> 13 & 3, priority=bool(e & 0x8000)))
        layer = Layer(system, name, w, h, 'genesis-4bpp', 'vram', cells, source)
        if not video:
            layer.notes.append('Plane position and size are the common defaults, not read from the engine.')
        elif name == 'window':
            # The window replaces plane A left or right of a column and above or below a row (registers 17 and 18);
            # with both at zero it covers nothing, and its table address may point at anything.
            layer.shown = bool(regs[17] & 0x9F or regs[18] & 0x9F)
            if not layer.shown:
                layer.notes.append('The game does not show the window plane at this moment.')
        else:
            layer.shown = True
        out.append(layer)
    return out


def _sms_layers(scene, system, video):
    d = scene.snapshot.domains.get('vram')
    if d is None or d.data is None:
        return []
    base = ((video['regs'][2] & 0x0E) << 10) if video else 0x3800
    cells = []
    for y in range(28):
        for x in range(32):
            a = (base + (y * 32 + x) * 2) & 0x3FFF
            e = d.data[a] | d.data[(a + 1) & 0x3FFF] << 8
            cells.append(_cell(system, d, 'background', x, y, [a, (a + 1) & 0x3FFF], tile=e & 0x1FF,
                               tile_address=(e & 0x1FF) * 32, hflip=bool(e & 0x200), vflip=bool(e & 0x400),
                               palette=e >> 11 & 1, priority=bool(e & 0x1000)))
    layer = Layer(system, 'background', 32, 28, 'sms-4bpp', 'vram', cells, 'registers' if video else 'assumed')
    if video:
        layer.scroll_x, layer.scroll_y = (-video['regs'][8]) & 0xFF, video['regs'][9]
    else:
        layer.notes.append('The name table position is the usual $3800, not read from the engine.')
    return [layer]


_LAYERS = {'gb': _gb_layers, 'gbc': _gb_layers, 'nes': _nes_layers, 'snes': _snes_layers,
           'genesis': _genesis_layers, 'sms': _sms_layers, 'gg': _sms_layers}


def layers(scene: Scene, system: str, video: dict | None = None) -> list[Layer]:
    """Background maps of the scene: for each cell, the tile, flips and palette it shows.

    `video` (or scene.video, set by scene_from_session) holds the registers
    that place the maps. Without it the layout is inferred or assumed and
    each Layer says so. SNES needs the registers and returns [] without them.
    """
    video = video if video is not None else getattr(scene, 'video', None)
    return _LAYERS[system](scene, system, video)


def used_tile_addresses(scene: Scene, system: str, video: dict | None = None) -> set[int]:
    """First-byte addresses of tiles that a background cell or a sprite refers to."""
    used = set()
    for layer in layers(scene, system, video):
        for c in layer.cells:
            used.add(c.tile_address)
    doms = scene.snapshot.domains
    oam = doms.get('oam')
    video = video if video is not None else getattr(scene, 'video', None)
    if oam is not None and oam.data is not None:
        o = oam.data
        if system in ('gb', 'gbc'):
            tall = bool(video and video['lcdc'] & 4)
            for i in range(0, 0xA0, 4):
                if 0 < o[i] < 160:
                    n = o[i + 2] & (0xFE if tall else 0xFF)
                    bank = (o[i + 3] >> 3 & 1) if system == 'gbc' else 0
                    used.add(bank * 0x2000 + n * 16)
                    if tall:
                        used.add(bank * 0x2000 + (n + 1) * 16)
        elif system == 'nes':
            table = 1 if video and video['ppuctrl'] & 8 else 0
            for i in range(0, 0x100, 4):
                if o[i] < 0xEF:
                    used.add((table * 256 + o[i + 1]) * 16)
        elif system == 'snes' and video:
            base = video['oam_tdaddr']
            for i in range(0, 0x200, 4):
                n = o[i + 2]
                high = (0x2000 + (video['oam_nameselect'] << 13)) if o[i + 3] & 1 else 0
                used.add((base + high + n * 32) & 0xFFFF)
    vram = doms.get('vram')
    if video and 'regs' in video and vram is not None and vram.data is not None:
        # Sega systems keep the sprite table in video memory; the registers say where.
        regs, v = video['regs'], vram.data
        if system == 'genesis':
            table = (regs[5] & (0x7E if regs[12] & 1 else 0x7F)) << 9
            link = 0
            for _ in range(80):
                a = (table + link * 8) & 0xFFFF
                if a + 8 > len(v):
                    break
                wide, tall = (v[a + 2] >> 2 & 3) + 1, (v[a + 2] & 3) + 1
                first = (v[a + 4] << 8 | v[a + 5]) & 0x7FF
                y, x = (v[a] << 8 | v[a + 1]) & 0x3FF, (v[a + 6] << 8 | v[a + 7]) & 0x1FF
                if 128 - 32 < y < 128 + 240 and 128 - 32 < x < 128 + 320:
                    for k in range(wide * tall):
                        used.add(((first + k) & 0x7FF) * 32)
                link = v[a + 3] & 0x7F
                if not link:
                    break
        elif len(v) >= 0x4000:
            table = (regs[5] & 0x7E) << 7
            high = 0x2000 if regs[6] & 4 else 0
            tall = bool(regs[1] & 2)
            for i in range(64):
                y = v[(table + i) & 0x3FFF]
                if y == 0xD0 and not regs[1] & 0x10:
                    break
                n = v[(table + 0x81 + i * 2) & 0x3FFF] & (0xFE if tall else 0xFF)
                if y < 0xC0 or y > 0xF0:
                    used.add(high + n * 32)
                    if tall:
                        used.add(high + (n + 1) * 32)
    return used


# ---------------------------------------------------------------------------
# 3. Direct edits: bytes that are ROM bytes
# ---------------------------------------------------------------------------

def _direct_writes(stored, new, sources, rom, skip, what):
    writes: dict[int, tuple[int, int]] = {}
    for k, src in enumerate(sources):
        if new[k] == stored[k]:
            continue
        if not src or src['kind'] not in ('rom', 'code'):
            raise ValueError(f'This {what} is computed by the game; it cannot be written in place.')
        off = src['offset'] + skip
        if off >= len(rom) or rom[off] != stored[k]:
            raise ValueError(f'ROM byte at the traced source differs from the stored {what}; take a new scene.')
        if off in writes and writes[off][1] != new[k]:
            raise ValueError(f'Two bytes of this {what} come from one ROM byte and would need different values; '
                             'the data is packed, so it has to be re-encoded.')
        writes[off] = (rom[off], new[k])
    # A ROM byte shared with an unchanged byte of the same item would change that one too.
    for k, src in enumerate(sources):
        if new[k] == stored[k] and src and src['offset'] + skip in writes:
            raise ValueError(f'A ROM byte behind this {what} also feeds a byte that must stay; '
                             'the data is packed, so it has to be re-encoded.')
    return [(o, a, b) for o, (a, b) in sorted(writes.items())]


def plan_tile_edit(tile: Tile, pixels, rom: bytes, skip: int | None = None) -> list[tuple[int, int, int]]:
    """ROM writes [(file offset, old, new)] that turn this tile into `pixels`.

    Works for tiles whose changed bytes trace to ROM data or code values.
    Raises ValueError when the tile is computed, when the ROM no longer
    matches the scene, or when packed data would need re-encoding
    (plan_derived_tile_edit handles those).
    """
    new = encode_tile(pixels, tile.format)
    skip = rom_skip(rom, tile.system) if skip is None else skip
    return _direct_writes(tile.stored, new, tile.sources, rom, skip, 'tile')


def plan_tilemap_edit(cell: MapCell, rom: bytes, *, tile: int | None = None, hflip: bool | None = None,
                      vflip: bool | None = None, palette: int | None = None, priority: bool | None = None,
                      skip: int | None = None) -> list[tuple[int, int, int]]:
    """ROM writes that change what one background cell shows.

    `tile` is the hardware tile number stored in the cell (0-255 on Game Boy
    and NES, wider elsewhere). Fields left as None keep their value.
    """
    new = bytearray(cell.stored)
    s = cell.system
    if s in ('gb', 'gbc'):
        if tile is not None:
            new[0] = tile & 0xFF
        if len(new) > 1:
            a = new[1]
            if tile is not None and tile > 0xFF:
                raise ValueError('Game Boy cells hold tile numbers 0-255; the bank is a separate bit.')
            if hflip is not None: a = a & ~0x20 | (0x20 if hflip else 0)
            if vflip is not None: a = a & ~0x40 | (0x40 if vflip else 0)
            if palette is not None: a = a & ~7 | (palette & 7)
            if priority is not None: a = a & ~0x80 | (0x80 if priority else 0)
            new[1] = a
        elif any(v is not None for v in (hflip, vflip, palette, priority)):
            raise ValueError('Game Boy (not Color) cells hold only a tile number.')
    elif s == 'nes':
        if tile is not None:
            new[0] = tile & 0xFF
        if palette is not None:
            shift = ((cell.y // 2) & 1) * 4 + ((cell.x // 2) & 1) * 2
            new[1] = new[1] & ~(3 << shift) | (palette & 3) << shift
        if hflip or vflip or priority:
            raise ValueError('NES background cells cannot flip.')
    elif len(new) == 1:
        # Super NES mode 7: one byte per cell, a tile number and nothing else
        if tile is not None:
            if not 0 <= tile <= 0xFF:
                raise ValueError('tile number is out of range for this layer')
            new[0] = tile
        if any(v is not None for v in (hflip, vflip, palette, priority)):
            raise ValueError('Mode 7 cells hold only a tile number.')
    else:
        big = s == 'genesis'
        e = (new[0] << 8 | new[1]) if big else (new[0] | new[1] << 8)
        tile_mask, h, v, pal_shift, pal_mask, pri = {
            'snes': (0x3FF, 0x4000, 0x8000, 10, 7, 0x2000),
            'genesis': (0x7FF, 0x0800, 0x1000, 13, 3, 0x8000),
        }.get(s, (0x1FF, 0x0200, 0x0400, 11, 1, 0x1000))
        if tile is not None:
            if not 0 <= tile <= tile_mask:
                raise ValueError('tile number is out of range for this system')
            e = e & ~tile_mask | tile
        if hflip is not None: e = e & ~h | (h if hflip else 0)
        if vflip is not None: e = e & ~v | (v if vflip else 0)
        if palette is not None: e = e & ~(pal_mask << pal_shift) | (palette & pal_mask) << pal_shift
        if priority is not None: e = e & ~pri | (pri if priority else 0)
        new[0], new[1] = (e >> 8, e & 0xFF) if big else (e & 0xFF, e >> 8)
    skip = rom_skip(rom, s) if skip is None else skip
    return _direct_writes(cell.stored, bytes(new), cell.sources, rom, skip, 'map cell')


def predicted_effects(scene: Scene, writes, skip: int = 0, domains=('vram', 'chr', 'palette', 'oam', 'vram4')) -> dict:
    """{domain: [indices]} of scene bytes whose tag names a written ROM byte.

    This is the tag-level prediction (a claim); verify_plan measures it.
    """
    offsets = {o - skip for o, _, _ in writes}
    out = {}
    for name in domains:
        d = scene.snapshot.domains.get(name)
        if d is None:
            continue
        hit = [i for i, t in enumerate(d.tags) if tag_kind(t) in (1, 2) and tag_offset(t) in offsets]
        if hit:
            out[name] = hit
    return out


def impact(index: pv.ImpactIndex, writes, skip: int = 0) -> dict:
    """{scene id: sorted domain names} for every known scene that uses a written byte."""
    out: dict[str, set] = {}
    for o, _, _ in writes:
        for scene_id, names in index.users(o - skip, o - skip + 1).items():
            out.setdefault(scene_id, set()).update(names)
    return {k: sorted(v) for k, v in out.items()}


# ---------------------------------------------------------------------------
# Plans and the causal check
# ---------------------------------------------------------------------------

@dataclass
class EditPlan:
    kind: str                      # 'direct', 'reencode', 'relocate', 'overlay', 'private-copy'
    writes: list                   # [(file offset, old or None past the old end, new)]
    rom_size: int                  # file size after the edit
    expect: dict = field(default_factory=dict)   # {domain: {index: value}} the scene should then hold
    notes: list = field(default_factory=list)
    details: dict = field(default_factory=dict)
    verified: dict | None = None   # verify_plan result, once run

    def apply(self, rom: bytes) -> bytes:
        return apply_writes(rom, self.writes, self.rom_size)

    def to_dict(self) -> dict:
        return {'kind': self.kind, 'writes': [list(w) for w in self.writes], 'rom_size': self.rom_size,
                'expect': {d: {str(i): v for i, v in m.items()} for d, m in self.expect.items()},
                'notes': list(self.notes), 'details': self.details,
                'verified': None if self.verified is None else {k: v for k, v in self.verified.items() if k != 'changed'}}


def apply_writes(rom: bytes, writes, size: int | None = None) -> bytes:
    out = bytearray(rom)
    if size and size > len(out):
        out += b'\xFF' * (size - len(out))
    for o, old, new in writes:
        if old is not None and o < len(rom) and rom[o] != old:
            raise ValueError(f'ROM byte at {o:#x} is not what the plan was made against.')
        out[o] = new
    return bytes(out)


def _diff_writes(before: bytes, after: bytes) -> list:
    out = [(i, before[i], after[i]) for i in range(min(len(before), len(after))) if before[i] != after[i]]
    # Past the old end only bytes that are not FF are listed: apply_writes fills a grown ROM with FF first.
    out += [(i, None, after[i]) for i in range(len(before), len(after)) if after[i] != 0xFF]
    return out


class _Tap:
    """Frontend wrapper that records final domain contents and screen when closed."""

    def __init__(self, fe, sink):
        self.__dict__['_fe'] = fe
        self.__dict__['_sink'] = sink

    def __getattr__(self, name):
        return getattr(self._fe, name)

    def __setattr__(self, name, value):
        setattr(self._fe, name, value)

    def serialize(self):
        # The replay session takes rolling checkpoints it never uses; on some engines each one is slow.
        return b''

    def close(self):
        fe = self._fe
        try:
            lib = fe.lib
            data = {}
            lib.romancer_trace_domain.restype = ctypes.POINTER(pv._Domain)
            for i in range(lib.romancer_trace_domain_count()):
                d = lib.romancer_trace_domain(i).contents
                if d.data:
                    try:
                        data[d.name.decode()] = ctypes.string_at(d.data, d.size)
                    except OSError:  # an engine that registered more bytes than it owns
                        pass
            frame = getattr(fe, 'last_frame', None)
            self._sink.append((data, frame.sha256() if frame else None))
        finally:
            fe.close()


def verify_plan(make_frontend: Callable[[bytes], object], rom: bytes, plan, scene: Scene, *, expect: dict | None = None,
                domains: Iterable[str] = ('vram', 'chr', 'vram4'), buttons_for=None) -> dict:
    """Replay `scene` with the plan applied and say whether it did what was planned.

    `plan` is an EditPlan or a write list. The result is
    provenance.verify_edit's, plus:
      as_planned  every expected byte holds its planned value (None when no
                  expectation was given: then `verified` alone says the edit
                  reaches the scene)
      missed      expected bytes that hold another value
      unplanned   {domain: count} of other bytes that changed (side effects to show)
      by          'memory' or, for tiles the picture chip reads straight from
                  ROM (NES CHR-ROM), 'screen': the replayed picture differs
                  from the scene's while an unedited replay reproduces it
                  (result['replay_is_repeatable']). Used only when the plan
                  expects no change in a memory domain.
    """
    if isinstance(plan, EditPlan):
        edited = plan.apply(rom)
        expect = plan.expect if expect is None else expect
    else:
        edited = apply_writes(rom, plan)
    sink: list = []
    if expect is not None and not any(expect.values()):
        result = {'verified': False, 'changed': {}, 'checkpoints_tried': []}   # nothing to look for in memory
    else:
        result = dict(pv.verify_edit(lambda data: _Tap(make_frontend(data), sink), rom, edited, scene,
                                     [d for d in domains if d in scene.snapshot.domains], buttons_for))
    result['by'] = 'memory'
    final = sink[-1][0] if sink else {}
    if not result['verified'] and scene.screen_sha256 and not (expect and any(expect.values())):
        # Nothing in memory changed (NES CHR-ROM is read straight from the cartridge). The edit still counts
        # when the replayed picture differs from the scene's and the same replay with the unedited ROM
        # reproduces the scene's picture exactly.
        before = [c for c in scene.checkpoints if c[0] < scene.frame]
        # A savestate can carry what the cartridge had mapped when it was made, so an edit to the picture data may
        # only show when the game is replayed from further back. Step back one savestate at a time, down to the
        # first one, until the edit shows.
        for start in reversed(before):
            short = Scene(scene.id, scene.frame, scene.screen_sha256, [start], scene.snapshot)
            shots: list = []
            for data in (edited, rom):
                pv.verify_edit(lambda d: _Tap(make_frontend(d), shots), rom, data, short, [], buttons_for)
            if len(shots) != 2 or not shots[0][1] or not shots[1][1]:
                continue
            result['replay_is_repeatable'] = shots[1][1] == scene.screen_sha256
            if result['replay_is_repeatable'] and shots[0][1] != scene.screen_sha256:
                result.update(verified=True, by='screen', screen_sha256=shots[0][1], from_frame=start[0])
                break
    missed = {}
    planned = set()
    if expect:
        for name, cells in expect.items():
            after = final.get(name)
            for i, v in cells.items():
                planned.add((name, int(i)))
                if after is None or after[int(i)] != v:
                    missed.setdefault(name, []).append(int(i))
        result['as_planned'] = result['verified'] and not missed
    else:
        result['as_planned'] = None
    result['missed'] = missed
    result['unplanned'] = {name: n for name, idx in result.get('changed', {}).items()
                           if (n := sum((name, i) not in planned for i in idx))}
    if isinstance(plan, EditPlan):
        plan.verified = result
    return result


VIDEO_DOMAINS = ('vram', 'chr', 'vram4')


def _live_domains(fe, names) -> dict:
    """{domain: bytes} read from a tracing engine right now."""
    lib = fe.lib
    lib.romancer_trace_domain.restype = ctypes.POINTER(pv._Domain)
    out = {}
    for i in range(lib.romancer_trace_domain_count()):
        d = lib.romancer_trace_domain(i).contents
        if d.name.decode() in names and d.data:
            out[d.name.decode()] = ctypes.string_at(d.data, d.size)
    return out


def verify_from_power_on(make_frontend: Callable[[bytes], object], rom: bytes, plan, scene: Scene, *, buttons_for=None,
                         slack: int = 12, domains: Iterable[str] = VIDEO_DOMAINS) -> dict:
    """Run the edited ROM from the scene's first checkpoint and look for the scene, changed only as planned.

    verify_plan replays a scene from a checkpoint shortly before it, which
    shows that an edit reaches the scene. This is the longer test: the whole
    recorded run (from power-on, when the session was recorded from there)
    with the edited ROM. It passes (`clean`) when, at some frame within
    `slack` of the scene's, every video domain equals the scene's except
    for the planned bytes holding their planned values. `slack` is there
    because an added routine costs time, so a game can reach the same
    moment a frame or two later.

    Returns {'frames', 'clean', 'at_frame', 'closest_diff'}; closest_diff is
    the smallest number of differing bytes seen. A run that is not clean
    is not proof of damage: see overlay_safety.
    """
    edited = plan.apply(rom) if isinstance(plan, EditPlan) else apply_writes(rom, plan)
    expect = plan.expect if isinstance(plan, EditPlan) else {}
    buttons_for = buttons_for or (lambda f: ())
    start, state = scene.checkpoints[0]
    want = {}
    for n in domains:
        d = scene.snapshot.domains.get(n)
        if d is None or d.data is None:
            continue
        w = bytearray(d.data)
        for i, v in expect.get(n, {}).items():
            w[int(i)] = v
        want[n] = bytes(w)
    fe = make_frontend(edited)
    best = None
    try:
        fe.unserialize(state)
        session = pv.TraceSession(fe, checkpoint_every=10 ** 9)
        session.frame = start
        session.start()
        session.run(max(0, scene.frame - start - 2), buttons_for)
        for _ in range(slack):
            got = _live_domains(fe, want)
            diff = sum(sum(a != b for a, b in zip(got.get(n, b''), want[n])) + abs(len(want[n]) - len(got.get(n, b''))) for n in want)
            if best is None or diff < best[1]:
                best = (session.frame, diff)
            if diff == 0:
                break
            session.run(1, buttons_for)
    finally:
        fe.close()
    return {'frames': scene.frame, 'clean': bool(best and best[1] == 0), 'at_frame': best[0] if best else None,
            'closest_diff': best[1] if best else None}


def overlay_safety(make_frontend: Callable[[bytes], object], rom: bytes, plan: EditPlan, scene: Scene, system: str, *,
                   edits: list | None = None, options: dict | None = None, buttons_for=None, slack: int = 12,
                   cache: dict | None = None) -> dict:
    """Does an overlay plan leave the rest of the game alone over the whole run from power-on?

    Returns {'state': ..., 'run': ..., 'hook_only': ..., 'control': ...}
    (the last two only when they had to be run). `state` is one of

    'clean'       the run from power-on reaches the scene changed only as planned.
    'timing'      it does not, but neither does a run with the bare interrupt hook (plan_hook_only) or with a
                  routine of the same cost that touches nothing (plan_overlay_control): any added code changes
                  this game's course, so the original run is no reference and nothing can be laid at the
                  overlay's door. (The scene replay, verify_plan, is then the evidence there is.)
    'disturbed'   the controls reproduce the original run (or come far closer to it than the overlay does: the
                  overlay's difference is more than four times theirs plus 64 bytes), so the overlay's own
                  video access changes something else in this game.
    'differs'     the bare hook reproduces the original run and the overlay does not, on a processor for which
                  no cost-matched control exists: the cause is the routine's time or its video access, and
                  this measurement cannot say which.
    'unmeasured'  a control could not be built.

    `edits` and `options` are what plan_overlay_patch was called with; they
    are needed for the cost-matched control (Super NES and Mega Drive).
    `cache` (a dict the caller keeps per ROM) saves repeating the hook-only
    run for several plans.
    """
    options = dict(options or {})
    run = verify_from_power_on(make_frontend, rom, plan, scene, buttons_for=buttons_for, slack=slack)
    out = {'state': 'clean', 'run': run}
    if run['clean']:
        return out
    cache = cache if cache is not None else {}
    hook = options.get('hook', 'nmi')
    if ('hook', hook) not in cache:
        try:
            cache['hook', hook] = verify_from_power_on(make_frontend, rom, plan_hook_only(rom, system, hook=hook), scene,
                                                       buttons_for=buttons_for, slack=slack)
        except ValueError as e:
            cache['hook', hook] = {'error': str(e)}
    out['hook_only'] = cache['hook', hook]
    if 'error' in out['hook_only']:
        out['state'] = 'unmeasured'
        return out
    reference = out['hook_only']['closest_diff']
    if out['hook_only']['clean'] and not (edits and CPU[system] in ('65816', '68000', 'sm83')):
        out['state'] = 'differs'
        return out
    if out['hook_only']['clean']:
        control = {}
        for cost in ('low', 'high'):
            try:
                c = plan_overlay_control(edits, rom, system, cost=cost,
                                         **{k: v for k, v in options.items() if k in ('after_handler', 'guard', 'hook', 'grow')})
                control[cost] = verify_from_power_on(make_frontend, rom, c, scene, buttons_for=buttons_for, slack=slack)
            except ValueError as e:
                control[cost] = {'error': str(e)}
        out['control'] = control
        diffs = [c['closest_diff'] for c in control.values() if 'error' not in c]
        if diffs:
            reference = max(diffs)
    out['state'] = 'disturbed' if run['closest_diff'] > 4 * reference + 64 else 'timing'
    return out


def with_checksums(rom: bytes, writes, system: str) -> list:
    """`writes` plus the header-checksum writes they make necessary.

    plan_tile_edit and plan_tilemap_edit return only the data bytes, as
    palette_trace.plan_color_edit does. A saved ROM also needs its header
    checksum brought up to date where the cartridge carries a valid one
    (some games refuse to start otherwise); EditPlan-returning functions
    already include that.
    """
    fixed = fix_checksums(apply_writes(rom, writes), rom, system)
    return _diff_writes(rom, fixed)


def expect_for(item, new_stored: bytes) -> dict:
    """{domain: {index: value}} for a Tile or MapCell taking `new_stored`."""
    if item.domain == 'chr_rom':
        return {}
    return {item.domain: {a: new_stored[k] for k, a in enumerate(item.addresses) if new_stored[k] != item.stored[k]}}


# ---------------------------------------------------------------------------
# Checksums, free space and pointers (shared by relocation and the overlay)
# ---------------------------------------------------------------------------

def fix_checksums(rom: bytes, original: bytes, system: str) -> bytes:
    """Recompute header checksums in `rom`, but only those that were valid in `original`."""
    out = bytearray(rom)
    if system in ('gb', 'gbc') and len(out) >= 0x150:
        def head(b):
            x = 0
            for i in range(0x134, 0x14D):
                x = (x - b[i] - 1) & 0xFF
            return x

        def total(b):
            return (sum(b) - b[0x14E] - b[0x14F]) & 0xFFFF
        if original[0x14D] == head(original):
            out[0x14D] = head(out)
        if original[0x14E] << 8 | original[0x14F] == total(original):
            t = total(out)
            out[0x14E], out[0x14F] = t >> 8, t & 0xFF
    elif system == 'genesis' and len(out) >= 0x200:
        def total(b):
            end = len(b) & ~1
            return sum(b[i] << 8 | b[i + 1] for i in range(0x200, end, 2)) & 0xFFFF
        if len(out) != len(original):
            end = len(out) - 1
            out[0x1A4:0x1A8] = end.to_bytes(4, 'big')
        if original[0x18E] << 8 | original[0x18F] == total(original):
            t = total(out)
            out[0x18E], out[0x18F] = t >> 8, t & 0xFF
    elif system == 'snes':
        skip = rom_skip(bytes(out), system)
        for base in (0x7FC0, 0xFFC0, 0x40FFC0):
            h = skip + base
            if h + 0x20 > len(original):
                continue
            comp = original[h + 0x1C] | original[h + 0x1D] << 8
            chk = original[h + 0x1E] | original[h + 0x1F] << 8
            if comp ^ chk != 0xFFFF:
                continue
            from .cartridge_integrity import snes_mirrored_checksum
            try:
                if snes_mirrored_checksum(bytes(original[skip:])) != chk:
                    continue
                out[h + 0x1C:h + 0x20] = b'\xFF\xFF\x00\x00'
                t = snes_mirrored_checksum(bytes(out[skip:]))
            except ValueError:
                continue
            out[h + 0x1C:h + 0x20] = bytes(((t ^ 0xFFFF) & 0xFF, (t ^ 0xFFFF) >> 8, t & 0xFF, t >> 8))
            break
    elif system in ('sms', 'gg') and len(out) >= 0x8000 and out[0x7FF0:0x7FF8] == b'TMR SEGA':
        def total(b):
            size = {0xA: 0x1FF0, 0xB: 0x3FF0, 0xC: 0x7FF0, 0xD: 0xBFF0, 0xE: 0x10000, 0xF: 0x20000, 0: 0x40000,
                    1: 0x80000, 2: 0x100000}.get(b[0x7FFF] & 0x0F, 0x7FF0)
            s = sum(b[:min(size, 0x7FF0)])
            if size > 0x8000:
                s += sum(b[0x8000:min(size, len(b))])
            return s & 0xFFFF
        if original[0x7FFA] | original[0x7FFB] << 8 == total(original):
            t = total(out)
            out[0x7FFA], out[0x7FFB] = t & 0xFF, t >> 8
    return bytes(out)


def _bank_span(system: str, rom: bytes, file_offset: int) -> tuple[int, int]:
    """File range a short (16-bit) pointer to `file_offset` can also reach."""
    skip = rom_skip(rom, system)
    o = file_offset - skip
    if system in ('gb', 'gbc', 'sms', 'gg'):
        size = 0x4000
    elif system == 'nes':
        size = 0x2000
    elif system == 'snes':
        size = 0x10000 if _snes_hirom(rom) else 0x8000
    else:
        return skip, len(rom)
    a = o // size * size
    return skip + a, min(len(rom), skip + a + size)


def _snes_hirom(rom: bytes) -> bool:
    skip = rom_skip(rom, 'snes')

    def score(base):
        h = skip + base
        if h + 0x20 > len(rom):
            return -1
        s = 0
        s += 2 * ((rom[h + 0x1C] | rom[h + 0x1D] << 8) ^ (rom[h + 0x1E] | rom[h + 0x1F] << 8) == 0xFFFF)
        s += (rom[h + 0x15] & 1) == (1 if base == 0xFFC0 else 0)
        s += all(0x20 <= c < 0x7F for c in rom[h:h + 21])
        return s
    return score(0xFFC0) > score(0x7FC0)


def find_free_space(rom: bytes, system: str, size: int, *, near: int | None = None, same_bank: bool = True,
                    avoid: Iterable[tuple[int, int]] = (), span: tuple[int, int] | None = None) -> int | None:
    """File offset of `size` unused bytes, or None.

    Unused means a run of FF (anywhere) or of 00 that reaches the end of its
    bank: padding, not blank picture data. With `same_bank` the search stays
    in the bank of `near`, where a 16-bit pointer can still reach; a run never
    crosses a bank boundary. On Game Boy, zero padding between the interrupt
    vectors and the header ($0061-$00FF) also counts. `avoid`
    lists (start, end) file ranges known to be read (ImpactIndex sources).
    A margin of 4 bytes is kept from the data in front of the run.
    """
    lo, hi = span if span else (_bank_span(system, rom, near) if same_bank and near is not None else (rom_skip(rom, system), len(rom)))
    avoid = sorted(avoid)
    need = size + 4
    best = None
    i = lo
    while i < hi:
        b = rom[i]
        if b not in (0x00, 0xFF):
            i += 1
            continue
        bank_end = min(hi, _bank_span(system, rom, i)[1])
        j = i
        while j < bank_end and rom[j] == b:
            j += 1
        if system in ('gb', 'gbc') and i < 0x100 < j:
            j = 0x100  # never run into the header
        usable = b == 0xFF or j >= bank_end or (system in ('gb', 'gbc') and i >= 0x61 and j == 0x100)
        if usable and j - i >= need:
            start = i + 4
            if system in ('gb', 'gbc') and 0x100 <= start < 0x150:
                start = 0x150 if j - 0x150 >= size else None
            if system == 'genesis' and start is not None:
                start += start & 1
            if start is not None and j - start >= size and not any(a < start + size and start < e for a, e in avoid):
                if best is None or (near is not None and abs(start - near) < abs(best - near)):
                    best = start
                if near is None:
                    return best
        i = j
    return best


def pointer_candidates(rom: bytes, system: str, target: int, limit: int = 64) -> list[dict]:
    """Places in the ROM that could be a pointer to file offset `target`.

    Candidates are byte patterns only; locate_pointer keeps the ones a replay
    confirms. Ranked so that pointers loaded by an instruction or stored with
    their bank byte come first.
    """
    skip = rom_skip(rom, system)
    o = target - skip
    pats: list[tuple[bytes, str, int]] = []   # (bytes, encoding, base rank)
    if system in ('gb', 'gbc'):
        addr = o if o < 0x4000 else 0x4000 + (o & 0x3FFF)
        pats.append((addr.to_bytes(2, 'little'), 'le16', 2))
        gb_bank = o >> 14
    elif system in ('sms', 'gg'):
        for base in (0, 0x4000, 0x8000):
            pats.append((((o & 0x3FFF) + base).to_bytes(2, 'little'), f'le16+{base:04x}', 2 if base == (min(o, 0x8000) & 0xC000) else 3))
    elif system == 'nes':
        for base in (0x8000, 0xA000, 0xC000, 0xE000):
            pats.append((((o & 0x1FFF) + base).to_bytes(2, 'little'), f'le16+{base:04x}', 3))
    elif system == 'snes':
        if _snes_hirom(rom):
            addr = o & 0xFFFF
            for bank in ((o >> 16) | 0xC0, (o >> 16) | 0x40, (o >> 16) | 0x80, o >> 16):
                if bank & 0x7F < 0x40 and addr < 0x8000:
                    continue
                pats.append((addr.to_bytes(2, 'little') + bytes([bank & 0xFF]), 'le24', 1))
        else:
            addr = 0x8000 | (o & 0x7FFF)
            for bank in ((o >> 15) | 0x80, o >> 15):
                pats.append((addr.to_bytes(2, 'little') + bytes([bank & 0xFF]), 'le24', 1))
        pats.append((addr.to_bytes(2, 'little'), 'le16', 3))
    elif system == 'genesis':
        pats.append((o.to_bytes(4, 'big'), 'be32', 1))
        pats.append((o.to_bytes(3, 'big'), 'be24', 3))
    out = []
    seen = set()
    opcodes = {'sm83': (0x01, 0x11, 0x21), 'z80': (0x01, 0x11, 0x21), '6502': (), '65816': (0xA9, 0xA2, 0xA0), '68000': ()}[CPU[system]]
    for pat, enc, rank in pats:
        at = rom.find(pat, skip)
        while at >= 0:
            if at not in seen and not (at <= target < at + len(pat)):
                seen.add(at)
                r = rank
                if at and rom[at - 1] in opcodes:
                    r -= 1
                if system == 'genesis' and at & 1:
                    r += 2
                # the same bank is the likeliest home of a 16-bit pointer
                if len(pat) == 2 and _bank_span(system, rom, at) != _bank_span(system, rom, target) and at - skip >= 0x4000:
                    r += 1
                if system in ('gb', 'gbc') and gb_bank:
                    # a bank number stored next to the address makes a far pointer that can move anywhere
                    if at and rom[at - 1] == gb_bank:
                        out.append({'offset': at - 1, 'size': 3, 'encoding': 'gb-far-pre', 'rank': 0})
                    if at + 2 < len(rom) and rom[at + 2] == gb_bank:
                        out.append({'offset': at, 'size': 3, 'encoding': 'gb-far-post', 'rank': 0})
                    # `ld a,BANK` within a few instructions of `ld hl/de/bc,ADDRESS`: a far pointer held in code
                    if at and rom[at - 1] in opcodes:
                        for q in range(max(0, at - 12), min(len(rom) - 1, at + 12)):
                            if rom[q] == 0x3E and rom[q + 1] == gb_bank and not at - 1 <= q + 1 <= at + 1:
                                out.append({'offset': at, 'size': 3, 'encoding': 'gb-far-code', 'rank': 0.5, 'bank_at': q + 1})
                                break
                out.append({'offset': at, 'size': len(pat), 'encoding': enc, 'rank': r})
            at = rom.find(pat, at + 1)
    out.sort(key=lambda c: (c['rank'], abs(c['offset'] - target)))
    return out[:limit]


def _repoint(rom: bytes, system: str, pointer: dict, target: int, new_target: int) -> list:
    """Writes that make `pointer` (a pointer_candidates entry for `target`) name `new_target`."""
    delta = new_target - target
    size, enc = pointer['size'], pointer['encoding']
    old = rom[pointer['offset']:pointer['offset'] + size]
    if enc.startswith('gb-far'):
        if new_target < 0x4000:
            raise ValueError('A far pointer needs a target outside bank 0.')
        addr = (0x4000 + (new_target & 0x3FFF)).to_bytes(2, 'little')
        bank = bytes([new_target >> 14 & 0xFF])
        if new_target >> 14 > 0xFF:
            raise ValueError('Bank number does not fit in one byte.')
        if enc == 'gb-far-code':   # the address operand, and the bank operand of the `ld a,n` beside it
            at, b = pointer['offset'], pointer['bank_at']
            return ([(at + k, rom[at + k], addr[k]) for k in range(2) if rom[at + k] != addr[k]]
                    + ([(b, rom[b], bank[0])] if rom[b] != bank[0] else []))
        new = bank + addr if enc == 'gb-far-pre' else addr + bank
    elif enc.startswith('be'):
        value = int.from_bytes(old, 'big') + delta
        new = value.to_bytes(size, 'big')
    elif enc == 'le24':
        value = int.from_bytes(old, 'little')
        addr, bank = value & 0xFFFF, value >> 16
        lin = (bank << 16 | addr) + delta if _snes_hirom(rom) else None
        if lin is not None:
            new = (lin & 0xFFFFFF).to_bytes(3, 'little')
        else:
            o = ((bank & 0x7F) << 15 | (addr & 0x7FFF)) + delta
            new = (0x8000 | (o & 0x7FFF)).to_bytes(2, 'little') + bytes([(bank & 0x80) | (o >> 15)])
    else:
        if _bank_span(system, rom, target) != _bank_span(system, rom, new_target):
            raise ValueError('A 16-bit pointer cannot reach another bank.')
        new = ((int.from_bytes(old, 'little') + delta) & 0xFFFF).to_bytes(2, 'little')
    return [(pointer['offset'] + k, old[k], new[k]) for k in range(size) if old[k] != new[k]]


def plan_relocation(rom: bytes, system: str, start: int, end: int, new_bytes: bytes, pointer, *,
                    avoid: Iterable[tuple[int, int]] = (), kind: str = 'relocate', grow: bool = True) -> EditPlan:
    """Write `new_bytes` to free space and make `pointer` name it instead of [start, end).

    `pointer` is one pointer_candidates entry or a list of them (every
    reference that should move). The original bytes stay where they are, so
    every other reference keeps the old data.

    When no free space is within reach and every pointer can name any bank
    (a Game Boy far pointer, a 24-bit Super NES pointer, any Mega Drive
    pointer), the ROM grows instead, unless `grow` is False: Mega Drive by
    the size of the copy, Game Boy and Super NES to the next power-of-two
    size with the header's size byte brought up to date.
    """
    pointers = [pointer] if isinstance(pointer, dict) else list(pointer)
    if not pointers:
        raise ValueError('No pointer to move.')
    wide = all(p['size'] > 2 for p in pointers)
    span = (0x4000, len(rom)) if wide and system in ('gb', 'gbc') else None
    dest = find_free_space(rom, system, len(new_bytes), near=start, same_bank=not wide, avoid=avoid, span=span)
    base = rom
    notes = []
    if dest is None and wide and grow:
        if system == 'genesis' and len(rom) + len(new_bytes) + 2 <= 0x400000:
            dest = len(rom) + (len(rom) & 1)
            size = dest + len(new_bytes)
            size += size & 1
            base = rom + b'\xFF' * (size - len(rom))
            notes.append(f'The ROM grows by {size - len(rom)} bytes to hold the new copy.')
        elif system in ('gb', 'gbc') and len(rom) & (len(rom) - 1) == 0 and 0x8000 < len(rom) < 0x400000 \
                and rom[0x148] < 8 and not (rom[0x147] in (0x01, 0x02, 0x03) and len(rom) >= 0x80000) \
                and len(new_bytes) <= 0x4000:
            grown = bytearray(rom) + b'\xFF' * len(rom)
            grown[0x148] = rom[0x148] + 1
            base, dest = bytes(grown), len(rom)
        elif system == 'snes':
            grown = _snes_grown(rom)
            bank = 0x10000 if _snes_hirom(rom) else 0x8000
            if grown is not None and len(new_bytes) <= bank:
                base, dest = grown, len(rom)
        if base is not rom and system != 'genesis':
            notes.append(f'The ROM grows from {len(rom) >> 10} KB to {len(base) >> 10} KB to hold the new copy.')
    if dest is None:
        raise ValueError('No free ROM space within reach of the pointer for the new copy.')
    edited = bytearray(base)
    edited[dest:dest + len(new_bytes)] = new_bytes
    for p in pointers:
        for o, _, n in _repoint(base, system, p, start, dest):
            edited[o] = n
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan(kind, _diff_writes(rom, final), len(final), notes=notes,
                    details={'old_range': [start, end], 'new_offset': dest, 'new_size': len(new_bytes),
                             'pointer': dict(pointers[0]), 'repointed': [p['offset'] for p in pointers]})


def locate_pointer(verify: Callable[[EditPlan], dict], rom: bytes, system: str, start: int, end: int, probe: bytes,
                   expect: dict, *, avoid: Iterable[tuple[int, int]] = (), max_candidates: int = 24,
                   find_all: bool = False, report: dict | None = None) -> list[dict]:
    """Pointers to [start, end) that the scene really loads through.

    `probe` is a replacement block with a visible change and `expect` the
    scene bytes that change if a pointer is the one in use. Each candidate is
    repointed at a relocated probe and replayed with `verify(plan)` (a
    verify_plan closure). The search stops at the first candidate whose
    replay comes out as planned; it is returned in a one-element list with
    the replay result under 'check' (an empty list when none is confirmed).
    With `find_all` every candidate is replayed and every confirmed one is
    returned (the same reference is sometimes stored in more than one form).

    `report`, when given, receives why candidates fell away: 'candidates'
    (byte patterns found), 'no_room' (no free space within the pointer's
    reach), 'replayed', 'confirmed'.
    """
    hits = []
    cands = pointer_candidates(rom, system, start)[:max_candidates]
    counts = {'candidates': len(cands), 'no_room': 0, 'replayed': 0, 'confirmed': 0}
    for cand in cands:
        try:
            plan = plan_relocation(rom, system, start, end, probe, cand, avoid=avoid)
        except ValueError:
            counts['no_room'] += 1
            continue
        plan.expect = expect
        result = verify(plan)
        counts['replayed'] += 1
        if result.get('as_planned'):
            counts['confirmed'] += 1
            hits.append({**cand, 'check': {'from_frame': result.get('from_frame'), 'unplanned': result.get('unplanned', {})}})
            if not find_all:
                break
    if report is not None:
        report.update(counts)
    return hits


def _no_pointer(counts: dict) -> str:
    """Why locate_pointer came back empty, in a sentence."""
    if not counts.get('candidates'):
        return 'nothing in the ROM looks like a pointer to it (the address is probably computed)'
    if not counts.get('replayed'):
        return (f'{counts["candidates"]} possible pointer(s) were found, but there is no free ROM space within their '
                'reach for the copy')
    return (f'{counts["replayed"]} possible pointer(s) were moved in turn and none changed the scene as planned'
            + (f' ({counts["no_room"]} more had no free space within reach)' if counts.get('no_room') else ''))


# ---------------------------------------------------------------------------
# 4. Compressed (derived) graphics: recognise the block, re-encode it
# ---------------------------------------------------------------------------

def _expand_3bpp(raw: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(raw) - len(raw) % 24, 24):
        out += raw[i:i + 16]
        for b in raw[i + 16:i + 24]:
            out += bytes((b, 0))
    return bytes(out)


def _index_3bpp(k: int):
    tile, j = divmod(k, 32)
    if j < 16:
        return tile * 24 + j
    return None if j & 1 else tile * 24 + 16 + (j - 16) // 2


# How a game lays an unpacked block into video memory:
# name -> (expand the block, index in the block of an expanded byte or None when the game makes that byte up).
TRANSFORMS = {
    '': (lambda raw: raw, lambda k: k),
    # Super NES 3-bit tiles: 16 bytes as they are, then 8 bytes each followed by a zero.
    '3bpp': (_expand_3bpp, _index_3bpp),
}


@dataclass
class CompressedBlock:
    codec: str
    start: int           # FILE offset of the stream
    size: int            # stream bytes the decoder consumed
    decoded: bytes       # the unpacked block as the codec yields it
    domain: str
    domain_start: int    # domain index that holds expanded[first]
    first: int           # expanded[first:last] is what the scene holds at domain_start,
    last: int            # where expanded = TRANSFORMS[transform] applied to decoded
    transform: str = ''

    def decoded_index(self, domain_index: int) -> int:
        k = domain_index - self.domain_start + self.first
        if not self.first <= k < self.last:
            raise ValueError('That byte is not part of the recognised block.')
        k = TRANSFORMS[self.transform][1](k)
        if k is None:
            raise ValueError('The game fills that byte in itself (the tile is stored with 8 colors); it cannot be edited.')
        return k

    def to_dict(self) -> dict:
        return {'codec': self.codec, 'start': self.start, 'size': self.size, 'decoded_size': len(self.decoded),
                'domain': self.domain, 'domain_start': self.domain_start, 'first': self.first, 'last': self.last,
                'transform': self.transform}


def source_cluster(scene: Scene, domain: str, start: int, length: int, walk: int = 0x8000, drop: int = 0x30,
                   most: int = 40, holes: int = 256):
    """Where in the ROM the load that produced domain[start:start+length] may begin.

    Unpacked bytes carry the offset of the last stream byte read (or, for
    literals, their own offset), so within one load the offsets fall as the
    bytes are followed backwards through video memory. Walking back from the
    target, every sudden fall of the lowest offset seen marks a possible
    boundary between two loads (or the header of this one).

    Returns (domain start, domain end, anchors, lowest target offset, highest
    target offset): the run of video memory that looks like one stretch of
    loading, and the candidate first-data offsets, nearest first. None when
    the target carries no ROM offsets. Bytes whose value is 00 or FF are
    skipped: their tags are often coincidences. Up to `holes` bytes in a row
    that came from somewhere else are stepped over: games overwrite parts of
    a loaded block later (animated tiles, text).
    """
    d = scene.snapshot.domains[domain]
    own = [tag_offset(d.tags[i]) for i in range(start, start + length) if tag_kind(d.tags[i]) and not d.tags[i] & RT_WEAK]
    if not own:
        own = [tag_offset(d.tags[i]) for i in range(start, start + length) if tag_kind(d.tags[i])]
    if not own:
        return None
    tlo, thi = min(own), max(own)
    anchors = []
    low = tlo
    a = start
    i = start - 1
    strangers = 0
    while i >= 0 and start - i <= walk and strangers <= holes:
        tag = d.tags[i]
        o = tag_offset(tag)
        kind = tag_kind(tag)
        if tag & RT_WEAK and kind:
            a = i                # a 00 or FF: says nothing either way
        elif kind in (pv.RT_ROM, pv.RT_DERIVED) and low - 0x400 <= o <= thi + 0x400:
            strangers = 0        # at most a header's length below anything seen so far: still this stretch
            if o < low:
                if low - o > drop:
                    anchors.append(low)
                low = o
            a = i
        else:
            strangers += 1       # never written, a code value, or from elsewhere in the ROM: not this load
        i -= 1
    # The lowest offset of the whole stretch is the likeliest start; then the falls nearest the target.
    anchors = [low] + [x for x in anchors if x != low][:most - 1]
    b = start + length
    i = b
    n = len(d.tags)
    strangers = 0
    while i < n and i - start <= walk and strangers <= holes:
        tag = d.tags[i]
        if tag_kind(tag) and tag & RT_WEAK:
            b = i + 1
        elif tag_kind(tag) in (pv.RT_ROM, pv.RT_DERIVED) and low <= tag_offset(tag) <= thi + 0x4000:
            strangers = 0
            b = i + 1
        else:
            strangers += 1
        i += 1
    return a, b, anchors, tlo, thi


# How far in front of the first data byte a stream may begin (headers, code tables).
_STREAM_HEAD = {'nemesis': 0x280, 'enigma': 8}


def find_compressed_block(scene: Scene, rom: bytes, system: str, domain: str, start: int, length: int,
                          codecs: Iterable[str] | None = None, back: int = 8) -> CompressedBlock | None:
    """Recognise the packed stream that produced domain[start:start+length].

    The tags of the bytes around the target give candidate places where the
    stream begins (source_cluster). Every known codec is run from the few
    plausible starts in front of each; where one stream ends before the
    target's data, the stream that follows it is tried too (packed files
    often sit back to back and load to adjacent video memory). A codec is
    accepted when its output, laid out as the system does (TRANSFORMS),
    reproduces the target exactly and at least nine tenths of the rest of
    the block as the scene still holds it. A complete agreement ends the
    search; otherwise the fullest one over every codec and start is
    returned. A recognised block is still a claim until an edit made through
    it has replayed as planned.
    """
    d = scene.snapshot.domains[domain]
    cluster = source_cluster(scene, domain, start, length)
    if cluster is None:
        return None
    a, b, anchors, tlo, thi = cluster
    skip = rom_skip(rom, system)
    region = bytes(d.data[a:b])
    target = bytes(d.data[start:start + length])
    probe = target
    probe_shift = 0
    if len(set(target)) <= 2:
        # a flat target matches anywhere; anchor on the nearest stretch that has a picture
        near = sorted(range(0, max(0, len(region) - 16), 8), key=lambda k: abs(a + k - start))
        for k in near:
            if len(set(region[k:k + 16])) > 4:
                probe, probe_shift = region[k:k + 16], (a + k) - start
                break
        else:
            return None
    best = None
    transforms = ('', '3bpp') if system == 'snes' else ('',)
    need = min(48, len(region))

    def consider(codec, s, raw_out, used):
        nonlocal best
        for transform in transforms:
            out = TRANSFORMS[transform][0](raw_out)
            k = out.find(probe)
            tries = 0
            while k >= 0 and tries < 8:
                tries += 1
                base = start + probe_shift - k           # domain index of expanded[0]
                p, q = max(0, a - base), min(len(out), b - base)
                at = start - base
                if p <= at and at + length <= q and out[at:at + length] == target and q - p >= need:
                    held = d.data[base + p:base + q]
                    agree = sum(x == y for x, y in zip(out[p:q], held))
                    # Parts of a block are often overwritten later, so nine bytes in ten must agree, not all.
                    # A stream entered a few bytes late can fall back into step and reproduce most of a
                    # block, so every candidate is scored and the fullest agreement wins; between equals,
                    # the one with no output hanging off the front of the stretch.
                    if agree * 10 >= (q - p) * 9 and len(set(out[p:q])) > 2:
                        score = (agree == q - p, agree, -p, s)
                        if best is None or score > best[0]:
                            best = (score, CompressedBlock(codec, skip + s, used, raw_out, domain, base + p, p, q, transform))
                k = out.find(probe, k + 1)

    for codec in (list(codecs) if codecs else gfx_codecs.order_for(system)):
        terminated = gfx_codecs.CODECS[codec]['terminated']
        limit = 0x10000 if terminated else len(region) + 0x100
        seen = set()
        for anchor in anchors:
            for s in range(anchor, max(anchor - max(back, _STREAM_HEAD.get(codec, 0)), 0) - 1, -1):
                chain = 0
                while s not in seen and chain < 64:
                    seen.add(s)
                    try:
                        raw_out, used = gfx_codecs.decode(codec, rom, skip + s, limit)
                    except (ValueError, IndexError):
                        break
                    if used < 3:
                        break
                    if s + used > tlo:
                        consider(codec, s, raw_out, used)
                        break
                    # this stream ends before the target's data: try the one that follows it
                    s += used + ((s + used) & 1 if system == 'genesis' else 0)
                    chain += 1
        if best and best[0][0]:
            break
    if not (best and best[0][0]):
        # gfx_codecs' own recogniser: data stored as it is with made-up planes, finer stream starts, more layouts
        extra = gfx_codecs.recognise(d, rom, skip, system, start, length, codecs)
        if extra and (extra['complete'] or best is None):
            return CompressedBlock(extra['codec'], extra['start'], extra['size'], extra['decoded'], domain,
                                   extra['domain_start'], extra['first'], extra['last'])
    return best[1] if best else None


def plan_block_edit(block: CompressedBlock, changes: dict, rom: bytes, system: str, *,
                    verify: Callable[[EditPlan], dict] | None = None, avoid: Iterable[tuple[int, int]] = (),
                    force_relocate: bool = False, max_candidates: int = 24,
                    also: Iterable[tuple] = ()) -> EditPlan:
    """Re-encode a recognised block with `changes` ({domain index: new value}) applied.

    The new stream is written over the old one when it is no longer. When it
    is longer it goes to free space and the pointer to the block is moved;
    the pointer is found by replay, so `verify` (a closure over verify_plan
    taking an EditPlan) is required for that case.

    A moved block is reached only through the references that were moved
    with it. Every reference this scene's replay confirms is moved. `also`
    names other scenes that load the same block: (CompressedBlock as
    recognised in that scene, verify closure for that scene) pairs. The
    reference each of them loads through is found by replaying that scene
    and moved as well; `details['scenes_repointed']` says how many of them
    were confirmed, and a scene that is not confirmed keeps the old picture.
    """
    raw = bytearray(block.decoded)
    for i, v in changes.items():
        raw[block.decoded_index(int(i))] = v
    stream = gfx_codecs.encode(block.codec, bytes(raw), like=rom[block.start:block.start + block.size])
    expect = {block.domain: {int(i): v for i, v in changes.items()}}
    details = {'block': block.to_dict(), 'old_stream': block.size, 'new_stream': len(stream)}
    if len(stream) <= block.size and not force_relocate:
        edited = bytearray(rom)
        edited[block.start:block.start + len(stream)] = stream
        final = fix_checksums(bytes(edited), rom, system)
        return EditPlan('reencode', _diff_writes(rom, final), len(final), expect, details=details)
    if verify is None:
        raise ValueError(f'The re-encoded data is {len(stream) - block.size} bytes longer than the original; '
                         'pass verify so the pointer to the block can be found and moved.')
    counts: dict = {}
    hits = locate_pointer(verify, rom, system, block.start, block.start + block.size, stream, expect, avoid=avoid,
                          max_candidates=max_candidates, find_all=True, report=counts)
    if not hits:
        raise ValueError('The re-encoded data does not fit in place and no pointer to the block was confirmed: '
                         + _no_pointer(counts) + '.')
    others = 0
    also = list(also)
    for other, other_verify in also:
        if other.start != block.start or other.codec != block.codec:
            continue
        other_expect: dict = {}
        for i, v in changes.items():       # the same decoded bytes, where that scene holds them
            try:
                k = block.decoded_index(int(i))
            except ValueError:
                continue
            for j in range(other.domain_start, other.domain_start + other.last - other.first):
                try:
                    if other.decoded_index(j) == k:
                        other_expect.setdefault(other.domain, {})[j] = v
                except ValueError:
                    pass
        if not other_expect:
            continue
        found = locate_pointer(other_verify, rom, system, block.start, block.start + block.size, stream, other_expect,
                               avoid=avoid, max_candidates=max_candidates)
        if found:
            others += 1
            hits += [h for h in found if h['offset'] not in {x['offset'] for x in hits}]
    plan = plan_relocation(rom, system, block.start, block.start + block.size, stream, hits, avoid=avoid)
    plan.expect = expect
    plan.details.update(details)
    plan.details['pointer_search'] = counts
    plan.notes.append('The data no longer fits where it was; it was written to free space and its pointer moved.')
    if also:
        plan.details['scenes_repointed'] = others
        plan.notes.append(f'{len(hits)} reference(s) were moved: the one(s) this scene loads through and those of '
                          f'{others} of the {len(also)} other scene(s) that use the same data. A use that was not '
                          'confirmed keeps the old picture.')
    else:
        plan.notes.append('Only the reference(s) this scene loads through were moved. If the game reaches the old data '
                          'through another reference, that use keeps the old picture.')
    return plan


# ---------------------------------------------------------------------------
# 4b. Codec-independent fallback: overlay on the vertical-blank interrupt
# ---------------------------------------------------------------------------

OVERLAY_STATUS = {
    'sm83': 'implemented and replay-verified (Game Boy, Game Boy Color)',
    '65816': 'implemented and replay-verified (Super NES): native NMI vector -> JML in the unused vector bytes at '
             '$00:FFE0 -> routine in free ROM; it sets VMAIN/VMADD, which the game cannot read back',
    '68000': 'implemented and replay-verified (Mega Drive / Genesis): level-6 vector at $78 -> routine in free or '
             'added ROM; it sends its own VDP commands, which can collide with a command the game was halfway through',
    '6502': 'implemented and replay-verified (NES, CHR-RAM cartridges; CHR-ROM tiles are edited in place): NMI vector '
            '-> routine in the always-mapped part of the program ROM; it uses $2006/$2007, which also hold the scroll',
    'z80': 'implemented and replay-verified (Master System): jump at $0038 -> routine in the first 32 KB, or a paging '
           'stub there and the routine in any bank or in added ROM; works only in the vertical blank',
}

_SM83_LEN3 = {0x01, 0x11, 0x21, 0x31, 0x08, 0xC2, 0xC3, 0xCA, 0xD2, 0xDA, 0xC4, 0xCC, 0xCD, 0xD4, 0xDC, 0xEA, 0xFA}
_SM83_LEN2 = {0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x36, 0x3E, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38, 0xC6, 0xCE, 0xD6,
              0xDE, 0xE6, 0xEE, 0xF6, 0xFE, 0xE0, 0xF0, 0xE8, 0xF8, 0xCB}
_SM83_RELATIVE = {0x18, 0x20, 0x28, 0x30, 0x38}
_SM83_END = {0xC3, 0xC9, 0xD9, 0xE9}
_SM83_INVALID = {0xD3, 0xDB, 0xDD, 0xE3, 0xE4, 0xEB, 0xEC, 0xED, 0xF4, 0xFC, 0xFD}


def _assemble(items, origin: int) -> bytes:
    """Tiny assembler: bytes, ('label', name), ('jr', opcode, name), ('abs', name)."""
    for final in (False, True):
        out = bytearray()
        labels_now = {}
        for it in items:
            if isinstance(it, (bytes, bytearray)):
                out += it
            elif it[0] == 'label':
                labels_now[it[1]] = len(out)
            elif it[0] == 'jr':
                rel = (labels[it[2]] - (len(out) + 2)) if final else 0
                if not -128 <= rel <= 127:
                    raise ValueError('relative jump out of range')
                out += bytes((it[1], rel & 0xFF))
            elif it[0] == 'abs':
                out += ((origin + labels[it[1]]) if final else 0).to_bytes(2, 'little')
        labels = labels_now
    return bytes(out)


def _sm83_overlay_routine(origin: int, tail: bytes, records: bytes, after: bool = False, vblank_only: bool = False) -> bytes:
    """The overlay routine at `origin`; `tail` runs after every register is restored.

    With `after`, the routine first calls on into the game's handler (`tail`), which leaves the work below as
    the address that handler returns to. The work then runs when the game's handler has finished (after any
    tile the game itself writes each frame), only while the screen is still in its vertical blank, and its own
    `ret` goes back to the interrupted program.
    """
    items = [b'\xCD', ('abs', 'handler')] if after else []
    items += [
        b'\xF5\xC5\xD5\xE5',            # push af / bc / de / hl
        b'\xF0\x4F\xF5',                # ldh a,[$4F] ; push af        (current VRAM bank)
    ]
    if after or vblank_only:
        items += [b'\xF0\x41\xE6\x03\x3D', ('jr', 0x20, 'done')]   # ldh a,[$41] ; and 3 ; dec a ; jr nz,done  (not mode 1)
    items += [
        b'\x21', ('abs', 'table'),      # ld hl,table
        ('label', 'next'),
        b'\x2A\xFE\xFF', ('jr', 0x28, 'done'),   # ld a,[hl+] ; cp $FF ; jr z,done
        b'\xE0\x4F',                    # ldh [$4F],a                  (bank of this tile)
        b'\x2A\x5F\x2A\x57',            # de = address of the key byte
        b'\x1A\xBE\x23',                # ld a,[de] ; cp [hl] ; inc hl (flags survive the loads below)
        b'\x2A\x5F\x2A\x57',            # de = tile address
        ('jr', 0x20, 'skip32'),         # key byte is not the original: nothing to do
        b'\x06\x10',                    # ld b,16
        ('label', 'cmp'),
        b'\x1A\xBE', ('jr', 0x20, 'skipb'), b'\x23\x1C\x05', ('jr', 0x20, 'cmp'),
        b'\x7B\xD6\x10\x5F\x06\x10',    # e -= 16 ; ld b,16
        ('label', 'cpy'),
        b'\x2A\x12\x1C\x05', ('jr', 0x20, 'cpy'),
        ('jr', 0x18, 'next'),
        ('label', 'skipb'),
        b'\x78\xC6\x10', ('jr', 0x18, 'adv'),    # a = bytes left of old + 16 of new
        ('label', 'skip32'),
        b'\x3E\x20',
        ('label', 'adv'),
        b'\x85\x6F', ('jr', 0x30, 'next'), b'\x24', ('jr', 0x18, 'next'),
        ('label', 'done'),
        b'\xF1\xE0\x4F',                # restore the VRAM bank
        b'\xE1\xD1\xC1\xF1',            # pop hl / de / bc / af
    ]
    items += [b'\xC9', ('label', 'handler'), tail] if after else [tail]
    items += [('label', 'table'), records, b'\xFF']
    return _assemble(items, origin)


def gb_bank_shadow(rom: bytes) -> dict | None:
    """The RAM variable in which a Game Boy game keeps its current ROM bank number.

    The cartridge's bank register cannot be read back, so games store the
    number in RAM just before writing it to the register ($2000-$3FFF). This
    looks for that pair of instructions (`ldh [n],a` or `ld [nnnn],a`, then
    `ld [$2xxx],a`). Returns {'address', 'uses', 'bank_writes'} for the
    variable used by the most bank switches, or None when the game has no
    such habit or stores the number only after switching (restoring from the
    variable would then not be safe inside an interrupt).
    """
    before: dict[int, int] = {}
    after: dict[int, int] = {}
    writes = 0
    at = rom.find(b'\xEA')
    while at >= 0 and at + 2 < len(rom):
        if 0x20 <= rom[at + 2] <= 0x3F:
            writes += 1
            for back in range(2, 9):
                q = at - back
                if q < 0:
                    break
                if back in (2, 3, 4, 5) and rom[q] == 0xE0 and rom[q + 1] >= 0x80 and rom[q + 1] != 0xFF:
                    before[0xFF00 | rom[q + 1]] = before.get(0xFF00 | rom[q + 1], 0) + 1
                    break
                if back >= 3 and rom[q] == 0xEA and 0xC0 <= rom[q + 2] <= 0xDF:
                    a = rom[q + 1] | rom[q + 2] << 8
                    before[a] = before.get(a, 0) + 1
                    break
            q = at + 3
            if q + 2 < len(rom):
                if rom[q] == 0xE0 and rom[q + 1] >= 0x80:
                    after[0xFF00 | rom[q + 1]] = after.get(0xFF00 | rom[q + 1], 0) + 1
                elif rom[q] == 0xEA and 0xC0 <= rom[q + 2] <= 0xDF:
                    a = rom[q + 1] | rom[q + 2] << 8
                    after[a] = after.get(a, 0) + 1
        at = rom.find(b'\xEA', at + 1)
    if not before:
        return None
    address, uses = max(before.items(), key=lambda kv: kv[1])
    if uses < 2 or after.get(address, 0) > uses or max(after.values(), default=0) > uses:
        return None
    return {'address': address, 'uses': uses, 'bank_writes': writes}


def gb_bank_probe(rom: bytes) -> dict | None:
    """One or two places in the switchable ROM area whose bytes tell every bank apart.

    The cartridge's bank register cannot be read back, but the bank it
    selects can be recognised by its contents. Returns {'offsets': [k, ...],
    'table': [(byte at k, ..., bank number), ...]} with offsets counted from
    $4000, or None when no one or two positions separate the banks. Banks
    with identical contents count as one: mapping either is the same thing.
    """
    banks = len(rom) // 0x4000
    first = 0 if rom[0x147] in range(0x19, 0x1F) else 1     # only MBC5 can map bank 0 there
    seen: dict[bytes, int] = {}
    for b in range(first, banks):
        seen.setdefault(rom[b * 0x4000:(b + 1) * 0x4000], b)
    numbers = sorted(seen.values())
    if not numbers or len(numbers) > 255 or max(numbers) > 0xFF:
        return None
    cols = [rom[b * 0x4000:(b + 1) * 0x4000] for b in numbers]
    best = (0, 0)
    for k, col in enumerate(zip(*cols)):
        distinct = len(set(col))
        if distinct == len(cols):
            return {'offsets': [k], 'table': [(c[k], b) for c, b in zip(cols, numbers)]}
        if distinct > best[0]:
            best = (distinct, k)
    k1 = best[1]
    firsts = [c[k1] for c in cols]
    for k2, col in enumerate(zip(*cols)):
        if len(set(zip(firsts, col))) == len(cols):
            return {'offsets': [k1, k2], 'table': [(c[k1], c[k2], b) for c, b in zip(cols, numbers)]}
    return None


def _sm83_displaced(rom: bytes, vec: int) -> tuple[bytes, int]:
    """(code that does what the instructions at `vec` did and then carries on after them, bytes covered).

    The jump to the overlay routine replaces at least three bytes at the
    interrupt vector; the instructions it covers run at the end of the
    routine instead.
    """
    if rom[vec] in (0xFF,) or rom[vec] in _SM83_INVALID:
        raise ValueError('This game has no vertical-blank interrupt handler to hook.')
    covered = 0
    ended = False
    displaced = bytearray()
    while covered < 3 and not ended:
        op = rom[vec + covered]
        if op == 0x18:  # jr e: the same jump, absolute
            e = rom[vec + covered + 1]
            displaced += b'\xC3' + ((vec + covered + 2 + (e - 256 if e & 0x80 else e)) & 0xFFFF).to_bytes(2, 'little')
            covered += 2
            ended = True
            break
        if op in _SM83_RELATIVE or op in _SM83_INVALID:
            raise ValueError('The interrupt handler starts with code that cannot be moved.')
        size = 3 if op in _SM83_LEN3 else 2 if op in _SM83_LEN2 else 1
        displaced += rom[vec + covered:vec + covered + size]
        covered += size
        ended = op in _SM83_END
    if covered > 8:
        raise ValueError('The interrupt handler starts with code that cannot be moved.')
    return bytes(displaced) + (b'' if ended else b'\xC3' + (vec + covered).to_bytes(2, 'little')), covered


# `guard` values that mean "only while the interrupted program is waiting", and the longest loop (in bytes)
# each accepts as a wait. The wider test lets through games whose wait loop is longer, and more loops that
# are not waits; the planner tries the narrow one first.
_IDLE_BYTES = {'idle': 8, 'idle-wide': 16}


def plan_overlay_patch(edits: list, rom: bytes, system: str, *, avoid: Iterable[tuple[int, int]] = (),
                       max_tiles: int = 24, scene: Scene | None = None, after_handler: bool = False,
                       guard: bool = True, hook: str = 'nmi', grow: bool = True, _control: str | None = None) -> EditPlan:
    """Fallback for tiles no codec explains: rewrite them after the game has loaded them.

    `edits` is [(Tile, new pixels)]. A routine is added on the vertical-blank
    interrupt. Each frame, for each edited tile, it checks whether video
    memory holds exactly the original tile and, if so, writes the edited one.
    It does not depend on how the game stores or unpacks the tile, and it
    leaves the slot alone when the game has loaded something else there.

    Every processor ROMancer knows (OVERLAY_STATUS). The game must take the
    vertical-blank interrupt (on Super NES the IRQ can stand in: `hook`).

    The video chips' address registers cannot be read back, so the routine
    cannot put back what it found. What keeps it from disturbing a transfer
    the game has under way is `guard`, which makes it do nothing in a frame
    that looks unsafe. Which test that is depends on the processor; where
    one costs coverage (a game that never passes it never gets the edit)
    the other values are the alternatives, and plan_derived_tile_edit tries
    them from safest to least safe.

    Mega Drive / Genesis: the level-6 (vertical blank) vector at $78 is
    pointed at the routine, which goes into free ROM or onto the end of the
    ROM and ends by jumping to the game's own handler. Each frame it sends
    one read command per edited tile. `guard=True` (the default) skips a
    frame in which the interrupted program holds a VDP port address in an
    address register, the usual sign of a stream into video memory;
    `guard='idle'` also requires that the interrupted program was waiting
    (stopped, or in a loop of a few instructions; 'idle-wide' accepts loops
    twice as long); `guard=False` always works. `after_handler` runs the
    work when the game's handler returns.

    Super NES: the native-mode NMI vector (`hook='irq'`: the IRQ vector, and
    then only in the vertical blank; `hook='poll'`: no vector at all, the
    routine is called from the loop in which a game without such an
    interrupt waits for the vertical blank) is pointed at a JML in bank 0: in a
    blank reserved vector slot, in any four free bytes, or in a reserved
    slot whatever it holds (the processor never fetches those). The routine
    itself goes into free ROM anywhere, or, with `grow`, into a ROM enlarged
    to the next power-of-two size, and ends by jumping to the game's own
    handler (which may be a jump the game keeps in RAM). It sets VMAIN and
    VMADD. `guard='idle'` makes it work only while the interrupted program
    was waiting (WAI, or a loop of at most eight bytes with no store to the
    picture chip; 'idle-wide': sixteen bytes); other values of `guard` mean
    no test. With
    `after_handler` the work runs when the game's handler returns instead of
    before it starts (see _snes_overlay_routine).

    Game Boy: the routine (about 80 bytes plus 38 per tile) goes, in order of
    preference:

    * 'bank0': into free space in ROM bank 0, always mapped;
    * 'fixed': anywhere in a 32 KB cartridge that has no bank switching;
    * 'banked': into free space in another bank, behind a stub in bank 0
      that maps that bank, calls the routine and restores the game's bank
      from the game's own current-bank variable (gb_bank_shadow). Used only
      when that variable is found and, given `scene`, holds a valid bank
      number at that moment;
    * 'banked-probe': the same, for games without such a variable: the stub
      recognises the mapped bank by reading one or two bytes of it
      (gb_bank_probe) and maps that bank again afterwards;
    * 'added-mapper': a 32 KB cartridge without a mapper becomes a 64 KB
      MBC1 cartridge with the routine in the added half (`grow`).

    With `grow`, a banked cartridge with no room in any bank doubles in size.

    NES (CHR-RAM cartridges) and Master System: see romancer.gfx_overlay8.
    `guard` there means: NES, do nothing while the game's own mask variable
    has the picture switched off; Master System, do nothing while the
    interrupted program holds the video data port in register C.

    verify_plan then shows whether the tile really changes in the scene and
    whether anything else did; overlay_safety, whether the game is left
    alone over the whole run from power-on.
    """
    cpu = CPU[system]
    if not edits or len(edits) > max_tiles:
        raise ValueError(f'The overlay handles 1 to {max_tiles} tiles at a time.')
    if cpu == '65816':
        return _snes_overlay_patch(edits, rom, system, avoid, after_handler, hook, grow, idle=_IDLE_BYTES.get(guard, 0))
    if cpu == '68000':
        return _genesis_overlay_patch(edits, rom, system, avoid, guard, after_handler)
    if cpu == '6502':
        from . import gfx_overlay8
        return gfx_overlay8.nes_overlay_patch(edits, rom, system, avoid, guard=bool(guard))
    if cpu == 'z80':
        from . import gfx_overlay8
        return gfx_overlay8.sms_overlay_patch(edits, rom, system, avoid, bool(guard), grow, scene=scene,
                                              hook='poll' if hook == 'poll' else 'irq', after=after_handler)
    if len(rom) < 0x4000:
        raise ValueError('Not a Game Boy ROM image.')
    records = bytearray()
    expect: dict[int, int] = {}
    for tile, pixels in edits:
        new = encode_tile(pixels, tile.format) if not isinstance(pixels, (bytes, bytearray)) else bytes(pixels)
        if tile.domain != 'vram' or len(new) != 16:
            raise ValueError('The overlay edits 16-byte tiles in video memory.')
        diff = [k for k in range(16) if new[k] != tile.stored[k]]
        if not diff:
            continue
        a = tile.addresses[0]
        bank, addr = a >> 13, 0x8000 + (a & 0x1FFF)
        key = diff[0]
        if _control:
            # plan_overlay_control: the same routine and table, but it writes back the bytes it found ('high':
            # the cost of a frame in which the tile is rewritten) or never gets past the first compare ('low').
            # Video memory is plain memory on this system, so reading it has no effect of its own.
            first = tile.stored[key] if _control == 'high' else tile.stored[key] ^ 0xFF
            records += bytes((bank, (addr + key) & 0xFF, (addr + key) >> 8, first, addr & 0xFF, addr >> 8))
            records += tile.stored + tile.stored
            continue
        records += bytes((bank, (addr + key) & 0xFF, (addr + key) >> 8, tile.stored[key], addr & 0xFF, addr >> 8))
        records += tile.stored + new
        expect.update({tile.addresses[k]: new[k] for k in diff})
    if not records:
        raise ValueError('The edit changes nothing.')
    vec = 0x40
    tail, covered = _sm83_displaced(rom, vec)
    records = bytes(records)
    size = len(_sm83_overlay_routine(0, tail, records, after_handler))
    edited = bytearray(rom)
    notes = ['The game unpacks this tile in a way ROMancer does not decode, so the edit is applied '
             'by a small added routine each frame instead of changing the stored data.',
             'It applies wherever the game shows this exact tile in this tile slot.']
    details = {'routine_size': size, 'hook_offset': vec, 'tiles': len(records) // 38, 'cpu': cpu,
               'timing': 'after the game\'s handler' if after_handler else 'before the game\'s handler'}
    where = find_free_space(rom, system, size, span=(0x68, 0x4000), avoid=avoid)
    if where is not None:
        details.update(placement='bank0', routine_offset=where)
    elif rom[0x147] == 0x00 and len(rom) == 0x8000:
        where = find_free_space(rom, system, size, span=(0x4000, 0x8000), avoid=avoid)
        if where is not None:
            details.update(placement='fixed', routine_offset=where)
    if where is not None:
        code = _sm83_overlay_routine(where, tail, records, after_handler)
        edited[where:where + len(code)] = code
        edited[vec:vec + 3] = b'\xC3' + where.to_bytes(2, 'little')
    else:
        # The routine goes into another bank, behind a stub that maps it and then maps the game's bank again.
        banks = len(rom) // 0x4000
        cart = rom[0x147]
        if cart in (0x01, 0x02, 0x03) and banks > 32:
            raise ValueError(f'ROM bank 0 has no {size} free bytes for the overlay routine, and this cartridge type '
                             'splits its bank number over two registers.')
        plain = cart == 0x00 and len(rom) == 0x8000      # no mapper at all: it gets one, and a second 32 KB
        shadow = probe = None
        problem = ''
        if plain:
            if not grow:
                raise ValueError(f'The ROM has no {size} free bytes for the overlay routine.')
        else:
            shadow = gb_bank_shadow(rom)
            if shadow is None:
                problem = 'the game keeps no current-bank variable'
            elif scene is not None:
                a = shadow['address']
                d = scene.snapshot.domains.get('hram' if a >= 0xFF80 else 'wram')
                value = None
                if d is not None and d.data is not None:
                    value = d.data[a - 0xFF80] if a >= 0xFF80 else d.data[a - 0xC000] if a < 0xD000 else None
                if value is not None and not 0 < value < banks:
                    shadow, problem = None, 'the variable that looked like the current bank number does not hold one'
            if shadow is None:
                probe = gb_bank_probe(rom)
                if probe is None:
                    raise ValueError(f'ROM bank 0 has no {size} free bytes for the overlay routine, {problem}, and the '
                                     'banks cannot be told apart by reading one or two bytes of them.')
        # the stub: push af ; [remember which bank is mapped] ; map the routine ; call it ; map the game's bank ; pop af
        if plain:
            before, after = b'\xF5', b'\x3E\x01\xEA\x00\x21\xF1'                # ... ld a,1 ; ld [$2100],a ; pop af
        elif shadow:
            a = shadow['address']
            load = bytes((0xF0, a & 0xFF)) if a >= 0xFF00 else bytes((0xFA, a & 0xFF, a >> 8))
            before, after = b'\xF5', load + b'\xEA\x00\x21\xF1'
        else:
            before = b'\xF5\xE5'                                                # push af ; push hl
            for n, k in enumerate(probe['offsets']):
                before += b'\xFA' + (0x4000 + k).to_bytes(2, 'little') + (b'\x67', b'\x6F')[n]   # ld a,[k] ; ld h,a / ld l,a
            after = b'\xEA\x00\x21\xE1\xF1'                                     # ld [$2100],a ; pop hl ; pop af
        stub_size = len(before) + 8 + len(after) + len(tail) + (4 if after_handler else 0)
        stub = find_free_space(rom, system, stub_size, span=(0x68, 0x8000 if plain else 0x4000), avoid=avoid)
        if stub is None:
            raise ValueError(f'ROM bank 0 has no {size} free bytes for the overlay routine, and there is no room for '
                             f'a {stub_size}-byte stub either.')

        def body_code(entry):
            if not probe:
                return _sm83_overlay_routine(entry, b'\xC9', records, vblank_only=after_handler)
            # Called with the probed bytes in H (and L); returns the bank they belong to in A.
            two = len(probe['offsets']) == 2
            items = [b'\xC5\xD5\x11', ('abs', 'banks'), b'\x06', bytes([len(probe['table'])]),   # push bc ; push de ; ld de,banks ; ld b,n
                     ('label', 'find'), b'\x1A\x13\xBC']                                        # ld a,[de] ; inc de ; cp h
            if two:
                items += [('jr', 0x20, 'miss'), b'\x1A\xBD', ('jr', 0x28, 'hit'), ('label', 'miss'), b'\x13']
            else:
                items += [('jr', 0x28, 'found')]
            items += [b'\x13\x05', ('jr', 0x20, 'find')]                                         # inc de ; dec b ; jr nz,find
            if two:
                items += [('jr', 0x18, 'found'), ('label', 'hit'), b'\x13']
            items += [('label', 'found'), b'\x1A\xF5\xCD', ('abs', 'work'), b'\xF1\xD1\xC1\xC9',   # ld a,[de] ; push af ; call work ; pop af ; pop de ; pop bc ; ret
                      ('label', 'banks'), b''.join(bytes(row) for row in probe['table']), b'\x01',   # (bank 1 when nothing matches)
                      ('label', 'work')]
            head = _assemble(items, entry)
            return head + _sm83_overlay_routine(entry + len(head), b'\xC9', records, vblank_only=after_handler)
        body_size = len(body_code(0x4000))
        base = rom
        placement = 'banked' if shadow else 'banked-probe' if probe else 'added-mapper'
        body = None if plain else find_free_space(rom, system, body_size, span=(0x4000, min(len(rom), 0x400000)),
                                                   avoid=list(avoid) + [(stub, stub + stub_size)])
        if body is None:
            if not grow or len(rom) & (len(rom) - 1) or len(rom) >= 0x400000 or (cart in (0x01, 0x02, 0x03) and banks >= 32):
                raise ValueError(f'ROM bank 0 has no {size} free bytes for the overlay routine, and there is no room for '
                                 'the routine in another bank.')
            if plain:
                # A cartridge without a mapper ignores writes to its ROM, and some games make them. Once it has
                # a mapper, such a write maps another bank at $4000. So the added banks are copies of the one
                # the game expects there, and the routine replaces only the last bytes of the last copy.
                grown = bytearray(rom) + rom[0x4000:0x8000] * 2
                grown[0x147] = 0x01
                body = len(grown) - body_size
            else:
                grown = bytearray(rom) + b'\xFF' * len(rom)
                body = len(rom)
            grown[0x148] = rom[0x148] + 1 if rom[0x148] < 8 else rom[0x148]
            base = bytes(grown)
            edited = bytearray(base)
            placement += '+added-rom' if not plain else ''
            notes.append(f'The ROM grows from {len(rom) >> 10} KB to {len(base) >> 10} KB to hold the routine'
                         + ('; the cartridge type becomes MBC1 so that the added part can be reached.' if plain else '.'))
        entry = 0x4000 + (body & 0x3FFF)
        code = body_code(entry)
        edited[body:body + len(code)] = code
        core = (before + b'\x3E' + bytes([body >> 14]) + b'\xEA\x00\x21'    # ld a,bank ; ld [$2100],a
                + b'\xCD' + entry.to_bytes(2, 'little') + after)
        if after_handler:   # call the game's handler first; it returns into the stub's work, whose ret ends the interrupt
            core = b'\xCD' + (stub + 3 + len(core) + 1).to_bytes(2, 'little') + core + b'\xC9'
        edited[stub:stub + stub_size] = core + tail
        edited[vec:vec + 3] = b'\xC3' + stub.to_bytes(2, 'little')
        details.update(placement=placement, routine_offset=body, routine_size=len(code), stub_offset=stub, stub_size=stub_size)
        if shadow:
            details.update(bank_variable=shadow['address'], bank_variable_uses=shadow['uses'])
            notes.append(f'The routine sits in ROM bank {body >> 14}; after it runs, the game\'s bank is restored from '
                         f'the game\'s own bank variable at ${shadow["address"]:04X}.')
        elif probe:
            details.update(bank_probe=[0x4000 + k for k in probe['offsets']], banks_told_apart=len(probe['table']))
            notes.append(f'The routine sits in ROM bank {body >> 14}. The stub finds out which bank the game has mapped '
                         f'by reading {len(probe["offsets"])} byte(s) of it, and maps that bank again afterwards.')
        final = fix_checksums(bytes(edited), rom, system)
        return EditPlan('overlay-control' if _control else 'overlay', _diff_writes(rom, final), len(final), {'vram': expect},
                        notes=notes, details=details)
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan('overlay-control' if _control else 'overlay', _diff_writes(rom, final), len(final), {'vram': expect},
                    notes=notes, details=details)


def _snes_overlay_routine(origin: int, records: bytes, resume: int, after: bool = False, vblank: bool = False,
                          idle: int = 0) -> bytes:
    """65816 overlay routine at bank-local address `origin`.

    Normally the work is done first and the routine ends with JML to the
    game's handler at `resume` (24-bit). With `after`, the routine first
    pushes a second interrupt frame and jumps to the game's handler; the
    handler's RTI then lands in the overlay work, whose own RTI returns to
    the interrupted program. The work then runs after the game's own
    video-memory transfers of that frame instead of before them.

    With `vblank` the work is skipped unless the picture chip reports the
    vertical blank ($4212 bit 7): needed when the routine hangs on the IRQ
    vector, which a game may also fire in the middle of the picture.

    With `idle` (a number of bytes: 8, or 16 for the wider test) the work is
    skipped unless the interrupted program was waiting: stopped on WAI, or
    inside a loop of at most that many bytes that stores nothing to a
    picture-chip register (one of the bytes from the interrupted
    instruction on is a branch back to it or before it, at most that many
    bytes back, and no instruction in between is a store to $21xx). The address register of video memory cannot be read back, so a
    transfer the game's main program has under way cannot be put right
    after the routine has used the register; a game that is waiting for the
    next frame has none under way.
    """
    items = []
    if after:
        items += [b'\x4B\xF4', ('abs', 'work'), b'\x08',        # phk ; pea work ; php
                  b'\x5C' + resume.to_bytes(3, 'little'),      # jml handler
                  ('label', 'work')]
    items += [
        b'\x08\xC2\x30',                      # php ; rep #$30          (16-bit A, X, Y)
        b'\x48\xDA\x5A\x8B\x4B\xAB',          # pha ; phx ; phy ; phb ; phk ; plb
    ]
    if vblank:
        # sep #$20 ; lda $004212 ; rep #$20 ; bmi + ; jmp done      (rep leaves the sign flag of the load)
        items += [b'\xE2\x20\xAF\x12\x42\x00\xC2\x20\x30\x03\x4C', ('abs', 'done')]
    if idle:
        # Above the eight bytes saved here lies the interrupt frame: flags at 9,s, return address at 10,s, bank at 12,s.
        items += [
            b'\xA3\x0A\xAA',                          # lda 10,s ; tax          (x = return address)
            b'\xE2\x20\xA3\x0C\x48\xAB',              # sep #$20 ; lda 12,s ; pha ; plb   (read the interrupted program's bank)
            b'\xCA\xBD\x00\x00\xE8\xC9\xCB',          # dex ; lda 0,x ; inx ; cmp #$CB    (the instruction before was WAI)
            ('jr', 0xF0, 'idle'),
            b'\xA0\x02\x00',                          # ldy #2                  (y = bytes scanned + 2)
            ('label', 'scan'),
            b'\xBD\x00\x00\xC9\x80', ('jr', 0xF0, 'branch'),      # lda 0,x ; cmp #$80 ; beq branch        (bra)
            b'\x29\x1F\xC9\x10', ('jr', 0xD0, 'nobranch'),        # and #$1F ; cmp #$10 ; bne nobranch     (bpl ... beq)
            ('label', 'branch'),
            b'\xBD\x01\x00\xC9' + bytes([256 - idle]), ('jr', 0x90, 'nobranch'),   # lda 1,x ; cmp #-n ; bcc nobranch  (forward, or more than n back)
            b'\x98\x18\x7D\x01\x00',                              # tya ; clc ; adc 1,x    (zero or negative: it reaches the pc or before)
            ('jr', 0xF0, 'loop'), ('jr', 0x30, 'loop'),
            ('label', 'nobranch'),
            b'\xE8\xC8\xC0' + bytes([idle + 2]) + b'\x00', ('jr', 0xD0, 'scan'),   # inx ; iny ; cpy #n+2 ; bne scan
            ('label', 'busy'),
            b'\xC2\x20\x4C', ('abs', 'done'),                     # rep #$20 ; jmp done    (busy: leave everything alone)
            ('label', 'loop'),                                    # a short loop around the pc: does it store to $21xx?
            b'\xA0' + bytes([idle]) + b'\x00',                    # ldy #n
            ('label', 'body'),
            b'\xCA\xBD\x02\x00\xC9\x21', ('jr', 0xD0, 'plain'),   # dex ; lda 2,x ; cmp #$21 ; bne plain
            b'\xBD\x00\x00\x29\xEC\xC9\x8C', ('jr', 0xF0, 'busy'),  # lda 0,x ; and #$EC ; cmp #$8C ; beq busy   (sta/stx/sty/stz $21xx)
            ('label', 'plain'),
            b'\x88', ('jr', 0xD0, 'body'),                        # dey ; bne body
            ('label', 'idle'),
            b'\xC2\x20\x4B\xAB',                      # rep #$20 ; phk ; plb
        ]
    items += [
        b'\xE2\x20\xA9\x80\x8F\x15\x21\x00\xC2\x20',   # sep #$20 ; lda #$80 ; sta $002115 ; rep #$20
        b'\xA2', ('abs', 'table'),             # ldx #table
        ('label', 'next'),
        b'\xBD\x00\x00\xC9\xFF\xFF', ('jr', 0xF0, 'done'),      # lda 0,x ; cmp #$FFFF ; beq done
        b'\x8F\x16\x21\x00',                  # sta $002116            (address of the key word)
        b'\xAF\x39\x21\x00\xAF\x39\x21\x00',  # lda $002139 twice       (first read is the stale buffer)
        b'\xDD\x02\x00', ('jr', 0xD0, 'skip'),  # cmp 2,x ; bne skip
        b'\xBD\x04\x00\x8F\x16\x21\x00',      # lda 4,x ; sta $002116   (tile address)
        b'\xAF\x39\x21\x00',                  # lda $002139            (stale buffer)
        b'\xBD\x06\x00\xA8\xDA',              # lda 6,x ; tay ; phx    (word count)
        ('label', 'cmp'),
        b'\xAF\x39\x21\x00\xDD\x08\x00', ('jr', 0xD0, 'nomatch'),
        b'\xE8\xE8\x88', ('jr', 0xD0, 'cmp'),   # inx ; inx ; dey ; bne cmp
        b'\xFA\xDA',                          # plx ; phx
        b'\xBD\x04\x00\x8F\x16\x21\x00',      # lda 4,x ; sta $002116
        b'\xBD\x06\x00\xA8',                  # lda 6,x ; tay
        b'\x0A\x18\x63\x01\xAA',              # asl ; clc ; adc 1,s ; tax   (x = record + 2 * count: the new words)
        ('label', 'cpy'),
        b'\xBD\x08\x00\x8F\x18\x21\x00',      # lda 8,x ; sta $002118
        b'\xE8\xE8\x88', ('jr', 0xD0, 'cpy'),
        ('label', 'nomatch'),
        b'\xFA',                              # plx
        ('label', 'skip'),
        b'\xBD\x06\x00\x0A\x0A\x18\x69\x08\x00',   # lda 6,x ; asl ; asl ; clc ; adc #8
        b'\x48\x8A\x18\x63\x01\xAA\x68',      # pha ; txa ; clc ; adc 1,s ; tax ; pla
        ('jr', 0x80, 'next'),                 # bra next
        ('label', 'done'),
        b'\xAB\x7A\xFA\x68\x28',              # plb ; ply ; plx ; pla ; plp
        b'\x40' if after else b'\x5C' + resume.to_bytes(3, 'little'),   # rti, or jml to the game's handler
        ('label', 'table'), records, b'\xFF\xFF',
    ]
    return _assemble(items, origin)


def _genesis_overlay_routine(records: bytes, resume: int, guard=True, after: bool = False, port: int = 0xC00000) -> bytes:
    """Position-independent 68000 overlay routine; ends with JMP to `resume`.

    With `guard`, the routine does nothing in a frame in which any address
    register of the interrupted program holds a VDP port address
    ($C00000-$C00007). Games keep the port in a register while they stream
    data into video memory from their main loop; sending a command of our
    own in the middle of that would redirect the rest of their data.

    With `guard='idle'` it also does nothing unless the interrupted program
    was waiting: stopped on a STOP instruction, or inside a loop of a few
    instructions (one of the eight words from the interrupted instruction on
    is a short branch back to it or before it, at most 16 bytes back). A
    game that is waiting for the next frame is not in the middle of a
    transfer of its own.

    With `after`, the routine first pushes a second exception frame and
    jumps to the game's handler; the handler's RTE then lands in the overlay
    work, whose own RTE returns to the interrupted program. The game's
    handler then starts on time and does its own transfers first.
    """
    code = bytearray()
    if after:
        code += bytes.fromhex('487A000A' '40E7') + b'\x4E\xF9' + resume.to_bytes(4, 'big')   # pea work(pc) ; move.w sr,-(sp) ; jmp handler
    start_at = len(code)
    leave = bytes.fromhex('4E73') + bytes(4) if after else b'\x4E\xF9' + resume.to_bytes(4, 'big')   # rte, or jmp handler
    code += bytes.fromhex('48E7E0E0')            # movem.l d0-d2/a0-a2,-(sp)
    if guard:
        checks = len(code)
        bail = checks + 7 * 6 + 2
        chk = bail + 10
        for n in range(7):
            code += bytes((0x20, 0x08 + n))                              # move.l aN,d0
            code += bytes((0x61, chk - (len(code) + 2)))                 # bsr.s chk
            code += bytes((0x67, bail - (len(code) + 2)))                # beq.s bail
        code += bytes((0x60, 10 + 14))                                   # bra.s start
        code += bytes.fromhex('4CDF0707') + leave                        # bail: restore ; jmp handler (or rte)
        code += bytes.fromhex('028000FFFFF8' '0C8000C00000' '4E75')      # chk: andi.l #$FFFFF8,d0 ; cmpi.l #$C00000,d0 ; rts
    if guard in _IDLE_BYTES:
        code += bytes.fromhex('206F001A')                                # movea.l 26(sp),a0      (interrupted pc)
        code += bytes.fromhex('0C684E72FFFC')                            # cmpi.w #$4E72,-4(a0)   (it was stopped)
        idle_at = len(code)
        code += bytes.fromhex('6700')                                    # beq.s idle
        code += bytes.fromhex('7407')                                    # moveq #7,d2
        scan = len(code)
        code += bytes.fromhex('3018' '3200' '0241F080' '0C416080')       # move.w (a0)+,d0 ; move.w d0,d1 ; andi.w #$F080,d1 ; cmpi.w #$6080,d1
        code += bytes.fromhex('6612')                                    # bne.s n               (not a short backward branch)
        code += bytes.fromhex('0C0000') + bytes([256 - 2 * _IDLE_BYTES[guard]]) + bytes.fromhex('650C')   # cmpi.b #-n,d0 ; bcs.s n  (further back: not a wait loop)
        code += bytes.fromhex('4880' '45F00000' 'B5EF001A')              # ext.w d0 ; lea (a0,d0.w),a2 ; cmpa.l 26(sp),a2
        idle2_at = len(code)
        code += bytes.fromhex('6300')                                    # bls.s idle            (it branches to the pc or before)
        code += bytes((0x51, 0xCA)) + ((scan - (len(code) + 2)) & 0xFFFF).to_bytes(2, 'big')   # n: dbf d2,scan
        code += bytes((0x60, (bail - (len(code) + 2)) & 0xFF))           # bra.s bail
        code[idle_at + 1] = len(code) - (idle_at + 2)
        code[idle2_at + 1] = len(code) - (idle2_at + 2)
    lea_at = len(code)
    code += bytes.fromhex('41FA0000')            # lea table(pc),a0
    code += bytes.fromhex('43F9') + port.to_bytes(4, 'big')   # lea $C00000,a1          (data port; control port at 4(a1))
    nxt = len(code)
    code += bytes.fromhex('2018')                # move.l (a0)+,d0         (read command for the key word)
    bmi_at = len(code)
    code += bytes.fromhex('6B00')                # bmi.s done
    code += bytes.fromhex('23400004')            # move.l d0,4(a1)
    code += bytes.fromhex('3211')                # move.w (a1),d1
    code += bytes.fromhex('B258')                # cmp.w (a0)+,d1
    bne1_at = len(code)
    code += bytes.fromhex('6600')                # bne.s skip
    code += bytes.fromhex('337C8F020004')        # move.w #$8F02,4(a1)     (address step 2, only when a tile was just loaded)
    code += bytes.fromhex('23500004')            # move.l (a0),4(a1)       (read command for the tile)
    code += bytes.fromhex('45E80008')            # lea 8(a0),a2            (the original tile)
    code += bytes.fromhex('740F')                # moveq #15,d2
    code += bytes.fromhex('3211B25A56CAFFFA')    # cmp: move.w (a1),d1 ; cmp.w (a2)+,d1 ; dbne d2,cmp
    bne2_at = len(code)
    code += bytes.fromhex('6600')                # bne.s skip
    code += bytes.fromhex('236800040004')        # move.l 4(a0),4(a1)      (write command for the tile)
    code += bytes.fromhex('740F')                # moveq #15,d2
    code += bytes.fromhex('329A51CAFFFC')        # cpy: move.w (a2)+,(a1) ; dbf d2,cpy
    skip = len(code)
    code += bytes.fromhex('41E80048')            # lea 72(a0),a0           (next record)
    code += bytes([0x60, (nxt - (len(code) + 2)) & 0xFF])      # bra.s next
    done = len(code)
    code += bytes.fromhex('4CDF0707')            # movem.l (sp)+,d0-d2/a0-a2
    code += leave                                # jmp handler (or rte)
    table = len(code)
    code[bmi_at + 1] = done - (bmi_at + 2)
    code[bne1_at + 1] = skip - (bne1_at + 2)
    code[bne2_at + 1] = skip - (bne2_at + 2)
    code[lea_at + 2:lea_at + 4] = (table - (lea_at + 2)).to_bytes(2, 'big')
    return bytes(code) + records + b'\xFF\xFF\xFF\xFF'


def _genesis_overlay_patch(edits, rom, system, avoid, guard=True, after=False, control=None) -> EditPlan:
    vector = 0x78
    if len(rom) < 0x200:
        raise ValueError('Not a Mega Drive ROM image.')
    handler = int.from_bytes(rom[vector:vector + 4], 'big')
    if handler in (0, 0xFFFFFFFF) or handler & 1:
        raise ValueError('This game has no vertical-blank interrupt handler to hook.')
    records = bytearray()
    expect: dict[int, int] = {}

    def command(address, write):
        return ((0x40000000 if write else 0) | (address & 0x3FFF) << 16 | address >> 14).to_bytes(4, 'big')

    for tile, pixels in edits:
        new = encode_tile(pixels, tile.format) if not isinstance(pixels, (bytes, bytearray)) else bytes(pixels)
        a = tile.addresses[0]
        if tile.domain != 'vram' or a & 1 or len(tile.stored) != 32 or len(new) != 32 or tile.addresses[-1] - a != 31:
            raise ValueError('The overlay edits whole 32-byte tiles in video memory.')
        diff = [k for k in range(32) if new[k] != tile.stored[k]]
        if not diff:
            continue
        key = diff[0] & ~1
        records += command(a + key, False) + tile.stored[key:key + 2] + command(a, False) + command(a, True)
        records += tile.stored + new
        expect.update({a + k: new[k] for k in diff})
    if not records:
        raise ValueError('The edit changes nothing.')
    if control:
        # Same routine and table shape, but every "port" access goes to eight ROM bytes behind the routine:
        # reads return the word there, writes do nothing. 'high' makes every compare succeed (the cost of a
        # frame in which the tile is rewritten), 'low' makes the first one fail (the cost of every other frame).
        word = b'\x5A\xA5'
        key = word if control == 'high' else b'\xA5\x5A'
        n = len(records) // 78
        records = bytearray((command(0, False) + key + command(0, False) + command(0, True) + word * 16 + bytes(32)) * n)
        expect = {}
        code = _genesis_overlay_routine(bytes(records), handler, guard, after) + word + bytes(6)
    else:
        code = _genesis_overlay_routine(bytes(records), handler, guard, after)
    edited = bytearray(rom)
    notes = ['The game unpacks this tile in a way ROMancer does not decode, so the edit is applied '
             'by a small added routine each frame instead of changing the stored data.',
             'It applies wherever the game shows this exact tile in this tile slot.']
    where = find_free_space(rom, system, len(code), same_bank=False, avoid=avoid, span=(0x200, min(len(rom), 0x400000)))
    placement = 'free-rom'
    if where is None:
        where = len(rom) + (len(rom) & 1)
        if where + len(code) > 0x400000:
            raise ValueError('The ROM has no free space for the overlay routine and cannot grow.')
        edited += b'\xFF' * (where + len(code) + (len(code) & 1) - len(rom))
        placement = 'added-rom'
        notes.append(f'The ROM grows by {len(edited) - len(rom)} bytes to hold the routine.')
    if control:
        code = _genesis_overlay_routine(bytes(records), handler, guard, after, port=where + len(code) - 8) + word + bytes(6)
    edited[where:where + len(code)] = code
    edited[vector:vector + 4] = where.to_bytes(4, 'big')
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan('overlay-control' if control else 'overlay', _diff_writes(rom, final), len(final), {'vram': expect}, notes=notes,
                    details={'routine_size': len(code), 'routine_offset': where, 'hook_offset': vector, 'placement': placement,
                             'tiles': len(records) // 78, 'cpu': '68000', 'handler': handler,
                             'guard': 'works only while the interrupted program is waiting in a short loop and holds '
                                      'no VDP port in an address register' if guard in _IDLE_BYTES else
                                      'skips frames in which the interrupted program holds a VDP port in an '
                                      'address register' if guard else 'none',
                             'timing': 'after the game\'s handler' if after else 'before the game\'s handler'})


def _snes_exhirom(rom: bytes) -> bool:
    """A HiROM image of more than 4 MB whose header sits in its second part ($40FFC0)."""
    skip = rom_skip(rom, 'snes')
    h = skip + 0x40FFC0
    if len(rom) - skip <= 0x400000 or h + 0x20 > len(rom):
        return False
    return (rom[h + 0x15] & 0x0F) == 5 and all(0x20 <= c < 0x7F for c in rom[h:h + 21])


def _snes_address(rom: bytes, file_offset: int) -> int:
    """24-bit CPU address of a ROM file offset (LoROM, HiROM or ExHiROM; fast mirror)."""
    o = file_offset - rom_skip(rom, 'snes')
    if _snes_exhirom(rom):
        return ((0xC0 + (o >> 16)) if o < 0x400000 else (0x40 + ((o - 0x400000) >> 16))) << 16 | (o & 0xFFFF)
    if _snes_hirom(rom):
        return (0xC0 | o >> 16) << 16 | (o & 0xFFFF)
    return (0x80 | o >> 15) << 16 | 0x8000 | (o & 0x7FFF)


# Four bytes in ROM bank 0 that can hold a JML, best first: (offset from $00:8000, needs to be blank).
# The processor never fetches the reserved vector slots ($FFE0-$FFE3, $FFF0-$FFF3, $FFF6-$FFF7) and the console
# does not wire the ABORT pin ($FFF8-$FFF9), so those bytes are free whatever a cartridge happens to hold there.
_SNES_STUB_SLOTS = ((0x7FE0, True), (0x7FF0, True), (0x7FE0, False), (0x7FF0, False), (0x7FF6, False))


_SNES_POLL_IDIOMS = (b'\xAD\x10\x42\x10\xFB', b'\x2C\x10\x42\x10\xFB', b'\xAD\x12\x42\x10\xFB', b'\x2C\x12\x42\x10\xFB')


def _snes_poll_sites(rom: bytes, most: int = 16) -> tuple[list, bytes]:
    """Places where a game waits for the vertical blank by polling: (file offsets, the five-byte loop found there).

    The loops looked for are `lda $4210 ; bpl *-3` and its variants with BIT
    and with $4212. The form that occurs most often is returned; a ROM with
    more than `most` such places is left alone (the bytes are then too
    likely to be something else).
    """
    best: tuple[list, bytes] = ([], b'')
    for idiom in _SNES_POLL_IDIOMS:
        found = []
        at = rom.find(idiom)
        while at >= 0:
            found.append(at)
            at = rom.find(idiom, at + 1)
        if len(best[0]) < len(found) <= most:
            best = (found, idiom)
    return best


def _snes_stub_slot(rom: bytes, system: str, bank0: int, avoid=()) -> tuple[int, str]:
    """Four bytes in ROM bank 0 for a JML: blank reserved vector slots, then any free bytes, then the reserved
    slots whatever they hold (see _SNES_STUB_SLOTS). Returns (file offset, what it is)."""
    for o, blank in _SNES_STUB_SLOTS:
        if blank and rom[bank0 + o:bank0 + o + 4] in (bytes(4), b'\xFF' * 4):
            return bank0 + o, 'blank vector slot'
    stub = find_free_space(rom, system, 4, span=(bank0, bank0 + 0x7FB0), avoid=avoid)
    if stub is not None:
        return stub, 'free bytes in bank 0'
    return bank0 + next(o for o, blank in _SNES_STUB_SLOTS if not blank), 'unused vector slot'


def _snes_grown(rom: bytes) -> bytes | None:
    """`rom` grown to the next power-of-two size (at most 4 MB), new part filled with FF, size byte updated."""
    skip = rom_skip(rom, 'snes')
    size = len(rom) - skip
    if size >= 0x400000 or _snes_exhirom(rom):
        return None
    grown = min(0x400000, 1 << size.bit_length())     # a power of two doubles; an irregular size rounds up
    out = bytearray(rom) + b'\xFF' * (grown - size)
    h = skip + (0xFFC0 if _snes_hirom(rom) else 0x7FC0)
    if 0x08 <= out[h + 0x17] <= 0x0D:               # header size byte: log2 of the size in KB
        out[h + 0x17] = max(out[h + 0x17], ((grown >> 10) - 1).bit_length())
    return bytes(out)


def _snes_overlay_patch(edits, rom, system, avoid, after=False, hook='nmi', grow=True, control=None, idle=0) -> EditPlan:
    skip = rom_skip(rom, system)
    exhi = _snes_exhirom(rom)
    bank0 = skip + (0x408000 if exhi else 0x8000 if _snes_hirom(rom) else 0)     # file offset of $00:8000
    if hook not in ('nmi', 'irq', 'poll'):
        raise ValueError("hook is 'nmi', 'irq' or 'poll'")
    vector = bank0 + (0x7FEA if hook == 'nmi' else 0x7FEE)
    if len(rom) < bank0 + 0x8000:
        raise ValueError('Not a Super NES ROM image.')
    handler = rom[vector] | rom[vector + 1] << 8
    # A vector into RAM ($0000-$1FFF) is a game that builds its handler jump there at run time; that still works,
    # the routine just ends by jumping to that RAM address. $FFFF, or $0000 with nothing else in the table, is no handler.
    table = rom[bank0 + 0x7FE4:bank0 + 0x7FF0]
    if hook != 'poll' and (handler == 0xFFFF or (handler == 0 and not any(table)) or 0x2000 <= handler < 0x8000):
        raise ValueError('This game has no vertical-blank interrupt handler to hook.' if hook == 'nmi' else
                         'This game has no IRQ handler to hook.')
    sites, idiom = _snes_poll_sites(rom) if hook == 'poll' else ([], b'')
    if hook == 'poll' and not sites:
        raise ValueError('This game has no loop that waits for the vertical blank by reading $4210 or $4212.')
    records = bytearray()
    expect: dict[int, int] = {}
    for tile, pixels in edits:
        new = encode_tile(pixels, tile.format) if not isinstance(pixels, (bytes, bytearray)) else bytes(pixels)
        a = tile.addresses[0]
        n = len(tile.stored)
        if tile.domain != 'vram' or a & 1 or n & 1 or len(new) != n or tile.addresses[-1] - a + 1 != n:
            raise ValueError('The overlay edits whole tiles stored as consecutive words of video memory.')
        diff = [k for k in range(n) if new[k] != tile.stored[k]]
        if not diff:
            continue
        key = diff[0] & ~1
        records += ((a + key) >> 1).to_bytes(2, 'little') + tile.stored[key:key + 2]
        records += (a >> 1).to_bytes(2, 'little') + (n // 2).to_bytes(2, 'little') + tile.stored + new
        expect.update({a + k: new[k] for k in diff})
    if not records:
        raise ValueError('The edit changes nothing.')
    if control:
        # Same routine and table shape, with the picture chip's registers replaced by four ROM bytes behind the
        # routine: reads return the word there, writes do nothing. 'high' makes every compare succeed (the cost
        # of a frame in which the tile is rewritten), 'low' makes the first one fail (every other frame).
        word = b'\x5A\xA5'
        made = bytearray()
        for tile, _ in edits:
            n = len(tile.stored)
            made += bytes(2) + (word if control == 'high' else b'\xA5\x5A') + bytes(2) + (n // 2).to_bytes(2, 'little') + word * (n // 2) + bytes(n)
        records, expect = made, {}
    records = bytes(records)
    vblank = hook == 'irq'

    def routine(origin, bank=0):
        if hook == 'poll':
            # the game's own wait, then the work, then back to the game (rtl in place of the jump to a handler)
            code = bytearray(_snes_overlay_routine(origin + len(idiom), records, 0))
            at = len(code) - len(records) - 6
            code[at:at + 4] = b'\x6B\xEA\xEA\xEA'
            return idiom + bytes(code)
        code = _snes_overlay_routine(origin, records, handler, after, vblank, idle)
        if not control:
            return code
        head = bytearray(code[:len(code) - len(records) - 2])
        dummy = origin + len(code)
        read = bytes((dummy & 0xFF, dummy >> 8 & 0xFF, bank))
        write = bytes(((dummy + 2) & 0xFF, (dummy + 2) >> 8 & 0xFF, bank))
        for old, new in ((b'\x8F\x15\x21\x00', b'\x8F' + write), (b'\x8F\x16\x21\x00', b'\x8F' + write),
                         (b'\x8F\x18\x21\x00', b'\x8F' + write), (b'\xAF\x39\x21\x00', b'\xAF' + read)):
            head = head.replace(old, new)
        return bytes(head) + code[len(head):] + word + bytes(2)
    size = len(routine(0))
    notes = ['The game unpacks this tile in a way ROMancer does not decode, so the edit is applied '
             'by a small added routine each frame instead of changing the stored data.',
             'It applies wherever the game shows this exact tile in this tile slot.',
             'The routine sets the video-memory address and increment registers each frame.']
    stub, stub_kind = (None, None) if hook == 'poll' else _snes_stub_slot(rom, system, bank0, avoid)
    taken = list(avoid) + ([(stub, stub + 4)] if stub is not None else [(s, s + 5) for s in sites])
    base = rom
    body = find_free_space(rom, system, size, near=bank0, same_bank=False, avoid=taken,
                           span=(skip, min(len(rom), skip + 0x400000)))
    placement = 'free-rom'
    if body is None and grow:
        grown = _snes_grown(rom)
        if grown is not None:
            base = grown
            body = len(rom) + 4
            placement = 'added-rom'
            notes.append(f'The ROM has no free space for the routine, so it grows from {(len(rom) - skip) >> 10} KB to '
                         f'{(len(grown) - skip) >> 10} KB. A game that relies on its data repeating beyond its old size '
                         'would be disturbed; the replay shows whether this one is.')
    if body is None:
        raise ValueError(f'The ROM has no {size} free bytes for the overlay routine' +
                         (' and cannot grow.' if grow else '.'))
    address = _snes_address(base, body)
    code = routine(address & 0xFFFF, address >> 16)
    bank = 0x10000 if _snes_hirom(rom) else 0x8000
    if (body - skip) // bank != (body + len(code) - 1 - skip) // bank:
        raise ValueError('The free space found for the overlay routine crosses a bank boundary.')
    edited = bytearray(base)
    edited[body:body + len(code)] = code
    if hook == 'poll':
        for s in sites:
            edited[s:s + 5] = b'\x22' + address.to_bytes(3, 'little') + b'\xEA'     # jsl routine ; nop
        notes.append(f'This game does not take a vertical-blank interrupt in this scene; it waits for the vertical '
                     f'blank in a loop. The routine is called from that wait ({len(sites)} place(s) in the ROM).')
    else:
        edited[stub:stub + 4] = b'\x5C' + address.to_bytes(3, 'little')
        stub_address = 0x8000 + (stub - bank0)
        edited[vector:vector + 2] = stub_address.to_bytes(2, 'little')
    final = fix_checksums(bytes(edited), rom, system)
    if hook == 'irq':
        notes.append('The routine hangs on the IRQ vector (this game does not use the vertical-blank interrupt) and '
                     'only works while the picture chip reports the vertical blank.')
    return EditPlan('overlay-control' if control else 'overlay', _diff_writes(rom, final), len(final), {'vram': expect}, notes=notes,
                    details={'routine_size': len(code), 'routine_offset': body, 'stub_offset': stub, 'stub': stub_kind,
                             'hook_offset': sites[0] if hook == 'poll' else vector, 'hook': hook, 'hook_sites': len(sites) or 1,
                             'placement': placement, 'tiles': len(edits),
                             'cpu': '65816', 'handler': handler,
                             'guard': f'works only while the interrupted program is waiting (WAI or a loop of at most {idle} bytes)'
                                      if idle else 'none',
                             'timing': 'after the game\'s handler' if after else 'before the game\'s handler'})


def plan_overlay_control(edits: list, rom: bytes, system: str, *, cost: str = 'high', avoid: Iterable[tuple[int, int]] = (),
                         after_handler: bool = False, guard=True, hook: str = 'nmi', grow: bool = True) -> EditPlan:
    """The overlay routine for `edits` with its video ports replaced by ROM bytes: a control that costs the
    same processor time each frame but reads and writes nothing in the video chip.

    plan_hook_only tells whether a game's run changes when a few cycles are
    added; this tells whether it changes when the cycles of the real routine
    are added. `cost='high'` takes the path of a frame in which the tile is
    rewritten, `cost='low'` the path of every other frame. When a run with
    the overlay differs from the original run and the runs with these
    controls do not, the difference is the overlay's video access and not
    its timing. Super NES, Mega Drive and Game Boy (where video memory is
    plain memory, so the control simply writes back what it reads).
    `expect` is empty.
    """
    cpu = CPU[system]
    if cost not in ('high', 'low'):
        raise ValueError("cost is 'high' or 'low'")
    if not edits:
        raise ValueError('The control is built for the tiles of an overlay.')
    if cpu == '65816':
        return _snes_overlay_patch(edits, rom, system, avoid, after_handler, hook, grow, control=cost,
                                   idle=_IDLE_BYTES.get(guard, 0))
    if cpu == '68000':
        return _genesis_overlay_patch(edits, rom, system, avoid, guard, after_handler, control=cost)
    if cpu == 'sm83':
        return plan_overlay_patch(edits, rom, system, avoid=avoid, grow=grow, _control=cost)
    raise ValueError('There is no cost-matched control for this processor; use plan_hook_only.')


def plan_hook_only(rom: bytes, system: str, *, avoid: Iterable[tuple[int, int]] = (), hook: str = 'nmi') -> EditPlan:
    """The overlay's interrupt hook with no work behind it: a control for measurements.

    Adding any code to an interrupt handler makes a game run a few processor
    cycles later, and some games then take a different course (a sound
    handshake that completes a frame later, a random number seeded from a
    counter). A run of the overlay that differs from the original run can
    therefore be the overlay's doing or just that. Running this plan the
    same way tells the two apart: when the hook alone already changes the
    run, the original run is no reference for this game.

    The plan expects no change anywhere (`expect` is empty).
    """
    cpu = CPU[system]
    if cpu == '6502':
        from . import gfx_overlay8
        return gfx_overlay8.nes_overlay_patch([], rom, system, avoid, null=True)
    if cpu == 'z80':
        from . import gfx_overlay8
        return gfx_overlay8.sms_overlay_patch([], rom, system, avoid, null=True, hook='poll' if hook == 'poll' else 'irq')
    edited = bytearray(rom)
    details = {'cpu': cpu}
    if cpu == '65816' and hook == 'poll':
        sites, idiom = _snes_poll_sites(rom)
        if not sites:
            raise ValueError('This game has no loop that waits for the vertical blank by reading $4210 or $4212.')
        skip = rom_skip(rom, system)
        where = find_free_space(rom, system, len(idiom) + 1, same_bank=False, avoid=list(avoid) + [(s, s + 5) for s in sites],
                                span=(skip, min(len(rom), skip + 0x400000)))
        if where is None:
            raise ValueError('The ROM has no free bytes for the hook.')
        edited[where:where + len(idiom) + 1] = idiom + b'\x6B'                   # the game's wait ; rtl
        for s in sites:
            edited[s:s + 5] = b'\x22' + _snes_address(rom, where).to_bytes(3, 'little') + b'\xEA'
        details.update(hook_offset=sites[0], routine_offset=where, hook=hook, hook_sites=len(sites))
    elif cpu == '65816':
        skip = rom_skip(rom, system)
        bank0 = skip + (0x408000 if _snes_exhirom(rom) else 0x8000 if _snes_hirom(rom) else 0)
        vector = bank0 + (0x7FEA if hook == 'nmi' else 0x7FEE)
        if len(rom) < bank0 + 0x8000:
            raise ValueError('Not a Super NES ROM image.')
        handler = rom[vector] | rom[vector + 1] << 8
        if handler == 0xFFFF or (handler == 0 and not any(rom[bank0 + 0x7FE4:bank0 + 0x7FF0])) or 0x2000 <= handler < 0x8000:
            raise ValueError('This game has no interrupt handler to hook.')
        stub = _snes_stub_slot(rom, system, bank0, avoid)[0]
        edited[stub:stub + 4] = b'\x5C' + handler.to_bytes(3, 'little')
        edited[vector:vector + 2] = (0x8000 + (stub - bank0)).to_bytes(2, 'little')
        details.update(hook_offset=vector, stub_offset=stub, hook=hook)
    elif cpu == '68000':
        vector = 0x78
        handler = int.from_bytes(rom[vector:vector + 4], 'big')
        if len(rom) < 0x200 or handler in (0, 0xFFFFFFFF) or handler & 1:
            raise ValueError('This game has no vertical-blank interrupt handler to hook.')
        where = find_free_space(rom, system, 6, same_bank=False, avoid=avoid, span=(0x200, min(len(rom), 0x400000)))
        if where is None:
            where = len(rom) + (len(rom) & 1)
            edited += b'\xFF' * (where + 6 - len(rom))
        edited[where:where + 6] = b'\x4E\xF9' + handler.to_bytes(4, 'big')
        edited[vector:vector + 4] = where.to_bytes(4, 'big')
        details.update(hook_offset=vector, routine_offset=where)
    else:
        tail, _ = _sm83_displaced(rom, 0x40)
        where = find_free_space(rom, system, len(tail), span=(0x68, 0x4000), avoid=avoid)
        if where is None:
            raise ValueError('ROM bank 0 has no free bytes for the hook.')
        edited[where:where + len(tail)] = tail
        edited[0x40:0x43] = b'\xC3' + where.to_bytes(2, 'little')
        details.update(hook_offset=0x40, routine_offset=where)
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan('hook-only', _diff_writes(rom, final), len(final), {}, details=details,
                    notes=['Only the interrupt hook, with no work behind it: a control for timing.'])


# ---------------------------------------------------------------------------
# One entry point for tiles that cannot be written in place
# ---------------------------------------------------------------------------

# The overlay's variants per processor, from the most careful to the least: plan_overlay_patch keyword arguments.
OVERLAY_VARIANTS = {
    'sm83': [{}, {'after_handler': True}],
    '6502': [{'guard': True}, {'guard': False}],
    'z80': [{'guard': True}, {'guard': False}, {'after_handler': True}, {'hook': 'poll'}],
    '68000': [{'guard': 'idle'}, {'guard': 'idle', 'after_handler': True}, {'guard': 'idle-wide'}, {'guard': True},
              {'guard': False}, {'guard': False, 'after_handler': True}],
    '65816': [{'guard': 'idle'}, {'guard': 'idle', 'after_handler': True}, {'guard': 'idle-wide'}, {'after_handler': False},
              {'after_handler': True}, {'hook': 'irq'}, {'hook': 'irq', 'after_handler': True}, {'hook': 'poll'}],
}
_SAFETY_RANK = {'clean': 0, 'timing': 1, 'differs': 2, 'unmeasured': 3, 'disturbed': 4}


def plan_derived_tile_edit(tile: Tile, pixels, rom: bytes, scene: Scene, *, verify: Callable[[EditPlan], dict],
                           avoid: Iterable[tuple[int, int]] = (), codecs: Iterable[str] | None = None,
                           max_candidates: int = 24, safety: Callable | None = None) -> EditPlan:
    """Plan and confirm an edit to a computed, unpacked or packed tile.

    Tries, in order: (1) a recognised codec, re-encoded in place or relocated
    and repointed; (2) the overlay fallback in each of its variants for the
    processor (OVERLAY_VARIANTS), from the most careful guard to none (and,
    on Super NES and Master System, from another hook when the
    vertical-blank one never runs). `verify(plan)` must run verify_plan; the
    first plan whose replay comes out as planned is returned with
    `.verified` set. Raises ValueError, listing what was tried, when nothing
    is confirmed.

    `safety(plan, edits, options)`, when given, must run overlay_safety (it
    needs the recorded run from power-on, which only the caller has) and
    return its result. The search then goes on past an overlay that replays
    as planned but is not clean from power-on, and returns the variant with
    the best outcome ('clean' ends the search). The outcome is stored in
    `details['safety']`; the options used are in `details['options']`.
    """
    new = encode_tile(pixels, tile.format)
    changes = {a: new[k] for k, a in enumerate(tile.addresses) if new[k] != tile.stored[k]}
    if not changes:
        raise ValueError('The edit changes nothing.')
    tried = []
    contiguous = tile.addresses[-1] - tile.addresses[0] + 1 == len(tile.addresses)
    if tile.domain != 'chr_rom' and contiguous:
        block = find_compressed_block(scene, rom, tile.system, tile.domain, tile.addresses[0], len(tile.addresses), codecs)
        if block is None:
            tried.append('no known codec reproduces this tile')
        else:
            try:
                plan = plan_block_edit(block, changes, rom, tile.system, verify=verify, avoid=avoid,
                                       max_candidates=max_candidates)
                result = verify(plan)
                plan.verified = result
                if result.get('as_planned'):
                    return plan
                tried.append(f'{block.codec} re-encode did not replay as planned')
            except ValueError as e:
                tried.append(f'{block.codec}: {e}')
    cpu = CPU[tile.system]
    edits = [(tile, list(pixels))]
    fired = False
    best = None
    for options in OVERLAY_VARIANTS[cpu]:
        if options.get('hook') in ('irq', 'poll') and fired:
            continue        # the vertical-blank hook does run in this game; hanging on another hook would not help
        try:
            plan = plan_overlay_patch(edits, rom, tile.system, avoid=avoid, scene=scene, **options)
            result = verify(plan)
            plan.verified = result
            plan.details['options'] = dict(options)
            fired = fired or bool(result.get('verified'))
            if not result.get('as_planned'):
                tried.append('overlay did not replay as planned' + (f' ({options})' if options else ''))
                continue
            if safety is None:
                best = (0, plan)
                break
            outcome = safety(plan, edits, options)
            plan.details['safety'] = outcome['state']
            rank = _SAFETY_RANK.get(outcome['state'], 3)
            if best is None or rank < best[0]:
                best = (rank, plan)
            if rank == 0:
                break
            tried.append(f'overlay replays as planned but the run from power-on is "{outcome["state"]}"'
                         + (f' ({options})' if options else ''))
            hook_only = outcome.get('hook_only') or {}
            if 'clean' in hook_only and not hook_only['clean']:
                break       # even the bare hook changes this game's run: no variant can reproduce it
        except ValueError as e:
            if f'overlay: {e}' not in tried:
                tried.append(f'overlay: {e}')
    if best is not None:
        plan = best[1]
        if tried:
            plan.notes.append('Tried first: ' + '; '.join(tried) + '.')
        state = plan.details.get('safety')
        if state and state != 'clean':
            plan.notes.append({
                'timing': 'A run from power-on with this edit differs from the original run, but so does a run with '
                          'an empty routine of the same cost: this game changes course when any code is added, so '
                          'the difference cannot be laid at the edit\'s door.',
                'differs': 'A run from power-on with this edit differs from the original run beyond the edit itself.',
                'disturbed': 'A run from power-on with this edit differs from the original run beyond the edit itself, '
                             'and controls show that the routine\'s use of the video chip is the cause. The edit '
                             'holds in this scene; elsewhere in the game it may disturb graphics.',
            }.get(state, 'The run from power-on could not be compared.'))
        return plan
    raise ValueError('No confirmed way to edit this tile: ' + '; '.join(tried) + '.')


# ---------------------------------------------------------------------------
# 5. Shared data: change all users, or only this one
# ---------------------------------------------------------------------------

def source_run(scene: Scene, domain: str, index: int) -> tuple[int, int, int, int] | None:
    """The plain copy that `domain[index]` belongs to.

    Returns (domain start, domain end, ROM start, ROM end) of the longest run
    around `index` whose bytes come from consecutive ROM bytes, i.e. one
    block the game copied in one go. Offsets are tag offsets (no file header).
    """
    d = scene.snapshot.domains[domain]
    if tag_kind(d.tags[index]) != pv.RT_ROM:
        return None
    base = tag_offset(d.tags[index]) - index
    a = index
    while a > 0 and tag_kind(d.tags[a - 1]) == pv.RT_ROM and tag_offset(d.tags[a - 1]) - (a - 1) == base:
        a -= 1
    b = index + 1
    while b < len(d.tags) and tag_kind(d.tags[b]) == pv.RT_ROM and tag_offset(d.tags[b]) - b == base:
        b += 1
    return a, b, base + a, base + b


def sharing(index: pv.ImpactIndex, start: int, end: int, scene: Scene | None = None) -> dict:
    """Who else uses ROM bytes [start, end) (tag offsets): the "change all N" side of the choice."""
    users = index.users(start, end)
    others = {k: sorted(v) for k, v in users.items() if scene is None or k != scene.id}
    return {'scenes': len(users), 'other_scenes': others, 'shared': bool(others)}


def plan_private_copy(item, new_stored: bytes, rom: bytes, scene: Scene, *, verify: Callable[[EditPlan], dict],
                      avoid: Iterable[tuple[int, int]] = (), codecs: Iterable[str] | None = None,
                      max_candidates: int = 24) -> EditPlan:
    """ "Change only this one": copy the data behind a Tile or MapCell and repoint this scene's use.

    The block the item was loaded from (a plain copy run, or a recognised
    packed block) is duplicated into free space with the edit applied, and
    the pointer this scene loads it through is moved to the copy. The
    original bytes are untouched, so anything that reaches them through
    another pointer keeps the old picture. The pointer is found by replay.

    `item` needs .system, .domain, .addresses, .stored and .status (a Tile, a
    MapCell, or any object shaped like them, e.g. a palette entry).

    Raises ValueError when no pointer can be confirmed. If every use goes
    through the same pointer, the copy changes them all; the replay result's
    `unplanned` and a re-check of the other scenes show that. The pointer
    search replays the scene once per candidate (`max_candidates` at most).
    """
    system = item.system
    skip = rom_skip(rom, system)
    changes = {a: new_stored[k] for k, a in enumerate(item.addresses) if new_stored[k] != item.stored[k]}
    if not changes:
        raise ValueError('The edit changes nothing.')
    expect = {item.domain: changes}
    run = source_run(scene, item.domain, item.addresses[0]) if item.status == 'rom' else None
    if run and all(run[0] <= a < run[1] for a in item.addresses) and getattr(item, 'layout', 'plain') == 'plain':
        d0, d1, r0, r1 = run
        new_block = bytearray(rom[skip + r0:skip + r1])
        for a, v in changes.items():
            new_block[a - d0] = v
        start, end, new_block = skip + r0, skip + r1, bytes(new_block)
        how = 'plain copy'
    else:
        block = find_compressed_block(scene, rom, system, item.domain, item.addresses[0],
                                      item.addresses[-1] - item.addresses[0] + 1, codecs)
        if block is None:
            raise ValueError('The data behind this item is neither a plain copy nor a recognised packed block.')
        raw = bytearray(block.decoded)
        for a, v in changes.items():
            raw[block.decoded_index(a)] = v
        start, end = block.start, block.start + block.size
        new_block = gfx_codecs.encode(block.codec, bytes(raw), like=rom[start:end])
        how = block.codec
    counts: dict = {}
    hits = locate_pointer(verify, rom, system, start, end, new_block, expect, avoid=avoid, max_candidates=max_candidates,
                          report=counts)
    if not hits:
        raise ValueError('No pointer to this data was confirmed, so a private copy cannot be made: '
                         + _no_pointer(counts) + '.')
    plan = plan_relocation(rom, system, start, end, new_block, hits[0], avoid=avoid, kind='private-copy')
    plan.expect = expect
    plan.details['source'] = how
    plan.details['pointer_search'] = counts
    plan.notes.append('The original data is unchanged; only the reference this scene loads through was moved.')
    plan.verified = verify(plan)
    return plan
