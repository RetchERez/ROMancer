"""Reviewed relocation of explicitly declared data and linear references.

Does not discover every consumer or move position-dependent code. Reservations
and reference completeness are author declarations, not inferred from padding.
"""
import hashlib
from pathlib import Path
from .asset_schema import fields,number
from .debugger_protocol import _rom_regions
from .release_scope import require_supported
from .workbench_evidence import store_evidence

MAX_DATA=48*1024


def prepare_edits(raw,system,spec,replacement=None,*,cancelled=lambda:False):
    if cancelled():raise KeyboardInterrupt
    if type(raw) is not bytes or not 1<=len(raw)<=64*1024**2:raise ValueError('Choose a supported cartridge up to 64 MiB.')
    fields(spec,'source_offset source_length target_offset target_capacity fill_byte alignment bank_size bank_origin references references_complete destination_reserved replacement_input_id')
    if spec['references_complete'] is not True:raise ValueError('Declare all references for this move; numeric search alone cannot establish completeness.')
    if spec['destination_reserved'] is not True:raise ValueError('Explicitly reserve the destination; fill bytes do not prove unused space.')
    start=number(spec['source_offset'],0,len(raw)-1);length=number(spec['source_length'],1,MAX_DATA)
    target=number(spec['target_offset'],0,len(raw)-1);capacity=number(spec['target_capacity'],1,MAX_DATA)
    fill=number(spec['fill_byte'],0,255);alignment=spec['alignment']
    if type(alignment) is not int or alignment not in (1,2,4,8,16,32):raise ValueError('Choose a supported power-of-two alignment.')
    if start%alignment or target%alignment:raise ValueError('Source and destination must satisfy the declared alignment.')
    if start+length>len(raw) or target+capacity>len(raw):raise ValueError('The allocation extends beyond the cartridge.')
    if start<target+capacity and target<start+length:raise ValueError('Source and destination allocations overlap.')
    if system in ('nes','snes'):
        regions=_rom_regions(raw,system);region=regions.get('nesPrgRom' if system=='nes' else 'snesPrgRom')
        if region is None:raise ValueError('The cartridge payload layout is unresolved.')
        low,extent=region
        if min(start,target)<low or max(start+length,target+capacity)>low+extent:raise ValueError('This move must stay inside the identified CPU ROM payload.')
    elif system in ('gb','gbc','gba','genesis','sms'):
        minimum={'gb':0x150,'gbc':0x150,'gba':0xc0,'genesis':0x200,'sms':0x100}[system]
        if min(start,target)<minimum:raise ValueError('Data relocation cannot use this cartridge boot/header extent.')
    else:raise ValueError('Choose a supported cartridge system.')
    bank=number(spec['bank_size'],0,65536);origin=number(spec['bank_origin'],0,len(raw)-1)
    if system in ('nes','snes','gb','gbc','sms') and not bank:raise ValueError('Banked systems require an explicit same-bank constraint.')
    protected=[(0,0x100)]+[(at,at+16) for at in (0x1ff0,0x3ff0,0x7ff0) if raw[at:at+8]==b'TMR SEGA'] if system=='sms' else []
    if any(a<end and begin<b for a,b in protected for begin,end in ((start,start+length),(target,target+capacity))):raise ValueError('Data relocation overlaps protected SMS boot or header bytes.')
    if bank:
        if bank not in (8192,16384,32768,65536) or min(start,target)<origin:raise ValueError('Choose a supported declared bank window and origin.')
        banks={(point-origin)//bank for point in (start,start+length-1,target,target+capacity-1)}
        if len(banks)!=1:raise ValueError('The allocations cross the declared bank boundary. Cross-bank relocation is unavailable.')
    elif origin:raise ValueError('A linear allocation uses bank origin zero.')
    if raw[target:target+capacity]!=bytes([fill])*capacity:raise ValueError('The reserved destination no longer contains the expected fill bytes.')
    payload=raw[start:start+length] if replacement is None else replacement
    if type(payload) is not bytes or not 1<=len(payload)<=capacity:raise ValueError('Replacement data must fit the reserved destination.')
    refs=spec['references']
    if type(refs) is not list or not 1<=len(refs)<=128:raise ValueError('Declare 1 to 128 linear references.')
    occupied=[];edits=[];updates=[]
    for ref in refs:
        if cancelled():raise KeyboardInterrupt
        fields(ref,'offset width endian base target_delta')
        width=number(ref['width'],2,4);offset=number(ref['offset'],0,len(raw)-width)
        if any(offset<b and a<offset+width for a,b in protected):raise ValueError('References overlap protected SMS boot or header bytes.')
        delta=number(ref['target_delta'],0,min(length,len(payload))-1);base=number(ref['base'],-0xffffffff,0xffffffff)
        if ref['endian'] not in ('little','big'):raise ValueError('Choose a supported reference byte order.')
        if any(offset<b and a<offset+width for a,b in [(start,start+length),(target,target+capacity),*occupied]):
            raise ValueError('References overlap one another or a resource allocation. Embedded references are unavailable.')
        occupied.append((offset,offset+width));before=raw[offset:offset+width]
        expected=start+delta+base;after=target+delta+base
        if not 0<=expected<2**(width*8) or int.from_bytes(before,ref['endian'])!=expected:raise ValueError('Reference before-bytes do not point to the declared source and interior offset.')
        if not 0<=after<2**(width*8):raise ValueError('The destination reference cannot be represented in its declared width.')
        encoded=after.to_bytes(width,ref['endian'])
        edits.append({'offset':offset,'before':before.hex(),'after':encoded.hex()})
        updates.append({'offset':offset,'width':width,'before':expected,'after':after,'target_delta':delta,'base':base,'endian':ref['endian']})
    for index in range(0,len(payload),4096):
        before=raw[target+index:target+index+min(4096,len(payload)-index)];after=payload[index:index+4096]
        if before!=after:edits.append({'offset':target+index,'before':before.hex(),'after':after.hex()})
    return {'edits':sorted(edits,key=lambda row:row['offset']),
        'relocation':{'source_offset':start,'source_length':length,'target_offset':target,'target_capacity':capacity,
            'payload_size':len(payload),'payload_sha256':hashlib.sha256(payload).hexdigest(),'pointer_updates':updates,
            'reference_coverage':'author-declared-complete','destination_scope':'author-reserved; expected fill checked',
            'bank_constraint':{'size':bank,'origin':origin,'scope':'author-declared'},'original_extent_preserved':True,
            'all_references_observed':False,'game_semantics_verified':False,'native_verified':False,
            'position_dependent_code_supported':False,'scope':'Fixed-size cartridge; external linear references only. Playtest the separate build before release.'}}


class RelocationTools:
    def __init__(self,api):self.api=api

    def routes(self):return {'relocation.plan':('project_id artifact_id spec',self.plan),
        'relocation.table_definition':('project_id artifact_id',self.table_definition)}

    def table_definition(self,p,c):
        import copy
        from . import workbench_projects as projects
        from .data_tables import validate_definition,inspect_table
        project,row,path=self.api.source(p);require_supported(row);meta=row.get('plan_annotations')
        if not isinstance(meta,dict) or meta.get('kind')!='declared-data-relocation-v1' or not row.get('source_id'):
            raise ValueError('Select a build made by a reviewed data relocation.')
        parent=projects.artifact(project,row['source_id']);projects._measure(parent['path'],parent,cancelled=c)
        saved=parent.get('descriptors',{}).get('tables')
        if not isinstance(saved,dict) or saved.get('source_sha256')!=parent['sha256']:raise ValueError('The parent has no source-bound table declaration to move.')
        definition=copy.deepcopy(validate_definition(saved['definition'],parent['size']))
        if any(field['pointer_base'] is not None for field in definition['fields']):raise ValueError('Pointer-bearing table layouts need a fresh declaration after relocation.')
        start=number(meta['source_offset'],0,parent['size']-1);length=number(meta['source_length'],1,MAX_DATA)
        target=number(meta['target_offset'],0,row['size']-1);payload_size=number(meta['payload_size'],1,MAX_DATA)
        if start+length>parent['size'] or target+payload_size>row['size']:raise ValueError('Relocation metadata exceeds its artifact bounds.')
        old=definition['offset'];extent=definition['count']*definition['stride']
        if old<start or old+extent>start+length or old-start+extent>payload_size:raise ValueError('The declared table is not wholly covered by the moved payload.')
        with path.open('rb') as stream:stream.seek(target);payload=stream.read(payload_size)
        if len(payload)!=payload_size or hashlib.sha256(payload).hexdigest()!=meta['payload_sha256']:raise ValueError('Moved payload differs from its relocation record.')
        definition['offset']=target+old-start
        labels=definition.get('label_source')
        if labels:
            first=labels['offset'];end=first+(definition['count']-1)*labels['stride']+labels['length']
            if first<start+length and start<end:
                if first<start or end>start+length or end-start>payload_size:raise ValueError('The label layout only partly overlaps the moved extent.')
                labels['offset']=target+first-start
        inspection=inspect_table(path,row['sha256'],definition,0,8)
        return {'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'definition':definition,
            'inspection':inspection,'definition_saved':False,'game_semantics_verified':False,
            'scope':'Checked rebase of the parent neutral numeric declaration. Original count and field layout retained; review replacement-format changes before saving.'}

    def plan(self,p,c):
        from .workbench_files import input_file,read_bounded
        from . import workbench_projects as projects
        project,row,path=self.api.source(p);require_supported(row)
        if type(p['spec']) is not dict:raise ValueError('Provide the declared relocation fields.')
        replacement=None;input_id=p['spec'].get('replacement_input_id')
        if input_id is not None:
            owned,resource=input_file(project,input_id,'resource');replacement=read_bounded(resource,MAX_DATA,owned,cancelled=c)
        raw=read_bounded(Path(path),64*1024**2,row,cancelled=c)
        prepared=prepare_edits(raw,row['system_id'],p['spec'],replacement,cancelled=c)
        del raw
        result=self.api._integrity_plan({**p,'edits':prepared['edits']},c,
            annotations={'kind':'declared-data-relocation-v1',**prepared['relocation']})
        projects._measure(path,row,cancelled=c)
        record=store_evidence(project,'coverage',{'kind':'declared-data-relocation-v1','source_sha256':row['sha256'],
            'artifact_id':row['artifact_id'],'plan_id':result['plan_id'],'relocation':prepared['relocation'],
            'replacement_input_id':input_id,'evidence_scope':'static checks and author declarations; no native execution'})
        return {**result,'artifact_id':row['artifact_id'],'evidence_id':record['evidence_id'],'relocation':prepared['relocation']}
