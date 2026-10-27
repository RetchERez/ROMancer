import assert from 'node:assert/strict';
import {objectWorkbench,openObject,mountObjectWorkbench} from '../romancer/ui/object_workbench.js';
const actions={},calls=[],state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s',object_layouts:{objects:[{}]}},results:{},paint:null},ctx={state,use:r=>Object.assign(actions,r),sourceParams:()=>({project_id:'p',artifact_id:'a'}),api:{call:async(op,p)=>{calls.push([op,p]);if(op==='objects.list')return {objects:[{object_id:'o',name:'Enemy',columns:2,rows:1,parts:2}]};if(op==='objects.get')return {object_id:'o',source_dependency_verified:true,object:{name:'Enemy',trace_id:'t',definition:{scene_region:{x:0,y:0,width:16,height:8},layout:{indices:[0,0],columns:2,rows:1}},parts:[]}};if(op==='traces.get')return {crop_png_base64:'picture',region:{x:0,y:0,width:16,height:8},frame:{sha256:'f'}};}},run:async(op,p)=>{calls.push([op,p]);return {object_id:'o',object_name:'Enemy',layout:{indices:[0,0]},inspection:{document_id:'d'}}},navigate:async id=>{calls.push(['navigate',id]);},isCurrentRender:()=>true};
let html=await objectWorkbench(ctx,{document_id:'d'},null);assert.match(html,/Saved objects/);assert(actions['object-open']);
await openObject(ctx,'o');assert.equal(state.connectedAssetSetup.result.object_id,'o');assert.equal(calls.at(-1)[1],'assets');
state.objectWorkbench={scope:'p:a:s',object_id:'o',document_id:'d'};
// Match the real selection key; changing the selected ROM must invalidate old actions.
const {selectionKey}=await import('../romancer/ui/tool_inputs.js');state.objectWorkbench.scope=selectionKey(state);
html=await objectWorkbench(ctx,{document_id:'d'},{width:8,height:8,count:1,codec:'tile8-planar2-msb-v1'});assert.match(html,/Captured scene/);assert.match(html,/Shared/);assert.match(html,/Enemy/);const oldOpen=actions['object-open'];state.artifact={artifact_id:'other',sha256:'z'};const count=calls.length;assert.throws(()=>oldOpen({dataset:{id:'o'}}),/changed|selection/i);assert.equal(calls.length,count);
console.log('Connected object workspace retains the captured scene, source uses and guarded exact-source editor handoff.');

const {spriteAssembly}=await import('../romancer/ui/sprite_assembly.js');
state.artifact={artifact_id:'a',sha256:'s'};state.objectWorkbench={scope:selectionKey(state)};
const doc={ok:true,document_id:'d'},bitmap={id:'b',codec:'tile8-planar2-msb-v1',count:1,width:8,height:8,cells:[{pixels:Array(64).fill(1)}]};
ctx.draft=(id,fallback)=>id==='sprite-layout'?JSON.stringify({document_id:'d',bitmap_id:'b',first:0,columns:2,rows:1,indices:[0,0],flips:[0,0],provenance:'causal_replay'}):fallback;
html=spriteAssembly(ctx,doc,bitmap);
assert.match(html,/<details class="object-layout-advanced"><summary>/,'Saved objects keep layout setup collapsed so the captured scene and editing preview can fit together.');

let loaded,drawn=0;
globalThis.Image=class {constructor(){loaded=this;this.naturalWidth=32;this.naturalHeight=16;}};
const full={isConnected:true,dataset:{preview:'iVBORw0KGgo='},getContext:()=>({drawImage:()=>drawn++,strokeRect:()=>{}})};
globalThis.document={getElementById:id=>id==='object-scene-full'?full:null};
state.objectWorkbench.preview={scene_region:{x:0,y:0,width:8,height:8}};
mountObjectWorkbench(ctx);
assert.match(loaded.src,/^data:image\/png;base64,/,'A scene PNG must be loaded as image data, not an invalid relative URL.');
loaded.onload();assert.equal(drawn,1);assert.equal(full.width,32);assert.equal(full.height,16);
