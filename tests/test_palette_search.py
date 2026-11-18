"""Finding the stored color behind a palette entry the tags do not lead to (romancer.palette_trace).

No engine needed: the swatches and ROMs are built by hand. Every place these
searches return is only a proposal; the editor and the coverage sweep write
it and replay the game before calling it anything.
"""
import unittest

from romancer import palette_trace as pt
from romancer.palette_trace import Swatch


def line(domain, fmt, stored, status='derived', first=0, sources=None):
    size = len(stored[0])
    return [Swatch(domain, first + i, 'group', fmt, raw, [[0, 0, 0]], list(sources[i]) if sources else [None] * size, status)
            for i, raw in enumerate(stored)]


def genesis_line(words, **more):
    return line('palette', 'genesis', [bytes.fromhex(w) for w in words], **more)


WORDS = ['0000', '0eee', '0222', '06ae', '0444', '0888', '0e00', '00e0', '000e', '0e0e', '0ee0', '00ee', '0246', '0642', '0a86', '068a']


class StoredCopiesTests(unittest.TestCase):
    def test_a_whole_palette_line_stored_as_plain_colors_is_found_wherever_the_tags_point(self):
        rom = bytes(range(256)) * 2 + b''.join(bytes.fromhex(w) for w in WORDS) + b'\x55' * 64
        swatches = genesis_line(WORDS)
        found = pt.stored_copies(swatches[3], swatches, rom, 'genesis')
        self.assertEqual(found, [{'offsets': [518, 519], 'run': 16, 'copies': 1}])
        writes = pt.plan_at(swatches[3], [255, 0, 0], rom, found[0]['offsets'])
        self.assertEqual(writes, [(518, 0x06, 0x00), (519, 0xAE, 0x0E)])

    def test_the_longest_run_wins_and_an_entry_outside_every_run_has_no_place(self):
        # Entry 0 is the backdrop the game forces to black, so only entries 1..15 match the ROM.
        stored = ['0000'] + WORDS[1:]
        rom = b'\xAA' * 100 + bytes.fromhex('0abc') + b''.join(bytes.fromhex(w) for w in WORDS[1:]) + b'\xAA' * 50 \
            + b''.join(bytes.fromhex(w) for w in WORDS[1:4]) + b'\xBB' * 20
        swatches = genesis_line(stored)
        found = pt.stored_copies(swatches[2], swatches, rom, 'genesis')
        self.assertEqual([(f['offsets'][0], f['run']) for f in found], [(104, 15), (184, 3)])
        self.assertEqual(pt.stored_copies(swatches[0], swatches, rom, 'genesis'), [])

    def test_a_run_of_one_repeated_value_is_never_offered(self):
        swatches = genesis_line(['0000'] * 16)
        self.assertEqual(pt.stored_copies(swatches[5], swatches, bytes(4096), 'genesis'), [])
        swatches = line('palette', 'sms-rgb222', [b'\x3f'] * 16)
        self.assertEqual(pt.stored_copies(swatches[5], swatches, b'\x3f' * 4096, 'sms'), [])

    def test_the_three_game_boy_shade_registers_are_looked_for_together(self):
        rom = b'\x00' * 300 + bytes([0xD8, 0x1E, 0x1B]) + b'\x00' * 300 + bytes([0xD8, 0x00, 0x1B])
        swatches = line('dmg_palette', 'dmg-shades', [b'\xD8', b'\x1E', b'\x1B'])
        self.assertEqual(pt.stored_copies(swatches[1], swatches, rom, 'gb'), [{'offsets': [301], 'run': 3, 'copies': 1}])

    def test_nes_offsets_count_from_the_end_of_the_file_header(self):
        body = b'\x00' * 64 + bytes([0x0F, 0x16, 0x27, 0x30]) + b'\x00' * 64
        rom = b'NES\x1a' + bytes(12) + body
        swatches = line('palette', 'nes-index', [bytes([v]) for v in (0x0F, 0x16, 0x27, 0x30)])
        found = pt.stored_copies(swatches[2], swatches, rom, 'nes')
        self.assertEqual(found[0]['offsets'], [66])
        self.assertEqual(pt.plan_at(swatches[2], list(pt.NES_RGB[0x11]), rom, found[0]['offsets']), [(82, 0x27, 0x11)])

    def test_found_places_puts_another_scenes_direct_source_first_and_skips_the_entrys_own_tags(self):
        rom = bytes(range(256)) * 2 + b''.join(bytes.fromhex(w) for w in WORDS) + b'\x55' * 64
        swatches = genesis_line(WORDS)
        places = pt.found_places(swatches[3], swatches, rom, 'genesis', hints=[[900, 901]])
        self.assertEqual([p['how'] for p in places], ['other scene', 'copy of 16 entries'])
        self.assertEqual(places[0]['offsets'], [900, 901])
        tagged = genesis_line(WORDS, sources=[[{'offset': 512 + 2 * i, 'kind': 'derived', 'weak': False, 'pc': 0},
                                               {'offset': 513 + 2 * i, 'kind': 'derived', 'weak': False, 'pc': 0}] for i in range(16)])
        self.assertEqual(pt.found_places(tagged[3], tagged, rom, 'genesis'), [], 'the place the tags already name is not a new find')


class ConstantPlacesTests(unittest.TestCase):
    def test_numbers_loaded_next_to_each_other_in_code_are_offered_and_a_lone_match_is_not(self):
        code = bytes([0x3E, 0xE1, 0x22, 0x3E, 0xE1, 0x22, 0x3E, 0xD1, 0x77, 0xC9])       # ld a,$E1 / ld (hl+),a ... ret
        rom = b'\x00' * 500 + code + b'\x00' * 500 + bytes([0x3E, 0xE1]) + b'\x00' * 500
        swatches = line('dmg_palette', 'dmg-shades', [b'\xE1', b'\xE1', b'\xD1'])
        self.assertEqual(pt.constant_places(swatches[0], swatches, rom, 'gb'), [501, 504])
        self.assertEqual(pt.constant_places(swatches[2], swatches, rom, 'gb'), [507])
        places = pt.found_places(swatches[2], swatches, rom, 'gb')
        self.assertEqual([(p['how'], p['offsets']) for p in places], [('constant in code', [507])])
        self.assertEqual(pt.constant_places(genesis_line(WORDS)[1], genesis_line(WORDS), rom, 'genesis'), [], 'one-byte palettes only')


class MeasurementTests(unittest.TestCase):
    """A shade register built two bits at a time from four table bytes, as fade tables do."""

    def setUp(self):
        self.rom = b'\x11' * 10 + bytes([0x00, 0x40, 0x80, 0xC0]) + b'\x22' * 10

    def entry(self, rom):
        return bytes([(rom[13] & 0xC0) | (rom[12] & 0xC0) >> 2 | (rom[11] & 0xC0) >> 4 | (rom[10] & 0xC0) >> 6])

    def measure(self, writes):
        rom = bytearray(self.rom)
        for offset, old, new in writes:
            self.assertEqual(rom[offset], old)
            rom[offset] = new
        after = self.entry(rom)
        return None if after == self.entry(self.rom) else after

    def test_each_bit_is_measured_and_the_flips_that_give_the_wanted_value_are_returned(self):
        self.assertEqual(self.entry(self.rom), b'\xE4')
        # Only three of the four bytes were seen to move the entry (the fourth holds 00): its neighbours are measured too.
        writes = pt.plan_by_measurement(self.measure, self.rom, [11, 12, 13], b'\xE4', b'\x1B')
        rom = bytearray(self.rom)
        for offset, _, new in writes:
            rom[offset] = new
        self.assertEqual(self.entry(rom), b'\x1B')
        self.assertEqual([w[0] for w in writes], [10, 11, 12, 13])

    def test_a_value_the_measured_bits_cannot_reach_gives_no_plan(self):
        low_only = lambda writes: (lambda v: None if v == b'\xE4' else v)(bytes([0xE4 ^ ((self.measure(writes) or b'\xE4')[0] ^ 0xE4) & 0x0F]))
        self.assertIsNone(pt.plan_by_measurement(low_only, self.rom, [11, 12, 13], b'\xE4', b'\x1B'))
        self.assertIsNone(pt.plan_by_measurement(self.measure, self.rom, [], b'\xE4', b'\x1B'))
        self.assertIsNone(pt.plan_by_measurement(self.measure, self.rom, [11], b'\xE4', b'\xE4'))


if __name__ == '__main__':
    unittest.main()
