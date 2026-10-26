"""Paged source-bound resource labels. Catalog entries never grant edit authority."""

import os
from pathlib import Path
import tempfile
from .asset_schema import fields,label,number
from .assets import checked_path,digest
from .script_schema import load_script_json,canonical_bytes
from . import workbench_projects as p

MAX_ENTRIES=50000


def _rows(project,row):
    folder=checked_path(Path(project)/'catalog'/row['artifact_id']);result={}
    files=sorted(folder.glob('*.json'))
    if len(files)>128:raise ValueError('catalog batch budget exceeded')
    for path in files:
        value=load_script_json(checked_path(path),max_bytes=256*1024)
        fields(value,'schema_version artifact_id source_sha256 resources')
        if value['schema_version']!=1 or value['artifact_id']!=row['artifact_id'] or value['source_sha256']!=row['sha256']:raise ValueError('stale catalog source identity')
        if type(value['resources']) is not list or len(value['resources'])>500:raise ValueError('catalog batch budget exceeded')
        for item in value['resources']:
            checked=_entry(row,item)
            if checked!=item:raise ValueError('catalog entry identity changed')
            result[item['resource_id']]=item
        if len(result)>MAX_ENTRIES:raise ValueError('catalog entry budget exceeded')
    return result


def _entry(row,item):
    item=dict(item);item.pop('resource_id', None);fields(item,'name kind offset length format')
    label(item['name'],128);label(item['kind'],32);label(item['format'],128,blank=True)
    number(item['offset'],0,row['size']);number(item['length'],1,row['size'])
    if item['offset']+item['length']>row['size']:raise ValueError('catalog resource exceeds source')
    return {**item,'resource_id':digest({'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],**item})}


def add_resources(project,artifact_id,resources):
    row=p.artifact(project,artifact_id);p._measure(row['path'],row)
    if type(resources) is not list or not 1<=len(resources)<=500:raise ValueError('index1..500 resources per transaction')
    existing=_rows(project,row);entries=[_entry(row,item) for item in resources]
    combined={**existing,**{item['resource_id']:item for item in entries}}
    if len(combined)>MAX_ENTRIES:raise ValueError('catalog entry budget exceeded')
    value={'schema_version':1,'artifact_id':artifact_id,'source_sha256':row['sha256'],'resources':entries}
    raw=canonical_bytes(value,max_bytes=256*1024);folder=checked_path(Path(project)/'catalog'/artifact_id);folder.mkdir(parents=True,exist_ok=True)
    destination=folder/(digest(value)+'.json')
    p._measure(row['path'],row)
    if not destination.exists():
        if len(list(folder.glob('*.json')))>=128:raise ValueError('catalog batch budget exceeded')
        fd,name=tempfile.mkstemp(prefix='.catalog-',dir=folder)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.link(name,destination)
        finally:Path(name).unlink(missing_ok=True)
    return {'ok':True,'status':'INDEXED','total':len(combined),'write_authorized':False}


def list_resources(project,artifact_id,query,page,limit):
    label(query,128,blank=True);number(page,0,MAX_ENTRIES);number(limit,1,100)
    row=p.artifact(project,artifact_id);p._measure(row['path'],row);rows=list(_rows(project,row).values())
    query=query.casefold();matches=sorted((r for r in rows if query in (r['name']+' '+r['kind']+' '+r['format']).casefold()),key=lambda r:(r['name'].casefold(),r['resource_id']))
    p._measure(row['path'],row)
    return {'ok':True,'source_sha256':row['sha256'],'artifact_id':artifact_id,'total':len(matches),'page':page,'limit':limit,
        'resources':matches[page*limit:(page+1)*limit],'write_authorized':False,'scope':'declared_resource_catalog'}


def index_declared(project,artifact_id):
    row=p.artifact(project,artifact_id);entries=[];schemas=row.get('descriptors',{})
    p._measure(row['path'],row)
    def add(name,kind,offset,length,format):
        entries.append({'name':name[:128],'kind':kind,'offset':offset,'length':length,'format':format[:128]})
    if schemas.get('assets'):
        from .assets import inspect_assets
        from .asset_schema import validate_asset_schema
        from .asset_codecs import cell_size
        schema=validate_asset_schema(schemas['assets'])['normalized_schema'];result=inspect_assets(Path(row['path']),schema)
        if not result['ok']:raise ValueError('asset declaration cannot be indexed')
        for bitmap in schema['bitmaps']:
            size=cell_size(bitmap['codec'],bitmap['width'],bitmap['height'])
            for index in range(bitmap['count']):entries.append({'name':bitmap['id']+' / cell '+str(index),'kind':'tile','offset':bitmap['offset']+index*size,'length':size,'format':bitmap['codec']})
        for kind in ('palettes','tilemaps'):
            for item in schema[kind]:entries.append({'name':item['id'],'kind':kind[:-1],'offset':item['offset'],'length':item['length'],'format':'declared '+kind[:-1]})
    if schemas.get('script'):
        from .script import inspect_script
        result=inspect_script(Path(row['path']),schemas['script'])
        if not result['ok']:raise ValueError('text declaration cannot be indexed')
        for record in result['records']:entries.append({'name':record['id'],'kind':'text','offset':record['offset'],'length':record['capacity'],'format':'declared text slot'})
    table=schemas.get('tables')
    if table:
        if table.get('source_sha256')!=row['sha256']:raise ValueError('table catalog declaration source differs')
        from .data_tables import inspect_table
        d=inspect_table(row['path'],row['sha256'],table['definition'],0,1)['definition']
        add(d['name'],'table',d['offset'],d['count']*d['stride'],str(d['count'])+' declared records; '+', '.join(f['name'] for f in d['fields']))
    if schemas.get('levels') or schemas.get('sound'):
        from .workbench_files import read_bounded
        raw=read_bounded(row['path'],64*1024**2,row)
        if schemas.get('levels'):
            from .level_design import inspect_level
            doc=inspect_level(raw,schemas['levels'],row['sha256']);definition=doc['definition']
            for span in doc['ranges']:
                if span['name'] in ('tiles','metatiles','palette'):
                    add(definition['name']+' / '+span['name'],span['name'],span['offset'],span['length'],'declared level '+span['name'])
            for room in definition['rooms']:
                for key,kind in (('terrain','room'),('collision','collision')):
                    grid=room[key]
                    if grid:add(room['name']+' / '+key,kind,grid['offset'],room['width']*room['height']*grid['entry_bytes'],'declared '+str(room['width'])+' x '+str(room['height'])+' grid')
                objects=room['objects']
                if objects:
                    add(room['name']+' / object slots','objects',objects['offset'],objects['count']*objects['stride'],'declared fixed records')
                    for metadata in room.get('object_metadata',[]):
                        add(room['name']+' / '+metadata['name'],'object',objects['offset']+metadata['index']*objects['stride'],objects['stride'],'declared '+metadata['role'])
        if schemas.get('sound'):
            from .sound_studio import inspect_sound
            doc=inspect_sound(raw,schemas['sound'],row['sha256'])
            for sample in doc['samples']:add(sample['name'],'sample',sample['offset'],sample['length'],sample['codec'])
            for song in doc['songs']:add(song['name'],'song',song['offset'],song['count']*song['stride'],song['driver'])
    if not entries:return {'ok':True,'status':'EMPTY','total':0,'write_authorized':False}
    for start in range(0,len(entries),500):add_resources(project,artifact_id,entries[start:start+500])
    return {'ok':True,'status':'INDEXED','total':len(entries),'write_authorized':False}
