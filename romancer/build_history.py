"""User labels and comparisons do not change immutable outputs or test evidence."""
from pathlib import Path
from . import workbench_projects as p
from .asset_schema import label
from .assets import checked_path
from .script_schema import load_script_json
from .binary_tools import compare_files


def _notes(project):
    path=checked_path(Path(project)/'build-notes.json')
    if not path.exists():return {}
    value=load_script_json(path,max_bytes=1024*1024)
    if type(value) is not dict or value.get('format')!='romancer-build-notes-v1' or type(value.get('notes')) is not dict:raise ValueError('Build notes are invalid. Restore a backup.')
    for key,text in value['notes'].items():p.identifier(key);label(text,2000,blank=True)
    return value['notes']


def timeline(project):
    value=p.read_project(project);notes=_notes(project)
    return {'ok':True,'project_id':value['project_id'],'artifacts':[
        {**{k:r[k] for k in ('artifact_id','name','kind','sha256','size')},'parent_id':r.get('source_id'),
         'plan_id':r.get('plan_id'),'notes':notes.get(r['artifact_id'],'')}
        for r in value['sources']+value['builds']]}


def annotate(project,artifact_id,name,notes):
    label(name,120);label(notes,2000,blank=True)
    with p.locked(project) as value:
        row=next((r for r in value['builds'] if r['artifact_id']==artifact_id),None)
        if row is None:raise ValueError('Choose a build; original source labels are preserved.')
        p._measure(row['path'],row);saved=_notes(project);saved[artifact_id]=notes
        p.write_json(Path(project)/'build-notes.json',{'format':'romancer-build-notes-v1','notes':saved},max_bytes=1024*1024)
        row['name']=name;p.write_json(Path(project)/'project.json',value)
    return timeline(project)


def compare(project,left_id,right_id,*,cancelled=lambda:False):
    left=p.artifact(project,left_id);right=p.artifact(project,right_id)
    p._measure(left['path'],left,cancelled=cancelled);p._measure(right['path'],right,cancelled=cancelled)
    result=compare_files(left['path'],right['path'],cancelled=cancelled)
    p._measure(left['path'],left,cancelled=cancelled);p._measure(right['path'],right,cancelled=cancelled)
    return {'ok':True,'project_id':Path(project).name,'left_id':left_id,'right_id':right_id,
            'left_sha256':left['sha256'],'right_sha256':right['sha256'],**result}
