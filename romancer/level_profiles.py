"""What ROMancer knows about the levels of particular games: their enemies, items, secrets and what their blocks do.

A profile reads the game's own tables (worked out from the game's code and proven by replaying the game) and turns them
into things on a level map. Edits are exact ROM writes; ROMancer checks each one by replaying the game.

Only games with a profile get these; every other game keeps the general level map tools.
"""
from __future__ import annotations

import hashlib

HEADER_NES = 16


class Castlevania:
    """Castlevania (USA). Spawn code: bank 7 $D10D / $D199. Items: $EB46. Collision: $F9B0.

    A stage is cut into zones of 64 pixels. Each zone has two bytes in the stage's zone table: an enemy index and a
    candle index. The indexes pick records from shared pools (enemy records at $D6A1; candle records at $D6A1, or
    $D7A1 for indexes of $80 and up). Records are shared between zones, so a change to one zone points it at another
    record and leaves the record alone.
    """
    name = 'Castlevania'
    sha256 = '55bcab0d9efc33a9d9efc90f2c3c4ab12f3221a44b1f357e6c6202a456399aa8'
    BANK7 = 0x1C000            # ROM offset (no header) of CPU $C000
    ZONE = 64
    # spawner types identified by spawning each one and looking at what the game drew (trace/v14_objects/enemy_types_sheet.png)
    ENEMIES = {0x01: 'Zombies', 0x02: 'Zombies', 0x03: 'Zombies', 0x04: 'Zombies', 0x05: 'Zombies', 0x06: 'Zombies',
               0x51: 'Panther', 0x5E: 'Phantom Bat (boss)'}
    UNSURE = set()
    # item codes, from the pickup code at $E73E (bank 7): 0 small heart (a weak whip gets the whip upgrade instead), 1 money
    # bag, 3 whip upgrade, 4 large heart, 5 pot roast, 6 magic crystal, A rosary, C double or triple shot, E invisibility
    # potion, and the rest set the subweapon (2 and 7 are numbers no subweapon uses)
    DROPS = {0x0: 'Heart or whip upgrade', 0x1: 'Money bag', 0x2: 'Empty subweapon (0x02)', 0x3: 'Whip upgrade',
             0x4: 'Large heart', 0x5: 'Pot roast', 0x6: 'Magic crystal (ends the stage)', 0x7: 'Empty subweapon (0x07)',
             0x8: 'Dagger', 0x9: 'Cross', 0xA: 'Rosary', 0xB: 'Holy water', 0xC: 'Double or triple shot', 0xD: 'Axe',
             0xE: 'Invisibility potion', 0xF: 'Stopwatch'}
    # hidden treasure ($A63A, bank 6): 4 bytes each, table $FC14 by stage. What appears is byte 3; how it is found is
    # bits 1-2 of byte 0 (jump table at $A67C)
    TREASURES = {0: 'Money bag', 1: 'Extra life', 2: 'Crown', 3: 'Treasure chest', 4: 'Moai head'}
    TRIGGERS = {0: 'Stand still there', 1: 'Crouch there', 2: 'Keep walking there', 3: 'Walk there'}
    BANK6 = 0x18000
    SOLID = range(0x60, 0x6C)
    BREAKABLE = {0x66}

    def __init__(self, rom: bytes):
        self.rom = rom

    # ---- reading
    def _at(self, address: int) -> int:
        return self.rom[HEADER_NES + self.BANK7 + (address - 0xC000)]

    def _word(self, address: int) -> int:
        return self._at(address) | self._at(address + 1) << 8

    def offset(self, address: int) -> int:
        """ROM file offset of a CPU address in the fixed bank."""
        return HEADER_NES + self.BANK7 + (address - 0xC000)

    def zone_table(self, stage: int, floor: int) -> int:
        return self._word(self._word(0xD26B + stage * 2) + floor * 2)

    def enemy_record(self, index: int):
        record = self._word(0xD6A1 + index * 2)
        kind = self._at(record)
        return None if not kind else {'type': kind, 'dx': self._at(record + 1), 'y': self._at(record + 2)}

    def candle_record(self, index: int):
        record = self._word((0xD7A1 if index & 0x80 else 0xD6A1) + ((index << 1) & 0xFF))
        first = self._at(record)
        if not first:
            return None
        drop, y = 0, 0
        if first == 0xFF:
            drop, y, first = self._at(record + 1), 2, self._at(record + 2)
        kind = 0x28 if first == 0xFE else 0x27
        if first == 0xFE:
            y += 1
        return {'type': kind, 'dx': self._at(record + y), 'y': self._at(record + y + 1), 'drop': drop, 'record': record}

    def zones(self, stage: int, floor: int, count: int = 64) -> list:
        table = self.zone_table(stage, floor)
        out = []
        for zone in range(count):
            enemy_index, candle_index = self._at(table + zone * 2), self._at(table + zone * 2 + 1)
            out.append({'zone': zone, 'enemy_index': enemy_index, 'candle_index': candle_index,
                        'enemy_byte': self.offset(table + zone * 2), 'candle_byte': self.offset(table + zone * 2 + 1),
                        'enemy': self.enemy_record(enemy_index), 'candle': self.candle_record(candle_index)})
        return out

    # ---- secrets: hidden treasure and breakable blocks (bank 6)
    def _b6(self, address: int) -> int:
        return self.rom[HEADER_NES + self.BANK6 + (address - 0x8000)]

    def _offset6(self, address: int) -> int:
        return HEADER_NES + self.BANK6 + (address - 0x8000)

    def _list_users(self, table: int, stage: int) -> int:
        pointer = self._word(table + stage * 2)
        return sum(1 for other in range(19) if self._word(table + other * 2) == pointer)

    def treasures(self, stage: int, floor: int) -> list:
        """Hidden treasure of a stage floor. x is in stage pixels like the other objects; y is where Simon stands."""
        address, out = self._word(0xFC14 + stage * 2), []
        for number in range(16):
            first = self._b6(address)
            if first == 0xFF:
                break
            b1, b3 = self._b6(address + 1), self._b6(address + 3)
            if first & 1 == floor:
                out.append({'kind': 'treasure', 'number': number, 'x': ((b1 & 0x07) << 8 | (b1 & 0xF8)) + self.ZONE + 1,
                            'y': first & 0xF0, 'treasure': b3, 'trigger': (first >> 1) & 3, 'second_quest': bool(first & 8),
                            'name': 'Hidden ' + self.TREASURES.get(b3, f'treasure {b3:#04x}').lower(),
                            'how': self.TRIGGERS[(first >> 1) & 3], 'byte': self._offset6(address),
                            'shared': self._list_users(0xFC14, stage)})
            address += 4
        return out

    def block_items(self) -> list:
        """What a breakable block can hold: its 3-bit number picks an item code from the table at $AA4F."""
        return [self._b6(0xAA4F + n) for n in range(8)]

    def block_item_name(self, number: int) -> str:
        return 'Nothing' if number == 0 else self.drop_name(self.block_items()[number])

    def blocks(self, stage: int, floor: int) -> list:
        """Breakable blocks that hold something ($A825, bank 6): 2 bytes each, table $FC4D by stage, 0 ends it."""
        address, out = self._word(0xFC4D + stage * 2), []
        for number in range(16):
            b0 = self._b6(address)
            if b0 == 0:
                break
            b1 = self._b6(address + 1)
            if (b0 >> 3) & 1 == floor:
                item = b0 & 7
                out.append({'kind': 'block', 'number': number, 'x': ((b1 & 0x07) << 8 | (b1 & 0xF0)) + 8 + self.ZONE + 1,
                            'y': (b0 & 0xF0) + 16, 'item': item, 'second_quest': bool(b1 & 8),
                            'name': 'Breakable block', 'drop_name': self.block_item_name(item),
                            'byte': self._offset6(address), 'shared': self._list_users(0xFC4D, stage)})
            address += 2
        return out

    def secret_writes(self, kind: str, stage: int, floor: int, number: int, item=None, treasure=None, trigger=None) -> list:
        """[(offset, old, new)] for a change to one secret."""
        rows = self.blocks(stage, floor) if kind == 'block' else self.treasures(stage, floor)
        row = next((r for r in rows if r['number'] == int(number)), None)
        if row is None:
            raise ValueError('That secret is not part of this stage.')
        writes = []
        if kind == 'block' and item is not None:
            if not 0 <= int(item) <= 7:
                raise ValueError('Choose one of the items a block can hold.')
            old = self.rom[row['byte']]
            writes.append((row['byte'], old, (old & 0xF8) | int(item)))
        if kind == 'treasure':
            if treasure is not None:
                if int(treasure) not in self.TREASURES:
                    raise ValueError('Choose one of the game\u2019s treasures.')
                writes.append((row['byte'] + 3, self.rom[row['byte'] + 3], int(treasure)))
            if trigger is not None:
                if int(trigger) not in self.TRIGGERS:
                    raise ValueError('Choose how the treasure is found.')
                old = self.rom[row['byte']]
                writes.append((row['byte'], old, (old & ~0x06 & 0xFF) | int(trigger) << 1))
        return [w for w in writes if w[1] != w[2]]

    # ---- level length (layout bank 4; tables bank 7)
    # A stage floor is (pages + 1) screens of 256 pixels. Layout: master table $FAFF -> floor list (bank 4) -> pointer
    # (data - $18); 6 blocks of 32 pixels per column, 8 columns per screen. Scroll limit: $FB8C (high nibble floor 0, low
    # nibble floor 1). Zones: (pages + 1) * 4 + 2 entries. Things placed by world x that move with their screen: hidden
    # treasure, breakable blocks, stairs ($FBC8), the boss lock ($FC3A), the left limit ($FB9F) and the courtyard gate ($CF5B).
    BANK4 = 0x10000
    MAX_PAGES = 5           # the longest stage the game has: candle states ($0190 per zone) must stay below the stack
    ZONES_START, ZONES_END = 0xD2CD, 0xD6A1

    def _b4(self, address: int) -> int:
        return self.rom[HEADER_NES + self.BANK4 + (address - 0x8000)]

    def _offset4(self, address: int) -> int:
        return HEADER_NES + self.BANK4 + (address - 0x8000)

    def pages(self, stage: int, floor: int) -> int:
        limit = self._at(0xFB8C + stage)
        return limit >> 4 if floor == 0 else limit & 15

    def layout_word(self, stage: int, floor: int) -> int:
        """CPU address (bank 4) of the floor's layout pointer."""
        return self._word(0xFAFF + stage * 2) + floor * 2

    def layout(self, stage: int, floor: int) -> int:
        word = self.layout_word(stage, floor)
        return (self._b4(word) | self._b4(word + 1) << 8) + 0x18

    def zone_word(self, stage: int, floor: int) -> int:
        return self._word(0xD26B + stage * 2) + floor * 2

    def _zone_tables(self) -> dict:
        """{table address: its bytes} for every zone table, each running to the next one."""
        need = {}
        for st in range(19):
            for fl in (0, 1):
                start = self.zone_table(st, fl)
                if not self.ZONES_START <= start < self.ZONES_END:
                    raise ValueError('This copy of the game keeps its enemy tables somewhere ROMancer does not expect.')
                need[start] = max(need.get(start, 0), ((self.pages(st, fl) + 1) * 4 + 2) * 2)
        starts = sorted(need)
        ends = starts[1:] + [self.ZONES_END]
        # a table is what the game can read of it: to the next table, or further where a long stage reads on into the next
        return {start: bytes(self._at(start + i) for i in range(max(end - start, need[start])))
                for start, end in zip(starts, ends)}

    def screen_items(self, stage: int, floor: int) -> list:
        """[(offset of the byte that holds the page, low bits mask, current x, what)] for things placed by world x."""
        items = []
        for row in self.treasures(stage, floor):
            items.append((row['byte'] + 1, row['x'] - self.ZONE - 1, 'hidden treasure'))
        for row in self.blocks(stage, floor):
            items.append((row['byte'] + 1, row['x'] - self.ZONE - 1 - 8, 'breakable block'))
        address = self._word(0xFBC8 + stage * 2)
        for number in range(32):                    # stairs: 2 bytes, 0 ends the list; page is the low 3 bits of byte 1
            first = self._b6(address) if address < 0xC000 else self._at(address)
            if first == 0:
                break
            if (first >> 2) & 1 == floor:
                where = address + 1
                value = self._b6(where) if where < 0xC000 else self._at(where)
                offset = self._offset6(where) if where < 0xC000 else self.offset(where)
                items.append((offset, (value & 7) << 8 | (value & 0xF8), 'stairs'))
            address += 2
        return items

    def resize_writes(self, stage: int, floor: int, at: int, delta: int) -> dict:
        """Writes that remove `-delta` screens starting at screen `at`, or repeat screen `at` `delta` more times right after
        it, with everything placed in later screens moved along. Returns {'writes': [(offset, old, new)], 'pages': new pages,
        'notes': [...]}."""
        stage, floor, at, delta = int(stage), int(floor), int(at), int(delta)
        pages = self.pages(stage, floor)
        new_pages = pages + delta
        if not 0 <= at <= pages:
            raise ValueError('That screen is not part of this stage.')
        if delta == 0:
            raise ValueError('Choose how many screens to add or remove.')
        if delta < 0 and (at - delta > pages or at == 0):
            raise ValueError('The first and the last screen hold the way in and the way out, so they stay. Choose a screen in between.')
        if not 0 <= new_pages <= self.MAX_PAGES:
            raise ValueError(f'A stage can be 1 to {self.MAX_PAGES + 1} screens long here (the longest the game has).')
        writes, notes = {}, []

        def put(offset, value):
            writes[offset] = value & 0xFF

        # which screens move: removing [at, at - delta) moves later screens left; repeating `at` moves later ones right
        boundary = (at - delta if delta < 0 else at + 1) * 256
        removed = range(at * 256, (at - delta) * 256) if delta < 0 else range(0)
        for offset, x, what in self.screen_items(stage, floor):
            if x in removed:
                if what == 'stairs':
                    raise ValueError('That screen has stairs the level needs, so it cannot be removed. Choose another screen.')
                put(offset, (self.rom[offset] & 0xF8) | 7)          # out of reach: past the end of any stage
                notes.append(f'The {what} on a removed screen can no longer be reached.')
            elif x >= boundary:
                page = ((self.rom[offset] & 7) + delta)
                if not 0 <= page <= 7:
                    raise ValueError('Something in this stage would move past where the game can place it.')
                put(offset, (self.rom[offset] & 0xF8) | page)

        def shift_page(offset, low_nibble_page):            # a page number in a nibble, moved if it is past the boundary
            value = self.rom[offset]
            page = value & 15 if low_nibble_page else value >> 4
            if page != 15 and page * 256 >= boundary:
                page += delta
                put(offset, (value & 0xF0 | page) if low_nibble_page else (page << 4 | value & 15))
        lock = self._at(0xFC3A + stage)
        if lock != 0xFF and lock >> 4 == floor:
            shift_page(self.offset(0xFC3A + stage), True)
        left = self._at(0xFB9F + stage)
        if left != 0xFF:
            shift_page(self.offset(0xFB9F + stage), floor != 0)
        gates = {0: 0xCF5B, 0x10: 0xCF5E}
        if stage in gates and floor == 0:
            page_at = self.offset(gates[stage] + 2)
            if self.rom[page_at] * 256 + self.rom[page_at - 1] >= boundary:
                put(page_at, self.rom[page_at] + delta)

        # scroll limit
        limit = self.offset(0xFB8C + stage)
        value = self.rom[limit]
        put(limit, (new_pages << 4 | value & 15) if floor == 0 else (value & 0xF0 | new_pages))

        # layout: columns of 6 bytes, 8 columns a screen
        data = self.layout(stage, floor)
        columns = [bytes(self._b4(data + 6 * c + r) for r in range(6)) for c in range((pages + 1) * 8)]
        if delta < 0:
            new = columns[:at * 8] + columns[(at - delta) * 8:]
            new += columns[-8:] * (-delta)                   # what the game reads past the end stays a copy of the last screen
            for i, byte in enumerate(b''.join(new)):
                put(self._offset4(data) + i, byte)
        else:
            new = columns[:(at + 1) * 8] + columns[at * 8:(at + 1) * 8] * delta + columns[(at + 1) * 8:]
            before = bytes(self._b4(data - 0x18 + i) for i in range(0x18))
            after = bytes(self._b4(data + len(columns) * 6 + i) for i in range(48))
            block = before + b''.join(new) + after
            start = self._free4(len(block))
            for i, byte in enumerate(block):
                put(self._offset4(start) + i, byte)
            word = self._offset4(self.layout_word(stage, floor))
            put(word, start & 0xFF)
            put(word + 1, start >> 8)

        # zones: 4 a screen, then 2 read ahead of the end
        table = self.zone_table(stage, floor)
        count = (pages + 1) * 4 + 2
        zones = [bytes(self._at(table + 2 * i + k) for k in range(2)) for i in range(count)]
        if delta < 0:
            new_zones = zones[:at * 4] + zones[(at - delta) * 4:]
            new_zones += [b'\0\0'] * (count - len(new_zones))
            for i, pair in enumerate(new_zones):
                put(self.offset(table) + 2 * i, pair[0])
                put(self.offset(table) + 2 * i + 1, pair[1])
        else:
            new_zones = zones[:(at + 1) * 4] + zones[at * 4:(at + 1) * 4] * delta + zones[(at + 1) * 4:]
            self._repack_zones(table, b''.join(new_zones), put)
        out = [(offset, self.rom[offset], value) for offset, value in sorted(writes.items()) if self.rom[offset] != value]
        return {'writes': out, 'pages': new_pages, 'notes': notes}

    def _free4(self, size: int) -> int:
        """Start of the unused space at the end of bank 4 ($B408 onward, all $FF) that fits `size` bytes."""
        start = 0xB408
        if any(self._b4(start + i) != 0xFF for i in range(size)) or start + size > 0xC000:
            raise ValueError('There is no room left in the game for a longer layout.')
        return start

    def _repack_zones(self, table: int, grown: bytes, put) -> None:
        """Lay every zone table out again in the same space, sharing bytes where tables overlap, so a grown table fits.
        Every other table keeps exactly its bytes; only the pointers to them change."""
        tables = self._zone_tables()
        tables[table] = grown
        order = sorted(tables, key=lambda start: -len(tables[start]))
        blob = b''
        where = {}
        for start in order:
            body = tables[start]
            found = next((i for i in range(0, len(blob) - len(body) + 1, 2) if blob[i:i + len(body)] == body), None)
            if found is None:
                overlap = next((k for k in range(min(len(blob), len(body)) // 2 * 2, 0, -2) if blob[-k:] == body[:k]), 0)
                found = len(blob) - overlap
                blob += body[overlap:]
            where[start] = found
        if len(blob) > self.ZONES_END - self.ZONES_START:
            raise ValueError('There is not enough room in the game for that many more screens.')
        for i, byte in enumerate(blob):
            put(self.offset(self.ZONES_START + i), byte)
        for stage in range(19):
            for floor in (0, 1):
                word = self.zone_word(stage, floor)
                new = self.ZONES_START + where[self.zone_table(stage, floor)]
                put(self.offset(word), new & 0xFF)
                put(self.offset(word + 1), new >> 8)

    def drop_name(self, drop: int) -> str:
        low = drop & 0x0F
        return self.DROPS.get(low, f'Item {low:#04x}')

    def enemy_name(self, kind: int) -> str:
        name = self.ENEMIES.get(kind)
        if name is None:
            return f'Enemy {kind:#04x}'
        return name + (' (likely)' if kind in self.UNSURE else '')

    def objects(self, stage: int, floor: int, count: int = 64) -> list:
        """Every enemy and candle of a stage, in stage pixels (x from the stage start, y on the screen)."""
        out = []
        for row in self.zones(stage, floor, count):
            base = row['zone'] * self.ZONE
            if row['enemy']:
                e = row['enemy']
                out.append({'kind': 'enemy', 'zone': row['zone'], 'type': e['type'], 'name': self.enemy_name(e['type']),
                            'x': base + e['dx'], 'y': e['y'], 'index': row['enemy_index'], 'byte': row['enemy_byte']})
            if row['candle']:
                c = row['candle']
                out.append({'kind': 'candle', 'zone': row['zone'], 'type': c['type'],
                            'name': 'Candle' if c['type'] == 0x28 else 'Wall candle', 'drop': c['drop'],
                            'drop_name': self.drop_name(c['drop']), 'x': base + c['dx'], 'y': c['y'],
                            'index': row['candle_index'], 'byte': row['candle_byte'],
                            'shared': self.candle_users(stage, floor, row['candle_index'], count)})
        return out + self.treasures(stage, floor) + self.blocks(stage, floor)

    def candle_users(self, stage: int, floor: int, index: int, count: int = 64) -> int:
        table = self.zone_table(stage, floor)
        return sum(1 for zone in range(count) if self._at(table + zone * 2 + 1) == index)

    def tile_role(self, tile: int) -> str:
        if tile in self.BREAKABLE:
            return 'breakable'
        if tile in self.SOLID:
            return 'solid'
        return 'open'

    # ---- choices for edits (all point a zone at an existing record, so nothing else moves)
    def drop_choices(self, stage: int, floor: int, zone: int, count: int = 64) -> list:
        """Other candle records at the same place in their zone with a different drop: [{'index', 'drop', 'name'}]."""
        here = self.zones(stage, floor, count)[zone]['candle']
        if here is None:
            return []
        found, seen = [], set()
        for index in range(256):
            try:
                other = self.candle_record(index)
            except IndexError:
                continue
            if other and other['type'] == here['type'] and (other['dx'], other['y']) == (here['dx'], here['y']) and other['drop'] not in seen:
                seen.add(other['drop'])
                found.append({'index': index, 'drop': other['drop'], 'name': self.drop_name(other['drop'])})
        return found

    def enemy_choices(self) -> list:
        """Enemy records the game has: [{'index', 'type', 'name', 'dx', 'y'}], one per type and place."""
        found, seen = [], set()
        for index in range(1, 128):
            try:
                record = self.enemy_record(index)
            except IndexError:
                break
            if record and (record['type'], record['dx'], record['y']) not in seen:
                seen.add((record['type'], record['dx'], record['y']))
                found.append({'index': index, **record, 'name': self.enemy_name(record['type'])})
        return found


PROFILES = [Castlevania]


def profile_for(rom: bytes):
    digest = hashlib.sha256(rom).hexdigest()
    for kind in PROFILES:
        if kind.sha256 == digest:
            return kind(rom)
    return None
