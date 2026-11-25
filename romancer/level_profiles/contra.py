"""Contra (USA): the enemies and weapon capsules of every side-scrolling stage and the Waterfall, decoded from the game's
own screen lists (research/contra-level-profile.md).

Loader: bank 2 $B419, run once a frame. The level number ($30) picks a pointer at $B513 to a list of words, one per
screen ($64); each points at that screen's list. An entry is three bytes or more: [x, type, y and setting, (more y and
setting bytes)], then $FF ends the list:

* x: bits 1-7 are how far into the screen the camera ($65) must be for the entry to load; bit 0 lets it take the slot
  of another enemy when every slot is in use
* type: bits 0-5 the enemy type, bits 6-7 how many more copies follow (each copy is one more y and setting byte)
* y and setting: bits 4-7 the place across the screen (y on a side-scrolling stage, x on the Waterfall), bits 0-3 the
  setting, kept in $05A8. For a pillbox sensor (type 2) and a flying capsule (type 3) the low three bits are the weapon
  they leave: when shot they turn into a weapon item ($82DF, bank 0) with that number, and picking the item up ($E300,
  bank 7) gives it

The game reads one entry a frame. A side-scrolling enemy appears at the right edge (screen x 240) and the Waterfall's at
the top edge. Stage settings: 32 bytes a level at $B319 (bank 2) copied to $40: $40 is set for the 3-D base stages, $41
for the Waterfall (it scrolls up), $48 is the last screen.
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER = 16
BANK2 = 0x8000                  # ROM offset (no header) of bank 2, which the game maps at $8000 for the loader

STAGES = {0: 'Stage 1: Jungle', 1: 'Stage 2: Base 1', 2: 'Stage 3: Waterfall', 3: 'Stage 4: Base 2',
          4: 'Stage 5: Snow Field', 5: 'Stage 6: Energy Zone', 6: 'Stage 7: Hangar', 7: "Stage 8: Alien's Lair"}

# weapons, by the number a capsule or sensor holds: the letters the game draws on the falling item (research note), and
# what $E300 does with the number: 0 sets the rapid-fire bit and keeps the gun, 1-4 set the gun, 5 starts the barrier
# timer ($B0), 6 calls the clear-the-screen code ($E9E5)
WEAPONS = {0: ('R: rapid bullets', 'Makes your bullets fly faster, and you keep your gun.'),
           1: ('M: machine gun', 'Gives the machine gun: hold the button to keep firing.'),
           2: ('F: fire gun', 'Gives the fire gun, whose shots spiral as they fly.'),
           3: ('S: spread gun', 'Gives the spread gun, which fires five shots in a fan.'),
           4: ('L: laser', 'Gives the laser.'),
           5: ('B: barrier', 'Makes you invincible for a short time.'),
           6: ('Falcon: clears the screen', 'Destroys every enemy on the screen.')}

# enemy types 0-$0F use one routine table for every stage ($E6A8); $10 and up use the stage's own table ($80). Named
# from spawning each one in its stage and looking (trace/v15_profiles/contra/names.png)
COMMON = {
    0x02: ('Pillbox sensor', 'A weapon box set into the ground or wall; shoot it while it is open and it leaves a weapon.'),
    0x03: ('Flying capsule', 'Flies across the screen; shoot it down and it leaves a weapon.'),
    0x04: ('Rotating gun', 'A gun set in the wall that opens up and turns to fire at you.'),
    0x05: ('Running soldier', 'Runs along the ground toward you and drops off ledges.'),
    0x06: ('Rifleman', 'Stands still and fires at you.'),
    0x07: ('Cannon', 'A cannon that rises out of the ground and fires at you.'),
    0x0C: ('Scuba soldier', 'Hides in the water and comes up to throw grenades.'),
    0x0E: ('Heavy gunner', 'An armored soldier with a big gun that fires shells at you.'),
}
VARIANTS = {(0x06, 1): ('Rifleman, hiding in the bushes', 'Hides in the bushes and comes up to fire at you.')}
STAGE_TYPES = {
    0: {0x10: ('Boss wall gun', 'A gun on the wall at the end of the stage.', True),
        0x11: ('Boss wall core', 'The red sensor in the wall at the end of the stage; destroy it to finish the stage.', True),
        0x12: ('Exploding bridge', 'A bridge that blows up piece by piece once you step onto it.', False)},
    2: {0x11: ('Flames', 'Flames that burn on a ledge.', False),
        0x12: ('Falling rock', 'A rock that rolls off a ledge and falls down the falls.', False)},
    5: {0x10: ('Ceiling fire jet', 'Shoots a jet of fire down from the ceiling now and then.', False),
        0x11: ('Wall fire jet, to the left', 'Shoots a jet of fire to the left out of the wall now and then.', False),
        0x12: ('Wall fire jet, to the right', 'Shoots a jet of fire to the right out of the wall now and then.', False),
        0x13: ('Giant soldier (boss)', 'The boss at the end of the stage.', True)},
    6: {0x10: ('Ceiling claws', 'A row of claws that drops from the ceiling and pulls back up.', False),
        0x12: ('Spiked wall', 'A wall that pushes spikes out at you.', False),
        0x13: ('Ceiling claw', 'A single claw that drops from the ceiling and pulls back up.', False),
        0x15: ('Mine cart', 'A cart that rolls along the rail.', False),
        0x16: ('Boss wall core', 'The core of the armored wall at the end of the stage.', True),
        0x17: ('Boss wall hatch', 'A hatch on the armored wall at the end of the stage.', True),
        0x18: ('Boss wall gun', 'A gun on the armored wall at the end of the stage.', True)},
    7: {0x10: ('Alien mouth', 'A giant mouth with teeth set in the wall.', False),
        0x11: ('Alien mouth pod', 'A small mouth in the wall that spits fire.', False),
        0x12: ('Alien pod', 'A pink pod in the wall that throbs and spits.', False),
        0x14: ('Alien scorpion', 'A pink alien that crawls along the floor.', False),
        0x15: ('Alien face (boss)', 'A face in the wall before the heart.', True),
        0x16: ('Alien heart (boss)', 'The last boss: the beating heart of the lair.', True)},
}
CARRIES = (0x02, 0x03)          # types whose setting is the weapon they leave


class Contra:
    """Reads the screen lists. Every address is a CPU address in bank 2."""
    name = 'Contra'
    sha256 = '1f4a9b3f04e2f828688512c0b83611a87c3fc1bd4f85ed91da1b19abc5816d73'
    LEVELS = 8

    def __init__(self, rom: bytes):
        self.rom = rom

    def offset(self, address: int) -> int:
        return HEADER + BANK2 + (address - 0x8000)

    def _at(self, address: int) -> int:
        return self.rom[self.offset(address)]

    def _word(self, address: int) -> int:
        return self._at(address) | self._at(address + 1) << 8

    def settings(self, level: int) -> dict:
        base = 0xB319 + level * 32
        return {'base': bool(self._at(base)), 'up': bool(self._at(base + 1)), 'last': self._at(base + 8)}

    def side(self, level: int) -> bool:
        """True for the stages the profile covers: everything but the 3-D base stages."""
        return 0 <= level < self.LEVELS and not self.settings(level)['base']

    def screen_list(self, level: int, screen: int) -> int:
        return self._word(self._word(0xB513 + level * 2) + screen * 2)

    def entries(self, level: int, screen: int) -> list:
        """[{'entry', 'start' (byte index in the list), 'x', 'grab', 'type', 'type_at', 'places': [(value, offset)]}]"""
        address, out, index = self.screen_list(level, screen), [], 0
        for number in range(64):
            x = self._at(address + index)
            if x == 0xFF:
                break
            kind = self._at(address + index + 1)
            places = [(self._at(address + index + 2 + k), self.offset(address + index + 2 + k)) for k in range((kind >> 6) + 1)]
            out.append({'entry': number, 'start': index, 'x': x & 0xFE, 'grab': x & 1, 'type': kind & 0x3F,
                        'type_at': self.offset(address + index + 1), 'places': places})
            index += 3 + (kind >> 6)
        return out

    def list_end(self, level: int, screen: int) -> int:
        """Byte index of the $FF that ends a screen's list."""
        rows = self.entries(level, screen)
        return rows[-1]['start'] + 2 + len(rows[-1]['places']) if rows else 0

    def shared(self, level: int, screen: int) -> bool:
        """True when another screen's pointer points into this list (the base stages share their lists)."""
        start = self.screen_list(level, screen)
        end = start + self.list_end(level, screen)
        for other in range(self.LEVELS):
            for s in range(self.settings(other)['last'] + 1):
                if (other, s) != (level, screen) and start <= self.screen_list(other, s) <= end:
                    return True
        return False

    def type_name(self, level: int, kind: int, setting: int = 0):
        """(name, does, boss)"""
        if (kind, setting & 7) in VARIANTS and kind == 0x06:
            name, does = VARIANTS[(kind, setting & 7)]
            return name, does, False
        if kind < 0x10 and kind in COMMON:
            return COMMON[kind] + (False,)
        if kind in STAGE_TYPES.get(level, {}):
            return STAGE_TYPES[level][kind]
        return (f'Enemy {kind:#04x}', None, kind >= 0x10)

    def objects_of(self, level: int) -> list:
        """Every enemy copy of a stage, in stage pixels."""
        info, out = self.settings(level), []
        for screen in range(info['last'] + 1):
            for row in self.entries(level, screen):
                for copy, (value, at) in enumerate(row['places']):
                    if info['up']:
                        x, y = (value & 0xF0) + 8, (info['last'] - screen) * 240 - row['x'] + 16
                    else:
                        x, y = screen * 256 + row['x'] + 0xF0, (value & 0xF0) + 8
                    name, does, boss = self.type_name(level, row['type'], value & 0x0F)
                    out.append({'screen': screen, 'entry': row['entry'], 'copy': copy, 'copies': len(row['places']),
                                'type': row['type'], 'setting': value & 0x0F, 'place': value & 0xF0, 'x': x, 'y': y,
                                'name': name, 'does': does, 'boss': boss, 'start': row['start'], 'trigger': row['x'],
                                'type_at': row['type_at'], 'place_at': at})
        return out

    def type_choices(self, level: int) -> list:
        """The (type, setting) pairs the stage itself uses, bosses left out: [{'value': type * 16 + setting, 'name'}]."""
        seen, out = set(), []
        for o in self.objects_of(level):
            key = (o['type'], o['setting'])
            if o['boss'] or key in seen:
                continue
            seen.add(key)
            name = o['name']
            if o['type'] in CARRIES:
                name += f', leaves {WEAPONS.get(o["setting"] & 7, ("weapon " + str(o["setting"] & 7),))[0]}'
            out.append({'value': o['type'] * 16 + o['setting'], 'name': name})
        names = {}
        for c in out:
            names.setdefault(c['name'], []).append(c)
        for name, group in names.items():
            if len(group) > 1:
                for n, c in enumerate(group, 1):
                    c['name'] = f'{name} (kind {n})'
        return sorted(out, key=lambda c: c['name'])

    def remove_writes(self, level: int, screen: int, entry: int, copy=None) -> list:
        """Writes that take an entry (or one copy of it) out of a screen's list: the rest moves up, $FF fills the end."""
        if self.shared(level, screen):
            raise ValueError('This screen shares its list with another screen, so ROMancer cannot take one enemy out of it.')
        rows = self.entries(level, screen)
        row = next((r for r in rows if r['entry'] == entry), None)
        if row is None:
            raise ValueError('That is not part of this stage.')
        address = self.screen_list(level, screen)
        end = self.list_end(level, screen)
        data = [self._at(address + i) for i in range(end + 1)]
        start = row['start']
        if copy is not None and len(row['places']) > 1:
            del data[start + 2 + copy]
            data[start + 1] -= 0x40
        else:
            del data[start:start + 2 + len(row['places'])]
        data += [0xFF] * (end + 1 - len(data))
        return [(self.offset(address + i), self._at(address + i), v) for i, v in enumerate(data) if self._at(address + i) != v]


def _swap_value(value: int):
    return value >> 4, value & 15


class _SpawnWatcher(Watcher):
    """An enemy edit: from the first frame the camera reaches the entry's place in its screen, watch for 8 frames which
    enemies the screen list loads (new slots at the edge where list enemies appear). Slots: $04B8 routine, $0528 type,
    $05A8 setting, $033E x, $0324 y."""
    every = 1

    def __init__(self, watch):
        self.w = watch
        self.prev = {}
        self.start = {}
        self.seen = {}

    def _new(self, ram, run):
        prev = self.prev.get(run)
        now = [(ram[0x4B8 + s], ram[0x528 + s], ram[0x5A8 + s], ram[0x33E + s], ram[0x324 + s]) for s in range(16)]
        self.prev[run] = now
        if prev is None:
            return []
        out = []
        for s in range(16):
            on, kind, setting, x, y = now[s]
            if on and (not prev[s][0] or prev[s][1] != kind):
                edge = y <= 0x20 if self.w['up'] else 0xC8 <= x <= 0xF0
                if edge:
                    out.append((kind, setting))
        return out

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x30] != w['level'] or ram[0x2C] != 4 or ram[0x18] != 5:
            self.prev[run] = None
            return False
        fresh = self._new(ram, run)
        if run not in self.start:
            if ram[0x64] == w['screen'] and ram[0x65] >= w['trigger'] or ram[0x64] > w['screen']:
                if ram[0x64] > w['screen'] + 1:
                    return False                # the walk started past this place
                self.start[run] = frame
            else:
                return False
        self.seen.setdefault(run, []).extend(fresh)
        return frame - self.start[run] >= 8

    def result(self):
        w = self.w
        seen = self.seen.get('changed')
        if seen is None:
            return super().result()
        if w['remove']:
            left = sum(1 for kind, setting in seen if kind == w['type'] and setting == w['setting'])
            ok = left == w['keep']
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the {w["name"].lower()} no longer appears there.' if ok
                    else f'Played from the start, the {w["name"].lower()} still appears there.'}
        ok = (w['type'], w['setting']) in seen
        if ok:
            return {'state': 'good', 'text': f'Played from the start, the game now puts a {w["name"][0].lower() + w["name"][1:]} at that place.'}
        got = ', '.join(f'type {k:#04x} setting {s}' for k, s in seen) or 'nothing'
        return {'state': 'bad', 'text': f'Played from the start, the game put {got} there, not what was chosen.'}


class ContraProfile(Contra, Profile):
    """Contra on the common profile interface. Parts are {'stage': level number}; a side-scrolling stage's x is the
    camera's pixels from the stage start, the Waterfall's y the camera's pixels from the top."""
    sha256s = (Contra.sha256,)

    def where(self, ram):
        if ram[0x18] != 5 or ram[0x2C] != 4:
            return None
        level = ram[0x30]
        if not self.side(level):
            return None
        info = self.settings(level)
        if info['up']:
            return {'part': {'stage': level}, 'x': 0, 'y': (info['last'] - ram[0x64]) * 240 - ram[0x65]}
        return {'part': {'stage': level}, 'x': ram[0x64] * 256 + ram[0x65], 'y': 0}

    def part_name(self, part):
        return STAGES.get(int(part['stage']), f'Stage {int(part["stage"]) + 1}')

    def choices(self):
        return {'weapons': [{'value': k, 'name': v[0]} for k, v in WEAPONS.items()]}

    def objects(self, part):
        level = int(part['stage'])
        if not self.side(level):
            return []
        enemies = self.type_choices(level)
        out = []
        for o in self.objects_of(level):
            row = {'id': f'enemy:{o["screen"]}:{o["entry"]}:{o["copy"]}', 'style': 'item' if o['type'] in CARRIES else 'enemy',
                   'type': o['type'], 'x': o['x'], 'y': o['y'], 'name': o['name'], 'does': o['does'], 'fields': [],
                   'remove': None if o['boss'] else 'Remove this enemy'}
            if o['type'] in CARRIES:
                weapon = o['setting'] & 7
                row['detail'] = f'leaves {WEAPONS[weapon][0] if weapon in WEAPONS else "weapon " + str(weapon)}'
                row['fields'].append({'key': 'weapon', 'label': 'Leaves', 'value': weapon, 'choices': 'weapons'})
            if not o['boss']:
                row['fields'].insert(0, {'key': 'enemy', 'label': 'Swap for', 'value': o['type'] * 16 + o['setting'], 'choices': enemies})
            if o['copies'] > 1:
                row['note'] = (f'This is one of {o["copies"]} that the game loads together from one entry; a swap changes all '
                               f'{o["copies"]}, a new weapon or a removal changes this one alone.')
            if o['boss']:
                row['note'] = 'Part of the boss: ROMancer leaves it as it is.'
            out.append(row)
        return out

    def _find(self, level, object_id):
        kind, screen, entry, copy = object_id.split(':')
        if kind != 'enemy':
            raise ValueError('ROMancer cannot change that yet.')
        o = next((o for o in self.objects_of(level) if (o['screen'], o['entry'], o['copy']) == (int(screen), int(entry), int(copy))), None)
        if o is None:
            raise ValueError('That is not part of this stage any more. Reopen the map.')
        return o

    def edit(self, part, object_id, values, remove=False):
        level = int(part['stage'])
        if not self.side(level):
            raise ValueError('ROMancer does not know the enemies of the base stages yet.')
        o = self._find(level, object_id)
        if o['boss']:
            raise ValueError('ROMancer leaves the boss as it is.')
        watch = {'level': level, 'screen': o['screen'], 'trigger': o['trigger'], 'up': self.settings(level)['up']}
        if remove:
            writes = self.remove_writes(level, o['screen'], o['entry'], o['copy'] if o['copies'] > 1 else None)
            keep = sum(1 for p in self.objects_of(level) if (p['screen'], p['entry']) == (o['screen'], o['entry'])
                       and p['copy'] != o['copy'] and p['setting'] == o['setting'])
            # other entries at the same place in the screen with the same type and setting load in the same window
            keep += sum(1 for p in self.objects_of(level) if p['screen'] == o['screen'] and p['entry'] != o['entry']
                        and p['trigger'] == o['trigger'] and (p['type'], p['setting']) == (o['type'], o['setting']))
            watch.update(remove=True, type=o['type'], setting=o['setting'], keep=keep, name=o['name'])
            return {'writes': writes, 'title': f'Remove the {o["name"].lower()} (screen {o["screen"] + 1})', 'watch': watch}
        writes = {}
        kind, setting = o['type'], o['setting']
        if values.get('enemy') is not None and int(values['enemy']) != o['type'] * 16 + o['setting']:
            options = {c['value'] for c in self.type_choices(level)}
            if int(values['enemy']) not in options:
                raise ValueError('That choice is not one of the game’s own.')
            kind, setting = _swap_value(int(values['enemy']))
            old = self.rom[o['type_at']]
            writes[o['type_at']] = (old, (old & 0xC0) | kind)
            for p in self.objects_of(level):
                if (p['screen'], p['entry']) == (o['screen'], o['entry']):
                    v = self.rom[p['place_at']]
                    writes[p['place_at']] = (v, (v & 0xF0) | setting)
        if values.get('weapon') is not None:
            weapon = int(values['weapon'])
            if weapon not in WEAPONS:
                raise ValueError('Choose one of the game’s weapons.')
            if kind not in CARRIES:
                raise ValueError('Only a pillbox sensor or a flying capsule leaves a weapon.')
            v = writes.get(o['place_at'], (self.rom[o['place_at']], self.rom[o['place_at']]))
            setting = (setting & 8) | weapon
            writes[o['place_at']] = (v[0], (v[1] & 0xF0) | setting)
        out = [(at, old, new) for at, (old, new) in sorted(writes.items()) if old != new]
        name = self.type_name(level, kind, setting)[0]
        title = f'Enemy here: {name}'
        if kind in CARRIES:
            title += f', leaves {WEAPONS.get(setting & 7, ("weapon",))[0]}'
        watch.update(remove=False, type=kind, setting=setting, name=name + (f' that leaves {WEAPONS.get(setting & 7, ("a weapon",))[0]}' if kind in CARRIES else ''))
        return {'writes': out, 'title': f'{title} (screen {o["screen"] + 1})', 'watch': watch}

    def watcher(self, watch):
        return _SpawnWatcher(watch)


PROFILES = [ContraProfile]
