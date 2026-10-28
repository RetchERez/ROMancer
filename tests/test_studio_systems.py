from pathlib import Path
import copy,hashlib,tempfile,unittest
from romancer.boot_fixtures import make_boot_fixture
from romancer.workbench_api import WorkbenchAPI
from tests.test_level_design import fixture

class DeclaredStudioSystemsTests(unittest.TestCase):
 def test_checked_generic_level_layouts_use_same_plan_service_on_all_supported_cartridges(self):
  for system in ('nes','snes','genesis','gb','gbc','sms'):
   with self.subTest(system=system),tempfile.TemporaryDirectory() as temp:
    api=WorkbenchAPI(Path(temp)/'work')
    try:
     from tests.test_sms_controller_native import controller_program
     project=api.dispatch('project.create',{'name':'Declared '+system});p={'project_id':project['project_id']};payload,d,_=fixture();boot={'data':controller_program(),'suffix':'.sms'} if system=='sms' else make_boot_fixture(system);raw=bytearray(boot['data']);raw[4096:4096+len(payload)]=payload
     d=copy.deepcopy(d);d['source_sha256']=hashlib.sha256(raw).hexdigest();d['tiles']['offset']+=4096;d['tiles']['palette_offset']+=4096;d['metatiles']['offset']+=4096
     for r in d['rooms']:
      for key in ('terrain','collision','objects'):r[key]['offset']+=4096
     file=Path(temp)/('source'+boot['suffix']);file.write_bytes(raw)
     source=api.dispatch('source.import',{**p,'path':str(file),'system':None});self.assertTrue(source['ok'],source);sp={**p,'artifact_id':source['artifact_id']}
     doc=api.dispatch('levels.inspect',{**sp,'definition':d});self.assertTrue(doc['ok'],doc)
     plan=api.dispatch('levels.plan',{**sp,'definition':d,'document_id':doc['document_id'],'changes':[{'kind':'collision','room_id':'room-0','index':1,'value':0}]});self.assertTrue(plan['ok'],plan);self.assertFalse(doc['game_semantics_verified'])
    finally:api.close()
