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
                                                 tile after the game's own loader has run
    plan_private_copy                         -> EditPlan: "change only this one" by copying the data
                                                 and repointing the single reference
    plan_derived_tile_edit                    -> tries the three paths above in that order

Every plan ends in verify_plan, which replays the scene with the edited ROM
(provenance.verify_edit) and reports whether the planned bytes took their
planned values, and every other byte that changed.

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


def tiles(scene: Scene, system: str, rom: bytes | None = None, fmt: str | None = None) -> list[Tile]:
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
                                ['The picture chip reads this tile straight from the ROM.']))
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
                'scroll_x': self.scroll_x, 'scroll_y': self.scroll_y, 'notes': list(self.notes),
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
                return {'system': system, 'source': 'savestate', 'bg_mode': mode, 'bg3_priority': state[r + 50],
                        'bg_tilesize': list(state[r + 46:r + 50]), 'bg_scaddr': u16(59, 4),
                        'bg_scsize': list(state[r + 67:r + 71]), 'bg_tdaddr': u16(71, 4), 'bg_hofs': u16(84, 4),
                        'bg_vofs': u16(92, 4), 'oam_tdaddr': u16(37)[0], 'oam_nameselect': state[r + 36],
                        'display_disabled': state[r + 33]}
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
    if not video:
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
    out += [(i, None, after[i]) for i in range(len(before), len(after))]
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
        if before:
            short = Scene(scene.id, scene.frame, scene.screen_sha256, before[-1:], scene.snapshot)
            shots: list = []
            for data in (edited, rom):
                pv.verify_edit(lambda d: _Tap(make_frontend(d), shots), rom, data, short, [], buttons_for)
            if len(shots) == 2 and shots[0][1] and shots[1][1]:
                result['replay_is_repeatable'] = shots[1][1] == scene.screen_sha256
                if result['replay_is_repeatable'] and shots[0][1] != scene.screen_sha256:
                    result.update(verified=True, by='screen', screen_sha256=shots[0][1], from_frame=before[-1][0])
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


def plan_relocation(rom: bytes, system: str, start: int, end: int, new_bytes: bytes, pointer: dict, *,
                    avoid: Iterable[tuple[int, int]] = (), kind: str = 'relocate') -> EditPlan:
    """Write `new_bytes` to free space and make `pointer` name it instead of [start, end).

    The original bytes stay where they are, so every other reference keeps
    the old data. Sega Genesis ROMs grow when no free space is left.
    """
    wide = pointer['size'] > 2
    span = (0x4000, len(rom)) if wide and system in ('gb', 'gbc') else None
    dest = find_free_space(rom, system, len(new_bytes), near=start, same_bank=not wide, avoid=avoid, span=span)
    edited = bytearray(rom)
    notes = []
    if dest is None and system == 'genesis' and len(rom) + len(new_bytes) + 2 <= 0x400000:
        dest = len(rom) + (len(rom) & 1)
        grow = dest + len(new_bytes)
        grow += grow & 1
        edited += b'\xFF' * (grow - len(rom))
        notes.append(f'The ROM grows by {grow - len(rom)} bytes to hold the new copy.')
    if dest is None:
        raise ValueError('No free ROM space within reach of the pointer for the new copy.')
    edited[dest:dest + len(new_bytes)] = new_bytes
    for o, _, n in _repoint(rom, system, pointer, start, dest):
        edited[o] = n
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan(kind, _diff_writes(rom, final), len(final), notes=notes,
                    details={'old_range': [start, end], 'new_offset': dest, 'new_size': len(new_bytes),
                             'pointer': dict(pointer)})


def locate_pointer(verify: Callable[[EditPlan], dict], rom: bytes, system: str, start: int, end: int, probe: bytes,
                   expect: dict, *, avoid: Iterable[tuple[int, int]] = (), max_candidates: int = 24) -> list[dict]:
    """Pointers to [start, end) that the scene really loads through.

    `probe` is a replacement block with a visible change and `expect` the
    scene bytes that change if a pointer is the one in use. Each candidate is
    repointed at a relocated probe and replayed with `verify(plan)` (a
    verify_plan closure). The search stops at the first candidate whose
    replay comes out as planned; it is returned in a one-element list with
    the replay result under 'check' (an empty list when none is confirmed).
    """
    hits = []
    for cand in pointer_candidates(rom, system, start)[:max_candidates]:
        try:
            plan = plan_relocation(rom, system, start, end, probe, cand, avoid=avoid)
        except ValueError:
            continue
        plan.expect = expect
        result = verify(plan)
        if result.get('as_planned'):
            hits.append({**cand, 'check': {'from_frame': result.get('from_frame'), 'unplanned': result.get('unplanned', {})}})
            break
    return hits


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
    return best[1] if best else None


def plan_block_edit(block: CompressedBlock, changes: dict, rom: bytes, system: str, *,
                    verify: Callable[[EditPlan], dict] | None = None, avoid: Iterable[tuple[int, int]] = (),
                    force_relocate: bool = False, max_candidates: int = 24) -> EditPlan:
    """Re-encode a recognised block with `changes` ({domain index: new value}) applied.

    The new stream is written over the old one when it is no longer. When it
    is longer it goes to free space and the pointer to the block is moved;
    the pointer is found by replay, so `verify` (a closure over verify_plan
    taking an EditPlan) is required for that case.
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
    hits = locate_pointer(verify, rom, system, block.start, block.start + block.size, stream, expect, avoid=avoid,
                          max_candidates=max_candidates)
    if not hits:
        raise ValueError('The re-encoded data does not fit in place and no pointer to the block was confirmed.')
    plan = plan_relocation(rom, system, block.start, block.start + block.size, stream, hits[0], avoid=avoid)
    plan.expect = expect
    plan.details.update(details)
    plan.notes.append('The data no longer fits where it was; it was written to free space and its pointer moved.')
    plan.notes.append('Only the reference this scene loads through was moved. If the game reaches the old data '
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
    '6502': 'not implemented: only applies to CHR-RAM games; NMI vector in the fixed bank, $2006/$2007 writes',
    'z80': 'not implemented: hook at $0038 must not disturb the VDP control-port latch of the interrupted code',
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


def _sm83_overlay_routine(origin: int, tail: bytes, records: bytes) -> bytes:
    """The overlay routine at `origin`; `tail` runs after every register is restored."""
    items = [
        b'\xF5\xC5\xD5\xE5',            # push af / bc / de / hl
        b'\xF0\x4F\xF5',                # ldh a,[$4F] ; push af        (current VRAM bank)
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
        tail,
        ('label', 'table'), records, b'\xFF',
    ]
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


def plan_overlay_patch(edits: list, rom: bytes, system: str, *, avoid: Iterable[tuple[int, int]] = (),
                       max_tiles: int = 24, scene: Scene | None = None, after_handler: bool = False,
                       guard: bool = True) -> EditPlan:
    """Fallback for tiles no codec explains: rewrite them after the game has loaded them.

    `edits` is [(Tile, new pixels)]. A routine is added on the vertical-blank
    interrupt. Each frame, for each edited tile, it checks whether video
    memory holds exactly the original tile and, if so, writes the edited one.
    It does not depend on how the game stores or unpacks the tile, and it
    leaves the slot alone when the game has loaded something else there.

    Game Boy, Game Boy Color, Super NES and Mega Drive / Genesis
    (OVERLAY_STATUS lists the other processors). The game must take the
    vertical-blank interrupt.

    Mega Drive / Genesis: the level-6 (vertical blank) vector at $78 is
    pointed at the routine, which goes into free ROM or onto the end of the
    ROM and ends by jumping to the game's own handler. Each frame it sends
    one read command per edited tile, which would redirect data a game is
    streaming into video memory from its main loop. With `guard` (the
    default) it therefore skips any frame in which the interrupted program
    holds a VDP port address in an address register, the usual sign of such
    a stream; a game that keeps the port in a register all the time then
    never gets the edit, and `guard=False` is the alternative to try.

    Super NES: the native-mode NMI vector is pointed at a JML placed in the
    four unused vector bytes at $00:FFE0 (or any four free bytes of bank 0);
    the routine itself goes into free ROM anywhere and ends by jumping to the
    game's own handler. It rewrites VMAIN and VMADD, which are write-only, so
    a game that fills video memory from its main loop while NMI is enabled
    could be disturbed; the replay shows that as unplanned changes. With
    `after_handler` the work runs when the game's handler returns instead of
    before it starts (see _snes_overlay_routine).

    Game Boy: the routine (about 80 bytes plus 38 per tile) goes, in order of
    preference:

    * 'bank0': into free space in ROM bank 0, always mapped;
    * 'fixed': anywhere in a 32 KB cartridge that has no bank switching;
    * 'banked': into free space in another bank, behind a 25-byte stub in
      bank 0 that maps that bank, calls the routine and restores the game's
      bank from the game's own current-bank variable (gb_bank_shadow). Used
      only when that variable is found and, given `scene`, holds a valid bank
      number at that moment.

    verify_plan then shows whether the tile really changes in the scene and
    whether anything else did.
    """
    cpu = CPU[system]
    if cpu not in ('sm83', '65816', '68000'):
        raise ValueError(f'The overlay fallback for this processor is {OVERLAY_STATUS[cpu]}.')
    if not edits or len(edits) > max_tiles:
        raise ValueError(f'The overlay handles 1 to {max_tiles} tiles at a time.')
    if cpu == '65816':
        return _snes_overlay_patch(edits, rom, system, avoid, after_handler)
    if cpu == '68000':
        return _genesis_overlay_patch(edits, rom, system, avoid, guard)
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
        records += bytes((bank, (addr + key) & 0xFF, (addr + key) >> 8, tile.stored[key], addr & 0xFF, addr >> 8))
        records += tile.stored + new
        expect.update({tile.addresses[k]: new[k] for k in diff})
    if not records:
        raise ValueError('The edit changes nothing.')
    # Instructions at the interrupt vector that the jump will replace.
    vec = 0x40
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
    tail = bytes(displaced) + (b'' if ended else b'\xC3' + (vec + covered).to_bytes(2, 'little'))
    records = bytes(records)
    size = len(_sm83_overlay_routine(0, tail, records))
    edited = bytearray(rom)
    notes = ['The game unpacks this tile in a way ROMancer does not decode, so the edit is applied '
             'by a small added routine each frame instead of changing the stored data.',
             'It applies wherever the game shows this exact tile in this tile slot.']
    details = {'routine_size': size, 'hook_offset': vec, 'tiles': len(records) // 38, 'cpu': cpu}
    where = find_free_space(rom, system, size, span=(0x68, 0x4000), avoid=avoid)
    if where is not None:
        details.update(placement='bank0', routine_offset=where)
    elif rom[0x147] == 0x00 and len(rom) == 0x8000:
        where = find_free_space(rom, system, size, span=(0x4000, 0x8000), avoid=avoid)
        if where is None:
            raise ValueError(f'The ROM has no {size} free bytes for the overlay routine.')
        details.update(placement='fixed', routine_offset=where)
    if where is not None:
        code = _sm83_overlay_routine(where, tail, records)
        edited[where:where + len(code)] = code
        edited[vec:vec + 3] = b'\xC3' + where.to_bytes(2, 'little')
    else:
        shadow = gb_bank_shadow(rom)
        banks = len(rom) // 0x4000
        if shadow is None:
            raise ValueError(f'ROM bank 0 has no {size} free bytes for the overlay routine, and the game keeps no '
                             'current-bank variable that would let the routine live in another bank.')
        if rom[0x147] in (0x01, 0x02, 0x03) and banks > 32:
            raise ValueError(f'ROM bank 0 has no {size} free bytes for the overlay routine, and this cartridge type '
                             'splits its bank number over two registers.')
        if scene is not None:
            a = shadow['address']
            d = scene.snapshot.domains.get('hram' if a >= 0xFF80 else 'wram')
            value = None
            if d is not None and d.data is not None:
                value = d.data[a - 0xFF80] if a >= 0xFF80 else d.data[a - 0xC000] if a < 0xD000 else None
            if value is not None and not 0 < value < banks:
                raise ValueError('The variable that looked like the current bank number does not hold one.')
        body_size = len(_sm83_overlay_routine(0, b'\xC9', records))
        body = find_free_space(rom, system, body_size, span=(0x4000, min(len(rom), 0x400000)), avoid=avoid)
        a = shadow['address']
        load = bytes((0xF0, a & 0xFF)) if a >= 0xFF00 else bytes((0xFA, a & 0xFF, a >> 8))
        stub_size = 13 + len(load) + len(tail)
        stub = find_free_space(rom, system, stub_size, span=(0x68, 0x4000), avoid=avoid)
        if body is None or stub is None:
            raise ValueError(f'ROM bank 0 has no {size} free bytes for the overlay routine, and there is no room for '
                             + ('the routine in another bank.' if body is None else f'a {stub_size}-byte stub either.'))
        entry = 0x4000 + (body & 0x3FFF)
        code = _sm83_overlay_routine(entry, b'\xC9', records)
        edited[body:body + len(code)] = code
        edited[stub:stub + stub_size] = (b'\xF5\x3E' + bytes([body >> 14]) + b'\xEA\x00\x21'      # push af ; map the routine
                                         + b'\xCD' + entry.to_bytes(2, 'little')                      # call it
                                         + load + b'\xEA\x00\x21\xF1' + tail)                        # map the game's bank ; pop af
        edited[vec:vec + 3] = b'\xC3' + stub.to_bytes(2, 'little')
        details.update(placement='banked', routine_offset=body, stub_offset=stub, stub_size=stub_size,
                       bank_variable=a, bank_variable_uses=shadow['uses'])
        notes.append(f'The routine sits in ROM bank {body >> 14}; after it runs, the game\'s bank is restored from '
                     f'the game\'s own bank variable at ${a:04X}.')
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan('overlay', _diff_writes(rom, final), len(final), {'vram': expect}, notes=notes, details=details)


def _snes_overlay_routine(origin: int, records: bytes, resume: int, after: bool = False) -> bytes:
    """65816 overlay routine at bank-local address `origin`.

    Normally the work is done first and the routine ends with JML to the
    game's handler at `resume` (24-bit). With `after`, the routine first
    pushes a second interrupt frame and jumps to the game's handler; the
    handler's RTI then lands in the overlay work, whose own RTI returns to
    the interrupted program. The work then runs after the game's own
    video-memory transfers of that frame instead of before them.
    """
    items = []
    if after:
        items += [b'\x4B\xF4', ('abs', 'work'), b'\x08',        # phk ; pea work ; php
                  b'\x5C' + resume.to_bytes(3, 'little'),      # jml handler
                  ('label', 'work')]
    items += [
        b'\x08\xC2\x30',                      # php ; rep #$30          (16-bit A, X, Y)
        b'\x48\xDA\x5A\x8B\x4B\xAB',          # pha ; phx ; phy ; phb ; phk ; plb
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


def _genesis_overlay_routine(records: bytes, resume: int, guard: bool = True) -> bytes:
    """Position-independent 68000 overlay routine; ends with JMP to `resume`.

    With `guard`, the routine does nothing in a frame in which any address
    register of the interrupted program holds a VDP port address
    ($C00000-$C00007). Games keep the port in a register while they stream
    data into video memory from their main loop; sending a command of our
    own in the middle of that would redirect the rest of their data.
    """
    code = bytearray()
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
        code += bytes.fromhex('4CDF0707') + b'\x4E\xF9' + resume.to_bytes(4, 'big')   # bail: restore ; jmp handler
        code += bytes.fromhex('028000FFFFF8' '0C8000C00000' '4E75')      # chk: andi.l #$FFFFF8,d0 ; cmpi.l #$C00000,d0 ; rts
    lea_at = len(code)
    code += bytes.fromhex('41FA0000')            # lea table(pc),a0
    code += bytes.fromhex('43F900C00000')        # lea $C00000,a1          (data port; control port at 4(a1))
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
    code += b'\x4E\xF9' + resume.to_bytes(4, 'big')            # jmp handler
    table = len(code)
    code[bmi_at + 1] = done - (bmi_at + 2)
    code[bne1_at + 1] = skip - (bne1_at + 2)
    code[bne2_at + 1] = skip - (bne2_at + 2)
    code[lea_at + 2:lea_at + 4] = (table - (lea_at + 2)).to_bytes(2, 'big')
    return bytes(code) + records + b'\xFF\xFF\xFF\xFF'


def _genesis_overlay_patch(edits, rom, system, avoid, guard=True) -> EditPlan:
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
    code = _genesis_overlay_routine(bytes(records), handler, guard)
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
    edited[where:where + len(code)] = code
    edited[vector:vector + 4] = where.to_bytes(4, 'big')
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan('overlay', _diff_writes(rom, final), len(final), {'vram': expect}, notes=notes,
                    details={'routine_size': len(code), 'routine_offset': where, 'hook_offset': vector, 'placement': placement,
                             'tiles': len(records) // 78, 'cpu': '68000', 'handler': handler,
                             'guard': 'skips frames in which the interrupted program holds a VDP port in an '
                                      'address register' if guard else 'none'})


def _snes_address(rom: bytes, file_offset: int) -> int:
    """24-bit CPU address of a ROM file offset (LoROM or HiROM, fast mirror)."""
    o = file_offset - rom_skip(rom, 'snes')
    if _snes_hirom(rom):
        return (0xC0 | o >> 16) << 16 | (o & 0xFFFF)
    return (0x80 | o >> 15) << 16 | 0x8000 | (o & 0x7FFF)


def _snes_overlay_patch(edits, rom, system, avoid, after=False) -> EditPlan:
    skip = rom_skip(rom, system)
    bank0 = skip + (0x8000 if _snes_hirom(rom) else 0)     # file offset of $00:8000
    vector = bank0 + 0x7FEA
    if len(rom) < bank0 + 0x8000:
        raise ValueError('Not a Super NES ROM image.')
    handler = rom[vector] | rom[vector + 1] << 8
    if handler in (0x0000, 0xFFFF):
        raise ValueError('This game has no vertical-blank interrupt handler to hook.')
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
    records = bytes(records)
    size = len(_snes_overlay_routine(0, records, handler, after))
    # Four bytes for a JML in bank 0: the unused slots of the native ($FFE0) or emulation ($FFF0) vector table.
    stub = next((bank0 + o for o in (0x7FE0, 0x7FF0) if rom[bank0 + o:bank0 + o + 4] in (bytes(4), b'\xFF' * 4)), None)
    if stub is None:
        stub = find_free_space(rom, system, 4, span=(bank0, bank0 + 0x7FB0), avoid=avoid)
        if stub is None:
            raise ValueError('ROM bank 0 has no four free bytes for the jump to the overlay routine.')
    body = find_free_space(rom, system, size, near=bank0, same_bank=False, avoid=list(avoid) + [(stub, stub + 4)],
                           span=(skip, min(len(rom), skip + 0x400000)))
    if body is None:
        raise ValueError(f'The ROM has no {size} free bytes for the overlay routine.')
    address = _snes_address(rom, body)
    code = _snes_overlay_routine(address & 0xFFFF, records, handler, after)
    if (body - skip) // 0x8000 != (body + len(code) - 1 - skip) // 0x8000:
        raise ValueError('The free space found for the overlay routine crosses a bank boundary.')
    edited = bytearray(rom)
    edited[body:body + len(code)] = code
    edited[stub:stub + 4] = b'\x5C' + address.to_bytes(3, 'little')
    stub_address = 0x8000 + (stub - bank0)
    edited[vector:vector + 2] = stub_address.to_bytes(2, 'little')
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan('overlay', _diff_writes(rom, final), len(final), {'vram': expect},
                    notes=['The game unpacks this tile in a way ROMancer does not decode, so the edit is applied '
                           'by a small added routine each frame instead of changing the stored data.',
                           'It applies wherever the game shows this exact tile in this tile slot.',
                           'The routine sets the video-memory address and increment registers each frame.'],
                    details={'routine_size': len(code), 'routine_offset': body, 'stub_offset': stub, 'hook_offset': vector,
                             'placement': 'free-rom', 'tiles': len(edits), 'cpu': '65816', 'handler': handler,
                             'timing': 'after the game\'s handler' if after else 'before the game\'s handler'})


# ---------------------------------------------------------------------------
# One entry point for tiles that cannot be written in place
# ---------------------------------------------------------------------------

def plan_derived_tile_edit(tile: Tile, pixels, rom: bytes, scene: Scene, *, verify: Callable[[EditPlan], dict],
                           avoid: Iterable[tuple[int, int]] = (), codecs: Iterable[str] | None = None,
                           max_candidates: int = 24) -> EditPlan:
    """Plan and confirm an edit to a computed, unpacked or packed tile.

    Tries, in order: (1) a recognised codec, re-encoded in place or relocated
    and repointed; (2) the overlay fallback (on Super NES at both timings,
    on Mega Drive with and without its guard). `verify(plan)` must run
    verify_plan; the first plan whose replay comes out as planned is
    returned with `.verified` set. Raises ValueError, listing what was tried,
    when nothing is confirmed.
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
    variants = [{}]
    if cpu == '65816':
        variants = [{'after_handler': False}, {'after_handler': True}]
    elif cpu == '68000':
        variants = [{'guard': True}, {'guard': False}]
    for options in variants:
        try:
            plan = plan_overlay_patch([(tile, list(pixels))], rom, tile.system, avoid=avoid, scene=scene, **options)
            result = verify(plan)
            plan.verified = result
            if result.get('as_planned'):
                if tried:
                    plan.notes.append('Tried first: ' + '; '.join(tried) + '.')
                return plan
            tried.append('overlay did not replay as planned' + (f' ({options})' if options else ''))
        except ValueError as e:
            tried.append(f'overlay: {e}')
            break
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
    hits = locate_pointer(verify, rom, system, start, end, new_block, expect, avoid=avoid, max_candidates=max_candidates)
    if not hits:
        raise ValueError('No pointer to this data was confirmed, so a private copy cannot be made.')
    plan = plan_relocation(rom, system, start, end, new_block, hits[0], avoid=avoid, kind='private-copy')
    plan.expect = expect
    plan.details['source'] = how
    plan.notes.append('The original data is unchanged; only the reference this scene loads through was moved.')
    plan.verified = verify(plan)
    return plan
