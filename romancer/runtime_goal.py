from __future__ import annotations

"""Bounded save-state search toward a learned visual target for ROMancer v7."""

from pathlib import Path
from typing import Any

from .frame_analysis import frame_signature
from .libretro_frontend import BUTTON_IDS, LibretroFrontend
from .state_model import compare_state_signature
from .util import write_json


def _key(frontend: LibretroFrontend) -> str | None:
    if frontend.last_frame is None:
        return None
    return str(frame_signature(frontend.last_frame,16,14)["thumbnail"]["sha256"])


def _score(comp: dict[str,Any]) -> float:
    if not comp.get("comparable"):
        return 1e12
    return float(comp.get("mean_abs_luma_delta",1e9)) + 50.0 * float(comp.get("changed_cell_ratio",1.0))


def goal_search(frontend: LibretroFrontend, target: dict[str,Any], out_dir: str|Path, *, actions: list[str] | None=None, boot_frames: int=120, action_frames: int=1, settle_frames: int=3, max_depth: int=12, beam_width: int=8, success_mean_delta: float=1.0, success_changed_ratio: float=0.01) -> dict[str,Any]:
    """Search bounded input sequences for a frame resembling a captured target.

    This is objective-directed visual search. It does not infer which story objective the
    target represents. The target's semantic label must come from the supplied signature.
    """
    out=Path(out_dir); (out/"frames").mkdir(parents=True,exist_ok=True); (out/"states").mkdir(parents=True,exist_ok=True)
    actions=[a.lower() for a in (actions or ["up","down","left","right","a","b","x","y","start"])]
    bad=[a for a in actions if a not in BUTTON_IDS]
    if bad: raise ValueError(f"Unknown RetroPad actions: {bad}")
    if max_depth < 0 or beam_width <= 0: raise ValueError("max_depth must be >=0 and beam_width >0")

    frontend.clear_buttons(); frontend.run_frames(max(0,boot_frames))
    root_state=frontend.serialize(); root_comp=compare_state_signature(target,frontend.last_frame)
    root={"state":root_state,"sequence":[],"score":_score(root_comp),"comparison":root_comp,"key":_key(frontend)}
    best=root; frontier=[root]; visited={root["key"]:0} if root["key"] else {}
    levels=[]; success=None

    def reached(comp):
        return bool(comp.get("comparable") and float(comp.get("mean_abs_luma_delta",1e9)) <= success_mean_delta and float(comp.get("changed_cell_ratio",1.0)) <= success_changed_ratio)

    if reached(root_comp): success=root
    for depth in range(1,max_depth+1):
        if success is not None: break
        candidates=[]; level_trials=[]
        for node in frontier:
            for action in actions:
                frontend.unserialize(node["state"]); frontend.clear_buttons(); frontend.run_frames(1)
                frontend.run_frames(action_frames,buttons=[action],release_after=True)
                if settle_frames: frontend.clear_buttons(); frontend.run_frames(settle_frames)
                state=frontend.serialize(); comp=compare_state_signature(target,frontend.last_frame); score=_score(comp); key=_key(frontend)
                sequence=node["sequence"]+[action]
                prior=visited.get(key) if key else None
                novel=prior is None
                trial={"depth":depth,"action":action,"sequence":sequence,"score":round(score,6),"frame_key":key,"novel":novel,"comparison":comp}
                level_trials.append(trial)
                candidate={"state":state,"sequence":sequence,"score":score,"comparison":comp,"key":key}
                if score < best["score"]: best=candidate
                if reached(comp): success=candidate; best=candidate; break
                if key is None or novel or depth < int(prior):
                    if key: visited[key]=depth
                    candidates.append(candidate)
            if success is not None: break
        level_trials.sort(key=lambda x:x["score"])
        levels.append({"depth":depth,"trials":level_trials[:max(beam_width*len(actions),beam_width)],"candidate_count":len(candidates)})
        if success is not None: break
        candidates.sort(key=lambda x:x["score"])
        frontier=candidates[:beam_width]
        if not frontier: break

    chosen=success or best
    frontend.unserialize(chosen["state"]); frontend.clear_buttons(); frontend.run_frames(1)
    screenshot=None
    if frontend.last_frame:
        screenshot=out/"frames"/("goal_reached.png" if success else "best_found.png"); frontend.last_frame.save_png(screenshot)
    state_path=out/"states"/("goal_reached.state" if success else "best_found.state"); state_path.write_bytes(chosen["state"])
    result={
        "tool":"ROMancer","version":"7.0.0","feature":"visual goal search","goal_reached":success is not None,
        "target":{"name":target.get("name"),"context":target.get("context"),"status":target.get("status")},
        "sequence":chosen["sequence"],"depth":len(chosen["sequence"]),"best_score":round(float(chosen["score"]),6),"comparison":chosen["comparison"],
        "actions":actions,"action_frames":action_frames,"settle_frames":settle_frames,"max_depth":max_depth,"beam_width":beam_width,
        "success_thresholds":{"mean_abs_luma_delta":success_mean_delta,"changed_cell_ratio":success_changed_ratio},
        "unique_visual_states":len(visited),"levels":levels,"screenshot":str(screenshot) if screenshot else None,"state":str(state_path),
        "limits":[
            "The agent searches toward a supplied observable visual target; it does not infer the story meaning of that target.",
            "Beam search is bounded and can miss valid paths outside the retained frontier or paths requiring different action durations.",
            "Dynamic animation, camera motion, timing mechanics, and visually similar states can reduce target discrimination.",
        ],
    }
    write_json(out/"goal_search.json",result)
    return result
