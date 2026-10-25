"""Explicit system mappings and bounded byte comparisons; no observed bank claim.

References: NESdev NROM; SNESdev Memory_map; GBATEK GBA memory map.
Only the declared windows below resolve. Other cartridge/mapper states refuse.
"""
from pathlib import Path
from .asset_schema import number,fields
from . import workbench_projects as p


def translate(system_id,address,mapping,bank,source_size):
    number(address,0,0xffffffff);number(source_size,1,8*1024**3)
    if type(mapping) is not dict:raise ValueError('declare a mapping')
    if bank is not None:number(bank,0,65535)
    kind=mapping.get('id')
    if system_id=='nes' and kind=='nrom':
        fields(mapping,'id prg_offset prg_size');start=number(mapping['prg_offset'],16,528);length=number(mapping['prg_size'],16384,32768)
        if start not in (16,528) or length not in (16384,32768) or not 0x8000<=address<=0xffff or bank is not None:raise ValueError('NROM requires a fixed16/32KiB PRG window')
        offset=start+(address-0x8000)%length
        if start+length>source_size:raise ValueError('declared PRG exceeds source')
    elif system_id=='nes' and kind=='prg-bank':
        fields(mapping,'id prg_offset bank_size window_start window_size')
        if bank is None:raise ValueError('declare the actual PRG bank; it cannot be inferred')
        start=number(mapping['prg_offset'],0,source_size);unit=number(mapping['bank_size'],1024,32768);window=number(mapping['window_start'],0x6000,0xffff);length=number(mapping['window_size'],1,unit)
        if not window<=address<window+length or window+length>0x10000:raise ValueError('address is outside declared bank window')
        offset=start+bank*unit+address-window
        if start+(bank+1)*unit>source_size:raise ValueError('bank extends outside source')
    elif system_id=='snes' and kind in ('lorom','hirom'):
        fields(mapping,'id copier_header');prefix=number(mapping['copier_header'],0,512)
        if prefix not in (0,512):raise ValueError('copier header must be explicitly0 or512 bytes')
        if bank is not None:
            number(bank,0,255)
            if address>65535 and address>>16!=bank:raise ValueError('address and explicit bank disagree')
            address=(bank<<16)|(address&65535)
        if address>0xffffff:raise ValueError('SNES addresses are24bit')
        selected=address>>16;within=address&65535
        if selected in (0x7e,0x7f):raise ValueError('address is WRAM, not cartridge bytes')
        if kind=='lorom':
            if within<0x8000:raise ValueError('this LoROM resolver covers upper ROM windows only')
            offset=prefix+(selected&0x7f)*32768+(within&32767)
        else:
            if within<0x8000 and not (0x40<=selected<=0x7d or 0xc0<=selected<=0xff):raise ValueError('address is outside a declared HiROM ROM window')
            offset=prefix+(selected&0x3f)*65536+within
    elif system_id=='genesis' and kind=='linear':
        fields(mapping,'id')
        if bank is not None or address>=0x400000:raise ValueError('only the initial4MiB linear cartridge window is supported')
        offset=address
    elif system_id=='gb' and kind=='gb-rom':
        fields(mapping,'id')
        if not 0<=address<0x8000:raise ValueError('address is outside Game Boy ROM windows')
        if address<0x4000:
            if bank not in (None,0):raise ValueError('this fixed bank-zero resolver does not infer MBC1 alternate mode')
            offset=address
        else:
            if bank is None:raise ValueError('declare the actual ROM bank; mapper state cannot be inferred')
            offset=bank*16384+address-0x4000
    elif system_id=='gba' and kind=='rom':
        fields(mapping,'id')
        if bank is not None or not 0x08000000<=address<0x0e000000:raise ValueError('address is outside GBA ROM wait-state windows')
        offset=address&0x1ffffff
    elif system_id=='segacd' and kind=='declared-window':
        fields(mapping,'id cpu_start file_offset length');start=number(mapping['cpu_start'],0,0xffffff);length=number(mapping['length'],1,source_size);file_start=number(mapping['file_offset'],0,source_size)
        if bank is not None or not start<=address<start+length or file_start+length>source_size:raise ValueError('address is outside the explicit loaded-file window')
        offset=file_start+address-start
    else:raise ValueError('unsupported or undeclared system mapping')
    if not 0<=offset<source_size:raise ValueError('mapped offset exceeds the actual source')
    return {'ok':True,'status':'RESOLVED','system_id':system_id,'address':address,'offset':offset,'mapping':mapping,'bank':bank,'bank_state_observed':False,'scope':'declared_address_mapping'}


def inspect_address(project,artifact_id,system_id,address,mapping,bank):
    row=p.artifact(project,artifact_id);p._measure(row['path'],row)
    result=translate(system_id,address,mapping,bank,row['size'])
    with Path(row['path']).open('rb') as stream:stream.seek(result['offset']);raw=stream.read(min(32,row['size']-result['offset']))
    p._measure(row['path'],row)
    return {**result,'artifact_id':artifact_id,'source_sha256':row['sha256'],'hex':raw.hex(),'length':len(raw)}


def compare_bytes(project,left_id,right_id,offset,length):
    number(offset,0,8*1024**3);number(length,1,4096);left=p.artifact(project,left_id);right=p.artifact(project,right_id)
    if offset+length>min(left['size'],right['size']):raise ValueError('comparison range exceeds selected artifacts')
    chunks=[]
    for row in (left,right):
        p._measure(row['path'],row)
        with Path(row['path']).open('rb') as stream:stream.seek(offset);chunks.append(stream.read(length))
    for row in (left,right):p._measure(row['path'],row)
    differences=[{'offset':offset+i,'before':f'{a:02x}','after':f'{b:02x}'} for i,(a,b) in enumerate(zip(*chunks)) if a!=b]
    return {'ok':True,'status':'CHANGED' if differences else 'EQUAL','left_sha256':left['sha256'],'right_sha256':right['sha256'],'offset':offset,'length':length,'differences':differences,'scope':'selected_byte_range'}
