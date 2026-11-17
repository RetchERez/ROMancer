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
        self.bank = 1
        self.io = bytearray(0x100)
        self.stack = []
        self.r = dict(a=0, b=0, c=0, d=0, e=0, h=0, l=0, z=0, cy=0)
        self.steps = 0

    def rd(self, a):
        if a < 0x4000:
            return self.rom[a]
        if a < 0x8000:
            return self.rom[self.bank * 0x4000 + a - 0x4000]
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
        elif 0x2000 <= a < 0x4000:
            self.bank = v or 1
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
            op = self.rd(pc); n = self.rd(pc + 1); nn = n | self.rd(pc + 2) << 8
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
            elif op == 0xEA: self.wr(nn, r['a']); pc += 3
            elif op == 0xFA: r['a'] = self.rd(nn); pc += 3
            elif op == 0xCD: self.stack.append(('ret', pc + 3)); pc = nn
            elif op == 0xC9: kind, pc = self.stack.pop(); assert kind == 'ret'
            elif op == 0x67: r['h'] = r['a']; pc += 1
            elif op == 0x11: r['d'], r['e'] = nn >> 8, nn & 0xFF; pc += 3
            elif op == 0x13: v = (de() + 1) & 0xFFFF; r['d'], r['e'] = v >> 8, v & 0xFF; pc += 1
            elif op == 0xBC: cp(r['h']); pc += 1
            elif op == 0xBD: cp(r['l']); pc += 1
            elif op == 0xE6: r['a'] &= n; r['z'], r['cy'] = int(r['a'] == 0), 0; pc += 2
            elif op == 0x3D: r['a'] = (r['a'] - 1) & 0xFF; r['z'] = int(r['a'] == 0); pc += 1
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
        with self.assertRaisesRegex(ValueError, 'iNES'):
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


class Mos6502:
    """Just enough of the NES processor and picture chip to run the overlay routine."""

    def __init__(self, prg, chr_ram):
        self.mem = bytearray(0x10000)
        self.mem[0x10000 - len(prg):] = prg
        self.chr = chr_ram
        self.a = self.x = self.y = 0
        self.z = self.n = self.c = 0
        self.sp = 0xFD
        self.v = self.w = self.high = self.buffer = 0
        self.port_writes = []
        self.steps = 0

    def rd(self, a):
        if a == 0x2002:
            self.w = 0
            return 0x80
        if a == 0x2007:
            out, self.buffer = self.buffer, self.chr[self.v & 0x1FFF]
            self.v = (self.v + 1) & 0x3FFF
            return out
        return self.mem[a]

    def wr(self, a, v):
        if a == 0x2006:
            if self.w:
                self.v = (self.high << 8 | v) & 0x3FFF
            else:
                self.high = v
            self.w ^= 1
        elif a == 0x2007:
            self.chr[self.v & 0x1FFF] = v
            self.v = (self.v + 1) & 0x3FFF
        elif a in (0x2000, 0x2005):
            self.port_writes.append((a, v))
            if a == 0x2005:
                self.w ^= 1
        else:
            assert a < 0x800, hex(a)
            self.mem[a] = v

    def run(self, pc, stop):
        def nz(v):
            self.z, self.n = int(v == 0), v >> 7
            return v

        def push(v):
            self.mem[0x100 + self.sp] = v
            self.sp = (self.sp - 1) & 0xFF

        def pull():
            self.sp = (self.sp + 1) & 0xFF
            return self.mem[0x100 + self.sp]
        while pc != stop:
            self.steps += 1
            assert self.steps < 100000, 'runaway'
            op, n = self.mem[pc], self.mem[pc + 1]
            nn = n | self.mem[pc + 2] << 8
            rel = pc + 2 + (n - 256 if n & 0x80 else n)
            if op == 0x48: push(self.a); pc += 1
            elif op == 0x68: self.a = nz(pull()); pc += 1
            elif op == 0x8A: self.a = nz(self.x); pc += 1
            elif op == 0x98: self.a = nz(self.y); pc += 1
            elif op == 0xA8: self.y = nz(self.a); pc += 1
            elif op == 0xAA: self.x = nz(self.a); pc += 1
            elif op == 0x2C: m = self.rd(nn); self.z, self.n = int(self.a & m == 0), m >> 7; pc += 3
            elif op == 0xA2: self.x = nz(n); pc += 2
            elif op == 0xA0: self.y = nz(n); pc += 2
            elif op == 0xBC: self.y = nz(self.rd(nn + self.x)); pc += 3
            elif op == 0xBD: self.a = nz(self.rd(nn + self.x)); pc += 3
            elif op == 0xAD: self.a = nz(self.rd(nn)); pc += 3
            elif op == 0xA5: self.a = nz(self.rd(n)); pc += 2
            elif op == 0x29: self.a = nz(self.a & n); pc += 2
            elif op == 0xDD: m = self.rd(nn + self.x); nz((self.a - m) & 0xFF); self.c = int(self.a >= m); pc += 3
            elif op == 0x30: pc = rel if self.n else pc + 2
            elif op == 0xD0: pc = rel if not self.z else pc + 2
            elif op == 0xF0: pc = rel if self.z else pc + 2
            elif op == 0x20: push((pc + 2) >> 8); push((pc + 2) & 0xFF); pc = nn
            elif op == 0x60: lo = pull(); pc = (pull() << 8 | lo) + 1
            elif op == 0xE8: self.x = nz((self.x + 1) & 0xFF); pc += 1
            elif op == 0x88: self.y = nz((self.y - 1) & 0xFF); pc += 1
            elif op == 0x8D: self.wr(nn, self.a); pc += 3
            elif op == 0x18: self.c = 0; pc += 1
            elif op == 0x69: t = self.a + n + self.c; self.c = int(t > 0xFF); self.a = nz(t & 0xFF); pc += 2
            elif op == 0x4C: pc = nn
            else:
                raise AssertionError(f'opcode {op:02X} at {pc:04X}')
        return pc


class NesOverlayTests(unittest.TestCase):
    def setup_game(self, free=0x400, mapper=2):
        prg = bytearray(b'\x55' * 0x8000)
        prg[0x7000:0x7000 + free] = b'\xFF' * free                 # free space in the fixed bank ($F000)
        prg[0x4200:0x4214] = bytes.fromhex('A5108D0520A5118D0520' 'A5128D0020' 'A5138D0120')   # scroll, control, mask
        prg[0x7FFA:0x7FFC] = b'\x00\xC1'                           # NMI handler at $C100
        rom = b'NES\x1a' + bytes((2, 0, mapper << 4 & 0xF0, mapper & 0xF0)) + bytes(8) + bytes(prg)
        chr_ram = bytes(random.Random(11).randrange(256) for _ in range(0x2000))
        scene = make_scene({'chr': (chr_ram, [tag(pv.RT_DERIVED, 0x1000)] * 0x2000)})
        return rom, scene, chr_ram

    def run_nmi(self, rom, chr_ram, mask=0x1E):
        cpu = Mos6502(rom[16:], chr_ram)
        cpu.mem[0x10:0x14] = bytes((0x21, 0x43, 0x88, mask))
        cpu.a, cpu.x, cpu.y = 0x12, 0x34, 0x56
        self.assertEqual(cpu.run(cpu.mem[0xFFFA] | cpu.mem[0xFFFB] << 8, 0xC100), 0xC100)
        self.assertEqual((cpu.a, cpu.x, cpu.y, cpu.sp), (0x12, 0x34, 0x56, 0xFD))
        return cpu

    def test_routine_rewrites_exactly_the_edited_tiles(self):
        rom, scene, chr_ram = self.setup_game()
        t1 = gt.tile_at(scene, 'nes', 5 * 16, domain='chr')
        t2 = gt.tile_at(scene, 'nes', 0x1000 + 77 * 16, domain='chr')
        new1, new2 = [3 - p for p in t1.pixels], [(p + 1) & 3 for p in t2.pixels]
        plan = gt.plan_overlay_patch([(t1, new1), (t2, new2)], rom, 'nes')
        self.assertEqual((plan.kind, plan.details['placement'], plan.details['copies']), ('overlay', 'fixed-bank', 1))
        edited = plan.apply(rom)
        hook = edited[16 + 0x7FFA] | edited[16 + 0x7FFB] << 8
        self.assertTrue(0xF000 <= hook < 0xF400)
        work = bytearray(chr_ram)
        cpu = self.run_nmi(edited, work)
        expected = bytearray(chr_ram)
        expected[80:96] = gt.encode_tile(new1, 'nes-2bpp')
        expected[0x1000 + 77 * 16:0x1000 + 78 * 16] = gt.encode_tile(new2, 'nes-2bpp')
        self.assertEqual(work, expected)
        self.assertEqual(plan.expect['chr'], {i: expected[i] for i in range(0x2000) if expected[i] != chr_ram[i]})
        # the scroll is set the way the game's own code sets it, and the address latch ends up clear
        self.assertEqual(cpu.port_writes, [(0x2000, 0x88), (0x2005, 0x21), (0x2005, 0x43)])
        self.assertEqual(cpu.w, 0)
        self.run_nmi(edited, work)                      # second frame: nothing more to do
        self.assertEqual(work, expected)

    def test_other_graphics_and_a_blanked_picture_are_left_alone(self):
        rom, scene, chr_ram = self.setup_game()
        t = gt.tile_at(scene, 'nes', 7 * 16, domain='chr')
        edited = gt.plan_overlay_patch([(t, [3 - p for p in t.pixels])], rom, 'nes').apply(rom)
        for changed_byte in (0, 7, 15):
            work = bytearray(chr_ram)
            work[7 * 16 + changed_byte] ^= 0x10
            snapshot = bytes(work)
            self.run_nmi(edited, work)
            self.assertEqual(bytes(work), snapshot, changed_byte)
        # the game's mask variable says the picture is off: the routine must not touch the address register
        work = bytearray(chr_ram)
        cpu = self.run_nmi(edited, work, mask=0x06)
        self.assertEqual((bytes(work), cpu.v, cpu.port_writes), (chr_ram, 0, []))
        # without the guard it works whatever the variable says
        plain = gt.plan_overlay_patch([(t, [3 - p for p in t.pixels])], rom, 'nes', guard=False)
        self.assertLess(plain.details['routine_size'], gt.plan_overlay_patch([(t, [0] * 64)], rom, 'nes').details['routine_size'])
        work = bytearray(chr_ram)
        self.run_nmi(plain.apply(rom), work, mask=0x06)
        self.assertEqual(bytes(work[112:128]), gt.encode_tile([3 - p for p in t.pixels], 'nes-2bpp'))

    def test_placement_and_refusals(self):
        rom, scene, chr_ram = self.setup_game()
        t = gt.tile_at(scene, 'nes', 16, domain='chr')
        with self.assertRaisesRegex(ValueError, 'free bytes'):
            gt.plan_overlay_patch([(t, [0] * 64)], self.setup_game(free=40)[0], 'nes')
        with self.assertRaisesRegex(ValueError, 'CHR-ROM'):
            gt.plan_overlay_patch([(t, [0] * 64)], rom[:5] + b'\x01' + rom[6:] + bytes(0x2000), 'nes')
        with self.assertRaisesRegex(ValueError, 'iNES'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(0x8000), 'nes')
        # a board that switches all 32 KB needs the routine and the vector in every bank
        both = rom[:4] + b'\x04' + rom[5:6] + b'\x70' + rom[7:16] + rom[16:] * 2
        plan = gt.plan_overlay_patch([(t, [0] * 64)], both, 'nes')
        out = plan.apply(both)
        self.assertEqual((plan.details['placement'], plan.details['copies']), ('every-bank', 2))
        self.assertEqual(out[16 + 0x7FFA:16 + 0x7FFC], out[16 + 0xFFFA:16 + 0xFFFC])
        self.assertEqual(out[16:16 + 0x8000][0x7000:0x7400], out[16 + 0x8000:][0x7000:0x7400])
        hook = gt.plan_hook_only(rom, 'nes')
        self.assertEqual((hook.kind, hook.expect), ('hook-only', {'chr': {}}))
        cpu = Mos6502(hook.apply(rom)[16:], bytearray(chr_ram))
        cpu.run(cpu.mem[0xFFFA] | cpu.mem[0xFFFB] << 8, 0xC100)
        self.assertEqual(cpu.steps, 1)


class Z80:
    """Just enough of the Master System processor, mapper and video chip to run the overlay routine."""

    def __init__(self, rom, vram, line=0xC1):
        self.rom, self.vram, self.line = rom, vram, line
        self.ram = bytearray(0x2000)
        self.page = 2
        self.r = dict(a=0, b=0, c=0, d=0, e=0, h=0, l=0, z=0, cy=0)
        self.stack = []
        self.first = None                 # first byte of a control word, when one is pending
        self.address = self.code = self.buffer = 0
        self.steps = 0

    def rd(self, a):
        if a < 0x8000:
            return self.rom[a]
        if a < 0xC000:
            return self.rom[self.page * 0x4000 + a - 0x8000]
        return self.ram[a & 0x1FFF]

    def wr(self, a, v):
        assert a >= 0xC000, 'write to ' + hex(a)
        self.ram[a & 0x1FFF] = v
        if a == 0xFFFF:
            self.page = v % (len(self.rom) // 0x4000)

    def port_in(self, n):
        if n == 0x7E:
            return self.line
        if n == 0xBF:
            self.first = None
            return 0x80
        assert n == 0xBE and self.code == 0, 'read in write mode'
        out, self.buffer = self.buffer, self.vram[self.address]
        self.address = (self.address + 1) & 0x3FFF
        return out

    def port_out(self, n, v):
        if n == 0xBF:
            if self.first is None:
                self.first = v
            else:
                self.address, self.code, self.first = (v & 0x3F) << 8 | self.first, v >> 6, None
                if self.code == 0:
                    self.buffer = self.vram[self.address]
                    self.address = (self.address + 1) & 0x3FFF
        else:
            assert n == 0xBE and self.code == 1 and self.first is None, 'write in read mode'
            self.vram[self.address] = v
            self.address = (self.address + 1) & 0x3FFF

    def run(self, pc, stop):
        r = self.r

        def hl(): return r['h'] << 8 | r['l']
        def cp(v): r['z'], r['cy'] = int(r['a'] == v), int(r['a'] < v)
        pairs = {0xF5: 'af', 0xC5: 'bc', 0xD5: 'de', 0xE5: 'hl', 0xF1: 'af', 0xC1: 'bc', 0xD1: 'de', 0xE1: 'hl'}
        while pc != stop:
            self.steps += 1
            assert self.steps < 100000, 'runaway'
            op, n = self.rd(pc), self.rd(pc + 1)
            nn = n | self.rd(pc + 2) << 8
            rel = pc + 2 + (n - 256 if n & 0x80 else n)
            if op in (0xF5, 0xC5, 0xD5, 0xE5):
                name = pairs[op]
                self.stack.append((name, (r['a'], r['z'], r['cy']) if name == 'af' else (r[name[0]], r[name[1]]))); pc += 1
            elif op in (0xF1, 0xC1, 0xD1, 0xE1):
                name = pairs[op]
                pushed, value = self.stack.pop()
                assert pushed == name, (pushed, name)
                if name == 'af':
                    r['a'], r['z'], r['cy'] = value
                else:
                    r[name[0]], r[name[1]] = value
                pc += 1
            elif op == 0xDB: r['a'] = self.port_in(n); pc += 2
            elif op == 0xD3: self.port_out(n, r['a']); pc += 2
            elif op == 0xFE: cp(n); pc += 2
            elif op == 0x38: pc = rel if r['cy'] else pc + 2
            elif op == 0x30: pc = rel if not r['cy'] else pc + 2
            elif op == 0x28: pc = rel if r['z'] else pc + 2
            elif op == 0x20: pc = rel if not r['z'] else pc + 2
            elif op == 0x18: pc = rel
            elif op == 0x10: r['b'] = (r['b'] - 1) & 0xFF; pc = rel if r['b'] else pc + 2
            elif op == 0x79: r['a'] = r['c']; pc += 1
            elif op == 0x00: pc += 1
            elif op == 0x07: r['cy'] = r['a'] >> 7; r['a'] = (r['a'] << 1 | r['cy']) & 0xFF; pc += 1
            elif op == 0x21: r['h'], r['l'] = nn >> 8, nn & 0xFF; pc += 3
            elif op == 0x7E: r['a'] = self.rd(hl()); pc += 1
            elif op == 0x57: r['d'] = r['a']; pc += 1
            elif op == 0x23: v = (hl() + 1) & 0xFFFF; r['h'], r['l'] = v >> 8, v & 0xFF; pc += 1
            elif op == 0xBE: cp(self.rd(hl())); pc += 1
            elif op == 0x5E: r['e'] = self.rd(hl()); pc += 1
            elif op == 0x56: r['d'] = self.rd(hl()); pc += 1
            elif op == 0x7B: r['a'] = r['e']; pc += 1
            elif op == 0x7A: r['a'] = r['d']; pc += 1
            elif op == 0x78: r['a'] = r['b']; pc += 1
            elif op == 0x06: r['b'] = n; pc += 2
            elif op == 0x3E: r['a'] = n; pc += 2
            elif op == 0xF6: r['a'] |= n; r['z'], r['cy'] = int(r['a'] == 0), 0; pc += 2
            elif op == 0xC6: r['cy'] = int(r['a'] + n > 0xFF); r['a'] = (r['a'] + n) & 0xFF; r['z'] = int(r['a'] == 0); pc += 2
            elif op == 0x85: r['cy'] = int(r['a'] + r['l'] > 0xFF); r['a'] = (r['a'] + r['l']) & 0xFF; r['z'] = int(r['a'] == 0); pc += 1
            elif op == 0x6F: r['l'] = r['a']; pc += 1
            elif op == 0x24: r['h'] = (r['h'] + 1) & 0xFF; r['z'] = int(r['h'] == 0); pc += 1
            elif op == 0x3A: r['a'] = self.rd(nn); pc += 3
            elif op == 0x32: self.wr(nn, r['a']); pc += 3
            elif op == 0xCD: self.stack.append(('ret', pc + 3)); pc = nn
            elif op == 0xC9: kind, pc = self.stack.pop(); assert kind == 'ret'
            elif op == 0xC3: pc = nn
            else:
                raise AssertionError(f'opcode {op:02X} at {pc:04X}')
        return pc


class SmsOverlayTests(unittest.TestCase):
    REGS = dict(a=0x12, b=0x34, c=0x56, d=0x78, e=0x9A, h=0xBC, l=0xDE, z=1, cy=0)

    def setup_game(self, low_free=0x300, vector=b'\xF5\xDB\xBF\xB7'):
        rom = bytearray(b'\x55' * 0x10000)
        rom[0x38:0x38 + len(vector)] = vector
        rom[0x66:0x68] = b'\xED\x45'
        rom[0x100:0x100 + low_free] = b'\xFF' * low_free          # free space in bank 0
        rom[0xC800:0xCC00] = b'\xFF' * 0x400                      # and in bank 3
        vram = bytes(random.Random(12).randrange(256) for _ in range(0x4000))
        scene = make_scene({'vram': (vram, [tag(pv.RT_DERIVED, 0x9000)] * 0x4000)})
        return bytes(rom), scene, vram

    def run_interrupt(self, rom, vram, stop=0x3B, **over):
        cpu = Z80(rom, vram, over.pop('line', 0xC1))
        cpu.r.update(self.REGS, **over)
        before = dict(cpu.r)
        cpu.wr(0xFFFF, 2)
        self.assertEqual(cpu.run(0x38, stop), stop)
        self.assertEqual({k: v for k, v in cpu.r.items() if k != 'a'}, {k: v for k, v in before.items() if k != 'a'})
        self.assertEqual([name for name, _ in cpu.stack], ['af'])     # the handler's own push af, moved into the routine
        self.assertEqual(cpu.stack[0][1][0], before['a'])
        self.assertEqual((cpu.page, cpu.ram[0x1FFF], cpu.first), (2, 2, None))
        return cpu

    def test_routine_in_bank_0(self):
        rom, scene, vram = self.setup_game()
        t1, t2 = gt.tile_at(scene, 'sms', 5 * 32), gt.tile_at(scene, 'sms', 300 * 32)
        new1, new2 = [15 - p for p in t1.pixels], [(p + 1) & 15 for p in t2.pixels]
        plan = gt.plan_overlay_patch([(t1, new1), (t2, new2)], rom, 'sms')
        self.assertEqual((plan.kind, plan.details['placement']), ('overlay', 'bank0'))
        edited = plan.apply(rom)
        self.assertEqual(edited[0x38], 0xC3)
        work = bytearray(vram)
        self.run_interrupt(edited, work)
        expected = bytearray(vram)
        expected[160:192] = gt.encode_tile(new1, 'sms-4bpp')
        expected[9600:9632] = gt.encode_tile(new2, 'sms-4bpp')
        self.assertEqual(work, expected)
        self.assertEqual(plan.expect['vram'], {i: expected[i] for i in range(0x4000) if expected[i] != vram[i]})
        self.run_interrupt(edited, work)
        self.assertEqual(work, expected)
        for changed_byte in (0, 13, 31):                 # any differing byte means "not our tile"
            other = bytearray(vram)
            other[160 + changed_byte] ^= 0x10
            other[9600 + changed_byte] ^= 0x10
            snapshot = bytes(other)
            self.run_interrupt(edited, other)
            self.assertEqual(bytes(other), snapshot, changed_byte)

    def test_line_interrupts_and_block_transfers_are_left_alone(self):
        rom, scene, vram = self.setup_game()
        t = gt.tile_at(scene, 'sms', 64)
        edited = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'sms').apply(rom)
        for over in ({'line': 0x60}, {'c': 0xBE}):
            work = bytearray(vram)
            cpu = self.run_interrupt(edited, work, **over)
            self.assertEqual((bytes(work), cpu.address), (vram, 0), over)
        unguarded = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'sms', guard=False).apply(rom)
        work = bytearray(vram)
        self.run_interrupt(unguarded, work, c=0xBE)
        self.assertEqual(bytes(work[64:96]), bytes(32))

    def test_paged_routine_and_growth(self):
        rom, scene, vram = self.setup_game(low_free=0x30)
        t = gt.tile_at(scene, 'sms', 64)
        plan = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'sms')
        self.assertEqual(plan.details['placement'], 'paged')
        self.assertEqual(plan.details['routine_offset'] // 0x4000, 3)
        self.assertTrue(0x100 <= plan.details['stub_offset'] < 0x130)
        work = bytearray(vram)
        self.run_interrupt(plan.apply(rom), work)             # run_interrupt checks that page 2 is mapped again
        self.assertEqual(bytes(work[64:96]), bytes(32))
        full = bytearray(rom); full[0xC800:0xCC00] = b'\x55' * 0x400
        plan = gt.plan_overlay_patch([(t, [0] * 64)], bytes(full), 'sms')
        self.assertEqual((plan.details['placement'], plan.rom_size), ('paged-added', 0x20000))
        self.assertLess(len(plan.writes), 400)                 # the FF fill of the new half is not listed
        work = bytearray(vram)
        self.run_interrupt(plan.apply(bytes(full)), work)
        self.assertEqual(bytes(work[64:96]), bytes(32))
        with self.assertRaisesRegex(ValueError, 'free bytes for the overlay routine'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(full), 'sms', grow=False)
        with self.assertRaisesRegex(ValueError, 'stub'):
            gt.plan_overlay_patch([(t, [0] * 64)], self.setup_game(low_free=8)[0], 'sms')

    def test_hook_and_displaced_code(self):
        from romancer import gfx_overlay8 as o8
        rom, scene, vram = self.setup_game(vector=b'\xC3\x00\x02')        # jp $0200: nothing to move, the jump is retargeted
        t = gt.tile_at(scene, 'sms', 64)
        edited = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'sms').apply(rom)
        cpu = Z80(edited, bytearray(vram)); cpu.r.update(self.REGS)
        cpu.run(0x38, 0x200)
        self.assertEqual((cpu.stack, bytes(cpu.vram[64:96])), ([], bytes(32)))
        with self.assertRaisesRegex(ValueError, 'cannot be moved'):
            gt.plan_overlay_patch([(t, [0] * 64)], self.setup_game(vector=b'\x20\x05\x00')[0], 'sms')
        with self.assertRaisesRegex(ValueError, 'no interrupt handler'):
            gt.plan_overlay_patch([(t, [0] * 64)], self.setup_game(vector=b'\xFF\xFF\xFF')[0], 'sms')
        self.assertEqual([o8.z80_length(bytes.fromhex(h), 0) for h in ('F5', 'DBBF', 'C30000', 'ED4D', 'ED430000', '3E01', '21FCFF', 'CB7F', '18FE')],
                         [1, 2, 3, 2, 4, 2, 3, 2, 2])
        self.assertIsNone(o8.z80_length(b'\xDD\xE5', 0))
        self.assertFalse(o8.sms_slot1_is_paged(b'\x3E\x01\x32\xFE\xFF' + bytes(64)))
        self.assertTrue(o8.sms_slot1_is_paged(b'\x78\x32\xFE\xFF' + bytes(64)))
        hook = gt.plan_hook_only(rom, 'sms')
        cpu = Z80(hook.apply(rom), bytearray(vram))
        cpu.run(0x38, 0x200)
        self.assertEqual((hook.kind, cpu.steps), ('hook-only', 2))


class GameBoyAfterHandlerTests(unittest.TestCase):
    def test_work_runs_when_the_games_handler_has_returned(self):
        for banked in (False, True):
            if banked:
                rom, scene, vram = BankProbeTests().setup_game()
                rom = bytearray(rom); rom[0x3000:0x3030] = b'\xFF' * 0x30; rom = bytes(rom)
            else:
                rom, scene, vram = OverlayTests().setup_game()
            rom = bytearray(rom); rom[0x200] = 0xC9; rom = bytes(rom)          # the game's handler: just ret
            t = gt.tile_at(scene, 'gb', 5 * 16)
            plan = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'gb', after_handler=True)
            self.assertEqual(plan.details['timing'], "after the game's handler")
            for mode, applied in ((1, True), (3, False)):                       # only in the vertical blank
                work = bytearray(vram)
                cpu = Sm83(plan.apply(rom), work)
                cpu.bank = 2 if banked else 1
                cpu.io[0x41] = 0x80 | mode
                cpu.stack.append(('ret', 0x1234))
                visited = []
                real_rd = cpu.rd
                cpu.rd = lambda a: (visited.append(a), real_rd(a))[1]
                cpu.run(0x40, 0x1234)
                self.assertEqual((cpu.stack, cpu.bank), ([], 2 if banked else 1), (banked, mode))
                self.assertEqual(bytes(work[80:96]) == bytes(16), applied, (banked, mode))
                first_video = next((n for n, a in enumerate(visited) if 0x8000 <= a < 0xA000), len(visited))
                self.assertLess(visited.index(0x200), first_video)               # the handler ran before any video access


class SmsOtherHookTests(unittest.TestCase):
    def setup_game(self):
        rom = bytearray(b'\x55' * 0x10000)
        rom[0x38:0x3D] = b'\xF5\xDB\xBF\xF1\xC9'                  # push af ; in a,($BF) ; pop af ; ret
        rom[0x66:0x68] = b'\xED\x45'
        rom[0x100:0x400] = b'\xFF' * 0x300
        rom[0x200 + 0x400:0x205 + 0x400] = b'\xDB\xBF\x07\x30\xFB'   # at $0600: in a,($BF) ; rlca ; jr nc,*-3
        vram = bytes(random.Random(12).randrange(256) for _ in range(0x4000))
        scene = make_scene({'vram': (vram, [tag(pv.RT_DERIVED, 0x9000)] * 0x4000)})
        return bytes(rom), gt.tile_at(scene, 'sms', 64), vram

    def test_work_after_the_games_handler(self):
        rom, t, vram = self.setup_game()
        plan = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'sms', after_handler=True)
        self.assertEqual(plan.details['timing'], "after the game's handler")
        work = bytearray(vram)
        cpu = Z80(plan.apply(rom), work)
        cpu.r.update(SmsOverlayTests.REGS)
        before = dict(cpu.r)
        cpu.stack.append(('ret', 0x1234))             # the interrupted program
        order = []
        real_in = cpu.port_in
        cpu.port_in = lambda n: (order.append(('status' if n == 0xBF else 'data', cpu.steps)), real_in(n))[1]
        self.assertEqual(cpu.run(0x38, 0x1234), 0x1234)
        self.assertEqual((cpu.r, cpu.stack, bytes(work[64:96])), (before, [], bytes(32)))
        kinds = [k for k, _ in order if k in ('status', 'data')]
        self.assertEqual(kinds[0], 'status')           # the game's handler ran before the routine read video memory
        self.assertIn('data', kinds)

    def test_routine_called_from_the_games_own_wait(self):
        rom, t, vram = self.setup_game()
        plan = gt.plan_overlay_patch([(t, [0] * 64)], rom, 'sms', hook='poll')
        out = plan.apply(rom)
        self.assertEqual((plan.details['hook'], plan.details['hook_sites'], out[0x38:0x3B]), ('poll', 1, rom[0x38:0x3B]))
        self.assertEqual((out[0x600], out[0x603:0x605]), (0xCD, bytes(2)))            # call routine ; nop ; nop
        results = []
        for image in (rom, out):
            work = bytearray(vram)
            cpu = Z80(image, work)
            cpu.r.update(SmsOverlayTests.REGS)
            cpu.run(0x600, 0x605)
            results.append((dict(cpu.r), list(cpu.stack)))
            self.assertEqual(bytes(work[64:96]) == bytes(32), image is out)
        self.assertEqual(results[0], results[1])           # the wait leaves the registers as the game's own loop did
        with self.assertRaisesRegex(ValueError, 'no loop that waits'):
            gt.plan_overlay_patch([(t, [0] * 64)], rom.replace(b'\xDB\xBF\x07\x30\xFB', b'\x55' * 5), 'sms', hook='poll')
        control = gt.plan_hook_only(rom, 'sms', hook='poll')
        cpu = Z80(control.apply(rom), bytearray(vram))
        cpu.run(0x600, 0x605)
        self.assertEqual((control.kind, cpu.address, cpu.stack), ('hook-only', 0, []))


class SnesPollHookTests(unittest.TestCase):
    def test_the_wait_loop_calls_the_routine(self):
        rom, t = SnesPlacementTests().setup_game()
        rom[0x18000:0x18400] = b'\xFF' * 0x400
        rom[0x9000:0x9005] = b'\xAD\x10\x42\x10\xFB'              # lda $4210 ; bpl *-3
        rom[0xA000:0xA005] = b'\xAD\x10\x42\x10\xFB'
        rom[0xB000:0xB005] = b'\x2C\x12\x42\x10\xFB'              # another form, found once: left alone
        plan = gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'snes', hook='poll')
        out = plan.apply(bytes(rom))
        body = plan.details['routine_offset']
        self.assertEqual((plan.details['hook'], plan.details['hook_sites']), ('poll', 2))
        jsl = b'\x22' + bytes((body & 0xFF, 0x80 | (body >> 8 & 0x7F), 0x80 | body >> 15)) + b'\xEA'
        self.assertEqual((out[0x9000:0x9005], out[0xA000:0xA005], out[0xB000:0xB005]), (jsl, jsl, bytes(rom[0xB000:0xB005])))
        self.assertEqual(out[0x7FE0:0x8000], bytes(rom[0x7FE0:0x8000]))                 # no vector is touched
        code = out[body:body + plan.details['routine_size']]
        self.assertEqual(code[:5], b'\xAD\x10\x42\x10\xFB')                           # the game's wait comes first
        self.assertIn(b'\x28\x6B\xEA\xEA\xEA', code)                                  # plp ; rtl
        self.assertNotIn(b'\x5C', code[:code.index(b'\x6B\xEA\xEA\xEA')])
        control = gt.plan_hook_only(bytes(rom), 'snes', hook='poll')
        where = control.details['routine_offset']
        self.assertEqual(control.apply(bytes(rom))[where:where + 6], b'\xAD\x10\x42\x10\xFB\x6B')
        rom[0x9000] = rom[0xA000] = rom[0xB000] = 0x55
        with self.assertRaisesRegex(ValueError, 'no loop that waits'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'snes', hook='poll')


class BankProbeTests(unittest.TestCase):
    def test_probe_tells_banks_apart(self):
        rom = gb_rom(0x10000, 0x55)
        rom[0x147] = 0x19
        for bank in range(4):
            rom[bank * 0x4000 + 0x123] = 0x10 + bank
        self.assertEqual(gt.gb_bank_probe(bytes(rom)), {'offsets': [0x123], 'table': [(0x10, 0), (0x11, 1), (0x12, 2), (0x13, 3)]})
        rom[0x147] = 0x01                                  # MBC1 cannot map bank 0 at $4000
        self.assertEqual([b for _, b in gt.gb_bank_probe(bytes(rom))['table']], [1, 2, 3])
        same = gb_rom(0x10000, 0x55); same[0x147] = 0x01
        self.assertEqual(gt.gb_bank_probe(bytes(same))['table'], [(0x55, 1)])     # identical banks count as one
        two = gb_rom(0x10000, 0x55); two[0x147] = 0x01
        two[0x4000 + 9], two[0x8000 + 9], two[0xC000 + 9] = 1, 1, 2
        two[0x4000 + 20], two[0x8000 + 20], two[0xC000 + 20] = 7, 8, 7
        probe = gt.gb_bank_probe(bytes(two))
        self.assertEqual(len(probe['offsets']), 2)
        self.assertEqual(len({row[:2] for row in probe['table']}), 3)

    def setup_game(self):
        rom = gb_rom(0x10000, 0x55)
        rom[0x147], rom[0x148] = 0x01, 0x01
        rom[0x40:0x43] = b'\xC3\x00\x02'
        rom[0x3000:0x3020] = b'\xFF' * 0x20                 # room for a stub only
        rom[0xC100:0xC400] = b'\xFF' * 0x300                # room for the routine in bank 3
        for bank in range(4):
            rom[bank * 0x4000 + 0x77] = 0x30 + bank
        vram = bytearray(random.Random(9).randrange(256) for _ in range(0x4000))
        scene = make_scene({'vram': (bytes(vram), [tag(pv.RT_DERIVED, 0x4000)] * 0x4000)})
        return bytes(rom), scene, vram

    def test_routine_in_another_bank_restores_the_games_bank(self):
        rom, scene, vram = self.setup_game()
        t = gt.tile_at(scene, 'gb', 5 * 16)
        plan = gt.plan_overlay_patch([(t, [3 - p for p in t.pixels])], rom, 'gb')
        self.assertEqual((plan.details['placement'], plan.details['bank_probe']), ('banked-probe', [0x4077]))
        edited = plan.apply(rom)
        for mapped in (1, 2):
            cpu = Sm83(edited, bytearray(vram))
            cpu.bank = mapped
            cpu.r.update(dict(a=0x12, b=0x34, c=0x56, d=0x78, e=0x9A, h=0xBC, l=0xDE, z=1, cy=0))
            before = dict(cpu.r)
            cpu.run(0x40, 0x200)
            self.assertEqual((cpu.bank, cpu.r, cpu.stack), (mapped, before, []))
            self.assertEqual(bytes(cpu.vram[80:96]), gt.encode_tile([3 - p for p in t.pixels], 'gb-2bpp'))

    def test_plain_cartridge_gets_a_mapper_and_a_second_half(self):
        rom = gb_rom(0x8000, 0x55)
        rom[0x40:0x43] = b'\xC3\x00\x02'
        rom[0x147], rom[0x148] = 0x00, 0x00                 # no mapper, 32 KB
        rom[0x3000:0x3020] = b'\xFF' * 0x20
        vram = bytearray(random.Random(9).randrange(256) for _ in range(0x4000))
        scene = make_scene({'vram': (bytes(vram), [tag(pv.RT_DERIVED, 0x4000)] * 0x4000)})
        t = gt.tile_at(scene, 'gb', 5 * 16)
        plan = gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'gb')
        out = plan.apply(bytes(rom))
        self.assertEqual((plan.details['placement'], len(out), out[0x147], out[0x148]), ('added-mapper', 0x10000, 0x01, 0x01))
        # the added banks are copies of bank 1 (a stray write to the new mapper then changes nothing); the
        # routine takes the place of the last bytes of the last copy only
        size = plan.details['routine_size']
        self.assertEqual(out[0x8000:0xC000], bytes(rom[0x4000:0x8000]))
        self.assertEqual(out[0xC000:0x10000 - size], bytes(rom[0x4000:0x8000 - size]))
        self.assertEqual(plan.details['routine_offset'], 0x10000 - size)
        cpu = Sm83(out, bytearray(vram))
        cpu.run(0x40, 0x200)
        self.assertEqual((cpu.bank, bytes(cpu.vram[80:96])), (1, bytes(16)))
        with self.assertRaisesRegex(ValueError, 'free bytes'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'gb', grow=False)


class SnesPlacementTests(unittest.TestCase):
    def setup_game(self, size=0x40000):
        rom = bytearray(b'\x55' * size)                   # LoROM, nothing free
        rom[0x7FC0:0x7FD5] = b'TEST GAME            '
        rom[0x7FD5], rom[0x7FD7] = 0x20, 0x08
        rom[0x7FDC:0x7FE0] = b'\xFF\xFF\x00\x00'
        rom[0x7FE0:0x8000] = b'\x11' * 0x20                # every vector slot holds something
        rom[0x7FEA:0x7FEC] = b'\x34\x92'
        rom[0x7FEE:0x7FF0] = b'\x78\x96'
        vram = bytes(random.Random(3).randrange(1, 255) for _ in range(0x10000))
        scene = make_scene({'vram': (vram, [tag(pv.RT_DERIVED, 0x9000)] * 0x10000)})
        return rom, gt.tile_at(scene, 'snes', 0x4000)

    def test_reserved_vector_slot_and_growth(self):
        rom, t = self.setup_game()
        plan = gt.plan_overlay_patch([(t, [15 - p for p in t.pixels])], bytes(rom), 'snes')
        out = plan.apply(bytes(rom))
        self.assertEqual((plan.details['stub'], plan.details['placement'], len(out)), ('unused vector slot', 'added-rom', 0x80000))
        self.assertEqual(out[0x7FEA:0x7FEC], b'\xE0\xFF')                    # vector -> $00:FFE0, a slot the processor never reads
        self.assertEqual(out[0x7FE0:0x7FE4], b'\x5C\x04\x80\x88')             # jml $88:8004, the first added bank
        self.assertEqual(out[0x7FD7], 0x09)                                   # header: 512 KB
        self.assertLess(len(plan.writes), 400)
        self.assertEqual(out[0x40000:0x40004], b'\xFF' * 4)
        with self.assertRaisesRegex(ValueError, 'cannot grow'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom) + b'\x55' * (0x400000 - len(rom)), 'snes')
        with self.assertRaisesRegex(ValueError, 'free bytes'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'snes', grow=False)

    def test_irq_hook_and_handlers_in_ram(self):
        rom, t = self.setup_game()
        rom[0x18000:0x18400] = b'\xFF' * 0x400
        plan = gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'snes', hook='irq')
        out = plan.apply(bytes(rom))
        self.assertEqual((out[0x7FEA:0x7FEC], out[0x7FEE:0x7FF0]), (b'\x34\x92', b'\xE0\xFF'))
        code = out[plan.details['routine_offset']:][:plan.details['routine_size']]
        self.assertIn(b'\xAF\x12\x42\x00', code)                              # works only in the vertical blank
        self.assertIn(b'\x5C\x78\x96\x00', code)
        rom[0x7FEA:0x7FEC] = b'\x00\x00'                                      # the game builds its handler jump at $0000
        code = gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'snes').apply(bytes(rom))[0x18000:0x18400]
        self.assertIn(b'\x5C\x00\x00\x00', code)
        rom[0x7FE4:0x7FF0] = bytes(12)
        with self.assertRaisesRegex(ValueError, 'no vertical-blank'):
            gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'snes')

    def test_controls(self):
        rom, t = self.setup_game()
        rom[0x18000:0x18400] = b'\xFF' * 0x400
        hook = gt.plan_hook_only(bytes(rom), 'snes')
        out = hook.apply(bytes(rom))
        self.assertEqual((hook.kind, hook.expect, out[0x7FE0:0x7FE4]), ('hook-only', {}, b'\x5C\x34\x92\x00'))
        real = gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'snes')
        for cost in ('low', 'high'):
            control = gt.plan_overlay_control([(t, [0] * 64)], bytes(rom), 'snes', cost=cost)
            code = control.apply(bytes(rom))[control.details['routine_offset']:][:control.details['routine_size']]
            self.assertEqual((control.kind, control.expect, len(code)), ('overlay-control', {'vram': {}}, real.details['routine_size'] + 4))
            for register in (b'\x8F\x15\x21\x00', b'\x8F\x16\x21\x00', b'\x8F\x18\x21\x00', b'\xAF\x39\x21\x00'):
                self.assertNotIn(register, code)                                 # no picture-chip register left
                self.assertIn(register, real.apply(bytes(rom))[real.details['routine_offset']:][:real.details['routine_size']])
        with self.assertRaisesRegex(ValueError, 'no cost-matched control'):
            gt.plan_overlay_control([(t, [0] * 64)], bytes(rom), 'nes')

    def test_game_boy_control_writes_back_what_it_reads(self):
        rom, scene, vram = OverlayTests().setup_game()
        t = gt.tile_at(scene, 'gb', 5 * 16)
        real = gt.plan_overlay_patch([(t, [3 - p for p in t.pixels])], rom, 'gb')
        for cost in ('high', 'low'):
            control = gt.plan_overlay_control([(t, [3 - p for p in t.pixels])], rom, 'gb', cost=cost)
            self.assertEqual((control.kind, control.expect, control.details['routine_size']),
                             ('overlay-control', {'vram': {}}, real.details['routine_size']))
            work = bytearray(vram)
            cpu = Sm83(control.apply(rom), work)
            cpu.run(0x40, 0x200)
            self.assertEqual(work, vram)
            if cost == 'high':
                steps = cpu.steps
        self.assertGreater(steps, cpu.steps)               # the 'high' control takes the longer path

    def test_genesis_controls_and_idle_guard(self):
        rom = bytearray(b'\x55' * 0x2000)
        rom[0x78:0x7C] = (0x000200).to_bytes(4, 'big')
        rom[0x1000:0x1400] = b'\xFF' * 0x400
        vram = bytes(random.Random(4).randrange(1, 255) for _ in range(0x10000))
        scene = make_scene({'vram': (vram, [tag(pv.RT_DERIVED, 0x900)] * 0x10000)})
        t = gt.tile_at(scene, 'genesis', 0x8440)
        hook = gt.plan_hook_only(bytes(rom), 'genesis')
        where = hook.details['routine_offset']
        self.assertEqual(hook.apply(bytes(rom))[where:where + 6], bytes.fromhex('4EF900000200'))
        sizes = {}
        for guard in (False, True, 'idle'):
            plan = gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'genesis', guard=guard)
            sizes[guard] = plan.details['routine_size']
        self.assertEqual(sizes['idle'] - sizes[True], 52)
        after = gt.plan_overlay_patch([(t, [0] * 64)], bytes(rom), 'genesis', guard='idle', after_handler=True)
        code = after.apply(bytes(rom))[after.details['routine_offset']:][:after.details['routine_size']]
        self.assertEqual(code[:12], bytes.fromhex('487A000A40E74EF900000200'))    # second frame, then the game's handler
        self.assertNotIn(bytes.fromhex('4EF900000200'), code[12:])               # the work ends with rte, not a jump
        self.assertIn(bytes.fromhex('4CDF07074E73'), code)
        control = gt.plan_overlay_control([(t, [0] * 64)], bytes(rom), 'genesis', cost='high', guard='idle')
        code = control.apply(bytes(rom))[control.details['routine_offset']:][:control.details['routine_size']]
        self.assertNotIn(bytes.fromhex('43F900C00000'), code)
        port = control.details['routine_offset'] + len(code) - 8
        self.assertIn(bytes.fromhex('43F9') + port.to_bytes(4, 'big'), code)
        self.assertEqual((control.expect, code[-8:-6]), ({'vram': {}}, b'\x5A\xA5'))


class SegaRegisterTests(unittest.TestCase):
    def state(self, regs, vdp_at=2):
        body = bytes((1, 64)) + bytes(0x10000 + 128 + 128 + 320) + bytes(regs) + (0x1234).to_bytes(4, 'big') + bytes(4) + b'\x01' + bytes(40)
        sections = b''
        for ident in range(1, vdp_at + 2):
            data = body if ident == 3 else bytes(10)
            sections += ident.to_bytes(2, 'big') + len(data).to_bytes(4, 'big') + data
        return bytes(8) + sections

    def test_registers_are_read_from_a_blastem_state(self):
        regs = [4, 0x64, 0x30, 0x34, 7, 0x6A] + [0] * 6 + [0x81, 0x36, 0, 2, 1] + [0] * 7
        video = gt.blastem_video(self.state(regs), 'genesis')
        self.assertEqual((video['regs'], video['address'], video['code'], video['source']), (regs, 0x1234, 1, 'savestate'))
        self.assertIsNone(gt.blastem_video(self.state([0] * 24), 'genesis'))     # not in mode 5: not a Mega Drive game's state
        self.assertIsNotNone(gt.blastem_video(self.state([0] * 24), 'sms'))
        self.assertIsNone(gt.blastem_video(b'\x00' * 64, 'genesis'))
        vram = bytearray(0x10000)
        scene = make_scene({'vram': (bytes(vram), [0] * 0x10000)})
        layers = gt.layers(scene, 'genesis', video)
        self.assertEqual([(l.name, l.width, l.height, l.layout_source) for l in layers],
                         [('plane A', 64, 32, 'registers'), ('plane B', 64, 32, 'registers'), ('window', 64, 32, 'registers')])
        self.assertEqual(layers[0].cells[0].addresses, [0xC000, 0xC001])

    def test_sprites_count_as_tiles_on_screen(self):
        regs = [4, 0x64, 0x30, 0x34, 7, 0x6A] + [0] * 6 + [0x81, 0x36, 0, 2, 1] + [0] * 7
        vram = bytearray(0x10000)
        table = (0x6A & 0x7E) << 9
        vram[table:table + 8] = bytes((0, 0x90, 0x05, 0, 0x01, 0x23, 0, 0x90))      # 2x2 sprite of tile $123 on screen
        scene = make_scene({'vram': (bytes(vram), [0] * 0x10000)})
        used = gt.used_tile_addresses(scene, 'genesis', {'regs': regs})
        self.assertTrue({0x123 * 32, 0x124 * 32, 0x125 * 32, 0x126 * 32} <= used)
        sms = bytearray(0x4000)
        sms[0x3F00], sms[0x3F81], sms[0x3F01] = 0x40, 0x07, 0xD0
        scene = make_scene({'vram': (bytes(sms), [0] * 0x4000)})
        used = gt.used_tile_addresses(scene, 'sms', {'regs': [0x06, 0xE0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF] + [0] * 17})
        self.assertIn(0x2000 + 7 * 32, used)


class SafestVariantTests(unittest.TestCase):
    def setup_game(self):
        rom = bytearray(b'\x55' * 0x2000)
        rom[0x78:0x7C] = (0x000200).to_bytes(4, 'big')
        rom[0x1000:0x1400] = b'\xFF' * 0x400
        vram = bytes(random.Random(4).randrange(1, 255) for _ in range(0x10000))
        scene = make_scene({'vram': (vram, [tag(pv.RT_DERIVED, 0x900)] * 0x10000)})
        return bytes(rom), scene, gt.tile_at(scene, 'genesis', 0x8440)

    def test_the_planner_goes_on_to_a_variant_that_is_clean_from_power_on(self):
        rom, scene, t = self.setup_game()
        ok = lambda plan: {'verified': True, 'as_planned': True}
        first = gt.plan_derived_tile_edit(t, [0] * 64, rom, scene, verify=ok)
        self.assertEqual(first.details['options'], gt.OVERLAY_VARIANTS['68000'][0])
        asked = []

        def safety(plan, edits, options):
            asked.append(options)
            return {'state': 'clean' if options == {'guard': True} else 'disturbed', 'hook_only': {'clean': True}}
        plan = gt.plan_derived_tile_edit(t, [0] * 64, rom, scene, verify=ok, safety=safety)
        self.assertEqual((plan.details['options'], plan.details['safety'], len(asked)),
                         ({'guard': True}, 'clean', gt.OVERLAY_VARIANTS['68000'].index({'guard': True}) + 1))
        # nothing clean: the best outcome is returned and the plan says what that means
        plan = gt.plan_derived_tile_edit(t, [0] * 64, rom, scene, verify=ok,
                                         safety=lambda p, e, o: {'state': 'timing' if o.get('after_handler') else 'disturbed',
                                                                 'hook_only': {'clean': True}})
        self.assertEqual((plan.details['safety'], plan.details['options']['after_handler']), ('timing', True))
        self.assertTrue(any('changes course when any code is added' in n for n in plan.notes))
        # a game that the bare hook already changes: one variant is enough
        asked.clear()
        gt.plan_derived_tile_edit(t, [0] * 64, rom, scene, verify=ok,
                                  safety=lambda p, e, o: (asked.append(o), {'state': 'timing', 'hook_only': {'clean': False}})[1])
        self.assertEqual(len(asked), 1)


class RepointEveryUserTests(unittest.TestCase):
    def test_references_of_other_scenes_move_with_the_block(self):
        helper = CompressedBlockTests()
        rom, scene, game, raw, stream, start = helper.build()
        rom = bytearray(rom)
        rom[0x1100] = 0x21                                   # a second place loads the same block, elsewhere in video memory
        rom[0x1101:0x1103] = bytes([start & 0xFF, start >> 8])
        rom = bytes(rom)
        other = MiniGame('lz3', 0x1101, 0x1400)
        tags = [0] * 0x4000
        for i in range(len(raw)):
            tags[0x1400 + i] = tag(pv.RT_DERIVED, start + min(len(stream) - 1, 1 + i * len(stream) // len(raw)))
        scene2 = make_scene({'vram': (other.vram(rom), tags)}, frame=20)
        block = gt.find_compressed_block(scene, rom, 'gb', 'vram', 0x800, 16)
        block2 = gt.find_compressed_block(scene2, rom, 'gb', 'vram', 0x1400, 16)
        self.assertEqual((block2.start, block2.domain_start), (block.start, 0x1400))
        changes = {i: v for i, v in helper.grow_changes(raw).items() if v != raw[i - 0x800]}
        # alone, only this scene's reference moves and the other scene keeps the old picture
        alone = gt.plan_block_edit(block, changes, rom, 'gb', verify=game.verifier(rom, scene))
        self.assertEqual(alone.details['repointed'], [0x1001])
        self.assertEqual(other.vram(alone.apply(rom)), other.vram(rom))
        # with the other scene named, its reference is found by its own replay and moved too
        plan = gt.plan_block_edit(block, changes, rom, 'gb', verify=game.verifier(rom, scene),
                                  also=[(block2, other.verifier(rom, scene2))])
        self.assertEqual((sorted(plan.details['repointed']), plan.details['scenes_repointed']), ([0x1001, 0x1101], 1))
        edited = plan.apply(rom)
        for i, v in changes.items():
            self.assertEqual(game.vram(edited)[i], v)
            self.assertEqual(other.vram(edited)[i - 0x800 + 0x1400], v)
        self.assertEqual(plan.details['pointer_search']['confirmed'], 1)


class RelocationTests(unittest.TestCase):
    def test_growth_is_not_listed_byte_by_byte(self):
        self.assertEqual(gt._diff_writes(b'\x01\x02', b'\x01\x03\xFF\xFF\x07'), [(1, 2, 3), (4, None, 7)])
        self.assertEqual(gt.apply_writes(b'\x01\x02', [(1, 2, 3), (4, None, 7)], 5), b'\x01\x03\xFF\xFF\x07')

    def test_far_pointer_relocation_can_grow_a_game_boy_rom(self):
        rom = gb_rom(0x10000, 0x55)
        rom[0x147], rom[0x148] = 0x19, 0x01
        block = bytes(range(1, 65))
        rom[0x9000:0x9040] = block
        rom[0x200:0x203] = b'\x02\x00\x50'                 # bank 2, $5000
        cands = [c for c in gt.pointer_candidates(bytes(rom), 'gb', 0x9000) if c['encoding'] == 'gb-far-pre']
        plan = gt.plan_relocation(bytes(rom), 'gb', 0x9000, 0x9040, block[::-1], cands[0])
        out = plan.apply(bytes(rom))
        self.assertEqual((len(out), out[0x148], plan.details['new_offset'], plan.details['repointed']), (0x20000, 0x02, 0x10000, [0x200]))
        self.assertEqual((out[0x200:0x203], out[0x10000:0x10040]), (b'\x04\x00\x40', block[::-1]))
        with self.assertRaisesRegex(ValueError, 'No free ROM space'):
            gt.plan_relocation(bytes(rom), 'gb', 0x9000, 0x9040, block[::-1], cands[0], grow=False)

    def test_pointer_search_says_why_it_found_nothing(self):
        self.assertIn('computed', gt._no_pointer({'candidates': 0}))
        self.assertIn('no free ROM space', gt._no_pointer({'candidates': 3, 'no_room': 3, 'replayed': 0}))
        self.assertIn('none changed the scene', gt._no_pointer({'candidates': 3, 'no_room': 1, 'replayed': 2}))


if __name__ == '__main__':
    unittest.main()
