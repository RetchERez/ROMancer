import {esc,button} from './common.js';
import {selectionKey} from './tool_inputs.js';
const labels={ready:'Ready to edit',needs_investigation:'Needs investigation',unsupported:'Unsupported definition'};
export function readinessCards(model){
 return '<section class="card editing-readiness"><h3>This ROM: editing readiness</h3><div class="readiness-grid">'+model.areas.map(a=>'<div><strong>'+esc(a.title)+'</strong><p class="readiness-state '+esc(a.status)+'">'+esc(labels[a.status])+'</p><p>'+esc(a.reason)+'</p>'+button(a.action,'readiness-open',{id:a.kind})+'</div>').join('')+'</div><p class="subtle">Ready means the saved layout passed inspection for this revision. Names and game behavior still need evidence.</p></section>';
}
export async function editingReadiness(ctx){
 const scope=selectionKey(ctx.state),current=()=>scope===selectionKey(ctx.state)&&ctx.isCurrentRender?.()!==false;
 const model=await ctx.api.call('editing.readiness',ctx.sourceParams());if(!current())return '';
 ctx.use({'readiness-open':node=>{if(!current())throw Error('The selected ROM changed.');const area=model.areas.find(a=>a.kind===node.dataset.id);if(!area)throw Error('Refresh editing readiness.');if(area.status==='ready'||area.status==='unsupported'){ctx.state.researchOpen={scope,kind:area.kind};return ctx.navigate(area.page);}return ctx.navigate(area.kind==='assets'?'playtest':'debug');}});
 return readinessCards(model);
}
