"""More Super Nintendo games: Mega Man X (USA) (Rev 1) and Super Castlevania IV (USA).

Both cartridges are LoROM without a copier header: CPU address $BB:8000-$BB:FFFF is ROM offset (BB & $7F) * $8000 +
(address & $7FFF). The snapshots give the system RAM as 'wram' (index 0 is $7E:0000).

Only the object lists are changed here (which object, what it holds, or one entry taken out); the level layouts are
left alone. Research notes: research/snes_more-level-profile.md; scratch scripts and pictures:
trace/v15_profiles/snes_more/.
"""
from __future__ import annotations

from . import Profile, Watcher


def lorom(address: int) -> int:
    """ROM offset of a LoROM CPU address (banks $80-$FF mirror $00-$7F)."""
    return ((address >> 16) & 0x7F) * 0x8000 + (address & 0x7FFF)


def _w(data, offset: int) -> int:
    return data[offset] | data[offset + 1] << 8


# --------------------------------------------------------------------------------------------- Mega Man X

class MegaManX:
    """Mega Man X (USA) (Rev 1). Level number $1F7A (0 = the highway, 1-8 the eight stages, 9-12 the fortress).

    Object list ($80DB71): $85:82C2 + level * 2 points (bank $85) at the level's list. It is grouped by 32-pixel
    column: a column byte, then 7-byte entries (type, y low, y high, id, sub, x low, x high | flags); bit 7 of the
    last byte ends the column's group. The list ends with a column byte equal to the one before it. The lists of the
    13 levels follow each other with no room between them.
    The loader copies the list into RAM at $7E:FA02 (5 bytes per entry, in list order); the spawner ($80DD26) puts an
    entry in a slot of its type ($8282AC): type 0 $1628 + n * $30 (items and level parts), type 1 $1928 + n * $20,
    type 2 $1D08 + n * $10 (camera, graphics and palette events), type 3 $0E68 + n * $40 (enemies). The slot gets
    +$0A id, +$0B sub, +5 x, +8 y and +$0C the entry's RAM address ($FA02 + 5 * index).
    Graphics: type 2 id $15 (handler $83FD7B) loads a graphics set when Mega Man passes it ($1F08 = high nibble of
    sub going right, low nibble going left; $80B071 decompresses the sets of that number), so an enemy only draws right
    where its graphics are loaded. Swaps are offered between enemies placed under the same graphics load.
    """
    name = 'Mega Man X'
    sha256 = 'b8f70a6e7fb93819f79693578887e2c11e196bdf1ac6ddc7cb924b1ad0be2d32'
    LISTS = 0x8582C2
    LEVELS = 13
    ENTRY_RAM = 0xFA02
    LEVEL_NAMES = ['Highway', 'Stage 1 (sea)', 'Stage 2 (forest)', 'Stage 3 (factory)', 'Stage 4', 'Stage 5',
                   'Stage 6', 'Stage 7', 'Stage 8 (snow)', 'Fortress 1', 'Fortress 2', 'Fortress 3', 'Fortress 4']
    # Enemies named from what the game drew when they spawned (trace/v15_profiles/snes_more/survey2, sheet_survey.png)
    ENEMY_NAMES = {0x15: 'Spiky', 0x22: 'Bee Blader', 0x29: 'Gun Volt', 0x0B: 'Axe Max', 0x0F: 'Flying spiked pod',
                   0x2D: 'Batton Bone', 0x04: 'Tall walker', 0x51: 'Snowmobile rider', 0x49: 'Crane claw',
                   0x33: 'Zero'}
    # Items: each was put in the highway's list and picked up (mmxitem.py): what changed in RAM is in the notes
    ITEMS = {(0x02, 0x80): 'Large life energy', (0x02, 0x82): 'Small life energy', (0x04, 0x80): '1-Up',
             (0x0B, None): 'Heart Tank', (0x05, None): 'Sub Tank'}
    COMMON_ITEMS = [(0x02, 0x80), (0x02, 0x82), (0x04, 0x80)]
    SLOTS = {0: (0x1628, 0x30, 16), 1: (0x1928, 0x20, 31), 2: (0x1D08, 0x10, 16), 3: (0x0E68, 0x40, 15)}

    def __init__(self, rom: bytes):
        self.rom = rom
        self._cache = {}

    def b(self, address: int) -> int:
        return self.rom[lorom(address)]

    def w(self, address: int) -> int:
        return self.b(address) | self.b(address + 1) << 8

    def list_start(self, level: int) -> int:
        """ROM offset of a level's list."""
        return lorom(0x850000 | self.w(self.LISTS + level * 2))

    def entries(self, level: int) -> list:
        """[{'index', 'offset', 'col', 'type', 'y', 'id', 'sub', 'x', 'b6'}] in list order; also caches the end."""
        if ('list', level) in self._cache:
            return self._cache[('list', level)]
        rom, p = self.rom, self.list_start(level)
        out, last = [], None
        for _ in range(300):
            col = rom[p]
            if col == last:
                break
            last = col
            p += 1
            for _ in range(64):
                e = rom[p:p + 7]
                out.append({'index': len(out), 'offset': p, 'col': col, 'type': e[0], 'y': e[1] | e[2] << 8,
                            'id': e[3], 'sub': e[4], 'x': e[5] | (e[6] & 0x1F) << 8, 'b6': e[6]})
                p += 7
                if e[6] & 0x80:
                    break
        self._cache[('end', level)] = p           # the closing column byte
        self._cache[('list', level)] = out
        return out

    def list_bytes(self, entries: list) -> bytes:
        """The list as the game reads it: column groups, the last entry of each with bit 7, then the closing byte."""
        out, i = bytearray(), 0
        while i < len(entries):
            col = entries[i]['col']
            group = [e for e in entries[i:] if e['col'] == col]
            j = i
            while j < len(entries) and entries[j]['col'] == col:
                j += 1
            group = entries[i:j]
            out.append(col)
            for k, e in enumerate(group):
                b6 = (e['b6'] & 0x7F) | (0x80 if k == len(group) - 1 else 0)
                out += bytes([e['type'], e['y'] & 0xFF, e['y'] >> 8, e['id'], e['sub'], e['x'] & 0xFF, b6])
            i = j
        out.append(entries[-1]['col'] if entries else 0)
        return bytes(out)

    def remove_writes(self, level: int, index: int) -> list:
        entries = self.entries(level)
        if len(entries) < 2:
            raise ValueError('That is the only thing in this level’s list, so ROMancer leaves it.')
        start = self.list_start(level)
        new = self.list_bytes([e for e in entries if e['index'] != index])
        old = self.rom[start:start + len(new)]
        return [(start + i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]

    def count(self) -> dict:
        """How many times each (type, id) is placed in the whole game."""
        if 'count' not in self._cache:
            c = {}
            for level in range(self.LEVELS):
                for e in self.entries(level):
                    c[(e['type'], e['id'])] = c.get((e['type'], e['id']), 0) + 1
            self._cache['count'] = c
        return self._cache['count']

    def segment(self, level: int, e: dict):
        """The graphics load in effect where an entry is: the nearest type 2 id $15 event to its left (within 256 px
        up or down), and for climbing parts the nearest id $18 event below it (same rule turned on its side)."""
        best15 = best18 = None
        for ev in self.entries(level):
            if ev['type'] != 2:
                continue
            if ev['id'] == 0x15 and ev['x'] <= e['x'] and abs(ev['y'] - e['y']) < 0x100:
                if best15 is None or ev['x'] > best15['x']:
                    best15 = ev
            if ev['id'] == 0x18 and ev['y'] >= e['y'] and abs(ev['x'] - e['x']) < 0x100:
                if best18 is None or ev['y'] < best18['y']:
                    best18 = ev
        return (best15['sub'] >> 4 if best15 else None, best18['sub'] >> 4 if best18 else None)

    def editable_enemy(self, e: dict) -> bool:
        """Enemies the game places more than once (a single one is a boss or a scripted part)."""
        return e['type'] == 3 and self.count().get((3, e['id']), 0) > 1 and e['id'] != 0x33

    def enemy_choices(self, level: int, e: dict) -> list:
        seg = self.segment(level, e)
        seen = []
        for other in self.entries(level):
            if self.editable_enemy(other) and self.segment(level, other) == seg and (other['id'], other['sub']) not in seen:
                seen.append((other['id'], other['sub']))
        return sorted(seen)

    def enemy_name(self, number: int, sub: int | None = None) -> str:
        name = self.ENEMY_NAMES.get(number, f'Enemy {number:#04x}')
        return name if sub in (None, 0) else f'{name} (setting {sub:#04x})'

    def item_name(self, number: int, sub: int) -> str:
        return self.ITEMS.get((number, sub)) or self.ITEMS.get((number, None)) or f'Object {number:#04x}'

    def is_item(self, e: dict) -> bool:
        return e['type'] == 0 and ((e['id'], e['sub']) in self.ITEMS or (e['id'], None) in self.ITEMS)


class _MmxWatcher(Watcher):
    """A Mega Man X edit. A swap is seen when a slot of the entry's type holds the entry's RAM address (+$0C) and the
    chosen id and sub (+$0A, +$0B). A removal is seen when the screen has been over the spot for 30 looks and no slot
    of that type first showed the old id and sub there (within 8 px)."""
    every = 3

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.reached = 0
        self.slots = {}

    def see(self, ram, frame, run):
        w = self.w
        if ram[0xD1] != 2 or ram[0xD2] != 4 or ram[0x1F7A] != w['level']:
            return False
        base, size, count = MegaManX.SLOTS[w['type']]
        if w['remove']:
            for n in range(count):
                s = base + n * size
                if not ram[s]:
                    self.slots.pop(s, None)
                    continue
                key = (ram[s + 0xA], ram[s + 0xB], _w(ram, s + 0xC))
                if self.slots.get(s) == key:
                    continue
                self.slots[s] = key
                if key[:2] == (w['id'], w['sub']) and abs(_w(ram, s + 5) - w['x']) <= 8 and abs(_w(ram, s + 8) - w['y']) <= 8:
                    self.seen = 'there'
                    return True
            cx, cy = _w(ram, 0x1E4D), _w(ram, 0x1E50)
            if cx <= w['x'] <= cx + 256 and cy <= w['y'] <= cy + 224:
                self.reached += 1
                if self.reached > 30:
                    self.seen = 'gone'
                    return True
            return False
        for n in range(count):
            s = base + n * size
            if ram[s] and _w(ram, s + 0xC) == w['entry']:
                self.seen = (ram[s + 0xA], ram[s + 0xB])
                return True
        return False

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if w['remove']:
            ok = self.seen == 'gone'
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the screen reached that spot and no {w["name"]} appeared there.' if ok
                    else f'Played from the start, a {w["name"]} still appears there.'}
        ok = self.seen == (w['id'], w['sub'])
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now puts {w["name"]} there.' if ok
                else f'Played from the start, the game put object {self.seen[0]:#04x} (setting {self.seen[1]:#04x}) there, not the one chosen.'}


class MegaManXProfile(MegaManX, Profile):
    """Parts are {'level': number}; x and y are the level's pixels (the camera is $1E4D / $1E50)."""
    sha256s = (MegaManX.sha256,)
    system = 'snes'

    def __init__(self, rom: bytes):
        MegaManX.__init__(self, rom)

    def where(self, ram):
        if ram[0xD1] != 2 or ram[0xD2] != 4 or ram[0x1F7A] >= self.LEVELS:
            return None
        return {'part': {'level': ram[0x1F7A]}, 'x': _w(ram, 0x1E4D), 'y': _w(ram, 0x1E50)}

    def part_name(self, part):
        return self.LEVEL_NAMES[int(part['level'])]

    def choices(self):
        return {'items': [{'value': i << 8 | s, 'name': self.ITEMS[(i, s)]} for i, s in self.COMMON_ITEMS]}

    def objects(self, part):
        level = int(part['level'])
        out = []
        for e in self.entries(level):
            if e['type'] == 3:
                row = {'id': f'obj:{e["index"]}', 'style': 'enemy', 'type': e['id'], 'x': e['x'], 'y': e['y'],
                       'name': self.enemy_name(e['id']), 'remove': None, 'fields': []}
                if e['sub']:
                    row['detail'] = f'setting {e["sub"]:#04x}'
                if self.editable_enemy(e):
                    row['remove'] = 'Remove this enemy'
                    choices = self.enemy_choices(level, e)
                    if len(choices) > 1:
                        row['fields'] = [{'key': 'enemy', 'label': 'Swap for', 'value': e['id'] << 8 | e['sub'],
                                          'choices': [{'value': i << 8 | s, 'name': self.enemy_name(i, s)} for i, s in choices]}]
                    row['note'] = 'Swaps are the enemies the game places under the same graphics load, so they draw right.'
                else:
                    row['note'] = 'The game places this one only once (a boss, a helper or a scripted part), so ROMancer leaves it alone.'
                out.append(row)
            elif self.is_item(e):
                name = self.item_name(e['id'], e['sub'])
                special = (e['id'], e['sub']) not in self.COMMON_ITEMS
                fields = self.choices()['items']
                if special:
                    fields = [{'value': e['id'] << 8 | e['sub'], 'name': name}] + fields
                row = {'id': f'obj:{e["index"]}', 'style': 'secret' if special else 'item', 'type': e['id'], 'x': e['x'],
                       'y': e['y'], 'name': name, 'remove': 'Remove this item',
                       'fields': [{'key': 'item', 'label': 'Item', 'value': e['id'] << 8 | e['sub'], 'choices': fields}]}
                if special:
                    row['note'] = 'Changing it to another item gives up this one for good: the game counts each of these once.'
                out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        level = int(part['level'])
        kind, _, number = object_id.partition(':')
        entries = self.entries(level)
        if kind != 'obj' or not number.isdigit() or not 0 <= int(number) < len(entries):
            raise ValueError('That is not part of this level any more. Reopen the map.')
        e = entries[int(number)]
        enemy = self.editable_enemy(e)
        if not enemy and not self.is_item(e):
            raise ValueError('ROMancer cannot change that yet.')
        name = self.enemy_name(e['id']) if enemy else self.item_name(e['id'], e['sub'])
        watch = {'level': level, 'type': e['type'], 'entry': self.ENTRY_RAM + 5 * e['index'], 'x': e['x'], 'y': e['y']}
        if remove:
            return {'writes': self.remove_writes(level, e['index']), 'title': f'Remove the {name}',
                    'watch': {**watch, 'remove': True, 'id': e['id'], 'sub': e['sub'], 'name': name}}
        if enemy:
            value = int(values.get('enemy', e['id'] << 8 | e['sub']))
            if (value >> 8, value & 0xFF) not in self.enemy_choices(level, e):
                raise ValueError('That choice is not one of the game’s own.')
            new_name = self.enemy_name(value >> 8, value & 0xFF)
        else:
            value = int(values.get('item', e['id'] << 8 | e['sub']))
            if (value >> 8, value & 0xFF) not in self.COMMON_ITEMS + [(e['id'], e['sub'])]:
                raise ValueError('That choice is not one of the game’s own.')
            new_name = self.item_name(value >> 8, value & 0xFF)
        writes = [(e['offset'] + 3 + i, self.rom[e['offset'] + 3 + i], v) for i, v in enumerate((value >> 8, value & 0xFF))
                  if self.rom[e['offset'] + 3 + i] != v]
        return {'writes': writes, 'title': f'{"Enemy" if enemy else "Item"} here: {new_name}',
                'watch': {**watch, 'remove': False, 'id': value >> 8, 'sub': value & 0xFF, 'name': new_name}}

    def watcher(self, watch):
        return _MmxWatcher(watch)


# --------------------------------------------------------------------------------------------- Super Castlevania IV

class SuperCastlevania4:
    """Super Castlevania IV (USA). Room number $86 (68 rooms); camera $1280 (x) / $1298 (y); playing when $70 = 5.

    Object list per room ($00D3EC): $00:D81B + room * 2 points (bank $05) at a zero entry, then 6-byte entries, $FFFF
    ends it. Entry: word x (low 2 bits = kind, $0FFC = x, top bits flags), word y ($0FFC = y), byte type, byte value.
    The spawner ($00D682) picks the handler by kind ($00D695): 0 an enemy or level part ($00D6EC; bit 14 of x = only
    on the harder setting $88, bit 15 = facing), 1 a candle ($00D771: object $0E, the type byte is its once-only flag
    in $1500, the value is the item it drops), 2 an object that comes once ($00D69B, flag from the top bits of x and y).
    Slots $0580 + n * $40 (to $0EC0): +$10 type, +$0A x, +$0E y, +$14 value. Rooms with $00:D8A3 = 1 or 3 read their
    list from the end, 2 by y.
    """
    name = 'Super Castlevania IV'
    sha256 = '0ef6f4cce5a2273fa49fe1ce724e0048a8e39c91da6b00dbb693fe1ba909177d'
    LISTS = 0x00D81B
    ROOMS = 68
    # What a candle gives: each value was put in the first candle of room 0, whipped and picked up (sc4item.py); the
    # pictures are in items/sc4_*.png and the RAM it changed ($13F2 hearts, $008E sub-weapon) in the notes
    ITEMS = {0x18: 'Small heart', 0x19: 'Large heart', 0x1A: 'Dagger', 0x1B: 'Axe', 0x1C: 'Holy water', 0x1D: 'Cross',
             0x1E: 'Stopwatch', 0x1F: 'Rosary', 0x20: 'Potion', 0x22: 'Money bag', 0x62: 'Money bag (second kind)',
             0xA2: 'Money bag (third kind)', 0xE2: 'Money bag (fourth kind)', 0x25: 'Small meat', 0x26: 'Pot roast',
             0x28: '1-Up'}
    # Objects named from what the game drew (survey_sc4, sheet_sc4survey.png)
    NAMES = {0x11: 'Skeleton', 0x10: 'Bird', 0x0C: 'Bat (likely)'}
    SLOTS = (0x0580, 0x40, 0x26)

    def __init__(self, rom: bytes):
        self.rom = rom
        self._cache = {}

    def w(self, address: int) -> int:
        return _w(self.rom, lorom(address))

    def list_start(self, room: int) -> int:
        return lorom(0x050000 | self.w(self.LISTS + room * 2))

    def entries(self, room: int) -> list:
        if ('list', room) in self._cache:
            return self._cache[('list', room)]
        p = self.list_start(room)
        if _w(self.rom, p) == 0 and _w(self.rom, p + 2) == 0:
            p += 6
        out = []
        while _w(self.rom, p) != 0xFFFF and len(out) < 300:
            x, y = _w(self.rom, p), _w(self.rom, p + 2)
            out.append({'index': len(out), 'offset': p, 'x': x & 0xFFC, 'y': y & 0xFFC, 'kind': x & 3,
                        'type': self.rom[p + 4], 'value': self.rom[p + 5]})
            p += 6
        self._cache[('end', room)] = p
        self._cache[('list', room)] = out
        return out

    def count(self) -> dict:
        if 'count' not in self._cache:
            c = {}
            for room in range(self.ROOMS):
                for e in self.entries(room):
                    if e['kind'] != 1:
                        c[e['type']] = c.get(e['type'], 0) + 1
            self._cache['count'] = c
        return self._cache['count']

    def editable_enemy(self, e: dict) -> bool:
        return e['kind'] in (0, 2) and self.count().get(e['type'], 0) > 1

    def enemy_choices(self, room: int, e: dict) -> list:
        seen = []
        for other in self.entries(room):
            if other['kind'] == e['kind'] and self.editable_enemy(other) and (other['type'], other['value']) not in seen:
                seen.append((other['type'], other['value']))
        return sorted(seen)

    def object_name(self, number: int, value: int | None = None) -> str:
        name = self.NAMES.get(number, f'Object {number:#04x}')
        return name if not value else f'{name} (setting {value:#04x})'

    def remove_writes(self, room: int, index: int) -> list:
        entries = self.entries(room)
        start = entries[index]['offset']
        end = self._cache[('end', room)]          # the $FFFF
        old = self.rom[start:end + 2]
        new = self.rom[start + 6:end + 2]
        return [(start + i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]


class _Sc4Watcher(Watcher):
    """A Super Castlevania IV edit. Each slot is looked at when it first holds something: a swap (or a candle's item) is
    seen when a slot of the entry's kind first shows at the entry's place (within 8 px) and holds the chosen type
    (+$10, and for a candle the item +$14). A removal is seen when the screen has been over the spot for 30 looks with
    no slot of the old type first showing there."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.reached = 0
        self.slots = {}

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x70] != 5 or _w(ram, 0x86) != w['room']:
            return False
        base, size, count = SuperCastlevania4.SLOTS
        for n in range(count):
            s = base + n * size
            t = _w(ram, s + 0x10)
            if not t:
                self.slots.pop(s, None)
                continue
            key = (t, ram[s + 0x14])
            if self.slots.get(s) == key:
                continue
            self.slots[s] = key
            if abs(_w(ram, s + 0x0A) - w['x']) > 8 or abs(_w(ram, s + 0x0E) - w['y']) > 8:
                continue
            if w['remove']:
                if t == w['old']:
                    self.seen = 'there'
                    return True
            elif w['candle']:
                if t == 0x0E:
                    self.seen = key[1]
                    return True
            elif t in w['types']:
                self.seen = t
                return True
        if w['remove']:
            cx, cy = _w(ram, 0x1280), _w(ram, 0x1298)
            if cx <= w['x'] <= cx + 256 and cy <= w['y'] <= cy + 224:
                self.reached += 1
                if self.reached > 30:
                    self.seen = 'gone'
                    return True
        return False

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if w['remove']:
            ok = self.seen == 'gone'
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the screen reached that spot and no {w["name"]} appeared there.' if ok
                    else f'Played from the start, a {w["name"]} still appears there.'}
        ok = self.seen == w['want']
        if w['candle']:
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, this candle now holds {w["name"]}.' if ok
                    else f'Played from the start, this candle holds item {self.seen:#04x}, not the one chosen.'}
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now puts {w["name"]} there.' if ok
                else f'Played from the start, the game put object {self.seen:#04x} there, not the one chosen.'}


class SuperCastlevania4Profile(SuperCastlevania4, Profile):
    """Parts are {'room': number}; x and y are the room's pixels (the camera is $1280 / $1298)."""
    sha256s = (SuperCastlevania4.sha256,)
    system = 'snes'

    def __init__(self, rom: bytes):
        SuperCastlevania4.__init__(self, rom)

    def where(self, ram):
        if ram[0x70] != 5 or _w(ram, 0x86) >= self.ROOMS:
            return None
        return {'part': {'room': _w(ram, 0x86)}, 'x': _w(ram, 0x1280), 'y': _w(ram, 0x1298)}

    def part_name(self, part):
        return f'Room {int(part["room"])}'

    def choices(self):
        return {'items': [{'value': v, 'name': n} for v, n in sorted(self.ITEMS.items())]}

    def objects(self, part):
        room = int(part['room'])
        out = []
        for e in self.entries(room):
            if e['kind'] == 1:
                item = self.ITEMS.get(e['value'], f'item {e["value"]:#04x}')
                row = {'id': f'obj:{e["index"]}', 'style': 'item', 'type': 0x0E, 'x': e['x'], 'y': e['y'],
                       'name': 'Candle', 'detail': f'holds {item[0].lower() + item[1:]}', 'remove': 'Remove this candle',
                       'fields': []}
                if e['value'] in self.ITEMS:
                    row['fields'] = [{'key': 'item', 'label': 'Holds', 'value': e['value'], 'choices': 'items'}]
                out.append(row)
            elif e['kind'] in (0, 2):
                row = {'id': f'obj:{e["index"]}', 'style': 'enemy', 'type': e['type'], 'x': e['x'], 'y': e['y'],
                       'name': self.object_name(e['type']), 'remove': None, 'fields': []}
                if e['value']:
                    row['detail'] = f'setting {e["value"]:#04x}'
                if self.editable_enemy(e):
                    row['remove'] = 'Remove this'
                    choices = self.enemy_choices(room, e)
                    if len(choices) > 1:
                        row['fields'] = [{'key': 'object', 'label': 'Swap for', 'value': e['type'] << 8 | e['value'],
                                          'choices': [{'value': t << 8 | v, 'name': self.object_name(t, v)} for t, v in choices]}]
                    row['note'] = 'Swaps are the things the game places in this same room.'
                else:
                    row['note'] = 'The game places this one only once (a boss or a scripted part), so ROMancer leaves it alone.'
                out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        room = int(part['room'])
        kind, _, number = object_id.partition(':')
        entries = self.entries(room)
        if kind != 'obj' or not number.isdigit() or not 0 <= int(number) < len(entries):
            raise ValueError('That is not part of this room any more. Reopen the map.')
        e = entries[int(number)]
        candle = e['kind'] == 1
        if not candle and not self.editable_enemy(e):
            raise ValueError('ROMancer cannot change that yet.')
        name = 'candle' if candle else self.object_name(e['type'])
        watch = {'room': room, 'x': e['x'], 'y': e['y'], 'candle': candle}
        if remove:
            return {'writes': self.remove_writes(room, e['index']), 'title': f'Remove the {name}',
                    'watch': {**watch, 'remove': True, 'old': 0x0E if candle else e['type'], 'name': name}}
        if candle:
            value = int(values.get('item', e['value']))
            if value not in self.ITEMS:
                raise ValueError('That choice is not one of the game’s own.')
            at = e['offset'] + 5
            writes = [(at, self.rom[at], value)] if self.rom[at] != value else []
            item = self.ITEMS[value]
            return {'writes': writes, 'title': f'Candle holds: {item}',
                    'watch': {**watch, 'remove': False, 'want': value, 'name': item[0].lower() + item[1:]}}
        value = int(values.get('object', e['type'] << 8 | e['value']))
        if (value >> 8, value & 0xFF) not in self.enemy_choices(room, e):
            raise ValueError('That choice is not one of the game’s own.')
        writes = [(e['offset'] + 4 + i, self.rom[e['offset'] + 4 + i], v) for i, v in enumerate((value >> 8, value & 0xFF))
                  if self.rom[e['offset'] + 4 + i] != v]
        new_name = self.object_name(value >> 8, value & 0xFF)
        return {'writes': writes, 'title': f'Here: {new_name}',
                'watch': {**watch, 'remove': False, 'want': value >> 8, 'types': [e['type'], value >> 8], 'name': new_name}}

    def watcher(self, watch):
        return _Sc4Watcher(watch)


PROFILES = [MegaManXProfile, SuperCastlevania4Profile]
