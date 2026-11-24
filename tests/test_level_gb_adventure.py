"""Game Boy adventure profiles (Metroid II, Link's Awakening): decoders and edits on made-up cartridges laid out like
the real ones. The real games are not part of the tests; what the tables mean was proven by replaying the real games
(research/gb_adventure-level-profile.md)."""
import unittest

from romancer.level_profiles import gb_adventure as gba


def put(rom, bank, address, data):
    o = gba._file(bank, address)
    rom[o:o + len(data)] = bytes(data)


def m2_cart():
    """Map 9 screen $27: three records; screen $26: an item sphere; screen $37: a missile tank. Every other screen
    points at an empty list. Object headers at $6300 give hit points (byte 8) and the code pointer (bytes 9-10)."""
    rom = bytearray(16 * 0x4000)
    empty = 0x5100
    put(rom, 3, empty, [0xFF])
    for area in range(9, 16):
        for screen in range(256):
            put(rom, 3, 0x42E0 + (area - 9) * 0x200 + screen * 2, [empty & 0xFF, empty >> 8])
    lists = {0x27: (0x5110, [[0x23, 0x12, 0xA0, 0xC0], [0x24, 0x12, 0xC0, 0x70], [0x25, 0x16, 0xE0, 0x20]]),
             0x26: (0x5130, [[0x63, 0x88, 0x5C, 0x60]]),
             0x37: (0x5140, [[0x66, 0x99, 0x48, 0x18], [0x41, 0xA3, 0x80, 0x80]])}
    for screen, (address, records) in lists.items():
        put(rom, 3, 0x42E0 + screen * 2, [address & 0xFF, address >> 8])
        put(rom, 3, address, [b for r in records for b in r] + [0xFF])
    for kind in range(256):
        header = 0x6600 + kind * 11
        put(rom, 3, 0x6300 + kind * 2, [header & 0xFF, header >> 8])
        put(rom, 3, header, [0] * 8 + [10 if kind == 0xA3 else 1, kind, 0x50])
    return bytes(rom)


class MetroidIITest(unittest.TestCase):
    def setUp(self):
        self.rom = m2_cart()
        self.p = gba.MetroidII(self.rom)

    def test_records_and_objects(self):
        rows = self.p.records(9, 0x27)
        self.assertEqual([(r['type'], r['x'], r['y']) for r in rows], [(0x12, 0xA0, 0xC0), (0x12, 0xC0, 0x70), (0x16, 0xE0, 0x20)])
        objects = {o['id']: o for o in self.p.objects({'area': 9})}
        first = objects['obj:39:0']
        self.assertEqual((first['x'], first['y']), (7 * 256 + 0xA0, 2 * 256 + 0xC0 + 8))
        self.assertEqual(first['style'], 'enemy')
        sphere = objects['obj:38:0']
        self.assertEqual((sphere['style'], sphere['detail']), ('item', 'holds Bombs'))
        self.assertEqual(objects['obj:55:0']['name'], 'Missile Tank')
        self.assertEqual(objects['obj:55:1']['name'], 'Gamma Metroid')
        self.assertEqual(objects['obj:55:1']['detail'], '10 hit points')
        self.assertEqual(self.p.objects({'area': 10}), [])

    def test_where(self):
        ram = bytearray(0x2000)
        ram[0x1058] = 9
        ram[0x1027], ram[0x1028], ram[0x1029], ram[0x102A] = 1614 & 0xFF, 1614 >> 8, 2004 & 0xFF, 2004 >> 8
        ram[0x206], ram[0x205] = (1614 - 84) & 0xFF, (2004 - 92) & 0xFF
        self.assertEqual(self.p.where(ram), {'part': {'area': 9}, 'x': 1530, 'y': 1912})
        ram[0x1058] = 3
        self.assertIsNone(self.p.where(ram))

    def test_choices(self):
        enemies = [c['value'] for c in self.p.type_choices(9, 0x27, 0x12)]
        self.assertEqual(enemies, [0x12, 0x16, 0xA3])           # this screen and its neighbours, no items
        spheres = [c['value'] for c in self.p.type_choices(9, 0x26, 0x88)]
        self.assertEqual(spheres, list(range(0x80, 0x96, 2)))
        loose = [c['value'] for c in self.p.type_choices(9, 0x37, 0x99)]
        self.assertEqual(loose, [0x97, 0x99, 0x9B, 0x9D])

    def test_swap_writes_one_byte(self):
        plan = self.p.edit({'area': 9}, 'obj:39:1', {'type': 0x16})
        offset = gba._file(3, 0x5110 + 4 + 1)
        self.assertEqual(plan['writes'], [(offset, 0x12, 0x16)])
        self.assertEqual(plan['watch']['number'], 0x24)
        plan = self.p.edit({'area': 9}, 'obj:38:0', {'type': 0x82})
        self.assertEqual(plan['writes'], [(gba._file(3, 0x5131), 0x88, 0x82)])
        self.assertIn('Ice Beam', plan['title'])
        with self.assertRaises(ValueError):
            self.p.edit({'area': 9}, 'obj:39:1', {'type': 0x99})

    def test_remove_moves_last_record(self):
        plan = self.p.edit({'area': 9}, 'obj:39:0', {}, remove=True)
        base = gba._file(3, 0x5110)
        self.assertEqual(plan['writes'], [(base, 0x23, 0x25), (base + 1, 0x12, 0x16), (base + 2, 0xA0, 0xE0),
                                          (base + 3, 0xC0, 0x20), (base + 8, 0x25, 0xFF)])
        changed = bytearray(self.rom)
        for o, _, n in plan['writes']:
            changed[o] = n
        rows = gba.MetroidII(bytes(changed)).records(9, 0x27)
        self.assertEqual([r['number'] for r in rows], [0x25, 0x24])
        last = self.p.edit({'area': 9}, 'obj:39:2', {}, remove=True)
        self.assertEqual(last['writes'], [(base + 8, 0x25, 0xFF)])

    def test_watcher(self):
        plan = self.p.edit({'area': 9}, 'obj:39:1', {'type': 0x16})

        def ram_with(kind, code):
            ram = bytearray(0x2000)
            ram[0x1058] = 9
            x, y = 7 * 256 + 0x60, 2 * 256 + 0x40
            ram[0x1027], ram[0x1028], ram[0x1029], ram[0x102A] = x & 0xFF, x >> 8, y & 0xFF, y >> 8
            ram[0x206], ram[0x205] = (x - 80) & 0xFF, (y - 72) & 0xFF
            for slot in range(16):
                ram[0x600 + slot * 32] = 0xFF
            ram[0x600], ram[0x603], ram[0x61D], ram[0x61E], ram[0x61F] = 0, kind, 0x24, code, 0x50
            return ram
        good = self.p.watcher(plan['watch'])
        self.assertTrue(good.see(ram_with(0x17, 0x16), 2, 'changed'))      # animating type, same code as 0x16
        self.assertEqual(good.result()['state'], 'good')
        bad = self.p.watcher(plan['watch'])
        bad.see(ram_with(0x12, 0x12), 2, 'changed')
        self.assertEqual(bad.result()['state'], 'bad')
        self.assertEqual(self.p.watcher(plan['watch']).result()['state'], 'warn')
        removal = self.p.watcher(self.p.edit({'area': 9}, 'obj:39:1', {}, remove=True)['watch'])
        self.assertTrue(removal.compare)
        removal.see(ram_with(0x12, 0x12), 2, 'original')
        empty = ram_with(0x12, 0x12)
        empty[0x600] = 0xFF
        removal.see(empty, 2, 'changed')
        self.assertEqual(removal.result()['state'], 'good')


def la_cart():
    rom = bytearray(32 * 0x4000)
    empty = 0x5000
    put(rom, 0x16, empty, [0xFF])
    for room in range(256):
        put(rom, 0x16, 0x4000 + room * 2, [empty & 0xFF, empty >> 8])
    put(rom, 0x16, 0x4000 + 0xB3 * 2, [0x10, 0x50])
    put(rom, 0x16, 0x5010, [0x34, 0x6E, 0x45, 0x6E, 0x56, 0x6F, 0xFF])
    put(rom, 0x16, 0x4000 + 0xB2 * 2, [0x20, 0x50])
    put(rom, 0x16, 0x5020, [0x23, 0x6C, 0xFF])
    return bytes(rom)


class LinksAwakeningTest(unittest.TestCase):
    def setUp(self):
        self.rom = la_cart()
        self.p = gba.LinksAwakening(self.rom)

    def test_objects_and_where(self):
        objects = {o['id']: o for o in self.p.objects({'map': 'overworld'})}
        o = objects['obj:179:0']
        self.assertEqual((o['x'], o['y'], o['type']), (3 * 160 + 4 * 16 + 8, 11 * 128 + 3 * 16 + 16, 0x6E))
        self.assertEqual(len(objects), 4)
        ram = bytearray(0x2000)
        ram[0x1B54] = 0xB3
        self.assertEqual(self.p.where(ram), {'part': {'map': 'overworld'}, 'x': 480, 'y': 1408})
        ram[0x1BA5] = 1
        self.assertIsNone(self.p.where(ram))

    def test_edits(self):
        plan = self.p.edit({'map': 'overworld'}, 'obj:179:1', {'type': 0x6C})
        self.assertEqual(plan['writes'], [(gba._file(0x16, 0x5013), 0x6E, 0x6C)])
        with self.assertRaises(ValueError):
            self.p.edit({'map': 'overworld'}, 'obj:179:1', {'type': 0x40})
        plan = self.p.edit({'map': 'overworld'}, 'obj:179:0', {}, remove=True)
        base = gba._file(0x16, 0x5010)
        self.assertEqual(plan['writes'], [(base, 0x34, 0x56), (base + 1, 0x6E, 0x6F), (base + 4, 0x56, 0xFF)])

    def test_watcher(self):
        plan = self.p.edit({'map': 'overworld'}, 'obj:179:1', {'type': 0x6C})
        w = self.p.watcher(plan['watch'])

        def ram_with(types):
            ram = bytearray(0x2000)
            ram[0x1B54] = 0xB3
            for slot, kind in enumerate(types):
                ram[0x280 + slot], ram[0x3A0 + slot] = 5, kind
            return ram
        self.assertFalse(w.see(ram_with([0x6E, 0x6E, 0x6F]), 10, 'original'))
        self.assertTrue(w.see(ram_with([0x6E, 0x6E, 0x6F]), 60, 'original'))
        w.see(ram_with([0x6E, 0x6C, 0x6F]), 10, 'changed')
        w.see(ram_with([0x6E, 0x6C, 0x6F]), 60, 'changed')
        self.assertEqual(w.result()['state'], 'good')
        control = self.p.watcher(plan['watch'])
        for run in ('original', 'changed'):
            control.see(ram_with([0x6E, 0x6E, 0x6F]), 10, run)
            control.see(ram_with([0x6E, 0x6E, 0x6F]), 60, run)
        self.assertEqual(control.result()['state'], 'bad')


if __name__ == '__main__':
    unittest.main()
