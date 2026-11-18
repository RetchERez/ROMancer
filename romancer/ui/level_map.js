// Level maps in Scenes & colors: record a level while the game scrolls, see the
// whole map, and paint on it. A place on the map is a background cell of the
// scene that showed it, so a change made here is planned, replayed and listed
// exactly like a background change made in that scene.
import {esc,button,badge} from './common.js';
import {plural} from './scene_editor.js';

const TOOLS=[['pick','Pick a picture'],['paint','Paint'],['erase','Unpaint']];
const ZOOMS=[1,2,3,4];
const key=(col,row)=>col+','+row;

// ---- pure helpers (tested in tests/ui_level_map.mjs)

// The place under a pointer, or null outside the map.
export function placeAt(view,zoom,x,y){
 const size=view.cell*zoom,col=Math.floor(x/size),row=Math.floor(y/size);
 return col>=0&&row>=0&&col<view.width&&row<view.height?[col,row]:null;
}
// The units the brush can snap to: single cells, the level's blocks, and its larger blocks when it has them.
export function units(view){
 const out=[{id:'cells',label:'Single cells',width:1,height:1,left:0,top:0}],blocks=view.blocks;
 if(blocks){out.push({id:'blocks',label:`Blocks (${blocks.width} by ${blocks.height} cells)`,...blocks});
  if(blocks.larger)out.push({id:'larger',label:`Larger blocks (${blocks.larger.width} by ${blocks.larger.height} cells)`,...blocks.larger});}
 return out;
}
const floorTo=(value,size,start)=>value-(((value-start)%size)+size)%size;
// The corner of the unit that holds a place.
export function snap(place,unit){return [floorTo(place[0],unit.width,unit.left),floorTo(place[1],unit.height,unit.top)];}
// A brush is a rectangle of the map: every unit touched between two places. It starts at its top left corner.
export function brushFrom(a,b,unit={width:1,height:1,left:0,top:0}){
 const first=snap([Math.min(a[0],b[0]),Math.min(a[1],b[1])],unit),last=snap([Math.max(a[0],b[0]),Math.max(a[1],b[1])],unit);
 return {col:first[0],row:first[1],width:last[0]-first[0]+unit.width,height:last[1]-first[1]+unit.height};
}
// Places a brush covers when stamped at (col,row): [[col,row,fromCol,fromRow],...]. Places no capture showed are left out.
export function stamp(view,brush,col,row){
 const out=[];
 for(let dy=0;dy<brush.height;dy++)for(let dx=0;dx<brush.width;dx++){
  const c=col+dx,r=row+dy,fc=brush.col+dx,fr=brush.row+dy;
  if(c<0||r<0||fc<0||fr<0||c>=view.width||r>=view.height||fc>=view.width||fr>=view.height)continue;
  if(view.frames[r*view.width+c]<0||view.frames[fr*view.width+fc]<0)continue;
  if(view.status[r*view.width+c]==='u')continue;
  if(c===fc&&r===fr)continue;
  out.push([c,r,fc,fr]);
 }
 return out;
}
export const paintedCells=painted=>[...painted.entries()].map(([place,from])=>{const [col,row]=place.split(',').map(Number);return {col,row,from};});
export function levelStatus(summary,playing){
 const rec=summary.level_recording,job=summary.level_job;
 if(rec)return `Recording ${rec.name}: ${plural(rec.captures,'moment')} captured${rec.captures>=rec.limit?' (that is the most one recording holds; finish the map)':''}.`;
 if(job?.state==='running')return `${job.message} ${job.done} of ${job.total}.`;
 if(job?.message)return job.message;
 return playing?'Play to the start of the level, then start recording.':'';
}

// ---- parts

export const levelChange=ed=>ed.proposal&&ed.proposal.level&&ed.level&&ed.proposal.level.id===ed.level.id?ed.proposal:null;

export function levelsPart(ed){
 const summary=ed.summary,levels=summary.levels||[],rec=summary.level_recording,job=summary.level_job,walking=summary.recording?.state==='running';
 const building=job?.state==='running';
 const actions=rec?button('Finish the level map','level-stop',{primary:true,icon:'check',disabled:walking,reason:'Wait until ROMancer stops playing.'})+button(walking?'ROMancer is playing…':'Let ROMancer walk right','level-auto',{disabled:walking,reason:'Already playing.'}):
  button('Record a level map','level-start',{icon:'plus',disabled:!ed.playing||building,reason:building?'ROMancer is still putting the last map together.':'Choose Play and capture a moment above and play to the start of the level first.'});
 return `<div class="card-heading"><h3>Level maps</h3>${badge(plural(levels.length,'level map'),levels.length?'good':'neutral')}</div>
 <p class="subtle">A level map is the whole background of a level, put together while the game scrolls. Play to where the level starts, start recording, then play through it. ROMancer keeps a scene every time the screen moves and lays them side by side.</p>
 <div class="actions">${actions}</div>
 <p class="subtle" id="level-status" role="status" aria-live="polite">${esc(levelStatus(summary,ed.playing))}</p>
 ${building?`<progress max="${job.total}" value="${job.done}" aria-label="Putting the map together"></progress>`:''}
 <div class="scene-strip" role="group" aria-label="Level maps">${levels.map(row=>`<button type="button" class="scene-thumb level-thumb ${ed.level?.id===row.id?'selected':''}" data-action="level-open" data-id="${row.id}" aria-pressed="${ed.level?.id===row.id}"><img alt="" data-picture="${esc(row.image)}" width="${row.pixel_width}" height="${row.pixel_height}"><span>${esc(row.name)} · ${row.planes[0].width} by ${row.planes[0].height} cells</span></button>`).join('')}</div>`;
}

export function levelPart(ed,verdict,keep){
 const level=ed.level;if(!level||!level.view)return '';
 const view=level.view,change=levelChange(ed),painted=level.painted.size,brush=level.brush;
 const planes=view.planes.length>1?`<label>Layer <select id="level-plane" aria-label="Layer of the level">${view.planes.map(p=>`<option value="${p.index}" ${p.index===view.plane?'selected':''}>${esc(p.name)} (${p.width} by ${p.height})</option>`).join('')}</select></label>`:'';
 const choices=units(view),unitPart=choices.length>1?`<label>Brush snaps to <select id="level-unit" aria-label="What the brush snaps to">${choices.map(u=>`<option value="${u.id}" ${u.id===level.unit?'selected':''}>${esc(u.label)}</option>`).join('')}</select></label>`:'';
 const zoom=`<label>Zoom <select id="level-zoom" aria-label="Zoom">${ZOOMS.map(z=>`<option value="${z}" ${z===level.zoom?'selected':''}>${z}x</option>`).join('')}</select></label>`;
 const tools=TOOLS.map(([id,label])=>`<button type="button" class="scene-mode ${level.tool===id?'active':''}" data-action="level-tool" data-id="${id}" aria-pressed="${level.tool===id}">${label}</button>`).join('');
 const hint=level.tool==='pick'?'Click a place to take its picture as your brush, or drag to take a block of places (a platform, a tree).':
  !brush?'Pick a picture from the map first.':level.tool==='paint'?'Click or drag on the map to put your brush there.':'Click or drag over painted places to take the paint off.';
 const brushText=brush?`Brush: ${brush.width} by ${brush.height} ${brush.width*brush.height===1?'place':'places'} from column ${brush.col+1}, row ${brush.row+1}.`:'No brush yet.';
 const built=view.blocks?` This level is built from blocks of ${view.blocks.width} by ${view.blocks.height} cells${view.blocks.larger?`, laid out in larger blocks of ${view.blocks.larger.width} by ${view.blocks.larger.height}`:''}. Paint a whole block onto a whole block and ROMancer looks for the level's own list of blocks, so that only that place changes.`:'';
 const locked=view.status.includes('u')?' Places marked with a cross cannot be changed: ROMancer has not seen where the game gets them from.':'';
 const after=view.after?`<label class="level-toggle"><input type="checkbox" id="level-after" ${level.showAfter?'checked':''}> Show the map with the changes</label>`:'';
 const propose=button('Show what changes','level-propose',{primary:true,disabled:!painted,reason:'Paint at least one place first.'})+button('Clear paint','level-clear',{disabled:!painted&&!change});
 return `<div class="card-heading"><h3>${esc(view.name)}</h3>${badge(`${view.width} by ${view.height} cells · ${plural(view.scenes.length,'capture')}`,'neutral')}</div>
 <div class="actions level-bar">${planes}${zoom}${unitPart}${after}${button('Save map as PNG','level-export',{icon:'download'})}${button('Remove this level map','level-forget')}${button('Close','level-close')}</div>
 <div class="scene-modes" role="group" aria-label="Tool">${tools}</div>
 <p class="subtle" role="status">${hint}${built}${locked}</p>
 <div class="level-scroll" id="level-scroll" tabindex="0" aria-label="The level map. Scroll to move around."><canvas id="level-canvas" class="level-canvas" width="${view.width*view.cell*level.zoom}" height="${view.height*view.cell*level.zoom}" role="img" aria-label="Map of ${esc(view.name)}"></canvas></div>
 <p class="subtle" id="level-where" role="status">${brushText} ${painted?plural(painted,'place')+' painted.':''}</p>
 ${change?verdict(change):''}
 ${change&&view.unshown?`<p class="notice warm" role="status">${view.unshown===view.pending.filter(cell=>cell.change===change.id).length?'The places you painted':plural(view.unshown,'place')+' you painted'} ${view.unshown===1?'does':'do'} not look different on the map after the replay. The change may show somewhere else in the level. Look at the map before you keep it.</p>`:''}
 <div class="actions">${change?keep(change,propose):propose}${button('Open this place in its scene','level-goto',{disabled:!level.last,reason:'Click a place on the map first.'})}</div>
 <p class="subtle">A place on the map is a background cell of the scene that showed it. If the game builds that cell from a block it also uses elsewhere, every place that uses the block changes; the map shows them before you keep the change.</p>`;
}

// ---- drawing

export async function drawLevel(ctx,ed,picture){
 const level=ed.level,canvas=document.getElementById('level-canvas');
 if(!level||!level.view||!canvas)return;
 const view=level.view,zoom=level.zoom,size=view.cell*zoom,context=canvas.getContext('2d');
 const imageKey=level.showAfter&&view.after?view.after:view.image;
 let image=null;
 try{image=await picture(imageKey);}catch{try{image=await picture(view.image);}catch{}}
 if(ed.level!==level||!canvas.isConnected)return;
 context.imageSmoothingEnabled=false;context.clearRect(0,0,canvas.width,canvas.height);
 if(image)context.drawImage(image,0,0,canvas.width,canvas.height);
 context.lineWidth=1;
 // a room the game drew in the place of another starts a new section: mark where one ends and the next begins
 context.strokeStyle='rgba(255,255,255,.55)';context.fillStyle='rgba(255,255,255,.8)';context.font='12px sans-serif';context.setLineDash([6,4]);
 for(const [first] of view.sections.slice(1)){const x=first*size-size*2+.5;context.beginPath();context.moveTo(x,0);context.lineTo(x,canvas.height);context.stroke();context.fillText('another area',x+6,14);}
 context.setLineDash([]);
 // places that cannot be changed
 context.strokeStyle='rgba(255,255,255,.35)';context.beginPath();
 for(let row=0;row<view.height;row++)for(let col=0;col<view.width;col++){
  if(view.status[row*view.width+col]!=='u')continue;
  const x=col*size,y=row*size;context.moveTo(x+2,y+2);context.lineTo(x+size-2,y+size-2);context.moveTo(x+size-2,y+2);context.lineTo(x+2,y+size-2);
 }
 context.stroke();
 // kept and previewed places
 context.strokeStyle='#ffd166';
 for(const cell of view.pending)context.strokeRect(cell.col*size+.5,cell.row*size+.5,size-1,size-1);
 // paint not yet shown to the game: draw the brush picture there, outlined
 if(image&&level.painted.size){
  const source=await picture(view.image).catch(()=>null);
  if(ed.level!==level||!canvas.isConnected)return;
  for(const [place,from] of level.painted){
   const [col,row]=place.split(',').map(Number);
   if(source)context.drawImage(source,from[0]*view.cell,from[1]*view.cell,view.cell,view.cell,col*size,row*size,size,size);
  }
  context.strokeStyle='#4cc9f0';
  for(const place of level.painted.keys()){const [col,row]=place.split(',').map(Number);context.strokeRect(col*size+.5,row*size+.5,size-1,size-1);}
 }
 if(level.brush&&level.tool==='pick'){
  context.strokeStyle='#ffffff';context.setLineDash([4,3]);
  context.strokeRect(level.brush.col*size+.5,level.brush.row*size+.5,level.brush.width*size-1,level.brush.height*size-1);context.setLineDash([]);
 }
 if(level.drag){
  const box=brushFrom(level.drag.from,level.drag.to,units(view).find(u=>u.id===level.unit)||units(view)[0]);context.strokeStyle='#ffffff';
  context.strokeRect(box.col*size+.5,box.row*size+.5,box.width*size-1,box.height*size-1);
 }
}

// ---- behaviour

export function levelTools(ctx,ed,host){
 // host: {call, update, refresh, dropPreview, watchProposal, picture, loadScene, current}
 const redraw=()=>drawLevel(ctx,ed,key=>host.picture(key));
 const load=async(id,plane=0)=>{
  const view=await host.call('level',{level_id:id,plane});
  const same=ed.level&&ed.level.id===id&&ed.level.view?.plane===view.plane;
  const unitIds=units(view).map(u=>u.id);
  ed.level={id,view,unit:same&&unitIds.includes(ed.level.unit)?ed.level.unit:unitIds[unitIds.length-1],tool:same?ed.level.tool:'pick',brush:same?ed.level.brush:null,painted:same?ed.level.painted:new Map(),zoom:same?ed.level.zoom:view.height*view.cell>300?1:2,
   showAfter:same?ed.level.showAfter:true,last:same?ed.level.last:null,drag:null};
 };
 const reload=async()=>{if(!ed.level)return;try{await load(ed.level.id,ed.level.view.plane);}catch{ed.level=null;}host.update(['scene-level']);};
 const watch=()=>{
  clearTimeout(ed.levelPoll);
  const tick=async()=>{
   if(!host.current())return;
   try{
    const summary=await host.call('open');if(!host.current())return;
    const before=ed.summary.level_job?.state,walked=ed.summary.recording?.state;ed.summary=summary;
    const busy=summary.level_recording||summary.level_job?.state==='running'||summary.recording?.state==='running';
    if(before==='running'&&summary.level_job?.state==='finished'&&summary.level_job.level_id){await load(summary.level_job.level_id);host.update(['scene-gallery','scene-levels','scene-level']);ctx.notify(summary.level_job.message);return;}
    if(before==='running'&&summary.level_job?.state==='failed'){host.update(['scene-gallery','scene-levels']);ctx.notify(summary.level_job.message,true);return;}
    if(walked==='running'&&summary.recording?.state!=='running'&&summary.recording?.message)ctx.notify(summary.recording.message,summary.recording.state==='failed');
    const stopped=walked==='running'&&summary.recording?.state!=='running';
    if(!stopped&&ed.playing&&summary.level_recording&&summary.recording?.state!=='running'){const status=document.getElementById('level-status');if(status)status.textContent=levelStatus(summary,true);}
    else host.update(['scene-levels']);
    if(busy)ed.levelPoll=setTimeout(tick,700);
   }catch(error){ctx.notify(error.message,true);}
  };
  ed.levelPoll=setTimeout(tick,500);
 };
 const handlers={
  'level-start':async()=>{ed.summary=await host.call('level_start',{name:''});host.update(['scene-levels']);watch();},
  'level-auto':async()=>{ed.summary=await host.call('level_auto',{steps:6,direction:'right'});host.update(['scene-levels']);watch();},
  'level-stop':async()=>{ed.summary=await host.call('level_stop');host.update(['scene-levels']);watch();},
  'level-open':async node=>{if(ed.level?.id===node.dataset.id)return;await host.dropPreview();await load(node.dataset.id);host.update(['scene-levels','scene-level','scene-changes']);document.getElementById('scene-level')?.scrollIntoView({block:'nearest'});},
  'level-close':async()=>{await host.dropPreview();ed.level=null;host.update(['scene-levels','scene-level','scene-changes']);},
  'level-forget':async()=>{const id=ed.level?.id;if(!id)return;await host.dropPreview();const summary=await host.call('level_forget',{level_id:id});ed.level=null;await host.refresh(summary);host.update();},
  'level-export':async()=>{
   const level=ed.level;if(!level)return;
   const result=await host.call('level_export',{level_id:level.id,plane:level.view.plane,edited:!!(level.showAfter&&level.view.after)});
   const link=document.createElement('a');link.href='data:image/png;base64,'+result.png_base64;link.download=result.name;document.body.append(link);link.click();link.remove();
   ctx.notify(`Saved ${result.name} (${result.width} by ${result.height} pixels).`);
  },
  'level-tool':node=>{if(!ed.level)return;ed.level.tool=node.dataset.id;host.update(['scene-level']);},
  'level-clear':async()=>{if(!ed.level)return;await host.dropPreview();ed.level.painted=new Map();await reload();host.update(['scene-changes']);},
  'level-propose':async()=>{
   const level=ed.level;if(!level||!level.painted.size)return;
   await host.dropPreview();
   const result=await host.call('level_paint',{level_id:level.id,plane:level.view.plane,cells:paintedCells(level.painted)});
   if(!host.current())return;
   ed.proposal=result.change;ed.inspect=null;ed.summary.preview=result.change;level.painted=new Map();level.showAfter=true;
   await reload();host.update(['scene-changes']);host.watchProposal();
  },
  'level-goto':async()=>{
   const level=ed.level;if(!level||!level.last)return;
   const place=await host.call('level_place',{level_id:level.id,plane:level.view.plane,col:level.last[0],row:level.last[1]});
   await host.dropPreview();ed.mode='background';ed.layer=place.layer;await host.loadScene(place.scene_id);host.update();
   document.getElementById('scene-stage')?.scrollIntoView({block:'nearest'});
  },
 };
 const mount=()=>{
  const main=document.getElementById('main');if(!main||main.dataset.levelMounted)return;main.dataset.levelMounted='true';
  const at=event=>{const canvas=document.getElementById('level-canvas'),level=ed.level;if(!canvas||!level?.view||event.target!==canvas)return null;const box=canvas.getBoundingClientRect();return placeAt(level.view,level.zoom,(event.clientX-box.left)*canvas.width/box.width,(event.clientY-box.top)*canvas.height/box.height);};
  const unitOf=level=>units(level.view).find(u=>u.id===level.unit)||units(level.view)[0];
  const apply=place=>{
   const level=ed.level;if(!level||!place)return false;
   if(level.tool==='paint'&&level.brush){let changed=false;const corner=snap(place,unitOf(level));for(const [c,r,fc,fr] of stamp(level.view,level.brush,corner[0],corner[1])){const k=key(c,r);if(String(level.painted.get(k))!==String([fc,fr])){level.painted.set(k,[fc,fr]);changed=true;}}return changed;}
   if(level.tool==='erase')return level.painted.delete(key(place[0],place[1]));
   return false;
  };
  const where=()=>{const node=document.getElementById('level-where'),level=ed.level;if(node&&level)node.textContent=`${level.brush?`Brush: ${level.brush.width} by ${level.brush.height} from column ${level.brush.col+1}, row ${level.brush.row+1}.`:'No brush yet.'} ${level.painted.size?plural(level.painted.size,'place')+' painted.':''}`;};
  main.addEventListener('pointerdown',event=>{
   const place=at(event),level=ed.level;if(!place||!level)return;
   event.preventDefault();event.target.setPointerCapture?.(event.pointerId);level.last=place;
   if(level.tool==='pick'){level.drag={from:place,to:place};}
   else{level.stroke=true;if(apply(place)){where();}}
   void redraw();
  });
  main.addEventListener('pointermove',event=>{
   const level=ed.level;if(!level||(!level.drag&&!level.stroke))return;const place=at(event);if(!place)return;
   if(level.drag){if(String(level.drag.to)===String(place))return;level.drag.to=place;void redraw();}
   else if(apply(place)){where();void redraw();}
  });
  const finish=()=>{
   const level=ed.level;if(!level)return;
   if(level.drag){level.brush=brushFrom(level.drag.from,level.drag.to,unitOf(level));level.drag=null;level.tool='paint';host.update(['scene-level']);}
   else if(level.stroke){level.stroke=false;host.update(['scene-level']);}
  };
  main.addEventListener('pointerup',finish);main.addEventListener('pointercancel',finish);
  main.addEventListener('change',async event=>{
   const level=ed.level;if(!level)return;
   if(event.target.id==='level-zoom'){level.zoom=Number(event.target.value);host.update(['scene-level']);}
   if(event.target.id==='level-unit'){level.unit=event.target.value;level.brush=null;level.tool='pick';host.update(['scene-level']);}
   if(event.target.id==='level-after'){level.showAfter=event.target.checked;void redraw();}
   if(event.target.id==='level-plane'){await host.dropPreview();const id=level.id;ed.level=null;await load(id,Number(event.target.value));host.update(['scene-level','scene-changes']);}
  });
  if(ed.summary?.level_recording||ed.summary?.level_job?.state==='running')watch();
 };
 return {handlers,mount,reload,redraw,watch};
}
