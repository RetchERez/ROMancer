"""Bounded structural experiments over source bytes, without game-name rules.

An in-bounds numeric run is a hypothesis. It does not establish dereferences,
record meanings, complete boundaries, or a game's active bank mapping.
"""
import hashlib
import math
import re
from .asset_schema import number
from .data_tables import validate_definition
from .script_schema import canonical_bytes


def survey(raw,source_sha256,system,offset,file_size,*,max_positions=16384,max_results=32,cancelled=lambda:False):
    if type(raw) is not bytes or not 1<=len(raw)<=65536:raise ValueError('Choose a structural window of 1 to 65536 bytes.')
    if type(source_sha256) is not str or re.fullmatch('[0-9a-f]{64}',source_sha256) is None:raise ValueError('invalid source identity')
    if system not in ('nes','snes','genesis','gb','gbc','gba'):raise ValueError('choose a supported cartridge system')
    number(file_size,1,64*1024**2);number(offset,0,file_size-len(raw));number(max_positions,16,16384);number(max_results,1,64)
    stride=math.ceil(len(raw)/max_positions);window_sha=hashlib.sha256(raw).hexdigest()
    candidates=[];tested=0;total=0
    for width in (4,3,2):
        bases=(0,0x08000000,0x0a000000,0x0c000000) if system=='gba' and width==4 else (0,)
        for endian in ('little','big'):
            for base in bases:
                for record_stride in (width,width*2,width*4):
                    covered={}
                    for position in range(0,max(0,len(raw)-record_stride*3-width+1),stride):
                        if tested%256==0 and cancelled():raise KeyboardInterrupt
                        phase=position%record_stride
                        if position<covered.get(phase,0):continue
                        tested+=1;values=[];targets=[]
                        for row in range(64):
                            start=position+row*record_stride
                            if start+record_stride>len(raw):break
                            value=int.from_bytes(raw[start:start+width],endian);target=value-base
                            if not 0<=target<file_size:break
                            values.append(value);targets.append(target)
                            # Flat padding is not a useful start of an experiment.
                            # A varying suffix can still be tested at a later start.
                            if row==3 and len(set(targets))==1:break
                        if len(values)<4 or len(set(targets))<3:continue
                        end=offset+position+len(values)*record_stride
                        if any(offset+position<=target<end for target in targets):continue
                        samples=[]
                        for row,(value,target) in enumerate(zip(values[:8],targets[:8])):
                            local=target-offset;preview=None
                            if 0<=local<len(raw):
                                text=raw[local:min(local+24,len(raw))].split(b'\0',1)[0]
                                if len(text)>=3 and all(32<=b<=126 for b in text):preview=text.decode('ascii')
                            samples.append({'index':row,'offset':offset+position+row*record_stride,
                                'stored_value':value,'target_offset':target,'target_preview':preview})
                        candidate={'offset':offset+position,'count':len(values),'stride':record_stride,'width':width,
                            'endian':endian,'base':base,'samples':samples,'confidence':'CANDIDATE',
                            'format':'numeric-record-run','dereference_observed':False,
                            'boundary_scope':'At most 64 consecutive records were tested. The run may be part of a larger or different structure.',
                            'interpretation':'Distinct numeric values stay within file bounds after the stated subtraction. Pointer use and record meanings are unverified.'}
                        identity={'source_sha256':source_sha256,'window_sha256':window_sha,'window_offset':offset,
                            'window_length':len(raw),**{k:candidate[k] for k in ('offset','count','stride','width','endian','base')}}
                        candidate['candidate_id']=hashlib.sha256(canonical_bytes(identity,max_bytes=4096)).hexdigest()
                        rank=(0 if base else 1,-sum(s['target_preview'] is not None for s in samples),-width,-len(values),offset+position,record_stride,endian,base)
                        total+=1;candidates.append((rank,candidate));candidates.sort(key=lambda row:row[0]);del candidates[max_results:]
                        covered[phase]=position+len(values)*record_stride
    return {'ok':True,'source_sha256':source_sha256,'system_id':system,'window_sha256':window_sha,
        'candidates':[c for _,c in candidates],'total_candidates':total,'truncated':total>max_results,
        'coverage':{'offset':offset,'length':len(raw),'position_stride':stride,'positions_tested':tested,
            'maximum_records_per_run':64,'minimum_records_per_run':4,'result_limit':max_results,
            'tested_widths':[2,3,4],'tested_byte_orders':['little','big'],
            'target_content_scope':'Only targets inside this window receive a printable preview. Other targets were checked against file bounds only.'},
        'game_profile_required':False,'write_authorized':False,'dereference_observed':False,
        'next_experiment':'Replay a read watch on a surviving run, compare controlled gameplay states, or open a neutral numeric editor. Do not assign gameplay names until behavior supports them.'}


def table_definition(candidate,size,interpretation='numeric'):
    if interpretation not in ('numeric','linear-pointer'):raise ValueError('Choose neutral numeric values or an explicit linear-pointer hypothesis.')
    width=number(candidate['width'],2,4);stride=number(candidate['stride'],width,16)
    base=number(candidate['base'],0,0xffffffff)
    fields=[{'name':'Value','offset':0,'type':'u'+str(width*8),'endian':candidate['endian'],
        'pointer_base':base if interpretation=='linear-pointer' else None}]
    fields.extend({'name':'Byte '+str(index),'offset':index,'type':'u8','endian':'little','pointer_base':None} for index in range(width,stride))
    return validate_definition({'schema_version':1,'name':'Investigated records at 0x'+format(candidate['offset'],'X'),
        'offset':candidate['offset'],'count':candidate['count'],'stride':stride,'fields':fields},size)
