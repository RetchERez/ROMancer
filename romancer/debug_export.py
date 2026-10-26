from __future__ import annotations
from pathlib import Path
from typing import Any


def export_debug_script(backend:str,system:str,addr:str,access:str='write',out:str|None=None)->dict[str,Any]:
    b=backend.lower(); lines=[]; kind='checklist'
    if b in {'blastem','blastem-gtk'}:
        kind='blastem command note'; lines=['# BlastEm debugger candidate commands',f'# Target {access} at {addr}','# Uses BlastEm documented top-level debugger command names; verify local build help for context/options.','breakpoint '+addr if access=='execute' else f'watchpoint {addr}']
    elif b in {'mesen','mesen2','mesen-s'}:
        kind='mesen lua/checklist'; lines=[f'-- Mesen/Mesen-S helper notes for {system}',f'-- Add a {access} breakpoint at {addr} in the debugger UI.','-- Enable trace logging shortly before reproducing the event.']
    elif b=='bsnes-plus':
        kind='bsnes-plus checklist'; lines=[f'# bsnes-plus target: {addr}',f'# Add data breakpoint manually: access={access}', '# Start CPU trace logger, reproduce event, stop after hit.']
    else:
        lines=[f'Backend {backend}: add {access} breakpoint/watchpoint at {addr}.']
    text='\n'.join(lines)+'\n'
    if out: Path(out).parent.mkdir(parents=True,exist_ok=True); Path(out).write_text(text,encoding='utf-8')
    return {'tool':'ROMancer','feature':'export debug script','backend':backend,'system':system,'addr':addr,'access':access,'kind':kind,'out':out,'text':text,
            'warnings':['Script exports are conservative helpers. Confirm exact backend syntax in the emulator debugger.']}
