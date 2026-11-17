import assert from 'node:assert/strict';
import {expandGraphics,MODES,parsePixels,pixelText,tilePalette,sameTile,flipTile,fillTile,nearestInk,importPixels,tileRgba,howLabel,bandAt,cellAt,cellRects,bandGrid,sharedCells,cellState,layerLabel,bestLayer,checkTone} from '../romancer/ui/scene_graphics.js';
import {changeLine} from '../romancer/ui/scene_editor.js';
import {render} from '../romancer/ui/views/scenes.js';

// Pictures: text form, palette, and the editor's tools.
const text='0123'.repeat(16),pixels=parsePixels(text,2);
assert.equal(pixels.length,64);assert.equal(pixelText(pixels,2),text);
assert.deepEqual(parsePixels('00ff10',8),[0,255,16]);assert.equal(pixelText([0,255,16],8),'00ff10');
const colors=Array.from({length:64},(_,i)=>[i*4,i,255-i]);
const tile={id:'vram:4640:gb-2bpp',name:'Picture 290',domain:'vram',address:4640,format:'gb-2bpp',bits:2,pixels:text,status:'rom',how:'direct',editable:true,reason:'This picture is stored as plain picture data in the ROM, so it can be changed in place.',on_screen:true,kind:'bg',pal:[0,4,4],line:2,lines:8,zero:'color',uses:3,blank:false,pending:null,notes:[],details:[42823]};
assert.deepEqual(tilePalette(tile,colors),[colors[8],colors[9],colors[10],colors[11]],'a picture is shown with one line of the palette');
assert.deepEqual(tilePalette({...tile,zero:'backdrop'},colors,1)[0],colors[0],'NES color 0 is the shared backdrop');
assert.deepEqual(flipTile(flipTile(pixels,'h'),'h'),pixels);assert.deepEqual(flipTile(pixels,'h').slice(0,8),[3,2,1,0,3,2,1,0]);
assert.deepEqual(flipTile(pixels,'v'),pixels,'every row is the same, so upside down is the same picture');
const filled=fillTile(Array(64).fill(0).map((_,i)=>i%8===3?1:0),0,0,2);
assert.equal(filled.filter(p=>p===2).length,24,'fill stops at a line of another color');assert.equal(filled[4],0);
assert.ok(sameTile(pixels,[...pixels]));assert.ok(!sameTile(pixels,filled));
assert.equal(nearestInk([250,5,5],[[0,0,0],[255,0,0],[0,255,0]]),1);
const rgba=tileRgba([0,1,...Array(62).fill(0)],[[9,9,9],[255,0,0]],true);
assert.equal(rgba[3],0,'see-through pixels are exported transparent');assert.deepEqual([...rgba.slice(4,8)],[255,0,0,255]);
assert.deepEqual(importPixels(rgba,[[9,9,9],[255,0,0]]).slice(0,2),[0,1],'an imported PNG snaps to the palette');
assert.equal(howLabel(tile),'Can be changed in place');assert.equal(howLabel({...tile,how:'packed'}),'Packed in the ROM');assert.equal(howLabel({...tile,editable:false}),'Locked');
assert.deepEqual(MODES.map(mode=>mode[1]),['Colors','Graphics','Background']);
assert.equal(checkTone('good'),'notice');assert.equal(checkTone('warn'),'notice warm');

// A background layer on the screen: scrolled 5 across and 3 down, with a status bar that is not scrolled.
const cells=32*32,layer={index:0,name:'background',width:32,height:32,cell:8,tile_format:'gb-2bpp',tile_domain:'vram',pal:[0,4,4],zero:'color',placed:true,placed_by:'picture',seen:97,
 bands:[[0,16,0,0],[16,144,5,3]],notes:[],flips:true,lines:8,line_note:'',counts:{rom:900,code:24,derived:90,unknown:10},pending:[],
 cells:{tile:Array.from({length:cells},(_,i)=>i%2?4640:4656),flags:Array(cells).fill(0),line:Array(cells).fill(2),status:'r'.repeat(cells-10)+'u'.repeat(10),source:Array.from({length:cells},(_,i)=>i<64?777:1000+i)}};
assert.deepEqual(bandAt(layer,20),[16,144,5,3]);assert.equal(bandAt(layer,200),null);
assert.deepEqual(cellAt(layer,0,0),{cx:0,cy:0,index:0,left:0,top:0});
assert.deepEqual(cellAt(layer,10,20),{cx:1,cy:2,index:65,left:3,top:13},'the scrolled part of the screen starts part-way into a cell');
assert.equal(cellAt(layer,10,150),null);
const rects=cellRects(layer,1,2,160,144);
assert.deepEqual(rects,[{x:3,y:13,size:8,first:16,last:21}],'a cell cut by the status bar is drawn only below it');
assert.deepEqual(cellRects(layer,0,0,160,144).map(rect=>[rect.x,rect.y,rect.first,rect.last]),[[0,0,0,8]]);
const [xs,ys]=bandGrid(layer,layer.bands[1],160);assert.equal(xs[0],3);assert.equal(xs[1],11);assert.equal(ys[0],21);
assert.equal(sharedCells(layer,[3]).length,63,'cells stored in the same place in the ROM change together');assert.deepEqual(sharedCells(layer,[100]),[]);
assert.equal(cellState(layer,0),'plain');assert.equal(cellState(layer,cells-1),'locked');
assert.match(layerLabel(layer),/Background \(seen on 97% of the screen\)/);
assert.equal(bestLayer([{...layer,seen:10},{...layer,index:1,seen:60},{...layer,index:2,placed:false,seen:99}]).index,1);
assert.equal(changeLine({planning:true,scope:'all',verdict:'Trying to pack your picture back into the ROM…'}),'Trying to pack your picture back into the ROM…');
assert.equal(changeLine({planning:true,scope:'only_this',verdict:'x'}),'Working out how to change only this scene…');

// A big scene arrives compact and is expanded to the same shape.
const wire=expandGraphics({kinds:[{how:'packed',editable:true,reason:'r',kind:'bg',pal:[0,16,16],zero:'clear',lines:4,bits:4,status:'derived'}],tiles:[{id:'vram:320:genesis-4bpp',name:'Picture 10',pixels:'01'.repeat(32),k:0,line:1,uses:2,on:1,at:-1}],layers:[{cells:{tile:'320,352',flags:'05',line:'13',status:'dr',source:'-1,77'}}]});
assert.deepEqual([wire.tiles[0].address,wire.tiles[0].format,wire.tiles[0].how,wire.tiles[0].on_screen,wire.tiles[0].details,wire.tiles[0].pending,wire.tiles[0].blank],[320,'genesis-4bpp','packed',true,[],null,false]);
assert.deepEqual(wire.layers[0].cells,{tile:[320,352],flags:[0,5],line:[1,3],status:'dr',source:[-1,77]});

// The screen in Graphics and Background modes.
const scene={id:'s1',label:'Scene 1 (0:10 into play)',frame:600,origin:'explore',image:'scene:s1',width:160,height:144};
const summary={system:'gbc',system_label:'Game Boy Color',engine:{installed:true,reason:''},scenes:[scene],scene_limit:160,recording:null,live:{state:'off'},preview:null,private_copy:{available:true,reason:''},changes:{revision:0,changes:[],scene_count:0,summary:'No changes yet'}};
const view={scene,look:{image:'scene:s1',state:'original'},recorded_scenes:1,line:{palette:4},pickers:{'rgb555-le':{kind:'levels',levels:Array.from({length:32},(_,i)=>Math.round(i*255/31)),label:'32 levels',help:'This system stores 32 levels of red, green and blue.'}},
 swatches:[{id:'palette:5',domain:'palette',entry:5,group:'Background palette 1',name:'Background palette 1, color 2',format:'rgb555-le',colors:[[80,40,0]],editable:false,status:'derived',locked_reason:'The game works this color out while it runs (a fade or a blend, for example), so there is no single stored color to change yet.',findable:true,elsewhere:[{scene_id:'s9',label:'Scene 9 (2:10 into play)',colors:[[255,165,8]],swatch:'palette:5'}],uses:0,notes:[],pending:null,pending_change:null,details:[null,null]}]};
const locked={...tile,id:'vram:0:gb-2bpp',name:'Picture 0',address:0,how:'locked',editable:false,status:'unknown',reason:'ROMancer has not seen where this picture comes from. It was loaded before recording started, or this slot is unused.',uses:0};
const packed={...tile,id:'vram:4656:gb-2bpp',name:'Picture 291',address:4656,how:'packed',status:'derived',reason:'This picture is unpacked by the game while it runs. ROMancer will try to pack your version back into the ROM; if it cannot, it will add a small patch that swaps your picture in.'};
const gfx={scene_id:'s1',colors,tiles:[tile,packed,locked],layers:[layer],sprites:2,patch_available:true,width:160,height:144,private_copy:{available:true,reason:''}};
const calls=[],state={project:{project_id:'p',sources:[],builds:[]},artifact:{artifact_id:'a',sha256:'s'},page:'scenes',results:{}},handlers={},notes=[];
const ctx={state,sourceParams:()=>({project_id:'p',artifact_id:'a'}),use:added=>Object.assign(handlers,added),notify:message=>notes.push(message),api:{call:async(operation)=>{calls.push(operation);return operation==='edits.open'?summary:operation==='edits.scene'?view:operation==='edits.graphics'?gfx:{};}}};
let html=await render(ctx);
for(const label of ['Colors','Graphics','Background'])assert.match(html,new RegExp(`data-action="scene-mode" data-id="${label.toLowerCase()}"[^>]*>${label}<`));
assert.deepEqual(calls,['edits.open','edits.scene'],'pictures are only read when a picture mode is opened');
const ed=state.sceneEditor;
// A locked, computed color offers the search and points at the scene where the same slot is not faded.
ed.selected='palette:5';ed.draft=[[80,40,0]];html=await render(ctx);
assert.match(html,/This color can't be changed here\. The game works this color out/);
assert.match(html,/data-action="scene-find-color"[^>]*>Try to find where this color comes from</);
assert.match(html,/data-action="scene-goto" data-id="s9" data-name="palette:5"[\s\S]*Scene 9 \(2:10 into play\)/);
assert.match(html,/keeps the change only if a replay shows this color following yours/);
// Graphics: nothing chosen, then a picture open in the editor.
ed.mode='graphics';html=await render(ctx);
assert.ok(calls.includes('edits.graphics'));
assert.match(html,/Click a pixel in the scene to open the picture under it/);assert.match(html,/id="scene-sheet"[^>]*tabindex="0"/);
assert.match(html,/Also show pictures that are loaded but not on screen \(3 in all\)/);
ed.tile={id:tile.id,draft:parsePixels(tile.pixels,2),undo:[],ink:1,tool:'pencil',line:2,cx:0,cy:0};html=await render(ctx);
assert.match(html,/<h3>Picture 290<\/h3>[\s\S]*Used in 3 scenes/);assert.match(html,/Can be changed in place/);
assert.match(html,/id="scene-tile-editor"[^>]*tabindex="0" role="application" aria-label="Picture editor, 8 by 8 pixels\. Arrow keys move/);
assert.equal((html.match(/data-action="scene-ink"/g)||[]).length,4,'only the colors of the picture\'s palette are offered');
for(const word of ['Pencil','Pick color','Fill','Flip sideways','Flip upside down','Undo','Start over','Save as PNG','Load a PNG','Show what changes'])assert.match(html,new RegExp('>'+word+'<'),word);
assert.match(html,/Everywhere this picture is used \(3 recorded scenes\)/);assert.match(html,/value="only_this"\s+>/);
assert.match(html,/Shown with palette/);assert.match(html,/<option value="2" selected>Palette 3<\/option>/);
let outside=html.replace(/<details>[\s\S]*?<\/details>/g,'');
assert(!/0x[0-9A-F]{4}/.test(outside),'Byte offsets stay inside Details.');assert(!/style=/.test(html),'No inline styles.');
assert.match(html,/<details><summary>Details<\/summary>[\s\S]*0x00A747/);
// The two facts of a picture change are shown separately, and a patched change says the patch runs everywhere.
const check=(name,stateName,textOf)=>({name,state:stateName,text:textOf});
ed.proposal={id:'c2',kind:'graphics',title:'Picture 291',state:'preview',scene_id:'s1',swatch:null,from_rgb:null,to_rgb:null,scope:'all',bytes:186,affected:[],working:0,scene_count:4,visible_count:2,verified:true,verified_here:true,badge:'Used in 4 scenes',coverage:"Seen in 4 of 4 recorded scenes; 2 look different. Scenes you haven't recorded can't be shown.",planning:false,error:'',notes:[],details:[{file_offset:120,before:1,after:2},{file_offset:524288,before:null,after:7}],grows:0,every_scene:true,tried:[],tiles:[],cells:[],cell_count:0,method:'overlay',
 method_text:'This picture is unpacked by the game while it runs, in a way ROMancer cannot pack again. ROMancer adds a small patch that swaps your picture in after the game has loaded it.',
 checks:[check('In this scene','good','Works in this scene: the game was replayed and the picture came out exactly as you made it.'),check('From power-on','warn','ROMancer also replayed the game from power-on: your change is there, and other things changed too (12 other bytes of video memory). Look at the pictures below before keeping it.')],verdict:'x'};
ed.tile.id=packed.id;summary.preview=ed.proposal;html=await render(ctx);
assert.match(html,/<strong>In this scene\.<\/strong> Works in this scene: the game was replayed/);
assert.match(html,/class="notice warm"><strong>From power-on\.<\/strong> ROMancer also replayed the game from power-on: your change is there, and other things changed too/);
assert.match(html,/adds a small patch that swaps your picture in/);assert.match(html,/every recorded scene was re-rendered/);
assert.match(html,/data-action="scene-keep"/);assert.match(html,/<td>new<\/td><td>07<\/td>/,'bytes added past the old end of the ROM have no old value');
ed.proposal={...ed.proposal,planning:true,working:1,checks:[],verdict:'Trying to pack your picture back into the ROM…',progress:{text:'Trying to pack your picture back into the ROM…',done:3}};summary.preview=ed.proposal;html=await render(ctx);
assert.match(html,/Trying to pack your picture back into the ROM… \(replay 3\)/);assert.match(html,/data-action="scene-keep"[^>]*disabled/);
ed.proposal={...ed.proposal,planning:false,working:0,error:'ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed.',verdict:'ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed.'};summary.preview=ed.proposal;html=await render(ctx);
assert.match(html,/class="notice warm"[^>]*>ROMancer could not find a way to change this picture/);assert.match(html,/data-action="scene-keep"[^>]*disabled/,'an unconfirmed plan cannot be kept');
ed.proposal=null;summary.preview=null;ed.tile.id=locked.id;html=await render(ctx);
assert.match(html,/This picture can't be changed here\. ROMancer has not seen where this picture comes from/);
// Background: the brush, what is painted, and what changes with it.
ed.mode='background';ed.tile=null;ed.brush.tile=tile.id;ed.painted=new Map([[3,{index:3,cx:3,cy:0,tile:tile.id,hflip:false,vflip:false,line:-1}]]);html=await render(ctx);
assert.match(html,/<h3>Paint the background<\/h3>[\s\S]*1 cell painted/);
assert.match(html,/<strong>63 other cells in this scene are stored in the same place in the ROM and will change too<\/strong>/);
for(const word of ['Paint','Pick from the scene','Unpaint','Flip sideways','Flip upside down','Show what changes','Clear painting'])assert.match(html,new RegExp('>'+word+'<'),word);
assert.match(html,/Keep each cell's palette/);assert.match(html,/924 cells can be changed directly, 90 are built by the game while it runs, and 10 are locked/);
assert.match(html,/id="scene-stagewrap" tabindex="0"/,'the scene can be painted with the keyboard');
gfx.layers=[{...layer,placed:false,placed_by:'none',bands:[]}];html=await render(ctx);
assert.match(html,/ROMancer could not find this layer on the recorded screen/);
gfx.layers=[];html=await render(ctx);assert.match(html,/ROMancer could not read a background layer in this scene/);
for(const action of ['scene-mode','scene-sheet-pick','scene-hit','scene-ink','scene-tool','scene-tile-flip','scene-tile-undo','scene-tile-reset','scene-tile-export','scene-tile-import','scene-tile-propose','scene-bg-tool','scene-bg-flip','scene-bg-clear','scene-bg-propose','scene-find-color','scene-goto'])assert.equal(typeof handlers[action],'function',action);
console.log('Scene graphics: picture tools, background cells on a scrolled screen, separate in-scene and power-on facts, plain reasons for locks.');
