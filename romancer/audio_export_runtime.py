"""Own a cold-boot emulator/audio window, prove closure, then export."""
import base64
import hashlib
from pathlib import Path
from .asset_schema import fields,number
from .assets import digest,failure
from .audio_export import MAX_PCM,check_pcm,publish_pcm,validate_baseline
from .cd_patch import check_output_paths
from .runtime_session import OwnedRuntime,preflight_load,snapshot_json,validate_steps,validate_timeout


def _drain(result,rate=None,*,allow_empty=False):
    value=result.get('sample_rate')
    if type(value) not in (int,float) or int(value)!=value:raise ValueError('nonintegral sample rate is unsupported')
    value=number(int(value),1,192000)
    if rate is not None and value!=rate:raise ValueError('audio sample rate changed')
    encoded=result.get('pcm_s16le_base64')
    if type(encoded) is not str or len(encoded)>((MAX_PCM+2)//3)*4:raise ValueError('audio payload budget exceeded')
    raw=base64.b64decode(encoded,validate=True)
    if len(raw)>MAX_PCM or len(raw)%4 or (not raw and not allow_empty):raise ValueError('invalid captured PCM length')
    if (result.get('format')!='s16le' or result.get('channels')!=2
            or result.get('captured_frames')!=len(raw)//4 or result.get('observed') is not bool(raw)
            or result.get('complete') is not True or result.get('dropped_frames')!=0 or result.get('invalid_batches')!=0):
        raise ValueError('audio capture incomplete or inconsistent')
    if result.get('run_mode')!='cold_boot' or result.get('provenance',{}).get('state_derived') is not False:
        raise ValueError('runtime audio requires a fresh cold boot')
    return raw,value


def capture_audio(config: dict,baseline: dict,destination: Path,*,base: Path,
                  output_format: str,protected_inputs: tuple[Path,...]=(),cancelled=None) -> dict:
    result={'written':False,'publication_status':'NOT_PUBLISHED'}
    try:
        config=snapshot_json(config);fields(config,'schema_version load steps timeout_seconds');number(config['schema_version'],1,1)
        steps=validate_steps(config['steps']);timeout=validate_timeout(config['timeout_seconds']);baseline=validate_baseline(baseline)
        load=preflight_load(config['load'],base)
        for path in (load['core'],load['game'],load.get('system_dir'),*[e['source'] for e in load.get('game_dependencies',[])],*protected_inputs):
            if path is not None:check_output_paths(Path(path),[Path(destination)])
        session=Path(load['session_dir']);output=Path(destination).absolute()
        if output==session or session in output.parents:raise ValueError('audio output cannot be inside runtime session')
        result.update(capture_origin='runtime_worker',runtime_config_sha256=digest(config),session_path=str(session),drains=[])
        with OwnedRuntime(load,timeout,cancelled=cancelled) as runtime:
            startup=runtime.request('audio');_,rate=_drain(startup,allow_empty=True)
            result['startup_audio']={k:v for k,v in startup.items() if k!='pcm_s16le_base64'}
            chunks=[];total=0
            for step in steps:
                advance=runtime.request('advance',**step);drain=runtime.request('audio')
                raw,_=_drain(drain,rate,allow_empty=True);total+=len(raw)
                if total>MAX_PCM:raise ValueError('aggregate PCM budget exceeded')
                chunks.append(raw);result['drains'].append({'frame_index':advance['frame_index'],'sample_frames':len(raw)//4,'pcm_sha256':hashlib.sha256(raw).hexdigest()})
            raw=b''.join(chunks);result.update(check_pcm(raw,rate,baseline),operation='audio-capture',core_sha256=load['expected_core_sha256'],game_sha256=load['expected_game_sha256'])
            runtime.close_verified();result.update(worker_close_acknowledged=True,worker_exit_code=runtime.exit_code)
            if result['ok']:
                result.update(publish_pcm(raw,destination,rate,output_format,protected_inputs,runtime.remaining))
        return result
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,KeyboardInterrupt) as exc:
        return {**failure('audio-capture',exc),**{k:v for k,v in result.items() if k not in ('ok','status')},'ok':False}
