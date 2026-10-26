"""Public original fixtures, never extracted commercial map data."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from romancer import workbench_projects as projects
from romancer.workbench_api import WorkbenchAPI
from tests.test_ffl2_maps import fixture


class KnownMapsAPITests(unittest.TestCase):
    def setUp(self):
        from romancer.verified_games import PROFILES
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.api = WorkbenchAPI(self.root/'workspace')
        self.addCleanup(self.api.close)
        self.project = projects.create_project(self.api.projects, 'Synthetic map program')
        from romancer.boot_fixtures import make_boot_fixture
        raw = fixture(); raw[0x100:0x150] = make_boot_fixture('gb')['data'][0x100:0x150]
        raw[0x147:0x14a] = bytes((0, 3, 0))
        raw[0x14d] = (-sum(raw[0x134:0x14d])-25)&255
        raw[0x14e:0x150] = bytes(2); raw[0x14e:0x150] = (sum(raw)&65535).to_bytes(2, 'big')
        self.original = bytes(raw); self.source = self.root/'synthetic.gb'; self.source.write_bytes(raw)
        row = projects.register_source(Path(self.project['path']), self.source, 'Game Boy')
        self.params = {'project_id':self.project['project_id'], 'artifact_id':row['artifact_id']}
        profile = copy.deepcopy(next(p for p in PROFILES if p['id']=='ffl2-usa'))
        profile['sha256'] = hashlib.sha256(raw).hexdigest()
        for target, value in [('romancer.verified_games.PROFILES', (profile,)),
                              ('romancer.ffl2_maps.ROOT_SHA256', profile['sha256'])]:
            guard=patch(target,value); guard.start(); self.addCleanup(guard.stop)

    def test_catalog_inspection_plan_build_and_owned_lineage(self):
        catalog=self.api.dispatch('games.maps.catalog',{**self.params,'offset':0,'limit':2,'query':''})
        self.assertTrue(catalog['ok'],catalog); self.assertEqual(catalog['counts']['arrivals'],543)
        doc=self.api.dispatch('games.maps.inspect',{**self.params,'header':0x486b,'state':None})
        self.assertTrue(doc['ok'],doc); self.assertEqual(doc['map']['status'],'decoded')
        plan=self.api.dispatch('games.maps.plan',{**self.params,'header':0x486b,
            'changes':[{'kind':'command','offset':0x20267,'x':15}]})
        self.assertTrue(plan['ok'],plan); self.assertTrue(plan['requires_native_playtest'])
        self.assertEqual(len(plan['preview_map']['cells']),4096)
        self.assertEqual(plan['preview_map']['cells'][31*64+15],2)
        built=self.api.dispatch('build.apply',{'project_id':self.params['project_id'],'plan_id':plan['plan_id']})
        self.assertTrue(built['ok'],built)
        inspected=self.api.dispatch('games.maps.inspect',{**self.params,'artifact_id':built['artifact_id'],'header':0x486b,'state':None})
        self.assertTrue(inspected['ok'],inspected)
        self.assertEqual(inspected['map']['commands'][1]['x'],15)
        self.assertEqual(self.source.read_bytes(),self.original)
        foreign=self.root/'foreign.gb';foreign.write_bytes(Path(built['path']).read_bytes())
        row=projects.register_source(Path(self.project['path']),foreign,'Game Boy')
        unknown=self.api.dispatch('games.maps.catalog',{**self.params,'artifact_id':row['artifact_id'],'offset':0,'limit':1,'query':''})
        self.assertFalse(unknown['ok'])

    def test_readonly_mcp_maps_and_bounded_opted_in_plan_schema(self):
        from romancer.mcp_server import MCPServer
        reader=MCPServer(self.root/'reader');self.addCleanup(reader.close)
        writer=MCPServer(self.root/'writer',allow_writes=True);self.addCleanup(writer.close)
        self.assertIn('games.maps.catalog',reader.operations)
        self.assertIn('games.maps.inspect',reader.operations)
        self.assertNotIn('games.maps.plan',reader.operations)
        self.assertIn('games.maps.plan',writer.operations)
        schemas={t['name']:t['inputSchema'] for t in writer.tools()}
        self.assertEqual(schemas['romancer_games_maps_catalog']['properties']['limit']['maximum'],24)
        self.assertEqual(schemas['romancer_games_maps_inspect']['properties']['state']['type'],['object','null'])
        changes=schemas['romancer_games_maps_plan']['properties']['changes']
        self.assertEqual(changes['maxItems'],64);self.assertEqual(len(changes['items']['oneOf']),4)

    def test_bounds_and_unobserved_state_are_explicit(self):
        for extra in ({'offset':0,'limit':25,'query':''},{'offset':0,'limit':1,'query':'x'*129}):
            self.assertFalse(self.api.dispatch('games.maps.catalog',{**self.params,**extra})['ok'])
        invalid=self.api.dispatch('games.maps.inspect',{**self.params,'header':0x486b,'state':{'1':16}})
        self.assertTrue(invalid['ok']); self.assertEqual(invalid['map']['status'],'unsupported')
        self.assertIn('state',invalid['map']['reason'])


class KnownChronoRegistryTests(unittest.TestCase):
    def test_named_resources_are_connected_without_breaking_legacy_id(self):
        from romancer.verified_games import resource_definitions
        resources=resource_definitions({'id':'chrono-trigger-usa','reference':'unused'})
        self.assertEqual(resources[0]['id'],'weapon-power-table')
        self.assertEqual(len(resources),8)
        self.assertTrue(resources[0]['legacy'])
        named=next(r for r in resources if r['id']=='armor-defense-table')
        self.assertIn('label_source',named['definition'])


if __name__=='__main__':unittest.main()
