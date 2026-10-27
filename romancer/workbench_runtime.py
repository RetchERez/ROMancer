"""Interactive owned native sessions, serialized per session and expired when idle."""
import base64
import hashlib
import copy
from pathlib import Path
import threading
import time
import uuid
from .asset_schema import number
from .assets import checked_path
from .runtime_session import OwnedRuntime,preflight_load,validate_steps
from .workbench_projects import artifact,_measure,write_json


class RuntimePool:
    def __init__(self):
        self.sessions={};self.lock=threading.RLock();self.stopping=threading.Event()
        self.reaper=threading.Thread(target=self._expire,daemon=True);self.reaper.start()

    def _expire(self):
        while not self.stopping.wait(10):
            with self.lock:
                for project,value in list(self.sessions.items()):
                    if time.monotonic()-value['touched']>300:
                        try:self.close_session(project)
                        except (ValueError,OSError,RuntimeError):pass

    def load(self,project,artifact_id,core,options,*,cancelled=None,configuration=None,selection=None):
        with self.lock:
            if len(self.sessions)>=4:raise ValueError('four native sessions are already active; close one first')
            if str(project) in self.sessions:raise ValueError('close the current playtest session first')
            row=selection if selection is not None else artifact(project,artifact_id);_measure(row['path'],row);core=checked_path(Path(core));core_id=_measure(core)
            if configuration and core_id['sha256']!=configuration['expected_core_sha256']:raise ValueError('configured core revision changed')
            load=preflight_load({**(configuration or {}),'game':row['path'],'core':str(core),'session_dir':str(Path(project)/'sessions'/uuid.uuid4().hex),
                'expected_game_sha256':row['sha256'],'expected_core_sha256':core_id['sha256'],'core_options':options},project,allow_game_save=True)
            runtime=OwnedRuntime(load,30,cancelled=cancelled);runtime.__enter__()
            from .replay_journal import ReplayJournal
            self.sessions[str(project)]={'runtime':runtime,'touched':time.monotonic(),'artifact_id':artifact_id,'load':load,'replay_journal':ReplayJournal(game_save=bool(load.get('game_save')))}
            try:hello=runtime.request('hello')
            except BaseException:self.close_session(project);raise
            runtime.client.cancelled=None
            return {'ok':True,'status':'LOADED','artifact_id':artifact_id,'game_sha256':row['sha256'],'core_sha256':core_id['sha256'],
                    'capabilities':hello,'loaded':runtime.load_result,'session_dir':load['session_dir'],'idle_timeout_seconds':300,'run_mode':runtime.load_result.get('run_mode','cold_boot')}

    def request(self,project,operation,parameters,*,cancelled=None):
        with self.lock:
            value=self.sessions.get(str(project))
            if value is None:raise ValueError('no active playtest; load a compatible native core and game first')
            runtime=value['runtime'];runtime.deadline=time.monotonic()+30;value['touched']=time.monotonic()
            runtime.client.cancelled=cancelled
            if operation=='load_state' and value.get('recording',{}).get('status')=='RECORDING':raise ValueError('stop recording before restoring a checkpoint')
            if operation=='advance':validate_steps([parameters])
            proposed=None
            if operation=='advance' and value.get('recording',{}).get('status')=='RECORDING':
                from .route_editor import append_input
                proposed=copy.deepcopy(value['recording']);append_input(proposed,parameters)
            try:
                result=runtime.request(operation,**parameters)
                if 'replay_journal' in value:value['replay_journal'].acknowledge(operation,parameters,result)
                if proposed is not None:
                    proposed['acknowledged_frames']=proposed.get('acknowledged_frames',0)+parameters['frames']
                    value['recording']=proposed;write_json(Path(project)/'routes'/(proposed['definition_id']+'.json'),proposed,max_bytes=2*1024**2)
                if operation=='capture':
                    rgb=base64.b64decode(result['rgb24_base64'],validate=True)
                    if len(rgb)!=result['width']*result['height']*3 or hashlib.sha256(rgb).hexdigest()!=result['sha256']:raise ValueError('capture identity mismatch')
                if operation=='audio':value['last_audio']=result
                return result
            except BaseException:
                try:self.close_session(project)
                except Exception:pass  # Preserve the primary refusal/cancellation after reaping.
                raise
            finally:runtime.client.cancelled=None

    def step(self,project,frames,buttons,port,*,cancelled=None):
        number(frames,1,12)
        validate_steps([{'frames':frames,'buttons':buttons,'port':port}])
        with self.lock:
            value=self.sessions.get(str(project))
            if value is None:raise ValueError('load a native playtest first')
            # A live packet contains this step's audio, not a paused/manual backlog.
            # Keep explicit runtime.audio available for capturing that backlog.
            self.request(project,'audio',{},cancelled=cancelled)
            advanced=self.request(project,'advance',{'frames':frames,'buttons':buttons,'port':port},cancelled=cancelled)
            frame=self.request(project,'capture',{},cancelled=cancelled)
            audio=self.request(project,'audio',{},cancelled=cancelled)
            return {'ok':True,'advanced':advanced,'frame':frame,'audio':audio,
                    'timing':copy.deepcopy(value['runtime'].load_result.get('av',{}).get('timing',{}))}

    def audio_snapshot(self,project):
        
        with self.lock:
            value=self.sessions.get(str(project))
            if value is None or 'last_audio' not in value:raise ValueError('drain captured audio first')
            result=value['last_audio'];raw=base64.b64decode(result['pcm_s16le_base64'],validate=True)
            if not raw or len(raw)>1024**2 or len(raw)%4 or result.get('format')!='s16le' or result.get('channels')!=2 or result.get('captured_frames')!=len(raw)//4 or result.get('complete') is not True:raise ValueError('audio capture is empty or incomplete')
            return raw,result

    def session_selection(self,project):
        with self.lock:
            value=self.sessions.get(str(project))
            if value is None:raise ValueError('load a native session first')
            return {'id':value['artifact_id'],'sha256':value['load']['expected_game_sha256']}

    def replay_snapshot(self,project,frame):
        from .replay_journal import execution_context
        with self.lock:
            value=self.sessions.get(str(project))
            if value is None:raise ValueError('The native session is no longer available. Capture a fresh trace after loading.')
            if frame.get('game_sha256')!=value['load']['expected_game_sha256'] or frame.get('core_sha256')!=value['load']['expected_core_sha256']:raise ValueError('Replay source or core differs from the captured frame.')
            packet=value['replay_journal'].snapshot(frame['index'])
            return {**packet,'context':execution_context(value['load'])}

    def begin_recording(self,project,record):
        with self.lock:
            value=self.sessions.get(str(project))
            if value is None:raise ValueError('load a native session first')
            if value.get('recording',{}).get('status')=='RECORDING':raise ValueError('stop the current recording first')
            if record['selection']['id']!=value['artifact_id'] or record['selection']['sha256']!=value['load']['expected_game_sha256']:raise ValueError('recording source differs from active session')
            root=Path(project)/'routes';root.mkdir(exist_ok=True);write_json(root/(record['definition_id']+'.json'),record,max_bytes=2*1024**2);value['recording']=record
            return {'ok':True,**copy.deepcopy(record)}

    def record_assertion(self,project,kind,parameters,*,cancelled=None):
        with self.lock:
            value=self.sessions.get(str(project));record=value.get('recording') if value else None
            if not record or record['status']!='RECORDING' or not record['route']['steps']:raise ValueError('record at least one input step first')
            proposed=copy.deepcopy(record);assertions=proposed['route']['steps'][-1]['assertions']
            if len(assertions)>=32:raise ValueError('assertion budget reached for this step')
            if kind=='capture':
                result=self.request(project,'capture',{},cancelled=cancelled);assertion={'kind':'capture_sha256','sha256':result['sha256']}
            elif kind=='memory':
                result=self.request(project,'read_memory',parameters,cancelled=cancelled);assertion={'kind':'memory_eq','region':parameters['region'],'offset':parameters['offset'],'expected_hex':result['raw_hex']}
            elif kind=='region':
                from .visual_checks import make_assertion
                result=self.request(project,'capture',{},cancelled=cancelled)
                if result['sha256']!=parameters['frame_sha256']:raise ValueError('The frame changed after region selection. Pause and capture it again.')
                assertion=make_assertion(result,parameters['region'])
            else:raise ValueError('unsupported recorded assertion')
            assertions.append(assertion)
            from .replay_schema import validate_route
            validate_route(proposed['route'])
            write_json(Path(project)/'routes'/(record['definition_id']+'.json'),proposed,max_bytes=2*1024**2);value['recording']=proposed
            return {'ok':True,'status':'ASSERTION_RECORDED','assertion':assertion,'definition_id':record['definition_id']}

    def stop_recording(self,project):
        from .route_editor import _complete
        with self.lock:
            value=self.sessions.get(str(project));record=value.get('recording') if value else None
            if not record or record['status']!='RECORDING':raise ValueError('no active input recording')
            complete=_complete(record['route']) if record['route']['steps'] else False
            record.update(complete=complete,status='DEFINED' if complete else 'DRAFT')
            write_json(Path(project)/'routes'/(record['definition_id']+'.json'),record,max_bytes=2*1024**2)
            return {'ok':True,**copy.deepcopy(record)}

    def close_session(self,project):
        with self.lock:
            value=self.sessions.pop(str(project),None)
            if value is None:return {'ok':True,'status':'CLOSED','already_closed':True}
            runtime=value['runtime'];runtime.deadline=time.monotonic()+5
            try:
                runtime.close_verified()
                return {'ok':True,'status':'CLOSED','worker_close_acknowledged':True,'worker_exit_code':runtime.exit_code}
            finally:runtime.__exit__(None,None,None)

    def close(self):
        self.stopping.set()
        with self.lock:
            for project in list(self.sessions):
                try:self.close_session(project)
                except (ValueError,OSError,RuntimeError):pass
