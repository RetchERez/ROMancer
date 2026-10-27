import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class BundledDebuggerTests(unittest.TestCase):
    def test_observer_pack_requires_every_pinned_source_and_notice_and_no_extra_file(self):
        from romancer.bundled_debuggers import observer_files
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);files={'mesence-2.2.1/Core.dll':b'original fixture','mesence-2.2.1/source.zip':b'corresponding source','mame-0.289/COPYING':b'license'}
            pins={}
            for name,raw in files.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                pins[name]={'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            with patch('romancer.bundled_debuggers.OBSERVER_FILES',pins):
                self.assertEqual(set(observer_files(root)),set(files))
                (root/'private.rom').write_bytes(b'private')
                with self.assertRaises(ValueError):observer_files(root)
                (root/'private.rom').unlink();(root/'mesence-2.2.1/source.zip').write_bytes(b'changed')
                with self.assertRaises(ValueError):observer_files(root)
    def test_current_bundled_observer_wins_over_an_old_cache_without_silent_fallback(self):
        from romancer.debugger_provision import preferred_root,cache_root
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/'work';old=cache_root(work,'nes');old.mkdir(parents=True);bundled=root/'debuggers/mesence-2.2.1';bundled.mkdir(parents=True)
            with patch('romancer.native_debugger.backend_root',return_value=bundled):
                self.assertEqual(preferred_root(work,'nes'),bundled)
