"""Capcom Disney level profiles, later games (DuckTales 2, Darkwing Duck, Chip 'n Dale - Rescue Rangers 2): decoders and
edits on made-up cartridges laid out like the real ones.

The real games are not part of the tests; these build the same tables at the same addresses, so a change in how a
table is read or written shows here. What the tables mean was proven by replaying the real games
(research/capcom_disney2-level-profile.md).
"""
import unittest

from romancer.level_profiles import capcom_disney2 as cd2

H = 16


def ram(**values):
    r = bytearray(0x800)
    for k, v in values.items():
        r[int(k[1:], 16)] = v
    return r


# =====================================================================================================================
# DuckTales 2
# (section: DuckTales 2)

# =====================================================================================================================
# Darkwing Duck
# (section: Darkwing Duck)

class DwCart:
    """A blank MMC1 cartridge (8 banks of 16 KB PRG) with Darkwing Duck's bank 4 tables at their real addresses."""

    def __init__(self):
        self.rom = bytearray(H + 8 * 0x4000)

    def o4(self, address):
        return H + 0x10000 + address - 0x8000

    def put4(self, address, data):
        o = self.o4(address)
        self.rom[o:o + len(data)] = bytes(data)


# kinds (4 bytes at $8AB3 + kind * 4): flags, type, graphic, parameter
DW_KINDS = {
    0x00: [0xD0, 0x0C, 0x41, 0x40],      # enemy (parameter bit $40)
    0x01: [0xD0, 0x0E, 0x45, 0x42],      # enemy
    0x04: [0xD0, 0x11, 0x59, 0x00],      # left as it is
    0x10: [0x90, 0x09, 0x1C, 0x02],      # diamond
    0x12: [0x90, 0x09, 0x1E, 0x02],      # extra life
    0x13: [0x90, 0x08, 0x22, 0x02],      # health kit
    0x1E: [0xB0, 0x08, 0x24, 0x02],      # hidden gas canister (flag $20)
    0x35: [0xD8, 0x35, 0x90, 0x40],      # enemy that starts hidden (flag $08): not offered
    0x49: [0x90, 0x50, 0x92, 0x0A],      # boss
}
# level 0: x, section, y, kind; the arrays end with an all-$FF record
DW_RECORDS = [(0x0030, 0, 200, 0x65), (0x0178, 3, 184, 0x10), (0x0180, 3, 36, 0x00), (0x01B8, 3, 140, 0x04),
              (0x0200, 3, 116, 0x01), (0x0230, 3, 184, 0x1E), (0x0260, 3, 60, 0x35), (0x0FF0, 1, 208, 0x49),
              (0xFFFF, 0xFF, 0xFF, 0xFF)]
DW_LEVEL0 = 0x8239


def dw_build():
    c = DwCart()
    n = len(DW_RECORDS)
    bases = [DW_LEVEL0 + n * k for k in range(5)]                  # x high, x low, section, y, kind
    empty = 0x8400                                                 # the other levels: one $FF record each
    for k in range(5):
        for level in range(7):
            a = bases[k] if level == 0 else empty + k
            c.put4(0x81F3 + 14 * k + level, [a & 0xFF])
            c.put4(0x81F3 + 14 * k + 7 + level, [a >> 8])
    c.put4(empty, [0xFF] * 6)
    for i, (x, section, y, kind) in enumerate(DW_RECORDS):
        for k, v in enumerate((x >> 8, x & 0xFF, section, y, kind)):
            c.put4(bases[k] + i, [v])
    for kind, data in DW_KINDS.items():
        c.put4(0x8AB3 + kind * 4, data)
    return c, bases


class DarkwingDuckTest(unittest.TestCase):
    def setUp(self):
        self.c, self.bases = dw_build()
        self.p = cd2.DarkwingDuckProfile(bytes(self.c.rom))

    def test_records_and_roles(self):
        recs = self.p.records(0)
        self.assertEqual(len(recs), 8)
        self.assertEqual((recs[1]['x'], recs[1]['section'], recs[1]['y'], recs[1]['kind']), (0x178, 3, 184, 0x10))
        self.assertEqual(self.p.place(recs[1]), (0x178, 3 * 240 + 184))
        self.assertEqual([r['role'] for r in recs],
                         ['fixed', 'covered', 'enemy', 'fixed', 'enemy', 'hidden', 'enemy', 'fixed'])
        self.assertEqual(self.p.kind_name(0x10), 'Diamond (bonus +1)')
        self.assertEqual(self.p.kind_name(0x1E), 'Hidden gas canister (+10 gas)')
        self.assertEqual(self.p.records(1), [])

    def test_choices(self):
        self.assertEqual([c['value'] for c in self.p.enemy_choices(0)], [0x00, 0x01])
        self.assertEqual([c['value'] for c in self.p.content_choices(0x10, 1)], [0x10, 0x12, 0x13])
        self.assertEqual(self.p.content_choices(0x1E, 5), [])

    def test_where(self):
        r = ram(x31=0, x2C=0x10, x74=DW_LEVEL0 & 0xFF, x75=DW_LEVEL0 >> 8, xFD=1, xFC=0x20, xFB=3, xFA=8)
        self.assertEqual(self.p.where(r), {'part': {'level': 0}, 'x': 0x120, 'y': 728})
        r[0x2C] = 0
        self.assertIsNone(self.p.where(r))

    def test_swap_item_and_enemy(self):
        plan = self.p.edit({'level': 0}, 'object:1', {'kind': 0x13})
        self.assertEqual(plan['writes'], [(self.c.o4(self.bases[4] + 1), 0x10, 0x13)])
        self.assertEqual(plan['watch']['want'], {'types': [0x08], 'gfx': [0x22]})
        plan = self.p.edit({'level': 0}, 'object:2', {'kind': 0x01})
        self.assertEqual(plan['writes'], [(self.c.o4(self.bases[4] + 2), 0x00, 0x01)])
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'object:2', {'kind': 0x35})
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'object:3', {'kind': 0x00})

    def test_remove(self):
        plan = self.p.edit({'level': 0}, 'object:2', {}, remove=True)
        rom = bytearray(self.c.rom)
        for o, old, new in plan['writes']:
            self.assertEqual(rom[o], old)
            rom[o] = new
        after = cd2.DarkwingDuckProfile(bytes(rom))
        self.assertEqual([r['kind'] for r in after.records(0)], [0x65, 0x10, 0x04, 0x01, 0x1E, 0x35, 0x49])
        self.assertEqual(after.count(0), 9)
        self.assertTrue(plan['watch']['removing'])

    def test_watcher(self):
        plan = self.p.edit({'level': 0}, 'object:1', {'kind': 0x13})
        w = self.p.watcher(plan['watch'])
        r = ram(x31=0, x2C=0x10, xFC=0x40, xFD=0x01, xFB=3)
        w.see(bytes(r), 0, 'changed')
        s = 9
        r[0x4D0 + s], r[0x590 + s], r[0x4F0 + s], r[0x500 + s], r[0x510 + s], r[0x520 + s] = 0x80, 1, 0x78, 0x01, 184, 3
        r[0x4E0 + s], r[0x420 + s] = 0x08, 0x22
        self.assertTrue(w.see(bytes(r), 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        w.see(bytes(ram(x31=0, x2C=0x10)), 0, 'changed')
        r[0x4E0 + s], r[0x420 + s] = 0x09, 0x1C
        w.see(bytes(r), 1, 'changed')
        self.assertEqual(w.result()['state'], 'bad')

    def test_removal_watcher_keeps_the_old_object(self):
        plan = self.p.edit({'level': 0}, 'object:1', {}, remove=True)
        w = self.p.watcher(plan['watch'])
        r = ram(x31=0, x2C=0x10, xFC=0x40, xFD=0x01, xFB=3)
        w.see(bytes(r), 0, 'original')
        s = 9
        r[0x4D0 + s], r[0x590 + s], r[0x4F0 + s], r[0x500 + s], r[0x510 + s], r[0x520 + s] = 0x80, 1, 0x78, 0x01, 184, 3
        r[0x4E0 + s], r[0x420 + s] = 0x09, 0x1C            # the diamond still spawns there
        w.see(bytes(r), 1, 'original')
        r[0x590 + s], r[0x4E0 + s] = 0xFF, 0x0B            # taken: another object appears in its slot
        w.see(bytes(r), 2, 'original')
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(plan['watch'])                   # nothing there, the place was on screen
        w.see(bytes(ram(x31=0, x2C=0x10, xFC=0x40, xFD=0x01, xFB=3)), 0, 'changed')
        self.assertEqual(w.result()['state'], 'good')


# =====================================================================================================================
# Chip 'n Dale - Rescue Rangers 2
# (section: Chip 'n Dale 2)

class Cd2Cart:
    """A blank MMC1 cartridge (8 banks of 16 KB PRG) with Chip 'n Dale 2's step table (bank 7), area records (bank 2)
    and object lists (bank 3) at their real addresses."""

    def __init__(self):
        self.rom = bytearray(H + 8 * 0x4000)

    def o(self, bank, address):
        return H + bank * 0x4000 + address - (0xC000 if bank == 7 else 0x8000)

    def put(self, bank, address, data):
        o = self.o(bank, address)
        self.rom[o:o + len(data)] = bytes(data)


# level 0 list: monkey, rat, a vertical-scrolling rat, star (left alone), monkey, area exit; the second area starts
# again at the third record (the same place, entered after a scene)
CD2_LIST = 0xA3F1
CD2_RECORDS = [(0x18, 0x22, 0x27), (0x20, 0x2A, 0x25), (0x9B, 0x65, 0x25), (0x30, 0x24, 0x1F), (0x44, 0x22, 0x27),
               (0x7E, 0x2A, 0x21)]


def cd2_build():
    c = Cd2Cart()
    c.put(7, 0xDAAC, [0] + [6] * 8)                                   # level 0: steps 0-2; levels 1-8 empty or scenes
    c.put(7, 0xDA46, [0x00, 0xB0, 0x02, 0x00, 0x19, 0xB0])            # area $B000, a scene, area $B019
    c.put(2, 0xB000 + 15, [CD2_LIST & 0xFF, CD2_LIST >> 8])
    c.put(2, 0xB019 + 15, [(CD2_LIST + 6) & 0xFF, (CD2_LIST + 6) >> 8])
    for i, rec in enumerate(CD2_RECORDS):
        c.put(3, CD2_LIST + 3 * i, rec)
    c.put(3, CD2_LIST + 3 * len(CD2_RECORDS), [0xFF, 0x44, 0x44, 0x44])   # end, then the next list
    return c


class ChipDale2Test(unittest.TestCase):
    def setUp(self):
        self.c = cd2_build()
        self.p = cd2.ChipDale2Profile(bytes(self.c.rom))

    def test_parts_and_records(self):
        self.assertEqual(self.p.parts(0), [{'area': 0, 'start': CD2_LIST, 'end': CD2_LIST + 18}])
        recs = self.p.records(0, 0)
        self.assertEqual([r['kind'] for r in recs], [0x27, 0x25, 0x25, 0x1F, 0x27, 0x21])
        self.assertEqual([r['role'] for r in recs], ['enemy', 'enemy', 'enemy', 'fixed', 'enemy', 'fixed'])
        self.assertEqual((recs[2]['col'], recs[2]['vertical'], recs[2]['row']), (0x1B, True, 0x65))
        self.assertEqual(self.p.place(recs[0]), (0x180, 2 * 240 + 2 * 16))
        self.assertEqual(self.p.records(0, 2), [])
        self.assertEqual(self.p.parts(1), [])

    def test_where(self):
        r = ram(x40=4, x72=0, x79=(CD2_LIST + 9) & 0xFF, x7A=(CD2_LIST + 9) >> 8, xAE=1, xAC=0x20, xB2=2, xB0=8)
        self.assertEqual(self.p.where(r), {'part': {'level': 0, 'area': 0}, 'x': 0x120, 'y': 488})
        r[0x40] = 3
        self.assertIsNone(self.p.where(r))
        r[0x40], r[0x79] = 4, 0
        self.assertIsNone(self.p.where(r))

    def test_objects_and_choices(self):
        objs = {o['id']: o for o in self.p.objects({'level': 0, 'area': 0})}
        self.assertEqual(objs['object:0']['name'], 'Monkey')
        self.assertIsNone(objs['object:0']['remove'])               # the second area's list starts after it
        self.assertEqual(objs['object:4']['remove'], 'Remove this object')
        self.assertEqual(objs['object:3']['fields'], [])
        self.assertEqual([c['value'] for c in self.p.choices()['level0area0']], [0x25, 0x27])

    def test_swap(self):
        plan = self.p.edit({'level': 0, 'area': 0}, 'object:0', {'kind': 0x25})
        self.assertEqual(plan['writes'], [(self.c.o(3, CD2_LIST + 2), 0x27, 0x25)])
        self.assertEqual(plan['watch']['want'], 0x25)
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0, 'area': 0}, 'object:0', {'kind': 0x24})
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0, 'area': 0}, 'object:3', {'kind': 0x25})

    def test_remove(self):
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0, 'area': 0}, 'object:1', {}, remove=True)
        plan = self.p.edit({'level': 0, 'area': 0}, 'object:4', {}, remove=True)
        rom = bytearray(self.c.rom)
        for o, old, new in plan['writes']:
            self.assertEqual(rom[o], old)
            rom[o] = new
        after = cd2.ChipDale2Profile(bytes(rom))
        self.assertEqual([r['kind'] for r in after.records(0, 0)], [0x27, 0x25, 0x25, 0x1F, 0x21])
        self.assertEqual(rom[self.c.o(3, CD2_LIST + 19)], 0x44)          # the next list is untouched

    def _frame(self, kind95=None, slot=None):
        r = ram(x40=4, x72=0, x79=CD2_LIST & 0xFF, x7A=CD2_LIST >> 8, xAC=0x00, xAE=1, xB0=0, xB2=2)
        if kind95 is not None:
            r[0x95], r[0x96], r[0x97] = 0x18, 0x22, kind95
        if slot is not None:
            s = 5
            r[0x2F0 + s], r[0x314 + s], r[0x320 + s], r[0x2FC + s], r[0x308 + s] = slot, 0x80, 0, 32, 0
        return bytes(r)

    def test_watcher_swap(self):
        plan = self.p.edit({'level': 0, 'area': 0}, 'object:0', {'kind': 0x25})
        w = self.p.watcher(plan['watch'])
        w.see(self._frame(), 0, 'changed')
        self.assertTrue(w.see(self._frame(0x25), 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        w.see(self._frame(0x27), 0, 'original')
        self.assertEqual(w.result()['state'], 'bad')

    def test_watcher_remove(self):
        watch = {'level': 0, 'start': CD2_LIST, 'end': CD2_LIST + 18, 'col': 0x18, 'row': 0x22, 'x': 0x180, 'y': 512,
                 'old_kind': 0x27, 'removing': True}
        w = self.p.watcher(watch)
        w.see(self._frame(), 0, 'changed')
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(watch)                       # the game read the record
        w.see(self._frame(0x27), 0, 'original')
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(watch)                       # $95-$97 overwritten, but a slot appeared at the place
        w.see(self._frame(), 0, 'original')
        w.see(self._frame(slot=0x06), 1, 'original')
        self.assertEqual(w.result()['state'], 'bad')


if __name__ == '__main__':
    unittest.main()
