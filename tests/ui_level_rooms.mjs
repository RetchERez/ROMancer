import assert from 'node:assert/strict';
import test from 'node:test';
import {LevelDraft,changedRoomCells,mountLevel} from '../romancer/ui/level_canvas.js';
import * as rooms from '../romancer/ui/room_navigation.js';
import {render} from '../romancer/ui/views/levels.js';

function documentFixture(){return {ok:true,document_id:'rooms',source_sha256:'sha',uses:{},tiles:[Array(64).fill(0)],palette:[[10,20,30]],block_width:1,block_height:1,metatiles:[[0]],definition:{rooms:[{id:'first',objects:{fields:[{name:'kind',maximum:8},{name:'x',maximum:1},{name:'y',maximum:0},{name:'exit_room',maximum:0}]}}]},rooms:[{id:'first',name:'First',width:4,height:2,terrain:Array(8).fill(0),collision:[4,0,0,0,0,0,0,0],objects:[{kind:1,x:0,y:0,exit_room:0}]},{id:'second',name:'Second',width:4,height:2,terrain:Array(8).fill(0),collision:null,objects:[]}]};}

test('reserved object fields honor both declared maxima and room bounds',()=>{
 const model=new LevelDraft(documentFixture());
 for(const [field,value] of [['x',2],['y',1],['exit_room',1]])assert.throws(()=>model.set({kind:'object',room_id:'first',index:0,field,value}),/bounds/);
});

test('changing a coordinate-free object produces no room cell highlight',()=>{
 const doc=documentFixture();doc.rooms[0].objects=[{kind:1}];const model=new LevelDraft(doc);
 model.set({kind:'object',room_id:'first',index:0,field:'kind',value:2});
 assert.deepEqual(changedRoomCells(doc,model,'first'),[]);
});

test('nonzero collision values remain visible when divisible by four',()=>{
 const fills=[],graphics={fillRect(){fills.push(this.fillStyle);},strokeRect(){},createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){}};
 const canvas={style:{},parentElement:{clientWidth:600},getContext:()=>graphics,addEventListener(){}};
 const values={'level-overlay':'collision','level-tool':'paint','level-layer':'terrain','level-brush':'0','level-zoom':'1'};
 const previousDocument=globalThis.document,previousWindow=globalThis.window;
 try{globalThis.document={getElementById:id=>id==='level-canvas'?canvas:values[id]?{value:values[id],addEventListener(){}}:null,querySelectorAll:()=>[]};globalThis.window={innerHeight:800};
  const doc=documentFixture(),model=new LevelDraft(doc);mountLevel({state:{page:'levels',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'}},setDraft(){},notify(){}},doc,model,'first',()=>{});
  assert.ok(fills.length>0);assert.ok(fills.every(color=>color!=='transparent'),'nonzero collision cells have a visible fill');
 }finally{globalThis.document=previousDocument;globalThis.window=previousWindow;}
});

function connectedDocument(){const doc=documentFixture();doc.definition.rooms[0].objects.fields.at(-1).maximum=1;doc.rooms[0].object_metadata=[{index:0,name:'Garden <gate>',role:'exit',reference:{field:'exit_room',targets:[{value:0,room_id:'first'},{value:1,room_id:'second'}]}}];return doc;}

test('room links are explicit and follow staged destination changes and undo',()=>{
 const legacy=documentFixture();assert.deepEqual(rooms.roomConnections(legacy,new LevelDraft(legacy)),[]);
 const doc=connectedDocument(),model=new LevelDraft(doc);model.begin();model.set({kind:'object',room_id:'first',index:0,field:'exit_room',value:1});model.commit();
 assert.equal(rooms.roomConnections(doc,model)[0].target_room_id,'second');assert.equal(doc.rooms[0].objects[0].exit_room,0);
 model.undo();assert.equal(rooms.roomConnections(doc,model)[0].target_room_id,'first');model.redo();assert.equal(rooms.roomConnections(doc,model)[0].target_room_id,'second');
});

test('frontend also refuses unmapped explicit exit destinations',()=>{
 const doc=connectedDocument();doc.rooms[0].object_metadata[0].reference.targets.pop();
 assert.throws(()=>new LevelDraft(doc).set({kind:'object',room_id:'first',index:0,field:'exit_room',value:1}),/destination/);
});

test('room thumbnails sample staged terrain without allocating a full room canvas',()=>{
 const doc=connectedDocument();doc.tiles.push(Array(64).fill(1));doc.palette.push([200,100,50]);doc.metatiles.push([1]);const model=new LevelDraft(doc);
 model.set({kind:'terrain',room_id:'first',index:0,value:1});
 const picture=rooms.roomThumbnail(doc,model,'first');assert.ok(picture.width<=160&&picture.height<=96);
 assert.deepEqual(Array.from(picture.pixels.slice(0,4)),[200,100,50,255]);
 assert.equal(doc.rooms[0].terrain[0],0);
});

test('named object inspector exposes actual limits, mapped destinations and remaining integer fields',()=>{
 const doc=connectedDocument(),model=new LevelDraft(doc),ctx={draft:(id,fallback)=>fallback};
 const html=rooms.objectInspector(ctx,doc,model,'first');
 assert.match(html,/Garden &lt;gate&gt;/);assert.match(html,/Destination room/);assert.match(html,/<option value="1"[^>]*>Second/);
 assert.match(html,/id="level-object-input-1"[^>]*max="1"/);assert.match(html,/id="level-object-input-2"[^>]*max="0"/);
 assert.match(html,/kind/);assert.doesNotMatch(html,/script|opcode|compile/i);
});

test('room navigation actions validate room IDs and group object fields into one undo step',async()=>{
 const doc=connectedDocument(),drafts=new Map(),actions={},ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',name:'Rooms'},results:{'levels.inspect':doc}},draft:(id,fallback)=>drafts.get(id)??fallback,setDraft:(id,value)=>drafts.set(id,value),use:next=>Object.assign(actions,next),render:async()=>{},sourceParams:()=>({project_id:'p',artifact_id:'a'})};
 const html=await render(ctx);assert.match(html,/Choose a room/);assert.match(html,/data-level-room-preview="first"/);
 await actions['levels-open-room']({dataset:{id:'second'}});assert.equal(drafts.get('level-room'),'second');
 assert.throws(()=>actions['levels-open-room']({dataset:{id:'missing'}}),/room/i);
 await actions['levels-select-object']({dataset:{id:'0',name:'first'}});assert.equal(drafts.get('level-room'),'first');assert.equal(drafts.get('level-object-index'),'0');
 const previous=globalThis.document;try{globalThis.document={getElementById:id=>({value:({'level-object-index':'0','level-object-input-0':'2','level-object-input-1':'1','level-object-input-2':'0','level-object-destination':'1'})[id]})};
  await actions['levels-object-apply']();assert.equal(ctx.state.levelEditor.past.length,1);assert.equal(ctx.state.levelEditor.objects('first')[0].exit_room,1);
  ctx.state.levelEditor.undo();assert.deepEqual(ctx.state.levelEditor.objects('first')[0],doc.rooms[0].objects[0]);
 }finally{globalThis.document=previous;}
});

test('workshop distinguishes editor connections from its native terrain and music preview',async()=>{
 const doc=connectedDocument();doc.definition.name='Hillside editor-layout workshop';
 const ctx={state:{project:{project_id:'p',demo:true},artifact:{artifact_id:'a',sha256:'sha'},results:{'levels.inspect':doc}},draft:(id,fallback)=>fallback,setDraft(){},use(){}};
 const html=await render(ctx);assert.match(html,/Practice layout\. These room links and object records do not run in Playtest; only Hillside terrain and music do\./);
 assert.ok(html.indexOf('Practice layout.')<html.indexOf('data-level-room-preview="first"'));
});

test('unsupported ROM shows a plain availability message and keeps setup and practice collapsed',async()=>{
 const ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'unknown'},results:{}},draft:(id,fallback)=>fallback,setDraft(){},use(){},api:{call:async()=>({ok:true,status:'UNSUPPORTED'})},sourceParams:()=>({})};
 const html=await render(ctx);assert.match(html,/No supported level map for this ROM yet/);assert.match(html,/Investigate bytes/);
 assert.doesNotMatch(html,/<details[^>]*open[^>]*><summary>Advanced level setup/);
 assert.match(html,/<details[^>]*><summary>Advanced practice<\/summary>[\s\S]*data-action="studio-example"[^>]*>Open test layout<\/button>/);
 assert.doesNotMatch(html.slice(0,html.indexOf('<details')),/JSON|Tile count|Blocks across|test layout/i);
 const practice=html.slice(html.indexOf('<summary>Advanced practice</summary>'));assert.equal((html.match(/data-action="studio-example"/g)||[]).length,1);assert.match(practice,/Open test layout/);
});

test('an unusable saved layout also returns the plain availability screen',async()=>{
 const ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'unknown',descriptors:{levels:{source_sha256:'unknown'}}},results:{}},draft:(id,fallback)=>fallback,setDraft(){},use(){},api:{call:async()=>{throw Error('invalid layout definition');}},sourceParams:()=>({})};
 const html=await render(ctx);assert.match(html,/No supported level map for this ROM yet/);assert.match(html,/Investigate bytes/);assert.doesNotMatch(html,/<canvas/);
});

test('empty Levels view starts with importing a ROM and keeps practice secondary',async()=>{
 const html=await render({state:{project:null,artifact:null,results:{}},use(){}});
 assert.match(html,/Choose a project or import a ROM/);assert.match(html,/data-action="import"[^>]*class="primary[^>]*>Import ROM/);
 assert.match(html,/<details[^>]*><summary>Advanced practice<\/summary>/);assert.doesNotMatch(html,/Open design workshop/);
});

test('named object inspector keeps only selection, dragging and destination visible by default',()=>{
 const doc=connectedDocument();doc.rooms[0].objects.push({kind:7,x:1,y:0,exit_room:0});const model=new LevelDraft(doc),ctx={draft:(id,fallback)=>fallback};
 const html=rooms.objectInspector(ctx,doc,model,'first'),advanced=html.indexOf('<details class="level-object-advanced"'),normal=html.slice(0,advanced);
 assert.ok(advanced>=0);assert.match(html.slice(advanced),/<summary>Position & advanced values<\/summary>/);
 assert.match(normal,/Selected object/);assert.match(normal,/Destination room/);assert.match(normal,/drag/i);assert.match(normal,/Update preview/);
 assert.doesNotMatch(normal,/level-object-input-|>kind<|Record 1|Object slot 1/);
 assert.match(html.slice(advanced),/id="level-object-input-0"/);assert.match(html.slice(advanced),/id="level-object-input-1"/);
 assert.equal((html.match(/id="level-object-destination"/g)||[]).length,1);
});

test('default named markers and advanced records use the same visible hit-test filter',()=>{
 const doc=connectedDocument();doc.definition.rooms[0].objects.fields.find(field=>field.name==='y').maximum=1;doc.rooms[0].objects.push({kind:7,x:1,y:1,exit_room:0});const model=new LevelDraft(doc);
 assert.deepEqual(rooms.visibleLevelObjects(doc,model,'first','objects').map(marker=>[marker.index,marker.label]),[[0,'Garden <gate>']]);
 assert.deepEqual(rooms.visibleLevelObjects(doc,model,'first','records').map(marker=>marker.index),[0,1]);
 const captions=[],notices=[],drafts=new Map(),graphics={fillRect(){},strokeRect(){},fillText:text=>captions.push(text),createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){}};
 const canvas={style:{},events:{},parentElement:{clientWidth:600},getContext:()=>graphics,addEventListener(name,fn){this.events[name]=fn;},focus(){},setPointerCapture(){},getBoundingClientRect:()=>({left:0,top:0,width:400,height:200})};
 const values={'level-overlay':'objects','level-tool':'objects','level-layer':'terrain','level-brush':'0','level-zoom':'1'},controls=Object.fromEntries(Object.entries(values).map(([id,value])=>[id,{value,events:{},addEventListener(name,fn){this.events[name]=fn;}}]));
 const previousDocument=globalThis.document,previousWindow=globalThis.window;
 try{globalThis.document={getElementById:id=>id==='level-canvas'?canvas:controls[id]||null,querySelectorAll:()=>[]};globalThis.window={innerHeight:800};
  mountLevel({state:{page:'levels',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'}},setDraft:(id,value)=>drafts.set(id,value),notify:text=>notices.push(text),render(){}},doc,model,'first',()=>{});
  assert.deepEqual(captions,['Exit'],'labels come from the explicit role, never the raw kind integer');const event=x=>({pointerId:1,button:0,clientX:x,clientY:150,preventDefault(){}});
  canvas.events.pointerdown(event(150));assert.equal(drafts.has('level-object-index'),false,'an invisible unnamed record cannot be selected');assert.equal(model.start,null);assert.equal(notices.length,1);
  controls['level-overlay'].value='records';captions.length=0;controls['level-overlay'].events.change();assert.ok(captions.includes('1'));
  canvas.events.pointerdown(event(150));canvas.events.pointerup(event(150));assert.equal(drafts.get('level-object-index'),'1','advanced records can be selected explicitly');
 }finally{globalThis.document=previousDocument;globalThis.window=previousWindow;}
});

test('readable object labels can be dragged from their text without jumping the object',()=>{
 const doc=connectedDocument();doc.block_width=2;doc.block_height=2;doc.metatiles=[[0,0,0,0]];const model=new LevelDraft(doc),drafts=new Map();
 const graphics={fillRect(){},strokeRect(){},fillText(){},createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){}};
 const canvas={style:{},events:{},parentElement:{clientWidth:600},getContext:()=>graphics,addEventListener(name,fn){this.events[name]=fn;},focus(){},setPointerCapture(){},getBoundingClientRect:()=>({left:0,top:0,width:400,height:200})};
 const values={'level-overlay':'objects','level-tool':'objects','level-layer':'terrain','level-brush':'0','level-zoom':'1'},previousDocument=globalThis.document,previousWindow=globalThis.window;
 try{globalThis.document={getElementById:id=>id==='level-canvas'?canvas:values[id]?{value:values[id],addEventListener(){}}:null,querySelectorAll:()=>[]};globalThis.window={innerHeight:800};
  mountLevel({state:{page:'levels',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'}},setDraft:(id,value)=>drafts.set(id,value),notify(){},render(){}},doc,model,'first',()=>{});
  const event=x=>({pointerId:1,button:0,clientX:x,clientY:50,preventDefault(){}});
  canvas.events.pointerdown(event(150));assert.equal(drafts.get('level-object-index'),'0','the label text outside the object cell is still selectable');assert.equal(model.objects('first')[0].x,0);
  canvas.events.pointermove(event(250));canvas.events.pointerup(event(250));assert.equal(model.objects('first')[0].x,1);assert.equal(model.past.length,1);
 }finally{globalThis.document=previousDocument;globalThis.window=previousWindow;}
});

test('legacy layouts expose raw slots only in advanced record mode',()=>{
 const doc=documentFixture(),model=new LevelDraft(doc);
 assert.deepEqual(rooms.visibleLevelObjects(doc,model,'first','objects'),[]);assert.equal(rooms.visibleLevelObjects(doc,model,'first','records').length,1);
 const normal=rooms.objectInspector({draft:(id,fallback)=>fallback},doc,model,'first');assert.match(normal,/No named objects/);assert.doesNotMatch(normal,/id="level-object-input-/);
 const advanced=rooms.objectInspector({draft:(id,fallback)=>id==='level-overlay'?'records':fallback},doc,model,'first');assert.match(advanced,/Record 0/);assert.match(advanced,/id="level-object-input-0"/);assert.doesNotMatch(advanced,/>actor<|>enemy<|>door</i);
});

test('invalid object inspector values roll back the entire staged action',async()=>{
 const doc=connectedDocument(),actions={},ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'},results:{'levels.inspect':doc}},draft:(id,fallback)=>fallback,setDraft(){},use:next=>Object.assign(actions,next),render:async()=>{}};
 await render(ctx);const previous=globalThis.document;
 try{globalThis.document={getElementById:id=>({value:({'level-object-index':'0','level-object-input-0':'2','level-object-input-1':'2','level-object-input-2':'0','level-object-destination':'1'})[id]})};
  assert.throws(()=>actions['levels-object-apply'](),/bounds/);assert.deepEqual(ctx.state.levelEditor.values(),[]);assert.equal(ctx.state.levelEditor.past.length,0);
 }finally{globalThis.document=previous;}
});

test('object inspector shares the main editor layout with both room canvases',async()=>{
 const doc=connectedDocument(),ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'},results:{'levels.inspect':doc}},draft:(id,fallback)=>fallback,setDraft(){},use(){}};
 const html=await render(ctx),layout=html.indexOf('class="level-editor-layout"'),inspector=html.indexOf('class="card level-object-inspector"'),undo=html.indexOf('data-action="levels-undo"'),metatiles=html.indexOf('Metatiles & shared uses');
 assert.ok(layout>=0,'room maps and inspector have a shared responsive layout');
 assert.ok(layout<html.indexOf('id="level-original"')&&layout<html.indexOf('id="level-canvas"'));
 assert.ok(layout<inspector&&inspector<undo&&undo<metatiles,'inspector stays with maps above editor actions and the separate metatile section');
 assert.equal(html.match(/class="card level-object-inspector"/g).length,1);
 assert.doesNotMatch(html,/<div class="grid-two"><details class="card"><summary>Metatiles/);
});

test('blank or malformed object fields preserve staged values, history and review',async()=>{
 for(const [invalidField,invalidValue] of [['level-object-input-1',''],['level-object-input-1','   '],['level-object-input-1','1.0'],['level-object-input-1','1e0'],['level-object-input-1','x'],['level-object-input-1','9007199254740992'],['level-object-destination',''],['level-object-destination','2']]){
  const doc=connectedDocument(),actions={},drafts=new Map(),ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'},results:{'levels.inspect':doc}},draft:(id,fallback)=>drafts.get(id)??fallback,setDraft:(id,value)=>drafts.set(id,value),use:next=>Object.assign(actions,next),render:async()=>{}};
  await render(ctx);const model=ctx.state.levelEditor;
  model.begin();model.set({kind:'object',room_id:'first',index:0,field:'kind',value:2});model.set({kind:'object',room_id:'first',index:0,field:'x',value:1});model.commit();
  model.begin();model.set({kind:'object',room_id:'first',index:0,field:'kind',value:3});model.commit();model.undo();
  const pending={kind:'levels',plan_id:'existing-review'};ctx.state.pending=pending;
  const before=JSON.stringify({changes:model.values(),past:model.past,future:model.future,drafts:[...drafts]}),previous=globalThis.document;
  const inputs={'level-object-index':'0','level-object-input-0':'4','level-object-input-1':'1','level-object-input-2':'0','level-object-destination':'1',[invalidField]:invalidValue};
  try{globalThis.document={getElementById:id=>({value:inputs[id]})};
   assert.throws(()=>actions['levels-object-apply'](),/whole number|bounds|destination/i,`${invalidField} must reject ${JSON.stringify(invalidValue)}`);
   assert.equal(JSON.stringify({changes:model.values(),past:model.past,future:model.future,drafts:[...drafts]}),before);assert.equal(ctx.state.pending,pending);
  }finally{globalThis.document=previous;}
 }
});
