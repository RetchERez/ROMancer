"""Owned declarative system capabilities; recognition is never write permission."""
import copy

REGISTRY_VERSION='1'
FOCUS_SYSTEM_IDS=('nes', 'snes', 'genesis', 'gb', 'gbc', 'sms')
SYSTEM_IDS=frozenset({'nes', 'snes', 'genesis', 'gb', 'gbc', 'sms'})


def _cap(status,reason,implementation):
    return {'status':status,'reason':reason,'implementation':implementation}


def _definitions():
    descriptions=(('nes', 'NES', ['ines', 'nes2'], 'iNES/NES 2.0 header, trainer, PRG-ROM and CHR-ROM extents.'), ('snes', 'SNES', ['lorom', 'hirom', 'exhirom-candidate'], 'Header candidates and declared copier prefix; mapping remains heuristic.'), ('genesis', 'Genesis', ['genesis-linear'], 'Linear cartridge header and declared ROM extent; interleaved variants are separate.'), ('gb', 'Game Boy', ['gb-cartridge'], 'DMG header, declared ROM banks and header checksum.'), ('gbc', 'Game Boy Color', ['gbc-cartridge'], 'CGB-compatible and Color-only header flags, ROM banks and checksums.'), ('sms', 'Master System', ['sms-sega'], 'Bounded Sega header and additive checksum; game resources require declarations.'))
    packs=[]
    for identifier,label,formats,description in descriptions:
        module='romancer/system_formats/'+('gb' if identifier=='gbc' else identifier)+'.py'
        capabilities={
            'identification':_cap('experimental' if identifier=='snes' else 'supported',description,module),
            'raw_inspection':_cap('supported','Bounded read-only inspection of registered bytes.','romancer/workbench_projects.py:inspect_resource'),
            'structured_formats':_cap('supported','Exact-revision declared flat resources use explicit codec/slot descriptors.','romancer/assets.py; romancer/script.py'),
            'automatic_resource_discovery':_cap('supported','Bounded text/graphics candidates and validated LZ10/RLE probes; every editable location still needs confirmation.','romancer/resource_discovery.py'),
            'address_translation':_cap('unsupported' if identifier=='sms' else 'supported','Declared supported windows only; bank state is not inferred.','romancer/system_addresses.py'),
            'integrity_repair':_cap('supported','System edit plans maintain supported cartridge checksums.','romancer/system_integrity.py'),
            'runtime_control':_cap('unavailable','Configure a matching native core and measure its worker handshake.','romancer/workbench_runtime.py'),
            'nes_chr_descriptor':_cap('supported' if identifier=='nes' else 'unsupported',
                'NES CHR-ROM pages use a checked literal planar descriptor; CHR-RAM is not stored ROM art.' if identifier=='nes' else 'This descriptor applies only to NES CHR-ROM.',
                'romancer/system_resources.py:describe_nes_chr'),
        }
        packs.append({'id':identifier,'label':label,'version':REGISTRY_VERSION,'formats':formats,
            'release_focus':identifier in FOCUS_SYSTEM_IDS,'capabilities':capabilities,'runtime_requirements':{'core_platform':'match-host',
                'system_files':'explicit BIOS/system file configuration' if identifier=='segacd' else 'core-specific',
                'configured':False,'probed':False}})
    return packs


def system_inventory()->dict:
    return {'schema_version':1,'operation':'systems-list','ok':True,'registry_version':REGISTRY_VERSION,
        'systems':copy.deepcopy([p for p in _definitions() if p['id'] in FOCUS_SYSTEM_IDS]),'write_authorized':False,'runtime_verified':False}


def get_system(system_id:str)->dict:
    if type(system_id) is not str or system_id not in SYSTEM_IDS:raise ValueError('unknown canonical system ID')
    return copy.deepcopy(next(pack for pack in _definitions() if pack['id']==system_id))
