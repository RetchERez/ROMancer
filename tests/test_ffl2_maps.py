"""Original synthetic map programs; no cartridge data or copied disassembly."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def xy(op, x, y):
    return bytes(((op << 4) | (y >> 2), ((y & 3) << 6) | x))


def fixture():
    raw = bytearray(262144)
    for offset, count in ((0x1c000, 511), (0x1ef80, 32)):
        for i in range(count):
            raw[offset+4*i:offset+4*i+4] = bytes((0x6b, 0x48, 0x8c, 0x9f))
    raw[0x1c000:0x1c004] = bytes((0, 0x48, 4, 4))
    raw[0x1c800:0x1c805] = bytes((0, 0, 0, 0, 0))
    # A header with two interaction words, one sprite page and one real object.
    header = bytes((0x65, 2, 0, 0x80, 2, 0x10, 5, 0xff, 6,
                    1, 0xff, 0, 0x0f, 0x8e, 0xad, 0x12, 0x91, 0xff))
    raw[0x1c86b:0x1c86b+len(header)] = header
    raw[0x20000:0x20003] = xy(7, 1, 1) + b'\0'
    stream = xy(7, 1, 1) + xy(1, 14, 31) + b'\2' + b'\0'
    raw[0x20265:0x20265+len(stream)] = stream
    raw[0x1f000:0x1f020] = bytes((3, 1, 1, 0xc0)) + bytes(28)
    raw[0x1f800+2] = 1
    for q in range(4):
        for y in range(8):
            raw[0x8040+q*16+y*2:0x8042+q*16+y*2] = bytes((255 if q & 1 else 0, 255 if q & 2 else 0))
    return raw


class FFL2MapsTests(unittest.TestCase):
    def test_terrain_edit_preserves_each_shared_headers_collision_context(self):
        from romancer import ffl2_maps
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'root.gb';selected=Path(folder)/'selected.gb'
            raw=fixture();raw[0x1c800:0x1c805]=bytes((0x65,2,1,0,0))
            raw[0x1f020:0x1f040]=bytes((3,1,3))+bytes(29)
            root.write_bytes(raw);selected.write_bytes(raw)
            with patch.object(ffl2_maps,'ROOT_SHA256',hashlib.sha256(raw).hexdigest()):
                with self.assertRaisesRegex(ValueError,'collision|shared'):
                    ffl2_maps.plan_edits(selected,root,0x486b,[{'kind':'command','offset':0x20267,'tile':1}])

    def test_derived_header_cannot_trade_interactions_for_removed_story_records(self):
        from romancer import ffl2_maps
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'root.gb';selected=Path(folder)/'selected.gb'
            raw=fixture();root.write_bytes(raw)
            changed=raw.copy();changed[0x1c86f]=5
            changed[0x1c87a:0x1c87c]=b'\x01\xff'
            selected.write_bytes(changed)
            with patch.object(ffl2_maps,'ROOT_SHA256',hashlib.sha256(raw).hexdigest()):
                with self.assertRaisesRegex(ValueError,'counts|structure|pointers'):
                    ffl2_maps.plan_edits(selected,root,0x486b,[{'kind':'command','offset':0x20267,'x':15}])

    def setUp(self):
        from romancer import ffl2_maps
        self.maps = ffl2_maps
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original = Path(self.temp.name)/'original.gb'
        self.current = Path(self.temp.name)/'current.gb'
        self.raw = fixture()
        self.original.write_bytes(self.raw)
        self.current.write_bytes(self.raw)
        identity = patch.object(ffl2_maps, 'ROOT_SHA256', hashlib.sha256(self.raw).hexdigest())
        identity.start()
        self.addCleanup(identity.stop)

    def test_catalog_pages_actual_header_variants_and_arrivals(self):
        result = self.maps.catalog(self.current, self.original, limit=1)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['counts']['arrivals'], 543)
        self.assertEqual(result['counts']['maps'], 2)
        self.assertEqual(result['rooms'][0]['header'], 0x4800)
        page = self.maps.catalog(self.current, self.original, offset=1, limit=1)
        self.assertEqual(page['rooms'][0]['header'], 0x486b)
        self.assertEqual(self.maps.catalog(self.current, self.original, query='486b')['total'], 1)
        for params in ({'limit': 257}, {'offset': -1}, {'limit': True}, {'query': 'a'*129}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.maps.catalog(self.current, self.original, **params)

    def test_catalog_thumbnails_are_small_pngs_and_unsupported_is_explicit(self):
        result = self.maps.catalog(self.current, self.original, limit=2)
        for room in result['rooms']:
            thumb = room['thumbnail']
            self.assertEqual(thumb['status'], 'available')
            self.assertEqual((thumb['width'], thumb['height']), (96, 96))
            self.assertTrue(thumb['data_url'].startswith('data:image/png;base64,'))
            self.assertLess(len(thumb['data_url']), 20000)
            self.assertNotIn('tiles', room)
            self.assertNotIn('cells', room)

    def test_conditional_thumbnail_returns_reason_without_choosing_a_branch(self):
        raw = self.raw.copy()
        raw[0x20265:0x2026a] = xy(7, 1, 1)+bytes((0xa1, 0x03, 0))
        self.current.write_bytes(raw); self.original.write_bytes(raw)
        with patch.object(self.maps, 'ROOT_SHA256', hashlib.sha256(raw).hexdigest()):
            row = self.maps.catalog(self.current, self.original, query='486B')['rooms'][0]
            self.assertEqual(row['thumbnail']['status'], 'unavailable')
            self.assertIn('state nibble 1', row['thumbnail']['reason'])
            self.assertEqual(self.maps.inspect_room(self.current, self.original, 0x486b)['map']['status'], 'unsupported')

    def test_marker_backing_table_and_protected_instance_order(self):
        cells = [1]*4096
        cells[4] = 3; cells[65] = 35
        marked, markers = self.maps._markers(cells, 1)
        self.assertEqual([marked[4], marked[65]], [64, 97])
        self.assertEqual(markers, [{'index': 0, 'x': 4, 'y': 0, 'tile': 3},
                                   {'index': 1, 'x': 1, 'y': 1, 'tile': 35}])
        cells[:33] = [3]*33
        with self.assertRaises(ValueError):
            self.maps._markers(cells, 1)

    def test_inspection_uses_actual_tiles_and_keeps_npc_packed_flags(self):
        info = self.maps.inspect_room(self.current, self.original, 0x486b)
        self.assertEqual(info['map']['status'], 'decoded')
        self.assertEqual(info['map']['cells'][31*64+14], 2)
        self.assertEqual(info['map']['end'], 0x2026b)
        self.assertEqual(info['map']['commands'][1]['offset'], 0x20267)
        tile = info['map']['tiles'][2]
        self.assertEqual([tile[i] for i in (0, 8, 128, 136)], [0, 1, 2, 3])
        npc = info['objects'][0]
        self.assertEqual((npc['offset'], npc['x'], npc['y'], npc['event']), (0x1c876, 14, 45, 0x112))
        self.assertEqual(npc['raw'], '000f8ead1291')
        self.assertEqual(info['links'][0]['transition']['id'], 0x10)
        self.assertEqual(info['links'][0]['destination']['header'], 0x486b)
        self.assertEqual(info['map']['commands'][1]['final_cells'], 1)
        self.assertEqual(info['links'][1]['transition']['kind'], 'saved-return')
        self.assertEqual(info['map']['native_verified'], False)

    def test_transition_tag_arithmetic_and_reserved_return(self):
        for word, index in ((0x0510, 0x10), (0x06d0, 0x1d0)):
            self.assertEqual(self.maps.transition(word)['id'], index)
        self.assertEqual(self.maps.transition(0x06ff)['kind'], 'saved-return')
        self.assertEqual(self.maps.transition(0x0e10)['table'], 'special')
        self.assertEqual(self.maps.transition(0x0112)['kind'], 'event')

    def test_map_terminator_owns_one_byte_and_reports_last_writer(self):
        program = xy(7, 1, 1) + xy(1, 2, 3) + b'\2\0'
        result = self.maps.decode_map(program, 0, len(program))
        self.assertEqual(result['end'], len(program))
        self.assertEqual(result['provenance'][3*64+2], 2)
        for program in (b'\xb0\0', b'\x10\0', xy(2, 1, 1)*4097):
            with self.subTest(length=len(program)), self.assertRaises(ValueError):
                self.maps.decode_map(program, 0, len(program))

    def test_span_fill_uses_anchor_spine_and_operand_x_as_tile(self):
        # Matching row segments connect around a barrier. The game fill only
        # discovers horizontal spans along its anchor column, not that branch.
        program = (xy(7, 0, 0) + xy(2, 2, 2) + xy(4, 4, 4) + b'\1'
                   + xy(1, 2, 3) + b'\2' + xy(2, 2, 2) + xy(8, 3, 0) + b'\0')
        result = self.maps.decode_map(program, 0, len(program))
        grid = result['cells']
        self.assertEqual([grid[2*64+x] for x in range(2, 5)], [3, 3, 3])
        self.assertEqual(grid[4*64+2], 1)
        self.assertEqual(grid[3*64+3], 1)

    def test_conditional_requires_explicit_valid_state_and_stops_correctly(self):
        program = xy(7, 1, 1) + bytes((0xa2, 0x24)) + xy(1, 5, 5) + b'\2\0'
        with self.assertRaisesRegex(ValueError, 'state'):
            self.maps.decode_map(program, 0, len(program))
        yes = self.maps.decode_map(program, 0, len(program), state={2: 3})
        no = self.maps.decode_map(program, 0, len(program), state={2: 1})
        self.assertEqual(yes['cells'][5*64+5], 2)
        self.assertEqual(self.maps.decode_map(program, 0, len(program), state={'2': 3})['cells'], yes['cells'])
        self.assertEqual(no['cells'][5*64+5], 1)
        for state in ({2: 16}, {True: 1}, {2: True}):
            with self.assertRaises(ValueError):
                self.maps.decode_map(program, 0, len(program), state=state)

    def test_large_circle_fails_closed_and_cancellation_is_observed(self):
        program = xy(2, 1, 1) + xy(5, 12, 1) + b'\2\0'
        with self.assertRaisesRegex(ValueError, 'circle'):
            self.maps.decode_map(program, 0, len(program))
        with self.assertRaises(KeyboardInterrupt):
            self.maps.catalog(self.current, self.original, cancelled=lambda: True)
        with self.assertRaises(KeyboardInterrupt):
            self.maps.decode_map(b'\0', 0, 1, cancelled=lambda: True)

    def test_fixed_width_plans_preserve_original_and_packed_flags(self):
        changes = [{'kind': 'command', 'offset': 0x20267, 'x': 15, 'y': 31},
                   {'kind': 'npc', 'offset': 0x1c876, 'x': 13, 'y': 45},
                   {'kind': 'arrival', 'table': 'main', 'id': 0x10, 'x': 10, 'y': 30}]
        result = self.maps.plan_edits(self.current, self.original, 0x486b, changes)
        by_offset = {e['offset']: e for e in result['edits']}
        self.assertEqual(by_offset[0x20267]['after'], (xy(1, 15, 31)+b'\2').hex())
        self.assertEqual(by_offset[0x1c876]['after'], '000f8dad1291')
        self.assertEqual(by_offset[0x1c040]['after'], '6b488a9e')
        self.assertTrue(result['requires_native_playtest'])
        self.assertEqual(self.current.read_bytes(), self.raw)
        self.assertEqual(self.original.read_bytes(), self.raw)

    def test_unselected_scripts_flags_records_and_unknown_changes_are_protected(self):
        for change in (
            {'kind': 'npc', 'offset': 0x1c876, 'event': 7},
            {'kind': 'npc', 'offset': 0x1c877, 'x': 5},
            {'kind': 'command', 'offset': 0x20268, 'x': 5},
            {'kind': 'command', 'offset': 0x20267, 'tile': 3},
            {'kind': 'link', 'index': 1, 'arrival_id': 0x10},
            {'kind': 'arrival', 'table': 'special', 'id': 0, 'x': 4},
            {'kind': 'arrival', 'table': 'main', 'id': 0, 'x': 4},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.maps.plan_edits(self.current, self.original, 0x486b, [change])
        with self.assertRaises(ValueError):
            self.maps.plan_edits(self.current, self.original, 0x486b, [])
        with self.assertRaises(ValueError):
            self.maps.plan_edits(self.current, self.original, 0x4800,
                                 [{'kind': 'command', 'offset': 0x20000, 'x': 3}])

    def test_root_hash_and_structural_guards(self):
        raw = self.raw.copy(); raw[0x1c800+4] = 255
        self.current.write_bytes(raw)
        with self.assertRaises(ValueError):
            self.maps.catalog(self.current, self.original)
        self.original.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'revision'):
            self.maps.catalog(self.current, self.original)

    def test_prior_hex_changes_cannot_turn_protected_data_into_editable_context(self):
        for offset in (0x1f001, 0x1f800, 0x1c87a):
            raw = self.raw.copy(); raw[offset] ^= 1
            self.current.write_bytes(raw)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.maps.plan_edits(self.current, self.original, 0x486b,
                                     [{'kind': 'command', 'offset': 0x20267, 'x': 15}])

    def test_valid_link_replacement_encodes_tag_by_index_and_preserves_saved_return(self):
        result = self.maps.plan_edits(self.current, self.original, 0x486b,
                                     [{'kind': 'link', 'index': 0, 'arrival_id': 0x1d0}])
        self.assertEqual(result['edits'], [{'offset': 0x1c870, 'before': '1005', 'after': 'd006'}])
        self.assertEqual(self.current.read_bytes()[0x1c872:0x1c874], bytes((255, 6)))

    def test_same_behavior_trigger_substitution_in_prior_build_is_rejected(self):
        raw = self.raw.copy()
        program = xy(7, 1, 1)+xy(1, 14, 31)+b'\2'+xy(1, 8, 8)+b'\3\0'
        raw[0x20265:0x20265+len(program)] = program
        raw[0x1f004] = 0xc0
        self.original.write_bytes(raw)
        changed = raw.copy(); changed[0x2026c] = 4
        self.current.write_bytes(changed)
        with patch.object(self.maps, 'ROOT_SHA256', hashlib.sha256(raw).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'trigger'):
                self.maps.plan_edits(self.current, self.original, 0x486b,
                                     [{'kind': 'command', 'offset': 0x20267, 'x': 15}])


if __name__ == '__main__':
    unittest.main()
