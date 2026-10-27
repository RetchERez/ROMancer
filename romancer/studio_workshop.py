"""Mossy Hollow: original NROM teaching scene, art and declared editing layouts."""
from pathlib import Path
import uuid
from .asset_codecs import encode_cell

class Assembler:
    def __init__(self):self.code=bytearray();self.labels={};self.fixups=[]
    def emit(self,*values):self.code.extend(values)
    def label(self,name):
        if name in self.labels:raise ValueError('Duplicate studio code label')
        self.labels[name]=0x8000+len(self.code)
    def absolute(self,opcode,address):
        self.emit(opcode)
        if isinstance(address,str):self.fixups.append((len(self.code),address,False));self.emit(0,0)
        else:self.emit(address&255,address>>8)
    def branch(self,opcode,label):self.emit(opcode);self.fixups.append((len(self.code),label,True));self.emit(0)
    def finish(self):
        for at,label,relative in self.fixups:
            address=self.labels[label]
            if relative:
                value=address-(0x8000+at+1)
                if not -128<=value<=127:raise ValueError('Studio branch exceeds6502 range: '+label)
                self.code[at]=value&255
            else:self.code[at:at+2]=address.to_bytes(2,'little')
        if len(self.code)>=4096:raise ValueError('Studio program overlaps its resource region')
        return bytes(self.code)

FONT={
 'A':'0e 11 11 1f 11 11 11','B':'1e 11 11 1e 11 11 1e','C':'0e 11 10 10 10 11 0e','D':'1e 11 11 11 11 11 1e',
 'E':'1f 10 10 1e 10 10 1f','F':'1f 10 10 1e 10 10 10','G':'0e 11 10 17 11 11 0f','H':'11 11 11 1f 11 11 11',
 'I':'0e 04 04 04 04 04 0e','J':'07 02 02 02 12 12 0c','K':'11 12 14 18 14 12 11','L':'10 10 10 10 10 10 1f',
 'M':'11 1b 15 15 11 11 11','N':'11 19 15 13 11 11 11','O':'0e 11 11 11 11 11 0e','P':'1e 11 11 1e 10 10 10',
 'Q':'0e 11 11 11 15 12 0d','R':'1e 11 11 1e 14 12 11','S':'0f 10 10 0e 01 01 1e','T':'1f 04 04 04 04 04 04',
 'U':'11 11 11 11 11 11 0e','V':'11 11 11 11 11 0a 04','W':'11 11 11 15 15 15 0a','X':'11 11 0a 04 0a 11 11',
 'Y':'11 11 0a 04 04 04 04','Z':'1f 01 02 04 08 10 1f','0':'0e 11 13 15 19 11 0e','1':'04 0c 04 04 04 04 0e',
 '2':'0e 11 01 02 04 08 1f','3':'1e 01 01 0e 01 01 1e','4':'02 06 0a 12 1f 02 02','5':'1f 10 10 1e 01 01 1e',
 '6':'0e 10 10 1e 11 11 0e','7':'1f 01 02 04 08 08 08','8':'0e 11 11 0e 11 11 0e','9':'0e 11 11 0f 01 01 0e',
 '!':'04 04 04 04 04 00 04',',':'00 00 00 00 00 04 08','.':'00 00 00 00 00 00 04','-':'00 00 00 1f 00 00 00',':':'00 04 00 00 04 00 00'}

def make_studio_rom():
    data=bytearray(16+16384+8192);data[:6]=b'NES\x1a\x01\x01';a=Assembler()
    a.emit(0x78,0xd8,0xa2,0xff,0x9a,0xe8)
    for address in (0x2000,0x2001,0x4010):a.absolute(0x8e,address)
    a.emit(0xa9,0x40);a.absolute(0x8d,0x4017)
    for name in ('warmup1','warmup2'):a.label(name);a.absolute(0x2c,0x2002);a.branch(0x10,name)
    a.emit(0xa9,0,0x85,0,0x85,3,0x85,4,0x85,5)
    a.absolute(0xad,0x9703);a.emit(0x0a,0x0a,0x0a,0x85,1)
    a.absolute(0xad,0x9705);a.emit(0x0a,0x0a,0x0a,0x85,2)
    a.emit(0xa9,0xf0,0xa2,0);a.label('hide');a.absolute(0x9d,0x0200);a.emit(0xe8);a.branch(0xd0,'hide')
    a.emit(0xa2,0);a.label('oam');a.absolute(0xbd,0x9800);a.absolute(0x9d,0x0200);a.emit(0xe8,0xe0,32);a.branch(0xd0,'oam')
    def ppu(address):
        for value in (address>>8,address&255):a.emit(0xa9,value);a.absolute(0x8d,0x2006)
    ppu(0x3f00);a.emit(0xa2,0);a.label('palette');a.absolute(0xbd,0x9000);a.absolute(0x8d,0x2007);a.emit(0xe8,0xe0,32);a.branch(0xd0,'palette')
    ppu(0x2000)
    for page in range(4):
        name='room'+str(page);a.emit(0xa2,0);a.label(name);a.absolute(0xbd,0x9100+page*256);a.absolute(0x8d,0x2007);a.emit(0xe8);a.branch(0xd0,name)
    ppu(0x2343);a.emit(0xa2,0);a.label('dialogue');a.absolute(0xbd,0x9600);a.branch(0xf0,'dialogue_done');a.absolute(0x8d,0x2007);a.emit(0xe8,0xe0,26);a.branch(0xd0,'dialogue');a.label('dialogue_done')
    a.emit(0xa9,1);a.absolute(0x8d,0x4015);a.emit(0xa9,8);a.absolute(0x8d,0x4001)
    a.emit(0xa9,0);a.absolute(0x8d,0x2005);a.absolute(0x8d,0x2005);a.emit(0xa9,0x1e);a.absolute(0x8d,0x2001)
    a.label('frame');a.absolute(0x2c,0x2002);a.branch(0x10,'frame');a.emit(0xe6,0)
    a.emit(0xa9,1);a.absolute(0x8d,0x4016);a.emit(0xa9,0);a.absolute(0x8d,0x4016);a.emit(0x85,4,0xa2,8)
    a.label('pad');a.absolute(0xad,0x4016);a.emit(0x4a,0x26,4,0xca);a.branch(0xd0,'pad')
    a.emit(0xa5,4,0x29,1);a.branch(0xf0,'left');a.emit(0xa5,1,0x18);a.absolute(0x6d,0x9700);a.emit(0xc9,224);a.branch(0x90,'right_store');a.emit(0xa9,224);a.label('right_store');a.emit(0x85,1)
    a.label('left');a.emit(0xa5,4,0x29,2);a.branch(0xf0,'enemy');a.emit(0xa5,1,0x38);a.absolute(0xed,0x9700);a.branch(0x90,'left_min');a.emit(0xc9,16);a.branch(0xb0,'left_store');a.label('left_min');a.emit(0xa9,16);a.label('left_store');a.emit(0x85,1)
    a.label('enemy');a.emit(0xa5,3);a.branch(0xf0,'enemy_right');a.emit(0xa5,2,0x38);a.absolute(0xed,0x9701);a.emit(0xc9,48);a.branch(0xb0,'enemy_left_store');a.emit(0xa9,0,0x85,3,0xa9,48);a.label('enemy_left_store');a.emit(0x85,2);a.absolute(0x4c,'sound')
    a.label('enemy_right');a.emit(0xa5,2,0x18);a.absolute(0x6d,0x9701);a.emit(0xc9,224);a.branch(0x90,'enemy_right_store');a.emit(0xa9,1,0x85,3,0xa9,224);a.label('enemy_right_store');a.emit(0x85,2)
    a.label('sound');a.emit(0xa5,4,0x29,0x80);a.branch(0xf0,'sound_tick');a.emit(0xa9,12,0x85,5,0xa9,0xba);a.absolute(0x8d,0x4000);a.absolute(0xad,0x9702);a.absolute(0x8d,0x4002);a.emit(0xa9,8);a.absolute(0x8d,0x4003)
    a.label('sound_tick');a.emit(0xa5,5);a.branch(0xf0,'quiet');a.emit(0xc6,5);a.absolute(0x4c,'actors');a.label('quiet');a.emit(0xa9,0xb0);a.absolute(0x8d,0x4000)
    a.label('actors')
    for base,zp,spawn in ((0x0200,1,0x9704),(0x0210,2,0x9706)):
        a.emit(0xa5,zp);a.absolute(0x8d,base+3);a.absolute(0x8d,base+11);a.emit(0x18,0x69,8);a.absolute(0x8d,base+7);a.absolute(0x8d,base+15)
        a.absolute(0xad,spawn);a.emit(0x0a,0x0a,0x0a,0x38,0xe9,1);a.absolute(0x8d,base);a.absolute(0x8d,base+4);a.emit(0x18,0x69,8);a.absolute(0x8d,base+8);a.absolute(0x8d,base+12)
    for base,tile,mask,shifts in ((0x0200,16,16,2),(0x0210,32,32,3)):
        a.emit(0xa5,0,0x29,mask,*([0x4a]*shifts),0x18,0x69,tile)
        for i in range(4):
            a.absolute(0x8d,base+1+i*4)
            if i<3:a.emit(0x18,0x69,1)
    a.emit(0xa9,0);a.absolute(0x8d,0x2003);a.emit(0xa9,2);a.absolute(0x8d,0x4014);a.emit(0xa9,0);a.absolute(0x8d,0x2005);a.absolute(0x8d,0x2005);a.absolute(0x4c,'frame')
    code=a.finish();data[16:16+len(code)]=code;data[16+16384-6:16+16384]=bytes.fromhex('008000800080')
    def put(cpu,raw):data[16+cpu-0x8000:16+cpu-0x8000+len(raw)]=raw
    put(0x9000,bytes([15,12,26,48]*4+[15,18,39,48,15,26,42,48,15,18,39,48,15,26,42,48]))
    room=bytearray(1024)
    for y in range(30):
        for x in range(32):
            room[y*32+x]=1 if 24<=y<=29 else 2 if (y==7 and 2<=x<=29) or (x in (2,29) and 7<=y<24) else 0
    for x,y in [(5,9),(11,11),(22,9),(18,14),(7,16),(25,17)]:room[y*32+x]=6
    for y in range(20,24):room[y*32+26]=3
    def text(x,y,value):room[y*32+x:y*32+x+len(value)]=bytes(ord(c)+32 for c in value)
    text(10,2,'MOSSY HOLLOW');text(5,4,'ARROWS MOVE  A CHIRP')
    for y in (25,26,27,28):room[y*32+3:y*32+29]=bytes(26)
    text(4,28,'BUILD YOUR OWN ADVENTURE')
    put(0x9100,room);put(0x9600,bytes(ord(c)+32 for c in 'HELLO, EXPLORER!')+bytes([0])+bytes([255])*11)
    put(0x9700,bytes([2,1,128,5,22,23,22]));put(0x9800,bytes([175,16,0,40,175,17,0,48,183,18,0,40,183,19,0,48,175,32,1,184,175,33,1,192,183,34,1,184,183,35,1,192]))
    put(0x9900,bytes([5,10,25,25,85,115,45,140,75,235,240,220]));put(0x9a00,bytes(range(128)))
    def tile(index,pixels):data[16400+index*16:16400+(index+1)*16]=encode_cell(pixels,codec='tile8-planar2-msb-v1',width=8,height=8)
    patterns={1:['22222222','23322332','11111111','11111111','11111111','11111111','11111111','11111111'],2:['11111111','12222122','12222122','11111111','22122221','22122221','11111111','11111111'],3:['22222222','21111112','21131112','21111112','21111112','21111112','21111112','21111112'],6:['00000000','00030000','00333000','00030000','00000000','00000000','00000000','00000000']}
    for i,rows in patterns.items():tile(i,[int(v) for row in rows for v in row])
    hero=['0000011111100000','0000112222110000','0001122222211000','0001223322331000','0001223322331000','0001122222211000','0000012222100000','0000111111110000','0001222222221000','0011222222221100','0011122222211100','0000122222210000','0000111111110000','0000111001110000','0001111001111000','0001111001111000']
    slime=['0000000000000000','0000000000000000','0000000000000000','0000011111100000','0001122222211000','0012222222222100','0122222222222210','0122233223322210','1222233223322221','1222222222222221','1222222222222221','1222223333222221','1222222222222221','0122222222222210','0011111111111100','0000000000000000']
    for first,rows in ((16,hero),(20,hero[:13]+['0001111001110000','0011110000111100','0000000000000000']),(32,slime),(36,['0000000000000000']+slime[2:]+['0000000000000000'])):
        for part in range(4):tile(first+part,[int(rows[(part//2)*8+y][(part%2)*8+x]) for y in range(8) for x in range(8)])
    for char,encoded in FONT.items():
        rows=[int(v,16) for v in encoded.split()];tile(ord(char)+32,[3 if y<7 and 1<=x<=5 and rows[y]&(1<<(5-x)) else 0 for y in range(8) for x in range(8)])
    return {'data':bytes(data),'graphics_offset':16400+16*16,'stats_offset':0x1710,'spawn_offset':0x1713,'dialogue_offset':0x1610,'map_offset':0x1110,'program_size':len(code)}

def create_studio(root,incoming):
    from . import workbench_projects as projects
    from .resource_forms import graphics_schema,script_schema
    from .data_tables import inspect_table
    from .level_design import inspect_level
    fixture=make_studio_rom();project=Path(projects.create_project(root,'Mossy Hollow - editing studio')['path'])
    path=Path(incoming)/(uuid.uuid4().hex+'.nes');path.write_bytes(fixture['data'])
    try:source=projects.register_source(project,path,None)
    finally:path.unlink(missing_ok=True)
    source_path=Path(source['path']);sha=source['sha256']
    assets=graphics_schema(source_path,sha,{'system_id':'nes','offset':fixture['graphics_offset'],'count':24})
    script=script_schema(source_path,sha,{'system_id':'nes','offset':fixture['dialogue_offset'],'capacity':27,'count':1,'encoding':'table','table':'\n'.join(format(i+32,'02X')+'='+chr(i) for i in range(32,96))})
    table={'schema_version':1,'name':'Scene controls','offset':fixture['stats_offset'],'count':1,'stride':3,'row_names':['Mossy Hollow'],'fields':[{'name':name,'offset':i,'type':'u8','endian':'little','pointer_base':None,**({'minimum':0,'maximum':8} if i<2 else {})} for i,name in enumerate(('Hero speed','Slime speed','Chirp pitch value'))]}
    inspect_table(source_path,sha,table,0,1)
    levels={'schema_version':1,'source_sha256':sha,'name':'Mossy Hollow room','tiles':{'offset':16400,'count':128,'codec':'tile8-planar2-msb-v1','palette_offset':0x1910,'palette_format':'rgb888'},'metatiles':{'offset':0x1a10,'count':128,'width':1,'height':1,'entry_bytes':1,'endian':'little'},'rooms':[{'id':'hollow','name':'Mossy Hollow','width':32,'height':30,'terrain':{'offset':fixture['map_offset'],'entry_bytes':1,'endian':'little'},'collision':None,'objects':{'offset':fixture['spawn_offset'],'count':2,'stride':2,'fields':[{'name':'x','offset':0,'bytes':1,'endian':'little','maximum':28},{'name':'y','offset':1,'bytes':1,'endian':'little','maximum':29}]},'object_metadata':[{'index':0,'name':'Hero start','role':'actor','reference':None},{'index':1,'name':'Slime start','role':'actor','reference':None}]}]}
    inspect_level(fixture['data'],levels,sha)
    value=projects.read_project(project);value.update(demo=True,demo_type='original-studio',original_workshop=True,demo_system='nes')
    value['sources'][0].update(name='Mossy Hollow - original.nes',descriptors={'assets':assets,'script':script,'tables':{'source_sha256':sha,'definition':table},'levels':levels})
    projects.write_json(project/'project.json',value)
    return {**projects.read_project(project),'ok':True,'status':'CREATED','path':str(project),'workshop_note':'Original interactive scene: arrows move, A chirps; hero/slime animation, editable graphics, dialogue, speeds and room/spawn positions. Level-editor RGB colors are an authored reference preview, not editable NES palette data. Room terrain is visual; collision is not implemented.'}
