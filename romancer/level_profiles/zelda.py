"""The Legend of Zelda (USA) (Rev 1): level profile (Zelda II - The Adventure of Link is not covered yet; see the notes).

Everything here was read from the games' own code and tables and checked by replaying the games (research notes in
research/zelda-level-profile.md). Zelda shows its world one screen at a time; a part of the game is the overworld or one
dungeon (with its quest), and its pixels are the screens laid out on the game's own 16 x 8 room grid, so the screens the
map recorder stitches together line up with the rooms they show.
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER = 16


def _bank(rom_banks: int, bank: int, address: int) -> int:
    """File offset of a CPU address in a 16 KB bank (the last bank sits at $C000)."""
    return HEADER + bank * 0x4000 + address - (0xC000 if bank == rom_banks - 1 else 0x8000)


class Zelda1:
    """The Legend of Zelda (USA) (Rev 1). MMC1, 8 banks of 16 KB, fixed bank 7.

    Rooms: every level (0 overworld, 1-9 dungeons) has six tables of 128 bytes, one byte per room of a 16 x 8 grid
    (level blocks in bank 6: pointers $8000 for the first quest and $802A for the second, copied to RAM $687E).
    Dungeons 1-6 share one block and 7-9 another; each dungeon owns its own rooms of the grid. Level info (bank 6
    pointers at $8014, $FC bytes, copied to $6B7E): enemy counts at +$24, item spots at +$29, start room at +$2F, the
    dungeon map at +$3F (one byte per column, rotated by +$2D), stairway rooms at +$34 and the boss room at +$3E.
    """
    name = 'The Legend of Zelda'
    sha256 = '44e33dc0a6fb663b98908ea761b33bbd77ca5092f25c624b10bf2a97e5406a5a'
    BANKS = 8
    # enemy types, named by spawning each one in a room and looking at what the game drew (pictures in
    # trace/v15_profiles/zelda/sheet_ow.png, sheet_dg*.png, sheet_re.png); types never seen keep their number
    ENEMIES = {0x01: 'Blue Lynel', 0x02: 'Red Lynel', 0x03: 'Blue Moblin', 0x04: 'Red Moblin', 0x05: 'Blue Goriya',
               0x06: 'Red Goriya', 0x07: 'Red Octorok', 0x08: 'Red Octorok (second kind)', 0x09: 'Blue Octorok',
               0x0A: 'Blue Octorok (second kind)', 0x0B: 'Red Darknut', 0x0C: 'Blue Darknut', 0x0D: 'Blue Tektite',
               0x0E: 'Red Tektite', 0x0F: 'Blue Leever', 0x10: 'Red Leever', 0x12: 'Vire', 0x13: 'Zol', 0x15: 'Gel',
               0x16: 'Pols Voice', 0x17: 'Like Like', 0x1A: 'Peahat', 0x1B: 'Blue Keese', 0x1D: 'Black Keese',
               0x1F: 'Falling rocks', 0x21: 'Ghini', 0x23: 'Blue Wizzrobe', 0x24: 'Red Wizzrobe', 0x27: 'Wallmaster',
               0x28: 'Rope', 0x2A: 'Stalfos', 0x2B: 'Bubble', 0x2C: 'Blue Bubble', 0x2D: 'Red Bubble', 0x2F: 'Fairy',
               0x30: 'Gibdo', 0x31: 'Dodongo', 0x32: 'Dodongo (one)', 0x33: 'Blue Gohma', 0x34: 'Red Gohma',
               0x35: 'Ring of rupees', 0x36: 'Hungry Goriya', 0x37: 'Old man', 0x38: 'Digdogger',
               0x39: 'Digdogger (one)', 0x3A: 'Red Lanmola', 0x3B: 'Blue Lanmola', 0x3C: 'Manhandla',
               0x3D: 'Aquamentus', 0x3E: 'Ganon', 0x3F: 'Fire', 0x41: 'Moldorm', 0x43: 'Gleeok', 0x44: 'Gleeok',
               0x45: 'Gleeok', 0x47: 'Patra', 0x48: 'Patra', 0x49: 'Blade trap', 0x4A: 'Blade traps in the corners',
               0x4B: 'Old man (hint about Dodongo)', 0x4C: 'Old man (hint about the eastmost peninsula)',
               0x4D: 'Old man (hint about the eyes of Gohma)', 0x4E: 'Old man (hint about the waterfall)',
               0x4F: 'Old man who gives or takes rupees', 0x50: 'Old man (hint about the tip of the nose)',
               0x51: 'Old man who asks for life or money', 0x52: 'Old man (hint about the arrow)'}
    # item numbers (caves and dungeons share them), named by placing each one and looking at it
    # (trace/v15_profiles/zelda/items_crop.png, sheet_shop.png)
    ITEMS = {0x00: 'Bombs', 0x01: 'Wooden sword', 0x02: 'White sword', 0x03: 'Magical sword', 0x04: 'Bait',
             0x05: 'Recorder', 0x06: 'Blue candle', 0x07: 'Red candle', 0x08: 'Arrow', 0x09: 'Silver arrow',
             0x0A: 'Bow', 0x0B: 'Magic key', 0x0C: 'Raft', 0x0D: 'Stepladder', 0x0F: '5 rupees', 0x10: 'Magic rod',
             0x11: 'Book of magic', 0x12: 'Blue ring', 0x13: 'Red ring', 0x14: 'Power bracelet', 0x15: 'Letter',
             0x16: 'Compass', 0x17: 'Map', 0x18: 'Rupee', 0x19: 'Key', 0x1A: 'Heart container',
             0x1B: 'Triforce piece', 0x1C: 'Magic shield', 0x1D: 'Boomerang', 0x1E: 'Magic boomerang',
             0x1F: 'Blue potion', 0x20: 'Red potion', 0x21: 'Clock', 0x22: 'Heart', 0x23: 'Fairy'}
    NO_ITEM = 0x03                      # a dungeon room whose item number is 3 has no item ($B84E)
    NO_CAVE_ITEM = 0x3F
    # door types (dungeon tables A and B): drawn in sheet_doors.png; walls 1-3 told apart by the walk code at
    # $E69C (1 and 7 stop Link), 4 by the bomb code at $F99F
    DOORS = {0: 'Open doorway', 1: 'Wall', 2: 'Wall Link can walk through', 3: 'Wall Link can walk through (kind 3)',
             4: 'Wall a bomb opens', 5: 'Locked door', 6: 'Locked door (kind 6)', 7: 'Shutter'}
    PASSABLE = {0, 2, 3}                # doors Link walks through on the way in, with no key or bomb
    SIDES = (('north', 0, 5), ('south', 0, 2), ('west', 1, 5), ('east', 1, 2))   # (side, table, shift)
    # room action (dungeon table F bits 0-2), from the jump table at bank 5 $8BF1 and the item code at $B83A
    ACTIONS = {0: 'Nothing happens',
               1: 'Shutters open when every enemy is defeated',
               2: 'Defeating the first enemy defeats the others',
               3: 'Shutters open when the recorder is played',
               4: 'Shutters open when the block is pushed',
               5: 'Stairs appear when the block is pushed',
               6: 'Shutters open when the first enemy is defeated',
               7: 'The item appears and the shutters open when every enemy is defeated'}
    HIDES_ITEM = {3, 7}                 # actions that keep the room item hidden at first ($B856)
    # overworld secret squares (bank 5 $AABF: square tiles $E5-$EA -> secret object $62-$67, handled at bank 4 $8E44)
    SECRETS = {0x26: 'Rock that moves when pushed (needs the power bracelet)', 0x27: 'Wall that a bomb opens',
               0x28: 'Bush that burns away', 0x29: 'Gravestone that moves when pushed',
               0x2A: 'Block that moves when pushed (needs the power bracelet)', 0x2B: 'Wall that a bomb opens'}
    CAVE_SQUARE = 0x0C
    CAVES = 20                          # cave contents: overworld table E, 3 items each, then 3 prices each

    def __init__(self, rom: bytes):
        self.rom = rom

    # ---- reading
    def at(self, bank: int, address: int) -> int:
        return _bank(self.BANKS, bank, address)

    def byte(self, bank: int, address: int) -> int:
        return self.rom[self.at(bank, address)]

    def word(self, bank: int, address: int) -> int:
        return self.byte(bank, address) | self.byte(bank, address + 1) << 8

    def block(self, level: int, quest: int) -> int:
        """File offset of the level's six room tables."""
        return self.at(6, self.word(6, (0x8000 if quest == 1 else 0x802A) + level * 2))

    def table(self, level: int, quest: int, number: int) -> int:
        return self.block(level, quest) + number * 128

    def info(self, level: int, quest: int) -> bytes:
        """The level info as the game has it in RAM: the second quest's dungeons replace bytes from +$29 ($8109)."""
        start = self.at(6, self.word(6, 0x8014 + level * 2))
        data = bytearray(self.rom[start:start + 0xFC])
        if quest == 2 and level:
            source = self.word(6, 0x83A2 + level * 2)
            count = self.byte(6, 0x83B5 + level) + 1
            data[0x29:0x29 + count] = bytes(self.byte(6, source + i) for i in range(count))
        return bytes(data)

    def second_quest_patches(self) -> dict:
        """{table offset: value} the code at bank 6 $812D writes over the overworld tables in the second quest."""
        out = {}
        for i in range(8):
            out[self.byte(6, 0x815F + i) + 128] = self.byte(6, 0x8167 + i)       # X indexes $68FE (table B onward)
        address = 0x813B
        while self.byte(6, address) == 0xA9 and self.byte(6, address + 2) == 0x8D:
            out[self.word(6, address + 3) - 0x687E] = self.byte(6, address + 1)
            address += 5
        return out

    def room(self, level: int, quest: int, room: int) -> dict:
        """The six table bytes of a room (a-f) and their file offsets (None where the game's code sets the value)."""
        values = {}
        patches = self.second_quest_patches() if (level == 0 and quest == 2) else {}
        for number, key in enumerate('abcdef'):
            offset = self.table(level, quest, number) + room
            values[key] = patches.get(number * 128 + room, self.rom[offset])
            values[key + '_at'] = None if number * 128 + room in patches else offset
        return values

    def counts(self, level: int, quest: int) -> list:
        return list(self.info(level, quest)[0x24:0x28])

    def rooms(self, level: int, quest: int) -> list:
        if level == 0:
            return list(range(128))
        info = self.info(level, quest)
        found = set(self.stair_rooms(level, quest))
        for index in range(16):
            column = (index - info[0x2D]) & 15
            for row in range(8):
                if info[0x3F + index] & (0x80 >> row):
                    found.add(row * 16 + column)
        return sorted(found)

    def stair_rooms(self, level: int, quest: int) -> list:
        if level == 0:
            return []
        out = []
        for value in self.info(level, quest)[0x34:0x3E]:
            if value == 0xFF:
                break
            out.append(value)
        return out

    def start_room(self, level: int, quest: int) -> int:
        return self.info(level, quest)[0x2F]

    def boss_room(self, level: int, quest: int):
        return self.info(level, quest)[0x3E] if level else None

    # ---- enemies (bank 5 $887E): type = C & $3F, plus $40 when D bit 7 is set; count = level info +$24 [C >> 6]
    def enemy(self, level: int, quest: int, room: int) -> dict:
        r = self.room(level, quest, room)
        kind = (r['c'] & 0x3F) | (0x40 if r['d'] & 0x80 else 0)
        index = r['c'] >> 6
        count = self.group_count(level, quest, kind, index)
        return {'type': kind, 'count_index': index, 'count': count, 'members': self.members(kind, count),
                'c_at': r['c_at'], 'd_at': r['d_at'], 'c': r['c'], 'd': r['d']}

    def group_count(self, level: int, quest: int, kind: int, index: int) -> int:
        if not kind:
            return 0
        if 0x32 <= kind < 0x62:
            return 1                    # the game makes these one of a kind ($88A2)
        return self.counts(level, quest)[index]

    def members(self, kind: int, count: int) -> list:
        """What fills the enemy slots: one type, or for types $62 and up the game's mixed list (bank 5 $873F)."""
        if not kind:
            return []
        if kind < 0x62:
            return [kind] * count
        pointer = self.word(5, 0x873F + (kind - 0x62) * 2)
        return [self.byte(5, pointer + i) for i in range(count)]

    def enemy_name(self, kind: int) -> str:
        return self.ENEMIES.get(kind, f'Enemy {kind:#04x}')

    def group_name(self, kind: int, count: int) -> str:
        names = {}
        for member in self.members(kind, count):
            if member:
                name = self.enemy_name(member)
                names[name] = names.get(name, 0) + 1
        return ', '.join(f'{name} ({n})' if n > 1 else name for name, n in names.items()) or 'No enemies'

    # ---- dungeon rooms
    def doors(self, level: int, quest: int, room: int) -> list:
        r = self.room(level, quest, room)
        out = []
        for side, number, shift in self.SIDES:
            key = 'ab'[number]
            out.append({'side': side, 'type': (r[key] >> shift) & 7, 'at': r[key + '_at'], 'shift': shift})
        return out

    def item(self, level: int, quest: int, room: int) -> dict:
        r = self.room(level, quest, room)
        spot = self.info(level, quest)[0x29 + ((r['f'] >> 4) & 3)]
        return {'item': r['e'] & 0x1F, 'x': spot & 0xF0, 'y': (spot & 0x0F) << 4, 'at': r['e_at'],
                'hidden': (r['f'] & 7) in self.HIDES_ITEM}

    def action(self, level: int, quest: int, room: int) -> dict:
        r = self.room(level, quest, room)
        return {'action': r['f'] & 7, 'at': r['f_at']}

    def item_name(self, item: int) -> str:
        return self.ITEMS.get(item, f'Item {item:#04x}')

    # ---- overworld screens: layout (bank 5 $AA04), entrances and secrets
    def squares(self, room: int, quest: int = 1) -> list:
        """The screen's 11 rows of 16 squares (square numbers, before the secret squares are drawn as what they hide)."""
        layout = self.room(0, quest, room)['d'] & 0x7F
        columns_at = self.word(5, 0x9F9C) + layout * 16
        pointers = [self.word(6, 0x9CD8 + 0x37 + 2 * k) for k in range(16)]   # copied to $6827
        grid = [[0] * 16 for _ in range(11)]
        for column in range(16):
            code = self.byte(5, columns_at + column)
            data, skip = pointers[code >> 4], code & 15
            i = -1
            while True:
                i += 1
                if self.byte(5, data + i) & 0x80:
                    skip -= 1
                    if skip < 0:
                        break
            rows, twice = [], False
            while len(rows) < 11:
                value = self.byte(5, data + i)
                rows.append(value & 0x3F)
                if value & 0x40:
                    twice = not twice
                    if twice:
                        continue
                i += 1
            for row in range(11):
                grid[row][column] = rows[row]
        return grid

    def entrances(self, room: int, quest: int = 1) -> list:
        out = []
        for row, line in enumerate(self.squares(room, quest)):
            for column, square in enumerate(line):
                if square == self.CAVE_SQUARE or square in self.SECRETS:
                    out.append({'square': square, 'column': column, 'row': row})
        return out

    def destination(self, room: int, quest: int = 1) -> int:
        return self.room(0, quest, room)['b'] >> 2

    def destination_name(self, value: int) -> str:
        if 1 <= value <= 9:
            return f'Level {value}'
        if 0x10 <= value < 0x10 + self.CAVES:
            cave = value - 0x10
            return f'Cave {cave + 1} ({self.cave_summary(cave)})'
        return f'Place {value:#04x}'

    def cave(self, cave: int) -> dict:
        start = self.table(0, 1, 4) + cave * 3
        return {'items': [self.rom[start + i] for i in range(3)], 'prices': [self.rom[start + 0x3C + i] for i in range(3)],
                'at': start, 'person': 0x6A + cave}

    def cave_summary(self, cave: int) -> str:
        items = [i & 0x3F for i in self.cave(cave)['items'] if i & 0x3F != self.NO_CAVE_ITEM]
        return ', '.join(self.item_name(i) for i in items) if items else 'no items'

    def cave_users(self, cave: int, quest: int = 1) -> list:
        return [room for room in range(128) if self.destination(room, quest) == 0x10 + cave and self.entrances(room, quest)]




# ---------------------------------------------------------------- watchers (they read the replayed game's 2 KB of RAM)
# $10 level, $EB room, $12 game mode (5 playing, $0B/$0C in a cave), $034E enemy count, $0350+ enemy types,
# $AB the room's item, $04CD the room's table F byte, $0422-$0424 the cave's items

class _RoomWatcher(Watcher):
    """Looks at the room a few frames after the game has set it up, the first time the walk is there."""
    every = 2
    SETTLE = 6

    def __init__(self, watch):
        self.w, self.seen, self.since = watch, None, 0

    def here(self, ram):
        w = self.w
        return ram[0x12] == 5 and ram[0x10] == w['level'] and ram[0xEB] == w['room']

    def see(self, ram, frame, run):
        if not self.here(ram):
            self.since = 0
            return False
        self.since += 1
        if self.since < self.SETTLE:
            return False
        self.seen = self.sample(ram)
        return True

    def sample(self, ram):
        return None


class _EnemyWatcher(_RoomWatcher):
    ALIASES = {0x4A: 0x49}              # the corner traps set themselves up as blade traps

    def sample(self, ram):
        return {'count': ram[0x34E], 'slots': [ram[0x350 + i] for i in range(8)]}

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return super().result()
        members = w['members']
        if not members:
            ok = seen['count'] == 0 or not any(seen['slots'])
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, the room now has no enemies.' if ok
                    else 'Played from the start, the room still has enemies.'}
        if 0x32 <= w['type'] < 0x62:
            ok = seen['slots'][0] in (w['type'], self.ALIASES.get(w['type']))
        else:
            ok = seen['count'] == len(members) and seen['slots'][:len(members)] == members
        found = ', '.join(f'{v:#04x}' for v in seen['slots'][:max(1, seen['count'])])
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the room now has {w["name"]}.' if ok
                else f'Played from the start, the room has enemy types {found}, not what was chosen.'}


class _ItemWatcher(_RoomWatcher):
    def sample(self, ram):
        return ram[0xAB]

    def result(self):
        if self.seen is None:
            return super().result()
        ok = self.seen == self.w['item']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the room now holds {self.w["name"]}.' if ok
                else f'Played from the start, the room holds item {self.seen:#04x}, not the one chosen.'}


class _ActionWatcher(_RoomWatcher):
    def sample(self, ram):
        return ram[0x4CD] & 7

    def result(self):
        if self.seen is None:
            return super().result()
        ok = self.seen == self.w['action']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game set the room up so that: {self.w["name"].lower()}.' if ok
                else f'Played from the start, the room is set up with action {self.seen}, not the one chosen.'}


class _DoorWatcher(Watcher):
    """A door edit: play the walk on the old and the new game and see whether Link goes through that side of the room."""
    compare = True
    every = 2
    STEP = {'north': -16, 'south': 16, 'west': -1, 'east': 1}

    def __init__(self, watch):
        self.w = watch
        self.runs = {}

    def see(self, ram, frame, run):
        w = self.w
        state = self.runs.setdefault(run, {'last': None, 'passed': False, 'been': False})
        if ram[0x12] == 5 and ram[0x10] == w['level']:
            room = ram[0xEB]
            if room == w['room']:
                state['been'] = True
            if state['last'] == w['room'] and room == w['room'] + self.STEP[w['side']]:
                state['passed'] = True
            state['last'] = room
        return False

    def result(self):
        w = self.w
        old = self.runs.get('original', {'passed': False, 'been': False})
        new = self.runs.get('changed', {'passed': False, 'been': False})
        if not new['been']:
            return super().result()
        side = w['side']
        if new['passed'] == w['passable'] and new['passed'] != old['passed']:
            return {'state': 'good', 'text': f'Played from the start, Link now goes through the {side} side of the room.' if new['passed']
                    else f'Played from the start, Link is now stopped at the {side} side of the room, where he went through before.'}
        if new['passed'] == old['passed'] == w['passable']:
            return {'state': 'warn', 'text': f"The recorded walk doesn't try the {side} side of the room, so the new door couldn't be watched in the game. Use Play from here to try it."}
        return {'state': 'bad', 'text': f'Played from the start, Link {"goes through" if new["passed"] else "is stopped at"} the {side} side of the room, not what the new door should do.'}


class _CaveWatcher(Watcher):
    """An entrance or cave edit: wait until the walk goes in from that screen, then look where it went."""
    every = 2

    def __init__(self, watch):
        self.w, self.seen, self.inside, self.was = watch, None, 0, None

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x10] == 0 and ram[0xEB] == w['room'] and ram[0x12] in (0x0B, 0x0C):
            self.inside += 1
            if w['kind'] == 'dest' and ram[0x350] >= 0x6A:
                self.seen = {'cave': ram[0x350] - 0x6A}
                return True
            if w['kind'] == 'cave' and self.inside > 120 and any(ram[0x422 + i] for i in range(3)):
                self.seen = {'items': [ram[0x422 + i] for i in range(3)]}
                return True
        elif w['kind'] == 'dest' and ram[0x10] and ram[0x12] == 5 and self.was == w['room']:
            self.seen = {'level': ram[0x10]}
            return True
        if ram[0x10] == 0 and ram[0x12] == 5:
            self.was = ram[0xEB]
        return False

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return {'state': 'warn', 'text': "The recorded walk doesn't go in at this entrance, so the change couldn't be watched in the game. Use Play from here to try it."}
        if w['kind'] == 'dest':
            got = seen['level'] if 'level' in seen else 0x10 + seen['cave']
            ok = got == w['dest']
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the entrance now leads to {w["name"]}.' if ok
                    else 'Played from the start, the entrance leads somewhere else.'}
        ok = [i & 0x3F for i in seen['items']] == [i & 0x3F for i in w['items']]
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the cave now offers {w["name"]}.' if ok
                else 'Played from the start, the cave offers something else.'}


class Zelda1Profile(Zelda1, Profile):
    """The Legend of Zelda on the common profile interface. Parts are {'level', 'quest'}; x and y are pixels of the
    level's 16 x 8 room grid, laid out the way the map recorder stitches them."""
    sha256s = (Zelda1.sha256,)
    # the map recorder lays screens out by the console's scroll: 256 across, and 240 down (a whole screen of the
    # console's background, of which the room shows 176 lines), measured on recorded maps
    ROOM_W, ROOM_H = 256, 240
    TOP = 56                            # screen line (of the 224 the engine shows) where the room starts

    def where(self, ram):
        """Playing ($12 = 5), or just arrived ($12 = 4, measured on recorded captures): the camera is on room $EB. Scrolling sideways to the next room ($12 = 7, step $13 >= 3,
        Link facing $98 right or left): $EB is already the new room, and the console's scroll ($FD, nametable bit 0
        of $FF) runs from the old room's nametable to the new one's (right: new room in nametable 1). Other moments
        (the first steps of a scroll, scrolling up or down, caves, menus) are not placed."""
        room = ram[0xEB]
        x = (room & 15) * self.ROOM_W
        if ram[0x12] == 7 and ram[0x13] >= 3 and ram[0x98] in (1, 2):
            x += (ram[0xFF] & 1) * 256 + ram[0xFD] - (256 if ram[0x98] == 1 else 0)
        elif ram[0x12] not in (4, 5):        # 4: the moment a move to a new room has finished
            return None
        quest = 2 if ram[0x62D + (ram[0x16] % 3)] else 1
        return {'part': {'level': ram[0x10], 'quest': quest}, 'x': x, 'y': (room >> 4) * self.ROOM_H}

    def part_name(self, part):
        name = 'Overworld' if not part['level'] else f'Level {part["level"]}'
        return name + (', second quest' if part.get('quest') == 2 else '')

    # ---- places on the map (x, y: the bottom middle of the thing, in part pixels)
    def _spot(self, room, x, y):
        """Room pixels (x across, y the line of the screen the engine shows) to part pixels."""
        return (room & 15) * self.ROOM_W + x, (room >> 4) * self.ROOM_H + y

    def _level_types(self, level):
        """Enemy types the rooms of this level use (either quest; for the overworld, its own screens)."""
        found = set()
        for quest in (1, 2):
            for room in self.rooms(level, quest):
                kind = self.enemy(level, quest, room)['type']
                if kind:
                    found.add(kind)
        return sorted(found)

    def _type_name(self, kind):
        if kind >= 0x62:
            names = []
            for member in self.members(kind, 8):
                if member and self.enemy_name(member) not in names:
                    names.append(self.enemy_name(member))
            return 'Mixed: ' + ', '.join(names)
        return self.enemy_name(kind)

    def choices(self):
        out = {'items': [{'value': k, 'name': 'No item' if k == self.NO_ITEM else self.item_name(k)}
                         for k in range(0x20) if k in self.ITEMS],
               'cave_items': [{'value': self.NO_CAVE_ITEM, 'name': 'Nothing'}] + [{'value': k, 'name': v} for k, v in self.ITEMS.items()],
               'doors': [{'value': k, 'name': v} for k, v in self.DOORS.items()],
               'actions': [{'value': k, 'name': v} for k, v in self.ACTIONS.items()]}
        dests = sorted({self.destination(room) for room in range(128) if self.entrances(room)})
        out['destinations'] = [{'value': d, 'name': self.destination_name(d)} for d in dests]
        for level in range(10):
            kinds = self._level_types(level)
            names = [self._type_name(k) for k in kinds]
            out[f'enemies_{level}'] = [{'value': k, 'name': n + (f' (type {k:#04x})' if names.count(n) > 1 else '')}
                                       for k, n in zip(kinds, names)]
            for quest in (1, 2):
                out[f'counts_{level}_{quest}'] = [{'value': i, 'name': str(n)} for i, n in enumerate(self.counts(level, quest))]
        return out

    def objects(self, part):
        level, quest = int(part['level']), int(part.get('quest', 1))
        out = []
        for room in self.rooms(level, quest):
            out += self._room_objects(level, quest, room)
        return out

    @staticmethod
    def _room_label(level, room):
        return f'room {room:#04x}' if level else f'screen {room:#04x}'

    def _room_objects(self, level, quest, room):
        out = []
        tag = f'{room:02X}'
        where = self._room_label(level, room)
        e = self.enemy(level, quest, room)
        cx, cy = self._spot(room, 128, self.TOP + 96)
        if e['type'] or level:
            row = {'id': f'enemy:{tag}', 'style': 'enemy', 'type': e['members'][0] if e['members'] else 0, 'x': cx, 'y': cy,
                   'name': self.group_name(e['type'], e['count']) if e['type'] else 'No enemies',
                   'detail': f'enemies of {where}', 'remove': 'Remove the enemies' if e['type'] else None,
                   'note': 'The game places them when the room starts; the box marks the room, not where they stand.',
                   'fields': [{'key': 'enemy', 'label': 'Enemy', 'value': e['type'], 'choices': f'enemies_{level}'},
                              {'key': 'count', 'label': 'How many', 'value': e['count_index'], 'choices': f'counts_{level}_{quest}'}]}
            if 0x32 <= e['type'] < 0x62:
                row['note'] += ' The game always makes this one of a kind, whatever the count.'
            if e['c_at'] is None or e['d_at'] is None:
                row['fields'], row['remove'] = [], None
                row['note'] += ' The game sets this screen up in its code for the second quest, so it is shown but not changed here.'
            out.append(row)
        if level == 0:
            return out + self._entrance_objects(quest, room)
        it = self.item(level, quest, room)
        if it['item'] != self.NO_ITEM:
            x, y = self._spot(room, it['x'] + 8, it['y'] + 8)
            row = {'id': f'item:{tag}', 'style': 'item', 'type': 0x100 + it['item'], 'x': x, 'y': y,
                   'name': self.item_name(it['item']), 'detail': f'item of {where}', 'remove': 'Remove the item',
                   'fields': [{'key': 'item', 'label': 'Item', 'value': it['item'], 'choices': 'items'}]}
            if it['hidden']:
                row['note'] = 'It is hidden until this happens: ' + self.ACTIONS[self.action(level, quest, room)['action']].lower() + '.'
            out.append(row)
        for door in self.doors(level, quest, room):
            x, y = {'north': (128, self.TOP + 32), 'south': (128, self.TOP + 176), 'west': (16, self.TOP + 104),
                    'east': (240, self.TOP + 104)}[door['side']]
            x, y = self._spot(room, x, y)
            out.append({'id': f'door:{tag}:{door["side"]}', 'style': 'block', 'type': 0x200 + door['type'], 'x': x, 'y': y,
                        'name': self.DOORS[door['type']], 'detail': f'{door["side"]} side of {where}', 'remove': None,
                        'note': 'The room on the other side has its own door here; change both to keep the way the same from both sides.',
                        'fields': [{'key': 'door', 'label': 'Door', 'value': door['type'], 'choices': 'doors'}]})
        act = self.action(level, quest, room)
        x, y = self._spot(room, 128, self.TOP + 64)
        row = {'id': f'action:{tag}', 'style': 'secret', 'type': 0x300 + act['action'], 'x': x, 'y': y,
               'name': self.ACTIONS[act['action']], 'detail': f'what happens in {where}', 'remove': None,
               'fields': [{'key': 'action', 'label': 'In this room', 'value': act['action'], 'choices': 'actions'}]}
        notes = []
        if room in self.stair_rooms(level, quest):
            notes.append('This room is reached by stairs.')
        if room == self.start_room(level, quest):
            notes.append('The level starts in this room.')
        if room == self.boss_room(level, quest):
            notes.append('This is the boss room.')
        if notes:
            row['note'] = ' '.join(notes)
        out.append(row)
        return out

    def _entrance_objects(self, quest, room):
        out = []
        r = self.room(0, quest, room)
        dest, gate = r['b'] >> 2, r['f'] >> 6
        for number, ent in enumerate(self.entrances(room, quest)):
            x, y = self._spot(room, ent['column'] * 16 + 8, self.TOP + ent['row'] * 16 + 16)
            secret = ent['square'] in self.SECRETS
            row = {'id': f'entrance:{room:02X}:{number}', 'style': 'secret' if secret else 'block', 'type': 0x400 + ent['square'],
                   'x': x, 'y': y, 'name': self.SECRETS[ent['square']] if secret else 'Cave entrance',
                   'detail': f'leads to {self.destination_name(dest)}', 'remove': None,
                   'fields': [{'key': 'dest', 'label': 'Leads to', 'value': dest, 'choices': 'destinations'}]}
            notes = []
            if secret and gate in (1, 2):
                notes.append(f'This secret is only there in the {"first" if gate == 1 else "second"} quest.')
            if 0x10 <= dest < 0x10 + self.CAVES:
                users = self.cave_users(dest - 0x10, quest)
                items = self.cave(dest - 0x10)['items']
                if users == [room] and quest == 1:
                    for slot in range(3):
                        row['fields'].append({'key': f'item{slot + 1}', 'label': f'Cave item {slot + 1}',
                                              'value': items[slot] & 0x3F, 'choices': 'cave_items'})
                elif len(users) > 1:
                    notes.append(f'{len(users)} entrances lead to this cave, so what it holds is changed here by pointing '
                                 'this entrance at another cave.')
            if r['b_at'] is None:
                row['fields'] = []
                notes.append('The game sets this screen up in its code for the second quest, so it is shown but not changed here.')
            if notes:
                row['note'] = ' '.join(notes)
            out.append(row)
        return out

    # ---- edits
    def edit(self, part, object_id, values, remove=False):
        level, quest = int(part['level']), int(part.get('quest', 1))
        kind, _, rest = object_id.partition(':')
        room = int(rest.split(':')[0], 16)
        if room not in self.rooms(level, quest):
            raise ValueError('That room is not part of this level.')
        r = self.room(level, quest, room)
        where = self._room_label(level, room)

        def write(offset, new):
            if offset is None:
                raise ValueError('The game sets that in its code for the second quest, so ROMancer leaves it alone.')
            return [(offset, self.rom[offset], new & 0xFF)] if self.rom[offset] != new & 0xFF else []

        def own(ok):
            if not ok:
                raise ValueError('That choice is not one of the game’s own.')

        if kind == 'enemy':
            e = self.enemy(level, quest, room)
            new_type = 0 if remove else int(values.get('enemy', e['type']))
            index = e['count_index'] if values.get('count') is None else int(values['count'])
            own(0 <= new_type < 0x80 and 0 <= index < 4)
            writes = write(e['c_at'], (new_type & 0x3F) | index << 6)
            writes += write(e['d_at'], (e['d'] & 0x7F) | (0x80 if new_type & 0x40 else 0))
            count = self.group_count(level, quest, new_type, index)
            name = self.group_name(new_type, count) if new_type else 'no enemies'
            return {'writes': writes, 'title': f'Enemies of {where}: {name}',
                    'watch': {'kind': 'enemy', 'level': level, 'room': room, 'type': new_type,
                              'members': self.members(new_type, count), 'name': name}}
        if kind == 'item':
            item = self.NO_ITEM if remove else int(values.get('item'))
            own(item in self.ITEMS and item < 0x20)
            name = 'no item' if item == self.NO_ITEM else self.item_name(item)
            return {'writes': write(r['e_at'], (r['e'] & 0xE0) | item), 'title': f'Item of {where}: {name}',
                    'watch': {'kind': 'item', 'level': level, 'room': room, 'item': item, 'name': name}}
        if kind == 'door':
            side = rest.split(':')[1]
            door = next(d for d in self.doors(level, quest, room) if d['side'] == side)
            new = int(values.get('door'))
            own(new in self.DOORS)
            key = 'a' if side in ('north', 'south') else 'b'
            value = (r[key] & ~(7 << door['shift']) & 0xFF) | new << door['shift']
            return {'writes': write(r[key + '_at'], value), 'title': f'{side.capitalize()} door of {where}: {self.DOORS[new]}',
                    'watch': {'kind': 'door', 'level': level, 'room': room, 'side': side, 'type': new, 'passable': new in self.PASSABLE}}
        if kind == 'action':
            new = int(values.get('action'))
            own(new in self.ACTIONS)
            return {'writes': write(r['f_at'], (r['f'] & 0xF8) | new), 'title': f'In {where}: {self.ACTIONS[new].lower()}',
                    'watch': {'kind': 'action', 'level': level, 'room': room, 'action': new, 'name': self.ACTIONS[new]}}
        if kind == 'entrance':
            dest = r['b'] >> 2
            writes, watch, title = [], None, ''
            new_dest = int(values['dest']) if values.get('dest') is not None else dest
            if new_dest != dest:
                own(1 <= new_dest <= 9 or 0x10 <= new_dest < 0x10 + self.CAVES)
                writes += write(r['b_at'], (r['b'] & 3) | new_dest << 2)
                title = f'Entrance on {where} leads to {self.destination_name(new_dest)}'
                watch = {'kind': 'dest', 'room': room, 'dest': new_dest, 'name': self.destination_name(new_dest)}
            slots = [values.get(f'item{k + 1}') for k in range(3)]
            if any(v is not None for v in slots):
                cave = self.cave(dest - 0x10) if 0x10 <= dest < 0x10 + self.CAVES else None
                items = list(cave['items']) if cave else []
                for k, v in enumerate(slots):
                    if v is not None and cave and (int(v) & 0x3F) != (items[k] & 0x3F):
                        if quest != 1 or self.cave_users(dest - 0x10, quest) != [room]:
                            raise ValueError('Several entrances share this cave, so point this entrance at another cave instead.')
                        own(int(v) == self.NO_CAVE_ITEM or int(v) in self.ITEMS)
                        items[k] = (items[k] & 0xC0) | int(v)
                if cave and items != cave['items']:
                    if watch:
                        raise ValueError('Change where the entrance leads and what the cave holds one at a time.')
                    writes += [(cave['at'] + k, cave['items'][k], items[k]) for k in range(3) if items[k] != cave['items'][k]]
                    names = ', '.join(self.item_name(i & 0x3F) for i in items if i & 0x3F != self.NO_CAVE_ITEM) or 'nothing'
                    title = f'Cave on {where} holds: {names}'
                    watch = {'kind': 'cave', 'room': room, 'cave': dest - 0x10, 'items': items, 'name': names}
            if watch is None:
                raise ValueError('That is how the game already has it.')
            return {'writes': writes, 'title': title, 'watch': watch}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        return {'enemy': _EnemyWatcher, 'item': _ItemWatcher, 'action': _ActionWatcher, 'door': _DoorWatcher,
                'dest': _CaveWatcher, 'cave': _CaveWatcher}[watch['kind']](watch)


PROFILES = [Zelda1Profile]
