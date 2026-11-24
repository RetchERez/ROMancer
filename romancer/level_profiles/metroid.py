"""Metroid (USA) and Kid Icarus (USA, Europe) (Rev 1): enemies, items, doors and block roles.

Both games are MMC1 cartridges of eight 16 KB banks with the last bank fixed at $C000; the reading helpers (`_Cart`) are
shared. The level formats differ and each game has its own decoders below, proven separately (research notes:
research/metroid-level-profile.md).
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER = 16


class _Cart:
    """Reading an MMC1 cartridge of 8 banks: bank 7 is fixed at $C000, the others are switched in at $8000."""

    def __init__(self, rom: bytes):
        self.rom = rom

    @staticmethod
    def offset(bank: int, address: int) -> int:
        return HEADER + bank * 0x4000 + (address - (0xC000 if address >= 0xC000 else 0x8000))

    def at(self, bank: int, address: int) -> int:
        return self.rom[self.offset(bank, address)]

    def word(self, bank: int, address: int) -> int:
        return self.at(bank, address) | self.at(bank, address + 1) << 8


def _shift_out(rom: bytes, offsets: list, rest: list, end: int) -> list:
    """Writes that take one record out of a list kept in the ROM: `rest` (the bytes of the records after it), then the
    list's end mark `end`, are written from the removed record's first byte on. `offsets` are the ROM offsets from there."""
    data = list(rest) + [end]
    return [(offsets[k], rom[offsets[k]], value) for k, value in enumerate(data) if rom[offsets[k]] != value]


def _wram(ram, address: int) -> int:
    """A byte of cartridge RAM ($6000-$7FFF): ROMancer's RAM snapshot holds it after the 2 KB of system RAM."""
    return ram[0x800 + address - 0x6000]


# ---------------------------------------------------------------------------------------------------------------- Metroid

class Metroid(_Cart):
    """Metroid (USA). Fixed bank code: room loader $EA2B (room entries $EACA), special items $ED98, world map read $E720.

    The world is one map of 32 x 32 rooms (bank 0 $A53E, copied to $7000 when a game starts); each byte is a room number
    of the area the player is in, $FF is no room. Each area has its own bank and its own rooms: area $74 & 15 picks the
    bank from $CA30 (0 Brinstar bank 1, 1 Norfair bank 2, 2 Kraid's lair bank 4, 3 Tourian bank 3, 4 Ridley's lair bank 5).
    An area bank starts its tables at $9598: special items, room pointers, structure pointers, ...

    A room: one palette byte, structures (3 bytes each) to $FD, then entries to $FF. Entry low nibble: 1 enemy
    [slot << 4 | 1, kind, YX], 2 door [$02, info], 4 elevator [$04, info], 6 statues [$06], 7 enemy pipe [x7, kind, YX].
    Enemy kind: low 6 bits the enemy, bit 7 twice the hit points ($F866), bit 6 only while the area's boss lives.
    Door info: bit 4 the side (0 right, 1 left), bits 0-1 the door (hits from bank $8BD1: 0 five missiles, 1 one shot,
    2 ten missiles, 3 one shot, kept shut in Tourian until the end).

    Special items (per area, sorted by map row then column): [y][next row word], then per room [x][step] and entries to
    0: 1 enemy (3 bytes, as in a room), 2 power-up [$02, item, YX], 3 Mellows, 4 elevator, 5-8 Tourian things, 9 door,
    A palette. Items: 0-7 set gear bit 0-7 of $6878 (6 and 7 rule each other out), 8 an energy tank, 9 five missiles.
    """
    name = 'Metroid'
    sha256 = '88ad02b0b53012712f3c773a62073847551cec191aeda5d3ec19b22b594640eb'
    WORLD = HEADER + 0x253E           # bank 0 $A53E
    AREAS = {0: ('Brinstar', 1), 1: ('Norfair', 2), 2: ('Kraid’s lair', 4), 3: ('Tourian', 3), 4: ('Ridley’s lair', 5)}
    ENTRY_SIZE = {1: 3, 2: 2, 4: 2, 6: 1, 7: 3}
    ITEM_SIZE = {1: 3, 2: 3, 3: 1, 4: 2, 5: 2, 6: 1, 7: 1, 8: 1, 9: 2, 10: 1}
    # power-ups: picked up in a scripted replay (gear bits, tanks, missiles measured) and pictured, trace/v15_profiles/metroid
    ITEMS = {0: 'Bombs', 1: 'High jump boots', 2: 'Long beam', 3: 'Screw attack', 4: 'Maru Mari (morph ball)',
             5: 'Varia suit', 6: 'Wave beam', 7: 'Ice beam', 8: 'Energy tank', 9: 'Missiles (5 more)'}
    DOORS = {0: 'Red door (5 missiles)', 1: 'Blue door (any shot)', 2: 'Orange door (10 missiles)'}
    # enemies by area, from spawning each kind next to Samus and looking at what the game draws
    # (trace/v15_profiles/metroid/shots/enemies_area*.png); "(likely)" where the picture is less certain
    ENEMIES = {
        0: {0x02: 'Ripper', 0x04: 'Skree', 0x05: 'Zoomer', 0x06: 'Rio', 0x03: 'Memu (likely)'},
        1: {0x06: 'Nova (likely)', 0x0C: 'Multiviola (likely)', 0x0D: 'Dragon'},
        2: {0x00: 'Sidehopper', 0x05: 'Zeela (likely)', 0x08: 'Kraid'},
        3: {0x00: 'Metroid (orange)', 0x01: 'Metroid (green)'},
        4: {0x00: 'Holtz (likely)', 0x06: 'Viola (likely)', 0x0C: 'Multiviola (likely)', 0x09: 'Ridley'},
    }
    BOSSES = {2: 0x08, 4: 0x09}

    def __init__(self, rom: bytes):
        super().__init__(rom)
        self._rooms = {}

    # ---- reading
    def bank(self, area: int) -> int:
        return self.AREAS[area][1]

    def cell(self, x: int, y: int) -> int:
        if not (0 <= x < 32 and 0 <= y < 32):
            return 0xFF
        return self.rom[self.WORLD + y * 32 + x]

    def room_count(self, area: int) -> int:
        bank = self.bank(area)
        return (self.word(bank, 0x959C) - self.word(bank, 0x959A)) // 2

    def room(self, area: int, number: int) -> dict:
        """A room's entries: {'pointer', 'entries': [{'at' (CPU address), 'kind', 'bytes'}], 'end' (address of $FF)}."""
        key = (area, number)
        if key in self._rooms:
            return self._rooms[key]
        bank = self.bank(area)
        if not 0 <= number < self.room_count(area):
            raise ValueError('That room is not part of this area.')
        pointer = self.word(bank, self.word(bank, 0x959A) + number * 2)
        at = pointer + 1
        while self.at(bank, at) not in (0xFD, 0xFF):
            at += 1 if self.at(bank, at) == 0xFE else 3
        entries = []
        if self.at(bank, at) == 0xFD:
            at += 1
            while self.at(bank, at) != 0xFF:
                kind = self.at(bank, at) & 15
                size = self.ENTRY_SIZE.get(kind)
                if size is None:
                    break                   # the game stops reading the room's entries here too
                entries.append({'at': at, 'kind': kind, 'bytes': [self.at(bank, at + k) for k in range(size)]})
                at += size
        out = {'pointer': pointer, 'entries': entries, 'end': at if self.at(bank, at) == 0xFF else None}
        self._rooms[key] = out
        return out

    def special(self, area: int, x: int, y: int) -> list:
        """Special items of one map place: [{'at', 'kind', 'bytes'}]."""
        bank = self.bank(area)
        row = self.word(bank, 0x9598)
        for _ in range(32):
            if self.at(bank, row) == y:
                break
            if self.at(bank, row) > y:
                return []
            following = self.word(bank, row + 1)
            if following == 0xFFFF:
                return []
            row = following
        else:
            return []
        place = row + 3
        for _ in range(32):
            here, step = self.at(bank, place), self.at(bank, place + 1)
            if here == x:
                out, at = [], place + 2
                while self.at(bank, at) != 0 and len(out) < 16:
                    kind = self.at(bank, at) & 15
                    size = self.ITEM_SIZE.get(kind, 1)
                    out.append({'at': at, 'kind': kind, 'bytes': [self.at(bank, at + k) for k in range(size)]})
                    at += size
                return out
            if here > x or step == 0xFF:
                return []
            place += step
        return []

    def doors(self, area: int, number: int) -> dict:
        """{side: door type} of a room (side 0 right, 1 left)."""
        return {(e['bytes'][1] >> 4) & 1: e['bytes'][1] & 3 for e in self.room(area, number)['entries'] if e['kind'] == 2}

    def strip(self, area: int, x: int, y: int, way: str) -> list:
        """The map places the screen can scroll through from (x, y) without a door: a row of rooms ended by doors or
        empty places when the game scrolls across, a column ended by empty places when it scrolls up and down."""
        if self.cell(x, y) == 0xFF:
            return []
        out = [(x, y)]
        if way == 'down':
            for step in (-1, 1):
                at = y + step
                while self.cell(x, at) != 0xFF and len(out) < 32:
                    out.append((x, at))
                    at += step
            return sorted(out, key=lambda p: p[1])
        for step in (-1, 1):
            at = x
            while len(out) < 32:
                here, there = self.cell(at, y), self.cell(at + step, y)
                if there == 0xFF:
                    break
                try:
                    blocked = (0 if step > 0 else 1) in self.doors(area, here) or (1 if step > 0 else 0) in self.doors(area, there)
                except ValueError:
                    break
                if blocked:
                    break
                at += step
                out.append((at, y))
        return sorted(out)

    def enemy_name(self, area: int, kind: int) -> str:
        base = self.ENEMIES.get(area, {}).get(kind & 0x3F)
        name = base or f'Enemy {kind & 0x3F:#04x}'
        if kind & 0x80:
            name += ', tough'
        return name

    def enemy_kinds(self, area: int) -> list:
        """Every enemy kind byte the area's own rooms use (not its bosses)."""
        kinds = set()
        for number in range(self.room_count(area)):
            for e in self.room(area, number)['entries']:
                if e['kind'] == 1:
                    kinds.add(e['bytes'][1])
        boss = self.BOSSES.get(area)
        return sorted(k for k in kinds if not k & 0x40 and (k & 0x3F) != boss)

    # ---- edits
    def remove_entry(self, area: int, number: int, index: int) -> list:
        """Writes that take one entry out of a room: the later entries move up and the list ends earlier."""
        bank = self.bank(area)
        room = self.room(area, number)
        if room['end'] is None:
            raise ValueError('ROMancer cannot remove things from this room.')
        entries = room['entries']
        start = entries[index]['at']
        rest = [b for e in entries[index + 1:] for b in e['bytes']]
        return _shift_out(self.rom, [self.offset(bank, start + k) for k in range(len(rest) + 1)], rest, 0xFF)


class _MetroidWatcher(Watcher):
    """Watches the replay for the room of an edit, then reads what the game loaded there."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.reached = False

    @staticmethod
    def camera(ram):
        way = ram[0x49]
        mx, my = ram[0x50], ram[0x4F]
        if way >= 2:
            return (mx - (1 if way == 3 and ram[0xFD] else 0)) * 256 + ram[0xFD], my * 240
        return mx * 256, (my - (1 if way == 1 and ram[0xFC] else 0)) * 240 + ram[0xFC]

    def here(self, ram) -> bool:
        """The edit's room is on screen (more than half of it)."""
        w = self.w
        if ram[0x1E] != 3 or (ram[0x74] & 15) != w['area']:
            return False
        cx, cy = self.camera(ram)
        return abs(cx - w['mx'] * 256) < 128 and abs(cy - w['my'] * 240) < 120

    def near(self, ram) -> bool:
        w = self.w
        if ram[0x1E] != 3 or (ram[0x74] & 15) != w['area']:
            return False
        cx, cy = self.camera(ram)
        return abs(cx - w['mx'] * 256) <= 256 and abs(cy - w['my'] * 240) <= 240


class _EnemyWatcher(_MetroidWatcher):
    """An enemy's slot (the entry's high nibble) right after the game loads it at its place: the kind it got, or for a
    removal, that nothing was loaded there while the room was on screen."""

    def see(self, ram, frame, run):
        w = self.w
        if not self.near(ram):
            return False
        slot = w['slot']
        status = _wram(ram, 0x6AF4 + slot)
        placed = status and ram[0x400 + slot] == w['spawn_y'] and ram[0x401 + slot] == w['spawn_x']
        if placed:
            kind = _wram(ram, 0x6B02 + slot) | (ram[0x40F + slot] & 0xC0)
            self.seen = kind
            if w['kind'] is not None:
                return kind == w['kind']
            return True
        if self.here(ram):
            self.reached = True
            if w['kind'] is None and self.seen is None:
                self.seen = 'none'
                return True
        return False

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if w['kind'] is None:
            ok = self.seen == 'none'
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, no enemy appears there any more.' if ok
                    else 'Played from the start, an enemy still appears there.'}
        if self.seen == 'none':
            return {'state': 'bad', 'text': 'Played from the start, no enemy appeared there.'}
        ok = self.seen == w['kind']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game now puts {w["name"]} there.' if ok
                else f'Played from the start, the game put enemy {self.seen & 0x3F:#04x}{" (tough)" if self.seen & 0x80 else ""} there, not the one chosen.'}


class _DoorWatcher(_MetroidWatcher):
    """The door slot the game uses for that room and side ($EC00): which door it loaded."""

    def see(self, ram, frame, run):
        w = self.w
        if not self.near(ram):
            return False
        slot = w['slot']
        if ram[0x300 + slot] and ram[0x30E + slot] == (0x10 if w['side'] else 0xF0):
            self.seen = ram[0x307 + slot] & 3
            return self.seen == w['door'] or self.here(ram)
        return False

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        ok = self.seen == w['door']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game now loads the chosen door there ({w["name"].lower()}).' if ok
                else f'Played from the start, the game loaded door type {self.seen} there, not the one chosen.'}


class _ItemWatcher(_MetroidWatcher):
    """The power-up slots ($0748 and $0750, 8 bytes each) once the game has loaded the item's room."""

    def see(self, ram, frame, run):
        w = self.w
        if not self.near(ram):
            return False
        for slot in (0x748, 0x750):
            if ram[slot] != 0xFF and ram[slot + 1] == w['spawn_y'] and ram[slot + 2] == w['spawn_x']:
                self.seen = ram[slot]
                return self.seen == w['item'] or self.here(ram)
        return False

    def result(self):
        w = self.w
        if self.seen is None:
            return {'state': 'warn', 'text': "The recorded walk doesn't reach this item (or it was already taken), so the change couldn't be watched in the game. Use Play from here to try it yourself."}
        ok = self.seen == w['item']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the item there is now {w["name"]}.' if ok
                else f'Played from the start, the game put item {self.seen} there, not the one chosen.'}


class MetroidProfile(Metroid, Profile):
    """Metroid on the common profile interface. A part is the row (or column) of rooms the screen scrolls through:
    {'area', 'x', 'y' (map place of the first room seen), 'way' ('across' or 'down')}; its pixels are the area's map
    pixels (256 x 240 a room), so x is the camera's map x."""
    sha256s = (Metroid.sha256,)
    DOOR_SLOTS = (0x80, 0xB0, 0xA0, 0x90)          # $EC00
    _area = None

    def where(self, ram):
        if ram[0x1E] != 3:                          # not playing (title, map screens, game over)
            return None
        area = ram[0x74] & 15
        if area not in self.AREAS:
            return None
        self._area = ram[0x74]
        cx, cy = _MetroidWatcher.camera(ram)
        way = 'across' if ram[0x49] >= 2 else 'down'
        return {'part': {'area': area, 'x': cx // 256, 'y': cy // 240, 'way': way}, 'x': cx, 'y': cy}

    def part_name(self, part):
        return f'{self.AREAS[int(part["area"])][0]}, rooms from map place {part["x"]}, {part["y"]}'

    def choices(self):
        out = {'items': [{'value': k, 'name': v} for k, v in self.ITEMS.items()],
               'doors': [{'value': k, 'name': v} for k, v in self.DOORS.items()]}
        for area in self.AREAS:
            out[f'enemies{area}'] = [{'value': k, 'name': self.enemy_name(area, k)} for k in self.enemy_kinds(area)]
        return out

    def objects(self, part):
        area, way = int(part['area']), part.get('way', 'across')
        out = []
        for mx, my in self.strip(area, int(part['x']), int(part['y']), way):
            number = self.cell(mx, my)
            try:
                room = self.room(area, number)
            except ValueError:
                continue
            shared = (f'Rooms in this game share their layout wherever the map shows the same room, so every place that shows '
                      f'room {number} of {self.AREAS[area][0]} gets the change.')
            ox, oy = mx * 256, my * 240
            for index, e in enumerate(room['entries']):
                b = e['bytes']
                row = None
                if e['kind'] == 1:
                    kind, yx = b[1], b[2]
                    row = {'id': f'enemy:{mx}:{my}:{index}', 'style': 'enemy', 'type': kind & 0x7F, 'name': self.enemy_name(area, kind),
                           'x': ox + (yx & 15) * 16 + 8, 'y': oy + (yx >> 4) * 16 + 16, 'remove': 'Remove this enemy',
                           'fields': [{'key': 'kind', 'label': 'Swap for', 'value': kind, 'choices': f'enemies{area}'}]}
                    if kind & 0x40:
                        row['detail'] = 'only while the area’s boss lives'
                        row['fields'], row['remove'] = [], None
                elif e['kind'] == 7:
                    kind, yx = b[1], b[2]
                    row = {'id': f'pipe:{mx}:{my}:{index}', 'style': 'enemy', 'type': 0x100 | kind, 'name': 'Enemy pipe',
                           'detail': f'sends out enemy {kind & 0x3F:#04x}', 'x': ox + (yx & 15) * 16 + 8, 'y': oy + (yx >> 4) * 16 + 16,
                           'remove': None, 'fields': []}
                elif e['kind'] == 2:
                    side, door = (b[1] >> 4) & 1, b[1] & 3
                    row = {'id': f'door:{mx}:{my}:{index}', 'style': 'block', 'type': 'door', 'x': ox + (16 if side else 240),
                           'y': oy + 128, 'name': self.DOORS.get(door, 'Blue door (shut in Tourian until the end)'),
                           'detail': 'on the left of the room' if side else 'on the right of the room', 'remove': None,
                           'fields': [{'key': 'door', 'label': 'Door', 'value': door, 'choices': 'doors'}] if door in self.DOORS else []}
                if row:
                    if shared:
                        row['note'] = shared
                    out.append(row)
            for index, e in enumerate(self.special(area, mx, my)):
                b = e['bytes']
                if e['kind'] == 2 and len(b) == 3:
                    item, yx = b[1], b[2]
                    out.append({'id': f'item:{mx}:{my}:{index}', 'style': 'item', 'type': item,
                                'name': self.ITEMS.get(item, f'Item {item:#04x}'), 'x': ox + (yx & 15) * 16 + 8,
                                'y': oy + (yx >> 4) * 16 + 16, 'remove': None,
                                'fields': [{'key': 'item', 'label': 'Holds', 'value': item, 'choices': 'items'}]})
                elif e['kind'] == 1:
                    kind, yx = b[1], b[2]
                    out.append({'id': f'special:{mx}:{my}:{index}', 'style': 'enemy', 'type': kind & 0x7F,
                                'name': self.enemy_name(area, kind), 'x': ox + (yx & 15) * 16 + 8, 'y': oy + (yx >> 4) * 16 + 16,
                                'remove': None, 'fields': [{'key': 'kind', 'label': 'Swap for', 'value': kind, 'choices': f'enemies{area}'}]})
        return out

    def edit(self, part, object_id, values, remove=False):
        area = int(part['area'])
        bank = self.bank(area)
        kind, mx, my, index = object_id.split(':')
        mx, my, index = int(mx), int(my), int(index)
        if kind in ('enemy', 'pipe', 'door'):
            number = self.cell(mx, my)
            entries = self.room(area, number)['entries']
            if not 0 <= index < len(entries):
                raise ValueError('That is not part of this room any more. Reopen the map.')
            entry = entries[index]
        else:
            entries = self.special(area, mx, my)
            if not 0 <= index < len(entries):
                raise ValueError('That is not part of this room any more. Reopen the map.')
            entry = entries[index]
        b = entry['bytes']
        wanted = {'enemy': 1, 'door': 2, 'special': 1, 'item': 2}.get(kind)
        if wanted is None or entry['kind'] != wanted or (kind == 'item' and len(b) != 3):
            raise ValueError('ROMancer cannot change that yet.')
        base = {'area': area, 'mx': mx, 'my': my}
        if kind in ('enemy', 'special'):
            slot, yx = b[0] & 0xF0, b[2]
            spawn = {'slot': slot, 'spawn_y': (yx & 0xF0) | 8, 'spawn_x': (yx << 4 & 0xF0) | 0x0C}
            if remove:
                if kind == 'special':
                    raise ValueError('That cannot be removed.')
                return {'writes': self.remove_entry(area, number, index), 'title': f'Remove the enemy (map place {mx}, {my})',
                        'watch': {'kind': 'enemy', **base, **spawn, 'want': None, 'name': ''}}
            new = int(values.get('kind'))
            if new not in self.enemy_kinds(area):
                raise ValueError('That choice is not one of the game’s own.')
            name = self.enemy_name(area, new)
            offset = self.offset(bank, entry['at'] + 1)
            writes = [(offset, self.rom[offset], new)] if self.rom[offset] != new else []
            return {'writes': writes, 'title': f'Enemy here: {name} (map place {mx}, {my})',
                    'watch': {'kind': 'enemy', **base, **spawn, 'want': new, 'name': name}}
        if kind == 'door':
            door = int(values.get('door'))
            if door not in self.DOORS:
                raise ValueError('That choice is not one of the game’s own.')
            offset = self.offset(bank, entry['at'] + 1)
            old = self.rom[offset]
            new = (old & 0xFC) | door
            side = (old >> 4) & 1
            slot = self.DOOR_SLOTS[(((mx + my) << 1) | side) & 3]
            return {'writes': [(offset, old, new)] if old != new else [], 'title': f'{self.DOORS[door]} (map place {mx}, {my})',
                    'watch': {'kind': 'door', **base, 'slot': slot, 'side': side, 'door': door, 'name': self.DOORS[door]}}
        if kind == 'item':
            item = int(values.get('item'))
            if item not in self.ITEMS:
                raise ValueError('That choice is not one of the game’s own.')
            offset = self.offset(bank, entry['at'] + 1)
            yx = b[2]
            return {'writes': [(offset, self.rom[offset], item)] if self.rom[offset] != item else [],
                    'title': f'Item here: {self.ITEMS[item]} (map place {mx}, {my})',
                    'watch': {'kind': 'item', **base, 'item': item, 'name': self.ITEMS[item],
                              'spawn_y': (yx & 0xF0) | 8, 'spawn_x': (yx << 4 & 0xF0) | 8}}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        kind = watch['kind']
        if kind == 'enemy':
            return _EnemyWatcher(dict(watch, kind=watch['want']))
        if kind == 'door':
            return _DoorWatcher(watch)
        if kind == 'item':
            return _ItemWatcher(watch)
        return Watcher()

    def tile_role(self, tile):
        """Blocks by tile number ($D60E, $D651, $DB63): $A0 and up are open; below $A0 is solid, and from $70 (from $80
        in Brinstar once it has been entered by elevator) it can be shot or bombed away and grows back."""
        if tile >= 0xA0:
            return 'open'
        if tile >= (0x80 if self._area == 0x10 else 0x70):
            return 'breakable'
        return 'solid'


# ------------------------------------------------------------------------------------------------------------ Kid Icarus

class KidIcarus(_Cart):
    """Kid Icarus (USA, Europe) (Rev 1). World 1 keeps its level data in bank 6 and the game copies $0F00 bytes of it
    to cartridge RAM $7000 when the world starts (bank 6 $98D0; source words at $9907: $9940 while $A0 is 2, world 1;
    $A790 while $A0 is 6, laid out differently and not decoded); the stage code (bank 2) reads the copy.

    In the copy: $7BF0 + stage * 2 -> the stage's screen list (a word per screen, $FFFF ends it); a screen is one byte,
    then structures [YX, structure, palette] to $FD. $7B60, $7B80, $7BA0 and $7BC0 are four lists of up to 8 records
    [stage, screen, scroll, 0] ($FF ends a list; bank 2 $8B51): when the stage ($0130), the screen ($04D1) and the fine
    scroll ($FD) match a record, the game starts object $78 in that list's slot ($0760, $0770, $0780, $0790).
    """
    name = 'Kid Icarus'
    sha256 = '335d09f48e5ebb1d7123d1599c5867b9e52b5b4393b7ad92c39cf6a064424233'
    WORLDS = {1: (2, 0x9940)}                       # world: ($A0 while playing it, start of its data in bank 6)
    LISTS = (0x7B60, 0x7B80, 0x7BA0, 0x7BC0)

    def copy_offset(self, world: int, address: int) -> int:
        """ROM offset of a byte of the world's data, by its address in the copy the game reads ($7000-$7EFF)."""
        if not 0x7000 <= address < 0x7F00:
            raise ValueError('That is not part of the world data.')
        return self.offset(6, self.WORLDS[world][1] + address - 0x7000)

    def ram_byte(self, world: int, address: int) -> int:
        return self.rom[self.copy_offset(world, address)]

    def stage_screens(self, world: int, stage: int) -> list:
        """RAM addresses of a stage's screens, in the order of the game's screen number $04D1."""
        table = self.ram_byte(world, 0x7BF0 + stage * 2) | self.ram_byte(world, 0x7BF1 + stage * 2) << 8
        out = []
        for k in range(64):
            if not 0x7000 <= table + 2 * k + 1 < 0x7F00:
                break
            word = self.ram_byte(world, table + 2 * k) | self.ram_byte(world, table + 2 * k + 1) << 8
            if word == 0xFFFF or not 0x7000 <= word < 0x7F00:
                break
            out.append(word)
        return out

    def spawns(self, world: int) -> list:
        """Every record of the four lists: {'list', 'number', 'stage', 'screen', 'scroll', 'at' (RAM address)}."""
        out = []
        for k, start in enumerate(self.LISTS):
            for n in range(8):
                at = start + 4 * n
                first = self.ram_byte(world, at)
                if first == 0xFF:
                    break
                out.append({'list': k, 'number': n, 'stage': first, 'screen': self.ram_byte(world, at + 1),
                            'scroll': self.ram_byte(world, at + 2), 'at': at})
        return out

    def remove_spawn(self, world: int, list_number: int, number: int) -> list:
        start = self.LISTS[list_number]
        count = sum(1 for r in self.spawns(world) if r['list'] == list_number)
        if not 0 <= number < count:
            raise ValueError('That is not part of this stage any more. Reopen the map.')
        rest = [self.ram_byte(world, start + 4 * (number + 1) + k) for k in range(4 * (count - number - 1))]
        offsets = [self.copy_offset(world, start + 4 * number + k) for k in range(len(rest) + 1)]
        return _shift_out(self.rom, offsets, rest, 0xFF)


class _SpawnWatcher(Watcher):
    """A removed record: the list's slot ($0760 + 16 * list) must not get object $78 when the stage, screen and scroll
    of the record come by."""
    every = 1

    def __init__(self, watch):
        self.w, self.reached, self.spawned = watch, False, False

    def see(self, ram, frame, run):
        w = self.w
        if ram[0xA0] != w['mode'] or ram[0x130] != w['stage'] or ram[0x4D1] != w['screen']:
            return False
        slot = 0x760 + 16 * w['list']
        if ram[0xFD] == w['scroll']:
            self.reached = True
        if self.reached and ram[slot + 1] == 0x78 and ram[slot] < 8:
            self.spawned = True
            return True
        return False

    def result(self):
        if not self.reached:
            return super().result()
        ok = not self.spawned
        return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, nothing starts there any more.' if ok
                else 'Played from the start, the object still starts there.'}


class KidIcarusProfile(KidIcarus, Profile):
    """Kid Icarus on the common profile interface, for world 1. A part is {'world', 'stage'}; its pixels
    have y 0 at the top of the screen the stage starts on and grow downwards (the screens above are negative)."""
    sha256s = (KidIcarus.sha256,)
    START_SCROLL = 0xEE                                  # $FD when a stage starts (bank 2 $971D)

    def where(self, ram):
        world = next((w for w, (mode, _) in self.WORLDS.items() if ram[0xA0] == mode), None)
        if world is None or ram[0x3A] >= 0x10:          # title and menus, the other worlds and fortresses, chambers
            return None
        y = -(ram[0x4D1] - 1) * 240 + ram[0xFD] - self.START_SCROLL
        return {'part': {'world': world, 'stage': ram[0x130]}, 'x': 0, 'y': y}

    def part_name(self, part):
        return f'Stage {part["world"]}-{int(part["stage"]) + 1}'

    def objects(self, part):
        world, stage = int(part['world']), int(part['stage'])
        out = []
        for r in self.spawns(world):
            if r['stage'] != stage:
                continue
            out.append({'id': f'spawn:{r["list"]}:{r["number"]}', 'style': 'enemy', 'type': 0x78, 'name': 'Object 0x78',
                        'detail': f'starts at the top of the screen when screen {r["screen"]} has scrolled to {r["scroll"]}',
                        'x': 128, 'y': -(r['screen'] - 1) * 240 + r['scroll'] - self.START_SCROLL + 16,
                        'remove': 'Remove this', 'fields': []})
        return out

    def edit(self, part, object_id, values, remove=False):
        world, stage = int(part['world']), int(part['stage'])
        kind, list_number, number = object_id.split(':')
        if kind != 'spawn' or not remove:
            raise ValueError('ROMancer cannot change that yet.')
        record = next((r for r in self.spawns(world) if r['list'] == int(list_number) and r['number'] == int(number)), None)
        if record is None or record['stage'] != stage:
            raise ValueError('That is not part of this stage any more. Reopen the map.')
        return {'writes': self.remove_spawn(world, int(list_number), int(number)),
                'title': f'Remove object 0x78 (screen {record["screen"]})',
                'watch': {'kind': 'spawn', 'mode': self.WORLDS[world][0], 'stage': stage, 'screen': record['screen'],
                          'scroll': record['scroll'], 'list': int(list_number)}}

    def watcher(self, watch):
        return _SpawnWatcher(watch) if watch.get('kind') == 'spawn' else Watcher()


PROFILES = [MetroidProfile, KidIcarusProfile]
