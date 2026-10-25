import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ABC_SHA='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
ABC_SHA1='a9993e364706816aba3e25717850c26c9cd0d89d'


class RevisionCatalogTests(unittest.TestCase):
    def test_sparse_rows_cannot_hide_conflicts_in_any_order(self):
        from itertools import permutations
        from romancer.revision_catalog import parse_catalog
        rows=[{'name':'a','size':3,'sha1':ABC_SHA1,'crc32':'352441c2'},
              {'name':'sparse','size':3,'sha1':ABC_SHA1},
              {'name':'b','size':3,'sha1':ABC_SHA1,'crc32':'00000000'}]
        for order in permutations(rows):
            with self.subTest(names=[r['name'] for r in order]),self.assertRaisesRegex(ValueError,'conflict'):
                parse_catalog(json.dumps(order).encode(),'file')

    def test_linked_strong_references_preserve_previously_known_hashes(self):
        from romancer.revision_catalog import parse_catalog
        rows=[{'name':'a','size':3,'sha1':ABC_SHA1,'crc32':'352441c2'},
              {'name':'bridge','size':3,'sha1':ABC_SHA1,'sha256':ABC_SHA},
              {'name':'b','size':3,'sha256':ABC_SHA,'crc32':'00000000'}]
        with self.assertRaisesRegex(ValueError,'conflict'):parse_catalog(json.dumps(rows).encode(),'file')

    def test_csv_tsv_json_and_dat_preserve_literal_reference_hashes(self):
        from romancer.revision_catalog import parse_catalog
        inputs=[json.dumps([{'name':'ABC','size':3,'crc32':'352441C2','sha1':ABC_SHA1,'sha256':ABC_SHA}]).encode(),
                f'name,size,crc32,sha1,sha256\nABC,3,352441c2,{ABC_SHA1},{ABC_SHA}\n'.encode(),
                f'name\tsize\tcrc32\tsha1\tsha256\nABC\t3\t352441c2\t{ABC_SHA1}\t{ABC_SHA}\n'.encode(),
                f'<datafile><game name="ABC"><rom name="ABC" size="3" crc="352441c2" sha1="{ABC_SHA1}" sha256="{ABC_SHA}"/></game></datafile>'.encode()]
        for raw in inputs:
            with self.subTest(raw=raw[:20]):
                rows=parse_catalog(raw,'file');self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['sha256'],ABC_SHA);self.assertEqual(rows[0]['crc32'],'352441c2');self.assertEqual(rows[0]['size'],3)

    def test_unsafe_xml_duplicates_and_conflicting_strong_hashes_are_refused(self):
        from romancer.revision_catalog import parse_catalog
        for raw in [b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///private">]><datafile/>',b'name,size,crc32,crc32\na,3,352441c2,00000000',b'[{"name":"a","name":"b","size":3,"crc32":"352441c2"}]',b'[{"name":"a","size":true,"crc32":"352441c2"}]']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):parse_catalog(raw,'file')
        raw=json.dumps([{'name':'a','size':3,'sha1':ABC_SHA1,'crc32':'352441c2'},
                        {'name':'b','size':3,'sha1':ABC_SHA1,'crc32':'00000000'}]).encode()
        with self.assertRaisesRegex(ValueError,'conflict'):parse_catalog(raw,'file')

    def test_lookup_distinguishes_match_unknown_and_explicit_mismatch(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);rom=root/'rom';rom.write_bytes(b'abc');catalog=root/'catalog.json'
            catalog.write_text(json.dumps([{'name':'Original <ABC>','size':3,'sha256':ABC_SHA},{'name':'Other','size':3,'sha256':'0'*64}]))
            api=WorkbenchAPI(root/'workspace')
            try:
                p=api.dispatch('project.create',{'name':'Catalog'});params={'project_id':p['project_id']}
                source=api.dispatch('source.import',{**params,'path':str(rom),'system':None});src={**params,'artifact_id':source['artifact_id']}
                inp=api.dispatch('inputs.import',{**params,'path':str(catalog),'name':'catalog.json','kind':'catalog'})
                imported=api.dispatch('revision.import',{**params,'input_id':inp['input_id'],'scope':'file'});self.assertTrue(imported['ok'],imported)
                found=api.dispatch('revision.lookup',{**src,'scope':'file','expected_id':''});self.assertEqual(found['status'],'MATCHED',found)
                self.assertEqual(found['matches'][0]['name'],'Original <ABC>')
                other=next(r for r in api.dispatch('revision.list',{**params,'query':'Other'})['entries'])
                wrong=api.dispatch('revision.lookup',{**src,'scope':'file','expected_id':other['id']});self.assertEqual(wrong['status'],'MISMATCHED',wrong)
                rom.write_bytes(b'def');new=api.dispatch('source.import',{**params,'path':str(rom),'system':None})
                unknown=api.dispatch('revision.lookup',{**params,'artifact_id':new['artifact_id'],'scope':'file','expected_id':''});self.assertEqual(unknown['status'],'UNKNOWN',unknown)
                self.assertFalse(unknown['corruption_established'])
            finally:api.close()

    def test_payload_reference_is_explicit_and_header_bytes_are_not_hashed(self):
        from romancer.revision_catalog import import_catalog,lookup_revision
        from romancer.workbench_projects import create_project,register_source
        from romancer.workbench_files import import_input
        from romancer.boot_fixtures import make_boot_fixture
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(create_project(root/'projects','Payload')['path']);raw=make_boot_fixture('nes')['data'];rom=root/'a.nes';rom.write_bytes(raw)
            source=register_source(project,rom,None);catalog=root/'catalog';catalog.write_text(json.dumps([{'name':'Payload','size':len(raw)-16,'sha256':hashlib.sha256(raw[16:]).hexdigest()}]))
            inp=import_input(project,catalog,'payload.json','catalog');import_catalog(project,inp['input_id'],'payload')
            found=lookup_revision(project,source['artifact_id'],'payload','');self.assertEqual(found['status'],'MATCHED')
            self.assertNotEqual(found['hashes']['sha256'],source['sha256'])
            with self.assertRaisesRegex(ValueError,'scope'):lookup_revision(project,source['artifact_id'],'file',found['matches'][0]['id'])
