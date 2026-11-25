"""Tests for the Castlevania II - Belmont's Revenge profile .
A made-up 128 KB cartridge with the game's tables at their real addresses: bank 3 lists ($5242 things, $58AC enemies,
$5D25 candles) and bank 6 area starts ($5020)."""
import unittest

from romancer.level_profiles.gb_more import BelmontsRevenge, PROFILES


def _cv2_rom():
    rom = bytearray(0x20000)

    def put(bank, address, data):
        o = bank * 0x4000 + address - 0x4000
        rom[o:o + len(data)] = bytes(data)

    def table(address, lists):
        """8 stage pointers, then the 8 area tables (2 areas each) one after another, then the lists, as in the game"""
        tables = address + 16
        data = tables + 8 * 4
        for s in range(8):
            put(3, address + 2 * s, [(tables + 4 * s) & 255, (tables + 4 * s) >> 8])
            for a in range(2):
                body = lists.get((s, a), [0xFD])
                put(3, tables + 4 * s + 2 * a, [data & 255, data >> 8])
                put(3, data, body)
                data += len(body)

    table(0x5242, {(3, 0): [7, 0x2C, 0, 0x4E, 0xB0, 0x13, 0xFD]})
    table(0x58AC, {(3, 0): [8, 0x28, 0, 0x34, 0xB0, 0x12, 9, 0x48, 1, 0x34, 0xB0, 0x12, 0xFF, 9, 0x80, 2, 0x1F, 0xB0, 0x28, 0xFD],
                   (3, 1): [0xFE, 0, 0x33, 0x60, 0x60, 0xFD]})
    table(0x5D25, {(3, 0): [7, 0x4C, 0, 4, 0xB0, 0x4C, 7, 0x8C, 1, 5, 0xB0, 0x4C, 0xFD]})
    # bank 6 area starts: stage -> area -> (x screen, y screen)
    put(6, 0x5020, sum(([0x30 + 4 * s, 0x50] for s in range(8)), []))
    for s in range(8):
        put(6, 0x5030 + 4 * s, [0x60, 0x50, 0x60, 0x50])
    put(6, 0x5060, [8, 8])
    return bytes(rom)


class BelmontsRevengeTest(unittest.TestCase):
    def setUp(self):
        self.p = BelmontsRevenge(_cv2_rom())
        self.part = {'stage': 3, 'area': 0}

    def test_records_and_places(self):
        recs = self.p.records('enemy', 3, 0)
        self.assertEqual([r['type'] for r in recs], [0x34, 0x34, 0x1F])
        self.assertEqual([r['section'] for r in recs], [0, 0, 1])
        self.assertEqual(self.p.place(8, recs[0]), (8 * 160 + 0x28 + 0xB0, 8 * 128 + 0x12 + 8))
        rooms = self.p.records('enemy', 3, 1)
        self.assertEqual((rooms[0]['size'], rooms[0]['type'], rooms[0]['room']), (4, 0x33, 1))
        self.assertEqual(self.p.area_count(3), 2)

    def test_where(self):
        ram = bytearray(0x2000)
        ram[0x8C0], ram[0x8C1] = 3, 0
        ram[0xA86], ram[0xA85], ram[0xA8D], ram[0xA8C] = 9, 0x16, 8, 0x20
        self.assertEqual(self.p.where(bytes(ram)), {'part': {'stage': 3, 'area': 0}, 'x': 9 * 160 + 0x16, 'y': 8 * 128 + 0x20})
        ram[0x8C0] = 0
        self.assertIsNone(self.p.where(bytes(ram)))

    def test_objects_and_names(self):
        objs = {o['id']: o for o in self.p.objects(self.part)}
        self.assertEqual(objs['candle:0']['name'], 'Candle')
        self.assertEqual(objs['candle:0']['detail'], 'holds whip upgrade')
        self.assertIn('does', objs['candle:1'])
        self.assertEqual(objs['thing:0']['name'], 'Torch flame')
        self.assertIsNone(objs['thing:0']['remove'])
        self.assertIn('later section', objs['enemy:2']['note'])
        for o in objs.values():
            self.assertFalse(o['name'].startswith('0x'))
        names = [c['name'] for c in self.p.choices()['contents']]
        self.assertIn('Large heart', names)
        self.assertIn('1-up', names)

    def test_candle_contents_write(self):
        e = self.p.edit(self.part, 'candle:1', {'contents': 6})
        o = 3 * 0x4000 + self.p.list_pointer('candle', 3, 0) - 0x4000 + 6 + 3
        self.assertEqual(e['writes'], [(o, 5, 6)])
        self.assertEqual(e['watch']['wanted'], 6)
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'candle:1', {'contents': 0x09})

    def test_enemy_swap_and_remove(self):
        e = self.p.edit(self.part, 'enemy:0', {'type': 0x1F})
        o = 3 * 0x4000 + self.p.list_pointer('enemy', 3, 0) - 0x4000 + 3
        self.assertEqual(e['writes'], [(o, 0x34, 0x1F)])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'enemy:0', {'type': 0x40})
        r = self.p.edit(self.part, 'enemy:0', {}, remove=True)
        rom = bytearray(self.p.rom)
        for at, old, new in r['writes']:
            self.assertEqual(rom[at], old)
            rom[at] = new
        after = BelmontsRevenge(bytes(rom))
        self.assertEqual([x['type'] for x in after.records('enemy', 3, 0)], [0x34, 0x1F])
        self.assertEqual(after.records('enemy', 3, 1)[0]['type'], 0x33)      # the next list is untouched
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'thing:0', {}, remove=True)


if __name__ == '__main__':
    unittest.main()
