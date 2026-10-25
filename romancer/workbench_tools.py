"""Connected workbench tools; the core API still owns validation and locking."""
from pathlib import Path
from .workbench_files import list_inputs,import_input


class WorkbenchTools:
    def __init__(self,api):self.api=api

    def routes(self):
        return {
            'inputs.list':('project_id',self.inputs_list),
            'inputs.import':('project_id path name kind',self.inputs_import),
            'patches.preview':('project_id artifact_id input_id expected_reference',self.patch_preview),
            'patches.apply':('project_id plan_id name',self.patch_apply),
            'revision.import':('project_id input_id scope',self.revision_import),
            'revision.info':('project_id',self.revision_info),
            'revision.list':('project_id query',self.revision_list),
            'revision.lookup':('project_id artifact_id scope expected_id',self.revision_lookup),
            'hex.search':('project_id artifact_id kind query start endian width signed',self.hex_search),
            'hex.numbers':('project_id artifact_id offset',self.hex_numbers),
            'hex.bookmarks':('project_id artifact_id',self.hex_bookmarks),
            'hex.bookmark':('project_id artifact_id offset name remove',self.hex_bookmark),
            'builds.timeline':('project_id',self.builds_timeline),
            'builds.annotate':('project_id artifact_id name notes',self.builds_annotate),
            'builds.compare':('project_id left_id right_id',self.builds_compare),
            'project.validate':('project_id',self.project_validate),
            'support.collect':('selection',self.support_collect),
            'saves.list':('project_id artifact_id',self.saves_list),
            'saves.capture':('project_id artifact_id name',self.saves_capture),
            'saves.import':('project_id artifact_id input_id name',self.saves_import),
            'saves.restore':('project_id artifact_id save_id',self.saves_restore),
            'saves.export':('project_id artifact_id save_id',self.saves_export),
            'runtime.status':('project_id',self.runtime_status),
            'translation.export':('project_id artifact_id schema format',self.translation_export),
            'translation.preview':('project_id artifact_id schema input_id format',self.translation_preview),
            'routes.record_region':('project_id region frame_sha256',self.routes_region),
        }

    def inputs_list(self,p,c):
        rows=list_inputs(self.api.project(p))
        return {'ok':True,'inputs':[{k:v for k,v in r.items() if k!='path'} for r in rows]}

    def inputs_import(self,p,c):
        return import_input(self.api.project(p),Path(p['path']),p['name'],p['kind'],cancelled=c)

    def patch_preview(self,p,c):
        from .patch_import import preview_patch
        return preview_patch(self.api.project(p),p['artifact_id'],p['input_id'],p['expected_reference'],cancelled=c)

    def patch_apply(self,p,c):
        from .patch_import import apply_preview
        return apply_preview(self.api.project(p),p['plan_id'],p['name'],cancelled=c)

    def revision_import(self,p,c):
        from .revision_catalog import import_catalog
        result=import_catalog(self.api.project(p),p['input_id'],p['scope'],cancelled=c)
        self.api.invalidate_scans(p['project_id']);return result

    def revision_info(self,p,c):
        from .revision_catalog import catalog_info
        return catalog_info(self.api.project(p))

    def revision_list(self,p,c):
        from .revision_catalog import catalog_info
        return catalog_info(self.api.project(p),p['query'])

    def revision_lookup(self,p,c):
        from .revision_catalog import lookup_revision
        return lookup_revision(self.api.project(p),p['artifact_id'],p['scope'],p['expected_id'],cancelled=c)

    def hex_search(self,p,c):
        from .hex_tools import search
        return search(self.api.project(p),*(p[k] for k in ('artifact_id','kind','query','start','endian','width','signed')),cancelled=c)

    def hex_numbers(self,p,c):
        from .hex_tools import inspect_numbers
        return inspect_numbers(self.api.project(p),p['artifact_id'],p['offset'])

    def hex_bookmarks(self,p,c):
        from .hex_tools import bookmarks
        return bookmarks(self.api.project(p),p['artifact_id'])

    def hex_bookmark(self,p,c):
        from .hex_tools import save_bookmark
        return save_bookmark(self.api.project(p),*(p[k] for k in ('artifact_id','offset','name','remove')))

    def builds_timeline(self,p,c):
        from .build_history import timeline
        return timeline(self.api.project(p))

    def builds_annotate(self,p,c):
        from .build_history import annotate
        return annotate(self.api.project(p),*(p[k] for k in ('artifact_id','name','notes')))

    def builds_compare(self,p,c):
        from .build_history import compare
        return compare(self.api.project(p),p['left_id'],p['right_id'],cancelled=c)

    def project_validate(self,p,c):
        from .project_checks import validate_project
        return validate_project(self.api.project(p),cancelled=c)

    def support_collect(self,p,c):
        from .support_report import collect_report
        project=None if p['selection'] is None else self.api.project({'project_id':p['selection']})
        return collect_report(self.api.workspace,project,cancelled=c)

    def saves_list(self,p,c):
        from .save_manager import list_saves
        return list_saves(self.api.project(p),p['artifact_id'])

    def saves_capture(self,p,c):
        from .save_manager import capture_save
        return capture_save(self.api,self.api.project(p),p['artifact_id'],p['name'],cancelled=c)

    def saves_import(self,p,c):
        from .save_manager import import_save
        return import_save(self.api,self.api.project(p),p['artifact_id'],p['input_id'],p['name'],cancelled=c)

    def saves_restore(self,p,c):
        from .save_manager import restore_save
        return restore_save(self.api,self.api.project(p),p['artifact_id'],p['save_id'],cancelled=c)

    def saves_export(self,p,c):
        from .save_manager import export_save
        return export_save(self.api,self.api.project(p),p['artifact_id'],p['save_id'],cancelled=c)

    def runtime_status(self,p,c):
        project=self.api.project(p)
        with self.api.runtime.lock:
            session=self.api.runtime.sessions.get(str(project))
            return {'ok':True,'active':session is not None,'artifact_id':session['artifact_id'] if session else None}

    def translation_export(self,p,c):
        from .translation_sheets import export_sheet
        from .release import publish_bytes
        project=self.api.project(p);text=export_sheet(project,p['artifact_id'],p['schema'],p['format'])
        path=self.api._export_path(project,p['format']);publish_bytes(path,text.encode('utf-8-sig'),cancelled=c)
        return {'ok':True,'status':'EXPORTED','export':self.api._record_export(project,path,'translation')}

    def translation_preview(self,p,c):
        from .translation_sheets import preview_sheet
        return preview_sheet(self.api.project(p),p['artifact_id'],p['schema'],p['input_id'],p['format'],cancelled=c)

    def routes_region(self,p,c):
        return self.api.runtime.record_assertion(self.api.project(p),'region',{'region':p['region'],'frame_sha256':p['frame_sha256']},cancelled=c)


def register_tools(api):
    api.tools=WorkbenchTools(api);api.routes.update(api.tools.routes())
