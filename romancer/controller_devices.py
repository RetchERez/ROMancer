"""Bounded core-advertised controller choices; unsupported device classes stay read only."""
import ctypes


class ControllerDescription(ctypes.Structure):
    _fields_=[('desc',ctypes.c_char_p),('id',ctypes.c_uint)]


class ControllerInfo(ctypes.Structure):
    _fields_=[('types',ctypes.POINTER(ControllerDescription)),('num_types',ctypes.c_uint)]


def validate_devices(value):
    if type(value) is not dict or len(value)>4:raise ValueError('controller devices require up to four port choices')
    for port,device in value.items():
        if port not in ('0','1','2','3') or type(device) is not int or not 0<=device<=65535 or device&255 not in (0,1):
            raise ValueError('choose a supported joypad device and port')
    return dict(value)


def read_controller_info(data):
    if not data:return []
    ports=ctypes.cast(data,ctypes.POINTER(ControllerInfo));result=[]
    for port in range(4):
        info=ports[port]
        if not info.types and not info.num_types:break
        if not info.types or not 1<=info.num_types<=32:raise ValueError('invalid advertised controller count')
        choices=[];seen=set()
        for index in range(info.num_types):
            item=info.types[index];identifier=int(item.id)
            if identifier in seen or identifier>65535 or not item.desc:raise ValueError('invalid advertised controller')
            seen.add(identifier);label=item.desc.decode('utf-8',errors='replace')[:160]
            if any(ord(c)<32 for c in label):raise ValueError('invalid advertised controller name')
            choices.append({'id':identifier,'name':label,'selectable':identifier&255 in (0,1)})
        result.append({'port':port,'devices':choices})
    return result


def checked_choices(advertised,requested):
    requested=validate_devices(requested);effective={'0':1,**requested}
    for port,identifier in effective.items():
        info=next((p for p in advertised if p['port']==int(port)),None)
        # The libretro standard joypad is the compatibility default. Explicit
        # subtypes require an actual advertisement from the loaded core.
        if identifier in (0,1):continue
        if info is None or not any(d['id']==identifier and d['selectable'] for d in info['devices']):
            raise ValueError('this core does not advertise the selected controller type')
    return effective
