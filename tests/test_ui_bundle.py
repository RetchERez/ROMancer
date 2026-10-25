import hashlib
import json
from pathlib import Path
import unittest


class UIBundleTests(unittest.TestCase):
    def test_classic_desktop_bundle_is_bound_to_current_sources(self):
        root=Path(__file__).resolve().parents[1];ui=root/'romancer/ui'
        manifest=json.loads((ui/'bundle.json').read_bytes())
        self.assertEqual(manifest['builder'],'esbuild@0.25.12')
        for name,sha in manifest['sources'].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),sha,name+' needs UI rebuild')
        bundle=(ui/'app.bundle.js').read_bytes()
        self.assertEqual(hashlib.sha256(bundle).hexdigest(),manifest['sha256'])
        self.assertNotIn(b'import(',bundle)
        self.assertNotIn("import(", (ui/'startup.js').read_text())
        self.assertIn('app.bundle.js',(ui/'startup.js').read_text())
