"""Owned, bounded auxiliary inputs and immutable completed build registration."""
from pathlib import Path
import hashlib
import re
import uuid

from . import workbench_projects as p
from .asset_schema import label
from .assets import checked_path
from .script_schema import load_script_json

LIMITS={'patch':64*1024**2,'catalog':16*1024**2,'save':8*1024**2,'translation':4*1024**2,'audio':2*1024**2,'resource':48*1024,'symbols':2*1024**2}


def read_bounded(path,limit,expected=None,*,cancelled=lambda:False):
    path=checked_path(Path(path));measured=p._measure(path,expected,cancelled=cancelled)
    if measured['size']>limit:raise ValueError('Input exceeds this tool’s byte limit.')
    result=bytearray()
    with path.open('rb') as stream:
        while raw:=stream.read(min(65536,limit+1-len(result))):
            if cancelled():raise KeyboardInterrupt
            result.extend(raw)
            if len(result)>limit:raise ValueError('Input grew beyond this tool’s byte limit.')
    if len(result)!=measured['size'] or hashlib.sha256(result).hexdigest()!=measured['sha256']:raise ValueError('Input changed while reading.')
    p._measure(path,measured,cancelled=cancelled);return bytes(result)


def list_inputs(project):
    project=checked_path(Path(project));path=project/'inputs.json'
    if not path.exists():return []
    value=load_script_json(path,max_bytes=1024**2)
    rows=value.get('inputs')
    if value.get('format')!='romancer-inputs-v1' or type(rows) is not list or len(rows)>512:
        raise ValueError('Invalid project input list. Restore a private backup.')
    seen=set()
    for row in rows:
        if type(row) is not dict or set(row)!={'input_id','name','kind','path','size','sha256'}:raise ValueError('invalid owned input record')
        p.identifier(row['input_id']);p.identifier(row['sha256']);label(row['name'],240)
        if row['input_id'] in seen or row['kind'] not in LIMITS:raise ValueError('invalid or duplicate input kind/identity')
        seen.add(row['input_id'])
        if type(row['size']) is not int or not 0<=row['size']<=LIMITS[row['kind']]:raise ValueError('input exceeds its byte budget')
        if not re.fullmatch(r'inputs/'+row['input_id']+r'\.[a-z0-9]{1,8}',row['path']):raise ValueError('input path escapes owned storage')
    return rows


def import_input(project,source,name,kind,*,cancelled=lambda:False):
    if kind not in LIMITS:raise ValueError('Choose a patch, catalog, battery save, translation sheet, audio or data resource.')
    label(name,240)
    if Path(name).name!=name or any(c in name for c in '\\/:'):raise ValueError('Use a filename without a directory.')
    project=checked_path(Path(project));source=checked_path(Path(source))
    if source.stat().st_size>LIMITS[kind]:raise ValueError(f'{kind.title()} exceeds the {LIMITS[kind]//1024**2} MiB import limit.')
    measured=p._measure(source,cancelled=cancelled)
    with p.locked(project):
        rows=list_inputs(project)
        if len(rows)>=512:raise ValueError('This project has reached its 512 imported-file limit.')
        folder=checked_path(project/'inputs');folder.mkdir(exist_ok=True)
        suffix=Path(name).suffix.lower().lstrip('.')
        if not re.fullmatch('[a-z0-9]{1,8}',suffix):suffix='bin'
        ident=uuid.uuid4().hex;target=folder/(ident+'.'+suffix)
        copied=p._publish_copy(source,target,measured,cancelled=cancelled)
        if copied['size']>LIMITS[kind]:raise ValueError('input changed beyond its byte budget')
        row={'input_id':ident,'name':name,'kind':kind,'path':target.relative_to(project).as_posix(),**copied}
        rows.append(row);p.write_json(project/'inputs.json',{'format':'romancer-inputs-v1','inputs':rows},max_bytes=1024**2)
    return {'ok':True,**{k:v for k,v in row.items() if k!='path'}}


def input_file(project,input_id,kind):
    p.identifier(input_id);project=checked_path(Path(project))
    row=next((r for r in list_inputs(project) if r['input_id']==input_id),None)
    if row is None:raise ValueError('Imported file is missing. Choose the file again.')
    if row['kind']!=kind:raise ValueError('Imported file kind does not match this tool.')
    path=checked_path(project/row['path']);p._measure(path,row)
    return row,path


def register_completed_build(project,parent_id,path,plan_id,kind,name,*,expected_parent_sha256=None,expected_output=None):
    """The caller has independently verified output bytes; never replace a file."""
    from .history import register_build
    project=checked_path(Path(project));path=checked_path(Path(path));p.identifier(plan_id);label(name,120);label(kind,80)
    if path.parent!=project/'builds':raise ValueError('Completed builds must use owned build storage.')
    with p.locked(project) as value:
        parent=p.artifact(project,parent_id);p._measure(parent['path'],parent);measured=p._measure(path,expected_output)
        if expected_parent_sha256 is not None and parent['sha256']!=expected_parent_sha256:raise ValueError('Build parent identity changed.')
        registered=register_build(project,{'inputs':[{'role':'original','path':parent['path']}],
            'output':str(path),'adapter':{'name':kind,'version':'1'},
            'profile':{'name':'reviewed-workbench-tool','version':'1'},'settings':{'plan_id':plan_id}},project)
        record={'artifact_id':uuid.uuid4().hex,'name':name,'kind':'build','path':str(path),'system':parent['system'],
                **measured,'source_id':parent_id,'plan_id':plan_id,'build_id':registered['build_id']}
        p.assess_artifact(record);value['builds'].append(record);p.write_json(project/'project.json',value)
    return {'ok':True,'status':'BUILT','original_preserved':True,**record}
