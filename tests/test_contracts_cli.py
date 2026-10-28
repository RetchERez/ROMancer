import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ContractsCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer contract CLI ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifact = self.root / 'synthetic original.bin'
        self.artifact.write_bytes(b'ABCD')
        self.path = self.root / 'profile.json'
        self.profile = {'schema_version': 2, 'id': 'synthetic', 'version': '1', 'system': 'nes',
                        'accepted_sha256': [hashlib.sha256(b'ABCD').hexdigest()],
                        'rules': [{'resource': 'text', 'offset': 1, 'length': 2, 'expected_hex': '4243'}]}
        self.path.write_text(json.dumps(self.profile), encoding='utf-8')

    def cli(self, *args):
        result = subprocess.run([sys.executable, '-m', 'romancer', *map(str, args), '--json'],
                                capture_output=True, text=True, timeout=30)
        self.assertTrue(result.stdout, result.stderr[-600:])
        return result.returncode, json.loads(result.stdout)

    def test_adapter_inventory_is_explicit(self):
        code, result = self.cli('adapter-inventory')
        self.assertEqual(code, 0, result)
        self.assertEqual({item['id'] for item in result['adapters']},
                         {'nes', 'snes', 'genesis', 'gb', 'gbc', 'gba', 'sms'})
        self.assertFalse(result['write_authorized'])

    def test_profile_revision_check_does_not_authorize_write(self):
        code, result = self.cli('profile-contract-check', self.path, self.artifact)
        self.assertEqual(code, 0, result)
        self.assertTrue(result['revision_match'])
        self.assertFalse(result['write_authorized'])
        self.artifact.write_bytes(b'ABCE')
        code, result = self.cli('profile-contract-check', self.path, self.artifact)
        self.assertEqual(code, 1, result)
        self.assertFalse(result['ok'])
        self.assertEqual(self.artifact.read_bytes(), b'ABCE')

    def test_invalid_profile_is_structured_nonzero(self):
        self.profile['rules'][0]['offset'] = True
        self.path.write_text(json.dumps(self.profile), encoding='utf-8')
        code, result = self.cli('profile-contract-check', self.path, self.artifact)
        self.assertEqual(code, 1, result)
        self.assertFalse(result['write_authorized'])
        self.assertEqual(self.artifact.read_bytes(), b'ABCD')

    def test_duplicate_keys_fail_before_contract_service(self):
        self.path.write_text('{"id":"a","id":"b"}', encoding='utf-8')
        code, result = self.cli('profile-contract-check', self.path, self.artifact)
        self.assertEqual(code, 1, result)
        self.assertIn('duplicate', result['error'])

    def test_large_valid_contract_and_oversized_input(self):
        payload = b'X' * (4 * 1048576)
        self.artifact.write_bytes(payload)
        self.profile['accepted_sha256'] = [hashlib.sha256(payload).hexdigest()]
        self.profile['rules'] = [
            {'resource': f'block{i}', 'offset': i * 1048576,
             'length': 1048576, 'expected_hex': '58' * 1048576} for i in range(4)]
        self.path.write_text(json.dumps(self.profile), encoding='utf-8')
        code, result = self.cli('profile-contract-check', self.path, self.artifact)
        self.assertEqual(code, 0, result)
        self.assertTrue(result['revision_match'])
        self.assertFalse(result['write_authorized'])
        self.assertEqual(self.artifact.read_bytes(), payload)
        self.path.write_bytes(b' ' * (32 * 1048576 + 1))
        code, result = self.cli('profile-contract-check', self.path, self.artifact)
        self.assertEqual(code, 1, result)

    def test_legacy_profile_preserved_as_historical(self):
        raw = b'{"version":"31.0.0", "verified_routes": {"old": ["old observation"]}}'
        self.path.write_bytes(raw)
        code, result = self.cli('profile-import-legacy', self.path)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['status'], 'HISTORICAL_UNVERIFIED')
        self.assertFalse(result['write_authorized'])
        self.assertEqual(self.path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
