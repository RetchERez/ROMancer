"""Original factual summaries of pinned public references, not copied game data.

The verified-games service establishes exact original identity and owned build
ancestry before attaching these references. A documented format is not an
enabled editor or a fresh validation of an arbitrary derived build.
"""
from copy import deepcopy

VERSION=1


def _source(identifier,repo,commit,path='',scope='Public format reference'):
    return {'id':identifier,'url':'https://github.com/'+repo+('/blob/' if path else '/tree/')+commit+('/'+path if path else ''),
            'commit':commit,'scope':scope}


def _fact(label,status,scope,sources,**details):
    return {'label':label,'status':status,'scope':scope,'source_ids':sources,**details}


REFERENCES={
 'rastan-sms':{
  'sources':[{'id':'native-proof','url':'/user-guide/index.html#rastan-blobs','commit':'native-proof','scope':'ROMancer source-bound native observation','kind':'native_observation',
    'original_frame_sha256':'a1bb75c23d86c6e98f2e5e6c12d5e3d2a940c42168e7f94d53f98632a75e578c',
    'edited_frame_sha256':'77b64f165f92d9d9fdb469d072c86abde2e81b6cf9b179e48a10004b0ca6870a'}],
  'facts':[
   _fact('First humanoid enemy graphics','implemented','60 literal SMS 4bpp tiles at file offset 0x10000. Open the verified resource to edit a checked pose as one assembled sprite. The grayscale preview preserves indices; the stored palette is separate.',['native-proof'],offset=0x10000,length=1920),
   _fact('Observed sprite assembly','layout_checked','Two columns by four rows, tile indices 30,32,31,33,52,54,53,55. This is one observed pose, not a complete animation or metasprite grammar.',['native-proof']),
   _fact('Single-blob native check','layout_checked','The corrected build contains one connected blob per lower animation frame. Native frame841 shows the first humanoid enemies changed; collision, AI and other enemy types were not redesigned.',['native-proof'])]},
 'ffl2-usa':{
  'sources':[_source('disassembly','daid/FFL2-Disassembly','a5c17a90d87d102a9a45d287042c9a36ffd06f97')],
  'facts':[
   _fact('Room and arrival catalog','implemented','219 room-header variants reference 164 drawing streams and 543 arrival records. Names absent from the cartridge remain numbered; shared maps affect multiple arrivals.',['disassembly'],room_headers=219,map_streams=164,arrival_records=543,object_definitions=660),
   _fact('Real terrain previews','implemented','Decode supported drawing commands and actual 16-pixel metatiles. Conditional branches require explicit state. Unsupported circles stay unavailable. Only the opening atlas has an observed native palette.',['disassembly']),
   _fact('Fixed-width map edits','implemented','Opening atlas 486B only: preserve collision behavior, trigger ordering, conditions and packed flags. Moving an unconditional object can still move a story character. Each build requires playtesting.',['disassembly']),
   _fact('Room links','layout_checked','Arrival tags are decoded; saved-return links and event references are distinct. Structural link inspection does not prove a successful gameplay transition.',['disassembly'])]},
 'chrono-trigger-usa':{
  'sources':[_source('items','Pseudoarc/jetsoftime','3af9a5a8fa5db7cd47740c791fa6580f7a4efa44','sourcefiles/itemdata.py'),
             _source('enemies','Pseudoarc/jetsoftime','3af9a5a8fa5db7cd47740c791fa6580f7a4efa44','sourcefiles/enemystats.py'),
             _source('names','Pseudoarc/jetsoftime','3af9a5a8fa5db7cd47740c791fa6580f7a4efa44','sourcefiles/ctstrings.py'),
             _source('consumer','dscotton/ct_disassembly','eeae27acdb6565e96d1d796a3d60792c250c0aa1','bank_FD.asm')],
  'facts':[
   _fact('Named equipment tables','implemented','Read names from the selected cartridge: 85 weapon slots contain 74 names and 11 blank slots; 32 armor and 24 helm slots are named. IDs distinguish duplicates and unused entries.',['items','names'],weapon_offset=0xc0267,weapon_stride=5,armor_offset=0xc0481,helm_offset=0xc04e4),
   _fact('Attack, defense and prices','implemented','Supported fields are stored base attack, critical rate, defense and base price. Effects and flags are preserved. Final attack and sale prices depend on game formulas; fist power is level-derived.',['items','consumer']),
   _fact('Enemy HP and core stats','implemented','251 slots through ID FA contain 212 names and 39 blank slots. HP and declared numeric stats are editable; rewards, effects and battle scripts are preserved. Scripts may override stored values.',['enemies','names'],offset=0xc4700,stride=23,count=251),
   _fact('Battle effects and event scripts','research_candidate','Related public code exists, but a general effect/script editor and safe relocation are not implemented. Conflicting historical field descriptions are not promoted to writable fields.',['items','enemies'])]},
 'wario-land4-ue':{
  'sources':[_source('editor','wario-land/WL4Editor','1385bed01909a39e96367e80d23354db2069e278'),
             _source('docs','wario-land/Toge-Docs','aff83247ac9355d9ecd177a7dd86be188d0d745b'),
             _source('decomp','lilDavid/warioland4','abb7800a8d8fa6d7f7f003627893e06bc2879329')],
  'facts':[
   _fact('Rooms, layers and doors','layout_checked','Exact-original checks found 242 room headers across 25 standard level groups, 635 live doors and 683 distinct enabled layer streams. This reference inventory is not an enabled Wario level editor.',['editor','docs'],room_table_offset=0x78f280,room_header_bytes=44,door_table_offset=0x78f21c,door_record_bytes=12),
   _fact('Entities and shared lists','layout_checked','555 distinct three-byte entity lists contain 4559 records. 103 lists are shared across room/difficulty references; some rooms change entity sets by incoming door. Entry context and aliases must be preserved before editing.',['editor','docs']),
   _fact('Stage timers','layout_checked','Three stored decimal fields represent minutes, tens of seconds and seconds. They are not one unsigned 24-bit timer.',['editor','docs']),
   _fact('Audio resources','layout_checked','The M4A/Sappy-style sound table has 819 entries with 659 nonempty song headers in the matched original. This does not provide a commercial music sequence editor.',['decomp','docs']),
   _fact('File-select colors','implemented','The supported palette workflow edits the two observed RGB555 file-select blocks. Level palettes and object graphics are separate resources.',['decomp'])]},
 'dejavu-casebooks-usa':{
  'sources':[_source('resources','Hoshiruna/djv1-2disasm','b7ae8ca791ba31b956e015d3c87f3acc47f0fb42','notes/resource-text.txt'),
             _source('disassembly','Hoshiruna/djv1-2disasm','b7ae8ca791ba31b956e015d3c87f3acc47f0fb42')],
  'facts':[
   _fact('Dialogue pointers','layout_checked','1536 bank-relative little-endian pointer slots resolve to 1490 distinct messages. Terminators and control codes must be preserved. No text relocation or complete dialogue editor is enabled by this inventory.',['resources']),
   _fact('Object names','layout_checked','Case I has 240 fixed slots and Case II has 256. Each slot is 16 bytes, with at most 14 displayed glyphs; 373 slots are nonblank in the matched original.',['resources']),
   _fact('HUD and font compression','layout_checked','Documented HUD RLE and LZ resources were independently decoded within their original allocations. Replacing or growing them requires a separate checked editor.',['disassembly']),
   _fact('Scene-specific colors','layout_checked','86 Case I scene palettes contain five interface-palette variants; 76 Case II palettes contain three. Updating the opening colors does not recolor every scene.',['disassembly']),
   _fact('Opening interface palette','implemented','The supported color edit updates the observed startup and first Case I scene copies together. Later scene palettes remain separate.',['disassembly'])]},
 'immortal-ue':{
  'sources':[_source('text','sewave/translations','4237e3e93d8320abdbca39f8e028a7e99582fb28','smd/immortalthesmd/immortalthesmd.off'),
             _source('integrity','sewave/translations','4237e3e93d8320abdbca39f8e028a7e99582fb28','smd/immortalthesmd/immortalthesmd.hex')],
  'facts':[
   _fact('Text reference regions','layout_checked','21 documented extraction regions contain 192 original records covering 14128 bytes; every referenced record matched the exact local cartridge. These regions do not establish a pointer or level format.',['text']),
   _fact('New-game prompt','implemented','The fixed nine-character ASCII menu slot has a protected delimiter. The supported plan includes the explicit game-specific ROM-check adjustment and standard cartridge checksum.',['text','integrity'],offset=0x4e1b,length=9),
   _fact('Level and object formats','research_candidate','No Genesis-specific level or object grammar was established by these sources. An Apple IIGS engine implementation cannot establish the Genesis cartridge layout.',['text'])]},
 'castlevania-usa':{
  'sources':[_source('editor','spiiin/CadEditor','b28316ddd9be4e79ac5e6adf89b7751df609d94e','CadEditor/settings_nes/castlevania/Settings_Castlevania-1.cs'),
             _source('target','spiiin/CadEditor','b28316ddd9be4e79ac5e6adf89b7751df609d94e','CadEditor/ROMS/copySupportedRomsFromGoodROM.py'),
             _source('port','rumbleminze/castlevania-snes','f7490c28fd58aa59f4b2cb5d3077cb2f24939b7b','README.md')],
  'facts':[
   _fact('Starting lives','implemented','Two guarded initialization constants hold the current life plus spare lives. The matched original stores 4 for three spare lives; both constants change together.',['port'],offsets=[0x1c836,0x1c93b]),
   _fact('First-level block reference','research_candidate','A public editor describes one European level using 6-by-8 screen grids and 17-byte blocks. Its applicability to this USA revision is not certified. External graphics/palette dumps are not bundled.',['editor','target']),
   _fact('Port disassembly limitations','research_candidate','The NES-to-SNES port explicitly changes game code. Matching data spans are useful research leads; port addresses and code must not be assumed identical to the USA NES cartridge.',['port'])]}}


def reference_knowledge(profile_id,original_sha256,derived):
    entry=REFERENCES.get(profile_id)
    if entry is None:return None
    return {**deepcopy(entry),'version':VERSION,'profile_id':profile_id,
            'verified_original_sha256':original_sha256,'selected_is_derived':bool(derived),
            'selected_layout_revalidated':False,'gameplay_verified':False,'write_authorized':False,
            'note':'Reference facts were checked against the matched original. This inventory does not revalidate every field in a derived build or enable unsupported edits.'}
