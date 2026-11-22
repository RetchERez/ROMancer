"""A recorded scene's pictures as PNG files, out and back in.

Two pictures can be saved from any recorded scene:

* the sheet: every 8x8 picture the scene holds, 16 across, each drawn with
  the palette line the scene shows it with;
* a background layer: the layer as the game laid it out, cell by cell.

Both are palette PNGs whose palette is the scene's own colors in the game's
order, so an image editor opens them with exactly the colors the game has,
and a pixel's palette number says which color of which line it is.

Reading a PNG back never guesses silently. A pixel is taken by its palette
number when the file still carries the scene's palette; otherwise by its
color, within the palette line of the picture it belongs to. Every color
that line does not have is reported with the color it became. A background
layer shows one picture in many cells: a picture changes when the cells
that show it agree, and the cells that disagree are counted.

This module only turns pictures into pixels and back. Planning the ROM
change, and checking it by replaying the game, is scene_graphics' work.
"""
from __future__ import annotations

import io

from . import graphics_trace as gt
from . import scene_graphics as sg

COLUMNS = 16
MAX_PNG = 600 * 1024
MAX_SIDE = 4096
GREY = [(v, v, v) for v in (0, 85, 170, 255)]


def _image():
    from PIL import Image
    return Image


def _palette(graphics) -> list:
    return [tuple(int(v) for v in color) for color in graphics.colors[:256]]


def _slot(rule, line: int, value: int) -> int:
    base, step, _ = rule
    return base + line * step + value


def _rgb(colors: list, slot: int, value: int, bits: int) -> tuple:
    if 0 <= slot < len(colors):
        return colors[slot]
    top = (1 << bits) - 1
    shade = round(value * 255 / top) if top else 0
    return (shade, shade, shade)


class Picture:
    """Pixels of one exported picture: `slots` are palette numbers (or None where the scene's palette has no such color)."""

    def __init__(self, width: int, height: int, colors: list):
        self.width, self.height, self.colors = width, height, colors
        self.slots = [0] * (width * height)
        self.rgb = [(0, 0, 0)] * (width * height)
        self.indexed = True

    def put(self, x: int, y: int, slot: int, rgb: tuple) -> None:
        at = y * self.width + x
        self.rgb[at] = rgb
        if 0 <= slot < len(self.colors):
            self.slots[at] = slot
        else:
            self.indexed = False

    def square(self, left: int, top: int, slots: list, rgb: list, indexed: bool) -> None:
        """Put one 8x8 square: 64 palette numbers and 64 colors in screen order."""
        if not indexed:
            self.indexed = False
            slots = [slot if 0 <= slot < len(self.colors) else 0 for slot in slots]
        at = top * self.width + left
        for row in range(0, 64, 8):
            self.slots[at:at + 8] = slots[row:row + 8]
            self.rgb[at:at + 8] = rgb[row:row + 8]
            at += self.width

    def png(self) -> bytes:
        Image = _image()
        if self.indexed and self.colors:
            image = Image.frombytes('P', (self.width, self.height), bytes(self.slots))
            flat = [v for color in self.colors for v in color]
            image.putpalette(flat + [0] * (768 - len(flat)))
        else:
            image = Image.frombytes('RGB', (self.width, self.height), bytes(v for color in self.rgb for v in color))
        out = io.BytesIO()
        image.save(out, format='PNG', optimize=True)
        return out.getvalue()


# ----------------------------------------------------------------- the two layouts

def sheet_layout(view: dict) -> dict:
    """Where each picture of the scene sits on the sheet: {'tiles': [tile dict], 'width', 'height'}."""
    tiles = view['tiles']
    rows = max(1, (len(tiles) + COLUMNS - 1) // COLUMNS)
    return {'tiles': tiles, 'width': COLUMNS * 8, 'height': rows * 8}


def _current(tile: dict) -> list:
    """The pixels a picture has now: with the change you kept, where there is one."""
    text = (tile.get('pending') or {}).get('pixels') or tile['pixels']
    return sg.parse_pixels(text, tile['format'])


def export_sheet(graphics, view: dict) -> dict:
    layout = sheet_layout(view)
    if not layout['tiles']:
        raise ValueError('This scene holds no pictures to save.')
    colors = _palette(graphics)
    picture = Picture(layout['width'], layout['height'], colors)
    for number, tile in enumerate(layout['tiles']):
        left, top = number % COLUMNS * 8, number // COLUMNS * 8
        pixels = _current(tile)
        slots = [_slot(tile['pal'], tile['line'], value) for value in pixels]
        picture.square(left, top, slots, [_rgb(colors, slot, value, tile['bits']) for slot, value in zip(slots, pixels)],
                       all(0 <= slot < len(colors) for slot in slots))
    return {'png': picture.png(), 'width': picture.width, 'height': picture.height, 'pictures': len(layout['tiles']),
            'indexed': picture.indexed, 'colors': len(colors)}


def layer_cells(graphics, number: int):
    """(layer view, [(cell x, cell y, quadrant x, quadrant y, tile address, cell)]) for a background layer that has a flat picture."""
    layers = graphics.layers()
    if not 0 <= number < len(layers):
        raise ValueError('That background layer is not part of this scene.')
    view = layers[number]
    layer = view.layer
    if layer.width * view.px > MAX_SIDE or layer.height * view.px > MAX_SIDE:
        raise ValueError('This background layer is too large to save as one picture. Use the sheet instead.')
    quads = view.px // 8
    places = []
    for cy in range(layer.height):
        for cx in range(layer.width):
            cell = layer.cells[cy * layer.width + cx]
            for qy in range(quads):
                for qx in range(quads):
                    places.append((cx, cy, qx, qy, graphics._subtile(view, cell, qx, qy), cell))
    return view, places


def _cells_now(view: dict, layer_view, number: int) -> dict:
    """{(cell x, cell y): (tile address, hflip, vflip, palette line)} with the background changes that are kept or shown.

    A cell painted in the Background editor, or moved by an earlier PNG, is
    part of what the scene looks like now, so a saved PNG shows it and a
    loaded PNG is compared with it.
    """
    layer = layer_view.layer
    now = {(cell.x, cell.y): (cell.tile_address, cell.hflip, cell.vflip, cell.palette) for cell in layer.cells}
    row = next((entry for entry in view['layers'] if entry['index'] == number), None)
    for item in (row or {}).get('pending', ()):
        at = (int(item['x']), int(item['y']))
        if at not in now:
            continue
        address, hflip, vflip, line = now[at]
        if item.get('tile') is not None:
            address = sg.parse_tile_id(item['tile'])[1]
        if item.get('hflip') is not None:
            hflip = bool(item['hflip'])
        if item.get('vflip') is not None:
            vflip = bool(item['vflip'])
        if item.get('line') is not None:
            line = int(item['line'])
        now[at] = (address, hflip, vflip, line)
    return now


def _layer_tiles(view: dict, layer_view) -> dict:
    layer = layer_view.layer
    return {tile['address']: tile for tile in view['tiles']
            if tile['domain'] == layer.tile_domain and tile['format'] == layer.tile_format}


def _place(k: int, cell) -> tuple:
    """Where pixel k of a picture lands inside its 8x8 square on the layer, with the cell's flips."""
    x, y = k % 8, k // 8
    return (7 - x if cell.hflip else x), (7 - y if cell.vflip else y)


def _turned(pixels, hflip: bool, vflip: bool) -> tuple:
    """A picture as it lands on the layer: the 64 values in screen order, with these flips."""
    out = [0] * 64
    for k, value in enumerate(pixels):
        x, y = k % 8, k // 8
        out[(7 - y if vflip else y) * 8 + (7 - x if hflip else x)] = value
    return tuple(out)


def export_layer(graphics, view: dict, number: int) -> dict:
    layer_view, places = layer_cells(graphics, number)
    layer = layer_view.layer
    colors = _palette(graphics)
    picture = Picture(layer.width * layer_view.px, layer.height * layer_view.px, colors)
    known = _layer_tiles(view, layer_view)
    bits = gt.TILE_FORMATS[layer.tile_format][0]
    cache, squares = {}, {}
    now = _cells_now(view, layer_view, number) if layer_view.px == 8 else {}
    for cx, cy, qx, qy, address, cell in places:
        if now:
            address, hflip, vflip, line = now[(cx, cy)]
            cell = _Cell(hflip, vflip, line)
        pixels = cache.get(address)
        if pixels is None:
            tile = known.get(address)
            if tile is not None:
                pixels = _current(tile)
            else:
                raw = graphics.tile_pixels(layer.tile_domain, address, layer.tile_format)
                pixels = list(raw) if raw is not None else [0] * 64
            cache[address] = pixels
        left, top = cx * layer_view.px + qx * 8, cy * layer_view.px + qy * 8
        look = (address, cell.hflip, cell.vflip, cell.palette)
        square = squares.get(look)
        if square is None:
            # one 8x8 square as it lands on the layer, worked out once for every cell that shows it the same way
            slots = [_slot(layer_view.rule, cell.palette, value) for value in _turned(pixels, cell.hflip, cell.vflip)]
            turned = _turned(pixels, cell.hflip, cell.vflip)
            square = squares[look] = (slots, [_rgb(colors, slot, value, bits) for slot, value in zip(slots, turned)],
                                      all(0 <= slot < len(colors) for slot in slots))
        picture.square(left, top, *square)
    return {'png': picture.png(), 'width': picture.width, 'height': picture.height, 'pictures': len(cache),
            'indexed': picture.indexed, 'colors': len(colors), 'layer': layer.name}


# ----------------------------------------------------------------- reading a PNG back

class Imported:
    """A PNG read back: per pixel its color, and its palette number when the file still carries the scene's palette."""

    def __init__(self, raw: bytes, width: int, height: int, colors: list):
        if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_PNG:
            raise ValueError(f'That PNG is larger than {MAX_PNG // 1024} KB. Save it as an 8-bit (palette) PNG and try again.')
        Image = _image()
        try:
            image = Image.open(io.BytesIO(bytes(raw)))
            image.load()
        except Exception:
            raise ValueError('That file is not a PNG picture ROMancer can read.') from None
        if image.format != 'PNG':
            raise ValueError('Choose a PNG picture.')
        if image.size != (width, height):
            raise ValueError(f'This picture is {image.size[0]} x {image.size[1]} pixels. The one saved from this scene is '
                             f'{width} x {height}. Keep the size the same: draw inside the saved picture.')
        self.width, self.height = width, height
        self.slots = None
        if image.mode == 'P' and colors:
            flat = image.getpalette('RGB') or []
            mine = [tuple(flat[i * 3:i * 3 + 3]) for i in range(len(flat) // 3)]
            if mine[:len(colors)] == colors:
                self.slots = image.tobytes()
        rgba = image.convert('RGBA').tobytes()
        self.rgb = [bytes(rgba[i:i + 3]) for i in range(0, len(rgba), 4)]
        self.clear = [rgba[i + 3] < 128 for i in range(0, len(rgba), 4)]
        self.by_number = self.slots is not None

    def at(self, x: int, y: int):
        k = y * self.width + x
        return (self.slots[k] if self.slots is not None else None), tuple(self.rgb[k]), self.clear[k]


class _Cell:
    """A cell as it is now: how its picture is turned and which palette line it uses."""

    def __init__(self, hflip: bool, vflip: bool, palette: int):
        self.hflip, self.vflip, self.palette = hflip, vflip, palette


class Report:
    moved = 0               # cells that now show another picture that the scene already has
    recolored = 0           # of those, cells that keep the palette of where they were put (NES)

    def __init__(self):
        self.off = {}           # (from rgb, to rgb) -> pixels
        self.clear = 0
        self.conflicts = 0      # pictures whose cells disagreed
        self.conflict_cells = 0

    def color(self, source: tuple, target: tuple) -> None:
        self.off[(source, target)] = self.off.get((source, target), 0) + 1

    def rows(self, limit: int = 12) -> list:
        ordered = sorted(self.off.items(), key=lambda item: -item[1])
        return [{'from': '#%02X%02X%02X' % a, 'to': '#%02X%02X%02X' % b, 'pixels': n} for (a, b), n in ordered[:limit]]


def _value(pixel, rule, line: int, bits: int, colors: list, original: int, report: Report) -> int:
    """The picture value (0 .. colors per line - 1) an imported pixel stands for."""
    slot, rgb, clear = pixel
    count = min(1 << bits, rule[2] or (1 << bits))
    if clear:
        report.clear += 1
        return 0
    first = _slot(rule, line, 0)
    if slot is not None and first <= slot < first + count:
        return slot - first
    table = [_rgb(colors, first + value, value, bits) for value in range(count)]
    if table[original] == rgb:
        return original                      # two slots of a line can hold one color: an untouched pixel stays as it was
    best, distance = 0, None
    for value, color in enumerate(table):
        d = (color[0] - rgb[0]) ** 2 + (color[1] - rgb[1]) ** 2 + (color[2] - rgb[2]) ** 2
        if distance is None or d < distance:
            best, distance = value, d
    if distance:
        report.color(rgb, table[best])
    return best


def read_sheet(graphics, view: dict, raw: bytes) -> tuple:
    """({tile id: new pixels} for every picture that differs from the scene, Report)."""
    layout = sheet_layout(view)
    colors = _palette(graphics)
    image = Imported(raw, layout['width'], layout['height'], colors)
    report, wanted = Report(), {}
    for number, tile in enumerate(layout['tiles']):
        left, top = number % COLUMNS * 8, number // COLUMNS * 8
        now = _current(tile)
        new = [_value(image.at(left + k % 8, top + k // 8), tile['pal'], tile['line'], tile['bits'], colors, now[k], report)
               for k in range(64)]
        if new != sg.parse_pixels(tile['pixels'], tile['format']):
            wanted[tile['id']] = new
    report.by_number = image.by_number
    report.covered = {tile['id'] for tile in layout['tiles']}
    return wanted, report


def _exact(image, left: int, top: int, rule, line: int, bits: int, colors: list):
    """The 64 values, in screen order, of an 8x8 square of the PNG if every pixel is a color of this palette line; else None."""
    count = min(1 << bits, rule[2] or (1 << bits))
    first = _slot(rule, line, 0)
    table = None
    out = []
    for y in range(8):
        for x in range(8):
            slot, rgb, clear = image.at(left + x, top + y)
            if clear:
                return None
            if slot is not None:
                if not first <= slot < first + count:
                    return None
                out.append(slot - first)
                continue
            if table is None:
                table = {}
                for value in range(count):
                    table.setdefault(_rgb(colors, first + value, value, bits), value)
            value = table.get(rgb)
            if value is None:
                return None
            out.append(value)
    return tuple(out)


def read_layer(graphics, view: dict, number: int, raw: bytes) -> tuple:
    """({tile id: new pixels} for pictures drawn differently, Report, [cell changes] for cells that show another picture).

    A cell of the PNG that no longer matches the scene is one of two things.
    If its 8x8 square is exactly a picture the scene already has (turned any
    way the layer allows, in any of its palette lines), the cell was given
    that picture: a background change, which leaves the pictures alone. That
    is how a PNG moves, copies or rearranges parts of a background. Any
    other difference is a picture that was drawn on, as before.
    """
    layer_view, places = layer_cells(graphics, number)
    layer = layer_view.layer
    colors = _palette(graphics)
    image = Imported(raw, layer.width * layer_view.px, layer.height * layer_view.px, colors)
    report = Report()
    known = _layer_tiles(view, layer_view)
    bits = gt.TILE_FORMATS[layer.tile_format][0]
    row = next((entry for entry in view['layers'] if entry['index'] == number), {})
    plain = layer_view.px == 8
    now_cells = _cells_now(view, layer_view, number) if plain else {}
    flips = [(False, False)] + ([(True, False), (False, True), (True, True)] if row.get('flips') else [])
    nes = graphics.system == 'nes'          # there one palette choice covers 2 by 2 cells: a cell cannot take its own
    lines = range(4 if nes else int(row.get('lines') or 1))
    looks = None            # {64 values in screen order: (tile address, hflip, vflip)} for every picture of the layer
    votes, shown, moves = {}, {}, []
    for cx, cy, qx, qy, address, cell in places:
        if plain:
            address, hflip, vflip, line = now_cells[(cx, cy)]
            cell = _Cell(hflip, vflip, line)
        tile = known.get(address)
        if tile is None:
            continue
        now = shown.get(tile['id'])
        if now is None:
            now = shown[tile['id']] = _current(tile)
        left, top = cx * layer_view.px + qx * 8, cy * layer_view.px + qy * 8
        if plain:
            # exactly the same square as the scene shows now: nothing to do, and nothing to report
            if _exact(image, left, top, layer_view.rule, cell.palette, bits, colors) == _turned(now, cell.hflip, cell.vflip):
                continue
            if looks is None:
                looks = {}
                for other in known.values():
                    pixels = _current(other)
                    for hflip, vflip in flips:
                        looks.setdefault(_turned(pixels, hflip, vflip), (other['address'], hflip, vflip))
            found = None
            for line in [cell.palette] + [k for k in lines if k != cell.palette]:
                square = _exact(image, left, top, layer_view.rule, line, bits, colors)
                hit = looks.get(square) if square is not None else None
                if hit is not None and (hit[0], hit[1], hit[2], line) != (address, cell.hflip, cell.vflip, cell.palette):
                    found = (hit, line)
                    break
            if found is not None:
                (other, hflip, vflip), line = found
                move = {'layer': number, 'x': cx, 'y': cy, 'tile': sg.tile_id(layer.tile_domain, other, layer.tile_format)}
                if row.get('flips'):
                    move.update(hflip=hflip, vflip=vflip)
                if line != cell.palette:
                    if nes:
                        if other == address:
                            found = None            # only its colors differ, and the cell cannot be given other colors
                        else:
                            report.recolored += 1   # the picture goes there; it keeps the colors of the place it was put
                    else:
                        move['line'] = line
                if found is not None:
                    moves.append(move)
                    continue
        new = [0] * 64
        for k in range(64):
            x, y = _place(k, cell)
            new[k] = _value(image.at(left + x, top + y), layer_view.rule, cell.palette, bits, colors, now[k], report)
        if new != now:
            votes.setdefault(tile['id'], {}).setdefault(tuple(new), []).append((cx, cy))
    wanted = {}
    by_id = {tile['id']: tile for tile in known.values()}
    for ident, now in shown.items():
        final = now
        versions = votes.get(ident)
        if versions:
            ranked = sorted(versions.items(), key=lambda item: -len(item[1]))
            if len(ranked) > 1:
                report.conflicts += 1
                report.conflict_cells += sum(len(cells) for _, cells in ranked[1:])
            final = list(ranked[0][0])
        if final != sg.parse_pixels(by_id[ident]['pixels'], by_id[ident]['format']):
            wanted[ident] = final
    report.by_number = image.by_number
    report.covered = set(shown)
    report.moved = len(moves)
    return wanted, report, moves


# ----------------------------------------------------------------- sprites, put together as the objects they make

GAP = 8                     # pixels between two objects on the sprites PNG
ROW = 320                   # the sheet is at most about this wide
MAX_OBJECTS = 96


def sprite_objects(graphics, view: dict) -> tuple:
    """([object], {tile id: tile}): the sprites on screen, grouped into the objects they make.

    The console draws a character from several small sprites side by side.
    Sprites whose boxes touch or overlap are one object: {'left', 'top',
    'width', 'height' (screen pixels), 'sprites': [(sprite, [tile id])]} with
    the sprites in the console's order, the front one first.
    """
    known = {tile['id']: tile for tile in view['tiles']}
    found = []
    for sprite in graphics.sprites():
        if sprite.guess and sprite.cols > 1:
            continue
        wide, tall = sprite.cols * 8, sprite.rows * 8
        if sprite.x + wide <= 0 or sprite.y + tall <= 0 or sprite.x >= graphics.width or sprite.y >= graphics.height:
            continue
        ids = [sg.tile_id(sprite.domain, address, sprite.fmt) for address in sprite.tiles]
        if all(ident in known for ident in ids):
            found.append((sprite, ids))
    group = list(range(len(found)))

    def root(k):
        while group[k] != k:
            group[k] = group[group[k]]
            k = group[k]
        return k
    for a in range(len(found)):
        sa = found[a][0]
        for b in range(a + 1, len(found)):
            sb = found[b][0]
            if (sa.x - 1 < sb.x + sb.cols * 8 and sb.x - 1 < sa.x + sa.cols * 8
                    and sa.y - 1 < sb.y + sb.rows * 8 and sb.y - 1 < sa.y + sa.rows * 8):
                group[root(a)] = root(b)
    sets: dict = {}
    for k, item in enumerate(found):
        sets.setdefault(root(k), []).append(item)
    objects = []
    for members in sets.values():
        left = min(s.x for s, _ in members)
        top = min(s.y for s, _ in members)
        right = max(s.x + s.cols * 8 for s, _ in members)
        bottom = max(s.y + s.rows * 8 for s, _ in members)
        if right - left <= ROW and bottom - top <= ROW:
            objects.append({'left': left, 'top': top, 'width': right - left, 'height': bottom - top, 'sprites': members})
    objects.sort(key=lambda o: (o['top'], o['left']))
    return objects[:MAX_OBJECTS], known


def sprite_layout(objects: list) -> tuple:
    """([(x, y) of each object on the sheet], sheet width, sheet height): rows of objects, a gap between them."""
    places, x, y, tall, wide = [], GAP, GAP, 0, GAP
    for obj in objects:
        if x > GAP and x + obj['width'] + GAP > ROW:
            x, y, tall = GAP, y + tall + GAP, 0
        places.append((x, y))
        x += obj['width'] + GAP
        tall = max(tall, obj['height'])
        wide = max(wide, x)
    return places, wide, y + tall + GAP


def _sprite_at(obj: dict, known: dict, x: int, y: int, shown: dict):
    """(sprite, tile id, pixel number in the tile, value) that an object shows at one of its pixels, or None outside every sprite.

    Where sprites overlap the front one with something drawn there is
    shown. A pixel that is empty in all of them belongs to the front one.
    """
    first = None
    for sprite, ids in obj['sprites']:
        lx, ly = obj['left'] + x - sprite.x, obj['top'] + y - sprite.y
        wide, tall = sprite.cols * 8, sprite.rows * 8
        if not (0 <= lx < wide and 0 <= ly < tall):
            continue
        if sprite.hflip:
            lx = wide - 1 - lx
        if sprite.vflip:
            ly = tall - 1 - ly
        ident = ids[(ly // 8) * sprite.cols + lx // 8]
        k = (ly % 8) * 8 + lx % 8
        pixels = shown.get(ident)
        if pixels is None:
            pixels = shown[ident] = _current(known[ident])
        value = pixels[k]
        if value:
            return sprite, ident, k, value
        if first is None:
            first = (sprite, ident, k, 0)
    return first


def export_sprites(graphics, view: dict) -> dict:
    """One PNG with every object the sprites on screen make, each put together as the game shows it."""
    objects, known = sprite_objects(graphics, view)
    if not objects:
        raise ValueError('ROMancer found no sprites on this screen to save.')
    places, width, height = sprite_layout(objects)
    colors = _palette(graphics)
    picture = Picture(width, height, colors)
    sprite, ids = objects[0]['sprites'][0]
    empty = _slot(known[ids[0]]['pal'], sprite.line, 0)
    blank = _rgb(colors, empty, 0, known[ids[0]]['bits'])
    for y in range(height):
        for x in range(width):
            picture.put(x, y, empty, blank)
    shown: dict = {}
    for obj, (left, top) in zip(objects, places):
        for y in range(obj['height']):
            for x in range(obj['width']):
                hit = _sprite_at(obj, known, x, y, shown)
                if hit is None:
                    continue
                sprite, ident, k, value = hit
                tile = known[ident]
                slot = _slot(tile['pal'], sprite.line, value)
                picture.put(left + x, top + y, slot, _rgb(colors, slot, value, tile['bits']))
    return {'png': picture.png(), 'width': width, 'height': height, 'pictures': len({i for o in objects for _, ids in o['sprites'] for i in ids}),
            'objects': len(objects), 'indexed': picture.indexed, 'colors': len(colors)}


def read_sprites(graphics, view: dict, raw: bytes) -> tuple:
    """({tile id: new pixels} for the pictures drawn on, Report) from a PNG saved by export_sprites.

    A pixel drawn on an object goes to the picture of the sprite that shows
    it there. Pixels drawn between objects, outside every sprite, are not
    part of any picture and are left alone.
    """
    objects, known = sprite_objects(graphics, view)
    if not objects:
        raise ValueError('ROMancer found no sprites on this screen, so there is nothing to load a sprites PNG into.')
    places, width, height = sprite_layout(objects)
    colors = _palette(graphics)
    image = Imported(raw, width, height, colors)
    report = Report()
    edits: dict = {}
    covered = set()
    shown: dict = {}
    for obj, (left, top) in zip(objects, places):
        for y in range(obj['height']):
            for x in range(obj['width']):
                hit = _sprite_at(obj, known, x, y, shown)
                if hit is None:
                    continue
                sprite, ident, k, now = hit
                covered.add(ident)
                tile = known[ident]
                new = _value(image.at(left + x, top + y), tile['pal'], sprite.line, tile['bits'], colors, now, report)
                if new == now:
                    continue
                marks = edits.setdefault(ident, {})
                if k in marks and marks[k] != new:
                    report.conflict_cells += 1
                marks[k] = new
    wanted = {}
    for ident, marks in edits.items():
        pixels = list(shown[ident])
        for k, value in marks.items():
            pixels[k] = value
        if pixels != sg.parse_pixels(known[ident]['pixels'], known[ident]['format']):
            wanted[ident] = pixels
    report.conflicts = 1 if report.conflict_cells else 0
    report.by_number = image.by_number
    report.covered = covered
    return wanted, report


def summary(report: Report, wanted: int, skipped: list) -> str:
    def plural(n, word):
        return f'{n:,} {word}{"" if n == 1 else "s"}'
    notes = []
    if not wanted:
        notes.append('PNG read. It is the same as the scene, so there is nothing to change.')
    else:
        notes.append(f'PNG read: {plural(wanted, "picture")} changed.')
    if report.off:
        pixels = sum(report.off.values())
        notes.append(f'{plural(len(report.off), "color")} in it {"is" if len(report.off) == 1 else "are"} not in the palette line of the '
                     f'picture {"it is" if len(report.off) == 1 else "they are"} drawn on; {plural(pixels, "pixel")} '
                     f'{"was" if pixels == 1 else "were"} changed to the nearest color of that line.')
    elif wanted:
        notes.append('Every color in it belongs to the palette line of the picture it is drawn on.')
    if report.clear:
        notes.append(f'{plural(report.clear, "see-through pixel")} became color 0.')
    if report.conflicts:
        notes.append(f'{plural(report.conflicts, "picture")} {"is" if report.conflicts == 1 else "are"} shown in several places that you '
                     f'drew differently. The version drawn most often was used; {plural(report.conflict_cells, "place")} '
                     f'will show it instead of what you drew there.')
    if skipped:
        notes.append(f'{plural(len(skipped), "picture")} you changed cannot be changed and {"was" if len(skipped) == 1 else "were"} left out.')
    return ' '.join(notes)
