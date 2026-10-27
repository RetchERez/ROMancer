import importlib
import unittest


class CodecTests(unittest.TestCase):
    def functions(self):
        try:
            module = importlib.import_module('romancer.asset_codecs')
        except ModuleNotFoundError:
            module = None
        self.assertIsNotNone(module, 'literal asset codecs are missing')
        return module.decode_cell, module.encode_cell

    def test_literal_vectors_have_independently_known_pixels(self):
        decode, encode = self.functions()
        cases = [
            ('tile8-rowplanar4-msb-v1', bytes.fromhex('80402010'+'00'*28), [1,2,4,8]+[0]*60),
            ('tile8-planar2-msb-v1', bytes.fromhex('80000000000000000000000000000001'), [1] + [0]*62 + [2]),
            ('tile8-packed4-high-v1', bytes.fromhex('12' + '00'*30 + 'ef'), [1,2] + [0]*60 + [14,15]),
            ('tile8-paired4-msb-v1', bytes.fromhex('8040' + '00'*14 + '2010' + '00'*14), [1,2,4,8] + [0]*60),
            ('mono-row-msb-v1', bytes.fromhex('8142241818244281'),
             [1,0,0,0,0,0,0,1, 0,1,0,0,0,0,1,0, 0,0,1,0,0,1,0,0, 0,0,0,1,1,0,0,0,
              0,0,0,1,1,0,0,0, 0,0,1,0,0,1,0,0, 0,1,0,0,0,0,1,0, 1,0,0,0,0,0,0,1]),
        ]
        for codec, raw, pixels in cases:
            with self.subTest(codec=codec):
                self.assertEqual(decode(raw, codec=codec, width=8, height=8), pixels)
                self.assertEqual(encode(pixels, codec=codec, width=8, height=8), raw)

    def test_mono_width_nine_and_padding_refusal(self):
        decode, encode = self.functions()
        self.assertEqual(decode(b'\x80\x80', codec='mono-row-msb-v1', width=9, height=1), [1]+[0]*7+[1])
        with self.assertRaises(ValueError):
            decode(b'\x80\x81', codec='mono-row-msb-v1', width=9, height=1)
        with self.assertRaises(ValueError):
            encode([True]*9, codec='mono-row-msb-v1', width=9, height=1)

    def test_exact_lengths_indices_dimensions_and_unknown_codec(self):
        decode, encode = self.functions()
        for kwargs, raw in [({'codec':'unknown','width':8,'height':8},b'0'*32),
                            ({'codec':'tile8-packed4-high-v1','width':7,'height':8},b'0'*32),
                            ({'codec':'mono-row-msb-v1','width':0,'height':1},b''),
                            ({'codec':'tile8-planar2-msb-v1','width':8,'height':8},b'0'*15)]:
            with self.assertRaises(ValueError): decode(raw, **kwargs)
        with self.assertRaises(ValueError):
            encode([16]*64, codec='tile8-packed4-high-v1',width=8,height=8)

    def test_every_single_storage_bit_round_trips(self):
        decode, encode = self.functions()
        for codec, size in [('tile8-rowplanar4-msb-v1',32),('tile8-planar2-msb-v1',16),('tile8-paired4-msb-v1',32),('tile8-packed4-high-v1',32)]:
            for bit in range(size*8):
                raw=bytearray(size);raw[bit//8]=1<<(bit%8)
                pixels=decode(bytes(raw),codec=codec,width=8,height=8)
                self.assertEqual(encode(pixels,codec=codec,width=8,height=8),bytes(raw))
