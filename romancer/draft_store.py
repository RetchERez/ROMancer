"""Atomic source-bound edit drafts with optimistic revisions and bounded history."""
from pathlib import Path
from .assets import digest
from .asset_schema import number,label
from .script_schema import load_script_json,canonical_bytes
from . import workbench_projects as p


def _load(project,artifact_id,key):
    label(key,240);row=p.artifact(project,artifact_id);p._measure(row['path'],row)
    root=Path(project)/'drafts';root.mkdir(exist_ok=True)
    path=root/(digest({'artifact_id':artifact_id,'key':key})+'.json')
    value=load_script_json(path,max_bytes=2*1024**2) if path.exists() else {'artifact_id':artifact_id,'key':key,'source_sha256':row['sha256'],'revision':0,'cursor':0,'states':[None]}
    if value['source_sha256']!=row['sha256'] or value['artifact_id']!=artifact_id or value['key']!=key:raise ValueError('draft belongs to a different source')
    return path,value


def _result(value):
    return {**{k:v for k,v in value.items() if k!='states'},'ok':True,'value':value['states'][value['cursor']],
            'can_undo':value['cursor']>0,'can_redo':value['cursor']+1<len(value['states'])}


def draft_get(project,artifact_id,key):return _result(_load(project,artifact_id,key)[1])


def draft_list(project,artifact_id):
    row=p.artifact(project,artifact_id);p._measure(row['path'],row)
    result=[]
    for path in sorted((Path(project)/'drafts').glob('*.json')):
        value=load_script_json(path,max_bytes=2*1024**2)
        if value['artifact_id']==artifact_id and value['source_sha256']==row['sha256']:result.append(_result(value))
    return {'ok':True,'drafts':result}


def draft_update(project,artifact_id,key,revision,value):
    number(revision,0,2**53);canonical_bytes(value,max_bytes=65536)
    with p.locked(project):
        path,record=_load(project,artifact_id,key)
        if revision!=record['revision']:raise ValueError('draft changed in another window; reopen before editing')
        if value==record['states'][record['cursor']]:return _result(record)
        states=record['states'][:record['cursor']+1]+[value]
        while len(states)>64 or len(canonical_bytes(states,max_bytes=8*1024**2))>1024**2:states.pop(0)
        record.update(states=states,cursor=len(states)-1,revision=revision+1)
        p.write_json(path,record,max_bytes=2*1024**2);return _result(record)


def draft_move(project,artifact_id,key,revision,direction):
    if type(direction) is not int or direction not in (-1,1):raise ValueError('undo/redo direction must be -1 or 1')
    with p.locked(project):
        path,record=_load(project,artifact_id,key)
        if revision!=record['revision']:raise ValueError('draft revision conflict')
        cursor=record['cursor']+direction
        if not 0<=cursor<len(record['states']):raise ValueError('no further draft history')
        record.update(cursor=cursor,revision=revision+1);p.write_json(path,record,max_bytes=2*1024**2)
        return _result(record)
