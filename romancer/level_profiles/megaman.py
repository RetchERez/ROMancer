"""What ROMancer knows about the levels of the NES Mega Man games: each stage's sections and how they link, and the
enemies and items the stage places, all read from the games' own tables (research/megaman-level-profile.md).

Mega Man and Mega Man 2 share the stage engine: a stage is a chain of sections, each a row of screens numbered along
the whole stage. One byte per section (low 5 bits: screens - 1; $80 the next section is above, $40 below, $20 to the
right; 0 for the last section, the boss room) is read by the same scrolling code in both games. Enemies and items are
records sorted by screen and x; the game spawns a record when the camera comes near and remembers which record each
object slot holds. Each game is proven on its own (profile_check.py runs and scripted experiments).
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER = 16


class _MegaMan(Profile):
    system = 'nes'
    STAGES: dict = {}
    NAMES: dict = {}
    PICKUPS: set = set()        # item types the player collects
    LINKS = {0x80: 'Way up to the next section', 0x40: 'Way down to the next section',
             0x20: 'The next section continues to the right'}
    RAM: dict = {}              # stage, segment, first, last, screen, x (camera)
    SLACK = 96                  # pixels past a record's spot by which the camera's right edge has surely spawned it

    # ---- ROM reading
    def bank_offset(self, bank: int, address: int) -> int:
        """File offset of a CPU address in a 16 KB bank ($8000-$BFFF, or the last bank at $C000)."""
        base = 0xC000 if address >= 0xC000 else 0x8000
        return HEADER + bank * 0x4000 + (address - base)

    def byte(self, bank: int, address: int) -> int:
        return self.rom[self.bank_offset(bank, address)]

    def word(self, bank: int, address: int) -> int:
        return self.byte(bank, address) | self.byte(bank, address + 1) << 8

    # ---- per game: stage_bank(stage), start(stage) -> (first screen, first segment), SEGMENTS, records(stage),
    #      remove_writes(stage, record), slots(ram)
    def sections(self, stage: int) -> list:
        """[{'segment', 'first', 'last', 'link'}]: the stage's sections, from its start to the boss room."""
        bank = self.stage_bank(stage)
        screen, segment = self.start(stage)
        out = []
        while len(out) < 40 and segment < 64:
            flags = self.byte(bank, self.SEGMENTS + segment)
            count = (flags & 0x1F) + 1
            out.append({'segment': segment, 'first': screen, 'last': screen + count - 1, 'link': flags & 0xE0})
            if flags & 0xE0 == 0:
                break
            screen += count
            segment += 1
        return out

    def where(self, ram):
        r = self.RAM
        stage = ram[r['stage']]
        if stage not in self.STAGES:
            return None
        sections = self.sections(stage)
        number = ram[r['segment']] - sections[0]['segment']
        if not 0 <= number < len(sections):
            return None
        here = sections[number]
        if (ram[r['first']], ram[r['last']]) != (here['first'], here['last']) or not here['first'] <= ram[r['screen']] <= here['last']:
            return None         # the stage is not running (boss intro, READY, menus)
        return {'part': {'stage': stage, 'section': number}, 'x': (ram[r['screen']] - here['first']) * 256 + ram[r['x']], 'y': 0}

    def stage_of(self, ram):
        return ram[self.RAM['stage']]

    def camera(self, ram):
        return ram[self.RAM['screen']] * 256 + ram[self.RAM['x']]

    def part_name(self, part):
        name = self.STAGES.get(int(part['stage']), f'Stage {int(part["stage"]) + 1}')
        return f'{name}, section {int(part["section"]) + 1}'

    def type_name(self, kind: int) -> str:
        if kind in self.NAMES:
            return self.NAMES[kind]
        return f'{"Item" if kind in self.PICKUPS else "Enemy"} {kind:#04x}'

    def is_item(self, record) -> bool:
        return record['type'] in self.PICKUPS

    def choice_list(self, record) -> str:
        return 'items' if self.is_item(record) else 'enemies'

    def objects(self, part):
        stage, number = int(part['stage']), int(part['section'])
        sections = self.sections(stage)
        if not 0 <= number < len(sections):
            return []
        here = sections[number]
        out = []
        for record in self.records(stage):
            if not here['first'] <= record['screen'] <= here['last'] or not record['editable']:
                continue
            item = self.is_item(record)
            out.append({'id': f'{record["list"]}:{record["number"]}', 'style': 'item' if item else 'enemy', 'type': record['type'],
                        'x': (record['screen'] - here['first']) * 256 + record['x'], 'y': min(239, record['y'] + 8),
                        'name': self.type_name(record['type']), 'detail': f'screen {record["screen"] - here["first"] + 1} of this section',
                        'fields': [{'key': 'type', 'label': 'Item' if item else 'Swap for', 'value': record['type'],
                                    'choices': self.choice_list(record)}],
                        'remove': 'Remove this item' if item else 'Remove this enemy'})
        if here['link'] in self.LINKS:
            width = (here['last'] - here['first'] + 1) * 256
            out.append({'id': f'link:{number}', 'style': 'block', 'type': 'link', 'name': self.LINKS[here['link']],
                        'x': width - 8 if here['link'] == 0x20 else width - 128, 'y': {0x80: 24, 0x40: 239}.get(here['link'], 160),
                        'detail': f'this section has {here["last"] - here["first"] + 1} screens', 'fields': [], 'remove': None})
        return out

    def all_records(self):
        for stage in self.STAGES:
            yield from (r for r in self.records(stage) if r['editable'])

    def choices(self):
        if not hasattr(self, '_choices'):
            found = {}
            for record in self.all_records():
                found.setdefault(self.choice_list(record), set()).add(record['type'])
            self._choices = {name: [{'value': k, 'name': self.type_name(k)} for k in sorted(kinds)] for name, kinds in found.items()}
        return self._choices

    def edit(self, part, object_id, values, remove=False):
        stage = int(part['stage'])
        listed, _, number = object_id.partition(':')
        records = [r for r in self.records(stage) if r['list'] == listed]
        record = next((r for r in records if str(r['number']) == number and r['editable']), None)
        if record is None:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        base = {'stage': stage, 'list': listed, 'record': record['number'], 'spot': record['screen'] * 256 + record['x'],
                'old': record['type']}
        if remove:
            later = [r for r in records if r['number'] > record['number']]
            if later:
                base.update(next=later[0]['screen'] * 256 + later[0]['x'], next_type=later[0]['type'])
            return {'writes': self.remove_writes(stage, record), 'title': f'Remove the {self.type_name(record["type"]).lower()}',
                    'watch': {**base, 'kind': 'remove'}}
        new = int(values['type'])
        if not any(c['value'] == new for c in self.choices().get(self.choice_list(record), [])):
            raise ValueError('That choice is not one of the game’s own.')
        at = record['type_at']
        writes = [(at, self.rom[at], new)] if self.rom[at] != new else []
        return {'writes': writes, 'title': f'{self.type_name(record["type"])} becomes {self.type_name(new).lower()}',
                'watch': {**base, 'kind': 'swap', 'new': new, 'name': self.type_name(new)}}

    @staticmethod
    def shift_writes(rom, arrays, number: int, count: int, size: int = 1) -> list:
        """Take entry `number` out of arrays of `count` entries of `size` bytes, the last being the one-byte end mark:
        the later entries and the end mark move up one entry."""
        writes = []
        for start in arrays:
            for i in range(number * size, (count - 2) * size + 1):
                old, new = rom[start + i], rom[start + i + size]
                if old != new:
                    writes.append((start + i, old, new))
        return writes

    def watcher(self, watch):
        return _SpawnWatcher(self, watch)

    def signature(self, kind):
        """What the game's RAM shows for an object of this type (the type itself in Mega Man and Mega Man 2)."""
        return kind


class MegaMan1(_MegaMan):
    """Mega Man (USA). Spawn code: fixed bank $D8C0-$DA31. Enemy lists: bank 6, pointer table $A452 by stage, records of
    4 bytes [screen, x, y, type] ended by screen $FF (type $FF loads graphics, y $FE fills every slot, y $FF starts an
    event: these are not editable). Sections: stage bank $8C71 + segment, first segment $93A0 (bank 5) and first screen
    $C2EB by stage. Items are types $3C-$47 (pickup code $C833)."""
    name = 'Mega Man'
    sha256s = ('6f74e8a7575ab43a36ea4cb337114ca1af8b1955b7e8ee4a6088a3824e736e34',)
    # stage numbers measured on the stage select ($31 as the cursor goes round)
    STAGES = {0: 'Cut Man stage', 1: 'Ice Man stage', 2: 'Bomb Man stage', 3: 'Fire Man stage', 4: 'Elec Man stage',
              5: 'Guts Man stage', 6: 'Wily stage 1', 7: 'Wily stage 2', 8: 'Wily stage 3', 9: 'Wily stage 4'}
    # named from what the game draws when each type is spawned in its own stage (trace/v15_profiles/megaman/lab_s*.png)
    # and, for items, the pickup code at $C833 ($AD = refill: bit 7 weapon energy, 2 or 10 units)
    NAMES = {0x00: 'Blader', 0x01: 'Met', 0x02: 'Kamadoma', 0x03: 'Met', 0x04: 'Octopus Battery', 0x05: 'Screw Bomber',
             0x07: 'Peng', 0x21: 'Octopus Battery', 0x3D: 'Small weapon energy', 0x3E: 'Small life energy',
             0x3F: 'Large weapon energy', 0x40: 'Large life energy', 0x41: 'Extra life', 0x42: 'Magnet Beam',
             0x45: 'Full refill of all energy'}
    PICKUPS = set(range(0x3C, 0x48))
    RAM = {'stage': 0x31, 'segment': 0x29, 'first': 0x27, 'last': 0x28, 'screen': 0x1B, 'x': 0x1A}
    LIST_TABLE = 0xA452     # bank 6
    SEGMENTS = 0x8C71       # stage bank
    FIRST_SEGMENT = 0x93A0  # bank 5, by stage
    FIRST_SCREEN = 0xC2EB   # fixed bank, by stage
    ENEMY_START = 0x93C3    # bank 5, (restart point * 12 + stage): the last record behind the restart point

    @staticmethod
    def stage_bank(stage: int) -> int:
        return stage if stage < 6 else stage - 6

    def start(self, stage):
        return self.byte(7, self.FIRST_SCREEN + stage), self.byte(5, self.FIRST_SEGMENT + stage)

    def records(self, stage: int) -> list:
        address = self.word(6, self.LIST_TABLE + stage * 2)
        out = []
        for number in range(256):
            at = self.bank_offset(6, address + number * 4)
            screen, x, y, kind = self.rom[at:at + 4]
            if screen == 0xFF:
                break
            out.append({'list': 'record', 'number': number, 'offset': at, 'type_at': at + 3, 'screen': screen, 'x': x, 'y': y,
                        'type': kind, 'editable': kind != 0xFF and y < 0xFE})
        return out

    def remove_writes(self, stage, record):
        """The later records (and the end mark) move up by one; each restart point of the stage that has the removed
        record behind it counts one record fewer."""
        records = self.records(stage)
        start = records[0]['offset']
        writes = self.shift_writes(self.rom, [start], record['number'], len(records) + 1, 4)
        for row in range(3):
            at = self.bank_offset(5, self.ENEMY_START + row * 12 + stage)
            old = self.rom[at]
            if old != 0xFF and old >= record['number']:
                writes.append((at, old, old - 1))
        return writes

    @staticmethod
    def slots(ram):
        """[(slot, list, record number, type, world x)] for the stage's placed objects that are alive."""
        return [(slot, 'record', ram[0x6B + slot], ram[0x6E0 + slot], ram[0x460 + slot] * 256 + ram[0x480 + slot])
                for slot in range(0x10, 0x20) if ram[0x400 + slot] == 0xFF and ram[0x600 + slot] != 0xF8]


class MegaMan2(_MegaMan):
    """Mega Man 2 (USA). Spawn code: fixed bank $D658-$D804. Each stage bank (stage & 7; the Wily stages share the banks
    of the first six) holds two lists of parallel arrays ended by screen $FF: enemies $B600 screen, $B700 x, $B800 y,
    $B900 type, and objects that stay gone once taken $BA00 screen, $BA40 x, $BA80 y, $BAC0 type. Restart points
    $BB00-$BB41 (screen $BB06, enemy records behind $BB0C, item records behind $BB12, segment $BB30; 0-2 the robot
    master stage, 3-5 the Wily stage). Sections: stage bank $B400 + segment (same rule as Mega Man). Pickups $76-$7B
    (pickup jump table $84DC, bank 14)."""
    name = 'Mega Man 2'
    sha256s = ('9f5fa21062933e89c4f923d7755b6df185b054e84d9b5a6ef54216ac4dd67070',)
    STAGES = {0: 'Heat Man stage', 1: 'Air Man stage', 2: 'Wood Man stage', 3: 'Bubble Man stage', 4: 'Quick Man stage',
              5: 'Flash Man stage', 6: 'Metal Man stage', 7: 'Crash Man stage', 8: 'Wily stage 1', 9: 'Wily stage 2',
              10: 'Wily stage 3', 11: 'Wily stage 4', 12: 'Wily stage 5', 13: 'Wily stage 6'}
    # pickups named from the pickup code; enemies from what the game draws when each type is spawned in its own stage
    # (trace/v15_profiles/megaman/lab2_*.png, made by name2.py)
    NAMES = {0x0C: 'Kerog', 0x17: 'Robbit', 0x40: 'Air Tikki', 0x41: 'Air Tikki', 0x4E: 'Sniper Armor', 0x76: 'Large life energy', 0x77: 'Small life energy', 0x78: 'Large weapon energy', 0x79: 'Small weapon energy',
             0x7A: 'Energy Tank', 0x7B: 'Extra life'}
    PICKUPS = set(range(0x76, 0x7C))
    RAM = {'stage': 0x2A, 'segment': 0x38, 'first': 0x14, 'last': 0x15, 'screen': 0x20, 'x': 0x1F}
    SEGMENTS = 0xB400
    LISTS = {'enemy': (0xB600, 0xB700, 0xB800, 0xB900, 256), 'item': (0xBA00, 0xBA40, 0xBA80, 0xBAC0, 64)}
    BEHIND = {'enemy': 0xBB0C, 'item': 0xBB12}

    @staticmethod
    def stage_bank(stage: int) -> int:
        return stage & 7

    def start(self, stage):
        point = 3 if stage & 8 else 0
        bank = self.stage_bank(stage)
        return self.byte(bank, 0xBB06 + point), self.byte(bank, 0xBB30 + point)

    def records(self, stage: int) -> list:
        bank = self.stage_bank(stage)
        out = []
        for listed, (screens, xs, ys, kinds, most) in self.LISTS.items():
            for number in range(most):
                screen = self.byte(bank, screens + number)
                if screen == 0xFF:
                    break
                out.append({'list': listed, 'number': number, 'type_at': self.bank_offset(bank, kinds + number), 'screen': screen,
                            'x': self.byte(bank, xs + number), 'y': self.byte(bank, ys + number),
                            'type': self.byte(bank, kinds + number), 'editable': True})
        return out

    def is_item(self, record):
        return record['list'] == 'item' and record['type'] in self.PICKUPS

    def type_name(self, kind):
        if kind in self.NAMES or kind in self.PICKUPS:
            return super().type_name(kind)
        if not hasattr(self, '_enemy_types'):
            self._enemy_types = {r['type'] for r in self.all_records() if r['list'] == 'enemy'}
        return f'{"Enemy" if kind in self._enemy_types else "Object"} {kind:#04x}'

    def choice_list(self, record):
        return 'items' if record['list'] == 'item' else 'enemies'

    def remove_writes(self, stage, record):
        """The later records of the list (and its end mark) move up by one; each restart point in the bank that has the
        removed record behind it counts one fewer."""
        bank = self.stage_bank(stage)
        listed = record['list']
        count = sum(1 for r in self.records(stage) if r['list'] == listed) + 1
        arrays = [self.bank_offset(bank, a) for a in self.LISTS[listed][:4]]
        writes = self.shift_writes(self.rom, arrays, record['number'], count)
        for point in range(6):
            at = self.bank_offset(bank, self.BEHIND[listed] + point)
            if self.rom[at] > record['number']:
                writes.append((at, self.rom[at], self.rom[at] - 1))
        return writes

    def item_types(self):
        if not hasattr(self, '_item_types'):
            self._item_types = {r['type'] for r in self.all_records() if r['list'] == 'item'} | self.PICKUPS
        return self._item_types

    def slots(self, ram):
        """Alive slots ($0430 bit 7). An enemy-list object has its record number in $0100 and $0120 = 0; an item-list
        object has its record number in both $0130 and $0120 (spawn code $D753 / $D7CC)."""
        out = []
        for slot in range(16):
            if ram[0x430 + slot] & 0x80:
                kind, x = ram[0x410 + slot], ram[0x450 + slot] * 256 + ram[0x470 + slot]
                if ram[0x120 + slot] == 0:
                    out.append((slot, 'enemy', ram[0x100 + slot], kind, x))
                if ram[0x120 + slot] == ram[0x130 + slot] and (ram[0x120 + slot] or kind in self.item_types()):
                    out.append((slot, 'item', ram[0x130 + slot], kind, x))
        return out


class _MegaMan3On(_MegaMan):
    """Mega Man 3 to 6 keep each stage's tables in an 8 KB bank switched in at $A000 and give each section a byte that
    describes the section itself (see MegaMan3.sections), not the way on to the next one."""
    HEADER_BANK = 0x2000

    def bank_offset(self, bank: int, address: int) -> int:
        """File offset of a CPU address in an 8 KB bank (mapped at $8000-$BFFF; the fixed bank at $C000-$FFFF is the
        last 16 KB of the PRG ROM)."""
        if address >= 0xC000:
            return HEADER + (self.rom[4] * 0x4000 - 0x4000) + (address - 0xC000)
        return HEADER + bank * 0x2000 + (address & 0x1FFF)


class MegaMan3(_MegaMan3On):
    """Mega Man 3 (USA). Spawn code: bank 26 at $8000, $9C90-$9D37 (the camera scan $9C01-$9C8F). Stage s keeps its
    tables in 8 KB bank s at $A000: records $AB00 screen, $AC00 x, $AD00 y, $AE00 type (at most $C0, ended by screen
    $FF), sections $AA40, restart points $AAF0 section, $AAF8 screen (ended by $FF), $ABC0 records behind. A spawned
    record: slot X $10-$1F, $0300 bit 7 alive, $04C0 record number, $0380/$0360 x, $03C0 y; the type itself is not
    kept, only what it sets from the type tables in bank 0 ($A100: main routine into $0320, $A300: sprite)."""
    name = 'Mega Man 3'
    sha256s = ('d50c957bd76c6af2c2684983e3f8d1a3904c38811cd8424a7dd1480f1d21caaa',)
    # $22 measured on the stage select (one direction from the centre, then Start; pictures stg3/*.png); 8-15 by writing
    # $22 as the stage starts (pk3/*.png): the stage loads and plays, its look named in the notes
    STAGES = {0: 'Needle Man stage', 1: 'Magnet Man stage', 2: 'Gemini Man stage', 3: 'Hard Man stage', 4: 'Top Man stage',
              5: 'Snake Man stage', 6: 'Spark Man stage', 7: 'Shadow Man stage'}
    # enemies from what the game draws when the stage places them (trace/v15_profiles/megaman/wn3.png, walkname.py);
    # pickups from what it draws when each is given to a stage's first record (lab3_items.png, namex.py)
    NAMES = {0x1B: 'Hari Harry', 0x3B: 'Penpen', 0x50: 'Large life energy', 0x51: 'Small life energy',
             0x52: 'Large weapon energy', 0x53: 'Small weapon energy', 0x54: 'Energy Tank', 0x55: 'Extra life'}
    PICKUPS = set(range(0x50, 0x57))
    RAM = {'stage': 0x22, 'section': 0x2B, 'into': 0x2D, 'count': 0x2C, 'screen': 0xF9, 'x': 0xFC}
    SECTIONS = 0xAA40
    RESTART_SCREEN, RESTART_BEHIND = 0xAAF8, 0xABC0
    LISTS = (0xAB00, 0xAC00, 0xAD00, 0xAE00)
    MOST = 0xC0
    SLACK = 16                  # the scan spawns a record as soon as camera + 255 reaches its screen and x ($9C5F)
    TYPE_BANK, ROUTINE, ENERGY = 0, 0xA100, 0xA400
    LAST_STAGE = 15

    def sections(self, stage: int) -> list:
        """A section byte describes its own section: low 5 bits screens - 1, $20 it scrolls sideways, $80 it is entered
        going up, $40 going down (scroll code $E24A-$E2B4 and $E3C7-$E464). The next section follows on to the right when
        both bytes have $20 and the next has neither $80 nor $40; up or down when the next has $80 or $40. Anything else
        ($00, or $FF in the Wily stages) cannot be reached and ends the stage."""
        out = []
        screen = 0
        for number in range(40):
            flags = self.byte(stage, self.SECTIONS + number)
            count = (flags & 0x1F) + 1
            out.append({'segment': number, 'first': screen, 'last': screen + count - 1, 'flags': flags, 'link': 0})
            following = self.byte(stage, self.SECTIONS + number + 1) if number < 39 else 0
            if following & 0xC0 in (0x80, 0x40):
                out[-1]['link'] = following & 0xC0
            elif following & 0xC0 == 0 and following & 0x20 and flags & 0x20:
                out[-1]['link'] = 0x20
            else:
                break
            screen += count
        return out

    def stage_bank(self, stage):
        return stage

    def where(self, ram):
        r = self.RAM
        stage = ram[r['stage']]
        if stage > self.LAST_STAGE or not ram[0x300] & 0x80:      # Mega Man is not in the stage (intro, menus)
            return None
        sections = self.sections(stage)
        number = ram[r['section']]
        if number >= len(sections):
            return None
        here = sections[number]
        screen = ram[r['screen']]
        if screen - ram[r['into']] != here['first'] or screen > here['last'] or ram[r['count']] != here['last'] - here['first']:
            return None
        return {'part': {'stage': stage, 'section': number}, 'x': (screen - here['first']) * 256 + ram[r['x']], 'y': 0}

    def records(self, stage: int) -> list:
        screens, xs, ys, kinds = self.LISTS
        sections = self.sections(stage)
        boss = sections[-1]['first']
        out = []
        for number in range(self.MOST):
            screen = self.byte(stage, screens + number)
            if screen == 0xFF:
                break
            out.append({'list': 'record', 'number': number, 'type_at': self.bank_offset(stage, kinds + number), 'screen': screen,
                        'x': self.byte(stage, xs + number), 'y': self.byte(stage, ys + number),
                        'type': self.byte(stage, kinds + number), 'editable': screen < boss and not self.is_boss(self.byte(stage, kinds + number))})
        return out

    def is_boss(self, kind) -> bool:
        """Types that start with a boss's full energy bar (28 in the type's energy table): bosses, left as they are."""
        return kind not in self.PICKUPS and self.byte(self.TYPE_BANK, self.ENERGY + kind) == 0x1C

    def all_records(self):
        for stage in range(self.LAST_STAGE + 1):
            yield from (r for r in self.records(stage) if r['editable'])

    def part_name(self, part):
        stage = int(part['stage'])
        name = self.STAGES.get(stage, f'Stage {stage + 1}')
        return f'{name}, section {int(part["section"]) + 1}'

    def remove_writes(self, stage, record):
        """The later records (and the end mark) move up by one; each restart point that has the removed record behind
        it counts one record fewer (restart code $CC18-$CC75 starts the spawner at $ABC0 + point)."""
        count = sum(1 for _ in self.records(stage)) + 1
        arrays = [self.bank_offset(stage, a) for a in self.LISTS]
        writes = self.shift_writes(self.rom, arrays, record['number'], count)
        for point in range(8):
            if self.byte(stage, self.RESTART_SCREEN + point) == 0xFF:
                break
            at = self.bank_offset(stage, self.RESTART_BEHIND + point)
            if self.rom[at] > record['number']:
                writes.append((at, self.rom[at], self.rom[at] - 1))
        return writes

    def signature(self, kind):
        """The main routine the type sets ($A100 in bank 0): the slot keeps that, not the type."""
        return None if kind is None else self.byte(self.TYPE_BANK, self.ROUTINE + kind)

    def slots(self, ram):
        """Alive slots $10-$1F: (slot, 'record', record number $04C0, main routine $0320, world x)."""
        return [(slot, 'record', ram[0x4C0 + slot], ram[0x320 + slot], ram[0x380 + slot] * 256 + ram[0x360 + slot])
                for slot in range(0x10, 0x20) if ram[0x300 + slot] & 0x80]

    @staticmethod
    def slot_y(ram, slot):
        return ram[0x3C0 + slot]


class MegaMan4(_MegaMan3On):
    """Mega Man 4 (USA) (Rev 1). Spawn code: bank $38 at $8000, $8090-$818E (camera scan $8010-$808F, as in Mega Man 3).
    Stage s keeps its tables in 8 KB bank $20 + s at $A000: records $B100 screen, $B180 x, $B200 y, $B280 type (at most
    $80, ended by screen $FF; types $C0 and up change palettes and are not objects), first record of each screen $B300
    (32 screens: the restart code $C5CA and the warps start the spawner there), sections $B530 (16), warps $B540 (4 bytes:
    screen, direction, section, screen; ended by a byte $80 or more). A spawned record: slot X $08-$17, $0300 the object
    number from the type ($820F in bank $38), $0438 record number, $0348/$0330 x, $0378 y."""
    name = 'Mega Man 4'
    sha256s = ('1e06f22247921dab39c2350ae1a96cddf74e6e9d25e9d9ddf53686269547bd7f',)
    # $22 measured on the stage select (one direction from the centre, then Start; pictures stg4/*.png)
    STAGES = {0: 'Bright Man stage', 1: 'Toad Man stage', 2: 'Drill Man stage', 3: 'Pharaoh Man stage', 4: 'Ring Man stage',
              5: 'Dust Man stage', 6: 'Dive Man stage', 7: 'Skull Man stage'}
    # pickups from what the game draws when each is given to a stage's first record (lab4_items.png, namey.py)
    NAMES = {0x56: 'Energy Tank', 0x5A: 'Large life energy', 0x5B: 'Small life energy', 0x7A: 'Large weapon energy',
             0x7B: 'Small weapon energy', 0x7C: 'Extra life', 0x7D: 'Balloon item (B)', 0x7E: 'Wire item (W)'}
    PICKUPS = {0x56, 0x5A, 0x5B, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E}
    RAM = {'stage': 0x22, 'section': 0x2B, 'into': 0x2E, 'count': 0x2D, 'screen': 0xF9, 'x': 0xFC}
    PLAYER = 1                  # Mega Man's object number in slot 0 while he is in the stage
    BANKS = 0x20
    SECTIONS, WARPS, FIRST = 0xB530, 0xB540, 0xB300
    LISTS = (0xB100, 0xB180, 0xB200, 0xB280)
    MOST = 0x80
    SLACK = 16
    TYPE_BANK, OBJECT, PICTURE = 0x38, 0x820F, 0x832F
    PICKUP_OBJECTS = (0xC1, 0xC2)
    SECTION_BITS = COUNT_BITS = 0x0F
    LAST_STAGE = 15

    def stage_bank(self, stage):
        return self.BANKS | stage

    def section_bytes(self, stage):
        return [self.byte(self.stage_bank(stage), self.SECTIONS + n) for n in range(16)]

    def warps(self, stage):
        out = []
        bank = self.stage_bank(stage)
        for n in range(8):
            screen = self.byte(bank, self.WARPS + n * 4)
            if screen >= 0x80:
                break
            out.append(tuple(self.byte(bank, self.WARPS + n * 4 + k) for k in range(4)))
        return out

    def sections(self, stage: int) -> list:
        """A section byte: low 4 bits screens - 1, $20 it scrolls sideways, $80 it is entered going up, $40 going down
        (scroll code $CC3C-$CDD4, $CAFF-$CB18). The next section follows on to the right when the next byte's top bits are
        $20 (or $30); up or down when the next byte has $80 or $40; a warp ($B540) at one of the section's screens
        starts another section at its own screen. Sections no way leads to are left out."""
        flags = self.section_bytes(stage)
        firsts = {0: 0}
        todo = [0]
        warps = self.warps(stage)
        while todo:
            number = todo.pop()
            first = firsts[number]
            count = (flags[number] & self.COUNT_BITS) + 1
            if self.link(flags, number) and number + 1 not in firsts:
                firsts[number + 1] = first + count
                todo.append(number + 1)
            for screen, _, section, target in warps:
                if first <= screen < first + count and section < len(flags) and section not in firsts:
                    firsts[section] = target
                    todo.append(section)
        return [{'segment': n, 'first': firsts[n], 'last': firsts[n] + (flags[n] & self.COUNT_BITS), 'flags': flags[n],
                 'link': self.link(flags, n)} for n in sorted(firsts)]

    @staticmethod
    def link(flags, number):
        """Up or down when the next byte has $80 or $40; on to the right when its top bits are $20 (or $30)."""
        following = flags[number + 1] if number + 1 < len(flags) else 0
        if following & 0xC0 in (0x80, 0x40):
            return following & 0xC0
        return 0x20 if following & 0xE0 == 0x20 else 0

    def boss_room(self, stage):
        """The section the stage ends in: behind the boss doors (sections marked $30) with no way on; failing that, the
        furthest section with no way on."""
        chain = self.sections(stage)
        ends = [s for s in chain if not s['link'] and s['flags'] & 0xF0 == 0x30]
        ends = ends or [s for s in chain if not s['link']] or chain
        return max(ends, key=lambda s: s['first'])

    def where(self, ram):
        r = self.RAM
        stage = ram[r['stage']]
        if stage > self.LAST_STAGE or ram[0x300] != self.PLAYER:          # Mega Man is not in the stage
            return None
        number = ram[r['section']] & self.SECTION_BITS
        here = next((s for s in self.sections(stage) if s['segment'] == number), None)
        screen = ram[r['screen']]
        if here is None or screen - ram[r['into']] != here['first'] or screen > here['last'] or ram[r['count']] != here['last'] - here['first']:
            return None
        return {'part': {'stage': stage, 'section': number}, 'x': (screen - here['first']) * 256 + ram[r['x']], 'y': 0}

    def objects(self, part):
        """Parts are named by the section number the game keeps ($2B); some sections cannot be reached and are left out."""
        stage, number = int(part['stage']), int(part['section'])
        order = [s['segment'] for s in self.sections(stage)]
        if number not in order:
            return []
        out = super().objects({'stage': stage, 'section': order.index(number)})
        for o in out:
            if o['id'].startswith('link:'):
                o['id'] = f'link:{number}'
        return out

    def records(self, stage: int) -> list:
        bank = self.stage_bank(stage)
        screens, xs, ys, kinds = self.LISTS
        boss = self.boss_room(stage)
        out = []
        for number in range(self.MOST):
            screen = self.byte(bank, screens + number)
            if screen == 0xFF:
                break
            kind = self.byte(bank, kinds + number)
            out.append({'list': 'record', 'number': number, 'type_at': self.bank_offset(bank, kinds + number), 'screen': screen,
                        'x': self.byte(bank, xs + number), 'y': self.byte(bank, ys + number), 'type': kind,
                        'editable': kind < 0xC0 and not boss['first'] <= screen <= boss['last']})
        return out

    def all_records(self):
        for stage in range(self.LAST_STAGE + 1):
            yield from (r for r in self.records(stage) if r['editable'])

    def part_name(self, part):
        stage = int(part['stage'])
        name = self.STAGES.get(stage, f'Stage {stage + 1}')
        return f'{name}, section {int(part["section"]) + 1}'

    def remove_writes(self, stage, record):
        """The later records (and the end mark) move up by one; each screen whose first record ($B300) comes after the
        removed one starts one record earlier."""
        bank = self.stage_bank(stage)
        count = sum(1 for _ in self.records(stage)) + 1
        arrays = [self.bank_offset(bank, a) for a in self.LISTS]
        writes = self.shift_writes(self.rom, arrays, record['number'], count)
        for screen in range(32):
            at = self.bank_offset(bank, self.FIRST + screen)
            if self.rom[at] > record['number']:
                writes.append((at, self.rom[at], self.rom[at] - 1))
        return writes

    def signature(self, kind):
        """The object number the type sets ($820F in bank $38): the slot keeps that, not the type. Pickups share object
        numbers and differ by the picture the type sets ($832F, kept in $0558), so for them it is both."""
        if kind is None:
            return None
        number = self.byte(self.TYPE_BANK, self.OBJECT + kind)
        return (number, self.byte(self.TYPE_BANK, self.PICTURE + kind)) if number in self.PICKUP_OBJECTS else number

    def slots(self, ram):
        """Slots $08-$17 in use ($0300 not 0): (slot, 'record', record number $0438, object number $0300, world x)."""
        out = []
        for slot in range(0x08, 0x18):
            number = ram[0x300 + slot]
            if number:
                mark = (number, ram[0x558 + slot]) if number in self.PICKUP_OBJECTS else number
                out.append((slot, 'record', ram[0x438 + slot], mark, ram[0x348 + slot] * 256 + ram[0x330 + slot]))
        return out

    @staticmethod
    def slot_y(ram, slot):
        return ram[0x378 + slot]


class MegaMan5(MegaMan4):
    """Mega Man 5 (USA). Spawn code: bank $1B at $8000, $990A-$9A41 (camera scan $988A-$9909, the Mega Man 4 code with
    other addresses). Stage s keeps its tables in 8 KB bank s at $A000: records $AA00 screen, $AA80 x, $AB00 y, $AB80
    type (at most $80, ended by screen $FF; types $C0 and up change palettes), first record of each screen $AC00 (the
    restart code $D39E starts the spawner there), sections $A950 (low 5 bits screens - 1, flags as in Mega Man 4; scroll
    code $CB5F-$CE7B), ladder warps $A9E0. A spawned record: slot X $08-$17, $0300 object number, $0510 the type itself, $0438 record number."""
    name = 'Mega Man 5'
    sha256s = ('010673ff28a6e9e29857260a5acaaff20b44dd09487a48900f6ab71fbcc66d13',)
    # $26 measured on the stage select (one direction from the centre, then Start; pictures stg5/*.png)
    STAGES = {0: 'Gravity Man stage', 1: 'Wave Man stage', 2: 'Stone Man stage', 3: 'Gyro Man stage', 4: 'Star Man stage',
              5: 'Charge Man stage', 6: 'Napalm Man stage', 7: 'Crystal Man stage'}
    NAMES: dict = {}
    PICKUPS: set = set()
    RAM = {'stage': 0x26, 'section': 0x29, 'into': 0x2B, 'count': 0x2A, 'screen': 0xF9, 'x': 0xFC}
    SECTION_BITS = COUNT_BITS = 0x1F
    BANKS = 0
    SECTIONS, WARPS, FIRST = 0xA950, 0xA9E0, 0xAC00
    LISTS = (0xAA00, 0xAA80, 0xAB00, 0xAB80)

    def stage_bank(self, stage):
        return stage

    def section_bytes(self, stage):
        return [self.byte(stage, self.SECTIONS + n) for n in range(24)]

    def warps(self, stage):
        """Ladder warps $A9E0 (4 bytes: screen, direction, screen, section; code $CFF0), as (screen, direction, section,
        screen) like Mega Man 4's."""
        out = []
        for n in range(8):
            screen = self.byte(stage, self.WARPS + n * 4)
            if screen >= 0x80:
                break
            direction, target, section = (self.byte(stage, self.WARPS + n * 4 + k) for k in (1, 2, 3))
            out.append((screen, direction, section, target))
        return out

    def remove_writes(self, stage, record):
        """The later records (and the end mark) move up by one; each screen whose first record ($AC00, one byte per
        screen up to the stage's last) comes after the removed one starts one record earlier."""
        records = self.records(stage)
        arrays = [self.bank_offset(stage, a) for a in self.LISTS]
        writes = self.shift_writes(self.rom, arrays, record['number'], len(records) + 1)
        for screen in range(min(64, max(r['screen'] for r in records) + 2)):
            at = self.bank_offset(stage, self.FIRST + screen)
            if self.rom[at] > record['number']:
                writes.append((at, self.rom[at], self.rom[at] - 1))
        return writes

    def signature(self, kind):
        return kind

    def type_name(self, kind):
        """No type is named yet: the game keeps a type number in each slot, and the pictures taken so far do not settle
        which is which."""
        return self.NAMES.get(kind, f'Object {kind:#04x}')

    def slots(self, ram):
        """Slots $08-$17 in use ($0300 not 0): (slot, 'record', record number $0438, type $0510, world x)."""
        return [(slot, 'record', ram[0x438 + slot], ram[0x510 + slot], ram[0x348 + slot] * 256 + ram[0x330 + slot])
                for slot in range(0x08, 0x18) if ram[0x300 + slot]]


class _SpawnWatcher(Watcher):
    """An enemy or item edit: replay the walk and look at the object the game places for the record's number. A swap
    counts once that object shows with the chosen type. After a removal the later records move up one number, so the
    number must bring nothing by the time the camera has passed the spot (or the next record's object, at its own spot)."""
    every = 2

    def __init__(self, profile, watch):
        self.p, self.w = profile, watch
        self.seen = self.at = None      # type and first x of the object the game spawned for this record number
        self.passed = False

    def see(self, ram, frame, run):
        p, w = self.p, self.w
        if p.stage_of(ram) != w['stage'] or p.where(ram) is None:
            return False
        mark = p.signature
        for slot, listed, number, kind, x in p.slots(ram):
            if listed == w['list'] and number == w['record'] and (w['kind'] == 'remove' or kind in (mark(w['old']), mark(w.get('new')))):
                self.seen, self.at = kind, x
                return True
        if p.camera(ram) + 255 >= w['spot'] + p.SLACK:     # the game spawns a record once the camera's right edge reaches it
            self.passed = True
            return w['kind'] == 'remove'
        return False

    def result(self):
        w, mark = self.w, self.p.signature

        def name(kind):     # the type behind what the game shows (games that keep a routine, not the type, in RAM)
            for known in (w['old'], w.get('new'), w.get('next_type')):
                if known is not None and mark(known) == kind:
                    return self.p.type_name(known)
            return self.p.type_name(kind)
        if w['kind'] == 'swap':
            if self.seen is None:
                return super().result()
            ok = self.seen == mark(w['new'])
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the game now places {w["name"].lower()} there.' if ok
                    else f'Played from the start, the game placed {name(self.seen).lower()} there, not what was chosen.'}
        if self.seen is None:
            if self.passed:
                return {'state': 'good', 'text': 'Played from the start, nothing appears there any more.'}
            return super().result()
        if w.get('next') is not None and self.seen == mark(w['next_type']) and abs(self.at - w['next']) < abs(self.at - w['spot']):
            return {'state': 'good', 'text': 'Played from the start, nothing appears there any more; the next object in the list comes next.'}
        return {'state': 'bad', 'text': f'Played from the start, {name(self.seen).lower()} still appears there.'}


PROFILES = [MegaMan1, MegaMan2, MegaMan3, MegaMan4, MegaMan5]
