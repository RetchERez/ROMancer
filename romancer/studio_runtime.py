"""Original NROM collision/actor/music laboratory. Legacy workshop bytes stay separate."""
from functools import lru_cache
from .studio_workshop import Assembler,make_studio_rom

ACTORS=0x9d00
COLLISION=0xa000
MUSIC=0x9b00
PITCH=0x9c00
ACTOR_FIELDS=('x','y','offset_x','offset_y','width','height','starting_health','contact_damage','ai_enabled','patrol_left','patrol_right','damage_cooldown')
RAM={'frame':0,'hero_x':1,'enemy_x':2,'enemy_direction':3,'buttons':4,'chirp':5,'hero_y':6,'enemy_y':7,'hero_health':8,'hero_cooldown':9,'candidate_x':10,'candidate_y':11,'width':12,'height':13,'offset_x':14,'offset_y':15,'collision_pointer':16,'sample_x':18,'hazard':19,'music_event':20,'music_lo':21,'music_hi':22,'amount':23,'enemy_health':24,'enemy_cooldown':25,'row':26,'previous_buttons':27}

@lru_cache(maxsize=1)
def _authored():
    data=bytearray(make_studio_rom()['data']);a=Assembler()
    inverse={0xf0:0xd0,0xd0:0xf0,0x90:0xb0,0xb0:0x90,0x10:0x30,0x30:0x10}
    def jump_if(op,target):a.emit(inverse[op],3);a.absolute(0x4c,target)
    def load(z):a.emit(0xa5,z)
    def save(z):a.emit(0x85,z)
    def value(v):a.emit(0xa9,v)
    def read(at):a.absolute(0xad,at)
    def write(at):a.absolute(0x8d,at)
    def call(target):a.absolute(0x20,target)
    def ppu(at):value(at>>8);write(0x2006);value(at&255);write(0x2006)
    def box(base):
        for offset,z in [(4,12),(5,13),(2,14),(3,15)]:read(base+offset);save(z)
    a.emit(0x78,0xd8,0xa2,0xff,0x9a,0xe8)
    for at in (0x2000,0x2001,0x4010):a.absolute(0x8e,at)
    value(0x40);write(0x4017)
    for name in ('warmup1','warmup2'):a.label(name);a.absolute(0x2c,0x2002);a.branch(0x10,name)
    value(0);a.emit(0xa2,0);a.label('clear_ram');a.absolute(0x9d,0);a.emit(0xe8);a.branch(0xd0,'clear_ram')
    for base,x,y,hp in [(ACTORS,1,6,8),(ACTORS+16,2,7,24)]:
        read(base);a.emit(0x0a,0x0a,0x0a);save(x);read(base+1);a.emit(0x0a,0x0a,0x0a);save(y);read(base+6);save(hp)
    value(0xf0);a.emit(0xa2,0);a.label('hide');a.absolute(0x9d,0x0200);a.emit(0xe8);a.branch(0xd0,'hide')
    a.emit(0xa2,0);a.label('oam');a.absolute(0xbd,0x9800);a.absolute(0x9d,0x0200);a.emit(0xe8,0xe0,32);a.branch(0xd0,'oam')
    ppu(0x3f00);a.emit(0xa2,0);a.label('palette');a.absolute(0xbd,0x9000);write(0x2007);a.emit(0xe8,0xe0,32);a.branch(0xd0,'palette')
    ppu(0x2000)
    for page in range(4):
        name='map'+str(page);a.emit(0xa2,0);a.label(name);a.absolute(0xbd,0x9100+page*256);write(0x2007);a.emit(0xe8);a.branch(0xd0,name)
    ppu(0x2343);a.emit(0xa2,0);a.label('dialogue');a.absolute(0xbd,0x9600);a.branch(0xf0,'dialogue_done');write(0x2007);a.emit(0xe8,0xe0,26);a.branch(0xd0,'dialogue');a.label('dialogue_done')
    value(3);write(0x4015)
    for at in (0x4001,0x4005):value(8);write(at)
    value(0);write(0x2005);write(0x2005);value(0x1e);write(0x2001)
    a.label('frame');a.emit(0xe6,0)
    for z in (9,25):load(z);a.branch(0xf0,'cool_'+str(z));a.emit(0xc6,z);a.label('cool_'+str(z))
    value(1);write(0x4016);value(0);write(0x4016);save(4);a.emit(0xa2,8)
    a.label('pad');read(0x4016);a.emit(0x4a,0x26,4,0xca);a.branch(0xd0,'pad')
    load(4);a.emit(0x29,0x10);jump_if(0xd0,'restart')
    value(0);save(19);box(ACTORS)
    load(8);jump_if(0xf0,'hero_done');read(ACTORS+8);jump_if(0xf0,'hero_done')
    for name,mask,z,op,limit,greater in [('right',1,1,0x6d,240,True),('left',2,1,0xed,0,False),('down',4,6,0x6d,224,True),('up',8,6,0xed,0,False)]:
        load(4);a.emit(0x29,mask);jump_if(0xf0,name+'_done')
        load(1);save(10);load(6);save(11);load(z);a.emit(0x18 if greater else 0x38);a.absolute(op,0x9700)
        if greater:a.emit(0xc9,limit+1);jump_if(0xb0,name+'_done')
        else:jump_if(0x90,name+'_done')
        save(10 if z==1 else 11)
        if z==1:
            read(ACTORS+9);a.emit(0x0a,0x0a,0x0a);save(18);load(10);a.emit(0xc5,18);jump_if(0x90,name+'_done')
            read(ACTORS+10);a.emit(0x0a,0x0a,0x0a);save(18);load(18);a.emit(0xc5,10);jump_if(0x90,name+'_done')
        call('blocked');jump_if(0xb0,name+'_done');load(10 if z==1 else 11);save(z);a.label(name+'_done')
    a.label('hero_done');value(0);save(19);load(1);save(10);load(6);save(11);call('blocked');load(19);a.emit(0xc9,2);a.branch(0xd0,'no_hazard');value(1);call('hurt_hero');a.label('no_hazard')
    box(ACTORS+16);load(24);jump_if(0xf0,'enemy_done');read(ACTORS+24);jump_if(0xf0,'enemy_done')
    read(ACTORS+25);a.emit(0x0a,0x0a,0x0a);save(28);read(ACTORS+26);a.emit(0x0a,0x0a,0x0a);save(29)
    load(2);save(10);load(7);save(11);load(3);a.branch(0xf0,'enemy_right')
    load(2);a.emit(0x38);a.absolute(0xed,0x9701);jump_if(0x90,'turn_right');a.emit(0xc5,28);jump_if(0x90,'turn_right');save(10);call('blocked');jump_if(0xb0,'turn_right');load(10);save(2);a.absolute(0x4c,'enemy_done')
    a.label('enemy_right');load(2);a.emit(0x18);a.absolute(0x6d,0x9701);jump_if(0xb0,'turn_left');save(10);load(29);a.emit(0xc5,10);jump_if(0x90,'turn_left');call('blocked');jump_if(0xb0,'turn_left');load(10);save(2);a.absolute(0x4c,'enemy_done')
    a.label('turn_right');value(0);save(3);a.absolute(0x4c,'enemy_done');a.label('turn_left');value(1);save(3)
    a.label('enemy_done');load(8);jump_if(0xf0,'sound');load(24);jump_if(0xf0,'sound');call('overlap');jump_if(0x90,'sound')
    read(ACTORS+23);call('hurt_hero');load(4);a.emit(0x29,0x80);jump_if(0xf0,'sound');load(27);a.emit(0x29,0x80);jump_if(0xd0,'sound');read(ACTORS+7);call('hurt_enemy')
    a.label('sound');load(4);a.emit(0x29,0x80);a.branch(0xf0,'chirp_tick');value(12);save(5);value(0xba);write(0x4004);read(0x9702);write(0x4006);value(8);write(0x4007)
    a.label('chirp_tick');load(5);a.branch(0xf0,'quiet');a.emit(0xc6,5);a.absolute(0x4c,'music_tick');a.label('quiet');value(0xb0);write(0x4004)
    a.label('music_tick');call('music');load(4);save(27)
    for base,x,y in [(0x0200,1,6),(0x0210,2,7)]:
        load(x);write(base+3);write(base+11);a.emit(0x18,0x69,8);write(base+7);write(base+15)
        load(y);a.emit(0x38,0xe9,1);write(base);write(base+4);a.emit(0x18,0x69,8);write(base+8);write(base+12)
    for base,tile,mask,shifts in [(0x0200,16,16,2),(0x0210,32,32,3)]:
        load(0);a.emit(0x29,mask,*([0x4a]*shifts),0x18,0x69,tile)
        for i in range(4):
            write(base+1+i*4)
            if i<3:a.emit(0x18,0x69,1)
    load(24);a.branch(0xd0,'enemy_visible');value(240)
    for at in (0x0210,0x0214,0x0218,0x021c):write(at)
    a.label('enemy_visible');a.label('vblank');a.absolute(0x2c,0x2002);a.branch(0x10,'vblank')
    for address,z in [(0x209b,8),(0x20dc,24)]:ppu(address);load(z);a.emit(0x18,0x69,80);write(0x2007)
    value(0);write(0x2003);value(2);write(0x4014);value(0);write(0x2005);write(0x2005);a.absolute(0x4c,'frame')
    a.label('restart');a.absolute(0x4c,0x8000)
    # With dimensions at most 16 px, start/middle/end cover every touched8px cell.
    a.label('blocked')
    for right,bottom in [(x,y) for y in (0,1,2) for x in (0,1,2)]:
        load(10);a.emit(0x18,0x65,14)
        jump_if(0xb0,'blocked_overflow')
        if right:
            save(30);load(12);a.emit(0x38,0xe9,1)
            if right==1:a.emit(0x4a)
            a.emit(0x18,0x65,30);jump_if(0xb0,'blocked_overflow')
        save(30);load(11);a.emit(0x18,0x65,15)
        jump_if(0xb0,'blocked_overflow')
        if bottom:
            save(31);load(13);a.emit(0x38,0xe9,1)
            if bottom==1:a.emit(0x4a)
            a.emit(0x18,0x65,31);jump_if(0xb0,'blocked_overflow')
        a.emit(0xaa);load(30);call('cell');jump_if(0xb0,'blocked_return')
    a.emit(0x18);a.label('blocked_return');a.emit(0x60)
    a.label('blocked_overflow');a.emit(0x38,0x60)
    # A=x pixel, X=y pixel. Grid is32x30 with one byte per8x8 cell.
    a.label('cell');save(18);a.emit(0x8a,0xc9,240);a.branch(0xb0,'cell_wall');a.emit(0x4a,0x4a,0x4a);save(26);a.emit(0x29,7,0x0a,0x0a,0x0a,0x0a,0x0a);save(16)
    load(26);a.emit(0x4a,0x4a,0x4a,0x18,0x69,0xa0);save(17);load(18);a.emit(0x4a,0x4a,0x4a,0xa8,0xb1,16,0xc9,0);a.branch(0xf0,'cell_clear');a.emit(0xc9,2);a.branch(0xd0,'cell_wall');save(19)
    a.label('cell_clear');a.emit(0x18,0x60);a.label('cell_wall');a.emit(0x38,0x60)
    # AABB overlap uses the authored pixel offsets and dimensions, not sprite art.
    a.label('overlap')
    for axis,zhero,zenemy,offset,size in [('x',1,2,2,4),('y',6,7,3,5)]:
        load(zhero);a.emit(0x18);a.absolute(0x6d,ACTORS+offset);save(28);load(zenemy);a.emit(0x18);a.absolute(0x6d,ACTORS+16+offset);save(29)
        load(28);a.emit(0x18);a.absolute(0x6d,ACTORS+size);a.emit(0xc5,29);jump_if(0x90,'no_overlap');jump_if(0xf0,'no_overlap')
        load(29);a.emit(0x18);a.absolute(0x6d,ACTORS+16+size);a.emit(0xc5,28);jump_if(0x90,'no_overlap');jump_if(0xf0,'no_overlap')
    a.emit(0x38,0x60);a.label('no_overlap');a.emit(0x18,0x60)
    for name,hp,cool,base in [('hero',8,9,ACTORS),('enemy',24,25,ACTORS+16)]:
        a.label('hurt_'+name);a.emit(0xc9,0);a.branch(0xf0,'hurt_'+name+'_return');save(23);load(cool);a.branch(0xd0,'hurt_'+name+'_return');load(hp);a.branch(0xf0,'hurt_'+name+'_return');a.emit(0x38,0xe5,23);a.branch(0xb0,'hurt_'+name+'_store');value(0);a.label('hurt_'+name+'_store');save(hp);read(base+11);save(cool);a.label('hurt_'+name+'_return');a.emit(0x60)
    a.label('music');load(21);a.emit(0x05,22);a.branch(0xf0,'music_next');load(21);a.branch(0xd0,'music_decrement');a.emit(0xc6,22);a.label('music_decrement');a.emit(0xc6,21,0x60)
    a.label('music_next');load(20);a.emit(0xa8);a.absolute(0xb9,MUSIC);a.emit(0x38,0xe9,33,0x0a,0xaa);a.absolute(0xbd,PITCH);write(0x4002);a.absolute(0xbd,PITCH+1);a.emit(0x09,8);write(0x4003)
    a.absolute(0xb9,MUSIC+1);save(21);a.absolute(0xb9,MUSIC+2);save(22);a.absolute(0xb9,MUSIC+3);a.emit(0x4a,0x4a,0x4a,0x09,0xb0);write(0x4000)
    load(20);a.emit(0x18,0x69,6,0xc9,96);a.branch(0x90,'music_index');value(0);a.label('music_index');save(20);a.emit(0x60)
    code=a.finish();data[16:4112]=bytes(4096);data[16:16+len(code)]=code
    def put(cpu,raw):data[16+cpu-0x8000:16+cpu-0x8000+len(raw)]=raw
    room=bytearray(data[0x1110:0x1510]);grid=bytearray(960)
    for y in range(30):
        for x in range(32):grid[y*32+x]=int(y<=7 or y>=24 or x<=2 or x>=29)
    for y in range(18,24):room[y*32+16]=2;grid[y*32+16]=1
    for y in (19,20):
        for x in (10,11):room[y*32+x]=6;grid[y*32+x]=2
    room[:7*32]=bytes(7*32)
    for x,y,text in [(10,2,'MOSSY HOLLOW'),(3,4,'ARROWS MOVE  A HIT'),(3,6,'START RESTARTS'),(24,4,'HP:'),(24,6,'FOE:')]:room[y*32+x:y*32+x+len(text)]=bytes(ord(c)+32 for c in text)
    put(0x9100,room);put(COLLISION,grid)
    hero=bytes([5,22,2,1,12,14,5,1,1,0,28,30,0,0,0,0]);enemy=bytes([23,22,1,5,14,10,3,1,1,6,28,8,0,0,0,0]);put(ACTORS,hero+enemy)
    sequence=bytearray()
    for note in [60,64,67,72,67,64,62,65,69,74,69,65,60,67,64,60]:sequence.extend(bytes([note,20,0,72,0,0]))
    put(MUSIC,sequence);pitch=bytearray()
    for note in range(33,109):pitch.extend(max(8,min(2047,round(1789773/(16*440*2**((note-69)/12))-1))).to_bytes(2,'little'))
    put(PITCH,pitch)
    return bytes(data),len(code)

def make_collision_studio_rom():
    raw,size=_authored()
    return {'data':raw,'program_size':size,'graphics_offset':16400+16*16,'stats_offset':0x1710,'spawn_offset':0x1d10,'dialogue_offset':0x1610,'map_offset':0x1110,'collision_offset':0x2010,'music_offset':0x1b10,'pitch_offset':0x1c10}

def matches_studio_runtime(raw):
    expected,size=_authored()
    return type(raw) is bytes and len(raw)==len(expected) and raw[:16]==expected[:16] and raw[16:16+size]==expected[16:16+size] and raw[16394:16400]==expected[16394:16400]

def validate_studio_data(raw):
    if not matches_studio_runtime(raw):return
    if any(value>8 for value in raw[0x1710:0x1712]):raise ValueError('Original workshop speed must be 0 to 8 pixels per frame.')
    for index in range(2):
        at=0x1d10+index*16;actor=dict(zip(ACTOR_FIELDS,raw[at:at+12]))
        if not 1<=actor['width']<=16 or not 1<=actor['height']<=16 or actor['offset_x']>15 or actor['offset_y']>15:raise ValueError('Original workshop hitboxes need 1 to 16 pixel dimensions and 0 to 15 pixel offsets.')
        if actor['x']>28 or actor['y']>29 or actor['x']*8+actor['offset_x']+actor['width']>256 or actor['y']*8+actor['offset_y']+actor['height']>240:raise ValueError('Original workshop starting hitbox must fit inside the256 by240 pixel room.')
        if not actor['patrol_left']<=actor['x']<=actor['patrol_right']<=28:raise ValueError('Starting X must lie between the left and right movement limits.')
        if actor['starting_health']>9 or actor['contact_damage']>9 or actor['ai_enabled']>1 or actor['damage_cooldown']>120:raise ValueError('Original workshop actor values exceed their engine limits.')

def runtime_definitions(fixture,sha):
    def field(name,i):
        limits={'x':(0,28),'y':(0,29),'offset_x':(0,15),'offset_y':(0,15),'width':(1,16),'height':(1,16),'starting_health':(0,9),'contact_damage':(0,9),'ai_enabled':(0,1),'patrol_left':(0,28),'patrol_right':(0,28),'damage_cooldown':(0,120)}
        low,high=limits[name];return {'name':name,'offset':i,'bytes':1,'endian':'little','minimum':low,'maximum':high}
    levels={'schema_version':1,'source_sha256':sha,'name':'Mossy Hollow collision lab','tiles':{'offset':16400,'count':128,'codec':'tile8-planar2-msb-v1','palette_offset':0x1910,'palette_format':'rgb888'},'metatiles':{'offset':0x1a10,'count':128,'width':1,'height':1,'entry_bytes':1,'endian':'little'},'rooms':[{'id':'hollow','name':'Mossy Hollow','width':32,'height':30,'terrain':{'offset':fixture['map_offset'],'entry_bytes':1,'endian':'little'},'collision':{'offset':fixture['collision_offset'],'entry_bytes':1,'endian':'little'},'collision_types':[{'value':0,'name':'Open floor','kind':'walkable','color':[45,155,110]},{'value':1,'name':'Solid wall','kind':'solid','color':[195,65,85]},{'value':2,'name':'Damage floor','kind':'hazard','color':[215,160,35]}],'objects':{'offset':fixture['spawn_offset'],'count':2,'stride':16,'fields':[field(name,i) for i,name in enumerate(ACTOR_FIELDS)]},'object_metadata':[{'index':i,'name':name,'role':'actor','reference':None,'hitbox':{'offset_x':'offset_x','offset_y':'offset_y','width':'width','height':'height'},'sprite':{'tiles':list(range(16 if i==0 else 32,20 if i==0 else 36)),'width':2,'height':2,'transparent_index':0}} for i,name in enumerate(['Hero start','Slime start'])]}]}
    sound={'schema_version':1,'source_sha256':sha,'samples':[],'songs':[{'id':'hollow-theme','name':'Mossy Hollow theme','driver':'mossy-pulse-v1','offset':fixture['music_offset'],'count':16,'stride':6,'tempo':150,'ticks_per_beat':24,'channels':1}]}
    return {'levels':levels,'sound':sound}
