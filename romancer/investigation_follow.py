"""Explain authenticated captures without inventing data-flow edges."""
from .asset_schema import number


def follow_capture(report,resources,size,*,trusted,cancelled=lambda:False):
    events=report.get('events',[])
    if type(events) is not list or len(events)>2000:raise ValueError('Access capture exceeds its bounded event budget.')
    writers={};reads={};unmapped=0
    def offset(value):
        return None if value is None else number(value,0,size-1)
    def overlaps(at):
        return [{k:r[k] for k in ('name','kind','editor','offset','length')} for r in resources if r['offset']<=at<r['offset']+r['length']][:8]
    for event in events:
        if cancelled():raise KeyboardInterrupt
        if event.get('kind')=='write':
            context=event.get('execution_context') or {};at=offset(context.get('file_offset'))
            if at is None:unmapped+=1;continue
            key=(at,context.get('pc'));row=writers.setdefault(key,{'file_offset':at,'cpu_pc':key[1],
                'sampled_writes':0,'addresses':set(),'first_event_id':event.get('id'),
                'resources':overlaps(at),'scope':'Mapped writer instruction context; not the edited gameplay value.'})
            row['sampled_writes']+=1;row['addresses'].add(event['address'])
        elif event.get('kind')=='read':
            at=offset(event.get('file_offset'))
            if at is None:continue
            row=reads.setdefault(at,{'file_offset':at,'sampled_reads':0,'resources':overlaps(at),
                'first_event_id':event.get('id'),'scope':'Observed ROM read; no causal link to a particular write established.'})
            row['sampled_reads']+=1
    ordered=sorted(writers.values(),key=lambda r:(-r['sampled_writes'],r['file_offset']))
    omitted=report.get('omitted_events',0);partial=bool(omitted or report.get('status')!='CAPTURED' or not report.get('route_complete'))
    steps=[]
    if not trusted:steps.append('Capture a fresh replay before treating these historical observations as current evidence.')
    if partial:steps.append('Narrow the watch or recording window to obtain a complete replay capture.')
    if ordered:steps.append('Inspect a mapped writer instruction. Its code location is distinct from the ROM data it may read.')
    if reads:steps.append('Inspect a mapped source read, preview its bytes and define a resource after checking its format.')
    if not reads:steps.append('Capture reads in a focused replay window. No source read was mapped in this sample.')
    if unmapped:steps.append('Some writers are unmapped. Check the native address and observed bank; a pattern candidate is not a confirmed mapping.')
    return {'ok':True,'status':'HISTORICAL' if not trusted else 'PARTIAL' if partial else 'OBSERVED',
        'writers':[{**r,'addresses':sorted(r['addresses'])[:32]} for r in ordered[:128]],
        'source_reads':sorted(reads.values(),key=lambda r:(-r['sampled_reads'],r['file_offset']))[:128],
        'unmapped_write_events':unmapped,'next_steps':steps,
        'coverage':{'access_events':len(events),'writer_locations':len(writers),'read_locations':len(reads),
            'partial':partial,'omitted_events':omitted,'summary_truncated':len(writers)>128 or len(reads)>128},
        'runtime_trusted':trusted,'causation_proven':False,'write_authorized':False,
        'scope':'Mapped writes and source reads are separate observations. Proximity and execution context do not prove a source-to-value dependency.'}
