from pathlib import Path
import tempfile
import unittest
from romancer import workbench_projects as p


class HexHistoryTests(unittest.TestCase):
    def test_wildcard_chunk_boundary_numeric_endian_and_inspection(self):
        from romancer.hex_tools import search,inspect_numbers
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.bin';source.write_bytes(b'\x00'*65535+b'\xab\x19\xcd\x34\x12\xff\xff')
            project=Path(p.create_project(root/'projects','Hex')['path']);row=p.register_source(project,source,None)
            found=search(project,row['artifact_id'],'hex','ab ?? cd',0,'little',2,False)
            self.assertEqual(found['offsets'],[65535]);self.assertTrue(found['complete'])
            self.assertEqual(search(project,row['artifact_id'],'number','4660',0,'little',2,False)['offsets'],[65538])
            self.assertEqual(search(project,row['artifact_id'],'number','4660',0,'big',2,False)['offsets'],[])
            values=inspect_numbers(project,row['artifact_id'],65538)
            self.assertEqual(values['values']['u16le'],4660);self.assertEqual(values['values']['u16be'],13330)
            self.assertEqual(inspect_numbers(project,row['artifact_id'],65540)['values']['i16le'],-1)

    def test_bookmarks_recheck_source_and_validate_offsets(self):
        from romancer.hex_tools import bookmarks,save_bookmark
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'rom';source.write_bytes(b'abc')
            project=Path(p.create_project(root/'projects','Hex')['path']);row=p.register_source(project,source,None)
            save_bookmark(project,row['artifact_id'],1,'Middle',False)
            self.assertEqual(bookmarks(project,row['artifact_id'])['bookmarks'],[{'offset':1,'name':'Middle'}])
            with self.assertRaises(ValueError):save_bookmark(project,row['artifact_id'],3,'Past end',False)
            Path(row['path']).write_bytes(b'def')
            with self.assertRaises(ValueError):bookmarks(project,row['artifact_id'])

    def test_named_timeline_parentage_compare_and_source_immutability(self):
        from romancer.build_history import timeline,annotate,compare
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'rom';source.write_bytes(b'abcdefgh')
            project=Path(p.create_project(root/'projects','History')['path']);row=p.register_source(project,source,None)
            plan=p.plan_byte_edits(project,row['artifact_id'],[{'offset':2,'before':'6364','after':'5859'}]);built=p.apply_build(project,plan['plan_id'])
            annotate(project,built['artifact_id'],'Readable title','Works at title screen')
            rows=timeline(project)['artifacts'];self.assertEqual(rows[1]['parent_id'],row['artifact_id']);self.assertEqual(rows[1]['notes'],'Works at title screen')
            diff=compare(project,row['artifact_id'],built['artifact_id'])
            self.assertEqual(diff['changed_bytes'],2);self.assertEqual(diff['ranges'],[{'offset':2,'length':2}])
            self.assertEqual(p.artifact(project,built['artifact_id'])['name'],'Readable title')
            self.assertEqual(source.read_bytes(),b'abcdefgh');self.assertEqual(Path(row['path']).read_bytes(),b'abcdefgh')
            self.assertEqual(Path(built['path']).read_bytes(),b'abXYefgh')
            with self.assertRaises(ValueError):annotate(project,row['artifact_id'],'Rename original','')
