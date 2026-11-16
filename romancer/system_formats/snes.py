"""Explicit SNES header candidates; a self-consistent header remains heuristic."""
import hashlib
from . import candidate,region,text

# Physical layout facts independently checked against the pinned MAME source
# inventory. Keys bind body length, header position and all header bytes except
# the checksum/complement. This permits ordinary content edits and checksum
# maintenance without changing a nonstandard mode byte or inferring game identity.
NONSTANDARD_HEADERS={
    (1048576,0x7fc0,'c20a02795424e4498a4065f7eb19f8b21fc3b1df29e4a171e6d5b7a3c4d80024'):'lorom',
    (1048576,0x7fc0,'dfdaf5dd40c9833e1d28cf24cd544658b0be306bd49b3c824fccc3d0d4dcfaef'):'lorom',
}


def candidates(reader):
    size=reader.identity['size'];result=[]
    for prefix in (0,512):
        body=size-prefix
        if body<=0 or body%32768:continue
        for name,offset,modes in (('lorom',0x7fc0,(0x20,0x30,0x23,0x32)),('hirom',0xffc0,(0x21,0x31)),('exhirom-candidate',0x40ffc0,(0x25,0x35))):
            position=prefix+offset
            if position+64>size:continue
            h=reader.read_at(position,64)
            signature=hashlib.sha256(h[:28]+h[32:]).hexdigest()
            known_header=NONSTANDARD_HEADERS.get((body,offset,signature))==name
            if h[21] not in modes and not known_header:continue
            title_ascii=all(32<=c<127 or c==0 for c in h[:21])
            hardware={0x23:('sa1',(0x34,0x35)),0x32:('sdd1',(0x43,0x45))}.get(h[21])
            chip_valid=hardware is None or h[22] in hardware[1]
            pair=(int.from_bytes(h[28:30],'little')^int.from_bytes(h[30:32],'little'))==65535
            declared=(1<<(h[23]+10)) if h[23]<=15 else None
            rounded=1<<((body-1).bit_length())
            valid=pair and declared==rounded and chip_valid
            warnings=['Mapping is heuristic; no CPU/bank mapping or whole-image checksum is established.']
            if not pair or declared!=rounded:warnings.append('SNES header checksum pair or declared ROM size is inconsistent.')
            if not chip_valid:warnings.append('This map mode requires its documented cartridge chip type.')
            if hardware:warnings.append('Enhancement-chip CPU windows and decompression require their own observed mapping; a LoROM header is only the file-container layout.')
            if not title_ascii:warnings.append('Header title contains non-ASCII bytes; its text encoding is not inferred.')
            if known_header:warnings.append('A checked nonstandard header-layout signature matched; game identity still requires the complete file hash.')
            if name=='exhirom-candidate':warnings.append('ExHiROM addressing is not implemented by this foundation.')
            meta={'title':text(h[:21]) if title_ascii else 'Non-ASCII header title','title_ascii':title_ascii,
                'map_mode':h[21],'cartridge_type':h[22],'copier_header_bytes':prefix,'declared_rom_bytes':declared,
                'checksum_pair_valid':pair,'rounded_payload_bytes':rounded,'whole_image_checksum':'NOT_CHECKED','address_mapping':'NOT_INFERRED'}
            if hardware:meta['cartridge_hardware']=hardware[0]
            if known_header:meta['layout_signature_sha256']=signature
            regions=[region('rom','program',prefix,body),region('header','header',position,64)] if valid else []
            if prefix and valid:regions.insert(0,region('copier-header','prefix',0,512))
            result.append(candidate('snes',name,position,metadata=meta,regions=regions,warnings=warnings,valid=valid,confidence='heuristic'))
    return result
