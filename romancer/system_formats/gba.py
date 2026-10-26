"""GBA fixed-byte/header complement inspection without copied logo data."""
from . import candidate,region,text


def candidates(reader):
    size=reader.identity['size']
    if size<0xb3 or reader.read_at(0xb2,1)!=b'\x96':return []
    if size<0xc0:return [candidate('gba','gba-linear',0,metadata={},valid=False,warnings=['Truncated GBA header.'])]
    h=reader.read_at(0,0xc0);expected=(-sum(h[0xa0:0xbd])-0x19)&255
    printable=all(32<=c<127 or c==0 for c in h[0xa0:0xb2]);capacity=size<=32*1024**2;valid=expected==h[0xbd] and printable and capacity
    return [candidate('gba','gba-linear',0,metadata={'title':text(h[0xa0:0xac]),'game_code':text(h[0xac:0xb0]),
        'header_complement':h[0xbd],'expected_complement':expected,'header_complement_valid':expected==h[0xbd],
        'logo_validation':'NOT_CHECKED'},regions=[region('rom','program',0,size),region('header','header',0,192)] if valid else [],
        warnings=['Logo validation and native boot are not established.']+([] if expected==h[0xbd] and printable else ['GBA header complement or text fields are inconsistent.'])+([] if capacity else ['The supported GBA linear cartridge layout is limited to 32 MiB.']),valid=valid)]
