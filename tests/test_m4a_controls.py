import hashlib,os,unittest
from pathlib import Path
from romancer.m4a_music import decode_track

class ControlTests(unittest.TestCase):
    def test_pan_and_voice_are_decoded_without_exposing_protected_voice_writes(self):
        raw=bytes([0xbd,7,0xbf,32,0xd1,60,80,0x84,0xbf,96,0xd1,62,75,0xb1])
        doc=decode_track(raw,0,0,len(raw),include_controls=True);self.assertFalse(doc['issues'])
        pans=[e for e in doc['events'] if e['kind']=='pan'];self.assertEqual([e['pan'] for e in pans],[32,96]);self.assertEqual(pans[0]['edit_offsets'],{'pan':3})
        notes=[e for e in doc['events'] if e['kind']=='note'];self.assertEqual([(e['instrument'],e['pan']) for e in notes],[(7,32),(7,96)])
        voice=next(e for e in doc['events'] if e['kind']=='instrument');self.assertEqual(voice['editable_fields'],[])
        legacy=decode_track(raw,0,0,len(raw));self.assertEqual(len(legacy['events']),2);self.assertEqual(legacy['roles'][3],'parameter')
    def test_out_of_range_pan_disables_editing(self):
        raw=bytes([0xbf,255,0xb1]);self.assertTrue(decode_track(raw,0,0,len(raw),include_controls=True)['issues'])

@unittest.skipUnless(os.environ.get('ROMANCER_WL4_TEST_ROM'),'Private user ROM is not included')
class NativeRevisionControlTests(unittest.TestCase):
    def test_new_controls_keep_legacy_documents_and_identify_instruments(self):
        from romancer.m4a_music import inspect_song,plan_song
        from romancer.m4a_instruments import inspect_instrument
        raw=Path(os.environ['ROMANCER_WL4_TEST_ROM']).read_bytes();sha=hashlib.sha256(raw).hexdigest()
        legacy=inspect_song(raw,'635',sha,driver='wl4-m4a-v1');self.assertEqual(len(legacy['events']),151)
        song=inspect_song(raw,'635',sha);self.assertEqual(song['driver'],'wl4-m4a-v2');self.assertTrue(song['sequence_edit_supported'],song['issues'])
        index=next(i for i,e in enumerate(song['events']) if e['kind']=='pan');event=song['events'][index];value=16 if event['pan']!=16 else 112
        plan=plan_song(raw,song['definition'],song['document_id'],[{'kind':'note','song_id':'635','index':index,'field':'pan','value':value}],sha)
        self.assertEqual(plan['edits'][0]['offset'],event['edit_offsets']['pan']);self.assertEqual(plan['edits'][0]['after'],bytes([value]).hex())
        instrument=next(e['instrument'] for e in song['events'] if e['instrument'] is not None)
        data=inspect_instrument(raw,'635',instrument,sha);self.assertEqual(data['instrument'],instrument);self.assertFalse(data['editable']);self.assertIn('type',data)
        with self.assertRaises(ValueError):plan_song(raw,song['definition'],song['document_id'],[{'kind':'note','song_id':'635','index':index,'field':'pan','value':128}],sha)
