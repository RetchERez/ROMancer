import assert from 'node:assert/strict';
import test from 'node:test';
import {memoryWatches} from '../romancer/ui/memory_watches.js';

function fixture(){
 const actions={},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s',descriptors:{watches:{source_sha256:'s',watches:[{name:'Lives',region:2,offset:4,length:1}]}}},runtime:{game_sha256:'s'}};
 const packet={game_sha256:'s',worker_session_id:'worker',epoch:0,core_sha256:'core',core_options:{},region_size:100,region:2,offset:4,length:1,raw_hex:'01',sequence:1};
 const ctx={state,use:rows=>Object.assign(actions,rows),draft:(k,d)=>d,sourceParams:()=>({project_id:state.project.project_id,artifact_id:state.artifact.artifact_id}),projectParams:()=>({project_id:state.project.project_id}),render:()=>{},api:{call:async()=>packet}};
 return {ctx,state,actions,packet};
}

test('late watch reads cannot repopulate another project source or runtime',async()=>{
 for(const change of [s=>s.project={project_id:'q'},s=>s.artifact={...s.artifact,artifact_id:'b'},s=>s.runtime={game_sha256:'s'}]){
  const {ctx,state,actions,packet}=fixture();let finish;ctx.api.call=()=>new Promise(resolve=>finish=resolve);memoryWatches(ctx);
  const pending=actions['watch-read']();change(state);memoryWatches(ctx);finish(packet);await pending;
  assert.equal(state.watchReadings,null);
 }
});

test('late watch comparison cannot overwrite observations after runtime restore',async()=>{
 const {ctx,state,actions,packet}=fixture();memoryWatches(ctx);await actions['watch-read']();actions['watch-baseline']();memoryWatches(ctx);
 let finish;ctx.api.call=async op=>op==='runtime.memory'?{...packet,raw_hex:'02',sequence:2}:new Promise(resolve=>finish=resolve);
 const pending=actions['watch-read']();await new Promise(resolve=>setImmediate(resolve));assert.equal(typeof finish,'function');
 state.runtime={...state.runtime,restored:true};memoryWatches(ctx);finish({changes:[{offset:4,before:1,after:2}]});await pending;
 assert.equal(state.watchReadings,null);assert.equal(state.watchChanges,null);
});

test('watch baseline resets on same-byte source selection in another project',async()=>{
 const {ctx,state,actions}=fixture();memoryWatches(ctx);await actions['watch-read']();actions['watch-baseline']();state.project={project_id:'q'};memoryWatches(ctx);
 assert.equal(state.watchBaseline,null);assert.equal(state.watchReadings,null);
});

test('newer watch reads win while mixed native epochs cannot publish a watch group',async()=>{
 const {ctx,state,actions,packet}=fixture();const pending=[];ctx.api.call=()=>new Promise(resolve=>pending.push(resolve));memoryWatches(ctx);
 const first=actions['watch-read'](),second=actions['watch-read']();pending[1]({...packet,raw_hex:'02',sequence:2});await second;pending[0](packet);await first;
 assert.equal(state.watchReadings.Lives.raw_hex,'02');
 state.artifact.descriptors.watches.watches.push({name:'Gold',region:2,offset:8,length:1});memoryWatches(ctx);let count=0;
 ctx.api.call=async()=>({...packet,epoch:count++});await assert.rejects(actions['watch-read'](),/context changed/i);
 assert.equal(state.watchReadings.Gold,undefined);
});

test('a stale saved watch declaration can be replaced on the current source',async()=>{
 const {ctx,state,actions}=fixture();state.artifact.descriptors.watches.source_sha256='old';let saved;
 globalThis.document={getElementById:id=>({value:({'watch-name':'New watch','watch-region':'2','watch-offset':'8','watch-length':'1'})[id]})};
 ctx.run=async(op,params)=>{saved={op,params};};memoryWatches(ctx);await actions['watch-add']();
 assert.equal(saved.op,'watches.save');assert.deepEqual(saved.params.watches,[{name:'New watch',region:2,offset:8,length:1}]);
});
