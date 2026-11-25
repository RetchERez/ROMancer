"""Mega Man 6 level profile on a made-up cartridge with the game's tables at their real addresses."""
import unittest

from romancer.level_profiles.megaman6 import MegaMan6

HEADER = 16
LIST, SCRIPTS = 0x3A * 0x2000, 0x39 * 0x2000


def cart():
    rom = bytearray(HEADER + 0x80000)
    rom[:6] = b'NES\x1a\x20\x00'
    put = lambda bank, address, data: rom.__setitem__(slice(HEADER + bank + address - 0x8000, HEADER + bank + address - 0x8000 + len(data)), bytes(data))
    # stage 0: records (screen, x, y, type); type $80 = room script number y
    recs = [(0, 0x40, 0, 0x80), (1, 0x50, 0x80, 0x24), (2, 0x30, 0x70, 0x38), (2, 0xC0, 1, 0x80), (3, 0x20, 0x90, 0x25),
            (3, 0x80, 2, 0x80), (4, 0x10, 0xF3, 0x5B), (4, 0x80, 3, 0x80), (4, 0x90, 0x60, 0x26)]
    n = len(recs)
    block = [0x36] + [r[0] for r in recs] + [0xFF] + [r[1] for r in recs] + [0xFF] + [r[2] for r in recs] + [0xFF] + [r[3] for r in recs]
    put(LIST, 0x85D8, block)
    put(LIST, 0x85D8 + len(block), [0x11, 0x22, 0x33, 0x44])      # the next stage's block
    put(LIST, 0x80BF, [0xD8]); put(LIST, 0x80CF, [0x85]); put(LIST, 0x80DF, [n])
    # scripts: 0 scroll right; 1 no scroll, ladder up (transition 2); 2 scroll right; 3 the boss room (table entry outside bank $39)
    for k, address in enumerate((0x8400, 0x8410, 0x8420, 0xF943)):
        put(SCRIPTS, 0x82EB + k, [address & 0xFF]); put(SCRIPTS, 0x836B + k, [address >> 8])
    put(SCRIPTS, 0x8400, [0x01, 0, 0, 0])
    put(SCRIPTS, 0x8410, [0x02, 0, 0, 0x02, 0, 0, 0])
    put(SCRIPTS, 0x8420, [0x01, 0, 0, 0x05, 0, 0, 0])
    return rom


def ram(stage=0, screen=0, x=0, slots=()):
    r = bytearray(0x800)
    r[0x51], r[0x57], r[0x56], r[0x3A0], r[0x441] = stage, screen, x, 4, 0x38
    for slot in range(0x16):
        r[0x3FC + slot] = 0xFF
    for slot, number, kind, wx in slots:
        r[0x3A0 + slot], r[0x3FC + slot], r[0x46F + slot], r[0x486 + slot] = kind, number, wx >> 8, wx & 0xFF
    return bytes(r)


class MegaMan6Test(unittest.TestCase):
    def setUp(self):
        self.rom = cart()
        self.p = MegaMan6(bytes(self.rom))

    def test_records_and_editable(self):
        recs = self.p.records(0)
        self.assertEqual([(r['screen'], r['x'], r['type']) for r in recs][:3], [(0, 0x40, 0x80), (1, 0x50, 0x24), (2, 0x30, 0x38)])
        self.assertEqual([r['number'] for r in recs if r['editable']], [1, 2, 4])     # not scripts, y $F0+, or the boss room
        self.assertEqual(self.p.boss_screens(0), {4})

    def test_sections(self):
        self.assertEqual([(s['first'], s['last'], s['link']) for s in self.p.sections(0)], [(0, 2, 0x80), (3, 4, 0)])     # a door on the right goes on

    def test_where(self):
        self.assertEqual(self.p.where(ram(screen=1, x=0x20)), {'part': {'stage': 0, 'section': 0}, 'x': 0x120, 'y': 0})
        self.assertEqual(self.p.where(ram(screen=3, x=0)), {'part': {'stage': 0, 'section': 1}, 'x': 0, 'y': 0})
        beaming = bytearray(ram(screen=1)); beaming[0x441] = 0x3B
        self.assertIsNone(self.p.where(bytes(beaming)))

    def test_objects_and_choices(self):
        objects = self.p.objects({'stage': 0, 'section': 0})
        self.assertEqual([o['id'] for o in objects], ['record:1', 'record:2', 'link:0'])
        self.assertEqual(objects[1]['name'], 'Small life energy')
        self.assertEqual(objects[0]['fields'][0]['choices'], 'enemies 0')
        self.assertEqual([c['value'] for c in self.p.choices()['enemies 0']], [0x24, 0x25])
        self.assertEqual(len(self.p.choices()['items']), 6)

    def test_swap(self):
        plan = self.p.edit({'stage': 0, 'section': 0}, 'record:1', {'type': 0x25})
        n = 9
        self.assertEqual(plan['writes'], [(HEADER + LIST + 0x5D8 + 3 * n + 4 + 1, 0x24, 0x25)])
        plan = self.p.edit({'stage': 0, 'section': 0}, 'record:2', {'type': 0x37})
        self.assertEqual(plan['writes'][0][2], 0x37)
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 0, 'section': 0}, 'record:1', {'type': 0x38})     # an item is not an enemy choice
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 0, 'section': 0}, 'record:0', {'type': 0x24})     # a room script is not editable

    def test_remove(self):
        plan = self.p.edit({'stage': 0, 'section': 0}, 'record:1', {}, remove=True)
        rom = bytearray(self.rom)
        for at, old, new in plan['writes']:
            self.assertEqual(rom[at], old)
            rom[at] = new
        p = MegaMan6(bytes(rom))
        self.assertEqual(p.block(0)[1], 8)
        self.assertEqual([(r['screen'], r['x'], r['y'], r['type']) for r in p.records(0)][:3], [(0, 0x40, 0, 0x80), (2, 0x30, 0x70, 0x38), (2, 0xC0, 1, 0x80)])
        start = HEADER + LIST + 0x5D8
        self.assertEqual(rom[start + 1 + 8], 0xFF)                       # the end mark after the screens
        self.assertEqual(rom[start + 4 * 9: start + 4 * 9 + 4], bytes([0xFF] * 4))
        self.assertEqual(rom[start + 4 * 9 + 4], 0x11)                   # the next stage's block is untouched
        self.assertEqual(plan['watch']['next_type'], 0x38)

    def test_watcher(self):
        plan = self.p.edit({'stage': 0, 'section': 0}, 'record:1', {'type': 0x25})
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram(screen=0, x=0x80, slots=[(0x15, 1, 0x25, 0x150)]), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram(screen=0, x=0x80, slots=[(0x15, 1, 0x24, 0x150)]), 0, 'original'))
        self.assertEqual(w.result()['state'], 'bad')
        plan = self.p.edit({'stage': 0, 'section': 0}, 'record:1', {}, remove=True)
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram(screen=1, x=0x80), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')



class MegaMan6NamesTest(unittest.TestCase):
    def setUp(self):
        self.p = MegaMan6(bytes(cart()))

    def test_stage_names(self):
        # the made-up stage 0 has enemies 0x24 and 0x25: 0x24 is named for Blizzard Man's stage, 0x25 is not watched
        objects = self.p.objects({'stage': 0, 'section': 0})
        self.assertEqual(objects[0]['name'], 'Propeller capsule robot')
        self.assertEqual(objects[0]['does'], 'Flies down to the ground, then moves toward you.')
        self.assertEqual(objects[1]['does'], 'Restores 2 units of life energy.')
        self.assertEqual([c['name'] for c in self.p.choices()['enemies 0']], ['Propeller capsule robot', 'Enemy 0x25'])
        self.assertEqual(self.p.type_name(0x24, 2), 'Orange lantern robot')     # one number, another stage's picture
        self.assertEqual(self.p.type_name(0x70, 11), 'Small red helmet robot')  # same in every stage watched

    def test_titles(self):
        plan = self.p.edit({'stage': 0, 'section': 0}, 'record:1', {}, remove=True)
        self.assertEqual(plan['title'], 'Remove the propeller capsule robot')
        plan = self.p.edit({'stage': 0, 'section': 0}, 'record:1', {'type': 0x25})
        self.assertEqual(plan['title'], 'Propeller capsule robot becomes enemy 0x25')

    def test_tables(self):
        for stage, kinds in self.p.STAGE_ENEMIES.items():
            for kind, (name, does) in kinds.items():
                self.assertFalse(name.startswith('Enemy'))
                self.assertTrue(does is None or does.endswith('.'))


if __name__ == '__main__':
    unittest.main()
