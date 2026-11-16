import copy
import unittest
from romancer import scene_schema
from romancer.level_design import inspect_level,plan_level
from tests.test_level_design import fixture


class SceneSchemaTests(unittest.TestCase):
    def fixture(self):
        raw,d,sha=fixture();raw=bytearray(raw)
        raw[192:208]=bytes([1,2,1,0,2,0,0,0,2,0,0,0,1,0,0,0])
        raw[224:230]=bytes([0,1,0,2,0,1])
        import hashlib
        raw=bytes(raw);sha=hashlib.sha256(raw).hexdigest();d['source_sha256']=sha
        d['scene']={'projection':'isometric','tile_width':32,'tile_height':16,'elevation_step':8,
                    'object_fields':{'z':'z','layer':None,'order':None}}
        room=d['rooms'][0];room['elevation']={'offset':224,'entry_bytes':1,'endian':'little'}
        room['objects']['stride']=8
        room['objects']['fields'].append({'name':'z','offset':4,'bytes':1,'endian':'little','maximum':16})
        return raw,d,sha

    def test_declared_projection_height_and_object_fields_are_source_bound(self):
        raw,d,sha=self.fixture();doc=inspect_level(raw,d,sha)
        self.assertEqual(doc['scene']['projection'],'isometric')
        self.assertEqual(doc['rooms'][0]['elevation'],[0,1,0,2,0,1])
        self.assertEqual(doc['rooms'][0]['objects'][0]['z'],2)
        self.assertFalse(doc['game_semantics_verified'])
        plan=plan_level(raw,d,doc['document_id'],[
            {'kind':'elevation','room_id':'room-0','index':1,'value':2},
            {'kind':'object','room_id':'room-0','index':0,'field':'z','value':3}],sha)
        self.assertEqual(plan['edits'],[{'offset':196,'before':'02','after':'03'},
                                       {'offset':225,'before':'01','after':'02'}])
        d['scene']['projection']='orthogonal'
        with self.assertRaisesRegex(ValueError,'stale'):plan_level(raw,d,doc['document_id'],[
            {'kind':'elevation','room_id':'room-0','index':1,'value':2}],sha)

    def test_legacy_definitions_stay_orthogonal_and_do_not_infer_height(self):
        raw,d,sha=fixture();doc=inspect_level(raw,d,sha)
        self.assertEqual(doc['scene']['projection'],'orthogonal')
        self.assertIsNone(doc['rooms'][0]['elevation'])
        self.assertEqual(doc['scene']['object_fields'],{'z':None,'layer':None,'order':None})

    def test_projection_has_exact_inverse_only_at_a_known_height(self):
        spec={'projection':'isometric','tile_width':32,'tile_height':16,'elevation_step':8,
              'object_fields':{'z':None,'layer':None,'order':None}}
        spec=scene_schema.normalize_scene(spec,16,16)
        point=scene_schema.project_point(spec,3,1,2)
        self.assertEqual(point,(32,16))
        self.assertEqual(scene_schema.inverse_at_z(spec,*point,2),(3,1))
        self.assertEqual(scene_schema.inverse_at_z(spec,*point,0),(2,0))
        self.assertEqual(scene_schema.project_point(spec,-2,3,1),(-80,0))
        with self.assertRaises(ValueError):scene_schema.inverse_at_z(spec,*point,None)

    def test_invalid_geometry_bindings_storage_and_pixel_budget_are_rejected(self):
        for mutate in [lambda d:d['scene'].update(projection='unknown'),
                       lambda d:d['scene'].update(tile_width=True),
                       lambda d:d['scene'].update(tile_height=0),
                       lambda d:d['scene']['object_fields'].update(z='missing'),
                       lambda d:d['rooms'][0]['elevation'].update(offset=192),
                       lambda d:d['scene'].update(elevation_step=4096)]:
            raw,d,sha=self.fixture();mutate(d)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):inspect_level(raw,d,sha)
        for bad in [True,float('inf'),float('nan')]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                scene_schema.project_point(scene_schema.normalize_scene(None,16,16),bad,0,0)

    def test_height_changes_preserve_storage_bounds(self):
        raw,d,sha=self.fixture();doc=inspect_level(raw,d,sha)
        for value in [-1,256,True]:
            with self.subTest(value=value),self.assertRaises(ValueError):plan_level(raw,d,doc['document_id'],[
                {'kind':'elevation','room_id':'room-0','index':0,'value':value}],sha)

    def test_connected_view_includes_explicit_height_storage(self):
        from romancer.studio_discovery import resource_relationships
        raw,d,sha=self.fixture();graph=resource_relationships(raw,{'levels':d},sha)
        self.assertIn({'from':'level:room-0 elevation','to':'level:room-0 terrain','relation':'declared terrain height'},graph['edges'])
