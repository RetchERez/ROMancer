"""iNES/NES 2.0 file regions; no CPU mapper inference."""
from . import candidate,region
from ..system_reader import MAX_SOURCE


def _rom_size(low,high,unit):
    if high==15:
        exponent=low>>2
        if exponent>33:raise ValueError('NES 2.0 ROM size exceeds source budget')
        size=(1<<exponent)*((low&3)*2+1)
    else:size=((high<<8)|low)*unit
    if size>MAX_SOURCE:raise ValueError('NES ROM size exceeds source budget')
    return size


def candidates(reader):
    size=reader.identity['size']
    if size<4 or reader.read_at(0,4)!=b'NES\x1a':return []
    if size<16:return [candidate('nes','ines',0,metadata={},valid=False,warnings=['Truncated NES header.'])]
    h=reader.read_at(0,16);nes2=(h[7]&12)==8;mapper=(h[6]>>4)|(h[7]&240)
    if nes2:mapper|=(h[8]&15)<<8
    meta={'mapper':mapper,'submapper':h[8]>>4 if nes2 else None,'trainer_present':bool(h[6]&4),
        'console_type':h[7]&3,'cpu_mapping':'NOT_INFERRED'}
    try:
        prg=_rom_size(h[4],h[9]&15 if nes2 else 0,16384)
        chr_size=_rom_size(h[5],h[9]>>4 if nes2 else 0,8192)
    except ValueError as exc:return [candidate('nes','nes2' if nes2 else 'ines',0,metadata=meta,valid=False,warnings=[str(exc)])]
    meta.update(prg_rom_bytes=prg,chr_rom_bytes=chr_size,chr_storage='ROM' if chr_size else 'RAM')
    trainer=512 if h[6]&4 else 0;start=16+trainer;end=start+prg+chr_size;warnings=[]
    valid=prg>0 and end<=size
    if not valid:warnings.append('Declared NES ROM regions are empty or extend beyond the source.')
    if nes2 and trainer and mapper in (561,562):
        valid=False;warnings.append('This mapper has a nonstandard trainer layout; explicit layout support is required.')
    regions=[region('header','header',0,16)]
    if valid:
        if trainer:regions.append(region('trainer','trainer',16,512))
        regions.append(region('prg-rom','program',start,prg))
        if chr_size:regions.append(region('chr-rom','graphics',start+prg,chr_size))
        if end<size:regions.append(region('trailing','unknown',end,size-end));warnings.append('Trailing bytes are preserved without inferred semantics.')
    else:regions=[]
    if not nes2 and any(h[11:16]):warnings.append('Nonzero legacy padding is retained; mapper state is not inferred.')
    return [candidate('nes','nes2' if nes2 else 'ines',0,metadata=meta,regions=regions,warnings=warnings,valid=valid)]
