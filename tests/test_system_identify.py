import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class ReaderTests(unittest.TestCase):
    def test_bounded_reads_stale_identity_and_same_length_mutation(self):
        from romancer.system_reader import SystemReader
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'source Ω with spaces.bin';path.write_bytes(b'ABCDEFGH')
            expected=hashlib.sha256(b'ABCDEFGH').hexdigest()
            with SystemReader(path,expected_sha256=expected) as reader:
                self.assertEqual(reader.identity,{'sha256':expected,'size':8})
                self.assertEqual(reader.read_at(2,3),b'CDE')
            for offset,length in ((True,1),(-1,1),(0,True),(0,0),(0,65537),(7,2)):
                with self.subTest(offset=offset,length=length),self.assertRaises(ValueError):
                    with SystemReader(path) as reader:reader.read_at(offset,length)
            with self.assertRaises(ValueError):
                with SystemReader(path,expected_sha256='0'*64):pass
            stamp=path.stat().st_mtime_ns
            with self.assertRaisesRegex(ValueError,'changed'):
                with SystemReader(path) as reader:
                    reader.read_at(0,1);path.write_bytes(b'ABXDEFGH');os.utime(path,ns=(stamp,stamp))
            self.assertTrue(reader.stream.closed)
            with self.assertRaises(KeyboardInterrupt):
                with SystemReader(path,cancelled=lambda:True):pass

    def test_large_sparse_source_never_uses_unbounded_read(self):
        from romancer.system_reader import SystemReader
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'large.bin'
            with path.open('wb') as stream:stream.seek(8*1024**2-1);stream.write(b'Z')
            opened=Path.open;sizes=[]
            class Guard:
                def __init__(self,stream):self.stream=stream
                def __getattr__(self,name):return getattr(self.stream,name)
                def read(self,size=-1):
                    if not 0<=size<=65536:raise AssertionError('unbounded read')
                    sizes.append(size);return self.stream.read(size)
                def __enter__(self):return self
                def __exit__(self,*args):return self.stream.__exit__(*args)
            with patch.object(Path,'open',lambda obj,*args,**kwargs:Guard(opened(obj,*args,**kwargs))):
                with SystemReader(path) as reader:
                    self.assertEqual(reader.read_at(8*1024**2-1,1),b'Z')
            self.assertTrue(sizes);self.assertLessEqual(max(sizes),65536)
            with SystemReader(path) as reader:
                reader.read_at(0,65536)
                with self.assertRaises(ValueError):reader.read_at(65536,1)

    def test_linked_source_is_rejected(self):
        from romancer.system_reader import SystemReader
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'source';path.write_bytes(b'ABCD');linked=Path(temp)/'linked'
            try:os.link(path,linked)
            except OSError:self.skipTest('hard-link creation unavailable')
            with self.assertRaises(ValueError):
                with SystemReader(path):pass


def nes_bytes(*,trainer=False,chr_units=1,mapper=0):
    header=bytearray(16);header[:4]=b'NES\x1a';header[4]=1;header[5]=chr_units
    header[6]=((mapper&15)<<4)|(4 if trainer else 0);header[7]=mapper&240
    return bytes(header)+b'T'*(512 if trainer else 0)+bytes(16384)+bytes(chr_units*8192)


def snes_bytes(*,dual=False,headered=False):
    size=65536 if dual else 32768;prefix=512 if headered else 0;raw=bytearray(size+prefix)
    for off,mode in ([(0x7fc0,0x20),(0xffc0,0x21)] if dual else [(0x7fc0,0x20)]):
        off+=prefix;raw[off:off+21]=b'ROMANCER SYSTEM TEST'.ljust(21,b' ');raw[off+21]=mode
        raw[off+23]=6 if dual else 5;raw[off+28:off+32]=b'\xff\xff\x00\x00'
    return bytes(raw)


def genesis_bytes():
    raw=bytearray(1024);raw[0x100:0x110]=b'SEGA MEGA DRIVE '
    raw[0x1a4:0x1a8]=(len(raw)-1).to_bytes(4,'big');return bytes(raw)


def gba_bytes():
    raw=bytearray(1024);raw[0xa0:0xac]=b'ROMANCERTEST';raw[0xac:0xb0]=b'TEST';raw[0xb0:0xb2]=b'00';raw[0xb2]=0x96
    raw[0xbd]=(-sum(raw[0xa0:0xbd])-0x19)&255;return bytes(raw)


def cd_bytes(*,raw_sector=False):
    data=bytearray(2048);data[:16]=b'SEGADISCSYSTEM'.ljust(16,b' ')
    if not raw_sector:return bytes(data)
    return b'\x00'+b'\xff'*10+b'\x00'+b'\x00'*3+b'\x01'+bytes(data)+bytes(288)


class RecognitionTests(unittest.TestCase):
    def test_gba_linear_image_over_hardware_rom_capacity_is_not_editable_layout(self):
        raw=gba_bytes()+bytes(32*1024**2-1024+1)
        result=self.investigate(raw)
        self.assertEqual(result['status'],'BLOCKED',result)
        self.assertFalse(result['candidates'][0]['layout_valid'])
        self.assertTrue(any('32 MiB' in warning for warning in result['warnings']))

    def test_snes_non_power_of_two_size_uses_rounded_header_declaration(self):
        raw=bytearray(snes_bytes())+bytearray(3*1024**2-32768)
        raw[0x7fd7]=12  # 3 MiB payload conventionally declares 4 MiB.
        result=self.investigate(raw)
        self.assertEqual(result['status'],'IDENTIFIED',result)
        self.assertEqual(result['candidates'][0]['metadata']['declared_rom_bytes'],4*1024**2)
        raw[0x7fd7]=11
        self.assertEqual(self.investigate(raw)['status'],'BLOCKED')

    def investigate(self,raw,suffix='.anything'):
        from romancer.system_identify import identify_system
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/('original Ω'+suffix);path.write_bytes(raw);result=identify_system(path)
            self.assertEqual(path.read_bytes(),raw);return result

    def test_nes_trainer_chr_ram_and_unknown_mapper(self):
        result=self.investigate(nes_bytes(trainer=True,mapper=255));self.assertEqual(result['status'],'IDENTIFIED',result)
        self.assertEqual(result['system_id'],'nes');self.assertFalse(result['write_authorized']);self.assertFalse(result['runtime_verified'])
        meta=result['candidates'][0]['metadata'];self.assertEqual(meta['mapper'],255)
        regions={r['id']:r for r in result['regions']};self.assertEqual(regions['prg-rom']['offset'],528)
        self.assertEqual(regions['chr-rom']['offset'],16912);self.assertEqual(regions['chr-rom']['length'],8192)
        ram=self.investigate(nes_bytes(chr_units=0));self.assertEqual(ram['status'],'IDENTIFIED')
        self.assertNotIn('chr-rom',{r['id'] for r in ram['regions']})
        truncated=self.investigate(nes_bytes()[:-1]);self.assertEqual(truncated['status'],'BLOCKED')

    def test_nes2_extended_sizes_submapper_and_exponent_vectors(self):
        raw=bytearray(nes_bytes());raw[6]=0x30;raw[7]=0x28;raw[8]=0xa1
        result=self.investigate(raw);meta=result['candidates'][0]['metadata']
        self.assertEqual(meta['mapper'],0x123);self.assertEqual(meta['submapper'],10)
        self.assertEqual(result['candidates'][0]['format'],'nes2')
        # Exponent 14, multiplier 1 -> 16384 bytes; exponent 13 -> 8192 CHR.
        raw[4]=14<<2;raw[5]=13<<2;raw[9]=0xff
        result=self.investigate(raw);self.assertEqual(result['status'],'IDENTIFIED',result)
        self.assertEqual(result['candidates'][0]['metadata']['prg_rom_bytes'],16384)
        raw[4]=0xfc;self.assertEqual(self.investigate(raw)['status'],'BLOCKED')
        extended=bytearray(nes_bytes());extended[7]=8;extended[9]=1
        self.assertEqual(self.investigate(extended)['status'],'BLOCKED')

    def test_snes_weak_and_conflicting_headers_remain_explicit(self):
        self.assertEqual(self.investigate(bytes(65536))['status'],'UNKNOWN')
        for headered in (False,True):
            result=self.investigate(snes_bytes(headered=headered));self.assertEqual(result['system_id'],'snes',result)
            candidate=result['candidates'][0];self.assertEqual(candidate['confidence'],'heuristic')
            self.assertEqual(candidate['header_offset'],0x7fc0+(512 if headered else 0))
            self.assertTrue(candidate['metadata']['checksum_pair_valid']);self.assertEqual(candidate['metadata']['whole_image_checksum'],'NOT_CHECKED')
        result=self.investigate(snes_bytes(dual=True));self.assertEqual(result['status'],'AMBIGUOUS',result)
        self.assertIsNone(result['system_id']);self.assertEqual(len(result['candidates']),2)

    def test_genesis_gba_and_disc_signatures_do_not_claim_boot(self):
        for raw,family in ((genesis_bytes(),'genesis'),(gba_bytes(),'gba'),(cd_bytes(),'segacd'),(cd_bytes(raw_sector=True),'segacd')):
            result=self.investigate(raw,'.nes');self.assertEqual(result['system_id'],family,result)
            self.assertFalse(result['runtime_verified']);self.assertFalse(result['write_authorized'])
        gba=bytearray(gba_bytes());gba[0xbd]^=1
        self.assertEqual(self.investigate(gba)['status'],'BLOCKED')
        self.assertEqual(self.investigate(gba_bytes())['candidates'][0]['metadata']['logo_validation'],'NOT_CHECKED')
        malformed=bytearray(cd_bytes(raw_sector=True));malformed[15]=2
        self.assertEqual(self.investigate(malformed)['status'],'BLOCKED')

    def test_cue_references_are_never_opened(self):
        from romancer.system_identify import identify_system
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'disc.cue';outside=Path(temp)/'outside';outside.write_bytes(b'private')
            path.write_text('FILE "../outside" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n')
            opened=Path.open;names=[]
            def record(obj,*args,**kwargs):names.append(obj);return opened(obj,*args,**kwargs)
            with patch.object(Path,'open',record):result=identify_system(path)
            self.assertEqual(result['status'],'UNKNOWN',result);self.assertIsNone(result['system_id'])
            self.assertEqual(result['container']['format'],'cue');self.assertTrue(all(p==path for p in names))
            self.assertTrue(result['warnings']);self.assertEqual(outside.read_bytes(),b'private')

    def test_cross_family_conflict_unknown_stale_and_cancellation(self):
        from romancer.system_identify import identify_system
        raw=bytearray(nes_bytes());raw[0x100:0x110]=b'SEGA MEGA DRIVE ';raw[0x1a4:0x1a8]=(len(raw)-1).to_bytes(4,'big')
        result=self.investigate(raw);self.assertEqual(result['status'],'AMBIGUOUS',result);self.assertEqual(result['regions'],[])
        self.assertEqual(self.investigate(b'ABC')['status'],'UNKNOWN')
        self.assertEqual(self.investigate(b'')['status'],'UNKNOWN')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input';path.write_bytes(nes_bytes())
            self.assertEqual(identify_system(path,expected_sha256='0'*64)['status'],'BLOCKED')
            self.assertEqual(identify_system(path,cancelled=lambda:True)['status'],'CANCELLED')


if __name__=='__main__':unittest.main()
