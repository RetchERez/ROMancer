"""Checked layout bindings; no game bytes or inferred editing certification.

The column grammar is shared by the declared-level adapter. These bindings
describe one measured revision and conservatively checked owned descendants.
"""
import hashlib
import json
from .column_terrain import decode_stream,INTERACTIVE
from .workbench_files import read_bounded
from . import workbench_projects as projects

SOURCE_SHA='49fbd2f61f953d5ef28cab73e357e524c3009ad19fcf30f6a9ee0ae273be41dc'
SOURCE_SIZE=65536
LAYOUT_PIN='b5e0b4b27ee1ec397fdcd6606c8798538d5cf33752cf78d625efa8de0b83de4f'
WORLD_BANKS=(2,1,3,1)
CODEC='sml-column-segments-v1'


def _offset(bank,address):
    if type(bank)is not int or bank not in (1,2,3) or type(address)is not int or not 0x4000<=address<0x8000:
        raise ValueError('Level pointer is outside its checked ROM bank.')
    return bank*0x4000+address-0x4000


def _pointer(raw,bank,address):
    at=_offset(bank,address)
    if address==0x7fff:raise ValueError('Level pointer crosses the bank boundary.')
    return int.from_bytes(raw[at:at+2],'little')


def _inventory(raw):
    if type(raw)is not bytes or len(raw)!=SOURCE_SIZE:raise ValueError('Level preset source size differs.')
    levels=[];streams={};references={}
    def screen(bank,address,reference):
        at=_offset(bank,address);key=(bank,address)
        if key not in streams:
            if len(streams)>=256:raise ValueError('Level screen inventory exceeds its budget.')
            model=decode_stream(raw[at:(bank+1)*0x4000],base=at)
            if model.overlaps:raise ValueError('Known level layout has overlapping segments.')
            streams[key]=model
        references.setdefault(key,[]).append(reference)
    for index in range(12):
        world=index//3+1;part=index%3+1;bank=WORLD_BANKS[world-1]
        table=_pointer(raw,bank,0x4000+index*2);pointers=[]
        for position in range(128):
            address=table+position*2
            if raw[_offset(bank,address)]==0xff:break
            target=_pointer(raw,bank,address);pointers.append(target)
            screen(bank,target,'World '+str(world)+'-'+str(part)+' / screen '+str(position+1))
        else:raise ValueError('Level screen list has no bounded terminator.')
        if not pointers:raise ValueError('Known level list is empty.')
        levels.append({'id':'sml-'+str(world)+'-'+str(part),'name':'World '+str(world)+'-'+str(part),
            'world':world,'bank':bank,'table':table,'pointers':pointers})
    extras=[]
    for bank,name in ((2,'Title: separate graphics context'),(3,'First hangar: inherited graphics context')):
        table=_pointer(raw,bank,0x4018);address=_pointer(raw,bank,table)
        screen(bank,address,name);extras.append([bank,table,address])
    return levels,streams,references,extras


def layout_fingerprint(raw):
    levels,streams,_,extras=_inventory(raw)
    # Mutable ranges are measured literal graphics, checksum fields, the BGP
    # operand and noninteractive terrain operands. All other bytes stay bound.
    mutable=set(range(0x14d,0x150))|{0x1a6}
    for start,end in ((0x8032,0x9832),(0x4032,0x4fb2),(0xc032,0xc7f2),(0xb91a,0xbf8a)):
        mutable.update(range(start,end))
    for model in streams.values():
        mutable.update(o.offset for o in model.operands if o.tile not in INTERACTIVE)
    normalized=bytearray(raw)
    for offset in mutable:normalized[offset]=0
    digest=hashlib.sha256(normalized)
    digest.update(json.dumps(sorted(mutable),separators=(',',':')).encode())
    # Bind parsed topology as well as bytes; a changed grammar cannot redefine
    # which operands are excluded from the dependency hash.
    digest.update(json.dumps([levels,extras],sort_keys=True,separators=(',',':')).encode())
    return digest.hexdigest()


def _known_root(project,row,cancelled):
    seen=set()
    for _ in range(128):
        if cancelled():raise KeyboardInterrupt
        if row['artifact_id']in seen:return False
        seen.add(row['artifact_id'])
        if row['sha256']==SOURCE_SHA and row['size']==SOURCE_SIZE:
            projects._measure(row['path'],row,cancelled=cancelled);return True
        if row.get('kind')!='build' or not row.get('source_id'):return False
        row=projects.artifact(project,row['source_id'])
    return False


def _context(project,row,path,cancelled):
    if row.get('system_id')!='gb' or row['size']!=SOURCE_SIZE or not _known_root(project,row,cancelled):return None
    raw=read_bounded(path,SOURCE_SIZE,row,cancelled=cancelled)
    try:matched=layout_fingerprint(raw)==LAYOUT_PIN
    except ValueError:matched=False
    return raw if matched else None


def catalog(project,row,path,*,cancelled=lambda:False):
    raw=_context(project,row,path,cancelled)
    entries=[]
    if raw is not None:
        levels,_,_,_=_inventory(raw)
        entries=[{'id':r['id'],'name':r['name'],'screen_references':len(r['pointers']),
            'unique_screens':len(set(r['pointers']))}for r in levels]
    return {'ok':True,'status':'PRESETS_AVAILABLE'if entries else'NO_PRESETS',
        'source_sha256':row['sha256'],'presets':entries,'full_editing_verified':False,
        'scope':'Checked stored terrain and baseline graphics only. Shared screens affect every reference; collision and interactive metadata are separate.'}


def _tile_segments(world):
    offsets=[0x9032+i*16 for i in range(128)]+[0x8832+i*16 for i in range(128)]
    if world>1:
        enemy,backdrop={2:(0x4032,0x4402),3:(0xc032,0xc402),4:(0x47f2,0x4bc2)}[world]
        for i in range(61):offsets[0xa0+i]=enemy+i*16
        for i in range(63):offsets[0x31+i]=backdrop+i*16
    segments=[]
    for index,offset in enumerate(offsets):
        if segments and offset==segments[-1]['offset']+segments[-1]['count']*16:segments[-1]['count']+=1
        else:segments.append({'first':index,'count':1,'offset':offset,'codec':'tile8-paired2-msb-v1','pixel_map':[0,1,2,3]})
    return segments


def definition(project,row,path,preset_id,*,cancelled=lambda:False):
    if type(preset_id)is not str:raise ValueError('Choose a checked level preset.')
    raw=_context(project,row,path,cancelled)
    if raw is None:raise ValueError('No checked level preset matches this source and its layout bindings.')
    levels,streams,references,_=_inventory(raw)
    level=next((r for r in levels if r['id']==preset_id),None)
    if level is None:raise ValueError('Unknown checked level preset.')
    rooms=[];seen=set()
    for position,address in enumerate(level['pointers']):
        key=(level['bank'],address)
        if key in seen:continue
        seen.add(key);model=streams[key]
        rooms.append({'id':'screen-'+str(level['bank'])+'-'+format(address,'04x'),
            'name':'Screen '+str(position+1),'width':20,'height':16,
            'terrain':{'codec':CODEC,'offset':model.base,'length':model.consumed},
            'collision':None,'objects':None,'references':references[key]})
    if len(rooms)>32:raise ValueError('This preset needs a smaller screen page.')
    value={'schema_version':1,'source_sha256':row['sha256'],'name':level['name'],
        'tiles':{'count':256,'color_count':4,'segments':_tile_segments(level['world']),
            'palette_offset':0x1a6,'palette_format':'dmg-shades'},
        'metatiles':{'kind':'identity'},'rooms':rooms}
    return {'ok':True,'source_sha256':row['sha256'],'preset_id':preset_id,'definition':value,
        'full_editing_verified':False,'scope':'Fixed stored terrain operands and canonical unfiltered grayscale preview. Implicit blanks, interactive tiles and stream growth are protected.'}
