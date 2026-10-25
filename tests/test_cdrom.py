import importlib.util
import hashlib
import json
from pathlib import Path
import unittest


def subject():
    from romancer import cdrom
    return cdrom


def sector(seed=0, frame=0):
    header = b'\x00' + b'\xff' * 10 + b'\x00\x00\x02' + bytes([frame, 1])
    payload = bytes((i * 17 + seed) % 256 for i in range(2048))
    return subject().repair_mode1(header + payload + bytes(288))


class SectorTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.cdrom'),
                             'sector-safe mapping and integrity module missing')

    def test_cross_sector_mapping_skips_integrity_and_header(self):
        spans = subject().payload_spans(1, 2047, 2)
        self.assertEqual([s['raw_offset'] for s in spans], [4415, 4720])
        self.assertEqual([s['length'] for s in spans], [1, 1])
        self.assertEqual([s['data_offset'] for s in spans], [0, 1])

    def test_three_sector_span(self):
        spans = subject().payload_spans(0, 2040, 2060)
        self.assertEqual([s['length'] for s in spans], [8, 2048, 4])
        self.assertEqual([s['sector'] for s in spans], [0, 1, 2])

    def test_zero_and_negative_spans_rejected(self):
        for args in [(0, 0, 0), (-1, 0, 1), (0, -1, 1), (0, 0, -1), (True, 0, 1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                subject().payload_spans(*args)

    def test_generated_integrity_and_payload_preservation(self):
        raw = sector(7)
        self.assertIsNone(subject().validate_mode1(raw))
        self.assertEqual(raw[16:2064], bytes((i * 17 + 7) % 256 for i in range(2048)))
        self.assertEqual(raw, subject().repair_mode1(raw))
        self.assertEqual(len(raw), 2352)

    def test_each_corrupted_region_is_rejected(self):
        good = sector(3)
        for offset in [0, 10, 15, 16, 2063, 2064, 2068, 2076, 2248, 2351]:
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                bad = bytearray(good)
                bad[offset] ^= 1
                subject().validate_mode1(bad)

    def test_invalid_header_cannot_be_repaired(self):
        for offset, value in [(12, 0xAA), (13, 0x60), (14, 0x75), (15, 2)]:
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                bad = bytearray(sector())
                bad[offset] = value
                subject().repair_mode1(bad)

    def test_wrong_size_rejected(self):
        for size in [0, 2048, 2351, 2353]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                subject().validate_mode1(bytes(size))

    def test_matches_frozen_independently_checked_vectors(self):
        path = Path(__file__).parent / 'fixtures' / 'mode1_vectors.json'
        self.assertTrue(path.exists(), 'independently checked vectors missing')
        vectors = json.loads(path.read_text(encoding='utf-8'))['vectors']
        self.assertEqual(len(vectors), 4)
        for vector in vectors:
            raw = sector(vector['seed'])
            self.assertEqual(raw[2064:].hex(), vector['integrity_hex'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), vector['sector_sha256'])


if __name__ == '__main__':
    unittest.main()
