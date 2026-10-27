import {esc,button,select} from './common.js';
import {selectionKey} from './tool_inputs.js';

export async function draftScene(ctx,doc,getSnapshot){
 if(!doc?.ok||!ctx.state.artifact)return '';
 const {state}=ctx,scope=selectionKey(state),params={...ctx.sourceParams()},current=()=>scope===selectionKey(state)&&ctx.isCurrentRender?.()!==false&&state.results['assets.inspect']?.document_id===doc.document_id;
 const traces=state.artifact.gameplay_traces?.source_sha256===state.artifact.sha256?state.artifact.gameplay_traces.ids||[]:[];
 const trace=ctx.draft('asset-scene-trace',traces.at(-1)||''),capture=traces.includes(trace)?trace:'';
 let snapshot;try{snapshot=JSON.parse(JSON.stringify(getSnapshot()));}catch(error){return '<section class="card"><h3>Captured-scene preview</h3><p class="error">'+esc(error.message)+'. Correct the graphics setup or draft first.</p></section>';}
 const signature=JSON.stringify({capture,...snapshot}),changed=Array.isArray(snapshot.edits?.changes)&&snapshot.edits.changes.length>0;
 let entry=state.assetScene?.scope===scope&&state.assetScene.signature===signature?state.assetScene:null;
 const stillMatches=()=>current()&&ctx.draft('asset-scene-trace',traces.at(-1)||'')===capture&&JSON.stringify({capture,...getSnapshot()})===signature;
 if(!entry&&capture&&changed&&doc.write_supported){
  try{
   const restored=await ctx.api.call('assets.preview_scene.find',{...params,trace_id:capture,...snapshot});if(!stillMatches())return '';
   entry=state.assetScene={scope,signature,result:restored.found?restored:null,reason:restored.reason||''};
  }catch(error){if(!current())return '';entry=state.assetScene={scope,signature,result:null,reason:error.message};}
 }
 if(!current())return '';
 const restoreReview=result=>{state.pending={kind:'assets',plan_id:result.plan_id,artifact_id:state.artifact.artifact_id,document_id:doc.document_id,signature:JSON.stringify(snapshot)};};
 if(entry?.result?.source_sha256===state.artifact.sha256&&entry.result.artifact_id===state.artifact.artifact_id)restoreReview(entry.result);
 ctx.use({'asset-scene-preview':async()=>{
  if(!stillMatches())throw Error('The selected ROM or graphics draft changed. Refresh the preview controls.');
  if(!capture||!changed||!doc.write_supported)throw Error('Stage an editable change and choose a fresh captured scene first.');
  const plan=await ctx.run('assets.plan',{...params,...snapshot},{render:false,refresh:false});
  if(!stillMatches())return;
  if(!plan.workbench_plan_id)throw Error('Review the current editable graphics plan first.');
  restoreReview({plan_id:plan.workbench_plan_id});
  const result=await ctx.run('assets.preview_scene',{...params,plan_id:plan.workbench_plan_id,trace_id:capture},{render:false});
  if(!stillMatches())return;
  state.assetScene={scope,signature,result};return ctx.render();
 }});
 const r=entry?.result,valid=r&&r.source_sha256===state.artifact.sha256&&r.artifact_id===state.artifact.artifact_id;
 const reason=!capture?'Load this ROM from a cold start in Playtest, then save a capture first.':!changed?'Stage a palette or pixel change first.':!doc.write_supported?'This layout is read-only.':'';
 const pictures=valid&&r.emulated_frame&&r.visual?'<div class="draft-scene-result"><p class="preview-caption" role="status">Emulated draft preview · '+r.changed_pixels+' pixel'+(r.changed_pixels===1?'':'s')+' changed</p><div class="draft-scene-pictures">'+[['Original replay','original_png_base64'],['Draft replay','build_png_base64'],['Difference','difference_png_base64']].map(([name,key])=>'<figure><figcaption>'+name+'</figcaption><img src="data:image/png;base64,'+esc(r.visual[key])+'" alt="'+name+' of the captured scene"></figure>').join('')+'</div><p class="subtle">No project build was created. These frames were produced by the emulator using temporary checked copies. They cover the captured route; build and test the edit to keep it.</p></div>':valid?'<p class="notice">'+esc(r.reason||'The captured scene could not be reproduced. Record a new cold-start capture.')+'</p>':'';
 return '<details class="card draft-scene" id="asset-scene-panel" '+(valid?'open':'')+'><summary>Preview this draft in a captured scene</summary><p>Replay the original twice and a temporary draft once. Palette changes are rendered by the emulator.</p>'+(traces.length?select('asset-scene-trace','Captured scene',traces.map((id,i)=>[id,'Capture '+(i+1)]),capture):'')+'<div class="actions">'+button('Preview captured scene','asset-scene-preview',{disabled:!!reason,reason,primary:true})+button('Open Playtest','navigate',{id:'playtest'})+'</div><p class="subtle">Up to 2,400 frames and 20 input steps. Your source, saved live session and project build history stay separate.</p><p id="asset-scene-notice" class="preview-caption" role="status">'+esc(reason||entry?.reason||'Previewing does not publish a build.')+'</p>'+pictures+'</details>';
}

export function invalidateDraftScene(){
 const panel=globalThis.document?.getElementById('asset-scene-panel'),result=panel?.querySelector('.draft-scene-result');
 if(result){result.hidden=true;const notice=globalThis.document.getElementById('asset-scene-notice');if(notice)notice.textContent='Draft changed. Update the captured-scene preview.';}
}
export function invalidateAssetSceneDraft(id){
 if(['paint-buffer','asset-changes','asset-schema'].includes(id))invalidateDraftScene();
}
export function mountDraftScene(ctx){
 if(!globalThis.document?.getElementById('asset-scene-panel'))return;
 const select=globalThis.document?.getElementById('asset-scene-trace'),scope=selectionKey(ctx.state);
 select?.addEventListener('change',()=>{if(scope!==selectionKey(ctx.state)||ctx.isCurrentRender?.()===false||globalThis.document.getElementById('asset-scene-trace')!==select)return;ctx.setDraft('asset-scene-trace',select.value);invalidateDraftScene();ctx.render();});
 for(const id of ['palette-picker','asset-schema','asset-changes'])globalThis.document?.getElementById(id)?.addEventListener('input',invalidateDraftScene);
 for(const id of ['palette-picker','asset-schema','asset-changes']){
  const node=globalThis.document?.getElementById(id);
  node?.addEventListener('change',()=>queueMicrotask(()=>{if(scope===selectionKey(ctx.state)&&ctx.isCurrentRender?.()!==false&&globalThis.document.getElementById(id)===node)ctx.render();}));
 }
 for(const id of ['paint-canvas','sprite-canvas']){const node=globalThis.document?.getElementById(id);node?.addEventListener('pointerdown',invalidateDraftScene);node?.addEventListener('keydown',e=>{if(e.key===' ')invalidateDraftScene();});}
}
