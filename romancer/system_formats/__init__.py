"""Bounded, read-only header parsers; metadata is not runtime evidence."""


def candidate(system_id,format,header_offset,*,metadata,regions=(),warnings=(),valid=True,confidence='structural'):
    return {'system_id':system_id,'format':format,'header_offset':header_offset,'confidence':confidence,
        'layout_valid':valid,'metadata':metadata,'regions':list(regions),'warnings':list(warnings)}


def region(id,kind,offset,length):return {'id':id,'kind':kind,'offset':offset,'length':length}


def text(raw):return raw.decode('ascii',errors='replace').rstrip(' \x00')
