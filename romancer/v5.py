from __future__ import annotations

"""
ROMancer v5: adds a 65816 CPU simulation engine.

Motivation: v0.4 can parse traces exported from a real emulator/debugger,
but has no way to *execute* candidate code itself. During interactive
patch-development sessions, the single most valuable thing turned out to
be a small, honest CPU interpreter: load the ROM (or a patched copy),
set up a plausible register/memory state (usually copied straight from a
real debugger breakpoint capture), run a candidate routine for a bounded
number of steps, and report exactly what happened -- which branches were
taken, what memory changed, and where control ended up.

This is NOT a full SNES emulator. There is no PPU, no APU, no DMA, no
NMI/IRQ timing, and no cycle accuracy. Any opcode touching those systems
is unimplemented on purpose -- the goal is verifying the *logic* of a
candidate patch (branch offsets, addressing modes, 8/16-bit mode
assumptions, stack balance) before ever touching a real emulator, not
replacing one.
"""

import json
from typing import Any

from .systems.snes import snes_to_offset
from .util import parse_int, write_json

VERSION = "5.0.0"


# ---------------------------------------------------------------------------
# CPU core
# ---------------------------------------------------------------------------

class Sim65816:
    """Minimal 65816 interpreter over a LoROM image + simulated WRAM."""

    def __init__(self, rom: bytes):
        self.rom = rom
        self.wram = bytearray(0x20000)  # $7E0000-$7FFFFF
        self.A = 0
        self.X = 0
        self.Y = 0
        self.S = 0x01FF
        self.D = 0x0000
        self.DB = 0x00
        self.PB = 0x00
        self.PC = 0x0000
        self.M = 1   # 1 = 8-bit A, 0 = 16-bit A
        self.XF = 1  # 1 = 8-bit X/Y, 0 = 16-bit X/Y
        self.N = 0
        self.Z = 0
        self.C = 0
        self.V = 0
        self.halted = False
        self.halt_reason = ""
        self.steps_run = 0
        self.trace: list[str] = []
        self.mem_writes: list[dict] = []  # log of every memory write, for diffing
        self.hw_regs: dict[int, int] = {}  # injectable fake hardware register values ($2100-$5FFF space)
        self.hw_reads: list[dict] = []     # log of every hardware register read, for diagnostics
        # $4016/$4017 are the classic serial manual-read joypad registers. Real SNES
        # hardware returns one new data bit per read (MSB-first), advancing an internal
        # shift register each time. We model that explicitly instead of a static value,
        # since the rainwarrior mouse-read routine bit-bangs $4017 sixteen times per frame.
        self.serial_shift_4016 = 0
        self.serial_shift_4017 = 0
        self.serial_bits_remaining_4016 = 0
        self.serial_bits_remaining_4017 = 0

    def load_serial_port2(self, value16: int) -> None:
        """Pre-load the 16-bit value that $4017 will shift out, MSB first, over the
        next 16 reads -- mirroring how a real controller/mouse serial-clocks its report."""
        self.serial_shift_4017 = value16 & 0xFFFF
        self.serial_bits_remaining_4017 = 16

    def load_serial_port1(self, value16: int) -> None:
        self.serial_shift_4016 = value16 & 0xFFFF
        self.serial_bits_remaining_4016 = 16

    def set_hw_reg(self, addr: int, val: int) -> None:
        """Inject a fake value for a hardware register (e.g. $4218 joypad, $421A mouse data)."""
        self.hw_regs[addr & 0xFFFF] = val & 0xFF

    def is_hw_reg(self, bank: int, addr: int) -> bool:
        return (bank <= 0x3F or 0x80 <= bank <= 0xBF) and 0x2100 <= (addr & 0xFFFF) <= 0x5FFF

    # -- LoROM mapping, delegated to ROMancer's own mapper for consistency --
    def _file_offset(self, bank: int, addr: int) -> int | None:
        cpu_addr = ((bank & 0xFF) << 16) | (addr & 0xFFFF)
        if addr < 0x8000 and not (0x7E <= bank <= 0x7F) and not (addr <= 0x1FFF):
            return None
        result = snes_to_offset(f"0x{cpu_addr:06X}", "lorom")
        if "error" in result:
            return None
        return int(result["rom_offset_headerless"], 16)

    def read8(self, bank: int, addr: int) -> int:
        addr &= 0xFFFF
        if 0x7E <= bank <= 0x7F:
            waddr = (bank - 0x7E) * 0x10000 + addr
            return self.wram[waddr & 0x1FFFF]
        if addr <= 0x1FFF and (bank <= 0x3F or 0x80 <= bank <= 0xBF):
            return self.wram[addr & 0x1FFF]
        if self.is_hw_reg(bank, addr):
            if addr == 0x4017:
                if self.serial_bits_remaining_4017 > 0:
                    bit = (self.serial_shift_4017 >> 15) & 1
                    self.serial_shift_4017 = (self.serial_shift_4017 << 1) & 0xFFFF
                    self.serial_bits_remaining_4017 -= 1
                else:
                    bit = 1  # real hardware returns 1s once the report is exhausted
                self.hw_reads.append({"bank": bank, "addr": addr, "value": bit})
                return bit
            if addr == 0x4016:
                if self.serial_bits_remaining_4016 > 0:
                    bit = (self.serial_shift_4016 >> 15) & 1
                    self.serial_shift_4016 = (self.serial_shift_4016 << 1) & 0xFFFF
                    self.serial_bits_remaining_4016 -= 1
                else:
                    bit = 1
                self.hw_reads.append({"bank": bank, "addr": addr, "value": bit})
                return bit
            val = self.hw_regs.get(addr, 0)
            self.hw_reads.append({"bank": bank, "addr": addr, "value": val})
            return val
        fo = self._file_offset(bank, addr)
        if fo is not None and 0 <= fo < len(self.rom):
            return self.rom[fo]
        return 0

    def write8(self, bank: int, addr: int, val: int) -> None:
        addr &= 0xFFFF
        val &= 0xFF
        if 0x7E <= bank <= 0x7F:
            waddr = (bank - 0x7E) * 0x10000 + addr
            self.wram[waddr & 0x1FFFF] = val
        elif addr <= 0x1FFF and (bank <= 0x3F or 0x80 <= bank <= 0xBF):
            self.wram[addr & 0x1FFF] = val
        elif self.is_hw_reg(bank, addr):
            pass  # writes to hardware registers are side-effecting on real hardware; not modeled
        else:
            self.trace.append(f"WARN write to ROM/HW space {bank:02X}:{addr:04X}={val:02X} ignored")
            return
        self.mem_writes.append({"bank": bank, "addr": addr, "value": val})

    def read16(self, bank: int, addr: int) -> int:
        return self.read8(bank, addr) | (self.read8(bank, (addr + 1) & 0xFFFF) << 8)

    def write16(self, bank: int, addr: int, val: int) -> None:
        self.write8(bank, addr, val & 0xFF)
        self.write8(bank, (addr + 1) & 0xFFFF, (val >> 8) & 0xFF)

    def fetch8(self) -> int:
        v = self.read8(self.PB, self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        return v

    def fetch16(self) -> int:
        return self.fetch8() | (self.fetch8() << 8)

    def fetch24(self) -> int:
        lo = self.fetch8(); mid = self.fetch8(); hi = self.fetch8()
        return lo | (mid << 8) | (hi << 16)

    def push8(self, v: int) -> None:
        self.wram[self.S & 0x1FFF] = v & 0xFF
        self.S = (self.S - 1) & 0xFFFF

    def pull8(self) -> int:
        self.S = (self.S + 1) & 0xFFFF
        return self.wram[self.S & 0x1FFF]

    def push16(self, v: int) -> None:
        self.push8((v >> 8) & 0xFF)
        self.push8(v & 0xFF)

    def pull16(self) -> int:
        lo = self.pull8(); hi = self.pull8()
        return lo | (hi << 8)

    def set_nz8(self, v: int) -> int:
        v &= 0xFF
        self.Z = 1 if v == 0 else 0
        self.N = 1 if v & 0x80 else 0
        return v

    def set_nz16(self, v: int) -> int:
        v &= 0xFFFF
        self.Z = 1 if v == 0 else 0
        self.N = 1 if v & 0x8000 else 0
        return v

    def get_p(self) -> int:
        return ((self.N << 7) | (self.V << 6) | (self.M << 5) | (self.XF << 4)
                | (self.Z << 1) | self.C)

    def set_p(self, p: int) -> None:
        self.N = (p >> 7) & 1; self.V = (p >> 6) & 1
        self.M = (p >> 5) & 1; self.XF = (p >> 4) & 1
        self.Z = (p >> 1) & 1; self.C = p & 1

    def addr_abs(self):
        return (self.DB, self.fetch16())

    def addr_abs_long(self):
        full = self.fetch24()
        return (full >> 16, full & 0xFFFF)

    def addr_abs_long_x(self):
        full = self.fetch24()
        addr = (full + self.X) & 0xFFFFFF
        return (addr >> 16, addr & 0xFFFF)

    def addr_abs_x(self):
        base = self.fetch16()
        return (self.DB, (base + self.X) & 0xFFFF)

    def addr_dp(self):
        off = self.fetch8()
        return (0x7E, (self.D + off) & 0xFFFF)

    def addr_dp_x(self):
        off = self.fetch8()
        idx = self.X & (0xFFFF if self.XF == 0 else 0xFF)
        return (0x7E, (self.D + off + idx) & 0xFFFF)

    def addr_dp_y(self):
        off = self.fetch8()
        idx = self.Y & (0xFFFF if self.XF == 0 else 0xFF)
        return (0x7E, (self.D + off + idx) & 0xFFFF)

    def addr_abs_y(self):
        base = self.fetch16()
        idx = self.Y & (0xFFFF if self.XF == 0 else 0xFF)
        return (self.DB, (base + idx) & 0xFFFF)

    def addr_dp_indirect(self):
        off = self.fetch8()
        ptr_addr = (self.D + off) & 0xFFFF
        target = self.read16(0x7E, ptr_addr)
        return (self.DB, target)

    def addr_dp_indirect_y(self):
        off = self.fetch8()
        ptr_addr = (self.D + off) & 0xFFFF
        target = self.read16(0x7E, ptr_addr)
        idx = self.Y & (0xFFFF if self.XF == 0 else 0xFF)
        return (self.DB, (target + idx) & 0xFFFF)

    def addr_dp_indirect_long(self):
        off = self.fetch8()
        ptr_addr = (self.D + off) & 0xFFFF
        lo = self.read8(0x7E, ptr_addr)
        mid = self.read8(0x7E, (ptr_addr + 1) & 0xFFFF)
        hi = self.read8(0x7E, (ptr_addr + 2) & 0xFFFF)
        return (hi, (mid << 8) | lo)

    def addr_dp_indirect_long_y(self):
        b, a = self.addr_dp_indirect_long()
        idx = self.Y & (0xFFFF if self.XF == 0 else 0xFF)
        full = (((b << 16) | a) + idx) & 0xFFFFFF
        return (full >> 16, full & 0xFFFF)

    def step(self) -> bool:
        if self.halted:
            return False
        spb, spc = self.PB, self.PC
        op = self.fetch8()
        Aw = self.M == 0
        Xw = self.XF == 0

        def rd(b, a, wide):
            return self.read16(b, a) if wide else self.read8(b, a)

        def wr(b, a, v, wide):
            self.write16(b, a, v) if wide else self.write8(b, a, v)

        try:
            if op == 0x08: self.push8(self.get_p())
            elif op == 0x28: self.set_p(self.pull8())
            elif op == 0xE2:
                m = self.fetch8()
                if m & 0x20: self.M = 1
                if m & 0x10: self.XF = 1
            elif op == 0xC2:
                m = self.fetch8()
                if m & 0x20: self.M = 0
                if m & 0x10: self.XF = 0
            elif op == 0xA9:
                v = self.fetch16() if Aw else self.fetch8()
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xAD:
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xAF:
                b, a = self.addr_abs_long(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xA5:
                b, a = self.addr_dp(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xBF:
                b, a = self.addr_abs_long_x(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xBD:
                b, a = self.addr_abs_x(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xB9:  # LDA abs,Y
                b, a = self.addr_abs_y(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xB5:  # LDA dp,X
                b, a = self.addr_dp_x(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xB2:  # LDA (dp)
                b, a = self.addr_dp_indirect(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xB1:  # LDA (dp),Y
                b, a = self.addr_dp_indirect_y(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xA7:  # LDA [dp]
                b, a = self.addr_dp_indirect_long(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xB7:  # LDA [dp],Y
                b, a = self.addr_dp_indirect_long_y(); v = rd(b, a, Aw)
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0x95:  # STA dp,X
                b, a = self.addr_dp_x(); wr(b, a, self.A, Aw)
            elif op == 0x99:  # STA abs,Y
                b, a = self.addr_abs_y(); wr(b, a, self.A, Aw)
            elif op == 0x92:  # STA (dp)
                b, a = self.addr_dp_indirect(); wr(b, a, self.A, Aw)
            elif op == 0x91:  # STA (dp),Y
                b, a = self.addr_dp_indirect_y(); wr(b, a, self.A, Aw)
            elif op == 0x97:  # STA [dp],Y
                b, a = self.addr_dp_indirect_long_y(); wr(b, a, self.A, Aw)
            elif op == 0x14:  # TRB dp
                b, a = self.addr_dp(); v = rd(b, a, Aw)
                self.Z = 1 if (v & self.A) == 0 else 0
                wr(b, a, v & ~self.A, Aw)
            elif op == 0x1C:  # TRB abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                self.Z = 1 if (v & self.A) == 0 else 0
                wr(b, a, v & ~self.A, Aw)
            elif op == 0xF4:  # PEA
                v = self.fetch16()
                self.push16(v)
            elif op == 0xD4:  # PEI (dp)
                off = self.fetch8()
                ptr_addr = (self.D + off) & 0xFFFF
                v = self.read16(0x7E, ptr_addr)
                self.push16(v)
            elif op == 0x62:  # PER
                v = self.fetch16()
                self.push16((self.PC + v) & 0xFFFF)
            elif op == 0x8D:
                b, a = self.addr_abs(); wr(b, a, self.A, Aw)
            elif op == 0x8F:
                b, a = self.addr_abs_long(); wr(b, a, self.A, Aw)
            elif op == 0x85:
                b, a = self.addr_dp(); wr(b, a, self.A, Aw)
            elif op == 0x9D:
                b, a = self.addr_abs_x(); wr(b, a, self.A, Aw)
            elif op == 0x86:
                b, a = self.addr_dp(); wr(b, a, self.X, Xw)
            elif op == 0x84:
                b, a = self.addr_dp(); wr(b, a, self.Y, Xw)
            elif op == 0x8E:
                b, a = self.addr_abs(); wr(b, a, self.X, Xw)
            elif op == 0x8C:
                b, a = self.addr_abs(); wr(b, a, self.Y, Xw)
            elif op == 0xA2:
                v = self.fetch16() if Xw else self.fetch8()
                self.X = self.set_nz16(v) if Xw else self.set_nz8(v)
            elif op == 0xA0:
                v = self.fetch16() if Xw else self.fetch8()
                self.Y = self.set_nz16(v) if Xw else self.set_nz8(v)
            elif op == 0xAE:
                b, a = self.addr_abs(); v = rd(b, a, Xw)
                self.X = self.set_nz16(v) if Xw else self.set_nz8(v)
            elif op == 0xAC:
                b, a = self.addr_abs(); v = rd(b, a, Xw)
                self.Y = self.set_nz16(v) if Xw else self.set_nz8(v)
            elif op == 0x9C:
                b, a = self.addr_abs(); wr(b, a, 0, Aw)
            elif op == 0x64:
                b, a = self.addr_dp(); wr(b, a, 0, Aw)
            elif op == 0x0C:
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                self.Z = 1 if (v & self.A) == 0 else 0
                wr(b, a, v | self.A, Aw)
            elif op == 0xAA: self.X = self.set_nz16(self.A) if Xw else self.set_nz8(self.A & 0xFF)
            elif op == 0xA8: self.Y = self.set_nz16(self.A) if Xw else self.set_nz8(self.A & 0xFF)
            elif op == 0x8A: self.A = self.set_nz16(self.X) if Aw else self.set_nz8(self.X & 0xFF)
            elif op == 0x98: self.A = self.set_nz16(self.Y) if Aw else self.set_nz8(self.Y & 0xFF)
            elif op == 0x9A: self.S = self.X  # TXS
            elif op == 0xBA: self.X = self.set_nz16(self.S) if Xw else self.set_nz8(self.S & 0xFF)  # TSX
            elif op == 0x48:
                self.push16(self.A) if Aw else self.push8(self.A & 0xFF)
            elif op == 0x68:
                v = self.pull16() if Aw else self.pull8()
                self.A = self.set_nz16(v) if Aw else self.set_nz8(v)
            elif op == 0xDA:
                self.push16(self.X) if Xw else self.push8(self.X & 0xFF)
            elif op == 0xFA:
                v = self.pull16() if Xw else self.pull8()
                self.X = self.set_nz16(v) if Xw else self.set_nz8(v)
            elif op == 0x5A:
                self.push16(self.Y) if Xw else self.push8(self.Y & 0xFF)
            elif op == 0x7A:
                v = self.pull16() if Xw else self.pull8()
                self.Y = self.set_nz16(v) if Xw else self.set_nz8(v)
            elif op == 0x8B: self.push8(self.DB)  # PHB
            elif op == 0xAB: self.DB = self.pull8()  # PLB
            elif op == 0x29:
                v = self.fetch16() if Aw else self.fetch8()
                self.A = self.set_nz16(self.A & v) if Aw else self.set_nz8(self.A & v)
            elif op == 0x2F:
                b, a = self.addr_abs_long(); v = rd(b, a, Aw)
                self.A = self.set_nz16(self.A & v) if Aw else self.set_nz8(self.A & v)
            elif op == 0x2D:
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                self.A = self.set_nz16(self.A & v) if Aw else self.set_nz8(self.A & v)
            elif op == 0x09:
                v = self.fetch16() if Aw else self.fetch8()
                self.A = self.set_nz16(self.A | v) if Aw else self.set_nz8(self.A | v)
            elif op == 0x49:
                v = self.fetch16() if Aw else self.fetch8()
                self.A = self.set_nz16(self.A ^ v) if Aw else self.set_nz8(self.A ^ v)
            elif op == 0x4F:  # EOR abs long
                b, a = self.addr_abs_long(); v = rd(b, a, Aw)
                self.A = self.set_nz16(self.A ^ v) if Aw else self.set_nz8(self.A ^ v)
            elif op == 0x4D:  # EOR abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                self.A = self.set_nz16(self.A ^ v) if Aw else self.set_nz8(self.A ^ v)
            elif op == 0x45:  # EOR dp
                b, a = self.addr_dp(); v = rd(b, a, Aw)
                self.A = self.set_nz16(self.A ^ v) if Aw else self.set_nz8(self.A ^ v)
            elif op == 0x0D:  # ORA abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                self.A = self.set_nz16(self.A | v) if Aw else self.set_nz8(self.A | v)
            elif op == 0x0F:  # ORA abs long
                b, a = self.addr_abs_long(); v = rd(b, a, Aw)
                self.A = self.set_nz16(self.A | v) if Aw else self.set_nz8(self.A | v)
            elif op == 0x05:  # ORA dp
                b, a = self.addr_dp(); v = rd(b, a, Aw)
                self.A = self.set_nz16(self.A | v) if Aw else self.set_nz8(self.A | v)
            # -- ADC/SBC (decimal mode not modeled; this ROM doesn't use it) --
            elif op == 0x69:  # ADC #imm
                v = self.fetch16() if Aw else self.fetch8()
                mask = 0xFFFF if Aw else 0xFF
                r = (self.A & mask) + v + self.C
                self.C = 1 if r > mask else 0
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0x6D:  # ADC abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                mask = 0xFFFF if Aw else 0xFF
                r = (self.A & mask) + v + self.C
                self.C = 1 if r > mask else 0
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0x6F:  # ADC abs long
                b, a = self.addr_abs_long(); v = rd(b, a, Aw)
                mask = 0xFFFF if Aw else 0xFF
                r = (self.A & mask) + v + self.C
                self.C = 1 if r > mask else 0
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0xE9:  # SBC #imm
                v = self.fetch16() if Aw else self.fetch8()
                mask = 0xFFFF if Aw else 0xFF
                r = (self.A & mask) - v - (1 - self.C)
                self.C = 1 if r >= 0 else 0
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0xED:  # SBC abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                mask = 0xFFFF if Aw else 0xFF
                r = (self.A & mask) - v - (1 - self.C)
                self.C = 1 if r >= 0 else 0
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0xEF:  # SBC abs long
                b, a = self.addr_abs_long(); v = rd(b, a, Aw)
                mask = 0xFFFF if Aw else 0xFF
                r = (self.A & mask) - v - (1 - self.C)
                self.C = 1 if r >= 0 else 0
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0xC9:
                v = self.fetch16() if Aw else self.fetch8()
                mask = 0xFFFF if Aw else 0xFF
                self.C = 1 if (self.A & mask) >= v else 0
                self.set_nz16(self.A - v) if Aw else self.set_nz8(self.A - v)
            elif op == 0xE0:  # CPX #imm
                v = self.fetch16() if Xw else self.fetch8()
                mask = 0xFFFF if Xw else 0xFF
                self.C = 1 if (self.X & mask) >= v else 0
                self.set_nz16(self.X - v) if Xw else self.set_nz8(self.X - v)
            elif op == 0xC0:  # CPY #imm
                v = self.fetch16() if Xw else self.fetch8()
                mask = 0xFFFF if Xw else 0xFF
                self.C = 1 if (self.Y & mask) >= v else 0
                self.set_nz16(self.Y - v) if Xw else self.set_nz8(self.Y - v)
            elif op == 0x89:
                v = self.fetch16() if Aw else self.fetch8()
                self.Z = 1 if (self.A & v) == 0 else 0
            elif op == 0x1A: self.A = self.set_nz16(self.A + 1) if Aw else self.set_nz8(self.A + 1)
            elif op == 0x3A: self.A = self.set_nz16(self.A - 1) if Aw else self.set_nz8(self.A - 1)
            elif op == 0xE8: self.X = self.set_nz16(self.X + 1) if Xw else self.set_nz8(self.X + 1)  # INX
            elif op == 0xC8: self.Y = self.set_nz16(self.Y + 1) if Xw else self.set_nz8(self.Y + 1)  # INY
            elif op == 0xCA: self.X = self.set_nz16(self.X - 1) if Xw else self.set_nz8(self.X - 1)  # DEX
            elif op == 0x88: self.Y = self.set_nz16(self.Y - 1) if Xw else self.set_nz8(self.Y - 1)  # DEY
            elif op == 0x0A:
                r = self.A << 1
                self.C = 1 if (r & (0x10000 if Aw else 0x100)) else 0
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0x4A:
                self.C = self.A & 1
                self.A = self.set_nz16(self.A >> 1) if Aw else self.set_nz8(self.A >> 1)
            elif op == 0x2A:  # ROL A
                carry_in = self.C
                r = (self.A << 1) | carry_in
                self.C = 1 if (r & (0x10000 if Aw else 0x100)) else 0
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0x6A:  # ROR A
                carry_in = self.C
                mask = 0xFFFF if Aw else 0xFF
                new_c = self.A & 1
                r = (self.A >> 1) | (carry_in << (15 if Aw else 7))
                self.C = new_c
                self.A = self.set_nz16(r) if Aw else self.set_nz8(r)
            elif op == 0x0E:  # ASL abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                r = v << 1
                self.C = 1 if (r & (0x10000 if Aw else 0x100)) else 0
                r = self.set_nz16(r) if Aw else self.set_nz8(r)
                wr(b, a, r, Aw)
            elif op == 0x4E:  # LSR abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                self.C = v & 1
                r = self.set_nz16(v >> 1) if Aw else self.set_nz8(v >> 1)
                wr(b, a, r, Aw)
            elif op == 0x2E:  # ROL abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                r = (v << 1) | self.C
                self.C = 1 if (r & (0x10000 if Aw else 0x100)) else 0
                r = self.set_nz16(r) if Aw else self.set_nz8(r)
                wr(b, a, r, Aw)
            elif op == 0x6E:  # ROR abs
                b, a = self.addr_abs(); v = rd(b, a, Aw)
                carry_in = self.C
                new_c = v & 1
                r = (v >> 1) | (carry_in << (15 if Aw else 7))
                self.C = new_c
                r = self.set_nz16(r) if Aw else self.set_nz8(r)
                wr(b, a, r, Aw)
            elif op == 0xEB:  # XBA
                lo = self.A & 0xFF; hi = (self.A >> 8) & 0xFF
                self.A = (lo << 8) | hi
                self.Z = 1 if (self.A & 0xFF) == 0 else 0
                self.N = 1 if (self.A & 0x80) else 0
            elif op == 0x38: self.C = 1
            elif op == 0x18: self.C = 0
            elif op == 0xF0:
                off = self.fetch8()
                if off & 0x80: off -= 0x100
                if self.Z: self.PC = (self.PC + off) & 0xFFFF
            elif op == 0xD0:
                off = self.fetch8()
                if off & 0x80: off -= 0x100
                if not self.Z: self.PC = (self.PC + off) & 0xFFFF
            elif op == 0x10:
                off = self.fetch8()
                if off & 0x80: off -= 0x100
                if not self.N: self.PC = (self.PC + off) & 0xFFFF
            elif op == 0x30:
                off = self.fetch8()
                if off & 0x80: off -= 0x100
                if self.N: self.PC = (self.PC + off) & 0xFFFF
            elif op == 0x90:
                off = self.fetch8()
                if off & 0x80: off -= 0x100
                if not self.C: self.PC = (self.PC + off) & 0xFFFF
            elif op == 0xB0:
                off = self.fetch8()
                if off & 0x80: off -= 0x100
                if self.C: self.PC = (self.PC + off) & 0xFFFF
            elif op == 0x80:
                off = self.fetch8()
                if off & 0x80: off -= 0x100
                self.PC = (self.PC + off) & 0xFFFF
            elif op == 0x4C: self.PC = self.fetch16()
            elif op == 0x5C:
                full = self.fetch24()
                self.PB = full >> 16; self.PC = full & 0xFFFF
            elif op == 0x20:
                target = self.fetch16()
                self.push16((self.PC - 1) & 0xFFFF)
                self.PC = target
            elif op == 0x22:
                full = self.fetch24()
                self.push8(self.PB)
                self.push16((self.PC - 1) & 0xFFFF)
                self.PB = full >> 16; self.PC = full & 0xFFFF
            elif op == 0x60: self.PC = (self.pull16() + 1) & 0xFFFF
            elif op == 0x6B:
                self.PC = (self.pull16() + 1) & 0xFFFF
                self.PB = self.pull8()
            elif op == 0xEA:
                pass
            else:
                self.halted = True
                self.halt_reason = f"unimplemented opcode 0x{op:02X} at {spb:02X}:{spc:04X}"
                return False
        except Exception as exc:  # defensive: never crash the host process on bad candidate code
            self.halted = True
            self.halt_reason = f"exception at {spb:02X}:{spc:04X}: {exc}"
            return False

        self.steps_run += 1
        self.trace.append(
            f"{spb:02X}:{spc:04X} op={op:02X} -> A={self.A:04X} X={self.X:04X} "
            f"Y={self.Y:04X} PB:PC={self.PB:02X}:{self.PC:04X} S={self.S:04X} "
            f"Z={self.Z} N={self.N} C={self.C}"
        )
        return True

    def run(self, max_steps: int, stop_at: tuple[int, int] | None = None,
            stop_on_jsr_to: set[int] | None = None) -> dict:
        hit_jsr = None
        while self.steps_run < max_steps:
            if stop_at is not None and (self.PB, self.PC) == stop_at:
                return {"stopped": "stop_at", "pc": f"{self.PB:02X}:{self.PC:04X}"}
            if stop_on_jsr_to is not None:
                op = self.read8(self.PB, self.PC)
                if op in (0x20, 0x22):
                    tsize = 2 if op == 0x20 else 3
                    raw = 0
                    for i in range(tsize):
                        raw |= self.read8(self.PB, (self.PC + 1 + i) & 0xFFFF) << (8 * i)
                    target = raw if op == 0x22 else raw
                    if target in stop_on_jsr_to or (op == 0x22 and (target & 0xFFFF) in stop_on_jsr_to):
                        return {"stopped": "jsr_target", "target": f"{target:06X}" if op == 0x22 else f"{target:04X}"}
            if not self.step():
                return {"stopped": "halted", "reason": self.halt_reason}
        return {"stopped": "max_steps"}


# ---------------------------------------------------------------------------
# CLI-facing entry point
# ---------------------------------------------------------------------------

def _parse_kv_list(items: list[str] | None) -> dict[str, int]:
    out = {}
    for item in items or []:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        out[k.strip()] = parse_int(v.strip())
    return out


def sim_run(rom_path: str, entry: str, *, set_mem: list[str] | None = None,
            set_reg: list[str] | None = None, stop_at: str | None = None,
            stop_on_jsr: list[str] | None = None, max_steps: int = 2000,
            push_return: str | None = None, out: str | None = None) -> dict:
    """
    Execute a candidate routine against simulated state.

    entry:        "BB:AAAA" bank:PC to begin execution at
    set_mem:      repeatable "BB:AAAA=VALUE" (8-bit) or "BB:AAAA=VALUE:16" (16-bit) memory presets
    set_reg:      repeatable "REG=VALUE", REG in A,X,Y,S,D,DB,PB,M,XF (M/XF are 0 or 1 width flags)
    stop_at:      "BB:AAAA" -- halt cleanly when PB:PC reaches this address
    stop_on_jsr:  repeatable target addresses (4 hex = abs $xxxx, 6 hex = long $BBxxxx);
                  halts BEFORE executing a JSR/JSL to any of these, without simulating the callee
    push_return:  "BB:AAAA" -- pushes a fake JSL-style return frame (PBR + PC-1) onto the
                  stack BEFORE execution starts, so a routine ending in RTL has somewhere
                  valid to return to. Append ":RTS" instead to push an RTS-style frame
                  (PC-1 only, no bank byte) for routines entered via JSR rather than JSL.
    max_steps:    safety limit on executed instructions
    """
    rom = open(rom_path, "rb").read()
    cpu = Sim65816(rom)

    eb, ea = entry.split(":")
    cpu.PB = int(eb, 16)
    cpu.PC = int(ea, 16)

    regs = _parse_kv_list(set_reg)
    for k, v in regs.items():
        ku = k.upper()
        if ku == "A": cpu.A = v
        elif ku == "X": cpu.X = v
        elif ku == "Y": cpu.Y = v
        elif ku == "S": cpu.S = v
        elif ku == "D": cpu.D = v
        elif ku == "DB": cpu.DB = v
        elif ku == "PB": cpu.PB = v
        elif ku == "M": cpu.M = v
        elif ku == "XF": cpu.XF = v
        elif ku == "P": cpu.set_p(v)

    if push_return:
        is_rts_style = push_return.upper().endswith(":RTS")
        base = push_return[:-4] if is_rts_style else push_return
        rb, ra = base.split(":")
        ret_pc = (int(ra, 16) - 1) & 0xFFFF
        if not is_rts_style:
            cpu.push8(int(rb, 16))
        cpu.push16(ret_pc)

    mem_before = {}
    for item in set_mem or []:
        addr_part, val_part = item.split("=", 1)
        bank_s, addr_s = addr_part.split(":")
        bank = int(bank_s, 16); addr = int(addr_s, 16)
        wide = val_part.endswith(":16")
        val = parse_int(val_part[:-3] if wide else val_part)
        if wide:
            cpu.write16(bank, addr, val)
        else:
            cpu.write8(bank, addr, val)
        mem_before[f"{bank:02X}:{addr:04X}"] = f"{val:0{4 if wide else 2}X}"

    cpu.mem_writes.clear()  # don't count our own presets as "changes"

    stop_pc = None
    if stop_at:
        sb, sa = stop_at.split(":")
        stop_pc = (int(sb, 16), int(sa, 16))

    jsr_targets = set()
    for t in stop_on_jsr or []:
        jsr_targets.add(int(t, 16))

    result = cpu.run(max_steps=max_steps, stop_at=stop_pc, stop_on_jsr_to=jsr_targets or None)

    changed = {}
    for w in cpu.mem_writes:
        key = f"{w['bank']:02X}:{w['addr']:04X}"
        changed[key] = f"{w['value']:02X}"  # last value wins; hex string to avoid decimal/hex misread

    report = {
        "tool": "ROMancer",
        "version": VERSION,
        "entry": entry,
        "result": result,
        "final_state": {
            "PC": f"{cpu.PB:02X}:{cpu.PC:04X}",
            "A": f"{cpu.A:04X}", "X": f"{cpu.X:04X}", "Y": f"{cpu.Y:04X}",
            "S": f"{cpu.S:04X}", "D": f"{cpu.D:04X}", "DB": f"{cpu.DB:02X}",
            "M": cpu.M, "XF": cpu.XF, "Z": cpu.Z, "N": cpu.N, "C": cpu.C,
        },
        "steps_run": cpu.steps_run,
        "memory_changed": changed,
        "memory_preset": mem_before,
        "trace_tail": cpu.trace[-20:],
        "note": (
            "This is an instruction-level logic simulation, not a full emulator. "
            "No PPU/APU/DMA/NMI modeled. JSR/JSL targets not in stop_on_jsr are "
            "executed as real code if implemented, or halt the sim if not."
        ),
    }
    if out:
        write_json(out, report)
    return report
