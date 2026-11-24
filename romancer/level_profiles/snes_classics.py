"""Super Nintendo classics: Super Mario World (USA) and Super Metroid (Japan, USA).

Both cartridges are LoROM without a copier header: CPU address $BB:8000-$BB:FFFF is ROM offset BB * $8000 + (address
& $7FFF). The snapshots give the system RAM as 'wram' (128 KB): index 0 is $7E:0000 and index $10000 is $7F:0000.

The level layouts are left alone here, except for single bytes that name what one block or one exit holds (see the
notes on each). Research notes: research/snes_classics-level-profile.md.
"""
from __future__ import annotations

from . import Profile, Watcher


def lorom(address: int) -> int:
    """ROM offset of a LoROM CPU address."""
    return ((address >> 16) & 0x7F) * 0x8000 + (address & 0x7FFF)


# --------------------------------------------------------------------------------------------- Super Mario World

class SuperMarioWorld:
    """Super Mario World (USA). Level loading: $05D8B7 (bank 5). Sprite loader: $02A7FC (bank 2). Objects: $0585FF.

    A level number (0-$1FF) picks two things from tables in bank 5:
    * $05E000 + level * 3: the layer 1 data (a 5-byte header, then objects of 3 bytes, $FF ends it)
    * $05EC00 + level * 2: the sprite list in bank 7 (a header byte, then 3 bytes per sprite, $FF ends it)
    Sprite entry: byte 0 = row (high nibble), extra bits (bits 2-3), screen bit 4 (bit 1), high bit of the row (bit 0);
    byte 1 = column (high nibble) and screen (low nibble); byte 2 = sprite number. In vertical levels the row and column
    swap. The list is sorted by screen; the loader writes the entry's index to $161A of the sprite slot it fills.
    """
    name = 'Super Mario World'
    sha256 = '0838e531fe22c077528febe14cb3ff7c492f1f5fa8de354192bdff7137c27f5b'
    LAYER1 = 0x05E000
    SPRITES = 0x05EC00
    MODE_FLAGS = 0x058417       # per level mode: bit 0 = vertical level ($5B)
    LEVELS = 0x200
    # screen exits ($0DA512): extended object 0, 4 bytes; byte 3 is where it leads ($19B8 + screen)
    # single blocks ($0DA57B): extended objects $10-$42 put one Map16 tile (table $0DA548) in the level
    SCREEN_MAPS = (0x00BEA8, 0x00BEAC)  # RAM addresses of each screen's blocks, low and high bytes

    # Sprite names: each was spawned in a level that uses it and looked at (trace/v15_profiles/snes_classics/spawn).
    NAMES = {
        0x00: 'Green Koopa without a shell', 0x01: 'Red Koopa without a shell', 0x02: 'Blue Koopa without a shell',
        0x03: 'Yellow Koopa without a shell', 0x04: 'Green Koopa', 0x05: 'Red Koopa', 0x06: 'Blue Koopa',
        0x07: 'Yellow Koopa', 0x08: 'Green Paratroopa', 0x09: 'Green Paratroopa', 0x0A: 'Red Paratroopa',
        0x0B: 'Red Paratroopa', 0x0C: 'Yellow Paratroopa', 0x0E: 'Keyhole', 0x0F: 'Goomba', 0x10: 'Winged Goomba',
        0x11: 'Buzzy Beetle', 0x13: 'Spiny', 0x15: 'Cheep Cheep', 0x16: 'Cheep Cheep', 0x18: 'Cheep Cheep (likely)',
        0x1D: 'Hopping flame', 0x1E: 'Lakitu', 0x2A: 'Upside-down Piranha Plant', 0x2C: 'Yoshi egg',
        0x2E: 'Spike Top', 0x2F: 'Springboard', 0x3A: 'Urchin', 0x3B: 'Urchin', 0x3C: 'Urchin', 0x3D: 'Rip Van Fish',
        0x3E: 'P-switch', 0x3F: 'Goomba with a parachute', 0x40: 'Bob-omb with a parachute', 0x41: 'Dolphin',
        0x42: 'Dolphin', 0x43: 'Dolphin', 0x46: "Diggin' Chuck", 0x47: 'Cheep Cheep (likely)', 0x48: "Diggin' Chuck's rock",
        0x49: 'Pipe that grows and shrinks', 0x4B: 'Lakitu without a cloud', 0x4D: 'Monty Mole', 0x4E: 'Monty Mole',
        0x4F: 'Jumping Piranha Plant', 0x50: 'Jumping Piranha Plant', 0x55: 'Checkered platform',
        0x57: 'Checkered platform', 0x59: 'Turn block bridge', 0x5A: 'Turn block bridge',
        0x5F: 'Brown platform on a chain', 0x61: 'Skull raft', 0x62: 'Brown platform', 0x63: 'Brown platform',
        0x64: 'Rope', 0x68: 'Fuzzy', 0x6E: 'Dino Rhino', 0x6F: 'Dino Torch', 0x70: 'Pokey', 0x72: 'Super Koopa',
        0x73: 'Super Koopa', 0x74: 'Mushroom', 0x75: 'Fire flower', 0x76: 'Star', 0x77: 'Feather',
        0x78: '1-Up mushroom', 0x7B: 'Goal tape', 0x80: 'Key', 0x82: 'Bonus game', 0x83: 'Flying question block',
        0x84: 'Flying question block', 0x86: 'Wiggler', 0x8A: 'Bird', 0x91: 'Chuck', 0x92: 'Chuck', 0x93: 'Chuck',
        0x94: 'Chuck', 0x95: 'Chuck', 0x97: 'Chuck', 0x98: 'Chuck', 0x99: 'Volcano Lotus', 0x9A: 'Sumo Bro',
        0x9C: 'Flying grey blocks', 0x9D: 'Bubble with an enemy inside', 0x9F: 'Banzai Bill', 0xA5: 'Fuzzy (likely)',
        0xAB: 'Rex', 0xB7: 'Carrot lift', 0xB8: 'Carrot lift', 0xB9: 'Message block', 0xBA: 'Timed lift',
        0xBE: 'Swooper', 0xBF: 'Mega Mole', 0xC1: 'Flying grey blocks', 0xC2: 'Blurp', 0xC3: 'Porcu-Puffer',
        0xC4: 'Grey falling platform', 0xDA: 'Green Koopa shell', 0xDB: 'Red Koopa shell', 0xDC: 'Blue Koopa shell',
        0xDD: 'Yellow Koopa shell'}
    ITEMS = {0x2C, 0x2F, 0x3E, 0x74, 0x75, 0x76, 0x77, 0x78, 0x80, 0x83, 0x84, 0xB9, 0xDA, 0xDB, 0xDC, 0xDD}
    # what the sprite loader does with numbers of $C9 and up ($02A86A-$02A8D4)
    SHOOTERS = range(0xC9, 0xCB)        # $02AB78
    GENERATORS = range(0xCB, 0xDA)      # $18B9 = number - $CA: a generator that keeps making sprites
    SHELLS = range(0xDA, 0xDE)          # spawned as a shell: number - $DA + 4, status 9
    SCROLLERS = range(0xE7, 0x100)      # $143E = number - $E7: a layer scroll command
    # Single blocks that give something when hit: extended object -> (Map16 tile the level gets, what comes out). Each was
    # put in level $105 and hit by Mario, small and big (trace/v15_profiles/snes_classics/blocks.py, blocks/results*.txt):
    # the sprite that came out is named above; the tile is what the game wrote to the level's RAM for it.
    BLOCKS = {
        0x11: (0x022, 'Invisible block with a 1-Up mushroom'), 0x17: (0x12D, 'Green star block with a coin'),
        0x23: (0x111, 'Note block with a mushroom or flower'), 0x28: (0x117, 'Turn block with a mushroom or flower'),
        0x29: (0x118, 'Turn block with a mushroom or feather'), 0x2A: (0x119, 'Turn block with a star'),
        0x2B: (0x11A, 'Turn block with a coin'), 0x2C: (0x11B, 'Turn block with several coins'),
        0x2D: (0x11C, 'Turn block with a coin'), 0x2F: (0x11D, 'Turn block with a P-switch'),
        0x30: (0x11F, 'Question block with a mushroom or flower'), 0x31: (0x120, 'Question block with a mushroom or feather'),
        0x32: (0x121, 'Question block with a star'), 0x33: (0x122, 'Question block with a coin'),
        0x34: (0x123, 'Question block with several coins'), 0x36: (0x126, 'Question block with a Yoshi egg'),
        0x37: (0x127, 'Question block with a Koopa shell'), 0x38: (0x128, 'Question block with a Koopa shell')}

    def __init__(self, rom: bytes):
        self.rom = rom
        self._lists = None
        self._cache = {}

    # ---- reading
    def b(self, address: int) -> int:
        return self.rom[lorom(address)]

    def w(self, address: int) -> int:
        return self.b(address) | self.b(address + 1) << 8

    def l(self, address: int) -> int:
        return self.w(address) | self.b(address + 2) << 16

    def header(self, level: int) -> list:
        start = self.l(self.LAYER1 + level * 3)
        return [self.b(start + i) for i in range(5)]

    def vertical(self, level: int) -> bool:
        return bool(self.b(self.MODE_FLAGS + (self.header(level)[1] & 0x1F)) & 1)

    def sprite_gfx(self, level: int) -> int:
        return self.header(level)[2] & 0x0F

    def list_address(self, level: int) -> int:
        return 0x070000 | self.w(self.SPRITES + level * 2)

    def sprite_list(self, level: int) -> list:
        """[{'index', 'offset', 'number', 'x', 'y', 'extra', 'screen'}] in level pixels (top left of the sprite)."""
        address, out = self.list_address(level) + 1, []
        vertical = self.vertical(level)
        while self.b(address) != 0xFF and len(out) < 128:
            b0, b1, number = self.b(address), self.b(address + 1), self.b(address + 2)
            screen = (b0 >> 1 & 1) << 4 | (b1 & 0x0F)
            along, across = screen * 256 + (b1 & 0xF0), (b0 & 1) << 8 | (b0 & 0xF0)
            x, y = (across, along) if vertical else (along, across)
            out.append({'index': len(out), 'offset': lorom(address), 'number': number, 'x': x, 'y': y,
                        'extra': b0 >> 2 & 3, 'screen': screen})
            address += 3
        return out

    def list_users(self, level: int) -> list:
        """Every level that uses the same sprite list."""
        if self._lists is None:
            self._lists = {}
            for other in range(self.LEVELS):
                self._lists.setdefault(self.list_address(other), []).append(other)
        return self._lists.get(self.list_address(level), [level])

    def layer1_objects(self, level: int) -> list:
        """The layer 1 objects with their screen ($1928): [{'offset', 'screen', 'row', 'col', 'number', 'ext', 'size'}]."""
        if ('l1', level) in self._cache:
            return self._cache[('l1', level)]
        address = self.l(self.LAYER1 + level * 3) + 5
        out, screen = [], 0
        for _ in range(4000):
            b0 = self.b(address)
            if b0 == 0xFF:
                break
            b1, b2 = self.b(address + 1), self.b(address + 2)
            if b0 & 0x80:
                screen += 1
            number = (b0 & 0x60) >> 1 | b1 >> 4
            size = 4 if number == 0 and b2 == 0 else 3
            if number == 0 and b2 == 1:             # screen jump
                screen = b0 & 0x1F
            out.append({'offset': lorom(address), 'screen': screen, 'row': b0 & 0x1F, 'col': b1 & 0x0F, 'number': number,
                        'ext': b2 if number == 0 else None, 'size': size,
                        'bytes': bytes(self.b(address + i) for i in range(size))})
            address += size
        self._cache[('l1', level)] = out
        return out

    def exits(self, level: int) -> list:
        """Screen exits: [{'offset' (of the byte that says where it leads), 'screen', 'to', 'secondary'}]."""
        out = []
        for obj in self.layer1_objects(level):
            if obj['ext'] == 0:
                out.append({'offset': obj['offset'] + 3, 'screen': obj['row'], 'to': obj['bytes'][3],
                            'secondary': bool(obj['bytes'][1] & 2)})
        return out

    def block_name(self, ext: int) -> str:
        name = self.BLOCKS[ext][1]
        if sum(1 for v in self.BLOCKS.values() if v[1] == name) > 1:
            return f'{name} ({ext:#04x})'
        return name

    def blocks(self, level: int) -> list:
        """Single blocks that give something when hit (the extended objects in BLOCKS)."""
        if self.vertical(level):
            return []
        out = []
        for obj in self.layer1_objects(level):
            ext = obj['ext']
            if ext in self.BLOCKS:
                out.append({**obj, 'tile': self.BLOCKS[ext][0], 'x': obj['screen'] * 256 + obj['col'] * 16,
                            'y': obj['row'] * 16})
        return out

    def block_ram(self, level: int, screen: int, row: int, col: int) -> tuple:
        """RAM indexes (low byte, high byte) of a block in the decoded level, from the game's own screen tables."""
        mode = self.header(level)[1] & 0x1F
        places = []
        for table in self.SCREEN_MAPS:
            per_mode = self.w(table)
            screens = self.w(per_mode + mode * 2)
            base = self.l(screens + screen * 3)
            places.append(base + (0x100 if row & 0x10 else 0) + (row & 0x0F) * 16 + col - 0x7E0000)
        return tuple(places)

    def main_level(self, translevel: int, submap: int) -> int:
        """The level the overworld enters ($05D8A2): translevels of $25 and up are levels 1 onward."""
        low = translevel - 0x24 if translevel >= 0x25 else translevel
        return low | (0x100 if submap else 0)

    def level_of(self, ram):
        """Which level the game is playing, from the sprite list pointer ($CE) and the header values the loader keeps."""
        if ram[0xD0] != 0x07:
            return None
        pointer = 0x070000 | ram[0xCE] | ram[0xCF] << 8
        found = [lv for lv in range(self.LEVELS) if self.list_address(lv) == pointer]
        if not found:
            return None
        exact = [lv for lv in found if self._header_matches(lv, ram)]
        found = exact or found
        if len(found) > 1:
            main = self.main_level(ram[0x13BF], ram[0x1F11 + (ram[0x0DD6] >> 2)])
            if main in found:
                return main
            exits = [lv for lv in found if all(ram[0x19B8 + e['screen']] == e['to'] for e in self.exits(lv))]
            found = exits or found
        return found[0]

    def _header_matches(self, level, ram) -> bool:
        h = self.header(level)
        return (ram[0x1925] == h[1] & 0x1F and ram[0x192B] == h[2] & 0x0F and ram[0x1931] == h[4] & 0x0F
                and ram[0x1930] == h[0] >> 5)

    def kind(self, number: int) -> str:
        if number in self.SHOOTERS:
            return 'shooter'
        if number in self.GENERATORS:
            return 'generator'
        if number in self.SCROLLERS:
            return 'scroller'
        if number < 0xC9 or number in self.SHELLS:
            return 'sprite'
        return 'special'

    def sprite_name(self, number: int) -> str:
        name = self.NAMES.get(number)
        if not name:
            return f'Sprite {number:#04x}'
        if sum(1 for v in self.NAMES.values() if v == name) > 1:      # several numbers look alike: keep them apart
            return f'{name} ({number:#04x})'
        return name

    def swap_choices(self, gfx: int) -> list:
        """Sprites the game itself places in levels with this sprite graphics set (so they draw right), one per number."""
        if ('swap', gfx) not in self._cache:
            seen = set()
            for level in range(self.LEVELS):
                if self.sprite_gfx(level) != gfx:
                    continue
                for entry in self.sprite_list(level):
                    if self.kind(entry['number']) == 'sprite':
                        seen.add(entry['number'])
            self._cache[('swap', gfx)] = sorted(seen)
        return self._cache[('swap', gfx)]

    def remove_writes(self, level: int, index: int) -> list:
        """Take one entry out of the list: the later entries move up, $FF ends the list one entry sooner."""
        entries = self.sprite_list(level)
        start = entries[index]['offset']
        end = lorom(self.list_address(level)) + 1 + 3 * len(entries)      # the $FF
        old = self.rom[start:end + 1]
        new = self.rom[start + 3:end] + b'\xff' * 4
        return [(start + i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]


class _SmwSpriteWatcher(Watcher):
    """A sprite edit. A swap is seen when a sprite slot filled from that list entry ($161A = index, $14C8 not 0) holds
    the chosen number ($9E). A removal is seen when the camera has passed the spot and no sprite of that number appeared
    there (slots are checked for where each sprite first shows, $E4/$14E0 x and $D8/$14D4 y)."""
    every = 3

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.reached = 0
        self.slots = {}

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x100] != 0x14 or ram[0xD0] != 0x07 or (ram[0xCE] | ram[0xCF] << 8) != w['list'] & 0xFFFF:
            return False
        if w['remove']:
            for slot in range(12):
                status = ram[0x14C8 + slot]
                key = (ram[0x161A + slot], ram[0x9E + slot])
                if not status:
                    self.slots.pop(slot, None)
                    continue
                if self.slots.get(slot) == key:
                    continue
                self.slots[slot] = key
                x = ram[0xE4 + slot] | ram[0x14E0 + slot] << 8
                y = ram[0xD8 + slot] | ram[0x14D4 + slot] << 8
                if key[1] == w['shown'] and abs(x - w['x']) <= 8 and abs(y - w['y']) <= 8:
                    self.seen = 'there'
                    return True
            camera = (ram[0x1C] | ram[0x1D] << 8) if w['vertical'] else (ram[0x1A] | ram[0x1B] << 8)
            spot = w['y'] if w['vertical'] else w['x']
            if camera <= spot <= camera + 224:
                self.reached += 1
                if self.reached > 30:
                    self.seen = 'gone'
                    return True
            return False
        for slot in range(12):
            if ram[0x14C8 + slot] and ram[0x161A + slot] == w['index']:
                self.seen = ram[0x9E + slot]
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
                    else f'Played from the start, a {w["name"]} still appears there.'}
        ok = self.seen == w['shown']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now puts {w["name"]} there.' if ok
                else f'Played from the start, the game put sprite {self.seen:#04x} there, not the one chosen.'}


class _SmwRamWatcher(Watcher):
    """A block or exit edit: once the level has loaded, the game's own decoded copy in RAM (the level's blocks at
    $7EC800/$7FC800, or the screen exit table at $19B8) must show the chosen value."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x100] != 0x14 or ram[0xD0] != 0x07 or (ram[0xCE] | ram[0xCF] << 8) != w['list'] & 0xFFFF:
            return False
        if w['kind'] == 'exit':
            self.seen = ram[0x19B8 + w['screen']]
        else:
            low, high = w['ram']
            self.seen = ram[low] | (ram[high] & 1) << 8
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        ok = self.seen == w['value']
        if w['kind'] == 'exit':
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the level loads with this exit leading to {w["name"]}.' if ok
                    else f'Played from the start, the level loads with this exit leading to {self.seen:#04x}, not the one chosen.'}
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the level loads with a {w["name"][0].lower() + w["name"][1:]} here.' if ok
                else f'Played from the start, the level loads with block tile {self.seen:#05x} there, not the one chosen.'}


class SuperMarioWorldProfile(SuperMarioWorld, Profile):
    """Parts are {'level': number}; x and y are the level's pixels (the camera is $1A/$1C)."""
    sha256s = (SuperMarioWorld.sha256,)
    system = 'snes'

    def __init__(self, rom: bytes):
        SuperMarioWorld.__init__(self, rom)

    def where(self, ram):
        if ram[0x100] != 0x14:
            return None
        level = self.level_of(ram)
        if level is None:
            return None
        return {'part': {'level': level}, 'x': ram[0x1A] | ram[0x1B] << 8, 'y': ram[0x1C] | ram[0x1D] << 8}

    def part_name(self, part):
        return f'Level {part["level"]:03X}'

    def choices(self):
        out = {}
        for gfx in sorted({self.sprite_gfx(lv) for lv in range(self.LEVELS)}):
            out[f'sprites{gfx}'] = [{'value': n, 'name': self.sprite_name(n)} for n in self.swap_choices(gfx)]
        out['blocks'] = [{'value': ext, 'name': self.block_name(ext)} for ext in sorted(self.BLOCKS)]
        return out

    def objects(self, part):
        level = int(part['level'])
        out = []
        users = self.list_users(level)
        gfx = self.sprite_gfx(level)
        for entry in self.sprite_list(level):
            number, kind = entry['number'], self.kind(entry['number'])
            row = {'id': f'sprite:{entry["index"]}', 'style': 'item' if number in self.ITEMS else 'enemy', 'type': number,
                   'x': entry['x'] + 8, 'y': entry['y'] + 16, 'name': self.sprite_name(number), 'remove': None, 'fields': []}
            if kind == 'sprite':
                row['remove'] = 'Remove this sprite'
                row['fields'] = [{'key': 'number', 'label': 'Swap for', 'value': number, 'choices': f'sprites{gfx}'}]
            else:
                row['note'] = {'shooter': 'A shooter: it fires from this spot while it is on screen.',
                               'generator': 'A generator: from here on it keeps sending sprites for the rest of the level.',
                               'scroller': 'A scroll command: it moves a layer of the level from here on.',
                               'special': 'A group the game places as one entry.'}[kind]
            if entry['extra']:
                row['detail'] = f'extra setting {entry["extra"]}'
            if len(users) > 1:
                others = ', '.join(f'{u:03X}' for u in users if u != level)
                row['note'] = ((row['note'] + ' ') if row.get('note') else '') + \
                    f'This sprite list is shared with level {others}, so a change shows there too.'
            out.append(row)
        for block in self.blocks(level):
            out.append({'id': f'block:{block["offset"]:x}', 'style': 'secret', 'type': block['tile'], 'x': block['x'] + 8,
                        'y': block['y'] + 16, 'name': self.block_name(block['ext']), 'remove': None,
                        'fields': [{'key': 'ext', 'label': 'Block', 'value': block['ext'], 'choices': 'blocks'}]})
        for ex in self.exits(level):
            choices = self.exit_choices(level, ex)
            if not choices:
                continue
            vertical = self.vertical(level)
            out.append({'id': f'exit:{ex["screen"]}', 'style': 'block', 'type': 'exit',
                        'x': 128 if vertical else ex['screen'] * 256 + 128, 'y': ex['screen'] * 256 + 128 if vertical else 400,
                        'name': 'Screen exit', 'detail': f'leads to {self.exit_name(level, ex["to"], ex["secondary"])}',
                        'note': 'Every door and pipe on this screen that leads out uses this exit.', 'remove': None,
                        'fields': [{'key': 'to', 'label': 'Leads to', 'value': ex['to'], 'choices': choices}]})
        return out

    def exit_name(self, level: int, to: int, secondary: bool) -> str:
        if secondary:
            return f'secondary entrance {to:02X}'
        return f'level {(to | (level & 0x100)):03X}'

    def exit_choices(self, level: int, ex: dict) -> list:
        """Places other screen exits of the same kind (level or secondary entrance) on the same map half lead to."""
        key = ('exits', level >> 8, ex['secondary'])
        if key not in self._cache:
            seen = set()
            for other in range(self.LEVELS):
                if other >> 8 != level >> 8:
                    continue
                for e in self.exits(other):
                    if e['secondary'] == ex['secondary']:
                        seen.add(e['to'])
            self._cache[key] = sorted(seen)
        return [{'value': v, 'name': self.exit_name(level, v, ex['secondary']).capitalize()} for v in self._cache[key]]

    def edit(self, part, object_id, values, remove=False):
        level = int(part['level'])
        kind, _, number = object_id.partition(':')
        base = {'list': self.list_address(level), 'level': level}
        if kind == 'sprite':
            index = int(number)
            entries = self.sprite_list(level)
            if not 0 <= index < len(entries):
                raise ValueError('That is not part of this level any more. Reopen the map.')
            entry = entries[index]
            if self.kind(entry['number']) != 'sprite':
                raise ValueError('ROMancer cannot change that yet.')
            if remove:
                return {'writes': self.remove_writes(level, index), 'title': f'Remove the {self.sprite_name(entry["number"])}',
                        'watch': {**base, 'kind': 'sprite', 'remove': True, 'index': index, 'shown': self.shown(entry['number']),
                                  'x': entry['x'], 'y': entry['y'], 'vertical': self.vertical(level),
                                  'name': self.sprite_name(entry['number'])}}
            new = int(values.get('number', entry['number']))
            if new not in self.swap_choices(self.sprite_gfx(level)):
                raise ValueError('That choice is not one of the game’s own.')
            offset = entry['offset'] + 2
            writes = [(offset, self.rom[offset], new)] if self.rom[offset] != new else []
            return {'writes': writes, 'title': f'Sprite here: {self.sprite_name(new)}',
                    'watch': {**base, 'kind': 'sprite', 'remove': False, 'index': index, 'shown': self.shown(new),
                              'name': self.sprite_name(new)}}
        if kind == 'block':
            block = next((b for b in self.blocks(level) if f'{b["offset"]:x}' == number), None)
            if block is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            new = int(values.get('ext', block['ext']))
            if new not in self.BLOCKS:
                raise ValueError('That choice is not one of the game’s own.')
            offset = block['offset'] + 2
            writes = [(offset, self.rom[offset], new)] if self.rom[offset] != new else []
            name = self.block_name(new)
            return {'writes': writes, 'title': f'Block here: {name}',
                    'watch': {**base, 'kind': 'block', 'ram': self.block_ram(level, block['screen'], block['row'], block['col']),
                              'value': self.BLOCKS[new][0], 'name': name}}
        if kind == 'exit':
            screen = int(number)
            ex = next((e for e in self.exits(level) if e['screen'] == screen), None)
            if ex is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            new = int(values.get('to', ex['to']))
            if new not in [c['value'] for c in self.exit_choices(level, ex)]:
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(ex['offset'], self.rom[ex['offset']], new)] if self.rom[ex['offset']] != new else []
            name = self.exit_name(level, new, ex['secondary'])
            return {'writes': writes, 'title': f'Screen exit leads to {name}',
                    'watch': {**base, 'kind': 'exit', 'screen': screen, 'value': new, 'name': name}}
        raise ValueError('ROMancer cannot change that yet.')

    def shown(self, number: int) -> int:
        """The number the sprite slot gets ($02A97A): shells become the matching Koopa number."""
        return number - 0xDA + 4 if number in self.SHELLS else number

    def watcher(self, watch):
        if watch['kind'] == 'sprite':
            return _SmwSpriteWatcher(watch)
        return _SmwRamWatcher(watch)



# --------------------------------------------------------------------------------------------- Super Metroid

class SuperMetroid:
    """Super Metroid (Japan, USA). Room header (bank $8F): +1 area, +4 width, +5 height (screens), +9 door list,
    +11 states. States ($8FE5E6 and the condition codes before it): each condition code is followed by its arguments and
    a state pointer; $E5E6 ends the list and its state follows it directly. State data (26 bytes, read at $82DEF7):
    +8 enemy population (bank $A1), +$0A enemy set (bank $B4), +$14 room objects (PLMs, bank $8F; spawned at $84846A).

    Enemy population ($A08ADE): 16 bytes each (species, x, y, tilemap, properties, extra, two parameters), $FFFF ends
    it, then one byte: how many must be killed to open grey doors. Entry n goes to enemy slot n ($0F78 + n * $40 species,
    $0F7A x, $0F7E y). Species names are the game's own (species header + $3E points to a 10-letter name in bank $B4).
    Room objects: 6 bytes (id, x block, y block, parameter), 0 ends it; the spawner writes the id to $1C37 + slot * 2 and
    the block index * 2 to $1C87 + slot * 2.
    """
    name = 'Super Metroid'
    sha256 = '12b77c4bc9c1832cee8881244659065ee1d84c70c3d29e6eaf92e6798cc2ca72'
    CONDITIONS = {0xE5EB: 4, 0xE5FF: 2, 0xE612: 3, 0xE629: 3, 0xE640: 2, 0xE652: 2, 0xE669: 2, 0xE678: 2}
    FIRST_ROOMS = (0x91F8, 0xDF45)      # the landing site and Ceres station; every other room is found through doors
    # Item objects: three styles of 21 items each (in the open, held by a statue, hidden in a block). Every item of the
    # first style was put in Ceres and picked up (trace/v15_profiles/snes_classics/smitems.py, smitems/results*.txt): the
    # RAM it changed and the message it showed ($1C1F) are recorded there; the names are the game's own message texts
    # ($85869B). The other two styles run the same pickup code with the same values (their instruction lists in bank $84).
    ITEMS = ['Energy Tank', 'Missile', 'Super Missile', 'Power Bomb', 'Bomb', 'Charge Beam', 'Ice Beam', 'Hi-Jump Boots',
             'Speed Booster', 'Wave Beam', 'Spazer', 'Spring Ball', 'Varia Suit', 'Gravity Suit', 'X-Ray Scope',
             'Plasma Beam', 'Grappling Beam', 'Space Jump', 'Screw Attack', 'Morphing Ball', 'Reserve Tank']
    STYLES = {0xEED7: 'item', 0xEF2B: 'item on a statue', 0xEF7F: 'hidden item'}
    # the statue and hidden versions of the Morphing Ball give a different equipment bit than the one in the open
    # (their pickup data says $0002, not $0004), so they are not offered
    ODD = {0xEF77, 0xEFCB}

    def __init__(self, rom: bytes):
        self.rom = rom
        self._cache = {}

    def b(self, address: int) -> int:
        return self.rom[lorom(address)]

    def w(self, address: int) -> int:
        return self.b(address) | self.b(address + 1) << 8

    def doors(self, room: int) -> list:
        """Rooms the door list of a room leads to."""
        at, out = 0x8F0000 | self.w(0x8F0000 | room + 9), []
        for _ in range(40):
            door = self.w(at)
            if not 0x8800 <= door < 0xC000:
                break
            out.append(self.w(0x830000 | door))
            at += 2
        return out

    def rooms(self) -> list:
        if 'rooms' not in self._cache:
            seen, todo = set(), list(self.FIRST_ROOMS)
            while todo:
                room = todo.pop()
                if room in seen:
                    continue
                seen.add(room)
                todo += [r for r in self.doors(room) if r >= 0x91F8]
            self._cache['rooms'] = sorted(seen)
        return self._cache['rooms']

    def states(self, room: int) -> list:
        """State data addresses (16 bits, bank $8F) of a room, the default one last."""
        at, out = 0x8F0000 | room + 11, []
        for _ in range(16):
            code = self.w(at)
            if code == 0xE5E6:
                out.append((at + 2) & 0xFFFF)
                return out
            size = self.CONDITIONS.get(code)
            if size is None:
                break
            out.append(self.w(at + size))
            at += 2 + size
        return out

    def area(self, room: int) -> int:
        return self.b(0x8F0000 | room + 1)

    def species_name(self, species: int) -> str:
        pointer = self.w(0xA00000 | species + 0x3E)
        if pointer >= 0x8000:
            text = bytes(self.b(0xB40000 | pointer + i) for i in range(10)).decode('ascii', 'replace').strip()
            if text and all(c.isalnum() or c in ' -' for c in text):
                return text.title()
        return f'Enemy {species:#06x}'

    def enemies(self, state: int) -> list:
        at, out = 0xA10000 | self.w(0x8F0000 | state + 8), []
        while self.w(at) != 0xFFFF and len(out) < 32:
            out.append({'index': len(out), 'offset': lorom(at), 'species': self.w(at), 'x': self.w(at + 2), 'y': self.w(at + 4)})
            at += 16
        return out

    def enemy_set(self, state: int) -> list:
        """Species whose graphics the room loads (bank $B4: species, palette; $FFFF ends it)."""
        at, out = 0xB40000 | self.w(0x8F0000 | state + 0x0A), []
        while self.w(at) != 0xFFFF and len(out) < 16:
            out.append(self.w(at))
            at += 4
        return out

    def objects_list(self, state: int) -> list:
        at, out = 0x8F0000 | self.w(0x8F0000 | state + 0x14), []
        while self.w(at) and len(out) < 64:
            out.append({'index': len(out), 'offset': lorom(at), 'id': self.w(at), 'x': self.b(at + 2), 'y': self.b(at + 3),
                        'param': self.w(at + 4)})
            at += 6
        return out

    def item_of(self, plm: int):
        """(style base, item number) of an item object, or None."""
        for base in self.STYLES:
            if base <= plm < base + 4 * 21 and (plm - base) % 4 == 0:
                return base, (plm - base) // 4
        return None

    def population_regions(self) -> list:
        if 'pops' not in self._cache:
            regions = set()
            for room in self.rooms():
                for state in self.states(room):
                    start = lorom(0xA10000 | self.w(0x8F0000 | state + 8))
                    regions.add((start, start + len(self.enemies(state)) * 16 + 3))
            self._cache['pops'] = sorted(regions)
        return self._cache['pops']

    def remove_enemy_writes(self, state: int, index: int) -> list:
        """Take one enemy out: later entries move up, $FFFF and the kill count follow one entry sooner (the kill count
        is lowered when it asked for more enemies than are left)."""
        entries = self.enemies(state)
        start = lorom(0xA10000 | self.w(0x8F0000 | state + 8))
        end = start + len(entries) * 16                 # the $FFFF
        kill = self.rom[end + 2]
        old = self.rom[entries[index]['offset']:end + 3]
        new = self.rom[entries[index]['offset'] + 16:end] + b'\xff\xff' + bytes([min(kill, len(entries) - 1)])
        new += old[len(new):]                           # bytes after the new end stay as they were
        writes = [(entries[index]['offset'] + i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]
        for other in self.population_regions():
            if other != (start, end + 3) and any(other[0] <= off < other[1] for off, _, _ in writes):
                raise ValueError('This enemy list runs into another room’s list, so ROMancer cannot shorten it safely.')
        return writes


def _word(ram, address):
    return ram[address] | ram[address + 1] << 8


class _SmEnemyWatcher(Watcher):
    """An enemy edit: when the room has loaded (game state 8, the room and its state in $079B / $07BB), enemy slot n holds
    the chosen species; a removed enemy is in no slot (species and position)."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if _word(ram, 0x998) != 8 or _word(ram, 0x79B) != w['room'] or _word(ram, 0x7BB) != w['state']:
            return False
        slots = [(_word(ram, 0xF78 + n * 0x40), _word(ram, 0xF7A + n * 0x40), _word(ram, 0xF7E + n * 0x40)) for n in range(32)]
        if w['remove']:
            there = any(s[0] == w['species'] and abs(s[1] - w['x']) < 4 and abs(s[2] - w['y']) < 4 for s in slots)
            self.seen = 'there' if there else 'gone'
        else:
            self.seen = slots[w['index']][0]
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if w['remove']:
            ok = self.seen == 'gone'
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the room loads without that {w["name"]}.' if ok
                    else f'Played from the start, the {w["name"]} is still in the room.'}
        ok = self.seen == w['species']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the room loads with {w["name"]} there.' if ok
                else f'Played from the start, the room loads with enemy {self.seen:#06x} there, not the one chosen.'}


class _SmItemWatcher(Watcher):
    """An item edit: when the room has loaded, a room object slot at that block ($1C87) holds the chosen item ($1C37)."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if _word(ram, 0x998) != 8 or _word(ram, 0x79B) != w['room'] or _word(ram, 0x7BB) != w['state']:
            return False
        block = (w['y'] * _word(ram, 0x7A5) + w['x']) * 2
        found = [_word(ram, 0x1C37 + 2 * n) for n in range(40) if _word(ram, 0x1C87 + 2 * n) == block and _word(ram, 0x1C37 + 2 * n)]
        self.seen = found[0] if found else 0
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        ok = self.seen == w['id']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the room loads with {w["name"]} at that spot.' if ok
                else f'Played from the start, the room loads with object {self.seen:#06x} at that spot, not the one chosen.'}


class SuperMetroidProfile(SuperMetroid, Profile):
    """Parts are {'room': room header address in bank $8F, 'state': the room state in use}; x and y are room pixels
    (the camera is $0911 / $0915)."""
    sha256s = (SuperMetroid.sha256,)
    system = 'snes'

    def __init__(self, rom: bytes):
        SuperMetroid.__init__(self, rom)

    def where(self, ram):
        if _word(ram, 0x998) not in (8, 9, 0x0B) or _word(ram, 0x79B) < 0x91F8:
            return None
        return {'part': {'room': _word(ram, 0x79B), 'state': _word(ram, 0x7BB)}, 'x': _word(ram, 0x911), 'y': _word(ram, 0x915)}

    def part_name(self, part):
        room, state = int(part['room']), int(part['state'])
        states = self.states(room)
        name = f'Room {room:04X} (area {self.area(room)})'
        if len(states) > 1 and state in states:
            name += f', state {states.index(state) + 1} of {len(states)}'
        return name

    def item_name(self, plm: int) -> str:
        base, number = self.item_of(plm)
        return self.ITEMS[number] + {0xEED7: '', 0xEF2B: ' (on a statue)', 0xEF7F: ' (hidden)'}[base]

    def choices(self):
        return {f'items{base:04x}': [{'value': base + 4 * n, 'name': self.item_name(base + 4 * n)}
                                     for n in range(21) if base + 4 * n not in self.ODD] for base in self.STYLES}

    def _list_users(self, state: int) -> int:
        pointer = self.w(0x8F0000 | state + 8)
        return sum(1 for r in self.rooms() for s in set(self.states(r)) if self.w(0x8F0000 | s + 8) == pointer)

    def objects(self, part):
        room, state = int(part['room']), int(part['state'])
        users = self._list_users(state)
        out = []
        species_choices = [{'value': s, 'name': self.species_name(s)} for s in self.enemy_set(state)]
        for e in self.enemies(state):
            row = {'id': f'enemy:{e["index"]}', 'style': 'enemy', 'type': e['species'], 'x': e['x'],
                   'y': e['y'] + self.w(0xA00000 | e['species'] + 0x0A), 'name': self.species_name(e['species']),
                   'remove': 'Remove this enemy', 'fields': []}
            if species_choices:
                row['fields'] = [{'key': 'species', 'label': 'Swap for', 'value': e['species'], 'choices': species_choices}]
            if users > 1:
                row['note'] = f'This enemy list is shared with {users - 1} other room states, so a change shows there too.'
            out.append(row)
        for o in self.objects_list(state):
            found = self.item_of(o['id'])
            if not found:
                continue
            out.append({'id': f'item:{o["index"]}', 'style': 'secret' if found[0] == 0xEF7F else 'item', 'type': o['id'],
                        'x': o['x'] * 16 + 8, 'y': o['y'] * 16 + 16, 'name': self.item_name(o['id']), 'remove': None,
                        'fields': [{'key': 'id', 'label': 'Item', 'value': o['id'], 'choices': f'items{found[0]:04x}'}]})
        return out

    def edit(self, part, object_id, values, remove=False):
        room, state = int(part['room']), int(part['state'])
        kind, _, number = object_id.partition(':')
        number = int(number)
        base = {'room': room, 'state': state}
        if kind == 'enemy':
            entries = self.enemies(state)
            if not 0 <= number < len(entries):
                raise ValueError('That is not part of this room any more. Reopen the map.')
            e = entries[number]
            if remove:
                return {'writes': self.remove_enemy_writes(state, number), 'title': f'Remove the {self.species_name(e["species"])}',
                        'watch': {**base, 'kind': 'enemy', 'remove': True, 'species': e['species'], 'x': e['x'], 'y': e['y'],
                                  'name': self.species_name(e['species'])}}
            new = int(values.get('species', e['species']))
            if new not in self.enemy_set(state):
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(e['offset'] + i, self.rom[e['offset'] + i], v) for i, v in enumerate(new.to_bytes(2, 'little'))
                      if self.rom[e['offset'] + i] != v]
            return {'writes': writes, 'title': f'Enemy here: {self.species_name(new)}',
                    'watch': {**base, 'kind': 'enemy', 'remove': False, 'index': number, 'species': new,
                              'name': self.species_name(new)}}
        if kind == 'item':
            objects = self.objects_list(state)
            if not 0 <= number < len(objects) or not self.item_of(objects[number]['id']):
                raise ValueError('That is not part of this room any more. Reopen the map.')
            o = objects[number]
            new = int(values.get('id', o['id']))
            if self.item_of(new) is None or self.item_of(new)[0] != self.item_of(o['id'])[0] or new in self.ODD:
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(o['offset'] + i, self.rom[o['offset'] + i], v) for i, v in enumerate(new.to_bytes(2, 'little'))
                      if self.rom[o['offset'] + i] != v]
            return {'writes': writes, 'title': f'Item here: {self.item_name(new)}',
                    'watch': {**base, 'kind': 'item', 'id': new, 'x': o['x'], 'y': o['y'], 'name': self.item_name(new)}}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        return _SmEnemyWatcher(watch) if watch['kind'] == 'enemy' else _SmItemWatcher(watch)


PROFILES = [SuperMarioWorldProfile, SuperMetroidProfile]
