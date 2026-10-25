"""Original NES room renderer and one-channel event player for editor practice."""
import hashlib,math
from .asset_codecs import encode_cell


def make_studio_example():
    raw=bytearray(16+16384+8192);raw[:6]=b'NES\x1a\x01\x01'
    code=bytearray();labels={};fixups=[]
    def emit(*values):code.extend(values)
    def mark(name):labels[name]=0x8000+len(code)
    def branch(op,name):emit(op,0);fixups.append((len(code)-1,name,True))
    def jump(op,name):emit(op,0,0);fixups.append((len(code)-2,name,False))
    def store(address):emit(0x8d,address&255,address>>8)
    def load(address,index=False):emit(0xbd if index else 0xad,address&255,address>>8)
    emit(0x78,0xd8,0xa2,0xff,0x9a,0xe8);emit(0x8e,0,0x20,0x8e,1,0x20)
    for name in ('wait1','wait2'):
        mark(name);emit(0x2c,2,0x20);branch(0x10,name)
    emit(0xa9,0x3f);store(0x2006);emit(0xa9,0);store(0x2006);emit(0xa2,0)
    mark('palette');load(0xb600,True);store(0x2007);emit(0xe8,0xe0,32);branch(0xd0,'palette')
    emit(0xa9,0x20);store(0x2006);emit(0xa9,0);store(0x2006);emit(0x85,0,0xa9,0xb0,0x85,1,0xa9,0,0x85,2)
    mark('row');emit(0xa9,0,0x85,3)
    mark('half');emit(0xa9,0,0x85,4)
    mark('column');emit(0xa4,4,0xb1,0,0x0a,0x0a,0x85,6,0xa5,3,0x0a,0x05,6,0xaa)
    load(0xb200,True);store(0x2007);emit(0xe8);load(0xb200,True);store(0x2007)
    emit(0xe6,4,0xa5,4,0xc9,16);branch(0xd0,'column');emit(0xe6,3,0xa5,3,0xc9,2);branch(0xd0,'half')
    emit(0x18,0xa5,0,0x69,16,0x85,0);branch(0x90,'no_carry');emit(0xe6,1);mark('no_carry')
    emit(0xe6,2,0xa5,2,0xc9,14);branch(0xd0,'row');emit(0xa2,128,0xa9,0)
    mark('clear');store(0x2007);emit(0xca);branch(0xd0,'clear')
    emit(0xa9,0);store(0x2005);store(0x2005);store(0x2000);emit(0xa9,0x0a);store(0x2001)
    emit(0xa9,1);store(0x4015);emit(0xa9,8);store(0x4001);emit(0xa9,0,0x85,7);jump(0x20,'note')
    mark('music');emit(0x2c,2,0x20);branch(0x10,'music');emit(0xa5,8);branch(0xd0,'decrement');emit(0xc6,9)
    mark('decrement');emit(0xc6,8,0xa5,8,0x05,9);branch(0xd0,'music')
    emit(0x18,0xa5,7,0x69,6,0xc9,96);branch(0x90,'event');emit(0xa9,0);mark('event');emit(0x85,7);jump(0x20,'note');jump(0x4c,'music')
    mark('note');emit(0xa4,7,0xb9,0,0xb8,0x0a,0xaa);load(0xba00,True);store(0x4002);load(0xba01,True);emit(0x09,0xf8);store(0x4003)
    emit(0xb9,1,0xb8,0x85,8,0xb9,2,0xb8,0x85,9,0xb9,3,0xb8,0x4a,0x4a,0x4a,0x09,0xb0);store(0x4000);emit(0x60)
    for at,name,relative in fixups:
        value=labels[name]
        if relative:
            delta=value-(0x8000+at+1)
            if not -128<=delta<=127:raise ValueError('original fixture branch out of range')
            code[at]=delta&255
        else:code[at:at+2]=value.to_bytes(2,'little')
    raw[16:16+len(code)]=code;raw[16+16384-6:16+16384]=bytes.fromhex('008000800080')
    colors=[[0,0,0],[76,154,236],[228,92,16],[236,238,236]]
    for tile in range(16):
        pixels=[0 if tile==0 else (1+(x//2+y//2+tile)%3 if y<7 else 3) for y in range(8) for x in range(8)]
        raw[16400+tile*16:16400+(tile+1)*16]=encode_cell(pixels,codec='tile8-planar2-msb-v1',width=8,height=8)
    raw[0x3610:0x3630]=bytes([0x0f,0x21,0x27,0x30])*8;raw[0x3700:0x370c]=bytes(c for rgb in colors for c in rgb)
    for i in range(16):raw[0x3210+i*4:0x3214+i*4]=bytes([i]*4)
    terrain=[3 if y>=12 else 2 if (x+y)%13==0 else 1 if y==11 and 3<=x<=7 else 0 for y in range(14) for x in range(16)]
    raw[0x3010:0x3010+224]=bytes(terrain);raw[0x3410:0x3410+224]=bytes(1 if v==3 else 0 for v in terrain)
    raw[0x3510:0x3530]=bytes([1,2,10,0,2,12,10,0]+[0]*24)
    melody=[60,64,67,72,71,67,64,62,60,62,65,69,67,65,62,60]
    for i,note in enumerate(melody):raw[0x3810+i*6:0x3816+i*6]=bytes([note,30,0,96,0,0])
    for note in range(128):
        period=max(8,min(2047,round(1789773/(16*440*2**((note-69)/12))-1)))
        raw[0x3a10+note*2:0x3a12+note*2]=period.to_bytes(2,'little')
    raw[0x1000:0x1200]=bytes(255 if math.sin(i/11)>0 else 0 for i in range(512))
    sha=hashlib.sha256(raw).hexdigest()
    levels={'schema_version':1,'source_sha256':sha,'name':'Hillside',
      'tiles':{'offset':16400,'count':16,'codec':'tile8-planar2-msb-v1','palette_offset':0x3700,'palette_format':'rgb888'},
      'metatiles':{'offset':0x3210,'count':16,'width':2,'height':2,'entry_bytes':1,'endian':'little'},
      'rooms':[{'id':'hillside','name':'Hillside','width':16,'height':14,'terrain':{'offset':0x3010,'entry_bytes':1,'endian':'little'},'collision':{'offset':0x3410,'entry_bytes':1,'endian':'little'},
        'objects':{'offset':0x3510,'count':8,'stride':4,'fields':[{'name':name,'offset':i,'bytes':1,'endian':'little','maximum':maximum} for i,(name,maximum) in enumerate([('kind',15),('x',15),('y',13),('exit_room',0)])]}}]}
    sound={'schema_version':1,'source_sha256':sha,'samples':[{'id':'pulse-sample','name':'DPCM practice','offset':0x1000,'length':512,'codec':'nes-dpcm','sample_rate':16000,'initial_level':64}],
      'songs':[{'id':'hillside','name':'Hillside melody','driver':'hillside-pulse-v1','offset':0x3810,'count':16,'stride':6,'tempo':150,'ticks_per_beat':24,'channels':1}]}
    return {'raw':bytes(raw),'levels':levels,'sound':sound,'driver_length':len(code)}
