import assert from 'node:assert/strict';
import {render} from '../romancer/ui/views/tables.js';
const state={project:{project_id:'project'},artifact:{artifact_id:'source',sha256:'1'.repeat(64),size:64,descriptors:{}},results:{},pending:null};
const ctx={state,draft:(_,fallback)=>fallback,use:()=>{},sourceParams:()=>({project_id:'project',artifact_id:'source'}),api:{call:()=>{throw new Error('Unexpected implicit table request');}}};
const first=await render(ctx);assert.ok(first.includes('Define a table'));assert.ok(first.includes('Load table definition'));
state.results['tables.inspect']={source_sha256:state.artifact.sha256,document_id:'2'.repeat(64),definition:{name:'Test table',fields:[{name:'<script>unsafe</script>'}]},total:1,page:0,limit:50,rows:[{index:0,offset:4,cells:[{field:'<script>unsafe</script>',value:3,target_offset:null,pointer_resolution:null}]}]};
const populated=await render(ctx);assert.ok(populated.includes('Review changes'));assert.ok(populated.includes('&lt;script&gt;unsafe&lt;/script&gt;'));assert.equal(populated.includes('<script>unsafe</script>'),false);
state.results['tables.inspect'].definition.fields[0].type='u8';ctx.draft=(id,fallback)=>id.startsWith('table-cell-')?'256':fallback;
assert.match(await render(ctx),/Outside the declared numeric range/);
state.artifact.sha256='3'.repeat(64);assert.ok((await render(ctx)).includes('Define a table'));
console.log('Empty table, populated table, escaped labels and stale source UI passed.');
const {selectionKey}=await import('../romancer/ui/tool_inputs.js');
const proposal={scope:selectionKey(state),result:{source_sha256:state.artifact.sha256,definition:{},inspection:{}}};
state.tableProposal=proposal;ctx.draft=(id,fallback)=>id==='table-changes'?JSON.stringify({changes:[{row:0,after:4}]}):fallback;
assert.match(await render(ctx),/Finish the current table edits first/);
assert.equal(state.tableProposal,proposal,'Opening a generated layout must preserve existing staged edits.');

state.results['tables.inspect']={source_sha256:state.artifact.sha256,document_id:'typed',rows:[{index:0,cells:[{value:45}]}]};
ctx.draft=(id,fallback)=>id==='table-cell-typed-0-0'?'55':fallback;
assert.match(await render(ctx),/Finish the current table edits first/,'Typed cells must not be replaced before review stages them.');

{
 const definition={schema_version:1,name:'Neutral experiment',offset:32,count:1,stride:1,fields:[{name:'Value',offset:0,type:'u8',endian:'little',pointer_base:null}]};
 const sha='a'.repeat(64),inspection={source_sha256:sha,document_id:'generated',definition,total:1,page:0,limit:8,rows:[{index:0,offset:32,cells:[{field:'Value',value:5,target_offset:null}]}]};
 const drafts={},actions={},next={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:sha,size:64,descriptors:{tables:{source_sha256:sha,definition:{...definition,name:'Old named table',offset:0,label_source:{offset:16,length:4,stride:4}}}}},results:{}};
 next.tableProposal={scope:selectionKey(next),result:{source_sha256:sha,definition,inspection}};
 let submitted;
 const testctx={state:next,draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,use:r=>Object.assign(actions,r),sourceParams:()=>({project_id:'p',artifact_id:'a'}),render:async()=>{},run:async(op,p)=>{submitted=p.definition;return {inspection};}};
 globalThis.document={getElementById:id=>({value:drafts[id]??''})};
 assert.match(await render(testctx),/Save this layout/);await actions['table-inspect']();
 assert.equal(submitted.label_source,undefined,'A neutral generated layout must not inherit unrelated labels from the previously saved table.');
}
