"""Mega Man level profiles on made-up cartridges that have the games' tables at their real addresses."""
from __future__ import annotations

import unittest

from romancer.level_profiles import megaman as mm


def put(rom, bank, address, data):
    at = mm.HEADER + bank * 0x4000 + (address - (0xC000 if address >= 0xC000 else 0x8000))
    rom[at:at + len(data)] = bytes(data)
    return at


def cart1():
    """Mega Man: stage 1 (Ice Man) with two sections and five records, one of them a graphics load."""
    rom = bytearray(mm.HEADER + 8 * 0x4000)
    put(rom, 7, 0xC2EB + 1, [0])                      # first screen
    put(rom, 5, 0x93A0 + 1, [2])                      # first segment
    put(rom, 1, 0x8C71 + 2, [0x41, 0x20, 0x00])       # 2 screens then down, 1 screen then right, boss room
    put(rom, 6, 0xA452 + 2, [0x00, 0xA5])             # stage 1 list at $A500
    put(rom, 6, 0xA500, [0x00, 0x80, 0x90, 0x03,      # Met on screen 0
                         0x01, 0x10, 0x40, 0x07,      # Peng on screen 1
                         0x01, 0x40, 0x02, 0xFF,      # loads graphics: not editable
                         0x02, 0x20, 0xB0, 0x40,      # large life energy, section 2
                         0x02, 0x60, 0xB0, 0x03,
                         0xFF])
    put(rom, 5, 0x93C3 + 1, [0xFF])                   # restart points of stage 1: start, middle, boss
    put(rom, 5, 0x93C3 + 13, [2])
    put(rom, 5, 0x93C3 + 25, [0])
    return rom


def cart2():
    """Mega Man 2: Air Man (stage 1, bank 1) and Wily stage 2 (stage 9) share bank 1."""
    rom = bytearray(mm.HEADER + 16 * 0x4000)
    put(rom, 1, 0xB400, [0x41, 0x00, 0x80, 0x00])     # Air Man: 2 screens down, boss; Wily 2: 1 screen up, boss
    put(rom, 1, 0xBB06, [0, 1, 2, 3, 3, 3])           # restart screens (3 = Wily stage 2 start)
    put(rom, 1, 0xBB0C, [0, 1, 2, 2, 3, 3])           # enemy records behind each restart point
    put(rom, 1, 0xBB12, [0, 0, 1, 1, 1, 1])           # item records behind
    put(rom, 1, 0xBB30, [0, 0, 1, 2, 2, 2])           # segments
    for address, values in ((0xB600, [0, 1, 3, 0xFF]), (0xB700, [0x30, 0x50, 0x70, 0xFF]),
                            (0xB800, [0x80, 0x90, 0xA0, 0xFF]), (0xB900, [0x21, 0x30, 0x21, 0xFF]),
                            (0xBA00, [1, 3, 0xFF]), (0xBA40, [0x40, 0x20, 0xFF]), (0xBA80, [0x60, 0x70, 0xFF]),
                            (0xBAC0, [0x7A, 0x7B, 0xFF])):
        put(rom, 1, address, values)
    return rom


class MegaMan1Test(unittest.TestCase):
    def setUp(self):
        self.rom = cart1()
        self.p = mm.MegaMan1(bytes(self.rom))

    def test_sections_and_links(self):
        sections = self.p.sections(1)
        self.assertEqual([(s['first'], s['last'], s['link']) for s in sections], [(0, 1, 0x40), (2, 2, 0x20), (3, 3, 0)])
        links = [o for o in self.p.objects({'stage': 1, 'section': 0}) if o['style'] == 'block']
        self.assertEqual(links[0]['name'], 'Way down to the next section')

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'stage': 1, 'section': 0}) if o['style'] != 'block'}
        self.assertEqual(sorted(objects), ['record:0', 'record:1'])           # the graphics record is left out
        self.assertEqual((objects['record:1']['name'], objects['record:1']['x'], objects['record:1']['y']), ('Peng', 256 + 0x10, 0x48))
        item = self.p.objects({'stage': 1, 'section': 1})[0]
        self.assertEqual((item['style'], item['name'], item['x']), ('item', 'Large life energy', 0x20))

    def test_where(self):
        ram = bytearray(0x800)
        ram[0x31], ram[0x29], ram[0x27], ram[0x28], ram[0x1B], ram[0x1A] = 1, 2, 0, 1, 1, 0x30
        self.assertEqual(self.p.where(ram), {'part': {'stage': 1, 'section': 0}, 'x': 256 + 0x30, 'y': 0})
        ram[0x28] = 0                                                         # not running (intro)
        self.assertIsNone(self.p.where(ram))

    def test_swap(self):
        plan = self.p.edit({'stage': 1, 'section': 0}, 'record:0', {'type': 7})
        at = put(bytearray(len(self.rom)), 6, 0xA503, [])
        self.assertEqual(plan['writes'], [(at, 0x03, 0x07)])
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 1, 'section': 0}, 'record:0', {'type': 0x40})   # an item is not an enemy

    def test_remove(self):
        plan = self.p.edit({'stage': 1, 'section': 0}, 'record:1', {}, remove=True)
        rom = bytearray(self.rom)
        for at, old, new in plan['writes']:
            self.assertEqual(rom[at], old)
            rom[at] = new
        p = mm.MegaMan1(bytes(rom))
        self.assertEqual([r['type'] for r in p.records(1)], [0x03, 0xFF, 0x40, 0x03])
        rows = [rom[put(bytearray(len(rom)), 5, 0x93C3 + 1 + 12 * row, [])] for row in range(3)]
        self.assertEqual(rows, [0xFF, 1, 0])                                   # restart points after record 1 count one fewer
        self.assertEqual(plan['watch']['next_type'], 0xFF)

    def test_watcher(self):
        plan = self.p.edit({'stage': 1, 'section': 0}, 'record:0', {'type': 7})
        ram = bytearray(0x800)
        ram[0x31], ram[0x29], ram[0x27], ram[0x28] = 1, 2, 0, 1
        watcher = self.p.watcher(plan['watch'])
        self.assertFalse(watcher.see(ram, 0, 'changed'))
        ram[0x410], ram[0x7B], ram[0x6F0], ram[0x490], ram[0x610] = 0xFF, 0, 0x07, 0x80, 0x90
        self.assertTrue(watcher.see(ram, 2, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        control = self.p.watcher(plan['watch'])
        ram[0x6F0] = 0x03
        control.see(ram, 2, 'original')
        self.assertEqual(control.result()['state'], 'bad')


class MegaMan2Test(unittest.TestCase):
    def setUp(self):
        self.rom = cart2()
        self.p = mm.MegaMan2(bytes(self.rom))

    def test_stages_share_a_bank(self):
        self.assertEqual([(s['first'], s['last']) for s in self.p.sections(1)], [(0, 1), (2, 2)])
        self.assertEqual([(s["first"], s["last"]) for s in self.p.sections(9)], [(3, 3), (4, 4)])
        wily = self.p.objects({'stage': 9, 'section': 0})
        self.assertEqual([o['id'] for o in wily], ['enemy:2', 'item:1', 'link:0'])
        self.assertEqual(wily[1]['name'], 'Extra life')

    def test_item_swap_and_remove(self):
        plan = self.p.edit({'stage': 1, 'section': 0}, 'item:0', {'type': 0x7B})
        self.assertEqual(plan['writes'], [(put(bytearray(len(self.rom)), 1, 0xBAC0, []), 0x7A, 0x7B)])
        plan = self.p.edit({'stage': 1, 'section': 0}, 'enemy:0', {}, remove=True)
        rom = bytearray(self.rom)
        for at, old, new in plan['writes']:
            rom[at] = new
        p = mm.MegaMan2(bytes(rom))
        self.assertEqual([(r['screen'], r['type']) for r in p.records(1) if r['list'] == 'enemy'], [(1, 0x30), (3, 0x21)])
        behind = rom[put(bytearray(len(rom)), 1, 0xBB0C, []):][:6]
        self.assertEqual(list(behind), [0, 0, 1, 1, 2, 2])

    def test_slots(self):
        ram = bytearray(0x800)
        ram[0x430 + 3], ram[0x410 + 3], ram[0x130 + 3], ram[0x120 + 3] = 0x80, 0x7A, 1, 1
        ram[0x430 + 4], ram[0x410 + 4], ram[0x100 + 4], ram[0x120 + 4] = 0x80, 0x21, 2, 0
        self.assertEqual([(s, l, n, k) for s, l, n, k, x in self.p.slots(ram)], [(3, 'item', 1, 0x7A), (4, 'enemy', 2, 0x21)])


def put8(rom, bank, address, data):
    """Write into an 8 KB bank (Mega Man 3 to 5 map stage banks at $A000 and code banks at $8000)."""
    at = mm.HEADER + bank * 0x2000 + (address & 0x1FFF)
    rom[at:at + len(data)] = bytes(data)
    return at


def cart3():
    """Mega Man 3: stage 1 (bank 1) with four sections, four records (the last in the boss room) and one restart point."""
    rom = bytearray(mm.HEADER + 16 * 0x4000)
    rom[4] = 0x10
    put8(rom, 1, 0xAA40, [0x22, 0x40, 0x61, 0x20, 0x00])   # 3 screens; down 1; down then 2 sideways; right 1 (boss); end
    for address, values in ((0xAB00, [1, 2, 3, 6, 0xFF]), (0xAC00, [0x10, 0x20, 0x30, 0x40]), (0xAD00, [0x80, 0x90, 0x90, 0x90]),
                            (0xAE00, [0x1B, 0x50, 0x3B, 0x47])):
        put8(rom, 1, address, values)
    put8(rom, 1, 0xAAF8, [3, 0xFF])                         # restart point at screen 3
    put8(rom, 1, 0xABC0, [2])                               # with records 0 and 1 behind it
    put8(rom, 0, 0xA100 + 0x1B, [0x2A])
    put8(rom, 0, 0xA100 + 0x3B, [0x4C])
    put8(rom, 0, 0xA100 + 0x50, [0x64])
    put8(rom, 0, 0xA400 + 0x47, [0x1C])                     # a boss's full energy bar
    return rom


class MegaMan3Test(unittest.TestCase):
    def setUp(self):
        self.rom = cart3()
        self.p = mm.MegaMan3(bytes(self.rom))

    def test_sections(self):
        self.assertEqual([(s['first'], s['last'], s['link']) for s in self.p.sections(1)],
                         [(0, 2, 0x40), (3, 3, 0x40), (4, 5, 0x20), (6, 6, 0)])

    def test_objects_and_boss(self):
        first = self.p.objects({'stage': 1, 'section': 0})
        self.assertEqual([(o['id'], o['name']) for o in first], [('record:0', 'Hari Harry'), ('record:1', 'Large life energy'),
                                                                 ('link:0', 'Way down to the next section')])
        self.assertEqual(first[1]['style'], 'item')
        self.assertEqual([o['id'] for o in self.p.objects({'stage': 1, 'section': 3})], [])     # the boss is left as it is
        self.assertNotIn(0x47, [c['value'] for c in self.p.choices()['enemies']])

    def test_where(self):
        ram = bytearray(0x800)
        ram[0x22], ram[0x2B], ram[0x2C], ram[0x2D], ram[0xF9], ram[0xFC], ram[0x300] = 1, 2, 1, 1, 5, 0x40, 0x80
        self.assertEqual(self.p.where(ram), {'part': {'stage': 1, 'section': 2}, 'x': 256 + 0x40, 'y': 0})
        ram[0x300] = 0                                                          # Mega Man is not in the stage
        self.assertIsNone(self.p.where(ram))

    def test_swap_and_remove(self):
        plan = self.p.edit({'stage': 1, 'section': 0}, 'record:0', {'type': 0x3B})
        self.assertEqual(plan['writes'], [(put8(bytearray(len(self.rom)), 1, 0xAE00, []), 0x1B, 0x3B)])
        plan = self.p.edit({'stage': 1, 'section': 0}, 'record:0', {}, remove=True)
        rom = bytearray(self.rom)
        for at, old, new in plan['writes']:
            self.assertEqual(rom[at], old)
            rom[at] = new
        p = mm.MegaMan3(bytes(rom))
        self.assertEqual([(r['screen'], r['type']) for r in p.records(1)], [(2, 0x50), (3, 0x3B), (6, 0x47)])
        self.assertEqual(rom[put8(bytearray(len(rom)), 1, 0xABC0, [])], 1)    # one record fewer behind the restart point

    def test_watcher_uses_routine(self):
        plan = self.p.edit({'stage': 1, 'section': 0}, 'record:0', {'type': 0x3B})
        ram = bytearray(0x800)
        ram[0x22], ram[0x2C], ram[0x300] = 1, 2, 0x80
        ram[0x312], ram[0x4D2], ram[0x332], ram[0x392], ram[0x372] = 0x80, 0, 0x4C, 1, 0x10
        watcher = self.p.watcher(plan['watch'])
        self.assertTrue(watcher.see(ram, 0, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        ram[0x332] = 0x2A                                                       # the unchanged game: Hari Harry's routine
        control = self.p.watcher(plan['watch'])
        control.see(ram, 0, 'original')
        self.assertEqual(control.result()['state'], 'bad')


def cart4():
    """Mega Man 4: stage 2 (bank $22) with a warp into a side section, records and the first-record-of-screen table."""
    rom = bytearray(mm.HEADER + 32 * 0x4000)
    rom[4] = 0x20
    bank = 0x22
    put8(rom, bank, 0xB530, [0x21, 0x40, 0x30, 0x00, 0x20] + [0] * 11)   # 2 screens; down; boss room; unreachable; side room
    put8(rom, bank, 0xB540, [1, 0x40, 4, 9, 0xFF])                        # warp: screen 1 going down -> section 4 at screen 9
    for address, values in ((0xB100, [0, 1, 2, 3, 9, 0xFF]), (0xB180, [0x40, 0x50, 0x20, 0x30, 0x60]),
                            (0xB200, [0x90] * 5), (0xB280, [0x03, 0xC1, 0x5A, 0x79, 0x7C])):
        put8(rom, bank, address, values)
    put8(rom, bank, 0xB300, [0, 1, 2, 3] + [4] * 6 + [5] * 22)
    for kind, number, picture in ((0x03, 0x15, 0), (0x13, 0x33, 0x56), (0x5A, 0xC1, 0x1A), (0x7C, 0xC1, 0x1E), (0x79, 0xB8, 0)):
        put8(rom, 0x38, 0x820F + kind, [number])
        put8(rom, 0x38, 0x832F + kind, [picture])
    return rom


class MegaMan4Test(unittest.TestCase):
    def setUp(self):
        self.rom = cart4()
        self.p = mm.MegaMan4(bytes(self.rom))

    def test_sections_and_warp(self):
        self.assertEqual([(s['segment'], s['first'], s['last']) for s in self.p.sections(2)], [(0, 0, 1), (1, 2, 2), (2, 3, 3), (4, 9, 9)])
        self.assertEqual(self.p.boss_room(2)['segment'], 2)
        side = self.p.objects({'stage': 2, 'section': 4})
        self.assertEqual([(o['id'], o['x']) for o in side], [('record:4', 0x60)])

    def test_objects(self):
        first = {o['id']: o for o in self.p.objects({'stage': 2, 'section': 0})}
        self.assertEqual(sorted(first), ['link:0', 'record:0'])               # record 1 changes palettes
        self.assertEqual(self.p.objects({'stage': 2, 'section': 1})[0]['name'], 'Large life energy')
        self.assertEqual(self.p.objects({'stage': 2, 'section': 2}), [])       # the boss room

    def test_remove_updates_screen_table(self):
        plan = self.p.edit({'stage': 2, 'section': 0}, 'record:0', {}, remove=True)
        rom = bytearray(self.rom)
        for at, old, new in plan['writes']:
            rom[at] = new
        table = put8(bytearray(len(rom)), 0x22, 0xB300, [])
        self.assertEqual(list(rom[table:table + 32]), [0, 0, 1, 2] + [3] * 6 + [4] * 22)
        self.assertEqual([r['type'] for r in mm.MegaMan4(bytes(rom)).records(2)], [0xC1, 0x5A, 0x79, 0x7C])

    def test_pickup_signature(self):
        plan = self.p.edit({'stage': 2, 'section': 1}, 'record:2', {'type': 0x7C})
        ram = bytearray(0x800)
        ram[0x22], ram[0x300] = 2, 1
        ram[0x309], ram[0x441], ram[0x561], ram[0x351] = 0xC1, 2, 0x1E, 2
        watcher = self.p.watcher(plan['watch'])
        self.assertTrue(watcher.see(ram, 0, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        ram[0x561] = 0x1A                                                       # same object number, large life energy's picture
        control = self.p.watcher(plan['watch'])
        control.see(ram, 0, 'original')
        self.assertEqual(control.result()['state'], 'bad')


def cart5():
    """Mega Man 5: stage 3 (bank 3) with a ladder warp."""
    rom = bytearray(mm.HEADER + 16 * 0x4000)
    rom[4] = 0x10
    put8(rom, 3, 0xA950, [0x23, 0x20, 0x00, 0x20, 0x20, 0x00])           # 4 screens; right 1; stops; (warp) 1; right 1
    put8(rom, 3, 0xA9E0, [4, 0x80, 7, 3, 0xFF])                           # screen 4 going up -> screen 7, section 3
    for address, values in ((0xAA00, [1, 4, 8, 0xFF]), (0xAA80, [0x10, 0x20, 0x30]), (0xAB00, [0x90] * 3), (0xAB80, [0x07, 0x01, 0x6A])):
        put8(rom, 3, address, values)
    put8(rom, 3, 0xAC00, [0, 0, 1, 1, 1, 2, 2, 2, 2, 3])
    return rom


class MegaMan5Test(unittest.TestCase):
    def setUp(self):
        self.rom = cart5()
        self.p = mm.MegaMan5(bytes(self.rom))

    def test_sections(self):
        self.assertEqual([(s['segment'], s['first'], s['last']) for s in self.p.sections(3)], [(0, 0, 3), (1, 4, 4), (3, 7, 7), (4, 8, 8)])
        self.assertEqual(self.p.boss_room(3)['segment'], 4)
        self.assertEqual([o['id'] for o in self.p.objects({'stage': 3, 'section': 0})], ['record:0', 'link:0'])

    def test_remove_and_slots(self):
        plan = self.p.edit({'stage': 3, 'section': 0}, 'record:0', {}, remove=True)
        rom = bytearray(self.rom)
        for at, old, new in plan['writes']:
            rom[at] = new
        table = put8(bytearray(len(rom)), 3, 0xAC00, [])
        self.assertEqual(list(rom[table:table + 10]), [0, 0, 0, 0, 0, 1, 1, 1, 1, 2])
        ram = bytearray(0x800)
        ram[0x30A], ram[0x442], ram[0x51A], ram[0x352], ram[0x33A] = 0x12, 1, 0x01, 4, 0x20
        self.assertEqual(self.p.slots(ram), [(10, 'record', 1, 0x01, 4 * 256 + 0x20)])


if __name__ == '__main__':
    unittest.main()
