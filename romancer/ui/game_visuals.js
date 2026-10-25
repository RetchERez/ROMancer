import {esc} from './common.js';
import {numberComparison,textComparison,paletteComparison} from './edit_preview.js';
import {selectionKey} from './tool_inputs.js';

const palette=colors=>({entries:colors.map((c,index)=>({bank:0,index,rgb:{r:c[0],g:c[1],b:c[2]}}))});
export function gameVisual(model,chosen){
 if(model.visual?.palettes){const style=chosen.palette_style;
  return `<div class="live-game-preview"><h3>Color preview</h3>${model.visual.palettes.map((p,i)=>`<details ${i===0?'open':''}><summary>${esc(p.name)}</summary>${paletteComparison(palette(p.current),palette(['original','teal_magenta'].includes(style)?p[style]:p.current))}</details>`).join('')}<p class="preview-caption">Stored palette colors · playtest to see them in the game scene.</p></div>`;
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
