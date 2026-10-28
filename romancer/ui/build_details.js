import {esc} from './common.js';
import {selectionKey} from './tool_inputs.js';
import {summaryText} from './change_summary.js';
const actions=new Set(['growth-build','cq-build','command-build','asset-apply','script-apply','translation-apply','table-build','levels-build','sound-build','bytes-apply','hex-apply','game-apply','maps-build','reloc-build','compression-build','recipe-build']);
const pendingKinds={'growth-build':'text-growth','cq-build':'command-rewrite','command-build':'commands','asset-apply':'assets','script-apply':'script','table-build':'table','levels-build':'levels','sound-build':'sound','bytes-apply':'bytes','reloc-build':'relocation','compression-build':'compression','recipe-build':'recipe'};
export function planForBuildAction(state,action){
 if(action==='hex-apply'){
  const row=state.hexReview;
  return row?.scope===selectionKey(state)&&state.hexDraft&&row.signature===JSON.stringify(state.hexDraft.edits(state))?row.plan:null;
 }
 if(action==='game-apply')return state.gameEditPlan?.scope===selectionKey(state)?state.gameEditPlan.result:null;
 const kind=pendingKinds[action],pending=state.pending;
 if(!kind||pending?.kind!==kind||pending.artifact_id!==state.artifact?.artifact_id||pending.project_id&&pending.project_id!==state.project?.project_id)return null;
 return [...Object.values(state.results||{}),pending.report].find(row=>row&&(row.workbench_plan_id||row.plan_id)===pending.plan_id)||null;
}
export function mountBuildDetails(ctx,root=document.getElementById('main')){
 const target=[...root.querySelectorAll('[data-action]')].find(node=>actions.has(node.dataset.action)&&!node.disabled&&!node.textContent.includes('Open existing build'));
 if(!target||root.querySelector('#next-build-name'))return;
 const panel=document.createElement('details');panel.className='build-details';panel.innerHTML=`<summary>Name and notes for this build (optional)</summary><label class="field"><span>Build name</span><input id="next-build-name" maxlength="120" value="${esc(ctx.draft('next-build-name',''))}" placeholder="Keep the automatic name"></label><label class="field"><span>Build notes</span><textarea id="next-build-notes" maxlength="2000" rows="2">${esc(ctx.draft('next-build-notes',''))}</textarea></label>`;
 (target.closest('.actions')||target).before(panel);
 const text=summaryText(planForBuildAction(ctx.state,target.dataset.action));
 if(text){const note=document.createElement('p');note.className='notice build-change-summary';note.setAttribute('role','status');note.textContent=text;panel.before(note);}
}
export async function runNamedBuild(ctx,operation,parameters,options,runner){
 if(!['build.apply','structured.apply'].includes(operation))return runner(operation,parameters,options);
 const name=ctx.draft('next-build-name','').trim(),notes=ctx.draft('next-build-notes','').replace(/\r\n/g,'\n'),scope=selectionKey(ctx.state),project=ctx.state.project?.project_id;
 if(name.length>120||notes.length>2000)throw Error('Use up to 120 characters for the build name and 2000 for notes.');
 if(/[\x00-\x1f\x7f-\x9f]/.test(name)||/[\x00-\x09\x0b-\x1f\x7f-\x9f]/.test(notes))throw Error('Remove control characters from the build name or notes.');
 if(!name&&!notes)return runner(operation,parameters,options);
 const current=()=>scope===selectionKey(ctx.state),changed=()=>Error('Build completed for the previous selection. Open that file to review it.');
 let result=await runner(operation,parameters,{...options,render:false});if(!current())throw changed();
 if(result?.kind==='build'&&result.artifact_id){
  try{await ctx.api.call('builds.annotate',{project_id:project,artifact_id:result.artifact_id,name:name||result.name,notes});}
  catch(error){if(!current())throw changed();ctx.notify('Build created, but its name/notes were not saved. Use Build history to retry. '+error.message,true);result={...result,metadata_warning:true};}
  if(!current())throw changed();
  await ctx.refreshProject();if(!current())throw changed();
  const row=ctx.state.project.builds.find(r=>r.artifact_id===result.artifact_id);if(row)result={...result,name:row.name};
  if(!result.metadata_warning){if(ctx.draft('next-build-name','').trim()===name)ctx.setDraft('next-build-name','');if(ctx.draft('next-build-notes','')===notes)ctx.setDraft('next-build-notes','');}
  ctx.state.results??={};ctx.state.results[operation]=result;
 }
 if(options.render!==false)await ctx.render();return result;
}
