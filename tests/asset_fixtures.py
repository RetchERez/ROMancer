import hashlib

P = {'origin':'synthetic_fixture','note':'Handwritten original fixture','reference':None}


def asset_fixture(root):
    data=bytearray(b'\xa5'*64)
    data[4:20]=bytes.fromhex('80000000000000000000000000000001')
    data[20:28]=bytes.fromhex('8000801f83e0fc00')
    data[28:32]=bytes.fromhex('20006000')
    data[32:40]=bytes.fromhex('8142241818244281')
    data[40]=5
    source=root/'original art.bin';source.write_bytes(data)
    schema={'schema_version':1,'id':'handwritten-art','version':'1',
            'source':{'sha256':hashlib.sha256(data).hexdigest(),'size':64},
            'bitmaps':[
                {'id':'tiles','offset':4,'length':16,'codec':'tile8-planar2-msb-v1','width':8,'height':8,'count':1,'palette_id':'colors','provenance':dict(P)},
                {'id':'font_cells','offset':32,'length':8,'codec':'mono-row-msb-v1','width':8,'height':8,'count':1,'palette_id':None,'provenance':dict(P)}],
            'palettes':[{'id':'colors','offset':20,'length':8,'entry_bytes':2,'byte_order':'big','banks':1,'colors_per_bank':4,'channels':{'r':31,'g':992,'b':31744},'provenance':dict(P)}],
            'tilemaps':[{'id':'map','offset':28,'length':4,'entry_bytes':2,'byte_order':'big','width':2,'height':1,'bitmap_id':'tiles','palette_id':'colors','fields':{
                'tile_index':{'kind':'bits','mask':1023},'palette_bank':{'kind':'constant','value':0},
                'flip_x':{'kind':'bits','mask':16384},'flip_y':{'kind':'bits','mask':32768}},'provenance':dict(P)}],
            'fonts':[{'id':'font','glyphs':[{'id':'glyph','bitmap_id':'font_cells','cell_index':0,'bearing':{'x':0,'y':0},'advance':{'kind':'u8','offset':40},'provenance':dict(P)}],'provenance':dict(P)}],
            'provenance':dict(P)}
    return source,schema
