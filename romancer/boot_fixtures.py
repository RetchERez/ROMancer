"""Original tiny console programs for ROMancer's measured native checks.

These draw simple patterns/colors; they contain no game or BIOS payloads and no
copied Nintendo logos. Boot checks use cores configured to skip external BIOS.
"""
import struct


def make_boot_fixture(system):
    if system=='nes':
        data=bytearray(16+16384+8192);data[:6]=b'NES\x1a\x01\x01'
        code=bytes.fromhex('78d8a2ff9ae88e00208e01208e10402c022010fb2c022010fba93f8d0620a9008d0620a200bd8d808d0720e8e020d0f5a9208d0620a9008d0620a004a2008d0720e8d0fa88d0f7a9008d05208d05208d0020a90a8d01202c022010fba9018d1640a9008d1640ad16402901f004a916d002a921aaa93f8d0620a9018d06208a8d0720a9008d05208d05204c57800f2130160f2130160f2130160f2130160f2130160f2130160f2130160f213016')
        data[16:16+len(code)]=code;data[16+16384-6:16+16384]=bytes.fromhex('008000800080')
        data[16400:16408]=bytes.fromhex('8142241818244281')
        return {'data':bytes(data),'suffix':'.nes','offset':16400,'before':'81','after':'c1','graphics_offset':16400}
    data=bytearray(32768)
    if system=='snes':
        code=bytes.fromhex('7818fbe230a98f8d00219c00429c2121a200bd00908d2221e8e020d0f5a90f8d002180fe')
        data[:len(code)]=code;data[0x1000:0x1002]=bytes.fromhex('e003')
        data[0x7fc0:0x7fd5]=b'ROMANCER ORIGINAL BOOT'[:21];data[0x7fd5]=0x20;data[0x7fd7]=5
        data[0x7ffc:0x7ffe]=bytes.fromhex('0080');data[0x7fdc:0x7fe0]=bytes.fromhex('ffff0000')
        checksum=sum(data)&65535;data[0x7fdc:0x7fe0]=struct.pack('<HH',checksum^65535,checksum)
        return {'data':bytes(data),'suffix':'.sfc','offset':0x1000,'before':'e003','after':'1f00','graphics_offset':0x2000,'palette_offset':0x1000}
    if system=='genesis':
        data[:8]=bytes.fromhex('00ff000000000200');data[0x100:0x110]=b'SEGA MEGA DRIVE '
        data[0x150:0x180]=b'ROMANCER ORIGINAL BOOT'.ljust(48,b' ');data[0x1a4:0x1a8]=(len(data)-1).to_bytes(4,'big');data[0x1f0:0x1f3]=b'JUE'
        # Original hardware without TMSS does not decode A14000. Check the
        # hardware version before unlocking; the same image then boots on both.
        code=bytearray.fromhex('46fc2700103900a100010200000f670a23fc5345474100a1400033fc010000a1110033fc010000a11200')
        for word in [0x8004,0x8144,0x8230,0x833c,0x8407,0x856c,0x8700,0x8b00,0x8c81,0x8f02,0x9001]:code+=bytes.fromhex('33fc')+word.to_bytes(2,'big')+bytes.fromhex('00c00004')
        code+=bytes.fromhex('23fcc000000000c0000441f900001000303c000f33d800c0000051c8fff860fe')
        data[0x200:0x200+len(code)]=code;data[0x1000:0x1002]=bytes.fromhex('00e0')
        checksum=sum(int.from_bytes(data[i:i+2],'big') for i in range(0x200,len(data),2))&65535;data[0x18e:0x190]=checksum.to_bytes(2,'big')
        return {'data':bytes(data),'suffix':'.md','offset':0x1000,'before':'00e0','after':'000e','graphics_offset':0x2000,'palette_offset':0x1000}
    if system=='gb':
        data[0x100:0x104]=bytes.fromhex('c3500100');data[0x134:0x144]=b'ROMANCER BOOT'.ljust(16,b'\0')
        # DI; LCD off; copy a tile; clear BG map; DMG palette; LCD on; idle.
        code=bytes.fromhex('f3afe0402100801100020110001a22130b78b120f8210098010004af220b78b120f93ee4e0473e91e04018fe')
        data[0x150:0x150+len(code)]=code
        for row,value in enumerate(bytes.fromhex('8142241818244281')):data[0x200+row*2]=value
        data[0x14d]=(-sum(data[0x134:0x14d])-25)&255;data[0x14e:0x150]=(sum(data)&65535).to_bytes(2,'big')
        return {'data':bytes(data),'suffix':'.gb','offset':0x200,'before':'81','after':'c1','graphics_offset':0x200}
    if system=='gba':
        data[:4]=struct.pack('<I',0xea00002e);data[0xa0:0xac]=b'ROMANCERBOOT';data[0xac:0xb0]=b'R60A';data[0xb0:0xb2]=b'00';data[0xb2]=0x96
        words=[0xe3a00301,0,0xe1c010b0,0xe3a00406,0,0xe1d110b0,0xe3a02c96,0xe0c010b2,0xe2522001,0x1afffffc,0xeafffffe]
        for slot,value in [(1,0x403),(4,0x08000200)]:
            pool=len(words)*4;words[slot]=0xe59f1000|(pool-(slot*4+8));words.append(value)
        code=struct.pack('<'+'I'*len(words),*words);data[0xc0:0xc0+len(code)]=code;data[0x200:0x202]=bytes.fromhex('e003')
        data[0xbd]=(-sum(data[0xa0:0xbd])-0x19)&255
        return {'data':bytes(data),'suffix':'.gba','offset':0x200,'before':'e003','after':'1f00','graphics_offset':0x1000,'palette_offset':0x200}
    raise ValueError('choose NES, SNES, Genesis, Game Boy or GBA')
