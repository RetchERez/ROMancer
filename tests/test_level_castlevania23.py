"""Castlevania III and Castlevania II level profiles: decoders, edits and watchers on made-up cartridges laid out like
the real ones (tables at the real addresses, nothing else of the games). What the tables mean was proven by replaying
the real games (research/castlevania23-level-profile.md)."""
import unittest

from romancer.level_profiles import castlevania23 as cv

H = cv.HEADER_NES


class Cart3:
    """256 KB of PRG laid out like Castlevania III: spawn code bank 0x28000 at $8000, $C000 bank 0x3C000, $E000 bank
    0x3E000, level bank 0x20000 at $8000, ROM bank 0 for the status bar."""

    def __init__(self):
        self.rom = bytearray(H + 0x40000)

    def put(self, address, data):           # spawn view of the CPU
        if address < 0xC000:
            offset = H + 0x28000 + address - 0x8000
        elif address < 0xE000:
            offset = H + 0x3C000 + address - 0xC000
        else:
            offset = H + 0x3E000 + address - 0xE000
        self.rom[offset:offset + len(data)] = bytes(data)

    def level(self, address, data):
        self.rom[H + 0x20000 + address - 0x8000:H + 0x20000 + address - 0x8000 + len(data)] = bytes(data)

    def bank0(self, address, data):
        self.rom[H + address - 0x8000:H + address - 0x8000 + len(data)] = bytes(data)

    def obj(self, address, data):           # stage object bank 0x8000 at $8000
        self.rom[H + 0x8000 + address - 0x8000:H + 0x8000 + address - 0x8000 + len(data)] = bytes(data)

    @staticmethod
    def w(value):
        return [value & 0xFF, value >> 8]


def build3():
    c = Cart3()
    for block in range(15):
        c.put(0x937F + 2 * block, Cart3.w(0x93A0))          # every block shares one list: two sub-blocks
        c.put(0xC94B + block, [0x90])                        # layout bank 0x20000
        c.put(0xD5D4 + 2 * block, Cart3.w(0x8000))
        c.put(0xD62E + 2 * block, Cart3.w(0xD700))
        c.bank0(0x8DCF + 2 * block, Cart3.w(0x8E00))
    c.put(0x93A0, Cart3.w(0x93A4) + Cart3.w(0x93A8))
    c.put(0x93A4, Cart3.w(0x9500) + Cart3.w(0x9600))         # sub 0: a sideways room and an up-and-down room
    c.put(0x93A8, Cart3.w(0x9700))
    c.level(0x8000, Cart3.w(0x8010) + Cart3.w(0x8020))
    c.level(0x8010, [1] + Cart3.w(0x8100) + Cart3.w(0x8200))
    c.level(0x8020, [0] + Cart3.w(0x8300))
    c.level(0x8100, [2]); c.level(0x8200, [1]); c.level(0x8300, [0])
    c.put(0xD700, Cart3.w(0xD710) + Cart3.w(0xD712))
    c.put(0xD710, [0x00, 0x80]); c.put(0xD712, [0x00])
    c.bank0(0x8E00, [0x42, 0x42, 0x43])                      # "1", then sub-blocks "1", "2"
    # pools
    c.put(0xA03F, Cart3.w(0xB0F0)); c.put(0xB0F0, [0])     # record 0: no enemy
    c.put(0xA03F + 2, Cart3.w(0xB000)); c.put(0xB000, [0x32, 0x10, 0xB0, 0, 0])
    c.put(0xA03F + 4, Cart3.w(0xB008)); c.put(0xB008, [0x05, 0x00, 0xA8, 0, 0])
    c.put(0xA13F + ((0xD1 << 1) & 0xFF), Cart3.w(0xB010)); c.put(0xB010, [0x01, 0, 0xC0, 0, 0])
    c.put(0xA644 + 2, Cart3.w(0xB100)); c.put(0xB100, [0x90, 0xAE, 0x20, 0x98])
    c.put(0xA644 + 4, Cart3.w(0xB110)); c.put(0xB110, [0x91, 0xAD, 0x08, 0xC0])
    c.put(0xA644 + 6, Cart3.w(0xB120)); c.put(0xB120, [0x91, 0xA4, 0x08, 0xC0])
    zones = [(0, 0)] * 14
    zones[1] = (1, 0)
    zones[2] = (0, 1)
    zones[4] = (0, 2)
    zones[5] = (0xD1, 0)
    zones[9] = (0, 2)
    c.put(0x9500, [b for z in zones for b in z])
    c.put(0x9600, [1, 0x20, 0x90, 0x40, 0xA2, 0, 0, 1, 0x50, 0x32, 0x80, 0, 1, 2, 0xFF])
    c.put(0x9700, [0] * 6)
    # stage objects: room 1 of sub-block 0 and the room of sub-block 1 share list 1, the up-and-down room has list 2
    for block in range(15):
        c.obj(0xA073 + 2 * block, Cart3.w(0xA100))
    c.obj(0xA100, Cart3.w(0xA110) + Cart3.w(0xA112))
    c.obj(0xA110, [1, 2]); c.obj(0xA112, [1])
    c.obj(0xA199 + 2, Cart3.w(0xA200)); c.obj(0xA199 + 4, Cart3.w(0xA240))
    c.obj(0xA200, [0x00, 0x50, 0x00, 0x02, 0x64, 1, 0, 0,        # a platform (not a block)
                   0x01, 0x18, 0x00, 0x10, 0xB0, 0, 1, 0, 0xFF])  # block at 256 + 24, y $B0, two high, pot roast
    c.obj(0xA240, [0x01, 0x20, 0x00, 0x11, 0x40, 4, 0, 1, 0xFF])  # up and down: x $40, page 1 y $20, extra life
    return c


ROOM = {'block': 0, 'sub': 0, 'room': 0}
UP = {'block': 0, 'sub': 0, 'room': 1}


class Castlevania3Tests(unittest.TestCase):
    def setUp(self):
        self.c = build3()
        self.p = cv.Castlevania3Profile(bytes(self.c.rom))

    def test_structure(self):
        p = self.p
        self.assertEqual(p.subs(0), 2)
        self.assertEqual([p.rooms(0, 0), p.rooms(0, 1)], [2, 1])
        self.assertEqual([p.pages(0, 0, 0), p.pages(0, 0, 1), p.pages(0, 1, 0)], [2, 1, 0])
        self.assertEqual([p.vertical(0, 0, 0), p.vertical(0, 0, 1)], [False, True])
        self.assertEqual(p.zone_count(0, 0, 0), 14)
        self.assertEqual(p.part_name(ROOM), 'Block 1-01, room 1')
        self.assertEqual(p.part_name({'block': 0, 'sub': 1, 'room': 0}), 'Block 1-02')

    def test_where(self):
        ram = bytearray(0x800)
        ram[0x56], ram[0x57] = 0x30, 1
        self.assertEqual(self.p.where(bytes(ram)), {'part': ROOM, 'x': 0x130, 'y': 0})
        ram[0x34] = 1
        self.assertEqual(self.p.where(bytes(ram))['y'], 240 + 0x30)

    def test_objects(self):
        objs = {o['id']: o for o in self.p.objects(ROOM)}
        self.assertEqual(set(objs), {'enemy:1', 'candle:2', 'candle:4', 'enemy:5', 'candle:9', 'block:1'})
        self.assertEqual((objs['enemy:1']['x'], objs['enemy:1']['y'], objs['enemy:1']['name']), (64 - 64 + 0x10, 0xB0, 'Bone-throwing skeleton'))
        self.assertEqual((objs['candle:2']['x'], objs['candle:2']['y']), (2 * 64 - 64 + 0x20, 0x98))
        self.assertEqual(objs['candle:2']['fields'][0]['key'], 'drop')            # used once: its own item byte
        self.assertEqual(objs['candle:4']['fields'][0]['key'], 'record')          # shared: point at another record
        self.assertEqual([c['value'] for c in objs['candle:4']['fields'][0]['choices']], [2, 3])
        self.assertIn('harder mode', objs['enemy:5']['note'])
        self.assertEqual(objs['enemy:5']['name'], 'Zombies')
        up = {o['id']: o for o in self.p.objects(UP)}
        self.assertEqual((up['vcandle:0']['x'], up['vcandle:0']['y']), (0x40, 240 + 0x20 + 0x37))
        self.assertEqual(up['venemy:1']['name'], 'Bone-throwing skeleton')

    def test_edits(self):
        p, t = self.p, 0x28000 + 0x9500 - 0x8000 + H
        plan = p.edit(ROOM, 'enemy:1', {'record': 2})
        self.assertEqual(plan['writes'], [(t + 2, 1, 2)])
        self.assertEqual(p.edit(ROOM, 'enemy:1', {}, True)['writes'], [(t + 2, 1, 0)])
        plan = p.edit(ROOM, 'candle:2', {'drop': 0xAD})
        self.assertEqual(plan['writes'], [(H + 0x28000 + 0xB101 - 0x8000, 0xAE, 0xAD)])
        self.assertEqual(p.edit(ROOM, 'candle:4', {'record': 3})['writes'], [(t + 9, 2, 3)])
        self.assertEqual(p.edit(ROOM, 'candle:4', {}, True)['writes'], [(t + 9, 2, 0)])
        with self.assertRaises(ValueError):
            p.edit(ROOM, 'candle:4', {'drop': 0xAD})
        v = H + 0x28000 + 0x9600 - 0x8000
        self.assertEqual(p.edit(UP, 'vcandle:0', {'drop': 0xAD})['writes'], [(v + 4, 0xA2, 0xAD)])
        self.assertEqual(p.edit(UP, 'vcandle:0', {}, True)['writes'], [(v + 2, 0x90, 0)])
        self.assertEqual(p.edit(UP, 'venemy:1', {}, True)['writes'], [(v + 7 + 2, 0x32, 0)])

    def test_watchers(self):
        p = self.p
        ram = bytearray(0x800)
        plan = p.edit(ROOM, 'enemy:1', {'record': 2})
        watcher = p.watcher(plan['watch'])
        ram[0x7C2 + 1] = 0x05
        self.assertFalse(watcher.see(bytes(ram), 0, 'changed'))      # first look in the zone's window is skipped
        self.assertTrue(watcher.see(bytes(ram), 4, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        plan = p.edit(ROOM, 'candle:2', {}, True)
        watcher = p.watcher(plan['watch'])
        ram[0x54E + 0x0D + 2], ram[0x645 + 0x0D + 2] = 0x90, 2
        watcher.see(bytes(ram), 0, 'changed')
        self.assertTrue(watcher.see(bytes(ram), 4, 'changed'))
        self.assertEqual(watcher.result()['state'], 'bad')
        self.assertEqual(p.watcher({'kind': 'candle', 'zone': 9, 'record': None, 'part': [0, 0, 0], 'name': ''}).result()['state'], 'warn')


class Castlevania3NameTests(unittest.TestCase):
    def setUp(self):
        self.p = cv.Castlevania3Profile(bytes(build3().rom))

    def test_names_and_does(self):
        for kind, (name, does) in cv.Castlevania3.ENEMIES.items():
            self.assertNotIn('0x', name)
            self.assertTrue(does.endswith('.'), kind)
        objs = {o['id']: o for o in self.p.objects(ROOM)}
        self.assertEqual(objs['enemy:1']['does'], 'Throws bones at you in an arc.')
        self.assertEqual(objs['enemy:5']['does'], 'Zombies rise and walk toward you along the floor.')
        self.assertEqual(self.p.enemy_name(0x29), 'Spider')
        self.assertEqual(self.p.enemy_name(0x50), 'Enemy 0x50')          # never seen, so it keeps its number

    def test_choice_names(self):
        names = {c['value']: c['name'] for c in self.p.choices()['enemies']}
        self.assertEqual(names, {1: 'Bone-throwing skeleton', 2: 'Sword skeleton'})
        self.assertEqual(self.p._vertical_enemy_choices(), [{'value': '50:1:2', 'name': 'Bone-throwing skeleton'}])


class Castlevania3BlockTests(unittest.TestCase):
    def setUp(self):
        self.p = cv.Castlevania3Profile(bytes(build3().rom))

    def test_blocks(self):
        block = {o['id']: o for o in self.p.objects(ROOM)}['block:1']
        self.assertEqual((block['style'], block['x'], block['y']), ('block', 256 + 0x18, 0xB0 + 8))
        self.assertEqual(block['detail'], 'pot roast inside')
        self.assertIn('Two blocks high', block['note'])
        self.assertIn('Block 1-02', block['note'])                      # the other room that uses list 1
        up = {o['id']: o for o in self.p.objects(UP)}['block:0']
        self.assertEqual((up['x'], up['y'], up['detail']), (0x40, 240 + 0x20 + 0x37, 'extra life inside'))
        self.assertEqual([c['value'] for c in self.p.choices()['block_items']], [0, 1, 2, 3, 4, 5])

    def test_block_edit_and_watcher(self):
        p = self.p
        plan = p.edit(ROOM, 'block:1', {'item': 4})
        self.assertEqual(plan['writes'], [(H + 0x8000 + 0xA200 - 0x8000 + 8 + 5, 0, 4)])
        self.assertEqual(p.edit(UP, 'block:0', {'item': 0})['writes'], [(H + 0x8000 + 0xA240 - 0x8000 + 5, 4, 0)])
        with self.assertRaises(ValueError):
            p.edit(ROOM, 'block:1', {'item': 6})
        ram = bytearray(0x800)
        watcher = p.watcher(plan['watch'])
        self.assertFalse(watcher.see(bytes(ram), 0, 'changed'))
        self.assertEqual(watcher.result()['state'], 'warn')
        ram[0x470 + 0x1A], ram[0x41C + 0x1A], ram[0x78B + 0x1A] = 2, 0xB0, 4
        self.assertTrue(watcher.see(bytes(ram), 2, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        control = p.watcher(plan['watch'])
        ram[0x78B + 0x1A] = 0
        control.see(bytes(ram), 2, 'original')
        self.assertEqual(control.result()['state'], 'bad')

    def test_tile_roles(self):
        p = self.p
        self.assertIsNone(p.tile_role(0))                               # no rule seen yet
        ram = bytearray(0x800)
        ram[0x770:0x780] = bytes([0x7E] * 6 + [0x80] * 2 + [0xB7] * 6 + [0xC0] * 2)
        p.where(bytes(ram))
        self.assertEqual([p.tile_role(t) for t in (0x10, 0x7E, 0xB0, 0xB8, 0xDC, 0xE4, 0xC5)],
                         ['open', 'solid', 'open', 'solid', 'solid', 'open', None])
        ram[0x770] = 0x70                                               # another part with another rule
        p.where(bytes(ram))
        self.assertIsNone(p.tile_role(0))


class Cart2:
    """128 KB of PRG laid out like Castlevania II: object bank 0x4000 at $8000, text bank 0xC000, fixed 0x1C000."""

    def __init__(self):
        self.rom = bytearray(H + 0x20000)

    def put(self, address, data):
        offset = H + 0x4000 + address - 0x8000
        self.rom[offset:offset + len(data)] = bytes(data)

    def text(self, address, data):
        offset = H + 0xC000 + address - 0x8000
        self.rom[offset:offset + len(data)] = bytes(data)


def letters(s):
    return [0 if ch == ' ' else 0xFE if ch == '/' else 0x1B if ch == '.' else 0x5D if ch == '?' else ord(ch) - 64 for ch in s] + [0xFF]


def build2():
    c = Cart2()
    for kind in range(6):
        c.put(0x8192 + 2 * kind, Cart3.w(0x8200))
    c.put(0x8200, Cart3.w(0x8210))
    c.put(0x8210, Cart3.w(0x8300))
    c.put(0x8300, [4, 0xC, 0xB5, 0x38, 0xC, 0xC, 0x17, 1, 0x34, 0x12, 0xAE, 7, 0x20, 0x10, 0x03, 2, 0xFF])
    c.put(0x8871, [0x30, 0, 0, 0, 0, 0, 0, 0x32])
    for number, address, words in ((0x38, 0x9000, 'FIRST THING/TO DO.'), (0x30, 0x9040, 'BUY SOME OF/MY LAURELS?'),
                                    (0x32, 0x9080, 'BUY A WHITE/CRYSTAL?')):
        c.text(0x8B82 + 2 * number, Cart3.w(address))
        c.text(address, letters(words))
    return c


TOWN = {'kind': 0, 'area': 0, 'room': 0}


class Castlevania2Tests(unittest.TestCase):
    def setUp(self):
        self.c = build2()
        self.p = cv.Castlevania2Profile(bytes(self.c.rom))

    def test_records_and_text(self):
        objs = {o['id']: o for o in self.p.objects(TOWN)}
        self.assertEqual((objs['obj:0']['x'], objs['obj:0']['y']), (4 * 16 + 8, 0xC * 16))
        self.assertEqual(objs['obj:0']['detail'], 'FIRST THING TO DO.')
        self.assertEqual(objs['obj:2']['name'], 'Merchant')
        self.assertEqual(objs['obj:2']['detail'], 'BUY A WHITE CRYSTAL?')
        self.assertEqual(objs['obj:1']['name'], 'Zombie')
        self.assertEqual(objs['obj:1']['style'], 'enemy')
        self.assertEqual(self.p.part_name(TOWN), 'Town 1, room 1')
        ram = bytearray(0x800)
        ram[0x53], ram[0x54], ram[0x8C] = 0x10, 1, 0x2E
        self.assertEqual(self.p.where(bytes(ram)), {'part': TOWN, 'x': 0x110, 'y': 0x2E})

    def test_edits(self):
        p, base = self.p, H + 0x4000 + 0x8300 - 0x8000
        choices = p.choices()
        self.assertEqual([c['value'] for c in choices['wares']], [7])
        self.assertEqual([c['value'] for c in choices['enemies']], [0x03, 0x17])
        self.assertEqual(p.edit(TOWN, 'obj:1', {}, True)['writes'], [(base + 4 + 2, 0x17, 0)])
        self.assertEqual(p.edit(TOWN, 'obj:1', {'type': 3})['writes'], [(base + 4 + 2, 0x17, 3)])
        with self.assertRaises(ValueError):
            p.edit(TOWN, 'obj:0', {'setting': 0x30})          # no talker in the game says that one
        with self.assertRaises(ValueError):
            p.edit(TOWN, 'obj:1', {'type': 0x55})

    def test_names(self):
        objs = {o['id']: o for o in self.p.objects(TOWN)}
        self.assertEqual(objs['obj:1']['does'], 'Walks toward you through town at night.')
        self.assertEqual(objs['obj:3']['name'], 'Skeleton')
        self.assertEqual({c['value']: c['name'] for c in self.p.choices()['enemies']}, {0x03: 'Skeleton', 0x17: 'Zombie'})

    def test_watcher(self):
        p = self.p
        plan = p.edit(TOWN, 'obj:1', {'type': 3})
        watcher = p.watcher(plan['watch'])
        ram = bytearray(0x800)
        ram[0x82] = 1
        ram[0x432 + 7], ram[0x3B4 + 7] = 2, 3
        self.assertTrue(watcher.see(bytes(ram), 0, 'changed'))
        self.assertEqual(watcher.result()['state'], 'good')
        removal = p.watcher(p.edit(TOWN, 'obj:1', {}, True)['watch'])
        ram = bytearray(0x800)                                 # daylight: the town places no enemies
        ram[0x8C] = 0x00
        removal.see(bytes(ram), 0, 'changed')
        self.assertEqual(removal.result()['state'], 'warn')
        ram[0x82] = 1
        removal.see(bytes(ram), 4, 'changed')
        self.assertEqual(removal.result()['state'], 'good')


if __name__ == '__main__':
    unittest.main()
