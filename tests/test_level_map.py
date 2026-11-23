import unittest
from types import SimpleNamespace

from romancer import level_map as lm

PX = 8
LAYER_W, LAYER_H = 32, 30          # cells of the map the console keeps
SCREEN_W, SCREEN_H = 256, 224


class FakeLayer:
    name = 'background'
    tile_domain = 'vram'
    tile_format = 'test'
    width, height = LAYER_W, LAYER_H

    def __init__(self, tiles):
        self.tiles = tiles                              # {(x, y): tile number}
        self.cells = [self.cell(x, y) for y in range(LAYER_H) for x in range(LAYER_W)]

    def cell(self, x, y):
        return SimpleNamespace(x=x, y=y, tile_address=self.tiles[(x, y)], hflip=False, vflip=False, palette=0, status='rom')


class FakeGraphics:
    """One layer scrolled to (across, down) over a large level whose cell at (column, row) shows tile world(column, row)."""
    width, height = SCREEN_W, SCREEN_H
    reps = [(v, v, v) for v in range(250)]

    def __init__(self, world, across, down=0):
        tiles = {}
        first_column, first_row = across // PX, down // PX
        for row in range(first_row, first_row + LAYER_H):
            for column in range(first_column, first_column + LAYER_W):
                tiles[(column % LAYER_W, row % LAYER_H)] = world(column, row)
        self.layer = FakeLayer(tiles)
        rows = []
        for y in range(LAYER_H * PX):
            rows.append(bytes(self.layer.tiles[(x // PX, y // PX)] % 250 for x in range(LAYER_W * PX)))
        lines = [(across % (LAYER_W * PX), down % (LAYER_H * PX))] * SCREEN_H
        self.view = SimpleNamespace(layer=self.layer, px=PX, rows=rows, lines=lines, match=1.0, source='picture')
        self.screen = [bytes(rows[(y + lines[y][1]) % len(rows)][(x + lines[y][0]) % (LAYER_W * PX)] for x in range(SCREEN_W))
                       for y in range(SCREEN_H)]

    def layers(self):
        return [self.view]

    def bands(self, view):
        return [[0, SCREEN_H, *view.lines[0]]]

    def tile_pixels(self, domain, address, fmt):
        return bytes([address % 250]) * 64


class TwoTables(FakeGraphics):
    """The NES way: two tables side by side, each a console map wide, repeated. Table p holds the latest stretch of the
    level whose number has that parity; the screen starts in one and runs on into the other."""

    def __init__(self, world, across, base=0):
        self.views = []                         # base: the level column at scroll 0 (a restart redraws a checkpoint there)
        for table in (0, 1):
            turn = (across + SCREEN_W - 1) // (LAYER_W * PX)            # the stretch the right edge of the screen is in
            if turn % 2 != table:
                turn -= 1
            tiles = {(x, y): world(base + turn * LAYER_W + x, y) for y in range(LAYER_H) for x in range(LAYER_W)}
            layer = FakeLayer(tiles)
            layer.name = f'nametable {table}'
            rows = [bytes(tiles[(x // PX, y // PX)] % 250 for x in range(LAYER_W * PX)) for y in range(LAYER_H * PX)]
            self.views.append(SimpleNamespace(layer=layer, px=PX, rows=rows, lines=[(across % (LAYER_W * PX), 0)] * SCREEN_H,
                                              match=1.0, source='picture'))
        self.screen = [bytes(world(base + (across + x) // PX, y // PX) % 250 for x in range(SCREEN_W)) for y in range(SCREEN_H)]

    def layers(self):
        return self.views


def repeating(column, row):
    """A level that looks the same every 32 columns, but for one post at column 70."""
    if column == 70 and 8 <= row < 12:
        return 240
    return 1 if row < 6 else 10 + (column % 32 * 7 + row * 13) % 200


def level(column, row):
    """A level 400 cells wide: every cell differs from its neighbours, with a wide strip of plain sky on top."""
    return 1 if row < 6 else 10 + (column * column * 7 + row * 13 + column * row) % 200


def other_room(column, row):
    return 1 if row < 6 else 10 + (column * column * 11 + row * 5 + 3) % 200


def frames_for(steps):
    return [lm.Frame(f'scene{number}', FakeGraphics(world, across, down), number * 12)
            for number, (world, across, down) in enumerate(steps)]


class StitchTests(unittest.TestCase):
    def test_scrolling_past_the_width_of_the_console_map_gives_one_long_map(self):
        frames = frames_for([(level, across, 0) for across in range(0, 900, 60)])
        planes = lm.stitch(frames, 'gb')
        self.assertEqual(len(planes), 1)
        plane = planes[0]
        self.assertEqual(len(plane.sections), 1)
        left, top, right, bottom = plane.bounds()
        self.assertEqual((left, top), (0, 0))
        self.assertEqual(right, (840 + SCREEN_W) // PX)                 # the last capture's right edge, in whole cells
        for (column, row), spot in plane.cells.items():                 # every place shows the level's own cell
            shown = frames[spot.frame].graphics.layer.cell(spot.x, spot.y).tile_address
            self.assertEqual(shown, level(column, row), (column, row))
        self.assertEqual(plane.spot(0, 0).frame, frames.index(frames[0]))

    def test_only_the_captures_the_map_needs_are_kept(self):
        frames = frames_for([(level, across, 0) for across in range(0, 600, 20)])
        plane = lm.stitch(frames, 'gb')[0]
        everything = set(plane.cells)
        keep = plane.cover()
        self.assertLess(len(keep), len(frames) // 2)
        plane.assign(keep)
        self.assertEqual(set(plane.cells), everything)

    def test_a_new_room_starts_a_new_section_and_coming_back_returns_to_the_first(self):
        steps = [(level, across, 0) for across in range(0, 200, 40)]
        steps += [(other_room, across, 0) for across in range(0, 120, 40)]          # a door: the scroll starts again at 0
        steps += [(level, 40, 0)]                                                   # and back to a place seen before
        frames = frames_for(steps)
        plane = lm.stitch(frames, 'gb')[0]
        self.assertEqual(len(plane.sections), 2)
        sections = [plane.windows[number].section for number in sorted(plane.windows)]
        self.assertEqual(sections[:5], [0] * 5)
        self.assertEqual(sections[5:8], [1] * 3)
        self.assertEqual(sections[8], 0)
        self.assertEqual(plane.windows[8].across, plane.windows[1].across)          # the same place as the second capture
        first, second = plane.sections
        self.assertGreaterEqual(second[0], first[1] + lm.GAP)                       # the rooms do not overlap on the map

    def test_a_restart_in_a_level_with_a_lot_of_sky_goes_back_to_the_start(self):
        steps = [(level, across, 0) for across in range(0, 520, 40)] + [(level, 0, 0), (level, 40, 0)]
        plane = lm.stitch(frames_for(steps), 'gb')[0]
        self.assertEqual(len(plane.sections), 1)
        self.assertEqual(plane.windows[13].across, 0)
        self.assertEqual(plane.windows[14].across, 40)

    def test_screens_between_levels_are_left_out_when_a_level_scrolled(self):
        steps = [(other_room, 0, 0)] + [(level, across, 0) for across in range(0, 400, 40)]      # a title screen, then a level
        plane = lm.stitch(frames_for(steps), 'gb')[0]
        self.assertEqual(len(plane.sections), 1)
        self.assertNotIn(0, plane.windows)
        rooms = lm.stitch(frames_for([(level, 0, 0), (other_room, 0, 0)]), 'gb')[0]             # nothing scrolled: both rooms stay
        self.assertEqual(len(rooms.sections), 2)

    def test_a_blank_screen_places_nothing(self):
        steps = [(level, 0, 0), (lambda column, row: 1, 0, 0), (level, 40, 0)]
        plane = lm.stitch(frames_for(steps), 'gb')[0]
        self.assertEqual(sorted(plane.windows), [0, 2])

    def test_picture_and_changed_places(self):
        frames = frames_for([(level, across, 0) for across in range(0, 200, 40)])
        plane = lm.stitch(frames, 'gb')[0]
        picture = plane.picture(frames)
        width, height = plane.size()
        self.assertEqual(picture.size, (width * PX, height * PX))
        self.assertEqual(picture.getpixel((3, 60)), (level(0, 7) % 250,) * 3)
        frame = plane.spot(4, 10).frame
        window = plane.windows[frame]
        before = bytes(v for line in frames[frame].graphics.screen for value in line for v in (value, value, value))
        after = bytearray(before)
        x, y = 4 * PX - window.across + 2, 10 * PX - window.down + 2                  # one pixel of that place on the screen
        after[(y * SCREEN_W + x) * 3] = 255
        places = plane.changed(picture, {frame: (SCREEN_W, SCREEN_H, before, bytes(after))})
        self.assertEqual(places, [(4, 10)])
        self.assertEqual(picture.getpixel((4 * PX + 2, 10 * PX + 2))[0], 255)

    def test_two_tables_that_hold_the_same_picture_are_told_apart_over_the_whole_stretch(self):
        frames = [lm.Frame(f'scene{number}', TwoTables(repeating, across), number * 12) for number, across in enumerate(range(0, 720, 24))]
        plane = lm.stitch(frames, 'nes')[0]
        self.assertEqual(plane.name, 'Background')
        self.assertEqual(len(plane.sections), 1)
        wrong = [(place, spot.layer) for place, spot in plane.cells.items() if spot.layer != place[0] // LAYER_W % 2]
        self.assertEqual(wrong, [])                                   # every place comes from the table that holds it
        self.assertEqual((plane.cells[(70, 9)].x, plane.cells[(70, 9)].y), (70 % LAYER_W, 9))

    def test_after_a_restart_the_tables_are_read_where_the_screen_shows_them(self):
        # Scroll on, then the game restarts at a checkpoint 20 columns in and redraws it from scroll 0. The capture is
        # moved 20 columns to line up; from then on a map place and the table place it shows differ by 20 columns.
        # Reading the tables at the map place's own number left holes and broke the map in two (Adventure Island).
        steps = [(across, 0) for across in range(0, 480, 24)] + [(across, 20) for across in range(0, 240, 24)]
        frames = [lm.Frame(f'scene{number}', TwoTables(level, across, base), number * 12) for number, (across, base) in enumerate(steps)]
        plane = lm.stitch(frames, 'nes')[0]
        self.assertEqual(len(plane.sections), 1)
        after = [plane.windows[number] for number in range(20, len(steps))]
        self.assertTrue(all(len(window.cells) >= LAYER_W * 27 for window in after), [len(window.cells) for window in after])
        for window in after:
            for (column, row), spot in window.cells.items():
                self.assertEqual(spot.layer, (column - 20) // LAYER_W % 2)       # the table that holds it since the restart
                self.assertEqual(spot.x, (column - 20) % LAYER_W)

    def test_captures_taken_during_a_fade_are_left_out(self):
        frames = frames_for([(level, across, 0) for across in range(0, 400, 40)])
        dim = frames[5].graphics                                   # the screen fades: same pictures, darker colors
        dim.reps = [(v * 6 // 10,) * 3 for v in range(250)]
        dark = frames[7].graphics                                  # nearly black: the fade into a stage
        dark.reps = [(v // 5,) * 3 for v in range(250)]
        plane = lm.stitch(frames, 'gb')[0]
        self.assertNotIn(5, plane.windows)
        self.assertNotIn(7, plane.windows)
        self.assertEqual(len(plane.sections), 1)
        self.assertTrue(all(spot.frame not in (5, 7) for spot in plane.cells.values()))

    def test_a_level_that_is_dark_all_through_is_kept(self):
        frames = frames_for([(level, across, 0) for across in range(0, 400, 40)])
        for frame in frames:
            frame.graphics.reps = [(v // 5,) * 3 for v in range(250)]
        plane = lm.stitch(frames, 'gb')[0]
        self.assertEqual(len(plane.windows), len(frames))

    def test_a_capture_scrolled_like_the_status_bar_takes_the_usual_split(self):
        # Most captures show the level from line 38 (a bar above it); one was scrolled like the bar, so its band
        # starts at line 0 and the bar's last row (screen row 4) would pass for level.
        plane = lm.Plane('Background', PX)
        def cells(rows):
            return {(column, row): lm.Spot(0, 0, column, row) for column in range(32) for row in rows}
        plane.windows = {0: lm.Window(0, 0, 0, 38, 224, cells(range(5, 28))),
                         1: lm.Window(0, 0, 0, 38, 224, cells(range(5, 28))),
                         2: lm.Window(0, 0, 0, 0, 224, cells(range(4, 28)))}
        plane.same_split()
        self.assertEqual(min(row for _, row in plane.windows[2].cells), 5)
        self.assertEqual(plane.windows[2].first, 38)
        plain = lm.Plane('Background', PX)                       # no bar: nothing changes
        plain.windows = {0: lm.Window(0, 0, 0, 0, 224, cells(range(0, 28)))}
        plain.same_split()
        self.assertEqual(min(row for _, row in plain.windows[0].cells), 0)

    def test_a_small_hole_closed_in_by_the_map_is_filled_from_the_layer(self):
        seen = {(column, row): lm.Spot(0, 0, column, row) for column in range(10) for row in range(6)}
        hole = {(4, 2), (5, 2), (5, 3)}                            # a sprite stood there in every capture
        edge = {(9, 5)}                                            # on the edge of what was seen: not a hole
        for place in hole | edge:
            del seen[place]
        plane = lm.Plane('Background', PX)
        plane.windows = {0: lm.Window(0, 0, 0, 0, 224, seen, {}, {place: lm.Spot(0, 0, *place) for place in hole | edge | {(10, 5)}})}
        plane.assign()
        self.assertTrue(hole <= set(plane.cells))
        self.assertNotIn((9, 5), plane.cells)
        self.assertNotIn((10, 5), plane.cells)

    def test_a_status_bar_that_stays_put_is_left_off_the_map(self):
        frames = frames_for([(level, across, 0) for across in range(0, 400, 40)])
        for frame in frames:                      # the top two rows of the screen always show the same words
            graphics = frame.graphics
            graphics.screen = [bytes((x // PX * 3 + y // PX) % 200 + 20 for x in range(SCREEN_W)) if y < 2 * PX else line
                               for y, line in enumerate(graphics.screen)]
        plane = lm.stitch(frames, 'gb')[0]
        self.assertEqual(min(row for _, row in plane.cells), 2)
        self.assertEqual(max(row for _, row in plane.cells), SCREEN_H // PX - 1)

    def test_places_no_capture_showed_are_drawn_as_not_seen(self):
        frames = frames_for([(level, 0, 0), (other_room, 0, 0)])
        plane = lm.stitch(frames, 'gb')[0]
        picture = plane.picture(frames)
        gap = plane.sections[0][1] * PX + 3
        self.assertEqual(picture.getpixel((gap, 4)), lm.HATCH)          # fine diagonal lines
        self.assertEqual(picture.getpixel((gap, 5)), lm.EMPTY)

    def test_the_nes_keeps_one_background_in_several_nametables(self):
        self.assertEqual(lm.plane_key('nes', 'nametable 0'), lm.plane_key('nes', 'nametable 1'))
        self.assertNotEqual(lm.plane_key('genesis', 'plane A'), lm.plane_key('genesis', 'plane B'))


if __name__ == '__main__':
    unittest.main()
