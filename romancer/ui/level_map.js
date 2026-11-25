// Level maps in Scenes & colors: record a level while the game scrolls, see the
// whole map, and paint on it. A place on the map is a background cell of the
// scene that showed it, so a change made here is planned, replayed and listed
// exactly like a background change made in that scene.
import {esc,button,badge} from './common.js';
import {plural} from './scene_editor.js';

const TOOLS=[['pick','Copy'],['paint','Paint'],['erase','Erase']];
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
 const out=[{id:'cells',label:'Single tiles',width:1,height:1,left:0,top:0}],blocks=view.blocks;
 if(view.layout)return [{id:'layout',label:`Whole blocks (${view.layout.width}×${view.layout.height})`,...view.layout}];
 if(blocks){out.push({id:'blocks',label:`Whole blocks (${blocks.width}×${blocks.height})`,...blocks});
  if(blocks.larger)out.push({id:'larger',label:`Big blocks (${blocks.larger.width}×${blocks.larger.height})`,...blocks.larger});}
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
// Which layers a change is made on: the layer being looked at, one chosen layer, or all of them.
// The first map of a level shows every layer together; the others show one layer alone.
export function paintLayers(view,choice){
 if(view.plane!==0||view.planes.length<2)return [view.plane];
 return choice==='all'?view.planes.map(plane=>plane.index):[Number(choice)];
}
export const layerChoices=view=>view.plane===0&&view.planes.length>1?[['all','All layers'],...view.planes.map(plane=>[String(plane.index),plane.name+' only'])]:[];
// The four steps of changing a level, and which one the user is on.
export function steps(level,change){
 const at=change?(change.working||change.error?2:3):level.painted.size?2:level.brush?1:0;
 return [['Copy','Copy a piece of the map'],['Paint','Paint it somewhere else'],['Check','Check it in the game'],['Keep','Keep it or cancel']].map(([name,text],index)=>({name,text,now:index===at,done:index<at}));
}
export const paintedCells=painted=>[...painted.entries()].map(([place,from])=>{const [col,row]=place.split(',').map(Number);return {col,row,from};});
export function levelStatus(summary,playing){
 const rec=summary.level_recording,job=summary.level_job;
 if(rec?.extends)return rec.captures>=rec.limit?`That's as much as one map can hold, so finish it now (${plural(rec.added,'new screen')}).`:`Adding to ${rec.name}, ${plural(rec.added,'new screen')} so far. Play through the parts the map is missing, then finish the map.`;
 if(rec)return rec.captures>=rec.limit?`That's as much as one map can hold, so finish it now (${plural(rec.captures,'screen')}).`:`Recording the level, ${plural(rec.captures,'screen')} so far. Play to the end of it, then finish the map.`;
 if(job?.state==='running')return `${job.message} ${job.done} of ${job.total}.`;
 if(job?.message)return job.message;
 return playing?'Play to where the level starts, then record it.':'';
}

// What an object is, in a few words.
export function objectLabel(item){
 return item.detail?`${item.name}, ${item.detail}`:item.name;
}
// The choices of one field of an object: its own list, or a list the game shares between objects.
export function fieldChoices(field,shared){
 return Array.isArray(field.choices)?field.choices:(shared?.[field.choices]||[]);
}
// The fields of the kind chosen to add, or of the first kind offered.
export function addOption(spot,kind){
 const options=spot?.options||[];
 return options.find(o=>o.kind===kind)||options[0]||null;
}
// The enemy or candle under a map pixel (objects sit on their bottom middle), or null.
export function objectAt(objects,x,y,reach=12){
 let best=null,dist=reach*reach;
 for(const item of objects||[]){const dx=item.map_x-x,dy=item.map_y-8-y,d=dx*dx+dy*dy;if(d<=dist){best=item;dist=d;}}
 return best;
}

// ---- parts

export const levelChange=ed=>ed.proposal&&ed.level&&((ed.proposal.level&&ed.proposal.level.id===ed.level.id)||ed.proposal.kind==='level-object')?ed.proposal:null;

// Which games the level editor knows in full (enemies, items, secrets), and whether this is one of them.
export function gamesPart(info){
 if(!info?.games?.length)return '';
 const groups={};for(const g of info.games)(groups[g.system]=groups[g.system]||[]).push(g.name);
 const here=info.this?`<p><strong>${esc(info.this)}</strong> has full level editing: its enemies, items and secrets are on the map and can be changed.</p>`:'<p>This game has the general level tools: the map, painting blocks, Play from here, and Before and after.</p>';
 return `<div class="level-games">${here}<details><summary>Games with full level editing (${info.games.length})</summary>${Object.entries(groups).map(([system,names])=>`<p class="subtle"><strong>${esc(system)}</strong></p><ul>${names.map(n=>`<li>${esc(n)}</li>`).join('')}</ul>`).join('')}</details></div>`;
}
export function levelsPart(ed){
 const summary=ed.summary,levels=summary.levels||[],rec=summary.level_recording,job=summary.level_job,walking=summary.recording?.state==='running';
 const building=job?.state==='running';
 const actions=rec?button('Finish the map','level-stop',{primary:true,icon:'check',disabled:walking,reason:'Wait for the walk to finish.'})+button(walking?'Walking…':'Walk right for me','level-auto',{disabled:walking,reason:'Already walking.'}):
  button('Record a level map','level-start',{icon:'plus',disabled:!ed.playing||building,reason:building?'The last map is still being put together.':'Start playing above and get to where the level starts first.'});
 return `<div class="card-heading"><h3>Level maps <small class="beta-tag">BETA</small></h3>${badge(plural(levels.length,'level map'),levels.length?'good':'neutral')}</div><p class="subtle">The level editor is in beta. Every change is checked in the game before you keep it, but expect rough edges.</p>
 <p class="subtle">Record a level while you play and you get a map of the whole level that you can paint on.</p>
 ${gamesPart(summary.level_games)}
 <div class="actions">${actions}<label class="button level-walk-open">Open a saved walk<input id="level-walk-file" type="file" accept=".romancer-walk,application/json" aria-label="Open a saved walk" ${rec||building?'disabled':''}></label></div>
 <p class="subtle" id="level-status" role="status" aria-live="polite">${esc(levelStatus(summary,ed.playing))}</p>
 ${building?`<progress max="${job.total}" value="${job.done}" aria-label="Putting the map together"></progress>`:''}
 <div class="scene-strip" role="group" aria-label="Level maps">${levels.map(row=>`<button type="button" class="scene-thumb level-thumb ${ed.level?.id===row.id?'selected':''}" data-action="level-open" data-id="${row.id}" aria-pressed="${ed.level?.id===row.id}"><img alt="" data-picture="${esc(row.image)}" width="${row.pixel_width}" height="${row.pixel_height}"><span>${esc(row.name)}</span></button>`).join('')}</div>`;
}

export function levelPart(ed,verdict,keep){
 const level=ed.level;if(!level||!level.view)return '';
 const view=level.view,change=levelChange(ed),painted=level.painted.size,brush=level.brush;
 const planes=view.planes.length>1?`<label>Show <select id="level-plane" aria-label="Which layers the map shows">${view.planes.map(p=>`<option value="${p.index}" ${p.index===view.plane?'selected':''}>${p.index===0?'All layers':esc(p.name)+' only'}</option>`).join('')}</select></label>`:'';
 const choices=layerChoices(view),paintOn=choices.length?`<label>Paint on <select id="level-layers" aria-label="Which layers a change is made on">${choices.map(([value,label])=>`<option value="${value}" ${value===level.paintOn?'selected':''}>${esc(label)}</option>`).join('')}</select></label>`:'';
 const guide=`<ol class="level-steps" aria-label="How to change the level">${steps(level,change).map(step=>`<li class="${step.now?'now':step.done?'done':''}"${step.now?' aria-current="step"':''}><strong>${step.name}</strong><span>${step.text}</span></li>`).join('')}</ol>`;
 const sizes=units(view),unitPart=sizes.length>1?`<label>Brush size <select id="level-unit" aria-label="Brush size">${sizes.map(u=>`<option value="${u.id}" ${u.id===level.unit?'selected':''}>${esc(u.label)}</option>`).join('')}</select></label>`:'';
 const zoom=`<label>Zoom <select id="level-zoom" aria-label="Zoom">${ZOOMS.map(z=>`<option value="${z}" ${z===level.zoom?'selected':''}>${z}x</option>`).join('')}</select></label>`;
 const tools=[...TOOLS,...(level.objects?.profile?[['objects','Enemies, items and secrets'],...(level.objects.addable?[['add','Add new']]:[]),...(level.objects.resizable?[['length','Longer or shorter']]:[])]:[]),['play','Play from here'],['compare','Before and after']].map(([id,label])=>`<button type="button" class="scene-mode ${level.tool===id?'active':''}" data-action="level-tool" data-id="${id}" aria-pressed="${level.tool===id}">${label}</button>`).join('');
 const hint=level.tool==='add'?'Click an empty spot on the map to add a new enemy, item or secret there. Only things this part of the level can draw are offered.':level.tool==='length'?'Click a screen of the level to repeat it or remove it. Enemies, candles and secrets on later screens move along with them.':level.tool==='objects'?'Click an enemy, a candle, a breakable block (purple) or a hidden treasure (green) to see what it is and change it.':level.tool==='compare'?'Click a spot on the map. ROMancer replays your recorded walk from there on the original game and on the game with your kept changes, side by side.':level.tool==='play'?'Click a spot on the map. The game starts there with your kept changes, so you can play it.':level.tool==='objects'?'Click an enemy or a candle to see what it is and change it.':level.tool==='pick'?'Click a spot on the map to copy it, or drag across a bigger piece like a platform or a tree.':
  !brush?'Copy something from the map first.':level.tool==='paint'?'Click or drag where you want it.':'Click or drag over your paint to remove it.';
 const brushText=brush?`Copied a ${brush.width}×${brush.height} piece.`:'Nothing copied yet.';
 const built=view.layout?' This level is stored packed, so the brush copies whole blocks of it, and ROMancer packs the level again.':view.blocks?' The brush moves in whole blocks, the way this level is built, so a change can stay in one spot.':'';
 const locked=view.status.includes('u')?" Spots with a cross can't be changed yet.":'';
 const known=level.objects?.profile?`<label class="level-toggle"><input type="checkbox" id="level-show-objects" ${level.showObjects?'checked':''}> Show enemies, items and secrets (object layer)</label>${level.objects.roles?`<label class="level-toggle"><input type="checkbox" id="level-show-solid" ${level.showSolid?'checked':''}> Show what's solid</label>`:''}`:'';
 const picked=level.picked;
 const job=level.compare,comparePanel=job?`<div class="notice level-compare" role="group" aria-label="Before and after"><p><strong>Before and after</strong></p><p role="status">${esc(job.message)}${job.state==='running'?` (${Math.round(100*job.done/Math.max(1,job.total))}%)`:''}</p>${job.state==='finished'&&level.compareGif?`<img class="level-compare-picture" src="data:image/gif;base64,${level.compareGif}" width="${job.width}" height="${job.height}" alt="The recorded walk, the original game on the left and the changed game on the right">`:''}<div class="actions">${job.state==='finished'&&level.compareGif?button('Save as GIF','level-compare-save',{icon:'download',primary:true}):''}${job.state!=='running'?button('Close','level-compare-close'):''}</div></div>`:'';
 const objectEditor=level.tool==='objects'&&picked?`<div class="notice level-object" role="group" aria-label="${esc(objectLabel(picked))}"><p><strong>${esc(picked.name)}</strong>${picked.detail?', '+esc(picked.detail):''}</p>${picked.note?`<p class="subtle">${esc(picked.note)}</p>`:''}${(picked.fields||[]).map(field=>`<label>${esc(field.label)} <select id="level-field-${esc(field.key)}" data-key="${esc(field.key)}">${fieldChoices(field,level.objects?.choices).map(c=>`<option value="${esc(JSON.stringify(c.value))}" ${JSON.stringify(c.value)===JSON.stringify(field.value)?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label>`).join('')}<div class="actions">${(picked.fields||[]).length?button('Check in the game','level-edit-apply',{primary:true}):''}${picked.remove?button(picked.remove,'level-edit-remove'):''}</div>${(picked.changes||[]).length?`<p class="subtle">Your changes to this:</p><ul class="level-object-changes">${picked.changes.map(c=>`<li>${esc(c.title)} ${button('Undo','level-edit-undo',{id:c.id})}</li>`).join('')}</ul>`:''}</div>`:'';
 const screen=level.tool==='length'?level.screen:null;
 const lengthPanel=screen?`<div class="notice level-object" role="group" aria-label="Screen ${screen.screen+1}"><p><strong>Screen ${screen.screen+1} of ${screen.screens}</strong> in this part of the level</p><label>How many <select id="level-length-count">${[1,2,3].map(n=>`<option value="${n}">${n}</option>`).join('')}</select></label><div class="actions">${button('Repeat this screen','level-length-apply',{id:'1',primary:true,disabled:screen.screens>=screen.most,reason:`This part is already ${screen.most} screens long, the longest the game has.`})}${button('Remove this screen','level-length-apply',{id:'-1',disabled:screen.screen===0||screen.screen===screen.screens-1,reason:'The first and the last screen hold the way in and the way out, so they stay.'})}</div><p class="subtle">The map keeps showing the level as it was recorded. Play from here and Before and after show the new length.</p></div>`:'';
 const spot=level.tool==='add'?level.spot:null,option=addOption(spot,level.addKind);
 const addPanel=spot&&option?`<div class="notice level-object" role="group" aria-label="Add something new"><p><strong>Add at this spot</strong> in ${esc(spot.name)}</p><label>What to add <select id="level-add-kind">${spot.options.map(o=>`<option value="${esc(o.kind)}" ${o.kind===option.kind?'selected':''}>${esc(o.name)}</option>`).join('')}</select></label>${(option.fields||[]).map(field=>`<label>${esc(field.label)} <select id="level-add-field-${esc(field.key)}" data-key="${esc(field.key)}">${fieldChoices(field,spot.choices).map(c=>`<option value="${esc(JSON.stringify(c.value))}" ${JSON.stringify(c.value)===JSON.stringify(field.value)?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label>`).join('')}<div class="actions">${button('Check in the game','level-add-apply',{primary:true})}${button('Cancel','level-add-cancel')}</div></div>`:'';
 const objectPanel=lengthPanel||addPanel||objectEditor;
 const after=view.after?`<label class="level-toggle"><input type="checkbox" id="level-after" ${level.showAfter?'checked':''}> Show my changes</label>`:'';
 const propose=button('Check in the game','level-propose',{primary:true,disabled:!painted,reason:'Paint something first.'})+button('Clear paint','level-clear',{disabled:!painted&&!change});
 return `<div class="card-heading"><h3>${esc(view.name)}</h3>${badge(`${view.width}×${view.height} tiles`,'neutral')}</div>
 ${guide}
 <div class="actions level-bar">${planes}${paintOn}${zoom}${unitPart}${known}${after}${button('Save map as PNG','level-export',{icon:'download'})}${level.objects?.profile?button('Save map with names','level-export-named',{icon:'download'}):''}${button('Save the walk','level-walk-save',{icon:'download'})}${button('Add to this map','level-extend',{disabled:!ed.playing||!!ed.summary?.level_recording,reason:ed.summary?.level_recording?'A map is being recorded now.':'Start playing above first, then play through what the map is missing.'})}${button('Delete map','level-forget')}${button('Close','level-close')}</div>
 <div class="scene-modes" role="group" aria-label="Tool">${tools}</div>
 <p class="subtle" role="status">${hint}${built}${locked}</p>
 <div class="level-scroll" id="level-scroll" tabindex="0" aria-label="The level map. Scroll to move around."><canvas id="level-canvas" class="level-canvas" width="${view.width*view.cell*level.zoom}" height="${view.height*view.cell*level.zoom}" role="img" aria-label="Map of ${esc(view.name)}"></canvas></div>
 ${objectPanel}${comparePanel}
 <p class="subtle" id="level-where" role="status">${brushText} ${painted?plural(painted,'tile')+' painted.':''}</p>
 ${change?verdict(change):''}
 ${change&&view.unshown?`<p class="notice warm" role="status">Some of what you painted doesn't show on the map after the check. It may appear somewhere else in the level, so look over the map before you keep it.</p>`:''}
 <div class="actions">${change?keep(change,propose):propose}${button('Open in its scene','level-goto',{disabled:!level.last,reason:'Click a spot on the map first.'})}</div>`;
}

// ---- drawing

const objectImages=new Map();
function objectImage(data){
 let image=objectImages.get(data);
 if(!image){image=new Image();image.src='data:image/png;base64,'+data;objectImages.set(data,image);}
 return image;
}

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
 for(const [first] of view.sections.slice(1)){const x=first*size-size*2+.5;context.beginPath();context.moveTo(x,0);context.lineTo(x,canvas.height);context.stroke();context.fillText('separate area',x+6,14);}
 context.setLineDash([]);
 // what is solid and what breaks, from the game's own rule
 if(level.showSolid&&level.objects?.roles){
  for(let row=0;row<view.height;row++)for(let col=0;col<view.width;col++){
   const role=level.objects.roles[row*view.width+col];if(role==='.')continue;
   context.fillStyle=role==='b'?'rgba(255,160,40,.45)':'rgba(70,140,255,.35)';context.fillRect(col*size,row*size,size,size);
  }
 }
 if(level.tool==='add'&&level.spot){
  context.strokeStyle='#ffffff';context.lineWidth=2;context.setLineDash([3*zoom,2*zoom]);
  context.strokeRect(level.spot.map_x*zoom-8*zoom,level.spot.map_y*zoom-16*zoom,16*zoom,16*zoom);context.setLineDash([]);context.lineWidth=1;
 }
 if(level.tool==='length'&&level.screen){
  context.strokeStyle='#7fb2ff';context.lineWidth=2;context.setLineDash([6,4]);
  context.strokeRect(level.screen.map_left*zoom+1,1,256*zoom-2,view.height*view.cell*zoom-2);context.setLineDash([]);context.lineWidth=1;
 }
 if(level.showObjects&&level.objects?.objects){
  context.font=`${Math.max(10,5*zoom)}px sans-serif`;
  for(const item of level.objects.objects){
   const x=item.map_x*zoom,y=item.map_y*zoom,w=16*zoom,h=16*zoom;
   if(item.picture){                                            // the object layer: what the game draws there
    const image=objectImage(item.picture);
    if(image.complete){const [l,t,pw,ph]=item.picture_box;context.globalAlpha=item.picture_from_another?.7:1;context.drawImage(image,l*zoom,t*zoom,pw*zoom,ph*zoom);context.globalAlpha=1;}
    else image.onload=()=>void drawLevel(ctx,ed,picture);
   }
   context.strokeStyle={enemy:'#ff5a5a',item:'#ffd166',secret:'#5ee6b0',block:'#c792ff'}[item.style]||'#ffd166';context.lineWidth=item===level.picked?3:1.5;
   if(item.style==='secret'||item.style==='block')context.setLineDash([3*zoom,2*zoom]);
   context.strokeRect(x-w/2,y-h,w,h);context.setLineDash([]);context.lineWidth=1;
   if(item===level.picked){                                    // the name of the one you clicked; the rest keep the map readable
    context.fillStyle='rgba(0,0,0,.7)';const label=objectLabel(item),width=context.measureText(label).width+6;
    context.fillRect(x-w/2,y-h-14*zoom/2-4,width,12+zoom);context.fillStyle='#fff';context.fillText(label,x-w/2+3,y-h-6);
   }
  }
 }
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
 const watchCompare=async level=>{
  while(ed.level===level&&level.compare?.state==='running'&&host.current()){
   await new Promise(resolve=>setTimeout(resolve,700));
   try{const result=await host.call('level_compare',{level_id:level.id});if(ed.level!==level)return;level.compare=result.compare;}
   catch(error){ctx.notify(error.message,true);return;}
   if(level.compare?.state==='finished'){const file=await host.call('level_compare_file',{level_id:level.id});level.compareGif=file.gif_base64;level.compareName=file.name;}
   host.update(['scene-level']);
  }
 };
 // host: {call, update, refresh, dropPreview, watchProposal, picture, loadScene, current}
 const redraw=()=>drawLevel(ctx,ed,key=>host.picture(key));
 const load=async(id,plane=0)=>{
  const view=await host.call('level',{level_id:id,plane});
  let objects=null;try{objects=await host.call('level_objects',{level_id:id});}catch{objects=null;}
  const same=ed.level&&ed.level.id===id&&ed.level.view?.plane===view.plane;
  const unitIds=units(view).map(u=>u.id);
  ed.level={id,view,paintOn:same&&ed.level.paintOn?ed.level.paintOn:'all',unit:same&&unitIds.includes(ed.level.unit)?ed.level.unit:unitIds[unitIds.length-1],tool:same?ed.level.tool:'pick',brush:same?ed.level.brush:null,painted:same?ed.level.painted:new Map(),zoom:same?ed.level.zoom:view.height*view.cell>300?1:2,
   showAfter:same?ed.level.showAfter:true,last:same?ed.level.last:null,drag:null,objects,showObjects:same?ed.level.showObjects:!!objects?.profile,showSolid:same?ed.level.showSolid:false,picked:same?ed.level.picked:null,spot:same?ed.level.spot:null,addKind:same?ed.level.addKind:null,choices:same?ed.level.choices:null};
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
  'level-extend':async()=>{const id=ed.level?.id;if(!id)return;ed.summary=await host.call('level_start',{name:'',extend:id});host.update(['scene-levels','scene-level']);watch();document.getElementById('scene-levels')?.scrollIntoView({block:'nearest'});},
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
  'level-walk-save':async()=>{
   const level=ed.level;if(!level)return;
   const result=await host.call('level_walk_file',{level_id:level.id});
   const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([result.text],{type:'application/json'}));link.download=result.name;document.body.append(link);link.click();link.remove();
   ctx.notify(`Saved ${result.name}. Anyone with the same ROM can open it to get this map and replay its checks.`);
  },
  'level-export-named':async()=>{
   const level=ed.level;if(!level)return;
   const result=await host.call('level_export',{level_id:level.id,plane:0,edited:!!(level.showAfter&&level.view.after),labels:true});
   const link=document.createElement('a');link.href='data:image/png;base64,'+result.png_base64;link.download=result.name;document.body.append(link);link.click();link.remove();
   ctx.notify(`Saved ${result.name} (${result.width} by ${result.height} pixels), with every enemy, item and secret named.`);
  },
  'level-edit-undo':async node=>{
   const level=ed.level;if(!level)return;
   await host.dropPreview();
   const summary=await host.call('remove',{change_id:node.dataset.id});
   await host.refresh(summary);await reload();
   if(level.picked)level.picked=(ed.level?.objects?.objects||[]).find(o=>o.id===level.picked.id&&JSON.stringify(o.part)===JSON.stringify(level.picked.part))||null;
   if(ed.level)ed.level.picked=level.picked;
   host.update(['scene-level','scene-changes']);ctx.notify('That change is undone.');
  },
  'level-compare-save':()=>{
   const level=ed.level;if(!level?.compareGif)return;
   const link=document.createElement('a');link.href='data:image/gif;base64,'+level.compareGif;link.download=level.compareName||'before and after.gif';document.body.append(link);link.click();link.remove();
   ctx.notify(`Saved ${level.compareName||'before and after.gif'}.`);
  },
  'level-compare-close':()=>{if(!ed.level)return;ed.level.compare=null;ed.level.compareGif=null;host.update(['scene-level']);},
  'level-tool':node=>{if(!ed.level)return;ed.level.tool=node.dataset.id;host.update(['scene-level']);},
  'level-clear':async()=>{if(!ed.level)return;await host.dropPreview();ed.level.painted=new Map();await reload();host.update(['scene-changes']);},
  'level-propose':async()=>{
   const level=ed.level;if(!level||!level.painted.size)return;
   await host.dropPreview();
   const result=level.view.layout?await host.call('level_layout',{level_id:level.id,cells:paintedCells(level.painted)}):
    await host.call('level_paint',{level_id:level.id,plane:level.view.plane,cells:paintedCells(level.painted),layers:paintLayers(level.view,level.paintOn)});
   if(!host.current())return;
   ed.proposal=result.change;ed.inspect=null;ed.summary.preview=result.change;level.painted=new Map();level.showAfter=true;
   await reload();host.update(['scene-changes']);host.watchProposal();
  },
  'level-edit-apply':async()=>{
   const level=ed.level,picked=level?.picked;if(!picked)return;
   const values={};for(const node of document.querySelectorAll('[id^="level-field-"]'))values[node.dataset.key]=JSON.parse(node.value);
   await host.dropPreview();
   const result=await host.call('level_edit',{level_id:level.id,part:picked.part,object_id:picked.id,values,remove:false});
   if(!host.current())return;ed.proposal=result.change;ed.summary.preview=result.change;host.update(['scene-level','scene-changes']);host.watchProposal();
  },
  'level-edit-remove':async()=>{
   const level=ed.level,picked=level?.picked;if(!picked)return;
   await host.dropPreview();
   const result=await host.call('level_edit',{level_id:level.id,part:picked.part,object_id:picked.id,values:{},remove:true});
   if(!host.current())return;ed.proposal=result.change;ed.summary.preview=result.change;host.update(['scene-level','scene-changes']);host.watchProposal();
  },
  'level-add-apply':async()=>{
   const level=ed.level,spot=level?.spot,option=addOption(spot,level?.addKind);if(!option)return;
   const values={};for(const node of document.querySelectorAll('[id^="level-add-field-"]'))values[node.dataset.key]=JSON.parse(node.value);
   await host.dropPreview();
   const result=await host.call('level_add',{level_id:level.id,part:spot.part,kind:option.kind,x:spot.x,y:spot.y,values});
   if(!host.current())return;ed.proposal=result.change;ed.summary.preview=result.change;host.update(['scene-level','scene-changes']);host.watchProposal();
  },
  'level-add-cancel':()=>{if(!ed.level)return;ed.level.spot=null;host.update(['scene-level']);},
  'level-length-apply':async node=>{
   const level=ed.level,screen=level?.screen;if(!screen)return;
   const count=Number(document.getElementById('level-length-count')?.value||1),delta=Number(node.dataset.id)*count;
   await host.dropPreview();
   const result=await host.call('level_length',{level_id:level.id,part:screen.part,screen:screen.screen,delta});
   if(!host.current())return;ed.proposal=result.change;ed.summary.preview=result.change;host.update(['scene-level','scene-changes']);host.watchProposal();
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
   const level=ed.level;
   if(level?.tool==='length'){
    const canvas=document.getElementById('level-canvas');if(!canvas||event.target!==canvas)return;
    const box=canvas.getBoundingClientRect(),x=(event.clientX-box.left)*canvas.width/box.width/level.zoom;
    void host.call('level_screen_at',{level_id:level.id,x}).then(result=>{level.screen=result;host.update(['scene-level']);}).catch(error=>ctx.notify(error.message,true));
    return;
   }
   if(level?.tool==='add'){
    const canvas=document.getElementById('level-canvas');if(!canvas||event.target!==canvas)return;
    const box=canvas.getBoundingClientRect(),x=(event.clientX-box.left)*canvas.width/box.width/level.zoom,y=(event.clientY-box.top)*canvas.height/box.height/level.zoom;
    void host.call('level_add_at',{level_id:level.id,x,y}).then(result=>{level.spot=result;level.addKind=result.options[0]?.kind;host.update(['scene-level']);void redraw();}).catch(error=>ctx.notify(error.message,true));
    return;
   }
   if(level?.tool==='compare'){
    const canvas=document.getElementById('level-canvas');if(!canvas||event.target!==canvas)return;
    if(level.compare?.state==='running')return;
    const box=canvas.getBoundingClientRect(),x=(event.clientX-box.left)*canvas.width/box.width/level.zoom,y=(event.clientY-box.top)*canvas.height/box.height/level.zoom;
    level.compareGif=null;
    void host.call('level_compare',{level_id:level.id,x,y}).then(result=>{level.compare=result.compare;host.update(['scene-level']);watchCompare(level);}).catch(error=>ctx.notify(error.message,true));
    return;
   }
   if(level?.tool==='play'){
    const canvas=document.getElementById('level-canvas');if(!canvas||event.target!==canvas)return;
    const box=canvas.getBoundingClientRect(),x=(event.clientX-box.left)*canvas.width/box.width/level.zoom,y=(event.clientY-box.top)*canvas.height/box.height/level.zoom;
    ctx.notify('Starting your changed game at that spot…');
    void host.call('level_play_from',{level_id:level.id,x,y}).then(result=>{if(host.current())host.startPlaying(result.playtest);}).catch(error=>ctx.notify(error.message,true));
    return;
   }
   if(level?.tool==='objects'){
    const canvas=document.getElementById('level-canvas');if(!canvas||event.target!==canvas)return;
    const box=canvas.getBoundingClientRect(),x=(event.clientX-box.left)*canvas.width/box.width/level.zoom,y=(event.clientY-box.top)*canvas.height/box.height/level.zoom;
    const item=objectAt(level.objects?.objects,x,y);level.picked=item;
    host.update(['scene-level']);
    return;
   }
   const place=at(event);if(!place||!level)return;
   event.preventDefault();event.target.setPointerCapture?.(event.pointerId);level.last=place;
   if(level.tool==='pick'){level.drag={from:place,to:place};}
   else{level.stroke=true;if(apply(place)){where();}}
   void redraw();
  });
  main.addEventListener('pointermove',event=>{
   const level=ed.level,canvas=document.getElementById('level-canvas');
   if(level&&canvas&&event.target===canvas&&level.showObjects&&level.objects?.objects){
    const box=canvas.getBoundingClientRect(),x=(event.clientX-box.left)*canvas.width/box.width/level.zoom,y=(event.clientY-box.top)*canvas.height/box.height/level.zoom;
    const item=objectAt(level.objects.objects,x,y);
    canvas.title=item?objectLabel(item):'';
   }if(!level||(!level.drag&&!level.stroke))return;const place=at(event);if(!place)return;
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
   if(event.target.id==='level-walk-file'){
    const file=event.target.files?.[0];if(!file)return;
    if(file.size>8*1024*1024){ctx.notify('That file is too big to be a saved walk.',true);return;}
    try{ed.summary=await host.call('level_walk_open',{text:await file.text()});host.update(['scene-levels']);watch();}catch(error){ctx.notify(error.message,true);}
    event.target.value='';return;
   }
   const level=ed.level;if(!level)return;
   if(event.target.id==='level-add-kind'){level.addKind=event.target.value;host.update(['scene-level']);}
   if(event.target.id==='level-zoom'){level.zoom=Number(event.target.value);host.update(['scene-level']);}
   if(event.target.id==='level-layers'){level.paintOn=event.target.value;}
   if(event.target.id==='level-unit'){level.unit=event.target.value;level.brush=null;level.tool='pick';host.update(['scene-level']);}
   if(event.target.id==='level-after'){level.showAfter=event.target.checked;void redraw();}
   if(event.target.id==='level-show-objects'){level.showObjects=event.target.checked;void redraw();}
   if(event.target.id==='level-show-solid'){level.showSolid=event.target.checked;void redraw();}
   if(event.target.id==='level-plane'){await host.dropPreview();const id=level.id;ed.level=null;await load(id,Number(event.target.value));host.update(['scene-level','scene-changes']);}
  });
  if(ed.summary?.level_recording||ed.summary?.level_job?.state==='running')watch();
 };
 return {handlers,mount,reload,redraw,watch};
}
