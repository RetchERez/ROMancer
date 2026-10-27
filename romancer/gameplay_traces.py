"""Persistent measured screen-to-literal-ROM candidates across tested codecs."""
import threading
from .asset_schema import label
from .workbench_evidence import load_evidence,store_evidence
from . import workbench_projects as projects


def saved_traces(project,row):
    index=row.get('gameplay_traces')
    if index is None:return []
    if type(index) is not dict or set(index)!={'source_sha256','ids'} or index['source_sha256']!=row['sha256'] or type(index['ids']) is not list or len(index['ids'])>32:raise ValueError('Trace index belongs to another source or exceeds its budget.')
    result=[]
    for ident in index['ids']:
        record=load_evidence(project,ident,'runtime');r=record['report']
        if r.get('scope')!='gameplay_trace_v1' or r.get('source_sha256')!=row['sha256'] or r.get('artifact_id')!=row['artifact_id']:raise ValueError('Saved trace source differs.')
        result.append({'trace_id':ident,'report':r,'runtime_trusted':record['runtime_trusted']})
    return result


class GameplayTraceTools:
    def __init__(self,api):self.api=api
    def routes(self):return {'traces.capture':('project_id artifact_id name frame_sha256 region offset length',self.capture),'traces.get':('project_id artifact_id trace_id',self.get),'traces.open':('project_id artifact_id trace_id matches',self.open)}
    def capture(self,p,c):
        from .visual_checks import _frame,_crop,_png,_region
        label(p['name'],80)
        if p['region'] is None:raise ValueError('Select a captured region up to 256 by 256 pixels before saving a trace.')
        observed=self.api._graphics_observe({k:p[k] for k in ('project_id','artifact_id','frame_sha256','region','offset','length')},c)
        project,row,path=self.api.source(p);frame=self.api.runtime.request(project,'capture',{},cancelled=c)
        if frame['sha256']!=observed['frame']['sha256'] or frame['game_sha256']!=row['sha256']:raise ValueError('The measured frame changed. Pause and trace the selection again.')
        width,height,rgb=_frame(frame);region=p['region'] or {'x':0,'y':0,'width':min(256,width),'height':min(256,height)};_region(region,width,height)
        report={**observed,'scope':'gameplay_trace_v1','name':p['name'],'graphics_evidence_id':observed['evidence_id'],'region':region,
                'crop_png_base64':_png(_crop(rgb,width,region),region['width'],region['height']),'source_transfer_observed':False}
        try:report['replay']=self.api.runtime.replay_snapshot(project,frame)
        except (ValueError,KeyError):report['replay']={'status':'UNAVAILABLE','reason':'No acknowledged cold-start replay is available. Load the game again and capture a fresh trace.'}
        report.pop('evidence_id',None)
        with self.api.operation_locks_guard:lock=self.api.operation_locks.setdefault(p['project_id'],threading.RLock())
        with lock:
            self.api.project(p);projects._measure(path,row,cancelled=c)
            if c():raise KeyboardInterrupt
            with projects.locked(project) as store:
                owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);repaired=False
                try:previous=saved_traces(project,owned)
                except (ValueError,OSError,KeyError,TypeError):
                    previous=[];repaired=True;index=owned.get('gameplay_traces');ids=index.get('ids',[]) if type(index) is dict else []
                    for ident in ids[:32] if type(ids) is list else []:
                        try:previous.extend(saved_traces(project,{**owned,'gameplay_traces':{'source_sha256':row['sha256'],'ids':[ident]}}))
                        except (ValueError,OSError,KeyError,TypeError):pass
                report['trace_index_repaired']=repaired;evidence=store_evidence(project,'runtime',report)
                owned['gameplay_traces']={'source_sha256':row['sha256'],'ids':[r['trace_id'] for r in previous][-31:]+[evidence['evidence_id']]};projects.write_json(project/'project.json',store)
        return {'ok':True,**report,'trace_id':evidence['evidence_id'],'runtime_trusted':True}
    def get(self,p,c):
        project,row,_=self.api.source(p);record=load_evidence(project,p['trace_id'],'runtime');report=record['report']
        if report.get('scope')!='gameplay_trace_v1' or report.get('source_sha256')!=row['sha256'] or report.get('artifact_id')!=row['artifact_id']:raise ValueError('Choose a trace from this exact source revision.')
        result={'ok':True,**report,'trace_id':p['trace_id'],'runtime_trusted':record['runtime_trusted']}
        from .visual_source_tools import saved_verifications
        try:
            history=[v for v in saved_verifications(project,row) if v['report']['trace_id']==p['trace_id']]
            result['verification_history']=[{'verification_id':v['verification_id'],'status':v['report']['status'],'runtime_trusted':v['runtime_trusted']} for v in history]
            latest=next((v for v in reversed(history) if v['runtime_trusted'] and v['report']['status']=='VERIFIED_VISUAL_SOURCE'),history[-1] if history else None)
            if latest:result['verification_summary']={'verification_id':latest['verification_id'],'status':latest['report']['status'],'verified_placements':len(latest['report']['verified_matches']),'runtime_trusted':latest['runtime_trusted']}
        except (ValueError,OSError,KeyError):result['verification_issue']='Saved verification index is unavailable; capture a fresh trace and verify again.'
        return result
    def open(self,p,c):
        report=self.get(p,c)
        if not report['runtime_trusted']:raise ValueError('This is historical imported evidence. Capture a fresh local trace before opening candidates for editing.')
        return self.api._graphics_declare({k:p[k] for k in ('project_id','artifact_id','matches')}|{'evidence_id':report['graphics_evidence_id']},c)
