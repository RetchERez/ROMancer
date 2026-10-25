from pathlib import Path
import tempfile
import unittest
from romancer.workbench_api import WorkbenchAPI

class ProjectLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.api=WorkbenchAPI(self.root/'workspace');self.addCleanup(self.api.close)
        self.project=self.api.dispatch('project.create',{'name':'Keep my work'})

    def delete(self):
        result=self.api.dispatch('project.delete',{'project_id':self.project['project_id']})
        if not result['ok'] and 'atomic no-replace' in result.get('error',''):self.skipTest(result['error'])
        self.assertTrue(result['ok'],result);return result

    def test_delete_hides_project_and_restore_preserves_all_owned_bytes(self):
        file=Path(self.project['path'])/'sessions/note.bin';file.write_bytes(b'owned project data\0\xff')
        deleted=self.delete()
        self.assertFalse(self.api.dispatch('projects.list',{})['projects'])
        trash=self.api.dispatch('projects.trash',{})['projects'];self.assertEqual(trash[0]['name'],'Keep my work')
        restored=self.api.dispatch('project.undelete',{'trash_id':deleted['trash_id']});self.assertTrue(restored['ok'],restored)
        self.assertEqual(file.read_bytes(),b'owned project data\0\xff');self.assertFalse(self.api.dispatch('projects.trash',{})['projects'])

    def test_restore_refuses_to_replace_existing_project(self):
        deleted=self.delete()
        existing=Path(self.project['path']);existing.mkdir();(existing/'keep.txt').write_bytes(b'keep')
        refused=self.api.dispatch('project.undelete',{'trash_id':deleted['trash_id']})
        self.assertFalse(refused['ok']);self.assertEqual((existing/'keep.txt').read_bytes(),b'keep')
        self.assertEqual(len(self.api.dispatch('projects.trash',{})['projects']),1)

    def test_identifiers_cannot_escape_workspace(self):
        for op,key in [('project.delete','project_id'),('project.undelete','trash_id')]:
            self.assertFalse(self.api.dispatch(op,{key:'../outside'})['ok'])
        self.assertTrue(Path(self.project['path']).exists())
