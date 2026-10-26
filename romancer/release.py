"""BPS1 creation, separate decoder verification, and positive release manifests.

Format: byuu's public-domain BPS specification, archived at
https://floating.muncher.se/byuu/bps/bps_spec.html
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import zipfile
import zlib
from .asset_schema import fields,label
from .assets import checked_path
from .player_docs import default_credits
from .script_schema import canonical_bytes
from .workbench_projects import _measure

MAX_IMAGE=256*1024**2


def _check_cancelled(cancelled):
    if cancelled():raise KeyboardInterrupt('release cancelled before publication')


def _read(path,limit=MAX_IMAGE,*,cancelled=lambda:False):
    path=checked_path(Path(path));measured=_measure(path,cancelled=cancelled)
    if measured['size']>limit:raise ValueError('release input exceeds byte budget')
    raw=bytearray()
    with path.open('rb') as stream:
        while True:
            _check_cancelled(cancelled)
            chunk=stream.read(min(65536,limit+1-len(raw)))
            if not chunk:break
            raw.extend(chunk)
            if len(raw)>limit:raise ValueError('release input exceeds byte budget')
    if hashlib.sha256(raw).hexdigest()!=measured['sha256']:raise ValueError('release input changed')
    return bytes(raw),measured


def publish_bytes(destination,raw,*,cancelled=lambda:False):
    destination=checked_path(Path(destination))
    if destination.exists():raise ValueError('destination already exists; choose a new name')
    fd,name=tempfile.mkstemp(prefix='.export-',dir=destination.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            for offset in range(0,len(raw),65536):
                _check_cancelled(cancelled);stream.write(raw[offset:offset+65536])
            stream.flush();os.fsync(stream.fileno())
        if Path(name).read_bytes()!=raw:raise ValueError('export byte verification failed')
        _check_cancelled(cancelled)
        os.link(name,destination)
    finally:Path(name).unlink(missing_ok=True)
    return {'path':str(destination),'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def _encode_number(value):
    encoded=bytearray()
    while True:
        part=value&127;value>>=7
        if not value:encoded.append(part|128);return encoded
        encoded.append(part);value-=1


def apply_bps(source:bytes,patch:bytes,*,cancelled=lambda:False)->bytes:
    """Independent bounded BPS decoder, including SourceCopy and TargetCopy."""
    if len(source)>MAX_IMAGE or not 19<=len(patch)<=MAX_IMAGE+1024**2 or patch[:4]!=b'BPS1':raise ValueError('invalid BPS header or size')
    source_crc,target_crc,patch_crc=struct.unpack('<III',patch[-12:])
    if zlib.crc32(source)!=source_crc or zlib.crc32(patch[:-4])!=patch_crc:raise ValueError('BPS source or patch checksum mismatch')
    cursor=4;end=len(patch)-12
    def number():
        nonlocal cursor
        value=0;factor=1
        for _ in range(10):
            if cursor>=end:raise ValueError('truncated BPS integer')
            byte=patch[cursor];cursor+=1;value+=(byte&127)*factor
            if byte&128:return value
            factor*=128;value+=factor
        raise ValueError('BPS integer overflow')
    source_size=number();target_size=number();metadata_size=number()
    if source_size!=len(source) or target_size>MAX_IMAGE or metadata_size>1024**2 or cursor+metadata_size>end:raise ValueError('BPS size mismatch')
    metadata=patch[cursor:cursor+metadata_size];cursor+=metadata_size
    # ROMancer metadata strengthens BPS CRC source binding without rejecting other BPS metadata.
    if metadata.startswith(b'{'):
        try:identity=json.loads(metadata)
        except (ValueError,UnicodeError):raise ValueError('invalid BPS metadata') from None
        if identity.get('romancer_bps')==1 and identity.get('source_sha256')!=hashlib.sha256(source).hexdigest():raise ValueError('BPS source SHA-256 mismatch')
    output=bytearray();source_relative=0;target_relative=0;actions=0
    while cursor<end:
        _check_cancelled(cancelled)
        command=number();kind=command&3;length=(command>>2)+1;actions+=1
        if length>target_size-len(output) or actions>1000000:raise ValueError('BPS command exceeds target or action budget')
        if kind==0:
            position=len(output)
            if position+length>len(source):raise ValueError('BPS source read exceeds input')
            output.extend(source[position:position+length])
        elif kind==1:
            if cursor+length>end:raise ValueError('BPS literal is truncated')
            output.extend(patch[cursor:cursor+length]);cursor+=length
        else:
            signed=number();delta=-(signed>>1) if signed&1 else signed>>1
            if kind==2:
                source_relative+=delta
                if source_relative<0 or source_relative+length>len(source):raise ValueError('BPS source copy outside input')
                output.extend(source[source_relative:source_relative+length]);source_relative+=length
            else:
                target_relative+=delta
                if target_relative<0 or target_relative>=len(output):raise ValueError('BPS target copy reads unwritten data')
                # Repeated copies may overlap, by the BPS specification.
                for index in range(length):
                    if index%65536==0:_check_cancelled(cancelled)
                    output.append(output[target_relative]);target_relative+=1
    if cursor!=end or len(output)!=target_size or zlib.crc32(output)!=target_crc:raise ValueError('BPS target checksum or size mismatch')
    return bytes(output)


def prepare_patch(source:Path,target:Path,destination:Path,metadata:dict,*,cancelled=lambda:False)->dict:
    source=checked_path(Path(source));target=checked_path(Path(target));destination=checked_path(Path(destination))
    if max(source.stat().st_size,target.stat().st_size)>MAX_IMAGE:
        from .streaming_bps import create_patch
        return create_patch(source,target,destination,metadata,cancelled=cancelled)
    if source==target or destination in (source,target):raise ValueError('patch source, target and destination must be separate')
    fields(metadata,'title description');label(metadata['title'],256);label(metadata['description'],2048,blank=True)
    a,source_identity=_read(source,cancelled=cancelled);b,target_identity=_read(target,cancelled=cancelled)
    info={'romancer_bps':1,**metadata,'credit':default_credits(),'source_sha256':source_identity['sha256'],'target_sha256':target_identity['sha256']}
    meta=canonical_bytes(info,max_bytes=16384)
    patch=bytearray(b'BPS1')+_encode_number(len(a))+_encode_number(len(b))+_encode_number(len(meta))+meta
    # Linear encoding uses only SourceRead/TargetRead; decoder above is separately implemented.
    position=0;actions=0
    while position<len(b):
        _check_cancelled(cancelled)
        same=position<len(a) and a[position]==b[position];start=position;position+=1
        while position<len(b) and position-start<65536 and (position<len(a) and a[position]==b[position])==same:position+=1
        length=position-start;patch+=_encode_number(((length-1)<<2)|(0 if same else 1));actions+=1
        if not same:patch+=b[start:position]
        if actions>1000000:raise ValueError('patch action budget exceeded')
    patch+=struct.pack('<II',zlib.crc32(a),zlib.crc32(b));patch+=struct.pack('<I',zlib.crc32(patch))
    if apply_bps(a,patch,cancelled=cancelled)!=b:raise ValueError('independent patch application differs from target')
    _measure(source,source_identity,cancelled=cancelled);_measure(target,target_identity,cancelled=cancelled)
    published=publish_bytes(destination,patch,cancelled=cancelled)
    return {'schema_version':1,'operation':'patch-prepare','ok':True,'status':'VERIFIED','format':'BPS1',**published,
            'source_sha256':source_identity['sha256'],'target_sha256':target_identity['sha256'],
            'independent_apply_verified':True,'original_preserved':True,'credit':default_credits()}


def verify_patch(source:Path,patch:Path,expected_target_sha256:str,*,cancelled=lambda:False)->dict:
    from .streaming_bps import apply_patch
    with tempfile.TemporaryDirectory(prefix='.romancer-verify-') as folder:
        result=apply_patch(source,patch,Path(folder)/'reconstructed',cancelled=cancelled)
    if result['target_sha256']!=expected_target_sha256:raise ValueError('independent target SHA-256 mismatch')
    return {'ok':True,'status':'VERIFIED','operation':'patch-verify','source_sha256':result['source_sha256'],
        'patch_sha256':result['patch_sha256'],'target_sha256':result['target_sha256'],'target_size':result['target_size'],'written':False}



def package_release(destination:Path,manifest:dict,*,cancelled=lambda:False)->dict:
    from .streaming_bps import _scan,_recheck,_destination,_space,MAX_PATCH
    fields(manifest,'title files');label(manifest['title'],256)
    destination=_destination(destination,())
    if type(manifest['files']) is not list or not 1<=len(manifest['files'])<=128:raise ValueError('invalid release selection')
    selected=[];names={'manifest.json'};total=0
    for item in manifest['files']:
        _check_cancelled(cancelled);fields(item,'source path role');name=item['path'];role=item['role']
        if (type(name) is not str or len(name)>256 or '\\' in name or ':' in name or name.startswith('/')
                or any(p in ('','.','..') for p in name.split('/')) or name.casefold() in names):raise ValueError('unsafe or duplicate archive path')
        names.add(name.casefold())
        if role not in ('patch','documentation','credits','notice'):raise ValueError('release role is not approved for distribution')
        path=checked_path(Path(item['source']));measured=_scan(path,MAX_PATCH if role=='patch' else 4*1024**2,cancelled=cancelled)
        if path==destination:raise ValueError('release aliases input')
        with path.open('rb') as stream:
            if role=='patch':
                if stream.read(4)!=b'BPS1':raise ValueError('only BPS patches are approved binary release inputs')
            else:
                text=stream.read().decode('utf-8')
                if '\x00' in text:raise ValueError('documentation contains binary bytes')
        total+=measured['size']
        if total>16*1024**3:raise ValueError('release aggregate byte budget exceeded')
        selected.append((item,path,measured))
    public_manifest={'schema_version':1,'title':manifest['title'],'credit':default_credits(),
        'files':[{'path':i['path'],'role':i['role'],**{k:identity[k] for k in ('size','sha256')}} for i,_,identity in selected]}
    _space(destination.parent,total)
    fd,name=tempfile.mkstemp(prefix='.export-',dir=destination.parent);os.close(fd);temporary=Path(name)
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
            for item,path,_ in selected:
                with path.open('rb') as src,archive.open(item['path'],'w',force_zip64=True) as dest:
                    while chunk:=src.read(65536):_check_cancelled(cancelled);dest.write(chunk)
            archive.writestr('MANIFEST.json',canonical_bytes(public_manifest,max_bytes=1024**2))
        with zipfile.ZipFile(temporary) as archive:
            for item,path,identity in selected:
                digest=hashlib.sha256();count=0
                with archive.open(item['path']) as stream:
                    while chunk:=stream.read(65536):_check_cancelled(cancelled);digest.update(chunk);count+=len(chunk)
                if count!=identity['size'] or digest.hexdigest()!=identity['sha256']:raise ValueError('ZIP member identity mismatch')
                _recheck(path,identity,MAX_PATCH if item['role']=='patch' else 4*1024**2,cancelled=cancelled)
        measured=_scan(temporary,16*1024**3+1024**2,cancelled=cancelled);_check_cancelled(cancelled);os.link(temporary,destination)
    finally:temporary.unlink(missing_ok=True)
    return {'ok':True,'status':'PACKAGED','operation':'release-package','path':str(destination),'size':measured['size'],'sha256':measured['sha256'],'manifest':public_manifest}
