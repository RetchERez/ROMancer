"""Mega Man X2 and X3 level profiles on made-up cartridges that only have the object tables at their real places
(no game data)."""
import unittest

from romancer.level_profiles.megamanx23 import MegaManX2Profile, MegaManX3Profile, PROFILES, _X23Watcher, lorom


def put(rom, address, data):
    o = lorom(address)
    rom[o:o + len(data)] = bytes(data)


def entry(t, y, oid, sub, x, last):
    return [t, y & 0xFF, y >> 8, oid, sub, x & 0xFF, (x >> 8) | (0x80 if last else 0)]


def make_rom(P, size, enemy_a, enemy_b, enemy_c):
    """Level 0 has a graphics load, three enemies, a large life energy, a Heart Tank and a weapon energy; level 1
    places the same enemies again so they count as ordinary ones."""
    rom = bytearray(size)
    bank = P.BANK << 16
    put(rom, bank | 0xA000, [0x00] + entry(2, 0x100, 0x00, 0x00, 0x10, True) + [0x00])
    for level in range(P.LEVELS):
        put(rom, P.LISTS + level * 2, [0x00, 0xA0])
    put(rom, P.LISTS, [0x00, 0x90])
    data = ([0x04] + entry(2, 0x180, 0x15, 0x11, 0x080, True)                       # graphics load
            + [0x09] + entry(3, 0x170, enemy_a, 0x00, 0x130, False) + entry(3, 0x168, enemy_b, 0x00, 0x13F, True)
            + [0x0B] + entry(0, 0x170, 0x02, 0x80, 0x170, False) + entry(0, 0x170, 0x0B, 0x01, 0x178, False)
            + entry(0, 0x170, 0x01, 0x80, 0x17C, True)
            + [0x0C] + entry(3, 0x150, enemy_c, 0x00, 0x190, True)
            + [0x0C])
    put(rom, bank | 0x9000, data)
    put(rom, P.LISTS + 2, [0x00, 0x98])
    put(rom, bank | 0x9800, [0x01] + entry(3, 0x100, enemy_a, 0, 0x20, False) + entry(3, 0x100, enemy_b, 0, 0x20, False)
        + entry(3, 0x100, enemy_c, 0, 0x30, True) + [0x01])
    return bytes(rom)


def ram_at(level_byte, level, cam_x, cam_y, playing=True):
    ram = bytearray(0x20000)
    ram[0xD1], ram[0xD2] = (4, 4) if playing else (2, 4)
    ram[0x1E5D:0x1E5F] = cam_x.to_bytes(2, 'little')
    ram[0x1E60:0x1E62] = cam_y.to_bytes(2, 'little')
    ram[level_byte] = level
    return ram


class _Common:
    P = None
    SIZE = 0
    ENEMIES = (0, 0, 0)

    def setUp(self):
        # item edits are switched off in the shipped profile; the tests check their writes with them on
        self.P = type(self.P.__name__, (self.P,), {'ITEM_EDITS': True})
        self.p = self.P(make_rom(self.P, self.SIZE, *self.ENEMIES))

    def test_items_not_offered_when_off(self):
        base = self.P.__mro__[1]
        p = base(self.p.rom)
        objs = {o['id']: o for o in p.objects({'level': 0})}
        self.assertEqual((objs['obj:3']['fields'], objs['obj:3']['remove']), ([], None))
        self.assertEqual(objs['obj:3']['name'], 'Large life energy')
        with self.assertRaises(ValueError):
            p.edit({'level': 0}, 'obj:3', {'item': 0x0480})
        self.assertTrue(p.edit({'level': 0}, 'obj:2', {}, remove=True)['writes'])

    def test_decode(self):
        e = self.p.entries(0)
        a, b, c = self.ENEMIES
        self.assertEqual([(x['type'], x['id'], x['x'], x['y']) for x in e],
                         [(2, 0x15, 0x80, 0x180), (3, a, 0x130, 0x170), (3, b, 0x13F, 0x168), (0, 0x02, 0x170, 0x170),
                          (0, 0x0B, 0x178, 0x170), (0, 0x01, 0x17C, 0x170), (3, c, 0x190, 0x150)])
        start = self.p.list_start(0)
        self.assertEqual(start, lorom(self.P.BANK << 16 | 0x9000))
        self.assertEqual(self.p.list_bytes(e), self.p.rom[start:start + 54])
        objs = {o['id']: o for o in self.p.objects({'level': 0})}
        self.assertNotIn('obj:0', objs)
        self.assertEqual(objs['obj:3']['name'], 'Large life energy')
        self.assertEqual(objs['obj:3']['does'], 'Restores 8 life energy.')
        self.assertEqual(objs['obj:3']['style'], 'item')
        self.assertEqual(objs['obj:4']['name'], 'Heart Tank')
        self.assertEqual(objs['obj:4']['style'], 'secret')
        self.assertEqual(objs['obj:5']['name'], 'Large weapon energy')
        self.assertEqual(objs['obj:5']['style'], 'item')
        self.assertNotIn('note', objs['obj:5'])
        self.assertEqual(len(objs['obj:1']['fields'][0]['choices']), 3)
        for o in objs.values():
            self.assertNotRegex(o['name'], r'0x|\d{2,}')
            if o['style'] == 'enemy':
                self.assertTrue(o.get('does'))
            for f in o['fields']:
                for ch in f['choices']:
                    self.assertNotRegex(ch['name'], r'0x')

    def test_where(self):
        lv = self.P.LEVEL_RAM
        self.assertEqual(self.p.where(ram_at(lv, 3, 0x120, 0x40)), {'part': {'level': 3}, 'x': 0x120, 'y': 0x40})
        self.assertIsNone(self.p.where(ram_at(lv, 3, 0x120, 0x40, playing=False)))
        self.assertIsNone(self.p.where(ram_at(lv, self.P.LEVELS, 0, 0)))

    def test_swap_and_item(self):
        a, b, c = self.ENEMIES
        plan = self.p.edit({'level': 0}, 'obj:1', {'enemy': c << 8})
        off = self.p.entries(0)[1]['offset']
        self.assertEqual(plan['writes'], [(off + 3, a, c)])
        self.assertEqual(plan['watch']['entry'], 0xFA02 + 5)
        plan = self.p.edit({'level': 0}, 'obj:3', {'item': 0x0480})
        off = self.p.entries(0)[3]['offset']
        self.assertEqual(plan['writes'], [(off + 3, 0x02, 0x04)])
        plan = self.p.edit({'level': 0}, 'obj:4', {'item': 0x0280})       # Heart Tank to large life energy
        off = self.p.entries(0)[4]['offset']
        self.assertEqual(plan['writes'], [(off + 3, 0x0B, 0x02), (off + 4, 0x01, 0x80)])
        plan = self.p.edit({'level': 0}, 'obj:5', {'item': 0x0480})       # weapon energy to 1-Up
        off = self.p.entries(0)[5]['offset']
        self.assertEqual(plan['writes'], [(off + 3, 0x01, 0x04)])
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'obj:3', {'item': 0x0181})          # weapon energy is not offered
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'obj:3', {'item': 0x0B01})          # nor a Heart Tank
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'obj:1', {'enemy': 0x6F00})

    def test_remove(self):
        plan = self.p.edit({'level': 0}, 'obj:2', {}, remove=True)
        rom = bytearray(self.p.rom)
        for o, old, new in plan['writes']:
            self.assertEqual(rom[o], old)
            rom[o] = new
        q = self.P(bytes(rom))
        a, b, c = self.ENEMIES
        self.assertEqual([(x['id'], x['x']) for x in q.entries(0)],
                         [(0x15, 0x80), (a, 0x130), (0x02, 0x170), (0x0B, 0x178), (0x01, 0x17C), (c, 0x190)])
        plan = self.p.edit({'level': 0}, 'obj:6', {}, remove=True)
        rom = bytearray(self.p.rom)
        for o, old, new in plan['writes']:
            rom[o] = new
        q = self.P(bytes(rom))
        self.assertEqual([x['id'] for x in q.entries(0)], [0x15, a, b, 0x02, 0x0B, 0x01])
        start = q.list_start(0)
        self.assertEqual(q.list_bytes(q.entries(0)), q.rom[start:start + len(q.list_bytes(q.entries(0)))])

    def test_watchers(self):
        a, b, c = self.ENEMIES
        lv = self.P.LEVEL_RAM
        plan = self.p.edit({'level': 0}, 'obj:1', {'enemy': c << 8})
        base = self.P.SLOTS[3][0]

        def with_slot(oid):
            ram = ram_at(lv, 0, 0x100, 0x100)
            s = base + 2 * 0x40
            ram[s], ram[s + 0xA], ram[s + 0xB] = 1, oid, 0
            ram[s + 0xC:s + 0xE] = (0xFA02 + 5).to_bytes(2, 'little')
            return ram
        w = self.p.watcher(plan['watch'])
        self.assertIsInstance(w, _X23Watcher)
        self.assertTrue(w.see(with_slot(c), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(with_slot(a), 0, 'original'))
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(plan['watch'])
        self.assertFalse(w.see(ram_at(lv, 1, 0, 0), 0, 'original'))
        self.assertEqual(w.result()['state'], 'warn')
        # removal: the screen over the spot for 31 looks with nothing there
        plan = self.p.edit({'level': 0}, 'obj:2', {}, remove=True)
        w = self.p.watcher(plan['watch'])
        ram = ram_at(lv, 0, 0x100, 0x100)
        self.assertFalse(any(w.see(ram, f, 'changed') for f in range(30)))
        self.assertTrue(w.see(ram, 31, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        s = base
        ram[s], ram[s + 0xA], ram[s + 0xB] = 1, b, 0
        ram[s + 5:s + 7] = (0x13F).to_bytes(2, 'little')
        ram[s + 8:s + 10] = (0x168).to_bytes(2, 'little')
        self.assertTrue(w.see(ram, 0, 'original'))
        self.assertEqual(w.result()['state'], 'bad')


class NamesTest(unittest.TestCase):
    def test_registered_and_named(self):
        self.assertEqual(PROFILES, [MegaManX2Profile])
        for P in (MegaManX2Profile, MegaManX3Profile):
            for number, (name, does) in P.ENEMIES.items():
                self.assertNotRegex(name, r'0x|\d{2,}')
                self.assertTrue(does and does.endswith('.'))
            self.assertEqual(len(P.LEVEL_NAMES), P.LEVELS)


class MegaManX2Test(_Common, unittest.TestCase):
    P = MegaManX2Profile
    SIZE = 0x180000
    ENEMIES = (0x09, 0x2D, 0x50)

    def test_small_energy(self):
        plan = self.p.edit({'level': 0}, 'obj:3', {'item': 0x0282})
        self.assertEqual(plan['writes'], [(self.p.entries(0)[3]['offset'] + 4, 0x80, 0x82)])
        self.assertEqual(self.p.item_does(0x02, 0x82), 'Restores 2 life energy.')


class MegaManX3Test(_Common, unittest.TestCase):
    P = MegaManX3Profile
    SIZE = 0x200000
    ENEMIES = (0x08, 0x0D, 0x2D)

    def test_no_small_energy(self):
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'obj:3', {'item': 0x0282})


if __name__ == '__main__':
    unittest.main()
