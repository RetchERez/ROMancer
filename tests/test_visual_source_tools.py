import base64,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from romancer.asset_codecs import encode_cell,decode_cell
from romancer.boot_fixtures import make_boot_fixture
from romancer.graphics_discovery import SYSTEM_CODECS
from romancer.workbench_api import WorkbenchAPI
from romancer.replay_journal import execution_context

class VisualSourceToolTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()));self.api=WorkbenchAPI(self.root/'work');self.addCleanup(self.api.close)
        core=self.root/'unit-test-core';core.write_bytes(b'unit fixture; native sampling mocked')
        self.config={'core':str(core),'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'core_options':{},'system_dir':None,'system_files':[]}
    def prepare(self,system,height=8,zero_last=False):
        codec=SYSTEM_CODECS[system];pixels=[1+(x+y)%3 for y in range(height) for x in range(8)]
        if zero_last:pixels[-1]=0
        tile=b''.join(encode_cell(pixels[i:i+64],codec=codec,width=8,height=8) for i in range(0,len(pixels),64))
        if system=='sms':raw=bytearray(32768);raw[0x7ff0:0x7ff8]=b'TMR SEGA';raw[0x7fff]=0x4c
        else:raw=bytearray(make_boot_fixture(system)['data'])
        raw[4096:4096+len(tile)]=tile;f=self.root/(system+'.rom');f.write_bytes(raw)
        p={'project_id':self.api.dispatch('project.create',{'name':system+' causal test'})['project_id']};s=self.api.dispatch('source.import',{**p,'path':str(f),'system':None});self.assertTrue(s['ok'],s);sp={**p,'artifact_id':s['artifact_id']}
        def sample(project,row,config,steps,cancelled):
            if cancelled():raise KeyboardInterrupt
            if project is not None:
                folder=Path(project)/'sessions/test-unit-sample';folder.mkdir(parents=True,exist_ok=True);(folder/'owned-runtime-copy').write_bytes(b'test')
            r=Path(row['path']).read_bytes()[4096:4096+len(tile)];pp=sum([decode_cell(r[i:i+16],codec=codec,width=8,height=8) for i in range(0,len(r),16)],[]) if height==16 else decode_cell(r,codec=codec,width=8,height=8);colors=[(0,0,0),(255,0,0),(0,255,0),(0,0,255)];rgb=bytes(c for i in pp for c in colors[i]);frame={'ok':True,'width':8,'height':height,'index':10,'sha256':hashlib.sha256(rgb).hexdigest(),'rgb24_base64':base64.b64encode(rgb).decode(),'game_sha256':row['sha256'],'core_sha256':config['expected_core_sha256'],'runtime_identity_sha256':'c'*64}
            return {'frame':frame,'worker_exit_code':0,'state_replay':True,'execution_sha256':'e'*64}
        frame=sample(None,s,self.config,[],lambda:False)['frame'];replay={'status':'READY','version':1,'frames':10,'steps':[{'frames':10,'buttons':[],'port':0}],'context':execution_context(self.config)}
        with patch.object(self.api.runtime,'request',return_value=frame),patch.object(self.api.runtime,'replay_snapshot',return_value=replay):trace=self.api.dispatch('traces.capture',{**sp,'name':'Known unit pixels','frame_sha256':frame['sha256'],'region':{'x':0,'y':0,'width':8,'height':height},'offset':4096,'length':len(tile)})
        self.assertTrue(trace['ok'],trace)
        return sp,s,trace,sample
    def test_seven_systems_verify_via_real_romancer_plans_without_adding_user_builds(self):
        for system in SYSTEM_CODECS:
            with self.subTest(system=system):
                sp,source,trace,sample=self.prepare(system)
                with patch.object(self.api,'_profile_load_config',return_value=self.config),patch('romancer.visual_source_tools.run_sample',side_effect=sample):r=self.api.dispatch('traces.verify',{**sp,'trace_id':trace['trace_id'],'start':0,'limit':1})
                self.assertTrue(r['ok'],r);self.assertEqual(r['status'],'VERIFIED_VISUAL_SOURCE',r);self.assertTrue(r['verified_matches']);self.assertTrue(r['original_reproduced_twice']);self.assertTrue(r['restored_control']['frame_matches']);self.assertFalse(r['source_transfer_observed'])
                p=self.api.dispatch('project.open',{'project_id':sp['project_id']});self.assertEqual(p['builds'],[]);self.assertEqual(hashlib.sha256((self.root/(system+'.rom')).read_bytes()).hexdigest(),source['sha256'])
                opened=self.api.dispatch('traces.open_verified',{**sp,'verification_id':r['verification_id'],'matches':[r['verified_matches'][0]['match_id']]});self.assertTrue(opened['ok'],opened);self.assertTrue(opened['source_dependency_verified']);self.assertEqual(opened['layout']['provenance'],'causal_replay')
                self.assertEqual(list((self.api.project(sp)/'sessions').glob('source-test-*')),[])
                self.assertEqual(list((self.api.project(sp)/'sessions').glob('test-*')),[],'All original and probe replay files must be owned by temporary storage.')
                graph=self.api.dispatch('gameview.graph',{**sp,'query':'','kind':'verified_source','page':0});self.assertTrue(graph['ok'],graph);self.assertTrue(graph['nodes']);self.assertTrue(all(n['confidence']=='causal_replay' for n in graph['nodes']))
                from romancer.workbench_evidence import quarantine_restored_evidence
                quarantine_restored_evidence(self.api.project(sp))
                self.assertFalse(self.api.dispatch('traces.open_verified',{**sp,'verification_id':r['verification_id'],'matches':[r['verified_matches'][0]['match_id']]})['ok'])
    def test_unstable_replay_and_changed_context_do_not_create_verified_authority(self):
        sp,source,trace,sample=self.prepare('nes')
        changed={**self.config,'core_options':{'altered':'yes'}}
        with patch.object(self.api,'_profile_load_config',return_value=changed):r=self.api.dispatch('traces.verify',{**sp,'trace_id':trace['trace_id'],'start':0,'limit':1})
        self.assertFalse(r['ok']);self.assertIn('context',r['error'].lower())
        n=0
        def unstable(*args):
            nonlocal n
            n+=1;r=sample(*args)
            if n==2:
                rgb=bytearray(base64.b64decode(r['frame']['rgb24_base64']));rgb[0]^=1;r['frame']['rgb24_base64']=base64.b64encode(rgb).decode();r['frame']['sha256']=hashlib.sha256(rgb).hexdigest()
            return r
        with patch.object(self.api,'_profile_load_config',return_value=self.config),patch('romancer.visual_source_tools.run_sample',side_effect=unstable):r=self.api.dispatch('traces.verify',{**sp,'trace_id':trace['trace_id'],'start':0,'limit':1})
        self.assertTrue(r['ok'],r);self.assertEqual(r['status'],'INCONCLUSIVE');self.assertEqual(r['verified_matches'],[])
        self.assertFalse(self.api.dispatch('traces.open_verified',{**sp,'verification_id':r['verification_id'],'matches':[0]})['ok'])

    def test_second_original_context_and_later_empty_page_preserve_correct_authority(self):
        sp,source,trace,sample=self.prepare('nes');n=0
        def changed(*args):
            nonlocal n
            n+=1;r=sample(*args)
            if n==2:r['execution_sha256']='f'*64
            return r
        params={**sp,'trace_id':trace['trace_id'],'start':0,'limit':1}
        with patch.object(self.api,'_profile_load_config',return_value=self.config),patch('romancer.visual_source_tools.run_sample',side_effect=changed):r=self.api.dispatch('traces.verify',params)
        self.assertTrue(r['ok'],r);self.assertEqual(r['status'],'INCONCLUSIVE');self.assertEqual(r['verified_matches'],[])
        with patch.object(self.api,'_profile_load_config',return_value=self.config),patch('romancer.visual_source_tools.run_sample',side_effect=sample):
            good=self.api.dispatch('traces.verify',params);later=self.api.dispatch('traces.verify',{**params,'start':1})
        self.assertEqual(good['status'],'VERIFIED_VISUAL_SOURCE',good);self.assertEqual(later['status'],'NOT_VERIFIED')
        graph=self.api.dispatch('gameview.graph',{**sp,'query':'','kind':'verified_source','page':0});self.assertTrue(graph['nodes'],'Later unsuccessful pages must not hide previously proved sources.')
        saved=self.api.dispatch('traces.get',{**sp,'trace_id':trace['trace_id']});self.assertEqual(saved['verification_summary']['verification_id'],good['verification_id']);self.assertEqual(len(saved['verification_history']),3)

    def test_transparent_highest_code_bit_uses_an_unchanged_control_and_cancel_releases_capacity(self):
        sp,source,trace,sample=self.prepare('nes',16,True)
        from romancer.visual_source import group_candidates
        groups=group_candidates(trace,0,8)['groups'];start=next(i for i,g in enumerate(groups) if g['length']==32)
        with patch.object(self.api,'_profile_load_config',return_value=self.config),patch('romancer.visual_source_tools.run_sample',side_effect=sample):r=self.api.dispatch('traces.verify',{**sp,'trace_id':trace['trace_id'],'start':start,'limit':1})
        self.assertEqual(r['status'],'VERIFIED_VISUAL_SOURCE',r);self.assertTrue(any(x.get('unchanged_control') for x in r['groups'][0]['locator_runs']))
        def interrupted(*args):raise KeyboardInterrupt
        with patch.object(self.api,'_profile_load_config',return_value=self.config),patch('romancer.visual_source_tools.run_sample',side_effect=interrupted):
            cancelled=self.api.dispatch('traces.verify',{**sp,'trace_id':trace['trace_id'],'start':0,'limit':1});self.assertFalse(cancelled['ok']);self.assertEqual(cancelled['status'],'CANCELLED')
        from romancer.visual_source_tools import VisualSourceTools
        self.assertTrue(VisualSourceTools.capacity.acquire(blocking=False));VisualSourceTools.capacity.release();self.assertEqual(list((self.api.project(sp)/'sessions').glob('source-test-*')),[])

    def test_failed_native_probe_cleans_all_temporary_original_and_build_copies(self):
        sp,source,trace,sample=self.prepare('nes');n=0
        def fail(*args):
            nonlocal n
            n+=1
            if n==3:raise RuntimeError('unit native failure')
            return sample(*args)
        with patch.object(self.api,'_profile_load_config',return_value=self.config),patch('romancer.visual_source_tools.run_sample',side_effect=fail):r=self.api.dispatch('traces.verify',{**sp,'trace_id':trace['trace_id'],'start':0,'limit':1})
        self.assertFalse(r['ok']);self.assertEqual(list((self.api.project(sp)/'sessions').glob('test-*')),[])

if __name__=='__main__':unittest.main()

class SourceTestCleanupTests(unittest.TestCase):
    def test_closed_worker_loader_locks_are_retried_without_deleting_an_unowned_directory(self):
        from romancer.visual_source_tools import source_test_directory
        import tempfile,shutil
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);real=shutil.rmtree;attempts=[]
            def delayed(path,*a,**kw):
                attempts.append(Path(path))
                if len(attempts)<9:raise PermissionError('closed DLL still scanned')
                return real(path,*a,**kw)
            with patch('romancer.visual_source_tools.shutil.rmtree',side_effect=delayed),patch('romancer.visual_source_tools.time.sleep') as sleep:
                with source_test_directory(root) as owned:(owned/'owned.dll').write_bytes(b'original test')
            self.assertFalse(owned.exists());self.assertEqual(len(attempts),9);self.assertTrue(all(p.parent==root for p in attempts));self.assertLessEqual(sum(c.args[0] for c in sleep.call_args_list),30)
