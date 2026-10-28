"""Local, declarative format knowledge; matches never infer game semantics."""
import copy,hashlib,re,threading
from pathlib import Path
from .asset_schema import fields,label,number
from .assets import checked_path,digest
from .script_schema import canonical_bytes,load_script_json
from . import workbench_projects as projects
from .research_tools import KINDS,_definition
from .release_scope import SYSTEMS,require_supported
from .workflow_recipes import definition_document

PACK_LIMIT=512*1024

def validate_pack(document):
    import json
    p=json.loads(canonical_bytes(document,max_bytes=PACK_LIMIT));fields(p,'format name origin match definitions')
    if p['format']!='romancer-format-pack-v1':raise ValueError('Choose a ROMancer format pack.')
    label(p['name'],80);fields(p['origin'],'sha256 size system_id');number(p['origin']['size'],1,64*1024**2)
    if p['origin']['system_id'] not in SYSTEMS or type(p['origin']['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',p['origin']['sha256']):raise ValueError('Invalid format-pack source identity.')
    fields(p['match'],'mode guards')
    if p['match']['mode'] not in ('exact','guarded'):raise ValueError('Choose exact-source or explicitly guarded matching.')
    guards=p['match']['guards']
    if type(guards) is not list or len(guards)>32 or (p['match']['mode']=='guarded' and not guards) or (p['match']['mode']=='exact' and guards):raise ValueError('Guarded packs need1–32 protected hash regions; exact packs use the complete source hash.')
    end=0;total=0
    for guard in sorted(guards,key=lambda g:g.get('offset',-1) if type(g) is dict else -1):
        fields(guard,'offset length sha256');offset=number(guard['offset'],0,p['origin']['size']-1);length=number(guard['length'],16,min(65536,p['origin']['size']-offset));total+=length
        if offset<end or total>256*1024 or type(guard['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',guard['sha256']):raise ValueError('Protected hash regions overlap, exceed the budget or contain an invalid digest.')
        end=offset+length
    if type(p['definitions']) is not dict or not 1<=len(p['definitions'])<=6 or set(p['definitions'])-set(KINDS):raise ValueError('Use1–6 supported editor definitions.')
    for kind,value in p['definitions'].items():
        if type(value) is not dict:raise ValueError('Editor definitions must be objects.')
        if kind=='script':
            for rule in value.get('profile',{}).get('rules',[]):
                if 'expected_hex' in rule:raise ValueError('Portable text rules omit original ROM bytes; current preconditions are read on preview.')
    return p

def _files(workspace):
    root=checked_path(Path(workspace)/'format-library')
    if not root.exists():return []
    values=sorted(root.glob('*.json'))
    if len(values)>32:raise ValueError('The local format library exceeds32 packs.')
    return [checked_path(p) for p in values]

def library_stamp(workspace):
    rows=[]
    for path in _files(workspace):
        stat=path.stat()
        if stat.st_size>PACK_LIMIT:rows.append([path.name,'oversize',stat.st_size,stat.st_mtime_ns])
        else:rows.append([path.name,hashlib.sha256(path.read_bytes()).hexdigest()])
    return digest(rows)

def _read(path):
    pack=validate_pack(load_script_json(path,max_bytes=PACK_LIMIT))
    if path.stem!=digest(pack):raise ValueError('Installed format-pack content identity differs.')
    return pack

def _rebind(definitions,row,path):
    result=copy.deepcopy(definitions)
    for kind,d in result.items():
        if kind=='assets':d['source']['sha256']=row['sha256'];d['source']['size']=row['size']
        elif kind=='script':
            d['profile']['accepted_sha256']=[row['sha256']];d['artifact']['size']=row['size']
            with path.open('rb') as stream:
                for rule in d['profile']['rules']:
                    offset=number(rule['offset'],0,row['size']-1);length=number(rule['length'],1,row['size']-offset);stream.seek(offset);rule['expected_hex']=stream.read(length).hex()
        elif kind in ('levels','sound','commands'):d['source_sha256']=row['sha256']
    return result

def evaluate(pack,row,path,c):
    origin=pack['origin'];exact=row['sha256']==origin['sha256']
    if row.get('system_id')!=origin['system_id'] or row['size']!=origin['size']:return {'matched':False,'reason':'Console or cartridge size differs.'}
    if pack['match']['mode']=='exact' and not exact:return {'matched':False,'reason':'The complete source SHA-256 differs.'}
    with path.open('rb') as stream:
        for guard in pack['match']['guards']:
            if c():raise KeyboardInterrupt
            stream.seek(guard['offset'])
            if hashlib.sha256(stream.read(guard['length'])).hexdigest()!=guard['sha256']:return {'matched':False,'reason':'A declared protected hash region differs.'}
    try:
        definitions={}
        for kind,value in _rebind(pack['definitions'],row,path).items():
            if c():raise KeyboardInterrupt
            definitions[kind]=definition_document(path,row['sha256'],kind,value)['definition']
    except (ValueError,KeyError,TypeError) as error:return {'matched':False,'reason':'An editor cannot inspect this layout: '+str(error)[:240]}
    projects._measure(path,row,cancelled=c)
    return {'matched':True,'exact_source':exact,'definitions':definitions}

def scan_library(workspace,row,path,cancelled=lambda:False):
    matches=[];issues=0;checked=0;paths=_files(workspace)
    for entry in paths:
        if cancelled():raise KeyboardInterrupt
        try:
            p=_read(entry)
            # Only matching identities/guards reach the bounded actual decoders.
            result=evaluate(p,row,Path(path),cancelled);checked+=1
            if result['matched']:matches.append({'pack_id':entry.stem,'name':p['name'],'exact_source':result['exact_source'],'kinds':list(result['definitions']),'confidence':'checked_declaration'})
        except (ValueError,OSError):issues+=1
        if len(matches)>=8:break
    return {'matches':matches,'checked':checked,'total':len(paths),'partial':checked+issues<len(paths),'invalid_packs':issues,'applied':False,'game_semantics_verified':False}

class FormatLibrary:
    def __init__(self,api):self.api=api;self.lock=threading.RLock()
    def routes(self):return {'formats.create':('project_id artifact_id name mode guards',self.create),'formats.install':('document',self.install),'formats.list':('',self.list),'formats.preview':('project_id artifact_id pack_id',self.preview),'formats.apply':('project_id artifact_id pack_id review_id replace accept_guarded',self.apply),'formats.delete':('pack_id',self.delete),'formats.export':('project_id pack_id',self.export)}
    def _path(self,ident):
        projects.identifier(ident)
        if len(ident)!=64:raise ValueError('Choose a content-addressed format pack.')
        return checked_path(self.api.workspace/'format-library'/(ident+'.json'))
    def create(self,p,c):
        _,row,path=self.api.source(p);require_supported(row);number(row['size'],1,64*1024**2);definitions={k:_definition(row,path,k) for k in KINDS if row.get('descriptors',{}).get(k)}
        if 'script' in definitions:
            for rule in definitions['script']['profile']['rules']:rule.pop('expected_hex',None)
        if type(p['guards']) is not list or len(p['guards'])>32:raise ValueError('Use at most32 protected ranges.')
        guards=[]
        with path.open('rb') as stream:
            for g in p['guards']:
                if c():raise KeyboardInterrupt
                fields(g,'offset length');offset=number(g['offset'],0,row['size']-1);length=number(g['length'],16,min(65536,row['size']-offset));stream.seek(offset);guards.append({**g,'sha256':hashlib.sha256(stream.read(length)).hexdigest()})
        pack=validate_pack({'format':'romancer-format-pack-v1','name':p['name'],'origin':{k:row[k] for k in ('sha256','size','system_id')},'match':{'mode':p['mode'],'guards':guards},'definitions':definitions})
        projects._measure(path,row,cancelled=c);return {'ok':True,'document':pack,'pack_id':digest(pack),'installed':False,'rom_modified':False}
    def install(self,p,c):
        pack=validate_pack(p['document']);ident=digest(pack)
        with self.lock:
            paths=_files(self.api.workspace);path=self._path(ident)
            if len(paths)>=32 and path not in paths:raise ValueError('Delete a pack before installing a thirty-third.')
            if c():raise KeyboardInterrupt
            path.parent.mkdir(exist_ok=True);projects.write_json(path,pack,max_bytes=PACK_LIMIT)
        return {'ok':True,'pack_id':ident,'name':pack['name'],'rom_modified':False}
    def list(self,p,c):
        values=[]
        for path in _files(self.api.workspace):
            if c():raise KeyboardInterrupt
            try:
                pack=_read(path);values.append({'pack_id':path.stem,'name':pack['name'],'mode':pack['match']['mode'],'system_id':pack['origin']['system_id'],'kinds':list(pack['definitions']),'valid':True})
            except (ValueError,OSError):values.append({'pack_id':path.stem,'name':'Invalid local format pack','valid':False})
        return {'ok':True,'packs':values,'revision':library_stamp(self.api.workspace),'executable_plugins':False}
    def _prepare(self,p,c):
        _,row,path=self.api.source(p);pack=_read(self._path(p['pack_id']));matched=evaluate(pack,row,path,c)
        if not matched['matched']:return None,{'ok':True,**matched,'pack_id':p['pack_id'],'name':pack['name'],'rom_modified':False}
        document={'format':'romancer-research-v1','source':{k:row[k] for k in ('sha256','size','system_id')},'definitions':matched['definitions'],'notes':[]}
        _,_,review=self.api.research._review(row,path,document,c)
        return document,{**review,'pack_id':p['pack_id'],'name':pack['name'],'matched':True,'exact_source':matched['exact_source'],'match_mode':pack['match']['mode'],'research_review_id':review['review_id'],'review_id':digest({'pack_id':p['pack_id'],'research_review':review['review_id']}),'rom_modified':False}
    def preview(self,p,c):
        with self.lock:return self._prepare(p,c)[1]
    def apply(self,p,c):
        if type(p['replace']) is not bool or type(p['accept_guarded']) is not bool:raise ValueError('Choose explicit replacement and guarded-layout acknowledgements.')
        with self.lock:
            document,review=self._prepare(p,c)
            if document is None or review['review_id']!=p['review_id']:raise ValueError('The format pack, source or current editor metadata changed. Preview again.')
            if not review['exact_source'] and not p['accept_guarded']:raise ValueError('Acknowledge that guarded compatibility is an author declaration, not native proof.')
            result=self.api.research.apply({**p,'document':document,'review_id':review['research_review_id']},c)
        return {**result,'pack_id':p['pack_id'],'rom_modified':False,'game_semantics_verified':False}
    def delete(self,p,c):
        with self.lock:
            path=self._path(p['pack_id'])
            if c():raise KeyboardInterrupt
            path.unlink()
        return {'ok':True,'rom_modified':False}
    def export(self,p,c):
        pack=_read(self._path(p['pack_id']));return self.api._export_declaration(self.api.project(p),pack,c)
