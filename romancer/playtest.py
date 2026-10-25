from __future__ import annotations

"""Deterministic runtime scenario runner and evidence bundle generation."""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .frame_analysis import compare_frames, changed_bbox, frame_signature
from .libretro_frontend import Frame, LibretroFrontend
from .util import write_json


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def memory_diff(a: bytes, b: bytes, limit: int = 200) -> dict[str, Any]:
    n = min(len(a), len(b))
    changed = []
    total = 0
    for i in range(n):
        if a[i] != b[i]:
            total += 1
            if len(changed) < limit:
                changed.append({"offset": i, "before": a[i], "after": b[i]})
    if len(a) != len(b):
        total += abs(len(a) - len(b))
    return {
        "before_size": len(a), "after_size": len(b), "changed_bytes": total,
        "changed_ratio": round(total / max(1, max(len(a), len(b))), 8),
        "sample": changed, "sample_truncated": total > len(changed),
    }


def _compare_numeric(actual: int, op: str, expected: int) -> bool:
    return {
        "eq": actual == expected, "ne": actual != expected,
        "lt": actual < expected, "le": actual <= expected,
        "gt": actual > expected, "ge": actual >= expected,
    }.get(op, False)


@dataclass
class Checkpoint:
    name: str
    frame: Frame | None
    memories: dict[str, bytes] = field(default_factory=dict)
    state: bytes | None = None
    created_at_step: int = 0


class ScenarioError(RuntimeError):
    pass


class ScenarioRunner:
    def __init__(self, frontend: LibretroFrontend, out_dir: str | Path):
        self.frontend = frontend
        self.out_dir = Path(out_dir)
        self.frames_dir = self.out_dir / "frames"
        self.states_dir = self.out_dir / "states"
        self.memory_dir = self.out_dir / "memory"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.states_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints: dict[str, Checkpoint] = {}
        self.named_states: dict[str, bytes] = {}
        self.results: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.start_time = time.time()

    def _capture_memories(self, names: list[str] | None) -> dict[str, bytes]:
        result = {}
        for name in names or []:
            result[name] = self.frontend.memory_region(name)
        return result

    def checkpoint(self, name: str, *, memory: list[str] | None = None, state: bool = False, screenshot: bool = True, step_index: int = 0) -> dict[str, Any]:
        frame = self.frontend.last_frame
        memories = self._capture_memories(memory)
        state_data = None
        state_error = None
        if state:
            try:
                state_data = self.frontend.serialize()
            except Exception as exc:
                state_error = str(exc)
        cp = Checkpoint(name=name, frame=frame, memories=memories, state=state_data, created_at_step=step_index)
        self.checkpoints[name] = cp
        artifacts: dict[str, Any] = {}
        if screenshot and frame:
            p = self.frames_dir / f"{step_index:04d}_{_safe_name(name)}.png"
            frame.save_png(p)
            artifacts["screenshot"] = str(p)
        for mem_name, data in memories.items():
            p = self.memory_dir / f"{step_index:04d}_{_safe_name(name)}_{_safe_name(mem_name)}.bin"
            p.write_bytes(data)
            artifacts.setdefault("memory", {})[mem_name] = {"path": str(p), "size": len(data), "sha256": _sha256(data)}
        if state_data is not None:
            p = self.states_dir / f"{step_index:04d}_{_safe_name(name)}.state"
            p.write_bytes(state_data)
            artifacts["state"] = {"path": str(p), "size": len(state_data), "sha256": _sha256(state_data)}
        return {
            "checkpoint": name,
            "frame": frame.summary() if frame else None,
            "memory_regions": {k: {"size": len(v), "sha256": _sha256(v)} for k, v in memories.items()},
            "state_captured": state_data is not None,
            "state_error": state_error,
            "artifacts": artifacts,
        }

    def run(self, scenario: dict[str, Any]) -> dict[str, Any]:
        steps = scenario.get("steps")
        if not isinstance(steps, list):
            raise ScenarioError("Scenario requires a steps array")
        if int(scenario.get("boot_frames", 0)) > 0:
            self.frontend.clear_buttons()
            self.frontend.run_frames(int(scenario["boot_frames"]))
        self.checkpoint("__start__", memory=scenario.get("default_memory", ["system_ram"]), state=True, screenshot=True, step_index=0)
        stop_on_fail = bool(scenario.get("stop_on_fail", True))
        for idx, step in enumerate(steps, start=1):
            try:
                result = self._run_step(idx, step)
                result.setdefault("ok", True)
            except Exception as exc:
                result = {"step": idx, "action": step.get("action") if isinstance(step, dict) else None, "ok": False, "error": str(exc)}
            self.results.append(result)
            if not result.get("ok", False):
                self.failures.append(result)
                if stop_on_fail:
                    break
        # Always capture the final observable state, even after a failed assertion.
        try:
            final_cp = self.checkpoint("__final__", memory=scenario.get("default_memory", ["system_ram"]), state=False, screenshot=True, step_index=len(self.results) + 1)
        except Exception as exc:
            final_cp = {"error": str(exc)}
        report = {
            "tool": "ROMancer",
            "version": "7.0.0",
            "feature": "runtime scenario",
            "scenario": {k: v for k, v in scenario.items() if k != "steps"},
            "steps_requested": len(steps),
            "steps_executed": len(self.results),
            "ok": not self.failures,
            "failure_count": len(self.failures),
            "failures": self.failures,
            "results": self.results,
            "final": final_cp,
            "runtime": {
                "core": self.frontend.core_info().__dict__,
                "av_info": self.frontend.av_info(),
                "memory": self.frontend.memory_summary(),
                "hardware_video_seen": self.frontend.hardware_video_seen,
                "shutdown_requested": self.frontend.shutdown_requested,
                "elapsed_seconds": round(time.time() - self.start_time, 3),
            },
            "interpretation_rule": "A failed assertion is evidence that observed runtime state did not meet the scenario condition. Visual staticness alone is not labeled a CPU hang.",
        }
        write_json(self.out_dir / "report.json", report)
        (self.out_dir / "report.txt").write_text(render_scenario_report(report), encoding="utf-8")
        return report

    def _run_step(self, idx: int, step: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(step, dict):
            raise ScenarioError(f"Step {idx} is not an object")
        action = str(step.get("action", "")).strip().lower()
        if not action:
            raise ScenarioError(f"Step {idx} has no action")
        base = {"step": idx, "action": action, "label": step.get("label")}

        if action == "wait":
            frames = int(step.get("frames", 1))
            before = self.frontend.last_frame
            self.frontend.clear_buttons()
            after = self.frontend.run_frames(frames)
            return {**base, "frames": frames, "frame_delta": compare_frames(before, after)}

        if action in {"press", "hold"}:
            buttons = _buttons(step)
            frames = int(step.get("frames", 1))
            before = self.frontend.last_frame
            self.frontend.run_frames(frames, buttons=buttons, release_after=bool(step.get("release_after", True)))
            settle = int(step.get("settle_frames", 0))
            if settle:
                self.frontend.clear_buttons(); self.frontend.run_frames(settle)
            after = self.frontend.last_frame
            return {**base, "buttons": buttons, "frames": frames, "settle_frames": settle, "frame_delta": compare_frames(before, after), "changed_bbox": changed_bbox(before, after)}

        if action == "tap":
            buttons = _buttons(step)
            before = self.frontend.last_frame
            self.frontend.tap(buttons, hold_frames=int(step.get("hold_frames", 1)), settle_frames=int(step.get("settle_frames", 1)))
            after = self.frontend.last_frame
            return {**base, "buttons": buttons, "frame_delta": compare_frames(before, after), "changed_bbox": changed_bbox(before, after)}

        if action == "release":
            self.frontend.clear_buttons(int(step.get("port", 0)))
            return {**base, "released": True}

        if action == "reset":
            self.frontend.lib.retro_reset()
            settle = int(step.get("settle_frames", 1))
            self.frontend.run_frames(settle)
            return {**base, "settle_frames": settle}

        if action == "checkpoint":
            name = str(step.get("name") or f"checkpoint_{idx}")
            return {**base, **self.checkpoint(name, memory=step.get("memory", ["system_ram"]), state=bool(step.get("state", False)), screenshot=bool(step.get("screenshot", True)), step_index=idx)}

        if action == "screenshot":
            frame = self.frontend.last_frame
            if not frame:
                raise ScenarioError("No software frame has been captured")
            name = _safe_name(str(step.get("name") or f"screen_{idx}"))
            path = self.frames_dir / f"{idx:04d}_{name}.png"
            frame.save_png(path)
            return {**base, "path": str(path), "frame": frame.summary(), "signature": frame_signature(frame)}

        if action == "save_state":
            name = str(step.get("name") or f"state_{idx}")
            data = self.frontend.serialize()
            self.named_states[name] = data
            path = self.states_dir / f"{idx:04d}_{_safe_name(name)}.state"
            path.write_bytes(data)
            return {**base, "name": name, "path": str(path), "size": len(data), "sha256": _sha256(data)}

        if action == "load_state":
            name = str(step.get("name") or "")
            data = self.named_states.get(name)
            if data is None and name in self.checkpoints:
                data = self.checkpoints[name].state
            if data is None:
                path = step.get("path")
                if path:
                    data = Path(path).read_bytes()
            if data is None:
                raise ScenarioError(f"No saved state named {name!r}")
            self.frontend.unserialize(data)
            settle = int(step.get("settle_frames", 0))
            if settle:
                self.frontend.run_frames(settle)
            return {**base, "name": name, "size": len(data), "settle_frames": settle}

        if action == "memory_snapshot":
            region = str(step.get("region", "system_ram"))
            data = self.frontend.memory_region(region)
            name = _safe_name(str(step.get("name") or f"memory_{idx}"))
            path = self.memory_dir / f"{idx:04d}_{name}_{_safe_name(region)}.bin"
            path.write_bytes(data)
            return {**base, "region": region, "path": str(path), "size": len(data), "sha256": _sha256(data)}

        if action == "assert_frame_changed":
            a, b = self._frames_for_assert(step)
            comp = compare_frames(a, b, threshold=int(step.get("threshold", 12)))
            min_ratio = float(step.get("min_changed_cell_ratio", 0.001))
            min_mean = float(step.get("min_mean_abs_luma_delta", 0.05))
            ok = bool(comp.get("comparable")) and (float(comp.get("changed_cell_ratio", 0)) >= min_ratio or float(comp.get("mean_abs_luma_delta", 0)) >= min_mean)
            return {**base, "ok": ok, "comparison": comp, "required": {"min_changed_cell_ratio": min_ratio, "min_mean_abs_luma_delta": min_mean}}

        if action == "assert_frame_stable":
            a, b = self._frames_for_assert(step)
            comp = compare_frames(a, b, threshold=int(step.get("threshold", 12)))
            max_ratio = float(step.get("max_changed_cell_ratio", 0.001))
            max_mean = float(step.get("max_mean_abs_luma_delta", 0.05))
            ok = bool(comp.get("comparable")) and float(comp.get("changed_cell_ratio", 1)) <= max_ratio and float(comp.get("mean_abs_luma_delta", 999)) <= max_mean
            return {**base, "ok": ok, "comparison": comp, "required": {"max_changed_cell_ratio": max_ratio, "max_mean_abs_luma_delta": max_mean}}

        if action == "assert_memory_changed":
            region = str(step.get("region", "system_ram"))
            cp_a = self._get_checkpoint(str(step.get("from", "__start__")))
            cp_b = self._get_checkpoint(str(step.get("to", "__final__")), allow_live=True, memory_region=region)
            a = cp_a.memories.get(region, b"")
            b = cp_b.memories.get(region, b"")
            diff = memory_diff(a, b)
            min_changed = int(step.get("min_changed_bytes", 1))
            max_changed = step.get("max_changed_bytes")
            ok = diff["changed_bytes"] >= min_changed and (max_changed is None or diff["changed_bytes"] <= int(max_changed))
            return {**base, "ok": ok, "region": region, "diff": diff, "required": {"min_changed_bytes": min_changed, "max_changed_bytes": max_changed}}

        if action == "assert_memory_value":
            region = str(step.get("region", "system_ram"))
            data = self.frontend.memory_region(region)
            offset = _parse_int(step.get("offset", 0))
            width = int(step.get("width", 1))
            endian = str(step.get("endian", "little"))
            if width not in (1, 2, 3, 4, 8):
                raise ScenarioError("assert_memory_value width must be 1,2,3,4,8")
            if offset < 0 or offset + width > len(data):
                raise ScenarioError(f"Memory range outside {region}: offset={offset} width={width} size={len(data)}")
            actual = int.from_bytes(data[offset:offset + width], endian)
            expected = _parse_int(step.get("value", 0))
            op = str(step.get("op", "eq")).lower()
            ok = _compare_numeric(actual, op, expected)
            return {**base, "ok": ok, "region": region, "offset": offset, "width": width, "endian": endian, "actual": actual, "op": op, "expected": expected}

        if action == "assert_not_shutdown":
            return {**base, "ok": not self.frontend.shutdown_requested, "shutdown_requested": self.frontend.shutdown_requested}

        if action == "choose_first_effective":
            return {**base, **self._choose_first_effective(idx, step)}

        if action == "press_until_change":
            buttons = _buttons(step)
            attempts = int(step.get("max_attempts", 20))
            hold_frames = int(step.get("hold_frames", 1))
            settle = int(step.get("settle_frames", 2))
            min_ratio = float(step.get("min_changed_cell_ratio", 0.01))
            baseline = self.frontend.last_frame
            history = []
            found = False
            for attempt in range(1, attempts + 1):
                self.frontend.tap(buttons, hold_frames=hold_frames, settle_frames=settle)
                comp = compare_frames(baseline, self.frontend.last_frame)
                history.append({"attempt": attempt, "comparison": comp})
                if float(comp.get("changed_cell_ratio", 0)) >= min_ratio:
                    found = True
                    break
            return {**base, "ok": found, "buttons": buttons, "attempts": len(history), "required_ratio": min_ratio, "history": history}

        if action == "note":
            return {**base, "text": str(step.get("text", ""))}

        raise ScenarioError(f"Unsupported scenario action: {action}")

    def _choose_first_effective(self, idx: int, step: dict[str, Any]) -> dict[str, Any]:
        candidates = step.get("candidates") or []
        if not isinstance(candidates, list) or not candidates:
            raise ScenarioError("choose_first_effective requires candidates")
        try:
            anchor = self.frontend.serialize()
        except Exception as exc:
            raise ScenarioError(f"choose_first_effective requires save-state support: {exc}")
        memory_region = str(step.get("memory_region", "system_ram"))
        baseline_memory = self.frontend.memory_region(memory_region)
        baseline_frame = self.frontend.last_frame
        trials = []
        selected = None
        selected_state = None
        for candidate in candidates:
            buttons = [candidate] if isinstance(candidate, str) else list(candidate)
            self.frontend.unserialize(anchor)
            self.frontend.clear_buttons()
            self.frontend.run_frames(int(step.get("pre_frames", 0)))
            before = self.frontend.last_frame or baseline_frame
            self.frontend.tap(buttons, hold_frames=int(step.get("hold_frames", 1)), settle_frames=int(step.get("settle_frames", 3)))
            after = self.frontend.last_frame
            frame_delta = compare_frames(before, after)
            mem = self.frontend.memory_region(memory_region)
            mem_delta = memory_diff(baseline_memory, mem, limit=40)
            score = float(frame_delta.get("changed_cell_ratio", 0)) * 1000.0 + min(1000, mem_delta["changed_bytes"]) / 1000.0
            effective = float(frame_delta.get("changed_cell_ratio", 0)) >= float(step.get("min_changed_cell_ratio", 0.002)) or mem_delta["changed_bytes"] >= int(step.get("min_changed_bytes", 1))
            trials.append({"buttons": buttons, "effective": effective, "score": round(score, 6), "frame_delta": frame_delta, "memory_changed_bytes": mem_delta["changed_bytes"]})
            if effective and selected is None:
                selected = buttons
                selected_state = self.frontend.serialize()
                if not bool(step.get("try_all", False)):
                    break
        if selected_state is not None:
            self.frontend.unserialize(selected_state)
        else:
            self.frontend.unserialize(anchor)
        return {"ok": selected is not None, "selected": selected, "trials": trials, "state_restored_to": "selected outcome" if selected else "anchor"}

    def _frames_for_assert(self, step: dict[str, Any]) -> tuple[Frame | None, Frame | None]:
        frm = str(step.get("from", "__start__"))
        to = str(step.get("to", "live"))
        a = self._get_checkpoint(frm).frame
        b = self.frontend.last_frame if to in {"live", "__live__", "__final__"} else self._get_checkpoint(to).frame
        return a, b

    def _get_checkpoint(self, name: str, allow_live: bool = False, memory_region: str | None = None) -> Checkpoint:
        if allow_live and name in {"live", "__live__", "__final__"}:
            memories = {memory_region: self.frontend.memory_region(memory_region)} if memory_region else {}
            return Checkpoint(name="live", frame=self.frontend.last_frame, memories=memories)
        if name not in self.checkpoints:
            raise ScenarioError(f"Unknown checkpoint: {name}")
        return self.checkpoints[name]


def _safe_name(text: str) -> str:
    out = "".join(c if (c.isalnum() or c in "._-") else "_" for c in text.strip())
    return out[:120] or "unnamed"


def _buttons(step: dict[str, Any]) -> list[str]:
    value = step.get("buttons", step.get("button", []))
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value]
    raise ScenarioError("buttons must be a string or array")


def _parse_int(v: Any) -> int:
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.startswith("$"):
        return int(s[1:], 16)
    return int(s, 0)


def load_scenario(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render_scenario_report(report: dict[str, Any]) -> str:
    lines = [
        "ROMancer v7 Runtime Validation Report",
        "=====================================",
        "",
        f"Result: {'PASS' if report.get('ok') else 'FAIL'}",
        f"Steps executed: {report.get('steps_executed')}/{report.get('steps_requested')}",
        f"Failures: {report.get('failure_count')}",
        "",
    ]
    scenario = report.get("scenario", {})
    if scenario.get("name"):
        lines.append(f"Scenario: {scenario['name']}")
    if scenario.get("description"):
        lines.append(f"Description: {scenario['description']}")
    lines.append("")
    for r in report.get("results", []):
        status = "PASS" if r.get("ok", True) else "FAIL"
        label = f" - {r.get('label')}" if r.get("label") else ""
        lines.append(f"[{status}] Step {r.get('step')}: {r.get('action')}{label}")
        if r.get("error"):
            lines.append(f"  Error: {r['error']}")
        if r.get("selected"):
            lines.append(f"  Selected input: {', '.join(r['selected'])}")
        comp = r.get("comparison") or r.get("frame_delta")
        if isinstance(comp, dict) and comp.get("comparable"):
            lines.append(f"  Visual delta: mean={comp.get('mean_abs_luma_delta')} changed_cells={comp.get('changed_cell_ratio')}")
    lines.extend(["", "Interpretation:", str(report.get("interpretation_rule", "")), ""])
    return "\n".join(lines)
