import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name=='nt','Windows directory publication')
class WindowsPublicationTests(unittest.TestCase):
    def test_transient_sharing_refusal_retries_atomic_rename_without_overwrite(self):
        from romancer.patch_sets import _publish_directory
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'staging';source.mkdir();(source/'owned.txt').write_text('original');target=root/'published'
            real_rename=os.rename;attempts=[]
            def transient(a,b):
                attempts.append(1)
                if len(attempts)==1:
                    error=PermissionError('temporary Windows sharing refusal');error.winerror=5;raise error
                return real_rename(a,b)
            with patch('romancer.patch_sets.os.rename',side_effect=transient):_publish_directory(source,target)
            self.assertEqual(len(attempts),2);self.assertEqual((target/'owned.txt').read_text(),'original');self.assertFalse(source.exists())
            another=root/'next';another.mkdir()
            with self.assertRaises(ValueError):_publish_directory(another,target)
            self.assertTrue(another.is_dir());self.assertEqual((target/'owned.txt').read_text(),'original')

    def test_large_verified_bundle_can_wait_for_a_bounded_scanner_lock(self):
        from romancer.patch_sets import _publish_directory
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'staging';source.mkdir();target=root/'ready';real=os.rename;attempts=[]
            def scanner(a,b):
                attempts.append(1)
                if len(attempts)<9:
                    error=PermissionError('scanner still checks new native files');error.winerror=32;raise error
                return real(a,b)
            with patch('romancer.patch_sets.os.rename',side_effect=scanner),patch('time.sleep') as sleep:
                _publish_directory(source,target)
            self.assertTrue(target.is_dir());self.assertEqual(len(attempts),9)
            self.assertLessEqual(sum(c.args[0] for c in sleep.call_args_list),30)
