import assert from 'node:assert/strict';
import {hexComparison} from '../romancer/ui/hex_editor.js';
async function compare(leftBytes,rightBytes,offset){
 const left={artifact_id:'l',sha256:'left',name:'Original',size:leftBytes.length},right={artifact_id:'r',sha256:'right',name:'Modded',size:rightBytes.length};
 const state={project:{project_id:'p',sources:[left],builds:[right]},artifact:right,hexComparison:{project_id:'p',left_id:'l',right_id:'r',left_sha256:'left',right_sha256:'right',offset}};
 const actions={},calls=[];const ctx={state,use:a=>Object.assign(actions,a),render:async()=>{},api:{call:async(op,p)=>{calls.push(p);const row=p.artifact_id==='l'?left:right,bytes=p.artifact_id==='l'?leftBytes:rightBytes;return {ok:true,artifact_id:row.artifact_id,sha256:row.sha256,offset:p.offset,length:Math.min(p.length,bytes.length-p.offset),hex:Buffer.from(bytes.slice(p.offset,p.offset+p.length)).toString('hex')};}}};
 const html=await hexComparison(ctx,{artifact_id:'r',sha256:'right',offset:Math.max(0,right.size-1),length:1,hex:'00'});return {html,ctx,actions,calls};
}
let r=await compare([0,1,2,3,4,5],[0,9,2],3);assert.match(r.html,/Compare at 0x3/);assert.match(r.html,/03.*04.*05/);assert.match(r.html,/No byte in file/);assert.equal(r.calls[1].offset,3);
r=await compare([0,1,2],[0,1,2,3,4,5],3);assert.match(r.html,/No byte in file/);assert.match(r.html,/03.*04.*05/);
r=await compare([0,1,2],[0,9,2],0);assert.match(r.html,/<mark>01<\/mark>/);assert.match(r.html,/<mark>09<\/mark>/);
r.ctx.state.artifact={...r.ctx.state.artifact,artifact_id:'other'};await assert.rejects(r.actions['hex-diff-page']({dataset:{id:'256'}}),/selected|changed/i);
console.log('Byte comparison shows changed, added and removed bytes without shifting offsets or borrowing another source.');
