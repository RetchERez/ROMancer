"""Super Mario Land level profile: decoders and edits on a made-up cartridge laid out like the real one.

The real game is not part of the tests; these build the same tables at the same addresses, so a change in how a table
is read or written shows here. What the tables mean was proven by replaying the real game (research notes).
"""
import unittest

from romancer.level_profiles import mario_land as ml


def off(bank, address):
    return address if address < 0x4000 else bank * 0x4000 + address - 0x4000


class Cart:
    """A blank 64 KB cartridge (4 banks of 16 KB)."""

    def __init__(self):
        self.rom = bytearray(4 * 0x4000)

    def put(self, bank, address, data):
        o = off(bank, address)
        self.rom[o:o + len(data)] = bytes(data)

    @staticmethod
    def word(value):
        return [value & 0xFF, value >> 8]


def column(tiles):
    """One column in the game's format: a group of 16 tiles from row 0, then $FE."""
    return [0x00] + list(tiles) + [0xFE]


def screen(special=None):
    """20 columns of sky over ground; special = {(column, row): tile}."""
    data = []
    for c in range(20):
        tiles = [0x2C] * 14 + [0x60, 0x61]
        for (sc, row), tile in (special or {}).items():
            if sc == c:
                tiles[row] = tile
        data += column(tiles)
    return data


def build():
    c = Cart()
    plain = screen()
    level0 = screen({(5, 9): 0x81, (2, 9): 0x81, (7, 4): 0x5F, (7, 9): 0x81, (1, 12): 0x70})
    room = screen({(6, 7): 0xF4})
    for bank in (1, 2, 3):
        # layout: 13 levels; each points to its own screen list in this bank
        for level in range(13):
            c.put(bank, 0x4000 + level * 2, Cart.word(0x4100 + level * 16))
            c.put(bank, 0x401A + level * 2, Cart.word(0x4300 + level * 8))
            c.put(bank, 0x4300 + level * 8, [0xFF])          # no enemies
            screens = [0x5000] * 5
            c.put(bank, 0x4100 + level * 16, sum((Cart.word(s) for s in screens), []) + [0xFF])
        c.put(bank, 0x5000, plain)
    # world 1 (bank 2), level 0: room on screen 1, start screen 3 holds the special tiles
    c.put(2, 0x4100, sum((Cart.word(s) for s in (0x5000, 0x5800, 0x5000, 0x5400, 0x5000)), []) + [0xFF])
    c.put(2, 0x5400, level0)
    c.put(2, 0x5800, room)
    # level 0 enemies (bank 2 $6002): Goombo at column 12, Nokobon (second quest only) at column 14 row 12 fine 1
    c.put(2, 0x401A, Cart.word(0x6002))
    c.put(2, 0x6002, [12, 0x0F, 0x00, 14, 0x4C, 0x84, 0xFF])
    # level 1 enemies elsewhere in bank 2 so the enemy pointer tells levels apart
    c.put(2, 0x401A + 2, Cart.word(0x6010))
    c.put(2, 0x6010, [20, 0x0F, 0x04, 0xFF])
    # bank 3 block and pipe lists for every level (level 0 has entries, the rest are empty)
    for level in range(13):
        c.put(3, 0x6536 + level * 2, Cart.word(0x5200))
        c.put(3, 0x651C + level * 2, Cart.word(0x5100))
    c.put(3, 0x5200, [0xFF])
    c.put(3, 0x5100, [0xFF])
    c.put(3, 0x6536, Cart.word(0x5210))
    c.put(3, 0x5210, [3, 5, 0x28, 3, 7, 0x2A, 0xFF])        # screen 3 column 5: mushroom; column 7: heart (hidden block on top)
    c.put(3, 0x651C, Cart.word(0x5110))
    c.put(3, 0x5110, [3, 1, 1, 3, 24, 136, 0xFF])          # pipe at screen 3 column 1 to the room on screen 1
    return c


class SuperMarioLandTest(unittest.TestCase):
    def setUp(self):
        self.c = build()
        self.p = ml.SuperMarioLandProfile(bytes(self.c.rom))

    def test_banks_and_layout(self):
        self.assertEqual(self.p.bank(0), 2)
        self.assertEqual(self.p.bank(3), 1)
        self.assertEqual(self.p.bank(6), 3)
        cols = self.p.columns(0)
        self.assertEqual(len(cols), 100)
        self.assertEqual(cols[3 * 20 + 5][9], 0x81)
        self.assertEqual(cols[3 * 20 + 7][4], 0x5F)

    def test_repeat_tile(self):
        c = Cart()
        c.put(2, 0x5000, [0x0E, 0xFD, 0x7F, 0xE2, 0x60, 0x61, 0xFE] + column([0x2C] * 16) * 19)
        p = ml.SuperMarioLandProfile(bytes(c.rom))
        cols = p._screen_columns(2, 0x5000)
        self.assertEqual(cols[0], [0x7F] * 14 + [0x60, 0x61])
        self.assertEqual(cols[1], [0x2C] * 16)

    def test_enemies(self):
        e = self.p.enemies(0)
        self.assertEqual([x['type'] for x in e], [0x00, 0x04])
        self.assertEqual((e[0]['x'], e[0]['y']), (480 + 12 * 16 + 8, 15 * 8 + 8))
        self.assertTrue(e[1]['second_quest'])
        self.assertEqual(e[1]['x'], 480 + 14 * 16 + 4 + 8)
        self.assertEqual(e[0]['byte'], off(2, 0x6004))

    def test_blocks_and_pipes(self):
        b = self.p.blocks(0)
        self.assertEqual([(x['screen'], x['column'], x['row'], x['tile'], x['what']) for x in b],
                         [(3, 5, 9, 0x81, 0x28), (3, 7, 4, 0x5F, 0x2A)])      # the top special tile of the column
        plain = self.p.plain_blocks(0)
        self.assertEqual([(x['screen'], x['column'], x['row']) for x in plain], [(3, 2, 9)])
        pipe = self.p.pipes(0)[0]
        self.assertEqual((pipe['room'], pipe['back'], pipe['row']), (1, 3, 12))
        names = {o['id']: o for o in self.p.objects({'level': 0})}
        self.assertEqual(names['block:1']['style'], 'secret')
        self.assertEqual(names['block:0']['name'], 'Question block')
        self.assertIn('enemy:0', names)
        self.assertIsNone(names['enemy:1']['remove'])

    def test_enemy_edits(self):
        swap = self.p.edit({'level': 0}, 'enemy:0', {'type': 4})
        self.assertEqual(swap['writes'], [(off(2, 0x6004), 0x00, 0x04)])
        self.assertEqual(swap['watch']['wanted'], [4])
        keep_flag = self.p.edit({'level': 0}, 'enemy:1', {'type': 0})
        self.assertEqual(keep_flag['writes'], [(off(2, 0x6007), 0x84, 0x80)])
        gone = self.p.edit({'level': 0}, 'enemy:0', {}, remove=True)
        self.assertEqual(gone['writes'], [(off(2, 0x6004), 0x00, 0x80)])
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'enemy:0', {'type': 0x77})
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'enemy:1', {}, remove=True)

    def test_block_edits(self):
        edit = self.p.edit({'level': 0}, 'block:0', {'what': 0x2C})
        self.assertEqual(edit['writes'], [(off(3, 0x5212), 0x28, 0x2C)])
        self.assertEqual(edit['watch']['row'], 9)
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'block:0', {'what': 0x55})

    def test_where(self):
        ram = bytearray(0x2000)
        ram[0x1010], ram[0x1011] = 0x05, 0x60       # inside level 0's enemy list
        ram[0xAB], ram[0xAA] = 12, 0
        ram[0xB0:0xC0] = bytes(self.p.columns(0)[86])
        self.assertEqual(self.p.where(ram), {'part': {'level': 0}, 'x': 483, 'y': 0})
        ram[0x1010] = 0x11                           # level 1's list
        self.assertEqual(self.p.where(ram)['part'], {'level': 1})
        ram[0x1010], ram[0x1011] = 0x00, 0x10       # no level
        self.assertIsNone(self.p.where(ram))

    def test_where_room(self):
        ram = bytearray(0x2000)
        ram[0x1010], ram[0x1011] = 0x02, 0x60
        ram[0xAB], ram[0xAA] = 12, 0
        ram[0xB0:0xC0] = bytes([0x55] * 16)          # a column the level does not have near the camera
        self.assertEqual(self.p.where(ram)['x'], 160)

    def test_watchers(self):
        edit = self.p.edit({'level': 0}, 'enemy:0', {'type': 4})
        w = self.p.watcher(edit['watch'])
        ram = bytearray(0x2000)
        for slot in range(10):
            ram[0x1100 + 16 * slot] = 0xFF
        ram[0x1010], ram[0x1011] = 0x05, 0x60
        ram[0x1100:0x1104] = bytes([0x04, 0x01, 15 * 8 + 16, 0xBE])
        ram[0x1011] = 0x5F                           # before the entry: no slot yet
        w.see(ram, 8, 'changed')
        ram[0x1011] = 0x60
        self.assertTrue(w.see(ram, 10, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(edit['watch'])
        ram[0x1100] = 0x00
        w.see(ram, 10, 'changed')
        self.assertEqual(w.result()['state'], 'bad')
        self.assertEqual([c['value'] for c in self.p.choices()['enemies_world1']], [0, 4])
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'enemy:0', {'type': 0x3C})     # not used by world 1
        self.assertEqual(self.p.watcher(edit['watch']).result()['state'], 'warn')

    def test_second_quest_watch_warns(self):
        edit = self.p.edit({'level': 0}, 'enemy:1', {'type': 0})
        w = self.p.watcher(edit['watch'])
        ram = bytearray(0x2000)
        for slot in range(10):
            ram[0x1100 + 16 * slot] = 0xFF
        ram[0x1010], ram[0x1011] = 0x08, 0x60      # past the entry
        for frame in range(0, 20, 2):
            if w.see(ram, frame, 'changed'):
                break
        self.assertEqual(w.result()['state'], 'warn')

    def test_tile_roles(self):
        self.assertEqual(self.p.tile_role(0x60), 'solid')
        self.assertEqual(self.p.tile_role(0x82), 'breakable')
        self.assertEqual(self.p.tile_role(0x2C), 'open')
        self.assertEqual(self.p.tile_role(0xF4), 'open')


if __name__ == '__main__':
    unittest.main()


# ---------------------------------------------------------------------------------------------------------------------
# Super Mario Land 2
# ---------------------------------------------------------------------------------------------------------------------

class Ram(bytes):
    domains = {}


def build2():
    """32 levels: headers in bank 1, maps in bank 4, object lists in bank 3; level 0 has a few objects."""
    rom = bytearray(8 * 0x4000)

    def put(bank, address, data):
        o = off(bank, address)
        rom[o:o + len(data)] = bytes(data)
    for level in range(32):
        put(1, 0x55CB + level * 2, Cart.word(0x5700 + level * 20))
        head = [0] * 20
        head[0x0D], head[0x12] = 4, level % 2
        put(1, 0x5700 + level * 20, head)
        put(3, 0x6037 + level * 2, Cart.word(0x6100 if level else 0x6077))
    put(3, 0x6100, [0xFF])
    # map 0: 16 rows of cell $60, then row 16 onward cell $61, one ? block (cell 1) at row 28 column 42; map 1: all $62
    put(4, 0x42F0, Cart.word(0x4500) + Cart.word(0x4600))
    map0 = [0x80 | 0x60, 0xFF] * 16 + [0x80 | 0x61, 0xFF] * 12 + [0x80 | 0x61, 41, 0x01, 0x80 | 0x61, 0xFF] + [0x80 | 0x61, 0xFF] * 20
    put(4, 0x4500, map0)
    put(4, 0x4600, [0x80 | 0x62, 0xFF] * 48)
    # objects of level 0: Goomba (472, 496), mushroom in the block at (680, 440), Koopa (584, 448), the end bell
    entries = [(0x21, 0x3B, 0x3E), (0x42, 0x35, 0x37), (0x02, 0x09 | 0x20, 0x38), (*ml.SuperMarioLand2.encode_type(0x02, 0x10, 0x16), 0x2D)]
    put(3, 0x6077, [b for e in entries for b in e] + [0xFF])
    return rom


class SuperMarioLand2Test(unittest.TestCase):
    def setUp(self):
        self.rom = build2()
        self.p = ml.SuperMarioLand2Profile(bytes(self.rom))

    def test_decode_encode(self):
        d = ml.SuperMarioLand2.decode(0x21, 0x3B, 0x3E)
        self.assertEqual((d['x'], d['y'], d['type']), (472, 496, 0x09))
        self.assertEqual(ml.SuperMarioLand2.decode(0x42, 0x35, 0x37)['type'], 0x11)
        for kind in (0x01, 0x09, 0x11, 0x15, 0x4D, 0x6F):
            b0, b1 = ml.SuperMarioLand2.encode_type(0x21, 0x3B, kind)
            self.assertEqual(ml.SuperMarioLand2.decode(b0, b1, 0x3E)['type'], kind)
            self.assertEqual((b0 & 15, b1 & 31), (1, 0x1B))

    def test_map_and_objects(self):
        m = self.p.level_map(0)
        self.assertEqual(len(m), 0x3000)
        self.assertEqual(m[28 * 256 + 42], 1)
        objs = {o['id']: o for o in self.p.objects({'level': 0})}
        self.assertEqual(objs['object:0']['name'], 'Goomba')
        self.assertEqual(objs['object:1']['name'], 'Question block')
        self.assertEqual((objs['object:1']['x'], objs['object:1']['y']), (42 * 16 + 8, 28 * 16 + 16))
        self.assertEqual(objs['object:2']['name'], 'Koopa Troopa')
        self.assertEqual(objs['object:3']['fields'], [])
        self.assertEqual([c['value'] for c in self.p.enemy_choices(0)], [0x01, 0x09])

    def test_edits(self):
        swap = self.p.edit({'level': 0}, 'object:0', {'type': 0x01})
        self.assertEqual(swap['writes'], [(off(3, 0x6077), 0x21, 0x01)])
        item = self.p.edit({'level': 0}, 'object:1', {'type': 0x14})
        b0, b1 = ml.SuperMarioLand2.encode_type(0x42, 0x35, 0x14)
        self.assertEqual(item['writes'], [(off(3, 0x607A + i), old, new) for i, (old, new) in enumerate(((0x42, b0), (0x35, b1))) if old != new])
        gone = self.p.edit({'level': 0}, 'object:0', {}, remove=True)
        rom = bytearray(self.rom)
        for offset, old, new in gone['writes']:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        after = ml.SuperMarioLand2Profile(bytes(rom))
        self.assertEqual([o['type'] for o in after.objects_of(0)], [0x11, 0x01, 0x16])
        for bad in (({'type': 0x4D}, False), ({}, True)):
            with self.assertRaises(ValueError):
                self.p.edit({'level': 0}, 'object:1' if bad[1] else 'object:0', bad[0], remove=bad[1])
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'object:3', {'type': 0x09})

    def ram(self, level=0, cam=(0x150, 0x1C0)):
        ram = Ram(self.p.level_map(level)[0x1000:0x3000])
        cart = bytearray(0x2000)
        cart[0x269] = level
        high = bytearray(0x80)
        high[0x4A], high[0x4B] = (cam[0] + 0x50) & 0xFF, (cam[0] + 0x50) >> 8
        high[0x48], high[0x49] = (cam[1] + 0x48) & 0xFF, (cam[1] + 0x48) >> 8
        ram.domains = {'sram': bytes(cart), 'hram': bytes(high)}
        return ram, cart

    def test_where(self):
        ram, _ = self.ram()
        self.assertEqual(self.p.where(ram), {'part': {'level': 0}, 'x': 0x150, 'y': 0x1C0})
        other, _ = self.ram(level=1)
        other.domains = dict(other.domains, sram=bytes([0] * 0x269 + [0] + [0] * (0x2000 - 0x26A)))
        self.assertIsNone(self.p.where(other))          # the map in work RAM is not level 0's
        self.assertIsNone(self.p.where(Ram(bytes(0x2000))))

    def test_watcher(self):
        edit = self.p.edit({'level': 0}, 'object:0', {'type': 0x01})
        ram, cart = self.ram()
        cart[0xB06:0xB0C] = bytes([0x01, 0xD8, 0, 0x01, 0xF0, 0x01])
        ram.domains = dict(ram.domains, sram=bytes(cart))
        w = self.p.watcher(edit['watch'])
        w.see(ram, 8, 'changed')
        self.assertEqual(w.result()['state'], 'good')
        cart[0xB0B] = 0x09
        ram.domains = dict(ram.domains, sram=bytes(cart))
        w = self.p.watcher(edit['watch'])
        w.see(ram, 8, 'changed')
        self.assertEqual(w.result()['state'], 'bad')
        self.assertEqual(self.p.watcher(edit['watch']).result()['state'], 'warn')


class NamesTest(unittest.TestCase):
    """Naming pass: every name is a name, every does-line a plain sentence."""

    def test_tables(self):
        for cls in (ml.SuperMarioLand, ml.SuperMarioLand2):
            for kind, name in cls.ENEMIES.items():
                self.assertFalse(name.startswith('Enemy'), name)
            for kind, does in cls.DOES.items():
                self.assertIn(kind, cls.ENEMIES)
                self.assertTrue(does[0].isupper() and does.endswith('.'), does)
        self.assertEqual(ml.SuperMarioLand.ENEMIES[0x3F], 'Gao')
        self.assertEqual(ml.SuperMarioLand2.ENEMIES[0x5B], 'Diving bird')

    def test_unsure_cleared(self):
        p = ml.SuperMarioLand(bytes(0x10000))
        self.assertEqual(p.enemy_name(0x3C), 'Bunbun')
        self.assertEqual(p.enemy_name(0x36), 'Enemy 0x36')      # not settled by a picture yet
