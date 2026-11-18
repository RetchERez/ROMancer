"""System-codec graphics candidates, independent of game names and reference ROMs.

Pixel agreement is evidence of a possible literal encoding, not proof that the
game fetched those bytes. No result from this module authorizes a write.
"""
from collections import defaultdict
import hashlib
import math
from .asset_codecs import decode_cell,cell_size

VERSION=1
SYSTEM_CODECS={'sms': 'tile8-rowplanar4-msb-v1', 'nes': 'tile8-planar2-msb-v1', 'snes': 'tile8-paired4-msb-v1', 'genesis': 'tile8-packed4-high-v1', 'gb': 'tile8-paired2-msb-v1', 'gbc': 'tile8-paired2-msb-v1'}
MAX_SOURCE_BYTES=512*1024
MAX_WINDOWS=8192
MAX_BUCKET=16
MAX_MATCHES=256


def _integer(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('graphics analysis value outside bounds')
    return value


def _flip_mask(mask,height,fx,fy):
    if not fx and not fy:return mask
    result=0
    while mask:
        bit=mask&-mask;pos=bit.bit_length()-1;mask-=bit
        x,y=pos%8,pos//8
        result|=1<<((height-1-y if fy else y)*8+(7-x if fx else x))
    return result


def _frame_index(rgb,width,height,region,part_height,cancelled):
    positions=max(0,region['width']-7)*max(0,region['height']-part_height+1)
    stride=max(1,math.ceil(positions/MAX_WINDOWS));index=defaultdict(list);truncated=False;sampled=0
    for ordinal in range(0,positions,stride):
        if ordinal%128==0 and cancelled():raise KeyboardInterrupt
        x=region['x']+ordinal%max(1,region['width']-7)
        y=region['y']+ordinal//max(1,region['width']-7)
        colors={}
        for yy in range(part_height):
            at=((y+yy)*width+x)*3
            for xx in range(8):
                color=rgb[at+xx*3:at+xx*3+3]
                colors[color]=colors.get(color,0)|(1<<(yy*8+xx))
        sampled+=1
        # Reject flat screens. Sparse/one-color pieces remain unresolved.
        if len(colors)<2:continue
        for mask in colors.values():
            if not 8<=mask.bit_count()<=8*part_height-8:continue
            for fx,fy in ((False,False),(True,False),(False,True),(True,True)):
                bucket=index[_flip_mask(mask,part_height,fx,fy)]
                if len(bucket)<MAX_BUCKET:bucket.append((x,y,fx,fy))
                else:truncated=True
    return index,{'possible_positions':positions,'sampled_positions':sampled,'position_stride':stride,'mask_buckets_truncated':truncated}


def _palette_match(pixels,rgb,width,x,y,part_height,fx,fy):
    colors={};visible=0
    for i,value in enumerate(pixels):
        if value==0:continue  # Transparent index is a hypothesis, never a ROM palette claim.
        xx,yy=i%8,i//8;at=((y+(part_height-1-yy if fy else yy))*width+x+(7-xx if fx else xx))*3
        color=rgb[at:at+3]
        if value in colors and colors[value]!=color:return None
        colors[value]=color;visible+=1
    if visible<16 or len(colors)<2 or len(set(colors.values()))!=len(colors):return None
    return {str(k):list(v) for k,v in colors.items()},visible


def match_graphics(raw,rgb,width,height,system,*,region=None,start=0,length=None,cancelled=lambda:False):
    """Find bounded literal candidates at every byte alignment in a source range."""
    if cancelled():raise KeyboardInterrupt
    if system not in SYSTEM_CODECS:raise ValueError('no literal tile codec configured for this system')
    _integer(width,8,1024);_integer(height,8,1024)
    if type(rgb) is not bytes or len(rgb)!=width*height*3:raise ValueError('captured RGB dimensions differ')
    if type(raw) is not bytes or not raw or len(raw)>64*1024**2:raise ValueError('source bytes exceed graphics budget')
    _integer(start,0,len(raw)-1)
    requested=len(raw)-start if length is None else _integer(length,1,len(raw)-start)
    length=min(requested,MAX_SOURCE_BYTES);end=start+length
    region={'x':0,'y':0,'width':width,'height':height} if region is None else region
    if type(region) is not dict or set(region)!={'x','y','width','height'}:raise ValueError('invalid frame region')
    for key in region:_integer(region[key],0 if key in ('x','y') else 8,1024)
    if region['x']+region['width']>width or region['y']+region['height']>height:raise ValueError('region exceeds captured frame')
    codec=SYSTEM_CODECS[system];unit=cell_size(codec,8,8);matches=[];seen=set();frame_coverage=[];source_coverage=[];limited=False;passes=[]
    for part_height in ((16,8) if system=='nes' else (8,)):
        if region['height']<part_height:continue
        index,coverage=_frame_index(rgb,width,height,region,part_height,cancelled);frame_coverage.append({'part_height':part_height,**coverage})
        block=unit*(part_height//8)
        segment={'part_height':part_height,'block_bytes':block,'offset':start,'end':start,'requested_end':start+requested}
        source_coverage.append(segment);passes.append((part_height,block,index,segment))
    last_offset=start
    # Advance all part-size passes together so continuation cannot skip an
    # unvisited 8x8 pass when a preceding 8x16 pass reaches the result budget.
    for offset in range(start,max(start,end-unit+1)):
        if offset%256==0 and cancelled():raise KeyboardInterrupt
        last_offset=offset
        for part_height,block,index,segment in passes:
            if offset+block>end:continue
            segment['end']=offset+block;data=raw[offset:offset+block]
            if len(set(data))<2:continue
            pixels=decode_cell(data[:unit],codec=codec,width=8,height=8)
            if part_height==16:pixels+=decode_cell(data[unit:],codec=codec,width=8,height=8)
            masks={}
            for i,value in enumerate(pixels):
                if value:masks[value]=masks.get(value,0)|(1<<i)
            if len(masks)<2:continue
            buckets=[index[mask] for mask in masks.values() if 8<=mask.bit_count()<=8*part_height-8 and mask in index]
            if not buckets:continue
            for x,y,fx,fy in sorted(set(min(buckets,key=len))):
                key=(offset,x,y,part_height,fx,fy)
                if key in seen:continue
                result=_palette_match(pixels,rgb,width,x,y,part_height,fx,fy)
                if result is None:continue
                colors,visible=result;seen.add(key)
                matches.append({'offset':offset,'length':block,'x':x,'y':y,'width':8,'height':part_height,
                                'flip_x':fx,'flip_y':fy,'observed_colors':colors,'visible_pixels':visible,
                                'confidence':'literal_pixel_candidate','codec':codec})
                if len(matches)>=MAX_MATCHES:limited=True;break
            if limited:break
        if limited:break
    whole_range=not limited and length==requested
    return {'ok':True,'status':'CANDIDATES' if matches else 'NO_LITERAL_MATCH','matcher_version':VERSION,
            'system_id':system,'codec':codec,'matches':sorted(matches,key=lambda m:(m['y'],m['x'],m['offset'])),
            'coverage':{'offset':start,'bytes_requested':requested,'bytes_loaded':length,'bytes_scanned':max((r['end']-start for r in source_coverage),default=0),'offset_alignment':1,
                        'next_offset':min(end,max(start+1,last_offset)) if limited else (max(start+1,end-max(r['block_bytes'] for r in source_coverage)+1) if end<len(raw) else end),
                        'whole_requested_range':whole_range,'whole_source':whole_range and start==0 and end==len(raw),
                        'source_ranges':source_coverage,'frame_positions':frame_coverage,'match_limit':MAX_MATCHES,'matches_truncated':limited},
            'unique_source':False,'write_authorized':False,'provenance_verified':False,
            'limits':['Index 0 is treated as transparent; captured colors are observations, not ROM palette addresses.',
                      'Pixel agreement does not prove a source transfer, object membership, or complete sprite layout.',
                      'Compressed, transformed, occluded and RAM-generated graphics may have no literal match.',
                      'Limited searches and repeated patterns cannot establish a unique source.']}


def index_graphics(path,system,size,*,cancelled=lambda:False):
    """Import-time storage index. Byte-identical cells are not semantic references."""
    if system not in SYSTEM_CODECS:return {'status':'CODEC_UNRESOLVED','banks':[]}
    codec=SYSTEM_CODECS[system];unit=cell_size(codec,8,8);base=16 if system=='nes' else 0
    count=max(0,(size-base)//unit);stride=max(1,math.ceil(count/65536));patterns={};banks={};sampled=0
    with open(path,'rb') as stream:
        for cell in range(0,count,stride):
            if sampled%256==0 and cancelled():raise KeyboardInterrupt
            offset=base+cell*unit;stream.seek(offset);data=stream.read(unit)
            if len(data)!=unit:raise ValueError('source changed during graphics indexing')
            sampled+=1
            if len(set(data))<3:continue
            bank=offset//16384;entry=banks.setdefault(bank,{'offset':bank*16384,'length':min(16384,size-bank*16384),'sampled_nonflat_cells':0})
            entry['sampled_nonflat_cells']+=1
            key=hashlib.blake2s(data,digest_size=16).digest();record=patterns.setdefault(key,{'count':0,'offsets':[]})
            record['count']+=1
            if len(record['offsets'])<8:record['offsets'].append(offset)
    repeated=sorted((v for v in patterns.values() if v['count']>1),key=lambda r:-r['count'])[:32]
    return {'status':'STORAGE_CANDIDATES','codec':codec,'sampled_cells':sampled,'cell_sampling_stride':stride,
            'alignment_assumption':base%unit,'bank_size':16384,
            'banks':sorted(banks.values(),key=lambda r:-r['sampled_nonflat_cells'])[:64],
            'repeated_patterns':repeated,'write_authorized':False,
            'runtime_status':'WAITING_FOR_GAMEPLAY','note':'Storage groups and byte-identical patterns only. Gameplay capture is needed to investigate visible placements.'}


def candidate_layout(report,selected):
    """Convert explicitly chosen candidates to an editing view, never choose an offset."""
    matches=report['matches'];system=report['system_id'];codec=SYSTEM_CODECS.get(system)
    if type(selected) is not list or not 1<=len(selected)<=64 or len(set(selected))!=len(selected):raise ValueError('choose distinct candidate parts')
    if any(type(i) is not int or not 0<=i<len(matches) for i in selected):raise ValueError('invalid candidate selection')
    parts=[matches[i] for i in selected];unit=cell_size(codec,8,8)
    if any(p['codec']!=codec or p['width']!=8 or p['height'] not in (8,16) for p in parts):raise ValueError('candidate codecs differ')
    base=min(p['offset'] for p in parts);end=max(p['offset']+p['length'] for p in parts)
    count=(end-base)//unit
    if not 1<=count<=1024 or any((p['offset']-base)%unit for p in parts) or (end-base)%unit:raise ValueError('candidate source ranges need separate tile collections')
    left=min(p['x'] for p in parts);top=min(p['y'] for p in parts)
    width=max(p['x']+p['width'] for p in parts)-left;height=max(p['y']+p['height'] for p in parts)-top
    if width%8 or height%8 or not 1<=width//8<=8 or not 1<=height//8<=8 or any((p['x']-left)%8 or (p['y']-top)%8 for p in parts):raise ValueError('placements need a shared grid of up to 8 by 8 tiles')
    columns,rows=width//8,height//8;indices=[None]*(columns*rows);flips=[0]*len(indices);colors=[None]*len(indices)
    for p in parts:
        for stored in range(p['height']//8):
            display=p['height']//8-1-stored if p['flip_y'] else stored
            pos=((p['y']-top)//8+display)*columns+(p['x']-left)//8
            if indices[pos] is not None:raise ValueError('candidate parts overlap; choose one source for each placement')
            indices[pos]=(p['offset']-base)//unit+stored
            flips[pos]=(1 if p['flip_x'] else 0)|(2 if p['flip_y'] else 0);colors[pos]=p['observed_colors']
    return {'config':{'system_id':system,'offset':base,'count':count,'codec':codec,'width':8,'height':8,
                      'palette_offset':None,'palette_banks':1,'palette_format':'rgb555-le'},
            'layout':{'first':0,'columns':columns,'rows':rows,'order':'rows','indices':indices,'flips':flips,'colors':colors,'provenance':'pixel_candidate'}}
