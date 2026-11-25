"""Sonic The Hedgehog 2 (Master System) level profile: the decoders and the edits, on a made-up cartridge laid out like
the real one.

The real game is not part of the tests; these build the same tables at the same addresses, so a change in how a table is
read or written shows here. What the tables mean was proven by replaying the real game (research notes).
"""
import unittest

from romancer.level_profiles import Ram
from romancer.level_profiles import sms_more as sm

S2 = sm.Sonic2Profile
BANK = 0x78000 - 0x8000


def apply(rom, writes):
    out = bytearray(rom)
    for offset, old, new in writes:
        assert out[offset] == old, (hex(offset), old, out[offset])
        out[offset] = new
    return bytes(out)


def record(kind, x, y, b5=0, b6=0, b7=0, b8=0):
    return bytes([kind, x & 255, x >> 8, y & 255, y >> 8, b5, b6, b7, b8])


def sonic2_cart():
    """512 KB. Zone 0 (Under Ground) act 1: a crab robot, an item box with an extra life, an end sign and an event record;
    act 2: a drill robot (the zone's other badnik, with its own art place) and a crab robot. Every other act is empty."""
    rom = bytearray(0x80000)
    lists = {(0, 0): record(0x23, 640, 400, 0, 0, 0xD4, 0xD4) + record(0x10, 1969, 110, 0, 3) + record(0x18, 5251, 366, 0, 0, 0x62, 0x62)
             + record(0xFE, 100, 100, 1),
             (0, 1): record(0x34, 1600, 496, 0, 0, 0x98, 0xA8) + record(0x23, 416, 272, 0, 0, 0xD4, 0xD4) + record(0x23, 900, 272, 0, 0, 0xD4, 0xD4)}
    at = 0x8173                       # CPU address of the first list (in bank 30), as in the game
    tables = 0x8149
    for zone in range(7):
        rom[0x78135 + zone * 2:0x78137 + zone * 2] = (tables + zone * 6).to_bytes(2, 'little')
        for act in range(3):
            data = lists.get((zone, act), b'') + b'\xFF'
            rom[BANK + tables + zone * 6 + act * 2:BANK + tables + zone * 6 + act * 2 + 2] = at.to_bytes(2, 'little')
            rom[BANK + at:BANK + at + len(data)] = data
            at += len(data)
    return bytes(rom)


def ram(zone=0, act=0, sonic=1, camera=(8, 48), statuses=None, slots=()):
    data = bytearray(0x2000)
    data[0xD295 - 0xC000], data[0xD296 - 0xC000], data[0xD500 - 0xC000] = zone, act, sonic
    data[0xD174 - 0xC000:0xD176 - 0xC000] = camera[0].to_bytes(2, 'little')
    data[0xD176 - 0xC000:0xD178 - 0xC000] = camera[1].to_bytes(2, 'little')
    for number, status in (statuses or {}).items():
        data[0xD400 - 0xC000 + number] = status
    for index, (kind, number, content) in enumerate(slots):
        base = 0xD700 + index * 0x40 - 0xC000
        data[base], data[base + 0x3E], data[base + 0x3F] = kind, number + 1, content
    return Ram(bytes(data))


class Sonic2(unittest.TestCase):
    def setUp(self):
        self.rom = sonic2_cart()
        self.p = S2(self.rom)

    def test_records(self):
        first = self.p.records(0, 0)[0]
        self.assertEqual(first, (0, BANK + 0x8173, 0x23, 640, 400, (0, 0, 0xD4, 0xD4)))
        self.assertEqual(len(self.p.records(0, 0)), 4)
        self.assertEqual([r[2] for r in self.p.records(0, 1)], [0x34, 0x23, 0x23])
        self.assertEqual(self.p.records(3, 2), [])
        self.assertEqual(self.p.zone_badniks(0), {0x23: (0, 0, 0xD4, 0xD4), 0x34: (0, 0, 0x98, 0xA8)})
        self.assertEqual(self.p.zone_badniks(1), {})

    def test_where(self):
        self.assertEqual(self.p.where(ram(0, 1, camera=(300, 120))), {'part': {'zone': 0, 'act': 1}, 'x': 300, 'y': 120})
        self.assertIsNone(self.p.where(ram(9, 0)))              # the opening and the title use zone 9
        self.assertIsNone(self.p.where(ram(0, 0, sonic=0)))     # the title card: no Sonic yet
        self.assertEqual(self.p.part_name({'zone': 4, 'act': 2}), 'Gimmick Mt. Act 3')

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'zone': 0, 'act': 0})}
        self.assertEqual(set(objects), {'object:0', 'object:1', 'object:2'})     # the event record makes nothing
        crab = objects['object:0']
        self.assertEqual((crab['style'], crab['name'], crab['x'], crab['y']), ('enemy', 'Crab robot', 640, 409))
        self.assertTrue(crab['does'])
        self.assertEqual([c['name'] for c in crab['fields'][0]['choices']], ['Crab robot', 'Drill robot'])
        box = objects['object:1']
        self.assertEqual((box['style'], box['name'], box['detail'], box['y']), ('item', 'Item box', 'holds extra life', 119))
        self.assertEqual(box['fields'][0]['choices'], 'contents')
        self.assertEqual([c['name'] for c in self.p.choices()['contents']],
                         ['Ten rings', 'Extra life', 'Speed shoes', 'Invincibility', 'Continue'])
        sign = objects['object:2']
        self.assertEqual((sign['style'], sign['name'], sign['remove']), ('block', 'End sign', None))

    def test_names(self):
        for kind in list(S2.BADNIKS) + list(S2.OTHER) + [S2.BOX]:
            self.assertFalse(S2.type_name(kind).startswith('Object'), hex(kind))
        for kind, (name, does) in S2.BADNIKS.items():
            self.assertTrue(does and does.endswith('.'), hex(kind))
        self.assertEqual(S2.shown_name(0x10, 5), 'an item box with invincibility')
        self.assertEqual(S2.type_name(0x99), 'Object 0x99')

    def test_badnik_edits(self):
        start = BANK + 0x8173
        swap = self.p.edit({'zone': 0, 'act': 0}, 'object:0', {'type': 0x34})
        self.assertEqual(swap['writes'], [(start, 0x23, 0x34), (start + 7, 0xD4, 0x98), (start + 8, 0xD4, 0xA8)])
        self.assertEqual(swap['watch']['type'], 0x34)
        changed = S2(apply(self.rom, swap['writes']))
        self.assertEqual(changed.records(0, 0)[0][2:], (0x34, 640, 400, (0, 0, 0x98, 0xA8)))
        gone = self.p.edit({'zone': 0, 'act': 0}, 'object:0', {}, remove=True)
        self.assertEqual(gone['writes'], [(start, 0x23, 0xFE), (start + 5, 0, 1)])
        self.assertTrue(gone['watch']['remove'])
        after = S2(apply(self.rom, gone['writes']))
        self.assertEqual(len(after.records(0, 0)), 4)             # the list still runs to its end
        self.assertNotIn('object:0', {o['id'] for o in after.objects({'zone': 0, 'act': 0})})
        self.assertEqual(self.p.edit({'zone': 0, 'act': 0}, 'object:0', {'type': 0x23})['writes'], [])
        with self.assertRaises(ValueError):
            self.p.edit({'zone': 0, 'act': 0}, 'object:0', {'type': 0x39})      # not one of the zone's own
        with self.assertRaises(ValueError):
            self.p.edit({'zone': 0, 'act': 0}, 'object:2', {}, remove=True)      # the end sign cannot be changed

    def test_box_edits(self):
        start = BANK + 0x8173 + 9
        plan = self.p.edit({'zone': 0, 'act': 0}, 'object:1', {'content': 5})
        self.assertEqual(plan['writes'], [(start + 6, 3, 5)])
        self.assertEqual((plan['watch']['type'], plan['watch']['content']), (0x10, 5))
        self.assertEqual(self.p.edit({'zone': 0, 'act': 0}, 'object:1', {}, remove=True)['writes'], [(start, 0x10, 0xFE), (start + 5, 0, 1)])
        with self.assertRaises(ValueError):
            self.p.edit({'zone': 0, 'act': 0}, 'object:1', {'content': 7})

    def test_watcher(self):
        plan = self.p.edit({'zone': 0, 'act': 0}, 'object:1', {'content': 5})
        w = self.p.watcher(plan['watch'])
        self.assertFalse(w.see(ram(), 0, 'changed'))                             # not read yet
        self.assertFalse(w.see(ram(0, 1, statuses={1: 0x10}), 0, 'changed'))     # another act
        self.assertTrue(w.see(ram(statuses={1: 0x10}, slots=[(0x23, 0, 0), (0x10, 1, 5)]), 1, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        w = self.p.watcher(plan['watch'])
        w.see(ram(statuses={1: 0x10}, slots=[(0x10, 1, 3)]), 1, 'original')
        self.assertEqual(w.result()['state'], 'bad')
        gone = self.p.watcher(self.p.edit({'zone': 0, 'act': 0}, 'object:0', {}, remove=True)['watch'])
        gone.see(ram(statuses={0: 0xFF}), 1, 'changed')
        self.assertEqual(gone.result()['state'], 'good')
        kept = self.p.watcher(self.p.edit({'zone': 0, 'act': 0}, 'object:0', {}, remove=True)['watch'])
        kept.see(ram(statuses={0: 0x23}, slots=[(0x23, 0, 0)]), 1, 'original')
        self.assertEqual(kept.result()['state'], 'bad')
        swap = self.p.watcher(self.p.edit({'zone': 0, 'act': 0}, 'object:0', {'type': 0x34})['watch'])
        swap.see(ram(statuses={0: 0x34}, slots=[(0x34, 0, 0)]), 1, 'changed')
        self.assertEqual(swap.result()['state'], 'good')
        self.assertEqual(self.p.watcher(plan['watch']).result()['state'], 'warn')

    def test_profile_registry_entry(self):
        self.assertEqual(sm.PROFILES, [S2])
        self.assertEqual(S2.system, 'sms')
        self.assertEqual(S2.sha256s, ('b7bb3b55ca308ce0d235469f877d21f8188960aec5cd473349ab66cac089927d',))


if __name__ == '__main__':
    unittest.main()
