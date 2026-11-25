"""What ROMancer knows about the levels of Mega Man 6 (NES): each stage's sections, and the enemies and items the stage
places, read from the game's own tables (research/megaman6-level-profile.md).

Mega Man 6 keeps every stage's object list in one 8 KB bank ($3A): four arrays (screen, x, y, type) with a pointer and a
count per stage. The spawner (bank $3A $8120-$822E) places a record when the camera's right edge reaches its screen and
x and keeps the record's number in the object slot. Records of type $80 are not objects: they start the stage's room
script (bank $39 $824D, script number = the record's y), which says whether the camera may scroll on to the next screen
and which ladders, pits and doors lead on. The sections below follow those scripts.
"""
from __future__ import annotations

from .megaman import _MegaMan3On

LIST_BANK = 0x3A            # object lists and the spawner
SCRIPT_BANK = 0x39          # room scripts


class MegaMan6(_MegaMan3On):
    """Mega Man 6 (USA). Records: bank $3A, pointer $80BF/$80CF + stage, count $80DF + stage; the block at the pointer is
    [pad, screen * n, $FF, x * n, pad, y * n, pad, type * n] (spawner init $8032). A spawned record: slot X $08-$15,
    $03A0 type, $03FC record number ($FF none), x $046F/$0486, y $04CB. Type $80 records are room scripts (script table
    $82EB/$836B in bank $39): byte 0 bit 0 lets the camera scroll right past the screen, then transitions of 3 or 4
    bytes (1 fall to the screen below, 2 climb to the screen above, 3 and 4 back, 5 door on the right, 6 door on the
    left; a byte with bit 7 after them sends the transition to another screen)."""
    name = 'Mega Man 6'
    sha256s = ('6791433fd1c639d3f281522d7ab7d1e80bd01f1cdf99bad42cdf9d25b730f6d8',)
    # $51 measured on the stage select (one direction from the centre, or two one after the other; stg/*.png)
    STAGES = {0: 'Blizzard Man stage', 1: 'Wind Man stage', 2: 'Plant Man stage', 3: 'Flame Man stage', 4: 'Yamato Man stage',
              5: 'Tomahawk Man stage', 6: 'Knight Man stage', 7: 'Centaur Man stage'}
    # pickups from their code in bank $3B (all start with JSR $9245): life energy $03E5 + 2 or + 10 (at most 28), weapon
    # energy $0688 + weapon + 2 or + 10, $A9 + 1 (lives, 2 at the start of a game, at most 9), $06A1 + 1 (at most 9);
    # pictures in trace/v15_profiles/megaman6/items.png
    NAMES = {0x38: 'Small life energy', 0x39: 'Large life energy', 0x49: 'Small weapon energy', 0x4A: 'Large weapon energy',
             0x37: 'Extra life', 0x1D: 'Energy Tank'}
    ITEM_DOES = {0x38: 'Restores 2 units of life energy.', 0x39: 'Restores 10 units of life energy.',
                 0x49: 'Restores 2 units of the weapon in use.', 0x4A: 'Restores 10 units of the weapon in use.',
                 0x37: 'Gives one extra life (at most 9).', 0x1D: 'Adds one Energy Tank (at most 9).'}
    # Enemies. The type number picks the enemy's code, but each stage loads its own pictures, so one number can look like a
    # different enemy in another stage. Names and does-lines come from giving each stage's first screen-1 record (the
    # first record in a fortress stage) each of the stage's own types, walking up until the game placed it and watching it
    # for 240 frames (trace/v15_profiles/naming_capcom_sml_mm6/mm6/, research/megaman6-level-profile.md).
    STAGE_ENEMIES = {
        0: {0x10: ('Green shell robot', 'Drops into place and fires.'),
            0x12: ('Sliding number block', 'Slides left and right along the floor.'),
            0x13: ('Red propeller robot', 'Hovers in one place.'),
            0x19: ('Number block', 'Stays in place.'),
            0x1E: ('Red-capped capsule robot', 'Slides toward you and drops off ledges.'),
            0x1F: ('Cannon robot with a rider, facing left', 'Stays in place with its cannon pointed left.'),
            0x20: ('Cannon robot with a rider, facing right', 'Stays in place with its cannon pointed right.'),
            0x21: ('Number block, on its side', 'Stays in place.'),
            0x24: ('Propeller capsule robot', 'Flies down to the ground, then moves toward you.'),
            0x4D: ('Blue seal robot', 'Stays in place.')},
        1: {0x1B: ('Green hopping robot', 'Bounces up and down in place.'),
            0x27: ('White bear robot', 'Stays in place and fires shots.'),
            0x29: ('Spiked armadillo robot', 'Rolls back and forth along the floor.'),
            0x2D: ('Hard hat robot with a gun', 'Walks toward you and fires.'),
            0x34: ('Wall cannon', 'Stays in place.'),
            0x36: ('Small red turret', 'Stays in place and fires small pellets sideways.'),
            0x59: ('Large spring robot', 'Jumps high toward you on its spring.'),
            0x75: ('Ceiling crawler', 'Climbs to the ceiling and moves along it toward you.')},
        2: {0x24: ('Orange lantern robot', 'Flies down to the ground, then moves toward you.'),
            0x54: ('Purple bird robot', 'Stays in place.'),
            0x58: ('Purple pod', 'Hangs in one place.'),
            0x59: ('Large spring robot', 'Jumps high toward you on its spring.'),
            0x5F: ('Invisible object', None),
            0x60: ('Yellow bird robot', 'Hops along the ground toward you.'),
            0x61: ('Green propeller robot', 'Flies down at a slant toward you.'),
            0x62: ('Purple flying robot', 'Flies straight across the screen toward you.'),
            0x70: ('Small red helmet robot', 'Waits, then jumps up.')},
        3: {0x18: ('Hard hat (Met)', 'Hides under its helmet and peeks out.'),
            0x2A: ('Fire-headed robot', 'Stays in place and throws fireballs.'),
            0x2B: ('Small orange walker', 'Walks slowly away from you.'),
            0x2C: ('Flame pillar robot', 'Moves straight toward you.'),
            0x73: ('Green hooded walker', 'Walks back and forth.'),
            0xC0: ('Green barrel robot', 'Stays in place.'),
            0xC9: ('Green antenna bug', 'Stays in place.')},
        4: {0x13: ('Red hanging robot', 'Hangs in one place.'),
            0x24: ('Propeller capsule robot', 'Flies down to the ground, then moves toward you.'),
            0x54: ('Blue turret head', 'Stays in place and fires shots.'),
            0x5F: ('Invisible object', None),
            0x69: ('Green rider on a wheel', 'Rolls quickly toward you.'),
            0x75: ('Ceiling crawler', 'Climbs to the ceiling and moves along it toward you.'),
            0xA2: ('Spear-throwing robot', 'Stays in place and throws spears.'),
            0xA7: ('Spring-necked robot', 'Bounces toward you on its spring.'),
            0xC2: ('Orange helmet robot', 'Stays in place and opens up to attack.')},
        5: {0x12: ('Pink flower robot', 'Moves back and forth along the floor.'),
            0x13: ('Red bird robot', 'Stays in place.'),
            0x18: ('Hard hat (Met)', 'Hides under its helmet, then fires three shots.'),
            0x29: ('Green armadillo robot', 'Rolls back and forth along the floor.'),
            0x4F: ('Hard hat (Met) that pops up', 'Pops up from under its helmet and fires.'),
            0x59: ('Large spring robot', 'Jumps high toward you on its spring.'),
            0x66: ('Pink skull walker', 'Walks toward you and fires.'),
            0x67: ('Green cactus robot', 'Hops toward you.'),
            0x6C: ('Cowboy robot', 'Stands in place and fires its gun.'),
            0x6E: ('Blue charging robot', 'Charges straight toward you.'),
            0x70: ('Small red helmet robot', 'Waits, then jumps up.'),
            0x8A: ('Rising post', 'Shoots straight up out of the ground.'),
            0xA0: ('Hovering platform', 'Bobs up and down in one place.'),
            0xA1: ('Green spiked machine', 'Stays in place.')},
        6: {0x29: ('Orange armadillo robot', 'Rolls back and forth along the floor.'),
            0x2D: ('Crown turret', 'Stays in place and fires shots.'),
            0x3C: ('Blue dome walker', 'Walks toward you.'),
            0x3D: ('Orange pot', 'Stays in place.'),
            0x65: ('Green cannon', 'Stays in place and fires.'),
            0x67: ('Skull walker', 'Hops toward you.'),
            0x6E: ('Drill tank', 'Drives straight toward you.'),
            0x70: ('Small red helmet robot', 'Waits, then jumps up.'),
            0x75: ('Ceiling crawler', 'Climbs to the ceiling and moves along it toward you.'),
            0xC6: ('Shield knight robot', 'Walks back and forth behind its shield.')},
        7: {0x10: ('Green shell robot', 'Stays in place and fires.'),
            0x2B: ('Orange dome crab', 'Opens its shell and creeps away from you.'),
            0x70: ('Small red helmet robot', 'Waits, then jumps up.'),
            0xA5: ('Orange submarine robot', 'Swims toward you and fires.'),
            0xA9: ('Dome jellyfish robot', 'Drifts down toward the floor.'),
            0xAB: ('Propeller robot with a claw', 'Flies straight toward you.'),
            0xC1: ('Red robot fish', 'Swims back and forth.'),
            0xC4: ('Teal fish robot', 'Stays in place and throws balls.'),
            0xC9: ('Red shrimp robot', 'Stays in place and fires small shots.')},
        9: {0x18: ('Hard hat (Met)', 'Hides under its helmet and fires.'),
            0x66: ('Helmet walker', 'Walks back and forth.'),
            0x67: ('Skull walker', 'Hops toward you.'),
            0x6E: ('Drill tank', 'Drives straight toward you.')},
        10: {0x1B: ('Green hopping robot', 'Bounces up and down in place.'),
             0x2B: ('Pink dome crab', 'Stays in place.'),
             0x6F: ('Green ring block', 'Stays in place.')},
        12: {0x1B: ('Green hopping robot', 'Bounces up and down in place.'),
             0x20: ('Cannon robot with a rider, facing right', 'Stays in place with its cannon pointed right.'),
             0x2C: ('Flame pillar robot', 'Moves straight toward you.'),
             0x2D: ('Small green antenna robot', 'Shuffles back and forth in place.'),
             0x34: ('Wall cannon', 'Stays in place.'),
             0x36: ('Small red turret', 'Stays in place and fires small pellets sideways.'),
             0x41: ('Small red turret on a barrel', 'Pops up from its barrel and fires.'),
             0x65: ('Green cannon', 'Stays in place and fires.'),
             0xA2: ('Spear-throwing robot', 'Stays in place and throws spears.')},
        13: {0x12: ('Sliding pink block', 'Slides left and right.'),
             0x1E: ('Red-capped capsule robot', 'Slides toward you and drops off ledges.'),
             0x65: ('Green cannon robot', 'Stays in place and fires.'),
             0x8F: ('Small green block', 'Stays in place.'),
             0xC6: ('Shield knight robot', 'Walks back and forth behind its shield.')},
        15: {0x4F: ('Hard hat (Met) that pops up', 'Pops up from under its helmet and fires.'),
             0x54: ('Blue turret head', 'Stays in place and fires shots.')},
    }
    # types that looked and acted the same in every stage where they were watched; the fortress stages (9-16) use these
    # names where their own pictures were not looked at
    SAME_EVERYWHERE = {0x18: ('Hard hat (Met)', 'Hides under its helmet and fires.'),
                       0x70: ('Small red helmet robot', 'Waits, then jumps up.'),
                       0x10: ('Green shell robot', 'Stays in place and fires.'),
                       0x59: ('Large spring robot', 'Jumps high toward you on its spring.'),
                       0x75: ('Ceiling crawler', 'Climbs to the ceiling and moves along it toward you.')}
    PICKUPS = {0x1D, 0x37, 0x38, 0x39, 0x49, 0x4A}
    SCRIPT = 0x80
    LINKS = {0x80: 'Ladder up to the next section', 0x40: 'Way down to the next section'}
    SLACK = 16                  # the spawner places a record once camera + $FE reaches its screen and x ($8120)
    PLAYER_BANK = 0x38          # Mega Man's code bank ($0441) while he is in the stage (3B while beaming in)
    LAST_STAGE = 15

    # ---- tables
    def block(self, stage: int):
        """(offset of the stage's block, record count)."""
        lo = self.byte(LIST_BANK, 0x80BF + stage)
        hi = self.byte(LIST_BANK, 0x80CF + stage)
        return self.bank_offset(LIST_BANK, lo | hi << 8), self.byte(LIST_BANK, 0x80DF + stage)

    @staticmethod
    def array_offsets(start: int, count: int):
        """Offsets of the screen, x, y and type arrays of a block of `count` records."""
        return start + 1, start + count + 2, start + 2 * count + 3, start + 3 * count + 4

    def records(self, stage: int) -> list:
        start, count = self.block(stage)
        screens, xs, ys, kinds = self.array_offsets(start, count)
        last = self.boss_screens(stage, start, count)
        out = []
        for number in range(count):
            screen, x, y, kind = (self.rom[a + number] for a in (screens, xs, ys, kinds))
            out.append({'list': 'record', 'stage': stage, 'number': number, 'type_at': kinds + number, 'screen': screen, 'x': x, 'y': y,
                        'type': kind, 'editable': kind != self.SCRIPT and y < 0xF0 and screen not in last})
        return out

    def boss_screens(self, stage, start=None, count=None):
        """Screens of the boss rooms: screens whose room script is the boss room's (script table entry outside bank
        $39, the one every robot master stage ends with)."""
        if start is None:
            start, count = self.block(stage)
        screens, _, ys, kinds = self.array_offsets(start, count)
        out = set()
        for n in range(count):
            if self.rom[kinds + n] == self.SCRIPT and self.script_address(self.rom[ys + n]) >= 0xA000:
                out.add(self.rom[screens + n])
        return out

    def script_address(self, number: int) -> int:
        return self.byte(SCRIPT_BANK, 0x82EB + number) | self.byte(SCRIPT_BANK, 0x836B + number) << 8

    def script(self, number: int):
        """(flags, [(transition, screen or None)]) of a room script ($824D in bank $39)."""
        address = self.script_address(number)
        if address >= 0xA000:
            return 0, []
        q = lambda i: self.byte(SCRIPT_BANK, address + i)
        flags, at = q(0), 1
        if flags & 0x80:            # a routine runs first; the flags follow its address
            flags, at = q(2), 3
        i, out = at + 2, []
        while 0 < q(i) < 0x80 and len(out) < 8:
            kind = q(i)
            i += 3
            target = None
            if q(i) & 0x80:
                target = q(i) & 0x7F
                i += 1
            out.append((kind, target))
        return flags, out

    def sections(self, stage: int) -> list:
        """Runs of screens the camera scrolls through to the right. The room script in force at the right edge of a screen
        is the last type $80 record at or before that screen; the run goes on to the next screen when the script lets the
        camera scroll right (bit 0) or has a door on the right to the next screen (transition 5 with no other screen)."""
        records = [r for r in self._raw(stage)]
        last = max((r[0] for r in records), default=0)
        scripts = [(screen, y) for screen, x, y, kind in records if kind == self.SCRIPT]
        out, first = [], 0
        for screen in range(last + 1):
            ruling = [y for s, y in scripts if s <= screen]
            flags, moves = self.script(ruling[-1]) if ruling else (0, [])
            goes_on = flags & 1 or any(kind == 5 and target is None for kind, target in moves)
            if goes_on and screen < last:
                continue
            link = 0
            for kind, target in moves:
                if target is None and kind in (1, 2):
                    link = {1: 0x40, 2: 0x80}[kind]
            out.append({'segment': len(out), 'first': first, 'last': screen, 'link': link if screen < last else 0})
            first = screen + 1
        return out

    def _raw(self, stage):
        start, count = self.block(stage)
        screens, xs, ys, kinds = self.array_offsets(start, count)
        return [(self.rom[screens + n], self.rom[xs + n], self.rom[ys + n], self.rom[kinds + n]) for n in range(count)]

    def stage_bank(self, stage):
        return LIST_BANK

    # ---- where the game is
    def stage_of(self, ram):
        return ram[0x51]

    def camera(self, ram):
        return ram[0x57] * 256 + ram[0x56]

    def where(self, ram):
        stage = ram[0x51]
        if stage > self.LAST_STAGE or ram[0x3A0] == 0 or ram[0x441] != self.PLAYER_BANK or ram[0x58] != 0:
            return None             # Mega Man is not in the stage (menus, beaming in) or the screen scrolls up or down
        screen = ram[0x57]
        for number, here in enumerate(self.sections(stage)):
            if here['first'] <= screen <= here['last']:
                return {'part': {'stage': stage, 'section': number}, 'x': (screen - here['first']) * 256 + ram[0x56], 'y': 0}
        return None

    def part_name(self, part):
        stage = int(part['stage'])
        return f'{self.STAGES.get(stage, f"Stage {stage + 1}")}, section {int(part["section"]) + 1}'

    # ---- what can be chosen
    def all_records(self):
        for stage in range(self.LAST_STAGE + 1):
            yield from (r for r in self.records(stage) if r['editable'])

    def choice_list(self, record):
        """Items swap among the pickups; an enemy swaps for another enemy of the same stage (the stage loads only its own
        enemies' graphics)."""
        return 'items' if self.is_item(record) else f'enemies {record["stage"]}'

    def choices(self):
        if not hasattr(self, '_choices'):
            found = {}
            for stage in range(self.LAST_STAGE + 1):
                for record in self.records(stage):
                    if record['editable']:
                        found.setdefault(self.choice_list(record), set()).add(record['type'])
            found['items'] = set(self.PICKUPS)
            stage_of = lambda name: int(name.split()[1]) if name.startswith('enemies ') else None
            self._choices = {name: [{'value': k, 'name': self.type_name(k, stage_of(name))} for k in sorted(kinds)]
                             for name, kinds in found.items()}
        return self._choices

    def type_name(self, kind, stage=None):
        if kind in self.NAMES:
            return self.NAMES[kind]
        found = self.STAGE_ENEMIES.get(stage, {}).get(kind) or self.SAME_EVERYWHERE.get(kind)
        if found:
            return found[0]
        return f'{"Item" if kind in self.PICKUPS else "Enemy"} {kind:#04x}'

    def does(self, kind, stage=None):
        """One plain sentence on what the type does in that stage, or None when it was not watched."""
        if kind in self.ITEM_DOES:
            return self.ITEM_DOES[kind]
        found = self.STAGE_ENEMIES.get(stage, {}).get(kind) or self.SAME_EVERYWHERE.get(kind)
        return found[1] if found else None

    def objects(self, part):
        stage = int(part['stage'])
        out = super().objects(part)
        for o in out:
            if o['id'].startswith('record:'):
                o['name'] = self.type_name(o['type'], stage)
                does = self.does(o['type'], stage)
                if does:
                    o['does'] = does
        return out

    def edit(self, part, object_id, values, remove=False):
        """The shared edit, with the stage's own names in the title."""
        plan = super().edit(part, object_id, values, remove)
        stage, watch = int(part['stage']), plan['watch']
        old = self.type_name(watch['old'], stage)
        if remove:
            plan['title'] = f'Remove the {old[0].lower()}{old[1:]}'
        else:
            new = self.type_name(watch['new'], stage)
            plan['title'] = f'{old} becomes {new[0].lower()}{new[1:]}'
            watch['name'] = new
        return plan

    # ---- edits
    def remove_writes(self, stage, record):
        """The stage's block is written again with one record fewer (each array moves up, the end mark stays $FF) and
        the stage's count goes down by one. The four bytes freed at the end of the block become $FF. Nothing else holds
        record numbers: restarts find their first record by screen ($8250) and the taken-object bits ($0650) are RAM."""
        start, count = self.block(stage)
        arrays = [list(self.rom[a:a + count]) for a in self.array_offsets(start, count)]
        for column in arrays:
            del column[record['number']]
        new = [self.rom[start]]
        pads = [0xFF, self.rom[start + 2 * count + 2], self.rom[start + 3 * count + 3]]
        for k, column in enumerate(arrays):
            new += column
            if k < 3:
                new.append(pads[k])
        new += [0xFF] * 4
        writes = [(start + i, self.rom[start + i], v) for i, v in enumerate(new) if self.rom[start + i] != v]
        at = self.bank_offset(LIST_BANK, 0x80DF + stage)
        writes.append((at, self.rom[at], count - 1))
        return writes

    def signature(self, kind):
        return kind

    def slots(self, ram):
        """Slots $08-$15 holding a placed record: (slot, 'record', record number $03FC, type $03A0, world x)."""
        return [(slot, 'record', ram[0x3FC + slot], ram[0x3A0 + slot], ram[0x46F + slot] * 256 + ram[0x486 + slot])
                for slot in range(0x08, 0x16) if ram[0x3A0 + slot] and ram[0x3FC + slot] != 0xFF]

    @staticmethod
    def slot_y(ram, slot):
        return ram[0x4CB + slot]


PROFILES = [MegaMan6]
