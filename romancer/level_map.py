"""A level map: the background of a level put together from scenes captured while the game scrolled.

A scene holds the background as the console had it at one moment: a small
map the game keeps redrawing as it scrolls. scene_graphics finds where that
map sits on the recorded screen (how far it is scrolled, for each screen
line). This module follows that scroll from one capture to the next and
lays the part each capture shows into one large map.

    stitch(frames, system) -> [Plane]: one map for each background layer that scrolled
    Plane.cells            {(column, row): Spot}: which scene, layer and cell shows that place
    Plane.cover()          the fewest captures that still show the whole map
    Plane.picture(frames)  a picture of the whole map
    Plane.changed(...)     the places an edit changes, drawn into that picture

Nothing here reads the ROM or guesses a format: a place on the map is only
ever a cell of a recorded scene, so every edit made on the map is an edit of
that cell in that scene, planned and replayed by the scene editor.

How the pieces are placed. The captured map wraps around (a 256 pixel wide
map shows pixel 300 at 44), so the scroll of one capture says where the screen
is only up to the size of the map. The nearest place to the last capture is
tried first. When that contradicts what the map already holds, the capture
is looked for anywhere on the map (a restart, a way back to a room seen
before). When that does not fit either, the game drew a new picture in the
same place (a new room, a door), and a new section is started beside the
old one. Captures are taken often enough that the screen never moves half a
console map between two of them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MIN_LINES = 48          # a band must cover this many screen lines to count as the level
MIN_MATCH = 0.10        # and the layer must be found on at least this share of the screen
CELL_MATCH = 0.85
WEAK_MATCH = 0.3        # below CELL_MATCH something covers the cell; above this the layer is still the likeliest one there       # share of a cell's pixels that must agree with the screen, where two layers share one map
BREAK = 0.25            # share of overlapping cells that may disagree before a new section starts
GAP = 4                 # empty columns between sections
EMPTY = (24, 24, 32)    # the color of places no capture showed
HATCH = (58, 58, 76)    # and of the fine lines drawn across them


@dataclass
class Frame:
    """One captured scene, in the order the captures were taken."""
    scene_id: str
    graphics: object            # scene_graphics.SceneGraphics
    frame: int = 0              # the game frame it was captured at


@dataclass
class Spot:
    frame: int                  # index into the frames given to stitch
    layer: int                  # index into graphics.layers()
    x: int                      # cell of that layer
    y: int


@dataclass
class Window:
    """What one capture shows of a plane: where the screen was, and the cells it saw."""
    section: int
    across: int                 # map pixel at the left edge of the screen
    down: int                   # map pixel at the top line of the screen
    first: int                  # first screen line of the band
    last: int                   # line after its last
    cells: dict                 # (column, row) -> Spot
    weak: dict = field(default_factory=dict)    # places where something (a sprite) hid the background: the likeliest Spot


@dataclass
class Plane:
    name: str
    px: int                                         # pixels per cell (8, or 16 for large cells)
    layers: tuple = ()                              # layer indices that make up this plane
    windows: dict = field(default_factory=dict)     # frame index -> Window
    cells: dict = field(default_factory=dict)       # (column, row) -> Spot, from the frames given to assign()
    sections: list = field(default_factory=list)    # [first column, column after the last] of each section, after assign()

    def assign(self, chosen=None) -> 'Plane':
        """Fill `cells` from these frames (all of them when None); where two show one place the later capture wins."""
        self.cells = {}
        spans: dict = {}
        weak: dict = {}
        for number in sorted(self.windows):
            if chosen is not None and number not in chosen:
                continue
            window = self.windows[number]
            self.cells.update(window.cells)
            for place, spot in window.weak.items():
                weak.setdefault(place, spot)
            if window.cells:
                low = min(c[0] for c in window.cells)
                high = max(c[0] for c in window.cells) + 1
                span = spans.setdefault(window.section, [low, high])
                span[0], span[1] = min(span[0], low), max(span[1], high)
        self.sections = [spans[k] for k in sorted(spans)]
        for place, spot in weak.items():            # a place only ever seen behind a sprite still belongs on the map
            self.cells.setdefault(place, spot)
        return self

    def trim(self, fixed: set) -> None:
        """Leave these rows of the screen (counted in cells from the top) out of every capture: a status bar."""
        if not fixed:
            return
        px = self.px
        for window in self.windows.values():
            def moving(place):
                return (place[1] * px - window.down) // px not in fixed
            window.cells = {place: spot for place, spot in window.cells.items() if moving(place)}
            window.weak = {place: spot for place, spot in window.weak.items() if moving(place)}
        self.windows = {number: window for number, window in self.windows.items() if window.cells}

    def cover(self) -> list:
        """The fewest frames that still show every place: each time the frame that adds the most."""
        left = set()
        for window in self.windows.values():
            left.update(window.cells)
        chosen = []
        while left:
            best = max(self.windows, key=lambda n: (len(left.intersection(self.windows[n].cells)), -n))
            gain = left.intersection(self.windows[best].cells)
            if not gain:
                break
            chosen.append(best)
            left -= gain
        return sorted(chosen)

    def bounds(self) -> tuple:
        xs = [c[0] for c in self.cells]
        ys = [c[1] for c in self.cells]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    def size(self) -> tuple:
        left, top, right, bottom = self.bounds()
        return right - left, bottom - top

    def spot(self, column: int, row: int):
        """The Spot at a place counted from the top left corner of the map."""
        left, top, _, _ = self.bounds()
        return self.cells.get((column + left, row + top))

    def picture(self, frames: list, screens: dict | None = None):
        """A PIL image of the whole map; places no capture showed are left dark.

        With `screens` ({frame index: picture of that capture's screen with every background layer and no sprites,
        from screen_picture}) a place shows all the layers the game drew there, not only this plane.
        """
        from PIL import Image
        left, top, right, bottom = self.bounds()
        px = self.px
        out = _unseen((right - left) * px, (bottom - top) * px)
        pictures = {}
        for (column, row), spot in self.cells.items():
            window = self.windows.get(spot.frame)
            screen = screens.get(spot.frame) if screens else None
            if screen is not None and window is not None:
                x, y = column * px - window.across, row * px - window.down
                if x >= 0 and y >= window.first and x + px <= screen.width and y + px <= window.last:
                    out.paste(screen.crop((x, y, x + px, y + px)), ((column - left) * px, (row - top) * px))
                    continue
            key = (spot.frame, spot.layer)
            picture = pictures.get(key)
            if picture is None:
                picture = pictures[key] = _layer_picture(frames[spot.frame].graphics, spot.layer)
            box = (spot.x * px, spot.y * px, spot.x * px + px, spot.y * px + px)
            out.paste(picture.crop(box), ((column - left) * px, (row - top) * px))
        return out

    def changed(self, picture, shots: dict) -> list:
        """Paste what changed on screen into a picture of the map; returns the places that changed.

        `shots` is {frame index: (width, height, RGB before, RGB after)}: the
        recorded screen of a capture and the same moment replayed with an edit.
        A place is redrawn from the capture the map took it from, and only
        where the two screens differ, so sprites do not land on the map.
        """
        from PIL import Image, ImageChops
        left, top, _, _ = self.bounds()
        px = self.px
        images = {}
        places = []
        for (column, row), spot in sorted(self.cells.items()):
            shot = shots.get(spot.frame)
            window = self.windows.get(spot.frame)
            if shot is None or window is None:
                continue
            pair = images.get(spot.frame)
            if pair is None:
                width, height, before, after = shot
                pair = images[spot.frame] = (Image.frombytes('RGB', (width, height), before),
                                             Image.frombytes('RGB', (width, height), after))
            x, y = column * px - window.across, row * px - window.down
            if x < 0 or y < window.first or x + px > pair[0].width or y + px > window.last:
                continue
            box = (x, y, x + px, y + px)
            piece = pair[1].crop(box)
            if ImageChops.difference(pair[0].crop(box), piece).getbbox() is None:
                continue
            picture.paste(piece, ((column - left) * px, (row - top) * px))
            places.append((column - left, row - top))
        return places


def _unseen(width: int, height: int):
    """The ground of a map picture: fine diagonal lines, so a place no capture showed reads as not seen, not as black."""
    from PIL import Image
    tile = Image.new('RGB', (8, 8), EMPTY)
    for k in range(8):
        tile.putpixel((k, 7 - k), HATCH)
    out = Image.new('RGB', (width, height), EMPTY)
    for y in range(0, height, 8):
        for x in range(0, width, 8):
            out.paste(tile, (x, y))
    return out


def _layer_picture(graphics, number: int):
    from PIL import Image
    view = graphics.layers()[number]
    wide, tall = view.layer.width * view.px, view.layer.height * view.px
    picture = Image.frombytes('P', (wide, tall), b''.join(view.rows))
    palette = [0] * 768
    for index, color in enumerate(graphics.reps):
        palette[3 * index:3 * index + 3] = color
    palette[3 * 254:3 * 254 + 3] = EMPTY
    picture.putpalette(palette)
    return picture.convert('RGB')


SEE_THROUGH = ('genesis', 'snes')       # systems whose background layers show the layer behind where a picture is empty


def _layer_mask(graphics, number: int):
    """Where a layer is solid: an 'L' image the size of the layer, 255 where its picture has something to show."""
    from PIL import Image
    view = graphics.layers()[number]
    layer, px = view.layer, view.px
    out = Image.new('L', (layer.width * px, layer.height * px), 0)
    cache = {}
    quads = px // 8
    for cell in layer.cells:
        for qy in range(quads):
            for qx in range(quads):
                address = graphics._subtile(view, cell, qx, qy)
                key = (address, cell.hflip, cell.vflip)
                tile = cache.get(key)
                if tile is None:
                    pixels = graphics.tile_pixels(layer.tile_domain, address, layer.tile_format)
                    tile = Image.frombytes('L', (8, 8), bytes(255 if p else 0 for p in pixels)) if pixels else Image.new('L', (8, 8), 0)
                    if cell.hflip:
                        tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
                    if cell.vflip:
                        tile = tile.transpose(Image.FLIP_TOP_BOTTOM)
                    cache[key] = tile
                out.paste(tile, (cell.x * px + qx * 8, cell.y * px + qy * 8))
    return out


def _on_screen(graphics, view, picture, fill):
    """A layer picture laid on the screen the way the game scrolled it, line band by line band."""
    from PIL import Image
    wide, tall = picture.size
    twice = Image.new(picture.mode, (wide * 2, tall * 2))
    for at in ((0, 0), (wide, 0), (0, tall), (wide, tall)):
        twice.paste(picture, at)
    out = Image.new(picture.mode, (graphics.width, graphics.height), fill)
    for first, last, across, down in graphics.bands(view):
        x, y = across % wide, (first + down) % tall
        for start in range(0, graphics.width, wide):                    # a screen wider than the layer shows it again
            piece = twice.crop((x, y, x + min(wide, graphics.width - start), y + last - first))
            out.paste(piece, (start, first))
    return out


def screen_picture(graphics, system: str):
    """The recorded screen with every background layer and no sprites, as a PIL RGB image.

    The layers are drawn back to front in the order the console lists them.
    Which layer is in front can also be decided for each cell by the game, so
    the recorded screen settles it: wherever the screen shows the color of
    some layer's solid pixel, that is what goes on the map. What is left are
    the pixels a sprite covered, and those keep the layers' own picture.
    """
    from PIL import Image, ImageChops
    width, height = graphics.width, graphics.height
    shot = Image.new('RGB', (width, height))
    palette = [tuple(color) for color in graphics.reps] + [EMPTY] * (256 - len(graphics.reps))
    shot.putdata([palette[value] if value != 254 else EMPTY for line in graphics.screen for value in line])
    layers = [(number, view) for number, view in enumerate(graphics.layers()) if view.rows is not None and view.lines and view.match >= 0.05]
    if not layers:
        return shot
    out = Image.new('RGB', (width, height), EMPTY)
    covered = Image.new('L', (width, height), 0)
    agrees = Image.new('L', (width, height), 0)
    for number, view in reversed(layers):                               # the first layer listed is the front one
        picture = _on_screen(graphics, view, _layer_picture(graphics, number), EMPTY)
        if system in SEE_THROUGH:
            solid = _on_screen(graphics, view, _layer_mask(graphics, number), 0)
        else:
            solid = _on_screen(graphics, view, Image.new('L', (view.layer.width * view.px, view.layer.height * view.px), 255), 0)
        out.paste(picture, (0, 0), solid)
        covered = ImageChops.lighter(covered, solid)
        same = ImageChops.difference(picture, shot).convert('L').point(lambda v: 255 if v == 0 else 0)
        agrees = ImageChops.lighter(agrees, ImageChops.multiply(same, solid))
    # where no layer is solid the game shows its backdrop color: take it from the screen
    backdrop = covered.point(lambda v: 0 if v else 255)
    out.paste(shot, (0, 0), ImageChops.lighter(agrees, backdrop))
    return out


def plane_key(system: str, name: str) -> str:
    """Layers that are parts of one map share a key: the NES keeps its background in up to four nametables side by side."""
    if system == 'nes' and name.startswith('nametable'):
        return 'Background'
    return name


def placement(graphics, view):
    """(first line, line after the last, scrolled across, scrolled down) of the widest band, or None when the layer is not on screen."""
    if view.rows is None or not view.lines or view.match < MIN_MATCH:
        return None
    bands = graphics.bands(view)
    if not bands:
        return None
    best = max(bands, key=lambda b: b[1] - b[0])
    if best[1] - best[0] < MIN_LINES:
        return None
    return tuple(best)


def _wrap(delta: int, size: int) -> int:
    """The shorter way round a map of this size."""
    delta %= size
    return delta - size if delta > size // 2 else delta


def _agrees(graphics, view, x0: int, y0: int, mx: int, my: int) -> float:
    """Share of a cell's pixels where the layer and the recorded screen hold the same color; x0, y0 is its screen corner."""
    px = view.px
    wide = view.layer.width * px
    same = total = 0
    for dy in range(0, px, 2):
        y = y0 + dy
        if not 0 <= y < graphics.height:
            continue
        row, line = view.rows[(my + dy) % len(view.rows)], graphics.screen[y]
        for dx in range(0, px, 2):
            x = x0 + dx
            if 0 <= x < graphics.width:
                total += 1
                same += row[(mx + dx) % wide] == line[x]
    return same / total if total else 0.0


def _look(graphics, view, x: int, y: int):
    """What a cell shows, for telling whether two captures show the same thing in one place: which picture, and how it is
    turned. Not its colors (a fade is not another room) and not its pixels (games animate water and flowers by redrawing
    the picture in place)."""
    cell = view.layer.cell(x, y)
    return (cell.tile_address, cell.hflip, cell.vflip)


def _settle_tables(plane, runs: list) -> None:
    """Decide which of two tables that share one map (the NES nametables) each place of the map was drawn from.

    The console lays the two tables side by side (or one above the other)
    and repeats the pair, so along a stretch of unbroken scrolling the table
    alternates every table width (or height). That leaves four ways a
    stretch can be: side by side or stacked, starting with either table. The
    way that agrees best with the recorded screens over the whole stretch is
    taken. Looking at one screen is not enough: where a level repeats, both
    tables hold the same picture and either would do, but only one of them
    is the place in the level, and an edit made in the other lands a screen
    away. Ties go to the layout the cartridge header names and the table the
    picture chip was set to.
    """
    px = plane.px
    for run in runs:
        totals = {}
        for number, shift, wide, tall, tables, graphics, seen in run:
            for (gx, gy, index), score in seen.items():
                for across in (True, False):
                    turn = ((gx * px // wide) if across else (gy * px // tall)) & 1
                    start = tables.index(index) ^ turn          # the table at turn 0 if this one is shown here
                    totals[(across, start)] = totals.get((across, start), 0.0) + score
        if not totals:
            continue
        number, shift, wide, tall, tables, graphics, seen = run[0]
        rom = getattr(graphics, 'rom', b'') or b''
        header = bool(rom[6] & 1) if rom[:4] == b'NES\x1a' and len(rom) > 6 else True      # vertical mirroring: side by side
        control = (getattr(graphics, 'video', None) or {}).get('ppuctrl')
        left = min(gx for gx, _, _ in seen)
        top = min(gy for _, gy, _ in seen)

        def liking(way):
            across, start = way
            named = 1 if across == header else 0
            if control is not None:
                turn = ((left * px // wide) if across else (top * px // tall)) & 1
                named += 1 if ((control & 1) if across else (control >> 1 & 1)) == start ^ turn else 0
            return named
        best = max(totals.values())
        across, start = max((way for way, total in totals.items() if total >= best * 0.995), key=liking)
        for number, shift, wide, tall, tables, graphics, seen in run:
            window = plane.windows.get(number)
            if window is None:
                continue
            layers = graphics.layers()
            cells, weak = {}, {}
            for gx, gy in {(gx, gy) for gx, gy, _ in seen}:
                turn = ((gx * px // wide) if across else (gy * px // tall)) & 1
                index = tables[start ^ turn]
                score = seen[(gx, gy, index)]
                spot = Spot(number, index, (gx * px % wide) // px, (gy * px % tall) // px)
                if score >= CELL_MATCH:
                    cells[(gx + shift, gy)] = spot
                elif score >= WEAK_MATCH:
                    weak[(gx + shift, gy)] = spot
            if cells:
                window.cells, window.weak = cells, weak


def stitch(frames: list, system: str) -> list:
    """Planes of the level with every frame assigned, the largest first."""
    planes: dict = {}
    track: dict = {}            # key -> {'at': (sx, sy, U, V), 'shift', 'section', 'looks', 'where', 'right'}
    for number, frame in enumerate(frames):
        graphics = frame.graphics
        layers = graphics.layers()
        groups: dict = {}
        for index, view in enumerate(layers):
            if view.rows is not None:
                groups.setdefault((plane_key(system, view.layer.name), view.px), []).append((index, view))
        for (name, px), members in groups.items():
            # Layers that share one map sit at one scroll: the one found best on the screen says where.
            placed = [(view.match, placement(graphics, view), view) for _, view in members]
            placed = [item for item in placed if item[1] is not None]
            if not placed:
                continue
            _, (y0, y1, sx, sy), lead = max(placed, key=lambda item: item[0])
            wide, tall = lead.layer.width * px, lead.layer.height * px
            members = [(index, view) for index, view in members if (view.layer.width * px, view.layer.height * px) == (wide, tall)]
            plane = planes.get((name, px))
            if plane is None:
                plane = planes[(name, px)] = Plane(name, px)
                track[(name, px)] = {'at': None, 'shift': 0, 'section': 0, 'looks': {}, 'where': {}, 'right': None, 'still': {}, 'rows': None, 'runs': []}
            state = track[(name, px)]
            last = state['at']
            if last is None:
                U, V = sx, sy
            else:
                U = last[2] + _wrap(sx - last[0], wide)
                V = last[3] + _wrap(sy - last[1], tall)
            shared = len(members) > 1
            fresh, hidden = {}, {}
            # Which layer shows where? Layers that share one map (the nametables of the NES) each fill a part of the
            # screen, and the parts meet where the map wraps round. A level that repeats looks the same in two layers
            # at once, so the choice is made for each part as a whole, by how well each layer agrees with the screen
            # over all of it, and not cell by cell.
            scores: dict = {}
            agreement: dict = {}
            for gy in range(-((-(V + y0)) // px), (V + y1) // px):              # cells that are whole on the screen
                for gx in range(-((-U) // px), (U + graphics.width) // px):
                    mx, my = (gx * px) % wide, (gy * px) % tall
                    part = (mx >= U % wide, my >= V % tall)
                    for index, view in members:
                        score = _agrees(graphics, view, gx * px - U, gy * px - V, mx, my) if shared else 1.0
                        agreement[(gx, gy, index)] = score
                        scores[(part, index)] = scores.get((part, index), 0.0) + score
            for gy in range(-((-(V + y0)) // px), (V + y1) // px):
                for gx in range(-((-U) // px), (U + graphics.width) // px):
                    mx, my = (gx * px) % wide, (gy * px) % tall
                    part = (mx >= U % wide, my >= V % tall)
                    index, view = max(members, key=lambda member: scores[(part, member[0])])
                    score = agreement[(gx, gy, index)]
                    if score >= (CELL_MATCH if shared else 0):
                        fresh[(gx, gy)] = (Spot(number, index, mx // px, my // px), _look(graphics, view, mx // px, my // px))
                    elif score >= WEAK_MATCH:
                        hidden[(gx, gy)] = Spot(number, index, mx // px, my // px)
            tally: dict = {}
            for value in fresh.values():
                tally[value[1]] = tally.get(value[1], 0) + 1
            if len(tally) < 4:
                continue                    # a blank or one-picture screen can be found at any scroll: it places nothing
            filler = {look for look, count in tally.items() if count * 25 > len(fresh)}     # sky, plain ground
            shift = state['shift']

            def clash(dx, dy):
                """(places also on the map, how many of them show something else) with the capture moved this many cells.

                Filler (a picture that covers more than a twenty-fifth of the screen) agrees with filler almost
                anywhere, so places that show it both on the map and in the capture are counted only when little else is.
                """
                both = differ = plain = 0
                for place, value in fresh.items():
                    known = state['looks'].get((place[0] + dx + shift, place[1] + dy))
                    if known is None:
                        continue
                    if known[0] == value[1] and value[1] in filler:
                        plain += 1
                        continue
                    both += 1
                    differ += known[0] != value[1]
                if both < 12:
                    both += plain
                return both, differ

            def fits(dx, dy):
                both, differ = clash(dx, dy)
                return both >= 24 and differ <= BREAK * both

            # Where does this capture go? The scroll wraps, and a game also jumps about (a restart, a door back to a
            # room seen before), so the nearest place is only the first one tried:
            #   1. the nearest place, when it agrees with the map or the map does not reach there yet;
            #   2. a place anywhere on the map that the capture agrees with (found from its least common pictures);
            #   3. otherwise the game drew a new picture in the same place: a new section.
            moved, jumped = None, last is None
            both, differ = clash(0, 0)
            if both < 24 or differ <= BREAK * both:
                moved = (0, 0)
            if moved is None:
                votes: dict = {}
                rare = sorted(fresh.items(), key=lambda item: len(state['where'].get(item[1][1], ())) or 10 ** 6)[:40]
                for place, value in rare:
                    for at in state['where'].get(value[1], ())[:60]:
                        offset = (at[0] - shift - place[0], at[1] - place[1])
                        votes[offset] = votes.get(offset, 0) + 1
                for offset, count in sorted(votes.items(), key=lambda item: -item[1])[:6]:
                    if count >= 6 and fits(*offset):
                        moved, jumped = offset, True
                        break
            if moved is None:
                shift = state['shift'] = state['right'] + GAP - min(place[0] for place in fresh)
                state['section'] += 1
                moved, jumped = (0, 0), True
            if moved != (0, 0):
                dx, dy = moved
                fresh = {(place[0] + dx, place[1] + dy): value for place, value in fresh.items()}
                hidden = {(place[0] + dx, place[1] + dy): spot for place, spot in hidden.items()}
                U, V = U + dx * px, V + dy * px
            seen = [state['looks'][at][1] for at in ((place[0] + shift, place[1]) for place in fresh) if at in state['looks']]
            section = max(set(seen), key=seen.count) if seen else state['section']
            cells = {}
            for place, (spot, look) in fresh.items():
                at = (place[0] + shift, place[1])
                cells[at] = spot
                if at not in state['looks']:
                    state['where'].setdefault(look, []).append(at)
                state['looks'][at] = (look, section)
            plane.windows[number] = Window(section, U + shift * px, V, y0, y1, cells,
                                           {(place[0] + shift, place[1]): spot for place, spot in hidden.items()})
            if shared and len(members) == 2:
                # remembered for _settle_tables: how well each of the two tables agreed with the screen at every cell
                if jumped or not state['runs']:
                    state['runs'].append([])
                state['runs'][-1].append((number, shift, wide, tall, [index for index, _ in members], graphics,
                                          {(gx + moved[0], gy + moved[1], index): score for (gx, gy, index), score in agreement.items()}))
            edge = max(c[0] for c in cells) + 1
            state['right'] = edge if state['right'] is None else max(state['right'], edge)
            plane.layers = tuple(sorted(set(plane.layers) | {spot.layer for spot in cells.values()}))
            # which rows of the screen stand still while the map moves under them (a status bar)?
            rows = {}
            for row in range(graphics.height // px):
                lines = graphics.screen[row * px:row * px + px]
                rows[row] = [b''.join(line[x:x + px] for line in lines) for x in range(0, graphics.width - px + 1, px)]
            before = state['rows']
            if before is not None and (abs(U - before[1]) >= px or abs(V - before[2]) >= px):
                for row, columns in rows.items():
                    old = before[0].get(row)
                    if old is None or len(set(columns)) < 4:
                        continue                    # plain sky looks the same wherever the screen is: it says nothing
                    alike = sum(1 for a, b in zip(columns, old) if a == b)      # a clock or a score may tick in a few places
                    same, seen = state['still'].get(row, (0, 0))
                    state['still'][row] = (same + (alike * 4 >= len(columns) * 3), seen + 1)
            state['rows'] = (rows, U, V)
            state['at'] = (sx, sy, U, V)
    for key, plane in planes.items():
        _settle_tables(plane, track[key]['runs'])
    for key, plane in planes.items():
        # A row of the screen that held the same varied picture while the level scrolled past is not part of the level.
        still = track[key]['still']
        fixed = {row for row, (same, seen) in still.items() if seen >= 3 and same >= 0.8 * seen}
        count = frames[0].graphics.height // plane.px
        above = [row for row in fixed if row < count // 3]
        below = [row for row in fixed if row >= count - count // 3]
        if above:                                   # blank lines between a status bar and the edge of the screen go with it
            fixed.update(range(max(above) + 1))
        if below:
            fixed.update(range(min(below), count + 1))
        plane.trim(fixed)
    found = [plane.assign() for plane in planes.values() if plane.windows]
    found.sort(key=lambda plane: -len(plane.cells))
    return found
