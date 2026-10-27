from pathlib import Path
import hashlib,tempfile,unittest,os

class StudioWorkshopTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ROMANCER_STUDIO_TEST_CORE'),'Reviewed native NES core not supplied')
    def test_native_studio_draws_animates_moves_chirps_and_restores_state(self):
        from romancer.studio_workshop import make_studio_rom
        from romancer.libretro_frontend import LibretroFrontend
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'studio.nes';path.write_bytes(make_studio_rom()['data'])
            host=LibretroFrontend(os.environ['ROMANCER_STUDIO_TEST_CORE'],save_dir=root/'run')
            try:
                host.load_game(path);host.run_frames(180);before=host.memory_region('system_ram')[1]
                host.run_frames(8,['right']);self.assertGreater(host.memory_region('system_ram')[1],before)
                frames=set()
                for _ in range(32):host.run_frames(1,[]);frames.add(host.memory_region('system_ram')[0x201])
                self.assertEqual(frames,{16,20})
                host.drain_audio();host.run_frames(8,['a']);self.assertGreater(host.memory_region('system_ram')[5],0);self.assertTrue(any(host.drain_audio()['pcm_s16le']))
                raw=host.last_frame.rgb;self.assertGreater(len({raw[i:i+3] for i in range(0,len(raw),3)}),5)
                saved=host.serialize();host.run_frames(1,[]);expected=host.last_frame.sha256();host.unserialize(saved);host.run_frames(1,[]);self.assertEqual(host.last_frame.sha256(),expected)
            finally:host.close()
    def test_original_studio_has_valid_vectors_separate_edit_ranges_and_repeatable_art(self):
        from romancer.studio_workshop import make_studio_rom
        r=make_studio_rom();raw=r['data'];self.assertEqual(raw[:6],b'NES\x1a\x01\x01');self.assertEqual(len(raw),24592)
        self.assertEqual(int.from_bytes(raw[16+16384-4:16+16384-2],'little'),0x8000)
        self.assertEqual(raw[r['stats_offset']:r['stats_offset']+3],bytes([2,1,128]))
        self.assertEqual(raw[r['spawn_offset']:r['spawn_offset']+4],bytes([5,22,23,22]))
        self.assertNotEqual(raw[r['graphics_offset']:r['graphics_offset']+64],raw[r['graphics_offset']+64:r['graphics_offset']+128])
        self.assertEqual(hashlib.sha256(raw).digest(),hashlib.sha256(make_studio_rom()['data']).digest())
    def test_workshop_opens_real_graphics_text_numbers_and_level_definitions(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.research_tools import _definition
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'work')
            try:
                p=api.dispatch('project.studio',{});self.assertTrue(p['ok'],p);row=p['sources'][0]
                for kind in ('assets','script','tables','levels'):
                    self.assertTrue(_definition(row,Path(row['path']),kind),kind)
                sp={'project_id':p['project_id'],'artifact_id':row['artifact_id']}
                ready=api.dispatch('editing.readiness',sp);self.assertEqual(sum(a['status']=='ready' for a in ready['areas']),4)
                self.assertIn('Mossy Hollow',p['name']);self.assertTrue(p['original_workshop'])
            finally:api.close()

    def test_studio_definitions_limit_movement_to_the_play_area_and_safe_speed_range(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'work')
            try:
                p=api.dispatch('project.studio',{});row=p['sources'][0];sp={'project_id':p['project_id'],'artifact_id':row['artifact_id']}
                definition=row['descriptors']['tables']['definition'];doc=api.dispatch('tables.inspect',{**sp,'definition':definition,'page':0,'limit':1})
                for value,allowed in ((8,True),(9,False),(255,False)):
                    result=api.dispatch('tables.plan',{**sp,'definition':definition,'document_id':doc['document_id'],'changes':[{'row':0,'field':'Hero speed','before':2,'after':value}]})
                    self.assertEqual(result['ok'],allowed,result)
                level=row['descriptors']['levels'];doc=api.dispatch('levels.inspect',{**sp,'definition':level})
                result=api.dispatch('levels.plan',{**sp,'definition':level,'document_id':doc['document_id'],'changes':[{'kind':'object','room_id':'hollow','index':0,'field':'x','value':29}]})
                self.assertFalse(result['ok'],result)
            finally:api.close()
