"""Original synthetic catalog and cartridge; no publisher data in fixtures."""
from pathlib import Path
import tempfile
import unittest

from romancer.workbench_api import WorkbenchAPI
from romancer.boot_fixtures import make_boot_fixture


class CheatScanAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.api=WorkbenchAPI(self.root/'workspace');self.addCleanup(self.api.close)
        self.project=self.api.dispatch('project.create',{'name':'Code clues'})['project_id']
        source=self.root/'Example Cart.nes';source.write_bytes(make_boot_fixture('nes')['data'])
        self.source=self.api.dispatch('source.import',{'project_id':self.project,'path':str(source),'system':None})
        self.params={'project_id':self.project,'artifact_id':self.source['artifact_id']}

    def test_catalog_connects_to_inspection_and_deep_scan_without_writes(self):
        original=Path(self.source['path']).read_bytes()
        catalog=self.root/'refs.txt';catalog.write_text('[NES] Example Cart\n  SOURCE: Fictional reference | page 1\n  AAAAAA | Different tickets\n',encoding='utf-8')
        auxiliary=self.api.dispatch('inputs.import',{'project_id':self.project,'path':str(catalog),'name':catalog.name,'kind':'catalog'})
        imported=self.api.dispatch('cheats.import',{'project_id':self.project,'input_id':auxiliary['input_id']})
        self.assertTrue(imported['ok'],imported);self.assertEqual(imported['count'],1)
        result=self.api.dispatch('cheats.inspect',{**self.params,'query':'','page':0,'limit':20})
        self.assertTrue(result['ok'],result);self.assertEqual(result['total'],1)
        self.assertEqual(result['entries'][0]['revision_status'],'UNSPECIFIED')
        scan=self.api.dispatch('rom.scan.run',self.params)
        self.assertTrue(scan['ok'],scan);self.assertEqual(scan['cheat_references']['catalog_count'],1)
        self.assertFalse(scan['cheat_references']['write_authorized'])
        self.assertEqual(Path(self.source['path']).read_bytes(),original)

    def test_catalog_and_read_only_ai_operations_are_discoverable(self):
        operations={r['name'] for r in self.api.dispatch('system.operations',{})['operations']}
        self.assertTrue({'cheats.import','cheats.catalog','cheats.inspect'}.issubset(operations))
        from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS
        self.assertIn('cheats.inspect',READ_OPERATIONS);self.assertIn('cheats.catalog',READ_OPERATIONS)
        self.assertIn('cheats.import',WRITE_OPERATIONS);self.assertNotIn('cheats.import',READ_OPERATIONS)
        self.assertNotIn('engines.inspect',READ_OPERATIONS)

    def test_replacing_catalog_invalidates_signed_scan_cache(self):
        from romancer import rom_scan,workbench_projects
        project=self.api.project({'project_id':self.project})
        row=workbench_projects.artifact(project,self.source['artifact_id'])
        rom_scan.run(project,row)
        self.assertIsNotNone(rom_scan.cached(project,row))
        catalog=self.root/'updated.txt';catalog.write_text('[NES] Example Cart\nAAAAAA | New clue\n',encoding='utf-8')
        auxiliary=self.api.dispatch('inputs.import',{'project_id':self.project,'path':str(catalog),'name':catalog.name,'kind':'catalog'})
        self.api.dispatch('cheats.import',{'project_id':self.project,'input_id':auxiliary['input_id']})
        self.assertIsNone(rom_scan.cached(project,row))
        scan=rom_scan.run(project,row)
        self.assertEqual(scan['cheat_references']['catalog_count'],1)
        self.assertIsNotNone(rom_scan.cached(project,row))

    def test_ai_schema_agrees_with_backend_page_bounds(self):
        from romancer.mcp_server import _schema
        schema=_schema(['project_id','artifact_id','query','page','limit'],'cheats.inspect')
        self.assertEqual(schema['properties']['limit']['maximum'],20)
        self.assertEqual(schema['properties']['page']['maximum'],20000)
        rejected=self.api.dispatch('cheats.inspect',{**self.params,'query':'','page':0,'limit':21})
        self.assertFalse(rejected['ok'])


if __name__=='__main__':unittest.main()
