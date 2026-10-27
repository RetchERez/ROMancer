import hashlib,unittest,os
from pathlib import Path
from romancer.m4a_music import decode_track,plan_song

class M4ATrackTests(unittest.TestCase):
 def stream(self,body,**kw):return decode_track(bytes(body),0,0,len(body),**kw)
 def test_explicit_and_inherited_notes_running_status_waits_and_tempo(self):
  doc=self.stream([0xbb,43,0xbe,56,0xd1,60,80,0x84,62,70,0x82,0xd1,64,0x82,0xb1])
  self.assertFalse(doc['issues']);notes=[e for e in doc['events'] if e['kind']=='note']
  self.assertEqual([(e['note'],e['volume'],e['tick']) for e in notes],[(60,80,0),(62,70,4),(64,70,6)])
  self.assertEqual(notes[-1]['editable_fields'],['note']);self.assertEqual(doc['events'][0]['tempo_bpm'],86)
 def test_pattern_returns_repeat_counter_and_bounded_loop(self):
  # PATT -> note,FINE-equivalent return, then REPT twice -> final FINE.
  body=bytearray([0xb3,0,0,0,8,0xb1,0xb1,0xb1,0xd1,60,80,0x81,0xb4]);body[1:5]=(0x08000008).to_bytes(4,'little')
  doc=self.stream(body);self.assertFalse(doc['issues']);self.assertEqual(doc['termination'],'fine')
  loop=self.stream([0xd1,60,80,0x81,0xb2,0,0,0,8]);self.assertEqual(loop['termination'],'loop');self.assertLessEqual(len(loop['events']),2)
 def test_unsupported_conditional_or_bad_pointer_is_read_only(self):
  for body in ([0xb9,6,0,0,0,0,0,8],[0xb2,0,0,0,9],[60],[0xcd,99,0xb1],[0xd1,60]):
   with self.subTest(body=body):self.assertTrue(self.stream(body)['issues'])
 def test_opcode_operand_alias_is_refused(self):
  doc=self.stream([0xd1,60,80,0xb2,2,0,0,8]);self.assertTrue(doc['issues'])
 def test_budget_and_recursion_never_run_unbounded(self):
  self.assertTrue(self.stream([0xb3,0,0,0,8])['issues'])
  self.assertTrue(self.stream([0x81]*40+[0xb1],instruction_limit=8)['issues'])
 def test_source_and_document_bindings_are_mandatory(self):
  with self.assertRaisesRegex(ValueError,'identified'):plan_song(b'not a game',{'id':'x'},'bad',[],hashlib.sha256(b'not a game').hexdigest())

@unittest.skipUnless(os.environ.get('ROMANCER_WL4_TEST_ROM'),'Private user-supplied commercial ROM is not distributed')
class M4ARevisionTests(unittest.TestCase):
 def setUp(self):self.raw=Path(os.environ['ROMANCER_WL4_TEST_ROM']).read_bytes();self.sha=hashlib.sha256(self.raw).hexdigest()
 def test_selected_catalog_checks_control_flow_and_conservative_editing(self):
  from romancer.m4a_music import inspect_song,identified
  song=inspect_song(self.raw,'635',self.sha);self.assertTrue(song['sequence_edit_supported']);self.assertEqual(len(song['tracks']),7)
  index=next(i for i,e in enumerate(song['events']) if e['edit_offsets'].get('note')==0x250342)
  change={'kind':'note','song_id':'635','index':index,'field':'note','value':62}
  plan=plan_song(self.raw,song['definition'],song['document_id'],[change],self.sha);self.assertEqual(plan['edits'],[{'offset':0x250342,'before':'32','after':'3e'}])
  changed=bytearray(self.raw);changed[0x250342]=62;changed=bytes(changed);self.assertTrue(inspect_song(changed,'635',hashlib.sha256(changed).hexdigest())['sequence_edit_supported'])
  for offset in (0x1540,0x1710,0x9540c):
   bad=bytearray(self.raw);bad[offset]^=1;self.assertFalse(identified(bytes(bad)))
  bad=bytearray(self.raw);bad[0x250332]^=1;bad=bytes(bad);self.assertFalse(inspect_song(bad,'635',hashlib.sha256(bad).hexdigest())['sequence_edit_supported'])
  for field,value in [('duration',12),('note',128),('note',True)]:
   with self.assertRaises(ValueError):plan_song(self.raw,song['definition'],song['document_id'],[{**change,'field':field,'value':value}],self.sha)
  for ident in ('639','651'):self.assertFalse(inspect_song(self.raw,ident,self.sha)['sequence_edit_supported'])
