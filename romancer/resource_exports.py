"""Indexed source previews and explicitly declared resource-use summaries."""
import io
from PIL import Image
from .asset_codecs import CODECS
from .asset_schema import number
from .assets import inspect_assets


def export_tile_sheet(source,schema,bitmap_id,columns,bank=0):
    document=inspect_assets(source,schema)
    if not document['ok']:raise ValueError(str(document.get('error','cannot inspect the selected graphics')))
    bitmap=next((row for row in document['bitmaps'] if row['id']==bitmap_id),None)
    if bitmap is None or bitmap['codec'] not in CODECS or len(bitmap['cells'])!=bitmap['count']:raise ValueError('choose a decoded supported bitmap')
    number(columns,1,min(64,bitmap['count']));number(bank,0,15)
    palette=next((row for row in document['palettes'] if row['id']==bitmap['palette_id']),None)
    count=2**CODECS[bitmap['codec']]
    if palette:
        if bank>=palette['banks'] or palette['colors_per_bank']<count:raise ValueError('palette bank is unavailable for this bitmap')
        colors=[row['rgb'] for row in palette['entries'][bank*palette['colors_per_bank']:bank*palette['colors_per_bank']+count]];scope='declared-palette'
    else:
        if bank:raise ValueError('this resource has no declared palette banks')
        colors=[{key:round(18+index*216/(count-1)) for key in ('r','g','b')} for index in range(count)];scope='inspection-aid'
    width=columns*bitmap['width'];height=((bitmap['count']+columns-1)//columns)*bitmap['height'];pixels=bytearray(width*height)
    for cell in bitmap['cells']:
        left=(cell['index']%columns)*bitmap['width'];top=(cell['index']//columns)*bitmap['height']
        for y in range(bitmap['height']):
            for x in range(bitmap['width']):pixels[(top+y)*width+left+x]=cell['pixels'][y*bitmap['width']+x]
    image=Image.frombytes('P',(width,height),bytes(pixels));flat=[value for rgb in colors for value in (rgb['r'],rgb['g'],rgb['b'])]
    image.putpalette(flat+[0]*(768-len(flat)));output=io.BytesIO();image.save(output,format='PNG')
    encoded=output.getvalue()
    if len(encoded)>512*1024:raise ValueError('tile sheet PNG exceeds the import/export budget')
    with Image.open(io.BytesIO(encoded)) as check:
        if check.mode!='P' or check.size!=(width,height) or check.tobytes()!=bytes(pixels):raise ValueError('independent indexed PNG readback differs')
    return {'ok':True,'status':'EXPORTED','png':encoded,'width':width,'height':height,'palette_rgb':colors,'palette_scope':scope,
            'source_sha256':document['source_sha256'],'bitmap_id':bitmap_id,'palette_bank':bank,'palette_indices_preserved':True}


def declared_usage(document,bitmap_id,cell_index):
    bitmap=next((row for row in document.get('bitmaps',[]) if row['id']==bitmap_id),None)
    if not document.get('ok') or bitmap is None:raise ValueError('inspect a declared bitmap first')
    number(cell_index,0,bitmap['count']-1);uses=[]
    for tilemap in document.get('tilemaps',[]):
        if tilemap['bitmap_id']!=bitmap_id:continue
        for entry in tilemap['entries']:
            if entry['values']['tile_index']==cell_index:uses.append({'kind':'tilemap','id':tilemap['id'],'entry_index':entry['index'],'offset':entry['offset']})
    for font in document.get('fonts',[]):
        for glyph in font['glyphs']:
            if glyph['bitmap_id']==bitmap_id and glyph['cell_index']==cell_index:uses.append({'kind':'font','id':font['id'],'glyph_id':glyph['id']})
    return {'ok':True,'bitmap_id':bitmap_id,'cell_index':cell_index,'uses':uses[:4096],'truncated':len(uses)>4096,'source_sha256':document['source_sha256'],'document_id':document['document_id'],
            'relationship_coverage':'declared_only','native_render_verified':False,'note':'Undeclared uses remain unknown.'}


def declared_address_uses(path,sha,descriptors,offset):
    from .workbench_projects import _measure
    source=_measure(path)
    if source['sha256']!=sha:raise ValueError('source revision changed')
    number(offset,0,source['size']-1);uses=[];partial=False
    script=descriptors.get('script')
    if script:
        from .script import inspect_script
        document=inspect_script(path,script)
        if not document['ok']:raise ValueError('saved text definition no longer inspects this source')
        for row in document['records']:
            if row['offset']<=offset<row['offset']+row['capacity']:uses.append({'kind':'text','name':row['id'],'offset':row['offset']})
        for row in document['pointers']:
            if row['target_offset']==offset:uses.append({'kind':'text-pointer','name':row['id'],'offset':row['offset']})
    table=descriptors.get('tables')
    if table and table.get('source_sha256')==sha:
        from .data_tables import _context,_read
        with _context(path,sha,table['definition']) as (stream,identity,definition):
            partial=definition['count']>4096
            for index in range(min(4096,definition['count'])):
                for field in definition['fields']:
                    if field['pointer_base'] is None:continue
                    cell=_read(stream,definition,index,field,identity['size'])
                    if cell['target_offset']==offset and len(uses)<4096:uses.append({'kind':'table-pointer','name':definition['name']+' · '+str(index)+' · '+field['name'],'offset':cell['offset']})
    assets=descriptors.get('assets')
    if assets:
        document=inspect_assets(path,assets)
        if not document['ok']:raise ValueError('saved graphics definition no longer inspects this source')
        from .asset_codecs import cell_size
        for bitmap in document['bitmaps']:
            if bitmap['offset']<=offset<bitmap['offset']+bitmap['length']:
                index=(offset-bitmap['offset'])//cell_size(bitmap['codec'],bitmap['width'],bitmap['height'])
                for row in declared_usage(document,bitmap['id'],index)['uses']:uses.append({'kind':row['kind'],'name':row['id'],'offset':row.get('offset',bitmap['offset'])})
    _measure(path,source)
    return {'ok':True,'source_sha256':sha,'target_offset':offset,'uses':uses[:4096],'partial':partial or len(uses)>4096,'relationship_coverage':'declared_only'}
