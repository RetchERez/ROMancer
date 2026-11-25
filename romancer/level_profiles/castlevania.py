"""What ROMancer knows about the levels of particular games: their enemies, items, secrets and what their blocks do.

A profile reads the game's own tables (worked out from the game's code and proven by replaying the game) and turns them
into things on a level map. Edits are exact ROM writes; ROMancer checks each one by replaying the game.

Only games with a profile get these; every other game keeps the general level map tools.
"""
from __future__ import annotations


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
    # spawner types, named by placing each record alone in a zone of a stage that uses it (the stage's own graphics,
    # reached by finishing the stage before it) and watching (trace/v15_profiles/naming_castlevania/names.png). Some
    # spawner handlers ($F3B9 jump table) depend on the stage; every name holds for the stages the game uses it in.
    # Bosses: the handlers that clear the screen and take the boss slot ($F469), each used once, in the last stage of a level.
    ENEMIES = {
        0x01: ('Zombies', 'Zombies come in from the side of the screen and walk along the floor.'),
        0x02: ('Bats', 'Bats fly in from the side of the screen in a wavy line.'),
        0x03: ('Fishmen', 'Fishmen leap out of the water and walk toward you.'),
        0x04: ('Bats (second quest only)', 'Only in the second quest: bats fly in from the side of the screen.'),
        0x05: ('Medusa heads (second quest only)', 'Only in the second quest: Medusa heads fly across the screen in a wavy line.'),
        0x06: ('Medusa heads', 'Medusa heads fly across the screen in a wavy line.'),
        0x0D: ('Ghost, from the left', 'A ghost comes in from the left side of the screen and floats toward you.'),
        0x8D: ('Ghost, from the right', 'A ghost comes in from the right side of the screen and floats toward you.'),
        0x12: ('Eagle', 'Flies across the top of the screen and drops fleamen.'),
        0x47: ('Bat, hanging', 'Hangs on the wall until you come near, then swoops at you.'),
        0x48: ('Zombie', 'Walks slowly along the floor.'),
        0x4A: ('Axe Knight', 'Stands guard and throws axes at you.'),
        0x4C: ('Fleaman', 'Hops about and leaps at you.'),
        0x4E: ('Bone pillar', 'A stack of dragon skulls that stays in place and spits fireballs.'),
        0x4F: ('Raven', 'Perches until you come near, then dives at you.'),
        0x50: ('Skeleton', 'Walks back and forth and throws bones in an arc.'),
        0x51: ('Panther', 'Crouches on a ledge and pounces when you come near.'),
        0x53: ('Red skeleton', 'Walks toward you along the floor.'),
        0x54: ('Bone dragon', 'A neck of bones that sways out from the wall; its head spits fireballs.'),
        0x58: ('Death (boss)', 'The boss at the end of stage 15.'),
        0x59: ('Phantom Bat (boss)', 'The boss at the end of stage 3; it hangs on the wall until the fight starts.'),
        0x5A: ('Mummies (boss)', 'The boss at the end of stage 9.'),
        0x5B: ('Medusa (boss)', 'The boss at the end of stage 6.'),
        0x5C: ("Frankenstein's monster and Igor (boss)", 'The boss at the end of stage 12.'),
        0x5D: ('Dracula (boss)', 'The last boss, at the end of stage 18.'),
        0x5E: ('Giant bat', 'A big red bat that flies about in wide swoops.'),
    }
    # enemy indexes from 69 on read candle records (both share the pool at $D6A1); no zone uses them as enemies, so
    # they are not offered
    NOT_ENEMIES = {0x20, 0xFE, 0xFF}
    # item codes, from the pickup code at $E73E (bank 7): 0 small heart (a weak whip gets the whip upgrade instead), 1 money
    # bag, 3 whip upgrade, 4 large heart, 5 pot roast, 6 magic crystal, A rosary, C double or triple shot, E invisibility
    # potion, and the rest set the subweapon (2 and 7 are numbers no subweapon uses)
    DROPS = {0x0: 'Heart or whip upgrade', 0x1: 'Money bag', 0x2: 'Blank subweapon (an unused code)', 0x3: 'Whip upgrade',
             0x4: 'Large heart', 0x5: 'Pot roast', 0x6: 'Magic crystal (ends the stage)', 0x7: 'Blank subweapon (a second unused code)',
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
        if kind in self.ENEMIES:
            return self.ENEMIES[kind][0]
        if kind in self.NOT_ENEMIES:
            return 'Not an enemy (candle data)'
        return f'Enemy {kind:#04x}'

    def enemy_does(self, kind: int):
        return self.ENEMIES[kind][1] if kind in self.ENEMIES else None

    def objects(self, stage: int, floor: int, count: int = 64) -> list:
        """Every enemy and candle of a stage, in stage pixels (x from the stage start, y on the screen)."""
        out = []
        for row in self.zones(stage, floor, count):
            base = row['zone'] * self.ZONE
            if row['enemy']:
                e = row['enemy']
                out.append({'kind': 'enemy', 'zone': row['zone'], 'type': e['type'], 'name': self.enemy_name(e['type']),
                            'does': self.enemy_does(e['type']),
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
            if record and record['type'] not in self.NOT_ENEMIES and (record['type'], record['dx'], record['y']) not in seen:
                seen.add((record['type'], record['dx'], record['y']))
                found.append({'index': index, **record, 'name': self.enemy_name(record['type'])})
        return found


from . import Profile, Watcher  # noqa: E402  (the package imports this module lazily)


def _band(y: int) -> str:
    if y < 80:
        return 'near the top'
    if y < 112:
        return 'high'
    if y < 144:
        return 'halfway up'
    if y < 176:
        return 'low'
    return 'near the floor'


def _side(dx: int) -> str:
    return 'to the left' if dx < 22 else ('in the middle' if dx < 43 else 'to the right')


def variant_names(choices: list) -> list:
    """[{'value', 'name'}] for enemy records [{'index', 'name', 'dx', 'y', ...}]: records that share a name get where
    they stand (height on the screen, then their place in their 64-pixel stretch), and a count when that is still the same."""
    groups = {}
    for c in choices:
        groups.setdefault(c['name'], []).append(c)
    names = {}
    for name, group in groups.items():
        if len(group) == 1:
            names[group[0]['index']] = name
            continue
        labels = {c['index']: _band(c['y']) for c in group}
        for c in group:
            if sum(1 for o in group if _band(o['y']) == _band(c['y'])) > 1:
                labels[c['index']] = f'{_band(c["y"])}, {_side(c["dx"])}'
        if name.startswith('Not an enemy'):
            for n, c in enumerate(group, 1):
                names[c['index']] = f'{name} {n}'
            continue
        clash = {}
        for c in group:
            clash.setdefault(labels[c['index']], []).append(c)
        for label, same in clash.items():
            same.sort(key=lambda c: (c['y'], c['dx'], c['index']))
            if len(same) == 1:
                names[same[0]['index']] = f'{name}, {label}'
            elif len(same) == 2 and same[0]['y'] != same[1]['y']:
                names[same[0]['index']] = f'{name}, {label}, a little higher'
                names[same[1]['index']] = f'{name}, {label}, a little lower'
            elif len(same) == 2 and same[0]['dx'] != same[1]['dx']:
                names[same[0]['index']] = f'{name}, {label}, a little to the left'
                names[same[1]['index']] = f'{name}, {label}, a little to the right'
            else:
                for n, c in enumerate(same, 1):
                    names[c['index']] = f'{name}, {label}' + (f' ({n})' if n > 1 else '')
    return [{'value': c['index'], 'name': names[c['index']]} for c in choices]


class _SlotWatcher(Watcher):
    """An enemy or candle edit: watch the zone's spawn slot from when the zone loads until the slot goes to zone + 6
    (the first six zones load at once when a stage starts). A new enemy or item counts once it shows; a removal counts
    only if nothing shows the whole time."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        record = watch['record']
        self.removing = record is None
        self.wanted = (record['type'] if record else 0) if watch['kind'] == 'enemy' else record

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x28] != w['stage'] or not w['zone'] <= ram[0x6D] < w['zone'] + 6:
            return False
        slot = w['zone'] % 6
        if w['kind'] == 'enemy':
            sample = {'type': ram[0x166 + slot]}
            hit = sample['type'] == self.wanted if not self.removing else sample['type'] != 0
        else:
            candle = 0x0E + slot
            sample = {'type': ram[0x434 + candle], 'drop': ram[0x584 + candle]}
            hit = (sample['type'] in (0x27, 0x28) and sample['drop'] == self.wanted['drop']) if not self.removing else sample['type'] in (0x27, 0x28)
        if self.seen is None or hit or (not self.removing and sample['type']):
            self.seen = sample
        return hit

    def result(self):
        seen, w = self.seen, self.w
        if seen is None:
            return super().result()
        if w['kind'] == 'enemy':
            wanted = self.wanted
            ok = seen['type'] == wanted
            return {'state': 'good' if ok else 'bad',
                    'text': ('Played from the start, the game now spawns ' + ('no enemy' if not wanted else w['name']) + ' there.') if ok
                    else f'Played from the start, the game spawned type {seen["type"]:#04x} there, not what was chosen.'}
        if self.removing:
            ok = seen['type'] == 0
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, there is no candle there any more.' if ok
                    else 'Played from the start, a candle still appears there.'}
        ok = seen['type'] in (0x27, 0x28) and seen['drop'] == self.wanted['drop']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the candle there now holds the item chosen ({w["name"]}).' if ok
                else f'Played from the start, the candle there holds item code {seen["drop"]:#04x}, not the one chosen.'}


class _SecretWatcher(Watcher):
    """A secret edit: watch the game's found-flags ($0144 treasure, $0146 blocks, one bit per secret), then what appeared."""
    every = 2

    def __init__(self, watch):
        self.w, self.seen, self.found_at = watch, None, None

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x28] != w['stage']:
            return False
        flags = ram[0x144] if w['kind'] == 'treasure' else ram[0x146]
        if not flags & (1 << w['number']):
            return False
        self.found_at = self.found_at or frame
        if w['kind'] == 'treasure':
            hits = [ram[0x568 + x] for x in range(0x17, 0x1C) if ram[0x434 + x] == 2]
        else:
            hits = [ram[0x584 + x] for x in range(0x03, 0x1C) if ram[0x434 + x] == 0x2F]
        if hits:
            self.seen = hits[0]
            return True
        return frame - self.found_at > 60

    def result(self):
        w = self.w
        if self.found_at is None:
            return {'state': 'warn', 'text': "The recorded walk doesn't find this secret, so the change couldn't be watched in the game. Use Play from here to try it yourself."}
        if w['kind'] == 'treasure':
            ok = self.seen == w['treasure']
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, the secret is found and the chosen treasure appears.' if ok
                    else 'Played from the start, the secret is found but a different treasure appears.'}
        ok = (self.seen is None) if w['drop'] is None else self.seen == w['drop']
        return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, the block breaks and gives the chosen item.' if ok
                else 'Played from the start, the block breaks but gives something else.'}


class _LengthWatcher(Watcher):
    """A length change: how far the part scrolls on the old and the new game, and when the next part starts."""
    compare = True

    def __init__(self, watch):
        self.w = watch
        self.runs = {}

    def see(self, ram, frame, run):
        w = self.w
        state = self.runs.setdefault(run, {'far': 0, 'left': None, 'been': False})
        camera = ram[0x2E] | ram[0x2F] << 8
        if ram[0x28] == w['stage'] and ram[0x46] == w['floor'] and camera < 0x8000:
            state['been'] = state['been'] or camera > 0       # really played (the attract mode shows stages too)
            if state['been']:
                state['far'] = max(state['far'], camera)
        elif state['been'] and ram[0x28] == w['stage'] + 1:
            state['left'] = frame
            return True
        return False

    def result(self):
        w = self.w
        old = self.runs.get('original', {'far': 0, 'left': None})
        new = self.runs.get('changed', {'far': 0, 'left': None})
        wanted = w['new'] * 256

        def screens(far):
            return far // 256 + 1
        if new['far'] == wanted:
            text = f'Played from the start, this part now scrolls through {screens(new["far"])} screens (it was {screens(old["far"])}).'
            if old['left'] and new['left']:
                seconds = round(abs(new['left'] - old['left']) / 60, 1)
                text += f' The next part starts {seconds} seconds {"later" if new["left"] > old["left"] else "earlier"}.'
            out = {'state': 'good', 'text': text}
        elif new['far'] < wanted and w['new'] > w['old'] and new['far'] >= old['far']:
            out = {'state': 'warn', 'text': "The recorded walk doesn't reach the end of this part, so the new length couldn't be watched to the end "
                                            f"(it got {screens(new['far'])} screens in). Use Play from here to walk it."}
        else:
            out = {'state': 'bad', 'text': f'Played from the start, this part scrolls through {screens(new["far"])} screens, not the {w["new"] + 1} chosen.'}
        if w['notes']:
            out['text'] += ' ' + ' '.join(sorted(set(w['notes'])))
        return out


class CastlevaniaProfile(Castlevania, Profile):
    """Castlevania on the common profile interface. Parts are {'stage', 'floor'}; x is the camera's world pixels."""
    sha256s = (Castlevania.sha256,)
    SPAWN = Castlevania.ZONE + 1        # a zone record's x is drawn this far right of the same world x

    def where(self, ram):
        camera = ram[0x2E] | ram[0x2F] << 8
        return {'part': {'stage': ram[0x28], 'floor': ram[0x46]}, 'x': camera, 'y': 0}

    def part_name(self, part):
        return f'Stage part {part["stage"] + 1}' + (', lower floor' if part['floor'] else '')

    def choices(self):
        return {'enemies': variant_names(self.enemy_choices()),
                'block_items': [{'value': n, 'name': self.block_item_name(n)} for n in range(8)],
                'treasures': [{'value': k, 'name': v} for k, v in self.TREASURES.items()],
                'triggers': [{'value': k, 'name': v} for k, v in self.TRIGGERS.items()]}

    def objects(self, part, floor=None, count=64):
        if not isinstance(part, dict):                      # the old call: objects(stage, floor, count)
            return Castlevania.objects(self, part, floor, count)
        stage, floor = int(part['stage']), int(part['floor'])
        count = (self.pages(stage, floor) + 1) * 4 + 2
        out = []
        for item in Castlevania.objects(self, stage, floor, count):
            row = dict(item)
            if item['kind'] == 'enemy':
                row.update(id=f'enemy:{item["zone"]}', style='enemy', x=item['x'] - self.SPAWN, remove='Remove this enemy',
                           fields=[{'key': 'record', 'label': 'Swap for', 'value': item['index'], 'choices': 'enemies'}])
            elif item['kind'] == 'candle':
                choices = [{'value': c['index'], 'name': c['name'] + (f' (colour {c["drop"] >> 4})' if c['drop'] & 0xF0 and (c['drop'] & 15) == 1 else '')}
                           for c in self.drop_choices(stage, floor, item['zone'], count)]
                row.update(id=f'candle:{item["zone"]}', style='item', x=item['x'] - self.SPAWN, detail=f'drops {item["drop_name"]}',
                           remove='Remove this candle', fields=[{'key': 'record', 'label': 'Drops', 'value': item['index'], 'choices': choices}])
                if item['shared'] > 1:
                    others = item['shared'] - 1
                    row['note'] = (f'This candle shares its settings with {others} other {"candle" if others == 1 else "candles"} in this stage, '
                                   'so a new item is given to this one alone by pointing it at another of the game’s candles at the same spot.')
            elif item['kind'] == 'treasure':
                row.update(id=f'treasure:{item["number"]}', style='secret', x=item['x'] - self.SPAWN, detail=item['how'].lower(), remove=None,
                           fields=[{'key': 'treasure', 'label': 'Treasure', 'value': item['treasure'], 'choices': 'treasures'},
                                   {'key': 'trigger', 'label': 'Found by', 'value': item['trigger'], 'choices': 'triggers'}])
            else:
                row.update(id=f'block:{item["number"]}', style='block', x=item['x'] - self.SPAWN, name='Breakable block',
                           detail=f'{item["drop_name"].lower()} inside' if item['item'] else 'empty', remove=None,
                           fields=[{'key': 'item', 'label': 'Inside', 'value': item['item'], 'choices': 'block_items'}])
            notes = []
            if item.get('second_quest'):
                notes.append('Only in the second quest (the harder game after the ending).')
            if item['kind'] in ('treasure', 'block') and item['shared'] > 1:
                notes.append(f'This list is shared with {item["shared"] - 1} other stages, so the change shows there too.')
            if notes:
                row['note'] = ' '.join(([row['note']] if row.get('note') else []) + notes)
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        stage, floor = int(part['stage']), int(part['floor'])
        kind, _, number = object_id.partition(':')
        number = int(number)
        if kind in ('enemy', 'candle'):
            row = self.zones(stage, floor)[number]
            offset = row['enemy_byte' if kind == 'enemy' else 'candle_byte']
            index = 0 if remove else int(values.get('record'))
            if not 0 <= index <= 255:
                raise ValueError('That choice is not one of the game’s own.')
            if kind == 'enemy':
                record = self.enemy_record(index)
                name = 'no enemy' if record is None else self.enemy_name(record['type'])
                title = 'Remove the enemy' if record is None else f'Enemy here: {name}'
            else:
                record = self.candle_record(index)
                name = '' if record is None else self.drop_name(record['drop'])
                title = 'Remove the candle' if record is None else f'Candle drops: {name}'
            writes = [(offset, self.rom[offset], index)] if self.rom[offset] != index else []
            return {'writes': writes, 'title': f'{title} (zone {number + 1})',
                    'watch': {'kind': kind, 'zone': number, 'record': record, 'stage': stage, 'name': name}}
        if kind == 'block':
            item = int(values.get('item'))
            return {'writes': Castlevania.secret_writes(self, 'block', stage, floor, number, item=item),
                    'title': f'Breakable block holds: {self.block_item_name(item)}',
                    'watch': {'kind': 'block', 'number': number, 'stage': stage, 'drop': None if item == 0 else self.block_items()[item]}}
        if kind == 'treasure':
            row = next(r for r in self.treasures(stage, floor) if r['number'] == number)
            treasure = int(values['treasure']) if values.get('treasure') is not None else None
            trigger = int(values['trigger']) if values.get('trigger') is not None else None
            shown = row['treasure'] if treasure is None else treasure
            how = row['trigger'] if trigger is None else trigger
            return {'writes': Castlevania.secret_writes(self, 'treasure', stage, floor, number, treasure=treasure, trigger=trigger),
                    'title': f'Hidden treasure: {self.TREASURES[shown]}, {self.TRIGGERS[how].lower()}',
                    'watch': {'kind': 'treasure', 'number': number, 'stage': stage, 'treasure': shown}}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        if watch['kind'] in ('enemy', 'candle'):
            return _SlotWatcher(watch)
        if watch['kind'] in ('block', 'treasure'):
            return _SecretWatcher(watch)
        return _LengthWatcher(watch)

    def screens(self, part):
        return {'count': self.pages(int(part['stage']), int(part['floor'])) + 1, 'most': self.MAX_PAGES + 1}

    def resize(self, part, at, delta):
        stage, floor = int(part['stage']), int(part['floor'])
        old = self.pages(stage, floor)
        result = self.resize_writes(stage, floor, at, delta)
        return {'writes': result['writes'], 'notes': result['notes'],
                'watch': {'kind': 'length', 'stage': stage, 'floor': floor, 'old': old, 'new': result['pages'], 'notes': result['notes']}}


PROFILES = [CastlevaniaProfile]


def profile_for(rom: bytes):
    from . import profile_for as find
    return find(rom)
