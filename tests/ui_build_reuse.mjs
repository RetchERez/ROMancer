import assert from 'node:assert/strict';
import {applyReviewedBuild} from '../romancer/ui/build_reuse.js';
const pending={artifact_id:'a',plan_id:'plan'},existing={artifact_id:'b',source_id:'a',plan_id:'plan'};let calls=0;
const ctx={projectParams:()=>({project_id:'p'}),api:{call:async()=>({builds:[existing]})},run:async()=>{calls++;return {artifact_id:'new'};}};
assert.equal((await applyReviewedBuild(ctx,pending)).artifact_id,'b');assert.equal(calls,0);
ctx.api.call=async()=>({builds:[{...existing,source_id:'other'}]});assert.equal((await applyReviewedBuild(ctx,pending)).artifact_id,'new');assert.equal(calls,1);
console.log('Reviewed editor actions reopen an exact existing plan build, while a different input creates a separate build.');
