"""Synthetic, original map programs; no game data is bundled in fixtures."""
from pathlib import Path
import tempfile
import unittest


def point(x, y, tile):
    return bytes((0x10 | (y >> 2), ((y & 3) << 6) | x, tile))


def make_room_fixture(base=None):
    raw = bytearray(base or b'')
    raw.extend(bytes(262144 - len(raw)))
    raw[0x1c86b:0x1c86e] = (0x265).to_bytes(2, 'little') + bytes((11,))
    # Checker fill, move, floor rectangle, doorway, then harmless move commands.
    stream = bytearray((0x70, 0, 0x27, 0xcc, 0x48, 0x0e, 19))
    stream.extend(point(13, 33, 19))
    while len(stream) < 0x20375 - 0x20265:
        stream.extend((0x20, 0))
    stream.extend(point(14, 31, 29)); stream.append(0)
    raw[0x20265:0x20265+len(stream)] = stream
    raw[0x1f160:0x1f180] = bytes([3] * 32)
    raw[0x1f160+19] = raw[0x1f160+29] = 1
    raw[0x1f960+19] = 1
    # Graphic 1 has distinct source indices in each quadrant.
    for q in range(4):
        for row in range(8):
            raw[0x8040+q*16+row*2:0x8042+q*16+row*2] = bytes((255 if q & 1 else 0, 255 if q & 2 else 0))
    return raw


class VerifiedRoomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'root.gb'; self.current = Path(self.temp.name)/'current.gb'
        self.raw = make_room_fixture(); self.root.write_bytes(self.raw); self.current.write_bytes(self.raw)

    def test_room_decodes_original_geometry_and_live_2bpp_tiles(self):
        from romancer.verified_room import room_visual
        room = room_visual(self.current, self.root)
        self.assertEqual(room['kind'], 'room-map')
        self.assertEqual((room['origin'], room['size'], room['tile_size']), ([10,28], [7,8],16))
        self.assertEqual(room['current'], [14,31])
        self.assertEqual(room['base_cells'][3*7+4], 19)
        self.assertEqual(room['original_cells'][3*7+4], 29)
        self.assertEqual(len(room['tiles']),64)
        tile = room['tiles'][19]
        self.assertEqual([tile[i] for i in (0,8,128,136)], [0,1,2,3])
        self.assertEqual(room['palette'], [[85]*3,[255]*3,[170]*3,[0]*3])
        self.assertEqual(len(room['collision_values']),56)
        self.assertEqual(room['collision_values'][3*7+4],1)
        changed=self.raw.copy();changed[0x1f960+19]=0;self.current.write_bytes(changed)
        self.assertEqual(set(room_visual(self.current,self.root)['tiles'][19]),{0})

    def test_only_five_floor_cells_are_writable_and_round_trip(self):
        from romancer.verified_room import room_visual, encode_move
        allowed=[[12,31],[14,31],[12,32],[13,32],[14,32]]
        self.assertEqual(room_visual(self.current,self.root)['object']['allowed'],allowed)
        for x,y in allowed:
            value='original' if [x,y]==[14,31] else 'stool_down' if [x,y]==[14,32] else f'at:{x},{y}'
            encoded=encode_move(self.current,self.root,value)
            self.assertEqual(encoded,point(x,y,29))
            changed=self.raw.copy();changed[0x20375:0x20378]=encoded;self.current.write_bytes(changed)
            room=room_visual(self.current,self.root)
            self.assertEqual(room['value'],value);self.assertEqual(room['current'],[x,y])
        for value in ('at:13,33','at:13,31','at:64,32','at:-1,32','at:12,31junk',True,None):
            with self.subTest(value=value), self.assertRaises(ValueError):encode_move(self.current,self.root,value)
        self.assertEqual(self.root.read_bytes(),self.raw)

    def test_unrelated_map_header_collision_and_unsafe_current_refuse(self):
        from romancer.verified_room import room_visual
        for offset,value in ((0x20266,1),(0x1c86c,3),(0x1f160+19,2),(0x20377,30)):
            changed=self.raw.copy();changed[offset]=value;self.current.write_bytes(changed)
            with self.subTest(offset=offset),self.assertRaises(ValueError):room_visual(self.current,self.root)
        changed=self.raw.copy();changed[0x20375:0x20378]=point(13,33,29);self.current.write_bytes(changed)
        with self.assertRaises(ValueError):room_visual(self.current,self.root)

    def test_map_decoder_bounds_unknown_ops_truncation_and_point_provenance(self):
        from romancer.verified_room import decode_commands, room_visual
        for raw in (bytes((0xb0,0)),bytes((0x10,0)),bytes((0x20,0))*1001):
            with self.subTest(raw_length=len(raw)),self.assertRaises(ValueError):decode_commands(raw,0,len(raw))
        # A point-looking byte sequence after an early terminator is not an object.
        changed=self.raw.copy();changed[0x20265]=0;self.root.write_bytes(changed);self.current.write_bytes(changed)
        with self.assertRaises(ValueError):room_visual(self.current,self.root)

    def test_line_rectangle_circle_and_checker_commands(self):
        from romancer.verified_room import decode_commands
        # Original authored test program: checker 1/2, rectangle 3/4, line 5,
        # and radius-one circle 6 around (4,4).
        raw=bytes((0x70,0x81,0x20,0x41,0x40,0xc3,0x43,4,0x60,0x45,5,0x21,4,0x51,5,6,0))
        # Circle lookup is data from the input, expressed as a synthetic table.
        raw+=bytes(64-len(raw));raw+=bytes((66,0,1,0,255))
        grid,commands,end=decode_commands(raw,0,18,circle_table=64)
        self.assertEqual(grid[0],1);self.assertEqual(grid[1],2)
        self.assertEqual(grid[2*64+1],4);self.assertEqual(grid[2*64+2],3)
        self.assertEqual(grid[1*64+5],5)
        self.assertEqual([grid[y*64+x] for x,y in ((3,4),(5,4),(4,3),(4,5))],[6]*4)


if __name__=='__main__':unittest.main()
