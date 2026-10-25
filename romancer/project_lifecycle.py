"""Recoverable project removal; no recursive deletion and no external files touched."""
from datetime import datetime,timezone
from pathlib import Path
import uuid
from .assets import checked_path
from . import workbench_projects as projects
from .script_schema import load_script_json
from .patch_sets import _publish_directory

def trash_projects(workspace):
    root=checked_path(Path(workspace)/'trash');rows=[]
    if not root.exists():return {'ok':True,'projects':[]}
    for bucket in sorted(root.iterdir()):
        try:
            projects.identifier(bucket.name);bucket=checked_path(bucket)
            record=load_script_json(bucket/'deleted.json',max_bytes=4096);pid=projects.identifier(record['project_id'])
            project=projects.read_project(checked_path(bucket/pid))
            rows.append({'trash_id':bucket.name,'project_id':pid,'name':project['name'],'deleted_utc':record['deleted_utc']})
        except (ValueError,OSError,KeyError,TypeError):continue
    return {'ok':True,'projects':rows}

def delete_project(workspace,project):
    workspace=checked_path(Path(workspace));project=checked_path(Path(project));record=projects.read_project(project)
    if project.parent!=workspace/'projects':raise ValueError('project is outside this workspace')
    root=checked_path(workspace/'trash');root.mkdir(exist_ok=True);trash_id=uuid.uuid4().hex
    bucket=checked_path(root/trash_id);bucket.mkdir();target=checked_path(bucket/record['project_id'])
    if target.parent.parent!=root or target.exists():raise ValueError('unsafe project trash destination')
    projects.write_json(bucket/'deleted.json',{'project_id':record['project_id'],'deleted_utc':datetime.now(timezone.utc).isoformat()})
    _publish_directory(project,target)
    return {'ok':True,'status':'MOVED_TO_TRASH','trash_id':trash_id,'original_files_untouched':True,'recoverable':True}

def undelete_project(workspace,trash_id):
    workspace=checked_path(Path(workspace));trash_id=projects.identifier(trash_id)
    bucket=checked_path(workspace/'trash'/trash_id);record=load_script_json(bucket/'deleted.json',max_bytes=4096)
    pid=projects.identifier(record['project_id']);source=checked_path(bucket/pid);projects.read_project(source)
    target=checked_path(workspace/'projects'/pid)
    if source.parent.parent!=workspace/'trash' or target.parent!=workspace/'projects':raise ValueError('unsafe project recovery paths')
    if target.exists():raise ValueError('a project with this identity already exists; recovery never replaces it')
    # Unique project identifiers and the API administrator lock prevent an
    # ordinary restore from clobbering an existing destination.
    _publish_directory(source,target)
    return {'ok':True,'status':'RESTORED','project_id':pid}
