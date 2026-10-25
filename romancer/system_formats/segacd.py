"""First-sector Sega CD system IDs; descriptor references are never followed here."""
from . import candidate,region,text

SYNC=b'\x00'+b'\xff'*10+b'\x00'


def candidates(reader):
    size=reader.identity['size']
    if size<14:return []
    h=reader.read_at(0,min(size,2352));result=[]
    for base,format,sector in ((0,'mode1-2048',2048),(16,'mode1-2352',2352)):
        tag=h[base:base+16]
        if not (tag.startswith(b'SEGADISCSYSTEM') or tag.startswith(b'SEGADATADISC')):continue
        valid=size>=sector and size%sector==0
        if base:valid=valid and h[:12]==SYNC and h[15]==1
        warnings=['Sector integrity, filesystem extents, BIOS and native boot are separate checks.']
        if not valid:warnings.append('Unsupported or truncated first-sector layout.')
        result.append(candidate('segacd',format,base,metadata={'system_id':text(tag),'sector_bytes':sector,
            'payload_offset':base,'payload_bytes':2048,'sector_integrity':'NOT_CHECKED'},
            regions=[region('track','disc-track',0,size)] if valid else [],warnings=warnings,valid=valid,confidence='signature'))
    return result
