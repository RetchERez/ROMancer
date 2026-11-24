"""The Legend of Zelda level profile: decoders and edits, on a made-up cartridge laid out like the real one.

The real game is not part of the tests; these build the same tables at the same addresses (8 banks of 16 KB, fixed bank
7), so a change in how a table is read or written shows here. What the tables mean was proven by replaying the real game
(research/zelda-level-profile.md).
"""
import unittest

from romancer.level_profiles import zelda as zl

H = zl.HEADER


class Cart:
    def __init__(self):
        self.rom = bytearray(H + 8 * 0x4000)

    def at(self, bank, address):
        return H + bank * 0x4000 + address - (0xC000 if bank == 7 else 0x8000)

    def put(self, bank, address, data):
        o = self.at(bank, address)
        self.rom[o:o + len(data)] = bytes(data)

    def word(self, bank, address, value):
        self.put(bank, address, [value & 0xFF, value >> 8])


OW, DG, Q2DG = 0x8400, 0x8700, 0x8D00


def build():
    c = Cart()
    for level in range(10):                           # level blocks: overworld, then levels 1-9 share one block
        c.word(6, 0x8000 + level * 2, OW if level == 0 else DG)
        c.word(6, 0x802A + level * 2, OW if level == 0 else Q2DG)
        c.word(6, 0x8014 + level * 2, 0x9300 + level * 0xFC)
        info = 0x9300 + level * 0xFC
        c.put(6, info + 0x24, [1, 4, 5, 6] if level == 0 else [3, 5, 6, 8])
        c.put(6, info + 0x29, [0x57, 0x49, 0x99, 0x69])
        c.put(6, info + 0x34, [0xFF] * 10)
    # level 1: map rotated by 4 ($6BAB); column 3 (index 7) holds rows 6 and 7; stairway room $7F; start $73, boss $35
    info1 = 0x9300 + 0xFC
    c.put(6, info1 + 0x2D, [4])
    c.put(6, info1 + 0x2F, [0x73])
    c.put(6, info1 + 0x34, [0x7F, 0xFF])
    c.put(6, info1 + 0x3E, [0x35])
    c.put(6, info1 + 0x3F + 7, [0x03])
    # second quest level 1 replaces 2 bytes from +$29
    c.word(6, 0x83A2 + 2, 0x8170)
    c.put(6, 0x83B5 + 1, [1])
    c.put(6, 0x8170, [0xAB, 0xCD])
    # second quest overworld patches: 8 (index, value) pairs and the LDA/STA run at $813B, ended by RTS
    c.put(6, 0x815F, [0x0E, 0, 0, 0, 0, 0, 0, 0])
    c.put(6, 0x8167, [0x7B, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03])
    c.put(6, 0x813B, [0xA9, 0x5A, 0x8D, 0x72, 0x6A, 0x60])     # D[$74] = $5A
    # dungeon rooms (block at $8700): room $73 enemies type $2A x idx 1; room $63 type $4A (D bit 7)
    c.put(6, DG + 2 * 128 + 0x73, [0x6A])            # C: idx 1, type $2A
    c.put(6, DG + 2 * 128 + 0x63, [0x0A])
    c.put(6, DG + 3 * 128 + 0x63, [0x80])
    c.put(6, DG + 0 * 128 + 0x73, [0xA2])            # A: north 5, south 0
    c.put(6, DG + 1 * 128 + 0x73, [0x03 | 1 << 2])   # B: west 0, east 1, palette 3
    c.put(6, DG + 4 * 128 + 0x73, [0x40 | 0x19])     # E: key, upper bits kept
    c.put(6, DG + 5 * 128 + 0x73, [0x17])            # F: spot 1, action 7
    # mixed group list $62 at bank 5 $8600
    c.word(5, 0x873F, 0x8600)
    c.put(5, 0x8600, [0x03, 0x04, 0x03, 0x04, 0x03, 0x04])
    # overworld: room $77 enemies mixed $62 (C $62 low bits $22 | D bit 7), dest cave $10; room $78 dest cave $11
    c.put(6, OW + 2 * 128 + 0x77, [0x62])
    c.put(6, OW + 3 * 128 + 0x77, [0x80 | 0x01])     # D: layout 1
    c.put(6, OW + 1 * 128 + 0x77, [0x10 << 2 | 2])
    c.put(6, OW + 3 * 128 + 0x78, [0x02])
    c.put(6, OW + 1 * 128 + 0x78, [0x11 << 2 | 1])
    c.put(6, OW + 1 * 128 + 0x79, [0x11 << 2])       # another screen with a cave to $11
    c.put(6, OW + 3 * 128 + 0x79, [0x02])
    # caves: items in table E (3 each), prices after 60 bytes
    c.put(6, OW + 4 * 128, [0x3F, 0x01, 0x7F, 0x20, 0x3F, 0x5A])
    # layouts: pointer at bank 5 $9F9C -> 16 column codes per layout; column table pointers at bank 6 $9CD8 + $37
    c.word(5, 0x9F9C, 0x9418)
    c.word(6, 0x9CD8 + 0x37, 0x9BD8)                 # column group 0 (bank 5)
    c.put(5, 0x9BD8, [0x80 | 0x0E] + [0x0E] * 10)    # column 0: all ground
    c.put(5, 0x9BD8 + 11, [0x80 | 0x0E, 0x0C] + [0x0E] * 9)   # column 1: cave on row 1
    c.put(5, 0x9BD8 + 22, [0x80 | 0x40 | 0x0E, 0x28] + [0x0E] * 8)   # column 2: ground twice, a bush on row 2
    c.put(5, 0x9418 + 1 * 16, [0, 1] + [0] * 14)
    c.put(5, 0x9418 + 2 * 16, [0, 0, 2] + [0] * 13)
    return c


class Zelda1Test(unittest.TestCase):
    def setUp(self):
        self.c = build()
        self.z = zl.Zelda1Profile(bytes(self.c.rom))

    def test_rooms_and_info(self):
        z = self.z
        self.assertEqual(z.rooms(1, 1), [0x63, 0x73, 0x7F])
        self.assertEqual(z.stair_rooms(1, 1), [0x7F])
        self.assertEqual((z.start_room(1, 1), z.boss_room(1, 1)), (0x73, 0x35))
        self.assertEqual(z.info(1, 2)[0x29:0x2B], bytes([0xAB, 0xCD]))
        self.assertEqual(z.counts(1, 1), [3, 5, 6, 8])

    def test_enemies(self):
        z = self.z
        e = z.enemy(1, 1, 0x73)
        self.assertEqual((e['type'], e['count']), (0x2A, 5))
        self.assertEqual(z.enemy(1, 1, 0x63)['type'], 0x4A)
        self.assertEqual(z.enemy(1, 1, 0x63)['count'], 1)              # $32-$61: one of a kind
        ow = z.enemy(0, 1, 0x77)
        self.assertEqual(ow['type'], 0x62)
        self.assertEqual(ow['members'], [0x03, 0x04, 0x03, 0x04])         # count index 1 of [1, 4, 5, 6]
        plan = z.edit({'level': 1, 'quest': 1}, 'enemy:73', {'enemy': 0x41, 'count': 3})
        c_at = self.c.at(6, DG + 2 * 128 + 0x73)
        d_at = self.c.at(6, DG + 3 * 128 + 0x73)
        self.assertEqual(plan['writes'], [(c_at, 0x6A, 0xC1), (d_at, 0x00, 0x80)])
        plan = z.edit({'level': 1, 'quest': 1}, 'enemy:63', {}, remove=True)
        self.assertEqual(plan['writes'], [(self.c.at(6, DG + 2 * 128 + 0x63), 0x0A, 0x00), (self.c.at(6, DG + 3 * 128 + 0x63), 0x80, 0x00)])
        self.assertEqual(plan['watch']['members'], [])

    def test_item_door_action(self):
        z = self.z
        it = z.item(1, 1, 0x73)
        self.assertEqual((it['item'], it['x'], it['y'], it['hidden']), (0x19, 0x40, 0x90, True))
        e_at = self.c.at(6, DG + 4 * 128 + 0x73)
        self.assertEqual(z.edit({'level': 1, 'quest': 1}, 'item:73', {'item': 0x17})['writes'], [(e_at, 0x59, 0x57)])
        self.assertEqual(z.edit({'level': 1, 'quest': 1}, 'item:73', {}, remove=True)['writes'], [(e_at, 0x59, 0x43)])
        doors = {d['side']: d['type'] for d in z.doors(1, 1, 0x73)}
        self.assertEqual(doors, {'north': 5, 'south': 0, 'west': 0, 'east': 1})
        b_at = self.c.at(6, DG + 1 * 128 + 0x73)
        plan = z.edit({'level': 1, 'quest': 1}, 'door:73:west', {'door': 7})
        self.assertEqual(plan['writes'], [(b_at, 0x07, 0xE7)])
        self.assertFalse(plan['watch']['passable'])
        f_at = self.c.at(6, DG + 5 * 128 + 0x73)
        self.assertEqual(z.edit({'level': 1, 'quest': 1}, 'action:73', {'action': 4})['writes'], [(f_at, 0x17, 0x14)])
        with self.assertRaises(ValueError):
            z.edit({'level': 1, 'quest': 1}, 'action:73', {'action': 9})

    def test_overworld_layout_and_entrances(self):
        z = self.z
        grid = z.squares(0x77)
        self.assertEqual(grid[1][1], 0x0C)
        self.assertEqual(z.entrances(0x77), [{'square': 0x0C, 'column': 1, 'row': 1}])
        self.assertEqual(z.squares(0x78)[2][2], 0x28)                   # the bit-6 square is used twice first
        self.assertEqual(z.entrances(0x78)[0]['square'], 0x28)
        self.assertEqual(z.cave_users(0), [0x77])
        b_at = self.c.at(6, OW + 1 * 128 + 0x77)
        plan = z.edit({'level': 0, 'quest': 1}, 'entrance:77:0', {'dest': 2})
        self.assertEqual(plan['writes'], [(b_at, 0x42, 0x0A)])
        cave_at = self.c.at(6, OW + 4 * 128)
        plan = z.edit({'level': 0, 'quest': 1}, 'entrance:77:0', {'item2': 0x02, 'item3': 0x3F})
        self.assertEqual(plan['writes'], [(cave_at + 1, 0x01, 0x02)])
        self.assertEqual(plan['watch']['items'], [0x3F, 0x02, 0x7F])
        with self.assertRaises(ValueError):                             # two screens share cave $11
            z.edit({'level': 0, 'quest': 1}, 'entrance:78:0', {'item1': 0x02})

    def test_second_quest_overworld(self):
        z = self.z
        self.assertEqual(z.room(0, 2, 0x0E)['b'], 0x7B)
        self.assertIsNone(z.room(0, 2, 0x0E)['b_at'])
        self.assertEqual(z.room(0, 2, 0x74)['d'], 0x5A)

    def test_objects_and_where(self):
        z = self.z
        ids = {o['id'] for o in z.objects({'level': 1, 'quest': 1})}
        self.assertTrue({'enemy:73', 'item:73', 'door:73:north', 'action:73', 'enemy:63'} <= ids)
        ram = bytearray(0x800)
        ram[0x12], ram[0x10], ram[0xEB] = 5, 1, 0x73
        self.assertEqual(z.where(ram), {'part': {'level': 1, 'quest': 1}, 'x': 3 * 256, 'y': 7 * 240})
        ram[0x12], ram[0x13], ram[0x98], ram[0xFD], ram[0xFF], ram[0xEB] = 7, 3, 1, 0x40, 0xB0, 0x74   # scrolling right
        self.assertEqual(z.where(ram)['x'], 3 * 256 + 0x40)
        ram[0x98], ram[0xFF], ram[0xEB] = 2, 0xB1, 0x73                                              # scrolling left
        self.assertEqual(z.where(ram)['x'], 3 * 256 + 256 + 0x40)
        ram[0x12] = 0x0B
        self.assertIsNone(z.where(ram))
        self.assertIn('enemies_1', z.choices())


# ---------------------------------------------------------------- Zelda II

def build2():
    """Zelda II tables at their real places: scene tables ($8523/$85A1, $A000/$A07E) of every scene bank, enemy lists
    in the bank's $88A0 block (cartridge RAM $7000), the line table at bank 7 $D5FB and map entrances at $869D/$86DC."""
    c = Cart()
    c.put(7, 0xD5FB, [0x30, 0x50, 0x60, 0x70, 0x80, 0x90, 0xA0, 0xB0])
    for bank in (1, 2, 3, 4, 5):
        for area in range(63):
            c.word(bank, 0x8523 + 2 * area, 0x9000)            # every area: an empty layout
            c.word(bank, 0x85A1 + 2 * area, 0x7000)            # and the empty list at $7000
            c.word(bank, 0xA000 + 2 * area, 0x9000)
            c.word(bank, 0xA07E + 2 * area, 0x7000)
        c.put(bank, 0x9000, [4, 0, 0, 0])
        c.put(bank, 0x88A0, [1])
        for k in range(62):                                    # map entrances: all lead to area $3E of world 0
            c.put(bank, 0x869D + k, [0x3E])
            c.put(bank, 0x86DC + k, [0])
    # towns: area 2 list at $7010 (two enemies), layout $9100 with an item
    c.word(3, 0x85A1 + 2 * 2, 0x7010)
    c.put(3, 0x88A0 + 0x10, [5, 0x7D, 0x17, 0xF5, 0xE2])      # (height 7, col D, screen 0, $17), (placed, col 5, screen 3, $22)
    c.word(3, 0x8523 + 2 * 2, 0x9100)
    c.put(3, 0x9100, [11, 0x60, 0xA0, 0x01, 0x32, 0x10, 0xE2, 0x00, 0x84, 0x0F, 0x0A])   # object; to screen 2; item at x 4
    c.word(3, 0x85A1 + 2 * 3, 0x7020)                          # areas 3 and 4 (different layouts) share a list
    c.word(3, 0x85A1 + 2 * 4, 0x7020)
    c.word(3, 0x8523 + 2 * 4, 0x9200)
    c.put(3, 0x9200, [4, 0, 0, 0])
    c.put(3, 0x88A0 + 0x20, [3, 0x10, 0x05])
    c.word(3, 0x8523 + 2 * 6, 0x9300)                          # area 6: its own layout with a key
    c.put(3, 0x9300, [7, 0, 0, 0, 0x93, 0x0F, 0x08])
    # West Hyrule: area $22 (no entrance) list at $7040, followed by its big-monster list
    c.word(1, 0x85A1 + 2 * 0x22, 0x7040)
    c.put(1, 0x88A0 + 0x40, [3, 0x7C, 0x04, 5, 0x0F, 0x21, 0x70, 0x45])
    return c


class Zelda2Test(unittest.TestCase):
    def setUp(self):
        self.c = build2()
        self.z = zl.Zelda2Profile(bytes(self.c.rom))

    def test_where(self):
        ram = bytearray(0x800)
        ram[0x736], ram[0x707], ram[0x706], ram[0x561], ram[0x72A], ram[0x72C] = 0x0B, 1, 0, 2, 3, 0x10
        self.assertEqual(self.z.where(bytes(ram)), {'part': {'set': 4, 'area': 2}, 'x': 0x310, 'y': 0})
        ram[0x707], ram[0x706], ram[0x70A] = 0, 1, 2
        self.assertEqual(self.z.where(bytes(ram))['part']['set'], 3)    # Maze Island: region 1, came from the east
        ram[0x70A] = 0
        self.assertEqual(self.z.where(bytes(ram))['part']['set'], 1)
        ram[0x707] = 4
        self.assertEqual(self.z.where(bytes(ram))['part']['set'], 5)
        ram[0x736] = 5
        self.assertIsNone(self.z.where(bytes(ram)))

    def test_enemies(self):
        e = self.z.enemies(4, 2)
        self.assertEqual([(x['height'], x['column'], x['screen'], x['type'], x['placed']) for x in e],
                         [(7, 0xD, 0, 0x17, False), (7, 5, 3, 0x22, True)])
        self.assertEqual(e[0]['at'], self.c.at(3, 0x88B1))
        objs = {o['id']: o for o in self.z.objects({'set': 4, 'area': 2})}
        self.assertEqual((objs['enemy:0']['x'], objs['enemy:0']['y']), (0xD8, 0xB0 + zl.Zelda2Profile.FEET))
        self.assertEqual(objs['enemy:0']['name'], 'Woman (red dress)')
        self.assertIn('already placed', objs['enemy:1']['note'])
        plan = self.z.edit({'set': 4, 'area': 2}, 'enemy:0', {'enemy': 0x22})
        self.assertEqual(plan['writes'], [(self.c.at(3, 0x88B2), 0x17, 0x22)])
        plan = self.z.edit({'set': 4, 'area': 2}, 'enemy:0', {}, True)
        self.assertEqual(plan['writes'], [(self.c.at(3, 0x88B1), 0x7D, 0xFD)])
        self.assertEqual(plan['watch']['offset'], 1)
        with self.assertRaises(ValueError):
            self.z.edit({'set': 4, 'area': 2}, 'enemy:0', {'enemy': 0x3F})     # not a type the set uses
        row = self.z.objects({'set': 4, 'area': 3})[0]                          # list shared by two scenes
        self.assertEqual(row['fields'], [])
        with self.assertRaises(ValueError):
            self.z.edit({'set': 4, 'area': 3}, 'enemy:0', {'enemy': 0x17})

    def test_big_monster_list(self):
        ids = [o['id'] for o in self.z.objects({'set': 0, 'area': 0x22})]
        self.assertEqual(ids, ['enemy:0', 'strong:0', 'strong:1'])
        self.assertEqual(self.z.list_at(0, 0x22, True), 0x7043)
        plan = self.z.edit({'set': 0, 'area': 0x22}, 'strong:1', {'enemy': 0x04})
        self.assertEqual(plan['writes'], [(self.c.at(1, 0x88A0 + 0x47), 0x45, 0x44)])
        self.assertTrue(plan['watch']['strong'])
        with self.assertRaises(ValueError):
            self.z.edit({'set': 0, 'area': 0x22}, 'strong:1', {}, True)
        self.assertEqual(self.z.objects({'set': 0, 'area': 0x3E}), [])       # an entrance's scene: no big-monster list

    def test_items(self):
        its = self.z.items(4, 2)
        self.assertEqual([(i['item'], i['screen'], i['column'], i['row']) for i in its], [(0x0A, 2, 4, 8)])
        self.assertEqual(its[0]['at'], self.c.at(3, 0x910A))
        plan = self.z.edit({'set': 4, 'area': 2}, 'item:0', {'item': 0x0D})
        self.assertEqual(plan['writes'], [(self.c.at(3, 0x910A), 0x0A, 0x0D)])
        self.assertEqual(plan['watch'], {'kind': 'item', 'set': 4, 'area': 2, 'screen': 2, 'column': 4, 'item': 0x0D,
                                         'name': 'P-bag (500 points)'})
        self.assertEqual(self.z.items(4, 6)[0]['item'], 0x08)
        self.c.word(3, 0x8523 + 2 * 7, 0x9300)                  # area 7 now shares area 6's layout
        z = zl.Zelda2Profile(bytes(self.c.rom))
        self.assertEqual(z.objects({'set': 4, 'area': 6})[0]['fields'], [])
        with self.assertRaises(ValueError):
            z.edit({'set': 4, 'area': 6}, 'item:0', {'item': 0x0D})

    @staticmethod
    def ram():
        ram = bytearray(0x800)
        ram[0x736], ram[0x707], ram[0x561], ram[0x72A] = 0x0B, 1, 2, 2
        return ram

    def test_watchers(self):
        plan = self.z.edit({'set': 4, 'area': 2}, 'enemy:0', {'enemy': 0x22})
        w = self.z.watcher(plan['watch'])
        ram = self.ram()
        ram[0xB6], ram[0xBC], ram[0xA1] = 1, 1, 0x22
        self.assertTrue(w.see(bytes(ram), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.z.watcher(plan['watch'])
        ram[0xA1] = 0x17
        w.see(bytes(ram), 0, 'original')
        self.assertEqual(w.result()['state'], 'bad')
        removed = self.z.watcher(self.z.edit({'set': 4, 'area': 2}, 'enemy:0', {}, True)['watch'])
        ram = self.ram()
        ram[0x732], ram[0x734] = 0, 0xD
        for f in range(60):
            if removed.see(bytes(ram), f, 'changed'):
                break
        self.assertEqual(removed.result()['state'], 'good')
        item = self.z.watcher(self.z.edit({'set': 4, 'area': 2}, 'item:0', {'item': 0x0D})['watch'])
        ram = self.ram()
        ram[0xB6], ram[0xA1], ram[0x3C], ram[0x4E], ram[0xAF] = 1, 1, 2, 0x43, 0x0D
        self.assertTrue(item.see(bytes(ram), 0, 'changed'))
        self.assertEqual(item.result()['state'], 'good')
        self.assertEqual(self.z.watcher({'kind': 'item', 'set': 4, 'area': 2, 'screen': 2, 'column': 4, 'item': 0x0D,
                                         'name': ''}).result()['state'], 'warn')

    def test_registered(self):
        self.assertIn(zl.Zelda2Profile, zl.PROFILES)
        self.assertIn(zl.Zelda1Profile, zl.PROFILES)


if __name__ == '__main__':
    unittest.main()
