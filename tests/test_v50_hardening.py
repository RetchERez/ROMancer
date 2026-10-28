import importlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import hashlib


class HardeningTests(unittest.TestCase):
    def test_distribution_contains_launchable_ui_and_independent_manifest(self):
        try:module=importlib.import_module('tools.package_v50')
        except ModuleNotFoundError:module=None
        self.assertIsNotNone(module,'v50 distribution packager is missing')
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'ROMancer.zip'
            report=module.package_v50(Path(__file__).resolve().parents[1],output)
            self.assertTrue(report['ok']);self.assertEqual(report['credit'],'By RetchEWretched')
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                for member in ('Launch ROMancer.cmd','launch.ps1','romancer/ui/app.js','romancer/workbench_server.py','README.txt',
                               'romancer/system_registry.py','romancer/system_formats/nes.py','romancer/system_resources.py'):
                    self.assertIn(member,archive.namelist())
                for row in report['members']:self.assertEqual(hashlib.sha256(archive.read(row['path'])).hexdigest(),row['sha256'])
                self.assertFalse(any('projects/' in name or '.romancer-evidence' in name for name in archive.namelist()))

    def test_scoped_matrix_runs_real_identification_build_and_patch_for_each_family(self):
        try:module=importlib.import_module('tools.verify_v50')
        except ModuleNotFoundError:module=None
        self.assertIsNotNone(module,'v50 acceptance verifier is missing')
        with tempfile.TemporaryDirectory() as temp:
            report=module.verify_v50(Path(temp))
            self.assertTrue(report['ok'],report)
            self.assertEqual(set(report['families']),{'NES','SNES','Genesis','Game Boy','Game Boy Color','Master System'})
            for family,result in report['families'].items():
                self.assertEqual(result['generic_workflow'],'PASS',family)
                self.assertEqual(result['private_game_runtime'],'NOT_RUN',family)
            self.assertFalse(report['full_game_compatibility_claimed'])
