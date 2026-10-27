"""Explicit local workbench operations over the validated engineering services."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import threading
import uuid
from datetime import datetime,timezone
from .asset_schema import fields
from .assets import checked_path,digest
from .runtime_session import snapshot_json
from .script_schema import load_script_json
from . import workbench_projects as projects
from .workbench_jobs import JobManager
from .workbench_runtime import RuntimePool
from . import ROMANCER_VERSION,ROMANCER_RELEASE_NAME,ROMANCER_BUILD_LABEL


class WorkbenchAPI:
    def __init__(self,workspace):
        self.workspace=checked_path(Path(workspace));self.workspace.mkdir(parents=True,exist_ok=True)
        self.projects=self.workspace/'projects';self.incoming=self.workspace/'incoming'
        self.projects.mkdir(exist_ok=True);self.incoming.mkdir(exist_ok=True)
        self.operation_locks={};self.operation_locks_guard=threading.Lock()
        self.profile_lock=threading.Lock();self.ui_launch_lock=threading.Lock();self.ui_launches={};self.tutorial_lock=threading.RLock()
        self.rom_scans={}
        self.project_admin_lock=threading.RLock()
        self.routes={
            'settings.get':('',self._settings_get),
            'settings.save':('revision values',self._settings_save),
            'settings.workspace.get':('',self._settings_workspace_get),
            'settings.workspace.save':('location',self._settings_workspace_save),
            'system.operations':('',self._operations),
            'games.inspect':('project_id artifact_id',self._game_inspect),
            'games.maps.catalog':('project_id artifact_id offset limit query',lambda p,c:self._game_maps(p,c,'catalog')),
            'games.maps.inspect':('project_id artifact_id header state',lambda p,c:self._game_maps(p,c,'inspect')),
            'games.maps.plan':('project_id artifact_id header changes',lambda p,c:self._game_maps(p,c,'plan')),
            'cheats.import':('project_id input_id',self._cheat_import),
            'cheats.catalog':('project_id',self._cheat_catalog),
            'cheats.inspect':('project_id artifact_id query page limit',self._cheat_inspect),
            'engines.inspect':('project_id artifact_id',self._engine_inspect),
            'games.plan':('project_id artifact_id profile_id values',self._game_plan),
            'graphics.observe':('project_id artifact_id frame_sha256 region offset length',self._graphics_observe),
            'graphics.declare':('project_id artifact_id evidence_id matches',self._graphics_declare),
            'rom.scan.start':('project_id artifact_id rescan',self._scan_start),
            'rom.scan.run':('project_id artifact_id',self._scan_run),
            'projects.trash':('',self._projects_trash),
            'project.delete':('project_id',self._project_delete),
            'project.undelete':('trash_id',self._project_undelete),
            'rom.check':('project_id artifact_id expected_crc32 crc_scope',self._rom_check),
            'tutorial.get':('',lambda p,c:self._tutorial('get',p,c)),
            'tutorial.preferences':('never_ask_again',lambda p,c:self._tutorial('preferences',p,c)),
            'tutorial.progress':('lesson_id outcome',lambda p,c:self._tutorial('progress',p,c)),
            'tutorial.practice':('',lambda p,c:self._tutorial('practice',p,c)),
            'system.ui_ready':('launch_id',lambda p,c:self._ui_startup(p,True)),
            'system.ui_status':('launch_id',lambda p,c:self._ui_startup(p,False)),
            'recipes.list':('project_id artifact_id',self._recipes_list),
            'recipes.from_plan':('project_id artifact_id plan_id name',self._recipe_from_plan),
            'recipes.import':('project_id artifact_id recipe',self._recipe_import),
            'recipes.preview':('project_id artifact_id recipe',self._recipe_preview),
            'recipes.export':('project_id artifact_id recipe',self._recipe_export),
            'definitions.export':('project_id artifact_id kind',self._definition_export),
            'definitions.import':('project_id artifact_id document',self._definition_import),
            'watches.save':('project_id artifact_id watches',self._watches_save),
            'watches.compare':('before after',self._watch_compare),
            'help.list':('query topic',self._help),
            'project.readiness':('project_id',self._readiness),
            'system.capabilities':('',self._capabilities),'system.pick_file':('',self._pick_file),
            'systems.list':('',self._systems_list),'systems.identify':('project_id artifact_id',self._system_identify),
            'systems.reference':('system_id',self._hardware_reference),
            'systems.classify_address':('system_id address domain',self._classify_address),
            'systems.nes_chr':('project_id artifact_id first_tile count',self._nes_chr),
            'project.demo_nes':('',self._demo_nes),
            'project.demo_system':('system_id',self._demo_system),
            'release.disc_set':('project_id source_id target_id title',self._patch_set),
            'release.apply_set':('source_cue archive destination',self._apply_patch_set),
            'drafts.list':('project_id artifact_id',self._draft_list),
            'drafts.get':('project_id artifact_id key',self._draft_get),
            'drafts.save':('project_id artifact_id key revision value',self._draft_save),
            'drafts.move':('project_id artifact_id key revision direction',self._draft_move),
            'project.migrate':('project_id',self._project_migrate),
            'project.backup':('project_id destination roles',self._project_backup),
            'project.restore':('archive',self._project_restore),
            'project.recover_lock':('project_id',self._project_recover),
            'containers.inventory':('project_id artifact_id',self._container_inventory),
            'containers.import_disc':('project_id cue',self._container_import),
            'containers.disc_inventory':('project_id container_id',self._disc_inventory),
            'containers.build_disc':('project_id container_id track offset before after',self._disc_build),
            'containers.extract':('project_id artifact_id offset length',self._container_extract),
            'containers.extract_disc':('project_id container_id offset length',self._disc_extract),
            'containers.reinsert':('project_id artifact_id',self._container_reinsert),
            'systems.plan_edits':('project_id artifact_id edits',self._integrity_plan),
            'compression.inspect':('project_id artifact_id offset allocation codec',self._compression_inspect),
            'compression.extract':('project_id artifact_id offset allocation codec',self._compression_extract),
            'compression.plan_relocate':('project_id parent_id decoded_id edited_id offset allocation codec spec',self._compression_relocate),
            'compression.preview_reinsert':('project_id parent_id decoded_id edited_id offset allocation codec',self._compression_preview),
            'compression.plan_reinsert':('project_id parent_id decoded_id edited_id offset allocation codec',self._compression_reinsert),
            'tables.inspect':('project_id artifact_id definition page limit',self._tables_inspect),
            'tables.save_definition':('project_id artifact_id definition',self._tables_save),
            'tables.plan':('project_id artifact_id definition document_id changes',self._tables_plan),
            'tables.batch':('project_id artifact_id definition field operation value first count',self._tables_batch),
            'resources.discover':('project_id artifact_id config',self._discover_resources),
            'resources.declare_script':('project_id artifact_id config',lambda p,c:self._declare_resource(p,c,'script')),
            'resources.declare_assets':('project_id artifact_id config',lambda p,c:self._declare_resource(p,c,'assets')),
            'resources.export_image':('project_id artifact_id schema bitmap_id columns bank',self._export_image),
            'resources.reuse_definitions':('project_id artifact_id',self._reuse_definitions),
            'resources.address_uses':('project_id artifact_id offset',self._address_uses),
            'resources.references':('project_id artifact_id schema bitmap_id cell_index',self._resource_references),
            'resources.image_map_selection':('project_id artifact_id schema bitmap_id bank png_base64 columns mode',self._image_map),
            'resources.image_map':('project_id artifact_id schema png_base64 columns mode',self._image_map),
            'resources.layout_form':('project_id artifact_id font_artifact_id width height line_height',self._layout_form),
            'resources.menu_form':('project_id artifact_id font_artifact_id width height line_height',self._menu_form),
            'profiles.scan_local':('directories',self._scan_local_cores),
            'profiles.configure_local':('system_id candidate',self._configure_local_core),
            'profiles.get':('system_id',self._profile_get),
            'games.configure':('project_id artifact_id resource_id',self._game_configure),
            'system.agent_config':('allow_writes read_roots',self._agent_config),
            'profiles.save':('system_id core options system_dir input_map',self._profile_save),
            'profiles.controller':('system_id controller_devices',self._profile_controller),
            'profiles.validate':('system_id',self._profile_validate),
            'runtime.smoke_profile':('project_id artifact_id system_id',self._runtime_smoke),
            'runtime.load_profile':('project_id artifact_id system_id',self._runtime_profile),
            'runtime.load_disc':('project_id container_id system_id',self._runtime_disc),
            'runtime.checkpoints':('project_id',self._checkpoints),
            'runtime.export_audio':('project_id',self._export_runtime_audio),
            'runtime.game_saves':('project_id',self._game_saves),
            'runtime.load_game_save':('project_id artifact_id system_id save_id',self._runtime_saved_game),
            'systems.address':('project_id artifact_id system_id address mapping bank',self._system_address),
            'catalog.add':('project_id artifact_id resources',self._catalog_add),
            'catalog.list':('project_id artifact_id query page limit',self._catalog_list),
            'catalog.index':('project_id artifact_id',self._catalog_index),
            'resources.compare':('project_id artifact_id other_id offset length',self._compare_resources),
            'runtime.memory':('project_id region offset length',self._memory_snapshot),
            'projects.list':('',lambda p,c:{'ok':True,'projects':projects.list_projects(self.projects)}),
            'project.create':('name',lambda p,c:projects.create_project(self.projects,p['name'])),
            'project.open':('project_id',lambda p,c:{**projects.read_project(self.project(p)), 'ok':True,'path':str(self.project(p))}),
            'project.demo':('',self._demo),'source.import':('project_id path system',self._import),
            'resource.inspect':('project_id artifact_id offset length',lambda p,c:projects.inspect_resource(self.project(p),p['artifact_id'],p['offset'],p['length'])),
            'bytes.plan':('project_id artifact_id edits',lambda p,c:projects.plan_byte_edits(self.project(p),p['artifact_id'],p['edits'])),
            'build.apply':('project_id plan_id',self._apply_byte_build),
            'script.inspect':('project_id artifact_id schema',self._script_inspect),
            'script.plan':('project_id artifact_id schema edits',lambda p,c:self._structured_plan(p,'script')),
            'assets.inspect':('project_id artifact_id schema',self._assets_inspect),
            'assets.plan':('project_id artifact_id schema edits',lambda p,c:self._structured_plan(p,'assets')),
            'structured.apply':('project_id plan_id',self._structured_apply),
            'font.measure':('project_id artifact_id schema',self._font),
            'layout.check':('project_id artifact_id schema font_artifact_id font_schema policy',lambda p,c:self._layout(p,False)),
            'layout.plan':('project_id artifact_id schema font_artifact_id font_schema policy request',lambda p,c:self._layout(p,True)),
            'menu.inspect':('project_id artifact_id schema profile',self._menu),
            'menu.preview':('project_id artifact_id schema profile cases font_artifact_id font_schema',self._menu_preview),
            'menu.compare':('project_id artifact_id schema profile cases font_artifact_id font_schema request',self._menu_compare),
            'runtime.load':('project_id artifact_id core options',self._runtime_load),
            'runtime.advance':('project_id frames buttons port',lambda p,c:self.runtime.request(self.project(p),'advance',{k:p[k] for k in ('frames','buttons','port')},cancelled=c)),
            'runtime.step':('project_id frames buttons port',lambda p,c:self.runtime.step(self.project(p),p['frames'],p['buttons'],p['port'],cancelled=c)),
            'runtime.capture':('project_id',lambda p,c:self.runtime.request(self.project(p),'capture',{},cancelled=c)),
            'runtime.audio':('project_id',lambda p,c:self.runtime.request(self.project(p),'audio',{},cancelled=c)),
            'runtime.save_state':('project_id',self._save_state),
            'runtime.load_state':('project_id snapshot_id',self._load_state),
            'runtime.save_game':('project_id',self._save_game),
            'runtime.close':('project_id',lambda p,c:self.runtime.close_session(self.project(p))),
            'captures.record':('project_id artifact_id config',self._capture_record),
            'captures.search':('project_id query',self._capture_search),
            'captures.get':('project_id capture_id',self._capture_get),
            'captures.annotate':('project_id capture_id entries',self._capture_annotate),
            'audio.capture':('project_id config baseline format',self._audio_capture),
            'debug.inspect':('project_id artifact_id case trace',lambda p,c:self._debug(p,False)),
            'debug.observe':('project_id artifact_id case trace runtime',lambda p,c:self._debug(p,True,c)),
            'route.run':('project_id artifact_id core options route timeout initial_state',self._route),
            'route.run_profile':('project_id artifact_id system_id route timeout initial_state',self._route),
            'route.run_disc':('project_id container_id system_id route timeout initial_state',self._route),
            'routes.compile':('name steps max_frames max_actions',self._compile_route),
            'routes.list':('project_id',self._list_routes),
            'routes.get':('project_id definition_id',self._get_route),
            'routes.save':('project_id selection system_id route initial_state_id',self._save_route),
            'routes.run_saved':('project_id definition_id selection use_checkpoint timeout',self._run_saved_route),
            'routes.record_start':('project_id system_id name',self._record_route_start),
            'routes.record_capture':('project_id',lambda p,c:self.runtime.record_assertion(self.project(p),'capture',{},cancelled=c)),
            'routes.record_memory':('project_id region offset length',lambda p,c:self.runtime.record_assertion(self.project(p),'memory',{k:p[k] for k in ('region','offset','length')},cancelled=c)),
            'routes.record_stop':('project_id',lambda p,c:self.runtime.stop_recording(self.project(p))),
            'battle.analyze':('profile observations budget',self._battle),
            'coverage.build':('project_id evidence_ids objectives',self._coverage),
            'regression.run_suite':('project_id source_id target_id definition_ids timeout',self._regression_suite),
            'regression.compare':('project_id baseline_id candidate_id',self._regression),
            'regression.bisect':('project_id artifact_id core options route changes budget timeout',self._bisect),
            'regression.bisect_profile':('project_id artifact_id system_id route changes budget timeout',self._bisect),
            'reports.list':('project_id',self._reports),'reports.get':('project_id evidence_id',self._report),
            'docs.script':('project_id document format',self._docs_script),
            'docs.script_from_resource':('project_id artifact_id schema format',self._docs_script_resource),
            'docs.walkthrough':('project_id evidence_id annotations',self._docs_walkthrough),
            'release.prepare':('project_id source_id target_id title description',self._patch),
            'release.verify':('project_id source_id export_id',self._verify_patch),
            'release.package':('project_id export_ids title',self._package),
            'exports.list':('project_id',lambda p,c:{'ok':True,'exports':self.exports(self.project(p))}),
        }
        from .workbench_tools import register_tools
        register_tools(self)
        from .studio_tools import StudioTools
        self.studio=StudioTools(self);self.routes.update(self.studio.routes())
        from .investigation_tools import InvestigationTools
        self.investigations=InvestigationTools(self);self.routes.update(self.investigations.routes())
        from .debugger_tools import DebuggerTools
        self.debugger=DebuggerTools(self);self.routes.update(self.debugger.routes())
        from .structure_tools import StructureTools
        self.structures=StructureTools(self);self.routes.update(self.structures.routes())
        from .research_tools import ResearchTools
        self.research=ResearchTools(self);self.routes.update(self.research.routes())
        from .documented_tables import DocumentedTableTools
        self.documented=DocumentedTableTools(self);self.routes.update(self.documented.routes())
        from .source_symbols import SymbolTools
        self.symbols=SymbolTools(self);self.routes.update(self.symbols.routes())
        from .connected_game import ConnectedGameTools
        self.connected=ConnectedGameTools(self);self.routes.update(self.connected.routes())
        from .gameplay_traces import GameplayTraceTools
        self.traces=GameplayTraceTools(self);self.routes.update(self.traces.routes())
        from .visual_source_tools import VisualSourceTools
        self.visual_sources=VisualSourceTools(self);self.routes.update(self.visual_sources.routes())
        from .object_workbench import ObjectTools
        self.objects=ObjectTools(self);self.routes.update(self.objects.routes())
        from .graphics_access import GraphicsAccessTools
        self.graphics_access=GraphicsAccessTools(self);self.routes.update(self.graphics_access.routes())
        from .build_checks import BuildCheckTools
        self.checks=BuildCheckTools(self);self.routes.update(self.checks.routes())
        from .popular_references import catalog as reference_catalog,inspect_template
        self.routes['references.catalog']=('query system_filter',lambda p,c:reference_catalog(p['query'],p['system_filter']))
        self.routes['references.template']=('project_id artifact_id template_id offset count stride',lambda p,c:inspect_template(self,p,c))
        from .data_relocation import RelocationTools
        self.relocation=RelocationTools(self);self.routes.update(self.relocation.routes())
        for operation in tuple(self.routes):
            if operation.startswith('containers.') or operation in ('runtime.load_disc','route.run_disc','release.disc_set'):
                del self.routes[operation]
        self.jobs=JobManager(self.workspace,self.dispatch,set(self.routes)-{'system.capabilities','systems.list','projects.list','project.open','reports.list','reports.get','exports.list','drafts.list','drafts.get','drafts.save','drafts.move'})
        try:self.runtime=RuntimePool()
        except BaseException:self.jobs.close();raise

    def project(self,parameters):
        project_id=projects.identifier(parameters['project_id']);project=checked_path(self.projects/project_id)
        projects.read_project(project);return project

    def source(self,p):
        project=self.project(p);row=projects.artifact(project,p['artifact_id']);projects._measure(row['path'],row)
        return project,row,Path(row['path'])

    def _game_inspect(self,p,c):
        from .verified_games import inspect
        project,row,path=self.source(p)
        return inspect(project,row,path,cancelled=c)

    def _game_maps(self,p,c,operation):
        from .verified_games import maps
        return maps(self,p,operation,cancelled=c)

    def _cheat_import(self,p,c):
        from .cheat_catalog import import_catalog
        count=import_catalog(self.project(p),p['input_id'],cancelled=c)
        return {'ok':True,'status':'IMPORTED','project_id':p['project_id'],'count':count}

    def _hardware_reference(self,p,c):
        from .hardware_reference import reference_for
        return reference_for(p['system_id'])

    def _classify_address(self,p,c):
        from .hardware_reference import classify_address
        return classify_address(p['system_id'],p['address'],p['domain'])

    def _cheat_catalog(self,p,c):
        from .cheat_catalog import catalog_info
        return catalog_info(self.project(p))

    def _cheat_inspect(self,p,c):
        from .cheat_catalog import inspect_catalog
        project,row,path=self.source(p)
        return inspect_catalog(project,row,path,query=p['query'],page=p['page'],limit=p['limit'],cancelled=c)

    def _engine_inspect(self,p,c):
        from .engine_recognition import recognize_engines
        project,row,path=self.source(p)
        return recognize_engines(path,row['sha256'],row.get('system_id'),cancelled=c)

    def _operations(self,p,c):
        return {'ok':True,'operations':[{'name':name,'required_parameters':entry[0].split()} for name,entry in sorted(self.routes.items())],
                'scope':'Operation names and required parameter names; value constraints are documented per operation.'}

    def _settings_get(self,p,c):
        from .app_settings import get_settings
        return get_settings(self.workspace)

    def _settings_save(self,p,c):
        from .app_settings import save_settings
        return save_settings(self.workspace,p['revision'],p['values'])

    def _settings_workspace_get(self,p,c):
        from .app_settings import get_workspace_location
        return get_workspace_location(self.workspace)

    def _settings_workspace_save(self,p,c):
        from .app_settings import save_workspace_location
        return save_workspace_location(self.workspace,p['location'])

    def _game_plan(self,p,c):
        from .verified_games import plan
        return plan(self,p,cancelled=c)

    def _graphics_observe(self,p,c):
        from .graphics_discovery import match_graphics,MAX_SOURCE_BYTES
        from .workbench_evidence import store_evidence
        from .asset_schema import number
        with self.operation_locks_guard:lock=self.operation_locks.setdefault(p['project_id'],threading.RLock())
        with lock:
            project,row,path=self.source(p)
            offset=number(p['offset'],0,row['size']-1);requested=number(p['length'],1,row['size']-offset)
            if type(p['frame_sha256']) is not str or (p['frame_sha256'] and (len(p['frame_sha256'])!=64 or any(ch not in '0123456789abcdef' for ch in p['frame_sha256']))):raise ValueError('invalid captured frame identity')
            frame=self.runtime.request(project,'capture',{},cancelled=c)
            if frame['game_sha256']!=row['sha256']:raise ValueError('runtime is running a different source; load the selected ROM first')
            if p['frame_sha256'] and p['frame_sha256']!=frame['sha256']:raise ValueError('captured frame changed; pause and select the region again')
            rgb=base64.b64decode(frame['rgb24_base64'],validate=True)
            if len(rgb)!=frame['width']*frame['height']*3 or __import__('hashlib').sha256(rgb).hexdigest()!=frame['sha256']:raise ValueError('captured frame pixels do not match their identity')
        with path.open('rb') as stream:stream.seek(offset);raw=stream.read(min(requested,MAX_SOURCE_BYTES))
        result=match_graphics(raw,rgb,frame['width'],frame['height'],row.get('system_id'),region=p['region'],cancelled=c)
        for match in result['matches']:match['offset']+=offset
        result['coverage'].update(offset=offset,bytes_requested=requested,whole_requested_range=len(raw)==requested and not result['coverage']['matches_truncated'],whole_source=offset==0 and len(raw)==row['size'] and not result['coverage']['matches_truncated'])
        result['coverage']['next_offset']+=offset
        if not result['coverage']['matches_truncated'] and offset+len(raw)<row['size']:
            overlap=max((r['block_bytes'] for r in result['coverage']['source_ranges']),default=1)-1
            result['coverage']['next_offset']=max(offset+1,offset+len(raw)-overlap)
        for segment in result['coverage']['source_ranges']:
            segment.update(offset=segment['offset']+offset,end=segment['end']+offset,requested_end=offset+requested)
        result.update(artifact_id=row['artifact_id'],source_sha256=row['sha256'],source_size=row['size'],
                      frame={k:frame.get(k) for k in ('sha256','width','height','index','core_sha256','game_sha256','runtime_identity_sha256','provenance')},
                      scope='graphics_pixel_candidates',origin='owned_native_frame_analysis')
        with lock:
            if c():raise KeyboardInterrupt
            self.project(p);projects._measure(path,row,cancelled=c)
            evidence=store_evidence(project,'runtime',result)
        return {**result,'evidence_id':evidence['evidence_id']}

    def _graphics_declare(self,p,c):
        from .graphics_discovery import candidate_layout
        from .workbench_evidence import load_evidence
        project,row,path=self.source(p);record=load_evidence(project,p['evidence_id'],'runtime');report=record['report']
        if record.get('runtime_trusted') is False or report.get('scope')!='graphics_pixel_candidates':raise ValueError('run a fresh local gameplay analysis first')
        if report.get('source_sha256')!=row['sha256'] or report.get('artifact_id')!=row['artifact_id']:raise ValueError('graphics candidates belong to a different source')
        view=candidate_layout(report,p['matches'])
        declared=self._declare_resource({'project_id':p['project_id'],'artifact_id':p['artifact_id'],'config':view['config']},c,'assets')
        return {**declared,'layout':view['layout'],'observation_id':p['evidence_id'],'candidate_only':True}

    def _scan_start(self,p,c):
        from .rom_scan import cached
        if type(p['rescan']) is not bool:raise ValueError('rescan must be true or false')
        project,row,path=self.source(p);key=(p['project_id'],p['artifact_id'])
        pending=self.rom_scans.get(key)
        if pending:
            job=self.jobs.get(pending)
            if job['status'] not in ('COMPLETED','FAILED','CANCELLED','INTERRUPTED'):
                return {'ok':True,'status':'RUNNING','job_id':pending,'artifact_id':row['artifact_id']}
        result=None if p['rescan'] else cached(project,row,cancelled=c)
        if result:return {'ok':True,'status':'READY','result':result,'artifact_id':row['artifact_id']}
        job=self.jobs.submit('rom.scan.run',{'project_id':p['project_id'],'artifact_id':p['artifact_id']});self.rom_scans[key]=job['job_id']
        return {'ok':True,'status':'RUNNING','job_id':job['job_id'],'artifact_id':row['artifact_id']}

    def _scan_run(self,p,c):
        from .rom_scan import run
        from .rom_scan import write_cache
        project,row,path=self.source(p)
        with self.operation_locks_guard:lock=self.operation_locks.setdefault(p['project_id'],threading.RLock())
        def publish(result):
            # Only the short publication step holds the normal project lock.
            # Navigation stays available and deletion cannot resurrect a folder.
            with lock:
                if c():raise KeyboardInterrupt
                self.project(p);projects._measure(path,row,cancelled=c)
                write_cache(project,row,result)
        return run(project,row,cancelled=c,publish=publish)

    def invalidate_scans(self,project_id):
        for key,job in list(self.rom_scans.items()):
            if key[0]==project_id:
                self.jobs.cancel(job);self.rom_scans.pop(key,None)

    def _projects_trash(self,p,c):
        from .project_lifecycle import trash_projects
        with self.project_admin_lock:return trash_projects(self.workspace)

    def _project_delete(self,p,c):
        from .project_lifecycle import delete_project
        for key,job in self.rom_scans.items():
            if key[0]==p['project_id']:self.jobs.cancel(job)
        project=self.project(p);self.runtime.close_session(project)
        with self.project_admin_lock:return delete_project(self.workspace,project)

    def _project_undelete(self,p,c):
        from .project_lifecycle import undelete_project
        with self.project_admin_lock:return undelete_project(self.workspace,p['trash_id'])

    def dispatch(self,operation,parameters,cancelled=lambda:False):
        try:
            parameters=snapshot_json(parameters)
            if operation=='jobs.submit':
                fields(parameters,'operation parameters');return {'ok':True,**self.jobs.submit(parameters['operation'],parameters['parameters'])}
            if operation=='jobs.get':fields(parameters,'job_id');return {'ok':True,**self.jobs.get(parameters['job_id'])}
            if operation=='jobs.cancel':fields(parameters,'job_id');return {'ok':True,**self.jobs.cancel(parameters['job_id'])}
            if operation=='jobs.list':fields(parameters,'');return {'ok':True,'jobs':self.jobs.list()}
            if operation not in self.routes:raise ValueError('unknown workbench operation')
            names,handler=self.routes[operation];fields(parameters,names)
            if cancelled():raise KeyboardInterrupt
            if operation in ('rom.scan.run','graphics.observe','traces.capture','traces.verify','checks.run','checks.from_trace','graphics.accesses.capture'):return handler(parameters,cancelled)
            if 'project_id' in parameters:
                project_id=projects.identifier(parameters['project_id'])
                with self.operation_locks_guard:lock=self.operation_locks.setdefault(project_id,threading.RLock())
                with lock:
                    if cancelled():raise KeyboardInterrupt
                    from .release_scope import guard_request
                    guard_request(self,operation,parameters)
                    result=handler(parameters,cancelled)
                    if operation in ('build.apply','structured.apply','patches.apply'):
                        try:
                            if cancelled():result['automatic_check']={'status':'NOT_QUEUED','reason':'Build saved; automatic checks were not started after cancellation.'}
                            else:self.checks.on_build(parameters,result)
                        except (ValueError,OSError,RuntimeError) as error:result['automatic_check']={'status':'NOT_QUEUED','reason':str(error)[:240]}
                    return result
            from .release_scope import guard_request
            guard_request(self,operation,parameters)
            return handler(parameters,cancelled)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError,KeyboardInterrupt) as exc:
            return {'schema_version':1,'operation':operation,'ok':False,'status':'CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED',
                    'error':str(exc)[:1024] or 'Operation cancelled'}

    def _tutorial(self,operation,p,c):
        from . import onboarding
        with self.tutorial_lock:
            if c():raise KeyboardInterrupt
            if operation=='get':return onboarding.tutorial_status(self.workspace)
            if operation=='preferences':return onboarding.set_preferences(self.workspace,p['never_ask_again'])
            if operation=='progress':return onboarding.record_progress(self.workspace,p['lesson_id'],p['outcome'])
            value=onboarding.load_state(self.workspace);project_id=value['practice_project_id']
            if project_id:
                try:
                    project=projects.read_project(self.project({'project_id':project_id}))
                    if project.get('demo') and project.get('demo_system')=='nes' and project.get('name') in ('ROMancer tutorial','Tutorial practice'):
                        return {**project,'ok':True}
                except (ValueError,OSError,KeyError):pass
            project=self._demo_system({'system_id':'nes'},c)
            folder=self.project({'project_id':project['project_id']});project['name']='Tutorial practice'
            projects.write_json(folder/'project.json',project)
            value['practice_project_id']=project['project_id'];onboarding.save_state(self.workspace,value)
            return {**projects.read_project(folder),'ok':True}

    def _ui_startup(self,p,mark):
        launch=p['launch_id']
        if type(launch) is not str or len(launch)!=32 or any(ch not in '0123456789abcdef' for ch in launch):raise ValueError('invalid UI launch identifier')
        now=time.monotonic()
        with self.ui_launch_lock:
            self.ui_launches={key:stamp for key,stamp in self.ui_launches.items() if now-stamp<120}
            if mark:
                self.ui_launches.pop(launch,None);self.ui_launches[launch]=now
                while len(self.ui_launches)>32:self.ui_launches.pop(next(iter(self.ui_launches)))
            return {'ok':True,'scope':'ui_startup','ready':launch in self.ui_launches}

    def _capabilities(self,p,c):
        from .contracts import adapter_inventory
        from .system_registry import system_inventory
        return {'ok':True,'product':'ROMancer','version':ROMANCER_VERSION,'display_version':ROMANCER_BUILD_LABEL,'release_name':ROMANCER_RELEASE_NAME,'build_label':ROMANCER_BUILD_LABEL,'target_version':'1.0','credit':'By RetchEWretched','release_status':'RELEASE',
                'python':platform.python_version(),'platform':platform.system(),'pillow':importlib.util.find_spec('PIL') is not None,
                'native_dialog':os.name=='nt' or importlib.util.find_spec('tkinter') is not None,'adapters':{**adapter_inventory(),'adapters':[a for a in adapter_inventory()['adapters'] if a['id'] in ('nes','snes','genesis','gb','gbc','gba','sms')]},'systems':system_inventory(),
                'runtime_note':'The full Windows release includes engines for all seven systems. Source installations can use compatible local libretro cores. Gameplay evidence applies to the exact ROM and tested setup.'}

    def _agent_config(self,p,c):
        if type(p['allow_writes']) is not bool or type(p['read_roots']) is not list or len(p['read_roots'])>8:raise ValueError('choose agent access and up to eight import folders')
        arguments=['-I','-B',str(Path(__file__).with_name('mcp_server.py').resolve()),'--workspace',str(self.workspace)]
        if p['allow_writes']:arguments.append('--allow-writes')
        for root in p['read_roots']:
            if type(root) is not str or not root or len(root)>4096:raise ValueError('invalid agent import folder')
            directory=checked_path(root)
            if not directory.is_dir():raise ValueError('agent import folder must exist')
            arguments.extend(['--rom-root',str(directory)])
        return {'ok':True,'configuration':{'mcpServers':{'romancer':{'command':sys.executable,'args':arguments}}},'access':'editing' if p['allow_writes'] else 'inspection','note':'Contains local paths. Paste into your local MCP client configuration; it includes no authentication token.'}

    def _help(self,p,c):
        from .help_content import help_topics
        return help_topics(p['query'],p['topic'])

    def _readiness(self,p,c):
        from .help_content import project_readiness
        from .runtime_profiles import load_profile,validate_profile
        from .workbench_evidence import load_evidence
        project=self.project(p);value=projects.read_project(project);exports=self.exports(project)
        configured=False
        for system in {row.get('system_id') for row in value['sources'] if row.get('system_id')}:
            profile=load_profile(self.workspace,system)['profile']
            if profile:
                try:validate_profile(profile);configured=True
                except (ValueError,OSError):pass
        verified=[];rows={row['export_id']:row for row in exports if row['role']=='patch'}
        for file in sorted((project/'reports').glob('*.json'))[:4096]:
            try:
                record=load_evidence(project,file.stem);report=record['report'];row=rows.get(report.get('export_id'))
                if record.get('runtime_trusted') and record['kind']=='release' and report.get('scope')=='patch_verification' and report.get('status')=='VERIFIED' and row and row['sha256']==report.get('patch_sha256'):
                    projects._measure(project/'exports'/row['name'],row);verified.append(row['export_id'])
            except (ValueError,OSError,KeyError):continue
        return project_readiness(value,exports,configured,verified)

    def _systems_list(self,p,c):
        from .system_registry import system_inventory
        return system_inventory()

    def _draft_list(self,p,c):
        from .draft_store import draft_list
        return draft_list(self.project(p),p['artifact_id'])

    def _draft_get(self,p,c):
        from .draft_store import draft_get
        return draft_get(self.project(p),p['artifact_id'],p['key'])

    def _draft_save(self,p,c):
        from .draft_store import draft_update
        return draft_update(self.project(p),p['artifact_id'],p['key'],p['revision'],p['value'])

    def _draft_move(self,p,c):
        from .draft_store import draft_move
        return draft_move(self.project(p),p['artifact_id'],p['key'],p['revision'],p['direction'])

    def _project_migrate(self,p,c):
        from .project_portability import migrate_project
        return migrate_project(self.project(p))

    def _project_backup(self,p,c):
        from .project_portability import backup_project
        return backup_project(self.project(p),Path(p['destination']),p['roles'])

    def _project_restore(self,p,c):
        from .project_portability import restore_project
        return restore_project(Path(p['archive']),self.projects)

    def _project_recover(self,p,c):
        from .project_portability import recover_lock
        return recover_lock(self.project(p))

    def _container_inventory(self,p,c):
        from .container_workspace import inventory_container
        project,row,path=self.source(p)
        return {**inventory_container(path,row['sha256'],cancelled=c),'artifact_id':row['artifact_id']}

    def _container_import(self,p,c):
        from .container_workspace import import_disc_set
        return import_disc_set(self.project(p),Path(p['cue']),cancelled=c)

    def _disc_inventory(self,p,c):
        from .container_workspace import parse_cue,inventory_container
        project=self.project(p);projects.identifier(p['container_id'])
        record=next((r for r in projects.read_project(project).get('containers',[]) if r['container_id']==p['container_id']),None)
        if record is None:raise ValueError('unknown owned disc set')
        folder=checked_path(project/'containers'/p['container_id']);actual=parse_cue(folder/record['cue'])
        if actual['members']!=record['members'] or actual['tracks']!=record['tracks']:raise ValueError('disc set changed')
        track=actual['tracks'][0];member=next(m for m in actual['members'] if m['name']==track['file'])
        return {'ok':True,**record,'inventory':inventory_container(folder/track['file'],member['sha256'],cancelled=c)}

    def _disc_build(self,p,c):
        from .container_workspace import build_disc_set
        return build_disc_set(self.project(p),p['container_id'],p['track'],p['offset'],bytes.fromhex(p['after']),expected_before=bytes.fromhex(p['before']),cancelled=c)

    def _container_extract(self,p,c):
        from .container_workspace import inventory_container,extract_extent
        project,row,path=self.source(p);inventory=inventory_container(path,row['sha256'],cancelled=c)
        if not any(f['offset']<=p['offset'] and p['offset']+p['length']<=f['offset']+f['length'] for f in inventory['files']):raise ValueError('extraction must fit an inventoried file')
        raw=extract_extent(path,row['sha256'],p['offset'],p['length'],layout=inventory['layout'])
        parent={'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'offset':p['offset'],'length':p['length'],'layout':inventory['layout']}
        return self._store_extracted(project,raw,row['system'],parent,c)

    def _store_extracted(self,project,raw,system,parent,c):
        temp=self.incoming/(uuid.uuid4().hex+'.resource')
        try:
            temp.write_bytes(raw);result=projects.register_source(project,temp,system,cancelled=c)
            with projects.locked(project) as value:
                owned=next(r for r in value['sources'] if r['artifact_id']==result['artifact_id'])
                owned['container_parent']=parent
                result['container_parent']=owned['container_parent'];projects.write_json(project/'project.json',value)
            return result
        finally:temp.unlink(missing_ok=True)

    def _disc_extract(self,p,c):
        from .container_workspace import extract_extent
        project=self.project(p);disc=self._disc_inventory({'project_id':p['project_id'],'container_id':p['container_id']},c)
        if not any(f['offset']<=p['offset'] and p['offset']+p['length']<=f['offset']+f['length'] for f in disc['inventory']['files']):raise ValueError('extraction must fit one inventoried file')
        track=disc['tracks'][0];member=next(m for m in disc['members'] if m['name']==track['file']);source=checked_path(project/'containers'/p['container_id']/track['file'])
        raw=extract_extent(source,member['sha256'],p['offset'],p['length'],layout=disc['inventory']['layout'])
        parent={'container_id':p['container_id'],'track':track['number'],'source_sha256':member['sha256'],'offset':p['offset'],'length':p['length'],'layout':disc['inventory']['layout']}
        return self._store_extracted(project,raw,'Sega CD',parent,c)

    def _container_reinsert(self,p,c):
        from .container_workspace import build_container,build_disc_set,extract_extent
        project,row,path=self.source(p);parent=row.get('container_parent')
        if not parent or row['size']!=parent['length']:raise ValueError('select a same-size resource build extracted from a container')
        if 'container_id' in parent:
            disc=self._disc_inventory({'project_id':p['project_id'],'container_id':parent['container_id']},c)
            track=next(t for t in disc['tracks'] if t['number']==parent['track']);source=checked_path(project/'containers'/parent['container_id']/track['file'])
            before=extract_extent(source,parent['source_sha256'],parent['offset'],parent['length'],layout=parent['layout'])
            return build_disc_set(project,parent['container_id'],parent['track'],parent['offset'],path.read_bytes(),expected_before=before,cancelled=c)
        original=projects.artifact(project,parent['artifact_id'])
        if original['sha256']!=parent['source_sha256']:raise ValueError('parent container revision changed')
        before=extract_extent(Path(original['path']),original['sha256'],parent['offset'],parent['length'],layout=parent['layout'])
        destination=project/'builds'/(uuid.uuid4().hex+Path(original['path']).suffix)
        with projects.locked(project) as value:
            build_container(Path(original['path']),original['sha256'],destination,parent['offset'],path.read_bytes(),layout=parent['layout'],expected_before=before,cancelled=c)
            measured=projects._measure(destination)
            from .history import register_build
            registered=register_build(project,{'inputs':[{'role':'original','path':original['path']},{'role':'resource','path':row['path']}],'output':str(destination),'adapter':{'name':'container-insert','version':'1'},'profile':{'name':'declared-extent','version':'1'},'settings':parent},project)
            record={'artifact_id':uuid.uuid4().hex,'name':'Container build '+str(len(value['builds'])+1),'kind':'build','path':str(destination),'system':original['system'],'system_id':original.get('system_id'),**measured,'source_id':original['artifact_id'],'resource_id':row['artifact_id'],'build_id':registered['build_id']}
            value['builds'].append(record);projects.write_json(project/'project.json',value)
        return {'ok':True,'status':'BUILT',**record,'independent_container_check':True}

    def _integrity_plan(self,p,c,*,annotations=None):
        from .system_integrity import integrity_edits
        project,row,path=self.source(p)
        from .system_identify import identify_system
        system=identify_system(path,expected_sha256=row['sha256'],cancelled=c)['system_id']
        edits=integrity_edits(path,row['sha256'],system,p['edits'])
        result=projects.plan_byte_edits(project,row['artifact_id'],edits,annotations=annotations)
        return {**result,'system_id':system,'integrity_planned':True,'integrity_edit_count':len(edits)-len(p['edits'])}

    def _compression_inspect(self,p,c):
        from .resource_compression import inspect_compressed
        project,row,path=self.source(p)
        return inspect_compressed(path,row['sha256'],p['offset'],p['allocation'],p['codec'],cancelled=c)

    def _compression_extract(self,p,c):
        from .resource_compression import inspect_compressed
        project,parent,path=self.source(p)
        inspected=inspect_compressed(path,parent['sha256'],p['offset'],p['allocation'],p['codec'],include_data=True,cancelled=c)
        raw=inspected.pop('decoded_data');temp=self.incoming/(uuid.uuid4().hex+'.resource')
        try:
            temp.write_bytes(raw);child=projects.register_source(project,temp,None,cancelled=c)
            metadata={'parent_id':parent['artifact_id'],'parent_sha256':parent['sha256'],'offset':p['offset'],'allocation':p['allocation'],'codec':p['codec'],
                      'decoded_sha256':inspected['decoded_sha256'],'stream_sha256':inspected['stream_sha256'],'consumed':inspected['consumed']}
            with projects.locked(project) as value:
                projects._measure(path,parent,cancelled=c)
                owned=next(row for row in value['sources'] if row['artifact_id']==child['artifact_id'])
                owned['compressed_parent']=metadata;owned['system_hint']=parent.get('system_id') or parent.get('system_hint')
                owned['name']='Decoded '+p['codec']+' at0x'+format(p['offset'],'x')
                projects.write_json(project/'project.json',value)
            return {'ok':True,'status':'EXTRACTED','artifact':projects.artifact(project,child['artifact_id']),'inspection':inspected}
        finally:temp.unlink(missing_ok=True)

    def _compression_relocate(self,p,c):
        from .resource_compression import prepare_reinsert
        from .data_relocation import prepare_edits
        from .workbench_files import read_bounded
        project=self.project(p)
        parent,edited,packed,summary=prepare_reinsert(project,p['parent_id'],p['decoded_id'],p['edited_id'],p['offset'],p['allocation'],p['codec'],cancelled=c)
        spec=p['spec']
        if type(spec) is not dict or spec.get('source_offset')!=p['offset'] or spec.get('source_length')!=summary['original_stored_size'] or spec.get('replacement_input_id') is not None:
            raise ValueError('Relocation must move this confirmed stream, without an external replacement.')
        if any(type(r) is not dict or r.get('target_delta')!=0 for r in spec.get('references',[])):
            raise ValueError('Compressed streams require references to the stream start; interior pointers are unavailable.')
        raw=read_bounded(Path(parent['path']),64*1024**2,parent,cancelled=c)
        prepared=prepare_edits(raw,parent['system_id'],spec,packed,cancelled=c)
        return {**self._integrity_plan({'project_id':p['project_id'],'artifact_id':parent['artifact_id'],'edits':prepared['edits']},c,
            annotations={'kind':'declared-data-relocation-v1',**prepared['relocation'],'compression':summary}),
            'relocation':prepared['relocation'],'compression':summary}

    def _compression_preview(self,p,c):
        from .resource_compression import preview_reinsert
        return preview_reinsert(self.project(p),p['parent_id'],p['decoded_id'],p['edited_id'],p['offset'],p['allocation'],p['codec'],cancelled=c)

    def _compression_reinsert(self,p,c):
        from .resource_compression import plan_reinsert
        return plan_reinsert(self.project(p),p['parent_id'],p['decoded_id'],p['edited_id'],p['offset'],p['allocation'],p['codec'],cancelled=c)

    def _tables_inspect(self,p,c):
        from .data_tables import inspect_table
        project,row,path=self.source(p)
        return inspect_table(path,row['sha256'],p['definition'],p['page'],p['limit'])

    def _tables_save(self,p,c):
        from .data_tables import inspect_table
        project,row,path=self.source(p);inspection=inspect_table(path,row['sha256'],p['definition'],0,50)
        with projects.locked(project) as value:
            projects._measure(path,row,cancelled=c)
            owned=next(item for item in value['sources']+value['builds'] if item['artifact_id']==row['artifact_id'])
            owned.setdefault('descriptors',{})['tables']={'source_sha256':row['sha256'],'definition':inspection['definition']}
            projects.write_json(project/'project.json',value)
        return {'ok':True,'status':'DECLARED','inspection':inspection}

    def _tables_plan(self,p,c):
        from .data_tables import inspect_table,table_edits
        project,row,path=self.source(p);inspection=inspect_table(path,row['sha256'],p['definition'],0,1)
        if p['document_id']!=inspection['document_id']:raise ValueError('table definition or source changed; inspect it again')
        edits=table_edits(path,row['sha256'],p['definition'],p['changes'])
        if row.get('system_id') in ('nes','snes','genesis','gb','gbc','gba','sms'):
            return self._integrity_plan({'project_id':p['project_id'],'artifact_id':p['artifact_id'],'edits':edits},c)
        return projects.plan_byte_edits(project,row['artifact_id'],edits)

    def _tables_batch(self,p,c):
        from .data_tables import batch_changes,inspect_table
        project,row,path=self.source(p);inspection=inspect_table(path,row['sha256'],p['definition'],0,1)
        changes=batch_changes(path,row['sha256'],p['definition'],p['field'],p['operation'],p['value'],p['first'],p['count'])
        return {'ok':True,'status':'PREVIEW','document_id':inspection['document_id'],'changes':changes}

    def _discover_resources(self,p,c):
        from .resource_discovery import discover
        project,row,path=self.source(p);config=p['config']
        fields(config,'system_id start length kinds target')
        if row.get('system_id') and config['system_id']!=row['system_id']:raise ValueError('choose the identified source system for discovery')
        return discover(path,row['sha256'],config['system_id'],config['start'],config['length'],config['kinds'],target=config['target'],cancelled=c)

    def _declare_resource(self,p,c,kind):
        from .resource_forms import script_schema,graphics_schema,font_schema_from_assets
        project,row,path=self.source(p)
        if row.get('system_id')=='segacd' and not row.get('container_parent'):raise ValueError('extract a disc file before declaring flat resources')
        schema=(script_schema if kind=='script' else graphics_schema)(path,row['sha256'],p['config'])
        if kind=='script':
            from .script import inspect_script
            inspected=inspect_script(path,schema)
        else:
            from .assets import inspect_assets
            inspected=inspect_assets(path,schema)
        if not inspected['ok']:return inspected
        with projects.locked(project) as value:
            projects._measure(path,row,cancelled=c)
            owned=next(r for r in value['sources']+value['builds'] if r['artifact_id']==row['artifact_id'])
            owned.setdefault('descriptors',{})[kind]=schema
            if kind=='assets' and schema['fonts']:owned['descriptors']['font']=font_schema_from_assets(schema)
            projects.write_json(project/'project.json',value)
        return {'ok':True,'status':'DECLARED','schema':schema,'inspection':inspected,'artifact_id':row['artifact_id']}

    def _export_image(self,p,c):
        from .resource_exports import export_tile_sheet
        from .release import publish_bytes
        project,row,path=self.source(p);result=export_tile_sheet(path,p['schema'],p['bitmap_id'],p['columns'],p['bank'])
        target=self._export_path(project,'png');publish_bytes(target,result.pop('png'));result['export']=self._record_export(project,target,'image')
        return result

    def _reuse_definitions(self,p,c):
        import copy
        from .workflow_recipes import definition_document
        project,row,path=self.source(p)
        context=row.get('plan_annotations')
        if isinstance(context,dict) and context.get('kind')=='declared-data-relocation-v1':
            raise ValueError('Data moved to new offsets. Inspect the relocation evidence and declare resources at their current locations; old fixed-offset definitions are not reused.')
        if not row.get('source_id'):raise ValueError('select a build with an owned parent source')
        parent=projects.artifact(project,row['source_id']);projects._measure(parent['path'],parent);definitions={};issues=[]
        for kind,definition in parent.get('descriptors',{}).items():
            if kind not in ('script','assets','tables','levels','sound') or kind in row.get('descriptors',{}):continue
            definition=copy.deepcopy(definition)
            if kind in ('levels','sound'):
                if definition.get('source_sha256')!=parent['sha256']:continue
                definition['source_sha256']=row['sha256']
                try:
                    from .workbench_files import read_bounded
                    raw=read_bounded(path,64*1024**2,row,cancelled=c)
                    if kind=='levels':
                        from .level_design import inspect_level
                        inspect_level(raw,definition,row['sha256'])
                    else:
                        from .sound_studio import inspect_sound
                        inspect_sound(raw,definition,row['sha256'])
                    definitions[kind]=definition
                except ValueError as error:issues.append({'kind':kind,'reason':str(error)})
                continue
            if kind=='script':
                if parent['sha256'] not in definition['profile']['accepted_sha256']:continue
                definition['profile']['accepted_sha256']=[row['sha256']]
                with path.open('rb') as stream:
                    for rule in definition['profile']['rules']:
                        stream.seek(rule['offset']);rule['expected_hex']=stream.read(rule['length']).hex()
            elif kind=='assets':
                if definition['source']['sha256']!=parent['sha256']:continue
                definition['source']={'sha256':row['sha256'],'size':row['size']}
            else:
                if definition['source_sha256']!=parent['sha256']:continue
                definition=definition['definition']
            try:definitions[kind]=definition_document(path,row['sha256'],kind,definition)['definition']
            except ValueError as error:issues.append({'kind':kind,'reason':str(error)})
        with projects.locked(project) as value:
            projects._measure(path,row,cancelled=c);owned=next(r for r in value['builds'] if r['artifact_id']==row['artifact_id']);saved=owned.setdefault('descriptors',{})
            for kind,definition in definitions.items():saved[kind]={'source_sha256':row['sha256'],'definition':definition} if kind=='tables' else definition
            if 'assets' in definitions and definitions['assets']['fonts']:
                from .resource_forms import font_schema_from_assets
                saved['font']=font_schema_from_assets(definitions['assets'])
            projects.write_json(project/'project.json',value)
        return {'ok':True,'status':'RECHECKED','reused':list(definitions),'issues':issues,'note':'Same declared offsets, re-read against current build bytes.'}

    def _address_uses(self,p,c):
        from .resource_exports import declared_address_uses
        project,row,path=self.source(p)
        return declared_address_uses(path,row['sha256'],row.get('descriptors',{}),p['offset'])

    def _resource_references(self,p,c):
        from .resource_exports import declared_usage
        project,row,path=self.source(p);document=self._assets_inspect(p,c)
        if not document.get('ok'):return document
        return declared_usage(document,p['bitmap_id'],p['cell_index'])

    def _image_map(self,p,c):
        from .resource_forms import image_to_cells
        project,row,path=self.source(p)
        from .assets import inspect_assets
        document=inspect_assets(path,p['schema'])
        if not document['ok']:return document
        bitmap=next((bitmap for bitmap in document['bitmaps'] if bitmap['id']==p.get('bitmap_id',document['bitmaps'][0]['id'])),None)
        if bitmap is None:raise ValueError('choose a declared bitmap for PNG import')
        palette=next((r for r in document['palettes'] if r['id']==bitmap['palette_id']),None)
        from .asset_schema import number
        bank=number(p.get('bank',0),0,palette['banks']-1 if palette else 0)
        from .asset_codecs import CODECS
        count=1<<CODECS[bitmap['codec']]
        colors=[e['rgb'] for e in palette['entries'][bank*palette['colors_per_bank']:bank*palette['colors_per_bank']+count]] if palette else [{'r':round(18+i/(count-1)*216),'g':round(18+i/(count-1)*216),'b':round(18+i/(count-1)*216)} for i in range(count)]
        if type(p['png_base64']) is not str or len(p['png_base64'])>700000:raise ValueError('PNG mapping exceeds budget')
        try:raw=base64.b64decode(p['png_base64'],validate=True)
        except ValueError:raise ValueError('invalid PNG encoding') from None
        mapped=image_to_cells(raw,bitmap['width'],bitmap['height'],bitmap['count'],p['columns'],colors,p['mode'])
        changes=[{'kind':'cell','bitmap_id':bitmap['id'],'cell_index':i,'before_pixels':cell['pixels'],'after_pixels':mapped['cells'][i]} for i,cell in enumerate(bitmap['cells']) if cell['pixels']!=mapped['cells'][i]]
        return {**{k:v for k,v in mapped.items() if k!='cells'},'document_id':document['document_id'],'changes':changes,'palette_rgb':colors,'status':'MAPPED'}

    def _layout_form(self,p,c):
        from .resource_forms import layout_policy
        from .script import inspect_script
        project,row,path=self.source(p);schema=row.get('descriptors',projects.read_project(project).get('descriptors',{})).get('script')
        font_row=projects.artifact(project,p['font_artifact_id']);font=font_row.get('descriptors',{}).get('font')
        if not schema or not font:raise ValueError('declare text and a measured mono font first')
        document=inspect_script(path,schema)
        if not document['ok']:return document
        policy=layout_policy(document,schema,font,p['width'],p['height'],p['line_height'])
        return {'ok':True,'font_artifact_id':font_row['artifact_id'],'font_schema':font,'policy':policy,'request':{},'status':'CONFIGURED'}

    def _menu_form(self,p,c):
        from .resource_forms import menu_configuration
        project,row,path=self.source(p);schema=row.get('descriptors',projects.read_project(project).get('descriptors',{})).get('script')
        font_row=projects.artifact(project,p['font_artifact_id']);font=font_row.get('descriptors',{}).get('font')
        if not schema or not font:raise ValueError('declare text and a mono font first')
        result=menu_configuration(schema,font,p['width'],p['height'],p['line_height'])
        return {'ok':True,**result,'font_artifact_id':font_row['artifact_id'],'font_schema':font,'request':{},'status':'CONFIGURED'}

    def _scan_local_cores(self,p,c):
        from .runtime_library import scan_core_library
        directories=p['directories'] or [str(self.workspace.parent/'cores')]
        return scan_core_library(self.workspace,directories)

    def _configure_local_core(self,p,c):
        from .runtime_library import configure_local_core
        with self.profile_lock:return configure_local_core(self.workspace,p['system_id'],p['candidate'])

    def _recipes_list(self,p,c):
        project,row,path=self.source(p)
        return {'ok':True,'recipes':row.get('recipes',[])}

    def _recipe_import(self,p,c):
        from .workflow_recipes import preview_recipe,validate_recipe
        project,row,path=self.source(p);preview_recipe(path,p['recipe'],cancelled=c);recipe=validate_recipe(p['recipe'])
        with projects.locked(project) as value:
            projects._measure(path,row,cancelled=c);owned=next(r for r in value['sources']+value['builds'] if r['artifact_id']==row['artifact_id'])
            saved=owned.setdefault('recipes',[])
            if recipe not in saved:
                if len(saved)>=16:raise ValueError('this source already has16 saved recipes')
                saved.append(recipe)
            projects.write_json(project/'project.json',value)
        return {'ok':True,'status':'SAVED','recipe':recipe}

    def _recipe_preview(self,p,c):
        from .workflow_recipes import preview_recipe
        project,row,path=self.source(p);preview=preview_recipe(path,p['recipe'],cancelled=c)
        if c():raise KeyboardInterrupt
        planned=self._integrity_plan({**p,'edits':preview['edits']},c) if row.get('system_id') in ('nes','snes','genesis','gb','gbc','gba','sms') else projects.plan_byte_edits(project,row['artifact_id'],preview['edits'])
        return {**planned,'recipe_id':preview['recipe_id']}

    def _recipe_export(self,p,c):
        from .workflow_recipes import preview_recipe,validate_recipe
        project,row,path=self.source(p);preview_recipe(path,p['recipe'],cancelled=c);recipe=validate_recipe(p['recipe'])
        if c():raise KeyboardInterrupt
        return self._export_declaration(project,recipe,c)

    def _export_declaration(self,project,document,cancelled=lambda:False):
        from .release import publish_bytes
        from .script_schema import canonical_bytes
        path=self._export_path(project,'json');publish_bytes(path,canonical_bytes(document,max_bytes=1024**2),cancelled=cancelled)
        return {'ok':True,'status':'EXPORTED','export':self._record_export(project,path,'definition')}

    def _recipe_from_plan(self,p,c):
        project,row,path=self.source(p);plan_id=projects.identifier(p['plan_id']);plan=load_script_json(project/'plans'/(plan_id+'.json'),max_bytes=8*1024**2)
        if plan.get('operation')=='byte-build':
            check=dict(plan);check.pop('plan_id',None)
            if digest(check)!=plan_id or plan['source_id']!=row['artifact_id'] or plan['source_sha256']!=row['sha256']:raise ValueError('plan belongs to another source or changed')
            edits=plan['edits']
        else:
            if digest(plan)!=plan_id or plan['artifact_id']!=row['artifact_id']:raise ValueError('plan belongs to another source or changed')
            result=self._structured_plan({**p,'schema':plan['schema'],'edits':plan['edits']},plan['kind'])
            if not result.get('ok'):raise ValueError('review a valid structured plan first')
            edits=[{'offset':r['offset'],'before':r['before_hex'],'after':r['after_hex']} for r in result['hunks']]
        # Remove automatic checksum ranges; every replay recomputes obligations.
        from .workflow_recipes import omit_checksum_ranges
        edits=omit_checksum_ranges(path,row.get('system_id'),edits)
        recipe={'format':'romancer-recipe-v1','name':p['name'],'source':{'sha256':row['sha256'],'size':row['size']},'operations':[{'kind':'bytes',**edit} for edit in edits]}
        return self._recipe_import({**p,'recipe':recipe},c)

    def _definition_export(self,p,c):
        from .workflow_recipes import definition_document
        project,row,path=self.source(p);kind=p['kind'];definition=row.get('descriptors',{}).get(kind)
        if not definition:raise ValueError('declare this resource on the selected source first')
        if kind=='tables':definition=definition['definition']
        return self._export_declaration(project,definition_document(path,row['sha256'],kind,definition))

    def _definition_import(self,p,c):
        from .workflow_recipes import import_definition
        project,row,path=self.source(p);document=import_definition(path,row['sha256'],p['document']);kind=document['kind'];definition=document['definition']
        with projects.locked(project) as value:
            projects._measure(path,row,cancelled=c);owned=next(r for r in value['sources']+value['builds'] if r['artifact_id']==row['artifact_id'])
            owned.setdefault('descriptors',{})[kind]={'source_sha256':row['sha256'],'definition':definition} if kind=='tables' else definition
            if kind=='assets' and definition['fonts']:
                from .resource_forms import font_schema_from_assets
                owned['descriptors']['font']=font_schema_from_assets(definition)
            projects.write_json(project/'project.json',value)
        return {'ok':True,'status':'DECLARED','kind':kind}

    def _watches_save(self,p,c):
        from .memory_watches import validate_watches
        project,row,path=self.source(p);watches=validate_watches(p['watches'])
        with projects.locked(project) as value:
            projects._measure(path,row,cancelled=c);owned=next(r for r in value['sources']+value['builds'] if r['artifact_id']==row['artifact_id'])
            owned.setdefault('descriptors',{})['watches']={'source_sha256':row['sha256'],'watches':watches};projects.write_json(project/'project.json',value)
        return {'ok':True,'status':'SAVED','watches':watches}

    def _watch_compare(self,p,c):
        from .memory_watches import compare_watch
        return compare_watch(p['before'],p['after'])

    def _profile_get(self,p,c):
        from .runtime_profiles import load_profile
        return load_profile(self.workspace,p['system_id'])

    def _game_configure(self,p,c):
        from .verified_games import configure_resource
        return configure_resource(self,p,cancelled=c)

    def _profile_save(self,p,c):
        from .runtime_profiles import save_profile
        with self.profile_lock:return save_profile(self.workspace,p['system_id'],p['core'],p['options'],p['system_dir'],p['input_map'])

    def _profile_validate(self,p,c):
        from .runtime_profiles import validate_profile,load_profile
        profile=load_profile(self.workspace,p['system_id'])['profile']
        if profile is None:raise ValueError('configure this system first')
        return validate_profile(profile)

    def _profile_controller(self,p,c):
        from .runtime_profiles import save_profile,load_profile,validate_profile
        from .controller_devices import validate_devices
        devices=validate_devices(p['controller_devices'])
        with self.profile_lock:
            profile=load_profile(self.workspace,p['system_id'])['profile']
            if profile is None:raise ValueError('load a compatible engine setup first')
            validate_profile(profile)
            return save_profile(self.workspace,p['system_id'],profile['core'],profile['options'],profile['system_dir'],profile['input_map'],controller_devices=devices)

    def _profile_load_config(self,system_id):
        checked=self._profile_validate({'system_id':system_id},lambda:False)
        result={k:checked[k] for k in ('core','expected_core_sha256','core_options','system_dir','system_files')}
        if checked.get('controller_devices'):result['controller_devices']=checked['controller_devices']
        return result

    def _runtime_smoke(self,p,c):
        from .runtime_session import OwnedRuntime,preflight_load
        from .workbench_evidence import store_evidence
        import hashlib
        project,row,path=self.source(p)
        if row.get('system_id') not in ('nes','snes','genesis','gb','gbc','gba','sms') or row['system_id']!=p['system_id']:raise ValueError('select an identified cartridge and its matching saved system setup')
        checked=self._profile_load_config(p['system_id']);config={**checked,'game':str(path),'expected_game_sha256':row['sha256'],'session_dir':str(project/'sessions'/('check-'+uuid.uuid4().hex))}
        load=preflight_load(config,project)
        with OwnedRuntime(load,30,cancelled=c) as runtime:
            runtime.request('advance', frames=120, buttons=[], port=0);frame=runtime.request('capture');audio=runtime.request('audio')
            rgb=base64.b64decode(frame['rgb24_base64'],validate=True);pcm=base64.b64decode(audio['pcm_s16le_base64'],validate=True)
            if len(rgb)!=frame['width']*frame['height']*3 or hashlib.sha256(rgb).hexdigest()!=frame['sha256']:raise ValueError('ROM check video identity differs')
            if len(pcm)!=audio['captured_frames']*4:raise ValueError('ROM check audio sample count differs')
            runtime.close_verified()
            result={'ok':True,'status':'OBSERVED','scope':'rom_smoke_check','source_sha256':row['sha256'],'core_sha256':checked['expected_core_sha256'],
                'frames_advanced':120,'frame':{k:frame[k] for k in ('width','height','sha256')},
                'audio':{k:audio[k] for k in ('observed','complete','sample_rate','captured_frames')},'worker_exit_code':runtime.exit_code,
                'gameplay_verified':False,'note':'Startup observations only. A regression pass requires a route and expected results.'}
            result['audio']['sample_bytes_nonzero']=any(pcm)
        projects._measure(path,row,cancelled=c);result['evidence_id']=store_evidence(project,'runtime',result)['evidence_id'];return result

    def _runtime_profile(self,p,c):
        project,row,path=self.source(p)
        if row.get('system_id') and row['system_id']!=p['system_id']:raise ValueError('selected system differs from source identification')
        config=self._profile_load_config(p['system_id'])
        return self.runtime.load(project,row['artifact_id'],config['core'],config['core_options'],configuration=config,cancelled=c)

    def _runtime_saved_game(self,p,c):
        project,row,path=self.source(p);save_id=projects.identifier(p['save_id']);snapshot=load_script_json(project/'sessions'/(save_id+'.json'),max_bytes=12*1024**2)
        if 'save_ram_base64' not in snapshot:raise ValueError('choose a captured game-save record')
        config=self._profile_load_config(p['system_id']);config['game_save']=snapshot
        return self.runtime.load(project,row['artifact_id'],config['core'],config['core_options'],configuration=config,cancelled=c)

    def _runtime_disc(self,p,c):
        if p['system_id']!='segacd':raise ValueError('disc sets require a Sega CD profile')
        project=self.project(p);disc=self._disc_inventory({'project_id':p['project_id'],'container_id':p['container_id']},c)
        folder=checked_path(project/'containers'/p['container_id']);cue=next(m for m in disc['members'] if m['name']==disc['cue'])
        row={'artifact_id':p['container_id'],'path':str(folder/disc['cue']),**cue}
        config=self._profile_load_config('segacd');config['game_dependencies']=[{'source':str(folder/m['name']),'relative':m['name'],'expected_sha256':m['sha256']} for m in disc['members'] if m['name']!=disc['cue']]
        return self.runtime.load(project,p['container_id'],config['core'],config['core_options'],configuration=config,selection=row,cancelled=c)

    def _checkpoints(self,p,c):
        project=self.project(p);result=[]
        for path in sorted((project/'sessions').glob('*.json'))[-128:]:
            if path.stat().st_size>12*1024**2:continue
            value=load_script_json(path,max_bytes=12*1024**2)
            if 'state_base64' in value:result.append({'snapshot_id':path.stem,'created_utc':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(timespec='seconds'),**{k:value.get(k) for k in ('sha256','core_sha256','game_sha256','runtime_identity_sha256','run_mode')}})
        return {'ok':True,'checkpoints':sorted(result,key=lambda row:row['created_utc'])}

    def _export_runtime_audio(self,p,c):
        from .audio_export import publish_pcm
        project=self.project(p);raw,record=self.runtime.audio_snapshot(project);path=self._export_path(project,'wav')
        rate=record['sample_rate']
        if type(rate) not in (int,float) or int(rate)!=rate:raise ValueError('WAV requires an integral sample rate')
        result=publish_pcm(raw,path,int(rate),'wav')
        result.update(ok=True,status='EXPORTED',capture_origin='owned_native_worker',runtime_identity_sha256=record.get('runtime_identity_sha256'),sample_frames=len(raw)//4,timing_status='NOT_ASSERTED')
        result['export']=self._record_export(project,path,'audio',result);return result

    def _save_game(self,p,c):
        project=self.project(p);snapshot=self.runtime.request(project,'save_game',{},cancelled=c);save_id=uuid.uuid4().hex
        projects.write_json(project/'sessions'/(save_id+'.json'),snapshot,max_bytes=12*1024**2)
        return {k:v for k,v in snapshot.items() if k!='save_ram_base64'}|{'save_id':save_id,'status':'CAPTURED'}

    def _game_saves(self,p,c):
        project=self.project(p);result=[]
        for path in sorted((project/'sessions').glob('*.json'))[-128:]:
            value=load_script_json(path,max_bytes=12*1024**2)
            if 'save_ram_base64' in value:result.append({'save_id':path.stem,**{k:value.get(k) for k in ('sha256','core_sha256','game_sha256','run_mode')}})
        return {'ok':True,'saves':result}

    def _system_address(self,p,c):
        from .system_addresses import inspect_address
        project,row,path=self.source(p)
        from .system_identify import identify_system
        assessment=identify_system(path,expected_sha256=row['sha256'],cancelled=c)
        if assessment['system_id'] and assessment['system_id']!=p['system_id']:raise ValueError('mapping system differs from identified source')
        if assessment['system_id']=='nes':
            candidate=assessment['candidates'][0];prg=next(r for r in assessment['regions'] if r['id']=='prg-rom');mapping=p['mapping']
            if mapping.get('prg_offset')!=prg['offset']:raise ValueError('mapping PRG offset differs from validated header')
            if mapping.get('id')=='nrom' and (candidate['metadata']['mapper']!=0 or mapping.get('prg_size')!=prg['length']):raise ValueError('NROM declaration differs from actual mapper/PRG layout')
            if mapping.get('id')=='prg-bank' and p['bank'] is not None and (p['bank']+1)*mapping['bank_size']>prg['length']:raise ValueError('bank exceeds declared PRG-ROM')
        if assessment['system_id']=='snes' and not any(candidate['format']==p['mapping'].get('id') and candidate['metadata']['copier_header_bytes']==p['mapping'].get('copier_header') for candidate in assessment['candidates']):raise ValueError('mapping differs from supported header candidates')
        return inspect_address(project,row['artifact_id'],p['system_id'],p['address'],p['mapping'],p['bank'])

    def _catalog_add(self,p,c):
        from .resource_catalog import add_resources
        return add_resources(self.project(p),p['artifact_id'],p['resources'])

    def _catalog_list(self,p,c):
        from .resource_catalog import list_resources
        return list_resources(self.project(p),p['artifact_id'],p['query'],p['page'],p['limit'])

    def _catalog_index(self,p,c):
        from .resource_catalog import index_declared
        return index_declared(self.project(p),p['artifact_id'])

    def _compare_resources(self,p,c):
        from .system_addresses import compare_bytes
        return compare_bytes(self.project(p),p['artifact_id'],p['other_id'],p['offset'],p['length'])

    def _memory_snapshot(self,p,c):
        project=self.project(p);result=self.runtime.request(project,'read_memory',{'region':p['region'],'offset':p['offset'],'length':p['length']},cancelled=c)
        from .workbench_evidence import store_evidence
        evidence=store_evidence(project,'runtime',{'scope':'native_memory_snapshot','origin':'owned_native_worker',**result})
        return {**result,'evidence_id':evidence['evidence_id']}

    def _rom_check(self,p,c):
        from .rom_health import check_rom
        row=projects.artifact(self.project(p),p['artifact_id'])
        return {**check_rom(Path(row['path']),row['sha256'],p['expected_crc32'],p['crc_scope'],cancelled=c),'artifact_id':row['artifact_id']}

    def _system_identify(self,p,c):
        from .system_identify import identify_system
        project=self.project(p);row=projects.artifact(project,p['artifact_id'])
        return {**identify_system(Path(row['path']),expected_sha256=row['sha256'],cancelled=c),'artifact_id':row['artifact_id']}

    def _nes_chr(self,p,c):
        from .system_resources import describe_nes_chr
        project=self.project(p)
        with projects.locked(project) as value:
            row=projects.artifact(project,p['artifact_id'])
            result=describe_nes_chr(Path(row['path']),expected_sha256=row['sha256'],first_tile=p['first_tile'],count=p['count'],cancelled=c)
            if result.get('ok') is not True:return result
            projects._measure(row['path'],row,cancelled=c)
            owned=next(r for r in value['sources']+value['builds'] if r['artifact_id']==row['artifact_id'])
            owned.setdefault('descriptors',{})['assets']=result['schema']
            projects.write_json(project/'project.json',value)
            return {**result,'artifact_id':row['artifact_id']}

    def _demo_system(self,p,c):
        from .system_demo import create_system_demo
        return create_system_demo(self.projects,self.incoming,p['system_id'])

    def _patch_set(self,p,c):
        from .patch_sets import create_patch_set
        project=self.project(p)
        source=self._disc_inventory({'project_id':p['project_id'],'container_id':p['source_id']},c)
        target=self._disc_inventory({'project_id':p['project_id'],'container_id':p['target_id']},c)
        path=self._export_path(project,'zip')
        result=create_patch_set(project/'containers'/p['source_id']/source['cue'],project/'containers'/p['target_id']/target['cue'],path,p['title'],cancelled=c)
        result['export']=self._record_export(project,path,'patchset',result)
        return result

    def _apply_patch_set(self,p,c):
        from .patch_sets import apply_patch_set
        return apply_patch_set(Path(p['source_cue']),Path(p['archive']),Path(p['destination']),cancelled=c)

    def _demo_nes(self,p,c):
        from .system_demo import create_nes_demo
        return create_nes_demo(self.projects,self.incoming)

    def _pick_file(self,p,c):
        if os.name=='nt':
            code="[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);Add-Type -AssemblyName System.Windows.Forms;$d=[System.Windows.Forms.OpenFileDialog]::new();$d.Title='Select a ROMancer input file';if($d.ShowDialog() -eq 'OK'){[Console]::WriteLine($d.FileName)};$d.Dispose()"
            command=['powershell.exe','-NoProfile','-STA','-WindowStyle','Hidden','-Command',code]
        else:
            code="import tkinter as t;from tkinter.filedialog import askopenfilename;r=t.Tk();r.withdraw();print(askopenfilename(title='Select a ROMancer input file'));r.destroy()"
            command=[sys.executable,'-X','utf8','-I','-c',code]
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline=time.monotonic()+120
            while process.poll() is None:
                if c():raise KeyboardInterrupt
                if time.monotonic()>deadline:raise ValueError('file chooser timed out')
                time.sleep(.05)
            raw=process.stdout.read(16385)
            if process.returncode or len(raw)>16384:raise ValueError('native file chooser unavailable; use the file upload control or paste an absolute path')
            path=raw.decode('utf-8').strip()
            return {'ok':True,'status':'SELECTED' if path else 'CANCELLED','path':path}
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stdout.close()

    def _demo(self,p,c):
        from .workbench_demo import create_demo
        return create_demo(self.projects,self.incoming)

    def _import(self,p,c):
        from .system_identify import identify_system
        from .release_scope import SYSTEMS
        # Reject saved web error pages before creating a source or scan job.
        source=checked_path(Path(p['path']))
        with source.open('rb') as stream:prefix=stream.read(512)
        if prefix.startswith(b'\xef\xbb\xbf'):prefix=prefix[3:]
        if re.match(rb'(?:<!doctype\s+html(?:\s|>)|<html(?:\s|>))',prefix.lstrip(),re.I):
            raise ValueError('This file contains an HTML page, not ROM data. Choose the actual cartridge file; extract it from a valid archive first.')
        detected=identify_system(Path(p['path']),cancelled=c)
        if detected.get('status')!='IDENTIFIED' or detected.get('system_id') not in SYSTEMS:
            raise ValueError('Choose a recognized, supported cartridge format listed in Settings. Unknown, ambiguous and unsupported layouts cannot be imported; a filename or system hint does not verify a format.')
        result=projects.register_source(self.project(p),Path(p['path']),p['system'],cancelled=c)
        try:result['scan']=self._scan_start({'project_id':p['project_id'],'artifact_id':result['artifact_id'],'rescan':False},c)
        except (ValueError,OSError,RuntimeError) as error:result['scan']={'status':'NOT_STARTED','reason':str(error)}
        return result

    def _apply_byte_build(self,p,c):
        result=projects.apply_build(self.project(p),p['plan_id'],cancelled=c)
        try:result['resource_setup']=self._reuse_definitions({'project_id':p['project_id'],'artifact_id':result['artifact_id']},c)
        except (ValueError,OSError,KeyError) as error:result['resource_setup']={'status':'NOT_REUSED','reason':str(error)}
        return result

    def _capture_record(self,p,c):
        from .capture_runtime import capture_run
        project,row,_=self.source(p)
        if not row.get('build_id'):raise ValueError('Reimport this older source to register its capture identity.')
        return capture_run(project,row['build_id'],p['config'],project,cancelled=c)

    def _capture_search(self,p,c):
        from .capture_store import init_capture_store,search_captures
        project=self.project(p)
        if not (project/'.romancer-evidence').exists():init_capture_store(project)
        return search_captures(project,p['query'])

    def _capture_get(self,p,c):
        from .capture_store import get_capture
        result=get_capture(self.project(p),p['capture_id'])
        result['png_base64']=base64.b64encode(result.pop('png_bytes')).decode('ascii')
        return result

    def _capture_annotate(self,p,c):
        from .capture_ingest import add_annotations
        return add_annotations(self.project(p),p['capture_id'],p['entries'])

    def _script_inspect(self,p,c):
        from .script import inspect_script
        _,_,source=self.source(p);return inspect_script(source,p['schema'])

    def _assets_inspect(self,p,c):
        from .assets import inspect_assets
        _,_,source=self.source(p);return inspect_assets(source,p['schema'])

    def _structured_plan(self,p,kind):
        project,row,source=self.source(p)
        if kind=='script':
            from .script import plan_script
            result=plan_script(source,p['schema'],p['edits'])
        else:
            from .assets import plan_assets
            result=plan_assets(source,p['schema'],p['edits'])
        if result.get('ok') is not True:return result
        envelope={'kind':kind,'artifact_id':p['artifact_id'],'schema':p['schema'],'edits':p['edits'],'service_plan_id':result['plan_id']}
        from .system_identify import identify_system
        system=identify_system(source,expected_sha256=row['sha256'])['system_id']
        if system=='segacd':raise ValueError('extract and edit a disc resource, then rebuild its container')
        if system in ('nes','snes','genesis','gb','gbc','gba','sms'):
            from .system_integrity import integrity_edits
            hunks=[{'offset':h['offset'],'before':h['before_hex'],'after':h['after_hex']} for h in result['hunks']]
            repaired=integrity_edits(source,row['sha256'],system,hunks)
            envelope['integrity_edits']=repaired[len(hunks):]
            result['integrity_edits']=envelope['integrity_edits']
        plan_id=digest(envelope);projects.write_json(project/'plans'/(plan_id+'.json'),envelope)
        return {**result,'workbench_plan_id':plan_id}

    def _record_build(self,project,row,path,plan_id,kind,schema):
        from .history import register_build
        measured=projects._measure(path)
        registered=register_build(project,{'inputs':[{'role':'original','path':row['path']}],'output':str(path),
            'adapter':{'name':kind,'version':'1'},'profile':{'name':'declared-structured-plan','version':'1'},'settings':{'plan_id':plan_id}},project)
        value=projects.read_project(project);record={'artifact_id':uuid.uuid4().hex,'name':kind.title()+' build '+str(len(value['builds'])+1),
            'kind':'build','path':str(path),'system':row['system'],**measured,'source_id':row['artifact_id'],'plan_id':plan_id,'build_id':registered['build_id']}
        # Derive only descriptors bound to the input that was just independently verified.
        # Generic byte builds deliberately do not receive inferred schemas.
        import copy
        descriptors=copy.deepcopy(row.get('descriptors',value.get('descriptors',{})))
        descriptors[kind]=copy.deepcopy(schema)
        for descriptor_kind,descriptor in list(descriptors.items()):
            if descriptor_kind in ('assets','font') and descriptor.get('source',{}).get('sha256')==row['sha256']:
                descriptor['source']['sha256']=measured['sha256']
            elif descriptor_kind=='script' and row['sha256'] in descriptor.get('profile',{}).get('accepted_sha256',[]):
                descriptor['profile']['accepted_sha256']=[measured['sha256']]
                if kind=='script':
                    text_rules={r['rule'] for r in descriptor['format']['records']}
                    with path.open('rb') as stream:
                        for rule in descriptor['profile']['rules']:
                            if rule['resource'] in text_rules:
                                stream.seek(rule['offset']);rule['expected_hex']=stream.read(rule['length']).hex()
            else:descriptors.pop(descriptor_kind,None)
        record['descriptors']=descriptors
        if 'container_parent' in row:record['container_parent']=row['container_parent']
        projects.assess_artifact(record)
        value['builds'].append(record);projects.write_json(project/'project.json',value);return record

    def _structured_apply(self,p,c):
        project=self.project(p);plan_id=projects.identifier(p['plan_id'])
        with projects.locked(project):
            envelope=load_script_json(project/'plans'/(plan_id+'.json'),max_bytes=8*1024**2)
            if digest(envelope)!=plan_id:raise ValueError('structured plan identity mismatch')
            row=projects.artifact(project,envelope['artifact_id']);projects._measure(row['path'],row)
            path=project/'builds'/(uuid.uuid4().hex+Path(row['path']).suffix)
            if envelope['kind']=='script':
                from .script_patch import apply_script
                result=apply_script(Path(row['path']),path,envelope['schema'],envelope['edits'],expected_plan_id=envelope['service_plan_id'])
            elif envelope['kind']=='assets':
                from .asset_patch import apply_assets
                result=apply_assets(Path(row['path']),path,envelope['schema'],envelope['edits'],expected_plan_id=envelope['service_plan_id'])
            else:raise ValueError('unknown structured plan type')
            if result.get('ok') is not True:return result
            if envelope.get('integrity_edits'):
                repaired=project/'builds'/(uuid.uuid4().hex+path.suffix)
                projects._publish_copy(path,repaired,projects._measure(path),envelope['integrity_edits'],cancelled=c)
                path.unlink();path=repaired
                measured=projects._measure(path)
                result.update(integrity_edits=envelope['integrity_edits'],integrity_repaired=True)
                for key in ('output_sha256','out_sha256'):
                    if key in result:result[key]=measured['sha256']
                for key in ('output_path','out_path'):
                    if key in result:result[key]=str(path)
            return {**result,**self._record_build(project,row,path,plan_id,envelope['kind'],envelope['schema']),'ok':True,'status':'BUILT'}

    def _font(self,p,c):
        from .font_metrics import measure_font
        _,_,source=self.source(p);return measure_font(source,p['schema'])

    def _layout(self,p,plan):
        from .dialogue_layout import check_layout,plan_layout
        project,_,source=self.source(p);font=Path(projects.artifact(project,p['font_artifact_id'])['path'])
        args=(source,p['schema'],font,p['font_schema'],p['policy'])
        return plan_layout(*args,p['request']) if plan else check_layout(*args)

    def _menu(self,p,c):
        from .menu import inspect_menu
        _,_,source=self.source(p);return inspect_menu(source,p['schema'],p['profile'])

    def _menu_preview(self,p,c):
        from .menu import preview_menu
        project,_,source=self.source(p);font=Path(projects.artifact(project,p['font_artifact_id'])['path'])
        return preview_menu(source,p['schema'],p['profile'],p['cases'],p['font_schema'],font)

    def _menu_compare(self,p,c):
        from .menu_compare import compare_menu_captures
        project,_,source=self.source(p);font=Path(projects.artifact(project,p['font_artifact_id'])['path'])
        return compare_menu_captures(project,source,p['schema'],p['profile'],p['cases'],p['font_schema'],font,p['request'])

    def _runtime_load(self,p,c):return self.runtime.load(self.project(p),p['artifact_id'],p['core'],p['options'],cancelled=c)

    def _save_state(self,p,c):
        project=self.project(p);snapshot=self.runtime.request(project,'save_state',{},cancelled=c)
        snapshot_id=uuid.uuid4().hex;projects.write_json(project/'sessions'/(snapshot_id+'.json'),snapshot,max_bytes=12*1024**2)
        return {key:value for key,value in snapshot.items() if key!='state_base64'}|{'snapshot_id':snapshot_id,'status':'CAPTURED'}

    def _load_state(self,p,c):
        project=self.project(p);snapshot_id=projects.identifier(p['snapshot_id'])
        snapshot=load_script_json(project/'sessions'/(snapshot_id+'.json'),max_bytes=12*1024**2)
        return self.runtime.request(project,'load_state',{'snapshot':snapshot},cancelled=c)

    def _runtime_config(self,p):
        from .release_scope import require_supported
        if 'container_id' in p:raise ValueError('Choose a supported cartridge source.')
        project,row,path=self.source(p);require_supported(row)
        if 'system_id' in p:
            config=self._profile_load_config(p['system_id'])
            if row.get('system_id') and row['system_id']!=p['system_id']:raise ValueError('configured system differs from selected image')
            return project,{**config,'game':str(path),'expected_game_sha256':row['sha256'],'session_dir':str(project/'sessions'/uuid.uuid4().hex)}
        project,row,_=self.source(p);core=checked_path(Path(p['core']));identity=projects._measure(core)
        return project,{'core':str(core),'game':row['path'],'expected_core_sha256':identity['sha256'],
                        'expected_game_sha256':row['sha256'],'session_dir':str(project/'sessions'/uuid.uuid4().hex),'core_options':p['options']}

    def _audio_capture(self,p,c):
        from .audio_export_runtime import capture_audio
        from .release_scope import require_supported
        project=self.project(p);game=checked_path(project/Path(p['config']['load']['game']))
        owned=next((r for r in projects.read_project(project)['sources']+projects.read_project(project)['builds'] if checked_path(Path(r['path']))==game),None)
        if owned is None:raise ValueError('Choose an owned supported cartridge for audio capture.')
        require_supported(owned);projects._measure(game,owned)
        path=self._export_path(project,p['format']);result=capture_audio(p['config'],p['baseline'],path,base=project,output_format=p['format'],cancelled=c)
        if result.get('ok'):result['export']=self._record_export(project,path,'audio',result)
        return result

    def _debug(self,p,live,c=None):
        from .debug import inspect_debug_case
        from .debug_runtime import observe_debug_case
        project,_,source=self.source(p)
        return observe_debug_case(project,source,p['case'],p['trace'],p['runtime'],project,cancelled=c) if live else inspect_debug_case(project,source,p['case'],p['trace'])

    def _route(self,p,c):
        from .replay import run_route
        project,load=self._runtime_config(p)
        return run_route(project,p['route'],load,project,timeout=p['timeout'],cancelled=c,initial_state=p['initial_state'])

    def _compile_route(self,p,c):
        from .route_editor import compile_route
        return {'ok':True,'status':'DEFINED','route':compile_route(p['name'],p['steps'],p['max_frames'],p['max_actions'])}

    def _list_routes(self,p,c):
        from .route_editor import list_definitions
        return list_definitions(self.project(p))

    def _get_route(self,p,c):
        from .route_editor import get_definition
        return get_definition(self.project(p),p['definition_id'])

    def _route_selection(self,p,selection):
        fields(selection,'kind id');projects.identifier(selection['id'])
        if selection['kind']=='artifact':
            project,row,path=self.source({'project_id':p['project_id'],'artifact_id':selection['id']})
            from .release_scope import require_supported
            require_supported(row)
            return {'kind':'artifact','id':row['artifact_id'],'sha256':row['sha256']}
        raise ValueError('unknown route content kind')

    def _save_route(self,p,c):
        from .route_editor import save_definition
        project=self.project(p);selection=self._route_selection(p,p['selection'])
        return save_definition(project,selection,p['system_id'],p['route'],p['initial_state_id'])

    def _run_saved_route(self,p,c):
        from .route_editor import get_definition
        from .replay import run_route
        if type(p['use_checkpoint']) is not bool:raise ValueError('choose cold start or checkpoint')
        project=self.project(p);definition=get_definition(project,p['definition_id']);selection=self._route_selection(p,p['selection'])
        if not definition['complete'] or definition['status']=='RECORDING':raise ValueError('finish the route and add an assertion before replay')
        params={'project_id':p['project_id'],'system_id':definition['system_id'],('artifact_id' if selection['kind']=='artifact' else 'container_id'):selection['id']}
        project,load=self._runtime_config(params);initial=None
        if p['use_checkpoint']:
            if not definition['initial_state_id']:raise ValueError('route has no initial checkpoint; select cold start')
            initial=load_script_json(project/'sessions'/(definition['initial_state_id']+'.json'),max_bytes=12*1024**2)
        return run_route(project,definition['route'],load,project,timeout=p['timeout'],cancelled=c,initial_state=initial)

    def _record_route_start(self,p,c):
        from .system_registry import SYSTEM_IDS
        from .asset_schema import label
        label(p['name'])
        if p['system_id'] not in SYSTEM_IDS:raise ValueError('choose a supported system')
        project=self.project(p);current=self.runtime.session_selection(project);value=projects.read_project(project)
        kind='artifact' if any(r['artifact_id']==current['id'] for r in value['sources']+value['builds']) else 'disc'
        selection=self._route_selection(p,{'kind':kind,'id':current['id']});snapshot=self._save_state({'project_id':p['project_id']},c)
        record={'format':'romancer-route-v1','definition_id':uuid.uuid4().hex,'selection':selection,'system_id':p['system_id'],'initial_state_id':snapshot['snapshot_id'],'complete':False,'status':'RECORDING','origin':'acknowledged_native_inputs','acknowledged_frames':0,
                'route':{'schema_version':1,'id':p['name'],'max_frames':6000,'max_actions':100,'steps':[]}}
        return self.runtime.begin_recording(project,record)

    def _battle(self,p,c):
        from .battle_analysis import analyze_battle
        return analyze_battle(p['profile'],p['observations'],p['budget'])

    def _coverage(self,p,c):
        from .coverage import build_coverage
        from .workbench_evidence import store_evidence
        project=self.project(p);result=build_coverage(project,p['evidence_ids'],p['objectives'])
        result['evidence_id']=store_evidence(project,'coverage',result)['evidence_id'];return result

    def _regression_suite(self,p,c):
        from .asset_schema import number
        from .route_editor import get_definition
        from .workbench_evidence import store_evidence
        project=self.project(p);ids=p['definition_ids'];number(p['timeout'],1,30)
        if type(ids) is not list or not 1<=len(ids)<=8 or any(type(v) is not str for v in ids) or len(set(ids))!=len(ids):raise ValueError('choose1..8 different saved assertion routes')
        source=projects.artifact(project,p['source_id']);target=projects.artifact(project,p['target_id']);projects._measure(source['path'],source);projects._measure(target['path'],target)
        from .release_scope import require_supported
        require_supported(source);require_supported(target)
        definitions=[get_definition(project,definition_id) for definition_id in ids]
        for definition in definitions:
            if not definition['complete'] or definition['status']=='RECORDING':raise ValueError('every suite route needs completed assertions')
            if definition['initial_state_id'] is not None:raise ValueError('suite comparisons need cold-start routes; use Replay saved route for recorded checkpoints')
            if any(row.get('system_id') and row['system_id']!=definition['system_id'] for row in (source,target)):raise ValueError('suite route and cartridge systems differ')
        deadline=time.monotonic()+120
        def aborted():return c() or time.monotonic()>deadline
        tests=[]
        for definition in definitions:
            if aborted():raise KeyboardInterrupt
            params={'project_id':p['project_id'],'definition_id':definition['definition_id'],'use_checkpoint':False,'timeout':p['timeout']}
            test={'name':definition['route']['id'],'definition_id':definition['definition_id'],'status':'INCONCLUSIVE'}
            try:
                baseline=self._run_saved_route({**params,'selection':{'kind':'artifact','id':source['artifact_id']}},aborted)
                if aborted() or baseline.get('status')=='CANCELLED':raise KeyboardInterrupt
                test['baseline_id']=baseline.get('evidence_id');test['baseline_status']=baseline['status']
                if baseline['status']!='PASS':test['reason']='Baseline assertions failed; candidate was not run.'
                else:
                    candidate=self._run_saved_route({**params,'selection':{'kind':'artifact','id':target['artifact_id']}},aborted)
                    if aborted() or candidate.get('status')=='CANCELLED':raise KeyboardInterrupt
                    test['candidate_id']=candidate.get('evidence_id');test['candidate_status']=candidate['status']
                    if candidate.get('evidence_id') and baseline.get('evidence_id'):
                        comparison=self._regression({'project_id':p['project_id'],'baseline_id':baseline['evidence_id'],'candidate_id':candidate['evidence_id']},aborted);test['comparison']=comparison
                        test['status']='PASS' if candidate['status']=='PASS' and comparison['status']=='UNCHANGED' else 'REGRESSION' if comparison['status']=='REGRESSION' else 'INCONCLUSIVE'
                        if test['status']=='INCONCLUSIVE':test['reason']=comparison.get('reason','Outcomes changed; inspect measured assertions.')
                    else:test['reason']='A native run did not create comparable evidence.'
            except (ValueError,OSError,RuntimeError) as error:test['reason']=str(error)[:1024]
            tests.append(test)
        if aborted():raise KeyboardInterrupt
        counts={key:sum(row['status']==status for row in tests) for key,status in [('passed','PASS'),('regression','REGRESSION'),('inconclusive','INCONCLUSIVE')]}
        status='REGRESSION' if counts['regression'] else 'INCONCLUSIVE' if counts['inconclusive'] else 'PASS'
        result={'ok':True,'status':status,'scope':'native_route_suite','project_id':p['project_id'],'source_id':source['artifact_id'],'target_id':target['artifact_id'],'source_sha256':source['sha256'],'target_sha256':target['sha256'],'tests':tests,'counts':counts,
            'runtime_evidence_authenticated':all(row.get('comparison',{}).get('runtime_evidence_authenticated') for row in tests),'gameplay_verified':False,'max_seconds':120,
            'note':'Results cover the selected route assertions; untested gameplay remains unknown.'}
        result['evidence_id']=store_evidence(project,'regression',result)['evidence_id'];return result

    def _regression(self,p,c):
        from .regression import compare_runs
        from .workbench_evidence import load_evidence,store_evidence
        project=self.project(p);baseline=load_evidence(project,p['baseline_id'],'route');candidate=load_evidence(project,p['candidate_id'],'route')
        if not baseline['runtime_trusted'] or not candidate['runtime_trusted']:
            result={'ok':True,'status':'INCONCLUSIVE','reason':'Restored reports are historical imports; record fresh local routes for authenticated comparison.','runtime_evidence_authenticated':False}
        else:
            result=compare_runs(baseline['report'],candidate['report']);result['runtime_evidence_authenticated']=True
        result['evidence_id']=store_evidence(project,'regression',result)['evidence_id'];return result

    def _bisect(self,p,c):
        from .regression import bisect_changes
        from .replay import run_route
        project,row,_=self.source(p);results=[]
        def evaluate(changes):
            if c():raise KeyboardInterrupt
            source_id=p['artifact_id']
            if changes:
                plan=self._integrity_plan({'project_id':p['project_id'],'artifact_id':source_id,'edits':changes},c) if row.get('system_id') in ('nes','snes','genesis','gb','gbc','gba','sms') else projects.plan_byte_edits(project,source_id,changes);build_path=project/'builds'/(plan['plan_id']+Path(row['path']).suffix)
                if build_path.exists():
                    candidates=[r for r in projects.read_project(project)['builds'] if r['plan_id']==plan['plan_id']]
                    if not candidates:raise ValueError('bisection output collision')
                    source_id=candidates[0]['artifact_id']
                else:source_id=projects.apply_build(project,plan['plan_id'])['artifact_id']
            params={**p,'artifact_id':source_id};_,load=self._runtime_config(params)
            result=run_route(project,p['route'],load,project,timeout=p['timeout'],cancelled=c);results.append(result['evidence_id']);return result
        result=bisect_changes(p['changes'],evaluate,p['budget']);result.update(native_execution_verified=True,evidence_ids=results)
        return result

    def _reports(self,p,c):
        from .workbench_evidence import load_evidence
        project=self.project(p);rows=[]
        for path in sorted((project/'reports').glob('*.json'))[-256:]:
            try:
                item=load_evidence(project,path.stem);report=item['report']
                rows.append({'evidence_id':item['evidence_id'],'kind':item['kind'],'status':report.get('status'),'route_id':report.get('route_id'),'authentication':item['authentication'],'runtime_trusted':item['runtime_trusted']})
            except (ValueError,OSError):continue
        return {'ok':True,'reports':rows[::-1]}

    def _report(self,p,c):
        from .workbench_evidence import load_evidence
        return {'ok':True,**load_evidence(self.project(p),p['evidence_id'])}

    def exports(self,project):
        path=project/'exports.json'
        if not path.exists():return []
        from .runtime_protocol import _pairs,_constant
        from .script_schema import canonical_bytes
        projects._measure(path)
        if path.stat().st_size>8*1024**2:raise ValueError('export index is too large')
        value=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=_pairs,parse_constant=_constant)
        canonical_bytes(value,max_bytes=8*1024**2)
        # Recover the initial development index format without discarding exports.
        rows=value if type(value) is list else value.get('exports')
        if type(rows) is not list or len(rows)>4096:raise ValueError('invalid export index')
        from .export_names import download_name
        return [{**row,'download_name':download_name(row)} for row in rows]

    def _export_path(self,project,suffix):
        if suffix not in ('txt','html','bps','zip','pcm','wav','json','png','sav','csv','tsv'):raise ValueError('unsupported export type')
        return project/'exports'/(uuid.uuid4().hex+'.'+suffix)

    def _record_export(self,project,path,role,result=None,*,title=None):
        from .export_names import readable_name
        title=title if title is not None else projects.read_project(project)['name']+'-'+role
        row={'export_id':path.stem,'name':path.name,'download_name':readable_name(title,path.suffix[1:]),'role':role,**projects._measure(path)}
        if result:
            for key in ('source_sha256','target_sha256','format'): 
                if key in result:row[key]=result[key]
        rows=self.exports(project);rows.append(row);projects.write_json(project/'exports.json',{'schema_version':1,'exports':rows});return row

    def download(self,project_id,export_id):
        project=self.project({'project_id':project_id});projects.identifier(export_id)
        for row in self.exports(project):
            if row['export_id']==export_id:
                path=checked_path(project/'exports'/row['name'])
                if path.parent!=project/'exports':raise ValueError('export path escaped storage')
                projects._measure(path,row);return path,row
        raise ValueError('unknown export')

    def _docs_script(self,p,c):
        from .player_docs import export_script
        from .release import publish_bytes
        project=self.project(p);path=self._export_path(project,'html' if p['format']=='html' else 'txt')
        publish_bytes(path,export_script(p['document'],p['format']).encode('utf-8'),cancelled=c)
        return {'ok':True,'status':'EXPORTED','export':self._record_export(project,path,'documentation')}

    def _docs_script_resource(self,p,c):
        from .player_docs import script_document
        model=self._script_inspect(p,c)
        if model.get('ok') is not True:return model
        title=projects.read_project(self.project(p))['name']
        return self._docs_script({'project_id':p['project_id'],'document':script_document(model,title),'format':p['format']},c)

    def _docs_walkthrough(self,p,c):
        from .workbench_evidence import load_evidence
        from .player_docs import export_walkthrough
        from .release import publish_bytes
        project=self.project(p);report=load_evidence(project,p['evidence_id'],'coverage')['report'];path=self._export_path(project,'txt')
        publish_bytes(path,export_walkthrough(report,p['annotations']).encode('utf-8'),cancelled=c)
        return {'ok':True,'status':'EXPORTED','export':self._record_export(project,path,'documentation')}

    def _patch(self,p,c):
        from .streaming_bps import create_patch as prepare_patch
        from .release import publish_bytes
        project=self.project(p);source=projects.artifact(project,p['source_id']);target=projects.artifact(project,p['target_id'])
        projects._measure(source['path'],source,cancelled=c);projects._measure(target['path'],target,cancelled=c)
        path=self._export_path(project,'bps');result=prepare_patch(Path(source['path']),Path(target['path']),path,{'title':p['title'],'description':p['description']},cancelled=c)
        # Atomic BPS publication is the commit point. Finish its small index/docs transaction
        # even if a cancellation arrives afterward; the completed publication stays visible.
        result['export']=self._record_export(project,path,'patch',result,title=p['title'])
        instructions=('ROMancer patch instructions\n\n'+p['title']+'\n\nOriginal SHA-256: '+source['sha256']+'\nTarget SHA-256: '+target['sha256']+
            '\nApply the BPS patch with a compatible patcher to your own exact source revision. Keep the original unchanged.\nVerify the output SHA-256 before use.\n\nBy RetchEWretched\n')
        doc=self._export_path(project,'txt');publish_bytes(doc,instructions.encode());result['instructions']=self._record_export(project,doc,'documentation',title=p['title']+'-instructions')
        return result

    def _verify_patch(self,p,c):
        from .release import verify_patch
        project=self.project(p);source=projects.artifact(project,p['source_id']);path,row=self.download(p['project_id'],p['export_id'])
        if row['role']!='patch':raise ValueError('selected export is not a patch')
        result=verify_patch(Path(source['path']),path,row['target_sha256'],cancelled=c)
        if result.get('ok') and result.get('status')=='VERIFIED':
            from .workbench_evidence import store_evidence
            evidence=store_evidence(project,'release',{'scope':'patch_verification','export_id':row['export_id'],'source_id':source['artifact_id'],'patch_sha256':row['sha256'],**result})
            result['evidence_id']=evidence['evidence_id']
        return result

    def _package(self,p,c):
        from .release import package_release
        project=self.project(p)
        if type(p['export_ids']) is not list or not 1<=len(p['export_ids'])<=128:raise ValueError('select 1..128 exports')
        selected=[]
        for index,export_id in enumerate(p['export_ids']):
            path,row=self.download(p['project_id'],export_id)
            selected.append({'source':str(path),'path':f'{index+1:02d}-'+row['download_name'],'role':row['role']})
        path=self._export_path(project,'zip');result=package_release(path,{'title':p['title'],'files':selected},cancelled=c)
        result['export']=self._record_export(project,path,'package',title=p['title']+'-release');return result

    def close(self):self.jobs.close();self.runtime.close()
