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


if __name__ == '__main__':
    unittest.main()
