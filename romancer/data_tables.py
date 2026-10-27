"""Declared numeric records and linear file pointers over exact source revisions."""
from contextlib import contextmanager
import json
from pathlib import Path
from .asset_schema import fields,label,number
from .assets import checked_path,digest
from .script_schema import canonical_bytes
from .workbench_projects import _measure

TYPES={prefix+str(bits):(bits//8,prefix=='s') for prefix in ('u','s') for bits in (8,16,24,32)}


def _optional_fields(value,required,optional):
    if type(value) is not dict:raise ValueError('descriptor must be an object')
    present=set(value)&set(optional.split())
    fields(value,' '.join(required.split()+sorted(present)))


def _storage_bounds(field):
    width,signed=TYPES[field['type']];bits=width*8
    return (-(1<<(bits-1)) if signed else 0),(1<<(bits-1 if signed else bits))-1


def validate_definition(definition,size):
    definition=json.loads(canonical_bytes(definition,max_bytes=65536))
    _optional_fields(definition,'schema_version name offset count stride fields','label_source row_names row_id_base')
    if type(definition['schema_version']) is not int or definition['schema_version']!=1:raise ValueError('unsupported table definition version')
    label(definition['name'],64);number(definition['offset'],0,size);number(definition['count'],1,65536);number(definition['stride'],1,65536)
    if definition['offset']+definition['count']*definition['stride']>size:raise ValueError('table records extend beyond the source')
    rows=definition['fields']
    if 'row_names' in definition:
        if 'label_source' in definition:raise ValueError('Choose declared row names or a stored name table, not both.')
        names=definition['row_names']
        if type(names) is not list or len(names)!=definition['count']:raise ValueError('Supply exactly one declared name per table row.')
        for name in names:label(name,80)
        number(definition.get('row_id_base',0),0,65536-definition['count'])
    elif 'row_id_base' in definition:raise ValueError('A row ID base requires declared row names.')
    if type(rows) is not list or not 1<=len(rows)<=32:raise ValueError('define1..32 named table fields')
    occupied=[];names=set()
    for field in rows:
        _optional_fields(field,'name offset type endian pointer_base','minimum maximum');label(field['name'],64)
        key=field['name'].casefold()
        if key in names:raise ValueError('table field names must be unique')
        names.add(key)
        if field['type'] not in TYPES or field['endian'] not in ('little','big'):raise ValueError('choose a supported numeric type and byte order')
        width,signed=TYPES[field['type']];number(field['offset'],0,definition['stride']-1)
        lower,upper=_storage_bounds(field)
        minimum=number(field.get('minimum',lower),lower,upper)
        number(field.get('maximum',upper),minimum,upper)
        if field['offset']+width>definition['stride']:raise ValueError('table field extends beyond its record stride')
        if field['pointer_base'] is not None:
            number(field['pointer_base'],0,0xffffffff)
            if signed:raise ValueError('linear pointers use an unsigned numeric field')
        for start,end in occupied:
            if field['offset']<end and start<field['offset']+width:raise ValueError('table fields overlap')
        occupied.append((field['offset'],field['offset']+width))
    if 'label_source' in definition:
        source=definition['label_source'];fields(source,'offset stride length skip encoding id_base')
        if source['encoding']!='chrono-name':raise ValueError('unsupported table label encoding')
        number(definition['count'],1,4096);number(source['offset'],0,size)
        number(source['stride'],1,256);number(source['length'],1,256)
        number(source['skip'],0,source['length']-1);number(source['id_base'],0,65535)
        if source['length']>source['stride']:raise ValueError('table labels overlap')
        if source['offset']+(definition['count']-1)*source['stride']+source['length']>size:
            raise ValueError('table labels extend beyond the source')
        if source['id_base']+definition['count']>65536:raise ValueError('table label IDs exceed supported bounds')
    return definition


@contextmanager
def _context(path,sha,definition):
    path=checked_path(Path(path));source=_measure(path)
    if not 1<=source['size']<=64*1024**2:raise ValueError('tables require a declared flat resource up to64MiB')
    if source['sha256']!=sha:raise ValueError('source revision changed; inspect the current table')
    definition=validate_definition(definition,source['size'])
    with path.open('rb') as stream:
        yield stream,source,definition
        _measure(path,source)


def _read(stream,definition,row,field,size):
    width,signed=TYPES[field['type']];offset=definition['offset']+row*definition['stride']+field['offset']
    stream.seek(offset);raw=stream.read(width)
    if len(raw)!=width:raise ValueError('table source changed while reading')
    value=int.from_bytes(raw,field['endian'],signed=signed)
    target=value-field['pointer_base'] if field['pointer_base'] is not None else None
    resolved=target is not None and 0<=target<size
    return {'field':field['name'],'value':value,'offset':offset,'raw_hex':raw.hex(),'target_offset':target if resolved else None,
            'pointer_resolution':('declared-linear-file-offset' if resolved else 'unresolved') if field['pointer_base'] is not None else None}


def _check_value(value,field,*,declared=True):
    width,signed=TYPES[field['type']];
    minimum,maximum=_storage_bounds(field)
    if declared:minimum=field.get('minimum',minimum);maximum=field.get('maximum',maximum)
    if type(value) is not int or not minimum<=value<=maximum:raise ValueError(f"{field['name']} must be an integer from{minimum} to{maximum}")
    return value.to_bytes(width,field['endian'],signed=signed)


def _row_catalog(stream,definition):
    if 'row_names' in definition:return [{'index':i,'record_id':definition.get('row_id_base',0)+i,'label':name,'label_origin':'declared'} for i,name in enumerate(definition['row_names'])]
    source=definition.get('label_source')
    if source is None:return []
    from .chrono_tables import decode_name
    rows=[]
    for index in range(definition['count']):
        stream.seek(source['offset']+index*source['stride']);raw=stream.read(source['length'])
        if len(raw)!=source['length']:raise ValueError('table name source changed while reading')
        rows.append({'index':index,'record_id':source['id_base']+index,**decode_name(raw[source['skip']:])})
    return rows


def inspect_table(path,sha,definition,page=0,limit=50):
    number(page,0,65535);number(limit,1,100)
    with _context(path,sha,definition) as (stream,source,definition):
        catalog=_row_catalog(stream,definition)
        rows=[{'index':row,'offset':definition['offset']+row*definition['stride'],
               **(catalog[row] if catalog else {}),
               'cells':[_read(stream,definition,row,field,source['size']) for field in definition['fields']]}
              for row in range(page*limit,min((page+1)*limit,definition['count']))]
    return {'ok':True,'status':'INSPECTED','source_sha256':sha,'document_id':digest({'source_sha256':sha,'definition':definition}),
            'definition':definition,'rows':rows,'row_catalog':catalog,'page':page,'limit':limit,'total':definition['count'],'pointer_formula':'target file offset = stored value - base'}


def table_edits(path,sha,definition,changes):
    changes=json.loads(canonical_bytes(changes,max_bytes=256*1024))
    if type(changes) is not list or not 1<=len(changes)<=1024:raise ValueError('review1..1024 table changes at a time')
    edits=[];seen=set()
    with _context(path,sha,definition) as (stream,source,definition):
        named={field['name']:field for field in definition['fields']}
        for change in changes:
            fields(change,'row field before after');number(change['row'],0,definition['count']-1)
            field=named.get(change['field'])
            if field is None:raise ValueError('unknown table field')
            key=(change['row'],change['field'])
            if key in seen:raise ValueError('duplicate changes target the same table field')
            seen.add(key);current=_read(stream,definition,change['row'],field,source['size'])
            _check_value(change['before'],field,declared=False);replacement=_check_value(change['after'],field)
            if current['value']!=change['before']:raise ValueError('table old-value precondition failed; inspect the current revision')
            if current['raw_hex']!=replacement.hex():edits.append({'offset':current['offset'],'before':current['raw_hex'],'after':replacement.hex()})
    if not edits:raise ValueError('change at least one table value before reviewing a build')
    return sorted(edits,key=lambda row:row['offset'])


def batch_changes(path,sha,definition,field_name,operation,value,first,count):
    number(first,0,65535);number(count,1,1024)
    if operation not in ('set','add','multiply','percent') or type(value) is not int or abs(value)>0xffffffff:raise ValueError('choose a bounded numeric set/add/multiply/percent operation')
    if operation=='percent':number(value,-100,1000)
    changes=[]
    with _context(path,sha,definition) as (stream,source,definition):
        if first+count>definition['count']:raise ValueError('batch extends beyond table records')
        field=next((field for field in definition['fields'] if field['name']==field_name),None)
        if field is None:raise ValueError('choose a declared field for the batch')
        for row in range(first,first+count):
            before=_read(stream,definition,row,field,source['size'])['value']
            after=value if operation=='set' else before+value if operation=='add' else before*value
            if operation=='percent':
                scaled=before*(100+value);after=((abs(scaled)+50)//100)*(1 if scaled>=0 else -1)
            try:_check_value(after,field)
            except ValueError as error:raise ValueError(f'row {row}: {error}') from error
            if after!=before:changes.append({'row':row,'field':field_name,'before':before,'after':after})
    return changes
