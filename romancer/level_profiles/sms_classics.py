"""Level profiles for Master System classics: Sonic The Hedgehog, Alex Kidd in Miracle World, Wonder Boy and Wonder Boy III.

Each game's tables were found by reading its Z80 code and proven by replaying the game with a changed ROM (research notes:
research/sms_classics-level-profile.md). Master System RAM is the 8 KB at CPU $C000-$DFFF; the snapshot's 'wram' domain
holds it with index 0 = $C000, so RAM address A is ram[A - $C000].
"""
from __future__ import annotations

from . import Profile, Watcher

RAM = 0xC000


def _w(ram, address):
    return ram[address - RAM] | ram[address - RAM + 1] << 8


def _b(ram, address):
    return ram[address - RAM]


class _Sms(Profile):
    system = 'sms'

    def word(self, offset):
        return self.rom[offset] | self.rom[offset + 1] << 8

    def tile_role(self, tile):
        return None


# ------------------------------------------------------------------------------------------------------------- Sonic

class _SonicWatcher(Watcher):
    """A Sonic object edit. Every object of a level is loaded at once when the level starts, record n into object slot
    n + 1 (slots of 26 bytes from $D3FC: +0 type, +2/+3 x, +5/+6 y, $FF = empty). Looks at the slot the first time the
    level is loaded with that slot still at the record's own position."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if SonicProfile.loaded_level(ram) != w['level'] or _b(ram, 0xD3FC) != 0:
            return False
        if bytes(ram[0xD354 - RAM:0xD354 - RAM + 37]) != bytes(w['header']):
            return False
        slot = 0xD3FC + 26 * (w['number'] + 1)
        if _w(ram, slot + 2) != w['x'] and _w(ram, slot + 5) != w['y']:
            return False
        self.seen = _b(ram, slot)
        return True

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return super().result()
        if seen == w['type']:
            text = ('Played from the start, the level loads with nothing in that place.' if w['type'] == 0xFF
                    else f'Played from the start, the level loads {w["name"]} in that place.')
            return {'state': 'good', 'text': text}
        shown = 'nothing' if seen == 0xFF else SonicProfile.shown_name(seen)
        return {'state': 'bad', 'text': f'Played from the start, the level loads {shown} in that place, not what was chosen.'}


class SonicProfile(_Sms):
    """Sonic The Hedgehog (USA, Europe, Brazil).

    Level headers: little-endian offsets at ROM $15580 + level * 2 (relative to $15580), 37 bytes each, copied to RAM
    $D354 when a level loads (code $20CB). Header bytes 30-31: the object list, again relative to $15580 (read at $22D6).
    Object list ($232B): a count byte (objects + 1, Sonic being object 0), then 3 bytes per object: type, x and y in
    32-pixel units. Records are written to the object slots in order; the rest of the 32 slots are set to $FF (empty), and
    a record of type $FF is the game's own empty record. The level loaded is RAM $D23E, or $D2D3 when bit 4 of $D206 is
    set ($1CED). Camera: $D25A (x) and $D25D (y). Object code: pointer table $2AF6 + type * 2.
    """
    name = 'Sonic The Hedgehog'
    sha256s = ('6ad738965ece231427ee046b9905cfee470d5c01220afdd934da4673e4a2458b',)
    HEADERS = 0x15580
    LEVELS = 36
    # zone names: the game's own name table ($1209, one pointer per level 0-17) holds GREEN HILL, BRIDGE, JUNGLE, LABYRINTH,
    # SCRAP BRAIN and SKY BASE, three levels each
    ZONES = ['Green Hill', 'Bridge', 'Jungle', 'Labyrinth', 'Scrap Brain', 'Sky Base']
    # badniks: the object types whose code calls the touch routine $35E5 (Sonic is hurt, or the badnik is destroyed when
    # Sonic rolls into it or is invincible: the type becomes $0A, the explosion). Names from spawning each one and looking
    # at what the game draws (trace/v15_profiles/sms_classics/sonic_types); unnamed ones show their number.
    BADNIKS = {0x10: 'Motobug', 0x08: 'Crabmeat', 0x0E: 'Badnik 0x0E', 0x11: 'Badnik 0x11', 0x26: 'Chopper',
               0x2D: 'Yadrin', 0x3C: 'Jaws', 0x35: 'Orbinaut', 0x44: 'Burrobot', 0x1B: 'Ball Hog', 0x1F: 'Caterkiller'}
    # monitors: each type has its own code; what breaking one does was read from that code and measured in a replay
    MONITORS = {0x01: 'Ten rings', 0x02: 'Speed shoes', 0x03: 'Extra life', 0x04: 'Shield', 0x05: 'Invincibility'}
    OTHER = {0x06: 'Chaos Emerald', 0x51: 'Checkpoint monitor', 0x52: 'Continue monitor'}

    # -- the game's tables
    def header_at(self, level):
        offset = self.word(self.HEADERS + level * 2)
        return None if offset == 0 else self.HEADERS + offset

    def header(self, level):
        at = self.header_at(level)
        return None if at is None else bytes(self.rom[at:at + 37])

    def list_at(self, level):
        header = self.header(level)
        return None if header is None else self.HEADERS + (header[30] | header[31] << 8)

    def records(self, level):
        """[(number, offset of the type byte, type, x, y)] of a level's object list (x, y in 32-pixel units)."""
        at = self.list_at(level)
        if at is None:
            return []
        count = self.rom[at]
        return [(n, at + 1 + n * 3, self.rom[at + 1 + n * 3], self.rom[at + 2 + n * 3], self.rom[at + 3 + n * 3]) for n in range(max(0, count - 1))]

    def sharing(self, level):
        """Other levels that read the same object list."""
        at = self.list_at(level)
        return [n for n in range(self.LEVELS) if n != level and at is not None and self.list_at(n) == at]

    def art(self, level):
        header = self.header(level)
        return None if header is None else header[24] | header[25] << 8      # sprite art of the level (header bytes 24-25)

    def badniks_for(self, level):
        """Badniks the game itself places in levels that load the same sprite art (only those draw right)."""
        art = self.art(level)
        found = []
        for n in range(self.LEVELS):
            if self.art(n) == art:
                for _, _, kind, _, _ in self.records(n):
                    if kind in self.BADNIKS and kind not in found:
                        found.append(kind)
        return sorted(found)

    @classmethod
    def type_name(cls, kind):
        if kind in cls.BADNIKS:
            return cls.BADNIKS[kind]
        if kind in cls.MONITORS:
            return f'{cls.MONITORS[kind]} monitor'
        return cls.OTHER.get(kind, f'Object 0x{kind:02X}')

    @classmethod
    def shown_name(cls, kind):
        """The name inside a sentence: 'a monitor with a shield', 'Crabmeat'."""
        if kind in cls.MONITORS:
            return f'a monitor with {cls.MONITORS[kind].lower()}'
        return cls.type_name(kind)

    @staticmethod
    def loaded_level(ram):
        return _b(ram, 0xD2D3) if _b(ram, 0xD206) & 0x10 else _b(ram, 0xD23E)

    # -- the profile interface
    def where(self, ram):
        level = self.loaded_level(ram)
        if level >= self.LEVELS or self.header(level) is None:
            return None
        if bytes(ram[0xD354 - RAM:0xD354 - RAM + 37]) != self.header(level) or _b(ram, 0xD3FC) != 0:
            return None             # not in a level (title, map) or still loading
        return {'part': {'level': level}, 'x': _w(ram, 0xD25A), 'y': _w(ram, 0xD25D)}

    def part_name(self, part):
        level = int(part['level'])
        if level < 18:
            return f'{self.ZONES[level // 3]} Act {level % 3 + 1}'
        if 28 <= level < 36:
            return f'Special Stage {level - 27}'
        if level == 18:
            return 'Ending'
        return f'{self.ZONES[4]} room (level {level})' if self.art(level) == self.art(12) else f'Level {level}'

    def choices(self):
        return {'monitors': [{'value': k, 'name': v} for k, v in self.MONITORS.items()]}

    def objects(self, part):
        level = int(part['level'])
        shared = self.sharing(level)
        out = []
        for number, _, kind, x, y in self.records(level):
            if kind == 0xFF:
                continue
            # objects are drawn from their x, y (Sonic's own sprite is at exactly his x, y); a monitor settles 7 pixels
            # higher and 4 to the right, so it shows from y - 7 to y + 25 (measured)
            bottom = y * 32 + (25 if kind in self.MONITORS or kind in (0x51, 0x52) else 32)
            row = {'id': f'object:{number}', 'type': kind, 'x': x * 32 + 16, 'y': bottom, 'name': self.type_name(kind),
                   'remove': None, 'fields': []}
            if kind in self.BADNIKS:
                row.update(style='enemy', remove='Remove this badnik',
                           fields=[{'key': 'type', 'label': 'Swap for', 'value': kind,
                                    'choices': [{'value': k, 'name': self.BADNIKS[k]} for k in self.badniks_for(level)]}])
            elif kind in self.MONITORS:
                row.update(style='item', name='Monitor', detail=f'holds {self.MONITORS[kind].lower()}', remove='Remove this monitor',
                           fields=[{'key': 'type', 'label': 'Holds', 'value': kind, 'choices': 'monitors'}])
            elif kind in self.OTHER:
                row.update(style='item')
            else:
                row.update(style='block')
            if shared:
                names = ', '.join(self.part_name({'level': n}) for n in shared)
                row['note'] = f'This level shares its object list with {names}, so a change shows there too.'
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        level = int(part['level'])
        kind, _, number = object_id.partition(':')
        number = int(number)
        record = next((r for r in self.records(level) if r[0] == number), None)
        if kind != 'object' or record is None:
            raise ValueError('ROMancer cannot change that yet.')
        _, offset, old, x, y = record
        if remove:
            if old not in self.BADNIKS and old not in self.MONITORS:
                raise ValueError('That cannot be removed.')
            new = 0xFF
        else:
            new = int(values.get('type', old))
            allowed = self.badniks_for(level) if old in self.BADNIKS else list(self.MONITORS) if old in self.MONITORS else []
            if new not in allowed:
                raise ValueError('That choice is not one of the game’s own.')
        name = 'nothing' if new == 0xFF else self.shown_name(new)
        if old in self.BADNIKS:
            title = 'Remove the badnik' if new == 0xFF else f'Badnik here: {self.BADNIKS[new]}'
        else:
            title = 'Remove the monitor' if new == 0xFF else f'Monitor holds: {self.MONITORS[new].lower()}'
        writes = [(offset, old, new)] if new != old else []
        return {'writes': writes, 'title': f'{title} ({self.part_name(part)})',
                'watch': {'kind': 'sonic', 'level': level, 'number': number, 'type': new, 'name': name,
                          'x': x * 32, 'y': y * 32, 'header': list(self.header(level))}}

    def watcher(self, watch):
        return _SonicWatcher(watch)


# ---------------------------------------------------------------------------------------------- Alex Kidd in Miracle World

def _rle(rom, at):
    """A screen of 16 x 12 blocks, packed the game's way ($6BE8): n < $80 = n copies of the next byte, n >= $80 = the next
    n & $7F bytes as they are, 0 = end. Returns [(block, rom offset of its byte, how many blocks that byte gives)]."""
    out = []
    while len(out) < 192:
        n = rom[at]
        if n == 0:
            break
        if n & 0x80:
            out += [(rom[at + 1 + i], at + 1 + i, 1) for i in range(n & 0x7F)]
            at += 1 + (n & 0x7F)
        else:
            out += [(rom[at + 1], at + 1, n)] * n
            at += 2
    return out


class _AlexWatcher(Watcher):
    """An Alex Kidd edit, watched in the replayed game.

    Enemy: a screen's enemies are put in the object slots ($C3C0, 10 slots of 32 bytes: +0 type, +12 x, +14 y on the
    screen) the moment the screen counter $C08D reaches that screen; looks at the slots in the first frames after that.
    Box: the screen's tiles are written to the name table copy at $C800 (32 x 28 words); once the box's place is in view
    the tile there says which box it is (tile 1 skull box, 5 question box, 9 star box)."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.since = None

    def see(self, ram, frame, run):
        w = self.w
        if _b(ram, 0xC023) != w['round'] or _b(ram, 0xC01F) not in (0x8A, 0x82):     # play, or the game's own demo
            self.since = None
            return False
        if w['kind'] == 'enemy':
            if _b(ram, 0xC08D) & 0x7F != w['screen']:
                self.since = None
                return False
            self.since = frame if self.since is None else self.since
            here = {_b(ram, slot) for slot in range(0xC3C0, 0xC500, 32)
                    if _b(ram, slot) and abs(_b(ram, slot + 12) - w['sx']) <= 12 and abs(_b(ram, slot + 14) - w['sy']) <= 12}
            self.seen = (self.seen or set()) | here
            return frame - self.since >= 3
        spot = AlexKiddProfile.camera(ram, w['round'])
        if spot is None:
            return False
        x, y = spot
        if not (x <= w['x'] and w['x'] + 16 <= x + 248 and y <= w['y'] and w['y'] + 16 <= y + 192):
            return False
        cell = ((w['y'] // 8) % 28) * 32 + (w['x'] // 8) % 32
        self.seen = (_b(ram, 0xC800 + cell * 2) | _b(ram, 0xC801 + cell * 2) << 8) & 0x1FF
        return True

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return super().result()
        if w['kind'] == 'enemy':
            if w['type'] == 0:
                ok = w['old'] not in seen
                return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, no enemy appears there any more.' if ok
                        else 'Played from the start, the enemy still appears there.'}
            ok = w['type'] in seen
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, a {w["name"].lower()} appears there.' if ok
                    else 'Played from the start, a different enemy appears there.'}
        ok = AlexKiddProfile.BOX_TILES.get(seen) == w['block']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, there is a {w["name"].lower()} there.' if ok
                else 'Played from the start, a different block is there.'}


class AlexKiddProfile(_Sms):
    """Alex Kidd in Miracle World (World) (Sega Ages).

    Round: RAM $C023; play mode $C01F = $8A. Round record ($65AA): word at $66CD + round * 2 -> [bank | $80, row table,
    column table, $C0B6, $C0C4 (row), $C0A0 (screens), $C0A5, $C080 (how the round scrolls), block table]. A row table
    entry points at a list of screens (column table: the same by columns); a screen is 16 x 12 blocks of 16 pixels, packed
    ($6BE8, see _rle). Blocks 1, 2 and 3 are the skull, question and star boxes: their tiles carry the 'special' bit and
    the punch code ($4569) picks what happens by tile (table $45D0): star -> object $3C, a money bag ($4620); question ->
    the next of objects $4D extra life, $4E power bracelet, $4F ghost, in turn (table $0DD7, counter $C07C, $460E); skull
    -> Alex is held still ($45EA, bit 4 of $C31C).
    Enemies ($6F41): word at $B503 + round * 2 (bank 2) -> one list per value of the screen counter $C08D: a count byte,
    then 4 bytes per enemy (type, y, x, value); bytes with bit 7 set are other commands. Type 0 is the empty slot.
    Camera: x = 16 * ($C0B6 * 16 + $C0B5) + 8 * bit 7 of $C0B4, matched to the scroll register $C0B0; y = 192 * $C0C4 +
    16 * $C0C3 + 8 * bit 7 of $C0C2 + ($C0BE & 7). Supported rounds: those that scroll only to the right ($C080 = 8) and
    the shaft of round 1 (its first ten screens).
    """
    name = 'Alex Kidd in Miracle World'
    sha256s = ('42c08c72ffff8a8c0bb6dc6e53ba2cc1e12c95f59c02461914c136030bcd8f7b',)
    ROUNDS = 17
    # names from spawning each type in its own round and looking at what the game draws (sms_classics/alex/types.png)
    ENEMIES = {0x2D: 'Monster bird', 0x33: 'Monster bird', 0x30: 'Small fish', 0x2E: 'Large fish', 0x3E: 'Scorpion',
               0x2F: 'Frog', 0x31: 'Seahorse', 0x46: 'Lion', 0x3D: 'Flame', 0x57: 'Flame', 0x54: 'Owl', 0x20: 'Bat',
               0x2A: 'Monkey'}
    BOXES = {0x03: 'Star box', 0x02: 'Question box', 0x01: 'Skull box'}
    HOLDS = {0x03: 'a money bag', 0x02: 'the next of extra life, power bracelet and ghost', 0x01: 'a curse that holds Alex still'}
    BOX_TILES = {9: 0x03, 5: 0x02, 1: 0x01}
    SHOWN = 16          # the level map shows the game's pixel row 0 sixteen rows lower (measured on the map of round 1)

    def record(self, rnd):
        at = self.word(0x66CD + rnd * 2)
        r = self.rom
        return {'bank': r[at] & 0x1F, 'rows': self.word(at + 1), 'columns': self.word(at + 3), 'row': r[at + 6],
                'screens': r[at + 7], 'scroll': r[at + 9]}

    def kind(self, rnd):
        if rnd == 1:
            return 'down'
        if 1 <= rnd <= self.ROUNDS and self.record(rnd)['scroll'] == 8:
            return 'right'
        return None

    def at(self, rnd, address):
        """ROM offset of a CPU address in the round's map bank ($8000-$BFFF)."""
        return self.record(rnd)['bank'] * 0x4000 + address - 0x8000

    def screen_list(self, rnd):
        """[(screen counter value, ROM offset of the packed screen, world x, world y)] of the round's supported screens."""
        if self.kind(rnd) is None:
            return []
        rec = self.record(rnd)
        if self.kind(rnd) == 'right':
            table, count, step = self.word(self.at(rnd, rec['rows'] + rec['row'] * 2)), rec['screens'], (256, 0)
        else:
            table, count, step = self.word(self.at(rnd, rec['columns'])), 10, (0, 192)
        return [(n + 1, self.at(rnd, self.word(self.at(rnd, table + n * 2))), step[0] * n, step[1] * n) for n in range(count)]

    def enemy_lists(self, rnd):
        """{screen counter value: [(rom offset of the type byte, type, y, x, value)]} (bank 2 sits at its own addresses)"""
        start, end = self.word(0xB503 + rnd * 2), self.word(0xB503 + rnd * 2 + 2)
        out = {}
        for k in range(max(0, (end - start) // 2)):
            q, recs = self.word(start + 2 * k), []
            for _ in range(16):
                n = self.rom[q]
                if n == 0:
                    break
                if n & 0x80:
                    q += 5 if n & 5 else 2 if n & 2 else 2 + self.rom[q + 1]
                    continue
                recs = [(q + 1 + 4 * i,) + tuple(self.rom[q + 1 + 4 * i:q + 5 + 4 * i]) for i in range(n)]
                break
            out[k] = recs
        return out

    def enemies_for(self, rnd):
        """Enemies the game itself places in the round (their pictures are loaded there)."""
        return sorted({rec[1] for recs in self.enemy_lists(rnd).values() for rec in recs if rec[1] in self.ENEMIES})

    @staticmethod
    def camera(ram, rnd):
        if _b(ram, 0xC023) != rnd:
            return None
        if rnd == 1:
            if _b(ram, 0xC08D) & 0x7F > 10:
                return None
            return 0, 192 * _b(ram, 0xC0C4) + 16 * _b(ram, 0xC0C3) + 8 * (_b(ram, 0xC0C2) >> 7) + (_b(ram, 0xC0BE) & 7)
        rough = 16 * (_b(ram, 0xC0B6) * 16 + _b(ram, 0xC0B5)) + 8 * (_b(ram, 0xC0B4) >> 7) - 8
        low = -_b(ram, 0xC0B0) & 0xFF
        x = min(((rough // 256 + d) * 256 + low for d in (-1, 0, 1)), key=lambda c: abs(c - rough))
        return max(0, x), 0

    # -- the profile interface
    def where(self, ram):
        rnd = _b(ram, 0xC023)
        if _b(ram, 0xC01F) != 0x8A or self.kind(rnd) is None:
            return None
        spot = self.camera(ram, rnd)
        return None if spot is None else {'part': {'round': rnd}, 'x': spot[0], 'y': spot[1]}

    def part_name(self, part):
        return f'Round {int(part["round"])}'

    def choices(self):
        return {'boxes': [{'value': k, 'name': f'{v} ({self.HOLDS[k]})'} for k, v in self.BOXES.items()]}

    def uses(self, offset):
        """How many screens of the supported rounds read the packed byte at offset."""
        return sum(1 for rnd in range(1, self.ROUNDS + 1) for _, at, _, _ in self.screen_list(rnd)
                   if any(o == offset for _, o, _ in _rle(self.rom, at)))

    def objects(self, part):
        rnd = int(part['round'])
        lists = self.enemy_lists(rnd)
        choices = [{'value': k, 'name': self.ENEMIES[k]} for k in self.enemies_for(rnd)]
        out = []
        for k, at, ox, oy in self.screen_list(rnd):
            for i, (block, offset, run) in enumerate(_rle(self.rom, at)):
                if block not in self.BOXES:
                    continue
                row = {'id': f'box:{k}:{i}', 'style': 'item', 'type': block, 'x': ox + (i % 16) * 16 + 8, 'y': oy + (i // 16) * 16 + 16 + self.SHOWN,
                       'name': self.BOXES[block], 'detail': f'holds {self.HOLDS[block]}', 'remove': None, 'fields': []}
                if run == 1:
                    row['fields'] = [{'key': 'block', 'label': 'Box', 'value': block, 'choices': 'boxes'}]
                    uses = self.uses(offset)
                    if uses > 1:
                        row['note'] = f'This screen is used {uses} times in the game, so the change shows in every one of them.'
                else:
                    row['note'] = 'The game stores this box together with the blocks next to it, so it cannot be changed alone.'
                out.append(row)
            for offset, kind, y, x, value in lists.get(k, []):
                row = {'id': f'enemy:{k}:{offset}', 'type': kind, 'x': ox + x + 12, 'y': oy + y + 16 + self.SHOWN, 'remove': None, 'fields': []}
                if kind in self.ENEMIES:
                    row.update(style='enemy', name=self.ENEMIES[kind], remove='Remove this enemy',
                               fields=[{'key': 'type', 'label': 'Swap for', 'value': kind, 'choices': choices}])
                else:
                    row.update(style='block', name=f'Object 0x{kind:02X}')
                out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        rnd = int(part['round'])
        found = self.find(part, object_id)
        kind, k, rest = object_id.split(':')
        k, rest = int(k), int(rest)
        screen = next(s for s in self.screen_list(rnd) if s[0] == k)
        if kind == 'enemy' and found['style'] == 'enemy':
            old = self.rom[rest]
            new = 0 if remove else int(values.get('type', old))
            if new and new not in self.enemies_for(rnd):
                raise ValueError('That choice is not one of the game’s own.')
            y, x = self.rom[rest + 1], self.rom[rest + 2]
            name = self.ENEMIES.get(new, 'no enemy')
            return {'writes': [(rest, old, new)] if new != old else [],
                    'title': ('Remove the enemy' if not new else f'Enemy here: {name}') + f' (round {rnd}, screen {k})',
                    'watch': {'kind': 'enemy', 'round': rnd, 'screen': k, 'type': new, 'old': old, 'name': name,
                              'sx': x - (8 if self.kind(rnd) == 'right' else 0), 'sy': y}}
        if kind == 'box' and found['fields']:
            block, offset, _ = _rle(self.rom, screen[1])[rest]
            new = int(values.get('block', block))
            if new not in self.BOXES:
                raise ValueError('That choice is not one of the game’s own.')
            return {'writes': [(offset, block, new)] if new != block else [],
                    'title': f'{self.BOXES[new]} here (round {rnd}, screen {k})',
                    'watch': {'kind': 'box', 'round': rnd, 'block': new, 'name': self.BOXES[new],
                              'x': screen[2] + (rest % 16) * 16, 'y': screen[3] + (rest // 16) * 16}}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        return _AlexWatcher(watch)


# ------------------------------------------------------------------------------------------------------------ Wonder Boy

class _WonderBoyWatcher(Watcher):
    """A Wonder Boy edit. The game reads a round's object records in order through the pointer $C18D (bank 2, so the
    pointer is the record's ROM offset) and puts each new object in the list at $C1A1 (10 entries of 12 bytes; byte 0 is
    $80 + type once the object is made). Looks at the frame the pointer passes the record: good when an object of the
    chosen type was made in that frame (for a removal: when none of the old type was)."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.prev = {}

    def see(self, ram, frame, run):
        w = self.w
        pointer = _w(ram, 0xC18D)
        entries = [bytes(ram[0xC1A1 - RAM + 12 * i:0xC1A1 - RAM + 12 * i + 3]) for i in range(10)]
        before = self.prev.get(run)
        self.prev[run] = (pointer, entries)
        if before is None or _b(ram, 0xC128) != w['round']:
            return False
        old_pointer, old_entries = before
        if not old_pointer <= w['offset'] < pointer or pointer - old_pointer > 60:
            return False
        self.seen = {e[0] & 0x7F for e, o in zip(entries, old_entries) if e != o and e[0] & 0x80 and e[0] != 0x80}
        return True

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return super().result()
        if w['type'] is None:
            ok = w['old'] not in seen
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, nothing appears there any more.' if ok
                    else 'Played from the start, it still appears there.'}
        ok = w['type'] in seen
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, {w["name"].lower()} appears there.' if ok
                else 'Played from the start, something else appears there.'}


class WonderBoyProfile(_Sms):
    """Wonder Boy (USA, Europe, Brazil) (Rev 1).

    Round: RAM $C128 (0 = area 1 round 1; four rounds an area, the fourth using the castle layout). Camera: $C12B (x);
    $C12A counts the camera in 8-pixel steps and $C129 counts 256 of those (a part of the round, 2048 pixels).
    Objects ($10CA, bank 2): word at $9EB6 + (round * 4 + part) * 2 -> records of 3 bytes, ended by a first byte of $7F
    or $FF: [position (bit 7: other rule), y (bit 7: skipped while bit 0 of $C114 is set), level (top 3 bits) + index
    (low 5 bits)]. A record is read when $C12A reaches position * 2; the index picks the type from the part's type list
    (word at $9D6E + the same * 2). Levels: a normal record appears when its level is at most the round's value at
    $11E7 + round ($C136); a record with bit 7 set appears only when its level is that value. The object is put at screen
    x $D0 and the record's y ($06E2); fruit types place themselves at x $98 (measured). Object x is in 2-pixel steps:
    the sprite's left edge is at screen 2 * x - 135, so an object made at $D0 is 281 pixels right of the camera.
    """
    name = 'Wonder Boy'
    sha256s = ('a13fa8164a0ab2d549d9a9bb3f998907c3f64b42eab9f4fae3d666abab510fdd',)
    ROUNDS = 41
    # names from making the first record of a round each type and looking at what the game draws (sms_classics/wb/p*.png)
    ENEMIES = {0x26: 'Cobra', 0x22: 'Snail', 0x70: 'Snail', 0x04: 'Bonfire', 0x5F: 'Bonfire', 0x47: 'Octopus',
               0x48: 'Bee', 0x49: 'Bee', 0x4A: 'Bee', 0x4C: 'Bee', 0x43: 'Spider', 0x27: 'Skull', 0x23: 'Rock', 0x5E: 'Rock'}
    EGGS = {0x10: 'Egg', 0x11: 'Egg', 0x12: 'Egg', 0x13: 'Egg', 0x14: 'Egg', 0x6D: 'Egg'}
    OTHER = {0x15: 'Stone hatchet', 0x58: 'Doll', 0x42: 'Flower', 0x67: 'Flower', 0x2F: 'Spring board', 0x1E: 'Sign 2',
             0x1F: 'Sign 3', 0x20: 'Sign 4', 0x21: 'Goal sign', 0x33: 'King'}
    FRUIT_X = {0x07, 0x0D, 0x0E, 0x0F}      # measured: these appear at screen x $98, the rest at $D0
    START = 256                             # the camera when a round starts at its first part (measured)
    # a record's y counts up from the ground in 2-pixel steps: a snail with y $2C has its sprite bottom on screen line 145.
    # An object's x (+7) is in 2-pixel steps too: its sprite's left edge is on screen at 2 * x - 135 (rocks, snail and
    # fruit, sprite table against the object, sms_classics/wb/w14.py, w16.py)
    GROUND = 145 + 2 * 0x2C

    def level_value(self, rnd):
        return self.rom[0x11E7 + rnd]

    def part_lists(self, rnd):
        """[(part, ROM offset of the records, ROM offset of the type list)] (bank 2 sits at its own addresses)."""
        return [(seg, self.word(0x9EB6 + (rnd * 4 + seg) * 2), self.word(0x9D6E + (rnd * 4 + seg) * 2)) for seg in range(4)]

    def records(self, rnd):
        """Records that appear in the round: [(part, offset, position, y, level, index, type)]."""
        value = self.level_value(rnd)
        out = []
        for seg, at, types in self.part_lists(rnd):
            q = at
            for _ in range(256):
                if (self.rom[q] << 1) & 0xFF == 0xFE:
                    break
                b0, y, e = self.rom[q], self.rom[q + 1], self.rom[q + 2]
                level = e & 0xE0
                shown = level == value if b0 & 0x80 else level <= value
                if shown:
                    out.append((seg, q, b0 & 0x7F, y, level, e & 0x1F, self.rom[types + (e & 0x1F)]))
                q += 3
        return out

    def type_name(self, kind):
        return self.ENEMIES.get(kind) or self.EGGS.get(kind) or self.OTHER.get(kind) or f'Object 0x{kind:02X}'

    def sharing(self, rnd, offset):
        return [n for n in range(self.ROUNDS) if n != rnd and any(r[1] == offset for r in self.records(n))]

    # -- the profile interface
    def where(self, ram):
        rnd = _b(ram, 0xC128)
        if rnd >= self.ROUNDS:
            return None
        pointer = _w(ram, 0xC18D)
        lists = self.part_lists(rnd)
        if not any(at <= pointer <= at + 3 * 256 for _, at, _ in lists):
            return None                 # not playing this round (title, area screen)
        camera = _w(ram, 0xC12B)
        if camera == _b(ram, 0xC129) * 2048 + self.START:
            return None                 # the round's first screen before it scrolls: the forest repeats, so the level map
                                        # can place this screen a few trees off (measured); later screens place right
        return {'part': {'round': rnd}, 'x': camera, 'y': 0}

    def part_name(self, part):
        rnd = int(part['round'])
        return f'Area {rnd // 4 + 1}, Round {rnd % 4 + 1}' if rnd < 36 else f'Extra round {rnd - 35}'

    def objects(self, part):
        rnd = int(part['round'])
        out = []
        for seg, offset, pos, y, level, index, kind in self.records(rnd):
            types = self.part_lists(rnd)[seg][2]
            table = [self.rom[types + k] for k in range(32)]
            camera = max((seg * 256 + pos * 2) * 8, seg * 2048 + self.START)
            row = {'id': f'object:{offset}', 'type': kind, 'x': camera + 2 * (0x98 if kind in self.FRUIT_X else 0xD0) - 135 + 8,
                   'y': self.GROUND - 2 * (y & 0x7F) + AlexKiddProfile.SHOWN, 'name': self.type_name(kind), 'remove': None, 'fields': []}
            group = self.ENEMIES if kind in self.ENEMIES else self.EGGS if kind in self.EGGS else None
            if group is not None:
                choices = []
                kinds = {}
                for k, t in enumerate(table):
                    if t in group and t not in kinds:
                        kinds[t] = index if t == kind else k          # one choice per type; this record's own index for its type
                for t, k in kinds.items():
                    choices.append({'value': k, 'name': self.type_name(t) if t in self.ENEMIES else f'Egg (0x{t:02X})'})
                row.update(style='enemy' if group is self.ENEMIES else 'item',
                           remove='Remove this enemy' if group is self.ENEMIES else 'Remove this egg',
                           fields=[{'key': 'index', 'label': 'Swap for' if group is self.ENEMIES else 'Egg', 'value': index, 'choices': choices}])
                if group is self.EGGS:
                    row['name'] = f'Egg (0x{kind:02X})'
            else:
                row['style'] = 'item' if kind in self.OTHER else 'block'
            notes = []
            if y & 0x80:
                notes.append('The game skips this one in some situations (bit 0 of $C114).')
            others = self.sharing(rnd, offset)
            if others:
                notes.append('This list is shared with ' + ', '.join(self.part_name({'round': n}) for n in others[:4])
                             + (' and more' if len(others) > 4 else '') + ', so the change shows there too.')
            if notes:
                row['note'] = ' '.join(notes)
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        rnd = int(part['round'])
        found = self.find(part, object_id)
        if not found['fields']:
            raise ValueError('ROMancer cannot change that yet.')
        offset = int(object_id.split(':')[1])
        seg = next(r[0] for r in self.records(rnd) if r[1] == offset)
        types = self.part_lists(rnd)[seg][2]
        b0, e = self.rom[offset], self.rom[offset + 2]
        old = self.rom[types + (e & 0x1F)]
        if remove:
            value = self.level_value(rnd)
            hidden = [lv for lv in (0xE0, 0xC0) if (lv != value if b0 & 0x80 else lv > value)]
            if not hidden:
                raise ValueError('That cannot be removed in this round.')
            new_byte, kind, name = (e & 0x1F) | hidden[0], None, 'nothing'
        else:
            index = int(values.get('index', e & 0x1F))
            if all(c['value'] != index for c in found['fields'][0]['choices']):
                raise ValueError('That choice is not one of the game’s own.')
            new_byte, kind = (e & 0xE0) | index, self.rom[types + index]
            name = next(c['name'] for c in found['fields'][0]['choices'] if c['value'] == index)
        title = (f'Remove the {found["style"] == "enemy" and "enemy" or "egg"}' if remove else f'Here: {name}') + f' ({self.part_name(part)})'
        return {'writes': [(offset + 2, e, new_byte)] if new_byte != e else [], 'title': title,
                'watch': {'kind': 'wonderboy', 'round': rnd, 'offset': offset, 'type': kind, 'old': old, 'name': name}}

    def watcher(self, watch):
        return _WonderBoyWatcher(watch)


PROFILES = [SonicProfile, AlexKiddProfile, WonderBoyProfile]
