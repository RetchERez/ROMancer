import hashlib
import importlib.util
import unittest

class WatchTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.memory_watches'),'saved watches missing')
        from romancer import memory_watches
        return memory_watches

    def snapshot(self,raw,sequence):
        return {'worker_session_id':'a'*32,'epoch':0,'sequence':sequence,'region':2,'region_size':1024,'offset':4,'length':len(raw),'raw_hex':raw.hex(),'data_sha256':hashlib.sha256(raw).hexdigest(),'game_sha256':'b'*64,'core_sha256':'c'*64,'core_options':{}}

    def test_literal_before_after_and_session_bound_comparison(self):
        service=self.service();before=self.snapshot(b'\x01\x02',1);after=self.snapshot(b'\x03\x02',2)
        result=service.compare_watch(before,after)
        self.assertEqual(result['changes'],[{'offset':4,'before':1,'after':3}]);self.assertFalse(result['write_event_observed'])
        for mutation in ({'worker_session_id':'d'*32},{'epoch':1},{'offset':5},{'raw_hex':'ffff'},{'sequence':1}):
            with self.assertRaises(ValueError):service.compare_watch(before,{**after,**mutation})

    def test_changed_memory_extent_or_core_options_refuses_comparison(self):
        service=self.service();before=self.snapshot(b'\x01',1);after=self.snapshot(b'\x02',2)
        for mutation in ({'region_size':2048},{'core_options':{'mode':'other'}}):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):service.compare_watch(before,{**after,**mutation})

    def test_watch_definition_bounds(self):
        service=self.service();watch={'name':'Lives','region':2,'offset':4,'length':2}
        self.assertEqual(service.validate_watches([watch]),[watch])
        for mutation in ({'length':4097},{'region':9},{'path':'C:/private'},{'offset':True}):
            with self.assertRaises(ValueError):service.validate_watches([{**watch,**mutation}])

if __name__=='__main__':unittest.main()
