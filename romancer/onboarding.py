"""Short, fixed guided lessons and workspace-persistent tutorial preferences."""
from copy import deepcopy
from .assets import checked_path
from .script_schema import load_script_json
from . import workbench_projects as projects


LESSONS=[
 {'id':'basic-start','section':'Basic','title':'Find your way','steps':[
  {'page':'overview','target':'.task-checklist','title':'Your workspace','body':'Projects keep your original ROM and separate builds. This original practice ROM is safe to explore.'},
  {'page':'resources','target':'.identity','title':'Inspect a source','body':'Resources shows the selected ROM and its stored bytes. Choose a known resource before editing.'},
  {'page':'help','target':'[data-action="tutorial-hub"]','title':'Help is always here','body':'Open Tutorials from Help whenever you want another lesson.'}]},
 {'id':'basic-edit','section':'Basic','title':'Make your first patch','steps':[
  {'page':'assets','target':'#paint-canvas','title':'Try a tile edit','body':'Pick a palette index, then click pixels. Fill tile is a quick way to try a change.'},
  {'page':'assets','target':'[data-action="asset-plan"]','title':'Review, then build','body':'Review asset changes first. Then Create asset build saves your edit as a separate ROM.'},
  {'page':'playtest','target':'[data-action="runtime-load"]','title':'Playtest your build','body':'With a core configured, choose Load game, then Play. Pause stops playback. You can set up a core later.'},
  {'page':'release','target':'[data-action="release-patch"]','title':'Export a patch','body':'Choose the original and a build, then create a verified BPS patch. Your ROM stays private.'}]},
 {'id':'advanced-data','section':'Advanced','title':'Work with data','steps':[
  {'page':'tables','target':'#table-offset','title':'Define a table','body':'Enter a known offset and field layout, then Load table definition. Unknown game formats need their own definition.'},
  {'page':'tables','target':'[data-action="table-review"]','title':'Review a data change','body':'Edit a record, review changes, then create a separate build. Keep the original values for comparison.'},
  {'page':'automation','target':'#main .card','title':'Reuse your setup','body':'Save a definition or a source-bound recipe to repeat work. Preview each recipe before creating a build.'}]},
 {'id':'advanced-testing','section':'Advanced','title':'Test a change','steps':[
  {'page':'routes','target':'#main .card','title':'Record expected results','body':'Record inputs and add an expected frame or memory value. Save a cold-start test for repeatable checks.'},
  {'page':'regression','target':'[data-action="suite-run"]','title':'Compare original and build','body':'Select an original, a build and saved tests. A passing baseline is required; mismatched runs stay inconclusive.'},
  {'page':'debug','target':'#main .card','title':'Look closer with watches','body':'Use memory watches to compare observed bytes. A difference does not identify which instruction wrote it.'}]},
]
IDS={lesson['id'] for lesson in LESSONS}


def load_state(workspace):
    path=checked_path(workspace/'tutorial.json')
    value=load_script_json(path,max_bytes=16384) if path.exists() else {
        'schema_version':1,'never_ask_again':False,'progress':{},'practice_project_id':None}
    if (type(value) is not dict or set(value)!={'schema_version','never_ask_again','progress','practice_project_id'}
            or value['schema_version']!=1 or type(value['never_ask_again']) is not bool
            or type(value['progress']) is not dict or set(value['progress'])-IDS
            or any(status not in ('not_started','skipped','completed') for status in value['progress'].values())):
        raise ValueError('Tutorial preferences are invalid; workspace files were preserved.')
    if value['practice_project_id'] is not None:projects.identifier(value['practice_project_id'])
    return value


def save_state(workspace,value):
    projects.write_json(workspace/'tutorial.json',value,max_bytes=16384)


def tutorial_status(workspace):
    value=load_state(workspace)
    progress={key:value['progress'].get(key,'not_started') for key in IDS}
    return {'ok':True,'lessons':deepcopy(LESSONS),'progress':progress,
            'never_ask_again':value['never_ask_again'],
            'prompt':not value['never_ask_again'] and 'completed' not in progress.values()}


def set_preferences(workspace,never):
    if type(never) is not bool:raise ValueError('Never ask again must be a checkbox value.')
    value=load_state(workspace);value['never_ask_again']=never;save_state(workspace,value)
    return tutorial_status(workspace)


def record_progress(workspace,lesson,outcome):
    if type(lesson) is not str or lesson not in IDS or outcome not in ('completed','skipped'):
        raise ValueError('Choose a known lesson and completed or skipped outcome.')
    value=load_state(workspace)
    if value['progress'].get(lesson)!='completed':value['progress'][lesson]=outcome
    save_state(workspace,value);return tutorial_status(workspace)
