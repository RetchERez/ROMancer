"""Game Boy Color profiles (Link's Awakening DX, Wario Land II): decoders and edits on made-up cartridges laid out
like the real ones. The real games are not part of the tests; what the tables mean was proven by replaying the real
games (research/gbc_more-level-profile.md)."""
import unittest

from romancer.level_profiles import Ram
from romancer.level_profiles import gbc_more as gm
from romancer.level_profiles.gb_adventure import _file


def put(rom, bank, address, data):
    o = _file(bank, address)
    rom[o:o + len(data)] = bytes(data)


def dx_cart():
    """Link's Awakening DX tables at their DX addresses. Overworld room $B3 with objects; dungeon map 0 (indoors A)
    rooms $16/$17 on the grid at $4220; map $FF rooms 2 and 3 on its grid at $44E0, room 2 with a chest ($4860 + 2),
    hidden stairs and two objects (list table $4600, layout table $7B77 in bank $0A); a chest in indoors A room $16
    ($4560 + $100 + $16). Every other room is empty."""
    rom = bytearray(64 * 0x4000)
    empty = 0x5000
    put(rom, 0x16, empty, [0xFF])
    for room in range(256):
        for table in (0x4000, 0x4200, 0x4400):
            put(rom, 0x16, table + room * 2, [empty & 0xFF, empty >> 8])
        for bank in (0x09, 0x0A, 0x0B):
            put(rom, bank, 0x4000 + room * 2, [0x00, 0x7F])
    for room in range(0x20):
        put(rom, 0x16, 0x4600 + room * 2, [empty & 0xFF, empty >> 8])
        put(rom, 0x0A, 0x7B77 + room * 2, [0x00, 0x7F])
    for bank in (0x09, 0x0A, 0x0B, 0x1A):
        put(rom, bank, 0x7F00, [0x00, 0x00, 0xFE])
    put(rom, 0x14, 0x4220 + 7 * 8 + 2, [0x16, 0x17])           # map 0 grid, row 7, columns 2 and 3
    put(rom, 0x14, 0x44E0 + 1 * 8 + 4, [0x02, 0x03])           # map $FF grid, row 1, columns 4 and 5
    put(rom, 0x14, 0x4200 + 7 * 8 + 2, [0x30, 0x31])           # where the original keeps map 0's grid: not used
    put(rom, 0x16, 0x4200 + 0x17 * 2, [0x40, 0x50])
    put(rom, 0x16, 0x5040, [0x34, 0x61, 0x45, 0x9B, 0xFF])
    put(rom, 0x14, 0x4560 + 0x100 + 0x16, [0x19])
    put(rom, 0x16, 0x4600 + 2 * 2, [0x60, 0x50])
    put(rom, 0x16, 0x5060, [0x23, 0x20, 0x44, 0x21, 0xFF])
    put(rom, 0x0A, 0x7B77 + 2 * 2, [0x00, 0x60])
    put(rom, 0x0A, 0x6000, [0x00, 0x00, 0x14, 0xA0, 0x18, 0xBF, 0xFE])
    put(rom, 0x14, 0x4860 + 2, [0x1A])
    put(rom, 0x14, 0x4560 + 0x200 + 0x1C, [0x0A])              # indoors B: a bomb (new in DX)
    put(rom, 0x16, 0x4000 + 0xB3 * 2, [0x10, 0x50])
    put(rom, 0x16, 0x5010, [0x34, 0x6E, 0x45, 0x6E, 0x56, 0x6F, 0xFF])
    return bytes(rom)


def dx_ram(room, mp, slots=(), blocks=None, at=0xFF):
    raw = bytearray(0x8000)
    raw[0x1BA5] = 1
    raw[0x1BAE] = at
    for slot, (kind, extra) in enumerate(slots):
        raw[0x280 + slot], raw[0x3A0 + slot], raw[0x3B0 + slot] = 5, kind, extra
    for place, kind in (blocks or {}).items():
        raw[0x1711 + place] = kind
    ram = Ram(bytes(raw))
    hram = bytearray(128)
    hram[0x76], hram[0x77] = room, mp
    ram.domains = {'hram': bytes(hram)}
    return ram


class LinksAwakeningDXTest(unittest.TestCase):
    def setUp(self):
        self.p = gm.LinksAwakeningDX(dx_cart())

    def test_where(self):
        self.assertEqual(self.p.where(dx_ram(0x17, 0)), {'part': {'map': 0}, 'x': 3 * 160, 'y': 7 * 128})
        self.assertEqual(self.p.where(dx_ram(0x03, 0xFF)), {'part': {'map': 0xFF}, 'x': 5 * 160, 'y': 128})
        self.assertEqual(self.p.where(dx_ram(0xA8, 0x10)), {'part': {'map': 0x10, 'room': 0xA8}, 'x': 0, 'y': 0})
        ram = bytearray(0x8000)
        ram[0x1B54] = 0xB3
        self.assertEqual(self.p.where(ram), {'part': {'map': 'overworld'}, 'x': 480, 'y': 1408})
        self.assertEqual(self.p.part_name({'map': 0xFF}), 'Dungeon map 0xFF')
        self.assertEqual(self.p.part_name({'map': 0}), 'Dungeon map 0')

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'map': 0})}
        self.assertEqual(sorted(objects), ['chest:22', 'obj:23:0', 'obj:23:1'])
        self.assertEqual(objects['chest:22']['detail'], "holds Nightmare's Key")
        ff = {o['id']: o for o in self.p.objects({'map': 0xFF})}
        self.assertEqual(sorted(ff), ['chest:2', 'obj:2:0', 'obj:2:1', 'stairs:2:24'])
        self.assertEqual((ff['chest:2']['x'], ff['chest:2']['y']), (4 * 160 + 4 * 16 + 8, 128 + 16 + 16))
        self.assertEqual((ff['obj:2:1']['x'], ff['obj:2:1']['y']), (4 * 160 + 4 * 16 + 8, 128 + 4 * 16 + 16))
        choices = [c['value'] for c in ff['chest:2']['fields'][0]['choices']]
        self.assertEqual(choices, [0x0A, 0x19, 0x1A])
        self.assertEqual(self.p.content_name(0x0A), 'Bomb')
        self.assertEqual(self.p.content_name(0x18), 'Stone Beak')
        overworld = {o['id']: o for o in self.p.objects({'map': 'overworld'})}
        self.assertEqual(overworld['obj:179:0']['name'], 'Butterfly')

    def test_edits(self):
        plan = self.p.edit({'map': 0xFF}, 'chest:2', {'contents': 0x19})
        self.assertEqual(plan['writes'], [(_file(0x14, 0x4862), 0x1A, 0x19)])
        self.assertEqual(plan['watch']['group'], 3)
        plan = self.p.edit({'map': 0}, 'chest:22', {'contents': 0x0A})
        self.assertEqual(plan['writes'], [(_file(0x14, 0x4676), 0x19, 0x0A)])
        plan = self.p.edit({'map': 0xFF}, 'stairs:2:24', {'block': 0xBE})
        self.assertEqual(plan['writes'], [(_file(0x0A, 0x6005), 0xBF, 0xBE)])
        plan = self.p.edit({'map': 0xFF}, 'obj:2:0', {'type': 0x21})
        self.assertEqual(plan['writes'], [(_file(0x16, 0x5061), 0x20, 0x21)])
        plan = self.p.edit({'map': 0xFF}, 'obj:2:0', {}, remove=True)
        base = _file(0x16, 0x5060)
        self.assertEqual(plan['writes'], [(base, 0x23, 0x44), (base + 1, 0x20, 0x21), (base + 2, 0x44, 0xFF)])
        with self.assertRaises(ValueError):
            self.p.edit({'map': 0xFF}, 'chest:2', {'contents': 0x03})
        plan = self.p.edit({'map': 'overworld'}, 'obj:179:1', {'type': 0x6F})
        self.assertEqual(plan['writes'], [(_file(0x16, 0x5013), 0x6E, 0x6F)])

    def test_watchers(self):
        chest = self.p.watcher(self.p.edit({'map': 0xFF}, 'chest:2', {'contents': 0x19})['watch'])
        self.assertFalse(chest.see(dx_ram(2, 0x10, slots=[(7, 0x19)]), 2, 'changed'))   # another map's room 2
        self.assertTrue(chest.see(dx_ram(2, 0xFF, slots=[(7, 0x19)]), 4, 'changed'))
        self.assertEqual(chest.result()['state'], 'good')
        control = self.p.watcher(self.p.edit({'map': 0xFF}, 'chest:2', {'contents': 0x19})['watch'])
        control.see(dx_ram(2, 0xFF, slots=[(7, 0x1A)]), 4, 'changed')
        self.assertEqual(control.result()['state'], 'bad')
        stairs = self.p.watcher(self.p.edit({'map': 0xFF}, 'stairs:2:24', {'block': 0xBE})['watch'])
        stairs.see(dx_ram(2, 0xFF, blocks={0x18: 0xBE}), 2, 'changed')
        self.assertTrue(stairs.see(dx_ram(2, 0xFF, blocks={0x18: 0xBE}), 30, 'changed'))
        self.assertEqual(stairs.result()['state'], 'good')
        swap = self.p.watcher(self.p.edit({'map': 0xFF}, 'obj:2:0', {'type': 0x21})['watch'])
        for run, kinds in (('original', [(0x20, 0), (0x21, 0)]), ('changed', [(0x21, 0), (0x21, 0)])):
            swap.see(dx_ram(2, 0xFF, slots=kinds), 2, run)
            swap.see(dx_ram(2, 0xFF, slots=kinds), 60, run)
        self.assertEqual(swap.result()['state'], 'good')


def wl_cart():
    """Wario Land II tables at their real addresses. Story 0: header at bank $0A $5000 (width 160, object map at bank
    $0F $4000), one area (rows 0-31, columns 16-47, object set 1). Object map: (14, 33) starts object index 2, (14, 34)
    holds a cell the scan does not start (index 1), (20, 100) starts index 3 outside every area; everything else is
    empty, packed in runs."""
    rom = bytearray(64 * 0x4000)
    put(rom, 0x0A, 0x4195, [0x00, 0x50])
    put(rom, 0x0A, 0x5000, [0x30, 160, 0x0E, 0x00, 0x40, 0x00, 0x40])
    packed = []

    def zeros(n):
        while n:
            k = min(n, 0x7F)
            packed.extend([k, 0x00])
            n -= k
    zeros(14 * 80 + 16)
    packed.extend([0x82, 0x0A, 0x10])
    zeros(20 * 80 + 50 - (14 * 80 + 18))
    packed.extend([0x81, 0xB0])
    zeros(48 * 80 - (20 * 80 + 51))
    packed.append(0)
    put(rom, 0x0F, 0x4000, packed)
    put(rom, 0, 0x2C98, [0x00, 0x60])
    put(rom, 0x0A, 0x6000, [0x10, 0x60] + [0x00, 0x2D] * 29)
    put(rom, 0x0A, 0x6010, [0x01, 0x02, 0x13, 0x00, 0x01])            # rows 0-31, columns 16-47, set 1
    put(rom, 0x3E, 0x4DB3 + 2, [0x00, 0x70])
    put(rom, 0x3E, 0x7000, [0, 0, 0, 0, 0, 0x87, 0x42, 0x91, 0x42, 0xB9, 0x42, 0x39, 0x45, 0x7D, 0x42])
    put(rom, 0x3E, 0x42B9, [0x01, 0x10, 0xF2, 0x00, 0x00, 0xF1, 0x40, 0x01, 0x9D, 0x41])
    put(rom, 0x3E, 0x4539, [0x49, 0x14, 0xF4, 0x05, 0x07, 0xAE, 0x41, 0x01, 0x5A, 0x60])
    put(rom, 0x22, 0x5DCA, [0x00, 0x60])
    text = bytearray(b' ' * 86)
    text[14:24] = bytes((ord(c) + 127) & 0xFF for c in 'Chapter   ')
    text[56:66] = bytes((ord(c) + 127) & 0xFF for c in 'Story     ')
    put(rom, 0x22, 0x6000, text)
    return bytes(rom)


def wl_ram(story=0, x=0x1C0, y=0x60, slots=(), mode=(3, 0x11)):
    raw = bytearray(0x8000)
    raw[0x6F1], raw[0x6F2] = mode
    raw[0x1510] = story
    for slot, data in enumerate(slots):
        raw[slot * 32:slot * 32 + 32] = data
    ram = Ram(bytes(raw))
    hram = bytearray(128)
    hram[0x2D], hram[0x2E], hram[0x2F], hram[0x30] = y >> 8, y & 0xFF, x >> 8, x & 0xFF
    ram.domains = {'hram': bytes(hram)}
    return ram


def wl_slot(row, col, record):
    s = bytearray(32)
    s[0] = 0x81 if col % 2 == 0 else 0x01
    s[1] = 0xB0 + col // 2
    s[2] = 0xA0 + row % 32 + 32 * (row // 32)
    for k, at in enumerate((7, 9, 10, 16, 17, 18, 19, 26, 30, 31)):
        s[at] = record[k]
    return bytes(s)


class WarioLand2Test(unittest.TestCase):
    def setUp(self):
        self.rom = wl_cart()
        self.p = gm.WarioLand2(self.rom)
        self.rec_a = self.p.record(0x42B9)
        self.rec_b = self.p.record(0x4539)

    def test_where(self):
        self.assertEqual(self.p.where(wl_ram()), {'part': {'story': 0}, 'x': 0x1C0, 'y': 0x60})
        self.assertIsNone(self.p.where(wl_ram(mode=(3, 0x0B))))           # the story's scroll
        self.assertEqual(self.p.part_name({'story': 0}), 'Story 1 (Chapter: Story)')

    def test_objects(self):
        objects = {o['id']: o for o in self.p.objects({'story': 0})}
        self.assertEqual(sorted(objects), ['obj:14:33', 'obj:14:34', 'obj:20:100'])
        o = objects['obj:14:33']
        self.assertEqual((o['x'], o['y'], o['name']), (33 * 16 + 8, 14 * 16 + 16, 'Object 42B9'))
        self.assertEqual([c['value'] for c in o['fields'][0]['choices']], [2, 3])
        self.assertEqual(objects['obj:14:34']['fields'], [])
        self.assertIn('does not start', objects['obj:14:34']['note'])
        self.assertIn('No single area', objects['obj:20:100']['note'])
        self.assertEqual([a['kind'] for a in self.p.addable({'story': 0})], ['42b9', '4539'])

    def test_edits(self):
        byte = _file(0x0F, 0x4000) + 2 * 9 + 1                          # after nine zero runs and the literal count
        self.assertEqual(self.rom[byte], 0x0A)
        plan = self.p.edit({'story': 0}, 'obj:14:33', {'type': 3})
        self.assertEqual(plan['writes'], [(byte, 0x0A, 0x0B)])
        plan = self.p.edit({'story': 0}, 'obj:14:33', {}, remove=True)
        self.assertEqual(plan['writes'], [(byte, 0x0A, 0x00)])
        with self.assertRaises(ValueError):
            self.p.edit({'story': 0}, 'obj:14:33', {'type': 4})          # the set's end marker
        with self.assertRaises(ValueError):
            self.p.edit({'story': 0}, 'obj:14:34', {'type': 2})          # not started by the scan
        plan = self.p.add({'story': 0}, '4539', 32 * 16 + 8, 14 * 16 + 16, {})
        self.assertEqual(plan['writes'], [(byte, 0x0A, 0xBA)])
        with self.assertRaises(ValueError):
            self.p.add({'story': 0}, '4539', 20 * 16 + 8, 3 * 16 + 16, {})   # inside a run of empty cells
        with self.assertRaises(ValueError):
            self.p.add({'story': 0}, '4539', 33 * 16 + 8, 14 * 16 + 16, {})  # taken

    def test_watchers(self):
        plan = self.p.edit({'story': 0}, 'obj:14:33', {'type': 3})
        w = self.p.watcher(plan['watch'])
        self.assertFalse(w.see(wl_ram(), 1, 'changed'))
        self.assertTrue(w.see(wl_ram(slots=[wl_slot(14, 33, self.rec_b)]), 2, 'changed'))
        self.assertEqual(w.result()['state'], 'good')
        control = self.p.watcher(plan['watch'])
        control.see(wl_ram(slots=[wl_slot(14, 33, self.rec_a)]), 2, 'changed')
        self.assertEqual(control.result()['state'], 'bad')
        other = self.p.watcher(plan['watch'])
        other.see(wl_ram(slots=[wl_slot(14, 32, self.rec_b)]), 2, 'changed')   # the other half of the byte
        self.assertEqual(other.result()['state'], 'bad')                       # the camera showed the spot
        gone = self.p.watcher(self.p.edit({'story': 0}, 'obj:14:33', {}, remove=True)['watch'])
        self.assertTrue(gone.compare)
        gone.see(wl_ram(slots=[wl_slot(14, 33, self.rec_a)]), 2, 'original')
        gone.see(wl_ram(), 2, 'changed')
        self.assertEqual(gone.result()['state'], 'good')
        far = self.p.watcher(plan['watch'])
        far.see(wl_ram(x=0x800), 2, 'changed')
        self.assertEqual(far.result()['state'], 'warn')
