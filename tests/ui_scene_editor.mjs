import assert from 'node:assert/strict';
import {snapColor,levelIndex,pickerSummary,swatchesForPixel,groupSwatches,swatchLabel,changeLine,plural,hex,parseHex,offsetText,KEY_BUTTONS} from '../romancer/ui/scene_editor.js';
import {BASIC_PAGES} from '../romancer/ui/navigation.js';
import {render} from '../romancer/ui/views/scenes.js';

// Pickers offer only what the hardware stores.
const genesis={kind:'levels',levels:[0,36,73,109,146,182,219,255]},gbc={kind:'levels',levels:Array.from({length:32},(_,i)=>Math.round(i*255/31))},sms={kind:'levels',levels:[0,85,170,255]};
assert.deepEqual(snapColor([250,40,130],genesis),[255,36,146]);
assert.deepEqual(snapColor([250,40,130],sms),[255,0,170]);
assert.deepEqual(snapColor([255,165,8],gbc),[255,165,8]);
assert.equal(levelIndex(146,genesis.levels),4);
assert.match(pickerSummary([[255,36,146]],genesis),/Red 7, green 1, blue 4 \(each 0 to 7\)/);
const nes={kind:'master',colors:[[117,117,117],[36,24,142],[0,0,0],[255,255,255]],hidden:[2]};
assert.deepEqual(snapColor([5,5,5],nes),[36,24,142],'hidden NES blacks are never offered');
assert.equal(pickerSummary([[36,24,142]],nes),'NES color 2 of 4');
const shades={kind:'shades',colors:[[255,255,255],[170,170,170],[85,85,85],[0,0,0]]};
assert.equal(pickerSummary([[255,255,255],[170,170,170],[85,85,85],[0,0,0]],shades),'slot 1: white, slot 2: light gray, slot 3: dark gray, slot 4: black');
assert.deepEqual(parseHex(hex([255,165,8])),[255,165,8]);assert.equal(parseHex('red'),null);

// A clicked pixel finds its palette entry even though engines round colors on the way to the screen.
const swatches=[
 {id:'palette:0',name:'Background palette 0, color 1',group:'Background palette 0',colors:[[255,165,8]],editable:true,uses:3,pending:null,locked_reason:''},
 {id:'palette:1',name:'Background palette 0, color 2',group:'Background palette 0',colors:[[0,0,0]],editable:false,uses:0,pending:null,locked_reason:'The game works this color out while it runs.'},
 {id:'palette:9',name:'Background palette 2, color 2',group:'Background palette 2',colors:[[255,165,8]],editable:true,uses:1,pending:null,locked_reason:''}];
const found=swatchesForPixel([255,162,8],swatches);
assert.deepEqual(found.map(match=>match.swatch.id),['palette:0','palette:9'],'every entry that shows the color is reported');
assert.deepEqual(swatchesForPixel([10,200,10],swatches),[]);
assert.deepEqual(groupSwatches(swatches).map(group=>[group.name,group.items.length]),[['Background palette 0',2],['Background palette 2',1]]);
assert.match(swatchLabel(swatches[0]),/can be changed, used in 3 scenes/);
assert.match(swatchLabel(swatches[1]),/locked: The game works this color out/);
assert.equal(changeLine({working:2}),'Redrawing 2 scenes in the real game…');
assert.equal(changeLine({working:0,badge:'Used in 14 scenes',visible_count:1}),'Used in 14 scenes. 1 scene looks different.');
assert.equal(plural(1,'scene'),'1 scene');assert.equal(offsetText(42823),'0x00A747');assert.equal(KEY_BUTTONS.z,'a');
assert.ok(BASIC_PAGES.includes('scenes'),'Scenes & colors is a basic editing screen.');

// The screen: plain language first, byte offsets only inside Details, locked colors say why.
const scene={id:'s1',label:'Scene 1 (0:10 into play)',frame:600,origin:'explore',image:'scene:s1',width:160,height:144};
const change={id:'c1',kind:'color',title:'Background palette 0, color 1',state:'kept',scene_id:'s1',swatch:'palette:0',from_rgb:[[255,0,0]],to_rgb:[[0,255,0]],scope:'all',bytes:2,affected:[],working:0,scene_count:14,visible_count:1,verified:true,verified_here:true,badge:'Used in 14 scenes',coverage:"Seen in 14 of 15 recorded scenes; 1 looks different. Scenes you haven't recorded can't be shown.",verdict:'Checked.',planning:false,error:'',notes:[],details:[]};
const summary={system:'gbc',system_label:'Game Boy Color',engine:{installed:true,reason:''},scenes:[scene],scene_limit:160,recording:null,live:{state:'off'},preview:null,private_copy:{available:false,reason:'Changing only this scene needs a private copy; that tool is not part of this build yet.'},
 changes:{revision:1,changes:[change],scene_count:14,summary:'1 change: affects 14 scenes'}};
const view={scene,look:{image:'scene:s1',state:'original'},recorded_scenes:1,line:{palette:4},pickers:{'rgb555-le':{...gbc,label:'32 levels',help:'This system stores 32 levels of red, green and blue.'}},
 swatches:[{id:'palette:0',domain:'palette',entry:0,group:'Background palette 0',name:'Background palette 0, color 1',format:'rgb555-le',colors:[[255,0,0]],editable:true,status:'rom',locked_reason:'',uses:14,notes:[],pending:[[0,255,0]],pending_change:'c1',details:[{file_offset:42823,kind:'rom',code_address:3981},{file_offset:42824,kind:'rom',code_address:3983}]},
  {id:'palette:1',domain:'palette',entry:1,group:'Background palette 0',name:'Background palette 0, color 2',format:'rgb555-le',colors:[[0,0,0]],editable:false,status:'derived',locked_reason:'The game works this color out while it runs.',uses:0,notes:[],pending:null,pending_change:null,details:[null,null]}]};
const calls=[],state={project:{project_id:'p',sources:[],builds:[]},artifact:{artifact_id:'a',sha256:'s'},page:'scenes',results:{}},handlers={};
const ctx={state,sourceParams:()=>({project_id:'p',artifact_id:'a'}),use:added=>Object.assign(handlers,added),notify(){},api:{call:async(operation,parameters)=>{calls.push(operation);return operation==='edits.open'?summary:operation==='edits.scene'?view:{};}}};
let html=await render(ctx);
assert.deepEqual(calls,['edits.open','edits.scene']);
assert.match(html,/Scenes &amp; colors/);assert.match(html,/Record more scenes/);assert.match(html,/Play and capture a moment/);
assert.match(html,/1 change: affects 14 scenes/);assert.match(html,/data-action="scene-undo" data-id="c1"/);assert.match(html,/data-action="scene-review"/);
assert.match(html,/class="scene-swatch locked[^"]*"[^>]*aria-label="[^"]*locked: The game works this color out/,'A locked color says why in its own label.');
assert.match(html,/Scenes you haven't recorded can't be shown/);
assert(!/style=/.test(html),'Colors are applied by script; the content policy forbids inline styles.');
const outsideDetails=html.replace(/<details>[\s\S]*?<\/details>/g,'');
assert(!/0x[0-9A-F]{4}/.test(outsideDetails),'Byte offsets stay inside Details.');
state.sceneEditor.selected='palette:0';state.sceneEditor.draft=[[0,255,0]];html=await render(ctx);
assert.match(html,/Used in 14 scenes/);assert.match(html,/Everywhere this color is used \(14 recorded scenes\)/);
assert.match(html,/value="only_this" disabled/);assert.match(html,/not part of this build yet/);
assert.match(html,/type="range" min="0" max="31"/);assert.match(html,/<details><summary>Details<\/summary>[\s\S]*0x00A747/);
state.sceneEditor.selected='palette:1';html=await render(ctx);
assert.match(html,/This color can't be changed here\. The game works this color out/);
for(const action of ['scene-open','scene-select','scene-pick-pixel','scene-propose','scene-keep','scene-cancel','scene-undo','scene-compare','scene-record','scene-capture','scene-review','scene-save'])assert.equal(typeof handlers[action],'function',action);
summary.engine={installed:false,reason:'The tracing engine is not installed for Game Boy Color.'};html=await render(ctx);
assert.match(html,/The tracing engine is not installed for Game Boy Color/);assert.match(html,/data-action="scene-record"[^>]*disabled/);
console.log('Scene editor: hardware-true pickers, pixel-to-palette lookup, plain language with details on request.');
