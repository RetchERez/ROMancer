"""Original tiny console programs for ROMancer's measured native checks.

These draw simple patterns/colors; they contain no game or BIOS payloads and no
copied Nintendo logos. Boot checks use cores configured to skip external BIOS.
"""
import struct


def make_boot_fixture(system):
    if system == 'nes':
        data = bytearray(16 + 16384 + 8192)
        data[:6] = b'NES\x1a\x01\x01'
        code = bytes.fromhex('78d8a2ff9ae88e00208e01208e10402c022010fb2c022010fba93f8d0620a9008d0620a200bd8d808d0720e8e020d0f5a9208d0620a9008d0620a004a2008d0720e8d0fa88d0f7a9008d05208d05208d0020a90a8d01202c022010fba9018d1640a9008d1640ad16402901f004a916d002a921aaa93f8d0620a9018d06208a8d0720a9008d05208d05204c57800f2130160f2130160f2130160f2130160f2130160f2130160f2130160f213016')
        data[16:16 + len(code)] = code
        data[16 + 16384 - 6:16 + 16384] = bytes.fromhex('008000800080')
        data[16400:16408] = bytes.fromhex('8142241818244281')
        return {'data': bytes(data), 'suffix': '.nes', 'offset': 16400, 'before': '81', 'after': 'c1', 'graphics_offset': 16400}
    data = bytearray(32768)
    if system == 'snes':
        code = bytes.fromhex('7818fbe230a98f8d00219c00429c2121a200bd00908d2221e8e020d0f5a90f8d002180fe')
        data[:len(code)] = code
        data[4096:4098] = bytes.fromhex('e003')
        data[32704:32725] = b'ROMANCER ORIGINAL BOOT'[:21]
        data[32725] = 32
        data[32727] = 5
        data[32764:32766] = bytes.fromhex('0080')
        data[32732:32736] = bytes.fromhex('ffff0000')
        checksum = sum(data) & 65535
        data[32732:32736] = struct.pack('<HH', checksum ^ 65535, checksum)
        return {'data': bytes(data), 'suffix': '.sfc', 'offset': 4096, 'before': 'e003', 'after': '1f00', 'graphics_offset': 8192, 'palette_offset': 4096}
    if system == 'genesis':
        data[:8] = bytes.fromhex('00ff000000000200')
        data[256:272] = b'SEGA MEGA DRIVE '
        data[336:384] = b'ROMANCER ORIGINAL BOOT'.ljust(48, b' ')
        data[420:424] = (len(data) - 1).to_bytes(4, 'big')
        data[496:499] = b'JUE'
        code = bytearray.fromhex('46fc2700103900a100010200000f670a23fc5345474100a1400033fc010000a1110033fc010000a11200')
        for word in [32772, 33092, 33328, 33596, 33799, 34156, 34560, 35584, 35969, 36610, 36865]:
            code += bytes.fromhex('33fc') + word.to_bytes(2, 'big') + bytes.fromhex('00c00004')
        code += bytes.fromhex('23fcc000000000c0000441f900001000303c000f33d800c0000051c8fff860fe')
        data[512:512 + len(code)] = code
        data[4096:4098] = bytes.fromhex('00e0')
        checksum = sum((int.from_bytes(data[i:i + 2], 'big') for i in range(512, len(data), 2))) & 65535
        data[398:400] = checksum.to_bytes(2, 'big')
        return {'data': bytes(data), 'suffix': '.md', 'offset': 4096, 'before': '00e0', 'after': '000e', 'graphics_offset': 8192, 'palette_offset': 4096}
    if system in ('gb', 'gbc'):
        data[256:260] = bytes.fromhex('c3500100')
        data[308:324] = b'ROMANCER BOOT'.ljust(16, b'\x00')
        code = bytes.fromhex('f3afe0402100801100020110001a22130b78b120f8210098010004af220b78b120f93ee4e0473e91e04018fe')
        if system == 'gbc':
            data[323] = 192
            code = bytes.fromhex('f3afe040e04f2100801100020110001a22130b78b120f8210098010004af220b78b120f93e01e04f210098010004af220b78b120f9afe04f3e80e06821000306082ae0690520fa3e91e04018fe')
            data[768:776] = bytes.fromhex('ff7f1f00e003007c')
        data[336:336 + len(code)] = code
        for row, value in enumerate(bytes.fromhex('8142241818244281')):
            data[512 + row * 2] = value
        data[333] = -sum(data[308:333]) - 25 & 255
        data[334:336] = (sum(data) & 65535).to_bytes(2, 'big')
        result = {'data': bytes(data), 'suffix': '.gbc' if system == 'gbc' else '.gb', 'offset': 512, 'before': '81', 'after': 'c1', 'graphics_offset': 512}
        if system == 'gbc':
            result['palette_offset'] = 768
        return result
    if system == 'sms':
        # Original Mode 4 drawing fixture: one patterned tile and explicit CRAM.
        data[:3] = bytes.fromhex('c30001')
        code = bytearray.fromhex('f331f0df')
        for register, value in ((0,4),(1,0),(2,14),(5,126),(6,0),(7,0),(8,0),(9,0),(10,255)):
            code += bytes((0x3e,value,0xd3,0xbf,0x3e,0x80|register,0xd3,0xbf))
        code += bytes.fromhex('afd3bf3ec0d3bf21000206207ed3be2310fa')
        code += bytes.fromhex('afd3bf3e40d3bf21200206207ed3be2310fa')
        code += bytes.fromhex('afd3bf3e78d3bf010007afd3be0b78b120f8')
        code += bytes.fromhex('afd3bf3e7fd3bf3ed0d3be3e40d3bf3e81d3bf18fe')
        data[0x100:0x100+len(code)] = code
        data[0x200:0x220] = bytes([0,12,3,63]+[0]*28)
        for y in range(8):data[0x220+y*4] = 0xaa if y%2 else 0x55
        data[0x7ff0:0x7ff8] = b'TMR SEGA'
        data[0x7fff] = 0x4c
        from .system_formats.sms import checksum
        data[0x7ffa:0x7ffc] = checksum(data,0x7ff0,len(data)).to_bytes(2,'little')
        return {'data':bytes(data),'suffix':'.sms','offset':0x201,'before':'0c','after':'30','graphics_offset':0x220,'palette_offset':0x200}
    raise ValueError('choose NES, SNES, Genesis, Game Boy, Game Boy Color or Master System')
