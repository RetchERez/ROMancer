"""Move growing declared text with control preservation and explicit references."""
import copy,hashlib
from .asset_schema import fields,number
from .assets import digest
from .script import inspect_script,parse_slot
from .script_schema import validate_schema,canonical_bytes
from .data_relocation import prepare_edits,MAX_DATA
from .release_scope import require_supported
from .workbench_files import read_bounded
from . import workbench_projects as projects

def serialize_record(row,fmt,changes,capacity):
    if row['read_only_reasons'] or any(not c['position_independent'] for c in fmt['controls']):raise ValueError('Only fully decoded, position-independent text can be moved.')
    if type(changes) is not list or not 1<=len(changes)<=256:raise ValueError('Supply1–256 edited text segments.')
    glyphs={g['text']:g['byte'] for g in fmt['encoding']['glyphs']};values={}
    for change in changes:
        fields(change,'segment text');index=number(change['segment'],0,len(row['segments'])-1)
        if index in values or type(change['text']) is not str or len(change['text'])>65536:raise ValueError('Text segments repeat or exceed their bounds.')
        try:values[index]=bytes(glyphs[c] for c in change['text'])
        except KeyError:raise ValueError('Text contains a character absent from this encoding; control codes cannot be inserted.') from None
    chunks=[];index=0
    for token in row['tokens']:
        if token['kind']=='text':chunks.append(values.get(index,bytes.fromhex(token['raw_hex'])));index+=1
        elif token['kind'] in ('control','terminator'):chunks.append(bytes.fromhex(token['raw_hex']))
    body=b''.join(chunks)
    if len(body)>capacity:raise ValueError('The growing text exceeds the reserved capacity.')
    payload=body+bytes([fmt['padding']['byte']])*(capacity-len(body))
    final=parse_slot(payload,{**{k:row[k] for k in ('id','offset','annotations')},'capacity':capacity},fmt)
    if final['read_only_reasons'] or [t['raw_hex'] for t in row['tokens'] if t['kind']=='control']!=[t['raw_hex'] for t in final['tokens'] if t['kind']=='control']:raise ValueError('Moved text does not preserve its checked control sequence.')
    return payload,final,len(body)

def moved_schema(schema,row,path,record_id,target,capacity):
    d=copy.deepcopy(schema);rules={r['resource']:r for r in d['profile']['rules']};record=next(r for r in d['format']['records'] if r['id']==record_id)
    rules[record['rule']].update(offset=target,length=capacity);d['profile']['accepted_sha256']=[row['sha256']]
    with path.open('rb') as stream:
        for rule in rules.values():
            number(rule['offset'],0,row['size']-1);number(rule['length'],1,row['size']-rule['offset']);stream.seek(rule['offset']);rule['expected_hex']=stream.read(rule['length']).hex()
    return validate_schema(d)['normalized_schema']

class TextGrowthTools:
    def __init__(self,api):self.api=api
    def routes(self):
        keys='project_id artifact_id schema document_id record_id changes destination'
        return {'text.grow.preview':(keys,self.preview),'text.grow.plan':(keys+' review_id',self.plan),'text.grow.definition':('project_id artifact_id',self.definition)}
    def _prepare(self,p,c):
        project,row,path=self.api.source(p);require_supported(row);canonical_bytes(p['schema'],max_bytes=512*1024)
        doc=inspect_script(path,p['schema'])
        if not doc.get('ok') or not doc.get('write_supported') or doc['document_id']!=p['document_id']:raise ValueError('Inspect the exact current writable text layout before growing a record.')
        d=validate_schema(p['schema'])['normalized_schema'];record=next((r for r in doc['records'] if r['id']==p['record_id']),None)
        if record is None:raise ValueError('Choose a current text record.')
        dest=p['destination'];fields(dest,'offset capacity fill_byte alignment bank_size bank_origin extra_references references_complete destination_reserved')
        capacity=number(dest['capacity'],record['capacity']+1,MAX_DATA);target=number(dest['offset'],0,row['size']-capacity)
        payload,final,required=serialize_record(record,d['format'],p['changes'],capacity)
        rules={r['resource']:r for r in d['profile']['rules']};refs=[]
        for pointer in d['format']['pointers']:
            if pointer['target_record']==record['id']:refs.append({'offset':rules[pointer['rule']]['offset'],'width':pointer['width'],'endian':pointer['endian'],'base':-pointer['base'],'target_delta':0})
        if type(dest['extra_references']) is not list or len(dest['extra_references'])>128:raise ValueError('Declare at most128 additional references.')
        if any(type(ref) is not dict or type(ref.get('target_delta')) is not int or ref['target_delta']!=0 for ref in dest['extra_references']):raise ValueError('Growing text supports record-start references only; interior segment offsets can shift.')
        refs+=dest['extra_references']
        for old in rules.values():
            if target<old['offset']+old['length'] and old['offset']<target+capacity:raise ValueError('Reserved text capacity overlaps a declared text or pointer range.')
        from .research_tools import _resources
        resources,issues,_=_resources(row,path,c)
        if issues:raise ValueError('Some saved layouts are stale. Review them before reserving space for growing text.')
        if any(target<r['offset']+r['length'] and r['offset']<target+capacity for r in resources):raise ValueError('Reserved text capacity overlaps another declared resource.')
        raw=read_bounded(path,64*1024**2,row,cancelled=c)
        spec={'source_offset':record['offset'],'source_length':record['capacity'],'target_offset':target,'target_capacity':capacity,'fill_byte':dest['fill_byte'],'alignment':dest['alignment'],'bank_size':dest['bank_size'],'bank_origin':dest['bank_origin'],'references':refs,'references_complete':dest['references_complete'],'destination_reserved':dest['destination_reserved'],'replacement_input_id':None}
        prepared=prepare_edits(raw,row['system_id'],spec,payload,cancelled=c)
        # The proposed full schema must also remain non-overlapping and parse exactly.
        candidate=bytearray(raw)
        for e in prepared['edits']:candidate[e['offset']:e['offset']+len(e['before'])//2]=bytes.fromhex(e['after'])
        new=copy.deepcopy(d);newrules={r['resource']:r for r in new['profile']['rules']};newrecord=next(r for r in new['format']['records'] if r['id']==record['id']);newrules[newrecord['rule']].update(offset=target,length=capacity)
        for rule in newrules.values():rule['expected_hex']=candidate[rule['offset']:rule['offset']+rule['length']].hex()
        validate_schema(new)
        review=digest({'document':doc['document_id'],'record_id':record['id'],'changes':p['changes'],'destination':dest,'payload_sha256':hashlib.sha256(payload).hexdigest(),'spec':spec})
        result={'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'review_id':review,'record_id':record['id'],'required_bytes':required,'capacity':capacity,'text_preview':'\n'.join(s['text'] for s in final['segments']),'controls_preserved':True,'pointer_updates':prepared['relocation']['pointer_updates'],'relocation':prepared['relocation'],'rom_modified':False}
        return result,prepared['edits'],{'kind':'text-relocation-v1','schema':d,'record_id':record['id'],'target_offset':target,'capacity':capacity,'payload_sha256':hashlib.sha256(payload).hexdigest()}
    def preview(self,p,c):return self._prepare(p,c)[0]
    def plan(self,p,c):
        review,edits,annotations=self._prepare(p,c)
        if review['review_id']!=p['review_id']:raise ValueError('The text or destination changed. Preview growth again.')
        return {**self.api._integrity_plan({**p,'edits':edits},c,annotations=annotations),**review,'status':'PLANNED'}
    def definition(self,p,c):
        _,row,path=self.api.source(p);meta=row.get('plan_annotations',{})
        if meta.get('kind')!='text-relocation-v1':raise ValueError('Select the build created by reviewed text growth.')
        with path.open('rb') as stream:stream.seek(meta['target_offset']);payload=stream.read(meta['capacity'])
        if hashlib.sha256(payload).hexdigest()!=meta['payload_sha256']:raise ValueError('Moved text differs from its reviewed payload.')
        d=moved_schema(meta['schema'],row,path,meta['record_id'],meta['target_offset'],meta['capacity']);inspection=inspect_script(path,d)
        if not inspection.get('write_supported'):raise ValueError('The moved text cannot reopen in its checked layout.')
        projects._measure(path,row,cancelled=c);return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'schema':d,'inspection':inspection,'definition_saved':False}
