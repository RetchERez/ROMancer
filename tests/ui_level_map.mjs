import assert from 'node:assert/strict';
import {placeAt,units,snap,brushFrom,stamp,paintedCells,paintLayers,layerChoices,steps,levelStatus,levelsPart,levelPart,levelChange} from '../romancer/ui/level_map.js';

// a map of 12 by 6 cells; (5,2) was never seen, (7,3) cannot be changed
const width=12,height=6,frames=Array.from({length:width*height},()=>0),status=Array.from({length:width*height},()=>'r');
frames[2*width+5]=-1;status[2*width+5]='.';status[3*width+7]='u';
const view={id:'lvl',name:'Level map 1',plane:0,planes:[{index:0,name:'Background',width,height,cell:8}],width,height,cell:8,sections:[[0,12]],image:'level:lvl:0',after:null,
 frames,status:status.join(''),scenes:[{id:'a',label:'A'}],pending:[],working:false,blocks:{width:2,height:2,left:1,top:0,larger:{width:4,height:4,left:1,top:2}}};

// pointer to place
assert.deepEqual(placeAt(view,2,0,0),[0,0]);
assert.deepEqual(placeAt(view,2,16*5+3,16*2+15),[5,2]);
assert.equal(placeAt(view,2,16*12,0),null);
assert.equal(placeAt(view,1,-1,4),null);

// what the brush can snap to
const [cells,blocks,larger]=units(view);
assert.deepEqual([cells.id,blocks.id,larger.id],['cells','blocks','larger']);
assert.match(blocks.label,/2 by 2 cells/);
assert.match(larger.label,/4 by 4 cells/);
assert.equal(units({...view,blocks:null}).length,1);
assert.deepEqual(snap([4,3],cells),[4,3]);
assert.deepEqual(snap([4,3],blocks),[3,2]);          // blocks start at column 1
assert.deepEqual(snap([0,1],blocks),[-1,0]);         // the block that hangs over the left edge
assert.deepEqual(snap([4,3],larger),[1,2]);
assert.deepEqual(snap([4,1],larger),[1,-2]);

// a brush is every unit touched between two places
assert.deepEqual(brushFrom([4,3],[4,3]),{col:4,row:3,width:1,height:1});
assert.deepEqual(brushFrom([6,4],[4,3]),{col:4,row:3,width:3,height:2});
assert.deepEqual(brushFrom([4,3],[4,3],blocks),{col:3,row:2,width:2,height:2});
assert.deepEqual(brushFrom([4,3],[6,3],blocks),{col:3,row:2,width:4,height:2});
assert.deepEqual(brushFrom([2,2],[2,2],larger),{col:1,row:2,width:4,height:4});

// stamping leaves out places that were never seen, places that cannot be changed, and a place onto itself
const brush={col:1,row:0,width:2,height:2};
assert.deepEqual(stamp(view,brush,3,2),[[3,2,1,0],[4,2,2,0],[3,3,1,1],[4,3,2,1]]);
assert.deepEqual(stamp(view,brush,4,2),[[4,2,1,0],[4,3,1,1],[5,3,2,1]]);          // (5,2) was never seen
assert.deepEqual(stamp(view,brush,6,2),[[6,2,1,0],[7,2,2,0],[6,3,1,1]]);          // (7,3) is locked
assert.deepEqual(stamp(view,brush,1,0),[]);
assert.deepEqual(stamp(view,brush,11,5),[[11,5,1,0]]);                              // the rest falls off the map
assert.deepEqual(stamp(view,{col:5,row:2,width:1,height:1},0,0),[]);              // a brush taken from an unseen place paints nothing

const painted=new Map([['3,2',[1,0]],['4,2',[2,0]]]);
assert.deepEqual(paintedCells(painted),[{col:3,row:2,from:[1,0]},{col:4,row:2,from:[2,0]}]);

// status line
assert.equal(levelStatus({level_recording:null,level_job:null},false),'');
assert.match(levelStatus({level_recording:null,level_job:null},true),/start recording/);
assert.match(levelStatus({level_recording:{name:'Level map 2',captures:1,limit:600},level_job:null},true),/Recording Level map 2: 1 moment captured\./);
assert.match(levelStatus({level_recording:{name:'L',captures:600,limit:600},level_job:null},true),/finish the map/);
assert.match(levelStatus({level_recording:null,level_job:{state:'running',message:'Putting the map together…',done:3,total:40}},false),/3 of 40/);
assert.equal(levelStatus({level_recording:null,level_job:{state:'failed',message:'Nothing was captured.'}},false),'Nothing was captured.');

// the list of level maps: recording needs the game playing
const summary={levels:[],level_recording:null,level_job:null,recording:null};
let html=levelsPart({summary,playing:false,level:null});
assert.match(html,/Record a level map/);
assert.match(html,/disabled/);
assert.match(html,/0 level maps/);
html=levelsPart({summary,playing:true,level:null});
assert.doesNotMatch(html.slice(html.indexOf('level-start')-200,html.indexOf('level-start')+200),/disabled/);
html=levelsPart({summary:{...summary,level_recording:{name:'Level map 1',captures:12,limit:600}},playing:true,level:null});
assert.match(html,/Finish the level map/);
assert.match(html,/Let ROMancer walk right/);
html=levelsPart({summary:{...summary,levels:[{id:'lvl',name:'Stage <1>',scenes:9,planes:[{name:'Background',width:120,height:28,cell:8}],image:'level:lvl:0',pixel_width:960,pixel_height:224}]},playing:false,level:{id:'lvl'}});
assert.match(html,/Stage &lt;1&gt; · 120 by 28 cells/);
assert.match(html,/data-picture="level:lvl:0"/);
assert.match(html,/aria-pressed="true"/);

// the map editor
const verdict=change=>`<p>${change.verdict}</p>`,keep=(change,propose)=>change?'KEEP':propose;
const level={id:'lvl',view,unit:'blocks',tool:'pick',brush:null,painted:new Map(),zoom:2,showAfter:true,last:null,drag:null};
assert.equal(levelPart({level:null},verdict,keep),'');
html=levelPart({level,proposal:null},verdict,keep);
assert.match(html,/width="192" height="96"/);                         // 12 by 6 cells of 8 pixels at 2x
assert.match(html,/built from blocks of 2 by 2 cells, laid out in larger blocks of 4 by 4/);
assert.match(html,/Brush snaps to/);
assert.match(html,/cannot be changed/);
assert.match(html,/No brush yet\./);
assert.match(html,/Show what changes/);
assert.doesNotMatch(html,/KEEP/);
level.brush=brush;level.tool='paint';level.painted=painted;
html=levelPart({level,proposal:null},verdict,keep);
assert.match(html,/Brush: 2 by 2 places from column 2, row 1\. 2 places painted\./);
const proposal={id:'c1',level:{id:'lvl',plane:0,places:[[3,2]]},verdict:'Checked.'};
assert.equal(levelChange({level,proposal}),proposal);
assert.equal(levelChange({level,proposal:{id:'c2',level:{id:'other'}}}),null);
assert.equal(levelChange({level,proposal:{id:'c3'}}),null);
html=levelPart({level,proposal},verdict,keep);
assert.match(html,/<p>Checked\.<\/p>/);
assert.match(html,/KEEP/);
assert.doesNotMatch(html,/not look different/);
html=levelPart({level:{...level,view:{...view,unshown:1,pending:[{col:3,row:2,change:'c1'},{col:4,row:2,change:'c1'}]}},proposal},verdict,keep);
assert.match(html,/1 place you painted does not look different on the map/);
html=levelPart({level:{...level,view:{...view,unshown:2,pending:[{col:3,row:2,change:'c1'},{col:4,row:2,change:'c1'}]}},proposal},verdict,keep);
assert.match(html,/The places you painted do not look different on the map/);
// which layers a change is made on
const two={...view,planes:[{index:0,name:'plane A',width,height,cell:8},{index:1,name:'plane B',width:20,height:6,cell:8}]};
assert.deepEqual(layerChoices(view),[]);                                   // one layer: nothing to choose
assert.deepEqual(layerChoices(two),[['all','All layers'],['0','plane A only'],['1','plane B only']]);
assert.deepEqual(layerChoices({...two,plane:1}),[]);                       // a layer shown alone is the layer painted
assert.deepEqual(paintLayers(view,'all'),[0]);
assert.deepEqual(paintLayers(two,'all'),[0,1]);
assert.deepEqual(paintLayers(two,'1'),[1]);
assert.deepEqual(paintLayers({...two,plane:1},'all'),[1]);
html=levelPart({level:{...level,view:two,paintOn:'1'},proposal:null},verdict,keep);
assert.match(html,/All layers together/);
assert.match(html,/plane B alone/);
assert.match(html,/Paint on/);
assert.match(html,/<option value="1" selected>plane B only/);
// the four steps
const fresh={...level,brush:null,painted:new Map()};
assert.deepEqual(steps(fresh,null).map(step=>step.now),[true,false,false,false]);
assert.deepEqual(steps({...fresh,brush},null).map(step=>step.now),[false,true,false,false]);
assert.deepEqual(steps({...fresh,brush,painted},null).map(step=>step.now),[false,false,true,false]);
assert.deepEqual(steps(fresh,{working:1}).map(step=>step.now),[false,false,true,false]);
assert.deepEqual(steps(fresh,{working:0,error:''}).map(step=>step.now),[false,false,false,true]);
assert.match(levelPart({level:fresh,proposal:null},verdict,keep),/aria-current="step"><strong>Pick/);
console.log('level map checks passed');
