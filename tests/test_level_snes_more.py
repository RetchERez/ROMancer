"""Mega Man X and Super Castlevania IV level profiles on made-up cartridges that only have the object tables at their
real places (no game data)."""
import unittest

from romancer.level_profiles.snes_more import (MegaManXProfile, SuperCastlevania4Profile, lorom, _MmxWatcher,
                                               _Sc4Watcher)


def put(rom, address, data):
    o = lorom(address)
    rom[o:o + len(data)] = bytes(data)


def entry(t, y, oid, sub, x, last):
    return [t, y & 0xFF, y >> 8, oid, sub, x & 0xFF, (x >> 8) | (0x80 if last else 0)]


def mmx_rom():
    rom = bytearray(0x180000)
    # every other level: one helper event and nothing else, at $85:A000
    put(rom, 0x85A000, [0x00] + entry(2, 0x100, 0x00, 0x00, 0x10, True) + [0x00])
    for level in range(13):
        put(rom, 0x8582C2 + level * 2, [0x00, 0xA0])
    put(rom, 0x8582C2, [0x00, 0x90])                 # level 0 at $85:9000
    data = ([0x04] + entry(2, 0x180, 0x15, 0x11, 0x080, True)            # graphics load 1
            + [0x09] + entry(3, 0x170, 0x15, 0x00, 0x130, False) + entry(3, 0x168, 0x29, 0x00, 0x13F, True)
            + [0x0B] + entry(0, 0x170, 0x02, 0x80, 0x170, True)          # large life energy
            + [0x0C] + entry(3, 0x150, 0x0F, 0x00, 0x190, True)
            + [0x0C])
    put(rom, 0x859000, data)
    # the same enemies once more in level 1 so they count as ordinary enemies
    put(rom, 0x8582C2 + 2, [0x00, 0x98])
    put(rom, 0x859800, [0x01] + entry(3, 0x100, 0x15, 0, 0x20, False) + entry(3, 0x100, 0x29, 0, 0x20, False)
        + entry(3, 0x100, 0x0F, 0, 0x30, True) + [0x01])
    return rom


class MegaManXTest(unittest.TestCase):
    def setUp(self):
        self.p = MegaManXProfile(bytes(mmx_rom()))

    def test_decode(self):
        e = self.p.entries(0)
        self.assertEqual([(x['type'], x['id'], x['x'], x['y']) for x in e],
                         [(2, 0x15, 0x80, 0x180), (3, 0x15, 0x130, 0x170), (3, 0x29, 0x13F, 0x168), (0, 0x02, 0x170, 0x170),
                          (3, 0x0F, 0x190, 0x150)])
        start = self.p.list_start(0)
        self.assertEqual(self.p.list_bytes(e), self.p.rom[start:start + 40])
        objs = {o['id']: o for o in self.p.objects({'level': 0})}
        self.assertEqual(objs['obj:1']['name'], 'Spiky')
        self.assertEqual(objs['obj:3']['name'], 'Large life energy')
        self.assertEqual(len(objs['obj:1']['fields'][0]['choices']), 3)
        self.assertNotIn('obj:0', objs)
        self.assertEqual(self.p.where(bytes(0xD1) + bytes([2, 4]) + bytes(0x1E4D - 0xD3) + bytes([0x20, 0x01, 0, 0x40, 0]) +
                                      bytes(0x1F7A - 0x1E52) + bytes([0]) + bytes(0x10000)),
                         {'part': {'level': 0}, 'x': 0x120, 'y': 0x40})

    def test_swap_and_item(self):
        plan = self.p.edit({'level': 0}, 'obj:1', {'enemy': 0x0F00})
        off = self.p.entries(0)[1]['offset']
        self.assertEqual(plan['writes'], [(off + 3, 0x15, 0x0F)])
        self.assertEqual(plan['watch']['entry'], 0xFA02 + 5)
        plan = self.p.edit({'level': 0}, 'obj:3', {'item': 0x0480})
        off = self.p.entries(0)[3]['offset']
        self.assertEqual(plan['writes'], [(off + 3, 0x02, 0x04)])
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'obj:1', {'enemy': 0x2200})

    def test_remove(self):
        # the last entry of column 9: the one before it becomes the last of the column
        plan = self.p.edit({'level': 0}, 'obj:2', {}, remove=True)
        rom = bytearray(self.p.rom)
        for o, old, new in plan['writes']:
            self.assertEqual(rom[o], old)
            rom[o] = new
        q = MegaManXProfile(bytes(rom))
        self.assertEqual([(x['id'], x['x']) for x in q.entries(0)], [(0x15, 0x80), (0x15, 0x130), (0x02, 0x170), (0x0F, 0x190)])
        # the only entry of the last column: the column goes and the list closes one column sooner
        plan = self.p.edit({'level': 0}, 'obj:4', {}, remove=True)
        rom = bytearray(self.p.rom)
        for o, old, new in plan['writes']:
            rom[o] = new
        self.assertEqual(len(MegaManXProfile(bytes(rom)).entries(0)), 4)

    def test_watcher(self):
        plan = self.p.edit({'level': 0}, 'obj:1', {'enemy': 0x0F00})
        ram = bytearray(0x20000)
        ram[0xD1], ram[0xD2] = 2, 4
        s = 0x0E68 + 0x40 * 2
        ram[s], ram[s + 0xA], ram[s + 0xB] = 1, 0x0F, 0
        ram[s + 0xC], ram[s + 0xD] = 0x07, 0xFA
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(bytes(ram), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[s + 0xA] = 0x15
        w = self.p.watcher(plan['watch'])
        w.see(bytes(ram), 0, 'original')
        self.assertEqual(w.result()['state'], 'bad')

    def test_names(self):
        objs = {o['id']: o for o in self.p.objects({'level': 0})}
        self.assertEqual(objs['obj:2']['name'], 'Gun Volt')
        self.assertEqual(objs['obj:1']['does'], 'Rolls along the road toward Mega Man.')
        self.assertEqual(objs['obj:3']['does'], 'Restores 8 life energy.')
        names = [c['name'] for c in objs['obj:1']['fields'][0]['choices']]
        self.assertEqual(names, ['Flying drone (likely)', 'Spiky', 'Gun Volt'])
        self.assertEqual([c['name'] for c in self.p.choices()['items']], ['Large life energy', 'Small life energy', '1-Up'])
        self.assertEqual(self.p.item_does(0x02, 0x82), 'Restores 2 life energy.')
        self.assertEqual(self.p.item_name(0x0B, 0x04), 'Heart Tank')
        self.assertEqual(self.p.enemy_name(0x2D, 0x01), 'Batton Bone, second kind')
        self.assertEqual(self.p.enemy_name(0x0C), 'Stage 4 boss')
        self.assertEqual(self.p.enemy_name(0x4D), 'Dr. Light capsule')
        # a type never seen says where it is and that it was not seen, without its number
        self.assertEqual(self.p.enemy_name(0x62), 'Unplaced enemy, not seen yet')
        for number in range(0x100):
            self.assertNotIn('0x', self.p.enemy_name(number))
            self.assertNotIn('0x', self.p.enemy_name(number, 0x10))
        for o in objs.values():
            self.assertNotIn('0x', o['name'])


def sc4_rom():
    rom = bytearray(0x100000)
    for room in range(68):
        put(rom, 0x00D81B + room * 2, [0x00, 0xF0])
    put(rom, 0x05F000, [0] * 6 + [0xFF, 0xFF])
    put(rom, 0x00D81B, [0x00, 0x80])
    put(rom, 0x058000, [0] * 6
        + [0x81, 0x00, 0xA1, 0x00, 0x02, 0x18]          # candle at $80, $A0 with a small heart
        + [0xA8, 0x02, 0xB8, 0x00, 0x11, 0x00]          # skeleton at $2A8, $B8
        + [0xC8, 0x02, 0xB8, 0x00, 0x0C, 0x00]          # bat at $2C8
        + [0xFF, 0xFF])
    put(rom, 0x00D81B + 2, [0x00, 0x90])
    put(rom, 0x059000, [0] * 6 + [0x40, 0x00, 0x40, 0x00, 0x11, 0x00, 0x60, 0x00, 0x40, 0x00, 0x0C, 0x00, 0xFF, 0xFF])
    return rom


class SuperCastlevania4Test(unittest.TestCase):
    def setUp(self):
        self.p = SuperCastlevania4Profile(bytes(sc4_rom()))

    def test_decode(self):
        objs = self.p.objects({'room': 0})
        self.assertEqual([(o['name'], o['x'], o['y']) for o in objs],
                         [('Candle', 0x80, 0xA0), ('Skeleton', 0x2A8, 0xB8), ('Red bat (likely)', 0x2C8, 0xB8)])
        self.assertEqual(objs[0]['detail'], 'holds small heart')
        self.assertEqual(objs[0]['does'], 'Drops its item when whipped. The item adds 1 heart.')
        self.assertEqual(objs[1]['does'], 'Walks back and forth near you.')
        ram = bytearray(0x20000)
        ram[0x70] = 5
        ram[0x1280], ram[0x1281] = 0x34, 0x01
        self.assertEqual(self.p.where(bytes(ram)), {'part': {'room': 0}, 'x': 0x134, 'y': 0})

    def test_edits(self):
        plan = self.p.edit({'room': 0}, 'obj:0', {'item': 0x1B})
        self.assertEqual(plan['writes'], [(0x28006 + 5, 0x18, 0x1B)])
        plan = self.p.edit({'room': 0}, 'obj:1', {'object': 0x0C00})
        self.assertEqual(plan['writes'], [(0x2800C + 4, 0x11, 0x0C)])
        with self.assertRaises(ValueError):
            self.p.edit({'room': 0}, 'obj:0', {'item': 0x21})
        plan = self.p.edit({'room': 0}, 'obj:1', {}, remove=True)
        rom = bytearray(self.p.rom)
        for o, old, new in plan['writes']:
            rom[o] = new
        self.assertEqual([e['type'] for e in SuperCastlevania4Profile(bytes(rom)).entries(0)], [0x02, 0x0C])

    def test_watcher(self):
        plan = self.p.edit({'room': 0}, 'obj:0', {'item': 0x1B})
        ram = bytearray(0x20000)
        ram[0x70] = 5
        s = 0x0580 + 0x40 * 3
        ram[s + 0x10], ram[s + 0x0A], ram[s + 0x0E], ram[s + 0x14] = 0x0E, 0x80, 0xA0, 0x1B
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(bytes(ram), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[s + 0x14] = 0x18
        w = self.p.watcher(plan['watch'])
        w.see(bytes(ram), 0, 'original')
        self.assertEqual(w.result()['state'], 'bad')
        plan = self.p.edit({'room': 0}, 'obj:2', {}, remove=True)
        w = self.p.watcher(plan['watch'])
        ram[s + 0x10], ram[s + 0x0A], ram[s + 0x0B], ram[s + 0x0E] = 0x0C, 0xC8, 0x02, 0xB8
        self.assertTrue(w.see(bytes(ram), 0, 'original'))
        self.assertEqual(w.result()['state'], 'bad')

    def test_names(self):
        p = self.p
        # every type the profile can name has a name and a does-line, and no name or choice shows a number
        for number, (name, does) in p.NAMES.items():
            self.assertTrue(name and does)
            self.assertNotIn('0x', name)
        for number in range(0x100):
            self.assertNotIn('0x', p.object_name(number))
        self.assertEqual(p.object_name(0x99), 'Unplaced object, not seen yet')
        for option in p.choices()['items']:
            self.assertNotIn('0x', option['name'])
        for o in p.objects({'room': 0}) + p.objects({'room': 1}):
            self.assertNotIn('0x', o['name'])
        self.assertEqual(p.ITEMS[0x65], 'Small meat (second kind)')

    def test_hard_flag_and_kinds(self):
        rom = sc4_rom()
        put(rom, 0x059000, [0] * 6 + [0x40, 0x40, 0x40, 0x00, 0x11, 0x00, 0x62, 0x00, 0x40, 0x00, 0x2B, 0x01,
                                      0x66, 0x00, 0x48, 0x00, 0x2B, 0x00, 0xFF, 0xFF])
        p = SuperCastlevania4Profile(bytes(rom))
        objs = p.objects({'room': 1})
        self.assertEqual(objs[0]['detail'], 'only on the harder setting')
        self.assertEqual([o['name'] for o in objs[1:]], ['Barred gate, second kind', 'Barred gate'])


if __name__ == '__main__':
    unittest.main()
