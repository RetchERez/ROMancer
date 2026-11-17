// Pure helpers for the Scenes & colors screen: what a system can show, which
// palette color a clicked pixel is, and the plain-language lines around a change.
export const plural=(count,word,many=word+'s')=>`${count} ${count===1?word:many}`;
export const hex=rgb=>'#'+rgb.map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('');
export function parseHex(text){const match=/^#?([0-9a-f]{6})$/i.exec(String(text||''));if(!match)return null;const value=parseInt(match[1],16);return [value>>16&255,value>>8&255,value&255];}
const distance=(a,b)=>(a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2;

// The nearest step a channel can take, as an index into the system's levels.
export function levelIndex(value,levels){let best=0;for(let i=1;i<levels.length;i++)if(Math.abs(levels[i]-value)<Math.abs(levels[best]-value))best=i;return best;}

// Snap one color to what the picker's system can represent.
export function snapColor(rgb,picker){
 if(picker.kind==='levels')return rgb.map(value=>picker.levels[levelIndex(value,picker.levels)]);
 const hidden=new Set(picker.hidden||[]);let best=-1;
 picker.colors.forEach((color,index)=>{if(!hidden.has(index)&&(best<0||distance(color,rgb)<distance(picker.colors[best],rgb)))best=index;});
 return [...picker.colors[best]];
}
export function pickerSummary(colors,picker){
 if(picker.kind==='levels'){const top=picker.levels.length-1,[r,g,b]=colors[0].map(v=>levelIndex(v,picker.levels));return `Red ${r}, green ${g}, blue ${b} (each 0 to ${top})`;}
 if(picker.kind==='master'){const index=picker.colors.findIndex(c=>distance(c,colors[0])===0);return index<0?'A color outside the NES set':`NES color ${index+1} of ${picker.colors.length}`;}
 const names=['white','light gray','dark gray','black'];
 return colors.map((color,slot)=>`slot ${slot+1}: ${names[Math.max(0,picker.colors.findIndex(c=>distance(c,color)===0))]}`).join(', ');
}

// Which palette entries show the color under a clicked pixel. Engines round
// colors slightly on the way to the screen, so near matches count.
export function swatchesForPixel(rgb,swatches,tolerance=1500){
 const found=[];
 for(const swatch of swatches)swatch.colors.forEach((color,slot)=>{const d=distance(color,rgb);if(d<=tolerance)found.push({swatch,slot,distance:d});});
 if(!found.length)return [];
 const best=Math.min(...found.map(f=>f.distance));
 return found.filter(f=>f.distance<=best+48).sort((a,b)=>a.distance-b.distance||Number(b.swatch.editable)-Number(a.swatch.editable));
}
export function groupSwatches(swatches){const groups=[];for(const swatch of swatches){let group=groups.at(-1);if(!group||group.name!==swatch.group){group={name:swatch.group,items:[]};groups.push(group);}group.items.push(swatch);}return groups;}
export const sameColors=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function swatchLabel(swatch){
 const state=swatch.editable?(swatch.pending?'changed, not saved yet':'can be changed'):'locked: '+swatch.locked_reason;
 return `${swatch.name}, ${swatch.colors.map(hex).join(' ')}, ${state}${swatch.editable&&swatch.uses?', used in '+plural(swatch.uses,'scene'):''}`;
}
export function changeLine(change){
 if(change.planning)return change.scope==='only_this'||!change.verdict?'Working out how to change only this scene…':change.verdict;
 if(change.error)return change.error;
 if(change.working)return `Re-rendering ${plural(change.working,'scene')} in the real game…`;
 return `${change.badge}. ${plural(change.visible_count,'scene')} ${change.visible_count===1?'looks':'look'} different.`;
}
export const KEY_BUTTONS={ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right',z:'a',x:'b',a:'x',s:'y',q:'l',w:'r',Enter:'start',Shift:'select'};
export const offsetText=value=>'0x'+Number(value).toString(16).toUpperCase().padStart(6,'0');
