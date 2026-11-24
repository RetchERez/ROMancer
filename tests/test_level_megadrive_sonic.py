"""Sonic The Hedgehog and Sonic The Hedgehog 2 object layouts: decoding and edits on made-up cartridges that have the
games' tables at their real addresses (nothing else of the games)."""
import unittest

from romancer.level_profiles.megadrive_sonic import Sonic1, Sonic2


def word(value):
    return bytes([value >> 8 & 0xFF, value & 0xFF])


def record(x, y, ident, sub):
    return word(x) + word(y) + bytes([ident, sub])


def sonic1_rom():
    rom = bytearray(0x80000)
    index = Sonic1.INDEX
    # Green Hill act 1: rings, a monitor, a Moto Bug, a spring, a Crabmeat; act 2: a Buzz Bomber; the rest empty
    first = 0x100
    lists = {(0, 0): record(0x144, 0x360, 0xA5, 0x12) + record(0x248, 0x351, 0xA6, 0x06) + record(0x340, 0x3AC, 0xC0, 0x00)
             + record(0x334, 0x4328, 0x41, 0x02) + record(0x8B0, 0x350, 0x9F, 0x00),
             (0, 1): record(0x420, 0x330, 0xA2, 0x00)}
    empty = first - 6
    rom[index + empty:index + empty + 6] = word(0xFFFF) + bytes(4)
    at = first
    starts = {}
    for key, body in lists.items():
        starts[key] = at
        rom[index + at:index + at + len(body) + 6] = body + word(0xFFFF) + bytes(4)
        at += len(body) + 6
    for zone in range(7):
        for act in range(4):
            entry = index + zone * 16 + act * 4
            rom[entry:entry + 2] = word(starts.get((zone, act), starts[(0, 0)] if act == 3 and zone == 0 else empty))
            rom[entry + 2:entry + 4] = word(empty)
    return bytes(rom)


def sonic2_rom():
    rom = bytearray(0x100000)
    index, rings = Sonic2.INDEX, Sonic2.RING_INDEX
    body = record(0x100, 0x2B0, 0x26, 0x04) + record(0x200, 0x2B0, 0x9D, 0x1E) + record(0x300, 0x82B0, 0x41, 0x00)
    empty = 0x44 + 0x10
    rom[index + empty:index + empty + 2] = word(0xFFFF)
    rom[index + 0x46:index + 0x46 + len(body) + 2] = body + word(0xFFFF)
    for n in range(34):
        rom[index + 2 * n:index + 2 * n + 2] = word(0x46 if n == 0 else empty)
    ring_body = word(0x124) + word(0x2240) + word(0x230) + word(0x91E0) + word(0x400) + word(0x0300)
    rom[rings + 0x44:rings + 0x44 + len(ring_body) + 2] = ring_body + word(0xFFFF)
    rom[rings + 0x60:rings + 0x62] = word(0xFFFF)
    for n in range(34):
        rom[rings + 2 * n:rings + 2 * n + 2] = word(0x44 if n == 0 else 0x60)
    return bytes(rom)


def ram_with(mode=0x0C, zone=0, act=0, camera=(0, 0), objects=(), base=0):
    ram = bytearray(0x10000)
    ram[0xF600] = mode
    ram[0xFE10], ram[0xFE11] = zone, act
    return ram


class Sonic1Tests(unittest.TestCase):
    def setUp(self):
        self.p = Sonic1(sonic1_rom())
        self.part = {'zone': 0, 'act': 0}

    def test_records(self):
        rows = self.p.records(0, 0)
        self.assertEqual([(r['x'], r['y'], r['id'], r['sub']) for r in rows],
                         [(0x144, 0x360, 0x25, 0x12), (0x248, 0x351, 0x26, 6), (0x340, 0x3AC, 0x40, 0), (0x334, 0x328, 0x41, 2), (0x8B0, 0x350, 0x1F, 0)])
        self.assertEqual(rows[3]['flags'], 1)
        self.assertTrue(rows[0]['remember'])
        self.assertFalse(rows[3]['remember'])

    def test_where(self):
        ram = ram_with(zone=0, act=1)
        ram[0xF700:0xF704] = word(0x1234) + word(0)
        ram[0xF704:0xF706] = word(0x300)
        self.assertEqual(self.p.where(ram), {'part': {'zone': 0, 'act': 1}, 'x': 0x1234, 'y': 0x300})
        self.assertIsNone(self.p.where(ram_with(mode=0x08)))       # the attract demo
        self.assertIsNone(self.p.where(ram_with(zone=0, act=3)))   # Green Hill has no fourth act
        self.assertEqual(self.p.part_name({'zone': 1, 'act': 3}), 'Scrap Brain Zone, act 3')
        self.assertEqual(self.p.part_name({'zone': 5, 'act': 2}), 'Final Zone')

    def test_objects(self):
        rows = {o['id']: o for o in self.p.objects(self.part)}
        self.assertEqual(rows['object:0']['name'], 'Rings')
        self.assertEqual(rows['object:0']['detail'], 'a row of 3')
        self.assertEqual(rows['object:1']['detail'], 'holds ten rings')
        self.assertEqual(rows['object:2']['style'], 'enemy')
        self.assertEqual(rows['object:2']['name'], 'Moto Bug')
        self.assertEqual(rows['object:3']['name'], 'Spring')
        self.assertIsNone(rows['object:3']['remove'])
        enemies = self.p.choices()['enemies_0']
        self.assertEqual([c['value'] for c in enemies], [0x4000, 0x1F00, 0x2200])

    def test_edits(self):
        offset = self.p.list_start(0, 0)
        plan = self.p.edit(self.part, 'object:1', {'contents': 5})
        self.assertEqual(plan['writes'], [(offset + 6 + 5, 6, 5)])
        plan = self.p.edit(self.part, 'object:2', {'enemy': 0x1F00})
        self.assertEqual(plan['writes'], [(offset + 12 + 4, 0xC0, 0x9F)])
        plan = self.p.edit(self.part, 'object:2', {}, remove=True)
        self.assertEqual(plan['writes'], [(offset + 12 + 4, 0xC0, 0x80)])     # id 0, the remember bit kept
        plan = self.p.edit(self.part, 'object:0', {'count': 6})
        self.assertEqual(plan['writes'], [(offset + 5, 0x12, 0x16)])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:2', {'enemy': 0x2C00})            # Jaws: not a Green Hill enemy
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:3', {}, remove=True)              # springs stay

    def test_watchers(self):
        plan = self.p.edit(self.part, 'object:1', {'contents': 5})
        ram = ram_with()
        slot = 0xD800 + 0x40 * 3
        ram[slot] = 0x26
        ram[slot + 8:slot + 10], ram[slot + 0xC:slot + 0xE] = word(0x248), word(0x351)
        ram[slot + 0x28] = 5
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 10, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[slot + 0x28] = 6
        w = self.p.watcher(plan['watch'])
        w.see(ram, 10, 'changed')
        self.assertEqual(w.result()['state'], 'bad')
        # a removal: camera over the place long enough with no Moto Bug there
        plan = self.p.edit(self.part, 'object:2', {}, remove=True)
        ram = ram_with()
        ram[0xF700:0xF702], ram[0xF704:0xF706] = word(0x300), word(0x300)
        w = self.p.watcher(plan['watch'])
        self.assertFalse(any(w.see(ram, f, 'changed') for f in range(10)))
        self.assertEqual(w.result()['state'], 'warn')
        while not w.see(ram, 0, 'changed'):
            pass
        self.assertEqual(w.result()['state'], 'good')
        ram[slot] = 0x40
        ram[slot + 8:slot + 10], ram[slot + 0xC:slot + 0xE] = word(0x350), word(0x3AC)
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'bad')
        # rings: count the ring objects whose parent x is the record's
        plan = self.p.edit(self.part, 'object:0', {'count': 6})
        ram = ram_with()
        for n in range(7):
            s = 0xD800 + 0x40 * n
            ram[s] = 0x25
            ram[s + 0x32:s + 0x34], ram[s + 0xC:s + 0xE] = word(0x144), word(0x360)
            ram[s + 0x34] = n
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')


class Sonic2Tests(unittest.TestCase):
    def setUp(self):
        self.p = Sonic2(sonic2_rom())
        self.part = {'zone': 0, 'act': 0}

    def test_records(self):
        rows = self.p.records(0, 0)
        self.assertEqual([(r['x'], r['y'], r['id'], r['sub'], r['remember']) for r in rows],
                         [(0x100, 0x2B0, 0x26, 4, False), (0x200, 0x2B0, 0x9D, 0x1E, False), (0x300, 0x2B0, 0x41, 0, True)])
        self.assertEqual(self.p.ring_groups(0, 0)[1], {'n': 1, 'offset': Sonic2.RING_INDEX + 0x48, 'x': 0x230, 'y': 0x1E0, 'count': 2, 'vertical': True})

    def test_where(self):
        ram = ram_with(zone=0, act=1)
        ram[0xEE00:0xEE02], ram[0xEE04:0xEE06] = word(0x500), word(0x280)
        self.assertEqual(self.p.where(ram), {'part': {'zone': 0, 'act': 1}, 'x': 0x500, 'y': 0x280})
        self.assertIsNone(self.p.where(ram_with(zone=1)))

    def test_edits(self):
        offset = self.p.list_start(0, 0)
        self.assertEqual(self.p.edit(self.part, 'object:0', {'contents': 6})['writes'], [(offset + 5, 4, 6)])
        self.assertEqual(self.p.edit(self.part, 'object:1', {}, remove=True)['writes'], [(offset + 6 + 4, 0x9D, 0)])
        rings = Sonic2.RING_INDEX + 0x44
        plan = self.p.edit(self.part, 'rings:0', {'count': 4})
        self.assertEqual(plan['writes'], [(rings + 2, 0x22, 0x42)])
        plan = self.p.edit(self.part, 'rings:1', {'count': 0})
        self.assertEqual(plan['writes'], [(rings + 6, 0x91, 0x81)])
        plan = self.p.edit(self.part, 'rings:0', {}, remove=True)
        # the list closes up over the removed group and ends one record sooner
        after = bytearray(self.p.rom)
        for at, old, new in plan['writes']:
            self.assertEqual(after[at], old)
            after[at] = new
        self.assertEqual(bytes(after[rings:rings + 10]), word(0x230) + word(0x91E0) + word(0x400) + word(0x0300) + word(0xFFFF))

    def test_ring_watcher(self):
        plan = self.p.edit(self.part, 'rings:0', {'count': 4})
        ram = ram_with()
        table = Sonic2.RING_TABLE
        for n in range(5):
            at = table + 6 * n
            ram[at + 2:at + 4], ram[at + 4:at + 6] = word(0x124 + 0x18 * n), word(0x240)
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[table + 6 * 4 + 2:table + 6 * 4 + 6] = bytes(4)
        w = self.p.watcher(plan['watch'])
        w.see(ram, 0, 'changed')
        self.assertEqual(w.result()['state'], 'bad')


if __name__ == '__main__':
    unittest.main()
