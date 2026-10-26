"""Original synthetic observations; no game names or private ROM data required."""
import copy
import hashlib
import importlib.util
import unittest


def observation(raw,sequence,value=None,relation='changed',delta=None):
    return {'snapshot':{'worker_session_id':'owned-worker','epoch':0,'region':2,
        'region_size':8192,'offset':16,'length':len(raw),'game_sha256':'a'*64,
        'core_sha256':'b'*64,'core_options':{},'sequence':sequence,
        'raw_hex':raw.hex(),'data_sha256':hashlib.sha256(raw).hexdigest()},
        'label':'Observation '+str(sequence),'value':value,
        'relation':'initial' if sequence==1 else relation,'delta':delta}


class ObservationSeriesTests(unittest.TestCase):
    def analyze(self,rows,**kwargs):
        self.assertIsNotNone(importlib.util.find_spec('romancer.observation_series'),
            'automatic multi-observation analysis is not implemented')
        from romancer.observation_series import analyze_series
        return analyze_series(rows,**kwargs)

    def test_unaligned_word_matches_three_observations_and_unchanged_control(self):
        rows=[]
        for i,v in enumerate((1000,950,950),1):
            raw=bytes([i])+v.to_bytes(2,'little')+bytes([i*3,0,0,0,0])
            rows.append(observation(raw,i,v,'unchanged' if i==3 else 'decreased'))
        result=self.analyze(rows)
        chosen=next(c for c in result['candidates'] if c['offset']==17 and c['width']==2 and c['endian']=='little' and c['encoding']=='binary')
        self.assertEqual(chosen['values'],[1000,950,950]);self.assertEqual(chosen['model'],'exact')
        self.assertEqual(result['unchanged_controls'],1)
        self.assertFalse(result['rom_location_known']);self.assertFalse(result['causation_proven'])
        self.assertFalse(result['write_authorized'])

    def test_display_bias_is_reported_rather_than_invented_as_a_named_stat(self):
        rows=[observation(bytes([v,255]),i,v-1,'unchanged' if i==3 else 'decreased') for i,v in enumerate((3,2,2),1)]
        result=self.analyze(rows)
        c=next(c for c in result['candidates'] if c['offset']==16 and c['width']==1 and c['encoding']=='binary')
        self.assertEqual(c['model'],'constant_offset');self.assertEqual(c['bias'],1)
        self.assertNotIn('health',str(result).lower())

    def test_packed_bcd_and_signed_24_bit_are_discovered_without_a_game_profile(self):
        rows=[observation(bytes([v]),i,n,'increased') for i,(v,n) in enumerate(((0x09,9),(0x10,10),(0x11,11)),1)]
        r=self.analyze(rows)
        self.assertTrue(any(c['encoding']=='packed_bcd' and c['model']=='exact' for c in r['candidates']))
        rows=[observation(v.to_bytes(3,'big',signed=True),i,v,'increased') for i,v in enumerate((-300,-299,-298),1)]
        r=self.analyze(rows)
        self.assertTrue(any(c['encoding']=='binary' and c['signed'] and c['width']==3 and c['endian']=='big' and c['model']=='exact' for c in r['candidates']))

    def test_delta_and_unchanged_constraints_reject_a_background_counter(self):
        rows=[observation(bytes([20,1]),1),observation(bytes([15,2]),2,relation='delta',delta=-5),observation(bytes([15,3]),3,relation='unchanged')]
        r=self.analyze(rows)
        self.assertTrue(any(c['offset']==16 and c['width']==1 for c in r['candidates']))
        self.assertFalse(any(c['offset']==17 for c in r['candidates']))

    def test_stable_memory_requests_a_change_instead_of_claiming_identification(self):
        r=self.analyze([observation(b'\x01\x02',1,1),observation(b'\x01\x02',2,1,'unchanged')])
        self.assertEqual(r['status'],'NEEDS_VARIATION');self.assertEqual(r['candidates'],[])

    def test_changed_bindings_old_sequence_tampered_bytes_and_bad_annotations_refuse(self):
        base=[observation(b'\x01\x02',1,1),observation(b'\x02\x03',2,2)]
        for key,value in [('epoch',1),('worker_session_id','other'),('region',0),('offset',17),('game_sha256','c'*64),('core_options',{'mode':'other'}),('sequence',1),('data_sha256','0'*64)]:
            bad=copy.deepcopy(base);bad[1]['snapshot'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.analyze(bad)
        for key,value in [('value',True),('relation','guessed'),('label','x'*121),('delta',1.5)]:
            bad=copy.deepcopy(base);bad[1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.analyze(bad)
        with self.assertRaises(ValueError):self.analyze(base[:1])
        with self.assertRaises(ValueError):self.analyze(base*17)

    def test_cancellation_and_result_budget_do_not_claim_complete_results(self):
        rows=[observation(bytes([v])*512,i,v) for i,v in enumerate((1,2,3),1)]
        r=self.analyze(rows,max_results=5)
        self.assertEqual(len(r['candidates']),5);self.assertTrue(r['truncated'])
        self.assertGreater(r['total'],5);self.assertEqual(r['coverage']['alignment'],1)
        with self.assertRaises(KeyboardInterrupt):self.analyze(rows,cancelled=lambda:True)
