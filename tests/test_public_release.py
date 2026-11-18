import hashlib
import io
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import patch
import zipfile


class PublicReleaseTests(unittest.TestCase):
    def test_public_version_identity(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder))
            try:
                value=api.dispatch('system.capabilities',{})
                self.assertEqual(value['release_name'],'ROMancer v1.1.1')
                self.assertEqual(value['version'],'1.1.1')
                self.assertEqual(value['target_version'],'1.1.1')
                self.assertEqual(value['build_label'],'v1.1.1')
                self.assertEqual(value['release_status'],'RELEASE')
            finally:api.close()

    def test_level_editing_is_excluded_from_the_release(self):
        from romancer.mcp_server import MCPServer
        with tempfile.TemporaryDirectory() as folder:
            server = MCPServer(Path(folder), allow_writes=True)
            try:
                operations = {row['name'] for row in server.api.dispatch('system.operations', {})['operations']}
                for operation in ('levels.plan','games.maps.plan'):
                    self.assertNotIn(operation, operations)
                    self.assertNotIn(operation, server.operations)
                self.assertIn('levels.inspect', operations)
                self.assertIn('bytes.plan', operations)
                self.assertIn('release.prepare', operations)
            finally:
                server.close()

    def test_public_metadata_is_in_the_explicit_source_inventory(self):
        from tools.package_source import APPROVED_FILES
        required={'LICENSE','.gitignore','.gitattributes','.editorconfig','README.txt','THIRD_PARTY_NOTICES.txt',
                  'package.json','package-lock.json','.github/workflows/ci.yml',
                  'tools/fetch_runtime.py','tools/audit_release.py','tools/check_ui.mjs'}
        self.assertFalse(required-APPROVED_FILES,required-APPROVED_FILES)

    def test_runtime_fetch_is_hash_checked_atomic_and_reuses_a_valid_cache(self):
        from tools.fetch_runtime import fetch_pin
        raw=b'original pinned runtime';pin={'file':'fixture.zip','sha256':hashlib.sha256(raw).hexdigest(),'url':'https://www.python.org/fixture.zip'}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);opener=lambda *_args,**_kwargs:io.BytesIO(raw)
            self.assertTrue(fetch_pin(root,pin,opener=opener).is_file())
            self.assertEqual(fetch_pin(root,pin,opener=lambda *_a,**_k:self.fail('cache fetched again')).read_bytes(),raw)
            (root/pin['file']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'hash'):fetch_pin(root,pin,opener=opener)
            self.assertEqual((root/pin['file']).read_bytes(),b'changed')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaisesRegex(ValueError,'hash'):fetch_pin(root,pin,opener=lambda *_a,**_k:io.BytesIO(b'bad'))
            self.assertEqual(list(root.iterdir()),[])

    def test_runtime_fetch_rejects_unsafe_names_urls_and_oversized_downloads(self):
        from tools.fetch_runtime import fetch_pin
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pin={'file':'../escape.zip','sha256':'0'*64,'url':'https://www.python.org/fixture.zip'}
            with self.assertRaises(ValueError):fetch_pin(root,pin)
            pin['file']='fixture.zip';pin['url']='http://www.python.org/fixture.zip'
            with self.assertRaises(ValueError):fetch_pin(root,pin)
            pin['url']='https://www.python.org/fixture.zip'
            with patch('tools.fetch_runtime.MAX_DOWNLOAD',4):
                with self.assertRaisesRegex(ValueError,'budget'):fetch_pin(root,pin,opener=lambda *_a,**_k:io.BytesIO(b'12345'))
            self.assertFalse((root/pin['file']).exists())

    def test_release_audit_rejects_private_paths_credentials_and_missing_license(self):
        from tools.audit_release import audit_source
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'source.zip'
            for name,raw in [('work_private/data.json',b'{}'),('../outside',b'bad'),('README.txt',('ghp_'+'A'*36).encode()),('README.txt',('C:/Users/'+'LocalOwner/private').encode())]:
                with self.subTest(name=name):
                    with zipfile.ZipFile(p,'w') as z:z.writestr(name,raw)
                    with self.assertRaises(ValueError):audit_source(p)
            with zipfile.ZipFile(p,'w') as z:z.writestr('README.txt',b'No license')
            with self.assertRaisesRegex(ValueError,'missing'):audit_source(p)
            with zipfile.ZipFile(p,'w') as z:z.writestr('README.txt',b'a');z.writestr('Readme.txt',b'b')
            with self.assertRaisesRegex(ValueError,'duplicate'):audit_source(p)

    def test_actual_mit_source_is_reproducible_and_auditable(self):
        from tools.package_source import package
        from tools.audit_release import audit_source
        app=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            one=Path(folder)/'one.zip';two=Path(folder)/'two.zip'
            package(app,one);package(app,two);self.assertEqual(one.read_bytes(),two.read_bytes())
            result=audit_source(one);self.assertTrue(result['ok']);self.assertEqual(result['license'],'MIT')
            with zipfile.ZipFile(one) as z:
                self.assertIn(b'2026 RetchEWretched',(z.read('LICENSE')))
                config=json.loads(z.read('package.json'));self.assertEqual(config['devDependencies']['esbuild'],'0.25.12')
                self.assertEqual(config['type'],'module')

    def test_fresh_git_repository_stages_every_release_source_member(self):
        from tools.package_source import package,APPROVED_FILES
        if not shutil.which('git'):self.skipTest('Git is optional in the bundled runtime')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'source.zip';export=root/'export'
            package(Path(__file__).resolve().parents[1],archive)
            with zipfile.ZipFile(archive) as z:z.extractall(export)
            def git(*args):
                return subprocess.run(['git','-c','core.autocrlf=false',*args],cwd=export,check=True,capture_output=True).stdout
            git('init');git('add','--all')
            # Read every index object ID in one Git process. The previous
            # per-file rev-parse loop spent minutes on Windows process startup.
            indexed={}
            for entry in git('ls-files','--stage','-z').split(b'\0'):
                if not entry:continue
                metadata,name=entry.split(b'\t',1)
                _mode,object_id,stage=metadata.split(b' ')
                self.assertEqual(stage,b'0')
                name=name.decode('utf-8')
                self.assertNotIn(name,indexed)
                indexed[name]=object_id.decode('ascii')
            staged=set(indexed)
            self.assertEqual(staged,APPROVED_FILES)
            # Generated bundle metadata hashes literal source bytes. Git's LF
            # normalization must not silently change those inputs on upload.
            for name in sorted(staged):
                if name.endswith(('.py','.js','.mjs','.json','.css','.html','.txt','.yml','.patch')):
                    raw=(export/name).read_bytes()
                    expected=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
                    self.assertEqual(indexed[name],expected,name)

    def test_source_audit_requires_the_complete_runnable_buildable_inventory(self):
        from tools.package_source import package
        from tools.audit_release import audit_source
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.zip';changed=root/'changed.zip'
            package(Path(__file__).resolve().parents[1],source)
            with zipfile.ZipFile(source) as z:files={n:z.read(n) for n in z.namelist()}
            for missing in ['romancer/workbench_api.py','requirements.txt','tools/build_ui.mjs','examples/fake_trace.log']:
                with self.subTest(missing=missing):
                    with zipfile.ZipFile(changed,'w') as z:
                        for name,raw in files.items():
                            if name!=missing:z.writestr(name,raw)
                    with self.assertRaisesRegex(ValueError,'missing'):audit_source(changed)

    def test_windows_audit_rejects_rehashed_root_tampering_and_wrong_identity(self):
        from tools.package_source import package
        from tools.audit_release import audit_windows
        app=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.zip';windows=root/'windows.zip'
            package(app,source)
            # Real packager bytes without native downloads: only the runtime oracle is synthetic.
            from tools.package_windows import build_bundle,package_bundle
            runtime={'python':[('LICENSE.txt',b'Python notice')],
                     'pillow':[('pillow-12.3.0.dist-info/licenses/LICENSE',b'Pillow notice')]}
            # This audit fixture does not test host-specific directory publication.
            with patch('tools.package_windows.runtime_members',side_effect=lambda _p,_sha,kind:runtime[kind]), \
                 patch('romancer.patch_sets._publish_directory',side_effect=lambda a,b:a.rename(b)):
                build_bundle(app,root,root/'bundle');package_bundle(root/'bundle',windows)
                self.assertTrue(audit_windows(windows,source,root)['ok'])
                with zipfile.ZipFile(windows) as z:original={n:z.read(n) for n in z.namelist()}
                for name in ['Install ROMancer.cmd','Open ROMancer.cmd','Rollback ROMancer.cmd','Uninstall ROMancer.cmd','README.txt','ROMancer.ico']:
                    with self.subTest(name=name):
                        altered=dict(original);altered[name]=('exit /b 1\nC:/Users/'+'PrivateOwner/private').encode()
                        manifest=json.loads(altered['BUNDLE.json'])
                        for row in manifest['files']:
                            if row['path']==name:row.update(size=len(altered[name]),sha256=hashlib.sha256(altered[name]).hexdigest())
                        altered['BUNDLE.json']=json.dumps(manifest).encode()
                        with zipfile.ZipFile(windows,'w') as z:
                            for member,raw in altered.items():z.writestr(member,raw)
                        with self.assertRaises(ValueError):audit_windows(windows,source,root)
                for field in ['schema_version','product','version','release_name','build_label','install_layout']:
                    with self.subTest(field=field):
                        altered=dict(original);manifest=json.loads(altered['BUNDLE.json']);manifest[field]='wrong';altered['BUNDLE.json']=json.dumps(manifest).encode()
                        with zipfile.ZipFile(windows,'w') as z:
                            for member,raw in altered.items():z.writestr(member,raw)
                        with self.assertRaises(ValueError):audit_windows(windows,source,root)

                altered=dict(original);manifest=json.loads(altered['BUNDLE.json'])
                manifest['files'][0]['private_path']='C:/Users/'+'PrivateOwner/private'
                altered['BUNDLE.json']=json.dumps(manifest).encode()
                with zipfile.ZipFile(windows,'w') as z:
                    for member,raw in altered.items():z.writestr(member,raw)
                with self.assertRaises(ValueError):audit_windows(windows,source,root)
