import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from romancer.boot_fixtures import make_boot_fixture


class DataRelocationTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.data_relocation'),'Reviewed declared-data relocation is missing.')
        from romancer import data_relocation
        return data_relocation

    def original(self):
        raw=bytearray(make_boot_fixture('nes')['data']);size=len(raw);raw[0x1000:0x1010]=b'ORIGINAL DATA!\0\xff'
        raw[0x1800:0x1840]=b'\xff'*64;raw[0x201:0x203]=(0x8ff0).to_bytes(2,'little');assert len(raw)==size;return bytes(raw)

    def spec(self,**changes):
        return {'source_offset':0x1000,'source_length':16,'target_offset':0x1800,'target_capacity':64,'fill_byte':255,
            'alignment':1,'bank_size':16384,'bank_origin':16,
            'references':[{'offset':0x201,'width':2,'endian':'little','base':0x7ff0,'target_delta':0}],
            'references_complete':True,'destination_reserved':True,'replacement_input_id':None,**changes}

    def test_growing_data_updates_only_declared_references_and_preserves_original_extent(self):
        raw=self.original();result=self.module().prepare_edits(raw,'nes',self.spec(),b'EXPANDED ORIGINAL DATA!')
        output=bytearray(raw)
        for e in result['edits']:output[e['offset']:e['offset']+len(bytes.fromhex(e['after']))]=bytes.fromhex(e['after'])
        self.assertEqual(output[0x1000:0x1010],raw[0x1000:0x1010]);self.assertEqual(output[0x1800:0x1817],b'EXPANDED ORIGINAL DATA!')
        self.assertEqual(output[0x201:0x203],bytes.fromhex('f097'))
        self.assertFalse(result['relocation']['all_references_observed']);self.assertFalse(result['relocation']['game_semantics_verified'])
        self.assertEqual(result['relocation']['reference_coverage'],'author-declared-complete')

    def test_overlap_unreserved_fill_cross_bank_overflow_and_incomplete_references_are_refused(self):
        m=self.module();raw=self.original()
        bad=[{'target_offset':0x1008},{'destination_reserved':False},{'references_complete':False},
            {'target_offset':0x5000},{'references':[]},{'alignment':32,'target_offset':0x1801},
            {'references':[{'offset':0x201,'width':2,'endian':'little','base':0xffff,'target_delta':0}]},
            {'references':[{'offset':0x1000,'width':2,'endian':'little','base':0x7ff0,'target_delta':0}]}]
        for changes in bad:
            with self.subTest(changes=changes),self.assertRaises(ValueError):m.prepare_edits(raw,'nes',self.spec(**changes))
        changed=bytearray(raw);changed[0x183f]=0
        with self.assertRaises(ValueError):m.prepare_edits(bytes(changed),'nes',self.spec())
        with self.assertRaises(ValueError):m.prepare_edits(raw,'nes',self.spec(),b'A'*65)
        with self.assertRaisesRegex(ValueError,'bank'):m.prepare_edits(raw,'nes',self.spec(bank_size=8192,target_offset=0x3000))

    def test_pointer_before_bytes_interior_targets_and_cancellation_are_checked(self):
        m=self.module();raw=self.original();refs=[{**self.spec()['references'][0],'target_delta':1}]
        with self.assertRaises(ValueError):m.prepare_edits(raw,'nes',self.spec(references=refs))
        with self.assertRaises(KeyboardInterrupt):m.prepare_edits(raw,'nes',self.spec(),cancelled=lambda:True)

    def test_api_build_keeps_source_identity_and_rechecks_changes(self):
        from romancer.workbench_api import WorkbenchAPI
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);api=WorkbenchAPI(root/'workspace');self.addCleanup(api.close)
        s=api.dispatch('settings.get',{});api.dispatch('settings.save',{'revision':s['revision'],'values':{**s['values'],'autoDeepScan':False}})
        project=api.dispatch('project.create',{'name':'Declared relocation'});source=root/'original.nes';source.write_bytes(self.original())
        artifact=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(source),'system':None})
        p={'project_id':project['project_id'],'artifact_id':artifact['artifact_id']}
        definition={'schema_version':1,'name':'Original data','offset':0x1000,'count':16,'stride':1,
            'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]}
        self.assertTrue(api.dispatch('tables.save_definition',{**p,'definition':definition})['ok'])
        planned=api.dispatch('relocation.plan',{**p,'spec':self.spec()});self.assertTrue(planned['ok'],planned)
        self.assertTrue(planned['integrity_planned']);self.assertIn('evidence_id',planned)
        built=api.dispatch('build.apply',{'project_id':project['project_id'],'plan_id':planned['plan_id']});self.assertTrue(built['ok'],built)
        output=Path(built['path']).read_bytes();self.assertEqual(output[0x1800:0x1810],self.original()[0x1000:0x1010])
        self.assertTrue(built['layout_changed']);self.assertEqual(built['resource_setup']['status'],'NOT_REUSED')
        self.assertFalse(api.dispatch('resources.reuse_definitions',{'project_id':p['project_id'],'artifact_id':built['artifact_id']})['ok'])
        rebased=api.dispatch('relocation.table_definition',{'project_id':p['project_id'],'artifact_id':built['artifact_id']})
        self.assertTrue(rebased['ok'],rebased);self.assertEqual(rebased['definition']['offset'],0x1800)
        self.assertEqual(rebased['inspection']['rows'][0]['cells'][0]['value'],ord('O'))
        self.assertFalse(rebased['definition_saved'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),artifact['sha256'])
        from romancer.mcp_server import WRITE_OPERATIONS,_investigation_properties
        self.assertIn('relocation.plan',WRITE_OPERATIONS)
        self.assertEqual(_investigation_properties('relocation.plan')['spec']['type'],'object')
