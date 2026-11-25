"""Wonder Boy III level profile: the decoders and the edits, on a made-up cartridge laid out like the real one.

The real game is not part of the tests; these build the same tables at the same addresses (room headers in bank 4,
name lists, drop tables and sprite descriptors in bank 7), so a change in how a table is read or written shows here.
What the tables mean was proven by replaying the real game (research/wonderboy3-level-profile.md).
"""
import unittest

from romancer.level_profiles import Watcher
from romancer.level_profiles import wonderboy3 as wb

RAM = 0xC000
P = wb.WonderBoy3Profile


def b4(address):
    return 0x10000 + address - 0x8000


def b7(address):
    return 0x1C000 + address - 0x8000


def apply(rom, writes):
    out = bytearray(rom)
    for offset, old, new in writes:
        assert out[offset] == old, (hex(offset), old, out[offset])
        out[offset] = new
    return bytes(out)


def cart():
    """256 KB. Room 0: two green cobras ($37), a blue cobra ($38), a room effect ($8A), a rock ($40); a shop door. Room 1:
    two red knights ($01). Every other room points at the empty list $AD90 and an empty zone list."""
    rom = bytearray(0x40000)

    def put(offset, data):
        rom[offset:offset + len(data)] = bytes(data)

    def w(v):
        return [v & 0xFF, v >> 8]
    put(b4(0xAD90), [0xFF])
    put(b4(0x8CAA), [0xFF])
    for room in range(P.ROOMS):
        put(b4(0x8000 + 18 * room), w(0x8CAA) + w(0xA1B0) + w(0xAD90) + [room & 0x7F])
    # room 0: zones (an exit, then a shop door type 2 to the list $A168), objects
    put(b4(0x8000), w(0x8C9C) + w(0xA1B0) + w(0xAD91) + [0x00])
    put(b4(0x8C9C), [0x7E, 0xC0, 0x02, 0x50, 0x00] + w(0x8C90) + [0x10, 0xC0, 0x02, 0x20, 0x02] + w(0xA168) + [0xFF])
    put(b4(0xA168), [0x02, 0x12, 0x22, 0xFF, 0x03, 0x42, 0xFF, 0xFF])
    put(b4(0xAD91), [0x37, 0x24, 0x80, 0xFF, 0x37, 0x34, 0x80, 0x02, 0x38, 0x7C, 0x60, 0xC2, 0x8A, 0x40, 0x50, 0x90, 0xFF, 0xFF])
    # room 1: two knights with random table 0
    put(b4(0x8012), w(0x8CAA) + w(0xA1B0) + w(0xADA6) + [0x01])
    put(b4(0xADA6), [0x01, 0x14, 0x80, 0x00, 0x01, 0x34, 0x80, 0x00, 0xFF])
    # sprite descriptors (bank 7): word $9D60 + (type - 1) * 2 -> entries [count, source word], $7F one blank tile
    desc = {0x01: [27, 0, 0, 27, 0, 0, 0], 0x14: [20, 0, 0, 0], 0x36: [0x7F, 59, 0, 0, 0], 0x37: [0x7F, 59, 0, 0, 0],
            0x38: [0x7F, 59, 0, 0, 0], 0x40: [12, 0, 0, 0], 0x21: [98, 0, 0, 0]}
    at = 0x9F00
    for kind in range(1, 0x46):
        data = desc.get(kind, [4, 0, 0, 0])
        put(b7(0x9D60 + 2 * (kind - 1)), w(at & 0x3FFF))
        put(b7(at), data)
        at += len(data)
    put(b7(0x9E00 + 2 * (0x0A - 1)), w(at & 0x3FFF))
    put(b7(at), [8, 0, 0, 0])
    # name lists (bank 7): word $8272 + kind * 4 -> one pointer per item -> words split by $FE, ended by $FF
    texts = {0: ['MITHRIL\xfeSWORD', 'IVORY\xfeSWORD', 'MITHRIL\xfeSWORD', 'SHOGUN\xfeBLADE'], 1: ['', '', 'MITHRIL\xfeSHIELD'],
             2: ['', '', 'MITHRIL\xfeARMOR'], 3: ['FIRE BALL', 'TORNADO'], 4: ['STONE', 'KEY', 'MEDICINE']}
    at = 0x8400
    for kind in range(5):
        put(b7(0x8272 + kind * 4), w(0x8300 + kind * 0x20))
        names = texts[kind] + [''] * (10 - len(texts[kind]))
        for n, text in enumerate(names):
            put(b7(0x8300 + kind * 0x20 + 2 * n), w(at))
            data = text.encode('latin-1') + b'\xff'
            put(b7(at), data)
            at += len(data)
    # drop tables (bank 7, $8BB0 + n * 16)
    put(b7(0x8BB0), [0xFF] * 9 + [0x45, 0x30] + [0xFF] * 5)
    put(b7(0x8BC0 + 16), [0x50] * 16)
    return bytes(rom)


def ram_in_room(profile, room, camera=0):
    ram = bytearray(0x2000)
    ram[0xCF5E - RAM:0xCF65 - RAM] = profile.header(room)[:7]
    ram[0xD0A0 - RAM] = len(profile.records(room))
    ram[0xD00F - RAM:0xD011 - RAM] = camera.to_bytes(2, 'little')
    return ram


def slot(ram, k, number, kind, drop):
    s = 0xC3C0 + 64 * k - RAM
    ram[s] = 0xC0
    ram[s + 0x2E] = number
    ram[s + 0x0F] = kind
    ram[s + 0x1A] = drop


class Decoding(unittest.TestCase):
    def setUp(self):
        self.p = P(cart())

    def test_records_and_objects(self):
        recs = self.p.records(0)
        self.assertEqual([r[2] for r in recs], [0x37, 0x37, 0x38, 0x8A, 0x40])
        self.assertEqual(recs[1][1:], (b4(0xAD95), 0x37, 0x34, 0x80, 0x02))
        objs = {o['id']: o for o in self.p.objects({'room': 0})}
        self.assertEqual(objs['object:0']['name'], 'Cobra (green)')
        self.assertEqual((objs['object:0']['x'], objs['object:0']['y']), (0x24 * 8, 0x80 + 16))
        self.assertEqual(objs['object:2']['detail'], 'drops medicine')
        self.assertEqual(objs['object:4']['name'], 'Rock')
        self.assertNotIn('object:3', objs)              # one-byte room effect
        shop = objs[f'shop:{b4(0x8CA3)}']
        self.assertEqual(shop['detail'], 'sells Mithril Sword, Mithril Shield, Mithril Armor')

    def test_tiles_and_swap_budget(self):
        self.assertEqual(self.p.tiles(0x37), 60)
        self.assertEqual(self.p.tiles(0x01), 54)
        self.assertEqual(self.p.tiles(0x8A), 8)
        self.assertEqual(self.p.room_tiles([0x37, 0x37, 0x38, 0x8A, 0x40]), 140)
        names = [c['value'] for c in self.p.enemy_choices(0, 0)]
        self.assertIn(0x38, names)                       # already loaded: 140 tiles
        self.assertIn(0x14, names)                       # 140 + 20 = 160
        self.assertNotIn(0x36, names)                    # 140 + 60 = 200, past the room's 170
        self.assertNotIn(0x21, names)

    def test_where(self):
        ram = ram_in_room(self.p, 1, camera=300)
        self.assertEqual(self.p.where(ram), {'part': {'room': 1}, 'x': 300, 'y': 0})
        ram[0xD0A0 - RAM] = 0
        self.assertIsNone(self.p.where(ram))
        self.assertIsNone(self.p.where(bytearray(0x2000)))

    def test_names(self):
        self.assertEqual(self.p.item_name(0x03), 'Shogun Blade')
        self.assertEqual(self.p.item_name(0x42), 'Medicine')
        self.assertEqual(self.p.item_name(0x55), '20 gold')
        self.assertEqual(self.p.item_name(0x50), '1 gold')
        self.assertEqual(self.p.item_name(0x43), 'Heart in a box')
        self.assertEqual(self.p.item_name(0x45), 'Small heart')
        self.assertEqual(self.p.drop_name(0xFF), 'Nothing')
        self.assertEqual(self.p.drop_name(0x00), 'Random 0: nothing, Small heart, Fire Ball')
        self.assertIn(0xC2, self.p.drops())
        self.assertEqual(self.p.wares(), [0x02, 0x12, 0x22, 0xFF])


class Edits(unittest.TestCase):
    def setUp(self):
        self.rom = cart()
        self.p = P(self.rom)

    def test_swap_and_drop(self):
        plan = self.p.edit({'room': 0}, 'object:1', {'type': 0x38, 'drop': 0xC2})
        self.assertEqual(plan['writes'], [(b4(0xAD95), 0x37, 0x38), (b4(0xAD98), 0x02, 0xC2)])
        changed = P(apply(self.rom, plan['writes']))
        self.assertEqual(changed.records(0)[1][2], 0x38)
        watcher = self.p.watcher(plan['watch'])
        ram = ram_in_room(self.p, 0)
        self.assertFalse(watcher.see(ram, 0, 'changed'))
        slot(ram, 2, 1, 0x38, 0xC2)
        self.assertTrue(watcher.see(ram, 2, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        control = self.p.watcher(plan['watch'])
        ram = ram_in_room(self.p, 0)
        slot(ram, 0, 1, 0x37, 0x02)
        control.see(ram, 0, 'original')
        self.assertEqual(control.result()['state'], 'bad')

    def test_refused_choices(self):
        with self.assertRaises(ValueError):
            self.p.edit({'room': 0}, 'object:0', {'type': 0x36})
        with self.assertRaises(ValueError):
            self.p.edit({'room': 0}, 'object:0', {'drop': 0x77})
        with self.assertRaises(ValueError):
            self.p.edit({'room': 0}, 'object:4', {'type': 0x37})

    def test_remove(self):
        plan = self.p.edit({'room': 0}, 'object:0', {}, remove=True)
        self.assertEqual(plan['writes'], [(b4(0xAD92), 0x24, 0xFF)])
        self.assertNotIn('object:0', {o['id'] for o in P(apply(self.rom, plan['writes'])).objects({'room': 0})})
        good = self.p.watcher(plan['watch'])
        for frame in range(0, 20, 2):
            done = good.see(ram_in_room(self.p, 0, camera=0x40), frame, 'changed')
        self.assertTrue(done)
        self.assertEqual(good.result()['state'], 'good')
        bad = self.p.watcher(plan['watch'])
        ram = ram_in_room(self.p, 0, camera=0x40)
        ram[0xD030 + 6 - RAM] = 0x80
        self.assertTrue(bad.see(ram, 0, 'original'))
        self.assertEqual(bad.result()['state'], 'bad')
        self.assertEqual(Watcher().result()['state'], self.p.watcher(plan['watch']).result()['state'])

    def test_shop(self):
        shop = f'shop:{b4(0x8CA3)}'
        plan = self.p.edit({'room': 0}, shop, {'item0': 0x12, 'item3': 0x22})
        self.assertEqual(plan['writes'], [(b4(0xA168), 0x02, 0x12), (b4(0xA16B), 0xFF, 0x22)])
        with self.assertRaises(ValueError):
            self.p.edit({'room': 0}, shop, {'item0': 0x42})
        watcher = self.p.watcher(plan['watch'])
        ram = bytearray(0x2000)
        ram[0xCFFE - RAM:0xD000 - RAM] = (0xA168).to_bytes(2, 'little')
        self.assertFalse(watcher.see(ram, 0, 'changed'))
        ram[0xD10E - RAM:0xD112 - RAM] = bytes([0x12, 0x12, 0x22, 0x22])
        self.assertTrue(watcher.see(ram, 1, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        control = self.p.watcher(plan['watch'])
        ram[0xD10E - RAM:0xD112 - RAM] = bytes([0x02, 0x12, 0x22, 0xFF])
        control.see(ram, 1, 'original')
        self.assertEqual(control.result()['state'], 'bad')


if __name__ == '__main__':
    unittest.main()
