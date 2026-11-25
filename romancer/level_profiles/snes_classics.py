"""Super Nintendo classics: Super Mario World (USA) and Super Metroid (Japan, USA).

Both cartridges are LoROM without a copier header: CPU address $BB:8000-$BB:FFFF is ROM offset BB * $8000 + (address
& $7FFF). The snapshots give the system RAM as 'wram' (128 KB): index 0 is $7E:0000 and index $10000 is $7F:0000.

Layouts (packed_layout / set_packed_layout): Super Mario World's levels are built from objects by the game's code, so
the profile runs that code (_Cpu, a small 65816 interpreter) to know the blocks and to check each change; Super Metroid's
rooms are compressed, so the profile decompresses, changes and compresses them in the game's own format. Research
notes: research/snes_classics-level-profile.md.
"""
from __future__ import annotations

import hashlib

from . import Profile, Watcher

_SINGLE_BLOCKS: dict = {}        # Super Mario World: objects found to put one block, per cartridge, level mode and tileset


def lorom(address: int) -> int:
    """ROM offset of a LoROM CPU address."""
    return ((address >> 16) & 0x7F) * 0x8000 + (address & 0x7FFF)


# --------------------------------------------------------------------------------------------- the 65816 CPU

# A small 65816 interpreter (native mode, LoROM) that runs the game's own code from the ROM on a copy of its RAM, to know
# what the game builds. Hardware registers read as 0 except the multiply / divide unit and the WRAM port; DMA is done
# only to and from the WRAM port (video memory is not kept).

class _CpuStop(Exception):
    pass


_SPEC = """
00 BRK imm8,01 ORA dpxi,02 COP imm8,03 ORA sr,04 TSB dp,05 ORA dp,06 ASL dp,07 ORA dpil,08 PHP imp,09 ORA immm,0A ASL acc,0B PHD imp,0C TSB abs,0D ORA abs,0E ASL abs,0F ORA long
10 BPL rel,11 ORA dpiy,12 ORA dpi,13 ORA sriy,14 TRB dp,15 ORA dpx,16 ASL dpx,17 ORA dpily,18 CLC imp,19 ORA absy,1A INC acc,1B TCS imp,1C TRB abs,1D ORA absx,1E ASL absx,1F ORA longx
20 JSR abs,21 AND dpxi,22 JSL long,23 AND sr,24 BIT dp,25 AND dp,26 ROL dp,27 AND dpil,28 PLP imp,29 AND immm,2A ROL acc,2B PLD imp,2C BIT abs,2D AND abs,2E ROL abs,2F AND long
30 BMI rel,31 AND dpiy,32 AND dpi,33 AND sriy,34 BIT dpx,35 AND dpx,36 ROL dpx,37 AND dpily,38 SEC imp,39 AND absy,3A DEC acc,3B TSC imp,3C BIT absx,3D AND absx,3E ROL absx,3F AND longx
40 RTI imp,41 EOR dpxi,42 WDM imm8,43 EOR sr,44 MVP mv,45 EOR dp,46 LSR dp,47 EOR dpil,48 PHA imp,49 EOR immm,4A LSR acc,4B PHK imp,4C JMP abs,4D EOR abs,4E LSR abs,4F EOR long
50 BVC rel,51 EOR dpiy,52 EOR dpi,53 EOR sriy,54 MVN mv,55 EOR dpx,56 LSR dpx,57 EOR dpily,58 CLI imp,59 EOR absy,5A PHY imp,5B TCD imp,5C JML long,5D EOR absx,5E LSR absx,5F EOR longx
60 RTS imp,61 ADC dpxi,62 PER rell,63 ADC sr,64 STZ dp,65 ADC dp,66 ROR dp,67 ADC dpil,68 PLA imp,69 ADC immm,6A ROR acc,6B RTL imp,6C JMP absi,6D ADC abs,6E ROR abs,6F ADC long
70 BVS rel,71 ADC dpiy,72 ADC dpi,73 ADC sriy,74 STZ dpx,75 ADC dpx,76 ROR dpx,77 ADC dpily,78 SEI imp,79 ADC absy,7A PLY imp,7B TDC imp,7C JMP absxi,7D ADC absx,7E ROR absx,7F ADC longx
80 BRA rel,81 STA dpxi,82 BRL rell,83 STA sr,84 STY dp,85 STA dp,86 STX dp,87 STA dpil,88 DEY imp,89 BIT immm,8A TXA imp,8B PHB imp,8C STY abs,8D STA abs,8E STX abs,8F STA long
90 BCC rel,91 STA dpiy,92 STA dpi,93 STA sriy,94 STY dpx,95 STA dpx,96 STX dpy,97 STA dpily,98 TYA imp,99 STA absy,9A TXS imp,9B TXY imp,9C STZ abs,9D STA absx,9E STZ absx,9F STA longx
A0 LDY immx,A1 LDA dpxi,A2 LDX immx,A3 LDA sr,A4 LDY dp,A5 LDA dp,A6 LDX dp,A7 LDA dpil,A8 TAY imp,A9 LDA immm,AA TAX imp,AB PLB imp,AC LDY abs,AD LDA abs,AE LDX abs,AF LDA long
B0 BCS rel,B1 LDA dpiy,B2 LDA dpi,B3 LDA sriy,B4 LDY dpx,B5 LDA dpx,B6 LDX dpy,B7 LDA dpily,B8 CLV imp,B9 LDA absy,BA TSX imp,BB TYX imp,BC LDY absx,BD LDA absx,BE LDX absy,BF LDA longx
C0 CPY immx,C1 CMP dpxi,C2 REP imm8,C3 CMP sr,C4 CPY dp,C5 CMP dp,C6 DEC dp,C7 CMP dpil,C8 INY imp,C9 CMP immm,CA DEX imp,CB WAI imp,CC CPY abs,CD CMP abs,CE DEC abs,CF CMP long
D0 BNE rel,D1 CMP dpiy,D2 CMP dpi,D3 CMP sriy,D4 PEI dp,D5 CMP dpx,D6 DEC dpx,D7 CMP dpily,D8 CLD imp,D9 CMP absy,DA PHX imp,DB STP imp,DC JML absil,DD CMP absx,DE DEC absx,DF CMP longx
E0 CPX immx,E1 SBC dpxi,E2 SEP imm8,E3 SBC sr,E4 CPX dp,E5 SBC dp,E6 INC dp,E7 SBC dpil,E8 INX imp,E9 SBC immm,EA NOP imp,EB XBA imp,EC CPX abs,ED SBC abs,EE INC abs,EF SBC long
F0 BEQ rel,F1 SBC dpiy,F2 SBC dpi,F3 SBC sriy,F4 PEA abs,F5 SBC dpx,F6 INC dpx,F7 SBC dpily,F8 SED imp,F9 SBC absy,FA PLX imp,FB XCE imp,FC JSR absxi,FD SBC absx,FE INC absx,FF SBC longx
"""
_OPS = {}
for _line in _SPEC.strip().split('\n'):
    for _item in _line.split(','):
        _op, _name, _mode = _item.split()
        _OPS[int(_op, 16)] = (_name, _mode)

_N, _V, _M, _XF, _D, _I, _Z, _C = 0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01


class _Cpu:
    def __init__(self, rom: bytes, ram: bytearray):
        self.rom = rom
        self.ram = ram
        self.a = self.x = self.y = 0
        self.s = 0x1FF
        self.d = 0
        self.db = 0
        self.pb = 0
        self.pc = 0
        self.p = _M | _XF | _I
        self.io = {}
        self.wport = 0
        self.writes = None          # set to a dict to record WRAM writes {index: value}
        self.patch = None           # {ROM offset: byte}: ROM bytes read as if they had been changed

    # ---- bus
    def read(self, a):
        bank, addr = a >> 16 & 0xFF, a & 0xFFFF
        if bank in (0x7E, 0x7F):
            return self.ram[(bank - 0x7E) << 16 | addr]
        low = bank & 0x7F
        if low < 0x40:
            if addr < 0x2000:
                return self.ram[addr]
            if addr < 0x8000:
                return self.ioread(addr)
        if addr >= 0x8000:
            o = (low * 0x8000 + (addr & 0x7FFF)) % len(self.rom)
            if self.patch is not None and o in self.patch:
                return self.patch[o]
            return self.rom[o]
        return 0

    def write(self, a, v):
        bank, addr = a >> 16 & 0xFF, a & 0xFFFF
        if bank in (0x7E, 0x7F):
            i = (bank - 0x7E) << 16 | addr
        elif (bank & 0x7F) < 0x40 and addr < 0x2000:
            i = addr
        else:
            if (bank & 0x7F) < 0x40 and 0x2000 <= addr < 0x8000:
                self.iowrite(addr, v)
            return
        self.ram[i] = v
        if self.writes is not None:
            self.writes[i] = v

    def ioread(self, addr):
        if addr == 0x2180:
            v = self.ram[self.wport]
            self.wport = (self.wport + 1) & 0x1FFFF
            return v
        return self.io.get(addr, 0)

    def iowrite(self, addr, v):
        io = self.io
        io[addr] = v
        if addr == 0x2180:
            self.ram[self.wport] = v
            if self.writes is not None:
                self.writes[self.wport] = v
            self.wport = (self.wport + 1) & 0x1FFFF
        elif 0x2181 <= addr <= 0x2183:
            shift = (addr - 0x2181) * 8
            self.wport = (self.wport & ~(0xFF << shift) | v << shift) & 0x1FFFF
        elif addr == 0x4203:
            product = io.get(0x4202, 0) * v
            io[0x4216], io[0x4217] = product & 0xFF, product >> 8
        elif addr == 0x4206:
            dividend = io.get(0x4204, 0) | io.get(0x4205, 0) << 8
            q, r = (dividend // v, dividend % v) if v else (0xFFFF, dividend)
            io[0x4214], io[0x4215], io[0x4216], io[0x4217] = q & 0xFF, q >> 8, r & 0xFF, r >> 8
        elif addr == 0x420B:
            for ch in range(8):
                if v >> ch & 1:
                    self.dma(ch)

    def dma(self, ch):
        io = self.io
        base = 0x4300 + ch * 16
        mode, baddr = io.get(base, 0), io.get(base + 1, 0)
        a = io.get(base + 2, 0) | io.get(base + 3, 0) << 8 | io.get(base + 4, 0) << 16
        size = io.get(base + 5, 0) | io.get(base + 6, 0) << 8 or 0x10000
        if baddr != 0x80:
            return                  # only the WRAM port matters here (video memory is not kept)
        step = 0 if mode & 0x08 else (-1 if mode & 0x10 else 1)
        for _ in range(size):
            if mode & 0x80:
                self.write(a, self.ioread(0x2180))
            else:
                self.iowrite(0x2180, self.read(a))
            a = (a & 0xFF0000) | ((a + step) & 0xFFFF)
        io[base + 5] = io[base + 6] = 0

    def r16(self, a):
        return self.read(a) | self.read(a + 1) << 8

    def r24(self, a):
        return self.read(a) | self.read(a + 1) << 8 | self.read(a + 2) << 16

    # ---- helpers
    def fetch(self):
        v = self.read(self.pb << 16 | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        return self.fetch() | self.fetch() << 8

    def push(self, v):
        self.write(self.s, v)
        self.s = (self.s - 1) & 0xFFFF

    def pull(self):
        self.s = (self.s + 1) & 0xFFFF
        return self.read(self.s)

    def push16(self, v):
        self.push(v >> 8 & 0xFF)
        self.push(v & 0xFF)

    def pull16(self):
        return self.pull() | self.pull() << 8

    def nz(self, v, wide):
        self.p &= ~(_N | _Z)
        if wide:
            v &= 0xFFFF
            self.p |= (_N if v & 0x8000 else 0) | (0 if v else _Z)
        else:
            v &= 0xFF
            self.p |= (_N if v & 0x80 else 0) | (0 if v else _Z)

    def setp(self, v):
        self.p = v
        if v & _XF:
            self.x &= 0xFF
            self.y &= 0xFF

    def address(self, mode):
        """Effective 24-bit address of an operand."""
        if mode == 'dp':
            return (self.d + self.fetch()) & 0xFFFF
        if mode == 'dpx':
            return (self.d + self.fetch() + self.x) & 0xFFFF
        if mode == 'dpy':
            return (self.d + self.fetch() + self.y) & 0xFFFF
        if mode == 'dpi':
            p = (self.d + self.fetch()) & 0xFFFF
            return self.db << 16 | self.r16(p)
        if mode == 'dpxi':
            p = (self.d + self.fetch() + self.x) & 0xFFFF
            return self.db << 16 | self.r16(p)
        if mode == 'dpiy':
            p = (self.d + self.fetch()) & 0xFFFF
            return ((self.db << 16 | self.r16(p)) + self.y) & 0xFFFFFF
        if mode == 'dpil':
            return self.r24((self.d + self.fetch()) & 0xFFFF)
        if mode == 'dpily':
            return (self.r24((self.d + self.fetch()) & 0xFFFF) + self.y) & 0xFFFFFF
        if mode == 'abs':
            return self.db << 16 | self.fetch16()
        if mode == 'absx':
            return ((self.db << 16 | self.fetch16()) + self.x) & 0xFFFFFF
        if mode == 'absy':
            return ((self.db << 16 | self.fetch16()) + self.y) & 0xFFFFFF
        if mode == 'long':
            return self.fetch16() | self.fetch() << 16
        if mode == 'longx':
            return ((self.fetch16() | self.fetch() << 16) + self.x) & 0xFFFFFF
        if mode == 'sr':
            return (self.s + self.fetch()) & 0xFFFF
        if mode == 'sriy':
            p = (self.s + self.fetch()) & 0xFFFF
            return ((self.db << 16 | self.r16(p)) + self.y) & 0xFFFFFF
        raise _CpuStop(f'mode {mode}')

    def operand(self, mode, wide):
        if mode in ('immm', 'immx'):
            return self.fetch16() if wide else self.fetch()
        a = self.address(mode)
        return self.r16(a) if wide else self.read(a)

    def store(self, a, v, wide):
        self.write(a, v & 0xFF)
        if wide:
            self.write(a + 1, v >> 8 & 0xFF)

    # ---- running
    def run(self, pc, stop=None, limit=5_000_000):
        """Run from pb:pc (24-bit) as a JSL; returns when the routine returns or reaches a stop address."""
        self.pb, self.pc = pc >> 16, pc & 0xFFFF
        floor = self.s
        self.push(0xFF)
        self.push16(0xFFFF)          # a return address no code uses
        self.floor = floor
        self.go(stop, limit)

    def go(self, stop=None, limit=5_000_000):
        """Carry on from where the last run stopped."""
        stops = set(stop or ())
        floor = self.floor
        for _ in range(limit):
            if (self.pb << 16 | self.pc) in stops or self.s > floor or (self.pb == 0xFF and self.pc == 0):
                return
            self.step()
        raise _CpuStop('too many steps')

    def state(self):
        return {k: v for k, v in self.__dict__.items() if k not in ('rom', 'ram', 'io', 'writes')} | {'io': dict(self.io)}

    def restore(self, state):
        self.__dict__.update({k: (dict(v) if k == 'io' else v) for k, v in state.items()})

    def step(self):
        op = self.fetch()
        name, mode = _OPS[op]
        p = self.p
        m16, x16 = not p & _M, not p & _XF
        if name in ('LDA', 'ORA', 'AND', 'EOR', 'ADC', 'SBC', 'CMP', 'BIT') and mode not in ('acc', 'imp'):
            v = self.operand(mode, m16)
            mask = 0xFFFF if m16 else 0xFF
            if name == 'LDA':
                self.a = (self.a & 0xFF00 | v) if not m16 else v
                self.nz(v, m16)
            elif name in ('ORA', 'AND', 'EOR'):
                cur = self.a & mask
                r = cur | v if name == 'ORA' else cur & v if name == 'AND' else cur ^ v
                self.a = (self.a & ~mask | r) & 0xFFFF
                self.nz(r, m16)
            elif name == 'CMP':
                self.compare(self.a & mask, v, m16)
            elif name == 'BIT':
                r = self.a & mask & v
                self.p = self.p & ~_Z | (0 if r else _Z)
                if mode != 'immm':
                    top = 0x8000 if m16 else 0x80
                    self.p = self.p & ~(_N | _V) | (_N if v & top else 0) | (_V if v & (top >> 1) else 0)
            elif name == 'ADC':
                self.adc(v, m16)
            else:
                self.sbc(v, m16)
            return
        if name in ('LDX', 'LDY'):
            v = self.operand(mode, x16)
            if name == 'LDX':
                self.x = v
            else:
                self.y = v
            self.nz(v, x16)
            return
        if name in ('CPX', 'CPY'):
            v = self.operand(mode, x16)
            self.compare(self.x if name == 'CPX' else self.y, v, x16)
            return
        if name in ('STA', 'STX', 'STY', 'STZ'):
            a = self.address(mode)
            if name == 'STA':
                self.store(a, self.a, m16)
            elif name == 'STZ':
                self.store(a, 0, m16)
            else:
                self.store(a, self.x if name == 'STX' else self.y, x16)
            return
        if name in ('ASL', 'LSR', 'ROL', 'ROR', 'INC', 'DEC', 'TSB', 'TRB'):
            if mode == 'acc':
                mask = 0xFFFF if m16 else 0xFF
                r = self.shift(name, self.a & mask, m16)
                self.a = (self.a & ~mask | r) & 0xFFFF
            else:
                a = self.address(mode)
                v = self.r16(a) if m16 else self.read(a)
                if name in ('TSB', 'TRB'):
                    acc = self.a & (0xFFFF if m16 else 0xFF)
                    self.p = self.p & ~_Z | (0 if v & acc else _Z)
                    r = v | acc if name == 'TSB' else v & ~acc & 0xFFFF
                else:
                    r = self.shift(name, v, m16)
                self.store(a, r, m16)
            return
        getattr(self, 'op_' + name)(mode, m16, x16)

    def compare(self, reg, v, wide):
        r = reg - v
        self.p = self.p & ~_C | (_C if r >= 0 else 0)
        self.nz(r, wide)

    def adc(self, v, wide):
        mask, top = (0xFFFF, 0x8000) if wide else (0xFF, 0x80)
        a = self.a & mask
        c = self.p & _C
        if self.p & _D:
            r, carry, shift = 0, c, 0
            for _ in range(4 if wide else 2):
                digit = (a >> shift & 15) + (v >> shift & 15) + carry
                carry = 1 if digit > 9 else 0
                if carry:
                    digit -= 10
                r |= (digit & 15) << shift
                shift += 4
            overflow = 0
        else:
            r = a + v + c
            carry = 1 if r > mask else 0
            r &= mask
            overflow = _V if (~(a ^ v) & (a ^ r) & top) else 0
        self.p = self.p & ~(_C | _V) | carry | overflow
        self.a = (self.a & ~mask | r) & 0xFFFF
        self.nz(r, wide)

    def sbc(self, v, wide):
        mask, top = (0xFFFF, 0x8000) if wide else (0xFF, 0x80)
        if self.p & _D:
            a = self.a & mask
            borrow = 1 - (self.p & _C)
            r, shift = 0, 0
            for _ in range(4 if wide else 2):
                digit = (a >> shift & 15) - (v >> shift & 15) - borrow
                borrow = 1 if digit < 0 else 0
                if borrow:
                    digit += 10
                r |= (digit & 15) << shift
                shift += 4
            self.p = self.p & ~(_C | _V) | (0 if borrow else _C)
            self.a = (self.a & ~mask | r) & 0xFFFF
            self.nz(r, wide)
        else:
            self.adc(v ^ mask, wide)

    def shift(self, name, v, wide):
        mask, top = (0xFFFF, 0x8000) if wide else (0xFF, 0x80)
        c = self.p & _C
        if name == 'ASL':
            r, nc = (v << 1) & mask, 1 if v & top else 0
        elif name == 'LSR':
            r, nc = v >> 1, v & 1
        elif name == 'ROL':
            r, nc = ((v << 1) | c) & mask, 1 if v & top else 0
        elif name == 'ROR':
            r, nc = (v >> 1) | (top if c else 0), v & 1
        elif name == 'INC':
            r = (v + 1) & mask
            self.nz(r, wide)
            return r
        else:
            r = (v - 1) & mask
            self.nz(r, wide)
            return r
        self.p = self.p & ~_C | nc
        self.nz(r, wide)
        return r

    # ---- the other instructions
    def branch(self, take):
        off = self.fetch()
        if take:
            self.pc = (self.pc + (off - 256 if off > 127 else off)) & 0xFFFF

    def op_BPL(self, *a): self.branch(not self.p & _N)
    def op_BMI(self, *a): self.branch(self.p & _N)
    def op_BVC(self, *a): self.branch(not self.p & _V)
    def op_BVS(self, *a): self.branch(self.p & _V)
    def op_BCC(self, *a): self.branch(not self.p & _C)
    def op_BCS(self, *a): self.branch(self.p & _C)
    def op_BNE(self, *a): self.branch(not self.p & _Z)
    def op_BEQ(self, *a): self.branch(self.p & _Z)
    def op_BRA(self, *a): self.branch(True)

    def op_BRL(self, *a):
        off = self.fetch16()
        self.pc = (self.pc + (off - 0x10000 if off > 0x7FFF else off)) & 0xFFFF

    def op_JMP(self, mode, *a):
        if mode == 'abs':
            self.pc = self.fetch16()
        elif mode == 'absi':
            self.pc = self.r16(self.fetch16())
        else:  # absxi
            self.pc = self.r16(self.pb << 16 | ((self.fetch16() + self.x) & 0xFFFF))

    def op_JML(self, mode, *a):
        if mode == 'long':
            t = self.fetch16() | self.fetch() << 16
        else:
            t = self.r24(self.fetch16())
        self.pb, self.pc = t >> 16, t & 0xFFFF

    def op_JSR(self, mode, *a):
        t = self.fetch16()
        if mode == 'absxi':
            t = self.r16(self.pb << 16 | ((t + self.x) & 0xFFFF))
        self.push16((self.pc - 1) & 0xFFFF)
        self.pc = t

    def op_JSL(self, *a):
        t = self.fetch16()
        bank = self.fetch()
        self.push(self.pb)
        self.push16((self.pc - 1) & 0xFFFF)
        self.pb, self.pc = bank, t

    def op_RTS(self, *a):
        self.pc = (self.pull16() + 1) & 0xFFFF

    def op_RTL(self, *a):
        self.pc = (self.pull16() + 1) & 0xFFFF
        self.pb = self.pull()

    def op_RTI(self, *a):
        self.setp(self.pull())
        self.pc = self.pull16()
        self.pb = self.pull()

    def op_PHA(self, mode, m16, x16):
        self.push16(self.a) if m16 else self.push(self.a & 0xFF)

    def op_PHX(self, mode, m16, x16):
        self.push16(self.x) if x16 else self.push(self.x & 0xFF)

    def op_PHY(self, mode, m16, x16):
        self.push16(self.y) if x16 else self.push(self.y & 0xFF)

    def op_PLA(self, mode, m16, x16):
        v = self.pull16() if m16 else self.pull()
        self.a = v if m16 else (self.a & 0xFF00 | v)
        self.nz(v, m16)

    def op_PLX(self, mode, m16, x16):
        self.x = self.pull16() if x16 else self.pull()
        self.nz(self.x, x16)

    def op_PLY(self, mode, m16, x16):
        self.y = self.pull16() if x16 else self.pull()
        self.nz(self.y, x16)

    def op_PHP(self, *a): self.push(self.p)
    def op_PLP(self, *a): self.setp(self.pull())
    def op_PHB(self, *a): self.push(self.db)
    def op_PHK(self, *a): self.push(self.pb)
    def op_PHD(self, *a): self.push16(self.d)

    def op_PLB(self, *a):
        self.db = self.pull()
        self.nz(self.db, False)

    def op_PLD(self, *a):
        self.d = self.pull16()
        self.nz(self.d, True)

    def op_PEA(self, *a): self.push16(self.fetch16())
    def op_PEI(self, *a): self.push16(self.r16((self.d + self.fetch()) & 0xFFFF))

    def op_PER(self, *a):
        off = self.fetch16()
        self.push16((self.pc + off) & 0xFFFF)

    def op_REP(self, *a): self.setp(self.p & ~self.fetch())
    def op_SEP(self, *a): self.setp(self.p | self.fetch())

    def _tr(self, value, wide, target):
        if target == 'a':
            if wide:
                self.a = value & 0xFFFF
            else:
                self.a = self.a & 0xFF00 | value & 0xFF
        else:
            setattr(self, target, value & (0xFFFF if wide else 0xFF))
        self.nz(value, wide)

    def op_TAX(self, mode, m16, x16): self._tr(self.a, x16, 'x')
    def op_TAY(self, mode, m16, x16): self._tr(self.a, x16, 'y')
    def op_TXA(self, mode, m16, x16): self._tr(self.x, m16, 'a')
    def op_TYA(self, mode, m16, x16): self._tr(self.y, m16, 'a')
    def op_TXY(self, mode, m16, x16): self._tr(self.x, x16, 'y')
    def op_TYX(self, mode, m16, x16): self._tr(self.y, x16, 'x')
    def op_TSX(self, mode, m16, x16): self._tr(self.s, x16, 'x')
    def op_TXS(self, *a): self.s = self.x
    def op_TCS(self, *a): self.s = self.a

    def op_TSC(self, *a):
        self.a = self.s
        self.nz(self.a, True)

    def op_TCD(self, *a):
        self.d = self.a
        self.nz(self.d, True)

    def op_TDC(self, *a):
        self.a = self.d
        self.nz(self.a, True)

    def op_XBA(self, *a):
        self.a = (self.a >> 8 | self.a << 8) & 0xFFFF
        self.nz(self.a & 0xFF, False)

    def op_XCE(self, *a):
        if self.p & _C:
            raise _CpuStop('emulation mode')

    def op_INX(self, mode, m16, x16):
        self.x = (self.x + 1) & (0xFFFF if x16 else 0xFF)
        self.nz(self.x, x16)

    def op_INY(self, mode, m16, x16):
        self.y = (self.y + 1) & (0xFFFF if x16 else 0xFF)
        self.nz(self.y, x16)

    def op_DEX(self, mode, m16, x16):
        self.x = (self.x - 1) & (0xFFFF if x16 else 0xFF)
        self.nz(self.x, x16)

    def op_DEY(self, mode, m16, x16):
        self.y = (self.y - 1) & (0xFFFF if x16 else 0xFF)
        self.nz(self.y, x16)

    def op_CLC(self, *a): self.p &= ~_C
    def op_SEC(self, *a): self.p |= _C
    def op_CLI(self, *a): self.p &= ~_I
    def op_SEI(self, *a): self.p |= _I
    def op_CLD(self, *a): self.p &= ~_D
    def op_SED(self, *a): self.p |= _D
    def op_CLV(self, *a): self.p &= ~_V
    def op_NOP(self, *a): pass
    def op_WDM(self, *a): self.fetch()

    def _move(self, step, x16):
        dst, src = self.fetch(), self.fetch()
        self.db = dst
        while True:
            self.write(dst << 16 | self.y, self.read(src << 16 | self.x))
            self.x = (self.x + step) & 0xFFFF
            self.y = (self.y + step) & 0xFFFF
            self.a = (self.a - 1) & 0xFFFF
            if self.a == 0xFFFF:
                break
        if not x16:
            self.x &= 0xFF
            self.y &= 0xFF

    def op_MVN(self, mode, m16, x16): self._move(1, x16)
    def op_MVP(self, mode, m16, x16): self._move(-1, x16)

    def op_BRK(self, *a): raise _CpuStop(f'BRK at {self.pb:02X}:{self.pc - 1:04X}')
    def op_COP(self, *a): raise _CpuStop('COP')
    def op_STP(self, *a): raise _CpuStop('STP')
    def op_WAI(self, *a): raise _CpuStop('WAI')


# --------------------------------------------------------------------------------------------- Super Mario World

class SuperMarioWorld:
    """Super Mario World (USA). Level loading: $05D8B7 (bank 5). Sprite loader: $02A7FC (bank 2). Objects: $0585FF.

    A level number (0-$1FF) picks two things from tables in bank 5:
    * $05E000 + level * 3: the layer 1 data (a 5-byte header, then objects of 3 bytes, $FF ends it)
    * $05EC00 + level * 2: the sprite list in bank 7 (a header byte, then 3 bytes per sprite, $FF ends it)
    Sprite entry: byte 0 = row (high nibble), extra bits (bits 2-3), screen bit 4 (bit 1), high bit of the row (bit 0);
    byte 1 = column (high nibble) and screen (low nibble); byte 2 = sprite number. In vertical levels the row and column
    swap. The list is sorted by screen; the loader writes the entry's index to $161A of the sprite slot it fills.
    """
    name = 'Super Mario World'
    sha256 = '0838e531fe22c077528febe14cb3ff7c492f1f5fa8de354192bdff7137c27f5b'
    LAYER1 = 0x05E000
    SPRITES = 0x05EC00
    MODE_FLAGS = 0x058417       # per level mode: bit 0 = vertical level ($5B)
    LEVELS = 0x200
    # screen exits ($0DA512): extended object 0, 4 bytes; byte 3 is where it leads ($19B8 + screen)
    # single blocks ($0DA57B): extended objects $10-$42 put one Map16 tile (table $0DA548) in the level
    SCREEN_MAPS = (0x00BEA8, 0x00BEAC)  # RAM addresses of each screen's blocks, low and high bytes

    # Sprite names: each was spawned in a level that uses it and looked at (trace/v15_profiles/snes_classics/spawn).
    NAMES = {
        0x00: 'Green Koopa without a shell', 0x01: 'Red Koopa without a shell', 0x02: 'Blue Koopa without a shell',
        0x03: 'Yellow Koopa without a shell', 0x04: 'Green Koopa', 0x05: 'Red Koopa', 0x06: 'Blue Koopa',
        0x07: 'Yellow Koopa', 0x08: 'Green Paratroopa', 0x09: 'Green Paratroopa', 0x0A: 'Red Paratroopa',
        0x0B: 'Red Paratroopa', 0x0C: 'Yellow Paratroopa', 0x0E: 'Keyhole', 0x0F: 'Goomba', 0x10: 'Winged Goomba',
        0x11: 'Buzzy Beetle', 0x13: 'Spiny', 0x15: 'Cheep Cheep', 0x16: 'Cheep Cheep', 0x18: 'Cheep Cheep (likely)',
        0x1D: 'Hopping flame', 0x1E: 'Lakitu', 0x2A: 'Upside-down Piranha Plant', 0x2C: 'Yoshi egg',
        0x2E: 'Spike Top', 0x2F: 'Springboard', 0x3A: 'Urchin', 0x3B: 'Urchin', 0x3C: 'Urchin', 0x3D: 'Rip Van Fish',
        0x3E: 'P-switch', 0x3F: 'Goomba with a parachute', 0x40: 'Bob-omb with a parachute', 0x41: 'Dolphin',
        0x42: 'Dolphin', 0x43: 'Dolphin', 0x46: "Diggin' Chuck", 0x47: 'Cheep Cheep (likely)', 0x48: "Diggin' Chuck's rock",
        0x49: 'Pipe that grows and shrinks', 0x4B: 'Lakitu without a cloud', 0x4D: 'Monty Mole', 0x4E: 'Monty Mole',
        0x4F: 'Jumping Piranha Plant', 0x50: 'Jumping Piranha Plant', 0x55: 'Checkered platform',
        0x57: 'Checkered platform', 0x59: 'Turn block bridge', 0x5A: 'Turn block bridge',
        0x5F: 'Brown platform on a chain', 0x61: 'Skull raft', 0x62: 'Brown platform', 0x63: 'Brown platform',
        0x64: 'Rope', 0x68: 'Fuzzy', 0x6E: 'Dino Rhino', 0x6F: 'Dino Torch', 0x70: 'Pokey', 0x72: 'Super Koopa',
        0x73: 'Super Koopa', 0x74: 'Mushroom', 0x75: 'Fire flower', 0x76: 'Star', 0x77: 'Feather',
        0x78: '1-Up mushroom', 0x7B: 'Goal tape', 0x80: 'Key', 0x82: 'Bonus game', 0x83: 'Flying question block',
        0x84: 'Flying question block', 0x86: 'Wiggler', 0x8A: 'Bird', 0x91: 'Chuck', 0x92: 'Chuck', 0x93: 'Chuck',
        0x94: 'Chuck', 0x95: 'Chuck', 0x97: 'Chuck', 0x98: 'Chuck', 0x99: 'Volcano Lotus', 0x9A: 'Sumo Bro',
        0x9C: 'Flying grey blocks', 0x9D: 'Bubble with an enemy inside', 0x9F: 'Banzai Bill', 0xA5: 'Fuzzy (likely)',
        0xAB: 'Rex', 0xB7: 'Carrot lift', 0xB8: 'Carrot lift', 0xB9: 'Message block', 0xBA: 'Timed lift',
        0xBE: 'Swooper', 0xBF: 'Mega Mole', 0xC1: 'Flying grey blocks', 0xC2: 'Blurp', 0xC3: 'Porcu-Puffer',
        0xC4: 'Grey falling platform', 0xDA: 'Green Koopa shell', 0xDB: 'Red Koopa shell', 0xDC: 'Blue Koopa shell',
        0xDD: 'Yellow Koopa shell'}
    ITEMS = {0x2C, 0x2F, 0x3E, 0x74, 0x75, 0x76, 0x77, 0x78, 0x80, 0x83, 0x84, 0xB9, 0xDA, 0xDB, 0xDC, 0xDD}
    # what the sprite loader does with numbers of $C9 and up ($02A86A-$02A8D4)
    SHOOTERS = range(0xC9, 0xCB)        # $02AB78
    GENERATORS = range(0xCB, 0xDA)      # $18B9 = number - $CA: a generator that keeps making sprites
    SHELLS = range(0xDA, 0xDE)          # spawned as a shell: number - $DA + 4, status 9
    SCROLLERS = range(0xE7, 0x100)      # $143E = number - $E7: a layer scroll command
    # Single blocks that give something when hit: extended object -> (Map16 tile the level gets, what comes out). Each was
    # put in level $105 and hit by Mario, small and big (trace/v15_profiles/snes_classics/blocks.py, blocks/results*.txt):
    # the sprite that came out is named above; the tile is what the game wrote to the level's RAM for it.
    BLOCKS = {
        0x11: (0x022, 'Invisible block with a 1-Up mushroom'), 0x17: (0x12D, 'Green star block with a coin'),
        0x23: (0x111, 'Note block with a mushroom or flower'), 0x28: (0x117, 'Turn block with a mushroom or flower'),
        0x29: (0x118, 'Turn block with a mushroom or feather'), 0x2A: (0x119, 'Turn block with a star'),
        0x2B: (0x11A, 'Turn block with a coin'), 0x2C: (0x11B, 'Turn block with several coins'),
        0x2D: (0x11C, 'Turn block with a coin'), 0x2F: (0x11D, 'Turn block with a P-switch'),
        0x30: (0x11F, 'Question block with a mushroom or flower'), 0x31: (0x120, 'Question block with a mushroom or feather'),
        0x32: (0x121, 'Question block with a star'), 0x33: (0x122, 'Question block with a coin'),
        0x34: (0x123, 'Question block with several coins'), 0x36: (0x126, 'Question block with a Yoshi egg'),
        0x37: (0x127, 'Question block with a Koopa shell'), 0x38: (0x128, 'Question block with a Koopa shell')}

    def __init__(self, rom: bytes):
        self.rom = rom
        self._lists = None
        self._cache = {}

    # ---- reading
    def b(self, address: int) -> int:
        return self.rom[lorom(address)]

    def w(self, address: int) -> int:
        return self.b(address) | self.b(address + 1) << 8

    def l(self, address: int) -> int:
        return self.w(address) | self.b(address + 2) << 16

    def header(self, level: int) -> list:
        start = self.l(self.LAYER1 + level * 3)
        return [self.b(start + i) for i in range(5)]

    def vertical(self, level: int) -> bool:
        return bool(self.b(self.MODE_FLAGS + (self.header(level)[1] & 0x1F)) & 1)

    def sprite_gfx(self, level: int) -> int:
        return self.header(level)[2] & 0x0F

    def list_address(self, level: int) -> int:
        return 0x070000 | self.w(self.SPRITES + level * 2)

    def sprite_list(self, level: int) -> list:
        """[{'index', 'offset', 'number', 'x', 'y', 'extra', 'screen'}] in level pixels (top left of the sprite)."""
        address, out = self.list_address(level) + 1, []
        vertical = self.vertical(level)
        while self.b(address) != 0xFF and len(out) < 128:
            b0, b1, number = self.b(address), self.b(address + 1), self.b(address + 2)
            screen = (b0 >> 1 & 1) << 4 | (b1 & 0x0F)
            along, across = screen * 256 + (b1 & 0xF0), (b0 & 1) << 8 | (b0 & 0xF0)
            x, y = (across, along) if vertical else (along, across)
            out.append({'index': len(out), 'offset': lorom(address), 'number': number, 'x': x, 'y': y,
                        'extra': b0 >> 2 & 3, 'screen': screen})
            address += 3
        return out

    def list_users(self, level: int) -> list:
        """Every level that uses the same sprite list."""
        if self._lists is None:
            self._lists = {}
            for other in range(self.LEVELS):
                self._lists.setdefault(self.list_address(other), []).append(other)
        return self._lists.get(self.list_address(level), [level])

    def layer1_objects(self, level: int) -> list:
        """The layer 1 objects with their screen ($1928): [{'offset', 'screen', 'row', 'col', 'number', 'ext', 'size'}]."""
        if ('l1', level) in self._cache:
            return self._cache[('l1', level)]
        address = self.l(self.LAYER1 + level * 3) + 5
        out, screen = [], 0
        for _ in range(4000):
            b0 = self.b(address)
            if b0 == 0xFF:
                break
            b1, b2 = self.b(address + 1), self.b(address + 2)
            if b0 & 0x80:
                screen += 1
            number = (b0 & 0x60) >> 1 | b1 >> 4
            size = 4 if number == 0 and b2 == 0 else 3
            if number == 0 and b2 == 1:             # screen jump
                screen = b0 & 0x1F
            out.append({'offset': lorom(address), 'screen': screen, 'row': b0 & 0x1F, 'col': b1 & 0x0F, 'number': number,
                        'ext': b2 if number == 0 else None, 'size': size,
                        'bytes': bytes(self.b(address + i) for i in range(size))})
            address += size
        self._cache[('l1', level)] = out
        return out

    def exits(self, level: int) -> list:
        """Screen exits: [{'offset' (of the byte that says where it leads), 'screen', 'to', 'secondary'}]."""
        out = []
        for obj in self.layer1_objects(level):
            if obj['ext'] == 0:
                out.append({'offset': obj['offset'] + 3, 'screen': obj['row'], 'to': obj['bytes'][3],
                            'secondary': bool(obj['bytes'][1] & 2)})
        return out

    def block_name(self, ext: int) -> str:
        name = self.BLOCKS[ext][1]
        if sum(1 for v in self.BLOCKS.values() if v[1] == name) > 1:
            return f'{name} ({ext:#04x})'
        return name

    def blocks(self, level: int) -> list:
        """Single blocks that give something when hit (the extended objects in BLOCKS)."""
        if self.vertical(level):
            return []
        out = []
        for obj in self.layer1_objects(level):
            ext = obj['ext']
            if ext in self.BLOCKS:
                out.append({**obj, 'tile': self.BLOCKS[ext][0], 'x': obj['screen'] * 256 + obj['col'] * 16,
                            'y': obj['row'] * 16})
        return out

    def block_ram(self, level: int, screen: int, row: int, col: int) -> tuple:
        """RAM indexes (low byte, high byte) of a block in the decoded level, from the game's own screen tables."""
        mode = self.header(level)[1] & 0x1F
        places = []
        for table in self.SCREEN_MAPS:
            per_mode = self.w(table)
            screens = self.w(per_mode + mode * 2)
            base = self.l(screens + screen * 3)
            places.append(base + (0x100 if row & 0x10 else 0) + (row & 0x0F) * 16 + col - 0x7E0000)
        return tuple(places)

    def main_level(self, translevel: int, submap: int) -> int:
        """The level the overworld enters ($05D8A2): translevels of $25 and up are levels 1 onward."""
        low = translevel - 0x24 if translevel >= 0x25 else translevel
        return low | (0x100 if submap else 0)

    def level_of(self, ram):
        """Which level the game is playing, from the sprite list pointer ($CE) and the header values the loader keeps."""
        if ram[0xD0] != 0x07:
            return None
        pointer = 0x070000 | ram[0xCE] | ram[0xCF] << 8
        found = [lv for lv in range(self.LEVELS) if self.list_address(lv) == pointer]
        if not found:
            return None
        exact = [lv for lv in found if self._header_matches(lv, ram)]
        found = exact or found
        if len(found) > 1:
            main = self.main_level(ram[0x13BF], ram[0x1F11 + (ram[0x0DD6] >> 2)])
            if main in found:
                return main
            exits = [lv for lv in found if all(ram[0x19B8 + e['screen']] == e['to'] for e in self.exits(lv))]
            found = exits or found
        return found[0]

    def _header_matches(self, level, ram) -> bool:
        h = self.header(level)
        return (ram[0x1925] == h[1] & 0x1F and ram[0x192B] == h[2] & 0x0F and ram[0x1931] == h[4] & 0x0F
                and ram[0x1930] == h[0] >> 5)

    def kind(self, number: int) -> str:
        if number in self.SHOOTERS:
            return 'shooter'
        if number in self.GENERATORS:
            return 'generator'
        if number in self.SCROLLERS:
            return 'scroller'
        if number < 0xC9 or number in self.SHELLS:
            return 'sprite'
        return 'special'

    def sprite_name(self, number: int) -> str:
        name = self.NAMES.get(number)
        if not name:
            return f'Sprite {number:#04x}'
        if sum(1 for v in self.NAMES.values() if v == name) > 1:      # several numbers look alike: keep them apart
            return f'{name} ({number:#04x})'
        return name

    def swap_choices(self, gfx: int) -> list:
        """Sprites the game itself places in levels with this sprite graphics set (so they draw right), one per number."""
        if ('swap', gfx) not in self._cache:
            seen = set()
            for level in range(self.LEVELS):
                if self.sprite_gfx(level) != gfx:
                    continue
                for entry in self.sprite_list(level):
                    if self.kind(entry['number']) == 'sprite':
                        seen.add(entry['number'])
            self._cache[('swap', gfx)] = sorted(seen)
        return self._cache[('swap', gfx)]

    def remove_writes(self, level: int, index: int) -> list:
        """Take one entry out of the list: the later entries move up, $FF ends the list one entry sooner."""
        entries = self.sprite_list(level)
        start = entries[index]['offset']
        end = lorom(self.list_address(level)) + 1 + 3 * len(entries)      # the $FF
        old = self.rom[start:end + 1]
        new = self.rom[start + 3:end] + b'\xff' * 4
        return [(start + i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]

    # ---- the layout: layer 1 blocks as the game builds them in RAM
    # The game builds a level at $05801E: it fills the level with the empty block, then runs every layer 1 object
    # ($0583AC, the object list after the 5-byte header) and puts the blocks in RAM ($7EC800 low bytes, $7FC800 high
    # bytes, screen by screen from the $00BEA8 tables). ROMancer runs that same code from the ROM (_Cpu) to know the
    # blocks exactly, and to check every change it makes before it offers it.
    LAYER2 = 0x05E600
    BUILD, BUILD_OBJECTS, BUILD_DONE = 0x05801E, 0x0583AC, 0x05808F
    NO_OBJECTS = (0x09, 0x0B, 0x10)     # boss rooms: the builder skips the objects ($0583BB)
    ROWS = 27                           # rows of a screen in a level that scrolls sideways ($1B0 bytes a screen)
    EMPTY = 0x25                        # the block the builder fills the level with first ($05807F)

    def _cpu(self, level, patch=None):
        ram = bytearray(0x20000)
        for i, table in enumerate((self.LAYER1, self.LAYER2)):
            o = lorom(table + level * 3)
            ram[0x65 + 3 * i:0x68 + 3 * i] = bytes(self.rom[o:o + 3])
        for offset, value in (patch or {}).items():         # a changed pointer must be seen before the build starts
            for i, table in enumerate((self.LAYER1, self.LAYER2)):
                o = lorom(table + level * 3)
                if o <= offset < o + 3:
                    ram[0x65 + 3 * i + offset - o] = value
        cpu = _Cpu(self.rom, ram)
        cpu.patch = patch
        cpu.p = 0x34
        return cpu, ram

    def build(self, level: int, patch=None) -> bytearray:
        """The game's RAM after it has built the level (patch: {ROM offset: byte} read instead of the ROM's)."""
        key = ('build', level)
        if patch is None and key in self._cache:
            return self._cache[key]
        cpu, ram = self._cpu(level, patch)
        cpu.run(self.BUILD, stop=[self.BUILD_DONE])
        if patch is None:
            self._cache[key] = ram
        return ram

    def layout_screens(self, level: int):
        """How many screens the level's layout has, or None when ROMancer cannot change its layout (levels that scroll
        up and down, and boss rooms)."""
        mode = self.header(level)[1] & 0x1F
        if self.vertical(level) or mode in self.NO_OBJECTS:
            return None
        return (self.header(level)[0] & 0x1F) + 1

    def spot(self, level: int, column: int, row: int) -> tuple:
        return self.block_ram(level, column // 16, row, column % 16)

    def decoded(self, level: int, ram=None) -> list:
        ram = self.build(level) if ram is None else ram
        width = self.layout_screens(level) * 16
        out = []
        for row in range(self.ROWS):
            for column in range(width):
                low, high = self.spot(level, column, row)
                out.append(ram[low] | ram[high] << 8)
        return out

    def objects_data(self, level: int) -> bytes:
        """The level's layer 1 data: the 5-byte header and the objects, without the $FF that ends them."""
        start = lorom(self.l(self.LAYER1 + level * 3))
        objects = self.layer1_objects(level)
        end = objects[-1]['offset'] + objects[-1]['size'] if objects else start + 5
        return bytes(self.rom[start:end])

    # objects that may put one block by themselves: extended objects 2-$FF, then standard objects 1-$3F of the smallest
    # size, then with the other sizes whose high or low half is 0 (in a scan of every size of every standard object in
    # level $106 those were the only ones that put a single block)
    def _candidates(self):
        for ext in range(2, 0x100):
            yield (0, ext)
        for number in range(1, 0x40):
            yield (number, 0)
        for size in list(range(1, 0x10)) + list(range(0x10, 0x100, 0x10)):
            for number in range(1, 0x40):
                yield (number, size)

    @staticmethod
    def object_bytes(number: int, size: int, row: int, column: int) -> bytes:
        """A 3-byte layer 1 object on the current screen ($0585FF): number = BB << 4 | bbbb in b0 bits 5-6 and b1."""
        return bytes([(number & 0x30) << 1 | row, (number & 0x0F) << 4 | column, size])

    def single_blocks(self, level: int, wanted=None) -> dict:
        """{block: (number, size)}: objects that put exactly that one block in this level and nothing else, found by
        running each on its own in the level's own builder (stops early once every wanted block is found)."""
        header = self.objects_data(level)[:5]
        if 'digest' not in self._cache:
            self._cache['digest'] = hashlib.sha1(bytes(self.rom)).hexdigest()
        key = ('single', self._cache['digest'], header[1] & 0x1F, header[4] & 0x0F)
        cache = _SINGLE_BLOCKS          # kept for every profile of the same cartridge: a full search takes a while
        found, done = cache.setdefault(key, [{}, None])
        if done is not None or (wanted is not None and set(wanted) <= set(found)):
            return found
        cpu, ram = self._cpu(level)
        cpu.run(self.BUILD, stop=[self.BUILD_OBJECTS])
        start_ram, start = bytes(ram), cpu.state()
        screen, row, column = 1, 10, 5
        place = set(self.spot(level, 16 + column, row))
        tried = cache.setdefault(key + ('tried',), set())
        start_offset = lorom(self.l(self.LAYER1 + level * 3))

        def objects_alone(data):
            run_ram = bytearray(start_ram)
            run = _Cpu(self.rom, run_ram)
            run.restore(start)
            run.patch = {start_offset + i: v for i, v in enumerate(data)}
            run.writes = {}
            run.go([self.BUILD_DONE], 200_000)
            return run_ram, {i: v for i, v in run.writes.items() if 0xC800 <= i & 0xFFFF and (i < 0x10000 or i >= 0x1C800)}

        _, plain = objects_alone(header + bytes([0xFF]))        # what the header alone writes (a layer 2 pass, for example)
        for candidate in self._candidates():
            if candidate in tried:
                continue
            tried.add(candidate)
            data = header + bytes([screen, 0, 1]) + self.object_bytes(*candidate, row, column) + b'\xff'
            run_ram = bytearray(start_ram)
            run = _Cpu(self.rom, run_ram)
            run.restore(start)
            run.patch = {start_offset + i: v for i, v in enumerate(data)}
            run.writes = {}
            try:
                run.go([self.BUILD_DONE], 200_000)
            except _CpuStop:
                continue
            places = {i for i in run.writes if 0xC800 <= i & 0xFFFF and (i < 0x10000 or i >= 0x1C800)}
            if places and places <= place and min(place) in places:
                low, high = sorted(place)
                block = run_ram[low] | run_ram[high] << 8
                found.setdefault(block, candidate)
            if wanted is not None and set(wanted) <= set(found):
                return found
        cache[key][1] = True
        return found

    def free_space(self, size: int, avoid=()):
        """A ROM offset with room for size bytes: inside a run of $FF that fills the end of a bank (padding nothing
        reads), 16 bytes after the run starts, never across a bank (the builder's pointer only carries into its middle
        byte). Banks are tried from the last one down."""
        for bank in range(len(self.rom) // 0x8000 - 1, 0, -1):
            end = (bank + 1) * 0x8000
            start = end
            while start > bank * 0x8000 and self.rom[start - 1] == 0xFF:
                start -= 1
            at = start + 16
            for lo_, hi_ in sorted(avoid):
                if lo_ < at + size and at < hi_:
                    at = hi_ + 16
            if at + size <= end:
                return at
        return None


class _SmwSpriteWatcher(Watcher):
    """A sprite edit. A swap is seen when a sprite slot filled from that list entry ($161A = index, $14C8 not 0) holds
    the chosen number ($9E). A removal is seen when the camera has passed the spot and no sprite of that number appeared
    there (slots are checked for where each sprite first shows, $E4/$14E0 x and $D8/$14D4 y)."""
    every = 3

    def __init__(self, watch):
        self.w = watch
        self.seen = None
        self.reached = 0
        self.slots = {}

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x100] != 0x14 or ram[0xD0] != 0x07 or (ram[0xCE] | ram[0xCF] << 8) != w['list'] & 0xFFFF:
            return False
        if w['remove']:
            for slot in range(12):
                status = ram[0x14C8 + slot]
                key = (ram[0x161A + slot], ram[0x9E + slot])
                if not status:
                    self.slots.pop(slot, None)
                    continue
                if self.slots.get(slot) == key:
                    continue
                self.slots[slot] = key
                x = ram[0xE4 + slot] | ram[0x14E0 + slot] << 8
                y = ram[0xD8 + slot] | ram[0x14D4 + slot] << 8
                if key[1] == w['shown'] and abs(x - w['x']) <= 8 and abs(y - w['y']) <= 8:
                    self.seen = 'there'
                    return True
            camera = (ram[0x1C] | ram[0x1D] << 8) if w['vertical'] else (ram[0x1A] | ram[0x1B] << 8)
            spot = w['y'] if w['vertical'] else w['x']
            if camera <= spot <= camera + 224:
                self.reached += 1
                if self.reached > 30:
                    self.seen = 'gone'
                    return True
            return False
        for slot in range(12):
            if ram[0x14C8 + slot] and ram[0x161A + slot] == w['index']:
                self.seen = ram[0x9E + slot]
                return True
        return False

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if w['remove']:
            ok = self.seen == 'gone'
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the screen reached that spot and no {w["name"]} appeared there.' if ok
                    else f'Played from the start, a {w["name"]} still appears there.'}
        ok = self.seen == w['shown']
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the game now puts {w["name"]} there.' if ok
                else f'Played from the start, the game put sprite {self.seen:#04x} there, not the one chosen.'}


class _SmwRamWatcher(Watcher):
    """A block or exit edit: once the level has loaded, the game's own decoded copy in RAM (the level's blocks at
    $7EC800/$7FC800, or the screen exit table at $19B8) must show the chosen value."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x100] != 0x14 or ram[0xD0] != 0x07 or (ram[0xCE] | ram[0xCF] << 8) != w['list'] & 0xFFFF:
            return False
        if w['kind'] == 'exit':
            self.seen = ram[0x19B8 + w['screen']]
        else:
            low, high = w['ram']
            self.seen = ram[low] | (ram[high] & 1) << 8
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        ok = self.seen == w['value']
        if w['kind'] == 'exit':
            return {'state': 'good' if ok else 'bad',
                    'text': f'Played from the start, the level loads with this exit leading to {w["name"]}.' if ok
                    else f'Played from the start, the level loads with this exit leading to {self.seen:#04x}, not the one chosen.'}
        return {'state': 'good' if ok else 'bad',
                'text': f'Played from the start, the level loads with a {w["name"][0].lower() + w["name"][1:]} here.' if ok
                else f'Played from the start, the level loads with block tile {self.seen:#05x} there, not the one chosen.'}


class _SmwLayoutWatcher(Watcher):
    """A layout change: once the level has loaded, the game's decoded blocks in RAM ($7EC800 low bytes, $7FC800 high
    bytes) must be the chosen blocks at every changed place."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if ram[0x100] != 0x14 or ram[0xD0] != 0x07 or (ram[0xCE] | ram[0xCF] << 8) != w['list'] & 0xFFFF:
            return False
        self.seen = [ram[low] | ram[high] << 8 for low, high, _ in w['spots']]
        return True

    def result(self):
        if self.seen is None:
            return super().result()
        wrong = [(got, spot[2]) for got, spot in zip(self.seen, self.w['spots']) if got != spot[2]]
        if not wrong:
            return {'state': 'good', 'text': 'Played from the start, the level loads with the new blocks in place.'}
        got, want = wrong[0]
        return {'state': 'bad', 'text': f'Played from the start, the level loads with block {got:03X} where {want:03X} should be.'}


class SuperMarioWorldProfile(SuperMarioWorld, Profile):
    """Parts are {'level': number}; x and y are the level's pixels (the camera is $1A/$1C)."""
    sha256s = (SuperMarioWorld.sha256,)
    system = 'snes'

    def __init__(self, rom: bytes):
        SuperMarioWorld.__init__(self, rom)

    def where(self, ram):
        if ram[0x100] != 0x14:
            return None
        level = self.level_of(ram)
        if level is None:
            return None
        return {'part': {'level': level}, 'x': ram[0x1A] | ram[0x1B] << 8, 'y': ram[0x1C] | ram[0x1D] << 8}

    def part_name(self, part):
        return f'Level {part["level"]:03X}'

    def choices(self):
        out = {}
        for gfx in sorted({self.sprite_gfx(lv) for lv in range(self.LEVELS)}):
            out[f'sprites{gfx}'] = [{'value': n, 'name': self.sprite_name(n)} for n in self.swap_choices(gfx)]
        out['blocks'] = [{'value': ext, 'name': self.block_name(ext)} for ext in sorted(self.BLOCKS)]
        return out

    def objects(self, part):
        level = int(part['level'])
        out = []
        users = self.list_users(level)
        gfx = self.sprite_gfx(level)
        for entry in self.sprite_list(level):
            number, kind = entry['number'], self.kind(entry['number'])
            row = {'id': f'sprite:{entry["index"]}', 'style': 'item' if number in self.ITEMS else 'enemy', 'type': number,
                   'x': entry['x'] + 8, 'y': entry['y'] + 16, 'name': self.sprite_name(number), 'remove': None, 'fields': []}
            if kind == 'sprite':
                row['remove'] = 'Remove this sprite'
                row['fields'] = [{'key': 'number', 'label': 'Swap for', 'value': number, 'choices': f'sprites{gfx}'}]
            else:
                row['note'] = {'shooter': 'A shooter: it fires from this spot while it is on screen.',
                               'generator': 'A generator: from here on it keeps sending sprites for the rest of the level.',
                               'scroller': 'A scroll command: it moves a layer of the level from here on.',
                               'special': 'A group the game places as one entry.'}[kind]
            if entry['extra']:
                row['detail'] = f'extra setting {entry["extra"]}'
            if len(users) > 1:
                others = ', '.join(f'{u:03X}' for u in users if u != level)
                row['note'] = ((row['note'] + ' ') if row.get('note') else '') + \
                    f'This sprite list is shared with level {others}, so a change shows there too.'
            out.append(row)
        for block in self.blocks(level):
            out.append({'id': f'block:{block["offset"]:x}', 'style': 'secret', 'type': block['tile'], 'x': block['x'] + 8,
                        'y': block['y'] + 16, 'name': self.block_name(block['ext']), 'remove': None,
                        'fields': [{'key': 'ext', 'label': 'Block', 'value': block['ext'], 'choices': 'blocks'}]})
        for ex in self.exits(level):
            choices = self.exit_choices(level, ex)
            if not choices:
                continue
            vertical = self.vertical(level)
            out.append({'id': f'exit:{ex["screen"]}', 'style': 'block', 'type': 'exit',
                        'x': 128 if vertical else ex['screen'] * 256 + 128, 'y': ex['screen'] * 256 + 128 if vertical else 400,
                        'name': 'Screen exit', 'detail': f'leads to {self.exit_name(level, ex["to"], ex["secondary"])}',
                        'note': 'Every door and pipe on this screen that leads out uses this exit.', 'remove': None,
                        'fields': [{'key': 'to', 'label': 'Leads to', 'value': ex['to'], 'choices': choices}]})
        return out

    def exit_name(self, level: int, to: int, secondary: bool) -> str:
        if secondary:
            return f'secondary entrance {to:02X}'
        return f'level {(to | (level & 0x100)):03X}'

    def exit_choices(self, level: int, ex: dict) -> list:
        """Places other screen exits of the same kind (level or secondary entrance) on the same map half lead to."""
        key = ('exits', level >> 8, ex['secondary'])
        if key not in self._cache:
            seen = set()
            for other in range(self.LEVELS):
                if other >> 8 != level >> 8:
                    continue
                for e in self.exits(other):
                    if e['secondary'] == ex['secondary']:
                        seen.add(e['to'])
            self._cache[key] = sorted(seen)
        return [{'value': v, 'name': self.exit_name(level, v, ex['secondary']).capitalize()} for v in self._cache[key]]

    def edit(self, part, object_id, values, remove=False):
        level = int(part['level'])
        kind, _, number = object_id.partition(':')
        base = {'list': self.list_address(level), 'level': level}
        if kind == 'sprite':
            index = int(number)
            entries = self.sprite_list(level)
            if not 0 <= index < len(entries):
                raise ValueError('That is not part of this level any more. Reopen the map.')
            entry = entries[index]
            if self.kind(entry['number']) != 'sprite':
                raise ValueError('ROMancer cannot change that yet.')
            if remove:
                return {'writes': self.remove_writes(level, index), 'title': f'Remove the {self.sprite_name(entry["number"])}',
                        'watch': {**base, 'kind': 'sprite', 'remove': True, 'index': index, 'shown': self.shown(entry['number']),
                                  'x': entry['x'], 'y': entry['y'], 'vertical': self.vertical(level),
                                  'name': self.sprite_name(entry['number'])}}
            new = int(values.get('number', entry['number']))
            if new not in self.swap_choices(self.sprite_gfx(level)):
                raise ValueError('That choice is not one of the game’s own.')
            offset = entry['offset'] + 2
            writes = [(offset, self.rom[offset], new)] if self.rom[offset] != new else []
            return {'writes': writes, 'title': f'Sprite here: {self.sprite_name(new)}',
                    'watch': {**base, 'kind': 'sprite', 'remove': False, 'index': index, 'shown': self.shown(new),
                              'name': self.sprite_name(new)}}
        if kind == 'block':
            block = next((b for b in self.blocks(level) if f'{b["offset"]:x}' == number), None)
            if block is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            new = int(values.get('ext', block['ext']))
            if new not in self.BLOCKS:
                raise ValueError('That choice is not one of the game’s own.')
            offset = block['offset'] + 2
            writes = [(offset, self.rom[offset], new)] if self.rom[offset] != new else []
            name = self.block_name(new)
            return {'writes': writes, 'title': f'Block here: {name}',
                    'watch': {**base, 'kind': 'block', 'ram': self.block_ram(level, block['screen'], block['row'], block['col']),
                              'value': self.BLOCKS[new][0], 'name': name}}
        if kind == 'exit':
            screen = int(number)
            ex = next((e for e in self.exits(level) if e['screen'] == screen), None)
            if ex is None:
                raise ValueError('That is not part of this level any more. Reopen the map.')
            new = int(values.get('to', ex['to']))
            if new not in [c['value'] for c in self.exit_choices(level, ex)]:
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(ex['offset'], self.rom[ex['offset']], new)] if self.rom[ex['offset']] != new else []
            name = self.exit_name(level, new, ex['secondary'])
            return {'writes': writes, 'title': f'Screen exit leads to {name}',
                    'watch': {**base, 'kind': 'exit', 'screen': screen, 'value': new, 'name': name}}
        raise ValueError('ROMancer cannot change that yet.')

    def packed_layout(self, part):
        level = int(part['level'])
        screens = self.layout_screens(level)
        if screens is None:
            return None
        return {'size': 16, 'width': screens * 16, 'height': self.ROWS, 'blocks': self.decoded(level), 'left': 0, 'top': 0}

    def set_packed_layout(self, part, changes):
        """Put blocks in a level: for each one, a screen jump and an object that puts exactly that block (found by
        running the game's builder) go after the level's own objects, so they are built last. The longer object list
        moves to free space and the level's pointer ($05E000 + level * 3) points at it; levels that shared the old list
        keep it. The whole level is built again with the new bytes and must come out exactly as asked."""
        level = int(part['level'])
        screens = self.layout_screens(level)
        if screens is None:
            raise ValueError('ROMancer cannot change the layout of this level: it scrolls up and down, or it is a boss room.')
        width = screens * 16
        wanted = {}
        for column, row, block in changes:
            column, row, block = int(column), int(row), int(block)
            if not (0 <= column < width and 0 <= row < self.ROWS):
                raise ValueError('That place is outside the level.')
            wanted[(column, row)] = block
        if not wanted:
            raise ValueError('Paint something first.')
        found = self.single_blocks(level, set(wanted.values()))
        missing = sorted({b for b in wanted.values() if b not in found})
        if missing:
            raise ValueError('The game has no object that puts block ' + ', '.join(f'{b:03X}' for b in missing) +
                             ' by itself in this level, so ROMancer cannot place it exactly.')
        data = bytearray(self.objects_data(level))
        for (column, row), block in sorted(wanted.items(), key=lambda item: (item[0][0] // 16, item[0])):
            data += bytes([column // 16, 0x00, 0x01])                  # screen jump ($0DA100 extended object 1)
            data += self.object_bytes(*found[block], row, column % 16)
        before = self.build(level)
        # two more screen jumps leave the builder's screen ($1928) and its copy ($1BA1) as the level's own list left them
        data += bytes([before[0x1BA1] & 0x1F, 0x00, 0x01, before[0x1928] & 0x1F, 0x00, 0x01, 0xFF])
        at = self.free_space(len(data))
        if at is None:
            raise ValueError('There is no free space left in the cartridge for this level’s longer object list.')
        pointer = lorom(self.LAYER1 + level * 3)
        address = (at // 0x8000) << 16 | 0x8000 | at % 0x8000
        writes = [(at + i, self.rom[at + i], v) for i, v in enumerate(data)]
        writes += [(pointer + i, self.rom[pointer + i], v) for i, v in enumerate(address.to_bytes(3, 'little'))]
        writes = [w for w in writes if w[1] != w[2]]
        # check: the game's own builder must give exactly the asked blocks, and the rest of its RAM as it was (apart from
        # its scratch bytes, its pointers into the object list and the stack)
        after = self.build(level, {off: new for off, _, new in writes})
        old_blocks, new_blocks = self.decoded(level, before), self.decoded(level, after)
        expect = list(old_blocks)
        for (column, row), block in wanted.items():
            expect[row * width + column] = block
        spots = [[*self.spot(level, column, row), block] for (column, row), block in sorted(wanted.items())]
        places = {i for spot in spots for i in spot[:2]}
        scratch = set(range(0x10)) | set(range(0x57, 0x5B)) | set(range(0x65, 0x70)) | set(range(0x100, 0x200))
        others = [i for i in range(len(after)) if after[i] != before[i] and i not in places and i not in scratch]
        if new_blocks != expect or others:
            raise ValueError('The game would not build that exactly, so ROMancer did not change it.')
        count = len(wanted)
        title = f'Layout: {count} block{"s" if count > 1 else ""} in level {level:03X}'
        return {'writes': writes, 'title': title,
                'watch': {'kind': 'layout', 'list': self.list_address(level), 'level': level, 'spots': spots}}

    def shown(self, number: int) -> int:
        """The number the sprite slot gets ($02A97A): shells become the matching Koopa number."""
        return number - 0xDA + 4 if number in self.SHELLS else number

    def watcher(self, watch):
        if watch['kind'] == 'sprite':
            return _SmwSpriteWatcher(watch)
        if watch['kind'] == 'layout':
            return _SmwLayoutWatcher(watch)
        return _SmwRamWatcher(watch)



# --------------------------------------------------------------------------------------------- Super Metroid

# Super Metroid level data: the game's own decompressor ($80B0FF / $80B119) in Python, and a compressor that writes
# only the command formats that decompressor reads.
#
# Command byte c ($FF ends the data):
# * c >> 5 != 7: command = c & $E0, length = (c & $1F) + 1
# * c >> 5 == 7 (long form): command = (c << 3) & $E0, length = ((c & 3) << 8 | next byte) + 1
# Commands: $00 copy the next length bytes; $20 one byte, repeated; $40 two bytes a, b, written a b a b ... (length
# bytes in all); $60 one byte, written counting up by one; $80 copy from an earlier place in the output (2-byte offset
# from the start of the output, low byte first); $A0 the same with every byte inverted (EOR #$FF); $C0 copy from one
# byte back distance before the current place (1 byte); $E0 the same inverted (only in the long form, c = $FC-$FE).
# Copies go one byte at a time, so they may overlap what they are writing. Reading crosses into the next bank at
# $8000 ($80B266), which is the next byte of a LoROM file.


def _sm_decompress(rom: bytes, offset: int):
    """(data, compressed length) of the compressed data at a ROM file offset."""
    out = bytearray()
    i = offset
    while True:
        c = rom[i]
        i += 1
        if c == 0xFF:
            return bytes(out), i - offset
        if c >> 5 == 7:
            cmd = (c << 3) & 0xE0
            length = ((c & 3) << 8 | rom[i]) + 1
            i += 1
        else:
            cmd, length = c & 0xE0, (c & 0x1F) + 1
        if cmd == 0x00:
            out += rom[i:i + length]
            i += length
        elif cmd == 0x20:
            out += bytes([rom[i]]) * length
            i += 1
        elif cmd == 0x40:
            a, b = rom[i], rom[i + 1]
            i += 2
            out += (bytes([a, b]) * (length // 2 + 1))[:length]
        elif cmd == 0x60:
            v = rom[i]
            i += 1
            out += bytes((v + k) & 0xFF for k in range(length))
        else:
            if cmd < 0xC0:
                src = rom[i] | rom[i + 1] << 8
                i += 2
            else:
                src = len(out) - rom[i]
                i += 1
            invert = 0xFF if cmd & 0x20 else 0
            for k in range(length):
                out.append(out[src + k] ^ invert)


def _sm_header(cmd: int, length: int) -> bytes:
    """Command byte(s) for a command of length bytes (1..1024)."""
    n = length - 1
    if n < 32 and cmd != 0xE0:
        return bytes([cmd | n])
    return bytes([0xE0 | (cmd >> 3) | n >> 8, n & 0xFF])


def _sm_hsize(cmd: int, length: int) -> int:
    return 1 if length <= 32 and cmd != 0xE0 else 2


_SM_MAX = 1024


def _sm_lengths(k: int):
    """Lengths worth trying for a fill or copy that could go k bytes: the short ones, the longest one header byte
    can say, and the longest."""
    return sorted({x for x in (2, 3, 4, min(k, 32), k) if 2 <= x <= k})


def _sm_compress(data: bytes) -> bytes:
    """Compressed bytes (ending in $FF) that decompress to exactly data. An optimal parse over the game's commands
    (fills and copies of lengths 2-4, 32 and their longest, literals of any length)."""
    data = bytes(data)
    n = len(data)
    inv = bytes(b ^ 0xFF for b in data)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    how = [None] * (n + 1)              # (start, cmd, length, argument bytes)
    cost[0] = 0
    chains: dict = {}                   # 3-byte key -> positions (latest last)

    def extend(p, i, src, limit):
        k = 0
        while k + 16 <= limit and src[p + k:p + k + 16] == data[i + k:i + k + 16]:
            k += 16
        while k < limit and src[p + k] == data[i + k]:
            k += 1
        return k

    def offer(i, j, c, step):
        if c < cost[j]:
            cost[j], how[j] = c, step

    # literal runs: cost[j] = min over i in [j-1024, j-1] of cost[i] + header + (j - i); done lazily per position
    from collections import deque
    # how far each kind of fill could go from each place (counted from the end)
    run1, run2, run3 = [1] * (n + 1), [1] * (n + 1), [1] * (n + 1)
    for i in range(n - 2, -1, -1):
        if data[i + 1] == data[i]:
            run1[i] = run1[i + 1] + 1
        if data[i + 1] == (data[i] + 1) & 0xFF:
            run3[i] = run3[i + 1] + 1
    tail = 0                            # places from i on where data[k + 2] == data[k]
    for i in range(n - 1, -1, -1):
        tail = tail + 1 if i + 2 < n and data[i + 2] == data[i] else 0
        run2[i] = min(n - i, 2 + tail) if n - i >= 2 else 1
    last: dict = {}
    short, long_ = deque(), deque()     # (value cost[i]-i, i), increasing values
    for i in range(n + 1):
        # literals ending at i (from earlier starts)
        if i > 0:
            k = i - 1
            v = cost[k] - k
            while short and short[-1][0] >= v:
                short.pop()
            short.append((v, k))
            while short and short[0][1] < i - 32:
                moved = short.popleft()
                while long_ and long_[-1][0] >= moved[0]:
                    long_.pop()
                long_.append(moved)
            while long_ and long_[0][1] < i - _SM_MAX:
                long_.popleft()
            if short:
                v, k = short[0]
                offer(k, i, v + i + 1, (k, 0x00, i - k, None))
            if long_:
                v, k = long_[0]
                offer(k, i, v + i + 2, (k, 0x00, i - k, None))
        if i == n:
            break
        base = cost[i]
        left = min(_SM_MAX, n - i)
        b = data[i]
        r, r2, r3 = min(run1[i], left), min(run2[i], left), min(run3[i], left)
        for cmd, run, extra in ((0x20, r, 1), (0x40, r2, 2), (0x60, r3, 1)):
            if run < 2:
                continue
            arg = bytes([b]) if extra == 1 else data[i:i + 2]
            for length in _sm_lengths(run):
                offer(i, i + length, base + _sm_hsize(cmd, length) + extra, (i, cmd, length, arg))
        # copies
        if left >= 3:
            key = data[i:i + 3]
            best = {}
            for src, cmd_abs, cmd_rel in ((data, 0x80, 0xC0), (inv, 0xA0, 0xE0)):
                carried = last.get(cmd_abs)
                if carried and carried[0] > 64:         # still inside a long copy: the same source one byte on
                    far = near = (min(carried[0] - 1, left), carried[1] + 1)
                    if i - near[1] > 255:
                        near = last.get(cmd_rel, (0, 0))
                        near = (min(near[0] - 1, left), near[1] + 1) if near[0] > 2 else (0, 0)
                    best[cmd_abs] = far
                    if near[0] >= 2:
                        best[cmd_rel] = near
                    continue
                positions = chains.get(('i' if src is inv else 'd', key))
                if not positions:
                    continue
                far = near = (0, 0)
                for count, p in enumerate(reversed(positions)):
                    if count >= 24:
                        break
                    k = extend(p, i, src, left)
                    if k > far[0]:
                        far = (k, p)
                    if i - p <= 255 and k > near[0]:
                        near = (k, p)
                if far[0] >= 3:
                    best[cmd_abs] = far
                if near[0] >= 2:
                    best[cmd_rel] = near
            last = dict(best)
            for cmd, (k, p) in best.items():
                if cmd == 0xE0:
                    k = min(k, 768)         # a long-form $E0 of 769 or more would be the end byte $FF
                arg = bytes([p & 0xFF, p >> 8]) if cmd < 0xC0 else bytes([i - p])
                for length in _sm_lengths(k):
                    offer(i, i + length, base + _sm_hsize(cmd, length) + len(arg), (i, cmd, length, arg))
        # index this position: by its own bytes (for plain copies) and by its inverted bytes (for inverted copies)
        if i + 3 <= n:
            chains.setdefault(('d', data[i:i + 3]), []).append(i)
            chains.setdefault(('i', inv[i:i + 3]), []).append(i)
    # walk back
    steps = []
    j = n
    while j > 0:
        step = how[j]
        steps.append(step)
        j = step[0]
    out = bytearray()
    for start, cmd, length, arg in reversed(steps):
        out += _sm_header(cmd, length)
        out += data[start:start + length] if cmd == 0x00 else arg
    out.append(0xFF)
    return bytes(out)


class SuperMetroid:
    """Super Metroid (Japan, USA). Room header (bank $8F): +1 area, +4 width, +5 height (screens), +9 door list,
    +11 states. States ($8FE5E6 and the condition codes before it): each condition code is followed by its arguments and
    a state pointer; $E5E6 ends the list and its state follows it directly. State data (26 bytes, read at $82DEF7):
    +8 enemy population (bank $A1), +$0A enemy set (bank $B4), +$14 room objects (PLMs, bank $8F; spawned at $84846A).

    Enemy population ($A08ADE): 16 bytes each (species, x, y, tilemap, properties, extra, two parameters), $FFFF ends
    it, then one byte: how many must be killed to open grey doors. Entry n goes to enemy slot n ($0F78 + n * $40 species,
    $0F7A x, $0F7E y). Species names are the game's own (species header + $3E points to a 10-letter name in bank $B4).
    Room objects: 6 bytes (id, x block, y block, parameter), 0 ends it; the spawner writes the id to $1C37 + slot * 2 and
    the block index * 2 to $1C87 + slot * 2.
    """
    name = 'Super Metroid'
    sha256 = '12b77c4bc9c1832cee8881244659065ee1d84c70c3d29e6eaf92e6798cc2ca72'
    CONDITIONS = {0xE5EB: 4, 0xE5FF: 2, 0xE612: 3, 0xE629: 3, 0xE640: 2, 0xE652: 2, 0xE669: 2, 0xE678: 2}
    FIRST_ROOMS = (0x91F8, 0xDF45)      # the landing site and Ceres station; every other room is found through doors
    # Item objects: three styles of 21 items each (in the open, held by a statue, hidden in a block). Every item of the
    # first style was put in Ceres and picked up (trace/v15_profiles/snes_classics/smitems.py, smitems/results*.txt): the
    # RAM it changed and the message it showed ($1C1F) are recorded there; the names are the game's own message texts
    # ($85869B). The other two styles run the same pickup code with the same values (their instruction lists in bank $84).
    ITEMS = ['Energy Tank', 'Missile', 'Super Missile', 'Power Bomb', 'Bomb', 'Charge Beam', 'Ice Beam', 'Hi-Jump Boots',
             'Speed Booster', 'Wave Beam', 'Spazer', 'Spring Ball', 'Varia Suit', 'Gravity Suit', 'X-Ray Scope',
             'Plasma Beam', 'Grappling Beam', 'Space Jump', 'Screw Attack', 'Morphing Ball', 'Reserve Tank']
    STYLES = {0xEED7: 'item', 0xEF2B: 'item on a statue', 0xEF7F: 'hidden item'}
    # the statue and hidden versions of the Morphing Ball give a different equipment bit than the one in the open
    # (their pickup data says $0002, not $0004), so they are not offered
    ODD = {0xEF77, 0xEFCB}

    def __init__(self, rom: bytes):
        self.rom = rom
        self._cache = {}

    def b(self, address: int) -> int:
        return self.rom[lorom(address)]

    def w(self, address: int) -> int:
        return self.b(address) | self.b(address + 1) << 8

    def doors(self, room: int) -> list:
        """Rooms the door list of a room leads to."""
        at, out = 0x8F0000 | self.w(0x8F0000 | room + 9), []
        for _ in range(40):
            door = self.w(at)
            if not 0x8800 <= door < 0xC000:
                break
            out.append(self.w(0x830000 | door))
            at += 2
        return out

    def rooms(self) -> list:
        if 'rooms' not in self._cache:
            seen, todo = set(), list(self.FIRST_ROOMS)
            while todo:
                room = todo.pop()
                if room in seen:
                    continue
                seen.add(room)
                todo += [r for r in self.doors(room) if r >= 0x91F8]
            self._cache['rooms'] = sorted(seen)
        return self._cache['rooms']

    def states(self, room: int) -> list:
        """State data addresses (16 bits, bank $8F) of a room, the default one last."""
        at, out = 0x8F0000 | room + 11, []
        for _ in range(16):
            code = self.w(at)
            if code == 0xE5E6:
                out.append((at + 2) & 0xFFFF)
                return out
            size = self.CONDITIONS.get(code)
            if size is None:
                break
            out.append(self.w(at + size))
            at += 2 + size
        return out

    def area(self, room: int) -> int:
        return self.b(0x8F0000 | room + 1)

    def species_name(self, species: int) -> str:
        pointer = self.w(0xA00000 | species + 0x3E)
        if pointer >= 0x8000:
            text = bytes(self.b(0xB40000 | pointer + i) for i in range(10)).decode('ascii', 'replace').strip()
            if text and all(c.isalnum() or c in ' -' for c in text):
                return text.title()
        return f'Enemy {species:#06x}'

    def enemies(self, state: int) -> list:
        at, out = 0xA10000 | self.w(0x8F0000 | state + 8), []
        while self.w(at) != 0xFFFF and len(out) < 32:
            out.append({'index': len(out), 'offset': lorom(at), 'species': self.w(at), 'x': self.w(at + 2), 'y': self.w(at + 4)})
            at += 16
        return out

    def enemy_set(self, state: int) -> list:
        """Species whose graphics the room loads (bank $B4: species, palette; $FFFF ends it)."""
        at, out = 0xB40000 | self.w(0x8F0000 | state + 0x0A), []
        while self.w(at) != 0xFFFF and len(out) < 16:
            out.append(self.w(at))
            at += 4
        return out

    def objects_list(self, state: int) -> list:
        at, out = 0x8F0000 | self.w(0x8F0000 | state + 0x14), []
        while self.w(at) and len(out) < 64:
            out.append({'index': len(out), 'offset': lorom(at), 'id': self.w(at), 'x': self.b(at + 2), 'y': self.b(at + 3),
                        'param': self.w(at + 4)})
            at += 6
        return out

    def item_of(self, plm: int):
        """(style base, item number) of an item object, or None."""
        for base in self.STYLES:
            if base <= plm < base + 4 * 21 and (plm - base) % 4 == 0:
                return base, (plm - base) // 4
        return None

    def population_regions(self) -> list:
        if 'pops' not in self._cache:
            regions = set()
            for room in self.rooms():
                for state in self.states(room):
                    start = lorom(0xA10000 | self.w(0x8F0000 | state + 8))
                    regions.add((start, start + len(self.enemies(state)) * 16 + 3))
            self._cache['pops'] = sorted(regions)
        return self._cache['pops']

    def remove_enemy_writes(self, state: int, index: int) -> list:
        """Take one enemy out: later entries move up, $FFFF and the kill count follow one entry sooner (the kill count
        is lowered when it asked for more enemies than are left)."""
        entries = self.enemies(state)
        start = lorom(0xA10000 | self.w(0x8F0000 | state + 8))
        end = start + len(entries) * 16                 # the $FFFF
        kill = self.rom[end + 2]
        old = self.rom[entries[index]['offset']:end + 3]
        new = self.rom[entries[index]['offset'] + 16:end] + b'\xff\xff' + bytes([min(kill, len(entries) - 1)])
        new += old[len(new):]                           # bytes after the new end stay as they were
        writes = [(entries[index]['offset'] + i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]
        for other in self.population_regions():
            if other != (start, end + 3) and any(other[0] <= off < other[1] for off, _, _ in writes):
                raise ValueError('This enemy list runs into another room’s list, so ROMancer cannot shorten it safely.')
        return writes

    # ---- the layout: the room's level data, compressed ($80B119)
    def level_pointer(self, state: int) -> int:
        """CPU address of a room state's compressed level data (state +0, 3 bytes)."""
        return self.w(0x8F0000 | state) | self.b(0x8F0000 | state + 2) << 16

    def level_data(self, state: int):
        """(decompressed level data, compressed length) of a room state."""
        key = ('level', self.level_pointer(state))
        if key not in self._cache:
            self._cache[key] = _sm_decompress(self.rom, lorom(self.level_pointer(state)))
        return self._cache[key]

    def level_users(self, state: int) -> list:
        """Every (room, state) whose level data is the same as this state's."""
        pointer = self.level_pointer(state)
        return sorted({(r, s) for r in self.rooms() for s in self.states(r) if self.level_pointer(s) == pointer})

    def room_blocks(self, room: int) -> tuple:
        return self.b(0x8F0000 | room + 4) * 16, self.b(0x8F0000 | room + 5) * 16

    def free_space(self, size: int, first_bank: int):
        """A ROM offset with room for size bytes in a run of $FF that fills the end of a bank (padding nothing reads),
        16 bytes after the run starts; the level data's own bank is tried first, then the others from the last one down."""
        banks = len(self.rom) // 0x8000
        for bank in [first_bank] + list(range(banks - 1, -1, -1)):
            end = (bank + 1) * 0x8000
            start = end
            while start > bank * 0x8000 and self.rom[start - 1] == 0xFF:
                start -= 1
            if start + 16 + size <= end:
                return start + 16
        return None


def _word(ram, address):
    return ram[address] | ram[address + 1] << 8


class _SmEnemyWatcher(Watcher):
    """An enemy edit: when the room has loaded (game state 8, the room and its state in $079B / $07BB), enemy slot n holds
    the chosen species; a removed enemy is in no slot (species and position)."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if _word(ram, 0x998) != 8 or _word(ram, 0x79B) != w['room'] or _word(ram, 0x7BB) != w['state']:
            return False
        slots = [(_word(ram, 0xF78 + n * 0x40), _word(ram, 0xF7A + n * 0x40), _word(ram, 0xF7E + n * 0x40)) for n in range(32)]
        if w['remove']:
            there = any(s[0] == w['species'] and abs(s[1] - w['x']) < 4 and abs(s[2] - w['y']) < 4 for s in slots)
            self.seen = 'there' if there else 'gone'
        else:
            self.seen = slots[w['index']][0]
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        if w['remove']:
            ok = self.seen == 'gone'
            return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the room loads without that {w["name"]}.' if ok
                    else f'Played from the start, the {w["name"]} is still in the room.'}
        ok = self.seen == w['species']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the room loads with {w["name"]} there.' if ok
                else f'Played from the start, the room loads with enemy {self.seen:#06x} there, not the one chosen.'}


class _SmItemWatcher(Watcher):
    """An item edit: when the room has loaded, a room object slot at that block ($1C87) holds the chosen item ($1C37)."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if _word(ram, 0x998) != 8 or _word(ram, 0x79B) != w['room'] or _word(ram, 0x7BB) != w['state']:
            return False
        block = (w['y'] * _word(ram, 0x7A5) + w['x']) * 2
        found = [_word(ram, 0x1C37 + 2 * n) for n in range(40) if _word(ram, 0x1C87 + 2 * n) == block and _word(ram, 0x1C37 + 2 * n)]
        self.seen = found[0] if found else 0
        return True

    def result(self):
        w = self.w
        if self.seen is None:
            return super().result()
        ok = self.seen == w['id']
        return {'state': 'good' if ok else 'bad', 'text': f'Played from the start, the room loads with {w["name"]} at that spot.' if ok
                else f'Played from the start, the room loads with object {self.seen:#06x} at that spot, not the one chosen.'}


class _SmLayoutWatcher(Watcher):
    """A layout change: when the room has loaded, the game's decompressed level data in RAM must hold the chosen blocks:
    the layer 1 word at $7F0002 + block * 2 and the BTS byte at $7F6402 + block."""

    def __init__(self, watch):
        self.w = watch
        self.seen = None

    def see(self, ram, frame, run):
        w = self.w
        if _word(ram, 0x998) != 8 or _word(ram, 0x79B) != w['room'] or _word(ram, 0x7BB) != w['state']:
            return False
        self.seen = [_word(ram, 0x10002 + i * 2) | ram[0x16402 + i] << 16 for i, _ in w['spots']]
        return True

    def result(self):
        if self.seen is None:
            return super().result()
        wrong = [(got, spot[1]) for got, spot in zip(self.seen, self.w['spots']) if got != spot[1]]
        if not wrong:
            return {'state': 'good', 'text': 'Played from the start, the room loads with the new blocks in place.'}
        got, want = wrong[0]
        return {'state': 'bad', 'text': f'Played from the start, the room loads with block {got:06X} where {want:06X} should be.'}


class SuperMetroidProfile(SuperMetroid, Profile):
    """Parts are {'room': room header address in bank $8F, 'state': the room state in use}; x and y are room pixels
    (the camera is $0911 / $0915)."""
    sha256s = (SuperMetroid.sha256,)
    system = 'snes'

    def __init__(self, rom: bytes):
        SuperMetroid.__init__(self, rom)

    def where(self, ram):
        if _word(ram, 0x998) not in (8, 9, 0x0B) or _word(ram, 0x79B) < 0x91F8:
            return None
        return {'part': {'room': _word(ram, 0x79B), 'state': _word(ram, 0x7BB)}, 'x': _word(ram, 0x911), 'y': _word(ram, 0x915)}

    def part_name(self, part):
        room, state = int(part['room']), int(part['state'])
        states = self.states(room)
        name = f'Room {room:04X} (area {self.area(room)})'
        if len(states) > 1 and state in states:
            name += f', state {states.index(state) + 1} of {len(states)}'
        return name

    def item_name(self, plm: int) -> str:
        base, number = self.item_of(plm)
        return self.ITEMS[number] + {0xEED7: '', 0xEF2B: ' (on a statue)', 0xEF7F: ' (hidden)'}[base]

    def choices(self):
        return {f'items{base:04x}': [{'value': base + 4 * n, 'name': self.item_name(base + 4 * n)}
                                     for n in range(21) if base + 4 * n not in self.ODD] for base in self.STYLES}

    def _list_users(self, state: int) -> int:
        pointer = self.w(0x8F0000 | state + 8)
        return sum(1 for r in self.rooms() for s in set(self.states(r)) if self.w(0x8F0000 | s + 8) == pointer)

    def objects(self, part):
        room, state = int(part['room']), int(part['state'])
        users = self._list_users(state)
        out = []
        species_choices = [{'value': s, 'name': self.species_name(s)} for s in self.enemy_set(state)]
        for e in self.enemies(state):
            row = {'id': f'enemy:{e["index"]}', 'style': 'enemy', 'type': e['species'], 'x': e['x'],
                   'y': e['y'] + self.w(0xA00000 | e['species'] + 0x0A), 'name': self.species_name(e['species']),
                   'remove': 'Remove this enemy', 'fields': []}
            if species_choices:
                row['fields'] = [{'key': 'species', 'label': 'Swap for', 'value': e['species'], 'choices': species_choices}]
            if users > 1:
                row['note'] = f'This enemy list is shared with {users - 1} other room states, so a change shows there too.'
            out.append(row)
        for o in self.objects_list(state):
            found = self.item_of(o['id'])
            if not found:
                continue
            out.append({'id': f'item:{o["index"]}', 'style': 'secret' if found[0] == 0xEF7F else 'item', 'type': o['id'],
                        'x': o['x'] * 16 + 8, 'y': o['y'] * 16 + 16, 'name': self.item_name(o['id']), 'remove': None,
                        'fields': [{'key': 'id', 'label': 'Item', 'value': o['id'], 'choices': f'items{found[0]:04x}'}]})
        return out

    def edit(self, part, object_id, values, remove=False):
        room, state = int(part['room']), int(part['state'])
        kind, _, number = object_id.partition(':')
        number = int(number)
        base = {'room': room, 'state': state}
        if kind == 'enemy':
            entries = self.enemies(state)
            if not 0 <= number < len(entries):
                raise ValueError('That is not part of this room any more. Reopen the map.')
            e = entries[number]
            if remove:
                return {'writes': self.remove_enemy_writes(state, number), 'title': f'Remove the {self.species_name(e["species"])}',
                        'watch': {**base, 'kind': 'enemy', 'remove': True, 'species': e['species'], 'x': e['x'], 'y': e['y'],
                                  'name': self.species_name(e['species'])}}
            new = int(values.get('species', e['species']))
            if new not in self.enemy_set(state):
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(e['offset'] + i, self.rom[e['offset'] + i], v) for i, v in enumerate(new.to_bytes(2, 'little'))
                      if self.rom[e['offset'] + i] != v]
            return {'writes': writes, 'title': f'Enemy here: {self.species_name(new)}',
                    'watch': {**base, 'kind': 'enemy', 'remove': False, 'index': number, 'species': new,
                              'name': self.species_name(new)}}
        if kind == 'item':
            objects = self.objects_list(state)
            if not 0 <= number < len(objects) or not self.item_of(objects[number]['id']):
                raise ValueError('That is not part of this room any more. Reopen the map.')
            o = objects[number]
            new = int(values.get('id', o['id']))
            if self.item_of(new) is None or self.item_of(new)[0] != self.item_of(o['id'])[0] or new in self.ODD:
                raise ValueError('That choice is not one of the game’s own.')
            writes = [(o['offset'] + i, self.rom[o['offset'] + i], v) for i, v in enumerate(new.to_bytes(2, 'little'))
                      if self.rom[o['offset'] + i] != v]
            return {'writes': writes, 'title': f'Item here: {self.item_name(new)}',
                    'watch': {**base, 'kind': 'item', 'id': new, 'x': o['x'], 'y': o['y'], 'name': self.item_name(new)}}
        raise ValueError('ROMancer cannot change that yet.')

    def packed_layout(self, part):
        room, state = int(part['room']), int(part['state'])
        width, height = self.room_blocks(room)
        data, _ = self.level_data(state)
        size = data[0] | data[1] << 8
        if not width or size != width * height * 2 or len(data) < 2 + size + size // 2:
            return None
        bts = data[2 + size:]
        blocks = [data[2 + i * 2] | data[3 + i * 2] << 8 | bts[i] << 16 for i in range(width * height)]
        return {'size': 16, 'width': width, 'height': height, 'blocks': blocks, 'left': 0, 'top': 0}

    def set_packed_layout(self, part, changes):
        """Blocks are the layer 1 word (block number, flips and block type) with the BTS byte in bits 16-23. The level
        data is changed, compressed again in the game's own format, and written where it was when it fits and no other
        room uses it; otherwise it goes to free space and this room's states that used it point at the new copy."""
        room, state = int(part['room']), int(part['state'])
        grid = self.packed_layout(part)
        if grid is None:
            raise ValueError('ROMancer cannot read the layout of this room.')
        width, height = grid['width'], grid['height']
        data, old_length = self.level_data(state)
        new = bytearray(data)
        size = data[0] | data[1] << 8
        wanted = {}
        for column, row, block in changes:
            column, row, block = int(column), int(row), int(block)
            if not (0 <= column < width and 0 <= row < height):
                raise ValueError('That place is outside the room.')
            if not 0 <= block <= 0xFFFFFF:
                raise ValueError('That is not one of the game’s blocks.')
            i = row * width + column
            wanted[i] = block
            new[2 + i * 2], new[3 + i * 2], new[2 + size + i] = block & 0xFF, block >> 8 & 0xFF, block >> 16
        if not wanted:
            raise ValueError('Paint something first.')
        packed = _sm_compress(bytes(new))
        if _sm_decompress(packed, 0) != (bytes(new), len(packed)):
            raise ValueError('ROMancer could not pack this room again exactly, so it did not change it.')
        pointer = self.level_pointer(state)
        users = self.level_users(state)
        here = [s for r, s in users if r == room]
        start = lorom(pointer)
        if all(r == room for r, _ in users) and len(packed) <= old_length:
            writes = [(start + i, self.rom[start + i], v) for i, v in enumerate(packed) if self.rom[start + i] != v]
            moved = False
        else:
            at = self.free_space(len(packed), start // 0x8000)
            if at is None:
                raise ValueError('There is no free space left in the cartridge for this room’s level data.')
            address = 0x800000 | (at // 0x8000) << 16 | 0x8000 | at % 0x8000
            writes = [(at + i, self.rom[at + i], v) for i, v in enumerate(packed)]
            for s in sorted(set(here)):
                o = lorom(0x8F0000 | s)
                writes += [(o + i, self.rom[o + i], v) for i, v in enumerate(address.to_bytes(3, 'little'))]
            writes = [w for w in writes if w[1] != w[2]]
            moved = True
        count = len(wanted)
        title = f'Layout: {count} block{"s" if count > 1 else ""} in room {room:04X}'
        return {'writes': writes, 'title': title,
                'watch': {'kind': 'layout', 'room': room, 'state': state, 'moved': moved,
                          'spots': [[i, block] for i, block in sorted(wanted.items())]}}

    def watcher(self, watch):
        if watch['kind'] == 'layout':
            return _SmLayoutWatcher(watch)
        return _SmEnemyWatcher(watch) if watch['kind'] == 'enemy' else _SmItemWatcher(watch)


PROFILES = [SuperMarioWorldProfile, SuperMetroidProfile]
