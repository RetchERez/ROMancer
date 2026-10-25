import unittest
import ctypes
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import zipfile
from tools.package_installer import literal,installer_script


class SetupTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows installer and sharing semantics')
    def test_cleanup_file_lock_does_not_report_a_published_installer_as_failed(self):
        from tools.package_installer import build_installer
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
        kernel.CreateFileW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handles=[];link=os.link;expected=b'Original setup fixture'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);payload=root/'payload';payload.mkdir();archive=root/'compiler.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('nsis-3.13/makensis.exe',b'Original compiler fixture')
            def compile_fixture(args,**kwargs):
                Path(args[-1]).with_name('Setup.exe').write_bytes(expected)
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            def publish_then_lock(source,destination):
                link(source,destination)
                handle=kernel.CreateFileW(str(source),0x80000000,3,None,3,0,None)
                self.assertNotEqual(handle,ctypes.c_void_p(-1).value);handles.append(handle)
            try:
                with patch('tools.package_installer.verify_tree',return_value={'manifest':{'version':'1.0.18','engines':{'included':True}},'manifest_sha256':'fixture'}),patch('romancer.bundled_cores.core_members',return_value={}),patch('tools.package_installer.NSIS_PIN',{'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}),patch('tools.package_installer.subprocess.run',side_effect=compile_fixture),patch('tools.package_installer.os.link',side_effect=publish_then_lock):
                    result=build_installer(payload,archive,root/'Released Setup.exe')
                self.assertTrue(result['ok']);self.assertEqual((root/'Released Setup.exe').read_bytes(),expected)
            finally:
                for handle in handles:kernel.CloseHandle(handle)

    def test_paths_are_literal_and_silent_install_has_no_forced_launch(self):
        escaped=literal('C:/work/$name/"quoted"')
        self.assertIn('$$name',escaped);self.assertIn('$\\"quoted$\\"',escaped)
        with self.assertRaises(ValueError):literal('bad\npath')
        with self.assertRaises(ValueError):installer_script('payload','setup.exe','1.0"\n!system evil')
        script=installer_script('payload','Setup.exe','1.0.17')
        self.assertIn('RequestExecutionLevel user',script);self.assertIn('MUI_FINISHPAGE_RUN_NOTCHECKED',script)
        self.assertIn('SetCompressor /SOLID zlib',script);self.assertNotIn('--launch',script)
        uninstall=script.split('Section "Uninstall"',1)[1]
        self.assertNotIn('RMDir /r',uninstall);self.assertNotIn('workspace\\*',uninstall)
        self.assertIn('/NOINTEGRATION',script)


if __name__=='__main__':unittest.main()
