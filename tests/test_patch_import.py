import hashlib
from pathlib import Path
import tempfile
import unittest
import zlib


class PatchImportTests(unittest.TestCase):
    def test_ips_literal_rle_growth_and_optional_truncation(self):
        from romancer.patch_import import decode_ips
        self.assertEqual(decode_ips(b'abcdef',b'PATCH\0\0\1\0\2XYEOF'),b'aXYdef')
        self.assertEqual(decode_ips(b'abcdef',b'PATCH\0\0\4\0\0\0\3!EOF'),b'abcd!!!')
        self.assertEqual(decode_ips(b'abcdef',b'PATCHEOF\0\0\3'),b'abc')
        for bad in [b'PATCH',b'PATCHEOFx',b'PATCH\0\0\1\0\4abEOF',b'PATCH\0\0\1\0\0\0\0!EOF']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):decode_ips(b'abcdef',bad)

    def test_bps_preview_and_explicit_apply_create_a_named_separate_build(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.streaming_bps import create_patch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=bytearray(1024);raw[:6]=b'abcdef';raw[0x100:0x110]=b'SEGA MEGA DRIVE ';raw[0x1a4:0x1a8]=(1023).to_bytes(4,'big');raw=bytes(raw);expected=raw[:1]+b'XY'+raw[3:];source=root/'source.bin';source.write_bytes(raw);target=root/'target.bin';target.write_bytes(expected)
            patch=root/'edit.bps';create_patch(source,target,patch)
            api=WorkbenchAPI(root/'workspace')
            try:
                p=api.dispatch('project.create',{'name':'Patches'});params={'project_id':p['project_id']}
                row=api.dispatch('source.import',{**params,'path':str(source),'system':None})
                uploaded=api.dispatch('inputs.import',{**params,'path':str(patch),'name':'edit.bps','kind':'patch'})
                preview=api.dispatch('patches.preview',{**params,'artifact_id':row['artifact_id'],'input_id':uploaded['input_id'],'expected_reference':''})
                self.assertTrue(preview['ok'],preview);self.assertEqual(preview['changed_bytes'],2)
                self.assertEqual(api.dispatch('project.open',params)['builds'],[])
                built=api.dispatch('patches.apply',{**params,'plan_id':preview['plan_id'],'name':'New graphics'})
                self.assertTrue(built['ok'],built);self.assertEqual(Path(built['path']).read_bytes(),expected)
                self.assertEqual(built['name'],'New graphics');self.assertEqual(source.read_bytes(),raw)
                self.assertEqual(built['source_id'],row['artifact_id'])
                self.assertEqual(list((Path(p['path'])/'patch-previews').iterdir()),[])
                repeated=api.dispatch('patches.apply',{**params,'plan_id':preview['plan_id'],'name':'New graphics'})
                self.assertTrue(repeated['already_applied'],repeated)
                self.assertEqual(len(api.dispatch('project.open',params)['builds']),1)
            finally:api.close()

    def test_ips_requires_a_reference_and_rejects_wrong_original(self):
        from romancer.patch_import import preview_patch
        from romancer.workbench_projects import create_project,register_source
        from romancer.workbench_files import import_input
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(create_project(root/'projects','IPS')['path'])
            source=root/'source';source.write_bytes(b'abcdef');row=register_source(project,source,None)
            patch=root/'patch';patch.write_bytes(b'PATCH\0\0\1\0\2XYEOF');inp=import_input(project,patch,'a.ips','patch')
            for reference in ['', '00000000', 'not a checksum']:
                with self.subTest(reference=reference),self.assertRaises(ValueError):preview_patch(project,row['artifact_id'],inp['input_id'],reference)
            result=preview_patch(project,row['artifact_id'],inp['input_id'],f'{zlib.crc32(b"abcdef"):08x}')
            self.assertEqual(result['format'],'IPS');self.assertEqual(result['target_sha256'],hashlib.sha256(b'aXYdef').hexdigest())

    def test_changed_preview_is_refused_without_registering_a_build(self):
        from romancer.patch_import import preview_patch,apply_preview
        from romancer.workbench_projects import create_project,register_source,read_project
        from romancer.workbench_files import import_input
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(create_project(root/'projects','IPS')['path']);source=root/'source';source.write_bytes(b'abcdef')
            row=register_source(project,source,None);patch=root/'patch';patch.write_bytes(b'PATCH\0\0\1\0\2XYEOF');inp=import_input(project,patch,'a.ips','patch')
            plan=preview_patch(project,row['artifact_id'],inp['input_id'],hashlib.sha256(b'abcdef').hexdigest())
            preview=next((project/'patch-previews').iterdir());preview.write_bytes(b'forged')
            with self.assertRaises(ValueError):apply_preview(project,plan['plan_id'],'Should not exist')
            self.assertEqual(read_project(project)['builds'],[]);self.assertEqual(source.read_bytes(),b'abcdef')
