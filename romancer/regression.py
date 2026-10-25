"""Explicit report comparison and budgeted delta debugging with real evaluator calls."""
import hashlib
from .asset_schema import fields,number
from .runtime_session import snapshot_json
from .script_schema import canonical_bytes


def evidence_cache_key(inputs:dict)->str:
    fields(inputs,'source profile core settings route tool')
    return hashlib.sha256(canonical_bytes(inputs,max_bytes=1024**2)).hexdigest()


def compare_runs(baseline:dict,candidate:dict)->dict:
    baseline=snapshot_json(baseline);candidate=snapshot_json(candidate)
    result={'schema_version':1,'operation':'regression-compare','ok':True,'status':'INCONCLUSIVE',
            'scope':'report_comparison','baseline_status':baseline.get('status'),'candidate_status':candidate.get('status'),
            'runtime_evidence_authenticated':False,'differences':[]}
    if baseline.get('status') not in ('PASS','FAIL') or candidate.get('status') not in ('PASS','FAIL'):
        result['reason']='Both runs need completed assertions';return result
    for key in ('route_sha256',):
        if not baseline.get(key) or baseline.get(key)!=candidate.get(key):
            result['reason']='Runs use different or unknown route identities';return result
    bcontext=baseline.get('context',{});ccontext=candidate.get('context',{})
    if not bcontext.get('core_sha256') or bcontext.get('core_sha256')!=ccontext.get('core_sha256'):
        result['reason']='Core identities differ or are unknown';return result
    left_identity=baseline.get('execution_identity');right_identity=candidate.get('execution_identity')
    required={'schema_version','tool_version','core_options','game_dependencies','initial_state_sha256','game_save_sha256','system_directory_used'}
    if type(left_identity) is dict and left_identity.get('schema_version')==2:required|={'effective_core_options','system_files'}
    if (type(left_identity) is not dict or type(right_identity) is not dict
            or set(left_identity)!=required or set(right_identity)!=required or left_identity!=right_identity):
        result['reason']='Complete execution settings/checkpoint identities differ or are absent';return result
    if left_identity['system_directory_used'] is not False and (left_identity.get('schema_version')!=2 or type(left_identity.get('system_files')) is not list):
        result['reason']='External system-directory contents were not measured for comparison';return result
    b=baseline.get('observations',[]);c=candidate.get('observations',[])
    for index in range(max(len(b),len(c))):
        left=b[index] if index<len(b) else None;right=c[index] if index<len(c) else None
        keys=('kind','step','actual_hex','actual_sha256','pass')
        left={k:left[k] for k in keys if k in left} if left else None
        right={k:right[k] for k in keys if k in right} if right else None
        if left!=right:result['differences'].append({'index':index,'baseline':left,'candidate':right})
    result['status']='REGRESSION' if baseline['status']=='PASS' and candidate['status']=='FAIL' else ('CHANGED' if result['differences'] else 'UNCHANGED')
    return result


def bisect_changes(changes:list[dict],evaluate,budget:dict)->dict:
    changes=snapshot_json(changes);fields(budget,'max_evaluations');limit=number(budget['max_evaluations'],1,256)
    if type(changes) is not list or not 1<=len(changes)<=128:raise ValueError('bisection requires 1..128 changes')
    result={'schema_version':1,'operation':'change-bisection','ok':True,'status':'INCONCLUSIVE',
            'failing_subset':changes,'minimal_reproduced':False,'evaluations':[],
            'scope':'supplied_evaluator_results','native_execution_verified':False}
    def run(subset):
        if len(result['evaluations'])>=limit:raise StopIteration
        response=evaluate(snapshot_json(subset));status=response.get('status')
        if status not in ('PASS','FAIL'):raise ValueError('evaluator did not produce a conclusive result')
        result['evaluations'].append({'subset':subset,'status':status});return status
    try:
        if run([])!='PASS':result['reason']='Empty baseline already fails';return result
        if run(changes)!='FAIL':result['reason']='Full change set does not reproduce failure';return result
        current=changes[:];granularity=2
        while len(current)>=2:
            size=(len(current)+granularity-1)//granularity;reduced=False
            for start in range(0,len(current),size):
                complement=current[:start]+current[start+size:]
                if complement and run(complement)=='FAIL':
                    current=complement;granularity=max(2,granularity-1);reduced=True;break
            if not reduced:
                if granularity>=len(current):break
                granularity=min(len(current),granularity*2)
            result['failing_subset']=current
        # Fresh reproduction, then every single-removal check establishes 1-minimality.
        if run(current)!='FAIL':raise ValueError('failure was not reproducible')
        for index in range(len(current)):
            if run(current[:index]+current[index+1:])!='PASS':raise ValueError('subset is not reproducibly minimal')
        result.update(status='LOCALIZED',failing_subset=current,minimal_reproduced=True);return result
    except (StopIteration,ValueError) as exc:
        result['reason']='Evaluation budget exhausted' if isinstance(exc,StopIteration) else str(exc)
        return result
