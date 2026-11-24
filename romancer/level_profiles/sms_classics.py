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


PROFILES = [SonicProfile]
