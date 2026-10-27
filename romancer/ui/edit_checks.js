import {button,select,read} from './common.js';
import {selectionKey} from './tool_inputs.js';
import {checkReport} from './build_checks.js';
export function editCheckSelection(state){
 const rows=[...(state.project?.sources||[]),...(state.project?.builds||[])],byId=new Map(rows.map(r=>[r.artifact_id,r]));
 const chain=artifact=>{const seen=new Set(),list=[];for(let n=0;artifact&&n<128;n++){if(seen.has(artifact.artifact_id))break;seen.add(artifact.artifact_id);list.push(artifact);artifact=byId.get(artifact.source_id);}return list;};
 const baseline=chain(state.artifact).find(r=>r.gameplay_traces?.source_sha256===r.sha256&&r.gameplay_traces.ids?.length);
 if(!baseline)return {baseline:null,targets:[],traces:[]};
 const targets=rows.filter(r=>r.kind==='build'&&r.artifact_id!==baseline.artifact_id&&r.system_id===baseline.system_id&&chain(r).some(a=>a.artifact_id===baseline.artifact_id));
 return {baseline,targets,traces:baseline.gameplay_traces.ids};
}
export function editCheckControls(ctx){
 const {state}=ctx;if(!state.artifact)return '';
 const scope=selectionKey(state),choice=editCheckSelection(state),current=()=>scope===selectionKey(state);
 ctx.use({'edit-check-run':async()=>{if(!current())throw Error('The selected ROM changed.');const target_id=read('edit-check-target'),trace_id=read('edit-check-trace');if(!choice.baseline||!choice.targets.some(r=>r.artifact_id===target_id)||!choice.traces.includes(trace_id))throw Error('Choose a descendant build and captured trace.');const result=await ctx.run('checks.from_trace',{project_id:state.project.project_id,source_id:choice.baseline.artifact_id,target_id,trace_id},{render:false});if(!current())return;state.editCheckResult=result;return ctx.render();}});
 const result=state.editCheckResult,matching=result&&choice.baseline?.sha256===result.source_sha256&&choice.targets.some(t=>t.sha256===result.target_sha256);
 const reason=!choice.baseline?'Capture a fresh cold-start trace in Playtest first.':!choice.targets.length?'Review your edit and create a separate build first.':'';
 return '<details class="card edit-checks" '+(matching?'open':'')+'><summary>Test this edit</summary><p>Replay your captured inputs on the original twice and the edited build once. Compare the original, build and difference pictures.</p>'+
 (choice.targets.length?select('edit-check-target','Edited build',choice.targets.map(r=>[r.artifact_id,r.name||r.artifact_id]),ctx.draft('edit-check-target',state.artifact.kind==='build'?state.artifact.artifact_id:choice.targets.at(-1).artifact_id)):'')+
 (choice.traces.length?select('edit-check-trace','Saved trace',choice.traces.map((id,i)=>[id,'Capture '+(i+1)+' · '+id.slice(0,8)]),ctx.draft('edit-check-trace',choice.traces.at(-1))):'')+
 button('Test this edit','edit-check-run',{primary:true,disabled:!!reason,reason})+button('Open Playtest','navigate',{id:'playtest'})+'<p class="subtle">Up to 2400 frames and 20 input steps. The original must reproduce the captured scene. A visible change needs review; it is not automatically a failure.</p>'+(matching?checkReport(result):'')+'</details>';
}
