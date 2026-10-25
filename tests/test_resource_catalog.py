import hashlib
from pathlib import Path
import tempfile
import unittest


class CatalogTests(unittest.TestCase):
    def test_ten_thousand_declared_entries_page_search_and_stale_source(self):
        from romancer.resource_catalog import add_resources,list_resources
        from romancer.workbench_projects import create_project,register_source
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(create_project(root/'projects','Catalog')['path']);source=root/'own.bin';source.write_bytes(bytes(16384));row=register_source(project,source,None)
            for start in range(0,10000,500):
                add_resources(project,row['artifact_id'],[{'name':f'Fixture byte {i:05d}','kind':'bytes','offset':i,'length':1,'format':'declared byte'} for i in range(start,start+500)])
            seen=[]
            for page in range(100):
                result=list_resources(project,row['artifact_id'],'',page,100);self.assertEqual(result['total'],10000);self.assertEqual(len(result['resources']),100);seen.extend(r['resource_id'] for r in result['resources'])
            self.assertEqual(len(set(seen)),10000)
            found=list_resources(project,row['artifact_id'],'09999',0,50);self.assertEqual(found['total'],1);self.assertEqual(found['resources'][0]['offset'],9999)
            self.assertFalse(found['write_authorized'])
            Path(row['path']).write_bytes(b'x'+bytes(16383))
            with self.assertRaises(ValueError):list_resources(project,row['artifact_id'],'',0,50)

    def test_invalid_ranges_and_duplicate_batches_never_add_authority(self):
        from romancer.resource_catalog import add_resources,list_resources
        from romancer.workbench_projects import create_project,register_source
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(create_project(root/'projects','Catalog')['path']);source=root/'own.bin';source.write_bytes(b'1234');row=register_source(project,source,None)
            item={'name':'Literal','kind':'bytes','offset':1,'length':2,'format':'declared'}
            add_resources(project,row['artifact_id'],[item]);add_resources(project,row['artifact_id'],[item])
            self.assertEqual(list_resources(project,row['artifact_id'],'',0,50)['total'],1)
            with self.assertRaises(ValueError):add_resources(project,row['artifact_id'],[{**item,'length':99}])
