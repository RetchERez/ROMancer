"""Original, read-only helpers for bounded cartridge integrity checks.

Additive checksums and header-logo fingerprints are format consistency evidence,
never trusted game-revision identification or proof of native boot/gameplay.
Only SHA-256 fingerprints are stored here; no Nintendo logo data is distributed.
"""
import hashlib


MAX_SNES_PAYLOAD = 8*1024**2
SNES_CHECKSUM_REFERENCE = 'https://snes.nesdev.org/wiki/ROM_header#Checksum'
SNES_MIRROR_REFERENCE = 'https://wiki.superfamicom.org/non-power-of-two-rom-size'
GB_HEADER_REFERENCE = ('https://github.com/gbdev/pandocs/blob/'
                       'abeda621759a8e2b322b368eacf4d31ec48eb4df/'
                       'src/The_Cartridge_Header.md#0104-0133--nintendo-logo')
GB_LOGO_SHA256 = 'daf4cabdc852baa0291849203f0b41fd0b4ecd58e0d7aff4a509f5de4d7f9a2e'


def snes_mirrored_checksum(payload: bytes) -> int:
    """Return the 16-bit byte sum under standard recursive tail mirroring.

    Input must be a headerless bytes payload, 32 KiB aligned and at most 8 MiB.
    The largest power-of-two prefix appears once; its remainder mirrors to fill
    an equally large second half, recursively for irregular remainder sizes.
    No expanded image is allocated, and each physical input byte is summed once.

    This helper neither detects nor establishes LoROM/HiROM/ExHiROM or an add-on
    board. The caller must establish that standard mirroring is appropriate and
    remove any identified copier header. Stored checksum/complement bytes are
    included as they are; a valid complementary pair contributes a constant sum.
    No checksum field, declared size, padding or source byte is modified.
    """
    if type(payload) is not bytes or not 32768 <= len(payload) <= MAX_SNES_PAYLOAD or len(payload) % 32768:
        raise ValueError('SNES payload must be headerless bytes in 32 KiB multiples, 32 KiB through 8 MiB')
    view = memoryview(payload)

    def weighted_sum(start, length):
        prefix = 1 << (length.bit_length()-1)
        total = sum(view[start:start+prefix])
        remainder = length-prefix
        if remainder:
            mirrored_size = 1 << ((remainder-1).bit_length())
            total += weighted_sum(start+prefix, remainder) * (prefix//mirrored_size)
        return total

    return weighted_sum(0, len(payload)) & 0xffff


def _check_result(name, status, detail, references, **extra):
    return {'name': name, 'status': status, 'detail': detail,
            'references': references, 'runtime_verified': False,
            'trusted_revision_match': False, 'write_authorized': False, **extra}


def _header_bytes(raw):
    if type(raw) not in (bytes, bytearray):
        raise ValueError('header checks require bytes or bytearray')


def check_boot_logo(raw, system_id):
    """Compare only a documented header region against a canonical fingerprint.

    Mismatches are WARN, since custom headers/homebrew or boot environments may
    intentionally differ. PASS confirms this region's format consistency only.
    GB/GBC compare all 48 bytes even though CGB boot checks only the first half.
    """
    _header_bytes(raw)
    if type(system_id) is not str or len(system_id) > 32:
        raise ValueError('system_id must be a short string')
    if system_id in ('gb', 'gbc'):
        offset, length, expected = (260, 48, GB_LOGO_SHA256)
        name, references = ('Game Boy header-logo fingerprint', [GB_HEADER_REFERENCE])
    else:
        return _check_result('Header-logo fingerprint', 'NOT_CHECKED', 'No canonical boot-logo check is implemented for this system.', [])
    if len(raw) < offset + length:
        return _check_result(name, 'NOT_CHECKED', 'The complete header-logo region is unavailable.', references, offset=offset, length=length)
    region = bytes(raw[offset:offset + length])
    observed = hashlib.sha256(region).hexdigest()
    fields = {'offset': offset, 'length': length, 'fingerprint_algorithm': 'sha256', 'expected_logo_sha256': expected, 'observed_logo_sha256': observed}
    compared = observed
    matches = compared == expected
    detail = 'Canonical header-logo fingerprint matches' + ('.') if matches else 'Header-logo fingerprint differs from the canonical reference; custom headers or homebrew may be intentional.'
    if system_id in ('gb', 'gbc'):
        detail += ' This compares all 48 bytes; CGB boot checks only the first 24.'
    detail += ' This is neither trusted revision identification nor native boot proof.'
    return _check_result(name, 'PASS' if matches else 'WARN', detail, references, **fields)
