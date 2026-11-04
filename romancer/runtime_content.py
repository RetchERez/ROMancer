"""Immutable native bus views for checked physical cartridge layouts.

Pinned MAME f34f02505e32c1993c6a782b6814232cbfc74e36/hash/megadriv.xml:
quacksht loads its two physical halves at0 and0x100000. Native canonical
observer reads independently confirmed zero-initialized gap storage. This is
engine input staging, not a ROM build, a cartridge-mirroring claim or an editor.
"""
import hashlib
from .system_formats import genesis

def native_view(raw):
    if type(raw)is not bytes or not 512<=len(raw)<=8*1024**2:return None
    class Reader:
        identity={'size':len(raw)}
        def read_at(self,at,length):return raw[at:at+length]
    choices=[c for c in genesis.candidates(Reader())if c['layout_valid']and c['format']=='genesis-scattered']
    if not choices:return None
    selected=choices[0];mapping=selected['metadata']['address_mapping'];end=selected['metadata']['rom_end']+1
    if end!=0x140000 or len(raw)!=0x80000 or selected['metadata']['canonical_gap_fill']!=0:raise ValueError('Unsupported checked native image view.')
    from .system_addresses import translate
    value=bytearray(end)
    for segment in mapping['segments']:
        at=segment['cpu_start'];start=segment['file_offset'];length=segment['length']
        if translate('genesis',at,mapping,None,len(raw))['offset']!=start:raise ValueError('Native view mapping differs.')
        value[at:at+length]=raw[start:start+length]
    image=bytes(value)
    return image,{'id':'genesis-scattered-zero-gap-v1','source_sha256':hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(image).hexdigest(),'size':len(image),'layout_signature_sha256':selected['metadata']['layout_signature_sha256']}
