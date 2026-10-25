import assert from 'node:assert/strict';
const resetCtx={state:{project:{project_id:'reset'},artifact:{artifact_id:'a',sha256:'s'}}};
const resetDoc={document_id:'reset-doc'};
// A restored field draft invalidates the live pixel-history cache.
const {historyFor:resetHistory}=await import('../romancer/ui/pixel_history.js');
resetHistory(resetCtx,resetDoc,'tiles',0,[0]);resetCtx.state.pixelHistories=null;
assert.doesNotThrow(()=>resetHistory(resetCtx,resetDoc,'tiles',0,[1]));
assert.deepEqual(resetHistory(resetCtx,resetDoc,'tiles',0,[1]).current,[1]);
import {PixelHistory,historyFor} from '../romancer/ui/pixel_history.js';
const h=new PixelHistory('cell',[0,0,0,0],2);h.begin([0,0,0,0]);h.commit([1,1,0,0]);assert.deepEqual(h.undo(),[0,0,0,0]);assert.deepEqual(h.redo(),[1,1,0,0]);
h.begin([1,1,0,0]);h.commit([2,1,0,0]);h.begin([2,1,0,0]);h.commit([3,1,0,0]);assert.deepEqual(h.undo(),[2,1,0,0]);assert.deepEqual(h.undo(),[1,1,0,0]);assert.equal(h.canUndo,false);
h.begin([1,1,0,0]);h.commit([0,1,0,0]);assert.equal(h.canRedo,false);
const ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'}}},doc={document_id:'d'};
const first=historyFor(ctx,doc,'tiles',0,[0]);first.begin([0]);first.commit([1]);assert.equal(historyFor(ctx,doc,'tiles',1,[0]).canUndo,false);assert.equal(historyFor(ctx,doc,'tiles',0,[1]).canUndo,true);
ctx.state.artifact.sha256='new';assert.equal(historyFor(ctx,doc,'tiles',0,[0]).canUndo,false);

for(let tile=0;tile<200;tile++){const item=historyFor(ctx,doc,'tiles',tile,[0]);item.begin([0]);item.commit([1]);}
assert.ok(ctx.state.pixelHistories.size<=32,'Visiting many tiles must not retain every undo stack.');
assert.equal(historyFor(ctx,doc,'tiles',199,[1]).canUndo,true,'Recently edited cells retain undo.');
assert.equal(historyFor(ctx,doc,'tiles',0,[1]).canUndo,false,'Evicted undo history must not invent an older pixel buffer.');
console.log('Pixel strokes undo as a unit, retain bounded history, and stay scoped to their cell and source.');
const {mountTools}=await import('../romancer/ui/asset_controls.js');
const handlers=new Map(),canvas={style:{},setAttribute(){},addEventListener:(name,handler)=>handlers.set(name,handler)},undo={disabled:true},redo={disabled:true};
globalThis.document={getElementById:id=>id==='paint-canvas'?canvas:id==='paint-color'?{value:'1'}:id==='asset-changes'?{value:'[]'}:null,querySelector:selector=>selector.includes('pixel-undo')?undo:selector.includes('pixel-redo')?redo:null};
const keyboardCtx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'}},draft:(_k,f)=>f,setDraft(){},notify(){}};
const bitmap={id:'tiles',width:2,height:2,codec:'mono-row-msb-v1',cells:[{pixels:[0,0,0,0]}]},keyboardDoc={document_id:'keyboard',bitmaps:[bitmap],tilemaps:[],palettes:[]};
mountTools(keyboardCtx,keyboardDoc,bitmap,()=>{});handlers.get('keydown')({key:' ',preventDefault(){}});assert.equal(undo.disabled,false,'Keyboard painting must immediately enable undo without another render.');
const imported=[{kind:'cell',bitmap_id:'tiles',cell_index:0,before_pixels:[0,0,0,0],after_pixels:[1,1,1,1]}];
keyboardCtx.state.paint=null;keyboardCtx.state.pixelHistoryScope=null;keyboardCtx.draft=(k,f)=>k==='asset-changes'?JSON.stringify(imported):f;
const importedHistory=historyFor(keyboardCtx,keyboardDoc,'tiles',0,[0,0,0,0]);importedHistory.begin([0,0,0,0]);importedHistory.commit([1,1,1,1]);
globalThis.document.getElementById=id=>id==='paint-canvas'?canvas:id==='paint-color'?{value:'0'}:id==='asset-changes'?{value:JSON.stringify(imported)}:null;
mountTools(keyboardCtx,keyboardDoc,bitmap,()=>{});handlers.get('keydown')({key:' ',preventDefault(){}});
assert.deepEqual(keyboardCtx.state.paint.pixels,[0,1,1,1],'Keyboard paint must preserve the remaining imported pixels.');
assert.deepEqual(historyFor(keyboardCtx,keyboardDoc,'tiles',0,keyboardCtx.state.paint.pixels).undo(),[1,1,1,1],'Undo restores the imported image.');

const {mount:mountAssets}=await import('../romancer/ui/views/assets.js');
const previewStatus={innerHTML:''};const priorGet=globalThis.document.getElementById;globalThis.document.getElementById=id=>id==='pixel-edit-status'?previewStatus:priorGet(id);
let displayed;canvas.getContext=()=>({createImageData:()=>({data:new Uint8ClampedArray(16)}),putImageData:image=>displayed=Array.from(image.data)});
globalThis.document.querySelectorAll=()=>[];keyboardCtx.state.paint=null;keyboardCtx.state.results={'assets.inspect':{...keyboardDoc,ok:true}};
mountAssets(keyboardCtx);assert.deepEqual(displayed,[234,234,234,255,234,234,234,255,234,234,234,255,234,234,234,255],'Main preview must show staged imported pixels before a new stroke.');

assert.match(previewStatus.innerHTML,/Staged/,'Imported edits must not be labeled saved.');
