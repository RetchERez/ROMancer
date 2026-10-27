import tempfile,unittest
from pathlib import Path
from romancer.mcp_server import MCPServer

class ConnectedMCPTests(unittest.TestCase):
    def test_cross_system_tools_expose_typed_parameters_and_write_permissions(self):
        folder=self.enterContext(tempfile.TemporaryDirectory());reader=MCPServer(Path(folder)/'read');writer=MCPServer(Path(folder)/'write',allow_writes=True);self.addCleanup(reader.close);self.addCleanup(writer.close)
        read={r['name']:r for r in reader.tools()};write={r['name']:r for r in writer.tools()}
        self.assertIn('romancer_gameview_graph',read);self.assertNotIn('romancer_traces_capture',read);self.assertNotIn('romancer_checks_run',read)
        schemas={k:v['inputSchema']['properties'] for k,v in write.items() if k!='romancer_call'}
        self.assertIn('trace',schemas['romancer_gameview_graph']['kind']['enum']);self.assertEqual(schemas['romancer_traces_capture']['region']['type'],'object')
        self.assertEqual(schemas['romancer_checks_configure']['config']['properties']['automatic']['type'],'boolean')
        self.assertEqual(schemas['romancer_traces_open']['matches']['maxItems'],64)
        self.assertTrue(read['romancer_gameview_detail']['annotations']['readOnlyHint'])

    def test_visual_previews_are_image_blocks_with_compact_machine_readable_metadata(self):
        folder=self.enterContext(tempfile.TemporaryDirectory());writer=MCPServer(Path(folder)/'work',allow_writes=True);self.addCleanup(writer.close)
        p=writer.api.dispatch('project.demo_system',{'system_id':'nes'});sp={'project_id':p['project_id'],'artifact_id':p['sources'][0]['artifact_id']}
        graph=writer.api.dispatch('gameview.graph',{**sp,'query':'','kind':'assets','page':0});self.assertTrue(graph['ok'],graph)
        node=next(n for n in graph['nodes'] if 'bitmaps' in n['name']);result=writer.call('romancer_gameview_detail',{**sp,'node_id':node['id']})
        self.assertFalse(result['isError'],result);self.assertTrue(any(c['type']=='image' for c in result['content']))
        self.assertTrue(result['structuredContent']['preview']['png_base64'].startswith('[PNG preview'))

    def test_native_graphics_preview_preserves_events_and_identity_in_a_bounded_model_image(self):
        import base64,random,io
        from PIL import Image
        from unittest.mock import patch
        folder=self.enterContext(tempfile.TemporaryDirectory());reader=MCPServer(Path(folder)/'work');self.addCleanup(reader.close)
        rng=random.Random(17);image=Image.frombytes('RGB',(320,224),rng.randbytes(320*224*3));out=io.BytesIO();image.save(out,format='PNG')
        result={'ok':True,'evidence_id':'e'*32,'artifact_id':'a'*32,'source_sha256':'b'*64,'events':[{'id':1,'kind':'read','file_offset':4096}],'scene':{'width':320,'height':224,'png_base64':base64.b64encode(out.getvalue()).decode()}}
        with patch.object(reader.api,'dispatch',return_value=result):
            got=reader.call('romancer_graphics_accesses_get',{'project_id':'p','artifact_id':'a','evidence_id':'e','offset':0,'limit':1})
        self.assertFalse(got['isError'],got);self.assertTrue(any(c['type']=='image' for c in got['content']))
        public=got['structuredContent'];self.assertNotIn('result_truncated',public);self.assertEqual(public['evidence_id'],'e'*32);self.assertEqual(public['events'],result['events'])
        self.assertTrue(public['scene']['png_base64'].startswith('[PNG preview'))
