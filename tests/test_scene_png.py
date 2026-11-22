import io
import unittest
from types import SimpleNamespace

from romancer import scene_png as sp

FMT = 'genesis-4bpp'


def tile(address, pixels, line=0, pending=None, kind='bg'):
    text = ''.join(f'{p:x}' for p in pixels)
    row = {'id': f'vram:{address}:{FMT}', 'name': f'Picture {address // 32}', 'domain': 'vram', 'address': address, 'format': FMT,
           'bits': 4, 'pixels': text, 'pal': [0, 16, 16], 'line': line, 'kind': kind, 'pending': None}
    if pending is not None:
        row['pending'] = {'pixels': ''.join(f'{p:x}' for p in pending), 'change': 'x'}
    return row


class FakeGraphics:
    """Two palette lines of 16 colors; a 3 x 2 layer that shows picture A three times (once flipped), B twice, C once."""

    def __init__(self):
        self.colors = [[i * 8, 255 - i * 8, (i * 37) % 256] for i in range(32)]
        self.colors[17] = list(self.colors[18])              # line 1 holds one color in two slots
        a = [(x + y) % 4 for y in range(8) for x in range(8)]
        b = [x % 16 for y in range(8) for x in range(8)]
        c = [(x * y) % 3 for y in range(8) for x in range(8)]
        self.tiles = [tile(0, a), tile(32, b, line=1), tile(64, c)]
        cells = [(0, 0, False, False), (32, 1, False, False), (0, 0, True, False),
                 (64, 0, False, True), (32, 1, False, False), (0, 0, False, False)]
        self.layer = SimpleNamespace(width=3, height=2, tile_format=FMT, tile_domain='vram', name='plane A',
                                     cells=[SimpleNamespace(tile_address=a, palette=p, hflip=h, vflip=v, x=k % 3, y=k // 3)
                                            for k, (a, p, h, v) in enumerate(cells)])
        self.system = 'genesis'
        self.view = {'tiles': self.tiles, 'layers': [{'index': 0, 'flips': True, 'lines': 2, 'pending': []}]}

    def layers(self):
        return [SimpleNamespace(layer=self.layer, px=8, rule=(0, 16, 16))]

    def _subtile(self, view, cell, qx, qy):
        return cell.tile_address

    def tile_pixels(self, domain, address, fmt):
        return None


def edit(png, changes, mode=None):
    """Set pixels {(x, y): palette number or RGB} in a PNG and return it, optionally converted to another mode first."""
    from PIL import Image
    image = Image.open(io.BytesIO(png))
    if mode:
        image = image.convert(mode)
    for (x, y), value in changes.items():
        image.putpixel((x, y), value)
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


class ScenePngTests(unittest.TestCase):
    def setUp(self):
        self.g = FakeGraphics()

    def test_the_sheet_is_a_palette_png_with_the_scenes_colors_and_reads_back_unchanged(self):
        from PIL import Image
        out = sp.export_sheet(self.g, self.g.view)
        self.assertEqual((out['width'], out['height'], out['pictures'], out['indexed'], out['colors']), (128, 8, 3, True, 32))
        image = Image.open(io.BytesIO(out['png']))
        self.assertEqual(image.mode, 'P')
        self.assertEqual([tuple(image.getpalette()[i * 3:i * 3 + 3]) for i in range(32)], [tuple(c) for c in self.g.colors])
        self.assertEqual(image.getpixel((8 + 5, 0)), 16 + 5, 'a pixel is the palette number of its color: line 1, color 5')
        for mode in (None, 'RGB', 'RGBA'):
            wanted, report = sp.read_sheet(self.g, self.g.view, edit(out['png'], {}, mode))
            self.assertEqual((wanted, report.off, report.clear), ({}, {}, 0), mode)
            self.assertEqual(report.by_number, mode is None)

    def test_a_drawn_pixel_is_taken_by_number_or_by_color_within_the_pictures_own_line(self):
        out = sp.export_sheet(self.g, self.g.view)
        # by palette number: picture B (line 1), pixel (0, 0) from color 0 to color 9
        wanted, report = sp.read_sheet(self.g, self.g.view, edit(out['png'], {(8, 0): 16 + 9}))
        self.assertEqual(list(wanted), ['vram:32:' + FMT])
        self.assertEqual(wanted['vram:32:' + FMT][0], 9)
        self.assertEqual(report.off, {})
        # by color: the same edit in a plain RGB file
        wanted, report = sp.read_sheet(self.g, self.g.view, edit(out['png'], {(8, 0): tuple(self.g.colors[16 + 9])}, 'RGB'))
        self.assertEqual(wanted['vram:32:' + FMT][0], 9)
        self.assertEqual(report.off, {})
        # a color of the other palette line is not this picture's color: nearest of its own line, and reported
        foreign = tuple(self.g.colors[3])
        wanted, report = sp.read_sheet(self.g, self.g.view, edit(out['png'], {(8, 0): foreign}, 'RGB'))
        self.assertEqual(len(report.off), 1)
        (source, target), pixels = next(iter(report.off.items()))
        self.assertEqual((source, pixels), (foreign, 1))
        self.assertIn(list(target), self.g.colors[16:32])
        self.assertEqual(report.rows()[0]['from'], '#%02X%02X%02X' % foreign)
        # a palette number of the other line is handled the same way
        wanted, report = sp.read_sheet(self.g, self.g.view, edit(out['png'], {(8, 0): 3}))
        self.assertEqual(len(report.off), 1)
        # see-through becomes color 0 and is counted
        wanted, report = sp.read_sheet(self.g, self.g.view, edit(out['png'], {(8 + 3, 0): (0, 0, 0, 0)}, 'RGBA'))
        self.assertEqual((report.clear, wanted['vram:32:' + FMT][3]), (1, 0))

    def test_two_slots_with_one_color_do_not_turn_an_untouched_pixel_into_a_change(self):
        # picture B uses colors 1 and 2 of line 1, which are the same color: read back by color it must stay as it is
        out = sp.export_sheet(self.g, self.g.view)
        wanted, report = sp.read_sheet(self.g, self.g.view, edit(out['png'], {}, 'RGB'))
        self.assertEqual(wanted, {})

    def test_wrong_size_and_not_a_png_are_refused_plainly(self):
        from PIL import Image
        out = io.BytesIO()
        Image.new('RGB', (64, 8)).save(out, format='PNG')
        with self.assertRaisesRegex(ValueError, '64 x 8 pixels.*128 x 8'):
            sp.read_sheet(self.g, self.g.view, out.getvalue())
        with self.assertRaisesRegex(ValueError, 'not a PNG'):
            sp.read_sheet(self.g, self.g.view, b'hello')
        with self.assertRaisesRegex(ValueError, 'larger than'):
            sp.read_sheet(self.g, self.g.view, bytes(sp.MAX_PNG + 1))

    def test_a_layer_is_saved_as_laid_out_with_flips_and_a_change_goes_back_to_the_picture(self):
        from PIL import Image
        out = sp.export_layer(self.g, self.g.view, 0)
        self.assertEqual((out['width'], out['height'], out['pictures']), (24, 16, 3))
        image = Image.open(io.BytesIO(out['png']))
        a = [(x + y) % 4 for y in range(8) for x in range(8)]
        self.assertEqual([image.getpixel((x, 0)) for x in range(8)], a[:8])
        self.assertEqual([image.getpixel((16 + x, 0)) for x in range(8)], a[:8][::-1], 'the third cell shows picture A flipped sideways')
        self.assertEqual(image.getpixel((0, 8 + 7)), [(x * y) % 3 for y in range(8) for x in range(8)][0], 'upside down: last row is the first')
        wanted, report, moves = sp.read_layer(self.g, self.g.view, 0, out['png'])
        self.assertEqual((wanted, report.conflicts), ({}, 0))
        self.assertEqual(moves, [])
        self.assertEqual(report.covered, {t['id'] for t in self.g.tiles})
        # draw on the flipped cell only: pixel (0, 0) of that cell is pixel (7, 0) of picture A
        wanted, report, moves = sp.read_layer(self.g, self.g.view, 0, edit(out['png'], {(16, 0): 9}))
        self.assertEqual(list(wanted), ['vram:0:' + FMT])
        self.assertEqual(wanted['vram:0:' + FMT][7], 9)
        self.assertEqual(report.conflicts, 0, 'one place drawn and the others left alone is not a disagreement')
        # two places drawn differently: the version drawn most often wins and the other place is counted
        both = edit(out['png'], {(0, 0): 9, (16 + 7, 0): 9, (16, 8): 5})        # cells 0 and 2 agree (pixel 0 = 9); cell 5 differs
        wanted, report, moves = sp.read_layer(self.g, self.g.view, 0, both)
        self.assertEqual(wanted['vram:0:' + FMT][0], 9)
        self.assertEqual((report.conflicts, report.conflict_cells), (1, 1))
        self.assertIn('drew differently', sp.summary(report, 1, []))

    def test_a_cell_given_a_picture_the_scene_already_has_is_a_background_change_not_a_redraw(self):
        from PIL import Image
        out = sp.export_layer(self.g, self.g.view, 0)
        image = Image.open(io.BytesIO(out['png']))

        def paste(source, target, turn=None):
            square = image.crop((source[0] * 8, source[1] * 8, source[0] * 8 + 8, source[1] * 8 + 8))
            if turn is not None:
                square = square.transpose(turn)
            image.paste(square, (target[0] * 8, target[1] * 8))
        paste((1, 0), (2, 1))                                   # picture B (palette line 1) copied over the last cell
        paste((0, 0), (1, 1), Image.FLIP_TOP_BOTTOM)            # picture A, upside down, over the second cell of row 2
        raw = io.BytesIO()
        image.save(raw, format='PNG')
        wanted, report, moves = sp.read_layer(self.g, self.g.view, 0, raw.getvalue())
        self.assertEqual(wanted, {}, 'no picture was drawn on')
        self.assertEqual(report.moved, 2)
        self.assertEqual(report.off, {})
        self.assertEqual(sorted(moves, key=lambda m: m['x']), [
            {'layer': 0, 'x': 1, 'y': 1, 'tile': 'vram:0:' + FMT, 'hflip': False, 'vflip': True, 'line': 0},
            {'layer': 0, 'x': 2, 'y': 1, 'tile': 'vram:32:' + FMT, 'hflip': False, 'vflip': False, 'line': 1}])
        # a moved cell and a drawn pixel in one PNG: both are found, each as what it is
        image.putpixel((0, 0), 9)
        raw = io.BytesIO()
        image.save(raw, format='PNG')
        wanted, report, moves = sp.read_layer(self.g, self.g.view, 0, raw.getvalue())
        self.assertEqual(len(moves), 2)
        self.assertEqual(list(wanted), ['vram:0:' + FMT])
        # once the moves are kept, the saved PNG shows them and loading it again finds nothing to do
        self.g.view['layers'][0]['pending'] = [dict(move, change='c1') for move in moves]
        again = sp.export_layer(self.g, self.g.view, 0)
        shown = Image.open(io.BytesIO(again['png']))
        self.assertEqual(shown.crop((16, 8, 24, 16)).tobytes(), shown.crop((8, 0, 16, 8)).tobytes())
        wanted, report, moves = sp.read_layer(self.g, self.g.view, 0, again['png'])
        self.assertEqual((wanted, moves), ({}, []))

    def test_what_you_kept_shows_in_the_next_png_and_drawing_it_back_takes_it_out_again(self):
        changed = [9] + [(x + y) % 4 for y in range(8) for x in range(8)][1:]
        self.g.tiles[0] = tile(0, [(x + y) % 4 for y in range(8) for x in range(8)], pending=changed)
        self.g.view = {'tiles': self.g.tiles}
        out = sp.export_sheet(self.g, self.g.view)
        from PIL import Image
        self.assertEqual(Image.open(io.BytesIO(out['png'])).getpixel((0, 0)), 9)
        wanted, _ = sp.read_sheet(self.g, self.g.view, out['png'])
        self.assertEqual(wanted, {'vram:0:' + FMT: changed}, 'the whole wanted state is stated again')
        wanted, _ = sp.read_sheet(self.g, self.g.view, edit(out['png'], {(0, 0): 0}))
        self.assertEqual(wanted, {})

    def test_summary_is_plain_about_colors_and_pictures_left_out(self):
        report = sp.Report()
        self.assertIn('nothing to change', sp.summary(report, 0, []))
        report.color((1, 2, 3), (4, 5, 6))
        report.color((1, 2, 3), (4, 5, 6))
        text = sp.summary(report, 2, [{'tile': 'x', 'reason': 'locked'}])
        self.assertIn('2 pictures changed', text)
        self.assertIn('1 color in it is not in the palette line', text)
        self.assertIn('2 pixels were changed to the nearest color', text)
        self.assertIn('1 picture you changed cannot be changed and was left out', text)


class SpriteObjectTests(unittest.TestCase):
    """Two sprites side by side make one object (the right one mirrored); a third stands alone."""

    def setUp(self):
        self.g = FakeGraphics()
        self.g.width, self.g.height = 256, 224
        def sprite(x, y, address, hflip=False, line=0):
            return SimpleNamespace(x=x, y=y, cols=1, rows=1, tiles=[address], hflip=hflip, vflip=False, line=line,
                                   domain='vram', fmt=FMT, guess=False)
        self.g.sprites = lambda: [sprite(10, 20, 0), sprite(18, 20, 64, hflip=True), sprite(100, 50, 32, line=1),
                                  sprite(300, 50, 32), sprite(40, 90, 4096)]      # off screen; a picture the scene does not list

    def test_touching_sprites_are_one_object_and_the_png_reads_back_unchanged(self):
        objects, _ = sp.sprite_objects(self.g, self.g.view)
        self.assertEqual([(o['left'], o['top'], o['width'], o['height'], len(o['sprites'])) for o in objects],
                         [(10, 20, 16, 8, 2), (100, 50, 8, 8, 1)])
        out = sp.export_sprites(self.g, self.g.view)
        self.assertEqual((out['width'], out['height'], out['objects'], out['pictures']), (48, 24, 2, 3))
        wanted, report = sp.read_sprites(self.g, self.g.view, out['png'])
        self.assertEqual(wanted, {})
        self.assertEqual(len(report.covered), 3)

    def test_a_pixel_drawn_on_an_object_goes_to_the_sprite_that_shows_it_with_its_flip(self):
        out = sp.export_sprites(self.g, self.g.view)
        # the first pixel of the right half of the first object is the last pixel of the first row of the mirrored picture
        wanted, _ = sp.read_sprites(self.g, self.g.view, edit(out['png'], {(16, 8): 5, (2, 2): 0}))
        c = [(x * y) % 3 for y in range(8) for x in range(8)]
        c[7] = 5
        self.assertEqual(wanted, {'vram:64:' + FMT: c}, 'the gap between objects belongs to no picture')

    def test_no_sprites_is_said_plainly(self):
        self.g.sprites = lambda: []
        with self.assertRaises(ValueError):
            sp.export_sprites(self.g, self.g.view)


class ChecksumFieldTests(unittest.TestCase):
    def test_both_bytes_of_a_checksum_count_when_a_probe_moved_one(self):
        from romancer import scene_graphics as sg
        self.assertEqual(sg.whole_checksums({0x14F}, 'gb'), {0x14E, 0x14F})
        self.assertEqual(sg.whole_checksums({0x14E}, 'gbc'), {0x14E, 0x14F})
        self.assertEqual(sg.whole_checksums({0x7FFB}, 'sms'), {0x7FFA, 0x7FFB})
        self.assertEqual(sg.whole_checksums({0x18F, 0x1A4}, 'genesis'), {0x18E, 0x18F, 0x1A4, 0x1A5})
        self.assertEqual(sg.whole_checksums({0x7FDE}, 'snes'), {0x7FDC, 0x7FDD, 0x7FDE, 0x7FDF})
        self.assertEqual(sg.whole_checksums(set(), 'nes'), set())


if __name__ == '__main__':
    unittest.main()
