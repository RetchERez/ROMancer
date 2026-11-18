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
                                     cells=[SimpleNamespace(tile_address=a, palette=p, hflip=h, vflip=v) for a, p, h, v in cells])
        self.view = {'tiles': self.tiles}

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
        wanted, report = sp.read_layer(self.g, self.g.view, 0, out['png'])
        self.assertEqual((wanted, report.conflicts), ({}, 0))
        self.assertEqual(report.covered, {t['id'] for t in self.g.tiles})
        # draw on the flipped cell only: pixel (0, 0) of that cell is pixel (7, 0) of picture A
        wanted, report = sp.read_layer(self.g, self.g.view, 0, edit(out['png'], {(16, 0): 9}))
        self.assertEqual(list(wanted), ['vram:0:' + FMT])
        self.assertEqual(wanted['vram:0:' + FMT][7], 9)
        self.assertEqual(report.conflicts, 0, 'one place drawn and the others left alone is not a disagreement')
        # two places drawn differently: the version drawn most often wins and the other place is counted
        both = edit(out['png'], {(0, 0): 9, (16 + 7, 0): 9, (16, 8): 5})        # cells 0 and 2 agree (pixel 0 = 9); cell 5 differs
        wanted, report = sp.read_layer(self.g, self.g.view, 0, both)
        self.assertEqual(wanted['vram:0:' + FMT][0], 9)
        self.assertEqual((report.conflicts, report.conflict_cells), (1, 1))
        self.assertIn('drew differently', sp.summary(report, 1, []))

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


if __name__ == '__main__':
    unittest.main()
