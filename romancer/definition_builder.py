"""Preview and save source-bound editor definitions with a metadata review guard."""
from .asset_schema import number


class DefinitionBuilder:
    def __init__(self,api):self.api=api
    def routes(self):return {'definitions.preview':('project_id artifact_id kind config',self.preview),
        'definitions.save':('project_id artifact_id kind config review_id replace',self.save)}

    def _definition(self,row,path,kind,config,c):
        if kind=='tables':
            from .data_tables import validate_definition
            return validate_definition(config,row['size'])
        if kind in ('assets','script'):
            from .resource_forms import graphics_schema,script_schema
            if type(config) is not dict or config.get('system_id')!=(row.get('system_id') or row.get('system_hint')):
                raise ValueError('Choose the identified cartridge system or decoded resource system hint.')
            number(config.get('count'),1,256 if kind=='assets' else 64)
            if kind=='script':number(config.get('capacity'),1,512)
            return (graphics_schema if kind=='assets' else script_schema)(path,row['sha256'],config)
        if kind not in ('levels','sound','commands'):raise ValueError('Choose graphics, text, tables, levels, sound or commands.')
        return config

    def _inspect(self,path,row,kind,definition,c):
        if kind=='tables':
            from .data_tables import inspect_table
            return inspect_table(path,row['sha256'],definition,0,8)
        if kind=='assets':
            from .assets import inspect_assets
            return inspect_assets(path,definition)
        if kind=='script':
            from .script import inspect_script
            return inspect_script(path,definition)
        from .workbench_files import read_bounded
        raw=read_bounded(path,64*1024**2,row,cancelled=c)
        if kind=='commands':
            from .command_editor import inspect_commands
            return inspect_commands(raw,definition,row['sha256'],cancelled=c)
        if kind=='levels':
            from .level_design import inspect_level
            return inspect_level(raw,definition,row['sha256'])
        from .sound_studio import inspect_sound
        return inspect_sound(raw,definition,row['sha256'])

    def _prepare(self,p,c):
        _,row,path=self.api.source(p);kind=p['kind']
        definition=self._definition(row,path,kind,p['config'],c)
        document={'format':'romancer-research-v1','source':{'sha256':row['sha256'],'size':row['size'],'system_id':row.get('system_id')},
            'definitions':{kind:definition},'notes':[]}
        checked,_,review=self.api.research._review(row,path,document,c)
        inspection=self._inspect(path,row,kind,checked['definitions'][kind],c)
        if not inspection.get('ok'):raise ValueError(inspection.get('error','This definition cannot decode the selected source.'))
        if c():raise KeyboardInterrupt
        return document,{**review,'kind':kind,'inspection':inspection,'definition':checked['definitions'][kind],
            'definition_saved':False,'rom_modified':False,'scope':'Preview of an explicit layout. Labels describe your declaration; gameplay meaning needs evidence.'}

    def preview(self,p,c):return self._prepare(p,c)[1]

    def save(self,p,c):
        document,review=self._prepare(p,c)
        if review['review_id']!=p['review_id']:raise ValueError('The layout or source research changed. Preview the definition again.')
        result=self.api.research.apply({**{k:p[k] for k in ('project_id','artifact_id','review_id','replace')},'document':document},c)
        return {**result,'kind':p['kind'],'definition':review['definition'],'inspection':review['inspection'],'rom_modified':False}
