"""Repeatable, isolated baseline/build observations and optional post-build jobs."""
import uuid,threading,json
from pathlib import Path
from .asset_schema import fields,label,number
from .assets import digest
from .script_schema import canonical_bytes
from .runtime_session import OwnedRuntime,preflight_load,validate_steps
from .visual_checks import _frame,_crop,_region,_png
from .workbench_evidence import store_evidence,load_evidence
from . import workbench_projects as projects

DEFAULT={'name':'Opening check','automatic':True,'mode':'review_changes','steps':[{'frames':600,'buttons':[],'port':0},{'frames':420,'buttons':[],'port':0}],'region':None,'route_ids':[]}


def validate_config(value):
    value=json.loads(canonical_bytes(value,max_bytes=16*1024));fields(value,'name automatic mode steps region route_ids');label(value['name'],80)
    if type(value['automatic']) is not bool or value['mode'] not in ('review_changes','unchanged'):raise ValueError('Choose automatic checks and a supported comparison mode.')
    validate_steps(value['steps'])
    if len(value['steps'])>20 or sum(r['frames'] for r in value['steps'])>2400:raise ValueError('Build checks allow up to 20 input steps / 2400 frames.')
    region=value['region']
    if region is not None:
        fields(region,'x y width height')
        for k in region:number(region[k],0 if k in ('x','y') else 1,2048)
    ids=value['route_ids']
    if type(ids) is not list or len(ids)>8 or len(set(ids))!=len(ids):raise ValueError('Select up to eight distinct saved assertion routes.')
    for ident in ids:projects.identifier(ident)
    return value


def compare_frames(first,repeated,candidate,region,mode):
    if mode not in ('review_changes','unchanged'):raise ValueError('Choose an available comparison mode.')
    w,h,a=_frame(first);ww,hh,repeat=_frame(repeated);cw,ch,b=_frame(candidate)
    if (w,h)!=(ww,hh) or a!=repeat:return {'status':'INCONCLUSIVE','reason':'The original did not reproduce its frame in two fresh runs.'}
    if (w,h)!=(cw,ch):return {'status':'INCONCLUSIVE','reason':'Frame dimensions changed; the pictures cannot be compared safely.'}
    if len({a[i:i+3] for i in range(0,len(a),3)})<2:return {'status':'INCONCLUSIVE','reason':'The original produced a flat frame. Choose a later frame or record an input route.'}
    chosen=region or {'x':0,'y':0,'width':w,'height':h}
    if region is not None:_region(region,w,h)
    x=_crop(a,w,chosen);y=_crop(b,w,chosen);changed=sum(x[i:i+3]!=y[i:i+3] for i in range(0,len(x),3))
    difference=bytes(abs(av-bv) for av,bv in zip(x,y));status='PASS' if not changed else 'REGRESSION' if mode=='unchanged' else 'REVIEW'
    return {'status':status,'changed_pixels':changed,'total_pixels':len(x)//3,'region':chosen,'comparison':'exact_rgb24','visual':{
        'original_png_base64':_png(x,chosen['width'],chosen['height']),'build_png_base64':_png(y,chosen['width'],chosen['height']),
        'difference_png_base64':_png(difference,chosen['width'],chosen['height'])},'reason':'Selected pixels are unchanged.' if not changed else 'Pixels changed. Review whether this was intended.'}


def run_sample(project,row,configuration,steps,cancelled,*,state_check=True):
    projects._measure(row['path'],row,cancelled=cancelled)
    core=projects._measure(configuration['core'],cancelled=cancelled)
    if core['sha256']!=configuration['expected_core_sha256']:raise ValueError('Configured engine revision changed before the test.')
    load=preflight_load({**configuration,'game':row['path'],'expected_game_sha256':row['sha256'],'session_dir':str(project/'sessions'/('test-'+uuid.uuid4().hex))},project)
    with OwnedRuntime(load,30,cancelled=cancelled) as runtime:
        expected=0
        for step in steps:
            if cancelled():raise KeyboardInterrupt
            r=runtime.request('advance',**step);expected+=step['frames']
            if r.get('frame_index')!=expected or r.get('game_sha256')!=row['sha256'] or r.get('core_sha256')!=configuration['expected_core_sha256']:raise ValueError('Test frame cadence or worker identity differs.')
        frame=runtime.request('capture');_frame(frame)
        if state_check:
            snapshot=runtime.request('save_state');runtime.request('advance',frames=1,buttons=[],port=0);next_frame=runtime.request('capture')
            runtime.request('load_state',snapshot=snapshot);runtime.request('advance',frames=1,buttons=[],port=0);replayed=runtime.request('capture')
            _frame(next_frame);_frame(replayed)
            if next_frame['sha256']!=replayed['sha256']:raise ValueError('Save-state replay did not reproduce the next frame.')
        runtime.close_verified();exit_code=runtime.exit_code
        identity={'core_sha256':configuration['expected_core_sha256'],'options':runtime.load_result.get('loaded',{}).get('core_options',{}),'controller_devices':configuration.get('controller_devices',{}),'system_files':configuration.get('system_files',[])}
    projects._measure(row['path'],row,cancelled=cancelled)
    projects._measure(configuration['core'],core,cancelled=cancelled)
    return {'frame':frame,'state_replay':bool(state_check),'worker_exit_code':exit_code,'execution_sha256':digest(identity)}


class BuildCheckTools:
    def __init__(self,api):self.api=api
    def routes(self):return {'checks.from_trace':('project_id source_id target_id trace_id',self.from_trace),'checks.configure':('project_id artifact_id config',self.configure),'checks.status':('project_id artifact_id',self.status),'checks.run':('project_id source_id target_id',self.run),'checks.get':('project_id artifact_id evidence_id',self.get)}
    def configure(self,p,c):
        project,row,path=self.api.source(p);from .release_scope import require_supported
        require_supported(row);config=validate_config(p['config'])
        from .route_editor import get_definition
        for ident in config['route_ids']:
            definition=get_definition(project,ident)
            if definition['system_id']!=row['system_id'] or not definition['complete'] or definition['initial_state_id'] is not None:raise ValueError('Choose completed cold-start assertion routes for this system.')
        with projects.locked(project) as store:
            if c():raise KeyboardInterrupt
            projects._measure(path,row);owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);owned['build_check_config']={'source_sha256':row['sha256'],'config':config};projects.write_json(project/'project.json',store)
        return {'ok':True,'config':config,'source_sha256':row['sha256']}
    def policy(self,project,row):
        seen=set()
        for _ in range(32):
            if row['artifact_id'] in seen:break
            seen.add(row['artifact_id']);stored=row.get('build_check_config')
            if stored:
                fields(stored,'source_sha256 config')
                if stored.get('source_sha256')!=row['sha256']:raise ValueError('Build check setup belongs to another revision.')
                return row,validate_config(stored['config'])
            if not row.get('source_id'):break
            row=projects.artifact(project,row['source_id'])
        return None,None
    def on_build(self,p,result):
        if result.get('ok') is not True or result.get('status')!='BUILT':return
        project=self.api.project(p);target=projects.artifact(project,result['artifact_id']);source,config=self.policy(project,target)
        from .release_scope import SYSTEMS
        if target.get('system_id') not in SYSTEMS:return
        if source is None or not config['automatic']:return
        try:
            job=self.api.jobs.submit('checks.run',{'project_id':p['project_id'],'source_id':source['artifact_id'],'target_id':target['artifact_id']})
            packet={'status':'QUEUED','job_id':job['job_id'],'source_id':source['artifact_id'],'target_id':target['artifact_id']}
        except (ValueError,OSError,RuntimeError) as error:packet={'status':'NOT_QUEUED','reason':str(error)[:240]}
        result['automatic_check']=packet
        try:
            with projects.locked(project) as store:
                owned=next(r for r in store['builds'] if r['artifact_id']==target['artifact_id']);owned['automatic_check']=packet;projects.write_json(project/'project.json',store)
        except (ValueError,OSError,RuntimeError) as error:packet['persistence_warning']='Build is saved; automatic-check status could not be stored: '+str(error)[:160]
    def status(self,p,c):
        project,row,_=self.api.source(p);source,config=self.policy(project,row);pending=row.get('automatic_check');progress=None
        if pending is not None and type(pending) is not dict:raise ValueError('Saved automatic-check status is malformed. Run a fresh check.')
        results=row.get('build_check_results',[])
        if type(results) is not list or len(results)>32:raise ValueError('Saved test history exceeds its budget.')
        for r in results:
            fields(r,'evidence_id status target_id target_sha256');projects.identifier(r['evidence_id']);projects.identifier(r['target_id']);projects.identifier(r['target_sha256']);label(r['status'],32)
        if pending and pending.get('job_id'):
            job=self.api.jobs.get(pending['job_id']);progress={k:job[k] for k in ('job_id','status','message')}
            if job.get('result'):progress['outcome']={k:v for k,v in job['result'].items() if k in ('status','error','evidence_id','reason')}
        pending=[]
        for build in projects.read_project(project)['builds'][-32:]:
            packet=build.get('automatic_check',{})
            if type(packet) is not dict:raise ValueError('Saved automatic-check status is malformed. Run a fresh check.')
            if packet.get('job_id') and (build['artifact_id']==row['artifact_id'] or packet.get('source_id')==row['artifact_id']):
                job=self.api.jobs.get(packet['job_id']);pending.append({'job_id':job['job_id'],'status':job['status'],'target_id':build['artifact_id'],'message':job['message'],'outcome':{k:v for k,v in (job.get('result') or {}).items() if k in ('status','reason','evidence_id','error')}})
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'configured':source is not None,'baseline_id':source['artifact_id'] if source else row['artifact_id'],'config':config or DEFAULT,'automatic':progress,'pending':pending[-8:],'results':results[-16:]}
    def get(self,p,c):
        project,row,_=self.api.source(p);record=load_evidence(project,p['evidence_id'],'regression');r=record['report']
        if r.get('scope')!='automatic_build_check_v1' or row['sha256'] not in (r.get('source_sha256'),r.get('target_sha256')):raise ValueError('Choose a check for this source or build.')
        return {'ok':True,**r,'evidence_id':p['evidence_id'],'runtime_trusted':record['runtime_trusted']}
    def from_trace(self,p,c):
        from .replay_journal import execution_context
        project=self.api.project(p);source=projects.artifact(project,p['source_id']);target=projects.artifact(project,p['target_id'])
        if target.get('kind')!='build' or target['artifact_id']==source['artifact_id']:raise ValueError('Create a separate edited build before testing this edit.')
        node=target;seen=set()
        for _ in range(128):
            if node['artifact_id']==source['artifact_id']:break
            if node['artifact_id'] in seen or not node.get('source_id'):raise ValueError('Choose a build descended from the captured source.')
            seen.add(node['artifact_id']);node=projects.artifact(project,node['source_id'])
        else:raise ValueError('Build ancestry exceeds the replay-check budget.')
        trace=self.api.traces.get({'project_id':p['project_id'],'artifact_id':source['artifact_id'],'trace_id':p['trace_id']},c)
        replay=trace.get('replay',{})
        if not trace['runtime_trusted'] or replay.get('status')!='READY':raise ValueError('Capture a fresh authenticated cold-start trace before testing an edit.')
        config=validate_config({'name':'Captured edit check','automatic':False,'mode':'review_changes','steps':replay['steps'],'region':trace['region'],'route_ids':[]})
        if sum(s['frames'] for s in config['steps'])!=replay['frames']:raise ValueError('Recorded replay frame count differs.')
        current=self.api._profile_load_config(source['system_id'])
        if execution_context(current)!=replay['context']:raise ValueError('The captured execution setup or core context changed. Capture a fresh trace.')
        return self._run(p,c,config,trace)

    def run(self,p,c):return self._run(p,c)

    def _run(self,p,c,config=None,trace=None):
        project=self.api.project(p);source=projects.artifact(project,p['source_id']);target=projects.artifact(project,p['target_id']);from .release_scope import require_supported
        require_supported(source);require_supported(target)
        if source['system_id']!=target['system_id']:raise ValueError('Build tests require the same cartridge system.')
        if config is None:
            _,config=self.policy(project,source)
        config=config or validate_config(DEFAULT)
        result={'ok':True,'scope':'automatic_build_check_v1','project_id':p['project_id'],'source_id':source['artifact_id'],'target_id':target['artifact_id'],'source_sha256':source['sha256'],'target_sha256':target['sha256'],'system_id':source['system_id'],'name':config['name'],'configuration':config,'configuration_sha256':digest(config),'status':'BLOCKED','gameplay_verified':False}
        if trace is not None:result.update(trace_id=p['trace_id'],captured_frame_sha256=trace['frame']['sha256'])
        try:
            checked=self.api._profile_load_config(source['system_id'])
            if trace is not None:
                from .replay_journal import execution_context
                if execution_context(checked)!=trace['replay']['context']:raise ValueError('Captured execution context changed before replay.')
            runs=[run_sample(project,row,checked,config['steps'],c) for row in (source,source,target)]
            if len({r['execution_sha256'] for r in runs})!=1:raise ValueError('Core options or controller/system context changed between test runs.')
            result.update(compare_frames(*(r['frame'] for r in runs),config['region'],config['mode']))
            if trace is not None and any(r['frame']['sha256']!=trace['frame']['sha256'] or r['frame']['index']!=trace['replay']['frames'] for r in runs[:2]):
                result.update(status='INCONCLUSIVE',reason='The original did not reproduce the captured trace frame. Record a fresh cold-start trace.')

            result['runs']=[{k:v for k,v in r.items() if k!='frame'}|{'frame':{k:r['frame'][k] for k in ('index','width','height','sha256')}} for r in runs]
            from .rom_health import check_rom
            health=[check_rom(Path(row['path']),row['sha256'],'','file',cancelled=c) for row in (source,target)]
            result['integrity']=[{'source_sha256':row['sha256'],'status':report['status'],'failures':[r['name'] if 'name' in r else r.get('id','Check') for r in report['checks'] if r['status']=='FAIL']} for row,report in zip((source,target),health)]
            if health[0]['status']=='ISSUES_FOUND':result.update(status='INCONCLUSIVE',reason='Original cartridge integrity checks report issues. Inspect the original before treating this as a regression baseline.')
            elif health[1]['status']=='ISSUES_FOUND':result.update(status='REGRESSION',reason='Build cartridge integrity checks report failures.')
            if config['route_ids']:
                suite=self.api._regression_suite({**p,'definition_ids':config['route_ids'],'timeout':30},c);result['suite']={k:v for k,v in suite.items() if k not in ('tests',)};result['suite_tests']=suite['tests']
                if suite['status']!='PASS' and result['status']!='REGRESSION':result.update(status=suite['status'],reason='Saved assertion routes need attention; inspect their measured results.')
        except (ValueError,OSError,RuntimeError) as error:result.update(status='BLOCKED',reason=str(error)[:1024])
        if c():raise KeyboardInterrupt
        with self.api.operation_locks_guard:lock=self.api.operation_locks.setdefault(p['project_id'],threading.RLock())
        with lock:
            self.api.project(p);projects._measure(source['path'],source,cancelled=c);projects._measure(target['path'],target,cancelled=c)
            evidence=store_evidence(project,'regression',result);result['evidence_id']=evidence['evidence_id']
            with projects.locked(project) as store:
                for row in store['sources']+store['builds']:
                    if row['artifact_id'] in (source['artifact_id'],target['artifact_id']):row['build_check_results']=(row.get('build_check_results',[])+[{'evidence_id':evidence['evidence_id'],'status':result['status'],'target_id':target['artifact_id'],'target_sha256':target['sha256']}])[-32:]
                projects.write_json(project/'project.json',store)
        return result

