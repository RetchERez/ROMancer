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
        for k, value in enumerate(pixels):
            slot = _slot(tile['pal'], tile['line'], value)
            picture.put(left + k % 8, top + k // 8, slot, _rgb(colors, slot, value, tile['bits']))
    return {'png': picture.png(), 'width': picture.width, 'height': picture.height, 'pictures': len(layout['tiles']),
            'indexed': picture.indexed, 'colors': len(colors)}


def layer_cells(graphics, number: int):
    """(layer view, [(cell x, cell y, quadrant x, quadrant y, tile address, cell)]) for a background layer that has a flat picture."""
    layers = graphics.layers()
    if not 0 <= number < len(layers):
        raise ValueError('That background layer is not part of this scene.')
    view = layers[number]
    layer = view.layer
    if layer.tile_format == 'snes-mode7':
        raise ValueError('This layer is drawn in perspective (Mode 7), so it has no flat picture to save. Use the sheet instead.')
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


def _layer_tiles(view: dict, layer_view) -> dict:
    layer = layer_view.layer
    return {tile['address']: tile for tile in view['tiles']
            if tile['domain'] == layer.tile_domain and tile['format'] == layer.tile_format}


def _place(k: int, cell) -> tuple:
    """Where pixel k of a picture lands inside its 8x8 square on the layer, with the cell's flips."""
    x, y = k % 8, k // 8
    return (7 - x if cell.hflip else x), (7 - y if cell.vflip else y)


def export_layer(graphics, view: dict, number: int) -> dict:
    layer_view, places = layer_cells(graphics, number)
    layer = layer_view.layer
    colors = _palette(graphics)
    picture = Picture(layer.width * layer_view.px, layer.height * layer_view.px, colors)
    known = _layer_tiles(view, layer_view)
    bits = gt.TILE_FORMATS[layer.tile_format][0]
    cache = {}
    for cx, cy, qx, qy, address, cell in places:
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
        for k, value in enumerate(pixels):
            x, y = _place(k, cell)
            slot = _slot(layer_view.rule, cell.palette, value)
            picture.put(left + x, top + y, slot, _rgb(colors, slot, value, bits))
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


class Report:
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


def read_layer(graphics, view: dict, number: int, raw: bytes) -> tuple:
    layer_view, places = layer_cells(graphics, number)
    layer = layer_view.layer
    colors = _palette(graphics)
    image = Imported(raw, layer.width * layer_view.px, layer.height * layer_view.px, colors)
    report = Report()
    known = _layer_tiles(view, layer_view)
    bits = gt.TILE_FORMATS[layer.tile_format][0]
    votes, shown = {}, {}
    for cx, cy, qx, qy, address, cell in places:
        tile = known.get(address)
        if tile is None:
            continue
        now = shown.get(tile['id'])
        if now is None:
            now = shown[tile['id']] = _current(tile)
        left, top = cx * layer_view.px + qx * 8, cy * layer_view.px + qy * 8
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
