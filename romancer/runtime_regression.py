from __future__ import annotations

"""Runtime regression orchestration for ROMancer v7."""

import json
from pathlib import Path
from typing import Any

from .game_profiles import compile_scenario, load_profile
from .libretro_frontend import LibretroFrontend
from .playtest import ScenarioRunner
from .util import write_json


def _load_obj(path: str | Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return obj


def _checkpoint_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in report.get("results", []):
        if item.get("action") == "checkpoint" and item.get("checkpoint"):
            out[str(item["checkpoint"])] = item
    return out


def compare_runtime_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare observable checkpoint evidence without claiming semantic equivalence."""
    a = _checkpoint_index(baseline); b = _checkpoint_index(candidate)
    names = sorted(set(a) | set(b))
    checkpoints = []
    for name in names:
        ca=a.get(name); cb=b.get(name)
        if ca is None or cb is None:
            checkpoints.append({"name":name,"present_in_baseline":ca is not None,"present_in_candidate":cb is not None,"exact_frame_match":False,"memory_hash_matches":{}})
            continue
        fa=(ca.get("frame") or {}).get("sha256"); fb=(cb.get("frame") or {}).get("sha256")
        ma=ca.get("memory_regions") or {}; mb=cb.get("memory_regions") or {}
        mem={}
        for region in sorted(set(ma)|set(mb)):
            mem[region] = bool(region in ma and region in mb and ma[region].get("sha256") == mb[region].get("sha256") and ma[region].get("size") == mb[region].get("size"))
        checkpoints.append({
            "name":name,"present_in_baseline":True,"present_in_candidate":True,
            "baseline_frame_sha256":fa,"candidate_frame_sha256":fb,"exact_frame_match":bool(fa and fb and fa==fb),
            "memory_hash_matches":mem,
        })
    return {
        "baseline_ok": bool(baseline.get("ok")), "candidate_ok": bool(candidate.get("ok")),
        "baseline_failures": int(baseline.get("failure_count",0)), "candidate_failures": int(candidate.get("failure_count",0)),
        "checkpoint_count": len(checkpoints), "checkpoints":checkpoints,
        "all_shared_frames_exact": bool(checkpoints) and all(x.get("exact_frame_match",False) for x in checkpoints),
        "interpretation": "Exact frame/RAM matches are reproducibility evidence only. A mismatch may be intentional; scenario assertions define functional pass/fail unless a caller explicitly requires exact visual identity.",
    }


def run_one(core: str, game: str, scenario: dict[str, Any], out_dir: str | Path, *, system_dir: str | None=None, save_dir: str | None=None, assets_dir: str | None=None, core_options: dict[str,str] | None=None) -> dict[str, Any]:
    with LibretroFrontend(core, system_dir=system_dir, save_dir=save_dir, assets_dir=assets_dir, core_options=core_options) as f:
        f.load_game(game)
        return ScenarioRunner(f,out_dir).run(scenario)


def run_regression(core: str, baseline_game: str, candidate_game: str, scenario_path: str | Path, out_dir: str | Path, *, profile: str | None=None, system_dir: str | None=None, assets_dir: str | None=None, core_options: dict[str,str] | None=None, require_exact_frames: bool=False) -> dict[str, Any]:
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    scenario=_load_obj(scenario_path)
    if profile:
        scenario=compile_scenario(scenario,load_profile(profile))
    baseline=run_one(core,baseline_game,scenario,out/"baseline",system_dir=system_dir,save_dir=out/"baseline_runtime"/"save",assets_dir=assets_dir,core_options=core_options)
    candidate=run_one(core,candidate_game,scenario,out/"candidate",system_dir=system_dir,save_dir=out/"candidate_runtime"/"save",assets_dir=assets_dir,core_options=core_options)
    comp=compare_runtime_reports(baseline,candidate)
    ok=bool(baseline.get("ok") and candidate.get("ok"))
    if require_exact_frames:
        ok = ok and bool(comp.get("all_shared_frames_exact"))
    result={
        "tool":"ROMancer","version":"7.0.0","feature":"runtime regression","ok":ok,
        "baseline_game":str(Path(baseline_game)),"candidate_game":str(Path(candidate_game)),"scenario":str(Path(scenario_path)),
        "profile":profile,"require_exact_frames":require_exact_frames,"comparison":comp,
        "reports":{"baseline":str(out/"baseline"/"report.json"),"candidate":str(out/"candidate"/"report.json")},
    }
    write_json(out/"regression.json",result)
    return result


def run_suite(core: str, game: str, manifest_path: str | Path, out_dir: str | Path, *, default_profile: str | None=None, system_dir: str | None=None, assets_dir: str | None=None, core_options: dict[str,str] | None=None) -> dict[str, Any]:
    manifest=_load_obj(manifest_path); entries=manifest.get("scenarios")
    if not isinstance(entries,list) or not entries:
        raise ValueError("Suite manifest requires a non-empty scenarios array")
    root=Path(manifest_path).resolve().parent; out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    results=[]
    for i,entry in enumerate(entries,1):
        if isinstance(entry,str): entry={"scenario":entry}
        if not isinstance(entry,dict) or not entry.get("scenario"):
            raise ValueError(f"Invalid suite entry {i}")
        sp=Path(entry["scenario"]); sp=sp if sp.is_absolute() else root/sp
        scenario=_load_obj(sp); profile=entry.get("profile") or default_profile
        if profile: scenario=compile_scenario(scenario,load_profile(profile))
        name=str(entry.get("name") or sp.stem)
        run_dir=out/f"{i:03d}_{_safe(name)}"
        report=run_one(core,game,scenario,run_dir,system_dir=system_dir,save_dir=out/"runtime_saves"/f"{i:03d}_{_safe(name)}",assets_dir=assets_dir,core_options=core_options)
        results.append({"name":name,"scenario":str(sp),"profile":profile,"ok":bool(report.get("ok")),"failure_count":report.get("failure_count",0),"report":str(run_dir/"report.json")})
    result={"tool":"ROMancer","version":"7.0.0","feature":"runtime suite","ok":all(x["ok"] for x in results),"scenario_count":len(results),"passed":sum(1 for x in results if x["ok"]),"failed":sum(1 for x in results if not x["ok"]),"results":results}
    write_json(out/"suite.json",result)
    return result


def _safe(text:str)->str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)[:80] or "scenario"
