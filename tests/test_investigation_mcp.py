from romancer.boot_fixtures import make_boot_fixture
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from romancer.mcp_server import MCPServer,MAX_RESULT


class InvestigationMCPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.reader=MCPServer(self.root/'workspace');self.addCleanup(self.reader.close)
        self.writer=MCPServer(self.root/'workspace',allow_writes=True,read_roots=[self.root/'roms']);self.addCleanup(self.writer.close)

    def test_read_only_investigation_and_opted_in_observation_operations(self):
        for operation in ('systems.address','resources.address_uses','watches.compare','debug.inspect','compression.inspect'):
            with self.subTest(operation=operation):self.assertIn(operation,self.reader.operations)
        for operation in ('values.start','values.narrow','watches.save','video.inspect','compression.extract','compression.plan_reinsert','definitions.export','definitions.import'):
            with self.subTest(operation=operation):
                self.assertNotIn(operation,self.reader.operations);self.assertIn(operation,self.writer.operations)
                self.assertTrue(self.reader.call('romancer_call',{'operation':operation,'parameters':{}})['isError'])
        for operation in ('debug.observe','runtime.load','profiles.save','system.pick_file'):
            self.assertNotIn(operation,self.writer.operations)

    def test_shapes_include_nullable_values_and_bounded_objects_arrays(self):
        tools={tool['name']:tool for tool in self.writer.tools()};schemas={name:tool['inputSchema']['properties'] for name,tool in tools.items() if name!='romancer_call'}
        address=schemas['romancer_systems_address'];self.assertEqual(address['mapping']['type'],'object');self.assertEqual(address['bank']['type'],['integer','null'])
        self.assertEqual(schemas['romancer_values_start']['target']['type'],['integer','null']);self.assertEqual(schemas['romancer_values_start']['signed']['type'],'boolean')
        self.assertEqual(schemas['romancer_values_narrow']['relation']['enum'],['equal','changed','unchanged','increased','decreased'])
        watches=schemas['romancer_watches_save']['watches'];self.assertEqual(watches['type'],'array');self.assertEqual(watches['maxItems'],32);self.assertFalse(watches['items']['additionalProperties'])
        for key in ('before','after'):self.assertEqual(schemas['romancer_watches_compare'][key]['type'],'object')
        for key in ('case','trace'):self.assertEqual(schemas['romancer_debug_inspect'][key]['type'],'object')
        self.assertEqual(schemas['romancer_compression_inspect']['allocation']['maximum'],49152)
        self.assertEqual(schemas['romancer_compression_inspect']['codec']['enum'],['lz10','rle','snes-lz2'])
        self.assertEqual(schemas['romancer_definitions_import']['document']['type'],'object')
        self.assertEqual(schemas['romancer_definitions_export']['kind']['enum'],['script','assets','tables','levels','sound','commands'])
        self.assertTrue(tools['romancer_compression_inspect']['annotations']['readOnlyHint']);self.assertFalse(tools['romancer_values_start']['annotations']['readOnlyHint'])

    def test_removed_system_mapping_is_not_advertised_and_cannot_bypass_release_scope(self):
        schema=next(tool['inputSchema'] for tool in self.reader.tools() if tool['name']=='romancer_systems_address')
        mappings={kind for variant in schema['properties']['mapping']['oneOf'] for kind in variant['properties']['id']['enum']}
        self.assertNotIn('declared-window',mappings);self.assertNotIn('segacd',schema['properties']['system_id']['enum'])
        params,_=self.source()
        result=self.reader.call('romancer_systems_address',{**params,'system_id':'segacd','address':0x200004,'mapping':{'id':'declared-window','cpu_start':0x200000,'file_offset':8,'length':16},'bank':None})
        self.assertTrue(result['isError'],result);self.assertEqual(result['structuredContent']['status'],'BLOCKED');self.assertNotIn('offset',result['structuredContent'])

    def source(self):
        self.root.joinpath('roms').mkdir();path=self.root/'roms/owned.bin';raw=bytearray(make_boot_fixture('snes')['data']);raw[:32]=bytes.fromhex('300400008141')+b'\xff'*26;path.write_bytes(raw)
        created=self.writer.call('romancer_project_create',{'name':'Investigation'})['structuredContent'];pid=created['project_id']
        imported=self.writer.call('romancer_source_import',{'project_id':pid,'path':str(path),'system':None})['structuredContent']
        return {'project_id':pid,'artifact_id':imported['artifact_id']},imported

    def test_compression_inspection_extraction_and_numeric_mapping_use_checked_services(self):
        params,source=self.source()
        result=self.reader.call('romancer_compression_inspect',{**params,'offset':0,'allocation':32,'codec':'rle'})
        self.assertFalse(result['isError'],result);self.assertEqual(result['structuredContent']['decoded_sha256'],hashlib.sha256(b'AAAA').hexdigest())
        extracted=self.writer.call('romancer_compression_extract',{**params,'offset':0,'allocation':32,'codec':'rle'})
        self.assertFalse(extracted['isError'],extracted);self.assertEqual(extracted['structuredContent']['artifact']['compressed_parent']['parent_sha256'],source['sha256'])
        mapped=self.reader.call('romancer_systems_address',{**params,'system_id':'snes','address':0x8004,'mapping':{'id':'lorom','copier_header':0},'bank':None})
        self.assertFalse(mapped['isError'],mapped);self.assertEqual(mapped['structuredContent']['offset'],4);self.assertFalse(mapped['structuredContent']['bank_state_observed'])
        bad=self.reader.call('romancer_systems_address',{**params,'system_id':'snes','address':0x700004,'mapping':{'id':'lorom','copier_header':0},'bank':None})
        self.assertTrue(bad['isError'])
        forbidden=self.writer.call('romancer_source_import',{'project_id':params['project_id'],'path':str(self.root/'secret.bin'),'system':None})
        self.assertTrue(forbidden['isError']);self.assertIn('allowed',forbidden['content'][0]['text'])

    def test_saved_watch_and_comparison_preserve_context_and_do_not_write_memory(self):
        params,_=self.source();watch={'name':'Lives','region':2,'offset':4,'length':1}
        saved=self.writer.call('romancer_watches_save',{**params,'watches':[watch]});self.assertFalse(saved['isError'],saved)
        opened=self.reader.call('romancer_project_open',{'project_id':params['project_id']})['structuredContent']
        self.assertEqual(opened['sources'][0]['descriptors']['watches']['watches'],[watch])
        too_many=self.writer.call('romancer_watches_save',{**params,'watches':[{**watch,'name':str(i)} for i in range(33)]})
        self.assertTrue(too_many['isError'])
        def snapshot(raw,sequence):return {'worker_session_id':'worker','epoch':0,'region':2,'region_size':128,'offset':4,'length':1,
            'game_sha256':'a'*64,'core_sha256':'b'*64,'core_options':{},'sequence':sequence,'raw_hex':raw.hex(),'data_sha256':hashlib.sha256(raw).hexdigest()}
        before,after=snapshot(b'\x01',1),snapshot(b'\x02',2)
        compared=self.reader.call('romancer_watches_compare',{'before':before,'after':after})
        self.assertFalse(compared['isError'],compared);self.assertEqual(compared['structuredContent']['changes'],[{'offset':4,'before':1,'after':2}]);self.assertFalse(compared['structuredContent']['write_event_observed'])
        rejected=self.reader.call('romancer_watches_compare',{'before':before,'after':{**after,'core_options':{'mode':'different'}}})
        self.assertTrue(rejected['isError'])

    def test_definition_roundtrip_uses_project_owned_export_and_source_checks(self):
        params,source=self.source();schema={'schema_version':1,'name':'Bytes','offset':0,'count':2,'stride':1,'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]}
        saved=self.writer.call('romancer_tables_save_definition',{**params,'definition':schema});self.assertFalse(saved['isError'],saved)
        result=self.writer.call('romancer_definitions_export',{**params,'kind':'tables'});self.assertFalse(result['isError'],result)
        self.assertEqual(result['structuredContent']['document']['source']['sha256'],source['sha256'])
        imported=self.writer.call('romancer_definitions_import',{**params,'document':result['structuredContent']['document']});self.assertFalse(imported['isError'],imported)
        forged={**result['structuredContent']['document'],'source':{'sha256':'0'*64,'size':32}}
        self.assertTrue(self.writer.call('romancer_definitions_import',{**params,'document':forged})['isError'])

    def test_explicit_trace_inspection_is_available_without_live_native_loading(self):
        from tests.debug_fixtures import debug_fixture
        from romancer.history import register_build
        params,_=self.source();fixture=debug_fixture();path=self.root/'roms/trace-fixture.bin';raw=bytearray(make_boot_fixture('snes')['data']);raw[:len(fixture['raw'])]=fixture['raw'];fixture['raw']=bytes(raw);fixture['trace']['source']={'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)};fixture['case']['source']={'role':'resource',**fixture['trace']['source']};fixture['case']['trace_sha256']=hashlib.sha256(json.dumps(fixture['trace'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest();path.write_bytes(raw)
        owned=self.writer.call('romancer_source_import',{'project_id':params['project_id'],'path':str(path),'system':None})['structuredContent']
        project=self.writer.api.project(params)
        registered=register_build(project,{'inputs':[{'role':'resource','path':owned['path']}],'output':owned['path'],
            'adapter':{'name':'synthetic','version':'1'},'profile':{'name':'literal','version':'1'},'settings':{}},project)
        fixture['case']['build_id']=registered['build_id']
        result=self.reader.call('romancer_debug_inspect',{'project_id':params['project_id'],'artifact_id':owned['artifact_id'],'case':fixture['case'],'trace':fixture['trace']})
        self.assertFalse(result['isError'],result);self.assertEqual(result['structuredContent']['causation'],'NOT_RUN')
        self.assertEqual(result['structuredContent']['probes'][0]['source']['raw_hex'],'00')

    def test_level_and_sound_definitions_roundtrip_through_actual_mcp_tools(self):
        from romancer.studio_examples import make_studio_example
        params,_=self.source();fixture=make_studio_example();path=self.root/'roms/workshop.nes';path.write_bytes(fixture['raw'])
        owned=self.writer.call('romancer_source_import',{'project_id':params['project_id'],'path':str(path),'system':None})['structuredContent']
        selected={**params,'artifact_id':owned['artifact_id']}
        for kind in ('levels','sound'):
            with self.subTest(kind=kind):
                document={'format':'romancer-definition-v1','source':{'sha256':owned['sha256'],'size':owned['size']},'kind':kind,'definition':fixture[kind]}
                imported=self.writer.call('romancer_definitions_import',{**selected,'document':document});self.assertFalse(imported['isError'],imported)
                exported=self.writer.call('romancer_definitions_export',{**selected,'kind':kind});self.assertFalse(exported['isError'],exported)
                self.assertEqual(exported['structuredContent']['document']['kind'],kind)
                again=self.writer.call('romancer_definitions_import',{**selected,'document':exported['structuredContent']['document']});self.assertFalse(again['isError'],again)
        self.assertEqual(path.read_bytes(),fixture['raw'])

    def test_large_definition_export_keeps_the_existing_ai_response_budget(self):
        params,_=self.source();path=self.root/'roms/large-text.bin';raw=bytearray((b'A\0'+b'\xff'*65534)*3);raw[0x7fc0:0x8000]=make_boot_fixture('snes')['data'][0x7fc0:0x8000];raw[0x7fd7]=8;path.write_bytes(raw)
        owned=self.writer.call('romancer_source_import',{'project_id':params['project_id'],'path':str(path),'system':None})['structuredContent'];selected={**params,'artifact_id':owned['artifact_id']}
        declared=self.writer.call('romancer_resources_declare_script',{**selected,'config':{'system_id':'gb','offset':0,'capacity':65536,'count':3}});self.assertFalse(declared['isError'],declared)
        result=self.writer.call('romancer_definitions_export',{**selected,'kind':'script'});self.assertFalse(result['isError'],result)
        self.assertTrue(result['structuredContent']['result_truncated']);self.assertLessEqual(len(json.dumps(result['structuredContent']).encode('utf-8')),MAX_RESULT)


if __name__=='__main__':unittest.main()
