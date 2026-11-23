"""The six-system workbench release; unknown inputs remain inspect-only."""
from . import workbench_projects as projects
from .script_schema import load_script_json

SYSTEMS=('nes', 'snes', 'genesis', 'gb', 'gbc', 'sms')
LEVEL_EDITOR_ENABLED = False
LEVEL_WRITE_OPERATIONS = frozenset(('levels.plan', 'games.maps.plan'))
LEVEL_EDITOR_MESSAGE = 'Edit levels on a level map: choose Levels, record the level, then paint on its map.'


def require_supported(row):
    if row.get('system_id') not in SYSTEMS:raise ValueError('Inspect only: this source is outside the six supported cartridge systems.')


def require_editable(project,row):
    """Decoded children inherit editing scope, never native cartridge identity."""
    seen=set()
    for _ in range(32):
        if row.get('system_id') in SYSTEMS:return
        if row['artifact_id'] in seen:break
        seen.add(row['artifact_id'])
        if row.get('source_id'):
            row=projects.artifact(project,row['source_id']);continue
        metadata=row.get('compressed_parent')
        if not metadata:break
        parent=projects.artifact(project,metadata['parent_id'])
        if parent['sha256']!=metadata['parent_sha256'] or row['sha256']!=metadata['decoded_sha256']:break
        from .resource_compression import inspect_compressed
        checked=inspect_compressed(parent['path'],parent['sha256'],metadata['offset'],metadata['allocation'],metadata['codec'])
        if checked['decoded_sha256']!=row['sha256'] or checked['stream_sha256']!=metadata['stream_sha256']:break
        row=parent
    require_supported(row)


def guard_request(api,operation,p):
    if not LEVEL_EDITOR_ENABLED and operation == 'games.plan' and p.get('profile_id') == 'ffl2-usa':
        raise ValueError(LEVEL_EDITOR_MESSAGE)
    if 'system_id' in p and p['system_id'] not in SYSTEMS:raise ValueError('This release supports only the six cartridge systems listed in Settings.')
    if operation.startswith('containers.') and operation!='containers.inventory':raise ValueError('This operation is outside the six-system cartridge release.')
    writes=operation.endswith('.plan') or operation in (
      'bytes.plan','systems.plan_edits','compression.plan_reinsert','runtime.load','runtime.load_profile','runtime.smoke_profile',
      'runtime.load_game_save','saves.restore','patches.preview','recipes.preview','captures.record','debug.observe',
      'regression.bisect','regression.bisect_profile','route.run','route.run_profile','routes.run','suite.run')
    if writes and 'artifact_id' in p:
        project=api.project(p);row=projects.artifact(project,p['artifact_id'])
        (require_editable(project,row) if operation.endswith('.plan') or operation in ('systems.plan_edits','patches.preview','recipes.preview') else require_supported(row))
    if operation in ('compression.plan_reinsert','compression.preview_reinsert','compression.plan_relocate'):require_supported(projects.artifact(api.project(p),p['parent_id']))
    if operation in ('build.apply','structured.apply','patches.apply'):
        project=api.project(p);ident=projects.identifier(p['plan_id']);plan=load_script_json(project/'plans'/(ident+'.json'),max_bytes=8*1024**2)
        require_editable(project,projects.artifact(project,plan.get('source_id',plan.get('artifact_id'))))
