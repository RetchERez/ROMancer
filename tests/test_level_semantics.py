import copy,hashlib,unittest
from tests.test_level_design import fixture
from romancer.level_design import inspect_level,plan_level

def semantic_fixture():
 raw,d,_=fixture();raw=bytearray(raw);raw[192:208]=bytes([1,1,0,0,12,14,0,0]*2)
 room=d['rooms'][0];room['collision_types']=[{'value':0,'name':'Clear floor','kind':'walkable','color':[25,130,95]},{'value':1,'name':'Wall','kind':'solid','color':[180,60,70]},{'value':2,'name':'Spikes','kind':'hazard','color':[215,155,30]}]
 room['objects']={'offset':192,'count':2,'stride':8,'fields':[{'name':name,'offset':i,'bytes':1,'endian':'little','maximum':(2 if name=='x' else 1 if name=='y' else 32),**({'minimum':1} if name in ('width','height') else {})} for i,name in enumerate(['x','y','box_x','box_y','width','height'])]}
 room['object_metadata']=[{'index':0,'name':'Hero','role':'actor','reference':None,'hitbox':{'offset_x':'box_x','offset_y':'box_y','width':'width','height':'height'}}]
 sha=hashlib.sha256(raw).hexdigest();d['source_sha256']=sha;return bytes(raw),d,sha

class LevelSemanticsTests(unittest.TestCase):
 def test_starting_sprite_is_declared_with_bounded_tiles_and_transparency(self):
  raw,d,sha=semantic_fixture();meta=d['rooms'][0]['object_metadata'][0];meta['sprite']={'tiles':[1],'width':1,'height':1,'transparent_index':0}
  self.assertEqual(inspect_level(raw,d,sha)['rooms'][0]['object_metadata'][0]['sprite']['tiles'],[1])
  for sprite in ({'tiles':[2],'width':1,'height':1,'transparent_index':0},{'tiles':[1],'width':2,'height':1,'transparent_index':0},{'tiles':[1],'width':1,'height':1,'transparent_index':4}):
   meta['sprite']=sprite
   with self.assertRaises(ValueError):inspect_level(raw,d,sha)
 def test_collision_names_and_hitbox_fields_are_validated_declarations(self):
  raw,d,sha=semantic_fixture();doc=inspect_level(raw,d,sha)
  self.assertEqual(doc['rooms'][0]['collision_types'][1]['name'],'Wall');self.assertFalse(doc['game_semantics_verified'])
  self.assertEqual(doc['rooms'][0]['object_metadata'][0]['hitbox']['width'],'width')
  result=plan_level(raw,d,doc['document_id'],[{'kind':'collision','room_id':'room-0','index':1,'value':0},{'kind':'object','room_id':'room-0','index':0,'field':'width','value':6}],sha)
  self.assertEqual(result['edits'],[{'offset':161,'before':'01','after':'00'},{'offset':196,'before':'0c','after':'06'}]);self.assertEqual(raw[196],12)
 def test_unknown_values_remain_raw_and_metadata_does_not_require_total_mapping(self):
  raw,d,sha=semantic_fixture();doc=inspect_level(raw,d,sha);self.assertEqual(doc['rooms'][0]['collision'][3],3)
  p=plan_level(raw,d,doc['document_id'],[{'kind':'collision','room_id':'room-0','index':0,'value':255}],sha);self.assertEqual(p['edits'][0]['after'],'ff')
 def test_bad_labels_colors_values_and_missing_collision_grid_are_refused(self):
  raw,d,sha=semantic_fixture()
  for mutate in [lambda r:r['collision_types'].append(r['collision_types'][0]),lambda r:r['collision_types'][0].update(value=256),lambda r:r['collision_types'][0].update(kind='invented'),lambda r:r['collision_types'][0].update(color=[True,0,0]),lambda r:r.update(collision=None),lambda r:r['collision_types'][0].update(runtime_verified=True)]:
   bad=copy.deepcopy(d);mutate(bad['rooms'][0])
   with self.subTest(definition=bad),self.assertRaises(ValueError):inspect_level(raw,bad,sha)
 def test_missing_or_zero_size_hitbox_and_object_minimum_are_refused(self):
  raw,d,sha=semantic_fixture();doc=inspect_level(raw,d,sha)
  bad=copy.deepcopy(d);bad['rooms'][0]['object_metadata'][0]['hitbox']['width']='missing'
  with self.assertRaises(ValueError):inspect_level(raw,bad,sha)
  for value in (0,33):
   with self.subTest(value=value),self.assertRaises(ValueError):plan_level(raw,d,doc['document_id'],[{'kind':'object','room_id':'room-0','index':0,'field':'width','value':value}],sha)
 def test_old_definitions_remain_compatible(self):
  raw,d,sha=fixture();doc=inspect_level(raw,d,sha);self.assertEqual(doc['rooms'][0]['collision_types'],[])
