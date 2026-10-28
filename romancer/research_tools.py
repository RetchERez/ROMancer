"""Checked portable research metadata. User notes never grant ROM-edit authority."""
import hashlib
import json
import uuid
from .asset_schema import fields,label,number
from .script_schema import canonical_bytes
from . import workbench_projects as projects

KINDS=('assets','script','tables','levels','sound','commands')
CATEGORIES=('graphics','text','numbers','level','sound','code','other')
PACK_LIMIT=1024**2


def _note(value,size):
    fields(value,'id title offset length category text reference')
    if type(value['id']) is not str or len(value['id'])!=32:raise ValueError('Invalid research note identity.')
    projects.identifier(value['id']);label(value['title'],80);label(value['reference'],512,blank=True)
    number(value['offset'],0,size-1);number(value['length'],1,size-value['offset'])
    if value['category'] not in CATEGORIES:raise ValueError('Choose a research category, not a verification claim.')
    text=value['text']
    if type(text) is not str or len(text)>2000 or any((ord(c)<32 and c not in '\n\r\t') or 127<=ord(c)<160 for c in text):raise ValueError('Research text must be at most 2000 characters without control bytes.')
    return json.loads(canonical_bytes(value,max_bytes=16*1024))


def _notes(values,size):
    if type(values) is not list or len(values)>256:raise ValueError('A source supports at most 256 research notes.')
    rows=[_note(n,size) for n in values]
    if len({n['id'] for n in rows})!=len(rows):raise ValueError('Duplicate research note identities.')
    return rows


def notes_for(row):
    stored=row.get('research_notes')
    if stored is None:return []
    fields(stored,'format source_sha256 notes')
    if stored['format']!='romancer-notes-v1' or stored['source_sha256']!=row['sha256']:raise ValueError('Research notes belong to another source revision.')
    return _notes(stored['notes'],row['size'])


def revision(row):
    raw=canonical_bytes({'descriptors':row.get('descriptors',{}),'notes':notes_for(row),'objects':row.get('object_layouts'),'animations':row.get('animation_layouts')},max_bytes=projects.MAX_STORE)
    return hashlib.sha256(raw).hexdigest()


def _store_notes(row,notes):
    row['research_notes']={'format':'romancer-notes-v1','source_sha256':row['sha256'],'notes':notes}


def note_summaries(notes):
    return [{**n,'text':n['text'][:128],'reference':n['reference'][:128]} for n in notes[:50]]


def _definition(row,path,kind):
    from .workflow_recipes import definition_document
    value=row.get('descriptors',{}).get(kind)
    if kind=='tables':
        if value.get('source_sha256')!=row['sha256']:raise ValueError('Table source differs.')
        value=value['definition']
    return definition_document(path,row['sha256'],kind,value)['definition']


def _resources(row,path,cancelled,maximum=4096):
    number(maximum,1,16384)
    resources=[];issues=[];total=0
    def add(kind,name,offset,length):
        nonlocal total
        number(offset,0,row['size']-1);number(length,1,row['size']-offset);total+=1
        if len(resources)<maximum:resources.append({'name':str(name)[:160],'kind':kind,'offset':offset,'length':length,'editor':{'script':'scripts','tables':'tables','assets':'assets','levels':'levels','sound':'sound','commands':'debug'}[kind]})
    for kind in KINDS:
        if cancelled():raise KeyboardInterrupt
        if not row.get('descriptors',{}).get(kind):continue
        before=len(resources);previous=total
        try:
            d=_definition(row,path,kind)
            if kind=='assets':
                for group in ('bitmaps','palettes','tilemaps'):
                    for r in d[group]:add(kind,r['id']+' / '+group,r['offset'],r['length'])
            elif kind=='script':
                from .script import inspect_script
                for r in inspect_script(path,d)['records']:add(kind,r['id'],r['offset'],r['capacity'])
            elif kind=='tables':add(kind,d['name'],d['offset'],d['count']*d['stride'])
            else:
                from .workbench_files import read_bounded
                raw=read_bounded(path,64*1024**2,row,cancelled=cancelled)
                if kind=='levels':
                    from .level_design import inspect_level
                    spans=inspect_level(raw,d,row['sha256'])['ranges']
                elif kind=='commands':
                    from .command_editor import inspect_commands
                    spans=inspect_commands(raw,d,row['sha256'],cancelled=cancelled)['ranges']
                else:
                    from .sound_studio import inspect_sound
                    spans=inspect_sound(raw,d,row['sha256'])['ranges']
                for r in spans:add(kind,r['name'],r['offset'],r['length'])
        except (ValueError,KeyError,TypeError,OSError):
            resources[before:]=[];total=previous
            issues.append({'kind':kind,'message':'Saved definition cannot inspect this revision. Reopen its editor and correct or replace the declaration.'})
    return resources,issues,total


class ResearchTools:
    def __init__(self,api):self.api=api

    def routes(self):
        return {'research.inspect':('project_id artifact_id query kind page',self.inspect),
                'research.note_save':('project_id artifact_id revision note',self.note_save),
                'research.note_delete':('project_id artifact_id revision note_id',self.note_delete),
                'research.note_get':('project_id artifact_id note_id',self.note_get),
                'research.export':('project_id artifact_id',self.export),
                'research.preview':('project_id artifact_id document',self.preview),
                'research.apply':('project_id artifact_id document review_id replace',self.apply)}

    def _public(self,row):
        notes=notes_for(row)
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'revision':revision(row),
                'notes':note_summaries(notes),'notes_total':len(notes),'notes_truncated':len(notes)>50,'note_summaries':True,
                'game_semantics_verified':False,'write_authorized':False}

    def inspect(self,p,c):
        _,row,path=self.api.source(p);label(p['query'],128,blank=True);number(p['page'],0,4096)
        if p['kind'] not in ('all','notes',*KINDS):raise ValueError('Choose an available resource kind.')
        rows,issues,total=_resources(row,path,c);query=p['query'].casefold()
        resources=[r for r in rows if p['kind'] in ('all',r['kind']) and query in r['name'].casefold()]
        notes=[n for n in notes_for(row) if p['kind'] in ('all','notes') and query in (n['title']+' '+n['text']+' '+n['reference']).casefold()]
        start=p['page']*50;projects._measure(path,row,cancelled=c)
        return {**self._public(row),'notes':note_summaries(notes[start:start+50]),'notes_total':len(notes),
                'resources':resources[start:start+50],'resources_total':len(resources),'page':p['page'],
                'partial':total>len(rows),'declared_ranges':total,'issues':issues,'limit':50}

    def note_get(self,p,c):
        _,row,_=self.api.source(p);projects.identifier(p['note_id'])
        note=next((n for n in notes_for(row) if n['id']==p['note_id']),None)
        if note is None:raise ValueError('Research note no longer exists.')
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'revision':revision(row),'note':note,'write_authorized':False}

    def note_save(self,p,c):
        project,row,path=self.api.source(p);value=p['note']
        if type(value) is not dict:raise ValueError('Enter a research note.')
        ident=value.get('id');note=_note({**value,'id':uuid.uuid4().hex if ident is None else ident},row['size'])
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id'])
            if revision(owned)!=p['revision']:raise ValueError('Research or resource setup changed. Reload before saving.')
            notes=notes_for(owned)
            if ident is not None and not any(n['id']==ident for n in notes):raise ValueError('Research note no longer exists.')
            notes=[n for n in notes if n['id']!=note['id']]+[note];_notes(notes,row['size'])
            if c():raise KeyboardInterrupt
            projects._measure(path,row,cancelled=c);_store_notes(owned,notes);projects.write_json(project/'project.json',store)
        return self._public(owned)

    def note_delete(self,p,c):
        project,row,path=self.api.source(p);projects.identifier(p['note_id'])
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id'])
            if revision(owned)!=p['revision']:raise ValueError('Research changed. Reload before removing a note.')
            old=notes_for(owned);notes=[n for n in old if n['id']!=p['note_id']]
            if len(old)==len(notes):raise ValueError('Research note no longer exists.')
            if c():raise KeyboardInterrupt
            projects._measure(path,row,cancelled=c);_store_notes(owned,notes);projects.write_json(project/'project.json',store)
        return self._public(owned)

    def export(self,p,c):
        project,row,path=self.api.source(p);definitions={}
        for kind in KINDS:
            if c():raise KeyboardInterrupt
            if row.get('descriptors',{}).get(kind):definitions[kind]=_definition(row,path,kind)
        document={'format':'romancer-research-v1','source':{'sha256':row['sha256'],'size':row['size'],'system_id':row.get('system_id')},
                  'definitions':definitions,'notes':notes_for(row)}
        from .object_workbench import portable_objects
        objects=portable_objects(row)
        if objects:document.update(format='romancer-research-v2',objects=objects)
        from .animation_layouts import animations_for
        animations=animations_for(row,path)
        if animations:document.update(format='romancer-research-v3',objects=objects,animations=animations)
        canonical_bytes(document,max_bytes=PACK_LIMIT);projects._measure(path,row,cancelled=c)
        return self.api._export_declaration(project,document,c)

    def _review(self,row,path,document,c):
        from .workflow_recipes import definition_document
        document=json.loads(canonical_bytes(document,max_bytes=PACK_LIMIT));fields(document,'format source definitions notes'+(' objects' if document.get('format') in ('romancer-research-v2','romancer-research-v3') else '')+(' animations' if document.get('format')=='romancer-research-v3' else ''))
        if document['format'] not in ('romancer-research-v1','romancer-research-v2','romancer-research-v3'):raise ValueError('Choose a ROMancer research pack.')
        fields(document['source'],'sha256 size system_id')
        if document['source']!={'sha256':row['sha256'],'size':row['size'],'system_id':row.get('system_id')}:raise ValueError('Research pack requires the exact matching ROM revision and system.')
        defs=document['definitions']
        if type(defs) is not dict or set(defs)-set(KINDS):raise ValueError('Research pack contains unsupported definitions.')
        checked={};replacements=[];existing=row.get('descriptors',{})
        for kind in KINDS:
            if c():raise KeyboardInterrupt
            if kind in defs:
                checked[kind]=definition_document(path,row['sha256'],kind,defs[kind])['definition']
                if existing.get(kind) is not None:replacements.append(kind+' definition')
        incoming=_notes(document['notes'],row['size']);old={n['id']:n for n in notes_for(row)}
        from .object_workbench import review_objects
        objects,object_replacements=review_objects(row,document.get('objects',[]));replacements.extend(object_replacements)
        from .animation_layouts import review_animations
        animations=review_animations(row,path,document.get('animations',[]))
        for n in incoming:
            if n['id'] in old and old[n['id']]!=n:replacements.append('note: '+n['title'])
            old[n['id']]=n
        _notes(list(old.values()),row['size'])
        normalized={**document,'definitions':checked,'notes':incoming}
        review_id=hashlib.sha256(canonical_bytes({'document':normalized,'revision':revision(row)},max_bytes=2*1024**2)).hexdigest()
        projects._measure(path,row,cancelled=c)
        return normalized,list(old.values()),{'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],
                 'review_id':review_id,'definitions':list(checked),'notes':[{k:n[k] for k in ('id','title','offset','length','category')} for n in incoming[:50]],'notes_truncated':len(incoming)>50,'replacements':replacements,
                 'note_count':len(incoming),'merged_note_count':len(old),'object_count':len(document.get('objects',[])),'merged_object_count':len(objects),'animation_count':len(document.get('animations',[])),'merged_animation_count':len(animations),'write_authorized':False,'game_semantics_verified':False,
                 'scope':'Checked declarations and user research only. No ROM bytes are changed.'}

    def preview(self,p,c):
        _,row,path=self.api.source(p);return self._review(row,path,p['document'],c)[2]

    def apply(self,p,c):
        project,row,path=self.api.source(p)
        if type(p['replace']) is not bool:raise ValueError('Choose whether to replace the listed research.')
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id'])
            document,notes,review=self._review(owned,path,p['document'],c)
            if review['review_id']!=p['review_id']:raise ValueError('Research or import document changed. Review this pack again.')
            if review['replacements'] and not p['replace']:raise ValueError('Acknowledge the listed replacements before importing.')
            descriptors=owned.setdefault('descriptors',{})
            for kind,d in document['definitions'].items():descriptors[kind]={'source_sha256':row['sha256'],'definition':d} if kind=='tables' else d
            if document['definitions'].get('assets',{}).get('fonts'):
                from .resource_forms import font_schema_from_assets
                descriptors['font']=font_schema_from_assets(document['definitions']['assets'])
            _store_notes(owned,notes)
            if 'objects' in document:
                from .object_workbench import review_objects
                objects,_=review_objects(owned,document['objects']);owned['object_layouts']={'source_sha256':row['sha256'],'objects':objects}
            if 'animations' in document:
                from .animation_layouts import review_animations
                animations=review_animations(owned,path,document['animations']);owned['animation_layouts']={'source_sha256':row['sha256'],'animations':animations}
            if c():raise KeyboardInterrupt
            projects._measure(path,row,cancelled=c);projects.write_json(project/'project.json',store)
        return {**self._public(owned),'status':'IMPORTED','definitions':review['definitions']}
