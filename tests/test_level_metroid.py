"""Metroid and Kid Icarus level profiles: the decoders and the edits, on made-up cartridges laid out like the real ones.

The real games are not part of the tests; these build the same tables at the same addresses, so a change in how a table
is read or written shows here. What the tables mean was proven by replaying the real games (research notes,
research/metroid-level-profile.md).
"""
import unittest

from romancer.level_profiles import metroid as m

H = m.HEADER


class Cart:
    """A blank MMC1 cartridge (8 banks of 16 KB) with helpers that write at CPU addresses of a bank."""

    def __init__(self):
        self.rom = bytearray(H + 8 * 0x4000)

    def at(self, bank, address):
        return m._Cart.offset(bank, address)

    def put(self, bank, address, data):
        o = self.at(bank, address)
        self.rom[o:o + len(data)] = bytes(data)

    @staticmethod
    def word(value):
        return [value & 0xFF, value >> 8]


def metroid_cart():
    """Brinstar (bank 1): rooms 0-2 on map row 14 at x 3, 4, 5, a door on the right of room 2, a power-up at (4, 14)."""
    c = Cart()
    world = [0xFF] * 1024
    world[14 * 32 + 3], world[14 * 32 + 4], world[14 * 32 + 5], world[14 * 32 + 6] = 0, 1, 2, 0
    c.rom[m.Metroid.WORLD:m.Metroid.WORLD + 1024] = bytes(world)
    for bank in (1, 2, 3, 4, 5):
        c.put(bank, 0x9598, Cart.word(0xA000) + Cart.word(0xA100) + Cart.word(0xA106))   # items, rooms, structures
        c.put(bank, 0xA000, [0xFF] + Cart.word(0xFFFF))                                  # no items (row $FF)
    # bank 1: three rooms (room pointers $A100, structures start $A106 so there are 3 rooms)
    c.put(1, 0xA100, Cart.word(0xA200) + Cart.word(0xA220) + Cart.word(0xA240))
    c.put(1, 0xA200, [0x02, 0x00, 0x11, 0x01, 0xFD, 0x51, 0x05, 0x25, 0x41, 0x85, 0x2B, 0xFF])   # two Zoomers
    c.put(1, 0xA220, [0x01, 0xFD, 0x21, 0x04, 0x38, 0x07, 0x07, 0xB7, 0xFF])                     # a Skree and a pipe
    c.put(1, 0xA240, [0x03, 0x10, 0x0B, 0x03, 0xFD, 0x02, 0xA1, 0x11, 0x02, 0x7B, 0xFF])         # right door, a Ripper
    # items: row 14 -> place x 4 holds a Maru Mari (4) at YX $96
    c.put(1, 0xA000, [0x0E] + Cart.word(0xFFFF) + [0x04, 0xFF, 0x02, 0x04, 0x96, 0x00])
    return c


class MetroidTest(unittest.TestCase):
    def setUp(self):
        self.c = metroid_cart()
        self.p = m.MetroidProfile(bytes(self.c.rom))
        self.part = {'area': 0, 'x': 3, 'y': 14, 'way': 'across'}

    def test_rooms_and_strip(self):
        self.assertEqual(self.p.room_count(0), 3)
        room = self.p.room(0, 0)
        self.assertEqual([e['bytes'] for e in room['entries']], [[0x51, 0x05, 0x25], [0x41, 0x85, 0x2B]])
        self.assertEqual(self.p.doors(0, 2), {0: 1})
        # the door on the right of (5, 14) ends the row; (6, 14) is beyond it
        self.assertEqual(self.p.strip(0, 3, 14, 'across'), [(3, 14), (4, 14), (5, 14)])
        self.assertEqual(self.p.strip(0, 4, 14, 'down'), [(4, 14)])

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects(self.part)}
        self.assertEqual(set(objects), {'enemy:3:14:0', 'enemy:3:14:1', 'enemy:4:14:0', 'pipe:4:14:1', 'door:5:14:0',
                                        'enemy:5:14:1', 'item:4:14:0'})
        zoomer = objects['enemy:3:14:0']
        self.assertEqual((zoomer['name'], zoomer['x'], zoomer['y']), ('Zoomer', 3 * 256 + 5 * 16 + 8, 14 * 240 + 2 * 16 + 16))
        self.assertEqual(objects['enemy:3:14:1']['name'], 'Zoomer, tough')
        self.assertEqual(objects['door:5:14:0']['name'], 'Blue door (any shot)')
        self.assertEqual(objects['door:5:14:0']['x'], 5 * 256 + 240)
        item = objects['item:4:14:0']
        self.assertEqual((item['name'], item['x'], item['y']), ('Maru Mari (morph ball)', 4 * 256 + 6 * 16 + 8, 14 * 240 + 9 * 16 + 16))
        self.assertIsNone(objects['pipe:4:14:1']['remove'])
        kinds = [c['value'] for c in self.p.choices()['enemies0']]
        self.assertEqual(kinds, [0x02, 0x04, 0x05, 0x85])

    def test_enemy_edits(self):
        plan = self.p.edit(self.part, 'enemy:3:14:0', {'kind': 0x04})
        self.assertEqual(plan['writes'], [(self.c.at(1, 0xA206), 0x05, 0x04)])
        self.assertEqual((plan['watch']['slot'], plan['watch']['spawn_y'], plan['watch']['spawn_x']), (0x50, 0x28, 0x5C))
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'enemy:3:14:0', {'kind': 0x06})          # not a kind Brinstar's rooms use here
        plan = self.p.edit(self.part, 'enemy:3:14:0', {}, remove=True)
        rom = bytearray(self.c.rom)
        for offset, old, new in plan['writes']:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        self.assertEqual([e['bytes'] for e in m.Metroid(bytes(rom)).room(0, 0)['entries']], [[0x41, 0x85, 0x2B]])

    def test_door_and_item_edits(self):
        plan = self.p.edit(self.part, 'door:5:14:0', {'door': 0})
        self.assertEqual(plan['writes'], [(self.c.at(1, 0xA246), 0xA1, 0xA0)])
        self.assertEqual(plan['watch']['slot'], m.MetroidProfile.DOOR_SLOTS[((5 + 14) << 1) & 3])
        plan = self.p.edit(self.part, 'item:4:14:0', {'item': 8})
        self.assertEqual(plan['writes'], [(self.c.at(1, 0xA006), 0x04, 0x08)])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'item:4:14:0', {'item': 12})

    def test_where_and_roles(self):
        ram = bytearray(0x2800)
        ram[0x1E], ram[0x74], ram[0x49], ram[0x50], ram[0x4F], ram[0xFD] = 3, 0, 3, 4, 14, 2
        self.assertEqual(self.p.where(ram), {'part': {'area': 0, 'x': 3, 'y': 14, 'way': 'across'}, 'x': 3 * 256 + 2, 'y': 14 * 240})
        ram[0x49] = 2
        self.assertEqual(self.p.where(ram)['x'], 4 * 256 + 2)
        ram[0x1E] = 4
        self.assertIsNone(self.p.where(ram))
        self.assertEqual([self.p.tile_role(t) for t in (0x00, 0x6F, 0x70, 0x9F, 0xA0, 0xFF)],
                         ['solid', 'solid', 'breakable', 'breakable', 'open', 'open'])

    def test_watchers(self):
        plan = self.p.edit(self.part, 'enemy:5:14:1', {'kind': 0x05})
        ram = bytearray(0x2800)
        ram[0x1E], ram[0x74], ram[0x49], ram[0x50], ram[0x4F] = 3, 0, 3, 5, 14
        slot = plan['watch']['slot']
        ram[0x800 + 0x6AF4 - 0x6000 + slot] = 1
        ram[0x400 + slot], ram[0x401 + slot] = plan['watch']['spawn_y'], plan['watch']['spawn_x']
        ram[0x800 + 0x6B02 - 0x6000 + slot] = 0x05
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[0x800 + 0x6B02 - 0x6000 + slot] = 0x02
        w = self.p.watcher(plan['watch'])
        w.see(ram, 0, 'changed')
        self.assertEqual(w.result()['state'], 'bad')
        plan = self.p.edit(self.part, 'door:5:14:0', {'door': 2})
        door = plan['watch']['slot']
        ram[0x300 + door], ram[0x30E + door], ram[0x307 + door] = 1, 0xF0, 2
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        self.assertEqual(self.p.watcher(plan['watch']).result()['state'], 'warn')


def kid_icarus_cart():
    """World 1 data at bank 6 $9940 (the game's copy at $7000): stage 0 with two screens, stage 1 with one, and one
    record in the first and the last spawn list."""
    c = Cart()
    k = m.KidIcarus

    def put(address, data):
        c.put(6, 0x9940 + address - 0x7000, data)
    put(0x7BF0, Cart.word(0x7C1A) + Cart.word(0x7C20))
    put(0x7C1A, Cart.word(0x7000) + Cart.word(0x7010) + [0xFF, 0xFF])
    put(0x7C20, Cart.word(0x7010) + [0xFF, 0xFF])
    put(0x7000, [0x01, 0x00, 0x1A, 0x01, 0xFD, 0xFF])
    put(0x7010, [0x00, 0x08, 0x00, 0x01, 0xFD, 0xFF])
    for start in k.LISTS:
        put(start, [0xFF] * 32)
    put(k.LISTS[0], [0x01, 0x09, 0xC7, 0x00, 0x01, 0x0A, 0x97, 0x00, 0xFF])
    put(k.LISTS[3], [0x00, 0x02, 0x37, 0x00, 0xFF])
    # stage 0: group A Monoeye on screen 1, group B Shemum on screen 1, a Reaper (group B) at YX $38 on screen 1
    put(0x7CD0, Cart.word(0x7D00) + Cart.word(0x7D08))
    put(0x7D00, [0x00, 0x08])
    put(0x7D3A, Cart.word(0x7D40) + Cart.word(0x7D48))
    put(0x7D40, [0x00, 0x02])
    put(0x7D05, Cart.word(0x7D50) + Cart.word(0x7D58))
    put(0x7D6F, Cart.word(0x7D60) + Cart.word(0x7D68))
    put(0x7D60, [0x00, 0x38])
    # items: a harp on stage 0 screen 1 at YX $5C, a chalice on stage 1 screen 0
    put(0x7E07, [0x02, 0x00, 0x01, 0x5C, 0x00, 0x01, 0x00, 0xA8, 0x01])
    # doors (bank 7, list found through the word at bank 2 $8056): stage 0 screen 1 YX $AE -> god's chamber, stage 1
    c.put(2, 0x8056, Cart.word(0xF001))
    c.put(7, 0xF001, [0x00, 0x01, 0xAE, 0x24, 0x01, 0x00, 0x71, 0x22, 0xFF])
    return c


class KidIcarusTest(unittest.TestCase):
    def setUp(self):
        self.c = kid_icarus_cart()
        self.p = m.KidIcarusProfile(bytes(self.c.rom))

    def test_decoding(self):
        self.assertEqual(self.p.stage_screens(1, 0), [0x7000, 0x7010])
        self.assertEqual(self.p.stage_screens(1, 1), [0x7010])
        rows = [(r['list'], r['number'], r['stage'], r['screen'], r['scroll']) for r in self.p.spawns(1)]
        self.assertEqual(rows, [(0, 0, 1, 9, 0xC7), (0, 1, 1, 10, 0x97), (3, 0, 0, 2, 0x37)])
        objects = self.p.objects({'world': 1, 'stage': 1})
        self.assertEqual([o['id'] for o in objects], ['spawn:0:0', 'spawn:0:1', 'item:1', 'door:1'])
        self.assertEqual(objects[0]['y'], -8 * 240 + 0xC7 - 0xEE + 16)

    def test_remove(self):
        plan = self.p.edit({'world': 1, 'stage': 1}, 'spawn:0:0', {}, remove=True)
        rom = bytearray(self.c.rom)
        for offset, old, new in plan['writes']:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        rows = [(r['list'], r['stage'], r['screen']) for r in m.KidIcarus(bytes(rom)).spawns(1)]
        self.assertEqual(rows, [(0, 1, 10), (3, 0, 2)])
        with self.assertRaises(ValueError):
            self.p.edit({'world': 1, 'stage': 0}, 'spawn:0:0', {}, remove=True)    # a record of another stage

    def test_where_and_watcher(self):
        ram = bytearray(0x2800)
        ram[0xA0], ram[0x130], ram[0x4D1], ram[0xFD] = 2, 0, 1, 0xEE
        self.assertEqual(self.p.where(ram), {'part': {'world': 1, 'stage': 0}, 'x': 0, 'y': 0})
        ram[0xA0] = 1
        self.assertIsNone(self.p.where(ram))
        plan = self.p.edit({'world': 1, 'stage': 0}, 'spawn:3:0', {}, remove=True)
        ram[0xA0], ram[0x4D1], ram[0xFD] = 2, 2, 0x37
        w = self.p.watcher(plan['watch'])
        self.assertFalse(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[0x790 + 1] = 0x78
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'bad')

    def test_groups_reapers_items_doors(self):
        part = {'world': 1, 'stage': 0}
        objects = {o['id']: o for o in self.p.objects(part)}
        self.assertEqual(sorted(objects), ['door:0', 'groupA:1', 'groupB:1', 'item:0', 'reaperB:1', 'spawn:3:0'])
        self.assertEqual(objects['groupA:1']['name'], 'Monoeye')
        self.assertEqual(objects['groupB:1']['name'], 'Shemum')
        self.assertEqual((objects['reaperB:1']['x'], objects['reaperB:1']['y']), (8 * 16 + 8, 2 - 240 + 0x30 + 16))
        self.assertEqual((objects['item:0']['name'], objects['item:0']['x']), ('Harp', 0xC * 16 + 8))
        self.assertEqual((objects['door:0']['name'], objects['door:0']['y']), ('God’s chamber', 2 - 240 + 0xA0 + 32))
        self.assertEqual([d['block'] for d in self.p.doors()], [0x24, 0x22])

    def apply(self, plan):
        rom = bytearray(self.c.rom)
        for offset, old, new in plan['writes']:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        return m.KidIcarusProfile(bytes(rom))

    def test_group_edits(self):
        part = {'world': 1, 'stage': 0}
        plan = self.p.edit(part, 'groupA:1', {'kind': 10})
        self.assertEqual(plan['writes'], [(m._Cart.offset(6, 0x9940 + 0x0D01), 8, 10)])
        self.assertEqual(plan['watch'], {'kind': 'wave', 'mode': 2, 'stage': 0, 'group': 'A', 'screen': 1, 'want': 10})
        self.assertEqual(self.apply(plan).find(part, 'groupA:1')['name'], 'Red floater')
        plan = self.p.edit(part, 'groupB:1', {}, remove=True)
        self.assertEqual(plan['writes'][0][2], 0)
        self.assertNotIn('groupB:1', [o['id'] for o in self.apply(plan).objects(part)])
        with self.assertRaises(ValueError):
            self.p.edit(part, 'groupB:1', {'kind': 8})            # a group A kind in group B
        plan = self.p.edit(part, 'reaperB:1', {}, remove=True)
        self.assertEqual(plan['writes'], [(m._Cart.offset(6, 0x9940 + 0x0D61), 0x38, 0)])
        self.assertEqual(plan['watch']['row'], 0x30)

    def test_item_and_door_edits(self):
        part = {'world': 1, 'stage': 0}
        plan = self.p.edit(part, 'item:0', {'item': 1})
        self.assertEqual(plan['writes'], [(m._Cart.offset(6, 0x9940 + 0x0E0B), 0, 1)])
        self.assertEqual((plan['watch']['x'], plan['watch']['row']), (0xC0, 0x50))
        p = self.apply(self.p.edit(part, 'item:0', {}, remove=True))
        self.assertEqual([(r['stage'], r['item']) for r in p.items(1)], [(1, 1)])
        plan = self.p.edit(part, 'door:0', {'chamber': 0x25})
        self.assertEqual(plan['writes'], [(m._Cart.offset(7, 0xF004), 0x24, 0x25)])
        self.assertEqual(plan['watch']['at'], 0x5F0 + 0xAE + 16)
        with self.assertRaises(ValueError):
            self.p.edit(part, 'door:0', {'chamber': 0x27})        # not used in world 1
        p = self.apply(self.p.edit(part, 'door:0', {}, remove=True))
        self.assertEqual([(d['stage'], d['block']) for d in p.doors()], [(1, 0x22)])

    def test_new_watchers(self):
        part = {'world': 1, 'stage': 0}
        ram = bytearray(0x2800)
        ram[0xA0], ram[0x130], ram[0x4D1], ram[0xFD] = 2, 0, 1, 0xEE
        w = self.p.watcher(self.p.edit(part, 'groupB:1', {'kind': 3})['watch'])
        self.assertFalse(w.see(ram, 0, 'changed'))                # all four slots empty
        ram[0x7C1] = ram[0x7D1] = 0x18
        self.assertTrue(w.see(ram, 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[0x7C1] = ram[0x7D1] = 0
        w = self.p.watcher(self.p.edit(part, 'door:0', {'chamber': 0x25})['watch'])
        ram[0x5F0 + 0xAE], ram[0x5F0 + 0xAE + 16] = 0x50, 0x24
        for f in range(4):
            done = w.see(ram, f, 'changed')
        self.assertTrue(done)
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(self.p.edit(part, 'item:0', {'item': 1})['watch'])
        ram[0x4D1], ram[0xFD] = 1, 0x50
        self.assertFalse(w.see(ram, 0, 'changed'))
        ram[0x751], ram[0x752], ram[0x753] = 0x81, 1, 0xC0
        self.assertTrue(w.see(ram, 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')


def kid_icarus_worlds_cart():
    """World 1 as above, plus world 2 (tables in bank 2) and world 3 (copied from bank 6 $A790), with their door lists."""
    c = kid_icarus_cart()
    w = Cart.word
    # world 2: stage 0 has screens 0-2; Rokman on screen 1 (group A), a Pale walker on screen 2 (group B)
    c.put(2, 0xBB04, w(0xB000) * 3)
    c.put(2, 0xB000, [0x10, 0x00, 0x11, 0x00, 0x12, 0x00, 0x00, 0xFF])
    c.put(2, 0xBC3F, w(0xB100) * 3)
    c.put(2, 0xB100, [0x00, 0x04, 0x00])
    c.put(2, 0xBCF9, w(0xB110) * 3)
    c.put(2, 0xB110, [0x00, 0x00, 0x09])
    # items: a harp on screen 1 at YX $8E; then a chalice on screen 0, behind it, which the game never reaches
    c.put(2, 0xBC2A, [0x02, 0x00, 0x01, 0x8E, 0x00, 0x00, 0x00, 0x88, 0x01])
    for start in m.KidIcarus.WORLDS[2]['lists']:
        c.put(2, start, [0xFF] * 32)
    c.put(2, 0xBDB3, [0x00, 0x02, 0x26, 0x00, 0xFF])
    c.put(2, 0x99F6, w(0xF037))
    c.put(7, 0xF037, [0x00, 0x01, 0xAF, 0x25, 0xFF])

    def put3(address, data):
        c.put(6, 0xA790 + address - 0x7000, data)
    # world 3: stage 0 has two screens; Komayto (group A 8) and a Reaper (group B: 13 keeps the slots, Reaper at $D8)
    put3(0x772B, w(0x7300) * 3)
    put3(0x7300, w(0x7000) + w(0x7010) + [0xFF, 0xFF])
    put3(0x77E1, w(0x7400) * 3)
    put3(0x7400, [0x00, 0x08])
    put3(0x781B, w(0x7410) * 3)
    put3(0x7855, w(0x7420) * 3)
    put3(0x7420, [0x00, 0x0D])
    put3(0x788F, w(0x7430) * 3)
    put3(0x7430, [0x00, 0xD8])
    # items (always harps): one on stage 3-3 screen 1 at YX $15, then one of stage 3-1 the game never reaches
    put3(0x792C, [0x02, 0x02, 0x01, 0x15, 0x00, 0x01, 0x07])
    for start in m.KidIcarus.WORLDS[3]['lists']:
        put3(start, [0xFF] * 32)
    c.put(3, 0x8056, w(0xF095))
    c.put(7, 0xF095, [0x00, 0x00, 0xBE, 0x27, 0xFF])
    return c


class KidIcarusWorldsTest(unittest.TestCase):
    def setUp(self):
        self.c = kid_icarus_worlds_cart()
        self.p = m.KidIcarusProfile(bytes(self.c.rom))

    def apply(self, plan):
        rom = bytearray(self.c.rom)
        for offset, old, new in plan['writes']:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        return m.KidIcarusProfile(bytes(rom))

    def test_world2_decoding(self):
        self.assertEqual(self.p.stage_screens(2, 0), [0x0010, 0x0011, 0x0012])
        self.assertEqual([(r['number'], r['live']) for r in self.p.items(2)], [(0, True), (1, False)])
        part = {'world': 2, 'stage': 0}
        objects = {o['id']: o for o in self.p.objects(part)}
        self.assertEqual(sorted(objects), ['door:0', 'groupA:1', 'groupB:2', 'item:0', 'spawn:0:0'])
        self.assertEqual(objects['groupA:1']['name'], 'Rokman (likely)')
        self.assertEqual(objects['groupB:2']['name'], 'Pale walker')
        self.assertEqual((objects['item:0']['x'], objects['item:0']['y']), (256 + 14 * 16 + 8, 0x80 + 16))
        self.assertEqual((objects['door:0']['x'], objects['door:0']['y']), (256 + 15 * 16 + 8, 0xA0 + 32))
        self.assertEqual(objects['spawn:0:0']['x'], 256 + 0x26 + 0xF8)
        self.assertEqual([d['block'] for d in self.p.doors(2)], [0x25])
        self.assertEqual([d['block'] for d in self.p.doors()], [0x24, 0x22])     # world 1's list is still the default

    def test_world2_where(self):
        ram = bytearray(0x2800)
        ram[0xA0], ram[0x130], ram[0x4D1], ram[0xFE] = 4, 1, 3, 0x40
        self.assertEqual(self.p.where(ram), {'part': {'world': 2, 'stage': 1}, 'x': 2 * 256 + 0x40, 'y': 0})
        ram[0x3A] = 5                                           # in a chamber
        self.assertIsNone(self.p.where(ram))
        ram[0x3A], ram[0xA0] = 0, 3                             # fortress 1
        self.assertIsNone(self.p.where(ram))
        self.assertEqual(self.p.part_name({'world': 2, 'stage': 1}), 'Stage 2-2')

    def test_world2_edits(self):
        part = {'world': 2, 'stage': 0}
        plan = self.p.edit(part, 'groupA:1', {'kind': 8})
        self.assertEqual(plan['writes'], [(m._Cart.offset(2, 0xB101), 4, 8)])
        self.assertEqual(plan['watch'], {'kind': 'wave', 'mode': 4, 'stage': 0, 'group': 'A', 'screen': 1, 'want': 8, 'world': 2})
        self.assertEqual(self.apply(plan).find(part, 'groupA:1')['name'], 'Biting plant head')
        with self.assertRaises(ValueError):
            self.p.edit(part, 'groupB:2', {'kind': 5})          # a group A kind in group B
        plan = self.p.edit(part, 'item:0', {'item': 1})
        self.assertEqual(plan['writes'], [(m._Cart.offset(2, 0xBC2E), 0, 1)])
        self.assertEqual((plan['watch']['row'], plan['watch']['col'], plan['watch']['way']), (0x80, 0xE0, 'across'))
        p = self.apply(self.p.edit(part, 'item:0', {}, remove=True))
        self.assertEqual([(r['screen'], r['item']) for r in p.items(2)], [(0, 1)])
        with self.assertRaises(ValueError):
            self.p.edit(part, 'item:1', {}, remove=True)        # a record the game never reaches
        plan = self.p.edit(part, 'door:0', {'chamber': 0x27})   # worlds 2 and 3 have hot springs
        self.assertEqual(plan['writes'], [(m._Cart.offset(7, 0xF03A), 0x25, 0x27)])
        self.assertEqual((plan['watch']['at'], plan['watch']['settle']), (0x5F0 + 0xAF + 16, 60))
        p = self.apply(self.p.edit(part, 'door:0', {}, remove=True))
        self.assertEqual(p.doors(2), [])
        self.assertEqual(len(p.doors(1)), 2)
        plan = self.p.edit(part, 'spawn:0:0', {}, remove=True)
        self.assertEqual(plan['watch']['scroll_at'], 0xFE)
        self.assertEqual(self.apply(plan).spawns(2), [])

    def test_world2_watchers(self):
        part = {'world': 2, 'stage': 0}
        ram = bytearray(0x2800)
        ram[0xA0], ram[0x130], ram[0x4D1], ram[0xFE] = 4, 0, 1, 0xD0
        w = self.p.watcher(self.p.edit(part, 'item:0', {'item': 1})['watch'])
        self.assertFalse(w.see(ram, 0, 'changed'))
        self.assertFalse(w.reached)
        ram[0xFE], ram[0x750], ram[0x751], ram[0x752] = 0xE0, 0x80, 0x81, 1
        self.assertTrue(w.see(ram, 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[0x751] = 0x80
        w = self.p.watcher(self.p.edit(part, 'spawn:0:0', {}, remove=True)['watch'])
        ram[0x4D1], ram[0xFE] = 2, 0x26
        self.assertFalse(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[0x761], ram[0x763] = 0x78, 0xF8
        w = self.p.watcher(self.p.edit(part, 'spawn:0:0', {}, remove=True)['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(self.p.edit(part, 'groupA:1', {'kind': 8})['watch'])
        ram[0x4D1], ram[0x761] = 1, 0
        self.assertFalse(w.see(ram, 0, 'changed'))
        ram[0x761] = ram[0x771] = 0x40
        self.assertTrue(w.see(ram, 1, 'changed'))
        self.assertEqual(w.result(), {'state': 'good', 'text': 'Played from the start, that screen brought Biting plant head.'})

    def test_world3(self):
        part = {'world': 3, 'stage': 0}
        objects = {o['id']: o for o in self.p.objects(part)}
        self.assertEqual(sorted(objects), ['door:0', 'groupA:1', 'reaperB:1'])
        self.assertEqual(objects['groupA:1']['name'], 'Komayto (likely)')
        self.assertEqual(objects['door:0']['name'], 'Hot spring chamber')
        self.assertEqual(objects['door:0']['y'], 2 + 0xB0 + 32)
        self.assertEqual([(r['number'], r['live']) for r in self.p.items(3)], [(0, True), (1, False)])
        item = self.p.find({'world': 3, 'stage': 2}, 'item:0')
        self.assertEqual((item['name'], item['fields'], item['x']), ('Harp', [], 5 * 16 + 8))
        with self.assertRaises(ValueError):
            self.p.edit({'world': 3, 'stage': 2}, 'item:0', {'item': 1})     # world 3 items are always harps
        plan = self.p.edit({'world': 3, 'stage': 2}, 'item:0', {}, remove=True)
        offset = m._Cart.offset(6, 0xA790 + 0x092C)
        self.assertEqual(plan['writes'][-1], (offset, 2, 1))
        self.assertEqual([r['stage'] for r in self.apply(plan).items(3)], [0])
        plan = self.p.edit(part, 'reaperB:1', {}, remove=True)
        self.assertEqual(plan['writes'], [(m._Cart.offset(6, 0xA790 + 0x0431), 0xD8, 0)])
        plan = self.p.edit(part, 'groupA:1', {'kind': 11})
        self.assertEqual(plan['writes'], [(m._Cart.offset(6, 0xA790 + 0x0401), 8, 11)])
        with self.assertRaises(ValueError):
            self.p.edit(part, 'groupA:1', {'kind': 5})          # a world 1 kind
        ram = bytearray(0x2800)
        ram[0xA0], ram[0x130], ram[0x4D1], ram[0xFD] = 6, 2, 1, 0xEE
        self.assertEqual(self.p.where(ram), {'part': {'world': 3, 'stage': 2}, 'x': 0, 'y': 0})
        # door watcher: the screen number is set before the block map is built (after a password), so worlds 2 and 3
        # decide at once when the door is there and otherwise only after 60 looks
        watch = self.p.edit(part, 'door:0', {'chamber': 0x25})['watch']
        self.assertEqual((watch['at'], watch['settle']), (0x500 + 0xBE + 16, 60))
        ram[0x130] = 0
        w = self.p.watcher(watch)
        self.assertEqual([w.see(ram, f, 'changed') for f in range(60)], [False] * 59 + [True])
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(watch)
        ram[0x5BE], ram[0x5CE] = 0x50, 0x25
        self.assertEqual([w.see(ram, f, 'changed') for f in range(4)], [False] * 3 + [True])
        self.assertEqual(w.result(), {'state': 'good', 'text': 'Played from the start, the door there leads to: Shop.'})
        choices = self.p.choices()
        self.assertEqual([c['value'] for c in choices['enemiesA3']], [0, 7, 8, 10, 11, 12])
        self.assertIn(0x27, [c['value'] for c in choices['chambers2']])
        self.assertNotIn(0x27, [c['value'] for c in choices['chambers']])


if __name__ == '__main__':
    unittest.main()
