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

    def test_tile_role(self):
        self.assertIsNone(self.p.tile_role(0))                 # no rule read yet
        ram = bytearray(0x2000)
        ram[0x1058] = 9
        ram[0x1056], ram[0x108A] = 0x69, 0x6E                   # solid below $69, shots stop below $6E
        ram[0x1C00 + 0x1C] = 0x20                               # shots break $1C
        ram[0x1C00 + 0x50] = 0x40                               # bombs break $50
        ram[0x1C00 + 0x6F] = 0x20                               # bit 5 on a tile shots pass through: not breakable
        self.p.where(ram)
        self.assertEqual([self.p.tile_role(t) for t in (0, 3, 4, 0x1C, 0x50, 0x68, 0x69, 0x6F, 0xFF)],
                         ['breakable', 'breakable', 'solid', 'breakable', 'breakable', 'solid', 'open', 'open', 'open'])
        ram[0x1056] = 0x5E                                      # a second graphics set in the same map: no roles
        self.p.where(ram)
        self.assertIsNone(self.p.tile_role(4))


def la_cart():
    """Overworld rooms $B2/$B3 with objects; overworld room $1F with a bombable cave wall; an overworld chest (room
    $41) that the layout does not show. Dungeon map 0 (indoors A): rooms $16 and $17 side by side on the grid's bottom
    row; room $16 has a chest holding a Nightmare's Key, a run of blocks, a bombable left wall, a warp and hidden
    stairs; room $17 has two objects. Every other room is empty."""
    rom = bytearray(32 * 0x4000)
    empty = 0x5000
    put(rom, 0x16, empty, [0xFF])
    for room in range(256):
        for table in (0x4000, 0x4200, 0x4400):
            put(rom, 0x16, table + room * 2, [empty & 0xFF, empty >> 8])
        for bank in (0x09, 0x0A, 0x0B):
            put(rom, bank, 0x4000 + room * 2, [0x00, 0x7F])
    for bank in (0x09, 0x0A, 0x0B, 0x1A):
        put(rom, bank, 0x7F00, [0x00, 0x00, 0xFE])
    put(rom, 0x14, 0x4200 + 7 * 8 + 2, [0x16, 0x17])           # map 0 grid, row 7, columns 2 and 3
    put(rom, 0x16, 0x4200 + 0x17 * 2, [0x40, 0x50])
    put(rom, 0x16, 0x5040, [0x34, 0x61, 0x45, 0x9B, 0xFF])
    put(rom, 0x16, 0x4200 + 0x16 * 2, [0x50, 0x50])
    put(rom, 0x16, 0x5050, [0x23, 0x20, 0xFF])
    put(rom, 0x0A, 0x4000 + 0x16 * 2, [0x00, 0x60])
    # header, chest at $14, a run of three blocks, bombable left wall $41 at $30, warp, hidden stairs $BF at $18
    put(rom, 0x0A, 0x6000, [0x00, 0x00, 0x14, 0xA0, 0x83, 0x21, 0x0D, 0x30, 0x41, 0xE1, 0x10, 0xA3, 0x50, 0x70,
                            0x18, 0xBF, 0xFE])
    put(rom, 0x14, 0x4600 + 0x16, [0x19])                       # chest contents, indoors A room $16
    put(rom, 0x14, 0x4500 + 0x41, [0x11])                       # overworld room $41
    put(rom, 0x14, 0x4700 + 0x05, [0x1B])                       # indoors B room 5 (no chest in its layout)
    put(rom, 0x09, 0x4000 + 0x1F * 2, [0x00, 0x60])
    put(rom, 0x09, 0x6000, [0x00, 0x00, 0x43, 0xBA, 0xFE])
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
        self.assertEqual(len([k for k in objects if k.startswith('obj:')]), 4)
        ram = bytearray(0x2000)
        ram[0x1B54] = 0xB3
        self.assertEqual(self.p.where(ram), {'part': {'map': 'overworld'}, 'x': 480, 'y': 1408})
        ram[0x1BA5] = 1
        self.assertIsNone(self.p.where(ram))                   # indoors needs high RAM

    @staticmethod
    def indoor_ram(room, mp=0, slots=(), blocks=None):
        from romancer.level_profiles import Ram
        raw = bytearray(0x2000)
        raw[0x1BA5] = 1
        for slot, (kind, extra) in enumerate(slots):
            raw[0x280 + slot], raw[0x3A0 + slot], raw[0x3B0 + slot] = 5, kind, extra
        for at, kind in (blocks or {}).items():
            raw[0x1711 + at] = kind
        ram = Ram(bytes(raw))
        hram = bytearray(128)
        hram[0x76], hram[0x77] = room, mp
        ram.domains = {'hram': bytes(hram)}
        return ram

    def test_indoor_where(self):
        self.assertEqual(self.p.where(self.indoor_ram(0x17)), {'part': {'map': 0}, 'x': 3 * 160, 'y': 7 * 128})
        self.assertEqual(self.p.where(self.indoor_ram(0xA8, 0x10)), {'part': {'map': 0x10, 'room': 0xA8}, 'x': 0, 'y': 0})
        self.assertEqual(self.p.part_name({'map': 0}), 'Dungeon map 0')
        self.assertEqual(self.p.part_name({'map': 0x10, 'room': 0xA8}), 'Indoors, map 0x10, room A8')

    def test_dungeon_objects(self):
        objects = {o['id']: o for o in self.p.objects({'map': 0})}
        self.assertEqual(sorted(objects), ['chest:22', 'obj:22:0', 'obj:23:0', 'obj:23:1', 'stairs:22:24', 'wall:22:48'])
        chest = objects['chest:22']
        self.assertEqual((chest['x'], chest['y'], chest['detail']),
                         (2 * 160 + 4 * 16 + 8, 7 * 128 + 16 + 16, "holds Nightmare's Key"))
        self.assertEqual([c['value'] for c in chest['fields'][0]['choices']], [0x11, 0x19, 0x1B])
        self.assertEqual(objects['wall:22:48']['detail'], 'opens the left side')
        self.assertEqual(objects['obj:23:0']['x'], 3 * 160 + 4 * 16 + 8)
        # swaps offer this room's and the grid neighbours' objects
        self.assertEqual([c['value'] for c in objects['obj:22:0']['fields'][0]['choices']], [0x20, 0x61, 0x9B])
        overworld = {o['id']: o for o in self.p.objects({'map': 'overworld'})}
        self.assertIn('not in the room', overworld['chest:65']['note'])
        self.assertNotIn(0x19, [c['value'] for c in overworld['chest:65']['fields'][0]['choices']])
        self.assertEqual(overworld['cave:31:67']['name'], 'Bombable cave entrance')

    def test_indoor_edits(self):
        plan = self.p.edit({'map': 0}, 'chest:22', {'contents': 0x1B})
        self.assertEqual(plan['writes'], [(gba._file(0x14, 0x4616), 0x19, 0x1B)])
        with self.assertRaises(ValueError):
            self.p.edit({'map': 0}, 'chest:22', {'contents': 0x03})           # not a value the game puts in a chest
        with self.assertRaises(ValueError):
            self.p.edit({'map': 'overworld'}, 'chest:65', {'contents': 0x19})  # dungeon items only in dungeons
        plan = self.p.edit({'map': 0}, 'stairs:22:24', {'block': 0xBE})
        self.assertEqual(plan['writes'], [(gba._file(0x0A, 0x600F), 0xBF, 0xBE)])
        plan = self.p.edit({'map': 'overworld'}, 'cave:31:67', {'block': 0xE1})
        self.assertEqual(plan['writes'], [(gba._file(0x09, 0x6003), 0xBA, 0xE1)])
        with self.assertRaises(ValueError):
            self.p.edit({'map': 'overworld'}, 'cave:31:67', {'block': 0x00})
        plan = self.p.edit({'map': 0}, 'obj:23:0', {}, remove=True)
        base = gba._file(0x16, 0x5040)
        self.assertEqual(plan['writes'], [(base, 0x34, 0x45), (base + 1, 0x61, 0x9B), (base + 2, 0x45, 0xFF)])
        self.assertEqual(plan['watch']['group'], 1)
        with self.assertRaises(ValueError):
            self.p.edit({'map': 1}, 'obj:23:0', {}, remove=True)                # not a room of that part

    def test_indoor_watchers(self):
        r = self.indoor_ram
        chest = self.p.watcher(self.p.edit({'map': 0}, 'chest:22', {'contents': 0x1B})['watch'])
        self.assertFalse(chest.see(r(0x16), 2, 'changed'))
        self.assertEqual(chest.result()['state'], 'warn')
        self.assertTrue(chest.see(r(0x16, slots=[(7, 0x1B)]), 4, 'changed'))
        self.assertEqual(chest.result()['state'], 'good')
        control = self.p.watcher(self.p.edit({'map': 0}, 'chest:22', {'contents': 0x1B})['watch'])
        control.see(r(0x16, slots=[(7, 0x19)]), 4, 'changed')
        self.assertEqual(control.result()['state'], 'bad')
        stairs = self.p.watcher(self.p.edit({'map': 0}, 'stairs:22:24', {'block': 0xBE})['watch'])
        stairs.see(r(0x16, blocks={0x18: 0xBE}), 2, 'changed')
        self.assertTrue(stairs.see(r(0x16, blocks={0x18: 0xBE}), 30, 'changed'))
        self.assertEqual(stairs.result()['state'], 'good')
        hidden = self.p.watcher(self.p.edit({'map': 0}, 'stairs:22:24', {'block': 0xBE})['watch'])
        hidden.see(r(0x16, blocks={0x18: 0x0D}), 2, 'changed')
        hidden.see(r(0x16, blocks={0x18: 0x0D}), 30, 'changed')
        self.assertEqual(hidden.result()['state'], 'bad')
        swap = self.p.watcher(self.p.edit({'map': 0}, 'obj:23:0', {'type': 0x9B})['watch'])
        self.assertTrue(swap.compare)
        for run, kinds in (('original', [(0x61, 0), (0x9B, 0)]), ('changed', [(0x9B, 0), (0x9B, 0)])):
            swap.see(r(0x17, slots=kinds), 2, run)
            swap.see(r(0x17, slots=kinds), 60, run)
        self.assertEqual(swap.result()['state'], 'good')
        blind = self.p.watcher(self.p.edit({'map': 0}, 'obj:23:0', {'type': 0x9B})['watch'])
        raw = bytearray(0x2000)
        raw[0x1BA5] = 1
        self.assertFalse(blind.see(bytes(raw), 60, 'changed'))       # no high RAM: indoor rooms are never matched

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
