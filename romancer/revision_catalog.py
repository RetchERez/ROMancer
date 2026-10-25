"""User-supplied offline hash references; matches confer no editing authority."""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib
from . import workbench_projects as p
from .asset_schema import label
from .assets import checked_path,digest
from .script_schema import load_script_json
from .workbench_files import input_file,read_bounded

MAX_BYTES=16*1024**2
MAX_ENTRIES=50000
HASH_LENGTHS={'crc32':8,'sha1':40,'sha256':64}


def _scope(scope):
    if scope not in ('file','payload'):raise ValueError('Choose whole-file or cartridge-payload reference scope.')
    return scope


def _entry(row,scope):
    if type(row) is not dict or set(row)-{'name','size','scope','crc32','crc','sha1','sha256','md5'}:raise ValueError('Catalog rows need name, size and supported hashes only.')
    row=dict(row)
    if 'crc' in row:
        if 'crc32' in row:raise ValueError('Duplicate CRC32 catalog column.')
        row['crc32']=row.pop('crc')
    name=label(row.get('name'),240);size=row.get('size')
    if type(size) is str and re.fullmatch('[0-9]{1,11}',size):size=int(size)
    if type(size) is not int or not 0<=size<=8*1024**3:raise ValueError('Catalog size must be a nonnegative byte count up to 8 GiB.')
    item={'name':name,'size':size,'scope':_scope(row.get('scope') or scope)}
    for key,length in {**HASH_LENGTHS,'md5':32}.items():
        value=row.get(key,'')
        if value in ('',None):continue
        if type(value) is not str or not re.fullmatch('[0-9a-fA-F]{'+str(length)+'}',value):raise ValueError('Invalid '+key+' catalog hash.')
        if key!='md5':item[key]=value.lower()
    if not any(k in item for k in HASH_LENGTHS):raise ValueError('Each reference needs CRC32, SHA1 or SHA256; MD5 alone is unsupported.')
    return {'id':digest(item),**item}


def _unique(rows):
    if len(rows)>MAX_ENTRIES:raise ValueError('Catalog exceeds 50,000 entries.')
    result={};strong={}
    for row in rows:
        known={k:row[k] for k in HASH_LENGTHS if k in row}
        for algorithm in ('sha1','sha256'):
            if algorithm not in row:continue
            prior=strong.get((row['scope'],row['size'],algorithm,row[algorithm]),{})
            if any(prior[k]!=known[k] for k in HASH_LENGTHS if k in prior and k in known):
                raise ValueError('Catalog contains conflicting hashes for the same strong reference.')
            known.update(prior)
        for algorithm in ('sha1','sha256'):
            if algorithm in known:strong[(row['scope'],row['size'],algorithm,known[algorithm])]=known
        result[row['id']]=row
    return sorted(result.values(),key=lambda r:(r['name'].casefold(),r['id']))


def parse_catalog(raw,scope):
    _scope(scope)
    if type(raw) is not bytes or not raw or len(raw)>MAX_BYTES:raise ValueError('Catalog must be a nonempty file no larger than 16 MiB.')
    try:text=raw.decode('utf-8-sig')
    except UnicodeError:raise ValueError('Save the catalog as UTF-8 CSV, TSV, JSON or XML DAT.') from None
    stripped=text.lstrip()
    if stripped.startswith('<'):
        if re.search(r'<!\s*(DOCTYPE|ENTITY)',text,re.I):raise ValueError('XML catalogs cannot contain DTDs or entities.')
        try:tree=ET.fromstring(text)
        except ET.ParseError:raise ValueError('Invalid XML DAT catalog.') from None
        if tree.tag.split('}')[-1]!='datafile':raise ValueError('Expected an XML DAT datafile.')
        records=[]
        for element in tree.iter():
            if element.tag.split('}')[-1]!='rom' or element.attrib.get('status')=='nodump':continue
            records.append({k:v for k,v in element.attrib.items() if k in {'name','size','crc','sha1','sha256','md5'}})
            if len(records)>MAX_ENTRIES:raise ValueError('Catalog exceeds 50,000 entries.')
    elif stripped.startswith(('[','{')):
        from .runtime_protocol import _pairs,_constant
        try:value=json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant)
        except (ValueError,RecursionError):raise ValueError('Invalid or duplicate-key JSON catalog.') from None
        if type(value) is dict:
            if set(value)-{'format','name','entries'}:raise ValueError('Unknown catalog document fields.')
            value=value.get('entries')
        if type(value) is not list:raise ValueError('JSON catalog needs an entries list.')
        records=value
    else:
        separator='\t' if '\t' in text.splitlines()[0] else ','
        reader=csv.DictReader(io.StringIO(text,newline=''),delimiter=separator)
        if not reader.fieldnames:raise ValueError('Missing catalog column names.')
        names=[name.strip().lower() for name in reader.fieldnames]
        if len(set(names))!=len(names) or set(names)-{'name','size','scope','crc','crc32','sha1','sha256','md5'}:
            raise ValueError('Duplicate or unknown catalog column.')
        reader.fieldnames=names;records=[]
        for row in reader:
            if None in row or any(v is None for v in row.values()):raise ValueError('Catalog row has missing or extra columns.')
            records.append(row)
            if len(records)>MAX_ENTRIES:raise ValueError('Catalog exceeds 50,000 entries.')
    if not records:raise ValueError('No usable ROM hash references were found.')
    return _unique([_entry(row,scope) for row in records])


def load_catalog(project):
    path=checked_path(Path(project)/'catalog'/'revisions.json')
    if not path.exists():return []
    value=load_script_json(path,max_bytes=32*1024**2)
    if value.get('format')!='romancer-revisions-v1' or type(value.get('entries')) is not list:raise ValueError('Saved revision catalog is invalid. Restore a backup or reimport it.')
    normalized=[]
    for row in value['entries']:
        if type(row) is not dict:raise ValueError('Invalid saved catalog entry.')
        checked=_entry({k:v for k,v in row.items() if k!='id'},'file')
        if checked!=row:raise ValueError('Saved catalog identity changed.')
        normalized.append(checked)
    return _unique(normalized)


def import_catalog(project,input_id,scope,*,cancelled=lambda:False):
    project=checked_path(Path(project));row,path=input_file(project,input_id,'catalog')
    incoming=parse_catalog(read_bounded(path,MAX_BYTES,row,cancelled=cancelled),scope)
    if cancelled():raise KeyboardInterrupt
    with p.locked(project):
        previous=load_catalog(project);combined=_unique(previous+incoming)
        folder=checked_path(project/'catalog');folder.mkdir(exist_ok=True)
        p.write_json(folder/'revisions.json',{'format':'romancer-revisions-v1','entries':combined},max_bytes=32*1024**2)
    return {'ok':True,'status':'IMPORTED','project_id':project.name,'count':len(combined),'added':len(combined)-len(previous)}


def catalog_info(project,query=None):
    rows=load_catalog(project);result={'ok':True,'project_id':Path(project).name,'count':len(rows)}
    if query is not None:
        label(query,160,blank=True);matches=[r for r in rows if query.casefold() in r['name'].casefold()]
        result.update(entries=[{k:r[k] for k in ('id','name','scope','size')} for r in matches[:100]],total=len(matches),truncated=len(matches)>100)
    return result


def _hashes(path,row,scope,cancelled):
    _scope(scope);p._measure(path,row,cancelled=cancelled)
    if scope=='payload':
        from .rom_health import check_rom
        ranges=check_rom(path,row['sha256'],'','payload',cancelled=cancelled)['payload_ranges']
    else:ranges=[{'offset':0,'length':row['size']}]
    sha1=hashlib.sha1(usedforsecurity=False);sha256=hashlib.sha256();crc=0;size=0
    with path.open('rb') as stream:
        for region in ranges:
            stream.seek(region['offset']);remaining=region['length']
            while remaining:
                if cancelled():raise KeyboardInterrupt
                raw=stream.read(min(65536,remaining))
                if not raw:raise ValueError('ROM changed during reference lookup.')
                remaining-=len(raw);size+=len(raw);sha1.update(raw);sha256.update(raw);crc=zlib.crc32(raw,crc)
    p._measure(path,row,cancelled=cancelled)
    return {'size':size,'sha1':sha1.hexdigest(),'sha256':sha256.hexdigest(),'crc32':f'{crc:08x}'}


def lookup_revision(project,artifact_id,scope,expected_id='',*,cancelled=lambda:False):
    project=checked_path(Path(project));row=p.artifact(project,artifact_id);entries=load_catalog(project)
    if not entries:raise ValueError('Import a local revision catalog first. ROM health still works without one.')
    hashes=_hashes(Path(row['path']),row,scope,cancelled)
    if expected_id:
        p.identifier(expected_id);expected=next((r for r in entries if r['id']==expected_id),None)
        if expected is None:raise ValueError('Reference is missing. Search the catalog again.')
        if expected['scope']!=scope:raise ValueError('Reference scope differs. Choose whole file or payload to match it.')
        candidates=[expected]
    else:candidates=[r for r in entries if r['scope']==scope]
    matches=[r for r in candidates if r['size']==hashes['size'] and all(r[k]==hashes[k] for k in HASH_LENGTHS if k in r)]
    status='MATCHED' if len(matches)==1 else 'AMBIGUOUS' if matches else 'MISMATCHED' if expected_id else 'UNKNOWN'
    return {'ok':True,'status':status,'project_id':project.name,'artifact_id':artifact_id,'source_sha256':row['sha256'],
            'scope':scope,'hashes':hashes,'matches':matches[:20],'match_count':len(matches),
            'expected':candidates[0] if expected_id else None,'corruption_established':False,
            'reference_origin':'user_imported_catalog','write_authorized':False,'runtime_verified':False}
