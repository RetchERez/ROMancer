"""Strict transport for measured debugger video memory, registers and pixels."""
import base64
import hashlib
import re
from .asset_schema import number

SNAPSHOT_DOMAINS={'nes': {'nesPpuMemory': 8192, 'nesSpriteRam': 256, 'nesPaletteRam': 32, 'nesNametableRam': 4096}, 'snes': {'snesVideoRam': 65536, 'snesSpriteRam': 544, 'snesCgRam': 512}, 'gb': {'gbVideoRam': 8192, 'gbSpriteRam': 160}, 'gbc': {'gbVideoRam': 16384, 'gbSpriteRam': 160, 'gbBgPaletteRam': 64, 'gbObjPaletteRam': 64}, 'sms': {'smsVideoRam': 16384, 'smsPaletteRam': 32}, 'genesis': {'genesisVideoRam': 65536, 'genesisColorRam': 128, 'genesisVScrollRam': 80}}


def parse_graphics_record(line,system,state):
    parts=line.split('\t');kind=parts[0]
    if kind not in ('M','SCREEN','S'):return False
    if kind=='M':
        if len(parts)!=4 or parts[1] not in SNAPSHOT_DOMAINS.get(system,{}):raise ValueError('Unsupported graphics memory domain.')
        name=parts[1];size=number(int(parts[2]),1,SNAPSHOT_DOMAINS[system][name]);text=parts[3]
        if re.fullmatch('[0-9a-f]{'+str(size*2)+'}',text) is None:raise ValueError('Graphics bytes differ from their declared length.')
        memory=state.setdefault('memory',{})
        if name in memory:raise ValueError('Duplicate graphics memory snapshot.')
        memory[name]={'size':size,'data_hex':text,'data_sha256':hashlib.sha256(bytes.fromhex(text)).hexdigest()}
    elif kind=='SCREEN':
        if len(parts)!=4 or 'frame' in state:raise ValueError('Invalid or repeated graphics frame.')
        width=number(int(parts[1]),1,1024);height=number(int(parts[2]),1,512)
        if width*height>262144 or re.fullmatch('[0-9a-f]{'+str(width*height*6)+'}',parts[3]) is None:raise ValueError('Graphics pixels exceed bounds or differ from dimensions.')
        raw=bytes.fromhex(parts[3]);state['frame']={'width':width,'height':height,'sha256':hashlib.sha256(raw).hexdigest(),'rgb24_base64':base64.b64encode(raw).decode()}
    else:
        if len(parts)!=4 or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.\[\]]{0,127}',parts[1]):raise ValueError('Invalid graphics state key.')
        values=state.setdefault('state',{})
        if len(values)>=512 or parts[1] in values:raise ValueError('Graphics register snapshot exceeds its budget or repeats a field.')
        if parts[2]=='b' and parts[3] in ('true','false'):value=parts[3]=='true'
        elif parts[2]=='n' and re.fullmatch('-?[0-9]{1,16}',parts[3]):value=number(int(parts[3]),-2**52,2**53-1)
        else:raise ValueError('Invalid graphics register value.')
        values[parts[1]]=value
    return True


def finish_snapshot(state,system):
    memory=state.get('memory',{});expected=SNAPSHOT_DOMAINS[system]
    return {**state,'point':'end_of_capture','system_id':system,'complete_memory_snapshot':all(memory.get(n,{}).get('size')==size for n,size in expected.items()),
        'missing_or_partial_domains':[n for n,size in expected.items() if memory.get(n,{}).get('size')!=size],'write_authorized':False,
        'scope':'Measured video memory and decoded screen at capture end. Mid-frame bank, palette and layer changes can differ from this snapshot; sprite ownership and ROM dataflow are not inferred.'}
