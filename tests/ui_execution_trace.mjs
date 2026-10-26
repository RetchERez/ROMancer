import assert from 'node:assert/strict';
import fs from 'node:fs';
const path=new URL('../romancer/ui/execution_trace.js',import.meta.url);
assert.ok(fs.existsSync(path),'Native access capture needs a guided UI.');
const {executionTrace,observedSourceContext}=await import(path);
const {selectionKey}=await import('../romancer/ui/tool_inputs.js');
const {releaseProjectResources}=await import('../romancer/ui/project_flow.js');
const report={ok:true,source_sha256:'sha',artifact_id:'a',evidence_id:'e',status:'BUDGET_EXCEEDED',
 runtime_trusted:true,total_events:130,events:[{id:1,kind:'write',address:17,value:3,frame:8,file_offset:null,
 execution_context:{pc:32768,file_offset:16},registers:{pc:32771}}],offset:0,limit:100,omitted_events:52,
 route_complete:true,summary:{event_counts:{write:130,read:0,exec:0}},backend:{backend:'MesenCE',version:'2.2.1'},
 total_instruction_samples:1,instruction_samples:[{id:1,pc:512,assembly:'move #$2700, SR'}]};
function fixture(){
 const actions={},drafts={},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',system_id:'nes',size:40976}};
 const calls=[],ctx={state,use:r=>Object.assign(actions,r),draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,
 sourceParams:()=>({project_id:'p',artifact_id:state.artifact.artifact_id}),render:async()=>{},navigate:async()=>{},
 api:{call:async op=>op==='debugger.capabilities'?{ok:true,available:true,source_sha256:'sha',artifact_id:'a',backend:'MesenCE'}:report},
 run:async(op,p)=>{calls.push([op,p]);return structuredClone(report);}};
 return {ctx,state,actions,drafts,calls};
}
globalThis.document={getElementById:id=>({value:({'trace-frames-0':'8','trace-buttons-0':'a',
 'trace-start':'4','trace-limit':'200','trace-kind':'write','trace-address':'0x10','trace-length':'2'})[id]??''})};
{
 const {ctx,state,actions,calls}=fixture();const scope=selectionKey(state);
 state.nativeProbe={scope,result:{ok:true,source_sha256:'sha',artifact_id:'a',investigation_id:'i',
 candidate:{candidate_id:'c',offset:17,width:2},physical_probe:{kind:'write',start:17,end:18,domain:'nesInternalRam'}}};
 const html=await executionTrace(ctx);assert.match(html,/power on/i);assert.match(html,/0x11/);
 await actions['trace-capture']();assert.equal(calls[0][0],'debugger.investigate');
 assert.equal(calls[0][1].candidate_id,'c');assert.equal(calls[0][1].replay.steps[0].frames,8);
 assert.deepEqual(calls[0][1].replay.steps[0].buttons,['a']);assert.equal(calls[0][1].replay.probes,undefined);
 const shown=await executionTrace(ctx);assert.match(shown,/52/);assert.match(shown,/partial|limit/i);assert.match(shown,/0x8000/);
 assert.match(shown,/Native instruction samples/);assert.match(shown,/move #\$2700, SR/);
 await actions['trace-open']({dataset:{id:'16'}});assert.equal(state.resourceJump,16);
 assert.equal(state.nativeSourceContext.evidence_id,'e');
 assert.match(await observedSourceContext(ctx),/Why these bytes are open/);
 assert.match(await observedSourceContext(ctx),/0x8000/);
 state.artifact={...state.artifact,artifact_id:'other'};
 await assert.rejects(async()=>actions['trace-capture'](),/source|selection/i);
 releaseProjectResources(state);assert.equal(state.nativeTrace,null);assert.equal(state.nativeProbe,null);
}
{
 const {ctx,state,actions,drafts}=fixture();await executionTrace(ctx);let finish;
 ctx.run=()=>new Promise(resolve=>finish=resolve);const pending=actions['trace-capture']();
 state.selectionRevision=3;finish(report);await pending;
 assert.equal(drafts['native-trace-id'],undefined,'A late capture must not attach to a new selection.');
}
{
 const {ctx,actions}=fixture();ctx.api.call=async()=>({ok:true,available:false,source_sha256:'sha',artifact_id:'a',reason:'Pinned tool is missing.'});
 const html=await executionTrace(ctx);assert.match(html,/Pinned tool is missing/);
 await assert.rejects(async()=>actions['trace-capture'](),/missing/i);
}
console.log('Native trace UI uses authenticated candidates, clear replay scope, partial evidence and source guards.');
