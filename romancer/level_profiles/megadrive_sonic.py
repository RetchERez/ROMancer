"""Sonic The Hedgehog and Sonic The Hedgehog 2 (Mega Drive): the object layout of every act.

The level layouts are compressed, so blocks stay with the general level map tools. Each act has a plain list of the
objects placed in it, 6 bytes each, sorted by x and ended by x = $FFFF:

    x (word), y (word: low 12 bits y, two flip bits above), object id (byte), subtype (byte)

Sonic 1 marks an object the game remembers (a broken monitor stays broken) with bit 7 of the id byte; Sonic 2 marks it
with bit 15 of the y word. Edits change the id and subtype bytes of one record in place, so nothing moves: a swap writes
another enemy's id and subtype as the game uses them in the same zone (so its graphics are loaded there), and a removal
writes object id 0, which the object loader places as an empty slot. Worked out from the games' own loaders (Sonic 1
$D8F0 and $DA56, Sonic 2 $17AA4 and $17F84) and proven by replaying the game; see research/megadrive_sonic-level-profile.md.

RAM: snapshots give work RAM as 'wram', index 0 = $FF0000, words big-endian (68000 order).
"""
from __future__ import annotations

from . import Profile, Watcher


def _w(data, at: int) -> int:
    return data[at] << 8 | data[at + 1]


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
        return _ObjectWatcher(watch)


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

    def watcher(self, watch):
        if 'table' in watch:
            return _RingWatcher(watch)
        return super().watcher(watch)


PROFILES = [Sonic1, Sonic2]
