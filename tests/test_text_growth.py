import unittest,tempfile,hashlib,copy
from pathlib import Path
from romancer.workbench_api import WorkbenchAPI
from romancer.boot_fixtures import make_boot_fixture
from romancer.resource_forms import script_schema

class TextGrowthTests(unittest.TestCase):
    def setUp(self):
        self.temp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.temp);self.api=WorkbenchAPI(self.root/'work');self.addCleanup(self.api.close)
        settings=self.api.dispatch('settings.get',{});self.api.dispatch('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
    def source(self,system='nes',interior_pointer=False):
        data=bytearray(32768) if system=='sms' else bytearray(make_boot_fixture(system)['data'])
        if system=='sms':data[0x7ff0:0x7ff8]=b'TMR SEGA';data[0x7fff]=0x4c
        width=2;base={'nes':0x7ff0,'snes':0x8000}.get(system,0);order='big' if system=='genesis' else 'little'
        data[0x500:0x500+width]=(0x1000+base).to_bytes(width,order);data[0x1000:0x1008]=b'HI\x01\x07!\0\xff\xff';data[0x1800:0x1840]=b'\xff'*64
        if interior_pointer:data[0x508:0x508+width]=(0x1004+base).to_bytes(width,order)
        path=self.root/(system+'.rom');path.write_bytes(data);project=self.api.dispatch('project.create',{'name':system});source=self.api.dispatch('source.import',{'project_id':project['project_id'],'path':str(path),'system':None});self.assertTrue(source['ok'],source)
        p={'project_id':project['project_id'],'artifact_id':source['artifact_id']};owned=self.api.source(p)[2]
        schema=script_schema(owned,source['sha256'],{'system_id':system,'offset':0x1000,'capacity':8,'count':1,'pointer_offset':0x500,'pointer_width':width,'pointer_endian':order,'pointer_base':-base,'controls':[{'id':'pause','opcode':1,'argument_length':1,'position_independent':True,'layout_role':'pause'}]})
        doc=self.api.dispatch('script.inspect',{**p,'schema':schema});self.assertTrue(doc['write_supported'],doc)
        return p,path,bytes(data),schema,doc,base,width,order
    def args(self,p,schema,doc):
        return {**p,'schema':schema,'document_id':doc['document_id'],'record_id':'line-0','changes':[{'segment':0,'text':'WELCOME'},{'segment':1,'text':'FRIEND'}],
            'destination':{'offset':0x1800,'capacity':32,'fill_byte':255,'alignment':1,'bank_size':8192,'bank_origin':16,'extra_references':[],'references_complete':True,'destination_reserved':True}}
    def test_growing_text_preserves_controls_updates_declared_pointers_and_reopens_across_seven_systems(self):
        for system in ('nes','snes','genesis','sms','gb','gbc'):
            with self.subTest(system=system):
                p,path,original,schema,doc,base,width,order=self.source(system);args=self.args(p,schema,doc);args['destination'].update(bank_size={'nes':8192,'snes':32768,'gb':16384,'gbc':16384,'sms':16384}.get(system,0),bank_origin=16 if system=='nes' else 0)
                before=self.api.dispatch('project.open',{'project_id':p['project_id']});preview=self.api.dispatch('text.grow.preview',args);self.assertTrue(preview['ok'],preview);self.assertEqual(preview['text_preview'],'WELCOME\nFRIEND');self.assertEqual(preview['required_bytes'],16);self.assertEqual(preview['pointer_updates'][0]['after'],0x1800+base)
                self.assertEqual(self.api.dispatch('project.open',{'project_id':p['project_id']}),before)
                plan=self.api.dispatch('text.grow.plan',{**args,'review_id':preview['review_id']});self.assertTrue(plan['ok'],plan);built=self.api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']});self.assertTrue(built['ok'],built)
                raw=Path(built['path']).read_bytes();self.assertEqual(raw[0x1800:0x1810],b'WELCOME\x01\x07FRIEND\0');self.assertEqual(int.from_bytes(raw[0x500:0x500+width],order),0x1800+base);self.assertEqual(raw[0x1000:0x1008],original[0x1000:0x1008]);self.assertEqual(path.read_bytes(),original)
                moved=self.api.dispatch('text.grow.definition',{'project_id':p['project_id'],'artifact_id':built['artifact_id']});self.assertTrue(moved['ok'],moved);self.assertEqual(moved['inspection']['records'][0]['segments'][0]['text'],'WELCOME');self.assertEqual(moved['inspection']['records'][0]['capacity'],32)
    def test_invalid_capacity_encoding_reservation_overlap_and_stale_review_refuse_without_builds(self):
        p,path,raw,schema,doc,*_=self.source();args=self.args(p,schema,doc);good=self.api.dispatch('text.grow.preview',args);self.assertTrue(good['ok'],good)
        for field,value in [('capacity',8),('offset',0x1000),('offset',0),('references_complete',False),('destination_reserved',False)]:
            bad=copy.deepcopy(args);bad['destination'][field]=value;self.assertFalse(self.api.dispatch('text.grow.preview',bad)['ok'])
        bad=copy.deepcopy(args);bad['changes'][0]['text']='🤞';self.assertFalse(self.api.dispatch('text.grow.preview',bad)['ok'])
        bad=copy.deepcopy(args);bad['changes'][0]['text']='CHANGED';self.assertFalse(self.api.dispatch('text.grow.plan',{**bad,'review_id':good['review_id']})['ok'])
        self.assertEqual(self.api.dispatch('project.open',{'project_id':p['project_id']})['builds'],[]);self.assertEqual(path.read_bytes(),raw)
    def test_non_position_independent_controls_cannot_be_moved(self):
        p,_,_,schema,doc,*_=self.source();schema=copy.deepcopy(schema);schema['format']['controls'][0]['position_independent']=False
        r=self.api.dispatch('text.grow.preview',self.args(p,schema,doc));self.assertFalse(r['ok'])
    def test_padding_inside_another_declared_resource_is_not_reserved_text_space(self):
        p,_,_,schema,doc,*_=self.source();config={'system_id':'nes','offset':0x1800,'count':4};review=self.api.dispatch('definitions.preview',{**p,'kind':'assets','config':config});self.assertTrue(review['ok'],review)
        self.assertTrue(self.api.dispatch('definitions.save',{**p,'kind':'assets','config':config,'review_id':review['review_id'],'replace':False})['ok'])
        self.assertFalse(self.api.dispatch('text.grow.preview',self.args(p,schema,doc))['ok'])
    def test_growing_text_refuses_interior_references_whose_segments_shift(self):
        p,_,_,schema,doc,base,width,order=self.source(interior_pointer=True);args=self.args(p,schema,doc)
        args['destination']['extra_references']=[{'offset':0x508,'width':width,'endian':order,'base':base,'target_delta':4}]
        result=self.api.dispatch('text.grow.preview',args);self.assertFalse(result['ok'],result);self.assertIn('record-start',result['error'])
