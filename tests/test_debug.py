import hashlib
import importlib
from pathlib import Path
import tempfile
import unittest
from debug_fixtures import debug_fixture


class DebugServiceTests(unittest.TestCase):
    def service(self):
        try:module=importlib.import_module('romancer.debug')
        except ModuleNotFoundError:module=None
        self.assertIsNotNone(module,'revision-bound case inspection is missing')
        return module.inspect_debug_case

    def fixture(self,root):
        from romancer.history import init_history,register_build
        fixture=debug_fixture();source=root/'source.bin';source.write_bytes(fixture['raw'])
        project=root/'project';project.mkdir();init_history(project)
        result=register_build(project,{'inputs':[{'role':'resource','path':str(source)}],'output':str(source),
            'adapter':{'name':'synthetic','version':'1'},'profile':{'name':'literal','version':'1'},'settings':{}},root)
        fixture['case']['build_id']=result['build_id']
        return source,project,fixture

    def test_exact_selected_build_and_source_bytes_without_store_writes(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,project,fixture=self.fixture(root)
            before={str(p.relative_to(project)):p.read_bytes() for p in project.rglob('*') if p.is_file()}
            result=service(project,source,fixture['case'],fixture['trace'])
            self.assertTrue(result['ok'],result)
            self.assertEqual(result['probes'][0]['source']['raw_hex'],'00')
            self.assertEqual(result['probes'][1]['source']['raw_hex'],'08')
            self.assertEqual(result['probes'][2]['status'],'UNRESOLVED')
            self.assertEqual(result['causation'],'NOT_RUN')
            self.assertEqual(before,{str(p.relative_to(project)):p.read_bytes() for p in project.rglob('*') if p.is_file()})

    def test_changed_source_or_wrong_build_refuses(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as temp:
            source,project,fixture=self.fixture(Path(temp))
            source.write_bytes(b'X'*32)
            self.assertFalse(service(project,source,fixture['case'],fixture['trace'])['ok'])
