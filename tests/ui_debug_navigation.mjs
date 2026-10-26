import assert from 'node:assert/strict';
import test from 'node:test';
import {render} from '../romancer/ui/views/debug.js';

function fixture(){
 const actions={},state={project:{project_id:'p',sources:[],builds:[]},artifact:{artifact_id:'a',sha256:'s',size:4096,system_id:'nes',descriptors:{}},results:{},drafts:{}};
 const inputs={'address-system':'nes','address-mapping':'nrom','address-prg':'16','address-prg-size':'16384','cpu-address':'0x8000','address-bank':'','uses-offset':'128'};
 globalThis.document={getElementById:id=>({value:inputs[id]??''})};
 const ctx={state,use:rows=>Object.assign(actions,rows),draft:(k,d)=>d,sourceParams:()=>({project_id:state.project.project_id,artifact_id:state.artifact.artifact_id}),projectParams:()=>({project_id:state.project.project_id}),navigate:page=>{state.page=page;},render:()=>{},run:async(op)=>{
  const result=op==='systems.address'?{ok:true,status:'RESOLVED',artifact_id:'a',source_sha256:'s',offset:128,bank_state_observed:false}:{ok:true,source_sha256:'s',uses:[{name:'Pointer',kind:'text-pointer',offset:24}]};state.results[op]=result;return result;
 }};
 return {ctx,state,actions};
}

test('declared reference opens its actual numeric file offset',async()=>{
 const {ctx,state,actions}=fixture();await render(ctx);await actions['uses-read']();await render(ctx);actions['uses-open']({dataset:{id:'24'}});
 assert.equal(state.resourceJump,24);assert.equal(state.page,'resources');
});

test('resolved declared CPU mapping opens bytes and refuses stale selection',async()=>{
 const {ctx,state,actions}=fixture();await render(ctx);await actions['address-resolve']();const html=await render(ctx);
 assert.match(html,/Inspect mapped bytes/);assert.equal(typeof actions['address-open'],'function');
 actions['address-open']();assert.equal(state.resourceJump,128);assert.equal(state.page,'resources');
 state.resourceJump=null;state.project={...state.project,project_id:'other'};
 assert.throws(()=>actions['address-open'](),/changed|current|again/i);assert.equal(state.resourceJump,null);
});

test('pending mapping and reference requests cannot become another selection results',async()=>{
 for(const action of ['address-resolve','uses-read']){
  const {ctx,state,actions}=fixture();let finish;ctx.run=()=>new Promise(resolve=>{finish=resolve;});await render(ctx);
  const pending=actions[action]();state.artifact={...state.artifact,artifact_id:'other'};finish({ok:true,status:'RESOLVED',artifact_id:'a',source_sha256:'s',offset:128,uses:[]});await pending;
  const html=await render(ctx);assert.doesNotMatch(html,/Inspect mapped bytes/);assert.equal(state.debugAddress,undefined);assert.equal(state.debugReferences,undefined);
 }
});

test('failed or unresolved mapping offers no inspect action',async()=>{
 const {ctx,actions}=fixture();ctx.run=async()=>({ok:false,status:'BLOCKED',offset:128});await render(ctx);await actions['address-resolve']();assert.doesNotMatch(await render(ctx),/Inspect mapped bytes/);
});

test('an older mapping response cannot replace a newer result or survive failed re-resolution',async()=>{
 const {ctx,state,actions}=fixture();const pending=[];ctx.run=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));await render(ctx);
 const first=actions['address-resolve'](),second=actions['address-resolve']();const mapped=offset=>({ok:true,status:'RESOLVED',artifact_id:'a',source_sha256:'s',offset});
 pending[1].resolve(mapped(256));await second;pending[0].resolve(mapped(128));await first;await render(ctx);actions['address-open']();assert.equal(state.resourceJump,256);
 const failed=actions['address-resolve']();pending[2].reject(Error('Outside mapped bytes'));await assert.rejects(failed);assert.doesNotMatch(await render(ctx),/Inspect mapped bytes/);
});

test('reference actions reject foreign offsets and an old same-byte project selection',async()=>{
 const {ctx,state,actions}=fixture();await render(ctx);await actions['uses-read']();await render(ctx);
 assert.throws(()=>actions['uses-open']({dataset:{id:'99'}}),/again/i);state.project={...state.project,project_id:'other'};
 assert.throws(()=>actions['uses-open']({dataset:{id:'24'}}),/changed|current|again/i);assert.equal(state.resourceJump,undefined);
});
