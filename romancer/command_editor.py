"""Original fixed-operand bytecode editor for explicit source-bound grammars.

Decodes declared commands, not arbitrary CPU code. No script is executed here.
"""
import hashlib,json
from .asset_schema import fields,label,number
from .script_schema import canonical_bytes
from .assets import digest

ROLES=('action','dialogue','sound','room','collision','animation','branch','end')

def inspect_commands(raw,definition,sha,*,cancelled=lambda:False):
    if type(raw) is not bytes or not 1<=len(raw)<=64*1024**2 or hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Command source revision differs.')
    d=json.loads(canonical_bytes(definition,max_bytes=128*1024));fields(d,'schema_version source_sha256 name scripts commands');number(d['schema_version'],1,1);label(d['name'],80)
    if d['source_sha256']!=sha:raise ValueError('Command definition belongs to another source.')
    if type(d['commands']) is not list or not 1<=len(d['commands'])<=256 or type(d['scripts']) is not list or not 1<=len(d['scripts'])<=32:raise ValueError('Declare 1–256 commands and 1–32 scripts.')
    opcodes={}
    for command in d['commands']:
        fields(command,'opcode name length role fields');opcode=number(command['opcode'],0,255);label(command['name'],80);length=number(command['length'],1,32)
        if opcode in opcodes or command['role'] not in ROLES:raise ValueError('Duplicate opcode or unsupported command role.')
        if type(command['fields']) is not list or len(command['fields'])>8:raise ValueError('Use at most 8 named operands per command.')
        names=set();occupied={0}
        for f in command['fields']:
            fields(f,'name offset bytes endian minimum maximum target_base');label(f['name'],64)
            if f['name'].casefold() in names:raise ValueError('Command operand names must be unique.')
            names.add(f['name'].casefold());width=number(f['bytes'],1,4);at=number(f['offset'],1,length-1)
            if f['endian'] not in ('little','big') or at+width>length:raise ValueError('Operand byte order or bounds are invalid.')
            span=set(range(at,at+width))
            if span&occupied:raise ValueError('Command operands overlap.')
            occupied|=span;low=number(f['minimum'],0,(1<<(width*8))-1);number(f['maximum'],low,(1<<(width*8))-1)
            if f['target_base'] is not None:number(f['target_base'],-0xffffffff,0xffffffff)
        opcodes[opcode]=command
    scripts=[];ranges=[];ids=set();total=0
    for script in d['scripts']:
        if cancelled():raise KeyboardInterrupt
        fields(script,'id name offset length');label(script['id'],64);label(script['name'],80);at=number(script['offset'],0,len(raw)-1);length=number(script['length'],1,4096);end=at+length
        if end>len(raw) or script['id'] in ids or any(at<b and a<end for a,b in ranges):raise ValueError('Script allocations overlap, repeat or exceed source bounds.')
        ids.add(script['id']);ranges.append((at,end));commands=[];issues=[];finished=False
        while at<end and len(commands)<256 and total<2048:
            if cancelled():raise KeyboardInterrupt
            cmd=opcodes.get(raw[at])
            if cmd is None:issues.append('Unknown opcode '+hex(raw[at])+' at '+hex(at)+'. Declare its verified format before editing.');break
            if at+cmd['length']>end:issues.append('Truncated '+cmd['name']+' at '+hex(at)+'.');break
            values=[]
            for f in cmd['fields']:
                offset=at+f['offset'];data=raw[offset:offset+f['bytes']];value=int.from_bytes(data,f['endian']);target=None if f['target_base'] is None else value-f['target_base']
                if not f['minimum']<=value<=f['maximum']:issues.append(f['name']+' is outside its declared range at '+hex(offset)+'.')
                values.append({**f,'offset':offset,'value':value,'raw_hex':data.hex(),'target_offset':target if target is not None and 0<=target<len(raw) else None})
            commands.append({'index':len(commands),'offset':at,'opcode':cmd['opcode'],'name':cmd['name'],'role':cmd['role'],'length':cmd['length'],'fields':values});total+=1;at+=cmd['length']
            if cmd['role']=='end':finished=True;break
        if not finished:issues.append('No declared end command reached within the allocation and command budget.')
        scripts.append({**script,'commands':commands,'issues':issues,'editable':not issues,'decoded_bytes':at-script['offset']})
    return {'ok':True,'source_sha256':sha,'definition':d,'document_id':digest({'source_sha256':sha,'definition':d}),
        'scripts':scripts,'ranges':[{'offset':s['offset'],'length':s['length'],'name':s['name']} for s in d['scripts']],
        'game_semantics_verified':False,'scope':'Explicit command grammar and operand bounds. Names and roles are declarations; runtime behavior requires playtesting.'}

def plan_commands(raw,definition,document_id,changes,sha,*,cancelled=lambda:False):
    doc=inspect_commands(raw,definition,sha,cancelled=cancelled)
    if doc['document_id']!=document_id:raise ValueError('Command review is stale. Inspect this exact layout again.')
    if type(changes) is not list or not 1<=len(changes)<=256:raise ValueError('Review1–256 operand changes.')
    edits=[];seen=set()
    for change in changes:
        fields(change,'script_id command_index field before after');script=next((s for s in doc['scripts'] if s['id']==change['script_id']),None)
        if script is None or not script['editable']:raise ValueError('Choose a fully decoded declared script.')
        index=number(change['command_index'],0,len(script['commands'])-1);cmd=script['commands'][index];f=next((f for f in cmd['fields'] if f['name']==change['field']),None)
        if f is None:raise ValueError('Only declared fixed operands can be changed; opcodes are protected.')
        number(change['before'],f['minimum'],f['maximum']);number(change['after'],f['minimum'],f['maximum'])
        if change['before']!=f['value'] or f['offset'] in seen:raise ValueError('Operand before-value differs or this operand was changed twice.')
        seen.add(f['offset'])
        if change['after']!=change['before']:edits.append({'offset':f['offset'],'before':f['raw_hex'],'after':change['after'].to_bytes(f['bytes'],f['endian']).hex()})
    if not edits:raise ValueError('No command operands changed.')
    return {'ok':True,'document_id':document_id,'edits':edits,'game_semantics_verified':False}

class CommandTools:
    def __init__(self,api):self.api=api
    def routes(self):return {'commands.inspect':('project_id artifact_id definition',self.inspect),
        'commands.plan':('project_id artifact_id definition document_id changes',self.plan)}
    def inspect(self,p,c):
        _,row,raw=self.api.studio.source(p,c);return inspect_commands(raw,p['definition'],row['sha256'],cancelled=c)
    def plan(self,p,c):
        _,row,raw=self.api.studio.source(p,c);result=plan_commands(raw,p['definition'],p['document_id'],p['changes'],row['sha256'],cancelled=c)
        return {**self.api.studio.plan(p,result['edits'],c),'document_id':result['document_id'],'game_semantics_verified':False}
