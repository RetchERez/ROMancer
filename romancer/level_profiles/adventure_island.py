"""Level profile for Adventure Island (NES, USA).

Everything here was read from the game's 6502 code and checked by replaying the game with a changed ROM (research notes:
research/adventure_island-level-profile.md, scratch scripts in trace/v15_profiles/adventure_island/). The cartridge has
32 KB of program ROM at CPU $8000-$FFFF (no program banks), so a CPU address A is at file offset 16 + A - $8000.

* Levels: 8 areas of 4 rounds, level number $51 = area ($37) * 4 + round ($38). A cloud bonus ($49 = 1 to 9) uses its
  own object lists ($F1D8 + ($49 - 1) * 6) over the level's layout.
* Layout ($BB48): map number $D94B[level]; chunks of 128 pixels at word $D99C + map * 2, 3 bytes each ($BD75): byte 0
  bits 0-1 the vertical scroll while the camera is in that chunk (1 up, 2 down, one pixel each 4 pixels across), byte 1
  bits 2-4 the change of ground height from the chunk before ($BF43: 0, -32, +32, -64, +64, -8, -96, +96), byte 2 low
  four bits the ground's shape (0 flat, 2 and 3 slopes, 4 to 6 a step halfway, 7 and up a gap; $C1EA) and high four
  bits how much higher fruit floats there. The ground height of chunk 0 is $60 + 8 * (low four bits of the first byte at
  word $D9B4 + map * 2). Chunk $3B is under the camera; RAM $0506-$050A hold the screen heights of chunks $3B-3 to $3B+1.
* Objects ($8C5A, $8D74): three bit-packed lists a level (word $F118 + level * 6 + list * 2; a zero word is no list).
  A list starts with 10 bits, the place / 8; then each entry is 6 bits of type, 8 more bits for a type of $38 and up
  and 8 more for $3E and up, then 1 bit: 0 and 6 bits, the step / 8 to the next entry's place, or 1 and 10 bits, the
  next place / 8 (0 ends the list). An entry is made when the camera ($3A:$06) + 64 reaches the place rounded down to
  16 ($8C71); it appears at that place in the level's own pixels (camera - 256 is the left of the screen). Object slots
  1-15: $0554 state, $0564 type, $0584/$0594 screen x, $05C4 y, $0664 what an egg holds. Lists are shared between
  levels that use the same objects, so a change shows in each of them.
* Eggs ($ABE4): a cracked egg's contents come from its type and $0664. Type $1C holds the stone axe while you have no
  weapon ($6D = 0); otherwise, like type $17, an item set per level and 2048-pixel stretch ($0533 = $AD69[level], two
  bits a stretch from the top: 0 skateboard (milk once you have one), 1 milk, 2 flower, 3 Honey Girl). Type $1D holds
  Honey Girl. Hidden eggs $19, $1A and $1B ($AB01) show when you jump into their place, then hold, in turn, the fire
  weapon or a bonus item, the eggplant, or the key.
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER = 16
DELTA = (0x00, -0x20, 0x20, -0x40, 0x40, -0x08, -0x60, 0x60)
GAP_FROM = (0x28, 0x00, 0x08, 0x00, 0x08, 0x48, 0x00, 0x20, 0x00)      # $C24D: a gap's start in its chunk (kind 7 up)
GAP_TO = (0x68, 0x68, 0x80, 0x08, 0x68, 0x80, 0x40, 0x60, 0x60)        # $C256: and its end
FRUIT_LIFT = {0x10: 0x48, 0x11: 0x18, 0x12: 0x4C, 0x13: 0x0C, 0x14: 0x48}   # $8AFD: how far above the ground fruit floats

# what each type is, from making it alone in a level that uses it and watching it (trace/v15_profiles/adventure_island/
# gal_sheet.png and names.png). Kinds: enemy, fruit, egg, hidden (a hidden egg or trigger), item, platform, spring.
TYPES = {
    0x01: ('enemy', 'Bonfire', 'Burns in one place on the ground.'),
    0x02: ('enemy', 'Rock', 'Sits on the ground in your way.'),
    0x03: ('enemy', 'Cobra', 'Stays in one place and sways from side to side.'),
    0x04: ('enemy', 'Rolling boulder', 'Rolls along the ground toward you.'),
    0x05: ('enemy', 'Rolling boulder, fast', 'Rolls along the ground toward you, faster than the other boulder.'),
    0x06: ('enemy', 'Pig', 'Walks along the ground toward you.'),
    0x07: ('enemy', 'Red frog', 'Sits in one place on the ground.'),
    0x08: ('enemy', 'Red frog, cave', 'Sits in one place on the ground.'),
    0x09: ('enemy', 'Red bird', 'Flies toward you in a wavy line.'),
    0x0A: ('enemy', 'Red bird, swooping', 'Flies toward you and swoops down to the ground.'),
    0x0B: ('enemy', 'Bat', 'Flies toward you in a wavy line.'),
    0x0C: ('enemy', 'Pig, running', 'Runs along the ground toward you, fast.'),
    0x0D: ('enemy', 'Green frog', 'Sits in one place on the ground.'),
    0x0E: ('enemy', 'Snail', 'Crawls slowly toward you.'),
    0x0F: ('enemy', 'Blue skull', 'Hovers in one place, bobbing a little.'),
    0x10: ('fruit', 'Banana', 'Appears when you come near; picking it up gives points.'),
    0x11: ('fruit', 'Apple', 'Appears when you come near; picking it up gives points.'),
    0x12: ('fruit', 'Tomato', 'Appears when you come near; picking it up gives points.'),
    0x13: ('fruit', 'Carrot', 'Appears when you come near; picking it up gives points.'),
    0x14: ('fruit', 'Melon', 'Appears when you come near; picking it up gives points.'),
    0x15: ('other', 'Nothing (an empty entry)', 'Takes an object slot but draws nothing and does nothing.'),
    0x17: ('egg', 'Egg', None),
    0x18: ('item', 'Stone axe', 'Lies on the ground; picking it up gives you the stone axe.'),
    0x19: ('hidden', 'Hidden egg', None),
    0x1A: ('hidden', 'Hidden egg', None),
    0x1B: ('hidden', 'Hidden egg', None),
    0x1C: ('egg', 'Egg', None),
    0x1D: ('egg', 'Egg', None),
    0x20: ('enemy', 'Red flower', 'Grows in one place on the ground.'),
    0x21: ('enemy', 'Red flower, dark forest', 'Grows in one place on the ground.'),
    0x22: ('enemy', 'Red frog, forest', 'Sits in one place on the ground.'),
    0x23: ('enemy', 'Pink octopus', 'Jumps up out of the water and falls back in.'),
    0x24: ('enemy', 'Swordfish', 'Leaps out of the water toward you.'),
    0x25: ('enemy', 'Pink octopus, high jump', 'Jumps high out of the water and falls back in.'),
    0x26: ('enemy', 'Icicle', 'Hangs from the ceiling.'),
    0x27: ('enemy', 'Icicle, ice cave', 'Hangs from the ceiling.'),
    0x28: ('enemy', 'Dark octopus', 'Jumps up out of the water and falls back in.'),
    0x29: ('enemy', 'Dark octopus, high jump', 'Jumps high out of the water and falls back in.'),
    0x30: ('hidden', 'Hidden cloud lift', 'Stand on this spot for about two seconds and a cloud lifts you up to a bonus.'),
    0x31: ('enemy', 'Rock, castle', 'Sits on the ground in your way.'),
    0x32: ('enemy', 'Bonfire, ice', 'Burns in one place on the ground.'),
    0x33: ('enemy', 'Snail, later areas', 'Crawls slowly toward you.'),
    0x34: ('enemy', 'Pig with a pot', 'Walks toward you; beaten, it leaves a pot behind.'),
    0x35: ('enemy', 'Cobra, sky', 'Stays in one place and sways from side to side.'),
    0x36: ('spring', 'Springboard', 'Bounces you high into the air when you land on it.'),
    0x37: ('spring', 'Springboard, cave', 'Bounces you high into the air when you land on it.'),
    0x38: ('enemy', 'Spider', 'Hangs on a thread and moves up and down.'),
    0x39: ('item', 'Pot', 'Floats high in the air in one place.'),
    0x3A: ('platform', 'Moving cloud', 'A platform that moves back and forth.'),
    0x3B: ('platform', 'Platform', 'A platform you can stand on.'),
    0x3E: ('platform', 'Platform, two settings', 'A platform you can stand on; its two settings say how it moves.'),
    0x3F: ('platform', 'Cloud platform', 'A platform you can stand on.'),
}
# what a cracked egg shows ($AD50 picture, $AC8A what touching it does), from forcing each code (contents.png)
CONTENTS = {0: 'stone axe', 1: 'fire weapon', 2: 'milk', 3: 'red milk bottle', 4: 'skateboard', 5: 'flower',
            6: 'bonus ring', 7: 'baby doll (an extra life)', 8: 'eggplant', 9: 'key', 'honey': 'Honey Girl'}
SPOT = {0: 4, 1: 2, 2: 5, 3: 'honey'}       # $0533 two-bit code -> contents ($AC2E: $AD66 + code; 3 is the Honey Girl egg)
EGG_KINDS = (0x1C, 0x17, 0x1D, 0x19, 0x1A, 0x1B)
NO_SWAP = ('platform', 'spring', 'other')


def _o(address):
    return HEADER + address - 0x8000


def _signed(value):
    return value - 0x100 if value & 0x80 else value


class _Bits:
    def __init__(self, rom, address):
        self.rom, self.at, self.left, self.byte = rom, address, 0, 0

    def read(self, count):
        value = 0
        for _ in range(count):
            if not self.left:
                self.byte, self.left = self.rom[_o(self.at)], 8
                self.at += 1
            value = value << 1 | self.byte >> 7
            self.byte, self.left = self.byte << 1 & 0xFF, self.left - 1
        return value


def decode(rom, address):
    """([{'pos', 'type', 'p1', 'p2'}], address after the last byte read) of one object list."""
    bits, out = _Bits(rom, address), []
    pos = bits.read(10) << 3
    while len(out) < 400:
        kind = bits.read(6)
        p1 = bits.read(8) if kind >= 0x38 else None
        p2 = bits.read(8) if kind >= 0x3E else None
        out.append({'pos': pos, 'type': kind, 'p1': p1, 'p2': p2})
        if bits.read(1):
            pos = bits.read(10) << 3
            if not pos:
                break
        else:
            pos += bits.read(6) << 3
    return out, bits.at


def encode(entries) -> bytes:
    """The game's packing of a list ($8D47/$8CF5); the same bytes as the game's own lists for unchanged entries."""
    bits = []

    def put(value, count):
        bits.extend(value >> i & 1 for i in range(count - 1, -1, -1))
    put(entries[0]['pos'] >> 3, 10)
    for i, entry in enumerate(entries):
        put(entry['type'], 6)
        if entry['type'] >= 0x38:
            put(entry['p1'], 8)
        if entry['type'] >= 0x3E:
            put(entry['p2'], 8)
        if i + 1 < len(entries):
            step = (entries[i + 1]['pos'] - entry['pos']) >> 3
            if 0 <= step < 64:
                put(0, 1)
                put(step, 6)
            else:
                put(1, 1)
                put(entries[i + 1]['pos'] >> 3, 10)
        else:
            put(1, 1)
            put(0, 10)
    bits += [0] * (-len(bits) % 8)
    return bytes(int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))


def _playing(ram):
    """A level is being played: a layout is loaded ($1B, $2F), not the demo ($40) and not the end of a life ($44, which
    stays set on the title screen after the game is over)."""
    return bool(ram[0x2F] and ram[0x1B] and ram[0x51] < 32 and not ram[0x40] and not ram[0x44])


def type_name(kind):
    return TYPES[kind][1] if kind in TYPES else f'Unknown object (type {kind:#04x})'


class _SpawnWatcher(Watcher):
    """Watches the object slots as the replayed game makes them. When the camera reaches the entry's place the game makes
    it (at the place's x in the level's pixels); every slot that is new or changes type within 10 pixels of that x while
    the camera is there counts. A swap is good when the chosen type is made there; a removal when the old type is made
    there no more often than the other entries that stay at that place."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.last = {}
        self.made = []
        self.done = False

    def see(self, ram, frame, run):
        w = self.w
        if not _playing(ram) or ram[0x51] != w['level'] or ram[0x49] != w['bonus']:
            self.last = {}
            return False
        camera = (ram[0x3A] << 8 | ram[0x06]) - (0x10000 if ram[0x3A] & 0x80 else 0) - 256
        due = w['x'] - 320
        for slot in range(1, 16):
            state, kind = ram[0x554 + slot], ram[0x564 + slot]
            key = (state != 0, kind)
            if state and self.last.get(slot) != key and due - 8 <= camera <= due + 24:
                x = camera + ((ram[0x594 + slot] << 8 | ram[0x584 + slot]) - (0x10000 if ram[0x594 + slot] & 0x80 else 0))
                if abs(x - w['x']) <= 10:
                    self.made.append(kind)
            self.last[slot] = key
        if camera > due + 24 and camera < due + 200:
            self.done = True
            return True
        return False

    def result(self):
        w = self.w
        if not self.done:
            return super().result()
        if w['want'] is None:
            ok = self.made.count(w['old']) <= w['others']
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game no longer makes the {w["name"]} there.' if ok
                    else f'Played from the start, the game still makes the {w["name"]} there.'}
        ok = w['want'] in self.made
        if ok:
            return {'state': 'good', 'text': f'Played from the start, the game now makes the chosen one there ({w["name"]}).'}
        seen = ', '.join(type_name(k) for k in self.made) or 'nothing'
        return {'state': 'bad', 'text': f'Played from the start, the game made something else there ({seen}).'}


class AdventureIslandProfile(Profile):
    """Adventure Island (USA). Parts are {'level': 0-31} and, in a cloud bonus, {'level', 'bonus': 1-9}."""
    name = 'Adventure Island'
    sha256s = ('f4083971fb7341ba6560fdd8ef588bd6e2ad450a8694a563cec099a5d306d42e',)
    system = 'nes'
    LISTS, BONUS_LISTS, BONUSES = 0xF118, 0xF1D8, 9

    # ---- the game's tables
    def at(self, address):
        return self.rom[_o(address)]

    def word(self, address):
        return self.at(address) | self.at(address + 1) << 8

    def map_of(self, level):
        return self.at(0xD94B + level)

    def chunks(self, level):
        """[(vertical scroll, height change, shape, fruit lift)] of the level's 128-pixel chunks."""
        layout = self.word(0xD99C + self.map_of(level) * 2)
        out = []
        for c in range(66):
            b0, b1, b2 = (self.at(layout + 3 * c + k) for k in range(3))
            out.append((b0 & 3, b1 >> 2 & 7, b2 & 15, b2 & 0xF0))
        return out

    def heights(self, level):
        """Ground height of each chunk's start in the level's pixels (chunk 0 where the level starts on the screen)."""
        start = self.at(self.word(0xD9B4 + self.map_of(level) * 2))
        out, h = [], 0x60 + 8 * (start & 15)
        for c, row in enumerate(self.chunks(level)):
            if c:
                h += DELTA[row[1]]
            out.append(h)
        return out

    def ground(self, level, x):
        """($C1EA) the ground's y at a level x, and whether it is a gap there."""
        c = max(0, min(65, x // 128))
        inside = x % 128
        h = self.heights(level)[c]
        shape = self.chunks(level)[c][2]
        if shape == 2:
            return h - inside // 4, False
        if shape == 3:
            return h + inside // 4, False
        if 4 <= shape <= 6:
            return (h + (-0x20 if shape == 4 else 0x20) if inside >= 0x40 else h), False
        if shape >= 7:
            k = shape - 7
            return h, GAP_FROM[k] <= inside < GAP_TO[k]
        return h, shape == 1

    def list_word(self, part, number):
        bonus = int(part.get('bonus', 0))
        return (self.BONUS_LISTS + (bonus - 1) * 6 if bonus else self.LISTS + int(part['level']) * 6) + number * 2

    def lists(self, part):
        """[(list number, address, entries, end)] of a part."""
        out = []
        for number in range(3):
            address = self.word(self.list_word(part, number))
            if address:
                entries, end = decode(self.rom, address)
                out.append((number, address, entries, end))
        return out

    def _all_lists(self):
        words = [self.LISTS + 2 * k for k in range(32 * 3)] + [self.BONUS_LISTS + 2 * k for k in range(self.BONUSES * 3)]
        return sorted({self.word(w) for w in words if self.word(w)})

    def list_room(self, address, end):
        """Bytes a list may use when packed again: the bytes it has now (lists sit one after another)."""
        return end - address

    def list_users(self, address):
        words = [(self.LISTS + 2 * k, k // 3) for k in range(32 * 3)]
        return sorted({level for w, level in words if self.word(w) == address})

    def chr_group(self, level):
        return self.at(0xD96C + self.map_of(level)) >> 4 & 3

    def contents(self, level, kind, x, hidden_turn=True):
        """Plain words for what an egg of `kind` at level x holds."""
        stretch = max(0, x) // 2048
        code = self.at(0xAD69 + level) >> (6 - 2 * min(stretch, 3)) & 3
        spot = CONTENTS[SPOT[code]]
        if code == 0:
            spot = 'a skateboard (milk if you already have one)'
        if kind == 0x1C:
            return f'the stone axe if you have no weapon, otherwise {spot}'
        if kind == 0x17:
            return spot
        if kind == 0x1D:
            return 'Honey Girl'
        if kind == 0x19:
            return 'the fire weapon if you hold the stone axe, otherwise a bonus item (it changes as you find more)'
        if kind == 0x1A:
            return 'the eggplant'
        if kind == 0x1B:
            return 'the key'
        return 'nothing'

    def egg_name(self, level, kind, x):
        """A short name for a choice list: 'Egg: skateboard', 'Hidden egg: key'."""
        short = {0x1C: 'stone axe first', 0x1D: 'Honey Girl', 0x19: 'fire weapon or a bonus item', 0x1A: 'eggplant', 0x1B: 'key'}
        if kind == 0x17:
            code = self.at(0xAD69 + level) >> (6 - 2 * min(max(0, x) // 2048, 3)) & 3
            short[0x17] = CONTENTS[SPOT[code]]
        return ('Hidden egg' if TYPES[kind][0] == 'hidden' else 'Egg') + ': ' + short[kind]

    # ---- the profile interface
    def where(self, ram):
        if not _playing(ram):
            return None
        camera = (ram[0x3A] << 8 | ram[0x06]) - (0x10000 if ram[0x3A] & 0x80 else 0)
        level, chunk = ram[0x51], ram[0x3B]
        y = 0
        if chunk < 66:
            y = self.heights(level)[chunk] - ram[0x509]
        part = {'level': level}
        if ram[0x49]:
            part['bonus'] = ram[0x49]
        return {'part': part, 'x': camera - 256, 'y': y}

    def part_name(self, part):
        level = int(part['level'])
        name = f'Area {level // 4 + 1}-{level % 4 + 1}'
        return name + (f', cloud bonus {part["bonus"]}' if part.get('bonus') else '')

    def choices(self):
        return {'fruit': [{'value': k, 'name': TYPES[k][1]} for k in range(0x10, 0x15)]}

    def enemy_choices(self, level):
        group = self.chr_group(level)
        used = set()
        for other in range(32):
            if self.chr_group(other) != group:
                continue
            for _, _, entries, _ in self.lists({'level': other}):
                used |= {e['type'] for e in entries}
        return [{'value': k, 'name': TYPES[k][1]} for k in sorted(used) if TYPES.get(k, ('',))[0] == 'enemy' and k < 0x38]

    def entry_y(self, level, entry):
        kind = entry['type']
        y, _ = self.ground(level, entry['pos'] & ~15)
        rec = _signed(self.at(0x901E + kind * 6 + 3)) if kind < 0x44 else 0
        y += rec
        if kind in FRUIT_LIFT:
            y -= FRUIT_LIFT[kind] + self.chunks(level)[max(0, min(65, entry['pos'] // 128))][3]
        if kind == 0x39:
            y -= 2 * entry['p1']
        return y + 8          # bottom of the 16-pixel picture

    def objects(self, part):
        level = int(part['level'])
        out = []
        enemies = None
        for number, address, entries, end in self.lists(part):
            users = self.list_users(address)
            for index, entry in enumerate(entries):
                kind = entry['type']
                group, name, does = TYPES.get(kind, ('other', type_name(kind), None))
                x = entry['pos'] & ~15
                row = {'id': f'list{number}:{index}', 'type': kind, 'x': x, 'y': self.entry_y(level, entry),
                       'name': name, 'remove': 'Remove this', 'fields': [],
                       'style': {'enemy': 'enemy', 'hidden': 'secret'}.get(group, 'item')}
                if does:
                    row['does'] = does
                if group == 'enemy' and kind < 0x38:
                    enemies = enemies if enemies is not None else self.enemy_choices(level)
                    options = enemies if any(c['value'] == kind for c in enemies) else enemies + [{'value': kind, 'name': name}]
                    row['fields'] = [{'key': 'type', 'label': 'Swap for', 'value': kind, 'choices': options}]
                elif group == 'fruit':
                    row['fields'] = [{'key': 'type', 'label': 'Fruit', 'value': kind, 'choices': 'fruit'}]
                elif kind in EGG_KINDS:
                    row['detail'] = 'holds ' + self.contents(level, kind, x)
                    row['does'] = ('Shows only when you jump into this spot; then it is an egg you crack by touching it.'
                                   if group == 'hidden' else 'Cracks when you touch it or hit it, and shows what it holds.')
                    row['fields'] = [{'key': 'type', 'label': 'Holds', 'value': kind,
                                      'choices': [{'value': k, 'name': self.egg_name(level, k, x)} for k in EGG_KINDS]}]
                elif kind == 0x39:
                    row['detail'] = f'{entry["p1"] * 2} pixels up'
                if len(users) > 1 and not part.get('bonus'):
                    others = [u for u in users if u != level]
                    row['note'] = ('The game uses this list in ' + ', '.join(self.part_name({'level': u}) for u in others) +
                                   ' too, so a change shows there as well.')
                out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        level = int(part['level'])
        name, _, index = object_id.partition(':')
        if not name.startswith('list'):
            raise ValueError('ROMancer cannot change that yet.')
        number, index = int(name[4:]), int(index)
        found = next((l for l in self.lists(part) if l[0] == number), None)
        if found is None or not 0 <= index < len(found[2]):
            raise ValueError('That is not part of this level any more. Reopen the map.')
        _, address, entries, end = found
        entry = entries[index]
        old = entry['type']
        new_entries = [dict(e) for e in entries]
        if remove:
            if len(entries) == 1:
                raise ValueError('This is the only thing in its list, and the game needs at least one. Swap it for something else instead.')
            del new_entries[index]
            want, title = None, f'Remove the {type_name(old).lower()}'
        else:
            row = self.find(part, object_id)
            if not row['fields']:
                raise ValueError('ROMancer cannot swap this one; it can only be removed.')
            want = int(values.get('type', old))
            self.pick(row['fields'][0], self.choices(), want)
            new_entries[index]['type'] = want
            label = self.egg_name(level, want, entry['pos'] & ~15) if want in EGG_KINDS else type_name(want)
            title = {'Swap for': f'Enemy here: {label}', 'Fruit': f'Fruit here: {label}'}.get(row['fields'][0]['label'], label)
        data = encode(new_entries)
        room = self.list_room(address, end)
        if len(data) > room:
            raise ValueError('The changed list would not fit in the space the game gives it.')
        base = _o(address)
        writes = [(base + i, self.rom[base + i], b) for i, b in enumerate(data) if self.rom[base + i] != b]
        x = entry['pos'] & ~15
        others = sum(1 for e in new_entries if e['pos'] & ~15 == x and e['type'] == old)
        shown = (self.egg_name(level, want, x) if want in EGG_KINDS else type_name(want)) if want is not None else type_name(old)
        return {'writes': writes, 'title': title,
                'watch': {'kind': 'spawn', 'level': level, 'bonus': int(part.get('bonus', 0)), 'x': x, 'want': want,
                          'old': old, 'others': others, 'name': shown.lower() if want is None else shown}}

    def watcher(self, watch):
        return _SpawnWatcher(watch)


PROFILES = [AdventureIslandProfile]
