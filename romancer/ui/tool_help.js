// Brief explanations of storage concepts. Game-specific meanings stay unknown.
const TERMS=[
 [/offset/i,"A byte's position in the selected file, counted from zero. CPU addresses are different."],
 [/stride/i,'Bytes from the start of one record to the start of the next. This can include unused bytes.'],
 [/capacity|allocation/i,'Maximum storage reserved for this resource. An edit must fit, including terminators and padding.'],
 [/palette/i,'A set of stored colors. Pixels refer to color indexes; the selected format determines their stored values.'],
 [/pointer/i,'A stored reference to another location. Its width, byte order and base determine how it is decoded.'],
 [/byte order|endian/i,'Little endian stores the least significant byte first. Big endian stores the most significant byte first.'],
 [/encoding|glyph/i,'The mapping between stored bytes and displayed characters. A game may use its own character table.'],
 [/terminator/i,'The byte that marks the end of a text record. It also uses space inside the slot.'],
 [/padding/i,'The value used to fill unused bytes in a fixed-size text slot.'],
 [/bank/i,'A numbered group of data. ROM banks and palette banks are different; use the declared layout.'],
 [/address/i,'A location in a declared CPU memory window. Translating it to a file offset may require the active bank.'],
 [/tile format|codec/i,'How the bytes encode pixels or samples. Selecting a format does not prove where the game stores that resource.'],
 [/tile index|brush value/i,'The numeric entry to place in a declared grid. Its game-specific meaning must be verified.'],
 [/crc/i,'A checksum of the selected byte scope. A mismatch needs an expected value for exactly the same scope.'],
 [/sha.?256/i,'A hash used to identify exact bytes. A changed ROM has a different identity.'],
 [/length|bytes to|byte count/i,'Number of bytes in this range, starting at the selected offset.'],
 [/control code/i,'A non-text instruction embedded in a text record, such as a pause or line break.'],
 [/collision/i,'Declared values used for movement or interaction. A numeric value alone does not prove what it does.']
];
export function fieldExplanation(label){return TERMS.find(([pattern])=>pattern.test(label))?.[1]||'';}
