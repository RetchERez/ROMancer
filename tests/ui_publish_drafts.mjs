import assert from 'node:assert/strict';
import * as assets from '../romancer/ui/views/assets.js';
import * as tables from '../romancer/ui/views/tables.js';
import {hexEditor} from '../romancer/ui/hex_editor.js';
const bitmap={id:'b',width:8,height:8,count:1,codec:'tile8-planar2-msb-v1',cells:[{index:0,pixels:Array(64).fill(0)}]};
const doc={ok:true,document_id:'ad',source_sha256:'s',write_supported:true,bitmaps:[bitmap],palettes:[],fonts:[],tilemaps:[]};
function setup(){const actions={},drafts=new Map(),elements=new Map([['asset-schema',{value:'{}'}],['asset-changes',{value:'[]'}]]);let finish;
 globalThis.document={getElementById:id=>elements.get(id),querySelector:()=>null};
 const state={project:{project_id:'p',sources:[],builds:[]},artifact:{artifact_id:'a',sha256:'s',name:'Original.nes',size:4,system_id:'nes'},results:{'assets.inspect':doc}};
 const ctx={state,use:a=>Object.assign(actions,a),draft:(k,f)=>drafts.get(k)??f,setDraft:(k,v)=>drafts.set(k,v),sourceParams:()=>({project_id:'p',artifact_id:'a'}),projectParams:()=>({project_id:'p'}),run:()=>new Promise(r=>finish=r),render:async()=>{},notify:()=>{},refreshProject:async()=>{},setArtifact:async()=>{state.switched=true;},navigate:async()=>{}};
 return {actions,drafts,elements,state,ctx,finish:value=>finish(value)};
}
{
 const t=setup();await assets.render(t.ctx);t.state.paint={document_id:'ad',bitmap_id:'b',cell_index:0,pixels:[1,...Array(63).fill(0)]};
 const review=t.actions['asset-plan']();t.finish({ok:true,workbench_plan_id:'plan'});await review;
 const building=t.actions['asset-apply']();t.state.paint.pixels[1]=1;t.state.pending=null;t.ctx.setDraft('paint-buffer',JSON.stringify(t.state.paint));t.finish({ok:true});await building;
 assert.equal(t.state.paint?.pixels[1],1,'asset publishing preserves newer pixels');
}
{
 const t=setup();t.state.results={'tables.inspect':{ok:true,document_id:'td',source_sha256:'s',definition:{name:'Stats',fields:[{name:'Value',type:'u8',endian:'little',offset:0,pointer_base:null}]},rows:[{index:0,offset:0,cells:[{field:'Value',value:10,target_offset:null}]}],total:1,page:0,limit:50}};
 const id='table-cell-td-0-0';t.elements.set(id,{id,value:'11'});await tables.render(t.ctx);
 t.state.pending={kind:'table',artifact_id:'a',document_id:'td',plan_id:'plan',changes:[{row:0,field:'Value',before:10,after:11}]};
 const building=t.actions['table-build']();t.elements.get(id).value='12';t.ctx.setDraft(id,'12');t.state.pending=null;t.finish({ok:true});await building;
 assert.equal(t.drafts.get('table-reset-td')||'0','0','table publishing does not reset later field inputs');
}
{
 const t=setup();hexEditor(t.ctx,{artifact_id:'a',sha256:'s',offset:0,length:4,hex:'01020304',text:'....'});t.state.hexDraft.set(0,'05');
 const signature=JSON.stringify(t.state.hexDraft.edits(t.state));t.state.hexReview={scope:'p:a:s',signature,plan:{plan_id:'plan'}};
 const building=t.actions['hex-apply']();t.state.hexDraft.set(1,'06');t.state.hexReview=null;t.finish({ok:true,artifact_id:'new'});await building;
 assert.equal(t.state.hexDraft?.changes.get(1),'06','hex publishing preserves later edits');assert.equal(t.state.switched,undefined);
}
console.log('Publishing assets, tables and hex builds preserves edits made while the operation was running.');
