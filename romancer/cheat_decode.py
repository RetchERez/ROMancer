"""Original, bounded Game Genie format decoder; never activates or applies codes.

Bit layouts are format facts corroborated by the pinned primary sources below.
No upstream decoder implementation or publisher archive is bundled here. A CPU
address is deliberately not a ROM file offset: mappers, banks, mirrors, compare
bytes and exact revisions must be checked by a separate read-only resolver.
"""
import re


FORMAT_SOURCES={
    'nes':{'url':'https://github.com/libretro/libretro-fceumm/blob/ac0d00a7fc01166f84c7bac01d1084ebfd2b865e/src/cheat.c',
           'license':'GPL-2.0','scope':'Format facts from FCEUI_DecodeGG; source implementation not reused.'},
    'snes':{'url':'https://github.com/libretro/bsnes-mercury/blob/79d7f9de218b6ffa65a80bbdc5828532bc239232/target-libretro/libretro.cpp',
            'license':'GPL-3.0','scope':'Game Genie symbol substitution and CPU-address bit layout only.'},
    'genesis':{'url':'https://github.com/libretro/Genesis-Plus-GX/blob/60bee4c724859710ce05672239e5b601ad01382e/libretro/libretro.c',
               'license':'custom noncommercial','scope':'Game Genie bit layout only; source implementation not reused.'},
    'gb':{'url':'https://github.com/libretro/gambatte-libretro/blob/d9d6cd06382d1ced30de34d56d3609452323dab1/libgambatte/src/mem/cartridge.cpp',
          'license':'GPL-2.0','scope':'Game Genie CPU address, value and comparison encoding facts only.'}
}
FORMAT_SOURCES['gbc']=dict(FORMAT_SOURCES['gb'])

_NES_ALPHABET='APZLGITYEOXUKSVN'
_SNES_ALPHABET='DF4709156BC8A23E'
_GENESIS_ALPHABET='ABCDEFGHJKLMNPRSTVWXYZ0123456789'
_ALIASES={'fc':'nes','sfc':'snes','gen':'genesis','md':'genesis','megadrive':'genesis',
          'mega-drive':'genesis','gameboy':'gb','game-boy':'gb',
          'gameboycolor':'gbc','game-boy-color':'gbc'}


def _bits(values,groups,base=0):
    """Gather documented contiguous bit groups into a result word."""
    result=base
    for index,source,count,destination in groups:
        result|=((values[index]>>source)&((1<<count)-1))<<destination
    return result


def _nes(code):
    if len(code) not in (6,8) or any(c not in _NES_ALPHABET for c in code):
        raise ValueError('NES Game Genie requires 6 or 8 letters from its declared alphabet')
    digits=[_NES_ALPHABET.index(c) for c in code]
    address=_bits(digits,((1,3,1,7),(2,0,3,4),(3,0,3,12),(3,3,1,3),
                          (4,0,3,0),(4,3,1,11),(5,0,3,8)),0x8000)
    last=5 if len(digits)==6 else 7
    value=_bits(digits,((0,0,3,0),(0,3,1,7),(1,0,3,4),(last,3,1,3)))
    compare=None if len(digits)==6 else _bits(digits,((5,3,1,3),(6,0,3,0),(6,3,1,7),(7,0,3,4)))
    return address,value,compare


def _snes(code):
    if re.fullmatch(r'[0-9A-F]{4}-[0-9A-F]{4}',code) is None:
        raise ValueError('SNES Game Genie requires XXXX-XXXX hexadecimal syntax')
    digits=[_SNES_ALPHABET.index(c) for c in code.replace('-','')]
    scrambled=0
    for digit in digits[2:]:scrambled=(scrambled<<4)|digit
    address=_bits([scrambled],((0,6,4,0),(0,16,4,4),(0,14,2,8),(0,0,2,10),
                               (0,20,4,12),(0,2,4,16),(0,10,4,20)))
    return address,(digits[0]<<4)|digits[1],None


def _genesis(code):
    if len(code)!=9 or code[4]!='-' or any(c not in _GENESIS_ALPHABET for c in code[:4]+code[5:]):
        raise ValueError('Genesis Game Genie requires XXXX-XXXX in its declared base32 alphabet')
    digits=[_GENESIS_ALPHABET.index(c) for c in code.replace('-','')]
    address=_bits(digits,((1,0,2,14),(2,0,5,9),(3,0,4,20),(3,4,1,8),
                          (4,1,4,16),(6,0,3,5),(7,0,5,0)))
    value=_bits(digits,((0,0,5,3),(1,2,3,0),(4,0,1,12),(5,0,1,15),(5,1,4,8),(6,3,2,13)))
    return address,value,None


def _gameboy(code):
    if re.fullmatch(r'[0-9A-F]{3}-[0-9A-F]{3}(?:-[0-9A-F]{3})?',code) is None:
        raise ValueError('GB/GBC Game Genie requires XXX-XXX or XXX-XXX-XXX hexadecimal syntax')
    digits=[int(c,16) for c in code.replace('-','')]
    address=_bits([digits[2],digits[3],digits[4],digits[5]^15],
                  ((0,0,4,8),(1,0,4,4),(2,0,4,0),(3,0,3,12)))
    compare=None
    if len(digits)==9:
        encoded=(digits[6]<<4)|digits[8]
        compare=_bits([encoded],((0,2,6,0),(0,0,2,6)))^0xba
    return address,(digits[0]<<4)|digits[1],compare


def decode_code(system_id,code,format='game-genie'):
    """Return CPU-address substitution metadata, or raise ValueError.

    Width and alignment are in bytes. Genesis words retain the encoded address,
    including odd addresses, so the resolver can refuse unsupported alignment.
    No bank, mapper, ROM offset, effect meaning or runtime success is inferred.
    """
    if type(system_id) is not str or len(system_id)>64:raise ValueError('unsupported cheat system')
    system=system_id.strip().lower().replace(' ','');system=_ALIASES.get(system,system)
    if system not in FORMAT_SOURCES:raise ValueError('Game Genie is unsupported for this system')
    if type(format) is not str or format.strip().lower().replace(' ','-').replace('_','-')!='game-genie':
        raise ValueError('unsupported cheat format; choose game-genie')
    if type(code) is not str or not 1<=len(code)<=32 or not code.isascii():
        raise ValueError('cheat code must be bounded ASCII text')
    normalized=code.strip().upper()
    decoder={'nes':_nes,'snes':_snes,'genesis':_genesis,'gb':_gameboy,'gbc':_gameboy}[system]
    address,value,compare=decoder(normalized)
    width=2 if system=='genesis' else 1
    return {'system_id':system,'format':'game-genie','code':normalized,'operation':'rom-read',
            'address_space':'cpu','address':address,'value':value,'width':width,'compare':compare,
            'endian':'big' if width==2 else 'little','alignment':width,'mapping_required':True,
            'semantic_verified':False,'runtime_activation_verified':False,'reference':FORMAT_SOURCES[system]['url']}
