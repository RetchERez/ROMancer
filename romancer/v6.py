from __future__ import annotations

"""
ROMancer v6: PPU state tracking + structured visual queries.

Motivation: v5 gave us a CPU that can execute real ROM code with injected
fake input. But every attempt this session to verify *visual* outcomes
(does the cursor sprite appear, did Jake's tile move, is this HUD text
readable) fell back on either screenshotting a live emulator (unreliable
input plumbing, no query interface, pixel-diffing as a weak proxy for
"did anything meaningful change") or manually reverse-engineering tile
maps and OAM by hand.

This module tracks the actual PPU-facing state that ROM code writes
through the standard registers ($2100-$213F): VRAM, CGRAM (palette),
OAM (sprites), and the handful of mode/address registers that determine
how that data is interpreted (BG mode, tilemap/tile-data base addresses,
scroll, main/sub screen enable). It is NOT a cycle-accurate PPU -- no
HDMA, no color math, no window logic, no interlace. The goal is a
faithful-enough model to answer concrete questions:

  - What tile (and palette) is at this background tilemap position?
  - Where is sprite N (by tile ID or index), and is it visible?
  - Did anything change in this rectangular region between two frames?
  - What text (if any) does this tilemap region spell out, given a
    known font-to-character mapping?

This deliberately does NOT try to replace "look at a screenshot" with
"look at a different screenshot, but built by us." It replaces looking
at pixels with asking direct, verifiable questions of the underlying
data structures the game itself is manipulating.
"""

import json
from typing import Any

from .v5 import Sim65816
from .util import parse_int, write_json

VERSION = "6.0.0"


# ---------------------------------------------------------------------------
# PPU state model
# ---------------------------------------------------------------------------

class PPUState:
    def __init__(self):
        self.vram = bytearray(0x10000)   # 64KB VRAM, word-addressed by the game but stored as bytes
        self.cgram = bytearray(0x200)    # 256 colors * 2 bytes (BGR555)
        self.oam_low = bytearray(0x200)  # 128 sprites * 4 bytes
        self.oam_high = bytearray(0x20)  # 32 bytes, 2 bits/sprite (size + x-msb)

        # Address/latch state for the write-twice / auto-increment registers
        self.vmadd = 0
        self.vmain = 0x00          # increment mode/amount
        self._vram_latch = None    # low byte held until high byte written (word access)
        self.cgadd = 0
        self._cgram_latch = None   # low byte held until high byte written
        self.oamadd = 0
        self._oam_low_latch = None

        # Mode/scroll/address registers relevant to interpreting VRAM contents
        self.bgmode = 0
        self.bg_sc = {1: 0, 2: 0, 3: 0, 4: 0}       # BG1SC-BG4SC: tilemap base + size
        self.bg_nba = {1: 0, 2: 0, 3: 0, 4: 0}      # BG12NBA/BG34NBA: tile data base
        self.bg_hofs = {1: 0, 2: 0, 3: 0, 4: 0}
        self.bg_vofs = {1: 0, 2: 0, 3: 0, 4: 0}
        self._bg_scroll_latch = {}                   # per-register write-twice latch
        self.tm = 0   # main screen layer enable bits
        self.obsel = 0  # sprite size/base select
        self.inidisp = 0x0F  # screen brightness/force-blank

    # -- VRAM word access (game writes/reads VRAM in 16-bit words) --
    def vram_write_word(self, word_addr: int, value: int) -> None:
        byte_addr = (word_addr & 0x7FFF) * 2
        self.vram[byte_addr] = value & 0xFF
        self.vram[(byte_addr + 1) & 0xFFFF] = (value >> 8) & 0xFF

    def vram_read_word(self, word_addr: int) -> int:
        byte_addr = (word_addr & 0x7FFF) * 2
        return self.vram[byte_addr] | (self.vram[(byte_addr + 1) & 0xFFFF] << 8)

    def cgram_color(self, index: int) -> tuple[int, int, int]:
        """Return (r,g,b) 0-255 for a palette index, decoded from BGR555."""
        lo = self.cgram[(index * 2) & 0x1FF]
        hi = self.cgram[(index * 2 + 1) & 0x1FF]
        word = lo | (hi << 8)
        r5 = word & 0x1F
        g5 = (word >> 5) & 0x1F
        b5 = (word >> 10) & 0x1F
        scale = lambda v: (v * 255) // 31
        return (scale(r5), scale(g5), scale(b5))

    # -- Tile decode (2bpp/4bpp planar, the two SNES BG bit depths in play here) --
    def decode_tile(self, tile_id: int, base_word_addr: int, bpp: int) -> list[list[int]]:
        """Return an 8x8 grid of palette-index values (0 = transparent) for one tile."""
        bytes_per_tile = 8 * bpp
        words_per_tile = bytes_per_tile // 2
        start_word = base_word_addr + tile_id * words_per_tile
        planes = []
        for p in range(bpp):
            plane_words = []
            for row in range(8):
                if bpp <= 2:
                    w = self.vram_read_word(start_word + row)
                    plane_words.append((w >> (8 if p else 0)) & 0xFF if bpp == 2 else w & 0xFF)
                else:
                    pair_word = start_word + row + (p // 2) * 8
                    w = self.vram_read_word(pair_word)
                    plane_words.append((w >> 8) & 0xFF if (p % 2) else w & 0xFF)
            planes.append(plane_words)
        grid = [[0] * 8 for _ in range(8)]
        for row in range(8):
            for col in range(8):
                bit_pos = 7 - col
                val = 0
                for p in range(bpp):
                    bit = (planes[p][row] >> bit_pos) & 1
                    val |= bit << p
                grid[row][col] = val
        return grid

    # -- Tilemap lookup --
    def bg_tilemap_base_word(self, layer: int) -> int:
        return (self.bg_sc[layer] >> 2) * 0x400  # SC register: bits 2-6 = tilemap word address / 0x400

    def bg_tile_data_base_word(self, layer: int) -> int:
        nba = self.bg_nba[layer]
        if layer in (1, 3):
            return (nba & 0x0F) * 0x1000
        else:
            return ((nba >> 4) & 0x0F) * 0x1000

    def get_tilemap_entry(self, layer: int, tx: int, ty: int) -> dict:
        base = self.bg_tilemap_base_word(layer)
        map_word_addr = base + ty * 32 + tx
        entry = self.vram_read_word(map_word_addr)
        return {
            "tile_id": entry & 0x3FF,
            "palette": (entry >> 10) & 0x07,
            "priority": (entry >> 13) & 0x01,
            "hflip": (entry >> 14) & 0x01,
            "vflip": (entry >> 15) & 0x01,
        }

    # -- Sprites (OAM) --
    def list_sprites(self, only_visible: bool = True) -> list[dict]:
        sprites = []
        for i in range(128):
            lo = self.oam_low[i * 4: i * 4 + 4]
            x_lo, y, tile, attr = lo[0], lo[1], lo[2], lo[3]
            hi_byte = self.oam_high[i // 4]
            shift = (i % 4) * 2
            bits = (hi_byte >> shift) & 0x03
            x_msb = bits & 1
            size_bit = (bits >> 1) & 1
            x = x_lo | (x_msb << 8)
            if x >= 256:
                x -= 512  # sprites can be positioned off the left edge with a negative x
            sprite = {
                "index": i,
                "x": x,
                "y": y,
                "tile": tile | ((attr & 0x01) << 8),
                "palette": (attr >> 1) & 0x07,
                "priority": (attr >> 4) & 0x03,
                "hflip": (attr >> 6) & 0x01,
                "vflip": (attr >> 7) & 0x01,
                "size_bit": size_bit,
            }
            if not only_visible or (0 <= y < 224):
                sprites.append(sprite)
        return sprites

    def find_sprites_by_tile(self, tile_id: int) -> list[dict]:
        return [s for s in self.list_sprites() if s["tile"] == tile_id]


# ---------------------------------------------------------------------------
# CPU + PPU combined simulator
# ---------------------------------------------------------------------------

class Sim65816PPU(Sim65816):
    """Sim65816 with PPU register writes routed into a tracked PPUState."""

    def __init__(self, rom: bytes):
        super().__init__(rom)
        self.ppu = PPUState()

    def write8(self, bank: int, addr: int, val: int) -> None:
        addr16 = addr & 0xFFFF
        if self.is_hw_reg(bank, addr) and 0x2100 <= addr16 <= 0x213F:
            self._ppu_reg_write(addr16, val & 0xFF)
            return
        super().write8(bank, addr, val)

    def _ppu_reg_write(self, addr: int, val: int) -> None:
        p = self.ppu
        if addr == 0x2100:
            p.inidisp = val
        elif addr == 0x2101:
            p.obsel = val
        elif addr == 0x2102:
            p.oamadd = (p.oamadd & 0x100) | val
        elif addr == 0x2103:
            p.oamadd = (p.oamadd & 0xFF) | ((val & 1) << 8)
        elif addr == 0x2104:
            idx = p.oamadd
            if idx < 128 * 2:
                # low table, word-paired writes
                byte_index = idx
                if byte_index % 2 == 0:
                    p._oam_low_latch = val
                else:
                    lo_addr = (byte_index - 1)
                    if lo_addr < len(p.oam_low):
                        pass
                # simpler: OAM low table is written byte-at-a-time in sequence
                if idx < len(p.oam_low):
                    p.oam_low[idx] = val
            else:
                hi_idx = idx - 128 * 2
                if hi_idx < len(p.oam_high):
                    p.oam_high[hi_idx] = val
            p.oamadd = (p.oamadd + 1) & 0x1FF
        elif addr == 0x2105:
            p.bgmode = val
        elif addr == 0x2107:
            p.bg_sc[1] = val
        elif addr == 0x2108:
            p.bg_sc[2] = val
        elif addr == 0x2109:
            p.bg_sc[3] = val
        elif addr == 0x210A:
            p.bg_sc[4] = val
        elif addr == 0x210B:
            p.bg_nba[1] = val & 0x0F
            p.bg_nba[2] = (val >> 4) & 0x0F
        elif addr == 0x210C:
            p.bg_nba[3] = val & 0x0F
            p.bg_nba[4] = (val >> 4) & 0x0F
        elif addr in (0x210D, 0x210F, 0x2111, 0x2113):
            layer = {0x210D: 1, 0x210F: 2, 0x2111: 3, 0x2113: 4}[addr]
            key = ("h", layer)
            if key not in p._bg_scroll_latch:
                p._bg_scroll_latch[key] = val
            else:
                lo = p._bg_scroll_latch.pop(key)
                p.bg_hofs[layer] = lo | (val << 8)
        elif addr in (0x210E, 0x2110, 0x2112, 0x2114):
            layer = {0x210E: 1, 0x2110: 2, 0x2112: 3, 0x2114: 4}[addr]
            key = ("v", layer)
            if key not in p._bg_scroll_latch:
                p._bg_scroll_latch[key] = val
            else:
                lo = p._bg_scroll_latch.pop(key)
                p.bg_vofs[layer] = lo | (val << 8)
        elif addr == 0x2115:
            p.vmain = val
        elif addr == 0x2116:
            p.vmadd = (p.vmadd & 0xFF00) | val
        elif addr == 0x2117:
            p.vmadd = (p.vmadd & 0x00FF) | (val << 8)
        elif addr == 0x2118:
            cur = p.vram_read_word(p.vmadd)
            p.vram_write_word(p.vmadd, (cur & 0xFF00) | val)
            if p.vmain & 0x80:
                p.vmadd = (p.vmadd + self._vram_increment()) & 0xFFFF
        elif addr == 0x2119:
            cur = p.vram_read_word(p.vmadd)
            p.vram_write_word(p.vmadd, (cur & 0x00FF) | (val << 8))
            if not (p.vmain & 0x80):
                p.vmadd = (p.vmadd + self._vram_increment()) & 0xFFFF
        elif addr == 0x2121:
            p.cgadd = val
        elif addr == 0x2122:
            if p._cgram_latch is None:
                p._cgram_latch = val
            else:
                lo = p._cgram_latch
                p.cgram[(p.cgadd * 2) & 0x1FF] = lo
                p.cgram[(p.cgadd * 2 + 1) & 0x1FF] = val
                p.cgadd = (p.cgadd + 1) & 0xFF
                p._cgram_latch = None
        elif addr == 0x212C:
            p.tm = val
        # else: not modeled (window, color math, mode7 matrix, etc) -- ignored

    def _vram_increment(self) -> int:
        step = self.ppu.vmain & 0x03
        return {0: 1, 1: 32, 2: 128, 3: 128}[step]


# ---------------------------------------------------------------------------
# Query helpers exposed to the CLI
# ---------------------------------------------------------------------------

def render_tile_ascii(ppu: PPUState, tile_id: int, base_word_addr: int, bpp: int) -> str:
    grid = ppu.decode_tile(tile_id, base_word_addr, bpp)
    chars = " .:-=+*#%@"
    lines = []
    for row in grid:
        lines.append("".join(chars[min(v, len(chars) - 1)] for v in row))
    return "\n".join(lines)


def read_tilemap_region(ppu: PPUState, layer: int, tx: int, ty: int, w: int, h: int) -> list[list[dict]]:
    out = []
    for row in range(h):
        line = []
        for col in range(w):
            line.append(ppu.get_tilemap_entry(layer, tx + col, ty + row))
        out.append(line)
    return out


def read_tilemap_as_text(ppu: PPUState, layer: int, tx: int, ty: int, w: int, h: int,
                          font_map: dict[int, str]) -> list[str]:
    """font_map: {tile_id: character}, built once per game by cross-referencing
    known on-screen strings (see docs/font-mapping workflow)."""
    lines = []
    for row in range(h):
        chars = []
        for col in range(w):
            entry = ppu.get_tilemap_entry(layer, tx + col, ty + row)
            chars.append(font_map.get(entry["tile_id"], "?"))
        lines.append("".join(chars))
    return lines


def diff_region(before: PPUState, after: PPUState, layer: int, tx: int, ty: int, w: int, h: int) -> dict:
    changed = []
    for row in range(h):
        for col in range(w):
            b = before.get_tilemap_entry(layer, tx + col, ty + row)
            a = after.get_tilemap_entry(layer, tx + col, ty + row)
            if b != a:
                changed.append({"x": tx + col, "y": ty + row, "before": b, "after": a})
    return {"changed_count": len(changed), "changes": changed}


def sim_ppu_query(rom_path: str, entry: str, *, set_mem: list[str] | None = None,
                   set_reg: list[str] | None = None, max_steps: int = 5000,
                   stop_at: str | None = None, query: str = "sprites",
                   layer: int = 1, tx: int = 0, ty: int = 0, w: int = 8, h: int = 4,
                   tile_id: int = 0, out: str | None = None) -> dict:
    """Run the CPU+PPU simulator, then answer one structured visual query
    about the resulting state. query in: sprites, tilemap, tile_ascii."""
    rom = open(rom_path, "rb").read()
    cpu = Sim65816PPU(rom)

    eb, ea = entry.split(":")
    cpu.PB = int(eb, 16)
    cpu.PC = int(ea, 16)

    for item in set_reg or []:
        k, v = item.split("=", 1)
        ku = k.upper()
        val = parse_int(v)
        if ku == "A": cpu.A = val
        elif ku == "X": cpu.X = val
        elif ku == "Y": cpu.Y = val
        elif ku == "S": cpu.S = val
        elif ku == "D": cpu.D = val
        elif ku == "DB": cpu.DB = val
        elif ku == "PB": cpu.PB = val
        elif ku == "M": cpu.M = val
        elif ku == "XF": cpu.XF = val

    for item in set_mem or []:
        addr_part, val_part = item.split("=", 1)
        bank_s, addr_s = addr_part.split(":")
        bank = int(bank_s, 16); addr = int(addr_s, 16)
        wide = val_part.endswith(":16")
        val = parse_int(val_part[:-3] if wide else val_part)
        if wide:
            cpu.write16(bank, addr, val)
        else:
            cpu.write8(bank, addr, val)

    stop_pc = None
    if stop_at:
        sb, sa = stop_at.split(":")
        stop_pc = (int(sb, 16), int(sa, 16))

    result = cpu.run(max_steps=max_steps, stop_at=stop_pc)

    if query == "sprites":
        answer = {"sprites": cpu.ppu.list_sprites()}
    elif query == "sprites_by_tile":
        answer = {"sprites": cpu.ppu.find_sprites_by_tile(tile_id)}
    elif query == "tilemap":
        answer = {"tilemap": read_tilemap_region(cpu.ppu, layer, tx, ty, w, h)}
    elif query == "tile_ascii":
        base = cpu.ppu.bg_tile_data_base_word(layer)
        bpp = 4 if (cpu.ppu.bgmode & 0x07) in (0, 1, 3, 4) and layer <= 2 else 2
        answer = {"ascii": render_tile_ascii(cpu.ppu, tile_id, base, bpp)}
    else:
        answer = {"error": f"unknown query type: {query}"}

    report = {
        "tool": "ROMancer", "version": VERSION, "entry": entry,
        "result": result, "query": query, "answer": answer,
    }
    if out:
        write_json(out, report)
    return report
