"""The Legend of Zelda (USA) (Rev 1) and Zelda II - The Adventure of Link (USA): level profiles.

Everything here was read from the games' own code and tables and checked by replaying the games (research notes in
research/zelda-level-profile.md). Zelda shows its world one screen at a time; a part of the game is the overworld or one
dungeon (with its quest), and its pixels are the screens laid out on the game's own 16 x 8 room grid, so the screens the
map recorder stitches together line up with the rooms they show. Zelda II's parts are its side-view scenes (towns,
palaces, caves, encounter scenes), each one area of up to four screens across.
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
    # trace/v15_profiles/zelda/sheet_ow.png, sheet_dg*.png, sheet_re.png, and trace/v15_profiles/naming_zelda_smb2/z1/);
    # two of a kind are told apart by what they were seen doing (z1_track.py: speeds, Gleeok heads, Patra eyes)
    ENEMIES = {0x01: 'Blue Lynel', 0x02: 'Red Lynel', 0x03: 'Blue Moblin', 0x04: 'Red Moblin', 0x05: 'Blue Goriya',
               0x06: 'Red Goriya', 0x07: 'Red Octorok, slow', 0x08: 'Red Octorok, fast', 0x09: 'Blue Octorok, slow',
               0x0A: 'Blue Octorok, fast', 0x0B: 'Red Darknut', 0x0C: 'Blue Darknut', 0x0D: 'Blue Tektite',
               0x0E: 'Red Tektite', 0x0F: 'Blue Leever', 0x10: 'Red Leever', 0x12: 'Vire', 0x13: 'Zol', 0x15: 'Gel',
               0x16: 'Pols Voice', 0x17: 'Like Like', 0x18: 'Green hopper drawn with the wrong tiles',
               0x1A: 'Peahat', 0x1B: 'Blue Keese', 0x1D: 'Black Keese',
               0x1F: 'Falling rocks', 0x21: 'Ghini', 0x23: 'Blue Wizzrobe', 0x24: 'Red Wizzrobe', 0x27: 'Wallmaster',
               0x28: 'Rope', 0x29: 'Nothing that shows', 0x2A: 'Stalfos', 0x2B: 'Bubble', 0x2C: 'Blue Bubble',
               0x2D: 'Red Bubble', 0x2F: 'Fairy',
               0x30: 'Gibdo', 0x31: 'Dodongo', 0x32: 'Dodongo (one)', 0x33: 'Blue Gohma', 0x34: 'Red Gohma',
               0x35: 'Ring of rupees', 0x36: 'Hungry Goriya', 0x37: 'Old man', 0x38: 'Digdogger',
               0x39: 'Digdogger (one)', 0x3A: 'Red Lanmola', 0x3B: 'Blue Lanmola', 0x3C: 'Manhandla',
               0x3D: 'Aquamentus', 0x3E: 'Ganon', 0x3F: 'Fire', 0x41: 'Moldorm', 0x42: 'Gleeok with one head',
               0x43: 'Gleeok with two heads', 0x44: 'Gleeok with three heads', 0x45: 'Gleeok with four heads',
               0x47: 'Patra, eyes circle close', 0x48: 'Patra, eyes swing wide', 0x49: 'Blade trap',
               0x4A: 'Blade traps in the corners',
               0x4B: 'Old man (hint about Dodongo)', 0x4C: 'Old man (hint about the eastmost peninsula)',
               0x4D: 'Old man (hint about the eyes of Gohma)', 0x4E: 'Old man (hint about the waterfall)',
               0x4F: 'Old man who gives or takes rupees', 0x50: 'Old man (hint about the tip of the nose)',
               0x51: 'Old man who asks for life or money', 0x52: 'Old man (hint about the arrow)'}
    # what each one does, from watching it for six seconds with Link standing at the door (z1_track.py: positions of
    # every enemy slot each frame and the shots that appeared)
    _PERSON = 'Stands still between two fires.'
    DOES = {0x01: 'Walks about slowly and shoots sword beams.', 0x02: 'Walks about slowly and shoots sword beams.',
            0x03: 'Walks about and throws spears.', 0x04: 'Walks about and throws spears.',
            0x05: 'Walks about and throws boomerangs.', 0x06: 'Walks about and throws boomerangs.',
            0x07: 'Walks about slowly and spits rocks.', 0x08: 'Walks about quickly and spits rocks.',
            0x09: 'Walks about slowly and spits rocks.', 0x0A: 'Walks about quickly and spits rocks.',
            0x0B: 'Walks about the room.', 0x0C: 'Walks about the room a little faster.',
            0x0D: 'Jumps about now and then.', 0x0E: 'Jumps about all the time.',
            0x0F: 'Comes up out of the sand and wanders about.',
            0x10: 'Comes up out of the sand near Link and sinks again.',
            0x12: 'Bounces about in hops.', 0x13: 'Creeps slowly about the room.', 0x15: 'Creeps about the room.',
            0x16: 'Hops about the room.', 0x17: 'Walks slowly about the room.',
            0x18: 'Stays still most of the time and now and then jumps a short way.',
            0x1A: 'Flies about in loops.', 0x1B: 'Flutters about the room.', 0x1D: 'Flutters quickly about the room.',
            0x1F: 'Rocks fall and bounce down the screen.', 0x21: 'Floats about the screen.',
            0x23: 'Walks about and vanishes from place to place.', 0x24: 'Appears near Link and shoots magic.',
            0x27: 'Stays hidden in the walls while Link keeps away from them.', 0x28: 'Walks about the room.',
            0x29: 'Nothing appears and nothing moves.', 0x2A: 'Walks about the room.',
            0x2B: 'Flies quickly about the room.', 0x2C: 'Flies quickly about the room.',
            0x2D: 'Flies quickly about the room.', 0x2F: 'Hovers in one place.', 0x30: 'Walks about the room.',
            0x31: 'Walks back and forth.', 0x32: 'Walks back and forth.',
            0x33: 'Moves along the top of the room and fires from its eye.',
            0x34: 'Moves along the top of the room and fires from its eye.',
            0x35: 'Rupees appear in a ring around Link.', 0x36: 'Stands still and blocks the way.', 0x37: _PERSON,
            0x38: 'Drifts about the room.', 0x39: 'Drifts about the room.',
            0x3A: 'Crawls about the room as a long body.', 0x3B: 'Crawls quickly about the room as a long body.',
            0x3C: 'Moves about the room and shoots fireballs.', 0x3D: 'Walks back and forth and shoots fireballs.',
            0x3E: 'Waits at the top of the room.', 0x3F: 'Burns in one place.', 0x41: 'Crawls about the room.',
            0x42: 'Stays at the top of the room and swings its head.',
            0x43: 'Stays at the top of the room, swings its heads and spits fire.',
            0x44: 'Stays at the top of the room, swings its heads and spits fire.',
            0x45: 'Stays at the top of the room, swings its heads and spits fire.',
            0x47: 'Flies about with eight eyes circling close around it.',
            0x48: 'Flies about with eight eyes swinging far out and back.',
            0x49: 'Waits in place and slides out at Link.', 0x4A: 'Wait in the corners and slide out at Link.',
            0x4B: _PERSON, 0x4C: _PERSON, 0x4D: _PERSON, 0x4E: _PERSON, 0x4F: _PERSON, 0x50: _PERSON,
            0x51: _PERSON, 0x52: _PERSON}
    # item numbers (caves and dungeons share them), named by placing each one and looking at it
    # (trace/v15_profiles/zelda/items_crop.png, sheet_shop.png)
    ITEMS = {0x00: 'Bombs', 0x01: 'Wooden sword', 0x02: 'White sword', 0x03: 'Magical sword', 0x04: 'Bait',
             0x05: 'Recorder', 0x06: 'Blue candle', 0x07: 'Red candle', 0x08: 'Arrow', 0x09: 'Silver arrow',
             0x0A: 'Bow', 0x0B: 'Magic key', 0x0C: 'Raft', 0x0D: 'Stepladder', 0x0F: '5 rupees', 0x10: 'Magic rod',
             0x11: 'Book of magic', 0x12: 'Blue ring', 0x13: 'Red ring', 0x14: 'Power bracelet', 0x15: 'Letter',
             0x16: 'Compass', 0x17: 'Map', 0x18: 'Rupee', 0x19: 'Key', 0x1A: 'Heart container',
             0x1B: 'Triforce piece', 0x1C: 'Magic shield', 0x1D: 'Boomerang', 0x1E: 'Magic boomerang',
             0x1F: 'Blue potion', 0x20: 'Red potion', 0x21: 'Clock', 0x22: 'Heart', 0x23: 'Fairy'}
    # named but not offered as a choice: the Triforce of Power, only in Ganon's room (placed in level 9's start room
    # and looked at: trace/v15_profiles/naming_zelda_smb2/z1/item0e_42.png); elsewhere the game draws it as garbage
    SHOWN_ITEMS = {0x0E: 'Triforce of Power'}
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
        return self.ITEMS.get(item, self.SHOWN_ITEMS.get(item, f'Item {item:#04x}'))

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
            kinds = {m for m in e['members'] if m}
            if len(kinds) == 1 and next(iter(kinds)) in self.DOES:
                row['does'] = self.DOES[next(iter(kinds))]
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


# ================================================================ Zelda II - The Adventure of Link (USA)

class Zelda2:
    """Zelda II - The Adventure of Link (USA). MMC1, 8 banks of 16 KB (bank 7 fixed at $C000).

    Side-view scenes ("areas") come in sets, one per bank of scene data (bank 7 $C4B7 picks the bank by world $0707;
    world 0 picks bank 1 or 2 by region $0706, and region 1 by the region Link came from, $070A). Each set has 63 areas:
    layout pointers at $8523 + 2 * area and enemy list pointers at $85A1 + 2 * area in the set's bank ($A000/$A07E
    for world 0 region 1, bank 7 $C4FE). Enemy list pointers are cartridge RAM addresses: bank 7 $CD9A copies the
    bank's $88A0-$8C9F to $7000-$73FF when a world is loaded.

    Enemy list: a length byte, then two bytes per enemy (bank 7 $D625): first byte bit 7 = already placed (the game
    sets it when it places the enemy and skips entries that have it), bits 4-6 = height (row of the table at bank 7
    $D5FB), bits 0-3 = column; second byte bits 6-7 = screen, bits 0-5 = type. The game places an entry when its
    screen comes into view; the slot remembers the entry's offset in $BC. In random encounters ($075A = 1 small, 2
    big monster touched on the map) bit 7 is cleared on entry (bank 7 $C554), and a big monster's encounter uses the
    list that follows the area's own list ($C53E).

    Layout: a length byte, three header bytes, then objects of two bytes (position, kind); kind $0F carries a third
    byte, an item ($C8F6 -> $C9A5: the item is placed at column x * 16 + 3 of its screen, line (y * 16) + $20, unless
    the per-area collected flags in RAM $0600+ (bank 7 $C2A6) say it was taken). Position $Dx changes the floor,
    $Ex jumps to screen x & 3.
    """
    name = 'Zelda II - The Adventure of Link'
    sha256 = '9fca03064a5113e6a92f550d9f42bac9ac1ae248a84df1f653d7cd7f76a1803d'
    BANKS = 8
    AREAS = 63
    # set: (name, bank, alternate tables)
    SETS = {0: ('West Hyrule', 1, False), 1: ('Death Mountain', 1, True), 2: ('East Hyrule', 2, False),
            3: ('Maze Island', 2, True), 4: ('Towns', 3, False), 5: ('Palaces', 4, False), 6: ('Great Palace', 5, False)}
    ENCOUNTER_SETS = {0, 1, 2, 3}       # world 0: the only sets with random encounters
    HEIGHTS_AT = 0xD5FB                 # bank 7: enemy line by the entry's height
    # items, named by placing each one and looking at it (trace/v15_profiles/zelda/z2/z2_items_crop.png) and by the
    # pickup code (bank 7 $E771): 0-7 set inventory flags $0785 + n, 8 adds a key ($0793), $0A-$0D give experience
    # through the table at $E7E6 + n (classes 7, 9, $0B, $0D of the experience table $DDC0/$DDDC: 50, 100, 200, 500),
    # $0E/$0F raise the magic and heart containers ($0783/$0784), $10/$11 refill magic ($05E2: a little / all),
    # $12 adds a life ($0700); $13-$15 set quest flags and keep their number
    ITEMS = {0x00: 'Candle', 0x01: 'Glove', 0x02: 'Raft', 0x03: 'Boots', 0x04: 'Flute', 0x05: 'Cross', 0x06: 'Hammer',
             0x07: 'Magic key', 0x08: 'Key', 0x0A: 'P-bag (50 points)',
             0x0B: 'P-bag (100 points)', 0x0C: 'P-bag (200 points)', 0x0D: 'P-bag (500 points)',
             0x0E: 'Magic container', 0x0F: 'Heart container', 0x10: 'Blue magic jar', 0x11: 'Red magic jar',
             0x12: 'Doll (extra life)', 0x13: 'Kidnapped child', 0x14: 'Trophy', 0x15: 'Water of Life'}
    SHOWN_ITEMS = {0x09: 'Unused glove picture'}         # named, not offered: the pickup code has no case for it
    # what picking an item up does, from the pickup code at bank 7 $E771
    ITEM_DOES = {**{k: 'Adds it to Link\'s items.' for k in range(8)}, 0x08: 'Adds a key.',
                 0x09: 'Nothing: the pickup code has no case for it.',
                 0x0A: 'Gives 50 experience points.', 0x0B: 'Gives 100 experience points.',
                 0x0C: 'Gives 200 experience points.', 0x0D: 'Gives 500 experience points.',
                 0x0E: 'Adds a magic container.', 0x0F: 'Adds a heart container.', 0x10: 'Refills some magic.',
                 0x11: 'Refills all magic.', 0x12: 'Gives an extra life.', 0x13: 'Marks a quest step as done.',
                 0x14: 'Marks a quest step as done.', 0x15: 'Marks a quest step as done.'}
    # enemy types per bank of scene data, named by placing each type in a scene and looking at what the game drew
    # (trace/v15_profiles/zelda/z2/names_*.png; trace/v15_profiles/naming_zelda_smb2/z2/view_*.png and crops_*.png:
    # every entry of one list set to the type, Link walking in from the left). Descriptive names say what the picture
    # shows; "Unseen" types drew nothing in the test scene. Banks 1 and 2 run the same enemy code (bank bytes
    # $8109-$8505 and $A0FC-$BFFF are the same), so East Hyrule and Maze Island use West Hyrule's names.
    _OUTDOORS = {0x00: 'Fairy', 0x01: 'Item lying in the scene', 0x03: 'Black beetle', 0x04: 'Blue slime',
                 0x05: 'Red slime', 0x06: 'Red flying eye', 0x07: 'Blue spiked crawler', 0x0A: 'Red spiked crawler',
                 0x0B: 'Unseen enemy', 0x0C: 'Red ball', 0x0D: 'Red spider', 0x0E: 'Blue spider',
                 0x0F: 'Sender of small flyers', 0x11: 'Red octopus', 0x12: 'Red octopus that spits rocks',
                 0x14: 'Orange spear soldier', 0x15: 'Red pig-faced soldier', 0x16: 'Blue pig-faced soldier',
                 0x17: 'Orange club thrower', 0x18: 'Dark pig-faced soldier', 0x19: 'Orange lizard soldier',
                 0x1A: 'Red lizard soldier', 0x1B: 'Blue lizard soldier', 0x1C: 'Blue grass creatures',
                 0x1D: 'Blue grass creature', 0x1F: 'Blue grass creature that jumps', 0x20: 'White column creature',
                 0x21: 'Unseen sender'}
    ENEMIES = {
        1: _OUTDOORS,
        2: _OUTDOORS,
        3: {0x06: 'Purple flying eye', 0x0A: 'Red bat', 0x0B: 'Purple slime', 0x0C: 'Unseen townsperson',
            0x0D: 'Old woman (purple)', 0x0E: 'Man (purple)', 0x0F: 'Wizard (the screen flashes red)', 0x10: 'Child',
            0x11: 'Woman (purple dress)', 0x12: 'Man (red)', 0x14: 'Door (kind 0x14)', 0x15: 'Door (kind 0x15)',
            0x16: 'Door (kind 0x16)', 0x17: 'Woman (red dress)', 0x18: 'Old woman (orange)',
            0x1D: 'Unseen walker', 0x1E: 'Unseen walker', 0x1F: 'Unseen walker', 0x20: 'Unseen walker',
            0x21: 'Unseen townsperson', 0x22: 'Unseen townsperson', 0x23: 'Woman with dark hair (purple dress)'},
        4: {0x00: 'Fairy', 0x03: 'Dark blue beetle', 0x04: 'Blue slime', 0x05: 'Unseen enemy',
            0x06: 'Floating skull, slow', 0x07: 'Orange flying head', 0x08: 'Unseen enemy', 0x0A: 'Unseen enemy',
            0x0B: 'Unseen enemy', 0x0C: 'Red horned creature', 0x0D: 'Red face block',
            0x0E: 'Floating skull, fast', 0x0F: 'Sender of small flyers', 0x11: 'Blue snake',
            0x12: 'Blue snake that spits fire', 0x14: 'Unseen dripper', 0x16: 'Unseen enemy',
            0x17: 'Bouncing blue orb', 0x18: 'Orange armored knight', 0x19: 'Red armored knight',
            0x1A: 'Blue armored knight', 0x1B: 'Unseen enemy', 0x1D: 'Flame', 0x1E: 'Red ogre that throws',
            0x1F: 'Red skeleton', 0x20: 'Red wolf-headed knight', 0x21: 'Big blue armored knight',
            0x23: 'Blue skeleton'},
        5: {0x00: 'Fairy', 0x03: 'Blue beetle', 0x04: 'Blue slime', 0x05: 'Unseen enemy',
            0x0F: 'Sender of small flyers', 0x11: 'Red hopping creature', 0x14: 'Floating skull, bounces',
            0x15: 'Floating skull, bounces fast', 0x16: 'Orange flying dragon head', 0x17: 'Masked flying creature',
            0x19: 'Red armored knight', 0x1A: 'Blue armored knight', 0x1D: 'Red ogre', 0x1E: 'Unseen enemy',
            0x20: 'Unseen enemy', 0x22: 'Thunderbird', 0x23: 'Unseen enemy'}}
    # what each one does, from its path over five seconds in the same scenes (z2_track.py, z2/track.log)
    _OUT_DOES = {0x00: 'Hovers in one place.', 0x01: 'Lies on the ground until picked up.',
                 0x03: 'Crawls slowly along the ground.', 0x04: 'Hops about on the ground.',
                 0x05: 'Hops slowly along the ground.', 0x06: 'Flies about in swoops.',
                 0x07: 'Hangs from above and drops down.', 0x0A: 'Hangs from above and drops down.',
                 0x0B: 'Stays where it is.', 0x0C: 'Stays where it is.', 0x0D: 'Drops from a tree and crawls.',
                 0x0E: 'Drops from a tree and crawls.', 0x0F: 'Sends small flyers across the screen.',
                 0x11: 'Jumps up and down in place.', 0x12: 'Walks about, jumps and spits rocks.',
                 0x14: 'Walks toward Link and throws spears.', 0x15: 'Walks toward Link and throws spears.',
                 0x16: 'Walks toward Link and throws spears.', 0x17: 'Walks toward Link and throws clubs.',
                 0x18: 'Walks toward Link and throws spears.', 0x19: 'Walks toward Link and attacks.',
                 0x1A: 'Walks toward Link and throws blades.', 0x1B: 'Walks toward Link and throws blades.',
                 0x1C: 'Crawl along the ground toward Link.', 0x1D: 'Crawls along the ground toward Link.',
                 0x1F: 'Jumps about quickly.', 0x20: 'Stands tall in one place.',
                 0x21: 'Sends out a red creature.'}
    DOES = {
        1: _OUT_DOES,
        2: _OUT_DOES,
        3: {0x06: 'Flies about in swoops.', 0x0A: 'Stays where it is.', 0x0B: 'Stays where it is.', 0x0C: 'Stays where it is.',
            0x0D: 'Stands in the town.', 0x0E: 'Stands in the town.', 0x0F: 'Stands still.',
            0x10: 'Stands in the town.', 0x11: 'Stands in the town.', 0x12: 'Stands in the town.',
            0x17: 'Walks about the town.', 0x18: 'Walks about the town.', 0x1D: 'Walks across the town.',
            0x1E: 'Walks across the town.', 0x1F: 'Walks across the town.', 0x20: 'Walks across the town.',
            0x21: 'Stays where it is.', 0x22: 'Stays where it is.', 0x23: 'Stands still.'},
        4: {0x00: 'Hovers in one place.', 0x03: 'Crawls along the floor.', 0x04: 'Hops about on the floor.',
            0x05: 'Stays where it is.', 0x06: 'Floats about the room.', 0x07: 'Flies about in waves.',
            0x08: 'Stays where it is.', 0x0A: 'Stays where it is.', 0x0B: 'Stays where it is.',
            0x0C: 'Runs quickly about the room.', 0x0D: 'Stays in place and lets blue slimes fall out.',
            0x0E: 'Floats quickly about the room.', 0x0F: 'Sends small flyers across the room.',
            0x11: 'Hops in place.', 0x12: 'Hops about and spits fire.', 0x14: 'Drips from the ceiling.',
            0x16: 'Stays where it is.', 0x17: 'Bounces about the room.', 0x18: 'Stands guard.',
            0x19: 'Stands guard.', 0x1A: 'Stands guard.', 0x1B: 'Stays where it is.',
            0x1D: 'Appears and vanishes from place to place.', 0x1E: 'Stands and throws at Link.',
            0x1F: 'Stands guard.', 0x20: 'Stands guard.', 0x21: 'Stands guard.',
            0x23: 'Stands guard.'},
        5: {0x00: 'Hovers in one place.', 0x03: 'Crawls along the floor.', 0x04: 'Hops about on the floor.',
            0x05: 'Stays where it is.', 0x0F: 'Sends small flyers across the room.',
            0x11: 'Hops in place and spits fire.', 0x14: 'Bounces up and down the room.',
            0x15: 'Bounces quickly up and down the room.', 0x16: 'Flies quickly across the room.',
            0x17: 'Flies up and down the room.', 0x19: 'Jumps about and attacks.',
            0x1A: 'Jumps about and attacks.', 0x1D: 'Hops about and attacks.',
            0x1E: 'Stays where it is.', 0x20: 'Stays where it is.', 0x22: 'Flies above the room.',
            0x23: 'Stays where it is.'}}

    def __init__(self, rom: bytes):
        self.rom = rom

    # ---- reading
    def at(self, bank, address):
        return _bank(self.BANKS, bank, address)

    def byte(self, bank, address):
        return self.rom[self.at(bank, address)]

    def word(self, bank, address):
        return self.byte(bank, address) | self.byte(bank, address + 1) << 8

    def tables(self, kind):
        name, bank, alt = self.SETS[kind]
        return bank, (0xA000, 0xA07E) if alt else (0x8523, 0x85A1)

    def list_offset(self, kind, address):
        """File offset of a cartridge RAM enemy list address ($7000-$73FF is the bank's $88A0-$8C9F)."""
        bank = self.SETS[kind][1]
        return self.at(bank, address - 0x7000 + 0x88A0)

    def layout_at(self, kind, area):
        bank, (layouts, lists) = self.tables(kind)
        return self.word(bank, layouts + 2 * area)

    def list_at(self, kind, area, strong=False):
        bank, (layouts, lists) = self.tables(kind)
        address = self.word(bank, lists + 2 * area)
        if strong:
            address += self.rom[self.list_offset(kind, address)]
        return address

    def enemies(self, kind, area, strong=False):
        """[{'k', 'at' (file offset of the entry's first byte), 'placed', 'height', 'column', 'screen', 'type'}]"""
        address = self.list_at(kind, area, strong)
        if not 0x7000 <= address < 0x7400:
            return []
        start = self.list_offset(kind, address)
        out = []
        for k, i in enumerate(range(1, self.rom[start] - 1, 2)):
            first, second = self.rom[start + i], self.rom[start + i + 1]
            out.append({'k': k, 'offset': i, 'at': start + i, 'placed': bool(first & 0x80), 'height': (first >> 4) & 7,
                        'column': first & 15, 'screen': second >> 6, 'type': second & 0x3F})
        return out

    def line(self, height):
        return self.byte(7, self.HEIGHTS_AT + height)

    def items(self, kind, area):
        """Item objects of the area's layout: [{'n', 'at' (file offset of the item byte), 'item', 'screen', 'column', 'row'}]"""
        bank = self.SETS[kind][1]
        start = self.at(bank, self.layout_at(kind, area))
        length = self.rom[start]
        out, i, x = [], 4, 0
        while i < length:
            pos, what = self.rom[start + i], self.rom[start + i + 1]
            if pos >> 4 == 0xE:
                x = (pos & 3) * 16
            elif pos >> 4 != 0xD:
                x += pos & 15
            if what == 0x0F and pos >> 4 != 0xD:
                out.append({'n': len(out), 'at': start + i + 2, 'item': self.rom[start + i + 2], 'screen': x >> 4,
                            'column': x & 15, 'row': pos >> 4})
                i += 3
            else:
                i += 2
        return out

    LOCATIONS = 62                      # map entrances of a region: bank $861F y, $865E x, $869D area, $86DC world
    LOCATION_AREAS, LOCATION_WORLDS = 0x869D, 0x86DC

    def entrance_areas(self, kind):
        """World-0 areas a map entrance of the set's own region leads to (West and East Hyrule only)."""
        bank = self.SETS[kind][1]
        return {self.byte(bank, self.LOCATION_AREAS + k) & 0x3F for k in range(self.LOCATIONS)
                if not (self.byte(bank, self.LOCATION_WORLDS + k) >> 2) & 7}

    def encounter_list(self, kind, area):
        """True when the area's big-monster list is shown: West or East Hyrule areas no map entrance leads to
        (random encounter scenes have no entrance of their own)."""
        return kind in (0, 2) and area not in self.entrance_areas(kind)

    def list_users(self, kind, address):
        """Areas of the set that use this enemy list: [(area, strong)]."""
        out = []
        for area in range(self.AREAS):
            if self.list_at(kind, area) == address:
                out.append((area, False))
            if self.encounter_list(kind, area) and self.list_at(kind, area, True) == address:
                out.append((area, True))
        return out

    def layout_users(self, kind, area):
        pointer = self.layout_at(kind, area)
        bank = self.SETS[kind][1]
        return [(k, a) for k in self.SETS if self.SETS[k][1] == bank for a in range(self.AREAS)
                if self.layout_at(k, a) == pointer]

    def enemy_name(self, kind, kind_type):
        names = self.ENEMIES.get(self.SETS[kind][1], {})
        return names.get(kind_type, f'Enemy {kind_type:#04x}')

    def item_name(self, item):
        return self.ITEMS.get(item & 0x7F, self.SHOWN_ITEMS.get(item & 0x7F, f'Item {item & 0x7F:#04x}'))

    def set_types(self, kind):
        found = set()
        for area in range(self.AREAS):
            for strong in ((False, True) if self.encounter_list(kind, area) else (False,)):
                for e in self.enemies(kind, area, strong):
                    found.add(e['type'])
        return sorted(found)


class _Z2Watcher(Watcher):
    """Watches one area of one set; `scene` gives (set, area) from the RAM like Zelda2Profile.where."""
    every = 2

    def __init__(self, watch):
        self.w = watch

    def here(self, ram):
        part = Zelda2Profile.part_of(ram)
        return part is not None and part == {'set': self.w['set'], 'area': self.w['area']} and \
            (not self.w.get('strong') or ram[0x75A] == 2) and (self.w.get('strong') or ram[0x75A] < 2)

    @staticmethod
    def camera(ram):
        return ram[0x72A] * 256 + ram[0x72C]


class _Z2EnemyWatcher(_Z2Watcher):
    """The slot the game fills from the entry ($BC = the entry's offset in its list) shows the chosen type; for a
    removed entry, the entry is in view or its screen and column reach an edge of the view ($0732/$0734 left,
    $0733/$0735 right, where the game places enemies) and no slot is filled from it in the next looks."""
    VIEW = 20                           # looks after the entry's column reached an edge of the screen

    def __init__(self, watch):
        super().__init__(watch)
        self.seen, self.viewed = None, 0

    def see(self, ram, frame, run):
        if not self.here(ram) or ram[0x736] != 0x0B:
            return False
        w = self.w
        for slot in range(6):
            if ram[0xB6 + slot] and ram[0xBC + slot] == w['offset'] and ram[0xA1 + slot] != 1:
                self.seen = ram[0xA1 + slot]
                return True
        edge = (ram[0x732], ram[0x734]), (ram[0x733], ram[0x735])    # screen and column at each edge ($D625)
        cam = self.camera(ram)
        if self.viewed or (w['screen'], w['column']) in edge or cam - 16 <= w['x'] < cam + 272:   # in view (or the next column): placed on entry
            self.viewed += 1
            if w['remove'] and self.viewed >= self.VIEW:
                return True
        return False

    def result(self):
        w = self.w
        if w['remove']:
            if self.seen is not None:
                return {'state': 'bad', 'text': f'Played from the start, the game still placed enemy type {self.seen:#04x} there.'}
            if self.viewed >= self.VIEW:
                return {'state': 'good', 'text': 'Played from the start, the game reached that spot and put no enemy there.'}
            return super().result()
        if self.seen is None:
            return super().result()
        ok = self.seen == w['type']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game placed {w["name"]} there.' if ok
                else f'Played from the start, the game placed enemy type {self.seen:#04x} there, not the one chosen.'}


class _Z2ItemWatcher(_Z2Watcher):
    """An item slot ($A1 = 1) at the item's screen and column holds the chosen item ($AF)."""

    def __init__(self, watch):
        super().__init__(watch)
        self.seen = None

    def see(self, ram, frame, run):
        if not self.here(ram) or ram[0x736] != 0x0B:
            return False
        w = self.w
        for slot in range(6):
            if ram[0xB6 + slot] and ram[0xA1 + slot] == 1 and ram[0x3C + slot] == w['screen'] and \
                    ram[0x4E + slot] == w['column'] * 16 + 3:
                self.seen = ram[0xAF + slot] & 0x7F
                return True
        return False

    def result(self):
        if self.seen is None:
            return super().result()
        ok = self.seen == self.w['item']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the scene now holds {self.w["name"]}.' if ok
                else f'Played from the start, the scene holds item {self.seen:#04x}, not the one chosen.'}


class Zelda2Profile(Zelda2, Profile):
    """Zelda II on the common profile interface. Parts are {'set', 'area'}: one side-view area of a set (see
    Zelda2.SETS); x is the camera ($072A screen, $072C pixel) and y the screen line."""
    sha256s = (Zelda2.sha256,)
    SCREEN_W = 256
    FEET = 24                           # lines from a figure's line ($2A) to its feet, measured on recorded maps

    @staticmethod
    def part_of(ram):
        """Side-view play ($0736 = $0B): the set from world $0707, region $0706 and the region Link came from
        $070A; the area is $0561."""
        if ram[0x736] != 0x0B:
            return None
        world, region = ram[0x707], ram[0x706]
        if world == 0:
            kind = {0: 0, 2: 2}.get(region, 3 if ram[0x70A] else 1)
        elif world in (1, 2):
            kind = 4
        elif world in (3, 4):
            kind = 5
        elif world == 5:
            kind = 6
        else:
            return None
        if ram[0x561] >= Zelda2.AREAS:
            return None
        return {'set': kind, 'area': ram[0x561]}

    def where(self, ram):
        part = self.part_of(ram)
        if part is None:
            return None
        return {'part': part, 'x': ram[0x72A] * 256 + ram[0x72C], 'y': 0}

    def part_name(self, part):
        return f'{self.SETS[int(part["set"])][0]}, area {int(part["area"]):#04x}'

    def choices(self):
        out = {'items': [{'value': k, 'name': v} for k, v in self.ITEMS.items()]}
        for kind in self.SETS:
            out[f'enemies_{kind}'] = [{'value': t, 'name': self.enemy_name(kind, t)} for t in self.set_types(kind)]
        return out

    def _list_note(self, kind, area, strong):
        """(editable, note) for the area's enemy list."""
        address = self.list_at(kind, area, strong)
        users = self.list_users(kind, address)
        layout = self.layout_at(kind, area)
        others = [(a, s) for a, s in users if (a, s) != (area, strong)]
        if not others:
            return True, ''
        if all(not s and self.layout_at(kind, a) == layout for a, s in others):
            return True, (f'Areas {", ".join(f"{a:#04x}" for a, s in others)} are this same scene and share this list, '
                          'so the change shows there too.')
        return False, (f'{len(others)} other place{"s" if len(others) > 1 else ""} use this enemy list, so it is shown '
                       'but not changed here.')

    def objects(self, part):
        kind, area = int(part['set']), int(part['area'])
        out = []
        for strong in ((False, True) if self.encounter_list(kind, area) else (False,)):
            editable, note = self._list_note(kind, area, strong)
            for e in self.enemies(kind, area, strong):
                x = e['screen'] * 256 + e['column'] * 16 + 8
                row = {'id': f'{"strong" if strong else "enemy"}:{e["k"]}', 'style': 'enemy', 'type': e['type'],
                       'x': x, 'y': self.line(e['height']) + self.FEET, 'name': self.enemy_name(kind, e['type']),
                       'detail': f'screen {e["screen"] + 1}, column {e["column"]}',
                       'remove': 'Remove the enemy' if editable and not strong else None,
                       'fields': [{'key': 'enemy', 'label': 'Enemy', 'value': e['type'], 'choices': f'enemies_{kind}'}] if editable else []}
                notes = []
                if strong:
                    notes.append('No map entrance leads to this scene; when it is a random encounter, this enemy is '
                                 'there when Link touches a big monster on the map.')
                elif self.encounter_list(kind, area):
                    notes.append('In a random encounter scene the game brings back every enemy each time, so a removed '
                                 'enemy stays away only when this scene is not a random encounter.')
                if e['placed']:
                    notes.append('The game treats this one as already placed, so it never appears.')
                if note:
                    notes.append(note)
                if notes:
                    row['note'] = ' '.join(notes)
                does = self.DOES.get(self.SETS[kind][1], {}).get(e['type'])
                if does:
                    row['does'] = does
                out.append(row)
        shared = len(self.layout_users(kind, area)) > 1
        for it in self.items(kind, area):
            x = it['screen'] * 256 + it['column'] * 16 + 8
            row = {'id': f'item:{it["n"]}', 'style': 'item', 'type': 0x100 + (it['item'] & 0x7F), 'x': x,
                   'y': it['row'] * 16 + 0x20 + self.FEET, 'name': self.item_name(it['item']),
                   'detail': f'screen {it["screen"] + 1}, column {it["column"]}', 'remove': None,
                   'note': 'It falls to the floor below this spot.',
                   'fields': [{'key': 'item', 'label': 'Item', 'value': it['item'] & 0x7F, 'choices': 'items'}]}
            if it['item'] & 0x7F in self.ITEM_DOES:
                row['does'] = self.ITEM_DOES[it['item'] & 0x7F]
            if shared:
                row['fields'] = []
                row['note'] += (f' {len(self.layout_users(kind, area)) - 1} other areas are drawn from the same layout, '
                                'so the item is shown but not changed here.')
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        kind, area = int(part['set']), int(part['area'])
        if kind not in self.SETS or not 0 <= area < self.AREAS:
            raise ValueError('That is not one of the game’s scenes.')
        what, _, n = object_id.partition(':')
        n = int(n)
        where = self.part_name(part)
        if what in ('enemy', 'strong'):
            strong = what == 'strong'
            if strong and not self.encounter_list(kind, area):
                raise ValueError('That is not part of this level any more. Reopen the map.')
            entries = self.enemies(kind, area, strong)
            if not 0 <= n < len(entries):
                raise ValueError('That is not part of this level any more. Reopen the map.')
            e = entries[n]
            editable, _ = self._list_note(kind, area, strong)
            if not editable:
                raise ValueError('Other places use this enemy list, so ROMancer leaves it alone.')
            first, second = self.rom[e['at']], self.rom[e['at'] + 1]
            x = e['screen'] * 256 + e['column'] * 16 + 8
            watch = {'kind': 'enemy', 'set': kind, 'area': area, 'strong': strong, 'offset': e['offset'], 'x': x,
                     'screen': e['screen'], 'column': e['column']}
            if remove:
                if strong:
                    raise ValueError('The game brings back every enemy of an encounter, so this one cannot be removed.')
                writes = [(e['at'], first, first | 0x80)] if not first & 0x80 else []
                watch.update(remove=True, type=None, name='no enemy')
                return {'writes': writes, 'title': f'{where}: enemy {n + 1} removed', 'watch': watch}
            new = int(values.get('enemy', e['type']))
            if new not in self.set_types(kind):
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(e['at'] + 1, second, (second & 0xC0) | new)] if new != e['type'] else []
            name = self.enemy_name(kind, new)
            watch.update(remove=False, type=new, name=name)
            return {'writes': writes, 'title': f'{where}: enemy {n + 1} is now {name}', 'watch': watch}
        if what == 'item':
            items = self.items(kind, area)
            if not 0 <= n < len(items):
                raise ValueError('That is not part of this level any more. Reopen the map.')
            it = items[n]
            if len(self.layout_users(kind, area)) > 1:
                raise ValueError('Other areas are drawn from the same layout, so ROMancer leaves this item alone.')
            new = int(values.get('item', it['item'] & 0x7F))
            if new not in self.ITEMS:
                raise ValueError('That choice is not one of the game’s own.')
            value = (it['item'] & 0x80) | new
            writes = [(it['at'], it['item'], value)] if value != it['item'] else []
            name = self.item_name(new)
            return {'writes': writes, 'title': f'{where}: item is now {name}',
                    'watch': {'kind': 'item', 'set': kind, 'area': area, 'screen': it['screen'], 'column': it['column'],
                              'item': new, 'name': name}}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        return {'enemy': _Z2EnemyWatcher, 'item': _Z2ItemWatcher}[watch['kind']](watch)

PROFILES = [Zelda1Profile, Zelda2Profile]
