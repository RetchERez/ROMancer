"""Small, sourced editing definitions; exact originals and explicit owned lineage.

Definitions describe tested locations, not whole-game compatibility. Original
game files stay local. Every write uses the existing byte planner.
"""
from pathlib import Path
import re
from . import workbench_projects as projects
from .asset_schema import fields, number


PROFILES=(
    {'id':'castlevania-usa','name':'Castlevania','system':'nes','size':131088,
     'sha256':'55bcab0d9efc33a9d9efc90f2c3c4ab12f3221a44b1f357e6c6202a456399aa8',
     'reference':'https://github.com/rumbleminze/castlevania-snes/blob/main/src/bank7.asm',
     'scope':'Starting spare lives; both initialization constants. Verified HUD 3 to 9.',
     'offsets':[(0x1c836,1,'Starting spare lives'),(0x1c93b,1,'Mirrored initialization')]},
    {'id':'chrono-trigger-usa','name':'Chrono Trigger','system':'snes','size':4194304,
     'sha256':'06d1c2b06b716052c5596aaa0c2e5632a027fee1a9a28439e509f813c30829a9',
     'reference':'https://github.com/dscotton/ct_disassembly/blob/main/data/item_weapon_stats.asm',
     'scope':'Wood Sword weapon power. Power 3 to 30 produced displayed attack 8 to 23; the game computes final attack.',
     'offsets':[(0xc0267,1,'Wood Sword power')]},
    {'id':'immortal-ue','name':'The Immortal','system':'genesis','size':1048576,
     'sha256':'b60aa52e46a199f755a1eb99daea543c468acf07d83624c85a84cdd14b786375',
     'reference':'https://github.com/sewave/translations/blob/master/smd/immortalthesmd/immortalthesmd.hex',
     'scope':'New-game menu prompt, up to nine ASCII characters. Includes the documented game-specific ROM-check adjustment.',
     'offsets':[(0x4e1b,9,'New-game prompt'),(0xfffca,2,'Game-specific integrity adjustment')]},
    {'id':'wario-land4-ue','name':'Wario Land 4','system':'gba','size':8388608,
     'sha256':'d16c7bf6e62bb84049fff1b387108fbd1e6e2cd38ca994ab5310dd9cbf9ba414',
     'reference':'https://github.com/lilDavid/warioland4/blob/master/asm/disasm_file_select.s',
     'scope':'Two file-select RGB555 palettes. Original or the verified teal/magenta variation.',
     'offsets':[(0x74253c,512,'File-select palette 1'),(0x74273c,512,'File-select palette 2')]},
)

BYTE_NOTES={
 'castlevania-usa':[
  {'storage':'Unsigned 8-bit counter','meaning':'Initialization counter includes the current life. Spare lives = stored value minus 1. Both initialization constants must agree.',
   'example':'04 = 3 spare lives; 0A = 9 spare lives.','evidence':'Native HUD changed from P-03 to P-09 after a new start.'},
  {'storage':'Unsigned 8-bit counter','meaning':'Second guarded initialization constant for the same life counter. Keep it equal to 0x1C836.',
   'example':'04 to 0A in both locations.','evidence':'Both code locations were checked against the exact original and tested together.'}],
 'chrono-trigger-usa':[
  {'storage':'Unsigned 8-bit weapon power','meaning':'Wood Sword base weapon power. This is an input to the game formula, not the final displayed attack stat.',
   'example':'03 = power 3; 1E = power 30.','evidence':'The tested build changed displayed attack from 8 to 23 on Crono\'s equipment screen.'}],
 'immortal-ue':[
  {'storage':'Fixed 9-byte ASCII text slot','meaning':'New-game prompt. Shorter text is padded with spaces. The following % delimiter at 0x4E24 is preserved.',
   'example':'New game? to New hack?; neither text changes the slot length.','evidence':'The changed prompt was visible after native boot with the required integrity adjustment.'},
  {'storage':'68000 opcode word, 2-byte patch','meaning':'Game-specific ROM check adjustment: replace the guarded instruction start with RTS (4E 75). The named plan also repairs the standard Genesis checksum.',
   'example':'0C 80 to 4E 75 at this exact guarded revision.','evidence':'Standard header checksum repair alone produced a black screen; the explicit adjustment allowed the tested menu edit to boot.'}],
 'wario-land4-ue':[
  {'storage':'256 little-endian RGB555 colors','meaning':'File-select palette block: 2 bytes per color. Red uses bits 0–4, green 5–9 and blue 10–14. This is palette data, not tile pixels.',
   'example':'1F 00 = full red; E0 03 = full green; 00 7C = full blue.','evidence':'Rotating color channels in both blocks produced the observed teal/magenta file-select screen.'},
  {'storage':'256 little-endian RGB555 colors','meaning':'Second file-select palette block. The verified color variation changes both 512-byte blocks together.',
   'example':'Each color is 2 bytes; 256 colors occupy 512 bytes.','evidence':'Both palette blocks were tested together in the same build.'}]
}


def _resolve(project,row,cancelled):
    current=row;seen=set()
    for _ in range(64):
        if current['artifact_id'] in seen:raise ValueError('cyclic game-definition ancestry')
        seen.add(current['artifact_id']);projects._measure(current['path'],current,cancelled=cancelled)
        if current['kind']=='source':
            profile=next((p for p in PROFILES if p['sha256']==current['sha256'] and p['size']==current['size']),None)
            if profile and (row['size']!=profile['size'] or row.get('system_id')!=profile['system']):return None,None
            return profile,current
        if not current.get('source_id'):return None,None
        current=projects.artifact(project,current['source_id'])
    raise ValueError('game-definition ancestry exceeds 64 builds')


def _read(path,offset,length):
    with Path(path).open('rb') as stream:stream.seek(offset);raw=stream.read(length)
    if len(raw)!=length:raise ValueError('verified game location exceeds the selected ROM')
    return raw


def _rotate(raw):
    result=bytearray()
    for i in range(0,len(raw),2):
        c=int.from_bytes(raw[i:i+2],'little')
        if c>0x7fff:raise ValueError('unsupported file-select palette value')
        result.extend((((c>>10)&31)|((c&31)<<5)|(((c>>5)&31)<<10)).to_bytes(2,'little'))
    return bytes(result)


def _model(profile,root,path):
    identifier=profile['id']
    if identifier=='castlevania-usa':
        constants=[]
        for offset,_,_ in profile['offsets']:
            raw=_read(path,offset-1,4)
            if raw[0]!=0xa9 or raw[2:]!=b'\x85\x2a':raise ValueError('starting-lives code guard differs; inspect the selected build')
            constants.append(raw[1])
        if constants[0]!=constants[1]:raise ValueError('mirrored starting-lives constants differ; inspect both locations')
        number(constants[0],2,100)
        return [{'id':'spare_lives','label':'Starting spare lives','type':'integer','min':1,'max':99,'value':constants[0]-1}]
    if identifier=='chrono-trigger-usa':
        return [{'id':'weapon_attack','label':'Wood Sword power','type':'integer','min':1,'max':255,'value':_read(path,0xc0267,1)[0]}]
    if identifier=='immortal-ue':
        slot=_read(path,0x4e1b,10);check=_read(path,0xfffca,10)
        if slot[-1]!=37 or any(c<32 or c>126 or c==37 for c in slot[:-1]):raise ValueError('menu text or protected terminator differs')
        if check not in (bytes.fromhex('0c80fede808566024e75'),bytes.fromhex('4e75fede808566024e75')):raise ValueError('game-specific integrity code guard differs')
        return [{'id':'menu_text','label':'New-game menu text','type':'text','max_length':9,'value':slot[:-1].decode('ascii').rstrip()}]
    originals=[_read(root['path'],offset,length) for offset,length,_ in profile['offsets']]
    current=[_read(path,offset,length) for offset,length,_ in profile['offsets']]
    value='original' if current==originals else 'teal_magenta' if current==[_rotate(r) for r in originals] else ''
    return [{'id':'palette_style','label':'File-select colors','type':'choice','value':value,
             'options':[['original','Original colors'],['teal_magenta','Teal and magenta']]}]


def palette_visuals(profile,root,path):
    if profile['id']!='wario-land4-ue':return None
    def colors(raw):
        return [[round(((int.from_bytes(raw[i:i+2],'little')>>shift)&31)*255/31) for shift in (0,5,10)] for i in range(0,len(raw),2)]
    rows=[]
    for offset,length,label in profile['offsets']:
        original=_read(root['path'],offset,length);current=_read(path,offset,length)
        rows.append({'name':label,'offset':offset,'current':colors(current),'original':colors(original),'teal_magenta':colors(_rotate(original))})
    return {'kind':'rgb555-palettes','palettes':rows,'scope':'Literal stored colors; native scene rendering is not predicted.'}


def inspect(project,row,path,*,cancelled=lambda:False):
    profile,root=_resolve(project,row,cancelled)
    if profile is None:return {'ok':True,'status':'UNSUPPORTED','profile':None,'artifact_id':row['artifact_id'],'source_sha256':row['sha256']}
    model=_model(profile,root,path);visual=palette_visuals(profile,root,path);projects._measure(path,row,cancelled=cancelled)
    if visual:projects._measure(root['path'],root,cancelled=cancelled)
    return {'ok':True,'status':'MATCHED' if row['kind']=='source' else 'DERIVED','artifact_id':row['artifact_id'],
            'source_sha256':row['sha256'],'verified_original_sha256':root['sha256'],'gameplay_verified':False,
            'profile':{k:profile[k] for k in ('id','name','system','reference','scope')},'fields':model,'visual':visual,
            'locations':[{'offset':o,'length':n,'label':label,**BYTE_NOTES[profile['id']][i]} for i,(o,n,label) in enumerate(profile['offsets'])],
            'note':'Definition locations were tested on the matched original. A new build still needs playtesting.'}


def plan(api,parameters,*,cancelled=lambda:False):
    project,row,path=api.source(parameters);profile,root=_resolve(project,row,cancelled)
    if profile is None or profile['id']!=parameters['profile_id']:raise ValueError('no matching verified game definition for this exact revision')
    model=_model(profile,root,path);values=parameters['values'];fields(values,' '.join(f['id'] for f in model))
    edits=[];preview=[];additional=[]
    def edit(offset,after):
        before=_read(path,offset,len(after))
        if before!=after:edits.append({'offset':offset,'before':before.hex(),'after':after.hex()})
    identifier=profile['id'];field=model[0];value=values[field['id']]
    if field['type']=='integer':number(value,field['min'],field['max'])
    if identifier=='castlevania-usa':
        for offset,_,_ in profile['offsets']:edit(offset,bytes([value+1]))
        name=f'{value} starting spare lives'
    elif identifier=='chrono-trigger-usa':
        edit(0xc0267,bytes([value]));name=f'Wood Sword power {value}'
    elif identifier=='immortal-ue':
        if type(value) is not str or not value.strip() or re.fullmatch(r'[A-Za-z0-9 ?]{1,9}',value) is None:raise ValueError('use 1 to 9 letters, digits, spaces or ?; game control characters are protected')
        edit(0x4e1b,value.ljust(9).encode('ascii'))
        if _read(path,0xfffca,2)!=b'\x4e\x75':
            edit(0xfffca,b'\x4e\x75');additional.append('Game-specific ROM check: documented 2-byte adjustment at 0xFFFCA.')
        name='Menu text - '+value
    else:
        if type(value) is not str or value not in ('original','teal_magenta'):raise ValueError('choose one of the verified file-select palettes')
        for offset,length,_ in profile['offsets']:
            original=_read(root['path'],offset,length);edit(offset,_rotate(original) if value=='teal_magenta' else original)
        name='File-select colors - '+('teal and magenta' if value=='teal_magenta' else 'original')
    if not edits:raise ValueError('no changes to build; choose a different value')
    preview.append({'label':field['label'],'before':field['value'],'after':value})
    result=api._integrity_plan({'project_id':parameters['project_id'],'artifact_id':row['artifact_id'],'edits':edits},cancelled)
    existing=next((b for b in projects.read_project(project)['builds'] if b.get('plan_id')==result['plan_id']),None)
    if existing is not None:projects._measure(existing['path'],existing,cancelled=cancelled)
    return {**result,'profile_id':identifier,'build_name':name,'preview':preview,'additional_changes':additional,
            'existing_build_id':existing['artifact_id'] if existing else None,
            'definition_reference':profile['reference'],'note':'Separate build. Test the result before sharing a patch.'}
