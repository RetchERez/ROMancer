"""Adventure Island level profile: a made-up cartridge with the game's tables at their real addresses."""
import unittest

from romancer.level_profiles import adventure_island as ai


def o(address):
    return 16 + address - 0x8000


def cartridge(lists=None):
    rom = bytearray(16 + 0x8000)
    rom[0:4] = b'NES\x1a'

    def put(address, data):
        rom[o(address):o(address) + len(data)] = bytes(data)

    def word(address, value):
        put(address, [value & 0xFF, value >> 8])
    # level 0 uses map 0: layout of flat chunks, chunk 1 rises 32 pixels; start byte 9 -> ground $A8
    put(0xD94B, [0] * 32)
    word(0xD99C, 0xE000)
    word(0xD9B4, 0xE200)
    put(0xE200, [0x09])
    put(0xD96C, [0x00])
    chunks = [[0, 0, 0]] * 66
    chunks[1] = [0, 1 << 2, 0]          # height change -32
    chunks[2] = [0, 0, 2]               # a slope up
    put(0xE000, sum(chunks, []))
    # type records: 6 bytes, byte 3 the y offset
    for kind in range(0x44):
        put(0x901E + kind * 6, [1, 0, 0xF8, 0xF8, 6, 6])
    put(0xAD69, [0b00011011] + [0] * 31)  # egg spots: stretch 0 skateboard, 1 milk, 2 flower, 3 Honey Girl
    lists = lists or [[{'pos': 640, 'type': 0x1C}, {'pos': 864, 'type': 0x0E}, {'pos': 880, 'type': 0x02}],
                      [{'pos': 328, 'type': 0x11}, {'pos': 1200, 'type': 0x10}],
                      [{'pos': 7000, 'type': 0x39, 'p1': 0x40}]]
    address = 0xF300
    for number, entries in enumerate(lists):
        data = ai.encode([dict({'p1': None, 'p2': None}, **e) for e in entries])
        word(0xF118 + number * 2, address)
        put(address, data)
        address += len(data)
    return bytes(rom)


class DecodeTest(unittest.TestCase):
    def test_round_trip(self):
        entries = [{'pos': 8, 'type': 1, 'p1': None, 'p2': None}, {'pos': 8, 'type': 0x3B, 'p1': 0xF8, 'p2': None},
                   {'pos': 600, 'type': 0x3F, 'p1': 0x12, 'p2': 0x18}, {'pos': 6000, 'type': 0x10, 'p1': None, 'p2': None}]
        rom = bytearray(16 + 0x8000)
        data = ai.encode(entries)
        rom[o(0x9000):o(0x9000) + len(data)] = data
        got, end = ai.decode(bytes(rom), 0x9000)
        self.assertEqual(got, entries)
        self.assertEqual(end, 0x9000 + len(data))

    def test_step_and_jump(self):
        # a step under 512 pixels is 7 bits, a longer one 11
        short = ai.encode([{'pos': 8, 'type': 1}, {'pos': 16, 'type': 1}])
        long = ai.encode([{'pos': 8, 'type': 1}, {'pos': 1000, 'type': 1}])
        self.assertEqual(len(short), 5)        # 10 + 6 + 7 + 6 + 11 bits
        self.assertEqual(len(long), 6)         # 10 + 6 + 11 + 6 + 11 bits


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.p = ai.AdventureIslandProfile(cartridge())

    def test_heights_and_ground(self):
        self.assertEqual(self.p.heights(0)[:3], [0xA8, 0x88, 0x88])
        self.assertEqual(self.p.ground(0, 256 + 64), (0x88 - 16, False))

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'level': 0})}
        egg = objects['list0:0']
        self.assertEqual((egg['x'], egg['y'], egg['name']), (640, 0x88 - 8 + 8, 'Egg'))
        self.assertIn('stone axe', egg['detail'])
        snail = objects['list0:1']
        self.assertEqual(snail['name'], 'Snail')
        self.assertEqual(snail['style'], 'enemy')
        self.assertTrue(snail['does'])
        self.assertEqual(objects['list1:0']['name'], 'Apple')
        self.assertEqual(objects['list1:0']['fields'][0]['choices'], 'fruit')
        self.assertEqual(objects['list2:0']['detail'], '128 pixels up')
        names = [c['name'] for c in egg['fields'][0]['choices']]
        self.assertEqual(names, ['Egg: stone axe first', 'Egg: skateboard', 'Egg: Honey Girl',
                                 'Hidden egg: fire weapon or a bonus item', 'Hidden egg: eggplant', 'Hidden egg: key'])

    def test_every_type_has_a_name(self):
        for kind, (group, name, does) in ai.TYPES.items():
            self.assertFalse(name.startswith('Unknown'), kind)
            self.assertNotRegex(name, r'0x')
            if group in ('enemy', 'fruit', 'platform', 'spring', 'item'):
                self.assertTrue(does, kind)

    def test_enemy_choices_are_the_games_own(self):
        choices = self.p.enemy_choices(0)
        self.assertEqual([c['value'] for c in choices], [0x02, 0x0E])
        self.assertEqual([c['name'] for c in choices], ['Rock', 'Snail'])

    def _apply(self, rom, writes):
        rom = bytearray(rom)
        for offset, old, new in writes:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        return ai.AdventureIslandProfile(bytes(rom))

    def test_swap_enemy(self):
        plan = self.p.edit({'level': 0}, 'list0:1', {'type': 0x02})
        after = self._apply(self.p.rom, plan['writes'])
        self.assertEqual([e['type'] for e in after.lists({'level': 0})[0][2]], [0x1C, 0x02, 0x02])
        self.assertEqual(plan['watch']['want'], 0x02)
        self.assertEqual(plan['title'], 'Enemy here: Rock')

    def test_swap_rejects_other_values(self):
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'list0:1', {'type': 0x23})

    def test_egg_contents(self):
        plan = self.p.edit({'level': 0}, 'list0:0', {'type': 0x1B})
        after = self._apply(self.p.rom, plan['writes'])
        self.assertEqual(after.lists({'level': 0})[0][2][0]['type'], 0x1B)
        self.assertEqual(plan['title'], 'Hidden egg: key')

    def test_fruit(self):
        plan = self.p.edit({'level': 0}, 'list1:0', {'type': 0x14})
        after = self._apply(self.p.rom, plan['writes'])
        self.assertEqual([e['type'] for e in after.lists({'level': 0})[1][2]], [0x14, 0x10])

    def test_remove_keeps_the_others_in_place(self):
        before = self.p.lists({'level': 0})[0]
        plan = self.p.edit({'level': 0}, 'list0:1', {}, remove=True)
        after = self._apply(self.p.rom, plan['writes'])
        got = after.lists({'level': 0})[0]
        self.assertEqual([(e['pos'], e['type']) for e in got[2]], [(640, 0x1C), (880, 0x02)])
        self.assertLessEqual(got[3], before[3])
        self.assertIsNone(plan['watch']['want'])
        self.assertEqual(plan['watch']['others'], 0)

    def test_only_entry_cannot_be_removed(self):
        with self.assertRaises(ValueError):
            self.p.edit({'level': 0}, 'list2:0', {}, remove=True)

    def test_where(self):
        ram = bytearray(0x800)
        ram[0x2F], ram[0x1B], ram[0x51] = 0x40, 0xD9, 0
        ram[0x3A], ram[0x06], ram[0x3B] = 0x02, 0x40, 4
        ram[0x509] = 0x88
        self.assertEqual(self.p.where(bytes(ram)), {'part': {'level': 0}, 'x': 0x240 - 256, 'y': 0})
        ram[0x49] = 3
        self.assertEqual(self.p.where(bytes(ram))['part'], {'level': 0, 'bonus': 3})
        ram[0x2F] = 0
        self.assertIsNone(self.p.where(bytes(ram)))

    def test_watcher(self):
        plan = self.p.edit({'level': 0}, 'list0:1', {'type': 0x02})
        w = self.p.watcher(plan['watch'])
        ram = bytearray(0x800)
        ram[0x2F], ram[0x1B] = 0x40, 0xD9
        camera = 864 - 320 + 256           # the frame the game makes it
        ram[0x3A], ram[0x06] = camera >> 8, camera & 0xFF
        ram[0x554 + 5], ram[0x564 + 5], ram[0x594 + 5], ram[0x584 + 5] = 1, 0x02, 1, 0x40
        self.assertFalse(w.see(bytes(ram), 0, 'changed'))
        camera += 40
        ram[0x3A], ram[0x06] = camera >> 8, camera & 0xFF
        self.assertTrue(w.see(bytes(ram), 2, 'changed'))
        self.assertEqual(w.result()['state'], 'good')


if __name__ == '__main__':
    unittest.main()
