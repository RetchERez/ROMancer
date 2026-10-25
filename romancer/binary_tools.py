"""Bounded binary comparisons with complete counts and limited range details."""
from pathlib import Path
from . import workbench_projects as p
from .asset_schema import number


def compare_files(left,right,*,max_ranges=64,cancelled=lambda:False):
    number(max_ranges,1,256);a=p._measure(left,cancelled=cancelled);b=p._measure(right,cancelled=cancelled)
    ranges=[];start=None;end=0;changed=0;total_ranges=0;offset=0
    with Path(left).open('rb') as first,Path(right).open('rb') as second:
        while True:
            if cancelled():raise KeyboardInterrupt
            x=first.read(65536);y=second.read(65536)
            if not x and not y:break
            for index in range(max(len(x),len(y))):
                differs=index>=len(x) or index>=len(y) or x[index]!=y[index]
                if differs:
                    changed+=1
                    if start is None:start=offset+index
                    end=offset+index+1
                elif start is not None:
                    total_ranges+=1
                    if len(ranges)<max_ranges:ranges.append({'offset':start,'length':end-start})
                    start=None
            offset+=max(len(x),len(y))
    if start is not None:
        total_ranges+=1
        if len(ranges)<max_ranges:ranges.append({'offset':start,'length':end-start})
    p._measure(left,a,cancelled=cancelled);p._measure(right,b,cancelled=cancelled)
    return {'changed_bytes':changed,'ranges':ranges,'range_count':total_ranges,
            'ranges_truncated':total_ranges>len(ranges),'original_size':a['size'],'target_size':b['size']}
