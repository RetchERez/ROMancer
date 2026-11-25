"""Sonic 3 & Knuckles and Castlevania: Bloodlines level profiles on made-up cartridges with the tables at their real
addresses (no game data beyond the table layouts)."""
import struct
import unittest

from romancer.level_profiles import megadrive_more as mm


def put_w(rom, at, value):
    rom[at:at + 2] = struct.pack('>H', value & 0xFFFF)


def put_l(rom, at, value):
    rom[at:at + 4] = struct.pack('>I', value)


def sonic_rom():
    rom = bytearray(0x400000)
    # code tables: id n -> $10000 + n * $100 (Sonic 3 zones), $20000 + n * $100 (Sonic & Knuckles zones)
    for n in range(256):
        put_l(rom, mm.Sonic3K.TABLE_S3 + 4 * n, 0x10000 + n * 0x100)
        put_l(rom, mm.Sonic3K.TABLE_SK + 4 * n, 0x20000 + n * 0x100)
    objects, rings = 0x300000, 0x310000
    for z in range(0x18):
        for a in range(2):
            put_l(rom, mm.Sonic3K.OBJ_INDEX + z * 8 + a * 4, objects + 0x1000 * (z * 2 + a))
            put_l(rom, mm.Sonic3K.RING_INDEX + z * 8 + a * 4, rings + 0x1000 * (z * 2 + a))
            put_w(rom, objects + 0x1000 * (z * 2 + a), 0xFFFF)
            put_l(rom, rings + 0x1000 * (z * 2 + a), 0)
            put_w(rom, rings + 0x1000 * (z * 2 + a) + 4, 0xFFFF)
    # Angel Island act 1: a monitor (ten rings), a Rhinobot, a Monkey Dude, an unknown object, then the end
    at = objects
    for x, y, i, s in ((0x100, 0x200, 0x01, 3), (0x180, 0x210, 0x8D, 0), (0x200, 0x220, 0x8E, 0x10), (0x280, 0x230, 0x07, 1)):
        put_w(rom, at, x); put_w(rom, at + 2, y); rom[at + 4] = i; rom[at + 5] = s
        at += 6
    put_w(rom, at, 0xFFFF)
    # three rings
    at = rings + 4
    for x, y in ((0x120, 0x300), (0x140, 0x300), (0x160, 0x300)):
        put_w(rom, at, x); put_w(rom, at + 2, y)
        at += 4
    put_w(rom, at, 0xFFFF)
    return bytes(rom)


def ram_with(values):
    ram = bytearray(0x10000)
    for at, (size, value) in values.items():
        ram[at:at + size] = value.to_bytes(size, 'big')
    return bytes(ram)


class Sonic3KTest(unittest.TestCase):
    def setUp(self):
        self.p = mm.Sonic3K(sonic_rom())
        self.part = {'zone': 0, 'act': 0}

    def test_where(self):
        ram = ram_with({0xF600: (1, 0x0C), 0xFE10: (2, 0x0001), 0xEE78: (2, 0x1234), 0xEE7C: (2, 0x300)})
        self.assertEqual(self.p.where(ram), {'part': {'zone': 0, 'act': 1}, 'x': 0x1234, 'y': 0x300})
        self.assertIsNone(self.p.where(ram_with({0xF600: (1, 0x08)})))
        self.assertEqual(self.p.part_name({'zone': 0x16, 'act': 1}), 'Hidden Palace Zone')
        self.assertEqual(self.p.part_name({'zone': 3, 'act': 1}), 'Carnival Night Zone, act 2')

    def test_objects(self):
        objs = {o['id']: o for o in self.p.objects(self.part)}
        self.assertEqual(objs['object:0']['name'], 'Monitor')
        self.assertEqual(objs['object:0']['detail'], 'holds ten rings')
        self.assertEqual(objs['object:1']['name'], 'Rhinobot')
        self.assertEqual(objs['object:2']['name'], 'Monkey Dude')
        self.assertEqual(objs['object:3']['style'], 'block')
        self.assertEqual(sum(1 for o in objs.values() if o['type'] == 'ring'), 3)
        choices = self.p.choices()['enemies_0_0']
        self.assertEqual([c['value'] for c in choices], [0x8D00, 0x8E10])

    def test_monitor_and_swap(self):
        e = self.p.edit(self.part, 'object:0', {'contents': 8})
        self.assertEqual(e['writes'], [(0x300005, 3, 8)])
        self.assertEqual(e['watch']['kind'], 'monitor')
        e = self.p.edit(self.part, 'object:1', {'enemy': 0x8E10})
        self.assertEqual(e['writes'], [(0x30000A, 0x8D, 0x8E), (0x30000B, 0, 0x10)])
        self.assertEqual(e['watch']['range'], [0x18E00, 0x18F00])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:1', {'enemy': 0x9000})
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:0', {'contents': 9})

    def test_removal_not_offered(self):
        objs = self.p.objects(self.part)
        self.assertTrue(all(o['remove'] is None for o in objs))
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:1', {}, True)

    def test_where_uses_the_scroll_the_picture_used(self):
        from romancer.level_profiles import Ram
        ram = Ram(ram_with({0xF600: (1, 0x0C), 0xFE10: (2, 0), 0xEE78: (2, 0x1240), 0xEE7C: (2, 0x300)}))
        vram = bytearray(0x10000)
        put_w(vram, 0xF000, -0x1234)
        ram.domains = {'vram': bytes(vram), 'vsram': bytes([0x02, 0xFE]) + bytes(78)}
        self.assertEqual(self.p.where(ram), {'part': {'zone': 0, 'act': 0}, 'x': 0x1234, 'y': 0x2FE})
        put_w(vram, 0xF000, 0)              # far from the camera: not the level's scroll, so the camera is kept
        ram.domains['vram'] = bytes(vram)
        self.assertEqual(self.p.where(ram)['x'], 0x1240)

    def test_remove_closes_the_list(self):
        self.p.REMOVAL = True
        e = self.p.edit(self.part, 'object:1', {}, True)
        rom = bytearray(self.p.rom)
        for at, old, new in e['writes']:
            self.assertEqual(rom[at], old)
            rom[at] = new
        after = mm.Sonic3K(bytes(rom)).records(0, 0)
        self.assertEqual([r['id'] for r in after], [0x01, 0x8E, 0x07])
        e = self.p.edit(self.part, 'ring:1', {}, True)
        rom = bytearray(self.p.rom)
        for at, old, new in e['writes']:
            rom[at] = new
        self.assertEqual([r['x'] for r in mm.Sonic3K(bytes(rom)).rings(0, 0)], [0x120, 0x160])

    def test_watchers(self):
        e = self.p.edit(self.part, 'object:1', {'enemy': 0x8E10})
        w = self.p.watcher(e['watch'])
        slot = mm.Sonic3K.SLOTS[0]
        ram = ram_with({0xF600: (1, 0x0C), 0xFE10: (2, 0), slot: (4, 0x18E40), slot + 0x48: (2, 0xEB01)})
        self.assertTrue(w.see(ram, 2, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(e['watch'])
        ram = ram_with({0xF600: (1, 0x0C), 0xFE10: (2, 0), slot: (4, 0x18D10), slot + 0x48: (2, 0xEB01)})
        self.assertTrue(w.see(ram, 2, 'changed'))
        self.assertEqual(w.result()['state'], 'bad')
        # an enemy removal: one fewer of that kind than the unchanged game at the same frames
        self.p.REMOVAL = True
        e = self.p.edit(self.part, 'object:1', {}, True)
        w = self.p.watcher(e['watch'])
        self.assertTrue(w.compare)
        other = slot + 0x4A
        both = ram_with({0xF600: (1, 0x0C), 0xFE10: (2, 0), slot: (4, 0x18D10), slot + 0x48: (2, 0xEB01),
                         other: (4, 0x18D20), other + 0x48: (2, 0xEB05)})
        one = ram_with({0xF600: (1, 0x0C), 0xFE10: (2, 0), other: (4, 0x18D20), other + 0x48: (2, 0xEB05)})
        for f in range(2, 62, 2):
            w.see(both, f, 'original')
        for f in range(2, 62, 2):
            if w.see(one, f, 'changed'):
                break
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(e['watch'])
        for f in range(2, 62, 2):
            w.see(both, f, 'original')
        for f in range(2, 62, 2):
            if w.see(both, f, 'changed'):
                break
        self.assertEqual(w.result()['state'], 'bad')
        # a ring removal: one ring fewer in the window than the unchanged game at the same frame and camera
        e = self.p.edit(self.part, 'ring:1', {}, True)
        w = self.p.watcher(e['watch'])
        self.assertTrue(w.compare)
        start = 0x310004
        for f in range(2, 42, 2):
            w.see(ram_with({0xF600: (1, 0x0C), 0xEE78: (2, 0x100), 0xEE42: (4, start), 0xEE46: (4, start + 12)}), f, 'original')
        for f in range(2, 42, 2):
            if w.see(ram_with({0xF600: (1, 0x0C), 0xEE78: (2, 0x100), 0xEE42: (4, start), 0xEE46: (4, start + 8)}), f, 'changed'):
                break
        self.assertEqual(w.result()['state'], 'good')


def bloodlines_rom():
    rom = bytearray(0x100000)
    base = mm.Bloodlines.INDEX
    lists = base + 0x200
    for n in range(mm.Bloodlines.ROOMS):
        put_w(rom, base + 2 * n, lists - base)
    at = lists
    records = ((0x8000, 0x19, 0, 0, 0, 0x03), (0x0040, 0x14, 4, 0x40, 0, 0x23), (0x0089, 0x77, 0x10, 0x9A, 2, 0x22),
               (0x0100, 0x77, 0x31, 0x80, 1, 0x22), (0x7FFF, 0x19, 0, 0x80, 0, 0x03))
    for x, kind, setting, y, extra, flags in records:
        put_w(rom, at, x); rom[at + 2] = kind; rom[at + 3] = setting; put_w(rom, at + 4, y); rom[at + 6] = extra; rom[at + 7] = flags
        at += 8
    return bytes(rom), lists


class BloodlinesTest(unittest.TestCase):
    def setUp(self):
        rom, self.lists = bloodlines_rom()
        self.p = mm.Bloodlines(rom)
        self.part = {'room': 0}

    def test_where_and_names(self):
        ram = ram_with({0x9002: (2, 9), 0x9264: (2, 1), 0x9122: (2, 12), 0x9220: (2, 0x80), 0x9234: (2, 0xFF00)})
        self.assertEqual(self.p.where(ram), {'part': {'room': 12}, 'x': 0x80, 'y': 0x100})
        self.assertIsNone(self.p.where(ram_with({0x9002: (2, 9), 0x9264: (2, 0xFFFF)})))
        self.assertEqual(self.p.part_name({'room': 12}), 'Stage 2 (Atlantis Shrine), room 2')

    def test_objects(self):
        objs = self.p.objects(self.part)
        self.assertEqual([o['name'] for o in objs], ['Enemy 0x14', 'Candle', 'Candle'])
        self.assertEqual(objs[1]['detail'], 'drops small red gem')
        self.assertIn('whip power-up', objs[1]['note'])
        self.assertEqual(objs[2]['detail'], 'drops money bag (setting 0x31)')
        self.assertEqual(objs[1]['x'], 0x89)

    def test_edits(self):
        e = self.p.edit(self.part, 'object:1', {'contents': 0xB1})
        self.assertEqual(e['writes'], [(self.lists + 16 + 3, 0x10, 0xB1)])
        with self.assertRaises(ValueError):          # removal is not offered yet
            self.p.edit(self.part, 'object:1', {}, True)
        self.assertTrue(all(o['remove'] is None for o in self.p.objects(self.part)))
        self.p.REMOVAL = True
        e2 = self.p.edit(self.part, 'object:1', {}, True)
        self.assertEqual(e2['writes'], [(self.lists + 16 + 2, 0x77, 0x03)])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:0', {}, True)
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:1', {'contents': 0x11})
        # the watcher finds the candle by its remember number (n + 2) and reads its setting
        w = self.p.watcher(e['watch'])
        slot = 0xBC80
        ram = ram_with({0x9002: (2, 9), 0x9264: (2, 1), slot: (2, 1), slot + 0x16: (2, 0x77), slot + 0x4C: (1, 3), slot + 0x53: (1, 0xB1)})
        self.assertTrue(w.see(ram, 2, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        # a removal compares with the unchanged game: the candle must be missing at the frames it was there
        empty = ram_with({0x9002: (2, 9), 0x9264: (2, 1), 0x9220: (2, 0x40)})
        for after, state in ((empty, 'good'), (ram, 'bad')):
            w = self.p.watcher(e2['watch'])
            self.assertTrue(w.compare)
            for f in range(0, 80, 2):
                w.see(ram, f, 'original')
            for f in range(0, 80, 2):
                if w.see(after, f, 'changed'):
                    break
            self.assertEqual(w.result()['state'], state)
        self.assertEqual(self.p.CONTENTS[0x70], 'Silver disc')
        self.assertEqual(self.p.CONTENTS[0x90], 'Dark orb')


if __name__ == '__main__':
    unittest.main()
