"""Castlevania III - Dracula's Curse (USA) and Castlevania II - Simon's Quest (USA) level profiles.

Both are decoded from the games' own code and proven by replaying the game with a changed ROM; the research notes are
research/castlevania23-level-profile.md. Castlevania III keeps Castlevania's idea of 64-pixel zones with an enemy byte
and a candle byte each, but its own tables, banks, record layouts and RAM; nothing is shared with castlevania.py.
"""
from __future__ import annotations

from . import Profile, Watcher
from .castlevania import variant_names

HEADER_NES = 16


# ============================================================================================ Castlevania III


class Castlevania3:
    """Castlevania III - Dracula's Curse (USA), MMC5. Spawn code: ROM 0x28000 run at CPU $8000 (16 KB at $8000-$BFFF,
    set by `LDA #$94; JSR $E2E6` before every call). Zone tables: $937F. Item drop: $A2E2 in ROM 0x2E000.

    A part of the game is a block ($32), its sub-block ($33) and a room ($34). Rooms that scroll sideways are cut into
    64-pixel zones; each zone has an enemy byte and a candle byte that pick records from shared pools (enemy records
    at $A03F, or $A13F for indexes of $80 and up; candle records at $A644 / $A744). Rooms that scroll up and down keep a
    list of 7-byte records instead (page, y, type, x, item or nothing, two settings), ended by $FF.
    """
    name = 'Castlevania III'
    sha256 = '085ec6395681c7ebfda19c2986069c21a3d27738cc61ada76249de70a07ed7d3'
    SPAWN_BANK = 0x28000            # ROM offset (no header) of CPU $8000 while objects are placed
    FIXED_C, FIXED_E = 0x3C000, 0x3E000
    ZONE = 64
    BLOCKS = 15
    # candle drop bytes are the item's object type; names from picking each one up in the game (research notes)
    ITEMS = {0x93: 'Axe', 0x94: 'Cross', 0x95: 'Dagger', 0x96: 'Holy water', 0x97: 'Stopwatch',
             0xA1: 'Invisibility potion', 0xA2: 'Rosary', 0xA3: 'Money bag (100)', 0xA4: 'Money bag (200)',
             0xA5: 'Money bag (400)', 0xA6: 'Money bag (700)', 0xA7: 'Money bag (1000)', 0xA8: 'Money bag (2000)',
             0xA9: 'Money bag (4000)', 0xAA: 'Money bag (7000)', 0xAB: 'Money bag (10000)', 0xAC: 'Extra life',
             0xAD: 'Large heart', 0xAE: 'Small heart or whip upgrade', 0xAF: 'Double shot', 0xB0: 'Triple shot'}
    SUBWEAPONS = range(0x93, 0x98)  # the game swaps these for the partner's own item when a partner is chosen ($A30B)
    CANDLES = {0x90: 'Candle', 0x91: 'Fire bowl', 0x92: 'Candle (0x92)'}
    # spawner types: (name, what it does), named by putting each record alone in a zone of a room that uses it (ROM
    # copy), sending the game there and watching (trace/v15_profiles/naming_castlevania/names.png). Types that showed
    # nothing there (bosses, or ones that wait for something the scripted visit never did) keep their numbers.
    ENEMIES = {
        0x01: ('Zombies', 'Zombies rise and walk toward you along the floor.'),
        0x02: ('Zombie', 'Walks toward you along the floor.'),
        0x03: ('Medusa heads', 'Medusa heads fly across the screen in a wavy line.'),
        0x04: ('Winged demon', 'A winged demon with a shield that flies down from above.'),
        0x05: ('Sword skeleton', 'Rises out of the ground and comes at you with a sword and shield.'),
        0x07: ('Hunchbacked ape', 'Crouches on top of a pillar.'),
        0x08: ('Red skeleton', 'Walks toward you along the floor.'),
        0x0B: ('Fleaman', 'Hops about and leaps at you.'),
        0x0C: ('Bat', 'Flies low toward you.'),
        0x0D: ('Bat, hanging', 'Hangs still until you come near.'),
        0x0E: ('Bone pillar', 'A stack of skulls that stays in place and spits fireballs.'),
        0x0F: ('Axe Knight', 'Walks toward you and throws axes.'),
        0x11: ('Fishman', 'Stands at the water and waits.'),
        0x12: ('Fishman', 'Stands on a ledge by the water.'),
        0x13: ('Chain skeleton', 'Swings a long chain whip at you.'),
        0x14: ('Floating eye', 'A red eye that hovers in the air.'),
        0x15: ('Green slime', 'Hops along the floor.'),
        0x16: ('Bone-throwing skeleton', 'Throws bones at you in an arc.'),
        0x17: ('Bone whip skeleton', 'Walks toward you swinging a curved bone.'),
        0x18: ('Ghost', 'Floats toward you.'),
        0x19: ('Red skeleton', 'Walks toward you along the floor.'),
        0x1B: ('Spider, hanging', 'Hangs still under a ledge.'),
        0x1D: ('Bat, hanging', 'Hangs still until you come near.'),
        0x20: ("Will-o'-the-wisp", 'A blue flame with a face that floats in place and flickers.'),
        0x23: ('Death', 'The Grim Reaper; he floats about swinging his scythe.'),
        0x24: ('Purple ghoul', 'Walks slowly along the floor.'),
        0x25: ("Will-o'-the-wisp", 'A blue flame with a face that grows and shrinks in place.'),
        0x26: ('Swinging pendulum', 'A clock pendulum that swings back and forth.'),
        0x27: ('Raven', 'Perches, then flies down at you.'),
        0x28: ('Hooded spearman', 'A hooded figure that stands guard with a spear.'),
        0x29: ('Spider', 'Lowers itself on a thread and climbs back up.'),
        0x2D: ('Red mushroom creature', 'Stands rooted to the floor.'),
        0x2E: ('Red hopping blob', 'Hops toward you.'),
        0x32: ('Bone-throwing skeleton', 'Throws bones at you in an arc.'),
        0x3A: ('Zombies', 'A crowd of zombies that walks toward you along the floor.'),
        0x3B: ('Mud men', 'Mud men rise out of the floor and shamble toward you.'),
        0x3C: ('Red crawler', 'Crouches on the floor.'),
        0x3D: ('Fishman, leaps from the water', 'Leaps out of the water and lands near you.'),
        0x3F: ('Flame man', 'A man made of fire that stands burning.'),
        0x40: ('Armored knight', 'Walks slowly toward you.'),
        0x41: ('Bone pillar', 'A stack of skulls on the wall that spits fireballs.'),
        0x43: ('Flock of bats', 'A flock of bats that takes off and flies at you.'),
        0x44: ('Owl', 'Swoops down from the trees and perches.'),
        0x45: ('Spiked ball', 'Rolls and bounces along.'),
        0x46: ('Harpy', 'Flies overhead and drops a fleaman.'),
        0x47: ('Bat', 'Flies toward you in a wavy line.'),
        0x4A: ('Medusa head', 'Flies at you in a wavy line.'),
        0x4B: ('Ghost', 'Drips from the ceiling, then floats toward you as a ghost.'),
        0x4F: ('Zombies', 'A crowd of zombies that walks toward you along the floor.'),
        0x51: ('Fishman', 'Stands on a ledge by the water.'),
        0x52: ('Winged demon', 'A winged demon with a shield that flies down from above.'),
    }
    # Stage objects (breakable blocks, moving platforms and the like): placed by $9D17 / $9EA5, code and tables in the
    # 16 KB bank at ROM 0x8000 run at CPU $8000. Room list: byte at word(word($A073 + block * 2) + sub * 2) + room, 0
    # none, else the list at word($A199 + index * 2): 8-byte records ended by $FF.
    OBJECT_BANK = 0x8000
    BLOCK_SIDEWAYS, BLOCK_UPDOWN = 0x10, 0x11       # record kinds of breakable blocks (jump table $A04F: $9CC0, $9CA4)
    # what a block holds ($078B; sprite table $B077, picked up at $B2EE). Measured by breaking the block of 1-03 with
    # each code (bitems.py): 0 health +32, 1 hearts +5, 2 nothing drops, 3 double shot ($87 = 1; triple shot when it is
    # already double), 4 lives +1, 5 triple shot ($87 = 2). 3 and 5 give a large heart instead with no subweapon or the
    # stopwatch ($B083, $B348).
    BLOCK_ITEMS = {0: 'Pot roast', 1: 'Large heart', 2: 'Nothing', 3: 'Double shot', 4: 'Extra life', 5: 'Triple shot'}
    BLOCK_SLOTS = (0x1A, 0x1B)

    def __init__(self, rom: bytes):
        self.rom = rom

    # ---- reading
    def offset(self, address: int) -> int:
        """ROM file offset of a CPU address as the spawn code sees it."""
        if address < 0x8000:
            raise ValueError('That address is not in the cartridge.')
        if address < 0xC000:
            return HEADER_NES + self.SPAWN_BANK + address - 0x8000
        if address < 0xE000:
            return HEADER_NES + self.FIXED_C + address - 0xC000
        return HEADER_NES + self.FIXED_E + address - 0xE000

    def _at(self, address: int) -> int:
        return self.rom[self.offset(address)]

    def _word(self, address: int) -> int:
        return self._at(address) | self._at(address + 1) << 8

    def _level_bank(self, block: int, sub: int = None, room: int = None) -> int:
        """ROM offset of the 16 KB bank that holds a block's room lists, or with sub and room, a room's layout ($C905:
        table $C94B, with four rooms that borrow another block's bank)."""
        index = block
        if sub is None:
            pass
        elif block == 13 and ((sub == 0 and room in (0, 1))):
            index = 2
        elif block == 13 and ((sub == 2 and room == 2) or (sub == 3 and room == 0)):
            index = 5
        elif block == 14 and sub == 0 and room == 1:
            index = 1
        return (self._at(0xC94B + index) & 0x7E) * 0x2000

    def _level(self, bank: int, address: int) -> int:
        return self.rom[HEADER_NES + bank + address - 0x8000]

    def subs(self, block: int) -> int:
        """Sub-blocks of a block: the gap to the next list in the table at $937F."""
        lists = [self._word(0x937F + 2 * b) for b in range(self.BLOCKS)]
        here = lists[block]
        # the next block's list, or where the room lists start (they follow the block lists)
        ends = [x for x in lists + [self._word(x) for x in lists] if x > here]
        return (min(ends) - here) // 2

    def rooms(self, block: int, sub: int) -> int:
        bank = self._level_bank(block)
        lists = self._word(0xD5D4 + 2 * block)
        room_list = self._level(bank, lists + 2 * sub) | self._level(bank, lists + 2 * sub + 1) << 8
        return self._level(bank, room_list) + 1

    def pages(self, block: int, sub: int, room: int) -> int:
        """Last page of a room ($D093: first byte of the room's layout, kept in $71)."""
        bank = self._level_bank(block)
        lists = self._word(0xD5D4 + 2 * block)
        room_list = self._level(bank, lists + 2 * sub) | self._level(bank, lists + 2 * sub + 1) << 8
        at = room_list + 1 + 2 * room
        data = self._level(bank, at) | self._level(bank, at + 1) << 8
        return self._level(self._level_bank(block, sub, room), data)

    def vertical(self, block: int, sub: int, room: int) -> bool:
        """Rooms that scroll up and down: bit 7 of the byte the game keeps in $68 ($D06E, table $D62E)."""
        return bool(self._at(self._word(self._word(0xD62E + 2 * block) + 2 * sub) + room) & 0x80)

    def zone_table(self, block: int, sub: int, room: int) -> int:
        return self._word(self._word(self._word(0x937F + 2 * block) + 2 * sub) + 2 * room)

    def zone_count(self, block: int, sub: int, room: int) -> int:
        return (self.pages(block, sub, room) + 1) * 4 + 2

    def enemy_address(self, index: int, hard: bool = False):
        """Record address for an enemy byte ($80FC): None for no enemy or one only the harder mode ($07F6) has."""
        if not index:
            return None
        doubled = (index << 1) & 0xFF
        if index & 0x80 and doubled >= 0xA0 and not hard:
            doubled = 0
            table = 0xA03F
        else:
            table = 0xA13F if index & 0x80 else 0xA03F
        return self._word(table + doubled)

    def enemy_record(self, index: int, hard: bool = False):
        address = self.enemy_address(index, hard)
        if address is None or not 0x8000 <= address < 0xBFFB or not self._at(address):
            return None
        return {'type': self._at(address), 'dx': self._at(address + 1), 'y': self._at(address + 2),
                'p1': self._at(address + 3), 'p2': self._at(address + 4), 'record': address}

    @staticmethod
    def hard_only(index: int) -> bool:
        return bool(index & 0x80) and ((index << 1) & 0xFF) >= 0xA0

    def candle_address(self, index: int):
        if not index:
            return None
        return self._word((0xA744 if index & 0x80 else 0xA644) + ((index << 1) & 0xFF))

    def candle_record(self, index: int):
        address = self.candle_address(index)
        if address is None or not 0x8000 <= address < 0xBFFC:
            return None
        return {'type': self._at(address), 'drop': self._at(address + 1), 'dx': self._at(address + 2),
                'y': self._at(address + 3), 'record': address}

    def all_rooms(self) -> list:
        out = []
        for block in range(self.BLOCKS):
            for sub in range(self.subs(block)):
                for room in range(self.rooms(block, sub)):
                    out.append((block, sub, room))
        return out

    def candle_users(self, address: int) -> int:
        """How many zones in the whole game use this candle record."""
        if not hasattr(self, '_users'):
            users = {}
            for block, sub, room in self.all_rooms():
                if self.vertical(block, sub, room):
                    continue
                table = self.zone_table(block, sub, room)
                seen = set()
                for zone in range(self.zone_count(block, sub, room)):
                    spot = table + 2 * zone + 1
                    if spot in seen:
                        continue
                    seen.add(spot)
                    record = self.candle_address(self._at(spot))
                    if record is not None:
                        users.setdefault(record, set()).add(spot)
            self._users = {k: len(v) for k, v in users.items()}
        return self._users.get(address, 0)

    def zones(self, block: int, sub: int, room: int) -> list:
        table = self.zone_table(block, sub, room)
        out = []
        for zone in range(self.zone_count(block, sub, room)):
            e, c = self._at(table + 2 * zone), self._at(table + 2 * zone + 1)
            out.append({'zone': zone, 'enemy_index': e, 'candle_index': c,
                        'enemy_byte': self.offset(table + 2 * zone), 'candle_byte': self.offset(table + 2 * zone + 1),
                        'enemy': self.enemy_record(e), 'hard_enemy': self.enemy_record(e, True) if self.hard_only(e) else None,
                        'candle': self.candle_record(c)})
        return out

    def vertical_records(self, block: int, sub: int, room: int) -> list:
        """Records of a room that scrolls up and down ($81F8): page, y, type (bit 7: candle), x, item, two settings."""
        address, out = self.zone_table(block, sub, room), []
        for number in range(64):
            if self._at(address) == 0xFF:
                break
            raw = [self._at(address + i) for i in range(7)]
            out.append({'number': number, 'page': raw[0], 'ry': raw[1], 'type': raw[2], 'x': raw[3], 'drop': raw[4],
                        'p1': raw[5], 'p2': raw[6], 'byte': self.offset(address), 'candle': bool(raw[2] & 0x80)})
            address += 7
        return out

    # ---- stage objects: breakable blocks
    def _obj_offset(self, address: int) -> int:
        """ROM file offset of a CPU address as the stage object code sees it (bank 0x8000 at $8000)."""
        if not 0x8000 <= address < 0xC000:
            return self.offset(address)
        return HEADER_NES + self.OBJECT_BANK + address - 0x8000

    def _obj_at(self, address: int) -> int:
        return self.rom[self._obj_offset(address)]

    def _obj_word(self, address: int) -> int:
        return self._obj_at(address) | self._obj_at(address + 1) << 8

    def object_list(self, block: int, sub: int, room: int):
        """(list number, CPU address) of a room's stage objects, or None."""
        subs = self._obj_word(0xA073 + 2 * block)
        if not 0x8000 <= subs < 0xC000:
            return None
        rooms = self._obj_word(subs + 2 * sub)
        if not 0x8000 <= rooms < 0xC000:
            return None
        index = self._obj_at(rooms + room)
        if not index:
            return None
        address = self._obj_word(0xA199 + 2 * index)
        return (index, address) if 0x8000 <= address < 0xC000 else None

    def blocks(self, block: int, sub: int, room: int) -> list:
        """Breakable blocks of a room. Record: position (page, then x in a sideways room or y in an up-and-down one),
        a size byte, kind ($10 sideways, $11 up and down), the other coordinate, the item ($078B), two blocks high
        ($0797, nonzero: one above the other, both must break) and the broken flag (`$F4` + this, set to $FF).
        Positions are in room pixels as the game keeps them; the object's middle. Checked by eye: the boxes drawn from
        them sit on the blocks of 1-03 (shots/brk3b_120_boxes.png)."""
        found = self.object_list(block, sub, room)
        if found is None:
            return []
        index, address = found
        out = []
        for number in range(40):
            if self._obj_at(address) == 0xFF:
                break
            raw = [self._obj_at(address + i) for i in range(8)]
            if raw[3] in (self.BLOCK_SIDEWAYS, self.BLOCK_UPDOWN):
                if raw[3] == self.BLOCK_SIDEWAYS:
                    x, y = raw[0] * 256 + raw[1], raw[4]
                else:
                    x, y = raw[4], raw[0] * 240 + raw[1] + 0x37
                out.append({'number': number, 'kind': raw[3], 'x': x, 'y': y, 'item': raw[5], 'double': bool(raw[6]),
                            'flag': raw[7], 'byte': self._obj_offset(address), 'list': index})
            address += 8
        return out

    def list_users(self, index: int) -> list:
        """Every (block, sub, room) whose stage object list is this one."""
        if not hasattr(self, '_list_users'):
            users = {}
            for place in self.all_rooms():
                found = self.object_list(*place)
                if found:
                    users.setdefault(found[0], []).append(place)
            self._list_users = users
        return self._list_users.get(index, [])

    def block_item_name(self, code: int) -> str:
        return self.BLOCK_ITEMS.get(code, f'Item {code}')

    # ---- names
    def item_name(self, code: int) -> str:
        return self.ITEMS.get(code, f'Item {code:#04x}')

    def enemy_name(self, kind: int) -> str:
        return self.ENEMIES[kind][0] if kind in self.ENEMIES else f'Enemy {kind:#04x}'

    def enemy_does(self, kind: int):
        return self.ENEMIES[kind][1] if kind in self.ENEMIES else None

    def block_label(self, block: int, sub: int) -> str:
        """The label the status bar shows ($8D96 in ROM bank 0: one string per block at $8DCF, the block's character
        then one character per sub-block; the bar puts a 0 between them)."""
        def char(tile):
            if 0x41 <= tile <= 0x4A:
                return str(tile - 0x41)
            if 0x50 <= tile <= 0x69:
                return chr(ord('A') + tile - 0x50)
            return '?'
        bank0 = lambda a: self.rom[HEADER_NES + a - 0x8000]
        pointer = bank0(0x8DCF + 2 * block) | bank0(0x8DD0 + 2 * block) << 8
        return f'{char(bank0(pointer))}-0{char(bank0(pointer + 1 + sub))}'

    def objects(self, block: int, sub: int, room: int) -> list:
        """Enemies and candles of a room in room pixels (x from the room's left edge, y from the top of the screen in
        rooms that scroll sideways; in rooms that scroll up and down y counts from the room's top in 240-pixel pages)."""
        out = []
        if self.vertical(block, sub, room):
            for rec in self.vertical_records(block, sub, room):
                y = rec['page'] * 240 + rec['ry'] + 0x37
                if rec['candle']:
                    out.append({'kind': 'vcandle', 'number': rec['number'], 'type': rec['type'], 'x': rec['x'], 'y': y,
                                'drop': rec['drop'], 'byte': rec['byte'], 'name': self.CANDLES.get(rec['type'], 'Candle')})
                elif rec['type']:
                    out.append({'kind': 'venemy', 'number': rec['number'], 'type': rec['type'], 'x': rec['x'], 'y': y,
                                'p1': rec['p1'], 'p2': rec['p2'], 'byte': rec['byte'], 'name': self.enemy_name(rec['type']),
                                'does': self.enemy_does(rec['type'])})
            return out + self._block_rows(block, sub, room)
        for row in self.zones(block, sub, room):
            base = row['zone'] * self.ZONE - self.ZONE
            enemy = row['enemy'] or row['hard_enemy']
            if enemy:
                out.append({'kind': 'enemy', 'zone': row['zone'], 'type': enemy['type'], 'name': self.enemy_name(enemy['type']),
                            'does': self.enemy_does(enemy['type']),
                            'x': base + enemy['dx'], 'y': enemy['y'], 'index': row['enemy_index'], 'byte': row['enemy_byte'],
                            'hard': row['enemy'] is None})
            if row['candle']:
                c = row['candle']
                out.append({'kind': 'candle', 'zone': row['zone'], 'type': c['type'], 'name': self.CANDLES.get(c['type'], 'Candle'),
                            'drop': c['drop'], 'x': base + c['dx'], 'y': c['y'], 'index': row['candle_index'],
                            'byte': row['candle_byte'], 'record': c['record'], 'shared': self.candle_users(c['record'])})
        return out + self._block_rows(block, sub, room)

    def _block_rows(self, block: int, sub: int, room: int) -> list:
        # the map wants the bottom middle: a block is 16 pixels square around its point, a double one 32 pixels high
        return [dict(b, kind='block', type=b['kind'], name='Breakable block', y=b['y'] + (8 if b['double'] else 0), middle=b['y'],
                     shared=len(self.list_users(b['list']))) for b in self.blocks(block, sub, room)]

    def enemy_choices(self) -> list:
        """One enemy record per type and place, from the pool the zone bytes point into (normal mode)."""
        found, seen = [], set()
        for index in range(1, 0xD0):
            record = self.enemy_record(index)
            if record:
                key = (record['type'], record['dx'], record['y'], record['p1'], record['p2'])
                if key not in seen:
                    seen.add(key)
                    found.append({'index': index, **record, 'name': self.enemy_name(record['type'])})
        return found

    def candle_alternatives(self, record: dict) -> list:
        """Other candle records of the same kind at the same spot in their zone with a different item."""
        found, seen = [], set()
        for index in range(1, 256):
            other = self.candle_record(index)
            if other and (other['type'], other['dx'], other['y']) == (record['type'], record['dx'], record['y']) and other['drop'] not in seen:
                seen.add(other['drop'])
                found.append({'index': index, 'drop': other['drop']})
        return found

    def drop_codes(self) -> list:
        """Every item byte the game's own candles use."""
        if hasattr(self, '_codes'):
            return self._codes
        codes = set()
        for index in range(1, 256):
            record = self.candle_record(index)
            if record and record['type'] in self.CANDLES:
                codes.add(record['drop'])
        for block, sub, room in self.all_rooms():
            if self.vertical(block, sub, room):
                codes.update(r['drop'] for r in self.vertical_records(block, sub, room) if r['type'] in self.CANDLES)
        self._codes = sorted(c for c in codes if c in self.ITEMS)
        return self._codes


class _Cv3SlotWatcher(Watcher):
    """A sideways room's enemy or candle: watch the zone's spawner slot ($840C: zone mod 6; enemies $07C2, candles
    object slot $0D + zone mod 6, tagged with the zone in $0645) while the camera is where that zone is loaded
    (camera zone - 5 to camera zone). A new thing counts once it shows; a removal counts only if nothing shows."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.inside = 0
        self.removing = watch['record'] is None

    def see(self, ram, frame, run):
        w = self.w
        if (ram[0x32], ram[0x33], ram[0x34]) != tuple(w['part']):
            self.inside = 0
            return False
        zone = (ram[0x56] | ram[0x57] << 8) // 64
        if not w['zone'] - 5 <= zone <= w['zone']:
            self.inside = 0
            return False
        self.inside += 1
        if self.inside < 2:                     # one look later, so the zone has surely been loaded
            return False
        slot = w['zone'] % 6
        if w['kind'] == 'enemy':
            sample = {'type': ram[0x7C2 + slot]}
            hit = sample['type'] == w['record']['type'] if not self.removing else sample['type'] != 0
        else:
            x = 0x0D + slot
            here = ram[0x645 + x] == w['zone']
            sample = {'type': ram[0x54E + x] if here else 0, 'drop': ram[0x5D8 + x]}
            hit = (sample['type'] in Castlevania3.CANDLES and sample['drop'] == w['record']['drop']) if not self.removing \
                else sample['type'] in Castlevania3.CANDLES
        if self.seen is None or hit or (not self.removing and sample['type']):
            self.seen = sample
        return hit

    def result(self):
        seen, w = self.seen, self.w
        if seen is None:
            return super().result()
        if w['kind'] == 'enemy':
            if self.removing:
                ok = seen['type'] == 0
                return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, no enemy is placed there any more.' if ok
                        else f'Played from the start, the game still places enemy type {seen["type"]:#04x} there.'}
            ok = seen['type'] == w['record']['type']
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game now places {w["name"]} there.' if ok
                    else f'Played from the start, the game placed enemy type {seen["type"]:#04x} there, not the one chosen.'}
        if self.removing:
            ok = seen['type'] not in Castlevania3.CANDLES
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, there is no candle there any more.' if ok
                    else 'Played from the start, a candle still appears there.'}
        ok = seen['type'] in Castlevania3.CANDLES and seen['drop'] == w['record']['drop']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the candle there now holds {w["name"]}.' if ok
                else f'Played from the start, the candle there holds item {seen["drop"]:#04x}, not the one chosen.'}


class _Cv3VerticalWatcher(Watcher):
    """A record of a room that scrolls up and down: the game puts it in any free slot when its height comes into view,
    so look for a spawner ($07C2 type, $07DA x) or candle slot ($054E type, $0438 x, $05D8 item) at its x."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.reached = False

    def see(self, ram, frame, run):
        w = self.w
        if (ram[0x32], ram[0x33], ram[0x34]) != tuple(w['part']):
            return False
        camera = (ram[0x57] * 240 + ram[0x56])
        if 0x37 <= w['y'] - camera < 0xB9 + 0x37:      # $82D7: placed while 0 <= its height - the camera's < $B9
            self.reached = True
        if w['kind'] == 'venemy':
            types = [ram[0x7C2 + s] for s in range(6) if ram[0x7DA + s] == w['x'] and ram[0x7C2 + s]]
            match = w['type'] in types if w['type'] else bool(types and w['old'] in types)
        else:
            drops = [ram[0x5D8 + s] for s in range(0x0D, 0x13) if ram[0x438 + s] == w['x'] and ram[0x54E + s] in Castlevania3.CANDLES]
            match = (w['drop'] in drops) if w['drop'] is not None else bool(drops)
        if match:
            self.seen = True
            return w['type'] != 0 if w['kind'] == 'venemy' else w['drop'] is not None
        return False

    def result(self):
        w = self.w
        if not self.reached:
            return super().result()
        removing = (w['kind'] == 'venemy' and not w['type']) or (w['kind'] == 'vcandle' and w['drop'] is None)
        ok = (not self.seen) if removing else bool(self.seen)
        what = 'enemy' if w['kind'] == 'venemy' else 'candle'
        if removing:
            text = f'Played from the start, the {what} no longer appears there.' if ok else f'Played from the start, the {what} still appears there.'
        else:
            text = f'Played from the start, the {what} there is now {w["name"]}.' if ok else f'Played from the start, the {what} there is not what was chosen.'
        return {'state': 'good' if ok else 'bad', 'text': text}


class _Cv3BlockWatcher(Watcher):
    """A breakable block: when the game places it (object slots $1A-$1B, $9CC0 / $9CA4) it copies the record's item
    into $078B and its broken flag number into $079D, so look for the slot with this block's flag and place (y in
    $041C in sideways rooms, x in $0438 in up-and-down ones) before it is broken ($078D = 0)."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if (ram[0x32], ram[0x33], ram[0x34]) != tuple(w['part']):
            return False
        for slot in Castlevania3.BLOCK_SLOTS:
            if not ram[0x470 + slot] or ram[0x79D + slot] != w['flag'] or ram[0x78D + slot] != 0:
                continue
            if (ram[0x41C + slot] if w['sideways'] else ram[0x438 + slot]) != (w['y'] if w['sideways'] else w['x']):
                continue
            self.seen = ram[0x78B + slot]
            return True
        return False

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        ok = self.seen == w['item']
        if w['item'] == 2:
            text = 'Played from the start, the block is placed empty.' if ok else 'Played from the start, the block still holds an item.'
        else:
            text = (f'Played from the start, the block now holds {w["name"].lower()}.' if ok else
                    f'Played from the start, the block holds {Castlevania3.BLOCK_ITEMS.get(self.seen, str(self.seen)).lower()}, not the one chosen.')
        return {'state': 'good' if ok else 'bad', 'text': text}


class Castlevania3Profile(Castlevania3, Profile):
    """Castlevania III on the common profile interface. Parts are {'block', 'sub', 'room'} (RAM $32, $33, $34)."""
    sha256s = (Castlevania3.sha256,)

    def where(self, ram):
        block, sub, room = ram[0x32], ram[0x33], ram[0x34]
        if block >= self.BLOCKS:
            return None
        part = {'block': block, 'sub': sub, 'room': room}
        try:
            vertical = self.vertical(block, sub, room)
        except (IndexError, ValueError):
            return None
        # the block's solidity rule as the game loaded it for its graphics (see tile_role)
        self.__dict__.setdefault('_rules', set()).add(bytes(ram[0x770:0x780]))
        if vertical:
            return {'part': part, 'x': 0, 'y': ram[0x57] * 240 + ram[0x56]}
        return {'part': part, 'x': ram[0x56] | ram[0x57] << 8, 'y': 0}

    def tile_role(self, tile):
        """What the game makes of a tile ($D3B9). Its collision map ($06E0: a nibble per 16x16 spot, from the tile at the
        spot's bottom left) gives tiles below $80 the class 'how many of $0770-$0777 the tile is not below', tiles $80-$BF
        the same with $0778-$077F, $DC/$DD 5 and $DE/$DF 7 (both kill), $E4/$E5 0. The eight bytes come from tables per
        background graphics set ($83F0 in ROM bank 0, by the banks in $4B/$4C), so the rule is read from the game's RAM
        in where(); when the parts of the map use different sets the roles are not given. The game's floor tests treat
        every class but 0 as ground. Breakable blocks use the same tiles as walls; they are objects (see blocks())."""
        rules = self.__dict__.get('_rules', set())
        if len(rules) != 1:
            return None
        rule = next(iter(rules))
        if tile >= 0xC0:
            if tile in (0xE4, 0xE5):
                return 'open'
            return 'solid' if tile in (0xDC, 0xDD, 0xDE, 0xDF) else None
        limits = rule[:8] if tile < 0x80 else rule[8:]
        return 'solid' if tile >= limits[0] else 'open'

    def part_name(self, part):
        block, sub, room = int(part['block']), int(part['sub']), int(part['room'])
        try:
            label = self.block_label(block, sub)
            many = self.rooms(block, sub) > 1
        except (IndexError, ValueError):
            return f'Block {block}, part {sub}, room {room + 1}'
        return f'Block {label}' + (f', room {room + 1}' if many else '')

    def choices(self):
        return {'enemies': variant_names(self.enemy_choices()),
                'items': [{'value': code, 'name': self.item_name(code)} for code in self.drop_codes()],
                'block_items': [{'value': code, 'name': name} for code, name in self.BLOCK_ITEMS.items()]}

    def _vertical_enemy_choices(self):
        found, seen = [], set()
        for block, sub, room in self.all_rooms():
            if not self.vertical(block, sub, room):
                continue
            for rec in self.vertical_records(block, sub, room):
                key = (rec['type'], rec['p1'], rec['p2'])
                if not rec['candle'] and rec['type'] and key not in seen:
                    seen.add(key)
                    found.append({'value': f'{rec["type"]}:{rec["p1"]}:{rec["p2"]}', 'name': self.enemy_name(rec['type']),
                                  'key': (rec['type'], rec['p1'], rec['p2'])})
        found.sort(key=lambda c: c['value'])
        # the same enemy with other settings: number them in the order of their settings
        out = []
        for c in found:
            same = sorted(o['key'] for o in found if o['name'] == c['name'])
            out.append({'value': c['value'], 'name': c['name'] + (f', kind {same.index(c["key"]) + 1}' if len(same) > 1 else '')})
        return out

    def objects(self, part, sub=None, room=None):
        if not isinstance(part, dict):
            return Castlevania3.objects(self, part, sub, room)
        block, sub, room = int(part['block']), int(part['sub']), int(part['room'])
        out = []
        for item in Castlevania3.objects(self, block, sub, room):
            row = dict(item)
            if item['kind'] == 'enemy':
                row.update(id=f'enemy:{item["zone"]}', style='enemy', remove='Remove this enemy',
                           fields=[{'key': 'record', 'label': 'Swap for', 'value': item['index'], 'choices': 'enemies'}])
                if item['hard']:
                    row['note'] = 'Only in the harder mode (the game skips this enemy unless $07F6 is set, as it is after the ending or with that password).'
            elif item['kind'] == 'candle':
                row.update(id=f'candle:{item["zone"]}', style='item', detail=f'drops {self.item_name(item["drop"])}',
                           remove='Remove this candle')
                if item['shared'] <= 1:
                    row['fields'] = [{'key': 'drop', 'label': 'Drops', 'value': item['drop'], 'choices': 'items'}]
                else:
                    others = item['shared'] - 1
                    alternatives = self.candle_alternatives(self.candle_record(item['index']))
                    row['fields'] = [{'key': 'record', 'label': 'Drops', 'value': item['index'],
                                      'choices': [{'value': a['index'], 'name': self.item_name(a['drop'])} for a in alternatives]}]
                    row['note'] = (f'This candle shares its settings with {others} other {"candle" if others == 1 else "candles"} in the game, '
                                   'so a new item is given to this one alone by pointing it at another of the game’s candles at the same spot.')
            elif item['kind'] == 'venemy':
                row.update(id=f'venemy:{item["number"]}', style='enemy', remove='Remove this enemy',
                           fields=[{'key': 'kind', 'label': 'Swap for', 'value': f'{item["type"]}:{item["p1"]}:{item["p2"]}',
                                    'choices': self._vertical_enemy_choices()}])
            elif item['kind'] == 'block':
                inside = self.block_item_name(item['item'])
                row.update(id=f'block:{item["number"]}', style='block', remove=None,
                           detail='empty' if item['item'] == 2 else f'{inside.lower()} inside',
                           fields=[{'key': 'item', 'label': 'Inside', 'value': item['item'], 'choices': 'block_items'}])
                notes = []
                if item['double']:
                    notes.append('Two blocks high: both have to be broken before the item falls out.')
                if item['item'] in (3, 5):
                    notes.append('With no subweapon or the stopwatch the game gives a large heart instead.')
                if item['shared'] > 1:
                    others = [self.part_name({'block': b, 'sub': s, 'room': r}) for b, s, r in self.list_users(item['list'])
                              if (b, s, r) != (block, sub, room)]
                    notes.append('The game uses this room’s list of blocks in other places too (' + ', '.join(others) +
                                 '), so the change shows there as well.')
                if notes:
                    row['note'] = ' '.join(notes)
            else:
                row.update(id=f'vcandle:{item["number"]}', style='item', detail=f'drops {self.item_name(item["drop"])}',
                           remove='Remove this candle', fields=[{'key': 'drop', 'label': 'Drops', 'value': item['drop'], 'choices': 'items'}])
            if item['kind'] != 'block' and item['type'] in self.CANDLES and item.get('drop') in self.SUBWEAPONS:
                row['note'] = ' '.join(([row['note']] if row.get('note') else []) +
                                       ['With a partner the game gives the partner’s own item in place of this one.'])
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        block, sub, room = int(part['block']), int(part['sub']), int(part['room'])
        where = [block, sub, room]
        kind, _, number = object_id.partition(':')
        number = int(number)
        if kind in ('enemy', 'candle'):
            row = self.zones(block, sub, room)[number]
            if kind == 'enemy':
                index = 0 if remove else int(values.get('record'))
                record = self.enemy_record(index)
                if not remove and record is None:
                    raise ValueError('That choice is not one of the game’s own.')
                name = 'no enemy' if record is None else self.enemy_name(record['type'])
                offset = row['enemy_byte']
                writes = [(offset, self.rom[offset], index)]
                title = 'Remove the enemy' if record is None else f'Enemy here: {name}'
            elif remove:
                record, name, offset = None, '', row['candle_byte']
                writes = [(offset, self.rom[offset], 0)]
                title = 'Remove the candle'
            elif 'drop' in values:
                if row['candle'] is None or self.candle_users(row['candle']['record']) > 1:
                    raise ValueError('This candle shares its settings with others. Choose one of the listed candles instead.')
                record = dict(row['candle'])
                if False:
                    raise ValueError('This candle shares its settings with others. Choose one of the listed candles instead.')
                drop = int(values['drop'])
                if drop not in self.drop_codes():
                    raise ValueError('That choice is not one of the game’s own.')
                offset = self.offset(record['record'] + 1)
                writes = [(offset, self.rom[offset], drop)]
                record['drop'] = drop
                name = self.item_name(drop)
                title = f'Candle drops: {name}'
            else:
                index = int(values.get('record'))
                record = self.candle_record(index)
                if record is None:
                    raise ValueError('That choice is not one of the game’s own.')
                offset = row['candle_byte']
                writes = [(offset, self.rom[offset], index)]
                name = self.item_name(record['drop'])
                title = f'Candle drops: {name}'
            return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'{title} (zone {number + 1})',
                    'watch': {'kind': kind, 'zone': number, 'record': record, 'part': where, 'name': name}}
        if kind in ('venemy', 'vcandle'):
            rec = next((r for r in self.vertical_records(block, sub, room) if r['number'] == number), None)
            if rec is None:
                raise ValueError('That is not part of this room.')
            y = rec['page'] * 240 + rec['ry'] + 0x37
            if kind == 'venemy':
                if remove:
                    new = (0, rec['p1'], rec['p2'])
                else:
                    value = str(values.get('kind'))
                    if value not in {c['value'] for c in self._vertical_enemy_choices()}:
                        raise ValueError('That choice is not one of the game’s own.')
                    new = tuple(int(v) for v in value.split(':'))
                spots = [(rec['byte'] + 2, new[0]), (rec['byte'] + 5, new[1]), (rec['byte'] + 6, new[2])]
                writes = [(o, self.rom[o], v) for o, v in spots if self.rom[o] != v]
                name = 'no enemy' if not new[0] else self.enemy_name(new[0])
                return {'writes': writes, 'title': 'Remove the enemy' if not new[0] else f'Enemy here: {name}',
                        'watch': {'kind': 'venemy', 'part': where, 'x': rec['x'], 'y': y, 'type': new[0], 'old': rec['type'], 'name': name}}
            if remove:
                o = rec['byte'] + 2
                return {'writes': [(o, self.rom[o], 0)], 'title': 'Remove the candle',
                        'watch': {'kind': 'vcandle', 'part': where, 'x': rec['x'], 'y': y, 'drop': None, 'name': ''}}
            drop = int(values.get('drop'))
            if drop not in self.drop_codes():
                raise ValueError('That choice is not one of the game’s own.')
            o = rec['byte'] + 4
            return {'writes': [(o, self.rom[o], drop)] if self.rom[o] != drop else [], 'title': f'Candle drops: {self.item_name(drop)}',
                    'watch': {'kind': 'vcandle', 'part': where, 'x': rec['x'], 'y': y, 'drop': drop, 'name': self.item_name(drop)}}
        if kind == 'block':
            rec = next((b for b in self.blocks(block, sub, room) if b['number'] == number), None)
            if rec is None:
                raise ValueError('That is not part of this room.')
            item = int(values.get('item'))
            if item not in self.BLOCK_ITEMS:
                raise ValueError('That choice is not one of the game’s own.')
            o = rec['byte'] + 5
            name = self.block_item_name(item)
            return {'writes': [(o, self.rom[o], item)] if self.rom[o] != item else [],
                    'title': 'Empty block' if item == 2 else f'Block holds: {name}',
                    'watch': {'kind': 'block', 'part': where, 'flag': rec['flag'], 'sideways': rec['kind'] == self.BLOCK_SIDEWAYS,
                              'x': rec['x'], 'y': rec['y'], 'item': item, 'name': name}}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        if watch['kind'] == 'block':
            return _Cv3BlockWatcher(watch)
        if watch['kind'] in ('enemy', 'candle'):
            return _Cv3SlotWatcher(watch)
        if watch['kind'] in ('venemy', 'vcandle'):
            return _Cv3VerticalWatcher(watch)
        return Watcher()


# ============================================================================================ Castlevania II


class Castlevania2:
    """Castlevania II - Simon's Quest (USA), MMC1. Object placement: ROM bank 1 (0x4000) run at CPU $8000 ($8000 finds
    the list, $8029 walks it). A part of the game is an area kind ($30), an area ($50) and a room ($51); the word at
    $8192 + kind * 2, then + area * 2, then + room * 2 points at the room's list of 4-byte records ended by $FF:
    x / 16, y / 16, type, setting. A type with bit 7 set is a person or thing Simon can talk to (its setting is the
    message it shows, or for a merchant ($2E) a line of the table at $8871); other types are enemies and items, whose
    setting the game doubles at night outside the exceptions listed at $811B.
    """
    name = 'Castlevania II'
    sha256 = '22ac359d66da2df940c9c309c8b1e29d0650700a58a9abd2ed5045d56a8c14dd'
    BANK = 0x4000           # ROM offset of CPU $8000 while objects are placed
    FIXED = 0x1C000
    TEXT_BANK = 0xC000      # messages: table $8B82 in ROM bank 3 (read by $EEA4)
    MERCHANT = 0x2E
    TALK_SPECIAL = {0x2F, 0x1E, 0x3C}     # talkers whose message is not their setting ($86C7)
    NOT_DOUBLED = {0x21, 0x22, 0x25, 0x26, 0x27, 0x2D, 0x2E, 0x2F, 0x34}  # $811B: settings kept at night
    THINGS = {}
    CHARS = {0x00: ' ', 0x1B: '.', 0x1C: '’', 0x1E: ',', 0x40: '!', 0x46: '-', 0x5D: '?'}

    def __init__(self, rom: bytes):
        self.rom = rom

    def offset(self, address: int) -> int:
        if address < 0x8000:
            raise ValueError('That address is not in the cartridge.')
        return HEADER_NES + (self.BANK + address - 0x8000 if address < 0xC000 else self.FIXED + address - 0xC000)

    def _at(self, address: int) -> int:
        return self.rom[self.offset(address)]

    def _word(self, address: int) -> int:
        return self._at(address) | self._at(address + 1) << 8

    def room_list(self, kind: int, area: int, room: int) -> int:
        return self._word(self._word(self._word(0x8192 + 2 * kind) + 2 * area) + 2 * room)

    def records(self, kind: int, area: int, room: int) -> list:
        address, out = self.room_list(kind, area, room), []
        if not 0x8000 <= address < 0xC000:
            return out
        for number in range(64):
            if self._at(address) == 0xFF:
                break
            raw = [self._at(address + i) for i in range(4)]
            out.append({'number': number, 'x': raw[0] * 16, 'y': raw[1] * 16, 'raw_type': raw[2], 'type': raw[2] & 0x7F,
                        'talks': bool(raw[2] & 0x80), 'setting': raw[3], 'byte': self.offset(address)})
            address += 4
        return out

    def text(self, number: int) -> str:
        """A message as the game spells it (table $8B82 in ROM bank 3; 1-26 are A-Z, $36-$3F digits, $FE a new line)."""
        bank = lambda a: self.rom[HEADER_NES + self.TEXT_BANK + a - 0x8000]
        if not 0 <= number < 0x79:
            return ''
        pointer = bank(0x8B82 + 2 * number) | bank(0x8B83 + 2 * number) << 8
        if not 0x8000 <= pointer < 0xC000:
            return ''
        out = ''
        for i in range(160):
            c = bank(pointer + i)
            if c == 0xFF:
                break
            if c == 0xFE:
                out = out[:-1] if out.endswith('-') else out + ' '
            elif 1 <= c <= 26:
                out += chr(64 + c)
            elif 0x36 <= c <= 0x3F:
                out += str(c - 0x36)
            else:
                out += self.CHARS.get(c, '')
        return ' '.join(out.split()).replace(' ,', ',')

    def merchant_text(self, setting: int) -> int:
        return self._at(0x8871 + setting)

    def message_of(self, record: dict):
        """The message number a talker shows, or None."""
        if not record['talks'] or record['type'] in self.TALK_SPECIAL:
            return None
        return self.merchant_text(record['setting']) if record['type'] == self.MERCHANT else record['setting']

    def all_lists(self) -> list:
        """(kind, area, room) of every room list the tables reach, walking each table up to the lowest address it
        points at (the tables follow one another)."""
        out, seen = [], set()
        for kind in range(6):
            areas = self._word(0x8192 + 2 * kind)
            lowest, area = 0xFFFF, 0
            while areas + 2 * area < lowest and area < 32:
                rooms = self._word(areas + 2 * area)
                if not 0x8000 <= rooms < 0xC000:
                    break
                lowest = min(lowest, rooms)
                low2, room = 0xFFFF, 0
                while rooms + 2 * room < low2 and room < 16:
                    found = self._word(rooms + 2 * room)
                    if not 0x8000 <= found < 0xC000:
                        break
                    low2 = min(low2, found)
                    if found not in seen:
                        seen.add(found)
                        out.append((kind, area, room))
                    room += 1
                area += 1
        return out


class _Cv2Watcher(Watcher):
    """A record of a Castlevania II room: the game tags the object slot it fills with the record's number + 1 ($0432,
    slots 6-17), so look at that slot's type ($03B4) and setting ($04D4 for talkers, $04C2 otherwise)."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.reached = False

    def see(self, ram, frame, run):
        w = self.w
        if (ram[0x30], ram[0x50], ram[0x51]) != tuple(w['part']):
            return False
        camera = ram[0x53] | ram[0x54] << 8
        down = w['y'] - (ram[0x8C] | ram[0x8D] << 8)
        night = ram[0x82] != 0 or ram[0x30] != 0          # towns place enemies only at night (0FA)
        if 16 <= w['x'] - camera <= 240 and 16 <= down <= 224 and (w['talks'] or night):
            self.reached = True
        elif 16 <= w['x'] - camera <= 240 and 16 <= down <= 224:
            self.daylight = True
        for slot in range(6, 18):
            if ram[0x432 + slot] == w['number'] + 1 and ram[0x3B4 + slot]:
                setting = ram[0x4D4 + slot] if w['talks'] else ram[0x4C2 + slot]
                self.seen = {'type': ram[0x3B4 + slot], 'setting': setting}
                return True
        return False

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            if self.reached and w['type'] == 0:
                return {'state': 'good', 'text': 'Played from the start, nothing is placed there any more.'}
            if not self.reached and getattr(self, 'daylight', False):
                return {'state': 'warn', 'text': 'The recorded walk passed that spot in daylight, when the game places no enemies in towns, so the change could not be watched.'}
            if self.reached:
                return {'state': 'bad', 'text': 'Played from the start, the walk passed that spot but nothing was placed there.'}
            return super().result()
        if w['type'] == 0:
            return {'state': 'bad', 'text': f'Played from the start, the game still places type {seen["type"]:#04x} there.'}
        ok = seen['type'] == w['type'] and (w['setting'] is None or seen['setting'] == w['setting'])
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game now places {w["name"]} there.' if ok
                else f'Played from the start, the game placed type {seen["type"]:#04x} with setting {seen["setting"]:#04x} there, not what was chosen.'}


class Castlevania2Profile(Castlevania2, Profile):
    """Castlevania II on the common profile interface. Parts are {'kind', 'area', 'room'} (RAM $30, $50, $51); the
    camera is $53/$54 across and $8C/$8D down, in the room's pixels."""
    sha256s = (Castlevania2.sha256,)
    # (name, what it does), named by keeping one record of the type in a room that uses it (the room's other enemies
    # removed in a ROM copy), sending the game there and watching (trace/v15_profiles/naming_castlevania/names.png).
    # Types the scripted visit never brought on screen keep their numbers.
    ENEMIES = {
        0x03: ('Skeleton', 'Walks back and forth on the stairs and floors of the mansions.'),
        0x04: ('Werewolf', 'Prowls back and forth near you.'),
        0x06: ('Red beast', 'Crouches low and spits fireballs.'),
        0x13: ('Blue ghoul', 'Lurches toward you through the woods.'),
        0x15: ('Wall creature', 'Clings to a wall and spits fire.'),
        0x17: ('Zombie', 'Walks toward you through town at night.'),
        0x1D: ('Fire man', 'A man made of fire that walks about and throws fireballs.'),
        0x02: ('Red snake', 'Wriggles in place on the wall.'),
        0x05: ('Spear skeleton', 'Stands guard and thrusts a spear.'),
        0x0D: ('Bone-throwing skeleton', 'Throws bones at you.'),
        0x0F: ('Gargoyle', 'A winged demon that flies about and spits fireballs.'),
        0x11: ('Bat', 'Flies about the room.'),
        0x12: ('Wolf', 'Leaps at you.'),
        0x16: ('Ghoul', 'Walks along the graveyard.'),
        0x18: ('Fishman', 'Leaps out of the swamp and spits fireballs.'),
        0x38: ('Grave hand', 'Pokes up out of the ground.'),
        0x39: ('Ghost', 'Floats toward you.'),
        0x3A: ('Mummy', 'Walks slowly toward you.'),
        0x3B: ('Eagle', 'Swoops across the sky.'),
        0x3F: ('Man-eating plant', 'Stays rooted and spits at you.'),
        0x41: ('Floating eyeball', 'Drifts up and down above the ground.'),
        0x42: ('Giant floating mask (boss)', 'A huge stone face that drifts about the room.'),
        0x44: ('Death (boss)', 'The Grim Reaper; he swings his scythe at you.'),
        0x4A: ('Bone serpent', 'A neck of bones that rises from the ground and spits fireballs.'),
    }

    def where(self, ram):
        kind = ram[0x30]
        if kind > 5:
            return None
        return {'part': {'kind': kind, 'area': ram[0x50], 'room': ram[0x51]},
                'x': ram[0x53] | ram[0x54] << 8, 'y': ram[0x8C] | ram[0x8D] << 8}

    def part_name(self, part):
        kind, area, room = int(part['kind']), int(part['area']), int(part['room'])
        place = 'Town' if kind == 0 else f'Area kind {kind}'
        return f'{place} {area + 1}, room {room + 1}'

    def enemy_name(self, kind: int) -> str:
        return self.ENEMIES[kind][0] if kind in self.ENEMIES else f'Enemy {kind:#04x}'

    def enemy_does(self, kind: int):
        return self.ENEMIES[kind][1] if kind in self.ENEMIES else None

    def _choices(self):
        if hasattr(self, '_cached'):
            return self._cached
        messages, merchants, enemies = set(), set(), set()
        for kind, area, room in self.all_lists():
            for rec in self.records(kind, area, room):
                if rec['talks'] and rec['type'] == self.MERCHANT:
                    merchants.add(rec['setting'])
                elif rec['talks'] and rec['type'] not in self.TALK_SPECIAL:
                    messages.add(rec['setting'])
                elif not rec['talks'] and rec['type'] not in self.NOT_DOUBLED and rec['type']:
                    enemies.add(rec['type'])
        self._cached = {
            'messages': [{'value': n, 'name': self.text(n)} for n in sorted(messages) if self.text(n)],
            'wares': [{'value': n, 'name': self.text(self.merchant_text(n))} for n in sorted(merchants)
                      if n < 16 and self.text(self.merchant_text(n))],
            'enemies': [{'value': t, 'name': self.enemy_name(t)} for t in sorted(enemies)]}
        return self._cached

    def choices(self):
        return self._choices()

    def objects(self, part):
        kind, area, room = int(part['kind']), int(part['area']), int(part['room'])
        out = []
        for rec in self.records(kind, area, room):
            row = {'id': f'obj:{rec["number"]}', 'type': rec['raw_type'], 'x': rec['x'] + 8, 'y': rec['y'],
                   'number': rec['number'], 'remove': None}
            message = self.message_of(rec)
            if rec['talks'] and rec['type'] == self.MERCHANT:
                row.update(style='item', name='Merchant', detail=self.text(message),
                           fields=[{'key': 'setting', 'label': 'Sells', 'value': rec['setting'], 'choices': 'wares'}])
            elif rec['talks'] and message is not None:
                row.update(style='item', name=f'Person {rec["type"]:#04x}', detail=self.text(message),
                           fields=[{'key': 'setting', 'label': 'Says', 'value': rec['setting'], 'choices': 'messages'}])
            elif rec['talks']:
                row.update(style='item', name=f'Person {rec["type"]:#04x}', fields=[])
            elif rec['type'] in self.NOT_DOUBLED:
                row.update(style='item', name=f'Thing {rec["type"]:#04x}', fields=[])
            else:
                row.update(style='enemy', name=self.enemy_name(rec['type']), remove='Remove this enemy',
                           fields=[{'key': 'type', 'label': 'Swap for', 'value': rec['type'], 'choices': 'enemies'}])
                if self.enemy_does(rec['type']):
                    row['does'] = self.enemy_does(rec['type'])
                if kind == 0:
                    row['note'] = 'In towns the game places enemies only at night.'
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        kind, area, room = int(part['kind']), int(part['area']), int(part['room'])
        number = int(object_id.partition(':')[2])
        rec = next((r for r in self.records(kind, area, room) if r['number'] == number), None)
        if rec is None:
            raise ValueError('That is not part of this room.')
        watch = {'part': [kind, area, room], 'number': number, 'x': rec['x'], 'y': rec['y'], 'talks': rec['talks'], 'day_only': False}
        if rec['talks']:
            if rec['type'] in self.TALK_SPECIAL:
                raise ValueError('ROMancer cannot change that yet.')
            setting = int(values.get('setting'))
            key = 'wares' if rec['type'] == self.MERCHANT else 'messages'
            if setting not in {c['value'] for c in self._choices()[key]}:
                raise ValueError('That choice is not one of the game’s own.')
            o = rec['byte'] + 3
            text = self.text(self.merchant_text(setting) if key == 'wares' else setting)
            short = text if len(text) <= 40 else text[:40].rsplit(' ', 1)[0] + '…'
            return {'writes': [(o, self.rom[o], setting)] if self.rom[o] != setting else [],
                    'title': ('Merchant sells: ' if key == 'wares' else 'Says: ') + short,
                    'watch': dict(watch, type=rec['type'], setting=setting, name='the chosen ' + ('wares' if key == 'wares' else 'message'))}
        if rec['type'] in self.NOT_DOUBLED:
            raise ValueError('ROMancer cannot change that yet.')
        new = 0 if remove else int(values.get('type'))
        if not remove and new not in {c['value'] for c in self._choices()['enemies']}:
            raise ValueError('That choice is not one of the game’s own.')
        o = rec['byte'] + 2
        name = 'nothing' if not new else self.enemy_name(new)
        return {'writes': [(o, self.rom[o], new)] if self.rom[o] != new else [],
                'title': 'Remove the enemy' if not new else f'Enemy here: {name}',
                'watch': dict(watch, type=new, setting=None, name=name, day_only=kind == 0)}

    def watcher(self, watch):
        return _Cv2Watcher(watch)


PROFILES = [Castlevania3Profile, Castlevania2Profile]
