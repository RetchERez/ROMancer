import assert from 'node:assert/strict';
import {render as playtest} from '../romancer/ui/views/playtest.js';
import {render as tables} from '../romancer/ui/views/tables.js';
import {stopPlayback} from '../romancer/ui/playback_controls.js';
globalThis.localStorage={getItem:()=>null};
globalThis.document={getElementById:()=>null,activeElement:null};
let failures=[];
async function check(name,test){try{await test();console.log(name+' passed.');}catch(error){failures.push(name+': '+error.message);}}
await check('Delayed Play cannot restart after navigation or selection changes',async()=>{
 for(const change of [state=>state.page='resources',state=>state.artifact={artifact_id:'other'},state=>state.project={project_id:'other'},state=>{state.project=null;state.runtime=null;}]){
  let resolveStart,steps=0;const handlers={},state={page:'playtest',project:{project_id:'p',containers:[]},artifact:{artifact_id:'a',name:'Original',sha256:'a'.repeat(64)},runtime:{session_dir:'s'},results:{},capabilities:{platform:'Windows'},liveAudio:{ticket:0,start:()=>new Promise(resolve=>resolveStart=resolve),stop(){this.ticket++;},setVolume(){}}};
  const ctx={state,use:actions=>Object.assign(handlers,actions),draft:(_,fallback)=>fallback,render:async()=>{},notify(){},sourceParams:()=>({project_id:state.project.project_id,artifact_id:state.artifact.artifact_id}),projectParams:()=>({project_id:state.project.project_id}),api:{call:async op=>{if(op==='runtime.step'){steps++;throw new Error('late step');}return op==='saves.list'?{saves:[]}:op==='runtime.checkpoints'?{checkpoints:[]}:{profile:null};}}};
  await playtest(ctx);const playing=handlers['runtime-play']();stopPlayback(state);change(state);resolveStart();await playing.catch(()=>{});assert.equal(steps,0);assert.equal(state.playing,false);
 }
});
function tableContext(){const handlers={},drafts=new Map(),nodes=new Map(),calls=[],definition={schema_version:1,name:'Stats',offset:0,count:100,stride:1,fields:[{name:'Value',offset:0,type:'u8',endian:'little',pointer_base:null}]};
 const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'a'.repeat(64),size:100,descriptors:{}},results:{'tables.inspect':{ok:true,source_sha256:'a'.repeat(64),document_id:'doc',definition,total:100,page:0,limit:50,rows:[{index:0,offset:0,cells:[{field:'Value',value:3,target_offset:null}]}]}},pending:null};
 const ctx={state,use:actions=>Object.assign(handlers,actions),draft:(id,fallback)=>drafts.get(id)??fallback,setDraft:(id,value)=>drafts.set(id,value),render:async()=>{},notify(){},sourceParams:()=>({project_id:'p',artifact_id:'a'}),projectParams:()=>({project_id:'p'}),sourceParams:()=>({project_id:'p',artifact_id:'a'}),api:{call:async()=>{}},run:async(op,p)=>{calls.push({op,p});return {plan_id:'plan'};}};
 globalThis.document={getElementById:id=>nodes.get(id)||null};return {ctx,state,handlers,drafts,nodes,calls};
}
await check('A changed visible value cannot apply an earlier table review',async()=>{const f=tableContext();await tables(f.ctx);const id='table-cell-doc-0-0';f.nodes.set(id,{id,value:'4'});await f.handlers['table-review']();f.nodes.get(id).value='5';await assert.rejects(f.handlers['table-build'](),/review|changed/i);assert.equal(f.calls.some(c=>c.op==='build.apply'),false);assert.equal(f.nodes.get(id).value,'5');});
await check('A value changed during review still needs a fresh review',async()=>{const f=tableContext();await tables(f.ctx);const id='table-cell-doc-0-0';f.nodes.set(id,{id,value:'4'});let finish;f.ctx.run=async(op,p)=>{f.calls.push({op,p});if(op==='tables.plan')return new Promise(resolve=>finish=resolve);return {ok:true};};const reviewing=f.handlers['table-review']();f.nodes.get(id).value='5';finish({plan_id:'plan'});await reviewing;await assert.rejects(f.handlers['table-build'](),/review|changed/i);assert.equal(f.calls.some(c=>c.op==='build.apply'),false);});
await check('Discard resets off-page table drafts',async()=>{const f=tableContext();f.drafts.set('table-cell-doc-50-0','9');await tables(f.ctx);await f.handlers['table-discard']();f.state.results['tables.inspect']={...f.state.results['tables.inspect'],page:1,rows:[{index:50,offset:50,cells:[{field:'Value',value:3,target_offset:null}]}]};const html=await tables(f.ctx);assert.ok(!/id="table-cell-doc[^\"]*50-0"[^>]*value="9"/.test(html));});
if(failures.length){console.error(failures.join('\n'));process.exitCode=1;}
