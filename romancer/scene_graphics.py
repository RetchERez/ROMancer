"""Pictures and backgrounds of a recorded scene, for the Scenes editor.

romancer.graphics_trace knows what video memory holds (tiles, background
cells) and how to plan a ROM edit. This module answers the questions the
editor screen asks on top of that:

* which 8x8 picture is under a clicked pixel, and which background cell;
* where each background layer sits on the recorded screen, so a grid can be
  drawn over it;
* the scene's tile set and background cells, each with a plain reason when
  it cannot be changed, or how it will be changed;
* in a worker process, the plan for a tile edit, a background edit or the
  search for where a computed color comes from, each confirmed by a replay
  in the real engine before it is offered.

Placement is measured, not assumed. Scroll registers are not available on
every engine, and a game may scroll each screen line differently, so each
layer is drawn from video memory and found in the recorded screen line by
line. Where a layer cannot be found in the picture, the registers are used
when the engine gave them, and the layer says which of the two it was.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from . import cell_trace as ct
from . import graphics_trace as gt
from . import palette_trace as pt
from . import provenance as pv

SEGMENT = 16            # pixels of a screen line looked for in a layer line
MAX_TILES = 2600
TILE_DOMAINS = ('vram', 'chr', 'vram4')      # palette memory is left out of tile checks (see verify_plan's callers)
SYSTEM_NAMES = {'nes': 'NES', 'snes': 'Super NES', 'genesis': 'Mega Drive', 'sms': 'Master System', 'gb': 'Game Boy',
                'gbc': 'Game Boy Color'}

DEBUG_LAYOUT = bool(__import__('os').environ.get('ROMANCER_DEBUG_LAYOUT'))
MAX_LAYOUT_TRIES = 20       # replays spent on one block before giving up on the level's own list

METHODS = {
    'layout': "Changed in the level's own list of blocks, so only this spot in the level changes.",
    'direct': 'Written straight over the picture in the ROM.',
    'direct-packed': 'This picture sits inside packed data, but your version could be written straight over it without '
                     'repacking. Bytes the packed data reuses change everywhere they are used, and the check counts them.',
    'reencode': 'This picture is packed in the ROM, so its set was unpacked, changed and packed again in the same place.',
    'relocate': "This picture is packed in the ROM and the changed set no longer fit, so it was written to unused space and "
                'the game now reads the new copy.',
    'overlay': "The game unpacks this picture in a way that can't be packed again, so a small patch swaps your picture in "
               'after the game loads it.',
    'private-copy': 'This scene gets its own copy of the data, and the game reads the copy here only. The original stays as it is.',
    'import': 'These pictures came from your PNG. Each one was changed the way the ROM stores it, and the game was replayed '
              'for each group and again with all of them together.',
    'cells': 'Written straight over these background tiles in the ROM.',
    'cells-reencode': 'This part of the background is packed in the ROM, so it was unpacked, changed and packed again.',
    'cells-built': 'The game builds this part of the background from a piece it reuses, such as a block of tiles. That piece '
                   'was changed, so everywhere the game draws it changes too.',
}
MAX_BUILT_CELLS = 6      # each cell built from a stored piece costs several replays to find that piece
CELL_REASONS = {
    'derived': 'The game builds this part of the background while it runs. ROMancer will try to find it packed in the '
               'ROM, or the stored piece the game builds it from; if it cannot, this cell cannot be changed here.',
    'unknown': 'ROMancer has not seen where this part of the background comes from. It was drawn before recording '
               'started, or it is unused.',
}


def overlay_available(system: str) -> bool:
    """Whether graphics_trace can add the swap-in patch on this system (it says so itself)."""
    status = gt.OVERLAY_STATUS.get(gt.CPU.get(system, ''), 'not implemented')
    return not status.startswith('not implemented')


def tile_id(domain: str, address: int, fmt: str) -> str:
    return f'{domain}:{address}:{fmt}'


def parse_tile_id(value: str) -> tuple[str, int, str]:
    domain, address, fmt = str(value).split(':')
    if domain not in ('vram', 'chr', 'chr_rom', 'vram4') or fmt not in gt.TILE_FORMATS:
        raise ValueError('That picture is not part of this scene.')
    return domain, int(address), fmt


def pixel_text(pixels, fmt: str) -> str:
    wide = gt.TILE_FORMATS[fmt][0] > 4
    return ''.join(f'{p:02x}' if wide else f'{p:x}' for p in pixels)


def parse_pixels(text, fmt: str) -> list[int]:
    if isinstance(text, (list, tuple)):
        pixels = [int(p) for p in text]
    else:
        text = str(text)
        step = 2 if gt.TILE_FORMATS[fmt][0] > 4 else 1
        pixels = [int(text[i:i + step], 16) for i in range(0, len(text), step)]
    top = 1 << gt.TILE_FORMATS[fmt][0]
    if len(pixels) != 64 or any(not 0 <= p < top for p in pixels):
        raise ValueError('A picture is 8 by 8 pixels, each one of the colors its palette holds.')
    return pixels


def tile_reason(tile, system: str) -> tuple[str, bool, str]:
    """(how it will be changed, whether it can be tried, the plain reason)."""
    patch = overlay_available(system)
    name = SYSTEM_NAMES.get(system, system)
    if tile.domain == 'chr_rom':
        return 'direct', True, "The game's picture chip reads this picture straight from the ROM, so it can be changed in place."
    if tile.status in ('rom', 'code') and tile.layout == 'plain':
        return 'direct', True, 'This picture is stored as plain picture data in the ROM, so it can be changed in place.'
    if tile.status in ('rom', 'code', 'derived'):
        return 'packed', True, ('This picture is unpacked by the game while it runs. ROMancer will try to pack your version '
                                'back into the ROM; ' + ('if it cannot, it will add a small patch that swaps your picture in.'
                                                         if patch else f'if it cannot, this picture cannot be changed yet on {name}.'))
    if patch:
        return 'patch', True, ('ROMancer has not seen where this picture comes from, so it cannot change the stored data. '
                               'It will add a small patch that swaps your picture in.')
    return 'locked', False, ('ROMancer has not seen where this picture comes from. It was loaded before recording started, '
                             'or this slot is unused.')


class SceneGraphics:
    """One scene's tiles, layers and sprites, placed on its recorded screen."""

    def __init__(self, scene, system: str, rom: bytes, rgb: bytes, width: int, height: int):
        self.scene, self.system, self.rom = scene, system, rom
        self.width, self.height = width, height
        self.video = getattr(scene, 'video', None)
        self.domains = scene.snapshot.domains
        every = pt.swatches(scene, system)
        colored = [s for s in every if s.domain == 'palette']
        self.dmg = system in ('gb', 'gbc') and not any(s.status != 'unknown' for s in colored)
        if self.dmg or not colored:
            shades = sorted((s for s in every if s.format == 'dmg-shades'), key=lambda s: s.entry)
            self.colors = [list(c) for s in shades for c in s.rgb] or [[v, v, v] for v in (255, 170, 85, 0)]
        else:
            self.colors = [list(s.rgb[0]) for s in sorted(colored, key=lambda s: s.entry)]
        self._canon()
        self._screen(rgb)
        self._pixels: dict = {}
        self._tiles: dict = {}
        self._lists: dict = {}
        self._layers = None
        self._sprites = None
        self.chr_bases = None           # NES: {pattern slot: ROM offset of the bank the screen was drawn from}, once settled
        self._chr_settled = False
        self._placing = False

    # ---- colors

    def _canon(self) -> None:
        """One id per distinct color, so two palette slots holding the same color compare equal."""
        self.reps, index, self.ids = [], {}, []
        for color in self.colors:
            key = tuple(color)
            if key not in index:
                if len(self.reps) < 250:
                    index[key] = len(self.reps)
                    self.reps.append(key)
                else:
                    index[key] = min(range(len(self.reps)), key=lambda i: sum((a - b) ** 2 for a, b in zip(self.reps[i], key)))
            self.ids.append(index[key])

    def _screen(self, rgb: bytes) -> None:
        cache, out = {}, bytearray(self.width * self.height)
        reps = self.reps
        for i in range(self.width * self.height):
            key = rgb[3 * i:3 * i + 3]
            value = cache.get(key)
            if value is None:
                best, distance = 254, 1500          # engines round colors a little on the way to the screen
                for k, rep in enumerate(reps):
                    d = (rep[0] - key[0]) ** 2 + (rep[1] - key[1]) ** 2 + (rep[2] - key[2]) ** 2
                    if d < distance:
                        best, distance = k, d
                value = cache[key] = best
            out[i] = value
        self.screen = [bytes(out[y * self.width:(y + 1) * self.width]) for y in range(self.height)]

    def rule(self, kind: str, fmt: str = '', index: int = 0) -> tuple[int, int, int]:
        """(first color, colors between palette lines, colors per line) for a layer or for sprites."""
        s, bg = self.system, kind == 'bg'
        if self.dmg:
            return (0, 0, 4) if bg else (4, 4, 4)
        if s in ('gb', 'gbc'):
            return (0, 4, 4) if bg else (32, 4, 4)
        if s == 'nes':
            return (0, 4, 4) if bg else (16, 4, 4)
        if s == 'snes':
            if not bg:
                return 128, 16, 16
            bpp = gt.TILE_FORMATS.get(fmt, (4, 32))[0]
            if bpp == 2:
                return (index * 32 if self.video and self.video.get('bg_mode', 1) & 7 == 0 else 0), 4, 4
            return (0, 16, 16) if bpp == 4 else (0, 0, 256)
        if s == 'genesis':
            return 0, 16, 16
        return (0, 16, 16) if bg else (16, 0, 16)

    def line_count(self, kind: str, fmt: str) -> int:
        """How many palette lines a picture of this kind can be shown with."""
        if self.dmg:
            return 1 if kind == 'bg' else 2
        if self.system == 'sms':
            return 2 if kind == 'bg' else 1
        if gt.TILE_FORMATS.get(fmt, (4,))[0] == 8:
            return 1
        return {'gb': 8, 'gbc': 8, 'nes': 4, 'snes': 8, 'genesis': 4}.get(self.system, 1)

    def zero(self, kind: str) -> str:
        """What color 0 of a picture shows: its own color, the shared backdrop, or whatever is behind it."""
        if kind != 'bg':
            return 'clear'
        return {'gb': 'color', 'gbc': 'color', 'sms': 'color', 'nes': 'backdrop'}.get(self.system, 'clear')

    def _table(self, kind: str, rule, line: int) -> bytes:
        base, step, size = rule
        table = bytearray([254]) * 256
        for p in range(min(size, 256)):
            i = base + line * step + p
            if i < len(self.ids):
                table[p] = self.ids[i]
        zero = self.zero(kind)
        if zero == 'clear':
            table[0] = 255
        elif zero == 'backdrop' and self.ids:
            table[0] = self.ids[0]
        return bytes(table)

    # ---- tiles

    def tile_list(self, fmt: str | None = None) -> dict:
        fmt = fmt or gt.SYSTEM_TILE_FORMAT[self.system]
        if self.system == 'nes' and not self._chr_settled and not self._placing:
            self.layers()                   # which bank the screen shows is settled there; every reader must agree on it
        found = self._lists.get(fmt)
        if found is None:
            found = self._lists[fmt] = {(t.domain, t.addresses[0]): t
                                        for t in gt.tiles(self.scene, self.system, self.rom, fmt, self.chr_bases)}
        return found

    def tile(self, domain: str, address: int, fmt: str):
        key = (domain, address, fmt)
        tile = self._tiles.get(key)
        if tile is None:
            if domain == 'chr_rom' or fmt == 'snes-mode7' or fmt == gt.SYSTEM_TILE_FORMAT[self.system]:
                tile = self.tile_list(fmt).get((domain, address))
            if tile is None and domain in self.domains and self.domains[domain].data is not None:
                size = gt.TILE_FORMATS[fmt][1]
                if fmt != 'snes-mode7' and 0 <= address and address + size <= len(self.domains[domain].data):
                    tile = gt.tile_at(self.scene, self.system, address, fmt, domain)
            if tile is None:
                raise ValueError('That picture is not part of this scene.')
            self._tiles[key] = tile
        return tile

    def tile_pixels(self, domain: str, address: int, fmt: str):
        key = (domain, address, fmt)
        if key not in self._pixels:
            try:
                self._pixels[key] = bytes(self.tile(domain, address, fmt).pixels)
            except ValueError:
                self._pixels[key] = None
        return self._pixels[key]

    # ---- layers

    def layers(self) -> list:
        if self._layers is None:
            self._layers = []
            self._placing = True
            try:
                found = gt.layers(self.scene, self.system)
            except Exception:
                found = []
            for index, layer in enumerate(found):
                px = 8
                if self.system == 'snes' and self.video and layer.name.startswith('BG'):
                    k = int(layer.name[2:]) - 1
                    index = k
                    if self.video['bg_tilesize'][k]:
                        px = 16
                view = SimpleNamespace(layer=layer, index=index, px=px, rule=self.rule('bg', layer.tile_format, index),
                                       rows=None, lines=None, source='none', match=0.0)
                self._layers.append(view)
            for view in self._layers:
                self._place(view)
            self._placing = False
            if not self._chr_settled:
                self._chr_settled = True
                if self._settle_chr():          # the pictures came from other banks: read them again and place again
                    self._lists, self._tiles, self._pixels, self._layers = {}, {}, {}, None
                    return self.layers()
        return self._layers

    def _settle_chr(self) -> bool:
        """NES with picture data in ROM: find the bank the recorded screen was really drawn from.

        The picture chip reads tiles straight from the cartridge, and the
        cartridge can switch banks while the screen is drawn (one bank for
        the status bar, another for the level). The scene knows the banks
        mapped when the frame ended, which may not be the ones most of the
        screen shows. For each of the eight pattern slots, the background
        cells that disagree with the recorded screen are compared with the
        same tile numbers in every bank of the ROM; a bank that explains
        most of them, where the recorded bank explains few, is taken.
        Returns True when a slot changed.
        """
        chart = self.domains.get('chr_map')
        if self.system != 'nes' or chart is None or self.rom[:4] != b'NES\x1a':
            return False
        skip = gt.rom_skip(self.rom, self.system)
        first = self.rom[4] * 16384
        size = self.rom[5] * 8192
        if size < 0x800:
            return False
        fmt = gt.SYSTEM_TILE_FORMAT[self.system]
        samples: dict = {}          # slot -> [(offset within the bank, palette table, the 8 lines of the screen)]
        for view in self._layers:
            if view.rows is None or not view.lines or view.layer.tile_domain != 'chr_rom':
                continue
            for sy in range(0, self.height - 7, 8):
                if view.lines[sy] is None:
                    continue
                for sx in range(0, self.width - 7, 8):
                    at = self.locate(view, sx + 4, sy + 4)
                    if at is None:
                        continue
                    mx, my, cell = at
                    x0, y0 = sx + 4 - mx % 8, sy + 4 - my % 8
                    if x0 < 0 or y0 < 0 or x0 + 8 > self.width or y0 + 8 > self.height or view.lines[y0] != view.lines[sy]:
                        continue
                    shown = [self.screen[y0 + k][x0:x0 + 8] for k in range(8)]
                    if len(set(b''.join(shown))) < 2:
                        continue                # one flat color fits any empty tile in any bank
                    samples.setdefault(cell.tile_address // 0x400, []).append(
                        (cell.tile_address % 0x400, self._table('bg', view.rule, cell.palette), shown))
        if not samples:
            return False

        def fits(base, sample):
            within, table, shown = sample
            raw = self.rom[skip + base + within:skip + base + within + 16]
            if len(raw) < 16:
                return False
            pixels = bytes(gt.decode_tile(raw, fmt))
            same = sum(1 for k in range(8) for p, q in zip(pixels[k * 8:k * 8 + 8].translate(table), shown[k]) if p == q)
            return same >= 60

        bases = {}
        for slot, cells in samples.items():
            if slot >= len(chart.tags) or pv.tag_kind(chart.tags[slot]) != pv.RT_ROM:
                continue
            mapped = pv.tag_offset(chart.tags[slot])
            step = max(1, len(cells) // 40)
            some = cells[::step][:40]
            now = sum(1 for sample in some if fits(mapped, sample))
            if now * 10 >= len(some) * 8:
                continue                        # the recorded bank already explains the screen
            probe = some[::max(1, len(some) // 6)][:6]
            best = None
            for base in range(first, first + size, 0x400):
                if base == mapped or sum(1 for sample in probe if fits(base, sample)) * 2 < len(probe):
                    continue
                count = sum(1 for sample in some if fits(base, sample))
                if best is None or count > best[0]:
                    best = (count, base)
            if best is not None and best[0] * 10 >= len(some) * 6 and best[0] >= now + max(3, len(some) // 4):
                bases[slot] = best[1]
        if not bases:
            return False
        self.chr_bases = bases
        return True

    def _subtile(self, view, cell, qx: int, qy: int) -> int:
        """Address of the tile a cell shows in quadrant (qx, qy); only 16x16 cells have more than one."""
        if view.px == 8:
            return cell.tile_address
        if cell.hflip:
            qx = 1 - qx
        if cell.vflip:
            qy = 1 - qy
        return (cell.tile_address + (qx + 16 * qy) * gt.TILE_FORMATS[view.layer.tile_format][1]) & 0xFFFF

    def _render(self, view) -> None:
        layer = view.layer
        if layer.width * layer.height > 8192 or layer.tile_format == 'snes-mode7':
            return                                   # mode 7 is drawn in perspective; it has no flat picture to find
        tables, cache = {}, {}
        blank = [bytes([254]) * 8] * 8
        quads = view.px // 8
        rows = []
        for cy in range(layer.height):
            parts = [[] for _ in range(view.px)]
            for cx in range(layer.width):
                cell = layer.cells[cy * layer.width + cx]
                for qy in range(quads):
                    for qx in range(quads):
                        address = self._subtile(view, cell, qx, qy)
                        key = (address, cell.palette, cell.hflip)
                        lines = cache.get(key)
                        if lines is None:
                            pixels = self.tile_pixels(layer.tile_domain, address, layer.tile_format)
                            if pixels is None:
                                lines = blank
                            else:
                                table = tables.get(cell.palette)
                                if table is None:
                                    table = tables[cell.palette] = self._table('bg', view.rule, cell.palette)
                                lines = [pixels[k:k + 8].translate(table) for k in range(0, 64, 8)]
                                if cell.hflip:
                                    lines = [line[::-1] for line in lines]
                            cache[key] = lines
                        for k in range(8):
                            parts[qy * 8 + k].append(lines[7 - k if cell.vflip else k])
            rows.extend(b''.join(part) for part in parts)
        view.rows = rows

    def _place(self, view) -> None:
        """Find the layer in the recorded screen: for each screen line, how far the layer is scrolled across and down.

        A game may scroll every line differently (parallax) and may change the
        vertical scroll part-way down the screen (a status bar), so lines are
        placed one by one, in up to four passes with one vertical offset each.
        """
        self._render(view)
        layer = view.layer
        hint = (layer.scroll_x, layer.scroll_y) if layer.layout_source == 'registers' and self.system in ('gb', 'gbc', 'snes') else None
        if view.rows is None:
            return
        wide, tall = layer.width * view.px, layer.height * view.px
        doubled = [row + row[:SEGMENT + 8] for row in view.rows]
        segments = []
        for y in range(self.height):
            line, found = self.screen[y], []
            for x in range(4, self.width - SEGMENT, 20):
                segment = line[x:x + SEGMENT]
                if 254 not in segment and (len(set(segment)) >= 3 or sum(a != b for a, b in zip(segment, segment[1:])) >= 4):
                    found.append((x, segment))
            segments.append(found)

        def telling(segment):
            return 254 not in segment and 255 not in segment and (
                len(set(segment)) >= 3 or sum(a != b for a, b in zip(segment, segment[1:])) >= 4)
        # The other way round as well: solid stretches of the layer, looked for in the screen. A layer that is
        # see-through around its picture (a logo, a foreground) is only found this way.
        solid = []
        for row in view.rows:
            found = [(x, row[x:x + 12]) for x in range(0, wide - 12, 12) if telling(row[x:x + 12])]
            solid.append(found[::max(1, len(found) // 16)][:16])

        def votes(y, sy):
            out = {}
            r = (y + sy) % tall
            row, line = doubled[r], self.screen[y]
            for x, segment in segments[y]:
                at, tries = row.find(segment), 0
                while at >= 0 and tries < 24:
                    if at < wide:
                        sx = (at - x) % wide
                        out[sx] = out.get(sx, 0) + 1
                    at, tries = row.find(segment, at + 1), tries + 1
            for x, segment in solid[r]:
                at, tries = line.find(segment), 0
                while at >= 0 and tries < 8:
                    sx = (x - at) % wide
                    out[sx] = out.get(sx, 0) + 1
                    at, tries = line.find(segment, at + 1), tries + 1
            return out

        def agree(y, sx, sy):
            r = (y + sy) % tall
            row, line = doubled[r], self.screen[y]
            count = sum(row[(x + sx) % wide:(x + sx) % wide + SEGMENT] == segment for x, segment in segments[y])
            for x, segment in solid[r]:
                at = (x - sx) % wide
                count += at + 12 <= self.width and line[at:at + 12] == segment
            return count

        if layer.name == 'window' and hint and self.video:
            # The Game Boy window is not scrolled: it starts at its own corner and covers the screen from there down.
            first = max(0, self.video['wy'])
            place = ((7 - self.video['wx']) % wide, (-self.video['wy']) % tall)
            view.lines, view.source = [None] * min(first, self.height) + [place] * max(0, self.height - first), 'registers'
            self._seen(view)
            return
        lines = [None] * self.height
        todo = list(range(self.height))
        for attempt in range(4):
            informative = [y for y in todo if len(segments[y]) >= 2]
            if len(informative) < 2:
                break
            tally = {}
            for y in informative[::max(1, len(informative) // 10)][:12]:
                for sy in range(tall):
                    found = votes(y, sy)
                    if found:
                        best = max(found.values())
                        if best >= 2:
                            tally[sy] = tally.get(sy, 0) + best
            if hint is not None and not attempt:
                tally[hint[1] % tall] = tally.get(hint[1] % tall, 0) + 0.5
            sy = max(tally, key=tally.get) if tally else None
            if sy is None or tally[sy] < 4:
                break
            found = {y: votes(y, sy) for y in todo}
            common = {}
            for line in found.values():
                for sx, count in line.items():
                    if count >= 2:
                        common[sx] = common.get(sx, 0) + count
            usual = max(common, key=common.get) if common else (hint[0] % wide if hint else None)
            previous, placed = usual, False
            for y in todo:
                pick, top = None, max(found[y].values()) if found[y] else 0
                for candidate in (previous, usual):
                    if candidate is not None and agree(y, candidate, sy) >= max(1, top / 2):
                        pick = candidate
                        break
                if pick is None and top >= 2:
                    pick = min(sx for sx, count in found[y].items() if count == top)
                if pick is not None:
                    lines[y], previous, placed = (pick, sy), pick, True
            todo = [y for y in todo if lines[y] is None]
            if not placed:
                break
        known = [y for y in range(self.height) if lines[y] is not None]
        if not known:
            if hint is not None:                     # not found in the picture; the engine's registers still place it
                view.lines, view.source = [(hint[0] % wide, hint[1] % tall)] * self.height, 'registers'
                self._seen(view)
            return
        # Lines with nothing to tell them apart (a flat sky) take the place of the nearest line that was found.
        filled, at = list(lines), 0
        for y in range(self.height):
            if filled[y] is None:
                while at + 1 < len(known) and abs(known[at + 1] - y) <= abs(known[at] - y):
                    at += 1
                filled[y] = lines[known[at]]
        view.lines, view.source = filled, 'picture'
        self._seen(view)

    def _seen(self, view) -> None:
        """How much of the recorded screen shows this layer, from a sample of its pixels."""
        wide, tall = view.layer.width * view.px, view.layer.height * view.px
        same = total = 0
        for y in range(2, self.height, 4):
            if view.lines[y] is None:
                continue
            sx, sy = view.lines[y]
            row, line = view.rows[(y + sy) % tall], self.screen[y]
            for x in range(2, self.width, 4):
                total += 1
                same += row[(x + sx) % wide] == line[x]
        view.match = same / max(1, (self.height // 4) * (self.width // 4))

    def bands(self, view) -> list:
        """[first line, line after the last, scrolled across, scrolled down] for each run of screen lines placed alike."""
        out = []
        for y, place in enumerate(view.lines or []):
            if place is None:
                continue
            if out and out[-1][1] == y and (out[-1][2], out[-1][3]) == place:
                out[-1][1] = y + 1
            else:
                out.append([y, y + 1, place[0], place[1]])
        return out

    # ---- sprites

    def sprites(self) -> list:
        if self._sprites is None:
            try:
                self._sprites = self._find_sprites()
            except Exception:
                self._sprites = []
        return self._sprites

    def _sprite(self, x, y, cols, rows, tiles, attrs, **more):
        hflip, vflip, line = attrs
        return SimpleNamespace(x=x, y=y, cols=cols, rows=rows, tiles=tiles, hflip=hflip, vflip=vflip, line=line,
                               domain=more.get('domain', 'vram'), fmt=more.get('fmt', gt.SYSTEM_TILE_FORMAT[self.system]),
                               guess=more.get('guess', False))

    def _find_sprites(self) -> list:
        s, video, out = self.system, self.video, []
        oam = self.domains.get('oam')
        o = oam.data if oam is not None else None
        if s in ('gb', 'gbc') and o:
            tall = bool(video and video['lcdc'] & 4)
            for i in range(0, 0xA0, 4):
                n, a = o[i + 2], o[i + 3]
                bank = (a >> 3 & 1) if not self.dmg else 0
                first = bank * 0x2000 + (n & 0xFE if tall else n) * 16
                out.append(self._sprite(o[i + 1] - 8, o[i] - 16, 1, 2 if tall else 1, [first, first + 16][:2 if tall else 1],
                                        (bool(a & 0x20), bool(a & 0x40), (a >> 4 & 1) if self.dmg else a & 7)))
        elif s == 'nes' and o:
            ctrl = video['ppuctrl'] if video else 0
            domain = 'chr' if self.domains.get('chr') is not None and self.domains['chr'].data is not None else 'chr_rom'
            top = (240 - self.height) // 2
            for i in range(0, 0x100, 4):
                if o[i] >= 0xEF:
                    continue
                n, a = o[i + 1], o[i + 2]
                if ctrl & 0x20:
                    first = ((n & 1) * 256 + (n & 0xFE)) * 16
                    tiles = [first, first + 16]
                else:
                    tiles = [((1 if ctrl & 8 else 0) * 256 + n) * 16]
                out.append(self._sprite(o[i + 3], o[i] + 1 - top, 1, len(tiles), tiles, (bool(a & 0x40), bool(a & 0x80), a & 3),
                                        domain=domain))
        elif s == 'snes' and o and video:
            base, select = video['oam_tdaddr'], video['oam_nameselect']
            for i in range(128):
                x, y, n, a = o[i * 4], o[i * 4 + 1], o[i * 4 + 2], o[i * 4 + 3]
                high = o[0x200 + i // 4] >> (i % 4 * 2) & 3
                x = x - 256 if high & 1 else x
                y = (y + 1) - 256 if y >= 224 else y + 1
                n |= (a & 1) << 8
                for size in (1, 2, 4, 8):           # the sprite size is register state the engine does not give; the picture decides
                    tiles = []
                    for row in range(size):
                        for col in range(size):
                            t = ((n & 0x1F0) + (row << 4)) & 0x1F0 | (n + col) & 0x0F
                            tiles.append((base + ((0x2000 + (select << 13)) if t & 0x100 else 0) + (t & 0xFF) * 32) & 0xFFFF)
                    out.append(self._sprite(x, y, size, size, tiles, (bool(a & 0x40), bool(a & 0x80), a >> 1 & 7), guess=True))
        elif s == 'genesis':
            out = self._best_sprites(self._genesis_sprites(base) for base in self._genesis_tables())
        elif s == 'sms':
            out = self._best_sprites(self._sms_sprites(tall, shift) for tall in (False, True) for shift in (0, 256))
        return out

    def _genesis_tables(self):
        if self.video and self.video.get('regs'):
            return [(self.video['regs'][5] & 0x7F) << 9]
        return range(0, 0x10000, 0x200)

    def _genesis_sprites(self, base: int) -> list:
        v = self.domains['vram'].data
        out, seen, i = [], set(), 0
        while i not in seen and len(seen) < 80:
            seen.add(i)
            e = v[(base + i * 8) & 0xFFFF:(base + i * 8 + 8) & 0xFFFF or None]
            if len(e) < 8:
                return []
            y, x = ((e[0] << 8 | e[1]) & 0x3FF) - 128, ((e[6] << 8 | e[7]) & 0x1FF) - 128
            cols, rows = (e[2] >> 2 & 3) + 1, (e[2] & 3) + 1
            word = e[4] << 8 | e[5]
            first = word & 0x7FF
            tiles = [((first + col * rows + row) & 0x7FF) * 32 for row in range(rows) for col in range(cols)]
            out.append(self._sprite(x, y, cols, rows, tiles, (bool(word & 0x800), bool(word & 0x1000), word >> 13 & 3)))
            i = e[3] & 0x7F
            if i == 0:
                return out
            if i >= 80:
                return []
        return []

    def _sms_sprites(self, tall: bool, shift: int) -> list:
        v = self.domains['vram'].data
        base = ((self.video['regs'][5] & 0x7E) << 7) if self.video and self.video.get('regs') else 0x3F00
        out = []
        for i in range(64):
            y = v[base + i]
            if y == 0xD0:
                break
            n = v[base + 0x81 + i * 2] + shift
            tiles = [(n & (0x1FE if tall else 0x1FF)) * 32]
            if tall:
                tiles.append(tiles[0] + 32)
            out.append(self._sprite(v[base + 0x80 + i * 2], y + 1, 1, len(tiles), tiles, (False, False, 0)))
        return out

    def _best_sprites(self, candidates) -> list:
        """Of several readings of the sprite table, the one the recorded screen agrees with (and where the screen starts)."""
        best, chosen = 0, []
        nominal = {'genesis': ((320, 224), (256, 224), (320, 240)), 'sms': ((256, 192), (256, 224))}.get(self.system, ())
        offsets = {(0, 0)} | {((self.width - w) // 2, (self.height - h) // 2) for w, h in nominal if w <= self.width and h <= self.height}
        for sprites in candidates:
            shown = [s for s in sprites if -s.cols * 8 < s.x < 320 and -s.rows * 8 < s.y < 240]
            if not shown or len(shown) > 80:
                continue
            for ox, oy in offsets:
                moved = [replace_ns(s, x=s.x + ox, y=s.y + oy) for s in shown]
                score = sum(self._sprite_score(s) for s in moved)
                if score > best:
                    best, chosen = score, moved
        return chosen

    def sprite_pixel(self, sprite, x: int, y: int):
        """(tile address, x in tile, y in tile, color number) of the sprite at a screen pixel, or None where it is clear."""
        lx, ly = x - sprite.x, y - sprite.y
        w, h = sprite.cols * 8, sprite.rows * 8
        if not (0 <= lx < w and 0 <= ly < h):
            return None
        if sprite.hflip:
            lx = w - 1 - lx
        if sprite.vflip:
            ly = h - 1 - ly
        address = sprite.tiles[(ly // 8) * sprite.cols + lx // 8]
        pixels = self.tile_pixels(sprite.domain, address, sprite.fmt)
        if pixels is None or not pixels[(ly % 8) * 8 + lx % 8]:
            return None
        return address, lx % 8, ly % 8, pixels[(ly % 8) * 8 + lx % 8]

    def _sprite_color(self, sprite, p: int) -> int:
        base, step, _ = self.rule('obj')
        i = base + sprite.line * step + p
        return self.ids[i] if i < len(self.ids) else 254

    def _sprite_score(self, sprite, around=None) -> int:
        """Pixels of the sprite that the recorded screen shows, minus those it does not (near one pixel, or all of it)."""
        if around:
            xs = range(max(sprite.x, around[0] - 4, 0), min(sprite.x + sprite.cols * 8, around[0] + 5, self.width))
            ys = range(max(sprite.y, around[1] - 4, 0), min(sprite.y + sprite.rows * 8, around[1] + 5, self.height))
        else:
            xs = range(max(sprite.x, 0), min(sprite.x + sprite.cols * 8, self.width))
            ys = range(max(sprite.y, 0), min(sprite.y + sprite.rows * 8, self.height))
        score = 0
        for y in ys:
            line = self.screen[y]
            for x in xs:
                hit = self.sprite_pixel(sprite, x, y)
                if hit:
                    score += 1 if self._sprite_color(sprite, hit[3]) == line[x] else -1
        return score

    # ---- what is under a pixel

    def lookup(self, x: int, y: int) -> list[dict]:
        """Every picture that the recorded screen shows at (x, y): sprites first, then background layers, best match first."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError('That point is outside the picture.')
        shown, hits = self.screen[y][x], []
        for sprite in self.sprites():
            hit = self.sprite_pixel(sprite, x, y)
            if not hit or self._sprite_color(sprite, hit[3]) != shown or self._sprite_score(sprite, (x, y)) < 4:
                continue
            address, tx, ty, _ = hit
            lx, ly = x - sprite.x, y - sprite.y
            hits.append({'kind': 'sprite', 'layer': None, 'cell': None, 'tile': tile_id(sprite.domain, address, sprite.fmt),
                         'pixel': [tx, ty], 'rect': [x - lx % 8, y - ly % 8, 8, 8], 'line': sprite.line,
                         'label': 'A sprite (a moving object)'})
            break
        found = []
        for number, view in enumerate(self.layers()):
            at = self.locate(view, x, y)
            if at is None:
                continue
            mx, my, cell = at
            layer = view.layer
            wide = layer.width * view.px
            score = 0
            for dy in range(-3, 4):
                if 0 <= y + dy < self.height:
                    row, line = view.rows[(my + dy) % len(view.rows)], self.screen[y + dy]
                    for dx in range(-6, 7):
                        if 0 <= x + dx < self.width and row[(mx + dx) % wide] == line[x + dx]:
                            score += 1
            exact = view.rows[my][mx] == shown
            address = self._subtile(view, cell, mx % view.px // 8, my % view.px // 8)
            tx, ty = mx % 8, my % 8
            found.append((exact, score, -number, {
                'kind': 'background', 'layer': number, 'cell': [cell.x, cell.y], 'tile': tile_id(layer.tile_domain, address, layer.tile_format),
                'pixel': [7 - tx if cell.hflip else tx, 7 - ty if cell.vflip else ty], 'rect': [x - tx, y - ty, 8, 8],
                'line': cell.palette, 'label': 'The background' + (f' ({layer.name})' if len(self.layers()) > 1 else '')}))
        found.sort(key=lambda item: item[:3], reverse=True)
        exact = [item[3] for item in found if item[0]]
        hits += exact or [item[3] for item in found if item[1] >= 45]
        return hits

    def locate(self, view, x: int, y: int):
        """(layer x, layer y, cell) under a screen pixel, or None where the layer was not found on that line."""
        if view.rows is None or not view.lines or view.lines[y] is None:
            return None
        layer = view.layer
        mx = (x + view.lines[y][0]) % (layer.width * view.px)
        my = (y + view.lines[y][1]) % (layer.height * view.px)
        return mx, my, layer.cell(mx // view.px, my // view.px)

    def _on_screen(self, view) -> list:
        """The cells of a layer that the recorded screen really shows.

        A layer holds more than the screen: the part scrolled out of view, a
        second table the game is filling ahead, cells behind a status bar.
        A cell counts when it lies on the screen where the layer was found
        and most of its pixels there are the layer's own. A layer that was
        not found on the screen keeps all its cells, so nothing is hidden
        from the list.
        """
        layer = view.layer
        if view.rows is None or not view.lines or view.source == 'none':
            return list(layer.cells)
        px = view.px
        wide = layer.width * px
        found, seen = [], set()
        for sy in range(0, self.height, px):
            for sx in range(0, self.width, px):
                y, x = min(sy + px // 2, self.height - 1), min(sx + px // 2, self.width - 1)
                at = self.locate(view, x, y)
                if at is None:
                    continue
                mx, my, cell = at
                key = (cell.x, cell.y)
                if key in seen:
                    continue
                x0, y0 = x - mx % px, y - my % px
                same = total = 0
                for dy in range(0, px, 2):
                    if not 0 <= y0 + dy < self.height or view.lines[y0 + dy] != view.lines[y]:
                        continue
                    row, line = view.rows[(my - my % px + dy) % len(view.rows)], self.screen[y0 + dy]
                    for dx in range(0, px, 2):
                        if 0 <= x0 + dx < self.width:
                            total += 1
                            same += row[(mx - mx % px + dx) % wide] == line[x0 + dx]
                if total and same * 4 >= total * 3:
                    seen.add(key)
                    found.append(cell)
        return found or list(layer.cells)

    # ---- what the screen lists

    def view(self, uses, pending_tiles: dict, pending_cells: dict) -> dict:
        """Tiles, layers and colors for the editor. `uses(tile)` counts the recorded scenes that load its bytes."""
        layers, shown = [], {}
        for number, view in enumerate(self.layers()):
            layer = view.layer
            size = gt.TILE_FORMATS[layer.tile_format][1]
            status = ''.join(c.status[:1] or 'u' for c in layer.cells)
            skip = gt.rom_skip(self.rom, self.system)
            quads = [(qx, qy) for qy in range(view.px // 8) for qx in range(view.px // 8)]
            for cell in self._on_screen(view):
                for qx, qy in quads:
                    shown.setdefault((layer.tile_domain, self._subtile(view, cell, qx, qy), layer.tile_format), ('bg', number, cell.palette))
            layers.append({
                'index': number, 'name': layer.name, 'width': layer.width, 'height': layer.height, 'cell': view.px,
                'tile_format': layer.tile_format, 'tile_domain': layer.tile_domain, 'tile_bytes': size,
                'pal': list(view.rule), 'zero': self.zero('bg'), 'placed': view.source != 'none', 'placed_by': view.source,
                'bands': self.bands(view), 'seen': round(view.match * 100), 'notes': list(layer.notes),
                'flips': self.system != 'nes' and len(layer.cells[0].addresses) > 1,
                'lines': 1 if len(layer.cells[0].addresses) < 2 else
                         {'gb': 8, 'gbc': 8, 'nes': 4, 'snes': 8, 'genesis': 4, 'sms': 2}.get(self.system, 1),
                'line_note': 'On the NES one palette choice covers a block of 2 by 2 cells.' if self.system == 'nes' else '',
                'cells': {'tile': [c.tile_address for c in layer.cells],
                          'flags': [c.hflip | c.vflip << 1 | c.priority << 2 for c in layer.cells],
                          'line': [c.palette for c in layer.cells], 'status': status,
                          'source': [c.sources[0]['offset'] + skip if c.sources and c.sources[0] else -1 for c in layer.cells]},
                'pending': pending_cells.get(number, []),
                'counts': layer.status_counts()})
        for sprite in self.sprites():
            if sprite.guess and sprite.cols > 1:
                continue
            if sprite.x + sprite.cols * 8 <= 0 or sprite.y + sprite.rows * 8 <= 0 or sprite.x >= self.width or sprite.y >= self.height:
                continue                             # parked off screen
            for address in sprite.tiles:
                shown.setdefault((sprite.domain, address, sprite.fmt), ('obj', None, sprite.line))
        keys = dict(shown)
        if self.system != 'snes':
            for (domain, address), tile in self.tile_list().items():
                if not tile.blank:
                    keys.setdefault((domain, address, tile.format), None)
        tiles = []
        for key in sorted(keys, key=lambda k: (k[0], k[2], k[1])):
            try:
                tile = self.tile(*key)
            except ValueError:
                continue
            user = keys[key]
            if tile.blank and user is None:
                continue
            kind = user[0] if user else 'bg'
            rule = self._layers[user[1]].rule if user and user[1] is not None else self.rule(kind, tile.format)
            how, can, reason = tile_reason(tile, self.system)
            ident = tile_id(*key)
            tiles.append({'id': ident, 'name': f'Picture {tile.index}' + (' (sprite)' if kind == 'obj' else ''),
                          'lines': self.line_count(kind, key[2]),
                          'domain': key[0], 'address': key[1], 'format': key[2], 'bits': gt.TILE_FORMATS[key[2]][0],
                          'pixels': pixel_text(tile.pixels, key[2]), 'status': tile.status, 'how': how, 'editable': can, 'reason': reason,
                          'on_screen': user is not None, 'kind': kind, 'pal': list(rule), 'line': user[2] if user else 0,
                          'zero': self.zero(kind), 'uses': uses(tile), 'blank': tile.blank, 'pending': pending_tiles.get(ident),
                          'notes': [note for note in tile.notes if '8 colors' in note or 'only change together' in note],
                          'details': [s['offset'] + gt.rom_skip(self.rom, self.system) for s in tile.sources[:1] if s]})
            if len(tiles) >= MAX_TILES:
                break
        return {'colors': self.colors, 'tiles': tiles, 'layers': layers, 'sprites': len({(s.x, s.y) for s in self.sprites()}),
                'patch_available': overlay_available(self.system), 'width': self.width, 'height': self.height}


SHARED_KEYS = ('how', 'editable', 'reason', 'kind', 'pal', 'zero', 'lines', 'bits', 'status')


def compact(view: dict) -> dict:
    """The same view in fewer JSON values, for the workbench's response budget (scene_graphics.js expands it again).

    A big scene has thousands of pictures and cells. What many pictures share
    goes into one table, and each layer's cells travel as four strings.
    """
    kinds, index, tiles = [], {}, []
    for tile in view['tiles']:
        shared = {key: tile[key] for key in SHARED_KEYS}
        mark = json.dumps(shared, sort_keys=True)
        if mark not in index:
            index[mark] = len(kinds)
            kinds.append(shared)
        row = {'id': tile['id'], 'name': tile['name'], 'pixels': tile['pixels'], 'k': index[mark], 'line': tile['line'], 'uses': tile['uses'],
               'on': int(tile['on_screen']), 'at': tile['details'][0] if tile['details'] else -1}
        if tile['pending']:
            row['pending'] = tile['pending']
        if tile['notes']:
            row['notes'] = tile['notes']
        tiles.append(row)
    layers = []
    for layer in view['layers']:
        cells = layer['cells']
        layers.append({**layer, 'cells': {'tile': ','.join(map(str, cells['tile'])), 'flags': ''.join(str(f) for f in cells['flags']),
                                          'line': ''.join(str(n) for n in cells['line']), 'status': cells['status'],
                                          'source': ','.join(map(str, cells['source']))}})
    return {**view, 'tiles': tiles, 'kinds': kinds, 'layers': layers}


def replace_ns(namespace, **changes):
    return SimpleNamespace(**{**vars(namespace), **changes})


def hardware_tile(view, cell, domain: str, address: int, fmt: str) -> int:
    """The number a background cell must hold to show the tile at `address`; ValueError says plainly why it cannot."""
    layer = view.layer
    if domain != layer.tile_domain or fmt != layer.tile_format:
        raise ValueError('That picture is a different kind from the ones this background layer uses.')
    system = layer.system
    if system in ('gb', 'gbc'):
        bank, t = address >> 13, (address & 0x1FFF) // 16
        if bank != cell.tile // 384:
            raise ValueError('That picture lives in the other picture bank. On Game Boy Color a cell stays in its own bank.')
        low = any(c.tile % 384 < 128 for c in layer.cells)
        high = any(c.tile % 384 >= 256 for c in layer.cells)
        if t < 128 and (low or not high):
            return t
        if 128 <= t < 256:
            return t
        if t >= 256 and (high or not low):
            return t - 256
        raise ValueError('This background reads its pictures from a different part of video memory than that picture is in.')
    if system == 'nes':
        if address // 16 // 256 != cell.tile // 256:
            raise ValueError('That picture is in the pattern table the sprites use; this background uses the other one.')
        return address // 16 % 256
    size = gt.TILE_FORMATS[fmt][1]
    if fmt == 'snes-mode7':
        return (address - 1) // 128
    if system == 'snes':
        first = (cell.tile_address - cell.tile * size) & 0xFFFF
        number, rest = divmod((address - first) & 0xFFFF, size)
        if rest or number > 0x3FF:
            raise ValueError("That picture is outside this background layer's picture set.")
        return number
    return address // size


# ----------------------------------------------------------------- planning, in a worker process

def _progress(job: dict, text: str, done: int = 0, total: int = 0) -> None:
    path = job.get('progress')
    if not path:
        return
    try:
        Path(path).write_text(json.dumps({'text': text, 'done': done, 'total': total, 'at': time.time()}))
    except OSError:
        pass


def read_progress(path) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _setup(job: dict):
    """(scene with the savestates that replay faithfully, trail, ROM bytes, make_frontend, buttons)."""
    from . import edit_session as es
    store = Path(job['store'])
    scene, header, rgb = es.read_scene(store / 'scenes' / (job['scene_id'] + '.scene'))
    trail = es._Trail(job, scene, header, rgb)
    starts = sorted(header['checkpoints'])
    quick = sorted(set(starts[:1] + starts[-2:]))        # power-on and the two latest bound the cost of a miss
    scene.checkpoints = [(f, trail.state(f)) for f in quick if trail.faithful(f)]
    if not scene.checkpoints:
        raise ValueError('This scene does not replay the same way twice in the engine, so a change to it cannot be checked.')
    rom = Path(job['base_rom']).read_bytes()

    def make(data):
        path = store / 'work' / (hashlib.sha256(data).hexdigest()[:24] + job['suffix'])
        if not path.exists():
            path.write_bytes(data)
        return es._frontend(job, path)
    return scene, trail, rom, make, trail.buttons, header, rgb


def _plan_out(plan, rom: bytes, method: str | None = None) -> dict:
    check = plan.verified or {}
    # A write past the old end of the ROM has no old value: the ROM grows (Mega Drive only), and the change says so.
    return {'writes': [[int(o), None if a is None else int(a), int(b)] for o, a, b in plan.writes if a != b],
            'rom_size': int(plan.rom_size), 'method': method or plan.kind,
            'notes': [str(n) for n in plan.notes],
            'expect': {name: {str(i): int(v) for i, v in cells.items()} for name, cells in plan.expect.items()},
            'in_scene': {'as_planned': bool(check.get('as_planned')), 'verified': bool(check.get('verified')), 'by': check.get('by', 'memory'),
                         'from_frame': check.get('from_frame'), 'unplanned': {k: int(v) for k, v in check.get('unplanned', {}).items()},
                         'missed': {k: len(v) for k, v in check.get('missed', {}).items()}},
            'block': (plan.details.get('block') or {}).get('start'), 'details': _plain(plan.details)}


def _plain(value):
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return {}


def _good(result: dict, tile=None) -> bool:
    return bool(result.get('as_planned') or (tile is not None and tile.domain == 'chr_rom' and result.get('verified')))


def _stored_tile(record: dict, system: str):
    """A graphics_trace Tile rebuilt from what a kept change remembers, for planning several tiles as one patch."""
    stored = bytes.fromhex(record['stored'])
    size = len(stored)
    return gt.Tile(system, record['domain'], 0, list(range(record['address'], record['address'] + size)), record['format'],
                   stored, gt.decode_tile(stored, record['format']), [None] * size, 'unknown')


def plan_task(job: dict) -> dict:
    """Plan one edit and confirm it by replaying the scene. Returns {'writes', 'method', 'in_scene', ...} or {'error'}."""
    try:
        return {'tile': _plan_tile, 'tiles': _plan_tiles, 'cells': _plan_cells, 'level': _plan_level, 'color': _plan_color}[job['what']](job)
    except ValueError as error:
        return {'error': str(error)}
    except Exception as error:
        return {'error': f'{type(error).__name__}: {error}'}


def _plan_tile(job: dict) -> dict:
    scene, trail, rom, make, buttons, header, rgb = _setup(job)
    system = job['system']
    view = SceneGraphics(scene, system, rom, rgb, header['width'], header['height'])
    tile = view.tile(job['domain'], job['address'], job['format'])
    pixels = parse_pixels(job['pixels'], tile.format)
    new = gt.encode_tile(pixels, tile.format)
    avoid = [tuple(r) for r in job.get('avoid', [])]
    slow = gt.CPU[system] not in ('sm83', '6502')
    candidates = 6 if slow else 24
    calls = [0]

    def verify(plan, expect=None):
        calls[0] += 1
        _progress(job, job.get('step', 'Replaying the game to check'), calls[0], 0)
        return gt.verify_plan(make, rom, plan, scene, expect=expect, domains=TILE_DOMAINS, buttons_for=buttons)

    def step(text):
        job['step'] = text
        _progress(job, text)
    if job.get('scope') == 'only_this':
        step('Giving this scene its own copy of the picture…')
        plan = gt.plan_private_copy(tile, new, rom, scene, verify=verify, avoid=avoid, max_candidates=candidates)
        if not _good(plan.verified or {}):
            raise ValueError('A private copy was planned, but the replay did not show your picture in this scene.')
        return _plan_out(plan, rom)
    tried = []
    if tile.editable:
        step('Trying to write your picture straight into the ROM…')
        try:
            writes = gt.plan_tile_edit(tile, pixels, rom)
            plan = gt.EditPlan('direct', gt.with_checksums(rom, writes, system), len(rom), gt.expect_for(tile, new))
            result = verify(plan)
            if _good(result, tile):
                return _plan_out(plan, rom, 'direct' if tile.layout == 'plain' or tile.domain == 'chr_rom' else 'direct-packed')
            tried.append('written in place, the replay did not show the picture as drawn')
        except ValueError as error:
            tried.append(str(error))
    if tile.domain == 'chr_rom':
        raise ValueError('ROMancer wrote your picture into the ROM, but replaying the game did not show a change in this '
                         'scene, so it is not offered. ' + ' '.join(tried))
    step('Trying to pack your picture back into the ROM…' if tile.status != 'unknown' else 'Adding a small patch that swaps your picture in…')
    companions = job.get('companions', [])
    try:
        plan = gt.plan_derived_tile_edit(tile, pixels, rom, scene, verify=verify, avoid=avoid, max_candidates=candidates)
    except ValueError as error:
        raise ValueError(_tile_failure(system, tried + [str(error)])) from None
    block = (plan.details.get('block') or {}).get('start')
    packed = [c for c in companions if c.get('block') is not None and c['block'] == block and c.get('decoded')]
    patched = [c for c in companions if c.get('method') == 'overlay']
    if plan.kind in ('reencode', 'relocate') and packed:
        # Other kept changes edit pictures packed in the same set: pack them all together, so none is lost.
        step('Packing this picture together with the others you changed in the same set…')
        found = gt.find_compressed_block(scene, rom, system, tile.domain, tile.addresses[0], len(tile.addresses))
        changes = {a: new[k] for k, a in enumerate(tile.addresses) if new[k] != tile.stored[k]}
        raw = bytearray(found.decoded)
        for other in packed:
            for index, value in other['decoded'].items():
                raw[int(index)] = value
        plan = gt.plan_block_edit(replace(found, decoded=bytes(raw)), changes, rom, system, verify=verify, avoid=avoid,
                                  max_candidates=candidates)
        _also(plan, packed)
        if not _good(verify(plan)):
            raise ValueError('Your picture could not be packed together with the other changes to the same set. '
                             'Undo the other change to this set, or keep only one of them.')
    elif plan.kind == 'overlay' and patched:
        step('Adding this picture to the patch that already swaps in your other pictures…')
        edits = [(_stored_tile(t, system), parse_pixels(t['pixels'], t['format'])) for other in patched for t in other['tiles']
                 if (t['domain'], t['address']) != (tile.domain, tile.addresses[0])]
        options = [{}]
        if gt.CPU[system] == '65816':
            options = [{'after_handler': False}, {'after_handler': True}]
        elif gt.CPU[system] == '68000':
            options = [{'guard': True}, {'guard': False}]
        merged = None
        for option in options:
            candidate = gt.plan_overlay_patch(edits + [(tile, pixels)], rom, system, avoid=avoid, scene=scene, **option)
            candidate.expect = {tile.domain: {a: new[k] for k, a in enumerate(tile.addresses) if new[k] != tile.stored[k]}}
            _also(candidate, patched)
            if _good(verify(candidate)):
                merged = candidate
                break
        if merged is None:
            raise ValueError('Your picture could not be added to the patch that swaps in your other pictures. '
                             'Undo the other patched picture, or keep only one of them.')
        plan = merged
    out = _plan_out(plan, rom)
    if plan.kind in ('reencode', 'relocate'):
        found = plan.details.get('block') or {}
        try:
            block_object = gt.find_compressed_block(scene, rom, system, tile.domain, tile.addresses[0], len(tile.addresses))
            out['decoded'] = {str(block_object.decoded_index(a)): new[k] for k, a in enumerate(tile.addresses) if new[k] != tile.stored[k]}
            for other in packed:
                out['decoded'] = {**{str(k): v for k, v in other['decoded'].items()}, **out['decoded']}
            out['block_range'] = [found.get('start', 0), found.get('start', 0) + found.get('size', 0)]
        except (ValueError, AttributeError):
            pass
    out['tried'] = tried
    return out


def _also(plan, companions) -> None:
    """Earlier changes made in this same scene are part of the plan too, so they are expected rather than a surprise."""
    for other in companions:
        for name, cells in (other.get('expect') or {}).items():
            for index, value in cells.items():
                plan.expect.setdefault(name, {}).setdefault(int(index), value)


def _tile_failure(system: str, tried: list) -> str:
    name = SYSTEM_NAMES.get(system, system)
    text = ('ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. '
            'It is unpacked or drawn by the game while it runs')
    text += '.' if overlay_available(system) else f', and the patch that would swap it in is not available for {name} yet.'
    return text + ' What was tried: ' + ' '.join(t if t.endswith('.') else t + '.' for t in tried)


MAX_IMPORT_TILES = 1024
PATCH_TILES = 24         # pictures one swap-in patch holds (graphics_trace.plan_overlay_patch)


def _checksum_places(rom: bytes, system: str) -> set:
    """File offsets the cartridge checksum occupies; plans that are joined must not disagree about them."""
    found = set()
    middle, early = len(rom) // 2, min(len(rom) - 2, 0x1000 + gt.rom_skip(rom, system))
    for at in (middle, middle + 1, early, early + 1, len(rom) - 2, len(rom) - 1):      # odd and even: a word sum has two bytes
        probe = bytearray(rom)
        probe[at] ^= 0x55
        fixed = gt.fix_checksums(bytes(probe), rom, system)
        for start in range(0, len(fixed), 4096):
            if fixed[start:start + 4096] != probe[start:start + 4096]:
                found.update(i for i in range(start, min(start + 4096, len(fixed))) if fixed[i] != probe[i])
    if system == 'genesis':
        found.update(range(0x1A4, 0x1A8))
        found.update((0x18E, 0x18F))
    return whole_checksums(found, system)


def whole_checksums(found: set, system: str) -> set:
    """Every byte of the checksum fields that these bytes belong to.

    A checksum is a 16-bit sum, and a probe that changes one ROM byte usually
    moves only its low byte: the high byte moves only on a carry. Two edits
    then looked as if they needed the same ROM byte when all they shared was
    the other half of the checksum. The fields are two bytes on an even
    address (Game Boy 0x14E, Master System 0x7FFA, Mega Drive 0x18E); the
    Super NES keeps the sum and its complement in four.
    """
    size = 4 if system == 'snes' else 2
    return {start + k for o in found for start in (o - o % size,) for k in range(size)} | set(found)


def _plan_tiles(job: dict) -> dict:
    """Plan many pictures as one change (a PNG that was read back).

    The pictures are sorted by how the ROM keeps them. Those stored as plain
    data are written together and checked by one replay. Those packed in a
    set ROMancer recognises are packed again, one replay per set. The rest
    go into one swap-in patch where the system has it. Each group is checked
    on its own, then one more replay checks everything together. A picture
    that no way confirms is left out, with the reason, and the others are
    still offered.
    """
    scene, trail, rom, make, buttons, header, rgb = _setup(job)
    system = job['system']
    view = SceneGraphics(scene, system, rom, rgb, header['width'], header['height'])
    avoid = [tuple(r) for r in job.get('avoid', [])]
    slow = gt.CPU[system] not in ('sm83', '6502')
    candidates = 6 if slow else 24
    companions = job.get('companions', [])
    calls = [0]

    def verify(plan, expect=None):
        calls[0] += 1
        _progress(job, job.get('step', 'Replaying the game to check'), calls[0], 0)
        return gt.verify_plan(make, rom, plan, scene, expect=expect, domains=TILE_DOMAINS, buttons_for=buttons)

    def step(text):
        job['step'] = text
        _progress(job, text)

    def count(n):
        return f'{n} picture{"" if n == 1 else "s"}'

    items, skipped = [], []
    for record in job['tiles']:
        ident = tile_id(record['domain'], record['address'], record['format'])
        try:
            tile = view.tile(record['domain'], record['address'], record['format'])
            pixels = parse_pixels(record['pixels'], tile.format)
        except ValueError as error:
            skipped.append({'tile': ident, 'reason': str(error)})
            continue
        new = gt.encode_tile(pixels, tile.format)
        if new == tile.stored:
            continue
        items.append(SimpleNamespace(id=ident, tile=tile, pixels=pixels, new=new, expect=gt.expect_for(tile, new), tried=[]))
    if not items:
        raise ValueError('The picture you read in is the same as the scene, so there is nothing to change.')

    def expect_of(group) -> dict:
        out: dict = {}
        for item in group:
            for name, cells in item.expect.items():
                out.setdefault(name, {}).update(cells)
        return out

    def good(result, group) -> bool:
        if any(item.tile.domain != 'chr_rom' for item in group):
            return bool(result.get('as_planned'))
        return bool(result.get('verified'))          # the picture chip reads these straight from the ROM: the screen is the check

    parts = []           # {'method', 'block', 'decoded', 'items', 'plan'}
    used = []            # file ranges earlier groups write, so a later group does not take the same free space

    def taken(plan):
        used.extend((o, o + 1) for o, _, _ in plan.writes)

    # ---- 1. pictures stored as plain data
    direct, rest, seen = [], [], {}
    for item in items:
        if not item.tile.editable:
            rest.append(item)
            continue
        try:
            writes = gt.plan_tile_edit(item.tile, item.pixels, rom)
        except ValueError as error:
            item.tried.append(str(error))
            rest.append(item)
            continue
        if any(seen.get(o, n) != n for o, _, n in writes):
            skipped.append({'tile': item.id, 'reason': 'This picture shares stored bytes with another picture you changed, '
                                                      'and the two were drawn differently. Only the other one was changed.'})
            continue
        for o, _, n in writes:
            seen[o] = n
        item.writes = writes
        direct.append(item)
    for _ in range(3):
        if not direct:
            break
        step(f'Writing {count(len(direct))} straight into the ROM and replaying the game to check…')
        writes = sorted({(o, a, n) for item in direct for o, a, n in item.writes})
        plan = gt.EditPlan('direct', gt.with_checksums(rom, writes, system), len(rom), expect_of(direct))
        result = plan.verified = verify(plan)
        if good(result, direct):
            packed_in = any(item.tile.layout != 'plain' and item.tile.domain != 'chr_rom' for item in direct)
            parts.append({'method': 'direct-packed' if packed_in else 'direct', 'block': None, 'decoded': None, 'items': direct, 'plan': plan})
            taken(plan)
            direct = []
            break
        missed = {name: set(cells) for name, cells in (result.get('missed') or {}).items()}
        bad = [item for item in direct if item.tile.domain != 'chr_rom'
               and any(a in missed.get(item.tile.domain, ()) for a in item.tile.addresses)]
        if not bad:
            bad = list(direct)
        for item in bad:
            item.tried.append('written in place, the replay did not show the picture as drawn')
        rest.extend(bad)
        direct = [item for item in direct if item not in bad]
    for item in direct:
        item.tried.append('written in place, the replay did not show the picture as drawn')
        rest.append(item)

    # ---- 2. pictures packed in a set ROMancer can pack again
    def inside(block, tile) -> bool:
        try:
            return block.domain == tile.domain and all(block.decoded[block.decoded_index(a)] == tile.stored[k]
                                                       for k, a in enumerate(tile.addresses))
        except (ValueError, IndexError):
            return False

    blocks, loose = [], []
    for item in rest:
        tile = item.tile
        if tile.domain == 'chr_rom':
            skipped.append({'tile': item.id, 'reason': 'ROMancer wrote this picture into the ROM, but replaying the game did not '
                                                      'show a change in this scene, so it was left out.'})
            continue
        home = None
        if tile.addresses[-1] - tile.addresses[0] + 1 == len(tile.addresses):
            for block, members in blocks:
                if inside(block, tile):
                    home = members
                    break
            if home is None:
                step('Looking for how the game packs these pictures…')
                try:
                    block = gt.find_compressed_block(scene, rom, system, tile.domain, tile.addresses[0], len(tile.addresses))
                except ValueError:
                    block = None
                if block is None:
                    item.tried.append('no known packing reproduces this picture')
                else:
                    home = []
                    blocks.append((block, home))
        if home is None:
            loose.append(item)
        else:
            home.append(item)
    # A picture written in place can sit inside a set that is now packed again: it joins the set, or the two would
    # write the same bytes of the ROM differently.
    plain = next((part for part in parts if part['method'] in ('direct', 'direct-packed')), None)
    joiners = {}
    if plain is not None:
        claimed = []
        for number, (block, members) in enumerate(blocks):
            joiners[number] = [item for item in plain['items'] if item not in claimed and item.tile.domain != 'chr_rom'
                               and inside(block, item.tile)
                               and any(block.start <= o < block.start + block.size for o, _, _ in item.writes)]
            claimed.extend(joiners[number])

    def leave_plain(moved):
        plain['items'] = [item for item in plain['items'] if item not in moved]
        if not plain['items']:
            parts.remove(plain)
            return
        writes = sorted({(o, a, n) for item in plain['items'] for o, a, n in item.writes})
        rebuilt = gt.EditPlan('direct', gt.with_checksums(rom, writes, system), len(rom), expect_of(plain['items']))
        rebuilt.verified = plain['plan'].verified
        plain['plan'] = rebuilt
    for number, (block, own) in enumerate(blocks):
        members = own + joiners.get(number, [])
        step(f'Packing {count(len(members))} back into the ROM and replaying the game to check…')
        mates = [c for c in companions if c.get('block') is not None and c['block'] == block.start and c.get('decoded')]
        changes = {a: item.new[k] for item in members for k, a in enumerate(item.tile.addresses) if item.new[k] != item.tile.stored[k]}
        raw = bytearray(block.decoded)
        for other in mates:
            for index, value in other['decoded'].items():
                raw[int(index)] = value
        try:
            plan = gt.plan_block_edit(replace(block, decoded=bytes(raw)), changes, rom, system, verify=verify,
                                      avoid=avoid + used, max_candidates=candidates)
            _also(plan, mates)
            result = plan.verified = verify(plan)
            if not result.get('as_planned'):
                raise ValueError(f'{block.codec} packed again, the replay did not show the pictures as drawn')
            decoded = {str(block.decoded_index(a)): item.new[k] for item in members for k, a in enumerate(item.tile.addresses)
                       if item.new[k] != item.tile.stored[k]}
            for other in mates:
                decoded = {**{str(k): v for k, v in other['decoded'].items()}, **decoded}
            if joiners.get(number):
                leave_plain(joiners[number])
            parts.append({'method': plan.kind, 'block': block.start, 'decoded': decoded, 'items': members, 'plan': plan,
                          'range': [block.start, block.start + block.size]})
            taken(plan)
        except ValueError as error:
            for item in own:                 # the pictures written in place stay written in place
                item.tried.append(str(error))
            loose.extend(own)

    # ---- 3. the rest: one patch that swaps them in after the game has loaded them
    if loose and not overlay_available(system):
        for item in loose:
            skipped.append({'tile': item.id, 'reason': _tile_failure(system, item.tried)})
        loose = []
    patched = [c for c in companions if c.get('method') == 'overlay']
    if loose:
        mine = {(item.tile.domain, item.tile.addresses[0]) for item in loose}
        earlier = [(_stored_tile(t, system), parse_pixels(t['pixels'], t['format'])) for other in patched for t in other['tiles']
                   if (t['domain'], t['address']) not in mine]
        room = max(0, PATCH_TILES - len(earlier))
        for item in loose[room:]:
            skipped.append({'tile': item.id, 'reason': f'This picture is unpacked by the game in a way ROMancer cannot pack again. The patch '
                                                      f'that swaps such pictures in holds {PATCH_TILES}, and it is full.'})
        loose = loose[:room]
    def swap_in(group, before, reserved):
        """One patch that swaps `group` in (with the pictures `before` already patched); the plan, or None and why."""
        fired, errors = False, []
        for options in gt.OVERLAY_VARIANTS[gt.CPU[system]]:
            if options.get('hook') in ('irq', 'poll') and fired:
                continue
            try:
                plan = gt.plan_overlay_patch(before + [(item.tile, item.pixels) for item in group], rom, system,
                                             avoid=avoid + reserved, scene=scene, **options)
                plan.expect = expect_of(group)
                _also(plan, patched)
                result = plan.verified = verify(plan)
                fired = fired or bool(result.get('verified'))
                if result.get('as_planned'):
                    return plan, errors
                errors.append('the patch did not replay as planned')
            except ValueError as error:
                if str(error) not in errors:
                    errors.append(str(error))
        return None, errors

    patched = [c for c in companions if c.get('method') == 'overlay']
    if loose:
        step(f'Adding a small patch that swaps {count(len(loose))} in, and replaying the game to check…')
        chosen, errors = swap_in(loose, earlier, used)
        if chosen is None:
            for item in loose:
                skipped.append({'tile': item.id, 'reason': _tile_failure(system, item.tried + errors[:2])})
        else:
            parts.append({'method': 'overlay', 'block': None, 'decoded': None, 'items': loose, 'plan': chosen})
            taken(chosen)

    if not parts:
        reasons = []
        for entry in skipped:
            if entry['reason'] not in reasons:
                reasons.append(entry['reason'])
        raise ValueError('None of the pictures you changed could be changed in a way the real game confirmed, so nothing is changed. '
                         + ' '.join(reasons[:3]))

    # ---- 4. everything together
    checksum = _checksum_places(rom, system)

    def join(group):
        merged, size, notes = {}, len(rom), []
        for part in group:
            for o, a, n in part['plan'].writes:
                if o in checksum:
                    continue
                if o in merged and merged[o][1] != n:
                    raise ValueError(f"two groups of pictures need the same place in the ROM ({part['method']} at {o:#x}; "
                                     f"{len(checksum)} checksum bytes; groups {[p['method'] for p in group]})")
                merged[o] = (a, n)
            size = max(size, part['plan'].rom_size)
            notes.extend(n for n in part['plan'].notes if n not in notes)
        data = [(o, a, n) for o, (a, n) in sorted(merged.items())]
        fixed = gt.fix_checksums(gt.apply_writes(rom, data, size), rom, system)
        plan = gt.EditPlan('import', gt._diff_writes(rom, fixed), len(fixed), expect_of([i for part in group for i in part['items']]), notes)
        for part in group:
            for other in companions:
                if (part['block'] is not None and other.get('block') == part['block']) or \
                        (part['method'] == 'overlay' and other.get('method') == 'overlay'):
                    _also(plan, [other])
        return plan

    def everything(group):
        return [item for part in group for item in part['items']]

    together = None
    if len(parts) == 1:
        final = join(parts)
        final.verified = parts[0]['plan'].verified
    else:
        final = None
        try:
            step('Replaying the game once more with every picture together…')
            final = join(parts)
            result = final.verified = verify(final)
            if not good(result, everything(parts)):
                together = {'missed': {k: len(v) for k, v in (result.get('missed') or {}).items()},
                            'unplanned': dict(result.get('unplanned') or {}), 'verified': bool(result.get('verified'))}
                final = None
        except ValueError as error:
            together = {'error': str(error)}
            final = None
        if final is None and (together or {}).get('missed') and overlay_available(system):
            # Pictures written into packed data can change their neighbours, so a second group no longer matches what it
            # expected to find. One patch that swaps all of them in does not depend on how they are packed.
            pool = [item for item in everything(parts) if item.tile.domain != 'chr_rom']
            fixed = [part for part in parts if all(item.tile.domain == 'chr_rom' for item in part['items'])]
            mine = {(item.tile.domain, item.tile.addresses[0]) for item in pool}
            before = [(_stored_tile(t, system), parse_pixels(t['pixels'], t['format'])) for other in patched for t in other['tiles']
                      if (t['domain'], t['address']) not in mine]
            if pool and len(pool) + len(before) <= PATCH_TILES:
                step(f'These pictures share packed data. Swapping all {len(pool)} in with one patch instead…')
                reserved = [(o, o + 1) for part in fixed for o, _, _ in part['plan'].writes]
                chosen, _ = swap_in(pool, before, reserved)
                if chosen is not None:
                    group = fixed + [{'method': 'overlay', 'block': None, 'decoded': None, 'items': pool, 'plan': chosen}]
                    try:
                        final = join(group)
                        final.verified = chosen.verified if not fixed else verify(final)
                        fine = good(final.verified, everything(group))
                        if fine and len(scene.checkpoints) > 1:
                            # A patch can work from the moment before the scene and still not from power-on. The pictures
                            # written in place did work from there, so the patch only replaces them if it does too.
                            step('Checking that patch again, playing the game from the start…')
                            saved = scene.checkpoints
                            try:
                                scene.checkpoints = saved[:1]
                                fine = good(verify(final), everything(group))
                            finally:
                                scene.checkpoints = saved
                        if fine:
                            parts = group
                        else:
                            final = None
                    except ValueError:
                        final = None
        if final is None:
            # Take the groups that do not get in each other's way, largest first, and check those together.
            fits = []
            for part in sorted(parts, key=lambda part: -len(part['items'])):
                try:
                    join(fits + [part])
                    fits.append(part)
                except ValueError:
                    pass
            if 1 < len(fits) < len(parts):
                step('Replaying the game once more with the pictures that go together…')
                final = join(fits)
                result = final.verified = verify(final)
                if not good(result, everything(fits)):
                    final = None
            if final is None:
                fits = [max(parts, key=lambda part: len(part['items']))]
                final = join(fits)
                final.verified = fits[0]['plan'].verified
            for part in parts:
                if part not in fits:
                    for item in part['items']:
                        skipped.append({'tile': item.id, 'reason': 'This picture was confirmed on its own, but not together with the other '
                                                                  'pictures in this PNG: they share packed data in the ROM, and changing '
                                                                  'one changes what the other is made from. It was left out.'})
            parts = fits
    out = _plan_out(final, rom, 'import')
    out['parts'] = [{'method': part['method'], 'block': part['block'], 'decoded': part['decoded'], 'tiles': [i.id for i in part['items']],
                     'expect': {name: {str(i): int(v) for i, v in cells.items()} for name, cells in expect_of(part['items']).items()}}
                    for part in parts]
    out['block_ranges'] = [part['range'] for part in parts if part.get('range')]
    out['done'] = [item.id for item in everything(parts)]
    out['skipped'] = skipped
    out['replays'] = calls[0]
    out['together'] = together
    out['tried'] = []
    return out


def _plan_cells(job: dict) -> dict:
    scene, trail, rom, make, buttons, header, rgb = _setup(job)
    system = job['system']
    view = SceneGraphics(scene, system, rom, rgb, header['width'], header['height'])
    layers = view.layers()
    skip = gt.rom_skip(rom, system)
    writes, expect, packed, domain, built = {}, {}, {}, None, []
    for item in job['cells']:
        layer_view = layers[int(item['layer'])]
        layer = layer_view.layer
        cell = layer.cell(int(item['x']), int(item['y']))
        options = {}
        if item.get('tile') is not None:
            options['tile'] = hardware_tile(layer_view, cell, *parse_tile_id(item['tile']))
        for name in ('hflip', 'vflip'):
            if item.get(name) is not None and bool(item[name]) != getattr(cell, name):
                options[name] = bool(item[name])
        if item.get('line') is not None and int(item['line']) != cell.palette:
            options['palette'] = int(item['line'])
        if not options:
            continue
        if cell.status == 'unknown':
            raise ValueError(CELL_REASONS['unknown'])
        new = bytearray(cell.stored)
        _new_cell(cell, new, options)
        changed = {a: new[k] for k, a in enumerate(cell.addresses) if new[k] != cell.stored[k]}
        if not changed:
            continue
        domain = cell.domain
        expect.setdefault(cell.domain, {}).update(changed)
        if all(cell.sources[k] and cell.sources[k]['kind'] in ('rom', 'code') for k, a in enumerate(cell.addresses) if a in changed):
            for offset, old, value in gt.plan_tilemap_edit(cell, rom, skip=skip, **options):
                if writes.get(offset, (old, value))[1] != value:
                    raise ValueError('Two of the cells you painted are stored in the same place in the ROM, so they cannot '
                                     'be given different pictures. Paint them the same, or one at a time.')
                writes[offset] = (old, value)
        else:
            packed.update(changed)
            built.append((cell, bytes(new)))
    if not writes and not packed:
        raise ValueError('These cells already look like that. Paint a different picture first.')
    calls = [0]

    def verify(plan, wanted=None):
        calls[0] += 1
        _progress(job, 'Replaying the game to check the background…', calls[0], 0)
        return gt.verify_plan(make, rom, plan, scene, expect=wanted, domains=TILE_DOMAINS, buttons_for=buttons)
    if packed:
        if writes:
            raise ValueError('Some of these cells are stored plainly and some are packed. Paint the two kinds as separate changes.')
        _progress(job, 'Looking for this part of the background packed in the ROM…')
        low, high = min(packed), max(packed)
        block = gt.find_compressed_block(scene, rom, system, domain, low, high - low + 1)
        failure = None
        if block is not None:
            try:
                plan = gt.plan_block_edit(block, packed, rom, system, verify=verify, avoid=[tuple(r) for r in job.get('avoid', [])],
                                          max_candidates=6 if gt.CPU[system] not in ('sm83', '6502') else 24)
                if _good(verify(plan)):
                    return _plan_out(plan, rom, 'cells-reencode')
            except ValueError as error:
                failure = str(error)
        else:
            failure = ('The game builds this part of the background while it runs, and ROMancer could not find it '
                       'packed in the ROM in a form it knows.')
        # A stored piece is found by trying, so it must also hold over the longest replay there is: from the
        # earliest savestate of the recording that replays faithfully.
        start = pv.Scene(scene.id, scene.frame, scene.screen_sha256, scene.checkpoints[:1], scene.snapshot)

        def confirm(plan, wanted=None):
            calls[0] += 1
            _progress(job, 'Replaying the game from the start of the recording…', calls[0], 0)
            return gt.verify_plan(make, rom, plan, start, expect=wanted, domains=TILE_DOMAINS, buttons_for=buttons)
        try:
            return _plan_out(_plan_built_cells(job, built, rom, scene, system, [v.layer for v in layers], verify, expect,
                                               confirm if len(scene.checkpoints) > 1 else None), rom, 'cells-built')
        except ValueError as error:
            raise ValueError((failure or 'ROMancer packed your background back into the ROM, but replaying the game did not '
                              'show it as painted.') + ' ' + str(error)) from None
    _progress(job, 'Replaying the game to check the background…')
    plan = gt.EditPlan('direct', gt.with_checksums(rom, [(o, a, b) for o, (a, b) in sorted(writes.items())], system), len(rom), expect)
    if not _good(verify(plan)):
        missed = sum(len(v) for v in (plan.verified or {}).get('missed', {}).values())
        raise ValueError('ROMancer changed the stored background, but replaying the game did not show '
                         + ('some of the cells' if missed and (plan.verified or {}).get('verified') else 'the cells')
                         + ' as painted in this scene, so the change is not offered. The game may redraw them from somewhere else.')
    return _plan_out(plan, rom, 'cells')


def _plan_layout(job: dict) -> dict:
    """Put another block of the level where a block is, by changing the ROM's list of which block goes where.

    Every painted cell names the place whose picture it should show (`like`).
    level_layout finds the blocks the layer is built from and the places in
    the ROM that hold a row or column of block numbers. One byte of such a
    place is changed, the game is replayed from the start of the recording,
    and the place counts only when the whole block on screen then shows the
    block that was asked for. Raises ValueError('') when the layer is not
    built that way, and ValueError with the reason when it is but no place
    was confirmed.
    """
    from . import edit_session as es
    from . import level_layout as ll
    wanted = [item for item in job['cells'] if item.get('like')]
    if not wanted or len(wanted) != len(job['cells']):
        raise ValueError('')
    scene, trail, rom, make, buttons, header, rgb = _setup(job)
    system = job['system']
    skip = gt.rom_skip(rom, system)
    layers = gt.layers(scene, system)
    grids, others = {}, {}

    def grid_of(number):
        if number not in grids:
            layer = layers[number]
            grids[number] = ll.find_grid(ll.cell_sources(layer, skip), layer.width, layer.height)
        return grids[number]

    def source_layer(like):
        if like['scene_id'] == job['scene_id']:
            return layers[int(like['layer'])]
        if like['scene_id'] not in others:
            other, _, _ = es.read_scene(Path(job['store']) / 'scenes' / (like['scene_id'] + '.scene'))
            others[like['scene_id']] = gt.layers(other, system)
        return others[like['scene_id']][int(like['layer'])]

    blocks: dict = {}
    for item in wanted:
        number = int(item['layer'])
        grid = grid_of(number)
        if grid is None:
            raise ValueError('')
        x, y = int(item['x']), int(item['y'])
        at = grid.block(x, y)
        inside = grid.inside(x, y)
        mine = grid.first.get(at)
        like = item['like']
        there = source_layer(like)
        sources = ll.cell_sources(there, skip)
        lx, ly = int(like['x']), int(like['y'])
        k = inside[1] * grid.width + inside[0]
        origin = sources.get((lx, ly))
        if mine is None or origin is None:
            raise ValueError('')
        origin -= grid.pattern[k]
        corner = (lx - inside[0], ly - inside[1])
        whole = all(sources.get((corner[0] + dx, corner[1] + dy)) == origin + grid.pattern[dy * grid.width + dx]
                    for dy in range(grid.height) for dx in range(grid.width))
        if not whole or (origin - mine) % grid.step:
            raise ValueError('This level is built from blocks of %d by %d cells. Pick a whole block and paint it onto a whole block '
                             '(the same corner of the block you picked onto the same corner of the block you paint).' % (grid.width, grid.height))
        entry = blocks.setdefault((number, at), origin)
        if entry != origin:
            raise ValueError('Two of the places you painted are in one block of the level and ask for different blocks. '
                             'Paint a whole block at a time.')
    start = pv.Scene(scene.id, scene.frame, scene.screen_sha256, scene.checkpoints[:1], scene.snapshot)
    writes, expect, tried, entries = {}, {}, 0, {}

    def cells_of(number, at, origin):
        grid, layer = grids[number], layers[number]
        out = {}
        for dy in range(grid.height):
            for dx in range(grid.width):
                cell = layer.cell(grid.left + at[0] * grid.width + dx, grid.top + at[1] * grid.height + dy)
                out[cell.addresses[0]] = rom[origin + grid.pattern[dy * grid.width + dx]]
        return out

    def attempt(places, delta, target, domain):
        """The ROM byte among these that, moved by delta, makes the replay show the target and disturbs the least else.

        The first place that changes nothing but the block is taken at once. A place that also changes other
        parts of the screen (a piece the game uses in several places) is kept only if no later place does better.
        """
        nonlocal tried
        best = None
        for place in list(dict.fromkeys(places)):
            value = rom[place] + delta
            if not 0 <= value <= 255 or place in writes or tried >= MAX_LAYOUT_TRIES * max(1, len(blocks)):
                continue
            tried += 1
            _progress(job, 'Looking for where the level says which block goes here…', tried, 0)
            plan = gt.EditPlan('layout', gt.with_checksums(rom, [(place, rom[place], value)], system), len(rom), {domain: dict(target)})
            result = gt.verify_plan(make, rom, plan, start, expect=plan.expect, domains=TILE_DOMAINS, buttons_for=buttons)
            extra = sum((result.get('unplanned') or {}).values())
            if DEBUG_LAYOUT:
                print(f'layout try {place:#x}: {rom[place]:#x} -> {value:#x} as_planned {result.get("as_planned")} verified '
                      f'{result.get("verified")} missed {sum(len(v) for v in (result.get("missed") or {}).values())} of {len(target)} '
                      f'unplanned {result.get("unplanned")}', flush=True)
            if not result.get('as_planned'):
                continue
            if best is None or extra < best[0]:
                best = (extra, (place, rom[place], value))
            if extra <= len(target):                 # the block's own palette bytes at most: nothing else moved
                break
        return best[1] if best else None

    def listed(grid, at):
        """ROM bytes that may hold the number of block `at` in a list of blocks: in the ROM itself, then by way of memory."""
        places = []
        through = ll.runs(grid, *at)
        if DEBUG_LAYOUT:
            for kind, index, numbers in through:
                print(f'  {kind} {index} {numbers} whole-run hits {ll.find_rows(rom, numbers)} pieces '
                      f'{[(begin, len(piece), len(ll.find_rows(rom, piece, 4 if len(piece) > 2 else 8))) for begin, piece in ll.windows(numbers, index)[:8]]}', flush=True)
        for kind, index, numbers in through:
            for begin, piece in ll.windows(numbers, index)[:8]:
                places += [offset + index - begin for offset, base in ll.find_rows(rom, piece, 4 if len(piece) > 2 else 8)]
        for kind, index, numbers in through:
            for begin, piece in ll.windows(numbers, index)[:4]:
                places += [row[index - begin] for row in ll.find_in_memory(scene.snapshot, piece, skip, 4) if row[index - begin] is not None]
        return places

    # Larger blocks first: when every block of a larger block was painted and together they are another larger block,
    # the level's list of larger blocks is changed, and only that place changes.
    done, large = set(), 0
    for number in sorted({number for number, _ in blocks}):
        grid = grids[number]
        entries[number] = ll.find_entries(rom, grid)
        table = entries[number]
        if table is None:
            continue
        columns = max(at[0] for at in grid.first) + 1
        rows = max(at[1] for at in grid.first) + 1
        larger = ll.find_grid(table.placed, columns, rows)
        if larger is None or (larger.width, larger.height) != (table.width, table.height):
            continue
        lowest = min(grid.first.values())
        for at in sorted({larger.block(*block) for layer_number, block in blocks if layer_number == number}):
            members = [(larger.left + at[0] * larger.width + dx, larger.top + at[1] * larger.height + dy) for dx, dy in table.inside]
            if at not in larger.first or any((number, member) not in blocks for member in members):
                continue
            wish = tuple((blocks[(number, member)] - lowest) // grid.step for member in members)
            entry = table.entry(rom, wish)
            if entry is None:
                continue
            delta = (entry - larger.first[at]) // larger.step
            if not delta:
                continue
            target = {}
            for member in members:
                target.update(cells_of(number, member, blocks[(number, member)]))
            if DEBUG_LAYOUT:
                print(f'larger block {at}: wish {wish} entry {entry:#x} delta {delta} places {[hex(v) for v in listed(larger, at)[:8]]}', flush=True)
            found = attempt(listed(larger, at), delta, target, layers[number].cells[0].domain)
            if found is None:
                continue
            writes[found[0]] = (found[1], found[2])
            expect.setdefault(layers[number].cells[0].domain, {}).update(target)
            done.update((number, member) for member in members)
            large += 1
    for (number, at), origin in blocks.items():
        if (number, at) in done:
            continue
        grid, layer = grids[number], layers[number]
        mine = grid.first[at]
        delta = (origin - mine) // grid.step
        if not delta:
            continue
        target = cells_of(number, at, origin)
        places = listed(grid, at)
        shared = entries.get(number)
        if shared is not None and at in shared.placed:      # a table of larger blocks: every place that uses the larger block changes
            places.append(shared.placed[at])
        if DEBUG_LAYOUT:
            print(f'block {at}: delta {delta} places {[hex(v) for v in places[:10]]} table {None if shared is None else (len(shared.placed), at in shared.placed)} grid {grid.width}x{grid.height} step {grid.step} blocks {len(grid.first)} runs {[(k, i, len(n)) for k, i, n in ll.runs(grid, *at)]}', flush=True)
        found = attempt(places, delta, target, layer.cells[0].domain)
        if found is None:
            raise ValueError('ROMancer found the blocks this level is built from, but not a place in the ROM where changing the '
                             'block number put your block here when the game was replayed. The level may be packed.')
        writes[found[0]] = (found[1], found[2])
        expect.setdefault(layer.cells[0].domain, {}).update(target)
    if not writes:
        raise ValueError('These places already show that block. Pick a different block first.')
    plan = gt.EditPlan('layout', gt.with_checksums(rom, [(o, a, b) for o, (a, b) in sorted(writes.items())], system), len(rom), expect)
    plan.verified = gt.verify_plan(make, rom, plan, start, expect=expect, domains=TILE_DOMAINS, buttons_for=buttons)
    if not plan.verified.get('as_planned'):
        raise ValueError('Each block could be changed on its own, but not all of them together. Paint fewer blocks in one change.')
    small = len(writes) - large
    first = grids[next(iter(blocks))[0]]
    if large:
        table = next(e for e in entries.values() if e is not None)
        plan.notes.append(f"{large} larger block{'s' if large != 1 else ''} of {first.width * table.width} by {first.height * table.height} cells "
                          "changed in the level's own list of blocks.")
    if small:
        plan.notes.append(f"{small} block{'s' if small != 1 else ''} of {first.width} by {first.height} cells changed where the ROM "
                          'says which block goes there.')
    unplanned = sum((plan.verified.get('unplanned') or {}).values())
    if unplanned > 2 * sum(len(v) for v in expect.values()):
        plan.notes.append('Other places of the level changed with it, because the game uses the same stored piece there. '
                          'The level map shows them.')
    return _plan_out(plan, rom, 'layout')


def _plan_level(job: dict) -> dict:
    """Places painted on a level map: the cells of each scene are planned and confirmed in that scene, then put together.

    Each scene's cells are planned against the unchanged ROM, exactly as a
    background change made in that scene would be. A scene whose plan needs a
    ROM byte that an earlier scene's plan already set to something else is
    left out with the reason, as is one that cannot be changed at all; the
    rest are still offered. The result is the first confirmed scene's, with
    the bytes of all of them.
    """
    merged, first, skipped, parts, size = {}, None, [], [], 0
    groups = job['groups']
    for number, group in enumerate(groups):
        sub = {**job, 'what': 'cells', 'scene_id': group['scene_id'], 'cells': group['cells']}
        count = len(group['cells'])
        if len(groups) > 1:
            _progress(job, f'Planning the places in capture {number + 1} of {len(groups)}…', number, len(groups))
        try:
            try:
                result = _plan_layout(sub)          # where the level says which block goes here, when that can be found
            except ValueError as error:
                why = str(error)
                try:
                    result = _plan_cells(sub)       # otherwise the stored cell or block itself, wherever it is used
                except ValueError as second:
                    raise ValueError((why + ' ' if why else '') + str(second)) from None
                if why:
                    result['notes'] = list(result.get('notes', [])) + [why]
        except ValueError as error:
            skipped.append({'scene_id': group['scene_id'], 'cells': count, 'reason': str(error)})
            continue
        if any(o in merged and merged[o][1] != b for o, _, b in result['writes']):
            skipped.append({'scene_id': group['scene_id'], 'cells': count,
                            'reason': 'They are packed in the ROM together with other places you painted, and ROMancer cannot '
                                      'yet pack both in one change. Keep this change, then paint them as the next one.'})
            continue
        for o, a, b in result['writes']:
            merged.setdefault(o, [a, b])
        size = max(size, result.get('rom_size') or 0)
        parts.append({'scene_id': group['scene_id'], 'cells': count, 'method': result['method']})
        if first is None:
            first = dict(result, scene_id=group['scene_id'])
    if first is None:
        raise ValueError(skipped[0]['reason'])
    first.update(writes=[[o, a, b] for o, (a, b) in sorted(merged.items())], rom_size=size, skipped=skipped, parts=parts)
    return first


def _plan_built_cells(job: dict, built: list, rom: bytes, scene, system: str, layers: list, verify, expect: dict,
                      confirm=None):
    """Cells the game builds from stored pieces (blocks, tables): find each piece by replay and change it there.

    cell_trace.plan_cell_edit confirms every cell on its own; several cells
    are then replayed together, and the plan is kept only when all of them
    come out as painted. `confirm` is the replay from the start of the
    recording that each piece must pass as well. Other cells built from the same pieces change too:
    plan.details['also_cells'] lists them and a note says how many.
    """
    if len(built) > MAX_BUILT_CELLS:
        raise ValueError(f'These cells are not stored one by one in the ROM. ROMancer can look for the stored pieces the game '
                         f'builds them from, but only for up to {MAX_BUILT_CELLS} cells in one change. Paint fewer cells.')
    one = len(built) == 1
    merged, plans = {}, []
    for number, (cell, new) in enumerate(built):
        _progress(job, 'Looking for the stored piece the game builds this cell from…', number, len(built))
        try:
            plan = ct.plan_cell_edit(cell, new, rom, scene, system, verify=verify, layers=layers, paths=('cell-source',),
                                     confirm=confirm)
        except ValueError:
            raise ValueError('ROMancer also looked for a stored piece the game builds ' + ('this cell' if one else 'these cells')
                             + ' from, and replaying the game confirmed none. ' + ('This cell' if one else 'These cells')
                             + ' cannot be changed here.') from None
        plans.append(plan)
        for offset, old, value in plan.writes:
            if offset != plan.details['source_offset']:
                continue                             # a header checksum: worked out again for the cells together
            if merged.get(offset, (old, value))[1] != value:
                raise ValueError('Two of the cells you painted are built from the same stored piece, so they cannot be given '
                                 'different pictures. Paint them the same, or one at a time.')
            merged[offset] = (old, value)
    if one:
        return plans[0]
    data = sorted({plan.details['source_offset'] for plan in plans})
    plan = gt.EditPlan('cell-source', gt.with_checksums(rom, [(o, *merged[o]) for o in data], system), len(rom), expect)
    if not _good(verify(plan, expect)):
        raise ValueError('Each of these cells could be changed on its own, but not all of them together: they are built from '
                         'stored pieces that overlap. Paint them one at a time.')
    effects = ct.side_effects(plan.verified, expect, layers, system)
    if effects['outside_maps']:
        raise ValueError('Changing these cells together also changed video memory outside the backgrounds, so the change is '
                         'not offered. Paint them one at a time.')
    plan.details.update(effects, path='cell-source', source_offsets=data)
    others = len(effects['also_cells'])
    plan.notes.append('The game builds these cells from stored pieces; the pieces were changed.')
    if others:
        plan.notes.append(f'{others} other background cell{"s" if others != 1 else ""} in this scene '
                          f'change{"" if others != 1 else "s"} with them: the game builds them from the same stored pieces.')
    return plan


def _new_cell(cell, new: bytearray, options: dict) -> None:
    """Fill `new` with the bytes the cell would store (graphics_trace.plan_tilemap_edit's own encoding, read from its writes)."""
    blank = bytearray(len(cell.stored))
    marked = replace(cell, sources=[{'offset': k, 'kind': 'rom', 'weak': False, 'pc': 0} for k in range(len(cell.stored))])
    image = bytes(cell.stored) + bytes(blank)
    for offset, _, value in gt.plan_tilemap_edit(marked, image, skip=0, **options):
        new[offset] = value


def _plan_color(job: dict) -> dict:
    """Find the stored color behind a computed palette entry, checking each guess by replay."""
    from . import edit_session as es
    scene, trail, rom, make, buttons, header, rgb = _setup(job)
    system = job['system']
    swatch = next(s for s in pt.swatches(scene, system) if s.domain == job['domain'] and s.entry == job['entry'])
    lead = es.header_skip(rom, job['suffix'])
    body = rom[lead:]                                           # tags count from the end of any file header
    colors = job['colors']
    target = colors if swatch.format == 'dmg-shades' else colors[0]
    size = len(swatch.stored)
    slots = set(range(swatch.entry * size, (swatch.entry + 1) * size))
    wanted = pt.encode_swatch(swatch, target)
    starts = [f for f, _ in reversed(scene.checkpoints)]
    count = [0]

    every = sorted(header['checkpoints'], reverse=True)

    def replay(writes, wide=False):
        """(bytes of the entry after the change, other palette bytes that changed, whether the entry moved), from the
        latest savestate that shows the change in this entry. `wide` steps back through every savestate of the scene,
        not only the two latest and power-on: a palette loaded long before the scene needs one from before the load."""
        edited = bytearray(rom)
        for offset, _, value in writes:
            edited[offset] = value
        edited = es._with_checksums(bytes(edited), rom, system)
        path = Path(job['store']) / 'work' / (hashlib.sha256(edited).hexdigest()[:24] + job['suffix'])
        if not path.exists():
            path.write_bytes(edited)
        seen = (None, [], False)
        for start in (every if wide else starts):
            count[0] += 1
            _progress(job, job.get('step', ''), count[0], 0)
            base = trail.baseline(start)
            if base is None:
                continue                  # this savestate does not replay the unchanged game faithfully
            data, _ = trail.replay(path, start)
            changed = [i for i, (a, b) in enumerate(zip(base[swatch.domain], data[swatch.domain])) if a != b]
            if changed:
                # Another entry that held this same color and now holds the new one is the same stored color, loaded twice.
                twin = lambda i: (base[swatch.domain][i - i % size:i - i % size + size] == swatch.stored
                                  and data[swatch.domain][i - i % size:i - i % size + size] == wanted)
                seen = (bytes(data[swatch.domain][i] for i in sorted(slots)),
                        [i for i in changed if i not in slots and not twin(i)], bool(slots & set(changed)))
                if seen[2]:
                    break                 # the entry itself moved; otherwise an earlier savestate may still reach it
        return seen

    job['step'] = 'Checking whether the color is stored next to where it was traced…'
    _progress(job, job['step'])
    notes = []
    try:
        direct = [(o + lead, a, b) for o, a, b in pt.plan_derived_edit(swatch, target, body)]
    except ValueError:
        direct = []
    if direct:
        after, others, hit = replay(direct)
        if hit and after == wanted and not others:
            return {'writes': [list(w) for w in direct], 'method': 'color', 'notes': notes, 'as_planned': True}
    job['step'] = 'Looking in the ROM for a plain copy of this palette and replaying to check…'
    _progress(job, job['step'])
    for place in pt.found_places(swatch, pt.swatches(scene, system), body, system, job.get('hints') or ()):
        try:
            writes = [(o + lead, a, b) for o, a, b in pt.plan_at(swatch, target, body, place['offsets'])]
        except (ValueError, IndexError):
            continue
        if not writes:
            continue
        after, others, hit = replay(writes, wide=True)
        if hit and after == wanted and not others:
            return {'writes': [list(w) for w in writes], 'method': 'color', 'notes': [place['note']], 'as_planned': True,
                    'place': [o + lead for o in place['offsets']]}
    job['step'] = 'Changing nearby bytes one at a time and replaying, to see which ones this color comes from…'
    _progress(job, job['step'])

    def probe(edited_body):
        writes = [(lead + i, body[i], edited_body[i]) for start in range(0, len(body), 4096)
                  if body[start:start + 4096] != edited_body[start:start + 4096]
                  for i in range(start, min(start + 4096, len(body))) if body[i] != edited_body[i]]
        after, others, hit = replay(writes)
        return {'changed': {swatch.domain: sorted(slots) if hit else []}, 'others': others}
    hits = sorted(h['offset'] + lead for h in pt.locate_derived_source(probe, body, swatch, scene))
    if not hits and not any(source and source['kind'] == 'derived' for source in swatch.sources):
        raise ValueError('ROMancer has not seen where this color comes from, and did not find this palette stored as plain '
                         'colors in the ROM. It is probably packed, or made by the game as it runs.')
    if not hits:
        raise ValueError('ROMancer changed the bytes around where this color was traced and replayed the game each time, '
                         'but none of them changed it. The game works it out from something further away.')
    places = []
    for h in hits:
        for start in ([h] if size == 1 else [h, h - 1]):
            if start not in places and 0 <= start and start + size <= len(rom):
                places.append(start)
    places.sort(key=lambda start: -sum(start + k in hits for k in range(size)))
    job['step'] = 'Writing your color where the game reads it and replaying to check…'
    for start in places[:4]:
        writes = [(start + k, rom[start + k], wanted[k]) for k in range(size) if rom[start + k] != wanted[k]]
        if not writes:
            continue
        after, others, hit = replay(writes)
        if hit and not others and after == wanted:
            return {'writes': [list(w) for w in writes], 'method': 'color', 'notes': notes, 'as_planned': True,
                    'place': list(range(start, start + size))}
        if hit and not others and all(start + k in hits for k in range(size)):
            from .level_palette import decode_palette
            shown = [list(pt.NES_RGB[after[0] & 0x3F])] if swatch.format == 'nes-index' else decode_palette(after, swatch.format, len(swatch.rgb))
            return {'writes': [list(w) for w in writes], 'method': 'color', 'as_planned': False, 'shown': shown,
                    'place': list(range(start, start + size)),
                    'notes': ['The game dims or blends this color in this scene, so here it shows as a shade of the color '
                              'you picked. The pictures below are the real result.']}
    # Not one stored color: perhaps put together from several bytes. Measure what each bit does and solve for the color.
    job['step'] = 'Measuring what each nearby bit does to this color…'
    solved = pt.plan_by_measurement(lambda writes: replay(writes)[0], rom, hits, swatch.stored, wanted)
    if solved:
        after, others, hit = replay(solved)
        if hit and not others and after == wanted:
            return {'writes': [list(w) for w in solved], 'method': 'color', 'as_planned': True, 'place': [w[0] for w in solved],
                    'notes': ['The game builds this color from several bytes of a table. ROMancer measured what each one does '
                              'and changed the ones that give your color.']}
    raise ValueError('ROMancer found bytes that change this color, but writing your color there did not give a clean '
                     'result in the replay (other colors moved, or this one did not follow). It is left locked.')

