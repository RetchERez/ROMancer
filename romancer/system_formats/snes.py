"""Explicit SNES header candidates; a self-consistent header remains heuristic."""
from . import candidate,region,text


def candidates(reader):
    size=reader.identity['size'];result=[]
    for prefix in (0,512):
        body=size-prefix
        if body<=0 or body%32768:continue
        for name,offset,modes in (('lorom',0x7fc0,(0x20,0x30)),('hirom',0xffc0,(0x21,0x31)),('exhirom-candidate',0x40ffc0,(0x25,0x35))):
            position=prefix+offset
            if position+64>size:continue
            h=reader.read_at(position,64)
            if h[21] not in modes or not all(32<=c<127 or c==0 for c in h[:21]) or not any(32<c<127 for c in h[:21]):continue
            pair=(int.from_bytes(h[28:30],'little')^int.from_bytes(h[30:32],'little'))==65535
            declared=(1<<(h[23]+10)) if h[23]<=15 else None
            valid=pair and declared is not None and declared<=body
            warnings=['Mapping is heuristic; no CPU/bank mapping or whole-image checksum is established.']
            if not valid:warnings.append('SNES header checksum pair or declared ROM size is inconsistent.')
            if name=='exhirom-candidate':warnings.append('ExHiROM addressing is not implemented by this foundation.')
            meta={'title':text(h[:21]),'map_mode':h[21],'copier_header_bytes':prefix,'declared_rom_bytes':declared,
                'checksum_pair_valid':pair,'whole_image_checksum':'NOT_CHECKED','address_mapping':'NOT_INFERRED'}
            regions=[region('rom','program',prefix,body),region('header','header',position,64)] if valid else []
            if prefix and valid:regions.insert(0,region('copier-header','prefix',0,512))
            result.append(candidate('snes',name,position,metadata=meta,regions=regions,warnings=warnings,valid=valid,confidence='heuristic'))
    return result
