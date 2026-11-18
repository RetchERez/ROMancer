import assert from 'node:assert/strict';
import zlib from 'node:zlib';
import {indexedPng,matchPalette,matchRows,matchSummary} from '../romancer/ui/battle_png.js';
const palette=[[0,0,36],[255,255,255],[0,0,0],[255,182,182],[255,145,145],[182,182,182],[72,72,72],[255,145,0],[255,0,0],[182,0,0],[0,0,218],[0,0,145],[255,255,36],[182,182,36],[145,145,255],[109,109,255]];
const width=320,height=128,pixels=Uint8Array.from({length:width*height},(_,i)=>(i+(i/width|0))%16);
const png=indexedPng(pixels,width,height,palette),view=new DataView(png.buffer);
assert.deepEqual([...png.subarray(0,8)],[0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]);
const chunks={};
for(let at=8;at<png.length;){
 const size=view.getUint32(at),type=String.fromCharCode(...png.subarray(at+4,at+8));
 assert.equal(view.getUint32(at+8+size),zlib.crc32(png.subarray(at+4,at+8+size)),`${type} checksum`);
 chunks[type]=png.subarray(at+8,at+8+size);at+=12+size;
}
assert.deepEqual(Object.keys(chunks),['IHDR','PLTE','IDAT','IEND']);
assert.deepEqual([...chunks.IHDR],[0,0,1,64,0,0,0,128,8,3,0,0,0],'320 x 128, 8-bit, palette color type');
assert.deepEqual([...chunks.PLTE],palette.flat(),'the PNG palette is the 16 battle colors in game order');
const raw=zlib.inflateSync(chunks.IDAT);
assert.equal(raw.length,(width+1)*height);
const back=new Uint8Array(width*height);
for(let row=0;row<height;row++){assert.equal(raw[row*(width+1)],0);back.set(raw.subarray(row*(width+1)+1,(row+1)*(width+1)),row*width);}
assert.deepEqual(back,pixels,'pixel values are the palette indices');
assert.throws(()=>indexedPng(pixels.subarray(1),width,height,palette));

// An exported picture comes back unchanged.
const rgba=new Uint8Array(pixels.length*4);
pixels.forEach((index,i)=>rgba.set([...palette[index],255],i*4));
let result=matchPalette(rgba,palette);
assert.deepEqual(result.pixels,pixels);
assert.equal(result.colors,16);assert.equal(result.changed.length,0);assert.equal(result.transparent,0);
assert.match(matchSummary(result),/All 16 of its colors are battle colors, so nothing was changed\./);
assert.deepEqual(matchRows(result),[]);

// Other ways of writing the same console level (0x24 steps, 0x20 steps) are the same color.
result=matchPalette(Uint8Array.of(0,0,32,255, 252,252,252,255, 144,144,252,255, 176,176,176,255),palette);
assert.deepEqual([...result.pixels],[0,1,14,5]);assert.equal(result.changed.length,0);

// Colors the battle palette does not have are reported, largest first, and still land on the nearest color.
result=matchPalette(Uint8Array.of(0,160,0,255, 0,160,0,255, 255,0,255,255, 0,0,36,255, 9,9,9,0),palette);
assert.deepEqual([...result.pixels],[6,6,4,0,0]);
assert.equal(result.colors,3);assert.equal(result.changedPixels,3);assert.equal(result.transparent,1);
assert.deepEqual(matchRows(result),[{from:'#00A000',to:'#484848',index:6,pixels:2},{from:'#FF00FF',to:'#FF9191',index:4,pixels:1}]);
assert.equal(matchSummary(result),'PNG imported, but 2 colors of 3 are not in the battle palette. 3 pixels were changed to the nearest battle color. Undo paint takes the import back. 1 see-through pixel became color 0.');
assert.equal(matchRows(result,1).length,1);
console.log('Battle background PNGs export with the battle palette and imports report every color that is not a battle color.');
