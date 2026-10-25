"""Bundled-runtime inventory and installer collision checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


def require_directory_publication(test):
    from romancer.patch_sets import _publish_directory,DirectoryPublicationUnavailable
    with tempfile.TemporaryDirectory() as temp:
        source=Path(temp)/'s';source.mkdir()
        try:_publish_directory(source,Path(temp)/'t')
        except DirectoryPublicationUnavailable as exc:test.skipTest(str(exc))


class WindowsPackageTests(unittest.TestCase):
    def test_upgrade_and_rollback_keep_both_verified_versions(self):
        require_directory_publication(self)
        from tools.install_windows import install,rollback,verify_tree
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);destination=root/'installed'
            for version in ('60.0.0','60.0.1'):
                payload=root/version;payload.mkdir();launcher=payload/'Open ROMancer.ps1';launcher.write_text(version)
                row={'path':launcher.name,'size':launcher.stat().st_size,'sha256':hashlib.sha256(launcher.read_bytes()).hexdigest()}
                (payload/'BUNDLE.json').write_text(json.dumps({'schema_version':1,'product':'ROMancer','version':version,'files':[row]}))
                install(payload,destination)
            rollback(destination)
            self.assertEqual(json.loads((destination/'active.json').read_text())['version'],'60.0.0')
            for version in ('60.0.0','60.0.1'):self.assertTrue(verify_tree(destination/'versions'/version)['ok'])

    def test_runtime_archives_require_exact_pins_and_safe_positive_paths(self):
        from tools.package_windows import runtime_members
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'python.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.dll',b'bad')
            digest=hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):runtime_members(archive,digest,'python')
            with self.assertRaises(ValueError):runtime_members(archive,'0'*64,'python')
            with zipfile.ZipFile(archive,'w') as z:z.writestr('python.exe',b'fake');z.writestr('Python.exe',b'collision')
            with self.assertRaises(ValueError):runtime_members(archive,hashlib.sha256(archive.read_bytes()).hexdigest(),'python')

    def test_install_verifies_every_member_and_preserves_workspace_on_upgrade(self):
        require_directory_publication(self)
        from tools.install_windows import install,verify_tree,uninstall
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);payload=root/'payload';payload.mkdir();(payload/'Open ROMancer.ps1').write_text('launcher');(payload/'app').mkdir();(payload/'app/main.py').write_text('original')
            entries=[{'path':p.relative_to(payload).as_posix(),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in payload.rglob('*') if p.is_file()]
            (payload/'BUNDLE.json').write_text(json.dumps({'schema_version':1,'product':'ROMancer','version':'60.0.0','files':entries}))
            destination=root/'installed';workspace=destination/'workspace';workspace.mkdir(parents=True);(workspace/'keep.txt').write_text('my project')
            result=install(payload,destination);self.assertTrue(result['ok']);self.assertEqual((workspace/'keep.txt').read_text(),'my project')
            self.assertEqual(json.loads((destination/'active.json').read_text())['version'],'60.0.0')
            self.assertTrue(verify_tree(destination/'versions/60.0.0')['ok'])
            (payload/'app/main.py').write_text('changed')
            with self.assertRaises(ValueError):install(payload,destination)
            self.assertEqual((destination/'versions/60.0.0/app/main.py').read_text(),'original')
            self.assertEqual((workspace/'keep.txt').read_text(),'my project')
            uninstall(destination);self.assertEqual((workspace/'keep.txt').read_text(),'my project');self.assertFalse((destination/'active.json').exists())

    def test_unlisted_input_and_path_escape_refuse_before_publication(self):
        from tools.install_windows import install
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);payload=root/'payload';payload.mkdir();(payload/'private.bin').write_bytes(b'private')
            (payload/'BUNDLE.json').write_text(json.dumps({'schema_version':1,'product':'ROMancer','version':'60.0.0','files':[]}))
            with self.assertRaises(ValueError):install(payload,root/'output')
            self.assertFalse((root/'output/active.json').exists())
