"""Super Mario Bros. 2 (USA) (Rev 1), NES: areas, enemies, what grass and blocks give, and where doors lead.

Everything here was read from the game's code and proven by replaying the game (research/smb2-level-profile.md).

The cartridge is MMC3. The game maps 16 KB pairs: bank 2n at $8000 and 2n+1 at $A000 ($FF85, A = n); banks 14 and 15
stay at $C000-$FFFF. Level and enemy data live in banks 8 and 9 (pair 4), so a data address a is file offset
16 + $10000 + (a - $8000).

* Which area plays ($F754, pair 4): level $0531 (0-19, three per world; world 7 has two; $E012 is each world's first
  level), area $0532. Area data = word $8015/$80E7 [$8000[level] + area] (ten areas per level), copied to $7800. Enemy
  data = ($A515/$A500 [level]) [area] high byte and ($A53F/$A52A [level]) [area] low byte, copied to $7B00. Inside a
  jar ($0628 = 1) the game reads area 4 of the level instead ($F7BE, $F77D); $0628 = 2 is subspace (the same area drawn
  mirrored).
* Area data ($9567, $95E6): a 4-byte header (byte 0 bit 7: horizontal; byte 2 high nibble: pages - 1), then objects,
  $FF ends. An object is a position byte and a type byte. The position's high nibble is added to the row of the
  object before (15 rows a page; going past row 14 moves to the next page), its low nibble is the column. A position
  byte $Fx is a command: $F0/$F1/$F6 take one more byte, $F2/$F3 skip one or two pages, $F4 goes back to page 0, $F5 is
  followed by an area pointer (level, area << 4 | page) for every door, jar and vine on its page ($051D + page * 2).
  Doors ($09, $0A, $0B, $1C, $1D) and doorways ($13, $14) carry the same two pointer bytes after their type, except in
  worlds 6 and 7 ($0635 = 5 or 6, $9048, $8A8A). Types $20-$2F are single tiles from $8D30: $20-$28 and $2A are grass
  that can be pulled ($91BF: tile - $43 + 4 indexes $9065, the object pulled). Types $00 and $01 are a mushroom block
  and a POW block lying on the ground (tiles $69 and $6C, picked up by $9164).
* Enemy data ($8256-$83AE, bank 2): for each page, a length byte (itself plus two per enemy), then pairs (enemy,
  column << 4 | row). The game spawns an enemy when its spot scrolls into view, sets bit 7 of the copy in $7B00 so it
  does not come again (and clears it when the enemy leaves the screen), and keeps the entry's offset in $0441 + slot.
  An entry with bit 7 already set is skipped: that is how an enemy is removed here. Ids $47-$5B start a generator
  ($04B9); $5C and up are bosses (id & $3F, with $049B set).
* Enemy pictures: each world's own sprite bank is $FE00[world] (the fifth sprite bank, $06FC): worlds 1, 3 and 5 share
  one, 2 and 6 another, 4 and 7 have their own. An enemy is offered in an area only when the game itself puts it in a
  world with the same sprite bank, so the game has its picture there.
"""
from __future__ import annotations

from . import Profile, Watcher

SHA256 = '7aaaf89257b1653b70104c6ac1539eafa87b714d38a2f118eb419bf6f67f1559'
HEADER = 16

# RAM
LEVEL, AREA, ENTRY_PAGE, WORLD, JAR = 0x531, 0x532, 0x533, 0x635, 0x628
NMI_MODE = 0x100                    # $C0 while an area is being played
HORIZONTAL = 0xEC
SCROLL_X_HI, SCROLL_X = 0x4BE, 0x4C0
SCROLL_Y_HI, SCROLL_Y = 0xCA, 0xCB
POINTERS = 0x51D                    # area pointer of each page: level, area << 4 | page
ID, STATE, ENTRY = 0x90, 0x51, 0x441
CART = 0x800                        # cartridge RAM $6000 follows system RAM in the work RAM the session reads
TILES = 0x6000                      # the area's tiles: page * $F0 + row * 16 + column
ENEMY_COPY = 0x7B00

# Enemy ids, spawned in place of an enemy entry and looked at (trace/v15_profiles/smb2/enemy_sheet_a.png, _b.png,
# snifit_sheet.png, look3_sheet.png). Colours are as the game draws them in World 1. Two of a kind keep their number;
# ids never seen in the pictures (they hide or fly in later) show only their number.
ENEMIES = {
    0x01: 'Shy Guy (red)', 0x02: 'Tweeter', 0x03: 'Shy Guy (pink)', 0x04: 'Porcupo', 0x05: 'Snifit (red)',
    0x06: 'Snifit (gray)', 0x07: 'Snifit (pink)', 0x08: 'Ostro', 0x09: 'Bob-omb', 0x0A: 'Albatoss (0x0a)',
    0x0B: 'Albatoss (0x0b)', 0x0C: 'Albatoss (0x0c)', 0x0D: 'Ninji (0x0d)', 0x0E: 'Ninji (0x0e)',
    0x0F: 'Beezo (0x0f)', 0x10: 'Beezo (0x10)', 0x12: 'Enemy 0x12', 0x13: 'Trouter', 0x14: 'Hoopster',
    0x17: 'Phanto', 0x18: 'Enemy 0x18', 0x19: 'Enemy 0x19', 0x1A: 'Pokey',
    0x23: 'Panser (0x23)', 0x24: 'Panser (0x24)', 0x25: 'Panser (0x25)',
    0x26: 'Autobomb', 0x29: 'Flurry', 0x2E: 'Spark (0x2e)', 0x2F: 'Spark (0x2f)', 0x30: 'Spark (0x30)', 0x31: 'Spark (0x31)',
}
# Shown but not changed: the level needs them to be finished, or they are not plain enemies
FIXED = {
    0x15: 'Enemy 0x15 (jar)', 0x16: 'Enemy 0x16 (jar)', 0x1C: 'Birdo',
    0x2D: 'Hawkmouth (boss)', 0x3B: 'Falling log', 0x3D: 'Key', 0x42: 'Hawkmouth (exit, facing right)',
    0x43: 'Hawkmouth (exit, facing left)', 0x44: 'Crystal ball', 0x47: 'Bob-omb generator',
    0x48: 'Beezo generator', 0x5C: 'Birdo (boss)', 0x5D: 'Mouser', 0x5F: 'Tryclyde', 0x61: 'Clawgrip',
    0x6A: 'Boss 0x6a', 0x6C: 'Wart',
}
ITEMS = {0x3B, 0x3D, 0x42, 0x43, 0x44}
# Grass that can be pulled: object type -> (tile, what comes out), each pulled in 1-1 (pull.py, pull2.py)
GRASS = {0x20: 'a coin', 0x21: 'a large vegetable', 0x22: 'a small vegetable', 0x23: 'a rocket', 0x24: 'a shell',
         0x25: 'a bomb', 0x26: 'a magic potion', 0x27: 'a 1-up mushroom', 0x28: 'a POW block', 0x2A: 'a Bob-omb'}
GRASS_TILES = 0x8D30                # bank 6: tile of each type $20-$2F
BLOCKS = {0x00: 'Mushroom block', 0x01: 'POW block'}
BLOCK_TILES = {0x00: 0x69, 0x01: 0x6C}
DOORS = {0x09: 'Locked door', 0x0A: 'Door', 0x0B: 'Doorway', 0x13: 'Doorway', 0x14: 'Doorway', 0x1C: 'Doorway',
         0x1D: 'Doorway'}
CMD_SIZE = {0: 2, 1: 2, 2: 1, 3: 1, 4: 1, 5: 3, 6: 2}


class SMB2Data:
    """Reads the game's level tables and its area and enemy streams."""
    LEVELS = 20
    START, AREA_LO, AREA_HI = 0x8000, 0x8015, 0x80E7
    ENEMY_HI_HI, ENEMY_HI_LO, ENEMY_LO_HI, ENEMY_LO_LO = 0xA500, 0xA515, 0xA52A, 0xA53F
    WORLD_START = 0xE012                # fixed bank 15
    SPRITE_BANK = 0xFE00                # fixed bank 15, per world

    def __init__(self, rom: bytes):
        self.rom = rom
        self._cache = {}

    @staticmethod
    def offset(address: int) -> int:
        """File offset of a level/enemy data address (banks 8 and 9 at $8000-$BFFF)."""
        return HEADER + 0x10000 + address - 0x8000

    def at(self, address: int) -> int:
        return self.rom[self.offset(address)]

    def fixed(self, address: int) -> int:
        return self.rom[HEADER + 0x1C000 + address - 0xC000]

    def grass_tile(self, kind: int) -> int:
        return self.rom[HEADER + 6 * 0x2000 + (GRASS_TILES & 0x1FFF) + (kind - 0x20)]

    # ---- levels and worlds
    def world_of(self, level: int) -> int:
        """World counted from 0."""
        return max(w for w in range(7) if self.fixed(self.WORLD_START + w) <= level)

    def level_name(self, level: int) -> str:
        w = self.world_of(level)
        return f'{w + 1}-{level - self.fixed(self.WORLD_START + w) + 1}'

    def sprite_bank(self, world: int) -> int:
        return self.fixed(self.SPRITE_BANK + world)

    def area_address(self, level: int, area: int) -> int:
        i = self.at(self.START + level) + area
        return self.at(self.AREA_LO + i) | self.at(self.AREA_HI + i) << 8

    def enemy_address(self, level: int, area: int) -> int:
        hi = self.at(self.ENEMY_HI_LO + level) | self.at(self.ENEMY_HI_HI + level) << 8
        lo = self.at(self.ENEMY_LO_LO + level) | self.at(self.ENEMY_LO_HI + level) << 8
        return self.at(hi + area) << 8 | self.at(lo + area)

    def header(self, level: int, area: int) -> list:
        a = self.area_address(level, area)
        return [self.at(a + k) for k in range(4)]

    def horizontal(self, level: int, area: int) -> bool:
        return bool(self.header(level, area)[0] & 0x80)

    def pages(self, level: int, area: int) -> int:
        return (self.header(level, area)[2] >> 4) + 1

    # ---- streams
    def stream(self, level: int, area: int) -> list:
        """Area objects: [{'kind': 'object'|'door'|'pointer', 'index' (offset in the stream), 'page', 'row', 'col',
        'type', 'to' (level, area, page) for doors and pointers}]."""
        key = ("stream", level, area)
        if key in self._cache:
            return self._cache[key]
        start, world = self.area_address(level, area), self.world_of(level)
        i, page, row, out = 4, 0, 0, []
        while i < 0x100:
            b = self.at(start + i)
            if b == 0xFF:
                break
            if b >> 4 == 15:
                c = b & 15
                if c not in CMD_SIZE:
                    break
                if c == 5:
                    lv, ap = self.at(start + i + 1), self.at(start + i + 2)
                    out.append({'kind': 'pointer', 'index': i, 'page': page, 'row': 0, 'col': 0, 'type': None,
                                'to': (lv, ap >> 4, ap & 15), 'bytes': i + 1})
                elif c in (2, 3):
                    page, row = page + c - 1, 0
                elif c == 4:
                    page, row = 0, 0
                i += CMD_SIZE[c]
                continue
            row += b >> 4
            if row >= 15:
                row, page = row - 15, page + 1
            kind = self.at(start + i + 1)
            item = {'kind': 'object', 'index': i, 'page': page, 'row': row, 'col': b & 15, 'type': kind}
            if kind in DOORS and world not in (5, 6):
                lv, ap = self.at(start + i + 2), self.at(start + i + 3)
                item.update(kind='door', to=(lv, ap >> 4, ap & 15), bytes=i + 2)
                i += 4
            else:
                i += 2
            out.append(item)
        self._cache[key] = out
        return out

    def enemies(self, level: int, area: int) -> list:
        """[{'index' (offset in the stream, as $0441 keeps it), 'page', 'col', 'row', 'id'}]"""
        start, out, i = self.enemy_address(level, area), [], 0
        for page in range(self.pages(level, area)):
            n = self.at(start + i)
            for k in range(1, max(n, 1), 2):
                xy = self.at(start + i + k + 1)
                out.append({'index': i + k, 'page': page, 'col': xy >> 4, 'row': xy & 15, 'id': self.at(start + i + k)})
            i += max(n, 1)
        return out

    def areas(self, level: int) -> list:
        """The areas the game reaches in a level: area 0, every area a door, jar or vine of the level points at, and the
        jar room (area 4) when its data is its own."""
        key = ('areas', level)
        if key in self._cache:
            return self._cache[key]
        found, todo = {0}, [0]
        while todo:
            area = todo.pop()
            for o in self.stream(level, area):
                if o['kind'] in ('door', 'pointer') and o['to'][0] == level and o['to'][1] not in found and o['to'][1] < 10:
                    found.add(o['to'][1])
                    todo.append(o['to'][1])
        jar = self.area_address(level, 4)
        if 4 not in found and all(self.area_address(level, a) != jar for a in range(10) if a != 4):
            found.add(4)
        self._cache[key] = sorted(found)
        return self._cache[key]

    def pointer_writers(self, level: int, area: int) -> dict:
        """{page: the last door or pointer on that page}: the one whose area pointer the game keeps for the page."""
        out = {}
        for o in self.stream(level, area):
            if o['kind'] in ('door', 'pointer'):
                out[o['page']] = o
        return out

    def used_enemies(self) -> dict:
        """{sprite bank: set of enemy ids the game's own data places in a world with that bank}"""
        key = ('used',)
        if key not in self._cache:
            used = {}
            for level in range(self.LEVELS):
                bank = self.sprite_bank(self.world_of(level))
                for area in self.areas(level):
                    used.setdefault(bank, set()).update(e['id'] & 0x7F for e in self.enemies(level, area))
            self._cache[key] = used
        return self._cache[key]

    def destinations(self, level: int) -> list:
        """Every (level, area, page) the game's own doors and pointers in this level lead to."""
        seen = set()
        for area in self.areas(level):
            for o in self.stream(level, area):
                if o['kind'] in ('door', 'pointer'):
                    seen.add(o['to'])
        return sorted(seen)


def _place(horizontal: bool, page: int, col: int, row: int, tile: bool = False) -> tuple:
    """The bottom middle of an enemy spot (tile=False) or of a tile of the area's tile map, in the area's pixels (the
    camera's, as sprites use them). In vertical areas the game draws tile row r of a page 16 lines above row r of its
    sprites (measured: Mario stands at y 464 on the tile row that starts at 480, cam2.py)."""
    if horizontal:
        return page * 256 + col * 16 + 8, row * 16 + 16
    return col * 16 + 8, page * 240 + row * 16 + (0 if tile else 16)


def _here(ram, w) -> bool:
    if ram[NMI_MODE] != 0xC0 or ram[LEVEL] != w['level'] or ram[JAR] == 2:
        return False
    area = 4 if ram[JAR] == 1 else ram[AREA]
    return area == w['area']


def _camera(ram):
    if ram[HORIZONTAL]:
        return ram[SCROLL_X_HI] * 256 + ram[SCROLL_X], 0
    return 0, ram[SCROLL_Y_HI] * 240 + ram[SCROLL_Y]


class _EnemyWatcher(Watcher):
    """An enemy edit: which object the game spawns from that entry ($0441 + slot keeps the entry), or, for a removal,
    that nothing comes from it while its spot is on screen."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.shown = 0

    def see(self, ram, frame, run):
        w = self.w
        if not _here(ram, w):
            return False
        for slot in range(9):
            if ram[STATE + slot] and ram[ENTRY + slot] == w['index']:
                self.seen = ram[ID + slot]
                return True
        x, y = _camera(ram)
        if x - 16 <= w['x'] <= x + 240 and y - 16 <= w['y'] <= y + 240:
            self.shown += 1
        return self.shown > 30

    def result(self):
        w = self.w
        if self.seen is None and self.shown <= 30:
            return super().result()
        if w['wanted'] is None:
            ok = self.seen is None
            return {'state': 'good' if ok else 'bad',
                    'text': 'Played from the start, nothing comes out of that spot any more.' if ok
                    else f'Played from the start, the game still put an enemy (number {self.seen:#04x}) there.'}
        if self.seen == w['wanted']:
            return {'state': 'good', 'text': f'Played from the start, the game now puts {w["name"]} there.'}
        if self.seen is None:
            return {'state': 'bad', 'text': 'Played from the start, the spot was on screen but nothing appeared there.'}
        return {'state': 'bad', 'text': f'Played from the start, the game put enemy number {self.seen:#04x} there, not the one chosen.'}


class _TileWatcher(Watcher):
    """A grass or block edit: the tile the game builds into the area's tile map ($6000) for that spot."""
    every = 4

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if not _here(ram, w):
            return False
        self.seen = ram[CART + TILES - 0x6000 + w['page'] * 0xF0 + w['row'] * 16 + w['col']]
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if self.seen == w['tile']:
            return {'state': 'good', 'text': f'Played from the start, the game builds {w["name"]} there.'}
        return {'state': 'bad', 'text': f'Played from the start, the game built a different tile there (tile {self.seen:#04x}).'}


class _WayWatcher(Watcher):
    """A door edit: the area pointer the game keeps for that page ($051D + page * 2) once the area is built."""
    every = 4

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if not _here(ram, w):
            return False
        a = POINTERS + 2 * w['page']
        self.seen = (ram[a], ram[a + 1])
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        lv, area, page = w['to']
        if self.seen == (lv, area << 4 | page):
            return {'state': 'good', 'text': f'Played from the start, doors on this screen now lead to {w["name"]}.'}
        same = 'this level' if self.seen[0] == w['level'] else f'level number {self.seen[0]}'
        return {'state': 'bad', 'text': f'Played from the start, doors on this screen still lead to area {(self.seen[1] >> 4) + 1} '
                                        f'of {same}, screen {(self.seen[1] & 15) + 1}.'}


class SMB2Profile(SMB2Data, Profile):
    """Super Mario Bros. 2 on the common profile interface. Parts are {'level': 0-19, 'area': 0-9} (inside a jar, area
    4). Horizontal areas: x is the screen's left edge ($04BE/$04C0), y 0. Vertical areas: x 0, y the screen's top
    ($CA pages of 240 lines + $CB)."""
    name = 'Super Mario Bros. 2'
    sha256s = (SHA256,)

    def __init__(self, rom: bytes):
        SMB2Data.__init__(self, rom)

    def where(self, ram):
        if ram[NMI_MODE] != 0xC0 or ram[JAR] == 2 or ram[LEVEL] >= self.LEVELS or ram[AREA] > 9:
            return None
        area = 4 if ram[JAR] == 1 else ram[AREA]
        if self.horizontal(ram[LEVEL], area) != bool(ram[HORIZONTAL]):
            return None                 # the first frame after a door: the new area is set but the old one still shows
        x, y = _camera(ram)
        return {'part': {'level': ram[LEVEL], 'area': area}, 'x': x, 'y': y}

    def part_name(self, part):
        level, area = int(part['level']), int(part['area'])
        name = f'World {self.level_name(level)}, area {area + 1}'
        if area == 4 and not any(o['to'][1] == 4 for a in self.areas(level) for o in self.stream(level, a)
                                 if o['kind'] in ('door', 'pointer') and o['to'][0] == level):
            name += ' (the jar room)'
        return name

    def _part(self, part):
        level, area = int(part['level']), int(part['area'])
        if not 0 <= level < self.LEVELS or not 0 <= area <= 9:
            raise ValueError('That part of the game is not one ROMancer knows.')
        return level, area

    def _way_name(self, to) -> str:
        lv, area, page = to
        if lv >= self.LEVELS:
            return f'level {lv}, area {area + 1}, screen {page + 1}'
        return f'World {self.level_name(lv)}, area {area + 1}, screen {page + 1}'

    def choices(self):
        out = {'grass': [{'value': k, 'name': f'Grass with {v}'} for k, v in GRASS.items()],
               'blocks': [{'value': k, 'name': v} for k, v in BLOCKS.items()]}
        for bank, ids in self.used_enemies().items():
            out[f'enemies_{bank:02x}'] = [{'value': k, 'name': ENEMIES[k]} for k in sorted(ids & set(ENEMIES), key=lambda k: ENEMIES[k])]
        for level in range(self.LEVELS):
            out[f'ways_{level}'] = [{'value': lv << 8 | area << 4 | page, 'name': self._way_name((lv, area, page))}
                                    for lv, area, page in self.destinations(level)]
        return out

    def objects(self, part):
        level, area = self._part(part)
        horizontal = self.horizontal(level, area)
        bank = self.sprite_bank(self.world_of(level))
        out = []
        shared = [a for a in self.areas(level) if a != area and self.enemy_address(level, a) == self.enemy_address(level, area)]
        for e in self.enemies(level, area):
            kind = e['id']
            if kind & 0x80:
                continue                        # already switched off in the game's own data
            x, y = _place(horizontal, e['page'], e['col'], e['row'])
            item = {'id': f'enemy:{e["index"]}', 'type': kind, 'x': x, 'y': y, 'remove': None}
            if kind in ENEMIES:
                item.update(style='enemy', name=ENEMIES[kind], remove='Remove this enemy',
                            fields=[{'key': 'kind', 'label': 'Swap for', 'value': kind, 'choices': f'enemies_{bank:02x}'}])
                if kind not in self.used_enemies().get(bank, ()):
                    item['fields'] = []
            elif kind in FIXED:
                item.update(style='item' if kind in ITEMS else 'enemy', name=FIXED[kind], fields=[],
                            note='The level needs this to be finished, or it is not a plain enemy, so ROMancer leaves it as it is.')
            else:
                item.update(style='enemy', name=f'Enemy {kind:#04x}', fields=[])
            if shared:
                item['note'] = (item.get('note', '') + ' ' if item.get('note') else '') + \
                    f'These enemies are shared with area {shared[0] + 1}, so a change shows there too.'
            out.append(item)
        writers = self.pointer_writers(level, area)
        doors_on = {}
        for o in self.stream(level, area):
            if o['kind'] in ('object', 'door') and o['type'] in DOORS:
                doors_on.setdefault(o['page'], []).append(o)
        for o in self.stream(level, area):
            t = o['type']
            if o['kind'] == 'object' and t in GRASS:
                x, y = _place(horizontal, o['page'], o['col'], o['row'], True)
                out.append({'id': f'grass:{o["index"]}', 'style': 'item', 'type': f'grass{t:02x}', 'name': 'Grass',
                            'detail': f'gives {GRASS[t]}', 'x': x, 'y': y, 'remove': None,
                            'fields': [{'key': 'gives', 'label': 'Pulling it gives', 'value': t, 'choices': 'grass'}],
                            'note': 'In subspace the game gives coins for pulled grass instead.' if t != 0x27 else
                                    'The game gives this 1-up only once a game; after that the grass gives a small vegetable.'})
            elif o['kind'] == 'object' and t in BLOCKS:
                x, y = _place(horizontal, o['page'], o['col'], o['row'], True)
                out.append({'id': f'block:{o["index"]}', 'style': 'item', 'type': f'block{t:02x}', 'name': BLOCKS[t],
                            'x': x, 'y': y, 'remove': None,
                            'fields': [{'key': 'block', 'label': 'Block', 'value': t, 'choices': 'blocks'}]})
            if o['kind'] in ('door', 'pointer'):
                live = writers.get(o['page']) is o
                doors = doors_on.get(o['page'], [])
                spot = o if o['kind'] == 'door' else (doors[0] if doors else None)
                if spot is not None:
                    x, y = _place(horizontal, spot['page'], spot['col'], spot['row'] + 1, True)
                    name = DOORS[spot['type']] if o['kind'] == 'door' else 'Where doors and jars on this screen lead'
                else:
                    x, y = _place(horizontal, o['page'], 7, 2, True)
                    name = 'Where jars and vines on this screen lead'
                item = {'id': f'way:{o["index"]}', 'style': 'secret', 'type': 'way', 'name': name,
                        'detail': f'leads to {self._way_name(o["to"])}', 'x': x, 'y': y, 'remove': None, 'fields': []}
                if live:
                    lv, ar, pg = o['to']
                    item['fields'] = [{'key': 'to', 'label': 'Leads to', 'value': lv << 8 | ar << 4 | pg, 'choices': f'ways_{level}'}]
                    item['note'] = 'The game keeps one place to go for each screen: every door, jar and vine on this screen leads there.'
                else:
                    item['note'] = 'Another door or pointer later on this screen replaces this one, so the game never uses it.'
                out.append(item)
        return out

    def edit(self, part, object_id, values, remove=False):
        level, area = self._part(part)
        kind, _, number = str(object_id).partition(':')
        index = int(number)
        where = self.part_name(part)
        horizontal = self.horizontal(level, area)
        if kind == 'enemy':
            e = next((r for r in self.enemies(level, area) if r['index'] == index), None)
            if e is None or e['id'] not in ENEMIES:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            byte = self.offset(self.enemy_address(level, area) + index)
            old = self.rom[byte]
            x, y = _place(horizontal, e['page'], e['col'], e['row'])
            watch = {'kind': 'enemy', 'level': level, 'area': area, 'index': index, 'x': x, 'y': y}
            if remove:
                return {'writes': [(byte, old, old | 0x80)], 'title': f'Remove the {ENEMIES[old]} ({where}, screen {e["page"] + 1})',
                        'watch': {**watch, 'wanted': None, 'name': ''}}
            new = int(values.get('kind'))
            bank = self.sprite_bank(self.world_of(level))
            if new not in ENEMIES or new not in self.used_enemies().get(bank, ()):
                raise ValueError('That choice is not one of the game’s own.')
            name = ENEMIES[new]
            return {'writes': [(byte, old, new)] if old != new else [],
                    'title': f'Enemy here: {name} ({where}, screen {e["page"] + 1})',
                    'watch': {**watch, 'wanted': new, 'name': 'a ' + name}}
        if kind in ('grass', 'block'):
            o = next((r for r in self.stream(level, area) if r['index'] == index and r['kind'] == 'object'), None)
            table = GRASS if kind == 'grass' else BLOCKS
            if o is None or o['type'] not in table:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            new = int(values.get('gives' if kind == 'grass' else 'block'))
            if new not in table:
                raise ValueError('That choice is not one of the game’s own.')
            byte = self.offset(self.area_address(level, area) + index + 1)
            old = self.rom[byte]
            tile = self.grass_tile(new) if kind == 'grass' else BLOCK_TILES[new]
            label = f'grass with {GRASS[new]}' if kind == 'grass' else 'a ' + BLOCKS[new].replace('Mushroom', 'mushroom')
            return {'writes': [(byte, old, new)] if old != new else [],
                    'title': f'{"Grass gives " + GRASS[new] if kind == "grass" else "Block: " + BLOCKS[new]} ({where}, screen {o["page"] + 1})',
                    'watch': {'kind': 'tile', 'level': level, 'area': area, 'page': o['page'], 'row': o['row'],
                              'col': o['col'], 'tile': tile, 'name': label}}
        if kind == 'way':
            o = next((r for r in self.stream(level, area) if r['index'] == index and r['kind'] in ('door', 'pointer')), None)
            if o is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            if self.pointer_writers(level, area).get(o['page']) is not o:
                raise ValueError('The game never uses this one: another door or pointer later on this screen replaces it.')
            value = int(values.get('to'))
            to = (value >> 8, value >> 4 & 15, value & 15)
            if to not in self.destinations(level):
                raise ValueError('That choice is not one of the game’s own.')
            start = self.area_address(level, area) + o['bytes']
            writes = []
            for k, new in enumerate((to[0], to[1] << 4 | to[2])):
                byte = self.offset(start + k)
                if self.rom[byte] != new:
                    writes.append((byte, self.rom[byte], new))
            name = self._way_name(to)
            return {'writes': writes, 'title': f'Doors on screen {o["page"] + 1} lead to {name} ({where})',
                    'watch': {'kind': 'way', 'level': level, 'area': area, 'page': o['page'], 'to': to, 'name': name}}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        if watch['kind'] == 'enemy':
            return _EnemyWatcher(watch)
        if watch['kind'] == 'tile':
            return _TileWatcher(watch)
        if watch['kind'] == 'way':
            return _WayWatcher(watch)
        return Watcher()


PROFILES = [SMB2Profile]
