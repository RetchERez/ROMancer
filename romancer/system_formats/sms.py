"""Bounded Sega header layouts, not mapper or game-resource identification.
Reference: https://www.smspower.org/Development/ROMHeader
Checksum ranges: https://www.smspower.org/Development/BIOSes
Only SMS region codes3/4 and conservative documented power-of-two sizes.
"""
from . import candidate,region
SIZES={0xa:8192,0xb:16384,0xc:32768,0xe:65536,0xf:131072,0:262144,1:524288}

def candidates(reader):
    size=reader.identity['size'];found=[]
    for offset in (0x1ff0,0x3ff0,0x7ff0):
        if offset+16>size:continue
        header=reader.read_at(offset,16)
        if header[:8]!=b'TMR SEGA':continue
        area=header[15]>>4;declared=SIZES.get(header[15]&15);valid=area in (3,4) and declared is not None and offset+16<=declared<=size<=4*1024*1024
        warnings=['A Sega header does not identify mapper state, game resources or native compatibility.']
        if not valid:warnings.append('Unsupported SMS region/size or a truncated declared ROM; Game Gear is separate.')
        found.append(candidate('sms','sms-sega',offset,metadata={'region_code':area,'declared_rom_bytes':declared,'checksum_length':declared,'checksum_header':int.from_bytes(header[10:12],'little')},regions=[region('rom','program',0,size),region('header','header',offset,16)] if valid else [],warnings=warnings,valid=valid))
    return found

def checksum(raw,header_offset,length):
    if not 0<=header_offset<header_offset+16<=length<=len(raw):raise ValueError('invalid SMS checksum range')
    return (sum(raw[:header_offset])+sum(raw[header_offset+16:length]))&65535
