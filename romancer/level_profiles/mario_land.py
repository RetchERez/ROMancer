"""Super Mario Land and Super Mario Land 2: their enemies, blocks, hidden blocks and pipes to bonus rooms.

Game Boy games (SM83 CPU, MBC1 banks of 16 KB). A CPU address $4000-$7FFF in bank b is ROM offset b * 0x4000 + (address -
$4000); $0000-$3FFF is the fixed bank 0. The game's RAM comes in as work RAM only: offset 0 is $C000.
Research notes: research/mario_land-level-profile.md.
"""
from __future__ import annotations

from . import Profile, Watcher


def rom_offset(bank: int, address: int) -> int:
    return address if address < 0x4000 else bank * 0x4000 + (address - 0x4000)


# ---------------------------------------------------------------------------------------------------------------------
# Super Mario Land (World) (Rev 1)
# ---------------------------------------------------------------------------------------------------------------------

class SuperMarioLand:
    """Super Mario Land. Level index $FFE4 (0-11: 1-1 ... 4-3). Each world keeps its levels in one bank (bank switch at
    $0D6D: world 1 bank 2, world 2 bank 1, world 3 bank 3, world 4 bank 1).

    * Layout: word at $4000 + level * 2 (level bank) -> list of screen pointers ($FF ends it). A screen is 20 columns of
      16 tiles (8x8 pixels); a column is groups of [high nibble first row, low nibble count (0 = 16)] + tiles, a tile of
      $FD repeats the next byte for the rest of the group, $FE ends the column (decoder $21C9). Level row 0 is drawn at
      background row 2 (the top two rows hold the status bar). The level starts at screen 3; screens 0-2 hold the bonus
      rooms that pipes lead to.
    * Enemies: word at $401A + level * 2 (level bank) -> 3-byte entries sorted by column, $FF ends (spawn code $249B):
      [16-pixel column counted from screen 3, y (low 5 bits, in 8-pixel rows) + x fine (bits 6-7, 4 pixels each),
      type (bit 7: only in the second quest, $24F4)].
    * Block contents: word at $6536 + level * 2 (bank 3) -> [screen, column, what] 3-byte entries, $FF ends ($2321). The
      top ? block, brick-like block or hidden block of that column gets it ($2363 writes it to the block map at $C800).
    * Pipes to bonus rooms: word at $651C + level * 2 (bank 3) -> [screen, column, room screen, way-back screen, x, y]
      6-byte entries, $FF ends ($22A9).
    """
    name = 'Super Mario Land'
    sha256 = '49fbd2f61f953d5ef28cab73e357e524c3009ad19fcf30f6a9ee0ae273be41dc'
    WORLD_BANK = {1: 2, 2: 1, 3: 3, 4: 1}
    LEVELS = 12
    SCREEN = 160            # pixels a screen (20 columns of 8)
    START_SCREEN = 3
    ENEMY_TABLE, LAYOUT_TABLE = 0x401A, 0x4000
    BLOCK_TABLE, PIPE_TABLE = 0x6536, 0x651C
    TOP = 16                # level row 0 is background pixel row 16
    QUESTION, BRICK_ITEM, HIDDEN, BRICK, PIPE = 0x81, 0x80, 0x5F, 0x82, 0x70
    # names from spawning each type in 1-1 and looking at what the game draws (trace/v15_profiles/mario_land/spawn_sheet3.png);
    # the four bosses are each the last enemy of their world's third level and draw as the big boss. The rest were named by
    # starting the first level of a world that uses the type (high RAM $FFE4/$FFB4 written through a save state as the game
    # starts) with the type in the level's first enemy entry, and watching it (trace/v15_profiles/naming_capcom_sml_mm6/sml/);
    # each world loads its own enemy pictures, so a type is looked at in its own world
    ENEMIES = {0x00: 'Goombo', 0x04: 'Nokobon', 0x08: 'King Totomesu (boss)', 0x1A: 'Dragonzamasu (boss)',
               0x32: 'Hiyoihoi (boss)', 0x61: 'Tatanga (boss)', 0x3C: 'Bunbun',
               0x0B: 'Lift (3 blocks)', 0x39: 'Lift (3 blocks)', 0x3B: 'Lift (2 blocks)', 0x0C: 'Lift (wide block)',
               0x0A: 'Falling lift (3 blocks)', 0x38: 'Falling lift (3 blocks)', 0x3A: 'Falling lift (2 blocks)',
               0x02: 'Pakkun Flower', 0x0E: 'Hopping fly', 0x3F: 'Gao', 0x42: 'Running creature',
               0x25: 'Jumping spider', 0x35: 'Small sprout', 0x47: 'Falling boulder', 0x49: 'Small hopping statue',
               0x4B: 'Small flying craft', 0x52: 'Hopping creature', 0x54: 'Bouncing ball'}
    # what each one did while Mario stood still for 200 frames (slot positions in the .json files beside the pictures)
    DOES = {0x00: 'Walks toward you.', 0x04: 'Walks toward you.', 0x08: 'Jumps up and down in place.',
            0x02: 'Rises and sinks in place.', 0x0E: 'Hops toward you.', 0x3F: 'Sits in place and spits fireballs.',
            0x42: 'Runs toward you.', 0x25: 'Jumps up and down in place.', 0x35: 'Stays in place.',
            0x47: 'Drops and rolls away.', 0x49: 'Hops in place and fires small shots.', 0x4B: 'Flies straight toward you.',
            0x52: 'Hops toward you, then stops.', 0x54: 'Bounces around in a loop.',
            0x3C: 'Flies toward you, swooping up and down.',
            0x0B: 'Moves left and right.', 0x3B: 'Moves left and right.', 0x39: 'Moves back and forth at a slant.',
            0x0C: 'Drops after a short wait.', 0x0A: 'Falls straight down.', 0x3A: 'Falls straight down.'}
    UNSURE = set()          # Bunbun (0x3C) was shown as likely from one picture in 1-1; watched flying in 3-1 since
    BOSSES = {0x08, 0x1A, 0x32, 0x61}
    # what a block can hold: hit with each value in a scripted 1-1 replay (trace/v15_profiles/mario_land/hit_sheet.png); $28
    # turns into the flower for big Mario in the code ($1911)
    CONTENTS = {0x28: 'Mushroom (a flower when Mario is big)', 0x2A: '1-up heart', 0x2C: 'Star', 0xC0: 'Coin',
                0xF0: 'Nothing (the block just shows)', 0x07: 'Object 0x07 (sits on the block)'}

    def __init__(self, rom: bytes):
        self.rom = rom
        self._columns = {}

    # ---- reading
    def at(self, bank: int, address: int) -> int:
        return self.rom[rom_offset(bank, address)]

    def word(self, bank: int, address: int) -> int:
        return self.at(bank, address) | self.at(bank, address + 1) << 8

    def bank(self, level: int) -> int:
        return self.WORLD_BANK[level // 3 + 1]

    def screen_pointers(self, level: int) -> list:
        bank, out = self.bank(level), []
        pointer = self.word(bank, self.LAYOUT_TABLE + level * 2)
        while self.at(bank, pointer) != 0xFF and len(out) < 64:
            out.append(self.word(bank, pointer))
            pointer += 2
        return out

    def _screen_columns(self, bank: int, pointer: int) -> list:
        columns = []
        for _ in range(20):
            column = [0x2C] * 16
            while True:
                head = self.at(bank, pointer)
                pointer += 1
                if head == 0xFE:
                    break
                row, count = head >> 4, head & 15 or 16
                while count:
                    tile = self.at(bank, pointer)
                    pointer += 1
                    if tile == 0xFD:
                        value = self.at(bank, pointer)
                        pointer += 1
                        while count and row < 16:
                            column[row] = value
                            row, count = row + 1, count - 1
                        break
                    if row < 16:
                        column[row] = tile
                    row, count = row + 1, count - 1
            columns.append(column)
        return columns

    def columns(self, level: int) -> list:
        """Every column of the level, screen 0 first: [[16 tile numbers]]."""
        if level not in self._columns:
            bank = self.bank(level)
            self._columns[level] = [c for p in self.screen_pointers(level) for c in self._screen_columns(bank, p)]
        return self._columns[level]

    def enemy_list(self, level: int):
        """(first entry address, address of the $FF that ends it) in the level bank."""
        bank = self.bank(level)
        start = pointer = self.word(bank, self.ENEMY_TABLE + level * 2)
        while self.at(bank, pointer) != 0xFF:
            pointer += 3
        return start, pointer

    def enemies(self, level: int) -> list:
        bank = self.bank(level)
        start, end = self.enemy_list(level)
        out = []
        for number, address in enumerate(range(start, end, 3)):
            column, place, kind = (self.at(bank, address + i) for i in range(3))
            fine = (place & 0xC0) >> 4
            out.append({'number': number, 'column': column, 'type': kind & 0x7F, 'second_quest': bool(kind & 0x80),
                        'x': self.START_SCREEN * self.SCREEN + column * 16 + fine + 8, 'y': (place & 0x1F) * 8 + 8,
                        'sprite_x': 0xC0 + fine, 'sprite_y': (place & 0x1F) * 8 + 16,
                        'byte': rom_offset(bank, address + 2), 'address': address})
        return out

    def _list(self, table: int, level: int, size: int) -> list:
        pointer, out = self.word(3, table + level * 2), []
        while self.at(3, pointer) != 0xFF and len(out) < 64:
            out.append((pointer, [self.at(3, pointer + i) for i in range(size)]))
            pointer += size
        return out

    def special_row(self, level: int, screen: int, column: int, tiles) -> int | None:
        cols = self.columns(level)
        index = screen * 20 + column
        if index >= len(cols):
            return None
        return next((row for row, tile in enumerate(cols[index]) if tile in tiles), None)

    def blocks(self, level: int) -> list:
        """Blocks the game gives contents to."""
        out = []
        for number, (address, (screen, column, what)) in enumerate(self._list(self.BLOCK_TABLE, level, 3)):
            row = self.special_row(level, screen, column, (self.BRICK_ITEM, self.HIDDEN, self.QUESTION))
            tile = self.columns(level)[screen * 20 + column][row] if row is not None else None
            out.append({'number': number, 'screen': screen, 'column': column, 'row': row, 'tile': tile, 'what': what,
                        'x': screen * self.SCREEN + column * 8 + 4, 'y': self.TOP + 8 * (row or 0) + 8,
                        'byte': rom_offset(3, address + 2)})
        return out

    def plain_blocks(self, level: int) -> list:
        """? blocks the list gives nothing (the game gives a coin)."""
        listed = {(b['screen'], b['column']) for b in self.blocks(level)}
        out = []
        for index, column in enumerate(self.columns(level)):
            screen, col = divmod(index, 20)
            for row, tile in enumerate(column):
                if tile == self.QUESTION and (screen, col) not in listed:
                    out.append({'screen': screen, 'column': col, 'row': row,
                                'x': screen * self.SCREEN + col * 8 + 4, 'y': self.TOP + 8 * row + 8})
        return out

    def pipes(self, level: int) -> list:
        out = []
        for number, (address, (screen, column, room, back, x, y)) in enumerate(self._list(self.PIPE_TABLE, level, 6)):
            row = self.special_row(level, screen, column, (self.PIPE,))
            out.append({'number': number, 'screen': screen, 'column': column, 'room': room, 'back': back,
                        'back_x': x, 'back_y': y, 'row': row, 'x': screen * self.SCREEN + column * 8 + 8,
                        'y': self.TOP + 8 * ((row if row is not None else 12) + 1), 'byte': rom_offset(3, address + 2)})
        return out

    def enemy_name(self, kind: int) -> str:
        name = self.ENEMIES.get(kind)
        if name is None:
            return f'Enemy {kind:#04x}'
        return name + (' (likely)' if kind in self.UNSURE else '')

    def content_name(self, what: int) -> str:
        return self.CONTENTS.get(what, f'Object {what:#04x}')

    # ---- where the game is (work RAM only: $C000 is offset 0)
    def level_of(self, ram) -> int | None:
        """The level whose enemy list holds the game's enemy pointer ($D010/$D011): each level's list is in its own place."""
        pointer = ram[0x1010] | ram[0x1011] << 8
        for level in range(self.LEVELS):
            start, end = self.enemy_list(level)
            if start <= pointer <= end:
                return level
        return None

    def camera(self, ram) -> tuple:
        """(camera x in level pixels, level pixel x shown at background column 0, modulo 256).

        The 16-pixel column counter $C0AB is 12 at the start of screen 3 and goes up by one each 16 pixels (a little ahead or
        behind the screen). $C0AA keeps the scroll value from when the last column was drawn. The background map was last
        reset at the start of a screen (a multiple of 160 pixels, so of 32), so the low 5 bits of $C0AA are the camera's,
        which the counter's estimate (within 16 pixels) completes. Measured error: 0 to 9 pixels."""
        approx = (ram[0xAB] - 12) * 16 - 4
        low = ram[0xAA] & 0x18
        scrolled = min((n * 32 + low for n in range(-8, 512)), key=lambda v: abs(v - approx))
        camera = self.START_SCREEN * self.SCREEN + scrolled
        return camera + 3, (camera - (ram[0xAA] & 0xF8)) & 0xE0

    def where_level(self, ram):
        """(level, camera x, background column 0 x modulo 256) or None."""
        level = self.level_of(ram)
        if level is None:
            return None
        columns = self.columns(level)
        last = list(ram[0xB0:0xC0])          # the column the game drew last (its buffer at $C0B0)
        predicted = 2 * ram[0xAB] + 62
        camera, base = self.camera(ram)
        if any(0 <= i < len(columns) and columns[i] == last for i in range(predicted - 3, predicted + 4)):
            return level, camera, base
        # in a bonus room the column counter stays where the pipe was: the room is the one that pipe leads to
        near = [p for p in self.pipes(level) if camera - 24 <= p['x'] <= camera + 184]
        if near and all(p['room'] == near[0]['room'] for p in near):
            room = near[0]['room'] * self.SCREEN
            return level, room, room & 0xFF
        return None


class _EnemyWatcher(Watcher):
    """An enemy edit: when the game's enemy pointer ($D010/$D011) passes the entry, look for an enemy slot ($D100, 16
    bytes each: type, state, y, x) that was not there on the look before, at the entry's spawn x. Its y is not checked:
    flying types move to their own height on the frame they appear."""
    every = 2

    def __init__(self, game, watch):
        self.g, self.w = game, watch
        self.passed, self.seen, self.before = None, None, set()

    def see(self, ram, frame, run):
        w = self.w
        if self.g.level_of(ram) != w['level']:
            return False
        slots = {(slot, ram[0x1100 + 16 * slot]) for slot in range(10) if ram[0x1100 + 16 * slot] != 0xFF}
        pointer = ram[0x1010] | ram[0x1011] << 8
        if pointer <= w['address']:
            self.before = slots
            return False
        self.passed = self.passed or frame
        for slot, kind in sorted(slots - self.before):
            x = ram[0x1100 + 16 * slot + 3]
            if w['sprite_x'] - 16 <= x <= w['sprite_x'] + 4:
                self.seen = kind
                return True
        self.before = slots
        return frame - self.passed > 8

    def result(self):
        w = self.w
        if self.passed is None:
            return super().result()
        if w.get('second_quest'):
            return {'state': 'warn', 'text': 'This enemy is only in the second quest, and the recorded walk plays the first quest, '
                                             'so the change couldn’t be watched in the game.'}
        if w['removing']:
            ok = self.seen is None
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, no enemy appears there any more.' if ok
                    else 'Played from the start, an enemy still appears there.'}
        ok = self.seen in w['wanted']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now puts {w["name"]} there.' if ok else
                ('Played from the start, nothing appeared there.' if self.seen is None
                 else f'Played from the start, the game put type {self.seen:#04x} there, not what was chosen.')}


class _BlockWatcher(Watcher):
    """A block edit: once the game has drawn the block's column, its block map ($C800, one byte per background cell) holds
    what the block gives. Hitting the block in the walk is not needed."""
    every = 4

    def __init__(self, game, watch):
        self.g, self.w = game, watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        found = self.g.where_level(ram)
        if found is None or found[0] != w['level']:
            return False
        level, camera, base = found
        if not w['x'] - 150 <= camera <= w['x'] + 20:
            return False
        # the column was drawn 27 columns ahead of the screen and is still in the background map
        column = ((w['x'] - base) & 0xFF) // 8
        value = ram[0x800 + (w['row'] + 2) * 32 + column]
        self.seen = value
        return value != 0

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        ok = self.seen == w['what']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game loads the block with what was chosen ({w["name"]}).' if ok
                else f'Played from the start, the game loads the block with {self.g.content_name(self.seen) if self.seen else "nothing"}, not what was chosen.'}


class SuperMarioLandProfile(SuperMarioLand, Profile):
    """Super Mario Land on the common profile interface. Parts are {'level': 0-11}; x is level pixels from screen 0."""
    sha256s = (SuperMarioLand.sha256,)
    system = 'gb'

    def where(self, ram):
        found = self.where_level(ram)
        if found is None:
            return None
        return {'part': {'level': found[0]}, 'x': found[1], 'y': 0}

    def part_name(self, part):
        level = int(part['level'])
        return f'World {level // 3 + 1}-{level % 3 + 1}'

    def enemy_choices(self, world: int) -> list:
        """The types the world's own enemy lists use, bosses left out (the level ends with its boss). These are the enemies
        the world's levels are built with; each was swapped in and watched in 1-1 for world 1 (research notes)."""
        levels = range((world - 1) * 3, world * 3)
        kinds = sorted({e['type'] for level in levels for e in self.enemies(level)} - self.BOSSES)
        return [{'value': k, 'name': self.enemy_name(k)} for k in kinds]

    def choices(self):
        return {**{f'enemies_world{w}': self.enemy_choices(w) for w in range(1, 5)},
                'contents': [{'value': k, 'name': v} for k, v in self.CONTENTS.items()]}

    def objects(self, part):
        level = int(part['level'])
        out = []
        for e in self.enemies(level):
            boss = e['type'] in self.BOSSES
            row = {'id': f'enemy:{e["number"]}', 'style': 'enemy', 'type': e['type'], 'x': e['x'], 'y': e['y'],
                   'name': self.enemy_name(e['type']),
                   'remove': None if e['second_quest'] or boss else 'Remove this enemy',
                   'fields': [] if boss else [{'key': 'type', 'label': 'Swap for', 'value': e['type'],
                                               'choices': f'enemies_world{level // 3 + 1}'}]}
            if e['type'] in self.DOES:
                row['does'] = self.DOES[e['type']]
            if e['second_quest']:
                row['note'] = ('Only in the second quest (the harder game after the ending). The recorded walk plays the first '
                               'quest, so a change here cannot be watched in the game.')
            if boss:
                row['note'] = 'The boss of this world. ROMancer leaves it as it is, because the level ends with it.'
            out.append(row)
        for b in self.blocks(level):
            hidden = b['tile'] == self.HIDDEN
            row = {'id': f'block:{b["number"]}', 'style': 'secret' if hidden else 'item', 'type': b['what'],
                   'x': b['x'], 'y': b['y'], 'name': 'Hidden block' if hidden else ('Question block' if b['tile'] == self.QUESTION else 'Brick block'),
                   'detail': f'holds {self.content_name(b["what"]).lower()}', 'remove': None,
                   'fields': [{'key': 'what', 'label': 'Holds', 'value': b['what'], 'choices': 'contents'}]}
            if b['screen'] < self.START_SCREEN:
                row['note'] = 'In a bonus room.'
            out.append(row)
        for b in self.plain_blocks(level):
            out.append({'id': f'coin:{b["screen"]}:{b["column"]}:{b["row"]}', 'style': 'item', 'type': 0, 'x': b['x'], 'y': b['y'],
                        'name': 'Question block', 'detail': 'holds a coin', 'remove': None, 'fields': [],
                        'note': 'The game has no entry for this block, so it gives a coin. ROMancer changes only the blocks the game lists.'})
        for p in self.pipes(level):
            out.append({'id': f'pipe:{p["number"]}', 'style': 'secret', 'type': 0x70, 'x': p['x'], 'y': p['y'],
                        'name': 'Pipe to a bonus room', 'remove': None, 'fields': [],
                        'detail': f'leads to the bonus room on screen {p["room"]}; the way out comes up on screen {p["back"]}'})
        return out

    def edit(self, part, object_id, values, remove=False):
        level = int(part['level'])
        kind, _, number = object_id.partition(':')
        if kind == 'enemy':
            e = next((e for e in self.enemies(level) if e['number'] == int(number)), None)
            if e is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            old = self.rom[e['byte']]
            if e['type'] in self.BOSSES:
                raise ValueError('ROMancer leaves the bosses as they are, because the level ends with them.')
            if remove:
                if e['second_quest']:
                    raise ValueError('This enemy is only in the second quest already.')
                new, name, title = old | 0x80, 'no enemy', f'Remove the {self.enemy_name(e["type"])}'
            else:
                kind_value = int(values.get('type'))
                if kind_value not in {c['value'] for c in self.enemy_choices(level // 3 + 1)}:
                    raise ValueError('Choose one of the enemies this world uses.')
                new, name = (old & 0x80) | kind_value, self.enemy_name(kind_value)
                title = f'Enemy here: {name}'
            writes = [(e['byte'], old, new)] if new != old else []
            return {'writes': writes, 'title': title,
                    'watch': {'kind': 'enemy', 'level': level, 'address': e['address'], 'sprite_x': e['sprite_x'],
                              'sprite_y': e['sprite_y'], 'removing': bool(remove), 'name': name,
                              'second_quest': e['second_quest'],
                              'wanted': self.slot_types(new & 0x7F)}}
        if kind == 'block':
            b = next((b for b in self.blocks(level) if b['number'] == int(number)), None)
            if b is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            what = int(values.get('what'))
            if what not in self.CONTENTS:
                raise ValueError('That choice is not one of the game’s own.')
            old = self.rom[b['byte']]
            return {'writes': [(b['byte'], old, what)] if old != what else [], 'title': f'Block holds: {self.content_name(what)}',
                    'watch': {'kind': 'block', 'level': level, 'x': b['x'] - 4, 'row': b['row'] or 0, 'what': what,
                              'name': self.content_name(what)}}
        raise ValueError('ROMancer cannot change that yet.')

    SLOT_TYPES = {0x07: {0x07, 0x13}, 0x2D: {0x2D, 0x2E}}

    def slot_types(self, kind: int) -> list:
        return sorted(self.SLOT_TYPES.get(kind, {kind}))

    def watcher(self, watch):
        if watch['kind'] == 'enemy':
            return _EnemyWatcher(self, watch)
        return _BlockWatcher(self, watch)

    def tile_role(self, tile):
        if tile in (self.BRICK, self.BRICK_ITEM):
            return 'breakable'
        if tile >= 0x60 and tile != 0xF4:
            return 'solid'
        return 'open'


# ---------------------------------------------------------------------------------------------------------------------
# Super Mario Land 2 - 6 Golden Coins (USA, Europe) (Rev 2)
# ---------------------------------------------------------------------------------------------------------------------

class SuperMarioLand2:
    """Super Mario Land 2. The game keeps its state in cartridge RAM ($A000-$BFFF) and high RAM; work RAM holds the lower
    part of the level map.

    * Level number: $A269 (0-31). Level header: word at bank 1 $55CB + level * 2 -> 20 bytes copied to $A800 ($5589):
      byte $0D is the map's bank, byte $12 (low nibble) the map's number in that bank.
    * Map ($0361): word at $42F0 + number * 2 in the map's bank; unpacked to $B000-$DFFF: a byte below $80 is one map
      cell, $80 + v followed by n is v written n + 1 times. 256 cells a row, 48 rows, a cell is 16x16 pixels. Work RAM
      ($C000) is map row 16 on.
    * Objects (enemies and what blocks hold, bank 3 $6BC7): word at $6037 + level * 2 -> 3-byte entries, $FF ends;
      unpacked to a 6-byte table at $AB06: [x high, x low, flag, y high, y low, type] with x = (b0 & $0F) << 8 |
      (b1 & $1F) << 3, y = ((b2 >> 5) & 3) << 8 | (b2 & $1F) << 3, flag = b2 bit 7, type = b0 bits 5-7 (type bits 3-5),
      b0 bit 4 (type bit 6) and b1 bits 5-7 (type bits 0-2). Object slots: $AD00 + 32 * n (16 slots), the first 6 bytes
      as in the table, bytes 6-7 the table address of the entry + 2.
    * Camera: $FFCA/$FFCB (x + $50) and $FFC8/$FFC9 (y + $48) in high RAM ($2065 sets the scroll registers from them).
    """
    name = 'Super Mario Land 2'
    sha256 = '42045a1642f77b568534ab85b9db93c8a33d2b95c38ae84c987f497e8d52f97f'
    LEVELS = 32
    HEADERS, MAPS, OBJECTS = 0x55CB, 0x42F0, 0x6037
    TABLE = 0x0B06              # the object table in cartridge RAM ($AB06), as an offset into it
    # what a ? block gives when an object of this type sits in it: each put in the first level's mushroom block and hit
    # in a scripted replay (trace/v15_profiles/mario_land/hit25.png)
    ITEMS = {0x11: 'Mushroom', 0x12: 'Fire flower', 0x13: 'Carrot', 0x14: 'Star', 0x15: 'Heart (extra life)'}
    # names from putting each type in place of the first level's first enemy and looking (spawn20.png); the rest from
    # putting each type in the left-most enemy of the first level that uses it (the level chosen by writing $A269 as the
    # map starts it) and watching it (trace/v15_profiles/naming_capcom_sml_mm6/sml/l2_*.png); each level loads its own
    # enemy pictures, so a type is looked at in its own level
    ENEMIES = {0x09: 'Goomba', 0x01: 'Koopa Troopa', 0x08: 'Goomba with wings', 0x0C: 'Piranha Plant',
               0x05: 'Small fish', 0x06: 'Fish', 0x0B: 'Small darting fish', 0x18: 'Large horned beast',
               0x1F: 'Small hopping creature', 0x21: 'Spiky creature', 0x22: 'Small walking creature',
               0x25: 'Shelled walker with a propeller', 0x27: 'Small black walker', 0x2B: 'Moving lift',
               0x2C: 'Moving lift, at a slant', 0x40: 'Small winged creature', 0x41: 'Crawling grub', 0x42: 'Crawling ant',
               0x43: 'White egg', 0x44: 'Small shelled walker', 0x47: 'Black ball', 0x48: 'Small soldier',
               0x49: 'Hanging claw', 0x4A: 'Spiked ball', 0x4C: 'Spiked ball', 0x57: 'Hopping mushroom creature',
               0x5A: 'Hopping broom', 0x5B: 'Diving bird', 0x5C: 'Flying pin', 0x5D: 'Black bird',
               0x6E: 'Large spiked ball'}
    DOES = {0x09: 'Walks toward you.', 0x01: 'Walks toward you.', 0x08: 'Hops toward you.', 0x0C: 'Rises and sinks in place.',
            0x05: 'Swims toward you.', 0x06: 'Swims toward you.', 0x0B: 'Swims toward you, then rises.',
            0x18: 'Stays in place.', 0x1F: 'Hops toward you.', 0x21: 'Stays in place.', 0x22: 'Walks toward you.',
            0x25: 'Walks toward you.', 0x27: 'Walks toward you.', 0x2B: 'Moves back and forth.',
            0x2C: 'Moves back and forth at a slant.', 0x40: 'Stays in place.', 0x41: 'Crawls back and forth.',
            0x42: 'Crawls back and forth.', 0x43: 'Stays in place.', 0x44: 'Walks toward you.', 0x47: 'Stays in place.',
            0x48: 'Drops down and walks toward you.', 0x49: 'Hangs in one place.', 0x4A: 'Stays in place.',
            0x4C: 'Stays in place.', 0x57: 'Hops toward you.', 0x5A: 'Hops toward you.',
            0x5B: 'Swoops down toward you and back up.', 0x5C: 'Flies toward you in short hops.', 0x5D: 'Stays in place.',
            0x6E: 'Rolls back and forth.'}
    # objects that are not enemies, shown but left alone: the bells (the end and the middle of the first level; drawn as
    # bells in spawn20.png) and a heart lying in the open
    FIXED = {0x0F: 'Heart (extra life)', 0x16: 'Bell (likely the end of the level)', 0x17: 'Bell (likely the midway bell)'}

    def __init__(self, rom: bytes):
        self.rom = rom
        self._maps = {}

    def at(self, bank: int, address: int) -> int:
        return self.rom[rom_offset(bank, address)]

    def word(self, bank: int, address: int) -> int:
        return self.at(bank, address) | self.at(bank, address + 1) << 8

    def header(self, level: int) -> list:
        pointer = self.word(1, self.HEADERS + level * 2)
        return [self.at(1, pointer + i) for i in range(20)]

    def level_map(self, level: int) -> bytes:
        if level not in self._maps:
            head = self.header(level)
            bank = head[0x0D]
            pointer = self.word(bank, self.MAPS + (head[0x12] & 15) * 2)
            out = bytearray()
            while len(out) < 0x3000:
                value = self.at(bank, pointer)
                pointer += 1
                if value & 0x80:
                    out += bytes([value & 0x7F]) * (self.at(bank, pointer) + 1)
                    pointer += 1
                else:
                    out.append(value)
            self._maps[level] = bytes(out[:0x3000])
        return self._maps[level]

    @staticmethod
    def decode(b0: int, b1: int, b2: int) -> dict:
        kind = (b0 >> 2) & 0x3C
        if kind & 4:
            kind = (kind | 0x40) & ~4
        kind += (b1 >> 5) & 7
        return {'x': (b0 & 15) << 8 | (b1 & 31) << 3, 'y': ((b2 >> 5) & 3) << 8 | (b2 & 31) << 3, 'flag': b2 >> 7,
                'type': kind}

    @staticmethod
    def encode_type(b0: int, b1: int, kind: int) -> tuple:
        return (b0 & 0x0F) | ((kind >> 3) & 7) << 5 | ((kind >> 6) & 1) << 4, (b1 & 0x1F) | (kind & 7) << 5

    def object_list(self, level: int):
        start = pointer = self.word(3, self.OBJECTS + level * 2)
        while self.at(3, pointer) != 0xFF and pointer - start < 3 * 255:
            pointer += 3
        return start, pointer

    def objects_of(self, level: int) -> list:
        start, end = self.object_list(level)
        out = []
        for number, address in enumerate(range(start, end, 3)):
            raw = [self.at(3, address + i) for i in range(3)]
            out.append({'number': number, 'address': address, 'offset': rom_offset(3, address), 'raw': raw,
                        **self.decode(*raw)})
        return out

    def block_at(self, level: int, x: int, y: int):
        """(x, y) of the map cell with a block (cells 0 and 1) that an object at x, y sits in, or None."""
        cells = self.level_map(level)
        for dx in (0, -8, 8):
            for dy in (0, 8, -8):
                cx, cy = (x + dx) // 16, (y + dy) // 16
                if 0 <= cx < 256 and 0 <= cy < 48 and cells[cy * 256 + cx] in (0, 1):
                    return cx * 16, cy * 16
        return None

    def enemy_name(self, kind: int) -> str:
        return self.ENEMIES.get(kind, f'Enemy {kind:#04x}')

    # ---- where the game is: the level number in cartridge RAM, checked against the map in work RAM
    def level_of(self, ram):
        cart = (getattr(ram, 'domains', None) or {}).get('sram')
        if cart is None or len(cart) < 0x1000:
            return None
        level = cart[0x269]
        if level >= self.LEVELS:
            return None
        expected = self.level_map(level)[0x1000:0x1200]
        if sum(a == b for a, b in zip(expected, ram[0:0x200])) < 0x1C0:
            return None
        return level

    @staticmethod
    def camera(ram):
        high = (getattr(ram, 'domains', None) or {}).get('hram')
        if high is None:
            return None
        return (high[0x4B] << 8 | high[0x4A]) - 0x50, ((high[0x49] & 15) << 8 | high[0x48]) - 0x48


class _Sml2TableWatcher(Watcher):
    """An object edit in Super Mario Land 2: once the level is loaded, the game's object table in cartridge RAM ($AB06,
    unpacked by the game from the ROM list) must hold the change; when an object slot ($AD00) spawns from that entry,
    its type is checked too."""
    every = 8

    def __init__(self, game, watch):
        self.g, self.w = game, watch
        self.table, self.spawned = None, None

    def entries(self, cart):
        out = []
        for i in range(255):
            row = cart[self.g.TABLE + 6 * i:self.g.TABLE + 6 * i + 6]
            if len(row) < 6 or row[0] == 0xFF or row == bytes(6):
                break
            out.append((row[0] << 8 | row[1], row[3] << 8 | row[4], row[5]))
        return out

    def see(self, ram, frame, run):
        w = self.w
        if self.g.level_of(ram) != w['level']:
            return False
        cart = ram.domains['sram']
        self.table = self.entries(cart)
        pointer = 0xA000 + self.g.TABLE + 6 * w['number'] + 2
        for slot in range(16):
            base = 0xD00 + 32 * slot
            if cart[base] and (cart[base + 6] << 8 | cart[base + 7]) == pointer:
                self.spawned = cart[base + 5]
        return self.spawned is not None and not w['removing']

    def result(self):
        w = self.w
        if self.table is None:
            return super().result()
        spot = (w['x'], w['y'])
        if w['removing']:
            ok = (spot[0], spot[1], w['old']) not in self.table
            return {'state': 'good' if ok else 'bad',
                    'text': 'Played from the start, the game no longer has that enemy in the level.' if ok
                    else 'Played from the start, the game still has that enemy in the level.'}
        found = self.table[w['number']] if w['number'] < len(self.table) else None
        ok = found is not None and found[:2] == spot and found[2] == w['type']
        text = (f'Played from the start, the game loads {w["name"]} there.' if ok
                else 'Played from the start, the game loads something else there, not what was chosen.')
        if ok and self.spawned is not None:
            ok = self.spawned == w['type']
            text = (f'Played from the start, the game puts {w["name"]} there.' if ok
                    else 'Played from the start, a different object appeared there.')
        return {'state': 'good' if ok else 'bad', 'text': text}


class SuperMarioLand2Profile(SuperMarioLand2, Profile):
    """Super Mario Land 2 on the common profile interface. Parts are {'level': 0-31}; x, y are level pixels."""
    sha256s = (SuperMarioLand2.sha256,)
    system = 'gb'

    def where(self, ram):
        level = self.level_of(ram)
        camera = self.camera(ram) if level is not None else None
        if camera is None:
            return None
        return {'part': {'level': level}, 'x': camera[0], 'y': camera[1]}

    def part_name(self, part):
        return f'Level {int(part["level"]) + 1}'

    def enemy_choices(self, level: int) -> list:
        """The enemy types the level's own list uses (each level loads the pictures of its own enemies)."""
        kinds = sorted({o['type'] for o in self.objects_of(level)} - set(self.ITEMS) - set(self.FIXED))
        return [{'value': k, 'name': self.enemy_name(k)} for k in kinds]

    def choices(self):
        return {'items': [{'value': k, 'name': v} for k, v in self.ITEMS.items()]}

    def objects(self, part):
        level = int(part['level'])
        out = []
        for o in self.objects_of(level):
            if o['type'] in self.ITEMS:
                block = self.block_at(level, o['x'], o['y'])
                x, y = (block[0] + 8, block[1] + 16) if block else (o['x'], o['y'])
                out.append({'id': f'object:{o["number"]}', 'style': 'item', 'type': o['type'], 'x': x, 'y': y,
                            'name': 'Question block' if block else 'Item',
                            'detail': f'holds {self.ITEMS[o["type"]].lower()}', 'remove': None,
                            'fields': [{'key': 'type', 'label': 'Holds', 'value': o['type'], 'choices': 'items'}]})
                continue
            if o['type'] in self.FIXED:
                out.append({'id': f'object:{o["number"]}', 'style': 'item', 'type': o['type'], 'x': o['x'], 'y': o['y'],
                            'name': self.FIXED[o['type']], 'remove': None, 'fields': [],
                            'note': 'ROMancer leaves this as it is.'})
                continue
            row = {'id': f'object:{o["number"]}', 'style': 'enemy', 'type': o['type'], 'x': o['x'], 'y': o['y'],
                   'name': self.enemy_name(o['type']), 'remove': 'Remove this enemy',
                   'fields': [{'key': 'type', 'label': 'Swap for', 'value': o['type'], 'choices': self.enemy_choices(level)}]}
            if o['type'] in self.DOES:
                row['does'] = self.DOES[o['type']]
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        level = int(part['level'])
        kind, _, number = object_id.partition(':')
        found = next((o for o in self.objects_of(level) if kind == 'object' and o['number'] == int(number)), None)
        if found is None:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        if found['type'] in self.FIXED:
            raise ValueError('ROMancer leaves this as it is.')
        item = found['type'] in self.ITEMS
        watch = {'kind': 'object', 'level': level, 'number': found['number'], 'x': found['x'], 'y': found['y'],
                 'old': found['type'], 'removing': bool(remove)}
        if remove:
            if item:
                raise ValueError('ROMancer cannot empty this block.')
            # the later entries move up one place and the list ends one entry sooner
            start, end = self.object_list(level)
            base = found['offset']
            rest = bytes(self.rom[base + 3:rom_offset(3, end) + 1])
            writes = [(base + i, self.rom[base + i], v) for i, v in enumerate(rest) if self.rom[base + i] != v]
            return {'writes': writes, 'title': f'Remove the {self.enemy_name(found["type"])}', 'watch': watch}
        new_type = int(values.get('type'))
        allowed = set(self.ITEMS) if item else {c['value'] for c in self.enemy_choices(level)}
        if new_type not in allowed:
            raise ValueError('That choice is not one of the game’s own.')
        b0, b1 = self.encode_type(found['raw'][0], found['raw'][1], new_type)
        base = found['offset']
        writes = [(base + i, self.rom[base + i], v) for i, v in enumerate((b0, b1)) if self.rom[base + i] != v]
        name = self.ITEMS[new_type] if item else self.enemy_name(new_type)
        watch.update(type=new_type, name=name)
        return {'writes': writes, 'title': f'Block holds: {name}' if item else f'Enemy here: {name}', 'watch': watch}

    def watcher(self, watch):
        return _Sml2TableWatcher(self, watch)


PROFILES = [SuperMarioLandProfile, SuperMarioLand2Profile]
