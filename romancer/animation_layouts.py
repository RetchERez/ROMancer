"""Portable exact-source animation arrangements; no runtime timing is inferred."""
import copy
import re
from collections import Counter
from .asset_schema import fields,label,number
from .assets import digest,inspect_assets
from .script_schema import canonical_bytes
from . import workbench_projects as projects

def frames_checked(frames,bitmap):
    if type(frames) is not list or not 1<=len(frames)<=32:raise ValueError('Save1–32 explicitly arranged animation frames.')
    result=[]
    for frame in frames:
        if type(frame) is not dict or set(frame)-{'first','columns','rows','order','indices','tiles','flips','colors','provenance','duration'}:raise ValueError('Unknown animation frame field.')
        columns=number(frame.get('columns'),1,8);rows=number(frame.get('rows'),1,8);duration=number(frame.get('duration'),40,2000);first=number(frame.get('first',0),0,bitmap['count']-1);order=frame.get('order','rows')
        if order not in ('rows','columns'):raise ValueError('Choose row or column tile order.')
        indices=frame.get('indices')
        if indices is None:indices=[first+(i if order=='rows' else (i%columns)*rows+i//columns) for i in range(columns*rows)]
        if type(indices) is not list or len(indices)!=rows*columns or all(i is None for i in indices):raise ValueError('Frame tile count differs from its grid.')
        for tile in indices:
            if tile is not None:number(tile,0,bitmap['count']-1)
        if frame.get('tiles') is not None and frame['tiles']!=indices:raise ValueError('Frame tile list differs from its declared placement.')
        flips=frame.get('flips',[0]*len(indices))
        if type(flips) is not list or len(flips)!=len(indices):raise ValueError('Supply one flip value per frame part.')
        for f in flips:number(f,0,3)
        colors=frame.get('colors')
        if colors is not None:
            if type(colors) is not list or len(colors)!=len(indices):raise ValueError('Frame colors differ from its tile count.')
            for group in colors:
                if group is None:continue
                if type(group) is not dict or len(group)>16:raise ValueError('Invalid frame color group.')
                for key,color in group.items():
                    if type(key) is not str or not key.isascii() or not key.isdecimal() or not 0<=int(key)<=15 or type(color) is not list or len(color)!=3:raise ValueError('Invalid declared frame color.')
                    for value in color:number(value,0,255)
        result.append({'first':first,'columns':columns,'rows':rows,'order':order,'indices':list(indices),'flips':list(flips),'colors':copy.deepcopy(colors),'duration':duration,'provenance':'declared_layout'})
    canonical_bytes(result,max_bytes=128*1024);return result

def checked_item(path,row,item):
    fields(item,'id name schema bitmap_id document_id frames'+(' document_version' if 'document_version' in item else ''));label(item['name'],80)
    doc=inspect_assets(path,item['schema'])
    version=item.get('document_version',doc.get('tool_version'))
    if type(version) is not str or not re.fullmatch(r'\d{1,6}\.\d{1,6}\.\d{1,6}',version):raise ValueError('Invalid saved animation document version.')
    expected=digest({'asset_version':1,'tool_version':version,'source_sha256':row['sha256'],'source_size':row['size'],'schema_sha256':doc.get('schema_sha256')})
    if not doc.get('ok') or doc.get('source_sha256')!=row['sha256'] or expected!=item['document_id']:raise ValueError('Animation belongs to another source or graphics document.')
    bitmap=next((b for b in doc['bitmaps'] if b['id']==item['bitmap_id']),None)
    if bitmap is None:raise ValueError('The animation bitmap is missing.')
    value={**item,'frames':frames_checked(item['frames'],bitmap)};value.pop('id')
    ident=digest(value)[:32]
    if item['id']!=ident:raise ValueError('Animation layout identity differs.')
    return {'id':ident,**value}

def animations_for(row,path):
    saved=row.get('animation_layouts')
    if saved is None:return []
    fields(saved,'source_sha256 animations')
    if saved['source_sha256']!=row['sha256'] or type(saved['animations']) is not list or len(saved['animations'])>16:raise ValueError('Animation collection differs from the source or exceeds 16 layouts.')
    values=[checked_item(path,row,v) for v in saved['animations']]
    if len({v['id'] for v in values})!=len(values):raise ValueError('Duplicate animation identities.')
    canonical_bytes(values,max_bytes=512*1024);return values

def review_animations(row,path,incoming):
    if type(incoming) is not list or len(incoming)>16:raise ValueError('Import at most 16 animation layouts.')
    old={a['id']:a for a in animations_for(row,path)}
    for item in incoming:
        checked=checked_item(path,row,item);old[checked['id']]=checked
    if len(old)>16:raise ValueError('The merged animation collection exceeds 16 layouts.')
    values=list(old.values());canonical_bytes(values,max_bytes=512*1024);return values

class AnimationTools:
    def __init__(self,api):self.api=api
    def routes(self):return {'animations.list':('project_id artifact_id',self.list),
        'animations.preview':('project_id artifact_id name bitmap_id document_id frames',self.preview),
        'animations.save':('project_id artifact_id name bitmap_id document_id frames review_id',self.save),
        'animations.get':('project_id artifact_id animation_id',self.get),
        'animations.delete':('project_id artifact_id animation_id',self.delete)}
    def list(self,p,c):
        _,row,path=self.api.source(p)
        return {'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'animations':[{'animation_id':a['id'],'name':a['name'],'frames':len(a['frames']),'bitmap_id':a['bitmap_id']} for a in animations_for(row,path)]}
    def _prepare(self,p,row,path,c):
        from .research_tools import revision
        label(p['name'],80);schema=row.get('descriptors',{}).get('assets')
        if not schema:raise ValueError('Save the current graphics definition before saving its animation.')
        value={k:p[k] for k in ('name','bitmap_id','document_id','frames')};value['schema']=schema
        doc=inspect_assets(path,schema)
        if not doc.get('ok') or p['document_id']!=doc.get('document_id'):raise ValueError('Save and inspect the current source-bound graphics definition first.')
        value['document_version']=doc['tool_version']
        bitmap=next((b for b in doc['bitmaps'] if b['id']==p['bitmap_id']),None)
        if bitmap is None:raise ValueError('Choose a declared bitmap.')
        value['frames']=frames_checked(p['frames'],bitmap);value['id']=digest(value)[:32]
        old=animations_for(row,path)
        if len(old)>=16 and not any(v['id']==value['id'] for v in old):raise ValueError('Delete an unneeded saved animation before adding a seventeenth.')
        if c():raise KeyboardInterrupt
        usage=Counter(tile for f in value['frames'] for tile in set(f['indices']) if tile is not None)
        return value,{'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],
            'review_id':digest({'animation':value,'revision':revision(row)}),'shared_tiles':sorted(k for k,v in usage.items() if v>1),
            'animation':value,'game_semantics_verified':False,'timing_origin':'author_declared','rom_modified':False}
    def preview(self,p,c):
        _,row,path=self.api.source(p);return self._prepare(p,row,path,c)[1]
    def save(self,p,c):
        project,row,path=self.api.source(p)
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);value,review=self._prepare(p,owned,path,c)
            if review['review_id']!=p['review_id']:raise ValueError('The animation or source research changed. Preview it again.')
            old=animations_for(owned,path);old=[v for v in old if v['id']!=value['id']]+[value]
            owned['animation_layouts']={'source_sha256':row['sha256'],'animations':old};projects._measure(path,row,cancelled=c);projects.write_json(project/'project.json',store)
        return {**review,'animation_id':value['id'],'status':'SAVED'}
    def get(self,p,c):
        _,row,path=self.api.source(p);projects.identifier(p['animation_id']);value=next((a for a in animations_for(row,path) if a['id']==p['animation_id']),None)
        if value is None:raise ValueError('This animation is not saved on the selected source.')
        current=inspect_assets(path,value['schema'])
        return {'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'animation':{**value,'document_id':current['document_id'],'document_version':current['tool_version']},'game_semantics_verified':False,'timing_origin':'author_declared'}
    def delete(self,p,c):
        project,row,path=self.api.source(p);projects.identifier(p['animation_id'])
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);old=animations_for(owned,path);kept=[v for v in old if v['id']!=p['animation_id']]
            if len(kept)==len(old):raise ValueError('Choose a current saved animation.')
            if c():raise KeyboardInterrupt
            owned['animation_layouts']={'source_sha256':row['sha256'],'animations':kept};projects.write_json(project/'project.json',store)
        return {'ok':True,'rom_modified':False}
