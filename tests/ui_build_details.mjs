import assert from 'node:assert/strict';
import {runNamedBuild,planForBuildAction} from '../romancer/ui/build_details.js';
const row={artifact_id:'b',kind:'build',sha256:'target',name:'Build 1'},drafts={'next-build-name':'My sprite','next-build-notes':'one pixel'},state={project:{project_id:'p',builds:[row]},artifact:{artifact_id:'a',sha256:'s'}};let annotation,rendered=0;
const ctx={state,draft:(k,f)=>drafts[k]??f,setDraft:(k,v)=>drafts[k]=v,api:{call:async(op,p)=>{annotation=p;row.name=p.name;}},refreshProject:async()=>{},render:async()=>rendered++,notify(){}};
const result=await runNamedBuild(ctx,'build.apply',{project_id:'p'},{},async()=>row);assert.equal(result.name,'My sprite');assert.equal(annotation.artifact_id,'b');assert.equal(annotation.notes,'one pixel');assert.equal(drafts['next-build-name'],'');assert.equal(rendered,1);
drafts['next-build-name']='Later';let finish;ctx.api.call=()=>new Promise(r=>finish=r);const waiting=runNamedBuild(ctx,'build.apply',{project_id:'p'},{},async()=>row);await Promise.resolve();state.artifact={artifact_id:'other',sha256:'other'};finish();await assert.rejects(waiting,/previous selection/);
state.artifact={artifact_id:'a',sha256:'s'};drafts['next-build-name']='x'.repeat(121);let applied=false;await assert.rejects(runNamedBuild(ctx,'build.apply',{project_id:'p'},{},async()=>{applied=true;return row;}),/120/);assert.equal(applied,false);
console.log('Build metadata is optional, source-bound, validated before creation and does not mislabel newer selections.');

const assetPlan={ok:true,plan_id:'assets',edits:[{offset:0,before:'00',after:'01'}]},hexPlan={ok:true,plan_id:'hex',edits:[{offset:0,before:'0000000000',after:'0101010101'}]};
const mixed={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'},pending:{kind:'assets',artifact_id:'a',plan_id:'assets'},results:{'assets.plan':assetPlan},hexReview:{scope:'p:a:s',signature:'[]',plan:hexPlan},hexDraft:{edits:()=>[]}};
assert.equal(planForBuildAction(mixed,'hex-apply'),hexPlan,'hex summary must not borrow another editor plan');
assert.equal(planForBuildAction(mixed,'asset-apply'),assetPlan);
assert.equal(planForBuildAction(mixed,'reloc-build'),null,'no fallback to unrelated editor');
assert.equal(planForBuildAction(mixed,'maps-build'),null,'unknown locally scoped plans are omitted');
mixed.hexReview.scope='old';assert.equal(planForBuildAction(mixed,'hex-apply'),null);
mixed.pending.artifact_id='old';assert.equal(planForBuildAction(mixed,'asset-apply'),null);
console.log('Create summaries resolve only the matching action and selected source; mixed editor plans cannot leak.');
