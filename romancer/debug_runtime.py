"""Owned two-phase native observations; byte relations do not prove causation."""
import base64
import hashlib
from pathlib import Path
from .asset_schema import fields,number
from .assets import checked_path,failure,_bounded
from .debug import _debug_inputs
from .runtime_session import OwnedRuntime,preflight_load,snapshot_json,validate_steps,validate_timeout
from .script_schema import load_script_json


def _observation(result,target):
    if (result.get('scope')!='native_memory_observation' or result.get('memory_read_version')!=1
            or any(result.get(key)!=target[key] for key in ('region','offset','length'))
            or result.get('memory_written') is not False or result.get('write_event_observed') is not False):
        raise ValueError('invalid native observation scope or target')
    raw=bytes.fromhex(result['raw_hex'])
    if len(raw)!=target['length'] or hashlib.sha256(raw).hexdigest()!=result['data_sha256']:
        raise ValueError('native observation byte identity mismatch')
    return result


def observe_debug_case(project:Path,source:Path,case:dict,trace:dict,runtime:dict,base:Path,*,cancelled=None)->dict:
    result={'operation':'debug-observe','ok':False,'status':'BLOCKED','memory':[],'acknowledged_steps':[]}
    try:
        runtime=snapshot_json(runtime);fields(runtime,'load steps initial_state_file timeout frame_region memory_probe_ids')
        steps=validate_steps(runtime['steps']);timeout=validate_timeout(runtime['timeout'])
        region=runtime['frame_region']
        if type(region) is not list or len(region)!=4:raise ValueError('frame region must be x y width height')
        for index,value in enumerate(region):number(value,0 if index<2 else 1,4096)
        if region[2]*region[3]*3>65536:raise ValueError('frame region byte budget exceeded')
        with _debug_inputs(project,source,case,trace) as inputs:
            selected=runtime['memory_probe_ids']
            if type(selected) is not list or not 1<=len(selected)<=32 or len(set(selected))!=len(selected):raise ValueError('invalid selected memory probes')
            by_id={p['probe_id']:p for p in inputs.report['probes']};probes=[]
            for identifier in selected:
                if identifier not in by_id or by_id[identifier]['memory'] is None:raise ValueError('required memory probe is unresolved')
                probes.append(by_id[identifier])
            if 2*sum(p['length'] for p in probes)>65536:raise ValueError('two-phase memory budget exceeded')
            load=preflight_load(runtime['load'],base,allow_game_save=True)
            if load['expected_game_sha256']!=inputs.build['identity']['output']['sha256']:raise ValueError('runtime game differs from selected build output')
            snapshot=None
            if runtime['initial_state_file'] is not None:
                path=Path(runtime['initial_state_file']);path=checked_path(path if path.is_absolute() else Path(base)/path)
                snapshot=load_script_json(path,max_bytes=12*1024*1024)
            result.update(inputs.report,operation='debug-observe',status='BLOCKED',ok=False,memory=[],acknowledged_steps=[],
                          session_path=load['session_dir'],session_files_written=True,source_store_written=False)
            with OwnedRuntime(load,timeout,cancelled=cancelled) as session:
                hello=session.request('hello')
                if hello.get('memory_read',{}).get('version')!=1:raise ValueError('worker does not support bounded native reads')
                if snapshot is not None:session.request('load_state',snapshot=snapshot)
                before=[_observation(session.request('read_memory',**p['memory']),p['memory']) for p in probes]
                previous=before[-1]['frame_index']
                for step in steps:
                    advance=session.request('advance',**step)
                    if advance['frame_index']-previous!=step['frames'] or advance.get('frame') is None:
                        raise ValueError('worker frame cadence does not match requested input step')
                    previous=advance['frame_index'];result['acknowledged_steps'].append({'request':step,'frame_index':previous})
                after=[_observation(session.request('read_memory',**p['memory']),p['memory']) for p in probes]
                for probe,old,new in zip(probes,before,after):
                    if any(old[key]!=new[key] for key in ('worker_session_id','epoch','region','region_size','offset','length','core_options')) or new['sequence']<=old['sequence']:
                        raise ValueError('memory observation context changed')
                    result['memory'].append({'probe_id':probe['probe_id'],'before':old,'after':new,'relation':'EQUAL' if old['raw_hex']==new['raw_hex'] else 'DIFFERENT'})
                frame=session.request('capture');width=number(frame['width'],1,4096);height=number(frame['height'],1,4096)
                encoded=frame['rgb24_base64']
                if type(encoded) is not str or width*height*3>8*1024*1024 or len(encoded)>((width*height*3+2)//3)*4:raise ValueError('frame payload budget exceeded')
                rgb=base64.b64decode(encoded,validate=True)
                if len(rgb)!=width*height*3 or hashlib.sha256(rgb).hexdigest()!=frame['sha256'] or frame['index']!=previous:raise ValueError('current frame identity mismatch')
                x,y,w,h=region
                if x+w>width or y+h>height:raise ValueError('frame region is outside current capture')
                roi=b''.join(rgb[((y+row)*width+x)*3:((y+row)*width+x+w)*3] for row in range(h))
                result['frame']={k:v for k,v in frame.items() if k!='rgb24_base64'}
                result['frame'].update(region=region,roi_rgb_hex=roi.hex(),roi_sha256=hashlib.sha256(roi).hexdigest())
                session.close_verified();inputs.recheck()
                result.update(ok=True,status='OBSERVED',worker_close_acknowledged=True,worker_exit_code=session.exit_code,
                              mutation_evidence='NOT_RUN',causation='NOT_RUN',atomic_snapshot_verified=False)
                _bounded(result);session.remaining()
        return result
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,KeyboardInterrupt) as exc:
        return {**failure('debug-observe',exc),**{k:v for k,v in result.items() if k not in ('ok','status')},'ok':False,'status':'CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED'}
