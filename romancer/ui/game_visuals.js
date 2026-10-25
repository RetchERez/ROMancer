import {esc} from './common.js';
import {numberComparison,textComparison,paletteComparison} from './edit_preview.js';
import {selectionKey} from './tool_inputs.js';

const palette=colors=>({entries:colors.map((c,index)=>({bank:0,index,rgb:{r:c[0],g:c[1],b:c[2]}}))});
export function gameVisual(model,chosen){
 if(model.visual?.kind==='map-point'){
  const v=model.visual,target=Object.hasOwn(v,chosen.room_layout)&&Array.isArray(v[chosen.room_layout])?v[chosen.room_layout]:v.current;
  const diagram=(point,label)=>`<svg viewBox="0 0 ${v.size[0]*16} ${v.size[1]*16}" role="img" aria-label="${label}" style="width:112px;height:128px;background:var(--panel);border:1px solid var(--line)">${Array.from({length:v.size[0]*v.size[1]},(_,i)=>`<rect x="${i%v.size[0]*16}" y="${Math.floor(i/v.size[0])*16}" width="16" height="16" fill="none" stroke="currentColor" opacity=".15"/>`).join('')}<rect x="${(point[0]-v.origin[0])*16+2}" y="${(point[1]-v.origin[1])*16+2}" width="12" height="12" rx="2" fill="var(--accent)"/></svg>`;
  return `<div class="live-game-preview"><h3>Stored map position</h3><p role="status">Stool: (${v.current.join(', ')}) → (${target.join(', ')})</p><div class="preview-pair"><div><span>Original</span>${diagram(v.current,'Original stool position')}</div><div><span>Edited</span>${diagram(target,'Edited stool position')}</div></div><p class="preview-caption">Declared coordinate preview · playtest the actual room.</p></div>`;
 }
 if(model.visual?.palettes){const style=chosen.palette_style;
  return `<div class="live-game-preview"><h3>Color preview</h3>${model.visual.palettes.map((p,i)=>`<details ${i===0?'open':''}><summary>${esc(p.name)}</summary>${paletteComparison(palette(p.current),palette(Object.hasOwn(p,style)&&Array.isArray(p[style])?p[style]:p.current))}</details>`).join('')}<p class="preview-caption">Stored palette colors · playtest to see them in the game scene.</p></div>`;
 }
 return model.fields.map(f=>`<div class="live-game-preview"><h3>${f.type==='integer'?'Stored values':'Text comparison'}</h3>${f.type==='integer'?numberComparison(f.value,chosen[f.id],{minimum:f.min,maximum:f.max}):textComparison(f.value,chosen[f.id]??f.value,{columns:32})}${f.type==='integer'?'<p class="preview-caption">Stored values only. The game may calculate the displayed result.</p>':''}</div>`).join('');
}
export function mountGameVisual(ctx){
 const owned=ctx.state.gameVisualModel,node=document.getElementById('game-visual-preview');if(!owned||!node)return;
 const current=()=>owned.scope===selectionKey(ctx.state)&&ctx.state.gameVisualModel===owned;
 const values=()=>Object.fromEntries(owned.model.fields.map(f=>[f.id,document.getElementById('game-'+f.id)?.value??f.value]));
 const draw=()=>{if(current())node.innerHTML=gameVisual(owned.model,values());};
 for(const f of owned.model.fields){const input=document.getElementById('game-'+f.id);if(!input)continue;const changed=()=>{if(!current())return;const reviewed=ctx.state.gameEditPlan;if(reviewed&&JSON.stringify(Object.fromEntries(owned.model.fields.map(f=>[f.id,f.type==='integer'?Number(values()[f.id]):values()[f.id]])))!==JSON.stringify(reviewed.values)){ctx.state.gameEditPlan=null;const review=document.getElementById('game-edit-review');if(review)review.hidden=true;}draw();};input.addEventListener('input',changed);input.addEventListener('change',changed);}
 draw();
}
