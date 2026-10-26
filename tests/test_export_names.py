import unittest
from pathlib import Path
import tempfile
from romancer.export_names import readable_name,download_name

class ExportNameTests(unittest.TestCase):
    def test_release_download_names_do_not_change_stored_identity_or_bytes(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer import workbench_projects as p
        import zipfile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.bin';source.write_bytes(b'abcdefgh');api=WorkbenchAPI(root/'workspace')
            try:
                project=Path(p.create_project(api.projects,'My example')['path']);row=p.register_source(project,source,None)
                plan=p.plan_byte_edits(project,row['artifact_id'],[{'offset':2,'before':'63','after':'58'}]);build=p.apply_build(project,plan['plan_id'])
                result=api.dispatch('release.prepare',{'project_id':project.name,'source_id':row['artifact_id'],'target_id':build['artifact_id'],'title':'First sprite edit','description':'One byte'})
                self.assertTrue(result['ok'],result);export=result['export'];self.assertEqual(export['download_name'],'First-sprite-edit.bps');self.assertNotEqual(export['name'],export['download_name'])
                path,download=api.download(project.name,export['export_id']);self.assertEqual(path.name,export['name']);self.assertEqual(download['sha256'],export['sha256'])
                package=api.dispatch('release.package',{'project_id':project.name,'export_ids':[export['export_id']],'title':'First sprite edit'});self.assertTrue(package['ok'],package)
                archive,_=api.download(project.name,package['export']['export_id'])
                with zipfile.ZipFile(archive) as z:self.assertTrue(any(name.endswith('First-sprite-edit.bps') for name in z.namelist()))
                self.assertEqual(source.read_bytes(),b'abcdefgh');self.assertEqual(Path(row['path']).read_bytes(),b'abcdefgh')
            finally:api.close()

    def test_build_notes_accept_lines_without_relaxing_control_validation(self):
        from romancer.build_history import build_note
        self.assertEqual(build_note('First line\r\nSecond line'),'First line\nSecond line')
        for note in ['bad\x00note','bad\x7fnote','bad\tnote','x'*2001]:
            with self.assertRaises(ValueError):build_note(note)

    def test_readable_safe_names_preserve_extension(self):
        self.assertEqual(readable_name('First sprite edit','bps'),'First-sprite-edit.bps')
        self.assertEqual(readable_name('Édition française','zip'),'Edition-francaise.zip')
        for title in ['../..\\bad\r\nInjected: yes','CON','NUL','...','💾','x'*1000]:
            name=readable_name(title,'bps');self.assertLessEqual(len(name),104)
            self.assertRegex(name,r'^[A-Za-z0-9_-]+\.bps$')
            self.assertNotIn(name.upper(),['CON.BPS','NUL.BPS'])
        with self.assertRaises(ValueError):readable_name('x','exe')

    def test_untrusted_or_legacy_download_labels_fail_back_to_storage_name(self):
        row={'name':'abcdef.bps','download_name':'Friendly.bps'}
        self.assertEqual(download_name(row),'Friendly.bps')
        for label in ['evil.exe','../evil.bps','x\r\nBad: header.bps','CON.bps']:
            self.assertEqual(download_name({**row,'download_name':label}),'abcdef.bps')
        self.assertEqual(download_name({'name':'abcdef.bps'}),'abcdef.bps')
