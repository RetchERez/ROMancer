"""Bounded cartridge/ISO9660 inventory and separate-file CUE/BIN transactions.

ISO directory record layout follows ECMA-119 (2019), sections8.4 and9.1.
Supported disc sets use one BINARY track per file: MODE1/2048, MODE1/2352,
or preserved AUDIO. Shared-file mixed-mode and interleaved ISO files refuse.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from .assets import checked_path
from .asset_schema import number
from .system_identify import identify_system
from . import workbench_projects as p


def _read_payload(stream,size,offset,length,layout):
    number(offset,0,8*1024**3);number(length,1,1024**2)
    sector=2352 if layout=='mode1-2352' else 2048
    if layout not in ('mode1-2048','mode1-2352') or size%sector or offset+length>size//sector*2048:raise ValueError('payload range exceeds supported track')
    if sector==2048:
        stream.seek(offset);raw=stream.read(length)
        if len(raw)!=length:raise ValueError('truncated payload')
        return raw
    output=bytearray()
    from .cdrom import validate_mode1
    while length:
        index,intra=divmod(offset,2048);count=min(2048-intra,length)
        stream.seek(index*2352);raw=stream.read(2352);validate_mode1(raw)
        output.extend(raw[16+intra:16+intra+count]);offset+=count;length-=count
    return bytes(output)


def extract_extent(path,expected_sha256,offset,length,*,layout):
    path=checked_path(path);measured=p._measure(path)
    if measured['sha256']!=expected_sha256:raise ValueError('container revision mismatch')
    with path.open('rb') as stream:raw=_read_payload(stream,measured['size'],offset,length,layout)
    p._measure(path,measured);return raw


def _both(raw,width=4):
    if len(raw)!=2*width or int.from_bytes(raw[:width],'little')!=int.from_bytes(raw[width:],'big'):raise ValueError('ISO both-endian field mismatch')
    return int.from_bytes(raw[:width],'little')


def _iso_inventory(stream,size,layout,cancelled):
    sector=2352 if layout=='mode1-2352' else 2048;blocks=size//sector
    if blocks<17:return []
    read=lambda o,n:_read_payload(stream,size,o,n,layout)
    primary=None
    for index in range(16,min(blocks,48)):
        raw=read(index*2048,2048)
        if raw[1:6]!=b'CD001' or raw[6]!=1:
            if index==16:return []
            raise ValueError('invalid ISO volume descriptor')
        if raw[0]==1:
            if primary is not None:raise ValueError('multiple primary ISO volumes are unsupported')
            primary=raw
        if raw[0]==255:break
    else:raise ValueError('missing ISO volume descriptor terminator')
    if primary is None:return []
    volume=_both(primary[80:88])
    if not 1<=volume<=blocks or _both(primary[128:132],2)!=2048:raise ValueError('unsupported ISO volume bounds/block size')
    files=[];visited=set();directory_bytes=0;occupied=[];metadata=[(0,(index+1)*2048)]
    def reserve(start,length):
        end=start+((length+2047)//2048)*2048
        if start<0 or end>volume*2048 or any(start<b and end>a for a,b in metadata):raise ValueError('overlapping or out-of-range ISO metadata')
        if length:metadata.append((start,end))
    table_size=_both(primary[132:140])
    if table_size>4*1024**2:raise ValueError('ISO path table budget exceeded')
    if table_size:
        locations=[int.from_bytes(primary[o:o+4],order) for o,order in ((140,'little'),(144,'little'),(148,'big'),(152,'big'))]
        if not locations[0] or not locations[2]:raise ValueError('missing ISO path table')
        for location in locations:
            if location:reserve(location*2048,table_size)
    def record(raw):
        if len(raw)<34 or raw[0]!=len(raw) or 33+raw[32]>len(raw):raise ValueError('truncated ISO directory record')
        extent=_both(raw[2:10]);length=_both(raw[10:18]);sequence=_both(raw[28:32],2)
        if raw[1] or raw[26] or raw[27] or raw[25]&128 or sequence!=1:raise ValueError('unsupported ISO extended/interleaved/multi-extent record')
        if extent>=volume or length>volume*2048-extent*2048:raise ValueError('ISO extent exceeds volume')
        return extent,length,raw[25],raw[33:33+raw[32]]
    def walk(raw,parent,depth):
        nonlocal directory_bytes
        if cancelled():raise KeyboardInterrupt
        extent,length,flags,_=record(raw)
        if not flags&2 or length>1024**2 or depth>8 or (extent,length) in visited:raise ValueError('invalid/cyclic/oversized ISO directory')
        reserve(extent*2048,length)
        visited.add((extent,length));directory_bytes+=length
        if directory_bytes>4*1024**2:raise ValueError('ISO directory budget exceeded')
        content=read(extent*2048,length);cursor=0
        while cursor<len(content):
            length_record=content[cursor]
            if not length_record:cursor=(cursor//2048+1)*2048;continue
            if cursor%2048+length_record>2048 or cursor+length_record>len(content):raise ValueError('ISO record crosses sector/directory boundary')
            entry=content[cursor:cursor+length_record];cursor+=length_record
            start,count,flags,name=record(entry)
            if name in (b'\x00',b'\x01'):continue
            try:decoded=name.decode('ascii')
            except UnicodeError:raise ValueError('unsupported ISO identifier encoding') from None
            if not decoded or any(c in decoded for c in '/\\:\x00') or any(ord(c)<32 for c in decoded):raise ValueError('unsafe ISO identifier')
            full=parent+decoded
            if flags&2:walk(entry,full+'/',depth+1)
            else:
                if len(files)>=4096 or any(f['name'].casefold()==full.casefold() for f in files):raise ValueError('duplicate/excessive ISO file inventory')
                if any(start*2048<end and start*2048+count>begin for begin,end in occupied):raise ValueError('overlapping ISO file extents unsupported')
                occupied.append((start*2048,start*2048+count));files.append({'name':full,'offset':start*2048,'length':count,'extent':start,'layout':layout})
    root_length=primary[156];walk(primary[156:156+root_length],'',0)
    for file in files:
        start=file['offset'];end=start+((file['length']+2047)//2048)*2048
        if file['length'] and any(start<b and end>a for a,b in metadata):raise ValueError('ISO file extent overlaps filesystem metadata')
    return files


def inventory_container(path,expected_sha256,*,cancelled=lambda:False):
    path=checked_path(path);assessment=identify_system(path,expected_sha256=expected_sha256,cancelled=cancelled)
    if assessment['status']=='CANCELLED':raise KeyboardInterrupt
    if not assessment['ok']:raise ValueError(assessment.get('error','container identity failed'))
    layout=assessment.get('container',{}).get('format');files=[]
    if layout in ('mode1-2048','mode1-2352'):
        with path.open('rb') as stream:files=_iso_inventory(stream,assessment['source']['size'],layout,cancelled)
    p._measure(path,assessment['source'],cancelled=cancelled)
    return {'ok':True,'status':'INVENTORIED','source':assessment['source'],'system_id':assessment['system_id'],'layout':layout,'regions':assessment['regions'],'files':files,'runtime_verified':False}


def build_container(path,expected_sha256,destination,offset,replacement,*,layout,expected_before,cancelled=lambda:False):
    path=checked_path(path);destination=checked_path(destination)
    if type(replacement) is not bytes or type(expected_before) is not bytes or not 1<=len(replacement)<=1024**2 or len(expected_before)!=len(replacement):raise ValueError('provide equal bounded payload bytes')
    inv=inventory_container(path,expected_sha256,cancelled=cancelled)
    if layout!=inv['layout']:raise ValueError('container layout mismatch')
    if not any(f['offset']<=offset and offset+len(replacement)<=f['offset']+f['length'] for f in inv['files']):raise ValueError('edit must fit one inventoried ISO file')
    if extract_extent(path,expected_sha256,offset,len(replacement),layout=layout)!=expected_before:raise ValueError('old payload bytes mismatch')
    if cancelled():raise KeyboardInterrupt
    if destination.exists():raise ValueError('container output already exists')
    with tempfile.TemporaryDirectory(prefix='.container-',dir=destination.parent) as temp:
        stage=Path(temp)/('output'+destination.suffix)
        if layout=='mode1-2352':
            from .cd_patch import patch_mode1
            result=patch_mode1(path,stage,offset//2048,offset%2048,replacement,expected_sha256=expected_sha256,expected_before=expected_before,resource_size=len(replacement))
            if not result['ok']:raise ValueError(result.get('error','raw sector build failed'))
            measure=p._measure(stage)
        else:
            measure=p._publish_copy(path,stage,inv['source'],[{'offset':offset,'before':expected_before.hex(),'after':replacement.hex()}],cancelled=cancelled)
        rebuilt=inventory_container(stage,measure['sha256'],cancelled=cancelled)
        if rebuilt['files']!=inv['files'] or rebuilt['layout']!=inv['layout']:raise ValueError('staged filesystem structure changed')
        p._measure(path,inv['source'],cancelled=cancelled)
        if cancelled():raise KeyboardInterrupt
        os.link(stage,destination)
    return {'ok':True,'status':'BUILT','path':str(destination),**measure,'independent_byte_check':True,'filesystem_revalidated':True}



def parse_cue(path):
    path=checked_path(path);measure=p._measure(path)
    if measure['size']>65536:raise ValueError('CUE exceeds64KiB')
    text=path.read_text(encoding='utf-8-sig');tracks=[];current_file=None;current=None;used=set()
    for line in text.splitlines():
        line=line.strip()
        if not line or re.match(r'(?i)^(REM|TITLE|PERFORMER)\b',line):continue
        file=re.fullmatch(r'(?i)FILE\s+(?:"([^"\r\n]+)"|(\S+))\s+BINARY',line)
        track=re.fullmatch(r'(?i)TRACK\s+(\d{2})\s+(MODE1/2048|MODE1/2352|AUDIO)',line)
        index=re.fullmatch(r'(?i)INDEX\s+(00|01)\s+(\d{2}):(\d{2}):(\d{2})',line)
        if file:
            name=file[1] or file[2]
            if not name or '\\' in name or ':' in name or name.startswith('/') or any(p in ('','.','..') for p in name.split('/')):raise ValueError('unsafe CUE track path')
            if name.casefold()=='set.json' or name.casefold()==path.name.casefold():raise ValueError('CUE cannot reference itself')
            current_file=name;current=None
        elif track:
            if current_file is None or current is not None or current_file.casefold() in used:raise ValueError('only separate-file tracks are supported')
            number=int(track[1]);mode=track[2].upper()
            if number!=len(tracks)+1 or number>99:raise ValueError('CUE tracks must be ordered from01')
            current={'number':number,'file':current_file,'mode':mode,'index':None};tracks.append(current);used.add(current_file.casefold())
        elif index:
            if current is None:raise ValueError('CUE index without track')
            minute,second,frame=map(int,index.groups()[1:])
            if second>=60 or frame>=75:raise ValueError('invalid CUE timestamp')
            position=(minute*60+second)*75+frame
            if position!=0:raise ValueError('separate-file track INDEX must begin atzero')
            if index[1]=='01':
                if current['index'] is not None:raise ValueError('duplicate track INDEX01')
                current['index']=position
        elif re.fullmatch(r'(?i)PREGAP\s+00:0[0-9]:[0-7][0-9]',line):
            if current is None:raise ValueError('PREGAP without track')
        else:raise ValueError('unsupported or malformed CUE directive')
    if not tracks or any(t['index'] is None for t in tracks):raise ValueError('CUE needs complete tracks')
    if tracks[0]['mode'] not in ('MODE1/2048','MODE1/2352'):raise ValueError('first track must be supported Mode1 data')
    members=[{'name':path.name,**measure}];total=measure['size']
    for track in tracks:
        source=checked_path(path.parent/track['file']);measured=p._measure(source);sector=2048 if track['mode']=='MODE1/2048' else 2352
        if not measured['size'] or measured['size']%sector:raise ValueError('track alignment mismatch')
        members.append({'name':track['file'],**measured});total+=measured['size']
    if total>8*1024**3:raise ValueError('disc set exceeds8GiB')
    p._measure(path,measure)
    return {'cue':path.name,'tracks':tracks,'members':members}


def import_disc_set(project,cue,*,cancelled=lambda:False):
    project=checked_path(project);cue=checked_path(cue);inventory=parse_cue(cue);container_id=uuid.uuid4().hex
    with p.locked(project) as value:
        root=project/'containers';root.mkdir(exist_ok=True);stage=root/('.staging-'+container_id);stage.mkdir();destination=root/container_id
        if shutil.disk_usage(root).free<sum(m['size'] for m in inventory['members'])+1024**2:raise ValueError('insufficient disc staging space')
        for member in inventory['members']:
            target=stage/member['name'];target.parent.mkdir(parents=True,exist_ok=True)
            p._publish_copy(cue.parent/member['name'],target,member,cancelled=cancelled)
        first=inventory['tracks'][0];member=next(m for m in inventory['members'] if m['name']==first['file'])
        system=inventory_container(stage/first['file'],member['sha256'],cancelled=cancelled)
        if system['system_id']!='segacd':raise ValueError('data track is not an identified Sega CD container')
        record={'container_id':container_id,'relative':'containers/'+container_id,'kind':'disc-set',**inventory}
        p.write_json(stage/'set.json',record)
        if cancelled():raise KeyboardInterrupt
        os.rename(stage,destination);value.setdefault('containers',[]).append(record);p.write_json(project/'project.json',value)
    return {'ok':True,'status':'IMPORTED','path':str(destination),**record}


def build_disc_set(project,container_id,track_number,offset,replacement,*,expected_before,cancelled=lambda:False):
    project=checked_path(project);p.identifier(container_id)
    with p.locked(project) as value:
        record=next((r for r in value.get('containers',[]) if r['container_id']==container_id),None)
        if not record:raise ValueError('unknown disc set')
        original=checked_path(project/'containers'/container_id);actual=parse_cue(original/record['cue'])
        if actual['members']!=record['members'] or actual['tracks']!=record['tracks']:raise ValueError('disc set revision changed')
        track=next((t for t in record['tracks'] if t['number']==track_number),None)
        if not track or track['mode']=='AUDIO':raise ValueError('choose a supported data track')
        build_id=uuid.uuid4().hex;stage=project/'containers'/('.staging-'+build_id);stage.mkdir();destination=stage.parent/build_id;members=[]
        for member in record['members']:
            source=original/member['name'];target=stage/member['name'];target.parent.mkdir(parents=True,exist_ok=True)
            if member['name']==track['file']:
                build_container(source,member['sha256'],target,offset,replacement,layout=track['mode'].lower().replace('/','-'),expected_before=expected_before,cancelled=cancelled)
                measured=p._measure(target)
            else:measured=p._publish_copy(source,target,member,cancelled=cancelled)
            members.append({'name':member['name'],**measured})
        built={**record,'container_id':build_id,'source_container_id':container_id,'relative':'containers/'+build_id,'kind':'disc-build','members':members}
        # Fresh dependency validation of the entire staged output set before publication.
        if parse_cue(stage/record['cue'])['members']!=members:raise ValueError('staged disc member verification failed')
        for member in record['members']:p._measure(original/member['name'],member,cancelled=cancelled)
        p.write_json(stage/'set.json',built)
        if cancelled():raise KeyboardInterrupt
        os.rename(stage,destination);value.setdefault('containers',[]).append(built);p.write_json(project/'project.json',value)
    return {'ok':True,'status':'BUILT','path':str(destination),**built,'independent_set_check':True}
