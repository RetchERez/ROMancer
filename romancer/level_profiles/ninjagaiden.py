"""Ninja Gaiden (USA) level profile: enemies and item lanterns, decoded from the game's own code.

Each game of the series is decoded and proven on its own (research/ninjagaiden-level-profile.md). Ninja Gaiden II and III
share far less with the first game than their look suggests (a byte comparison of the fixed code banks finds almost no
common code), so every class here reads its own tables.
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER_NES = 16


def _bit(index: int):
    """(byte, mask) of a list entry's one-bit flag in an 8-entries-per-byte flag array."""
    return index >> 3, 1 << (index & 7)


class NinjaGaiden1:
    """Ninja Gaiden (USA), MMC1, 16 KiB banks, fixed bank 7 at $C000.

    Stage index $6D (0-21) picks the first area from $AF2C (bank 0); doors move the area $6E on. Per area (bank 2,
    switched in by the spawn code at $E560):
      * enemy list: column ($87C0 + area*2 -> list), place ($8820), type ($8880); count at $AE40 + area (bank 0).
        An enemy spawns when the camera column ($4E, camera / 16) equals its column; it appears at screen x
        (place & $0F) * 16 and y place & $F0 (code $E5B3). A column of $FF never comes up: the game uses it for lists
        with nothing in them, so ROMancer removes an enemy by giving it that column.
      * lanterns (item holders): column ($8700), item and height ($8760: high nibble y, low nibble item); count at
        $AE10 + area. A lantern appears when the camera's right edge column ($4F) reaches its column (code $D8E8).
    What a lantern holds is the pickup jump table at $DBC9 (12 entries).
    """
    name = 'Ninja Gaiden'
    sha256 = 'ce3245591dd63e535287851e5e7a6881d81f7f74c7e22152903fbd6e9a2585cd'
    STAGES = 22
    AREAS = 48
    BOSS_TYPES = range(0x11, 0x30)
    # enemy types named by spawning each one in a stage that has it and looking at what the game drew
    # (trace/v15_profiles/ninjagaiden/crops3); a type can look different in another stage, so swaps stay within a stage
    ENEMIES = {0x00: 'Thug in a brown vest', 0x01: 'Soldier', 0x02: 'Hooded swordsman', 0x03: 'Club thug', 0x04: 'Boxer',
               0x05: 'Bazooka soldier', 0x06: 'Grey swordsman', 0x07: 'Leaping soldier', 0x08: 'Small crawler',
               0x09: 'Dog', 0x0A: 'Dog (second kind)', 0x0B: 'Hawk', 0x0C: 'Leaping beast', 0x0D: 'Green climber',
               0x0E: 'White crouching figure', 0x10: 'Green crouching creature'}
    # pickup code $DBC9: what each item number does (measured by collecting each one in stage 1-1)
    ITEMS = {0x0: 'Spirit points (5)', 0x1: 'Spirit points (10)', 0x2: 'Extra life', 0x3: 'Health (restores 6)',
             0x4: 'Time freeze', 0x5: 'Bonus points (500)', 0x6: 'Bonus points (1000)', 0x7: 'Invincible fire wheel',
             0x8: 'Throwing star', 0x9: 'Windmill star', 0xA: 'Art of the fire wheel', 0xB: 'Jump and slash'}
    NEVER = 0xFF                # the column the game itself gives entries that must not appear

    def __init__(self, rom: bytes):
        self.rom = rom

    # ---- reading
    def offset(self, bank: int, address: int) -> int:
        return HEADER_NES + bank * 0x4000 + (address - (0xC000 if bank == 7 else 0x8000))

    def _b(self, bank: int, address: int) -> int:
        return self.rom[self.offset(bank, address)]

    def _w(self, bank: int, address: int) -> int:
        return self._b(bank, address) | self._b(bank, address + 1) << 8

    def stage_area(self, stage: int) -> int:
        return self._b(0, 0xAF2C + stage)

    def stage_label(self, stage: int) -> str:
        """The game's own stage number ($AF6E, shown on the status bar as STAGE-x-y)."""
        value = self._b(0, 0xAF6E + stage)
        return f'{value >> 4}-{value & 15}'

    def stage_of(self, area: int) -> int:
        starts = [self.stage_area(s) for s in range(self.STAGES)]
        return max(s for s in range(self.STAGES) if starts[s] <= area)

    def lists(self, area: int) -> dict:
        p = [self._w(2, 0x8700 + area * 2 + k * 0x60) for k in range(5)]
        return {'lantern_col': p[0], 'lantern_item': p[1], 'col': p[2], 'place': p[3], 'type': p[4],
                'enemies': self._b(0, 0xAE40 + area), 'lanterns': self._b(0, 0xAE10 + area)}

    def enemies(self, area: int) -> list:
        L = self.lists(area)
        out = []
        for i in range(L['enemies']):
            col, place, kind = self._b(2, L['col'] + i), self._b(2, L['place'] + i), self._b(2, L['type'] + i)
            out.append({'index': i, 'col': col, 'place': place, 'type': kind, 'x': (col + (place & 15)) * 16, 'y': place & 0xF0,
                        'col_byte': self.offset(2, L['col'] + i), 'type_byte': self.offset(2, L['type'] + i)})
        return out

    def lanterns(self, area: int) -> list:
        L = self.lists(area)
        if L['lanterns'] >= 0x80:
            return []
        out = []
        for i in range(L['lanterns']):
            col, held = self._b(2, L['lantern_col'] + i), self._b(2, L['lantern_item'] + i)
            out.append({'index': i, 'col': col, 'item': held & 15, 'x': col * 16 + 4, 'y': (held & 0xF0) - 8,
                        'col_byte': self.offset(2, L['lantern_col'] + i), 'item_byte': self.offset(2, L['lantern_item'] + i)})
        return out

    def owners(self) -> dict:
        """{ROM offset: number of list entries that read it} over every area (two lists may share a byte)."""
        count = {}
        for area in range(self.AREAS):
            L = self.lists(area)
            spans = [(L['col'], L['enemies']), (L['place'], L['enemies']), (L['type'], L['enemies'])]
            if L['lanterns'] < 0x80:
                spans += [(L['lantern_col'], L['lanterns']), (L['lantern_item'], L['lanterns'])]
            for start, n in spans:
                for i in range(n):
                    o = self.offset(2, start + i)
                    count[o] = count.get(o, 0) + 1
        return count

    def enemy_name(self, kind: int) -> str:
        if kind in self.BOSS_TYPES:
            return f'Boss (type {kind:#04x})'
        return self.ENEMIES.get(kind, f'Enemy {kind:#04x}')

    def item_name(self, item: int) -> str:
        return self.ITEMS.get(item, f'Item {item:#04x}')

    def lantern_delete_writes(self, area: int, index: int) -> list:
        """Take a lantern out of its area's list: the later lanterns move up one place and the count ($AE10) drops by
        one. The game walks the lantern list in order with a cursor that only moves on when the next lantern's column
        comes up (code $D8E8), so a lantern given a column that never comes up would stop every lantern after it."""
        L = self.lists(area)
        count = L['lanterns']
        if count >= 0x80 or not 0 <= index < count:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        shared = self.owners()
        writes = []
        for start in (L['lantern_col'], L['lantern_item']):
            values = [self._b(2, start + i) for i in range(count)]
            new = values[:index] + values[index + 1:]
            for i, value in enumerate(new):
                if value != values[i]:
                    offset = self.offset(2, start + i)
                    if shared.get(offset, 1) > 1:
                        raise ValueError('The game reads this lantern list for another list too, so ROMancer leaves it alone.')
                    writes.append((offset, values[i], value))
        writes.append((self.offset(0, 0xAE10 + area), count, count - 1))
        return writes

    # ---- length (code $E902: layout pointer $AC30 + area * 2, last screen $AD20 + area; scrolling stops at $53, $F1EE)
    LAYOUT = 0xAC30             # bank 0: word per area, the area's columns (6 block numbers of 32 px each), 8 a screen
    LAST = 0xAD20               # bank 0: low 7 bits last screen ($53), bit 7 the area starts at its end and scrolls left
    FREE = (0xB58C, 0xBFDA)     # bank 0: unused ($FF) space that a longer layout is moved to
    MOST = 15                   # camera columns ($4E, $4E + 16 for lanterns) stay below 256 up to 15 screens
    MOST_REVERSED = 12          # the start table at $E95F is right for last screens 0-11 only
    SCREEN = 48                 # layout bytes a screen

    def area_last(self, area: int) -> int:
        return self._b(0, self.LAST + area) & 0x7F

    def area_reversed(self, area: int) -> bool:
        return bool(self._b(0, self.LAST + area) & 0x80)

    def layout(self, area: int) -> int:
        return self._w(0, self.LAYOUT + area * 2)

    def resizable(self, area: int) -> str:
        """'' when the area's length can be changed, otherwise the reason it cannot."""
        if self.area_last(area) == 0:
            return 'This part is a single screen (a boss room or a room behind a door), so its length stays as it is.'
        if any(e['type'] in self.BOSS_TYPES and e['col'] != self.NEVER for e in self.enemies(area)):
            return 'This part holds a boss, so its length stays as it is.'
        return ''

    def most_screens(self, area: int) -> int:
        return self.MOST_REVERSED if self.area_reversed(area) else self.MOST

    def column_buffer(self, stage: int, area: int, column: int) -> bytes:
        """The 12 bytes the game copies into its column buffer ($0300 + slot * 12, code $F5EA) for a layout column: for
        each of its 6 blocks the two bytes of the block's entry in the stage's block table ($A430 + ($AF00 & 3) * $200,
        code $EAE1)."""
        table = 0xA430 + (self._b(0, 0xAF00 + stage) & 3) * 0x200
        out = bytearray(12)
        for row in range(6):
            block = self._b(0, self.layout(area) + column * 6 + row)
            out[row] = self._b(0, table + block * 2)
            out[row + 6] = self._b(0, table + block * 2 + 1)
        return bytes(out)

    def _free0(self, size: int) -> int:
        """Where in bank 0's unused space `size` bytes fit, after anything already moved there."""
        start, end = self.FREE
        used = max((a for a in range(start, end) if self._b(0, a) != 0xFF), default=None)
        if used is not None:
            start = used + 1
        if start + size > end:
            raise ValueError('There is no room left in the game for a longer layout.')
        return start

    def resize_writes(self, area: int, at: int, delta: int) -> dict:
        """Writes that remove `-delta` screens starting at screen `at`, or repeat screen `at` `delta` more times right
        after it; the enemies and lanterns of later screens move along. {'writes', 'screens', 'notes'}."""
        area, at, delta = int(area), int(at), int(delta)
        why = self.resizable(area)
        if why:
            raise ValueError(why)
        last = self.area_last(area)
        count = last + 1
        if not 0 <= at < count:
            raise ValueError('That screen is not part of this stage.')
        if delta == 0:
            raise ValueError('Choose how many screens to add or remove.')
        if delta < 0 and (at == 0 or at - delta > last):
            raise ValueError('The first and the last screen hold the way in and the way out, so they stay. Choose a screen in between.')
        most = self.most_screens(area)
        if not 2 <= count + delta <= most:
            raise ValueError(f'This part can be 2 to {most} screens long.')
        writes, notes = {}, []
        shared = self.owners()

        def put(offset, value):
            writes[offset] = value & 0xFF

        boundary = (at - delta if delta < 0 else at + 1) * 16          # first column that moves
        removed = range(at * 16, (at - delta) * 16) if delta < 0 else range(0)
        for e in self.enemies(area):
            col = e['col']
            if col == self.NEVER:
                continue
            if col in removed:
                new = self.NEVER
                notes.append('The enemies of the removed screens are taken out.')
            elif col >= boundary:
                new = col + delta * 16
            else:
                continue
            if shared.get(e['col_byte'], 1) > 1:
                raise ValueError('An enemy that would move shares its bytes with another list, so ROMancer cannot change this part’s length.')
            put(e['col_byte'], new)
        gone = [l for l in self.lanterns(area) if l['col'] in removed]
        for lantern in self.lanterns(area):
            if lantern['col'] >= boundary and lantern['col'] != self.NEVER:
                if shared.get(lantern['col_byte'], 1) > 1:
                    raise ValueError('A lantern that would move shares its bytes with another list, so ROMancer cannot change this part’s length.')
                put(lantern['col_byte'], lantern['col'] + delta * 16)
        if gone:                         # take them out of the list, last first, from the already moved columns
            rom = bytearray(self.rom)
            for offset, value in writes.items():
                rom[offset] = value
            for lantern in sorted(gone, key=lambda l: -l['index']):
                for offset, old, value in type(self)(bytes(rom)).lantern_delete_writes(area, lantern['index']):
                    rom[offset] = value
                    put(offset, value)
            notes.append('The lanterns of the removed screens are taken out.')

        put(self.offset(0, self.LAST + area), (self._b(0, self.LAST + area) & 0x80) | (count + delta - 1))
        base = self.layout(area)
        size = count * self.SCREEN
        screens = [bytes(self._b(0, base + i * self.SCREEN + k) for k in range(self.SCREEN)) for i in range(count)]
        if delta < 0:
            new = screens[:at] + screens[at - delta:]
            new += new[-1:] * (-delta)          # what the game draws past the end (off screen) stays a copy of the last screen
            for i, byte in enumerate(b''.join(new)):
                put(self.offset(0, base) + i, byte)
        else:
            new = screens[:at + 1] + screens[at:at + 1] * delta + screens[at + 1:]
            pad = 3 * self.SCREEN               # the game draws up to three screens beyond either end, off screen
            before = bytes(self._b(0, a) if a >= 0x8000 else self._b(0, base + (a - base) % self.SCREEN) for a in range(base - pad, base))
            after = bytes(self._b(0, base + size + i) if base + size + i < 0xC000 else 0 for i in range(pad))
            block = before + b''.join(new) + after
            start = self._free0(len(block))
            for i, byte in enumerate(block):
                put(self.offset(0, start) + i, byte)
            put(self.offset(0, self.LAYOUT + area * 2), (start + pad) & 0xFF)
            put(self.offset(0, self.LAYOUT + area * 2 + 1), (start + pad) >> 8)
        out = [(offset, self.rom[offset], value) for offset, value in sorted(writes.items()) if self.rom[offset] != value]
        return {'writes': out, 'screens': count + delta, 'notes': sorted(set(notes))}

    def stage_types(self, stage: int) -> list:
        """Regular enemy types used anywhere in a stage (its sprites are loaded per stage, so these all draw right)."""
        first = self.stage_area(stage)
        last = self.stage_area(stage + 1) if stage + 1 < self.STAGES else self.AREAS
        kinds = set()
        for area in range(first, last):
            kinds.update(e['type'] for e in self.enemies(area) if e['col'] != self.NEVER and e['type'] not in self.BOSS_TYPES)
        return sorted(kinds)


class _NG1Watcher(Watcher):
    """An enemy or lantern edit in Ninja Gaiden: watch the entry's spawned flag ($B7 bits for enemies, the lantern
    slots' list number $04F1 for lanterns) and what the game put in the slot when it appeared."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.flag_was = False
        self.seen = None            # what appeared (enemy type or lantern item), or 'nothing'
        self.lo = self.hi = None    # camera columns seen in the part
        self.slots, self.appeared = {}, {}

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x6D] != w['stage'] or ram[0x6E] != w['area']:
            return False
        column = ram[0x4E] + (16 if w['kind'] == 'lantern' else 0)
        self.lo = column if self.lo is None else min(self.lo, column)
        self.hi = column if self.hi is None else max(self.hi, column)
        if w['kind'] == 'enemy':
            byte, mask = _bit(w['index'])
            flag = bool(ram[0xB7 + byte] & mask)
            if flag and not self.flag_was and self.seen is None:
                slots = [s for s in range(8) if ram[0x73] >> s & 1 and ram[0x4B0 + s] == w['index']]
                self.seen = ram[0x400 + slots[0]] if slots else -1
            self.flag_was = flag
            return self.seen is not None and (w['remove'] or self.seen == w.get('type'))
        elif w['remove']:
            # after a removal the later lanterns move up a place in the list, so list numbers change: count what
            # appears at the removed column ($4F, the game's own test) and check the next lantern still appears
            slots = {s: ram[0x4F1 + s] for s in range(4) if ram[0xC0] >> s & 1}
            for s, number in slots.items():
                if self.slots.get(s) != number:
                    self.appeared[column] = self.appeared.get(column, 0) + 1
            self.slots = slots
            return False
        else:
            for s in range(4):
                if ram[0xC0] >> s & 1 and ram[0x4F1 + s] == w['index'] and self.seen is None:
                    self.seen = ram[0x4C9 + s]
            return self.seen is not None
        return False

    def result(self):
        w = self.w
        reached = self.lo is not None and self.lo <= w['col'] <= self.hi
        what = 'enemy' if w['kind'] == 'enemy' else 'lantern'
        if w['remove'] and w['kind'] == 'lantern' and 'same' in w:
            if not reached:
                return super().result()
            if self.appeared.get(w['col'], 0) > w['same']:
                return {'state': 'bad', 'text': 'Played from the start, the lantern still appears there.'}
            text = 'Played from the start, the walk passes that spot and no lantern appears there any more.'
            if w['next'] is not None and self.hi >= w['next']:
                if not self.appeared.get(w['next']):
                    return {'state': 'bad', 'text': 'Played from the start, the lantern is gone but the next lantern does not appear either.'}
                text += ' The next lantern still appears.'
            return {'state': 'good', 'text': text}
        if w['remove']:
            if self.seen is not None:
                return {'state': 'bad', 'text': f'Played from the start, the {what} still appears there.'}
            if not reached:
                return super().result()
            return {'state': 'good', 'text': f'Played from the start, the walk passes that spot and no {what} appears there any more.'}
        if self.seen is None:
            return super().result()
        if w['kind'] == 'enemy':
            ok = self.seen == w['type']
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the game now spawns {w["name"]} there.' if ok
                    else f'Played from the start, the game spawned type {self.seen & 0xFF:#04x} there, not what was chosen.'}
        ok = self.seen == w['item']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the lantern there now holds {w["name"]}.' if ok
                else f'Played from the start, the lantern there holds item {self.seen:#04x}, not the one chosen.'}


class _NG1LengthWatcher(Watcher):
    """A length change in Ninja Gaiden, judged from the game's own memory on the original and the changed game: the
    scroll limit $53 the area set-up loads, the layout columns the game copies into its column buffer ($0300, 12 bytes
    a column, slot = column mod 16 in areas that scroll right) as the camera passes, and the camera column ($4E) at
    which each enemy spawns."""
    compare = True
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.visits = {}


    def see(self, ram, frame, run):
        w = self.w
        visits = self.visits.setdefault(run, [])
        inside = ram[0x6D] == w['stage'] and ram[0x6E] == w['area'] and ram[0x53] < 0x10
        visit = visits[-1] if visits and visits[-1]['open'] else None
        if not inside:
            if visit is not None:
                visit['open'] = False
                visit['left'] = frame
            return False
        if visit is None:
            visit = {'open': True, 'start': frame, 'limit': None, 'far': 0, 'cols': {}, 'spawn': {}, 'flags': bytes(ram[0xB7:0xBB]), 'left': None}
            visits.append(visit)
        visit['limit'] = ram[0x53]
        camera = ram[0x51] | ram[0x52] << 8
        visit['far'] = max(visit['far'], camera)
        first = camera // 32
        for k in range(first, first + 9):           # the columns on screen are always in the buffer
            slot = k % 16
            visit['cols'][k] = bytes(ram[0x300 + slot * 12:0x300 + slot * 12 + 12])     # the latest look: settled
        flags = bytes(ram[0xB7:0xBB])
        for i in range(32):
            byte, mask = _bit(i)
            if flags[byte] & mask and not visit['flags'][byte] & mask and i not in visit['spawn']:
                visit['spawn'][i] = ram[0x4E]
        visit['flags'] = flags
        return False

    @staticmethod
    def _best(visits):
        return max(visits, key=lambda v: (v['far'], v['start'])) if visits else None

    def result(self):
        w = self.w
        old, new = self._best(self.visits.get('original', [])), self._best(self.visits.get('changed', []))
        if old is None or new is None:
            return super().result()
        if new['limit'] != w['new'] - 1 or old['limit'] != w['old'] - 1:
            return {'state': 'bad', 'text': f'Played from the start, the game gives this part {(new["limit"] or 0) + 1} screens, not the {w["new"]} chosen.'}
        # the layout: each column the changed game showed must hold the blocks of the planned layout
        same = differ = 0
        for k, data in new['cols'].items():
            if k < len(w['expect']):
                if data.hex() == w['expect'][k]:
                    same += 1
                else:
                    differ += 1
        # the enemies: an enemy that moved spawns that much later (or earlier); a removed one never spawns
        moved = wrong = 0
        for i, (was, now) in enumerate(w['enemy_cols']):
            if was == now:
                continue
            if now == 0xFF:
                wrong += i in new['spawn']
            elif i in old['spawn'] and i in new['spawn']:
                if new['spawn'][i] - old['spawn'][i] == now - was:
                    moved += 1
                else:
                    wrong += 1
        if differ or wrong:
            return {'state': 'bad', 'text': f'Played from the start, the game gives this part {w["new"]} screens, but what it shows does not follow the plan '
                                            f'({differ} of {same + differ} columns and {wrong} enemies differ).'}
        text = f'Played from the start, the game now gives this part {w["new"]} screens (it had {w["old"]}).'
        if same:
            text += f' All {same} columns of blocks the walk passed hold the planned layout.'
        if moved:
            text += f' {moved} {"enemy appears" if moved == 1 else "enemies appear"} {abs(w["new"] - w["old"])} screen{"s" if abs(w["new"] - w["old"]) > 1 else ""} {"later" if w["new"] > w["old"] else "earlier"}, as planned.'
        if new['far'] >= (w['new'] - 1) * 256 and new['left'] and old['left']:
            seconds = round(abs(new['left'] - old['left']) / 60, 1)
            text += f' The walk reaches the new end, and the next part starts {seconds} seconds {"later" if new["left"] > old["left"] else "earlier"}.'
        else:
            got = new['far'] // 256 + 1
            text += f' The recorded walk gets {got} screen{"s" if got > 1 else ""} in.'
        if w['notes']:
            text += ' ' + ' '.join(w['notes'])
        return {'state': 'good', 'text': text}


class NinjaGaiden1Profile(NinjaGaiden1, Profile):
    """Ninja Gaiden on the common profile interface. Parts are {'stage': $6D, 'area': $6E}; x is the camera ($51/$52)."""
    sha256s = (NinjaGaiden1.sha256,)

    def where(self, ram):
        stage, area = ram[0x6D], ram[0x6E]
        if stage >= self.STAGES or area >= self.AREAS:
            return None
        return {'part': {'stage': stage, 'area': area}, 'x': ram[0x51] | ram[0x52] << 8, 'y': 0}

    def part_name(self, part):
        stage, area = int(part['stage']), int(part['area'])
        name = f'Stage {self.stage_label(stage)}'
        first = self.stage_area(stage)
        last = self.stage_area(stage + 1) if stage + 1 < self.STAGES else self.AREAS
        if last - first > 1:
            name += f', section {area - first + 1}'
        return name

    def choices(self):
        out = {'items': [{'value': k, 'name': v} for k, v in self.ITEMS.items()]}
        for stage in range(self.STAGES):
            out[f'enemies_{stage}'] = [{'value': t, 'name': self.enemy_name(t)} for t in self.stage_types(stage)]
        return out

    def objects(self, part):
        stage, area = int(part['stage']), int(part['area'])
        shared = self.owners()
        out = []
        for e in self.enemies(area):
            if e['col'] == self.NEVER:
                continue
            boss = e['type'] in self.BOSS_TYPES
            row = {'id': f'enemy:{e["index"]}', 'style': 'enemy', 'type': e['type'], 'x': e['x'], 'y': e['y'],
                   'name': self.enemy_name(e['type']), 'remove': None if boss else 'Remove this enemy',
                   'fields': [] if boss else [{'key': 'type', 'label': 'Swap for', 'value': e['type'], 'choices': f'enemies_{stage}'}]}
            if boss:
                row['note'] = 'The boss of this stage. ROMancer leaves bosses as they are.'
            elif shared.get(e['col_byte'], 1) > 1 or shared.get(e['type_byte'], 1) > 1:
                row.update(remove=None, fields=[], note='The game reads this entry’s bytes for another list too, so ROMancer leaves it alone.')
            out.append(row)
        for lantern in self.lanterns(area):
            if lantern['col'] == self.NEVER:
                continue
            row = {'id': f'lantern:{lantern["index"]}', 'style': 'item', 'type': 'lantern', 'x': lantern['x'], 'y': lantern['y'],
                   'name': 'Lantern', 'detail': f'holds {self.item_name(lantern["item"])}', 'remove': 'Remove this lantern',
                   'fields': [{'key': 'item', 'label': 'Holds', 'value': lantern['item'], 'choices': 'items'}]}
            if shared.get(lantern['col_byte'], 1) > 1 or shared.get(lantern['item_byte'], 1) > 1:
                row.update(remove=None, fields=[], note='The game reads this lantern’s bytes for another list too, so ROMancer leaves it alone.')
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        stage, area = int(part['stage']), int(part['area'])
        kind, _, number = object_id.partition(':')
        number = int(number)
        item = self.find(part, object_id)
        if not remove and not item.get('fields'):
            raise ValueError('ROMancer cannot change that yet.')
        if kind == 'enemy':
            e = self.enemies(area)[number]
            watch = {'kind': 'enemy', 'stage': stage, 'area': area, 'index': number, 'col': e['col'], 'remove': bool(remove)}
            if remove:
                writes = [(e['col_byte'], e['col'], self.NEVER)]
                title = f'Remove the {self.enemy_name(e["type"]).lower()}'
            else:
                new = int(values.get('type'))
                if new not in self.stage_types(stage):
                    raise ValueError('That choice is not one of the game’s own.')
                writes = [(e['type_byte'], e['type'], new)]
                watch.update(type=new, name=self.enemy_name(new))
                title = f'Enemy here: {self.enemy_name(new)}'
        elif kind == 'lantern':
            lantern = self.lanterns(area)[number]
            watch = {'kind': 'lantern', 'stage': stage, 'area': area, 'index': number, 'col': lantern['col'], 'remove': bool(remove)}
            if remove:
                writes = self.lantern_delete_writes(area, number)
                rest = self.lanterns(area)
                watch.update(same=sum(1 for l in rest if l['col'] == lantern['col']) - 1,
                             next=next((l['col'] for l in rest[number + 1:] if l['col'] != lantern['col']), None))
                title = 'Remove the lantern'
            else:
                new = int(values.get('item'))
                if new not in self.ITEMS:
                    raise ValueError('That choice is not one of the game’s own.')
                old = self.rom[lantern['item_byte']]
                writes = [(lantern['item_byte'], old, (old & 0xF0) | new)]
                watch.update(item=new, name=self.item_name(new))
                title = f'Lantern holds: {self.item_name(new)}'
        else:
            raise ValueError('ROMancer cannot change that yet.')
        return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'{title} ({self.part_name(part)})', 'watch': watch}

    def watcher(self, watch):
        if watch.get('kind') == 'length':
            return _NG1LengthWatcher(watch)
        return _NG1Watcher(watch)

    def screens(self, part):
        area = int(part['area'])
        if self.resizable(area):
            return None
        return {'count': self.area_last(area) + 1, 'most': self.most_screens(area)}

    def resize(self, part, at, delta):
        stage, area, at, delta = int(part['stage']), int(part['area']), int(at), int(delta)
        old = self.area_last(area) + 1
        result = self.resize_writes(area, at, delta)
        changed = bytearray(self.rom)
        for offset, _, value in result['writes']:
            changed[offset] = value
        after = type(self)(bytes(changed))
        new = result['screens']
        # what the game should copy into its column buffer for each column of the new layout (forward areas only)
        expect = [] if self.area_reversed(area) else [after.column_buffer(stage, area, k).hex() for k in range(new * 8)]
        enemy_cols = [(e['col'], f['col']) for e, f in zip(self.enemies(area), after.enemies(area))]
        watch = {'kind': 'length', 'stage': stage, 'area': area, 'old': old, 'new': new, 'expect': expect,
                 'enemy_cols': enemy_cols, 'notes': result['notes']}
        return {'writes': result['writes'], 'notes': result['notes'], 'watch': watch}


class _TecmoLength:
    """Level length for Ninja Gaiden II and III, whose area set-up and column code work the same way (each game at its
    own addresses): a word per area points at the area's layout in 8 KiB banks 0 and 1 (CPU $8000-$BFFF = ROM
    $0000-$3FFF while the column code reads it), columns of 6 block numbers (32 px each), 8 a screen; the low nibble of
    a per-area byte is the last screen, where the camera stops. Enemy and lantern lists are read in order by column,
    so entries of later screens get their columns moved and entries of removed screens are taken out of the lists."""
    LAYOUT_LO = LAYOUT_HI = LAST = 0        # ROM offsets of the pointer bytes; CPU address of the last-screen bytes
    FREE = None                             # CPU range of unused ($FF) space in banks 0-1 for a longer layout, if any
    MOST = 15                               # camera columns (and + 16 for lanterns) stay below 256 up to 15 screens
    SCREEN = 48

    def area_last(self, area: int) -> int:
        return self._b(self.LAST + area) & 0x0F

    def layout(self, area: int) -> int:
        return self.rom[HEADER_NES + self.LAYOUT_LO + area] | self.rom[HEADER_NES + self.LAYOUT_HI + area] << 8

    def layout_offset(self, address: int) -> int:
        return HEADER_NES + address - 0x8000

    def most_screens(self, area: int) -> int:
        return self.MOST if self.FREE else self.area_last(area) + 1          # no free space: shorter only

    def plain_section(self, area: int) -> bool:
        return True

    def resizable(self, area: int) -> str:
        if self.area_last(area) == 0:
            return 'This part is a single screen (a boss room or a room behind a door), so its length stays as it is.'
        if not self.plain_section(area):
            return 'This part scrolls up, down or to the left, and ROMancer only changes the length of parts that scroll to the right.'
        if self.FREE is None and self.area_last(area) < 2:
            return 'This part is two screens long and there is no room in the game for a longer layout, so its length stays as it is.'
        if any(e['type'] in getattr(self, 'BOSS_TYPES', ()) for e in self.enemies(area)):
            return 'This part holds a boss, so its length stays as it is.'
        return ''

    def resize_writes(self, area: int, at: int, delta: int) -> dict:
        """Writes that remove `-delta` screens starting at screen `at`, or repeat screen `at` `delta` more times right
        after it; enemies and lanterns of later screens move along, those of removed screens are taken out of their
        lists. {'writes', 'screens', 'notes', 'enemy_map'}."""
        area, at, delta = int(area), int(at), int(delta)
        why = self.resizable(area)
        if why:
            raise ValueError(why)
        last = self.area_last(area)
        count = last + 1
        if not 0 <= at < count:
            raise ValueError('That screen is not part of this stage.')
        if delta == 0:
            raise ValueError('Choose how many screens to add or remove.')
        if delta < 0 and (at == 0 or at - delta > last):
            raise ValueError('The first and the last screen hold the way in and the way out, so they stay. Choose a screen in between.')
        if not 2 <= count + delta <= self.most_screens(area):
            raise ValueError('There is no room left in the game for a longer layout.' if delta > 0 and self.FREE is None
                             else f'This part can be 2 to {self.most_screens(area)} screens long.')
        rom = bytearray(self.rom)
        notes = []
        boundary = (at - delta if delta < 0 else at + 1) * 16
        removed = range(at * 16, (at - delta) * 16) if delta < 0 else range(0)
        shared = self.owners()
        L = self.lists(area)
        for key, n in (('col', L['enemies']), ('lantern_col', L['lanterns'])):
            for i in range(n):
                o = self.offset(L[key] + i)
                col = rom[o]
                if col >= boundary and col not in removed:
                    if shared.get(o, 1) > 1:
                        raise ValueError('Something that would move shares its bytes with another list, so ROMancer cannot change this part’s length.')
                    rom[o] = col + delta * 16
        enemy_map = [[e['index'], e['index'], e['col'], None] for e in self.enemies(area)]
        for kind, items in (('enemy', self.enemies(area)), ('lantern', self.lanterns(area))):
            gone = [x['index'] for x in items if x['col'] in removed]
            for index in sorted(gone, reverse=True):
                for o, _, value in type(self)(bytes(rom)).delete_writes(area, kind, index):
                    rom[o] = value
                if kind == 'enemy':
                    for row in enemy_map:
                        if row[1] is not None and row[1] > index:
                            row[1] -= 1
                        elif row[1] == index:
                            row[1] = None
            if gone:
                notes.append(f'The {"enemies" if kind == "enemy" else "lanterns"} of the removed screens are taken out.')
        after = type(self)(bytes(rom))
        for row in enemy_map:
            if row[1] is not None:
                row[3] = after.enemies(area)[row[1]]['col']
        o = self.offset(self.LAST + area)
        rom[o] = (rom[o] & 0xF0) | (count + delta - 1)
        base = self.layout(area)
        screens = [bytes(self.rom[self.layout_offset(base) + i * self.SCREEN:self.layout_offset(base) + (i + 1) * self.SCREEN]) for i in range(count)]
        if delta < 0:
            new = screens[:at] + screens[at - delta:]
            new += new[-1:] * (-delta)          # what the game draws past the end (off screen) stays a copy of the last screen
            data = b''.join(new)
            rom[self.layout_offset(base):self.layout_offset(base) + len(data)] = data
        else:
            new = screens[:at + 1] + screens[at:at + 1] * delta + screens[at + 1:]
            pad = 3 * self.SCREEN               # the game draws up to three screens beyond either end, off screen
            lo = self.layout_offset(base)
            before = bytes(self.rom[lo - pad:lo]) if base - pad >= 0x8000 else screens[0] * 3
            after_bytes = bytes(self.rom[lo + count * self.SCREEN:lo + count * self.SCREEN + pad])
            block = before + b''.join(new) + after_bytes
            start, end = self.FREE
            used = max((a for a in range(start, end) if self.rom[self.layout_offset(a)] != 0xFF), default=None)
            start = start if used is None else used + 1
            if start + len(block) > end:
                raise ValueError('There is no room left in the game for a longer layout.')
            rom[self.layout_offset(start):self.layout_offset(start) + len(block)] = block
            rom[HEADER_NES + self.LAYOUT_LO + area] = (start + pad) & 0xFF
            rom[HEADER_NES + self.LAYOUT_HI + area] = (start + pad) >> 8
        writes = [(i, self.rom[i], rom[i]) for i in range(len(rom)) if rom[i] != self.rom[i]]
        return {'writes': writes, 'screens': count + delta, 'notes': notes, 'enemy_map': enemy_map}


class NinjaGaiden2(_TecmoLength):
    """Ninja Gaiden II - The Dark Sword of Chaos (USA), MMC3. Its own engine (not the first game's code).

    The area $7E (0-47) indexes tables in the bank at $8000 (ROM $8000-$9FFF, set up at $CEE3): enemy lists column
    ($87E0/$8810 low/high pointer), place ($8840/$8870) and type ($88A0/$88D0) with the count at $82D0; lanterns
    column ($8720/$8750) and item and height ($8780/$87B0) with the count at $82A0; bit 7 of $80F0 is set where the
    area is walked leftwards. Both lists are read in order with a cursor ($CA enemies, $B7/$B8 lanterns), so an
    entry is removed by moving the later entries up and lowering the count. Enemies spawn when the camera column $40
    equals their column ($C56F), at screen x (place & $0F) * 16 and y (place & $F0) | 8; the type goes through the
    object table at $E56D. Lanterns ($9F30) appear when the camera column is 16 less than theirs.
    """
    name = 'Ninja Gaiden II'
    sha256 = '9b7ebd1d6fd2a162a3f73eb2ddee5920e7eaa20343bcf9dd5cedee7687d935a0'
    AREAS = 48
    # the status bar's STAGE-x-y in each area (read from the screen after starting the game in every area)
    LABELS = (['1-1'] * 3 + ['1-2', '2-1'] + ['2-2'] * 3 + ['2-3', '3-1'] + ['3-2'] * 5 + ['3-3'] + ['4-1'] * 3
              + ['4-2'] * 3 + ['4-3'] + ['5-1'] * 3 + ['5-2'] * 3 + ['5-3'] + ['6-1'] * 3 + ['6-2', '6-3']
              + ['7-1'] * 5 + ['7-2'] * 5 + ['7-3', '7-4', '7-5'])
    BOSS_TYPES = {0x24}
    # what the game makes at the moment an enemy of each type spawns: (object $04D8, bit 0 of $04F0), measured by
    # spawning every type in stage 1-1 (trace/v15_profiles/ninjagaiden/ng2_sig_area0.json); every type differs
    SIGNATURES = {0x00: (21, 0), 0x01: (21, 1), 0x02: (23, 0), 0x03: (23, 1), 0x04: (17, 0), 0x05: (17, 1), 0x06: (19, 0),
                  0x07: (19, 1), 0x08: (26, 0), 0x09: (26, 1), 0x0A: (33, 0), 0x0B: (52, 0), 0x0C: (71, 0), 0x0D: (71, 1),
                  0x0E: (73, 0), 0x0F: (55, 0), 0x10: (60, 0), 0x13: (93, 0), 0x14: (96, 0), 0x15: (102, 0), 0x16: (107, 0),
                  0x17: (115, 0), 0x18: (118, 0), 0x1B: (37, 0), 0x1C: (40, 0), 0x1D: (66, 0), 0x1E: (44, 0), 0x1F: (28, 0),
                  0x20: (28, 1), 0x21: (30, 0), 0x22: (30, 1), 0x24: (137, 0), 0x2C: (175, 0)}
    # named only where the picture of the spawned enemy is clear (trace/v15_profiles/ninjagaiden/crops_ng2)
    ENEMIES = {0x04: 'Soldier in green', 0x05: 'Axe brute', 0x07: 'Sword ninja', 0x0B: 'Fire spirit', 0x0C: 'Crouching thug',
               0x0E: 'Spider', 0x10: 'Bald brute', 0x13: 'Axe brute (second kind)', 0x18: 'Red ninja'}
    # pickup code at $9807: 0-4 set the ninja art ($7D, named by the icon the status bar then shows), the rest measured
    ITEMS = {0x0: 'Throwing star', 0x1: 'Windmill star', 0x2: 'Art of the fire wheel', 0x3: 'Fire dragon balls',
             0x4: 'Invincible fire wheel', 0x5: 'Spirit points (10)', 0x6: 'Spirit points (refill)',
             0x7: 'Spirit limit up (10)', 0x8: 'Health (restores 6)', 0x9: 'Extra life', 0xA: 'Shadow double',
             0xB: 'Bonus points (1000)', 0xC: 'Bonus points (2000)'}

    # length (code $CED2): layout pointer $A700/$A730 in bank 1 (ROM $2700/$2730), last screen low nibble of $8180,
    # the camera stops at screen $7F ($DAA6); unused space after the last layout, $A136-$A6FF (the first 144 bytes stay:
    # the game draws up to three screens past an area's end, off screen)
    LAYOUT_LO, LAYOUT_HI, LAST, FREE = 0x2700, 0x2730, 0x8180, (0xA1C6, 0xA700)

    def __init__(self, rom: bytes):
        self.rom = rom

    def plain_section(self, area: int) -> bool:
        return not self.leftward(area)

    def offset(self, address: int) -> int:
        """ROM file offset of a CPU address in the list bank ($8000-$9FFF is ROM $8000-$9FFF)."""
        return HEADER_NES + address

    def _b(self, address: int) -> int:
        return self.rom[self.offset(address)]

    def _ptr(self, lo: int, hi: int, area: int) -> int:
        return self._b(lo + area) | self._b(hi + area) << 8

    def leftward(self, area: int) -> bool:
        return bool(self._b(0x80F0 + area) & 0x80)

    def lists(self, area: int) -> dict:
        return {'lantern_col': self._ptr(0x8720, 0x8750, area), 'lantern_item': self._ptr(0x8780, 0x87B0, area),
                'col': self._ptr(0x87E0, 0x8810, area), 'place': self._ptr(0x8840, 0x8870, area), 'type': self._ptr(0x88A0, 0x88D0, area),
                'lanterns': self._b(0x82A0 + area), 'enemies': self._b(0x82D0 + area),
                'lantern_count': self.offset(0x82A0 + area), 'enemy_count': self.offset(0x82D0 + area)}

    def enemies(self, area: int) -> list:
        L, left = self.lists(area), self.leftward(area)
        out = []
        for i in range(L['enemies']):
            col, place, kind = self._b(L['col'] + i), self._b(L['place'] + i), self._b(L['type'] + i)
            out.append({'index': i, 'col': col, 'place': place, 'type': kind,
                        'x': (col - (1 if left else 0) + (place & 15)) * 16, 'y': (place & 0xF0) | 8})
        return out

    def lanterns(self, area: int) -> list:
        L, left = self.lists(area), self.leftward(area)
        out = []
        for i in range(L['lanterns']):
            col, held = self._b(L['lantern_col'] + i), self._b(L['lantern_item'] + i)
            out.append({'index': i, 'col': col, 'item': held & 15, 'x': (col - (1 if left else 0)) * 16, 'y': held & 0xF0,
                        'item_byte': self.offset(L['lantern_item'] + i)})
        return out

    def owners(self) -> dict:
        count = {}
        for area in range(self.AREAS):
            L = self.lists(area)
            for key, n in (('col', L['enemies']), ('place', L['enemies']), ('type', L['enemies']),
                           ('lantern_col', L['lanterns']), ('lantern_item', L['lanterns'])):
                for i in range(n):
                    o = self.offset(L[key] + i)
                    count[o] = count.get(o, 0) + 1
        return count

    def delete_writes(self, area: int, kind: str, index: int) -> list:
        """Writes that take entry `index` out of an area's enemy or lantern list: later entries move up one, the count
        drops by one. Refused where another list reads the same bytes."""
        L = self.lists(area)
        keys, count, at = (('col', 'place', 'type'), L['enemies'], L['enemy_count']) if kind == 'enemy' else \
            (('lantern_col', 'lantern_item'), L['lanterns'], L['lantern_count'])
        if not 0 <= index < count:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        shared = self.owners()
        writes = []
        for key in keys:
            for i in range(index, count - 1):
                o = self.offset(L[key] + i)
                if shared.get(o, 1) > 1:
                    raise ValueError('The game reads these bytes for another list too, so ROMancer leaves this list alone.')
                writes.append((o, self.rom[o], self._b(L[key] + i + 1)))
        writes.append((at, count, count - 1))
        return [w for w in writes if w[1] != w[2]]

    def enemy_name(self, kind: int) -> str:
        if kind in self.BOSS_TYPES:
            return f'Boss (type {kind:#04x})'
        return self.ENEMIES.get(kind, f'Enemy {kind:#04x}')

    def item_name(self, item: int) -> str:
        return self.ITEMS.get(item, f'Item {item:#04x}')

    def stage_types(self, area: int) -> list:
        """Enemy types used in any area with the same stage number (the ones that draw right there)."""
        label = self.LABELS[area]
        kinds = set()
        for other in range(self.AREAS):
            if self.LABELS[other] == label:
                kinds.update(e['type'] for e in self.enemies(other) if e['type'] in self.SIGNATURES and e['type'] not in self.BOSS_TYPES)
        return sorted(kinds)


class _NG2Watcher(Watcher):
    """Ninja Gaiden II. A swap or a new lantern item: the entry's first appearance (spawned flag $0440 for enemies,
    lantern slots 4-7 with list number $0640). A removal compares the original and the changed game: how many
    things appear from the removed column in each."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.compare = bool(watch['remove'])
        self.flags = None
        self.slots = {}
        self.seen = None
        self.count = {}
        self.run = None

    def _column(self, ram):
        """The list column the game tests against right now: enemies at the camera column $40 (one more when walking
        left), lanterns 16 further on."""
        w = self.w
        if w['kind'] == 'enemy':
            return ram[0x40] + (1 if w.get('left') else 0)
        return ram[0x40] + (1 if w.get('left') else 16)

    def _events(self, ram):
        """[(entry index, slot)] that appeared since the last look."""
        w, out = self.w, []
        if w['kind'] == 'enemy':
            flags = bytes(ram[0x440:0x448])
            occupied = {s: ram[0x658 + s] for s in range(0x0B, 0x18) if ram[0x48 + (s >> 3)] >> (s & 7) & 1}
            if self.flags is not None:
                for i in range(64):
                    if flags[i >> 3] >> (i & 7) & 1 and not self.flags[i >> 3] >> (i & 7) & 1:
                        new = [s for s, v in occupied.items() if v == i and self.slots.get(s) != i]
                        new = new or [s for s, v in occupied.items() if v == i]     # a slot that held this number before
                        if new:             # flags that change with no enemy behind them (the title screen) are not spawns
                            out.append((i, new[0]))
            self.flags, self.slots = flags, occupied
        else:
            occupied = {s: ram[0x640 + s] for s in range(4, 8) if ram[0x48] >> s & 1 and ram[0x4D8 + s] == 0}
            out = [(v, s) for s, v in occupied.items() if self.slots.get(s) != v]
            self.slots = occupied
        return out

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x7E] != w['area'] or run != self.run:
            self.flags, self.slots, self.run = None, {}, run
            return False
        events = self._events(ram)
        if w['remove']:
            # what appears while the camera stands where the removed entry appeared (the game's own spawn test)
            self.count[run] = self.count.get(run, 0) + sum(1 for _ in events if self._column(ram) == w['col'])
            return False
        for i, s in events:
            if i == w['index'] and self.seen is None:
                if s is None:
                    self.seen = -1
                elif w['kind'] == 'enemy':
                    self.seen = (ram[0x4D8 + s], ram[0x4F0 + s] & 1)
                else:
                    self.seen = ram[0x520 + s] & 15
        return self.seen is not None

    def result(self):
        w = self.w
        what = 'enemy' if w['kind'] == 'enemy' else 'lantern'
        if w['remove']:
            old, new = self.count.get('original', 0), self.count.get('changed', 0)
            if old == 0:
                return super().result()
            others = sum(1 for c in w['cols_changed'] if c == w['col'])
            ok = new == 0 if not others else new < old
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the walk passes that spot and the {what} there no longer appears.' if ok
                    else f'Played from the start, the {what} still appears there.'}
        if self.seen is None:
            return super().result()
        if w['kind'] == 'enemy':
            ok = self.seen == tuple(w['signature'])
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game now spawns {w["name"]} there.' if ok
                    else 'Played from the start, the game spawned a different enemy there, not what was chosen '
                         f'(object {self.seen[0]:#04x}).' if self.seen != -1 else
                    'Played from the start, an enemy appeared there but ROMancer could not see which one.'}
        ok = self.seen == w['item']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the lantern there now holds {w["name"]}.' if ok
                else f'Played from the start, the lantern there holds item {self.seen & 0xFF:#04x}, not the one chosen.'}


class _NG23LengthWatcher(Watcher):
    """A length change in Ninja Gaiden II or III, judged from the game's own memory on the original and the changed
    game: the scroll limit the area set-up loads, the layout column the game last copied (its 6 block numbers and the
    layout pointer it read them from, checked against the planned layout and the camera), and the camera column at
    which each enemy spawns. The RAM addresses differ per game (the class attributes)."""
    compare = True
    every = 1
    AREA, LIMIT, CAMERA, COLUMN, FLAGS, FLAG_BYTES, POINTER, BLOCKS = 0x7E, 0x7F, 0x3A, 0x40, 0x440, 8, 0x86, 0x1E0
    FLAG_HIGH_FIRST = False
    AHEAD = (8, 9, 10)          # layout column - camera column of the column just copied, walking right

    def __init__(self, watch):
        self.w = watch
        self.visits = {}

    @staticmethod
    def _numbers(ram):
        """List numbers of the enemies in the game's enemy slots ($0B-$17, in use: bits of $48-$4A, number $0658)."""
        return {ram[0x658 + s] for s in range(0x0B, 0x18) if ram[0x48 + (s >> 3)] >> (s & 7) & 1}

    def _flag(self, flags, i):
        mask = 0x80 >> (i & 7) if self.FLAG_HIGH_FIRST else 1 << (i & 7)
        return bool(flags[i >> 3] & mask)

    def see(self, ram, frame, run):
        w = self.w
        visits = self.visits.setdefault(run, [])
        inside = ram[self.AREA] == w['area'] and (ram[self.LIMIT] & 0x0F) == ram[self.LIMIT]
        visit = visits[-1] if visits and visits[-1]['open'] else None
        if not inside:
            if visit is not None:
                visit['open'] = False
                visit['left'] = frame
            return False
        flags = bytes(ram[self.FLAGS:self.FLAGS + self.FLAG_BYTES])
        if visit is None:
            visit = {'open': True, 'start': frame, 'limit': None, 'far': 0, 'spawn': {}, 'flags': flags, 'left': None,
                     'same': 0, 'differ': 0, 'last': None}
            visits.append(visit)
        visit['limit'] = ram[self.LIMIT]
        camera = ram[self.CAMERA] | ram[self.CAMERA + 1] << 8
        visit['far'] = max(visit['far'], camera)
        for i in range(self.FLAG_BYTES * 8):
            # a flag that rises with an enemy of that list number in a slot (the flags hold other things on the title)
            if self._flag(flags, i) and not self._flag(visit['flags'], i) and i not in visit['spawn'] and i in self._numbers(ram):
                visit['spawn'][i] = ram[self.COLUMN]
        visit['flags'] = flags
        if run == 'changed' and w['expect']:
            pointer = ram[self.POINTER] | ram[self.POINTER + 1] << 8
            blocks = bytes(ram[self.BLOCKS:self.BLOCKS + 6]).hex()
            if blocks != visit['last']:         # only when the game has just copied a column (not when it turns round)
                visit['last'] = blocks
                k = (pointer - w['base']) // 6
                near = [j for j in (k - 1, k) if 0 <= j < len(w['expect'])]
                # walking right the game reads the column 8 to 10 columns ahead of the camera; walking left it reads
                # behind it, and those looks are left out
                if near and k * 6 == pointer - w['base'] and k - camera // 32 in self.AHEAD:
                    visit['same' if any(w['expect'][j] == blocks for j in near) else 'differ'] += 1
        return False

    @staticmethod
    def _best(visits):
        return max(visits, key=lambda v: (v['far'], v['start'])) if visits else None

    def result(self):
        w = self.w
        old, new = self._best(self.visits.get('original', [])), self._best(self.visits.get('changed', []))
        if old is None or new is None:
            return super().result()
        if new['limit'] != w['new'] - 1 or old['limit'] != w['old'] - 1:
            return {'state': 'bad', 'text': f'Played from the start, the game gives this part {(new["limit"] or 0) + 1} screens, not the {w["new"]} chosen.'}
        moved = wrong = 0
        for was_index, now_index, was, now in w['enemy_map']:
            if now == was:
                continue
            if now_index is None:
                continue                    # taken out of the list: its number now belongs to the next enemy
            if was_index in old['spawn'] and now_index in new['spawn']:
                if new['spawn'][now_index] - old['spawn'][was_index] == now - was:
                    moved += 1
                else:
                    wrong += 1
        if w['expect'] and not new['same']:
            return {'state': 'bad', 'text': f'Played from the start, the game gives this part {w["new"]} screens, but ROMancer could not see it read the planned layout.'}
        if new['differ'] or wrong:
            return {'state': 'bad', 'text': f'Played from the start, the game gives this part {w["new"]} screens, but what it shows does not follow the plan '
                                            f'({new["differ"]} of {new["same"] + new["differ"]} columns and {wrong} enemies differ).'}
        text = f'Played from the start, the game now gives this part {w["new"]} screens (it had {w["old"]}).'
        if new['same']:
            text += f' All {new["same"]} columns of blocks the game read as the walk went on are the planned ones, at the planned place.'
        if moved:
            text += f' {moved} {"enemy appears" if moved == 1 else "enemies appear"} {abs(w["new"] - w["old"])} screen{"s" if abs(w["new"] - w["old"]) > 1 else ""} {"later" if w["new"] > w["old"] else "earlier"}, as planned.'
        if new['far'] >= (w['new'] - 1) * 256 and new['left'] and old['left']:
            seconds = round(abs(new['left'] - old['left']) / 60, 1)
            text += f' The walk reaches the new end, and the next part starts {seconds} seconds {"later" if new["left"] > old["left"] else "earlier"}.'
        else:
            got = new['far'] // 256 + 1
            text += f' The recorded walk gets {got} screen{"s" if got > 1 else ""} in.'
        if w['notes']:
            text += ' ' + ' '.join(w['notes'])
        return {'state': 'good', 'text': text}


class NinjaGaiden2Profile(NinjaGaiden2, Profile):
    """Ninja Gaiden II on the common profile interface. Parts are {'area': $7E}; x is the camera ($3A/$3B)."""
    sha256s = (NinjaGaiden2.sha256,)

    def where(self, ram):
        area = ram[0x7E]
        if area >= self.AREAS:
            return None
        return {'part': {'area': area}, 'x': ram[0x3A] | ram[0x3B] << 8, 'y': 0}

    def part_name(self, part):
        area = int(part['area'])
        label = self.LABELS[area]
        same = [a for a in range(self.AREAS) if self.LABELS[a] == label]
        return f'Stage {label}' + (f', section {same.index(area) + 1}' if len(same) > 1 else '')

    def choices(self):
        out = {'items': [{'value': k, 'name': v} for k, v in self.ITEMS.items()]}
        for label in sorted(set(self.LABELS)):
            area = self.LABELS.index(label)
            out['enemies_' + label] = [{'value': t, 'name': self.enemy_name(t)} for t in self.stage_types(area)]
        return out

    def objects(self, part):
        area = int(part['area'])
        label = self.LABELS[area]
        shared = self.owners()
        L = self.lists(area)
        out = []
        for e in self.enemies(area):
            fixed = e['type'] in self.BOSS_TYPES or e['type'] not in self.SIGNATURES
            row = {'id': f'enemy:{e["index"]}', 'style': 'enemy', 'type': e['type'], 'x': e['x'], 'y': e['y'],
                   'name': self.enemy_name(e['type']), 'remove': None if fixed else 'Remove this enemy',
                   'fields': [] if fixed else [{'key': 'type', 'label': 'Swap for', 'value': e['type'], 'choices': 'enemies_' + label}]}
            if any(shared.get(self.offset(L[k] + e['index']), 1) > 1 for k in ('col', 'place', 'type')):
                row.update(remove=None, fields=[], note='The game reads this entry’s bytes for another list too, so ROMancer leaves it alone.')
            out.append(row)
        for lantern in self.lanterns(area):
            known = lantern['item'] in self.ITEMS
            row = {'id': f'lantern:{lantern["index"]}', 'style': 'item', 'type': 'lantern', 'x': lantern['x'], 'y': lantern['y'],
                   'name': 'Lantern', 'detail': f'holds {self.item_name(lantern["item"])}', 'remove': 'Remove this lantern',
                   'fields': [{'key': 'item', 'label': 'Holds', 'value': lantern['item'], 'choices': 'items'}] if known else []}
            if any(shared.get(self.offset(L[k] + lantern['index']), 1) > 1 for k in ('lantern_col', 'lantern_item')):
                row.update(remove=None, fields=[], note='The game reads this lantern’s bytes for another list too, so ROMancer leaves it alone.')
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        area = int(part['area'])
        kind, _, number = object_id.partition(':')
        number = int(number)
        item = self.find(part, object_id)
        if (remove and not item.get('remove')) or (not remove and not item.get('fields')):
            raise ValueError('ROMancer cannot change that yet.')
        watch = {'kind': kind, 'area': area, 'index': number, 'remove': bool(remove)}
        if remove:
            rows = self.enemies(area) if kind == 'enemy' else self.lanterns(area)
            writes = self.delete_writes(area, kind, number)
            after = rows[:number] + rows[number + 1:]
            watch.update(col=rows[number]['col'], left=self.leftward(area), cols_changed=[r['col'] for r in after])
            title = f'Remove the {self.enemy_name(rows[number]["type"]).lower()}' if kind == 'enemy' else 'Remove the lantern'
        elif kind == 'enemy':
            e = self.enemies(area)[number]
            new = int(values.get('type'))
            if new not in self.stage_types(area):
                raise ValueError('That choice is not one of the game’s own.')
            o = self.offset(self.lists(area)['type'] + number)
            writes = [(o, e['type'], new)]
            watch.update(signature=list(self.SIGNATURES[new]), name=self.enemy_name(new))
            title = f'Enemy here: {self.enemy_name(new)}'
        elif kind == 'lantern':
            lantern = self.lanterns(area)[number]
            new = int(values.get('item'))
            if new not in self.ITEMS:
                raise ValueError('That choice is not one of the game’s own.')
            old = self.rom[lantern['item_byte']]
            writes = [(lantern['item_byte'], old, (old & 0xF0) | new)]
            watch.update(item=new, name=self.item_name(new))
            title = f'Lantern holds: {self.item_name(new)}'
        else:
            raise ValueError('ROMancer cannot change that yet.')
        return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'{title} ({self.part_name(part)})', 'watch': watch}

    def watcher(self, watch):
        if watch.get('kind') == 'length':
            return _NG23LengthWatcher(watch)
        return _NG2Watcher(watch)

    def screens(self, part):
        area = int(part['area'])
        if self.resizable(area):
            return None
        return {'count': self.area_last(area) + 1, 'most': self.MOST}

    def resize(self, part, at, delta):
        area = int(part['area'])
        old = self.area_last(area) + 1
        result = self.resize_writes(area, int(at), int(delta))
        changed = bytearray(self.rom)
        for offset, _, value in result['writes']:
            changed[offset] = value
        after = type(self)(bytes(changed))
        new, base = result['screens'], after.layout(area)
        expect = [] if self.leftward(area) else [bytes(changed[after.layout_offset(base) + 6 * k:after.layout_offset(base) + 6 * k + 6]).hex()
                                                 for k in range(new * 8)]
        watch = {'kind': 'length', 'area': area, 'old': old, 'new': new, 'base': base, 'expect': expect,
                 'enemy_map': result['enemy_map'], 'notes': result['notes']}
        return {'writes': result['writes'], 'notes': result['notes'], 'watch': watch}


class NinjaGaiden3(_TecmoLength):
    """Ninja Gaiden III - The Ancient Ship of Doom (USA), MMC3. Its own code again (laid out like the second game's,
    but moved and changed: none of the second game's spawn code is in it byte for byte).

    The area $5F (0-47) indexes tables in the bank at $A000 (ROM $C000-$DFFF, set up at $86EE): lantern column
    ($A390/$A3C0 low/high pointer), lantern item and height ($A3F0/$A420), enemy column ($A450/$A480), place
    ($A4B0/$A4E0), type ($A510/$A540); counts are the top five bits of $A240 (lanterns) and $A210 (enemies). Bits 6-7
    of $A0F0 mark vertical or reversed sections. In a rightward section an enemy spawns when the camera column $D1
    equals its column ($807B), at screen x (place & $0F) * 16 and y place & $F0, the type picking the object through
    $C50F; a lantern ($8270) appears when the camera column is 16 less than its column. Both lists are read in order;
    the enemy list has no count check, so a removed enemy leaves column $FF behind it, which the camera never reaches.
    """
    name = 'Ninja Gaiden III'
    sha256 = 'c04c5c03653d1611ba9164ce5276748347f5fd3baeb867101b2a06b9b249a9b4'
    AREAS = 48
    # the status bar's STAGE-x-yZ in each area (read from the screen after starting the game in every area)
    LABELS = ['1-1A', '1-1B', '1-1C', '1-2A', '2-1A', '2-2A', '2-2B', '2-2C', '2-2D', '2-3A', '3-1A', '3-2A', '3-2B', '3-2C',
              '3-2D', '3-3A', '4-1A', '4-2A', '4-2B', '4-2C', '4-3A', '5-1A', '5-1B', '5-1C', '5-2A', '5-2B', '5-2C', '5-2D',
              '5-2E', '5-3A', '6-1A', '6-1B', '6-1C', '6-2A', '6-2B', '6-3A', '7-1A', '7-2A', '7-2B', '7-2C', '7-2D', '7-3A',
              '7-3B', '7-3C', '7-3D', '7-4A', '7-5A', '7-6A']
    # (object $037E, bit 0 of $04CE) at the moment each type spawns, measured in stage 1-1A
    # (trace/v15_profiles/ninjagaiden/ng3_sig_area0.json); it is $C50F and bit 0 of $C2B7 except for 0x10 and 0x24
    SIGNATURES = {0x00: (56, 0), 0x01: (56, 1), 0x02: (57, 0), 0x03: (57, 1), 0x04: (59, 0), 0x05: (59, 1), 0x06: (60, 0),
                  0x09: (83, 0), 0x0A: (83, 1), 0x0C: (71, 1), 0x0D: (66, 0), 0x0E: (66, 1), 0x0F: (92, 0), 0x10: (152, 0),
                  0x11: (80, 0), 0x12: (70, 0), 0x13: (86, 0), 0x15: (64, 0), 0x16: (75, 0), 0x17: (75, 0), 0x18: (61, 0),
                  0x19: (61, 0), 0x1B: (100, 1), 0x1F: (121, 0), 0x20: (150, 0), 0x21: (102, 0), 0x22: (106, 0), 0x23: (109, 0),
                  0x24: (115, 0), 0x25: (118, 0), 0x26: (123, 0), 0x27: (128, 0), 0x28: (138, 0), 0x2B: (141, 0)}
    # what collecting each item did (measured in stage 1-1A); 0-4 set the ninja art $9F, named by the status bar icon
    ITEMS = {0x0: 'Windmill star', 0x1: 'Art of the fire wheel', 0x2: 'Fire dragon balls', 0x3: 'Vacuum wave',
             0x4: 'Invincible fire wheel', 0x5: 'Sword power-up (likely)', 0x6: 'Spirit points (10)', 0x7: 'Spirit points (40)',
             0x8: 'Spirit limit up (10)', 0x9: 'Item 0x09', 0xA: 'Extra life', 0xB: 'Item 0x0B'}

    def __init__(self, rom: bytes):
        self.rom = rom

    # length (code $86EE): layout pointer $B960/$B990 in bank 1 (ROM $3960/$3990), last screen low nibble of $A1B0 ($48,
    # where the camera screen $DC stops, $910D); banks 0 and 1 have no unused space, so parts can only be made shorter
    LAYOUT_LO, LAYOUT_HI, LAST, FREE = 0x3960, 0x3990, 0xA1B0, None

    def plain_section(self, area: int) -> bool:
        return self.plain(area)

    def offset(self, address: int) -> int:
        """ROM file offset of a CPU address in the table bank ($A000-$BFFF is ROM $C000-$DFFF)."""
        return HEADER_NES + 0xC000 + (address - 0xA000)

    def _b(self, address: int) -> int:
        return self.rom[self.offset(address)]

    def _ptr(self, lo: int, hi: int, area: int) -> int:
        return self._b(lo + area) | self._b(hi + area) << 8

    def plain(self, area: int) -> bool:
        """A section walked rightwards (not vertical, not reversed): the only kind this profile places objects in."""
        return not self._b(0xA0F0 + area) & 0xC0

    def lists(self, area: int) -> dict:
        return {'lantern_col': self._ptr(0xA390, 0xA3C0, area), 'lantern_item': self._ptr(0xA3F0, 0xA420, area),
                'col': self._ptr(0xA450, 0xA480, area), 'place': self._ptr(0xA4B0, 0xA4E0, area), 'type': self._ptr(0xA510, 0xA540, area),
                'lanterns': self._b(0xA240 + area) >> 3, 'enemies': self._b(0xA210 + area) >> 3,
                'lantern_count': self.offset(0xA240 + area), 'enemy_count': self.offset(0xA210 + area)}

    def enemies(self, area: int) -> list:
        L = self.lists(area)
        out = []
        for i in range(L['enemies']):
            col, place, kind = self._b(L['col'] + i), self._b(L['place'] + i), self._b(L['type'] + i)
            out.append({'index': i, 'col': col, 'place': place, 'type': kind, 'x': (col + (place & 15)) * 16, 'y': place & 0xF0})
        return out

    def lanterns(self, area: int) -> list:
        L = self.lists(area)
        out = []
        for i in range(L['lanterns']):
            col, held = self._b(L['lantern_col'] + i), self._b(L['lantern_item'] + i)
            out.append({'index': i, 'col': col, 'item': held & 15, 'x': col * 16, 'y': held & 0xF0,
                        'item_byte': self.offset(L['lantern_item'] + i)})
        return out

    def owners(self) -> dict:
        count = {}
        for area in range(self.AREAS):
            L = self.lists(area)
            for key, n in (('col', L['enemies'] + 1), ('place', L['enemies']), ('type', L['enemies']),
                           ('lantern_col', L['lanterns']), ('lantern_item', L['lanterns'])):
                for i in range(n):
                    o = self.offset(L[key] + i)
                    count[o] = count.get(o, 0) + 1
        return count

    def delete_writes(self, area: int, kind: str, index: int) -> list:
        L = self.lists(area)
        keys, count, at = (('col', 'place', 'type'), L['enemies'], L['enemy_count']) if kind == 'enemy' else \
            (('lantern_col', 'lantern_item'), L['lanterns'], L['lantern_count'])
        if not 0 <= index < count:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        shared = self.owners()
        writes = []
        for key in keys:
            for i in range(index, count - 1):
                o = self.offset(L[key] + i)
                if shared.get(o, 1) > 1:
                    raise ValueError('The game reads these bytes for another list too, so ROMancer leaves this list alone.')
                writes.append((o, self.rom[o], self._b(L[key] + i + 1)))
        if kind == 'enemy':                 # the enemy list has no count check: the freed place gets a column never reached
            o = self.offset(L['col'] + count - 1)
            if shared.get(o, 1) > 1:
                raise ValueError('The game reads these bytes for another list too, so ROMancer leaves this list alone.')
            writes.append((o, self.rom[o], 0xFF))
        old = self.rom[at]
        writes.append((at, old, old - 8))
        return [w for w in writes if w[1] != w[2]]

    def enemy_name(self, kind: int) -> str:
        return f'Enemy {kind:#04x}'

    def item_name(self, item: int) -> str:
        return self.ITEMS.get(item, f'Item {item:#04x}')

    def stage_types(self, area: int) -> list:
        """Enemy types used in the same stage (same STAGE-x-y, any letter) where more than one enemy is placed."""
        stage = self.LABELS[area][:3]
        kinds = set()
        for other in range(self.AREAS):
            rows = self.enemies(other)
            if self.LABELS[other][:3] == stage and len(rows) > 1:
                kinds.update(e['type'] for e in rows if e['type'] in self.SIGNATURES)
        return sorted(kinds)


class _NG3Watcher(_NG2Watcher):
    """Ninja Gaiden III: the second game's watcher with this game's RAM (area $5F, spawned flags $D7-$D9 high bit
    first, enemy slots $10-$17 in use when bit 7 of $04E6 is set, list number $043E, object $037E; lantern slots 4-7
    with list number $04B6 and item $03DE)."""

    def _column(self, ram):
        return ram[0xD1] + (0 if self.w['kind'] == 'enemy' else ram[0x86])

    def _events(self, ram):
        w, out = self.w, []
        if w['kind'] == 'enemy':
            flags = bytes(ram[0xD7:0xDA])
            occupied = {s: ram[0x43E + s] for s in range(0x10, 0x18) if ram[0x4E6 + s] & 0x80}
            if self.flags is not None:
                for i in range(24):
                    mask = 0x80 >> (i & 7)
                    if flags[i >> 3] & mask and not self.flags[i >> 3] & mask:
                        new = [s for s, v in occupied.items() if v == i and self.slots.get(s) != i]
                        new = new or [s for s, v in occupied.items() if v == i]     # a slot that held this number before
                        if new:             # flags that change with no enemy behind them (the title screen) are not spawns
                            out.append((i, new[0]))
            self.flags, self.slots = flags, occupied
        else:
            occupied = {s: ram[0x4B6 + s] for s in range(4, 8) if ram[0x4E6 + s] & 0x80}
            out = [(v, s) for s, v in occupied.items() if self.slots.get(s) != v]
            self.slots = occupied
        return out

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x5F] != w['area'] or run != self.run:
            self.flags, self.slots, self.run = None, {}, run
            return False
        events = self._events(ram)
        if w['remove']:
            self.count[run] = self.count.get(run, 0) + sum(1 for _ in events if self._column(ram) == w['col'])
            return False
        for i, s in events:
            if i == w['index'] and self.seen is None:
                if s is None:
                    self.seen = -1
                elif w['kind'] == 'enemy':
                    self.seen = (ram[0x37E + s], ram[0x4CE + s] & 1)
                else:
                    self.seen = ram[0x3DE + s] & 15
        return self.seen is not None


class _NG3LengthWatcher(_NG23LengthWatcher):
    """Ninja Gaiden III: area $5F, last screen $48, camera $84/$85, camera column $D1, enemy spawned flags $D7-$D9
    (high bit first), layout pointer $40/$41 and the column copied to $01E0 (code $C01E)."""
    AREA, LIMIT, CAMERA, COLUMN, FLAGS, FLAG_BYTES, POINTER, BLOCKS = 0x5F, 0x48, 0x84, 0xD1, 0xD7, 3, 0x40, 0x1E0
    FLAG_HIGH_FIRST = True

    @staticmethod
    def _numbers(ram):
        """List numbers of the enemies in slots $10-$17 (in use: bit 7 of $04E6, number $043E)."""
        return {ram[0x43E + s] for s in range(0x10, 0x18) if ram[0x4E6 + s] & 0x80}


class NinjaGaiden3Profile(NinjaGaiden3, Profile):
    """Ninja Gaiden III on the common profile interface. Parts are {'area': $5F}; x is the camera ($84/$85)."""
    sha256s = (NinjaGaiden3.sha256,)

    def where(self, ram):
        area = ram[0x5F]
        if area >= self.AREAS:
            return None
        return {'part': {'area': area}, 'x': ram[0x84] | ram[0x85] << 8, 'y': 0}

    def part_name(self, part):
        return f'Stage {self.LABELS[int(part["area"])]}'

    def choices(self):
        out = {'items': [{'value': k, 'name': v} for k, v in self.ITEMS.items()]}
        for area in range(self.AREAS):
            out[f'enemies_{area}'] = [{'value': t, 'name': self.enemy_name(t)} for t in self.stage_types(area)]
        return out

    def objects(self, part):
        area = int(part['area'])
        if not self.plain(area):
            return []
        shared = self.owners()
        L = self.lists(area)
        out = []
        for e in self.enemies(area):
            fixed = e['type'] not in self.SIGNATURES or e['type'] not in self.stage_types(area)
            row = {'id': f'enemy:{e["index"]}', 'style': 'enemy', 'type': e['type'], 'x': e['x'], 'y': e['y'],
                   'name': self.enemy_name(e['type']), 'remove': None if fixed else 'Remove this enemy',
                   'fields': [] if fixed else [{'key': 'type', 'label': 'Swap for', 'value': e['type'], 'choices': f'enemies_{area}'}]}
            if any(shared.get(self.offset(L[k] + e['index']), 1) > 1 for k in ('col', 'place', 'type')):
                row.update(remove=None, fields=[], note='The game reads this entry’s bytes for another list too, so ROMancer leaves it alone.')
            out.append(row)
        for lantern in self.lanterns(area):
            known = lantern['item'] in self.ITEMS
            row = {'id': f'lantern:{lantern["index"]}', 'style': 'item', 'type': 'lantern', 'x': lantern['x'], 'y': lantern['y'],
                   'name': 'Lantern', 'detail': f'holds {self.item_name(lantern["item"])}', 'remove': 'Remove this lantern',
                   'fields': [{'key': 'item', 'label': 'Holds', 'value': lantern['item'], 'choices': 'items'}] if known else []}
            if any(shared.get(self.offset(L[k] + lantern['index']), 1) > 1 for k in ('lantern_col', 'lantern_item')):
                row.update(remove=None, fields=[], note='The game reads this lantern’s bytes for another list too, so ROMancer leaves it alone.')
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        area = int(part['area'])
        kind, _, number = object_id.partition(':')
        number = int(number)
        item = self.find(part, object_id)
        if (remove and not item.get('remove')) or (not remove and not item.get('fields')):
            raise ValueError('ROMancer cannot change that yet.')
        watch = {'kind': kind, 'area': area, 'index': number, 'remove': bool(remove)}
        if remove:
            rows = self.enemies(area) if kind == 'enemy' else self.lanterns(area)
            writes = self.delete_writes(area, kind, number)
            after = rows[:number] + rows[number + 1:]
            watch.update(col=rows[number]['col'], cols_changed=[r['col'] for r in after])
            title = 'Remove the enemy' if kind == 'enemy' else 'Remove the lantern'
        elif kind == 'enemy':
            e = self.enemies(area)[number]
            new = int(values.get('type'))
            if new not in self.stage_types(area):
                raise ValueError('That choice is not one of the game’s own.')
            if self.SIGNATURES[new] == self.SIGNATURES.get(e['type']):
                raise ValueError('The game makes the same enemy for both of these, so there is nothing to change.')
            o = self.offset(self.lists(area)['type'] + number)
            writes = [(o, e['type'], new)]
            watch.update(signature=list(self.SIGNATURES[new]), name=self.enemy_name(new))
            title = f'Enemy here: {self.enemy_name(new)}'
        elif kind == 'lantern':
            lantern = self.lanterns(area)[number]
            new = int(values.get('item'))
            if new not in self.ITEMS:
                raise ValueError('That choice is not one of the game’s own.')
            old = self.rom[lantern['item_byte']]
            writes = [(lantern['item_byte'], old, (old & 0xF0) | new)]
            watch.update(item=new, name=self.item_name(new))
            title = f'Lantern holds: {self.item_name(new)}'
        else:
            raise ValueError('ROMancer cannot change that yet.')
        return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'{title} ({self.part_name(part)})', 'watch': watch}

    def watcher(self, watch):
        if watch.get('kind') == 'length':
            return _NG3LengthWatcher(watch)
        return _NG3Watcher(watch)

    def screens(self, part):
        area = int(part['area'])
        if self.resizable(area):
            return None
        return {'count': self.area_last(area) + 1, 'most': self.most_screens(area)}

    def resize(self, part, at, delta):
        area = int(part['area'])
        old = self.area_last(area) + 1
        result = self.resize_writes(area, int(at), int(delta))
        changed = bytearray(self.rom)
        for offset, _, value in result['writes']:
            changed[offset] = value
        after = type(self)(bytes(changed))
        new, base = result['screens'], after.layout(area)
        expect = [bytes(changed[after.layout_offset(base) + 6 * k:after.layout_offset(base) + 6 * k + 6]).hex() for k in range(new * 8)]
        watch = {'kind': 'length', 'area': area, 'old': old, 'new': new, 'base': base, 'expect': expect,
                 'enemy_map': result['enemy_map'], 'notes': result['notes']}
        return {'writes': result['writes'], 'notes': result['notes'], 'watch': watch}


PROFILES = [NinjaGaiden1Profile, NinjaGaiden2Profile, NinjaGaiden3Profile]
