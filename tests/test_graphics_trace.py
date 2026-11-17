"""Graphics tracing backend: tile formats, scene reading, edit plans, codecs, overlay.

Everything here runs without an emulator: scenes are built by hand, and the
"replay" used for relocation tests is a small model of a game that loads a
packed block through a pointer. The engine-backed checks live in
trace/graphics_sweep.py.
"""
import random
import unittest
from array import array

from romancer import gfx_codecs
from romancer import graphics_trace as gt
from romancer import provenance as pv


def tag(kind, offset, weak=False):
    return (kind << 28) | offset | (pv.RT_WEAK if weak else 0)


def make_scene(domains, frame=10):
    """domains: {name: (data bytes or None, [tags])}"""
    snap = pv.Snapshot(frame, {name: pv.DomainSnapshot(name, data, array('I', tags), array('I', [0x150] * len(tags)))
                               for name, (data, tags) in domains.items()}, 'screen')
    return pv.Scene('scene', frame, 'screen', [(0, b'')], snap)


def gb_rom(size=0x8000, fill=0x55):
    rom = bytearray([fill]) * size
    rom[0x40:0x43] = b'\xC3\x00\x02'            # vertical-blank vector: jp $0200
    rom[0x134:0x144] = b'TEST            '
    return rom


class TileFormatTests(unittest.TestCase):
    def test_every_format_round_trips(self):
        rng = random.Random(7)
        for fmt, (bpp, size) in gt.TILE_FORMATS.items():
            for _ in range(20):
                pixels = [rng.randrange(1 << bpp) for _ in range(64)]
                raw = gt.encode_tile(pixels, fmt)
                self.assertEqual(len(raw), size, fmt)
                self.assertEqual(gt.decode_tile(raw, fmt), pixels, fmt)
                self.assertEqual(gt.encode_tile(gt.decode_tile(raw, fmt), fmt), raw, fmt)

    def test_known_layouts(self):
        # Game Boy: low plane byte then high plane byte per row, leftmost pixel in bit 7.
        self.assertEqual(gt.decode_tile(bytes([0x80, 0x40]) + bytes(14), 'gb-2bpp')[:8], [1, 2, 0, 0, 0, 0, 0, 0])
        # NES: eight rows of plane 0, then eight rows of plane 1.
        raw = bytes([0x80]) + bytes(7) + bytes([0xC0]) + bytes(7)
        self.assertEqual(gt.decode_tile(raw, 'nes-2bpp')[:8], [3, 2, 0, 0, 0, 0, 0, 0])
        # SNES 4bpp: planes 0/1 interleaved in the first 16 bytes, planes 2/3 in the last 16.
        raw = bytearray(32); raw[0] = 0x80; raw[1] = 0x40; raw[16] = 0x20; raw[17] = 0x10
        self.assertEqual(gt.decode_tile(bytes(raw), 'snes-4bpp')[:8], [1, 2, 4, 8, 0, 0, 0, 0])
        # Genesis: one nibble per pixel, high nibble first.
        self.assertEqual(gt.decode_tile(bytes([0x12, 0x34, 0xEF, 0x00]) + bytes(28), 'genesis-4bpp')[:8], [1, 2, 3, 4, 14, 15, 0, 0])
        # Master System: four plane bytes per row.
        self.assertEqual(gt.decode_tile(bytes([0x80, 0x40, 0x20, 0x10]) + bytes(28), 'sms-4bpp')[:8], [1, 2, 4, 8, 0, 0, 0, 0])
        # SNES 8bpp continues the plane pairs.
        raw = bytearray(64); raw[48] = 0x80; raw[49] = 0x80
        self.assertEqual(gt.decode_tile(bytes(raw), 'snes-8bpp')[0], 0xC0)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            gt.decode_tile(bytes(15), 'gb-2bpp')
        with self.assertRaises(ValueError):
            gt.encode_tile([4] * 64, 'gb-2bpp')
        with self.assertRaises(ValueError):
            gt.encode_tile([0] * 63, 'genesis-4bpp')

    def test_header_skip(self):
        self.assertEqual(gt.rom_skip(b'NES\x1a' + bytes(100), 'nes'), 16)
        self.assertEqual(gt.rom_skip(bytes(0x8200), 'snes'), 512)
        self.assertEqual(gt.rom_skip(bytes(0x8000), 'snes'), 0)
        self.assertEqual(gt.rom_skip(bytes(0x8000), 'gb'), 0)


class CodecTests(unittest.TestCase):
    def sample(self, rng, n):
        out = bytearray()
        while len(out) < n:
            m = rng.random()
            if m < .3:
                out += bytes([rng.choice([0, 0xFF, rng.randrange(256)])]) * rng.randrange(1, 40)
            elif m < .4:
                out += bytes([rng.randrange(256), rng.randrange(256)]) * rng.randrange(2, 10)
            elif m < .6 and len(out) > 8:
                a = rng.randrange(len(out)); out += out[a:a + rng.randrange(1, 60)]
            elif m < .7 and len(out) > 8:
                a = rng.randrange(len(out)); out += out[max(0, a - 12):a][::-1]
            else:
                out += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 20)))
        return bytes(out[:n])

    def test_every_codec_round_trips(self):
        rng = random.Random(3)
        for name, codec in gfx_codecs.CODECS.items():
            for n in (32, 64, 96, 640, 2048):
                raw = self.sample(rng, n)
                if name == 'enigma':   # tilemap words: tile number in 11 bits plus five flag bits
                    raw = bytes(b if i & 1 else b & 0xFF for i, b in enumerate(raw))
                stream = gfx_codecs.encode(name, raw)
                out, used = gfx_codecs.decode(name, stream + b'\x5A' * 8, 0, 0x10000 if codec['terminated'] else n)
                self.assertEqual(out, raw, name)
                if codec['terminated']:
                    self.assertEqual(used, len(stream), name)

    def test_lz2_known_stream(self):
        # literal "AB", byte fill x4 of 0x07, increment fill x3 from 1, copy 2 from offset 0, end
        stream = bytes([0x01, 0x41, 0x42, 0x23, 0x07, 0x62, 0x01, 0x81, 0x00, 0x00, 0xFF])
        self.assertEqual(gfx_codecs.decode('lz2', stream)[0], b'AB' + b'\x07' * 4 + b'\x01\x02\x03' + b'AB')

    def test_lz3_relative_and_reversed_copies(self):
        # literal 0x80 0x01, bit-reversed copy of 2 from 2 back (relative), zero fill x3, end
        stream = bytes([0x01, 0x80, 0x01, 0xA1, 0x81, 0x62, 0xFF])
        self.assertEqual(gfx_codecs.decode('lz3', stream)[0], bytes([0x80, 0x01, 0x01, 0x80, 0, 0, 0]))

    def test_kosinski_known_stream(self):
        # description field FF FF: 16 literals. The next field is read as soon as the last
        # bit is used, so it sits in front of the sixteenth literal.
        stream = b'\xFF\xFF' + bytes(range(15)) + b'\x02\x00' + b'\x0F' + b'\x00\xF0\x00'
        out, used = gfx_codecs.decode('kosinski', stream)
        self.assertEqual(out, bytes(range(16)))
        self.assertEqual(used, len(stream))

    def test_nemesis_inline_only_stream(self):
        # one tile, no code table, every run written inline: 111111 ccc nnnn with count 7 (8 nibbles)
        bits = ''.join('111111' + '111' + '0101' for _ in range(8))
        body = bytes(int(bits[i:i + 8].ljust(8, '0'), 2) for i in range(0, len(bits), 8))
        out, _ = gfx_codecs.decode('nemesis', b'\x00\x01\xFF' + body)
        self.assertEqual(out, b'\x55' * 32)

    def test_garbage_is_rejected_or_bounded(self):
        rng = random.Random(5)
        for name in gfx_codecs.CODECS:
            for _ in range(40):
                junk = bytes(rng.randrange(256) for _ in range(300))
                try:
                    out, used = gfx_codecs.decode(name, junk, 0, 0x2000)
                except (ValueError, IndexError):
                    continue
                self.assertLessEqual(used, len(junk))


class SceneReadingTests(unittest.TestCase):
    def gb_scene(self):
        rom = gb_rom()
        vram = bytearray(0x4000)
        tags = [0] * 0x4000
        # tile 1: plain copy of ROM $4000..$400F
        rom[0x4000:0x4010] = bytes(range(0x10, 0x20))
        vram[16:32] = rom[0x4000:0x4010]
        tags[16:32] = [tag(pv.RT_ROM, 0x4000 + k) for k in range(16)]
        # tile 2: run-length source, one ROM byte feeds two tile bytes
        rom[0x4100] = 0x3C
        rom[0x4101:0x410F] = bytes(range(0x61, 0x6F))
        vram[32:48] = bytes([0x3C, 0x3C]) + rom[0x4101:0x410F]
        tags[32:48] = [tag(pv.RT_ROM, 0x4100), tag(pv.RT_ROM, 0x4100)] + [tag(pv.RT_ROM, 0x4101 + k) for k in range(14)]
        # tile 3: computed
        vram[48:64] = bytes(range(0x90, 0xA0))
        tags[48:64] = [tag(pv.RT_DERIVED, 0x4200)] * 16
        # tile 4: loaded by immediates
        rom[0x300:0x310] = bytes(range(0xB0, 0xC0))
        vram[64:80] = rom[0x300:0x310]
        tags[64:80] = [tag(pv.RT_IMM, 0x300 + k) for k in range(16)]
        # background map at $9800: cell (0,0) shows tile 1 and traces to ROM $4300
        rom[0x4300] = 1
        vram[0x1800] = 1
        tags[0x1800] = tag(pv.RT_ROM, 0x4300)
        vram[0x1801] = 3
        tags[0x1801] = tag(pv.RT_DERIVED, 0x4301)
        scene = make_scene({'vram': (bytes(vram), tags), 'oam': (bytes(0xA0), [0] * 0xA0)})
        scene.video = {'system': 'gb', 'source': 'registers', 'lcdc': 0x91, 'scx': 0, 'scy': 0, 'wx': 0, 'wy': 0}
        return bytes(rom), scene

    def test_tile_status_and_layout(self):
        rom, scene = self.gb_scene()
        tiles = gt.tiles(scene, 'gb')
        self.assertEqual(len(tiles), 384)          # second bank never written
        self.assertEqual([tiles[i].status for i in range(5)], ['unknown', 'rom', 'rom', 'derived', 'code'])
        self.assertEqual(tiles[1].layout, 'plain')
        self.assertEqual(tiles[2].layout, 'scattered')
        self.assertTrue(tiles[1].editable and tiles[4].editable)
        self.assertFalse(tiles[3].editable)
        self.assertEqual(tiles[1].sources[5], {'offset': 0x4005, 'kind': 'rom', 'weak': False, 'pc': 0x150})
        self.assertEqual(tiles[1].pixels, gt.decode_tile(rom[0x4000:0x4010], 'gb-2bpp'))
        import json
        json.dumps(tiles[1].to_dict())

    def test_plan_tile_edit_writes_only_changed_bytes(self):
        rom, scene = self.gb_scene()
        tile = gt.tiles(scene, 'gb')[1]
        pixels = list(tile.pixels)
        pixels[0] ^= 3                              # top-left pixel: both planes of row 0
        writes = gt.plan_tile_edit(tile, pixels, rom)
        self.assertEqual([w[0] for w in writes], [0x4000, 0x4001])
        edited = gt.apply_writes(rom, writes)
        self.assertEqual(gt.decode_tile(edited[0x4000:0x4010], 'gb-2bpp'), pixels)
        for off, old, new in writes:
            self.assertEqual(rom[off], old)

    def test_plan_tile_edit_checks_the_rom(self):
        rom, scene = self.gb_scene()
        tile = gt.tiles(scene, 'gb')[1]
        stale = bytearray(rom); stale[0x4000] ^= 0xFF
        with self.assertRaisesRegex(ValueError, 'take a new scene'):
            gt.plan_tile_edit(tile, [3 - p for p in tile.pixels], bytes(stale))

    def test_plan_tile_edit_refuses_packed_conflicts_and_computed_tiles(self):
        rom, scene = self.gb_scene()
        tiles = gt.tiles(scene, 'gb')
        px = list(tiles[2].pixels)
        px[0] ^= 1                                  # byte 0 changes, byte 1 (same ROM byte) must stay
        with self.assertRaisesRegex(ValueError, 're-encoded'):
            gt.plan_tile_edit(tiles[2], px, rom)
        with self.assertRaisesRegex(ValueError, 'computed'):
            gt.plan_tile_edit(tiles[3], [3 - p for p in tiles[3].pixels], rom)
        # both bytes that share the ROM byte changing together is fine
        both = list(tiles[2].stored); both[0] = both[1] = 0xC3
        writes = gt.plan_tile_edit(tiles[2], gt.decode_tile(bytes(both), 'gb-2bpp'), rom)
        self.assertEqual(writes, [(0x4100, 0x3C, 0xC3)])

    def test_layers_and_map_edit(self):
        rom, scene = self.gb_scene()
        (bg,) = gt.layers(scene, 'gb')
        self.assertEqual((bg.name, bg.width, bg.height, bg.layout_source), ('background', 32, 32, 'registers'))
        cell = bg.cell(0, 0)
        self.assertEqual((cell.tile, cell.tile_address, cell.status), (1, 16, 'rom'))
        self.assertEqual(bg.cell(1, 0).status, 'derived')
        self.assertEqual(gt.plan_tilemap_edit(cell, rom, tile=4), [(0x4300, 1, 4)])
        with self.assertRaises(ValueError):
            gt.plan_tilemap_edit(bg.cell(1, 0), rom, tile=4)
        with self.assertRaises(ValueError):
            gt.plan_tilemap_edit(cell, rom, hflip=True)   # no attributes on the original Game Boy
        self.assertIn(16, gt.used_tile_addresses(scene, 'gb'))
        # signed tile numbering when LCDC bit 4 is clear
        scene.video['lcdc'] = 0x81
        self.assertEqual(gt.layers(scene, 'gb')[0].cell(0, 0).tile, 257)

    def test_layout_is_inferred_without_registers(self):
        rom, scene = self.gb_scene()
        scene.video = None
        (bg,) = gt.layers(scene, 'gb')
        self.assertEqual(bg.layout_source, 'inferred')
        self.assertEqual(bg.cell(0, 0).tile, 1)

    def test_predicted_effects_and_impact(self):
        rom, scene = self.gb_scene()
        self.assertEqual(gt.predicted_effects(scene, [(0x4100, 0x3C, 0)]), {'vram': [32, 33]})
        index = pv.ImpactIndex()
        index.add(scene)
        self.assertEqual(gt.impact(index, [(0x4100, 0x3C, 0)]), {'scene': ['vram']})
        self.assertEqual(gt.sharing(index, 0x4000, 0x4010, scene), {'scenes': 1, 'other_scenes': {}, 'shared': False})
        self.assertEqual(gt.source_run(scene, 'vram', 20), (16, 32, 0x4000, 0x4010))

    def test_gbc_cell_attributes(self):
        rom = gb_rom()
        vram = bytearray(0x4000); tags = [0] * 0x4000
        vram[0x1800] = 5; tags[0x1800] = tag(pv.RT_ROM, 0x4400); rom[0x4400] = 5
        vram[0x3800] = 0x6B; tags[0x3800] = tag(pv.RT_ROM, 0x4500); rom[0x4500] = 0x6B
        scene = make_scene({'vram': (bytes(vram), tags)})
        scene.video = {'lcdc': 0x91, 'scx': 0, 'scy': 0, 'wx': 0, 'wy': 0}
        cell = gt.layers(scene, 'gbc')[0].cell(0, 0)
        self.assertEqual((cell.tile, cell.palette, cell.hflip, cell.vflip, cell.tile_address), (384 + 5, 3, True, True, 0x2000 + 80))
        self.assertEqual(gt.plan_tilemap_edit(cell, bytes(rom), palette=1, hflip=False), [(0x4500, 0x6B, 0x49)])

    def test_nes_chr_rom_tiles_come_from_the_pattern_map(self):
        prg = bytes(0x4000)
        chr_rom = bytes(random.Random(1).randrange(256) for _ in range(0x2000))
        prg = bytearray(prg); prg[0x123] = 7; prg[0x200] = 0b10
        rom = b'NES\x1a\x01\x01' + bytes(10) + bytes(prg) + chr_rom
        tags = [tag(pv.RT_ROM, 0x4000 + slot * 0x400) for slot in range(8)]
        names = bytearray(0x800); ntags = [0] * 0x800
        names[0] = 7; ntags[0] = tag(pv.RT_ROM, 0x123)
        names[0x3C0] = 0b10; ntags[0x3C0] = tag(pv.RT_ROM, 0x200)
        scene = make_scene({'chr_map': (None, tags), 'vram': (bytes(names), ntags)})
        tiles = gt.tiles(scene, 'nes', rom)
        self.assertEqual(len(tiles), 512)
        t = tiles[300]
        self.assertEqual((t.domain, t.status, t.layout), ('chr_rom', 'rom', 'plain'))
        self.assertEqual(t.stored, chr_rom[300 * 16:301 * 16])
        writes = gt.plan_tile_edit(t, [3 - p for p in t.pixels], rom)
        self.assertEqual(writes[0][0], 16 + 0x4000 + 300 * 16)     # file offset includes the iNES header
        self.assertEqual(gt.expect_for(t, bytes(16)), {})
        layer = gt.layers(scene, 'nes', {'ppuctrl': 0x10})[0]
        cell = layer.cell(0, 0)
        self.assertEqual((cell.tile, cell.palette, layer.tile_domain), (256 + 7, 2, 'chr_rom'))
        self.assertEqual(gt.plan_tilemap_edit(cell, rom, tile=9), [(16 + 0x123, 7, 9)])
        self.assertEqual(gt.plan_tilemap_edit(cell, rom, palette=1), [(16 + 0x200, 0b10, 0b01)])

    def test_16_bit_map_cells(self):
        for system, raw, fields in (
                ('snes', bytes([0x34, 0xC5]), dict(tile=0x134, palette=1, hflip=True, vflip=True, priority=False)),
                ('genesis', bytes([0xA9, 0x34]), dict(tile=0x134, palette=1, hflip=True, vflip=False, priority=True)),
                ('sms', bytes([0x34, 0x0B]), dict(tile=0x134, palette=1, hflip=True, vflip=False, priority=False))):
            size = 0x4000 if system == 'sms' else 0x10000
            base = {'snes': 0x2000, 'genesis': 0xC000, 'sms': 0x3800}[system]
            vram = bytearray(size); tags = [0] * size
            vram[base:base + 2] = raw
            tags[base:base + 2] = [tag(pv.RT_ROM, 0x1000), tag(pv.RT_ROM, 0x1001)]
            rom = bytearray(0x8000); rom[0x1000:0x1002] = raw
            scene = make_scene({'vram': (bytes(vram), tags)})
            video = None
            if system == 'snes':
                video = {'bg_mode': 1, 'bg_scaddr': [0x2000, 0, 0, 0], 'bg_scsize': [0, 0, 0, 0], 'bg_tdaddr': [0x4000, 0, 0, 0],
                         'bg_hofs': [0] * 4, 'bg_vofs': [0] * 4, 'bg_tilesize': [0] * 4, 'oam_tdaddr': 0, 'oam_nameselect': 0}
            layer = gt.layers(scene, system, video)[0]
            cell = layer.cell(0, 0)
            for k, v in fields.items():
                self.assertEqual(getattr(cell, k), v, (system, k))
            writes = gt.plan_tilemap_edit(cell, bytes(rom), tile=0x135)
            self.assertEqual(len(writes), 1, system)
            edited = gt.apply_writes(bytes(rom), writes)
            e = edited[0x1000:0x1002]
            value = (e[0] << 8 | e[1]) if system == 'genesis' else (e[0] | e[1] << 8)
            self.assertEqual(value & 0x1FF, 0x135, system)
        self.assertEqual(gt.layers(make_scene({'vram': (bytes(0x10000), [0] * 0x10000)}), 'snes'), [])

    def test_snes_mode_7_cells_are_single_bytes(self):
        vram = bytearray(0x10000); tags = [0] * 0x10000
        vram[6] = 9; tags[6] = tag(pv.RT_ROM, 0x1234)        # cell (3, 0): low byte of word 3
        rom = bytearray(0x8000); rom[0x1234] = 9
        scene = make_scene({'vram': (bytes(vram), tags)})
        (layer,) = gt.layers(scene, 'snes', {'bg_mode': 7})
        cell = layer.cell(3, 0)
        self.assertEqual((layer.width, layer.tile_format, cell.tile, cell.tile_address, cell.status),
                         (128, 'snes-mode7', 9, 9 * 128 + 1, 'rom'))
        self.assertEqual(gt.plan_tilemap_edit(cell, bytes(rom), tile=10), [(0x1234, 9, 10)])
        with self.assertRaises(ValueError):
            gt.plan_tilemap_edit(cell, bytes(rom), hflip=True)
        self.assertEqual(len(gt.tiles(scene, 'snes', fmt='snes-mode7')), 256)


class MiniGame:
    """Stand-in for an engine: a Game Boy game that unpacks one block through a pointer into video memory."""

    def __init__(self, codec, pointer_at, vram_at, far=False):
        self.codec, self.pointer_at, self.vram_at, self.far = codec, pointer_at, vram_at, far

    def vram(self, rom):
        if self.far:
            bank = rom[self.pointer_at]
            addr = rom[self.pointer_at + 1] | rom[self.pointer_at + 2] << 8
            start = bank * 0x4000 + (addr - 0x4000)
        else:
            addr = rom[self.pointer_at] | rom[self.pointer_at + 1] << 8
            start = addr if addr < 0x4000 else 0x4000 + (addr - 0x4000)   # block lives in bank 1
        out = bytearray(0x4000)
        data, _ = gfx_codecs.decode(self.codec, rom, start)
        out[self.vram_at:self.vram_at + len(data)] = data
        return bytes(out)

    def verifier(self, rom, scene):
        before = scene.snapshot.domains['vram'].data

        def verify(plan):
            try:
                after = self.vram(plan.apply(rom))
            except (ValueError, IndexError):
                return {'verified': False, 'as_planned': False, 'changed': {}}
            changed = [i for i in range(len(after)) if after[i] != before[i]]
            ok = bool(changed) and all(after[i] == v for i, v in plan.expect.get('vram', {}).items())
            planned = set(plan.expect.get('vram', {}))
            return {'verified': bool(changed), 'as_planned': ok, 'changed': {'vram': changed}, 'from_frame': 0,
                    'unplanned': {'vram': sum(i not in planned for i in changed)} if any(i not in planned for i in changed) else {}}
        return verify


class CompressedBlockTests(unittest.TestCase):
    def build(self, codec='lz3', far=False, room=True):
        rng = random.Random(11)
        tiles = bytearray()
        for n in range(24):
            row = bytes(rng.randrange(256) for _ in range(4))
            tiles += row * 2 + bytes(4) + bytes(rng.randrange(256) for _ in range(4))
        raw = bytes(tiles)
        stream = gfx_codecs.encode(codec, raw)
        rom = gb_rom(0x10000, 0x55)
        start = 0x5000
        rom[start:start + len(stream)] = stream
        if room:
            rom[0x7000:0x7800] = b'\xFF' * 0x800      # free space in bank 1
            rom[0xC000:0xC800] = b'\xFF' * 0x800      # and in bank 3
        if far:
            rom[0x1000:0x1003] = bytes([1, start & 0xFF, 0x40 | (start >> 8 & 0x3F)])
        else:
            rom[0x1000] = 0x21                          # ld hl,nnnn
            rom[0x1001:0x1003] = bytes([start & 0xFF, start >> 8])
        game = MiniGame(codec, 0x1000 if far else 0x1001, 0x800, far)
        vram = game.vram(bytes(rom))
        # tags as a tracing engine would leave them for unpacked data: the last stream byte read
        tags = [0] * 0x4000
        for i in range(len(raw)):
            tags[0x800 + i] = tag(pv.RT_DERIVED, start + min(len(stream) - 1, 1 + i * len(stream) // len(raw)))
        scene = make_scene({'vram': (vram, tags)})
        return bytes(rom), scene, game, raw, stream, start

    def test_block_is_recognised_from_tags_alone(self):
        for codec in ('lz3', 'hal', 'lz2', 'rle-konami'):
            rom, scene, game, raw, stream, start = self.build(codec)
            block = gt.find_compressed_block(scene, rom, 'gb', 'vram', 0x800 + 5 * 16, 16)
            self.assertIsNotNone(block, codec)
            self.assertEqual((block.start, block.size, block.decoded), (start, len(stream), raw), codec)
            self.assertEqual(block.decoded_index(0x800 + 5 * 16), 5 * 16)

    def test_unknown_data_is_not_matched(self):
        rom, scene, game, raw, stream, start = self.build()
        broken = bytearray(rom)
        broken[start:start + len(stream)] = bytes(random.Random(2).randrange(1, 255) for _ in range(len(stream)))
        self.assertIsNone(gt.find_compressed_block(scene, bytes(broken), 'gb', 'vram', 0x800 + 5 * 16, 16))

    def test_reencode_in_place(self):
        rom, scene, game, raw, stream, start = self.build()
        block = gt.find_compressed_block(scene, rom, 'gb', 'vram', 0x800 + 5 * 16, 16)
        # an edit that makes the data simpler always fits
        changes = {0x800 + 5 * 16 + k: 0 for k in range(16) if raw[5 * 16 + k]}
        plan = gt.plan_block_edit(block, changes, rom, 'gb')
        self.assertEqual(plan.kind, 'reencode')
        self.assertTrue(all(start <= o < start + len(stream) or o in (0x14D, 0x14E, 0x14F) for o, _, _ in plan.writes))
        after = game.vram(plan.apply(rom))
        self.assertEqual(after[0x800 + 5 * 16:0x800 + 6 * 16], bytes(16))
        self.assertEqual(after[0x800:0x800 + 5 * 16], raw[:5 * 16])
        self.assertEqual(after[0x800 + 6 * 16:0x800 + len(raw)], raw[6 * 16:])

    def grow_changes(self, raw):
        rng = random.Random(4)
        return {0x800 + k: rng.randrange(256) ^ raw[k] or 1 for k in range(0, 96)}

    def test_relocate_and_repoint_when_it_no_longer_fits(self):
        rom, scene, game, raw, stream, start = self.build()
        block = gt.find_compressed_block(scene, rom, 'gb', 'vram', 0x800, 16)
        changes = {i: v for i, v in self.grow_changes(raw).items() if v != raw[i - 0x800]}
        with self.assertRaisesRegex(ValueError, 'longer'):
            gt.plan_block_edit(block, changes, rom, 'gb')
        plan = gt.plan_block_edit(block, changes, rom, 'gb', verify=game.verifier(rom, scene))
        self.assertEqual(plan.kind, 'relocate')
        self.assertEqual(plan.details['pointer']['offset'], 0x1001)
        self.assertTrue(0x7000 <= plan.details['new_offset'] < 0x7800)     # same bank as the 16-bit pointer
        edited = plan.apply(rom)
        self.assertEqual(edited[start:start + len(stream)], stream)         # the old block is untouched
        after = game.vram(edited)
        for i, v in changes.items():
            self.assertEqual(after[i], v)

    def test_far_pointer_can_move_to_another_bank(self):
        rom, scene, game, raw, stream, start = self.build(far=True)
        full = bytearray(rom); full[0x7000:0x7800] = b'\x55' * 0x800       # no room left in bank 1
        rom = bytes(full)
        block = gt.find_compressed_block(scene, rom, 'gb', 'vram', 0x800, 16)
        changes = {i: v for i, v in self.grow_changes(raw).items() if v != raw[i - 0x800]}
        plan = gt.plan_block_edit(block, changes, rom, 'gb', verify=game.verifier(rom, scene))
        self.assertEqual(plan.details['pointer']['encoding'], 'gb-far-pre')
        self.assertEqual(plan.details['new_offset'] >> 14, 3)
        after = game.vram(plan.apply(rom))
        for i, v in changes.items():
            self.assertEqual(after[i], v)

    def test_no_room_and_no_pointer_are_reported(self):
        rom, scene, game, raw, stream, start = self.build(room=False)
        block = gt.find_compressed_block(scene, rom, 'gb', 'vram', 0x800, 16)
        changes = {i: v for i, v in self.grow_changes(raw).items() if v != raw[i - 0x800]}
        with self.assertRaisesRegex(ValueError, 'no pointer'):
            gt.plan_block_edit(block, changes, rom, 'gb', verify=game.verifier(rom, scene))

    def test_private_copy_leaves_the_original_bytes(self):
        rom, scene, game, raw, stream, start = self.build()
        tile = gt.tile_at(scene, 'gb', 0x800 + 3 * 16)
        self.assertEqual(tile.status, 'derived')
        new = bytes(b ^ 0xFF for b in tile.stored)
        plan = gt.plan_private_copy(tile, new, rom, scene, verify=game.verifier(rom, scene))
        self.assertEqual(plan.kind, 'private-copy')
        edited = plan.apply(rom)
        self.assertEqual(edited[start:start + len(stream)], stream)
        self.assertEqual(game.vram(edited)[0x800 + 48:0x800 + 64], new)
        self.assertTrue(plan.verified['as_planned'])
        # a second user that still points at the old block is unaffected
        other = MiniGame('lz3', 0x1001, 0x800)
        untouched = bytearray(edited); untouched[0x1001:0x1003] = rom[0x1001:0x1003]
        self.assertEqual(other.vram(bytes(untouched)), game.vram(rom))

    def test_derived_edit_prefers_the_codec_path(self):
        rom, scene, game, raw, stream, start = self.build()
        tile = gt.tile_at(scene, 'gb', 0x800 + 5 * 16)
        plan = gt.plan_derived_tile_edit(tile, [0] * 64, rom, scene, verify=game.verifier(rom, scene))
        self.assertIn(plan.kind, ('reencode', 'relocate'))
        self.assertTrue(plan.verified['as_planned'])


class BlockSearchTests(unittest.TestCase):
    def test_second_of_two_back_to_back_streams_is_found(self):
        rng = random.Random(21)
        first = bytes(rng.randrange(256) for _ in range(64)) * 3
        second = bytes(rng.randrange(256) for _ in range(40)) * 4
        s1, s2 = gfx_codecs.encode('hal', first), gfx_codecs.encode('hal', second)
        rom = gb_rom(0x10000, 0x55)
        rom[0x5000:0x5000 + len(s1) + len(s2)] = s1 + s2
        vram = bytearray(0x4000); tags = [0] * 0x4000
        vram[0x400:0x400 + len(first) + len(second)] = first + second
        for i in range(len(first)):
            tags[0x400 + i] = tag(pv.RT_DERIVED, 0x5000 + 1 + i * (len(s1) - 2) // len(first))
        for i in range(len(second)):
            tags[0x400 + len(first) + i] = tag(pv.RT_DERIVED, 0x5000 + len(s1) + 1 + i * (len(s2) - 2) // len(second))
        scene = make_scene({'vram': (bytes(vram), tags)})
        at = 0x400 + len(first) + 32
        block = gt.find_compressed_block(scene, bytes(rom), 'gb', 'vram', at, 16)
        self.assertEqual((block.start, block.size, block.decoded), (0x5000 + len(s1), len(s2), second))
        self.assertEqual(block.decoded_index(at), 32)

    def test_snes_three_bit_tiles_map_back_into_the_block(self):
        rng = random.Random(22)
        raw = bytes(rng.randrange(256) for _ in range(24 * 12))
        stream = gfx_codecs.encode('lz2', raw)
        rom = bytearray(b'\x55' * 0x10000)
        rom[0x3000:0x3000 + len(stream)] = stream
        expanded = gt.TRANSFORMS['3bpp'][0](raw)
        self.assertEqual(len(expanded), 32 * 12)
        vram = bytearray(0x10000); tags = [0] * 0x10000
        vram[0x2000:0x2000 + len(expanded)] = expanded
        for i in range(len(expanded)):
            tags[0x2000 + i] = tag(pv.RT_DERIVED, 0x3000 + 1 + i * (len(stream) - 2) // len(expanded))
        scene = make_scene({'vram': (bytes(vram), tags)})
        block = gt.find_compressed_block(scene, bytes(rom), 'snes', 'vram', 0x2000 + 5 * 32, 32)
        self.assertEqual((block.codec, block.transform, block.start), ('lz2', '3bpp', 0x3000))
        self.assertEqual(block.decoded_index(0x2000 + 5 * 32 + 3), 5 * 24 + 3)
        self.assertEqual(block.decoded_index(0x2000 + 5 * 32 + 18), 5 * 24 + 17)
        with self.assertRaisesRegex(ValueError, '8 colors'):
            block.decoded_index(0x2000 + 5 * 32 + 17)
        plan = gt.plan_block_edit(block, {0x2000 + 5 * 32 + k: 0 for k in range(16)}, bytes(rom), 'snes', force_relocate=False)
        out, _ = gfx_codecs.decode('lz2', plan.apply(bytes(rom)), 0x3000)
        self.assertEqual(out[5 * 24:5 * 24 + 16], bytes(16))
        self.assertEqual(out[5 * 24 + 16:], raw[5 * 24 + 16:])

    def test_snes_three_bit_tile_read_straight_from_rom_counts_as_rom(self):
        vram = bytearray(0x10000); tags = [0] * 0x10000
        rom = bytes(range(256)) * 0x100
        src = 0x4010
        tile = bytearray(rom[src:src + 16])
        for k in range(8):
            tile += bytes((rom[src + 16 + k], 0))
        vram[0x100:0x120] = tile
        for k in range(16):
            tags[0x100 + k] = tag(pv.RT_ROM, src + k)
        for k in range(8):
            tags[0x110 + 2 * k] = tag(pv.RT_ROM, src + 16 + k)
            tags[0x111 + 2 * k] = tag(pv.RT_DERIVED, src + 16 + k)
        scene = make_scene({'vram': (bytes(vram), tags)})
        t = gt.tile_at(scene, 'snes', 0x100)
        self.assertEqual((t.status, t.layout), ('rom', 'plain'))
        self.assertTrue(any('8 colors' in n for n in t.notes))
        px = list(t.pixels); px[0] ^= 1
        self.assertEqual(len(gt.plan_tile_edit(t, px, rom)), 1)
        px[0] |= 8
        with self.assertRaises(ValueError):
            gt.plan_tile_edit(t, px, rom)


class M68k:
    """Just enough 68000 and VDP to run the Mega Drive overlay routine."""

    def __init__(self, rom, vram):
        self.rom, self.vram = rom, vram
        self.d = [0x11111111, 0x22222222, 0x33333333]
        self.a = [0x00FF0000 + 0x100 * n for n in range(7)]
        self.stack = []
        self.z = self.n = 0
        self.vdp_address, self.vdp_step, self.vdp_accesses = 0, 2, 0

    def w(self, at):
        return self.rom[at] << 8 | self.rom[at + 1]

    def l(self, at):
        return int.from_bytes(self.rom[at:at + 4], 'big')

    def control(self, value, size):
        self.vdp_accesses += 1
        if size == 2:
            assert value & 0xE000 == 0x8000, 'only register writes are sent as single words'
            if value >> 8 & 0x1F == 15:
                self.vdp_step = value & 0xFF
        else:
            self.vdp_address = (value >> 16 & 0x3FFF) | (value & 3) << 14
            self.vdp_write = bool(value & 0x40000000)

    def data_read(self):
        self.vdp_accesses += 1
        assert not self.vdp_write
        v = self.vram[self.vdp_address] << 8 | self.vram[self.vdp_address + 1]
        self.vdp_address = (self.vdp_address + self.vdp_step) & 0xFFFF
        return v

    def data_write(self, v):
        self.vdp_accesses += 1
        assert self.vdp_write
        self.vram[self.vdp_address:self.vdp_address + 2] = bytes((v >> 8, v & 0xFF))
        self.vdp_address = (self.vdp_address + self.vdp_step) & 0xFFFF

    def run(self, pc, stop):
        d, a = self.d, self.a
        s16 = lambda v: v - 0x10000 if v & 0x8000 else v
        s8 = lambda v: v - 0x100 if v & 0x80 else v
        for _ in range(100000):
            if pc == stop:
                return pc
            op = self.w(pc)
            if op == 0x48E7:
                assert self.w(pc + 2) == 0xE0E0
                self.stack.append(('regs', list(d), a[:3])); pc += 4
            elif op == 0x4CDF:
                assert self.w(pc + 2) == 0x0707
                kind, dd, aa = self.stack.pop(); assert kind == 'regs'
                d[:] = dd; a[:3] = aa; pc += 4
            elif op & 0xFFF8 == 0x2008: d[0] = a[op & 7]; pc += 2
            elif op >> 8 == 0x61: self.stack.append(('ret', pc + 2)); pc = pc + 2 + s8(op & 0xFF)
            elif op == 0x4E75:
                kind, pc = self.stack.pop(); assert kind == 'ret'
            elif op >> 8 in (0x67, 0x66, 0x6B, 0x60):
                take = {0x67: self.z, 0x66: not self.z, 0x6B: self.n, 0x60: True}[op >> 8]
                pc = pc + 2 + s8(op & 0xFF) if take else pc + 2
            elif op == 0x4EF9: pc = self.l(pc + 2)
            elif op == 0x0280: d[0] &= self.l(pc + 2); pc += 6
            elif op == 0x0C80: self.z = int(d[0] == self.l(pc + 2)); pc += 6
            elif op == 0x41FA: a[0] = pc + 2 + s16(self.w(pc + 2)); pc += 4
            elif op == 0x43F9: a[1] = self.l(pc + 2); pc += 6
            elif op == 0x2018:
                d[0] = self.l(a[0]); a[0] += 4; self.z, self.n = int(d[0] == 0), d[0] >> 31; pc += 2
            elif op == 0x2340:
                assert a[1] + s16(self.w(pc + 2)) == 0xC00004; self.control(d[0], 4); pc += 4
            elif op == 0x3211:
                assert a[1] == 0xC00000; d[1] = d[1] & 0xFFFF0000 | self.data_read(); pc += 2
            elif op in (0xB258, 0xB25A):
                r = 0 if op == 0xB258 else 2
                self.z = int(self.w(a[r]) == d[1] & 0xFFFF); a[r] += 2; pc += 2
            elif op == 0x337C:
                assert a[1] + s16(self.w(pc + 4)) == 0xC00004; self.control(self.w(pc + 2), 2); pc += 6
            elif op == 0x2350:
                assert a[1] + s16(self.w(pc + 2)) == 0xC00004; self.control(self.l(a[0]), 4); pc += 4
            elif op == 0x45E8: a[2] = a[0] + s16(self.w(pc + 2)); pc += 4
            elif op == 0x41E8: a[0] = a[0] + s16(self.w(pc + 2)); pc += 4
            elif op == 0x740F: d[2] = 15; pc += 2
            elif op in (0x56CA, 0x51CA):
                if op == 0x56CA and not self.z:
                    pc += 4
                else:
                    low = (d[2] - 1) & 0xFFFF
                    d[2] = d[2] & 0xFFFF0000 | low
                    pc = pc + 2 + s16(self.w(pc + 2)) if low != 0xFFFF else pc + 4
            elif op == 0x2368:
                assert a[1] + s16(self.w(pc + 4)) == 0xC00004
                self.control(self.l(a[0] + s16(self.w(pc + 2))), 4); pc += 6
            elif op == 0x329A:
                assert a[1] == 0xC00000; self.data_write(self.w(a[2])); a[2] += 2; pc += 2
            else:
                raise AssertionError(f'opcode {op:04X} at {pc:06X}')
        raise AssertionError('runaway')


class W65816:
    """Just enough 65816 and SNES video port to run the Super NES overlay routine (native mode)."""

    def __init__(self, rom, vram, bank_of):
        self.rom, self.vram, self.bank_of = rom, vram, bank_of   # bank_of(address24) -> file offset
        self.a, self.x, self.y = 0x1234, 0x78, 0xBC   # with 8-bit index registers their high bytes are zero
        self.m = self.xf = 1          # 8-bit accumulator and index at entry, as a game may have them
        self.db = 0x7E
        self.c = self.z = 0
        self.stack = []
        self.vmain, self.vmadd, self.buffer, self.ppu_accesses = 0, 0, 0, 0

    def rd(self, addr24):
        return self.rom[self.bank_of(addr24)]

    def ppu_write(self, reg, v):
        self.ppu_accesses += 1
        if reg == 0x2115: self.vmain = v
        elif reg in (0x2116, 0x2117):
            self.vmadd = self.vmadd & 0xFF00 | v if reg == 0x2116 else self.vmadd & 0x00FF | v << 8
            self.buffer = self.vram[self.vmadd * 2] | self.vram[self.vmadd * 2 + 1] << 8
        elif reg in (0x2118, 0x2119):
            self.vram[self.vmadd * 2 + (reg & 1)] = v
            if (reg == 0x2119) == bool(self.vmain & 0x80):
                self.vmadd = (self.vmadd + 1) & 0x7FFF
        else:
            raise AssertionError(hex(reg))

    def ppu_read(self, reg):
        self.ppu_accesses += 1
        assert reg in (0x2139, 0x213A)
        v = self.buffer >> (8 * (reg & 1) ^ 8 * 0) & 0xFF if reg == 0x2139 else self.buffer >> 8
        v &= 0xFF
        if (reg == 0x213A) == bool(self.vmain & 0x80):
            self.buffer = self.vram[self.vmadd * 2] | self.vram[self.vmadd * 2 + 1] << 8
            self.vmadd = (self.vmadd + 1) & 0x7FFF
        return v

    def run(self, pc24, stop24):
        bank = pc24 >> 16
        pc = pc24 & 0xFFFF
        byte = lambda o: self.rd(bank << 16 | (pc + o) & 0xFFFF)
        word = lambda o: byte(o) | byte(o + 1) << 8
        for _ in range(200000):
            if (bank << 16 | pc) == stop24:
                return stop24
            op = byte(0)
            wide = not self.m
            if op == 0x08: self.stack.append(('p', (self.m, self.xf, self.c, self.z))); pc += 1
            elif op == 0x28:
                kind, v = self.stack.pop(); assert kind == 'p'
                self.m, self.xf, self.c, self.z = v
                if self.xf: self.x &= 0xFF; self.y &= 0xFF
                pc += 1
            elif op == 0xC2:
                if byte(1) & 0x20: self.m = 0
                if byte(1) & 0x10: self.xf = 0
                pc += 2
            elif op == 0xE2:
                if byte(1) & 0x20: self.m = 1
                assert not byte(1) & 0x10
                pc += 2
            elif op == 0x48: assert wide; self.stack.append(('a', self.a)); pc += 1
            elif op == 0x68: kind, self.a = self.stack.pop(); assert kind == 'a' and wide; pc += 1
            elif op == 0xDA: assert not self.xf; self.stack.append(('x', self.x)); pc += 1
            elif op == 0xFA: kind, self.x = self.stack.pop(); assert kind == 'x'; pc += 1
            elif op == 0x5A: self.stack.append(('y', self.y)); pc += 1
            elif op == 0x7A: kind, self.y = self.stack.pop(); assert kind == 'y'; pc += 1
            elif op == 0x8B: self.stack.append(('b', self.db)); pc += 1
            elif op == 0x4B: self.stack.append(('b', bank)); pc += 1
            elif op == 0xAB: kind, self.db = self.stack.pop(); assert kind == 'b'; pc += 1
            elif op == 0xF4: self.stack.append(('pc', word(1))); pc += 3
            elif op == 0xA9:
                if wide: self.a = word(1); pc += 3
                else: self.a = self.a & 0xFF00 | byte(1); pc += 2
            elif op == 0xA2: assert not self.xf; self.x = word(1); pc += 3
            elif op == 0x8F:
                addr = word(1); assert byte(3) == 0
                self.ppu_write(addr, self.a & 0xFF)
                if wide: self.ppu_write(addr + 1, self.a >> 8)
                pc += 4
            elif op == 0xAF:
                addr = word(1); assert byte(3) == 0 and wide
                self.a = self.ppu_read(addr) | self.ppu_read(addr + 1) << 8
                pc += 4
            elif op in (0xBD, 0xDD):
                assert wide
                at = self.db << 16 | (word(1) + self.x) & 0xFFFF
                v = self.rd(at) | self.rd(at + 1) << 8
                if op == 0xBD: self.a = v
                else: self.z, self.c = int(self.a == v), int(self.a >= v)
                pc += 3
            elif op == 0xC9: assert wide; self.z, self.c = int(self.a == word(1)), int(self.a >= word(1)); pc += 3
            elif op in (0xF0, 0xD0, 0x80):
                rel = byte(1) - 256 if byte(1) & 0x80 else byte(1)
                take = {0xF0: self.z, 0xD0: not self.z, 0x80: True}[op]
                pc = (pc + 2 + rel) & 0xFFFF if take else pc + 2
            elif op == 0xA8: self.y = self.a; self.z = int(self.y == 0); pc += 1
            elif op == 0xAA: self.x = self.a; pc += 1
            elif op == 0x8A: self.a = self.x; pc += 1
            elif op == 0xE8: self.x = (self.x + 1) & 0xFFFF; pc += 1
            elif op == 0x88: self.y = (self.y - 1) & 0xFFFF; self.z = int(self.y == 0); pc += 1
            elif op == 0x0A: self.c = self.a >> 15; self.a = self.a << 1 & 0xFFFF; pc += 1
            elif op == 0x18: self.c = 0; pc += 1
            elif op in (0x63, 0x69):
                if op == 0x63:
                    assert byte(1) == 1
                    v = self.stack[-1][1]; pc += 2
                else:
                    v = word(1); pc += 3
                total = self.a + v + self.c
                self.c, self.a = total >> 16, total & 0xFFFF
            elif op == 0x5C:
                target = word(1) | byte(3) << 16
                bank, pc = target >> 16, target & 0xFFFF
            elif op == 0x40:
                kind, v = self.stack.pop(); assert kind == 'p'
                self.m, self.xf, self.c, self.z = v
                kind, pc = self.stack.pop(); assert kind == 'pc'
                kind, bank = self.stack.pop(); assert kind == 'b'
            else:
                raise AssertionError(f'opcode {op:02X} at {bank:02X}:{pc:04X}')
        raise AssertionError('runaway')


class OtherProcessorOverlayTests(unittest.TestCase):
    def test_genesis_routine_runs_on_a_model_processor(self):
        rom = bytearray(b'\x55' * 0x2000)
        rom[0x78:0x7C] = (0x000200).to_bytes(4, 'big')
        rom[0x1000:0x1300] = b'\xFF' * 0x300
        vram = bytearray(random.Random(6).randrange(1, 255) for _ in range(0x10000))
        scene = make_scene({'vram': (bytes(vram), [tag(pv.RT_DERIVED, 0x900)] * 0x10000)})
        t1 = gt.tile_at(scene, 'genesis', 0x8440)
        t2 = gt.tile_at(scene, 'genesis', 0x0020)
        new1, new2 = [15 - p for p in t1.pixels], [(p + 3) & 15 for p in t2.pixels]
        for guard in (True, False):
            plan = gt.plan_overlay_patch([(t1, new1), (t2, new2)], bytes(rom), 'genesis', guard=guard)
            out = plan.apply(bytes(rom))
            entry = int.from_bytes(out[0x78:0x7C], 'big')
            expected = bytearray(vram)
            expected[0x8440:0x8460] = gt.encode_tile(new1, 'genesis-4bpp')
            expected[0x0020:0x0040] = gt.encode_tile(new2, 'genesis-4bpp')
            work = bytearray(vram)
            for frame in range(2):                       # second frame: already applied, nothing changes
                cpu = M68k(out, work)
                before = (list(cpu.d), list(cpu.a))
                self.assertEqual(cpu.run(entry, 0x200), 0x200)
                self.assertEqual((cpu.d, cpu.a), before)
                self.assertEqual(cpu.stack, [])
                self.assertEqual(work, expected, (guard, frame))
            # another picture in the slot is left alone, even one that differs in a single late byte
            other = bytearray(vram); other[0x845F] ^= 1; other[0x0021] ^= 0x80
            keep = bytes(other)
            M68k(out, other).run(entry, 0x200)
            self.assertEqual(bytes(other), keep)
            # the interrupted program holds the VDP port in a register: the guarded routine stays off the VDP
            cpu = M68k(out, bytearray(vram))
            cpu.a[5] = 0xFFC00004
            cpu.run(entry, 0x200)
            self.assertEqual(cpu.vdp_accesses == 0, guard)
            self.assertEqual(bytes(cpu.vram) == bytes(vram), guard)

    def test_snes_routine_runs_on_a_model_processor(self):
        rom = bytearray(b'\x55' * 0x40000)                 # LoROM
        rom[0x7FC0:0x7FD5] = b'TEST GAME            '
        rom[0x7FD5] = 0x20
        rom[0x7FE0:0x7FE4] = b'\xFF' * 4
        rom[0x7FEA:0x7FEC] = b'\x34\x92'                    # NMI handler at $00:9234
        rom[0x9234 - 0x8000] = 0x40                         # the game's handler: rti
        rom[0x18000:0x18400] = b'\xFF' * 0x400
        vram = bytearray(random.Random(8).randrange(1, 255) for _ in range(0x10000))
        scene = make_scene({'vram': (bytes(vram), [tag(pv.RT_DERIVED, 0x9000)] * 0x10000)})
        t1 = gt.tile_at(scene, 'snes', 0x4000)
        t2 = gt.tile_at(scene, 'snes', 0xC020, fmt='snes-2bpp')
        new1, new2 = [15 - p for p in t1.pixels], [3 - p for p in t2.pixels]
        lorom = lambda addr: (addr >> 16 & 0x7F) << 15 | addr & 0x7FFF
        for after in (False, True):
            plan = gt.plan_overlay_patch([(t1, new1), (t2, new2)], bytes(rom), 'snes', after_handler=after)
            out = plan.apply(bytes(rom))
            expected = bytearray(vram)
            expected[0x4000:0x4020] = gt.encode_tile(new1, 'snes-4bpp')
            expected[0xC020:0xC030] = gt.encode_tile(new2, 'snes-2bpp')
            work = bytearray(vram)
            for frame in range(2):
                cpu = W65816(out, work, lorom)
                entry = out[0x7FEA] | out[0x7FEB] << 8
                state = (cpu.a, cpu.x, cpu.y, cpu.m, cpu.xf, cpu.db)
                if after:
                    cpu.stack = [('b', 0x05), ('pc', 0xABCD), ('p', (1, 1, 0, 0))]      # the interrupt frame
                    self.assertEqual(cpu.run(entry, 0x05ABCD), 0x05ABCD)                # back in the interrupted program
                else:
                    self.assertEqual(cpu.run(entry, 0x009234), 0x009234)                # reaches the game's handler
                self.assertEqual((cpu.a, cpu.x, cpu.y, cpu.m, cpu.xf, cpu.db), state)
                self.assertEqual(cpu.stack, [])
                self.assertEqual(work, expected, (after, frame))
            other = bytearray(vram); other[0x401F] ^= 1; other[0xC021] ^= 0x80
            keep = bytes(other)
            cpu = W65816(out, other, lorom)
            if after:
                cpu.stack = [('b', 0x05), ('pc', 0xABCD), ('p', (1, 1, 0, 0))]
            cpu.run(out[0x7FEA] | out[0x7FEB] << 8, 0x05ABCD if after else 0x009234)
            self.assertEqual(bytes(other), keep)

    def test_snes_overlay_hooks_the_native_nmi_vector(self):
        rom = bytearray(b'\x55' * 0x40000)                 # LoROM
        rom[0x7FC0:0x7FD5] = b'TEST GAME            '
        rom[0x7FD5] = 0x20
        rom[0x7FE0:0x7FE4] = b'\xFF' * 4
        rom[0x7FEA:0x7FEC] = b'\x34\x92'                    # NMI handler at $00:9234
        rom[0x18000:0x18400] = b'\xFF' * 0x400
        vram = bytes(random.Random(3).randrange(1, 255) for _ in range(0x10000))
        scene = make_scene({'vram': (vram, [tag(pv.RT_DERIVED, 0x9000)] * 0x10000)})
        t = gt.tile_at(scene, 'snes', 0x4000)
        for after in (False, True):
            plan = gt.plan_overlay_patch([(t, [15 - p for p in t.pixels])], bytes(rom), 'snes', after_handler=after)
            out = plan.apply(bytes(rom))
            self.assertEqual(out[0x7FEA:0x7FEC], b'\xE0\xFF')                # vector -> $00:FFE0
            self.assertEqual(out[0x7FE0], 0x5C)                                # JML
            body = plan.details['routine_offset']
            self.assertTrue(0x18000 <= body < 0x18400)
            self.assertEqual(out[0x7FE1:0x7FE4], bytes((body & 0xFF, 0x80 | (body >> 8 & 0x7F), 0x80 | body >> 15)))
            code = out[body:body + plan.details['routine_size']]
            self.assertIn(b'\x5C\x34\x92\x00', code)                           # reaches the game's handler
            self.assertEqual(code[-2:], b'\xFF\xFF')
            self.assertIn(t.stored + gt.encode_tile([15 - p for p in t.pixels], 'snes-4bpp'), code)
            self.assertEqual(code[0], 0x4B if after else 0x08)
            self.assertEqual(sorted(plan.expect['vram']), list(range(0x4000, 0x4020)))
        dead = bytearray(rom); dead[0x7FEA:0x7FEC] = b'\xFF\xFF'
        with self.assertRaisesRegex(ValueError, 'no vertical-blank'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(dead), 'snes')

    def test_genesis_overlay_hooks_level_six_and_can_grow_the_rom(self):
        rom = bytearray(b'\x55' * 0x2000)
        rom[0x78:0x7C] = (0x000200).to_bytes(4, 'big')
        rom[0x1A4:0x1A8] = (0x1FFF).to_bytes(4, 'big')
        vram = bytes(random.Random(4).randrange(1, 255) for _ in range(0x10000))
        scene = make_scene({'vram': (vram, [tag(pv.RT_DERIVED, 0x900)] * 0x10000)})
        t = gt.tile_at(scene, 'genesis', 0x8440)
        plan = gt.plan_overlay_patch([(t, [15 - p for p in t.pixels])], bytes(rom), 'genesis')
        out = plan.apply(bytes(rom))
        self.assertEqual(plan.details['placement'], 'added-rom')
        self.assertEqual(int.from_bytes(out[0x78:0x7C], 'big'), 0x2000)
        self.assertEqual(int.from_bytes(out[0x1A4:0x1A8], 'big'), len(out) - 1)
        code = out[0x2000:]
        self.assertEqual(code[:4], bytes.fromhex('48E7E0E0'))
        self.assertIn(bytes.fromhex('4EF900000200'), code)                    # jmp to the game's handler
        # the record: read command for the first changed word, that word, read and write commands for the tile
        read = (0x0440 << 16 | 2).to_bytes(4, 'big')
        self.assertIn(read + t.stored[:2] + read + (0x40000000 | 0x0440 << 16 | 2).to_bytes(4, 'big') + t.stored, code)
        # guard: seven register checks, then the bail-out and the compare helper, then the work
        self.assertEqual(code[4:10], bytes((0x20, 0x08, 0x61, 58 - 8, 0x67, 48 - 10)))
        self.assertEqual(code[46:48], bytes((0x60, 24)))                       # bra.s over them
        self.assertEqual(code[48:58], bytes.fromhex('4CDF07074EF900000200'))    # bail: restore, jmp handler
        self.assertEqual(code[58:72], bytes.fromhex('028000FFFFF80C8000C000004E75'))
        self.assertEqual(code[72:74], bytes.fromhex('41FA'))                   # lea table(pc),a0
        table = 74 + int.from_bytes(code[74:76], 'big')
        self.assertEqual(code[table:table + 4], read)
        plain = gt.plan_overlay_patch([(t, [15 - p for p in t.pixels])], bytes(rom), 'genesis', guard=False).apply(bytes(rom))[0x2000:]
        table = 4 + 2 + int.from_bytes(plain[6:8], 'big')
        self.assertEqual(plain[table:table + 4], read)
        self.assertEqual(len(code) - len(plain), 68)
        roomy = bytearray(rom); roomy[0x1000:0x1200] = b'\xFF' * 0x200
        plan = gt.plan_overlay_patch([(t, [15 - p for p in t.pixels])], bytes(roomy), 'genesis')
        self.assertEqual((plan.details['placement'], plan.rom_size), ('free-rom', 0x2000))


class ChecksumAndSpaceTests(unittest.TestCase):
    def test_far_pointer_held_in_code_moves_address_and_bank(self):
        rom = gb_rom(0x10000, 0x55)
        rom[0x2000:0x2008] = b'\x3E\x01\xEA\x00\x20\x21\x34\x52'   # ld a,1 ; ld [$2000],a ; ld hl,$5234
        rom[0xC000:0xC400] = b'\xFF' * 0x400                         # room in bank 3 only
        cands = gt.pointer_candidates(bytes(rom), 'gb', 0x5234)
        code = next(c for c in cands if c['encoding'] == 'gb-far-code')
        self.assertEqual((code['offset'], code['bank_at']), (0x2006, 0x2001))
        plan = gt.plan_relocation(bytes(rom), 'gb', 0x5234, 0x5244, bytes(range(16)), code)
        out = plan.apply(bytes(rom))
        dest = plan.details['new_offset']
        self.assertEqual(dest >> 14, 3)
        self.assertEqual(out[dest:dest + 16], bytes(range(16)))
        self.assertEqual(out[0x2001], 3)
        self.assertEqual(out[0x2006] | out[0x2007] << 8, 0x4000 + (dest & 0x3FFF))
        self.assertEqual(out[0x5234:0x5244], bytes(rom[0x5234:0x5244]))

    def test_with_checksums_adds_the_header_writes(self):
        rom = gb_rom()
        x = 0
        for i in range(0x134, 0x14D):
            x = (x - rom[i] - 1) & 0xFF
        rom[0x14D] = x
        total = (sum(rom) - rom[0x14E] - rom[0x14F]) & 0xFFFF
        rom[0x14E], rom[0x14F] = total >> 8, total & 0xFF
        writes = gt.with_checksums(bytes(rom), [(0x4000, 0x55, 0x56)], 'gb')
        self.assertEqual([w[0] for w in writes], [0x14F, 0x4000])
        self.assertEqual(writes[0][2], (total + 1) & 0xFF)

    def test_gb_checksums_follow_an_edit_only_when_they_were_valid(self):
        rom = gb_rom()
        fixed = bytearray(gt.fix_checksums(bytes(rom), bytes(rom), 'gb'))
        self.assertEqual(fixed, rom)                 # invalid before: left alone
        x = 0
        for i in range(0x134, 0x14D):
            x = (x - rom[i] - 1) & 0xFF
        rom[0x14D] = x
        total = (sum(rom) - rom[0x14E] - rom[0x14F]) & 0xFFFF
        rom[0x14E], rom[0x14F] = total >> 8, total & 0xFF
        edited = bytearray(rom); edited[0x4000] ^= 0x0F; edited[0x140] ^= 1
        out = gt.fix_checksums(bytes(edited), bytes(rom), 'gb')
        x = 0
        for i in range(0x134, 0x14D):
            x = (x - out[i] - 1) & 0xFF
        self.assertEqual(out[0x14D], x)
        self.assertEqual(out[0x14E] << 8 | out[0x14F], (sum(out) - out[0x14E] - out[0x14F]) & 0xFFFF)

    def test_genesis_checksum_and_growth(self):
        rom = bytearray(0x400)
        rom[0x200:0x400] = bytes(range(256)) * 2
        total = sum(rom[i] << 8 | rom[i + 1] for i in range(0x200, 0x400, 2)) & 0xFFFF
        rom[0x18E], rom[0x18F] = total >> 8, total & 0xFF
        rom[0x1A4:0x1A8] = (0x3FF).to_bytes(4, 'big')
        grown = bytes(rom) + b'\x12\x34'
        out = gt.fix_checksums(grown, bytes(rom), 'genesis')
        self.assertEqual(out[0x18E] << 8 | out[0x18F], (total + 0x1234) & 0xFFFF)
        self.assertEqual(int.from_bytes(out[0x1A4:0x1A8], 'big'), 0x401)

    def test_free_space_rules(self):
        rom = gb_rom(0x10000, 0x55)
        self.assertIsNone(gt.find_free_space(bytes(rom), 'gb', 32, near=0x5000))
        rom[0x6000:0x6100] = bytes(0x100)             # zeros in the middle of a bank: may be blank tiles
        self.assertIsNone(gt.find_free_space(bytes(rom), 'gb', 32, near=0x5000))
        rom[0x7F00:0x8000] = bytes(0x100)             # zeros that reach the end of the bank: padding
        self.assertEqual(gt.find_free_space(bytes(rom), 'gb', 32, near=0x5000), 0x7F04)
        rom[0x4800:0x4900] = b'\xFF' * 0x100
        self.assertEqual(gt.find_free_space(bytes(rom), 'gb', 32, near=0x5000), 0x4804)
        self.assertIsNone(gt.find_free_space(bytes(rom), 'gb', 32, near=0x5000, avoid=[(0x4800, 0x4900), (0x7F00, 0x8000)]))
        # a run never crosses a bank boundary
        rom2 = gb_rom(0x10000, 0x55)
        rom2[0x7FF0:0x8010] = b'\xFF' * 0x20
        self.assertIsNone(gt.find_free_space(bytes(rom2), 'gb', 20, same_bank=False))

    def test_pointer_candidates_rank_instruction_operands_first(self):
        rom = gb_rom(0x10000, 0x55)
        rom[0x9000:0x9002] = b'\x34\x52'              # bare bytes that look like the address
        rom[0x2000:0x2003] = b'\x21\x34\x52'          # ld hl,$5234
        rom[0x3000:0x3003] = b'\x34\x52\x01'          # address, bank 1: a far pointer
        cands = gt.pointer_candidates(bytes(rom), 'gb', 0x5234)
        self.assertEqual(cands[0], {'offset': 0x3000, 'size': 3, 'encoding': 'gb-far-post', 'rank': 0})
        self.assertEqual([c['offset'] for c in cands if c['encoding'] == 'le16'][:1], [0x2001])
        self.assertIn(0x9000, [c['offset'] for c in cands])


class Sm83:
    """Just enough of the Game Boy processor to run the overlay routine."""

    def __init__(self, rom, vram):
        self.rom, self.vram = rom, vram            # vram: two 0x2000 banks
        self.io = bytearray(0x100)
        self.stack = []
        self.r = dict(a=0, b=0, c=0, d=0, e=0, h=0, l=0, z=0, cy=0)
        self.steps = 0

    def rd(self, a):
        if a < 0x8000:
            return self.rom[a]
        if a < 0xA000:
            return self.vram[(self.io[0x4F] & 1) * 0x2000 + a - 0x8000]
        if a >= 0xFF00:
            return self.io[a - 0xFF00]
        raise AssertionError(hex(a))

    def wr(self, a, v):
        if 0x8000 <= a < 0xA000:
            self.vram[(self.io[0x4F] & 1) * 0x2000 + a - 0x8000] = v
        elif a >= 0xFF00:
            self.io[a - 0xFF00] = v
        else:
            raise AssertionError('write to ' + hex(a))

    def run(self, pc, stop):
        r = self.r
        pairs = {'af': ('a', 'f'), 'bc': ('b', 'c'), 'de': ('d', 'e'), 'hl': ('h', 'l')}

        def hl(): return r['h'] << 8 | r['l']
        def de(): return r['d'] << 8 | r['e']
        def set_hl(v): r['h'], r['l'] = v >> 8 & 0xFF, v & 0xFF
        def cp(v): r['z'], r['cy'] = int(r['a'] == v), int(r['a'] < v)

        while pc != stop:
            self.steps += 1
            assert self.steps < 100000, 'runaway'
            op = self.rom[pc]; n = self.rom[pc + 1]; nn = n | self.rom[pc + 2] << 8
            rel = pc + 2 + (n - 256 if n & 0x80 else n)
            if op in (0xF5, 0xC5, 0xD5, 0xE5):
                name = {0xF5: 'af', 0xC5: 'bc', 0xD5: 'de', 0xE5: 'hl'}[op]
                self.stack.append((name, (r['a'], r['z'], r['cy']) if name == 'af' else (r[name[0]], r[name[1]]))); pc += 1
            elif op in (0xF1, 0xC1, 0xD1, 0xE1):
                name = {0xF1: 'af', 0xC1: 'bc', 0xD1: 'de', 0xE1: 'hl'}[op]
                pushed, value = self.stack.pop()
                if name == 'af':
                    r['a'], r['z'], r['cy'] = value if pushed == 'af' else (value[0], 0, 0)
                else:
                    assert pushed == name
                    r[name[0]], r[name[1]] = value
                pc += 1
            elif op == 0xF0: r['a'] = self.rd(0xFF00 + n); pc += 2
            elif op == 0xE0: self.wr(0xFF00 + n, r['a']); pc += 2
            elif op == 0x21: set_hl(nn); pc += 3
            elif op == 0x2A: r['a'] = self.rd(hl()); set_hl(hl() + 1); pc += 1
            elif op == 0xFE: cp(n); pc += 2
            elif op == 0x28: pc = rel if r['z'] else pc + 2
            elif op == 0x20: pc = rel if not r['z'] else pc + 2
            elif op == 0x30: pc = rel if not r['cy'] else pc + 2
            elif op == 0x18: pc = rel
            elif op == 0x5F: r['e'] = r['a']; pc += 1
            elif op == 0x57: r['d'] = r['a']; pc += 1
            elif op == 0x1A: r['a'] = self.rd(de()); pc += 1
            elif op == 0xBE: cp(self.rd(hl())); pc += 1
            elif op == 0x23: set_hl(hl() + 1); pc += 1
            elif op == 0x06: r['b'] = n; pc += 2
            elif op == 0x1C: r['e'] = (r['e'] + 1) & 0xFF; r['z'] = int(r['e'] == 0); pc += 1
            elif op == 0x05: r['b'] = (r['b'] - 1) & 0xFF; r['z'] = int(r['b'] == 0); pc += 1
            elif op == 0x7B: r['a'] = r['e']; pc += 1
            elif op == 0x78: r['a'] = r['b']; pc += 1
            elif op == 0xD6: r['cy'] = int(r['a'] < n); r['a'] = (r['a'] - n) & 0xFF; r['z'] = int(r['a'] == 0); pc += 2
            elif op == 0xC6: r['cy'] = int(r['a'] + n > 0xFF); r['a'] = (r['a'] + n) & 0xFF; r['z'] = int(r['a'] == 0); pc += 2
            elif op == 0x12: self.wr(de(), r['a']); pc += 1
            elif op == 0x3E: r['a'] = n; pc += 2
            elif op == 0x85: r['cy'] = int(r['a'] + r['l'] > 0xFF); r['a'] = (r['a'] + r['l']) & 0xFF; r['z'] = int(r['a'] == 0); pc += 1
            elif op == 0x6F: r['l'] = r['a']; pc += 1
            elif op == 0x24: r['h'] = (r['h'] + 1) & 0xFF; r['z'] = int(r['h'] == 0); pc += 1
            elif op == 0xC3: pc = nn
            else:
                raise AssertionError(f'opcode {op:02X} at {pc:04X}')
        return pc


class OverlayTests(unittest.TestCase):
    def setup_game(self, vector=b'\xC3\x00\x02', second_bank=False):
        rom = gb_rom(0x8000, 0x55)
        rom[0x40:0x40 + len(vector)] = vector
        rom[0x3000:0x3400] = b'\xFF' * 0x400        # free space in bank 0
        vram = bytearray(0x4000)
        rng = random.Random(9)
        for i in range(0x1800):
            vram[i] = rng.randrange(256)
        if second_bank:
            for i in range(0x2000, 0x3800):
                vram[i] = rng.randrange(256)
        tags = [tag(pv.RT_DERIVED, 0x4000 + i % 0x1000) for i in range(0x4000)]
        scene = make_scene({'vram': (bytes(vram), tags)})
        return bytes(rom), scene, vram

    def run_interrupt(self, rom, vram, registers=None, stop=0x200):
        cpu = Sm83(rom, vram)
        cpu.r.update(registers or dict(a=0x12, b=0x34, c=0x56, d=0x78, e=0x9A, h=0xBC, l=0xDE, z=1, cy=0))
        before = dict(cpu.r)
        cpu.io[0x4F] = 0xFE
        self.assertEqual(cpu.run(0x40, stop), stop)
        self.assertEqual(cpu.r, before)              # every register and flag restored
        self.assertEqual(cpu.stack, [])
        self.assertEqual(cpu.io[0x4F], 0xFE)         # video bank restored
        return cpu

    def test_overlay_rewrites_exactly_the_edited_tiles(self):
        rom, scene, vram = self.setup_game(second_bank=True)
        t1 = gt.tile_at(scene, 'gbc', 5 * 16)
        t2 = gt.tile_at(scene, 'gbc', 0x2000 + 200 * 16)
        new1 = [3 - p for p in t1.pixels]
        new2 = [(p + 1) & 3 for p in t2.pixels]
        plan = gt.plan_overlay_patch([(t1, new1), (t2, new2)], rom, 'gbc')
        self.assertEqual(plan.kind, 'overlay')
        edited = plan.apply(rom)
        self.assertEqual(edited[0x40], 0xC3)
        work = bytearray(vram)
        self.run_interrupt(edited, work)
        expected = bytearray(vram)
        expected[80:96] = gt.encode_tile(new1, 'gb-2bpp')
        expected[0x2000 + 3200:0x2000 + 3216] = gt.encode_tile(new2, 'gb-2bpp')
        self.assertEqual(work, expected)
        self.assertEqual(plan.expect['vram'], {i: expected[i] for i in range(0x4000) if expected[i] != vram[i]})
        # second frame: already applied, nothing more changes
        self.run_interrupt(edited, work)
        self.assertEqual(work, expected)

    def test_overlay_leaves_other_graphics_in_the_slot_alone(self):
        rom, scene, vram = self.setup_game()
        t = gt.tile_at(scene, 'gb', 7 * 16)
        plan = gt.plan_overlay_patch([(t, [3 - p for p in t.pixels])], rom, 'gb')
        edited = plan.apply(rom)
        for changed_byte in range(16):               # any single differing byte means "not our tile"
            work = bytearray(vram)
            work[7 * 16 + changed_byte] ^= 0x10
            snapshot = bytes(work)
            self.run_interrupt(edited, work)
            self.assertEqual(bytes(work), snapshot, changed_byte)

    def test_displaced_vector_code_still_runs(self):
        # push af ; push hl ; jp $0200  ->  five bytes move into the routine
        rom, scene, vram = self.setup_game(vector=b'\xF5\xE5\xC3\x00\x02')
        t = gt.tile_at(scene, 'gb', 16)
        edited = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'gb').apply(rom)
        cpu = Sm83(edited, bytearray(vram))
        cpu.run(0x40, 0x200)
        self.assertEqual([name for name, _ in cpu.stack], ['af', 'hl'])
        self.assertEqual(bytes(cpu.vram[16:32]), bytes(16))
        # jr at the vector becomes an absolute jump to the same place
        rom, scene, vram = self.setup_game(vector=b'\x18\x1E')      # jr $0060
        edited = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'gb').apply(rom)
        self.run_interrupt(edited, bytearray(vram), stop=0x60)
        # a call followed by other code resumes after the three replaced bytes
        rom, scene, vram = self.setup_game(vector=b'\x3E\x01\xE0\x4F')   # ld a,1 ; ldh [$4F],a
        edited = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'gb').apply(rom)
        cpu = Sm83(edited, bytearray(vram))
        cpu.run(0x40, 0x44)
        self.assertEqual((cpu.r['a'], cpu.io[0x4F]), (1, 1))

    def test_overlay_refusals(self):
        rom, scene, vram = self.setup_game()
        t = gt.tile_at(scene, 'gb', 16)
        full = bytearray(rom); full[0x3000:0x3400] = b'\x55' * 0x400
        with self.assertRaisesRegex(ValueError, 'free bytes'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(full), 'gb')
        unused = bytearray(rom); unused[0x40:0x43] = b'\xFF\xFF\xFF'
        with self.assertRaisesRegex(ValueError, 'no vertical-blank'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(unused), 'gb')
        with self.assertRaisesRegex(ValueError, 'changes nothing'):
            gt.plan_overlay_patch([(t, t.pixels)], rom, 'gb')
        with self.assertRaisesRegex(ValueError, 'not implemented'):
            gt.plan_overlay_patch([(t, [0] * 64)], rom, 'nes')
        self.assertEqual(set(gt.OVERLAY_STATUS), set(gt.CPU.values()))


class VerifyPlanTests(unittest.TestCase):
    def test_apply_writes_checks_old_bytes_and_grows(self):
        rom = bytes(range(16))
        self.assertEqual(gt.apply_writes(rom, [(3, 3, 9)])[3], 9)
        with self.assertRaises(ValueError):
            gt.apply_writes(rom, [(3, 4, 9)])
        out = gt.apply_writes(rom, [(17, None, 7)], 18)
        self.assertEqual((len(out), out[16], out[17]), (18, 0xFF, 7))

    def test_edit_plan_is_json_friendly(self):
        import json
        plan = gt.EditPlan('direct', [(1, 2, 3)], 16, {'vram': {5: 9}})
        plan.verified = {'verified': True, 'as_planned': True, 'changed': {'vram': [5]}}
        json.dumps(plan.to_dict())


if __name__ == '__main__':
    unittest.main()
