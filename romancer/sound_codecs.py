"""Bounded literal sample codecs. Hardware mixing/envelopes are not simulated."""
import io,struct,wave
from .asset_schema import number

CODECS=('pcm-u8','pcm-s8','pcm-s16le','pcm-s16be','gb-wave4','nes-dpcm','snes-brr')
MAX_SAMPLES=65536


def decode_sample(raw,codec,initial_level=64):
    if codec not in CODECS or type(raw) is not bytes or not 1<=len(raw)<=65536:raise ValueError('unsupported sample codec or byte budget')
    number(initial_level,0,127)
    if codec=='nes-dpcm' and len(raw)>MAX_SAMPLES//8 or codec=='snes-brr' and len(raw)//9*16>MAX_SAMPLES:raise ValueError('decoded sample exceeds 65536 points')
    if codec=='pcm-u8':values=[(n-128)*256 for n in raw]
    elif codec=='pcm-s8':values=[(n if n<128 else n-256)*256 for n in raw]
    elif codec in ('pcm-s16le','pcm-s16be'):
        if len(raw)%2:raise ValueError('16-bit PCM requires whole samples')
        values=list(struct.unpack(('<' if codec.endswith('le') else '>')+str(len(raw)//2)+'h',raw))
    elif codec=='gb-wave4':
        if len(raw)!=16:raise ValueError('Game Boy wave format is exactly16bytes')
        values=[n*4369-32768 for b in raw for n in (b>>4,b&15)]
    elif codec=='nes-dpcm':
        level=initial_level;values=[]
        for byte in raw:
            for bit in range(8):
                if byte&(1<<bit):level+=2 if level<=125 else 0
                else:level-=2 if level>=2 else 0
                values.append((level-64)*512)
    else:
        if len(raw)%9 or raw[0]&12:raise ValueError('BRR needs whole blocks and a filter0start with known history')
        values=[];p1=p2=0
        for at in range(0,len(raw),9):
            header=raw[at];shift=header>>4;filter_id=(header>>2)&3
            if shift>12:raise ValueError('BRR reserved range is outside supported sample format')
            if bool(header&1)!=(at+9==len(raw)):raise ValueError('BRR end marker must terminate the declared sample')
            for byte in raw[at+1:at+9]:
                for nibble in (byte>>4,byte&15):
                    n=nibble if nibble<8 else nibble-16;v=(n<<shift)>>1
                    if filter_id==1:v+=p1+((-p1)>>4)
                    elif filter_id==2:v+=2*p1+((-3*p1)>>5)-p2+(p2>>4)
                    elif filter_id==3:v+=2*p1+((-13*p1)>>6)-p2+((3*p2)>>4)
                    v=max(-32768,min(32767,v));out=((v*2+32768)&65535)-32768;p2,p1=p1,out//2;values.append(out)
    if len(values)>MAX_SAMPLES:raise ValueError('decoded sample exceeds 65536 points')
    return values


def encode_sample(values,codec,initial_level=64,*,loop=False):
    if codec not in CODECS or type(values) is not list or not 1<=len(values)<=MAX_SAMPLES or any(type(v) is not int or not -32768<=v<=32767 for v in values):raise ValueError('invalid bounded PCM values')
    number(initial_level,0,127)
    if codec=='pcm-u8':return bytes(max(0,min(255,round(v/256)+128)) for v in values)
    if codec=='pcm-s8':return bytes(max(-128,min(127,round(v/256)))&255 for v in values)
    if codec in ('pcm-s16le','pcm-s16be'):return struct.pack(('<' if codec.endswith('le') else '>')+str(len(values))+'h',*values)
    if codec=='gb-wave4':
        if len(values)!=32:raise ValueError('Game Boy wave format requires32samples')
        n=[max(0,min(15,round((v+32768)/4369))) for v in values];return bytes(n[i]<<4|n[i+1] for i in range(0,32,2))
    if codec=='nes-dpcm':
        if len(values)%8:raise ValueError('DPCM encoding requires whole bytes')
        out=bytearray(len(values)//8);level=initial_level
        for i,value in enumerate(values):
            up=level+2 if level<=125 else level;down=level-2 if level>=2 else level
            if abs((up-64)*512-value)<=abs((down-64)*512-value):out[i//8]|=1<<(i%8);level=up
            else:level=down
        return bytes(out)
    if len(values)%16:raise ValueError('BRR encoding requires16-sample blocks')
    out=bytearray()
    for at in range(0,len(values),16):
        block=values[at:at+16];best=None
        for shift in range(1,13):
            n=[max(-8,min(7,round(v/(1<<shift)))) for v in block];error=sum((v-(q<<shift))**2 for v,q in zip(block,n))
            if best is None or error<best[0]:best=(error,shift,n)
        _,shift,n=best;last=at+16==len(values);out.append((shift<<4)|(1 if last else 0)|(2 if last and loop else 0));out.extend(((n[i]&15)<<4)|(n[i+1]&15) for i in range(0,16,2))
    return bytes(out)


def wav_bytes(values,rate):
    number(rate,1000,192000)
    if type(values) is not list or not 1<=len(values)<=1920000 or any(type(v) is not int or not -32768<=v<=32767 for v in values):raise ValueError('WAV sample budget exceeded')
    out=io.BytesIO()
    with wave.open(out,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(struct.pack('<'+str(len(values))+'h',*values))
    return out.getvalue()


def read_wav(raw,rate,capacity):
    number(rate,1000,96000);number(capacity,1,MAX_SAMPLES)
    if type(raw) is not bytes or not 44<=len(raw)<=2*1024**2:raise ValueError('WAV input exceeds byte budget')
    try:
        with wave.open(io.BytesIO(raw),'rb') as w:
            channels,width,source_rate,frames=w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getnframes()
            if channels not in (1,2) or width not in (1,2) or not 1000<=source_rate<=192000 or w.getcomptype()!='NONE' or not 1<=frames<=MAX_SAMPLES:raise ValueError('Use bounded8/16-bit mono/stereo PCM WAV')
            data=w.readframes(frames)
            if len(data)!=frames*channels*width:raise ValueError('WAV payload is truncated')
    except (wave.Error,EOFError,struct.error) as exc:raise ValueError('invalid PCM WAV') from exc
    count=max(1,round(frames*rate/source_rate))
    if count>capacity:raise ValueError('WAV exceeds declared sample capacity; trim it first')
    # WAV limits count frames, including both interleaved channels. ROM sample
    # allocations have a separate byte cap which must not truncate WAV input.
    pcm=list(struct.unpack('<'+str(frames*channels)+'h',data)) if width==2 else [(v-128)*256 for v in data]
    if channels==2:pcm=[round((pcm[i]+pcm[i+1])/2) for i in range(0,len(pcm),2)]
    out=[]
    for i in range(count):
        position=min(frames-1,i*source_rate/rate);a=int(position);fraction=position-a;out.append(round(pcm[a]*(1-fraction)+pcm[min(frames-1,a+1)]*fraction))
    return out+[0]*(capacity-count)
