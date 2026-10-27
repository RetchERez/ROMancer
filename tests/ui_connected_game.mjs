import assert from 'node:assert/strict';
import fs from 'node:fs';
const file=new URL('../romancer/ui/views/gameview.js',import.meta.url);assert(fs.existsSync(file),'A shared Game view must be available.');
const {render}=await import(file),actions={},state={project:{project_id:'p',sources:[],builds:[]},artifact:{artifact_id:'a',sha256:'s',system_id:'snes'},results:{}},calls=[];
const node={id:'n',kind:'record',name:'Health value',offset:32,length:2,editor:'tables',locator:{row:0},confidence:'checked_declaration'};
const ctx={state,draft:(_,d)=>d,use:h=>Object.assign(actions,h),sourceParams:()=>({project_id:'p',artifact_id:'a'}),projectParams:()=>({project_id:'p'}),api:{call:async op=>op==='gameview.graph'?{ok:true,artifact_id:'a',source_sha256:'s',nodes:[node],edges:[],total:1,page:0,issues:[]}:op==='gameview.detail'?{ok:true,artifact_id:'a',source_sha256:'s',node,neighbors:[],connections:[],preview:{fields:[{name:'HP',value:20}]},hex_preview:'1400'}:{ok:true,artifact_id:'a',source_sha256:'s',config:{name:'Opening',automatic:true,mode:'review_changes',steps:[{frames:60,buttons:[],port:0}],region:null,route_ids:[]},results:[],pending:[]}},navigate:async n=>calls.push(n),setDraft:()=>{},render:async()=>{}};
assert.match(await render(ctx),/Health value/);assert.match(await render(ctx),/HP/);await actions['gameview-bytes']();assert.equal(state.resourceJump,32);assert.equal(calls[0],'resources');
state.artifact={...state.artifact,artifact_id:'other'};await actions['gameview-bytes']();assert.equal(calls.length,1,'Old controls cannot navigate a different source.');
console.log('Shared Game view renders known fields and guards source-bound navigation.');
{
 const {selectionKey}=await import('../romancer/ui/tool_inputs.js');state.artifact={artifact_id:'a',sha256:'s',system_id:'snes'};state.connectedPage=2;state.connectedTraceFocus={scope:selectionKey(state),trace_id:'wanted'};
 const drafts=new Map([['gameview-query','Health value']]);ctx.draft=(k,d)=>drafts.has(k)?drafts.get(k):d;ctx.setDraft=(k,v)=>drafts.set(k,v);let requested;
 const trace={...node,id:'wanted-node',kind:'trace',offset:null,locator:{trace_id:'wanted'}};const original=ctx.api.call;ctx.api.call=async(op,p)=>op==='gameview.graph'?(requested=p,{ok:true,artifact_id:'a',source_sha256:'s',nodes:[trace],edges:[],total:1,page:0,issues:[]}):op==='gameview.detail'?{ok:true,artifact_id:'a',source_sha256:'s',node:trace,neighbors:[],connections:[],preview:{},hex_preview:''}:original(op,p);
 await render(ctx);assert.equal(requested.page,0);assert.equal(requested.query,'');assert.equal(requested.kind,'trace');assert.equal(state.connectedNode.id,'wanted-node');
}

state.artifact={artifact_id:'a',sha256:'s',system_id:'snes'};
await render(ctx);assert(state.connectedNode);
await actions['gameview-find']();assert.equal(state.connectedNode,null,'Changing a resource filter must not keep a detail from the previous category.');
