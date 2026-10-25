import importlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


class ReleaseTests(unittest.TestCase):
    def test_cancellation_during_encoding_never_publishes(self):
        from unittest.mock import patch
        m=self.module()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'source';b=root/'target';a.write_bytes(b'a'*1024**2);b.write_bytes(b'b'*1024**2)
            commands=0;encode=m._encode_number
            def observed_encode(value):
                nonlocal commands
                commands+=1;return encode(value)
            # Three header integers, then two actual encoding commands, then cancel.
            with patch.object(m,'_encode_number',observed_encode):
                with self.assertRaises(KeyboardInterrupt):m.prepare_patch(a,b,root/'cancelled.bps',{'title':'Cancel','description':''},cancelled=lambda:commands>=5)
            self.assertEqual(commands,5)
            self.assertFalse((root/'cancelled.bps').exists());self.assertFalse(list(root.glob('.export-*')))

    def module(self):
        try:m=importlib.import_module('romancer.release')
        except ModuleNotFoundError:m=None
        self.assertIsNotNone(m,'independently verified release service is missing');return m

    def test_expand_truncate_independent_apply_wrong_source_and_original(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'original';source.write_bytes(b'abcdefgh')
            for index,target_bytes in enumerate((b'abXdefghNEW',b'abX')):
                target=root/('target'+str(index));target.write_bytes(target_bytes);patch=root/(str(index)+'.bps')
                result=m.prepare_patch(source,target,patch,{'title':'Original demo','description':'Literal edits'})
                self.assertTrue(result['ok'],result)
                self.assertEqual(m.apply_bps(source.read_bytes(),patch.read_bytes()),target_bytes)
                self.assertTrue(m.verify_patch(source,patch,result['target_sha256'])['ok'])
                with self.assertRaises(ValueError):m.apply_bps(b'bad source',patch.read_bytes())
                corrupt=bytearray(patch.read_bytes());corrupt[-1]^=1
                with self.assertRaises(ValueError):m.apply_bps(source.read_bytes(),corrupt)
            self.assertEqual(source.read_bytes(),b'abcdefgh')
            with self.assertRaises(ValueError):m.prepare_patch(source,source,source,{})

    def test_positive_manifest_paths_roles_and_clean_zip(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);doc=root/'instructions.txt';doc.write_text('By RetchEWretched')
            dest=root/'release.zip';manifest={'title':'Demo','files':[{'source':str(doc),'path':'README.txt','role':'documentation'}]}
            result=m.package_release(dest,manifest);self.assertTrue(result['ok'])
            with zipfile.ZipFile(dest) as archive:
                self.assertEqual(archive.read('README.txt'),b'By RetchEWretched')
                self.assertIn('MANIFEST.json',archive.namelist())
            for path,role in (('../escape','documentation'),('game.bin','rom'),('same','save')):
                manifest['files'][0].update(path=path,role=role)
                with self.assertRaises(ValueError):m.package_release(root/'other.zip',manifest)
