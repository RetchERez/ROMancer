"""Bounded FFL2 room format reader and stool placement validator.

The caller verifies the source revision and owned artifact ancestry. This module
reads user supplied data; it contains format metadata and no cartridge assets.
"""
from pathlib import Path
import re

MAP_START, MAP_END, STOOL = 0x20265, 0x20460, 0x20375
HEADER, LOOKUP, COLLISION = 0x1c86b, 0x1f960, 0x1f160
ORIGIN, SIZE = (10, 28), (7, 8)
ORIGINAL = (14, 31)
ALLOWED = ((12, 31), ORIGINAL, (12, 32), (13, 32), (14, 32))


def decode_commands(raw, start, end, skip_point=None, circle_table=0x2670):
    """Decode the bounded drawing grammar used by this map into 4096 cells.

    Return cells, parsed command metadata, and offset after the terminator.
    Unsupported operations and circle radii fail closed. The opening map uses
    only radius-one circles; the small-radius table is read from the input.
    """
    if not 0 <= start < end <= len(raw):
        raise ValueError('room map range exceeds the ROM')
    grid = [0] * 4096
    commands = []
    p, anchor, previous = start, (0, 0), (0, 0)

    def read():
        nonlocal p
        if p >= end:
            raise ValueError('truncated room map command')
        value = raw[p]; p += 1
        return value

    def put(x, y, tile):
        if not (0 <= x < 64 and 0 <= y < 64 and 0 <= tile < 64):
            raise ValueError('room drawing exceeds map or tile bounds')
        grid[y * 64 + x] = tile

    for _ in range(1000):
        offset = p
        a = read(); op = a >> 4
        if op == 0:
            return grid, commands, p
        b = read(); x, y = b & 63, ((a & 15) << 2) | (b >> 6)
        command = {'offset': offset, 'op': op, 'x': x, 'y': y}
        if op == 1:
            tile = read() & 63
            command['tile'] = tile
            if offset != skip_point:
                put(x, y, tile)
        elif op == 2:
            anchor = (x, y)
        elif op in (3, 4, 5, 6, 9):
            first = read(); second = first
            if first & 192:
                first &= 63; second = read()
            if first >= 64 or second >= 64:
                raise ValueError('unsupported room tile flags')
            sx, sy = previous if op == 9 else anchor
            if op == 5:
                radius = abs(x-sx) + abs(y-sy)
                if not 1 <= radius < 8:
                    raise ValueError('unsupported room circle radius')
                table = circle_table + 2*(radius-1)
                if not 0 <= table <= len(raw)-2:
                    raise ValueError('room circle pointer exceeds ROM')
                q = int.from_bytes(raw[table:table+2], 'little')
                for _ in range(64):
                    if not 0 <= q < len(raw):
                        raise ValueError('room circle data exceeds ROM')
                    if raw[q] == 255:
                        break
                    if q+1 >= len(raw):
                        raise ValueError('truncated room circle data')
                    u, v = raw[q:q+2]; q += 2
                    for xx, yy in ((sx+u,sy+v),(sx+v,sy-u),(sx-u,sy-v),(sx-v,sy+u)):
                        if 0 <= xx < 64 and 0 <= yy < 64:
                            put(xx, yy, first)
                else:
                    raise ValueError('room circle budget exceeded')
            elif op in (6, 9):
                previous = (x, y)
                dx, dy = abs(x-sx), abs(y-sy)
                stepx, stepy = 1 if x >= sx else -1, 1 if y >= sy else -1
                major, minor = max(dx, dy), min(dx, dy)
                accumulator = max(major//2, 1)
                for step in range(128):
                    put(sx, sy, first if step % 2 == 0 else second)
                    if (sx, sy) == (x, y):
                        break
                    accumulator += minor
                    if accumulator > major:
                        sx += stepx; sy += stepy; accumulator -= major
                    elif dx >= dy:
                        sx += stepx
                    else:
                        sy += stepy
                else:
                    raise ValueError('room line budget exceeded')
            else:
                left, right = sorted((sx, x)); top, bottom = sorted((sy, y))
                if op == 4:
                    for yy in range(top, bottom+1):
                        for xx in range(left, right+1):
                            put(xx, yy, first if (xx-left+yy-top) % 2 == 0 else second)
                else:
                    perimeter = ([(xx,top) for xx in range(left,right+1)]
                                 + [(right,yy) for yy in range(top+1,bottom+1)]
                                 + [(xx,bottom) for xx in range(right-1,left-1,-1)]
                                 + [(left,yy) for yy in range(bottom-1,top,-1)])
                    for index, (xx,yy) in enumerate(perimeter):
                        put(xx, yy, first if index % 2 == 0 else second)
        elif op == 7:
            for yy in range(64):
                for xx in range(64):
                    put(xx, yy, x if (xx+yy) % 2 == 0 else y)
        else:
            raise ValueError('unsupported room map command')
        commands.append(command)
    raise ValueError('room map command budget exceeded')


def _position(raw):
    a, b, tile = raw[STOOL:STOOL+3]
    position = (b & 63, ((a & 15) << 2) | (b >> 6))
    if a >> 4 != 1 or tile != 29 or position not in ALLOWED:
        raise ValueError('stool command is outside the verified floor positions')
    return position


def _load(path, original_path):
    raw, original = Path(path).read_bytes(), Path(original_path).read_bytes()
    if len(raw) != 262144 or len(original) != 262144:
        raise ValueError('room definition requires the matched cartridge size')
    if (int.from_bytes(original[HEADER:HEADER+2], 'little') != 0x265
            or original[HEADER+2] != 11 or raw[HEADER:HEADER+17] != original[HEADER:HEADER+17]):
        raise ValueError('opening room header guard differs')
    if (raw[MAP_START:STOOL] != original[MAP_START:STOOL]
            or raw[STOOL+3:MAP_END] != original[STOOL+3:MAP_END]):
        raise ValueError('unrelated opening room map commands differ')
    if (raw[COLLISION:COLLISION+32] != original[COLLISION:COLLISION+32]
            or original[COLLISION+19] != 1 or original[COLLISION+29] != 1):
        raise ValueError('opening room collision guard differs')
    if raw[0x2670:0x26d5] != original[0x2670:0x26d5]:
        raise ValueError('opening room circle data guard differs')
    if _position(original) != ORIGINAL:
        raise ValueError('original stool position guard differs')
    current = _position(raw)
    cells, commands, _ = decode_commands(raw, MAP_START, MAP_END)
    root_cells, _, _ = decode_commands(original, MAP_START, MAP_END)
    base, _, _ = decode_commands(raw, MAP_START, MAP_END, skip_point=STOOL)
    if not any(c['offset'] == STOOL and c['op'] == 1 and c.get('tile') == 29 for c in commands):
        raise ValueError('stool bytes are not a parsed map point command')
    if max(cells) >= 32 or any(base[y*64+x] != 19 for x,y in ALLOWED):
        raise ValueError('verified bedroom floor or tile state differs')
    behavior = raw[COLLISION:COLLISION+32]
    if any(behavior[a & 31] != behavior[b & 31] for a,b in zip(cells,root_cells)):
        raise ValueError('stool move changes map collision behavior')
    return raw, base, root_cells, current


def _value(position):
    if position == ORIGINAL:
        return 'original'
    if position == (14,32):
        return 'stool_down'
    return f'at:{position[0]},{position[1]}'


def room_visual(path, original_path):
    raw, base, root_cells, current = _load(path, original_path)
    tiles = []
    for tile in range(64):
        source = 0x8000 + raw[LOOKUP+(tile & 31)]*64
        pixels = [0]*256
        for quadrant in range(4):
            for y in range(8):
                lo, hi = raw[source+quadrant*16+y*2:source+quadrant*16+y*2+2]
                for x in range(8):
                    pixels[((quadrant//2)*8+y)*16+(quadrant % 2)*8+x] = ((lo >> (7-x)) & 1) | (((hi >> (7-x)) & 1) << 1)
        tiles.append(pixels)
    def crop(cells):
        return [cells[y*64+x] for y in range(ORIGIN[1],ORIGIN[1]+SIZE[1])
                for x in range(ORIGIN[0],ORIGIN[0]+SIZE[0])]
    return {'kind':'room-map', 'origin':list(ORIGIN), 'size':list(SIZE), 'tile_size':16,
            'palette':[[85]*3,[255]*3,[170]*3,[0]*3], 'tiles':tiles,
            'base_cells':crop(base), 'original_cells':crop(root_cells),
            'collision_values':[raw[COLLISION+(tile&31)] for tile in crop(base)],
            'current':list(current), 'original':list(ORIGINAL), 'stool_down':[14,32],
            'object':{'name':'Stool','tile_id':29,'allowed':[list(p) for p in ALLOWED]},
            'options':[[_value(p), f'Stool at ({p[0]}, {p[1]})'] for p in ALLOWED],
            'value':_value(current),
            'scope':'Decoded opening-bedroom terrain and stool. Five floor positions preserve collision; test each new build.'}


def encode_move(path, original_path, value):
    _load(path, original_path)
    if type(value) is not str:
        raise ValueError('choose a verified bedroom stool position')
    if value == 'original':
        position = ORIGINAL
    elif value == 'stool_down':
        position = (14,32)
    else:
        match = re.fullmatch(r'at:(\d{1,2}),(\d{1,2})', value)
        position = tuple(map(int,match.groups())) if match else None
    if position not in ALLOWED:
        raise ValueError('choose a verified bedroom floor position')
    x, y = position
    return bytes((0x10 | (y >> 2), ((y & 3) << 6) | x, 29))
