"""Master System level profiles: the decoders and the edits, on a made-up cartridge laid out like the real one.

The real games are not part of the tests; these build the same tables at the same addresses, so a change in how a table
is read or written shows here. What the tables mean was proven by replaying the real games (research notes).
"""
import unittest

from romancer.level_profiles import sms_classics as sc

RAM = 0xC000


def apply(rom, writes):
    out = bytearray(rom)
    for offset, old, new in writes:
        assert out[offset] == old, (hex(offset), old, out[offset])
        out[offset] = new
    return bytes(out)


def sonic_cart():
    """256 KB. Level 0 and 1 (same sprite art) and level 2 (other art, sharing level 1's object list)."""
    rom = bytearray(0x40000)
    T = sc.SonicProfile.HEADERS

    def header(level, at, art, objects):
        rom[T + level * 2:T + level * 2 + 2] = (at - T).to_bytes(2, 'little')
        h = bytearray(37)
        h[24:26] = art.to_bytes(2, 'little')
        h[30:32] = (objects - T).to_bytes(2, 'little')
        rom[at:at + 37] = h
    header(0, T + 0x100, 0x612A, T + 0x300)
    header(1, T + 0x140, 0x612A, T + 0x340)
    header(2, T + 0x180, 0x6C3D, T + 0x340)
    # level 0: motobug, crabmeat, ring monitor, an empty record, a flower (other object)
    rom[T + 0x300:T + 0x300 + 16] = bytes([6, 0x10, 0x12, 0x0B, 0x08, 0x2A, 0x0D, 0x01, 0x1D, 0x09, 0xFF, 0, 0, 0x50, 0x09, 0x0B])
    # level 1 (and 2): a badnik 0x0E and an extra-life monitor
    rom[T + 0x340:T + 0x340 + 7] = bytes([3, 0x0E, 0x05, 0x06, 0x03, 0x07, 0x08])
    return bytes(rom)


class Sonic(unittest.TestCase):
    def setUp(self):
        self.rom = sonic_cart()
        self.p = sc.SonicProfile(self.rom)

    def test_records(self):
        T = sc.SonicProfile.HEADERS
        self.assertEqual(self.p.records(0)[0], (0, T + 0x301, 0x10, 0x12, 0x0B))
        self.assertEqual(len(self.p.records(0)), 5)
        self.assertEqual(self.p.sharing(1), [2])
        self.assertEqual(self.p.badniks_for(0), [0x08, 0x0E, 0x10])      # level 1 has the same art
        self.assertEqual(self.p.badniks_for(2), [0x0E])
        self.assertIsNone(self.p.header(3))

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'level': 0})}
        self.assertEqual(set(objects), {'object:0', 'object:1', 'object:2', 'object:4'})     # the empty record is skipped
        moto = objects['object:0']
        self.assertEqual((moto['style'], moto['name'], moto['x'], moto['y']), ('enemy', 'Motobug', 0x12 * 32 + 16, 0x0B * 32 + 32))
        self.assertEqual(objects['object:2']['style'], 'item')
        self.assertEqual(objects['object:2']['detail'], 'holds ten rings')
        self.assertEqual(objects['object:2']['y'], 9 * 32 + 25)
        self.assertEqual(objects['object:4']['style'], 'block')
        self.assertEqual(objects['object:4']['name'], 'Object 0x50')
        self.assertIn('Green Hill Act 3', self.p.objects({'level': 1})[0]['note'])
        self.assertEqual(self.p.part_name({'level': 0}), 'Green Hill Act 1')
        self.assertEqual(self.p.part_name({'level': 28}), 'Special Stage 1')

    def test_edits(self):
        T = sc.SonicProfile.HEADERS
        plan = self.p.edit({'level': 0}, 'object:0', {'type': 0x08})
        self.assertEqual(plan['writes'], [(T + 0x301, 0x10, 0x08)])
        self.assertEqual(plan['watch']['x'], 0x12 * 32)
        changed = sc.SonicProfile(apply(self.rom, plan['writes']))
        self.assertEqual(changed.records(0)[0][2], 0x08)
        self.assertEqual(self.p.edit({'level': 0}, 'object:1', {}, remove=True)['writes'], [(T + 0x304, 0x08, 0xFF)])
        self.assertEqual(self.p.edit({'level': 0}, 'object:2', {'type': 0x04})['writes'], [(T + 0x307, 0x01, 0x04)])
        self.assertEqual(self.p.edit({'level': 0}, 'object:2', {}, remove=True)['writes'], [(T + 0x307, 0x01, 0xFF)])
        with self.assertRaises(ValueError):
            self.p.edit({'level': 2}, 'object:0', {'type': 0x10})          # Motobug's art is not loaded there
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'object:4', {}, remove=True)
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'object:2', {'type': 0x06})

    def test_where_and_watcher(self):
        ram = bytearray(0x2000)
        self.assertIsNone(self.p.where(ram))                                # no header loaded: title or map
        ram[0xD354 - RAM:0xD354 - RAM + 37] = self.p.header(0)
        ram[0xD25A - RAM:0xD25C - RAM] = (300).to_bytes(2, 'little')
        ram[0xD25D - RAM:0xD25F - RAM] = (256).to_bytes(2, 'little')
        self.assertEqual(self.p.where(ram), {'part': {'level': 0}, 'x': 300, 'y': 256})
        plan = self.p.edit({'level': 0}, 'object:0', {'type': 0x08})
        slot = 0xD3FC + 26 - RAM
        ram[slot] = 0x08
        ram[slot + 2:slot + 4] = (0x12 * 32).to_bytes(2, 'little')
        watcher = self.p.watcher(plan['watch'])
        self.assertTrue(watcher.see(ram, 10, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        ram[slot] = 0x10
        control = self.p.watcher(plan['watch'])
        control.see(ram, 10, 'changed')
        self.assertEqual(control.result()['state'], 'bad')
        self.assertEqual(self.p.watcher(plan['watch']).result()['state'], 'warn')


if __name__ == '__main__':
    unittest.main()
