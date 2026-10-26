from __future__ import annotations

"""ROMancer v7 runtime validation, game-profile, and play-learning CLI layer."""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .frame_analysis import compare_frames
from .game_profiles import create_profile, list_profiles, load_profile, validate_profile, compile_scenario, resolve_intent
from .libretro_frontend import Frame, LibretroFrontend, runtime_platform_report, write_rgb_png
from .memory_learning import find_value, correlate_numeric_series, rank_monotonic_candidates, parse_observation_specs
from .playtest import ScenarioRunner
from .runtime_agent import discover_controls, novelty_explore
from .runtime_regression import run_regression, run_suite
from .runtime_goal import goal_search
from .state_model import capture_state_signature, compare_state_signature, load_state_library, match_state_library, save_state_signature

from .systems.gba import identify_gba
from .systems.segacd import identify_segacd_bytes
from .util import write_json

VERSION = "7.0.0"


def _kv(items: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Expected KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        if not k:
            raise ValueError("Core option key cannot be empty")
        out[k] = v
    return out


def _buttons_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [x.strip().lower() for x in value.split(",") if x.strip()]


def _load_json(path: str | Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object")
    return obj


def _frontend(args) -> LibretroFrontend:
    return LibretroFrontend(
        args.core,
        system_dir=getattr(args, "system_dir", None),
        save_dir=getattr(args, "save_dir", None),
        assets_dir=getattr(args, "assets_dir", None),
        core_options=_kv(getattr(args, "core_option", None)),
    )


def _add_runtime_common(s: argparse.ArgumentParser, *, game: bool = True) -> None:
    s.add_argument("--core", required=True, help="Path to a user-supplied libretro core shared library")
    if game:
        s.add_argument("--game", required=True, help="Path to a user-supplied ROM, disc descriptor, or other core content")
    s.add_argument("--system-dir", help="Libretro system/BIOS directory. ROMancer never bundles BIOS files")
    s.add_argument("--save-dir", help="Directory for SRAM and core save data")
    s.add_argument("--assets-dir", help="Libretro core assets directory")
    s.add_argument("--core-option", action="append", default=[], metavar="KEY=VALUE", help="Core option, repeatable")
    s.add_argument("--json", action="store_true")


def add_v7_parsers(sub) -> None:
    s = sub.add_parser("runtime-platform", help="[v7] Report the host capabilities used by the direct libretro runtime layer")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("runtime-doctor", help="[v7] Inspect a libretro core and optional content without GUI automation")
    _add_runtime_common(s, game=False)
    s.add_argument("--game", help="Optional content path to check extension compatibility and boot")
    s.add_argument("--boot-frames", type=int, default=2)

    s = sub.add_parser("runtime-run", help="[v7] Boot content, send deterministic RetroPad input, and capture runtime evidence")
    _add_runtime_common(s)
    s.add_argument("--boot-frames", type=int, default=120)
    s.add_argument("--buttons", help="Comma-separated RetroPad buttons to hold after boot")
    s.add_argument("--input-frames", type=int, default=1)
    s.add_argument("--settle-frames", type=int, default=1)
    s.add_argument("--screenshot")
    s.add_argument("--memory-out")
    s.add_argument("--memory-region", default="system_ram")

    s = sub.add_parser("runtime-scenario", help="[v7] Execute a deterministic JSON playtest and write screenshots, states, RAM, and assertions")
    _add_runtime_common(s)
    s.add_argument("--scenario", required=True)
    s.add_argument("--profile", help="Optional built-in profile id or JSON path used to resolve semantic intents")
    s.add_argument("--out-dir", required=True)

    s = sub.add_parser("runtime-controls", help="[v7] Probe RetroPad controls from one restored save-state anchor and record observable effects")
    _add_runtime_common(s)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--buttons", help="Comma-separated buttons; defaults to the standard discovery set")
    s.add_argument("--boot-frames", type=int, default=120)
    s.add_argument("--hold-frames", type=int, default=2)
    s.add_argument("--settle-frames", type=int, default=8)
    s.add_argument("--long-hold-frames", type=int, default=30)
    s.add_argument("--memory-region", default="system_ram")

    s = sub.add_parser("runtime-explore", help="[v7] Save-state branch through candidate inputs and retain novel observable outcomes for QA discovery")
    _add_runtime_common(s)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--decisions", type=int, default=40)
    s.add_argument("--actions", help="Comma-separated candidate RetroPad buttons")
    s.add_argument("--action-frames", type=int, default=10)
    s.add_argument("--settle-frames", type=int, default=4)
    s.add_argument("--boot-frames", type=int, default=120)
    s.add_argument("--memory-region", default="system_ram")
    s.add_argument("--save-every", type=int, default=1)

    s = sub.add_parser("runtime-suite", help="[v7] Run a manifest of deterministic playtest scenarios and aggregate pass/fail evidence")
    _add_runtime_common(s)
    s.add_argument("--manifest", required=True)
    s.add_argument("--profile", help="Default profile for suite entries that do not name one")
    s.add_argument("--out-dir", required=True)

    s = sub.add_parser("runtime-regression", help="[v7] Run one scenario against baseline and candidate content and compare checkpoint evidence")
    s.add_argument("--core", required=True)
    s.add_argument("--baseline", required=True)
    s.add_argument("--candidate", required=True)
    s.add_argument("--scenario", required=True)
    s.add_argument("--profile")
    s.add_argument("--out-dir", required=True)
    s.add_argument("--system-dir")
    s.add_argument("--assets-dir")
    s.add_argument("--core-option", action="append", default=[], metavar="KEY=VALUE")
    s.add_argument("--require-exact-frames", action="store_true", help="Make exact checkpoint frame hashes part of pass/fail")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("runtime-goal-search", help="[v7] Bounded save-state beam search toward a learned visual target state")
    _add_runtime_common(s)
    s.add_argument("--target", required=True, help="State signature JSON or state-library JSON")
    s.add_argument("--target-name", help="Required when --target contains multiple named states")
    s.add_argument("--out-dir", required=True)
    s.add_argument("--actions", help="Comma-separated candidate RetroPad actions")
    s.add_argument("--boot-frames", type=int, default=120)
    s.add_argument("--action-frames", type=int, default=1)
    s.add_argument("--settle-frames", type=int, default=3)
    s.add_argument("--max-depth", type=int, default=12)
    s.add_argument("--beam-width", type=int, default=8)
    s.add_argument("--success-mean-delta", type=float, default=1.0)
    s.add_argument("--success-changed-ratio", type=float, default=0.01)

    s = sub.add_parser("runtime-state-capture", help="[v7] Capture a reusable visual signature for a known or candidate game state")
    _add_runtime_common(s)
    s.add_argument("--name", required=True)
    s.add_argument("--context", default="unknown")
    s.add_argument("--status", default="candidate", choices=["candidate","verified"])
    s.add_argument("--evidence")
    s.add_argument("--boot-frames", type=int, default=120)
    s.add_argument("--buttons", help="Optional comma-separated input to apply before capture")
    s.add_argument("--input-frames", type=int, default=1)
    s.add_argument("--settle-frames", type=int, default=4)
    s.add_argument("--out", required=True)
    s.add_argument("--screenshot")

    s = sub.add_parser("runtime-state-match", help="[v7] Compare the current software frame to a library of previously captured visual state signatures")
    _add_runtime_common(s)
    s.add_argument("--states", required=True)
    s.add_argument("--boot-frames", type=int, default=120)
    s.add_argument("--buttons")
    s.add_argument("--input-frames", type=int, default=1)
    s.add_argument("--settle-frames", type=int, default=4)
    s.add_argument("--threshold", type=int, default=12)
    s.add_argument("--limit", type=int, default=10)

    s = sub.add_parser("runtime-memory-find", help="[v7] Find an observed numeric value in a runtime RAM snapshot")
    s.add_argument("snapshot")
    s.add_argument("--value", required=True)
    s.add_argument("--widths", default="1,2,3,4")
    s.add_argument("--endian", default="both", choices=["little", "big", "both"])
    s.add_argument("--signed", action="store_true")
    s.add_argument("--alignment", type=int, default=1)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("runtime-memory-correlate", help="[v7] Correlate known numeric observations across multiple RAM snapshots")
    s.add_argument("--observe", action="append", required=True, metavar="VALUE=FILE")
    s.add_argument("--widths", default="1,2,3,4")
    s.add_argument("--endian", default="both", choices=["little", "big", "both"])
    s.add_argument("--signed", action="store_true")
    s.add_argument("--alignment", type=int, default=1)
    s.add_argument("--out")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("runtime-memory-rank", help="[v7] Rank RAM offsets that repeatedly change, increase, or decrease across snapshots")
    s.add_argument("snapshots", nargs="+")
    s.add_argument("--direction", default="changed", choices=["changed", "increase", "decrease"])
    s.add_argument("--limit", type=int, default=200)
    s.add_argument("--out")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("profile", help="[v7] List, inspect, validate, create, or resolve semantic game profiles")
    s.add_argument("action", choices=["list", "show", "validate", "create", "resolve"])
    s.add_argument("target", nargs="?")
    s.add_argument("--rom")
    s.add_argument("--out")
    s.add_argument("--id")
    s.add_argument("--game")
    s.add_argument("--genre", default="unknown")
    s.add_argument("--intent")
    s.add_argument("--context", default="field")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("scenario-template", help="[v7] Write a documented runtime-scenario JSON starter")
    s.add_argument("--out", required=True)
    s.add_argument("--profile")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("v7-self-test", help="[v7] Test profiles, frame conversion, RAM learning, format detection, and the libretro host with the deterministic mock core when gcc is available")
    s.add_argument("--out")
    s.add_argument("--json", action="store_true")


def runtime_doctor(args) -> dict[str, Any]:
    report: dict[str, Any] = {"tool": "ROMancer", "version": VERSION, "feature": "runtime doctor", "platform": runtime_platform_report()}
    try:
        with _frontend(args) as f:
            report["core"] = f.core_info().__dict__
            report["libretro_api_ok"] = report["core"]["api_version"] == 1
            if args.game:
                load = f.load_game(args.game)
                f.run_frames(max(0, args.boot_frames))
                report["content"] = load
                report["last_frame"] = f.last_frame.summary() if f.last_frame else None
                report["memory"] = f.memory_summary()
                report["disk"] = f.disk_status()
                report["shutdown_requested"] = f.shutdown_requested
                report["hardware_video_seen"] = f.hardware_video_seen
                report["software_frame_available"] = f.last_frame is not None
            report["ok"] = bool(report.get("libretro_api_ok")) and not report.get("hardware_video_seen", False)
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
    report["limits"] = [
        "ROMancer v7 does not bundle emulator cores, BIOS/firmware, ROMs, disc images, or commercial game assets.",
        "The evidence frontend captures software-rendered frames. Hardware-rendered libretro cores are detected but are not captured by this headless path.",
        "A successful boot proves compatibility at the tested state only; it is not proof that an entire game is completable.",
    ]
    return report


def runtime_run(args) -> dict[str, Any]:
    with _frontend(args) as f:
        load = f.load_game(args.game)
        f.clear_buttons(); before = f.run_frames(max(0, args.boot_frames))
        buttons = _buttons_csv(args.buttons) or []
        if buttons and args.input_frames > 0:
            f.run_frames(args.input_frames, buttons=buttons, release_after=True)
        if args.settle_frames > 0:
            f.clear_buttons(); f.run_frames(args.settle_frames)
        after = f.last_frame
        screenshot = None
        if args.screenshot:
            if after is None:
                raise RuntimeError("No software frame available for screenshot")
            screenshot = after.save_png(args.screenshot)
        mem = f.memory_region(args.memory_region)
        mem_path = None
        if args.memory_out:
            Path(args.memory_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.memory_out).write_bytes(mem); mem_path = args.memory_out
        return {
            "tool": "ROMancer", "version": VERSION, "feature": "runtime run", "load": load,
            "buttons": buttons, "input_frames": args.input_frames, "settle_frames": args.settle_frames,
            "frame": after.summary() if after else None, "frame_delta": compare_frames(before, after),
            "screenshot": screenshot, "memory_region": args.memory_region, "memory_size": len(mem), "memory_out": mem_path,
            "memory": f.memory_summary(), "disk": f.disk_status(), "shutdown_requested": f.shutdown_requested,
            "hardware_video_seen": f.hardware_video_seen,
        }


def runtime_scenario(args) -> dict[str, Any]:
    scenario = _load_json(args.scenario)
    if args.profile:
        scenario = compile_scenario(scenario, load_profile(args.profile))
    with _frontend(args) as f:
        f.load_game(args.game)
        return ScenarioRunner(f, args.out_dir).run(scenario)


def runtime_controls(args) -> dict[str, Any]:
    with _frontend(args) as f:
        f.load_game(args.game)
        return discover_controls(f, args.out_dir, buttons=_buttons_csv(args.buttons), boot_frames=args.boot_frames,
                                 hold_frames=args.hold_frames, settle_frames=args.settle_frames,
                                 long_hold_frames=args.long_hold_frames, memory_region=args.memory_region)


def runtime_explore(args) -> dict[str, Any]:
    with _frontend(args) as f:
        f.load_game(args.game)
        return novelty_explore(f, args.out_dir, decisions=args.decisions, candidate_actions=_buttons_csv(args.actions),
                               action_frames=args.action_frames, settle_frames=args.settle_frames,
                               boot_frames=args.boot_frames, memory_region=args.memory_region, save_every=args.save_every)


def _reach_capture_state(args):
    f=_frontend(args); f.load_game(args.game); f.clear_buttons(); f.run_frames(max(0,args.boot_frames))
    buttons=_buttons_csv(args.buttons) or []
    if buttons and args.input_frames>0: f.run_frames(args.input_frames,buttons=buttons,release_after=True)
    if args.settle_frames>0: f.clear_buttons(); f.run_frames(args.settle_frames)
    if f.last_frame is None:
        f.close(); raise RuntimeError("No software-rendered frame was captured")
    return f


def runtime_goal_search(args) -> dict[str,Any]:
    states=load_state_library(args.target)
    if args.target_name:
        matches=[x for x in states if str(x.get("name"))==args.target_name]
        if not matches: raise ValueError(f"No target state named {args.target_name!r}")
        target=matches[0]
    else:
        if len(states)!=1: raise ValueError("Target library contains multiple states; supply --target-name")
        target=states[0]
    with _frontend(args) as f:
        f.load_game(args.game)
        return goal_search(f,target,args.out_dir,actions=_buttons_csv(args.actions),boot_frames=args.boot_frames,action_frames=args.action_frames,settle_frames=args.settle_frames,max_depth=args.max_depth,beam_width=args.beam_width,success_mean_delta=args.success_mean_delta,success_changed_ratio=args.success_changed_ratio)


def runtime_state_capture(args) -> dict[str,Any]:
    f=_reach_capture_state(args)
    try:
        sig=capture_state_signature(f.last_frame,args.name,context=args.context,status=args.status,evidence=args.evidence)
        save_state_signature(args.out,sig)
        screenshot=None
        if args.screenshot: screenshot=f.last_frame.save_png(args.screenshot)
        return {"tool":"ROMancer","version":VERSION,"feature":"runtime state capture","signature":sig,"out":args.out,"screenshot":screenshot}
    finally: f.close()


def runtime_state_match(args) -> dict[str,Any]:
    f=_reach_capture_state(args)
    try:
        result=match_state_library(load_state_library(args.states),f.last_frame,threshold=args.threshold,max_results=args.limit)
        return {"tool":"ROMancer","version":VERSION,"feature":"runtime state match","states":args.states,"result":result}
    finally: f.close()


def profile_cmd(args) -> dict[str, Any]:
    if args.action == "list":
        return {"tool": "ROMancer", "version": VERSION, "profiles": list_profiles()}
    if args.action == "create":
        if not args.rom or not args.out:
            raise ValueError("profile create requires --rom and --out")
        return create_profile(args.rom, args.out, profile_id=args.id, game=args.game, genre=args.genre)
    if not args.target:
        raise ValueError(f"profile {args.action} requires TARGET")
    p = load_profile(args.target)
    if args.action == "show": return p
    if args.action == "validate": return validate_profile(p)
    if args.action == "resolve":
        if not args.intent: raise ValueError("profile resolve requires --intent")
        return {"profile": p.get("id"), "context": args.context, "intent": args.intent, "buttons": resolve_intent(p, args.intent, args.context)}
    raise ValueError(args.action)


def scenario_template(out: str | Path, profile: str | None = None) -> dict[str, Any]:
    template: dict[str, Any] = {
        "name": "runtime_smoke",
        "description": "Replace the sample actions with evidence-backed checkpoints for the game under test.",
        "boot_frames": 120,
        "default_memory": ["system_ram"],
        "stop_on_fail": True,
        "steps": [
            {"action": "checkpoint", "name": "booted", "memory": ["system_ram"], "state": True, "screenshot": True},
            {"action": "tap", "button": "start", "hold_frames": 1, "settle_frames": 4},
            {"action": "checkpoint", "name": "after_start", "memory": ["system_ram"], "screenshot": True},
            {"action": "assert_frame_changed", "from": "booted", "to": "after_start", "min_changed_cell_ratio": 0.001},
        ],
    }
    if profile:
        p = load_profile(profile)
        template["profile"] = p.get("id")
        template["description"] += " Semantic `intent` may be used when the selected profile verifies that mapping."
    write_json(out, template)
    return template


def _synthetic_gba() -> bytes:
    data = bytearray(0xC0)
    data[0xA0:0xAC] = b"ROMANCERTEST"
    data[0xAC:0xB0] = b"R7TE"
    data[0xB0:0xB2] = b"01"
    data[0xB2] = 0x96
    data[0xBD] = (-sum(data[0xA0:0xBD]) - 0x19) & 0xFF
    return bytes(data)


def v7_self_test(out: str | None = None) -> dict[str, Any]:
    tests: list[dict[str, Any]] = []
    def check(name: str, fn):
        try:
            detail = fn()
            ok = bool(detail if isinstance(detail, bool) else True)
            tests.append({"name": name, "ok": ok, "detail": detail})
        except Exception as exc:
            tests.append({"name": name, "ok": False, "error": str(exc)})

    check("profile validation", lambda: all(validate_profile(load_profile(x))["ok"] for x in ["generic_jrpg", "final_fantasy_iii_snes", "shadowrun_genesis"]))
    check("Genesis semantic A/C mapping", lambda: resolve_intent(load_profile("shadowrun_genesis"), "attack", "field") == ["y"] and resolve_intent(load_profile("shadowrun_genesis"), "switch_character", "field") == ["a"])
    check("GBA header detection", lambda: bool((identify_gba(_synthetic_gba()) or {}).get("header_checksum_valid")))
    sega = bytearray(0x100); sega[:16] = b"SEGADISCSYSTEM  "
    check("Sega CD System ID detection", lambda: (identify_segacd_bytes(bytes(sega)) or {}).get("system") == "Sega CD / Mega-CD")
    check("PNG writer", lambda: _test_png_writer())
    check("RAM value correlation", lambda: _test_memory_correlation())
    check("semantic scenario compilation", lambda: _test_scenario_compile())
    check("visual state signature", lambda: _test_state_signature())

    mock = _test_mock_runtime()
    tests.append(mock)
    ok = all(t.get("ok", False) for t in tests if not t.get("skipped")) and not any(t.get("ok") is False for t in tests)
    result = {
        "tool": "ROMancer", "version": VERSION, "feature": "v7 self-test", "ok": ok,
        "tests": tests,
        "notes": [
            "The deterministic mock core tests ROMancer's libretro host, input, software video, exposed RAM, save states, screenshots, scenario assertions, and control discovery without a third-party emulator or commercial content.",
            "Testing with a real console core and legally supplied game remains a separate compatibility validation step.",
        ],
    }
    if out: write_json(out, result)
    return result


def _test_png_writer() -> bool:
    with tempfile.TemporaryDirectory(prefix="romancer_v7_png_") as td:
        p = Path(td) / "x.png"
        write_rgb_png(p, 2, 1, bytes([255,0,0, 0,255,0]))
        return p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") and p.stat().st_size > 40


def _test_memory_correlation() -> bool:
    a=bytearray(32); b=bytearray(32); c=bytearray(32)
    a[7:9]=(100).to_bytes(2,"little"); b[7:9]=(80).to_bytes(2,"little"); c[7:9]=(65).to_bytes(2,"little")
    r=correlate_numeric_series([(100,bytes(a)),(80,bytes(b)),(65,bytes(c))], widths=[2], endian="little")
    return any(x["offset"]==7 for x in r["candidates"])


def _test_scenario_compile() -> bool:
    s={"context":"field","steps":[{"action":"tap","intent":"open_subscreen"}]}
    c=compile_scenario(s,load_profile("final_fantasy_iii_snes"))
    return c["steps"][0].get("buttons")==["x"]


def _test_state_signature() -> bool:
    fr=Frame(index=1,width=2,height=1,pitch=6,pixel_format="RGB24-test",rgb=bytes([255,0,0,0,255,0]))
    sig=capture_state_signature(fr,"fixture",context="test")
    comp=compare_state_signature(sig,fr)
    return bool(comp.get("comparable") and comp.get("exact_rgb_match") and comp.get("mean_abs_luma_delta")==0.0)


def _test_mock_runtime() -> dict[str, Any]:
    gcc = shutil.which("gcc") or shutil.which("cc")
    source = Path(__file__).resolve().parent.parent / "tests" / "mock_libretro.c"
    if not gcc:
        return {"name":"libretro mock end-to-end", "ok": True, "skipped": True, "detail":"gcc/cc not found; source fixture remains available"}
    if not source.is_file():
        return {"name":"libretro mock end-to-end", "ok": False, "error":f"missing {source}"}
    try:
        with tempfile.TemporaryDirectory(prefix="romancer_v7_mock_") as td:
            td=Path(td); so=td/"mock_libretro.so"; content=td/"fixture.bin"; content.write_bytes(b"ROMancer v7 fixture")
            cp=subprocess.run([gcc,"-shared","-fPIC","-O2",str(source),"-o",str(so)],capture_output=True,text=True,timeout=30)
            if cp.returncode != 0:
                return {"name":"libretro mock end-to-end", "ok":False, "error":cp.stderr[-4000:]}
            with LibretroFrontend(so, save_dir=td/"runtime") as f:
                load=f.load_game(content); f.run_frames(2)
                before=f.memory_region("system_ram"); frame0=f.last_frame
                state=f.serialize(); f.tap(["right"],hold_frames=2,settle_frames=1)
                after=f.memory_region("system_ram"); frame1=f.last_frame
                moved=after[0] > before[0] and compare_frames(frame0,frame1).get("comparable")
                f.unserialize(state); restored=f.memory_region("system_ram")[0] == before[0]
                scenario={"boot_frames":1,"default_memory":["system_ram"],"steps":[
                    {"action":"checkpoint","name":"a","memory":["system_ram"],"state":True},
                    {"action":"press","button":"right","frames":1,"settle_frames":1},
                    {"action":"checkpoint","name":"b","memory":["system_ram"]},
                    {"action":"assert_memory_changed","region":"system_ram","from":"a","to":"b","min_changed_bytes":1}
                ]}
                scen=ScenarioRunner(f,td/"scenario").run(scenario)
                control=discover_controls(f,td/"controls",buttons=["right","a","b"],boot_frames=0,hold_frames=1,settle_frames=1,long_hold_frames=2)
                f.unserialize(state); f.clear_buttons(); f.run_frames(1); anchor_for_goal=f.serialize()
                f.tap(["right"],hold_frames=1,settle_frames=0); target=capture_state_signature(f.last_frame,"one_right",context="test")
                f.unserialize(anchor_for_goal); f.clear_buttons(); f.run_frames(1)
                goal=goal_search(f,target,td/"goal",actions=["left","right","b"],boot_frames=0,action_frames=1,settle_frames=0,max_depth=2,beam_width=3)
                descriptors=load.get("input_descriptors",[])
                ok=bool(moved and restored and scen.get("ok") and "right" in control.get("effective_buttons_at_anchor",[]) and descriptors and goal.get("goal_reached") and goal.get("sequence")==["right"])
                return {"name":"libretro mock end-to-end","ok":ok,"detail":{
                    "core":load.get("core",{}).get("library_name"),"input_descriptors":len(descriptors),"movement_observed":bool(moved),
                    "state_restore":bool(restored),"scenario_ok":bool(scen.get("ok")),"effective_buttons":control.get("effective_buttons_at_anchor",[]),
                    "visual_goal_reached":bool(goal.get("goal_reached")),"goal_sequence":goal.get("sequence")
                }}
    except Exception as exc:
        return {"name":"libretro mock end-to-end", "ok":False, "error":str(exc)}


def dispatch_v7(args) -> tuple[bool, Any]:
    cmd = getattr(args, "cmd", None)
    if cmd == "runtime-platform": return True, runtime_platform_report()
    if cmd == "runtime-doctor": return True, runtime_doctor(args)
    if cmd == "runtime-run": return True, runtime_run(args)
    if cmd == "runtime-scenario": return True, runtime_scenario(args)
    if cmd == "runtime-controls": return True, runtime_controls(args)
    if cmd == "runtime-explore": return True, runtime_explore(args)
    if cmd == "runtime-suite":
        return True, run_suite(args.core,args.game,args.manifest,args.out_dir,default_profile=args.profile,system_dir=args.system_dir,assets_dir=args.assets_dir,core_options=_kv(args.core_option))
    if cmd == "runtime-regression":
        return True, run_regression(args.core,args.baseline,args.candidate,args.scenario,args.out_dir,profile=args.profile,system_dir=args.system_dir,assets_dir=args.assets_dir,core_options=_kv(args.core_option),require_exact_frames=args.require_exact_frames)
    if cmd == "runtime-goal-search": return True, runtime_goal_search(args)
    if cmd == "runtime-state-capture": return True, runtime_state_capture(args)
    if cmd == "runtime-state-match": return True, runtime_state_match(args)
    if cmd == "runtime-memory-find":
        widths=[int(x) for x in args.widths.split(",") if x.strip()]
        return True, find_value(Path(args.snapshot).read_bytes(), int(args.value,0), widths=widths, endian=args.endian, signed=args.signed, alignment=args.alignment)
    if cmd == "runtime-memory-correlate":
        widths=[int(x) for x in args.widths.split(",") if x.strip()]
        result=correlate_numeric_series(parse_observation_specs(args.observe),widths=widths,endian=args.endian,signed=args.signed,alignment=args.alignment)
        if args.out: write_json(args.out,result)
        return True,result
    if cmd == "runtime-memory-rank":
        result=rank_monotonic_candidates([Path(x).read_bytes() for x in args.snapshots],direction=args.direction,max_results=args.limit)
        if args.out: write_json(args.out,result)
        return True,result
    if cmd == "profile": return True, profile_cmd(args)
    if cmd == "scenario-template": return True, scenario_template(args.out,args.profile)
    if cmd == "v7-self-test": return True, v7_self_test(args.out)
    return False, None
