"""Read-only tone metadata from the checked M4A song bank.

Primary structural reference is include/gba/m4a.h at the pinned Wario research
revision. No instrument/sample content is shipped with this implementation.
"""
from .asset_schema import number
from .m4a_music import inspect_song,REFERENCE

def inspect_instrument(raw,song_id,instrument,sha):
    number(instrument,0,255);song=inspect_song(raw,song_id,sha)
    used={e.get('instrument') for e in song['events'] if e.get('instrument') is not None}
    if instrument not in used:raise ValueError('Choose an instrument observed in this decoded song.')
    bank=int.from_bytes(raw[song['offset']+4:song['offset']+8],'little')-0x08000000;at=bank+instrument*12
    if bank%4 or bank<0 or not 0<=at<=len(raw)-12:raise ValueError('Instrument bank or tone record is outside this ROM.')
    tone=raw[at:at+12];kind=tone[0];channel=kind&7;compound=bool(kind&0xc0)
    names={0:'Direct sound',1:'Square channel1',2:'Square channel2',3:'Wave channel',4:'Noise channel'}
    status='COMPOUND_READ_ONLY' if compound else 'SUPPORTED_STRUCTURE' if channel in names and not kind&0x30 else 'UNSUPPORTED_STRUCTURE'
    result={'ok':True,'source_sha256':sha,'song_id':song['id'],'instrument':instrument,'bank_offset':bank,'offset':at,'length':12,
        'type':kind,'type_name':'Key split / rhythm table' if compound else names.get(channel,'Unmapped channel type'),
        'key':tone[1],'length_value':tone[2],'pan_or_sweep':tone[3],'fixed_pitch':bool(kind&8),
        'status':status,'editable':False,'game_semantics_verified':False,'reference':REFERENCE,
        'scope':'Read-only declared M4A tone structure used by this decoded song. Compound instruments are not followed. Game instrument names and exact mixing are not inferred.'}
    if status=='SUPPORTED_STRUCTURE':
        result['envelope']={name:tone[8+i] for i,name in enumerate(('attack','decay','sustain','release'))}
        if channel in (0,3):
            wave=int.from_bytes(tone[4:8],'little')-0x08000000
            if not 0<=wave<=len(raw)-16:result.update(status='UNSUPPORTED_STRUCTURE',reason='Wave pointer does not resolve inside the ROM.');return result
            if channel==3:result['wave']={'offset':wave,'length':16,'format':'gb-wave4'}
            else:
                sample_type=int.from_bytes(raw[wave:wave+2],'little');length=int.from_bytes(raw[wave+12:wave+16],'little');loop=int.from_bytes(raw[wave+8:wave+12],'little')
                if sample_type!=0 or not 1<=length<=1024**2 or wave+16+length>len(raw) or loop>length:
                    result.update(status='UNSUPPORTED_STRUCTURE',reason='The sample format or extent is outside this reader’s supported PCM structure.');return result
                result['wave']={'offset':wave+16,'length':length,'format':'pcm-s8','loop_start':loop,'status_word':int.from_bytes(raw[wave+2:wave+4],'little'),'frequency_word':int.from_bytes(raw[wave+4:wave+8],'little')}
    return result

class InstrumentTools:
    def __init__(self,api):self.api=api
    def routes(self):return {'sound.instrument':('project_id artifact_id song_id instrument',self.inspect)}
    def inspect(self,p,c):
        _,row,raw=self.api.studio.source(p,c)
        if row.get('system_id')!='gba':raise ValueError('Choose a checked M4A GBA source.')
        result=inspect_instrument(raw,p['song_id'],p['instrument'],row['sha256'])
        if c():raise KeyboardInterrupt
        return {**result,'artifact_id':row['artifact_id']}
