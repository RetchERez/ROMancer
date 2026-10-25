"""Original, nonbootable NES system fixture using regular project/edit services."""
from pathlib import Path
import uuid
from .workbench_projects import create_project,register_source,read_project,write_json
from .system_resources import describe_nes_chr


def make_nes_fixture()->bytes:
    header=bytearray(16);header[:4]=b'NES\x1a';header[4]=1;header[5]=1
    prg=bytearray(16384);prg[:32]=b'ROMancer original system fixture'.ljust(32,b' ')
    chr_data=bytearray(8192)
    shape=bytes.fromhex('8142241818244281')
    for tile in range(512):
        chr_data[tile*16:tile*16+8]=shape
        if tile%4>=2:chr_data[tile*16+8:tile*16+16]=shape
    return bytes(header+prg+chr_data)


def make_system_fixtures()->dict:
    """Original structural headers, explicitly not bootable system programs."""
    snes=bytearray(32768);snes[0x7fc0:0x7fd5]=b'ROMANCER SYSTEM TEST'.ljust(21,b' ')
    snes[0x7fd5]=0x20;snes[0x7fd7]=5;snes[0x7fdc:0x7fe0]=b'\xff\xff\x00\x00'
    genesis=bytearray(1024);genesis[0x100:0x110]=b'SEGA MEGA DRIVE '
    genesis[0x1a4:0x1a8]=(len(genesis)-1).to_bytes(4,'big')
    gba=bytearray(1024);gba[0xa0:0xac]=b'ROMANCERTEST';gba[0xac:0xb0]=b'TEST';gba[0xb0:0xb2]=b'00';gba[0xb2]=0x96
    gba[0xbd]=(-sum(gba[0xa0:0xbd])-0x19)&255
    from .boot_fixtures import make_boot_fixture
    return {'nes':make_nes_fixture(),'snes':bytes(snes),'genesis':bytes(genesis),'gb':make_boot_fixture('gb')['data'],'gba':bytes(gba)}


def create_nes_demo(root:Path,incoming:Path)->dict:
    project=Path(create_project(root,'NES • system workshop')['path'])
    fixture=Path(incoming)/(uuid.uuid4().hex+'.nes');fixture.write_bytes(make_nes_fixture())
    try:source=register_source(project,fixture,None)
    finally:fixture.unlink(missing_ok=True)
    described=describe_nes_chr(Path(source['path']),expected_sha256=source['sha256'])
    if not described['ok']:raise ValueError(described['error'])
    value=read_project(project);value.update(demo=True,demo_type='nes-system')
    value['sources'][0]['name']='Original NES system fixture.nes'
    value['sources'][0]['descriptors']={'assets':described['schema']}
    write_json(project/'project.json',value)
    return {**value,'ok':True,'status':'CREATED','path':str(project),
        'fixture_note':'Original structural/graphics fixture. Not a bootable game or native runtime compatibility test.'}


def create_system_demo(root,incoming,system_id):
    from .boot_fixtures import make_boot_fixture
    from .resource_forms import graphics_schema
    labels={'nes':'NES','snes':'SNES','genesis':'Genesis','gb':'Game Boy','gba':'GBA'}
    fixture=make_boot_fixture(system_id);project=Path(create_project(root,labels[system_id]+' workshop')['path'])
    path=Path(incoming)/(uuid.uuid4().hex+fixture['suffix']);path.write_bytes(fixture['data'])
    try:source=register_source(project,path,None)
    finally:path.unlink(missing_ok=True)
    config={'system_id':system_id,'offset':fixture['graphics_offset'],'count':1}
    if 'palette_offset' in fixture:config['palette_offset']=fixture['palette_offset']
    schema=graphics_schema(Path(source['path']),source['sha256'],config)
    value=read_project(project);value.update(demo=True,demo_type='system-workshop',demo_system=system_id)
    value['sources'][0]['name']='Original '+labels[system_id]+' program'+fixture['suffix']
    value['sources'][0]['descriptors']={'assets':schema};write_json(project/'project.json',value)
    return {**read_project(project),'ok':True,'status':'CREATED','path':str(project),
        'fixture_note':'Original minimal drawing program. Native support is measured separately for each configured core.'}
