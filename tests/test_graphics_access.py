import unittest
from romancer.graphics_access import capture_config,public_capture

class GraphicsAccessTests(unittest.TestCase):
    def replay(self,buttons=None):return {'status':'READY','steps':[{'frames':10,'buttons':buttons or [],'port':0}],'frames':10}
    def test_derived_probes_follow_real_source_domains_and_known_controller_mapping(self):
        from romancer.boot_fixtures import make_boot_fixture
        for system in ('nes','snes','gb','gbc','gba','genesis','sms'):
            if system=='sms':raw=bytearray(32768);raw[0x7ff0:0x7ff8]=b'TMR SEGA';raw[0x7fff]=0x4c;raw=bytes(raw)
            else:raw=make_boot_fixture(system)['data']
            r=capture_config(system,raw,self.replay(['a','b','r'] if system=='genesis' else ['a']),4096,32,0)
            self.assertTrue(r['graphics_snapshot']);self.assertGreaterEqual(len(r['probes']),2);self.assertEqual(r['steps'][0]['buttons'],['b','a','c'] if system=='genesis' else ['one'] if system=='sms' else ['a'])
            if system=='sms':self.assertEqual(r['probes'][0]['domain'],'smsPrgRom')
        with self.assertRaises(ValueError):capture_config('genesis',raw,self.replay(['x']),4096,32,0)
    def test_no_fake_replay_or_silent_route_truncation_and_no_hidden_source_range(self):
        for replay in ({'status':'UNAVAILABLE'}, {**self.replay(),'frames':9999}, {'status':'READY','frames':4000,'steps':[{'frames':4000,'buttons':[],'port':0}]}):
            with self.assertRaises(ValueError):capture_config('sms',bytes(32768),replay,4096,32,0)
        with self.assertRaises(ValueError):capture_config('sms',bytes(32768),self.replay(),32760,32,0)
    def test_summary_distinguishes_observed_dma_from_unknown_ownership_and_omitted_events(self):
        r=public_capture({'ok':True,'source_sha256':'a'*64,'artifact_id':'b'*32,'evidence_id':'c'*32,'system_id':'gba','events':[{'id':1,'kind':'read','domain':'gbaPrgRom','file_offset':4096,'actor':'dma','operation_kind':'DmaRead'},{'id':2,'kind':'write','domain':'gbaVideoRam','file_offset':None,'actor':None}], 'omitted_events':9,'route_complete':True,'graphics_snapshot':{'memory':{'gbaVideoRam':{'size':4,'data_hex':'00010203','data_sha256':'x'}},'state':{},'missing_or_partial_domains':[],'point':'end_of_capture','complete_memory_snapshot':False}})
        self.assertEqual(r['observed_rom_offsets'],[4096]);self.assertEqual(r['observed_dma_events'],1);self.assertFalse(r['causal_dataflow_proven']);self.assertEqual(r['omitted_events'],9);self.assertNotIn('data_hex',str(r['memory_domains']));self.assertNotIn('graphics_snapshot',r)


class GraphicsAccessServiceTests(unittest.TestCase):
    def test_saved_capture_list_and_memory_are_exact_source_bound(self):
        import tempfile,hashlib
        from pathlib import Path
        from romancer.workbench_api import WorkbenchAPI
        from romancer.workbench_evidence import store_evidence
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'work')
            try:
                demo=api.dispatch('project.demo_system',{'system_id':'nes'})
                sp={'project_id':demo['project_id'],'artifact_id':demo['sources'][0]['artifact_id']}
                row=demo['sources'][0];project=api.project(sp)
                report={'kind':'native-debugger-capture-v1','source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'system_id':'nes','events':[],
                    'investigation_link':{'graphics_trace_id':'b'*32},'graphics_snapshot':{'memory':{'nesPpuMemory':{'size':4,'data_hex':'00010203','data_sha256':hashlib.sha256(bytes(range(4))).hexdigest()}},'state':{}}}
                rec=store_evidence(project,'runtime',report)
                from romancer.graphics_access import remember_capture
                remember_capture(project,row,rec['evidence_id'])
                listing=api.dispatch('graphics.accesses.list',sp)
                self.assertTrue(listing['ok'],listing);self.assertEqual(listing['captures'][0]['evidence_id'],rec['evidence_id'])
                got=api.dispatch('graphics.accesses.memory',{**sp,'evidence_id':rec['evidence_id'],'domain':'nesPpuMemory','offset':1,'length':2})
                self.assertEqual(got['raw_hex'],'0102');self.assertFalse(got['write_authorized'])
                tiles=api.dispatch('graphics.accesses.tiles',{**sp,'evidence_id':rec['evidence_id'],'domain':'nesPpuMemory','offset':0,'count':1,'codec':'tile8-planar2-msb-v1'})
                self.assertFalse(tiles['ok'],'Truncated cells must not be padded into plausible pictures')
                full={**report,'graphics_snapshot':{'memory':{'nesPpuMemory':{'size':16,'data_hex':('ff'*8+'00'*8),'data_sha256':hashlib.sha256(bytes([255]*8+[0]*8)).hexdigest()}},'state':{}}}
                fullrec=store_evidence(project,'runtime',full)
                tiles=api.dispatch('graphics.accesses.tiles',{**sp,'evidence_id':fullrec['evidence_id'],'domain':'nesPpuMemory','offset':0,'count':1,'codec':'tile8-planar2-msb-v1'})
                self.assertTrue(tiles['ok'],tiles);self.assertEqual(tiles['cells'][0]['pixels'],[1]*64);self.assertFalse(tiles['rom_source_proven'])
                ordinary=store_evidence(project,'runtime',{**report,'graphics_snapshot':{},'investigation_link':{}})
                got=api.dispatch('graphics.accesses.get',{**sp,'evidence_id':ordinary['evidence_id'],'offset':0,'limit':10})
                self.assertFalse(got['ok']);self.assertRegex(got['error'],'graphics')
            finally:api.close()
if __name__=='__main__':unittest.main()

