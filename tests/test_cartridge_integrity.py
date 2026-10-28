"""Original synthetic payloads only; no Nintendo logo bytes or game data."""
import hashlib
import unittest
from unittest.mock import patch


def expanded_mirror(payload):
    """Independent oracle: physically duplicate trailing chunks to a power of 2."""
    expanded = bytearray(payload)
    while len(expanded) & (len(expanded)-1):
        trailing_unit = len(expanded) & -len(expanded)
        expanded.extend(expanded[-trailing_unit:])
    return sum(expanded) & 0xffff


class CartridgeIntegrityTests(unittest.TestCase):
    def test_mirrored_checksum_matches_expanded_oracle_for_every_bank_count(self):
        from romancer.cartridge_integrity import snes_mirrored_checksum
        # Each bank has a distinct, uneven sum. Zero-filled banks would hide
        # incorrect weights because a full 32 KiB constant bank cancels modulo.
        original = bytearray(8*1024**2)
        for bank in range(256):
            original[bank*32768] = bank % 251 + 1
            original[bank*32768+37] = (bank*17+9) % 256
        for banks in range(1, 257):
            payload = bytes(original[:banks*32768])
            with self.subTest(banks=banks):
                self.assertEqual(snes_mirrored_checksum(payload), expanded_mirror(payload))

    def test_three_six_and_irregular_mib_weight_the_tail_not_the_whole_image(self):
        from romancer.cartridge_integrity import snes_mirrored_checksum
        for length in (3*1024**2, 6*1024**2, 11*32768, 7*32768):
            raw = bytearray(length)
            for bank in range(length//32768):
                raw[bank*32768] = bank % 251
                raw[bank*32768+17] = (bank*13+1) % 256
            with self.subTest(length=length):
                payload = bytes(raw)
                self.assertEqual(snes_mirrored_checksum(payload), expanded_mirror(payload))
                self.assertNotEqual(snes_mirrored_checksum(payload), sum(payload) & 0xffff)
        raw = bytearray(3*32768)
        raw[0], raw[32768], raw[65536] = 1, 2, 3
        self.assertEqual(snes_mirrored_checksum(bytes(raw)), 9)  # A+B+C+C

    def test_checksum_includes_stored_header_bytes_and_rejects_copier_or_bad_size(self):
        from romancer.cartridge_integrity import snes_mirrored_checksum
        raw = bytearray(32768)
        raw[0x7fdc:0x7fe0] = bytes.fromhex('cbed3412')
        self.assertEqual(snes_mirrored_checksum(bytes(raw)), 510)
        for invalid in (b'', b'x', bytes(32767), bytes(32769), bytes(32768+512),
                        bytes(8*1024**2+32768), bytearray(32768), None, 32768):
            with self.subTest(invalid_type=type(invalid), length=len(invalid) if isinstance(invalid, (bytes, bytearray)) else None):
                with self.assertRaises(ValueError):
                    snes_mirrored_checksum(invalid)

    def test_missing_custom_and_unsupported_logo_checks_never_certify_boot(self):
        from romancer.cartridge_integrity import check_boot_logo
        for system, size in (('gb', 0x104+48), ('gbc', 0x104+48)):
            with self.subTest(system=system):
                absent = check_boot_logo(bytes(size-1), system)
                self.assertEqual(absent['status'], 'NOT_CHECKED')
                custom = check_boot_logo(bytes(size), system)
                self.assertEqual(custom['status'], 'WARN')
                self.assertEqual(len(custom['observed_logo_sha256']), 64)
                self.assertIn('custom', custom['detail'].lower())
                self.assertFalse(custom['runtime_verified'])
                self.assertFalse(custom['trusted_revision_match'])
                self.assertFalse(custom['write_authorized'])
        self.assertEqual(check_boot_logo(b'', 'nes')['status'], 'NOT_CHECKED')

    def test_logo_slicing_fingerprints_only_the_header_region_and_preserves_input(self):
        from romancer import cartridge_integrity as module
        # Substitute a digest of independently invented data, never real logos.
        synthetic = bytes((i*37+11) % 256 for i in range(48))
        digest = hashlib.sha256(synthetic).hexdigest()
        raw = bytearray(b'x'*0x104 + synthetic + b'not logo data')
        before = bytes(raw)
        with patch.object(module, 'GB_LOGO_SHA256', digest):
            for system in ('gb', 'gbc'):
                value = module.check_boot_logo(raw, system)
                self.assertEqual(value['status'], 'PASS')
                self.assertEqual(value['observed_logo_sha256'], digest)
                self.assertEqual(value['offset'], 0x104)
                self.assertEqual(value['length'], 48)
                self.assertFalse(value['trusted_revision_match'])
        self.assertEqual(bytes(raw), before)




if __name__ == '__main__':
    unittest.main()
