import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


def definition(offset=4,count=2):
    return {'schema_version':1,'name':'Example records','offset':offset,'count':count,'stride':12,'fields':[
        {'name':'Health','offset':0,'type':'u16','endian':'little','pointer_base':None},
        {'name':'Delta','offset':2,'type':'s8','endian':'little','pointer_base':None},
        {'name':'Reward','offset':3,'type':'s24','endian':'big','pointer_base':None},
        {'name':'Flags','offset':6,'type':'u8','endian':'little','pointer_base':None},
        {'name':'Pointer','offset':8,'type':'u32','endian':'little','pointer_base':4}]}


class TableTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.data_tables'),'source-bound data tables are missing')
        from romancer import data_tables
        return data_tables

    def test_literal_mixed_fields_pointer_targets_and_paging(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            raw=b'HEAD'+bytes.fromhex('3412fe010203070024000000 ffff7f800000080030000000')+b'\0'*36
            path=Path(folder)/'table';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            result=service.inspect_table(path,sha,definition(),0,1);cells={cell['field']:cell for cell in result['rows'][0]['cells']}
            self.assertEqual([cells[name]['value'] for name in ['Health','Delta','Reward','Flags','Pointer']],[4660,-2,66051,7,36])
            self.assertEqual(cells['Pointer']['target_offset'],32)
            second=service.inspect_table(path,sha,definition(),1,1)
            self.assertEqual(second['document_id'],result['document_id']);self.assertEqual(second['rows'][0]['index'],1)
            self.assertEqual(second['rows'][0]['cells'][2]['value'],-8388608)
            changes=[{'row':0,'field':'Health','before':4660,'after':999},{'row':0,'field':'Delta','before':-2,'after':-3}]
            self.assertEqual(service.table_edits(path,sha,definition(),changes),[{'offset':4,'before':'3412','after':'e703'},{'offset':6,'before':'fe','after':'fd'}])
            self.assertEqual(path.read_bytes(),raw)

    def test_wrong_revision_overlaps_old_values_and_overflow_refuse(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'table';path.write_bytes(b'\0'*64);sha=hashlib.sha256(path.read_bytes()).hexdigest()
            bad=definition();bad['fields'][1]['offset']=1
            with self.assertRaises(ValueError):service.inspect_table(path,sha,bad,0,20)
            with self.assertRaises(ValueError):service.inspect_table(path,'0'*64,definition(),0,20)
            for before,after in [(3,4),(0,65536)]:
                with self.assertRaises(ValueError):service.table_edits(path,sha,definition(),[{'row':0,'field':'Health','before':before,'after':after}])
            with self.assertRaises(ValueError):service.inspect_table(path,sha,definition(count=100),0,20)

    def test_batch_preview_uses_real_before_values_and_validates_every_result(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'table';path.write_bytes(bytes([1,2,3,254,255]));sha=hashlib.sha256(path.read_bytes()).hexdigest()
            config={'schema_version':1,'name':'Byte values','offset':0,'count':5,'stride':1,'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]}
            rows=service.batch_changes(path,sha,config,'Value','add',2,0,3)
            self.assertEqual(rows,[{'row':i,'field':'Value','before':i+1,'after':i+3} for i in range(3)])
            with self.assertRaises(ValueError):service.batch_changes(path,sha,config,'Value','add',2,3,2)
            self.assertEqual(path.read_bytes(),bytes([1,2,3,254,255]))

    def test_percentage_batch_uses_explicit_rounding_and_refuses_overflow(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'table';path.write_bytes(bytes([15,20,255]));sha=hashlib.sha256(path.read_bytes()).hexdigest()
            config={'schema_version':1,'name':'Declared values','offset':0,'count':3,'stride':1,'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]}
            rows=service.batch_changes(path,sha,config,'Value','percent',10,0,2)
            self.assertEqual([r['after'] for r in rows],[17,22])
            with self.assertRaisesRegex(ValueError,'row 2'):service.batch_changes(path,sha,config,'Value','percent',10,2,1)

    def test_api_definition_persists_and_build_has_independent_checksum_oracle(self):
        self.service()
        from romancer.workbench_api import WorkbenchAPI
        from romancer.boot_fixtures import make_boot_fixture
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=bytearray(make_boot_fixture('gb')['data']);raw[0x500:0x504]=bytes.fromhex('0a001400');source=root/'table.gb';source.write_bytes(raw)
            config={'schema_version':1,'name':'Stats','offset':0x500,'count':2,'stride':2,'fields':[{'name':'Health','offset':0,'type':'u16','endian':'little','pointer_base':None}]}
            api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Tables'});row=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(source),'system':None});params={'project_id':project['project_id'],'artifact_id':row['artifact_id']}
                saved=api.dispatch('tables.save_definition',{**params,'definition':config});self.assertTrue(saved['ok'],saved)
                opened=api.dispatch('project.open',{'project_id':project['project_id']});self.assertEqual(opened['sources'][0]['descriptors']['tables']['definition'],config)
                document=saved['inspection'];request={**params,'definition':config,'document_id':document['document_id'],'changes':[{'row':0,'field':'Health','before':10,'after':50}]}
                wrong=api.dispatch('tables.plan',{**request,'document_id':'0'*64});self.assertFalse(wrong['ok'])
                plan=api.dispatch('tables.plan',request);self.assertTrue(plan['ok'],plan)
                build=api.dispatch('build.apply',{'project_id':project['project_id'],'plan_id':plan['plan_id']});self.assertTrue(build['ok'],build)
                expected=bytearray(raw);expected[0x500:0x502]=b'\x32\0';expected[0x14d]=(-sum(expected[0x134:0x14d])-25)&255;expected[0x14e:0x150]=b'\0\0';expected[0x14e:0x150]=(sum(expected)&65535).to_bytes(2,'big')
                self.assertEqual(Path(build['path']).read_bytes(),expected);self.assertEqual(source.read_bytes(),raw)
            finally:api.close()
