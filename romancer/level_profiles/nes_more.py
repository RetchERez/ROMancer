"""What ROMancer knows about the levels of more NES games: Bubble Bobble's rounds and Kirby's Adventure's rooms, read
from the games' own tables (research/nes_more-level-profile.md).
"""
from __future__ import annotations

from . import Profile, Watcher

HEADER = 16


def _a(name: str) -> str:
    return ('an ' if name[:1].lower() in 'aeiou' else 'a ') + name


# ---------------------------------------------------------------------------------------------------------------------
# Bubble Bobble

class BubbleBobble:
    """Bubble Bobble (USA). Round number $0401 (1-112). A round's records sit in PRG bank (round - 1) >> 5, in the
    $8000 or $A000 half by bit 4 of (round - 1), sixteen rounds to a half (bank 7 $E954 and $F74D):

    * $x56B + 22 * ((round - 1) & 15): one setting byte, then up to seven enemies of 3 bytes, ended by $FF. Enemy byte 0:
      bit 7 the side it faces, bits 4-6 its slot (RAM $68 + 4 * slot), bits 0-3 its type (1-8; $E9C8). Byte 1: the
      height it drops to (sprite y = byte - 1), byte 2: its x. Enemies drop in from the top of the screen to that place.
    * $x520 + ((round - 1) & 15) / 2: a nibble per round (even rounds the high one): bit 0 opens the top and bottom
      walls, bits 3, 2 and 1 let lightning, fire and water bubbles float in ($E00E; the bubble's object type is $F6,
      $F7 or $F8, in slots $88-$C0).

    The sprite pictures come from CHR bank $F78D[round >> 4] ($F77D), so a round can only draw the enemy types of the
    rounds that share its bank; the swap lists keep to those.
    """
    name = 'Bubble Bobble'
    sha256 = 'e34901acf6917495890ef79ddb33e4641ea309a803d777a27a198e8802c9b4a0'
    ROUNDS = 112
    # names from what the game draws (trace/v15_profiles/nes_more/bb_names.png: each type in a round that uses it) and
    # what each throws or breathes there (bb_shot_*.png); does-lines from watching each for 25 seconds
    ENEMIES = {
        1: ('Zen-chan', 'A wind-up robot that walks along the platforms and jumps up to reach you.'),
        2: ('Mighta', 'A hooded wizard that walks along the platforms and throws boulders at you.'),
        3: ('Hidegons', 'Walks along the platforms and breathes fireballs that roll along the floor.'),
        4: ('Drunk', 'Walks along the platforms and throws bottles at you.'),
        5: ('Banebou', 'Bounces about the round on its spring.'),
        6: ('Monsta', 'A whale-like ghost that flies at a slant and bounces off the walls.'),
        7: ('Pulpul', 'Flies about the round, turning toward you.'),
        8: ('Invader', 'Moves side to side, steps down the screen and fires shots straight down.'),
    }
    # the enemy types each sprite bank can draw: the types its own rounds use (F78D: rounds 1-47 and 64-79 bank 2, 48-63 bank 3,
    # 80-95 bank 4, 96-112 bank 5)
    BANK_TYPES = {2: (1, 2, 3, 5, 6, 7, 8), 3: (1, 2, 3, 4, 6, 8), 4: (1, 3, 4, 6, 7, 8), 5: (1, 3, 4, 5, 6, 7, 8)}
    BUBBLES = {0x8: 'Lightning bubbles', 0x4: 'Fire bubbles', 0x2: 'Water bubbles'}
    BUBBLE_TYPE = {0x8: 0xF6, 0x4: 0xF7, 0x2: 0xF8}
    # the bubble mixes the game's rounds use (bits 3-1 of the round nibble)
    BUBBLE_MIXES = {0x0: 'No special bubbles', 0x2: 'Water bubbles', 0x4: 'Fire bubbles', 0x8: 'Lightning bubbles',
                    0xA: 'Lightning and water bubbles', 0xC: 'Lightning and fire bubbles'}
    BUBBLE_DOES = {0x2: 'Blue bubbles with a water drop float up through the round.',
                   0x4: 'Red bubbles with a flame float up through the round.',
                   0x8: 'Green bubbles with a lightning bolt float up through the round.'}

    def __init__(self, rom: bytes):
        self.rom = rom

    # ---- reading
    def _half(self, rnd: int) -> int:
        r = rnd - 1
        return HEADER + (r >> 5) * 0x4000 + ((r >> 4) & 1) * 0x2000

    def record_offset(self, rnd: int) -> int:
        return self._half(rnd) + 0x156B + ((rnd - 1) & 15) * 0x16

    def nibble_offset(self, rnd: int) -> int:
        return self._half(rnd) + 0x1520 + ((rnd - 1) & 15) // 2

    def nibble(self, rnd: int) -> int:
        byte = self.rom[self.nibble_offset(rnd)]
        return byte >> 4 if (rnd - 1) % 2 == 0 else byte & 15

    def sprite_bank(self, rnd: int) -> int:
        return (self.rom[HEADER + 7 * 0x4000 + 0x378D + (rnd >> 4)] & 0x1F) % 8

    def allowed_types(self, rnd: int) -> tuple:
        return self.BANK_TYPES.get(self.sprite_bank(rnd), tuple(self.ENEMIES))

    def enemies(self, rnd: int) -> list:
        at = self.record_offset(rnd)
        out, i = [], 1
        while i + 2 < 0x16 and self.rom[at + i] != 0xFF:
            b0, b1, b2 = self.rom[at + i:at + i + 3]
            out.append({'number': len(out), 'offset': at + i, 'type': b0 & 15, 'slot': (b0 >> 4) & 7, 'faces': b0 >> 7,
                        'drop_y': b1, 'x': b2})
            i += 3
        return out

    def enemy_name(self, kind: int) -> str:
        return self.ENEMIES.get(kind, (f'Enemy {kind:#x}', None))[0]

    def remove_writes(self, rnd: int, number: int) -> list:
        at = self.record_offset(rnd)
        old = bytes(self.rom[at + 1:at + 0x16])
        rows = [old[3 * k:3 * k + 3] for k in range(len(self.enemies(rnd)))]
        del rows[number]
        new = (b''.join(rows) + b'\xff' * 0x15)[:0x15]
        return [(at + 1 + k, old[k], new[k]) for k in range(0x15) if old[k] != new[k]]

    def bubble_writes(self, rnd: int, mix: int) -> list:
        at = self.nibble_offset(rnd)
        nib = (self.nibble(rnd) & 1) | mix
        old = self.rom[at]
        new = (old & 0x0F) | nib << 4 if (rnd - 1) % 2 == 0 else (old & 0xF0) | nib
        return [(at, old, new)] if new != old else []


class _BBEnemyWatcher(Watcher):
    """An enemy edit: when the round's enemies drop in (some slot at $68 + 4 * n has bit 7 set), read the edited one's slot."""
    every = 2

    def __init__(self, watch):
        self.w, self.seen = watch, None

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x401] != w['round'] or not any(ram[0x68 + 4 * s] & 0x80 for s in range(7)):
            return False
        self.seen = ram[0x68 + 4 * w['slot']]
        return True

    def result(self):
        w, seen = self.w, self.seen
        if seen is None:
            return super().result()
        if w['type'] is None:
            ok = seen == 0
            return {'state': 'good' if ok else 'bad', 'text': 'Played from the start, that enemy no longer drops into the round.' if ok
                    else 'Played from the start, an enemy still drops into the round there.'}
        ok = seen & 15 == w['type']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, {_a(w["name"])} now drops into the round there.' if ok
                else f'Played from the start, enemy type {seen & 15} dropped in there, not the one chosen.'}


class _BBBubbleWatcher(Watcher):
    """A special-bubble edit: from when the round's enemies drop in, which bubble types ($F6-$F8) show in slots $88-$C0."""
    every = 4
    WINDOW = 900            # every bubble mix the game uses shows its bubbles within 400 frames of the round starting

    def __init__(self, watch):
        self.w, self.start, self.last, self.kinds = watch, None, None, set()

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x401] != w['round']:
            return False
        if self.start is None:
            if not any(ram[0x68 + 4 * s] & 0x80 for s in range(7)):
                return False
            self.start = frame
        self.last = frame
        self.kinds |= {ram[0x88 + 4 * k] for k in range(15)} & {0xF6, 0xF7, 0xF8}
        wanted = set(w['types'])
        if self.kinds - wanted:
            return True
        if wanted and wanted <= self.kinds:
            return True
        return frame - self.start >= self.WINDOW

    def result(self):
        w = self.w
        if self.start is None:
            return super().result()
        wanted = set(w['types'])
        if self.kinds - wanted:
            return {'state': 'bad', 'text': 'Played from the start, bubbles that were not chosen still float into the round.'}
        if self.kinds == wanted:
            return {'state': 'good', 'text': 'Played from the start, ' + (f'{w["name"].lower()} now float into the round.' if wanted
                                                                           else 'no special bubbles float into the round.')}
        if self.last - self.start < self.WINDOW:
            return {'state': 'warn', 'text': "The recorded walk ends before the chosen bubbles would have shown, so the change couldn't be watched to the end."}
        return {'state': 'bad', 'text': 'Played from the start, the chosen bubbles did not float into the round.'}


class BubbleBobbleProfile(BubbleBobble, Profile):
    """Bubble Bobble on the common profile interface. Parts are {'round'}; every round is one screen."""
    sha256s = (BubbleBobble.sha256,)
    TOP = 8                 # the picture ROMancer records starts 8 lines below the top of the NES screen

    def where(self, ram):
        rnd = ram[0x401]
        if not 1 <= rnd <= self.ROUNDS or ram[0xFC] != 0:      # $FC: vertical scroll, not 0 while rounds slide past
            return None
        return {'part': {'round': rnd}, 'x': 0, 'y': 0}

    def part_name(self, part):
        return f'Round {int(part["round"])}'

    def choices(self):
        return {'bubbles': [{'value': k, 'name': v} for k, v in self.BUBBLE_MIXES.items()]}

    def _enemy_choices(self, rnd):
        return [{'value': t, 'name': self.ENEMIES[t][0]} for t in self.allowed_types(rnd)]

    def objects(self, part):
        rnd = int(part['round'])
        if not 1 <= rnd <= self.ROUNDS:
            return []
        out = []
        choices = self._enemy_choices(rnd)
        for e in self.enemies(rnd):
            name, does = self.ENEMIES.get(e['type'], (f'Enemy {e["type"]:#x}', None))
            row = {'id': f'enemy:{e["number"]}', 'style': 'enemy', 'type': e['type'], 'x': e['x'] + 8,
                   'y': e['drop_y'] + 16 - self.TOP, 'name': name, 'does': does, 'remove': 'Remove this enemy',
                   'detail': 'drops in from the top of the screen to here',
                   'fields': [{'key': 'type', 'label': 'Swap for', 'value': e['type'], 'choices': choices}]}
            out.append(row)
        mix = self.nibble(rnd) & 0xE
        out.append({'id': 'bubbles', 'style': 'item', 'type': 'bubbles', 'x': 128, 'y': 40 - self.TOP,
                    'name': self.BUBBLE_MIXES.get(mix, 'Special bubbles'),
                    'does': ' '.join(self.BUBBLE_DOES[b] for b in (8, 4, 2) if mix & b) or 'No special bubbles float into this round.',
                    'detail': 'special bubbles that float into this round', 'remove': None,
                    'note': 'This setting shares a byte with the round next to it; only this round’s half is changed.',
                    'fields': [{'key': 'bubbles', 'label': 'Special bubbles', 'value': mix, 'choices': 'bubbles'}]})
        return out

    def edit(self, part, object_id, values, remove=False):
        rnd = int(part['round'])
        if object_id == 'bubbles':
            mix = int(values.get('bubbles'))
            if mix not in self.BUBBLE_MIXES:
                raise ValueError('That choice is not one of the game’s own.')
            name = self.BUBBLE_MIXES[mix]
            return {'writes': self.bubble_writes(rnd, mix), 'title': f'Round {rnd}: {name.lower()}',
                    'watch': {'kind': 'bubbles', 'round': rnd, 'types': [self.BUBBLE_TYPE[b] for b in (8, 4, 2) if mix & b], 'name': name}}
        kind, _, number = object_id.partition(':')
        if kind != 'enemy':
            raise ValueError('ROMancer cannot change that yet.')
        rows = self.enemies(rnd)
        number = int(number)
        if not 0 <= number < len(rows):
            raise ValueError('That is not part of this level any more. Reopen the map.')
        e = rows[number]
        if remove:
            return {'writes': self.remove_writes(rnd, number), 'title': f'Round {rnd}: remove the {self.enemy_name(e["type"])}',
                    'watch': {'kind': 'enemy', 'round': rnd, 'slot': e['slot'], 'type': None, 'name': ''}}
        kind_new = int(values.get('type'))
        if kind_new not in self.allowed_types(rnd):
            raise ValueError('That choice is not one of the game’s own.')
        old = self.rom[e['offset']]
        new = (old & 0xF0) | kind_new
        name = self.enemy_name(kind_new)
        return {'writes': [(e['offset'], old, new)] if new != old else [], 'title': f'Round {rnd}: enemy here: {name}',
                'watch': {'kind': 'enemy', 'round': rnd, 'slot': e['slot'], 'type': kind_new, 'name': name}}

    def watcher(self, watch):
        return _BBBubbleWatcher(watch) if watch['kind'] == 'bubbles' else _BBEnemyWatcher(watch)


PROFILES = [BubbleBobbleProfile]
