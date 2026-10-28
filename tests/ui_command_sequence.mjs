import assert from 'node:assert/strict';
import {commandFromForm,operandFromForm,commandForms} from '../romancer/ui/command_forms.js';
import {sequenceChange,restoreSequence} from '../romancer/ui/command_sequence.js';
import {hasStagedChanges} from '../romancer/ui/workspace_status.js';
const field=operandFromForm({name:'Health',offset:'1',bytes:'1',endian:'little',minimum:'0',maximum:'99'});
const command=commandFromForm({opcode:'0x10',name:'Health',length:'2',role:'action'},[field]);
assert.equal(command.opcode,16);assert.equal(command.fields[0].target_base,null);
assert.throws(()=>commandFromForm({opcode:'256',name:'Bad',length:'2',role:'action'},[]));
assert.throws(()=>operandFromForm({name:'A',offset:'1',bytes:'1',endian:'little',minimum:'9',maximum:'1'}));
const doc={document_id:'d',scripts:[{id:'a',commands:[{opcode:16,fields:[{name:'Health',value:8}]},{opcode:255,fields:[]}]}]};
let s=restoreSequence(doc,'a','null');assert.deepEqual(s.items,[{opcode:16,values:{Health:8}},{opcode:255,values:{}}]);
s.items=sequenceChange(s.items,'insert',0,{opcode:16,values:{Health:12}});assert.equal(s.items.length,3);
s.items=sequenceChange(s.items,'down',0);assert.equal(s.items[0].values.Health,8);
s.items=sequenceChange(s.items,'remove',0);assert.equal(s.items[0].values.Health,12);
assert.throws(()=>sequenceChange(s.items,'down',9));assert.throws(()=>restoreSequence(doc,'a','bad'));
assert.equal(restoreSequence({...doc,document_id:'other'},'a',JSON.stringify(s)).items[0].values.Health,8);
s.changed=true;
const state={project:{project_id:'p'},artifact:{artifact_id:'a'},drafts:{'p:a:command-sequence':JSON.stringify(s)}};
assert.equal(hasStagedChanges(state),true);
console.log('Known command forms and sequence edits validate bounds, preserve named operands and register unsaved edits.');
{
 const actions={},drafts={},state={page:'debug',artifact:{sha256:'s',size:32768},project:{project_id:'p'}};globalThis.document={getElementById:id=>({value:id==='cf-name'?'Existing format':''})};
 const ctx={state,draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,use:r=>Object.assign(actions,r),render:async()=>{},sourceParams:()=>({}),run:async()=>({review_id:'r'})};
 commandForms(ctx,{definition:{source_sha256:'s',name:'Existing format',scripts:[],commands:[]}});await actions['cf-preview']();assert.equal(state.commandFormReview.review_id,'r','An untouched saved grammar can be previewed without first editing its form.');
}
