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
        return {'part': {'area': area}, 'x': left, 'y': top}

    def part_name(self, part):
        return f'Map {part["area"] - 8}'

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

    The overworld is 16 by 16 screens of 160 by 128 pixels; the room number is screen y * 16 + screen x (walking
    right adds 1, walking down adds 16). Work RAM $DBA5 is 0 outdoors and $DB54 holds the overworld room. Each room's
    objects come from bank $16 (loader $36EE, bank 0): the word at $4000 + room * 2 points at a list of 2-byte records
    [position, type] ending with $FF; the position byte's high nibble is the block row and its low nibble the block
    column (16-pixel blocks). The loader puts them in the object slots: type $C3A0, state $C280, x $C200 (column * 16
    + 8), y $C210 (row * 16 + 16). Rooms indoors use the tables at $4200 and $4400, but which indoor room is shown is
    kept only in high RAM ($FFF6 / $FFF7), outside the work RAM ROMancer reads, so indoor rooms are not placed yet.
    """
    name = "The Legend of Zelda - Link's Awakening"
    sha256s = ('ed42628d5cd8c73a6f8c6a8965f19674876a4fa04e616834e26b81b35963ad87',)
    system = 'gb'
    OBJ_BANK = 0x16
    TABLE = 0x4000
    W, H = 160, 128
    # named only from pictures the game drew in a recorded walk (research notes); others show their number
    NAMES = {0x6E: 'Butterfly'}

    def _b(self, address):
        return self.rom[_file(self.OBJ_BANK, address)]

    def list_address(self, room):
        return self._b(self.TABLE + room * 2) | self._b(self.TABLE + room * 2 + 1) << 8

    def records(self, room):
        address, out = self.list_address(room), []
        while self._b(address) != 0xFF and len(out) < 16:
            at = self._b(address)
            out.append({'index': len(out), 'row': at >> 4, 'column': at & 15, 'type': self._b(address + 1),
                        'byte': _file(self.OBJ_BANK, address)})
            address += 2
        return out

    def users(self, room):
        pointer = self.list_address(room)
        return sum(1 for other in range(256) if self.list_address(other) == pointer)

    def type_name(self, kind):
        return self.NAMES.get(kind, f'Object {kind:#04x}')

    def neighbours(self, room):
        y, x = room >> 4, room & 15
        kinds = set()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if 0 <= y + dy < 16 and 0 <= x + dx < 16:
                    kinds |= {r['type'] for r in self.records((y + dy) * 16 + x + dx)}
        return kinds

    def type_choices(self, room, kind):
        return [{'value': k, 'name': self.type_name(k)} for k in sorted(self.neighbours(room) | {kind})]

    def where(self, ram):
        if ram[0x1BA5] != 0:
            return None
        room = ram[0x1B54]
        return {'part': {'map': 'overworld'}, 'x': (room & 15) * self.W, 'y': (room >> 4) * self.H}

    def part_name(self, part):
        return 'Overworld'

    def objects(self, part):
        if part.get('map') != 'overworld':
            return []
        out = []
        for room in range(256):
            shared = self.users(room)
            for r in self.records(room):
                row = {'id': f'obj:{room}:{r["index"]}', 'type': r['type'], 'style': 'enemy', 'name': self.type_name(r['type']),
                       'x': (room & 15) * self.W + r['column'] * 16 + 8, 'y': (room >> 4) * self.H + r['row'] * 16 + 16,
                       'fields': [{'key': 'type', 'label': 'Swap for', 'value': r['type'],
                                   'choices': self.type_choices(room, r['type'])}],
                       'remove': 'Remove this object',
                       'note': 'Swaps offer the objects used in this room and the rooms around it, whose pictures are loaded nearby.'}
                if shared > 1:
                    row['note'] += f' This room shares its list with {shared - 1} other rooms, so the change shows there too.'
                out.append(row)
        return out

    def _spot(self, object_id):
        kind, room, index = object_id.split(':')
        rows = self.records(int(room))
        if kind != 'obj' or not 0 <= int(index) < len(rows):
            raise ValueError('That is not part of this level any more. Reopen the map.')
        return int(room), rows, rows[int(index)]

    def edit(self, part, object_id, values, remove=False):
        room, rows, row = self._spot(object_id)
        watch = {'game': 'la', 'room': room, 'old': row['type']}
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
        kind = int(values.get('type', row['type']))
        if not any(c['value'] == kind for c in self.type_choices(room, row['type'])):
            raise ValueError('That choice is not one of the game’s own.')
        offset = row['byte'] + 1
        watch.update(kind='type', type=kind)
        return {'writes': [(offset, self.rom[offset], kind)] if self.rom[offset] != kind else [],
                'title': f'Object here: {self.type_name(kind)} (room {room:02X})', 'watch': watch}

    def watcher(self, watch):
        return _ZeldaWatcher(self, watch)


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
        if ram[0x1BA5] != 0 or ram[0x1B54] != self.w['room']:
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


PROFILES = [MetroidII, LinksAwakening]
