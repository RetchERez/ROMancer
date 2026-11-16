import {badge,button,esc,read,select} from './common.js';
import {checkReport} from './build_checks.js';
import {fileInput,readJsonFile,selectionKey} from './tool_inputs.js';

export function replayRelease(ctx){
 const {state}=ctx,params=ctx.projectParams(),scope=selectionKey(state),current=()=>scope===selectionKey(state);
 const checks=state.project.builds.flatMap(build=>(build.build_check_results||[])
   .filter(result=>result.replay_verified&&result.target_id===build.artifact_id)
   .map(result=>({...result,build}))).slice(-32).reverse();
 const recent=state.results['release.replay'];
 const created=state.results['release.proof']?.export;
 ctx.use({
  'release-proof':async()=>{
   if(!current())throw Error('The selection changed. Reopen Export.');
   const id=read('release-proof-check');
   const check=checks.find(row=>row.evidence_id===id);
   if(!check||check.target_id!==read('release-target'))throw Error('Choose the build tested by this replay in the Edited build menu above.');
   return ctx.run('release.proof',{...params,source_id:read('release-source'),target_id:check.target_id,
      evidence_id:check.evidence_id,title:read('release-title'),description:read('release-description'),
      screenshots:!!document.getElementById('release-proof-images')?.checked});
  },
  'release-replay':async()=>{
   if(!current())throw Error('The selection changed. Reopen Export.');
   const source_id=read('release-source'),target_id=read('release-target');
   if(!source_id||!target_id)throw Error('Select the exact original and patched build above.');
   const patch=document.getElementById('release-replay-patch')?.files?.[0];
   if(!patch||!patch.name.toLowerCase().endsWith('.bps'))throw Error('Choose the BPS from the proof package.');
   const proof=await readJsonFile('release-replay-file',32*1024);
   if(!current())return;
   const input=await ctx.api.uploadInput(params.project_id,patch,'patch');
   if(!current()||source_id!==read('release-source')||target_id!==read('release-target'))return;
   return ctx.run('release.replay',{...params,source_id,target_id,input_id:input.input_id,proof});
  }
 });
 const preferred=checks.find(row=>row.target_id===ctx.draft('release-target',''))||checks[0];
 return '<div class="grid-two"><details class="card" '+(created?'open':'')+'><summary>Share a patch with replay proof</summary>'+
  '<p>Choose a completed replay from Check my hack. The ZIP includes the verified BPS, instructions and a replay file.</p>'+
  (checks.length?select('release-proof-check','Completed replay',checks.map(row=>[row.evidence_id,(row.build.name||'Build')+' · '+row.evidence_id.slice(0,8)]),ctx.draft('release-proof-check',preferred.evidence_id)):'<p>No completed cold-start replay to share yet.</p>')+
  '<label><input type="checkbox" id="release-proof-images"> Include original, build and difference screenshots</label>'+
  '<div class="actions">'+button('Create replay proof ZIP','release-proof',{primary:true,disabled:!checks.length})+
  (created?button('Download ZIP','download',{id:created.export_id,name:created.download_name,icon:'download'}):'')+'</div></details>'+
  '<details class="card" '+(recent?'open':'')+'><summary>Verify a shared replay</summary><p>Extract the ZIP, apply the BPS to your exact original, then select the original and patched build above.</p>'+
  fileInput('release-replay-patch','Patch.bps','.bps')+fileInput('release-replay-file','Replay.json','.json,application/json')+
  button('Run shared replay','release-replay',{primary:true,disabled:!state.project.builds.length})+
  (recent?.status?'<p role="status">'+badge(recent.replay_verified?'Replay reproduced':recent.status,recent.replay_verified?'good':'warm')+'</p>'+
   (recent.ok?checkReport(recent):'<p class="error">'+esc(recent.error||'Verification could not run.')+'</p>'):'')+'</details></div>';
}
