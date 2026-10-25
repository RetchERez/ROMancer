import importlib
import tempfile
from pathlib import Path
import unittest


class ProjectTests(unittest.TestCase):
    def test_cancelled_copy_does_not_publish(self):
        m=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'input';source.write_bytes(b'a'*200000)
            destination=root/'output';measured=m._measure(source)
            with self.assertRaises(KeyboardInterrupt):m._publish_copy(source,destination,measured,cancelled=lambda:True)
            self.assertFalse(destination.exists());self.assertEqual(list(root.glob('.build-*')),[])

    def service(self):
        try: module=importlib.import_module('romancer.workbench_projects')
        except ModuleNotFoundError: module=None
        self.assertIsNotNone(module,'content-bound workbench project service is missing')
        return module

    def test_reopen_edit_build_preserves_original_and_independent_output(self):
        m=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); original=root/'original Ω game.bin'; original.write_bytes(bytes(range(256)))
            project=Path(m.create_project(root/'projects','Test Ω project')['path'])
            source=m.register_source(project,original,None)
            self.assertEqual(m.list_projects(root/'projects')[0]['name'],'Test Ω project')
            view=m.inspect_resource(project,source['artifact_id'],250,6)
            self.assertEqual(view['hex'],'fafbfcfdfeff')
            plan=m.plan_byte_edits(project,source['artifact_id'],[{'offset':10,'before':'0a0b','after':'ffee'}])
            build=m.apply_build(project,plan['plan_id'])
            self.assertEqual(original.read_bytes(),bytes(range(256)))
            self.assertEqual(Path(build['path']).read_bytes(),bytes(range(10))+b'\xff\xee'+bytes(range(12,256)))
            from romancer.history import get_build
            self.assertEqual(get_build(project,build['build_id'])['identity']['output']['sha256'],build['sha256'])
            with self.assertRaises(ValueError):m.apply_build(project,plan['plan_id'])

    def test_bad_preconditions_overlap_bounds_and_stale_source_refuse(self):
        m=self.service()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); original=root/'g';original.write_bytes(b'abcd')
            project=Path(m.create_project(root/'p','P')['path']);a=m.register_source(project,original,None)
            for edits in ([{'offset':0,'before':'ff','after':'00'}],
                          [{'offset':0,'before':'6162','after':'1111'},{'offset':1,'before':'62','after':'22'}],
                          [{'offset':4,'before':'00','after':'11'}]):
                with self.assertRaises(ValueError):m.plan_byte_edits(project,a['artifact_id'],edits)
            plan=m.plan_byte_edits(project,a['artifact_id'],[{'offset':0,'before':'61','after':'62'}])
            Path(a['path']).write_bytes(b'xxxx')
            with self.assertRaises(ValueError):m.apply_build(project,plan['plan_id'])
            with self.assertRaises(ValueError):m.inspect_resource(project,'../escape',0,1)
            self.assertEqual(original.read_bytes(),b'abcd')
