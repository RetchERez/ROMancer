import tempfile,unittest
from pathlib import Path
from romancer.workbench_api import WorkbenchAPI

class DownloadInputTests(unittest.TestCase):
    def test_html_named_as_archive_is_rejected_without_registering_a_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bad=root/'Rastan.7z';bad.write_bytes(b'<!DOCTYPE HTML>\n<html><title>Download challenge</title></html>');api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Import check'});params={'project_id':project['project_id']}
                result=api.dispatch('source.import',{**params,'path':str(bad),'system':None})
                self.assertFalse(result['ok'],result);self.assertIn('HTML',result['error']);self.assertIn('actual cartridge',result['error'])
                self.assertEqual(api.dispatch('project.open',params)['sources'],[])
            finally:api.close()

    def test_html_bom_whitespace_and_case_do_not_hide_a_failed_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bad=root/'game.sms';bad.write_bytes(b'\xef\xbb\xbf  \r\n<HTML lang="en">Not a game</HTML>');api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Import check'})
                result=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(bad),'system':None})
                self.assertFalse(result['ok'],result);self.assertIn('HTML',result['error'])
            finally:api.close()

    def test_binary_data_with_embedded_html_remains_inspectable(self):
        from romancer.boot_fixtures import make_boot_fixture
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'known.nes';raw=bytearray(make_boot_fixture('nes')['data']);raw[100:115]=b'<!DOCTYPE HTML>';source.write_bytes(raw);api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Inspect binary'});params={'project_id':project['project_id']}
                result=api.dispatch('source.import',{**params,'path':str(source),'system':None});self.assertTrue(result['ok'],result)
                inspected=api.dispatch('resource.inspect',{**params,'artifact_id':result['artifact_id'],'offset':0,'length':4});self.assertTrue(inspected['ok'],inspected)
            finally:api.close()
