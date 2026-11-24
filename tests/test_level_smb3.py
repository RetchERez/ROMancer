"""Super Mario Bros. 3 level profile: decoding and edits on a made-up cartridge laid out like the real one.

The real game is not part of the tests. These build the same tables at the same addresses (map tables in bank 12,
builder dispatch in bank 30, builder tables in the tileset's bank, block tile tables in bank 14, enemy lists in bank 6),
so a change in how a table is read or written shows here. What the tables mean was proven by replaying the real game
(research/smb3-level-profile.md).
"""
import unittest

from romancer.level_profiles import smb3

H = 16


class Cart:
    """A blank MMC3 cartridge: 32 banks of 8 KB."""

    def __init__(self):
        self.rom = bytearray(H + 32 * 0x2000)

    def at(self, bank, address):
        return H + bank * 0x2000 + (address & 0x1FFF)

    def put(self, bank, address, data):
        o = self.at(bank, address)
        self.rom[o:o + len(data)] = bytes(data)

    @staticmethod
    def word(v):
        return [v & 0xFF, v >> 8]


ONE_TILES = [0x60, 0x61, 0x62, 0x64, 0x65, 0x66, 0x68, 0x69, 0x6A, 0x6C, 0x6D, 0x6E, 0x6F, 0x70, 0x44, 0x45,
             0x03, 0x2F, 0x30, 0x31, 0x73, 0x74, 0x75, 0x46, 0xF2]
ROW_TILES = [0x67, 0x63, 0x6B, 0x79, 0xBC, 0x2E, 0x72, 0x40]
MAIN, ALT = 0xB000, 0xB100
MAIN_OBJ, ALT_OBJ = 0xC100, 0xC200


def build(extra_world_objects=None):
    c = Cart()
    # tileset banks (bank 30 $83E9 = $A000 bank, $83D6 = $C000 bank): tileset 1 builds from banks 15 and 14
    c.put(30, 0x83E9, [0x0B] + [0x0F] * 18)
    c.put(30, 0x83D6, [0x0A] + [0x0E] * 18)
    # builder dispatch by tileset: $9A4F (kinds of $10 and up), $9A7B (smaller kinds)
    for ts in range(19):
        c.put(30, 0x9A4F + 2 * ts, Cart.word(0xA421))
        c.put(30, 0x9A7B + 2 * ts, Cart.word(0xA498))
    c.put(15, 0xA419, [0, 15, 30, 45, 60, 75, 90, 105])          # first entry of each class
    c.put(15, 0xA421, [0xEA, 0xEA, 0x20, 0x99, 0xFE])            # ... JSR $FE99 and the table
    var = [0xD095] * 15 + [0xCB1F] * 8 + [0xC64C] * 7 + [0xD095] * 15
    var[11] = 0xD306                                              # class 0 kind $C reads a 4th byte
    c.put(15, 0xA426, [b for w in var for b in Cart.word(w)])
    c.put(15, 0xA498, [0x20, 0x99, 0xFE])
    fix = [0xD226] * 16 + [0xCADD] * 16 + [0xCADD] * 9 + [0xD226] * 7 + [0xD226] * 64
    c.put(15, 0xA49B, [b for w in fix for b in Cart.word(w)])
    c.put(14, 0xD095, [0x60])
    c.put(14, 0xD226, [0x60])
    c.put(14, 0xC64C, [0x60])
    c.put(14, 0xCADD, [0x60])
    c.put(14, 0xCB1F, [0x60])
    c.put(14, 0xD306, [0xA0, 0x00, 0xB1, 0x61, 0x60])           # LDY #0, LDA ($61),Y, RTS
    c.put(14, 0xCAC4, ONE_TILES)
    c.put(14, 0xCB16, ROW_TILES)
    # layouts (bank 15): main area of 2 screens with its way out on screen 2, and the area the pipe leads to
    c.put(15, MAIN, Cart.word(ALT) + Cart.word(ALT_OBJ) + [0x01, 0x00, 0x01, 0x00, 0x00] +
          [0x00, 0x00, 0xC0, 0x26,          # 4-byte record (ground)
           0x20 | 19, 0x0E, 0x21,           # row of 2 ? blocks with coins, screen 0 column 14
           0x20 | 19, 0x0F, 0x01,           # one ? block with a leaf
           0x40 | 22, 0x13, 0x01,           # note block with a flower, screen 1 column 3
           0xE1, 0x42, 0x80,                # the way out of screen 1: screen 0 of the other area, column 8
           0xFF])
    c.put(15, ALT, Cart.word(MAIN) + Cart.word(MAIN_OBJ) + [0x01, 0x00, 0x01, 0x00, 0x00] +
          [0x20 | 20, 0x00, 0x0E, 0xE0, 0x71, 0x19, 0xFF])
    # enemy lists (bank 6)
    c.put(6, MAIN_OBJ, [0x01, 0x72, 0x0E, 0x19, 0xA6, 0x16, 0x17, 0x6C, 0x20, 0x19, 0xFF])
    c.put(6, ALT_OBJ, [0x01, 0xFF])
    # world map (bank 12): world 1 has one level at row 2, column 4 (tile $03, level 1)
    for world in range(9):
        base = 0xB500 + world * 0x60
        c.put(12, 0xB3DC + 2 * world, Cart.word(base))
        c.put(12, 0xB3EE + 2 * world, Cart.word(base + 0x10))
        c.put(12, 0xB400 + 2 * world, Cart.word(base + 0x20))
        c.put(12, 0xB412 + 2 * world, Cart.word(base + 0x40))
        c.put(12, 0xA598 + 2 * world, Cart.word(0xA600))
    c.put(12, 0xB500, [0x21])
    c.put(12, 0xB510, [0x04])
    c.put(12, 0xB520, Cart.word(MAIN_OBJ))
    c.put(12, 0xB540, Cart.word(MAIN))
    c.put(12, 0xA604, [0x03])
    if extra_world_objects:                          # world 2: an area that reads the main enemy list from the middle
        c.put(12, 0xB560, [0x21])
        c.put(12, 0xB570, [0x04])
        c.put(12, 0xB580, Cart.word(extra_world_objects))
        c.put(12, 0xB5A0, Cart.word(ALT))
    return c


PART = {'world': 1, 'tileset': 1, 'layout': MAIN, 'objects': MAIN_OBJ}


def ram_for(tileset, layout, objects):
    ram = bytearray(0x2800)
    ram[0x70A] = tileset
    ram[0x800 + 0x1EB9], ram[0x800 + 0x1EBA] = layout & 0xFF, layout >> 8
    ram[0x800 + 0x1EBB], ram[0x800 + 0x1EBC] = objects & 0xFF, objects >> 8
    return ram


class Decode(unittest.TestCase):
    def setUp(self):
        self.c = build()
        self.p = smb3.SMB3Profile(bytes(self.c.rom))

    def test_records_and_fourth_byte(self):
        rows = self.p.records(1, MAIN)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]['b3'], 0x26)                  # the builder reads ($61): 4 bytes
        self.assertEqual(rows[1]['at'], MAIN + 9 + 4)
        self.assertEqual([r['builder'] for r in rows[1:4]], [0xCB1F, 0xCADD, 0xCADD])
        self.assertEqual(rows[4]['kind'], 'way')

    def test_areas_and_names(self):
        areas = self.p.areas()
        self.assertIn((1, MAIN), areas)
        self.assertIn((1, ALT), areas)
        self.assertEqual(self.p.part_name(PART), 'World 1, level 1')
        self.assertEqual(self.p.part_name({'tileset': 1, 'layout': ALT}), 'World 1, level 1, the area a pipe or door leads to')

    def test_where(self):
        ram = ram_for(1, MAIN, MAIN_OBJ)
        ram[0x727], ram[0xFD], ram[0x12], ram[0xFC] = 0, 0x20, 1, 0xEF
        self.assertEqual(self.p.where(ram), {'part': PART, 'x': 0x120, 'y': 0xEF + 9})
        self.assertIsNone(self.p.where(ram_for(0, MAIN, MAIN_OBJ)))       # the world map

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects(PART)}
        self.assertEqual(objects['enemy:0']['name'], 'Goomba')
        self.assertEqual((objects['enemy:0']['x'], objects['enemy:0']['y']), (0x0E * 16 + 8, 0x19 * 16 + 16))
        self.assertEqual(objects['enemy:1']['name'], 'Venus Fire Trap (red)')
        self.assertEqual(objects['row:1']['name'], 'Row of ? blocks with coins')
        self.assertEqual(objects['row:1']['detail'], '2 long')
        self.assertEqual(objects['block:2']['name'], '? block with a mushroom, or a leaf when Mario is big')
        self.assertEqual((objects['block:2']['x'], objects['block:2']['y']), (15 * 16 + 8, 19 * 16 + 16))
        self.assertEqual(objects['block:3']['name'], 'Note block with a mushroom, or a fire flower when Mario is big')
        self.assertEqual(objects['block:3']['x'], 256 + 3 * 16 + 8)
        self.assertEqual(objects['way:4']['detail'], 'leads to screen 1 of World 1, level 1, the area a pipe or door leads to')
        self.assertNotIn('enemy:x', objects)
        values = [c['value'] for c in objects['block:2']['fields'][0]['choices']]
        self.assertIn(0x12, values)                          # ? block with a star
        self.assertIn(0x21, values)                          # note block with a flower (class 2 kind 1)
        self.assertIn(0x15, values)                          # the muncher tile is one of the game's single blocks too


class Edits(unittest.TestCase):
    def setUp(self):
        self.c = build()
        self.p = smb3.SMB3Profile(bytes(self.c.rom))

    def test_block_same_class(self):
        plan = self.p.edit(PART, 'block:2', {'block': 0x12})
        at = self.c.at(15, MAIN + 9 + 4 + 3)
        self.assertEqual(plan['writes'], [(at + 2, 0x01, 0x02)])
        self.assertEqual(plan['watch']['address'], 0x6000 + 19 * 16 + 15)
        self.assertEqual(plan['watch']['tiles'], [0x62])

    def test_block_other_class(self):
        plan = self.p.edit(PART, 'block:2', {'block': 0x20})          # hidden note block: class 2 kind 0
        at = self.c.at(15, MAIN + 9 + 4 + 3)
        self.assertEqual(plan['writes'], [(at, 0x20 | 19, 0x40 | 19), (at + 2, 0x01, 0x00)])

    def test_block_one_up_may_be_remembered(self):
        plan = self.p.edit(PART, 'block:2', {'block': 0x1B})
        self.assertEqual(plan['watch']['tiles'], [0x6E, 0x5F])

    def test_row(self):
        plan = self.p.edit(PART, 'row:1', {'row': 1})
        at = self.c.at(15, MAIN + 9 + 4)
        self.assertEqual(plan['writes'], [(at + 2, 0x21, 0x11)])          # width kept
        self.assertEqual(plan['watch']['tiles'], [0x67])

    def test_enemy_swap(self):
        plan = self.p.edit(PART, 'enemy:0', {'id': 0x6C})
        self.assertEqual(plan['writes'], [(self.c.at(6, MAIN_OBJ + 1), 0x72, 0x6C)])
        self.assertEqual(plan['watch']['name'], 'Koopa Troopa (green)')
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'enemy:0', {'id': 0x99})                    # not used anywhere in the game

    def test_enemy_choices_follow_sprite_banks(self):
        c = build()
        c.put(4, 0xA144 + 0x72 - 0x6C, [0xCF])          # Goomba: sprite bank $4F in $071E
        c.put(5, 0xA144 + 0xA6 - 0x90, [0xCF])          # Venus Fire Trap: the same
        c.put(4, 0xA144 + 0x6C - 0x6C, [0xB3])          # Koopa Troopa: bank $33 in $071E
        p = smb3.SMB3Profile(bytes(c.rom))
        self.assertEqual(p.sprite_need(0x72), (0x71E, 0x4F))
        self.assertEqual(p.enemy_choices(MAIN_OBJ, 2), [0x72, 0xA6])        # the Koopa may become what the others need
        self.assertEqual(p.enemy_choices(MAIN_OBJ, 0), [])                  # the others need two banks in $071E already
        with self.assertRaises(ValueError):
            p.edit(PART, 'enemy:0', {'id': 0xA6})
        objects = {o['id']: o for o in p.objects(PART)}
        self.assertEqual([c['value'] for c in objects['enemy:2']['fields'][0]['choices']], [0x72, 0xA6])

    def test_enemy_remove(self):
        plan = self.p.edit(PART, 'enemy:0', {}, remove=True)
        rom = bytearray(self.c.rom)
        for offset, old, new in plan['writes']:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        start = self.c.at(6, MAIN_OBJ)
        self.assertEqual(bytes(rom[start:start + 8]), bytes([0x01, 0xA6, 0x16, 0x17, 0x6C, 0x20, 0x19, 0xFF]))
        self.assertEqual(plan['watch']['record'], [0x72, 0x0E, 0x19])

    def test_enemy_remove_refused_for_shared_list(self):
        p = smb3.SMB3Profile(bytes(build(extra_world_objects=MAIN_OBJ + 3).rom))
        with self.assertRaises(ValueError):
            p.edit(PART, 'enemy:0', {}, remove=True)

    def test_way(self):
        plan = self.p.edit(PART, 'way:4', {'to_screen': 1})
        at = self.c.at(15, MAIN + 9 + 4 + 9)
        self.assertEqual(plan['writes'], [(at + 2, 0x80, 0x81)])
        self.assertEqual(plan['watch']['screen'], 1)
        with self.assertRaises(ValueError):
            self.p.edit(PART, 'way:4', {'to_screen': 2})                   # the other area has 2 screens


class Watchers(unittest.TestCase):
    def setUp(self):
        self.p = smb3.SMB3Profile(bytes(build().rom))

    def play(self, watcher, ram, frames=80):
        for frame in range(0, frames, 4):
            if watcher.see(ram, frame, 'changed'):
                break
        return watcher.result()

    def test_block(self):
        plan = self.p.edit(PART, 'block:2', {'block': 0x12})
        ram = ram_for(1, MAIN, MAIN_OBJ)
        ram[0x800 + 19 * 16 + 15] = 0x62
        self.assertEqual(self.play(self.p.watcher(plan['watch']), ram)['state'], 'good')
        ram[0x800 + 19 * 16 + 15] = 0x61
        self.assertEqual(self.play(self.p.watcher(plan['watch']), ram)['state'], 'bad')
        self.assertEqual(self.play(self.p.watcher(plan['watch']), ram_for(1, ALT, ALT_OBJ))['state'], 'warn')

    def test_enemy(self):
        plan = self.p.edit(PART, 'enemy:0', {'id': 0x6C})
        ram = ram_for(1, MAIN, MAIN_OBJ)
        ram[0x800 + 0x1B40:0x800 + 0x1B48] = bytes([0x01, 0x6C, 0x0E, 0x19, 0xFF, 0, 0, 0])
        ram[0x661 + 3], ram[0x671 + 3], ram[0x659 + 3] = 2, 0x6C, 0
        self.assertEqual(self.play(self.p.watcher(plan['watch']), ram)['state'], 'good')
        ram[0x671 + 3] = 0x72
        self.assertEqual(self.play(self.p.watcher(plan['watch']), ram)['state'], 'bad')

    def test_remove(self):
        plan = self.p.edit(PART, 'enemy:0', {}, remove=True)
        ram = ram_for(1, MAIN, MAIN_OBJ)
        ram[0x800 + 0x1B40:0x800 + 0x1B45] = bytes([0x01, 0xA6, 0x16, 0x17, 0xFF])
        self.assertEqual(self.play(self.p.watcher(plan['watch']), ram)['state'], 'good')
        ram[0x800 + 0x1B40:0x800 + 0x1B45] = bytes([0x01, 0x72, 0x0E, 0x19, 0xFF])
        self.assertEqual(self.play(self.p.watcher(plan['watch']), ram)['state'], 'bad')

    def test_way(self):
        plan = self.p.edit(PART, 'way:4', {'to_screen': 1})
        w = self.p.watcher(plan['watch'])
        here = ram_for(1, MAIN, MAIN_OBJ)
        here[0x75] = 1
        there = ram_for(1, ALT, ALT_OBJ)
        there[0x75] = 1
        w.see(here, 0, 'changed')
        w.see(there, 4, 'changed')
        self.assertEqual(w.result()['state'], 'good')


if __name__ == '__main__':
    unittest.main()
