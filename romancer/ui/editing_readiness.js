import {esc,button} from './common.js';
import {selectionKey} from './tool_inputs.js';
const labels={ready:'Ready to edit',needs_investigation:'Needs investigation',unsupported:'Setup needs fixing'};
const missing={assets:['Play this ROM, pause, then inspect a sprite to find its graphics.','Find graphics'],script:['Text needs a character table and text locations before it can be edited.','Check text setup'],tables:['Find a changing value, then save its table layout.','Find values'],levels:['Level editing needs a saved map layout, tiles and object records.','Check level setup'],sound:['Preview supported samples, or capture audio from Playtest. Editing music needs a supported format.','Open sound tools']};
export function readinessCards(model){
 return '<section class="card editing-readiness"><h3>What can I edit in this ROM?</h3><div class="readiness-grid">'+model.areas.map(a=>{const suggestion=missing[a.kind]||['Find and save an editing setup for this ROM.','Investigate'],summary=a.status==='ready'?'A working editing setup is saved for this ROM.':a.status==='unsupported'?'The saved setup does not work with this ROM. Open it to check the details.':suggestion[0],action=a.status==='ready'?'Open editor':a.status==='unsupported'?'Check setup':suggestion[1];return '<div><strong>'+esc(a.title)+'</strong><p class="readiness-state '+esc(a.status)+'">'+esc(labels[a.status])+'</p><p>'+esc(summary)+'</p>'+button(action,'readiness-open',{id:a.kind})+'<details class="readiness-details"><summary>Technical details</summary><p>'+esc(a.reason)+'</p></details></div>';}).join('')+'</div><p class="subtle">Ready applies to the saved layout, not every part of the game. Playtest your changes.</p></section>';
}
export async function editingReadiness(ctx){
 const scope=selectionKey(ctx.state),current=()=>scope===selectionKey(ctx.state)&&ctx.isCurrentRender?.()!==false;
 const model=await ctx.api.call('editing.readiness',ctx.sourceParams());if(!current())return '';
 ctx.use({'readiness-open':node=>{if(!current())throw Error('The selected ROM changed.');const area=model.areas.find(a=>a.kind===node.dataset.id);if(!area)throw Error('Refresh editing readiness.');if(area.status==='ready'||area.status==='unsupported'){ctx.state.researchOpen={scope,kind:area.kind};return ctx.navigate(area.page);}if(area.kind==='assets')return ctx.navigate('playtest');if(area.kind==='tables')return ctx.navigate('debug');ctx.state.researchOpen={scope,kind:area.kind};return ctx.navigate(area.page);}});
 return readinessCards(model);
}
