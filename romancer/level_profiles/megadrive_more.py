"""Sonic 3 & Knuckles and Castlevania: Bloodlines (Mega Drive): the object layouts of their levels.

Sonic & Knuckles + Sonic The Hedgehog 3 (the locked-on cartridge, 4 MiB; the Sonic & Knuckles half runs it). Each act has
a plain list of 6-byte object records sorted by x and ended by x = $FFFF:

    x (word), y (word: low 12 bits y, bits 13-14 flip, bit 15 "load whatever the camera height"), id (byte), subtype (byte)

found through the long pointer table at $1E3D98 (two acts a zone: `ror.b #1; lsr.w #5` of the zone and act word, code at
$1B6E8). The object loader ($1B79E-$1BAF0) turns the id into a code address through one of two 256-entry tables,
$94EA2 for the Sonic 3 zones (0-6) and $952A2 for the Sonic & Knuckles zones (7 and up, code at $1B6A8), and keeps one
byte per record in the respawn table at $FFEB00 (record n uses $FFEB00 + n; the slot remembers that address at +$48).
Rings are not objects: each act has a list of single rings at the pointer table $1E3E58, 4 bytes a ring (x, y) after a
4-byte header, ended by x = $FFFF; the game counts them into $FFFF04 when the act starts (code $EB52).

Castlevania: Bloodlines (USA). Each room has a list of 8-byte records sorted by x between an $8000 record and a $7FFF
record, found through the word offset table at $4BA3C indexed by the room number ($FF9122); code at $33B6E:

    x (word), kind (byte), setting (byte), y (word), extra (byte), flags (byte: bits 0-2 slot group, bits 3-4 the lowest
    difficulty that places it, bit 5 the game remembers it once destroyed, bit 7 placed from the left)

The spawner at $3356E places a record when the right edge (camera x + $160) reaches its x.

Worked out from the games' own code and proven by replaying the games; see research/megadrive_more-level-profile.md.
RAM: snapshots give work RAM as 'wram', index 0 = $FF0000, words big-endian (68000 order).
"""
from __future__ import annotations

from . import Profile, Watcher


def _w(data, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def _l(data, at: int) -> int:
    return _w(data, at) << 16 | _w(data, at + 2)


# ---------------------------------------------------------------------------------------------------------------------
# Sonic 3 & Knuckles

class Sonic3K(Profile):
    """Sonic & Knuckles + Sonic The Hedgehog 3 (USA)."""
    name = 'Sonic 3 & Knuckles'
    sha256s = ('fba0677fde9f76df93f3e98d6310d8af68b9847bde16e253d73cd4dd8134ed23',)
    system = 'genesis'
    OBJ_INDEX = 0x1E3D98         # long pointer per act, two acts a zone
    RING_INDEX = 0x1E3E58
    TABLE_S3, TABLE_SK = 0x94EA2, 0x952A2
    GAME_MODE, LEVEL_MODE = 0xF600, 0x0C
    ZONE = 0xFE10                # zone, then act
    CAMERA = 0xEE78              # camera x, then y 4 bytes on
    HSCROLL = 0xF000             # the scroll table in video memory: line 0, plane A (minus the camera x the picture used)
    SLOTS = (0xB0DE, 0xB0DE + 0x4A * 90)     # dynamic object slots, $4A bytes each ($1BAF2)
    RESPAWN = 0xEB00
    RING_START = 0xEE42          # ROM address of the first ring in the loaded window, then the end ($EB86)
    MONITOR = 0x01
    # title cards, read after loading each act (trace/v15_profiles/megadrive_more/shots/s3k_cards.png)
    ZONES = {0: 'Angel Island Zone', 1: 'Hydrocity Zone', 2: 'Marble Garden Zone', 3: 'Carnival Night Zone',
             4: 'Flying Battery Zone', 5: 'IceCap Zone', 6: 'Launch Base Zone', 7: 'Mushroom Hill Zone',
             8: 'Sandopolis Zone', 9: 'Lava Reef Zone', 0xA: 'Sky Sanctuary Zone', 0xB: 'Death Egg Zone',
             0xC: 'The Doomsday Zone', 0x16: 'Lava Reef Zone'}
    PARTS = {(0xA, 0): 'Sky Sanctuary Zone', (0xC, 0): 'The Doomsday Zone', (0x16, 0): 'Lava Reef Zone, act 2 (last part)',
             (0x16, 1): 'Hidden Palace Zone'}
    PLAYED = tuple((z, a) for z in range(0xC) for a in range(2) if (z, a) != (0xA, 1)) + ((0xC, 0), (0x16, 0), (0x16, 1))
    # Enemies: touch type $01-$3F (or $C0 and up) read from the spawned object's RAM (+$28), and pictured by spawning
    # each in its own act (shots/shs_0.png - shs_4.png). Only enemies whose picture is clear are named and editable.
    ENEMIES_S3 = {0x8C: 'Bloominator', 0x8D: 'Rhinobot', 0x8E: 'Monkey Dude', 0x8F: 'Caterkiller Jr', 0x94: 'Blastoid',
                  0x97: 'Jawz', 0x98: 'Pointdexter', 0x9B: 'Bubbles', 0x9C: 'Spiker', 0x9D: 'Mantis', 0x9E: 'Tunnelbot',
                  0xA3: 'Clamer', 0xA4: 'Sparkle', 0xA5: 'Batbot', 0xA8: 'Blaster', 0xA9: 'Technosqueek',
                  0xAD: 'Penguinator', 0xAE: 'Star Pointer', 0xBF: 'Snale Blaster', 0xC0: 'Orbinaut', 0xC1: 'Ribot',
                  0xC2: 'Flybot767'}
    ENEMIES_SK = {0x8D: 'Mushmeanie', 0x8E: 'Madmole', 0x8F: 'Dragonfly', 0x90: 'Cluckoid'}
    # measured by breaking a monitor with each number (trace/v15_profiles/megadrive_more/mon3k.py)
    CONTENTS = {1: 'Extra life', 2: 'Hurts the player', 3: 'Ten rings', 4: 'Speed shoes', 5: 'Fire shield',
                6: 'Lightning shield', 7: 'Bubble shield', 8: 'Invincibility'}

    # ---- reading
    def table(self, zone: int) -> int:
        return self.TABLE_SK if (zone >= 0x16 or 7 <= zone < 0xE) else self.TABLE_S3

    def enemies(self, zone: int) -> dict:
        return self.ENEMIES_SK if self.table(zone) == self.TABLE_SK else self.ENEMIES_S3

    def code_range(self, zone: int, kind: int) -> list:
        """[start, end) of an object's code: from its table entry to the next higher entry of the same table."""
        base = self.table(zone)
        entries = sorted({_l(self.rom, base + 4 * i) for i in range(256)})
        start = _l(self.rom, base + 4 * kind)
        later = [e for e in entries if e > start]
        return [start, later[0] if later else start + 0x1000]

    def list_start(self, zone: int, act: int) -> int:
        return _l(self.rom, self.OBJ_INDEX + zone * 8 + act * 4)

    def records(self, zone: int, act: int) -> list:
        at, out = self.list_start(zone, act), []
        while _w(self.rom, at) != 0xFFFF and len(out) < 1024:
            yword = _w(self.rom, at + 2)
            out.append({'n': len(out), 'offset': at, 'x': _w(self.rom, at), 'y': yword & 0xFFF, 'yword': yword,
                        'id': self.rom[at + 4], 'sub': self.rom[at + 5]})
            at += 6
        return out

    def ring_start(self, zone: int, act: int) -> int:
        return _l(self.rom, self.RING_INDEX + zone * 8 + act * 4)

    def rings(self, zone: int, act: int) -> list:
        at, out = self.ring_start(zone, act) + 4, []
        while _w(self.rom, at) != 0xFFFF and len(out) < 0x200:
            out.append({'n': len(out), 'offset': at, 'x': _w(self.rom, at), 'y': _w(self.rom, at + 2)})
            at += 4
        return out

    def same_list(self, zone, act):
        start = self.list_start(zone, act)
        return [(z, a) for z, a in self.PLAYED if (z, a) != (zone, act) and self.list_start(z, a) == start]

    def act_enemies(self, zone: int, act: int) -> list:
        names, seen = self.enemies(zone), []
        for r in self.records(zone, act):
            if r['id'] in names and (r['id'], r['sub']) not in seen:
                seen.append((r['id'], r['sub']))
        return seen

    def contents_name(self, sub):
        return self.CONTENTS.get(sub) or f'Contents {sub:#04x}'

    # ---- interface
    def where(self, ram):
        if ram[self.GAME_MODE] != self.LEVEL_MODE:
            return None
        zone, act = ram[self.ZONE], ram[self.ZONE + 1]
        if (zone, act) not in self.PLAYED:
            return None
        x, y = _w(ram, self.CAMERA), _w(ram, self.CAMERA + 4)
        # The picture of a frame is drawn with the scroll the game set one frame earlier, while the camera in RAM has
        # already moved on (by up to 16 pixels at full speed). The scroll the picture used is in video memory: the
        # first line of the scroll table at $F000 holds minus the camera x, and the first scroll word the camera y.
        domains = getattr(ram, 'domains', None) or {}
        vram, vsram = domains.get('vram'), domains.get('vsram')
        if vram is not None and len(vram) >= self.HSCROLL + 2 and vsram is not None and len(vsram) >= 2:
            shown_x, shown_y = -_w(vram, self.HSCROLL) & 0xFFFF, _w(vsram, 0)
            if abs(shown_x - x) <= 32 and abs(shown_y - y) <= 32:
                x, y = shown_x, shown_y
        return {'part': {'zone': zone, 'act': act}, 'x': x, 'y': y}

    def part_name(self, part):
        zone, act = int(part['zone']), int(part['act'])
        return self.PARTS.get((zone, act)) or f'{self.ZONES.get(zone, f"Zone {zone}")}, act {act + 1}'

    def choices(self):
        out = {'contents': [{'value': k, 'name': v} for k, v in self.CONTENTS.items()]}
        for zone, act in self.PLAYED:
            found = self.act_enemies(zone, act)
            kinds = [k for k, _ in found]
            names = self.enemies(zone)
            out[f'enemies_{zone}_{act}'] = [{'value': k << 8 | s, 'name': names[k] + (f' (setting {s})' if kinds.count(k) > 1 else '')}
                                            for k, s in found]
        return out

    def objects(self, part):
        zone, act = int(part['zone']), int(part['act'])
        names = self.enemies(zone)
        shared = self.same_list(zone, act)
        out = []
        for r in self.records(zone, act):
            kind = r['id']
            row = {'id': f'object:{r["n"]}', 'type': kind, 'x': r['x'], 'y': r['y'] + 16, 'style': 'block',
                   'name': f'Object {kind:#04x}', 'remove': None, 'fields': []}
            if kind in names:
                row.update(style='enemy', name=names[kind], remove='Remove this enemy' if self.REMOVAL else None,
                           fields=[{'key': 'enemy', 'label': 'Swap for', 'value': kind << 8 | r['sub'], 'choices': f'enemies_{zone}_{act}'}])
            elif kind == self.MONITOR:
                row.update(style='item', name='Monitor', detail=f'holds {self.contents_name(r["sub"]).lower()}', remove='Remove this monitor' if self.REMOVAL else None,
                           fields=[{'key': 'contents', 'label': 'Holds', 'value': r['sub'], 'choices': 'contents'}] if r['sub'] in self.CONTENTS else [])
            if shared and (row['fields'] or row['remove']):
                row['note'] = ' and '.join(self.part_name({'zone': z, 'act': a}) for z, a in shared) + ' uses the same list of objects, so a change here shows there too.'
            out.append(row)
        for g in self.rings(zone, act):
            out.append({'id': f'ring:{g["n"]}', 'type': 'ring', 'style': 'item', 'name': 'Ring', 'x': g['x'], 'y': g['y'] + 8,
                        'remove': 'Remove this ring' if self.REMOVAL else None, 'fields': []})
        return out

    def _game(self):
        return {'zone': self.ZONE, 'mode': self.GAME_MODE, 'level': self.LEVEL_MODE, 'camera': self.CAMERA, 'slots': self.SLOTS,
                'respawn': self.RESPAWN, 'rings': self.RING_START}

    # Removal (closing the list up over a record, and the ring list likewise) is written and has a compare watcher, but
    # it has not passed profile_check --control yet, so it is not offered (REMOVAL = True turns it back on).
    REMOVAL = False

    def edit(self, part, object_id, values, remove=False):
        zone, act = int(part['zone']), int(part['act'])
        if remove and not self.REMOVAL:
            raise ValueError('ROMancer cannot remove that yet.')
        text, _, number = str(object_id).partition(':')
        if text == 'ring':
            return self._edit_ring(part, zone, act, number, remove)
        rows = self.records(zone, act)
        if text != 'object' or not number.isdigit() or int(number) >= len(rows):
            raise ValueError('That is not part of this act any more. Reopen the map.')
        r = rows[int(number)]
        names = self.enemies(zone)
        watch = {'zone_n': zone, 'act': act, 'x': r['x'], 'y': r['y'], 'n': r['n'], 'old': r['id'], 'old_sub': r['sub'],
                 'old_range': self.code_range(zone, r['id']), 'game': self._game()}
        idb, subb = r['offset'] + 4, r['offset'] + 5
        if remove:
            if r['id'] not in names and r['id'] != self.MONITOR:
                raise ValueError('That cannot be removed.')
            # close the list up over this record: the rest moves 6 bytes down and the list ends one record sooner
            last = rows[-1]['offset'] + 6
            new = self.rom[r['offset'] + 6:last] + b'\xff\xff'
            writes = [(r['offset'] + i, self.rom[r['offset'] + i], b) for i, b in enumerate(new)]
            title = f'Remove: {names.get(r["id"]) or "Monitor"}'
            watch['kind'] = 'gone'
        elif r['id'] in names:
            value = int(values['enemy'])
            kind, sub = value >> 8, value & 0xFF
            if (kind, sub) not in self.act_enemies(zone, act):
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(idb, self.rom[idb], kind), (subb, self.rom[subb], sub)]
            title = f'Enemy here: {names[kind]}'
            watch.update(kind='enemy', id=kind, sub=sub, name=names[kind], range=self.code_range(zone, kind))
        elif r['id'] == self.MONITOR:
            sub = int(values['contents'])
            if sub not in self.CONTENTS:
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(subb, self.rom[subb], sub)]
            title = f'Monitor holds: {self.contents_name(sub)}'
            watch.update(kind='monitor', sub=sub, name=self.contents_name(sub))
        else:
            raise ValueError('ROMancer cannot change that yet.')
        return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'{title} ({self.part_name(part)}, x {r["x"]})', 'watch': watch}

    def _edit_ring(self, part, zone, act, number, remove):
        rings = self.rings(zone, act)
        if not number.isdigit() or int(number) >= len(rings):
            raise ValueError('That is not part of this act any more. Reopen the map.')
        if not remove:
            raise ValueError('ROMancer cannot change that yet.')
        g = rings[int(number)]
        last = rings[-1]['offset'] + 4
        new = self.rom[g['offset'] + 4:last] + b'\xff\xff'
        writes = [(g['offset'] + i, self.rom[g['offset'] + i], b) for i, b in enumerate(new)]
        watch = {'zone_n': zone, 'act': act, 'x': g['x'], 'y': g['y'], 'address': g['offset'], 'kind': 'ring', 'game': self._game()}
        return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'Remove the ring ({self.part_name(part)}, x {g["x"]})', 'watch': watch}

    def watcher(self, watch):
        if watch.get('kind') == 'ring':
            return _S3KRingWatcher(watch)
        return _S3KObjectWatcher(watch)


class _S3KObjectWatcher(Watcher):
    """Looks through the object slots of the replayed game.

    A record placed by the loader is found by the respawn address its slot keeps (+$48 = $FFEB00 + record number); what
    the slot is comes from its code address (+0), which stays inside the object's own code.

    A removal compares two replays: the unchanged game is played first, and at every look where the removed record's
    object is loaded (its slot keeps the record's respawn address) the number of objects of that kind is noted. The
    changed game must have one fewer of that kind at the same frames."""
    every = 2

    def __init__(self, watch):
        self.w, self.seen = watch, None
        self.compare = watch.get('kind') == 'gone'
        self.before, self.fewer, self.same = {}, 0, 0

    def _slots(self, ram):
        start, end = self.w['game']['slots']
        for slot in range(start, end, 0x4A):
            ptr = _l(ram, slot)
            if ptr:
                yield slot, ptr

    def see(self, ram, frame, run):
        w, g = self.w, self.w['game']
        if ram[g['mode']] != g['level'] or (ram[g['zone']], ram[g['zone'] + 1]) != (w['zone_n'], w['act']):
            return False
        old = w['old_range']
        if w['kind'] == 'gone':
            mine = (g['respawn'] + w['n']) & 0xFFFF
            kinds = [slot for slot, ptr in self._slots(ram) if old[0] <= ptr < old[1]]
            if run == 'original':
                if any(_w(ram, slot + 0x48) == mine for slot in kinds):
                    self.before[frame] = len(kinds)
                return False
            if frame in self.before:
                if len(kinds) < self.before[frame]:
                    self.fewer += 1
                else:
                    self.same += 1
            return self.fewer + self.same >= 30
        mine = (g['respawn'] + w['n']) & 0xFFFF
        for slot, ptr in self._slots(ram):
            if _w(ram, slot + 0x48) != mine:
                continue
            if w['kind'] == 'monitor':
                if old[0] <= ptr < old[1]:
                    self.seen = ram[slot + 0x2C]
                    return True
                continue
            new = w['range']
            if new == old:              # the same enemy with another setting: judged by the setting
                if new[0] <= ptr < new[1]:
                    self.seen = ('sub', ram[slot + 0x2C])
                    return True
            elif new[0] <= ptr < new[1]:
                self.seen = 'new'
                return True
            elif old[0] <= ptr < old[1]:
                self.seen = 'old'
                return True
        return False

    def result(self):
        w, seen = self.w, self.seen
        if w['kind'] == 'gone':
            if self.fewer + self.same == 0:
                return super().result()
            if self.fewer > self.same:
                return {'state': 'good', 'text': 'Played from the start, the object is gone: the game places one fewer of that kind there.'}
            return {'state': 'bad', 'text': 'Played from the start, the object still appears there.'}
        if seen is None:
            return super().result()
        if w['kind'] == 'monitor':
            ok = seen == w['sub']
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the monitor there now holds {w["name"].lower()}.' if ok
                    else f'Played from the start, the monitor there holds contents {seen:#04x}, not the one chosen.'}
        ok = seen == 'new' or (isinstance(seen, tuple) and seen[1] == w['sub'])
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the game now places {w["name"]} there.' if ok
                else 'Played from the start, the game still places the old enemy there.'}


class _S3KRingWatcher(Watcher):
    """A ring removal. The game reads the ring list straight from the cartridge and keeps the window of rings around the
    camera as two cartridge addresses ($FFEE42 first, $FFEE46 end). The unchanged game is replayed first: at each look
    where its window holds the removed ring, the number of rings in the window is noted with the camera x. The changed
    game must then show one ring fewer at the same frame and camera x."""
    every = 2
    compare = True

    def __init__(self, watch):
        self.w, self.before, self.fewer, self.same = watch, {}, 0, 0

    def see(self, ram, frame, run):
        w, g = self.w, self.w['game']
        if ram[g['mode']] != g['level'] or (ram[g['zone']], ram[g['zone'] + 1]) != (w['zone_n'], w['act']):
            return False
        first, end = _l(ram, g['rings']), _l(ram, g['rings'] + 4)
        cam = (_w(ram, g['camera']), _w(ram, g['camera'] + 4))
        if run == 'original':
            if first <= w['address'] < end:
                self.before[frame] = (cam, (end - first) // 4)
            return False
        if frame in self.before and self.before[frame][0] == cam:
            if (end - first) // 4 == self.before[frame][1] - 1:
                self.fewer += 1
            else:
                self.same += 1
        return self.fewer + self.same >= 20

    def result(self):
        if not self.before:
            return super().result()
        if self.fewer + self.same == 0:
            return super().result()
        if self.fewer > self.same:
            return {'state': 'good', 'text': 'Played from the start, the ring is gone: the game shows one ring fewer there.'}
        return {'state': 'bad', 'text': 'Played from the start, the ring is still there.'}


# ---------------------------------------------------------------------------------------------------------------------
# Castlevania: Bloodlines

class Bloodlines(Profile):
    """Castlevania: Bloodlines (USA)."""
    name = 'Castlevania: Bloodlines'
    sha256s = ('5bfe171f5c251600972c412d30a7a2e751c8ab4098163920e51a280298818ebd',)
    system = 'genesis'
    INDEX = 0x4BA3C              # word offsets from here, one per room ($33B6E)
    ROOMS = 70
    VERTICAL = 0x4DEFC           # a byte per room: nonzero when the room scrolls up and down ($33AD0)
    MODE, PLAYING = 0x9002, 9
    IN_ROOM = 0x9264             # 1 while a room is loaded and running
    ROOM = 0x9122
    CAMERA_X, CAMERA_Y = 0x9220, 0x9234     # camera y is the negative of $FF9234
    SLOTS = (0xB000, 0xF000)     # $80 bytes a slot; +0 = 1 while in use, +$17 kind, +$18 x on screen, +$1C y on screen
    CANDLE = 0x77
    GONE = 0x03                  # a kind that deletes itself on its first run (code $3170C)
    # first room of each stage, from the stage start table at $2EEC (blocks) as the game loads them (cvjump.py), and the
    # place names from the game's stage map screens (shots/cv_jump.png, shots/cv_boot_sheet.png)
    STAGES = ((0, 'Ruins of the Castle Dracula'), (11, 'Atlantis Shrine'), (17, 'The Leaning Tower of Pisa'),
              (23, 'The Munitions Factory'), (42, 'Versailles Palace'), (55, 'The Castle Proserpina'))
    # what a candle drops, by its setting (the setting's high nibble is the item, the low one its kind), pictured by
    # breaking a candle with each setting (shots/cv_candle_sheet3.png); only settings the game's own candles use
    CONTENTS = {0x10: 'Small red gem', 0x20: 'Blue gem', 0x30: 'Money bag (setting 0x30)', 0x31: 'Money bag (setting 0x31)',
                0x32: 'Money bag (setting 0x32)', 0x33: 'Money bag (setting 0x33)', 0x34: 'Money bag (setting 0x34)',
                0x35: 'Money bag (setting 0x35)', 0x70: 'Silver disc', 0x80: 'Extra life', 0x90: 'Dark orb',
                0xA0: 'Holy water', 0xB1: 'Axe', 0xC2: 'Boomerang'}

    # ---- reading
    def list_start(self, room: int) -> int:
        return self.INDEX + _w(self.rom, self.INDEX + 2 * room)

    def vertical(self, room: int) -> bool:
        return bool(self.rom[self.VERTICAL + room])

    def records(self, room: int) -> list:
        """The room's records after its $8000 record; n counts from 0 (the game's remember number at +$4C is n + 2)."""
        base = self.list_start(room)
        at, out = base + 8, []
        while _w(self.rom, at) != 0x7FFF and len(out) < 256:
            first, second = _w(self.rom, at), _w(self.rom, at + 4)
            x, y = (second, first) if self.vertical(room) else (first, second)
            out.append({'n': len(out), 'offset': at, 'x': x, 'y': y if y < 0x8000 else y - 0x10000, 'kind': self.rom[at + 2],
                        'setting': self.rom[at + 3], 'extra': self.rom[at + 6], 'flags': self.rom[at + 7]})
            at += 8
        return out

    def stage_of(self, room: int):
        stage = max(i for i, (start, _) in enumerate(self.STAGES) if start <= room)
        return stage + 1, room - self.STAGES[stage][0] + 1, self.STAGES[stage][1]

    def same_list(self, room):
        return [n for n in range(self.ROOMS) if n != room and self.list_start(n) == self.list_start(room)]

    # ---- interface
    def where(self, ram):
        if _w(ram, self.MODE) != self.PLAYING or _w(ram, self.IN_ROOM) != 1:
            return None
        room = _w(ram, self.ROOM)
        if room >= self.ROOMS:
            return None
        cy = _w(ram, self.CAMERA_Y)
        return {'part': {'room': room}, 'x': _w(ram, self.CAMERA_X), 'y': (0x10000 - cy) & 0xFFFF if cy else 0}

    def part_name(self, part):
        stage, number, place = self.stage_of(int(part['room']))
        return f'Stage {stage} ({place}), room {number}'

    def choices(self):
        return {'candle_contents': [{'value': k, 'name': v} for k, v in self.CONTENTS.items()]}

    def objects(self, part):
        room = int(part['room'])
        shared = self.same_list(room)
        out = []
        for r in self.records(room):
            row = {'id': f'object:{r["n"]}', 'type': r['kind'], 'x': r['x'], 'y': r['y'] + 16, 'style': 'block',
                   'name': f'Object {r["kind"]:#04x}', 'remove': None, 'fields': []}
            if r['kind'] == self.CANDLE:
                known = r['setting'] in self.CONTENTS
                row.update(style='item', name='Candle', remove='Remove this candle' if self.REMOVAL else None,
                           detail=f'drops {self.CONTENTS[r["setting"]].lower()}' if known else f'drops item {r["setting"]:#04x}',
                           fields=[{'key': 'contents', 'label': 'Drops', 'value': r['setting'], 'choices': 'candle_contents'}] if known else [])
                if r['extra'] & 0x7F != 1:
                    row['note'] = 'The game sometimes swaps what this candle drops for a whip power-up, until the whip is fully powered.'
            elif r['flags'] & 7 == 3:
                row.update(style='enemy', name=f'Enemy {r["kind"]:#04x}')
            if shared and (row['fields'] or row['remove']):
                names = ' and '.join(self.part_name({'room': n}) for n in shared)
                row['note'] = (row.get('note', '') + ' ' if row.get('note') else '') + f'{names} uses the same list, so a change here shows there too.'
            out.append(row)
        return out

    # Removal (kind 3 in place) is written and has a compare watcher, but the compare watcher has not passed
    # profile_check --control yet, so it is not offered (REMOVAL = True turns it back on).
    REMOVAL = False

    def edit(self, part, object_id, values, remove=False):
        room = int(part['room'])
        if remove and not self.REMOVAL:
            raise ValueError('ROMancer cannot remove that yet.')
        text, _, number = str(object_id).partition(':')
        rows = self.records(room)
        if text != 'object' or not number.isdigit() or int(number) >= len(rows):
            raise ValueError('That is not part of this room any more. Reopen the map.')
        r = rows[int(number)]
        if r['kind'] != self.CANDLE:
            raise ValueError('ROMancer cannot change that yet.')
        watch = {'room': room, 'x': r['x'], 'y': r['y'], 'n': r['n'], 'vertical': self.vertical(room),
                 'game': {'mode': self.MODE, 'playing': self.PLAYING, 'in_room': self.IN_ROOM, 'room': self.ROOM,
                          'camera': self.CAMERA_X, 'camera_y': self.CAMERA_Y, 'slots': self.SLOTS, 'candle': self.CANDLE}}
        if remove:
            # the record stays where it is (the game also finds records by place, $4BAC8) but places a kind that
            # deletes itself at once
            at = r['offset'] + 2
            writes = [(at, self.rom[at], self.GONE)]
            title = 'Remove: Candle'
            watch['kind'] = 'gone'
        else:
            setting = int(values['contents'])
            if setting not in self.CONTENTS:
                raise ValueError('That choice is not one of the game’s own.')
            at = r['offset'] + 3
            writes = [(at, self.rom[at], setting)]
            title = f'Candle drops: {self.CONTENTS[setting]}'
            watch.update(kind='candle', setting=setting, name=self.CONTENTS[setting])
        return {'writes': [w for w in writes if w[1] != w[2]], 'title': f'{title} ({self.part_name(part)}, x {r["x"]})', 'watch': watch}

    def watcher(self, watch):
        return _CandleWatcher(watch)


class _CandleWatcher(Watcher):
    """Finds the candle the changed record places: a slot in use (+0 = 1) of kind $77 whose remember number (+$4C, the
    record's place in the list counted from the $8000 record) is the record's. Its setting is kept at +$53.

    A removal compares two replays: the unchanged game is played first and every look where it has that candle is
    noted; the changed game must have no such candle at those same frames."""
    every = 2

    def __init__(self, watch):
        self.w, self.seen = watch, None
        self.compare = watch.get('kind') == 'gone'
        self.before, self.present, self.absent = set(), 0, 0

    def _candle(self, ram):
        w, g = self.w, self.w['game']
        if _w(ram, g['mode']) != g['playing'] or _w(ram, g['in_room']) != 1 or _w(ram, g['room']) != w['room']:
            return None
        number = (w['n'] + 2) & 0xFF
        start, end = g['slots']
        for slot in range(start, end, 0x80):
            if _w(ram, slot) == 1 and _w(ram, slot + 0x16) == g['candle'] and ram[slot + 0x4C] == number:
                return ram[slot + 0x53]
        return False

    def see(self, ram, frame, run):
        found = self._candle(ram)
        if self.w['kind'] != 'gone':
            if found is not None and found is not False:
                self.seen = found
                return True
            return False
        if run == 'original':
            if found is not None and found is not False:
                self.before.add(frame)
            return False
        if frame in self.before:
            if found is not None and found is not False:
                self.present += 1
            else:
                self.absent += 1
        return self.present + self.absent >= 30

    def result(self):
        w, seen = self.w, self.seen
        if w['kind'] == 'gone':
            if self.present + self.absent == 0:
                return super().result()
            if self.absent > self.present:
                return {'state': 'good', 'text': 'Played from the start, the candle is gone.'}
            return {'state': 'bad', 'text': 'Played from the start, the candle still appears there.'}
        if seen is None:
            return super().result()
        ok = seen == w['setting']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the candle there now drops {w["name"].lower()}.' if ok
                else f'Played from the start, the candle there has setting {seen:#04x}, not the one chosen.'}


PROFILES = [Sonic3K, Bloodlines]
