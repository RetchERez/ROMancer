from __future__ import annotations

"""Controlled input discovery and conservative novelty exploration for ROMancer v7."""

import hashlib

from pathlib import Path
from typing import Any

from .frame_analysis import compare_frames, thumbnail_luma
from .libretro_frontend import BUTTON_IDS, LibretroFrontend
from .playtest import memory_diff
from .util import write_json

DEFAULT_DISCOVERY_BUTTONS = ["up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "start", "select"]
DEFAULT_EXPLORATION_ACTIONS = ["up", "down", "left", "right", "a", "b", "start"]


def _frame_key(frontend: LibretroFrontend) -> str | None:
    fr = frontend.last_frame
    if not fr:
        return None
    return hashlib.sha256(thumbnail_luma(fr, 24, 20)).hexdigest()


def discover_controls(frontend: LibretroFrontend, out_dir: str | Path, *, buttons: list[str] | None = None, boot_frames: int = 120, hold_frames: int = 2, settle_frames: int = 8, long_hold_frames: int = 30, memory_region: str = "system_ram") -> dict[str, Any]:
    """Probe each standardized joypad input from the same save-state anchor.

    Results prove only observable effect/no-effect at the current game state.  They do not
    globally assign semantic meanings such as "talk" or "menu" without profile evidence.
    """
    out_dir = Path(out_dir); frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    buttons = [b.lower() for b in (buttons or DEFAULT_DISCOVERY_BUTTONS)]
    unknown = [b for b in buttons if b not in BUTTON_IDS]
    if unknown:
        raise ValueError(f"Unknown buttons: {unknown}")
    frontend.clear_buttons(); frontend.run_frames(max(0, boot_frames))
    anchor = frontend.serialize()
    baseline_frame = frontend.last_frame
    frontend.memory_region(memory_region)
    if baseline_frame:
        baseline_frame.save_png(frames_dir / "000_baseline.png")
    trials = []
    for order, button in enumerate(buttons, start=1):
        frontend.unserialize(anchor); frontend.clear_buttons()
        frontend.run_frames(1)
        before = frontend.last_frame
        mem_before = frontend.memory_region(memory_region)
        frontend.tap([button], hold_frames=hold_frames, settle_frames=settle_frames)
        after_tap = frontend.last_frame
        mem_tap = frontend.memory_region(memory_region)
        tap_visual = compare_frames(before, after_tap)
        tap_memory = memory_diff(mem_before, mem_tap, limit=30)
        tap_path = None
        if after_tap:
            tap_path = frames_dir / f"{order:03d}_{button}_tap.png"; after_tap.save_png(tap_path)

        # Direction buttons get a second long-hold experiment. This can distinguish a
        # one-shot menu reaction from sustained field movement without claiming either.
        long_visual = None; long_memory = None; long_path = None
        if button in {"up", "down", "left", "right"} and long_hold_frames > 0:
            frontend.unserialize(anchor); frontend.clear_buttons(); frontend.run_frames(1)
            long_before = frontend.last_frame
            long_mem_before = frontend.memory_region(memory_region)
            frontend.run_frames(long_hold_frames, buttons=[button], release_after=True)
            frontend.run_frames(settle_frames)
            long_after = frontend.last_frame
            long_mem_after = frontend.memory_region(memory_region)
            long_visual = compare_frames(long_before, long_after)
            long_memory = memory_diff(long_mem_before, long_mem_after, limit=30)
            if long_after:
                long_path = frames_dir / f"{order:03d}_{button}_hold.png"; long_after.save_png(long_path)

        visual_effect = float(tap_visual.get("changed_cell_ratio", 0)) >= 0.002 or (long_visual and float(long_visual.get("changed_cell_ratio", 0)) >= 0.002)
        memory_effect = tap_memory["changed_bytes"] > 0 or (long_memory and long_memory["changed_bytes"] > 0)
        trials.append({
            "button": button,
            "observable_effect": bool(visual_effect or memory_effect),
            "visual_effect": bool(visual_effect), "memory_effect": bool(memory_effect),
            "tap": {"visual": tap_visual, "memory_changed_bytes": tap_memory["changed_bytes"], "screenshot": str(tap_path) if tap_path else None},
            "long_hold": None if long_visual is None else {"frames": long_hold_frames, "visual": long_visual, "memory_changed_bytes": long_memory["changed_bytes"], "screenshot": str(long_path) if long_path else None},
        })
    frontend.unserialize(anchor)
    result = {
        "tool": "ROMancer", "version": "7.0.0", "feature": "control discovery",
        "core": frontend.core_info().__dict__, "memory_region": memory_region,
        "anchor_state_supported": True, "buttons_tested": len(trials), "trials": trials,
        "effective_buttons_at_anchor": [t["button"] for t in trials if t["observable_effect"]],
        "direction_buttons_with_sustained_effect": [t["button"] for t in trials if t["button"] in {"up","down","left","right"} and t.get("long_hold") and (float(t["long_hold"]["visual"].get("changed_cell_ratio",0)) >= .002 or t["long_hold"]["memory_changed_bytes"] > 0)],
        "limits": [
            "A button with no effect at this anchor may be meaningful elsewhere in the game.",
            "An observable effect does not by itself identify the semantic action.",
            "Memory offsets are relative to the core-exposed region unless independently mapped to CPU addresses.",
        ],
    }
    write_json(out_dir / "control_discovery.json", result)
    return result


def novelty_explore(frontend: LibretroFrontend, out_dir: str | Path, *, decisions: int = 40, candidate_actions: list[str] | None = None, action_frames: int = 10, settle_frames: int = 4, boot_frames: int = 120, memory_region: str = "system_ram", save_every: int = 1) -> dict[str, Any]:
    """Explore an unknown game by choosing observable novel outcomes.

    This is a QA exploration policy, not a promise to solve arbitrary games. Each decision
    branches from an exact save state, tries candidate inputs, scores visual novelty and RAM
    change, then restores the selected outcome. The resulting graph is reproducible.
    """
    out_dir = Path(out_dir); frames_dir = out_dir / "frames"; states_dir = out_dir / "states"
    frames_dir.mkdir(parents=True, exist_ok=True); states_dir.mkdir(parents=True, exist_ok=True)
    actions = [a.lower() for a in (candidate_actions or DEFAULT_EXPLORATION_ACTIONS)]
    for a in actions:
        if a not in BUTTON_IDS:
            raise ValueError(f"Unknown action button {a}")
    frontend.clear_buttons(); frontend.run_frames(max(0, boot_frames))
    # Fail early and honestly if the core cannot branch.
    frontend.serialize()
    visited: dict[str, int] = {}
    nodes = []
    edges = []
    k = _frame_key(frontend)
    if k: visited[k] = 1
    if frontend.last_frame:
        frontend.last_frame.save_png(frames_dir / "0000_start.png")
    for decision in range(1, max(0, decisions) + 1):
        anchor = frontend.serialize()
        anchor_frame = frontend.last_frame
        anchor_mem = frontend.memory_region(memory_region)
        anchor_key = _frame_key(frontend)
        trials = []
        best = None
        for action in actions:
            frontend.unserialize(anchor); frontend.clear_buttons(); frontend.run_frames(1)
            before = frontend.last_frame or anchor_frame
            frontend.run_frames(action_frames, buttons=[action], release_after=True)
            frontend.run_frames(settle_frames)
            after = frontend.last_frame
            visual = compare_frames(before, after)
            mem_after = frontend.memory_region(memory_region)
            mdiff = memory_diff(anchor_mem, mem_after, limit=10)
            key = _frame_key(frontend)
            seen = visited.get(key or "", 0)
            visual_ratio = float(visual.get("changed_cell_ratio", 0.0))
            visual_mean = float(visual.get("mean_abs_luma_delta", 0.0))
            # Primary objective is novelty. Secondary evidence is visible change, then RAM.
            novelty_bonus = 100.0 if key and seen == 0 else (10.0 / (1 + seen) if key else 0.0)
            score = novelty_bonus + visual_ratio * 25.0 + min(10.0, visual_mean / 5.0) + min(5.0, mdiff["changed_bytes"] / 500.0)
            effective = visual_ratio >= 0.001 or mdiff["changed_bytes"] > 0
            outcome_state = frontend.serialize()
            trial = {"action": action, "score": round(score, 6), "effective": effective, "frame_key": key, "visited_count": seen, "visual": visual, "memory_changed_bytes": mdiff["changed_bytes"]}
            trials.append(trial)
            if effective and (best is None or score > best[0]):
                best = (score, action, outcome_state, key, trial)
        if best is None:
            frontend.unserialize(anchor)
            nodes.append({"decision": decision, "frame_key": anchor_key, "status": "no_effective_candidate", "trials": trials})
            break
        score, action, outcome_state, key, selected_trial = best
        frontend.unserialize(outcome_state)
        if key:
            visited[key] = visited.get(key, 0) + 1
        screenshot = None; state_path = None
        if frontend.last_frame and (decision % max(1, save_every) == 0):
            screenshot = frames_dir / f"{decision:04d}_{action}.png"; frontend.last_frame.save_png(screenshot)
        if decision % max(1, save_every) == 0:
            state_path = states_dir / f"{decision:04d}_{action}.state"; state_path.write_bytes(outcome_state)
        nodes.append({"decision": decision, "frame_key": key, "selected_action": action, "score": round(score,6), "screenshot": str(screenshot) if screenshot else None, "state": str(state_path) if state_path else None, "trials": trials})
        edges.append({"from": anchor_key, "to": key, "action": action})
        if frontend.shutdown_requested:
            break
    result = {
        "tool": "ROMancer", "version": "7.0.0", "feature": "novelty exploration",
        "decisions_requested": decisions, "decisions_completed": len(nodes),
        "unique_visual_states": len(visited), "candidate_actions": actions,
        "action_frames": action_frames, "settle_frames": settle_frames,
        "nodes": nodes, "edges": edges,
        "limits": [
            "Novelty exploration is an automated QA search policy, not a general game-solving guarantee.",
            "It optimizes observable novelty and state change, not story objectives, combat skill, or puzzle semantics.",
            "A game-specific profile or authored scenario is required for reliable objective-driven play.",
        ],
    }
    write_json(out_dir / "exploration.json", result)
    return result
