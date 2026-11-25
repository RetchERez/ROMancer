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

class Dt2Cart:
    """A blank UNROM cartridge (8 banks of 16 KB) with DuckTales 2's bank 5 and bank 6 tables at their real addresses."""

    def __init__(self):
        self.rom = bytearray(H + 8 * 0x4000)

    def o(self, bank, address):
        return H + bank * 0x4000 + address - 0x8000

    def put(self, bank, address, data):
        o = self.o(bank, address)
        self.rom[o:o + len(data)] = bytes(data)


# Niagara row 3: (x / 8, y, kind); $9A is a control record (music or palette), counted in record numbers
DT2_ROW3 = [(0x29, 159, 0x4E), (0x31, 63, 0x67), (0x3A, 159, 0x4C), (0x50, 191, 0x33), (0x52, 191, 0x9A),
            (0x54, 191, 0x3C), (0x58, 175, 0x4D), (0x60, 175, 0x6D), (0x62, 175, 0x6E), (0x64, 191, 0x3B),
            (0x70, 191, 0x47)]
DT2_ROW3_AT = 0xA000
DT2_ROW4_AT = DT2_ROW3_AT + 2 + 3 * len(DT2_ROW3)


def dt2_build():
    c = Dt2Cart()
    c.put(6, 0x9424 + 3 * 2, [DT2_ROW3_AT & 0xFF, DT2_ROW3_AT >> 8])         # stage 0 row 3
    c.put(6, 0x9424 + 4 * 2, [DT2_ROW4_AT & 0xFF, DT2_ROW4_AT >> 8])         # stage 0 row 4 (empty)
    c.put(6, DT2_ROW3_AT, [0xFF, 3] + [b for rec in DT2_ROW3 for b in rec])
    c.put(6, DT2_ROW4_AT, [0xFF, 4, 0xFF, 5])
    c.put(6, 0x8ACA, [0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x31])                  # chests $66-$6B
    c.put(6, 0x8B2D, [0x2A, 0x2E, 0x2F, 0x30])                              # large chests $6C-$6F
    c.put(6, 0x89AC, [0x2A, 0x2B, 0x2C, 0x2D])                              # hidden items $32-$35
    c.put(6, 0x89B0, [0x67, 0x68, 0x69, 0x66, 0x6B, 0x52])                  # hidden chests $36-$3B
    for kind, handler in {0x4C: 0x9100, 0x4D: 0x9200, 0x4E: 0x9200, 0x47: 0x9300}.items():
        c.put(5, 0x8E51 + 2 * kind, [handler & 0xFF, handler >> 8])
    return c


class DuckTales2Test(unittest.TestCase):
    def setUp(self):
        self.c = dt2_build()
        self.p = cd2.DuckTales2Profile(bytes(self.c.rom))

    def test_registered(self):
        self.assertIn(cd2.DuckTales2Profile, cd2.PROFILES)
        self.assertEqual(cd2.DuckTales2Profile.sha256s, ('1b6b2323ac4c974d75c07d05a625c4bec582411a04e427b0b95e8d7bc3a17c25',))

    def test_records_and_roles(self):
        recs = self.p.records(0)
        self.assertEqual([r['index'] for r in recs], [0, 1, 2, 3, 5, 6, 7, 8, 9, 10])      # the control is skipped
        frog = recs[0]
        self.assertEqual((frog['row'], frog['x'], frog['y'], frog['kind']), (3, 0x29 * 8, 159, 0x4E))
        self.assertEqual(frog['kind_byte'], self.c.o(6, DT2_ROW3_AT + 2 + 2))
        roles = {r['kind']: (r['role'], r['item']) for r in recs}
        self.assertEqual(roles[0x67], ('chest', 0x2B))
        self.assertEqual(roles[0x6D], ('big chest', 0x2E))
        self.assertEqual(roles[0x33], ('hidden', 0x2B))
        self.assertEqual(roles[0x3B], ('fixed', None))
        self.assertEqual(roles[0x4E], ('enemy', None))
        self.assertEqual(self.p.row_records(0, 0), [])                         # no list of its own

    def test_where(self):
        self.assertIsNone(self.p.where(ram(x8A=0, xC8=0, x1B=3)))
        self.assertIsNone(self.p.where(ram(x8A=1, xC8=7, x1B=3)))
        # the recorded pictures leave out the top 8 lines, so the top of a picture is 8 below the camera
        self.assertEqual(self.p.where(ram(x8A=1, xC8=0, x1B=3, x17=0x34, x18=0x01, x1A=0)),
                         {'part': {'stage': 0}, 'x': 0x134, 'y': 3 * 240 + 8})

    def test_names_and_does(self):
        objects = {o['id']: o for o in self.p.objects({'stage': 0})}
        self.assertEqual(objects['object:3:0']['name'], 'Frog')
        self.assertEqual(objects['object:3:0']['does'], 'Hops toward Scrooge.')
        self.assertEqual(objects['object:3:5']['name'], 'Huey')
        self.assertEqual(objects['object:3:1']['name'], 'Treasure chest')
        self.assertEqual(objects['object:3:3']['name'], 'Hidden large diamond')
        self.assertEqual(objects['object:3:9']['name'], 'Hidden enemy')
        self.assertIn('Scrooge walks over', objects['object:3:9']['does'])
        self.assertEqual(objects['object:3:10']['name'], 'Enemy 0x47')        # not confirmed: keeps its number
        self.assertNotIn('does', objects['object:3:10'])
        self.assertEqual(self.p.kind_name(0x51, 1), 'Crab')
        self.assertEqual(self.p.kind_name(0x5B, 4), 'Ghost')
        self.assertEqual(self.p.kind_name(0x40, 2), 'Launchpad')
        self.assertEqual(self.p.kind_name(0x4C, 3), 'Enemy 0x4c')            # Mu's $4C is another creature

    def test_objects_and_choices(self):
        objects = {o['id']: o for o in self.p.objects({'stage': 0})}
        self.assertEqual(objects['object:3:0']['y'], 3 * 240 + 159)
        chest = objects['object:3:1']
        self.assertEqual(chest['style'], 'item')
        self.assertEqual([c['value'] for c in chest['fields'][0]['choices']], [0x66, 0x67, 0x68, 0x69, 0x6A])
        self.assertEqual([c['value'] for c in objects['object:3:7']['fields'][0]['choices']], [0x6C, 0x6D])
        self.assertIsNone(objects['object:3:8']['remove'])                   # the map piece chest stays
        self.assertEqual(objects['object:3:3']['style'], 'secret')
        self.assertIsNone(objects['object:3:5']['remove'])                   # Huey is left as he is
        # one kind per handler: $4D and $4E share theirs
        self.assertEqual([c['value'] for c in self.p.choices()['stage0']], [0x47, 0x4C, 0x4D])

    def test_swap(self):
        plan = self.p.edit({'stage': 0}, 'object:3:1', {'kind': 0x66})
        self.assertEqual(plan['writes'], [(self.c.o(6, DT2_ROW3_AT + 2 + 3 + 2), 0x67, 0x66)])
        self.assertEqual(plan['watch'], {'stage': 0, 'row': 3, 'index': 1, 'x': 0x31 * 8, 'y': 63, 'old_kind': 0x67,
                                         'removing': False, 'want': 0x66,
                                         'name': 'treasure chest holding red diamond ($50,000)'})
        plan = self.p.edit({'stage': 0}, 'object:3:0', {'kind': 0x4C})
        self.assertEqual(plan['writes'], [(self.c.o(6, DT2_ROW3_AT + 4), 0x4E, 0x4C)])
        self.assertEqual(plan['title'], 'Object here: Plant')
        plan = self.p.edit({'stage': 0}, 'object:3:3', {'kind': 0x32})
        self.assertEqual(plan['writes'], [(self.c.o(6, DT2_ROW3_AT + 2 + 9 + 2), 0x33, 0x32)])
        plan = self.p.edit({'stage': 0}, 'object:3:7', {'kind': 0x6C})
        self.assertEqual(plan['writes'], [(self.c.o(6, DT2_ROW3_AT + 2 + 21 + 2), 0x6D, 0x6C)])
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 0}, 'object:3:0', {'kind': 0x55})           # not used in this stage
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 0}, 'object:3:1', {'kind': 0x6B})           # the stage treasure is not offered
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 0}, 'object:3:8', {'kind': 0x6C})           # the map piece chest
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 0}, 'object:3:5', {}, remove=True)           # Huey

    def test_remove(self):
        plan = self.p.edit({'stage': 0}, 'object:3:2', {}, remove=True)
        rom = bytearray(self.c.rom)
        for offset, old, new in plan['writes']:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        after = cd2.DuckTales2(bytes(rom))
        kinds = [k for n, a, x, y, k in after.row_records(0, 3)]
        self.assertEqual(kinds, [0x4E, 0x67, 0x33, 0x9A, 0x3C, 0x4D, 0x6D, 0x6E, 0x3B, 0x47])
        self.assertEqual(after.list_at(0, 4), DT2_ROW4_AT)                    # the next row's list did not move
        self.assertEqual(rom[self.c.o(6, DT2_ROW4_AT - 3):self.c.o(6, DT2_ROW4_AT)], b'\xff\xff\xff')
        self.assertTrue(plan['watch']['removing'])
        self.assertEqual(plan['title'], 'Remove plant')

    def _play(self, w, spawn_kind, x=0x3A * 8):
        base = dict(x8A=1, xC8=0, x1B=3, x17=0x40, x18=0x01)
        w.see(ram(**base), 0, 'changed')
        r = ram(**base)
        if spawn_kind is not None:
            s = 4
            r[0x3FE + s], r[0x41E + s], r[0x4EE + s] = spawn_kind, 2, 3
            r[0x50E + s], r[0x4FE + s], r[0x51E + s] = x >> 8, x & 0xFF, 159
        w.see(r, 1, 'changed')
        return w.result()

    def test_watcher(self):
        swap = self.p.edit({'stage': 0}, 'object:3:2', {'kind': 0x4D})['watch']
        self.assertEqual(self._play(self.p.watcher(swap), 0x4D)['state'], 'good')
        self.assertEqual(self._play(self.p.watcher(swap), 0x4C)['state'], 'bad')
        self.assertEqual(self._play(self.p.watcher(swap), None)['state'], 'warn')
        self.assertEqual(self._play(self.p.watcher(swap), 0x4D, x=0x58 * 8)['state'], 'warn')   # another place
        remove = self.p.edit({'stage': 0}, 'object:3:2', {}, remove=True)['watch']
        self.assertEqual(self._play(self.p.watcher(remove), None)['state'], 'good')
        self.assertEqual(self._play(self.p.watcher(remove), 0x4C)['state'], 'bad')
        w = self.p.watcher(remove)
        w.see(ram(x8A=0), 0, 'changed')
        self.assertEqual(w.result()['state'], 'warn')                         # never in the stage

    def test_watcher_counts_objects_there_on_the_first_frame(self):
        # the stage spawns the first screen's objects before $8A turns 1
        swap = self.p.edit({'stage': 0}, 'object:3:2', {'kind': 0x4D})['watch']
        w = self.p.watcher(swap)
        r = ram(x8A=1, xC8=0, x1B=3, x17=0x40, x18=0x01)
        r[0x3FE + 2], r[0x41E + 2], r[0x4EE + 2], r[0x50E + 2], r[0x4FE + 2], r[0x51E + 2] = 0x4D, 2, 3, 0x01, 0xD0, 159
        self.assertTrue(w.see(r, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')


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
