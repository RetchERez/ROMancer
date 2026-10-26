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
GBA_HEADER_REFERENCE = 'https://problemkaputt.de/gbatek.htm#gbacartridgeheader'
GBA_FINGERPRINT_REFERENCE = ('https://github.com/devkitPro/gba-tools/blob/'
                             '054d507f90d32784274b6cf7e03f1c43d02d7a57/'
                             'src/gbafix.c')

# Derived privately from the primary references' canonical header regions.
# Pan Docs publishes the 48-byte GB logo. devkitPro's primary gbafix reference
# supplies the 156-byte GBA region; only its fingerprint is used, no source code.
GB_LOGO_SHA256 = 'daf4cabdc852baa0291849203f0b41fd0b4ecd58e0d7aff4a509f5de4d7f9a2e'
GBA_LOGO_SHA256 = '08a0153cfd6b0ea54b938f7d209933fa849da0d56f5a34c481060c9ff2fad818'


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
    GBA's documented variable bits are normalized in a private 156-byte copy;
    the literal observed-region and normalized-region hashes remain distinct.
    """
    _header_bytes(raw)
    if type(system_id) is not str or len(system_id) > 32:
        raise ValueError('system_id must be a short string')
    if system_id in ('gb', 'gbc'):
        offset, length, expected = 0x104, 48, GB_LOGO_SHA256
        name, references = 'Game Boy header-logo fingerprint', [GB_HEADER_REFERENCE]
    elif system_id == 'gba':
        offset, length, expected = 4, 156, GBA_LOGO_SHA256
        name, references = 'GBA header-logo fingerprint', [GBA_HEADER_REFERENCE, GBA_FINGERPRINT_REFERENCE]
    else:
        return _check_result('Header-logo fingerprint', 'NOT_CHECKED',
                             'No canonical boot-logo check is implemented for this system.', [])
    if len(raw) < offset+length:
        return _check_result(name, 'NOT_CHECKED', 'The complete header-logo region is unavailable.',
                             references, offset=offset, length=length)
    region = bytes(raw[offset:offset+length])
    observed = hashlib.sha256(region).hexdigest()
    fields = {'offset': offset, 'length': length, 'fingerprint_algorithm': 'sha256',
              'expected_logo_sha256': expected, 'observed_logo_sha256': observed}
    compared = observed
    if system_id == 'gba':
        normalized = bytearray(region)
        # GBATEK: 09C bits 2/7 and 09E bits 0/1 may vary. Clear just those
        # bits to the canonical settings; every other bit remains significant.
        normalized[0x9c-4] &= 0x7b
        normalized[0x9e-4] &= 0xfc
        compared = hashlib.sha256(normalized).hexdigest()
        fields.update(normalized_logo_sha256=compared,
                      normalization='Only header 009C bits 2/7 and 009E bits 0/1 cleared as permitted by GBATEK.')
    matches = compared == expected
    detail = ('Canonical header-logo fingerprint matches' +
              (' after documented variable-bit normalization.' if system_id == 'gba' else '.')) if matches else (
              'Header-logo fingerprint differs from the canonical reference; custom headers or homebrew may be intentional.')
    if system_id in ('gb', 'gbc'):
        detail += ' This compares all 48 bytes; CGB boot checks only the first 24.'
    detail += ' This is neither trusted revision identification nor native boot proof.'
    return _check_result(name, 'PASS' if matches else 'WARN', detail, references, **fields)


def check_gba_fixed_header(raw):
    """Check the documented GBA 00B2 fixed byte independently of the logo."""
    _header_bytes(raw)
    name, references = 'GBA fixed header byte', [GBA_HEADER_REFERENCE]
    if len(raw) <= 0xb2:
        return _check_result(name, 'NOT_CHECKED', 'Header byte 00B2 is unavailable.', references)
    stored = raw[0xb2]
    return _check_result(name, 'PASS' if stored == 0x96 else 'WARN',
                         'GBATEK specifies 96 at header byte 00B2; this does not establish native boot.',
                         references, offset=0xb2, stored=f'{stored:02X}', expected='96')
