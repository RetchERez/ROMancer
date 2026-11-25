"""Capcom's later Disney NES games: DuckTales 2, Darkwing Duck and Chip 'n Dale - Rescue Rangers 2. Each game has its
own class, decoded from its own ROM and proven on its own (research/capcom_disney2-level-profile.md). The shared
watcher and adapter pieces come from capcom_disney (DuckTales and Chip 'n Dale - Rescue Rangers).
"""
from __future__ import annotations

from . import Profile, Watcher
from .capcom_disney import HEADER_NES, _RecordProfile, _shift_out, _SlotWatcher


# =====================================================================================================================
# DuckTales 2 (USA)
# (section: DuckTales 2)

class DuckTales2:
    """DuckTales 2 (USA) decoder (UNROM, 8 banks of 16 KB, bank 7 fixed at $C000).

    * Stage $C8 (0 Niagara, 1 Bermuda, 2 Egypt, 3 Mu, 4 Scotland; 5 and 6 are the later stages). A stage is a grid of
      6 rows ($1B) of 8 screens. Camera: x $18:$17, y $1B * 240 + $1A. $8A is 1 while a stage is played.
    * Objects (bank 7 $F430, bank 6 mapped): bank 6 $9424 + (stage * 6 + row) * 2 points at the row's list: $FF, the
      row number, then records of 3 bytes (x / 8, y, kind) sorted by x. The list ends at the next $FF (the next
      row's list starts there). Kinds $99 and up are not objects (music and palette changes at a place).
    * Spawn ($F348): a free slot ($03FE,X = 0, X = 0-15) gets kind $03FE, record number $041E, x $04BE:$04AE (also
      $050E:$04FE, where it started), y $04DE (also $051E) and row $04EE. A record whose byte in the row's array at
      $F512/$F518 (one byte per record) is 0 is not spawned again (an opened chest or a taken hidden item).
    * Handlers by kind: bank 5 $8E51 (2 bytes per kind) into bank 6.
    * Kinds $66-$6B: a chest; opened, it gives item $8ACA[kind - $66]. Kinds $6C-$6F: a large chest; it turns into
      item $8B2D[kind - $6C] ($6E and $6F give their prize once: then $2B). Kinds $32-$3B: hidden; when Scrooge walks
      over the place they turn into $89AC[kind - $32] (items) or $89B0[kind - $36] (chests).
    """
    name = 'DuckTales 2'
    sha256 = '1b6b2323ac4c974d75c07d05a625c4bec582411a04e427b0b95e8d7bc3a17c25'
    BANK5, BANK6 = 0x14000, 0x18000
    STAGES = ['Niagara', 'Bermuda', 'Egypt', 'Mu', 'Scotland', 'Stage 6', 'Stage 7']
    ROWS = 6
    LISTS = 0x9424
    SCREEN_H = 240
    HIDDEN_LINES = 8
    FIRST_CONTROL = 0x99
    CHEST_ITEMS, BIG_CHEST_ITEMS = 0x8ACA, 0x8B2D
    HIDDEN_ITEMS, HIDDEN_CHESTS = 0x89AC, 0x89B0
    CHESTS = range(0x66, 0x6C)
    BIG_CHESTS = range(0x6C, 0x70)
    HIDDEN = range(0x32, 0x3C)
    # items: what picking each one up changed (trace/v15_profiles/capcom_disney2/item2_dt2.py, item3_dt2.py): money
    # digits $0303-$0309, hearts $CF ($10 each), lives $CE; and the game's own text for the map piece and the treasure
    ITEMS = {0x2A: 'Red diamond ($50,000)', 0x2B: 'Large diamond ($10,000)', 0x2C: 'Small diamond ($1,000)',
             0x2D: 'Ice cream (one heart)', 0x2E: 'Extra life', 0x2F: 'Piece of the map',
             0x30: 'Hidden treasure ($1,000,000)', 0x31: 'Stage treasure (ends the stage)'}
    OFFERED_ITEMS = (0x2A, 0x2B, 0x2C, 0x2D, 0x2E)
    # enemies: kinds $42-$5C (the pictures of every kind each stage uses, shots/dt2/zoom*.png, show its enemies there)
    FIRST_ENEMY, LAST_ENEMY = 0x42, 0x5C
    # names and what each does, from what the game draws when the record is spawned at its own place (the stage started
    # there: trace/v15_profiles/capcom_disney2/name2_dt2.py, pictures shots/dt2/m<stage>_<kind>.png) or in front of
    # Scrooge at the stage's start (name_dt2.py, shots/dt2/n<stage>_<kind>.png), and its place every frame for 160
    # frames. A kind can look different in another stage, so most names are per stage. Kinds drawn with the wrong
    # pictures in both ways (letters and numbers instead of a sprite) keep their number.
    NAMES = {
        (0, 0x4C): ('Plant', 'Stays rooted in one spot.'),
        (0, 0x4D): ('Bird', 'Flies slowly back and forth near the ground.'),
        (0, 0x4E): ('Frog', 'Hops toward Scrooge.'),
        (0, 0x76): ('Log', 'Floats down the waterfall and comes back at the top.'),
        (1, 0x51): ('Crab', 'Walks back and forth.'),
        (1, 0x53): ('Pink bird', 'Flies across the screen and away.'),
        (1, 0x52): ('Small duck in a hat', 'Jumps toward Scrooge.'),
        (1, 0x73): ('Striped pole', None), (1, 0x74): ('Striped pole', None),
        (1, 0x8D): ('Cannon', None), (1, 0x8E): ('Lever', None), (1, 0x96): ('Hanging ring', None),
        (2, 0x21): ('Hook', None), (2, 0x91): ('Hook', None),
        (2, 0x55): ('Mummy', None),
        (2, 0x7C): ('Arrow block', None), (2, 0x7D): ('Arrow block', None), (2, 0x7E): ('Arrow block', None),
        (2, 0x7F): ('Arrow block', None),
        (2, 0x94): ('Striped pillar', None),
        (2, 0x95): ('Creature in the sand', 'Rises out of the sand and sinks back.'),
        (3, 0x51): ('Crab', 'Walks back and forth.'),
        (3, 0x57): ('Mermaid', 'Hops along the ground toward Scrooge.'),
        (3, 0x72): ('Drum', None), (3, 0x92): ('Striped block', None), (3, 0x94): ('Striped pillar', None),
        (4, 0x4E): ('Frog', 'Hops toward Scrooge.'),
        (4, 0x5B): ('Ghost', 'Swoops down and across toward Scrooge.'),
        (4, 0x82): ('Arrow block', None), (4, 0x84): ('Cart', None),
        (5, 0x51): ('Crab', 'Walks back and forth.'),
        (5, 0x5B): ('Ghost', 'Swoops down and across toward Scrooge.'),
        (5, 0x72): ('Drum', None),
    }
    # the same picture in every stage it was seen in
    HELPERS = {0x3C: ('Huey', 'Stands in one place.'), 0x3D: ('Dewey', 'Stands in one place.'),
               0x3E: ('Louie', 'Stands in one place.'), 0x3F: ('Webby', 'Stands in one place.'),
               0x40: ('Launchpad', 'Stands in one place.'),
               0x41: ('Duck in a red cap', 'Stands in one place.'),
               0x23: ('Invisible object', 'Draws nothing and stays where it is.'),
               0x5E: ('Invisible marker', 'Draws nothing and is gone a few frames after it appears.')}

    def __init__(self, rom: bytes):
        self.rom = rom

    def o5(self, address: int) -> int:
        return HEADER_NES + self.BANK5 + (address - 0x8000)

    def o6(self, address: int) -> int:
        return HEADER_NES + self.BANK6 + (address - 0x8000)

    def b6(self, address: int) -> int:
        return self.rom[self.o6(address)]

    def list_at(self, stage: int, row: int):
        """The row's list address, or None when the row has no list of its own (the header must name the row)."""
        if not 0 <= stage < len(self.STAGES) or not 0 <= row < self.ROWS:
            return None
        x = (stage * self.ROWS + row) * 2
        p = self.b6(self.LISTS + x) | self.b6(self.LISTS + x + 1) << 8
        if not 0x8000 <= p < 0xBFFD or self.b6(p) != 0xFF or self.b6(p + 1) != row:
            return None
        return p

    def row_records(self, stage: int, row: int) -> list:
        """Every record of the row, controls included: [(number, address, x, y, kind)]."""
        p, out = self.list_at(stage, row), []
        if p is None:
            return out
        a = p + 2
        while a < 0xBFFD and self.b6(a) != 0xFF:
            out.append((len(out), a, self.b6(a) * 8, self.b6(a + 1), self.b6(a + 2)))
            a += 3
        return out

    def records(self, stage: int) -> list:
        out = []
        for row in range(self.ROWS):
            for number, a, x, y, kind in self.row_records(stage, row):
                if kind >= self.FIRST_CONTROL:
                    continue
                out.append({'row': row, 'index': number, 'x': x, 'y': y, 'kind': kind, 'kind_byte': self.o6(a + 2),
                            **self.role(kind, stage)})
        return out

    # ---- what a kind is
    def role(self, kind: int, stage: int = 0) -> dict:
        if kind in self.CHESTS:
            return {'role': 'chest', 'item': self.b6(self.CHEST_ITEMS + kind - 0x66)}
        if kind in self.BIG_CHESTS:
            return {'role': 'big chest', 'item': self.b6(self.BIG_CHEST_ITEMS + kind - 0x6C)}
        if kind in self.HIDDEN:
            if kind < 0x36:
                return {'role': 'hidden', 'item': self.b6(self.HIDDEN_ITEMS + kind - 0x32)}
            chest = self.b6(self.HIDDEN_CHESTS + kind - 0x36)
            if chest in self.CHESTS:
                return {'role': 'hidden chest', 'item': self.b6(self.CHEST_ITEMS + chest - 0x66)}
            return {'role': 'fixed', 'item': None}
        if self.FIRST_ENEMY <= kind <= self.LAST_ENEMY:
            return {'role': 'enemy', 'item': None}
        return {'role': 'fixed', 'item': None}

    def item_name(self, item) -> str:
        return self.ITEMS.get(item, f'Item {item:#04x}')

    def kind_name(self, kind: int, stage: int) -> str:
        r = self.role(kind, stage)
        if r['role'] == 'chest':
            return 'Treasure chest'
        if r['role'] == 'big chest':
            return 'Large treasure chest'
        if r['role'] == 'hidden':
            return 'Hidden ' + self.item_name(r['item']).split(' (')[0].lower()
        if r['role'] == 'hidden chest':
            return 'Hidden treasure chest'
        if (stage, kind) in self.NAMES:
            return self.NAMES[(stage, kind)][0]
        if kind in self.HELPERS:
            return self.HELPERS[kind][0]
        if kind in self.HIDDEN:
            return 'Hidden enemy' if self.FIRST_ENEMY <= self.b6(self.HIDDEN_CHESTS + kind - 0x36) <= self.LAST_ENEMY \
                else f'Hidden object {kind:#04x}'
        return f'Enemy {kind:#04x}' if r['role'] == 'enemy' else f'Object {kind:#04x}'

    def kind_does(self, kind: int, stage: int):
        """One short sentence on what the kind does, from watching it in the game, or None."""
        if (stage, kind) in self.NAMES:
            return self.NAMES[(stage, kind)][1]
        if kind in self.HELPERS:
            return self.HELPERS[kind][1]
        if kind in self.HIDDEN and self.kind_name(kind, stage) == 'Hidden enemy':
            return 'Turns into an enemy when Scrooge walks over the spot.'
        return None

    # ---- choices: always kinds from the game's own tables
    def content_choices(self, kind: int, stage: int) -> list:
        """Other kinds of the same container (chest, large chest, hidden item, hidden chest) that give one of the
        items picked up and measured. The large chests with a piece of the map or a hidden treasure ($6E, $6F)
        give their prize once per stage, so they are left as they are."""
        r = self.role(kind, stage)
        if r['role'] == 'chest':
            pool = list(self.CHESTS)
        elif r['role'] == 'big chest':
            pool = [0x6C, 0x6D]
        elif r['role'] in ('hidden', 'hidden chest'):
            pool = [k for k in self.HIDDEN if self.role(k, stage)['role'] == r['role']]
        else:
            return []
        if kind not in pool:
            return []
        out = []
        for other in pool:
            item = self.role(other, stage)['item']
            if item in self.OFFERED_ITEMS:
                out.append({'value': other, 'name': self.item_name(item)})
        return out if any(c['value'] == kind for c in out) else []

    def enemy_choices(self, stage: int) -> list:
        """Enemies this stage uses (each stage loads its own sprite pictures), one kind per handler."""
        out, seen = [], set()
        for kind in sorted({r['kind'] for r in self.records(stage)}):
            if self.role(kind, stage)['role'] != 'enemy':
                continue
            handler = self.rom[self.o5(0x8E51 + 2 * kind)] | self.rom[self.o5(0x8E52 + 2 * kind)] << 8
            if handler in seen:
                continue
            seen.add(handler)
            out.append({'value': kind, 'name': self.kind_name(kind, stage)})
        return out

    # ---- writes
    def find_record(self, stage: int, row: int, index: int):
        for number, a, x, y, kind in self.row_records(stage, row):
            if number == index:
                return a
        return None

    def swap_writes(self, stage: int, row: int, index: int, kind: int) -> list:
        a = self.find_record(stage, row, index)
        offset = self.o6(a + 2)
        return [(offset, self.rom[offset], kind)] if self.rom[offset] != kind else []

    def remove_writes(self, stage: int, row: int, index: int) -> list:
        """Take record `index` out of the row: later records move down 3 bytes and the last 3 bytes become $FF, so
        the list ends one record earlier and the next row's list (which starts with $FF) stays where it is."""
        recs = self.row_records(stage, row)
        if not 0 <= index < len(recs) or recs[index][4] >= self.FIRST_CONTROL:
            raise ValueError('That is not one of this stage’s objects.')
        start, end = recs[index][1], recs[-1][1] + 3
        old = [self.b6(a) for a in range(start, end)]
        new = old[3:] + [0xFF, 0xFF, 0xFF]
        return [(self.o6(start + i), o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]


class _DuckTales2Watcher(Watcher):
    """Watches the 16 object slots in the replay. A spawn is a slot whose record number $041E or kind $03FE changes
    while its start place ($050E:$04FE, $051E) and row $04EE are the edited record's. A swap is good when the game
    spawned the chosen kind there; a removal is good when the place was on screen and nothing of the old kind
    spawned there."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.slots = None
        self.spawned = None
        self.in_view = False

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x8A] != 1 or ram[0xC8] != w['stage']:
            self.slots = None
            return False
        if ram[0x1B] == w['row']:
            camera = ram[0x18] << 8 | ram[0x17]
            if camera - 16 <= w['x'] <= camera + 272:
                self.in_view = True
        slots = [(ram[0x3FE + s], ram[0x41E + s]) for s in range(16)]
        old, self.slots = self.slots, slots
        if old is None:
            # the stage spawns the objects of its first screen before $8A turns 1, so on the first frame of play
            # every object already in a slot counts as just spawned
            old = [(0, 0)] * 16
        for s in range(16):
            if not slots[s][0] or slots[s] == old[s] or slots[s][1] != w['index']:
                continue
            if (ram[0x4EE + s], ram[0x50E + s] << 8 | ram[0x4FE + s], ram[0x51E + s]) != (w['row'], w['x'], w['y']):
                continue
            if self.spawned is None or not w['removing']:
                self.spawned = {'kind': slots[s][0]}
            if not w['removing']:
                return True
        return False

    def result(self):
        w, got = self.w, self.spawned
        if w['removing']:
            if got is not None and got['kind'] == w['old_kind']:
                return {'state': 'bad', 'text': 'Played from the start, the object still appears there.'}
            if self.in_view:
                return {'state': 'good', 'text': 'Played from the start, nothing appears there any more.'}
            return super().result()
        if got is None:
            return super().result()
        if got['kind'] == w['want']:
            return {'state': 'good', 'text': f'Played from the start, the game now puts {w["name"]} there.'}
        return {'state': 'bad', 'text': f'Played from the start, the game put something else there (kind {got["kind"]:#04x}), '
                                        'not what was chosen.'}


class DuckTales2Profile(DuckTales2, Profile):
    """DuckTales 2 on the common interface. A part is a stage; x is the stage's x and y is row * 240 + y."""
    sha256s = (DuckTales2.sha256,)

    def where(self, ram):
        """None outside play: $8A is 1 while a stage is played (0 on the title, the map, the stage text and pause)."""
        stage, row = ram[0xC8], ram[0x1B]
        if ram[0x8A] != 1 or stage >= len(self.STAGES) or row >= self.ROWS:
            return None
        # the recorded pictures leave out the NES's top 8 lines, so the top of a picture is 8 below the camera
        # (an object's y is the screen line of its bottom: trace/v15_profiles/capcom_disney2/dt2_y2.py)
        return {'part': {'stage': stage}, 'x': ram[0x18] << 8 | ram[0x17],
                'y': row * self.SCREEN_H + ram[0x1A] + self.HIDDEN_LINES}

    def part_name(self, part):
        return self.STAGES[int(part['stage'])]

    def objects(self, part):
        stage = int(part['stage'])
        out = []
        for r in self.records(stage):
            row = {'id': f'object:{r["row"]}:{r["index"]}', 'type': r['kind'], 'x': r['x'],
                   'y': r['row'] * self.SCREEN_H + r['y'], 'name': self.kind_name(r['kind'], stage),
                   'remove': 'Remove this object'}
            does = self.kind_does(r['kind'], stage)
            if does:
                row['does'] = does
            if r['role'] in ('chest', 'big chest', 'hidden', 'hidden chest'):
                choices = self.content_choices(r['kind'], stage)
                hidden = r['role'].startswith('hidden')
                row.update(style='secret' if hidden else 'item',
                           detail=('gives ' if r['role'] == 'hidden' else 'holds ') + self.item_name(r['item']).lower(),
                           fields=[{'key': 'kind', 'label': 'Gives' if r['role'] == 'hidden' else 'Holds',
                                    'value': r['kind'], 'choices': choices}] if len(choices) > 1 else [])
                if hidden:
                    row['note'] = 'Hidden until Scrooge walks over the spot.'
                if r['kind'] in (0x6E, 0x6F):
                    row['remove'] = None
                    row['note'] = 'Its prize counts toward the stage’s secrets, so ROMancer leaves it as it is.'
            elif r['role'] == 'enemy':
                row.update(style='enemy', fields=[{'key': 'kind', 'label': 'Swap for', 'value': r['kind'],
                                                   'choices': f'stage{stage}'}])
            else:
                row.update(style='enemy', fields=[], remove=None,
                           note='ROMancer cannot change this object yet, so it stays as it is.')
            out.append(row)
        return out

    def choices(self):
        return {f'stage{stage}': self.enemy_choices(stage) for stage in range(len(self.STAGES))}

    def edit(self, part, object_id, values, remove=False):
        stage = int(part['stage'])
        kind_of, _, rest = object_id.partition(':')
        row_text, _, index_text = rest.partition(':')
        if kind_of != 'object' or not row_text.isdigit() or not index_text.isdigit():
            raise ValueError('ROMancer cannot change that yet.')
        row, index = int(row_text), int(index_text)
        rec = next((r for r in self.records(stage) if r['row'] == row and r['index'] == index), None)
        if rec is None:
            raise ValueError('That is not part of this stage any more. Reopen the map.')
        if rec['role'] == 'fixed' or rec['kind'] in (0x6E, 0x6F):
            raise ValueError('ROMancer cannot change that object yet.')
        watch = {'stage': stage, 'row': row, 'index': index, 'x': rec['x'], 'y': rec['y'], 'old_kind': rec['kind']}
        name = self.kind_name(rec['kind'], stage)
        if remove:
            return {'writes': self.remove_writes(stage, row, index), 'title': f'Remove {name.lower()}',
                    'watch': {**watch, 'removing': True}}
        kind = int(values.get('kind'))
        if rec['role'] == 'enemy':
            allowed = [c['value'] for c in self.enemy_choices(stage)]
        else:
            allowed = [c['value'] for c in self.content_choices(rec['kind'], stage)]
        if kind not in allowed:
            raise ValueError('That choice is not one of the game’s own.')
        if rec['role'] == 'enemy':
            said = self.kind_name(kind, stage)
            title = f'Object here: {said}'
        else:
            item = self.item_name(self.role(kind, stage)['item']).lower()
            if rec['role'] == 'hidden':
                title, said = f'Hidden item gives: {item}', f'a hidden {item}'
            else:
                title, said = f'{name} holds: {item}', f'{name.lower()} holding {item}'
        return {'writes': self.swap_writes(stage, row, index, kind), 'title': title,
                'watch': {**watch, 'removing': False, 'want': kind, 'name': said}}

    def watcher(self, watch):
        return _DuckTales2Watcher(watch)

# =====================================================================================================================
# Darkwing Duck (USA)
# (section: Darkwing Duck)

class DarkwingDuck:
    """Darkwing Duck (USA) decoder (MMC1, 8 banks of 16 KB, bank 7 fixed at $C000). The object engine is laid out like
    Chip 'n Dale - Rescue Rangers' (same zero page and slot arrays), with its own tables:

    * Level $31 (0-6). A level is made of sections ($FB, 240 pixels high, 0 at the top): camera x $FD:$FC, camera y
      $FA inside section $FB. $2C is $10 while a level is played.
    * Objects: bank 4 $8000 copies five pointers per level from $81F3 (tables of 7 low bytes then 7 high bytes, in
      the order x high, x low, section, y, kind). The five record arrays of a level are equally long (x low pointer
      minus x high pointer) and end with a record whose bytes are all $FF.
    * Spawn (bank 4 $80FC): skips a record whose bit in $0340 is set (an item already taken; bit $81EB[n & 7] of
      $0340 + n / 8) or that is alive in a slot ($0590,X), takes a free slot $0F down to $05 ($04D0 bit 7 clear) and
      writes $0590 record number, $04F0/$0500 x, $0510 y, $0520 section, then the kind's 4 bytes at bank 4 $8AB3 +
      kind * 4: $0400 flags, $04E0 object type, $0420 graphic, $0570 parameter, and $8C57 + kind * 4 to $05A0.
    * Object types $08 and $09 are items, picked up on touch (bank 6 $8837 and $8A1A); the graphic is the item.
      Flag $20 makes the item invisible (kind $1E). Parameter bit $40 marks an object Darkwing's gas shots can hit
      (bank 6 $8032-$80D1); $05A0 is then its hit points.
    """
    name = 'Darkwing Duck'
    sha256 = '1271dce8678ffc261e2c05cc785ae53e29ac1f9ecf6265a4265bed825abb0a00'
    BANK4 = 0x10000
    LEVELS = 7
    POINTERS = 0x81F3
    KINDS = 0x8AB3
    KIND_COUNT = 0x69
    SCREEN_H = 240
    PLAYING = 0x10
    LEVEL_NAMES = {0: 'Level 0: the bridge', 1: 'Level 1: the city', 2: 'Level 2: the sewers'}
    ITEM_TYPES = (0x08, 0x09)
    # items by graphic, from what picking one up changed (trace/v15_profiles/capcom_disney2/dw_pick.py, dw_hp.py,
    # dw_gas.py): the bonus counter $05C4-$05CC, lives $05E6, the heart $05B2-$05B8, gas $60/$61 and the gas kind $54
    # (the status bar shows AG, HG or TG)
    ITEMS = {0x1C: 'Diamond (bonus +1)', 0x1D: 'Bonus item (bonus +5)', 0x1E: 'Extra life',
             0x22: 'Health kit (full heart)', 0x23: 'Health bottle (a quarter heart)',
             0x24: 'Gas canister (+10 gas)', 0x25: 'Small gas canister (+1 gas)',
             0x26: 'AG gas', 0x27: 'HG gas', 0x28: 'TG gas'}
    FIRST_BOSS_KIND = 0x46        # kinds $46-$55 are the bosses and their parts (each level's last records)

    def __init__(self, rom: bytes):
        self.rom = rom

    def o4(self, address: int) -> int:
        return HEADER_NES + self.BANK4 + (address - 0x8000)

    def b4(self, address: int) -> int:
        return self.rom[self.o4(address)]

    def tables(self, level: int) -> dict:
        names = ('xhi', 'xlo', 'section', 'y', 'kind')
        return {n: self.b4(self.POINTERS + 14 * k + level) | self.b4(self.POINTERS + 14 * k + 7 + level) << 8
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
        if k['type'] in self.ITEM_TYPES and k['gfx'] in self.ITEMS:
            return {'role': 'hidden' if k['flags'] & 0x20 else 'covered', 'item': k['gfx']}
        if k['param'] & 0x40 and kind < self.FIRST_BOSS_KIND:
            return {'role': 'enemy', 'item': None}
        return {'role': 'fixed', 'item': None}

    def item_name(self, item) -> str:
        return self.ITEMS.get(item, f'Item {item:#04x}')

    def kind_name(self, kind: int) -> str:
        role = self.role(kind)
        if role['role'] == 'covered':
            return self.item_name(role['item'])
        if role['role'] == 'hidden':
            return 'Hidden ' + self.item_name(role['item']).lower()
        if role['role'] == 'enemy':
            return f'Enemy {kind:#04x}'
        return f'Object {kind:#04x}'

    def content_choices(self, kind: int, index: int) -> list:
        """Visible items: every visible item kind of the game (item pictures are the same in every level; checked
        in levels 0 and 1). The one hidden item kind ($1E) has no other hidden kind to change into."""
        if self.role(kind)['role'] != 'covered':
            return []
        out, seen = [], set()
        for other in range(self.KIND_COUNT):
            r = self.role(other)
            if r['role'] != 'covered' or r['item'] in seen:
                continue
            seen.add(r['item'])
            out.append({'value': other, 'name': self.item_name(r['item'])})
        return out

    def enemy_choices(self, level: int) -> list:
        """Enemies this level uses (their pictures are loaded there), one kind per object type. Kinds that start
        hidden (flag $08) are not offered."""
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


class _DarkwingWatcher(_SlotWatcher):
    """A taken item leaves a short-lived object of another type in its slot at the same place (record number $FF),
    so for a removal the first sighting of the old type is kept and never replaced by a later spawn there."""
    SLOTS = range(5, 16)

    def see(self, ram, frame, run):
        before = self.spawned
        done = super().see(ram, frame, run)
        if self.w['removing'] and before is not None and before['type'] in self.w['old_types']:
            self.spawned = before
        return done

    def part(self, ram):
        return {'level': ram[0x31]} if ram[0x2C] == DarkwingDuck.PLAYING else None

    def used(self, ram, s):
        return bool(ram[0x4D0 + s] & 0x80)

    def number(self, ram, s):
        return ram[0x590 + s]

    def place(self, ram, s):
        return ram[0x500 + s] << 8 | ram[0x4F0 + s], ram[0x520 + s] * DarkwingDuck.SCREEN_H + ram[0x510 + s]

    def camera(self, ram):
        return ram[0xFD] << 8 | ram[0xFC], ram[0xFB] * DarkwingDuck.SCREEN_H + ram[0xFA]

    def looks(self, ram, s):
        return {'type': ram[0x4E0 + s], 'gfx': ram[0x420 + s]}


class DarkwingDuckProfile(DarkwingDuck, _RecordProfile):
    """Darkwing Duck on the common interface. A part is a level ($31); x is the level's x and y is section * 240 + y."""
    sha256s = (DarkwingDuck.sha256,)
    HIDDEN_NOTE = 'The game does not draw it. Darkwing picks it up by walking over the spot.'

    def part_name(self, part):
        level = int(part['level'])
        return self.LEVEL_NAMES.get(level, f'Level {level}')

    def where(self, ram):
        """None outside play: $2C is $10 while a level is played and the object pointer $74/$75 is the level's own."""
        level = ram[0x31]
        if level >= self.LEVELS or ram[0x2C] != self.PLAYING or ram[0x74] | ram[0x75] << 8 != self.tables(level)['xhi']:
            return None
        return {'part': {'level': level}, 'x': ram[0xFD] << 8 | ram[0xFC], 'y': ram[0xFB] * self.SCREEN_H + ram[0xFA]}

    def watcher(self, watch):
        return _DarkwingWatcher(watch)


# =====================================================================================================================
# Chip 'n Dale - Rescue Rangers 2 (USA)
# (section: Chip 'n Dale 2)

class ChipDale2:
    """Chip 'n Dale - Rescue Rangers 2 (USA) decoder (MMC1, 8 banks of 16 KB, bank 7 fixed at $C000).

    * A level ($72, 0-8) is a list of steps: bank 7 $DA46 + $DAAC[level], 2 bytes each, step $73. A step below $8000
      is a scene; otherwise it points at a 25-byte area record in bank 2 (loaded by bank 7 $D903). Bytes 15-16 of the
      area record are its object list in bank 3 ($79/$7A while it is played); bytes 13-14 are its box list ($77/$78).
    * Object list: records of 3 bytes, ending with $FF: column (bit 7 set for a record met while the area scrolls up or
      down), row and kind. The list is read in order as new columns or rows come into view (bank 7 $CBD5 and $CCEF);
      each record is spawned once, by bank 3 $A2EA, which leaves the record's column, row and kind in $95, $96, $97.
      x = column * 16; row r is screen r / 16 (240 pixels each) and y (r % 16) * 16 inside it.
    * A spawned object takes a free slot of 12 ($02F0 type, low nibble 1, 9, $0A or 6 by kind range; screen position
      $0320:$0314, $0308:$02FC) and runs a script ($0284/$0290, from bank 3 $A363 + kind * 2).
    * Camera: x $AE:$AC, y screen $B2 and $B0 inside it. $40 is 4 while an area is played.
    * Some areas start part way into another area's list (the same place, entered again after a scene), so lists
      can share their tail.
    """
    name = "Chip 'n Dale Rescue Rangers 2"
    sha256 = 'dff668a7885369bb6cbdacde8bfcbdfe8dbba26dd33bad52cd5cabefbdc86fdc'
    BANK2, BANK3, BANK7 = 0x8000, 0xC000, 0x1C000
    LEVELS = 9
    STEPS, STEP_OFFSETS = 0xDA46, 0xDAAC
    SCRIPTS = 0xA363
    SCREEN_H = 240
    PLAYING = 4
    FIRST_ENEMY, LAST_ENEMY = 0x24, 0x3E       # kinds $24-$3E: object type 6, the level enemies; $40-$46 are bosses
    # named from what the game draws when one is spawned in its own level (trace/v15_profiles/capcom_disney2/shots/cd2)
    NAMES = {0x25: 'Rat with a fork', 0x27: 'Monkey', 0x39: 'Hedgehog', 0x3D: 'Fly', 0x1F: 'Star',
             0x1C: 'Big box', 0x1D: 'Big box', 0x1E: 'Big box', 0x21: 'Area exit'}

    def __init__(self, rom: bytes):
        self.rom = rom

    def b(self, base: int, address: int) -> int:
        return self.rom[HEADER_NES + base + (address - (0xC000 if base == self.BANK7 else 0x8000))]

    def o3(self, address: int) -> int:
        return HEADER_NES + self.BANK3 + (address - 0x8000)

    def steps(self, level: int) -> list:
        start = self.b(self.BANK7, self.STEP_OFFSETS + level)
        end = self.b(self.BANK7, self.STEP_OFFSETS + level + 1) if level + 1 < self.LEVELS else self.STEP_OFFSETS - self.STEPS
        return [self.b(self.BANK7, self.STEPS + o) | self.b(self.BANK7, self.STEPS + o + 1) << 8 for o in range(start, end, 2)]

    def list_start(self, area: int) -> int:
        return self.b(self.BANK2, area + 15) | self.b(self.BANK2, area + 16) << 8

    def list_end(self, start: int) -> int:
        """Address of the list's $FF."""
        p = start
        while self.b(self.BANK3, p) != 0xFF:
            p += 3
        return p

    def parts(self, level: int) -> list:
        """The level's places as [{'area': step, 'start', 'end'}]: one per object list; an area whose list is the tail of
        another area's list is the same place and is not listed again."""
        if not 0 <= level < self.LEVELS:
            return []
        lists = []
        for step, area in enumerate(self.steps(level)):
            if area < 0x8000:
                continue
            start = self.list_start(area)
            lists.append((step, start, self.list_end(start)))
        out = []
        for step, start, end in lists:
            if any(s < start <= e and e == end for _, s, e in lists) or any(o['start'] == start for o in out):
                continue
            out.append({'area': step, 'start': start, 'end': end})
        return out

    def part_list(self, level: int, area: int):
        return next((p for p in self.parts(level) if p['area'] == area), None)

    def all_starts(self) -> set:
        return {self.list_start(a) for level in range(self.LEVELS) for a in self.steps(level) if a >= 0x8000}

    def records(self, level: int, area: int) -> list:
        p = self.part_list(level, area)
        if p is None:
            return []
        out = []
        for i, a in enumerate(range(p['start'], p['end'], 3)):
            c, row, kind = (self.b(self.BANK3, a + n) for n in range(3))
            out.append({'index': i, 'address': a, 'col': c & 0x7F, 'vertical': bool(c & 0x80), 'row': row, 'kind': kind,
                        'role': self.role(kind)})
        return out

    @staticmethod
    def place(rec) -> tuple:
        return rec['col'] * 16, (rec['row'] >> 4) * 240 + (rec['row'] & 15) * 16

    def role(self, kind: int) -> str:
        return 'enemy' if self.FIRST_ENEMY <= kind <= self.LAST_ENEMY else 'fixed'

    @staticmethod
    def type_of(kind: int) -> int:
        """Object type nibble the spawn gives a kind (bank 3 $A34A-$A35E)."""
        return 1 if kind < 0x07 else 9 if kind < 0x19 else 0x0A if kind < 0x24 else 6

    def kind_name(self, kind: int) -> str:
        if kind in self.NAMES:
            return self.NAMES[kind]
        return f'Enemy {kind:#04x}' if self.role(kind) == 'enemy' else f'Object {kind:#04x}'

    def enemy_choices(self, level: int, area: int) -> list:
        """Enemies this place uses (their pictures are loaded there)."""
        kinds = sorted({r['kind'] for r in self.records(level, area) if r['role'] == 'enemy'})
        return [{'value': k, 'name': self.kind_name(k)} for k in kinds]

    def swap_writes(self, rec, kind: int) -> list:
        o = self.o3(rec['address'] + 2)
        return [(o, self.rom[o], kind)] if self.rom[o] != kind else []

    def removable(self, level: int, area: int, rec) -> bool:
        """A record can be taken out only when no other area's list starts after it in the same list (moving the
        later records down would move that start)."""
        end = self.part_list(level, area)['end']
        return not any(rec['address'] < s <= end for s in self.all_starts())

    def remove_writes(self, level: int, area: int, rec) -> list:
        """Take the record out: the later records and the $FF move down 3 bytes, the freed last 3 bytes become $FF."""
        if not self.removable(level, area, rec):
            raise ValueError('Another part of the level starts later in this list, so this object cannot be taken out.')
        end = self.part_list(level, area)['end']
        old = [self.b(self.BANK3, a) for a in range(rec['address'], end + 1)]
        new = old[3:] + [0xFF, 0xFF, 0xFF]
        return [(self.o3(rec['address'] + i), o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]


class _ChipDale2Watcher(Watcher):
    """Watches the replay for the edited record's spawn. The spawn leaves the record's column, row and kind in $95, $96
    and $97, so a swap is good when the game read the chosen kind there. A new object slot appearing at the record's
    place on screen also counts as a spawn there (when another record of the same column is read in the same frame and
    overwrites $95-$97). A removal is good when the place was on screen and nothing of the old kind spawned there."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.kind = None
        self.slot_type = None
        self.in_view = False
        self.slots = None

    def see(self, ram, frame, run):
        w = self.w
        ptr = ram[0x79] | ram[0x7A] << 8
        if ram[0x40] != ChipDale2.PLAYING or ram[0x72] != w['level'] or not w['start'] <= ptr <= w['end']:
            self.slots = None
            return False
        cx, cy = ram[0xAE] << 8 | ram[0xAC], ram[0xB2] * ChipDale2.SCREEN_H + ram[0xB0]
        if cx - 16 <= w['x'] <= cx + 272 and cy - 16 <= w['y'] <= cy + 256:
            self.in_view = True
        if (ram[0x95], ram[0x96]) == (w['col'], w['row']):
            self.kind = ram[0x97]
            if not w['removing']:
                return True
        slots = [ram[0x2F0 + s] for s in range(12)]
        old, self.slots = self.slots, slots
        if old is not None:
            for s in range(3, 12):
                if slots[s] and not old[s]:
                    x = (ram[0x320 + s] - 256 if ram[0x320 + s] >= 128 else ram[0x320 + s]) * 256 + ram[0x314 + s]
                    y = (ram[0x308 + s] - 256 if ram[0x308 + s] >= 128 else ram[0x308 + s]) * ChipDale2.SCREEN_H + ram[0x2FC + s]
                    if abs(x + cx - w['x']) <= 4 and abs(y + cy - w['y']) <= 4:
                        self.slot_type = slots[s] & 0x0F
        return False

    def result(self):
        w = self.w
        if w['removing']:
            if self.kind == w['old_kind'] or self.slot_type == ChipDale2.type_of(w['old_kind']):
                return {'state': 'bad', 'text': 'Played from the start, the object still appears there.'}
            if self.in_view:
                return {'state': 'good', 'text': 'Played from the start, nothing appears there any more.'}
            return super().result()
        if self.kind is not None:
            if self.kind == w['want']:
                return {'state': 'good', 'text': f'Played from the start, the game now puts {w["name"]} there.'}
            return {'state': 'bad', 'text': f'Played from the start, the game put object {self.kind:#04x} there, not what was chosen.'}
        return super().result()


class ChipDale2Profile(ChipDale2, Profile):
    """Chip 'n Dale - Rescue Rangers 2 on the common interface. A part is a level ($72) and the step of the area whose
    object list it uses; x and y are the area's pixels (y counts 240 pixels a screen)."""
    sha256s = (ChipDale2.sha256,)

    def where(self, ram):
        """None outside play: $40 is 4 while an area is played; the area is the one whose object list holds $79/$7A."""
        level = ram[0x72]
        if ram[0x40] != self.PLAYING or level >= self.LEVELS:
            return None
        ptr = ram[0x79] | ram[0x7A] << 8
        part = next((p for p in self.parts(level) if p['start'] <= ptr <= p['end']), None)
        if part is None:
            return None
        return {'part': {'level': level, 'area': part['area']}, 'x': ram[0xAE] << 8 | ram[0xAC],
                'y': ram[0xB2] * self.SCREEN_H + ram[0xB0]}

    def part_name(self, part):
        return f'Level {int(part["level"])}, area {int(part["area"])}'

    def objects(self, part):
        level, area = int(part['level']), int(part['area'])
        out = []
        for r in self.records(level, area):
            x, y = self.place(r)
            row = {'id': f'object:{r["index"]}', 'type': r['kind'], 'x': x + 8, 'y': y + 16, 'name': self.kind_name(r['kind']),
                   'style': 'enemy'}
            if r['role'] == 'enemy':
                row.update(fields=[{'key': 'kind', 'label': 'Swap for', 'value': r['kind'], 'choices': f'level{level}area{area}'}],
                           remove='Remove this object' if self.removable(level, area, r) else None)
            else:
                row.update(fields=[], remove=None, note='ROMancer does not know what this object does yet, so it stays as it is.')
            out.append(row)
        return out

    def choices(self):
        return {f'level{level}area{p["area"]}': self.enemy_choices(level, p['area'])
                for level in range(self.LEVELS) for p in self.parts(level)}

    def edit(self, part, object_id, values, remove=False):
        level, area = int(part['level']), int(part['area'])
        kind_of, _, number = object_id.partition(':')
        if kind_of != 'object' or not number.isdigit():
            raise ValueError('ROMancer cannot change that yet.')
        rec = next((r for r in self.records(level, area) if r['index'] == int(number)), None)
        if rec is None:
            raise ValueError('That is not part of this level any more. Reopen the map.')
        if rec['role'] != 'enemy':
            raise ValueError('ROMancer cannot change that object yet.')
        p = self.part_list(level, area)
        x, y = self.place(rec)
        watch = {'level': level, 'start': p['start'], 'end': p['end'], 'col': rec['col'], 'row': rec['row'], 'x': x, 'y': y,
                 'old_kind': rec['kind']}
        if remove:
            return {'writes': self.remove_writes(level, area, rec), 'title': f'Remove {self.kind_name(rec["kind"]).lower()}',
                    'watch': {**watch, 'removing': True}}
        kind = int(values.get('kind'))
        if kind not in [c['value'] for c in self.enemy_choices(level, area)]:
            raise ValueError('That choice is not one of the game’s own.')
        name = self.kind_name(kind)
        return {'writes': self.swap_writes(rec, kind), 'title': f'Object here: {name}',
                'watch': {**watch, 'removing': False, 'want': kind, 'name': name}}

    def watcher(self, watch):
        return _ChipDale2Watcher(watch)


# =====================================================================================================================

# DuckTales2Profile is decoded but its edits are not proven yet (research notes), so it is not registered
PROFILES = [DuckTales2Profile, DarkwingDuckProfile, ChipDale2Profile]
