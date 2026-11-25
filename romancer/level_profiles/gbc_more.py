"""Game Boy Color games: The Legend of Zelda - Link's Awakening DX and Wario Land II.

Link's Awakening DX runs the original Link's Awakening engine (see gb_adventure.py) with its tables moved and one
more dungeon (map $FF); the profile reuses that one and changes only what the DX code does differently. Research
notes: research/gbc_more-level-profile.md. Work RAM addresses are written as $Cxxx / $Dxxx; ROMancer's RAM view of a
Game Boy Color is all eight work RAM banks, bank 0 ($C000) at index 0 and bank n at index n * $1000, so $Dxxx in the
games' usual bank 1 is index $1xxx.
"""
from __future__ import annotations

from . import Profile, Watcher
from .gb_adventure import LinksAwakening, _ChestWatcher, _BlockWatcher, _ZeldaWatcher, _file


# ---------------------------------------------------------------------------------------------------------------------
# The Legend of Zelda - Link's Awakening DX
# ---------------------------------------------------------------------------------------------------------------------

class LinksAwakeningDX(LinksAwakening):
    """The Legend of Zelda - Link's Awakening DX (USA, Europe) (Rev 2).

    The same engine as the original (rooms of 160 by 128 pixels, $DBA5 outdoors flag, high RAM $FFF6 room and $FFF7
    map), decoded again in the DX code:

    * Objects (loader $37FD, bank 0): bank $16, the word at $4000 / $4200 / $4400 + room * 2 (overworld, indoors A,
      indoors B) and, new in DX, $4600 for map $FF; the same [position, type] records ending with $FF.
    * Room layouts (loader $3110-$3285, bank 0): bank 9 (overworld, rooms $80 and up in bank $1A), $0A (indoors A),
      $0B (indoors B), all with the pointer table at $4000; map $FF uses the table at $7B77 in bank $0A. The block
      format and the flag changes are the original's (flag bytes $D800 / $D900 / $DA00 + room, and $DDE0 + room for
      map $FF).
    * Dungeon grids (bank $14, $58A3): $4220 + map * 64 for maps 0-$0A, $4520 for map 6 once $DB6B bit 2 is set,
      $44E0 for map $FF.
    * Chests (bank $14, $58FD): $4560 + group * 256 + room, and $4860 + room for map $FF; opening one still makes
      object 7 with the contents in $C3B0.
    """
    name = "The Legend of Zelda - Link's Awakening DX"
    sha256s = ('5dee5816ed9b46cfc4a2d94f275e555dd3c5080eca00ded975a41a881a6d4c06',)
    system = 'gbc'
    OBJ_TABLES = (0x4000, 0x4200, 0x4400, 0x4600)
    LAYOUT_BANKS = (0x09, 0x0A, 0x0B, 0x0A)
    LAYOUT_TABLES = (0x4000, 0x4000, 0x4000, 0x7B77)
    GRID, GRID_ALT, GRID_FF = 0x4220, 0x4520, 0x44E0
    CHESTS, CHESTS_FF = 0x4560, 0x4860
    MAP_FF = 0xFF
    ROOMS_FF = 0x20             # the map $FF tables hold 32 rooms (the layout table's first list starts right after it)
    # chest contents: each value was put in the chest of dungeon map 0, room 8, and opened in the DX game, reading its
    # message and what changed in RAM (trace/v15_profiles/gbc_more/chest)
    CONTENTS = {**LinksAwakening.CONTENTS, 0x0A: 'Bomb', 0x10: 'Secret Medicine', 0x18: 'Stone Beak'}

    # ---- reading
    @staticmethod
    def group_of_map(m):
        return 3 if m == 0xFF else 2 if 6 <= m < 0x1A else 1

    def _room_count(self, group):
        return self.ROOMS_FF if group == 3 else 256

    def users(self, room, group=0):
        pointer = self.list_address(room, group)
        return sum(1 for other in range(self._room_count(group)) if self.list_address(other, group) == pointer)

    def layout(self, room, group=0):
        """The room's blocks, as LinksAwakening.layout, with the DX pointer table of each group."""
        table = self.LAYOUT_BANKS[group]
        base = self.LAYOUT_TABLES[group]
        pointer = self._rb(table, base + room * 2) | self._rb(table, base + room * 2 + 1) << 8
        bank = 0x1A if group == 0 and room >= 0x80 else table
        address, out = pointer + 2, []
        while len(out) < 160 and 0x4000 <= address < 0x7FFE:
            first = self._rb(bank, address)
            if first == 0xFE:
                break
            if first & 0xFC == 0xE0:
                address += 5
                continue
            if first & 0x80 and not first & 0x10:
                out.append({'at': self._rb(bank, address + 1), 'type': self._rb(bank, address + 2),
                            'byte': _file(bank, address + 2), 'run': first & 15})
                address += 3
            else:
                out.append({'at': first, 'type': self._rb(bank, address + 1), 'byte': _file(bank, address + 1), 'run': 1})
                address += 2
        return out

    def chest_offset(self, room, group):
        if group == 3:
            return _file(self.GRID_BANK, self.CHESTS_FF + room)
        return _file(self.GRID_BANK, self.CHESTS + group * 256 + room)

    def grid(self, m, alternate=False):
        base = self.GRID_FF if m == self.MAP_FF else self.GRID_ALT if alternate else self.GRID + m * 64
        return [self._rb(self.GRID_BANK, base + i) for i in range(64)]

    @staticmethod
    def has_grid(m):
        return m < 0x0B or m == 0xFF

    def content_choices(self, current, dungeon):
        used = {self.contents(r, g) for g in range(4) for r in range(self._room_count(g))} & set(self.CONTENTS)
        if not dungeon:
            used -= set(self.DUNGEON_ITEMS)
        return [{'value': v, 'name': self.content_name(v)} for v in sorted(used | {current})]

    # ---- interface
    def where(self, ram):
        if ram[0x1BA5] == 0:
            room = ram[0x1B54]
            return {'part': {'map': 'overworld'}, 'x': (room & 15) * self.W, 'y': (room >> 4) * self.H}
        hram = getattr(ram, 'domains', {}).get('hram')
        if hram is None or len(hram) < 0x78:
            return None
        room, m = hram[0x76], hram[0x77]
        if self.has_grid(m) and room:
            alternate = m == 6 and bool(ram[0x1B6B] & 4)
            cells = self.grid(m, alternate)
            at = ram[0x1BAE]
            if not (at < 64 and cells[at] == room):
                at = cells.index(room) if room in cells else None
            if at is not None:
                part = {'map': m, 'alternate': 1} if alternate else {'map': m}
                return {'part': part, 'x': (at & 7) * self.W, 'y': (at >> 3) * self.H}
        return {'part': {'map': m, 'room': room}, 'x': 0, 'y': 0}

    def part_name(self, part):
        if part.get('map') != 'overworld' and int(part['map']) == self.MAP_FF:
            return f'Indoors, map 0xFF, room {int(part["room"]):02X}' if 'room' in part else 'Dungeon map 0xFF'
        return super().part_name(part)

    def watcher(self, watch):
        if watch.get('kind') == 'chest':
            return _DXChestWatcher(self, watch)
        if watch.get('kind') == 'block':
            return _DXBlockWatcher(self, watch)
        return _DXObjectWatcher(self, watch)


def _dx_room(ram):
    """(group, room) Link is in (group 3 is map $FF), or None indoors when high RAM is not available."""
    if ram[0x1BA5] == 0:
        return 0, ram[0x1B54]
    hram = getattr(ram, 'domains', {}).get('hram')
    if hram is None or len(hram) < 0x78:
        return None
    return LinksAwakeningDX.group_of_map(hram[0x77]), hram[0x76]


class _DXObjectWatcher(_ZeldaWatcher):
    """The original's object watcher (one more / one fewer of the type in the slots 40 frames after Link enters the
    room, original game replayed first), with the DX room groups."""

    def see(self, ram, frame, run):
        if _dx_room(ram) != (self.w.get('group', 0), self.w['room']):
            return False
        self.first.setdefault(run, frame)
        if frame - self.first[run] < 40:
            return False
        counts = {}
        for slot in range(16):
            if ram[0x280 + slot]:
                kind = ram[0x3A0 + slot]
                counts[kind] = counts.get(kind, 0) + 1
        self.counts[run] = counts
        return True


class _DXChestWatcher(_ChestWatcher):
    """Object 7's contents ($C3B0) when the walk opens the chest of the edited room."""

    def see(self, ram, frame, run):
        if _dx_room(ram) != (self.w['group'], self.w['room']):
            return False
        for slot in range(16):
            if ram[0x280 + slot] and ram[0x3A0 + slot] == 7:
                self.seen = ram[0x3B0 + slot]
                return True
        return False


class _DXBlockWatcher(_BlockWatcher):
    """The block the room loader wrote to $D711 + position, 20 frames after Link enters the edited room."""

    def see(self, ram, frame, run):
        if _dx_room(ram) != (self.w['group'], self.w['room']):
            return False
        if self.first is None:
            self.first = frame
        if frame - self.first < 20:
            return False
        self.seen = ram[0x1711 + self.w['at']]
        return True


# ---------------------------------------------------------------------------------------------------------------------
# Wario Land II
# ---------------------------------------------------------------------------------------------------------------------

class WarioLand2(Profile):
    """Wario Land II (USA, Europe), the Game Boy Color cartridge (MBC5, 128 banks, 32 KB cartridge RAM).

    The story ($D510, 0-50) picks everything. Its header (bank $0A, the word at $4195 + story * 2 on a Game Boy Color;
    loader $40CB) gives the map width (byte 1, 160 blocks), the block map (bank of byte 2, pointer bytes 3-4) and the
    object map (bank $0F, pointer bytes 5-6). Both are unpacked into cartridge RAM banks 1-3 at $A000 (32 rows of 256
    bytes per bank): the block map in bytes 0-$9F of a row, the object map in bytes $B0-$FF (loader $22A1). The object
    map has a 4-bit cell per block, two blocks to a byte (the even column in the high nibble): bit 3 says the scan
    starts it, bits 0-2 pick one of the eight objects of the area's object set. Packing: a count byte, then one value
    repeated (count below $80) or count - $80 bytes as they are; 0 ends it.

    Areas: bank 0's word at $2C98 + story * 2 points (bank $0A) at up to 30 area words ($2D00: none); each area record
    gives its rows (byte 1: first and end row / 16, high and low nibble), its columns (byte 2: first and end column /
    16) and its object set (byte 4). The object set (bank $3E, word at $4DB3 + set * 2; loader $420E) is two graphics
    pointers, a byte, then up to eight object pointers ending with $427D; the loader copies them to $C100. A started
    object takes one of eight 32-byte slots at $C000 (bank $3E $4000): +0 state (bit 0 in use; $81 from a high nibble,
    $01 from a low one), +1 / +2 the map byte it came from ($B0 + column / 2, and $A0 + row in its RAM bank + 32 *
    (bank - 1)), +3/+4 y and +5/+6 x (bottom middle of the block, y = row * 16 + 16, x = column * 16 + 8), and the
    object's 10-byte record copied to +7, +9, +10, +16-19, +26, +30, +31. Starting it clears bit 3 of its cell.

    Where: work RAM $C6F1 = 3 and $C6F2 = $11 while a story is played; high RAM $FFAD/$FFAE is the camera's y and
    $FFAF/$FFB0 its x (the low bytes are the scroll registers' values).
    """
    name = 'Wario Land II'
    sha256s = ('40f366ccd5bd6a9643dc317db63a286f9104f164f9fc46ff037e548d5e83ed52',)
    system = 'gbc'
    STORIES = 51
    HEADERS = (0x0A, 0x4195)
    OBJ_BANK = 0x0F
    AREAS = 0x2C98
    AREA_BANK = 0x0A
    NO_AREA = 0x2D00
    SETS = (0x3E, 0x4DB3)
    TEXT = (0x22, 0x5DCA)
    END = 0x427D
    EMPTY = (0x427D, 0x4287)        # the end marker and a record with the same bytes: nothing to start
    WIDTH = 160

    def __init__(self, rom: bytes):
        super().__init__(rom)
        self._cache = {}

    # ---- reading
    def _b(self, bank, address):
        return self.rom[_file(bank, address)]

    def _w(self, bank, address):
        return self._b(bank, address) | self._b(bank, address + 1) << 8

    def header(self, story):
        return _file(self.HEADERS[0], self._w(*self.HEADERS[:1], self.HEADERS[1] + story * 2))

    def cells(self, story):
        """Every object cell of a story: [{'row', 'col', 'value' (4 bits), 'byte' (ROM offset of the packed byte, or None
        inside a repeated run), 'high'}]; empty cells are left out."""
        key = ('cells', story)
        if key in self._cache:
            return self._cache[key]
        head = self.header(story)
        width = self.rom[head + 1]
        address = _file(self.OBJ_BANK, self.rom[head + 5] | self.rom[head + 6] << 8)
        per_row = width // 2
        out, at = [], 0
        while at < per_row * 96:
            count = self.rom[address]
            address += 1
            if count == 0:
                break
            if count & 0x80:
                run = [(self.rom[address + k], address + k) for k in range(count & 0x7F)]
                address += count & 0x7F
            else:
                run = [(self.rom[address], None)] * count
                address += 1
            for value, offset in run:
                row, col2 = divmod(at, per_row)
                for half, nib in ((0, value >> 4), (1, value & 15)):
                    if nib:
                        out.append({'row': row, 'col': col2 * 2 + half, 'value': nib, 'byte': offset, 'high': half == 0})
                at += 1
        self._cache[key] = out
        self._cache[('rows', story)] = at // per_row if per_row else 0
        return out

    def packed_byte(self, story, row, col):
        """ROM offset of the packed byte that holds a cell when that byte is stored as is (not in a repeated run)."""
        head = self.header(story)
        width = self.rom[head + 1]
        address = _file(self.OBJ_BANK, self.rom[head + 5] | self.rom[head + 6] << 8)
        per_row, want, at = width // 2, row * (width // 2) + col // 2, 0
        while True:
            count = self.rom[address]
            if count == 0:
                return None
            n = count & 0x7F
            if at <= want < at + n:
                return address + 1 + (want - at) if count & 0x80 else None
            at += n
            address += 1 + (n if count & 0x80 else 1)

    def areas(self, story):
        """[{'entrance', 'rows': (first, end), 'cols': (first, end), 'set'}] from the story's area records."""
        key = ('areas', story)
        if key in self._cache:
            return self._cache[key]
        table = self._w(0, self.AREAS + story * 2)
        out = []
        for entrance in range(30):
            pointer = self._w(self.AREA_BANK, table + entrance * 2)
            if pointer == self.NO_AREA or not 0x4000 <= pointer < 0x8000:
                continue
            o = _file(self.AREA_BANK, pointer)
            rows, cols = self.rom[o + 1], self.rom[o + 2]
            out.append({'entrance': entrance, 'rows': ((rows >> 4) * 16, (rows & 15) * 16),
                        'cols': ((cols >> 4) * 16, (cols & 15) * 16), 'set': self.rom[o + 4]})
        self._cache[key] = out
        return out

    def object_set(self, number):
        """The eight object pointers the loader copies to $C100 (padded with the end marker)."""
        pointer = self._w(self.SETS[0], self.SETS[1] + number * 2)
        address, out = pointer + 5, []
        while len(out) < 8:
            value = self._w(self.SETS[0], address)
            out.append(value)
            address += 2
            if value == self.END:
                break
        return out + [self.END] * (8 - len(out))

    def record(self, kind):
        """The 10-byte record of an object pointer (bank $3E)."""
        o = _file(self.SETS[0], kind)
        return bytes(self.rom[o:o + 10])

    def kind_at(self, story, row, col, index):
        """The object pointer a cell's index means where it is, or None when no area covers the cell or the areas that
        do disagree."""
        kinds = {self.object_set(a['set'])[index] for a in self.areas(story)
                 if a['rows'][0] <= row < a['rows'][1] and a['cols'][0] <= col < a['cols'][1]}
        return kinds.pop() if len(kinds) == 1 else None

    def area_set(self, story, row, col):
        sets = {a['set'] for a in self.areas(story) if a['rows'][0] <= row < a['rows'][1] and a['cols'][0] <= col < a['cols'][1]}
        sets = {tuple(self.object_set(s)) for s in sets}
        return list(sets.pop()) if len(sets) == 1 else None

    def story_text(self, story):
        o = _file(self.TEXT[0], self._w(*self.TEXT[:1], self.TEXT[1] + story * 2))
        def text(data):
            chars = ''.join(chr((x - 127) & 0xFF) if 32 <= ((x - 127) & 0xFF) < 127 else ' ' for x in data)
            return ' '.join(chars.split())
        return text(self.rom[o + 14:o + 44]), text(self.rom[o + 56:o + 86])

    @staticmethod
    def type_name(kind):
        return f'Object {kind:04X}'

    # ---- interface
    def where(self, ram):
        if len(ram) < 0x1600 or ram[0x6F1] != 3 or ram[0x6F2] != 0x11:
            return None
        story = ram[0x1510]
        hram = getattr(ram, 'domains', {}).get('hram')
        if story >= self.STORIES or hram is None or len(hram) < 0x31:
            return None
        return {'part': {'story': story}, 'x': hram[0x2F] << 8 | hram[0x30], 'y': hram[0x2D] << 8 | hram[0x2E]}

    def part_name(self, part):
        chapter, story = self.story_text(int(part['story']))
        title = f'{chapter}: {story}' if chapter and story else chapter or story
        return f'Story {int(part["story"]) + 1}' + (f' ({title})' if title else '')

    def choices_at(self, story, row, col, current):
        """The objects the area's set can start at this cell: one choice per different record (not the empty ones)."""
        kinds = self.area_set(story, row, col)
        if kinds is None:
            return []
        out, records = [], set()
        for index, kind in enumerate(kinds):
            if index < 2 and index != current or kind in self.EMPTY:
                continue
            rec = self.record(kind)
            if rec in records and index != current:
                continue
            records.add(rec)
            out.append({'value': index, 'name': self.type_name(kind)})
        return out

    def objects(self, part):
        story = int(part['story'])
        out = []
        for c in self.cells(story):
            index, started = c['value'] & 7, bool(c['value'] & 8)
            kind = self.kind_at(story, c['row'], c['col'], index)
            row = {'id': f'obj:{c["row"]}:{c["col"]}', 'type': kind if kind is not None else index, 'style': 'enemy',
                   'x': c['col'] * 16 + 8, 'y': c['row'] * 16 + 16, 'fields': [], 'remove': None,
                   'name': self.type_name(kind) if kind is not None else f'Object {index} of the set'}
            if not started:
                row['note'] = ('The level scan does not start this one (bit 3 of its cell is clear); the game starts it '
                               'some other way, so ROMancer leaves it alone.')
            elif kind is None:
                row['note'] = 'No single area of the level covers this spot, so which object it is cannot be told.'
            elif c['byte'] is not None:
                row['fields'] = [{'key': 'type', 'label': 'Swap for', 'value': index,
                                  'choices': self.choices_at(story, c['row'], c['col'], index)}]
                row['remove'] = 'Remove this object'
                row['note'] = 'Swaps offer the objects this area of the level loads (its object set).'
            out.append(row)
        return out

    def _cell(self, story, object_id):
        kind, row, col = object_id.split(':')
        if kind != 'obj':
            raise ValueError('ROMancer cannot change that yet.')
        found = next((c for c in self.cells(story) if c['row'] == int(row) and c['col'] == int(col)), None)
        if found is None:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        return found

    def _write(self, offset, high, nibble):
        old = self.rom[offset]
        new = (old & 0x0F) | nibble << 4 if high else (old & 0xF0) | nibble
        return [(offset, old, new)] if new != old else []

    def _watch(self, story, row, col, kind, new=None, old=None):
        return {'game': 'wl2', 'story': story, 'row': row, 'col': col, 'kind': kind,
                'new': None if new is None else new, 'new_record': None if new is None else self.record(new).hex(),
                'old': old, 'old_record': None if old is None else self.record(old).hex()}

    def edit(self, part, object_id, values, remove=False):
        story = int(part['story'])
        c = self._cell(story, object_id)
        index = c['value'] & 7
        kind = self.kind_at(story, c['row'], c['col'], index)
        if not c['value'] & 8 or kind is None or c['byte'] is None:
            raise ValueError('ROMancer cannot change that yet.')
        where = f'story {story + 1}, column {c["col"]}, row {c["row"]}'
        if remove:
            return {'writes': self._write(c['byte'], c['high'], 0), 'title': f'Remove {self.type_name(kind)} ({where})',
                    'watch': self._watch(story, c['row'], c['col'], 'remove', old=kind)}
        value = int(values.get('type', index))
        if not any(o['value'] == value for o in self.choices_at(story, c['row'], c['col'], index)):
            raise ValueError('That choice is not one of the game’s own.')
        new = self.area_set(story, c['row'], c['col'])[value]
        return {'writes': self._write(c['byte'], c['high'], 8 | value),
                'title': f'Object here: {self.type_name(new)} ({where})',
                'watch': self._watch(story, c['row'], c['col'], 'type', new=new, old=kind)}

    def addable(self, part):
        story = int(part['story'])
        kinds = {}
        for a in self.areas(story):
            for index, kind in enumerate(self.object_set(a['set'])):
                if index >= 2 and kind not in self.EMPTY:
                    kinds.setdefault(kind, None)
        return [{'kind': f'{kind:04x}', 'name': self.type_name(kind), 'fields': []} for kind in sorted(kinds)]

    def add(self, part, kind, x, y, values):
        story = int(part['story'])
        col, row = int(x) // 16, (int(y) - 1) // 16
        if not (0 <= col < self.WIDTH and 0 <= row < self._rows(story)):
            raise ValueError('That spot is outside the level.')
        kinds = self.area_set(story, row, col)
        if kinds is None:
            raise ValueError('No single area of the level covers that spot, so the game would not know which object it is.')
        wanted = int(kind, 16)
        index = next((i for i, k in enumerate(kinds) if k == wanted and i >= 2), None)
        if index is None:
            raise ValueError('That object is not one the game loads in this area of the level.')
        if any(c['row'] == row and c['col'] == col for c in self.cells(story)):
            raise ValueError('There is already an object at that spot.')
        offset = self.packed_byte(story, row, col)
        if offset is None:
            raise ValueError('The level stores that spot packed together with its neighbours, so a new object cannot be '
                             'written there without making the level longer. Pick a spot closer to another object.')
        return {'writes': self._write(offset, col % 2 == 0, 8 | index),
                'title': f'Add {self.type_name(wanted)} (story {story + 1}, column {col}, row {row})',
                'watch': self._watch(story, row, col, 'add', new=wanted)}

    def _rows(self, story):
        self.cells(story)
        return self._cache[('rows', story)]

    def watcher(self, watch):
        return _WarioWatcher(self, watch)


class _WarioWatcher(Watcher):
    """Looks at the eight object slots every frame while the edited story is played. The slot whose +1 / +2 name the
    edited cell's map byte (and whose state's bit 7 matches its half) was started from that cell; the record bytes in
    the slot when it first appears tell which object it is. A removal replays the original game first and is good when
    the original started an object there and the changed game did not."""
    every = 1

    def __init__(self, profile, watch):
        self.p, self.w = profile, watch
        self.compare = watch['kind'] == 'remove'
        self.seen = {}            # run -> record bytes of the slot when first seen
        self.covered = {}         # run -> the camera showed the cell
        w = watch
        self.low = 0xB0 + w['col'] // 2
        self.high = 0xA0 + w['row'] % 32 + 32 * (w['row'] // 32)
        self.half = 0x80 if w['col'] % 2 == 0 else 0

    @staticmethod
    def _record(ram, base):
        return bytes(ram[base + k] for k in (7, 9, 10, 16, 17, 18, 19, 26, 30, 31))

    def see(self, ram, frame, run):
        at = self.p.where(ram)
        if at is None or at['part']['story'] != self.w['story']:
            return False
        x, y = self.w['col'] * 16 + 8, self.w['row'] * 16 + 8
        if at['x'] <= x < at['x'] + 160 and at['y'] <= y < at['y'] + 144:
            self.covered[run] = True
        if run in self.seen:
            return False
        for slot in range(8):
            base = slot * 32
            if ram[base] & 1 and ram[base + 1] == self.low and ram[base + 2] == self.high and ram[base] & 0x80 == self.half:
                self.seen[run] = self._record(ram, base)
                return not self.compare or run == 'changed'
        return False

    def _score(self, got, record):
        want = bytes.fromhex(record)
        return sum(1 for a, b in zip(got, want) if a == b)

    def result(self):
        w, got = self.w, self.seen.get('changed')
        if w['kind'] == 'remove':
            if got is not None:
                return {'state': 'bad', 'text': 'Played from the start, the game still started an object there.'}
            if 'original' in self.seen and self.covered.get('changed'):
                return {'state': 'good', 'text': 'Played from the start, nothing is started there any more.'}
            return super().result()
        if got is None:
            if self.covered.get('changed'):
                return {'state': 'bad', 'text': 'Played from the start, the game showed that spot but started nothing there.'}
            return super().result()
        new = self._score(got, w['new_record'])
        old = self._score(got, w['old_record']) if w.get('old_record') else -1
        ok = new == 10 or (got[0] == bytes.fromhex(w['new_record'])[0] and new > old)
        name = self.p.type_name(w['new'])
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now starts {name} there.' if ok
                else f'Played from the start, the game started another object there, not {name}.'}


PROFILES = [LinksAwakeningDX, WarioLand2]
