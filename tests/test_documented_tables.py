import hashlib,unittest


class DocumentedTablesTests(unittest.TestCase):
    def module(self):
        from romancer import documented_tables
        return documented_tables

    def fixture(self):
        raw=bytearray(16384)
        for i in range(151):raw[4096+i*28:4096+i*28+10]=bytes([50,50,50,50,50,50,12,3,45,64])
        for i,row in enumerate(([45,49,49,45,65,65,12,3],[60,62,63,60,80,80,12,3],[80,82,83,80,100,100,12,3])):
            raw[4096+i*28:4096+i*28+8]=bytes(row)
        return bytes(raw)

    def test_locates_relocated_documented_stat_pattern_and_names_all151_without_claiming_a_game_revision(self):
        raw=self.fixture();sha=hashlib.sha256(raw).hexdigest();r=self.module().scan(raw,sha,'gba')
        self.assertEqual(len(r['candidates']),1);found=r['candidates'][0]
        self.assertEqual((found['offset'],found['count'],found['stride']),(4096,151,28))
        self.assertFalse(found['exact_revision']);self.assertFalse(r['write_authorized'])
        d=self.module().definition(raw,sha,'gba',found['candidate_id'])
        self.assertEqual(d['row_names'][:3],['Bulbasaur','Ivysaur','Venusaur'])
        self.assertEqual(len(d['row_names']),151)
        self.assertEqual(d['fields'][0]['name'],'HP')

    def test_wrong_system_broken_record_bounds_and_stale_candidate_are_refused(self):
        m=self.module();raw=self.fixture();sha=hashlib.sha256(raw).hexdigest()
        self.assertEqual(m.scan(raw,sha,'nes')['candidates'],[])
        bad=bytearray(raw);bad[4096+100*28]=0;bad=bytes(bad)
        self.assertEqual(m.scan(bad,hashlib.sha256(bad).hexdigest(),'gba')['candidates'],[])
        with self.assertRaises(ValueError):m.scan(raw,'0'*64,'gba')
        with self.assertRaises(ValueError):m.definition(raw,sha,'gba','0'*64)
        short=raw[:4096+100*28];self.assertEqual(m.scan(short,hashlib.sha256(short).hexdigest(),'gba')['candidates'],[])

    def test_readable_record_names_are_checked_and_do_not_change_numeric_bytes(self):
        import tempfile
        from pathlib import Path
        from romancer.data_tables import inspect_table,table_edits,validate_definition
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'source';p.write_bytes(b'\x2d\x3c');sha=hashlib.sha256(p.read_bytes()).hexdigest()
            d={'schema_version':1,'name':'Original example','offset':0,'count':2,'stride':1,'row_names':['First','Second'],'row_id_base':1,
               'fields':[{'name':'HP','offset':0,'type':'u8','endian':'little','pointer_base':None}]}
            doc=inspect_table(p,sha,d);self.assertEqual(doc['rows'][0]['label'],'First');self.assertEqual(doc['rows'][1]['record_id'],2)
            self.assertEqual(table_edits(p,sha,d,[{'row':0,'field':'HP','before':45,'after':55}]),[{'offset':0,'before':'2d','after':'37'}])
            with self.assertRaises(ValueError):validate_definition({**d,'row_names':['Only one']},2)

    def test_move_layout_checks_all_records_and_preserves_effect_bytes(self):
        raw=bytearray(8192)
        for i in range(165):raw[1024+i*12:1024+i*12+8]=bytes([7,20,0,100,30,0,0,255])
        for i,marker in enumerate(self.module().MOVE_MARKERS):raw[1025+i*12:1025+i*12+4]=marker
        raw=bytes(raw);sha=hashlib.sha256(raw).hexdigest();found=self.module().scan(raw,sha,'gba')['candidates'][0]
        self.assertEqual(found['kind'],'moves');self.assertEqual(found['offset'],1024)
        d=self.module().definition(raw,sha,'gba',found['candidate_id']);self.assertEqual(d['row_names'][:3],['Pound','Karate Chop','Double Slap'])
        self.assertFalse(any(f['offset']==0 for f in d['fields']))
        bad=bytearray(raw);bad[1024+100*12+4]=0;bad=bytes(bad)
        self.assertEqual(self.module().scan(bad,hashlib.sha256(bad).hexdigest(),'gba')['candidates'],[])
