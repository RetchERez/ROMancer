"""Capcom's Disney NES games. Each game here has its own class, decoded and proven on its own: the five games were
checked for a shared object engine and do not share one (DuckTales' spawn routine, bank 6 $AF2B, is not in the others).

DuckTales (USA), research/capcom_disney-level-profile.md:

* A land ($F6: 0 Amazon, 1 Transylvania, 2 African Mines, 3 Himalayas, 4 Moon) is a grid of screens: rows ($CE57 per
  land) of 8 screens ($CE61). Camera: row $F1, screen in the row $F3, x in the screen $F2.
* Objects: per land five arrays (pointer tables at bank 6 $B050, 9 lands x 2 bytes x 5 tables): screen, x, a start
  index per row, y and kind. A row's records are sorted by screen and x and end with a screen byte of $80 or more.
* Kind: 4 bytes at bank 6 $BE16 + kind * 4: flags (high nibble) and contents (low nibble), graphic ($0620), object
  type ($0710) and a parameter ($07D0). Object slots 1-15: $0700 flags, $0710 type, $0720 x, $0730 screen, $0640 y,
  $06B0 contents, $07F0 the record that spawned it.
* Type $08 with graphic $1B or $3F is a treasure chest: contents n give item $8FB8[n] (graphic $3F: $9016[land * 3 + n]
  first, when it is not 0). Type $08 with graphic bit 7 set is a block or rock holding item $F67B[n]. Type $14 is a
  hidden item: its graphic is the item that appears.
Chip 'n Dale - Rescue Rangers (USA): see the ChipDale class below and the same research notes.
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER_NES = 16


class DuckTales:
    """DuckTales (USA) decoder: object records, kinds and what containers hold."""
    name = 'DuckTales'
    sha256 = '23f395b26644e9fce38b02973f16d8de2a69c358fd7934ec63404acafa1cfeb3'
    BANK6, BANK7 = 0x18000, 0x1C000
    LANDS = ['The Amazon', 'Transylvania', 'African Mines', 'The Himalayas', 'The Moon']
    TABLES = 0xB050          # 5 tables (screen, x, row starts, y, kind) of 9 low bytes then 9 high bytes
    KINDS = 0xBE16
    KIND_COUNT = 0x79
    CHEST_ITEMS, BIG_CHEST_ITEMS, BLOCK_ITEMS = 0x8FB8, 0x9016, 0xF67B
    ROWS, WIDTH = 0xCE57, 0xCE61
    SCREEN_H = 240
    # item numbers: what the game draws for each (pictures in trace/v15_profiles/capcom_disney/shots/itemcrop.png) and
    # what picking it up changed in RAM (money digits $0324-$0329, lives $0361)
    ITEMS = {0x23: 'Small diamond ($2,000)', 0x28: 'Large diamond ($10,000)', 0x61: 'Red diamond ($50,000)',
             0x24: 'Ice cream', 0x25: 'Cake', 0x26: 'Coin with an M', 0x27: 'Extra life', 0x1B: 'Treasure chest'}
    # enemies and other objects named from what the game draws when one is spawned on a land's first screen
    # (shots/p<land>_<kind>.png); the rest show their kind number
    NAMES = {0x01: 'Snake', 0x03: 'Man-eating plant', 0x05: 'Man-eating plant', 0x0C: 'Launchpad',
             0x67: 'Nephew', 0x68: 'Nephew', 0x69: 'Nephew', 0x6A: 'Nephew', 0x6B: 'Nephew', 0x6C: 'Nephew',
             0x6E: 'Nephew', 0x70: 'Nephew', 0x1E: 'Skeleton duck', 0x0B: 'Striped drum', 0x0A: 'Gorilla'}
    CONTAINER_NAMES = {0x1A: 'Stone block', 0x1C: 'Rock', 0x20: 'Block'}
    # kinds left as they are: invisible when spawned (likely triggers or level machinery: $15, $2F, $0C, $3C, $41,
    # $18 and kind $14), the big objects that are each land's boss or set piece ($0D, $50-$54, $5C, $21) and a chest
    # of another object type ($71); what they do is not proven, so they are shown but not offered
    FIXED = {0x0D, 0x0E, 0x14, 0x20, 0x26, 0x2C, 0x2D, 0x2E, 0x2F, 0x37, 0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x50,
             0x51, 0x52, 0x53, 0x54, 0x56, 0x5C, 0x64, 0x65, 0x71, 0x72, 0x73}

    def __init__(self, rom: bytes):
        self.rom = rom

    # ---- reading
    def o6(self, address: int) -> int:
        return HEADER_NES + self.BANK6 + (address - 0x8000)

    def o7(self, address: int) -> int:
        return HEADER_NES + self.BANK7 + (address - 0xC000)

    def b6(self, address: int) -> int:
        return self.rom[self.o6(address)]

    def b7(self, address: int) -> int:
        return self.rom[self.o7(address)]

    def tables(self, land: int) -> dict:
        names = ('screen', 'x', 'starts', 'y', 'kind')
        return {n: self.b6(self.TABLES + 18 * k + land) | self.b6(self.TABLES + 18 * k + 9 + land) << 8
                for k, n in enumerate(names)}

    def rows(self, land: int) -> int:
        return self.b7(self.ROWS + land)

    def count(self, land: int) -> int:
        """How many bytes each of the land's record arrays has (records and row ends): up to the last row's end."""
        t, last = self.tables(land), 0
        for row in range(self.rows(land)):
            i = self.b6(t['starts'] + row)
            while self.b6(t['screen'] + i) < 0x80:
                i += 1
            last = max(last, i)
        return last + 1

    def kind(self, kind: int) -> dict:
        a = self.KINDS + (kind & 0x7F) * 4
        flags, gfx, otype, param = (self.b6(a + i) for i in range(4))
        return {'kind': kind, 'flags': flags & 0xF0, 'contents': flags & 0x0F, 'gfx': gfx, 'type': otype, 'param': param}

    def records(self, land: int) -> list:
        if land >= len(self.LANDS):
            return []
        t, out = self.tables(land), []
        for row in range(self.rows(land)):
            i = self.b6(t['starts'] + row)
            while self.b6(t['screen'] + i) < 0x80:
                k = self.b6(t['kind'] + i)
                out.append({'index': i, 'row': row, 'screen': self.b6(t['screen'] + i), 'x': self.b6(t['x'] + i),
                            'y': self.b6(t['y'] + i), 'kind': k, 'kind_byte': self.o6(t['kind'] + i), **self.role(k, land)})
                i += 1
        return out

    # ---- what a kind is
    def role(self, kind: int, land: int) -> dict:
        k = self.kind(kind)
        if k['type'] == 0x08 and k['gfx'] in (0x1B, 0x3F):
            return {'role': 'chest', 'item': self.chest_item(kind, land)}
        if k['type'] == 0x08 and k['gfx'] & 0x7F in self.CONTAINER_NAMES:
            return {'role': 'block', 'item': self.b7(self.BLOCK_ITEMS + k['contents']) if k['gfx'] & 0x80 else None}
        if k['type'] == 0x14:
            return {'role': 'hidden', 'item': k['gfx']}
        if kind in self.FIXED:
            return {'role': 'fixed', 'item': None}
        return {'role': 'enemy', 'item': None}

    def chest_item(self, kind: int, land: int) -> int:
        k = self.kind(kind)
        if k['gfx'] == 0x3F:
            item = self.b6(self.BIG_CHEST_ITEMS + land * 3 + k['contents'])
            if item:
                return item
        return self.b6(self.CHEST_ITEMS + k['contents'])

    def item_name(self, item) -> str:
        if item is None:
            return 'Nothing'
        return self.ITEMS.get(item, f'Item {item:#04x}')

    def kind_name(self, kind: int, land: int) -> str:
        k, role = self.kind(kind), self.role(kind, land)
        if role['role'] == 'chest':
            return 'Large treasure chest' if k['gfx'] == 0x3F else 'Treasure chest'
        if role['role'] == 'block':
            return self.CONTAINER_NAMES[k['gfx'] & 0x7F]
        if role['role'] == 'hidden':
            return 'Hidden ' + self.item_name(role['item']).split(' (')[0].lower()
        return self.NAMES.get(kind, f'Object {kind:#04x}')

    # ---- choices: always kinds from the game's own table
    def used_kinds(self, land: int) -> list:
        return sorted({r['kind'] for r in self.records(land)})

    def content_choices(self, kind: int, land: int) -> list:
        """Other kinds of the same container (same type and look) that hold something else: [{'value', 'name'}]."""
        here, role = self.kind(kind), self.role(kind, land)
        out, seen = [], set()
        for other in range(self.KIND_COUNT):
            k, r = self.kind(other), self.role(other, land)
            if r['role'] != role['role'] or k['type'] != here['type']:
                continue
            if role['role'] == 'chest' and k['gfx'] != here['gfx']:
                continue
            if role['role'] == 'block' and (k['gfx'] & 0x7F) != (here['gfx'] & 0x7F):
                continue
            if r['item'] is not None and r['item'] not in self.ITEMS:
                continue             # items not identified (and the lands' own treasures, drawn wrong elsewhere)
            if r['item'] in seen or (other != kind and r['item'] == role['item']):
                continue
            seen.add(r['item'])
            out.append({'value': other, 'name': self.item_name(r['item'])})
        return out

    def enemy_choices(self, land: int) -> list:
        """Enemies and other objects this land uses (their pictures are loaded there), one kind per object type."""
        out, seen = [], set()
        for kind in self.used_kinds(land):
            k = self.kind(kind)
            if self.role(kind, land)['role'] != 'enemy' or k['type'] in seen:
                continue
            seen.add(k['type'])
            out.append({'value': kind, 'name': self.kind_name(kind, land)})
        return out

    # ---- writes
    def swap_writes(self, land: int, index: int, kind: int) -> list:
        offset = self.o6(self.tables(land)['kind'] + index)
        return [(offset, self.rom[offset], kind)] if self.rom[offset] != kind else []

    def remove_writes(self, land: int, index: int) -> list:
        """Take record `index` out of the land: later records move down one place in all four arrays, the last place
        becomes a row end ($FF), and the rows after it start one place earlier."""
        t, n = self.tables(land), self.count(land)
        if not 0 <= index < n - 1 or self.b6(t['screen'] + index) >= 0x80:
            raise ValueError('That is not one of this land’s objects.')
        writes = {}
        for name in ('screen', 'x', 'y', 'kind'):
            values = [self.b6(t[name] + i) for i in range(n)]
            new = values[:index] + values[index + 1:] + [0xFF]
            for i, v in enumerate(new):
                writes[self.o6(t[name] + i)] = v
        for row in range(self.rows(land)):
            start = self.b6(t['starts'] + row)
            if start > index:
                writes[self.o6(t['starts'] + row)] = start - 1
        return [(o, self.rom[o], v) for o, v in sorted(writes.items()) if self.rom[o] != v]


class _SpawnWatcher(Watcher):
    """Watches the object slots in the replay. Each time a slot takes a new object (its record number $07F0 changes),
    the spawn position ($0730 screen, $0720 x, $0640 y) is compared with the edited record. A swap counts when the
    object spawned there has the chosen type, graphic and contents; a removal counts when the spot was on screen and
    nothing of the old kind spawned there."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.slots = None
        self.spawned = None
        self.in_view = False

    def see(self, ram, frame, run):
        w = self.w
        if ram[0xF6] != w['land']:
            self.slots = None
            return False
        slots = [(ram[0x700 + s] & 0x80, ram[0x7F0 + s]) for s in range(16)]
        old, self.slots = self.slots, slots
        if ram[0xF1] == w['row']:
            camera = ram[0xF3] * 256 + ram[0xF2]
            if camera - 16 <= w['screen'] * 256 + w['x'] <= camera + 272:
                self.in_view = True
        if old is None:
            return False
        for s in range(1, 16):
            if slots[s][0] and slots[s] != old[s]:
                if (ram[0x730 + s], ram[0x720 + s], ram[0x640 + s]) == (w['screen'], w['x'], w['y']):
                    self.spawned = {'type': ram[0x710 + s], 'gfx': ram[0x620 + s], 'contents': ram[0x6B0 + s],
                                    'holds': bool(ram[0x6C0 + s] & 0x80)}
                    if not w['removing']:
                        return True
        return False

    def result(self):
        w, got = self.w, self.spawned
        if w['removing']:
            if got is not None and got['type'] == w['old_type']:
                return {'state': 'bad', 'text': 'Played from the start, the object still appears there.'}
            if self.in_view:
                return {'state': 'good', 'text': 'Played from the start, nothing appears there any more.'}
            return super().result()
        if got is None:
            return super().result()
        want = w['want']
        ok = got['type'] == want['type'] and got['gfx'] == want['gfx'] and (
            w['role'] not in ('chest', 'block') or got['contents'] == want['contents']) and (
            w['role'] != 'block' or got['holds'] == want['holds'])
        if ok:
            return {'state': 'good', 'text': f'Played from the start, the game now puts {w["name"]} there.'}
        return {'state': 'bad', 'text': f'Played from the start, the game put something else there (object type {got["type"]:#04x}, '
                                        f'graphic {got["gfx"]:#04x}, contents {got["contents"]}), not what was chosen.'}


class DuckTalesProfile(DuckTales, Profile):
    """DuckTales on the common profile interface. A part is a land; x and y are pixels in the land's grid of screens."""
    sha256s = (DuckTales.sha256,)

    def where(self, ram):
        """None outside play: $EA is $40 once a land is running and the spawn pointer $60/$61 is the land's own."""
        land = ram[0xF6]
        if land >= 9 or not ram[0xEA] & 0x40 or ram[0x60] | ram[0x61] << 8 != self.tables(land)['screen']:
            return None
        return {'part': {'land': land}, 'x': ram[0xF3] * 256 + ram[0xF2], 'y': ram[0xF1] * self.SCREEN_H}

    def part_name(self, part):
        land = int(part['land'])
        return self.LANDS[land] if land < len(self.LANDS) else f'Extra area {land}'

    def objects(self, part):
        land = int(part['land'])
        out = []
        for r in self.records(land):
            row = {'id': f'object:{r["index"]}', 'type': r['kind'], 'x': r['screen'] * 256 + r['x'],
                   'y': r['row'] * self.SCREEN_H + r['y'], 'name': self.kind_name(r['kind'], land), 'remove': None}
            if r['role'] in ('chest', 'block', 'hidden'):
                choices = self.content_choices(r['kind'], land)
                row.update(style='secret' if r['role'] == 'hidden' else 'item',
                           detail=('holds ' if r['role'] != 'hidden' else 'gives ') + self.item_name(r['item']).lower(),
                           fields=[{'key': 'kind', 'label': 'Holds' if r['role'] != 'hidden' else 'Gives',
                                    'value': r['kind'], 'choices': choices}] if len(choices) > 1 else [])
                if r['role'] == 'hidden':
                    row['note'] = 'Hidden until Scrooge comes near it.'
            elif r['role'] == 'fixed':
                row.update(style='enemy', fields=[],
                           note='ROMancer does not know what this object does yet, so it stays as it is.')
            else:
                row.update(style='enemy', remove='Remove this object',
                           fields=[{'key': 'kind', 'label': 'Swap for', 'value': r['kind'], 'choices': f'land{land}'}])
            if r['role'] in ('chest', 'block', 'hidden'):
                row['remove'] = 'Remove this object'
            out.append(row)
        return out

    def choices(self):
        return {f'land{land}': self.enemy_choices(land) for land in range(len(self.LANDS))}

    def edit(self, part, object_id, values, remove=False):
        land = int(part['land'])
        kind_of, _, number = object_id.partition(':')
        if kind_of != 'object':
            raise ValueError('ROMancer cannot change that yet.')
        rec = next((r for r in self.records(land) if r['index'] == int(number)), None)
        if rec is None:
            raise ValueError('That is not part of this land any more. Reopen the map.')
        watch = {'land': land, 'row': rec['row'], 'screen': rec['screen'], 'x': rec['x'], 'y': rec['y'],
                 'old_type': self.kind(rec['kind'])['type']}
        if rec['role'] == 'fixed':
            raise ValueError('ROMancer cannot change that object yet.')
        if remove:
            return {'writes': self.remove_writes(land, rec['index']), 'title': f'Remove {self.kind_name(rec["kind"], land).lower()}',
                    'watch': {**watch, 'removing': True}}
        kind = int(values.get('kind'))
        if rec['role'] == 'enemy':
            allowed = [c['value'] for c in self.enemy_choices(land)]
        else:
            allowed = [c['value'] for c in self.content_choices(rec['kind'], land)]
        if kind not in allowed:
            raise ValueError('That choice is not one of the game’s own.')
        k, role = self.kind(kind), self.role(kind, land)
        name = self.kind_name(kind, land) if rec['role'] == 'enemy' else self.item_name(role['item']).lower()
        if rec['role'] == 'enemy':
            title = f'Object here: {name}'
        elif rec['role'] == 'hidden':
            title = f'Hidden item gives: {name}'
        else:
            title = f'{self.kind_name(rec["kind"], land)} holds: {name}'
        want = {'type': k['type'], 'gfx': k['gfx'] & 0x7F if (k['type'] == 0x08 and k['gfx'] & 0x80) else k['gfx'],
                'contents': k['contents'], 'holds': bool(k['type'] == 0x08 and k['gfx'] & 0x80)}
        return {'writes': self.swap_writes(land, rec['index'], kind), 'title': title,
                'watch': {**watch, 'removing': False, 'want': want, 'role': rec['role'],
                          'name': name if rec['role'] == 'enemy' else
                          f'a hidden {name}' if rec['role'] == 'hidden' else f'a {self.kind_name(rec["kind"], land).lower()} holding {name}'}}

    def watcher(self, watch):
        return _SpawnWatcher(watch)



# ---------------------------------------------------------------------------------------------------------------------
# Shared pieces for the games below: each keeps its object records in parallel arrays and remembers in every object
# slot which record spawned it.

def _shift_out(values: list, index: int, end: int) -> list:
    """A record array with entry `index` taken out: later entries move down one place and the last place gets `end`."""
    return values[:index] + values[index + 1:] + [end]


class _SlotWatcher(Watcher):
    """Watches object slots in the replay. A new spawn is a slot whose record number changes while it is in use.
    Swaps: the edited record's spawn (same record number, same place) must have the chosen object type and graphic.
    Removals: the place was on screen and nothing of the old type spawned there. Subclasses say where things are."""
    every = 1
    SLOTS = range(0)
    TOLERANCE = 8

    def __init__(self, watch):
        self.w = watch
        self.slots = None
        self.spawned = None
        self.in_view = False

    def part(self, ram):
        raise NotImplementedError

    def used(self, ram, s) -> bool:
        raise NotImplementedError

    def number(self, ram, s) -> int:
        raise NotImplementedError

    def place(self, ram, s):
        raise NotImplementedError

    def camera(self, ram):
        raise NotImplementedError

    def looks(self, ram, s) -> dict:
        raise NotImplementedError

    def see(self, ram, frame, run):
        w = self.w
        if self.part(ram) != w['part']:
            self.slots = None
            return False
        slots = [(self.used(ram, s), self.number(ram, s)) for s in self.SLOTS]
        old, self.slots = self.slots, slots
        cam = self.camera(ram)
        if cam[0] - 16 <= w['x'] <= cam[0] + 272 and cam[1] - 16 <= w['y'] <= cam[1] + 256:
            self.in_view = True
        if old is None:
            return False
        for n, s in enumerate(self.SLOTS):
            if not slots[n][0] or slots[n] == old[n]:
                continue
            x, y = self.place(ram, s)
            if abs(x - w['x']) > self.TOLERANCE or abs(y - w['y']) > self.TOLERANCE:
                continue
            if not w['removing'] and slots[n][1] != w['index']:
                continue
            self.spawned = self.looks(ram, s)
            if not w['removing']:
                return True
        return False

    def result(self):
        w, got = self.w, self.spawned
        if w['removing']:
            if got is not None and got['type'] in w['old_types']:
                return {'state': 'bad', 'text': 'Played from the start, the object still appears there.'}
            if self.in_view:
                return {'state': 'good', 'text': 'Played from the start, nothing appears there any more.'}
            return super().result()
        if got is None:
            return super().result()
        want = w['want']
        if got['type'] in want['types'] and got['gfx'] in want['gfx']:
            return {'state': 'good', 'text': f'Played from the start, the game now puts {w["name"]} there.'}
        return {'state': 'bad', 'text': f'Played from the start, the game put something else there (object type {got["type"]:#04x}, '
                                        f'graphic {got["gfx"]:#04x}), not what was chosen.'}


class _RecordProfile(Profile):
    """Common adapter for the decoders below. The decoder gives records(level) (each with 'index', 'kind', 'role' and
    'item'), place(record) -> (x, y), role(kind), kind_name(kind), item_name(item), content_choices(kind, index),
    enemy_choices(level), swap_writes, remove_writes and wanted(kind) -> {'types', 'gfx'} (how a spawn of that kind
    looks in the slots). Roles: 'enemy' (swap and remove), 'covered' (an item under a box), 'container' (an object
    holding an item), 'hidden' (a hidden item) and 'fixed' (left as it is)."""
    KEY = 'level'
    LEVELS = 0
    HIDDEN_NOTE = ''
    COVERED_NOTE = ''

    def part_name(self, part):
        return f'Level {int(part[self.KEY])}'

    def objects(self, part):
        level = int(part[self.KEY])
        out = []
        for r in self.records(level):
            x, y = self.place(r)
            row = {'id': f'object:{r["index"]}', 'type': r['kind'], 'x': x, 'y': y, 'name': self.kind_name(r['kind']),
                   'remove': 'Remove this object'}
            if r['role'] in ('covered', 'hidden', 'container'):
                choices = self.content_choices(r['kind'], r['index'])
                label = {'hidden': 'Gives', 'container': 'Holds'}.get(r['role'], 'Item')
                row.update(style='secret' if r['role'] == 'hidden' else 'item',
                           fields=[{'key': 'kind', 'label': label, 'value': r['kind'], 'choices': choices}] if len(choices) > 1 else [])
                note = {'hidden': self.HIDDEN_NOTE, 'covered': self.COVERED_NOTE}.get(r['role'])
                if note:
                    row['note'] = note
                if r['role'] == 'container':
                    row['detail'] = 'holds ' + self.item_name(r['item']).lower()
            elif r['role'] == 'enemy':
                row.update(style='enemy', fields=[{'key': 'kind', 'label': 'Swap for', 'value': r['kind'], 'choices': f'{self.KEY}{level}'}])
            else:
                row.update(style='enemy', fields=[], remove=None,
                           note='ROMancer does not know what this object does yet, so it stays as it is.')
            out.append(row)
        return out

    def choices(self):
        return {f'{self.KEY}{level}': self.enemy_choices(level) for level in range(self.LEVELS)}

    def find_record(self, part, object_id):
        level = int(part[self.KEY])
        kind_of, _, number = object_id.partition(':')
        if kind_of != 'object' or not number.isdigit():
            raise ValueError('ROMancer cannot change that yet.')
        rec = next((r for r in self.records(level) if r['index'] == int(number)), None)
        if rec is None:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        if rec['role'] == 'fixed':
            raise ValueError('ROMancer cannot change that object yet.')
        return level, rec

    def edit(self, part, object_id, values, remove=False):
        level, rec = self.find_record(part, object_id)
        x, y = self.place(rec)
        watch = {'part': {self.KEY: level}, 'index': rec['index'], 'x': x, 'y': y,
                 'old_types': self.wanted(rec['kind'])['types']}
        if remove:
            return {'writes': self.remove_writes(level, rec['index']), 'title': f'Remove {self.kind_name(rec["kind"]).lower()}',
                    'watch': {**watch, 'removing': True}}
        kind = int(values.get('kind'))
        if rec['role'] == 'enemy':
            allowed = [c['value'] for c in self.enemy_choices(level)]
        else:
            allowed = [c['value'] for c in self.content_choices(rec['kind'], rec['index'])]
        if kind not in allowed:
            raise ValueError('That choice is not one of the game’s own.')
        if rec['role'] == 'enemy':
            name = self.kind_name(kind)
            title, said = f'Object here: {name}', name
        else:
            name = self.item_name(self.role(kind)['item']).lower()
            if rec['role'] == 'hidden':
                title, said = f'Hidden item gives: {name}', f'a hidden {name}'
            elif rec['role'] == 'container':
                title, said = f'{self.kind_name(rec["kind"])} holds: {name}', f'{self.kind_name(rec["kind"]).lower()} holding {name}'
            else:
                title, said = f'Item here: {name}', name
        return {'writes': self.swap_writes(level, rec['index'], kind), 'title': title,
                'watch': {**watch, 'removing': False, 'want': self.wanted(kind), 'name': said}}


# ---------------------------------------------------------------------------------------------------------------------
# Chip 'n Dale - Rescue Rangers (USA)

class ChipDale:
    """Chip 'n Dale - Rescue Rangers (USA) decoder (MMC1, 8 banks of 16 KB, bank 7 fixed at $C000).

    * Level $31 (0-10). A level is made of sections ($FB, 240 pixels high, 0 at the top) that scroll sideways: camera
      x $FD:$FC, camera y $FA inside section $FB. $97 is $28 while a level is played.
    * Objects: bank 4 $8000 copies six pointers per level from $8193 (tables of 15 lows then 15 highs): x high, x low,
      section, y, kind and a per-section table. The five record arrays are equally long and end with a $FF record.
    * Spawn (bank 4 $80FA): a free slot ($0F down to $06) gets $0590 record number, $04F0/$0500 x, $0510 y, $0520
      section, then the kind's 4 bytes at bank 4 $9028 + kind * 4: $0400 flags, $04E0 object type, $0420 graphic,
      $0570 parameter. Kind $53 (the red ball in a boss room) always goes to slot 2.
    * Object type $3B: an item waiting under a box (bank 6 $8BC8); it turns into item type $3C when nothing covers it,
      and its graphic is the item. Types $55-$5E with graphic $83: a hidden item that appears when Chip or Dale touches
      it (bank 6 $880F) and turns into graphic $8B55[type].
    """
    name = "Chip 'n Dale Rescue Rangers"
    sha256 = '8d5e3d9ce20fa0a61b23e93dbc975606803f2d5e7a264514b02b96f832a63181'
    BANK4, BANK6 = 0x10000, 0x18000
    LEVELS = 11
    POINTERS = 0x8193
    KINDS = 0x9028
    KIND_COUNT = 0x54
    REVEALS = 0x8B55
    SCREEN_H = 240
    PLAYING = 0x28
    # items by graphic, from what picking one up changed: the F, S and P counters of the status screen ($05AE, $05B2,
    # $05B6) and the hearts (sprites $0208, $020C, $0210)
    ITEMS = {0x2D: 'Flower', 0x2E: 'Star', 0x2F: 'Extra life', 0x30: 'Acorn (one heart)', 0x31: 'Acorn (all hearts)'}
    COVERED_TYPE = 0x3B
    HIDDEN_TYPES = range(0x55, 0x5F)
    HIDDEN_CHOICES = (0x0A, 0x12, 0x13)          # hidden star, extra life, acorn (all hearts)
    # named from what the game draws when one is spawned in its own level (trace/v15_profiles/capcom_disney/shots/cd1)
    NAMES = {0x00: 'Robot bulldog', 0x01: 'Robot mouse', 0x03: 'Caterpillar', 0x1D: 'Ape', 0x1F: 'Kangaroo',
             0x26: 'Lizard', 0x29: 'Crab', 0x2A: 'Pelican', 0x2C: 'Spark', 0x2D: 'Spark', 0x2E: 'Spark',
             0x30: 'Rolling ball', 0x33: 'Rolling ball', 0x34: 'Rolling ball', 0x3C: 'Rolling ball',
             0x09: 'Apple', 0x53: 'Red ball', 0x14: 'Hidden Zipper', 0x15: 'Hidden Zipper'}
    FIRST_BOSS_KIND = 0x40        # kinds $40-$53: each level's boss, its parts and the boss room's red ball

    def __init__(self, rom: bytes):
        self.rom = rom

    def o4(self, address: int) -> int:
        return HEADER_NES + self.BANK4 + (address - 0x8000)

    def b4(self, address: int) -> int:
        return self.rom[self.o4(address)]

    def b6(self, address: int) -> int:
        return self.rom[HEADER_NES + self.BANK6 + (address - 0x8000)]

    def tables(self, level: int) -> dict:
        names = ('xhi', 'xlo', 'section', 'y', 'kind', 'scroll')
        return {n: self.b4(self.POINTERS + 30 * k + level) | self.b4(self.POINTERS + 30 * k + 15 + level) << 8
                for k, n in enumerate(names)}

    def count(self, level: int) -> int:
        t = self.tables(level)
        return t['xlo'] - t['xhi']

    def kind(self, kind: int) -> dict:
        a = self.KINDS + kind * 4
        flags, otype, gfx, param = (self.b4(a + i) for i in range(4))
        return {'kind': kind, 'flags': flags, 'type': otype, 'gfx': gfx, 'param': param}

    def records(self, level: int) -> list:
        if not 0 <= level < self.LEVELS:
            return []
        t, out = self.tables(level), []
        for i in range(self.count(level)):
            section = self.b4(t['section'] + i)
            if section == 0xFF:
                continue
            k = self.b4(t['kind'] + i)
            out.append({'index': i, 'section': section, 'x': self.b4(t['xhi'] + i) << 8 | self.b4(t['xlo'] + i),
                        'y': self.b4(t['y'] + i), 'kind': k, **self.role(k)})
        return out

    def place(self, rec):
        return rec['x'], rec['section'] * self.SCREEN_H + rec['y']

    def role(self, kind: int) -> dict:
        if kind >= self.KIND_COUNT:
            return {'role': 'fixed', 'item': None}
        k = self.kind(kind)
        if k['type'] == self.COVERED_TYPE:
            return {'role': 'covered', 'item': k['gfx']}
        if k['type'] in self.HIDDEN_TYPES and k['gfx'] == 0x83:
            return {'role': 'hidden', 'item': self.b6(self.REVEALS + k['type'])}
        if k['flags'] & 0x40 and kind < self.FIRST_BOSS_KIND:
            return {'role': 'enemy', 'item': None}
        return {'role': 'fixed', 'item': None}

    def item_name(self, item) -> str:
        return self.ITEMS.get(item, f'Item {item:#04x}')

    def kind_name(self, kind: int) -> str:
        if kind in self.NAMES:
            return self.NAMES[kind]
        role = self.role(kind)
        if role['role'] == 'covered':
            return self.item_name(role['item'])
        if role['role'] == 'hidden':
            return 'Hidden ' + self.item_name(role['item']).lower() if role['item'] in self.ITEMS else f'Hidden object {kind:#04x}'
        if role['role'] == 'enemy':
            return f'Enemy {kind:#04x}'
        return f'Object {kind:#04x}'

    def content_choices(self, kind: int, index: int) -> list:
        """Kinds of the same sort (an item under a box, or a hidden item) with another known item. The extra life is
        not offered for record 0: the game remembers taken extra lives by record number in $E8-$EB, where 0 is an
        empty place, so record 0 would never give it."""
        role = self.role(kind)
        if role['role'] == 'covered':
            pool = [k for k in range(self.KIND_COUNT) if self.role(k)['role'] == 'covered']
        elif role['role'] == 'hidden':
            pool = list(self.HIDDEN_CHOICES)
        else:
            return []
        out, seen = [], set()
        for other in [kind] + pool:
            item = self.role(other)['item']
            if item in seen or (other != kind and (item not in self.ITEMS or (item == 0x2F and index == 0))):
                continue
            seen.add(item)
            out.append({'value': other, 'name': self.item_name(item) if item in self.ITEMS else self.kind_name(other)})
        return sorted(out, key=lambda c: c['value'])

    def enemy_choices(self, level: int) -> list:
        """Enemies this level uses (their pictures are loaded there), one kind per object type. Enemies that start
        hidden (flag $08) are not offered: they wait for something particular to their place."""
        out, seen = [], set()
        for kind in sorted({r['kind'] for r in self.records(level)}):
            k = self.kind(kind)
            if self.role(kind)['role'] != 'enemy' or k['type'] in seen or k['flags'] & 0x08:
                continue
            seen.add(k['type'])
            out.append({'value': kind, 'name': self.kind_name(kind)})
        return out

    def wanted(self, kind):
        k = self.kind(kind)
        if k['type'] == self.COVERED_TYPE:          # becomes item type $3C at once when nothing covers it
            return {'types': [k['type'], k['type'] + 1], 'gfx': [k['gfx']]}
        return {'types': [k['type']], 'gfx': [k['gfx']]}

    def swap_writes(self, level: int, index: int, kind: int) -> list:
        offset = self.o4(self.tables(level)['kind'] + index)
        return [(offset, self.rom[offset], kind)] if self.rom[offset] != kind else []

    def remove_writes(self, level: int, index: int) -> list:
        """Take record `index` out of the level: later records move down one place in all five arrays and the last
        place becomes another $FF record."""
        t, n = self.tables(level), self.count(level)
        if not 0 <= index < n - 1 or self.b4(t['section'] + index) == 0xFF:
            raise ValueError('That is not one of this level’s objects.')
        writes = {}
        for name in ('xhi', 'xlo', 'section', 'y', 'kind'):
            values = [self.b4(t[name] + i) for i in range(n)]
            for i, v in enumerate(_shift_out(values, index, 0xFF)):
                writes[self.o4(t[name] + i)] = v
        return [(o, self.rom[o], v) for o, v in sorted(writes.items()) if self.rom[o] != v]


class _ChipDaleWatcher(_SlotWatcher):
    SLOTS = range(2, 16)

    def part(self, ram):
        return {'level': ram[0x31]} if ram[0x97] == ChipDale.PLAYING else None

    def used(self, ram, s):
        return bool(ram[0x4D0 + s] & 0x80)

    def number(self, ram, s):
        return ram[0x590 + s]

    def place(self, ram, s):
        return ram[0x500 + s] << 8 | ram[0x4F0 + s], ram[0x520 + s] * ChipDale.SCREEN_H + ram[0x510 + s]

    def camera(self, ram):
        return ram[0xFD] << 8 | ram[0xFC], ram[0xFB] * ChipDale.SCREEN_H + ram[0xFA]

    def looks(self, ram, s):
        return {'type': ram[0x4E0 + s], 'gfx': ram[0x420 + s]}


class ChipDaleProfile(ChipDale, _RecordProfile):
    """Chip 'n Dale - Rescue Rangers on the common interface. A part is a level ($31); x is the level's x and y is
    section * 240 + y."""
    sha256s = (ChipDale.sha256,)
    HIDDEN_NOTE = 'Hidden until Chip or Dale touches the spot.'
    COVERED_NOTE = 'Waits under a box until the box is lifted (it shows at once when nothing covers it).'

    def where(self, ram):
        """None outside play: $97 is $28 while a level is played and the object pointer $74/$75 is the level's own."""
        level = ram[0x31]
        if level >= self.LEVELS or ram[0x97] != self.PLAYING or ram[0x74] | ram[0x75] << 8 != self.tables(level)['xhi']:
            return None
        return {'part': {'level': level}, 'x': ram[0xFD] << 8 | ram[0xFC], 'y': ram[0xFB] * self.SCREEN_H + ram[0xFA]}

    def watcher(self, watch):
        return _ChipDaleWatcher(watch)


PROFILES = [DuckTalesProfile, ChipDaleProfile]
