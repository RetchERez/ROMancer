"""Sonic The Hedgehog and Sonic The Hedgehog 2 (Mega Drive): the object layout and the chunk layout of every act.

Each act has a plain list of the objects placed in it, 6 bytes each, sorted by x and ended by x = $FFFF:

    x (word), y (word: low 12 bits y, two flip bits above), object id (byte), subtype (byte)

Sonic 1 marks an object the game remembers (a broken monitor stays broken) with bit 7 of the id byte; Sonic 2 marks it
with bit 15 of the y word. Edits change the id and subtype bytes of one record in place, so nothing moves: a swap writes
another enemy's id and subtype as the game uses them in the same zone (so its graphics are loaded there), and a removal
writes object id 0, which the object loader places as an empty slot. Worked out from the games' own loaders (Sonic 1
$D8F0 and $DA56, Sonic 2 $17A2A and $17EBE) and proven by replaying the game; see research/megadrive_sonic-level-profile.md.

The level layouts are made of chunks (256 by 256 pixels in Sonic 1, 128 by 128 in Sonic 2), so the general painter
cannot change them; packed_layout and set_packed_layout copy whole chunks:

* Sonic 1 (loader $6D12): index $68BD6, three words an act (foreground, background, unused), 6 bytes an act and 4 acts
  a zone; each layout is its width less one, its height less one, then the chunk numbers row by row, plain. The game
  copies it to $FFA400, $80 bytes a row (the background sits $40 on). Bit 7 of a chunk number is the loop flag and
  stays with the chunk. Writes go in place.
* Sonic 2 (loader $E42C): index $45A80, one word an act (unsigned, forward from the index), Kosinski compressed (KosDec
  $18F8) into $FFFF8000: 16 rows of $100 bytes, the foreground in the first $80 of each row. A change is decompressed,
  changed and compressed again by kos_encode, and must fit the layout's old room (up to the next layout; the layouts
  are padded to 16 bytes). No free space lies within reach of the index's 16-bit offsets, so a layout that does not
  fit is refused.

RAM: snapshots give work RAM as 'wram', index 0 = $FF0000, words big-endian (68000 order).
"""
from __future__ import annotations

from . import Profile, Watcher


def _w(data, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def kos_decode(data, at: int = 0):
    """Kosinski as KosDec ($18F8) reads it: (bytes out, bytes of input read). The next descriptor word is read as soon as
    the 16th bit of the old one is used, before that command's bytes."""
    src, out = at, bytearray()
    desc, left = data[src] | data[src + 1] << 8, 16
    src += 2

    def bit():
        nonlocal desc, left, src
        b = desc & 1
        desc >>= 1
        left -= 1
        if left == 0:
            desc, left = data[src] | data[src + 1] << 8, 16
            src += 2
        return b
    while True:
        if bit():
            out.append(data[src])
            src += 1
            continue
        if bit() == 0:
            count = (bit() << 1 | bit()) + 2
            back = 0x100 - data[src]
            src += 1
        else:
            lo, hi = data[src], data[src + 1]
            src += 2
            back = 0x2000 - (((hi & 0xF8) << 5) | lo)
            if hi & 7:
                count = (hi & 7) + 2
            else:
                count = data[src]
                src += 1
                if count == 0:
                    return bytes(out), src - at
                if count == 1:
                    continue
                count += 1
        if back > len(out):
            raise ValueError('That compressed layout reaches back before its start.')
        for _ in range(count):
            out.append(out[-back])


def kos_encode(data: bytes, chain: int = 48) -> bytes:
    """A Kosinski stream that kos_decode (and the game) reads back as data: the cheapest path over the commands (a
    literal costs 9 bits; a copy of 2-5 bytes within 256 costs 12; 3-9 bytes within 8192 costs 18; 10-256 bytes within
    8192 costs 26), with matches found through up to `chain` earlier places that start with the same two bytes."""
    n = len(data)
    heads: dict = {}
    found = [(0, 0, 0, 0)] * n
    for i in range(n - 1):
        key = data[i] << 8 | data[i + 1]
        short_len = short_back = long_len = long_back = 0
        cap = min(256, n - i)
        for j in reversed(heads.get(key, ())[-chain:]):
            back = i - j
            if back > 0x2000:
                break
            if not (back <= 256 and short_len < min(5, cap)):
                if long_len == cap:
                    break
                if data[j + long_len] != data[i + long_len]:
                    continue        # cannot beat the longest found so far
            length = 2
            while length < cap and data[j + length] == data[i + length]:
                length += 1
            if back <= 256 and min(length, 5) > short_len:
                short_len, short_back = min(length, 5), back
            if length > long_len:
                long_len, long_back = length, back
            if long_len == cap and (short_len == min(5, cap) or back > 256):
                break
        heads.setdefault(key, []).append(i)
        found[i] = (short_len, short_back, long_len, long_back)
    best = [0] * (n + 1)
    step = [None] * (n + 1)
    for i in range(n - 1, -1, -1):
        cost, how = 9 + best[i + 1], None
        short_len, short_back, long_len, long_back = found[i]
        for length in range(2, short_len + 1):
            if 12 + best[i + length] < cost:
                cost, how = 12 + best[i + length], (short_back, length, True)
        for length in range(3, long_len + 1):
            c = (18 if length <= 9 else 26) + best[i + length]
            if c < cost:
                cost, how = c, (long_back, length, False)
        best[i], step[i] = cost, how
    commands, i = [], 0
    while i < n:
        how = step[i]
        if how is None:
            commands.append(((1,), bytes([data[i]])))
            i += 1
            continue
        back, length, short = how
        if short:
            k = length - 2
            commands.append(((0, 0, k >> 1, k & 1), bytes([0x100 - back])))
        else:
            off = 0x2000 - back
            lo, hi = off & 0xFF, (off >> 5) & 0xF8
            commands.append(((0, 1), bytes([lo, hi | (length - 2)]) if length <= 9 else bytes([lo, hi, length - 1])))
        i += length
    commands.append(((0, 1), b'\x00\xf0\x00'))       # the end: a long copy whose count byte is 0
    out = bytearray(2)
    desc_at, desc, used = 0, 0, 0
    for bits, body in commands:
        for b in bits:
            desc |= b << used
            used += 1
            out[desc_at], out[desc_at + 1] = desc & 0xFF, desc >> 8
            if used == 16:          # the game reads the next descriptor right away
                desc_at, desc, used = len(out), 0, 0
                out += b'\0\0'
        out += body
    return bytes(out)


class _SonicLayouts(Profile):
    """What both games share. A game class gives the tables and names."""
    system = 'genesis'
    INDEX = 0              # ROM address of the object layout index
    ZONE_STRIDE = 16       # bytes of index per zone
    ACT_STRIDE = 4         # bytes of index per act
    ACTS = 4               # index entries per zone
    REMEMBER_IN_ID = True  # Sonic 1: bit 7 of the id byte; Sonic 2: bit 15 of the y word
    GAME_MODE, LEVEL_MODE = 0xF600, 0x0C
    ZONE = 0xFE10          # zone, then act
    CAMERA = 0xF700        # camera x, then y two words on
    OBJECTS = (0xD000, 0xF000)
    MONITOR = 0x26
    RINGS = None           # object id of a ring group (Sonic 1 only)
    ZONES: dict = {}       # zone number: name, from the title cards
    PARTS: dict = {}       # (zone, act): name where it is not "<zone>, act <n>"
    ENEMIES: dict = {}     # object id: name (None: an enemy by the game's code, never pictured)
    OBJECT_NAMES: dict = {}
    CONTENTS: dict = {}    # monitor subtype: what it holds (measured)

    # ---- reading
    def list_start(self, zone: int, act: int) -> int:
        entry = self.INDEX + zone * self.ZONE_STRIDE + act * self.ACT_STRIDE
        return self.INDEX + _w(self.rom, entry)

    def records(self, zone: int, act: int) -> list:
        """[{'n', 'offset', 'x', 'y', 'flags', 'id', 'remember', 'sub'}] of one act, in the game's order."""
        at, out = self.list_start(zone, act), []
        while _w(self.rom, at) != 0xFFFF and len(out) < 1024:
            x, yword, ident, sub = _w(self.rom, at), _w(self.rom, at + 2), self.rom[at + 4], self.rom[at + 5]
            if self.REMEMBER_IN_ID:
                kind, remember, flags = ident & 0x7F, bool(ident & 0x80), yword >> 14
            else:
                kind, remember, flags = ident, bool(yword & 0x8000), (yword >> 13) & 3
            out.append({'n': len(out), 'offset': at, 'x': x, 'y': yword & 0xFFF, 'flags': flags, 'id': kind,
                        'remember': remember, 'sub': sub})
            at += 6
        return out

    def acts(self) -> list:
        return [(z, a) for z in self.ZONES for a in range(self.ACTS) if (z, a) in self.PARTS or self._plays(z, a)]

    def _plays(self, zone: int, act: int) -> bool:
        return True

    def same_list(self, zone: int, act: int) -> list:
        """Other parts that read the very same list (an edit shows there too)."""
        start = self.list_start(zone, act)
        return [(z, a) for z, a in self.acts() if (z, a) != (zone, act) and self.list_start(z, a) == start]

    def enemy_name(self, kind: int) -> str:
        return self.ENEMIES.get(kind) or f'Enemy {kind:#04x}'

    def object_name(self, kind: int) -> str:
        if kind in self.ENEMIES:
            return self.enemy_name(kind)
        return self.OBJECT_NAMES.get(kind) or f'Object {kind:#04x}'

    def contents_name(self, sub: int) -> str:
        return self.CONTENTS.get(sub) or f'Contents {sub:#04x}'

    def zone_enemies(self, zone: int) -> list:
        """Each enemy the zone uses, as the game places it: [(id, subtype)] in the order first met."""
        seen = []
        for z, a in self.acts():
            if z != zone:
                continue
            for r in self.records(z, a):
                if r['id'] in self.ENEMIES and (r['id'], r['sub']) not in seen:
                    seen.append((r['id'], r['sub']))
        return seen

    def ring_count(self, sub: int) -> int:
        return 0

    # ---- the common profile interface
    TWO_PLAYER = None

    def where(self, ram):
        if ram[self.GAME_MODE] != self.LEVEL_MODE or (self.TWO_PLAYER and _w(ram, self.TWO_PLAYER)):
            return None
        zone, act = ram[self.ZONE], ram[self.ZONE + 1]
        if (zone, act) not in self.acts():
            return None
        return {'part': {'zone': zone, 'act': act}, 'x': _w(ram, self.CAMERA), 'y': _w(ram, self.CAMERA + 4)}

    def part_name(self, part):
        zone, act = int(part['zone']), int(part['act'])
        return self.PARTS.get((zone, act)) or f'{self.ZONES.get(zone, f"Zone {zone}")}, act {act + 1}'

    def choices(self):
        out = {'contents': [{'value': k, 'name': v} for k, v in self.CONTENTS.items()]}
        for zone in self.ZONES:
            found = self.zone_enemies(zone)
            kinds = [kind for kind, _ in found]
            # an enemy the zone places with more than one setting (a different way of moving) lists each one
            out[f'enemies_{zone}'] = [{'value': kind << 8 | sub, 'name': self.enemy_name(kind) + (f' (setting {sub})' if kinds.count(kind) > 1 else '')}
                                      for kind, sub in found]
        if self.RINGS is not None:
            out['ring_counts'] = [{'value': n, 'name': f'{n + 1} {"ring" if n == 0 else "rings"}'} for n in range(7)]
        return out

    def objects(self, part):
        zone, act = int(part['zone']), int(part['act'])
        shared = self.same_list(zone, act)
        out = []
        for r in self.records(zone, act):
            kind = r['id']
            row = {'id': f'object:{r["n"]}', 'type': kind, 'x': r['x'], 'y': r['y'] + 16, 'name': self.object_name(kind),
                   'remove': None, 'fields': [], 'style': 'block'}
            if kind in self.ENEMIES:
                row.update(style='enemy', remove='Remove this enemy',
                           fields=[{'key': 'enemy', 'label': 'Swap for', 'value': kind << 8 | r['sub'], 'choices': f'enemies_{zone}'}])
            elif kind == self.MONITOR:
                row.update(style='item', detail=f'holds {self.contents_name(r["sub"]).lower()}', remove='Remove this monitor',
                           fields=[{'key': 'contents', 'label': 'Holds', 'value': r['sub'], 'choices': 'contents'}])
                if r['sub'] not in self.CONTENTS:
                    row['fields'] = []
            elif kind == self.RINGS:
                count = self.ring_count(r['sub'])
                row.update(style='item', name='Rings', detail=f'a row of {count}', remove='Remove these rings',
                           fields=[{'key': 'count', 'label': 'Rings in the row', 'value': min(r['sub'] & 7, 6), 'choices': 'ring_counts'}])
            if shared and (row['fields'] or row['remove']):
                names = ' and '.join(self.part_name({'zone': z, 'act': a}) for z, a in shared)
                row['note'] = f'{names} uses the same list of objects, so a change here shows there too.'
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        zone, act = int(part['zone']), int(part['act'])
        kind_text, _, number = str(object_id).partition(':')
        rows = self.records(zone, act)
        if kind_text != 'object' or not number.isdigit() or int(number) >= len(rows):
            raise ValueError('That is not part of this act any more. Reopen the map.')
        r = rows[int(number)]
        idb, subb = r['offset'] + 4, r['offset'] + 5
        keep = self.rom[idb] & 0x80 if self.REMEMBER_IN_ID else 0
        writes, watch = [], {'zone': zone, 'act': act, 'x': r['x'], 'y': r['y'], 'old': r['id'], 'old_sub': r['sub']}
        if remove:
            if r['id'] not in self.ENEMIES and r['id'] not in (self.MONITOR, self.RINGS):
                raise ValueError('That cannot be removed.')
            writes.append((idb, self.rom[idb], keep))
            title = f'Remove: {self.object_name(r["id"]) if r["id"] != self.RINGS else "Rings"}'
            watch.update(kind='gone')
        elif r['id'] in self.ENEMIES:
            value = int(values['enemy'])
            kind, sub = value >> 8, value & 0xFF
            if (kind, sub) not in self.zone_enemies(zone):
                raise ValueError('That choice is not one of the game’s own.')
            writes += [(idb, self.rom[idb], keep | kind), (subb, self.rom[subb], sub)]
            title = f'Enemy here: {self.enemy_name(kind)}'
            watch.update(kind='enemy', id=kind, sub=sub, name=self.enemy_name(kind))
        elif r['id'] == self.MONITOR:
            sub = int(values['contents'])
            if sub not in self.CONTENTS:
                raise ValueError('That choice is not one of the game’s own.')
            writes.append((subb, self.rom[subb], sub))
            title = f'Monitor holds: {self.contents_name(sub)}'
            watch.update(kind='monitor', sub=sub, name=self.contents_name(sub))
        elif r['id'] == self.RINGS:
            count = int(values['count'])
            if not 0 <= count <= 6:
                raise ValueError('That choice is not one of the game’s own.')
            writes.append((subb, self.rom[subb], (self.rom[subb] & 0xF8) | count))
            title = f'Rings in the row: {count + 1}'
            watch.update(kind='rings', count=count + 1)
        else:
            raise ValueError('ROMancer cannot change that yet.')
        game = {'zone': self.ZONE, 'mode': self.GAME_MODE, 'level': self.LEVEL_MODE, 'camera': self.CAMERA, 'objects': self.OBJECTS,
                'monitor': self.MONITOR, 'rings': self.RINGS}
        watch.update(game=game)
        return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'{title} ({self.part_name(part)}, x {r["x"]})', 'watch': watch}

    def watcher(self, watch):
        if watch.get('kind') == 'layout':
            return _LayoutWatcher(watch)
        return _ObjectWatcher(watch)

    # ---- chunk layouts (a game class gives layout_start, layout_of and layout_writes)
    CHUNK = 256                 # pixels a chunk
    LAYOUT_RAM = 0xA400         # where the foreground layout sits in RAM
    LAYOUT_ROW = 0x80           # RAM bytes a row

    def layout_start(self, zone: int, act: int) -> int:
        raise NotImplementedError

    def layout_of(self, zone: int, act: int) -> dict:
        """{'width', 'height', 'blocks', ...}: the foreground as the game has it in RAM after loading the act."""
        raise NotImplementedError

    def layout_writes(self, zone: int, act: int, grid: dict, blocks: list) -> list:
        raise NotImplementedError

    def same_layout(self, zone: int, act: int) -> list:
        start = self.layout_start(zone, act)
        return [(z, a) for z, a in self.acts() if (z, a) != (zone, act) and self.layout_start(z, a) == start]

    def zone_chunks(self, zone: int) -> set:
        """Every chunk number the zone's own acts place (a zone's chunks are loaded in each of its acts)."""
        out = set()
        for z, a in self.acts():
            if z == zone:
                out.update(self.layout_of(z, a)['blocks'])
        return out

    def packed_layout(self, part):
        zone, act = int(part['zone']), int(part['act'])
        if (zone, act) not in self.acts():
            return None
        grid = self.layout_of(zone, act)
        return {'size': self.CHUNK, 'width': grid['width'], 'height': grid['height'], 'blocks': list(grid['blocks']),
                'left': 0, 'top': 0}

    def set_packed_layout(self, part, changes):
        zone, act = int(part['zone']), int(part['act'])
        if (zone, act) not in self.acts():
            raise ValueError('That part of the game has no layout ROMancer can change.')
        grid = self.layout_of(zone, act)
        allowed = self.zone_chunks(zone)
        blocks = list(grid['blocks'])
        places = []
        for column, row, block in changes:
            column, row, block = int(column), int(row), int(block)
            if not (0 <= column < grid['width'] and 0 <= row < grid['height']):
                raise ValueError('That place is outside the act’s layout.')
            if block not in allowed:
                raise ValueError('That chunk is not one this zone uses.')
            at = row * grid['width'] + column
            if blocks[at] != block:
                if any(p[:2] == [column, row] for p in places):
                    raise ValueError('Each place can take one chunk at a time.')
                places.append([column, row, block, blocks[at]])
                blocks[at] = block
        if not places:
            raise ValueError('Those places already look like that. Paint a different picture first.')
        writes = self.layout_writes(zone, act, grid, blocks)
        shared = self.same_layout(zone, act)
        title = f'Layout: {len(places)} {"chunk" if len(places) == 1 else "chunks"} changed ({self.part_name(part)})'
        if shared:
            names = ' and '.join(self.part_name({'zone': z, 'act': a}) for z, a in shared)
            title += f'; {names} {"uses" if len(shared) == 1 else "use"} the same layout'
        watch = {'kind': 'layout', 'zone': zone, 'act': act, 'places': places, 'ram': self.LAYOUT_RAM, 'row': self.LAYOUT_ROW,
                 'mode': self.GAME_MODE, 'level': self.LEVEL_MODE, 'zone_at': self.ZONE}
        return {'writes': writes, 'title': title, 'watch': watch}


class _ObjectWatcher(Watcher):
    """Looks through the object slots of the replayed game for the object that the changed record places.

    An object is matched by id near the record's place (enemies move, so within 48 pixels across and 64 up or down;
    monitors and rings do not move, so exactly). A removal counts once the place has been inside the
    loader's window (128 pixels left of the camera to 640 right) for 60 frames and nothing of the old kind showed up."""
    every = 2

    def __init__(self, watch):
        self.w = watch
        self.seen = None        # what was found at the place
        self.over = 0           # looks with the camera over the place
        self.rings = set()

    def _near(self, ram, kinds, exact):
        g = self.w['game']
        start, end = g['objects']
        for slot in range(start, end, 0x40):
            kind = ram[slot]
            if kind not in kinds:
                continue
            x, y = _w(ram, slot + 8), _w(ram, slot + 0xC)
            if exact and (x, y) == (self.w['x'], self.w['y']):
                return slot
            if not exact and abs(x - self.w['x']) <= 48 and abs(y - self.w['y']) <= 64:
                return slot
        return None

    def see(self, ram, frame, run):
        w, g = self.w, self.w['game']
        if ram[g['mode']] != g['level'] or (ram[g['zone']], ram[g['zone'] + 1]) != (w['zone'], w['act']):
            return False
        cx = _w(ram, g['camera'])
        # the loaders keep objects from 128 pixels left of the camera to 640 right of it (Sonic 1 $D930, Sonic 2 alike);
        # an object stays once loaded, whatever the camera height
        loaded = cx - 0x80 <= w['x'] < cx + 0x280
        kind = w['kind']
        if kind == 'monitor':
            slot = self._near(ram, {g['monitor']}, True)
            if slot is not None:
                self.seen = ram[slot + 0x28]
                return True
            return False
        if kind == 'rings':
            start, end = g['objects']
            for slot in range(start, end, 0x40):
                if ram[slot] == g['rings'] and _w(ram, slot + 0x32) == w['x'] and abs(_w(ram, slot + 0xC) - w['y']) <= 0x100:
                    self.rings.add(ram[slot + 0x34])
            if self.rings:
                self.seen = len(self.rings)
                return True
            return False
        if kind == 'enemy':
            slot = self._near(ram, {w['id'], w['old']}, False)
            if slot is not None:
                self.seen = ram[slot]
                return ram[slot] == w['id']
            return False
        # a removal: the old kind of object must never show at the place
        old = {w['old']}
        slot = self._near(ram, old, w['old'] in (g['monitor'], g['rings']))
        if w['old'] == g['rings']:
            start, end = g['objects']
            slot = next((s for s in range(start, end, 0x40) if ram[s] == g['rings'] and _w(ram, s + 0x32) == w['x']), None)
        if slot is not None:
            self.seen = ram[slot]
            return True
        if loaded:
            self.over += 1
        return self.over >= 30

    def result(self):
        w, seen = self.w, self.seen
        kind = w['kind']
        if kind == 'gone':
            if seen is not None:
                return {'state': 'bad', 'text': 'Played from the start, the object still appears there.'}
            if self.over >= 30:
                return {'state': 'good', 'text': 'Played from the start, nothing appears there any more.'}
            return super().result()
        if seen is None:
            return super().result()
        if kind == 'monitor':
            ok = seen == w['sub']
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the monitor there now holds {w["name"].lower()}.' if ok
                    else f'Played from the start, the monitor there holds contents {seen:#04x}, not the one chosen.'}
        if kind == 'rings':
            ok = seen == w['count']
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the row there now has {seen} rings.' if ok
                    else f'Played from the start, the row there has {seen} rings, not the {w["count"]} chosen.'}
        ok = seen == w['id']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game now places {w["name"]} there.' if ok
                else f'Played from the start, the game placed object {seen:#04x} there, not what was chosen.'}


class _LayoutWatcher(Watcher):
    """Reads the chunk numbers at the changed places in the layout the replayed game built in RAM once the act is
    playing (the act loads its layout before play starts); two looks in a row must agree."""

    def __init__(self, watch):
        self.w, self.seen, self.last = watch, None, None

    def see(self, ram, frame, run):
        w = self.w
        if ram[w['mode']] != w['level'] or (ram[w['zone_at']], ram[w['zone_at'] + 1]) != (w['zone'], w['act']):
            self.last = None
            return False
        now = [ram[w['ram'] + row * w['row'] + column] for column, row, _, _ in w['places']]
        if now == self.last:
            self.seen = now
            return True
        self.last = now
        return False

    def result(self):
        if self.seen is None:
            return super().result()
        places = self.w['places']
        right = sum(1 for got, place in zip(self.seen, places) if got == place[2])
        if right == len(places):
            return {'state': 'good', 'text': 'Played from the start, the game builds the act with the new '
                                             f'{"chunk" if right == 1 else "chunks"} there.'}
        got, new = next((got, place[2]) for got, place in zip(self.seen, places) if got != place[2])
        if len(places) == 1:
            return {'state': 'bad', 'text': f'Played from the start, that place holds chunk {got:#04x}, not the chosen {new:#04x}.'}
        return {'state': 'bad', 'text': f'Played from the start, {len(places) - right} of {len(places)} places hold another '
                                        f'chunk (chunk {got:#04x} where {new:#04x} was chosen).'}


class Sonic1(_SonicLayouts):
    """Sonic The Hedgehog (USA, Europe). Object loader $D8F0; index $6B000, two words per act (the second list is empty)."""
    name = 'Sonic The Hedgehog'
    sha256s = ('46160baa06362c711c9f1a5017cb7371026444936c8af5e93a78996cf32ff2a6',)
    INDEX, ZONE_STRIDE, ACT_STRIDE, ACTS = 0x6B000, 16, 4, 4
    REMEMBER_IN_ID = True
    CAMERA = 0xF700
    OBJECTS = (0xD800, 0xF000)
    RINGS = 0x25
    # title cards (trace/v15_profiles/megadrive_sonic/shots/s1_cards.png)
    ZONES = {0: 'Green Hill Zone', 1: 'Labyrinth Zone', 2: 'Marble Zone', 3: 'Star Light Zone', 4: 'Spring Yard Zone',
             5: 'Scrap Brain Zone'}
    PARTS = {(1, 3): 'Scrap Brain Zone, act 3', (5, 2): 'Final Zone'}
    # Enemies: touch type $01-$3F (or $C0+) set by the object's own code, and pictured by spawning each in its zone
    # (shots/s1_sheet_all.png, s1_objects_sheet_some.png). 0x43 is an enemy by its code but never showed when spawned.
    ENEMIES = {0x1E: 'Ball Hog', 0x1F: 'Crabmeat', 0x22: 'Buzz Bomber', 0x2B: 'Chopper', 0x2C: 'Jaws', 0x2D: 'Burrobot',
               0x40: 'Moto Bug', 0x42: 'Newtron', 0x43: None, 0x50: 'Yadrin', 0x55: 'Basaran', 0x5F: 'Bomb',
               0x60: 'Orbinaut', 0x78: 'Caterkiller'}
    # pictured by spawning (shots/s1_sheet_all.png); the rest show their number
    OBJECT_NAMES = {0x0D: 'Signpost (end of the act)', 0x11: 'Bridge', 0x15: 'Swinging platform', 0x18: 'Platform',
                    0x25: 'Rings', 0x26: 'Monitor', 0x31: 'Chained stomper', 0x33: 'Pushable block', 0x36: 'Spikes',
                    0x3B: 'Rock', 0x41: 'Spring', 0x62: 'Gargoyle head', 0x6D: 'Flamethrower', 0x79: 'Lamppost'}
    # measured by breaking a monitor with each number (trace/v15_profiles/megadrive_sonic/mon1.py)
    CONTENTS = {2: 'Extra life', 3: 'Speed shoes', 4: 'Shield', 5: 'Invincibility', 6: 'Ten rings'}

    def _plays(self, zone, act):
        # acts 1-3 of each zone; Labyrinth's fourth list is Scrap Brain act 3, and Scrap Brain's third is the Final Zone
        return act < 3 or (zone, act) == (1, 3)

    def ring_count(self, sub):
        n = sub & 7                     # $9B6E: low 3 bits are the extra rings, 7 is read as 6
        return (6 if n == 7 else n) + 1

    LAYOUT_INDEX = 0x68BD6      # $6D32: (zone * 4 + act) * 6, then the foreground's signed word offset from the index

    def layout_start(self, zone, act):
        offset = _w(self.rom, self.LAYOUT_INDEX + (zone * 4 + act) * 6)
        return self.LAYOUT_INDEX + (offset - 0x10000 if offset & 0x8000 else offset)

    def layout_of(self, zone, act):
        at = self.layout_start(zone, act)
        stride = self.rom[at] + 1
        # the game copies each row into $80 bytes of RAM, the background $40 on, after clearing $800 bytes ($6D12)
        width, height = min(stride, 0x40), min(self.rom[at + 1] + 1, 16)
        return {'width': width, 'height': height, 'stride': stride, 'at': at + 2,
                'blocks': [self.rom[at + 2 + r * stride + c] for r in range(height) for c in range(width)]}

    def layout_writes(self, zone, act, grid, blocks):
        out = []
        for n, block in enumerate(blocks):
            at = grid['at'] + (n // grid['width']) * grid['stride'] + n % grid['width']
            if self.rom[at] != block:
                out.append((at, self.rom[at], block))
        return out


class _RingWatcher(Watcher):
    """A ring row edit (Sonic 2): the game lays every ring of the act out in its ring table ($E806, 6 bytes each: state,
    x, y) when the act starts, so the row is counted there."""

    def __init__(self, watch):
        self.w, self.seen = watch, None

    def see(self, ram, frame, run):
        w = self.w
        if ram[w['mode']] != w['level'] or (ram[w['zone']], ram[w['zone'] + 1]) != (w['zone_n'], w['act']):
            return False
        places = set()
        for n in range(255):
            at = w['table'] + 6 * n
            places.add((_w(ram, at + 2), _w(ram, at + 4)))
        count = 0
        while count < 8 and ((w['x'], w['y'] + 0x18 * count) if w['vertical'] else (w['x'] + 0x18 * count, w['y'])) in places:
            count += 1
        self.seen = count
        return True

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return super().result()
        if w['count'] == 0:
            ok = seen == 0
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, the row of rings is gone.' if ok
                    else 'Played from the start, the row of rings is still there.'}
        ok = seen == w['count']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the row there now has {seen} rings.' if ok
                else f'Played from the start, the row there has {seen} rings, not the {w["count"]} chosen.'}


class Sonic2(_SonicLayouts):
    """Sonic The Hedgehog 2 (World) (Rev B). Object loader $17A2A (index $E6800, one word per act, two acts a zone; the
    two-player Casino Night lists at $17F98 and $18400 are left alone). Rings are not objects here: ring loader $17238,
    index $E4300, 4 bytes a row (x; y with the count less one in bits 12-14 and bit 15 for a column), 24 pixels apart."""
    name = 'Sonic The Hedgehog 2'
    sha256s = ('568e5e9557c4c1ef67305fcda429ce503149144e80de6f9aba80e709a8fcde66',)
    INDEX, ZONE_STRIDE, ACT_STRIDE, ACTS = 0xE6800, 4, 2, 2
    REMEMBER_IN_ID = False
    CAMERA = 0xEE00
    OBJECTS = (0xB400, 0xD000)
    RING_INDEX = 0xE4300
    RING_TABLE = 0xE806
    RING_MOST = 255         # the ring table holds 255 rings ($172AC sorts that many)
    TWO_PLAYER = 0xFFB8     # two-player mode reads other lists for Casino Night, so it is left out
    # title cards (trace/v15_profiles/megadrive_sonic/shots/s2_cards.png)
    ZONES = {0: 'Emerald Hill Zone', 4: 'Metropolis Zone', 5: 'Metropolis Zone', 6: 'Wing Fortress Zone', 7: 'Hill Top Zone',
             8: 'Hidden Palace Zone', 10: 'Oil Ocean Zone', 11: 'Mystic Cave Zone', 12: 'Casino Night Zone',
             13: 'Chemical Plant Zone', 14: 'Death Egg Zone', 15: 'Aquatic Ruin Zone', 16: 'Sky Chase Zone'}
    PARTS = {(5, 0): 'Metropolis Zone, act 3', (6, 0): 'Wing Fortress Zone', (8, 0): 'Hidden Palace Zone',
             (14, 0): 'Death Egg Zone', (16, 0): 'Sky Chase Zone'}
    PLAYED = ((0, 0), (0, 1), (4, 0), (4, 1), (5, 0), (6, 0), (7, 0), (7, 1), (8, 0), (10, 0), (10, 1), (11, 0), (11, 1),
              (12, 0), (12, 1), (13, 0), (13, 1), (14, 0), (15, 0), (15, 1), (16, 0))
    # Enemies: touch type read from the spawned object's RAM ($20) or set by its code, and pictured by spawning each
    # in its zone (shots/s2_enemies.png, s2_masher.png). 0x50, 0x8D, 0x95 and 0x9E are enemies by touch type but
    # never showed in a picture.
    ENEMIES = {0x4A: 'Octus', 0x4B: 'Buzzer', 0x50: None, 0x5C: 'Masher', 0x8C: 'Whisp', 0x8D: None, 0x8E: 'Grounder',
               0x91: 'Chop Chop', 0x92: 'Spiker', 0x95: None, 0x96: 'Rexon', 0x99: 'Nebula', 0x9A: 'Turtloid',
               0x9D: 'Coconuts', 0x9E: None, 0x9F: 'Shellcracker', 0xA1: 'Slicer', 0xA3: 'Flasher', 0xA4: 'Asteron',
               0xA5: 'Spiny', 0xA6: 'Spiny (on a wall)', 0xA7: 'Grabber', 0xAC: 'Balkiry', 0xAE: 'Clucker', 0xC8: 'Crawl'}
    OBJECT_NAMES = {0x11: 'Bridge', 0x26: 'Monitor'}
    # measured by breaking a monitor with each number (trace/v15_profiles/megadrive_sonic/mon2.py)
    CONTENTS = {1: 'Extra life', 4: 'Ten rings', 5: 'Speed shoes', 6: 'Shield', 7: 'Invincibility'}

    def _plays(self, zone, act):
        return (zone, act) in self.PLAYED

    def ring_groups(self, zone: int, act: int) -> list:
        entry = self.RING_INDEX + zone * 4 + act * 2
        at, out = self.RING_INDEX + _w(self.rom, entry), []
        while _w(self.rom, at) != 0xFFFF and len(out) < 512:
            yword = _w(self.rom, at + 2)
            out.append({'n': len(out), 'offset': at, 'x': _w(self.rom, at), 'y': yword & 0xFFF, 'count': (yword >> 12 & 7) + 1,
                        'vertical': bool(yword & 0x8000)})
            at += 4
        return out

    def choices(self):
        out = super().choices()
        out['ring_counts'] = [{'value': n, 'name': f'{n + 1} {"ring" if n == 0 else "rings"}'} for n in range(8)]
        return out

    def objects(self, part):
        out = super().objects(part)
        zone, act = int(part['zone']), int(part['act'])
        for g in self.ring_groups(zone, act):
            out.append({'id': f'rings:{g["n"]}', 'type': 'rings', 'style': 'item', 'name': 'Rings',
                        'x': g['x'] + (0 if g['vertical'] else 0x18 * (g['count'] - 1) // 2),
                        'y': g['y'] + (0x18 * (g['count'] - 1) if g['vertical'] else 0) + 8,
                        'detail': f'a {"column" if g["vertical"] else "row"} of {g["count"]}', 'remove': 'Remove these rings',
                        'fields': [{'key': 'count', 'label': 'Rings in the row', 'value': g['count'] - 1, 'choices': 'ring_counts'}]})
        return out

    def edit(self, part, object_id, values, remove=False):
        if not str(object_id).startswith('rings:'):
            return super().edit(part, object_id, values, remove)
        zone, act = int(part['zone']), int(part['act'])
        groups = self.ring_groups(zone, act)
        number = str(object_id)[6:]
        if not number.isdigit() or int(number) >= len(groups):
            raise ValueError('That is not part of this act any more. Reopen the map.')
        g = groups[int(number)]
        watch = {'zone_n': zone, 'act': act, 'x': g['x'], 'y': g['y'], 'vertical': g['vertical'], 'table': self.RING_TABLE,
                 'zone': self.ZONE, 'mode': self.GAME_MODE, 'level': self.LEVEL_MODE}
        if remove:
            # close the list up over this row: the rest moves 4 bytes down and the list ends one row sooner
            start, end = g['offset'], groups[-1]['offset'] + 4
            new = self.rom[start + 4:end] + b'\xff\xff'
            writes = [(start + i, self.rom[start + i], b) for i, b in enumerate(new) if self.rom[start + i] != b]
            watch['count'] = 0
            title = 'Remove the rings'
        else:
            count = int(values['count'])
            if not 0 <= count <= 7:
                raise ValueError('That choice is not one of the game’s own.')
            total = sum(x['count'] for x in groups) - g['count'] + count + 1
            if total > self.RING_MOST:
                raise ValueError(f'The game can hold {self.RING_MOST} rings in an act, and this would make {total}.')
            at = g['offset'] + 2
            writes = [(at, self.rom[at], (self.rom[at] & 0x8F) | count << 4)]
            watch['count'] = count + 1
            title = f'Rings in the row: {count + 1}'
        return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'{title} ({self.part_name(part)}, x {g["x"]})', 'watch': watch}

    CHUNK = 128
    LAYOUT_RAM, LAYOUT_ROW = 0x8000, 0x100
    LAYOUT_INDEX = 0x45A80      # $E42C: (zone * 2 + act) * 2, an unsigned word offset forward from the index

    def layout_start(self, zone, act):
        return self.LAYOUT_INDEX + _w(self.rom, self.LAYOUT_INDEX + (zone * 2 + act) * 2)

    def layout_room(self, start: int) -> int:
        """Bytes the layout at start may use: up to the next layout the index points at; the last one up to its end
        rounded up to 16 bytes (the layouts are padded to 16)."""
        starts = sorted({self.layout_start(z, a) for z in range(17) for a in range(2)})
        later = [s for s in starts if s > start]
        if later:
            return later[0] - start
        used = kos_decode(self.rom, start)[1]
        return (start + used + 15) // 16 * 16 - start

    def layout_of(self, zone, act):
        data = kos_decode(self.rom, self.layout_start(zone, act))[0]
        rows = min(16, len(data) // 0x100)
        return {'width': 0x80, 'height': rows, 'data': data,
                'blocks': [data[r * 0x100 + c] for r in range(rows) for c in range(0x80)]}

    def layout_writes(self, zone, act, grid, blocks):
        data = bytearray(grid['data'])
        for n, block in enumerate(blocks):
            data[(n // 0x80) * 0x100 + n % 0x80] = block
        data = bytes(data)
        start = self.layout_start(zone, act)
        room = self.layout_room(start)
        packed = b''
        for chain in (48, 320, 2048):       # quick first, harder only when it does not fit
            packed = kos_encode(data, chain)
            if len(packed) <= room:
                break
        if len(packed) > room:
            raise ValueError(f'The new layout packs to {len(packed)} bytes and only {room} fit where it was. The game '
                             'cannot reach any free space, so try fewer or plainer chunks.')
        if kos_decode(packed) != (data, len(packed)):
            raise ValueError('ROMancer could not pack that layout correctly.')
        new = packed + bytes(room - len(packed))
        return [(start + i, self.rom[start + i], b) for i, b in enumerate(new) if self.rom[start + i] != b]

    def watcher(self, watch):
        if 'table' in watch:
            return _RingWatcher(watch)
        return super().watcher(watch)


PROFILES = [Sonic1, Sonic2]
