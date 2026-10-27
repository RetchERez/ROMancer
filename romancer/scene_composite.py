"""Bounded staged-color composites; never presented as emulated gameplay."""
import base64,hashlib
from io import BytesIO
from PIL import Image
from .asset_schema import number,fields
from .visual_checks import _png

def composite(scene,definition,source_tiles,edits):
    width=number(scene['width'],1,1024);height=number(scene['height'],1,1024)
    if width*height>262144:raise ValueError('Captured scene exceeds the preview budget.')
    encoded=scene['png_base64']
    if type(encoded) is not str or len(encoded)>2*1024**2:raise ValueError('Captured scene image exceeds its budget.')
    with Image.open(BytesIO(base64.b64decode(encoded,validate=True))) as image:
        if image.format!='PNG' or image.size!=(width,height):raise ValueError('Scene dimensions differ from the captured frame.')
        before=image.convert('RGB').tobytes()
    if hashlib.sha256(before).hexdigest()!=scene['sha256']:raise ValueError('Captured scene identity changed.')
    layout=definition['layout'];region=definition['scene_region'];x=number(region['x'],0,width-1);y=number(region['y'],0,height-1)
    columns=number(layout['columns'],1,8);rows=number(layout['rows'],1,8)
    if x+columns*8>width or y+rows*8>height:raise ValueError('Object placement lies outside the captured scene.')
    if any(len(layout[k])!=columns*rows for k in ('indices','flips','colors')):raise ValueError('Object layout dimensions differ.')
    if type(edits) is not list or len(edits)>64:raise ValueError('Preview up to64 changed source tiles.')
    changed={};used={i for i in layout['indices'] if i is not None}
    for edit in edits:
        fields(edit,'cell_index pixels');index=number(edit['cell_index'],0,1023)
        if index not in used or index in changed:raise ValueError('Choose each used source tile only once.')
        if type(edit['pixels']) is not list or len(edit['pixels'])!=64:raise ValueError('A source tile needs64 pixels.')
        for v in edit['pixels']:number(v,0,15)
        if index not in source_tiles or len(source_tiles[index])!=64:raise ValueError('Original source tile is unavailable.')
        changed[index]=edit['pixels']
    after=bytearray(before)
    for part,index in enumerate(layout['indices']):
        if index not in changed:continue
        flip=number(layout['flips'][part],0,3);colors=layout['colors'][part] or {}
        for yy in range(8):
            for xx in range(8):
                source=(7-yy if flip&2 else yy)*8+(7-xx if flip&1 else xx);value=changed[index][source]
                if value==source_tiles[index][source]:continue
                color=colors.get(str(value))
                if type(color) is not list or len(color)!=3:raise ValueError('This color was not observed at the placement. Use a captured color or test the actual build.')
                for channel in color:number(channel,0,255)
                address=((y+(part//columns)*8+yy)*width+x+(part%columns)*8+xx)*3;after[address:address+3]=bytes(color)
    count=sum(before[i:i+3]!=after[i:i+3] for i in range(0,len(before),3))
    return {'ok':True,'width':width,'height':height,'original_png_base64':encoded,'preview_png_base64':_png(bytes(after),width,height),'changed_pixels':count,'staged_cells':len(changed),'simulated':True,'emulated_frame':False,'rom_written':False,'scope':'Staged composite using captured colors and verified placements. Only saved placements are composited; other uses of the same source may change. Transparency, priority, palette ownership, animation and gameplay are not reconstructed; test the build for the real result.'}
