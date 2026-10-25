from __future__ import annotations

from pathlib import Path


def breakpoint_script(backend: str, system: str, address: str, access: str = "write") -> dict:
    b = backend.lower()
    s = system.lower()
    access_l = access.lower()
    lines: list[str] = []
    notes: list[str] = []

    if b in {"mesen", "mesen2"}:
        lines = [
            f"# Mesen debugger setup reminder for {s}",
            f"# Add a CPU memory breakpoint on {address} with access={access_l}.",
            "# Enable Trace Logger when you need instruction context before/after the hit.",
            "# Export the trace log, then run: romancer parse-trace TRACE --format mesen --json",
        ]
        notes.append("Mesen breakpoints are usually configured through the debugger UI; this file is a reproducible checklist, not a Mesen automation script.")
    elif b in {"bsnes-plus", "bsnes"}:
        lines = [
            f"# bsnes-plus SNES debugger setup reminder",
            f"# Add breakpoint: bus {access_l} at {address}",
            "# Enable Tools > Debugger > Trace when instruction history is needed.",
            "# Exported trace logs can be parsed with: romancer parse-trace TRACE --format bsnes-plus --json",
        ]
        notes.append("bsnes-plus supports real-time instruction trace logs; ROMancer imports the text trace after export.")
    elif b == "blastem":
        # BlastEm debugger syntax has varied over time; keep this conservative.
        lines = [
            f"# BlastEm 68K debugger checklist",
            f"# Use `breakpoint ADDRESS` for execute breaks or `watchpoint ADDRESS [SIZE]` for a memory watchpoint.",
            "# Use step/continue/backtrace/register display commands to capture context.",
            "# Save console output to a text file, then run: romancer parse-trace TRACE --format blastem --json",
        ]
        notes.append("BlastEm exposes a command-line debugger. BlastEm documents breakpoint/watchpoint command names; verify debugger help for the active context and local build.")
    else:
        lines = [
            f"# Generic emulator debugger checklist",
            f"# Target address: {address}",
            f"# Access type: {access_l}",
            "# Export logs as text and parse with: romancer parse-trace TRACE --format generic --json",
        ]
        notes.append("Unknown backend. Generated generic instructions only.")

    return {"backend": backend, "system": system, "address": address, "access": access_l, "script_text": "\n".join(lines) + "\n", "notes": notes}


def write_breakpoint_script(out: str | Path, backend: str, system: str, address: str, access: str = "write") -> dict:
    result = breakpoint_script(backend, system, address, access)
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(result["script_text"], encoding="utf-8")
    result["path"] = str(p)
    return result
