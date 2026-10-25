"""Bounded, revision-bound investigation; byte writes still use reviewed plans."""
import math
from pathlib import Path
import re
import struct
from . import workbench_projects as p
from .asset_schema import label,number
from .assets import checked_path
from .script_schema import load_script_json

SCAN_BYTES=64*1024**2


def _source(project,artifact_id):
    row=p.artifact(project,artifact_id);p._measure(row['path'],row);return row,Path(row['path'])


def _pattern(kind,query,endian,width,signed):
    if type(query) is not str or not query or len(query)>1024:raise ValueError('Enter a search pattern up to 1024 characters.')
    if kind=='hex':
        tokens=query.split()
        if not 1<=len(tokens)<=256 or any(not re.fullmatch('[0-9a-fA-F]{2}|\\?\\?',t) for t in tokens):raise ValueError('Use two-digit hex bytes separated by spaces; ?? matches any byte.')
        values=[None if t=='??' else int(t,16) for t in tokens]
        if all(v is None for v in values):raise ValueError('Include at least one specific byte.')
        return values
    if kind=='text':
        raw=query.encode('utf-8')
        if len(raw)>256:raise ValueError('UTF-8 searches are limited to 256 bytes.')
        return list(raw)
    if kind=='number':
        if endian not in ('little','big') or type(width) is not int or width not in (1,2,4) or type(signed) is not bool:raise ValueError('Choose 8, 16 or 32-bit numbers and a byte order.')
        try:return list(int(query,0 if query.lower().startswith(('0x','-0x')) else 10).to_bytes(width,endian,signed=signed))
        except (ValueError,OverflowError):raise ValueError('Number is outside the selected width/sign range.') from None
    raise ValueError('Choose hex, UTF-8 text or number search.')


def search(project,artifact_id,kind,query,start,endian='little',width=2,signed=False,*,cancelled=lambda:False):
    values=_pattern(kind,query,endian,width,signed);row,path=_source(project,artifact_id);number(start,0,row['size'])
    last_start=min(row['size'],start+SCAN_BYTES);read_end=min(row['size'],last_start+len(values)-1)
    expression=b''.join(b'[\\x00-\\xff]' if v is None else re.escape(bytes([v])) for v in values)
    pattern=re.compile(b'(?=('+expression+b'))');offsets=[];tail=b'';position=start;truncated=False;next_start=last_start
    with path.open('rb') as stream:
        stream.seek(start)
        while position<read_end:
            if cancelled():raise KeyboardInterrupt
            raw=stream.read(min(65536,read_end-position))
            if not raw:raise ValueError('Source changed during search.')
            combined=tail+raw;base=position-len(tail)
            for match in pattern.finditer(combined):
                offset=base+match.start()
                if offset<start or offset>=last_start:continue
                offsets.append(offset)
                if len(offsets)==1000:truncated=True;next_start=offset+1;break
            if truncated:break
            tail=combined[-(len(values)-1):] if len(values)>1 else b'';position+=len(raw)
    p._measure(path,row,cancelled=cancelled)
    complete=not truncated and last_start==row['size']
    return {'ok':True,'artifact_id':artifact_id,'source_sha256':row['sha256'],'offsets':offsets,'start':start,
            'scanned_to':min(position if truncated else last_start,row['size']),'complete':complete,'truncated':truncated,'next_start':None if complete else next_start}


def inspect_numbers(project,artifact_id,offset):
    row,path=_source(project,artifact_id);number(offset,0,max(0,row['size']-1))
    with path.open('rb') as stream:stream.seek(offset);raw=stream.read(4)
    values={}
    for width in (1,2,4):
        if len(raw)<width:continue
        for order,tag in (('little','le'),('big','be')):
            for signed,prefix in ((False,'u'),(True,'i')):values[f'{prefix}{width*8}{tag}']=int.from_bytes(raw[:width],order,signed=signed)
            if width==4:
                value=struct.unpack('<f' if order=='little' else '>f',raw)[0]
                values['float32'+tag]=value if math.isfinite(value) else 'non-finite'
    p._measure(path,row)
    return {'ok':True,'artifact_id':artifact_id,'source_sha256':row['sha256'],'offset':offset,'hex':raw.hex(),'values':values}


def _bookmarks(project):
    path=checked_path(Path(project)/'bookmarks.json')
    if not path.exists():return {}
    value=load_script_json(path,max_bytes=1024*1024)
    if type(value) is not dict or value.get('format')!='romancer-bookmarks-v1' or type(value.get('artifacts')) is not dict:raise ValueError('Bookmark store is invalid. Restore a project backup.')
    for key,rows in value['artifacts'].items():
        p.identifier(key)
        if type(rows) is not list or len(rows)>256:raise ValueError('Invalid bookmark list.')
        for r in rows:
            if type(r) is not dict or set(r)!= {'offset','name'}:raise ValueError('Invalid bookmark fields.')
            number(r['offset'],0,p.MAX_SOURCE);label(r['name'],80)
    return value['artifacts']


def bookmarks(project,artifact_id):
    row,_=_source(project,artifact_id)
    return {'ok':True,'artifact_id':artifact_id,'source_sha256':row['sha256'],'bookmarks':_bookmarks(project).get(artifact_id,[])}


def save_bookmark(project,artifact_id,offset,name,remove):
    row,_=_source(project,artifact_id);number(offset,0,row['size']-1)
    if type(remove) is not bool:raise ValueError('Invalid bookmark action.')
    if not remove:label(name,80)
    with p.locked(project):
        store=_bookmarks(project);rows=[r for r in store.get(artifact_id,[]) if r['offset']!=offset]
        if not remove:rows.append({'offset':offset,'name':name})
        if len(rows)>256:raise ValueError('Each file supports 256 bookmarks. Remove one first.')
        store[artifact_id]=sorted(rows,key=lambda r:r['offset']);p.write_json(Path(project)/'bookmarks.json',{'format':'romancer-bookmarks-v1','artifacts':store},max_bytes=1024*1024)
    return bookmarks(project,artifact_id)
