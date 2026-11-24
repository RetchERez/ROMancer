"""Super Mario Bros. 2 level profile on a made-up cartridge with the game's tables at their real addresses."""
import unittest

from romancer.level_profiles import Ram
from romancer.level_profiles import smb2
from romancer.level_profiles.smb2 import SMB2Profile


def data(address):
    return 16 + 0x10000 + address - 0x8000


def fixed(address):
    return 16 + 0x1C000 + address - 0xC000


def cartridge():
    rom = bytearray(16 + 0x40000)
    rom[:4] = b'NES\x1a'
    for level in range(21):
        rom[data(0x8000 + level)] = level * 10
    for i in range(210):
        rom[data(0x8015 + i)], rom[data(0x80E7 + i)] = 0x40, 0x82            # every area: an empty one at $8240
    rom[data(0x8015)], rom[data(0x80E7)] = 0x00, 0x82                       # level 0 area 0 at $8200
    rom[data(0x8016)], rom[data(0x80E8)] = 0x20, 0x82                       # level 0 area 1 at $8220
    area0 = [0x80, 0x00, 0x10, 0x00,             # horizontal, two pages
             0x05, 0x21,                         # grass (large vegetable), page 0 row 0 column 5
             0x10, 0x0A, 0x00, 0x12,             # door, row 1 column 0, leads to level 0 area 1 screen 3
             0xF2,                               # next page
             0x34, 0x00,                         # mushroom block, page 1 row 3 column 4
             0xF5, 0x00, 0x10,                   # page 1 leads to level 0 area 1 screen 1
             0xFF]
    rom[data(0x8200):data(0x8200) + len(area0)] = bytes(area0)
    rom[data(0x8220):data(0x8220) + 7] = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x22, 0xFF])     # vertical, small vegetable
    rom[data(0x8240):data(0x8240) + 5] = bytes([0x80, 0x00, 0x00, 0x00, 0xFF])
    for level in range(21):
        rom[data(0xA500 + level)], rom[data(0xA515 + level)] = 0xA6, 0x00       # high bytes list at $A600
        rom[data(0xA52A + level)], rom[data(0xA53F + level)] = 0xA6, 0x10       # low bytes list at $A610
    for area in range(10):
        rom[data(0xA600 + area)], rom[data(0xA610 + area)] = 0xA7, 0x20
    rom[data(0xA610)] = 0x00                                                    # area 0 enemies at $A700
    enemies = [5, 0x01, 0x52, 0x44, 0x83,        # page 0: red Shy Guy at column 5 row 2, crystal ball
               3, 0x03, 0x14]                    # page 1: pink Shy Guy at column 1 row 4
    rom[data(0xA700):data(0xA700) + len(enemies)] = bytes(enemies)
    rom[data(0xA720):data(0xA720) + 4] = bytes([1, 1, 1, 1])
    rom[fixed(0xE012):fixed(0xE012) + 8] = bytes([0, 3, 6, 9, 12, 15, 18, 20])
    rom[fixed(0xFE00):fixed(0xFE00) + 7] = bytes([0x0C, 0x0D, 0x0C, 0x0E, 0x0C, 0x0D, 0x0F])
    grass = 16 + 6 * 0x2000 + 0xD30
    rom[grass:grass + 16] = bytes([0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B, 0x4E, 0x4C, 0x41, 0x5B, 0x42, 0x5A, 0xA4])
    return bytes(rom)


def ram(**values):
    r = bytearray(0x800 + 0x2000)
    r[smb2.NMI_MODE] = 0xC0
    r[smb2.HORIZONTAL] = 1
    for key, value in values.items():
        r[int(key[1:], 16)] = value
    return r


PART = {'level': 0, 'area': 0}


class Decode(unittest.TestCase):
    def setUp(self):
        self.p = SMB2Profile(cartridge())

    def test_stream(self):
        s = self.p.stream(0, 0)
        self.assertEqual([(o['kind'], o['page'], o['row'], o['col'], o['type']) for o in s],
                         [('object', 0, 0, 5, 0x21), ('door', 0, 1, 0, 0x0A), ('object', 1, 3, 4, 0x00), ('pointer', 1, 0, 0, None)])
        self.assertEqual(s[1]['to'], (0, 1, 2))
        self.assertEqual(s[3]['to'], (0, 1, 0))

    def test_doors_carry_no_pointer_in_world_6(self):
        rom = bytearray(cartridge())
        for i in range(10):         # level 15 (World 6-1) area 0 uses level 0's data
            rom[data(0x8015 + 150 + i)], rom[data(0x80E7 + 150 + i)] = 0x00, 0x82
        s = SMB2Profile(bytes(rom)).stream(15, 0)
        self.assertEqual(s[1]['kind'], 'object')
        self.assertEqual((s[2]['row'], s[2]['col'], s[2]['type']), (1, 0, 0x12))      # the pointer bytes read as an object

    def test_enemies_and_areas(self):
        self.assertEqual([(e['index'], e['page'], e['col'], e['row'], e['id']) for e in self.p.enemies(0, 0)],
                         [(1, 0, 5, 2, 0x01), (3, 0, 8, 3, 0x44), (6, 1, 1, 4, 0x03)])
        self.assertEqual(self.p.areas(0), [0, 1])
        self.assertEqual(self.p.level_name(4), '2-2')
        self.assertEqual(self.p.part_name(PART), 'World 1-1, area 1')

    def test_objects(self):
        objs = {o['id']: o for o in self.p.objects(PART)}
        self.assertEqual((objs['enemy:1']['x'], objs['enemy:1']['y'], objs['enemy:1']['name']), (88, 48, 'Shy Guy (red)'))
        self.assertEqual(objs['enemy:1']['fields'][0]['choices'], 'enemies_0c')
        self.assertEqual(objs['enemy:3']['fields'], [])                    # crystal ball: shown, not changed
        self.assertEqual((objs['enemy:6']['x'], objs['enemy:6']['y']), (256 + 24, 80))
        self.assertEqual((objs['grass:4']['x'], objs['grass:4']['y'], objs['grass:4']['detail']), (88, 16, 'gives a large vegetable'))
        self.assertEqual((objs['block:11']['x'], objs['block:11']['name']), (256 + 72, 'Mushroom block'))
        self.assertEqual(objs['way:6']['detail'], 'leads to World 1-1, area 2, screen 3')
        self.assertTrue(objs['way:6']['fields'] and objs['way:13']['fields'])
        names = [c['name'] for c in self.p.choices()['enemies_0c']]
        self.assertEqual(names, ['Shy Guy (pink)', 'Shy Guy (red)'])

    def test_vertical_tiles_sit_16_lines_above_sprites(self):
        objs = {o['id']: o for o in self.p.objects({'level': 0, 'area': 1})}
        self.assertEqual((objs['grass:4']['x'], objs['grass:4']['y']), (8, 0))


class Edits(unittest.TestCase):
    def setUp(self):
        self.p = SMB2Profile(cartridge())

    def test_enemy_swap_and_remove(self):
        e = self.p.edit(PART, 'enemy:1', {'kind': 3})
        self.assertEqual(e['writes'], [(data(0xA701), 0x01, 0x03)])
        self.assertEqual(e['watch']['wanted'], 3)
        e = self.p.edit(PART, 'enemy:1', {}, remove=True)
        self.assertEqual(e['writes'], [(data(0xA701), 0x01, 0x81)])
        self.assertNotIn('enemy:1', [o['id'] for o in SMB2Profile(self._apply(e['writes'])).objects(PART)])
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'enemy:1', {'kind': 0x26})          # Autobomb: not drawn in this world's sprite bank
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'enemy:3', {'kind': 1})             # crystal ball

    def test_grass_and_block(self):
        e = self.p.edit(PART, 'grass:4', {'gives': 0x25})
        self.assertEqual(e['writes'], [(data(0x8205), 0x21, 0x25)])
        self.assertEqual((e['watch']['tile'], e['watch']['page'], e['watch']['row'], e['watch']['col']), (0x48, 0, 0, 5))
        e = self.p.edit(PART, 'block:11', {'block': 1})
        self.assertEqual(e['writes'], [(data(0x820C), 0x00, 0x01)])
        self.assertEqual(e['watch']['tile'], 0x6C)
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'grass:4', {'gives': 0x29})

    def test_ways(self):
        e = self.p.edit(PART, 'way:6', {'to': 0x010})
        self.assertEqual(e['writes'], [(data(0x8209), 0x12, 0x10)])
        e = self.p.edit(PART, 'way:13', {'to': 0x012})
        self.assertEqual(e['writes'], [(data(0x820F), 0x10, 0x12)])
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'way:13', {'to': 0x090})

    def _apply(self, writes):
        rom = bytearray(cartridge())
        for offset, old, new in writes:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        return bytes(rom)


class Watchers(unittest.TestCase):
    def setUp(self):
        self.p = SMB2Profile(cartridge())

    def test_where(self):
        r = Ram(ram(x531=0, x532=0, x4BE=1, x4C0=0x20))
        self.assertEqual(self.p.where(r), {'part': PART, 'x': 0x120, 'y': 0})
        self.assertIsNone(self.p.where(Ram(ram(x532=1))))           # area 1 is vertical but the horizontal flag is still set
        r = ram(x532=1, xCA=2, xCB=0x10)
        r[smb2.HORIZONTAL] = 0
        self.assertEqual(self.p.where(Ram(r)), {'part': {'level': 0, 'area': 1}, 'x': 0, 'y': 2 * 240 + 0x10})
        self.assertIsNone(self.p.where(Ram(ram(x628=2))))           # subspace

    def test_enemy_watcher(self):
        e = self.p.edit(PART, 'enemy:1', {'kind': 3})
        w = self.p.watcher(e['watch'])
        r = ram(x51=1, x90=3, x441=1)
        self.assertTrue(w.see(Ram(r), 10, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(e['watch'])
        w.see(Ram(ram(x51=1, x90=1, x441=1)), 10, 'changed')
        self.assertEqual(w.result()['state'], 'bad')
        removal = self.p.watcher(self.p.edit(PART, 'enemy:1', {}, remove=True)['watch'])
        self.assertEqual(removal.result()['state'], 'warn')
        for frame in range(40):
            removal.see(Ram(ram()), frame, 'changed')
        self.assertEqual(removal.result()['state'], 'good')

    def test_tile_and_way_watchers(self):
        w = self.p.watcher(self.p.edit(PART, 'grass:4', {'gives': 0x25})['watch'])
        r = ram()
        r[0x800 + 5] = 0x48
        self.assertTrue(w.see(Ram(r), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(self.p.edit(PART, 'way:6', {'to': 0x010})['watch'])
        r = ram()
        r[0x51D], r[0x51E] = 0, 0x12
        w.see(Ram(r), 0, 'original')
        self.assertEqual(w.result()['state'], 'bad')


if __name__ == '__main__':
    unittest.main()
