"""Ordinary raw cartridge saves, separate from states; immutable restore backups."""
import base64
import copy
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import re
import uuid
from . import workbench_projects as p
from .asset_schema import label
from .assets import checked_path
from .script_schema import load_script_json
from .workbench_files import input_file,read_bounded

MAX_SAVE=8*1024**2
BINDING=('core_sha256','game_sha256','runtime_identity_sha256')


def _payload(snapshot):
    if type(snapshot) is not dict:raise ValueError('Invalid game-save record.')
    text=snapshot.get('save_ram_base64')
    if type(text) is not str or len(text)>((MAX_SAVE+2)//3)*4:raise ValueError('Choose an ordinary save-RAM record, not a save state.')
    raw=base64.b64decode(text,validate=True)
    if not raw or len(raw)>MAX_SAVE or hashlib.sha256(raw).hexdigest()!=snapshot.get('sha256'):raise ValueError('Save data checksum differs or size is unsupported.')
    for key in BINDING:
        if type(snapshot.get(key)) is not str or not re.fullmatch('[a-f0-9]{64}',snapshot[key]):raise ValueError('Save record lacks a measured core/game/setup binding.')
    return raw


def _active(api,project,artifact_id,cancelled):
    row=p.artifact(project,artifact_id);p._measure(row['path'],row,cancelled=cancelled)
    selection=api.runtime.session_selection(project)
    if selection['id']!=artifact_id or selection['sha256']!=row['sha256']:raise ValueError('Load the selected ROM before managing its battery saves.')
    session=api.runtime.sessions[str(project)]
    if session.get('recording',{}).get('status')=='RECORDING':raise ValueError('Stop route recording before changing battery saves.')
    snapshot=api.runtime.request(project,'save_game',{},cancelled=cancelled);_payload(snapshot)
    if snapshot['game_sha256']!=row['sha256']:raise ValueError('Active save belongs to another ROM revision.')
    return snapshot,session


def _store(project,snapshot,name,origin):
    label(name,120);raw=_payload(snapshot);save_id=uuid.uuid4().hex
    clean={k:copy.deepcopy(v) for k,v in snapshot.items() if k in {*BINDING,'sha256','save_ram_base64','run_mode','provenance','dependency_coverage'}}
    clean.update(ok=True,scope='exposed_save_ram_snapshot',in_game_save_event_verified=False,
                 manager={'name':name,'origin':origin,'created_utc':datetime.now(timezone.utc).isoformat()})
    with p.locked(project):p.write_json(Path(project)/'sessions'/(save_id+'.json'),clean,max_bytes=12*1024**2)
    return {'ok':True,'status':'SAVED','save_id':save_id,'name':name,'size':len(raw),'sha256':clean['sha256'],'origin':origin}


def _get(project,save_id,artifact_id):
    p.identifier(save_id);row=p.artifact(project,artifact_id);p._measure(row['path'],row)
    snapshot=load_script_json(checked_path(Path(project)/'sessions'/(save_id+'.json')),max_bytes=12*1024**2);raw=_payload(snapshot)
    if snapshot['game_sha256']!=row['sha256']:raise ValueError('Save belongs to a different ROM revision. Select its exact source first.')
    return snapshot,raw


def list_saves(project,artifact_id):
    row=p.artifact(project,artifact_id);p._measure(row['path'],row);result=[];files=sorted((Path(project)/'sessions').glob('*.json'))
    for path in files[:512]:
        try:
            snapshot=load_script_json(checked_path(path),max_bytes=12*1024**2)
            if 'save_ram_base64' not in snapshot or snapshot.get('game_sha256')!=row['sha256']:continue
            raw=_payload(snapshot);manager=snapshot.get('manager',{});name=manager.get('name','Captured save '+path.stem[:8]);label(name,120)
            result.append({'save_id':path.stem,'name':name,'size':len(raw),'sha256':snapshot['sha256'],
                'core_sha256':snapshot['core_sha256'],'runtime_identity_sha256':snapshot['runtime_identity_sha256'],
                'origin':manager.get('origin','captured'),'created_utc':manager.get('created_utc','')})
        except (ValueError,OSError,KeyError,TypeError):continue
    return {'ok':True,'project_id':Path(project).name,'artifact_id':artifact_id,'saves':result,'truncated':len(files)>512}


def capture_save(api,project,artifact_id,name,*,cancelled=lambda:False):
    with api.runtime.lock:
        snapshot,_=_active(api,project,artifact_id,cancelled)
        return _store(project,snapshot,name,'captured')


def _compatible_size(raw,current,session):
    exposed=_payload(current)
    if len(raw)==len(exposed):return True
    # Match the frontend's narrow mGBA initial-allocation exception. The new
    # worker still verifies every seed byte and the unchanged allocation tail.
    runtime=session.get('runtime');loaded=getattr(runtime,'load_result',{})
    core=loaded.get('loaded',{}).get('core',{})
    tail=exposed[len(raw):]
    return (core.get('library_name','').casefold()=='mgba'
            and Path(session['load'].get('game','')).suffix.lower()=='.gba'
            and len(exposed)==131072 and len(raw) in (512,8192,32768,65536)
            and bool(tail) and len(set(tail))==1 and tail[0] in (0,255))


def import_save(api,project,artifact_id,input_id,name,*,cancelled=lambda:False):
    label(name,120);entry,path=input_file(project,input_id,'save')
    if Path(entry['name']).suffix.lower() not in ('.sav','.srm'):raise ValueError('Choose a raw .sav or .srm file. Save states and wrapped formats are unsupported.')
    raw=read_bounded(path,MAX_SAVE,entry,cancelled=cancelled)
    with api.runtime.lock:
        active,session=_active(api,project,artifact_id,cancelled)
        if not _compatible_size(raw,active,session):raise ValueError('Save size differs from the core’s exposed save RAM. Choose a raw save for this ROM and core.')
        imported={**active,'save_ram_base64':base64.b64encode(raw).decode('ascii'),'sha256':hashlib.sha256(raw).hexdigest(),
                  'provenance':{'origin':'external_battery_save','state_derived':None,'ancestor_state_sha256':None,'trust':'user_supplied_save'}}
        return _store(project,imported,name,'imported')


def restore_save(api,project,artifact_id,save_id,*,cancelled=lambda:False):
    candidate,raw=_get(project,save_id,artifact_id)
    with api.runtime.lock:
        current,session=_active(api,project,artifact_id,cancelled)
        if any(candidate[k]!=current[k] for k in BINDING):raise ValueError('Save core, ROM or effective setup differs. Load the matching setup first.')
        if not _compatible_size(raw,current,session):raise ValueError('Save size differs from this core’s exposed save RAM.')
        backup=_store(project,current,'Before restoring another save','automatic_backup')
        config=copy.deepcopy(session['load']);config['game_save']=candidate
        core=config['core'];options=config.get('core_options',{})
        api.runtime.close_session(project)
        try:loaded=api.runtime.load(project,artifact_id,core,options,configuration=config,cancelled=cancelled)
        except (ValueError,OSError,RuntimeError) as error:
            raise ValueError(f'Restart refused: {error}. The previous RAM remains in the automatic backup {backup["save_id"][:8]}.') from error
    return {'ok':True,'status':'RESTORED','runtime':loaded,'save_id':save_id,'backup_save_id':backup['save_id'],'scope':'exposed_save_ram_snapshot','in_game_save_event_verified':False}


def export_save(api,project,artifact_id,save_id,*,cancelled=lambda:False):
    from .release import publish_bytes
    snapshot,raw=_get(project,save_id,artifact_id);path=api._export_path(project,'sav');publish_bytes(path,raw,cancelled=cancelled)
    return {'ok':True,'status':'EXPORTED','size':len(raw),'export':api._record_export(project,path,'save',{'source_sha256':snapshot['game_sha256']})}
