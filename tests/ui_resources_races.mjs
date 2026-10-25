import assert from 'node:assert/strict';
import {render} from '../romancer/ui/views/resources.js';
const artifact=id=>({artifact_id:id,sha256:id.repeat(64),size:1024,name:id,system:'NES',kind:'source'});
const page=(a,offset=0)=>({artifact_id:a.artifact_id,sha256:a.sha256,offset,length:1,hex:a.artifact_id==='a'?'aa':'cc',text:'.'});
const catalog={resources:[],total:0,page:0,limit:50};
function setup(){const state={project:{project_id:'p',sources:[],builds:[]},artifact:artifact('a'),results:{},drafts:{},page:'resources'},handlers={},drafts={},calls=[];
 const ctx={state,use:map=>Object.assign(handlers,map),draft:(k,f)=>drafts[k]??f,setDraft:(k,v)=>drafts[k]=v,projectParams:()=>({project_id:state.project.project_id}),sourceParams:()=>({project_id:state.project.project_id,artifact_id:state.artifact.artifact_id}),api:{call:async(op,p)=>{calls.push([op,p]);return op==='resource.inspect'?page(state.artifact,p.offset):catalog;}}};
 return {state,ctx,handlers,drafts,calls};}

{
 const {state,ctx,handlers}=setup();let release;const paused=new Promise(resolve=>release=resolve);let entered;const waiting=new Promise(resolve=>entered=resolve);
 ctx.api.call=async(op,p)=>{if(op==='resource.inspect')return page(artifact(p.artifact_id));if(p.artifact_id==='a'){entered();await paused;}return catalog;};
 const old=render(ctx);await waiting;state.artifact=artifact('b');await render(ctx);const activeHandler=handlers['hex-page'];assert.equal(state.hexDraft.original.get(0),'cc');release();await old;
 assert.equal(state.hexDraft.original.get(0),'cc','Late page A must not overwrite B bytes.');assert.equal(handlers['hex-page'],activeHandler,'Late renders must not replace current handlers.');
}
for(const cached of [false,true]){
 const {state,ctx,calls}=setup();if(cached)state.results['resource.inspect']=page(state.artifact,128);state.resourceJump=512;
 const html=await render(ctx);assert.equal(calls.find(([op])=>op==='resource.inspect')?.[1].offset,512,'A jump must fetch the requested bytes even with a cached page.');assert.match(html,/data-hex-offset="512"/);assert.equal(state.results['resource.inspect'].offset,512);
}
{
 const {state,ctx,handlers}=setup();let release,entered;let current=true;ctx.isCurrentRender=()=>current;
 const paused=new Promise(r=>release=r),waiting=new Promise(r=>entered=r);
 ctx.api.call=async(op)=>{if(op==='resource.inspect')return page(state.artifact);entered();await paused;return catalog;};
 const old=render(ctx);await waiting;current=false;release();await old;assert.equal(state.hexDraft,undefined,'Navigation invalidates the old view even without a source change.');assert.deepEqual(handlers,{});
}
{
 const {state,ctx}=setup();state.artifact=null;ctx.sourceParams=()=>{throw Error('No source selected');};
 assert.match(await render(ctx),/Import a source/,'An empty project must offer import without inspecting a missing ROM.');
}
console.log('Resource jumps load exact bytes; overlapping renders retain the active source and handlers.');
