"""Whole-object layouts from checked pixel origins; never infer character roles."""
from collections import Counter
import json
from .asset_schema import fields,number,label
from .assets import digest
from .asset_codecs import cell_size
from .graphics_discovery import SYSTEM_CODECS,candidate_layout
from .script_schema import canonical_bytes
from . import workbench_projects as projects


def _orientation(part):
    height=part['height'];mapping=part['pixel_map']
    if type(mapping) is not list or not 16<=len(mapping)<=128:raise ValueError('A part needs a recovered pixel mapping.')
    choices=[]
    for flip in range(4):
        good=True
        for point in mapping:
            source=number(point['source_pixel'],0,8*height-1);screen=number(point['screen_pixel'],0,8*height-1)
            sx,sy=source%8,source//8
            if (height-1-sy if flip&2 else sy)*8+(7-sx if flip&1 else sx)!=screen:good=False;break
        if good:choices.append(flip)
    if len(choices)!=1:raise ValueError('Recovered mapping has no single literal tile orientation. Open its stored source separately.')
    return choices[0]


def verified_layout(system,parts):
    if type(parts) is not list or not 1<=len(parts)<=64:raise ValueError('Choose 1 to 64 verified parts.')
    prepared=[]
    for part in parts:
        height=number(part['height'],8,16)
        if height not in (8,16) or part.get('width')!=8:raise ValueError('Choose supported literal tile parts.')
        flip=_orientation(part)
        prepared.append({**part,'flip_x':bool(flip&1),'flip_y':bool(flip&2),'observed_colors':part['source_colors']})
    result=candidate_layout({'system_id':system,'matches':prepared},list(range(len(prepared))))
    result['layout']['provenance']='causal_replay'
    left=min(p['x'] for p in prepared);top=min(p['y'] for p in prepared)
    result['scene_region']={'x':left,'y':top,'width':result['layout']['columns']*8,'height':result['layout']['rows']*8}
    result['shared_tiles']=[{'cell_index':i,'placements':[j for j,v in enumerate(result['layout']['indices']) if v==i]} for i,n in Counter(v for v in result['layout']['indices'] if v is not None).items() if n>1]
    result['complete_parts']=all(p.get('complete_placement') is True for p in parts)
    return result


def validate_layout(value,size,system):
    value=json.loads(canonical_bytes(value,max_bytes=128*1024))
    fields(value,'config layout scene_region shared_tiles complete_parts')
    cfg=value['config'];fields(cfg,'system_id offset count codec width height palette_offset palette_banks palette_format')
    if cfg['system_id']!=system or cfg['codec']!=SYSTEM_CODECS.get(system) or cfg['width']!=8 or cfg['height']!=8:raise ValueError('Object tile format differs from this system.')
    unit=cell_size(cfg['codec'],8,8);number(cfg['offset'],0,size-1);number(cfg['count'],1,1024)
    if cfg['offset']+cfg['count']*unit>size or cfg['palette_offset'] is not None or cfg['palette_banks']!=1 or cfg['palette_format']!='rgb555-le':raise ValueError('Object source range or palette declaration is invalid.')
    layout=value['layout'];fields(layout,'first columns rows order indices flips colors provenance')
    columns=number(layout['columns'],1,8);rows=number(layout['rows'],1,8);count=columns*rows
    if layout['first']!=0 or layout['order']!='rows' or layout['provenance'] not in ('causal_replay','checked_declaration'):raise ValueError('Invalid object layout metadata.')
    if any(type(layout[k]) is not list or len(layout[k])!=count for k in ('indices','flips','colors')):raise ValueError('Object grid dimensions differ.')
    if not any(i is not None for i in layout['indices']):raise ValueError('An object needs a source tile.')
    for index,flip,colors in zip(layout['indices'],layout['flips'],layout['colors']):
        if index is not None:number(index,0,cfg['count']-1)
        number(flip,0,3)
        if index is None and (flip or colors is not None):raise ValueError('An unmapped object hole cannot contain tile metadata.')
        if colors is not None:
            if type(colors) is not dict or len(colors)>16:raise ValueError('Observed colors exceed palette bounds.')
            for key,color in colors.items():
                if type(key) is not str or not key.isdecimal() or not 0<=int(key)<2**(2 if unit==16 else 4):raise ValueError('Invalid palette index.')
                if type(color) is not list or len(color)!=3:raise ValueError('Invalid observed RGB.')
                for channel in color:number(channel,0,255)
    region=value['scene_region'];fields(region,'x y width height');number(region['x'],0,2048);number(region['y'],0,2048)
    if region['width']!=columns*8 or region['height']!=rows*8 or type(value['complete_parts']) is not bool:raise ValueError('Scene and object dimensions differ.')
    expected=[{'cell_index':i,'placements':[j for j,v in enumerate(layout['indices']) if v==i]} for i,n in Counter(v for v in layout['indices'] if v is not None).items() if n>1]
    if value['shared_tiles']!=expected:raise ValueError('Shared tile relationships differ from the layout.')
    return value


def objects_for(row):
    saved=row.get('object_layouts')
    if saved is None:return []
    fields(saved,'source_sha256 objects')
    if saved['source_sha256']!=row['sha256'] or type(saved['objects']) is not list or len(saved['objects'])>64:raise ValueError('Saved objects belong to another revision or exceed the object budget.')
    ids=set()
    for obj in saved['objects']:
        fields(obj,'id name definition parts trace_id frame_sha256')
        projects.identifier(obj['id']);label(obj['name'],80)
        if obj['id'] in ids:raise ValueError('Duplicate saved object identity.')
        ids.add(obj['id']);validate_layout(obj['definition'],row['size'],row['system_id'])
        if type(obj['parts']) is not list or len(obj['parts'])>64:raise ValueError('Object proof references exceed their budget.')
        for p in obj['parts']:
            fields(p,'verification_id match_id');projects.identifier(p['verification_id']);number(p['match_id'],0,255)
        for key in ('trace_id','frame_sha256'):
            value=obj[key]
            if value is not None and (type(value) is not str or len(value)!=(32 if key=='trace_id' else 64) or any(c not in '0123456789abcdef' for c in value)):raise ValueError('Invalid saved capture identity.')
    return saved['objects']


def portable_objects(row):
    return [{**o,'parts':[],'trace_id':None,'frame_sha256':None,'definition':{**o['definition'],'layout':{**o['definition']['layout'],'provenance':'checked_declaration'}}} for o in objects_for(row)]


def review_objects(row,incoming):
    # Portable layouts carry declarations only; execution evidence stays local.
    checked=objects_for({**row,'object_layouts':{'source_sha256':row['sha256'],'objects':incoming}})
    if any(o['parts'] or o['trace_id'] is not None or o['frame_sha256'] is not None or o['definition']['layout']['provenance']!='checked_declaration' for o in checked):raise ValueError('Imported layouts must be historical declarations without runtime proof references.')
    merged={o['id']:o for o in objects_for(row)};names={o['name'].casefold():o['id'] for o in merged.values()};replacements=[]
    for obj in checked:
        if obj['id'] in merged and obj!=merged[obj['id']]:replacements.append('object: '+obj['name'])
        other=names.get(obj['name'].casefold())
        if other is not None and other!=obj['id']:raise ValueError('Imported object name conflicts with another saved layout. Rename it before importing.')
        names[obj['name'].casefold()]=obj['id'];merged[obj['id']]=obj
    if len(merged)>64:raise ValueError('Imported objects exceed the 64-layout source budget.')
    return list(merged.values()),replacements


class ObjectTools:
    def __init__(self,api):self.api=api
    def routes(self):
        return {'objects.create':('project_id artifact_id name parts',self.create),'objects.list':('project_id artifact_id',self.list),
            'objects.get':('project_id artifact_id object_id',self.get),'objects.open':('project_id artifact_id object_id',self.open),
            'objects.scene':('project_id artifact_id object_id edits',self.scene),
            'objects.delete':('project_id artifact_id object_id',self.delete)}
    def _parts(self,p,parts,c=lambda:False):
        if type(parts) is not list or not 1<=len(parts)<=64:raise ValueError('Choose 1 to 64 verified parts.')
        _,row,_=self.api.source(p)
        from .release_scope import require_supported
        require_supported(row);codec=SYSTEM_CODECS[row['system_id']]
        chosen=[];identity=None;seen=set()
        for part in parts:
            if c():raise KeyboardInterrupt
            fields(part,'verification_id match_id');projects.identifier(part['verification_id']);number(part['match_id'],0,255)
            key=(part['verification_id'],part['match_id'])
            if key in seen:raise ValueError('Choose each verified placement once.')
            seen.add(key);r=self.api.visual_sources.get({**p,'verification_id':part['verification_id']},c)
            if not r['runtime_trusted'] or r['status']!='VERIFIED_VISUAL_SOURCE':raise ValueError('Use fresh authenticated source verification for each object part.')
            binding=(r['trace_id'],r['frame']['sha256'],digest(r['context']))
            if identity is not None and binding!=identity:raise ValueError('All object parts must belong to the same captured frame, trace and execution setup.')
            identity=binding;match=next((m for m in r['verified_matches'] if m['match_id']==part['match_id']),None)
            if match is None:raise ValueError('This verified placement is no longer available.')
            if match.get('width',8)!=8 or match.get('codec',codec)!=codec:raise ValueError('Verified part width or codec format conflicts with its checked system.')
            chosen.append({'width':8,'codec':codec,**match})
        return chosen,identity
    def create(self,p,c):
        project,row,path=self.api.source(p);label(p['name'],80);chosen,binding=self._parts(p,p['parts'],c)
        definition=validate_layout(verified_layout(row['system_id'],chosen),row['size'],row['system_id'])
        obj={'name':p['name'].strip(),'definition':definition,'parts':p['parts'],'trace_id':binding[0],'frame_sha256':binding[1]}
        obj['id']=digest({'source':row['sha256'],**obj})[:32]
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);saved=objects_for(owned)
            same=next((r for r in saved if r['name'].casefold()==obj['name'].casefold()),None)
            if same and same['id']!=obj['id']:raise ValueError('An object already uses this name. Choose another name or delete the old layout.')
            saved=[r for r in saved if r['id']!=obj['id']]
            if len(saved)>=64:raise ValueError('This source already has 64 objects. Remove an old layout first.')
            if c():raise KeyboardInterrupt
            projects._measure(path,row,cancelled=c);owned['object_layouts']={'source_sha256':row['sha256'],'objects':saved+[obj]};projects.write_json(project/'project.json',store)
        return {'ok':True,'object_id':obj['id'],'object':obj,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'rom_written':False}
    def list(self,p,c):
        _,row,_=self.api.source(p)
        return {'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'objects':[{'object_id':o['id'],'name':o['name'],'columns':o['definition']['layout']['columns'],'rows':o['definition']['layout']['rows'],'parts':sum(i is not None for i in o['definition']['layout']['indices']),'trace_id':o['trace_id']} for o in objects_for(row)]}
    def get(self,p,c):
        _,row,_=self.api.source(p);projects.identifier(p['object_id']);obj=next((o for o in objects_for(row) if o['id']==p['object_id']),None)
        if obj is None:raise ValueError('Choose a saved object from this exact revision.')
        fresh=False
        if obj['parts']:
            try:
                chosen,binding=self._parts(p,obj['parts'],c)
                fresh=(binding[:2]==(obj['trace_id'],obj['frame_sha256']) and digest(verified_layout(row['system_id'],chosen))==digest(obj['definition']))
            except (ValueError,OSError,KeyError,TypeError):pass
        return {'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'object_id':obj['id'],'object':obj,'source_dependency_verified':fresh,'runtime_trusted':fresh}
    def open(self,p,c):
        result=self.get(p,c);obj=result['object'];declared=self.api._declare_resource({**p,'config':obj['definition']['config']},c,'assets')
        layout={**obj['definition']['layout'],'provenance':'causal_replay' if result['source_dependency_verified'] else 'checked_declaration'}
        return {**declared,'layout':layout,'object_id':obj['id'],'object_name':obj['name'],'object_definition':obj['definition'],'trace_id':obj['trace_id'],
            'source_dependency_verified':result['source_dependency_verified'],'historical_layout':not result['source_dependency_verified'],
            'scope':'Saved exact-revision layout. A grouped object name is an author label, not an inferred game role.'}
    def delete(self,p,c):
        project,row,path=self.api.source(p);projects.identifier(p['object_id'])
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);saved=objects_for(owned);kept=[o for o in saved if o['id']!=p['object_id']]
            if len(kept)==len(saved):raise ValueError('That object has already been removed.')
            if c():raise KeyboardInterrupt
            projects._measure(path,row,cancelled=c);owned['object_layouts']={'source_sha256':row['sha256'],'objects':kept};projects.write_json(project/'project.json',store)
        return {'ok':True,'rom_written':False}
    def scene(self,p,c):
        from .scene_composite import composite
        from .asset_codecs import decode_cell
        result=self.get(p,c)
        if not result['source_dependency_verified']:raise ValueError('Verify this object from a fresh local trace before using its scene preview.')
        obj=result['object'];trace=self.api.traces.get({**p,'trace_id':obj['trace_id']},c)
        if not trace.get('runtime_trusted'):raise ValueError('Capture a fresh authenticated local scene before using this preview.')
        scene=trace.get('scene')
        if not scene or scene['sha256']!=obj['frame_sha256']:raise ValueError('Capture a fresh trace with the full scene, then verify the object again.')
        project,row,path=self.api.source(p);projects._measure(path,row,cancelled=c);cfg=obj['definition']['config'];unit=cell_size(cfg['codec'],8,8)
        used={i for i in obj['definition']['layout']['indices'] if i is not None};tiles={}
        with path.open('rb') as source:
            for index in used:
                source.seek(cfg['offset']+index*unit);raw=source.read(unit)
                if len(raw)!=unit:raise ValueError('Object source tiles changed.')
                tiles[index]=decode_cell(raw,codec=cfg['codec'],width=8,height=8)
        projects._measure(path,row,cancelled=c)
        return {**composite(scene,obj['definition'],tiles,p['edits']),'object_id':obj['id'],'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'scene_region':obj['definition']['scene_region']}
