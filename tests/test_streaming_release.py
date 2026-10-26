import hashlib
from pathlib import Path
import shutil
import struct
import tempfile
import tracemalloc
import unittest
import zipfile
import zlib


def require_directory_publication(test):
    from romancer.patch_sets import _publish_directory,DirectoryPublicationUnavailable
    with tempfile.TemporaryDirectory() as temp:
        source=Path(temp)/'s';source.mkdir()
        try:_publish_directory(source,Path(temp)/'t')
        except DirectoryPublicationUnavailable as exc:test.skipTest(str(exc))


class StreamingBPSTests(unittest.TestCase):
    def test_sparse_edits_emit_only_changed_bytes_across_stream_boundaries(self):
        from romancer.streaming_bps import create_patch,apply_patch,CHUNK
        from romancer.release import apply_bps
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=bytearray(bytes(range(256))*600)
            marker=b'UNCHANGED-NEIGHBOR-MUST-STAY-IN-SOURCE';raw[7000:7000+len(marker)]=marker
            target=bytearray(raw);positions=[1,CHUNK-1,CHUNK,CHUNK+10,len(raw)-1]
            for offset in positions:target[offset]^=128
            source=root/'source';source.write_bytes(raw);changed=root/'target';changed.write_bytes(target)
            patch=root/'change.bps';create_patch(source,changed,patch,{})
            encoded=patch.read_bytes();self.assertLess(len(encoded),1024)
            self.assertNotIn(marker,encoded,'Unchanged source neighbors must be referenced, not embedded.')
            cursor=4
            def integer():
                nonlocal cursor
                value=0;shift=1
                while True:
                    byte=encoded[cursor];cursor+=1;value+=(byte&127)*shift
                    if byte&128:return value
                    shift<<=7;value+=shift
            self.assertEqual(integer(),len(raw));self.assertEqual(integer(),len(target));metadata=integer();cursor+=metadata
            literals=0;output=0
            while cursor<len(encoded)-12:
                command=integer();length=(command>>2)+1;kind=command&3
                self.assertIn(kind,(0,1))
                if kind==1:
                    self.assertEqual(encoded[cursor:cursor+length],target[output:output+length]);literals+=length;cursor+=length
                output+=length
            self.assertEqual(literals,len(positions));self.assertEqual(output,len(target))
            self.assertEqual(apply_bps(bytes(raw),encoded),bytes(target))
            rebuilt=root/'rebuilt';apply_patch(source,patch,rebuilt);self.assertEqual(rebuilt.read_bytes(),target)

    def test_dense_alternating_edits_coalesce_without_exhausting_action_budget(self):
        from romancer.streaming_bps import create_patch,apply_patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original=bytes(2*1024**2);target=b'\x00\x01'*(1024**2)
            source=root/'source';source.write_bytes(original);changed=root/'target';changed.write_bytes(target)
            patch=root/'patch';create_patch(source,changed,patch,{})
            self.assertLess(patch.stat().st_size,len(target)+65536)
            rebuilt=root/'rebuilt';apply_patch(source,patch,rebuilt);self.assertEqual(rebuilt.read_bytes(),target)

    def test_stream_runs_handle_empty_extension_truncation_and_long_literals(self):
        from romancer.streaming_bps import create_patch,apply_patch,CHUNK
        for original,target in [(b'',b'new'),(b'old',b''),(b'',b''),(b'abc',b'abc-more'),
                                (b'abcdef',b'abc'),(b'A'*(2*CHUNK+3),b'B'*(2*CHUNK+3))]:
            with self.subTest(source_size=len(original),target_size=len(target)),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);source=root/'source';source.write_bytes(original);changed=root/'target';changed.write_bytes(target)
                patch=root/'patch';create_patch(source,changed,patch,{})
                rebuilt=root/'rebuilt';apply_patch(source,patch,rebuilt);self.assertEqual(rebuilt.read_bytes(),target)

    def test_image_above_old_limit_reconstructs_with_bounded_memory(self):
        from romancer.streaming_bps import create_patch,apply_patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.bin';target=root/'target.bin';size=256*1024**2+65536
            if shutil.disk_usage(root).free<size*4:self.skipTest('large independent reconstruction needs1GiB free')
            with source.open('wb') as stream:stream.truncate(size);stream.seek(size-1);stream.write(b'Z')
            with source.open('rb') as src,target.open('wb') as dest:shutil.copyfileobj(src,dest,65536)
            with target.open('r+b') as stream:stream.seek(256*1024**2+31);stream.write(b'X')
            with target.open('rb') as stream:want=hashlib.file_digest(stream,'sha256').hexdigest()
            tracemalloc.start()
            try:
                patch=root/'change.bps';created=create_patch(source,target,patch,{'title':'Large original fixture','description':''})
                rebuilt=root/'rebuilt.bin';applied=apply_patch(source,patch,rebuilt);peak=tracemalloc.get_traced_memory()[1]
            finally:tracemalloc.stop()
            self.assertEqual(created['target_sha256'],want);self.assertEqual(applied['target_sha256'],want)
            self.assertLess(peak,8*1024**2);self.assertLess(patch.stat().st_size,1024**2)
            with rebuilt.open('rb') as stream:self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),want)
            with source.open('rb') as stream:stream.seek(256*1024**2+31);self.assertEqual(stream.read(1),b'\0')

    def test_independent_decoder_accepts_literal_sourcecopy_and_overlapping_targetcopy(self):
        from romancer.streaming_bps import apply_patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for index,(original,want,body) in enumerate([(b'abcd',b'abcdabcdabcd',b'BPS1\x84\x8c\x80\x8c\x9f\x80'),(b'abcdefgh',b'efgh',b'BPS1\x88\x84\x80\x8e\x88')]):
                source=root/('s'+str(index));source.write_bytes(original);patch=root/(str(index)+'.bps');raw=body+struct.pack('<II',zlib.crc32(original),zlib.crc32(want));patch.write_bytes(raw+struct.pack('<I',zlib.crc32(raw)))
                output=root/('o'+str(index));apply_patch(source,patch,output);self.assertEqual(output.read_bytes(),want)

    def test_cancel_corruption_wrong_source_and_no_clobber(self):
        from romancer.streaming_bps import create_patch,apply_patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';target=root/'target';source.write_bytes(b'abcd');target.write_bytes(b'abXdef');patch=root/'change.bps'
            with self.assertRaises(KeyboardInterrupt):create_patch(source,target,patch,{},cancelled=lambda:True)
            self.assertFalse(patch.exists());create_patch(source,target,patch,{})
            with self.assertRaises(ValueError):create_patch(source,target,patch,{})
            wrong=root/'wrong';wrong.write_bytes(b'xxxx');out=root/'out'
            with self.assertRaises(ValueError):apply_patch(wrong,patch,out)
            self.assertFalse(out.exists());corrupt=bytearray(patch.read_bytes());corrupt[-1]^=1;bad=root/'bad';bad.write_bytes(corrupt)
            with self.assertRaises(ValueError):apply_patch(source,bad,out)
            self.assertFalse(out.exists());out.write_bytes(b'keep')
            with self.assertRaises(ValueError):apply_patch(source,patch,out)
            self.assertEqual(out.read_bytes(),b'keep')


class PatchSetTests(unittest.TestCase):
    def test_disc_set_reconstruction_preserves_unchanged_audio_and_cue(self):
        require_directory_publication(self)
        from romancer.patch_sets import create_patch_set,apply_patch_set
        from tests.test_v53_containers import iso_fixture
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';target=root/'target';source.mkdir();target.mkdir()
            (source/'disc.cue').write_text('FILE "data.bin" BINARY\n TRACK 01 MODE1/2048\n INDEX 01 00:00:00\nFILE "audio.bin" BINARY\n TRACK 02 AUDIO\n INDEX 01 00:00:00\n')
            (source/'data.bin').write_bytes(iso_fixture());(source/'audio.bin').write_bytes(b'\x12\x34'*1176)
            for file in source.iterdir():shutil.copyfile(file,target/file.name)
            with (target/'data.bin').open('r+b') as stream:stream.seek(21*2048+1);stream.write(b'X')
            archive=root/'release.zip';made=create_patch_set(source/'disc.cue',target/'disc.cue',archive,'Original disc fixture')
            self.assertTrue(made['ok']);rebuilt=root/'rebuilt';applied=apply_patch_set(source/'disc.cue',archive,rebuilt);self.assertTrue(applied['ok'])
            for file in target.iterdir():self.assertEqual((rebuilt/file.name).read_bytes(),file.read_bytes())
            with zipfile.ZipFile(archive) as z:self.assertEqual(set(z.namelist()),{'PATCHSET.json','README.txt','patches/001.bps'})
            with self.assertRaises(ValueError):apply_patch_set(source/'disc.cue',archive,rebuilt)
            (source/'audio.bin').unlink()
            with self.assertRaises((ValueError,OSError)):apply_patch_set(source/'disc.cue',archive,root/'missing')
            self.assertFalse((root/'missing').exists())
