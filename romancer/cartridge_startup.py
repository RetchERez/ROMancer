"""Original, read-only startup encoding and conservative address checks.

The caller supplies the unique layout-valid candidate from system_identify.
These checks do not execute instructions, validate logo assets, observe mapper
state, or establish native boot. Unsupported mappings remain unresolved.
"""


_NES = 'https://www.nesdev.org/wiki/CPU_memory_map'
_SNES = 'https://snes.nesdev.org/wiki/CPU_vectors'
_GEN = 'https://www.plutiedev.com/memory-map'
_GB = 'https://gbdev.io/pandocs/The_Cartridge_Header.html#0100-0103--entry-point'
_GBA = 'https://problemkaputt.de/gbatek.htm#gbacartridgeheader'


def _item(name, status, detail, locations=(), *, cpu_address=None, value=None, reference=None):
    result = {'name': name, 'status': status, 'detail': detail,
              'locations': list(locations)}
    if cpu_address is not None:
        result['cpu_address'] = cpu_address
    if value is not None:
        result['value'] = value
    if reference:
        result['reference'] = reference
    return result


def _location(offset, length, label):
    return {'offset': offset, 'length': length, 'label': label}


def _integer(value):
    return type(value) is int


def _region(candidate, identifier, size):
    regions = candidate.get('regions', [])
    if not isinstance(regions, (list, tuple)):
        return None
    selected = [r for r in regions if isinstance(r, dict) and r.get('id') == identifier]
    if len(selected) != 1:
        return None
    region = selected[0]
    start, length = region.get('offset'), region.get('length')
    if not _integer(start) or not _integer(length) or not 0 <= start < start+length <= size:
        return None
    return start, length


def _nes(raw, candidate, metadata):
    mapper = metadata.get('mapper')
    region = _region(candidate, 'prg-rom', len(raw))
    if mapper not in (0, 2) or type(mapper) is not int or candidate.get('format') not in ('ines', 'nes2'):
        return [_item('NES startup vectors', 'NOT_CHECKED',
            'Only mapper 0 (NROM) and the fixed upper bank of mapper 2 are supported; no vector file location is assumed.', reference=_NES)]
    if candidate.get('format') == 'nes2' and metadata.get('submapper', 0) not in ((0,) if mapper == 0 else (0, 1, 2)):
        return [_item('NES startup vectors', 'NOT_CHECKED',
            'This NES 2.0 submapper has no supported startup mapping; standard fixed-bank behavior is not inherited.', reference=_NES)]
    if region is None:
        return [_item('NES startup vectors', 'NOT_CHECKED',
            'A complete, bounded PRG-ROM region is required; CHR/trailing bytes are not substitutes.', reference=_NES)]
    start, size = region
    expected_start = 16+(512 if metadata.get('trainer_present') is True else 0)
    if (start != expected_start or size % 16384 or
            (mapper == 0 and size not in (16384, 32768)) or
            (mapper == 2 and size < 32768)):
        return [_item('NES startup vectors', 'NOT_CHECKED',
            'PRG size or container prefix falls outside the supported standard NROM/UxROM layouts.', reference=_NES)]
    checks = []
    for name, vector, delta in (('reset', 0xfffc, -4), ('NMI', 0xfffa, -6), ('IRQ', 0xfffe, -2)):
        position = start+size+delta
        value = int.from_bytes(raw[position:position+2], 'little')
        locations = [_location(position, 2, f'{name} vector word')]
        if value < 0x8000:
            status, detail = 'WARN', 'Vector targets outside the supported cartridge ROM window; runtime initialization and other devices are not checked.'
        elif mapper == 2 and value < 0xc000:
            status, detail = 'NOT_CHECKED', 'Vector targets the switched lower PRG window; its selected bank is not observed.'
        else:
            if mapper == 0:
                target = start+(value-0x8000) % size
            else:
                target = start+size-16384+(value-0xc000)
            locations.append(_location(target, 1, 'Vector target byte'))
            status, detail = 'PASS', 'Little-endian vector and target lie within the supported static PRG mapping. Target instructions, interrupt use and boot behavior are not executed or verified.'
        checks.append(_item(f'NES {name} vector', status, detail, locations,
                            cpu_address=value, value=value, reference=_NES))
    return checks


def _snes(raw, candidate, metadata):
    name = 'SNES reset vector'
    format = candidate.get('format')
    prefix, header = metadata.get('copier_header_bytes', 0), candidate.get('header_offset')
    if format not in ('lorom', 'hirom'):
        return [_item(name, 'NOT_CHECKED', 'Reset mapping is implemented only for ordinary LoROM/HiROM; special maps remain unresolved.', reference=_SNES)]
    if (not _integer(prefix) or prefix not in (0, 512) or not _integer(header) or
            header != prefix+(0x7fc0 if format == 'lorom' else 0xffc0) or
            header+64 > len(raw)):
        return [_item(name, 'NOT_CHECKED', 'The expected complete internal header/vector and supported copier prefix are unavailable.', reference=_SNES)]
    if raw[header+21] not in ((0x20, 0x30) if format == 'lorom' else (0x21, 0x31)) or raw[header+22] > 2:
        return [_item(name, 'NOT_CHECKED', 'Header mapping/chip fields require a separate cartridge-specific mapping; no reset target is inferred.', reference=_SNES)]
    position = header+0x3c
    value = int.from_bytes(raw[position:position+2], 'little')
    locations = [_location(position, 2, 'Emulation-mode reset vector word')]
    if value < 0x8000:
        return [_item(name, 'WARN', 'Bank-00 reset target is below the supported upper ROM window. RAM, I/O and board behavior are not resolved.',
                      locations, cpu_address=value, value=value, reference=_SNES)]
    target = prefix+(value-0x8000 if format == 'lorom' else value)
    if target >= len(raw):
        return [_item(name, 'WARN', 'Target under the stated standard map exceeds the available image; alternate mirrors/boards are not resolved.',
                      locations, cpu_address=value, value=value, reference=_SNES)]
    locations.append(_location(target, 1, 'Reset target byte'))
    return [_item(name, 'PASS', 'The little-endian bank-00 reset vector resolves inside the image under the stated ordinary map. Header recognition is not board-state or boot verification.',
                  locations, cpu_address=value, value=value, reference=_SNES)]


def _genesis(raw, candidate, metadata):
    if candidate.get('format') != 'genesis-linear' or len(raw) < 8:
        return [_item('Genesis startup vectors', 'NOT_CHECKED', 'A complete linear big-endian vector pair is required; interleaved or truncated containers remain unresolved.', reference=_GEN)]
    checks = []
    stack, pc = int.from_bytes(raw[:4], 'big'), int.from_bytes(raw[4:8], 'big')
    physical_stack, physical_pc = stack & 0xffffff, pc & 0xffffff
    plausible = 0xe00000 <= physical_stack <= 0xffffff and stack % 2 == 0
    checks.append(_item('Genesis initial stack pointer', 'PASS' if plausible else 'WARN',
        ('Initial SSP is even and lies in the standard work-RAM decode, including its 64 KiB mirrors. This checks plausibility, not stack initialization or usage.' if plausible else
         'Initial SSP is odd or outside the standard work-RAM decode. Startup code could replace it; this is a plausibility warning, not a boot verdict.')+
        ' The physical bus uses the low 24 address bits.',
        [_location(0, 4, 'Initial supervisor stack-pointer longword')],
        cpu_address=physical_stack, value=stack, reference=_GEN))
    locations = [_location(4, 4, 'Reset PC longword')]
    if pc & 1:
        status, detail = 'FAIL', 'Reset PC is odd: base 68000 instruction fetch requires even alignment. No instructions have been executed.'
    else:
        start, end = metadata.get('rom_start'), metadata.get('rom_end')
        if (type(start) is int and start == 0 and type(end) is int and
                511 <= end < len(raw) and physical_pc < 0x400000 and physical_pc+2 <= end+1):
            locations.append(_location(physical_pc, 2, 'Reset target instruction word'))
            status, detail = 'PASS', 'Even reset PC lies in the declared linear cartridge extent under the ordinary direct map. Instruction validity and native boot are not checked.'
        else:
            status, detail = 'WARN', 'Reset PC cannot be resolved inside the declared linear image and ordinary cartridge window. Small-ROM mirrors, RAM targets and special mappings remain unresolved; this does not prove corruption.'
    checks.append(_item('Genesis reset vector', status, detail+' Physical mapping uses the low 24 address bits.',
                        locations, cpu_address=physical_pc, value=pc, reference=_GEN))
    return checks


def _gb(raw, candidate, metadata):
    name = 'Game Boy entry branch'
    if candidate.get('format') not in ('gb-cartridge', 'gbc-cartridge') or len(raw) < 0x104:
        return [_item(name, 'NOT_CHECKED', 'A complete cartridge entry area is required.', reference=_GB)]
    position = 0x101 if raw[0x100] == 0 else 0x100
    opcode = raw[position]
    if opcode == 0xc3:
        target, width, encoding = int.from_bytes(raw[position+1:position+3], 'little'), 3, 'JP a16'
    elif opcode == 0x18:
        displacement = raw[position+1]
        if displacement & 0x80:
            displacement -= 256
        target, width, encoding = (position+2+displacement) & 0xffff, 2, 'JR r8'
    else:
        return [_item(name, 'NOT_CHECKED', 'Entry does not use the supported optional NOP followed by unconditional JP/JR. Other valid startup code is not decoded.',
                      [_location(0x100, 4, 'Cartridge entry area')], reference=_GB)]
    locations = [_location(0x100, position-0x100+width, 'Entry branch encoding')]
    loop = 0x100 <= target < position+width
    branch = _item(name, 'WARN' if loop else 'PASS',
        f'Decoded {encoding}'+(' after NOP' if position == 0x101 else '')+
        ('. Target re-enters this entry encoding; this may loop or enter an operand. No execution is performed.' if loop else
         '. This checks only its encoding and destination arithmetic; no instructions are followed.'),
        locations, cpu_address=target, value=target, reference=_GB)
    cart_type = metadata.get('cartridge_type')
    fixed_lower = (0x00, 0x08, 0x09, 0x05, 0x06, 0x0f, 0x10, 0x11,
                   0x12, 0x13, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e)
    target_locations = []
    if target >= 0x4000:
        status, detail = 'NOT_CHECKED', 'Entry target is outside the fixed lower ROM window; mapper state or a non-ROM execution target requires separate evidence.'
    elif type(cart_type) is not int or cart_type not in fixed_lower:
        status, detail = 'NOT_CHECKED', 'Lower-bank identity is not inferred for MBC1 or an unsupported controller. Entry decoding does not observe mapper mode or reset state.'
    elif target >= len(raw):
        status, detail = 'WARN', 'Fixed-window target exceeds the supplied bytes; no out-of-bounds target is read.'
    else:
        target_locations.append(_location(target, 1, 'Entry target byte'))
        status, detail = 'PASS', 'The target lies in the lower bank-0 window for the supported controller layout. Boot-ROM state and target instructions are not executed or verified.'
    return [branch, _item('Game Boy entry target', status, detail, target_locations,
                          cpu_address=target, value=target, reference=_GB)]


def _gba(raw, candidate):
    name = 'GBA ARM entry branch'
    if candidate.get('format') != 'gba-linear' or len(raw) < 4:
        return [_item(name, 'NOT_CHECKED', 'A complete linear ARM entry word is required.', reference=_GBA)]
    word = int.from_bytes(raw[:4], 'little')
    locations = [_location(0, 4, 'ARM cartridge entry word')]
    if word & 0xff000000 != 0xea000000:
        return [_item(name, 'NOT_CHECKED', 'Entry is not the supported unconditional ARM B instruction. Conditional branches, BL and other instructions are not decoded.',
                      locations, value=word, reference=_GBA)]
    displacement = word & 0xffffff
    if displacement & 0x800000:
        displacement -= 0x1000000
    offset = 8+(displacement << 2)
    address = (0x08000000+offset) & 0xffffffff
    if offset == 0:
        status, detail = 'WARN', 'Unconditional ARM B returns to its own entry word; no code is executed to assess intent.'
    elif not 0 <= offset <= min(len(raw), 32*1024*1024)-4:
        status, detail = 'WARN', 'Signed ARM branch destination is outside the bounded cartridge image; mirrors and alternate boot environments are not inferred.'
    else:
        locations.append(_location(offset, 4, 'ARM branch target word'))
        status, detail = 'PASS', 'Signed imm24 displacement with the ARM PC+8 rule resolves to a complete word in the image. This is static encoding/mapping evidence, not instruction or boot verification.'
    return [_item(name, status, detail, locations, cpu_address=address, value=address, reference=_GBA)]


def inspect_startup(raw: bytes, candidate: dict) -> list:
    """Inspect a unique layout-valid candidate without changing any input.

    Unknown instructions and mappings return NOT_CHECKED. Warnings are not a
    corruption verdict. FAIL is reserved for a proven alignment constraint.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError('startup inspection requires raw cartridge bytes')
    if not isinstance(candidate, dict) or candidate.get('layout_valid') is not True:
        return [_item('Cartridge startup inspection', 'NOT_CHECKED',
                      'A unique layout-valid system candidate is required; no startup mapping is inferred.')]
    metadata = candidate.get('metadata')
    if not isinstance(metadata, dict):
        return [_item('Cartridge startup inspection', 'NOT_CHECKED', 'Candidate metadata is unavailable.')]
    system = candidate.get('system_id')
    if system == 'nes':
        return _nes(raw, candidate, metadata)
    if system == 'snes':
        return _snes(raw, candidate, metadata)
    if system == 'genesis':
        return _genesis(raw, candidate, metadata)
    if system in ('gb', 'gbc'):
        return _gb(raw, candidate, metadata)
    if system == 'gba':
        return _gba(raw, candidate)
    return [_item('Cartridge startup inspection', 'NOT_CHECKED',
                  'No startup inspection is implemented for this system.')]
