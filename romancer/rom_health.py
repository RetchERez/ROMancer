"""Read-only cartridge checks. References and limits: docs/rom-health.md.

CRC32 covers the whole file unless an explicit payload scope is selected.
Console additive/header checksums are independent of CRC32 and runtime behavior.
"""
from pathlib import Path
import re
import zlib
from .system_identify import identify_system
from .system_reader import SystemReader

MAX_CARTRIDGE=64*1024**2


def check_rom(path,expected_sha256,expected_crc32='',crc_scope='file',*,cancelled=lambda:False):
    if type(expected_crc32) is not str or (expected_crc32 and not re.fullmatch('[0-9a-fA-F]{8}',expected_crc32)):
        raise ValueError('Expected CRC32 must contain exactly eight hexadecimal digits, or be empty.')
    if crc_scope not in ('file','payload'):raise ValueError('Choose whole file or cartridge payload CRC32.')
    path=Path(path)
    if path.stat().st_size>MAX_CARTRIDGE:raise ValueError('ROM health checks support cartridge files up to 64 MiB.')
    assessment=identify_system(path,expected_sha256=expected_sha256,cancelled=cancelled)
    with SystemReader(path,expected_sha256=expected_sha256,cancelled=cancelled) as reader:
        if reader.identity['size']>MAX_CARTRIDGE:raise ValueError('ROM health budget exceeded.')
        raw=bytearray();reader.stream.seek(0)
        while len(raw)<reader.identity['size']:
            reader._cancel();chunk=reader.stream.read(min(65536,reader.identity['size']-len(raw)))
            if not chunk:raise ValueError('ROM was truncated during checking.')
            raw.extend(chunk)
            if reader.stream.tell()!=len(raw):raise ValueError('ROM read did not advance consistently.')
        # A second identity pass prevents publishing results for a changing file.
        identity=dict(reader.identity)
    full_crc=f'{zlib.crc32(raw):08X}';checks=[]
    def add(name,status,detail,stored=None,computed=None):
        item={'name':name,'status':status,'detail':detail}
        if stored is not None:item['stored']=stored
        if computed is not None:item['computed']=computed
        checks.append(item)
    found=assessment['candidates'];valid=[c for c in found if c['layout_valid']]
    selected=valid[0] if len(valid)==1 else found[0] if len(found)==1 else None
    system=selected['system_id'] if selected else None
    layout=assessment['status']=='IDENTIFIED'
    add('Cartridge layout','PASS' if layout else 'FAIL' if found and not valid else 'NOT_CHECKED',
        'Recognized header and declared regions are consistent.' if layout else assessment.get('error') or 'No unique supported cartridge layout was recognized.')
    payload=[{'offset':0,'length':len(raw)}] if layout else []
    if system=='nes' and layout:
        payload=[{'offset':r['offset'],'length':r['length']} for r in selected['regions'] if r['id'] in ('prg-rom','chr-rom')]
        add('Internal cartridge checksum','NOT_CHECKED','iNES/NES 2.0 has no standard stored whole-ROM checksum. Use a reference CRC32.')
    elif system in ('gb','gbc') and len(raw)>=0x150:
        expected=(-sum(raw[0x134:0x14d])-25)&255;stored=raw[0x14d]
        add('Game Boy header checksum','PASS' if expected==stored else 'FAIL','Header bytes 0134–014C.',f'{stored:02X}',f'{expected:02X}')
        expected=(sum(raw)-raw[0x14e]-raw[0x14f])&65535;stored=int.from_bytes(raw[0x14e:0x150],'big')
        add('Game Boy global checksum','PASS' if expected==stored else 'FAIL','Whole cartridge excluding 014E–014F.',f'{stored:04X}',f'{expected:04X}')
    elif system=='gba' and len(raw)>=0xc0:
        expected=(-sum(raw[0xa0:0xbd])-0x19)&255;stored=raw[0xbd]
        add('GBA header complement','PASS' if expected==stored else 'FAIL','Header bytes 00A0–00BC; this does not cover game data.',f'{stored:02X}',f'{expected:02X}')
    elif system=='genesis' and len(raw)>=512:
        if len(raw)%2:add('Genesis ROM checksum','NOT_CHECKED','Odd-sized images need an explicitly supported padding convention.')
        else:
            expected=sum((raw[i]<<8)|raw[i+1] for i in range(0x200,len(raw),2))&65535;stored=int.from_bytes(raw[0x18e:0x190],'big')
            add('Genesis ROM checksum','PASS' if expected==stored else 'FAIL','Big-endian 16-bit words from 0200 through end of file.',f'{stored:04X}',f'{expected:04X}')
    elif system=='sms' and layout:
        from .system_formats.sms import checksum
        header=selected['header_offset'];stored=int.from_bytes(raw[header+10:header+12],'little');expected=checksum(raw,header,selected['metadata']['checksum_length'])
        add('Master System ROM checksum','PASS' if expected==stored else 'FAIL','Declared Sega checksum extent excluding the sixteen-byte header; mapper and game behavior remain separate.',f'{stored:04X}',f'{expected:04X}')
    elif system=='snes':
        prefix=selected['metadata'].get('copier_header_bytes',0);body=len(raw)-prefix
        if layout:payload=[{'offset':prefix,'length':body}]
        h=selected['header_offset']
        if not layout or selected['format'] not in ('lorom','hirom') or not 32768<=body<=4*1024**2 or body%32768 or raw[h+22] not in (0,1,2):
            add('SNES ROM checksum','NOT_CHECKED','Standard checksum checks cover ordinary LoROM/HiROM up to 4 MiB. Enhancement chips, extended maps and unresolved layouts require separate evidence.')
        else:
            from .cartridge_integrity import snes_mirrored_checksum
            stored=int.from_bytes(raw[h+30:h+32],'little');expected=snes_mirrored_checksum(bytes(raw[prefix:]))
            add('SNES ROM checksum','PASS' if expected==stored else 'FAIL','Standard recursive tail mirroring; excludes an identified 512-byte copier header. This is not a game-revision match.',f'{stored:04X}',f'{expected:04X}')
    if layout and len(valid)==1:
        from .cartridge_startup import inspect_startup
        from .cartridge_integrity import check_boot_logo,check_gba_fixed_header
        if cancelled():raise KeyboardInterrupt('ROM verification cancelled')
        if system in ('gb','gbc','gba'):
            checks.append(check_boot_logo(raw,system))
            if system=='gba':checks.append(check_gba_fixed_header(raw))
        checks.extend(inspect_startup(raw,selected))
        for check in checks:
            if 'locations' not in check and type(check.get('offset')) is int:
                at=check['offset'];length=check.get('length',1)
                if type(length) is int and 0<=at<=len(raw)-length:
                    check['locations']=[{'offset':at,'length':length,'label':'View header bytes'}]
    if crc_scope=='payload' and not payload:raise ValueError('Payload CRC32 requires a unique supported cartridge layout. Use whole file instead.')
    ranges=[{'offset':0,'length':len(raw)}] if crc_scope=='file' else payload
    crc=0
    for region in ranges:crc=zlib.crc32(raw[region['offset']:region['offset']+region['length']],crc)
    measured=f'{crc:08X}';reference=expected_crc32.upper()
    comparison={'status':'NOT_CHECKED' if not reference else 'PASS' if measured==reference else 'FAIL',
                'expected':reference or None,'measured':measured,'scope':crc_scope,'ranges':ranges}
    issues=any(c['status']=='FAIL' for c in checks) or comparison['status']=='FAIL'
    warnings=any(c['status']=='WARN' for c in checks)
    return {'ok':True,'status':'ISSUES_FOUND' if issues else 'WARNINGS_FOUND' if warnings else 'CHECKED','source':identity,'system_id':system,
            'system_status':assessment['status'],'crc32':full_crc,'crc_comparison':comparison,'payload_ranges':payload,
            'checks':checks,'warnings':assessment['warnings'],
            'limits':['No trusted game database is bundled. A matching supplied CRC32 is not an authenticity guarantee.',
                      'Header and startup checks cover their explicitly supported encodings and mappings only.',
                      'A matching header logo does not identify a game revision or certify native boot.'],
            'runtime_verified':False,'write_authorized':False}
