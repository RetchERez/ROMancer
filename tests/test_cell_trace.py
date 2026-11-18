"""Background-cell edit paths (romancer.cell_trace), without an emulator.

The "game" here is a model: a Game Boy map built from a level of block
numbers and a table of block definitions, the way many games build their
backgrounds. Its replay is the model run again on the edited ROM, so a plan
is confirmed or refused by what the model then draws, as the real engine does.
"""
import json
import unittest
from array import array

from romancer import cell_trace as ct
from romancer import graphics_trace as gt
from romancer import provenance as pv


def tag(kind, offset, weak=False):
    return (kind << 28) | offset | (pv.RT_WEAK if weak else 0)


def make_scene(domains, frame=10):
    snap = pv.Snapshot(frame, {name: pv.DomainSnapshot(name, data, array('I', tags), array('I', [0x150] * len(tags)))
                               for name, (data, tags) in domains.items()}, 'screen')
    return pv.Scene('scene', frame, 'screen', [(0, b'')], snap)


LEVEL, BLOCKS, PLAIN, BASE = 0x1000, 0x2000, 0x3000, 0x40


class BlockGame:
    """Map rows 0-7: 2x2 blocks from LEVEL (16 block numbers per row of blocks) and BLOCKS (4 tiles per block).
    Row 8: copied straight from PLAIN. Row 9: PLAIN + 32 with BASE added by the game. A sprite byte in the
    tile area follows the first block number of the level (a stand-in for anything else that reads the level)."""

    def __init__(self, tagged_blocks=False):
        rom = bytearray(0x8000)
        for i in range(64):
            rom[LEVEL + i] = (i * 5) % 6
        for b in range(8):
            rom[BLOCKS + b * 4:BLOCKS + b * 4 + 4] = bytes(0x10 + b * 4 + k for k in range(4))
        for i in range(64):
            rom[PLAIN + i] = 0x60 + i
        self.rom = bytes(rom)
        self.tagged_blocks = tagged_blocks

    def draw(self, rom):
        vram = bytearray(0x2000)
        tags = [0] * 0x2000
        for t in range(0x10 * 16, 0x100 * 16):            # every tile the map uses holds a picture
            vram[t] = (t * 7) & 0xFF or 1
        for by in range(4):
            for bx in range(16):
                block = rom[LEVEL + by * 16 + bx]
                for k in range(4):
                    a = 0x1800 + (by * 2 + k // 2) * 32 + bx * 2 + k % 2
                    src = BLOCKS + block * 4 + k
                    vram[a] = rom[src]
                    # the tag of a computed byte names the last ROM byte read: here the block definition
                    tags[a] = tag(pv.RT_ROM if self.tagged_blocks else pv.RT_DERIVED, src)
        for x in range(32):
            vram[0x1800 + 8 * 32 + x] = rom[PLAIN + x]
            tags[0x1800 + 8 * 32 + x] = tag(pv.RT_ROM, PLAIN + x)
            vram[0x1800 + 9 * 32 + x] = (rom[PLAIN + 32 + x] + BASE) & 0xFF
            tags[0x1800 + 9 * 32 + x] = tag(pv.RT_DERIVED, PLAIN + 32 + x)
        vram[0x0010] = rom[LEVEL]
        return bytes(vram), tags

    def scene(self):
        vram, tags = self.draw(self.rom)
        scene = make_scene({'vram': (vram, tags)})
        scene.video = {'lcdc': 0x91, 'scx': 0, 'scy': 0, 'wx': 0, 'wy': 0}
        return scene

    def verify(self, plan, expect=None):
        """graphics_trace.verify_plan's result, from the model instead of an engine."""
        before, _ = self.draw(self.rom)
        after, _ = self.draw(plan.apply(self.rom))
        changed = [i for i in range(len(before)) if before[i] != after[i]]
        expect = plan.expect if expect is None else expect
        missed = [i for i, v in expect.get('vram', {}).items() if after[i] != v]
        planned = set(expect.get('vram', {}))
        result = {'verified': bool(changed), 'changed': {'vram': changed} if changed else {}, 'by': 'memory', 'from_frame': 0,
                  'as_planned': bool(changed) and not missed, 'missed': {'vram': missed} if missed else {},
                  'unplanned': {'vram': n} if (n := sum(i not in planned for i in changed)) else {}}
        plan.verified = result
        return result


class CellReadingTests(unittest.TestCase):
    def test_tile_status_looks_at_the_tile_number_only(self):
        # NES: tile byte from ROM, attribute byte computed. The cell as a whole is 'derived'; its picture is not.
        vram = bytearray(0x800)
        tags = [0] * 0x800
        vram[5] = 0x42
        tags[5] = tag(pv.RT_ROM, 0x1234)
        vram[0x3C0 + 1] = 0x55
        tags[0x3C0 + 1] = tag(pv.RT_DERIVED, 0x2000)
        layer = gt.layers(make_scene({'vram': (bytes(vram), tags)}), 'nes', {'ppuctrl': 0})[0]
        cell = layer.cell(5, 0)
        self.assertEqual(cell.status, 'derived')
        self.assertEqual(ct.tile_status(cell), 'rom')
        self.assertEqual(ct.tile_bytes(cell), [0])
        self.assertEqual(ct.tile_status(layer.cell(6, 0)), 'unknown')

    def test_tile_bytes_per_system(self):
        def cell(system, stored):
            return gt.MapCell(system, 'vram', 'l', 0, 0, list(range(len(stored))), stored, 0, 0,
                              sources=[{'offset': 9, 'kind': 'rom', 'weak': False, 'pc': 0}] + [None] * (len(stored) - 1))
        self.assertEqual(ct.tile_bytes(cell('snes', b'\x34\x12')), [0, 1])
        self.assertEqual(ct.tile_bytes(cell('genesis', b'\x12\x34')), [1, 0])
        self.assertEqual(ct.tile_status(cell('genesis', b'\x12\x34')), 'unknown')     # the low byte is the second one
        self.assertEqual(ct.tile_bytes(cell('snes', b'\x34')), [0])                   # mode 7
        self.assertEqual(ct.tile_bytes(cell('gbc', b'\x34\x00')), [0])

    def test_cell_bytes_uses_the_systems_encoding(self):
        def cell(system, stored, **kw):
            return gt.MapCell(system, 'vram', 'l', 2, 2, list(range(len(stored))), stored, 0, 0, **kw)
        self.assertEqual(ct.cell_bytes(cell('gb', b'\x10'), tile=0x11), b'\x11')
        self.assertEqual(ct.cell_bytes(cell('snes', b'\x34\x12'), tile=0x235, hflip=True), b'\x35\x52')
        self.assertEqual(ct.cell_bytes(cell('genesis', b'\x12\x34'), tile=0x235), b'\x12\x35')
        self.assertEqual(ct.cell_bytes(cell('nes', b'\x10\x00'), palette=3), b'\x10\xc0')     # cell (2, 2) is the lower right of its block
        self.assertEqual(ct.cell_bytes(cell('gb', b'\x10')), b'\x10')

    def test_map_area_counts_both_game_boy_maps(self):
        game = BlockGame()
        area = ct.map_area(gt.layers(game.scene(), 'gb'), 'gb')
        self.assertIn(0x1800, area['vram'])
        self.assertIn(0x1FFF, area['vram'])
        self.assertNotIn(0x0010, area['vram'])

    def test_layers_the_chip_does_not_draw_are_marked(self):
        # Mega Drive: the window plane covers nothing while registers 17 and 18 are zero
        regs = [0] * 24
        regs[2], regs[3], regs[4], regs[12], regs[16] = 0x30, 0x00, 0x07, 0x81, 0x01
        scene = make_scene({'vram': (bytes(0x10000), [0] * 0x10000)})
        shown = lambda: {l.name: l.shown for l in gt.layers(scene, 'genesis', {'regs': regs})}
        self.assertEqual(shown(), {'plane A': True, 'plane B': True, 'window': False})
        regs[18] = 0x04
        self.assertTrue(shown()['window'])
        self.assertEqual({l.shown for l in gt.layers(scene, 'genesis')}, {None})          # no registers: not known
        # Super NES: the main and sub screen flags
        video = {'bg_mode': 1, 'bg_scaddr': [0x1000, 0x2000, 0x3000, 0], 'bg_scsize': [0] * 4, 'bg_tdaddr': [0] * 4,
                 'bg_hofs': [0] * 4, 'bg_vofs': [0] * 4, 'bg_tilesize': [0] * 4,
                 'bg_enabled': [1, 0, 0, 0, 1], 'bgsub_enabled': [0, 1, 0, 0, 0]}
        layers = gt.layers(scene, 'snes', video)
        self.assertEqual([l.shown for l in layers], [True, True, False])
        self.assertIn('switched off', layers[2].notes[-1])
        del video['bg_enabled']
        self.assertEqual([l.shown for l in gt.layers(scene, 'snes', video)], [None, None, None])
        # Game Boy: a window that is on but parked below the screen
        small = make_scene({'vram': (bytes(0x2000), [0] * 0x2000)})
        video = {'lcdc': 0xB1, 'scx': 0, 'scy': 0, 'wx': 7, 'wy': 144}
        self.assertEqual([(l.name, l.shown) for l in gt.layers(small, 'gb', video)], [('background', None), ('window', False)])
        video['wy'] = 100
        self.assertTrue(gt.layers(small, 'gb', video)[1].shown)
        self.assertIn('shown', gt.layers(small, 'gb', video)[1].to_dict())


class PlanCellEditTests(unittest.TestCase):
    def setUp(self):
        self.game = BlockGame()
        self.scene = self.game.scene()
        self.layers = gt.layers(self.scene, 'gb')
        self.layer = self.layers[0]

    def plan(self, cell, **kw):
        new = bytes([(cell.stored[0] + 1) & 0xFF])
        return ct.plan_cell_edit(cell, new, self.game.rom, self.scene, 'gb', verify=self.game.verify, layers=self.layers, **kw)

    def test_plain_cell_is_written_in_place(self):
        cell = self.layer.cell(3, 8)
        plan = self.plan(cell)
        self.assertEqual(plan.kind, 'direct')
        self.assertEqual(plan.writes, [(PLAIN + 3, 0x63, 0x64)])
        self.assertEqual(plan.details['also_cells'], [])
        self.assertEqual(plan.details['outside_maps'], 0)
        self.assertTrue(plan.verified['as_planned'])

    def test_block_definition_is_found_and_every_use_is_listed(self):
        cell = self.layer.cell(2, 0)                      # block column 1, row 0: top-left tile of its block
        self.assertEqual(ct.tile_status(cell), 'derived')
        block = self.game.rom[LEVEL + 1]
        plan = self.plan(cell)
        self.assertEqual(plan.kind, 'cell-source')
        self.assertEqual(plan.details['relation'], 'copy')
        self.assertEqual(plan.writes, [(BLOCKS + block * 4, cell.stored[0], cell.stored[0] + 1)])
        uses = sum(self.game.rom[LEVEL + i] == block for i in range(64))
        self.assertGreater(uses, 1)
        self.assertEqual(len(plan.details['also_cells']), uses - 1)
        self.assertIn(['background', 2 + 12, 0], plan.details['also_cells'])     # the level repeats every six blocks
        self.assertTrue(any('same stored piece' in note for note in plan.notes))
        self.assertEqual(plan.details['outside_maps'], 0)

    def test_value_the_game_adds_a_base_to(self):
        cell = self.layer.cell(4, 9)
        plan = self.plan(cell)
        self.assertEqual(plan.kind, 'cell-source')
        self.assertEqual(plan.details['relation'], 'offset')
        self.assertEqual(plan.writes, [(PLAIN + 36, 0x60 + 36, 0x60 + 37)])
        self.assertEqual(plan.expect, {'vram': {0x1800 + 9 * 32 + 4: cell.stored[0] + 1}})

    def test_a_place_that_changes_more_than_the_maps_is_refused(self):
        # Point the tag of a block cell at the level byte that the sprite byte also follows, and make that level
        # byte numerically equal to the cell, so writing it does give the planned cell.
        game = self.game
        rom = bytearray(game.rom)
        rom[LEVEL] = 0
        rom[BLOCKS:BLOCKS + 4] = bytes([0, 0x70, 0x71, 0x72])     # block 0's first tile is tile 0 ... which is block 0
        game.rom = bytes(rom)

        def draw(rom, inner=game.draw):
            vram, tags = inner(rom)
            vram = bytearray(vram)
            vram[0x1800] = rom[LEVEL]                              # the model's first cell now copies the level byte
            tags[0x1800] = tag(pv.RT_DERIVED, LEVEL)
            return bytes(vram), tags
        game.draw = draw
        scene = game.scene()
        layers = gt.layers(scene, 'gb')
        cell = layers[0].cell(0, 0)
        with self.assertRaises(ValueError) as caught:
            ct.plan_cell_edit(cell, b'\x01', game.rom, scene, 'gb', verify=game.verify, layers=layers, radius=0)
        self.assertIn('outside the background maps', str(caught.exception))

    def test_a_base_added_to_every_cell_is_not_a_piece_of_the_background(self):
        # Row 9 is PLAIN + BASE. Make the model read BASE from the ROM, right after the row data, so the traced
        # neighbourhood of a row 9 cell holds both its own byte and the base; only its own byte may be offered.
        game = self.game
        where = PLAIN + 64
        rom = bytearray(game.rom)
        rom[where] = BASE
        game.rom = bytes(rom)

        def draw(rom, inner=game.draw):
            vram, tags = inner(rom)
            vram = bytearray(vram)
            for y in range(10, 32):                       # the rest of the map: the same row data, with the base added
                for x in range(32):
                    a = 0x1800 + y * 32 + x
                    vram[a] = (rom[PLAIN + 32 + x] + rom[where]) & 0xFF
                    tags[a] = tag(pv.RT_DERIVED, where)
            for x in range(32):
                a = 0x1800 + 9 * 32 + x
                vram[a] = (rom[PLAIN + 32 + x] + rom[where]) & 0xFF
            return bytes(vram), tags
        game.draw = draw
        scene = game.scene()
        layers = gt.layers(scene, 'gb')
        cell = layers[0].cell(4, 20)                      # tagged with the base only
        with self.assertRaises(ValueError) as caught:
            ct.plan_cell_edit(cell, bytes([cell.stored[0] + 1]), game.rom, scene, 'gb', verify=game.verify, layers=layers,
                              radius=0)
        self.assertIn('base the game adds to every cell', str(caught.exception))

    def test_a_stored_piece_must_also_hold_from_the_start_of_the_recording(self):
        cell = self.layer.cell(4, 9)                      # PLAIN + 36, with a base added
        seen = []

        def confirm(plan, expect=None):
            seen.append(plan.details['source_offset'])
            result = self.game.verify(plan, expect)
            if plan.details['source_offset'] == PLAIN + 36:           # played from the start, this byte sends the game elsewhere
                result = dict(result, as_planned=False)
            return result
        with self.assertRaises(ValueError) as caught:
            self.plan(cell, confirm=confirm)
        self.assertEqual(seen, [PLAIN + 36])
        self.assertIn('not when the recording is replayed from its start', str(caught.exception))
        plan = self.plan(cell, confirm=self.game.verify)
        self.assertTrue(plan.details['from_start'])
        # a place written in place is not asked for it: its source is traced, not found by trying
        self.assertEqual(self.plan(self.layer.cell(3, 8), confirm=confirm).kind, 'direct')
        self.assertEqual(seen, [PLAIN + 36])

    def test_failure_says_what_was_tried(self):
        cell = self.layer.cell(2, 0)
        with self.assertRaises(ValueError) as caught:
            self.plan(cell, paths=('direct', 'reencode'))
        self.assertIn('reencode', str(caught.exception))
        with self.assertRaises(ValueError):
            ct.plan_cell_edit(cell, cell.stored, self.game.rom, self.scene, 'gb', verify=self.game.verify)

    def test_probe_budget_is_respected(self):
        calls = []

        def verify(plan, expect=None):
            calls.append(plan.writes)
            return {'verified': False, 'changed': {}, 'as_planned': False, 'missed': {}, 'unplanned': {}}
        cell = self.layer.cell(2, 0)
        with self.assertRaises(ValueError):
            ct.plan_cell_edit(cell, bytes([cell.stored[0] + 1]), self.game.rom, self.scene, 'gb', verify=verify,
                              layers=self.layers, paths=('cell-source',), max_probes=3)
        self.assertEqual(len(calls), 3)

    def test_side_effects_separates_cells_from_other_memory(self):
        result = {'changed': {'vram': [0x1800, 0x1801, 0x0010]}}
        effects = ct.side_effects(result, {'vram': {0x1800: 1}}, self.layers, 'gb')
        self.assertEqual(effects, {'also_cells': [['background', 1, 0]], 'outside_maps': 1})


class BuiltCellsInTheEditorTests(unittest.TestCase):
    """scene_graphics._plan_built_cells: what the Scenes editor does with cells that are not stored one by one."""

    def setUp(self):
        from romancer import scene_graphics as sg
        self.sg = sg
        self.game = BlockGame()
        self.scene = self.game.scene()
        self.layers = gt.layers(self.scene, 'gb')

    def built(self, *places):
        out, expect = [], {'vram': {}}
        for x, y in places:
            cell = self.layers[0].cell(x, y)
            new = bytes([cell.stored[0] + 1])
            out.append((cell, new))
            expect['vram'][cell.addresses[0]] = new[0]
        return out, expect

    def plan(self, *places):
        built, expect = self.built(*places)
        return self.sg._plan_built_cells({}, built, self.game.rom, self.scene, 'gb', self.layers, self.game.verify, expect)

    def test_one_cell(self):
        plan = self.plan((2, 0))
        self.assertEqual(plan.kind, 'cell-source')
        self.assertTrue(plan.details['also_cells'])
        out = self.sg._plan_out(plan, self.game.rom, 'cells-built')
        self.assertEqual(out['method'], 'cells-built')
        self.assertTrue(out['in_scene']['as_planned'])
        self.assertEqual(out['in_scene']['unplanned'], {'vram': len(plan.details['also_cells'])})
        self.assertIn('cells-built', self.sg.METHODS)

    def test_the_replay_from_the_start_is_asked_for_each_piece(self):
        built, expect = self.built((2, 0))
        asked = []

        def confirm(plan, wanted=None):
            asked.append(plan.details['source_offset'])
            return self.game.verify(plan, wanted)
        plan = self.sg._plan_built_cells({}, built, self.game.rom, self.scene, 'gb', self.layers, self.game.verify, expect, confirm)
        self.assertEqual(asked, [plan.details['source_offset']])
        self.assertTrue(plan.details['from_start'])
        refuse = lambda plan, wanted=None: dict(self.game.verify(plan, wanted), as_planned=False)
        with self.assertRaises(ValueError) as caught:
            self.sg._plan_built_cells({}, built, self.game.rom, self.scene, 'gb', self.layers, self.game.verify, expect, refuse)
        self.assertIn('cannot be changed here', str(caught.exception))

    def test_several_cells_are_replayed_together(self):
        # two cells of different blocks: both pieces change, and the cells of every use of either are listed
        plan = self.plan((2, 0), (5, 1))
        self.assertEqual(len(plan.details['source_offsets']), 2)
        self.assertEqual(len([w for w in plan.writes if w[0] >= BLOCKS]), 2)
        self.assertTrue(plan.verified['as_planned'])
        self.assertTrue(any('same stored pieces' in note for note in plan.notes))

    def test_cells_of_one_piece_painted_alike_merge_and_too_many_are_refused(self):
        plan = self.plan((2, 0), (14, 0))                 # the same block, the same corner
        self.assertEqual(len(plan.details['source_offsets']), 1)
        with self.assertRaises(ValueError) as caught:
            self.plan(*[(x, 0) for x in range(self.sg.MAX_BUILT_CELLS + 1)])
        self.assertIn('Paint fewer cells', str(caught.exception))

    def test_no_stored_piece_is_said_plainly(self):
        built, expect = self.built((2, 0))
        nothing = lambda plan, wanted=None: {'verified': False, 'changed': {}, 'as_planned': False, 'missed': {}, 'unplanned': {}}
        with self.assertRaises(ValueError) as caught:
            self.sg._plan_built_cells({}, built, self.game.rom, self.scene, 'gb', self.layers, nothing, expect)
        self.assertIn('cannot be changed here', str(caught.exception))


class SweepTests(unittest.TestCase):
    """trace/graphics_sweep.py: which cells are tried, in which scene, and how a miss is named."""

    @classmethod
    def setUpClass(cls):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'trace'))
        import graphics_report
        import graphics_sweep
        cls.gs, cls.report = graphics_sweep, graphics_report

    def setUp(self):
        self.game = BlockGame()
        self.scene = self.game.scene()
        self.real = gt.verify_plan
        gt.verify_plan = lambda fe_for, rom, plan, scene, expect=None, buttons_for=None: self.game.verify(plan, expect)

    def tearDown(self):
        gt.verify_plan = self.real

    def blocks_only(self, frame):
        """A scene of the same game with rows 8 and 9 not drawn yet: nothing in it is stored cell by cell."""
        vram, tags = self.game.draw(self.game.rom)
        vram = bytearray(vram)
        for a in range(0x1800 + 8 * 32, 0x1800 + 10 * 32):
            vram[a], tags[a] = 0, 0
        scene = make_scene({'vram': (bytes(vram), tags)}, frame)
        scene.video = self.scene.video
        return scene

    def test_candidates_show_a_picture_and_come_from_different_rom_bytes(self):
        layers = gt.layers(self.scene, 'gb')
        (layer, count, picked), = self.gs.map_candidates(self.scene, 'gb', layers, 'rom')
        self.assertEqual(count, 32)                                    # row 8
        self.assertEqual(len(picked), 2)
        self.assertEqual(len({c.sources[0]['offset'] for c in picked}), len(picked))
        (_, count, picked), = self.gs.map_candidates(self.scene, 'gb', layers, 'derived')
        self.assertEqual(count, 8 * 32 + 32)                           # the block rows and row 9
        self.assertTrue(all(ct.tile_status(c) == 'derived' for c in picked))
        blank = self.blocks_only(5)
        self.assertEqual(self.gs.map_candidates(blank, 'gb', gt.layers(blank, 'gb'), 'rom')[0][1:], (0, []))

    def test_a_stored_cell_in_another_scene_comes_before_a_computed_one_in_the_chosen_scene(self):
        chosen = self.blocks_only(1800)
        self.scene.frame = 900
        m = self.gs.measure_map_edit(self.game.rom, 'gb', [self.scene, chosen], chosen, None)
        self.assertTrue(m['as_planned'])
        self.assertEqual((m['scene_frame'], m['path'], m['source']), (900, 'direct', 'rom'))
        self.assertEqual(m['from_start'], {'as_planned': True, 'outside_maps': 0})
        self.assertEqual([(t['scene_frame'], t['phase'], t['candidates']) for t in m['scenes']], [(1800, 'stored', 0)])

    def test_a_cell_that_shows_a_blank_tile_is_the_last_resort_and_says_so(self):
        vram, tags = self.game.draw(self.game.rom)
        vram = bytearray(vram)
        vram[0x60 * 16:0x80 * 16] = bytes(0x20 * 16)                   # the tiles row 8 shows: one flat color
        for a in list(range(0x1800, 0x1800 + 8 * 32)) + list(range(0x1800 + 9 * 32, 0x1800 + 10 * 32)):
            vram[a], tags[a] = 0, 0                                    # nothing else on the map
        scene = make_scene({'vram': (bytes(vram), tags)}, 1800)
        scene.video = self.scene.video
        self.assertEqual(self.gs.map_candidates(scene, 'gb', gt.layers(scene, 'gb'), 'rom')[0][1], 0)
        self.assertEqual(self.gs.map_candidates(scene, 'gb', gt.layers(scene, 'gb'), 'rom', with_picture=False)[0][1], 32)
        m = self.gs.measure_map_edit(self.game.rom, 'gb', [scene], scene, None)
        self.assertTrue(m['as_planned'])
        self.assertEqual((m['phase'], m['path'], m['blank_tile']), ('blank', 'direct', True))
        self.assertEqual([t['phase'] for t in m['scenes']], ['stored', 'computed'])

    def test_a_layer_that_is_not_drawn_is_not_tried(self):
        self.scene.video = dict(self.scene.video, lcdc=0xB1, wx=7, wy=150)      # window on, off screen, same map
        lay = gt.layers(self.scene, 'gb')
        self.assertEqual([l.shown for l in lay], [None, False])
        m = self.gs.measure_map(self.game.rom, 'gb', self.scene, None)
        self.assertEqual((m['layers'], m['layer'], m['candidates']), (1, 'background', 32))

    def test_a_cell_that_disturbs_other_memory_is_kept_in_hand_for_a_clean_one(self):
        inner = self.game.verify
        seen = []

        def verify(plan, expect=None):
            result = inner(plan, expect)
            seen.append(plan.writes)
            if len(seen) == 1:                           # the first cell tried: something else changed with it
                result['changed'] = {'vram': result['changed']['vram'] + [0x0010]}
            return result
        self.game.verify = verify
        m = self.gs.measure_map(self.game.rom, 'gb', self.scene, None)
        self.assertEqual(len(seen), 2)
        self.assertEqual(m['outside_maps'], 0)
        self.assertEqual(m['attempts'][0]['outside_maps'], 1)
        # with nothing better, the first one stands and says so
        seen.clear()

        def always(plan, expect=None):
            result = inner(plan, expect)
            result['changed'] = {'vram': result['changed']['vram'] + [0x0010]}
            return result
        self.game.verify = always
        m = self.gs.measure_map(self.game.rom, 'gb', self.scene, None)
        self.assertTrue(m['as_planned'])
        self.assertEqual(m['outside_maps'], 1)

    def test_a_computed_cell_is_confirmed_through_its_stored_piece(self):
        chosen = self.blocks_only(1800)
        m = self.gs.measure_map_edit(self.game.rom, 'gb', [chosen], chosen, None)
        self.assertTrue(m['as_planned'])
        self.assertEqual((m['path'], m['relation'], m['phase']), ('cell-source', 'copy', 'computed'))
        self.assertEqual(m['from_start'], {'as_planned': True, 'outside_maps': 0})
        self.assertGreater(m['also_cells'], 0)
        self.assertEqual(m['outside_maps'], 0)

    def test_a_miss_keeps_what_was_tried_and_is_given_a_cause(self):
        self.game.verify = lambda plan, expect=None: {'verified': False, 'changed': {}, 'as_planned': False, 'missed': {},
                                                      'unplanned': {}}
        chosen = self.blocks_only(1800)
        m = self.gs.measure_map_edit(self.game.rom, 'gb', [chosen], chosen, None)
        self.assertFalse(m.get('as_planned'))
        self.assertEqual([t['phase'] for t in m['scenes']], ['stored', 'computed', 'blank'])
        self.assertEqual(self.gs.map_cause({'map_edit': m})[0], 'computed')
        m = self.gs.measure_map_edit(self.game.rom, 'gb', [self.scene], self.scene, None)
        self.assertEqual(self.gs.map_cause({'map_edit': m})[0], 'no effect')
        self.assertIsNone(self.gs.map_cause({'map_edit': {'as_planned': True}}))
        empty = make_scene({'vram': (bytes(0x2000), [0] * 0x2000)})
        empty.video = self.scene.video
        m = self.gs.measure_map_edit(self.game.rom, 'gb', [empty], empty, None)
        self.assertEqual(self.gs.map_cause({'map_edit': m})[0], 'nothing drawn')
        # results written before every layer and scene was tried
        old = {'layers': [{'cells': {'rom': 0, 'code': 0, 'derived': 9, 'unknown': 0}}], 'map_edit': {'candidates': 0}}
        self.assertEqual(self.gs.map_cause(old)[0], 'computed')
        self.assertEqual(self.gs.map_cause({'layers': [], 'map_edit': {}})[0], 'no layer')
        self.assertTrue(all(cause in self.gs.MAP_CAUSES for cause in ('computed', 'no effect', 'nothing drawn', 'no layer',
                                                                      'shared source', 'out of time', 'not from power-on')))
        broke = {'scenes': [{'scene_frame': 9, 'layers': 1, 'attempts': [
            {'source': 'derived', 'error': 'cell-source at 0x10: ... but not when the recording is replayed from its start'},
            {'source': 'rom', 'error': 'direct: the replay did not show the cell as planned'}]}]}
        self.assertEqual(self.gs.map_cause({'map_edit': broke})[0], 'not from power-on')

    def test_a_repack_counts_only_when_nothing_unrelated_changed(self):
        span = range(0x100, 0x200)
        planned = [0x110, 0x112, 0x115]
        sort = lambda changed: self.gs.unrelated_changes(changed, 'vram', planned, span)
        self.assertEqual(sort({'vram': planned}), {'in_block': 0, 'copies': 0, 'unrelated': 0})
        self.assertEqual(sort({'vram': planned + [0x120]}), {'in_block': 1, 'copies': 0, 'unrelated': 0})
        # the same tile loaded to two more places: whole shifted copies of the edit
        twice = planned + [a + 0x400 for a in planned] + [a + 0x900 for a in planned]
        self.assertEqual(sort({'vram': twice}), {'in_block': 0, 'copies': 2, 'unrelated': 0})
        # a partial copy, a stray byte, another domain: unrelated
        self.assertEqual(sort({'vram': planned + [0x510, 0x512]})['unrelated'], 2)
        self.assertEqual(sort({'vram': twice + [0x3000], 'chr': [1, 2]}), {'in_block': 0, 'copies': 2, 'unrelated': 3})
        good = {'as_planned': True, 'unplanned_in_block': 0, 'reads_on_alike': True, 'unrelated': 0}
        self.assertTrue(self.gs.repack_confirmed(good))
        for worse in ({'unrelated': 4}, {'unplanned_in_block': 1}, {'reads_on_alike': False}, {'as_planned': False}):
            self.assertFalse(self.gs.repack_confirmed({**good, **worse}), worse)

    def test_the_coverage_section_is_replaced_in_place(self):
        import tempfile
        from pathlib import Path
        done = {'scene_frame': 900, 'as_planned': True, 'path': 'cell-source', 'also_cells': 3, 'outside_maps': 0,
                'from_start': {'as_planned': True, 'outside_maps': 0},
                'scenes': [{'scene_frame': 1800}]}
        missed = {'scene_frame': 1800, 'candidates': 0, 'computed_candidates': 5,
                  'scenes': [{'scene_frame': 1800, 'layers': 1, 'attempts': [{'source': 'derived', 'error': 'x'}]}]}

        def result(sha, name, map_edit):
            return {'sha256': sha, 'system': 'gb', 'member': f'{name}.zip!{name}.gb', 'ok': True, 'frames': 1800,
                    'tiles': {k: {'rom': 1, 'code': 0, 'derived': 0, 'unknown': 0} for k in ('with_picture', 'on_screen')},
                    'tile_edit': {'as_planned': True, 'verified': True, 'candidates': 1}, 'derived_edit': {},
                    'overlay': {}, 'private_copy': {}, 'layers': [], 'map_edit': map_edit}
        results = [result('a' * 64, 'Game A', done), result('b' * 64, 'Game B', missed)]
        results[0]['repack'] = {'confirmed': True, 'as_planned': True, 'sound': True, 'codec': 'lz2', 'path': 'relocate',
                                'copies_elsewhere': 1}
        results[1]['repack'] = {'confirmed': False, 'as_planned': True, 'sound': True, 'codec': 'rnc1', 'path': 'reencode',
                                'unrelated': 9}
        with tempfile.TemporaryDirectory() as folder:
            for r in results:
                (Path(folder) / (r['sha256'] + '.json')).write_text(json.dumps(r))
            totals = self.gs.report(folder)
            self.assertEqual(totals['gb']['map_edit_as_planned'], 1)
            self.assertEqual(totals['gb']['map_edit_path'], {'cell-source': 1})
            self.assertEqual(totals['gb']['map_edit_cause'], {'computed': 1})
            self.assertEqual(totals['gb']['map_edit_in_another_scene'], 1)
            self.assertEqual((totals['gb']['repack_confirmed'], totals['gb']['repack_as_planned_but_unrelated_bytes_changed'],
                              totals['gb']['repack_codec'], totals['gb']['repack_path']), (1, 1, {'lz2': 1}, {'relocate': 1}))
            self.assertEqual(totals['gb']['map_edit_on_a_blank_tile'], 0)
            self.assertEqual(totals['gb']['map_edit_as_planned_from_power_on_too'], 1)
            text = self.report.section(totals, results, {'b' * 64: 'Game B (USA)'}, {'gb': {'map_edit_as_planned': 0}})
            self.assertIn('| gb | Game B (USA) | computed (0 stored and 1 computed cells tried in 1 scene) |', text)
            self.assertIn('| gb | 2 | 1 | 0 | 0 | 0 | 1 | 1 | 1 | 0 | 1 | 1 |', text)
            self.assertIn('before this one: gb 0 (all 0)', text)
            self.assertIn('| gb | 2 | 1 | 1 | 1 | 0 | 1 | 0 |', text)
            self.assertIn('Confirmed re-packs by codec: lz2 1.', text)
            self.assertNotIn('Game A', text)
            away = dict(results[0], core='other_trace_libretro.dll')
            listed = self.report.section(totals, results, {}, unavailable=[away])
            self.assertIn('### Not available (1)', listed)
            self.assertIn('| gb | Game A | other_trace_libretro.dll |', listed)
            page = Path(folder) / 'COVERAGE.md'
            page.write_text('| palette table |\n', encoding='utf-8')
            self.report.write_section(page, text)
            self.report.write_section(page, text.replace('Game B (USA)', 'Game B again'))
            now = page.read_text(encoding='utf-8')
            self.assertTrue(now.startswith('| palette table |\n\n' + self.report.BEGIN))
            self.assertEqual(now.count(self.report.BEGIN), 1)
            self.assertIn('Game B again', now)
            self.assertNotIn('Game B (USA)', now)


if __name__ == '__main__':
    unittest.main()
