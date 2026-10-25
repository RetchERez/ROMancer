import hashlib
import json
from copy import deepcopy

P={'origin':'synthetic_fixture','note':'literal original fixture','reference':None}


def debug_fixture():
    raw=bytes(range(32))
    address=lambda space,bank,offset:{'space':space,'bank':bank,'offset':offset}
    trace={'schema_version':1,'format':'explicit-events-v1','source':{'sha256':hashlib.sha256(raw).hexdigest(),'size':32},
           'events':[{'id':name,'line':index+1,'pc':None,'access':{'kind':'read_candidate','address':address(space,bank,offset),'length':1,'raw_hex':value},
                      'frame_hint':None,'raw':'declared import','provenance':deepcopy(P)}
                     for index,(name,space,bank,offset,value) in enumerate([
                         ('bank1','cpu',1,16,'00'),('bank2','cpu',2,16,'08'),('different-offset','cpu',1,272,'00'),('ram','ram',None,8192,'08')])],
           'provenance':deepcopy(P)}
    case={'schema_version':1,'id':'toy-fault','version':'1','symptom':'Declared byte discrepancy','build_id':'0'*64,
          'source':{'role':'resource',**trace['source']},'trace_sha256':hashlib.sha256(json.dumps(trace,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest(),
          'spaces':[{'id':'cpu','address_bits':16,'bank_bits':8},{'id':'ram','address_bits':16,'bank_bits':0}],
          'windows':[{'id':name,'space':space,'bank':bank,'start':start,'length':length,'file_offset':offset,'memory':memory,'provenance':deepcopy(P)}
                     for name,space,bank,start,length,offset,memory in [
                         ('first','cpu',1,16,8,0,None),('second','cpu',2,16,8,8,None),('ram-view','ram',None,8192,4,8,{'region':2,'offset':0})]],
          'probes':[{'id':name,'address':address(space,bank,offset),'length':1} for name,space,bank,offset in
                    [('bank1','cpu',1,16),('bank2','cpu',2,16),('unknown','cpu',None,16),('cursor','ram',None,8192)]],
          'captures':[],'links':[],'provenance':deepcopy(P)}
    return {'raw':raw,'case':case,'trace':trace}
