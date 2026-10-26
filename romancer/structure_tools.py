"""Source-owned structural hypotheses and checked neutral editor definitions."""
from .asset_schema import number
from .release_scope import require_supported
from .workbench_projects import _measure
from .structural_lab import survey,table_definition


class StructureTools:
    def __init__(self,api):self.api=api

    def routes(self):
        return {'structures.survey':('project_id artifact_id offset length',self.survey),
            'structures.definition':('project_id artifact_id offset length candidate_id interpretation',self.definition)}

    def survey(self,p,c):
        _,row,path=self.api.source(p);require_supported(row)
        number(p['length'],1,65536);number(p['offset'],0,row['size']-p['length'])
        with path.open('rb') as stream:stream.seek(p['offset']);raw=stream.read(p['length'])
        if len(raw)!=p['length']:raise ValueError('Source changed during the structural experiment.')
        result=survey(raw,row['sha256'],row['system_id'],p['offset'],row['size'],cancelled=c)
        _measure(path,row,cancelled=c)
        return {**result,'artifact_id':row['artifact_id']}

    def definition(self,p,c):
        result=self.survey(p,c)
        candidate=next((r for r in result['candidates'] if r['candidate_id']==p['candidate_id']),None)
        if candidate is None:raise ValueError('This hypothesis is not present in the current source experiment. Rescan the range.')
        _,row,path=self.api.source(p)
        definition=table_definition(candidate,row['size'],p['interpretation'])
        from .data_tables import inspect_table
        inspection=inspect_table(path,row['sha256'],definition,0,8)
        return {'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'candidate':candidate,
            'definition':definition,'inspection':inspection,'game_semantics_verified':False,
            'definition_saved':False,'rom_modified':False,'write_authorized':False,
            'interpretation':p['interpretation'],'scope':'Generated neutral editor. Field labels and pointer use are hypotheses; saving a definition is an explicit declaration.'}
