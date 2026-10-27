import assert from 'node:assert/strict';
import fs from 'node:fs';
import {report} from '../romancer/ui/common.js';
assert.match(report({ok:true,details:'Scrollable diagnostic'},'Details'),/<pre[^>]*tabindex="0"/);
const target=new URL('../romancer/ui/research_tools.js',import.meta.url);
assert.ok(fs.existsSync(target),'Research browser and reviewed pack controls are missing.');
const {researchTools,useResearchSetup,researchNoteHelp}=await import(target);
assert.equal(typeof useResearchSetup,'function');
assert.equal(typeof researchNoteHelp,'function');
const values={};
globalThis.document={getElementById:id=>({value:values[id]??'',checked:values[id]===true,files:[]})};
function fixture(){
 const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',size:10000},results:{}},actions={},calls=[];
 const model={ok:true,artifact_id:'a',source_sha256:'sha',revision:'rev',resources:[{name:'<img src=x>',kind:'assets',offset:16,length:32,editor:'assets'}],notes:[{id:'1'.repeat(32),title:'<script>bad</script>',offset:16,length:32,category:'graphics',text:'User theory',reference:'source'}],resources_total:1,notes_total:1,page:0,limit:50,issues:[]};
 const ctx={state,use:handlers=>Object.assign(actions,handlers),draft:(k,d)=>values[k]??d,setDraft:(k,v)=>values[k]=v,
  sourceParams:()=>({project_id:'p',artifact_id:state.artifact.artifact_id}),api:{call:async op=>op.startsWith('drafts.')?{ok:true,revision:0,value:null}:model},render:async()=>{},notify(){},navigate:async view=>calls.push(['navigate',view]),
  run:async(op,params)=>{calls.push([op,params]);return op==='research.preview'?{ok:true,artifact_id:'a',source_sha256:'sha',review_id:'review',definitions:['assets'],note_count:1,replacements:['assets definition'],notes:[]}:model;}};
 return {state,actions,calls,model,ctx};
}
{
 const {ctx,state,actions}=fixture();state.artifact.descriptors={assets:{source:{sha256:'sha'},bitmaps:[]}};
 state.researchOpen={scope:'p:a:sha',kind:'assets'};values['asset-schema']='{"old":"unsaved"}';
 const review=useResearchSetup(ctx,'assets');assert.match(review,/Load saved/);
 assert.equal(values['asset-schema'],'{"old":"unsaved"}');
 await actions['research-keep-setup']();assert.equal(values['asset-schema'],'{"old":"unsaved"}');
 state.researchOpen={scope:'p:a:sha',kind:'assets'};useResearchSetup(ctx,'assets');
 await actions['research-load-setup']();useResearchSetup(ctx,'assets');
 assert.equal(JSON.parse(values['asset-schema']).source.sha256,'sha');
 assert.match(values['research-previous-setup'],/unsaved/);
 await actions['research-restore-setup']();assert.equal(values['asset-schema'],'{"old":"unsaved"}');
 delete values['asset-schema'];delete values['research-previous-setup'];
}
{
 const {ctx,state,actions}=fixture();state.page='assets';state.artifact.descriptors={assets:{source:{sha256:'sha'},bitmaps:[]}};
 state.researchOpen={scope:'p:a:sha',kind:'assets'};values['asset-schema']='{"newer":"draft"}';
 useResearchSetup(ctx,'assets');let finish;ctx.api.call=op=>op==='drafts.save'?new Promise(resolve=>finish=resolve):Promise.resolve({revision:0});
 const loading=actions['research-load-setup']();await Promise.resolve();state.page='settings';finish({ok:true});await loading;
 assert.equal(state.researchOpen.confirmed,undefined);assert.equal(values['research-previous-setup'],undefined);
 assert.equal(values['asset-schema'],'{"newer":"draft"}');delete values['asset-schema'];
}
{
 const {ctx,actions,calls}=fixture();const html=await researchTools(ctx);
 assert.match(html,/Resource browser/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>bad/);
 await actions['research-bytes']({dataset:{id:'16'}});assert.equal(ctx.state.resourceJump,16);
 assert.deepEqual(calls.at(-1),['navigate','resources']);
 await actions['research-editor']({dataset:{id:'assets'}});assert.deepEqual(calls.at(-1),['navigate','assets']);
}
{
 const {ctx,state,actions,calls}=fixture();await researchTools(ctx);state.researchImport={scope:'p:a:sha',document:{format:'pack'},review:{ok:true,artifact_id:'a',source_sha256:'sha',review_id:'review',definitions:['assets'],note_count:1,replacements:['assets definition'],notes:[]}};
 await researchTools(ctx);values['research-replace']=false;
 await assert.rejects(actions['research-apply'](),/replacement/i);
 values['research-replace']=true;await actions['research-apply']();
 const apply=calls.find(c=>c[0]==='research.apply');assert.equal(apply[1].review_id,'review');assert.equal(apply[1].replace,true);
}
{
 const {ctx,state}=fixture();let finish;ctx.api.call=()=>new Promise(resolve=>finish=resolve);
 const pending=researchTools(ctx);state.artifact={artifact_id:'new',sha256:'different',size:100};finish({ok:true,artifact_id:'a',source_sha256:'sha',resources:[],notes:[],issues:[]});
 assert.equal(await pending,'');assert.equal(state.researchBrowser,undefined);
}
console.log('Research UI escapes user text, navigates exact resources, requires reviewed replacements and ignores late old-source responses.');
