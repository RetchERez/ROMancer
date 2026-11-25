"""Game Boy level profiles: Castlevania II - Belmont's Revenge (enemies, candles and what they hold, other placed objects).

Castlevania - The Adventure and Wario Land - Super Mario Land 3 were started in the same pass but not finished; they
have no class yet. Research notes: research/gb_more-level-profile.md. Work RAM index 0 is $C000.
"""
from __future__ import annotations

from . import Profile, Watcher


def _cv2_file(bank: int, address: int) -> int:
    return address if address < 0x4000 else bank * 0x4000 + (address - 0x4000)


class BelmontsRevenge(Profile):
    """Parts are {'stage': 0-7, 'area': n} ($C8C0 / $C8C1). Positions are the game's own: x = screen * 160 + pixel
    ($CA86 / $CA85), y = screen * 128 + pixel ($CA8D / $CA8C).

    Objects come from three lists per area in bank 3 (pointer tables $5242, $58AC and $5D25, each indexed by stage, then
    area, through the routine at $2868). A list is a run of 6-byte records [camera screen, camera pixel, slot, type,
    screen x, screen y], ended by $FD. $FF separates sections of a list (the spawner stops there); $FE starts a group of
    4-byte records [slot, type, x, y] for rooms that do not scroll. A 6-byte record appears when the camera reaches its
    screen and pixel; its slot is (slot & 7) + $C4 (first list), $CC (second) or $D4 (third), times 256. The copy in RAM
    ($6CE2) stores slot | record number * 8, and the object keeps that record number in byte 5.
    """
    name = "Castlevania II - Belmont's Revenge"
    sha256s = ('17570ceec1b22153604622c4412d048dd8f7ccb4626daf9ddea96de8a062dbf2',)
    system = 'gb'

    BANK = 3
    TABLES = {'thing': 0x5242, 'enemy': 0x58AC, 'candle': 0x5D25}
    SLOT_BASE = {'thing': 0xC4, 'enemy': 0xCC, 'candle': 0xD4}
    START_TABLE = 0x5020        # bank 6: [stage][area] -> (x screen, y screen) where the area's room map starts
    STAGES = {1: 'Plant Castle', 2: 'Crystal Castle', 3: 'Cloud Castle', 4: 'Rock Castle'}

    # What a candle holds: its record's type byte (third list). Each was put in the first candle of Cloud Castle,
    # whipped and picked up (research notes): the picture it drops and the RAM it changes.
    CONTENTS = {
        0x01: ('Axe', 'Gives the axe as the sub-weapon.'),
        0x02: ('Holy water', 'Gives the holy water as the sub-weapon.'),
        0x03: ('Small rod', 'Picked up without any change seen in hearts, life, lives, whip or sub-weapon.'),
        0x04: ('Whip upgrade', 'Makes the whip longer, with a ball at its end.'),
        0x05: ('Small heart', 'Adds 1 heart.'),
        0x06: ('Large heart', 'Adds 5 hearts.'),
        0x08: ('1-up', 'Adds one life.'),
        0x0B: ('Large heart (second kind)', 'Drops a large heart that adds 5 hearts.'),
        0x35: ('Whip upgrade (second kind)', 'Drops the same ball as the whip upgrade.'),
    }

    # Names from spawning each type in an area that uses it and looking at what the game draws (research notes,
    # pictures in trace/v15_profiles/gb_more/cv2/spawn/). Types whose picture was not clear show their number.
    ENEMY_NAMES = {
        0x09: 'Hopping frog', 0x0E: 'Hopping frog', 0x0C: 'Seed-spitting plant', 0x0F: 'Rolling eyeball',
        0x12: 'Moving platform, up and down', 0x15: 'Spider on a thread', 0x34: 'Raven', 0x41: 'Bat',
        0x48: 'Rising platform', 0x5F: 'Rising platform',
    }
    ENEMY_DOES = {
        0x09: 'Hops about in big jumps.', 0x0E: 'Hops about in big jumps.',
        0x0C: 'Stays in place and spits a seed ball.', 0x0F: 'Rolls slowly along the floor.',
        0x12: 'Moves up and down.', 0x15: 'Moves up and down on its thread.',
        0x34: 'Swoops down at you and flies back up.', 0x41: 'Flies about in a zigzag.',
        0x48: 'Rises slowly.', 0x5F: 'Rises slowly.',
    }
    # Other placed objects (first list): only the named ones are shown.
    THING_NAMES = {0x4E: 'Torch flame', 0x13: 'Moving platform', 0x12: 'Sinking platform', 0x14: 'Spider on a thread'}
    THING_DOES = {0x13: 'Moves sideways.', 0x12: 'Moves down.', 0x14: 'Drops down on its thread.'}

    def __init__(self, rom: bytes):
        super().__init__(rom)

    # --- ROM access -----------------------------------------------------------------------------------------------
    def _b(self, bank, address):
        return self.rom[_cv2_file(bank, address)]

    def _w(self, bank, address):
        return self._b(bank, address) | self._b(bank, address + 1) << 8

    def area_count(self, stage: int) -> int:
        """The stages' area tables lie one after another, the first list right after the last one."""
        if not 0 <= stage < 8:
            return 0
        t = self.TABLES['enemy']
        starts = [self._w(self.BANK, t + 2 * s) for s in range(8)]
        ends = sorted(set(starts) | {self._w(self.BANK, starts[0])})
        later = [e for e in ends if e > starts[stage]]
        return (later[0] - starts[stage]) // 2 if later else 0

    def parts(self):
        return [{'stage': s, 'area': a} for s in range(1, 8) for a in range(self.area_count(s))]

    def list_pointer(self, kind: str, stage: int, area: int) -> int:
        return self._w(self.BANK, self._w(self.BANK, self.TABLES[kind] + 2 * stage) + 2 * area)

    def start_screens(self, stage: int, area: int) -> tuple:
        p = self._w(6, self._w(6, self.START_TABLE + 2 * stage) + 2 * area)
        return self._b(6, p), self._b(6, p + 1)

    def records(self, kind: str, stage: int, area: int) -> list:
        """Every record of a list: {'index' (the record number the game keeps), 'offset' (ROM), 'size' 6 or 4,
        'section' (count of $FF / $FE markers before it), 'slot', 'type', and for 6-byte records 'cam' (screen, pixel),
        'sx', 'sy'}."""
        o = _cv2_file(self.BANK, self.list_pointer(kind, stage, area))
        out, index, section, rooms = [], 0, 0, 0
        r = self.rom
        for _ in range(512):
            b = r[o]
            if b == 0xFD:
                break
            if b == 0xFF:
                section += 1
                o += 1
                continue
            if b == 0xFE:
                rooms += 1
                o += 1
                while r[o] not in (0xFD, 0xFE, 0xFF):
                    out.append({'index': index, 'offset': o, 'size': 4, 'section': section, 'room': rooms,
                                'slot': r[o] & 7, 'type': r[o + 1], 'sx': r[o + 2], 'sy': r[o + 3]})
                    index += 1
                    o += 4
                continue
            out.append({'index': index, 'offset': o, 'size': 6, 'section': section, 'cam': (r[o], r[o + 1]),
                        'slot': r[o + 2] & 7, 'type': r[o + 3], 'sx': r[o + 4], 'sy': r[o + 5]})
            index += 1
            o += 6
        return out

    def list_end(self, kind, stage, area) -> int:
        """ROM offset of the list's $FD."""
        o = _cv2_file(self.BANK, self.list_pointer(kind, stage, area))
        recs = self.records(kind, stage, area)
        o = max([rec['offset'] + rec['size'] for rec in recs], default=o)
        while self.rom[o] != 0xFD:
            o += 1
        return o

    @staticmethod
    def place(stage_row: int, rec: dict) -> tuple:
        screen, pixel = rec['cam']
        return screen * 160 + pixel + rec['sx'], stage_row * 128 + rec['sy'] + 8

    # --- names ----------------------------------------------------------------------------------------------------
    def enemy_name(self, kind: int) -> str:
        return self.ENEMY_NAMES.get(kind, f'Enemy 0x{kind:02X}')

    def content_name(self, value: int) -> str:
        return self.CONTENTS[value][0] if value in self.CONTENTS else f'Item 0x{value:02X}'

    def thing_name(self, kind: int) -> str:
        return self.THING_NAMES.get(kind, f'Object 0x{kind:02X}')

    def part_name(self, part):
        s, a = int(part['stage']), int(part['area'])
        return f'{self.STAGES.get(s, f"Stage {s}")}, area {a + 1}'

    # --- where ----------------------------------------------------------------------------------------------------
    def where(self, ram):
        if ram is None or len(ram) < 0x2000:
            return None
        stage, area = ram[0x8C0], ram[0x8C1]
        if not 1 <= stage <= 7 or area >= self.area_count(stage):
            return None
        if ram[0xA85] >= 160 or ram[0xA8C] >= 128:
            return None
        x = (ram[0xA86] & 0x0F) * 160 + ram[0xA85]
        y = (ram[0xA8D] & 0x0F) * 128 + ram[0xA8C]
        return {'part': {'stage': stage, 'area': area}, 'x': x, 'y': y}

    # --- objects --------------------------------------------------------------------------------------------------
    def choices(self):
        return {'contents': [{'value': k, 'name': v[0]} for k, v in self.CONTENTS.items()]}

    def enemy_choices(self, stage: int, area: int) -> list:
        """The enemy types this area's own list uses (their pictures are loaded for the area)."""
        kinds = sorted({rec['type'] for rec in self.records('enemy', stage, area)})
        return [{'value': k, 'name': self.enemy_name(k)} for k in kinds]

    def objects(self, part):
        stage, area = int(part['stage']), int(part['area'])
        row = self.start_screens(stage, area)[1]
        out = []
        for kind in ('enemy', 'candle', 'thing'):
            for rec in self.records(kind, stage, area):
                if rec['size'] != 6:
                    continue        # rooms that do not scroll: their place on the map is not known
                x, y = self.place(row, rec)
                oid = f'{kind}:{rec["index"]}'
                note = None
                if rec['section']:
                    note = ('This one belongs to a later section of the area; its height on the map is a guess '
                            '(the game keeps the height of each section elsewhere).')
                if kind == 'enemy':
                    o = {'id': oid, 'style': 'enemy', 'type': rec['type'], 'x': x, 'y': y,
                         'name': self.enemy_name(rec['type']), 'remove': 'Remove this enemy',
                         'fields': [{'key': 'type', 'label': 'Swap for', 'value': rec['type'],
                                     'choices': self.enemy_choices(stage, area)}]}
                    if rec['type'] in self.ENEMY_DOES:
                        o['does'] = self.ENEMY_DOES[rec['type']]
                elif kind == 'candle':
                    o = {'id': oid, 'style': 'item', 'type': rec['type'], 'x': x, 'y': y, 'name': 'Candle',
                         'detail': f'holds {self.content_name(rec["type"]).lower()}', 'remove': 'Remove this candle',
                         'fields': [{'key': 'contents', 'label': 'Holds', 'value': rec['type'], 'choices': 'contents'}]}
                    if rec['type'] in self.CONTENTS:
                        o['does'] = self.CONTENTS[rec['type']][1]
                else:
                    if rec['type'] not in self.THING_NAMES:
                        continue
                    o = {'id': oid, 'style': 'block', 'type': rec['type'], 'x': x, 'y': y,
                         'name': self.thing_name(rec['type']), 'remove': None, 'fields': [],
                         'note': 'ROMancer shows this but leaves it as it is.'}
                    if rec['type'] in self.THING_DOES:
                        o['does'] = self.THING_DOES[rec['type']]
                if note:
                    o['note'] = (o.get('note', '') + ' ' + note).strip()
                out.append(o)
        return out

    def _record(self, part, object_id):
        stage, area = int(part['stage']), int(part['area'])
        kind, _, number = object_id.partition(':')
        if kind not in self.TABLES:
            raise ValueError('ROMancer cannot change that yet.')
        rec = next((r for r in self.records(kind, stage, area) if r['index'] == int(number)), None)
        if rec is None or rec['size'] != 6:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        return stage, area, kind, rec

    def edit(self, part, object_id, values, remove=False):
        stage, area, kind, rec = self._record(part, object_id)
        if kind == 'thing':
            raise ValueError('ROMancer leaves this as it is.')
        watch = {'kind': kind, 'stage': stage, 'area': area, 'index': rec['index'], 'slot': rec['slot'],
                 'base': self.SLOT_BASE[kind], 'cam': list(rec['cam']), 'old': rec['type'], 'sx': rec['sx']}
        if remove:
            # the later records of the list move up one place and the list ends one record sooner
            start, end = rec['offset'], self.list_end(kind, stage, area)
            tail = self.rom[start + 6:end + 1]
            new = bytes(tail) + bytes([0xFD]) * 6
            writes = [(start + i, self.rom[start + i], new[i]) for i in range(len(new)) if self.rom[start + i] != new[i]]
            what = self.enemy_name(rec['type']) if kind == 'enemy' else 'candle'
            # the records after it now carry one number less; the watcher looks for the removed type at that place
            watch.update({'removing': True, 'name': what})
            return {'writes': writes, 'title': f'Remove the {what}', 'watch': watch}
        if kind == 'enemy':
            value = int(values.get('type'))
            if value not in {c['value'] for c in self.enemy_choices(stage, area)}:
                raise ValueError('Choose one of the enemies this area uses.')
            name = self.enemy_name(value)
            title = f'Enemy here: {name}'
        else:
            value = int(values.get('contents'))
            if value not in self.CONTENTS:
                raise ValueError('That choice is not one of the game’s own.')
            name = self.content_name(value)
            title = f'Candle holds: {name}'
        at = rec['offset'] + 3
        watch.update({'removing': False, 'wanted': value, 'name': name})
        return {'writes': [(at, self.rom[at], value)] if self.rom[at] != value else [], 'title': title, 'watch': watch}

    def watcher(self, watch):
        return _Cv2Watcher(watch)


class _Cv2Watcher(Watcher):
    """Watches the object slots of the edited list ((base + slot) * 256). A spawned object keeps its record number in
    byte 5, its type in byte 0 (bit 7 while it starts) and its screen x in byte $17. The object's place is the record's
    camera place plus its screen x; the watcher starts looking when that place is between the left edge of the screen
    and the record's screen x (walking right, the moment the game spawns it), and looks for 30 frames.

    A swap is seen when the record's slot holds the record number with the chosen type. A removal replays the original
    game first: there an object of the removed type must be in one of the list's slots near that screen x; in the
    changed game none may be."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.compare = bool(watch.get('removing'))
        self.seen = {}
        self.passed = {}

    def see(self, ram, frame, run):
        w = self.w
        if ram is None or ram[0x8C0] != w['stage'] or ram[0x8C1] != w['area']:
            return False
        cam = (ram[0xA86] & 0x0F) * 160 + ram[0xA85]
        place = w['cam'][0] * 160 + w['cam'][1] + w['sx']
        on = place - cam
        if run not in self.passed:
            if not 0 <= on <= min(w['sx'], 160):
                return False
            self.passed[run] = frame
        if frame - self.passed[run] > 30:
            return True
        if w['removing']:
            for s in range(w['base'], w['base'] + 8):
                a = (s - 0xC0) * 0x100
                if ram[a] and ram[a] & 0x7F == w['old'] & 0x7F and abs(((ram[a + 0x17] - on + 128) & 0xFF) - 128) <= 24:
                    self.seen[run] = True
            return False
        a = (w['base'] + w['slot'] - 0xC0) * 0x100
        if ram[a] and ram[a + 5] == w['index']:
            self.seen[run] = ram[a] & 0x7F
            return True
        return False

    def result(self):
        w = self.w
        if 'changed' not in self.passed:
            return super().result()
        if w['removing']:
            if self.compare and not self.seen.get('original'):
                return {'state': 'warn', 'text': 'In the original game nothing of that kind appeared there in the recorded walk, '
                                                 'so the removal couldn’t be told apart.'}
            ok = not self.seen.get('changed')
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the {w["name"]} no longer appears.' if ok
                    else f'Played from the start, the {w["name"]} still appears.'}
        got = self.seen.get('changed')
        if got is None:
            return {'state': 'bad', 'text': 'Played from the start, nothing appeared there.'}
        ok = got == w['wanted'] & 0x7F
        what = 'enemy' if w['kind'] == 'enemy' else 'candle'
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now puts {w["name"]} there.' if ok and what == 'enemy'
                else f'Played from the start, the candle now holds {w["name"]}.' if ok
                else f'Played from the start, the {what} there is type 0x{got:02X}, not what was chosen.'}


PROFILES = [BelmontsRevenge]
