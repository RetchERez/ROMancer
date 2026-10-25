import copy,hashlib,unittest


def fixture():
    raw=bytearray(2048)
    raw[0:32]=bytes([0xFF,0]*8+[0,0xFF]*8)
    raw[32:44]=bytes([12,20,30,220,60,40,80,220,140,240,220,160])
    raw[64:72]=bytes([0,1,1,0,1,0,0,1])
    raw[128:134]=bytes([0,1,0,1,0,1]);raw[160:166]=bytes([0,1,2,3,0,1])
    raw[192:200]=bytes([1,2,1,0,2,0,0,0])
    sha=hashlib.sha256(raw).hexdigest()
    definition={'schema_version':1,'source_sha256':sha,'name':'Test rooms',
      'tiles':{'offset':0,'count':2,'codec':'tile8-paired2-msb-v1','palette_offset':32,'palette_format':'rgb888'},
      'metatiles':{'offset':64,'count':2,'width':2,'height':2,'entry_bytes':1,'endian':'little'},
      'rooms':[{'id':'room-0','name':'First room','width':3,'height':2,
       'terrain':{'offset':128,'entry_bytes':1,'endian':'little'},'collision':{'offset':160,'entry_bytes':1,'endian':'little'},
       'objects':{'offset':192,'count':2,'stride':4,'fields':[{'name':'kind','offset':0,'bytes':1,'endian':'little','maximum':8},{'name':'x','offset':1,'bytes':1,'endian':'little','maximum':2},{'name':'y','offset':2,'bytes':1,'endian':'little','maximum':1},{'name':'exit_room','offset':3,'bytes':1,'endian':'little','maximum':0}]}}]}
    return bytes(raw),definition,sha


class LevelDesignTests(unittest.TestCase):
    def inspect(self):
        from romancer.level_design import inspect_level
        return inspect_level(*fixture())

    def test_decodes_room_layers_blocks_objects_and_shared_uses(self):
        doc=self.inspect()
        self.assertEqual(doc['rooms'][0]['terrain'],[0,1,0,1,0,1])
        self.assertEqual(doc['rooms'][0]['objects'][0],{'kind':1,'x':2,'y':1,'exit_room':0})
        self.assertEqual(doc['metatiles'][1],[1,0,0,1])
        self.assertEqual(doc['uses']['0'],[{'room_id':'room-0','cell':0},{'room_id':'room-0','cell':2},{'room_id':'room-0','cell':4}])
        self.assertFalse(doc['game_semantics_verified'])

    def test_plans_exact_layer_block_and_object_bytes(self):
        from romancer.level_design import plan_level
        raw,d,sha=fixture();doc=self.inspect()
        result=plan_level(raw,d,doc['document_id'],[
          {'kind':'terrain','room_id':'room-0','index':1,'value':0},
          {'kind':'collision','room_id':'room-0','index':2,'value':4},
          {'kind':'metatile','index':0,'part':1,'value':0},
          {'kind':'object','room_id':'room-0','index':0,'field':'x','value':1}],sha)
        self.assertEqual(result['edits'],[{'offset':65,'before':'01','after':'00'},{'offset':129,'before':'01','after':'00'},{'offset':162,'before':'02','after':'04'},{'offset':193,'before':'02','after':'01'}])
        self.assertEqual(result['affected_rooms'],['room-0'])
        self.assertEqual(raw,fixture()[0])

    def test_refuses_overlapping_storage_and_object_fields(self):
        from romancer.level_design import inspect_level
        raw,d,sha=fixture();d['rooms'][0]['collision']['offset']=130
        with self.assertRaisesRegex(ValueError,'overlap'):inspect_level(raw,d,sha)
        raw,d,sha=fixture();d['rooms'][0]['objects']['fields'][1]['offset']=0
        with self.assertRaisesRegex(ValueError,'overlap'):inspect_level(raw,d,sha)

    def test_refuses_stale_source_and_review(self):
        from romancer.level_design import inspect_level,plan_level
        raw,d,sha=fixture()
        with self.assertRaisesRegex(ValueError,'source'):inspect_level(raw,d,'0'*64)
        with self.assertRaisesRegex(ValueError,'review|document'):plan_level(raw,d,'old',[],sha)

    def test_refuses_out_of_range_tiles_cells_objects_and_exits(self):
        from romancer.level_design import plan_level
        raw,d,sha=fixture();doc=self.inspect()
        for change in [
          {'kind':'terrain','room_id':'room-0','index':6,'value':0},
          {'kind':'terrain','room_id':'room-0','index':0,'value':2},
          {'kind':'metatile','index':0,'part':4,'value':0},
          {'kind':'object','room_id':'room-0','index':0,'field':'x','value':3},
          {'kind':'object','room_id':'room-0','index':0,'field':'exit_room','value':1}]:
            with self.subTest(change=change),self.assertRaises(ValueError):plan_level(raw,d,doc['document_id'],[change],sha)

    def test_refuses_conflicting_duplicate_edits_and_bad_existing_indices(self):
        from romancer.level_design import plan_level,inspect_level
        raw,d,sha=fixture();doc=self.inspect();c={'kind':'terrain','room_id':'room-0','index':0,'value':1}
        with self.assertRaisesRegex(ValueError,'duplicate'):plan_level(raw,d,doc['document_id'],[c,c],sha)
        bad=bytearray(raw);bad[128]=3;sha=hashlib.sha256(bad).hexdigest();d['source_sha256']=sha
        with self.assertRaises(ValueError):inspect_level(bytes(bad),d,sha)

    def test_budgets_reject_empty_or_oversized_maps_before_decoding(self):
        from romancer.level_design import inspect_level
        raw,d,sha=fixture()
        for width in (0,10000):
            with self.subTest(width=width),self.assertRaises(ValueError):
                bad=copy.deepcopy(d);bad['rooms'][0]['width']=width;inspect_level(raw,bad,sha)

    def test_combined_document_budget_refuses_oversized_decoded_response(self):
        from romancer.level_design import inspect_level
        raw=bytes(200000);sha=hashlib.sha256(raw).hexdigest();d=fixture()[1]
        d['source_sha256']=sha
        d['tiles'].update(count=1024,palette_offset=16384)
        d['metatiles'].update(offset=16416,count=1024)
        d['rooms'][0].update(width=128,height=128,objects=None,
          terrain={'offset':22000,'entry_bytes':1,'endian':'little'},
          collision={'offset':40000,'entry_bytes':1,'endian':'little'})
        with self.assertRaisesRegex(ValueError,'preview budget'):
            inspect_level(raw,d,sha)

    def test_malformed_definitions_and_changes_are_actionable_refusals(self):
        from romancer.level_design import inspect_level,plan_level
        raw,d,sha=fixture();doc=self.inspect()
        for malformed in (None,[],42):
            with self.subTest(definition=malformed),self.assertRaisesRegex(ValueError,'definition'):
                inspect_level(raw,malformed,sha)
        with self.assertRaisesRegex(ValueError,'change'):
            plan_level(raw,d,doc['document_id'],[None],sha)
