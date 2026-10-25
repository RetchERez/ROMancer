import copy,hashlib,tempfile,unittest
from pathlib import Path
from romancer.workbench_api import WorkbenchAPI
from romancer.boot_fixtures import make_boot_fixture
from tests.test_level_design import fixture


class StudioAPITests(unittest.TestCase):
    def test_value_search_uses_owned_observations_and_rejects_epoch_changes(self):
        from tests.test_value_search import snapshot
        import threading
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'workspace');pool=api.runtime
            try:
                example=api.dispatch('studio.example',{});p={'project_id':example['project_id']};source=api.dispatch('project.open',p)['sources'][0];s={**p,'artifact_id':source['artifact_id']}
                packets=[snapshot(sequence=1),snapshot(b'\x02\x00\x03\x00',2),{**snapshot(sequence=3),'epoch':1}]
                for packet in packets:packet['game_sha256']=source['sha256']
                def request(project,operation,parameters,**kwargs):
                    self.assertEqual(operation,'read_memory');self.assertEqual(parameters,{'region':2,'offset':16,'length':4});return packets.pop(0)
                api.runtime=SimpleNamespace(lock=threading.RLock(),session_selection=lambda _: {'id':source['artifact_id'],'sha256':source['sha256']},request=request)
                started=api.dispatch('values.start',{**s,'region':2,'offset':16,'length':4,'width':2,'endian':'little','signed':False,'target':None})
                self.assertTrue(started['ok'],started);self.assertEqual(started['total'],2)
                narrowed=api.dispatch('values.narrow',{**s,'search_id':started['search_id'],'relation':'increased','target':None})
                self.assertTrue(narrowed['ok'],narrowed);self.assertEqual(narrowed['matches'][0]['offset'],16)
                changed=api.dispatch('values.narrow',{**s,'search_id':started['search_id'],'relation':'changed','target':None})
                self.assertFalse(changed['ok']);self.assertIn('session',changed['error'])
            finally:api.runtime=pool;api.close()

    def test_reusing_parent_setup_validates_level_and_audio_for_separate_build(self):
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'workspace')
            try:
                example=api.dispatch('studio.example',{});p={'project_id':example['project_id']};source=api.dispatch('project.open',p)['sources'][0];s={**p,'artifact_id':source['artifact_id']}
                definition=source['descriptors']['levels'];doc=api.dispatch('levels.inspect',{**s,'definition':definition})
                plan=api.dispatch('levels.plan',{**s,'definition':definition,'document_id':doc['document_id'],'changes':[{'kind':'terrain','room_id':'hillside','index':0,'value':3}]})
                build=api.dispatch('build.apply',{**p,'plan_id':plan['plan_id']});self.assertTrue(build['ok'],build)
                reused=api.dispatch('resources.reuse_definitions',{**p,'artifact_id':build['artifact_id']});self.assertTrue(reused['ok'],reused)
                self.assertEqual(set(build['resource_setup']['reused']),{'levels','sound'});self.assertEqual(reused['reused'],[])
                opened=api.dispatch('project.open',p)['builds'][0]
                self.assertEqual(opened['descriptors']['levels']['source_sha256'],build['sha256'])
                self.assertTrue(api.dispatch('sound.system',{**p,'artifact_id':build['artifact_id']})['sequence_edit_supported'])
            finally:api.close()
    def test_sound_system_and_preview_endpoints_use_real_decoded_data(self):
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'workspace')
            try:
                example=api.dispatch('studio.example',{});p={'project_id':example['project_id']};source=api.dispatch('project.open',p)['sources'][0];s={**p,'artifact_id':source['artifact_id']}
                hardware=api.dispatch('sound.system',s);self.assertTrue(hardware['ok'],hardware);self.assertEqual(hardware['hardware']['nominal_channels'],5)
                d=source['descriptors']['sound'];doc=api.dispatch('sound.inspect',{**s,'definition':d});self.assertTrue(doc['ok'],doc)
                preview=api.dispatch('sound.preview',{**s,'definition':d,'kind':'song','resource_id':'hillside','changes':[]});self.assertTrue(preview['ok'],preview)
                import base64,io,wave
                with wave.open(io.BytesIO(base64.b64decode(preview['wav_base64']))):pass
                planned=api.dispatch('sound.plan',{**s,'definition':d,'document_id':doc['document_id'],'changes':[{'kind':'note','song_id':'hillside','index':0,'field':'note','value':64}]});self.assertTrue(planned['ok'],planned);self.assertTrue(planned['integrity_planned'])
                before=Path(source['path']).read_bytes();built=api.dispatch('build.apply',{**p,'plan_id':planned['plan_id']});self.assertTrue(built['ok'],built);after=Path(built['path']).read_bytes()
                self.assertEqual([i for i,(a,b) in enumerate(zip(before,after)) if a!=b],[0x3810])
            finally:api.close()

    def test_level_definition_review_and_checksum_aware_build_preserve_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);api=WorkbenchAPI(root/'workspace')
            try:
                raw=bytearray(make_boot_fixture('nes')['data']);data,d,_=fixture();raw[0x2000:0x2800]=data
                for g in [d['tiles'],d['metatiles'],d['rooms'][0]['terrain'],d['rooms'][0]['collision'],d['rooms'][0]['objects']]:g['offset']+=0x2000
                d['tiles']['palette_offset']+=0x2000;d['source_sha256']=hashlib.sha256(raw).hexdigest()
                path=root/'original.nes';path.write_bytes(raw);project=api.dispatch('project.create',{'name':'Level test'});p={'project_id':project['project_id']}
                source=api.dispatch('source.import',{**p,'path':str(path),'system':None});s={**p,'artifact_id':source['artifact_id']}
                saved=api.dispatch('studio.definition',{**s,'kind':'levels','definition':d});self.assertTrue(saved['ok'],saved)
                doc=api.dispatch('levels.inspect',{**s,'definition':d});self.assertTrue(doc['ok'],doc)
                planned=api.dispatch('levels.plan',{**s,'definition':d,'document_id':doc['document_id'],'changes':[{'kind':'terrain','room_id':'room-0','index':0,'value':1}]});self.assertTrue(planned['ok'],planned)
                self.assertTrue(planned['integrity_planned']);built=api.dispatch('build.apply',{**p,'plan_id':planned['plan_id']});self.assertTrue(built['ok'],built)
                expected=bytearray(raw);expected[0x2080]=1;self.assertEqual(Path(built['path']).read_bytes(),bytes(expected));self.assertEqual(path.read_bytes(),bytes(raw))
                opened=api.dispatch('project.open',p);self.assertEqual(opened['sources'][0]['descriptors']['levels'],d)
            finally:api.close()

    def test_original_studio_example_has_actual_level_and_audio_definitions(self):
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'workspace')
            try:
                example=api.dispatch('studio.example',{});self.assertTrue(example['ok'],example)
                opened=api.dispatch('project.open',{'project_id':example['project_id']});source=opened['sources'][0]
                self.assertEqual(source['system_id'],'nes');self.assertIn('levels',source['descriptors']);self.assertIn('sound',source['descriptors'])
                doc=api.dispatch('levels.inspect',{'project_id':example['project_id'],'artifact_id':source['artifact_id'],'definition':source['descriptors']['levels']})
                self.assertTrue(doc['ok'],doc);self.assertEqual(doc['rooms'][0]['width'],16)
            finally:api.close()
