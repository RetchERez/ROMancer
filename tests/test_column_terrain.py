import unittest
from romancer.column_terrain import decode_stream,edit_operands


def screen(first=b''):
 return first+b'\xfe'*(20-(1 if first.endswith(b'\xfe')else 0))


class SmlColumnCodecTests(unittest.TestCase):
 def test_zero_count_means_sixteen_and_repeat_fills_remaining_count(self):
  raw=screen(bytes([0x00,0xfd,0x42,0xfe]));r=decode_stream(raw,base=0x8000)
  self.assertEqual(r.consumed,len(raw));self.assertEqual(r.tiles,tuple(0x42 if x==0 else 0x2c for y in range(16)for x in range(20)))
  operand=r.operands[0];self.assertEqual(operand.offset,0x8002);self.assertEqual(operand.cells,tuple(y*20 for y in range(16)));self.assertTrue(operand.repeat)
  changed=edit_operands(raw,base=0x8000,edits=[{'offset':0x8002,'tile':0x44}]);self.assertEqual(changed[:2],raw[:2]);self.assertEqual(changed[3:],raw[3:]);self.assertEqual(decode_stream(changed,base=0x8000).tiles[300],0x44)
 def test_marker_meaning_depends_on_header_literal_and_repeat_position(self):
  for repeated in(0xfd,0xfe):
   raw=screen(bytes([0x03,0x22,0xfd,repeated,0xfe]));r=decode_stream(raw)
   self.assertEqual([r.tiles[y*20]for y in range(3)],[0x22,repeated,repeated]);self.assertEqual(r.origins[40],3)
  raw=screen(bytes([0x12,0xfe,7,0xfe]));r=decode_stream(raw)
  self.assertEqual((r.tiles[20],r.tiles[40]),(0xfe,7));self.assertEqual(r.origins[20],1)
  changed=edit_operands(raw,edits=[{'offset':1,'tile':8}]);self.assertEqual(changed,raw[:1]+bytes([8])+raw[2:])
 def test_default_cells_have_no_operand_and_noop_serialization_preserves_bytes(self):
  raw=b'\xfe'*20+b'not part of this stream';r=decode_stream(raw,base=0x4000)
  self.assertEqual(r.consumed,20);self.assertEqual(r.tiles,(0x2c,)*320);self.assertEqual(r.origins,(None,)*320)
  self.assertEqual(edit_operands(raw,base=0x4000,edits=[]),raw[:20])
  with self.assertRaisesRegex(ValueError,'operand'):edit_operands(raw,base=0x4000,edits=[{'offset':0x4000,'tile':1}])
 def test_absolute_rows_and_overlaps_decode_last_write_but_shadowed_edits_refuse(self):
  raw=screen(bytes([0x12,4,5,0x21,6,0xfe]));r=decode_stream(raw)
  self.assertEqual((r.tiles[20],r.tiles[40]),(4,6));self.assertEqual(r.origins[40],4);self.assertEqual(r.overlaps,1)
  with self.assertRaisesRegex(ValueError,'overlap'):edit_operands(raw,edits=[{'offset':2,'tile':7}])
 def test_unsafe_grammar_changes_interaction_changes_and_bad_edits_refuse(self):
  raw=screen(bytes([0x01,4,0xfe]))
  for edits in[[{'offset':1,'tile':0xfd}],[{'offset':1,'tile':0x70}],[{'offset':True,'tile':5}],[{'offset':1,'tile':True}],[{'offset':1,'tile':5},{'offset':1,'tile':6}],[{'offset':1,'tile':256}],[{'offset':0,'tile':7}]]:
   with self.subTest(edits=edits),self.assertRaises(ValueError):edit_operands(raw,edits=edits)
  for tile in(0x70,0x80,0x5f,0x81):
   protected=screen(bytes([0x01,tile,0xfe]));self.assertEqual(edit_operands(protected,edits=[]),protected)
   with self.assertRaisesRegex(ValueError,'(?i)interactive'):edit_operands(protected,edits=[{'offset':1,'tile':6}])
 def test_bounds_and_missing_markers_are_rejected(self):
  for raw,base in[(b'\xfe'*19,0),(screen(bytes([0xf2,1,2,0xfe])),0),(b'\x01\xfd',0),(b'\xfe'*20,0x7ff0),(b'\xfe'*20,True)]:
   with self.subTest(base=base,raw=raw),self.assertRaises(ValueError):decode_stream(raw,base=base)

if __name__=='__main__':unittest.main()
