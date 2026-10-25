"""Sequential worker execution. Reports carry measurements, never supplied passes."""
import base64
import hashlib
import uuid
from .asset_schema import fields
from .assets import failure
from .debug_runtime import _observation
from .replay_schema import validate_route
from .runtime_session import OwnedRuntime,preflight_load,validate_timeout
from .script_schema import canonical_bytes


def execute_route(client,route:dict,context:dict,cancelled)->dict:
    route=validate_route(route)
    fields(context,'core_sha256 game_sha256')
    report={'schema_version':1,'operation':'route-execute','scope':'measured_route_assertions','run_id':uuid.uuid4().hex,
            'route_id':route['id'],'route_sha256':hashlib.sha256(canonical_bytes(route,max_bytes=1024**2)).hexdigest(),
            'origin':'worker_requests','context':context,'ok':False,'status':'RUNNING',
            'observations':[],'transitions':[],'checkpoints':[],'acknowledged_frames':0,'natural_progression_verified':False}
    def request(operation,**kwargs):
        if cancelled():raise KeyboardInterrupt
        result=client.request(operation,**kwargs)
        if result.get('ok') is not True:raise ValueError('worker refused route operation: '+str(result.get('error','unknown'))[:512])
        if operation!='hello' and any(result.get(k)!=v for k,v in context.items()):raise ValueError('route worker binding mismatch')
        return result
    try:
        checkpoint_bytes=0;previous=None
        for index,step in enumerate(route['steps']):
            remaining=step['frames']
            while remaining:
                count=min(30,remaining);advanced=request('advance',frames=count,buttons=step['buttons'],port=step['port'])
                frame_index=advanced['frame_index']
                if previous is not None and frame_index-previous!=count:raise ValueError('worker frame cadence differs from route')
                previous=frame_index;remaining-=count;report['acknowledged_frames']+=count
            for assertion in step['assertions']:
                if assertion['kind']=='memory_eq':
                    target={'region':assertion['region'],'offset':assertion['offset'],'length':len(assertion['expected_hex'])//2}
                    measured=_observation(request('read_memory',**target),target)
                    observation={'kind':'memory_eq','step':index,'actual_hex':measured['raw_hex'],
                        'expected_hex':assertion['expected_hex'],'measurement':measured,'pass':measured['raw_hex']==assertion['expected_hex']}
                elif assertion['kind']=='frame_region':
                    from .visual_checks import compare_frame
                    observation={**compare_frame(request('capture'),assertion),'step':index}
                else:
                    measured=request('capture');rgb=base64.b64decode(measured['rgb24_base64'],validate=True)
                    if len(rgb)>8*1024**2 or hashlib.sha256(rgb).hexdigest()!=measured['sha256']:raise ValueError('capture payload mismatch')
                    observation={'kind':'capture_sha256','step':index,'actual_sha256':measured['sha256'],
                        'expected_sha256':assertion['sha256'],'pass':measured['sha256']==assertion['sha256'],'frame_index':measured['index']}
                report['observations'].append(observation)
                if not observation['pass']:
                    report.update(status='FAIL',stopped_at_step=index);return report
            if step['transition'] is not None:
                report['transitions'].append({**step['transition'],'step':index,'evidence':'measured_assertions',
                    'interpretation':'profile_declared','frame_index':previous})
            if step['checkpoint']:
                snapshot=request('save_state');checkpoint_bytes+=len(snapshot['state_base64'])
                if checkpoint_bytes>4*1024**2:raise ValueError('route checkpoint budget exceeded')
                report['checkpoints'].append({'step':index,'snapshot':snapshot})
        report.update(ok=True,status='PASS');return report
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,KeyboardInterrupt) as exc:
        report.update(ok=False,status='CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED',error=str(exc)[:1024]);return report


def run_route(project,route,load,base,*,timeout=30,cancelled=lambda:False,initial_state=None):
    """Only this owned lifecycle may mint stored route evidence."""
    from .workbench_projects import _measure
    from .workbench_evidence import store_evidence
    from . import ROMANCER_VERSION
    validate_route(route);validate_timeout(timeout);load=preflight_load(load,base,allow_game_save=True)
    game=_measure(load['game']);core=_measure(load['core'])
    with OwnedRuntime(load,timeout,cancelled=cancelled) as runtime:
        if initial_state is not None:runtime.request('load_state',snapshot=initial_state)
        report=execute_route(runtime,route,{'core_sha256':load['expected_core_sha256'],'game_sha256':load['expected_game_sha256']},cancelled)
        runtime.close_verified();_measure(load['game'],game);_measure(load['core'],core)
        report.update(origin='owned_native_worker',worker_close_acknowledged=True,worker_exit_code=runtime.exit_code,
                      initial_state_derived=initial_state is not None)
        report['execution_identity']={'schema_version':2,'tool_version':ROMANCER_VERSION,
            'core_options':load.get('core_options',{}),
            'effective_core_options':runtime.load_result.get('loaded',{}).get('core_options',{}),
            'system_files':sorted([{'relative':d['relative'],'expected_sha256':d['expected_sha256']} for d in load['system_files']],key=lambda d:d['relative']) if 'system_files' in load else None,
            'game_dependencies':sorted([{'relative':d['relative'],'expected_sha256':d['expected_sha256']} for d in load.get('game_dependencies',[])],key=lambda d:d['relative']),
            'initial_state_sha256':initial_state['sha256'] if initial_state is not None else None,
            'game_save_sha256':load['game_save']['sha256'] if load.get('game_save') is not None else None,
            'system_directory_used':load.get('system_dir') is not None}
        # Snapshots stay in the caller result; evidence stores their hashes, not opaque payloads.
        stored={**report,'checkpoints':[{'step':c['step'],'sha256':c['snapshot']['sha256']} for c in report['checkpoints']]}
        evidence=store_evidence(project,'route',stored);report['evidence_id']=evidence['evidence_id'];return report
