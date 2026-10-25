"""Explicit cartridge checksum obligations for supported linear layouts.

SNES power-of-two images: SNESdev ROM_header#Checksum (Nintendo manual).
Genesis linear ROM checksum: big-endian words from0x200 through end.
GBA header complement: bytes0xA0..0xBC plus0x19 and complement byte.
"""
from pathlib import Path
from .system_identify import identify_system
from .workbench_projects import _measure


def _validate_result(raw,system_id):
    from .system_formats import nes,snes,genesis,gb,gba,segacd
    class Reader:
        identity={'size':len(raw)}
        def read_at(self,offset,length):
            if offset<0 or length<1 or offset+length>len(raw):raise ValueError('edited header exceeds cartridge')
            return bytes(raw[offset:offset+length])
    reader=Reader();valid=[c for parser in (nes,snes,genesis,gb,gba,segacd) for c in parser.candidates(reader) if c['layout_valid']]
    if len(valid)!=1 or valid[0]['system_id']!=system_id:raise ValueError('edited cartridge has an invalid or ambiguous system layout')


def integrity_edits(path,expected_sha256,system_id,edits):
    path=Path(path);assessment=identify_system(path,expected_sha256=expected_sha256)
    if assessment['status']!='IDENTIFIED' or assessment['system_id']!=system_id:raise ValueError('a unique current system layout is required')
    if path.stat().st_size>64*1024**2:raise ValueError('cartridge integrity budget is64MiB')
    raw=bytearray(path.read_bytes());_measure(path,{'sha256':expected_sha256,'size':len(raw)})
    protected={'nes':[(0,16)],'gb':[(0x143,0x14d)],'gbc':[(0x143,0x14d)],'genesis':[(0x100,0x110),(0x1a0,0x1a8)],'gba':[(0xb2,0xb3)]}.get(system_id,[])
    if system_id=='snes':
        header=next(c for c in assessment['candidates'] if c['layout_valid'])['header_offset'];protected=[(header+21,header+28)]
    for edit in edits:
        offset=edit['offset'];before=bytes.fromhex(edit['before']);after=bytes.fromhex(edit['after'])
        if type(offset) is not int or offset<0 or len(before)!=len(after) or not before or offset+len(before)>len(raw):raise ValueError('invalid fixed edit')
        if raw[offset:offset+len(before)]!=before:raise ValueError('old-byte precondition failed')
        if any(offset<end and offset+len(after)>start for start,end in protected):raise ValueError('structural header fields require a separately supported layout transform')
        raw[offset:offset+len(after)]=after
    if system_id=='nes':_validate_result(raw,system_id);return edits
    if system_id=='snes':
        candidate=assessment['candidates'][0];prefix=candidate['metadata']['copier_header_bytes'];body=len(raw)-prefix
        if candidate['format'] not in ('lorom','hirom') or body&(body-1):raise ValueError('checksum repair requires a supported power-of-two LoROM/HiROM image')
        start=candidate['header_offset']+28;length=4
        raw[start:start+4]=b'\xff\xff\x00\x00';checksum=sum(raw[prefix:])&65535
        replacement=(checksum^65535).to_bytes(2,'little')+checksum.to_bytes(2,'little')
    elif system_id=='genesis':
        if len(raw)%2:raise ValueError('checksum repair requires an even-sized linear cartridge')
        start=0x18e;length=2;replacement=(sum(int.from_bytes(raw[i:i+2],'big') for i in range(0x200,len(raw),2))&65535).to_bytes(2,'big')
    elif system_id in ('gb','gbc'):
        start=0x14d;length=3
        raw[start]=(-sum(raw[0x134:0x14d])-25)&255
        raw[0x14e:0x150]=b'\0\0'
        replacement=bytes([raw[start]])+(sum(raw)&65535).to_bytes(2,'big')
    elif system_id=='gba':start=0xbd;length=1;replacement=bytes([(-sum(raw[0xa0:0xbd])-0x19)&255])
    else:raise ValueError('use the disc payload build service for this system')
    if any(e['offset']<start+length and e['offset']+len(bytes.fromhex(e['after']))>start for e in edits):raise ValueError('checksum fields are maintained automatically; remove overlapping edit')
    raw[start:start+length]=replacement;_validate_result(raw,system_id)
    with path.open('rb') as stream:stream.seek(start);before=stream.read(length)
    return edits+([{'offset':start,'before':before.hex(),'after':replacement.hex()}] if before!=replacement else [])
