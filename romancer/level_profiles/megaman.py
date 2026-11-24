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
        for slot, listed, number, kind, x in p.slots(ram):
            if listed == w['list'] and number == w['record'] and (w['kind'] == 'remove' or kind in (w['old'], w.get('new'))):
                self.seen, self.at = kind, x
                return True
        if p.camera(ram) + 255 >= w['spot'] + 96:     # the game spawns a record once the camera's right edge reaches it
            self.passed = True
            return w['kind'] == 'remove'
        return False

    def result(self):
        w, name = self.w, self.p.type_name
        if w['kind'] == 'swap':
            if self.seen is None:
                return super().result()
            ok = self.seen == w['new']
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the game now places {w["name"].lower()} there.' if ok
                    else f'Played from the start, the game placed {name(self.seen).lower()} there, not what was chosen.'}
        if self.seen is None:
            if self.passed:
                return {'state': 'good', 'text': 'Played from the start, nothing appears there any more.'}
            return super().result()
        if w.get('next') is not None and self.seen == w['next_type'] and abs(self.at - w['next']) < abs(self.at - w['spot']):
            return {'state': 'good', 'text': 'Played from the start, nothing appears there any more; the next object in the list comes next.'}
        return {'state': 'bad', 'text': f'Played from the start, {name(self.seen).lower()} still appears there.'}


PROFILES = [MegaMan1, MegaMan2]
