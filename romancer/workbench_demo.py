"""Original redistributable harbor fixture, using the ordinary project services."""
import hashlib
from pathlib import Path
import uuid
from .asset_codecs import encode_cell
from .workbench_projects import create_project,register_source,write_json,read_project


def create_demo(root,incoming):
    project=Path(create_project(root,'Horizon • demonstration')['path'])
    raw=bytearray(b'\x00'*2048);raw[:32]=b'ROMancer original harbor fixture'.ljust(32,b' ')
    texts=[('welcome','WELCOME TO THE HARBOR.',64),('course','CHOOSE A COURSE. SAIL EAST.',128),('credit','By RetchEWretched',192)]
    rules=[];records=[]
    for name,text,offset in texts:
        slot=(text.encode('ascii')+b'\x00').ljust(64,b'\xff');raw[offset:offset+64]=slot
        rules.append({'resource':name,'offset':offset,'length':64,'expected_hex':slot.hex()})
        records.append({'id':name,'rule':name,'annotations':{'label':name.title(),'speaker_label':None,'speaker_provenance':None,'layout_ref':None}})
    pointers=[]
    for index,(name,text,offset) in enumerate(texts):
        position=32+index*2;raw[position:position+2]=offset.to_bytes(2,'little')
        rule='pointer-'+name;rules.append({'resource':rule,'offset':position,'length':2,'expected_hex':raw[position:position+2].hex()})
        pointers.append({'id':rule,'rule':rule,'target_record':name,'width':2,'endian':'little','base':0})
    prov={'origin':'synthetic_fixture','note':'Original ROMancer harbor demonstration, freely redistributable.','reference':None}
    shapes=[
        ['00000000','00011000','00111100','01111110','00011000','11111111','01111110','00111100'],
        ['00000000','00000000','00000000','00000000','00000000','01010101','10101010','01010101'],
        ['00011000','00111100','01111110','11111111','00011000','00011000','00011000','00011000'],
        ['00000000','00000000','00000000','00011000','00111100','01111110','11111111','11111111']]
    for index,shape in enumerate(shapes):
        pixels=[(index+1 if c=='1' else 0) for row in shape for c in row]
        raw[512+index*32:544+index*32]=encode_cell(pixels,codec='tile8-packed4-high-v1',width=8,height=8)
    colors=[0x0421,0x7fff,0x4f4a,0x03ff,0x2d7f]+[0]*11
    for index,color in enumerate(colors):raw[640+index*2:642+index*2]=color.to_bytes(2,'little')
    for index in range(32):raw[704+index*2:706+index*2]=(index%4).to_bytes(2,'little')
    # A structural cartridge fixture for declared-data workflows. The native
    # workshops use their separate original boot programs.
    raw[0x100:0x110]=b'SEGA MEGA DRIVE '
    raw[0x1a4:0x1a8]=(len(raw)-1).to_bytes(4,'big')
    raw[0x18e:0x190]=(sum(int.from_bytes(raw[i:i+2],'big') for i in range(0x200,len(raw),2))&65535).to_bytes(2,'big')
    path=Path(incoming)/(uuid.uuid4().hex+'.bin');path.write_bytes(raw)
    try:source=register_source(project,path,None)
    finally:path.unlink(missing_ok=True)
    value=read_project(project);value['demo']=True;value['sources'][0]['name']='Horizon original fixture.bin'
    sha=hashlib.sha256(raw).hexdigest()
    script={'schema_version':1,'id':'harbor-script','version':'1','artifact':{'kind':'flat-resource','size':len(raw),'integrity':'none'},
        'profile':{'schema_version':2,'id':'harbor-fixture','version':'1','system':'genesis','accepted_sha256':[sha],'rules':rules},
        'format':{'family':'fixed-slots','version':1,'encoding':{'kind':'single-byte','glyphs':[{'byte':i,'text':chr(i)} for i in range(32,127)]},
            'controls':[],'terminator':{'byte':0},'padding':{'byte':255},'records':records,'pointers':pointers,'guards':[]}}
    assets={'schema_version':1,'id':'harbor-art','version':'1','source':{'sha256':sha,'size':len(raw)},'provenance':prov,
        'bitmaps':[{'id':'harbor-tiles','offset':512,'length':128,'codec':'tile8-packed4-high-v1','width':8,'height':8,'count':4,'palette_id':'harbor-palette','provenance':prov}],
        'palettes':[{'id':'harbor-palette','offset':640,'length':32,'entry_bytes':2,'byte_order':'little','banks':1,'colors_per_bank':16,
                     'channels':{'r':31,'g':992,'b':31744},'provenance':prov}],
        'tilemaps':[{'id':'harbor-map','offset':704,'length':64,'entry_bytes':2,'byte_order':'little','width':8,'height':4,'bitmap_id':'harbor-tiles','palette_id':'harbor-palette',
            'fields':{'tile_index':{'kind':'bits','mask':1023},'palette_bank':{'kind':'constant','value':0},'flip_x':{'kind':'bits','mask':16384},'flip_y':{'kind':'bits','mask':32768}},'provenance':prov}], 'fonts':[]}
    value['descriptors']={'script':script,'assets':assets};write_json(project/'project.json',value)
    return {**value,'ok':True,'status':'CREATED','path':str(project),'fixture_note':'Original fixture content. This is not a commercial game or an emulator compatibility test.'}
