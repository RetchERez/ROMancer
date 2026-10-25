import assert from 'node:assert/strict';
import {canApplyPatch,preparePatch,patchControls} from '../romancer/ui/patch_controls.js';
const state={project:{project_id:'a'.repeat(32)},artifact:{artifact_id:'b'.repeat(32),sha256:'1'.repeat(64),name:'Original.nes'}};
const preview={ok:true,project_id:state.project.project_id,source_id:state.artifact.artifact_id,source_sha256:state.artifact.sha256,plan_id:'c'.repeat(64),changed_bytes:2};
assert.equal(canApplyPatch(state,preview),true);
assert.equal(canApplyPatch({...state,artifact:{...state.artifact,sha256:'2'.repeat(64)}},preview),false);
assert.equal(canApplyPatch({...state,project:{project_id:'d'.repeat(32)}},preview),false);
const ctx={state,api:{uploadInput:async()=>({input_id:'e'.repeat(32),name:'<img onerror=bad>.bps'})},run:async(op,p)=>{
 assert.equal(op,'patches.preview');assert.equal(p.input_id,'e'.repeat(32));return preview;
},draft:(_k,f)=>f,use:()=>{}};
await preparePatch(ctx,{name:'test.bps'},'');assert.equal(state.patchImport.preview,preview);
assert.ok(!patchControls(ctx).includes('<img onerror=bad>'));
ctx.api.uploadInput=async()=>{state.artifact={...state.artifact,artifact_id:'f'.repeat(32)};return {input_id:'e'.repeat(32)};};
const prior=state.patchImport;await assert.rejects(()=>preparePatch(ctx,{name:'other.bps'},''),/selection|selected/i);
assert.equal(state.patchImport,prior);
console.log('Patch previews bind exact project/source bytes; late uploads cannot replace a new selection.');
