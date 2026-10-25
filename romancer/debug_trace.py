"""Exact tuple/range resolution without mapper inference or fuzzy matching."""


def resolve_probe(probe: dict,normalized_case: dict) -> dict:
    address=probe['address'];length=probe['length']
    result={'probe_id':probe['id'],'status':'UNRESOLVED','reason':'no wholly containing declared window','window_id':None,'file_offset':None,'memory':None}
    space=next(row for row in normalized_case['spaces'] if row['id']==address['space'])
    if space['bank_bits'] and address['bank'] is None:return {**result,'reason':'bank is unknown'}
    for window in normalized_case['windows']:
        delta=address['offset']-window['start']
        if ((address['space'],address['bank'])==(window['space'],window['bank'])
                and 0<=delta and length<=window['length']-delta):
            memory=window['memory']
            return {**result,'status':'RESOLVED','reason':'declared address correspondence only','window_id':window['id'],
                    'file_offset':None if window['file_offset'] is None else window['file_offset']+delta,
                    'memory':None if memory is None else {'region':memory['region'],'offset':memory['offset']+delta,'length':length}}
    return result


def select_trace_candidates(trace: dict,normalized_case: dict) -> list[dict]:
    result=[];spaces={row['id']:row for row in normalized_case['spaces']}
    for probe in normalized_case['probes']:
        address=probe['address']
        if spaces[address['space']]['bank_bits'] and address['bank'] is None:continue
        for event in trace['events']:
            access=event['access']
            if access is None:continue
            other=access['address']
            if (spaces[other['space']]['bank_bits'] and other['bank'] is None):continue
            if ((address['space'],address['bank'])==(other['space'],other['bank'])
                    and address['offset']<other['offset']+access['length'] and other['offset']<address['offset']+probe['length']):
                result.append({'probe_id':probe['id'],'event_id':event['id'],'line':event['line'],'access':access,
                               'origin':'imported_trace','alignment':'UNKNOWN'})
    return result
