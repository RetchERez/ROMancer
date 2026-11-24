"""Capcom Disney level profiles (DuckTales): decoders and edits on a made-up cartridge laid out like the real one.

The real game is not part of the tests; these build the same tables at the same addresses (bank 6 object tables and
kinds, bank 7 land sizes and item tables), so a change in how a table is read or written shows here. What the tables
mean was proven by replaying the real game (research/capcom_disney-level-profile.md).
"""
import unittest

from romancer.level_profiles import capcom_disney as cd

H = 16


class Cart:
    """A blank UNROM cartridge (8 banks of 16 KB, bank 7 fixed at $C000)."""

    def __init__(self):
        self.rom = bytearray(H + 8 * 0x4000)

    def put6(self, address, data):
        o = H + 0x18000 + address - 0x8000
        self.rom[o:o + len(data)] = bytes(data)

    def put7(self, address, data):
        o = H + 0x1C000 + address - 0xC000
        self.rom[o:o + len(data)] = bytes(data)

    def get6(self, address):
        return self.rom[H + 0x18000 + address - 0x8000]


# kinds (4 bytes at $BE16 + kind * 4): flags|contents, graphic, type, parameter
KINDS = {
    0x01: [0xA0, 0x0D, 0x05, 0x91],      # snake
    0x03: [0xA0, 0x12, 0x07, 0x12],      # man-eating plant
    0x07: [0xB0, 0x1A, 0x08, 0x80],      # stone block, empty
    0x08: [0xA0, 0x1B, 0x08, 0x80],      # chest, contents 0
    0x17: [0xB0, 0x23, 0x14, 0x00],      # hidden small diamond
    0x18: [0xB0, 0x24, 0x14, 0x00],      # hidden ice cream
    0x2C: [0xB0, 0x28, 0x15, 0x05],      # fixed (left alone)
    0x32: [0xA1, 0x1B, 0x08, 0x80],      # chest, contents 1
    0x34: [0xA3, 0x1B, 0x08, 0x80],      # chest, contents 3
    0x40: [0xB1, 0x9A, 0x08, 0x80],      # stone block holding item 1
}
LAND0 = {'screen': 0x9000, 'x': 0x9010, 'starts': 0x9020, 'y': 0x9030, 'kind': 0x9040}
EMPTY = {'screen': 0x9100, 'x': 0x9101, 'starts': 0x9102, 'y': 0x9103, 'kind': 0x9104}
# land 0: row 0 = chest, snake, stone block; row 1 = hidden diamond, plant
RECORDS = [(0x00, 0x10, 0xB8, 0x08), (0x01, 0x20, 0xB0, 0x01), (0x01, 0x40, 0xB8, 0x07), (0xFF, 0xFF, 0xFF, 0xFF),
           (0x00, 0x30, 0xA8, 0x17), (0x02, 0x50, 0xB4, 0x03), (0xFF, 0xFF, 0xFF, 0xFF)]


def build():
    c = Cart()
    for land in range(9):
        t = LAND0 if land == 0 else EMPTY
        for k, name in enumerate(('screen', 'x', 'starts', 'y', 'kind')):
            c.put6(0xB050 + 18 * k + land, [t[name] & 0xFF])
            c.put6(0xB050 + 18 * k + 9 + land, [t[name] >> 8])
    for i, (screen, x, y, kind) in enumerate(RECORDS):
        c.put6(LAND0['screen'] + i, [screen])
        c.put6(LAND0['x'] + i, [x])
        c.put6(LAND0['y'] + i, [y])
        c.put6(LAND0['kind'] + i, [kind])
    c.put6(LAND0['starts'], [0, 4])
    c.put6(EMPTY['screen'], [0xFF])          # the other lands: one row, empty (the start index 0 points at $FF)
    for land in range(9):
        c.put7(0xCE57 + land, [2 if land == 0 else 1])
        c.put7(0xCE61 + land, [8])
    for kind, data in KINDS.items():
        c.put6(0xBE16 + kind * 4, data)
    c.put6(0x8FB8, [0x28, 0x23, 0x24, 0x25, 0x26, 0x27])       # chest contents -> item
    c.put7(0xF67B, [0x24, 0x28, 0x25, 0x26])                   # block contents -> item
    return c


def ram(**values):
    r = bytearray(0x800)
    for k, v in values.items():
        r[int(k[1:], 16)] = v
    return r


class DuckTalesDecode(unittest.TestCase):
    def setUp(self):
        self.c = build()
        self.p = cd.DuckTalesProfile(bytes(self.c.rom))

    def test_records(self):
        rows = self.p.records(0)
        self.assertEqual([(r['index'], r['row'], r['screen'], r['x'], r['y'], r['kind']) for r in rows],
                         [(0, 0, 0, 0x10, 0xB8, 8), (1, 0, 1, 0x20, 0xB0, 1), (2, 0, 1, 0x40, 0xB8, 7),
                          (4, 1, 0, 0x30, 0xA8, 0x17), (5, 1, 2, 0x50, 0xB4, 3)])
        self.assertEqual([r['role'] for r in rows], ['chest', 'enemy', 'block', 'hidden', 'enemy'])
        self.assertEqual(rows[0]['item'], 0x28)
        self.assertIsNone(rows[2]['item'])
        self.assertEqual(rows[3]['item'], 0x23)
        self.assertEqual(self.p.count(0), 7)
        self.assertEqual(self.p.records(1), [])

    def test_containers(self):
        self.assertEqual(self.p.role(0x40, 0), {'role': 'block', 'item': 0x28})
        self.assertEqual(self.p.role(0x34, 0), {'role': 'chest', 'item': 0x25})
        self.assertEqual(self.p.role(0x2C, 0)['role'], 'fixed')
        chest = self.p.content_choices(0x08, 0)
        self.assertEqual([c['value'] for c in chest], [0x08, 0x32, 0x34])
        self.assertEqual(chest[2]['name'], 'Cake')
        self.assertEqual([c['value'] for c in self.p.content_choices(0x07, 0)], [0x07, 0x40])
        self.assertEqual([c['value'] for c in self.p.content_choices(0x17, 0)], [0x17, 0x18])
        self.assertEqual([c['value'] for c in self.p.enemy_choices(0)], [0x01, 0x03])

    def test_objects_and_where(self):
        objs = {o['id']: o for o in self.p.objects({'land': 0})}
        self.assertEqual((objs['object:1']['x'], objs['object:1']['y']), (256 + 0x20, 0xB0))
        self.assertEqual((objs['object:5']['x'], objs['object:5']['y']), (512 + 0x50, 240 + 0xB4))
        self.assertEqual(objs['object:0']['style'], 'item')
        self.assertEqual(objs['object:4']['style'], 'secret')
        self.assertEqual(objs['object:1']['fields'][0]['choices'], 'land0')
        self.assertIsNone(self.p.where(ram(xF6=0)))                       # not playing
        playing = ram(xF6=0, xEA=0x40, x60=0x00, x61=0x90, xF1=1, xF3=2, xF2=0x34)
        self.assertEqual(self.p.where(playing), {'part': {'land': 0}, 'x': 512 + 0x34, 'y': 240})

    def test_swap(self):
        plan = self.p.edit({'land': 0}, 'object:0', {'kind': 0x34})
        self.assertEqual(plan['writes'], [(H + 0x18000 + 0x1040, 0x08, 0x34)])
        self.assertEqual(plan['watch']['want'], {'type': 0x08, 'gfx': 0x1B, 'contents': 3, 'holds': False})
        plan = self.p.edit({'land': 0}, 'object:2', {'kind': 0x40})
        self.assertEqual(plan['watch']['want']['gfx'], 0x1A)              # the game clears bit 7 when it spawns
        self.assertTrue(plan['watch']['want']['holds'])                   # and marks it in $06C0
        plan = self.p.edit({'land': 0}, 'object:1', {'kind': 0x03})
        self.assertEqual(plan['writes'], [(H + 0x18000 + 0x1041, 0x01, 0x03)])
        with self.assertRaises(ValueError):
            self.p.edit({'land': 0}, 'object:1', {'kind': 0x08})          # a chest is not one of the enemies
        with self.assertRaises(ValueError):
            self.p.edit({'land': 0}, 'object:0', {'kind': 0x17})

    def test_remove(self):
        writes = self.p.remove_writes(0, 1)
        rom = bytearray(self.c.rom)
        for offset, old, new in writes:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        after = cd.DuckTalesProfile(bytes(rom))
        rows = after.records(0)
        self.assertEqual([(r['row'], r['screen'], r['x'], r['kind']) for r in rows],
                         [(0, 0, 0x10, 8), (0, 1, 0x40, 7), (1, 0, 0x30, 0x17), (1, 2, 0x50, 3)])
        self.assertEqual(rom[H + 0x18000 + 0x1021], 3)                    # row 1 now starts one place earlier
        self.assertEqual(rom[H + 0x18000 + 0x1006], 0xFF)                 # the freed last place is a row end
        with self.assertRaises(ValueError):
            self.p.remove_writes(0, 3)                                    # a row end, not an object


class DuckTalesWatcher(unittest.TestCase):
    def setUp(self):
        self.p = cd.DuckTalesProfile(bytes(build().rom))

    def frames(self, watcher, spawn):
        base = dict(xF6=0, xF1=0, xF3=0, xF2=0)
        watcher.see(ram(**base), 0, 'changed')
        r = ram(**base)
        if spawn:
            s = 5
            for a, v in spawn.items():
                r[a + s] = v
        return watcher.see(r, 1, 'changed')

    def test_swap_good_and_bad(self):
        plan = self.p.edit({'land': 0}, 'object:0', {'kind': 0x34})
        w = self.p.watcher(plan['watch'])
        self.frames(w, {0x700: 0xA0, 0x7F0: 0, 0x730: 0, 0x720: 0x10, 0x640: 0xB8, 0x710: 0x08, 0x620: 0x1B, 0x6B0: 3})
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        self.frames(w, {0x700: 0xA0, 0x7F0: 0, 0x730: 0, 0x720: 0x10, 0x640: 0xB8, 0x710: 0x08, 0x620: 0x1B, 0x6B0: 0})
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(plan['watch'])
        self.assertEqual(w.result()['state'], 'warn')

    def test_block_needs_the_item_mark(self):
        plan = self.p.edit({'land': 0}, 'object:2', {'kind': 0x40})
        spot = {0x700: 0xB0, 0x7F0: 2, 0x730: 1, 0x720: 0x40, 0x640: 0xB8, 0x710: 0x08, 0x620: 0x1A, 0x6B0: 1}
        w = self.p.watcher(plan['watch'])
        self.frames(w, dict(spot))
        self.assertEqual(w.result()['state'], 'bad')                      # same look and number, no item
        w = self.p.watcher(plan['watch'])
        self.frames(w, {**spot, 0x6C0: 0xFF})
        self.assertEqual(w.result()['state'], 'good')

    def test_remove(self):
        plan = self.p.edit({'land': 0}, 'object:1', {}, remove=True)
        w = self.p.watcher(plan['watch'])
        r0 = ram(xF6=0, xF1=0, xF3=1, xF2=0)
        w.see(r0, 0, 'changed')
        w.see(r0, 1, 'changed')
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        w.see(r0, 0, 'changed')
        r1 = bytearray(r0)
        for a, v in {0x700: 0xA0, 0x7F0: 1, 0x730: 1, 0x720: 0x20, 0x640: 0xB0, 0x710: 0x05}.items():
            r1[a + 3] = v
        w.see(r1, 1, 'changed')
        self.assertEqual(w.result()['state'], 'bad')


if __name__ == '__main__':
    unittest.main()
