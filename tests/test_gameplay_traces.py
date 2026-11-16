import base64,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from romancer.asset_codecs import encode_cell
from romancer.boot_fixtures import make_boot_fixture
from romancer.graphics_discovery import SYSTEM_CODECS
from romancer.workbench_api import WorkbenchAPI

class GameplayTraceTests(unittest.TestCase):
    def test_scene_checkpoint_saves_owned_cold_replay_without_scanning_tiles(self):
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'work');self.addCleanup(api.close)
            project=api.dispatch('project.demo_system',{'system_id':'nes'})
            source=project['sources'][0]
            params={'project_id':project['project_id'],'artifact_id':source['artifact_id']}
            rgb=bytes(range(192))
            frame={'ok':True,'width':8,'height':8,'index':60,'sha256':hashlib.sha256(rgb).hexdigest(),
                   'rgb24_base64':base64.b64encode(rgb).decode(),'game_sha256':source['sha256'],
                   'core_sha256':'c'*64,'runtime_identity_sha256':'d'*64}
            replay={'status':'READY','steps':[{'frames':60,'buttons':['a'],'port':0}],'frames':60,'context':{}}
            request={**params,'frame_sha256':frame['sha256'],'region':None}
            with (patch.object(api,'_graphics_observe',side_effect=AssertionError('checkpoint scans ROM')),
                  patch.object(api.runtime,'request',return_value=frame),
                  patch.object(api.runtime,'session_selection',return_value={'id':source['artifact_id'],'sha256':source['sha256']}),
                  patch.object(api.runtime,'replay_snapshot',return_value=replay) as snapshot):
                captured=api.dispatch('traces.checkpoint',request)
                self.assertTrue(captured['ok'],captured)
                self.assertEqual(captured['matches'],[])
                self.assertEqual(captured['replay']['steps'],replay['steps'])
                self.assertTrue(captured['checkpoint_only'])
                snapshot.return_value={'status':'UNAVAILABLE','reason':'State loaded'}
                self.assertFalse(api.dispatch('traces.checkpoint',request)['ok'])
                snapshot.return_value=replay
                self.assertFalse(api.dispatch('traces.checkpoint',{**request,'frame_sha256':'0'*64})['ok'])
            saved=api.dispatch('traces.get',{**params,'trace_id':captured['trace_id']})
            self.assertEqual(saved['frame']['sha256'],frame['sha256'])
            self.assertFalse(api.dispatch('traces.open',{**params,'trace_id':saved['trace_id'],'matches':[0]})['ok'])

    def test_every_system_records_native_region_and_connects_candidates_without_claiming_rom_ownership(self):
        folder=self.enterContext(tempfile.TemporaryDirectory());root=Path(folder);api=WorkbenchAPI(root/'work');self.addCleanup(api.close)
        pixels=[1+(x+y)%3 for y in range(8) for x in range(8)];colors=[(0,0,0),(255,10,20),(10,255,20),(10,20,255)];rgb=bytes(c for i in pixels for c in colors[i])
        for system,codec in SYSTEM_CODECS.items():
            with self.subTest(system=system):
                if system=='sms':raw=bytearray(32768);raw[0x7ff0:0x7ff8]=b'TMR SEGA';raw[0x7fff]=0x4c
                else:raw=bytearray(make_boot_fixture(system)['data'])
                tile=encode_cell(pixels,codec=codec,width=8,height=8);raw[4096:4096+len(tile)]=tile;file=root/(system+'.bin');file.write_bytes(raw)
                p={'project_id':api.dispatch('project.create',{'name':system+' trace'})['project_id']};source=api.dispatch('source.import',{**p,'path':str(file),'system':None});sp={**p,'artifact_id':source['artifact_id']}
                frame={'ok':True,'width':8,'height':8,'index':5,'sha256':hashlib.sha256(rgb).hexdigest(),'rgb24_base64':base64.b64encode(rgb).decode(),'game_sha256':source['sha256'],'core_sha256':'c'*64,'runtime_identity_sha256':'d'*64,'provenance':{'origin':'cold_boot'}}
                params={**sp,'name':'Captured object','frame_sha256':frame['sha256'],'region':{'x':0,'y':0,'width':8,'height':8},'offset':4096,'length':64}
                with patch.object(api.runtime,'request',return_value=frame):trace=api.dispatch('traces.capture',params)
                self.assertTrue(trace['ok'],trace);self.assertFalse(trace['provenance_verified']);self.assertTrue(trace['crop_png_base64'])
                graph=api.dispatch('gameview.graph',{**sp,'query':'','kind':'all','page':0});self.assertTrue(graph['ok'],graph);self.assertTrue(any(e['relation']=='pixel_match' for e in graph['edges']))
                picked=next(i for i,m in enumerate(trace['matches']) if m['offset']==4096 and not m['flip_x'] and not m['flip_y'] and m['height']==8)
                opened=api.dispatch('traces.open',{**sp,'trace_id':trace['trace_id'],'matches':[picked]});self.assertTrue(opened['ok'],opened);self.assertTrue(opened['candidate_only'])
                if system=='nes':
                    from romancer import workbench_projects as projects
                    d={'schema_version':1,'name':'Dense table','offset':4096,'count':256,'stride':1,'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]}
                    self.assertTrue(api.dispatch('tables.save_definition',{**sp,'definition':d})['ok'])
                    with projects.locked(api.project(p)) as store:
                        store['sources'][0]['research_notes']={'format':'romancer-notes-v1','source_sha256':source['sha256'],'notes':[{'id':f'{i:032x}','title':'Note '+str(i),'offset':4096,'length':1,'category':'other','text':'Declared note','reference':''} for i in range(256)]};projects.write_json(api.project(p)/'project.json',store)
                    filtered=api.dispatch('gameview.graph',{**sp,'query':'','kind':'trace','page':0});self.assertTrue(filtered['ok'],filtered);self.assertEqual(filtered['total'],1,'A dense category cannot hide another category before filtering.')
                    with projects.locked(api.project(p)) as store:
                        store['sources'][0]['gameplay_traces']['ids'].append('e'*32);projects.write_json(api.project(p)/'project.json',store)
                    with patch.object(api.runtime,'request',return_value=frame):recovered=api.dispatch('traces.capture',params)
                    self.assertTrue(recovered['ok'],recovered);self.assertTrue(recovered['trace_index_repaired'])
                    self.assertTrue(api.dispatch('traces.get',{**sp,'trace_id':trace['trace_id']})['ok'],'Valid existing reports remain available after index recovery.')
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),source['sha256'])
                with patch.object(api.runtime,'request',return_value={**frame,'sha256':'0'*64}):self.assertFalse(api.dispatch('traces.capture',params)['ok'])
                from romancer.workbench_evidence import quarantine_restored_evidence
                quarantine_restored_evidence(api.project(p))
                self.assertFalse(api.dispatch('traces.get',{**sp,'trace_id':trace['trace_id']})['runtime_trusted'])
                self.assertFalse(api.dispatch('traces.open',{**sp,'trace_id':trace['trace_id'],'matches':[picked]})['ok'])

    def test_missing_or_foreign_trace_does_not_authorize_editing(self):
        folder=self.enterContext(tempfile.TemporaryDirectory());api=WorkbenchAPI(Path(folder)/'work');self.addCleanup(api.close);p=api.dispatch('project.demo_system',{'system_id':'nes'})
        result=api.dispatch('traces.open',{'project_id':p['project_id'],'artifact_id':p['sources'][0]['artifact_id'],'trace_id':'0'*32,'matches':[0]})
        self.assertFalse(result['ok']);self.assertNotEqual(result.get('error'),'unknown workbench operation')
