"""Lossless adapter for explicitly declared fixed-capacity level storage.

This covers the supplied definition, not an entire commercial game's inventory.
Reserved and uninterpreted bytes remain opaque and are preserved unchanged.
"""
import copy,hashlib
from .base import Resource,validate_resources,resource_impact,implementation_sha
from ..asset_codecs import cell_size,encode_cell
from ..level_design import inspect_level,plan_level
from ..level_palette import entry_size,encode_palette
from ..script_schema import canonical_bytes

IMPLEMENTATION_FILES=('romancer/adapters/base.py','romancer/adapters/levels.py',
 'romancer/adapters/registry.py','romancer/level_design.py','romancer/level_semantics.py',
 'romancer/scene_schema.py','romancer/asset_codecs.py','romancer/studio_runtime.py','romancer/level_palette.py')


class DeclaredLevelAdapter:
    adapter_id='declared-level-v1'

    def __init__(self,raw,definition,source_sha256):
        self._doc=inspect_level(raw,definition,source_sha256)
        self._raw=raw;self.source_sha256=source_sha256
        self.adapter_sha256=implementation_sha(IMPLEMENTATION_FILES)
        self._resources=self._make_resources()

    def _make_resources(self):
        ranges=self._doc['ranges'];identity=lambda name:hashlib.sha256(canonical_bytes({'source':self.source_sha256,'document':self._doc['document_id'],'resource':name},max_bytes=1024)).hexdigest()
        resources=[]
        for entry in ranges:
            name=entry['name'];kind=name.split(' ')[-1];dependencies=[]
            if name=='metatiles':dependencies=['tiles']
            elif name=='tiles':dependencies=['palette']
            elif kind=='terrain':
                dependencies=['metatiles']
                room=next(r for r in self._doc['rooms'] if name==r['id']+' terrain')
                if room['elevation'] is not None:dependencies.append(room['id']+' elevation')
            elif kind=='objects':
                room=next(r for r in self._doc['rooms'] if name==r['id']+' objects')
                if any(m.get('sprite') for m in room['object_metadata']):dependencies.append('tiles')
                for connection in self._doc['connections']:
                    if connection['room_id']==room['id']:dependencies.append(connection['target_room_id']+' terrain')
            resources.append(Resource(identity(name),kind,self.source_sha256,entry['offset'],entry['length'],tuple(sorted({identity(n) for n in dependencies}))))
        return validate_resources(resources,len(self._raw),self.source_sha256)

    def inventory(self):
        return {'adapter_id':self.adapter_id,'adapter_sha256':self.adapter_sha256,
                'source_sha256':self.source_sha256,'document_id':self._doc['document_id'],
                'resources':copy.deepcopy(self._resources),'game_revision_complete':False,
                'unresolved':[{'kind':'outside_declared_definitions','reason':'Only explicitly declared level storage is decoded; other game resources and runtime meanings are not certified.'}]}

    def _encode(self):
        doc=self._doc;d=doc['definition'];out=bytearray(self._raw);t=d['tiles'];unit=cell_size(t['codec'],8,8)
        for index,pixels in enumerate(doc['tiles']):
            start=t['offset']+index*unit
            out[start:start+unit]=encode_cell(pixels,codec=t['codec'],width=8,height=8)
        at=t['palette_offset'];size=entry_size(t['palette_format'])*len(doc['palette'])
        out[at:at+size]=encode_palette(doc['palette'],t['palette_format'],self._raw[at:at+size])
        def grid(storage,values):
            width=storage['entry_bytes'];start=storage['offset']
            for index,value in enumerate(values):out[start+index*width:start+(index+1)*width]=value.to_bytes(width,storage['endian'])
        grid(d['metatiles'],[v for parts in doc['metatiles'] for v in parts])
        for room,storage in zip(doc['rooms'],d['rooms']):
            for key in ('terrain','collision','elevation'):
                if storage.get(key) is not None:grid(storage[key],room[key])
            objects=storage['objects']
            if objects:
                for index,record in enumerate(room['objects']):
                    for field in objects['fields']:
                        at=objects['offset']+index*objects['stride']+field['offset'];width=field['bytes']
                        out[at:at+width]=record[field['name']].to_bytes(width,field['endian'])
        return bytes(out)

    def roundtrip(self):
        encoded=self._encode();same=encoded==self._raw
        if not same:raise ValueError('declared level adapter failed its lossless no-op roundtrip')
        return {'byte_identical':same,'source_sha256':self.source_sha256,'encoded_sha256':hashlib.sha256(encoded).hexdigest(),
                'declared_ranges_checked':len(self._resources),'reserved_bytes_preserved':True,
                'game_revision_complete':False,'native_verified':False}

    def inspect(self):
        return {**copy.deepcopy(self._doc),'adapter':{**self.inventory(),'roundtrip':self.roundtrip()}}

    def plan(self,document_id,changes):
        self.roundtrip()
        result=plan_level(self._raw,self._doc['definition'],document_id,changes,self.source_sha256)
        return {**result,'adapter_id':self.adapter_id,'adapter_sha256':self.adapter_sha256,
                'resource_impact':resource_impact(self._resources,result['edits'])}
