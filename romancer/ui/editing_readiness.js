import {esc,button} from './common.js';
import {selectionKey} from './tool_inputs.js';
const labels={ready:'Ready to edit',needs_investigation:'Needs investigation',unsupported:'Setup needs fixing'};
const missing={assets:['Play this ROM, pause, then inspect a sprite to find its graphics.','Find graphics'],script:['Text needs a character table and text locations before it can be edited.','Check text setup'],tables:['Find a changing value, then save its table layout.','Find values'],levels:['Level editing needs a saved map layout, tiles and object records.','Check level setup'],sound:['Preview supported samples, or capture audio from Playtest. Editing music needs a supported format.','Open sound tools']};
const editLabels={assets:'Edit graphics',script:'Edit text',tables:'Edit stats',sound:'Edit sound'};
export function readinessCards(model,{firstPracticeEdit=false}={}){
 const cards=model.areas.map(area=>{
  const ready=area.status==='ready',broken=area.status==='unsupported';
  const [hint,next]=missing[area.kind]||['Find and save an editing setup for this ROM.','Investigate'];
  const first=firstPracticeEdit&&area.kind==='tables'&&ready;
  const action=ready?(editLabels[area.kind]||'Open editor'):broken?'Check setup':next;
  const message=first?'For a first edit, change Hero speed from 2 to 3.':ready?'':broken?'Check the details of the saved setup.':hint;
  return `<div><strong>${esc(area.title)}</strong><p class="readiness-state ${esc(area.status)}">${esc(labels[area.status])}</p>${message?'<p>'+esc(message)+'</p>':''}
   ${button(action,'readiness-open',{id:area.kind,primary:first})}
   <details class="readiness-details"><summary>Technical details</summary><p>${esc(area.reason)}</p></details></div>`;
 }).join('');
 return `<section class="card editing-readiness"><h3>What can I edit in this ROM?</h3><div class="readiness-grid">${cards}</div><p class="subtle">Playtest changes to any checked layout.</p></section>`;
}
export async function editingReadiness(ctx){
 const scope=selectionKey(ctx.state),current=()=>scope===selectionKey(ctx.state)&&ctx.isCurrentRender?.()!==false;
 const model=await ctx.api.call('editing.readiness',ctx.sourceParams());if(!current())return '';
 ctx.use({'readiness-open':node=>{if(!current())throw Error('The selected ROM changed.');const area=model.areas.find(a=>a.kind===node.dataset.id);if(!area)throw Error('Refresh editing readiness.');if(area.status==='ready'||area.status==='unsupported'){ctx.state.researchOpen={scope,kind:area.kind};return ctx.navigate(area.page);}if(area.kind==='assets')return ctx.navigate('playtest');if(area.kind==='tables')return ctx.navigate('debug');ctx.state.researchOpen={scope,kind:area.kind};return ctx.navigate(area.page);}});
 const {project,artifact}=ctx.state;
 const firstPracticeEdit=project?.demo_type==='original-studio'&&project.builds?.length===0&&artifact?.kind==='source'&&artifact.descriptors?.tables?.definition?.name==='Scene controls';
 return readinessCards(model,{firstPracticeEdit});
}
