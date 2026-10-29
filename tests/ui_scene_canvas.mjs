import assert from 'node:assert/strict';
import {projectPoint,inverseAtZ,cellAtZ,sortNodes,pickNodes,sceneNodes,sceneBounds} from '../romancer/ui/scene_canvas.js';
import {LevelDraft,moveLevelObject} from '../romancer/ui/level_canvas.js';

const scene={projection:'isometric',tile_width:32,tile_height:16,elevation_step:8,object_fields:{z:'z',layer:null,order:null}};
assert.deepEqual(projectPoint(scene,{x:3,y:1,z:2}),{x:32,y:16});
assert.deepEqual(projectPoint(scene,{x:-2,y:3,z:1}),{x:-80,y:0});
const camera={offset_x:100,offset_y:50,zoom:2};
assert.deepEqual(projectPoint(scene,{x:3,y:1,z:2},camera),{x:164,y:82});
assert.deepEqual(inverseAtZ(scene,{x:164,y:82},2,camera),{x:3,y:1,z:2});
assert.deepEqual(inverseAtZ(scene,{x:32,y:16},0),{x:2,y:0,z:0});
assert.throws(()=>inverseAtZ(scene,{x:32,y:16},null));
assert.equal(cellAtZ(scene,{x:0,y:-.1},0,{width:3,height:2}),null);
assert.equal(cellAtZ(scene,projectPoint(scene,{x:3,y:0,z:0}),0,{width:3,height:2}),null);
assert.deepEqual(cellAtZ(scene,projectPoint(scene,{x:2.5,y:1.5,z:2}),2,{width:3,height:2}),{x:2,y:1,index:5});
for(const value of [NaN,Infinity,true])assert.throws(()=>projectPoint(scene,{x:value,y:0,z:0}));
assert.throws(()=>projectPoint(scene,{x:0,y:0,z:0},{offset_x:0,offset_y:0,zoom:0}));
const nodes=[{kind:'terrain',index:2,x:1,y:1,z:0,width:1,height:1,layer:0,order:0},
 {kind:'object',index:10,x:1,y:1,z:0,width:1,height:1,layer:1,order:0},
 {kind:'object',index:2,x:1,y:1,z:0,width:1,height:1,layer:1,order:0}];
assert.deepEqual(sortNodes(scene,nodes).map(n=>n.index),[2,2,10]);
assert.deepEqual(pickNodes(scene,nodes,projectPoint(scene,{x:1.5,y:1.5,z:0})).map(n=>n.index),[10,2,2]);
assert.equal(nodes[0].kind,'terrain','sorting does not mutate inspected nodes');
const doc={source_sha256:'a'.repeat(64),document_id:'b'.repeat(64),scene,
 tiles:[Array(64).fill(0)],palette:[[0,0,0]],block_width:1,block_height:1,metatiles:[[0]],
 definition:{rooms:[{id:'r',objects:{fields:[{name:'x',maximum:2},{name:'y',maximum:1},{name:'z',maximum:8}]}}]},
 rooms:[{id:'r',width:3,height:2,terrain:[0,0,0,0,0,0],elevation:[0,1,0,2,0,1],collision:null,objects:[{x:1,y:0,z:2}]}]};
const model=new LevelDraft(doc),before=sceneNodes(doc,model,'r'),selected=before.find(n=>n.kind==='object').key;
assert.equal(before.find(n=>n.kind==='terrain'&&n.index===3).z,2);
assert.equal(before.find(n=>n.kind==='object').z,2);
model.begin();moveLevelObject(model,'r',0,2,1);model.paint('r','elevation',0,3);model.commit();
assert.equal(sceneNodes(doc,model,'r').find(n=>n.kind==='object').key,selected,'selection identity survives movement');
model.undo();assert.equal(model.cells('r','elevation')[0],0);assert.equal(model.objects('r')[0].x,1);
model.redo();assert.equal(model.cells('r','elevation')[0],3);assert.equal(model.objects('r')[0].x,2);
const bounds=sceneBounds(scene,sceneNodes(doc,model,'r'));assert(bounds.width>0&&bounds.height>0);
const many=Array.from({length:16384},(_,index)=>({kind:'terrain',index,x:index%128,y:Math.floor(index/128),z:0,width:1,height:1,layer:0,order:0}));
const small={...scene,tile_width:8,tile_height:4};assert.deepEqual(sceneBounds(small,many),{width:1152,height:640,offset_x:576,offset_y:64,zoom:1});
const undeclared={...doc,scene:{...scene,object_fields:{z:null,layer:null,order:null}}};
assert.equal(sceneNodes(undeclared,model,'r').find(n=>n.kind==='object').z,0,'a field called z is not inferred');
const {render}=await import('../romancer/ui/views/levels.js');
const drafts=new Map([['level-layer','elevation']]),uiDoc={...doc,ok:true,uses:{'0':[]},rooms:doc.rooms.map(r=>({...r,name:'Projected room'}))};
const ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:doc.source_sha256,name:'Original projection fixture'},results:{'levels.inspect':uiDoc}},use:()=>{},draft:(k,v)=>drafts.get(k)??v,setDraft:(k,v)=>drafts.set(k,v),sourceParams:()=>({project_id:'p',artifact_id:'a'}),projectParams:()=>({project_id:'p'}),run:async()=>{},render:async()=>{}};
const markup=await render(ctx);assert.match(markup,/Elevation/);assert.match(markup,/isometric/i);assert.match(markup,/Height value/);
assert.doesNotMatch(markup,/Starting hitbox/,'projected scenes must not advertise an unimplemented hitbox overlay');
const {selectableSceneObjects}=await import('../romancer/ui/scene_canvas.js');
assert.deepEqual(selectableSceneObjects(doc,model,'r','objects'),[],'unnamed raw slots stay in Advanced');
assert.deepEqual(selectableSceneObjects(doc,model,'r','records').map(n=>n.index),[0]);
const {roomThumbnail}=await import('../romancer/ui/room_navigation.js');
const flatIso={...doc,definition:{...doc.definition,scene},rooms:doc.rooms.map(r=>({...r,elevation:null,objects:[]}))},thumbnail=roomThumbnail(flatIso,new LevelDraft(flatIso),'r');
assert.deepEqual([thumbnail.width,thumbnail.height],[80,40],'room cards use the declared projection too');
const {snapCoordinate}=await import('../romancer/ui/scene_geometry.js');
assert.equal(snapCoordinate(1-Number.EPSILON),1,'floating-point projection must not shift a dragged object by one cell');
assert.equal(snapCoordinate(-.6),-1);assert.equal(snapCoordinate(1.99),2);
const {mountLevel}=await import('../romancer/ui/level_canvas.js');
function fakeNode(value=''){
 const graphics={fillRect(){},strokeRect(){},fillText(){},beginPath(){},lineTo(){},moveTo(){},closePath(){},fill(){},stroke(){},save(){},restore(){},setTransform(){},drawImage(){},createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){},getImageData:(x,y,w,h)=>({data:new Uint8ClampedArray(w*h*4)})};
 return {value,style:{},events:{},parentElement:{clientWidth:600},getContext:()=>graphics,addEventListener(name,fn){this.events[name]=fn;},focus(){},setPointerCapture(){},getBoundingClientRect(){return {left:0,top:0,width:this.width,height:this.height};}};
}
const editorNodes=Object.fromEntries(['level-canvas','level-original','level-position','level-difference-count'].map(k=>[k,fakeNode()]));
for(const [k,v] of [['level-layer','elevation'],['level-brush','1'],['level-tool','paint'],['level-overlay','objects'],['level-zoom','1']])editorNodes[k]=fakeNode(v);
globalThis.document={getElementById:id=>editorNodes[id]||null,querySelectorAll:()=>[],createElement:()=>fakeNode()};globalThis.window={innerHeight:1000};
const mountedDoc={...doc,definition:{...doc.definition,scene}},mountedModel=new LevelDraft(mountedDoc),mountedState={page:'levels',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:doc.source_sha256},levelEditor:mountedModel};
let rerenders=0,saves=0;const mountedCtx={state:mountedState,setDraft(){},render(){rerenders++;},notify(message){throw Error(message);}};
mountLevel(mountedCtx,mountedDoc,mountedModel,'r',()=>saves++);
const canvas=editorNodes['level-canvas'],pointer={clientX:128,clientY:96,pointerId:1,button:0,preventDefault(){}};
canvas.events.pointerdown(pointer);canvas.events.pointerup({...pointer,type:'pointerup'});assert.equal(mountedModel.past.length,1);assert.equal(saves,1);assert.equal(rerenders,1,'committing a projected stroke refreshes Undo and build controls');
mountedModel.undo();canvas.events.keydown({key:'ArrowLeft',preventDefault(){}});canvas.events.keydown({key:' ',preventDefault(){}});assert.equal(rerenders,2,'keyboard painting also updates the review controls');
delete editorNodes['level-canvas'];assert.doesNotThrow(()=>canvas.events.keydown({key:' ',preventDefault(){}}),'detached scene controls cannot edit another selection');
editorNodes['level-canvas']=canvas;mountedModel.restore('[]');mountedModel.past=[];mountedModel.future=[];
editorNodes['level-tool'].value='pick';const beforePick=saves;mountLevel(mountedCtx,mountedDoc,mountedModel,'r',()=>saves++);
canvas.events.pointerdown(pointer);canvas.events.pointerup({...pointer,type:'pointerup'});assert.equal(saves,beforePick,'picking must not invalidate a reviewed build');
canvas.events.keydown({key:' ',preventDefault(){}});assert.equal(saves,beforePick,'keyboard picking must not invalidate a reviewed build either');
editorNodes['level-tool'].value='paste';mountedCtx.state.levelClipboard={width:1,height:1,values:[3]};mountLevel(mountedCtx,mountedDoc,mountedModel,'r',()=>saves++);
const pasteStart={...pointer,clientX:80,clientY:72},pasteEnd={...pointer,clientX:96,clientY:96};canvas.events.pointerdown(pasteStart);canvas.events.pointermove(pasteEnd);canvas.events.pointerup({...pasteEnd,type:'pointerup'});assert.equal(mountedModel.values().length,1,'one paste click does not paste repeatedly while the pointer moves');
mountedModel.restore('[]');mountedDoc.rooms[0].object_metadata=[{index:0,name:'Practice actor',role:'actor',reference:null}];editorNodes['level-tool'].value='objects';editorNodes['level-overlay'].value='none';editorNodes['level-object-index']=fakeNode('0');
mountLevel(mountedCtx,mountedDoc,mountedModel,'r',()=>saves++);assert.doesNotThrow(()=>canvas.events.pointerdown({...pointer,clientX:112,clientY:72}),'Move object keeps named markers selectable with overlays disabled');canvas.events.pointercancel({...pointer,type:'pointercancel'});
console.log('Scene projection, known-height inverse, half-open picking, overlap order and stable source identities verified.');
