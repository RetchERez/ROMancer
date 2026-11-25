"""Contra level profile on a made-up cartridge with the game's tables at their real addresses."""
import unittest

from romancer.level_profiles.contra import ContraProfile, WEAPONS

HEADER = 16


def put(rom, address, data):
    at = HEADER + 0x8000 + (address - 0x8000)          # bank 2
    rom[at:at + len(data)] = bytes(data)


def cart():
    rom = bytearray(HEADER + 0x20000)
    rom[:4] = b'NES\x1a'
    for level in range(8):
        settings = [0] * 32
        settings[0] = 1 if level in (1, 3) else 0       # base stages
        settings[1] = 1 if level == 2 else 0            # the Waterfall scrolls up
        settings[8] = 1                                 # two screens each
        put(rom, 0xB319 + level * 32, settings)
        put(rom, 0xB513 + level * 2, [0x00, 0xB0 + level])
    # level 0: screen 0 has a soldier, a pillbox (M) and two riflemen from one entry; screen 1 a capsule (R) and a boss part
    put(rom, 0xB000, [0x00, 0xA0, 0x0B, 0xA0])
    put(rom, 0xA000, [0x10, 0x05, 0x60, 0x60, 0x02, 0xA1, 0x80, 0x46, 0x40, 0xC1, 0xFF,
                      0xF0, 0x03, 0x40, 0xA8, 0x10, 0x81, 0xFF])
    # level 2 (Waterfall): screen 0 one soldier
    put(rom, 0xB200, [0x00, 0xA1, 0x00, 0xA1])
    put(rom, 0xA100, [0x30, 0x05, 0x80, 0xFF])
    # base levels point at one shared list
    for level in (1, 3):
        put(rom, 0xB000 + level * 0x100, [0x00, 0xA2, 0x00, 0xA2])
    put(rom, 0xA200, [0xFF])
    for level in (4, 5, 6, 7):
        put(rom, 0xB000 + level * 0x100, [0x00, 0xA2, 0x00, 0xA2])
    return rom


def ram(level=0, screen=0, x=0, playing=True):
    r = bytearray(0x800)
    r[0x18], r[0x2C], r[0x30], r[0x64], r[0x65] = (5 if playing else 3), 4, level, screen, x
    return r


class ContraTest(unittest.TestCase):
    def setUp(self):
        self.rom = cart()
        self.p = ContraProfile(bytes(self.rom))

    def test_where(self):
        self.assertEqual(self.p.where(ram(0, 1, 0x20)), {'part': {'stage': 0}, 'x': 0x120, 'y': 0})
        self.assertEqual(self.p.where(ram(2, 0, 0x10)), {'part': {'stage': 2}, 'x': 0, 'y': 240 - 0x10})
        self.assertIsNone(self.p.where(ram(1)))                       # a base stage
        self.assertIsNone(self.p.where(ram(0, playing=False)))
        self.assertEqual(self.p.part_name({'stage': 0}), 'Stage 1: Jungle')

    def test_objects(self):
        objs = {o['id']: o for o in self.p.objects({'stage': 0})}
        self.assertEqual(sorted(objs), ['enemy:0:0:0', 'enemy:0:1:0', 'enemy:0:2:0', 'enemy:0:2:1', 'enemy:1:0:0', 'enemy:1:1:0'])
        soldier = objs['enemy:0:0:0']
        self.assertEqual((soldier['x'], soldier['y'], soldier['name']), (0x10 + 0xF0, 0x68, 'Running soldier'))
        self.assertEqual(objs['enemy:0:1:0']['detail'], 'leaves M: machine gun')
        self.assertEqual(objs['enemy:0:2:1']['name'], 'Rifleman, hiding in the bushes')
        self.assertEqual(objs['enemy:1:0:0']['x'], 256 + 0xF0 + 0xF0)
        self.assertIsNone(objs['enemy:1:1:0']['remove'])                 # boss part
        self.assertTrue(all(o['does'] for o in objs.values()))
        water = self.p.objects({'stage': 2})[0]
        self.assertEqual((water['x'], water['y']), (0x88, 240 - 0x30 + 16))
        self.assertEqual(self.p.objects({'stage': 1}), [])

    def test_choices_are_the_stage_own(self):
        values = {c['value'] for c in self.p.type_choices(0)}
        self.assertEqual(values, {0x50, 0x21, 0x60, 0x61, 0x30})          # no boss part
        self.assertEqual(len(self.p.choices()['weapons']), len(WEAPONS))

    def test_swap(self):
        plan = self.p.edit({'stage': 0}, 'enemy:0:0:0', {'enemy': 0x60})
        self.assertEqual(plan['writes'], [(HEADER + 0xA001, 0x05, 0x06)])
        self.assertEqual(plan['watch']['type'], 6)
        plan = self.p.edit({'stage': 0}, 'enemy:0:0:0', {'enemy': 0x21})     # a pillbox with its setting
        self.assertEqual(plan['writes'], [(HEADER + 0xA001, 0x05, 0x02), (HEADER + 0xA002, 0x60, 0x61)])
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 0}, 'enemy:0:0:0', {'enemy': 0x110})      # the boss part is not offered

    def test_weapon(self):
        plan = self.p.edit({'stage': 0}, 'enemy:0:1:0', {'weapon': 4})
        self.assertEqual(plan['writes'], [(HEADER + 0xA005, 0xA1, 0xA4)])
        self.assertEqual((plan['watch']['type'], plan['watch']['setting']), (2, 4))
        with self.assertRaises(ValueError):
            self.p.edit({'stage': 0}, 'enemy:0:0:0', {'weapon': 1})          # a soldier carries nothing

    def test_remove(self):
        plan = self.p.edit({'stage': 0}, 'enemy:0:1:0', {}, remove=True)
        new = bytearray(self.rom)
        for at, old, value in plan['writes']:
            self.assertEqual(new[at], old)
            new[at] = value
        p = ContraProfile(bytes(new))
        self.assertEqual([(e['type'], len(e['places'])) for e in p.entries(0, 0)], [(5, 1), (6, 2)])
        self.assertEqual(new[HEADER + 0xA000 + 8:HEADER + 0xA000 + 11], b'\xff\xff\xff')
        # one copy of a two-copy entry
        plan = self.p.edit({'stage': 0}, 'enemy:0:2:0', {}, remove=True)
        new = bytearray(self.rom)
        for at, old, value in plan['writes']:
            new[at] = value
        p = ContraProfile(bytes(new))
        self.assertEqual([(e['type'], [v for v, _ in e['places']]) for e in p.entries(0, 0)], [(5, [0x60]), (2, [0xA1]), (6, [0xC1])])
        self.assertEqual(p.entries(1, 0), self.p.entries(1, 0))

    def test_shared_lists_refuse_removal(self):
        with self.assertRaises(ValueError):
            self.p.remove_writes(1, 0, 0)

    def test_watcher(self):
        plan = self.p.edit({'stage': 0}, 'enemy:0:0:0', {'enemy': 0x60})
        w = self.p.watcher(plan['watch'])
        r = ram(0, 0, 0x0F)
        w.see(bytes(r), 1, 'changed')
        r[0x65] = 0x10
        r[0x4B8 + 15], r[0x528 + 15], r[0x5A8 + 15], r[0x33E + 15], r[0x324 + 15] = 1, 6, 0, 0xF0, 0x60
        for f in range(2, 12):
            if w.see(bytes(r), f, 'changed'):
                break
        self.assertEqual(w.result()['state'], 'good')
        control = self.p.watcher(plan['watch'])
        r2 = ram(0, 0, 0x0F)
        control.see(bytes(r2), 1, 'changed')
        r2[0x65] = 0x10
        r2[0x4B8 + 15], r2[0x528 + 15], r2[0x33E + 15] = 1, 5, 0xF0
        for f in range(2, 12):
            control.see(bytes(r2), f, 'changed')
        self.assertEqual(control.result()['state'], 'bad')


if __name__ == '__main__':
    unittest.main()
