"""Round trips for every graphics codec, the parameterised families, the layouts, and recognise()."""
import random
import sys
import unittest
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from romancer import gfx_codecs as gc  # noqa: E402
from romancer import gfx_families as gf  # noqa: E402
from romancer import gfx_packers as gp  # noqa: E402


def sample(n, seed=1, tile=0):
    """Bytes with runs, repeats and noise, like tile data. `tile`: make it whole groups of that many bytes."""
    rng = random.Random(seed * 7919 + n)
    out = bytearray()
    while len(out) < n:
        r = rng.random()
        if r < .3:
            out += bytes([rng.choice((0, 0xFF, rng.randrange(256)))]) * rng.randrange(1, 40)
        elif r < .6 and len(out) > 8:
            a = rng.randrange(len(out))
            out += out[a:a + rng.randrange(2, 60)]
        else:
            out += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 20)))
    del out[n:]
    if tile:
        del out[len(out) - len(out) % tile:]
    return bytes(out)


SIZES = (1, 2, 3, 31, 32, 64, 640, 4096)
GROUP = {'nemesis': 32, 'enigma': 2, 'comper': 2, 'rle-sega-planes': 4}

FAMILY_MEMBERS = [
    'lz~le16.l1.L5hle.r7de.m3.s',       # Square (Final Fantasy V/VI)-style: 11-bit ring, 5-bit length
    'lz~be16.m1.oku.rfee+20.m3.s',
    'lz~le16c.l1.oku.rfee.m3.n',
    'lz~be16c.m0.L4hbe.b1.m2.n',
    'lz~le16i.l1.L5hle.r7de.m3.n',
    'lz~n.m0.L6hbe.b1.m2.n',
    'lz~n.l0.L3lle.b0.m1.n',
    'lz~n.l1.L4lbe.b1.m3.z',
    'lz~n.m1.L4hle.r0.m2.n',
    'rle~h.r1.l1.f.p1', 'rle~l.r0.l0.z.p4', 'rle~h.r3.l1.n.p1', 'rle~l.r2.l0.e.p2', 'rle~h.r0.l0.z.p1',
    'rle~l.r1.l1.n.p1',
]

FIXED = list(gc.CODECS)     # family members and layouts made on demand are not listed


class Domain:
    """What recognise() needs of a traced domain."""

    def __init__(self, data, tags):
        self.data = bytes(data)
        self.tags = array('I', tags)
        self.pcs = array('I', [0] * len(data))


ROM_TAG = 1 << 28
DERIVED_TAG = 3 << 28


class RoundTrips(unittest.TestCase):
    def check(self, name, raw):
        stream = gc.encode(name, raw)
        entry = gc.CODECS[name]
        if entry['terminated']:
            # whatever follows the stream in the ROM must not matter
            out, used = gc.decode(name, stream + b'\x55\xAA\x00\xFF' * 4, 0, 0x10000)
            self.assertEqual(out, raw, name)
            self.assertEqual(used, len(stream), name)
        else:
            out, used = gc.decode(name, stream, 0, len(raw))
            self.assertEqual(out[:len(raw)], raw, name)

    def test_every_registered_codec(self):
        for name in FIXED:
            for n in SIZES:
                group = GROUP.get(name, 1)
                raw = sample(max(n, group), tile=group)
                with self.subTest(codec=name, size=len(raw)):
                    self.check(name, raw)

    def test_family_members(self):
        for name in FAMILY_MEMBERS:
            planes = gf.rle_parse(name)['planes'] if name.startswith('rle~') else 1
            for n in SIZES:
                raw = sample(max(n, planes), seed=2, tile=planes)
                with self.subTest(codec=name, size=len(raw)):
                    self.check(name, raw)

    def test_grids_parse_and_round_trip(self):
        raw = sample(96, seed=3, tile=4)
        names = list(gf.lz_grid()) + list(gf.rle_grid())
        self.assertGreater(len(names), 500)
        for name in names[::7]:
            with self.subTest(codec=name):
                self.check(name, raw)

    def test_bad_names(self):
        for name in ('lz~nope', 'rle~x.r0.l0.z.p1', 'lz~le16.l1.oku.rfee.m3.n', 'nothing', 'raw|0X', 'raw|13'):
            with self.subTest(name=name):
                with self.assertRaises(KeyError):
                    gc.CODECS[name]

    def test_flat_and_extreme_data(self):
        for name in FIXED + FAMILY_MEMBERS:
            for raw in (bytes(256), b'\xFF' * 256, bytes(range(256)), b'\x00\xFF' * 128, b'\x80' * 64 + b'\x00' * 64):
                with self.subTest(codec=name, first=raw[:2].hex()):
                    self.check(name, raw)

    def test_saxman_is_okumura_behind_a_packed_size(self):
        raw = sample(700, seed=5)
        stream = gc.encode('saxman', raw)
        self.assertEqual(stream[0] | stream[1] << 8, len(stream) - 2)
        self.assertEqual(gc.decode('lzss-00-raw', stream, 2, len(raw))[0], raw)

    def test_saxman_reads_zeros_from_before_the_start(self):
        # flags 0b0: one pair, offset field 0, length 3 + 15 -> eighteen 00 bytes from the empty ring
        stream = bytes((3, 0, 0x00, 0x00, 0x0F))
        self.assertEqual(gc.decode('saxman', stream)[0], bytes(18))

    def test_comper_known_stream(self):
        # description 0110...: a word, then 2 words from 1 word back, then the end marker
        stream = bytes((0x60, 0x00, 0x12, 0x34, 0xFF, 0x01, 0x00, 0x00))
        self.assertEqual(gc.decode('comper', stream), (bytes((0x12, 0x34, 0x12, 0x34, 0x12, 0x34)), 8))

    def test_kosinski_moduled_pads_modules(self):
        raw = sample(0x2345, seed=6)
        stream = gc.encode('kosinski-moduled', raw)
        self.assertEqual(stream[0] << 8 | stream[1], len(raw))
        first, used = gc.decode('kosinski', stream, 2, 0x1000)
        self.assertEqual(first, raw[:0x1000])
        second, _ = gc.decode('kosinski', stream, 2 + (used + 15 & ~15), 0x1000)
        self.assertEqual(second, raw[0x1000:0x2000])

    def test_sega_plane_run_length_known_stream(self):
        # plane 0: run of 3 x 11; plane 1: 3 literals; plane 2: run 2 x 22 + literal 33; plane 3: run 3 x 00
        stream = bytes((3, 0x11, 0, 0x83, 1, 2, 3, 0, 2, 0x22, 0x81, 0x33, 0, 3, 0, 0))
        out, used = gc.decode('rle-sega-planes', stream)
        self.assertEqual(out, bytes((0x11, 1, 0x22, 0, 0x11, 2, 0x22, 0, 0x11, 3, 0x33, 0)))
        self.assertEqual(used, len(stream))

    def test_escape_run_length_known_stream(self):
        # as in Darkwing Duck (Game Boy): escape 05; 00 00 3C 3C, ten 18s, 3C 3C; then the end
        stream = bytes((0x05, 0x00, 0x00, 0x3C, 0x3C, 0x05, 0x0A, 0x18, 0x3C, 0x3C, 0x05, 0x00))
        out, used = gc.decode('rle-escape', stream + b'\x06rest')
        self.assertEqual(out, bytes((0, 0, 0x3C, 0x3C)) + b'\x18' * 10 + bytes((0x3C, 0x3C)))
        self.assertEqual(used, len(stream))
        # every byte value in use: the escape itself has to be written as a run
        every = bytes(range(256)) * 2
        self.assertEqual(gc.decode('rle-escape', gc.encode('rle-escape', every))[0], every)

    def test_framed_lz_may_copy_zeros_from_before_the_start_when_the_original_did(self):
        name = 'lz~le16.l1.L4lle.b0.m3.s'       # Tose (Dragon Warrior III): distance back; before the start reads 00
        raw = bytes(40) + bytes(range(1, 60)) + bytes(30)
        plain = gc.encode(name, raw)
        self.assertNotIn('prestart', gf.lz_features(gf.lz_parse(name), plain))
        # flags 00: a pair first; distance 0x012 back from position 0, length 3 + 15
        zeros = bytes((18, 0, 0x00, 0x2F, 0x01))
        self.assertEqual(gc.decode(name, zeros)[0], bytes(18))
        self.assertEqual(gf.lz_features(gf.lz_parse(name), zeros), {'prestart'})
        like = gc.encode(name, raw, like=zeros)
        self.assertIn('prestart', gf.lz_features(gf.lz_parse(name), like))
        self.assertLessEqual(len(like), len(plain))
        self.assertEqual(gc.decode(name, like)[0], raw)

    def test_escape_run_length_is_not_seen_in_plain_data(self):
        # stored bytes "unpack" as themselves until some escape, 00 pair turns up; that is not a stream
        rng = random.Random(41)
        plain = bytes(rng.randrange(1, 256) for _ in range(12000)) + bytes((7, 0))
        with self.assertRaises(ValueError):
            gc.decode('rle-escape', bytes([7]) + plain)
        # a run of one or two bytes (not of the escape itself) is something no packer writes
        with self.assertRaises(ValueError):
            gc.decode('rle-escape', bytes((5, 1, 2, 3, 5, 2, 0x44, 5, 0)))

    def test_konami_run_length_never_writes_the_counts_games_treat_as_commands(self):
        raw = bytes(300) + bytes(range(1, 200)) + b'\x55' * 127 + b'\x66' * 128 + bytes(range(200, 256))
        stream = gc.encode('rle-konami', raw)
        pos = 0
        while stream[pos] != 0xFF:
            self.assertNotIn(stream[pos], (0x7F, 0x80))
            pos += 2 if stream[pos] < 0x80 else 1 + stream[pos] - 0x80
        self.assertEqual(gc.decode('rle-konami', stream)[0], raw)

    def test_stock_bare_codecs_keep_their_size_too(self):
        raw = sample(300, seed=42)
        for name in ('packbits', 'lzss-00-raw', 'lzss-20-raw'):
            stream = gc.encode(name, raw)
            with self.subTest(codec=name):
                self.assertEqual(gc.encode(name, raw, like=stream), stream)
                flat = gc.encode(name, bytes(300), like=stream)     # packs far smaller: lengthened, not left short
                self.assertEqual(len(flat), len(stream))
                self.assertEqual(gc.decode(name, flat, 0, 300)[0][:300], bytes(300))
                with self.assertRaises(ValueError):
                    gc.encode(name, raw, like=stream[:-9])          # packs larger: refused

    def test_cheapest_parse_encoders_beat_plain_greedy(self):
        raw = sample(4096, seed=43)
        # one literal, then a repeat that a greedy parser splits badly
        tricky = b'abcdeXbcdefgh' * 3 + b'Ybcdefgh' + raw[:200]
        for name in ('kosinski', 'konami-snes', 'lz~le16.l1.L4lle.b0.m3.s'):
            with self.subTest(codec=name):
                self.assertEqual(gc.decode(name, gc.encode(name, tricky))[0], tricky)
                self.assertLess(len(gc.encode(name, raw)), len(raw))

    def test_lz5_known_stream(self):
        # literal 3; fill 4 x AA; copy 3 from absolute 0; copy 2 from 1 back; inverted copy 3 from absolute 0; end
        stream = bytes((0x02, 1, 2, 3, 0x23, 0xAA, 0x82, 0x00, 0x00, 0xC1, 0x01, 0xA2, 0x00, 0x00, 0xFF))
        out, used = gc.decode('lz5', stream)
        self.assertEqual(out, bytes((1, 2, 3, 0xAA, 0xAA, 0xAA, 0xAA, 1, 2, 3, 3, 3, 0xFE, 0xFD, 0xFC)))
        self.assertEqual(used, len(stream))
        # the long header: 111 ccc ll + low byte; command 7 (inverted copy from a distance) only exists there
        long = bytes((0x00, 0x55, 0xFC, 0x02, 0x01, 0xFF))
        self.assertEqual(gc.decode('lz5', long)[0], bytes((0x55, 0xAA, 0x55, 0xAA)))

    def test_konami_snes_known_stream(self):
        # as in Super Castlevania IV: 16 zeros, 8 literals, copy 2 from ring 3F5 (two back), 4 literals,
        # run 2 x 38; then two bytes each written after a 00
        body = bytes((0xEE, 0x88, 0x04, 0x3C, 0x7E, 0x32, 0xEF, 0x29, 0xE7, 0x21, 0x03, 0xF5, 0x84, 0x66, 0x22, 0x44, 0x7C,
                      0xC0, 0x38, 0xA0, 0x11, 0x22))
        stream = bytes((len(body) + 2, 0)) + body
        out, used = gc.decode('konami-snes', stream + b'\x99' * 5)
        self.assertEqual(out, bytes(16) + bytes((0x04, 0x3C, 0x7E, 0x32, 0xEF, 0x29, 0xE7, 0x21, 0xE7, 0x21, 0x66, 0x22, 0x44,
                                                 0x7C, 0x38, 0x38, 0x00, 0x11, 0x00, 0x22)))
        self.assertEqual(used, len(stream))

    def test_bare_streams_keep_their_size(self):
        # no end marker: an edit must pack to exactly the old size, or be refused
        name = 'rle~h.r0.l0.n.p1'
        raw = bytes((1, 2, 3, 4, 5, 6)) + bytes(9) + bytes(range(10, 30))
        stream = gc.encode(name, raw)
        self.assertEqual(gc.decode(name, stream, 0, len(raw))[0], raw)
        easier = bytes(15) + bytes(range(10, 30))               # packs smaller: lengthened back to the old size
        again = gc.encode(name, easier, like=stream)
        self.assertEqual(len(again), len(stream))
        self.assertEqual(gc.decode(name, again, 0, len(easier))[0], easier)
        harder = bytes(range(100, 135))                         # packs larger
        with self.assertRaises(ValueError):
            gc.encode(name, harder, like=stream)
        lz = 'lz~n.l1.oku.b0.m3.n'
        packed = gc.encode(lz, raw)
        with self.assertRaises(ValueError):
            gc.encode(lz, harder, like=packed)

    def test_bare_streams_stop_at_what_follows(self):
        name = 'rle~h.r0.l0.n.p1'
        raw = sample(120, seed=21)
        stream = gc.encode(name, raw)
        out, used = gc.decode(name, stream + b'\x00\x80\x00junk', 0, 0x1000)
        self.assertEqual(out, raw)
        self.assertEqual(used, len(stream))

    def test_members_found_in_games_are_valid(self):
        for system, names in gc.MEMBERS.items():
            for name in names:
                with self.subTest(system=system, codec=name):
                    self.check(name, sample(200, seed=22))

    def test_decode_cache_tells_roms_apart(self):
        raw = sample(300, seed=23)
        stream = gc.encode('lz2', raw)
        rom_a = bytes(0x2000) + stream + bytes(64)
        other = bytearray(raw)
        other[10] ^= 0xFF
        rom_b = bytes(0x2000) + gc.encode('lz2', bytes(other)) + bytes(64)
        self.assertEqual(gc.decode('lz2', rom_a, 0x2000)[0], raw)
        self.assertEqual(gc.decode('lz2', rom_b, 0x2000)[0], bytes(other))
        self.assertEqual(gc.decode('lz2', rom_a, 0x2000)[0], raw)
        for _ in range(2):
            with self.assertRaises(ValueError):
                gc.decode('nemesis', rom_a, 0)      # not a stream: both fresh and from the cache

    def test_encode_like_keeps_nintendo_commands(self):
        raw = sample(600, seed=8)
        plain = gc.encode('lz2', raw)
        again = gc.encode('lz2', raw, like=plain)
        self.assertEqual(gc.decode('lz2', again)[0], raw)


class Layouts(unittest.TestCase):
    def test_expand_contract(self):
        for text in list(gc.MAP_ALIASES) + ['012Z', '01ZZ', '0ZZZ', '0F', 'Z0', '00', '01FF']:
            m, k, _ = gc.map_parse(text)
            stored = sample(k * 20, seed=9, tile=k)
            wide = gc.map_expand(text, stored)
            with self.subTest(map=text):
                self.assertEqual(len(wide), len(stored) // k * m)
                self.assertEqual(gc.map_contract(text, wide), stored)
                for i in range(len(wide)):
                    q = gc.map_index(text, i)
                    if q is not None:
                        self.assertEqual(wide[i], stored[q])

    def test_3bpp_matches_the_super_nes_layout(self):
        stored = bytes(range(1, 25))
        wide = gc.map_expand('3bpp', stored)
        self.assertEqual(wide[:16], stored[:16])
        self.assertEqual(wide[16:], bytes(v for b in stored[16:] for v in (b, 0)))

    def test_made_up_bytes_cannot_be_edited(self):
        wide = bytearray(gc.map_expand('012Z', bytes(range(30))))
        wide[3] = 1
        with self.assertRaises(ValueError):
            gc.map_contract('012Z', bytes(wide))
        twice = bytearray(gc.map_expand('00', bytes(range(8))))
        twice[1] ^= 1
        with self.assertRaises(ValueError):
            gc.map_contract('00', bytes(twice))

    def test_codec_with_layout(self):
        stored = sample(24 * 16, seed=10, tile=24)
        wide = gc.map_expand('3bpp', stored)
        for base in ('lz2', 'hal', 'raw', 'lzss-00-le16', 'rle-konami'):
            name = base + '|3bpp'
            with self.subTest(codec=name):
                stream = gc.encode(name, wide)
                self.assertEqual(stream, gc.encode(base, stored))
                out, used = gc.decode(name, stream, 0, 0x10000 if gc.CODECS[name]['terminated'] else len(wide))
                self.assertEqual(out[:len(wide)], wide)
        bad = bytearray(wide)
        bad[17] = 0x80
        with self.assertRaises(ValueError):
            gc.encode('lz2|3bpp', bytes(bad))

    def test_layouts_are_not_listed_as_codecs(self):
        gc.CODECS['lz2|3bpp']
        gc.CODECS['rle~h.r1.l1.f.p1']
        self.assertNotIn('lz2|3bpp', list(gc.CODECS))
        self.assertNotIn('rle~h.r1.l1.f.p1', list(gc.CODECS))
        for system in ('snes', 'gb', 'genesis', 'sms', 'nes', 'gbc'):
            self.assertTrue(all('|' not in name for name in gc.order_for(system)))


class Recognise(unittest.TestCase):
    def scene(self, codec, text, raw, where=0x4321, base=0x800, size=0x4000, junk_seed=11):
        """A ROM holding `raw` packed at `where`, and video memory holding it (laid out by `text`) at `base`."""
        rng = random.Random(junk_seed)
        stream = gc.encode(codec, raw)
        rom = bytearray(rng.randrange(1, 255) for _ in range(0x8000))
        rom[where:where + len(stream)] = stream
        wide = gc.map_expand(text, raw) if text else raw
        data = bytearray(size)
        data[base:base + len(wide)] = wide
        tags = [0] * size
        for i in range(len(wide)):
            # as the tracer tags unpacked bytes: an offset inside the stream (past any header), rising through it
            tags[base + i] = DERIVED_TAG | (where + 3 + i * (len(stream) - 4) // len(wide))
        return bytes(rom), Domain(data, tags), stream, wide

    def test_finds_streams(self):
        cases = [('rle-sega-planes', '', 'sms', 32), ('lz2', '3bpp', 'snes', 32), ('hal', '', 'gb', 16),
                 ('kosinski', '', 'genesis', 32), ('comper', '', 'genesis', 32), ('saxman', '', 'genesis', 32),
                 ('nemesis', '', 'genesis', 32), ('rle-konami', '1of2n', 'nes', 16), ('lz3', '0Z', 'gbc', 16),
                 ('lz5', '', 'snes', 32), ('konami-snes', '', 'snes', 32), ('lz~le16.l1.oku.b0.m3.s', '', 'snes', 32),
                 ('rnc1', '', 'snes', 32), ('rnc2', '', 'genesis', 32), ('lz-ring256', '', 'snes', 32),
                 ('lz-konami-md', '', 'genesis', 32)]
        for codec, text, system, tile in cases:
            k = gc.map_parse(text)[1] if text else 32
            raw = sample(768, seed=12 + len(codec), tile=k)
            rom, d, stream, wide = self.scene(codec, text, raw)
            # a tile in the middle with a picture in it
            start = next(s for s in range(0x800 + (len(wide) // 2) // tile * tile, 0x800 + len(wide), tile)
                         if len(set(d.data[s:s + tile])) > 4)
            with self.subTest(codec=codec, layout=text):
                hit = gc.recognise(d, rom, 0, system, start, tile)
                self.assertIsNotNone(hit)
                self.assertEqual(hit['codec'], codec + ('|' + text if text else ''))
                self.assertEqual(hit['start'], 0x4321)
                self.assertEqual(hit['size'], len(stream))
                self.assertTrue(hit['complete'])
                self.assertEqual(hit['decoded'][hit['first']:hit['last']],
                                 d.data[hit['domain_start']:hit['domain_start'] + hit['last'] - hit['first']])
                # an edit made through the block re-encodes and unpacks to the edited block
                edited = bytearray(hit['decoded'])
                k0 = start - hit['domain_start'] + hit['first']
                edited[k0] ^= 0x10
                again = gc.encode(hit['codec'], bytes(edited), like=rom[hit['start']:hit['start'] + hit['size']])
                self.assertEqual(gc.decode(hit['codec'], again)[0][:len(edited)], bytes(edited))

    def test_finds_a_bare_stream_and_stops_where_it_ends(self):
        codec = 'rle~h.r0.l0.n.p1'
        raw = sample(400, seed=31)
        rom, d, stream, wide = self.scene(codec, '', raw)
        start = next(s for s in range(0x800 + 96, 0x800 + 300, 16) if len(set(d.data[s:s + 16])) > 4)
        # (asked for by name: left to itself, recognise() may first find the tile inside one of the
        # stream's literal blocks and offer it as stored data, which is also a sound way to edit it)
        hit = gc.recognise(d, rom, 0, 'gbc', start, 16, codecs=[codec])
        self.assertIsNotNone(hit)
        self.assertEqual((hit['codec'], hit['start']), (codec, 0x4321))
        self.assertEqual(hit['decoded'][:len(raw)], raw)
        self.assertGreaterEqual(hit['last'], len(raw))
        self.assertLess(hit['last'], len(raw) + 130)    # at most one command of the junk after the stream
        edited = bytearray(hit['decoded'])
        edited[start - hit['domain_start'] + hit['first']] ^= 0x10
        like = rom[hit['start']:hit['start'] + hit['size']]
        try:
            again = gc.encode(codec, bytes(edited), like=like)
        except ValueError:
            return      # refused: it would not pack to the same size, which is the safe answer
        self.assertEqual(len(again), len(like))

    def test_finds_plain_data_with_made_up_planes(self):
        rng = random.Random(13)
        rom = bytes(rng.randrange(1, 255) for _ in range(0x4000))
        where, base, groups = 0x1230, 0x400, 200
        wide = gc.map_expand('01ZZ', rom[where:where + 2 * groups])
        data = bytearray(0x2000)
        data[base:base + len(wide)] = wide
        tags = [0] * len(data)
        for g in range(groups):
            tags[base + g * 4] = ROM_TAG | (where + g * 2)
            tags[base + g * 4 + 1] = ROM_TAG | (where + g * 2 + 1)
            tags[base + g * 4 + 2] = tags[base + g * 4 + 3] = DERIVED_TAG | (where + g * 2 + 1) | 0x80000000
        d = Domain(data, tags)
        hit = gc.recognise(d, rom, 0, 'sms', base + 320, 32)
        self.assertEqual(hit['codec'], 'raw|01ZZ')
        self.assertEqual((hit['start'], hit['size'], hit['domain_start']), (where, 2 * groups, base))
        edited = bytearray(hit['decoded'])
        edited[320] ^= 0x0F
        self.assertEqual(len(gc.encode(hit['codec'], bytes(edited))), hit['size'])
        edited[322] = 1     # the plane the game makes up
        with self.assertRaises(ValueError):
            gc.encode(hit['codec'], bytes(edited))

    def test_nothing_for_unrelated_memory(self):
        rng = random.Random(14)
        rom = bytes(rng.randrange(256) for _ in range(0x4000))
        data = bytes(rng.randrange(256) for _ in range(0x1000))
        d = Domain(data, [DERIVED_TAG | (0x1000 + i // 2) for i in range(len(data))])
        self.assertIsNone(gc.recognise(d, rom, 0, 'gb', 0x400, 16))

    def test_search_names_a_family_member(self):
        raw = sample(32 * 20, seed=15, tile=32)
        for codec in ('lz~le16.l1.L5hle.r7de.m3.s', 'rle~h.r1.l1.f.p1'):
            rom, d, stream, wide = self.scene(codec, '', raw)
            start = next(s for s in range(0x800 + 320, 0x800 + len(wide), 32) if len(set(d.data[s:s + 32])) > 4)
            with self.subTest(codec=codec):
                hit = gc.search_families(d, rom, 0, 'snes', start, 32)
                self.assertIsNotNone(hit)
                self.assertEqual(hit['codec'], codec)
                self.assertEqual(hit['start'], 0x4321)


class SameSize(unittest.TestCase):
    """A bare stream is replaced by one of exactly its size: the encoders lengthen a shorter result."""

    NAMES = ('lzss-00-raw', 'lzss-20-raw', 'packbits', 'lz~n.m0.L6hbe.b1.m2.n', 'lz~n.l1.L4lbe.b1.m3.n', 'rle~h.r0.l0.n.p1')

    def test_shorter_results_are_lengthened(self):
        for name in self.NAMES:
            reached = 0
            for seed in range(4):
                raw = sample(700, seed=seed + 60)
                base = gc.encode(name, raw)
                for extra in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 17, 40, 100):
                    like = base + bytes(extra)
                    try:
                        stream = gc.encode(name, raw, like=like)
                    except ValueError:
                        continue        # refused, never left short
                    reached += 1
                    self.assertEqual(len(stream), len(like), name)
                    self.assertEqual(gc.decode(name, stream, 0, len(raw))[0][:len(raw)], raw, name)
            with self.subTest(codec=name):
                self.assertGreaterEqual(reached, 48)        # of 52

    def test_longer_results_are_refused(self):
        raw = sample(700, seed=64)
        for name in self.NAMES:
            with self.subTest(codec=name):
                with self.assertRaises(ValueError):
                    gc.encode(name, raw, like=gc.encode(name, raw)[:-1])

    def test_a_small_edit_usually_fits_back(self):
        # the common case: one tile redrawn inside a block
        raw = bytearray(sample(1500, seed=65))
        for name in ('lzss-00-raw', 'packbits'):
            like = gc.encode(name, bytes(raw))
            edited = bytearray(raw)
            edited[700:716] = bytes(16)         # a tile made flat packs smaller
            stream = gc.encode(name, bytes(edited), like=like)
            self.assertEqual(len(stream), len(like))
            self.assertEqual(gc.decode(name, stream, 0, len(raw))[0][:len(raw)], bytes(edited))


class Packers(unittest.TestCase):
    """The bit-stream packers of gfx_packers."""

    def test_checksum_is_crc16_arc(self):
        self.assertEqual(gp.crc16_arc(b'123456789'), 0xBB3D)

    def test_rnc2_known_stream(self):
        # two skipped bits; literal A; literal B; two bytes from two back; the end. Bit bytes are
        # fetched when a bit is wanted, so the stream is: 0D, 'A', 'B', distance - 1, E0, length byte 00.
        body = bytes((0x0D, 0x41, 0x42, 0x01, 0xE0, 0x00))
        sums = gp.crc16_arc(b'ABAB').to_bytes(2, 'big') + gp.crc16_arc(body).to_bytes(2, 'big')
        head = b'RNC\x02' + (4).to_bytes(4, 'big') + len(body).to_bytes(4, 'big') + sums + bytes((0, 1))
        self.assertEqual(gc.decode('rnc2', head + body + b'tail'), (b'ABAB', 18 + len(body)))
        self.assertEqual(gc.encode('rnc2', b'ABAB'), head + body)

    def test_rnc2_every_copy_form(self):
        # lengths 2 to 263 at distances that need every form of the distance's high bits
        rng = random.Random(51)
        for length in (2, 3, 4, 5, 6, 7, 8, 9, 40, 263):
            for dist in (1, 2, 255, 256, 257, 600, 800, 1100, 2000, 2300, 3000, 4096):
                noise = bytes(rng.randrange(256) for _ in range(dist + length + 7))
                tail = noise[len(noise) - dist:len(noise) - dist + length] if dist >= length else (noise[-dist:] * length)[:length]
                raw = noise + tail
                with self.subTest(length=length, dist=dist):
                    stream = gc.encode('rnc2', raw)
                    self.assertEqual(gc.decode('rnc2', stream), (raw, len(stream)))

    def test_rnc_header_fields(self):
        raw = sample(3000, seed=52)
        for name, method in (('rnc1', 1), ('rnc2', 2)):
            stream = gc.encode(name, raw)
            with self.subTest(codec=name):
                self.assertEqual(stream[:4], b'RNC' + bytes([method]))
                self.assertEqual(int.from_bytes(stream[4:8], 'big'), len(raw))
                self.assertEqual(int.from_bytes(stream[8:12], 'big'), len(stream) - 18)
                self.assertEqual(int.from_bytes(stream[12:14], 'big'), gp.crc16_arc(raw))
                self.assertEqual(int.from_bytes(stream[14:16], 'big'), gp.crc16_arc(stream[18:]))
                # the replaced stream's leeway byte is kept
                like = bytearray(stream)
                like[16] = 9
                self.assertEqual(gc.encode(name, raw, like=bytes(like))[16], 9)

    def test_rnc1_many_chunks_and_long_literal_runs(self):
        rng = random.Random(53)
        noise = bytes(rng.randrange(256) for _ in range(0x7400))      # longer than one literal count can say
        pairs = b''.join(bytes((rng.randrange(256), rng.randrange(256))) * 3 for _ in range(0x900))   # > 0x7FF copies
        for raw in (noise, pairs, noise + pairs):
            stream = gc.encode('rnc1', raw)
            self.assertEqual(gc.decode('rnc1', stream, 0, 0x20000), (raw, len(stream)))
            self.assertGreaterEqual(stream[17], 1)

    def test_rnc_rejects_what_is_not_a_stream(self):
        raw = sample(500, seed=54)
        for name in ('rnc1', 'rnc2'):
            stream = gc.encode(name, raw)
            with self.subTest(codec=name):
                with self.assertRaises(ValueError):
                    gc.decode(name, b'RNX' + stream[3:])
                with self.assertRaises(ValueError):
                    gc.decode(name, stream[:4] + b'\x7F\xFF\xFF\xFF' + stream[8:])     # an absurd size
                with self.assertRaises((ValueError, IndexError)):
                    gc.decode(name, stream[:len(stream) // 2])

    def test_ring256_known_streams(self):
        # literal A, literal B, three bytes from ring position EF (where A went): 31 bits, padded
        stream = bytes((0x05, 0x00, 0xA0, 0xD0, 0x9D, 0xE2))
        self.assertEqual(gc.decode('lz-ring256', stream + b'rest'), (b'ABABA', len(stream)))
        self.assertEqual(gc.encode('lz-ring256', b'ABABA'), stream)
        # a copy from a part of the ring nothing was written to yet reads the 20 it starts filled with
        self.assertEqual(gc.decode('lz-ring256', bytes((0x04, 0x00, 0x00, 0x10))), (b'    ', 4))

    def test_ring256_never_copies_from_further_back_than_the_ring(self):
        rng = random.Random(56)
        block = bytes(rng.randrange(256) for _ in range(300))
        raw = block + block             # the repeat is 300 back: out of reach
        stream = gc.encode('lz-ring256', raw)
        self.assertEqual(gc.decode('lz-ring256', stream), (raw, len(stream)))
        self.assertGreater(len(stream), 600)
        near = block[:200] + block[:200]
        self.assertLess(len(gc.encode('lz-ring256', near)), 280)

    def test_konami_md_known_stream(self):
        # flags 0C: literal A, literal B, command A2 (four bytes from two back), command 1F (the end)
        stream = bytes((0x00, 0x06, 0x0C, 0x41, 0x42, 0xA2, 0x1F))
        self.assertEqual(gc.decode('lz-konami-md', stream + b'rest'), (b'ABABAB', len(stream)))
        self.assertEqual(gc.encode('lz-konami-md', b'ABABAB'), stream)
        # a far copy: 0x25 0x10 is (5 + 3) bytes from (1 << 8 | 0x10) back; a literal run: C1 + nine bytes
        head = bytes(range(1, 10))
        filler = bytes((7,)) * 0x110
        raw = head + filler + head[:8]
        stream = gc.encode('lz-konami-md', raw)
        self.assertEqual(gc.decode('lz-konami-md', stream), (raw, len(stream)))

    def test_konami_md_never_writes_the_end_marker_as_a_copy(self):
        # 34 bytes from less than 256 back would be command byte 1F, which ends the stream
        rng = random.Random(57)
        block = bytes(rng.randrange(256) for _ in range(34))
        raw = block + bytes(rng.randrange(256) for _ in range(60)) + block
        stream = gc.encode('lz-konami-md', raw)
        self.assertEqual(gc.decode('lz-konami-md', stream), (raw, len(stream)))
        with self.assertRaises(ValueError):
            gc.decode('lz-konami-md', stream[:-1] + b'\x00')        # no end marker
        with self.assertRaises(ValueError):
            gc.decode('lz-konami-md', b'\x00\x09' + stream[2:])      # the size does not agree

    def test_magic_starts_are_the_nearest_streams_in_front(self):
        rom = bytearray(0x3000)
        for at in (0x100, 0x900, 0x2000):
            rom[at:at + 4] = b'RNC\x01'
        self.assertEqual(gc.magic_starts(bytes(rom), 0, b'RNC\x01', [0x950]), [0x900, 0x100])
        self.assertEqual(gc.magic_starts(bytes(rom), 0x10, b'RNC\x01', [0x1FF0, 0x8F0]), [0x1FF0, 0x8F0, 0xF0])
        self.assertEqual(gc.magic_starts(bytes(rom), 0, b'RNC\x02', [0x950]), [])

    def test_matches_are_real(self):
        raw = sample(2000, seed=55)
        for i, (k, dist) in enumerate(gp.lz_matches(raw, 300, 40, 2)):
            if k:
                self.assertTrue(2 <= k <= 40 and 1 <= dist <= 300 and dist <= i)
                self.assertEqual(bytes(raw[i - dist + j] for j in range(k)), raw[i:i + k])


if __name__ == '__main__':
    unittest.main()
