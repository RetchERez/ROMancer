"""Read-only checks of owned files and explicitly declared resource semantics."""
from pathlib import Path
from . import workbench_projects as p
from .asset_schema import number
from .assets import checked_path
from .script_schema import load_script_json

CHECK_CODES={'ARTIFACT_MISSING','ARTIFACT_CHANGED','MISSING_DEPENDENCY','STALE_DEFINITION','INVALID_DEFINITION',
             'INVALID_POINTER','OVERLAPPING_DECLARATIONS','UNKNOWN_SCOPE','COMPRESSED_ALLOCATION','INVALID_PLAN','PLAN_OVERLAP','STALE_PLAN','CATALOG_INVALID'}


def validate_project(project,*,cancelled=lambda:False):
    project=checked_path(Path(project));value=p.read_project(project);rows=value['sources']+value['builds'];by_id={r['artifact_id']:r for r in rows};issues=[];counts={'errors':0,'warnings':0};checked=0
    def issue(code,severity,row,location,remedy,offset=None):
        counts['errors' if severity=='error' else 'warnings']+=1
        if len(issues)<1000:issues.append({'code':code,'severity':severity,'artifact_id':row.get('artifact_id'),
            'location':location,'offset':offset,'remedy':remedy})
    for row in rows:
        if cancelled():raise KeyboardInterrupt
        checked+=1;aid=row['artifact_id'];where=row['name'];ranges=[]
        try:path=checked_path(Path(row['path']));p._measure(path,row,cancelled=cancelled)
        except FileNotFoundError:issue('ARTIFACT_MISSING','error',row,where,'Restore this owned file from a private project backup.');continue
        except (OSError,ValueError):issue('ARTIFACT_CHANGED','error',row,where,'Restore the original owned copy or import the changed file as a new source.');continue
        for field in ('source_id','resource_id'):
            if row.get(field) and row[field] not in by_id:issue('MISSING_DEPENDENCY','error',row,where+' / '+field,'Restore the missing parent from the same project backup.')
        descriptors=row.get('descriptors',{})
        if not descriptors:issue('UNKNOWN_SCOPE','warning',row,where,'Declare text, graphics or tables to check their format. File identity was checked.')
        if type(descriptors) is not dict:issue('INVALID_DEFINITION','error',row,where+' / descriptors','Restore or redeclare resource definitions.');continue
        for kind,schema in descriptors.items():
            location=where+' / '+kind
            try:
                if type(schema) is not dict:raise ValueError('Invalid descriptor')
                bound=(schema.get('profile',{}).get('accepted_sha256',[]) if kind=='script' else [schema.get('source_sha256')] if kind=='tables' else [schema.get('source',{}).get('sha256')])
                if row['sha256'] not in bound:issue('STALE_DEFINITION','error',row,location,'Reinspect this exact revision and redeclare or explicitly reuse its resource setup.');continue
                if kind in ('assets','font'):
                    from .assets import inspect_assets
                    from .asset_codecs import cell_size
                    result=inspect_assets(path,schema)
                    if not result['ok']:raise ValueError('Asset inspection failed')
                    for b in result['bitmaps']:ranges.append((b['offset'],b['offset']+b['count']*cell_size(b['codec'],b['width'],b['height']),kind+'/'+b['id']))
                    for group in ('palettes','tilemaps'):
                        for r in result[group]:ranges.append((r['offset'],r['offset']+r['length'],kind+'/'+r['id']))
                elif kind=='script':
                    from .script import inspect_script
                    result=inspect_script(path,schema)
                    if not result['ok']:raise ValueError('Text inspection failed')
                    ranges.extend((r['offset'],r['offset']+r['capacity'],'script/'+r['id']) for r in result['records'])
                elif kind=='tables':
                    from .data_tables import _context,_read
                    with _context(path,row['sha256'],schema['definition']) as (stream,source,definition):
                        ranges.append((definition['offset'],definition['offset']+definition['stride']*definition['count'],'tables'))
                        for index in range(definition['count']):
                            if cancelled():raise KeyboardInterrupt
                            for field in definition['fields']:
                                if field['pointer_base'] is None:continue
                                cell=_read(stream,definition,index,field,source['size'])
                                if cell['pointer_resolution']=='unresolved':issue('INVALID_POINTER','error',row,f"{location} / row {index} / {field['name']}",'Correct the declared pointer base or stored value; target lies outside this file.',cell['offset'])
                else:issue('UNKNOWN_SCOPE','warning',row,location,'Use a supported declaration to validate this resource kind.')
            except (ValueError,OSError,KeyError,TypeError):issue('INVALID_DEFINITION','error',row,location,'Check the declaration ranges, references, format and expected bytes against this revision.')
        previous=[]
        for start,end,name in sorted(set(ranges)):
            for a,b,other in previous:
                if start<b and a<end:issue('OVERLAPPING_DECLARATIONS','warning',row,f'{where} / {other} + {name}','Confirm these resources intentionally share bytes; each edit plan still checks overlapping writes.',start)
            previous=[r for r in previous if r[1]>start];previous.append((start,end,name))
        ancestor=row;seen=set();metadata=None
        for _ in range(128):
            if ancestor['artifact_id'] in seen:issue('MISSING_DEPENDENCY','error',row,where+' / ancestry','Restore a project backup with non-cyclic build ancestry.');break
            seen.add(ancestor['artifact_id'])
            if ancestor.get('compressed_parent'):metadata=ancestor['compressed_parent'];break
            ancestor=by_id.get(ancestor.get('source_id'))
            if ancestor is None:break
        if metadata:
            try:
                from .resource_compression import inspect_compressed,encode_stream,OUTPUT_LIMIT
                from .workbench_files import read_bounded
                parent=by_id[metadata['parent_id']]
                if parent['sha256']!=metadata['parent_sha256']:raise ValueError('Parent revision changed')
                result=inspect_compressed(parent['path'],parent['sha256'],metadata['offset'],metadata['allocation'],metadata['codec'],cancelled=cancelled)
                if result['decoded_sha256']!=ancestor['sha256']:raise ValueError('Decoded resource changed')
                raw=read_bounded(path,OUTPUT_LIMIT,row,cancelled=cancelled)
                if len(encode_stream(raw,metadata['codec']))>metadata['allocation']:raise ValueError('Allocation exceeded')
            except (ValueError,OSError,KeyError,TypeError):issue('COMPRESSED_ALLOCATION','error',row,where+' / compressed parent','Restore the exact parent and confirmed allocation, or reduce edits until recompressed data fits.',metadata.get('offset'))
        try:
            from .resource_catalog import _rows
            _rows(project,row)
        except (ValueError,OSError,KeyError,TypeError):issue('CATALOG_INVALID','error',row,where+' / resource catalog','Restore or reindex this revision’s declared resource catalog.')
    plans=sorted((project/'plans').glob('*.json'))
    for path in plans[:4096]:
        if cancelled():raise KeyboardInterrupt
        try:
            plan=load_script_json(checked_path(path),max_bytes=p.MAX_STORE)
            if plan.get('operation')!='byte-build':continue
            row=by_id.get(plan.get('source_id'))
            if row is None:issue('MISSING_DEPENDENCY','error',{},'plans/'+path.stem,'Restore this plan’s original source.');continue
            if plan.get('source_sha256')!=row['sha256']:issue('STALE_PLAN','error',row,'plans/'+path.stem,'Discard this stale plan and review the current source again.')
            end=-1
            for edit in sorted(plan['edits'],key=lambda e:e['offset']):
                offset=number(edit['offset'],0,row['size']);before=bytes.fromhex(edit['before']);after=bytes.fromhex(edit['after'])
                if not before or len(before)!=len(after) or offset+len(before)>row['size']:raise ValueError('Invalid plan range')
                if offset<end:issue('PLAN_OVERLAP','error',row,'plans/'+path.stem,'Remove overlapping changes and review a new plan.',offset)
                end=offset+len(before)
        except (ValueError,OSError,KeyError,TypeError):issue('INVALID_PLAN','error',{},'plans/'+path.stem,'Discard the damaged plan and review changes again.')
    if len(plans)>4096:issue('UNKNOWN_SCOPE','warning',{},'plans','Only the first 4096 saved plans were inspected; archive old plans in a private backup.')
    return {'ok':True,'project_id':value['project_id'],'status':'NEEDS_ATTENTION' if counts['errors'] else 'WARNINGS' if counts['warnings'] else 'CLEAN',
            'valid':not counts['errors'],'checked_artifacts':checked,**counts,'issues':issues,'issues_truncated':sum(counts.values())>len(issues),
            'scope':'Owned file identity and declared resources only; gameplay and undeclared formats are not certified.'}
