from __future__ import annotations

"""Capability-negotiated debugger abstraction for ROMancer v10.

The abstraction separates *documented backend capability* from *transport actually
available to this ROMancer process*. A backend profile can truthfully say that an
emulator supports a watchpoint while ROMancer still reports live_control=False if
no machine-readable bridge has been configured.
"""

from dataclasses import dataclass, asdict

from typing import Any
import shutil


CAPABILITIES = {
    "run", "pause", "reset", "step_instruction", "step_over", "step_out",
    "step_frame", "read_registers", "write_registers", "read_memory",
    "write_memory", "execute_breakpoint", "read_watchpoint", "write_watchpoint",
    "callstack", "trace", "code_data_log", "access_counters", "ppu_state",
    "vdp_state", "savestate", "input_injection", "screenshot"
}


@dataclass(frozen=True)
class BackendProfile:
    id: str
    systems: tuple[str, ...]
    documented_capabilities: tuple[str, ...]
    transport: str
    live_control: bool
    executable_names: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["detected_executable"] = next((shutil.which(x) for x in self.executable_names if shutil.which(x)), None)
        d["capability_count"] = len(self.documented_capabilities)
        return d


# These profiles state only what the cited backend documentation exposes. They do
# not claim that ROMancer can automate the backend unless live_control=True.
PROFILES: dict[str, BackendProfile] = {'blastem': BackendProfile(id='blastem', systems=('genesis', 'mega-drive'), documented_capabilities=('run', 'pause', 'step_instruction', 'step_over', 'execute_breakpoint', 'write_watchpoint', 'callstack', 'read_memory', 'read_registers', 'trace', 'vdp_state'), transport='native command-line debugger; interactive bridge not bundled', live_control=False, executable_names=('blastem',), notes=('BlastEm documents breakpoint, watchpoint, continue, advance, step, next, over, backtrace and print/display commands.', 'Backtrace is explicitly heuristic in BlastEm documentation.'), source_urls=('https://github.com/libretro/blastem',)), 'mesen2': BackendProfile(id='mesen2', systems=('nes', 'snes', 'gb', 'gbc', 'pc-engine', 'sms', 'game-gear'), documented_capabilities=('run', 'pause', 'step_instruction', 'step_over', 'step_out', 'execute_breakpoint', 'read_watchpoint', 'write_watchpoint', 'callstack', 'trace', 'code_data_log', 'access_counters', 'ppu_state', 'savestate', 'input_injection', 'screenshot'), transport='Lua/debugger integration required', live_control=False, executable_names=('Mesen', 'mesen', 'Mesen2', 'mesen2'), notes=('Mesen2 debugger interfaces expose breakpoint manager, callstack manager, trace logger, PPU tools and step-back infrastructure.', 'Its Lua documentation exposes CDL and access-counter retrieval among other debugger-oriented functions.'), source_urls=('https://github.com/SourMesen/Mesen2/blob/master/Core/Debugger/IDebugger.h', 'https://github.com/SourMesen/Mesen2/blob/master/UI/Debugger/Documentation/LuaDocumentation.json')), 'offline-trace': BackendProfile(id='offline-trace', systems=('nes', 'snes', 'genesis'), documented_capabilities=('trace',), transport='ROMancer normalized trace parser', live_control=True, notes=('Provides deterministic offline causal analysis only; it cannot stop a running emulator.',)), 'mock': BackendProfile(id='mock', systems=('test',), documented_capabilities=tuple(sorted(CAPABILITIES)), transport='in-process deterministic test adapter', live_control=True, notes=('Synthetic adapter used only by ROMancer self-tests.',))}


def list_debug_backends() -> dict[str, Any]:
    return {
        "tool": "ROMancer", "version_feature": "v10 debugger adapters",
        "backends": {k: v.to_dict() for k, v in PROFILES.items()},
        "policy": "documented capability is not equivalent to configured live control"
    }


def debug_backend_profile(name: str) -> dict[str, Any]:
    key = name.lower()
    if key not in PROFILES:
        raise ValueError(f"Unknown v10 debugger backend: {name}. Known: {', '.join(sorted(PROFILES))}")
    return PROFILES[key].to_dict()


def debugger_plan(name: str, *, address: str, access: str='write', goal: str='') -> dict[str, Any]:
    """Generate a conservative human/machine integration plan without pretending live control exists."""
    p = PROFILES.get(name.lower())
    if not p:
        raise ValueError(f'Unknown backend: {name}')
    access = access.lower()
    required = 'execute_breakpoint' if access == 'execute' else 'read_watchpoint' if access == 'read' else 'write_watchpoint'
    supported = required in p.documented_capabilities
    commands: list[str] = []
    if p.id == 'blastem':
        if access == 'execute':
            commands = [f'breakpoint {address}', 'continue', 'backtrace']
        else:
            commands = [f'watchpoint {address}', 'continue', 'backtrace']
    elif p.id == 'mesen2':
        commands = ['Configure a debugger breakpoint/memory callback for the target address.', 'Capture CPU state, callstack/trace context, and CDL/access-counter evidence where supported.']
    else:
        commands = ['Backend is analysis-only or synthetic; no external debugger command generated.']
    return {'backend': p.to_dict(), 'goal': goal, 'address': address, 'access': access, 'required_capability': required, 'documented_supported': supported, 'live_automation_available': p.live_control, 'plan': commands, 'status': 'ready' if supported else 'unsupported'}


class MockDebugAdapter:
    """Deterministic adapter used to prove the v10 API itself."""
    def __init__(self, program: list[dict[str, Any]] | None = None):
        self.program = program or []
        self.index = 0
        self.registers = {"pc": 0, "a": 0, "x": 0, "y": 0, "sp": 0x1FF}
        self.memory: dict[int, int] = {}
        self.breakpoints: set[int] = set()
        self.watch_writes: set[int] = set()
        self.events: list[dict[str, Any]] = []

    def capabilities(self) -> set[str]: return set(PROFILES["mock"].documented_capabilities)
    def get_registers(self) -> dict[str, int]: return dict(self.registers)
    def read_memory(self, addr: int, size: int = 1) -> bytes: return bytes(self.memory.get(addr+i, 0) for i in range(size))
    def write_memory(self, addr: int, data: bytes) -> None:
        for i,b in enumerate(data): self.memory[addr+i] = b
    def set_breakpoint(self, addr: int) -> None: self.breakpoints.add(addr)
    def set_write_watchpoint(self, addr: int) -> None: self.watch_writes.add(addr)
    def step_instruction(self) -> dict[str, Any]:
        if self.index >= len(self.program): return {"halted": True}
        ins = dict(self.program[self.index]); self.index += 1
        self.registers["pc"] = int(ins.get("pc", self.index))
        if "a" in ins: self.registers["a"] = int(ins["a"])
        event = {"pc": self.registers["pc"], "registers": self.get_registers(), "instruction": ins.get("instruction", "NOP")}
        if "write" in ins:
            addr, value = ins["write"]
            old = self.memory.get(int(addr), 0); self.memory[int(addr)] = int(value) & 0xFF
            event["memory_write"] = {"address": int(addr), "old": old, "new": int(value) & 0xFF}
            event["watchpoint_hit"] = int(addr) in self.watch_writes
        event["breakpoint_hit"] = self.registers["pc"] in self.breakpoints
        self.events.append(event)
        return event

    def run_until_stop(self, max_steps: int = 1000) -> dict[str, Any]:
        for _ in range(max_steps):
            e = self.step_instruction()
            if e.get("halted") or e.get("breakpoint_hit") or e.get("watchpoint_hit"):
                return e
        return {"timeout": True, "steps": max_steps}
