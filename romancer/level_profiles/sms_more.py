"""Level profiles for more Master System games: Sonic The Hedgehog 2.

The tables were found by reading the game's Z80 code and proven by replaying the game with a changed ROM (research notes:
research/sms_more-level-profile.md). Master System RAM is the 8 KB at CPU $C000-$DFFF; the snapshot's 'wram' domain holds
it with index 0 = $C000, so RAM address A is ram[A - $C000].
"""
from __future__ import annotations

from . import Watcher
from .sms_classics import RAM, _Sms, _b, _w


class _Sonic2Watcher(Watcher):
    """A Sonic 2 object edit, watched in the replayed game.

    The game reads a record when it comes within reach of the camera ($78000): it writes the record's type to the record's
    own status byte $D400 + record number (or $FF for an event record of type $FE, which makes no object) and puts the
    object in a free slot ($D700-$DBFF, 64 bytes each: +0 type, +$11 x, +$14 y, +$3E record number + 1, +$3F the record's
    seventh byte, an item box's content). Looks at the first frame that status byte is set in the act."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if (_b(ram, 0xD295), _b(ram, 0xD296)) != (w['zone'], w['act']) or _b(ram, 0xD500) != 1:
            return False
        status = _b(ram, 0xD400 + w['number'])
        if status == 0:
            return False
        content = None
        for slot in range(0xD700, 0xDC00, 0x40):
            if _b(ram, slot) == status and _b(ram, slot + 0x3E) == w['number'] + 1:
                content = _b(ram, slot + 0x3F)
                break
        self.seen = (status, content)
        return True

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return super().result()
        status, content = seen
        if w['remove']:
            ok = status == 0xFF
            return {'state': 'good' if ok else 'bad',
                    'text': 'Played from the start, nothing appears in that place any more.' if ok
                    else f'Played from the start, {Sonic2Profile.shown_name(status, content)} still appears in that place.'}
        ok = status == w['type'] and (w.get('content') is None or content == w['content'])
        if ok:
            return {'state': 'good', 'text': f'Played from the start, {w["name"]} appears in that place.'}
        shown = 'nothing' if status == 0xFF else Sonic2Profile.shown_name(status, content)
        return {'state': 'bad', 'text': f'Played from the start, {shown} appears in that place, not what was chosen.'}


class Sonic2Profile(_Sms):
    """Sonic The Hedgehog 2 (Europe, Brazil) (Rev 1).

    Zone RAM $D295 (0-6), act $D296 (0-2, the third act is the boss). Object lists ($78000, bank 30 in slot 2): word at
    CPU $8135 + zone * 2 -> three words, one per act -> the act's records, 9 bytes each: type, x (word), y (word), then four
    bytes copied to the object (byte 5 -> +4 with bit 6 set, byte 6 -> +$3F, bytes 7 and 8 -> +8 and +9: where the
    zone's sprite art for that type sits). A type of $FF ends the list; type $FE is an event record (it makes no object;
    byte 5 picks the event from the table at CPU $80BE, where entries 1-15 do nothing and entry 0 runs code).
    A record is read when its place comes within the area from 128 pixels left of and above the camera to 384 pixels
    right of and below it. Camera: $D174 (x) and $D176 (y). Sonic is the object in slot $D500 (type 1).
    """
    name = 'Sonic The Hedgehog 2'
    sha256s = ('b7bb3b55ca308ce0d235469f877d21f8188960aec5cd473349ab66cac089927d',)
    LISTS = 0x78135                 # CPU $8135 in bank 30
    BANK = 0x78000 - 0x8000         # ROM offset of a CPU address in bank 30
    # the zone names on the game's own title cards
    ZONES = ['Under Ground', 'Sky High', 'Aqua Lake', 'Green Hills', 'Gimmick Mt.', 'Scrambled Egg', 'Crystal Egg']
    ACTS = 3
    REMOVED = (0xFE, 0x01)          # an event record whose event (table entry 1) does nothing
    # badniks: the placed types whose code calls the game's badnik routine ($020C -> $6279, or $025D -> $6289 after its
    # own check): touched while Sonic attacks, the object turns into the explosion (type $0F). Names and does-lines from
    # what the game draws and how each moved in a replay (trace/v15_profiles/sms_more/names.png)
    BADNIKS = {
        0x23: ('Crab robot', 'Walks along the ground toward you.'),
        0x32: ('Turtle robot', 'Moves slowly along the ground.'),
        0x33: ('Fish robot', 'Swims back and forth under the water.'),
        0x34: ('Drill robot', 'Crawls back and forth along the floor.'),
        0x35: ('Lizard robot', 'Clings to the wall and fades from view now and then.'),
        0x37: ('Flying robot', 'Flies sideways through the air.'),
        0x38: ('Hidden robot', 'Stays out of sight; it was not seen drawn in the replays watched.'),
        0x39: ('Helmet robot', 'Walks slowly along the ground under its helmet.'),
        0x3A: ('Climbing robot', 'Clings to a pole and moves toward you.'),
    }
    BOX = 0x10
    # item box contents (the record's seventh byte; the box code turns it into a bit of $D39D, read at $4802), each
    # measured by breaking a box that holds it (trace/v15_profiles/sms_more/box_icons.png)
    CONTENTS = {
        2: ('Ten rings', 'Adds ten rings.'),
        3: ('Extra life', 'Adds a life.'),
        4: ('Speed shoes', 'Makes Sonic run faster for a while.'),
        5: ('Invincibility', 'Makes Sonic invincible for a while.'),
        6: ('Continue', 'Adds a continue.'),
    }
    # other objects: names from what the game draws, does-lines from watching them (or None when not watched)
    OTHER = {
        0x0A: ('Invisible object', None),
        0x0E: ('Lava fireball', 'Jumps up out of the lava and falls back in.'),
        0x14: ('Invisible object', None),
        0x18: ('End sign', 'Marks the end of the act.'),
        0x1B: ('Ceiling spikes', None),
        0x20: ('Moving platform', 'Moves back and forth.'),
        0x21: ('Striped pad', None),
        0x22: ('Moving pipe', 'Slides along to the right.'),
        0x25: ('Invisible object', None),
        0x26: ('Spear', None),
        0x27: ('Hang glider', None),
        0x28: ('Spinning wheel', 'Turns in place.'),
        0x29: ('Mine cart', 'Rolls along when you land on it.'),
        0x2A: ('Invisible object', None),
        0x2B: ('Invisible object', None),
        0x2C: ('Crystal blocks', None),
    }
    # how far below its place the object's sprites end (measured in the game's sprite table, $DB00/$DB40)
    BOTTOM = {0x10: 9, 0x23: 9, 0x39: 9, 0x3A: 3, 0x18: 1, 0x34: 1, 0x33: 1, 0x32: 1, 0x37: 1}

    # -- the game's tables
    def act_list(self, zone, act):
        acts = self.BANK + self.word(self.LISTS + zone * 2)
        return self.BANK + self.word(acts + act * 2)

    def records(self, zone, act):
        """[(number, offset, type, x, y, (byte5, byte6, byte7, byte8))] of an act's object list."""
        at = self.act_list(zone, act)
        out = []
        while self.rom[at] != 0xFF and len(out) < 255:
            r = self.rom[at:at + 9]
            out.append((len(out), at, r[0], r[1] | r[2] << 8, r[3] | r[4] << 8, tuple(r[5:9])))
            at += 9
        return out

    def zone_badniks(self, zone):
        """{type: (byte5, byte6, byte7, byte8)} of the badniks the game itself places in the zone's first two acts (the
        last four bytes say where the zone's art for that badnik sits, so only these draw right); the commonest settings."""
        counts = {}
        for act in (0, 1):
            for _, _, kind, _, _, rest in self.records(zone, act):
                if kind in self.BADNIKS:
                    counts.setdefault(kind, {}).setdefault(rest, 0)
                    counts[kind][rest] += 1
        return {kind: max(found, key=lambda k: (found[k], -k[1])) for kind, found in sorted(counts.items())}

    @classmethod
    def type_name(cls, kind):
        if kind in cls.BADNIKS:
            return cls.BADNIKS[kind][0]
        if kind == cls.BOX:
            return 'Item box'
        if kind in cls.OTHER:
            return cls.OTHER[kind][0]
        if kind in BOSSES:
            return BOSSES[kind][0]
        return f'Object 0x{kind:02X}'

    @classmethod
    def shown_name(cls, kind, content=None):
        """The name inside a sentence: 'an item box with an extra life', 'Crab robot'."""
        if kind == cls.BOX and content in cls.CONTENTS:
            return f'an item box with {cls.CONTENTS[content][0].lower()}'
        return cls.type_name(kind)

    # -- the profile interface
    def where(self, ram):
        zone, act = _b(ram, 0xD295), _b(ram, 0xD296)
        if zone >= len(self.ZONES) or act >= self.ACTS or _b(ram, 0xD500) != 1:
            return None             # title, story, title card or loading
        return {'part': {'zone': zone, 'act': act}, 'x': _w(ram, 0xD174), 'y': _w(ram, 0xD176)}

    def part_name(self, part):
        return f'{self.ZONES[int(part["zone"])]} Act {int(part["act"]) + 1}'

    def choices(self):
        return {'contents': [{'value': k, 'name': v[0]} for k, v in self.CONTENTS.items()]}

    def objects(self, part):
        zone, act = int(part['zone']), int(part['act'])
        badniks = self.zone_badniks(zone)
        out = []
        for number, _, kind, x, y, rest in self.records(zone, act):
            if kind == 0xFE:
                continue            # an event record: makes nothing in the level
            row = {'id': f'object:{number}', 'type': kind, 'x': x, 'y': y + self.BOTTOM.get(kind, 1), 'name': self.type_name(kind),
                   'remove': None, 'fields': []}
            if kind in self.BADNIKS:
                row.update(style='enemy', does=self.BADNIKS[kind][1], remove='Remove this badnik',
                           fields=[{'key': 'type', 'label': 'Swap for', 'value': kind,
                                    'choices': [{'value': k, 'name': self.BADNIKS[k][0]} for k in badniks]}])
            elif kind == self.BOX and rest[1] in self.CONTENTS:
                row.update(style='item', detail=f'holds {self.CONTENTS[rest[1]][0].lower()}', does=self.CONTENTS[rest[1]][1],
                           remove='Remove this item box', fields=[{'key': 'content', 'label': 'Holds', 'value': rest[1], 'choices': 'contents'}])
            elif kind in BOSSES:
                row.update(style='enemy')
                if BOSSES[kind][1]:
                    row['does'] = BOSSES[kind][1]
            else:
                row.update(style='block')
                if kind in self.OTHER and self.OTHER[kind][1]:
                    row['does'] = self.OTHER[kind][1]
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        zone, act = int(part['zone']), int(part['act'])
        kind, _, number = object_id.partition(':')
        record = next((r for r in self.records(zone, act) if kind == 'object' and str(r[0]) == number), None)
        if record is None:
            raise ValueError('ROMancer cannot change that yet.')
        number, offset, old, x, y, rest = record
        box = old == self.BOX and rest[1] in self.CONTENTS
        if old not in self.BADNIKS and not box:
            raise ValueError('ROMancer cannot change that yet.')
        new_bytes = list(self.rom[offset:offset + 9])
        watch = {'kind': 'sonic2', 'zone': zone, 'act': act, 'number': number, 'remove': bool(remove), 'x': x, 'y': y}
        if remove:
            new_bytes[0], new_bytes[5] = self.REMOVED
            title = 'Remove the badnik' if old in self.BADNIKS else 'Remove the item box'
            watch.update(type=0xFF, name='nothing')
        elif box:
            content = int(values.get('content', rest[1]))
            if content not in self.CONTENTS:
                raise ValueError('That choice is not one of the game’s own.')
            new_bytes[6] = content
            title = f'Item box holds: {self.CONTENTS[content][0].lower()}'
            watch.update(type=self.BOX, content=content, name=self.shown_name(self.BOX, content))
        else:
            new = int(values.get('type', old))
            badniks = self.zone_badniks(zone)
            if new not in badniks:
                raise ValueError('That choice is not one of the game’s own.')
            new_bytes[0] = new
            if new != old:
                new_bytes[5:9] = badniks[new]       # the zone's own settings and art place for that badnik
            title = f'Badnik here: {self.BADNIKS[new][0]}'
            watch.update(type=new, name=self.BADNIKS[new][0])
        writes = [(offset + i, self.rom[offset + i], v) for i, v in enumerate(new_bytes) if self.rom[offset + i] != v]
        return {'writes': writes, 'title': f'{title} ({self.part_name(part)})', 'watch': watch}

    def watcher(self, watch):
        return _Sonic2Watcher(watch)


# the boss acts' own objects: names from what the game draws (filled in by the naming pass; None = not watched)
BOSSES = {}


PROFILES = [Sonic2Profile]
