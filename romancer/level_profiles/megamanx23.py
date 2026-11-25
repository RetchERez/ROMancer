"""Mega Man X2 (USA) and Mega Man X3 (USA) on the Super NES.

Both use the Mega Man X engine (see snes_more.py and research/snes_more-level-profile.md): the same object lists, the
same loader and spawner, only moved. Both cartridges are LoROM without a copier header, with the Cx4 chip.

What moved (found in the code, research/megamanx23-level-profile.md):
* level number: X2 $1FAD, X3 $1FAE; playing while $00D1 = 4 (and $00D2 = 2 or 4)
* object list pointers: X2 $29:D3D1 + level * 2 (bank $29; loader $80DB8B), X3 $3C:CE4B + level * 2 (bank $3C;
  loader $80DD75). The list format is the same as Mega Man X's: a column byte, 7-byte entries (type, y, id, sub, x
  with bit 7 = last of the column), a closing column byte equal to the one before it. The loader copies the entries
  to RAM $7E:FA02 (5 bytes each); the spawner gives a slot +$0C = that RAM entry's address.
* camera $1E5D (x) / $1E60 (y), read by the spawner (X2 $80DC50, X3 $80DE3A); the camera borders are $1E66 (left),
  $1E68 (right), $1E6A (top), $1E6C (bottom), with copies at $1E6E / $1E70
* slots (X2 $80DA70, X3 $82D832): type 0 $1518 + n * $30 (16), type 1 $1818 + n * $20 (40), type 2 $1D18 + n * $10
  (16), type 3 $0D18 + n * $40 (15). Mega Man is the slot at $09D8 (x $09DD, y $09E0, life energy $09FF).
* graphics loads: type 2 ids $15 and $18 run the same graphics set loader as in Mega Man X (X2 $81FDB5 storing
  $1F18, X3 $B9C023), so swaps stay among enemies placed under the same load.
"""
from __future__ import annotations

from . import Profile, Watcher
from .snes_more import MegaManX, MegaManXProfile, lorom, _w


class _X23(MegaManX):
    """What X2 and X3 share. Subclasses give the tables, names and RAM places."""
    BANK = 0
    LEVEL_RAM = 0
    ENTRY_RAM = 0xFA02
    CAMERA = (0x1E5D, 0x1E60)
    SLOTS = {0: (0x1518, 0x30, 16), 1: (0x1818, 0x20, 40), 2: (0x1D18, 0x10, 16), 3: (0x0D18, 0x40, 15)}
    ONCE = ()                     # enemy ids never offered (bosses, helpers placed once, scripted parts)
    ENEMIES: dict = {}
    ITEMS: dict = {}
    ITEM_DOES: dict = {}
    COMMON_ITEMS: list = []
    SPECIAL = (0x0B, 0x05)        # Heart Tank and Sub Tank: the game counts each one once

    def list_start(self, level: int) -> int:
        return lorom(self.BANK << 16 | self.w(self.LISTS + level * 2))

    def editable_enemy(self, e: dict) -> bool:
        return e['type'] == 3 and self.count().get((3, e['id']), 0) > 1 and e['id'] not in self.ONCE

    def item_does(self, number: int, sub: int):
        return self.ITEM_DOES.get((number, sub), self.ITEM_DOES.get((number, None)))

    def item_name(self, number: int, sub: int) -> str:
        return self.ITEMS.get((number, sub)) or self.ITEMS.get((number, None)) or f'Object {number:#04x}'

    def is_item(self, e: dict) -> bool:
        return e['type'] == 0 and ((e['id'], e['sub']) in self.ITEMS or (e['id'], None) in self.ITEMS)

    @classmethod
    def playing(cls, ram) -> bool:
        return ram[0xD1] == 4 and ram[0xD2] in (2, 4)


class _X23Watcher(Watcher):
    """An X2 or X3 edit. A swap is seen when a slot of the entry's type holds the entry's RAM address (+$0C) and the
    chosen id and sub (+$0A, +$0B). A removal is seen when the screen has been over the spot for 30 looks and no slot
    of that type first showed the old id and sub there (within 8 px)."""
    every = 3

    def __init__(self, game, watch):
        self.g = game
        self.w = watch
        self.seen = None
        self.reached = 0
        self.slots = {}

    def see(self, ram, frame, run):
        g, w = self.g, self.w
        if not g.playing(ram) or ram[g.LEVEL_RAM] != w['level']:
            return False
        base, size, count = g.SLOTS[w['type']]
        if w['remove']:
            for n in range(count):
                s = base + n * size
                if not ram[s]:
                    self.slots.pop(s, None)
                    continue
                key = (ram[s + 0xA], ram[s + 0xB], _w(ram, s + 0xC))
                if self.slots.get(s) == key:
                    continue
                self.slots[s] = key
                if key[:2] == (w['id'], w['sub']) and abs(_w(ram, s + 5) - w['x']) <= 8 and abs(_w(ram, s + 8) - w['y']) <= 8:
                    self.seen = 'there'
                    return True
            cx, cy = _w(ram, g.CAMERA[0]), _w(ram, g.CAMERA[1])
            if cx <= w['x'] <= cx + 256 and cy <= w['y'] <= cy + 224:
                self.reached += 1
                if self.reached > 30:
                    self.seen = 'gone'
                    return True
            return False
        for n in range(count):
            s = base + n * size
            if ram[s] and _w(ram, s + 0xC) == w['entry']:
                self.seen = (ram[s + 0xA], ram[s + 0xB])
                return True
        return False

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if w['remove']:
            ok = self.seen == 'gone'
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the screen reached that spot and no {w["name"]} appeared there.' if ok
                    else f'Played from the start, the {w["name"]} still appears there.'}
        ok = self.seen == (w['id'], w['sub'])
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now puts {w["name"]} there.' if ok
                else f'Played from the start, the game put object {self.seen[0]:#04x} (setting {self.seen[1]:#04x}) there, not the one chosen.'}


class _X23Profile(_X23, MegaManXProfile):
    """Parts are {'level': number}; x and y are the level's pixels (the camera is $1E5D / $1E60)."""
    system = 'snes'

    def __init__(self, rom: bytes):
        _X23.__init__(self, rom)

    def where(self, ram):
        if not self.playing(ram) or ram[self.LEVEL_RAM] >= self.LEVELS:
            return None
        return {'part': {'level': ram[self.LEVEL_RAM]}, 'x': _w(ram, self.CAMERA[0]), 'y': _w(ram, self.CAMERA[1])}

    def watcher(self, watch):
        return _X23Watcher(type(self), watch)

    # Item edits (swap, removal, Heart Tank / Sub Tank changes) are written and unit tested, but no replay proof was
    # run for them before release, so they are not offered. Set to True once proof.py shows changed good, control bad.
    ITEM_EDITS = False

    def objects(self, part):
        """Like Mega Man X's, with these differences: weapon energy is shown (and can become one of the offered
        items) but is not offered itself, because what it refills was not measured; and item edits are only offered
        when ITEM_EDITS is on."""
        level = int(part['level'])
        out = []
        for row in MegaManXProfile.objects(self, part):
            e = self.entries(level)[int(row['id'].split(':')[1])]
            if row['style'] in ('item', 'secret'):
                special = e['id'] in self.SPECIAL
                row['style'] = 'secret' if special else 'item'
                if not special:
                    row.pop('note', None)
                if not self.ITEM_EDITS:
                    row['fields'], row['remove'] = [], None
                    row['note'] = 'ROMancer shows this item but cannot change it yet.'
            out.append(row)
        return out

    def edit(self, part, object_id, values, remove=False):
        if not self.ITEM_EDITS:
            kind, _, number = object_id.partition(':')
            entries = self.entries(int(part['level']))
            if number.isdigit() and int(number) < len(entries) and self.is_item(entries[int(number)]):
                raise ValueError('ROMancer cannot change that yet.')
        return MegaManXProfile.edit(self, part, object_id, values, remove)


# --------------------------------------------------------------------------------------------- Mega Man X2

class MegaManX2Profile(_X23Profile):
    """Mega Man X2 (USA). Level $1FAD: 0 the opening stage, 1-8 the eight stages (by their title cards), 9-12 the
    fortress stages. Lists at $29:D3D1."""
    name = 'Mega Man X2'
    sha256 = 'f3246755f608a1e1dc9c848b61da3b824c7853b29b3be40df6fc7f2793a887ed'
    sha256s = (sha256,)
    LISTS = 0x29D3D1
    BANK = 0x29
    LEVELS = 13
    LEVEL_RAM = 0x1FAD
    LEVEL_NAMES = ['Opening stage', 'Morph Moth stage', 'Wire Sponge stage', 'Bubble Crab stage', 'Flame Stag stage',
                   'Magna Centipede stage', 'Crystal Snail stage', 'Overdrive Ostrich stage', 'Wheel Gator stage',
                   'Fortress 1', 'Fortress 2', 'Fortress 3', 'Fortress 4']
    # Enemies: each type was spawned at its first place in the game and watched for 240 frames with Mega Man held
    # beside it (trace/v15_profiles/megamanx23/look.py; pictures look/x2_*, contact sheet names_x2.png; positions in
    # sv_x2.txt and re_x2.txt). Names come from the picture, "does" from what the slot did. "(likely)" marks a picture
    # that was hard to read; types that draw nothing are named by what they visibly do. Bosses are named by where the
    # game puts them: once in their own stage and once in Fortress 4, the room of boss rematches.
    ENEMIES = {
        0x02: ('Hidden helper, several stages', 'Draws nothing and stays in place.'),
        0x04: ('Hidden helper, opening stage', 'Draws nothing and stays in place.'),
        0x05: ('Hidden helper, opening stage, second kind', 'Draws nothing and stays in place.'),
        0x08: ('Hidden helper, Magna Centipede stage', 'Draws nothing and stays in place.'),
        0x09: ('Hidden roamer', 'Draws nothing where it was watched and moves around widely.'),
        0x0A: ('Hover bike rider', 'Rides a hover bike across the desert and fires shots.'),
        0x0B: ('Fast mover, Morph Moth stage (likely)', 'Moves quickly up and across; the picture did not catch it.'),
        0x0C: ('Crashing debris (likely)', 'Falls in a burst of fire and smoke.'),
        0x0E: ('Falling part (likely)', 'Draws little and drops a long way.'),
        0x10: ('Hidden roamer, Morph Moth stage', 'Draws nothing and moves sideways.'),
        0x11: ('Armored soldier robot', 'Stands in place in the scrap yard.'),
        0x12: ('Glass tube (likely)', 'Stands in place and lights up white after a while.'),
        0x16: ('Junk pile robot', 'Rises out of a heap of scrap and shifts a little.'),
        0x17: ('Green hopping robot', 'Sits in the grass and fires green shots.'),
        0x19: ('Small fish robot', 'Swims toward Mega Man.'),
        0x1A: ('Flower pod turret', 'Rises on a stalk out of the grass and fires shots.'),
        0x1B: ('Column robot (likely)', 'Sits inside a wall column and stays in place.'),
        0x1C: ('Hidden helper, Wire Sponge stage', 'Draws nothing and moves up and down.'),
        0x1D: ('Crystal Snail', 'The Crystal Snail stage boss.'),
        0x1E: ('Bubble Crab', 'The Bubble Crab stage boss.'),
        0x1F: ('Hidden helper, Flame Stag stage', 'Draws nothing, moves a little and goes away after a second.'),
        0x20: ('Purple orb on a stand', 'Stands in place.'),
        0x21: ('Hidden roamer, Wire Sponge stage', 'Draws nothing and moves around, then goes away.'),
        0x22: ('Hidden helper, Flame Stag stage, second kind', 'Draws nothing and stays in place.'),
        0x23: ('Wire Sponge', 'The Wire Sponge stage boss.'),
        0x29: ('Bubble Crab stage part (likely)', 'Draws broken blocks and moves sideways.'),
        0x2B: ('Purple orb on a stand, large (likely)', 'Stands in place.'),
        0x2C: ('Hidden helper, several stages, second kind', 'Draws nothing and moves up and down.'),
        0x2D: ('Wall crawler (likely)', 'Clings to the wall and stays in place.'),
        0x2E: ('Hidden helper, Flame Stag stage, third kind', 'Draws nothing and stays in place.'),
        0x2F: ('Hidden helper, Crystal Snail stage', 'Draws nothing and goes away at once.'),
        0x30: ('Wall pipe vent', 'Sits in the wall and lets out puffs.'),
        0x32: ('Underwater block (likely)', 'Drifts a little sideways under the water.'),
        0x34: ('Magna Centipede', 'The Magna Centipede stage boss.'),
        0x35: ('Overdrive Ostrich', 'The Overdrive Ostrich stage boss.'),
        0x36: ('Hidden stage marker', 'Draws nothing and goes away at once; the game puts one in seven of the stages.'),
        0x37: ('Wall machine (likely)', 'A block of machinery on the wall that stays in place.'),
        0x38: ('Flame Stag', 'The Flame Stag stage boss.'),
        0x39: ('Hidden helper, Magna Centipede stage, second kind', 'Draws nothing and stays in place.'),
        0x3A: ('Crescent drone', 'Flies back and forth along the corridor.'),
        0x3B: ('Morph Moth', 'The Morph Moth stage boss.'),
        0x3C: ('Wheel Gator', 'The Wheel Gator stage boss.'),
        0x3E: ('Overdrive Ostrich stage part (likely)', 'Stays in place.'),
        0x3F: ('Helmeted gunner robot', 'Rides along on a blue platform and fires shots.'),
        0x40: ('Crystal block', 'A block of green crystal that stays in place.'),
        0x42: ('Parked mech (likely)', 'Sits in a bay and stays in place.'),
        0x44: ('Ceiling hanger (likely)', 'Hangs from the cave ceiling and stays in place.'),
        0x45: ('Hidden helper, Wheel Gator stage', 'Draws nothing and stays in place.'),
        0x46: ('Burning wreck', 'A wrecked machine that burns in place.'),
        0x47: ('Sand burst (likely)', 'A cloud of sand that sweeps along the ground and goes away.'),
        0x48: ('Rail foot (likely)', 'Sits at the bottom of a rail and stays in place.'),
        0x49: ('Shield soldier', 'Climbs the tower holding a shield in front.'),
        0x4D: ('Dr. Light capsule (likely)', 'Draws nothing until Mega Man finds it; the game puts one in five places.'),
        0x4F: ('Crystal ledge (likely)', 'A purple crystal ledge that stays in place.'),
        0x50: ('Wall crab (likely)', 'Clings to the rock wall and stays in place.'),
        0x51: ('Green energy gate', 'A frame of green energy that stays in place.'),
        0x52: ('Hidden helper, Overdrive Ostrich stage', 'Draws nothing and stays in place.'),
        0x53: ('Large crystal', 'A big purple crystal that stays in place.'),
        0x54: ('Lit floor panel (likely)', 'A row of lamps in the floor that stays in place.'),
        0x55: ('Yellow energy ball', 'A big yellow ball that rolls along the floor.'),
        0x57: ('Hover platform (likely)', 'Sits on the hill and sends out a flier.'),
        0x58: ('Small cart robot (likely)', 'Rushes along the floor and goes away.'),
        0x59: ('Fortress 3 boss', 'Brings up the boss energy bar and moves up and down.'),
        0x5A: ('Hidden helper, Fortress 1', 'Draws nothing and goes away at once.'),
        0x5B: ('Hidden helper, several stages, third kind', 'Draws nothing and stays in place.'),
        0x61: ('Hidden runner, Fortress 2', 'Draws nothing and moves far to the right.'),
        0x62: ('Blue orb (likely)', 'A small blue ball at the edge of a wall that stays in place.'),
        0x64: ('Scrap robot (likely)', 'Comes into view after a while and stays in place.'),
        0x65: ('Rail wheel robot', 'Rolls up and down the rails toward Mega Man.'),
        0x66: ('Hidden helper, Overdrive Ostrich stage, second kind', 'Draws nothing and stays in place.'),
        0x6A: ('Wall spike shooter (likely)', 'Sits in the spiked wall and stays in place.'),
        0x6D: ('Screen effect (likely)', 'Fills the screen with a pattern that moves.'),
    }
    ENEMY_NAMES = {k: v[0] for k, v in ENEMIES.items()}
    # never offered: the bosses, the capsules, the stage markers and other things placed once or once per stage
    ONCE = (0x1D, 0x1E, 0x23, 0x34, 0x35, 0x38, 0x3B, 0x3C, 0x36, 0x45, 0x4D, 0x62, 0x6D)
    # Items: each (id, sub) was written into Morph Moth stage entry 10 and picked up (trace/v15_profiles/megamanx23/
    # look.py touch; RAM before and after): large life energy $09FF 4 -> 12, small 4 -> 6, 1-Up lives $1FB3 +1,
    # Heart Tank max life $1FD1 16 -> 18 with its bit in $1FD3, Sub Tank its bit in $1FD0 and $1FB6 = $80.
    # Weapon energy (id $01) changed nothing measured and is named from its picture (look/x2_L1_10_0180_view.png).
    ITEMS = {(0x02, 0x80): 'Large life energy', (0x02, 0x82): 'Small life energy', (0x04, 0x80): '1-Up',
             (0x01, 0x80): 'Large weapon energy', (0x01, 0x81): 'Small weapon energy',
             (0x0B, None): 'Heart Tank', (0x05, None): 'Sub Tank'}
    ITEM_DOES = {(0x02, 0x80): 'Restores 8 life energy.', (0x02, 0x82): 'Restores 2 life energy.',
                 (0x04, None): 'Gives one more life.', (0x0B, None): 'Raises the most life energy by 2 and adds 2 life energy.',
                 (0x05, None): 'Gives a Sub Tank, which stores spare life energy for later.'}
    COMMON_ITEMS = [(0x02, 0x80), (0x02, 0x82), (0x04, 0x80)]


# --------------------------------------------------------------------------------------------- Mega Man X3

class MegaManX3Profile(_X23Profile):
    """Mega Man X3 (USA). Level $1FAE: 0 the opening stage, 1-8 the eight stages (in the order of the stage select's
    boss texts), 9-14 the fortress stages. Lists at $3C:CE4B."""
    name = 'Mega Man X3'
    sha256 = '65b03268afac296330e8ff8d60dd0825879e13ed658b37713c034a3bd074f1d7'
    sha256s = (sha256,)
    LISTS = 0x3CCE4B
    BANK = 0x3C
    LEVELS = 15
    LEVEL_RAM = 0x1FAE
    LEVEL_NAMES = ['Opening stage', 'Blast Hornet stage', 'Blizzard Buffalo stage', 'Gravity Beetle stage',
                   'Toxic Seahorse stage', 'Volt Catfish stage', 'Crush Crawfish stage', 'Tunnel Rhino stage',
                   'Neon Tiger stage', 'Fortress 1', 'Fortress 2', 'Fortress 3', 'Fortress 4', 'Fortress 5', 'Fortress 6']
    # Enemies: spawned and watched the same way as X2's (look/x3_*, contact sheet names_x3.png; sv_x3.txt, re_x3.txt,
    # re2_x3.txt). The opening stage showed a white screen where it was watched, so types placed there were looked at
    # in another stage where they also appear. The eight bosses are named by where the game puts them: once in their
    # own stage and once in Fortress 4, which has the eight teleporters to the rematches.
    ENEMIES = {
        0x02: ('Hidden helper, several stages', 'Draws nothing and stays in place.'),
        0x03: ('Hopping cannon robot', 'Hops toward Mega Man and fires its cannon.'),
        0x05: ('Wall drill head (likely)', 'Sticks out of the wall and stays in place.'),
        0x06: ('Cyan cloud (likely)', 'A pale blue cloud that drifts up and down.'),
        0x08: ('Purple cannon robot', 'Stands in place and fires its cannon.'),
        0x09: ('Spiked wall section', 'A wall of spikes that moves up and down.'),
        0x0B: ('Hidden helper, many stages', 'Draws nothing and stays in place.'),
        0x0C: ('Dust cloud (likely)', 'A cloud of dust that stays in place.'),
        0x0D: ('Hidden helper, many stages, second kind', 'Draws nothing and moves up and down.'),
        0x0E: ('Wall eye drone', 'Hovers by the wall and moves a little up and down.'),
        0x0F: ('Hidden helper, Blast Hornet stage', 'Draws nothing and stays in place.'),
        0x11: ('Ceiling crab robot', 'Hangs from the ceiling and shifts a little sideways.'),
        0x16: ('Hidden helper, several stages, second kind', 'Draws nothing and stays in place.'),
        0x18: ('Red gun walker', 'Stands in place and aims its gun.'),
        0x19: ('Hidden helper, Gravity Beetle stage', 'Draws nothing and stays in place.'),
        0x1B: ('Hidden roamer', 'Draws nothing and falls a long way.'),
        0x1C: ('Water blob (likely)', 'Drifts around in the water.'),
        0x1D: ('Cannon tank robot', 'Rolls a little and aims its cannon.'),
        0x1E: ('Heavy armored robot', 'Stands in place and points its arm cannon.'),
        0x1F: ('Wasp robot', 'Flies across toward Mega Man.'),
        0x20: ('Opening stage helper (likely)', 'Stays in place; the screen was white where it was watched.'),
        0x21: ('Small flier, opening stage (likely)', 'Shows for a second and goes away.'),
        0x22: ('Rolling rock (likely)', 'Rolls a short way along the ground.'),
        0x23: ('Hidden helper, Blizzard Buffalo stage', 'Draws nothing and stays in place.'),
        0x24: ('Balloon robot (likely)', 'Hangs in the air and stays in place.'),
        0x25: ('Hidden helper, Gravity Beetle stage, second kind', 'Draws nothing and stays in place.'),
        0x26: ('Hidden helper, Blast Hornet stage, second kind', 'Draws nothing and stays in place.'),
        0x27: ('Claw crab robot', 'Drops down and walks toward Mega Man.'),
        0x28: ('Hidden helper, several stages, third kind', 'Draws nothing and moves a little sideways.'),
        0x29: ('Breaking ice wall (likely)', 'A part of the icy wall that moves.'),
        0x2A: ('Hidden helper, Crush Crawfish stage', 'Draws nothing and stays in place.'),
        0x2B: ('Yellow spark', 'A yellow spark in the cave that stays in place.'),
        0x2C: ('Hidden helper, Blast Hornet stage, third kind', 'Draws nothing and moves up and down.'),
        0x2D: ('Hidden faller', 'Draws nothing and falls a long way.'),
        0x2F: ('Hidden stage visitor', 'Draws nothing where it was watched; the game puts one in most stages.'),
        0x30: ('Crystal lamp (likely)', 'A green crystal in a pillar that stays in place.'),
        0x31: ('Hidden helper, Fortress 1', 'Draws nothing and stays in place.'),
        0x32: ('Pole climber robot', 'Slides up and down a pole.'),
        0x33: ('Falling boulder', 'Drops out of its frame and falls.'),
        0x34: ('Boulder dropper', 'Holds a boulder over the lava.'),
        0x35: ('Boulder rider', 'Rides a big rolling ball and fires shots.'),
        0x36: ('Spike block (likely)', 'A row of spikes that goes away after two seconds.'),
        0x37: ('Hidden helper, Volt Catfish stage', 'Draws nothing and stays in place.'),
        0x38: ('Moving wall section (likely)', 'A part of the wall that slides sideways.'),
        0x39: ('Wall turret (likely)', 'Sits in place and fires shots.'),
        0x3A: ('Hidden helper, Volt Catfish stage, second kind', 'Draws nothing and stays in place.'),
        0x3B: ('Hidden helper, Crush Crawfish stage, second kind', 'Draws nothing and goes away at once.'),
        0x3C: ('Hidden helper, Crush Crawfish stage, third kind', 'Draws nothing and stays in place.'),
        0x3D: ('Ceiling laser', 'Hangs from the ceiling and sweeps a red laser beam.'),
        0x3F: ('Steam vent pipe', 'Blows a jet of steam out of a pipe.'),
        0x40: ('Spiked crusher (likely)', 'A spiked machine by the wall that stays in place.'),
        0x41: ('Hidden helper, Fortress 2', 'Draws nothing and goes away at once.'),
        0x42: ('Hidden helper, Toxic Seahorse stage', 'Draws nothing and stays in place.'),
        0x45: ('Red claw robot (likely)', 'Rises into view with a large claw.'),
        0x46: ('Boss room helper', 'Draws nothing; the game puts one in each of the eight stages.'),
        0x47: ('Boss room helper, second kind', 'Draws nothing; the game puts one in each of the eight stages.'),
        0x48: ('Hidden helper, Fortress 4', 'Draws nothing and stays in place.'),
        0x49: ('Fortress 1 boss', 'Brings up the boss energy bar and fights Mega Man.'),
        0x4A: ('Hidden roamer, Fortress 3', 'Draws nothing and moves around.'),
        0x4B: ('Hidden helper, Blast Hornet stage, fourth kind', 'Draws nothing and goes away at once.'),
        0x4C: ('Parked mech (likely)', 'Stands in the hangar and stays in place.'),
        0x4D: ('Dr. Light capsule (likely)', 'Draws nothing until Mega Man finds it; its setting is one bit, like the Heart Tanks.'),
        0x50: ('Opening stage helper, second kind (likely)', 'Stays in place; the screen was white where it was watched.'),
        0x51: ('Junk machine (likely)', 'A pile of robot parts that moves sideways.'),
        0x52: ('Blizzard Buffalo', 'The Blizzard Buffalo stage boss.'),
        0x53: ('Blast Hornet', 'The Blast Hornet stage boss.'),
        0x54: ('Crush Crawfish', 'The Crush Crawfish stage boss.'),
        0x55: ('Tunnel Rhino', 'The Tunnel Rhino stage boss.'),
        0x56: ('Neon Tiger', 'The Neon Tiger stage boss.'),
        0x57: ('Toxic Seahorse', 'The Toxic Seahorse stage boss.'),
        0x58: ('Volt Catfish', 'The Volt Catfish stage boss.'),
        0x59: ('Gravity Beetle', 'The Gravity Beetle stage boss.'),
        0x5A: ('Fortress 2 boss (likely)', 'Brings up the boss energy bar and moves around.'),
        0x5B: ('Fortress 3 boss (likely)', 'A big red machine that moves across the room.'),
        0x5E: ('Hidden faller, Fortress 5', 'Draws nothing and falls a very long way.'),
        0x62: ('Opening stage roamer (likely)', 'Draws nothing and moves a long way.'),
        0x63: ('Fortress 6 boss (likely)', 'Brings up the boss energy bar and moves up and down.'),
        0x65: ('Hidden helper, Fortress 4, second kind', 'Draws nothing and stays in place.'),
    }
    ENEMY_NAMES = {k: v[0] for k, v in ENEMIES.items()}
    ONCE = (0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x46, 0x47, 0x4D, 0x2F, 0x48)
    # Items: measured the same way in Blizzard Buffalo stage entry 23: large life energy $09FF 4 -> 12, 1-Up lives
    # $1FB4 +1, Heart Tank max life $1FD2 16 -> 18 with its bit in $1FD4, Sub Tank its bit in $1FD1 and $1FB7 = $80.
    # X3 never places small life energy, so it is not offered here.
    ITEMS = {(0x02, 0x80): 'Large life energy', (0x04, 0x80): '1-Up',
             (0x01, 0x80): 'Large weapon energy', (0x01, 0x81): 'Small weapon energy',
             (0x0B, None): 'Heart Tank', (0x05, None): 'Sub Tank'}
    ITEM_DOES = {(0x02, 0x80): 'Restores 8 life energy.', (0x04, None): 'Gives one more life.',
                 (0x0B, None): 'Raises the most life energy by 2 and adds 2 life energy.',
                 (0x05, None): 'Gives a Sub Tank, which stores spare life energy for later.'}
    COMMON_ITEMS = [(0x02, 0x80), (0x04, 0x80)]


# Mega Man X3 is decoded and named but none of its edits was replayed before release, so only X2 is registered.
PROFILES = [MegaManX2Profile]
