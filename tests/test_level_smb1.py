"""Super Mario Bros. level profile: the decoders, the edits and the watchers, on a made-up cartridge laid out like the real
one (the area tables at their real addresses, made-up streams).

What the tables mean was proven by replaying the real game (research/smb1-level-profile.md).
"""
import unittest

from romancer.level_profiles import smb1

H = 16


class Cart:
    """A blank NROM cartridge (32 KB program, 8 KB characters) with helpers that write at CPU addresses."""

    def __init__(self):
        self.rom = bytearray(H + 0x8000 + 0x2000)

    @staticmethod
    def at(address):
        return H + address - 0x8000

    def put(self, address, data):
        self.rom[self.at(address):self.at(address) + len(data)] = bytes(data)


def build():
    c = Cart()
    # area lists: world 1 has a way-in area before its second level (five areas); the others have four
    worlds, areas = [], []
    for w in range(8):
        worlds.append(len(areas))
        areas += [0x25, 0x29, 0xC0, 0x26, 0x60] if w == 0 else [0x20 + w, 0x21, 0x22, 0x61]
    c.put(0x9CB4, worlds)
    c.put(0x9CBC, areas + [0] * (36 - len(areas)))
    # where each type starts in the pointer tables (same layout as the game: 3 water, 22 ground, 3 underground, 6 castle)
    c.put(0x9D28, [0, 3, 25, 28])
    c.put(0x9CE0, [28, 3, 25, 0])          # enemy tables: castle first, then ground, underground, water

    def area(pointer, objects, enemies, at_area, at_enemy):
        t, n = (pointer >> 5) & 3, pointer & 0x1F
        i = [0, 3, 25, 28][t] + n
        c.put(0x9D2C + i, [at_area & 0xFF])
        c.put(0x9D4E + i, [at_area >> 8])
        j = [28, 3, 25, 0][t] + n
        c.put(0x9CE4 + j, [at_enemy & 0xFF])
        c.put(0x9D06 + j, [at_enemy >> 8])
        c.put(at_area, [0x50, 0x31] + objects + [0xFD])
        c.put(at_enemy, enemies + [0xFF])

    # ground area 5: blocks on pages 1 and 4 (a row $D page select in between), a pipe one can enter on page 3
    area(0x25,
         [0x07, 0x81,          # page 1 col 0 row 7: question block with a coin
          0x57, 0x00,          # page 1 col 5 row 7: question block with a power-up
          0x97, 0x7B,          # page 1 col 9 row 7: pipe one can enter
          0x0D, 0x04,          # page select: page 4
          0x06, 0x03,          # page 4 col 0 row 6: hidden 1-up
          0x87, 0x07,          # page 4 col 8 row 7: brick with several coins
          0x17, 0x22],         # page 4 col 1: a row of bricks (not a single block)
         [0x1E, 0xC2, 0x00,    # page 1 (bit 7 of $C2), col 1: pipes lead to underground area 2, screen 1, in world 1
          0x6B, 0x06,          # page 1 col 6 row 11: Goomba
          0x8B, 0x86,          # page 2 col 8: Goomba
          0x63, 0x37,          # page 2 col 6 row 3: two Goombas
          0x0F, 0x05,          # page select: page 5
          0x03, 0x06,          # page 5 col 0: Goomba (just after a page select: cannot be removed in place)
          0x23, 0x46,          # page 5 col 2: Goomba, harder levels only
          0x2E, 0x25, 0xAA],   # page 5 col 2: pipes lead to ground area 5, screen 11, in world 6
         0xA000, 0xA100)
    area(0x42, [0x0B, 0x42], [0x1E, 0xA5, 0x0A], 0xA200, 0xA300)       # underground area 2: way back to 0x25 screen 11
    c.put(0xBDE8, [0xC1, 0xC0, 0x5F, 0x60, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E])
    return bytes(c.rom)


PART = {'world': 1, 'level': 1, 'area': 0x25}


def ram(**values):
    r = bytearray(0x800)
    r[smb1.MODE] = 1
    for key, value in values.items():
        r[int(key[1:], 16)] = value
    return r


class Decode(unittest.TestCase):
    def setUp(self):
        self.p = smb1.SMB1Profile(build())

    def test_areas_and_levels(self):
        self.assertEqual(self.p.area_count(), [3, 22, 3, 6])
        levels = self.p.levels()
        self.assertEqual(levels[(1, 1)], (0x25, None))
        self.assertEqual(levels[(1, 2)], (0x40, 0x29))
        self.assertEqual(levels[(2, 4)], (0x61, None))
        self.assertEqual(self.p.part_name(PART), 'World 1-1')
        self.assertEqual(self.p.part_name({'world': 1, 'level': 2, 'area': 0x29}), 'World 1-2, the way in')
        self.assertEqual(self.p.part_name({'world': 1, 'level': 1, 'area': 0x42}), 'World 1-1, underground side area 2')

    def test_streams(self):
        objects = self.p.objects_raw(0x25)
        self.assertEqual([(o['page'], o['col'], o['row'], o['value']) for o in objects],
                         [(1, 0, 7, 1), (1, 5, 7, 0), (1, 9, 7, 0x7B), (4, 0, 6, 3), (4, 8, 7, 7), (4, 1, 7, 0x22)])
        rows = self.p.enemies(0x25)
        self.assertEqual([(r['kind'], r['page'], r['col']) for r in rows],
                         [('way', 1, 1), ('enemy', 1, 6), ('enemy', 2, 8), ('enemy', 2, 6), ('page', 5, 0), ('enemy', 5, 0),
                          ('enemy', 5, 2), ('way', 5, 2)])
        self.assertEqual((rows[0]['to'], rows[0]['world'], rows[0]['at']), (0x42, 0, 0))
        self.assertTrue(rows[6]['hard'])
        self.assertEqual((rows[7]['to'], rows[7]['world'], rows[7]['at']), (0x25, 5, 10))

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects(PART)}
        self.assertNotIn('enemy:13', objects)                  # harder levels only
        self.assertNotIn('way:15', objects)                    # for world 6
        goomba = objects['enemy:3']
        self.assertEqual((goomba['name'], goomba['x'], goomba['y'], goomba['remove']), ('Goomba', 1 * 256 + 6 * 16 + 8, 208, 'Remove this enemy'))
        self.assertEqual(objects['enemy:7']['y'], 32 + 11 * 16)   # a group stands on the ground whatever its row
        self.assertIsNone(objects['enemy:11']['remove'])
        block = objects['block:2']
        self.assertEqual((block['style'], block['name'], block['detail'], block['x'], block['y']), ('item', 'Question block', 'holds a coin', 264, 160))
        self.assertEqual(objects['block:10']['style'], 'secret')
        self.assertNotIn('block:14', objects)                  # a row of bricks is not a single block
        way = objects['way:0']
        self.assertEqual((way['name'], way['x'], way['y']), ('Where this pipe leads', 256 + 9 * 16 + 16, 32 + 7 * 16))
        hard = {o['id'] for o in self.p.objects({'world': 6, 'level': 1, 'area': 0x25})}
        self.assertIn('enemy:13', hard)
        self.assertIn('way:15', hard)
        self.assertNotIn('way:0', hard)

    def test_where(self):
        self.assertEqual(self.p.where(ram(_75F=0, _75C=0, _74E=1, _74F=5, _750=0xC2, _71A=2, _71C=0x40)),
                         {'part': PART, 'x': 0x240, 'y': 8})
        self.assertIsNone(self.p.where(bytearray(0x800)))      # title screen and demo


class Edits(unittest.TestCase):
    def setUp(self):
        self.rom = build()
        self.p = smb1.SMB1Profile(self.rom)

    def test_swap_keeps_flags(self):
        plan = self.p.edit(PART, 'enemy:5', {'kind': 0x00})
        at = Cart.at(0xA100 + 6)
        self.assertEqual(plan['writes'], [(at, 0x86, 0x80)])
        self.assertEqual(plan['watch']['wanted'], 0)
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'enemy:5', {'kind': 0x3F})

    def test_remove_points_at_next_page(self):
        plan = self.p.edit(PART, 'enemy:3', {}, remove=True)
        at = Cart.at(0xA100 + 3)
        self.assertEqual(plan['writes'], [(at, 0x6B, 0x6F), (at + 1, 0x06, 0x02)])      # page select for page 2
        changed = bytearray(self.rom)
        for offset, old, new in plan['writes']:
            changed[offset] = new
        after = smb1.SMB1Profile(bytes(changed)).enemies(0x25)
        self.assertEqual([(r['kind'], r['page'], r['col']) for r in after if r['kind'] != 'page'],
                         [('way', 1, 1), ('enemy', 2, 8), ('enemy', 2, 6), ('enemy', 5, 0), ('enemy', 5, 2), ('way', 5, 2)])
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'enemy:11', {}, remove=True)

    def test_block(self):
        plan = self.p.edit(PART, 'block:2', {'holds': 6})
        self.assertEqual(plan['writes'], [(Cart.at(0xA000 + 3), 0x81, 0x86)])
        self.assertEqual(plan['watch']['metatile'], 0x57)
        self.assertEqual(self.p.metatile(6, 2), 0x5C)            # bricks look different outside ground areas
        self.assertEqual(self.p.metatile(3, 1), 0x60)
        self.assertEqual(self.p.metatile(3, 2), 0x59)
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'block:14', {'holds': 1})

    def test_way(self):
        plan = self.p.edit(PART, 'way:0', {'to': 0x25 << 5 | 10})
        at = Cart.at(0xA100)
        self.assertEqual(plan['writes'], [(at + 1, 0xC2, 0xA5), (at + 2, 0x00, 0x0A)])
        values = {c['value'] for c in self.p.choices()['ways']}
        self.assertEqual(values, {0x42 << 5, 0x25 << 5 | 10})


class Watchers(unittest.TestCase):
    def setUp(self):
        self.p = smb1.SMB1Profile(build())

    def play(self, watcher, frames):
        for frame, r in frames:
            if watcher.see(r, frame, 'changed'):
                break
        return watcher.result()['state']

    def test_enemy(self):
        plan = self.p.edit(PART, 'enemy:3', {'kind': 0x00})
        here = dict(_75F=0, _74E=1, _74F=5)
        before = ram(_739=2, **here)
        koopa = ram(_739=5, _0F=1, _16=0x00, _6E=1, _87=0x60, **here)
        goomba = ram(_739=5, _0F=1, _16=0x06, _6E=1, _87=0x60, **here)
        self.assertEqual(self.play(self.p.watcher(plan['watch']), [(0, before), (2, koopa), (40, koopa)]), 'good')
        self.assertEqual(self.play(self.p.watcher(plan['watch']), [(0, before), (2, goomba), (40, goomba)]), 'bad')
        self.assertEqual(self.play(self.p.watcher(plan['watch']), [(0, before)]), 'warn')
        removing = self.p.edit(PART, 'enemy:3', {}, remove=True)
        empty = ram(_739=5, **here)
        self.assertEqual(self.play(self.p.watcher(removing['watch']), [(0, before), (2, empty), (40, empty)]), 'good')
        self.assertEqual(self.play(self.p.watcher(removing['watch']), [(0, before), (2, goomba), (40, goomba)]), 'bad')

    def test_block(self):
        plan = self.p.edit(PART, 'block:2', {'holds': 6})
        star = ram(_75F=0, _74E=1, _74F=5, _71A=0, _71C=0x40, **{'_%X' % (0x5D0 + 7 * 16): 0x57})
        coin = ram(_75F=0, _74E=1, _74F=5, _71A=0, _71C=0x40, **{'_%X' % (0x5D0 + 7 * 16): 0xC0})
        self.assertEqual(self.play(self.p.watcher(plan['watch']), [(0, star)]), 'good')
        self.assertEqual(self.play(self.p.watcher(plan['watch']), [(0, coin)]), 'bad')
        far = ram(_75F=0, _74E=1, _74F=5, _71A=3, _71C=0)
        self.assertEqual(self.play(self.p.watcher(plan['watch']), [(0, far)]), 'warn')

    def test_way(self):
        plan = self.p.edit(PART, 'way:0', {'to': 0x25 << 5 | 10})
        new = ram(_75F=0, _74E=1, _74F=5, _739=3, _750=0xA5, _751=10)
        old = ram(_75F=0, _74E=1, _74F=5, _739=3, _750=0xC2, _751=0)
        self.assertEqual(self.play(self.p.watcher(plan['watch']), [(0, new)]), 'good')
        self.assertEqual(self.play(self.p.watcher(plan['watch']), [(0, old)]), 'bad')


if __name__ == '__main__':
    unittest.main()
