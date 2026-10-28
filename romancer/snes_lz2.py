"""Original bounded LC_LZ2 codec; no upstream implementation is bundled.

Format: https://smw-editor.github.io/docs/smw-rom/compression-methods/
Big-endian absolute repeat indices checked against SMW-Editor/snes-squish
commit0693b469cfb9a4e2ebe9ac0b29ae007741695cad. Encoder uses a bounded greedy
search, not an optimal-size algorithm. A stream location still needs evidence.
"""
from collections import defaultdict,deque
from .asset_schema import number

LIMIT=1024**2

def decode_lz2(data,max_output=LIMIT,*,cancelled=lambda:False):
    number(max_output,1,LIMIT)
    if not isinstance(data,(bytes,bytearray,memoryview)) or not 1<=len(data)<=2*LIMIT:raise ValueError('LC_LZ2 input exceeds its byte budget.')
    pos=0;out=bytearray();commands=0
    def take(count):
        nonlocal pos
        if pos+count>len(data):raise ValueError('LC_LZ2 token is truncated.')
        result=data[pos:pos+count];pos+=count;return result
    while True:
        if commands%256==0 and cancelled():raise KeyboardInterrupt
        head=take(1)[0]
        if head==255:
            if not out:raise ValueError('LC_LZ2 decoded resource is empty.')
            return {'data':bytes(out),'consumed':pos}
        command=head>>5;count=(head&31)+1
        if command==7:command=(head>>2)&7;count=(((head&3)<<8)|take(1)[0])+1
        if command>4:raise ValueError('Unsupported LC_LZ2 command.')
        if len(out)+count>max_output:raise ValueError('LC_LZ2 output exceeds its declared budget.')
        if command==0:out.extend(take(count))
        elif command==1:out.extend(bytes([take(1)[0]])*count)
        elif command==2:
            pair=bytes(take(2));out.extend((pair*((count+1)//2))[:count])
        elif command==3:
            first=take(1)[0];out.extend((first+i)&255 for i in range(count))
        else:
            start=int.from_bytes(take(2),'big')
            if start>=len(out):raise ValueError('LC_LZ2 repeat starts outside decoded history.')
            for i in range(count):out.append(out[start+i])
        commands+=1

def encode_lz2(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=LIMIT:raise ValueError('Encode a nonempty LC_LZ2 resource up to1MiB.')
    output=bytearray();history=defaultdict(lambda:deque(maxlen=24));pos=0
    def header(command,count):
        n=count-1
        return bytes([(command<<5)|n]) if count<=32 else bytes([224|(command<<2)|(n>>8),n&255])
    def options(at):
        stop=min(len(raw),at+1024);choices=[]
        for command,period in ((1,1),(2,2),(3,0)):
            end=at+1
            while end<stop and raw[end]==((raw[at]+end-at)&255 if period==0 else raw[at+(end-at)%period]):end+=1
            count=end-at;cost=len(header(command,count))+(2 if command==2 else 1)
            if count>cost:choices.append((count-cost,count,command,raw[at:at+2] if command==2 else raw[at:at+1]))
        if at+3<=len(raw):
            for old in reversed(history.get(raw[at:at+3],())):
                count=3
                while at+count<stop and raw[old+count]==raw[at+count]:count+=1
                cost=len(header(4,count))+2
                if count>cost:choices.append((count-cost,count,4,old.to_bytes(2,'big')))
        return max(choices,key=lambda c:(c[0],c[1],-c[2])) if choices else None
    def remember(start,end):
        for i in range(start,min(end,65536)):
            if i+3<=len(raw):history[raw[i:i+3]].append(i)
    while pos<len(raw):
        choice=options(pos)
        if choice:
            _,count,command,arg=choice;output.extend(header(command,count));output.extend(arg);remember(pos,pos+count);pos+=count
        else:
            start=pos;pos+=1;remember(start,pos)
            while pos<len(raw) and pos-start<1024 and not options(pos):remember(pos,pos+1);pos+=1
            output.extend(header(0,pos-start));output.extend(raw[start:pos])
    output.append(255);return bytes(output)
