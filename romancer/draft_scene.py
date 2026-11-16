"""Measured full-scene previews of checked drafts; no user build is published."""
import threading
from pathlib import Path
from .asset_schema import fields
from .assets import digest,plan_assets,checked_path
from .script_schema import load_script_json
from .replay_journal import execution_context
from .build_checks import run_sample,validate_config,compare_frames
from .visual_checks import _frame
from .visual_source_tools import source_test_directory
from .workbench_evidence import store_evidence,load_evidence
from . import workbench_projects as projects

class DraftSceneTools:
    def __init__(self,api):self.api=api;self.capacity=threading.BoundedSemaphore(1)
    def routes(self):
        return {'assets.preview_scene':('project_id artifact_id plan_id trace_id',self.preview),
                'assets.preview_scene.get':('project_id artifact_id plan_id trace_id evidence_id schema edits',self.get),
                'assets.preview_scene.find':('project_id artifact_id trace_id schema edits',self.find)}
    def _plan(self,p,c):
        project,row,path=self.api.source(p)
        from .release_scope import require_supported
        require_supported(row);projects.identifier(p['plan_id'])
        if row['size']>64*1024**2:raise ValueError('Native draft scene previews support cartridge images up to 64 MiB.')
        envelope=load_script_json(checked_path(project/'plans'/(p['plan_id']+'.json')),max_bytes=8*1024**2)
        if digest(envelope)!=p['plan_id'] or envelope.get('kind')!='assets' or envelope.get('artifact_id')!=row['artifact_id']:
            raise ValueError('Choose a reviewed graphics plan for this exact selected ROM.')
        fields(envelope,'kind artifact_id schema edits service_plan_id integrity_edits')
        plan=plan_assets(path,envelope['schema'],envelope['edits'])
        if not plan.get('ok') or plan.get('plan_id')!=envelope['service_plan_id']:raise ValueError('The graphics plan changed. Review the current draft again.')
        if not plan['hunks']:raise ValueError('Stage a palette or graphic change before previewing it in a captured scene.')
        edits=[{'offset':h['offset'],'before':h['before_hex'],'after':h['after_hex']} for h in plan['hunks']]
        from .system_integrity import integrity_edits
        repaired=integrity_edits(path,row['sha256'],row['system_id'],edits)
        if repaired[len(edits):]!=envelope['integrity_edits']:raise ValueError('Cartridge integrity repairs changed. Review the draft again.')
        trace=self.api.traces.get({**p,'trace_id':p['trace_id']},c);replay=trace.get('replay',{})
        if not trace.get('runtime_trusted') or replay.get('status')!='READY':raise ValueError('Capture a fresh authenticated cold-start trace for this ROM first.')
        config=validate_config({'name':'Draft scene preview','automatic':False,'mode':'review_changes','steps':replay['steps'],'region':None,'route_ids':[]})
        if sum(s['frames'] for s in config['steps'])!=replay['frames']:raise ValueError('The captured replay frame count differs.')
        return project,row,path,envelope,plan,repaired,trace,config
    def preview(self,p,c):
        project,row,path,envelope,plan,edits,trace,config=self._plan(p,c)
        configuration=self.api._profile_load_config(row['system_id'],row,project)
        if execution_context(configuration)!=trace['replay']['context']:raise ValueError('The captured execution setup changed. Restore it or capture a fresh trace.')
        if not self.capacity.acquire(blocking=False):raise ValueError('A draft scene preview is already running. Wait for it or cancel that job.')
        try:
            parent=checked_path(project/'sessions');parent.mkdir(exist_ok=True)
            result={'ok':True,'scope':'draft_scene_preview_v1','artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'plan_id':p['plan_id'],'service_plan_id':plan['plan_id'],'trace_id':p['trace_id'],
                    'preview_only':True,'simulated':False,'emulated_frame':False,'gameplay_verified':False,'original_reproduced_twice':False,'source_preserved':True,'user_builds_added':0,'context':execution_context(configuration),
                    'scope_note':'Native replay of a temporary checked draft. This measures the captured route, not all gameplay or general palette ownership. Create a separate build to keep the edit.'}
            with source_test_directory(parent) as temporary:
                private=Path(projects.create_project(Path(temporary),'Temporary draft scene preview')['path'])
                source=projects.register_source(private,path,None,cancelled=c)
                if source['sha256']!=row['sha256']:raise ValueError('The selected source changed before previewing.')
                first=run_sample(private,source,configuration,config['steps'],c);second=run_sample(private,source,configuration,config['steps'],c)
                for sample in (first,second):
                    width,height,_=_frame(sample['frame'])
                    if width*height>262144:raise ValueError('The full scene exceeds the 262,144-pixel preview budget.')
                stable=(first['frame']['sha256']==second['frame']['sha256']==trace['frame']['sha256'] and first['frame']['index']==second['frame']['index']==trace['replay']['frames'] and first['execution_sha256']==second['execution_sha256'])
                if not stable:result.update(status='INCONCLUSIVE',reason='The original did not reproduce the captured scene twice. Capture a fresh cold-start trace.')
                else:
                    if c():raise KeyboardInterrupt
                    reviewed=projects.plan_byte_edits(private,source['artifact_id'],edits,annotations={'kind':'checked-asset-draft-preview','reviewed_assets_plan':p['plan_id']})
                    draft=projects.apply_build(private,reviewed['plan_id'],cancelled=c)
                    candidate=run_sample(private,draft,configuration,config['steps'],c)
                    width,height,_=_frame(candidate['frame'])
                    if width*height>262144:raise ValueError('The draft scene exceeds the full-frame preview budget.')
                    if candidate['execution_sha256']!=first['execution_sha256']:raise ValueError('The effective engine settings changed between preview runs.')
                    result.update(compare_frames(first['frame'],second['frame'],candidate['frame'],None,'review_changes'))
                    if result['status']!='INCONCLUSIVE':result.update(emulated_frame=True,original_reproduced_twice=True,draft_sha256=draft['sha256'])
                    result['runs']=[{'frame_sha256':s['frame']['sha256'],'frame_index':s['frame']['index'],'execution_sha256':s['execution_sha256'],'state_replay':s['state_replay'],'worker_exit_code':s['worker_exit_code']} for s in (first,second,candidate)]
            if c():raise KeyboardInterrupt
            projects._measure(path,row,cancelled=c)
            stored=store_evidence(project,'runtime',result)
            with projects.locked(project) as store:
                owned=next(a for a in store['sources']+store['builds'] if a['artifact_id']==row['artifact_id'])
                projects._measure(path,owned,cancelled=c)
                index=self._index(owned)
                entry={'plan_id':p['plan_id'],'trace_id':p['trace_id'],'evidence_id':stored['evidence_id'],'service_plan_id':plan['plan_id']}
                index=[e for e in index if (e['plan_id'],e['trace_id'])!=(p['plan_id'],p['trace_id'])]
                owned['draft_scene_previews']={'source_sha256':row['sha256'],'entries':(index+[entry])[-16:]}
                projects.write_json(project/'project.json',store)
            return {**result,'evidence_id':stored['evidence_id'],'runtime_trusted':True}
        finally:self.capacity.release()
    def get(self,p,c):
        project,row,path,envelope,plan,edits,trace,config=self._plan(p,c)
        if digest(p['schema'])!=digest(envelope['schema']):raise ValueError('The graphics setup changed. Preview the current draft again.')
        current=plan_assets(path,p['schema'],p['edits'])
        if not current.get('ok') or current.get('plan_id')!=plan['plan_id']:raise ValueError('The draft changed. Update the captured-scene preview.')
        record=load_evidence(project,p['evidence_id'],'runtime');r=record['report']
        if not record['runtime_trusted'] or r.get('scope')!='draft_scene_preview_v1' or any(r.get(k)!=p[k] for k in ('artifact_id','plan_id','trace_id')) or r.get('source_sha256')!=row['sha256'] or r.get('service_plan_id')!=plan['plan_id']:
            raise ValueError('Choose a fresh local draft preview bound to this source, plan and capture.')
        return {**r,'ok':True,'evidence_id':p['evidence_id'],'runtime_trusted':True}
    @staticmethod
    def _index(row):
        saved=row.get('draft_scene_previews')
        if saved is None:return []
        fields(saved,'source_sha256 entries')
        if saved['source_sha256']!=row['sha256'] or type(saved['entries']) is not list or len(saved['entries'])>16:raise ValueError('Saved draft previews belong to another revision or exceed their budget.')
        for entry in saved['entries']:
            fields(entry,'plan_id trace_id evidence_id service_plan_id')
            for value in entry.values():projects.identifier(value)
        return saved['entries']
    def find(self,p,c):
        project,row,path=self.api.source(p);current=plan_assets(path,p['schema'],p['edits'])
        if not current.get('ok'):return {'ok':True,'found':False,'reason':'Review the current editable graphics draft first.'}
        for entry in reversed(self._index(row)):
            if entry['trace_id']==p['trace_id'] and entry['service_plan_id']==current['plan_id']:
                try:return {**self.get({**p,**entry},c),'found':True}
                except (ValueError,OSError):return {'ok':True,'found':False,'reason':'The saved preview no longer matches fresh local evidence. Update it for the current draft.'}
        return {'ok':True,'found':False}
