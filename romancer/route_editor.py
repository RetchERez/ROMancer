"""Persisted route definitions and acknowledged input recordings, never imported passes."""
import json
from pathlib import Path
import uuid
from .asset_schema import fields,label,number
from .replay_schema import validate_route
from .script_schema import canonical_bytes,load_script_json
from . import workbench_projects as p


def compile_route(name,steps,max_frames=6000,max_actions=100):
    label(name);return validate_route({'schema_version':1,'id':name,'max_frames':max_frames,'max_actions':max_actions,'steps':steps})


def _complete(route):
    try:validate_route(route);return True
    except ValueError:
        if not route['steps'] or any(s.get('assertions') for s in route['steps']):raise
        # Validate the entire input grammar/budgets while leaving the stored draft assertion-free.
        probe=json.loads(canonical_bytes(route,max_bytes=1024**2));probe['steps'][-1]['assertions']=[{'kind':'memory_eq','region':2,'offset':0,'expected_hex':'00'}]
        validate_route(probe);return False


def save_definition(project,selection,system_id,route,initial_state_id=None,*,allow_draft=False):
    from .system_registry import SYSTEM_IDS
    if system_id not in SYSTEM_IDS:raise ValueError('unknown system')
    fields(selection,'kind id sha256');p.identifier(selection['id']);p.identifier(selection['sha256'])
    if selection['kind'] not in ('artifact','disc'):raise ValueError('unknown route source kind')
    route=json.loads(canonical_bytes(route,max_bytes=1024**2));complete=_complete(route)
    if not complete and not allow_draft:raise ValueError('add at least one measured assertion')
    if initial_state_id is not None:
        p.identifier(initial_state_id);snapshot=load_script_json(Path(project)/'sessions'/(initial_state_id+'.json'),max_bytes=12*1024**2)
        if 'state_base64' not in snapshot or snapshot.get('game_sha256')!=selection['sha256']:raise ValueError('checkpoint belongs to another selected image')
    root=Path(project)/'routes';root.mkdir(exist_ok=True)
    if len(list(root.glob('*.json')))>=512:raise ValueError('route definition budget reached')
    definition={'format':'romancer-route-v1','definition_id':uuid.uuid4().hex,'selection':selection,'system_id':system_id,'route':route,'initial_state_id':initial_state_id,'complete':complete,'status':'DEFINED' if complete else 'DRAFT'}
    p.write_json(root/(definition['definition_id']+'.json'),definition,max_bytes=2*1024**2)
    return {'ok':True,**definition}


def get_definition(project,definition_id):
    p.identifier(definition_id);value=load_script_json(Path(project)/'routes'/(definition_id+'.json'),max_bytes=2*1024**2)
    if value.get('format')!='romancer-route-v1' or value.get('definition_id')!=definition_id:raise ValueError('invalid route definition')
    if value['route']['steps']:_complete(value['route'])
    return {'ok':True,**value}


def list_definitions(project):
    rows=[]
    for path in sorted((Path(project)/'routes').glob('*.json'))[-512:]:
        value=get_definition(project,path.stem);rows.append({k:value[k] for k in ('definition_id','selection','system_id','initial_state_id','complete','status')}|{'name':value['route']['id'],'steps':len(value['route']['steps'])})
    return {'ok':True,'routes':rows}


def append_input(record,step):
    """Called only after the native worker acknowledged an actual advance."""
    route=record['route'];steps=route['steps']
    if sum(s['frames'] for s in steps)+step['frames']>route['max_frames']:raise ValueError('recording frame budget exceeded')
    merge=steps and not steps[-1]['assertions'] and steps[-1]['transition'] is None and all(steps[-1][k]==step[k] for k in ('buttons','port')) and steps[-1]['frames']+step['frames']<=600
    if merge:steps[-1]['frames']+=step['frames']
    else:
        if len(steps)>=route['max_actions']:raise ValueError('recording action budget exceeded')
        steps.append({**step,'assertions':[],'transition':None,'checkpoint':False})
    return record
