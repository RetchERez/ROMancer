import unittest,hashlib,tempfile
from pathlib import Path
from romancer.resource_compression import decode_stream,encode_stream,inspect_compressed
from romancer.compression_oracle import verify_encoded

class LZ2Tests(unittest.TestCase):
    def test_all_five_commands_long_headers_and_overlap_follow_literal_vectors(self):
        examples=[('02414243ff',b'ABC'),('2441ff',b'A'*5),('444142ff',b'ABABA'),('63feff',bytes([254,255,0,1])),('02414243850000ff',b'ABCABCABC'),('e4205aff',b'Z'*33)]
        for hexdata,want in examples:
            with self.subTest(data=hexdata):
                encoded=bytes.fromhex(hexdata);r=decode_stream(encoded+b'padding','snes-lz2')
                self.assertEqual(r['data'],want);self.assertEqual(r['consumed'],len(encoded))
                self.assertTrue(verify_encoded(encoded,'snes-lz2',want)['verified'])
    def test_references_are_big_endian_not_host_endian(self):
        encoded=b'\xe0\xff'+bytes(range(256))+b'\x02XYZ\x82\x01\x00\xff'
        self.assertEqual(decode_stream(encoded,'snes-lz2')['data'],bytes(range(256))+b'XYZXYZ')
    def test_broken_tokens_invalid_commands_empty_and_output_bombs_are_refused(self):
        for data in (b'',b'\xff',b'\x03AB',b'\x20',b'\x40A',b'\x60',b'\x80\x00\x00\xff',b'\xa0\xff',b'\xc0\xff',b'\xfc\x00\xff',b'\xe0'):
            with self.subTest(data=data),self.assertRaises(ValueError):decode_stream(data,'snes-lz2')
        with self.assertRaises(ValueError):decode_stream(bytes.fromhex('e7ff41ff'),'snes-lz2',512)
    def test_original_encoder_is_deterministic_bounded_and_independently_verified(self):
        values=[b'ABCDE',b'A'*5000,b'AB'*2000,bytes(range(256))*40,bytes((i*39+i//31)&255 for i in range(16384))]
        for raw in values:
            packed=encode_stream(raw,'snes-lz2');self.assertEqual(encode_stream(raw,'snes-lz2'),packed)
            self.assertEqual(decode_stream(packed,'snes-lz2')['data'],raw)
            self.assertTrue(verify_encoded(packed,'snes-lz2',raw)['verified'])
            with self.assertRaises(ValueError):verify_encoded(packed+b'\x00','snes-lz2',raw)
        self.assertLess(len(encode_stream(b'AB'*2000,'snes-lz2')),64)
    def test_explicit_allocation_inspection_accepts_snes_stream_without_gba_header(self):
        raw=bytes.fromhex('2441ff')+b'\xff'*13
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'stream.bin';p.write_bytes(raw);r=inspect_compressed(p,hashlib.sha256(raw).hexdigest(),0,16,'snes-lz2')
            self.assertEqual(r['decoded_size'],5);self.assertEqual(r['consumed'],3)
    def test_cancellation_is_observed_before_large_lz2_decode(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('romancer.snes_lz2'))
        from romancer.snes_lz2 import decode_lz2
        with self.assertRaises(KeyboardInterrupt):decode_lz2(bytes.fromhex('2441ff'),cancelled=lambda:True)
    def test_three_byte_allocation_is_valid_for_lz2(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'stream.bin';raw=bytes.fromhex('2441ff');p.write_bytes(raw)
            self.assertEqual(inspect_compressed(p,hashlib.sha256(raw).hexdigest(),0,3,'snes-lz2')['decoded_size'],5)
