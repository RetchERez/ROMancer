import assert from 'node:assert/strict';
import test from 'node:test';
import {MapDraft,cropMap,mapPoint,mapPixels,gameMaps,mountGameMaps} from '../romancer/ui/game_maps.js';
import {render as levels} from '../romancer/ui/views/levels.js';

function inspection(header=0x486b){return {ok:true,source_sha256:'sha',room:{header,label:`Room ${header.toString(16)}`,map_pointer:0x265,shared_headers:[header],editable:header===0x486b,flags:0},objects:[{index:0,offset:70,x:5,y:6,event:0x112,condition:0,range:15,editable:true,state_status:'unconditional definition'}],arrivals:[{id:0x1fd,table:'main',offset:30,header,x:7,y:8,facing:0,flags:0}],links:[{index:0,word:0x06ff,transition:{kind:'saved-return'},destination:null}],map:{status:'decoded',size:[64,64],tile_size:16,cells:Array(4096).fill(0),tiles:[Array(256).fill(0),Array(256).fill(1)],palette:[[255,255,255],[0,0,0]],palette_status:'synthetic test palette',behavior:[1,1],provenance:Array(4096).fill(10),commands:[{offset:10,op:1,x:7,y:8,tile:1,editable:true,final_cells:1,size:3}],marker_cells:[],native_verified:false}};}
function catalog(){return {ok:true,source_sha256:'sha',rooms:[{header:0x486b,label:'Room <486B>',map_pointer:0x265,object_count:1,arrival_count:1,thumbnail:{status:'available',data_url:'data:image/png;base64,eA==',palette_status:'color-index grayscale'}}],total:219,offset:0,limit:12,counts:{rooms:219,maps:164,arrivals:543,objects:660}};}
function context(){const actions={},drafts=new Map();const ctx={state:{page:'levels',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',name:'Owned game'},results:{}},sourceParams:()=>({project_id:ctx.state.project.project_id,artifact_id:ctx.state.artifact.artifact_id}),projectParams:()=>({project_id:ctx.state.project.project_id}),draft:(id,fallback)=>drafts.get(id)??fallback,setDraft:(id,v)=>drafts.set(id,v),use:a=>Object.assign(actions,a),render:async()=>{},notify(){},api:{call:async(op,p)=>op==='games.maps.catalog'?catalog():inspection(p.header)},run:async()=>({ok:true,source_sha256:'sha',plan_id:'plan',edits:[{offset:10,before:'00',after:'01'}],preview_map:{cells:Array(4096).fill(1)}}),refreshProject:async()=>{},setArtifact:async()=>{}};return {ctx,actions,drafts};}
function fields(values){const old=globalThis.document;globalThis.document={getElementById:id=>({value:String(values[id]??'')})};return()=>globalThis.document=old;}
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}

test('staged edits merge fixed fields, undo and redo without changing source objects',()=>{
 const doc=inspection(),draft=new MapDraft(doc);draft.stage({kind:'command',offset:10,x:9,y:8});
 assert.deepEqual(draft.values(),[{kind:'command',offset:10,x:9}]);draft.stage({kind:'command',offset:10,y:10});
 assert.deepEqual(draft.values(),[{kind:'command',offset:10,x:9,y:10}]);draft.undo();assert.equal(draft.values()[0].y,undefined);draft.redo();assert.equal(draft.values()[0].y,10);
 draft.stage({kind:'command',offset:10,x:7,y:8});assert.deepEqual(draft.values(),[]);assert.equal(doc.map.commands[0].x,7);
 assert.throws(()=>draft.stage({kind:'npc',offset:70,event:3}),/field|coordinate|protected/i);
});
test('cropped terrain keeps selected arrival readable and picks actual coordinates',()=>{
 const crop=cropMap([7,8]);assert.ok(crop.width<=20&&crop.height<=16);assert.ok(crop.x<=7&&crop.x+crop.width>7);
 assert.deepEqual(mapPoint(crop,{left:0,top:0,width:160,height:120},{x:1,y:1}),[crop.x,crop.y]);
 assert.equal(mapPoint(crop,{left:0,top:0,width:160,height:120},{x:-1,y:1}),null);
 const doc=inspection();const image=mapPixels(doc.map,crop);assert.equal(image.pixels.length,image.width*image.height*4);assert.deepEqual([...image.pixels.slice(0,4)],[255,255,255,255]);
});
test('real map view uses bounded thumbnails, controls and scope text without invented names',async()=>{
 const {ctx,actions}=context();const html=await gameMaps(ctx);
 assert.match(html,/219/);assert.match(html,/data:image\/png/);assert.match(html,/Room &lt;486B&gt;/);assert.match(html,/Original for this edit/);assert.match(html,/Review map changes/);
 assert.match(html,/Mother/);assert.match(html,/story/i);assert.match(html,/saved return/i);assert.match(html,/grayscale|palette/i);assert.match(html,/crop|overview/i);
 assert.doesNotMatch(html,/textarea|JSON descriptor|test actor|fake character/i);assert.equal(typeof actions['maps-review'],'function');
});
test('delayed catalog and inspect results cannot overwrite a new artifact selection',async()=>{
 const {ctx}=context(),later=deferred();ctx.api.call=()=>later.promise;const pending=gameMaps(ctx);ctx.state.artifact={artifact_id:'other',sha256:'new'};later.resolve(catalog());
 assert.equal(await pending,'');assert.equal(ctx.state.gameMapsView?.inspection,undefined);
});
test('room selection changing during inspect drops the old room response',async()=>{
 const {ctx,actions}=context(),later=deferred();ctx.api.call=async(op)=>op==='games.maps.catalog'?catalog():later.promise;
 const pending=gameMaps(ctx);await Promise.resolve();await actions['maps-open-room']({dataset:{id:String(0x489d)}});later.resolve(inspection());
 assert.equal(await pending,'');assert.notEqual(ctx.state.gameMapsView?.inspection?.room?.header,0x486b);
});
test('review invalidates on newer edits and stale reviewed builds are refused',async()=>{
 const {ctx,actions}=context();await gameMaps(ctx);const view=ctx.state.gameMapsView;
 const reset=fields({'maps-x':9,'maps-y':8,'maps-tile':1});try{await actions['maps-stage']();}finally{reset();}
 const later=deferred();ctx.run=()=>later.promise;const pending=actions['maps-review']();view.model.stage({kind:'command',offset:10,x:10});later.resolve({ok:true,source_sha256:'sha',plan_id:'old',edits:[]});await pending;
 assert.equal(view.pending,null);await assert.rejects(()=>actions['maps-build'](),/review/i);
});
test('a newer review wins over a delayed response and exact reviewed pixels are used',async()=>{
 const {ctx,actions}=context();await gameMaps(ctx);ctx.state.gameMapsView.model.stage({kind:'command',offset:10,x:9});
 const first=deferred(),second=deferred();let count=0;ctx.run=()=>++count===1?first.promise:second.promise;
 const a=actions['maps-review'](),b=actions['maps-review']();second.resolve({ok:true,source_sha256:'sha',plan_id:'new',edits:[],preview_map:{cells:Array(4096).fill(1)}});await b;
 first.resolve({ok:true,source_sha256:'sha',plan_id:'old',edits:[]});await a;assert.equal(ctx.state.gameMapsView.pending.result.plan_id,'new');
});
test('newer staged edits survive an in-flight separate build',async()=>{
 const {ctx,actions}=context();await gameMaps(ctx);const view=ctx.state.gameMapsView;view.model.stage({kind:'command',offset:10,x:9});await actions['maps-review']();
 const later=deferred();ctx.run=()=>later.promise;let selected=false;ctx.setArtifact=async()=>{selected=true;};const pending=actions['maps-build']();view.model.stage({kind:'command',offset:10,x:11});later.resolve({ok:true,artifact_id:'built'});await pending;
 assert.equal(selected,false);assert.equal(view.model.values()[0].x,11);
});
test('derived FFL2 builds with no simple visual still open their real map catalog',async()=>{
 const {ctx}=context();ctx.api.call=async(op,p)=>op==='games.inspect'?{ok:true,profile:{id:'ffl2-usa'},map_workbench:true,visual:null}:op==='games.maps.catalog'?catalog():inspection(p.header);
 const html=await levels(ctx);assert.match(html,/Real game maps/);assert.match(html,/Original for this edit/);assert.doesNotMatch(html,/No supported level map/);
});
test('the bedroom shortcut stays the default with an explicit full browser action',async()=>{
 const {ctx,actions,drafts}=context(),visual={kind:'room-map',origin:[10,28],size:[7,8],tile_size:16,palette:[[255,255,255]],tiles:Array.from({length:64},()=>Array(256).fill(0)),base_cells:Array(56).fill(0),original_cells:Array(56).fill(0),current:[14,31],original:[14,31],stool_down:[14,32],object:{tile_id:29,allowed:[[14,31],[14,32]]}};
 const game={ok:true,status:'MATCHED',profile:{id:'ffl2-usa',name:'Final Fantasy Legend II',scope:'Opening room',reference:'https://example.test/source'},map_workbench:true,visual,fields:[{id:'room_layout',type:'choice',value:'original',label:'Stool',options:[['original','Original'],['stool_down','Down']]}],resources:[],locations:[]};ctx.api.call=async()=>game;
 const html=await levels(ctx);assert.match(html,/Browse game maps/);assert.match(html,/room-original/);assert.doesNotMatch(html,/game-map-catalog/);await actions['ffl2-maps-open']();assert.equal(drafts.get('ffl2-map-mode'),'browser');
});
test('leaving Levels drops an in-flight review for the same artifact',async()=>{
 const {ctx,actions}=context();await gameMaps(ctx);const view=ctx.state.gameMapsView;view.model.stage({kind:'command',offset:10,x:9});const later=deferred();ctx.run=()=>later.promise;
 const pending=actions['maps-review']();ctx.state.page='assets';later.resolve({ok:true,source_sha256:'sha',plan_id:'old',edits:[]});await pending;assert.equal(view.pending,null);
});
test('pending builds are invalidated when coordinate inputs change without staging',async()=>{
 const {ctx,actions}=context();await gameMaps(ctx);const view=ctx.state.gameMapsView;view.model.stage({kind:'command',offset:10,x:9});await actions['maps-review']();
 const events={},g={createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){},strokeRect(){},fillText(){}},canvas={style:{},getContext:()=>g,addEventListener(){}};
 const old=globalThis.document;try{globalThis.document={getElementById:id=>id==='maps-original'||id==='maps-edit'?canvas:{value:'9',addEventListener:(name,fn)=>events[id+':'+name]=fn},querySelectorAll:()=>[]};mountGameMaps(ctx);events['maps-x:input']();assert.equal(view.pending,null);await assert.rejects(()=>actions['maps-build'](),/review|stage/i);}finally{globalThis.document=old;}
});
test('validated staged map changes restore after a fresh view without saving reviews',async()=>{
 const {ctx,actions,drafts}=context();await gameMaps(ctx);const reset=fields({'maps-x':9,'maps-y':8,'maps-tile':1});try{await actions['maps-stage']();}finally{reset();}
 const saved=JSON.parse(drafts.get('game-map-changes'));assert.equal(saved.source_sha256,'sha');assert.equal(saved.changes_by_header[String(0x486b)][0].x,9);assert.equal(saved.plan_id,undefined);assert.equal(ctx.state.historyEditor,'maps-edit');
 ctx.state.gameMapsView=null;await gameMaps(ctx);assert.equal(ctx.state.gameMapsView.model.values()[0].x,9);assert.equal(ctx.state.gameMapsView.pending,null);
 await actions['maps-clear']();assert.deepEqual(JSON.parse(drafts.get('game-map-changes')).changes_by_header,{});
});
test('stale-source, unknown-header and invalid saved records are never restored',async()=>{
 for(const saved of [{version:1,source_sha256:'old',changes_by_header:{[0x486b]:[{kind:'command',offset:10,x:9}]}},{version:1,source_sha256:'sha',changes_by_header:{9999:[{kind:'command',offset:10,x:9}]}},{version:1,source_sha256:'sha',changes_by_header:{[0x486b]:[{kind:'npc',offset:70,event:4}]}}]){
  const {ctx,drafts}=context();drafts.set('game-map-changes',JSON.stringify(saved));const html=await gameMaps(ctx);assert.deepEqual(ctx.state.gameMapsView.model.values(),[]);assert.match(html,/saved.*ignored|ignored.*saved/i);
 }
});
test('map undo history and staging are bounded',()=>{
 const doc=inspection();doc.map.commands=Array.from({length:65},(_,i)=>({offset:100+i,op:1,x:7,y:8,tile:1,editable:true}));const model=new MapDraft(doc);
 for(let i=0;i<240;i++)model.stage({kind:'command',offset:100,x:i%2?8:9});assert.ok(model.past.length<=200);
 for(let i=1;i<64;i++)model.stage({kind:'command',offset:100+i,x:9});assert.equal(model.values().length,64);assert.throws(()=>model.stage({kind:'command',offset:164,x:9}),/64|limit/i);assert.equal(model.values().length,64);
});
test('switching to bedroom shortcut invalidates an in-flight browser review',async()=>{
 const {ctx,actions}=context();await gameMaps(ctx,{simpleAvailable:true});const view=ctx.state.gameMapsView;view.model.stage({kind:'command',offset:10,x:9});const later=deferred();ctx.run=()=>later.promise;
 const pending=actions['maps-review']();await actions['maps-simple']();later.resolve({ok:true,source_sha256:'sha',plan_id:'old',edits:[]});await pending;assert.equal(view.pending,null);
});
test('a delayed browser build cannot select its artifact after bedroom edits or reopening',async()=>{
 const {ctx,actions}=context();await gameMaps(ctx,{simpleAvailable:true});const view=ctx.state.gameMapsView;view.model.stage({kind:'command',offset:10,x:9});await actions['maps-review']();
 const later=deferred();ctx.run=()=>later.promise;let selected=false;ctx.setArtifact=async()=>selected=true;const pending=actions['maps-build']();await actions['maps-simple']();ctx.state.gameEditPlan={newerBedroomEdit:true};await gameMaps(ctx,{simpleAvailable:true});
 later.resolve({ok:true,artifact_id:'old-build'});await pending;assert.equal(selected,false);assert.deepEqual(ctx.state.gameEditPlan,{newerBedroomEdit:true});
});
