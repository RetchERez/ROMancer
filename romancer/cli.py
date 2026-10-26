from __future__ import annotations

import argparse
import json
from . import ROMANCER_VERSION as APP_VERSION
from .history_cli import add_commands as add_history_commands, dispatch as dispatch_history
from .contracts_cli import add_commands as add_contract_commands, dispatch as dispatch_contracts
from .systems_cli import add_commands as add_system_commands, dispatch as dispatch_systems
from .capture_cli import add_commands as add_capture_commands, dispatch as dispatch_captures, emit_result as emit_capture
from .script_cli import add_commands as add_script_commands, dispatch as dispatch_scripts, emit_result as emit_script
from .layout_cli import add_commands as add_layout_commands, dispatch as dispatch_layout, emit_result as emit_layout
from .menu_cli import register as add_menu_commands, dispatch as dispatch_menu, emit_result as emit_menu
from .engineering_cli import register as add_engineering_commands, dispatch as dispatch_engineering
import sys

from .rom_ident import identify_rom
from .project import init_project, project_report
from .systems.snes import snes_to_offset
from .systems.genesis import classify_68k_address
from .diffing import byte_diff
from .ips import create_ips
from .evidence import add_evidence, load_evidence, export_ai_bundle
from .trace_parser import parse_trace, trace_summary, filter_trace, detect_trace_format
from .util import write_json
from .workflow import (
    plan_breakpoints, debugger_guide, trace_window, correlate_trace,
    find_routine, resolve_pc, report_trace, ai_bundle_v2,
)
from .patching import patch_plan, validate_patch, risk_score, asar_skeleton, ips_manifest, doctor, self_test, project_status
from .recon import text_scan, pointer_scan, tile_dump, palette_dump, record_scan, table_report
from .backend import backend_config, backend_capabilities, launch, session_template, watch_traces
from .knowledge import symbol_cmd, finding_cmd, routine_cmd, ai_prompt
from .workspace import patch_workspace, patch_build, patch_rebuild, regression_plan, patch_compare
from .audit import audit_project, report_check, package_release
from .hardening import capabilities, rom_doctor, clean_tree, full_self_test, build_release
from .advanced_trace import trace_compare, trace_hot_pc, trace_memory_flow, trace_register_flow, trace_call_tree, trace_loop_detect
from .advanced_recon import tile_hunt, font_hunt
from .debug_export import export_debug_script
from .v3 import plugin_list, plugin_doctor, backend_profile, backend_script, trace_corpus_test, disasm, cfg_from_trace, cfg_from_disasm, value_flow, infer_table, tbl_validate, tbl_decode, tbl_encode, tbl_brute_hint, sandbox_patch, rollback_ips, compat, regression_bundle, package_release_strict, tui_report
from .v4 import graph_build, graph_query, graph_export, graph_dot, confidence_recompute, confidence_explain, trace_batch_correlate, classify_routine, recommend_patch, symbols_import, symbols_export, disasm_routine, compression_hint, fixture_run, state_diff, patch_rank, code_map
from .v5 import sim_run
from .v6 import sim_ppu_query
from .v7 import add_v7_parsers, dispatch_v7
from .v9 import add_v9_parsers, dispatch_v9
from .v10 import add_v10_parsers, dispatch_v10
from .v11 import add_v11_parsers, dispatch_v11
from .v12 import add_v12_parsers, dispatch_v12
from .v13 import add_v13_parsers, dispatch_v13
from .v14 import add_v14_parsers, dispatch_v14
from .v15 import add_v15_parsers, dispatch_v15
from .v16 import add_v16_parsers, dispatch_v16
from .v17 import add_v17_parsers, dispatch_v17
from .v18 import add_v18_parsers, dispatch_v18
from .v19 import add_v19_parsers, dispatch_v19
from .v20 import add_v20_parsers, dispatch_v20
from .v21 import add_v21_parsers, dispatch_v21
from .v22_30 import add_v22_30_parsers, dispatch_v22_30
from .v31 import dispatch_v31


def emit(obj, as_json=False):
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True), flush=True)
    elif isinstance(obj, str):
        print(obj, flush=True)
    else:
        print(json.dumps(obj, indent=2, sort_keys=True), flush=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="romancer", description=f"ROMancer {APP_VERSION}: ROM analysis, safe editing, runtime tools, and scoped verification. Capabilities depend on configured adapters and evidence.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("identify", help="Print supported cartridge header and hash facts.")
    s.add_argument("rom"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("init", help="Create a ROMancer project folder.")
    s.add_argument("project"); s.add_argument("--rom", required=True); s.add_argument("--no-copy", action="store_true"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("report", help="Generate a TXT project report.")
    s.add_argument("project")

    s = sub.add_parser("snes-map", help="Convert SNES CPU address to ROM offset for LoROM/HiROM/ExHiROM.")
    s.add_argument("--mapping", required=True, choices=["lorom", "hirom", "exhirom", "LoROM", "HiROM", "ExHiROM"])
    s.add_argument("--addr", required=True, help="Example: C5:55C0 or C555C0"); s.add_argument("--headered", action="store_true"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("genesis-map", help="Classify a Genesis/Mega Drive 68K address.")
    s.add_argument("--addr", required=True, help="Example: C00004 or 0x00C00004"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("diff", help="Compare original and modified files and output changed regions.")
    s.add_argument("original"); s.add_argument("modified"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("make-ips", help="Create an IPS patch from original and modified files.")
    s.add_argument("original"); s.add_argument("modified"); s.add_argument("--out", required=True); s.add_argument("--json", action="store_true")

    s = sub.add_parser("parse-trace", help="Parse emulator/debugger trace logs into normalized events.")
    s.add_argument("trace"); s.add_argument("--format", default="auto", choices=["auto", "mesen", "bsnes-plus", "blastem", "generic"]); s.add_argument("--max-events", type=int, default=None); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-detect", help="Detect likely trace-log format without fully parsing it.")
    s.add_argument("trace"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-summary", help="Parse a trace and print only summary statistics.")
    s.add_argument("trace"); s.add_argument("--format", default="auto", choices=["auto", "mesen", "bsnes-plus", "blastem", "generic"]); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-filter", help="Filter parsed trace events by address, mnemonic, or PC.")
    s.add_argument("trace"); s.add_argument("--format", default="auto", choices=["auto", "mesen", "bsnes-plus", "blastem", "generic"]); s.add_argument("--addr"); s.add_argument("--mnemonic"); s.add_argument("--pc"); s.add_argument("--max-events", type=int, default=None); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("breakpoint-script", help="Generate a conservative debugger checklist/script for a backend breakpoint target.")
    s.add_argument("--backend", required=True, choices=["mesen", "mesen2", "bsnes-plus", "blastem", "generic"]); s.add_argument("--system", required=True, choices=["nes", "snes", "genesis"]); s.add_argument("--addr", required=True); s.add_argument("--access", default="write", choices=["read", "write", "execute", "rw"]); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("plan-breakpoints", help="Create a debugger-first breakpoint plan for a target address.")
    s.add_argument("--system", required=True, choices=["nes", "snes", "genesis"]); s.add_argument("--addr", required=True); s.add_argument("--access", default="write", choices=["read", "write", "execute", "rw"]); s.add_argument("--goal", default=""); s.add_argument("--backend"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("debugger-guide", help="Generate emulator/backend-specific debugging steps.")
    s.add_argument("--backend", required=True, choices=["mesen", "mesen2", "mesen-s", "bsnes-plus", "blastem", "fceux", "generic"]); s.add_argument("--system", required=True, choices=["nes", "snes", "genesis"]); s.add_argument("--addr", required=True); s.add_argument("--access", default="write", choices=["read", "write", "execute", "rw"]); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-window", help="Extract raw trace context around a line or first address match.")
    s.add_argument("trace"); s.add_argument("--line", type=int); s.add_argument("--addr"); s.add_argument("--before", type=int, default=80); s.add_argument("--after", type=int, default=20); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("correlate-trace", help="Correlate parsed trace events with a target address.")
    s.add_argument("trace"); s.add_argument("--addr", required=True); s.add_argument("--format", default="auto", choices=["auto", "mesen", "bsnes-plus", "blastem", "generic"]); s.add_argument("--window", type=int, default=80); s.add_argument("--max-candidates", type=int, default=25); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("find-routine", help="Find trace-local routine anchors near a target address hit.")
    s.add_argument("trace"); s.add_argument("--addr", required=True); s.add_argument("--format", default="auto", choices=["auto", "mesen", "bsnes-plus", "blastem", "generic"]); s.add_argument("--window", type=int, default=120); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("resolve-pc", help="Resolve CPU PC/address to ROM offset where possible.")
    s.add_argument("--system", required=True, choices=["nes", "snes", "genesis"]); s.add_argument("--pc", required=True); s.add_argument("--rom"); s.add_argument("--mapping", choices=["lorom", "hirom", "exhirom", "LoROM", "HiROM", "ExHiROM"]); s.add_argument("--headered", action="store_true"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("report-trace", help="Generate a human-readable TXT trace report.")
    s.add_argument("trace"); s.add_argument("--addr"); s.add_argument("--format", default="auto", choices=["auto", "mesen", "bsnes-plus", "blastem", "generic"]); s.add_argument("--out")

    s = sub.add_parser("evidence-add", help="Add an evidence claim to a project.")
    s.add_argument("project"); s.add_argument("--claim", required=True); s.add_argument("--status", default="unverified"); s.add_argument("--confidence", type=float, default=0.5); s.add_argument("--detail", default=""); s.add_argument("--json", action="store_true")

    s = sub.add_parser("evidence-list", help="List project evidence.")
    s.add_argument("project"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("ai-bundle", help="Export project identity and evidence as an AI-readable JSON bundle.")
    s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("ai-pack-v2", help="Export project, evidence, trace summaries, and findings as AI evidence pack v2.")
    s.add_argument("project"); s.add_argument("--trace", action="append", default=[]); s.add_argument("--finding", action="append", default=[]); s.add_argument("--out"); s.add_argument("--json", action="store_true")


    s = sub.add_parser("version", help="Print ROMancer version.")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("doctor", help="Check optional Linux/emulator/toolchain dependencies.")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("self-test", help="Run built-in smoke tests against bundled examples.")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("project-status", help="Summarize project identity, evidence, traces, reports, and patches.")
    s.add_argument("project"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("patch-plan", help="Create a conservative candidate patch plan from trace/address evidence.")
    s.add_argument("--system", required=True, choices=["nes", "snes", "genesis"]); s.add_argument("--rom"); s.add_argument("--trace"); s.add_argument("--addr"); s.add_argument("--goal", default=""); s.add_argument("--mapping", choices=["lorom", "hirom", "exhirom", "LoROM", "HiROM", "ExHiROM"]); s.add_argument("--pc"); s.add_argument("--headered", action="store_true"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("validate-patch", help="Compare original/modified ROMs and optional before/after traces.")
    s.add_argument("--original", required=True); s.add_argument("--modified", required=True); s.add_argument("--trace-before"); s.add_argument("--trace-after"); s.add_argument("--addr"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("risk-score", help="Classify a candidate patch as low/medium/high risk.")
    s.add_argument("--system", required=True, choices=["nes", "snes", "genesis"]); s.add_argument("--offset"); s.add_argument("--change", default=""); s.add_argument("--change-len", type=int); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("asar-skeleton", help="Generate a conservative Asar skeleton for a small SNES byte patch.")
    s.add_argument("--mapping", required=True, choices=["lorom", "hirom", "exhirom"]); s.add_argument("--offset"); s.add_argument("--addr"); s.add_argument("--bytes", required=True); s.add_argument("--comment", default="ROMancer candidate patch"); s.add_argument("--out")

    s = sub.add_parser("ips-manifest", help="Create IPS patch plus optional manifest/report sidecars.")
    s.add_argument("--original", required=True); s.add_argument("--modified", required=True); s.add_argument("--patch-out", required=True); s.add_argument("--manifest-out"); s.add_argument("--report-out"); s.add_argument("--reason", default=""); s.add_argument("--json", action="store_true")



    # v0.5 recon commands
    s = sub.add_parser("text-scan", help="Scan ROM for ASCII or .tbl decoded candidate text strings.")
    s.add_argument("rom"); s.add_argument("--system", default="unknown"); s.add_argument("--encoding", default="ascii"); s.add_argument("--tbl"); s.add_argument("--min-length", type=int, default=5); s.add_argument("--terminators", default="00,F7,FF"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("pointer-scan", help="Search for candidate pointer references to a target offset/address.")
    s.add_argument("rom"); s.add_argument("--system", required=True, choices=["nes","snes","genesis","unknown"]); s.add_argument("--target", required=True); s.add_argument("--mapping", default="auto"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("tile-dump", help="Dump raw console tile graphics to a grayscale PNG sheet.")
    s.add_argument("rom"); s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--offset", required=True); s.add_argument("--count", type=int, default=128); s.add_argument("--bpp", type=int, default=4); s.add_argument("--columns", type=int, default=16); s.add_argument("--out", required=True); s.add_argument("--json", action="store_true")

    s = sub.add_parser("palette-dump", help="Dump SNES/Genesis palette candidates and optionally write a preview PNG.")
    s.add_argument("rom"); s.add_argument("--system", required=True, choices=["snes","genesis"]); s.add_argument("--offset", required=True); s.add_argument("--count", type=int, default=16); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("record-scan", help="Inspect a fixed-stride record table region.")
    s.add_argument("rom"); s.add_argument("--start", required=True); s.add_argument("--end", required=True); s.add_argument("--stride", required=True, type=int); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("table-report", help="Create a short TXT report from a recon JSON output.")
    s.add_argument("scan_json"); s.add_argument("--out")

    # v0.6 backend/session commands
    s = sub.add_parser("backend-config", help="Initialize/list/set emulator backend paths.")
    s.add_argument("action", choices=["init","list","set"]); s.add_argument("name", nargs="?"); s.add_argument("path", nargs="?"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("backend-capabilities", help="Report configured/detected backend capabilities.")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("launch", help="Launch configured emulator backend with a ROM.")
    s.add_argument("--backend", required=True); s.add_argument("--rom", required=True); s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("session-template", help="Write a debugger session template.")
    s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--backend", required=True); s.add_argument("--addr", required=True); s.add_argument("--access", default="write"); s.add_argument("--goal", default=""); s.add_argument("--out")

    s = sub.add_parser("watch-traces", help="Single-pass trace folder watcher/import helper.")
    s.add_argument("folder"); s.add_argument("--addr"); s.add_argument("--json", action="store_true")

    # v0.7 knowledge commands
    s = sub.add_parser("symbol", help="Add/list/export project symbols.")
    s.add_argument("project"); s.add_argument("action", choices=["add","list","export"]); s.add_argument("--name"); s.add_argument("--addr"); s.add_argument("--offset"); s.add_argument("--kind", default="unknown"); s.add_argument("--system", default="unknown"); s.add_argument("--status", default="candidate"); s.add_argument("--notes", default=""); s.add_argument("--json", action="store_true")

    s = sub.add_parser("finding", help="Add/list/audit project findings.")
    s.add_argument("project"); s.add_argument("action", choices=["add","list","audit"]); s.add_argument("--claim"); s.add_argument("--status", default="candidate"); s.add_argument("--evidence"); s.add_argument("--confidence", type=float, default=0.5); s.add_argument("--notes", default=""); s.add_argument("--json", action="store_true")

    s = sub.add_parser("routine", help="Add/list candidate routines.")
    s.add_argument("project"); s.add_argument("action", choices=["add","list"]); s.add_argument("--pc"); s.add_argument("--name"); s.add_argument("--status", default="candidate"); s.add_argument("--notes", default=""); s.add_argument("--json", action="store_true")

    s = sub.add_parser("ai-prompt", help="Export a focused AI prompt from project knowledge.")
    s.add_argument("project"); s.add_argument("--goal", required=True); s.add_argument("--out")

    # v0.8 patch workspace commands
    s = sub.add_parser("patch-workspace", help="Create a reproducible patch workspace.")
    s.add_argument("project"); s.add_argument("--name", required=True); s.add_argument("--json", action="store_true")

    s = sub.add_parser("patch-build", help="Build/check a patch workspace from original/modified ROMs.")
    s.add_argument("workspace"); s.add_argument("--original"); s.add_argument("--modified"); s.add_argument("--ips-out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("patch-rebuild", help="Load a patch manifest and report rebuild requirements.")
    s.add_argument("manifest"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("regression-plan", help="Generate a runtime regression checklist.")
    s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--patch"); s.add_argument("--out")

    s = sub.add_parser("patch-compare", help="Compare two binary patch files structurally.")
    s.add_argument("a"); s.add_argument("b"); s.add_argument("--json", action="store_true")

    # v0.9/v1.0 audit and release commands
    s = sub.add_parser("audit-project", help="Audit project evidence, JSON, and patch validation status.")
    s.add_argument("project"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("report-check", help="Check report folder JSON/TXT consistency.")
    s.add_argument("folder"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("package-release", help="Package a patch workspace into a release folder and zip.")
    s.add_argument("workspace"); s.add_argument("--out", required=True); s.add_argument("--json", action="store_true")


    # v2.0 hardening, trace intelligence, and deep recon commands
    s = sub.add_parser("capabilities", help="Print command stability and supported workflow capabilities.")
    s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("rom-doctor", help="Run a conservative ROM identity and patch-safety report.")
    s.add_argument("rom"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("clean-tree", help="Remove __pycache__ and .pyc files from a release tree.")
    s.add_argument("root"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("full-self-test", help="Run full bundled deterministic tests and doctor checks.")
    s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("build-release", help="Create a clean release zip and SHA256 sidecar from a ROMancer tree.")
    s.add_argument("root"); s.add_argument("--out-dir", default="dist"); s.add_argument("--name"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-compare", help="Compare two normalized traces structurally.")
    s.add_argument("a"); s.add_argument("b"); s.add_argument("--format-a", default="auto"); s.add_argument("--format-b", default="auto"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-hot-pc", help="List the most frequently executed PCs in a trace.")
    s.add_argument("trace"); s.add_argument("--format", default="auto"); s.add_argument("--limit", type=int, default=25); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-memory-flow", help="Show reads/writes and nearby loads around a target memory address.")
    s.add_argument("trace"); s.add_argument("--addr", required=True); s.add_argument("--format", default="auto"); s.add_argument("--window", type=int, default=80); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-register-flow", help="Track visible register value changes near a target address or trace start.")
    s.add_argument("trace"); s.add_argument("--register", required=True); s.add_argument("--around-addr"); s.add_argument("--format", default="auto"); s.add_argument("--window", type=int, default=80); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-call-tree", help="Infer a conservative call/return tree from trace mnemonics.")
    s.add_argument("trace"); s.add_argument("--format", default="auto"); s.add_argument("--around-line", type=int); s.add_argument("--window", type=int, default=400); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-loop-detect", help="Find hot repeated PCs that may indicate loops or polling routines.")
    s.add_argument("trace"); s.add_argument("--format", default="auto"); s.add_argument("--limit", type=int, default=50); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("tile-hunt", help="Generate tile sheets across a ROM at fixed offsets for visual reconnaissance.")
    s.add_argument("rom"); s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--bpp", type=int, default=4); s.add_argument("--step", default="0x1000"); s.add_argument("--count", type=int, default=64); s.add_argument("--out-dir", default="tile_hunt"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("font-hunt", help="Find heuristic text/font-like ROM regions.")
    s.add_argument("rom"); s.add_argument("--system", default="unknown"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("export-debug-script", help="Export conservative backend-specific debugger helper text.")
    s.add_argument("--backend", required=True); s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--addr", required=True); s.add_argument("--access", default="write"); s.add_argument("--out"); s.add_argument("--json", action="store_true")


    # v3.5 architecture, verification, static analysis, and strict release commands
    s = sub.add_parser("plugin-list", help="List ROMancer plugin groups and loaded built-ins.")
    s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("plugin-doctor", help="Check built-in plugin registry health.")
    s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("backend-profile", help="Show backend capability profile(s).")
    s.add_argument("backend", nargs="?"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("backend-script", help="Generate backend-specific debugger script/guide text.")
    s.add_argument("--backend", required=True); s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--addr", required=True); s.add_argument("--access", default="write"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-corpus-test", help="Run parser tests against trace_corpus or bundled examples.")
    s.add_argument("--root", default="trace_corpus"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("disasm", help="Conservative static disassembly around a ROM offset or PC.")
    s.add_argument("rom"); s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--offset"); s.add_argument("--pc"); s.add_argument("--mapping"); s.add_argument("--count", type=int, default=80); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("cfg-from-trace", help="Build a simple CFG/DOT graph from trace PC transitions.")
    s.add_argument("trace"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("cfg-from-disasm", help="Build a conservative CFG/DOT graph from static disassembly.")
    s.add_argument("rom"); s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--offset"); s.add_argument("--pc"); s.add_argument("--mapping"); s.add_argument("--count", type=int, default=200); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("value-flow", help="Trace-side heuristic: find likely source of value written to target address.")
    s.add_argument("trace"); s.add_argument("--target-addr", required=True); s.add_argument("--window", type=int, default=200); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("infer-table", help="Infer likely fields in a fixed-stride ROM table.")
    s.add_argument("rom"); s.add_argument("--start", required=True); s.add_argument("--end", required=True); s.add_argument("--stride", type=int, required=True); s.add_argument("--system", default="snes"); s.add_argument("--mapping", default="hirom"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("tbl", help=".tbl text encoding workbench.")
    s.add_argument("action", choices=["validate","decode","encode","brute-hint"]); s.add_argument("--tbl"); s.add_argument("--rom"); s.add_argument("--offset"); s.add_argument("--length", type=int); s.add_argument("--text"); s.add_argument("--known"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("sandbox-patch", help="Safely apply expected-before byte patch to a sandbox copy and create IPS plus rollback IPS.")
    s.add_argument("rom"); s.add_argument("--offset", required=True); s.add_argument("--before", required=True); s.add_argument("--after", required=True); s.add_argument("--out-dir", default="sandbox_patch"); s.add_argument("--name", default="candidate"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("rollback-ips", help="Create an IPS patch that converts modified ROM back to original ROM.")
    s.add_argument("--original", required=True); s.add_argument("--modified", required=True); s.add_argument("--out", required=True); s.add_argument("--json", action="store_true")

    s = sub.add_parser("compat", help="Project-local ROM compatibility database.")
    s.add_argument("action", choices=["add","check","list"]); s.add_argument("--rom"); s.add_argument("--name"); s.add_argument("--project", default="."); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("regression-bundle", help="Create structured regression evidence bundle folders and checklist.")
    s.add_argument("project"); s.add_argument("--patch", required=True); s.add_argument("--out-dir", default="regression_bundle"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("package-release-strict", help="Package release with additional strict gate metadata.")
    s.add_argument("workspace"); s.add_argument("--out", default="release"); s.add_argument("--allow-unverified", action="store_true"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("tui-report", help="Generate a terminal dashboard preview report.")
    s.add_argument("--project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")


    # v4.0 analysis engine commands
    s = sub.add_parser("graph", help="Build/query/export/dot project evidence graph.")
    s.add_argument("action", choices=["build","query","export","dot"]); s.add_argument("project"); s.add_argument("--query"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("confidence", help="Recompute or explain evidence confidence scores.")
    s.add_argument("action", choices=["recompute","explain"]); s.add_argument("project"); s.add_argument("--finding"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("trace-batch", help="Correlate multiple traces against common/unique PCs and optional target address.")
    s.add_argument("action", choices=["correlate"]); s.add_argument("traces", nargs="+"); s.add_argument("--addr"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("classify-routine", help="Classify a routine from trace evidence.")
    s.add_argument("--trace"); s.add_argument("--pc"); s.add_argument("--project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("recommend-patch", help="Rank safer candidate patch points from traces/project evidence.")
    s.add_argument("--project"); s.add_argument("--trace", action="append", dest="traces"); s.add_argument("--addr"); s.add_argument("--goal", default=""); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("symbols", help="Import/export debugger-compatible symbols.")
    s.add_argument("action", choices=["import","export"]); s.add_argument("project"); s.add_argument("--file"); s.add_argument("--format", default="generic-json"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("disasm-routine", help="Disassemble and summarize a candidate routine.")
    s.add_argument("rom"); s.add_argument("--system", required=True, choices=["nes","snes","genesis"]); s.add_argument("--pc"); s.add_argument("--offset"); s.add_argument("--mapping"); s.add_argument("--count", type=int, default=160); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("compression-hint", help="Detect high-entropy/filler/tile-like ROM regions.")
    s.add_argument("rom"); s.add_argument("--system", default="unknown"); s.add_argument("--window", type=int, default=4096); s.add_argument("--step", type=int, default=4096); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("fixture", help="Run built-in verification fixtures.")
    s.add_argument("action", choices=["run"]); s.add_argument("which", nargs="?", default="all"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("state-diff", help="Raw binary diff for emulator save-states or arbitrary state files.")
    s.add_argument("before"); s.add_argument("after"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("patch-rank", help="Alias-style patch candidate ranking from traces/project evidence.")
    s.add_argument("--project"); s.add_argument("--trace", action="append", dest="traces"); s.add_argument("--addr"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("code-map", help="Build a trace-derived code map of hot PCs, calls, branches, and writes.")
    s.add_argument("trace"); s.add_argument("--out"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("sim-run", help="[v5] Execute a candidate routine on a simulated 65816 CPU with controlled fake state (not a full emulator: no PPU/APU/DMA/timing).")
    s.add_argument("rom", help="Path to the ROM (or patched candidate) to execute code from.")
    s.add_argument("--entry", required=True, help="BB:AAAA -- bank:PC to begin execution at.")
    s.add_argument("--set-mem", action="append", help="Repeatable. BB:AAAA=VALUE (8-bit) or BB:AAAA=VALUE:16 (16-bit) memory preset before running.")
    s.add_argument("--set-reg", action="append", help="Repeatable. REG=VALUE where REG in A,X,Y,S,D,DB,PB,M,XF,P.")
    s.add_argument("--stop-at", help="BB:AAAA -- halt cleanly once PB:PC reaches this address.")
    s.add_argument("--stop-on-jsr", action="append", help="Repeatable. Halt BEFORE executing a JSR/JSL whose target matches (4 hex=abs, 6 hex=long), instead of simulating into the callee.")
    s.add_argument("--push-return", help="BB:AAAA (optionally suffixed :RTS) -- pushes a fake return frame before running, so a routine ending in RTL/RTS has somewhere valid to land.")
    s.add_argument("--max-steps", type=int, default=2000)
    s.add_argument("--out")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("sim-ppu-query", help="[v6] Run the CPU+PPU simulator and answer a structured visual query (sprites, tilemap, tile pixels) instead of producing a screenshot to eyeball.")
    s.add_argument("rom")
    s.add_argument("--entry", required=True, help="BB:AAAA -- bank:PC to begin execution at.")
    s.add_argument("--set-mem", action="append")
    s.add_argument("--set-reg", action="append")
    s.add_argument("--stop-at")
    s.add_argument("--max-steps", type=int, default=5000)
    s.add_argument("--query", default="sprites", choices=["sprites", "sprites_by_tile", "tilemap", "tile_ascii"])
    s.add_argument("--layer", type=int, default=1)
    s.add_argument("--tx", type=int, default=0)
    s.add_argument("--ty", type=int, default=0)
    s.add_argument("--w", type=int, default=8)
    s.add_argument("--h", type=int, default=4)
    s.add_argument("--tile-id", type=int, default=0)
    s.add_argument("--out")
    s.add_argument("--json", action="store_true")

    add_v7_parsers(sub)
    add_v9_parsers(sub)
    add_v10_parsers(sub)
    add_v11_parsers(sub)
    add_v12_parsers(sub)
    add_v13_parsers(sub)
    add_v14_parsers(sub)
    add_v15_parsers(sub)
    add_v16_parsers(sub)
    add_v17_parsers(sub)
    add_v18_parsers(sub)
    add_v19_parsers(sub)
    add_v20_parsers(sub)
    add_v21_parsers(sub)
    add_v22_30_parsers(sub)
    add_history_commands(sub)
    add_contract_commands(sub)
    add_system_commands(sub)
    add_capture_commands(sub)
    add_script_commands(sub)
    add_layout_commands(sub)
    add_menu_commands(sub)
    add_engineering_commands(sub)
    args = p.parse_args(argv)

    system_result = dispatch_systems(args)
    if system_result is not None:
        from .script_cli import encode_result
        try:
            sys.stdout.buffer.write(encode_result(system_result));sys.stdout.buffer.flush()
        except (OSError,ValueError):return 1
        return 130 if system_result.get('status')=='CANCELLED' else (0 if system_result.get('ok') is True else 1)

    engineering_result = dispatch_engineering(args)
    if engineering_result is not None:
        from .script_cli import encode_result
        try:
            sys.stdout.buffer.write(encode_result(engineering_result))
            sys.stdout.buffer.flush()
        except (OSError, ValueError):return 1
        return 130 if engineering_result.get('status') == 'CANCELLED' else (0 if engineering_result.get('ok') is True else 1)

    capture_result = dispatch_captures(args)
    if capture_result is not None:
        emit_capture(capture_result)
        return 0 if capture_result.get('ok') is True else 1

    script_result = dispatch_scripts(args)
    if script_result is not None:
        emit_script(script_result)
        return 130 if script_result.get('cancelled') else (0 if script_result.get('ok') is True else 1)

    layout_result = dispatch_layout(args)
    if layout_result is not None:
        emit_layout(layout_result)
        if layout_result.get('cancelled') or layout_result.get('status') == 'CANCELLED':
            return 130
        return 0 if layout_result.get('ok') is True else 1

    menu_result = dispatch_menu(args)
    if menu_result is not None:
        cancelled = menu_result.get('cancelled') or menu_result.get('status') == 'CANCELLED'
        try:
            emit_menu(menu_result, args.json)
        except (OSError, ValueError):
            return 130 if cancelled else 1
        if cancelled:
            return 130
        return 0 if menu_result.get('ok') is True else 1

    contract_result = dispatch_contracts(args)
    if contract_result is not None:
        emit(contract_result, getattr(args, 'json', False))
        return 0 if contract_result.get('ok') is True else 1

    history_result = dispatch_history(args)
    if history_result is not None:
        emit(history_result, getattr(args, 'json', False))
        return 0 if history_result.get('ok') is True else 1

    handled, v31_result = dispatch_v31(args)
    if handled:
        emit(v31_result, getattr(args, "json", False))
        return 1 if isinstance(v31_result, dict) and v31_result.get('ok') is False else 0

    handled, v30_result = dispatch_v22_30(args)
    if handled:
        emit(v30_result, getattr(args, "json", False))
        return 1 if isinstance(v30_result, dict) and v30_result.get('ok') is False else 0

    handled, v21_result = dispatch_v21(args)
    if handled:
        emit(v21_result, getattr(args, "json", False))
        return 0
    handled, v20_result = dispatch_v20(args)
    if handled:
        emit(v20_result, getattr(args, "json", False))
        return 0
    handled, v19_result = dispatch_v19(args)
    if handled:
        emit(v19_result, getattr(args, "json", False))
        return 0
    handled, v18_result = dispatch_v18(args)
    if handled:
        emit(v18_result, getattr(args, "json", False))
        return 0
    handled, v17_result = dispatch_v17(args)
    if handled:
        emit(v17_result, getattr(args, "json", False))
        return 0
    handled, v16_result = dispatch_v16(args)
    if handled:
        emit(v16_result, getattr(args, "json", False))
        return 0
    handled, v15_result = dispatch_v15(args)
    if handled:
        emit(v15_result, getattr(args, "json", False))
        return 0
    handled, v14_result = dispatch_v14(args)
    if handled:
        emit(v14_result, getattr(args, "json", False))
        return 0
    handled, v13_result = dispatch_v13(args)
    if handled:
        emit(v13_result, getattr(args, "json", False))
        return 0
    handled, v12_result = dispatch_v12(args)
    if handled:
        emit(v12_result, getattr(args, "json", False))
        return 0
    handled, v11_result = dispatch_v11(args)
    if handled:
        emit(v11_result, getattr(args, "json", False))
        return 0
    handled, v10_result = dispatch_v10(args)
    if handled:
        emit(v10_result, getattr(args, "json", False))
        return 1 if isinstance(v10_result, dict) and v10_result.get('ok') is False else 0

    handled, v9_result = dispatch_v9(args)
    if handled:
        emit(v9_result, getattr(args, "json", False))
        return 0

    handled, v7_result = dispatch_v7(args)
    if handled:
        emit(v7_result, getattr(args, "json", False))
        return 0

    if args.cmd == "identify": emit(identify_rom(args.rom), args.json)
    elif args.cmd == "init": emit(init_project(args.project, args.rom, copy_rom=not args.no_copy), args.json)
    elif args.cmd == "report": emit(project_report(args.project), False)
    elif args.cmd == "snes-map": emit(snes_to_offset(args.addr, args.mapping, args.headered), args.json)
    elif args.cmd == "genesis-map": emit(classify_68k_address(args.addr), args.json)
    elif args.cmd == "diff":
        result = byte_diff(args.original, args.modified)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "make-ips": emit(create_ips(args.original, args.modified, args.out), args.json)
    elif args.cmd == "parse-trace":
        result = parse_trace(args.trace, trace_format=args.format, max_events=args.max_events)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "trace-detect": emit(detect_trace_format(args.trace), args.json)
    elif args.cmd == "trace-summary":
        result = trace_summary(args.trace, trace_format=args.format)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "trace-filter":
        result = filter_trace(args.trace, trace_format=args.format, addr=args.addr, mnemonic=args.mnemonic, pc=args.pc, max_events=args.max_events)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "breakpoint-script":
        from .backend_scripts import breakpoint_script, write_breakpoint_script
        result = write_breakpoint_script(args.out, args.backend, args.system, args.addr, args.access) if args.out else breakpoint_script(args.backend, args.system, args.addr, args.access)
        emit(result, args.json)
    elif args.cmd == "plan-breakpoints":
        result = plan_breakpoints(args.system, args.addr, args.access, args.goal, args.backend)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "debugger-guide":
        result = debugger_guide(args.backend, args.system, args.addr, args.access)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "trace-window":
        result = trace_window(args.trace, line=args.line, addr=args.addr, before=args.before, after=args.after, out=args.out)
        emit(result if args.json else result.get("text", result), args.json)
    elif args.cmd == "correlate-trace":
        result = correlate_trace(args.trace, args.addr, trace_format=args.format, window=args.window, max_candidates=args.max_candidates)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "find-routine":
        result = find_routine(args.trace, args.addr, trace_format=args.format, window=args.window)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "resolve-pc":
        result = resolve_pc(args.system, args.pc, rom=args.rom, mapping=args.mapping, headered=args.headered)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "report-trace": emit(report_trace(args.trace, addr=args.addr, trace_format=args.format, out=args.out), False)
    elif args.cmd == "evidence-add": emit(add_evidence(args.project, args.claim, args.status, args.confidence, args.detail), args.json)
    elif args.cmd == "evidence-list": emit(load_evidence(args.project), args.json)
    elif args.cmd == "ai-bundle":
        result = export_ai_bundle(args.project)
        if args.out: write_json(args.out, result)
        emit(result, args.json)
    elif args.cmd == "ai-pack-v2":
        result = ai_bundle_v2(args.project, traces=args.trace, findings=args.finding, out=args.out)
        emit(result, args.json)
    elif args.cmd == "version": emit({"tool": "ROMancer", "version": APP_VERSION}, args.json)
    elif args.cmd == "doctor": emit(doctor(), args.json)
    elif args.cmd == "self-test": emit(self_test(), args.json)
    elif args.cmd == "project-status": emit(project_status(args.project), args.json)
    elif args.cmd == "patch-plan":
        result = patch_plan(args.system, rom=args.rom, trace=args.trace, addr=args.addr, goal=args.goal, mapping=args.mapping, pc=args.pc, headered=args.headered, out=args.out)
        emit(result, args.json)
    elif args.cmd == "validate-patch":
        result = validate_patch(args.original, args.modified, trace_before=args.trace_before, trace_after=args.trace_after, addr=args.addr, out=args.out)
        emit(result, args.json)
    elif args.cmd == "risk-score":
        result = risk_score(args.system, offset=args.offset, change=args.change, change_len=args.change_len, out=args.out)
        emit(result, args.json)
    elif args.cmd == "asar-skeleton": emit(asar_skeleton(args.mapping, offset=args.offset, addr=args.addr, bytes_text=args.bytes, comment=args.comment, out=args.out), False)
    elif args.cmd == "ips-manifest":
        result = ips_manifest(args.original, args.modified, args.patch_out, manifest_out=args.manifest_out, report_out=args.report_out, reason=args.reason)
        emit(result, args.json)
    elif args.cmd == "text-scan": emit(text_scan(args.rom, args.system, args.encoding, args.tbl, args.min_length, args.terminators, args.out), args.json)
    elif args.cmd == "pointer-scan": emit(pointer_scan(args.rom, args.system, args.target, args.mapping, out=args.out), args.json)
    elif args.cmd == "tile-dump": emit(tile_dump(args.rom, args.system, args.offset, args.count, args.bpp, args.columns, args.out), args.json)
    elif args.cmd == "palette-dump": emit(palette_dump(args.rom, args.system, args.offset, args.count, args.out), args.json)
    elif args.cmd == "record-scan": emit(record_scan(args.rom, args.start, args.end, args.stride, args.out), args.json)
    elif args.cmd == "table-report": emit(table_report(args.scan_json, args.out), False)
    elif args.cmd == "backend-config": emit(backend_config(args.action, args.name, args.path), args.json)
    elif args.cmd == "backend-capabilities": emit(backend_capabilities(), args.json)
    elif args.cmd == "launch": emit(launch(args.backend, args.rom, dry_run=args.dry_run), args.json)
    elif args.cmd == "session-template": emit(session_template(args.system, args.backend, args.addr, args.access, args.goal, args.out), False)
    elif args.cmd == "watch-traces": emit(watch_traces(args.folder, args.addr), args.json)
    elif args.cmd == "symbol": emit(symbol_cmd(args.project, args.action, args.name, args.addr, args.offset, args.kind, args.system, args.status, args.notes), args.json)
    elif args.cmd == "finding": emit(finding_cmd(args.project, args.action, args.claim, args.status, args.evidence, args.confidence, args.notes), args.json)
    elif args.cmd == "routine": emit(routine_cmd(args.project, args.action, args.pc, args.name, args.status, args.notes), args.json)
    elif args.cmd == "ai-prompt": emit(ai_prompt(args.project, args.goal, args.out), False)
    elif args.cmd == "patch-workspace": emit(patch_workspace(args.project, args.name), args.json)
    elif args.cmd == "patch-build": emit(patch_build(args.workspace, args.original, args.modified, args.ips_out), args.json)
    elif args.cmd == "patch-rebuild": emit(patch_rebuild(args.manifest), args.json)
    elif args.cmd == "regression-plan": emit(regression_plan(args.system, args.patch, args.out), False)
    elif args.cmd == "patch-compare": emit(patch_compare(args.a, args.b), args.json)
    elif args.cmd == "audit-project": emit(audit_project(args.project), args.json)
    elif args.cmd == "report-check": emit(report_check(args.folder), args.json)
    elif args.cmd == "package-release": emit(package_release(args.workspace, args.out), args.json)
    elif args.cmd == "capabilities":
        result = capabilities(args.out); emit(result, args.json)
    elif args.cmd == "rom-doctor":
        result = rom_doctor(args.rom, args.out); emit(result, args.json)
    elif args.cmd == "clean-tree": emit(clean_tree(args.root), args.json)
    elif args.cmd == "full-self-test":
        result = full_self_test(args.out); emit(result, args.json)
        return 0 if result.get('ok') is True else 1
    elif args.cmd == "build-release": emit(build_release(args.root, args.out_dir, args.name), args.json)
    elif args.cmd == "trace-compare":
        result = trace_compare(args.a, args.b, args.format_a, args.format_b, args.out); emit(result, args.json)
    elif args.cmd == "trace-hot-pc":
        result = trace_hot_pc(args.trace, args.format, args.limit, args.out); emit(result, args.json)
    elif args.cmd == "trace-memory-flow":
        result = trace_memory_flow(args.trace, args.addr, args.format, args.window, args.out); emit(result, args.json)
    elif args.cmd == "trace-register-flow":
        result = trace_register_flow(args.trace, args.register, args.format, args.around_addr, args.window, args.out); emit(result, args.json)
    elif args.cmd == "trace-call-tree":
        result = trace_call_tree(args.trace, args.format, args.around_line, args.window, args.out); emit(result, args.json)
    elif args.cmd == "trace-loop-detect":
        result = trace_loop_detect(args.trace, args.format, args.limit, args.out); emit(result, args.json)
    elif args.cmd == "tile-hunt": emit(tile_hunt(args.rom, args.system, args.bpp, args.step, args.count, args.out_dir), args.json)
    elif args.cmd == "font-hunt": emit(font_hunt(args.rom, args.system, args.out), args.json)
    elif args.cmd == "export-debug-script": emit(export_debug_script(args.backend, args.system, args.addr, args.access, args.out), args.json)
    elif args.cmd == "plugin-list": emit(plugin_list(args.out), args.json)
    elif args.cmd == "plugin-doctor": emit(plugin_doctor(args.out), args.json)
    elif args.cmd == "backend-profile": emit(backend_profile(args.backend, args.out), args.json)
    elif args.cmd == "backend-script": emit(backend_script(args.backend, args.system, args.addr, args.access, args.out), args.json)
    elif args.cmd == "trace-corpus-test": emit(trace_corpus_test(args.root, args.out), args.json)
    elif args.cmd == "disasm": emit(disasm(args.rom, args.system, args.offset, args.pc, args.mapping, args.count, args.out), args.json)
    elif args.cmd == "cfg-from-trace": emit(cfg_from_trace(args.trace, args.out), args.json)
    elif args.cmd == "cfg-from-disasm": emit(cfg_from_disasm(args.rom, args.system, args.offset, args.pc, args.mapping, args.count, args.out), args.json)
    elif args.cmd == "value-flow": emit(value_flow(args.trace, args.target_addr, args.window, args.out), args.json)
    elif args.cmd == "infer-table": emit(infer_table(args.rom, args.start, args.end, args.stride, args.system, args.mapping, args.out), args.json)
    elif args.cmd == "tbl":
        if args.action == "validate": emit(tbl_validate(args.tbl, args.out), args.json)
        elif args.action == "decode": emit(tbl_decode(args.rom, args.offset, args.length or 32, args.tbl, args.out), args.json)
        elif args.action == "encode": emit(tbl_encode(args.text or "", args.tbl, args.out), args.json)
        elif args.action == "brute-hint": emit(tbl_brute_hint(args.rom, args.offset, args.known or "", args.length, args.out), args.json)
    elif args.cmd == "sandbox-patch": emit(sandbox_patch(args.rom, args.offset, args.before, args.after, args.out_dir, args.name), args.json)
    elif args.cmd == "rollback-ips": emit(rollback_ips(args.original, args.modified, args.out), args.json)
    elif args.cmd == "compat": emit(compat(args.action, args.rom, args.name, args.project, args.out), args.json)
    elif args.cmd == "regression-bundle": emit(regression_bundle(args.project, args.patch, args.out_dir), args.json)
    elif args.cmd == "package-release-strict": emit(package_release_strict(args.workspace, args.out, fail_on_unverified=not args.allow_unverified), args.json)
    elif args.cmd == "tui-report": emit(tui_report(args.project, args.out), args.json)
    elif args.cmd == "graph":
        if args.action == "build": emit(graph_build(args.project, args.out), args.json)
        elif args.action == "query": emit(graph_query(args.project, args.query or "", args.out), args.json)
        elif args.action == "export": emit(graph_export(args.project, args.out or str(__import__('pathlib').Path(args.project)/'reports'/'project_graph_export.json')), args.json)
        elif args.action == "dot": emit(graph_dot(args.project, args.out), args.json)
    elif args.cmd == "confidence":
        if args.action == "recompute": emit(confidence_recompute(args.project, args.out), args.json)
        elif args.action == "explain": emit(confidence_explain(args.project, args.finding or "", args.out), args.json)
    elif args.cmd == "trace-batch":
        if args.action == "correlate": emit(trace_batch_correlate(args.traces, args.addr, args.out), args.json)
    elif args.cmd == "classify-routine": emit(classify_routine(args.trace, args.pc, args.project, args.out), args.json)
    elif args.cmd == "recommend-patch": emit(recommend_patch(args.project, args.traces, args.addr, args.goal, args.out), args.json)
    elif args.cmd == "symbols":
        if args.action == "import": emit(symbols_import(args.project, args.file, args.format, args.out), args.json)
        elif args.action == "export": emit(symbols_export(args.project, args.format, args.out), args.json)
    elif args.cmd == "disasm-routine": emit(disasm_routine(args.rom, args.system, args.pc, args.offset, args.mapping, args.count, args.out), args.json)
    elif args.cmd == "compression-hint": emit(compression_hint(args.rom, args.system, args.window, args.step, args.out), args.json)
    elif args.cmd == "fixture":
        if args.action == "run": emit(fixture_run(args.which, args.out), args.json)
    elif args.cmd == "state-diff": emit(state_diff(args.before, args.after, args.out), args.json)
    elif args.cmd == "patch-rank": emit(patch_rank(args.project, args.traces, args.addr, args.out), args.json)
    elif args.cmd == "code-map": emit(code_map(args.trace, args.out), args.json)
    elif args.cmd == "sim-run":
        emit(sim_run(args.rom, args.entry, set_mem=args.set_mem, set_reg=args.set_reg,
                      stop_at=args.stop_at, stop_on_jsr=args.stop_on_jsr,
                      push_return=args.push_return,
                      max_steps=args.max_steps, out=args.out), args.json)
    elif args.cmd == "sim-ppu-query":
        emit(sim_ppu_query(args.rom, args.entry, set_mem=args.set_mem, set_reg=args.set_reg,
                            max_steps=args.max_steps, stop_at=args.stop_at, query=args.query,
                            layer=args.layer, tx=args.tx, ty=args.ty, w=args.w, h=args.h,
                            tile_id=args.tile_id, out=args.out), args.json)
    return 0
