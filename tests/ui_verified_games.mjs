import assert from 'node:assert/strict';
import {gameEdits,gameByteNotes} from '../romancer/ui/verified_games.js';
import {selectionKey} from '../romancer/ui/tool_inputs.js';

const profile={id:'castlevania-usa',name:'Castlevania',reference:'https://example.org/source',scope:'Starting spare lives.'};
const model={ok:true,status:'MATCHED',artifact_id:'a',source_sha256:'sha',profile,fields:[{id:'spare_lives',label:'Starting spare lives',type:'integer',min:1,max:99,value:3}],locations:[{offset:116790,length:1,label:'Starting spare lives',storage:'Unsigned 8-bit counter',meaning:'Includes the current life.',example:'04 = 3 spare lives',evidence:'Native HUD observed.'}]};
let actions={},lateResolve,values={'game-spare_lives':'9'},calls=[];
globalThis.document={getElementById:id=>({value:values[id]})};
const ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'}},sourceParams:()=>({project_id:'p',artifact_id:ctx.state.artifact.artifact_id}),draft:(_,fallback)=>fallback,use:handlers=>Object.assign(actions,handlers),render:async()=>{},navigate:async page=>{ctx.state.page=page;},notify(){},refreshProject:async()=>{},setArtifact:async()=>{},api:{call:async(op,p)=>{calls.push([op,p]);return model;}},run:async(op,p)=>{calls.push([op,p]);if(op==='games.plan')return new Promise(resolve=>lateResolve=resolve);return {artifact_id:'new'};}};
const html=await gameEdits(ctx);
assert.match(html,/Starting spare lives/);assert.match(html,/0x1C836/i);assert.doesNotMatch(html,/data-action="game-apply"/,'a fresh field must not offer Create build before review');
const work=actions['game-review']();ctx.state.artifact={artifact_id:'b',sha256:'other'};lateResolve({plan_id:'old',profile_id:profile.id,preview:[],edits:[]});await work;
assert.equal(ctx.state.gameEditPlan,undefined,'late planning cannot attach to a different selection');
ctx.state.artifact={artifact_id:'a',sha256:'sha'};actions={};await gameEdits(ctx);
ctx.run=async(op,p)=>{calls.push([op,p]);return {plan_id:'plan',profile_id:profile.id,build_name:'9 spare lives',preview:[{label:'Starting spare lives',before:3,after:9}],edits:[{offset:116790,before:'04',after:'0a'}],additional_changes:[]};};
await actions['game-review']();const reviewed=await gameEdits(ctx);assert.match(reviewed,/data-action="game-apply"/);assert.match(reviewed,/04/);assert.match(reviewed,/0A/i);
values['game-spare_lives']='8';await assert.rejects(actions['game-apply'](),/changed.*review/i);assert.equal(calls.filter(([op])=>op==='build.apply').length,0);
values['game-spare_lives']='9';await actions['game-view-bytes']({dataset:{id:'116790'}});assert.equal(ctx.state.resourceJump,116790);assert.equal(ctx.state.page,'resources');
console.log('Verified game edits require review, guard selection/field races, and navigate to exact hex offsets.');
ctx.state.artifact={artifact_id:'a',sha256:'sha'};
const notes=await gameByteNotes(ctx,{offset:116790,length:256});
assert.match(notes,/Unsigned 8-bit counter/);assert.match(notes,/04 = 3 spare lives/);assert.match(notes,/Native HUD observed/);
const outside=await gameByteNotes(ctx,{offset:0,length:256});assert.doesNotMatch(outside,/Includes the current life/,'known meanings must not label unrelated bytes');
ctx.api.call=async()=>({profile:null,status:'UNSUPPORTED'});
const unknown=await gameByteNotes(ctx,{offset:116790,length:256});assert.doesNotMatch(unknown,/Includes the current life/);assert.match(unknown,/No verified game meaning/);
console.log('Byte references show storage and observed meaning only at the matched locations.');

// Keep a slow request from replacing newer input or selecting an older build.
const plan={plan_id:'race-plan',profile_id:profile.id,build_name:'9 spare lives',preview:[{label:'Starting spare lives',before:3,after:9}],edits:[],additional_changes:[]};
function resetRace(){
 actions={};values['game-spare_lives']='9';ctx.state.gameEditPlan=null;
 ctx.api.call=async()=>model;ctx.setArtifact=async id=>{calls.push(['selected',id]);};
 ctx.refreshProject=async()=>{};ctx.render=async()=>{};calls=[];
}
resetRace();await gameEdits(ctx);
ctx.run=async()=>new Promise(resolve=>lateResolve=resolve);
const lateReview=actions['game-review']();values['game-spare_lives']='10';lateResolve(plan);await lateReview;
assert.equal(ctx.state.gameEditPlan,null,'a late review must not approve superseded field values');

for(const existing of [false,true])for(const change of ['newer-input','invalid-input','newer-review','during-refresh','unchanged']){
 resetRace();ctx.state.gameEditPlan={scope:selectionKey(ctx.state),values:{spare_lives:9},result:existing?{...plan,existing_build_id:'existing'}:plan};
 await gameEdits(ctx);
 let newer;
 const edit=()=>{values['game-spare_lives']=change==='invalid-input'?'':'10';ctx.state.gameEditPlan=change==='newer-review'?(newer={scope:selectionKey(ctx.state),values:{spare_lives:10},result:{...plan,plan_id:'newer-plan'}}):null;};
 if(change==='during-refresh')ctx.refreshProject=async()=>edit();
 if(existing)ctx.api.call=async()=>new Promise(resolve=>lateResolve=resolve);
 else ctx.run=async()=>new Promise(resolve=>lateResolve=resolve);
 const lateBuild=actions['game-apply']();
 if(!['during-refresh','unchanged'].includes(change))edit();
 lateResolve(existing?model:{artifact_id:'new'});await lateBuild;
 assert.equal(calls.filter(([op])=>op==='selected').length,change==='unchanged'?1:0,'late '+(existing?'history lookup':'build')+' must preserve '+change);
 if(change==='newer-review')assert.equal(ctx.state.gameEditPlan,newer,'a newer review must not be cleared');
 if(change==='unchanged')assert.equal(calls.find(([op])=>op==='selected')[1],existing?'existing':'new');
}
console.log('Slow reviews and build results preserve newer game edits.');

{
 const actions={},drafts=new Map([['asset-schema','{"id":"old-declaration"}']]),schema={id:'verified-graphics',source:{sha256:'sha'}},inspection={document_id:'new-doc',bitmaps:[{id:'tiles'}]},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'},results:{},paint:{pixels:[1]},candidateReview:{artifact_id:'a'},pending:{plan_id:'old'}};
 const model={profile:{id:'rastan-sms',scope:'Checked pose',reference:'/user-guide/index.html#rastan-blobs'},fields:[],locations:[],resources:[{id:'first-enemy-sprites',name:'first enemy sprites',scope:'Checked pose',kind:'assets'}]};
 const ctx={state,sourceParams:()=>({project_id:'p',artifact_id:'a'}),use:h=>Object.assign(actions,h),draft:(k,v)=>drafts.get(k)??v,setDraft:(k,v)=>drafts.set(k,v),api:{call:async()=>model},run:async()=>({resource_kind:'assets',schema,inspection,sprite_layout:{first:0,columns:2,rows:4,order:'rows',indices:[30,32,31,33,52,54,53,55]}}),refreshProject:async()=>{},navigate:async page=>state.page=page,render:async()=>{}};
 await gameEdits(ctx);await actions['game-resource']({dataset:{id:'first-enemy-sprites'}});
 assert.deepEqual(JSON.parse(drafts.get('asset-schema')),schema);assert.equal(state.candidateReview,null);assert.equal(state.paint,null);assert.equal(state.pending,null);assert.equal(state.results['assets.inspect'],inspection);assert.equal(state.page,'assets');
 console.log('Opening verified enemy graphics replaces a stale schema and candidate state before review.');
}
