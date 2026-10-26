"""Known exposed-buffer layouts of pinned cores, independent of ROM game names.

Primary interfaces are the corresponding pinned libretro wrappers shipped in
CORE-SOURCES.zip. These formulas were also checked using original CPU programs.
They propose watch ranges; they never report an active bank as observed.
"""
from .asset_schema import number
from .core_pins import CORE_PINS


def memory_probe(system,snapshot,offset,width):
    pin=CORE_PINS.get('gb' if system=='gbc' else system)
    if pin is None or snapshot.get('core_sha256')!=pin['sha256'] or snapshot.get('region')!=2:
        raise ValueError('This core buffer layout is not verified; use an observed CPU address instead.')
    size=snapshot.get('region_size');number(width,1,4);number(offset,0,size-width if type(size) is int else -1)
    expected={'nes':(2048,),'snes':(131072,),'genesis':(65536,),'gb':(8192,),'gbc':(32768,),'gba':(32768,262144)}
    if size not in expected[system]:raise ValueError('The exposed memory size differs from the verified core interface.')
    positions=list(range(offset,offset+width));bank=False
    if system=='nes':addresses=positions;physical=positions;domain='nesInternalRam';member='src/drivers/libretro/libretro.c'
    elif system=='snes':addresses=[0x7e0000+p for p in positions];physical=positions;domain='snesWorkRam';member='target-libretro/libretro.cpp'
    elif system=='gba':addresses=[0x02000000+p for p in positions];physical=positions;domain='gbaExtWorkRam';member='src/platform/libretro/libretro.c'
    elif system=='genesis':
        # This pinned Windows/x64 build exposes uint16_t work_ram directly.
        # CPU byte order is big endian; the host buffer is little endian.
        physical=[p^1 for p in positions];addresses=[0xff0000+p for p in physical];domain='genesisWorkRam';member='libblastem.c'
    else:
        physical=positions;addresses=[0xc000+p if p<4096 else 0xd000+(p%4096) for p in positions]
        bank=system=='gbc' and any(p>=4096 for p in positions);domain='gbWorkRam';member='libgambatte/libretro/libretro.cpp'
    return {'ok':True,'system_id':system,'buffer_offset':offset,'width':width,'cpu_addresses':addresses,
        'physical_domain':domain,'physical_offsets':physical,'requires_observed_bank':bank,'active_bank_observed':False,
        'probe':{'kind':'write','start':min(addresses),'end':max(addresses)},
        'physical_probe':{'kind':'write','start':min(physical),'end':max(physical),'domain':domain},
        'evidence':'pinned_core_interface_and_hardware_mapping','core_sha256':pin['sha256'],
        'reference':pin['source_url']+'/blob/'+pin['source_commit']+'/'+member,
        'scope':'Proposed CPU watch range for a fresh replay. Actual mapped physical addresses must be checked in captured events.',
        'same_runtime_state_claimed':False,'write_authorized':False}
