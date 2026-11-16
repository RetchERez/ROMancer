"""Bounded SML column terrain, with physical operand provenance.

Format facts checked against original CPU construction and pinned source:
https://github.com/kaspermeerts/supermarioland/tree/618d00ed6c330928e106719533c6e294ae5d5726
This original implementation includes no game payload."""
from dataclasses import dataclass

WIDTH=20
HEIGHT=16
BANK_BYTES=0x4000
INTERACTIVE=frozenset((0x70,0x80,0x5f,0x81))

@dataclass(frozen=True)
class Operand:
    offset:int
    tile:int
    repeat:bool
    cells:tuple[int,...]

@dataclass(frozen=True)
class ColumnMap:
    encoded:bytes
    base:int
    tiles:tuple[int,...]
    origins:tuple[int|None,...]
    operands:tuple[Operand,...]
    overlaps:int
    @property
    def consumed(self):return len(self.encoded)


def decode_stream(raw,*,base=0):
    if type(raw)not in(bytes,bytearray)or type(base)is not int or not 0<=base<64*1024**2:
        raise ValueError('Invalid bounded terrain source.')
    raw=bytes(raw)
    if not raw or len(raw)>BANK_BYTES or base%BANK_BYTES+len(raw)>BANK_BYTES:
        raise ValueError('Terrain source crosses its declared bank window.')
    pointer=0;segments=0;overlaps=0
    tiles=[0x2c]*(WIDTH*HEIGHT);origins=[None]*(WIDTH*HEIGHT);operands=[]
    def read():
        nonlocal pointer
        if pointer>=len(raw):raise ValueError('Terrain column boundary or operand is missing.')
        value=raw[pointer];pointer+=1;return value
    def write_operand(offset,value,repeat,column,start,count):
        nonlocal overlaps
        cells=tuple(y*WIDTH+column for y in range(start,start+count))
        operands.append(Operand(offset,value,repeat,cells))
        for cell in cells:
            overlaps+=origins[cell]is not None
            tiles[cell]=value;origins[cell]=offset
    for column in range(WIDTH):
        while True:
            header=read()
            if header==0xfe:break
            segments+=1
            if segments>1024:raise ValueError('Terrain segment work limit exceeded.')
            row=header>>4;count=(header&15) or 16
            if row+count>HEIGHT:raise ValueError('Terrain segment exceeds the sixteen-row column.')
            for index in range(count):
                offset=base+pointer;tile=read()
                if tile==0xfd:
                    offset=base+pointer;tile=read()
                    write_operand(offset,tile,True,column,row+index,count-index)
                    break
                write_operand(offset,tile,False,column,row+index,1)
    return ColumnMap(raw[:pointer],base,tuple(tiles),tuple(origins),tuple(operands),overlaps)


def edit_operands(raw,*,base=0,edits):
    model=decode_stream(raw,base=base)
    if type(edits)is not list or len(edits)>WIDTH*HEIGHT:raise ValueError('Invalid terrain edit list.')
    if edits and model.overlaps:raise ValueError('Terrain overlap requires separate consumer verification.')
    by={o.offset:o for o in model.operands};seen=set();output=bytearray(model.encoded)
    for edit in edits:
        if type(edit)is not dict or set(edit)!={'offset','tile'}:raise ValueError('Invalid operand edit fields.')
        offset=edit['offset'];tile=edit['tile']
        if type(offset)is not int or offset not in by or offset in seen:raise ValueError('Choose one recorded operand offset.')
        if type(tile)is not int or not 0<=tile<=255:raise ValueError('Tile number must fit one byte.')
        seen.add(offset);operand=by[offset]
        if tile==operand.tile:continue
        if tile in INTERACTIVE or operand.tile in INTERACTIVE:raise ValueError('Interactive tile callbacks need a separate metadata edit.')
        if tile==0xfd and not operand.repeat:raise ValueError('A literal cannot become a repeat marker without a layout transform.')
        output[offset-base]=tile
    checked=decode_stream(output,base=base)
    if checked.consumed!=model.consumed or len(checked.operands)!=len(model.operands):raise ValueError('Edit changed the terrain grammar.')
    return bytes(output)
