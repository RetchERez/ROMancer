"""Super Mario Bros. 3 (USA) (Rev 1): areas, enemies, block contents, hidden blocks and where pipes and doors lead.

Everything here was read from the game's code (research/smb3-level-profile.md) and checked by replaying the game.

The cartridge is MMC3 with 8 KB banks: bank 30 sits at $8000 and bank 31 at $E000; $A000 and $C000 are switched.

* World map (bank 12 at $A000): per world, tables at $B3DC (row and tileset), $B3EE (map column), $B400 (enemy list)
  and $B412 (layout). Map tiles: $A598 + world * 2 points at 144-byte screens (9 rows of 16).
* Layout (bank $83E9[tileset] at $A000): a 9-byte header (bytes 0-3 the other area's layout and enemy list, byte 6 low
  nibble its tileset, byte 4 low nibble the last screen, byte 6 bit 4 a vertical area), then records of 3 bytes
  (b0 = class << 5 | row, b1 = screen << 4 | column, b2 = kind) or 4 for kinds whose builder reads one more byte, $FF ends.
  b0 $E0-$EF is a way out: the screen in the low nibble, b1 and b2 say where the pipe or door on that screen leads.
* Builders (bank 30 $9A49 / $9A75 jump by tileset; then tables in the tileset's bank). Fixed kind (b2 < $10): table
  entry class * 16 + b2; class 1 and class 2 kinds 0-8 run $CADD (bank 14), one block whose tile is $CAC4[class*16 + b2
  - 16]. Kind b2 >= $10: entry (b2 >> 4) + start[class] - 1; class 1 kinds 1-8 run $CB1F, a row of b2 & 15 + 1 tiles
  of $CB16[(b2 >> 4) - 1].
* Enemy list (bank 6 at $C000): one byte, then 3 bytes each (id, column 0-255, row: y = row * 16), $FF ends. The game
  copies it to $7B40 when the area loads ($B4FF, bank 26); a spawned enemy keeps its record number in $0659 + slot and
  its id in $0671 + slot.
* RAM: $0727 world, $070A tileset, $7EB9/$7EBA layout and $7EBB/$7EBC enemy list of the area being played, $FD/$12 the
  camera x, $FC/$13 the vertical scroll, $6000 + screen * $1B0 + row * 16 + column the area's tiles.
"""
from __future__ import annotations

from . import Profile, Watcher

H = 16
TILE_BASE = 0x6000
SCREEN = 0x1B0


class SMB3:
    sha256 = '1ddc4b429490e298c05fa70389034107c0cb50f671c7c1baaa3f228224afc2e9'
    BLOCK_ONE = 0xCADD            # builder of one block (bank 14)
    BLOCK_ROW = 0xCB1F            # builder of a row of blocks (bank 14)
    TILES_ONE = 0xCAC4
    TILES_ROW = 0xCB16
    TILESETS = tuple(range(1, 15)) + (18,)
    # what comes out, measured by bumping each tile in 1-1 with small and big Mario (research notes)
    BLOCK_NAMES = {
        0x60: '? block with a mushroom, or a fire flower when Mario is big',
        0x61: '? block with a mushroom, or a leaf when Mario is big',
        0x62: '? block with a star', 0x63: '? block with a coin', 0x64: '? block with a coin (tile 0x64)',
        0x65: '? block with a coin (tile 0x65)', 0x66: 'Muncher (a black plant that hurts Mario)',
        0x68: 'Brick with a mushroom, or a fire flower when Mario is big',
        0x69: 'Brick with a mushroom, or a leaf when Mario is big',
        0x6A: 'Brick with a star', 0x6C: 'Brick with a coin', 0x6D: 'Brick with several coins',
        0x6E: 'Brick with a 1-up mushroom', 0x6F: 'Brick with a vine', 0x70: 'Brick with a P-switch',
        0x44: 'Hidden block with a coin', 0x45: 'Hidden block with a 1-up mushroom', 0x03: 'Hidden note block',
        0x2F: 'Note block with a mushroom, or a fire flower when Mario is big',
        0x30: 'Note block with a mushroom, or a leaf when Mario is big', 0x31: 'Note block with a star',
        0x46: 'Block that turns into a note block when hit', 0xF2: 'P-switch',
        0x73: 'Wood block (tile 0x73)', 0x74: 'Wood block (tile 0x74)', 0x75: 'Wood block (tile 0x75)'}
    HIDDEN = {0x44, 0x45, 0x03}
    ROW_NAMES = {0x67: 'Row of bricks', 0x63: 'Row of ? blocks with coins', 0x6B: 'Row of bricks with a coin',
                 0x2E: 'Row of note blocks', 0x79: 'Row of wood blocks',
                 0x72: 'Row of wood blocks (tile 0x72)', 0x40: 'Row of coins'}
    # spawned in 1-1 and looked at (trace/v15_profiles/smb3/spawn_*.png)
    ENEMIES = {0x6C: 'Koopa Troopa (green)', 0x6D: 'Koopa Troopa (red)', 0x6E: 'Koopa Paratroopa (green)',
               0x70: 'Buzzy Beetle', 0x71: 'Spiny', 0x72: 'Goomba', 0x73: 'Para-Goomba', 0xA0: 'Piranha Plant (green)',
               0xA1: 'Piranha Plant (green, upside down)', 0xA2: 'Piranha Plant (red)',
               0xA3: 'Piranha Plant (red, upside down)', 0xA6: 'Venus Fire Trap (red)'}
    CONTROL = 0xB4                # ids from here on are level controls (scrolling, bosses' rooms, ...), not enemies
    MAP_TILES = {0x67: 'mini-fortress', 0xC9: 'castle', 0x50: 'Toad house'}

    def __init__(self, rom: bytes):
        self.rom = rom
        self._areas = None

    # ---- reading
    def _bank(self, bank: int, address: int) -> int:
        return H + bank * 0x2000 + (address & 0x1FFF)

    def _at(self, bank: int, address: int) -> int:
        return self.rom[self._bank(bank, address)]

    def _word(self, bank: int, address: int) -> int:
        return self._at(bank, address) | self._at(bank, address + 1) << 8

    def layout_bank(self, tileset: int) -> int:
        return self._at(30, 0x83E9 + tileset)

    def _cbank(self, tileset: int) -> int:
        return self._at(30, 0x83D6 + tileset)

    def _read(self, tileset: int, address: int) -> int:
        """A byte as the builders see it: bank 30 at $8000, the tileset's banks at $A000 and $C000, bank 31 at $E000."""
        bank = {0x8000: 30, 0xA000: self.layout_bank(tileset), 0xC000: self._cbank(tileset), 0xE000: 31}[address & 0xE000]
        return self._at(bank, address)

    def _read_word(self, tileset: int, address: int) -> int:
        return self._read(tileset, address) | self._read(tileset, address + 1) << 8

    def _jump_table(self, tileset: int, routine: int) -> int:
        """Address of the table after JSR $FE99 in a builder dispatch routine."""
        a = routine
        for _ in range(64):
            if (self._read(tileset, a), self._read(tileset, a + 1), self._read(tileset, a + 2)) == (0x20, 0x99, 0xFE):
                return a + 3
            a += 1
        raise ValueError('This copy of the game builds its levels in a way ROMancer does not expect.')

    def builder(self, tileset: int, b0: int, b2: int) -> int:
        """The routine that builds a layout record."""
        cls = b0 >> 5
        if b2 & 0xF0:
            routine = self._word(30, 0x9A4F + 2 * tileset)
            start = self._read(tileset, routine - 8 + cls)
            return self._read_word(tileset, self._jump_table(tileset, routine) + 2 * ((b2 >> 4) + start - 1))
        routine = self._word(30, 0x9A7B + 2 * tileset)
        return self._read_word(tileset, self._jump_table(tileset, routine) + 2 * (cls * 16 + b2))

    def _reads_more(self, tileset: int, entry: int, cache: dict) -> bool:
        """Does a builder read a 4th byte of its record (LDA ($61),Y and move $61 on)? Follows the code statically."""
        key = (tileset, entry)
        if key in cache:
            return cache[key]
        seen, todo, found = set(), [entry], False
        sizes = _SIZES
        while todo and not found and len(seen) < 6000:
            a = todo.pop()
            while a not in seen and a >= 0x8000:
                seen.add(a)
                code = self._read(tileset, a)
                size = sizes.get(code)
                if size is None:
                    break
                arg = self._read(tileset, a + 1) if size >= 1 else 0
                if size == 2:
                    arg |= self._read(tileset, a + 2) << 8
                if code == 0xB1 and arg == 0x61:
                    found = True
                    break
                nxt = a + 1 + size
                if code in (0x60, 0x40, 0x6C):
                    break
                if code == 0x4C:
                    a = arg
                    continue
                if code == 0x20:
                    if arg == 0xFE99:
                        break
                    todo.append(arg)
                if code in _BRANCHES:
                    todo.append((nxt + (arg - 256 if arg > 127 else arg)) & 0xFFFF)
                a = nxt
        cache[key] = found
        return found

    def header(self, tileset: int, layout: int) -> list:
        bank = self.layout_bank(tileset)
        return [self._at(bank, layout + i) for i in range(9)]

    def records(self, tileset: int, layout: int) -> list:
        """Layout records: dicts with 'at' (CPU address), 'offset' (file offset), b0, b1, b2, 'b3' (or None), 'builder'."""
        bank = self.layout_bank(tileset)
        cache = getattr(self, '_more_cache', None)
        if cache is None:
            cache = self._more_cache = {}
        a, out = layout + 9, []
        while len(out) < 800:
            b0 = self._at(bank, a)
            if b0 == 0xFF:
                return out
            b1, b2 = self._at(bank, a + 1), self._at(bank, a + 2)
            row = {'at': a, 'offset': self._bank(bank, a), 'b0': b0, 'b1': b1, 'b2': b2, 'b3': None, 'builder': None}
            if b0 & 0xE0 == 0xE0:
                row['kind'] = 'way'
                a += 3
            else:
                entry = self.builder(tileset, b0, b2)
                if entry < 0x8000:
                    raise ValueError('ROMancer could not read this level’s layout.')
                row['kind'], row['builder'] = 'build', entry
                if self._reads_more(tileset, entry, cache):
                    row['b3'] = self._at(bank, a + 3)
                    a += 4
                else:
                    a += 3
            out.append(row)
        raise ValueError('ROMancer could not read this level’s layout.')

    def enemy_list(self, objects: int) -> list:
        """[{'number', 'offset', 'id', 'column', 'row'}] of an enemy list in bank 6."""
        out = []
        if not 0xC000 <= objects < 0xE000:
            return out
        a = objects + 1
        while self._at(6, a) != 0xFF and len(out) < 84:
            out.append({'number': len(out), 'offset': self._bank(6, a), 'id': self._at(6, a),
                        'column': self._at(6, a + 1), 'row': self._at(6, a + 2)})
            a += 3
        return out

    # ---- the world map
    def map_entries(self, world: int) -> list:
        base = {k: self._word(12, t + 2 * world) for k, t in (('rows', 0xB3DC), ('cols', 0xB3EE), ('objs', 0xB400), ('lays', 0xB412))}
        out = []
        for i in range(base['cols'] - base['rows']):
            r, c = self._at(12, base['rows'] + i), self._at(12, base['cols'] + i)
            out.append({'world': world, 'index': i, 'row': r >> 4, 'tileset': r & 15, 'column': c,
                        'objects': self._word(12, base['objs'] + 2 * i), 'layout': self._word(12, base['lays'] + 2 * i)})
        return out

    def map_tile(self, world: int, row: int, column: int) -> int:
        start = self._word(12, 0xA598 + 2 * world)
        return self._at(12, start + (column >> 4) * 144 + (row - 2) * 16 + (column & 15))

    def map_place(self, world: int, row: int, column: int) -> str:
        tile = self.map_tile(world, row, column)
        if 0x03 <= tile <= 0x0C:
            return f'level {tile - 2}'
        if tile in self.MAP_TILES:
            return self.MAP_TILES[tile]
        return f'the map spot in row {row}, column {column}'

    def areas(self) -> dict:
        """{(tileset, layout): {'objects', 'name', 'world', 'main': (tileset, layout) of the area it is reached from or None}}"""
        if self._areas is not None:
            return self._areas
        found, todo = {}, []
        for world in range(9):
            entries = self.map_entries(world)
            uses = {}
            for e in entries:
                uses[(e['tileset'], e['layout'])] = uses.get((e['tileset'], e['layout']), 0) + 1
            for e in entries:
                if e['tileset'] in self.TILESETS and 0xA000 <= e['layout'] < 0xC000:
                    shared = uses[(e['tileset'], e['layout'])] > 1
                    name = f'World {world + 1}, ' + (self.map_place(world, e['row'], e['column']) if not shared else
                                                     f'the map spot in row {e["row"]}, column {e["column"]}')
                    todo.append((e['tileset'], e['layout'], e['objects'], world, name, None, shared))
        todo.sort(key=lambda t: t[6])       # names from a map's own spot first
        while todo:
            tileset, layout, objects, world, name, main, _ = todo.pop(0)
            key = (tileset, layout)
            if key in found:
                continue
            try:
                head = self.header(tileset, layout)
                self.records(tileset, layout)
            except (ValueError, IndexError, KeyError):
                continue
            found[key] = {'objects': objects, 'name': name, 'world': world, 'main': main, 'header': head}
            alt_tileset = head[6] & 15
            alt = head[0] | head[1] << 8
            if alt_tileset in self.TILESETS and 0xA000 <= alt < 0xC000 and (alt_tileset, alt) not in found:
                base = name if main is None else found[main]['name'] if main in found else name
                todo.append((alt_tileset, alt, head[2] | head[3] << 8, world,
                             (name + ', the area a pipe or door leads to') if main is None else base, key, False))
        self._areas = found
        return found

    def area_of(self, tileset: int, layout: int):
        return self.areas().get((tileset, layout))

    def screens_of(self, tileset: int, layout: int) -> int:
        return (self.header(tileset, layout)[4] & 15) + 1

    def vertical(self, tileset: int, layout: int) -> bool:
        return bool(self.header(tileset, layout)[6] & 0x10)

    def one_tile(self, cls: int, kind: int) -> int:
        return self._at(14, self.TILES_ONE + cls * 16 + kind - 16)

    def row_tile(self, kind: int) -> int:
        return self._at(14, self.TILES_ROW + (kind >> 4) - 1)

    def block_choices(self, tileset: int) -> list:
        """(class << 4 | kind, tile) of every single block the builder of one block makes in this tileset."""
        out = []
        for cls in (1, 2):
            for kind in range(16):
                if self.builder(tileset, cls << 5, kind) == self.BLOCK_ONE and self._cbank(tileset) == 14:
                    out.append((cls << 4 | kind, self.one_tile(cls, kind)))
        return out

    def row_choices(self, tileset: int) -> list:
        out = []
        for kind in range(1, 16):
            if self.builder(tileset, 1 << 5, kind << 4) == self.BLOCK_ROW and self._cbank(tileset) == 14:
                out.append((kind, self.row_tile(kind << 4)))
        return out


_BRANCHES = {0x10, 0x30, 0x50, 0x70, 0x90, 0xB0, 0xD0, 0xF0}


def _sizes():
    one = {0x09, 0x29, 0x49, 0x69, 0xA0, 0xA2, 0xA9, 0xC0, 0xC9, 0xE0, 0xE9}       # immediate
    one |= {0x05, 0x06, 0x24, 0x25, 0x26, 0x45, 0x46, 0x65, 0x66, 0x84, 0x85, 0x86, 0xA4, 0xA5, 0xA6, 0xC4, 0xC5, 0xC6,
            0xE4, 0xE5, 0xE6}                                                         # zero page
    one |= {0x15, 0x16, 0x35, 0x36, 0x55, 0x56, 0x75, 0x76, 0x94, 0x95, 0x96, 0xB4, 0xB5, 0xB6, 0xD5, 0xD6, 0xF5, 0xF6}
    one |= {0x01, 0x11, 0x21, 0x31, 0x41, 0x51, 0x61, 0x71, 0x81, 0x91, 0xA1, 0xB1, 0xC1, 0xD1, 0xE1, 0xF1}
    one |= _BRANCHES
    two = {0x0D, 0x0E, 0x20, 0x2C, 0x2D, 0x2E, 0x4C, 0x4D, 0x4E, 0x6C, 0x6D, 0x6E, 0x8C, 0x8D, 0x8E, 0xAC, 0xAD, 0xAE,
           0xCC, 0xCD, 0xCE, 0xEC, 0xED, 0xEE}
    two |= {0x19, 0x1D, 0x1E, 0x39, 0x3D, 0x3E, 0x59, 0x5D, 0x5E, 0x79, 0x7D, 0x7E, 0x99, 0x9D, 0xB9, 0xBC, 0xBD, 0xBE,
            0xD9, 0xDD, 0xDE, 0xF9, 0xFD, 0xFE}
    zero = {0x00, 0x08, 0x0A, 0x18, 0x28, 0x2A, 0x38, 0x40, 0x48, 0x4A, 0x58, 0x60, 0x68, 0x6A, 0x78, 0x88, 0x8A, 0x98,
            0x9A, 0xA8, 0xAA, 0xB8, 0xBA, 0xC8, 0xCA, 0xD8, 0xE8, 0xEA, 0xF8}
    out = {c: 0 for c in zero}
    out.update({c: 1 for c in one})
    out.update({c: 2 for c in two})
    return out


_SIZES = _sizes()


# ---- watchers

def _part_of(ram):
    tileset = ram[0x70A]
    if tileset not in SMB3.TILESETS:
        return None
    return (tileset, ram[0x800 + 0x1EB9] | ram[0x800 + 0x1EBA] << 8, ram[0x800 + 0x1EBB] | ram[0x800 + 0x1EBC] << 8)


class _Settled(Watcher):
    """Waits until the part has been played for a moment (its tiles and enemy list are loaded)."""
    SETTLE = 40

    def __init__(self, watch):
        self.w = watch
        self.since = None

    def settled(self, ram, frame) -> bool:
        w = self.w
        here = _part_of(ram)
        if here != (w['tileset'], w['layout'], w['objects']):
            self.since = None
            return False
        if self.since is None:
            self.since = frame
        return frame - self.since >= self.SETTLE


class _BlockWatcher(_Settled):
    """A block edit: the tile the game built at that spot once the part is loaded."""

    def __init__(self, watch):
        super().__init__(watch)
        self.seen = None

    def see(self, ram, frame, run):
        if not self.settled(ram, frame):
            return False
        self.seen = ram[0x800 + self.w['address'] - TILE_BASE]
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        ok = self.seen in w['tiles']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now builds the chosen block there ({w["name"]}).' if ok else
                        f'Played from the start, the game built tile {self.seen:#04x} there, not the one chosen.'}


class _EnemyWatcher(_Settled):
    """An enemy edit: the enemy list the game copied to $7B40 when the part loaded, then any enemy it spawned from that
    record ($0659 + slot holds the record number)."""

    def __init__(self, watch):
        super().__init__(watch)
        self.listed = None
        self.spawned = None

    def see(self, ram, frame, run):
        if not self.settled(ram, frame):
            return False
        w = self.w
        if self.listed is None:
            records = []
            for k in range(84):
                a = 0x800 + 0x1B41 + 3 * k
                if ram[a] == 0xFF:
                    break
                records.append((ram[a], ram[a + 1], ram[a + 2]))
            self.listed = records
            if w['remove']:
                return True
        if w['remove']:
            return True
        for slot in range(5):
            if ram[0x661 + slot] and ram[0x659 + slot] == w['number']:
                self.spawned = ram[0x671 + slot]
                return True
        return False

    def result(self):
        w = self.w
        if self.listed is None:
            return super().result()
        if w['remove']:
            ok = tuple(w['record']) not in self.listed
            return {'state': 'good' if ok else 'bad',
                    'text': 'Played from the start, the game no longer has that enemy in this part.' if ok else
                            'Played from the start, the game still loads that enemy in this part.'}
        listed = self.listed[w['number']][0] if w['number'] < len(self.listed) else None
        if self.spawned is not None:
            ok = self.spawned == w['id']
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the game now spawns {w["name"]} there.' if ok else
                            f'Played from the start, the game spawned enemy {self.spawned:#04x} there, not the one chosen.'}
        ok = listed == w['id']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now loads {w["name"]} there. The recorded walk did not get '
                        'close enough to see it appear.' if ok else
                        'Played from the start, the game still loads the old enemy there.'}


class _WayWatcher(_Settled):
    """A way-out edit: where Mario stands when he comes out in the other area ($75 is his screen)."""

    def __init__(self, watch):
        super().__init__(watch)
        self.went = None
        self.was_here = False

    def see(self, ram, frame, run):
        w = self.w
        here = _part_of(ram)
        if here == (w['tileset'], w['layout'], w['objects']):
            self.was_here = True
            self.from_screen = ram[0x75]
            return False
        if self.was_here and here == tuple(w['to']) and self.from_screen == w['screen']:
            self.went = ram[0x75]
            return True
        return False

    def result(self):
        w = self.w
        if self.went is None:
            return {'state': 'warn', 'text': "The recorded walk doesn't go through this pipe or door, so the change couldn't "
                                             'be watched in the game. Use Play from here to try it yourself.'}
        ok = self.went == w['to_screen']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, Mario comes out on screen {self.went + 1} of the other area.' if ok else
                        f'Played from the start, Mario came out on screen {self.went + 1}, not the one chosen.'}


class SMB3Profile(SMB3, Profile):
    """Parts are {'world', 'tileset', 'layout', 'objects'}: the area being played. x and y are the area's pixels."""
    name = 'Super Mario Bros. 3'
    sha256s = (SMB3.sha256,)

    def where(self, ram):
        part = _part_of(ram)
        if part is None or self.area_of(part[0], part[1]) is None:
            return None
        tileset, layout, objects = part
        x = ram[0xFD] | ram[0x12] << 8
        y = (ram[0xFC] | ram[0x13] << 8) + 9        # measured: with $FC = $EF the top of the screen is area y 248
        return {'part': {'world': ram[0x727] + 1, 'tileset': tileset, 'layout': layout, 'objects': objects}, 'x': x, 'y': y}

    def part_name(self, part):
        area = self.area_of(int(part['tileset']), int(part['layout']))
        return area['name'] if area else f'Area {part["layout"]:#06x}'

    def enemy_name(self, kind: int) -> str:
        return self.ENEMIES.get(kind, f'Enemy {kind:#04x}')

    def block_name(self, tile: int) -> str:
        return self.BLOCK_NAMES.get(tile, f'Block (tile {tile:#04x})')

    def row_name(self, tile: int) -> str:
        return self.ROW_NAMES.get(tile, f'Row of tile {tile:#04x}')

    def _enemy_ids(self) -> list:
        ids = set()
        for area in self.areas().values():
            ids |= {e['id'] for e in self.enemy_list(area['objects'])}
        return sorted(i for i in ids if i < self.CONTROL and i != 0x41)

    def choices(self):
        return {'enemies': [{'value': i, 'name': self.enemy_name(i)} for i in self._enemy_ids()]}

    def _blocks_list(self, tileset):
        return [{'value': v, 'name': self.block_name(t)} for v, t in self.block_choices(tileset) if t in self.BLOCK_NAMES]

    def _rows_list(self, tileset):
        return [{'value': k, 'name': self.row_name(t)} for k, t in self.row_choices(tileset)]

    def _part(self, part):
        tileset, layout = int(part['tileset']), int(part['layout'])
        area = self.area_of(tileset, layout)
        if area is None:
            raise ValueError('That part of the game is not one ROMancer knows.')
        return tileset, layout, int(part.get('objects', area['objects']))

    def objects(self, part):
        tileset, layout, objects = self._part(part)
        if self.vertical(tileset, layout):
            return []
        out = []
        for e in self.enemy_list(objects):
            if e['id'] >= self.CONTROL:
                continue
            editable = e['id'] != 0x41
            out.append({'id': f'enemy:{e["number"]}', 'style': 'enemy', 'type': e['id'], 'name': self.enemy_name(e['id']),
                        'x': e['column'] * 16 + 8, 'y': e['row'] * 16 + 16,
                        'fields': [{'key': 'id', 'label': 'Swap for', 'value': e['id'], 'choices': 'enemies'}] if editable else [],
                        'remove': 'Remove this enemy' if editable else None})
        blocks, rows = None, None
        for number, r in enumerate(self.records(tileset, layout)):
            screen, column, row = r['b1'] >> 4, r['b1'] & 15, r['b0'] & 31
            x, y = screen * 256 + column * 16 + 8, row * 16 + 16
            if r['kind'] == 'way':
                to = self._way_target(tileset, layout)
                where_to = f'screen {(r["b2"] & 15) + 1} of ' + (self.area_of(*to)['name'] if to and self.area_of(*to) else 'the other area')
                fields = []
                if to:
                    count = self.screens_of(*to)
                    fields = [{'key': 'to_screen', 'label': 'Comes out on', 'value': r['b2'] & 15,
                               'choices': [{'value': s, 'name': f'Screen {s + 1}'} for s in range(count)]}]
                out.append({'id': f'way:{number}', 'style': 'secret', 'type': 'way', 'name': 'Pipe or door on this screen',
                            'detail': f'leads to {where_to}', 'x': (r['b0'] & 15) * 256 + 128, 'y': 26 * 16,
                            'note': 'The game keeps one way out for each screen; any pipe or door you can enter on this screen uses it. '
                                    'Mario comes out at the same spot of the chosen screen, even where that screen has no pipe or door.',
                            'fields': fields, 'remove': None})
            elif r['builder'] == self.BLOCK_ONE:
                cls, kind = r['b0'] >> 5, r['b2']
                tile = self.one_tile(cls, kind)
                if blocks is None:
                    blocks = self._blocks_list(tileset)
                item = {'id': f'block:{number}', 'style': 'secret' if tile in self.HIDDEN else 'item', 'type': tile,
                        'name': self.block_name(tile), 'x': x, 'y': y,
                        'fields': [{'key': 'block', 'label': 'Block', 'value': cls << 4 | kind, 'choices': blocks}], 'remove': None}
                if tile in (0x6E, 0x45):
                    item['note'] = 'The game remembers this 1-up once it is taken and does not build it again.'
                out.append(item)
            elif r['builder'] == self.BLOCK_ROW:
                tile = self.row_tile(r['b2'])
                if rows is None:
                    rows = self._rows_list(tileset)
                out.append({'id': f'row:{number}', 'style': 'block', 'type': tile, 'name': self.row_name(tile),
                            'detail': f'{(r["b2"] & 15) + 1} long', 'x': x, 'y': y,
                            'fields': [{'key': 'row', 'label': 'Blocks', 'value': r['b2'] >> 4, 'choices': rows}], 'remove': None})
        return out

    def _way_target(self, tileset, layout):
        head = self.header(tileset, layout)
        to = (head[6] & 15, head[0] | head[1] << 8)
        return to if self.area_of(*to) else None

    def _record(self, tileset, layout, number):
        rows = self.records(tileset, layout)
        if not 0 <= number < len(rows):
            raise ValueError('That is not part of this level any more. Reopen the map.')
        return rows[number]

    def edit(self, part, object_id, values, remove=False):
        tileset, layout, objects = self._part(part)
        kind, _, number = object_id.partition(':')
        number = int(number)
        watch = {'tileset': tileset, 'layout': layout, 'objects': objects}
        if kind == 'enemy':
            rows = self.enemy_list(objects)
            if not 0 <= number < len(rows):
                raise ValueError('That is not part of this level any more. Reopen the map.')
            e = rows[number]
            if remove:
                users = [a for a in self.areas().values() if a['objects'] != objects
                         and objects < a['objects'] <= objects + 3 * len(rows)]
                if users:
                    raise ValueError('Another part of the game reads this enemy list from the middle, so this enemy cannot be removed. Swap it instead.')
                start = e['offset']
                tail = bytes(self.rom[start + 3:self._bank(6, objects + 1) + 3 * len(rows) + 1])   # later records and the $FF
                writes = [(start + i, self.rom[start + i], b) for i, b in enumerate(tail) if self.rom[start + i] != b]
                watch.update(kind='enemy', remove=True, number=number, record=[e['id'], e['column'], e['row']], name='')
                return {'writes': writes, 'title': f'Remove {self.enemy_name(e["id"])} (screen {e["column"] // 16 + 1})', 'watch': watch}
            new_id = int(values.get('id', e['id']))
            if new_id not in self._enemy_ids():
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(e['offset'], e['id'], new_id)] if new_id != e['id'] else []
            watch.update(kind='enemy', remove=False, number=number, id=new_id, name=self.enemy_name(new_id))
            return {'writes': writes, 'title': f'Enemy here: {self.enemy_name(new_id)} (screen {e["column"] // 16 + 1})', 'watch': watch}
        r = self._record(tileset, layout, number)
        address = TILE_BASE + (r['b1'] >> 4) * SCREEN + (r['b0'] & 31) * 16 + (r['b1'] & 15)
        if kind == 'block':
            if r['builder'] != self.BLOCK_ONE:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            value = int(values.get('block'))
            allowed = dict(self.block_choices(tileset))
            if value not in allowed or allowed[value] not in self.BLOCK_NAMES:
                raise ValueError('That choice is not one of the game’s own.')
            cls, kind_ = value >> 4, value & 15
            b0 = (r['b0'] & 0x1F) | cls << 5
            writes = [w for w in ((r['offset'], r['b0'], b0), (r['offset'] + 2, r['b2'], kind_)) if w[1] != w[2]]
            tile = allowed[value]
            tiles = [tile] + ([0x5F] if tile == 0x6E else [0x80] if tile == 0x45 else [])
            watch.update(kind='block', address=address, tiles=tiles, name=self.block_name(tile))
            return {'writes': writes, 'title': f'Block here: {self.block_name(tile)}', 'watch': watch}
        if kind == 'row':
            if r['builder'] != self.BLOCK_ROW:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            value = int(values.get('row'))
            allowed = dict(self.row_choices(tileset))
            if value not in allowed:
                raise ValueError('That choice is not one of the game’s own.')
            b2 = value << 4 | (r['b2'] & 15)
            writes = [(r['offset'] + 2, r['b2'], b2)] if b2 != r['b2'] else []
            watch.update(kind='block', address=address, tiles=[allowed[value]], name=self.row_name(allowed[value]))
            return {'writes': writes, 'title': f'{self.row_name(allowed[value])} here', 'watch': watch}
        if kind == 'way':
            if r['kind'] != 'way':
                raise ValueError('That is not part of this level any more. Reopen the map.')
            to = self._way_target(tileset, layout)
            screen = int(values.get('to_screen'))
            if to is None or not 0 <= screen < self.screens_of(*to):
                raise ValueError('That choice is not one of the game’s own.')
            b2 = (r['b2'] & 0xF0) | screen
            writes = [(r['offset'] + 2, r['b2'], b2)] if b2 != r['b2'] else []
            area = self.area_of(*to)
            watch.update(kind='way', screen=r['b0'] & 15, to=[to[0], to[1], area['objects'] if area else 0], to_screen=screen)
            return {'writes': writes, 'title': f'Pipe or door on screen {(r["b0"] & 15) + 1} leads to screen {screen + 1}', 'watch': watch}
        raise ValueError('ROMancer cannot change that yet.')

    def watcher(self, watch):
        if watch['kind'] == 'enemy':
            return _EnemyWatcher(watch)
        if watch['kind'] == 'way':
            return _WayWatcher(watch)
        return _BlockWatcher(watch)


PROFILES = [SMB3Profile]
