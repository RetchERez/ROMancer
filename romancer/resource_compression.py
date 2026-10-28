"""Bounded LZ10/RLE resources and fixed-allocation recompression.

Original bounded readers/writers for the documented 0x10 and 0x30 byte-stream formats.
The parsers/encoders here are original implementations tested by literal vectors.
"""
from collections import deque
import hashlib
from pathlib import Path
from .asset_schema import number
from .assets import checked_path
from . import workbench_projects as projects

OUTPUT_LIMIT=1024**2
ALLOCATION_LIMIT=48*1024
SIGNATURES={'lz10':0x10,'rle':0x30}


def canonical_codec(codec):
    """Read obsolete generic-codec metadata without restoring console support."""
    if type(codec) is not str:raise ValueError('choose a supported compression codec')
    codec={'gba-lz10':'lz10','gba-rle':'rle'}.get(codec,codec)
    if codec not in (*SIGNATURES,'snes-lz2'):raise ValueError('choose a supported compression codec')
    return codec


def decode_stream(data,codec,max_output=OUTPUT_LIMIT):
    codec=canonical_codec(codec)
    number(max_output,1,OUTPUT_LIMIT)
    if codec=='snes-lz2':
        from .snes_lz2 import decode_lz2
        return decode_lz2(data,max_output)
    if codec not in SIGNATURES or not isinstance(data,(bytes,bytearray,memoryview)):raise ValueError('choose a supported LZ10 or RLE byte stream')
    if not 4<=len(data)<=2*OUTPUT_LIMIT or data[0]!=SIGNATURES[codec]:raise ValueError('compressed stream header is missing or invalid')
    size=int.from_bytes(data[1:4],'little')
    if not 1<=size<=max_output:raise ValueError('decoded size is empty or exceeds the declared output budget')
    output=bytearray();position=4
    def take(count):
        nonlocal position
        if position+count>len(data):raise ValueError('compressed stream is truncated')
        result=data[position:position+count];position+=count;return result
    while len(output)<size:
        flags=take(1)[0]
        if codec=='rle':
            count=(flags&127)+(3 if flags&128 else 1)
            if count>size-len(output):raise ValueError('RLE block overruns the declared decoded size')
            output.extend(bytes([take(1)[0]])*count if flags&128 else take(count))
        else:
            for bit in range(7,-1,-1):
                if len(output)==size:break
                if flags&(1<<bit):
                    first,second=take(2);count=(first>>4)+3;distance=((first&15)<<8|second)+1
                    if distance>len(output) or count>size-len(output):raise ValueError('LZ10 back-reference is outside the decoded stream')
                    for _ in range(count):output.append(output[-distance])
                else:output.extend(take(1))
    return {'data':bytes(output),'consumed':position}


def _encode_lz(data):
    output=bytearray([0x10])+len(data).to_bytes(3,'little');position=0;positions={};history=deque()
    def remember(index):
        while history and history[0][0]<index-4095:
            old,key=history.popleft();bucket=positions.get(key)
            if bucket and bucket[0]==old:bucket.popleft()
            if bucket is not None and not bucket:positions.pop(key,None)
        if index+3>len(data):return
        key=data[index:index+3];bucket=positions.setdefault(key,deque(maxlen=64));bucket.append(index);history.append((index,key))
    while position<len(data):
        flag_position=len(output);output.append(0);flags=0
        for bit in range(7,-1,-1):
            if position>=len(data):break
            best=0;distance=0;maximum=min(18,len(data)-position)
            if maximum>=3:
                for prior in reversed(positions.get(data[position:position+3],())):
                    if position-prior>4096:break
                    length=3
                    while length<maximum and data[prior+length]==data[position+length]:length+=1
                    if length>best:best=length;distance=position-prior
                    if best==maximum:break
            if best>=3:
                flags|=1<<bit;value=((best-3)<<12)|(distance-1);output.extend(value.to_bytes(2,'big'));count=best
            else:output.append(data[position]);count=1
            for index in range(position,position+count):remember(index)
            position+=count
        output[flag_position]=flags
    return bytes(output)


def _encode_rle(data):
    output=bytearray([0x30])+len(data).to_bytes(3,'little');position=0
    def run(offset):
        end=offset+1
        while end<len(data) and end-offset<130 and data[end]==data[offset]:end+=1
        return end-offset
    while position<len(data):
        count=run(position)
        if count>=3:output.extend([(count-3)|128,data[position]]);position+=count
        else:
            start=position;position+=count
            while position<len(data) and position-start<128:
                if run(position)>=3:break
                position+=1
            output.append(position-start-1);output.extend(data[start:position])
    return bytes(output)


def encode_stream(raw,codec):
    codec=canonical_codec(codec)
    if codec=='snes-lz2':
        from .snes_lz2 import encode_lz2
        return encode_lz2(raw)
    if type(raw) is not bytes or not 1<=len(raw)<=OUTPUT_LIMIT or codec not in SIGNATURES:raise ValueError('choose nonempty decoded bytes up to1MiB and a supported codec')
    return (_encode_lz if codec=='lz10' else _encode_rle)(raw)


def compression_candidates(raw,start=0,*,cancelled=lambda:False,budget=None):
    rows=[];attempts=0;decoded_total=0;view=memoryview(raw)
    if budget is not None:budget.update(partial=False,next_offset=None,attempts=0)
    for offset in range((-start)%4,len(raw)-3,4):
        if offset%4096==0 and cancelled():raise KeyboardInterrupt
        if raw[offset] not in (0x10,0x30):continue
        size=int.from_bytes(view[offset+1:offset+4],'little')
        if not 8<=size<=65536:continue
        attempts+=1
        if attempts>128 or decoded_total+size>8*OUTPUT_LIMIT:
            if budget is not None:budget.update(partial=True,next_offset=start+offset,attempts=attempts-1)
            break
        if budget is not None:budget['attempts']=attempts
        codec='lz10' if raw[offset]==0x10 else 'rle'
        try:decoded=decode_stream(view[offset:offset+ALLOCATION_LIMIT],codec,65536)
        except ValueError:continue
        decoded_total+=size
        rows.append({'kind':'compression','offset':start+offset,'length':decoded['consumed'],'format':codec,'decoded_size':size,
                     'confidence':'validated-format','preview':decoded['data'][:32].hex(),
                     'reason':'Stream decodes within limits; confirm actual use and allocated capacity before extracting.'})
    return rows


def inspect_compressed(path,sha,offset,allocation,codec,*,include_data=False,cancelled=lambda:False):
    codec=canonical_codec(codec)
    number(offset,0,64*1024**2);number(allocation,3 if codec=='snes-lz2' else 4,ALLOCATION_LIMIT)
    if cancelled():raise KeyboardInterrupt
    path=checked_path(Path(path));source=projects._measure(path,cancelled=cancelled)
    if source['sha256']!=sha:raise ValueError('compressed parent source revision changed')
    if source['size']>64*1024**2 or offset+allocation>source['size']:raise ValueError('compressed allocation exceeds the supported parent extent')
    with path.open('rb') as stream:stream.seek(offset);raw=stream.read(allocation)
    decoded=decode_stream(raw,codec);projects._measure(path,source,cancelled=cancelled)
    result={'ok':True,'status':'INSPECTED','parent_sha256':sha,'offset':offset,'allocation':allocation,'codec':codec,'consumed':decoded['consumed'],
            'decoded_size':len(decoded['data']),'decoded_sha256':hashlib.sha256(decoded['data']).hexdigest(),
            'stream_sha256':hashlib.sha256(raw[:decoded['consumed']]).hexdigest(),'preview_hex':decoded['data'][:128].hex()}
    if include_data:result['decoded_data']=decoded['data']
    return result


def prepare_reinsert(project,parent_id,decoded_id,edited_id,offset,allocation,codec,*,cancelled=lambda:False):
    codec=canonical_codec(codec)
    project=Path(project);parent=projects.artifact(project,parent_id);decoded=projects.artifact(project,decoded_id);edited=projects.artifact(project,edited_id)
    inspected=inspect_compressed(parent['path'],parent['sha256'],offset,allocation,codec,include_data=True,cancelled=cancelled)
    metadata=decoded.get('compressed_parent')
    if type(metadata) is dict:metadata={**metadata,'codec':canonical_codec(metadata.get('codec'))}
    required={'parent_id':parent_id,'parent_sha256':parent['sha256'],'offset':offset,'allocation':allocation,'codec':codec,
              'decoded_sha256':inspected['decoded_sha256'],'stream_sha256':inspected['stream_sha256'],'consumed':inspected['consumed']}
    if metadata!=required:raise ValueError('reinsert parameters differ from the confirmed extracted allocation')
    projects._measure(decoded['path'],decoded,cancelled=cancelled);projects._measure(edited['path'],edited,cancelled=cancelled)
    if decoded['sha256']!=inspected['decoded_sha256'] or edited['size']!=decoded['size'] or edited['size']>OUTPUT_LIMIT:
        raise ValueError('decoded resource identity or fixed size changed')
    ancestor=edited;seen=set()
    for _ in range(128):
        if ancestor['artifact_id']==decoded_id:break
        if ancestor['artifact_id'] in seen or not ancestor.get('source_id'):raise ValueError('choose a build descended from this decoded resource')
        seen.add(ancestor['artifact_id']);ancestor=projects.artifact(project,ancestor['source_id'])
    else:raise ValueError('decoded resource ancestry exceeds its budget')
    replacement=Path(edited['path']).read_bytes()
    if len(replacement)!=edited['size'] or hashlib.sha256(replacement).hexdigest()!=edited['sha256']:raise ValueError('captured edited bytes differ from the expected resource identity')
    packed=encode_stream(replacement,codec)
    if decode_stream(packed,codec)['data']!=replacement:raise ValueError('recompression round-trip differs from edited resource')
    from .compression_oracle import verify_encoded
    verification=verify_encoded(packed,codec,replacement,cancelled=cancelled)
    projects._measure(parent['path'],parent,cancelled=cancelled);projects._measure(edited['path'],edited,cancelled=cancelled)
    summary={'ok':True,'parent_sha256':parent['sha256'],'edited_sha256':edited['sha256'],'codec':codec,'decoded_size':len(replacement),'original_stored_size':inspected['consumed'],'packed_size':len(packed),'allocation':allocation,
        'fits':len(packed)<=allocation,'free_bytes':max(0,allocation-len(packed)),'overflow_bytes':max(0,len(packed)-allocation),'independent_decode_verified':verification['verified'],'decode_verification':verification}
    return parent,edited,packed,summary


def preview_reinsert(project,parent_id,decoded_id,edited_id,offset,allocation,codec,*,cancelled=lambda:False):
    return prepare_reinsert(project,parent_id,decoded_id,edited_id,offset,allocation,codec,cancelled=cancelled)[3]


def plan_reinsert(project,parent_id,decoded_id,edited_id,offset,allocation,codec,*,cancelled=lambda:False):
    codec=canonical_codec(codec)
    parent,edited,packed,summary=prepare_reinsert(project,parent_id,decoded_id,edited_id,offset,allocation,codec,cancelled=cancelled)
    verification=summary['decode_verification']
    if not summary['fits']:raise ValueError('recompressed data does not fit the confirmed allocation; reduce the edit or use a separately supported relocation')
    with Path(parent['path']).open('rb') as stream:stream.seek(offset);before=stream.read(len(packed))
    edits=[]
    for position in range(0,len(packed),4096):
        old=before[position:position+4096];new=packed[position:position+4096]
        if old!=new:edits.append({'offset':offset+position,'before':old.hex(),'after':new.hex()})
    if not edits:raise ValueError('recompression makes no byte changes')
    if parent.get('system_id') in ('nes', 'snes', 'genesis', 'gb', 'gbc', 'sms'):
        from .system_integrity import integrity_edits
        edits=integrity_edits(parent['path'],parent['sha256'],parent['system_id'],edits)
    projects._measure(parent['path'],parent,cancelled=cancelled);projects._measure(edited['path'],edited,cancelled=cancelled)
    result=projects.plan_byte_edits(project,parent_id,edits)
    return {**result,'codec':codec,'packed_size':len(packed),'decoded_sha256':edited['sha256'],
        'independent_decode_verified':verification['verified'],'decode_verification':verification,'allocation':allocation}
