import hashlib,tempfile,unittest
from pathlib import Path
from romancer.workbench_api import WorkbenchAPI
from romancer.boot_fixtures import make_boot_fixture

class ConnectedGameTests(unittest.TestCase):
    def test_pixel_candidate_containment_keeps_the_same_direction_from_either_selection(self):
        from romancer.connected_game import neighbors
        resource={'id':'a','kind':'assets','offset':100,'length':100};candidate={'id':'b','kind':'candidate','offset':120,'length':16};model={'nodes':[resource,candidate],'edges':[]}
        for selected in (resource,candidate):self.assertEqual(neighbors(model,selected),[{'from':'b','to':'a','relation':'located_in'}])
        partial={**candidate,'offset':90};model['nodes']=[resource,partial]
        self.assertEqual(neighbors(model,partial)[0]['relation'],'shares_storage')

    def test_shared_view_connects_declared_resources_on_every_supported_system_without_game_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);api=WorkbenchAPI(root/'work');self.addCleanup(api.close)
            for system in ('nes','snes','genesis','sms','gb','gbc','gba'):
                with self.subTest(system=system):
                    if system=='sms':
                        raw=bytearray(32768);raw[0x7ff0:0x7ff8]=b'TMR SEGA';raw[0x7fff]=0x4c;raw=bytes(raw)
                    else:raw=make_boot_fixture(system)['data']
                    file=root/(system+'.bin');file.write_bytes(raw)
                    project=api.dispatch('project.create',{'name':'Connected '+system});p={'project_id':project['project_id']}
                    source=api.dispatch('source.import',{**p,'path':str(file),'system':None});self.assertTrue(source['ok'],source);sp={**p,'artifact_id':source['artifact_id']}
                    declared=api.dispatch('resources.declare_assets',{**sp,'config':{'system_id':system,'offset':4096,'count':2}});self.assertTrue(declared['ok'],declared)
                    definition={'schema_version':1,'name':'Example values','offset':4096,'count':2,'stride':2,'row_names':['First item','Second item'],'row_id_base':1,'fields':[{'name':'Value','offset':0,'type':'u16','endian':'little','pointer_base':None}]}
                    self.assertTrue(api.dispatch('tables.save_definition',{**sp,'definition':definition})['ok'])
                    graph=api.dispatch('gameview.graph',{**sp,'query':'','kind':'all','page':0});self.assertTrue(graph['ok'],graph)
                    self.assertEqual(graph['system_id'],system);self.assertTrue(any(n['name']=='First item' for n in graph['nodes']))
                    self.assertTrue(any(e['relation']=='shares_storage' for e in graph['edges']))
                    node=next(n for n in graph['nodes'] if n['name']=='First item')
                    detail=api.dispatch('gameview.detail',{**sp,'node_id':node['id']});self.assertTrue(detail['ok'],detail);self.assertEqual(detail['node']['offset'],4096)
                    self.assertEqual(detail['preview']['fields'][0]['name'],'Value');self.assertFalse(graph['game_semantics_inferred'])
                    self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),source['sha256'])
            api.close()

    def test_stale_or_missing_nodes_cannot_open_unrelated_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);api=WorkbenchAPI(root/'work');self.addCleanup(api.close);p=api.dispatch('project.demo_system',{'system_id':'nes'})
            row=p['sources'][0];result=api.dispatch('gameview.detail',{'project_id':p['project_id'],'artifact_id':row['artifact_id'],'node_id':'0'*32})
            self.assertFalse(result['ok']);self.assertNotEqual(result.get('error'),'unknown workbench operation')
            api.close()

    def test_rooms_have_real_map_previews_and_user_links_stay_declarations(self):
        folder=self.enterContext(tempfile.TemporaryDirectory());api=WorkbenchAPI(Path(folder)/'work');self.addCleanup(api.close);p=api.dispatch('studio.example',{});self.assertTrue(p['ok'],p)
        opened=api.dispatch('project.open',{'project_id':p['project_id']});sp={'project_id':p['project_id'],'artifact_id':opened['sources'][0]['artifact_id']};graph=api.dispatch('gameview.graph',{**sp,'query':'','kind':'all','page':0});self.assertTrue(graph['ok'],graph)
        room=next(n for n in graph['nodes'] if n['kind']=='room');preview=api.dispatch('gameview.detail',{**sp,'node_id':room['id']});self.assertTrue(preview['ok'],preview);self.assertTrue(preview['preview']['png_base64'])
        target=next(n for n in graph['nodes'] if n['id']!=room['id']);linked=api.dispatch('gameview.link',{**sp,'from_id':room['id'],'to_id':target['id'],'relation':'uses_graphics','note':'Author-declared example relationship'});self.assertTrue(linked['ok'],linked)
        current=api.dispatch('gameview.detail',{**sp,'node_id':room['id']});self.assertTrue(any(e['relation']=='uses_graphics' and e['confidence']=='user_declared' for e in current['connections']))
        self.assertFalse(api.dispatch('gameview.link',{**sp,'from_id':'0'*32,'to_id':target['id'],'relation':'uses_graphics','note':''})['ok'])
        self.assertTrue(api.dispatch('gameview.unlink',{**sp,'link_id':linked['link_id']})['ok'])
