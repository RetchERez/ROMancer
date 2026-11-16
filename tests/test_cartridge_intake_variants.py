import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from romancer.system_identify import identify_system


def snes_header(mode=0x20, chip=0, title=b'ORIGINAL FORMAT TEST'):
    raw=bytearray(32768);at=0x7fc0
    raw[at:at+21]=title.ljust(21,b' ')[:21]
    raw[at+21]=mode;raw[at+22]=chip;raw[at+23]=5
    raw[at+28:at+32]=bytes([255,255,0,0]);raw[at+60:at+62]=bytes([0,128])
    return raw


class CartridgeIntakeVariantTests(unittest.TestCase):
    def identify(self,raw):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'original.bin';path.write_bytes(raw)
            result=identify_system(path,expected_sha256=hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(),raw)
            self.assertFalse(result['write_authorized']);self.assertFalse(result['runtime_verified'])
            return result

    def test_documented_chip_headers_identify_physical_container_without_claiming_cpu_mapping(self):
        # A missing map-mode branch rejects valid SA-1/S-DD1 file headers.
        for mode,chip,hardware in[(0x23,0x34,'sa1'),(0x23,0x35,'sa1'),(0x32,0x43,'sdd1'),(0x32,0x45,'sdd1')]:
            with self.subTest(mode=mode,chip=chip):
                result=self.identify(snes_header(mode,chip))
                self.assertEqual(result['status'],'IDENTIFIED',result)
                self.assertEqual(result['system_id'],'snes')
                selected=next(c for c in result['candidates']if c['layout_valid'])
                self.assertEqual(selected['format'],'lorom')
                self.assertEqual(selected['metadata']['cartridge_hardware'],hardware)
                self.assertEqual(selected['metadata']['cartridge_type'],chip)
                self.assertEqual(selected['metadata']['address_mapping'],'NOT_INFERRED')

    def test_special_map_modes_require_their_documented_chip_type(self):
        for mode,chip in[(0x23,0),(0x23,0x43),(0x32,0x35),(0x32,0xff)]:
            with self.subTest(mode=mode,chip=chip):
                result=self.identify(snes_header(mode,chip))
                self.assertEqual(result['status'],'BLOCKED',result)
                self.assertIsNone(result['system_id'])
                self.assertFalse(any(c['layout_valid']for c in result['candidates']))

    def test_non_ascii_title_does_not_hide_an_otherwise_checked_header(self):
        # Header title encoding is not a physical ROM-region boundary.
        result=self.identify(snes_header(title=b'FORMAT '+bytes([0x83,0x91])+b' TEST'))
        self.assertEqual(result['status'],'IDENTIFIED',result)
        selected=next(c for c in result['candidates']if c['layout_valid'])
        self.assertFalse(selected['metadata']['title_ascii'])
        self.assertEqual(selected['metadata']['title'],'Non-ASCII header title')
        self.assertEqual(result['regions'][0],{'id':'rom','kind':'program','offset':0,'length':32768})

    def test_non_ascii_title_never_bypasses_checksum_pair_or_size_checks(self):
        raw=snes_header(title=bytes([0x83])*21);raw[0x7fdc]^=1
        self.assertEqual(self.identify(raw)['status'],'BLOCKED')
        raw=snes_header(title=bytes([0x83])*21);raw[0x7fd7]=6
        self.assertEqual(self.identify(raw)['status'],'BLOCKED')

    def test_genesis_console_field_accepts_ascii_space_padding(self):
        raw=bytearray(1024);raw[0x100:0x110]=b' SEGA MEGA DRIVE'
        raw[0x1a4:0x1a8]=bytes([0,0,3,255])
        result=self.identify(raw)
        self.assertEqual(result['status'],'IDENTIFIED',result)
        self.assertEqual(result['system_id'],'genesis')

    def test_padded_console_field_never_admits_a_larger_declared_linear_image(self):
        raw=bytearray(1024);raw[0x100:0x110]=b' SEGA MEGA DRIVE'
        raw[0x1a4:0x1a8]=bytes([0,0x13,255,255])
        result=self.identify(raw)
        self.assertEqual(result['status'],'BLOCKED',result)
        raw[0x100]=9
        self.assertNotEqual(self.identify(raw)['status'],'IDENTIFIED')

    def test_registered_nonstandard_header_layout_survives_content_and_checksum_edits(self):
        from romancer.system_formats import snes
        raw=snes_header(mode=0x44)
        signature=hashlib.sha256(raw[0x7fc0:0x7fdc]+raw[0x7fe0:0x8000]).hexdigest()
        registry={(32768,0x7fc0,signature):'lorom'}
        with patch.dict(snes.__dict__,{'NONSTANDARD_HEADERS':registry}):
            value=self.identify(raw)
            self.assertEqual(value['status'],'IDENTIFIED',value)
            candidate=next(c for c in value['candidates']if c['layout_valid'])
            self.assertEqual(candidate['metadata']['layout_signature_sha256'],signature)
            self.assertEqual(candidate['metadata']['address_mapping'],'NOT_INFERRED')
            raw[0]=0xea
            raw[0x7fdc:0x7fe0]=bytes([0x34,0x12,0xcb,0xed])
            self.assertEqual(self.identify(raw)['status'],'IDENTIFIED')
            raw[0x7fdc]^=1
            self.assertEqual(self.identify(raw)['status'],'BLOCKED')

    def test_unregistered_or_changed_nonstandard_headers_stay_unidentified(self):
        from romancer.system_formats import snes
        raw=snes_header(mode=0x53)
        signature=hashlib.sha256(raw[0x7fc0:0x7fdc]+raw[0x7fe0:0x8000]).hexdigest()
        registry={(32768,0x7fc0,signature):'lorom'}
        self.assertEqual(self.identify(raw)['status'],'UNKNOWN')
        with patch.dict(snes.__dict__,{'NONSTANDARD_HEADERS':registry}):
            self.assertEqual(self.identify(raw)['status'],'IDENTIFIED')
            changed=raw+bytearray(32768)
            self.assertNotEqual(self.identify(changed)['status'],'IDENTIFIED')
            raw[0x7fc1]^=1
            self.assertEqual(self.identify(raw)['status'],'UNKNOWN')

    def test_nonstandard_header_build_maintains_checksum_without_normalizing_mode(self):
        from romancer.system_formats import snes
        from romancer.system_integrity import integrity_edits
        raw=snes_header(mode=0x53)
        signature=hashlib.sha256(raw[0x7fc0:0x7fdc]+raw[0x7fe0:0x8000]).hexdigest()
        with tempfile.TemporaryDirectory()as directory,patch.dict(snes.__dict__,{'NONSTANDARD_HEADERS':{(32768,0x7fc0,signature):'lorom'}}):
            path=Path(directory)/'original.sfc';path.write_bytes(raw)
            try:edits=integrity_edits(path,hashlib.sha256(raw).hexdigest(),'snes',[{'offset':0,'before':'00','after':'ea'}])
            except ValueError as error:self.fail('A checked nonstandard layout must support fixed edits: '+str(error))
            changed=bytearray(raw)
            for edit in edits:
                offset=edit['offset'];before=bytes.fromhex(edit['before']);after=bytes.fromhex(edit['after'])
                self.assertEqual(raw[offset:offset+len(before)],before)
                changed[offset:offset+len(after)]=after
            self.assertEqual(changed[0],0xea)
            self.assertEqual(changed[0x7fd5],0x53)
            stored=int.from_bytes(changed[0x7fde:0x7fe0],'little')
            self.assertEqual(sum(changed)&65535,stored)
            self.assertEqual(int.from_bytes(changed[0x7fdc:0x7fde],'little')^stored,65535)
            self.assertEqual(path.read_bytes(),raw)
            self.assertEqual(self.identify(changed)['status'],'IDENTIFIED')

    def test_checksum_maintenance_ignores_a_rejected_earlier_header(self):
        from romancer.system_integrity import integrity_edits
        raw=snes_header(title=bytes([0x83])*21)+bytearray(32768)
        # The early LoROM header declares 32KiB, so cannot describe this 64KiB file.
        raw[0xffc0:0x10000]=snes_header(mode=0x21)[0x7fc0:0x8000]
        raw[0xffd7]=6
        identified=self.identify(raw)
        self.assertFalse(identified['candidates'][0]['layout_valid'])
        self.assertEqual(next(c for c in identified['candidates']if c['layout_valid'])['format'],'hirom')
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'source.sfc';path.write_bytes(raw)
            edits=integrity_edits(path,hashlib.sha256(raw).hexdigest(),'snes',[{'offset':0,'before':'00','after':'ea'}])
            self.assertEqual([e['offset']for e in edits],[0,0xffdc])
            changed=bytearray(raw)
            for edit in edits:changed[edit['offset']:edit['offset']+len(bytes.fromhex(edit['after']))]=bytes.fromhex(edit['after'])
            self.assertEqual(changed[0x7fdc:0x7fe0],raw[0x7fdc:0x7fe0])
            self.assertEqual(sum(changed)&65535,int.from_bytes(changed[0xffde:0xffe0],'little'))
            self.assertEqual(path.read_bytes(),raw)
