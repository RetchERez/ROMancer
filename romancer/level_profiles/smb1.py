"""Super Mario Bros. (World), NES: areas, enemies, block contents, hidden blocks and where pipes lead.

Everything here was read from the game's code and proven by replaying the game (research/smb1-level-profile.md).

The game is NROM: 32 KB of program at CPU $8000-$FFFF (file offset = 16 + address - $8000).

* Which area plays: $9C13 picks the area pointer from WorldAddrOffsets $9CB4 (one byte per world) + AreaNumber into
  AreaAddrOffsets $9CBC. An area pointer is type (bits 5-6: 0 water, 1 ground, 2 underground, 3 castle) and number
  (bits 0-4); bit 7 is free (the enemy data uses it as a page flag). $9C22 turns it into the two streams: enemy data
  from $9CE0[type] + number into $9CE4 / $9D06 (low / high) and area data from $9D28[type] + number into $9D2C / $9D4E.
  It keeps the loaded area in $074E (type) and $074F (number); $0750 is only the next area a pipe or vine leads to.
* Area data ($9508): a two byte header, then two bytes per object, $FD ends. Byte 1: column (high nibble), row (low
  nibble). Byte 2: bit 7 = on the next page (once per object). Row $D with bit 6 clear selects a page. Rows 0-$B with
  bits 4-6 clear are single blocks whose low nibble picks the contents ($9B0E, $9B01, $9B19, $9B14): metatile from
  $BDE8 (bricks use the next five in areas that are not ground).
* Enemy data ($C144): two bytes per entry, $FF ends. Byte 1: column, row. Byte 2: bit 7 = next page (once per page),
  bit 6 = only in the harder levels ($06CC, set from World 5-3 on and in the second quest, $9032), bits 0-5 the enemy.
  Row $F selects a page (byte 2 & $3F) when no page flag was taken just before it. Row $E is three bytes: the area a
  pipe or vine leads to (byte 2, stored in $0750) and, when the world in byte 3's top three bits is this one, the
  page to come out on (byte 3 & $1F, stored in $0751).
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER = 16
SHA256 = '0b3d9e1f01ed1668205bab34d6c82b0e281456e137352e4f36a9b2cfa3b66dea'

# RAM
WORLD, LEVEL, AREA_TYPE, AREA_NUMBER, NEXT_AREA, NEXT_PAGE = 0x75F, 0x75C, 0x74E, 0x74F, 0x750, 0x751
MODE, SCREEN_PAGE, SCREEN_X = 0x770, 0x71A, 0x71C
ENEMY_INDEX = 0x739                  # how far the enemy data has been read
FLAG, ID, PAGE, X, FRENZY = 0x0F, 0x16, 0x6E, 0x87, 0x6CB
BLOCKS = (0x500, 0x5D0)              # block buffers for even and odd pages: row * 16 + column

TYPES = {0: 'water', 1: 'ground', 2: 'underground', 3: 'castle'}

# Enemy numbers the game's enemy data uses. Each was spawned in World 1-1 in place of the first Goomba and looked at
# (trace/v15_profiles/smb1/enemy_types_sheet.png, spawn2_*.png, walk_*.png; lifts measured by their movement).
ENEMIES = {
    0x00: 'Green Koopa Troopa', 0x02: 'Buzzy Beetle', 0x03: 'Red Koopa Troopa', 0x05: 'Hammer Bro', 0x06: 'Goomba',
    0x07: 'Blooper', 0x0A: 'Green Cheep Cheep', 0x0C: 'Podoboo (lava fireball)', 0x0E: 'Green Koopa Paratroopa (jumping)',
    0x0F: 'Red Koopa Paratroopa', 0x10: 'Green Koopa Paratroopa (flying)', 0x11: 'Lakitu', 0x15: 'Bowser’s fire',
    0x17: 'Stream of Bullet Bills', 0x1B: 'Fire bar (clockwise)', 0x1C: 'Fast fire bar (clockwise)',
    0x1D: 'Fire bar (anticlockwise)', 0x1F: 'Long fire bar', 0x24: 'Pulley lift (one of a balanced pair)',
    0x25: 'Lift moving up and down', 0x26: 'Lift going up', 0x27: 'Lift going down', 0x28: 'Lift moving left and right',
    0x29: 'Lift that falls when stood on', 0x2A: 'Lift that moves right when stood on', 0x2B: 'Short lift going up',
    0x2C: 'Short lift going down', 0x2D: 'Bowser', 0x34: 'Warp zone', 0x35: 'Toad', 0x37: 'Two Goombas',
    0x38: 'Three Goombas', 0x39: 'Two Goombas, higher up', 0x3A: 'Three Goombas, higher up',
    0x3B: 'Two Green Koopa Troopas', 0x3C: 'Three Green Koopa Troopas',
}
GROUPS = {0x37: 0x06, 0x38: 0x06, 0x39: 0x06, 0x3A: 0x06, 0x3B: 0x00, 0x3C: 0x00}     # $C71B: what a group spawns
GROUP_ROW = {0x37: 11, 0x38: 11, 0x39: 7, 0x3A: 7, 0x3B: 11, 0x3C: 11}                  # $C732: y $B0 or $70 (row 11 or 7)
FRENZIES = {0x15, 0x16, 0x17}                                                           # $C7A0: kept in $06CB

# What a single block holds (low nibble of byte 2), proven by jumping into 1-1's first block with each value
# (trace/v15_profiles/smb1/block_contents_sheet.png, blocks.json)
CONTENTS = {0: 'Question block with a power-up', 1: 'Question block with a coin', 2: 'Hidden block with a coin',
            3: 'Hidden block with a 1-up', 4: 'Brick with a power-up', 5: 'Brick with a vine', 6: 'Brick with a star',
            7: 'Brick with several coins', 8: 'Brick with a 1-up'}
HOLDS = {0: 'a power-up', 1: 'a coin', 2: 'a coin', 3: 'a 1-up', 4: 'a power-up', 5: 'a vine', 6: 'a star',
         7: 'several coins', 8: 'a 1-up'}
HIDDEN = {2, 3}


class SMB1Data:
    """Reads the game's area tables and object streams."""
    WORLDS = 0x9CB4
    AREAS = 0x9CBC
    ENEMY_START, ENEMY_LOW, ENEMY_HIGH = 0x9CE0, 0x9CE4, 0x9D06
    AREA_START, AREA_LOW, AREA_HIGH = 0x9D28, 0x9D2C, 0x9D4E
    METATILES = 0xBDE8

    def __init__(self, rom: bytes):
        self.rom = rom

    @staticmethod
    def offset(address: int) -> int:
        return HEADER + address - 0x8000

    def at(self, address: int) -> int:
        return self.rom[self.offset(address)]

    # ---- areas
    def area_count(self) -> list:
        """How many areas of each type the game has (from where each type starts in the pointer tables)."""
        starts = [self.at(self.AREA_START + t) for t in range(4)] + [self.AREA_HIGH - self.AREA_LOW]
        order = sorted(range(4), key=lambda t: starts[t])
        counts = [0] * 4
        for i, t in enumerate(order):
            following = starts[order[i + 1]] if i + 1 < 4 else starts[4]
            counts[t] = following - starts[t]
        return counts

    def all_areas(self) -> list:
        return [t << 5 | n for t, count in enumerate(self.area_count()) for n in range(count)]

    def area_data(self, area: int) -> int:
        i = self.at(self.AREA_START + ((area >> 5) & 3)) + (area & 0x1F)
        return self.at(self.AREA_LOW + i) | self.at(self.AREA_HIGH + i) << 8

    def enemy_data(self, area: int) -> int:
        i = self.at(self.ENEMY_START + ((area >> 5) & 3)) + (area & 0x1F)
        return self.at(self.ENEMY_LOW + i) | self.at(self.ENEMY_HIGH + i) << 8

    def world_areas(self) -> list:
        """[[area pointer for each AreaNumber] for each world]."""
        starts = [self.at(self.WORLDS + w) for w in range(8)]
        ends = starts[1:] + [self.ENEMY_START - self.AREAS]       # the area list runs up to the next table
        return [[self.at(self.AREAS + i) & 0x7F for i in range(a, b)] for a, b in zip(starts, ends)]

    def levels(self) -> dict:
        """{(world, level): (main area, way-in area or None)}, both counted from 1. A world with five areas has a short
        way-in area before its second level (the pipe the player walks into)."""
        out = {}
        for w, areas in enumerate(self.world_areas()):
            if len(areas) == 5:
                out[(w + 1, 1)] = (areas[0], None)
                out[(w + 1, 2)] = (areas[2], areas[1])
                out[(w + 1, 3)] = (areas[3], None)
                out[(w + 1, 4)] = (areas[4], None)
            else:
                for level, area in enumerate(areas[:4]):
                    out[(w + 1, level + 1)] = (area, None)
        return out

    @staticmethod
    def hard(world: int, level: int) -> bool:
        """$9032 (first quest): entries marked for the harder levels appear from World 5-3 on."""
        return world > 5 or (world == 5 and level >= 3)

    # ---- streams
    def objects(self, area: int) -> list:
        """Area objects ($9508): [{'index', 'byte' (file offset of byte 1), 'page', 'col', 'row', 'value'}]."""
        start, i, page, taken, out = self.area_data(area), 2, 0, False, []
        while i < 0x400:
            b0 = self.at(start + i)
            if b0 == 0xFD:
                break
            b1 = self.at(start + i + 1)
            if b1 & 0x80 and not taken:
                page, taken = page + 1, True
            if b0 & 15 == 13 and not b1 & 0x40 and not taken:
                page = b1 & 0x1F
            else:
                out.append({'index': i, 'byte': self.offset(start + i), 'page': page, 'col': b0 >> 4, 'row': b0 & 15,
                            'value': b1 & 0x7F})
            taken = False
            i += 2
        return out

    def enemies(self, area: int, data: bytes = None) -> list:
        """Enemy data ($C144). [{'kind': 'enemy'|'way'|'page', 'index', 'byte', 'page', 'col', 'row', ...}]. `data`
        reads a changed copy of the stream instead (to check an edit)."""
        start = self.enemy_data(area)
        read = (lambda k: data[k]) if data is not None else (lambda k: self.at(start + k))
        i, page, taken, out = 0, 0, False, []
        while i < 0x200:
            b0 = read(i)
            if b0 == 0xFF:
                break
            b1 = read(i + 1)
            if b1 & 0x80 and not taken:
                page, taken = page + 1, True
            row = b0 & 15
            base = {'index': i, 'byte': self.offset(start + i), 'page': page, 'col': b0 >> 4, 'row': row}
            if row == 15 and not taken:
                page, taken = b1 & 0x3F, True
                out.append({**base, 'kind': 'page', 'page': page})
                i += 2
                continue
            if row == 14:
                b2 = read(i + 2)
                out.append({**base, 'kind': 'way', 'to': b1 & 0x7F, 'world': b2 >> 5, 'at': b2 & 0x1F})
                i += 3
            else:
                out.append({**base, 'kind': 'enemy', 'id': b1 & 0x3F, 'hard': bool(b1 & 0x40)})
                i += 2
            taken = False
        return out

    def enemy_stream(self, area: int) -> bytes:
        start, rows = self.enemy_data(area), self.enemies(area)
        end = (rows[-1]['index'] + (3 if rows[-1]['kind'] == 'way' else 2)) if rows else 0
        return bytes(self.at(start + k) for k in range(end + 1))

    def metatile(self, contents: int, area_type: int) -> int:
        """The metatile the game puts in the block buffer for a single block ($9B0E-$9B2C)."""
        index = contents if contents in (0, 1, 2) or (contents == 3 and area_type == 1) else contents + (0 if area_type == 1 else 5)
        return self.at(self.METATILES + index)

    # ---- edits
    def remove_writes(self, area: int, index: int) -> list:
        """Writes that take an enemy out of the data without moving anything: its two bytes become a page select for
        the page the next entry is on, so every other entry keeps its page. Checked by reading the stream again; [] when
        that cannot be done here."""
        rows = self.enemies(area)
        at = next((k for k, r in enumerate(rows) if r['index'] == index and r['kind'] == 'enemy'), None)
        if at is None:
            return []
        later = rows[at + 1] if at + 1 < len(rows) else None
        page = later['page'] if later else rows[at]['page']
        if page > 0x3F:
            return []
        old = self.enemy_stream(area)
        new = bytearray(old)
        new[index], new[index + 1] = (old[index] & 0xF0) | 0x0F, page
        before = [r for r in rows if r['index'] != index and r['kind'] != 'page']
        after = [r for r in self.enemies(area, bytes(new)) if r['kind'] != 'page']
        strip = lambda r: {k: v for k, v in r.items() if k != 'byte'}
        if [strip(r) for r in before] != [strip(r) for r in after]:
            return []
        byte = rows[at]['byte']
        return [(byte + k, old[index + k], new[index + k]) for k in (0, 1) if old[index + k] != new[index + k]]


def _list(names: list) -> str:
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]


class _EnemyWatcher(Watcher):
    """An enemy edit: once the game has read past the entry ($0739) in that area, which enemy appeared where it is."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.passed = None
        self.seen = []
        self.done = False

    def see(self, ram, frame, run):
        w = self.w
        if ram[MODE] != 1 or (ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]) != w['area'] or ram[WORLD] != w['world'] - 1:
            return False
        if ram[ENEMY_INDEX] <= w['index']:
            return self.passed is not None and frame - self.passed > 16
        if self.passed is None:
            self.passed = frame
        reach = 96 if w['wanted'] in GROUPS else 6
        for slot in range(6):
            if ram[FLAG + slot]:
                where = ram[PAGE + slot] * 256 + ram[X + slot]
                if abs(where - w['x']) <= reach:
                    self.seen.append(ram[ID + slot])
        if w['wanted'] in FRENZIES and ram[FRENZY]:
            self.seen.append(ram[FRENZY])
        return frame - self.passed > 16

    def result(self):
        w = self.w
        if self.passed is None:
            return super().result()
        wanted = w['wanted']
        if wanted is None:
            ok = not self.seen
            return {'state': 'good' if ok else 'bad',
                    'text': 'Played from the start, no enemy appears there any more.' if ok
                    else f'Played from the start, an enemy (number {self.seen[0]:#04x}) still appears there.'}
        spawns = {GROUPS.get(wanted, wanted)}
        if GROUPS.get(wanted, wanted) == 0x06:
            spawns.add(0x02)            # the second quest turns Goombas into Buzzy Beetles
        ok = any(s in spawns for s in self.seen)
        if ok:
            return {'state': 'good', 'text': f'Played from the start, the game now puts {w["name"]} there.'}
        if self.seen:
            return {'state': 'bad', 'text': f'Played from the start, the game put enemy number {self.seen[0]:#04x} there, not the one chosen.'}
        return {'state': 'bad', 'text': 'Played from the start, the game read that entry but nothing chosen appeared there.'}


class _BlockWatcher(Watcher):
    """A block edit: the metatile the game builds into its block buffer for that spot once the spot is on screen."""
    every = 4

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if ram[MODE] != 1 or (ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]) != w['area'] or ram[WORLD] != w['world'] - 1:
            return False
        left = ram[SCREEN_PAGE] * 256 + ram[SCREEN_X]
        x = w['page'] * 256 + w['col'] * 16
        if not left <= x <= left + 240:
            return False
        self.seen = ram[BLOCKS[w['page'] & 1] + w['row'] * 16 + w['col']]
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if self.seen == w['metatile']:
            return {'state': 'good', 'text': f'Played from the start, the game builds the block as chosen: {w["name"].lower()}.'}
        if self.seen == 0xC4 and w['metatile'] != 0xC4:
            return {'state': 'warn', 'text': 'Played from the start, the block had already been hit when it came on screen, so what it holds could not be seen.'}
        text = f'Played from the start, the game built a different block there (metatile {self.seen:#04x}).'
        if w['contents'] == 3:
            text += ' The game only shows a hidden 1-up block while its 1-up flag is set.'
        return {'state': 'bad', 'text': text}


class _WayWatcher(Watcher):
    """A pipe target edit: once the game has read the entry, the area ($0750) and page ($0751) a pipe or vine now leads to."""
    every = 4

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if ram[MODE] != 1 or (ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]) != w['area'] or ram[WORLD] != w['world'] - 1:
            return False
        if ram[ENEMY_INDEX] <= w['index']:
            return False
        self.seen = (ram[NEXT_AREA] & 0x7F, ram[NEXT_PAGE])
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if self.seen == (w['to'], w['at']):
            return {'state': 'good', 'text': f'Played from the start, the game now sends pipes and vines here to {w["name"]}.'}
        return {'state': 'bad', 'text': f'Played from the start, pipes and vines here still lead to area {self.seen[0]:#04x}, screen {self.seen[1] + 1}.'}


class SMB1Profile(SMB1Data, Profile):
    """Super Mario Bros. on the common profile interface. Parts are {'world', 'level', 'area'} (world and level counted
    from 1, area = the area pointer without bit 7); x is the screen's left edge in the area's pixels ($071A/$071C)."""
    name = 'Super Mario Bros.'
    sha256s = (SHA256,)

    def __init__(self, rom: bytes):
        SMB1Data.__init__(self, rom)
        self._levels = None

    # ---- where
    def where(self, ram):
        if ram[MODE] != 1:
            return None
        world, level = ram[WORLD] + 1, ram[LEVEL] + 1
        if not 1 <= world <= 8 or not 1 <= level <= 4 or ram[AREA_TYPE] > 3:
            return None
        return {'part': {'world': world, 'level': level, 'area': ram[AREA_TYPE] << 5 | ram[AREA_NUMBER]},
                'x': ram[SCREEN_PAGE] * 256 + ram[SCREEN_X], 'y': 8}

    def level_table(self) -> dict:
        if self._levels is None:
            self._levels = self.levels()
        return self._levels

    def area_title(self, area: int) -> str:
        """A name for an area from the levels that use it."""
        mains = [f'{w}-{l}' for (w, l), (main, _) in sorted(self.level_table().items()) if main == area]
        if mains:
            return f'World {_list(mains)}'
        ways = [f'{w}-{l}' for (w, l), (_, way) in sorted(self.level_table().items()) if way == area]
        if ways:
            return f'the way into World {_list(ways)}'
        return f'{TYPES[(area >> 5) & 3].capitalize()} side area {area & 0x1F}'

    def part_name(self, part):
        world, level, area = int(part['world']), int(part['level']), int(part['area'])
        main, way = self.level_table().get((world, level), (None, None))
        name = f'World {world}-{level}'
        if area == main:
            return name
        if area == way:
            return name + ', the way in'
        title = self.area_title(area)
        return name + (f', in the area of {title}' if title.startswith('World') else ', ' + title[0].lower() + title[1:])

    # ---- objects
    def choices(self):
        ways, seen = [], set()
        for area in self.all_areas():
            for row in self.enemies(area):
                if row['kind'] == 'way' and (row['to'], row['at']) not in seen:
                    seen.add((row['to'], row['at']))
        for to, at in sorted(seen):
            title = self.area_title(to)
            ways.append({'value': to << 5 | at, 'name': f'{title[0].upper() + title[1:]}, screen {at + 1}'})
        return {'enemies': [{'value': k, 'name': v} for k, v in sorted(ENEMIES.items(), key=lambda kv: kv[1])],
                'blocks': [{'value': k, 'name': v} for k, v in CONTENTS.items()],
                'ways': ways}

    @staticmethod
    def enemy_name(kind: int) -> str:
        return ENEMIES.get(kind, f'Enemy {kind:#04x}')

    def _here(self, part):
        world, level, area = int(part['world']), int(part['level']), int(part['area'])
        if area not in self.all_areas():
            raise ValueError('That part of the game is not one ROMancer knows.')
        return world, level, area

    def objects(self, part):
        world, level, area = self._here(part)
        hard, out = self.hard(world, level), []
        rows = self.enemies(area)
        pipes = [o for o in self.objects_raw(area) if self._enterable(o)]
        for row in rows:
            if row['kind'] == 'enemy':
                if row['hard'] and not hard:
                    continue
                notes = []
                if row['hard']:
                    notes.append('This enemy appears only in the harder levels (from World 5-3 on, and in the second quest).')
                if GROUPS.get(row['id'], row['id']) == 0x06:
                    notes.append('In the second quest the game turns Goombas into Buzzy Beetles.')
                if row['id'] in GROUPS:
                    notes.append('A group appears at the right edge of the screen when the game reads it, a little before this spot.')
                removable = bool(self.remove_writes(area, row['index']))
                if not removable:
                    notes.append('This one cannot be removed without moving other enemies, so it can only be swapped.')
                item = {'id': f'enemy:{row["index"]}', 'style': 'enemy', 'type': row['id'], 'name': self.enemy_name(row['id']),
                        'x': row['page'] * 256 + row['col'] * 16 + 8, 'y': 32 + GROUP_ROW.get(row['id'], row['row']) * 16,
                        'fields': [{'key': 'kind', 'label': 'Swap for', 'value': row['id'], 'choices': 'enemies'}],
                        'remove': 'Remove this enemy' if removable else None}
                if notes:
                    item['note'] = ' '.join(notes)
                out.append(item)
            elif row['kind'] == 'way' and row['world'] == world - 1:
                start = row['page'] * 256 + row['col'] * 16
                later = [w for w in rows if w['kind'] == 'way' and w['world'] == world - 1 and w['index'] > row['index']]
                end = later[0]['page'] * 256 + later[0]['col'] * 16 if later else 1 << 16
                pipe = next((p for p in pipes if start - 64 <= p['page'] * 256 + p['col'] * 16 < end), None)
                title = self.area_title(row['to'])
                target = f'{title}, screen {row["at"] + 1}'
                item = {'id': f'way:{row["index"]}', 'style': 'secret', 'type': 'way',
                        'name': 'Where this pipe leads' if pipe else 'Where pipes and vines lead',
                        'detail': f'to {target[0].lower() + target[1:] if not target.startswith("World") else target}',
                        'fields': [{'key': 'to', 'label': 'Leads to', 'value': row['to'] << 5 | row['at'], 'choices': 'ways'}],
                        'remove': None,
                        'note': 'The game uses the last of these it has read for every pipe and vine that leads somewhere, '
                                'so this one counts from here until the next one.'}
                if pipe:
                    # a vertical pipe: its top; the sideways way-out pipe: its opening, which stands on the floor
                    top = 32 + pipe['row'] * 16 if pipe['row'] <= 11 else 208
                    item.update(x=pipe['page'] * 256 + pipe['col'] * 16 + 16, y=top)
                else:
                    item.update(x=start + 8, y=48)
                out.append(item)
        for obj in self.objects_raw(area):
            if obj['row'] > 11 or obj['value'] & 0x70 or obj['value'] > 8:
                continue
            n = obj['value']
            item = {'id': f'block:{obj["index"]}', 'style': 'secret' if n in HIDDEN else 'item', 'type': f'block{n}',
                    'name': CONTENTS[n].split(' with ')[0], 'detail': f'holds {HOLDS[n]}',
                    'x': obj['page'] * 256 + obj['col'] * 16 + 8, 'y': 48 + obj['row'] * 16,
                    'fields': [{'key': 'holds', 'label': 'Block', 'value': n, 'choices': 'blocks'}], 'remove': None}
            notes = []
            if n == 3:
                notes.append('The game shows a hidden 1-up block only while its 1-up flag is set: at the start of a game '
                             'or a world, or after enough coins in the level before.')
            if n == 5:
                notes.append('The vine climbs to where this area’s pipes and vines lead.')
            if notes:
                item['note'] = ' '.join(notes)
            out.append(item)
        return out

    def objects_raw(self, area: int) -> list:
        return SMB1Data.objects(self, area)

    @staticmethod
    def _enterable(obj) -> bool:
        """A pipe the player can go down ($9604: a vertical pipe with bit 3 set) or the sideways way-out pipe (row $F, $4x)."""
        return (obj['row'] <= 11 and obj['value'] & 0x78 == 0x78) or (obj['row'] == 15 and obj['value'] & 0x70 == 0x40)

    # ---- edits
    def edit(self, part, object_id, values, remove=False):
        world, level, area = self._here(part)
        kind, _, number = str(object_id).partition(':')
        index = int(number)
        where = f'{self.part_name(part)}'
        if kind == 'enemy':
            row = next((r for r in self.enemies(area) if r['kind'] == 'enemy' and r['index'] == index), None)
            if row is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            x = row['page'] * 256 + row['col'] * 16
            if remove:
                writes = self.remove_writes(area, index)
                if not writes:
                    raise ValueError('This enemy cannot be removed without moving other enemies. Swap it for another instead.')
                return {'writes': writes, 'title': f'Remove the {self.enemy_name(row["id"])} ({where}, screen {row["page"] + 1})',
                        'watch': {'kind': 'enemy', 'area': area, 'world': world, 'index': index, 'x': x, 'wanted': None, 'name': ''}}
            new = int(values.get('kind'))
            if new not in ENEMIES:
                raise ValueError('That choice is not one of the game’s own.')
            byte = row['byte'] + 1
            old = self.rom[byte]
            value = (old & 0xC0) | new
            name = self.enemy_name(new)
            return {'writes': [(byte, old, value)] if old != value else [],
                    'title': f'Enemy here: {name} ({where}, screen {row["page"] + 1})',
                    'watch': {'kind': 'enemy', 'area': area, 'world': world, 'index': index, 'x': x, 'wanted': new,
                              'name': name if name.startswith(('Two', 'Three', 'Bowser', 'Toad')) else 'a ' + name[0].lower() + name[1:] if name.startswith(('Stream', 'Lift', 'Short', 'Long', 'Fire', 'Fast', 'Pulley', 'Warp')) else 'a ' + name}}
        if kind == 'block':
            obj = next((o for o in self.objects_raw(area) if o['index'] == index), None)
            if obj is None or obj['row'] > 11 or obj['value'] & 0x70 or obj['value'] > 8:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            n = int(values.get('holds'))
            if n not in CONTENTS:
                raise ValueError('That choice is not one of the game’s own.')
            byte = obj['byte'] + 1
            old = self.rom[byte]
            value = (old & 0xF0) | n
            return {'writes': [(byte, old, value)] if old != value else [],
                    'title': f'Block: {CONTENTS[n].lower()} ({where}, screen {obj["page"] + 1})',
                    'watch': {'kind': 'block', 'area': area, 'world': world, 'page': obj['page'], 'col': obj['col'],
                              'row': obj['row'], 'contents': n, 'metatile': self.metatile(n, (area >> 5) & 3), 'name': CONTENTS[n]}}
        if kind == 'way':
            row = next((r for r in self.enemies(area) if r['kind'] == 'way' and r['index'] == index), None)
            if row is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            value = int(values.get('to'))
            to, at = value >> 5, value & 0x1F
            if to not in self.all_areas():
                raise ValueError('That choice is not one of the game’s own.')
            writes = []
            b1, b2 = row['byte'] + 1, row['byte'] + 2
            new1, new2 = (self.rom[b1] & 0x80) | to, (self.rom[b2] & 0xE0) | at
            for byte, new in ((b1, new1), (b2, new2)):
                if self.rom[byte] != new:
                    writes.append((byte, self.rom[byte], new))
            title = self.area_title(to)
            name = f'{title}, screen {at + 1}'
            return {'writes': writes, 'title': f'Pipes lead to {name[0].lower() + name[1:] if not name.startswith("World") else name} ({where})',
                    'watch': {'kind': 'way', 'area': area, 'world': world, 'index': index, 'to': to, 'at': at,
                              'name': name[0].lower() + name[1:] if not name.startswith('World') else name}}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        if watch['kind'] == 'enemy':
            return _EnemyWatcher(watch)
        if watch['kind'] == 'block':
            return _BlockWatcher(watch)
        if watch['kind'] == 'way':
            return _WayWatcher(watch)
        return Watcher()


PROFILES = [SMB1Profile]
