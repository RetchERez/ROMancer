import {esc} from './common.js';

export function numberDelta(before,after){
 if(typeof after==='string'&&!after.trim())throw Error('Enter a whole number.');
 const next=typeof after==='string'?Number(after):after;
 if(!Number.isSafeInteger(before)||!Number.isSafeInteger(next))throw Error('Enter a whole number.');
 return {before,after:next,delta:next-before,percent:before===0?null:(next-before)/Math.abs(before)*100};
}
const signed=value=>(value>0?'+':'')+value;
export function numericBounds(type){const match=/^([us])(8|16|24|32)$/.exec(type);if(!match)return {minimum:-Infinity,maximum:Infinity};const bits=Number(match[2]),signed=match[1]==='s';return {minimum:signed?-(2**(bits-1)):0,maximum:2**(bits-Number(signed))-1};}
export function numberComparison(before,after,{minimum=-Infinity,maximum=Infinity,compact=false}={}){
 let d;try{d=numberDelta(before,after);}catch(error){return `<p class="error" role="status">${esc(error.message)}</p>`;}
 if(compact&&d.before===d.after)return `<span class="preview-caption">Original ${d.before} · unchanged</span>`;
 const max=Math.max(1,Math.abs(d.before),Math.abs(d.after)),percent=d.percent===null?'from zero':signed(Number(d.percent.toFixed(1)))+'%';
 return `<div class="number-comparison ${compact?'compact':''}" aria-label="Stored value comparison"><div class="preview-pair">${[['Original',d.before],['Edited',d.after]].map(([name,value])=>`<div><span>${name}</span><strong>${value}</strong><meter class="value-track" min="0" max="${max}" value="${Math.abs(value)}" aria-label="${name} value magnitude"></meter></div>`).join('')}</div><p class="value-delta" role="status">${d.delta===0?'Unchanged':'Preview updated'} · ${signed(d.delta)} · ${percent}</p>${d.after<minimum||d.after>maximum?'<p class="error">Outside the declared numeric range.</p>':''}</div>`;
}
export function textComparison(before,after,{columns=32}={}){
 columns=Number.isSafeInteger(columns)?Math.max(8,Math.min(80,columns)):32;
 return `<div class="text-comparison"><p class="preview-caption">System-font preview · wraps at ${columns} characters</p><div class="preview-pair">${[['Original',before],['Edited',after]].map(([name,text])=>`<div><span>${name}</span><div class="text-window" style="--text-columns:${columns}ch">${esc(String(text).slice(0,8192))||'<span class="subtle">Empty</span>'}</div></div>`).join('')}</div><p class="preview-caption" role="status">${before===after?'Unchanged preview':'Preview updated'} · ${Array.from(String(after)).length} characters · game font and window require a declared layout or playtest</p></div>`;
}
export function textCapacity(record,texts,glyphs){
 if(!Array.isArray(glyphs)||!Number.isSafeInteger(record.used_bytes))return {known:false};
 if(texts.length!==record.segments.length||texts.some(t=>typeof t!=='string'||t.length>131072))return {known:false,error:'Preview unavailable: text exceeds the supported record limit.'};
 const allowed=new Set(glyphs),unmapped=new Set();let used=record.used_bytes-record.segments.reduce((n,s)=>n+s.length,0);
 for(const text of texts){let count=0;for(const char of text){if(++count>65536)return {known:false,error:'Preview unavailable: text exceeds 65,536 characters.'};used++;if(!allowed.has(char)&&unmapped.size<16)unmapped.add(char);}}
 return {known:true,used,capacity:record.capacity,overflow:Math.max(0,used-record.capacity),unmapped:[...unmapped].slice(0,16)};
}
export function capacitySummary(value){
 if(!value.known)return `<p class="${value.error?'error':'preview-caption'}" role="status">${esc(value.error||'Byte capacity is checked when you review the changes.')}</p>`;
 return `<div class="capacity-summary ${value.overflow||value.unmapped.length?'error':''}" role="status"><progress max="${value.capacity}" value="${Math.min(value.capacity,value.used)}"></progress><span>${value.used} / ${value.capacity} bytes${value.overflow?' · '+value.overflow+' bytes over capacity':value.unmapped.length?'':' · fits'}</span>${value.unmapped.length?`<span>Unmapped characters: ${value.unmapped.map(c=>esc(JSON.stringify(c))).join(', ')}</span>`:''}</div>`;
}
export function channelMaximum(mask){
 if(!Number.isSafeInteger(mask)||mask<1||mask>0xffffffff)throw Error('No valid declared color channel.');
 while(mask%2===0)mask/=2;
 if(!Number.isInteger(Math.log2(mask+1)))throw Error('Color channel mask must be contiguous.');
 return mask;
}
export function componentRGB(components,channels){
 return Object.fromEntries(['r','g','b'].map(c=>{const maximum=channelMaximum(channels[c]),value=components[c];if(!Number.isSafeInteger(value)||value<0||value>maximum)throw Error('Color is outside its declared storage range.');return [c,Math.round(value/maximum*255)];}));
}
export function quantizeColor(hex,channels){
 if(typeof hex!=='string'||!/^#[a-f0-9]{6}$/i.test(hex))throw Error('Choose a valid RGB color.');
 return Object.fromEntries(['r','g','b'].map((c,i)=>[c,Math.round(parseInt(hex.slice(1+i*2,3+i*2),16)/255*channelMaximum(channels[c]))]));
}
export function editedPalette(palette,changes){
 if(!palette)return palette;
 if(!Array.isArray(changes)||changes.length>4096)throw Error('Palette preview exceeds its change budget.');
 const selected=changes.filter(c=>c.kind==='palette'&&c.palette_id===palette.id),seen=new Set();
 const entries=palette.entries.map(entry=>{
  const matching=selected.filter(c=>c.index===entry.index&&c.bank===entry.bank);if(matching.length>1)throw Error('Duplicate palette changes need review.');
  const change=matching[0];if(!change)return {...entry};
  if(['r','g','b'].some(c=>change.before?.[c]!==entry.components[c]))throw Error('Palette preview belongs to different original colors.');
  seen.add(change);return {...entry,components:{...change.after},rgb:componentRGB(change.after,palette.channels)};
 });
 if(seen.size!==selected.length)throw Error('Palette entry is outside the declaration.');
 return {...palette,entries};
}
export function editorPalette(ctx,palette){
 try{return editedPalette(palette,JSON.parse(ctx.draft('asset-changes','[]')));}
 catch(error){const node=globalThis.document?.getElementById('palette-preview-status');if(node)node.textContent=error.message;return palette;}
}
export const rgbHex=rgb=>'#'+['r','g','b'].map(c=>rgb[c].toString(16).padStart(2,'0')).join('');
export function paletteComparison(original,edited){
 const chips=palette=>palette.entries.slice(0,256).map(e=>`<svg class="preview-swatch" viewBox="0 0 1 1" width="100%" role="img" aria-label="Bank ${e.bank}, color ${e.index}: RGB ${e.rgb.r},${e.rgb.g},${e.rgb.b}"><title>Bank ${e.bank}, color ${e.index}: RGB ${e.rgb.r},${e.rgb.g},${e.rgb.b}</title><rect width="1" height="1" fill="rgb(${e.rgb.r},${e.rgb.g},${e.rgb.b})"/></svg>`).join('');
 const changed=original.entries.filter((e,i)=>['r','g','b'].some(c=>e.rgb[c]!==edited.entries[i]?.rgb[c])).length;
 return `<div class="palette-comparison"><div class="preview-pair"><div><span>Original</span><div class="preview-swatches">${chips(original)}</div></div><div><span>Edited</span><div class="preview-swatches">${chips(edited)}</div></div></div><p class="preview-caption" role="status">${changed?'Preview updated':'Unchanged'} · ${changed} changed color${changed===1?'':'s'}${original.entries.length>256?' · first 256 shown':''}</p></div>`;
}

export function mountNumberPreviews(root=document){
 root.querySelectorAll?.('[data-number-input]').forEach(node=>{
  const input=document.getElementById(node.dataset.numberInput);if(!input)return;
  const draw=()=>{node.innerHTML=numberComparison(Number(node.dataset.before),input.value,{minimum:Number(node.dataset.minimum??-Infinity),maximum:Number(node.dataset.maximum??Infinity),compact:node.dataset.compact==='true'});};
  input.addEventListener('input',draw);input.addEventListener('change',draw);draw();
 });
}
export function mountTextPreviews(root=document){
 root.querySelectorAll?.('[data-text-input]').forEach(node=>{
  const input=document.getElementById(node.dataset.textInput);if(!input)return;
  const draw=()=>{node.innerHTML=textComparison(node.dataset.before,input.value,{columns:Number(node.dataset.columns||32)});};
  input.addEventListener('input',draw);input.addEventListener('change',draw);draw();
 });
}
