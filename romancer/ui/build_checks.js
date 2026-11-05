import {originalForBuild} from './build_handoff.js';
import {esc,button,field,select,read,area,badge} from './common.js';
import {selectionKey} from './tool_inputs.js';
const terminal=new Set(['COMPLETED','FAILED','CANCELLED','INTERRUPTED']);
export async function buildChecks(ctx){
 const {state}=ctx,a=state.artifact;if(!a)return '';
 const scope=selectionKey(state),params={...ctx.sourceParams()},current=()=>scope===selectionKey(state)&&ctx.isCurrentRender?.()!==false;
 const model=await ctx.api.call('checks.status',params);if(!current()||model.source_sha256!==a.sha256||model.artifact_id!==a.artifact_id)return '';
 state.buildCheckView={scope,page:state.page,pending:(model.pending||[]).some(j=>!terminal.has(j.status))};
 const original=a.kind==='build'?originalForBuild(state.project,a):null;
 const matches=report=>report?.project_id===params.project_id&&report.source_id===original?.artifact_id&&report.source_sha256===original?.sha256&&report.target_id===a.artifact_id&&report.target_sha256===a.sha256;
 const comparison=state.hackComparison;
 const diff=original&&comparison?.project_id===params.project_id&&comparison.left_id===original.artifact_id&&comparison.left_sha256===original.sha256&&comparison.right_id===a.artifact_id&&comparison.right_sha256===a.sha256?comparison:null;
 const cfg=model.config,artifacts=state.project.sources.concat(state.project.builds),target=ctx.draft('check-target',a.kind==='build'?a.artifact_id:state.project.builds.at(-1)?.artifact_id||a.artifact_id);
 const saved=state.buildCheckReport?.scope===scope?state.buildCheckReport.result:null;
 let packet=original?(matches(saved)?saved:null):saved;
 const results=original?model.results.filter(row=>row.target_id===a.artifact_id&&row.target_sha256===a.sha256):model.results;
 if(original&&!packet&&results.length){
  try{const latest=await ctx.api.call('checks.get',{...params,evidence_id:results.at(-1).evidence_id});if(matches(latest))packet=latest;}catch{/* A missing report can be replaced by a fresh check. */}
  if(!current())return '';
 }
 ctx.use({'hack-compare':async()=>{
  if(!current()||!original)return;
  const result=await ctx.run('builds.compare',{project_id:params.project_id,left_id:original.artifact_id,right_id:a.artifact_id},{render:false});
  if(current()){state.hackComparison=result;return ctx.render();}
 },'hack-byte':async node=>{
  const offset=Number(node.dataset.id);
  if(!current()||!diff?.ranges.some(range=>range.offset===offset))return;
  state.hexComparison={...diff,offset};state.resourceJump=offset;return ctx.navigate('resources');
 },'check-save':async()=>{if(!current())return;let steps;if(read('check-input-mode')==='custom')steps=JSON.parse(read('check-steps'));else{let remaining=Number(read('check-frames'));if(!Number.isSafeInteger(remaining)||remaining<1||remaining>2400)throw Error('Choose 1 to 2400 frames before capture.');steps=[];while(remaining){const count=Math.min(600,remaining);steps.push({frames:count,buttons:[],port:0});remaining-=count;}}const region=document.getElementById('check-region-enable')?.checked?Object.fromEntries(['x','y','width','height'].map(k=>[k,Number(read('check-region-'+k))])):null;const config={name:read('check-name').trim(),automatic:!!document.getElementById('check-auto')?.checked,mode:read('check-mode'),steps,region,route_ids:cfg.route_ids||[]};await ctx.run('checks.configure',{...params,artifact_id:original?.artifact_id||params.artifact_id,config},{render:false});if(current())return ctx.render();},
 'check-run':async()=>{if(!current())return;const target_id=original?a.artifact_id:read('check-target');const result=await ctx.run('checks.run',{project_id:params.project_id,source_id:original?.artifact_id||model.baseline_id,target_id},{render:false});if(!current())return;state.buildCheckReport={scope,result};return ctx.render();},
 'check-open':async node=>{if(!current()||!results.some(r=>r.evidence_id===node.dataset.id))throw Error('Refresh this source’s test results first.');const result=await ctx.api.call('checks.get',{...params,evidence_id:node.dataset.id});if(!current())return;state.buildCheckReport={scope,result};return ctx.render();},
 'check-refresh':async()=>{if(!current())return;await ctx.refreshProject();if(current())return ctx.render();},
 'check-cancel':node=>{if(!current()||!model.pending.some(j=>j.job_id===node.dataset.id))throw Error('Refresh the active checks first.');return ctx.api.call('jobs.cancel',{job_id:node.dataset.id});}});
 const named=a.plan_annotations?.kind==='reviewed-table-changes-v1'?a.plan_annotations.changes:[];
 const review=original?'<p><strong>'+esc(original.name)+'</strong> → <strong>'+esc(a.name)+'</strong></p>'+
  (named?.length?'<details open><summary>Named edits from this build</summary><ul>'+named.map(change=>'<li>'+esc(change.field)+' · row '+esc(change.row)+' · '+esc(change.before)+' → '+esc(change.after)+'</li>').join('')+'</ul></details>':'')+
  button('Compare original and build','hack-compare')+(diff?'<p>'+esc(diff.changed_bytes)+' changed '+(diff.changed_bytes===1?'byte':'bytes')+'</p><div class="actions">'+diff.ranges.slice(0,24).map(range=>button('0x'+range.offset.toString(16)+' · '+range.length+' bytes','hack-byte',{id:String(range.offset)})).join('')+'</div>'+(diff.ranges.length>24||diff.ranges_truncated?'<p class="subtle">Showing the first changed ranges.</p>':''):'')+
  (!packet?'<p>No saved gameplay check for this original and build. Run checks to capture matching checkpoints.</p>':''):'';
 return '<section class="card" id="build-checks"><div class="card-heading"><h3>'+(original?'Check my hack':'Build checks')+'</h3>'+badge(model.configured?'Configured':'Ready to configure')+'</div>'+review+'<p>Run the original twice and the build once with the same inputs. Compare pictures, cartridge checks and save-state replay.</p><div id="checks-progress">'+(model.pending||[]).map(j=>'<p>'+esc(j.status)+' · '+esc(artifacts.find(a=>a.artifact_id===j.target_id)?.name||'Build')+' '+(!terminal.has(j.status)?button('Cancel check','check-cancel',{id:j.job_id}):esc(j.outcome?.status||j.outcome?.error||''))+'</p>').join('')+'</div>'+
 '<div class="field-row">'+(original?'':select('check-target','Build to check',artifacts.map(r=>[r.artifact_id,r.name]),target))+button('Run checks','check-run',{primary:true})+button('Refresh results','check-refresh')+'</div>'+
 '<details><summary>Automatic check setup</summary>'+field('check-name','Test name',ctx.draft('check-name',cfg.name))+'<label><input id="check-auto" type="checkbox" '+(cfg.automatic?'checked':'')+'> Check new descendant builds automatically after saving this setup</label>'+select('check-mode','Picture comparison',[['review_changes','Show changes for review'],['unchanged','Require identical selected pixels']],ctx.draft('check-mode',cfg.mode))+
 field('check-frames','Frames before capture',ctx.draft('check-frames',String(cfg.steps.reduce((n,s)=>n+s.frames,0))),{type:'number',min:1,max:2400})+select('check-input-mode','Inputs',[['simple','Wait with no buttons'],['custom','Use custom input sequence below']],ctx.draft('check-input-mode',cfg.steps.some(s=>s.buttons.length)?'custom':'simple'))+
 '<details><summary>Advanced inputs and comparison region</summary>'+area('check-steps','Custom input steps (frames, buttons, port)',ctx.draft('check-steps',JSON.stringify(cfg.steps,null,2)),5)+'<label><input id="check-region-enable" type="checkbox" '+(cfg.region?'checked':'')+'> Compare a fixed part of the screen</label><div class="field-row">'+['x','y','width','height'].map(k=>field('check-region-'+k,k[0].toUpperCase()+k.slice(1),ctx.draft('check-region-'+k,String(cfg.region?.[k]??(k==='width'||k==='height'?128:0))),{type:'number',min:k==='x'||k==='y'?0:1})).join('')+'</div></details>'+button('Save test setup for this revision','check-save')+'<p class="subtle">Up to 2400 frames. Setup follows builds descended from this revision. A flat or unstable original is inconclusive; visual changes need review unless identical pixels are required. Record longer assertions in Routes.</p></details>'+
 (results.length?'<details open><summary>Recent results</summary><div class="actions">'+results.slice().reverse().map(r=>button(r.status+' · '+r.evidence_id.slice(0,8),'check-open',{id:r.evidence_id})).join('')+'</div></details>':'')+
 (packet?checkReport(packet):'')+'</section>';
}
export function checkReport(r){
 return '<section class="notice"><h4>'+esc(r.name||'Build check')+' · '+esc(r.status)+'</h4><p>'+esc(r.reason||'')+'</p>'+(r.runtime_trusted===false?'<p class="notice warm">Historical imported report. Run fresh checks for current execution evidence.</p>':'')+(r.changed_pixels!==undefined?'<p>'+r.changed_pixels+' of '+r.total_pixels+' pixels changed.</p>':'')+
 (r.visual?'<div class="visual-comparison">'+[['original_png_base64','Original'],['build_png_base64','Build'],['difference_png_base64','Difference']].map(([key,name])=>'<figure><figcaption>'+name+'</figcaption><img src="data:image/png;base64,'+esc(r.visual[key])+'" alt="'+name+' check picture" loading="lazy"></figure>').join('')+'</div>':'')+
 (r.runs?'<p>'+r.runs.length+' fresh worker runs · '+r.runs.filter(s=>s.state_replay).length+' state replays verified · '+r.runs.filter(s=>s.worker_exit_code===0).length+' clean exits</p>':'')+'<p class="subtle">This covers the configured inputs and assertions. It does not certify a complete game.</p></section>';
}
export function mountBuildChecks(ctx){
 clearTimeout(ctx.state.buildCheckTimer);const view=ctx.state.buildCheckView;if(!view?.pending)return;
 const current=()=>ctx.state.buildCheckView===view&&selectionKey(ctx.state)===view.scope&&ctx.state.page===view.page&&!!document.getElementById('build-checks');
 const poll=async()=>{if(!current())return;try{const r=await ctx.api.call('checks.status',ctx.sourceParams());if(!current())return;if(!(r.pending||[]).some(j=>!terminal.has(j.status))){await ctx.refreshProject();if(current())await ctx.render();return;}const node=document.getElementById('checks-progress');if(node)node.textContent=r.pending.filter(j=>!terminal.has(j.status)).map(j=>j.message).join(' · ');}catch(error){if(current()){const node=document.getElementById('checks-progress');if(node)node.textContent=error.message;return;}}if(current())ctx.state.buildCheckTimer=setTimeout(poll,2000);};
 ctx.state.buildCheckTimer=setTimeout(poll,2000);
}
