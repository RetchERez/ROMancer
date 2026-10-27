"""Guided declarations for existing verified resource engines; no game offsets inferred."""
import io
from pathlib import Path
import re
from .asset_schema import number,validate_asset_schema
from .asset_codecs import CODECS,cell_size
from .script_schema import validate_schema
from .system_registry import SYSTEM_IDS
from .workbench_projects import _measure
from .assets import digest

PROVENANCE={'origin':'profile_assertion','note':'Explicit resource declaration entered in ROMancer.','reference':None}
TEMPLATES={'sms':'tile8-rowplanar4-msb-v1','gb':'tile8-paired2-msb-v1','gbc':'tile8-paired2-msb-v1','nes':'tile8-planar2-msb-v1','snes':'tile8-paired4-msb-v1','genesis':'tile8-packed4-high-v1','segacd':'tile8-packed4-high-v1','gba':'tile8-packed4-low-v1'}


def _source(path,sha):
    measured=_measure(path)
    if measured['sha256']!=sha:raise ValueError('source revision changed')
    if not 1<=measured['size']<=64*1024**2:raise ValueError('declare a flat resource of at most64MiB')
    return measured


def _system(config):
    system=config.get('system_id')
    if system not in SYSTEM_IDS:raise ValueError('choose a supported system template')
    return system


def script_schema(path,sha,config):
    source=_source(path,sha);system=_system(config)
    allowed={'system_id','offset','capacity','count','stride','pointer_offset','pointer_width','pointer_endian','pointer_base','terminator','padding','encoding','table','controls'}
    if set(config)-allowed:raise ValueError('unknown text declaration field')
    offset=number(config['offset'],0,source['size']);capacity=number(config['capacity'],1,65536);count=number(config['count'],1,256)
    stride=number(config.get('stride',capacity),capacity,source['size']);pointer_offset=None if config.get('pointer_offset') is None else number(config['pointer_offset'],0,source['size']);width=number(config.get('pointer_width',2),2,4)
    base=number(config.get('pointer_base',0),-0xffffffff,0xffffffff);endian=config.get('pointer_endian','little')
    if endian not in ('little','big'):raise ValueError('choose pointer byte order')
    if config.get('encoding','ascii')=='ascii':glyphs=[{'byte':i,'text':chr(i)} for i in range(32,127)]
    elif config['encoding']=='table':
        glyphs=[]
        for line in config.get('table','').splitlines():
            if not line:continue
            match=re.fullmatch(r'([0-9a-fA-F]{2})=(.)',line)
            if not match:raise ValueError('encoding table uses one HH=character entry per line')
            glyphs.append({'byte':int(match[1],16),'text':match[2]})
    else:raise ValueError('choose ASCII or a single-byte table')
    rules=[];records=[];pointers=[]
    with Path(path).open('rb') as stream:
        for i in range(count):
            start=offset+i*stride;pointer=None if pointer_offset is None else pointer_offset+i*width
            if start+capacity>source['size'] or (pointer is not None and pointer+width>source['size']):raise ValueError('text/pointer range exceeds source')
            stream.seek(start);slot=stream.read(capacity)
            rules.append({'resource':'slot-'+str(i),'offset':start,'length':capacity,'expected_hex':slot.hex()})
            records.append({'id':'line-'+str(i),'rule':'slot-'+str(i),'annotations':{'label':'Line '+str(i+1),'speaker_label':None,'speaker_provenance':None,'layout_ref':None}})
            if pointer is not None:
                stream.seek(pointer);stored=stream.read(width)
                rules.append({'resource':'pointer-'+str(i),'offset':pointer,'length':width,'expected_hex':stored.hex()})
                pointers.append({'id':'pointer-'+str(i),'rule':'pointer-'+str(i),'target_record':'line-'+str(i),'width':width,'endian':endian,'base':base})
    schema={'schema_version':1,'id':'declared-text','version':'1','artifact':{'kind':'flat-resource','size':source['size'],'integrity':'none'},
            'profile':{'schema_version':2,'id':'declared-text-resource','version':'1','system':system,'accepted_sha256':[sha],'rules':rules},
            'format':{'family':'fixed-slots-direct' if pointer_offset is None else 'fixed-slots','version':1,'encoding':{'kind':'single-byte','glyphs':glyphs},'controls':config.get('controls',[]),
                      'terminator':{'byte':config.get('terminator',0)},'padding':{'byte':config.get('padding',255)},'records':records,'pointers':pointers,'guards':[]}}
    _measure(path,source);return validate_schema(schema)['normalized_schema']


def graphics_schema(path,sha,config):
    source=_source(path,sha);system=_system(config)
    allowed={'system_id','offset','count','codec','width','height','palette_offset','palette_banks','palette_format','map_offset','map_width','map_height','font_chars','advance_offset','advance_pixels'}
    if set(config)-allowed:raise ValueError('unknown graphics declaration field')
    codec=config.get('codec') or TEMPLATES[system]
    if codec not in CODECS:raise ValueError('unsupported declared codec')
    width=number(config.get('width',8),1,32);height=number(config.get('height',8),1,32);count=number(config['count'],1,1024)
    offset=number(config['offset'],0,source['size']);length=cell_size(codec,width,height)*count
    palette_offset=config.get('palette_offset');palette_id='colors' if palette_offset is not None else None
    bitmap={'id':'tiles','offset':offset,'length':length,'codec':codec,'width':width,'height':height,'count':count,'palette_id':palette_id,'provenance':PROVENANCE}
    palettes=[];maps=[];fonts=[]
    if palette_offset is not None:
        number(palette_offset,0,source['size']);banks=number(config.get('palette_banks',1),1,16);colors=2**CODECS[codec]
        fmt=config.get('palette_format','genesis' if system in ('genesis','segacd') else 'sms-rgb222' if system=='sms' else 'rgb555-le')
        formats={'genesis':(2,'big',{'r':14,'g':224,'b':3584}),'rgb555-le':(2,'little',{'r':31,'g':992,'b':31744}),'rgb555-be':(2,'big',{'r':31,'g':992,'b':31744}),'sms-rgb222':(1,'little',{'r':3,'g':12,'b':48})}
        if fmt not in formats:raise ValueError('unsupported palette format')
        entry_bytes,byte_order,channels=formats[fmt]
        palettes=[{'id':'colors','offset':palette_offset,'length':banks*colors*entry_bytes,'entry_bytes':entry_bytes,'byte_order':byte_order,'banks':banks,'colors_per_bank':colors,'channels':channels,'provenance':PROVENANCE}]
    if config.get('map_offset') is not None:
        if not palettes or (width,height)!=(8,8):raise ValueError('tilemap requires a palette and8x8 tiles')
        mw=number(config.get('map_width',1),1,64);mh=number(config.get('map_height',1),1,64)
        if system in ('nes','gb','gbc'):entry=1;fields={'tile_index':255,'palette_bank':None,'flip_x':None,'flip_y':None}
        elif system=='gba':entry=2;fields={'tile_index':1023,'palette_bank':61440,'flip_x':1024,'flip_y':2048}
        elif system=='snes':entry=2;fields={'tile_index':1023,'palette_bank':7168,'flip_x':16384,'flip_y':32768}
        elif system=='sms':entry=2;fields={'tile_index':511,'palette_bank':2048,'flip_x':512,'flip_y':1024}
        else:entry=2;fields={'tile_index':2047,'palette_bank':24576,'flip_x':2048,'flip_y':4096}
        maps=[{'id':'map','offset':config['map_offset'],'length':entry*mw*mh,'entry_bytes':entry,'byte_order':'big' if system in ('genesis','segacd') else 'little',
               'width':mw,'height':mh,'bitmap_id':'tiles','palette_id':'colors','fields':{key:({'kind':'constant','value':0} if mask is None else {'kind':'bits','mask':mask}) for key,mask in fields.items()},'provenance':PROVENANCE}]
    chars=config.get('font_chars','')
    if chars:
        if type(chars) is not str or len(chars)!=count or len(set(chars))!=count or codec!='mono-row-msb-v1':raise ValueError('font needs one unique character per mono cell')
        advance_offset=config.get('advance_offset');advance_pixels=number(config.get('advance_pixels',width),0,128)
        fonts=[{'id':'font','provenance':PROVENANCE,'glyphs':[{'id':'u'+format(ord(char),'04x'),'bitmap_id':'tiles','cell_index':i,'bearing':{'x':0,'y':0},
                'advance':({'kind':'u8','offset':advance_offset+i} if advance_offset is not None else {'kind':'declared','pixels':advance_pixels,'provenance':PROVENANCE}),'provenance':PROVENANCE} for i,char in enumerate(chars)]}]
    schema={'schema_version':1,'id':'declared-graphics','version':'1','source':source,'bitmaps':[bitmap],'palettes':palettes,'tilemaps':maps,'fonts':fonts,'provenance':PROVENANCE}
    _measure(path,source);return validate_asset_schema(schema)['normalized_schema']


def font_schema_from_assets(schema):
    schema=validate_asset_schema(schema)['normalized_schema'];bitmaps={b['id']:b for b in schema['bitmaps']};glyphs=[]
    for font in schema['fonts']:
        for glyph in font['glyphs']:
            bitmap=bitmaps[glyph['bitmap_id']];stride=(bitmap['width']+7)//8
            glyphs.append({'id':glyph['id'],'bitmap':{'offset':bitmap['offset']+glyph['cell_index']*stride*bitmap['height'],'width':bitmap['width'],'height':bitmap['height'],'row_stride':stride},'bearing':glyph['bearing'],'advance':glyph['advance'],'provenance':glyph['provenance']})
    from .font_metrics import validate_font_schema
    return validate_font_schema({'schema_version':1,'id':'declared-font','version':'1','source':schema['source'],'codec':'mono-row-msb-v1','glyphs':glyphs,'provenance':PROVENANCE})['normalized_schema']


def layout_policy(document,schema,font_schema,width,height,line_height):
    number(width,1,1024);number(height,1,1024);number(line_height,1,64)
    ids={g['id'] for g in font_schema['glyphs']}
    mapped=[{'byte':g['byte'],'glyph_id':g['text'] if g['text'] in ids else 'u'+format(ord(g['text']),'04x')} for g in schema['format']['encoding']['glyphs'] if g['text'] in ids or 'u'+format(ord(g['text']),'04x') in ids]
    if len(mapped)!=len(schema['format']['encoding']['glyphs']):raise ValueError('The font must map every character in the declared text encoding.')
    controls=[];effects={'line':'line_reset','page':'page_reset','pause':'pause_no_motion'}
    for control in schema['format']['controls']:
        if control['argument_length'] or control['layout_role'] not in effects:raise ValueError('guided layout supports argument-free line/page/pause controls; use advanced declaration for other controls')
        controls.append({'control_id':control['id'],'arguments_hex':'','effect':effects[control['layout_role']],'provenance':PROVENANCE})
    return {'schema_version':1,'id':'declared-layout','version':'1','model':'explicit-lines-v1','document_id':document['document_id'],'script_schema_sha256':document['schema_sha256'],'font_schema_sha256':digest(font_schema),
        'glyph_map':mapped,'boxes':[{'id':'box','width_px':width,'height_px':height,'line_height_px':line_height}],'controls':controls,
        'records':[{'record_id':r['id'],'box_id':'box','breaks':[]} for r in document['records']],
        'quality':{'orphan_max_words':1,'orphan_max_percent':25,'forbid_line_start':[],'forbid_line_end':[]},'provenance':PROVENANCE}


def menu_configuration(schema,font_schema,width,height,line_height):
    number(width,1,1024);number(height,1,1024);number(line_height,1,64)
    entries=[]
    for record in schema['format']['records'][:64]:
        cell={'id':'name','kind':'name','box':{'x':0,'y':0,'width':width,'height':line_height},'align':'left','style':'plain','record_id':record['id']}
        entries.append({'id':record['id'],'kind':'other','states':{'selected':[cell],'unselected':[cell]},'provenance':PROVENANCE})
    chars=[]
    for glyph in font_schema['glyphs']:
        if re.fullmatch(r'u[0-9a-f]{4,6}',glyph['id']):scalar=chr(int(glyph['id'][1:],16))
        elif len(glyph['id'])==1:scalar=glyph['id']
        else:continue
        chars.append({'scalar':scalar,'glyph_id':glyph['id'],'provenance':PROVENANCE})
    profile={'schema_version':1,'id':'declared-menu','version':'1','model':'fixed-menu-v1','script_schema_sha256':digest(schema),'viewport':{'width':width,'height':height},'row_step_px':line_height,'line_height_px':line_height,'entries':entries,'numeric_fields':[],'empty':None,'glyph_map':chars,'provenance':PROVENANCE}
    from .menu_schema import validate_menu_profile,validate_menu_cases
    checked=validate_menu_profile(profile,schema)
    cases={'schema_version':1,'profile_sha256':checked['sha256'],'cases':[{'id':'preview','entries':[e['id'] for e in entries[:min(64,height//line_height)]],'selected_entry':entries[0]['id'] if height>=line_height and entries else None,'dynamic_values':[],'provenance':PROVENANCE}]}
    validate_menu_cases(cases,profile)
    return {'profile':profile,'cases':cases}


def image_to_cells(raw,width,height,count,columns,palette,mode):
    from PIL import Image
    number(width,1,32);number(height,1,32);number(count,1,256);number(columns,1,count)
    if type(raw) is not bytes or len(raw)>512*1024 or mode not in ('exact','nearest') or type(palette) is not list or not 2<=len(palette)<=256:raise ValueError('invalid image mapping request')
    colors=[]
    for color in palette:
        if type(color) is not dict or set(color)!={'r','g','b'}:raise ValueError('invalid mapping palette')
        colors.append(tuple(number(color[c],0,255) for c in ('r','g','b')))
    rows=(count+columns-1)//columns
    with Image.open(io.BytesIO(raw)) as image:
        if image.format!='PNG' or image.size!=(width*columns,height*rows):raise ValueError('PNG dimensions must match the declared tile sheet')
        source_palette=image.getpalette('RGB') if image.mode=='P' else None
        preserve_indices=mode=='exact' and source_palette is not None and len(source_palette)>=len(colors)*3 and [tuple(source_palette[i*3:i*3+3]) for i in range(len(colors))]==colors
        pixels=image.convert('RGBA');cells=[];converted=0
        for cell in range(count):
            values=[]
            for y in range(height):
                for x in range(width):
                    r,g,b,a=pixels.getpixel(((cell%columns)*width+x,(cell//columns)*height+y))
                    if a!=255:raise ValueError('flatten transparency before mapping')
                    rgb=(r,g,b)
                    if preserve_indices:
                        index=image.getpixel(((cell%columns)*width+x,(cell//columns)*height+y))
                        if not 0<=index<len(colors):raise ValueError('PNG index is outside the declared palette')
                    elif rgb in colors:index=colors.index(rgb)
                    elif mode=='exact':raise ValueError('PNG includes colors outside the palette; select reviewed nearest-color conversion')
                    else:index=min(range(len(colors)),key=lambda i:sum((colors[i][c]-rgb[c])**2 for c in range(3)));converted+=1
                    values.append(index)
            cells.append(values)
    return {'ok':True,'cells':cells,'converted_pixels':converted,'mode':mode,'duplicate_colors':len(colors)!=len(set(colors)),'unused_cells':columns*rows-count,'preserved_palette_indices':preserve_indices}
