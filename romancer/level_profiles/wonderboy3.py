"""Level profile for Wonder Boy III - The Dragon's Trap (Master System).

Everything here was read from the game's Z80 code and checked by replaying the game with a changed ROM (research notes:
research/wonderboy3-level-profile.md, scratch scripts in trace/v15_profiles/wonderboy3/). Master System RAM is the 8 KB
at CPU $C000-$DFFF; the snapshot's 'wram' domain holds it with index 0 = $C000.

The game is made of rooms. A room is a strip one screen high (11 rows of 16-pixel blocks under the status bar) that
scrolls only sideways, so the camera has no y.

* Rooms: 178 headers of 18 bytes at $8000 in bank 4 (ROM $10000). A door's destination record says where the hero
  stands and which header to load ($2620); the first 8 header bytes are copied to RAM $CF5E ($26F4): +0 the room's
  door/exit zones, +2 its block set, +4 its object list, +6 a room byte.
* Object list (bank 4, read at $2948 into the table $D030, 7 bytes an entry): records of 4 bytes [type, x / 8, y,
  drop]; a type with bit 7 set is a one-byte record (a room effect); $FF ends the list. An object is made in one of the
  slots at $C3C0 (64 bytes each: +0 bit 7 in use, +3/+4 x, +6 y, +$0F type, +$1A drop, +$2E the record's number) when
  the camera brings its x within 32 pixels of the screen edge ($64DB); the entry's +6 bit 7 is then set, so a beaten
  enemy stays away until the room is entered again.
* Sprite tiles: every different type in the list has its tiles loaded when the room starts ($29FA, descriptor at
  word $9D60 + (type - 1) * 2 in bank 7, $9E00 for one-byte records), from tile $56 up. More than 170 tiles run into
  the status bar's tiles (seen in the game), so a swap is only offered when the room stays within 170.
* Drop byte ($67C1, when the enemy is beaten): $FF nothing; bit 7 set: that item (byte & $7F); otherwise one of 16
  items picked at random from the table at $8BB0 + byte * 16 in bank 7.
* Items: high four bits the kind, low four the number (owned table $CF20 + kind * 10 + number, $2804). Names come from
  the game's own name lists (bank 7, word $8272 + kind * 4): swords, shields, armour, magic weapons, other items.
* Shops: a door whose zone type is 2, 10 or 12 opens a shop ($4CAD, $4D72); its destination word points at 4 item
  bytes in bank 4 ($334D), $FF being an empty place. Prices are kept per item, so any item a shop sells has a price.
* Camera: $D00F (x); the room's pixel row 0 is the screen's row 0.
"""
from __future__ import annotations

from . import Profile, Watcher

RAM = 0xC000


def _w(ram, address):
    return ram[address - RAM] | ram[address - RAM + 1] << 8


def _b(ram, address):
    return ram[address - RAM]


def _bank(bank, address):
    """ROM offset of a CPU address in slot 2 ($8000-$BFFF) with the given bank paged in."""
    return bank * 0x4000 + address - 0x8000


COLOURS = ['red', 'green', 'blue']


def _triple(first, name):
    return {first + k: f'{name} ({COLOURS[k]})' for k in range(3)}


class _Wb3Watcher(Watcher):
    """Watches a Wonder Boy III edit in the replayed game.

    Object (swap, drop): the first time an object slot holds the record's number in the room, its type ($0F) and drop
    ($1A) are what the game made. Removal: once the camera has come close enough for the record to be made, neither its
    spawned flag nor a slot with its number may show. Shop: once the shop with that list is open ($CFFE), its four items
    are in $D10E-$D111 as the game read them."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.near = None

    def see(self, ram, frame, run):
        w = self.w
        if w['kind'] == 'shop':
            if _w(ram, 0xCFFE) != w['list']:
                return False
            got = bytes(ram[0xD10E - RAM:0xD112 - RAM])
            if got == bytes(4):
                return False
            self.seen = list(got)
            return True
        if bytes(ram[0xCF5E - RAM:0xCF65 - RAM]) != bytes(w['header']) or _b(ram, 0xD0A0) != w['count']:
            return False
        entry = 0xD030 + 7 * w['number']
        slots = [0xC3C0 + 64 * k for k in range(8)]
        mine = [s for s in slots if _b(ram, s) & 0x80 and _b(ram, s + 0x2E) == w['number'] and _b(ram, s + 0x0F)]
        if w['kind'] == 'remove':
            if mine or _b(ram, entry + 6) & 0x80:
                self.seen = 'there'
                return True
            camera = _w(ram, 0xD00F)
            if camera + 0x108 + 0x20 > w['x'] and camera - 0x28 < w['x']:
                self.near = frame if self.near is None else self.near
                if frame - self.near >= 8:
                    self.seen = 'gone'
                    return True
            return False
        if not mine:
            return False
        self.seen = (_b(ram, mine[0] + 0x0F), _b(ram, mine[0] + 0x1A))
        return True

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return super().result()
        if w['kind'] == 'shop':
            ok = seen[w['place']] == w['item']
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the shop offers {w["name"]} in that place.' if ok
                    else 'Played from the start, the shop offers something else in that place.'}
        if w['kind'] == 'remove':
            ok = seen == 'gone'
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, nothing appears there any more.' if ok
                    else 'Played from the start, it still appears there.'}
        kind, drop = seen
        ok = kind == w['type'] and drop == w['drop']
        if ok:
            return {'state': 'good', 'text': f'Played from the start, the game makes a {w["name"]} there, with the chosen drop.'}
        return {'state': 'bad', 'text': 'Played from the start, the game makes something else there.'}


class WonderBoy3Profile(Profile):
    """Wonder Boy III - The Dragon's Trap (USA, Europe)."""
    name = "Wonder Boy III - The Dragon's Trap"
    sha256s = ('f2db2cbdaaedb3275fc6d334dc36514cbad969a5be62f63b93e14e7dbb7d9897',)
    system = 'sms'
    ROOMS = 178
    HEADERS = 0x8000            # bank 4
    TILE_START = 0x56
    TILE_ROOM = 170             # 256 - $56: more runs into the status bar's tiles (measured)
    FAR = 0xFF                  # x / 8 of a removed record: past the widest room, so the camera never brings it in
    SHOP_DOORS = (2, 10, 12)    # zone types whose door opens a shop ($4CAD: these go to $4D72)
    # names from making room 0's first record each type and looking at what the game draws
    # (trace/v15_profiles/wonderboy3/zoom_a.png, zoom_b.png); colours are the game's three strengths of each
    ENEMIES = {**_triple(0x01, 'Knight'), **_triple(0x04, 'Small ghost'), **_triple(0x09, 'Round creature'),
               0x0C: 'Skeleton', 0x0D: 'Skeleton with a hat', 0x0E: 'Skull', 0x0F: 'Skull with a hat',
               0x10: 'Small skeleton', 0x11: 'Enemy 0x11', 0x12: 'Enemy 0x12', 0x13: 'Enemy 0x13',
               **_triple(0x14, 'Crab'), **_triple(0x17, 'Bird'), **_triple(0x1D, 'Wizard'), **_triple(0x21, 'Ninja'),
               **_triple(0x24, 'Scythe knight'), **_triple(0x27, 'Octopus'), **_triple(0x2A, 'Cloud'),
               **_triple(0x2D, 'Bubble cluster'), **_triple(0x30, 'Fish'), **_triple(0x33, 'Beast man'),
               **_triple(0x36, 'Cobra'), **_triple(0x3A, 'Mushroom'), **_triple(0x3D, 'Spiky ball'),
               0x44: 'Small flower', 0x45: 'Tall flower'}
    OTHER = {0x20: 'Blue ball', 0x39: 'Floating block', 0x40: 'Rock', 0x41: 'Rock', 0x42: 'Rock', 0x43: 'Rock'}
    KINDS = ['sword', 'shield', 'armour', 'magic', 'item']
    # items with no name in the game's lists: pictured when a beaten cobra drops them, and the RAM change measured the
    # frame the hero picks them up (trace/v15_profiles/naming_sega/wb3_items.py; full life is $680, one heart $D0)
    EXTRA_ITEMS = {0x43: 'Heart in a box', 0x44: 'Large heart', 0x45: 'Small heart', 0x46: 'Question box'}
    ITEM_DOES = {0x43: 'Restores one heart of life.', 0x44: 'Restores about six hearts of life.',
                 0x45: 'Restores half a heart of life.', 0x46: 'Sets the flag that some locked doors need.'}
    # gold: the amount added to the gold count ($CF55-$CF56, decimal digits) when picked up (measured)
    GOLD = {0x50: 1, 0x51: 4, 0x52: 7, 0x53: 10, 0x54: 13, 0x55: 20, 0x56: 27, 0x57: 34, 0x58: 41, 0x59: 56, 0x5A: 71,
            0x5B: 84, 0x5C: 84, 0x5D: 84, 0x5E: 84, 0x5F: 84}

    # -- the game's tables
    def word(self, offset):
        return self.rom[offset] | self.rom[offset + 1] << 8

    def header_at(self, room):
        return _bank(4, self.HEADERS + 18 * room)

    def header(self, room):
        at = self.header_at(room)
        return bytes(self.rom[at:at + 18])

    def list_at(self, room):
        return _bank(4, self.word(self.header_at(room) + 4))

    def zones_at(self, room):
        return _bank(4, self.word(self.header_at(room)))

    def records(self, room):
        """[(number, rom offset, type, x / 8, y, drop)]; one-byte records have x, y and drop None."""
        q, out = self.list_at(room), []
        while self.rom[q] != 0xFF and len(out) < 32:
            kind = self.rom[q]
            if kind & 0x80:
                out.append((len(out), q, kind, None, None, None))
                q += 1
            else:
                out.append((len(out), q, kind, self.rom[q + 1], self.rom[q + 2], self.rom[q + 3]))
                q += 4
        return out

    def zones(self, room):
        """[(rom offset, x, y bottom, width, height, type, destination)] of the room's doors and exits."""
        q, out = self.zones_at(room), []
        while self.rom[q] != 0xFF and len(out) < 32:
            r = self.rom[q:q + 7]
            out.append((q, r[0] * 8, r[1], r[2] * 8, r[3], r[4], r[5] | r[6] << 8))
            q += 7
        return out

    def shops(self, room):
        return [z for z in self.zones(room) if z[5] & 0x3F in self.SHOP_DOORS]

    def sharing(self, room):
        at = self.list_at(room)
        return [n for n in range(self.ROOMS) if n != room and self.list_at(n) == at]

    def tiles(self, kind):
        """Sprite tiles the room loads for a type (its descriptor in bank 7: entries of [count, source word], a count of
        $7F is one blank tile, bit 7 adds a destination byte, 0 ends; $0A97)."""
        table = 0x9E00 if kind & 0x80 else 0x9D60
        pointer = self.word(_bank(7, table + 2 * ((kind & 0x7F) - 1)))
        q, n = _bank(7, (pointer & 0x3FFF) | 0x8000), 0
        for _ in range(64):
            a = self.rom[q]
            q += 1
            if a == 0:
                break
            if a & 0x80:
                a &= 0x7F
                q += 1
            if a == 0x7F:
                n += 1
            else:
                n += a
                q += 2
        return n

    def room_tiles(self, kinds):
        seen = []
        for k in kinds:
            if k not in seen:
                seen.append(k)
        return sum(self.tiles(k) for k in seen)

    def item_name(self, item):
        """The game's own name for an item (name lists in bank 7), or its number."""
        kind, number = item >> 4, item & 0x0F
        if kind < 5:
            names = self.word(_bank(7, 0x8272 + kind * 4))
            count = {0: 10, 1: 10, 2: 10, 3: 5, 4: 3}[kind]
            if number < count:
                q = _bank(7, self.word(_bank(7, names + 2 * number)))
                text, words = bytearray(), []
                for _ in range(40):
                    c = self.rom[q]
                    q += 1
                    if c in (0xFE, 0xFF):
                        words.append(text.decode('ascii', 'replace').strip())
                        text = bytearray()
                        if c == 0xFF:
                            break
                    else:
                        text.append(c)
                name = ' '.join(w for w in words if w)
                if name:
                    return name.title()
        if item in self.EXTRA_ITEMS:
            return self.EXTRA_ITEMS[item]
        if item in self.GOLD:
            return f'{self.GOLD[item]} gold'
        return f'Item 0x{item:02X}'

    def drop_name(self, drop):
        if drop == 0xFF:
            return 'Nothing'
        if drop & 0x80:
            return self.item_name(drop & 0x7F)
        table = bytes(self.rom[_bank(7, 0x8BB0 + 16 * drop):_bank(7, 0x8BB0 + 16 * drop) + 16])
        names = []
        for v in table:
            n = 'nothing' if v == 0xFF else self.item_name(v & 0x7F if v & 0x80 else v)
            if n not in names:
                names.append(n)
        shown = ', '.join(names[:4]) + (' and more' if len(names) > 4 else '')
        return f'Random {drop}: {shown}'

    def drops(self):
        """Drop bytes the game itself gives its enemies anywhere."""
        found = {0xFF}
        for room in range(self.ROOMS):
            for _, _, kind, _, _, drop in self.records(room):
                if kind in self.ENEMIES:
                    found.add(drop)
        return sorted(found)

    def wares(self):
        """Items any shop of the game sells (each has a price), and $FF for an empty place."""
        found = {0xFF}
        for room in range(self.ROOMS):
            for z in self.shops(room):
                at = _bank(4, z[6])
                found.update(self.rom[at:at + 4])
        return sorted(found)

    def room_of(self, ram):
        here = bytes(ram[0xCF5E - RAM:0xCF65 - RAM])
        for room in range(self.ROOMS):
            if self.header(room)[:7] == here:
                return room
        return None

    # -- the profile interface
    def where(self, ram):
        room = self.room_of(ram)
        if room is None or _b(ram, 0xD0A0) != len(self.records(room)):
            return None             # title, story or a room still loading
        return {'part': {'room': room}, 'x': _w(ram, 0xD00F), 'y': 0}

    def part_name(self, part):
        return f'Room {int(part["room"])}'

    def choices(self):
        return {'drops': [{'value': d, 'name': self.drop_name(d)} for d in self.drops()],
                'wares': [{'value': v, 'name': 'Empty' if v == 0xFF else self.item_name(v)} for v in self.wares()]}

    def enemy_choices(self, room, number):
        """Enemies that can stand in for record `number` without the room's sprite tiles running past 170."""
        kinds = [r[2] for r in self.records(room)]
        out = []
        for k in sorted(self.ENEMIES):
            trial = kinds[:number] + [k] + kinds[number + 1:]
            if k == kinds[number] or self.room_tiles(trial) <= self.TILE_ROOM:
                out.append({'value': k, 'name': self.ENEMIES[k]})
        return out

    def objects(self, part):
        room = int(part['room'])
        shared = self.sharing(room)
        out = []
        for number, offset, kind, x8, y, drop in self.records(room):
            if kind & 0x80:
                continue
            row = {'id': f'object:{number}', 'type': kind, 'x': x8 * 8, 'y': y + 16, 'remove': None, 'fields': []}
            if x8 == self.FAR:
                continue
            if kind in self.ENEMIES:
                row.update(style='enemy', name=self.ENEMIES[kind], detail=f'drops {self.drop_name(drop).lower()}',
                           remove='Remove this enemy',
                           fields=[{'key': 'type', 'label': 'Swap for', 'value': kind, 'choices': self.enemy_choices(room, number)},
                                   {'key': 'drop', 'label': 'Drops', 'value': drop, 'choices': 'drops'}])
            else:
                row.update(style='item' if kind in self.OTHER else 'block', name=self.OTHER.get(kind, f'Object 0x{kind:02X}'))
            if shared:
                row['note'] = 'This object list is shared with ' + ', '.join(self.part_name({'room': n}) for n in shared[:4]) + \
                              (' and more' if len(shared) > 4 else '') + ', so a change shows there too.'
            out.append(row)
        for z in self.shops(room):
            at = _bank(4, z[6])
            items = list(self.rom[at:at + 4])
            sold = ', '.join(self.item_name(i) for i in items if i != 0xFF) or 'nothing'
            out.append({'id': f'shop:{z[0]}', 'style': 'item', 'type': 'shop', 'x': z[1] + z[3] // 2, 'y': z[2],
                        'name': 'Shop door', 'detail': f'sells {sold}', 'remove': None,
                        'fields': [{'key': f'item{k}', 'label': f'Place {k + 1}', 'value': items[k], 'choices': 'wares'} for k in range(4)]})
        return out

    def edit(self, part, object_id, values, remove=False):
        room = int(part['room'])
        found = self.find(part, object_id)
        kind, _, rest = object_id.partition(':')
        choices = self.choices()
        if kind == 'shop':
            z = next(z for z in self.shops(room) if z[0] == int(rest))
            at = _bank(4, z[6])
            writes, watch = [], None
            for k in range(4):
                old = self.rom[at + k]
                new = int(values.get(f'item{k}', old))
                if new not in self.wares():
                    raise ValueError('That choice is not one of the game’s own.')
                if new != old:
                    writes.append((at + k, old, new))
                    name = 'nothing' if new == 0xFF else self.item_name(new)
                    watch = watch or {'kind': 'shop', 'list': z[6], 'place': k, 'item': new, 'name': name}
            if watch is None:
                watch = {'kind': 'shop', 'list': z[6], 'place': 0, 'item': self.rom[at], 'name': self.item_name(self.rom[at])}
            return {'writes': writes, 'title': f'Shop wares ({self.part_name(part)})', 'watch': watch}
        if kind != 'object' or found['style'] != 'enemy':
            raise ValueError('ROMancer cannot change that yet.')
        number = int(rest)
        _, offset, old, x8, y, drop = self.records(room)[number]
        base = {'header': list(self.header(room)[:7]), 'count': len(self.records(room)), 'number': number}
        if remove:
            return {'writes': [(offset + 1, x8, self.FAR)], 'title': f'Remove the enemy ({self.part_name(part)})',
                    'watch': dict(base, kind='remove', x=x8 * 8)}
        new = int(values.get('type', old))
        new_drop = int(values.get('drop', drop))
        if all(c['value'] != new for c in found['fields'][0]['choices']):
            raise ValueError('That choice is not one of the game’s own.')
        self.pick(found['fields'][1], choices, new_drop)
        writes = [(offset, old, new)] if new != old else []
        writes += [(offset + 3, drop, new_drop)] if new_drop != drop else []
        name = self.ENEMIES[new]
        title = f'Enemy here: {self.ENEMIES[new]}' if new != old else f'Enemy drops: {self.drop_name(new_drop)}'
        return {'writes': writes, 'title': f'{title} ({self.part_name(part)})',
                'watch': dict(base, kind='object', type=new, drop=new_drop, name=name)}

    def watcher(self, watch):
        return _Wb3Watcher(watch)


PROFILES = [WonderBoy3Profile]
