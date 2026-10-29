import {esc} from './common.js';
const bits={'mono-row-msb-v1':1,'tile8-paired2-msb-v1':2,'tile8-planar2-msb-v1':2,'tile8-rowplanar4-msb-v1':4,'tile8-paired4-msb-v1':4,'tile8-packed4-high-v1':4,'tile8-packed4-low-v1':4};
const valid=rgb=>Array.isArray(rgb)&&rgb.length===3&&rgb.every(v=>Number.isInteger(v)&&v>=0&&v<=255);
export function brushColors(bitmap,palette,layout,bank=0){
 const count=bits[bitmap?.codec]?Math.min(2**bits[bitmap.codec],palette?.colors_per_bank||256):0;
 return Array.from({length:count},(_,index)=>{
  const entry=palette?.entries.find(e=>e.bank===bank&&e.index===index),declared=entry&&[entry.rgb.r,entry.rgb.g,entry.rgb.b];
  if(valid(declared))return {index,rgb:declared,colors:[declared],origin:'declared'};
  const observed=[...new Map((layout?.colors||[]).map(part=>part?.[index]).filter(valid).map(rgb=>[rgb.join(','),rgb])).values()];
  if(observed.length)return {index,rgb:observed[0],colors:observed,origin:'observed'};
  const shade=Math.round(18+index/Math.max(1,count-1)*216),rgb=[shade,shade,shade];return {index,rgb,colors:[rgb],origin:'grayscale'};
 });
}
export function brushSwatches(colors,selected){
 const kinds=new Set(colors.map(c=>c.origin)),label=kinds.size===1&&kinds.has('declared')?'Declared palette colors':kinds.size===1&&kinds.has('grayscale')?'Grayscale preview · actual game palette unknown':kinds.has('grayscale')?'Declared/observed colors where available · grayscale for unknown entries':'Observed/declared preview colors';
 return `<div class="brush-swatches" role="group" aria-label="Sprite brush colors">${colors.map(color=>`<button type="button" data-action="sprite-brush" data-id="${color.index}" data-brush-index="${color.index}" aria-pressed="${color.index===Number(selected)}" aria-label="Color index ${color.index} · ${color.origin}${color.colors.length>1?' · varies across sprite parts':''}"><svg viewBox="0 0 32 24" width="32" height="24" aria-hidden="true">${color.colors.slice(0,8).map((rgb,i,rows)=>`<rect x="${i*32/rows.length}" width="${32/rows.length}" height="24" fill="rgb(${rgb.join(',')})"/>`).join('')}</svg><span>${color.index}</span></button>`).join('')}</div><p class="subtle brush-color-source">${esc(label)}</p>`;
}
