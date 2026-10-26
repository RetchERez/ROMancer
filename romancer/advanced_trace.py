from __future__ import annotations
from collections import Counter

from typing import Any

from .trace_parser import parse_trace
from .util import write_json

CALLS={'JSR','JSL','BSR','CALL'}; RETURNS={'RTS','RTL','RTI','RET','RTE'}; BRANCH_PREFIX=('B','JMP','BRA','DB')

def _norm(v:str|None)->str:
    return (v or '').upper().replace('$','').replace('0X','').replace(':','')

def _events(trace:str, fmt='auto'):
    return parse_trace(trace, trace_format=fmt).get('events',[])

def trace_compare(a:str,b:str,format_a='auto',format_b='auto',out:str|None=None)->dict[str,Any]:
    ea=_events(a,format_a); eb=_events(b,format_b)
    ca=Counter(e.get('mnemonic') for e in ea if e.get('mnemonic')); cb=Counter(e.get('mnemonic') for e in eb if e.get('mnemonic'))
    pa=Counter(e.get('pc') for e in ea if e.get('pc')); pb=Counter(e.get('pc') for e in eb if e.get('pc'))
    result={'tool':'ROMancer','feature':'advanced trace compare','a':a,'b':b,'events_a':len(ea),'events_b':len(eb),
            'mnemonic_delta':{k:cb.get(k,0)-ca.get(k,0) for k in sorted(set(ca)|set(cb))},
            'top_pc_added':[{'pc':pc,'delta':n} for pc,n in (pb-pa).most_common(25)],
            'top_pc_removed':[{'pc':pc,'delta':n} for pc,n in (pa-pb).most_common(25)],
            'warnings':['Trace comparison is structural. It does not prove gameplay correctness.']}
    if out: write_json(out,result)
    return result

def trace_hot_pc(trace:str,fmt='auto',limit:int=25,out:str|None=None)->dict[str,Any]:
    ev=_events(trace,fmt); c=Counter(e.get('pc') for e in ev if e.get('pc'))
    result={'tool':'ROMancer','feature':'hot PC report','trace':trace,'event_count':len(ev),'hot_pcs':[{'pc':pc,'hits':n} for pc,n in c.most_common(limit)]}
    if out: write_json(out,result)
    return result

def trace_memory_flow(trace:str,addr:str,fmt='auto',window:int=80,out:str|None=None)->dict[str,Any]:
    target=_norm(addr); ev=_events(trace,fmt); hits=[]
    for i,e in enumerate(ev):
        ma=e.get('memory_access') or {}
        ma_addr=_norm(ma.get('address'))
        if target and ma_addr and (target.endswith(ma_addr) or ma_addr.endswith(target)):
            before=ev[max(0,i-window):i]; after=ev[i+1:i+1+min(window,20)]
            hits.append({'index':i,'line':e.get('line'),'pc':e.get('pc'),'mnemonic':e.get('mnemonic'),'access':ma,
                         'recent_loads':[x for x in before if (x.get('mnemonic') or '').upper() in {'LDA','LDX','LDY','MOVE','MOVE.B','MOVE.W','MOVE.L','LEA'}][-12:],
                         'following_writes':[x for x in after if (x.get('memory_access') or {}).get('kind','').startswith('write')][:12]})
    result={'tool':'ROMancer','feature':'memory flow','trace':trace,'address':addr,'hit_count':len(hits),'hits':hits[:50],
            'warnings':['Use this to guide debugger work. Confirm register width, bank, and active mapper state before patching.']}
    if out: write_json(out,result)
    return result

def trace_register_flow(trace:str,register:str,fmt='auto',around_addr:str|None=None,window:int=80,out:str|None=None)->dict[str,Any]:
    reg=register.upper(); ev=_events(trace,fmt); focus=[]
    if around_addr:
        target=_norm(around_addr)
        indexes=[]
        for i,e in enumerate(ev):
            ma_addr=_norm((e.get('memory_access') or {}).get('address'))
            if ma_addr and (target.endswith(ma_addr) or ma_addr.endswith(target)):
                indexes.append(i)
    else:
        indexes=list(range(len(ev)))[:1]
    for idx in indexes[:20]:
        lo=max(0,idx-window); hi=min(len(ev),idx+window+1)
        changes=[]
        last=None
        for e in ev[lo:hi]:
            val=(e.get('registers') or {}).get(reg)
            if val is not None and val!=last:
                changes.append({'line':e.get('line'),'pc':e.get('pc'),'mnemonic':e.get('mnemonic'),'value':val,'raw':e.get('raw')})
                last=val
        focus.append({'around_event_index':idx,'changes':changes[:80]})
    result={'tool':'ROMancer','feature':'register flow','trace':trace,'register':reg,'around_addr':around_addr,'windows':focus}
    if out: write_json(out,result)
    return result

def trace_call_tree(trace:str,fmt='auto',around_line:int|None=None,window:int=400,out:str|None=None)->dict[str,Any]:
    ev=_events(trace,fmt)
    if around_line:
        idx=next((i for i,e in enumerate(ev) if e.get('line')>=around_line),0); ev=ev[max(0,idx-window):idx+window]
    stack=[]; nodes=[]
    for e in ev:
        m=(e.get('mnemonic') or '').upper(); ops=e.get('operands') or ''
        if m in CALLS:
            nodes.append({'depth':len(stack),'line':e.get('line'),'pc':e.get('pc'),'call':m,'target':ops})
            stack.append(e.get('pc'))
        elif m in RETURNS and stack:
            nodes.append({'depth':max(0,len(stack)-1),'line':e.get('line'),'pc':e.get('pc'),'return':m})
            stack.pop()
    result={'tool':'ROMancer','feature':'call tree candidate','trace':trace,'nodes':nodes[:500],'warnings':['Call tree is inferred from trace mnemonics only. Indirect jumps and bank changes may need manual confirmation.']}
    if out: write_json(out,result)
    return result

def trace_loop_detect(trace:str,fmt='auto',limit:int=50,out:str|None=None)->dict[str,Any]:
    ev=_events(trace,fmt); pcs=[e.get('pc') for e in ev if e.get('pc')]
    c=Counter(pcs); loops=[]
    for pc,n in c.most_common(limit):
        if n>=3:
            lines=[e.get('line') for e in ev if e.get('pc')==pc][:20]
            loops.append({'pc':pc,'hits':n,'sample_lines':lines})
    result={'tool':'ROMancer','feature':'loop detector','trace':trace,'candidates':loops,'warnings':['High PC hit counts may be loops, waits, polling, or normal hot routines.']}
    if out: write_json(out,result)
    return result
