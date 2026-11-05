from pathlib import Path
import hashlib,os,tempfile,unittest

class StudioRuntimeTests(unittest.TestCase):
 def test_legacy_source_remains_exactly_regenerable(self):
  from romancer.studio_workshop import make_studio_rom
  self.assertEqual(hashlib.sha256(make_studio_rom()['data']).hexdigest(),'95e0efbc4bc1b408f43da0f2f8b39874b0d4578eb65b1ec3e4890f6ed743ab1b')
 def test_new_source_has_separate_collision_actor_and_music_ranges(self):
  from romancer.studio_runtime import make_collision_studio_rom,runtime_definitions
  from romancer.level_design import inspect_level
  r=make_collision_studio_rom();sha=hashlib.sha256(r['data']).hexdigest();d=runtime_definitions(r,sha)
  doc=inspect_level(r['data'],d['levels'],sha);room=doc['rooms'][0]
  self.assertEqual(room['collision'][22*32+16],1);self.assertEqual(room['collision_types'][0]['kind'],'walkable')
  self.assertEqual(room['objects'][0]['width'],12);self.assertEqual(room['objects'][1]['contact_damage'],1)
  self.assertEqual(room['object_metadata'][1]['hitbox']['height'],'height');self.assertNotEqual(sha,'95e0efbc4bc1b408f43da0f2f8b39874b0d4578eb65b1ec3e4890f6ed743ab1b')
  self.assertEqual(r['data'],make_collision_studio_rom()['data'])
 def test_checked_engine_identity_does_not_cover_replaced_code(self):
  from romancer.studio_runtime import make_collision_studio_rom,matches_studio_runtime
  raw=make_collision_studio_rom()['data'];self.assertTrue(matches_studio_runtime(raw))
  broken=bytearray(raw);broken[16]^=1;self.assertFalse(matches_studio_runtime(bytes(broken)))
  broken=bytearray(raw);broken[16396]^=1;self.assertFalse(matches_studio_runtime(bytes(broken)),'A changed reset vector cannot identify the original executable runtime.')
  changed=bytearray(raw);changed[0x2010]^=1;self.assertTrue(matches_studio_runtime(bytes(changed)),'Editable data does not change the checked immutable engine signature.')
 def test_original_melody_is_inspectable_editable_and_previewed(self):
  from romancer.studio_runtime import make_collision_studio_rom,runtime_definitions
  from romancer.sound_studio import inspect_sound,plan_sound,preview_sound
  r=make_collision_studio_rom();sha=hashlib.sha256(r['data']).hexdigest();d=runtime_definitions(r,sha)['sound'];doc=inspect_sound(r['data'],d,sha)
  changes=[{'kind':'note','song_id':'hollow-theme','index':0,'field':'note','value':72}]
  plan=plan_sound(r['data'],d,doc['document_id'],changes,sha);self.assertEqual(plan['edits'],[{'offset':0x1b10,'before':'3c','after':'48'}])
  before,_=preview_sound(r['data'],d,sha,'song','hollow-theme');after,meta=preview_sound(r['data'],d,sha,'song','hollow-theme',changes)
  self.assertNotEqual(before,after);self.assertIn('Reference',meta['preview_scope'])
 def test_original_actor_bounds_and_patrol_are_checked_together_before_build(self):
  from romancer.studio_runtime import make_collision_studio_rom,runtime_definitions
  from romancer.level_design import inspect_level,plan_level
  r=make_collision_studio_rom();sha=hashlib.sha256(r['data']).hexdigest();d=runtime_definitions(r,sha)['levels'];doc=inspect_level(r['data'],d,sha)
  for field,value in [('patrol_left',28),('y',29)]:
   with self.subTest(field=field),self.assertRaises(ValueError):plan_level(r['data'],d,doc['document_id'],[{'kind':'object','room_id':'hollow','index':1,'field':field,'value':value}],sha)
 def test_imported_original_runtime_recovers_checked_level_and_music_layouts(self):
  from romancer.studio_runtime import make_collision_studio_rom
  from romancer.workbench_api import WorkbenchAPI
  with tempfile.TemporaryDirectory() as temp:
   api=WorkbenchAPI(Path(temp)/'work')
   try:
    project=api.dispatch('project.create',{'name':'Reimport original studio'});path=Path(temp)/'original.nes';path.write_bytes(make_collision_studio_rom()['data']);result=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(path),'system':None});self.assertTrue(result['ok'],result)
    self.assertIn('levels',result.get('descriptors',{}));self.assertIn('sound',result['descriptors'])
   finally:api.close()

@unittest.skipUnless(os.environ.get('ROMANCER_STUDIO_TEST_CORE'),'Reviewed native NES core not supplied')
class NativeStudioRuntimeTests(unittest.TestCase):
 def run_scene(self,path,frames,buttons):
  from romancer.libretro_frontend import LibretroFrontend
  with tempfile.TemporaryDirectory() as temp:
   host=LibretroFrontend(os.environ['ROMANCER_STUDIO_TEST_CORE'],save_dir=Path(temp))
   try:
    host.load_game(path);host.run_frames(180);host.run_frames(frames,buttons);ram=host.memory_region('system_ram');return {'x':ram[1],'y':ram[6],'hp':ram[8],'enemy_x':ram[2],'frame':host.last_frame.sha256()}
   finally:host.close()
 def checked(self,api,op,p):
  result=api.dispatch(op,p);self.assertTrue(result['ok'],result);return result
 def build(self,api,p,source,changes):
  sp={**p,'artifact_id':source['artifact_id']};d=source['descriptors']['levels'];doc=self.checked(api,'levels.inspect',{**sp,'definition':d});plan=self.checked(api,'levels.plan',{**sp,'definition':d,'document_id':doc['document_id'],'changes':changes});return self.checked(api,'build.apply',{**p,'plan_id':plan['plan_id']})
 def test_painted_opening_really_changes_native_collision(self):
  from romancer.workbench_api import WorkbenchAPI
  with tempfile.TemporaryDirectory() as temp:
   api=WorkbenchAPI(Path(temp)/'work')
   try:
    project=self.checked(api,'project.studio',{});p={'project_id':project['project_id']};source=project['sources'][0];before=Path(source['path']).read_bytes()
    original=self.run_scene(source['path'],100,['right']);self.assertEqual(original['x'],114)
    changed=self.build(api,p,source,[{'kind':'collision','room_id':'hollow','index':y*32+16,'value':0} for y in range(18,24)])
    opened=self.run_scene(changed['path'],100,['right']);self.assertGreater(opened['x'],original['x']+32);self.assertEqual(Path(source['path']).read_bytes(),before)
   finally:api.close()
 def test_actor_rectangles_affect_actual_contact_damage_separately_from_art(self):
  from romancer.workbench_api import WorkbenchAPI
  with tempfile.TemporaryDirectory() as temp:
   api=WorkbenchAPI(Path(temp)/'work')
   try:
    project=self.checked(api,'project.studio',{});p={'project_id':project['project_id']};source=project['sources'][0]
    actor=lambda field,value:{'kind':'object','room_id':'hollow','index':1,'field':field,'value':value}
    base=[actor('x',12),actor('ai_enabled',0)]
    wide=self.build(api,p,source,base);narrow=self.build(api,p,source,base+[actor('offset_x',7),actor('width',1)])
    first=self.run_scene(wide['path'],22,['right']);second=self.run_scene(narrow['path'],22,['right']);self.assertLess(first['hp'],second['hp']);self.assertEqual(second['hp'],5)
   finally:api.close()


def setUpModule():
    # Exercise preserved development internals separately from the release boundary.
    from unittest import addModuleCleanup
    from unittest.mock import patch
    feature = patch("romancer.release_scope.LEVEL_EDITOR_ENABLED", True)
    feature.start()
    addModuleCleanup(feature.stop)
