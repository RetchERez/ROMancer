"""Explicit case/trace grammar; imports never authenticate native observations."""
import hashlib
import json
import re
from .asset_schema import fields,number,label,provenance
from .script_schema import canonical_bytes


def sha(value,length=64):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{'+str(length)+'}',value):raise ValueError('invalid content identifier')


def _snapshot(value,maximum):
    encoded=canonical_bytes(value,max_bytes=maximum)
    return json.loads(encoded),hashlib.sha256(encoded).hexdigest()


def _rows(value,maximum,minimum=0):
    if type(value) is not list or not minimum<=len(value)<=maximum:raise ValueError('collection budget exceeded')
    names=set()
    for row in value:
        if type(row) is not dict:raise ValueError('collection members must be objects')
        name=label(row.get('id'))
        if name in names:raise ValueError('duplicate member ID')
        names.add(name)
    return names


def address(value,spaces,*,concrete=False):
    fields(value,'space bank offset')
    space=spaces.get(value['space'])
    if space is None:raise ValueError('undeclared address space')
    number(value['offset'],0,(1<<space['address_bits'])-1)
    if space['bank_bits']==0:
        if value['bank'] is not None:raise ValueError('unbanked space requires null bank')
    elif value['bank'] is None:
        if concrete:raise ValueError('window requires a concrete bank')
    else:number(value['bank'],0,(1<<space['bank_bits'])-1)


def validate_debug_case(case: dict) -> dict:
    case,digest=_snapshot(case,1024*1024)
    fields(case,'schema_version id version symptom build_id source trace_sha256 spaces windows probes captures links provenance')
    number(case['schema_version'],1,1);label(case['id']);label(case['version']);label(case['symptom'],512)
    sha(case['build_id']);sha(case['trace_sha256']);provenance(case['provenance'])
    fields(case['source'],'role sha256 size');label(case['source']['role']);sha(case['source']['sha256']);size=number(case['source']['size'],0,64*1024*1024)
    _rows(case['spaces'],16,1);spaces={row['id']:row for row in case['spaces']}
    for space in case['spaces']:
        fields(space,'id address_bits bank_bits');number(space['address_bits'],1,32);number(space['bank_bits'],0,16)
    _rows(case['windows'],128);ranges=[]
    for row in case['windows']:
        fields(row,'id space bank start length file_offset memory provenance');provenance(row['provenance'])
        address({'space':row['space'],'bank':row['bank'],'offset':row['start']},spaces,concrete=True)
        length=number(row['length'],1,1<<32)
        if length>(1<<spaces[row['space']]['address_bits'])-row['start']:raise ValueError('window exceeds address width')
        if row['file_offset'] is None and row['memory'] is None:raise ValueError('window needs a declared target')
        if row['file_offset'] is not None:
            number(row['file_offset'],0,size)
            if length>size-row['file_offset']:raise ValueError('window exceeds source bytes')
        if row['memory'] is not None:
            fields(row['memory'],'region offset');number(row['memory']['region'],0,3);number(row['memory']['offset'],0,256*1024*1024-1)
            if length>256*1024*1024-row['memory']['offset']:raise ValueError('window exceeds memory ceiling')
        for space,bank,start,end in ranges:
            if (space,bank)==(row['space'],row['bank']) and start<row['start']+length and row['start']<end:raise ValueError('address windows overlap')
        ranges.append((row['space'],row['bank'],row['start'],row['start']+length))
    probe_ids=_rows(case['probes'],32,1)
    for row in case['probes']:
        fields(row,'id address length');address(row['address'],spaces);number(row['length'],1,4096)
        if row['length']>(1<<spaces[row['address']['space']]['address_bits'])-row['address']['offset']:raise ValueError('probe exceeds address width')
    capture_ids=_rows(case['captures'],8)
    for row in case['captures']:
        fields(row,'id capture_id build_id png_sha256 rgb_sha256 source_role region')
        sha(row['capture_id'],32);sha(row['build_id']);sha(row['png_sha256']);sha(row['rgb_sha256']);label(row['source_role'])
        if type(row['region']) is not list or len(row['region'])!=4:raise ValueError('capture region must be x y width height')
        for index,value in enumerate(row['region']):number(value,0 if index<2 else 1,4096)
    _rows(case['links'],128)
    for row in case['links']:
        fields(row,'id probe_id trace_event_id capture_selector_id alignment provenance');provenance(row['provenance'])
        if row['probe_id'] not in probe_ids:raise ValueError('link references unknown probe')
        if row['trace_event_id'] is None and row['capture_selector_id'] is None:raise ValueError('link needs an event or capture')
        if row['trace_event_id'] is not None:label(row['trace_event_id'])
        if row['capture_selector_id'] is not None and row['capture_selector_id'] not in capture_ids:raise ValueError('link references unknown capture')
        fields(row['alignment'],'kind note')
        if row['alignment']['kind'] not in ('unknown','asserted'):raise ValueError('imported links cannot claim observed alignment')
        label(row['alignment']['note'],512,blank=True)
    return {'normalized':case,'sha256':digest}


def validate_debug_trace(trace: dict,normalized_case: dict) -> dict:
    trace,digest=_snapshot(trace,4*1024*1024);case=normalized_case
    fields(trace,'schema_version format source events provenance');number(trace['schema_version'],1,1);provenance(trace['provenance'])
    if trace['format']!='explicit-events-v1':raise ValueError('unsupported explicit trace format')
    fields(trace['source'],'sha256 size');sha(trace['source']['sha256']);number(trace['source']['size'],0,64*1024*1024)
    if trace['source']!={k:case['source'][k] for k in ('sha256','size')} or digest!=case['trace_sha256']:raise ValueError('trace/source identity mismatch')
    event_ids=_rows(trace['events'],2048);spaces={row['id']:row for row in case['spaces']}
    for event in trace['events']:
        fields(event,'id line pc access frame_hint raw provenance');provenance(event['provenance']);number(event['line'],1,(1<<63)-1)
        label(event['raw'],512,blank=True)
        if event['frame_hint'] is not None:number(event['frame_hint'],0,(1<<63)-1)
        if event['pc'] is None and event['access'] is None:raise ValueError('trace event needs a PC or explicit access')
        if event['pc'] is not None:address(event['pc'],spaces)
        if event['access'] is not None:
            access=event['access'];fields(access,'kind address length raw_hex')
            if access['kind'] not in ('read_candidate','write_candidate'):raise ValueError('imports contain candidates, not observed writes')
            address(access['address'],spaces);length=number(access['length'],1,16)
            if length>(1<<spaces[access['address']['space']]['address_bits'])-access['address']['offset']:raise ValueError('access exceeds address width')
            if access['raw_hex'] is not None and (type(access['raw_hex']) is not str or re.fullmatch('[0-9a-f]{'+str(2*length)+'}',access['raw_hex']) is None):raise ValueError('invalid trace byte declaration')
    for link in case['links']:
        if link['trace_event_id'] is not None and link['trace_event_id'] not in event_ids:raise ValueError('link references missing trace event')
    return {'normalized':trace,'sha256':digest}
