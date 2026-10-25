"""Progress graph from stored route assertions, with unknown/optional scope explicit."""
from .asset_schema import fields,label
from .runtime_session import snapshot_json
from .workbench_evidence import load_evidence


def build_coverage(project,route_reports:list[dict],objectives:dict)->dict:
    objectives=snapshot_json(objectives);fields(objectives,'required optional endings unknown_edges')
    all_goals=set()
    for kind,values in objectives.items():
        if type(values) is not list or len(values)>512:raise ValueError('invalid coverage objective list')
        for value in values:label(value)
        if len(set(values))!=len(values):raise ValueError('duplicate coverage objective')
        if kind!='unknown_edges':
            if all_goals.intersection(values):raise ValueError('objective appears in multiple categories')
            all_goals.update(values)
    if type(route_reports) is not list or len(route_reports)>256:raise ValueError('too many route reports')
    covered=set();edges=[];untrusted=0;used=[]
    for item in route_reports:
        try:
            evidence_id=item if type(item) is str else item['evidence_id']
            record=load_evidence(project,evidence_id,'route');report=record['report']
            if (not record.get('runtime_trusted',False) or report.get('origin')!='owned_native_worker' or report.get('status')!='PASS'
                    or report.get('worker_close_acknowledged') is not True or report.get('worker_exit_code')!=0):
                raise ValueError('route did not finish successfully')
            used.append(evidence_id)
            for edge in report.get('transitions',[]):
                if edge.get('evidence')!='measured_assertions' or edge.get('interpretation')!='profile_declared':continue
                covered.add(edge['objective']);edges.append({**edge,'evidence_id':evidence_id})
        except (KeyError,TypeError,ValueError,OSError):untrusted+=1
    result={'schema_version':1,'operation':'coverage','scope':'executed_route_assertion_coverage','ok':True,
            'status':'PARTIAL','covered':sorted(covered),'edges':edges,'untrusted_reports':untrusted,
            'evidence_ids':used,'unknown_edges':objectives['unknown_edges'],
            'natural_progression_verified':False,'currentness':'NOT_CHECKED',
            'note':'Node names and transition meanings are profile declarations. Evidence proves the recorded assertions, not full game completion.'}
    for kind in ('required','optional','endings'):
        result[kind]={'covered':sorted(set(objectives[kind])&covered),'missing':sorted(set(objectives[kind])-covered)}
    if not result['required']['missing'] and not result['endings']['missing'] and not objectives['unknown_edges']:
        result['status']='SCOPE_COVERED'
    return result
