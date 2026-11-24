"""Game Boy adventure games: Metroid II - Return of Samus and The Legend of Zelda - Link's Awakening.

Both games keep their objects in per-screen lists in ROM (decoded from the games' own code; research notes in
research/gb_adventure-level-profile.md). Edits are exact ROM writes to one screen's list, checked by replaying the
recorded walk and reading the game's object slots in work RAM ($C000 = index 0).
"""
from __future__ import annotations

from . import Profile, Watcher

BANK = 0x4000


def _file(bank: int, address: int) -> int:
    """ROM file offset of a CPU address ($4000-$7FFF in a switchable bank, $0000-$3FFF in bank 0)."""
    return address if address < 0x4000 else bank * BANK + address - 0x4000


# ---------------------------------------------------------------------------------------------------------------------
# Metroid II - Return of Samus
# ---------------------------------------------------------------------------------------------------------------------

class MetroidII(Profile):
    """Metroid II - Return of Samus (World).

    The world is seven maps (ROM banks 9-15, RAM $D058), each 16 by 16 screens of 256 by 256 pixels. Objects
    (enemies, Metroids, items) come from bank 3: the word at $42E0 + (map - 9) * $200 + (screen y * 16 + screen x) * 2
    points at that screen's list of 4-byte records [number, type, x, y] ending with $FF (loader $40FC, spawn $422F).
    The number picks the object's flag byte at $C500 + number (an object whose flag says it is gone does not come back);
    type is the object type; x and y are pixels in the screen. A spawned object takes a 32-byte slot at $C600: +0 state
    ($FF free), +1 y, +2 x, +3 type, +$1D number.
    """
    name = 'Metroid II - Return of Samus'
    sha256s = ('3080bcc2eb9965de463f5f4e02f0dabbb13b060e1654a18da8b50948c10af4a6',)
    system = 'gb'
    TABLE = 0x42E0
    OBJ_BANK = 3
    MAPS = range(9, 16)
    # Items: picked up next to the start in a scratch ROM, reading what each changed (trace/v15_profiles/gb_adventure/
    # pickup.py). The pickup code at $4E5D (bank 2) turns an odd type into item number (type - $81) / 2 + 1 for the
    # handler table at $379A; an even type is the item sphere that holds type + 1 (shooting it shows the item).
    ITEMS = {0x81: 'Plasma Beam', 0x83: 'Ice Beam', 0x85: 'Wave Beam', 0x87: 'Spazer', 0x89: 'Bombs',
             0x8B: 'Screw Attack', 0x8D: 'Varia Suit', 0x8F: 'Hi-Jump Boots', 0x91: 'Space Jump', 0x93: 'Spider Ball',
             0x95: 'Spring Ball', 0x97: 'Energy Tank', 0x99: 'Missile Tank', 0x9B: 'Energy refill', 0x9D: 'Missile refill'}
    SPHERES = {t - 1: n for t, n in ITEMS.items() if t <= 0x95}
    LOOSE = (0x97, 0x99, 0x9B, 0x9D)
    # Metroids: the object header table at $6300 (bank 3) gives each type's hit points (byte 8). The four Metroid
    # stages take 5, 10, 20 and 40, and the spawned pictures (trace/v15_profiles/gb_adventure/sheet) show the
    # matching shapes. These five types are also the 38 Metroids of the lists (the HUD starts at 39 with the queen).
    METROIDS = {0xA0: 'Alpha Metroid', 0xA4: 'Alpha Metroid', 0xA3: 'Gamma Metroid', 0xAD: 'Zeta Metroid',
                0xB3: 'Omega Metroid'}

    def __init__(self, rom: bytes):
        super().__init__(rom)

    # ---- reading
    def _b(self, address: int) -> int:
        return self.rom[_file(self.OBJ_BANK, address)]

    def _w(self, address: int) -> int:
        return self._b(address) | self._b(address + 1) << 8

    def list_address(self, area: int, screen: int) -> int:
        return self._w(self.TABLE + (area - 9) * 0x200 + screen * 2)

    def records(self, area: int, screen: int) -> list:
        """[{index, number, type, x, y, byte}] of one screen's list; byte is the ROM offset of the record."""
        address, out = self.list_address(area, screen), []
        while self._b(address) != 0xFF and len(out) < 32:
            out.append({'index': len(out), 'number': self._b(address), 'type': self._b(address + 1),
                        'x': self._b(address + 2), 'y': self._b(address + 3), 'byte': _file(self.OBJ_BANK, address)})
            address += 4
        return out

    def hit_points(self, kind: int) -> int:
        return self._b(self._w(0x6300 + kind * 2) + 8)

    def behaviour(self, kind: int) -> int:
        """The code pointer an object type runs (header bytes 9-10, copied to slot +$1E). Enemies that animate by
        changing their type (0x12 <-> 0x13) keep it, so it tells a spawned object's type apart from others."""
        header = self._w(0x6300 + kind * 2)
        return self._b(header + 9) | self._b(header + 10) << 8

    def type_name(self, kind: int) -> str:
        if kind in self.ITEMS:
            return self.ITEMS[kind]
        if kind in self.SPHERES:
            return f'Item sphere ({self.SPHERES[kind]})'
        if kind in self.METROIDS:
            return self.METROIDS[kind]
        return f'Enemy {kind:#04x}'

    def is_item(self, kind: int) -> bool:
        return kind in self.ITEMS or kind in self.SPHERES

    # ---- interface
    def where(self, ram):
        area = ram[0x1058]
        if area not in self.MAPS:
            return None
        x = ram[0x1027] | ram[0x1028] << 8          # Samus, world pixels (copies of $FFC2/$FFC0)
        y = ram[0x1029] | ram[0x102A] << 8
        left = x - ((x - ram[0x0206]) & 0xFF)       # $C206 / $C205: the scroll the next frame shows
        top = y - ((y - ram[0x0205]) & 0xFF)
        # the block rule of the graphics set the door scripts loaded (see tile_role)
        self.__dict__.setdefault('_rules', set()).add(bytes([ram[0x1056], ram[0x108A]]) + bytes(ram[0x1C00:0x1D00]))
        return {'part': {'area': area}, 'x': left, 'y': top}

    def part_name(self, part):
        return f'Map {part["area"] - 8}'

    def tile_role(self, tile):
        """What Samus's and the shots' collision code makes of a background tile. A door script picks a graphics set
        (bank 8: thresholds at $7EFA + set * 4, a 256-byte tile property table from the pointer at $7EEA + set * 2)
        and the game copies them to RAM: tiles below $D056 are solid for Samus, a shot stops on tiles below $D08A, and
        the property table is at $DC00. Shots break tiles 0-3 (they grow back, queue $D900, bank 1 $5671) and tiles
        whose property has bit 5 (gone for good, $56E9); bombs break tiles 0-3 and tiles with bit 6 (bank 1 $5536).
        The rule is read from RAM in where(); when the map's parts use different sets no roles are given."""
        rules = self.__dict__.get('_rules', set())
        if len(rules) != 1:
            return None
        rule = next(iter(rules))
        solid, shot, props = rule[0], rule[1], rule[2:]
        if tile < 4 or (tile < shot and props[tile] & 0x20) or props[tile] & 0x40:
            return 'breakable'
        return 'solid' if tile < solid else 'open'

    def neighbours(self, area: int, screen: int) -> set:
        """Object types used on this screen and the eight around it (the same enemy graphics are loaded there)."""
        sy, sx = screen >> 4, screen & 15
        kinds = set()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if 0 <= sy + dy < 16 and 0 <= sx + dx < 16:
                    kinds |= {r['type'] for r in self.records(area, (sy + dy) * 16 + sx + dx)}
        return kinds

    def type_choices(self, area: int, screen: int, kind: int) -> list:
        if kind in self.SPHERES:
            group = sorted(self.SPHERES)
        elif kind in self.ITEMS:
            group = sorted(set(self.LOOSE) | {kind})
        else:
            group = sorted(k for k in self.neighbours(area, screen) | {kind} if not self.is_item(k))
        return [{'value': k, 'name': self.type_name(k)} for k in group]

    def objects(self, part):
        area = int(part['area'])
        out = []
        for screen in range(256):
            rows = self.records(area, screen)
            for r in rows:
                kind = r['type']
                row = {'id': f'obj:{screen}:{r["index"]}', 'type': kind, 'x': (screen & 15) * 256 + r['x'],
                       'y': (screen >> 4) * 256 + r['y'] + 8, 'name': self.type_name(kind),
                       'style': 'item' if self.is_item(kind) else 'enemy',
                       'fields': [{'key': 'type', 'label': 'Holds' if self.is_item(kind) else 'Swap for', 'value': kind,
                                   'choices': self.type_choices(area, screen, kind)}],
                       'remove': 'Remove this item' if self.is_item(kind) else 'Remove this enemy'}
                if kind in self.SPHERES:
                    row['detail'] = f'holds {self.SPHERES[kind]}'
                    row['name'] = 'Item sphere'
                    row['note'] = ('The room loads the picture of the item it was made for, so a sphere given another item '
                                   'still shows the old picture; the item it gives is the new one.')
                elif kind in self.METROIDS:
                    row['detail'] = f'{self.hit_points(kind)} hit points'
                elif not self.is_item(kind):
                    row['note'] = 'Swaps offer the enemies used on this screen and the screens around it, whose pictures are loaded here.'
                out.append(row)
        return out

    def _spot(self, area: int, object_id: str):
        kind, screen, index = object_id.split(':')
        if kind != 'obj':
            raise ValueError('ROMancer cannot change that yet.')
        rows = self.records(area, int(screen))
        if not 0 <= int(index) < len(rows):
            raise ValueError('That is not part of this level any more. Reopen the map.')
        return int(screen), rows, rows[int(index)]

    def edit(self, part, object_id, values, remove=False):
        area = int(part['area'])
        screen, rows, row = self._spot(area, object_id)
        watch = {'game': 'm2', 'area': area, 'screen': screen, 'number': row['number'], 'x': (screen & 15) * 256 + row['x'],
                 'y': (screen >> 4) * 256 + row['y']}
        if remove:
            # the list has no gaps: the last record moves into this one's place and the list ends one record sooner
            last = rows[-1]
            writes = []
            if last is not row:
                for k in range(4):
                    old, new = self.rom[row['byte'] + k], self.rom[last['byte'] + k]
                    if old != new:
                        writes.append((row['byte'] + k, old, new))
            writes.append((last['byte'], self.rom[last['byte']], 0xFF))
            watch.update(kind='remove', name=self.type_name(row['type']))
            return {'writes': writes, 'title': f'Remove {self.type_name(row["type"])} (map {area - 8}, screen {screen:02X})',
                    'watch': watch}
        kind = int(values.get('type', row['type']))
        if not any(c['value'] == kind for c in self.type_choices(area, screen, row['type'])):
            raise ValueError('That choice is not one of the game’s own.')
        offset = row['byte'] + 1
        writes = [(offset, self.rom[offset], kind)] if self.rom[offset] != kind else []
        watch.update(kind='type', type=kind, old=row['type'], name=self.type_name(kind))
        title = (f'Item sphere holds: {self.SPHERES[kind]}' if kind in self.SPHERES else
                 f'Item here: {self.ITEMS[kind]}' if kind in self.ITEMS else f'Enemy here: {self.type_name(kind)}')
        return {'writes': writes, 'title': f'{title} (map {area - 8}, screen {screen:02X})', 'watch': watch}

    def watcher(self, watch):
        return _MetroidWatcher(self, watch)


class _MetroidWatcher(Watcher):
    """Watch the object slots ($C600, 32 bytes each) while the walk is on the edited map: a slot whose number is the
    record's, spawned while the record's spot is near the screen, is that record's object. A removal replays the
    original game first, so it only says good when the original walk really spawned the object there."""
    every = 2

    def __init__(self, profile, watch):
        self.p, self.w = profile, watch
        self.compare = watch['kind'] == 'remove'
        self.runs = {}            # run -> type seen in the record's slot (None: never)

    def see(self, ram, frame, run):
        w = self.w
        self.runs.setdefault(run, None)
        at = self.p.where(ram)
        if at is None or at['part']['area'] != w['area']:
            return False
        dx, dy = w['x'] - at['x'], w['y'] - at['y']
        if not (-48 <= dx < 208 and -48 <= dy < 192):
            return False
        for slot in range(16):
            base = 0x600 + slot * 32
            if ram[base] != 0xFF and ram[base + 0x1D] == w['number']:
                self.runs[run] = (ram[base + 3], ram[base + 0x1E] | ram[base + 0x1F] << 8)
                return True
        return False

    @property
    def seen(self):
        found = self.runs.get('changed')
        return None if found is None else found[0]

    def result(self):
        w = self.w
        if w['kind'] == 'remove':
            if self.seen is not None:
                return {'state': 'bad', 'text': f'Played from the start, the game still spawned type {self.seen:#04x} there.'}
            if self.runs.get('original') is not None:
                return {'state': 'good', 'text': 'Played from the start, nothing appears there any more.'}
            return super().result()
        if self.seen is None:
            return super().result()
        wanted, code = w['type'], self.runs['changed'][1]
        ok = (self.seen == wanted or (wanted in self.p.SPHERES and self.seen == wanted + 1)
              or (code == self.p.behaviour(wanted) and code != self.p.behaviour(w['old'])))
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now spawns {w["name"]} there.' if ok
                else f'Played from the start, the game spawned type {self.seen:#04x} there, not what was chosen.'}


# ---------------------------------------------------------------------------------------------------------------------
# The Legend of Zelda - Link's Awakening
# ---------------------------------------------------------------------------------------------------------------------

class LinksAwakening(Profile):
    """The Legend of Zelda - Link's Awakening (USA, Europe) (Rev 2).

    Rooms are 160 by 128 pixels (10 by 8 blocks of 16 pixels). Work RAM $DBA5 is 0 outdoors; high RAM $FFF6 is the
    room and $FFF7 the map indoors. Rooms come in three groups of 256: the overworld (room = screen y * 16 + screen x,
    also copied to $DB54), indoors A (maps 0-5 and $1A and up) and indoors B (maps 6-$19). Maps 0-$0A are laid out on
    an 8 by 8 grid (bank $14, $4200 + map * 64; map 6 uses $44C0 once $DB6B bit 2 is set; code $2F21) and are drawn as
    one part; every other indoor room is a part of its own.

    Objects: bank $16 (loader $36EE, bank 0), the word at $4000 / $4200 / $4400 (by group) + room * 2 points at a list
    of 2-byte records [position, type] ending with $FF; the position's high nibble is the block row, its low nibble the
    column. Slots: type $C3A0, state $C280, x $C200 (column * 16 + 8), y $C210 (row * 16 + 16).

    Room layouts (loader $2F90, bank 0): the word at $4000 + room * 2 of bank 9 (overworld; rooms $80 and up keep
    their data in bank $1A), $0A (indoors A) or $0B (indoors B) points at two header bytes, then blocks: [position,
    type], [count and direction, position, type] for a run ($8x / $Ax / $Cx), 5-byte warps ($E0-$E3) and $FE at the
    end. The loader writes each block's type to $D711 + position after changing some types by the room's flag byte
    ($D800 / $D900 / $DA00 + room): a chest ($A0) is drawn open with bit 4, hidden stairs ($BF) are drawn only with
    bit 4, an overworld cave wall ($BA) becomes a cave mouth ($E1) with bit 2, and the indoor wall blocks $3F-$42 and
    $47-$4A open with bits 2, 3, 1, 0 (top, bottom, left, right).

    Chests: what a chest holds is one byte per room, bank $14, $4500 + group * 256 + room (code $1FA1, bank 0). Opening
    it makes object 7 with the contents in $C3B0.
    """
    name = "The Legend of Zelda - Link's Awakening"
    sha256s = ('ed42628d5cd8c73a6f8c6a8965f19674876a4fa04e616834e26b81b35963ad87',)
    system = 'gb'
    OBJ_BANK = 0x16
    TABLE = 0x4000
    OBJ_TABLES = (0x4000, 0x4200, 0x4400)
    LAYOUT_BANKS = (0x09, 0x0A, 0x0B)
    GRID_BANK = 0x14
    CHESTS = 0x4500
    W, H = 160, 128
    # named only from pictures the game drew when spawned in a room that uses them (research notes); others show
    # their number
    NAMES = {0x6E: 'Butterfly', 0x31: 'Sword', 0x3C: 'Owl'}
    # chest contents: each value was put in a chest and opened (trace/v15_profiles/gb_adventure/chest), reading the
    # game's own message and what changed in RAM. Only values the game itself puts in a chest are offered.
    CONTENTS = {0x01: 'Mirror Shield', 0x02: 'Bow', 0x04: 'Magic Rod', 0x05: 'Pegasus Boots', 0x06: 'Ocarina',
                0x07: "Roc's Feather", 0x08: 'Shovel', 0x0C: 'Flippers', 0x11: 'Tail Key', 0x16: 'Map', 0x17: 'Compass',
                0x18: 'Stone Slab fragment', 0x19: "Nightmare's Key", 0x1A: 'Small Key', 0x1B: '50 Rupees',
                0x1C: '20 Rupees', 0x1D: '100 Rupees', 0x1E: '200 Rupees', 0x20: 'Secret Seashell', 0x21: 'No item',
                0x22: 'Explosion'}
    DUNGEON_ITEMS = (0x16, 0x17, 0x18, 0x19, 0x1A)
    UNIQUE = (0x01, 0x02, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0C, 0x11)
    WALLS = {0x3F: 'top', 0x40: 'bottom', 0x41: 'left', 0x42: 'right', 0x47: 'top', 0x48: 'bottom', 0x49: 'left',
             0x4A: 'right'}
    HIDDEN_STAIRS, STAIRS = 0xBF, 0xBE
    CAVE_WALL, CAVE = 0xBA, 0xE1

    # ---- reading
    def _rb(self, bank, address):
        return self.rom[_file(bank, address)]

    def _b(self, address):
        return self._rb(self.OBJ_BANK, address)

    @staticmethod
    def group_of_map(m):
        return 2 if 6 <= m < 0x1A else 1

    def list_address(self, room, group=0):
        table = self.OBJ_TABLES[group]
        return self._b(table + room * 2) | self._b(table + room * 2 + 1) << 8

    def records(self, room, group=0):
        address, out = self.list_address(room, group), []
        while self._b(address) != 0xFF and len(out) < 16:
            at = self._b(address)
            out.append({'index': len(out), 'row': at >> 4, 'column': at & 15, 'type': self._b(address + 1),
                        'byte': _file(self.OBJ_BANK, address)})
            address += 2
        return out

    def users(self, room, group=0):
        pointer = self.list_address(room, group)
        return sum(1 for other in range(256) if self.list_address(other, group) == pointer)

    def layout(self, room, group=0):
        """The room's blocks: [{'at', 'type', 'byte' (ROM offset of the type), 'run' (1 for a single block)}]."""
        table = self.LAYOUT_BANKS[group]
        pointer = self._rb(table, 0x4000 + room * 2) | self._rb(table, 0x4001 + room * 2) << 8
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
        return _file(self.GRID_BANK, self.CHESTS + group * 256 + room)

    def contents(self, room, group):
        return self.rom[self.chest_offset(room, group)]

    def grid(self, m, alternate=False):
        base = 0x44C0 if alternate else 0x4200 + m * 64
        return [self._rb(self.GRID_BANK, base + i) for i in range(64)]

    def type_name(self, kind):
        return self.NAMES.get(kind, f'Object {kind:#04x}')

    def content_name(self, value):
        return self.CONTENTS.get(value, f'Contents {value:#04x}')

    # ---- parts
    def rooms(self, part):
        """[(group, room, left, top)] of a part."""
        if part.get('map') == 'overworld':
            return [(0, r, (r & 15) * self.W, (r >> 4) * self.H) for r in range(256)]
        m = int(part['map'])
        group = self.group_of_map(m)
        if 'room' in part:
            return [(group, int(part['room']), 0, 0)]
        seen, out = set(), []
        for i, r in enumerate(self.grid(m, bool(part.get('alternate')))):
            if r and r not in seen:
                seen.add(r)
                out.append((group, r, (i & 7) * self.W, (i >> 3) * self.H))
        return out

    def where(self, ram):
        if ram[0x1BA5] == 0:
            room = ram[0x1B54]
            return {'part': {'map': 'overworld'}, 'x': (room & 15) * self.W, 'y': (room >> 4) * self.H}
        hram = getattr(ram, 'domains', {}).get('hram')
        if hram is None or len(hram) < 0x78:
            return None
        room, m = hram[0x76], hram[0x77]
        if m < 0x0B and room:
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
        if part.get('map') == 'overworld':
            return 'Overworld'
        if 'room' in part:
            return f'Indoors, map {int(part["map"]):#04x}, room {int(part["room"]):02X}'
        return f'Dungeon map {int(part["map"])}' + (' (after it changes)' if part.get('alternate') else '')

    def _group_of_part(self, part):
        return 0 if part.get('map') == 'overworld' else self.group_of_map(int(part['map']))

    @staticmethod
    def _dungeon(part):
        return part.get('map') != 'overworld' and 'room' not in part

    def neighbours(self, room, group=0, part=None):
        """Object types used in this room and the rooms around it (overworld screens or the dungeon grid)."""
        kinds = {r['type'] for r in self.records(room, group)}
        if group == 0:
            y, x = room >> 4, room & 15
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if 0 <= y + dy < 16 and 0 <= x + dx < 16:
                        kinds |= {r['type'] for r in self.records((y + dy) * 16 + x + dx)}
        elif part is not None and self._dungeon(part):
            cells = self.grid(int(part['map']), bool(part.get('alternate')))
            for i, r in enumerate(cells):
                if r != room:
                    continue
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        y, x = (i >> 3) + dy, (i & 7) + dx
                        if 0 <= y < 8 and 0 <= x < 8 and cells[y * 8 + x]:
                            kinds |= {k['type'] for k in self.records(cells[y * 8 + x], group)}
        return kinds

    def type_choices(self, room, kind, group=0, part=None):
        return [{'value': k, 'name': self.type_name(k)} for k in sorted(self.neighbours(room, group, part) | {kind})]

    def content_choices(self, current, dungeon):
        used = {self.contents(r, g) for g in range(3) for r in range(256)} & set(self.CONTENTS)
        if not dungeon:
            used -= set(self.DUNGEON_ITEMS)
        return [{'value': v, 'name': self.content_name(v)} for v in sorted(used | {current})]

    def objects(self, part):
        dungeon = self._dungeon(part)
        out = []
        for g, room, left, top in self.rooms(part):
            shared = self.users(room, g)
            for r in self.records(room, g):
                row = {'id': f'obj:{room}:{r["index"]}', 'type': r['type'], 'style': 'enemy', 'name': self.type_name(r['type']),
                       'x': left + r['column'] * 16 + 8, 'y': top + r['row'] * 16 + 16,
                       'fields': [{'key': 'type', 'label': 'Swap for', 'value': r['type'],
                                   'choices': self.type_choices(room, r['type'], g, part)}],
                       'remove': 'Remove this object',
                       'note': 'Swaps offer the objects used in this room and the rooms around it, whose pictures are loaded nearby.'}
                if shared > 1:
                    row['note'] += f' This room shares its list with {shared - 1} other rooms, so the change shows there too.'
                out.append(row)
            blocks = self.layout(room, g)
            content = self.contents(room, g)
            if content:
                chest = next((b for b in blocks if b['type'] == 0xA0 and b['run'] == 1), None)
                at = chest['at'] if chest else 0x44
                row = {'id': f'chest:{room}', 'type': 0xA0, 'style': 'item', 'name': 'Chest',
                       'detail': f'holds {self.content_name(content)}',
                       'x': left + (at & 15) * 16 + 8, 'y': top + (at >> 4) * 16 + 16,
                       'fields': [{'key': 'contents', 'label': 'Holds', 'value': content,
                                   'choices': self.content_choices(content, dungeon)}],
                       'remove': None}
                notes = []
                if chest is None:
                    notes.append('This chest is not in the room’s layout; the game puts it there during play, so the box '
                                 'marks the room, not the spot.')
                if content in self.UNIQUE:
                    notes.append('The game needs this item later; giving it away here can make the game impossible to finish.')
                if content == 0x20:
                    notes.append('The game gives 20 Rupees instead once Link has the second sword.')
                if notes:
                    row['note'] = ' '.join(notes)
                out.append(row)
            for b in blocks:
                if b['run'] != 1:
                    continue
                x, y = left + (b['at'] & 15) * 16 + 8, top + (b['at'] >> 4) * 16 + 16
                if g and b['type'] in self.WALLS:
                    out.append({'id': f'wall:{room}:{b["at"]}', 'type': b['type'], 'style': 'secret', 'x': x, 'y': y,
                                'name': 'Bombable wall', 'detail': f'opens the {self.WALLS[b["type"]]} side', 'fields': [],
                                'remove': None})
                elif g and b['type'] == self.HIDDEN_STAIRS:
                    out.append({'id': f'stairs:{room}:{b["at"]}', 'type': b['type'], 'style': 'secret', 'x': x, 'y': y,
                                'name': 'Hidden stairs', 'remove': None,
                                'fields': [{'key': 'block', 'label': 'Stairs', 'value': b['type'],
                                            'choices': [{'value': self.HIDDEN_STAIRS, 'name': 'Hidden until found'},
                                                        {'value': self.STAIRS, 'name': 'Shown from the start'}]}],
                                'note': 'The game draws these stairs only once the room’s flag says they were found.'})
                elif g == 0 and b['type'] == self.CAVE_WALL:
                    out.append({'id': f'cave:{room}:{b["at"]}', 'type': b['type'], 'style': 'secret', 'x': x, 'y': y,
                                'name': 'Bombable cave entrance', 'remove': None,
                                'fields': [{'key': 'block', 'label': 'Entrance', 'value': b['type'],
                                            'choices': [{'value': self.CAVE_WALL, 'name': 'Opened with a bomb'},
                                                        {'value': self.CAVE, 'name': 'Open from the start'}]}]})
        return out

    # ---- edits
    def _in_part(self, part, room):
        if not any(r == room for _, r, _, _ in self.rooms(part)):
            raise ValueError('That is not part of this level any more. Reopen the map.')

    def edit(self, part, object_id, values, remove=False):
        group = self._group_of_part(part)
        kind = object_id.split(':')[0]
        if kind == 'chest':
            room = int(object_id.split(':')[1])
            self._in_part(part, room)
            current = self.contents(room, group)
            if not current or remove:
                raise ValueError('ROMancer cannot change that yet.')
            value = int(values.get('contents', current))
            if not any(c['value'] == value for c in self.content_choices(current, self._dungeon(part))):
                raise ValueError('That choice is not one of the game’s own.')
            offset = self.chest_offset(room, group)
            return {'writes': [(offset, current, value)] if value != current else [],
                    'title': f'Chest holds: {self.content_name(value)} (room {room:02X})',
                    'watch': {'game': 'la', 'kind': 'chest', 'group': group, 'room': room, 'contents': value, 'old': current}}
        if kind in ('stairs', 'cave'):
            _, room, at = object_id.split(':')
            room, at = int(room), int(at)
            self._in_part(part, room)
            allowed = (self.HIDDEN_STAIRS, self.STAIRS) if kind == 'stairs' else (self.CAVE_WALL, self.CAVE)
            block = next((b for b in self.layout(room, group) if b['at'] == at and b['run'] == 1 and b['type'] in allowed), None)
            if block is None or remove:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            value = int(values.get('block', block['type']))
            if value not in allowed:
                raise ValueError('That choice is not one of the game’s own.')
            shown = value in (self.STAIRS, self.CAVE)
            label = ('Stairs shown from the start' if shown else 'Stairs hidden until found') if kind == 'stairs' else \
                    ('Cave open from the start' if shown else 'Cave opened with a bomb')
            return {'writes': [(block['byte'], block['type'], value)] if value != block['type'] else [],
                    'title': f'{label} (room {room:02X})',
                    'watch': {'game': 'la', 'kind': 'block', 'group': group, 'room': room, 'at': at, 'type': value}}
        if kind != 'obj':
            raise ValueError('ROMancer cannot change that yet.')
        _, room, index = object_id.split(':')
        room, index = int(room), int(index)
        if part.get('map') != 'overworld':
            self._in_part(part, room)
        rows = self.records(room, group)
        if not 0 <= index < len(rows):
            raise ValueError('That is not part of this level any more. Reopen the map.')
        row = rows[index]
        watch = {'game': 'la', 'room': room, 'group': group, 'old': row['type']}
        if remove:
            # the list has no gaps: the last record moves into this one's place and the list ends one record sooner
            last, writes = rows[-1], []
            if last is not row:
                for k in range(2):
                    old, new = self.rom[row['byte'] + k], self.rom[last['byte'] + k]
                    if old != new:
                        writes.append((row['byte'] + k, old, new))
            writes.append((last['byte'], self.rom[last['byte']], 0xFF))
            watch.update(kind='remove', type=None)
            return {'writes': writes, 'title': f'Remove {self.type_name(row["type"])} (room {room:02X})', 'watch': watch}
        value = int(values.get('type', row['type']))
        if not any(c['value'] == value for c in self.type_choices(room, row['type'], group, part)):
            raise ValueError('That choice is not one of the game’s own.')
        offset = row['byte'] + 1
        watch.update(kind='type', type=value)
        return {'writes': [(offset, self.rom[offset], value)] if self.rom[offset] != value else [],
                'title': f'Object here: {self.type_name(value)} (room {room:02X})', 'watch': watch}

    def watcher(self, watch):
        if watch.get('kind') == 'chest':
            return _ChestWatcher(self, watch)
        if watch.get('kind') == 'block':
            return _BlockWatcher(self, watch)
        return _ZeldaWatcher(self, watch)


def _la_room(ram):
    """(group, room) Link is in, or None indoors when high RAM is not available."""
    if ram[0x1BA5] == 0:
        return 0, ram[0x1B54]
    hram = getattr(ram, 'domains', {}).get('hram')
    if hram is None or len(hram) < 0x78:
        return None
    return LinksAwakening.group_of_map(hram[0x77]), hram[0x76]


class _ZeldaWatcher(Watcher):
    """Replays the original and then the changed game; 40 frames after Link first stands in the edited room it counts
    the object types in the slots ($C280 state, $C3A0 type). A swap is good when the room has one more of the chosen
    type and one fewer of the old one; a removal when it has one fewer of the old type."""
    compare = True
    every = 2

    def __init__(self, profile, watch):
        self.p, self.w = profile, watch
        self.first, self.counts = {}, {}

    def see(self, ram, frame, run):
        if _la_room(ram) != (self.w.get('group', 0), self.w['room']):
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

    def result(self):
        w = self.w
        old, new = self.counts.get('original'), self.counts.get('changed')
        if old is None or new is None:
            return super().result()
        if w['kind'] == 'remove':
            ok = new.get(w['old'], 0) == old.get(w['old'], 0) - 1
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, the room has one fewer of that object.' if ok
                    else 'Played from the start, the room still has the same objects.'}
        ok = new.get(w['type'], 0) == old.get(w['type'], 0) + 1 and new.get(w['old'], 0) == old.get(w['old'], 0) - 1
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the room now has {self.p.type_name(w["type"])} there.' if ok
                else 'Played from the start, the room does not show the chosen object.'}


class _ChestWatcher(Watcher):
    """A chest's contents show only when the walk opens it: the chest makes object 7 with the contents in $C3B0.
    Good when the chest opened in the edited room gave the chosen contents."""
    every = 2

    def __init__(self, profile, watch):
        self.p, self.w = profile, watch
        self.seen = None

    def see(self, ram, frame, run):
        if _la_room(ram) != (self.w['group'], self.w['room']):
            return False
        for slot in range(16):
            if ram[0x280 + slot] and ram[0x3A0 + slot] == 7:
                self.seen = ram[0x3B0 + slot]
                return True
        return False

    def result(self):
        if self.seen is None:
            return {'state': 'warn', 'text': "The recorded walk didn't open that chest, so the change couldn't be watched in the game."}
        wanted = self.w['contents']
        ok = self.seen == wanted or (wanted == 0x20 and self.seen == 0x1C)
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the chest gave {self.p.content_name(wanted)}.' if ok
                else f'Played from the start, the chest gave {self.p.content_name(self.seen)}, not what was chosen.'}


class _BlockWatcher(Watcher):
    """The room loader writes each block's type to $D711 + position (after the flag changes); 20 frames after Link
    enters the edited room the block there must be the chosen one."""
    every = 2

    def __init__(self, profile, watch):
        self.p, self.w = profile, watch
        self.first, self.seen = None, None

    def see(self, ram, frame, run):
        if _la_room(ram) != (self.w['group'], self.w['room']):
            return False
        if self.first is None:
            self.first = frame
        if frame - self.first < 20:
            return False
        self.seen = ram[0x1711 + self.w['at']]
        return True

    def result(self):
        if self.seen is None:
            return super().result()
        ok = self.seen == self.w['type']
        return {'state': 'good' if ok else 'bad',
                'text': 'Played from the start, the room shows the change.' if ok
                else f'Played from the start, the room has block {self.seen:#04x} there, not the chosen one.'}


PROFILES = [MetroidII, LinksAwakening]
