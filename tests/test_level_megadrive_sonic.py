"""Sonic The Hedgehog and Sonic The Hedgehog 2 object layouts: decoding and edits on made-up cartridges that have the
games' tables at their real addresses (nothing else of the games)."""
import unittest

from romancer.level_profiles.megadrive_sonic import Sonic1, Sonic2, kos_decode, kos_encode


def word(value):
    return bytes([value >> 8 & 0xFF, value & 0xFF])


def record(x, y, ident, sub):
    return word(x) + word(y) + bytes([ident, sub])


def sonic1_rom():
    rom = bytearray(0x80000)
    index = Sonic1.INDEX
    # Green Hill act 1: rings, a monitor, a Moto Bug, a spring, a Crabmeat; act 2: a Buzz Bomber; the rest empty
    first = 0x100
    lists = {(0, 0): record(0x144, 0x360, 0xA5, 0x12) + record(0x248, 0x351, 0xA6, 0x06) + record(0x340, 0x3AC, 0xC0, 0x00)
             + record(0x334, 0x4328, 0x41, 0x02) + record(0x8B0, 0x350, 0x9F, 0x00),
             (0, 1): record(0x420, 0x330, 0xA2, 0x00)}
    empty = first - 6
    rom[index + empty:index + empty + 6] = word(0xFFFF) + bytes(4)
    at = first
    starts = {}
    for key, body in lists.items():
        starts[key] = at
        rom[index + at:index + at + len(body) + 6] = body + word(0xFFFF) + bytes(4)
        at += len(body) + 6
    for zone in range(7):
        for act in range(4):
            entry = index + zone * 16 + act * 4
            rom[entry:entry + 2] = word(starts.get((zone, act), starts[(0, 0)] if act == 3 and zone == 0 else empty))
            rom[entry + 2:entry + 4] = word(empty)
    return bytes(rom)


def sonic2_rom():
    rom = bytearray(0x100000)
    index, rings = Sonic2.INDEX, Sonic2.RING_INDEX
    body = record(0x100, 0x2B0, 0x26, 0x04) + record(0x200, 0x2B0, 0x9D, 0x1E) + record(0x300, 0x82B0, 0x41, 0x00)
    empty = 0x44 + 0x10
    rom[index + empty:index + empty + 2] = word(0xFFFF)
    rom[index + 0x46:index + 0x46 + len(body) + 2] = body + word(0xFFFF)
    for n in range(34):
        rom[index + 2 * n:index + 2 * n + 2] = word(0x46 if n == 0 else empty)
    ring_body = word(0x124) + word(0x2240) + word(0x230) + word(0x91E0) + word(0x400) + word(0x0300)
    rom[rings + 0x44:rings + 0x44 + len(ring_body) + 2] = ring_body + word(0xFFFF)
    rom[rings + 0x60:rings + 0x62] = word(0xFFFF)
    for n in range(34):
        rom[rings + 2 * n:rings + 2 * n + 2] = word(0x44 if n == 0 else 0x60)
    return bytes(rom)


def ram_with(mode=0x0C, zone=0, act=0, camera=(0, 0), objects=(), base=0):
    ram = bytearray(0x10000)
    ram[0xF600] = mode
    ram[0xFE10], ram[0xFE11] = zone, act
    return ram


class Sonic1Tests(unittest.TestCase):
    def setUp(self):
        self.p = Sonic1(sonic1_rom())
        self.part = {'zone': 0, 'act': 0}

    def test_records(self):
        rows = self.p.records(0, 0)
        self.assertEqual([(r['x'], r['y'], r['id'], r['sub']) for r in rows],
                         [(0x144, 0x360, 0x25, 0x12), (0x248, 0x351, 0x26, 6), (0x340, 0x3AC, 0x40, 0), (0x334, 0x328, 0x41, 2), (0x8B0, 0x350, 0x1F, 0)])
        self.assertEqual(rows[3]['flags'], 1)
        self.assertTrue(rows[0]['remember'])
        self.assertFalse(rows[3]['remember'])

    def test_where(self):
        ram = ram_with(zone=0, act=1)
        ram[0xF700:0xF704] = word(0x1234) + word(0)
        ram[0xF704:0xF706] = word(0x300)
        self.assertEqual(self.p.where(ram), {'part': {'zone': 0, 'act': 1}, 'x': 0x1234, 'y': 0x300})
        self.assertIsNone(self.p.where(ram_with(mode=0x08)))       # the attract demo
        self.assertIsNone(self.p.where(ram_with(zone=0, act=3)))   # Green Hill has no fourth act
        self.assertEqual(self.p.part_name({'zone': 1, 'act': 3}), 'Scrap Brain Zone, act 3')
        self.assertEqual(self.p.part_name({'zone': 5, 'act': 2}), 'Final Zone')

    def test_objects(self):
        rows = {o['id']: o for o in self.p.objects(self.part)}
        self.assertEqual(rows['object:0']['name'], 'Rings')
        self.assertEqual(rows['object:0']['detail'], 'a row of 3')
        self.assertEqual(rows['object:1']['detail'], 'holds ten rings')
        self.assertEqual(rows['object:2']['style'], 'enemy')
        self.assertEqual(rows['object:2']['name'], 'Moto Bug')
        self.assertEqual(rows['object:3']['name'], 'Spring')
        self.assertIsNone(rows['object:3']['remove'])
        enemies = self.p.choices()['enemies_0']
        self.assertEqual([c['value'] for c in enemies], [0x4000, 0x1F00, 0x2200])

    def test_edits(self):
        offset = self.p.list_start(0, 0)
        plan = self.p.edit(self.part, 'object:1', {'contents': 5})
        self.assertEqual(plan['writes'], [(offset + 6 + 5, 6, 5)])
        plan = self.p.edit(self.part, 'object:2', {'enemy': 0x1F00})
        self.assertEqual(plan['writes'], [(offset + 12 + 4, 0xC0, 0x9F)])
        plan = self.p.edit(self.part, 'object:2', {}, remove=True)
        self.assertEqual(plan['writes'], [(offset + 12 + 4, 0xC0, 0x80)])     # id 0, the remember bit kept
        plan = self.p.edit(self.part, 'object:0', {'count': 6})
        self.assertEqual(plan['writes'], [(offset + 5, 0x12, 0x16)])
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:2', {'enemy': 0x2C00})            # Jaws: not a Green Hill enemy
        with self.assertRaises(ValueError):
            self.p.edit(self.part, 'object:3', {}, remove=True)              # springs stay

    def test_watchers(self):
        plan = self.p.edit(self.part, 'object:1', {'contents': 5})
        ram = ram_with()
        slot = 0xD800 + 0x40 * 3
        ram[slot] = 0x26
        ram[slot + 8:slot + 10], ram[slot + 0xC:slot + 0xE] = word(0x248), word(0x351)
        ram[slot + 0x28] = 5
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 10, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[slot + 0x28] = 6
        w = self.p.watcher(plan['watch'])
        w.see(ram, 10, 'changed')
        self.assertEqual(w.result()['state'], 'bad')
        # a removal: camera over the place long enough with no Moto Bug there
        plan = self.p.edit(self.part, 'object:2', {}, remove=True)
        ram = ram_with()
        ram[0xF700:0xF702], ram[0xF704:0xF706] = word(0x300), word(0x300)
        w = self.p.watcher(plan['watch'])
        self.assertFalse(any(w.see(ram, f, 'changed') for f in range(10)))
        self.assertEqual(w.result()['state'], 'warn')
        while not w.see(ram, 0, 'changed'):
            pass
        self.assertEqual(w.result()['state'], 'good')
        ram[slot] = 0x40
        ram[slot + 8:slot + 10], ram[slot + 0xC:slot + 0xE] = word(0x350), word(0x3AC)
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'bad')
        # rings: count the ring objects whose parent x is the record's
        plan = self.p.edit(self.part, 'object:0', {'count': 6})
        ram = ram_with()
        for n in range(7):
            s = 0xD800 + 0x40 * n
            ram[s] = 0x25
            ram[s + 0x32:s + 0x34], ram[s + 0xC:s + 0xE] = word(0x144), word(0x360)
            ram[s + 0x34] = n
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')


class Sonic2Tests(unittest.TestCase):
    def setUp(self):
        self.p = Sonic2(sonic2_rom())
        self.part = {'zone': 0, 'act': 0}

    def test_records(self):
        rows = self.p.records(0, 0)
        self.assertEqual([(r['x'], r['y'], r['id'], r['sub'], r['remember']) for r in rows],
                         [(0x100, 0x2B0, 0x26, 4, False), (0x200, 0x2B0, 0x9D, 0x1E, False), (0x300, 0x2B0, 0x41, 0, True)])
        self.assertEqual(self.p.ring_groups(0, 0)[1], {'n': 1, 'offset': Sonic2.RING_INDEX + 0x48, 'x': 0x230, 'y': 0x1E0, 'count': 2, 'vertical': True})

    def test_where(self):
        ram = ram_with(zone=0, act=1)
        ram[0xEE00:0xEE02], ram[0xEE04:0xEE06] = word(0x500), word(0x280)
        self.assertEqual(self.p.where(ram), {'part': {'zone': 0, 'act': 1}, 'x': 0x500, 'y': 0x280})
        self.assertIsNone(self.p.where(ram_with(zone=1)))

    def test_edits(self):
        offset = self.p.list_start(0, 0)
        self.assertEqual(self.p.edit(self.part, 'object:0', {'contents': 6})['writes'], [(offset + 5, 4, 6)])
        self.assertEqual(self.p.edit(self.part, 'object:1', {}, remove=True)['writes'], [(offset + 6 + 4, 0x9D, 0)])
        rings = Sonic2.RING_INDEX + 0x44
        plan = self.p.edit(self.part, 'rings:0', {'count': 4})
        self.assertEqual(plan['writes'], [(rings + 2, 0x22, 0x42)])
        plan = self.p.edit(self.part, 'rings:1', {'count': 0})
        self.assertEqual(plan['writes'], [(rings + 6, 0x91, 0x81)])
        plan = self.p.edit(self.part, 'rings:0', {}, remove=True)
        # the list closes up over the removed group and ends one record sooner
        after = bytearray(self.p.rom)
        for at, old, new in plan['writes']:
            self.assertEqual(after[at], old)
            after[at] = new
        self.assertEqual(bytes(after[rings:rings + 10]), word(0x230) + word(0x91E0) + word(0x400) + word(0x0300) + word(0xFFFF))

    def test_ring_watcher(self):
        plan = self.p.edit(self.part, 'rings:0', {'count': 4})
        ram = ram_with()
        table = Sonic2.RING_TABLE
        for n in range(5):
            at = table + 6 * n
            ram[at + 2:at + 4], ram[at + 4:at + 6] = word(0x124 + 0x18 * n), word(0x240)
        w = self.p.watcher(plan['watch'])
        self.assertTrue(w.see(ram, 0, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[table + 6 * 4 + 2:table + 6 * 4 + 6] = bytes(4)
        w = self.p.watcher(plan['watch'])
        w.see(ram, 0, 'changed')
        self.assertEqual(w.result()['state'], 'bad')


def with_s1_layouts(rom):
    """Green Hill act 1: 4 by 2 chunks; act 2: 3 by 1 with chunk 7 and a loop chunk $85; every other act a 1 by 1."""
    rom = bytearray(rom)
    index = Sonic1.LAYOUT_INDEX
    bodies = {(0, 0): bytes([3, 1, 0, 1, 2, 0, 3, 4, 0, 5]), (0, 1): bytes([2, 0, 7, 0x85, 0])}
    plain = 0x100
    rom[index + plain:index + plain + 3] = bytes([0, 0, 0])
    at, starts = 0xA8, {}
    for key, body in bodies.items():
        starts[key] = at
        rom[index + at:index + at + len(body)] = body
        at += len(body)
    for zone in range(7):
        for act in range(4):
            entry = index + (zone * 4 + act) * 6
            rom[entry:entry + 6] = word(starts.get((zone, act), plain)) + word(plain) + word(plain)
    return bytes(rom)


def s2_layout(fill):
    data = bytearray(0x1000)
    for (column, row), block in fill.items():
        data[row * 0x100 + column] = block
    return bytes(data)


def with_s2_layouts(rom, first, second):
    """Emerald Hill act 1 at the index + $44, act 2 (and every other act) right after it, 16-byte aligned."""
    rom = bytearray(rom)
    index = Sonic2.LAYOUT_INDEX
    one, two = kos_encode(first), kos_encode(second)
    at2 = (0x44 + len(one) + 15) // 16 * 16 + 4
    rom[index + 0x44:index + 0x44 + len(one)] = one
    rom[index + at2:index + at2 + len(two)] = two
    for n in range(34):
        rom[index + 2 * n:index + 2 * n + 2] = word(0x44 if n == 0 else at2)
    return bytes(rom), at2


class KosinskiTests(unittest.TestCase):
    def test_small_stream(self):
        # one literal, then the end: descriptor bits 1, 0, 1 (low bit first), the byte, the end's $00 $F0 $00
        self.assertEqual(kos_encode(b'A'), bytes([0x05, 0x00, 0x41, 0x00, 0xF0, 0x00]))
        self.assertEqual(kos_decode(bytes([0x05, 0x00, 0x41, 0x00, 0xF0, 0x00])), (b'A', 6))

    def test_round_trip(self):
        import random
        rng = random.Random(4)
        samples = [bytes(0x1000), bytes(rng.randrange(256) for _ in range(700)),
                   bytes(rng.choice((0, 0, 0, 1, 2, 0x93, 0xA2)) for _ in range(0x1000)),
                   bytes(range(256)) * 20 + b'\x07' * 300]
        for data in samples:
            for chain in (1, 48, 320):
                packed = kos_encode(data, chain)
                self.assertEqual(kos_decode(packed + b'\xEE' * 4), (data, len(packed)))


class Sonic1LayoutTests(unittest.TestCase):
    def setUp(self):
        self.p = Sonic1(with_s1_layouts(sonic1_rom()))
        self.part = {'zone': 0, 'act': 0}

    def test_layout(self):
        self.assertEqual(self.p.packed_layout(self.part), {'size': 256, 'width': 4, 'height': 2, 'blocks': [0, 1, 2, 0, 3, 4, 0, 5],
                                                           'left': 0, 'top': 0})
        self.assertEqual(self.p.packed_layout({'zone': 0, 'act': 1})['blocks'], [7, 0x85, 0])
        self.assertIsNone(self.p.packed_layout({'zone': 0, 'act': 3}))
        self.assertEqual(self.p.zone_chunks(0), {0, 1, 2, 3, 4, 5, 7, 0x85})

    def test_set_layout(self):
        start = Sonic1.LAYOUT_INDEX + 0xA8 + 2
        plan = self.p.set_packed_layout(self.part, [(0, 0, 0x85), (3, 1, 2), (1, 0, 1)])   # the last is already there
        self.assertEqual(plan['writes'], [(start, 0, 0x85), (start + 7, 5, 2)])
        self.assertEqual(plan['title'], 'Layout: 2 chunks changed (Green Hill Zone, act 1)')
        self.assertEqual(plan['watch']['places'], [[0, 0, 0x85, 0], [3, 1, 2, 5]])
        with self.assertRaises(ValueError):
            self.p.set_packed_layout(self.part, [(0, 0, 9)])         # not a Green Hill chunk
        with self.assertRaises(ValueError):
            self.p.set_packed_layout(self.part, [(4, 0, 1)])         # outside the layout
        with self.assertRaises(ValueError):
            self.p.set_packed_layout(self.part, [(1, 0, 1)])         # nothing changes

    def test_watcher(self):
        plan = self.p.set_packed_layout(self.part, [(0, 0, 0x85), (3, 1, 2)])
        ram = ram_with()
        ram[0xA400], ram[0xA400 + 0x80 + 3] = 0x85, 2
        w = self.p.watcher(plan['watch'])
        self.assertFalse(w.see(ram, 0, 'changed'))                   # two looks must agree
        self.assertTrue(w.see(ram, 4, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[0xA400 + 0x80 + 3] = 5                                   # the unchanged game
        w = self.p.watcher(plan['watch'])
        w.see(ram, 0, 'original'), w.see(ram, 4, 'original')
        self.assertEqual(w.result()['state'], 'bad')
        w = self.p.watcher(plan['watch'])
        self.assertFalse(w.see(ram_with(zone=0, act=1), 0, 'changed') or w.see(ram_with(zone=0, act=1), 4, 'changed'))
        self.assertEqual(w.result()['state'], 'warn')


class Sonic2LayoutTests(unittest.TestCase):
    def setUp(self):
        self.first = s2_layout({(0, 5): 0x02, (1, 5): 0x02, (2, 5): 0x0F, (3, 4): 0x93})
        self.second = s2_layout({**{(n, 6): 1 + n % 200 for n in range(0x80)}, **{(n, 7): 1 + (n * 7) % 200 for n in range(0x80)}})
        rom, self.at2 = with_s2_layouts(sonic2_rom(), self.first, self.second)
        self.p = Sonic2(rom)
        self.part = {'zone': 0, 'act': 0}

    def test_layout(self):
        grid = self.p.packed_layout(self.part)
        self.assertEqual((grid['size'], grid['width'], grid['height']), (128, 128, 16))
        self.assertEqual(grid['blocks'][5 * 128:5 * 128 + 4], [2, 2, 0x0F, 0])
        self.assertEqual(grid['blocks'][4 * 128 + 3], 0x93)
        self.assertEqual(self.p.layout_room(self.p.layout_start(0, 0)), self.at2 - 0x44)

    def test_set_layout(self):
        plan = self.p.set_packed_layout(self.part, [(3, 5, 0x02), (10, 4, 0x93)])
        after = bytearray(self.p.rom)
        for at, old, new in plan['writes']:
            self.assertEqual(after[at], old)
            self.assertTrue(Sonic2.LAYOUT_INDEX + 0x44 <= at < Sonic2.LAYOUT_INDEX + self.at2)     # within its own room
            after[at] = new
        data, _ = kos_decode(after, Sonic2.LAYOUT_INDEX + 0x44)
        want = bytearray(self.first)
        want[5 * 0x100 + 3], want[4 * 0x100 + 10] = 0x02, 0x93
        self.assertEqual(data, bytes(want))
        self.assertEqual(kos_decode(after, Sonic2.LAYOUT_INDEX + self.at2)[0], self.second)        # the next one untouched
        self.assertEqual(plan['watch']['places'], [[3, 5, 2, 0], [10, 4, 0x93, 0]])
        self.assertEqual(plan['watch']['ram'], 0x8000)

    def test_refused_when_too_big(self):
        import random
        rng = random.Random(9)
        chunks = sorted(self.p.zone_chunks(0) - {0})
        changes = [(n % 0x80, 8 + n // 0x80, rng.choice(chunks)) for n in range(0x60)]
        with self.assertRaises(ValueError) as caught:
            self.p.set_packed_layout(self.part, changes)
        self.assertIn('fit where it was', str(caught.exception))

    def test_watcher(self):
        plan = self.p.set_packed_layout(self.part, [(3, 5, 0x02)])
        ram = ram_with()
        ram[0x8000 + 5 * 0x100 + 3] = 0x02
        w = self.p.watcher(plan['watch'])
        w.see(ram, 0, 'changed')
        self.assertTrue(w.see(ram, 4, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        ram[0x8000 + 5 * 0x100 + 3] = 0
        w = self.p.watcher(plan['watch'])
        w.see(ram, 0, 'original'), w.see(ram, 4, 'original')
        self.assertEqual(w.result()['state'], 'bad')


if __name__ == '__main__':
    unittest.main()
