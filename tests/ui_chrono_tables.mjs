import assert from 'node:assert/strict';
import {render} from '../romancer/ui/views/tables.js';

const drafts=new Map(),actions={};
const definition={name:'Synthetic named stats',fields:[{name:'Chance',type:'u8',minimum:0,maximum:100}]};
const rows=[{index:0,offset:4,label:'Alpha <blade>',record_id:1,label_status:'decoded',
 cells:[{field:'Chance',value:25,target_offset:null,pointer_resolution:null}]}];
const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'1'.repeat(64),size:1024,descriptors:{}},
 results:{'tables.inspect':{definition,source_sha256:'1'.repeat(64),document_id:'2'.repeat(64),rows,
 row_catalog:[{index:0,label:'Alpha <blade>',record_id:1,label_status:'decoded'},
 {index:51,label:'Beta <script>',record_id:52,label_status:'decoded'}],total:85,page:0,limit:50}},pending:null};
let calls=[];const nodes=new Map();
globalThis.document={getElementById:id=>nodes.get(id)||null};
const ctx={state,draft:(id,fallback)=>drafts.get(id)??fallback,setDraft:(id,value)=>drafts.set(id,value),
 use:value=>Object.assign(actions,value),sourceParams:()=>({project_id:'p',artifact_id:'a'}),
 render:async()=>render(ctx),run:async(method,params)=>{calls.push({method,params});return {};},notify:()=>{}};
let html=await render(ctx);
assert.ok(html.includes('Alpha &lt;blade&gt;'),'named row labels are visible and escaped');
assert.ok(html.includes('Find records'),'named rows can be searched');
assert.ok(html.includes('Show selected record'),'a named record can be selected without entering an index');
assert.ok(html.includes('Range 0–100'),'declared numeric bounds are visible before editing');
const inputId='table-cell-'+state.results['tables.inspect'].document_id+'-0-0';
nodes.set(inputId,{id:inputId,value:'101'});
drafts.set(inputId,'101');html=await render(ctx);
assert.match(html,/Outside the declared numeric range/,'declared game limit overrides u8 storage limit');
nodes.set('table-name-query',{value:'beta'});
await actions['table-search']();
html=await render(ctx);
assert.ok(html.includes('Beta &lt;script&gt;'));
assert.equal(html.includes('<script>'),false);
nodes.set('table-record-choice',{value:'51'});
await actions['table-select-record']();
assert.equal(calls.at(-1).method,'tables.inspect');
assert.equal(calls.at(-1).params.page,1);
assert.equal(JSON.parse(drafts.get('table-changes')).changes[0].after,101,'pagination preserves staged visible edits');
nodes.set('table-record-choice',{value:'999'});
await assert.rejects(()=>actions['table-select-record'](),/record/i);
console.log('Named table search, selection, escaped labels, declared limits and staged pagination passed.');
