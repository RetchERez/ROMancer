"""Original bounded reader for a fingerprinted Wario Land4 M4A revision.

Format research: lilDavid/warioland4, commit abb7800a8d8fa6d7f7f003627893e06bc2879329.
No game code, samples or sequences are distributed in this module.
"""
import hashlib,math
from .asset_schema import fields,number
from .script_schema import canonical_bytes
from .sound_codecs import wav_bytes

REFERENCE='https://github.com/lilDavid/warioland4/tree/abb7800a8d8fa6d7f7f003627893e06bc2879329'
DRIVER='wl4-m4a-v1'
FINGERPRINTS=((0x9540c,144,'281a78b9fc456c120773e66e6429a81cf8e461c37b6ae3ae7caedfd70e4e5efb'),(0x1540,388,'c161eede6cb0db8fef5c94f4190456e9d1bb3340d6ee1f59ed07d7c294e5acf3'),(0x1710,616,'01d066a726009c17f1e1db0e166afcefff674e6ff4e0f857fac18adc26d61edc'))
# Individually checked table entries and header/track-pointer hashes, not a guessed catalog.
CATALOG=(
 (617,'Wario’s Workout',0x244720,3,'a5e7385d67c8e17222c21735498f42c397f618d332cb259b5568cb5ecdb9e05b','9a16742c119af016e8cbe73eac801c27a4284564857cb082cdd2902cd16a59f1'),
 (618,'Sound Room',0x2447e8,1,'8cc1f8cbdad13ee0127b27f8b4ec2e946777439640f792ed24ce5c3b4cd0b417','729e5c8b99046ae66597e6b17801161616118e3c5ac3e531dc433eab284ad36d'),
 (635,'Opening cutscene',0x2507a8,7,'9806e2438fbdce0fd9656599358e5221ef8c0960cfd3caa433d7734e815503a4','38b61d3af55a4ea2699d7e95db40ff164c9fa44d2eb474bec25800ee39296c37'),
 (639,'Level Select',0x25369c,4,'0c4d64c5842f8f4cf6eccb592eb3ed62ba99de43147d39cd0bc84636779ba507','f102a855b2f1d30c2eb178af1fe87494b1da8c01d52e8d49bd786b816800dc1e'),
 (651,'Palm Tree Paradise',0x254bb8,9,'97a73ed6311ceb3d5cba0c1a9430778c33e01ff89ec55fd4998874a426b7ecb4','4696c81d30cbf451c0a41e79cb84b475d95c07653569ac17f2b0fd9ef78f5382'))
CLOCK=tuple(range(25))+(28,30,32,36,40,42,44,48,52,54,56,60,64,66,68,72,76,78,80,84,88,90,92,96)
CONTROL_HASHES={617:'58a26dc7e0237dc6fa7ab0a4fda0c2dbf9286c12f18bf4e5bc05d6da1656d7a9',618:'b08620bc19d555c5e9a6f6435f70b2d7355d6e7f05cfe53135065894f90cce9f',635:'0a10aafbad9508b646738698ff925734caf63887f5b051ea1dcea89cebd028ee',639:'ebf5324162dd004a76196af6ce7989a8ff04381c2d038e60dce1cec3ebca87e4',651:'a60cb5b3eb7719136d143e7be8dcf1e7f52bab62fc2780e7bf37bf96190b7282'}

def identified(raw):
    return type(raw) is bytes and len(raw)==8388608 and all(hashlib.sha256(raw[at:at+size]).hexdigest()==digest for at,size,digest in FINGERPRINTS)

def decode_track(raw,start,low,high,*,instruction_limit=4096,tick_limit=3072):
    """Bounded control-flow walk. Unsupported conditional behavior disables editing."""
    pc=start;status=0;stack=[];repeat=0;tick=0;key=None;velocity=None;keyshift=0;channel_volume=127;tempo=150
    events=[];roles={};issues=[];seen=set();termination='budget';steps=0
    def take(n,role):
        nonlocal pc
        if not low<=pc<high or pc+n>high:raise ValueError('Track reads outside its checked sequence allocation.')
        at=pc;pc+=n
        for offset in range(at,pc):
            old=roles.get(offset)
            if old is not None and old!=role:raise ValueError('A track byte has conflicting opcode or operand roles.')
            roles[offset]=role
        return at,raw[at:pc]
    def pointer():
        _,data=take(4,'pointer');target=int.from_bytes(data,'little')-0x08000000
        if not low<=target<high:raise ValueError('Track pointer leaves its checked sequence allocation.')
        return target
    try:
        while steps<instruction_limit and tick<=tick_limit:
            if not low<=pc<high:raise ValueError('Track pointer leaves its checked sequence allocation.')
            state=(pc,status,tuple(stack),repeat,key,velocity,keyshift,channel_volume,tempo)
            if state in seen:termination='loop';break
            seen.add(state);steps+=1;at=pc;opcode=raw[pc]
            if opcode>=0x80:
                take(1,'opcode')
                if opcode>=0xbd:status=opcode
            else:
                if status<0xbd:raise ValueError('Running status appears before a supported command.')
                opcode=status
            if 0x80<=opcode<=0xb0:tick+=CLOCK[opcode-0x80];continue
            if opcode in (0xb1,0xb6,0xb7,0xb8,0xc6,0xc7,0xc9,0xca,0xcb):termination='fine';break
            if opcode==0xb2:pc=pointer();continue
            if opcode==0xb3:
                target=pointer()
                if len(stack)>=3:raise ValueError('Pattern stack exceeds this driver’s three-level limit.')
                stack.append(pc);pc=target;continue
            if opcode==0xb4:
                if stack:pc=stack.pop()
                continue
            if opcode==0xb5:
                _,count=take(1,'repeat_count');target=pointer()
                if count[0]==0:pc=target
                else:
                    repeat+=1
                    if repeat<count[0]:pc=target
                    else:repeat=0
                continue
            if opcode==0xb9:raise ValueError('MEMACC depends on live memory; this song stays read-only.')
            if opcode in (0xba,0xbb,0xbc,0xbd,0xbe,0xbf,0xc0,0xc1,0xc2,0xc3,0xc4,0xc5,0xc8):
                role='tempo' if opcode==0xbb else 'channel_volume' if opcode==0xbe else 'parameter'
                offset,value=take(1,role);value=value[0]
                if opcode==0xbc:keyshift=value-256 if value>127 else value
                if opcode in (0xbb,0xbe):
                    if value>127 or opcode==0xbb and value==0:raise ValueError('Tempo or volume is outside the supported editing range.')
                    if opcode==0xbb:tempo=value*2
                    else:channel_volume=value
                    events.append({'kind':role,'tick':tick,'note':None,'duration':0,'volume':None,'channel_volume':value if opcode==0xbe else None,'tempo':value if opcode==0xbb else None,'tempo_bpm':tempo if opcode==0xbb else None,'editable_fields':[role],'edit_offsets':{role:offset},'offset':at})
                continue
            if opcode==0xcc:take(2,'port_parameter');continue
            if opcode==0xcd:
                _,sub=take(1,'extended_command');sub=sub[0]
                if sub in (0,3):termination='extended_end';break
                if sub==1:pointer()
                elif sub==2 or 4<=sub<=11:take(1,'extended_parameter')
                else:raise ValueError('Unmapped extended command; this song stays read-only.')
                continue
            if opcode==0xce:
                if pc<high and raw[pc]<0x80:take(1,'end_key')
                continue
            if 0xcf<=opcode<=0xff:
                offsets={};extra=0
                for role in ('note','volume','gate'):
                    if pc>=high or raw[pc]>=0x80:break
                    offset,value=take(1,role);value=value[0]
                    if role=='note':key=value;offsets[role]=offset
                    elif role=='volume':velocity=value;offsets[role]=offset
                    else:extra=value
                duration=CLOCK[opcode-0xcf]+extra
                if key is None or velocity is None:raise ValueError('A note inherits an uninitialized key or velocity; this song stays read-only.')
                events.append({'kind':'note','tick':tick,'note':key,'duration':duration,'volume':velocity,'channel_volume':channel_volume,'key_shift':keyshift,'tempo':tempo,'tied':opcode==0xcf,'editable_fields':list(offsets),'edit_offsets':offsets,'offset':at})
                continue
            raise ValueError('Unmapped music opcode; this song stays read-only.')
        else:raise ValueError('Track exceeds its instruction or playback-tick budget.')
    except ValueError as error:issues.append(str(error))
    return {'events':events,'roles':roles,'issues':issues,'termination':termination,'instructions':steps,'ticks':tick}

def inspect_song(raw,song_id,source_sha256):
    if not identified(raw):raise ValueError('This M4A engine revision is not identified.')
    if hashlib.sha256(raw).hexdigest()!=source_sha256:raise ValueError('Music source differs.')
    row=next((r for r in CATALOG if str(r[0])==str(song_id)),None)
    if row is None:raise ValueError('Choose an individually verified song.')
    ident,name,header,count,header_hash,table_hash=row;entry=0x98028+ident*8
    if hashlib.sha256(raw[header:header+8+4*count]).hexdigest()!=header_hash or hashlib.sha256(raw[entry:entry+8]).hexdigest()!=table_hash:raise ValueError('Song header, bank or track pointers differ from the checked layout.')
    events=[];issues=[];roles={};tracks=[]
    for index in range(count):
        start=int.from_bytes(raw[header+8+index*4:header+12+index*4],'little')-0x08000000
        track=decode_track(raw,start,0x999c0,0x283ef8);tracks.append({'index':index,'offset':start,'termination':track['termination'],'instructions':track['instructions'],'ticks':track['ticks']})
        issues.extend('Track '+str(index+1)+': '+issue for issue in track['issues'])
        for offset,role in track['roles'].items():
            if offset in roles and roles[offset]!=role:issues.append('Tracks interpret a shared byte differently; editing is disabled.')
            roles[offset]=role
        events.extend({**event,'channel':index,'instrument':None} for event in track['events'])
    if len(events)>2048:raise ValueError('Decoded song exceeds its 2048-event display budget.')
    control=hashlib.sha256(canonical_bytes([[offset,role,raw[offset]] for offset,role in sorted(roles.items()) if role not in ('note','volume','tempo','channel_volume')],max_bytes=1024**2)).hexdigest()
    if control!=CONTROL_HASHES[ident]:issues.append('Sequence commands, pointers or protected parameters differ from the checked song. Editing is disabled.')
    events.sort(key=lambda event:(event['tick'],event['channel'],event['offset']))
    definition={'id':str(ident),'name':name,'driver':DRIVER,'offset':header,'count':len(events),'stride':0,'tempo':0,'ticks_per_beat':24,'channels':count}
    signature=hashlib.sha256(canonical_bytes({'source':source_sha256,'song':definition},max_bytes=128*1024)).hexdigest()
    return {**definition,'events':events,'tracks':tracks,'issues':list(dict.fromkeys(issues)),'sequence_edit_supported':not issues,'document_id':signature,'definition':definition,'source_sha256':source_sha256,'driver_scope':'Checked Wario Land4 M4A layout. Only explicit note, velocity, channel volume and tempo bytes can be edited; shared patterns affect every use.','reference':REFERENCE,'roles':roles}

def plan_song(raw,definition,document_id,changes,source_sha256):
    song=inspect_song(raw,definition.get('id'),source_sha256)
    if definition!=song['definition'] or document_id!=song['document_id']:raise ValueError('Music review is stale or its layout differs.')
    if not song['sequence_edit_supported']:raise ValueError('This sequence is read-only: '+'; '.join(song['issues']))
    if type(changes) is not list or not 1<=len(changes)<=256:raise ValueError('Review1 to256 explicit music values.')
    writes={}
    for change in changes:
        fields(change,'kind song_id index field value')
        if change['kind']!='note' or change['song_id']!=song['id']:raise ValueError('Music edit references another song.')
        number(change['index'],0,len(song['events'])-1);event=song['events'][change['index']];field=change['field']
        if field not in event['editable_fields']:raise ValueError('This value is inherited or protected; choose an explicit editable event.')
        number(change['value'],1 if field=='tempo' else 0,127);offset=event['edit_offsets'][field];value=change['value']
        if offset in writes and writes[offset]!=value:raise ValueError('Shared pattern edits request conflicting values for one byte.')
        writes[offset]=value
    edits=[{'offset':offset,'before':raw[offset:offset+1].hex(),'after':bytes([value]).hex()} for offset,value in sorted(writes.items()) if raw[offset]!=value]
    if not edits:raise ValueError('No changed music bytes.')
    return {'ok':True,'edits':edits,'document_id':document_id}

def reference_preview(song):
    rate=22050;limit=rate*20;values=[0.0]*limit;used=0
    tempos=[(e['tick'],e['tempo']*2) for e in song['events'] if e['kind']=='tempo']
    def seconds(tick):
        total=0;previous=0;tempo=150
        for at,value in tempos:
            if at>tick:break
            total+=(at-previous)*60/(tempo*24);previous=at;tempo=value
        return total+(tick-previous)*60/(tempo*24)
    # Deliberately a note sketch, not a reimplementation of samples, envelopes or mixing.
    for event in song['events']:
        if event['kind']!='note':continue
        start=round(seconds(event['tick'])*rate);duration=min(2,seconds(event['tick']+event['duration'])-seconds(event['tick']));end=min(limit,start+round(duration*rate))
        if start>=limit:continue
        frequency=440*2**((event['note']+event['key_shift']-69)/12);gain=event['volume']/127*event['channel_volume']/127*2200/max(1,song['channels']**.5)
        for i in range(start,end):values[i]+=math.sin(2*math.pi*(i-start)*frequency/rate)*gain
        used=max(used,end)
    return wav_bytes([max(-32768,min(32767,round(value))) for value in values[:max(1,used)]],rate),{'kind':'song','sample_rate':rate,'sample_frames':max(1,used),'truncated':True,'preview_scope':'Reference note sketch, up to20seconds. Instruments, ties, envelopes, pitch modulation and exact tempo changes are not emulated. Record native audio to hear the game.'}
