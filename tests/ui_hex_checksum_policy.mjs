import assert from 'node:assert/strict';
import {hexEditor} from '../romancer/ui/hex_editor.js';
const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',size:4,system_id:'snes'},results:{}};
const data={artifact_id:'a',sha256:'sha',offset:0,hex:'01020304',length:4},actions={},values=new Map(),calls=[];
const ctx={state,use:a=>Object.assign(actions,a),draft:(k,f)=>values.get(k)??f,setDraft:(k,v)=>values.set(k,v),sourceParams:()=>({project_id:'p',artifact_id:'a'}),run:async(op,p)=>{calls.push(op);return {ok:true,plan_id:'plan',changed_bytes:1};},render:async()=>{}};
let html=hexEditor(ctx,data);assert.match(html,/Checksum policy/);assert.match(html,/Preserve checksum fields/);state.hexDraft.set(0,'05');
const old=globalThis.document;globalThis.document={querySelector:()=>null};
try{await actions['hex-review']();assert.equal(calls.at(-1),'systems.plan_edits');values.set('hex-checksum-policy','preserve');html=hexEditor(ctx,data);assert.match(html,/data-action="hex-apply"[^>]*disabled/);await actions['hex-review']();assert.equal(calls.at(-1),'bytes.plan');assert.match(hexEditor(ctx,data),/Checksum fields are preserved/);
 values.set('hex-checksum-policy','maintain');await assert.rejects(()=>actions['hex-apply'](),/Review/);
 values.set('hex-checksum-policy','bad');await assert.rejects(()=>actions['hex-review'](),/policy/);
}finally{globalThis.document=old;}
console.log('Explicit checksum preservation is available, defaults to maintenance, and policy changes invalidate review.');
