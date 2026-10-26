import assert from 'node:assert/strict';
import fs from 'node:fs';
const path=new URL('../romancer/ui/structural_lab.js',import.meta.url);
assert.ok(fs.existsSync(path),'Structural experiments need a visible guided tool.');
const {structuralLab}=await import(path);
const candidate={candidate_id:'c',offset:3,width:4,stride:8,count:5,base:0x08000000,endian:'little',samples:[{stored_value:0x08000100,target_offset:256,target_preview:'HELLO'}]};
const survey={ok:true,source_sha256:'sha',artifact_id:'a',candidates:[candidate],total_candidates:1,truncated:false,
 coverage:{positions_tested:30,position_stride:1,length:512},next_experiment:'Compare another state.'};
function fixture(){
 const actions={},drafts={},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'},results:{}};
 const ctx={state,use:r=>Object.assign(actions,r),draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,
 sourceParams:()=>({project_id:'p',artifact_id:state.artifact.artifact_id}),render:async()=>{},navigate:async()=>{},
 run:async(op,p)=>op==='structures.survey'?survey:{ok:true,source_sha256:'sha',artifact_id:'a',inspection:{source_sha256:'sha'},definition:{fields:[]}}};
 return {ctx,state,actions,drafts};
}
globalThis.document={getElementById:id=>({value:({'lab-offset':'0','lab-length':'512','lab-interpretation':'numeric'})[id]??''})};
{
 const {ctx,state,actions}=fixture();await structuralLab(ctx);await actions['lab-survey']();
 const html=await structuralLab(ctx);assert.match(html,/HELLO/);assert.match(html,/hypothes/i);assert.match(html,/Open table editor/);
 await actions['lab-open']({dataset:{id:'c'}});assert.equal(state.tableProposal.result.source_sha256,'sha');
 state.artifact={...state.artifact,artifact_id:'other'};await assert.rejects(async()=>actions['lab-open']({dataset:{id:'c'}}),/source|selection/i);
}
{
 const {ctx,state,actions}=fixture();await structuralLab(ctx);let finish;
 ctx.run=()=>new Promise(resolve=>finish=resolve);const pending=actions['lab-survey']();state.selectionRevision=4;finish(survey);await pending;
 assert.equal(state.structuralLab.result,null,'A late experiment cannot attach to another selection.');
}
console.log('Structural lab opens source-bound neutral editors and guards late or replaced selections.');
