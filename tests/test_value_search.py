import copy,hashlib,unittest


def snapshot(raw=b'\x01\x00\x03\x00',sequence=1):
    return {'worker_session_id':'worker','epoch':0,'region':2,'region_size':8192,'offset':16,'length':len(raw),
      'game_sha256':'a'*64,'core_sha256':'b'*64,'core_options':{},'sequence':sequence,'frame_index':sequence,
      'raw_hex':raw.hex(),'data_sha256':hashlib.sha256(raw).hexdigest()}


class ValueSearchTests(unittest.TestCase):
    def test_typed_search_and_newer_observation_narrowing(self):
        from romancer.value_search import begin_search,narrow_search
        search=begin_search(snapshot(),2,'little',False,None)
        self.assertEqual(search['offsets'],[16,18])
        narrowed=narrow_search(search,snapshot(b'\x02\x00\x03\x00',2),'increased',None)
        self.assertEqual(narrowed['offsets'],[16]);self.assertEqual(narrowed['matches'],[{'offset':16,'previous':1,'value':2}])
        exact=narrow_search(narrowed,snapshot(b'\x02\x00\x04\x00',3),'equal',2)
        self.assertEqual(exact['matches'][0]['value'],2)
        self.assertFalse(exact['rom_location_known'])

    def test_signed_endian_alignment_and_empty_result(self):
        from romancer.value_search import begin_search,narrow_search
        search=begin_search(snapshot(b'\xff\xff\x00\x03'),2,'big',True,-1)
        self.assertEqual(search['offsets'],[16])
        self.assertEqual(narrow_search(search,snapshot(b'\xff\xfe\x00\x03',2),'unchanged',None)['offsets'],[])

    def test_refuses_changed_session_epoch_options_range_hash_and_old_sequence(self):
        from romancer.value_search import begin_search,narrow_search
        search=begin_search(snapshot(),1,'little',False,None)
        for key,value in [('epoch',1),('worker_session_id','other'),('game_sha256','c'*64),('core_sha256','d'*64),('core_options',{'x':'y'}),('offset',0),('region_size',4096),('data_sha256','0'*64),('sequence',1)]:
            after=snapshot(sequence=2);after[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):narrow_search(search,after,'changed',None)
        with self.assertRaises(ValueError):begin_search(snapshot(b'\0'*4097),1,'little',False,None)
        with self.assertRaises(ValueError):begin_search(snapshot(),3,'little',False,None)
        with self.assertRaises(ValueError):begin_search(snapshot(),1,'little',False,256)
