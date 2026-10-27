"""Editing readiness from checked definitions for the exact selected revision."""
from .research_tools import _definition
AREAS={'assets':('Graphics','assets'),'script':('Text & dialogue','scripts'),'tables':('Numbers & stats','tables'),'levels':('Levels & objects','levels'),'sound':('Music & sound','sound')}
class EditingReadinessTools:
    def __init__(self,api):self.api=api
    def routes(self):return {'editing.readiness':('project_id artifact_id',self.readiness)}
    def readiness(self,p,c):
        project,row,path=self.api.source(p);areas=[]
        for kind,(title,page) in AREAS.items():
            if c():raise KeyboardInterrupt
            status='needs_investigation';reason='No checked editing definition is saved for this revision.';action='Find or declare a layout';scope='No game structure inferred'
            if kind in row.get('descriptors',{}) and row['descriptors'][kind] is not None:
                try:
                    if type(row['descriptors'][kind]) is not dict:raise ValueError('The saved definition is malformed.')
                    if kind=='assets':
                        from .assets import inspect_assets
                        checked=inspect_assets(path,row['descriptors'][kind])
                    elif kind=='script':
                        from .script import inspect_script
                        checked=inspect_script(path,row['descriptors'][kind])
                    else:_definition(row,path,kind);checked={'ok':True}
                    if not checked.get('ok'):raise ValueError(str(checked.get('error','The layout cannot inspect this source.')))
                    if checked.get('write_supported') is False:raise ValueError('Read-only layout: '+'; '.join(checked.get('read_only_reasons',[])[:3]))
                    status='ready';reason='Saved layout successfully inspected this exact source.';action='Open editor';scope='Checked layout; game meaning is author-declared'
                    if kind=='assets' and not row['descriptors'][kind].get('palettes'):reason='Graphics layout inspected successfully. No editable palette is declared.'
                except (ValueError,OSError,KeyError,TypeError) as error:
                    status='unsupported';reason='Saved definition cannot be used: '+str(error)[:200];action='Repair or replace the definition'
            elif kind=='sound' and row.get('system_id')=='gba' and row.get('size')==8388608:
                known=self.api.studio.sound_system(p,c)
                if known.get('known_definition') and known.get('sequence_edit_supported'):
                    status='ready';reason='Selected songs have a checked engine, header and sequence layout. Conditional songs remain read-only.';action='Open decoded songs';scope='Checked M4A layout; explicit value edits only'
            areas.append({'kind':kind,'title':title,'page':page,'status':status,'reason':reason,'action':action,'scope':scope})
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'areas':areas,'game_semantics_inferred':False}
