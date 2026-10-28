"""Original factual summaries and storage prefixes, not game code or ROM data.

Public project descriptions are research leads. They never identify a user's
ROM revision, discover a table base, or prove a modified game's layout.
"""
from copy import deepcopy
import unicodedata
from .asset_schema import label,number


def _entry(identifier,title,system,repo,commit,path,facts,templates=(),addresses=()):
    return {'id':identifier,'title':title,'system_id':system,'status':'DOCUMENTED_REFERENCE',
            'url':'https://github.com/'+repo+'/blob/'+commit+'/'+path,'commit':commit,
            'facts':list(facts),'templates':list(templates),'addresses':list(addresses),
            'rom_revision_verified':False,'write_authorized':False}


REFERENCES=[_entry('pokemon-red-blue', 'Pokemon Red / Blue', 'gb', 'pret/pokered', '171e2c204f9c1ff8e577ca387a4bbb009e130843', 'constants/pokemon_data_constants.asm', ['The documented base-data prefix has a Pokedex number followed by five base stats, two type bytes, catch rate and experience yield.', 'Banked ROM addresses and sprite pointers require the correct bank and revision; the prefix is not a table locator.'], ['pokemon-red-blue']), _entry('pokemon-crystal', 'Pokemon Crystal', 'gbc', 'pret/pokecrystal', '5c877ef55197039c9676e8e3eec6d254b1c40fe8', 'constants/pokemon_data_constants.asm', ['The base-data prefix separates special attack and special defense. It differs from the Red/Blue layout.', 'The source also declares held items, gender, breeding and move-compatibility data beyond this prefix. Those bytes are not edited by the prefix template.'], ['pokemon-crystal']),   _entry('smb1', 'Super Mario Bros.', 'nes', 'Xkeeper0/smb1', '1cc3c92cbbe8cda44903657f3da332688e806a89', 'smb1.asm', ['The disassembly names player state, lives, world and area variables in CPU RAM.', 'These are runtime investigation leads, not ROM file offsets or universal addresses for rearranged hacks.'], addresses=[{'name': name, 'address': address, 'domain': 'cpu_ram', 'rom_file_offset_known': False} for name, address in [('Lives counter', 1882), ('Player power-up form', 1878), ('Displayed level number', 1884), ('World number', 1887), ('Internal area number', 1888), ('Player X low byte', 134), ('Player Y low byte', 206)]]), _entry('smw', 'Super Mario World', 'snes', 'IsoFrieze/SMWDisX', '30643c7595a7d097d731de69476f8059c7cf98c3', 'rammap.asm', ['The published RAM map distinguishes current power-up, position, screen-relative position and saved player state.', 'Lunar Magic edits can change level storage and supporting code. A base-game RAM label does not decode a modified level or establish its ROM bytes.'])]


def _fold(value):return ''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))


def catalog(query,system):
    label(query,128,blank=True)
    if system not in ('all', 'nes', 'snes', 'genesis', 'sms', 'gb', 'gbc'):raise ValueError('Choose a supported reference system.')
    rows=[r for r in REFERENCES if system in ('all',r['system_id']) and _fold(query) in _fold(r['title']+' '+' '.join(r['facts']))]
    return {'ok':True,'references':deepcopy(rows),'write_authorized':False,'rom_revision_verified':False,
            'note':'Pinned public research, not automatic compatibility with every hack. No game code or ROM is bundled.'}


def table_template(template_id,offset,count,stride,size,system):
    from .data_tables import validate_definition
    variants={'pokemon-red-blue': ('gb', [('Dex number', 0), ('HP', 1), ('Attack', 2), ('Defense', 3), ('Speed', 4), ('Special', 5), ('Type 1', 6), ('Type 2', 7), ('Catch rate', 8), ('Exp. yield', 9)]), 'pokemon-crystal': ('gbc', [('Dex number', 0), ('HP', 1), ('Attack', 2), ('Defense', 3), ('Speed', 4), ('Sp. attack', 5), ('Sp. defense', 6), ('Type 1', 7), ('Type 2', 8), ('Catch rate', 9), ('Exp. yield', 10)])}
    if template_id not in variants:raise ValueError('Choose a documented table prefix.')
    expected,fields=variants[template_id]
    if system!=expected:raise ValueError('This documented prefix belongs to another system.')
    number(offset,0,size);number(count,1,65536);number(stride,1,65536)
    return validate_definition({'schema_version':1,'name':template_id+' stat prefix (declared)','offset':offset,'count':count,'stride':stride,
       'fields':[{'name':name,'offset':at,'type':'u8','endian':'little','pointer_base':None} for name,at in fields]},size)


def inspect_template(api,p,c):
    from .data_tables import inspect_table
    _,row,path=api.source(p)
    d=table_template(p['template_id'],p['offset'],p['count'],p['stride'],row['size'],row.get('system_id'))
    result=inspect_table(path,row['sha256'],d,0,50)
    if c():raise KeyboardInterrupt
    return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'definition':result['definition'],'inspection':result,
            'rom_revision_verified':False,'game_semantics_verified':False,'write_authorized':False,
            'note':'Documented field positions applied at your declared base/stride/count. Verify the table and record identities before saving or editing.'}
