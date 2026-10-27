import assert from 'node:assert/strict';
import {compressedRoot,resourceSystem,compressionControls,compressionCapacity} from '../romancer/ui/compression_controls.js';
const parent={artifact_id:'parent',sha256:'a',size:32768,system_id:'gba'};
const child={artifact_id:'child',sha256:'b',size:16,system_hint:'gba',compressed_parent:{parent_id:'parent',codec:'gba-lz10',offset:512,allocation:32}};
const first={artifact_id:'first',source_id:'child',kind:'build'},second={artifact_id:'second',source_id:'first',kind:'build'};
const state={project:{sources:[parent,child],builds:[first,second]},artifact:second,results:{},pending:null};
assert.equal(compressedRoot(state),child);assert.equal(resourceSystem(state),'gba');
const ctx={state,draft:(_,fallback)=>fallback,use:()=>{}};
assert.ok(compressionControls(ctx).includes('Review reinsertion'));
state.artifact=parent;assert.equal(compressedRoot(state),null);assert.ok(compressionControls(ctx).includes('Extract decoded resource'));
state.artifact={artifact_id:'cycle',source_id:'cycle'};state.project.builds.push(state.artifact);assert.equal(compressedRoot(state),null);
console.log('Nested decoded-build ancestry, inherited system, setup and cycle refusal UI passed.');

assert.match(compressionCapacity({fits:true,packed_size:20,allocation:32,free_bytes:12,overflow_bytes:0,independent_decode_verified:true}),/12.*free/);
assert.match(compressionCapacity({fits:false,packed_size:35,allocation:32,free_bytes:0,overflow_bytes:3,independent_decode_verified:true}),/3.*over/);
