"""Super Mario Bros. (World), NES: areas, enemies, block contents, hidden blocks and where pipes lead.

Everything here was read from the game's code and proven by replaying the game (research/smb1-level-profile.md).

The game is NROM: 32 KB of program at CPU $8000-$FFFF (file offset = 16 + address - $8000).

* Which area plays: $9C13 picks the area pointer from WorldAddrOffsets $9CB4 (one byte per world) + AreaNumber into
  AreaAddrOffsets $9CBC. An area pointer is type (bits 5-6: 0 water, 1 ground, 2 underground, 3 castle) and number
  (bits 0-4); bit 7 is free (the enemy data uses it as a page flag). $9C22 turns it into the two streams: enemy data
  from $9CE0[type] + number into $9CE4 / $9D06 (low / high) and area data from $9D28[type] + number into $9D2C / $9D4E.
  It keeps the loaded area in $074E (type) and $074F (number); $0750 is only the next area a pipe or vine leads to.
* Area data ($9508): a two byte header, then two bytes per object, $FD ends. Byte 1: column (high nibble), row (low
  nibble). Byte 2: bit 7 = on the next page (once per object). Row $D with bit 6 clear selects a page. Rows 0-$B with
  bits 4-6 clear are single blocks whose low nibble picks the contents ($9B0E, $9B01, $9B19, $9B14): metatile from
  $BDE8 (bricks use the next five in areas that are not ground).
* Enemy data ($C144): two bytes per entry, $FF ends. Byte 1: column, row. Byte 2: bit 7 = next page (once per page),
  bit 6 = only in the harder levels ($06CC, set from World 5-3 on and in the second quest, $9032), bits 0-5 the enemy.
  Row $F selects a page (byte 2 & $3F) when no page flag was taken just before it. Row $E is three bytes: the area a
  pipe or vine leads to (byte 2, stored in $0750) and, when the world in byte 3's top three bits is this one, the
  page to come out on (byte 3 & $1F, stored in $0751).
* Level pieces (area objects, $9595 and the jump table at $9667): rows 0-$B with byte 2 bits 4-6 = 1-7 are the large
  pieces (1 the area style's platform or cannon, 2-4 rows of bricks, solid blocks, coins, 5-6 columns of bricks and
  solid blocks, 7 a pipe; low nibble the length), with bits 4-6 clear and low nibble 9-$B small pieces; row $C holds
  gaps, bridges and rows of ? blocks (bits 4-6 the kind, low nibble the length), row $F ropes, the castle, staircases
  and the sideways way-out pipe. The parser has three buffers ($0730-$0732, one per piece being drawn, counting down
  the columns left) and draws a piece only when the screen reaches its page ($0725) and column ($0726) exactly, so
  the stream must stay in order and no column may have more than three pieces on it (the game's own data never has
  more). Castle loops ($C08C) jump back to fixed byte offsets ($9BF8) of their areas, so there nothing may shift.
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER = 16
SHA256 = '0b3d9e1f01ed1668205bab34d6c82b0e281456e137352e4f36a9b2cfa3b66dea'

# RAM
WORLD, LEVEL, AREA_TYPE, AREA_NUMBER, NEXT_AREA, NEXT_PAGE = 0x75F, 0x75C, 0x74E, 0x74F, 0x750, 0x751
MODE, SCREEN_PAGE, SCREEN_X = 0x770, 0x71A, 0x71C
ENEMY_INDEX = 0x739                  # how far the enemy data has been read
FLAG, ID, PAGE, X, FRENZY = 0x0F, 0x16, 0x6E, 0x87, 0x6CB
BLOCKS = (0x500, 0x5D0)              # block buffers for even and odd pages: row * 16 + column

TYPES = {0: 'water', 1: 'ground', 2: 'underground', 3: 'castle'}

# Enemy numbers the game's enemy data uses. Each was spawned in World 1-1 in place of the first Goomba and looked at
# (trace/v15_profiles/smb1/enemy_types_sheet.png, spawn2_*.png, walk_*.png; lifts measured by their movement).
ENEMIES = {
    0x00: 'Green Koopa Troopa', 0x02: 'Buzzy Beetle', 0x03: 'Red Koopa Troopa', 0x05: 'Hammer Bro', 0x06: 'Goomba',
    0x07: 'Blooper', 0x0A: 'Green Cheep Cheep', 0x0C: 'Podoboo (lava fireball)', 0x0E: 'Green Koopa Paratroopa (jumping)',
    0x0F: 'Red Koopa Paratroopa', 0x10: 'Green Koopa Paratroopa (flying)', 0x11: 'Lakitu', 0x15: 'Bowser’s fire',
    0x17: 'Stream of Bullet Bills', 0x1B: 'Fire bar (clockwise)', 0x1C: 'Fast fire bar (clockwise)',
    0x1D: 'Fire bar (anticlockwise)', 0x1F: 'Long fire bar', 0x24: 'Pulley lift (one of a balanced pair)',
    0x25: 'Lift moving up and down', 0x26: 'Lift going up', 0x27: 'Lift going down', 0x28: 'Lift moving left and right',
    0x29: 'Lift that falls when stood on', 0x2A: 'Lift that moves right when stood on', 0x2B: 'Short lift going up',
    0x2C: 'Short lift going down', 0x2D: 'Bowser', 0x34: 'Warp zone', 0x35: 'Toad', 0x37: 'Two Goombas',
    0x38: 'Three Goombas', 0x39: 'Two Goombas, higher up', 0x3A: 'Three Goombas, higher up',
    0x3B: 'Two Green Koopa Troopas', 0x3C: 'Three Green Koopa Troopas',
}
# What each one does, from watching it in World 1-1 for four seconds with Mario standing still (positions every 4 frames:
# trace/v15_profiles/naming_smb/track1.py and track1.json; ledge edges: koopa1.py; a pair of pulley lifts with Mario on
# one: pulley1.py; the lifts that wait for Mario: smb1/lifts.py). The warp zone draws nothing and has no line.
DOES = {
    0x00: 'Walks along and walks off the edge of a ledge.',
    0x02: 'Walks along and walks off the edge of a ledge.',
    0x03: 'Walks along and turns back at the edge of a ledge.',
    0x05: 'Steps back and forth, jumps now and then and throws hammers at Mario.',
    0x06: 'Walks along, walks off ledges and turns back when it bumps into something.',
    0x07: 'Sinks slowly, then swims up toward Mario in quick spurts.',
    0x0A: 'Swims slowly to the left.',
    0x0C: 'Jumps high out of the lava and falls back, over and over.',
    0x0E: 'Hops along toward Mario.',
    0x0F: 'Flies slowly up and down in one place.',
    0x10: 'Flies left and right in one place.',
    0x11: 'Floats above Mario on a cloud and throws Spinies down at him.',
    0x15: 'Flies straight across the screen to the left.',
    0x17: 'Bullet Bills keep flying in from the right at different heights.',
    0x1B: 'A chain of fireballs that turns clockwise around a block.',
    0x1C: 'A chain of fireballs that turns clockwise around a block, twice as fast.',
    0x1D: 'A chain of fireballs that turns anticlockwise around a block.',
    0x1F: 'A long chain of fireballs that turns around a block.',
    0x24: 'Sinks while Mario stands on it and pulls its partner on the other side of the rope up.',
    0x25: 'Moves up and down, slowing down at each end.',
    0x26: 'Rises and comes back in at the bottom of the screen.',
    0x27: 'Sinks and comes back in at the top of the screen.',
    0x28: 'Moves left and right, slowing down at each end.',
    0x29: 'Stays still until Mario stands on it, then falls.',
    0x2A: 'Stays still until Mario stands on it, then carries him to the right.',
    0x2B: 'Rises and comes back in at the bottom of the screen.',
    0x2C: 'Sinks and comes back in at the top of the screen.',
    0x2D: 'Walks back and forth, jumps and breathes fire at Mario.',
    0x35: 'Stands still.',
    0x37: 'Walk along together toward Mario.',
    0x38: 'Walk along together toward Mario.',
    0x39: 'Walk along together toward Mario.',
    0x3A: 'Walk along together toward Mario.',
    0x3B: 'Walk along together toward Mario.',
    0x3C: 'Walk along together toward Mario.',
}
GROUPS = {0x37: 0x06, 0x38: 0x06, 0x39: 0x06, 0x3A: 0x06, 0x3B: 0x00, 0x3C: 0x00}     # $C71B: what a group spawns
GROUP_ROW = {0x37: 11, 0x38: 11, 0x39: 7, 0x3A: 7, 0x3B: 11, 0x3C: 11}                  # $C732: y $B0 or $70 (row 11 or 7)
FRENZIES = {0x15, 0x16, 0x17}                                                           # $C7A0: kept in $06CB

# What a single block holds (low nibble of byte 2), proven by jumping into 1-1's first block with each value
# (trace/v15_profiles/smb1/block_contents_sheet.png, blocks.json)
CONTENTS = {0: 'Question block with a power-up', 1: 'Question block with a coin', 2: 'Hidden block with a coin',
            3: 'Hidden block with a 1-up', 4: 'Brick with a power-up', 5: 'Brick with a vine', 6: 'Brick with a star',
            7: 'Brick with several coins', 8: 'Brick with a 1-up'}
HOLDS = {0: 'a power-up', 1: 'a coin', 2: 'a coin', 3: 'a 1-up', 4: 'a power-up', 5: 'a vine', 6: 'a star',
         7: 'several coins', 8: 'a 1-up'}
HIDDEN = {2, 3}

# Level pieces. Every kind was drawn at World 1-1 page 0 column 10 and looked at (trace/v15_profiles/smb_layout/
# kinds1.py, kinds1_sheet.png); the platform of kind 1 follows the area's style (header byte 2 bits 6-7).
STYLE_PIECES = {0: 'Treetop platform', 1: 'Mushroom platform', 2: 'Bullet Bill cannon'}
LARGE = {0x20: 'Row of bricks', 0x30: 'Row of solid blocks', 0x40: 'Row of coins', 0x50: 'Column of bricks',
         0x60: 'Column of solid blocks', 0x70: 'Pipe', 0x78: 'Pipe Mario can go down'}
SMALL = {9: 'Short pipe, one block wide', 10: 'Used block', 11: 'Springboard'}
ROW12 = {0x00: 'Gap in the ground', 0x10: 'Pulley rope', 0x20: 'Bridge (high)', 0x30: 'Bridge (middle)',
         0x40: 'Bridge (low)', 0x50: 'Gap filled with water', 0x60: 'Row of ? blocks with coins (high)',
         0x70: 'Row of ? blocks with coins (low)'}
ROW15 = {0x00: 'Rope from top to bottom', 0x10: 'Rope of a balanced lift', 0x20: 'Castle', 0x30: 'Staircase',
         0x40: 'Sideways pipe out of the area'}
BUFFERS = 3                          # $0730-$0732: pieces the parser can draw at once
NAMETABLE_ROW = 4                    # metatile row 0 is tile row 4 of the nametable (32 pixels down)


class SMB1Data:
    """Reads the game's area tables and object streams."""
    WORLDS = 0x9CB4
    AREAS = 0x9CBC
    ENEMY_START, ENEMY_LOW, ENEMY_HIGH = 0x9CE0, 0x9CE4, 0x9D06
    AREA_START, AREA_LOW, AREA_HIGH = 0x9D28, 0x9D2C, 0x9D4E
    METATILES = 0xBDE8

    def __init__(self, rom: bytes):
        self.rom = rom

    @staticmethod
    def offset(address: int) -> int:
        return HEADER + address - 0x8000

    def at(self, address: int) -> int:
        return self.rom[self.offset(address)]

    # ---- areas
    def area_count(self) -> list:
        """How many areas of each type the game has (from where each type starts in the pointer tables)."""
        starts = [self.at(self.AREA_START + t) for t in range(4)] + [self.AREA_HIGH - self.AREA_LOW]
        order = sorted(range(4), key=lambda t: starts[t])
        counts = [0] * 4
        for i, t in enumerate(order):
            following = starts[order[i + 1]] if i + 1 < 4 else starts[4]
            counts[t] = following - starts[t]
        return counts

    def all_areas(self) -> list:
        return [t << 5 | n for t, count in enumerate(self.area_count()) for n in range(count)]

    def area_data(self, area: int) -> int:
        i = self.at(self.AREA_START + ((area >> 5) & 3)) + (area & 0x1F)
        return self.at(self.AREA_LOW + i) | self.at(self.AREA_HIGH + i) << 8

    def enemy_data(self, area: int) -> int:
        i = self.at(self.ENEMY_START + ((area >> 5) & 3)) + (area & 0x1F)
        return self.at(self.ENEMY_LOW + i) | self.at(self.ENEMY_HIGH + i) << 8

    def world_areas(self) -> list:
        """[[area pointer for each AreaNumber] for each world]."""
        starts = [self.at(self.WORLDS + w) for w in range(8)]
        ends = starts[1:] + [self.ENEMY_START - self.AREAS]       # the area list runs up to the next table
        return [[self.at(self.AREAS + i) & 0x7F for i in range(a, b)] for a, b in zip(starts, ends)]

    def levels(self) -> dict:
        """{(world, level): (main area, way-in area or None)}, both counted from 1. A world with five areas has a short
        way-in area before its second level (the pipe the player walks into)."""
        out = {}
        for w, areas in enumerate(self.world_areas()):
            if len(areas) == 5:
                out[(w + 1, 1)] = (areas[0], None)
                out[(w + 1, 2)] = (areas[2], areas[1])
                out[(w + 1, 3)] = (areas[3], None)
                out[(w + 1, 4)] = (areas[4], None)
            else:
                for level, area in enumerate(areas[:4]):
                    out[(w + 1, level + 1)] = (area, None)
        return out

    @staticmethod
    def hard(world: int, level: int) -> bool:
        """$9032 (first quest): entries marked for the harder levels appear from World 5-3 on."""
        return world > 5 or (world == 5 and level >= 3)

    # ---- streams
    def objects(self, area: int) -> list:
        """Area objects ($9508): [{'index', 'byte' (file offset of byte 1), 'page', 'col', 'row', 'value'}]."""
        start, i, page, taken, out = self.area_data(area), 2, 0, False, []
        while i < 0x400:
            b0 = self.at(start + i)
            if b0 == 0xFD:
                break
            b1 = self.at(start + i + 1)
            if b1 & 0x80 and not taken:
                page, taken = page + 1, True
            if b0 & 15 == 13 and not b1 & 0x40 and not taken:
                page = b1 & 0x1F
            else:
                out.append({'index': i, 'byte': self.offset(start + i), 'page': page, 'col': b0 >> 4, 'row': b0 & 15,
                            'value': b1 & 0x7F})
            taken = False
            i += 2
        return out

    def enemies(self, area: int, data: bytes = None) -> list:
        """Enemy data ($C144). [{'kind': 'enemy'|'way'|'page', 'index', 'byte', 'page', 'col', 'row', ...}]. `data`
        reads a changed copy of the stream instead (to check an edit)."""
        start = self.enemy_data(area)
        read = (lambda k: data[k]) if data is not None else (lambda k: self.at(start + k))
        i, page, taken, out = 0, 0, False, []
        while i < 0x200:
            b0 = read(i)
            if b0 == 0xFF:
                break
            b1 = read(i + 1)
            if b1 & 0x80 and not taken:
                page, taken = page + 1, True
            row = b0 & 15
            base = {'index': i, 'byte': self.offset(start + i), 'page': page, 'col': b0 >> 4, 'row': row}
            if row == 15 and not taken:
                page, taken = b1 & 0x3F, True
                out.append({**base, 'kind': 'page', 'page': page})
                i += 2
                continue
            if row == 14:
                b2 = read(i + 2)
                out.append({**base, 'kind': 'way', 'to': b1 & 0x7F, 'world': b2 >> 5, 'at': b2 & 0x1F})
                i += 3
            else:
                out.append({**base, 'kind': 'enemy', 'id': b1 & 0x3F, 'hard': bool(b1 & 0x40)})
                i += 2
            taken = False
        return out

    def enemy_stream(self, area: int) -> bytes:
        start, rows = self.enemy_data(area), self.enemies(area)
        end = (rows[-1]['index'] + (3 if rows[-1]['kind'] == 'way' else 2)) if rows else 0
        return bytes(self.at(start + k) for k in range(end + 1))

    def metatile(self, contents: int, area_type: int) -> int:
        """The metatile the game puts in the block buffer for a single block ($9B0E-$9B2C)."""
        index = contents if contents in (0, 1, 2) or (contents == 3 and area_type == 1) else contents + (0 if area_type == 1 else 5)
        return self.at(self.METATILES + index)

    # ---- edits
    def remove_writes(self, area: int, index: int) -> list:
        """Writes that take an enemy out of the data without moving anything: its two bytes become a page select for
        the page the next entry is on, so every other entry keeps its page. Checked by reading the stream again; [] when
        that cannot be done here."""
        rows = self.enemies(area)
        at = next((k for k, r in enumerate(rows) if r['index'] == index and r['kind'] == 'enemy'), None)
        if at is None:
            return []
        later = rows[at + 1] if at + 1 < len(rows) else None
        page = later['page'] if later else rows[at]['page']
        if page > 0x3F:
            return []
        old = self.enemy_stream(area)
        new = bytearray(old)
        new[index], new[index + 1] = (old[index] & 0xF0) | 0x0F, page
        before = [r for r in rows if r['index'] != index and r['kind'] != 'page']
        after = [r for r in self.enemies(area, bytes(new)) if r['kind'] != 'page']
        strip = lambda r: {k: v for k, v in r.items() if k != 'byte'}
        if [strip(r) for r in before] != [strip(r) for r in after]:
            return []
        byte = rows[at]['byte']
        return [(byte + k, old[index + k], new[index + k]) for k in (0, 1) if old[index + k] != new[index + k]]

    # ---- level pieces (area objects)
    STAIR_COUNT, STAIR_ROW = 0x9AA5, 0x9AAE     # staircase columns: rows drawn and first row, read backwards from 8

    def tokens(self, area: int, data: bytes = None) -> list:
        """The area data as the parser reads it ($9508): [{'kind': 'page'|'object', 'index', 'byte', 'page', 'col',
        'row', 'value' (byte 2 without bit 7), 'flag' (bit 7)}]. `data` reads a changed copy (from byte 0 of the area)."""
        start = self.area_data(area)
        read = (lambda k: data[k]) if data is not None else (lambda k: self.at(start + k))
        i, page, out = 2, 0, []
        while i < 0x400:
            b0 = read(i)
            if b0 == 0xFD:
                break
            b1 = read(i + 1)
            taken = bool(b1 & 0x80)
            if taken:
                page += 1
            row = b0 & 15
            base = {'index': i, 'byte': self.offset(start + i), 'col': b0 >> 4, 'row': row, 'value': b1 & 0x7F, 'flag': taken}
            if row == 13 and not b1 & 0x40 and not taken:
                page = b1 & 0x1F
                out.append({**base, 'kind': 'page', 'page': page})
            else:
                out.append({**base, 'kind': 'object', 'page': page})
            i += 2
        return out

    def area_bytes(self, area: int) -> bytes:
        start = self.area_data(area)
        end = 2
        while self.at(start + end) != 0xFD and end < 0x400:
            end += 2
        return bytes(self.at(start + k) for k in range(end + 1))

    def style(self, area: int) -> int:
        """The area's platform style (header byte 2 bits 6-7; 3 is the cloud setting, which keeps style 0)."""
        value = self.at(self.area_data(area) + 1) >> 6
        return 0 if value == 3 else value

    def looping(self, area: int) -> bool:
        """Does the area hold a loop command (row $D, $4B)? Those jump back to fixed byte offsets of the area data."""
        return any(t['row'] == 13 and t['kind'] == 'object' and t['value'] & 0x3F == 0x0B for t in self.tokens(area))

    def piece(self, row: int, value: int, style: int):
        """What an area object is: {'group', 'kind' (the value that names it), 'name', 'size' (length field or None),
        'sizes' (choices), 'width' (parser columns it takes), 'cells' [(column, row)] it draws} or None for objects
        that are not pieces (single blocks with contents, page selects, scenery and level controls)."""
        t, n = (value >> 4) & 7, value & 15
        cells, size, sizes = None, None, None
        if row <= 11:
            if t == 0:
                if n not in SMALL:
                    return None
                group, kind, name, width = 'small', n, SMALL[n], 1
                cells = [(0, row), (0, row + 1)] if n in (9, 11) else [(0, row)]
            elif t == 1:
                group, kind, name = 'large', 0x10, STYLE_PIECES[style]
                size, sizes = n, range(16)
                if style == 2:
                    width, cells, sizes = 1, [(0, row + j) for j in range(n + 1)], range(13 - row) if row < 12 else range(1)
                else:
                    width, cells = n + 1, [(i, row) for i in range(n + 1)]
            elif t == 7:
                kind = 0x78 if n & 8 else 0x70
                group, name, width, size, sizes = 'large', LARGE[kind], 2, n & 7, range(1, 8)
                cells = [(i, row + j) for i in (0, 1) for j in range((n & 7) + 1)]
            else:
                group, kind, name, size, sizes = 'large', t << 4, LARGE[t << 4], n, range(16)
                if t in (2, 3, 4):
                    width, cells = n + 1, [(i, row) for i in range(n + 1)]
                else:
                    width, cells, sizes = 1, [(0, row + j) for j in range(n + 1)], range(max(1, 13 - row))
        elif row == 12:
            group, kind, name, width, size, sizes = 'row12', t << 4, ROW12[t << 4], n + 1, n, range(16)
            rows = {0: range(8, 13), 1: [0], 2: [6, 7], 3: [7, 8], 4: [9, 10], 5: range(10, 13), 6: [3], 7: [7]}[t]
            cells = [(i, r) for i in range(n + 1) for r in rows]
        elif row == 15:
            if (t << 4) not in ROW15:
                return None
            group, kind, name = 'row15', t << 4, ROW15[t << 4]
            if t == 0:
                width, cells = 1, [(0, r) for r in range(13)]
            elif t == 1:
                width, size, sizes, cells = 1, n, range(12), [(0, r) for r in range(1, min(n + 2, 13))]
            elif t == 2:
                width, cells = 5, [(i, r) for i in range(5) for r in range(n, 11)]
            elif t == 3:
                width, size, sizes = n + 1, n, range(9)
                cells = []
                for k in range(n + 1):
                    step = 8 - k if k <= 8 else 0
                    first, count = self.at(self.STAIR_ROW + step), self.at(self.STAIR_COUNT + step) + 1
                    cells += [(k, r) for r in range(first, min(first + count, 13))]
            else:
                width = 4
                cells = [(i, r) for i in (0, 1) for r in (n - 1, n) if r >= 0] + [(i, r) for i in (2, 3) for r in range(n + 1)]
        else:
            return None
        cells = [(c, r) for c, r in cells if 0 <= r <= 12]
        if sizes is not None:
            sizes = sorted(set(sizes) | {size})
        return {'group': group, 'kind': kind, 'name': name, 'size': size, 'sizes': sizes,
                'width': width, 'cells': cells}

    @staticmethod
    def parser_width(row: int, value: int, style: int) -> int:
        """Parser columns an area object keeps one of the three buffers busy ($0730,X counts them down; handlers that
        call $9BAC take the low nibble, $9BAF a fixed number, the rest only their own column)."""
        t, n = (value >> 4) & 7, value & 15
        if row <= 11:
            if t == 0 or t in (5, 6) or (t == 1 and style == 2):
                return 1
            return 2 if t == 7 else n + 1
        if row == 12:
            return n + 1
        if row == 13:
            return {0: 4, 4: 13}.get(value & 0x3F, 1)       # $9882 the pipe into the level, $9A01 the castle bridge
        if row == 15:
            return {2: 5, 3: n + 1, 4: 4}.get(t, 1)
        return 1

    def encode(self, area: int, sequence: list):
        """Bytes of the area data for a sequence of tokens (objects with absolute pages, page selects as they are), or
        None when a page cannot be reached with the page flag (every object may move on one page from the one before)."""
        out = bytearray(self.area_bytes(area)[:2])
        state = 0
        for t in sequence:
            if t['kind'] == 'page':
                out += bytes([t['col'] << 4 | 13, t['page']])
                state = t['page']
                continue
            step = t['page'] - state
            if step not in (0, 1):
                return None
            out += bytes([t['col'] << 4 | t['row'], t['value'] | (0x80 if step else 0)])
            state = t['page']
        return bytes(out + b'\xFD')

    def _cover(self, area: int, skip_index=None) -> dict:
        style, cover = self.style(area), {}
        for t in self.tokens(area):
            if t['kind'] == 'object' and t['index'] != skip_index:
                x = t['page'] * 16 + t['col']
                for k in range(self.parser_width(t['row'], t['value'], style)):
                    cover[x + k] = cover.get(x + k, 0) + 1
        return cover

    def place(self, area: int, index: int, page: int, col: int, row: int, value: int):
        """Writes that put the area object at `index` at page/column/row with byte 2 `value`, every other object staying
        exactly where it is (the stream is reordered when the object passes others). Returns (writes, reason): reason is
        a plain sentence when it cannot be done."""
        tokens = self.tokens(area)
        j = next((k for k, t in enumerate(tokens) if t['index'] == index and t['kind'] == 'object'), None)
        if j is None:
            return None, 'That is not part of this level any more. Reopen the map.'
        if not 0 <= page <= 0x1F or not 0 <= col <= 15:
            return None, 'That place is outside what the level can hold.'
        style = self.style(area)
        cover = self._cover(area, index)
        x = page * 16 + col
        if any(cover.get(x + k, 0) >= BUFFERS for k in range(self.parser_width(row, value, style))):
            return None, 'The game draws at most three level pieces on one column, and that place already has three.'
        moved = {**tokens[j], 'page': page, 'col': col, 'row': row, 'value': value}
        others = tokens[:j] + tokens[j + 1:]
        key = (page, col)
        before = [k for k, t in enumerate(others) if t['kind'] == 'object' and (t['page'], t['col']) > key]
        after = [k for k, t in enumerate(others) if t['kind'] == 'object' and (t['page'], t['col']) < key]
        low = after[-1] + 1 if after else 0
        high = before[0] if before else len(others)
        old = self.area_bytes(area)
        loop = self.looping(area)
        spots = sorted(range(low, high + 1), key=lambda k: (k != j, abs(k - j)))
        for k in spots:
            data = self.encode(area, others[:k] + [moved] + others[k:])
            if data is None or len(data) != len(old):
                continue
            writes = [(self.offset(self.area_data(area) + i), old[i], data[i]) for i in range(len(old)) if old[i] != data[i]]
            if loop and any(not index <= w[0] - self.offset(self.area_data(area)) <= index + 1 for w in writes):
                continue
            return writes, None
        if loop:
            return None, ('This castle loops back to fixed places in its layout, so a piece can only move where nothing '
                          'else has to change.')
        return None, ('The layout cannot hold that place: the pieces just before and after it would need another '
                      'screen jump the level has no room for.')

    def x_choices(self, area: int, index: int, row: int, value: int, near: int = None) -> list:
        """Every column (page * 16 + column) the object can be put at with place(), worked out without writing; with
        `near`, only on its own screen and the screens either side of it that far."""
        tokens = self.tokens(area)
        j = next(k for k, t in enumerate(tokens) if t['index'] == index)
        style = self.style(area)
        width = self.parser_width(row, value, style)
        cover = self._cover(area, index)
        last = max([t['page'] for t in tokens] + [0])
        loop = self.looping(area)
        others = tokens[:j] + tokens[j + 1:]
        # page state before each position of `others`, and whether the token at each position can follow a given page
        states, state = [], 0
        for t in others:
            states.append(state)
            state = t['page']
        states.append(state)
        objects = [(k, (t['page'], t['col'])) for k, t in enumerate(others) if t['kind'] == 'object']
        out = []
        first, end = 0, (last + 1) * 16
        if near is not None:
            first, end = max(0, (tokens[j]['page'] - near) * 16), min(end, (tokens[j]['page'] + near + 1) * 16)
        for x in range(first, end):
            page, col = divmod(x, 16)
            if (page, col) == (tokens[j]['page'], tokens[j]['col']):
                out.append(x)
                continue
            if any(cover.get(x + k, 0) >= BUFFERS for k in range(width)):
                continue
            low = max([k + 1 for k, p in objects if p < (page, col)] + [0])
            high = min([k for k, p in objects if p > (page, col)] + [len(others)])
            for k in range(low, high + 1):
                if loop and k != j:
                    continue
                if page - states[k] not in (0, 1):
                    continue
                follow = others[k] if k < len(others) else None
                if follow and follow['kind'] == 'object' and follow['page'] - page not in (0, 1):
                    continue
                if loop and follow and follow['kind'] == 'object' and follow['page'] - page != int(follow['flag']):
                    continue
                hole = others[j] if j < len(others) else None       # what followed the object where it was
                if k != j and hole and hole['kind'] == 'object':
                    if hole['page'] - (tokens[j - 1]['page'] if j > 0 else 0) not in (0, 1):
                        continue
                out.append(x)
                break
        return out

    def remove_piece(self, area: int, index: int) -> list:
        """Writes that take an area object out without moving anything: its two bytes become a page select for the page
        it was on, so the objects after it keep their pages and every byte keeps its place."""
        t = next((t for t in self.tokens(area) if t['index'] == index and t['kind'] == 'object'), None)
        if t is None:
            return []
        byte = t['byte']
        new = (t['col'] << 4 | 13, t['page'])
        return [(byte + k, self.rom[byte + k], new[k]) for k in (0, 1) if self.rom[byte + k] != new[k]]


def _list(names: list) -> str:
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]


class _EnemyWatcher(Watcher):
    """An enemy edit: once the game has read past the entry ($0739) in that area, which enemy appeared where it is."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.passed = None
        self.seen = []
        self.done = False

    def see(self, ram, frame, run):
        w = self.w
        if ram[MODE] != 1 or (ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]) != w['area'] or ram[WORLD] != w['world'] - 1:
            return False
        if ram[ENEMY_INDEX] <= w['index']:
            return self.passed is not None and frame - self.passed > 16
        if self.passed is None:
            self.passed = frame
        reach = 96 if w['wanted'] in GROUPS else 6
        for slot in range(6):
            if ram[FLAG + slot]:
                where = ram[PAGE + slot] * 256 + ram[X + slot]
                if abs(where - w['x']) <= reach:
                    self.seen.append(ram[ID + slot])
        if w['wanted'] in FRENZIES and ram[FRENZY]:
            self.seen.append(ram[FRENZY])
        return frame - self.passed > 16

    def result(self):
        w = self.w
        if self.passed is None:
            return super().result()
        wanted = w['wanted']
        if wanted is None:
            ok = not self.seen
            return {'state': 'good' if ok else 'bad',
                    'text': 'Played from the start, no enemy appears there any more.' if ok
                    else f'Played from the start, an enemy (number {self.seen[0]:#04x}) still appears there.'}
        spawns = {GROUPS.get(wanted, wanted)}
        if GROUPS.get(wanted, wanted) == 0x06:
            spawns.add(0x02)            # the second quest turns Goombas into Buzzy Beetles
        ok = any(s in spawns for s in self.seen)
        if ok:
            return {'state': 'good', 'text': f'Played from the start, the game now puts {w["name"]} there.'}
        if self.seen:
            return {'state': 'bad', 'text': f'Played from the start, the game put enemy number {self.seen[0]:#04x} there, not the one chosen.'}
        return {'state': 'bad', 'text': 'Played from the start, the game read that entry but nothing chosen appeared there.'}


class _BlockWatcher(Watcher):
    """A block edit: the metatile the game builds into its block buffer for that spot once the spot is on screen."""
    every = 4

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if ram[MODE] != 1 or (ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]) != w['area'] or ram[WORLD] != w['world'] - 1:
            return False
        left = ram[SCREEN_PAGE] * 256 + ram[SCREEN_X]
        x = w['page'] * 256 + w['col'] * 16
        if not left <= x <= left + 240:
            return False
        self.seen = ram[BLOCKS[w['page'] & 1] + w['row'] * 16 + w['col']]
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if self.seen == w['metatile']:
            return {'state': 'good', 'text': f'Played from the start, the game builds the block as chosen: {w["name"].lower()}.'}
        if self.seen == 0xC4 and w['metatile'] != 0xC4:
            return {'state': 'warn', 'text': 'Played from the start, the block had already been hit when it came on screen, so what it holds could not be seen.'}
        text = f'Played from the start, the game built a different block there (metatile {self.seen:#04x}).'
        if w['contents'] == 3:
            text += ' The game only shows a hidden 1-up block while its 1-up flag is set.'
        return {'state': 'bad', 'text': text}


def nametable_tiles(vram, column: int, row: int):
    """The four tiles the game drew for the metatile at an area column (page * 16 + column) and row: nametable page & 1
    (the two nametables side by side), tile row row * 2 + 4."""
    base = (column >> 4 & 1) * 0x400 + (row * 2 + NAMETABLE_ROW) * 32 + (column & 15) * 2
    return (vram[base], vram[base + 1], vram[base + 32], vram[base + 33])


class _PieceWatcher(Watcher):
    """A level piece edit: plays the original game, then the changed one, and reads what the game drew in its nametable
    at every place the piece covered and now covers, each when it first comes on screen. The piece must be gone from
    where it no longer is, drawn where it now is, and (when it only moved) drawn the same as it was."""
    every = 4
    compare = True
    SETTLE = 8

    def __init__(self, watch):
        self.w = watch
        self.runs = {}
        self.since = {}

    def see(self, ram, frame, run):
        w = self.w
        seen = self.runs.setdefault(run, {})
        if ram[MODE] != 1 or (ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]) != w['area'] or ram[WORLD] != w['world'] - 1:
            self.since.pop(run, None)
            return False
        start = self.since.setdefault(run, frame)
        vram = getattr(ram, 'domains', {}).get('vram')
        if vram is None or frame - start < self.SETTLE:
            return False
        left = ram[SCREEN_PAGE] * 256 + ram[SCREEN_X]
        cells = {tuple(c) for c in w['old']} | {tuple(c) for c in w['new']}
        for column, row in cells:
            if (column, row) not in seen and left <= column * 16 <= left + 240:
                seen[(column, row)] = nametable_tiles(vram, column, row)
        return len(seen) == len(cells)

    def result(self):
        w = self.w
        before, after = self.runs.get('original', {}), self.runs.get('changed', {})
        both = lambda c: c in before and c in after
        changed = lambda c: both(c) and before[c] != after[c]
        skip = {tuple(c) for c in w.get('skip', [])}       # drawn by other pieces too, so they tell nothing
        old, new = [tuple(c) for c in w['old'] if tuple(c) not in skip], [tuple(c) for c in w['new'] if tuple(c) not in skip]
        gone = [c for c in old if c not in new and both(c)]
        there = [c for c in new if c not in old and both(c)]
        name = w['name']
        if old and not new:
            if not gone:
                return super().result()
            ok = any(changed(c) for c in gone)
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the game no longer draws the {name} there.' if ok else
                            f'Played from the start, the game still draws the {name} there.'}
        if set(old) == set(new) or not w.get('moved', True):
            measured = [c for c in set(old) | set(new) if both(c)]
            if not measured:
                return super().result()
            ok = any(changed(c) for c in measured)
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the game now draws the {w["now"]} there.' if ok else
                            f'Played from the start, the game still draws the {name} there.'}
        if (set(old) - set(new) and not gone) or (set(new) - set(old) and not there):
            return super().result()
        problems = []
        if gone and not any(changed(c) for c in gone):
            problems.append('it is still drawn where it was')
        if there and not any(changed(c) for c in there):
            problems.append('nothing new is drawn where it now is')
        if w.get('shift') and not problems:
            dx, dy = w['shift']
            pairs = [(c, (c[0] + dx, c[1] + dy)) for c in old if c in before and (c[0] + dx, c[1] + dy) in after
                     and (c[0] + dx, c[1] + dy) not in skip]
            telling = [(a, b) for a, b in pairs if b in before and before[a] != before[b]]
            if any(after[b] != before[a] for a, b in telling):
                problems.append('it does not look the same at its new place')
        if problems:
            return {'state': 'bad', 'text': f'Played from the start, the {name} did not change as chosen: ' + ' and '.join(problems) + '.'}
        return {'state': 'good', 'text': f'Played from the start, the game now draws the {w["now"]} where chosen' +
                (' and no longer where it was.' if gone else '.')}


class _WayWatcher(Watcher):
    """A pipe target edit: once the game has read the entry, the area ($0750) and page ($0751) a pipe or vine now leads to."""
    every = 4

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if ram[MODE] != 1 or (ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]) != w['area'] or ram[WORLD] != w['world'] - 1:
            return False
        if ram[ENEMY_INDEX] <= w['index']:
            return False
        self.seen = (ram[NEXT_AREA] & 0x7F, ram[NEXT_PAGE])
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if self.seen == (w['to'], w['at']):
            return {'state': 'good', 'text': f'Played from the start, the game now sends pipes and vines here to {w["name"]}.'}
        return {'state': 'bad', 'text': f'Played from the start, pipes and vines here still lead to area {self.seen[0]:#04x}, screen {self.seen[1] + 1}.'}


class SMB1Profile(SMB1Data, Profile):
    """Super Mario Bros. on the common profile interface. Parts are {'world', 'level', 'area'} (world and level counted
    from 1, area = the area pointer without bit 7); x is the screen's left edge in the area's pixels ($071A/$071C)."""
    name = 'Super Mario Bros.'
    sha256s = (SHA256,)

    def __init__(self, rom: bytes):
        SMB1Data.__init__(self, rom)
        self._levels = None

    # ---- where
    def where(self, ram):
        if ram[MODE] != 1:
            return None
        world, level = ram[WORLD] + 1, ram[LEVEL] + 1
        if not 1 <= world <= 8 or not 1 <= level <= 4 or ram[AREA_TYPE] > 3:
            return None
        return {'part': {'world': world, 'level': level, 'area': ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]},
                'x': ram[SCREEN_PAGE] * 256 + ram[SCREEN_X], 'y': 8}

    def level_table(self) -> dict:
        if self._levels is None:
            self._levels = self.levels()
        return self._levels

    def area_title(self, area: int) -> str:
        """A name for an area from the levels that use it."""
        mains = [f'{w}-{l}' for (w, l), (main, _) in sorted(self.level_table().items()) if main == area]
        if mains:
            return f'World {_list(mains)}'
        ways = [f'{w}-{l}' for (w, l), (_, way) in sorted(self.level_table().items()) if way == area]
        if ways:
            return f'the way into World {_list(ways)}'
        return f'{TYPES[(area >> 5) & 3].capitalize()} side area {area & 0x1F}'

    def part_name(self, part):
        world, level, area = int(part['world']), int(part['level']), int(part['area'])
        main, way = self.level_table().get((world, level), (None, None))
        name = f'World {world}-{level}'
        if area == main:
            return name
        if area == way:
            return name + ', the way in'
        title = self.area_title(area)
        return name + (f', in the area of {title}' if title.startswith('World') else ', ' + title[0].lower() + title[1:])

    # ---- objects
    def choices(self):
        ways, seen = [], set()
        for area in self.all_areas():
            for row in self.enemies(area):
                if row['kind'] == 'way' and (row['to'], row['at']) not in seen:
                    seen.add((row['to'], row['at']))
        for to, at in sorted(seen):
            title = self.area_title(to)
            ways.append({'value': to << 5 | at, 'name': f'{title[0].upper() + title[1:]}, screen {at + 1}'})
        return {'enemies': [{'value': k, 'name': v} for k, v in sorted(ENEMIES.items(), key=lambda kv: kv[1])],
                'blocks': [{'value': k, 'name': v} for k, v in CONTENTS.items()],
                'ways': ways}

    @staticmethod
    def enemy_name(kind: int) -> str:
        return ENEMIES.get(kind, f'Enemy {kind:#04x}')

    def _here(self, part):
        world, level, area = int(part['world']), int(part['level']), int(part['area'])
        if area not in self.all_areas():
            raise ValueError('That part of the game is not one ROMancer knows.')
        return world, level, area

    def objects(self, part):
        world, level, area = self._here(part)
        hard, out = self.hard(world, level), []
        rows = self.enemies(area)
        pipes = [o for o in self.objects_raw(area) if self._enterable(o)]
        for row in rows:
            if row['kind'] == 'enemy':
                if row['hard'] and not hard:
                    continue
                notes = []
                if row['hard']:
                    notes.append('This enemy appears only in the harder levels (from World 5-3 on, and in the second quest).')
                if GROUPS.get(row['id'], row['id']) == 0x06:
                    notes.append('In the second quest the game turns Goombas into Buzzy Beetles.')
                if row['id'] in GROUPS:
                    notes.append('A group appears at the right edge of the screen when the game reads it, a little before this spot.')
                removable = bool(self.remove_writes(area, row['index']))
                if not removable:
                    notes.append('This one cannot be removed without moving other enemies, so it can only be swapped.')
                item = {'id': f'enemy:{row["index"]}', 'style': 'enemy', 'type': row['id'], 'name': self.enemy_name(row['id']),
                        'x': row['page'] * 256 + row['col'] * 16 + 8, 'y': 32 + GROUP_ROW.get(row['id'], row['row']) * 16,
                        'fields': [{'key': 'kind', 'label': 'Swap for', 'value': row['id'], 'choices': 'enemies'}],
                        'remove': 'Remove this enemy' if removable else None}
                if notes:
                    item['note'] = ' '.join(notes)
                if row['id'] in DOES:
                    item['does'] = DOES[row['id']]
                out.append(item)
            elif row['kind'] == 'way' and row['world'] == world - 1:
                start = row['page'] * 256 + row['col'] * 16
                later = [w for w in rows if w['kind'] == 'way' and w['world'] == world - 1 and w['index'] > row['index']]
                end = later[0]['page'] * 256 + later[0]['col'] * 16 if later else 1 << 16
                pipe = next((p for p in pipes if start - 64 <= p['page'] * 256 + p['col'] * 16 < end), None)
                title = self.area_title(row['to'])
                target = f'{title}, screen {row["at"] + 1}'
                item = {'id': f'way:{row["index"]}', 'style': 'secret', 'type': 'way',
                        'name': 'Where this pipe leads' if pipe else 'Where pipes and vines lead',
                        'detail': f'to {target[0].lower() + target[1:] if not target.startswith("World") else target}',
                        'fields': [{'key': 'to', 'label': 'Leads to', 'value': row['to'] << 5 | row['at'], 'choices': 'ways'}],
                        'remove': None,
                        'note': 'The game uses the last of these it has read for every pipe and vine that leads somewhere, '
                                'so this one counts from here until the next one.'}
                if pipe:
                    # a vertical pipe: its top; the sideways way-out pipe: its opening, which stands on the floor
                    top = 32 + pipe['row'] * 16 if pipe['row'] <= 11 else 208
                    item.update(x=pipe['page'] * 256 + pipe['col'] * 16 + 16, y=top)
                else:
                    item.update(x=start + 8, y=48)
                out.append(item)
        for obj in self.objects_raw(area):
            if obj['row'] > 11 or obj['value'] & 0x70 or obj['value'] > 8:
                continue
            n = obj['value']
            item = {'id': f'block:{obj["index"]}', 'style': 'secret' if n in HIDDEN else 'item', 'type': f'block{n}',
                    'name': CONTENTS[n].split(' with ')[0], 'detail': f'holds {HOLDS[n]}',
                    'x': obj['page'] * 256 + obj['col'] * 16 + 8, 'y': 48 + obj['row'] * 16,
                    'fields': [{'key': 'holds', 'label': 'Block', 'value': n, 'choices': 'blocks'}] + self._place_fields(area, obj, n),
                    'remove': 'Remove this block'}
            notes = []
            if n == 3:
                notes.append('The game shows a hidden 1-up block only while its 1-up flag is set: at the start of a game '
                             'or a world, or after enough coins in the level before.')
            if n == 5:
                notes.append('The vine climbs to where this area’s pipes and vines lead.')
            if notes:
                item['note'] = ' '.join(notes)
            out.append(item)
        style = self.style(area)
        for obj in self.objects_raw(area):
            info = self.piece(obj['row'], obj['value'], style)
            if info is None:
                continue
            columns = max(c for c, _ in info['cells']) + 1 if info['cells'] else 1
            bottom = max(r for _, r in info['cells']) if info['cells'] else obj['row']
            item = {'id': f'piece:{obj["index"]}', 'style': 'block', 'type': f'piece{obj["row"] if obj["row"] > 11 else 0}-{info["kind"]}',
                    'name': info['name'], 'x': obj['page'] * 256 + obj['col'] * 16 + columns * 8, 'y': 48 + bottom * 16,
                    'fields': self._place_fields(area, obj, obj['value']), 'remove': 'Remove this piece'}
            if info['size'] is not None:
                item['detail'] = self._size_name(info, info['size'])
                item['fields'].append({'key': 'size', 'label': self._size_label(info), 'value': info['size'],
                                       'choices': [{'value': n, 'name': self._size_name(info, n)} for n in info['sizes']]})
            kinds = self._kinds(info['group'], style)
            if len(kinds) > 1:
                item['fields'].append({'key': 'piece', 'label': 'Piece', 'value': info['kind'],
                                       'choices': [{'value': k, 'name': v} for k, v in kinds.items()]})
            notes = ['The game draws at most three pieces on one column, so places where three already meet are not offered.']
            if self.looping(area):
                notes.append('This castle loops back to fixed places in its layout, so pieces here move only where nothing else has to change.')
            if info['kind'] == 0x78:
                notes.append('Going down this pipe leads where this area’s pipes lead.')
            item['note'] = ' '.join(notes)
            out.append(item)
        return out

    # ---- level pieces on the map
    def _place_fields(self, area, obj, value) -> list:
        fields = [{'key': 'x', 'label': 'Place', 'value': obj['page'] * 16 + obj['col'],
                   'choices': [{'value': x, 'name': f'Screen {x // 16 + 1}, column {x % 16 + 1}'}
                               for x in self.x_choices(area, obj['index'], obj['row'], value, near=1)]}]
        if obj['row'] <= 11:
            fields.append({'key': 'y', 'label': 'Row', 'value': obj['row'],
                           'choices': [{'value': r, 'name': f'Row {r + 1} from the top'} for r in range(12)]})
        return fields

    @staticmethod
    def _size_label(info) -> str:
        across = info['width'] > 1 or info['group'] == 'row12' or info['kind'] == 0x30 and info['group'] == 'row15'
        return 'Length' if across and info['kind'] not in (0x70, 0x78) else 'Height'

    @staticmethod
    def _size_name(info, n) -> str:
        count = n + 1
        return f'{count} block' if count == 1 else f'{count} blocks'

    @staticmethod
    def _kinds(group, style) -> dict:
        if group == 'large':
            return {0x10: STYLE_PIECES[style], **LARGE}
        if group == 'small':
            return dict(SMALL)
        if group == 'row12':
            return dict(ROW12)
        return {}

    def objects_raw(self, area: int) -> list:
        return SMB1Data.objects(self, area)

    @staticmethod
    def _enterable(obj) -> bool:
        """A pipe the player can go down ($9604: a vertical pipe with bit 3 set) or the sideways way-out pipe (row $F, $4x)."""
        return (obj['row'] <= 11 and obj['value'] & 0x78 == 0x78) or (obj['row'] == 15 and obj['value'] & 0x70 == 0x40)

    # ---- edits
    def edit(self, part, object_id, values, remove=False):
        world, level, area = self._here(part)
        kind, _, number = str(object_id).partition(':')
        index = int(number)
        where = f'{self.part_name(part)}'
        if kind == 'enemy':
            row = next((r for r in self.enemies(area) if r['kind'] == 'enemy' and r['index'] == index), None)
            if row is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            x = row['page'] * 256 + row['col'] * 16
            if remove:
                writes = self.remove_writes(area, index)
                if not writes:
                    raise ValueError('This enemy cannot be removed without moving other enemies. Swap it for another instead.')
                return {'writes': writes, 'title': f'Remove the {self.enemy_name(row["id"])} ({where}, screen {row["page"] + 1})',
                        'watch': {'kind': 'enemy', 'area': area, 'world': world, 'index': index, 'x': x, 'wanted': None, 'name': ''}}
            new = int(values.get('kind'))
            if new not in ENEMIES:
                raise ValueError('That choice is not one of the game’s own.')
            byte = row['byte'] + 1
            old = self.rom[byte]
            value = (old & 0xC0) | new
            name = self.enemy_name(new)
            return {'writes': [(byte, old, value)] if old != value else [],
                    'title': f'Enemy here: {name} ({where}, screen {row["page"] + 1})',
                    'watch': {'kind': 'enemy', 'area': area, 'world': world, 'index': index, 'x': x, 'wanted': new,
                              'name': name if name.startswith(('Two', 'Three', 'Bowser', 'Toad')) else 'a ' + name[0].lower() + name[1:] if name.startswith(('Stream', 'Lift', 'Short', 'Long', 'Fire', 'Fast', 'Pulley', 'Warp')) else 'a ' + name}}
        if kind == 'piece':
            return self._piece_edit(world, area, index, values, remove, where)
        if kind == 'block':
            obj = next((o for o in self.objects_raw(area) if o['index'] == index), None)
            if obj is None or obj['row'] > 11 or obj['value'] & 0x70 or obj['value'] > 8:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            n = int(values.get('holds', obj['value']))
            if n not in CONTENTS:
                raise ValueError('That choice is not one of the game’s own.')
            x = int(values.get('x', obj['page'] * 16 + obj['col']))
            row = int(values.get('y', obj['row']))
            if remove or (x, row) != (obj['page'] * 16 + obj['col'], obj['row']):
                return self._piece_edit(world, area, index, {**values, 'holds': n}, remove, where)
            byte = obj['byte'] + 1
            old = self.rom[byte]
            value = (old & 0xF0) | n
            return {'writes': [(byte, old, value)] if old != value else [],
                    'title': f'Block: {CONTENTS[n].lower()} ({where}, screen {obj["page"] + 1})',
                    'watch': {'kind': 'block', 'area': area, 'world': world, 'page': obj['page'], 'col': obj['col'],
                              'row': obj['row'], 'contents': n, 'metatile': self.metatile(n, (area >> 5) & 3), 'name': CONTENTS[n]}}
        if kind == 'way':
            row = next((r for r in self.enemies(area) if r['kind'] == 'way' and r['index'] == index), None)
            if row is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            value = int(values.get('to'))
            to, at = value >> 5, value & 0x1F
            if to not in self.all_areas():
                raise ValueError('That choice is not one of the game’s own.')
            writes = []
            b1, b2 = row['byte'] + 1, row['byte'] + 2
            new1, new2 = (self.rom[b1] & 0x80) | to, (self.rom[b2] & 0xE0) | at
            for byte, new in ((b1, new1), (b2, new2)):
                if self.rom[byte] != new:
                    writes.append((byte, self.rom[byte], new))
            title = self.area_title(to)
            name = f'{title}, screen {at + 1}'
            return {'writes': writes, 'title': f'Pipes lead to {name[0].lower() + name[1:] if not name.startswith("World") else name} ({where})',
                    'watch': {'kind': 'way', 'area': area, 'world': world, 'index': index, 'to': to, 'at': at,
                              'name': name[0].lower() + name[1:] if not name.startswith('World') else name}}
        raise ValueError('ROMancer cannot change that yet.')

    def _piece_edit(self, world, area, index, values, remove, where):
        """Move, resize, change or remove a level piece (or move or remove a single block)."""
        obj = next((o for o in self.objects_raw(area) if o['index'] == index), None)
        style = self.style(area)
        if obj is None:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        single = obj['row'] <= 11 and not obj['value'] & 0x70 and obj['value'] <= 8
        info = None if single else self.piece(obj['row'], obj['value'], style)
        if not single and info is None:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        name = CONTENTS[obj['value']].split(' with ')[0].lower() if single else info['name'].lower()
        old_x = obj['page'] * 16 + obj['col']
        old_cells = [[old_x + c, r] for c, r in ([(0, obj['row'])] if single else info['cells'])]
        watch = {'kind': 'piece', 'area': area, 'world': world, 'old': old_cells, 'name': name}
        if remove:
            writes = self.remove_piece(area, index)
            watch['skip'] = self._others_cells(area, index, old_cells)
            return {'writes': writes, 'title': f'Remove the {name} ({where}, screen {obj["page"] + 1})',
                    'watch': {**watch, 'new': [], 'now': 'nothing'}}
        x, row = int(values.get('x', old_x)), int(values.get('y', obj['row']))
        if obj['row'] > 11:
            row = obj['row']
        elif not 0 <= row <= 11:
            raise ValueError('That choice is not one of the game’s own.')
        if single:
            value = int(values.get('holds', obj['value']))
            new_name = CONTENTS[value].split(' with ')[0].lower()
            new_cells = [(0, row)]
        else:
            kind = int(values.get('piece', info['kind']))
            kinds = self._kinds(info['group'], style)
            if kinds and kind not in kinds or not kinds and kind != info['kind']:
                raise ValueError('That choice is not one of the game’s own.')
            size = info['size']
            if 'size' in values and info['size'] is not None:
                size = int(values['size'])
            value = self._value(info, kind, size, obj['value'])
            new = self.piece(row, value, style)
            if new is None:
                raise ValueError('That choice is not one of the game’s own.')
            new_name, new_cells = new['name'].lower(), new['cells']
        writes, reason = self.place(area, index, x // 16, x % 16, row, value)
        if writes is None:
            raise ValueError(reason)
        parts = []
        if x != old_x:
            parts.append(f'moved to screen {x // 16 + 1}, column {x % 16 + 1}' + (f', row {row + 1}' if row != obj['row'] else ''))
        elif row != obj['row']:
            parts.append(f'moved to row {row + 1}')
        if new_name != name:
            parts.append(f'now a {new_name}')
        if not single and new['size'] is not None and new['size'] != info['size'] and info['kind'] == new['kind']:
            parts.append(f'now {self._size_name(new, new["size"])} {self._size_label(new).lower()}'.replace(' length', ' long').replace(' height', ' tall'))
        same_shape = value == obj['value']
        new_abs = [[x + c, r] for c, r in new_cells]
        watch.update(new=new_abs, now=new_name, moved=(x, row) != (old_x, obj['row']), shift=[x - old_x, row - obj['row']] if same_shape else None,
                     skip=self._others_cells(area, index, old_cells + new_abs))
        return {'writes': writes, 'title': f'{name[0].upper() + name[1:]}: {", ".join(parts) or "unchanged"} ({where})', 'watch': watch}

    def _others_cells(self, area, index, near) -> list:
        """Cells the other area objects draw on, next to the given cells (they may cover the piece or be covered)."""
        style = self.style(area)
        columns = {c for c, _ in near}
        low, high = min(columns) - 1, max(columns) + 1
        out = set()
        for t in self.tokens(area):
            if t['kind'] != 'object' or t['index'] == index:
                continue
            if t['row'] <= 11 and not t['value'] & 0x70 and t['value'] <= 8:
                cells = [(0, t['row'])]
            else:
                info = self.piece(t['row'], t['value'], style)
                if info is None:
                    continue
                cells = info['cells']
            x = t['page'] * 16 + t['col']
            out |= {(x + c, r) for c, r in cells if low <= x + c <= high}
        return sorted([list(c) for c in out])

    @staticmethod
    def _value(info, kind, size, old) -> int:
        """Byte 2 (without the page flag) for a piece of `kind` with length `size`, the nearest length the kind takes."""
        if info['group'] == 'small':
            return kind
        if info['group'] == 'row15':
            return (old & 0x70) | ((size if size is not None else old & 15) & 15)
        if kind in (0x70, 0x78):
            size = min(max(size if size is not None else 1, 1), 7)
            return 0x70 | (kind & 8) | size
        return kind | ((size if size is not None else old & 15) & 15)

    def watcher(self, watch):
        if watch['kind'] == 'piece':
            return _PieceWatcher(watch)
        if watch['kind'] == 'enemy':
            return _EnemyWatcher(watch)
        if watch['kind'] == 'block':
            return _BlockWatcher(watch)
        if watch['kind'] == 'way':
            return _WayWatcher(watch)
        return Watcher()


PROFILES = [SMB1Profile]
