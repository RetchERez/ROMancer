from __future__ import annotations

"""Bounded evidence-first autonomous runtime play for ROMancer v9.

This agent does not pretend to understand arbitrary pixels.  It combines exact core
input descriptors, verified game-profile semantics, optional learned visual state labels,
save-state branching, RAM/frame deltas, and a risk-aware planner.  Unknown semantics stay
unknown and cause conservative information-gathering behavior.
"""

from pathlib import Path
from typing import Any
import json

from .frame_analysis import compare_frames
from .game_profiles import load_profile
from .gameplay_beliefs import BeliefLedger
from .gameplay_planner import CandidateAction, choose_action
from .libretro_frontend import LibretroFrontend, BUTTON_IDS
from .playtest import memory_diff
from .state_model import load_state_library, match_state_library
from .util import write_json


CONTEXT_ALIASES={
    "field":"EXPLORATION","exploration":"EXPLORATION","world":"EXPLORATION","overworld":"EXPLORATION",
    "dialogue":"DIALOGUE","text":"DIALOGUE","battle":"COMBAT","combat":"COMBAT",
    "menu":"MAIN_MENU","shop":"SHOP","inventory":"INVENTORY","equipment":"EQUIPMENT","map":"MAP",
    "pause":"PAUSED","title":"TITLE","game_over":"GAME_OVER","results":"RESULTS"
}

INFO_INTENTS={"open_subscreen","menu","map","status","inventory","interact","talk","examine","cancel","back"}
DESTRUCTIVE_INTENTS={"sell","discard","delete","overwrite","abandon","permanent_spend","rare_currency_spend"}


def _normalize_context(ctx:str|None)->str:
    if not ctx: return "UNKNOWN"
    return CONTEXT_ALIASES.get(ctx.lower(),ctx.upper())


def _state_match(frontend:LibretroFrontend, states:list[dict[str,Any]]|None, threshold:int)->dict[str,Any]|None:
    if not states or not frontend.last_frame: return None
    r=match_state_library(states,frontend.last_frame,threshold=threshold,max_results=3)
    best=r.get("best")
    if not best or not best.get("comparable"): return None
    return best


def _profile_actions(profile:dict[str,Any], context:str)->list[tuple[str,list[str]]]:
    controls=profile.get("controls",{})
    candidates=[]
    # exact context first, then common aliases and global
    keys=[context,context.lower()]
    if context=="EXPLORATION": keys += ["field","exploration"]
    elif context=="COMBAT": keys += ["battle","combat"]
    elif context in {"MAIN_MENU","PAUSED","INVENTORY","EQUIPMENT","SHOP","MAP"}: keys += ["menu"]
    elif context=="DIALOGUE": keys += ["dialogue","field"]
    keys += ["global"]
    seen=set()
    for key in keys:
        mapping=controls.get(key,{})
        if not isinstance(mapping,dict): continue
        for intent,buttons in mapping.items():
            if not isinstance(buttons,list) or not buttons: continue
            b=tuple(str(x).lower() for x in buttons)
            sig=(intent,b)
            if sig in seen: continue
            seen.add(sig); candidates.append((str(intent),list(b)))
    return candidates


def _fallback_actions()->list[tuple[str,list[str]]]:
    return [(f"probe_{b}",[b]) for b in ["up","down","left","right","a","b","start","select"]]


def runtime_autoplay(core:str|Path, game:str|Path, out_dir:str|Path, *, profile:str|Path|None=None,
                     states:str|Path|None=None, mode:str="qa", decisions:int=30, boot_frames:int=120,
                     action_frames:int=1, settle_frames:int=5, memory_region:str="system_ram",
                     state_threshold:int=12, system_dir:str|Path|None=None, save_dir:str|Path|None=None,
                     assets_dir:str|Path|None=None, core_options:dict[str,str]|None=None) -> dict[str,Any]:
    out=Path(out_dir); frames=out/"frames"; states_out=out/"states"; out.mkdir(parents=True,exist_ok=True); frames.mkdir(exist_ok=True); states_out.mkdir(exist_ok=True)
    p=load_profile(profile) if profile else None
    library=load_state_library(states) if states else None
    ledger=BeliefLedger()
    decisions_log=[]
    with LibretroFrontend(core,system_dir=system_dir,save_dir=save_dir or out/"runtime_save",assets_dir=assets_dir,core_options=core_options or {}) as f:
        load=f.load_game(game); f.clear_buttons(); f.run_frames(max(0,boot_frames))
        for i in range(1,max(0,decisions)+1):
            if f.shutdown_requested: break
            anchor=f.serialize(); base_frame=f.last_frame; base_mem=f.memory_region(memory_region)
            match=_state_match(f,library,state_threshold)
            match_status=(match or {}).get("status")
            context=_normalize_context((match or {}).get("context"))
            if context=="UNKNOWN" and p:
                # Prefer one profile context only when it explicitly declares a single non-global context.
                cs=[str(x) for x in p.get("contexts",[]) if str(x).lower() not in {"unknown","global"}]
                if len(cs)==1: context=_normalize_context(cs[0])
            semantic=_profile_actions(p,context) if p else []
            action_defs=semantic or _fallback_actions()
            trial_records=[]; candidates=[]; outcome_states={}
            for intent,buttons in action_defs:
                if any(b not in BUTTON_IDS for b in buttons): continue
                # Unknown destructive semantics are never probed automatically.
                destructive=intent.lower() in DESTRUCTIVE_INTENTS
                if destructive: continue
                f.unserialize(anchor); f.clear_buttons(); f.run_frames(1)
                before=f.last_frame or base_frame; mem_before=f.memory_region(memory_region)
                f.run_frames(action_frames,buttons=buttons,release_after=True); f.run_frames(settle_frames)
                after=f.last_frame; mem_after=f.memory_region(memory_region)
                visual=compare_frames(before,after); md=memory_diff(mem_before,mem_after,limit=16)
                changed_ratio=float(visual.get("changed_cell_ratio",0) or 0); mean_delta=float(visual.get("mean_abs_luma_delta",0) or 0)
                effective=changed_ratio>=0.001 or md.get("changed_bytes",0)>0
                # Profile mapping is verified only to the degree the profile says it is. Existing v7 profiles
                # are evidence-authored, so an intent mapping is treated as high confidence, not universal fact.
                claim=f"intent {intent} uses {'+'.join(buttons)}"
                if p:
                    ledger.observe(claim,f"profile:{p.get('id')}",context=context,direct=False,repeated=2,source="game_profile")
                info=0.9 if intent.lower() in INFO_INTENTS or intent.startswith("probe_") else 0.35
                progress=min(1.0,changed_ratio*4 + min(0.5,mean_delta/80.0) + (0.2 if md.get("changed_bytes",0)>0 else 0))
                survival=0.2 if intent.lower() in {"cancel","back","pause","menu"} else 0.0
                reversibility=0.98 if intent.startswith("probe_") or intent.lower() in INFO_INTENTS else 0.8
                risk=0.05 if intent.startswith("probe_") else 0.12
                candidates.append(CandidateAction(name=intent,kind="probe" if intent.startswith("probe_") else "act",context=context,
                                                  progress_value=progress,information_gain=info,survival_value=survival,reversibility=reversibility,
                                                  failure_risk=risk,resource_cost=0.0,required_claims=[claim] if p else [],metadata={"buttons":buttons,"effective":effective}))
                outcome_states[intent]=f.serialize()
                trial_records.append({"intent":intent,"buttons":buttons,"effective":effective,"visual":visual,"memory_changed_bytes":md.get("changed_bytes",0)})
            f.unserialize(anchor)
            uncertainty=0.15 if match and match_status=="verified" else (0.35 if match else 0.8)
            plan=choose_action(candidates,ledger,mode=mode,uncertainty=uncertainty) if candidates else {"selected":None,"ranking":[]}
            selected=plan.get("selected")
            if not selected: break
            name=selected["name"]
            f.unserialize(outcome_states[name])
            if f.last_frame:
                shot=frames/f"{i:04d}_{name}.png"; f.last_frame.save_png(shot)
            else: shot=None
            st=states_out/f"{i:04d}_{name}.state"; st.write_bytes(f.serialize())
            decisions_log.append({"decision":i,"recognized_state":match,"context":context,"uncertainty":uncertainty,
                                  "selected":selected,"trials":trial_records,"screenshot":str(shot) if shot else None,"state":str(st)})
        result={"tool":"ROMancer","version":"9.0.0","feature":"bounded autonomous play","mode":mode,
                "core":load.get("core"),"profile":p.get("id") if p else None,"state_library":str(states) if states else None,
                "decisions_requested":decisions,"decisions_completed":len(decisions_log),"decisions":decisions_log,
                "beliefs":ledger.to_dict(),
                "limits":[
                    "This runtime agent does not OCR or invent objectives from pixels. Semantic state labels require learned signatures or profile evidence.",
                    "Genre conventions are not treated as verified controls or mechanics.",
                    "Unknown destructive actions are not automatically probed.",
                    "Completing a route is not equivalent to QA success; authored assertions and regression scenarios remain required for certification."
                ]}
        write_json(out/"autoplay.json",result)
        return result
