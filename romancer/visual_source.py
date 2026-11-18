"""Causal visual dependency tests. These do not observe CPU or DMA transfers."""
from .asset_schema import number
from .asset_codecs import decode_cell,encode_cell,cell_size
from .visual_checks import _frame,_crop,_png


def group_candidates(report,start,limit):
    number(start,0,256);number(limit,1,8);groups={};region=report['region']
    for i,m in enumerate(report['matches']):
        key=(m['offset'],m['length'],m['codec']);g=groups.setdefault(key,{'offset':m['offset'],'length':m['length'],'codec':m['codec'],'match_ids':[]});g['match_ids'].append(i)
    def rank(g):
        unit=cell_size(g['codec'],8,8)
        distance=min(abs(report['matches'][i]['x']+4-region['x']-region['width']/2)+abs(report['matches'][i]['y']+report['matches'][i]['height']/2-region['y']-region['height']/2) for i in g['match_ids'])
        return (bool(g['offset']%unit),distance,g['offset'],g['length'])
    ordered=sorted(groups.values(),key=rank)
    return {'groups':ordered[start:start+limit],'start':start,'next':min(len(ordered),start+limit),'total':len(ordered)}


def _pixels(raw,match):
    unit=cell_size(match['codec'],8,8)
    if match['height'] not in (8,16) or match['width']!=8 or len(raw)!=unit*(match['height']//8):raise ValueError('Verification requires a literal 8 by 8 or 8 by 16 source.')
    return sum([decode_cell(raw[i:i+unit],codec=match['codec'],width=8,height=8) for i in range(0,len(raw),unit)],[])


def encoding_lanes(match,source_pixel):
    """Format-derived byte lanes; does not claim individual native bus reads."""
    number(source_pixel,0,8*match['height']-1);codec=match['codec'];unit=cell_size(codec,8,8);tile,local=divmod(source_pixel,64);y,x=divmod(local,8);base=match['offset']+tile*unit
    if codec in ('tile8-packed4-low-v1','tile8-packed4-high-v1'):
        shift=(0 if x%2==0 else 4) if codec=='tile8-packed4-low-v1' else (4 if x%2==0 else 0)
        return [{'offset':base+y*4+x//2,'mask':15<<shift}]
    planes=2 if codec in ('tile8-planar2-msb-v1','tile8-paired2-msb-v1') else 4
    def offset(p):return y+p*8 if codec=='tile8-planar2-msb-v1' else y*4+p if codec=='tile8-rowplanar4-msb-v1' else (p//2)*16+y*2+p%2
    return [{'offset':base+offset(p),'mask':1<<(7-x)} for p in range(planes)]


def _marker(pixels,after,match,name,changed):
    raw=b''.join(encode_cell(after[i:i+64],codec=match['codec'],width=8,height=8) for i in range(0,len(after),64))
    return {'name':name,'before_pixels':pixels,'pixels':after,'after':raw,'changed_indices':sorted(changed)}


def locator_markers(raw,match):
    pixels=_pixels(raw,match);indices=sorted(set(pixels)-{0})
    if len(indices)<2:raise ValueError('At least two opaque source colors are needed for a coded source test.')
    cycle={v:indices[(i+1)%len(indices)] for i,v in enumerate(indices)};result=[]
    for bit in range((len(pixels)+1).bit_length()):
        selected={i for i,v in enumerate(pixels) if v and (i+1)&(1<<bit)}
        result.append(_marker(pixels,[cycle[v] if i in selected else v for i,v in enumerate(pixels)],match,'Source pixel code '+str(bit+1),selected))
    return result


def _region(match,width,height):
    r={'x':match['x'],'y':match['y'],'width':8,'height':match['height']}
    if r['x']<0 or r['y']<0 or r['x']+8>width or r['y']+r['height']>height:raise ValueError('The source selection lies outside the measured frame.')
    return r


def learn_mapping(original,frames,match,locators):
    width,height,rgb=_frame(original);region=_region(match,width,height);pixels=locators[0]['before_pixels']
    if len(frames)!=len(locators) or len(frames)!=(len(pixels)+1).bit_length():raise ValueError('The coded locator frame set is incomplete.')
    cropped=[]
    for frame in frames:
        w,h,raw=_frame(frame)
        if (w,h)!=(width,height):raise ValueError('Coded source replay changed frame dimensions.')
        cropped.append(_crop(raw,width,region))
    before=_crop(rgb,width,region);mapping=[];colors={}
    for screen in range(len(pixels)):
        old=before[screen*3:screen*3+3];code=0;alternate=set()
        for bit,raw in enumerate(cropped):
            color=raw[screen*3:screen*3+3]
            if color!=old:code|=1<<bit;alternate.add(color)
        source=code-1
        if not 0<=source<len(pixels) or not pixels[source] or len(alternate)!=1:continue
        value=pixels[source];colors.setdefault(value,set()).add(old)
        mapping.append({'source_pixel':source,'screen_pixel':screen,'value':value})
    if any(len(values)!=1 for values in colors.values()):raise ValueError('Recovered source color mapping is inconsistent; the pixel origins are unresolved.')
    by_color={v:{m['source_pixel'] for m in mapping if m['value']==v} for v in colors}
    eligible={v for v,ids in by_color.items() if len(ids)>=4};mapping=[m for m in mapping if m['value'] in eligible]
    ids={m['source_pixel'] for m in mapping}
    if len(ids)<16 or len(eligible)<2 or len({i%8 for i in ids})<4 or len({i//8 for i in ids})<4:raise ValueError('Fewer than 16 distinct source pixel origins with independent color controls were recovered. This may be a global color effect or a transformed/partial format.')
    return {'pixel_map':mapping,'source_colors':{str(v):list(next(iter(colors[v]))) for v in eligible},'unique_source_pixels':len(ids),'region':region}


def validation_markers(raw,match,mapping):
    import hashlib
    pixels=_pixels(raw,match);values=sorted(int(v) for v in mapping['source_colors']);cycle={v:values[(i+1)%len(values)] for i,v in enumerate(values)};result=[];previous=set()
    for seed in (0,1):
        selected=set()
        for value in values:
            ids={m['source_pixel'] for m in mapping['pixel_map'] if m['value']==value};ordered=sorted(ids,key=lambda i:hashlib.sha256(('romancer-source-'+str(seed)+'-'+str(i)).encode()).digest());half=set(ordered[:len(ordered)//2])
            if seed and half==previous&ids:half=ids-half
            selected.update(half)
        after=[cycle[v] if i in selected else v for i,v in enumerate(pixels)];result.append(_marker(pixels,after,match,'Independent validation '+str(seed+1),selected));previous=selected
    return result


def assess_mapping(original,frames,match,mapping,markers):
    width,height,rgb=_frame(original);region=_region(match,width,height);a=_crop(rgb,width,region);checks=[];counts=[];outside=[];pictures=[];mapped=mapping['pixel_map'];colors=mapping['source_colors']
    if len(frames)!=2 or len(markers)!=2:raise ValueError('Two independent validation runs are required.')
    for frame,marker in zip(frames,markers):
        w,h,raw=_frame(frame)
        if (w,h)!=(width,height):return {'status':'NOT_VERIFIED','reason':'Validation frame dimensions changed.','source_transfer_observed':False}
        b=_crop(raw,width,region);good=True
        for value in (int(v) for v in colors):
            ids={m['source_pixel'] for m in mapped if m['value']==value};changed=ids&set(marker['changed_indices'])
            if len(changed)<2 or len(ids-changed)<2:good=False
        for item in mapped:
            source=item['source_pixel'];screen=item['screen_pixel'];value=str(marker['pixels'][source])
            if value not in colors:good=False;continue
            expected=bytes(colors[value])
            if b[screen*3:screen*3+3]!=expected:good=False
        checks.append(good);changed=sum(a[i:i+3]!=b[i:i+3] for i in range(0,len(a),3));counts.append(changed);total=sum(rgb[i:i+3]!=raw[i:i+3] for i in range(0,len(rgb),3));outside.append(total-changed)
        pictures.append({'name':marker['name'],'original_png_base64':_png(a,8,region['height']),'marker_png_base64':_png(b,8,region['height']),'difference_png_base64':_png(bytes(abs(x-y) for x,y in zip(a,b)),8,region['height'])})
    verified=all(checks);indices=sorted({m['screen_pixel'] for m in mapped}) if verified else [];source_ids={m['source_pixel'] for m in mapped};opaque=sum(bool(v) for v in markers[0]['before_pixels']);complete=verified and len(source_ids)==opaque
    mask=bytes(c for i in range(len(a)//3) for c in ((35,190,125) if i in indices else (95,50,50)))
    return {'status':'VERIFIED_VISUAL_SOURCE' if verified else 'NOT_VERIFIED','reason':('Coded probes and both independent validations verified '+str(len(source_ids))+' distinct source pixel origins.' if verified else 'Independent validation did not reproduce every recovered pixel and its color controls. No source authority was granted.'),
        'verified_pixels':len(indices),'opaque_pixels':opaque,'verified_pixel_indices':indices,'unique_source_pixels':len(source_ids) if verified else 0,'pixel_map':mapped if verified else [],'source_colors':colors if verified else {},'complete_placement':complete,
        'changed_pixels':counts,'outside_placement_changed_pixels':outside,'marker_checks':checks,'visual':pictures,'mask_png_base64':_png(mask,8,region['height']),'region':region,'source_transfer_observed':False,'proof_method':'coded_romancer_build_replay','scope':'Controlled ROM storage-to-screen pixel provenance for this replay. CPU/VDP/DMA fetches and compressed-format semantics are not observed.'}
