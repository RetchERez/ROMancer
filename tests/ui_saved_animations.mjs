import assert from 'node:assert/strict';
import {savedAnimationControls,openSavedAnimation} from '../romancer/ui/saved_animations.js';
import {selectionKey} from '../romancer/ui/tool_inputs.js';
import {render as renderAssets} from '../romancer/ui/views/assets.js';
const actions={},drafts={},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'},results:{}},bitmap={id:'b',count:8,width:8,height:8};
const doc={ok:true,source_sha256:'s',document_id:'d',bitmaps:[bitmap]},frames=[{columns:2,rows:2,indices:[0,1,2,3],flips:[0,0,0,0],duration:120}];drafts['animation-frames']=JSON.stringify({document_id:'d',bitmap_id:'b',frames});
globalThis.document={getElementById:()=>({value:'Walk'})};let opened='';
const ctx={state,use:r=>Object.assign(actions,r),draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,sourceParams:()=>({project_id:'p',artifact_id:'a'}),render:async()=>{},notify:()=>{},navigate:async p=>opened=p,
 api:{call:async op=>op==='animations.list'?{ok:true,source_sha256:'s',artifact_id:'a',animations:[]} :op==='animations.get'?{ok:true,source_sha256:'s',artifact_id:'a',animation:{schema:{},bitmap_id:'b',document_id:'d',frames}}:doc},
 run:async(op,p)=>{assert.ok(['animations.preview','animations.save'].includes(op));return {ok:true,review_id:'r',shared_tiles:[],animation:{frames}};}};
assert.match(await savedAnimationControls(ctx,doc,bitmap),/Save &amp; reuse|Save & reuse/);await actions['animation-preview-save']();await savedAnimationControls(ctx,doc,bitmap);await actions['animation-save-reviewed']();
await openSavedAnimation(ctx,'id');assert.equal(opened,'assets');assert.equal(state.connectedAnimation.scope,selectionKey(state));assert.equal(state.connectedAssetSetup.result.layout.duration,120);
console.log('Saved animation reviews and exact-document reopening preserve arrangements.');
state.page='assets';state.artifact.descriptors={assets:{source:{sha256:'s'}}};drafts['asset-schema']='unfinished graphics declaration';
await openSavedAnimation(ctx,'id');
assert.equal(state.researchOpen?.kind,'assets','Saved animations must pass through graphics setup review.');
assert.match(await renderAssets(ctx),/Keep current draft/);await actions['research-keep-setup']();assert.equal(drafts['asset-schema'],'unfinished graphics declaration');assert.equal(state.connectedAnimation,null);
// A saved layout can belong to a bitmap other than the first one.
const b=(id)=>({id,count:8,width:8,height:8,codec:'tile8-planar2-msb-v1',cells:Array.from({length:8},(_,index)=>({index,pixels:Array(64).fill(0)}))});
const multi={...doc,write_supported:true,bitmaps:[b('first'),b('second')],palettes:[],tilemaps:[],fonts:[]};
ctx.api.call=async op=>op==='animations.get'?{ok:true,source_sha256:'s',artifact_id:'a',animation:{schema:{source:{sha256:'s'}},bitmap_id:'second',document_id:'d',frames}}:op==='assets.inspect'?multi:{ok:true,source_sha256:'s',artifact_id:'a',animations:[]};
delete drafts['asset-schema'];state.results['assets.inspect']=multi;drafts['paint-buffer']=JSON.stringify({document_id:'d',bitmap_id:'first',cell_index:0,pixels:Array(64).fill(1)});drafts['asset-changes']='[]';await openSavedAnimation(ctx,'second-animation');await renderAssets(ctx);
assert.equal(state.assetBitmapId,'second');assert.equal(JSON.parse(drafts['sprite-layout']).bitmap_id,'second');assert.equal(JSON.parse(drafts['animation-frames']).bitmap_id,'second');
assert.equal(JSON.parse(drafts['asset-changes'])[0].bitmap_id,'first','Switching to another animation bitmap preserves prior pixel edits.');
