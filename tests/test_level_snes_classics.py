"""Super Mario World and Super Metroid level profiles on made-up cartridges that only have the tables at their real
places (no game data)."""
import unittest

from romancer.level_profiles.snes_classics import (SuperMarioWorldProfile, SuperMetroidProfile, lorom, _Cpu,
                                                   _SmwSpriteWatcher, _SmwRamWatcher, _SmEnemyWatcher, _SmItemWatcher,
                                                   _SmwLayoutWatcher, _SmLayoutWatcher, _sm_compress, _sm_decompress)


def put(rom, address, data):
    o = lorom(address)
    rom[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8 & 0xFF]


LEVEL = 0x105


def smw_rom():
    rom = bytearray(0x80000)
    put(rom, 0x000005, [0xFF])                       # every other level: empty object list
    put(rom, 0x078001, [0xFF])                       # every other level: empty sprite list
    # level $105: layer 1 data at $068000, sprite list at $07C000
    put(rom, 0x05E000 + LEVEL * 3, [0x00, 0x80, 0x06])
    put(rom, 0x05EC00 + LEVEL * 2, [0x00, 0xC0])
    put(rom, 0x05EC00, [0x01, 0x80])                 # level 0 points at the empty sprite list
    put(rom, 0x068000, [0x13, 0x00, 0x08, 0x80, 0x07])       # header: 20 screens, mode 0, sprite graphics 8
    objects = [0x14, 0x06, 0x30,                     # screen 0: extended object $30 at row 20, column 6
               0xA3, 0x02, 0x40,                     # screen 1: a standard object (number $10)
               0x01, 0x00, 0x00, 0xCA,               # screen exit on screen 1 to level $CA
               0x95, 0x03, 0x2B,                     # screen 2: extended object $2B at row 21, column 3
               0xFF]
    put(rom, 0x068005, objects)
    sprites = [0x01,
               0xA0, 0x18, 0x05,                     # row $A, screen 8, column 1: sprite 5
               0xA0, 0x28, 0x05,
               0xB0, 0x39, 0x0F,
               0xFF]
    put(rom, 0x07C000, sprites)
    # another level (sprite graphics 8 too) uses sprite 4, so it is a swap choice
    put(rom, 0x05E000 + 0x10 * 3, [0x00, 0x90, 0x06])
    put(rom, 0x069000, [0x00, 0x00, 0x08, 0x00, 0x00, 0xFF])
    put(rom, 0x05EC00 + 0x10 * 2, [0x00, 0xD0])
    put(rom, 0x07D000, [0x00, 0x00, 0x10, 0x04, 0xFF])
    # where each screen's blocks are in RAM ($00BEA8 -> per mode -> per screen, low and high bytes)
    put(rom, 0x00BEA8, word(0xA000))
    put(rom, 0x00BEAC, word(0xA100))
    put(rom, 0x00A000, word(0xA200))
    put(rom, 0x00A100, word(0xA300))
    for s in range(4):
        put(rom, 0x00A200 + s * 3, [*word(0xC800 + s * 0x1B0), 0x7E])
        put(rom, 0x00A300 + s * 3, [*word(0xC800 + s * 0x1B0), 0x7F])
    return rom


def smw_ram(**pokes):
    ram = bytearray(0x20000)
    ram[0x100] = 0x14
    ram[0xCE], ram[0xCF], ram[0xD0] = 0x00, 0xC0, 0x07
    ram[0x192B], ram[0x1931], ram[0x1925], ram[0x1930] = 8, 7, 0, 0
    ram[0x1A], ram[0x1B], ram[0x1C], ram[0x1D] = 0x34, 0x02, 0xC0, 0x00
    for k, v in pokes.items():
        ram[int(k[1:], 16)] = v
    return ram


class SuperMarioWorldTest(unittest.TestCase):
    def setUp(self):
        self.rom = smw_rom()
        self.p = SuperMarioWorldProfile(bytes(self.rom))

    def test_where(self):
        self.assertEqual(self.p.where(smw_ram()), {'part': {'level': LEVEL}, 'x': 0x234, 'y': 0xC0})
        self.assertIsNone(self.p.where(smw_ram(a100=0x0E)))

    def test_sprites(self):
        rows = self.p.sprite_list(LEVEL)
        self.assertEqual([(r['number'], r['x'], r['y']) for r in rows], [(5, 8 * 256 + 16, 0xA0), (5, 8 * 256 + 32, 0xA0), (0x0F, 9 * 256 + 48, 0xB0)])
        objs = [o for o in self.p.objects({'level': LEVEL}) if o['id'].startswith('sprite')]
        self.assertEqual(objs[0]['name'], 'Red Koopa')
        self.assertEqual(objs[0]['x'], 8 * 256 + 16 + 8)
        self.assertEqual(objs[0]['y'], 0xA0 + 16)
        self.assertEqual(self.p.swap_choices(8), [4, 5, 0x0F])

    def test_swap(self):
        plan = self.p.edit({'level': LEVEL}, 'sprite:1', {'number': 4})
        self.assertEqual(plan['writes'], [(lorom(0x07C000) + 1 + 3 + 2, 5, 4)])
        with self.assertRaises(ValueError):
            self.p.edit({'level': LEVEL}, 'sprite:1', {'number': 0x77})
        w = self.p.watcher(plan['watch'])
        ram = smw_ram(a14C8=8, a161A=1, a9E=4)
        self.assertTrue(w.see(ram, 10, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        w.see(smw_ram(a14C8=8, a161A=1, a9E=5), 10, 'original')
        self.assertEqual(w.result()['state'], 'bad')

    def test_remove(self):
        plan = self.p.edit({'level': LEVEL}, 'sprite:0', {}, True)
        start = lorom(0x07C000) + 1
        new = bytearray(self.rom)
        for off, old, val in plan['writes']:
            self.assertEqual(new[off], old)
            new[off] = val
        self.assertEqual(bytes(new[start:start + 7]), bytes([0xA0, 0x28, 0x05, 0xB0, 0x39, 0x0F, 0xFF]))
        self.assertEqual(len(SuperMarioWorldProfile(bytes(new)).sprite_list(LEVEL)), 2)
        # the sprite seen at its spot: bad; the screen passing the spot with nothing there: good
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(smw_ram(a14C8=8, a9E=5, aE4=0x10, a14E0=8, aD8=0xA0), 3, 'original'))
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(plan['watch'])
        for f in range(40):
            if w.see(smw_ram(a1A=0x00, a1B=0x08), f, 'changed'):
                break
        self.assertEqual(w.result()['state'], 'good')

    def test_blocks_and_exits(self):
        blocks = self.p.blocks(LEVEL)
        self.assertEqual([(b['ext'], b['screen'], b['row'], b['col']) for b in blocks], [(0x30, 0, 20, 6), (0x2B, 2, 21, 3)])
        plan = self.p.edit({'level': LEVEL}, f'block:{blocks[0]["offset"]:x}', {'ext': 0x32})
        self.assertEqual(plan['writes'], [(lorom(0x068005) + 2, 0x30, 0x32)])
        self.assertEqual(plan['watch']['ram'], (0xC800 + 0x100 + 4 * 16 + 6, 0x1C800 + 0x100 + 4 * 16 + 6))
        ram = smw_ram()
        ram[plan['watch']['ram'][0]], ram[plan['watch']['ram'][1]] = 0x21, 0x01
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        exits = self.p.exits(LEVEL)
        self.assertEqual([(e['screen'], e['to'], e['secondary']) for e in exits], [(1, 0xCA, False)])
        with self.assertRaises(ValueError):
            self.p.edit({'level': LEVEL}, 'exit:1', {'to': 0x33})
        self.assertEqual(self.p.layer1_objects(LEVEL)[1]['number'], 0x10)


# A made-up level builder in 65816 code at the game's places ($05801E calls the object part at $0583AC, then goes to
# $05808F): it reads 3-byte objects after the 5-byte header until $FF. b1 = 0 and b2 = 1 is a screen jump (screen = b0);
# anything else puts block b2 at row b0 & $1F, column b1 & $0F of the current screen (screen bases at $05F000).
BUILDER = bytes.fromhex(
    'c210' 'a00500'                      # REP #$10; LDY #$0005
    'b765' 'c9ff' 'f053'                 # loop: LDA [$65],Y; CMP #$FF; BEQ done
    '8500' 'c8' 'b765' '8501' 'c8' 'b765' '8502' 'c8'
    'a501' 'd00c' 'a502' 'c901' 'd006'   # LDA $01; BNE place; LDA $02; CMP #$01; BNE place
    'a500' '8503' '80dd'                 # LDA $00; STA $03; BRA loop
    'c220' 'a503' '29ff00' '0a' 'aa' 'bf00f005' '8506'      # place: the screen's base
    'a500' '291f00' '0a0a0a0a' '18' '6506' '8506'          # + row * 16
    'a501' '290f00' '18' '6506' 'aa'                       # + column
    'e220' 'a502' '9f00c87e' 'a900' '9f00c87f' '80a7'      # store the block, high byte 0; BRA loop
    '60')                                # done: RTS
LAYOUT_LEVEL = 0x107


def smw_layout_rom():
    rom = smw_rom()
    put(rom, 0x05801E, bytes.fromhex('20ac83' '4c8f80'))     # JSR $83AC; JMP $808F
    put(rom, 0x05808F, [0x6B])                                # RTL
    put(rom, 0x0583AC, BUILDER)
    for s in range(4):
        put(rom, 0x05F000 + s * 2, word(s * 0x1B0))
    put(rom, 0x05E000 + LAYOUT_LEVEL * 3, [0x00, 0xA0, 0x06])
    put(rom, 0x05EC00 + LAYOUT_LEVEL * 2, [0x00, 0xC0])
    put(rom, 0x06A000, [0x01, 0x00, 0x08, 0x00, 0x07,       # 2 screens, mode 0
                        0x05, 0x03, 0x40,                    # block $40 at row 5, column 3
                        0x01, 0x00, 0x01,                    # screen jump to screen 1
                        0x02, 0x04, 0x41, 0xFF])             # block $41 at row 2, column 4 of screen 1
    rom[0x7F000:0x80000] = b'\xff' * 0x1000                 # padding at the end of the last bank: free space
    return rom


class SuperMarioWorldLayoutTest(unittest.TestCase):
    def setUp(self):
        self.rom = smw_layout_rom()
        self.p = SuperMarioWorldProfile(bytes(self.rom))
        self.part = {'level': LAYOUT_LEVEL}

    def test_cpu(self):
        code = bytes.fromhex('a90c' '8d0242' 'a90a' '8d0342' 'ad1642' '8510'   # 12 * 10 with the multiply unit
                             'f8' '18' 'a945' '6955' '8511' 'd8'               # decimal 45 + 55 = 00, carry
                             'c230' 'a93412' 'eb' '8512' 'e230' '6b')          # XBA, STA (16 bits); RTL
        rom = code + bytes(0x8000 - len(code))
        ram = bytearray(0x20000)
        cpu = _Cpu(rom, ram)
        cpu.p = 0x34
        cpu.run(0x008000)
        self.assertEqual((ram[0x10], ram[0x11], ram[0x12], ram[0x13]), (120, 0x00, 0x12, 0x34))
        self.assertTrue(cpu.p & 1)

    def test_packed_layout(self):
        grid = self.p.packed_layout(self.part)
        self.assertEqual((grid['size'], grid['width'], grid['height'], grid['left'], grid['top']), (16, 32, 27, 0, 0))
        self.assertEqual(grid['blocks'][5 * 32 + 3], 0x40)
        self.assertEqual(grid['blocks'][2 * 32 + 20], 0x41)
        self.assertEqual(sum(1 for b in grid['blocks'] if b), 2)

    def test_set_packed_layout(self):
        plan = self.p.set_packed_layout(self.part, [(10, 7, 0x55), (17, 1, 0x56)])
        at = 0x7F000 + 16
        data = bytes(self.rom[lorom(0x06A000):lorom(0x06A000) + 14]) + bytes(
            [0, 0, 1, 7, 0x0A, 0x55, 1, 0, 1, 1, 0x01, 0x56, 0, 0, 1, 0, 0, 1, 0xFF])
        pointer = lorom(0x05E000 + LAYOUT_LEVEL * 3)
        self.assertEqual(plan['writes'], [(at + i, 0xFF, v) for i, v in enumerate(data) if v != 0xFF] +
                         [(pointer, 0x00, 0x10), (pointer + 1, 0xA0, 0xF0), (pointer + 2, 0x06, 0x0F)])
        new = bytearray(self.rom)
        for off, old, val in plan['writes']:
            self.assertEqual(new[off], old)
            new[off] = val
        grid = SuperMarioWorldProfile(bytes(new)).packed_layout(self.part)
        self.assertEqual((grid['blocks'][7 * 32 + 10], grid['blocks'][1 * 32 + 17], grid['blocks'][5 * 32 + 3]), (0x55, 0x56, 0x40))
        spots = plan['watch']['spots']
        self.assertEqual(spots[1], [0xC800 + 0x1B0 + 0x10 + 1, 0x1C800 + 0x1B0 + 0x10 + 1, 0x56])
        ram = smw_ram()
        for low, high, block in spots:
            ram[low], ram[high] = block & 0xFF, block >> 8
        w = self.p.watcher(plan['watch'])
        self.assertIsInstance(w, _SmwLayoutWatcher)
        self.assertTrue(w.see(ram, 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(smw_ram(), 1, 'original'))
        self.assertEqual(w.result()['state'], 'bad')
        with self.assertRaises(ValueError):
            self.p.set_packed_layout(self.part, [(3, 3, 0x155)])     # no object of the made-up game puts it
        with self.assertRaises(ValueError):
            self.p.set_packed_layout(self.part, [(40, 3, 0x55)])     # outside the level

    def test_vertical_levels_are_not_offered(self):
        rom = smw_layout_rom()
        put(rom, 0x058417, [1])                  # mode 0 scrolls up and down
        self.assertIsNone(SuperMarioWorldProfile(bytes(rom)).packed_layout(self.part))


def sm_rom():
    rom = bytearray(0x300000)
    room, state = 0x91F8, 0x9205
    put(rom, 0x8F0000 | room, [0x00, 0x01, 0, 0, 2, 1, 0x70, 0xA0, 0, *word(0xFF00)])
    put(rom, 0x8F0000 | room + 11, word(0xE5E6))
    st = [0] * 26
    st[8:10], st[10:12], st[0x14:0x16] = word(0x9000), word(0x9100), word(0xA000)
    put(rom, 0x8F0000 | state, st)
    pop = []
    for species, x, y in ((0xD000, 100, 200), (0xD040, 300, 120)):
        pop += word(species) + word(x) + word(y) + [0] * 10
    put(rom, 0xA19000, pop + [0xFF, 0xFF, 2])
    put(rom, 0xB49100, word(0xD000) + [0, 0] + word(0xD040) + [0, 0] + [0xFF, 0xFF])
    put(rom, 0xA0D000 + 0x0A, word(8))
    put(rom, 0xA0D000 + 0x3E, word(0x8000))
    put(rom, 0xB48000, b'SKREE     ')
    put(rom, 0x8FA000, word(0xEEDB) + [5, 10] + word(0x40) + [0, 0])
    return rom


class SuperMetroidTest(unittest.TestCase):
    def setUp(self):
        self.rom = sm_rom()
        self.p = SuperMetroidProfile(bytes(self.rom))
        self.part = {'room': 0x91F8, 'state': 0x9205}

    def test_where_and_objects(self):
        ram = bytearray(0x20000)
        ram[0x998], ram[0x79B], ram[0x79C], ram[0x7BB], ram[0x7BC], ram[0x911] = 8, 0xF8, 0x91, 0x05, 0x92, 40
        self.assertEqual(self.p.where(ram), {'part': self.part, 'x': 40, 'y': 0})
        objs = self.p.objects(self.part)
        self.assertEqual([(o['id'], o['name']) for o in objs], [('enemy:0', 'Skree'), ('enemy:1', 'Enemy 0xd040'), ('item:0', 'Missile')])
        self.assertEqual((objs[0]['x'], objs[0]['y']), (100, 208))
        self.assertEqual((objs[2]['x'], objs[2]['y']), (88, 176))

    def test_enemy_edits(self):
        plan = self.p.edit(self.part, 'enemy:0', {'species': 0xD040})
        self.assertEqual(plan['writes'], [(lorom(0xA19000), 0x00, 0x40)])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'enemy:0', {'species': 0xD080})
        plan = self.p.edit(self.part, 'enemy:0', {}, True)
        new = bytearray(self.rom)
        for off, old, val in plan['writes']:
            new[off] = val
        after = SuperMetroidProfile(bytes(new))
        self.assertEqual([(e['species'], e['x']) for e in after.enemies(0x9205)], [(0xD040, 300)])
        self.assertEqual(new[lorom(0xA19000) + 18], 1)          # the kill count follows the list and is lowered
        ram = bytearray(0x20000)
        ram[0x998], ram[0x79B], ram[0x79C], ram[0x7BB], ram[0x7BC] = 8, 0xF8, 0x91, 0x05, 0x92
        ram[0xF78:0xF7A], ram[0xF7A:0xF7C], ram[0xF7E:0xF80] = bytes(word(0xD000)), bytes(word(100)), bytes(word(200))
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 1, 'original'))
        self.assertEqual(w.result()['state'], 'bad')

    def test_item_edit(self):
        plan = self.p.edit(self.part, 'item:0', {'id': 0xEEDF})
        self.assertEqual(plan['writes'], [(lorom(0x8FA000), 0xDB, 0xDF)])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'item:0', {'id': 0xEF2F})     # another style
        ram = bytearray(0x20000)
        ram[0x998], ram[0x79B], ram[0x79C], ram[0x7BB], ram[0x7BC], ram[0x7A5] = 8, 0xF8, 0x91, 0x05, 0x92, 32
        ram[0x1C37:0x1C39], ram[0x1C87:0x1C89] = bytes(word(0xEEDF)), bytes(word((10 * 32 + 5) * 2))
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        self.assertEqual(len(self.p.choices()['items' + 'eed7']), 21)
        self.assertEqual(len(self.p.choices()['items' + 'ef2b']), 20)


# a made-up room of 2 by 1 screens (32 by 16 blocks): the size word, layer 1 words, then BTS bytes
def sm_room_data():
    words = [0x00FF] * 512
    words[3 * 32 + 5] = 0x8007
    bts = [0] * 512
    bts[3 * 32 + 5] = 2
    data = bytes(word(1024))
    for value in words:
        data += bytes(word(value))
    return data + bytes(bts)


def sm_layout_rom():
    rom = sm_rom()
    packed = _sm_compress(sm_room_data())
    put(rom, 0xC28000, packed)
    put(rom, 0x8F9205, [0x00, 0x80, 0xC2])
    rom[lorom(0xCEF000):lorom(0xCEFFFF) + 1] = b'\xff' * 0x1000
    return rom, len(packed)


class SuperMetroidLayoutTest(unittest.TestCase):
    part = {'room': 0x91F8, 'state': 0x9205}

    def test_decompress_every_command(self):
        stream = bytes([0x02, 1, 2, 3,          # 3 bytes as they are
                        0x23, 9,                # 9 four times
                        0x44, 7, 8,             # 7 8 7 8 7
                        0x62, 0xFE,             # FE FF 00
                        0x81, 0x00, 0x00,       # 2 bytes from the start: 01 02
                        0xA1, 0x03, 0x00,       # 2 bytes from offset 3, inverted: F6 F6
                        0xC2, 0x03,             # 3 bytes from 3 back: 02 F6 F6
                        0xFC, 0x01, 0x02,       # long form $E0: 2 bytes from 2 back, inverted: 09 09
                        0xE4, 0x01, 0x05,       # long form $20: 5 two times
                        0xFF])
        data, length = _sm_decompress(stream, 0)
        self.assertEqual(length, len(stream))
        self.assertEqual(data, bytes([1, 2, 3, 9, 9, 9, 9, 7, 8, 7, 8, 7, 0xFE, 0xFF, 0x00, 1, 2, 0xF6, 0xF6,
                                      0x02, 0xF6, 0xF6, 0x09, 0x09, 5, 5]))

    def test_compress_round_trip(self):
        for data in (sm_room_data(), bytes(range(256)) * 3, b'\x00' * 3000, bytes([1, 2]) * 700 + b'\x05'):
            packed = _sm_compress(data)
            self.assertEqual(_sm_decompress(packed, 0), (data, len(packed)))

    def test_packed_layout_and_change(self):
        rom, length = sm_layout_rom()
        p = SuperMetroidProfile(bytes(rom))
        grid = p.packed_layout(self.part)
        self.assertEqual((grid['width'], grid['height']), (32, 16))
        self.assertEqual(grid['blocks'][3 * 32 + 5], 0x028007)
        self.assertEqual(grid['blocks'][0], 0xFF)
        plan = p.set_packed_layout(self.part, [(5, 3, 0xFF)])
        self.assertFalse(plan['watch']['moved'])                 # a plainer room packs smaller: it fits where it was
        new = bytearray(rom)
        for off, old, val in plan['writes']:
            self.assertEqual(new[off], old)
            self.assertTrue(lorom(0xC28000) <= off < lorom(0xC28000) + length)
            new[off] = val
        self.assertEqual(SuperMetroidProfile(bytes(new)).packed_layout(self.part)['blocks'], [0xFF] * 512)
        plan = p.set_packed_layout(self.part, [(6, 3, 0x028007), (0, 0, 0x8001)])
        new = bytearray(rom)
        for off, old, val in plan['writes']:
            self.assertEqual(new[off], old)
            new[off] = val
        after = SuperMetroidProfile(bytes(new)).packed_layout(self.part)['blocks']
        expect = list(grid['blocks'])
        expect[3 * 32 + 6], expect[0] = 0x028007, 0x8001
        self.assertEqual(after, expect)
        self.assertEqual(plan['watch']['spots'], [[0, 0x8001], [3 * 32 + 6, 0x028007]])
        ram = bytearray(0x20000)
        ram[0x998], ram[0x79B], ram[0x79C], ram[0x7BB], ram[0x7BC] = 8, 0xF8, 0x91, 0x05, 0x92
        w = p.watcher(plan['watch'])
        self.assertIsInstance(w, _SmLayoutWatcher)
        self.assertTrue(w.see(ram, 1, 'original'))
        self.assertEqual(w.result()['state'], 'bad')
        ram[0x10002:0x10004] = bytes(word(0x8001))
        i = 3 * 32 + 6
        ram[0x10002 + i * 2:0x10004 + i * 2], ram[0x16402 + i] = bytes(word(0x8007)), 2
        w = p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')

    def test_moves_when_it_does_not_fit(self):
        rom, length = sm_layout_rom()
        p = SuperMetroidProfile(bytes(rom))
        changes = [(c, r, (c * 7 + r * 13) & 0x3FF | 0x8000) for c in range(32) for r in range(16)]
        plan = p.set_packed_layout(self.part, changes)
        self.assertTrue(plan['watch']['moved'])
        new = bytearray(rom)
        for off, old, val in plan['writes']:
            new[off] = val
        self.assertEqual(new[lorom(0x8F9205):lorom(0x8F9205) + 3], bytes([0x10, 0xF0, 0xCE]))
        after = SuperMetroidProfile(bytes(new)).packed_layout(self.part)['blocks']
        self.assertEqual(after, [b for _, _, b in sorted(changes, key=lambda c: (c[1], c[0]))])
        with self.assertRaises(ValueError):
            p.set_packed_layout(self.part, [(32, 0, 0x8001)])


if __name__ == '__main__':
    unittest.main()
