"""Automatic offline cartridge investigation; candidates never grant write authority."""
import hashlib
import json
import hmac
from pathlib import Path
from . import workbench_projects as projects
from .assets import checked_path
from .resource_discovery import discover
from .revision_catalog import load_catalog,lookup_revision
from .rom_health import check_rom
from .script_schema import load_script_json
from .script_schema import canonical_bytes
from .workbench_evidence import _key
from .verified_games import inspect,PROFILES,BYTE_NOTES
from .graphics_discovery import index_graphics
from .audio_systems import audio_system_info

MAX_SCAN=64*1024**2
WINDOW=1024**2
PER_KIND=100
VERSION=13


def cache_path(project,row):
    return checked_path(Path(project)/'sessions/rom-scans'/(row['artifact_id']+'.json'))


def fingerprint(project):
    catalog=checked_path(Path(project)/'catalog/revisions.json')
    if catalog.exists():
        if catalog.stat().st_size>32*1024**2:raise ValueError('revision catalog exceeds scan budget')
        reference=hashlib.sha256(catalog.read_bytes()).hexdigest()
    else:reference=None
    cheat_path=checked_path(Path(project)/'catalog/cheats.json')
    if cheat_path.exists():
        if cheat_path.stat().st_size>16*1024**2:raise ValueError('code reference catalog exceeds scan budget')
        cheat_reference=hashlib.sha256(cheat_path.read_bytes()).hexdigest()
    else:cheat_reference=None
    return hashlib.sha256(json.dumps({'version':VERSION,'catalog':reference,'cheats':cheat_reference,'definitions':PROFILES,'notes':BYTE_NOTES},sort_keys=True).encode()).hexdigest()


def cached(project,row,*,cancelled=lambda:False):
    projects._measure(row['path'],row,cancelled=cancelled)
    path=cache_path(project,row)
    if not path.exists():return None
    try:
        envelope=load_script_json(path,max_bytes=2*1024**2)
        if type(envelope) is not dict or set(envelope)!={'report','signature'} or type(envelope['signature']) is not str:return None
        result=envelope['report']
        if not hmac.compare_digest(envelope['signature'],hmac.new(_key(project),canonical_bytes(result,max_bytes=2*1024**2),hashlib.sha256).hexdigest()):return None
    except (ValueError,OSError,TypeError):return None
    if (type(result) is not dict or result.get('scan_version')!=VERSION or result.get('source_sha256')!=row['sha256']
            or result.get('artifact_id')!=row['artifact_id'] or result.get('fingerprint')!=fingerprint(project)):return None
    if (type(result.get('candidates')) is not list or len(result['candidates'])>3*PER_KIND
            or type(result.get('coverage')) is not dict or type(result.get('counts')) is not dict
            or set(result['counts'])!={'text','graphics','compression'}):return None
    if any(type(c) is not dict or type(c.get('offset')) is not int or c['offset']<0
           or type(c.get('length')) is not int or not 0<c['length']<=row['size']-c['offset']
           or c.get('kind') not in result['counts'] or any(type(c.get(k)) is not str for k in ('preview','confidence','format')) for c in result['candidates']):return None
    # Definition meaning is always freshly resolved; cached candidates cannot
    # manufacture a verified game identity after a project restore/edit.
    result['identification']=inspect(project,row,Path(row['path']),cancelled=cancelled)
    return result


def run(project,row,*,cancelled=lambda:False,publish=None):
    path=Path(row['path']);projects._measure(path,row,cancelled=cancelled)
    stamp=fingerprint(project);model=inspect(project,row,path,cancelled=cancelled)
    health=check_rom(path,row['sha256'],'','file',cancelled=cancelled) if row['size']<=MAX_SCAN else None
    catalog={}
    if load_catalog(project):
        for scope in ('file','payload'):
            try:catalog[scope]=lookup_revision(project,row['artifact_id'],scope,cancelled=cancelled)
            except ValueError as error:catalog[scope]={'status':'NOT_CHECKED','reason':str(error)}
    else:catalog={'file':{'status':'NO_CATALOG'},'payload':{'status':'NO_CATALOG'}}
    system=row.get('system_id');rows=[];counts={kind:0 for kind in ('text','graphics','compression')};segments=[]
    size=min(row['size'],MAX_SCAN);supported=system in ('nes','snes','genesis','gb','gbc','gba','sms');structures=[];structure_coverage=[]
    lab_candidates=[];lab_coverage=[];lab_total=0
    if supported:
        for start in range(0,size,WINDOW):
            if cancelled():raise KeyboardInterrupt
            coverage={'offset':start,'length':min(WINDOW,size-start)}
            if system!='sms':
                from .studio_discovery import scan_structures
                with path.open('rb') as stream:stream.seek(start);window=stream.read(coverage['length'])
                structural=scan_structures(window,system,start,row['size'],cancelled=cancelled)
                structures.extend(structural['candidates'][:max(0,64-len(structures))]);structure_coverage.append(structural['coverage'])
                from .structural_lab import survey
                lab=survey(window[:4096],row['sha256'],system,start,row['size'],max_positions=512,max_results=8,cancelled=cancelled)
                lab_candidates.extend(lab['candidates'][:max(0,32-len(lab_candidates))]);lab_coverage.append(lab['coverage']);lab_total+=lab['total_candidates']
            for kind in counts:
                result=discover(path,row['sha256'],system,start,coverage['length'],[kind],cancelled=cancelled)
                candidates=result['candidates'];counts[kind]+=len(candidates)
                remaining=max(0,PER_KIND-sum(c['kind']==kind for c in rows));rows.extend(candidates[:remaining])
                coverage[kind]={'results_truncated':result['results_truncated'],'sampling_stride':result['graphics_sampling_stride'],
                                'compression':result['compression_scan']}
            segments.append(coverage)
    graphics_index=index_graphics(path,system,size,cancelled=cancelled) if supported else {'status':'CODEC_UNRESOLVED','banks':[]}
    from .hardware_reference import reference_for
    hardware=reference_for(system) if supported else None
    from .cheat_catalog import inspect_catalog
    cheat_references=inspect_catalog(project,row,path,page=0,limit=10,cancelled=cancelled)
    if system=='gba':
        from .engine_recognition import recognize_engines,MAX_ROM_BYTES
        if row['size']>MAX_ROM_BYTES:
            engines={'ok':True,'status':'BUDGET_EXCEEDED','source_sha256':row['sha256'],'system_id':system,'findings':[],
                     'budget_reason':'Source exceeds the bounded engine-recognition size limit. Other scan checks are reported separately.','write_authorized':False}
        else:engines=recognize_engines(path,row['sha256'],system,cancelled=cancelled)
    else:engines={'ok':True,'status':'NOT_IMPLEMENTED','source_sha256':row['sha256'],'findings':[],'write_authorized':False}
    projects._measure(path,row,cancelled=cancelled)
    if cancelled():raise KeyboardInterrupt
    if fingerprint(project)!=stamp:raise ValueError('catalog changed during scan; rescan the ROM')
    result={'ok':True,'status':'SCANNED' if supported else 'SYSTEM_UNRESOLVED','scan_version':VERSION,'fingerprint':stamp,
            'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'system_id':system,'identification':model,'catalog':catalog,'hardware_reference':hardware,
            'health':health,'graphics_index':graphics_index,'cheat_references':cheat_references,'engine_recognition':engines,'sound_system':audio_system_info(system,row['sha256']) if supported else None,'structures':{'candidates':structures,'coverage':structure_coverage,'dereference_observed':False},'counts':counts,'candidates':sorted(rows,key=lambda r:(r['offset'],r['kind'])),
            'coverage':{'file_bytes_read':size if supported else 0,'file_size':row['size'],'whole_file_read':supported and size==row['size'],
                        'segments':segments,'result_limit_per_kind':PER_KIND,'exhaustive_semantic_analysis':False},
            'write_authorized':False,'runtime_verified':False,
            'limits':['Printable ASCII only; custom text encodings need a definition.',
                      'Graphics are sampled codec candidates, not proven sprite layouts.',
                      'Compression checks cover aligned supported LZ10/RLE signatures with per-window work budgets; see coverage.',
                      'Window boundaries may split resources. Use a focused range scan to investigate them.',
                      'Unknown stats, scripts and banked pointers need evidence or explicit mappings.']}
    result['structural_lab']={'source_sha256':row['sha256'],'candidates':lab_candidates,'coverage':lab_coverage,
        'total_candidates':lab_total,'truncated':lab_total>len(lab_candidates),'dereference_observed':False,
        'game_profile_required':False,'write_authorized':False,
        'scope':'Sampled first 4096 bytes of each 1 MiB segment. Use focused structural experiments to test other ranges and byte alignments.'}
    if publish:publish(result)
    else:
        projects.read_project(project)
        write_cache(project,row,result)
    return result


def write_cache(project,row,result):
    signature=hmac.new(_key(project),canonical_bytes(result,max_bytes=2*1024**2),hashlib.sha256).hexdigest()
    cache=cache_path(project,row);cache.parent.mkdir(parents=True,exist_ok=True)
    projects.write_json(cache,{'report':result,'signature':signature},max_bytes=2*1024**2)
