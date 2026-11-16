import {esc,button,badge} from './common.js';
import {discoveryControls} from './saved_discoveries.js';
import {selectionKey} from './tool_inputs.js';
const labels={ready:'Ready to edit',needs_investigation:'Needs investigation',unsupported:'Setup needs fixing'};
const missing={assets:['Play this ROM, pause, then inspect a sprite to find its graphics.','Find graphics'],script:['Text needs a character table and text locations before it can be edited.','Check text setup'],tables:['Find a changing value, then save its table layout.','Find values'],levels:['Level editing needs a saved map layout, tiles and object records.','Check level setup'],sound:['Preview supported samples, or capture audio from Playtest. Editing music needs a supported format.','Open sound tools']};
const editLabels={assets:'Edit graphics',script:'Edit text',tables:'Edit stats',sound:'Edit sound'};
function playtestResult(result){
 if(!result)return '';
 if(result.status!=='recorded'){
  const message=result.status==='report_unavailable'?'The bundled audit report could not be read.':'No audit result for these exact bytes.';
  return `<p class="subtle">${message} ${button('Open Playtest','navigate',{id:'playtest'})}</p>`;
 }
 const sampled=result.frames_sampled.at(-1);
 const confirmed=result.title_confirmed&&result.gameplay_confirmed;
 const title=confirmed?'Title and opening gameplay verified':result.first_varied_frame!==null?`Video observed by frame ${result.first_varied_frame}`:!result.loaded?'Game load did not complete':sampled?`No varied video in samples through frame ${sampled}`:'No startup frame captured';
 const input={changed_frame:'Test inputs changed the rendered result',no_frame_change:'No visible change from the test inputs',inconclusive:'Input comparison inconclusive',not_checked:'Input comparison unavailable'}[result.input];
 const state={matched:'Frame replay matched after restoring a state',different:'Frame replay differed after restoring a state',save_refused:'The core refused to save a state',load_refused:'The core refused to restore the state',not_checked:'State replay unavailable'}[result.state];
 const scope=confirmed?'The exact original reached its title and opening gameplay. Controller input was compared with idle.':'Automated startup sample. Open Playtest to confirm the title screen and test your changes.';
 return `<details class="card"><summary>Playtest audit ${badge(title,confirmed||result.first_varied_frame!==null?'good':'warm')}</summary><p>${esc(result.engine)} · Bundled Windows engine</p><ul><li>${input}</li><li>${state}</li></ul><p class="subtle">${scope}</p>${result.failure_stage?`<p class="subtle">Stopped during ${esc(result.failure_stage.replaceAll('_',' '))}.</p>`:''}${button('Open Playtest','navigate',{id:'playtest'})}</details>`;
}

function namedEdits(model){
 const named={};
 for(const edit of model?.fields||[]){
  const kind={integer:'tables',text:'script'}[edit.type]||(edit.id==='palette_style'?'assets':null);
  if(kind&&!named[kind])named[kind]={label:edit.label,id:edit.id,kind:'field'};
 }
 for(const resource of model?.resources||[]){
  if(!resource.legacy&&!named[resource.kind])named[resource.kind]={label:resource.name,id:resource.id,kind:'resource'};
 }
 return named;
}

export function readinessCards(model,{firstPracticeEdit=false,named={}}={}){
 const cards=model.areas.map(area=>{
  const ready=area.status==='ready',broken=area.status==='unsupported';
  const verified=named[area.kind];
  const [hint,next]=missing[area.kind]||['Find and save an editing setup for this ROM.','Investigate'];
  const first=firstPracticeEdit&&area.kind==='tables'&&ready;
  const action=ready?(editLabels[area.kind]||'Open editor'):broken?'Check setup':next;
  const message=first?'For a first edit, change Hero speed from 2 to 3.':ready||verified?'':broken?'Check the details of the saved setup.':hint;
  const status=verified?'ready':area.status;
  return `<div><strong>${esc(area.title)}</strong><p class="readiness-state ${esc(status)}">${verified?'Verified edit available':esc(labels[status])}</p>${message?'<p>'+esc(message)+'</p>':''}
   ${verified?button((verified.kind==='field'?'Edit ':'Open ')+verified.label,verified.kind==='field'?'game-focus':'game-resource',{id:verified.id}):''}
   ${!verified||ready||broken?button(action,'readiness-open',{id:area.kind,primary:first}):''}
   <details class="readiness-details"><summary>Technical details</summary><p>${esc(area.reason)}</p></details></div>`;
 }).join('');
 return `${playtestResult(model.playtest)}<section class="card editing-readiness"><h3>What can I edit in this ROM?</h3><div class="readiness-grid">${cards}</div></section>`;
}
export async function editingReadiness(ctx){
 const scope=selectionKey(ctx.state),current=()=>scope===selectionKey(ctx.state)&&ctx.isCurrentRender?.()!==false;
 const model=await ctx.api.call('editing.readiness',ctx.sourceParams());if(!current())return '';
 ctx.use({'readiness-open':node=>{if(!current())throw Error('The selected ROM changed.');const area=model.areas.find(a=>a.kind===node.dataset.id);if(!area)throw Error('Refresh editing readiness.');if(area.status==='ready'||area.status==='unsupported'){ctx.state.researchOpen={scope,kind:area.kind};return ctx.navigate(area.page);}if(area.kind==='assets')return ctx.navigate('playtest');if(area.kind==='tables')return ctx.navigate('debug');ctx.state.researchOpen={scope,kind:area.kind};return ctx.navigate(area.page);}});
 const {project,artifact}=ctx.state;
 const firstPracticeEdit=project?.demo_type==='original-studio'&&project.builds?.length===0&&artifact?.kind==='source'&&artifact.descriptors?.tables?.definition?.name==='Scene controls';
 const owned=ctx.state.gameVisualModel;
 return readinessCards(model,{firstPracticeEdit,named:namedEdits(owned?.scope===scope?owned.model:null)})+
  discoveryControls(ctx,model,scope,current);
}
