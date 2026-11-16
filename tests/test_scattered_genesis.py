"""Checked scattered storage cannot weaken generic linear intake rules."""
from pathlib import Path
from unittest.mock import patch
import hashlib,tempfile,unittest
from romancer.system_formats import genesis
from romancer.system_identify import identify_system
from romancer.system_addresses import translate
from romancer.system_integrity import integrity_edits
from romancer.workbench_api import WorkbenchAPI

def authored():
 raw=bytearray(0x80000);raw[0x100:0x110]=b'SEGA TEST       ';raw[0x1a4:0x1a8]=(0x13ffff).to_bytes(4,'big');raw[0x40000]=0xbc
 raw[0x18e:0x190]=(sum(int.from_bytes(raw[i:i+2],'big')for i in range(512,len(raw),2))&65535).to_bytes(2,'big')
 return raw

def signature(raw):return hashlib.sha256(raw[0x100:0x18e]+raw[0x190:0x200]).hexdigest()
MAPPING={'id':'genesis-scattered','segments':[{'cpu_start':0,'file_offset':0,'length':0x40000},{'cpu_start':0x100000,'file_offset':0x40000,'length':0x40000}]}

class ScatteredGenesisTests(unittest.TestCase):
 def test_only_checked_header_and_size_admit_the_scattered_layout(self):
  raw=authored();sig=signature(raw)
  with tempfile.TemporaryDirectory()as temp:
   path=Path(temp)/'source.bin';path.write_bytes(raw)
   self.assertEqual(identify_system(path)['status'],'BLOCKED')
   with patch.dict(genesis.__dict__,{'SCATTERED_HEADERS':{(len(raw),sig):'quackshot-continue-v1'}}):
    result=identify_system(path);self.assertEqual(result['status'],'IDENTIFIED',result)
    c=next(c for c in result['candidates']if c['layout_valid']);self.assertEqual(c['format'],'genesis-scattered');self.assertEqual(c['metadata']['address_mapping'],MAPPING)
    self.assertFalse(result['runtime_verified']);self.assertFalse(result['write_authorized'])
    for offset in(0x100,0x150,0x1a4):
     changed=bytearray(raw);changed[offset]^=1;path.write_bytes(changed);self.assertNotEqual(identify_system(path)['status'],'IDENTIFIED')
    path.write_bytes(raw+bytes(2));self.assertNotEqual(identify_system(path)['status'],'IDENTIFIED')
 def test_declared_mapping_keeps_the_gap_unresolved_and_checks_every_extent(self):
  self.assertEqual(translate('genesis',0x100000,MAPPING,None,0x80000)['offset'],0x40000)
  self.assertEqual(translate('genesis',0x13ffff,MAPPING,None,0x80000)['offset'],0x7ffff)
  for address in(0x40000,0xfffff,0x140000):
   with self.assertRaises(ValueError):translate('genesis',address,MAPPING,None,0x80000)
  with self.assertRaises(ValueError):translate('genesis',0,MAPPING,0,0x80000)
  for mutation in({'cpu_start':0x20000,'file_offset':0x40000,'length':0x40000},{'cpu_start':0x100000,'file_offset':0,'length':0x40000},{'cpu_start':0x100000,'file_offset':0x40000,'length':0x40001}):
   bad={**MAPPING,'segments':[MAPPING['segments'][0],mutation]}
   with self.assertRaises(ValueError):translate('genesis',0,bad,None,0x80000)
 def test_api_import_plan_build_and_owned_reopen_preserve_physical_storage(self):
  raw=authored()
  with tempfile.TemporaryDirectory()as temp,patch.dict(genesis.__dict__,{'SCATTERED_HEADERS':{(len(raw),signature(raw)):'quackshot-continue-v1'}}):
   root=Path(temp);path=root/'original.bin';path.write_bytes(raw);api=WorkbenchAPI(root/'work')
   def call(op,p={}):
    r=api.dispatch(op,p);self.assertTrue(r['ok'],r);return r
   try:
    settings=call('settings.get');call('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
    p={'project_id':call('project.create',{'name':'Scattered storage'})['project_id']};source=call('source.import',{**p,'path':str(path),'system':None});s={**p,'artifact_id':source['artifact_id']}
    plan=call('systems.plan_edits',{**s,'edits':[{'offset':0x40000,'before':'bc','after':'bd'}]});build=call('build.apply',{**p,'plan_id':plan['plan_id']});value=Path(build['path']).read_bytes()
    self.assertEqual(len(value),len(raw));self.assertEqual(value[0x40000],0xbd);self.assertEqual(path.read_bytes(),raw)
    self.assertEqual(identify_system(Path(build['path']))['status'],'IDENTIFIED');self.assertEqual(int.from_bytes(value[0x18e:0x190],'big'),sum(int.from_bytes(value[i:i+2],'big')for i in range(512,len(value),2))&65535)
   finally:api.close()
