"""Game Boy cartridge headers. Pan Docs, The_Cartridge_Header.

No copied logo data. Header recognition does not establish mapper behavior or boot.
"""
from . import candidate,region,text


def candidates(reader):
    size=reader.identity['size']
    if size<0x150:return []
    h=reader.read_at(0x100,0x50);title=h[0x34:0x43] if h[0x43]&0x80 else h[0x34:0x44]
    printable=bool(title.rstrip(b'\x00 ')) and all(c==0 or 32<=c<127 for c in title)
    expected=(-sum(h[0x34:0x4d])-25)&255
    entry=h[0]==0xc3 or (h[0]==0 and h[1]==0xc3)
    if not printable or not (entry or expected==h[0x4d]):return []
    code=h[0x48];declared=(32768<<code) if code<=8 else {0x52:72*16384,0x53:80*16384,0x54:96*16384}.get(code)
    valid=declared==size and expected==h[0x4d]
    flag=h[0x43];mode='cgb-only' if flag==0xc0 else 'dmg-cgb' if flag==0x80 else 'dmg'
    metadata={'title':text(title),'color_mode':mode,'color_flag':flag,'cartridge_type':h[0x47],
        'rom_size_code':code,'rom_bytes':declared,'rom_banks':declared//16384 if declared else None,
        'ram_size_code':h[0x49],'header_checksum':h[0x4d],'expected_header_checksum':expected,
        'header_checksum_valid':expected==h[0x4d],'global_checksum':int.from_bytes(h[0x4e:0x50],'big'),
        'global_checksum_validation':'NOT_CHECKED','logo_validation':'NOT_CHECKED'}
    warnings=['Logo, whole-cartridge checksum, mapper behavior and native boot require separate checks.']
    if not valid:warnings.append('Game Boy declared ROM size or header checksum is inconsistent.')
    return [candidate('gb','gb-cartridge',0x100,metadata=metadata,valid=valid,warnings=warnings,
        regions=[region('rom','program',0,size),region('header','header',0x100,0x50)] if valid else [])]
