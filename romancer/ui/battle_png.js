// Exact PNG exchange for the battle background: export keeps the 16 battle
// colors as the picture's own palette, import says which colors were not
// battle colors instead of changing them silently.
const crcTable=Uint32Array.from({length:256},(_,n)=>{for(let k=0;k<8;k++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
function crc32(bytes){let crc=0xffffffff;for(const byte of bytes)crc=crcTable[(crc^byte)&255]^(crc>>>8);return (crc^0xffffffff)>>>0;}
function adler32(bytes){let a=1,b=0;for(const byte of bytes){a=(a+byte)%65521;b=(b+a)%65521;}return ((b<<16)|a)>>>0;}
function chunk(type,data){
 const out=new Uint8Array(12+data.length),view=new DataView(out.buffer);
 view.setUint32(0,data.length);
 for(let i=0;i<4;i++)out[4+i]=type.charCodeAt(i);
 out.set(data,8);
 view.setUint32(8+data.length,crc32(out.subarray(4,8+data.length)));
 return out;
}
function stored(raw){
 const blocks=Math.max(1,Math.ceil(raw.length/65535)),out=new Uint8Array(2+raw.length+blocks*5+4),view=new DataView(out.buffer);
 out[0]=0x78;out[1]=0x01;
 let at=2;
 for(let block=0;block<blocks;block++){
  const part=raw.subarray(block*65535,(block+1)*65535);
  out[at]=block===blocks-1?1:0;
  view.setUint16(at+1,part.length,true);view.setUint16(at+3,~part.length&0xffff,true);
  out.set(part,at+5);at+=5+part.length;
 }
 view.setUint32(at,adler32(raw));
 return out;
}

// A palette PNG (color type 3): pixel values are palette indices, so an
// image editor opens it with exactly the game's colors and nothing else.
export function indexedPng(pixels,width,height,palette){
 if(pixels.length!==width*height)throw Error('The picture does not match its size.');
 const header=new Uint8Array(13),view=new DataView(header.buffer);
 view.setUint32(0,width);view.setUint32(4,height);header[8]=8;header[9]=3;
 const colors=Uint8Array.from(palette.flatMap(([r,g,b])=>[r,g,b]));
 const raw=new Uint8Array((width+1)*height);
 for(let row=0;row<height;row++)raw.set(pixels.subarray(row*width,(row+1)*width),row*(width+1)+1);
 const parts=[Uint8Array.of(0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a),chunk('IHDR',header),chunk('PLTE',colors),chunk('IDAT',stored(raw)),chunk('IEND',new Uint8Array(0))];
 const out=new Uint8Array(parts.reduce((size,part)=>size+part.length,0));
 let at=0;
 for(const part of parts){out.set(part,at);at+=part.length;}
 return out;
}

// The console shows 8 levels per channel, about 36 apart. A color within half
// a level of a battle color on every channel is that color; anything further
// away is a different color and is reported.
export const sameColorTolerance=18;

export function matchPalette(rgba,palette){
 const count=rgba.length>>2,pixels=new Uint8Array(count),seen=new Map();
 let transparent=0;
 for(let i=0;i<count;i++){
  if(rgba[i*4+3]<128){transparent++;continue;}
  const r=rgba[i*4],g=rgba[i*4+1],b=rgba[i*4+2],key=r<<16|g<<8|b;
  let entry=seen.get(key);
  if(!entry){
   let best=Infinity,index=0;
   palette.forEach(([pr,pg,pb],candidate)=>{
    const distance=(r-pr)**2+(g-pg)**2+(b-pb)**2;
    if(distance<best){best=distance;index=candidate;}
   });
   const [pr,pg,pb]=palette[index];
   const same=Math.max(Math.abs(r-pr),Math.abs(g-pg),Math.abs(b-pb))<=sameColorTolerance;
   entry={from:[r,g,b],index,to:palette[index],same,pixels:0};
   seen.set(key,entry);
  }
  entry.pixels++;
  pixels[i]=entry.index;
 }
 const all=[...seen.values()],changed=all.filter(entry=>!entry.same).sort((a,b)=>b.pixels-a.pixels);
 return {
  pixels,transparent,colors:all.length,
  changed,changedPixels:changed.reduce((sum,entry)=>sum+entry.pixels,0),
 };
}

const hex=([r,g,b])=>'#'+[r,g,b].map(value=>value.toString(16).padStart(2,'0')).join('').toUpperCase();
const plural=(n,word)=>`${n.toLocaleString('en-US')} ${word}${n===1?'':'s'}`;

export function matchSummary(result){
 const notes=[];
 if(!result.colors)notes.push('PNG imported. It has no solid pixels.');
 else if(!result.changed.length)notes.push(`PNG imported. ${result.colors===1?'Its one color is a battle color':`All ${result.colors} of its colors are battle colors`}, so nothing was changed.`);
 else notes.push(`PNG imported, but ${plural(result.changed.length,'color')} of ${result.colors} ${result.changed.length===1?'is':'are'} not in the battle palette. ${plural(result.changedPixels,'pixel')} ${result.changedPixels===1?'was':'were'} changed to the nearest battle color. Undo paint takes the import back.`);
 if(result.transparent)notes.push(`${plural(result.transparent,'see-through pixel')} became color 0.`);
 return notes.join(' ');
}

export function matchRows(result,limit=12){
 return result.changed.slice(0,limit).map(entry=>({from:hex(entry.from),to:hex(entry.to),index:entry.index,pixels:entry.pixels}));
}
