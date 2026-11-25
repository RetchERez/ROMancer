"""Castlevania level profile: the decoders and the edits, on a made-up cartridge laid out like the real one.

The real game is not part of the tests; these build the same tables at the same addresses, so a change in how a table
is read or written shows here. What the tables mean was proven by replaying the real game (research notes).
"""
import unittest

from romancer import level_profiles as lp

H = lp.HEADER_NES


class Cart:
    """A blank NES cartridge (8 banks of 16 KB) with helpers that write at CPU addresses."""

    def __init__(self):
        self.rom = bytearray(H + 8 * 0x4000)

    def at7(self, address):
        return H + 0x1C000 + address - 0xC000

    def at6(self, address):
        return H + 0x18000 + address - 0x8000

    def at4(self, address):
        return H + 0x10000 + address - 0x8000

    def put7(self, address, data):
        self.rom[self.at7(address):self.at7(address) + len(data)] = bytes(data)

    def put6(self, address, data):
        self.rom[self.at6(address):self.at6(address) + len(data)] = bytes(data)

    def put4(self, address, data):
        self.rom[self.at4(address):self.at4(address) + len(data)] = bytes(data)

    @staticmethod
    def word(value):
        return [value & 0xFF, value >> 8]


def build():
    """Stage 0: 3 screens (pages 2), stage 1: 2 screens; every other stage points at stage 1's tables."""
    c = Cart()
    # zone tables: stage list $D26B -> one floor list per stage from $D291; the tables fill $D2CD-$D6A0 back to back
    # like the real ones (stage 0 and 1 hold objects; the others hold a marker in the middle and zeros around it)
    starts = [0xD2CD, 0xD2E9] + [0xD305 + 54 * n for n in range(17)]
    for stage in range(19):
        c.put7(0xD26B + stage * 2, Cart.word(0xD291 + stage * 2))
        c.put7(0xD291 + stage * 2, Cart.word(starts[stage]))
    c.put7(0xD291 + 19 * 2, Cart.word(starts[18]))       # the last stage's second floor
    for stage in range(2, 19):
        c.put7(starts[stage] + 26, [stage])
    stage0 = [(0, 0)] * 14
    stage0[1] = (1, 0)              # zone 1: enemy record 1
    stage0[2] = (0, 2)              # zone 2: candle record 2 (with a drop)
    stage0[5] = (0, 3)              # zone 5: candle record 3 (wall candle, no drop)
    stage0[9] = (1, 2)              # zone 9: same enemy and candle records again
    c.put7(0xD2CD, [b for pair in stage0 for b in pair])
    stage1 = [(0, 0)] * 14
    stage1[0] = (1, 0)
    c.put7(0xD2E9, [b for pair in stage1 for b in pair])
    c.put7(0xD6A1, Cart.word(0xD840))                     # record 0 is empty, as in the game
    c.put7(0xD840, [0])
    # record pools: words at $D6A1 + index * 2
    c.put7(0xD6A1 + 1 * 2, Cart.word(0xD800))
    c.put7(0xD800, [0x51, 0x10, 0x80])                    # enemy: panther, 16 px into the zone, y 128
    c.put7(0xD6A1 + 2 * 2, Cart.word(0xD810))
    c.put7(0xD810, [0xFF, 0x08, 0xFE, 0x20, 0xB0])        # candle with a dagger, 32 px in, y 176
    c.put7(0xD6A1 + 3 * 2, Cart.word(0xD820))
    c.put7(0xD820, [0x30, 0x98])                          # wall candle, 48 px in, y 152
    c.put7(0xD6A1 + 4 * 2, Cart.word(0xD830))
    c.put7(0xD830, [0xFF, 0x05, 0xFE, 0x20, 0xB0])        # same spot as record 2, pot roast
    # scroll limits: stage 0 floor 0 pages 2; others pages 1
    for stage in range(19):
        c.put7(0xFB8C + stage, [0x20 if stage == 0 else 0x10])
        c.put7(0xFB9F + stage, [0xFF])
        c.put7(0xFC3A + stage, [0xFF])
    # layout: master $FAFF -> floor lists in bank 4
    for stage in range(19):
        c.put7(0xFAFF + stage * 2, Cart.word(0x8000 if stage == 0 else 0x8004))
    c.put4(0x8000, Cart.word(0x8100 - 0x18) + Cart.word(0x8300 - 0x18))
    c.put4(0x8004, Cart.word(0x8300 - 0x18) + Cart.word(0x8300 - 0x18))
    for column in range(24):                               # stage 0: column n is six bytes of n
        c.put4(0x8100 + column * 6, [column] * 6)
    c.put4(0x8100 + 24 * 6, [0xEE] * 48)                    # whatever follows
    c.put4(0xB408, [0xFF] * (0xC000 - 0xB408))              # the free end of bank 4
    # secrets: treasure ($FC14) and blocks ($FC4D) lists in bank 6
    for stage in range(19):
        c.put7(0xFC14 + stage * 2, Cart.word(0x8040 if stage == 0 else 0x8060))
        c.put7(0xFC4D + stage * 2, Cart.word(0x8050 if stage == 0 else 0x8062))
        c.put7(0xFBC8 + stage * 2, Cart.word(0x8070 if stage == 0 else 0x8064))
    c.put6(0x8040, [0xB6, 0x62, 0x1A, 0x00,                 # walk in at x 0x260 (screen 2): money bag
                    0xBA, 0x31, 0x1A, 0x02,                 # crouch at x 0x130 (screen 1), second quest: crown
                    0xFF])
    c.put6(0x8050, [0x93, 0x22, 0x00])                       # block at x 0x228 (screen 2), y 0x98, item 3
    c.put6(0x8060, [0xFF])
    c.put6(0x8062, [0x00])
    c.put6(0x8064, [0x00])
    c.put6(0x8070, [0x01, 0x80, 0x00])                       # stairs at x 0x80 (screen 0)
    c.put6(0xAA4F, [0x00, 0x04, 0x05, 0x11, 0x0C, 0x07, 0x0E, 0x0E])
    c.put7(0xCF5B, [0xB0, 0xB8, 0x02, 0x70, 0x36, 0x00])     # courtyard gate at x 0x2B8
    return c


def apply(rom, writes):
    out = bytearray(rom)
    for offset, old, new in writes:
        assert out[offset] == old, (hex(offset), old, out[offset])
        out[offset] = new
    return bytes(out)


class Objects(unittest.TestCase):
    def setUp(self):
        self.p = lp.Castlevania(bytes(build().rom))

    def test_enemy_and_candle_records(self):
        self.assertEqual(self.p.enemy_record(1), {'type': 0x51, 'dx': 0x10, 'y': 0x80})
        self.assertIsNone(self.p.enemy_record(0))
        candle = self.p.candle_record(2)
        self.assertEqual((candle['type'], candle['dx'], candle['y'], candle['drop']), (0x28, 0x20, 0xB0, 0x08))
        wall = self.p.candle_record(3)
        self.assertEqual((wall['type'], wall['dx'], wall['y'], wall['drop']), (0x27, 0x30, 0x98, 0))

    def test_objects_are_placed_by_zone(self):
        found = [(o['kind'], o['zone'], o['x'], o['y'], o['name']) for o in self.p.objects(0, 0, 14) if o['kind'] in ('enemy', 'candle')]
        self.assertIn(('enemy', 1, 64 + 0x10, 0x80, 'Panther'), found)
        self.assertIn(('candle', 2, 128 + 0x20, 0xB0, 'Candle'), found)
        self.assertIn(('candle', 5, 320 + 0x30, 0x98, 'Wall candle'), found)
        candle = next(o for o in self.p.objects(0, 0, 14) if o['kind'] == 'candle' and o['zone'] == 2)
        self.assertEqual(candle['drop_name'], 'Dagger')
        self.assertEqual(candle['shared'], 2)          # zones 2 and 9 use the same record

    def test_drop_choices_keep_the_spot(self):
        choices = self.p.drop_choices(0, 0, 2, 14)
        self.assertEqual({c['name'] for c in choices}, {'Dagger', 'Pot roast'})
        self.assertNotIn(3, [c['index'] for c in choices])     # the wall candle is somewhere else

    def test_every_item_code_has_a_name(self):
        self.assertEqual(len({self.p.drop_name(code) for code in range(16)}), 16)
        self.assertEqual(self.p.drop_name(0x15), 'Pot roast')  # the high nibble is colour only

    def test_tile_roles(self):
        self.assertEqual(self.p.tile_role(0x60), 'solid')
        self.assertEqual(self.p.tile_role(0x66), 'breakable')
        self.assertEqual(self.p.tile_role(0x10), 'open')


class Secrets(unittest.TestCase):
    def setUp(self):
        self.p = lp.Castlevania(bytes(build().rom))

    def test_treasure(self):
        rows = self.p.treasures(0, 0)
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual((first['x'] - self.p.ZONE - 1, first['y'], first['treasure'], first['how'], first['second_quest']),
                         (0x260, 0xB0, 0, 'Walk there', False))
        second = rows[1]
        self.assertEqual((second['how'], second['second_quest'], second['name']), ('Crouch there', True, 'Hidden crown'))

    def test_blocks(self):
        rows = self.p.blocks(0, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['x'] - self.p.ZONE - 1 - 8, rows[0]['item'], rows[0]['drop_name']), (0x220, 3, 'Money bag'))
        self.assertEqual(self.p.block_item_name(0), 'Nothing')
        self.assertEqual(self.p.block_item_name(2), 'Pot roast')

    def test_secret_writes(self):
        writes = self.p.secret_writes('block', 0, 0, 0, item=2)
        self.assertEqual(len(writes), 1)
        changed = lp.Castlevania(apply(self.p.rom, writes))
        self.assertEqual(changed.blocks(0, 0)[0]['drop_name'], 'Pot roast')
        writes = self.p.secret_writes('treasure', 0, 0, 0, treasure=1, trigger=1)
        changed = lp.Castlevania(apply(self.p.rom, writes))
        row = changed.treasures(0, 0)[0]
        self.assertEqual((row['treasure'], row['how'], row['x']), (1, 'Crouch there', self.p.treasures(0, 0)[0]['x']))
        self.assertEqual(self.p.secret_writes('block', 0, 0, 0, item=3), [])
        with self.assertRaises(ValueError):
            self.p.secret_writes('block', 0, 0, 0, item=9)


class Length(unittest.TestCase):
    def setUp(self):
        self.p = lp.Castlevania(bytes(build().rom))

    def zones(self, profile, stage=0, floor=0):
        return [(z['enemy_index'], z['candle_index']) for z in profile.zones(stage, floor, (profile.pages(stage, floor) + 1) * 4 + 2)]

    def test_shorter(self):
        result = self.p.resize_writes(0, 0, 1, -1)
        q = lp.Castlevania(apply(self.p.rom, result['writes']))
        self.assertEqual(q.pages(0, 0), 1)
        # layout: screen 1 (columns 8-15) is gone
        data = q.layout(0, 0)
        columns = [q._b4(data + 6 * c) for c in range(16)]
        self.assertEqual(columns, list(range(8)) + list(range(16, 24)))
        # zones: 4 a screen
        old = self.zones(self.p)
        self.assertEqual(self.zones(q)[:8], old[:4] + old[8:12])
        # things on screen 2 move a screen left; the one on the removed screen goes out of reach
        treasure = q.treasures(0, 0)
        self.assertEqual(treasure[0]['x'], self.p.treasures(0, 0)[0]['x'] - 256)
        self.assertEqual((treasure[1]['x'] - q.ZONE - 1) >> 8, 7)
        self.assertEqual(q.blocks(0, 0)[0]['x'], self.p.blocks(0, 0)[0]['x'] - 256)
        self.assertEqual(q.rom[q.offset(0xCF5D)], 1)                 # the gate
        self.assertTrue(result['notes'])

    def test_longer_keeps_every_other_table(self):
        result = self.p.resize_writes(0, 0, 1, 2)
        q = lp.Castlevania(apply(self.p.rom, result['writes']))
        self.assertEqual(q.pages(0, 0), 4)
        self.assertEqual(q.layout(0, 0), 0xB408 + 0x18)                # moved to the free end of bank 4
        data = q.layout(0, 0)
        columns = [q._b4(data + 6 * c) for c in range(40)]
        self.assertEqual(columns, list(range(16)) + list(range(8, 16)) * 2 + list(range(16, 24)))
        old = self.zones(self.p)
        self.assertEqual(self.zones(q), old[:8] + old[4:8] * 2 + old[8:])
        for stage in range(1, 19):
            self.assertEqual(self.zones(q, stage), self.zones(self.p, stage))
        self.assertEqual(q.treasures(0, 0)[0]['x'], self.p.treasures(0, 0)[0]['x'] + 512)
        self.assertEqual(q.treasures(0, 0)[1]['x'], self.p.treasures(0, 0)[1]['x'])  # screen 1 itself stays
        self.assertEqual(q.rom[q.offset(0xCF5D)], 4)

    def test_limits(self):
        with self.assertRaises(ValueError):
            self.p.resize_writes(0, 0, 0, -1)          # the first screen stays
        with self.assertRaises(ValueError):
            self.p.resize_writes(0, 0, 2, -1)          # and the last
        with self.assertRaises(ValueError):
            self.p.resize_writes(0, 0, 1, 4)           # longer than the longest stage
        cart = build()
        cart.put6(0x8070, [0x01, 0x81, 0x00])          # stairs on screen 1
        with self.assertRaises(ValueError):
            lp.Castlevania(bytes(cart.rom)).resize_writes(0, 0, 1, -1)


class Matching(unittest.TestCase):
    def test_only_the_exact_game(self):
        self.assertIsNone(lp.profile_for(bytes(build().rom)))


if __name__ == '__main__':
    unittest.main()


class Names(unittest.TestCase):
    """The naming pass: every enemy type has a name and a line on what it does, and variants read as names."""

    def setUp(self):
        self.p = lp.Castlevania(bytes(build().rom))

    def test_enemy_names_and_does(self):
        from romancer.level_profiles.castlevania import Castlevania
        for kind, (name, does) in Castlevania.ENEMIES.items():
            self.assertNotIn('0x', name)
            self.assertTrue(does.endswith('.'), kind)
        self.assertEqual(self.p.enemy_name(0x4F), 'Raven')
        self.assertEqual(self.p.enemy_name(0x59), 'Phantom Bat (boss)')
        self.assertEqual(self.p.enemy_name(0x05), 'Medusa heads (second quest only)')
        self.assertEqual(self.p.enemy_name(0xFF), 'Not an enemy (candle data)')
        self.assertEqual(self.p.enemy_name(0x77), 'Enemy 0x77')
        panther = next(o for o in self.p.objects(0, 0, 14) if o['kind'] == 'enemy')
        self.assertEqual(panther['does'], 'Crouches on a ledge and pounces when you come near.')

    def test_variant_names(self):
        from romancer.level_profiles.castlevania import variant_names
        rows = [{'index': 1, 'name': 'Raven', 'dx': 24, 'y': 72}, {'index': 2, 'name': 'Raven', 'dx': 40, 'y': 120},
                {'index': 3, 'name': 'Raven', 'dx': 48, 'y': 64}, {'index': 4, 'name': 'Raven', 'dx': 44, 'y': 72},
                {'index': 5, 'name': 'Eagle', 'dx': 32, 'y': 80}, {'index': 6, 'name': 'Axe Knight', 'dx': 24, 'y': 80},
                {'index': 7, 'name': 'Axe Knight', 'dx': 32, 'y': 80}]
        names = {c['value']: c['name'] for c in variant_names(rows)}
        self.assertEqual(names[2], 'Raven, halfway up')
        self.assertEqual(names[1], 'Raven, near the top, in the middle')
        self.assertEqual(names[3], 'Raven, near the top, to the right, a little higher')
        self.assertEqual(names[4], 'Raven, near the top, to the right, a little lower')
        self.assertEqual(names[5], 'Eagle')
        self.assertEqual((names[6], names[7]), ('Axe Knight, high, in the middle, a little to the left', 'Axe Knight, high, in the middle, a little to the right'))
        self.assertEqual(len(set(names.values())), len(names))

    def test_candle_records_are_not_offered_as_enemies(self):
        p = lp.Castlevania(bytes(build().rom))
        # index 2 of the shared pool is a candle record ($FF, drop, ...): read as an enemy its type is $FF
        self.assertEqual(p.enemy_record(2)['type'], 0xFF)
        self.assertNotIn(2, [c['index'] for c in p.enemy_choices()])
        self.assertIn(1, [c['index'] for c in p.enemy_choices()])

    def test_choices_have_no_heights(self):
        from romancer.level_profiles.castlevania import CastlevaniaProfile
        names = [c['name'] for c in CastlevaniaProfile(bytes(build().rom)).choices()['enemies']]
        self.assertTrue(names)
        self.assertFalse([n for n in names if 'height' in n])
