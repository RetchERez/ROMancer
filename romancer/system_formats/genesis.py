"""Checked physical Genesis containers; bus mappings remain explicit."""
import hashlib
from . import candidate,region,text


# Pinned MAME f34f02505e32c1993c6a782b6814232cbfc74e36, megadriv:quacksht.
# One 512KiB physical input: 256KiB at bus0, CONTINUE at bus0x100000.
# Only immutable header facts are fingerprinted; no game payload is included.
SCATTERED_HEADERS={(0x80000,'c910378e028d652268263ea8166905b3b85f5a7e2e37e70fc48f08bc8c56df38'):'quackshot-continue-v1'}

def candidates(reader):
    size=reader.identity['size']
    if size<0x104:return []
    identifier=reader.read_at(0x100,min(16,size-0x100))
    if not identifier.lstrip(b' ').startswith(b'SEGA'):return []
    if size<512:return [candidate('genesis','genesis-linear',0x100,metadata={},valid=False,warnings=['Truncated Genesis cartridge header.'])]
    h=reader.read_at(0x100,256);start=int.from_bytes(h[0xa0:0xa4],'big');end=int.from_bytes(h[0xa4:0xa8],'big')
    valid=start==0 and 511<=end<size;warnings=['ROM window and checksum are not runtime or mapper-state proof.']
    signature=hashlib.sha256(h[:0x8e]+h[0x90:]).hexdigest()
    if not valid and start==0 and end==0x13ffff and SCATTERED_HEADERS.get((size,signature))=='quackshot-continue-v1':
        mapping={'id':'genesis-scattered','segments':[
            {'cpu_start':0,'file_offset':0,'length':0x40000},
            {'cpu_start':0x100000,'file_offset':0x40000,'length':0x40000}]}
        return [candidate('genesis','genesis-scattered',0x100,metadata={
            'console':text(h[:16]),'title':text(h[0x50:0x80]),'rom_start':start,'rom_end':end,
            'checksum_header':int.from_bytes(h[0x8e:0x90],'big'),'whole_image_checksum':'NOT_CHECKED',
            'layout_signature_sha256':signature,'address_mapping':mapping,'canonical_gap_fill':0},
            regions=[region('rom','program',0,size),region('header','header',0x100,256)],
            warnings=['Checked scattered physical storage. Unmapped bus gaps are not file bytes. Runtime loader compatibility is separate.'],valid=True)]
    if not valid:warnings.append('Declared linear ROM extent is invalid or unsupported.')
    return [candidate('genesis','genesis-linear',0x100,metadata={'console':text(h[:16]),'title':text(h[0x50:0x80]),
        'rom_start':start,'rom_end':end,'checksum_header':int.from_bytes(h[0x8e:0x90],'big'),'whole_image_checksum':'NOT_CHECKED'},
        regions=[region('rom','program',0,size),region('header','header',0x100,256)] if valid else [],warnings=warnings,valid=valid)]
