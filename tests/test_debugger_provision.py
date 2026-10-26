import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


class DebuggerProvisionTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.debugger_provision'),'Pinned first-use debugger preparation is missing.')
        from romancer import debugger_provision
        return debugger_provision

    def test_metadata_is_fixed_upstream_scoped_and_separate_from_bundled_cores(self):
        m=self.module()
        for system in ('nes','snes','genesis','gb','gbc','gba'):
            info=m.download_info(system)
            self.assertFalse(info['bundled']);self.assertTrue(info['requires_network']);self.assertGreater(info['download_bytes'],1000000)
            self.assertTrue(info['upstream'].startswith('https://github.com/'))
        with self.assertRaises(ValueError):m.download_info('unknown')

    def test_redirects_never_downgrade_or_leave_official_asset_hosts(self):
        m=self.module();handler=m.OfficialRedirect()
        import urllib.request
        request=urllib.request.Request('https://github.com/official')
        for url in ('http://github.com/asset','https://evil.example/asset','file:///C:/anything'):
            with self.assertRaises(ValueError):handler.redirect_request(request,None,302,'',{},url)

    def test_download_hash_size_and_cancel_are_checked_before_execution(self):
        m=self.module()
        class Response(io.BytesIO):
            def geturl(self):return 'https://release-assets.githubusercontent.com/fixed'
        class Opener:
            def open(self,*args,**kwargs):return Response(b'abc')
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'build_opener',return_value=Opener()):
            root=Path(folder);digest=hashlib.sha256(b'abc').hexdigest()
            m.download('https://github.com/fixed',root/'good',3,digest,cancelled=lambda:False)
            self.assertEqual((root/'good').read_bytes(),b'abc')
            for name,size,sha in [('wrong-hash',3,'0'*64),('too-long',2,digest),('too-short',4,digest)]:
                with self.subTest(name=name),self.assertRaises(ValueError):m.download('https://github.com/fixed',root/name,size,sha,cancelled=lambda:False)
            with self.assertRaises(KeyboardInterrupt):m.download('https://github.com/fixed',root/'cancel',3,digest,cancelled=lambda:True)

    def test_zip_only_extracts_the_one_pinned_executable_name(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'input.zip';output=root/'output';output.mkdir()
            for name in ('../Mesen.exe','folder/Mesen.exe','evil.exe'):
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,b'bad')
                with self.assertRaises(ValueError):m.extract_mesen(archive,output,cancelled=lambda:False)
            self.assertEqual(list(output.iterdir()),[])

    def test_destination_is_workspace_owned_and_cannot_be_selected_by_client(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            workspace=Path(folder)
            self.assertEqual(m.cache_root(workspace,'gba'),workspace/'debuggers'/'mesence-2.2.1')
            self.assertEqual(m.cache_root(workspace,'genesis'),workspace/'debuggers'/'mame-0.289')
        from romancer.mcp_server import WRITE_OPERATIONS,_investigation_properties
        self.assertIn('debugger.prepare',WRITE_OPERATIONS)
        self.assertEqual(set(_investigation_properties('debugger.prepare')),{'project_id','artifact_id'})

    def test_cached_binary_alone_does_not_replace_missing_notices_and_source_metadata(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);m.cache_root(root,'nes').mkdir(parents=True)
            with patch('romancer.native_debugger.verify_backend',return_value={'backend':'MesenCE'}),\
                    patch.object(m,'download_info',return_value={'preparable':True}),\
                    patch.object(m,'materialize_mesen',side_effect=ValueError('A new verified download is required.')):
                with self.assertRaises(ValueError):m.prepare_backend(root,'nes')

    def test_non_object_source_metadata_is_a_validation_error(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'backend.json').write_text('[]',encoding='utf-8')
            with patch('romancer.native_debugger.verify_backend',return_value={}):
                with self.assertRaises(ValueError):m.verify_prepared(root,'nes')

    def test_activation_can_copy_verified_files_when_windows_refuses_directory_move(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'runtime';source.mkdir();target=root/'cache'
            (source/'program').write_bytes(b'verified');(source/'backend.json').write_bytes(b'{}')
            with patch.object(m.os,'rename',side_effect=PermissionError('temporary directory lock')),\
                    patch.object(m,'verify_prepared',return_value={'backend':'test'}):
                m.activate(source,target,'nes',cancelled=lambda:False)
            self.assertEqual((target/'program').read_bytes(),b'verified')
            self.assertEqual((target/'backend.json').read_bytes(),b'{}')

    def test_deferred_cleanup_only_removes_marked_owned_install_stages(self):
        m=self.module();import json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);parent=root/'sessions/debugger-install';parent.mkdir(parents=True)
            pending=parent/('a'*32);pending.mkdir();(pending/'official-package').write_bytes(b'package')
            (pending/'cleanup.json').write_text(json.dumps({'kind':'romancer-debugger-cleanup-v1'}),encoding='utf-8')
            active=parent/('b'*32);active.mkdir();(active/'in-progress').write_bytes(b'keep')
            unrelated=parent/'keep';unrelated.mkdir()
            report=m.cleanup_pending_stages(root)
            self.assertEqual(report['removed'],1);self.assertFalse(pending.exists())
            self.assertTrue(active.exists());self.assertTrue(unrelated.exists())

    def test_repair_preserves_changed_cache_and_activates_a_new_verified_generation(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);old=m.cache_root(root,'nes');old.mkdir(parents=True);(old/'user-changed-file').write_bytes(b'preserve')
            def materialize(job,runtime,**kwargs):
                (runtime/'good').write_bytes(b'verified');return {'backend':'test'}
            def verify(path,system):
                if not (path/'good').exists():raise ValueError('changed cache')
                return {'backend':'test'}
            with patch.object(m,'download_info',return_value={'preparable':True}),\
                    patch.object(m,'materialize_mesen',side_effect=materialize),patch.object(m,'verify_prepared',side_effect=verify):
                result=m.prepare_backend(root,'nes')
                self.assertTrue(result['ok']);self.assertTrue(result['repaired'])
                self.assertNotEqual(m.cache_root(root,'nes'),old)
                self.assertEqual((old/'user-changed-file').read_bytes(),b'preserve')
                self.assertTrue((m.cache_root(root,'nes')/'good').exists())
