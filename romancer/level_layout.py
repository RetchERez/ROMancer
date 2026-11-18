"""Find where a game stores which block goes where, from the ROM bytes its background cells were copied from.

Most games of these systems do not store a level cell by cell. They store
blocks (2 by 2 or 4 by 4 cells, say) once in a table, and the level as a list
of block numbers. graphics_trace knows, for every background cell on screen,
the ROM byte its tile number was copied from. That byte lies in the block
table, so the cells themselves say how the blocks are laid out:

    cell_sources(layer, skip)   {(x, y): ROM offset the cell's tile number was copied from}
    find_grid(sources, w, h)    Grid: the block size and where the blocks start, when the screen is built from blocks
    Grid.number(x, y)           which block (counted in table entries) a cell belongs to
    find_rows(rom, grid, ...)   places in the ROM that hold the block numbers of a row or column of blocks

A place found this way is only a candidate. It becomes an edit when the
game is replayed with one byte of it changed and the block on screen changes
to the block that was asked for (scene_graphics does that).

The same step can be taken again: block numbers that turn out to lie in a
table of larger blocks are themselves copied from that table, and the search
then finds the list of the larger blocks.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import gcd

SHAPES = ((4, 4), (2, 2), (4, 2), (2, 4), (8, 8), (1, 1))
MIN_SHARE = 0.4         # share of blocks that must follow the common pattern
MIN_RUN = 2             # blocks in a row or column needed to look for it in the ROM
MIN_DISTINCT = 2        # and how many different blocks it must hold


@dataclass
class Grid:
    width: int              # cells in a block
    height: int
    left: int               # the first block starts at this cell
    top: int
    pattern: tuple          # offset of each cell's source from the source of the block's first cell, row by row
    step: int               # table entries between one block and the next
    share: float            # share of whole blocks on screen that follow the pattern
    first: dict             # (block column, block row) -> ROM offset of the block's first cell, for blocks that follow it

    def block(self, x: int, y: int) -> tuple:
        return (x - self.left) // self.width, (y - self.top) // self.height

    def inside(self, x: int, y: int) -> tuple:
        return (x - self.left) % self.width, (y - self.top) % self.height

    def number(self, column: int, row: int):
        """The block's place in its table, counted in blocks from the lowest one seen; None when it does not follow the pattern."""
        offset = self.first.get((column, row))
        return None if offset is None else (offset - min(self.first.values())) // self.step


def cell_sources(layer, skip: int = 0) -> dict:
    """{(x, y): file offset} of the ROM byte each cell's tile number came from.

    For a plain copy that is the byte itself. For a number the game worked
    out (it added a base, say) it is the last ROM byte read before the cell
    was written, which for a block table is still the block's entry.
    """
    out = {}
    for cell in layer.cells:
        source = cell.sources[0] if cell.sources else None
        if source and source.get('kind') in ('rom', 'derived') and source.get('offset') is not None:
            out[(cell.x, cell.y)] = source['offset'] + skip
    return out


def _entry(pattern: tuple) -> bool:
    """Whether these offsets are the cells of one table entry: 0..n-1 in some order, or 0, d, 2d, ... for lists d apart."""
    count = len(pattern)
    values = sorted(pattern)
    if values[0] != 0 or len(set(values)) != count:
        return False
    if values == list(range(count)):
        return True
    spacing = values[1]
    return spacing >= count and values == [k * spacing for k in range(count)]


def find_grid(sources: dict, width: int, height: int):
    """The largest block size that most of the layer follows, or None when its cells are not copied from a block table."""
    found = []
    for w, h in SHAPES:
        if (w, h) == (1, 1):
            continue
        for top in range(h):
            for left in range(w):
                patterns: dict = {}
                blocks = {}
                for by in range((height - top) // h):
                    for bx in range((width - left) // w):
                        cells = [sources.get((left + bx * w + dx, top + by * h + dy)) for dy in range(h) for dx in range(w)]
                        if any(c is None for c in cells):
                            continue
                        pattern = tuple(c - cells[0] for c in cells)
                        patterns[pattern] = patterns.get(pattern, 0) + 1
                        blocks[(bx, by)] = (cells[0], pattern)
                if len(blocks) < 8:
                    continue
                pattern, count = max(patterns.items(), key=lambda item: item[1])
                if not _entry(pattern):
                    continue                    # the cells of a block are one table entry: side by side, or one in each of
                                                # as many lists that lie the same distance apart
                share = count / len(blocks)
                if share < MIN_SHARE:
                    continue
                first = {at: offset for at, (offset, shape) in blocks.items() if shape == pattern}
                offsets = sorted(set(first.values()))
                if len(offsets) < MIN_DISTINCT:
                    continue
                step = 0
                for a, b in zip(offsets, offsets[1:]):
                    step = gcd(step, b - a)
                step = step or 1
                # One table holds at most 256 blocks. Blocks from another table (a status bar, say) are left out:
                # keep the 256 entries that most of the screen's blocks come from.
                if offsets[-1] - offsets[0] >= 256 * step:
                    start = max(offsets, key=lambda low: sum(1 for o in first.values() if low <= o < low + 256 * step))
                    first = {at: o for at, o in first.items() if start <= o < start + 256 * step}
                    offsets = sorted(set(first.values()))
                    if len(offsets) < MIN_DISTINCT:
                        continue
                    step = 0
                    for a, b in zip(offsets, offsets[1:]):
                        step = gcd(step, b - a)
                    share = len(first) / len(blocks)
                found.append(Grid(w, h, left, top, pattern, step or 1, share, first))
    if not found:
        return None
    # The true block size is the one most of the screen follows. A larger size is taken only when it is followed
    # nearly as widely: two blocks that happen to be neighbours in the table also look like one block twice the size.
    top_share = max(grid.share for grid in found)
    return max((grid for grid in found if grid.share >= 0.9 * top_share), key=lambda grid: (grid.width * grid.height, grid.share))


def runs(grid: Grid, column: int, row: int) -> list:
    """Runs of neighbouring blocks through one block: [('row' or 'column', index of the block in the run, [numbers])]."""
    out = []
    for name, dx, dy in (('row', 1, 0), ('column', 0, 1)):
        start = [column, row]
        while grid.number(start[0] - dx, start[1] - dy) is not None:
            start[0] -= dx
            start[1] -= dy
        numbers, at = [], list(start)
        while grid.number(*at) is not None:
            numbers.append(grid.number(*at))
            at[0] += dx
            at[1] += dy
        index = (column - start[0]) + (row - start[1])
        if len(numbers) >= MIN_RUN and len(set(numbers)) >= MIN_DISTINCT:
            out.append((name, index, numbers))
    return out


def find_rows(rom: bytes, numbers: list, limit: int = 12) -> list:
    """[(file offset of the first number, value stored for number 0)] where the ROM holds these block numbers one after another.

    The table may not start at block 0 of the list, so the stored value is the
    number plus some constant; every constant is tried.
    """
    span = max(numbers)
    hits = []
    for base in range(256 - span):
        needle = bytes(number + base for number in numbers)
        at = rom.find(needle)
        while at >= 0:
            hits.append((at, base))
            if len(hits) > limit:
                return []                       # found all over the ROM: not a layout, a coincidence
            at = rom.find(needle, at + 1)
    return hits


def find_in_memory(snapshot, numbers: list, skip: int = 0, limit: int = 8) -> list:
    """[(file offset of each number's ROM byte, or None), ...] for places in the game's memory that hold these block numbers.

    Many games unpack a level into memory before drawing it. graphics_trace
    keeps, for every byte of memory, the ROM byte it came from, so a row of
    block numbers found in memory leads back to where the ROM keeps each one.
    """
    from . import provenance as pv
    out = []
    for name, domain in snapshot.domains.items():
        if domain.data is None or any(part in name for part in ('vram', 'chr', 'pal', 'cram', 'oam', 'nametable')):
            continue
        for at, base in find_rows(domain.data, numbers, limit):
            places = []
            for index in range(len(numbers)):
                tag = domain.tags[at + index]
                places.append(pv.tag_offset(tag) + skip if pv.tag_kind(tag) in (pv.RT_ROM, pv.RT_DERIVED) else None)
            if any(place is not None for place in places):
                out.append(places)
    return out


def windows(numbers: list, index: int, shortest: int = MIN_RUN) -> list:
    """Stretches of a run that include block `index`, the longest first: [(where it starts in the run, its numbers)].

    A game that builds its level from short strips (a ledge, a column of a
    door) stores each strip on its own, so the whole row is found nowhere but
    a piece of it is.
    """
    out = []
    count = len(numbers)
    for length in range(count, shortest - 1, -1):
        for start in range(max(0, index - length + 1), min(index, count - length) + 1):
            piece = numbers[start:start + length]
            if len(set(piece)) >= MIN_DISTINCT:
                out.append((start, piece))
    return out


LARGER = ((2, 2), (4, 4), (4, 2), (2, 4))


@dataclass
class Entries:
    """A table of larger blocks, found in the ROM."""
    placed: dict            # (block column, block row) -> file offset of the byte that says which block goes there
    width: int              # blocks in a larger block
    height: int
    inside: list            # (dx, dy) of each block of a larger block, in the order the table stores them
    base: int               # what the table adds to a block's number
    residue: int            # entries start at file offsets with this remainder

    def entry(self, rom: bytes, numbers: tuple):
        """File offset of the entry that holds these block numbers (in table order), or None."""
        size = self.width * self.height
        if any(not 0 <= n + self.base <= 255 for n in numbers):
            return None
        needle = bytes(n + self.base for n in numbers)
        at = rom.find(needle)
        while at >= 0:
            if at % size == self.residue:
                return at
            at = rom.find(needle, at + 1)
        return None


def find_entries(rom: bytes, grid: Grid):
    """The table of larger blocks that lays out this grid's blocks (2 by 2 blocks, say), as Entries, or None.

    The numbers of the blocks inside one larger block are looked for in the
    ROM as one table entry. A table is taken when most of the different
    larger blocks on screen are found with one constant added to the numbers.
    """
    numbers = {at: grid.number(*at) for at in grid.first}
    if len(numbers) < 16:
        return None
    span = max(numbers.values())
    columns = max(at[0] for at in numbers) + 1
    rows = max(at[1] for at in numbers) + 1
    best = None
    for w, h in LARGER:
        for order in ('rows', 'columns'):
            inside = [(dx, dy) for dy in range(h) for dx in range(w)] if order == 'rows' else [(dx, dy) for dx in range(w) for dy in range(h)]
            for top in range(h):
                for left in range(w):
                    groups = {}
                    for by in range(top, rows - h + 1, h):
                        for bx in range(left, columns - w + 1, w):
                            members = [numbers.get((bx + dx, by + dy)) for dx, dy in inside]
                            if all(m is not None for m in members):
                                groups[(bx, by)] = tuple(members)
                    kinds = sorted(set(groups.values()), key=lambda g: -len(set(g)))
                    if len(kinds) < 4 or len(set(kinds[0])) < 2:
                        continue
                    probe = kinds[:5]
                    for base in range(256 - span):
                        if any(rom.find(bytes(n + base for n in kind)) < 0 for kind in probe):
                            continue
                        where = {}
                        for kind in kinds:
                            needle = bytes(n + base for n in kind)
                            hits, at = [], rom.find(needle)
                            while at >= 0 and len(hits) < 8:
                                hits.append(at)
                                at = rom.find(needle, at + 1)
                            if hits:
                                where[kind] = hits
                        if len(where) < 0.6 * len(kinds):
                            continue
                        # entries of one table start a whole number of entries apart
                        tally = {}
                        for hits in where.values():
                            for residue in {hit % (w * h) for hit in hits}:
                                tally[residue] = tally.get(residue, 0) + 1
                        residue, count = max(tally.items(), key=lambda item: item[1])
                        if count < 0.6 * len(kinds):
                            continue
                        score = (count / len(kinds)) * w * h
                        if best is None or score > best[0]:
                            placed = {}
                            for (bx, by), kind in groups.items():
                                hit = next((hit for hit in where.get(kind, ()) if hit % (w * h) == residue), None)
                                if hit is not None:
                                    for k, (dx, dy) in enumerate(inside):
                                        placed[(bx + dx, by + dy)] = hit + k
                            best = (score, Entries(placed, w, h, inside, base, residue))
    return best[1] if best else None
