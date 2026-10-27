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
