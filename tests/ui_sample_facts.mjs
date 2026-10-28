import assert from 'node:assert/strict';
import {sampleFacts} from '../romancer/ui/sample_facts.js';
const handlers={},moves=[],state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'a'.repeat(64),size:1024}};
const packet={status:'RECORDED_SAMPLE',source_sha256:state.artifact.sha256,record:{sha256:state.artifact.sha256,labels:['Example <unsafe>'],system_id:'nes',size:1024,crc32:'12345678',format:'ines',header_numbers:{mapper:0},coverage:{compression_work_limited:false},discoveries:[{kind:'graphics',confidence:'format-derived',offset:16,length:16,format:'tile8-planar2-msb-v1'}]}};
const ctx={state,use:next=>Object.assign(handlers,next),navigate:async page=>moves.push(page)};
const html=sampleFacts(ctx,packet);assert.match(html,/Recorded sample/);assert.match(html,/Example &lt;unsafe&gt;/);assert.doesNotMatch(html,/<unsafe>/);assert.match(html,/Header-declared graphics/);
await handlers['sample-location']({dataset:{id:'16'}});assert.equal(state.resourceJump,16);assert.deepEqual(moves,['resources']);
state.artifact={...state.artifact,artifact_id:'other'};await handlers['sample-location']({dataset:{id:'16'}});assert.equal(moves.length,1);
state.artifact.sha256='b'.repeat(64);assert.equal(sampleFacts(ctx,packet),'');
assert.equal(sampleFacts(ctx,{status:'NOT_RECORDED'}),'');
console.log('Exact-source sample facts escape labels, keep candidate evidence and refuse stale navigation.');

