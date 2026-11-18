import unittest
from array import array
from types import SimpleNamespace

from romancer import level_layout as ll
from romancer import provenance as pv

TABLE = 0x400           # block table: 4 bytes a block (top left, top right, bottom left, bottom right)
LARGER = 0x900          # table of larger blocks: 4 block numbers each, 0x20 added to each number
LAYOUT = 0x1200         # the level: larger block numbers, a column of 4 at a time


def block_numbers():
    """16 by 8 blocks, made of 8 by 4 larger blocks; larger block k holds blocks k, k + 1, 2k, 2k + 3 (mod 40)."""
    larger = [[(x * 3 + y * 5) % 12 for y in range(4)] for x in range(8)]
    blocks = {}
    for x in range(8):
        for y in range(4):
            k = larger[x][y]
            members = [k, k + 1, (2 * k) % 40, (2 * k + 3) % 40]
            for index, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                blocks[(x * 2 + dx, y * 2 + dy)] = members[index]
    return larger, blocks


def rom_image():
    larger, blocks = block_numbers()
    rom = bytearray(b'\xEE' * 0x2000)
    for number in range(64):
        rom[TABLE + number * 4:TABLE + number * 4 + 4] = bytes((number * 4 + k) % 251 for k in range(4))
    for k in range(12):
        members = [k, k + 1, (2 * k) % 40, (2 * k + 3) % 40]
        rom[LARGER + k * 4:LARGER + k * 4 + 4] = bytes(m + 0x20 for m in members)
    for x in range(8):
        rom[LAYOUT + x * 4:LAYOUT + x * 4 + 4] = bytes(larger[x])
    return bytes(rom), larger, blocks


def sources(blocks, left=0, top=0):
    """Where each cell's tile number was copied from: 2 by 2 cells a block."""
    out = {}
    for (bx, by), number in blocks.items():
        for k, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            out[(left + bx * 2 + dx, top + by * 2 + dy)] = TABLE + number * 4 + k
    return out


class GridTests(unittest.TestCase):
    def test_blocks_are_found_from_where_the_cells_were_copied_from(self):
        rom, larger, blocks = rom_image()
        grid = ll.find_grid(sources(blocks, left=1), 34, 16)
        self.assertEqual((grid.width, grid.height, grid.left, grid.top, grid.step), (2, 2, 1, 0, 4))
        self.assertEqual(grid.pattern, (0, 1, 2, 3))
        self.assertEqual(grid.share, 1.0)
        lowest = min(blocks.values())
        self.assertEqual(grid.number(3, 2), blocks[(3, 2)] - lowest)
        self.assertEqual(grid.block(1 + 6, 5), (3, 2))
        self.assertEqual(grid.inside(1 + 7, 5), (1, 1))

    def test_tables_kept_as_four_separate_lists_are_blocks_too(self):
        cells = {}
        for bx in range(8):
            for by in range(6):
                number = (bx * 5 + by * 3) % 30
                for k, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                    cells[(bx * 2 + dx, by * 2 + dy)] = 0x3000 + k * 256 + number
        grid = ll.find_grid(cells, 16, 12)
        self.assertEqual((grid.width, grid.height, grid.step), (2, 2, 1))
        self.assertEqual(grid.pattern, (0, 256, 512, 768))

    def test_cells_that_are_not_built_from_blocks_have_no_grid(self):
        cells = {(x, y): 0x5000 + (x * 37 + y * 101) % 900 for x in range(16) for y in range(12)}
        self.assertIsNone(ll.find_grid(cells, 16, 12))

    def test_blocks_from_another_table_are_left_out(self):
        rom, larger, blocks = rom_image()
        cells = sources(blocks)
        for bx in range(16):                                          # a status bar drawn from a table far away
            for k, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                cells[(bx * 2 + dx, 16 + dy)] = 0x9000 + (bx % 3) * 4 + k
        grid = ll.find_grid(cells, 32, 18)
        self.assertLess(max(grid.number(*at) for at in grid.first), 64)
        self.assertNotIn((0, 8), grid.first)


class SearchTests(unittest.TestCase):
    def test_a_row_of_block_numbers_is_found_whatever_the_table_adds_to_them(self):
        rom = bytearray(b'\x00' * 0x800)
        numbers = [3, 9, 4, 4, 11, 0, 7]
        rom[0x345:0x345 + 7] = bytes(n + 0x40 for n in numbers)
        self.assertEqual(ll.find_rows(bytes(rom), numbers), [(0x345, 0x40)])
        self.assertEqual(ll.find_rows(bytes(rom), [1, 2, 3, 250]), [])

    def test_numbers_found_all_over_the_rom_are_not_a_layout(self):
        self.assertEqual(ll.find_rows(bytes(0x1000), [0, 0, 0]), [])

    def test_runs_and_their_pieces(self):
        rom, larger, blocks = rom_image()
        grid = ll.find_grid(sources(blocks), 32, 16)
        through = dict((kind, (index, numbers)) for kind, index, numbers in ll.runs(grid, 5, 3))
        self.assertEqual(through['row'][0], 5)
        self.assertEqual(len(through['row'][1]), 16)
        self.assertEqual(through['column'][0], 3)
        pieces = ll.windows([5, 5, 6, 7, 7], 2)
        self.assertEqual(pieces[0], (0, [5, 5, 6, 7, 7]))
        self.assertTrue(all(start <= 2 < start + len(piece) for start, piece in pieces))
        self.assertNotIn((3, [7, 7]), pieces)

    def test_the_table_of_larger_blocks_and_then_the_level_list(self):
        rom, larger, blocks = rom_image()
        grid = ll.find_grid(sources(blocks), 32, 16)
        table = ll.find_entries(rom, grid)
        self.assertEqual((table.width, table.height), (2, 2))
        lowest = min(blocks.values())
        self.assertEqual(table.base, 0x20 + lowest)
        self.assertEqual(table.placed[(0, 0)], LARGER + larger[0][0] * 4)
        self.assertEqual(table.placed[(3, 5)], LARGER + larger[1][2] * 4 + 3)
        members = [blocks[(0, 0)] - lowest, blocks[(1, 0)] - lowest, blocks[(0, 1)] - lowest, blocks[(1, 1)] - lowest]
        self.assertEqual(table.entry(rom, tuple(members)), LARGER + larger[0][0] * 4)
        self.assertIsNone(table.entry(rom, (39, 39, 39, 39)))
        # the larger blocks are themselves a grid; a column of them is where the level is stored
        coarse = ll.find_grid(table.placed, 16, 8)
        self.assertEqual((coarse.width, coarse.height, coarse.step), (2, 2, 4))
        column = next(numbers for kind, index, numbers in ll.runs(coarse, 2, 1) if kind == 'column')
        hits = ll.find_rows(rom, column)
        self.assertIn(LAYOUT + 2 * 4, [offset for offset, base in hits])

    def test_a_level_unpacked_into_memory_leads_back_to_the_rom(self):
        numbers = [4, 9, 2, 2, 7, 5]
        data = bytearray(64)
        data[20:26] = bytes(n + 1 for n in numbers)
        tags = array('I', [0] * 64)
        for index in range(6):
            tags[20 + index] = (pv.RT_ROM << 28) | (0x1F00 + index * 2)
        ram = pv.DomainSnapshot('ram', bytes(data), tags, array('I', [0] * 64))
        video = pv.DomainSnapshot('vram', bytes(data), tags, array('I', [0] * 64))
        snapshot = SimpleNamespace(domains={'ram': ram, 'vram': video})
        self.assertEqual(ll.find_in_memory(snapshot, numbers, skip=16), [[0x1F10 + index * 2 for index in range(6)]])


if __name__ == '__main__':
    unittest.main()
