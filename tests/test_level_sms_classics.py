"""Master System level profiles: the decoders and the edits, on a made-up cartridge laid out like the real one.

The real games are not part of the tests; these build the same tables at the same addresses, so a change in how a table
is read or written shows here. What the tables mean was proven by replaying the real games (research notes).
"""
import unittest

from romancer.level_profiles import sms_classics as sc

RAM = 0xC000


def apply(rom, writes):
    out = bytearray(rom)
    for offset, old, new in writes:
        assert out[offset] == old, (hex(offset), old, out[offset])
        out[offset] = new
    return bytes(out)


def sonic_cart():
    """256 KB. Level 0 and 1 (same sprite art) and level 2 (other art, sharing level 1's object list)."""
    rom = bytearray(0x40000)
    T = sc.SonicProfile.HEADERS

    def header(level, at, art, objects):
        rom[T + level * 2:T + level * 2 + 2] = (at - T).to_bytes(2, 'little')
        h = bytearray(37)
        h[24:26] = art.to_bytes(2, 'little')
        h[30:32] = (objects - T).to_bytes(2, 'little')
        rom[at:at + 37] = h
    header(0, T + 0x100, 0x612A, T + 0x300)
    header(1, T + 0x140, 0x612A, T + 0x340)
    header(2, T + 0x180, 0x6C3D, T + 0x340)
    # level 0: motobug, crabmeat, ring monitor, an empty record, a flower (other object)
    rom[T + 0x300:T + 0x300 + 16] = bytes([6, 0x10, 0x12, 0x0B, 0x08, 0x2A, 0x0D, 0x01, 0x1D, 0x09, 0xFF, 0, 0, 0x50, 0x09, 0x0B])
    # level 1 (and 2): a badnik 0x0E and an extra-life monitor
    rom[T + 0x340:T + 0x340 + 7] = bytes([3, 0x0E, 0x05, 0x06, 0x03, 0x07, 0x08])
    return bytes(rom)


class Sonic(unittest.TestCase):
    def setUp(self):
        self.rom = sonic_cart()
        self.p = sc.SonicProfile(self.rom)

    def test_records(self):
        T = sc.SonicProfile.HEADERS
        self.assertEqual(self.p.records(0)[0], (0, T + 0x301, 0x10, 0x12, 0x0B))
        self.assertEqual(len(self.p.records(0)), 5)
        self.assertEqual(self.p.sharing(1), [2])
        self.assertEqual(self.p.badniks_for(0), [0x08, 0x0E, 0x10])      # level 1 has the same art
        self.assertEqual(self.p.badniks_for(2), [0x0E])
        self.assertIsNone(self.p.header(3))

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'level': 0})}
        self.assertEqual(set(objects), {'object:0', 'object:1', 'object:2', 'object:4'})     # the empty record is skipped
        moto = objects['object:0']
        self.assertEqual((moto['style'], moto['name'], moto['x'], moto['y']), ('enemy', 'Motobug', 0x12 * 32 + 16, 0x0B * 32 + 32))
        self.assertEqual(objects['object:2']['style'], 'item')
        self.assertEqual(objects['object:2']['detail'], 'holds ten rings')
        self.assertEqual(objects['object:2']['y'], 9 * 32 + 25)
        self.assertEqual(objects['object:4']['style'], 'block')
        self.assertEqual(objects['object:4']['name'], 'Object 0x50')
        self.assertIn('Green Hill Act 3', self.p.objects({'level': 1})[0]['note'])
        self.assertEqual(self.p.part_name({'level': 0}), 'Green Hill Act 1')
        self.assertEqual(self.p.part_name({'level': 28}), 'Special Stage 1')

    def test_edits(self):
        T = sc.SonicProfile.HEADERS
        plan = self.p.edit({'level': 0}, 'object:0', {'type': 0x08})
        self.assertEqual(plan['writes'], [(T + 0x301, 0x10, 0x08)])
        self.assertEqual(plan['watch']['x'], 0x12 * 32)
        changed = sc.SonicProfile(apply(self.rom, plan['writes']))
        self.assertEqual(changed.records(0)[0][2], 0x08)
        self.assertEqual(self.p.edit({'level': 0}, 'object:1', {}, remove=True)['writes'], [(T + 0x304, 0x08, 0xFF)])
        self.assertEqual(self.p.edit({'level': 0}, 'object:2', {'type': 0x04})['writes'], [(T + 0x307, 0x01, 0x04)])
        self.assertEqual(self.p.edit({'level': 0}, 'object:2', {}, remove=True)['writes'], [(T + 0x307, 0x01, 0xFF)])
        with self.assertRaises(ValueError):
            self.p.edit({'level': 2}, 'object:0', {'type': 0x10})          # Motobug's art is not loaded there
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'object:4', {}, remove=True)
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'object:2', {'type': 0x06})

    def test_where_and_watcher(self):
        ram = bytearray(0x2000)
        self.assertIsNone(self.p.where(ram))                                # no header loaded: title or map
        ram[0xD354 - RAM:0xD354 - RAM + 37] = self.p.header(0)
        ram[0xD25A - RAM:0xD25C - RAM] = (300).to_bytes(2, 'little')
        ram[0xD25D - RAM:0xD25F - RAM] = (256).to_bytes(2, 'little')
        self.assertEqual(self.p.where(ram), {'part': {'level': 0}, 'x': 300, 'y': 256})
        plan = self.p.edit({'level': 0}, 'object:0', {'type': 0x08})
        slot = 0xD3FC + 26 - RAM
        ram[slot] = 0x08
        ram[slot + 2:slot + 4] = (0x12 * 32).to_bytes(2, 'little')
        watcher = self.p.watcher(plan['watch'])
        self.assertTrue(watcher.see(ram, 10, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        ram[slot] = 0x10
        control = self.p.watcher(plan['watch'])
        control.see(ram, 10, 'changed')
        self.assertEqual(control.result()['state'], 'bad')
        self.assertEqual(self.p.watcher(plan['watch']).result()['state'], 'warn')


def alex_cart():
    """128 KB. Round 1 (the shaft, ten screens sharing one packed screen) and round 2 (scrolls right, two screens)."""
    rom = bytearray(0x20000)

    def word(at, value):
        rom[at:at + 2] = value.to_bytes(2, 'little')

    def bank6(address):
        return 6 * 0x4000 + address - 0x8000
    word(0x66CD + 2, 0x6700)
    rom[0x6700:0x670C] = bytes([0x86, 0x00, 0x80, 0x04, 0x80, 0, 0, 2, 9, 0x81, 0x00, 0x80])
    word(0x66CD + 4, 0x6710)
    rom[0x6710:0x671C] = bytes([0x86, 0x00, 0x81, 0x00, 0x81, 0, 0, 2, 0, 8, 0x00, 0x80])
    word(0x66CD + 6, 0x6720)
    rom[0x6720:0x672C] = bytes([0x86, 0x00, 0x80, 0x00, 0x80, 0, 0, 1, 0, 0x48, 0x00, 0x80])     # round 3 scrolls another way
    word(bank6(0x8004), 0x8010)                                  # round 1: column 0
    for n in range(10):
        word(bank6(0x8010) + 2 * n, 0x8200)
    word(bank6(0x8100), 0x8120)                                  # round 2: row 0
    word(bank6(0x8120), 0x8200)
    word(bank6(0x8122), 0x8220)
    # screen A: a star box at column 1 of row 0 and a run of two question boxes at columns 4-5 of row 1
    rom[bank6(0x8200):bank6(0x8200) + 13] = bytes([0x83, 0, 3, 0, 0x11, 0, 0x02, 0x02, 0x7F, 0, 0x2B, 0, 0])
    # screen B: 192 empty blocks
    rom[bank6(0x8220):bank6(0x8220) + 5] = bytes([0x7F, 0, 0x41, 0, 0])
    # enemies: round 1 screen 1 a monster bird; round 2 screen 1 a command, then a scorpion and a frog
    word(0xB503 + 2, 0xB520)
    word(0xB503 + 4, 0xB530)
    word(0xB503 + 6, 0xB540)
    for k in range(8):
        word(0xB520 + 2 * k, 0xB600)
    for k in range(8):
        word(0xB530 + 2 * k, 0xB600)
    word(0xB520 + 2, 0xB610)
    word(0xB530 + 2, 0xB620)
    rom[0xB600] = 0
    rom[0xB610:0xB616] = bytes([1, 0x2D, 0x78, 0x68, 0, 0])
    rom[0xB620:0xB62E] = bytes([0x84, 0x44, 0x30, 0xE0, 0, 2, 0x3E, 0x90, 0xB0, 0, 0x2F, 0x40, 0x70, 0])
    return bytes(rom)


class AlexKidd(unittest.TestCase):
    def setUp(self):
        self.rom = alex_cart()
        self.p = sc.AlexKiddProfile(self.rom)

    def test_rounds_and_screens(self):
        self.assertEqual(self.p.kind(1), 'down')
        self.assertEqual(self.p.kind(2), 'right')
        self.assertIsNone(self.p.kind(3))
        screens = self.p.screen_list(2)
        self.assertEqual([(k, x, y) for k, _, x, y in screens], [(1, 0, 0), (2, 256, 0)])
        self.assertEqual(len(self.p.screen_list(1)), 10)
        self.assertEqual(self.p.screen_list(1)[3][3], 192 * 3)
        packed = sc._rle(self.rom, screens[0][1])
        self.assertEqual(len(packed), 192)
        self.assertEqual(packed[1][0], 3)
        self.assertEqual(packed[16 + 4][2], 2)                      # the two question boxes come from one byte
        self.assertEqual(self.p.enemy_lists(2)[1], [(0xB626, 0x3E, 0x90, 0xB0, 0), (0xB62A, 0x2F, 0x40, 0x70, 0)])

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'round': 2})}
        star = objects['box:1:1']
        self.assertEqual((star['name'], star['x'], star['y']), ('Star box', 24, 16 + 16))
        self.assertTrue(star['fields'])
        self.assertFalse(objects['box:1:20']['fields'])            # part of a run
        scorpion = objects[f'enemy:1:{0xB626}']
        self.assertEqual(scorpion['name'], 'Scorpion')
        self.assertEqual([c['value'] for c in scorpion['fields'][0]['choices']], [0x2F, 0x3E])
        shared = {o['id']: o for o in self.p.objects({'round': 1})}['box:1:1']
        self.assertIn('used', shared['note'])
        self.assertEqual(self.p.part_name({'round': 2}), 'Round 2')

    def test_edits(self):
        bank6 = 6 * 0x4000
        plan = self.p.edit({'round': 2}, 'box:1:1', {'block': 2})
        self.assertEqual(plan['writes'], [(bank6 + 0x202, 3, 2)])
        self.assertEqual(plan['watch'], {'kind': 'box', 'round': 2, 'block': 2, 'name': 'Question box', 'x': 16, 'y': 0})
        plan = self.p.edit({'round': 2}, f'enemy:1:{0xB626}', {'type': 0x2F})
        self.assertEqual(plan['writes'], [(0xB626, 0x3E, 0x2F)])
        self.assertEqual(plan['watch']['sx'], 0xB0 - 8)
        self.assertEqual(self.p.edit({'round': 2}, f'enemy:1:{0xB62A}', {}, remove=True)['writes'], [(0xB62A, 0x2F, 0)])
        with self.assertRaises(ValueError):
            self.p.edit({'round': 2}, f'enemy:1:{0xB626}', {'type': 0x2D})   # not placed in this round
        with self.assertRaises(ValueError):
            self.p.edit({'round': 2}, 'box:1:20', {'block': 3})

    def test_where_and_watchers(self):
        ram = bytearray(0x2000)
        self.assertIsNone(self.p.where(ram))
        ram[0xC01F - RAM], ram[0xC023 - RAM] = 0x8A, 2
        ram[0xC0B6 - RAM], ram[0xC0B5 - RAM], ram[0xC0B0 - RAM] = 1, 0, 0xF8      # about 248, the scroll register says 8
        self.assertEqual(self.p.where(ram), {'part': {'round': 2}, 'x': 264, 'y': 0})
        plan = self.p.edit({'round': 2}, f'enemy:1:{0xB626}', {'type': 0x2F})
        ram[0xC0B6 - RAM], ram[0xC0B0 - RAM] = 0, 0
        ram[0xC08D - RAM] = 1
        ram[0xC3C0 - RAM], ram[0xC3CC - RAM], ram[0xC3CE - RAM] = 0x2F, 0xA8, 0x90
        w = self.p.watcher(plan['watch'])
        for frame in range(5):
            if w.see(ram, frame, 'changed'):
                break
        self.assertEqual(w.result()['state'], 'good')
        ram[0xC3C0 - RAM] = 0x3E
        control = self.p.watcher(plan['watch'])
        for frame in range(5):
            control.see(ram, frame, 'changed')
        self.assertEqual(control.result()['state'], 'bad')
        box = self.p.watcher(self.p.edit({'round': 2}, 'box:1:1', {'block': 2})['watch'])
        cell = 0xC800 - RAM + 2 * 2
        ram[cell], ram[cell + 1] = 5, 0xE0
        self.assertTrue(box.see(ram, 1, 'changed'))
        self.assertEqual(box.result()['state'], 'good')


def wonder_boy_cart():
    """128 KB. Round 0, part 0: a snail, an egg, a fruit, a record above the round's level and a record that needs the
    round's exact level; the other parts are empty. Round 1 (level $40) reads the same part 0 list."""
    rom = bytearray(0x20000)

    def word(at, value):
        rom[at:at + 2] = value.to_bytes(2, 'little')
    rom[0x11E7] = 0x00
    rom[0x11E8] = 0x40
    for rnd in range(41):
        for seg in range(4):
            word(0x9EB6 + (rnd * 4 + seg) * 2, 0xA000 if seg == 0 and rnd < 2 else 0xA100)
            word(0x9D6E + (rnd * 4 + seg) * 2, 0xBC00)
    rom[0xBC00:0xBC08] = bytes([0x1D, 0x70, 0x26, 0x10, 0x11, 0x07, 0x23, 0x13])
    rom[0xA000:0xA010] = bytes([0x10, 0x2C, 0x01,      # snail at position $10
                                0x12, 0x2E, 0x03,      # egg ($10)
                                0x14, 0x50, 0x05,      # fruit ($07)
                                0x16, 0x2C, 0x46,      # level $40: from level $40 on
                                0x98, 0x2C, 0x46,      # bit 7, level $40: only at level $40 exactly
                                0x7F])
    rom[0xA100] = 0xFF
    return bytes(rom)


class WonderBoy(unittest.TestCase):
    def setUp(self):
        self.rom = wonder_boy_cart()
        self.p = sc.WonderBoyProfile(self.rom)

    def test_records(self):
        self.assertEqual([r[6] for r in self.p.records(0)], [0x70, 0x10, 0x07])
        self.assertEqual([r[6] for r in self.p.records(1)], [0x70, 0x10, 0x07, 0x23, 0x23])
        self.assertEqual(self.p.part_name({'round': 5}), 'Area 2, Round 2')

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'round': 0})}
        snail = objects[f'object:{0xA000}']
        self.assertEqual((snail['name'], snail['style']), ('Snail', 'enemy'))
        self.assertEqual(snail['x'], max(0x20 * 8, 256) + 0xD0 - 4)
        self.assertEqual(snail['y'], 145 + 16)
        self.assertEqual([c['name'] for c in snail['fields'][0]['choices']], ['Snail', 'Cobra', 'Rock'])
        egg = objects[f'object:{0xA003}']
        self.assertEqual([c['value'] for c in egg['fields'][0]['choices']], [3, 4, 7])
        self.assertEqual(objects[f'object:{0xA006}']['x'], max(0x28 * 8, 256) + 0x98 - 4)
        self.assertIn('shared', snail['note'])

    def test_edits_and_watcher(self):
        plan = self.p.edit({'round': 0}, f'object:{0xA000}', {'index': 2})
        self.assertEqual(plan['writes'], [(0xA002, 0x01, 0x02)])
        self.assertEqual(self.p.edit({'round': 0}, f'object:{0xA000}', {}, remove=True)['writes'], [(0xA002, 0x01, 0xE1)])
        with self.assertRaises(ValueError):
            self.p.edit({'round': 0}, f'object:{0xA000}', {'index': 3})       # an egg is not one of the enemy choices
        ram = bytearray(0x2000)
        ram[0xC18D - RAM:0xC18F - RAM] = (0xA000).to_bytes(2, 'little')
        self.assertEqual(self.p.where(ram), {'part': {'round': 0}, 'x': 0, 'y': 0})
        w = self.p.watcher(plan['watch'])
        w.see(bytes(ram), 1, 'changed')
        ram[0xC18D - RAM:0xC18F - RAM] = (0xA003).to_bytes(2, 'little')
        ram[0xC1A1 - RAM:0xC1A4 - RAM] = bytes([0x80 | 0x26, 0x20, 0xC9])
        self.assertTrue(w.see(bytes(ram), 2, 'changed'))
        self.assertEqual(w.result()['state'], 'good')


if __name__ == '__main__':
    unittest.main()
