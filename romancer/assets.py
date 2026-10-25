"""Fresh, revision-bound inspection and semantic plans for uncompressed assets."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import ntpath
import os
from pathlib import Path
import stat
from typing import BinaryIO
from . import ROMANCER_VERSION
from .asset_codecs import CODECS, cell_size, decode_cell, encode_cell
from .asset_schema import fields, number, mask_info, validate_asset_schema
from .font_metrics import measure_bitmap
from .script_schema import canonical_bytes


def digest(value):
    return hashlib.sha256(canonical_bytes(value,max_bytes=8*1024*1024)).hexdigest()


def identity(info):
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns


def checked_path(value):
    raw=os.fspath(value)
    if os.name=='nt':
        drive,root,_=ntpath.splitroot(raw)
        if (drive and not root) or os.path.isreserved(raw) or raw.startswith(('\\\\?\\','\\\\.\\')):
            raise ValueError('ambiguous or reserved Windows path')
    path=Path(value).absolute()
    for item in (path,*path.parents):
        if item.is_symlink() or item.is_junction():raise ValueError('linked path ancestry is unsupported')
    return path


def hash_stream(stream):
    stream.seek(0);hasher=hashlib.sha256()
    while data:=stream.read(65536):hasher.update(data)
    return hasher.hexdigest()


def _word(stream,row,index):
    offset=row['offset']+index*row['entry_bytes'];stream.seek(offset)
    raw=stream.read(row['entry_bytes'])
    if len(raw)!=row['entry_bytes']:raise ValueError('source truncated')
    return offset,raw,int.from_bytes(raw,row['byte_order'])


def _map_values(word,row):
    return {name:field['value'] if field['kind']=='constant' else
            ((word&field['mask'])>>mask_info(field['mask'],row['entry_bytes'])[0])
            for name,field in row['fields'].items()}


def _inspect_stream(stream: BinaryIO, checked_schema: dict) -> dict:
    schema=checked_schema['normalized_schema'];bitmaps=[];palettes=[];maps=[];fonts=[]
    for row in schema['bitmaps']:
        stream.seek(row['offset']);raw=stream.read(row['length'])
        result={**row,'raw_hex':raw.hex(),'raw_sha256':hashlib.sha256(raw).hexdigest(),'cells':[]}
        if row['codec'] in CODECS:
            size=cell_size(row['codec'],row['width'],row['height'])
            for index in range(row['count']):
                cell=raw[index*size:(index+1)*size]
                pixels=decode_cell(cell,codec=row['codec'],width=row['width'],height=row['height'])
                if encode_cell(pixels,codec=row['codec'],width=row['width'],height=row['height'])!=cell:
                    raise ValueError('codec did not round trip')
                result['cells'].append({'index':index,'pixels':pixels,'raw_hex':cell.hex()})
        bitmaps.append(result)
    for row in schema['palettes']:
        colors=[]
        for index in range(row['banks']*row['colors_per_bank']):
            offset,raw,word=_word(stream,row,index)
            components={name:(word&mask)>>mask_info(mask,row['entry_bytes'])[0] for name,mask in row['channels'].items()}
            rgb={name:components[name]*255//mask_info(mask,row['entry_bytes'])[1] for name,mask in row['channels'].items()}
            colors.append({'bank':index//row['colors_per_bank'],'index':index%row['colors_per_bank'],
                           'components':components,'rgb':rgb,'raw_hex':raw.hex(),'offset':offset})
        palettes.append({**row,'entries':colors})
    bitmap_by_id={x['id']:x for x in bitmaps};palette_by_id={x['id']:x for x in palettes}
    for row in schema['tilemaps']:
        entries=[]
        for index in range(row['width']*row['height']):
            offset,raw,word=_word(stream,row,index);values=_map_values(word,row)
            if values['tile_index']>=bitmap_by_id[row['bitmap_id']]['count'] or values['palette_bank']>=palette_by_id[row['palette_id']]['banks']:
                raise ValueError('tilemap references an unavailable cell or palette bank')
            entries.append({'index':index,'values':values,'raw_hex':raw.hex(),'offset':offset})
        maps.append({**row,'entries':entries})
    for font in schema['fonts']:
        glyphs=[]
        for glyph in font['glyphs']:
            bitmap=bitmap_by_id[glyph['bitmap_id']];raw=bytes.fromhex(bitmap['cells'][glyph['cell_index']]['raw_hex'])
            if glyph['advance']['kind']=='u8':
                stream.seek(glyph['advance']['offset']);advance=stream.read(1)
                if len(advance)!=1 or advance[0]>128:raise ValueError('font advance exceeds supported bounds')
                advance=advance[0]
            else:advance=glyph['advance']['pixels']
            glyphs.append({**glyph,'advance_pixels':advance,'measurement':measure_bitmap(raw,width=bitmap['width'],height=bitmap['height'],row_stride=(bitmap['width']+7)//8)})
        fonts.append({**font,'glyphs':glyphs})
    return {'schema_version':1,'tool_version':ROMANCER_VERSION,'operation':'asset-inspect','ok':True,'status':'INSPECTED',
            'source_sha256':schema['source']['sha256'],'source_size':schema['source']['size'],
            'schema_sha256':checked_schema['schema_sha256'],'write_supported':checked_schema['write_supported'],
            'read_only_reasons':checked_schema['read_only_reasons'],'bitmaps':bitmaps,'palettes':palettes,'tilemaps':maps,'fonts':fonts,
            'relationship_coverage':'declared_only','native_render_verified':False,
            'document_id':digest({'asset_version':1,'tool_version':ROMANCER_VERSION,'source_sha256':schema['source']['sha256'],
                                  'source_size':schema['source']['size'],'schema_sha256':checked_schema['schema_sha256']})}


@dataclass(frozen=True)
class AssetSource:
    path: Path
    stream: BinaryIO
    opened_stat: os.stat_result
    checked_schema: dict
    document: dict


def _recheck_asset_source(held: AssetSource) -> None:
    checked_path(held.path)
    if identity(held.path.stat())!=identity(held.opened_stat) or identity(os.fstat(held.stream.fileno()))!=identity(held.opened_stat):
        raise ValueError('source identity changed')
    if hash_stream(held.stream)!=held.document['source_sha256']:raise ValueError('source content changed')


@contextmanager
def _asset_source(source: Path, schema: dict):
    checked=validate_asset_schema(schema);path=checked_path(source);before=path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:raise ValueError('source must be an ordinary single-link file')
    if before.st_size!=checked['normalized_schema']['source']['size']:raise ValueError('source size mismatch')
    with path.open('rb',buffering=0) as stream:
        if identity(os.fstat(stream.fileno()))!=identity(before):raise ValueError('source changed before open')
        if hash_stream(stream)!=checked['normalized_schema']['source']['sha256']:raise ValueError('source revision mismatch')
        document=_inspect_stream(stream,checked)
        held=AssetSource(path,stream,before,checked,document)
        _recheck_asset_source(held)
        yield held
        _recheck_asset_source(held)


def failure(operation,exc):
    return {'schema_version':1,'operation':operation,'ok':False,'status':'CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED',
            'error':str(exc)[:2048],'error_code':type(exc).__name__,'written':False,'warnings':[]}


def _bounded(result):
    if len(json.dumps(result,ensure_ascii=True,indent=2).encode('ascii'))+1>8*1024*1024:raise ValueError('asset report exceeds 8 MiB')
    return result


def inspect_assets(source: Path, schema: dict) -> dict:
    try:
        with _asset_source(source,schema) as held:result=_bounded(held.document)
        return result
    except (ValueError,OSError,KeyboardInterrupt) as exc:return failure('asset-inspect',exc)


def consumer_key(row):
    if row.get('kind')=='map':
        fields(row,'kind id entry_index');return ('map',row['id'],row['entry_index'])
    if row.get('kind')=='glyph':
        fields(row,'kind font_id glyph_id');return ('glyph',row['font_id'],row['glyph_id'])
    raise ValueError('unknown consumer key')


def _compile_assets(document: dict, checked_schema: dict, edits: dict) -> dict:
    request=json.loads(canonical_bytes(edits,max_bytes=1024*1024))
    fields(request,'schema_version document_id changes acknowledged_consumers');number(request['schema_version'],1,1)
    if request['document_id']!=document['document_id']:raise ValueError('stale asset document')
    if not document['write_supported']:raise ValueError('unsupported descriptor is read-only')
    if type(request['changes']) is not list or len(request['changes'])>1024:raise ValueError('asset edit budget exceeded')
    if type(request['acknowledged_consumers']) is not list or len(request['acknowledged_consumers'])>4352:raise ValueError('consumer budget exceeded')
    acknowledged=[consumer_key(row) for row in request['acknowledged_consumers']]
    if acknowledged!=sorted(set(acknowledged)):raise ValueError('consumer keys must be unique and sorted')
    groups={name:{row['id']:row for row in document[name]} for name in ('bitmaps','palettes','tilemaps','fonts')}
    final_maps={name:[dict(e['values']) for e in row['entries']] for name,row in groups['tilemaps'].items()}
    hunks=[];targets=set();changed_cells=[];changed_palettes=[];required=set()
    def hunk(offset,before,after,mask=None):
        if before!=after:hunks.append({'offset':offset,'before_hex':before.hex(),'after_hex':after.hex(),
                                      'writable_mask_hex':(mask if mask is not None else b'\xff'*len(before)).hex()})
    for change in request['changes']:
        if type(change) is not dict:raise ValueError('invalid asset change')
        kind=change.get('kind')
        if kind=='cell':
            fields(change,'kind bitmap_id cell_index before_pixels after_pixels')
            row=groups['bitmaps'][change['bitmap_id']];index=number(change['cell_index'],0,row['count']-1)
            key=(kind,row['id'],index);before=row['cells'][index]
            if change['before_pixels']!=before['pixels']:raise ValueError('cell precondition mismatch')
            # Encoding validates both arrays, including bool-as-int.
            encode_cell(change['before_pixels'],codec=row['codec'],width=row['width'],height=row['height'])
            after=encode_cell(change['after_pixels'],codec=row['codec'],width=row['width'],height=row['height'])
            original=bytes.fromhex(before['raw_hex']);hunk(row['offset']+index*len(original),original,after)
            if original!=after:changed_cells.append((row['id'],index))
        elif kind=='palette':
            fields(change,'kind palette_id bank index before after')
            row=groups['palettes'][change['palette_id']];bank=number(change['bank'],0,row['banks']-1);index=number(change['index'],0,row['colors_per_bank']-1)
            key=(kind,row['id'],bank,index);entry=row['entries'][bank*row['colors_per_bank']+index]
            fields(change['before'],'r g b');fields(change['after'],'r g b')
            if change['before']!=entry['components']:raise ValueError('palette precondition mismatch')
            original=bytes.fromhex(entry['raw_hex']);word=int.from_bytes(original,row['byte_order']);mask=0
            for name,bits in row['channels'].items():
                shift,maximum=mask_info(bits,row['entry_bytes']);number(change['before'][name],0,maximum);value=number(change['after'][name],0,maximum)
                word=(word&~bits)|(value<<shift);mask|=bits
            after=word.to_bytes(row['entry_bytes'],row['byte_order']);hunk(entry['offset'],original,after,mask.to_bytes(row['entry_bytes'],row['byte_order']))
            if original!=after:changed_palettes.append((row['id'],bank))
        elif kind=='map':
            fields(change,'kind tilemap_id entry_index before after')
            row=groups['tilemaps'][change['tilemap_id']];index=number(change['entry_index'],0,len(row['entries'])-1)
            key=(kind,row['id'],index);entry=row['entries'][index]
            fields(change['before'],'tile_index palette_bank flip_x flip_y');fields(change['after'],'tile_index palette_bank flip_x flip_y')
            if change['before']!=entry['values']:raise ValueError('map precondition mismatch')
            original=bytes.fromhex(entry['raw_hex']);word=int.from_bytes(original,row['byte_order']);mask=0
            for name,field in row['fields'].items():
                maximum=1 if name.startswith('flip_') else (groups['bitmaps'][row['bitmap_id']]['count']-1 if name=='tile_index' else groups['palettes'][row['palette_id']]['banks']-1)
                value=number(change['after'][name],0,maximum);number(change['before'][name],0,maximum)
                if field['kind']=='constant':
                    if value!=field['value']:raise ValueError('constant map field cannot change')
                else:
                    shift,storage_max=mask_info(field['mask'],row['entry_bytes'])
                    if value>storage_max:raise ValueError('map value does not fit storage')
                    word=(word&~field['mask'])|(value<<shift);mask|=field['mask']
            after=word.to_bytes(row['entry_bytes'],row['byte_order']);hunk(entry['offset'],original,after,mask.to_bytes(row['entry_bytes'],row['byte_order']))
            final_maps[row['id']][index]=dict(change['after'])
            if original!=after:required.add(('map',row['id'],index))
        elif kind=='advance':
            fields(change,'kind font_id glyph_id before after');font=groups['fonts'][change['font_id']]
            glyph=next((g for g in font['glyphs'] if g['id']==change['glyph_id']),None)
            if glyph is None or glyph['advance']['kind']!='u8':raise ValueError('unknown or declared-only font advance')
            number(change['before'],0,128);number(change['after'],0,128)
            if change['before']!=glyph['advance_pixels']:raise ValueError('advance precondition mismatch')
            key=(kind,font['id'],glyph['id']);hunk(glyph['advance']['offset'],bytes([change['before']]),bytes([change['after']]))
            if change['before']!=change['after']:required.add(('glyph',font['id'],glyph['id']))
        else:raise ValueError('unknown asset change kind')
        if key in targets:raise ValueError('duplicate asset target')
        targets.add(key)
    for row in document['tilemaps']:
        for entry,final in zip(row['entries'],final_maps[row['id']]):
            if ((row['bitmap_id'],entry['values']['tile_index']) in changed_cells
                    or (row['bitmap_id'],final['tile_index']) in changed_cells
                    or (row['palette_id'],entry['values']['palette_bank']) in changed_palettes
                    or (row['palette_id'],final['palette_bank']) in changed_palettes):
                required.add(('map',row['id'],entry['index']))
    for font in document['fonts']:
        for glyph in font['glyphs']:
            if (glyph['bitmap_id'],glyph['cell_index']) in changed_cells:required.add(('glyph',font['id'],glyph['id']))
    consumers=[{'kind':'map','id':key[1],'entry_index':key[2]} if key[0]=='map' else {'kind':'glyph','font_id':key[1],'glyph_id':key[2]} for key in sorted(required)]
    result={'schema_version':1,'operation':'asset-plan','ok':acknowledged==sorted(required),
            'status':'PLANNED' if hunks else 'NO_CHANGES','document_id':document['document_id'],
            'source_sha256':document['source_sha256'],'schema_sha256':document['schema_sha256'],
            'hunks':sorted(hunks,key=lambda h:h['offset']),'required_consumers':consumers,
            'affected_consumers':consumers,'relationship_coverage':'declared_only','native_render_verified':False,
            'normalized_request':request}
    if not result['ok']:result.update(status='BLOCKED',error='acknowledge exactly the affected declared consumers')
    result['plan_id']=digest({'asset_plan_version':1,'tool_version':ROMANCER_VERSION,'document_id':document['document_id'],
                              'normalized_request':request,'hunks':result['hunks'],'affected_consumers':consumers})
    return _bounded(result)


def plan_assets(source: Path, schema: dict, edits: dict) -> dict:
    try:
        with _asset_source(source,schema) as held:result=_compile_assets(held.document,held.checked_schema,edits)
        return result
    except (ValueError,OSError,KeyError,TypeError,KeyboardInterrupt) as exc:return failure('asset-plan',exc)
