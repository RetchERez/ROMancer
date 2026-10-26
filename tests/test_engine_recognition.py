"""Original generated THUMB roles and audio records; no commercial ROM bytes."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch


def put16(raw, offset, value):
    struct.pack_into('<H', raw, offset, value)


def put32(raw, offset, value):
    struct.pack_into('<I', raw, offset, value)


def fixture(shift=0, registers=(6, 4, 5, 7)):
    """Assemble a small, independently invented indexed-loader function."""
    raw = bytearray(0x1000 + shift)
    code, players, table = 0x40 + shift, 0x200 + shift, 0x230 + shift
    header, empty, tone, tracks = table + 32, table + 48, 0x300 + shift, 0x380 + shift
    index, playerbase, songbase, entry = registers
    words = [0xb5f0, (16 << 6) | index,
             0x4800 | (playerbase << 8), 0x4800 | (songbase << 8),
             0x0800 | (13 << 6) | (index << 3) | index,
             0x1800 | (index << 6) | (songbase << 3) | entry,
             0x8800 | (2 << 6) | (entry << 3) | 3,
             (1 << 6) | (3 << 3) | 1,
             0x1800 | (3 << 6) | (1 << 3) | 1,
             (2 << 6) | (1 << 3) | 1,
             0x1800 | (1 << 6) | (playerbase << 3) | 2,
             0x6800 | (2 << 3), 0x6800 | (entry << 3) | 1]
    call = code + len(words)*2
    target = 0x180 + shift
    displacement = target - (call + 4)
    words += [0xf000 | ((displacement >> 12) & 0x7ff),
              0xf800 | ((displacement >> 1) & 0x7ff), 0xbdf0]
    literals = (code + len(words)*2 + 3) & ~3
    for instruction, literal in ((2, literals), (3, literals+4)):
        pc = (code + instruction*2 + 4) & ~3
        words[instruction] |= (literal-pc)//4
    for i, word in enumerate(words):
        put16(raw, code+i*2, word)
    put32(raw, literals, 0x08000000+players)
    put32(raw, literals+4, 0x08000000+table)
    put16(raw, target, 0x4770)  # Independently generated return stub, never executed.
    for i in range(4):
        put32(raw, players+i*12, 0x03000040+i*0x80)
        put32(raw, players+i*12+4, 0x02000100+i*0x100)
        raw[players+i*12+8] = 4
        put32(raw, table+i*8, 0x08000000+(header if i < 2 else empty))
        put16(raw, table+i*8+4, i)
        put16(raw, table+i*8+6, i)  # Opaque secondary player selector.
    raw[header:header+4] = bytes((2, 0, 7, 0))
    put32(raw, header+4, 0x08000000+tone)
    put32(raw, header+8, 0x08000000+tracks)
    put32(raw, header+12, 0x08000000+tracks+8)
    raw[tracks:tracks+3] = bytes((0xbd, 1, 0xb1))
    raw[tracks+8:tracks+11] = bytes((0xbc, 0, 0xb1))
    raw[tone] = 1  # A PSG tone kind; no sample assets.
    return raw, dict(code=code, call=call, players=players, table=table,
                     header=header, empty=empty, tone=tone, tracks=tracks,
                     literals=literals)


class EngineRecognitionTests(unittest.TestCase):
    def setUp(self):
        from romancer import engine_recognition
        self.module = engine_recognition
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'fixture.gba'

    def recognize(self, raw, system='gba', **kw):
        self.path.write_bytes(raw)
        return self.module.recognize_engines(
            self.path, hashlib.sha256(raw).hexdigest(), system, **kw)

    def test_recovers_tables_from_register_roles_without_known_offsets(self):
        raw, addresses = fixture()
        result = self.recognize(raw)
        self.assertEqual(result['status'], 'MATCH')
        self.assertTrue(result['ok'])
        self.assertFalse(result['write_authorized'])
        finding, = result['findings']
        self.assertEqual(finding['family'], 'gba-m4a')
        self.assertEqual(finding['confidence'], 'code-and-structure')
        self.assertFalse(finding['engine_version_verified'])
        self.assertFalse(finding['runtime_verified'])
        evidence = finding['evidence']
        self.assertEqual(evidence['song_table_offset'], addresses['table'])
        self.assertEqual(evidence['player_table_offset'], addresses['players'])
        self.assertEqual(evidence['song_entries'], 4)
        self.assertEqual(evidence['nonempty_songs'], 2)
        self.assertEqual(evidence['track_pointers'], 4)
        self.assertEqual(evidence['distinct_song_headers'], 2)
        self.assertEqual(evidence['table_extent_evidence'], 'first-referenced-header')
        self.assertEqual(self.path.read_bytes(), raw)

    def test_shifted_layout_and_different_register_allocation(self):
        raw, addresses = fixture(0x154, (4, 5, 6, 7))
        result = self.recognize(raw)
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['findings'][0]['evidence']['song_table_offset'], addresses['table'])

    def test_data_without_code_relationship_is_not_an_engine(self):
        raw, addresses = fixture()
        raw[addresses['code']:addresses['code']+40] = bytes(40)
        self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_branch_cycle_is_not_followed(self):
        raw, a = fixture()
        put16(raw, a['code']+8, 0xe7fe)
        self.assertEqual(self.recognize(raw)['findings'], [])

    def test_missing_call_or_wrong_call_arguments_rejects_anchor(self):
        for offset, word in ((26, 0x4770), (24, 0x6800)):
            with self.subTest(offset=offset):
                raw, a = fixture()
                put16(raw, a['code']+offset, word)
                self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_bad_rom_regions_and_truncated_pointers_reject(self):
        for location, value in (('literals', 0x02000200), ('header', 0x0a100000)):
            raw, a = fixture()
            offset = a['literals'] if location == 'literals' else a['header']+8
            put32(raw, offset, value)
            self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_track_cannot_alias_table_or_its_header(self):
        for key in ('table', 'header', 'players'):
            raw, a = fixture()
            put32(raw, a['header']+8, 0x08000000+a[key])
            self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_malformed_player_ram_or_capacity_is_rejected(self):
        for field in ('pointer', 'capacity'):
            raw, a = fixture()
            if field == 'pointer':
                put32(raw, a['players'], 0x08000100)
            else:
                raw[a['players']+8] = 0
            self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_nonzero_block_counts_are_explicitly_unsupported(self):
        raw, a = fixture()
        raw[a['header']+1] = 1
        self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_null_hole_does_not_terminate_table(self):
        raw, a = fixture()
        put32(raw, a['table']+8, 0)
        result = self.recognize(raw)
        self.assertEqual(result['status'], 'MATCH')
        e = result['findings'][0]['evidence']
        self.assertEqual(e['song_entries'], 4)
        self.assertEqual(e['null_entries'], 1)
        self.assertEqual(e['nonempty_songs'], 1)

    def test_player_capacity_does_not_rewrite_declared_track_count(self):
        raw, a = fixture()
        raw[a['players']+8] = 1
        result = self.recognize(raw)
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['findings'][0]['evidence']['over_capacity_song_declarations'], 1)

    def test_rom_end_is_not_a_fabricated_header_boundary(self):
        raw, a = fixture()
        # Move the table beyond every header; a valid-looking run to EOF has
        # no supported format evidence for its extent.
        raw[-32:] = raw[a['table']:a['table']+32]
        put32(raw, a['literals']+4, 0x08000000+len(raw)-32)
        self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_duplicate_code_anchors_share_one_finding(self):
        raw, a = fixture()
        other, b = fixture(0x500)
        # Second function's literals refer to the first table pair.
        put32(other, b['literals'], 0x08000000+a['players'])
        put32(other, b['literals']+4, 0x08000000+a['table'])
        raw.extend(bytes(0x500))
        raw[b['code']:b['literals']+8] = other[b['code']:b['literals']+8]
        result = self.recognize(raw)
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['findings'][0]['evidence']['anchor_count'], 2)

    def test_track_cannot_alias_a_different_song_header(self):
        raw, a = fixture()
        # This otherwise valid initial command is inside the empty header.
        raw[a['empty']+2:a['empty']+4] = bytes((0xbc, 0))
        put32(raw, a['header']+8, 0x08000000+a['empty']+2)
        self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_self_referential_track_control_is_not_followed(self):
        raw, a = fixture()
        raw[a['tracks']] = 0xb2
        put32(raw, a['tracks']+1, 0x08000000+a['tracks'])
        self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_voicegroup_cannot_alias_referenced_structural_storage(self):
        raw, a = fixture()
        put32(raw, a['header']+4, 0x08000000+a['players'])
        self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_first_command_operand_cannot_straddle_into_header(self):
        raw, a = fixture()
        raw[a['header']-1] = 0xbd
        put32(raw, a['header']+8, 0x08000000+a['header']-1)
        self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_candidate_budget_exhaustion_is_explicit(self):
        raw, _ = fixture()
        with patch.object(self.module, 'MAX_FUNCTIONS', 0):
            self.assertEqual(self.recognize(raw)['status'], 'BUDGET_EXCEEDED')

    def test_malformed_later_record_does_not_publish_prefix(self):
        raw, a = fixture()
        put32(raw, a['table']+24, 0x02000000)
        self.assertEqual(self.recognize(raw)['status'], 'NO_MATCH')

    def test_rom_waitstate_mirrors_are_converted_after_region_check(self):
        raw, a = fixture()
        put32(raw, a['literals']+4, 0x0c000000+a['table'])
        self.assertEqual(self.recognize(raw)['status'], 'MATCH')

    def test_distinct_valid_table_pairs_are_ambiguous(self):
        raw, a = fixture()
        other, b = fixture(0x500)
        # Copy the entire second independently placed function/data region.
        raw.extend(bytes(0x500))
        raw[0x540:] = other[0x540:]
        result = self.recognize(raw)
        self.assertEqual(result['status'], 'AMBIGUOUS')
        self.assertEqual(result['findings'], [])

    def test_budget_exhaustion_never_returns_partial_findings(self):
        raw, _ = fixture()
        with patch.object(self.module, 'MAX_SONG_ENTRIES', 3):
            result = self.recognize(raw)
        self.assertEqual(result['status'], 'BUDGET_EXCEEDED')
        self.assertEqual(result['findings'], [])

    def test_other_systems_are_not_implemented(self):
        raw, _ = fixture()
        for system in ('nes', 'snes', 'genesis', 'gb', 'gbc'):
            with self.subTest(system=system):
                result = self.recognize(raw, system)
                self.assertEqual(result['status'], 'NOT_IMPLEMENTED')
                self.assertEqual(result['findings'], [])

    def test_expected_identity_is_mandatory(self):
        raw, _ = fixture()
        self.path.write_bytes(raw)
        for digest in ('0'*64, '', '../bad'):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                self.module.recognize_engines(self.path, digest, 'gba')

    def test_cancellation_before_read_and_during_scan(self):
        raw, _ = fixture()
        with self.assertRaises(KeyboardInterrupt):
            self.recognize(raw, cancelled=lambda: True)
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 5
        with self.assertRaises(KeyboardInterrupt):
            self.recognize(raw, cancelled=cancelled)

    def test_size_budget_applies_before_read(self):
        self.path.write_bytes(bytes(129))
        with patch.object(self.module, 'MAX_ROM_BYTES', 128), self.assertRaises(ValueError):
            self.module.recognize_engines(self.path, '0'*64, 'gba')


if __name__ == '__main__':
    unittest.main()
