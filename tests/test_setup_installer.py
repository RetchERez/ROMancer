import unittest
from tools.package_installer import literal,installer_script


class SetupTests(unittest.TestCase):
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
