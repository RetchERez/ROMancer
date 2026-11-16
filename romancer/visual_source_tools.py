"""Source locations verified by isolated ROMancer marker builds and replay."""
import tempfile,threading,shutil,time,os,re
from contextlib import contextmanager
from pathlib import Path
from .assets import checked_path,digest
from .runtime_session import validate_steps
from .replay_journal import execution_context
from .visual_source import group_candidates,locator_markers,learn_mapping,validation_markers,assess_mapping,encoding_lanes
from .visual_checks import _frame
from .build_checks import run_sample as _sample
from .workbench_evidence import load_evidence,store_evidence
from . import workbench_projects as projects


@contextmanager
def source_test_directory(parent):
    parent=checked_path(Path(parent));folder=Path(tempfile.mkdtemp(prefix='source-test-',dir=parent))
    identity=folder.stat()
    try:yield folder
    finally:
        for delay in (0,.05,.1,.2,.4,.8,1.6,3.2,6.4):
            if delay:time.sleep(delay)
            if folder.resolve().parent!=parent.resolve() or not re.fullmatch(r'source-test-[a-zA-Z0-9_-]+',folder.name):
                raise ValueError('Source-test cleanup escaped its owned session directory.')
            checked_path(folder)
            if not folder.exists():break
            if not os.path.samestat(identity,folder.stat()):raise ValueError('Source-test cleanup directory identity changed.')
            try:shutil.rmtree(folder);break
            except FileNotFoundError:break
            except PermissionError:
                if delay==6.4:raise


def run_sample(project,row,configuration,steps,cancelled):
    # Source proof deliberately replays from a cold start; it neither needs nor
    # imports a serialized state. Save-state testing remains in Build checks.
    return _sample(project,row,configuration,steps,cancelled,state_check=False)


def saved_verifications(project,row):
    ids=row.get('visual_source_verifications',[])
    if type(ids) is not list or len(ids)>32:raise ValueError('Source-verification index exceeds its budget.')
    result=[]
    for ident in ids:
        record=load_evidence(project,ident,'runtime');r=record['report']
        if r.get('scope') not in ('visual_source_v1','visual_source_v2') or r.get('source_sha256')!=row['sha256'] or r.get('artifact_id')!=row['artifact_id']:raise ValueError('Source-verification evidence belongs to another revision.')
        result.append({'verification_id':ident,'report':r,'runtime_trusted':record['runtime_trusted'] and r.get('scope')=='visual_source_v2'})
    return result


class VisualSourceTools:
    capacity=threading.BoundedSemaphore(1)
    def __init__(self,api):self.api=api
    def routes(self):return {'traces.verify':('project_id artifact_id trace_id start limit',self.verify),'traces.verification':('project_id artifact_id verification_id',self.get),'traces.open_verified':('project_id artifact_id verification_id matches',self.open),'traces.origin':('project_id artifact_id verification_id match_id',self.origin)}
    def get(self,p,c):
        project,row,_=self.api.source(p);record=load_evidence(project,p['verification_id'],'runtime');r=record['report']
        if r.get('scope') not in ('visual_source_v1','visual_source_v2') or r.get('source_sha256')!=row['sha256'] or r.get('artifact_id')!=row['artifact_id']:raise ValueError('Choose source verification for this exact revision.')
        result={'ok':True,**r,'verification_id':p['verification_id'],'runtime_trusted':record['runtime_trusted'] and r.get('scope')=='visual_source_v2'}
        result['saved_results']=[{'verification_id':v['verification_id'],'status':v['report']['status'],'verified_placements':len(v['report']['verified_matches']),'runtime_trusted':v['runtime_trusted']} for v in saved_verifications(project,row) if v['report']['trace_id']==r['trace_id']]
        return result
    def origin(self,p,c):
        from .asset_schema import number
        number(p['match_id'],0,255);r=self.get(p,c);part=next((m for m in r['verified_matches'] if m['match_id']==p['match_id']),None)
        if part is None:raise ValueError('Choose a verified origin from this source report.')
        return {k:r[k] for k in ('ok','verification_id','source_sha256','artifact_id','trace_id','context','runtime_trusted','proof_method','source_transfer_observed')}|{'origin':part}
    def open(self,p,c):
        r=self.get(p,c);chosen=p['matches'];valid={v['match_id'] for v in r['verified_matches']}
        if not r['runtime_trusted'] or r['status']!='VERIFIED_VISUAL_SOURCE' or type(chosen) is not list or len(chosen)!=1 or any(type(i) is not int or i not in valid for i in chosen):raise ValueError('Choose parts with fresh authenticated source verification.')
        result=self.api.traces.open({**p,'trace_id':r['trace_id']},c)
        result.update(candidate_only=False,source_dependency_verified=True,verification_id=p['verification_id']);result['layout']['provenance']='causal_replay';part=next(m for m in r['verified_matches'] if m['match_id']==chosen[0]);result['layout']['flips']=[0]*len(result['layout']['indices']);result['layout']['colors']=[part['source_colors']]*len(result['layout']['indices'])
        return result

    def verify(self,p,c):
        project,row,path=self.api.source(p);trace=self.api.traces.get(p,c);replay=trace.get('replay',{})
        if trace.get('checkpoint_only'):raise ValueError('Trace a sprite or tile selection before verifying its ROM source.')
        if not trace['runtime_trusted'] or replay.get('status')!='READY':raise ValueError('Source verification needs a fresh authenticated cold-start replay. Close and load the game again, then capture the object.')
        steps=replay['steps']
        for step in steps:validate_steps([step])
        if len(steps)>2048 or not 0<sum(s['frames'] for s in steps)<=36000 or sum(s['frames'] for s in steps)!=replay['frames']:raise ValueError('The replay exceeds its bounded frame or step budget.')
        config=self.api._profile_load_config(row['system_id'],row,project)
        if execution_context(config)!=replay['context']:raise ValueError('Core options, controllers or system-file context changed. Restore the captured setup or capture a fresh trace.')
        groups=group_candidates(trace,p['start'],p['limit']);result={'scope':'visual_source_v2','source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'system_id':row['system_id'],'trace_id':p['trace_id'],'context':replay['context'],'replay_sha256':digest(replay),'frame':trace['frame'],
            'status':'NOT_VERIFIED','verified_matches':[],'groups':[],'coverage':{k:v for k,v in groups.items() if k!='groups'},'original_reproduced_twice':False,'source_transfer_observed':False,'proof_method':'coded_romancer_build_replay','original_preserved':True,
            'scope_note':'Coded interventions verify causal literal ROM storage-to-screen pixel origins under this replay. CPU/VDP/DMA fetches and compression formats are not observed.'}
        if not self.capacity.acquire(blocking=False):raise ValueError('A source verification is already running. Wait for it to finish or cancel that job.')
        try:
            self._execute(project,row,path,trace,config,steps,groups,result,c)
            if c():raise KeyboardInterrupt
            projects._measure(path,row,cancelled=c)
            with projects.locked(project) as store:
                evidence=store_evidence(project,'runtime',result);owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);owned['visual_source_verifications']=(owned.get('visual_source_verifications',[])+[evidence['evidence_id']])[-32:];projects.write_json(project/'project.json',store)
            return self.get({**p,'verification_id':evidence['evidence_id']},c)
        finally:self.capacity.release()

    @staticmethod
    def _receipt(sample):return {k:sample[k] for k in ('state_replay','worker_exit_code','execution_sha256')}|{'frame_sha256':sample['frame']['sha256']}

    def _execute(self,project,row,path,trace,config,steps,groups,result,c):
        from .system_integrity import integrity_edits
        parent=checked_path(project/'sessions');parent.mkdir(exist_ok=True);pending=[];seen_verified=set();restored=None;identities=[]
        with source_test_directory(parent) as temporary:
            if Path(temporary).resolve().parent!=parent.resolve():raise ValueError('Temporary verification storage escaped its owned session folder.')
            probe_root=Path(projects.create_project(Path(temporary),'Temporary source verification')['path']);source=projects.register_source(probe_root,path,None,cancelled=c)
            first=run_sample(probe_root,source,config,steps,c);second=run_sample(probe_root,source,config,steps,c);_frame(first['frame']);_frame(second['frame']);identities.extend(r['execution_sha256'] for r in (first,second))
            if first['frame']['sha256']!=second['frame']['sha256'] or first['frame']['sha256']!=trace['frame']['sha256'] or first['frame']['index']!=replay_frames(steps) or first['execution_sha256']!=second['execution_sha256']:
                result.update(status='INCONCLUSIVE',reason='The original frame or effective execution context did not reproduce twice. No source authority was granted.');return
            result['original_reproduced_twice']=True;result['original_runs']=[self._receipt(r) for r in (first,second)]
            for group in groups['groups']:
                if c():raise KeyboardInterrupt
                entry={'offset':group['offset'],'length':group['length'],'match_ids':group['match_ids'],'status':'NOT_VERIFIED','locator_runs':[],'probes':[]};result['groups'].append(entry)
                match=trace['matches'][group['match_ids'][0]]
                with path.open('rb') as f:f.seek(group['offset']);raw=f.read(group['length'])
                def sample_marker(marker,receipts):
                    nonlocal restored
                    if marker['after']==raw:
                        sample=run_sample(probe_root,source,config,steps,c);identities.append(sample['execution_sha256']);receipts.append({'unchanged_control':True,'source_sha256':source['sha256'],**self._receipt(sample)});return sample['frame']
                    edits=integrity_edits(Path(source['path']),source['sha256'],row['system_id'],[{'offset':group['offset'],'before':raw.hex(),'after':marker['after'].hex()}])
                    plan=projects.plan_byte_edits(probe_root,source['artifact_id'],edits,annotations={'kind':'visual-source-diagnostic','purpose':marker['name']});build=projects.apply_build(probe_root,plan['plan_id'],cancelled=c);sample=run_sample(probe_root,build,config,steps,c);identities.append(sample['execution_sha256'])
                    receipts.append({'plan_id':plan['plan_id'],'source_sha256':source['sha256'],'target_sha256':build['sha256'],'changed_ranges':[{'offset':e['offset'],'length':len(e['after'])//2} for e in edits],**self._receipt(sample)})
                    if restored is None:
                        reverse=[{'offset':e['offset'],'before':e['after'],'after':e['before']} for e in edits];undo=projects.plan_byte_edits(probe_root,build['artifact_id'],reverse,annotations={'kind':'visual-source-restored-control'});restored=projects.apply_build(probe_root,undo['plan_id'],cancelled=c)
                        if restored['sha256']!=row['sha256']:raise ValueError('The restored control does not equal the original ROM hash.')
                    return sample['frame']
                try:locators=locator_markers(raw,match)
                except ValueError as e:entry['reason']=str(e);continue
                locator_frames=[sample_marker(marker,entry['locator_runs']) for marker in locators];mappings=[];entry['mapping_failures']=[]
                for ident in group['match_ids']:
                    try:mappings.append((ident,learn_mapping(first['frame'],locator_frames,trace['matches'][ident],locators)))
                    except ValueError as e:entry['mapping_failures'].append({'match_id':ident,'reason':str(e)})
                if not mappings:entry['reason']='Coded probes did not recover enough distinct pixel origins. No source was promoted.';continue
                best=max(mappings,key=lambda r:r[1]['unique_source_pixels']);markers=validation_markers(raw,match,best[1]);validation_frames=[sample_marker(marker,entry['probes']) for marker in markers]
                for ident,mapping in mappings:
                    checked=assess_mapping(first['frame'],validation_frames,trace['matches'][ident],mapping,markers)
                    if checked['status']=='VERIFIED_VISUAL_SOURCE':
                        m=trace['matches'][ident];entry['status']='VERIFIED_VISUAL_SOURCE';key=(m['offset'],m['length'],m['x'],m['y'],digest(checked['pixel_map']))
                        if key not in seen_verified:
                            seen_verified.add(key)
                            if len(pending)<16:
                                for point in checked['pixel_map']:point['encoded_bytes']=encoding_lanes(m,point['source_pixel'])
                                pending.append({'match_id':ident,'width':8,'codec':m['codec'],'offset':m['offset'],'length':m['length'],'x':m['x'],'y':m['y'],'height':m['height'],**checked})
                            else:result['verified_placements_truncated']=True
                if entry['status']!='VERIFIED_VISUAL_SOURCE':entry['reason']='Independent validation did not confirm every recovered pixel and spatial color control.'
            if restored is not None:
                control=run_sample(probe_root,restored,config,steps,c);identities.append(control['execution_sha256']);_frame(control['frame']);result['restored_control']={'source_sha256':restored['sha256'],'frame_matches':control['frame']['sha256']==first['frame']['sha256'],**self._receipt(control)}
                if not result['restored_control']['frame_matches'] or len(set(identities))!=1:
                    result.update(status='INCONCLUSIVE',reason='Restored control or execution context differed. No source authority was granted.');return
            result['verified_matches']=pending;result.update(status='VERIFIED_VISUAL_SOURCE' if pending else 'NOT_VERIFIED',reason='Coded probes and independent validations verified '+str(len(pending))+' visible placements.' if pending else 'No tested source passed coded pixel recovery and independent validation. Continue searching or investigate compression/transforms.')


def replay_frames(steps):return sum(step['frames'] for step in steps)
