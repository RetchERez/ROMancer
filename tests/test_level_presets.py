"""Known layout presets use source and structural guards, never filenames."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI
from romancer.boot_fixtures import make_boot_fixture


def authored_source():
    raw=bytearray(make_boot_fixture('gb')['data']);raw.extend(bytes(65536-len(raw)))
    raw[0x147]=1;raw[0x148]=1
    for bank in(1,2,3):
        for index in range(13):raw[bank*0x4000+index*2:bank*0x4000+index*2+2]=bytes([0,0x5f])
        raw[bank*0x4000+0x1f00:bank*0x4000+0x1f03]=bytes([0,0x60,0xff])
        stream=bytes([0,0xfd,4,0xfe])+b'\xfe'*19
        raw[bank*0x4000+0x2000:bank*0x4000+0x2000+len(stream)]=stream
    raw[0x1a6]=0xe4;raw[0x14d]=(-sum(raw[0x134:0x14d])-25)&255
    raw[0x14e:0x150]=bytes(2);raw[0x14e:0x150]=(sum(raw)&65535).to_bytes(2,'big')
    return bytes(raw)


class LevelPresetTests(unittest.TestCase):
    def test_preset_ai_tools_are_read_only_and_have_explicit_parameters(self):
        from romancer.mcp_server import READ_OPERATIONS,_investigation_properties
        for operation in ('levels.presets','levels.preset'):
            self.assertIn(operation,READ_OPERATIONS)
            properties=_investigation_properties(operation)
            self.assertEqual(properties['artifact_id']['type'],'string')
        self.assertEqual(_investigation_properties('levels.preset')['preset_id']['maxLength'],64)

    def test_unrecognized_source_has_no_presets_or_write_permission(self):
        with tempfile.TemporaryDirectory()as directory:
            api=WorkbenchAPI(Path(directory)/'work')
            try:
                path=Path(directory)/'original.gb';path.write_bytes(make_boot_fixture('gb')['data'])
                p={'project_id':api.dispatch('project.create',{'name':'No format guess'})['project_id']}
                source=api.dispatch('source.import',{**p,'path':str(path),'system':None});self.assertTrue(source['ok'],source)
                packet=api.dispatch('levels.presets',{**p,'artifact_id':source['artifact_id']})
                self.assertTrue(packet['ok'],packet);self.assertEqual(packet['status'],'NO_PRESETS')
                self.assertEqual(packet['presets'],[]);self.assertFalse(packet['full_editing_verified'])
            finally:api.close()

    def test_checked_preset_reuses_the_generic_visual_adapter_and_survives_owned_operand_build(self):
        from romancer import level_presets
        raw=authored_source();sha=hashlib.sha256(raw).hexdigest();pin=level_presets.layout_fingerprint(raw)
        with tempfile.TemporaryDirectory()as directory,patch.object(level_presets,'SOURCE_SHA',sha),patch.object(level_presets,'LAYOUT_PIN',pin):
            api=WorkbenchAPI(Path(directory)/'work')
            try:
                settings=api.dispatch('settings.get',{});api.dispatch('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
                path=Path(directory)/'original.gb';path.write_bytes(raw)
                p={'project_id':api.dispatch('project.create',{'name':'Known format'})['project_id']}
                source=api.dispatch('source.import',{**p,'path':str(path),'system':None});self.assertTrue(source['ok'],source)
                s={**p,'artifact_id':source['artifact_id']};catalog=api.dispatch('levels.presets',s)
                self.assertTrue(catalog['ok'],catalog);self.assertEqual(len(catalog['presets']),12)
                packet=api.dispatch('levels.preset',{**s,'preset_id':'sml-1-1'});self.assertTrue(packet['ok'],packet)
                definition=packet['definition'];self.assertEqual(len(definition['rooms']),1)
                self.assertEqual(len(definition['rooms'][0]['references']),4)
                doc=api.dispatch('levels.inspect',{**s,'definition':definition});self.assertTrue(doc['ok'],doc)
                room=doc['rooms'][0];self.assertEqual((room['width'],room['height']),(20,16));self.assertEqual(len(doc['tiles']),256)
                self.assertEqual(doc['palette'],[[255]*3,[170]*3,[85]*3,[0]*3])
                self.assertTrue(api.dispatch('studio.definition',{**s,'kind':'levels','definition':definition})['ok'])
                plan=api.dispatch('levels.plan',{**s,'definition':definition,'document_id':doc['document_id'],'changes':[{'kind':'terrain','room_id':room['id'],'index':0,'value':6}]});self.assertTrue(plan['ok'],plan)
                built=api.dispatch('build.apply',{**p,'plan_id':plan['plan_id']});self.assertTrue(built['ok'],built)
                derived=api.dispatch('levels.presets',{**p,'artifact_id':built['artifact_id']});self.assertTrue(derived['ok'],derived);self.assertEqual(len(derived['presets']),12)
                second=api.dispatch('levels.preset',{**p,'artifact_id':built['artifact_id'],'preset_id':'sml-1-2'});self.assertTrue(second['ok'],second)
                self.assertEqual(second['definition']['source_sha256'],built['sha256']);self.assertEqual(path.read_bytes(),raw)
            finally:api.close()

    def test_program_pointer_and_interactive_changes_invalidate_the_known_layout(self):
        from romancer import level_presets
        raw=authored_source();baseline=level_presets.layout_fingerprint(raw)
        for offset in(0x300,0x4000,0xa000):
            changed=bytearray(raw);changed[offset]^=1
            try:result=level_presets.layout_fingerprint(bytes(changed))
            except ValueError:continue
            self.assertNotEqual(result,baseline,hex(offset))
        changed=bytearray(raw);changed[0xa002]=6
        self.assertEqual(level_presets.layout_fingerprint(bytes(changed)),baseline)
        changed[0xa002]=0x70
        self.assertNotEqual(level_presets.layout_fingerprint(bytes(changed)),baseline)
        changed=bytearray(raw);changed[0x9032]^=255;changed[0x1a6]=0xd2
        self.assertEqual(level_presets.layout_fingerprint(bytes(changed)),baseline)
