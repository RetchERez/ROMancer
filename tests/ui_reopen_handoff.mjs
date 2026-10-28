import assert from 'node:assert/strict';
import {textGrowth} from '../romancer/ui/text_growth.js';
import {commandSequence} from '../romancer/ui/command_sequence.js';
const command={opcode:16,name:'Set color',length:2,role:'action',fields:[{name:'Color',minimum:0,maximum:63}]},end={opcode:255,name:'Finish',length:1,role:'end',fields:[]};
const script=id=>({id,editable:true,commands:[{opcode:16,fields:[{name:'Color',value:8}]},{opcode:255,fields:[]}]});
const commandDoc={document_id:'d',definition:{commands:[command,end]},scripts:[script('A'),script('B')]};
{
 const actions={},drafts={},state={page:'debug',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'}};
 const ctx={state,draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,use:r=>Object.assign(actions,r),render:async()=>{}};
 commandSequence(ctx,commandDoc);await actions['cq-insert']();drafts['command-script']='B';commandSequence(ctx,commandDoc);await actions['cq-insert']();drafts['command-script']='A';const html=commandSequence(ctx,commandDoc);
 assert.equal((html.match(/<li>/g)||[]).length,3,'Script A retains its inserted command after editing B.');assert.equal(Object.keys(drafts).filter(k=>k.startsWith('command-sequence')).length,2,'Each script owns its own draft.');
}
for(const kind of ['growth','cq']){
 const actions={},drafts={},nodes={'growth-record':{value:'r'},'growth-target':{value:'6144'},'growth-capacity':{value:'32'},'growth-fill':{value:'255'},'growth-align':{value:'1'},'growth-bank':{value:'8192'},'growth-origin':{value:'16'},'growth-extra':{value:''},'growth-complete':{checked:true},'growth-reserved':{checked:true},'script-schema':{value:'{}'},'script-segment-0-0':{value:'WELCOME'},'cq-fill':{value:'0'},'cq-complete':{checked:true}};
 globalThis.document={getElementById:id=>nodes[id]};const state={page:kind==='growth'?'scripts':'debug',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'},results:{}};let resolve;
 const built={artifact_id:'b',sha256:'target',plan_id:'plan',source_id:'a'},opened={ok:true,schema:{id:'moved'},definition:{id:'moved'},inspection:{id:'old-inspection'}};
 const ctx={state,sourceParams:()=>({project_id:state.project.project_id,artifact_id:state.artifact.artifact_id}),projectParams:()=>({project_id:state.project.project_id}),draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,use:r=>Object.assign(actions,r),render:async()=>{},notify:()=>{},api:{call:async op=>op==='project.open'?{builds:[built]}:opened},run:async op=>op.endsWith('plan')?{plan_id:'plan'}:{review_id:'review',pointer_updates:[],required_bytes:12,capacity:32},setArtifact:()=>new Promise(r=>resolve=r)};
 const doc={ok:true,write_supported:true,document_id:'d',records:[{id:'r',capacity:8,segments:[{index:0,text:'HI'}]}]},render=()=>kind==='growth'?textGrowth(ctx,doc):commandSequence(ctx,commandDoc);
 render();await actions[kind+'-preview']();render();await actions[kind+'-plan']();render();const pending=actions[kind+'-build']();await new Promise(setImmediate);assert.equal(typeof resolve,'function');state.artifact={artifact_id:'other',sha256:'new'};state.results={sentinel:true};resolve(false);await pending;
 assert.deepEqual(state.results,{sentinel:true},'Interrupted '+kind+' selection preserves the new source inspection.');assert.equal(drafts['script-schema'],undefined);assert.equal(drafts['command-definition'],undefined);
}
console.log('Separate script drafts survive switching; interrupted text/command build selection preserves the newer source.');
