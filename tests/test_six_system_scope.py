"""Current release scope applies to both fresh and saved requests."""
import unittest
from romancer.system_registry import system_inventory, get_system
from romancer.release_scope import SYSTEMS, require_supported
from romancer.core_pins import CORE_PINS, CORE_FILES
from romancer.contracts import ADAPTER_IDS

class SixSystemScopeTests(unittest.TestCase):
    systems={'nes','snes','genesis','gb','gbc','sms'}

    def test_every_retained_default_editor_build_matches_an_independent_byte_oracle(self):
        import tempfile
        from tools.verify_v60 import verify
        with tempfile.TemporaryDirectory() as temp:
            result=verify(temp)
        self.assertTrue(result['ok']);self.assertEqual({r['system_id'] for r in result['systems']},self.systems)
        self.assertTrue(all(r['structured_build_matches_oracle'] and r['patch_verified'] for r in result['systems']))

    def test_one_system_scope_for_registry_contracts_and_engine_pins(self):
        self.assertEqual(set(SYSTEMS),self.systems)
        self.assertEqual({p['id'] for p in system_inventory()['systems']},self.systems)
        self.assertEqual(set(ADAPTER_IDS),self.systems)
        # The alternate DSP-4 binary is a checked SNES profile, within the same six systems.
        self.assertEqual(set(CORE_PINS),{'nes','snes','snes-dsp4','genesis','gb','gbc-tilt'})
        self.assertIn(CORE_PINS['snes-dsp4']['file'],CORE_FILES)
        self.assertNotIn('mgba_libretro.dll',CORE_FILES)
        self.assertIn('mgba_gbc_libretro.dll',CORE_FILES)

    def test_excluded_saved_identity_is_not_a_supported_system(self):
        with self.assertRaises(ValueError):get_system('gba')
        with self.assertRaises(ValueError):require_supported({'system_id':'gba'})

    def test_removed_header_has_no_supported_candidate(self):
        from romancer.system_identify import identify_system
        import tempfile
        from pathlib import Path
        data=bytearray(1024);data[0xa0:0xac]=b'REMOVED TEST';data[0xb2]=0x96
        data[0xbd]=(-sum(data[0xa0:0xbd])-0x19)&255
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'removed.gba';path.write_bytes(data)
            result=identify_system(path)
            self.assertFalse(any(c.get('system_id')=='gba' for c in result.get('candidates',[])))
