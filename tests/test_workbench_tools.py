import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch


class OwnedInputTests(unittest.TestCase):
    def test_input_is_copied_and_rechecked_without_changing_original(self):
        from romancer.workbench_files import import_input, input_file
        from romancer.workbench_projects import create_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(create_project(root/'projects','Tools')['path'])
            original=root/'author.ips';original.write_bytes(b'PATCHEOF')
            imported=import_input(project,original,'Author patch.ips','patch')
            row,path=input_file(project,imported['input_id'],'patch')
            self.assertEqual(path.read_bytes(),b'PATCHEOF');self.assertEqual(row['name'],'Author patch.ips')
            original.write_bytes(b'changed outside');self.assertEqual(path.read_bytes(),b'PATCHEOF')
            path.write_bytes(b'changed inside')
            with self.assertRaisesRegex(ValueError,'identity|changed'):input_file(project,imported['input_id'],'patch')

    def test_wrong_kind_unsafe_names_and_budget_do_not_publish(self):
        from romancer.workbench_files import import_input, input_file
        from romancer.workbench_projects import create_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(create_project(root/'projects','Tools')['path']);source=root/'source';source.write_bytes(b'12345')
            for name,kind in [('../escape','patch'),('C:escape','patch'),('name','executable')]:
                with self.subTest(name=name,kind=kind),self.assertRaises(ValueError):import_input(project,source,name,kind)
            with patch('romancer.workbench_files.LIMITS',{'patch':4}):
                with self.assertRaises(ValueError):import_input(project,source,'patch.ips','patch')
            self.assertFalse((project/'inputs.json').exists())
            imported=import_input(project,source,'patch.ips','patch')
            with self.assertRaisesRegex(ValueError,'kind'):input_file(project,imported['input_id'],'save')

    def test_http_patch_upload_is_authenticated_and_not_a_rom_source(self):
        from romancer.workbench_server import create_server
        with tempfile.TemporaryDirectory() as folder:
            server=create_server(Path(folder));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                project=server.api.dispatch('project.create',{'name':'Uploaded patches'});pid=project['project_id']
                url=f'http://127.0.0.1:{server.server_port}/api/upload?project_id={pid}&name=demo.ips&kind=patch'
                with self.assertRaises(HTTPError) as denied:urlopen(Request(url,data=b'PATCHEOF',method='POST'))
                self.assertEqual(denied.exception.code,401)
                denied.exception.close()
                request=Request(url,data=b'PATCHEOF',method='POST',headers={'Authorization':'Bearer '+server.session_token})
                with urlopen(request) as response:result=json.load(response)
                self.assertTrue(result['ok'],result);self.assertEqual(result['kind'],'patch')
                opened=server.api.dispatch('project.open',{'project_id':pid});self.assertEqual(opened['sources'],[])
                listed=server.api.dispatch('inputs.list',{'project_id':pid})
                self.assertEqual(listed['inputs'][0]['sha256'],hashlib.sha256(b'PATCHEOF').hexdigest())
                self.assertNotIn('path',listed['inputs'][0])
            finally:server.shutdown();thread.join();server.server_close();server.api.close()

    def test_private_backup_preserves_new_inputs_and_metadata_by_role(self):
        from romancer.workbench_files import import_input
        from romancer.workbench_projects import create_project,write_json
        from romancer.project_portability import backup_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(create_project(root/'projects','Backup')['path'])
            file=root/'file';file.write_bytes(b'PATCHDATA');patch_input=import_input(project,file,'a.ips','patch')
            file.write_bytes(b'SAVEDATA');save_input=import_input(project,file,'a.sav','save')
            write_json(project/'bookmarks.json',{'marks':[]});write_json(project/'build-notes.json',{'notes':[]})
            backup_project(project,root/'source-backup.zip',['sources'])
            with zipfile.ZipFile(root/'source-backup.zip') as z:
                self.assertIn('inputs/'+patch_input['input_id']+'.ips',z.namelist())
                self.assertNotIn('inputs/'+save_input['input_id']+'.sav',z.namelist())
                self.assertTrue({'inputs.json','bookmarks.json','build-notes.json'}<=set(z.namelist()))
            backup_project(project,root/'complete.zip',['sources','sessions'])
            with zipfile.ZipFile(root/'complete.zip') as z:self.assertEqual(z.read('inputs/'+save_input['input_id']+'.sav'),b'SAVEDATA')

