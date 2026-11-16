"""Declared scene geometry. Projection is not evidence of a game's storage."""
import math
from .asset_schema import fields,label,number


def normalize_scene(value,width,height):
    if value is None:
        return {'projection':'orthogonal','tile_width':width,'tile_height':height,'elevation_step':1,
                'object_fields':{'z':None,'layer':None,'order':None}}
    fields(value,'projection tile_width tile_height elevation_step object_fields')
    if value['projection'] not in ('orthogonal','isometric'):raise ValueError('unsupported scene projection')
    for key in ('tile_width','tile_height','elevation_step'):number(value[key],1,256)
    fields(value['object_fields'],'z layer order')
    names=[]
    for name in value['object_fields'].values():
        if name is not None:
            label(name,128)
            if name in ('x','y') or name in names:raise ValueError('scene fields alias coordinates or each other')
            names.append(name)
    return {**value,'object_fields':dict(value['object_fields'])}


def _coordinate(value,maximum=1024**2):
    if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>maximum:
        raise ValueError('scene coordinate exceeds finite bounds')
    return value


def project_point(scene,x,y,z):
    x=_coordinate(x);y=_coordinate(y);z=_coordinate(z,1024)
    width=scene['tile_width'];height=scene['tile_height']
    if scene['projection']=='isometric':px=(x-y)*width/2;py=(x+y)*height/2
    elif scene['projection']=='orthogonal':px=x*width;py=y*height
    else:raise ValueError('unsupported scene projection')
    return px,py-z*scene['elevation_step']


def inverse_at_z(scene,px,py,z):
    px=_coordinate(px);py=_coordinate(py);z=_coordinate(z,1024)
    ground=py+z*scene['elevation_step']
    width=scene['tile_width'];height=scene['tile_height']
    if scene['projection']=='isometric':return px/width+ground/height,ground/height-px/width
    if scene['projection']=='orthogonal':return px/width,ground/height
    raise ValueError('unsupported scene projection')


def validate_scene(scene,rooms,definitions):
    """Validate explicit field bindings and conservative projected raster limits."""
    for room,definition in zip(rooms,definitions):
        declared=definition['objects']
        if declared:
            by_name={f['name']:f for f in declared['fields']}
            for kind,name in scene['object_fields'].items():
                if name is None:continue
                if name not in by_name:raise ValueError('scene object field is not declared')
                if kind=='z' and by_name[name]['maximum']>1024:raise ValueError('declared object height exceeds scene bounds')
        heights=room['elevation']
        if heights and any(z>1024 for z in heights):raise ValueError('terrain elevation exceeds scene bounds')
        points=[]
        for index in range(room['width']*room['height']):
            x=index%room['width'];y=index//room['width'];z=heights[index] if heights else 0
            points.extend(project_point(scene,x+dx,y+dy,z) for dx,dy in ((0,0),(1,0),(1,1),(0,1)))
        for obj in room['objects']:
            if 'x' not in obj or 'y' not in obj:continue
            name=scene['object_fields']['z'];z=obj[name] if name else 0
            points.extend(project_point(scene,obj['x']+dx,obj['y']+dy,z) for dx,dy in ((0,0),(1,0),(1,1),(0,1)))
        width=math.ceil(max(x for x,_ in points)-min(x for x,_ in points))+130
        height=math.ceil(max(y for _,y in points)-min(y for _,y in points))+130
        if width>8192 or height>8192 or width*height>4*1024**2:raise ValueError('projected scene exceeds pixel budget')
