import shutil,subprocess,unittest
from pathlib import Path
@unittest.skipUnless(shutil.which('git'),'Git patch parser not installed')
class NativeSourcePatchTests(unittest.TestCase):
    def test_reviewed_native_patches_are_complete_parseable_unified_diffs(self):
        root=Path(__file__).resolve().parents[1]
        for name,count in [('mesen-graphics.patch',4),('blastem-sms-input.patch',3)]:
            r=subprocess.run(['git','apply','--numstat',str(root/'tools/patches'/name)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(len(r.stdout.strip().splitlines()),count)
