"""Linear Genesis cartridge header inspection."""
from . import candidate,region,text


def candidates(reader):
    size=reader.identity['size']
    if size<0x104:return []
    identifier=reader.read_at(0x100,min(16,size-0x100))
    if not identifier.lstrip(b' ').startswith(b'SEGA'):return []
    if size<512:return [candidate('genesis','genesis-linear',0x100,metadata={},valid=False,warnings=['Truncated Genesis cartridge header.'])]
    h=reader.read_at(0x100,256);start=int.from_bytes(h[0xa0:0xa4],'big');end=int.from_bytes(h[0xa4:0xa8],'big')
    valid=start==0 and 511<=end<size;warnings=['ROM window and checksum are not runtime or mapper-state proof.']
    if not valid:warnings.append('Declared linear ROM extent is invalid or unsupported.')
    return [candidate('genesis','genesis-linear',0x100,metadata={'console':text(h[:16]),'title':text(h[0x50:0x80]),
        'rom_start':start,'rom_end':end,'checksum_header':int.from_bytes(h[0x8e:0x90],'big'),'whole_image_checksum':'NOT_CHECKED'},
        regions=[region('rom','program',0,size),region('header','header',0x100,256)] if valid else [],warnings=warnings,valid=valid)]
