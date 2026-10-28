import assert from 'node:assert/strict';
import {investigationFollow} from '../romancer/ui/investigation_follow.js';
const actions={},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s',size:8192}},entry={};
const result={evidence_id:'e'},response={ok:true,evidence_id:'e',artifact_id:'a',source_sha256:'s',status:'PARTIAL',
 writers:[{file_offset:16,cpu_pc:32768,sampled_writes:130,resources:[]}],source_reads:[{file_offset:4112,sampled_reads:2,resources:[]}],next_steps:['Narrow the watch'],coverage:{access_events:132,partial:true},scope:'Separate observations'};
let calls=[],navigated='';
const ctx={state,use:r=>Object.assign(actions,r),sourceParams:()=>({project_id:'p',artifact_id:'a'}),
 run:async(op,p)=>{calls.push([op,p]);return response;},render:async()=>{},navigate:async p=>navigated=p};
assert.match(investigationFollow(ctx,result,entry),/Explain this capture/);
await actions['follow-explain']();
let html=investigationFollow(ctx,result,entry);assert.match(html,/Writer code/);assert.match(html,/Source reads/);assert.match(html,/132/);
await actions['follow-open']({dataset:{id:'4112'}});assert.equal(state.resourceJump,4112);assert.equal(navigated,'resources');
assert.equal(calls[0][0],'debugger.follow');assert.equal(calls[0][1].evidence_id,'e');
await assert.rejects(async()=>actions['follow-open']({dataset:{id:'999'}}),/captured/);
let finish;ctx.run=()=>new Promise(r=>finish=r);let late=actions['follow-explain']();state.artifact={...state.artifact,artifact_id:'b'};finish(response);await late;
assert.equal(entry.follow,response,'Late completion cannot replace the earlier source-bound summary.');
console.log('Full-capture explanation and selected source read handoff are guarded.');
