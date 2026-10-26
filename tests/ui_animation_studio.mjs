import assert from 'node:assert/strict';
import {AnimationClock,readAnimation,mountAnimation} from '../romancer/ui/animation_studio.js';
const bitmap={id:'b',count:4,width:8,height:8},doc={document_id:'d'};
const saved={document_id:'d',bitmap_id:'b',frames:[{first:0,columns:2,rows:2,order:'rows',duration:120}]};
assert.equal(readAnimation(doc,bitmap,JSON.stringify(saved)).length,1);
assert.deepEqual(readAnimation({...doc,document_id:'other'},bitmap,JSON.stringify(saved)),[]);
assert.throws(()=>readAnimation(doc,bitmap,JSON.stringify({...saved,frames:[{...saved.frames[0],first:3}]})));
const calls=[],timers=new Map();let counter=0;
const clock=new AnimationClock({set:(fn,ms)=>{const id=++counter;timers.set(id,{fn,ms});return id;},clear:id=>timers.delete(id)});
clock.start([{duration:120},{duration:200}],index=>calls.push(index));assert.deepEqual(calls,[0]);assert.equal(timers.size,1);
const scheduled=[...timers.values()][0];timers.clear();scheduled.fn();assert.deepEqual(calls,[0,1]);assert.equal([...timers.values()][0].ms,200);
clock.stop();clock.stop();assert.equal(timers.size,0);
console.log('Explicit animation frames reject stale/out-of-range layouts and dispose their single playback timer.');

// Animation must preserve the same per-part observed colors as sprite assembly.
const coloredBitmap={id:'colored',count:2,width:1,height:1,codec:'tile8-paired2-msb-v1',cells:[{pixels:[1]},{pixels:[1]}]},coloredDoc={document_id:'colors'};
let frame={first:0,columns:2,rows:1,order:'rows',duration:120,colors:[{'1':[255,0,0]},{'1':[0,0,255]}]},rgba;
const context={createImageData:(width,height)=>({data:new Uint8ClampedArray(width*height*4)}),putImageData:image=>{rgba=[...image.data];}},canvas={style:{},getContext:()=>context,addEventListener(){}};
globalThis.document={getElementById:id=>id==='animation-canvas'?canvas:null};
const ctx={state:{page:'assets',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'}},draft:(key,fallback)=>key==='animation-frames'?JSON.stringify({document_id:'colors',bitmap_id:'colored',frames:[frame]}):fallback};
mountAnimation(ctx,coloredDoc,coloredBitmap,null);assert.deepEqual(rgba,[255,0,0,255,0,0,255,255],'each animation part keeps its observed gameplay colors');
mountAnimation(ctx,coloredDoc,coloredBitmap,{id:'p',colors_per_bank:4,entries:[{bank:0,index:1,rgb:{r:0,g:255,b:0}}]});assert.deepEqual(rgba,[0,255,0,255,0,255,0,255],'declared palette colors take priority over observed colors');
frame={...frame,colors:null};coloredBitmap.cells=[{pixels:[0]},{pixels:[3]}];mountAnimation(ctx,coloredDoc,coloredBitmap,null);assert.deepEqual(rgba,[18,18,18,255,234,234,234,255],'2bpp grayscale spans the same literal index range as sprite assembly');
console.log('Animation colors retain observed per-part RGB, prefer declared palettes, and scale grayscale to the codec depth.');
