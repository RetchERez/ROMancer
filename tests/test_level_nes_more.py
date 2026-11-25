"""Bubble Bobble level profile (nes_more): decoding and every edit's writes, on a made-up cartridge with the round tables
at their real places (research/nes_more-level-profile.md). No real game data beyond the table layout."""
import unittest

from romancer.level_profiles import nes_more as nm
from romancer.level_profiles import Watcher

H = nm.HEADER


def cart():
    rom = bytearray(H + 8 * 0x4000)
    # sprite bank table $F78D (bank 7 at $C000): rounds >> 4 -> CHR bank
    rom[H + 7 * 0x4000 + 0x378D:H + 7 * 0x4000 + 0x3795] = bytes([2, 2, 2, 3, 2, 4, 5, 0xAD])
    p = nm.BubbleBobbleProfile(bytes(rom))
    # round 1: three Zen-chan in slots 0, 3, 6; round 18 (second half of bank 0): a Monsta; round 49: a Drunk
    for rnd, body in ((1, [0x03, 0x81, 48, 120, 0xB1, 64, 120, 0xE1, 80, 120]), (18, [0x13, 0x06, 72, 56]),
                      (49, [0x36, 0x84, 120, 168])):
        at = p.record_offset(rnd)
        rom[at:at + 0x16] = bytes((body + [0xFF] * 0x16)[:0x16])
    rom[p.nibble_offset(1)] = 0x01          # round 1 high nibble 0, round 2 low nibble 1
    rom[p.nibble_offset(17)] = 0x9C         # round 17: lightning (9), round 18: lightning and fire (C)
    return rom


class Decode(unittest.TestCase):
    def setUp(self):
        self.rom = cart()
        self.p = nm.BubbleBobbleProfile(bytes(self.rom))

    def test_offsets(self):
        self.assertEqual(self.p.record_offset(1), H + 0x156B)
        self.assertEqual(self.p.record_offset(18), H + 0x2000 + 0x156B + 0x16)
        self.assertEqual(self.p.record_offset(49), H + 0x4000 + 0x2000 + 0x156B)     # round 49: bank 1, $A000 half
        self.assertEqual(self.p.nibble_offset(18), H + 0x2000 + 0x1520)

    def test_enemies_and_names(self):
        rows = self.p.enemies(1)
        self.assertEqual([(e['type'], e['slot'], e['drop_y'], e['x']) for e in rows], [(1, 0, 48, 120), (1, 3, 64, 120), (1, 6, 80, 120)])
        objs = self.p.objects({'round': 1})
        self.assertEqual(objs[0]['name'], 'Zen-chan')
        self.assertTrue(objs[0]['does'])
        self.assertEqual((objs[0]['x'], objs[0]['y']), (128, 56))
        self.assertEqual(self.p.objects({'round': 49})[0]['name'], 'Drunk')
        self.assertEqual(self.p.objects({'round': 18})[0]['name'], 'Monsta')
        for kind, (name, does) in nm.BubbleBobble.ENEMIES.items():
            self.assertFalse(name.startswith('Enemy'))
            self.assertTrue(does.endswith('.'))

    def test_bank_choices(self):
        self.assertNotIn(4, self.p.allowed_types(1))            # Drunk cannot be drawn in rounds 1-47
        self.assertIn(4, self.p.allowed_types(49))
        names = [c['name'] for c in self.p.objects({'round': 1})[0]['fields'][0]['choices']]
        self.assertIn('Mighta', names)
        self.assertNotIn('Drunk', names)

    def test_bubbles(self):
        self.assertEqual(self.p.nibble(1), 0)
        self.assertEqual(self.p.nibble(2), 1)
        self.assertEqual(self.p.nibble(18), 0xC)
        bub = [o for o in self.p.objects({'round': 18}) if o['id'] == 'bubbles'][0]
        self.assertEqual(bub['name'], 'Lightning and fire bubbles')

    def test_where(self):
        ram = bytearray(0x800)
        self.assertIsNone(self.p.where(bytes(ram)))
        ram[0x401] = 7
        self.assertEqual(self.p.where(bytes(ram))['part'], {'round': 7})
        ram[0xFC] = 0x40
        self.assertIsNone(self.p.where(bytes(ram)))


class Edits(unittest.TestCase):
    def setUp(self):
        self.p = nm.BubbleBobbleProfile(bytes(cart()))

    def test_swap(self):
        plan = self.p.edit({'round': 1}, 'enemy:1', {'type': 2})
        self.assertEqual(plan['writes'], [(H + 0x156B + 4, 0xB1, 0xB2)])
        self.assertEqual(plan['watch'], {'kind': 'enemy', 'round': 1, 'slot': 3, 'type': 2, 'name': 'Mighta'})
        with self.assertRaises(ValueError):
            self.p.edit({'round': 1}, 'enemy:1', {'type': 4})

    def test_remove(self):
        plan = self.p.edit({'round': 1}, 'enemy:0', {}, remove=True)
        at = H + 0x156B
        rom = bytearray(self.p.rom)
        for off, old, new in plan['writes']:
            self.assertEqual(rom[off], old)
            rom[off] = new
        self.assertEqual(bytes(rom[at + 1:at + 8]), bytes([0xB1, 64, 120, 0xE1, 80, 120, 0xFF]))
        self.assertEqual(plan['watch']['slot'], 0)
        self.assertIsNone(plan['watch']['type'])

    def test_bubble_writes_keep_other_round(self):
        plan = self.p.edit({'round': 18}, 'bubbles', {'bubbles': 2})
        self.assertEqual(plan['writes'], [(self.p.nibble_offset(18), 0x9C, 0x92)])
        plan = self.p.edit({'round': 17}, 'bubbles', {'bubbles': 0})
        self.assertEqual(plan['writes'], [(self.p.nibble_offset(17), 0x9C, 0x1C)])
        with self.assertRaises(ValueError):
            self.p.edit({'round': 17}, 'bubbles', {'bubbles': 6})

    def test_watchers(self):
        ram = bytearray(0x800)
        w = self.p.watcher(self.p.edit({'round': 1}, 'enemy:1', {'type': 2})['watch'])
        self.assertIsInstance(w, Watcher)
        ram[0x401] = 1
        ram[0x68 + 12] = 0x82
        self.assertTrue(w.see(bytes(ram), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(self.p.edit({'round': 1}, 'bubbles', {'bubbles': 2})['watch'])
        ram[0x88] = 0xF8
        self.assertTrue(w.see(bytes(ram), 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')


if __name__ == '__main__':
    unittest.main()
