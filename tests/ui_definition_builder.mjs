import assert from 'node:assert/strict';
import {definitionBuilder} from '../romancer/ui/definition_builder.js';
const actions={},drafts={},values={'builder-kind':'tables','builder-name':'Enemies','builder-offset':'0x1000','builder-count':'4','builder-stride':'4','builder-fields':'2','builder-field-name-0':'Health','builder-field-at-0':'0','builder-field-type-0':'u16','builder-field-endian-0':'little','builder-field-name-1':'Damage','builder-field-at-1':'2','builder-field-type-1':'u8','builder-field-endian-1':'little'};
globalThis.document={getElementById:id=>({value:values[id]??'',checked:values[id]===true})};
const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s',system_id:'nes'},results:{}};let saved=0,navigated='';
const ctx={state,use:r=>Object.assign(actions,r),draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,
 sourceParams:()=>({project_id:'p',artifact_id:'a'}),render:async()=>{},navigate:async p=>navigated=p,notify:()=>{},
 run:async(op,p)=>{if(op==='definitions.save')saved++;return {ok:true,kind:p.kind,source_sha256:'s',artifact_id:'a',review_id:'r',replacements:[],definition:p.config,inspection:{ok:true,definition:p.config,rows:[{index:0,cells:[{field:'Health',value:25}]}]}};}};
assert.match(definitionBuilder(ctx),/Build an editor/);await actions['builder-preview']();assert.equal(saved,0);
assert.match(definitionBuilder(ctx),/25/);values['builder-field-at-1']='3';await assert.rejects(async()=>actions['builder-save'](),/changed|preview/i);assert.equal(saved,0);
values['builder-field-at-1']='2';definitionBuilder(ctx);await actions['builder-save']();assert.equal(saved,1);assert.equal(navigated,'tables');
assert.equal(state.results['tables.inspect'].rows[0].cells[0].value,25);
values['builder-count']='';definitionBuilder(ctx);await assert.rejects(async()=>actions['builder-preview'](),/whole number/i);
console.log('Visual editor builder previews real fields, rejects changed forms and hands off saved definitions.');
