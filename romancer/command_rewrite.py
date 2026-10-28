"""Reflow fully declared linear scripts inside a confirmed fixed allocation."""
import hashlib,copy
from .asset_schema import fields,number
from .assets import digest
from .command_editor import inspect_commands
from . import workbench_projects as projects

def preview_stream(raw,definition,document_id,script_id,items,fill_byte,no_interior_references,sha):
    doc=inspect_commands(raw,definition,sha)
    if doc['document_id']!=document_id:raise ValueError('The command document changed. Inspect it again.')
    if no_interior_references is not True:raise ValueError('Confirm that no outside consumer enters the middle of this linear script.')
    fill=number(fill_byte,0,255);script=next((s for s in doc['scripts'] if s['id']==script_id),None)
    if script is None or not script['editable']:raise ValueError('Choose a fully decoded declared script.')
    if type(items) is not list or not 1<=len(items)<=256:raise ValueError('Use1–256 known commands including one final end.')
    grammar={cmd['opcode']:cmd for cmd in doc['definition']['commands']}
    def checked(cmd):
        if cmd['role']=='branch' or any(f['target_base'] is not None for f in cmd['fields']):raise ValueError('Branch and pointer-bearing scripts need their verified relocation format; linear reflow is unavailable.')
        covered={0}
        for f in cmd['fields']:covered.update(range(f['offset'],f['offset']+f['bytes']))
        if covered!=set(range(cmd['length'])):raise ValueError('Declare every stored command byte before inserting or reordering commands.')
    for old in script['commands']:checked(grammar[old['opcode']])
    start=script['offset'];capacity=script['length'];tail=raw[start+script['decoded_bytes']:start+capacity]
    if tail!=bytes([fill])*len(tail):raise ValueError('The bytes after the original end are not the confirmed allocation fill.')
    output=bytearray();summary=[]
    for index,item in enumerate(items):
        fields(item,'opcode values');opcode=number(item['opcode'],0,255);cmd=grammar.get(opcode)
        if cmd is None:raise ValueError('Only opcodes in the checked grammar can be inserted.')
        checked(cmd)
        if (cmd['role']=='end')!=(index==len(items)-1):raise ValueError('The linear stream must have exactly one end at its final command.')
        values=item['values']
        if type(values) is not dict or set(values)!={f['name'] for f in cmd['fields']}:raise ValueError('Supply exactly the declared named operands.')
        encoded=bytearray(cmd['length']);encoded[0]=opcode
        for f in cmd['fields']:
            value=number(values[f['name']],f['minimum'],f['maximum']);encoded[f['offset']:f['offset']+f['bytes']]=value.to_bytes(f['bytes'],f['endian'])
        summary.append({'name':cmd['name'],'offset':start+len(output),'values':values});output.extend(encoded)
        if len(output)>capacity:raise ValueError('The rewritten commands exceed the confirmed script allocation.')
    used=len(output);output.extend(bytes([fill])*(capacity-used));before=raw[start:start+capacity]
    candidate=bytearray(raw);candidate[start:start+capacity]=output;nextsha=hashlib.sha256(candidate).hexdigest();nextd={**doc['definition'],'source_sha256':nextsha};roundtrip=inspect_commands(bytes(candidate),nextd,nextsha)
    checked_script=next(s for s in roundtrip['scripts'] if s['id']==script_id)
    if not checked_script['editable'] or len(checked_script['commands'])!=len(items):raise ValueError('Rewritten commands do not independently inspect as declared.')
    edits=[] if output==before else [{'offset':start,'before':before.hex(),'after':output.hex()}]
    return {'ok':True,'source_sha256':sha,'document_id':document_id,'script_id':script_id,'used_bytes':used,'free_bytes':capacity-used,'capacity':capacity,'commands':summary,'edits':edits,'payload_sha256':hashlib.sha256(output).hexdigest(),'game_semantics_verified':False,'review_id':digest({'document':document_id,'script_id':script_id,'items':items,'fill_byte':fill,'no_interior_references':no_interior_references}),'rom_modified':False}

class CommandRewriteTools:
    def __init__(self,api):self.api=api
    def routes(self):
        keys='project_id artifact_id definition document_id script_id items fill_byte no_interior_references'
        return {'commands.rewrite.preview':(keys,self.preview),'commands.rewrite.plan':(keys+' review_id',self.plan),'commands.rewrite.definition':('project_id artifact_id',self.definition)}
    def _prepare(self,p,c):
        _,row,raw=self.api.studio.source(p,c);return preview_stream(raw,p['definition'],p['document_id'],p['script_id'],p['items'],p['fill_byte'],p['no_interior_references'],row['sha256'])
    def preview(self,p,c):return self._prepare(p,c)
    def plan(self,p,c):
        result=self._prepare(p,c)
        if result['review_id']!=p['review_id']:raise ValueError('Commands or allocation changed. Preview them again.')
        if not result['edits']:raise ValueError('The rewritten script makes no byte changes.')
        annotations={'kind':'command-stream-rewrite-v1','definition':copy.deepcopy(p['definition']),'script_id':p['script_id'],'payload_sha256':result['payload_sha256']}
        return {**result,**self.api._integrity_plan({**p,'edits':result['edits']},c,annotations=annotations),'rom_modified':False}
    def definition(self,p,c):
        _,row,raw=self.api.studio.source(p,c);meta=row.get('plan_annotations',{})
        if meta.get('kind')!='command-stream-rewrite-v1':raise ValueError('Select a reviewed command-sequence build.')
        d=copy.deepcopy(meta['definition']);d['source_sha256']=row['sha256'];doc=inspect_commands(raw,d,row['sha256']);s=next((s for s in doc['scripts'] if s['id']==meta['script_id']),None)
        if s is None or not s['editable'] or hashlib.sha256(raw[s['offset']:s['offset']+s['length']]).hexdigest()!=meta['payload_sha256']:raise ValueError('Rewritten script differs from its reviewed payload.')
        return {'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'definition':d,'inspection':doc,'definition_saved':False}
