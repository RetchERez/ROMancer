"""Bounded BPS1 file writer and independent full-standard streaming decoder.

Format reference: https://floating.muncher.se/byuu/bps/bps_spec.html
Publication follows complete reconstruction, CRC and SHA checks; no replacement.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile
import uuid
import zlib
from .assets import checked_path

CHUNK=65536
MAX_IMAGE=8*1024**3
MAX_PATCH=MAX_IMAGE+17*1024**2


def _cancel(cancelled):
    if cancelled():raise KeyboardInterrupt('patch operation cancelled')


def _identity(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)


def _scan(path,limit=MAX_IMAGE,*,cancelled=lambda:False,crc_limit=None):
    path=checked_path(Path(path));before=path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<=before.st_size<=limit:raise ValueError('patch input must be a bounded ordinary unlinked file')
    digest=hashlib.sha256();crc=0;prefix_crc=0;count=0
    with path.open('rb',buffering=0) as stream:
        if _identity(os.fstat(stream.fileno()))!=_identity(before):raise ValueError('input changed before open')
        while True:
            _cancel(cancelled);raw=stream.read(CHUNK)
            if not raw:break
            if count+len(raw)>limit:raise ValueError('patch input budget exceeded')
            digest.update(raw);crc=zlib.crc32(raw,crc)
            if crc_limit is not None and count<crc_limit:prefix_crc=zlib.crc32(raw[:min(len(raw),crc_limit-count)],prefix_crc)
            count+=len(raw)
        if _identity(os.fstat(stream.fileno()))!=_identity(before):raise ValueError('input changed while reading')
    if count!=before.st_size or _identity(path.stat())!=_identity(before):raise ValueError('input changed after reading')
    return {'size':count,'sha256':digest.hexdigest(),'crc32':crc,'prefix_crc32':prefix_crc,'identity':_identity(before)}


def _recheck(path,expected,limit=MAX_IMAGE,*,cancelled=lambda:False):
    actual=_scan(path,limit,cancelled=cancelled)
    if any(actual[k]!=expected[k] for k in ('size','sha256','identity')):raise ValueError('patch input revision changed')


def _destination(path,inputs):
    path=checked_path(Path(path))
    if path.exists() or path in inputs:raise ValueError('destination already exists or aliases an input')
    if not path.parent.is_dir():raise ValueError('destination directory must exist')
    return path


def _space(directory,size):
    if shutil.disk_usage(directory).free<size+16*1024**2:raise ValueError('insufficient free disk for staged verification')


def _number(value):
    out=bytearray()
    while True:
        byte=value&127;value>>=7
        if not value:out.append(byte|128);return bytes(out)
        out.append(byte);value-=1


def apply_patch(source,patch,destination,*,cancelled=lambda:False):
    source=checked_path(Path(source));patch=checked_path(Path(patch));destination=_destination(destination,(source,patch))
    original=_scan(source,cancelled=cancelled);encoded=_scan(patch,MAX_PATCH,cancelled=cancelled,crc_limit=max(0,patch.stat().st_size-4))
    if encoded['size']<19:raise ValueError('truncated BPS patch')
    temporary=None
    try:
        with patch.open('rb',buffering=0) as commands,source.open('rb',buffering=0) as src:
            if commands.read(4)!=b'BPS1':raise ValueError('invalid BPS header')
            end=encoded['size']-12;commands.seek(end);source_crc,target_crc,patch_crc=struct.unpack('<III',commands.read(12));commands.seek(4)
            if source_crc!=original['crc32'] or patch_crc!=encoded['prefix_crc32']:raise ValueError('BPS source or patch checksum mismatch')
            def integer():
                value=0;shift=1
                for _ in range(10):
                    if commands.tell()>=end:raise ValueError('truncated BPS integer')
                    raw=commands.read(1)
                    if len(raw)!=1:raise ValueError('truncated BPS integer')
                    byte=raw[0];value+=(byte&127)*shift
                    if value>0xffffffffffffffff:raise ValueError('BPS integer overflow')
                    if byte&128:return value
                    shift<<=7;value+=shift
                raise ValueError('BPS integer overflow')
            source_size=integer();target_size=integer();meta_size=integer()
            if source_size!=original['size'] or target_size>MAX_IMAGE or meta_size>1024**2 or commands.tell()+meta_size>end:raise ValueError('BPS image or metadata size mismatch')
            metadata=commands.read(meta_size);declared={}
            if metadata.startswith(b'{'):
                try:declared=json.loads(metadata)
                except (ValueError,UnicodeError):raise ValueError('invalid BPS metadata') from None
                if type(declared) is not dict:raise ValueError('invalid BPS metadata object')
                if declared.get('romancer_bps')==1 and declared.get('source_sha256')!=original['sha256']:raise ValueError('BPS source SHA-256 mismatch')
            _space(destination.parent,target_size)
            fd,name=tempfile.mkstemp(prefix='.bps-apply-',dir=destination.parent);temporary=Path(name)
            with os.fdopen(fd,'w+b',buffering=0) as output:
                position=0;relative_source=relative_target=actions=0
                while commands.tell()<end:
                    _cancel(cancelled);command=integer();kind=command&3;length=(command>>2)+1;actions+=1
                    if actions>1000000 or length>target_size-position:raise ValueError('BPS command exceeds target/action budget')
                    if kind==0:
                        start=position
                        if start+length>source_size:raise ValueError('BPS source read exceeds input')
                        src.seek(start)
                    elif kind==1:
                        if commands.tell()+length>end:raise ValueError('truncated BPS literal')
                    else:
                        signed=integer();delta=-(signed>>1) if signed&1 else signed>>1
                        if kind==2:
                            relative_source+=delta
                            if relative_source<0 or relative_source+length>source_size:raise ValueError('BPS source copy exceeds input')
                            src.seek(relative_source);relative_source+=length
                        else:
                            relative_target+=delta
                            if not 0<=relative_target<position:raise ValueError('BPS target copy reads unwritten data')
                    left=length
                    while left:
                        _cancel(cancelled);amount=min(CHUNK,left)
                        if kind in (0,2):raw=src.read(amount)
                        elif kind==1:raw=commands.read(amount)
                        else:
                            distance=position-relative_target;output.seek(relative_target);seed=output.read(min(amount,distance))
                            if not seed:raise ValueError('BPS target copy unavailable')
                            raw=(seed*((amount+len(seed)-1)//len(seed)))[:amount];relative_target+=amount
                        if len(raw)!=amount:raise ValueError('BPS source/literal truncated')
                        output.seek(position);output.write(raw);position+=amount;left-=amount
                if commands.tell()!=end or position!=target_size:raise ValueError('BPS target length mismatch')
                output.flush();os.fsync(output.fileno())
        rebuilt=_scan(temporary,cancelled=cancelled)
        if rebuilt['crc32']!=target_crc:raise ValueError('BPS target checksum mismatch')
        if declared.get('romancer_bps')==1 and declared.get('target_sha256')!=rebuilt['sha256']:raise ValueError('BPS target SHA-256 mismatch')
        _recheck(source,original,cancelled=cancelled);_recheck(patch,encoded,MAX_PATCH,cancelled=cancelled);_cancel(cancelled)
        os.link(temporary,destination)
        return {'ok':True,'status':'VERIFIED','path':str(destination),'source_sha256':original['sha256'],'patch_sha256':encoded['sha256'],'target_sha256':rebuilt['sha256'],'target_size':rebuilt['size'],'independent_apply_verified':True}
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def create_patch(source,target,destination,metadata=None,*,cancelled=lambda:False):
    source=checked_path(Path(source));target=checked_path(Path(target));destination=_destination(destination,(source,target))
    if source==target:raise ValueError('source and target must be separate')
    metadata={} if metadata is None else metadata
    if type(metadata) is not dict or set(metadata)-{'title','description'}:raise ValueError('invalid patch metadata fields')
    from .asset_schema import label
    label(metadata.get('title','ROMancer patch'),256);label(metadata.get('description',''),2048,blank=True)
    original=_scan(source,cancelled=cancelled);changed=_scan(target,cancelled=cancelled);_space(destination.parent,changed['size']*2)
    info={'romancer_bps':1,**metadata,'credit':'By RetchEWretched','source_sha256':original['sha256'],'target_sha256':changed['sha256']}
    meta=json.dumps(info,ensure_ascii=True,separators=(',',':'),sort_keys=True).encode('utf-8')
    temporary=verify=None
    try:
        fd,name=tempfile.mkstemp(prefix='.bps-create-',dir=destination.parent);temporary=Path(name)
        with os.fdopen(fd,'wb',buffering=0) as output,source.open('rb',buffering=0) as a,target.open('rb',buffering=0) as b:
            crc=0;actions=0
            def write(raw):
                nonlocal crc
                output.write(raw);crc=zlib.crc32(raw,crc)
            write(b'BPS1'+_number(original['size'])+_number(changed['size'])+_number(len(meta))+meta)
            same_run=0
            while True:
                _cancel(cancelled);right=b.read(CHUNK)
                if not right:break
                left=a.read(len(right))
                if left==right:same_run+=len(right);continue
                if same_run:write(_number((same_run-1)<<2));same_run=0;actions+=1
                write(_number(((len(right)-1)<<2)|1));write(right);actions+=1
                if actions>1000000:raise ValueError('patch action budget exceeded')
            if same_run:write(_number((same_run-1)<<2))
            write(struct.pack('<II',original['crc32'],changed['crc32']));output.write(struct.pack('<I',crc));output.flush();os.fsync(output.fileno())
        verify=destination.parent/('.bps-verification-'+uuid.uuid4().hex)
        rebuilt=apply_patch(source,temporary,verify,cancelled=cancelled)
        if rebuilt['target_sha256']!=changed['sha256'] or rebuilt['target_size']!=changed['size']:raise ValueError('independent complete reconstruction differs from target')
        _recheck(source,original,cancelled=cancelled);_recheck(target,changed,cancelled=cancelled)
        encoded=_scan(temporary,MAX_PATCH,cancelled=cancelled);_cancel(cancelled);os.link(temporary,destination)
        return {'schema_version':1,'operation':'patch-prepare','ok':True,'status':'VERIFIED','format':'BPS1','path':str(destination),
            'size':encoded['size'],'sha256':encoded['sha256'],'source_sha256':original['sha256'],'target_sha256':changed['sha256'],
            'independent_apply_verified':True,'original_preserved':True,'credit':'By RetchEWretched'}
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
        if verify is not None:verify.unlink(missing_ok=True)
