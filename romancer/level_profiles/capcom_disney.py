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


PROFILES = [DuckTalesProfile]
