"""Separate original verification parser for exact encoder output.

Uses a preallocated output and explicit token cursors rather than the discovery
decoder. This is implementation diversity, not an external emulator certification.
"""
import hashlib

def _verify_lz2(encoded,expected,cancelled):
    if type(encoded) is not bytes or not 1<=len(encoded)<=2*1024**2 or type(expected) is not bytes or not 1<=len(expected)<=1024**2:raise ValueError('Independent LC_LZ2 inputs exceed their bounds.')
    output=bytearray(len(expected));src=0;dst=0;packets=0
    def get():
        nonlocal src
        if src==len(encoded):raise ValueError('Independent LC_LZ2 input is truncated.')
        b=encoded[src];src+=1;return b
    while True:
        if packets%128==0 and cancelled():raise KeyboardInterrupt
        first=get()
        if first==255:break
        if first>=224:tag=(first//4)%8;length=((first%4)*256)+get()+1
        else:tag=first//32;length=first%32+1
        if tag>4 or dst+length>len(output):raise ValueError('Independent LC_LZ2 command/output extent differs.')
        if tag==0:
            for _ in range(length):output[dst]=get();dst+=1
        elif tag in (1,2,3):
            a=get();b=get() if tag==2 else a
            for i in range(length):output[dst]=(a+i)%256 if tag==3 else (b if tag==2 and i%2 else a);dst+=1
        else:
            origin=get()*256+get()
            if origin>=dst:raise ValueError('Independent LC_LZ2 repeat lacks prior bytes.')
            for i in range(length):output[dst]=output[origin+i];dst+=1
        packets+=1
    if src!=len(encoded) or dst!=len(output) or output!=expected:raise ValueError('Independent LC_LZ2 output differs from the edited resource.')
    return {'verified':True,'decoder':'separate-original-lz2-parser-v1','consumed':src,'decoded_sha256':hashlib.sha256(output).hexdigest(),'external_implementation_certified':False}


def verify_encoded(encoded,codec,expected,*,cancelled=lambda:False):
    if codec=='snes-lz2':return _verify_lz2(encoded,expected,cancelled)
    if type(encoded) is not bytes or type(expected) is not bytes or not 1<=len(expected)<=1024**2 or not 4<=len(encoded)<=2*1024**2:
        raise ValueError('Independent decode input exceeds its bounds.')
    signature={'gba-lz10':16,'gba-rle':48}.get(codec)
    if signature is None or encoded[0]!=signature or int.from_bytes(encoded[1:4],'little')!=len(expected):
        raise ValueError('Independent decode header differs from the edited resource.')
    output=bytearray(len(expected));source=4;destination=0;checks=0
    while destination<len(output):
        if checks%256==0 and cancelled():raise KeyboardInterrupt
        checks+=1
        if source>=len(encoded):raise ValueError('Independent decode found a truncated token.')
        token=encoded[source];source+=1
        if signature==48:
            repeated=bool(token&128);length=(token&127)+(3 if repeated else 1)
            needed=1 if repeated else length
            if source+needed>len(encoded) or destination+length>len(output):raise ValueError('Independent RLE token exceeds its stream or output.')
            if repeated:
                output[destination:destination+length]=bytes([encoded[source]])*length
            else:output[destination:destination+length]=encoded[source:source+length]
            source+=needed;destination+=length
        else:
            for bit in range(8):
                if destination==len(output):break
                if token&(128>>bit):
                    if source+2>len(encoded):raise ValueError('Independent LZ token is truncated.')
                    pair=(encoded[source]<<8)|encoded[source+1];source+=2
                    length=(pair>>12)+3;distance=(pair&4095)+1
                    if distance>destination or destination+length>len(output):raise ValueError('Independent LZ reference exceeds its decoded history.')
                    stop=destination+length
                    while destination<stop:
                        output[destination]=output[destination-distance];destination+=1
                else:
                    if source>=len(encoded):raise ValueError('Independent LZ literal is truncated.')
                    output[destination]=encoded[source];source+=1;destination+=1
    if source!=len(encoded) or output!=expected:raise ValueError('Independent recompression decode differs from the edited resource.')
    return {'verified':True,'decoder':'separate-original-token-parser-v1','consumed':source,
        'decoded_sha256':hashlib.sha256(output).hexdigest(),'external_implementation_certified':False}
