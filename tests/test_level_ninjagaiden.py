"""Ninja Gaiden I-III level profiles on made-up cartridges that only have the tables at their real addresses."""
from __future__ import annotations

import unittest

from romancer.level_profiles import ninjagaiden as ng

SIZE = 16 + 0x20000 + 0x20000


def _put(rom, offset, data):
    rom[offset:offset + len(data)] = bytes(data)


# ----------------------------------------------------------------- Ninja Gaiden

def ng1_rom():
    rom = bytearray(SIZE)
    b0 = lambda a: 16 + (a - 0x8000)                 # bank 0
    b2 = lambda a: 16 + 2 * 0x4000 + (a - 0x8000)    # bank 2
    # stages: stage 0 -> area 0, stage 1 -> area 2, every later stage after the last area
    _put(rom, b0(0xAF2C), [0, 2] + [3] * 20)
    _put(rom, b0(0xAF6E), [0x11, 0x12] + [0x21] * 20)
    _put(rom, b0(0xAE40), [3, 1, 1] + [0] * 45)      # enemies per area
    _put(rom, b0(0xAE10), [2, 1, 0x80] + [0] * 45)   # lanterns per area
    lists = {0: {'lc': 0x9000, 'li': 0x9010, 'c': 0x9020, 'p': 0x9030, 't': 0x9040},
             1: {'lc': 0x9100, 'li': 0x9110, 'c': 0x9120, 'p': 0x9130, 't': 0x9140},
             2: {'lc': 0x9200, 'li': 0x9210, 'c': 0x9220, 'p': 0x9230, 't': 0x9240}}
    for area in range(48):
        L = lists.get(area, {'lc': 0x9F00, 'li': 0x9F00, 'c': 0x9F00, 'p': 0x9F00, 't': 0x9F00})
        for k, key in enumerate(('lc', 'li', 'c', 'p', 't')):
            _put(rom, b2(0x8700 + area * 2 + k * 0x60), [L[key] & 0xFF, L[key] >> 8])
    _put(rom, b2(0x9000), [0x18, 0x30])              # lantern columns
    _put(rom, b2(0x9010), [0xB0, 0x95])              # lantern height | item
    _put(rom, b2(0x9020), [0x02, 0x17, 0x20])        # enemy columns
    _put(rom, b2(0x9030), [0xDF, 0xD1, 0x9F])        # place
    _put(rom, b2(0x9040), [0x03, 0x09, 0x04])        # types
    _put(rom, b2(0x9100), [0x05]); _put(rom, b2(0x9110), [0x83])
    _put(rom, b2(0x9120), [0x00]); _put(rom, b2(0x9130), [0xDD]); _put(rom, b2(0x9140), [0x17])
    # area 2: its column list's byte is also the first byte of area 1's place list (a shared byte)
    rom[b0(0xAE40) + 2] = 1
    for k, value in ((2, 0x9130),):
        _put(rom, b2(0x8700 + 2 * 2 + k * 0x60), [value & 0xFF, value >> 8])
    _put(rom, b2(0x9230), [0x5F]); _put(rom, b2(0x9240), [0x00])
    return bytes(rom)


class NinjaGaiden1Test(unittest.TestCase):
    def setUp(self):
        self.p = ng.NinjaGaiden1Profile(ng1_rom())
        self.part = {'stage': 0, 'area': 0}

    def test_where_and_names(self):
        ram = bytearray(0x800)
        ram[0x6D], ram[0x6E], ram[0x51], ram[0x52] = 0, 0, 0x34, 0x02
        self.assertEqual(self.p.where(ram), {'part': {'stage': 0, 'area': 0}, 'x': 0x234, 'y': 0})
        ram[0x6D] = 30
        self.assertIsNone(self.p.where(ram))
        self.assertEqual(self.p.part_name({'stage': 0, 'area': 0}), 'Stage 1-1, section 1')
        self.assertEqual(self.p.part_name({'stage': 1, 'area': 2}), 'Stage 1-2')

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects(self.part)}
        self.assertEqual((objects['enemy:0']['x'], objects['enemy:0']['y'], objects['enemy:0']['name']), ((2 + 15) * 16, 0xD0, 'Club thug'))
        self.assertEqual(objects['enemy:1']['name'], 'Dog')
        self.assertEqual(objects['lantern:1']['detail'], 'holds Bonus points (500)')
        self.assertEqual((objects['lantern:0']['x'], objects['lantern:0']['y']), (0x18 * 16 + 4, 0xB0 - 8))
        boss = self.p.objects({'stage': 0, 'area': 1})
        self.assertIsNone(next(o for o in boss if o['style'] == 'enemy')['remove'])

    def test_edits(self):
        L = self.p.lists(0)
        swap = self.p.edit(self.part, 'enemy:0', {'type': 4})
        self.assertEqual(swap['writes'], [(self.p.offset(2, L['type']), 0x03, 0x04)])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'enemy:0', {'type': 0x0B})          # not used in this stage
        gone = self.p.edit(self.part, 'enemy:1', {}, remove=True)
        self.assertEqual(gone['writes'], [(self.p.offset(2, L['col'] + 1), 0x17, 0xFF)])
        item = self.p.edit(self.part, 'lantern:1', {'item': 0x8})
        self.assertEqual(item['writes'], [(self.p.offset(2, L['lantern_item'] + 1), 0x95, 0x98)])
        lantern = self.p.edit(self.part, 'lantern:0', {}, remove=True)      # taken out of the list (the game reads it in order)
        self.assertEqual(lantern['writes'], [(self.p.offset(2, L['lantern_col']), 0x18, 0x30), (self.p.offset(2, L['lantern_item']), 0xB0, 0x95),
                                             (self.p.offset(0, 0xAE10), 2, 1)])
        self.assertEqual((lantern['watch']['same'], lantern['watch']['next']), (0, 0x30))

    def test_shared_bytes_are_left_alone(self):
        objects = self.p.objects({'stage': 1, 'area': 2})
        self.assertEqual(objects[0]['fields'], [])
        self.assertIsNone(objects[0]['remove'])

    def test_watcher(self):
        plan = self.p.edit(self.part, 'enemy:0', {'type': 4})
        w = self.p.watcher(plan['watch'])
        ram = bytearray(0x800)
        ram[0x4E] = 2
        self.assertFalse(w.see(ram, 0, 'changed'))
        ram[0xB7] = 1; ram[0x73] = 1 << 5; ram[0x4B0 + 5] = 0; ram[0x400 + 5] = 4
        self.assertTrue(w.see(ram, 2, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        removal = self.p.watcher(self.p.edit(self.part, 'enemy:1', {}, remove=True)['watch'])
        ram = bytearray(0x800)
        for column in range(0x10, 0x20):
            ram[0x4E] = column
            removal.see(ram, column, 'changed')
        self.assertEqual(removal.result()['state'], 'good')


def ng1_long_rom():
    """ng1_rom with area 0 four screens long: layout at $8000 (bank 0), every byte of screen n is n; free space $FF."""
    rom = bytearray(ng1_rom())
    b0 = lambda a: 16 + (a - 0x8000)
    rom[b0(0xAD20)] = 3
    _put(rom, b0(0xAC30), [0x00, 0x80])
    for screen in range(4):
        _put(rom, b0(0x8000 + screen * 48), [screen] * 48)
    _put(rom, b0(0x80C0), [9] * 144)                 # what follows (the next area's layout)
    _put(rom, b0(0xB58C), [0xFF] * (0xBFDA - 0xB58C))
    return bytes(rom)


class NinjaGaiden1LengthTest(unittest.TestCase):
    def setUp(self):
        self.p = ng.NinjaGaiden1Profile(ng1_long_rom())
        self.part = {'stage': 0, 'area': 0}
        self.b0 = lambda a: 16 + (a - 0x8000)
        self.b2 = lambda a: 16 + 2 * 0x4000 + (a - 0x8000)

    def apply(self, writes):
        rom = bytearray(self.p.rom)
        for offset, old, new in writes:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        return ng.NinjaGaiden1Profile(bytes(rom))

    def test_screens(self):
        self.assertEqual(self.p.screens(self.part), {'count': 4, 'most': 15})
        self.assertIsNone(self.p.screens({'stage': 0, 'area': 1}))       # a single screen
        with self.assertRaises(ValueError):
            self.p.resize(self.part, 0, -1)                               # the first screen stays
        with self.assertRaises(ValueError):
            self.p.resize(self.part, 3, -1)                               # the last screen stays

    def test_remove(self):
        plan = self.p.resize(self.part, 1, -1)
        after = self.apply(plan['writes'])
        self.assertEqual(after.area_last(0), 2)
        self.assertEqual([after._b(0, 0x8000 + s * 48) for s in range(4)], [0, 2, 3, 3])    # past the end: the last screen again
        self.assertEqual([e['col'] for e in after.enemies(0)], [0x02, 0xFF, 0x10])          # screen 1's enemy taken out, screen 2's moved
        self.assertEqual([(l['col'], l['item']) for l in after.lanterns(0)], [(0x20, 5)])   # screen 1's lantern taken out of the list
        self.assertEqual(plan['watch']['enemy_cols'], [(0x02, 0x02), (0x17, 0xFF), (0x20, 0x10)])
        self.assertEqual(len(plan['watch']['expect']), 3 * 8)

    def test_repeat(self):
        plan = self.p.resize(self.part, 0, 1)
        after = self.apply(plan['writes'])
        self.assertEqual(after.area_last(0), 4)
        start = after.layout(0)
        self.assertEqual(start, 0xB58C + 144)                             # moved to the free space, 3 screens of margin first
        self.assertEqual([after._b(0, start + s * 48) for s in range(5)], [0, 0, 1, 2, 3])
        self.assertEqual(after._b(0, start - 1), 0)                       # before the first area: copies of its first screen
        self.assertEqual(after._b(0, start + 5 * 48), 9)                  # what followed the old layout follows the new one
        self.assertEqual([e['col'] for e in after.enemies(0)], [0x02, 0x27, 0x30])
        self.assertEqual([l['col'] for l in after.lanterns(0)], [0x28, 0x40])
        with self.assertRaises(ValueError):
            self.p.resize(self.part, 1, 12)                               # more than 15 screens

    def test_watcher(self):
        plan = self.p.resize(self.part, 1, -1)
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.compare)
        expect = [bytes.fromhex(e) for e in plan['watch']['expect']]
        for run, limit in (('original', 3), ('changed', 2)):
            ram = bytearray(0x800)
            ram[0x53] = limit
            for k in range(9):
                ram[0x300 + k * 12:0x300 + k * 12 + 12] = expect[k] if run == 'changed' else bytes(12)
            w.see(ram, 1, run)
            ram[0x6E] = 5
            w.see(ram, 2, run)
        self.assertEqual(w.result()['state'], 'good')
        control = self.p.watcher(plan['watch'])                           # the unchanged game: the old length
        for run in ('original', 'changed'):
            ram = bytearray(0x800)
            ram[0x53] = 3
            control.see(ram, 1, run)
        self.assertEqual(control.result()['state'], 'bad')


# ----------------------------------------------------------------- Ninja Gaiden II

def ng2_rom():
    rom = bytearray(SIZE)
    at = lambda a: 16 + a
    for area in range(48):
        base = 0x9000 + area * 0x20
        pointers = {0x8720: base, 0x8780: base + 4, 0x87E0: base + 8, 0x8840: base + 12, 0x88A0: base + 16}
        for lo, value in pointers.items():
            rom[at(lo + area)], rom[at(lo + 0x30 + area)] = value & 0xFF, value >> 8
    rom[at(0x82A0)], rom[at(0x82D0)] = 2, 3
    _put(rom, at(0x9000), [0x13, 0x1D]); _put(rom, at(0x9004), [0x73, 0x55])
    _put(rom, at(0x9008), [0x04, 0x08, 0x0E]); _put(rom, at(0x900C), [0xBF, 0xBF, 0x6F]); _put(rom, at(0x9010), [0x04, 0x0C, 0x18])
    return bytes(rom)


class NinjaGaiden2Test(unittest.TestCase):
    def setUp(self):
        self.p = ng.NinjaGaiden2Profile(ng2_rom())
        self.part = {'area': 0}

    def test_objects_and_names(self):
        self.assertEqual(self.p.part_name(self.part), 'Stage 1-1, section 1')
        self.assertEqual(self.p.part_name({'area': 3}), 'Stage 1-2')
        objects = {o['id']: o for o in self.p.objects(self.part)}
        self.assertEqual((objects['enemy:0']['x'], objects['enemy:0']['y']), ((4 + 15) * 16, 0xB8))
        self.assertEqual(objects['enemy:2']['name'], 'Red ninja')
        self.assertEqual(objects['lantern:0']['detail'], 'holds Fire dragon balls')

    def test_edits(self):
        swap = self.p.edit(self.part, 'enemy:0', {'type': 0x0C})
        self.assertEqual(swap['writes'], [(16 + 0x9010, 0x04, 0x0C)])
        self.assertEqual(swap['watch']['signature'], [71, 0])
        gone = self.p.edit(self.part, 'enemy:0', {}, remove=True)
        self.assertEqual(sorted(gone['writes']), sorted([(16 + 0x9008, 4, 8), (16 + 0x9009, 8, 14), (16 + 0x900D, 0xBF, 0x6F),
                                                         (16 + 0x9010, 4, 0x0C), (16 + 0x9011, 0x0C, 0x18), (16 + 0x82D0, 3, 2)]))
        item = self.p.edit(self.part, 'lantern:1', {'item': 9})
        self.assertEqual(item['writes'], [(16 + 0x9005, 0x55, 0x59)])
        lantern = self.p.edit(self.part, 'lantern:0', {}, remove=True)
        self.assertEqual(lantern['writes'], [(16 + 0x9000, 0x13, 0x1D), (16 + 0x9004, 0x73, 0x55), (16 + 0x82A0, 2, 1)])

    def test_removal_watcher_compares(self):
        plan = self.p.edit(self.part, 'enemy:1', {}, remove=True)
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.compare)
        for run, flags in (('original', [0, 0, 0b10]), ('changed', [0, 0, 0b10])):
            for value in flags:
                ram = bytearray(0x800)
                ram[0x440], ram[0x40] = value, 8          # entry 1 sits at column 8
                if value:
                    ram[0x4A], ram[0x658 + 0x16] = 0x40, 1    # slot $16 in use with list number 1
                w.see(ram, 0, run)
        self.assertEqual(w.result()['state'], 'bad')          # the unchanged game: the enemy still appears
        w = self.p.watcher(plan['watch'])
        for run, flags in (('original', [0, 0, 0b10]), ('changed', [0, 0, 0])):
            for value in flags:
                ram = bytearray(0x800)
                ram[0x440], ram[0x40] = value, 8
                if value:
                    ram[0x4A], ram[0x658 + 0x16] = 0x40, 1
                w.see(ram, 0, run)
        self.assertEqual(w.result()['state'], 'good')


class NinjaGaiden2LengthTest(unittest.TestCase):
    """Area 0 three screens long: layout pointer at ROM $2700/$2730 (bank 1), layout at ROM 0 ($8000), last screen $8180."""
    def setUp(self):
        rom = bytearray(ng2_rom())
        rom[16 + 0x8180] = 0x02
        rom[16 + 0x2730] = 0x80                                           # area 0's layout at $8000
        for screen in range(3):
            _put(rom, 16 + screen * 48, [screen] * 48)
        _put(rom, 16 + 0x90, [9] * 144)
        _put(rom, 16 + 0x21C6 - 0x90, [0xFF] * (0x2700 - 0x21C6 + 0x90))
        self.p = ng.NinjaGaiden2Profile(bytes(rom))
        self.part = {'area': 0}

    def apply(self, writes):
        rom = bytearray(self.p.rom)
        for offset, old, new in writes:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        return ng.NinjaGaiden2Profile(bytes(rom))

    def test_remove_and_repeat(self):
        self.assertEqual(self.p.screens(self.part), {'count': 3, 'most': 15})
        self.assertIsNone(self.p.screens({'area': 1}))
        gone = self.apply(self.p.resize(self.part, 1, -1)['writes'])
        self.assertEqual(gone.area_last(0), 1)
        self.assertEqual([gone.rom[16 + s * 48] for s in range(3)], [0, 2, 2])
        self.assertEqual(gone.lanterns(0), [])                            # both lanterns were on screen 1
        self.assertEqual([e['col'] for e in gone.enemies(0)], [4, 8, 14])
        plan = self.p.resize(self.part, 0, 1)
        more = self.apply(plan['writes'])
        self.assertEqual(more.layout(0), 0xA1C6 + 144)
        self.assertEqual([more.rom[more.layout_offset(0xA256) + s * 48] for s in range(5)], [0, 0, 1, 2, 9])
        self.assertEqual([l['col'] for l in more.lanterns(0)], [0x23, 0x2D])
        self.assertEqual(len(plan['watch']['expect']), 4 * 8)

    def test_length_watcher(self):
        plan = self.p.resize(self.part, 0, 1)
        w = self.p.watcher(plan['watch'])
        for run, limit in (('original', 2), ('changed', 3)):
            ram = bytearray(0x800)
            ram[0x7F] = limit
            pointer = plan['watch']['base'] + 9 * 6                    # the game reads 9 columns ahead of the camera
            ram[0x86], ram[0x87] = pointer & 0xFF, pointer >> 8
            ram[0x1E0:0x1E6] = bytes.fromhex(plan['watch']['expect'][9])
            w.see(ram, 1, run)
        self.assertEqual(w.result()['state'], 'good')
        control = self.p.watcher(plan['watch'])
        for run in ('original', 'changed'):
            ram = bytearray(0x800)
            ram[0x7F] = 2
            control.see(ram, 1, run)
        self.assertEqual(control.result()['state'], 'bad')


# ----------------------------------------------------------------- Ninja Gaiden III

def ng3_rom():
    rom = bytearray(SIZE)
    at = lambda a: 16 + 0xC000 + (a - 0xA000)
    for area in range(48):
        base = 0xB000 + area * 0x20
        pointers = {0xA390: base, 0xA3F0: base + 4, 0xA450: base + 8, 0xA4B0: base + 13, 0xA510: base + 17}
        for lo, value in pointers.items():
            rom[at(lo + area)], rom[at(lo + 0x30 + area)] = value & 0xFF, value >> 8
    rom[at(0xA240)], rom[at(0xA210)] = 2 << 3, (3 << 3) | 2
    rom[at(0xA0F0 + 1)] = 0x80                       # area 1 is a vertical section
    _put(rom, at(0xB000), [0x12, 0x13]); _put(rom, at(0xB004), [0x52, 0x66])
    _put(rom, at(0xB008), [0x04, 0x05, 0x09, 0x7F]); _put(rom, at(0xB00D), [0x7F, 0xCF, 0xCF]); _put(rom, at(0xB011), [0x0E, 0x00, 0x03])
    return bytes(rom)


class NinjaGaiden3Test(unittest.TestCase):
    def setUp(self):
        self.p = ng.NinjaGaiden3Profile(ng3_rom())
        self.part = {'area': 0}
        self.at = lambda a: 16 + 0xC000 + (a - 0xA000)

    def test_objects(self):
        self.assertEqual(self.p.part_name(self.part), 'Stage 1-1A')
        objects = {o['id']: o for o in self.p.objects(self.part)}
        self.assertEqual((objects['enemy:1']['x'], objects['enemy:1']['y']), ((5 + 15) * 16, 0xC0))
        self.assertEqual(objects['lantern:0']['detail'], 'holds Fire dragon balls')
        self.assertEqual(self.p.objects({'area': 1}), [])

    def test_edits(self):
        swap = self.p.edit(self.part, 'enemy:1', {'type': 3})
        self.assertEqual(swap['writes'], [(self.at(0xB012), 0x00, 0x03)])
        gone = self.p.edit(self.part, 'enemy:0', {}, remove=True)
        self.assertIn((self.at(0xB00A), 0x09, 0xFF), gone['writes'])          # freed place: a column never reached
        self.assertIn((self.at(0xA210), 0x1A, 0x12), gone['writes'])          # count is the top five bits
        self.assertIn((self.at(0xB008), 0x04, 0x05), gone['writes'])
        item = self.p.edit(self.part, 'lantern:1', {'item': 0xA})
        self.assertEqual(item['writes'], [(self.at(0xB005), 0x66, 0x6A)])

    def test_same_enemy_refused(self):
        rom = bytearray(ng3_rom())
        rom[self.at(0xB011)] = 0x16
        rom[self.at(0xB012)] = 0x17
        p = ng.NinjaGaiden3Profile(bytes(rom))
        with self.assertRaises(ValueError):
            p.edit(self.part, 'enemy:0', {'type': 0x17})


class NinjaGaiden3LengthTest(unittest.TestCase):
    """Area 0 four screens long: layout pointer at ROM $3960/$3990, layout at ROM 0 ($8000), last screen $A1B0. Banks 0
    and 1 have no free space in the game, so parts only get shorter."""
    def setUp(self):
        rom = bytearray(ng3_rom())
        rom[16 + 0xC1B0] = 0x03
        rom[16 + 0x3990] = 0x80                                           # area 0's layout at $8000
        for screen in range(4):
            _put(rom, 16 + screen * 48, [screen] * 48)
        self.p = ng.NinjaGaiden3Profile(bytes(rom))
        self.part = {'area': 0}

    def test_shorter_only(self):
        self.assertEqual(self.p.screens(self.part), {'count': 4, 'most': 4})
        self.assertIsNone(self.p.screens({'area': 1}))                    # vertical section
        with self.assertRaises(ValueError):
            self.p.resize(self.part, 1, 1)
        plan = self.p.resize(self.part, 1, -1)
        rom = bytearray(self.p.rom)
        for offset, old, new in plan['writes']:
            rom[offset] = new
        after = ng.NinjaGaiden3Profile(bytes(rom))
        self.assertEqual(after.area_last(0), 2)
        self.assertEqual([rom[16 + s * 48] for s in range(4)], [0, 2, 3, 3])
        self.assertEqual(after.lanterns(0), [])                           # both lanterns were on screen 1
        self.assertEqual(rom[16 + 0xC000 + 0xA240 - 0xA000] >> 3, 0)
        self.assertEqual([e['col'] for e in after.enemies(0)], [4, 5, 9])
        self.assertEqual(self.p.watcher(plan['watch']).LIMIT, 0x48)


class RegistryTest(unittest.TestCase):
    def test_one_class_per_game(self):
        self.assertEqual([k.name for k in ng.PROFILES], ['Ninja Gaiden', 'Ninja Gaiden II', 'Ninja Gaiden III'])
        self.assertEqual(len({s for k in ng.PROFILES for s in k.sha256s}), 3)


if __name__ == '__main__':
    unittest.main()
