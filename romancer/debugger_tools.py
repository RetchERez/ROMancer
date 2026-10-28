"""Owned native instrumentation endpoints and bounded evidence summaries."""
import threading
from .asset_schema import number
from .release_scope import require_supported
from .workbench_evidence import store_evidence,load_evidence


def summarize_events(events):
    counts={'read':0,'write':0,'exec':0};contexts={};reads={}
    for event in events:
        kind=event['kind'];counts[kind]+=1
        context=event.get('execution_context',{})
        if kind=='write' and context.get('pc') is not None:
            key=(context['pc'],context.get('file_offset'),context.get('domain'),context.get('physical_offset'))
            row=contexts.setdefault(key,{'pc':key[0],'file_offset':key[1],'domain':key[2],
                'physical_offset':key[3],'sampled_write_events':0,'addresses':set()})
            row['sampled_write_events']+=1;row['addresses'].add(event['address'])
        if kind=='read' and event.get('file_offset') is not None:
            row=reads.setdefault(event['file_offset'],{'file_offset':event['file_offset'],'sampled_read_events':0})
            row['sampled_read_events']+=1
    return {'event_counts':counts,
        'execution_contexts':[{**row,'addresses':sorted(row['addresses'])[:32]} for row in list(contexts.values())[:128]],
        'source_reads':list(reads.values())[:128],'summary_truncated':len(contexts)>128 or len(reads)>128,
        'causation_proven':False,
        'interpretation':'These are sampled native access events and their observed execution context. Context is a lead for investigation; DMA ownership and higher-level meaning are not established.'}


class DebuggerTools:
    capacity=threading.BoundedSemaphore(2)
    def __init__(self,api):self.api=api

    def routes(self):
        return {'debugger.capabilities':('project_id artifact_id',self.capabilities),
            'debugger.prepare':('project_id artifact_id',self.prepare),
            'debugger.capture':('project_id artifact_id config',self.capture),
            'debugger.investigate':('project_id artifact_id investigation_id candidate_id replay',self.investigate),
            'debugger.follow':('project_id artifact_id evidence_id',self.follow),
            'debugger.get':('project_id artifact_id evidence_id offset limit',self.get)}

    def follow(self,p,c):
        from .investigation_follow import follow_capture
        from .research_tools import _resources
        from .workbench_projects import _measure
        project,row,path=self.api.source(p);record=load_evidence(project,p['evidence_id'],'runtime');report=record['report']
        if report.get('kind')!='native-debugger-capture-v1' or report.get('source_sha256')!=row['sha256'] or report.get('artifact_id')!=row['artifact_id']:
            raise ValueError('Choose an access capture for this exact selected source.')
        resources,issues,total=_resources(row,path,c)
        result=follow_capture(report,resources,row['size'],trusted=record['runtime_trusted'],cancelled=c)
        _measure(path,row,cancelled=c)
        return {**result,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],
            'evidence_id':p['evidence_id'],'resource_issues':issues,'resource_index_partial':total>len(resources)}

    def capabilities(self,p,c):
        from .native_debugger import backend_capabilities,verify_backend
        from .debugger_provision import preferred_root,download_info,verify_prepared
        _,row,_=self.api.source(p);result=backend_capabilities(row.get('system_id'))
        result.update(source_sha256=row['sha256'],artifact_id=row['artifact_id'],available=False)
        try:
            root=preferred_root(self.api.workspace,row.get('system_id'))
            backend=verify_prepared(root,row['system_id']) if root.resolve().is_relative_to((self.api.workspace/'debuggers').resolve()) else verify_backend(root,system=row.get('system_id'))
            result['backend_identity']=backend
            result['available']=result['supported_system'] and result['host_supported']
            if not result['available']:result['reason']='This pinned debugger build does not support the selected system or host.'
        except (ValueError,OSError) as error:result['reason']=str(error)
        if result['supported_system']:result['download']=download_info(row['system_id'])
        return result

    def prepare(self,p,c):
        from .debugger_provision import prepare_backend
        _,row,_=self.api.source(p);require_supported(row)
        result=prepare_backend(self.api.workspace,row['system_id'],cancelled=c)
        self.api.source(p)
        return {**result,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'available':True}

    def _response(self,record,offset,limit):
        number(offset,0,2000);number(limit,1,100);report=record['report'];events=report['events']
        samples=report.get('instruction_samples',[])
        if type(events) is not list or len(events)>2000 or type(samples) is not list or len(samples)>2000:raise ValueError('native event evidence exceeds its budget')
        return {**{k:v for k,v in report.items() if k not in ('events','kind','instruction_samples')},'ok':True,
            'evidence_id':record['evidence_id'],'runtime_trusted':record.get('runtime_trusted',True),
            'authentication':record.get('authentication','current_application'),
            'events':events[offset:offset+limit],'total_events':len(events),'offset':offset,'limit':limit,
            'instruction_samples':samples[offset:offset+limit],'total_instruction_samples':len(samples),
            'summary':summarize_events(events)}

    def capture(self,p,c):
        return self._capture(p,c,p['config'])

    def investigate(self,p,c):
        from .investigation_tools import InvestigationTools
        proposed=InvestigationTools(self.api).probe(p,c);replay=p['replay']
        if type(replay) is not dict or set(replay)-{'steps','start_frame','event_limit','instruction_limit','timeout'}:
            raise ValueError('Replay accepts bounded steps and budgets only; its probe is derived from the authenticated candidate.')
        link={key:proposed[key] for key in ('investigation_id','candidate','physical_probe','core_sha256','same_runtime_state_claimed','replay_scope')}
        link['candidate_id']=proposed['candidate']['candidate_id']
        return self._capture(p,c,{**replay,'probes':[proposed['physical_probe']]},link)

    def _capture(self,p,c,config,link=None):
        from .native_debugger import capture_native,validate_capture
        from .debugger_provision import preferred_root,verify_prepared,cleanup_pending_stages
        project,row,_=self.api.source(p);require_supported(row);validate_capture(row['system_id'],config)
        if not self.capacity.acquire(blocking=False):raise ValueError('two native investigations are running; wait for one to finish')
        try:
            if c():raise KeyboardInterrupt
            maintenance=cleanup_pending_stages(self.api.workspace)
            root=preferred_root(self.api.workspace,row['system_id'])
            if root.resolve().is_relative_to((self.api.workspace/'debuggers').resolve()):verify_prepared(root,row['system_id'])
            report=capture_native(project,row,config,root=root,cancelled=c)
            report={**report,'preparation_cleanup':maintenance}
            if report.get('source_sha256')!=row['sha256'] or report.get('artifact_id')!=row['artifact_id']:
                raise ValueError('native capture source identity differs')
            if c():raise KeyboardInterrupt
            if link is not None:report={**report,'investigation_link':link}
            record=store_evidence(project,'runtime',{'kind':'native-debugger-capture-v1',**report})
            return self._response(record,0,100)
        finally:self.capacity.release()

    def get(self,p,c):
        project,row,_=self.api.source(p);record=load_evidence(project,p['evidence_id'],'runtime');report=record['report']
        if (report.get('kind')!='native-debugger-capture-v1' or report.get('source_sha256')!=row['sha256']
                or report.get('artifact_id')!=row['artifact_id']):raise ValueError('native capture belongs to another selected source')
        return self._response(record,p['offset'],p['limit'])
