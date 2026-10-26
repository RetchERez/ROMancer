"""Numeric layouts and a bounded name decoder for the exact USA game profile.

Names remain in the user's selected ROM. This module contains layout facts,
not game text or upstream implementation code. The verified-games bridge owns
exact original SHA/size and derived-artifact lineage checks.
"""

ITEM_REFERENCE='https://github.com/Pseudoarc/jetsoftime/blob/3af9a5a8fa5db7cd47740c791fa6580f7a4efa44/sourcefiles/itemdata.py'
ENEMY_REFERENCE='https://github.com/Pseudoarc/jetsoftime/blob/3af9a5a8fa5db7cd47740c791fa6580f7a4efa44/sourcefiles/enemystats.py'
NAME_REFERENCE='https://github.com/Pseudoarc/jetsoftime/blob/3af9a5a8fa5db7cd47740c791fa6580f7a4efa44/sourcefiles/ctstrings.py'


def decode_name(raw):
    """Decode fixed name cells; retain unknown bytes as visible hex tokens."""
    raw=bytes(raw).rstrip(b'\xef\xff')
    if not raw:return {'label':'Blank slot','label_status':'blank'}
    text=[];unsupported=False
    punctuation={0xde:'!',0xdf:'?',0xe0:'/',0xe1:'“',0xe2:'”',0xe3:':',
                 0xe4:'&',0xe5:'(',0xe6:')',0xe7:"'",0xe8:'.',0xe9:',',
                 0xea:'=',0xeb:'-',0xec:'+',0xed:'%',0xef:' ',0xff:' '}
    for value in raw:
        if 0xa0<=value<=0xb9:character=chr(65+value-0xa0)
        elif 0xba<=value<=0xd3:character=chr(97+value-0xba)
        elif 0xd4<=value<=0xdd:character=str(value-0xd4)
        elif value in punctuation:character=punctuation[value]
        else:character=f'[{value:02X}]';unsupported=True
        text.append(character)
    return {'label':''.join(text),'label_status':'unsupported' if unsupported else 'decoded'}


def _field(name,offset,kind='u8',maximum=None):
    maximum=(65535 if kind=='u16' else 255) if maximum is None else maximum
    return {'name':name,'offset':offset,'type':kind,'endian':'little','pointer_base':None,
            'minimum':0,'maximum':maximum}


def _resource(identifier,name,offset,count,stride,first_id,columns,enemy=False):
    labels={'offset':(0xc6500 if enemy else 0xc0b5e)+11*first_id,
            'stride':11,'length':11,'skip':0 if enemy else 1,
            'encoding':'chrono-name','id_base':first_id}
    return {'id':identifier,'name':name,'kind':'tables','reference':ENEMY_REFERENCE if enemy else ITEM_REFERENCE,
            'scope':('Named enemy slots through ID FA; blank slots are marked. HP and core numeric stats only. '
                     'Battle scripts can alter these stored stats; flags, effects and rewards are preserved.' if enemy else
                     'Names are read from the selected ROM. IDs distinguish duplicates and unused entries. '
                     'Only declared numeric fields change; effects and other bytes are preserved. '
                     'Stored weapon power and prices are inputs to game formulas. Fist power is level-derived.'),
            'definition':{'schema_version':1,'name':name,'offset':offset,'count':count,'stride':stride,
                          'fields':columns,'label_source':labels}}


def resource_definitions():
    """Fresh definitions, attached only after the exact verified profile matches."""
    resources=[
        _resource('weapon-stats-table','Weapon attack and critical rates',0xc0267,85,5,1,
                  [_field('Base attack',0),_field('Critical rate (%)',2,maximum=100)]),
        _resource('armor-defense-table','Armor defense',0xc0481,32,3,0x5b,[_field('Base defense',0)]),
        _resource('helm-defense-table','Helm defense',0xc04e4,24,3,0x7c,[_field('Base defense',0)])]
    for kind,name,first,count in [('weapon','Weapon',1,85),('armor','Armor',0x5b,32),('helm','Helm',0x7c,24)]:
        resources.append(_resource(kind+'-price-table',name+' base prices',0xc06a4+6*first,count,6,first,
                                   [_field('Base price',1,'u16')]))
    resources.append(_resource('enemy-core-stats-table','Enemy HP and core stats',0xc4700,251,23,0,
                     [_field('HP',0,'u16'),_field('Level',2),_field('Speed',9),_field('Magic',10),
                      _field('Hit',11),_field('Evade',12),_field('Magic defense',13),
                      _field('Offense',14),_field('Defense',15)],enemy=True))
    resources.append({'id':'weapon-power-table','name':'Weapon base attack table','kind':'tables','legacy':True,
                      'reference':ITEM_REFERENCE,'scope':'Legacy 90-row attack-only definition; row numbers are record IDs.',
                      'definition':{'schema_version':1,'name':'Weapon base attack','offset':0xc0262,'count':90,'stride':5,
                                    'fields':[{'name':'Base attack','offset':0,'type':'u8','endian':'little','pointer_base':None}]}})
    return resources
