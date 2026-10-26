import assert from 'node:assert/strict';
import {LevelDraft,mountLevel,levelBrushPalette} from '../romancer/ui/level_canvas.js';
import {render} from '../romancer/ui/views/levels.js';

const doc={ok:true,document_id:'synthetic',source_sha256:'sha',uses:{},tiles:[Array(64).fill(0),Array(64).fill(1)],palette:[[10,20,30],[200,210,220]],block_width:1,block_height:1,metatiles:[[0],[1]],rooms:[{id:'room',name:'Practice',width:3,height:2,terrain:[0,1,0,0,0,0],collision:[0,3,0,0,0,0],objects:[{kind:0,x:0,y:0}]}]};
function node(value=''){
 const graphics={fillRect(){this.markers=(this.markers||0)+1;},strokeRect(){},fillText(){},createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(picture){this.last=picture;}};
 return {value,style:{},attrs:{},events:{},parentElement:{clientWidth:600},getContext:()=>graphics,graphics,addEventListener(name,fn){this.events[name]=fn;},setAttribute(name,value){this.attrs[name]=value;},focus(){},setPointerCapture(){},getBoundingClientRect:()=>({left:0,top:0,width:240,height:160})};
}
const nodes=Object.fromEntries(['level-canvas','level-position','level-difference-count'].map(name=>[name,node()]));
for(const [name,value] of [['level-overlay','none'],['level-zoom','1'],['level-tool','objects'],['level-layer','terrain'],['level-brush','0']])nodes[name]=node(value);
const brushes=[0,1].map(index=>{const b=node();b.dataset={levelBrush:String(index)};b.thumb=node();b.querySelector=()=>b.thumb;return b;});
globalThis.document={getElementById:name=>nodes[name]||null,querySelectorAll:()=>brushes};globalThis.window={innerHeight:800};
const model=new LevelDraft(doc),drafts=new Map(),state={page:'levels',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'},results:{}};
let persisted=0,renders=0;const ctx={state,setDraft:(name,value)=>drafts.set(name,value),render:()=>renders++,notify:message=>{throw Error(message);}};
mountLevel(ctx,doc,model,'room',()=>persisted++);
assert.ok(nodes['level-canvas'].graphics.markers>0,'kind zero is still an object marker when semantics are unknown');
const event=(clientX,clientY)=>({pointerId:1,button:0,clientX,clientY,preventDefault(){}}),canvas=nodes['level-canvas'];
canvas.events.pointerdown(event(5,5));canvas.events.pointermove(event(200,100));canvas.events.pointerup(event(200,100));
assert.deepEqual(model.objects('room')[0],{kind:0,x:2,y:1});assert.equal(model.past.length,1);assert.equal(persisted,1);
model.undo();assert.deepEqual(model.objects('room')[0],doc.rooms[0].objects[0]);
canvas.events.pointerdown(event(5,5));canvas.events.pointermove(event(200,100));canvas.events.pointercancel();
assert.deepEqual(model.objects('room')[0],doc.rooms[0].objects[0],'cancel restores both coordinates');assert.equal(model.past.length,0);
nodes['level-tool'].value='pick';canvas.events.pointerdown(event(100,5));canvas.events.pointerup(event(100,5));
assert.equal(nodes['level-brush'].value,'1');assert.equal(drafts.get('level-brush'),'1');assert.equal(model.values().length,0,'picking stages no room changes');assert.equal(persisted,1);
nodes['level-layer'].value='collision';canvas.events.pointerdown(event(100,5));canvas.events.pointerup(event(100,5));assert.equal(nodes['level-brush'].value,'3','pick preserves raw collision value without naming it');
brushes[1].events.click();assert.equal(nodes['level-layer'].value,'terrain');assert.equal(nodes['level-tool'].value,'paint');assert.equal(brushes[1].attrs['aria-pressed'],'true');
assert.deepEqual(Array.from(brushes[1].thumb.graphics.last.data.slice(0,4)),[200,210,220,255]);
canvas.events.pointerdown(event(5,5));canvas.events.pointerup(event(5,5));assert.equal(model.cells('room','terrain')[0],1);
assert.match(levelBrushPalette(doc,model,1),/data-level-brush="1" aria-pressed="true"/);

let calls=0;const controls={},viewCtx={...ctx,state:{...state,results:{'levels.inspect':doc}},draft:(name,fallback)=>fallback,use:actions=>Object.assign(controls,actions),api:{call:async()=>{calls++;return {ok:true,visual:{kind:'rgb555-palettes'},profile:{id:'other-game'}};}},sourceParams:()=>({project_id:'p',artifact_id:'a'})};
const html=await render(viewCtx);assert.equal(calls,0,'declared documents take precedence over named game definitions');assert.match(html,/Pick from room/);assert.match(html,/Move object/);assert.match(html,/Terrain brushes/);assert.match(html,/<details><summary>Advanced brush value/);
viewCtx.state.results={};const other=await render(viewCtx);assert.equal(calls,1);assert.doesNotMatch(other,/Game edits|game-visual-preview/,'Levels never shows unrelated game edits');
const roomVisual={kind:'room-map',size:[2,2],origin:[0,0],tile_size:16,current:[0,0],original:[0,0],stool_down:[0,1],object:{allowed:[[0,0],[0,1]],tile_id:1}};
viewCtx.api.call=async()=>({ok:true,status:'MATCHED',visual:roomVisual,fields:[{id:'room_layout',label:'Stool',type:'choice',value:'original',options:[['original','Original'],['stool_down','Down']]}],profile:{id:'ffl2-usa',name:'Synthetic routing example',scope:'Synthetic room'},locations:[],resources:[]});
const routed=await render(viewCtx);assert.match(routed,/room-edit/);assert.ok(viewCtx.state.levelRoomVisualScope,'exact room visuals select the Levels room mount');assert.equal(viewCtx.state.gameVisualModel.model.visual,roomVisual);
console.log('Visual terrain brushes, picking, bounded object dragging, cancellation, grouped undo, and Levels routing passed.');
