"""Facts-only measured sample catalog; matches never authorize ROM edits."""
import copy,functools,hashlib,json,re
from pathlib import Path
from .release_scope import SYSTEMS
from .script_schema import _unique_object,_nonfinite
from .graphics_discovery import SYSTEM_CODECS

VERSION=1
MAX_DATABASE=24*1024**2
HASH=re.compile('[0-9a-f]{64}')
STATUSES={'PASS','FAIL','WARN','NOT_CHECKED'}
DATABASE_PATH=Path(__file__).resolve().parents[1]/'knowledge/rom_samples.json'

def _fields(row,names):
    if type(row) is not dict or set(row)!=set(names.split()):raise ValueError('Unexpected measured-database fields.')
def _int(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('Measured number outside bounds.')
def _hash(value):
    if type(value) is not str or not HASH.fullmatch(value):raise ValueError('Invalid sample hash.')
def _range(row,size):
    _int(row['offset'],0,size-1);_int(row['length'],1,size-row['offset'])
def _name(value,limit=80):
    if type(value) is not str or not 1<=len(value)<=limit or any(ord(c)<32 or c in '/\\:' for c in value):raise ValueError('Invalid short sample label.')

def validate_record(row):
    _fields(row,'sha256 crc32 size system_id format labels header_offset regions header_numbers checks discoveries coverage')
    _hash(row['sha256'])
    if type(row['crc32']) is not str or not re.fullmatch('[0-9A-F]{8}',row['crc32']):raise ValueError('Invalid sample CRC32.')
    _int(row['size'],1,64*1024**2)
    formats={'nes':('ines','nes2'),'snes':('lorom','hirom','exhirom-candidate'),'genesis':('genesis-linear','genesis-scattered'),'gb':('gb-cartridge',),'gbc':('gbc-cartridge',),'sms':('sms-sega',)}
    if type(row['system_id']) is not str or row['system_id'] not in SYSTEMS:raise ValueError('Sample system is outside this release.')
    if row['format'] not in formats[row['system_id']]:raise ValueError('Sample format does not match its system.')
    if type(row['labels']) is not list or not 1<=len(row['labels'])<=8:raise ValueError('Invalid sample labels.')
    for label in row['labels']:_name(label)
    _int(row['header_offset'],0,row['size']-1)
    if type(row['regions']) is not list or not 1<=len(row['regions'])<=16:raise ValueError('Invalid file-region facts.')
    for region in row['regions']:
        _fields(region,'id kind offset length');_range(region,row['size'])
        for key in ('id','kind'):
            if type(region[key]) is not str or not re.fullmatch('[a-z0-9-]{1,64}',region[key]):raise ValueError('Invalid region identifier.')
    if type(row['header_numbers']) is not dict or len(row['header_numbers'])>32:raise ValueError('Invalid header-number facts.')
    for key,value in row['header_numbers'].items():
        if type(key) is not str or not re.fullmatch('[a-z][a-z0-9_]{0,63}',key):raise ValueError('Invalid header field.')
        if type(value) is not bool:_int(value,0,2**64-1)
    if type(row['checks']) is not list or len(row['checks'])>64:raise ValueError('Invalid cartridge checks.')
    for check in row['checks']:
        _fields(check,'id status stored computed locations')
        if type(check['id']) is not str or not re.fullmatch('[a-z0-9-]{1,96}',check['id']) or check['status'] not in STATUSES:raise ValueError('Invalid cartridge-check fact.')
        for key in ('stored','computed'):
            if check[key] is not None and (type(check[key]) is not str or not re.fullmatch('[0-9A-F]{1,16}',check[key])):raise ValueError('Only numeric checksum values belong in sample checks.')
        if type(check['locations']) is not list or len(check['locations'])>16:raise ValueError('Invalid check locations.')
        for loc in check['locations']:_fields(loc,'offset length');_range(loc,row['size'])
    if type(row['discoveries']) is not list or len(row['discoveries'])>96:raise ValueError('Too many resource facts.')
    for found in row['discoveries']:
        _fields(found,'kind offset length format confidence decoded_size decoded_sha256');_range(found,row['size'])
        if found['kind'] not in ('text','graphics','compression') or found['confidence'] not in ('candidate','format-derived','validated-encoding'):raise ValueError('Invalid resource evidence.')
        allowed=('ascii-run','tile8-planar2-msb-v1','tile8-paired2-msb-v1','tile8-paired4-msb-v1','tile8-packed4-high-v1','tile8-rowplanar4-msb-v1','lz10','rle')
        if found['format'] not in allowed:raise ValueError('Invalid resource format.')
        if found['kind']=='compression':
            if found['format'] not in ('lz10','rle') or found['confidence']!='validated-encoding':raise ValueError('Invalid compression evidence.')
            _int(found['decoded_size'],8,65536);_hash(found['decoded_sha256'])
        else:
            if found['decoded_size'] is not None or found['decoded_sha256'] is not None:raise ValueError('Unexpected decoded fields.')
            if found['kind']=='text' and (found['format']!='ascii-run' or found['confidence']!='candidate'):raise ValueError('Invalid text evidence.')
            if found['kind']=='graphics':
                if found['format']!=SYSTEM_CODECS[row['system_id']] or found['confidence'] not in ('candidate','format-derived'):raise ValueError('Invalid graphics evidence.')
                if found['confidence']=='format-derived' and (row['system_id']!='nes' or not any(r['id']=='chr-rom' and r['offset']==found['offset'] and found['length']<=r['length'] for r in row['regions'])):raise ValueError('Graphics evidence lacks a declared CHR-ROM region.')
    _fields(row['coverage'],'whole_file_read bytes_read text_runs graphics_stride graphics_samples compression_windows compression_work_limited text_truncated graphics_truncated compression_truncated')
    coverage=row['coverage']
    for key in ('whole_file_read','compression_work_limited','text_truncated','graphics_truncated','compression_truncated'):
        if type(coverage[key]) is not bool:raise ValueError('Invalid coverage flag.')
    for key in ('bytes_read','text_runs','graphics_stride','graphics_samples','compression_windows'):_int(coverage[key],0,64*1024**2)
    if coverage['bytes_read']!=row['size'] or coverage['whole_file_read'] is not True:raise ValueError('Recorded sample must have a complete identity read.')
    return row

def validate_database(data):
    _fields(data,'schema_version scanner_version facts_only label_origin records')
    if data['schema_version']!=1 or type(data['schema_version']) is not int or data['scanner_version']!=VERSION or type(data['scanner_version']) is not int or data['facts_only'] is not True or data['label_origin']!='supplied_filename':raise ValueError('Unsupported measured-database contract.')
    if type(data['records']) is not list or len(data['records'])>20000:raise ValueError('Sample catalog exceeds record budget.')
    seen=set()
    for row in data['records']:
        validate_record(row)
        if row['sha256'] in seen:raise ValueError('Duplicate source identity in catalog.')
        seen.add(row['sha256'])
    return data

def load_database(path=None):
    path=Path(path or DATABASE_PATH)
    if path.stat().st_size>MAX_DATABASE:raise ValueError('Measured catalog exceeds its byte budget.')
    with path.open('rb') as stream:raw=stream.read(MAX_DATABASE+1)
    if len(raw)>MAX_DATABASE:raise ValueError('Measured catalog exceeds its byte budget.')
    try:data=json.loads(raw,object_pairs_hook=_unique_object,parse_constant=_nonfinite)
    except (RecursionError,UnicodeError) as error:raise ValueError('Invalid measured catalog encoding or nesting.') from error
    return validate_database(data)

@functools.lru_cache(maxsize=1)
def _load_cached(path,size,mtime):
    data=load_database(path)
    return {row['sha256']:row for row in data['records']}

def fingerprint():
    if not DATABASE_PATH.exists():return 'not-installed'
    with DATABASE_PATH.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def lookup(sha256,size,*,database=None):
    _hash(sha256);_int(size,1,64*1024**2)
    if database is not None:records={r['sha256']:r for r in validate_database(database)['records']}
    elif DATABASE_PATH.exists():
        stat=DATABASE_PATH.stat();records=_load_cached(str(DATABASE_PATH),stat.st_size,stat.st_mtime_ns)
    else:records={}
    row=records.get(sha256)
    result={'ok':True,'status':'RECORDED_SAMPLE' if row else 'NOT_RECORDED','source_sha256':sha256,
        'canonical_revision_verified':False,'gameplay_verified':False,'write_authorized':False,
        'label_origin':'supplied_filename','record':copy.deepcopy(row)}
    if row and row['size']!=size:raise ValueError('Catalog size disagrees with this source identity.')
    return result

def catalog(query='',system_filter='all',page=0,limit=20):
    if type(query) is not str or len(query)>128 or system_filter not in ('all',*SYSTEMS):raise ValueError('Choose a supported sample filter.')
    _int(page,0,1000);_int(limit,1,50)
    if DATABASE_PATH.exists():
        stat=DATABASE_PATH.stat();records=_load_cached(str(DATABASE_PATH),stat.st_size,stat.st_mtime_ns).values()
    else:records=()
    rows=[r for r in records if (system_filter=='all' or r['system_id']==system_filter) and (query.casefold() in ' '.join(r['labels']).casefold() or query.lower() in r['sha256'] or query.upper() in r['crc32'])]
    rows=sorted(rows,key=lambda r:(r['labels'][0].casefold(),r['sha256']))
    return {'ok':True,'total':len(rows),'page':page,'limit':limit,'samples':[{k:copy.deepcopy(r[k]) for k in ('sha256','crc32','size','system_id','format','labels')} for r in rows[page*limit:(page+1)*limit]],
            'canonical_revision_verified':False,'write_authorized':False}

