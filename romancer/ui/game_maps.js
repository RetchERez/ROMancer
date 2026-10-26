import {rememberPreview} from './clean_preview.js';
import {esc,button,field,select,read} from './common.js';
import {selectionKey} from './tool_inputs.js';

const hex=n=>'0x'+Number(n).toString(16).toUpperCase();
const clone=value=>JSON.parse(JSON.stringify(value));
const key=c=>c.kind==='arrival'?`arrival:${c.table}:${c.id}`:`${c.kind}:${c.offset}`;
const number=(value,max=63)=>{if(!/^\d+$/.test(String(value))||!Number.isSafeInteger(Number(value))||Number(value)>max)throw Error(`Enter a whole number from 0 to ${max}.`);return Number(value);};
const objectName=(room,n)=>room.header===0x486b&&n.event===0x112?'Mother':`NPC definition ${n.index+1}`;

export class MapDraft{
 constructor(doc){this.doc=doc;this.changes=new Map();this.past=[];this.future=[];this.revision=0;}
 values(){return [...this.changes.values()].sort((a,b)=>key(a).localeCompare(key(b))).map(clone);}
 entity(change){if(change.kind==='command')return this.doc.map.commands.find(c=>c.offset===change.offset);if(change.kind==='npc')return this.doc.objects.find(n=>n.offset===change.offset);if(change.kind==='arrival')return this.doc.arrivals.find(a=>a.table===change.table&&a.id===change.id);return null;}
 stage(change){
  const base=this.entity(change),allowed=change.kind==='command'?['kind','offset','x','y','tile']:change.kind==='npc'?['kind','offset','x','y']:['kind','table','id','x','y'];
  if(!base||!['command','npc','arrival'].includes(change.kind)||Object.keys(change).some(k=>!allowed.includes(k)))throw Error('Unknown or protected map field.');
  if(change.kind!=='arrival'&&!base.editable)throw Error('This definition is read-only.');
  if(change.kind==='arrival'&&(change.table!=='main'||!this.doc.room.editable))throw Error('This arrival is read-only.');
  const before=this.values(),id=key(change),next={...(this.changes.get(id)||{}),...change};
  for(const name of ['x','y','tile'])if(name in next){number(next[name]);if(!(name in base))throw Error('This command has no tile field.');if(next[name]===base[name])delete next[name];}
  if(!this.changes.has(id)&&this.changes.size>=64&&['x','y','tile'].some(k=>k in next))throw Error('At most 64 map records can be staged.');
  if(['x','y','tile'].some(k=>k in next))this.changes.set(id,next);else this.changes.delete(id);
  if(JSON.stringify(before)!==JSON.stringify(this.values())){this.past.push(before);if(this.past.length>200)this.past.shift();this.future=[];this.revision++;}
 }
 restore(values){this.changes=new Map(values.map(c=>[key(c),clone(c)]));this.revision++;}
 undo(){if(this.past.length){this.future.push(this.values());if(this.future.length>200)this.future.shift();this.restore(this.past.pop());}}
 redo(){if(this.future.length){this.past.push(this.values());if(this.past.length>200)this.past.shift();this.restore(this.future.pop());}}
 clear(){if(this.changes.size){this.past.push(this.values());if(this.past.length>200)this.past.shift();this.future=[];this.restore([]);}}
 changed(entity,kind){return {...entity,...this.changes.get(key(kind==='arrival'?{kind,table:entity.table,id:entity.id}:{kind,offset:entity.offset}))};}
}

export function cropMap(center=[15,31],overview=false){return overview?{x:0,y:0,width:64,height:64,scale:4}:{x:Math.max(0,Math.min(48,Math.round(center[0])-8)),y:Math.max(0,Math.min(52,Math.round(center[1])-6)),width:16,height:12,scale:16};}
export function mapPoint(crop,rect,point){if(rect.width<=0||rect.height<=0)return null;const x=Math.floor((point.x-rect.left)/rect.width*crop.width),y=Math.floor((point.y-rect.top)/rect.height*crop.height);return x>=0&&y>=0&&x<crop.width&&y<crop.height?[crop.x+x,crop.y+y]:null;}
export function mapPixels(map,crop,cells=map.cells){
 const scale=crop.scale||16,width=crop.width*scale,height=crop.height*scale;if(width*height>1024*1024||cells?.length!==4096)throw Error('Map preview exceeds supported bounds.');
 const pixels=new Uint8ClampedArray(width*height*4),palette=map.palette||[[255,255,255],[170,170,170],[85,85,85],[0,0,0]];
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){const sx=crop.x+Math.floor(x/scale),sy=crop.y+Math.floor(y/scale),tile=map.tiles[cells[sy*64+sx]],px=Math.floor(x%scale*16/scale),py=Math.floor(y%scale*16/scale),rgb=palette[tile?.[py*16+px]];if(!rgb)throw Error('Missing decoded map tile or color index.');pixels.set([...rgb,255],(y*width+x)*4);}
 return {width,height,pixels};
}

function selected(view){const [kind,value,extra]=String(view.selection||'').split(':');if(!view.model)return null;const doc=view.model.doc;const entity=kind==='command'?doc.map.commands.find(c=>c.offset===Number(value)):kind==='npc'?doc.objects.find(n=>n.offset===Number(value)):kind==='arrival'?doc.arrivals.find(a=>a.table===value&&a.id===Number(extra)):null;return entity?{kind,entity}:null;}
function targetKey(kind,e){return kind==='arrival'?`arrival:${e.table}:${e.id}`:`${kind}:${e.offset}`;}
function currentTarget(view){const chosen=selected(view);return chosen?{...chosen,entity:view.model.changed(chosen.entity,chosen.kind)}:null;}
function requestFields(view){const chosen=selected(view);if(!chosen)throw Error('Select an existing command, NPC or arrival.');const data={kind:chosen.kind,...(chosen.kind==='arrival'?{table:chosen.entity.table,id:chosen.entity.id}:{offset:chosen.entity.offset}),x:number(read('maps-x')),y:number(read('maps-y'))};if(chosen.kind==='command'&&'tile' in chosen.entity)data.tile=number(read('maps-tile'));return data;}
function canEdit(view,chosen){return !!chosen&&view.model.doc.room.editable&&(chosen.kind==='arrival'?chosen.entity.table==='main':chosen.entity.editable);}
function savedChanges(ctx,sha){
 const text=ctx.draft('game-map-changes','{}');if(text==='{}'||!text)return {changes:{}};
 try{if(typeof text!=='string'||text.length>65536)throw Error();const data=JSON.parse(text);if(!data||data.version!==1||data.source_sha256!==sha||!data.changes_by_header||typeof data.changes_by_header!=='object'||Array.isArray(data.changes_by_header)||Object.keys(data).some(k=>!['version','source_sha256','changes_by_header'].includes(k)))throw Error();
  if(Object.entries(data.changes_by_header).some(([header,values])=>header!==String(0x486b)||!Array.isArray(values)||values.length>64))throw Error();return {changes:data.changes_by_header};
 }catch{return {changes:{},note:'Saved map edits were ignored because their source, header or fields no longer match.'};}
}

export async function gameMaps(ctx,{simpleAvailable=false}={}){
 const {state}=ctx,scope=selectionKey(state),params={...ctx.sourceParams()};
 let view=state.gameMapsView;if(view?.scope!==scope){const saved=savedChanges(ctx,state.artifact.sha256);view={scope,header:0x486b,offset:0,query:'',request:0,reviewSerial:0,pending:null,models:new Map(),overview:false,mode:'inspect',center:null,saved:saved.changes,draftNote:saved.note,active:true,epoch:1};state.gameMapsView=view;}
 if(!view.active){view.active=true;view.epoch=(view.epoch||0)+1;}
 const epoch=view.epoch;
 const current=()=>scope===selectionKey(state)&&state.gameMapsView===view&&view.active&&view.epoch===epoch&&(state.page===undefined||state.page==='levels');
 const invalidate=()=>{view.pending=null;view.reviewSerial++;};
 const persist=()=>{if(!current())return;const changes_by_header={};for(const [header,model] of view.models){const values=model.values();if(header===0x486b&&model.doc.source_sha256===state.artifact.sha256&&values.length)changes_by_header[String(header)]=values;}ctx.setDraft('game-map-changes',JSON.stringify({version:1,source_sha256:state.artifact.sha256,changes_by_header}));state.historyEditor='maps-edit';};
 view.persist=persist;
 const choose=value=>{view.selection=value;view.formDirty=false;const target=currentTarget(view);if(target)view.center=[target.entity.x,target.entity.y];};
 ctx.use({
  'maps-open-room':node=>{if(!current())return;const header=number(node.dataset.id,0x6f7f);if(header<0x4800)throw Error('Unknown room header.');view.header=header;view.selection=null;view.center=null;view.formDirty=false;view.inspection=undefined;view.request++;invalidate();return ctx.render();},
  'maps-search':()=>{if(!current())return;const query=read('maps-query').trim();if(query.length>128)throw Error('Search is limited to 128 characters.');view.query=query;view.offset=0;view.catalog=undefined;view.request++;return ctx.render();},
  'maps-page':node=>{if(!current())return;const offset=number(node.dataset.id,10000);if(offset>=view.catalog?.total&&offset!==0)throw Error('This map page is no longer available.');view.offset=offset;view.catalog=undefined;view.request++;return ctx.render();},
  'maps-simple':()=>{if(!current()||!simpleAvailable)return;invalidate();view.request++;view.active=false;view.epoch++;ctx.setDraft('ffl2-map-mode','simple');return ctx.render();},
  'maps-select':()=>{if(!current())return;choose(read('maps-target'));return ctx.render();},
  'maps-overview':()=>{if(!current())return;view.overview=!view.overview;return ctx.render();},
  'maps-pan':node=>{if(!current())return;const [dx,dy]=String(node.dataset.id).split(',').map(Number);if(![[8,0],[-8,0],[0,6],[0,-6]].some(p=>p[0]===dx&&p[1]===dy))throw Error('Unknown viewport direction.');const c=view.center||[15,31];view.center=[Math.max(0,Math.min(63,c[0]+dx)),Math.max(0,Math.min(63,c[1]+dy))];view.overview=false;return ctx.render();},
  'maps-mode':()=>{if(!current())return;const value=read('maps-mode');if(!['inspect','place'].includes(value))throw Error('Unknown map tool.');view.mode=value;return ctx.render();},
  'maps-stage':()=>{if(!current()||!view.model)return;if(!canEdit(view,selected(view)))throw Error('This map definition is read-only.');view.model.stage(requestFields(view));view.formDirty=false;invalidate();persist();return ctx.render();},
  'maps-undo':()=>{if(current()&&view.model){view.model.undo();view.formDirty=false;invalidate();persist();return ctx.render();}},
  'maps-redo':()=>{if(current()&&view.model){view.model.redo();view.formDirty=false;invalidate();persist();return ctx.render();}},
  'maps-clear':()=>{if(current()&&view.model){view.model.clear();view.formDirty=false;invalidate();persist();return ctx.render();}},
  'maps-review':async()=>{
   if(!current()||!view.model||!view.model.values().length)throw Error('Stage a map edit first.');
   if(view.formDirty)throw Error('Stage the changed coordinate fields before reviewing.');
   const model=view.model,header=view.header,changes=model.values(),signature=JSON.stringify(changes),revision=model.revision,serial=++view.reviewSerial;view.pending=null;
   const result=await ctx.run('games.maps.plan',{...params,header,changes},{render:false,refresh:false});
   if(!current()||view.header!==header||view.model!==model||view.reviewSerial!==serial||model.revision!==revision||JSON.stringify(model.values())!==signature)return;
   if(result.ok===false||result.source_sha256!==state.artifact.sha256)throw Error('Map review does not match the selected ROM. Review again.');
   view.pending={scope,header,signature,revision,result};return ctx.render();
  },
  'maps-build':async()=>{
   const pending=view.pending,model=view.model;
   if(!current()||view.formDirty||!pending||pending.scope!==scope||pending.header!==view.header||pending.revision!==model?.revision||pending.signature!==JSON.stringify(model.values()))throw Error('Review the current map changes first.');
   const result=await ctx.run('build.apply',{...ctx.projectParams(),plan_id:pending.result.plan_id},{render:false,refresh:false});
   if(!current())return;
   await ctx.refreshProject?.();if(!current())return;
   if(view.model!==model||view.pending!==pending||model.revision!==pending.revision||JSON.stringify(model.values())!==pending.signature){persist();ctx.notify('Separate map build created. Your newer edits remain staged.');return ctx.render();}
   model.restore([]);view.pending=null;persist();await ctx.setArtifact(result.artifact_id);ctx.notify('Separate map build created. Playtest its story and door routes before exporting.');
  }
 });
 const token=++view.request,header=view.header,offset=view.offset,query=view.query;
 const valid=()=>current()&&view.request===token&&view.header===header&&view.offset===offset&&view.query===query&&(!ctx.isCurrentRender||ctx.isCurrentRender());
 const tasks=[view.catalog?Promise.resolve(view.catalog):ctx.api.call('games.maps.catalog',{...params,offset,limit:12,query}),view.inspection?.room?.header===header?Promise.resolve(view.inspection):ctx.api.call('games.maps.inspect',{...params,header,state:null})];
 const [catalogResult,inspectResult]=await Promise.allSettled(tasks);if(!valid())return '';
 const response=result=>{if(result.status==='rejected')return {error:result.reason?.message||'Map inspection failed.'};if(result.value.source_sha256!==state.artifact.sha256)return {error:'Map response belongs to a different source. Reopen the map browser.'};return result.value;};
 const catalogDoc=response(catalogResult),doc=response(inspectResult);if(catalogDoc.error)return `<section class="card"><h3>Game maps unavailable</h3><p>${esc(catalogDoc.error)}</p></section>`;
 view.catalog=catalogDoc;
 if(!doc.error){view.inspection=doc;if(doc.map.status==='decoded'){let model=view.models.get(header);if(!model){model=new MapDraft(doc);try{for(const change of view.saved?.[String(header)]||[])model.stage(change);}catch{model=new MapDraft(doc);view.draftNote='Saved map edits were ignored because a definition or field no longer matches.';}view.models.set(header,model);}view.model=model;state.gameMapEditor=model;if(model.values().length)state.historyEditor='maps-edit';if(!selected(view)){const target=doc.map.commands.find(c=>c.offset===0x20375&&c.editable)||doc.map.commands.find(c=>c.editable)||doc.arrivals[0];view.selection=target?targetKey('op'in target?'command':'arrival',target):null;}if(!view.center){const target=currentTarget(view),arrival=doc.arrivals.find(a=>a.id===0x1fd)||doc.arrivals[0];view.center=target?[target.entity.x,target.entity.y]:arrival?[arrival.x,arrival.y]:[32,32];}}else{view.model=null;state.gameMapEditor=null;}}
 const counts=catalogDoc.counts||{},rows=catalogDoc.rooms||[],end=Math.min(catalogDoc.total,offset+rows.length);
 const browser=`<section class="card game-map-browser"><div class="card-heading"><h3>Real game maps</h3>${simpleAvailable?button('Bedroom shortcut','maps-simple'):''}</div><p>${counts.rooms||0} room definitions · ${counts.maps||0} shared terrain streams · ${counts.arrivals||0} arrivals. Names remain address labels where no game name is proven.</p>${view.draftNote?`<p class="notice">${esc(view.draftNote)}</p>`:''}<div class="field-row">${field('maps-query','Find room or terrain address',query)}${button('Search maps','maps-search')}</div><div class="resource-grid game-map-catalog">${rows.map(r=>`<article class="card"><h4>${esc(r.label)}</h4>${r.thumbnail?.status==='available'?`<img width="96" height="96" src="${esc(r.thumbnail.data_url)}" alt="Decoded terrain overview for ${esc(r.label)}"><small>${esc(r.thumbnail.palette_status)}</small>`:`<p class="subtle">Preview unavailable: ${esc(r.thumbnail?.reason||'Unknown format')}</p>`}<p>${r.object_count} NPC definitions · ${r.arrival_count} arrivals</p>${button(r.header===header?'Viewing this room':'Inspect room','maps-open-room',{id:String(r.header),primary:r.header===header})}</article>`).join('')}</div><div class="actions">${button('Previous maps','maps-page',{id:String(Math.max(0,offset-12)),disabled:offset===0})}<span>${rows.length?offset+1:0}–${end} of ${catalogDoc.total}</span>${button('Next maps','maps-page',{id:String(offset+12),disabled:end>=catalogDoc.total})}</div></section>`;
 if(doc.error)return browser+`<section class="card"><h3>Room unavailable</h3><p>${esc(doc.error)}</p></section>`;
 if(doc.map.status!=='decoded')return browser+`<section class="card"><h3>${esc(doc.room.label)}</h3><p class="notice">Terrain preview unavailable: ${esc(doc.map.reason)}</p><p>Conditional terrain needs an explicit game-state value. Unsupported circle paths remain unavailable. No state is assumed.</p>${definitions(doc)}</section>`;
 const model=view.model,chosen=currentTarget(view),editable=canEdit(view,chosen),pending=view.pending?.revision===model.revision&&view.pending.signature===JSON.stringify(model.values())?view.pending:null;
 const options=[...doc.map.commands.filter(c=>'x'in c).map(c=>[targetKey('command',c),`${c.name||'Command'} ${hex(c.offset)}${c.editable?'':' · read-only'}`]),...doc.objects.map(n=>[targetKey('npc',n),objectName(doc.room,n)+(n.editable?'':' · conditional/read-only')]),...doc.arrivals.map(a=>[targetKey('arrival',a),`Arrival ${a.table} ${hex(a.id)}`])];
 const form=chosen?`<aside class="card game-map-inspector"><h3>${chosen.kind==='npc'?esc(objectName(doc.room,chosen.entity)):chosen.kind==='arrival'?'Arrival position':'Existing terrain command'}</h3>${select('maps-target','Selection',options,view.selection)}<div class="field-row">${field('maps-x','X · 0–63',chosen.entity.x,{type:'number',min:0,readonly:!editable})}${field('maps-y','Y · 0–63',chosen.entity.y,{type:'number',min:0,readonly:!editable})}${chosen.kind==='command'&&'tile'in chosen.entity?field('maps-tile','Tile · 0–63',chosen.entity.tile,{type:'number',min:0,readonly:!editable}):''}</div>${chosen.kind==='npc'?`<p class="notice">NPCs are stored definitions. Their conditions may hide them in Playtest.${chosen.entity.event===0x112?' Mother participates in the opening story. Moving her can affect the narrative; playtest the full conversation.':''}</p>`:''}${chosen.kind==='command'?`<p>${chosen.entity.final_cells||0} final terrain cells currently come from this command. Later commands can overwrite its drawing.</p><p>Edits preserve collision behavior, region bits and existing trigger bindings. Changes that fail these checks are refused.</p>`:''}${chosen.kind==='arrival'?'<p>Changes only the arrival position. Destination, facing and packed flags stay protected. Enter through its real door when playtesting.</p>':''}${button('Stage position / tile','maps-stage',{disabled:!editable,reason:'This definition is read-only; writable scope is the initial shared atlas.'})}</aside>`:'<p>Select an existing terrain command, NPC definition or arrival.</p>';
 return browser+`<section class="card game-map-workbench"><h3>${header===0x486b?'Opening bedroom / shared interiors':esc(doc.room.label)}</h3><p>Terrain ${hex(doc.room.map_pointer)} · shared by ${doc.room.shared_headers.map(hex).join(', ')}. A terrain edit affects every listed definition.</p>${!doc.map.palette?'<p class="notice">Color-index grayscale preview. This room’s live palette has not been verified.</p>':''}<div class="field-row">${select('maps-mode','Canvas tool',[['inspect','Inspect terrain command'],['place','Place selected definition']],view.mode)}${button(view.overview?'Return to readable crop':'Show full overview','maps-overview')}${button('Left','maps-pan',{id:'-8,0'})}${button('Right','maps-pan',{id:'8,0'})}${button('Up','maps-pan',{id:'0,-6'})}${button('Down','maps-pan',{id:'0,6'})}</div><div class="level-editor-layout game-map-layout"><div><div class="preview-pair game-map-previews"><div><span>Original for this edit · selected ROM</span><canvas id="maps-original" aria-label="Original decoded game terrain"></canvas></div><div><span>${pending?.result.preview_map?'Reviewed terrain · exact planned bytes':'Staged placement overlay'}</span><canvas id="maps-edit" tabindex="0" aria-label="Decoded game map: inspect or place selected definition"></canvas></div></div><p id="maps-position" role="status">Readable crop around (${view.center.join(', ')}). NPC and arrival markers are outlines, not character artwork.</p><p>${pending?.result.preview_map?'The reviewed terrain comes from the server’s bounded decoder.':'Placement outlines show staged coordinates. Review computes exact terrain, including restored and overwritten cells.'}</p></div>${form}</div><div class="actions">${button('Undo staged edit','maps-undo',{disabled:!model.past.length})}${button('Redo staged edit','maps-redo',{disabled:!model.future.length})}${button('Clear staged edits','maps-clear',{disabled:!model.values().length})}${button('Review map changes','maps-review',{disabled:!model.values().length,primary:!pending})}</div><p>${model.values().length} staged records. The selected ROM remains unchanged.</p>${pending?review(pending.result):''}${definitions(doc)}</section>`;
}

function definitions(doc){return `<details><summary>NPC conditions and interactions</summary><p>These records are conditional definitions, not a list of characters guaranteed to be visible now. Interaction destinations remain read-only.</p><table><thead><tr><th>NPC definition</th><th>Position</th><th>Condition</th></tr></thead><tbody>${doc.objects.map(n=>`<tr><td>${esc(objectName(doc.room,n))}</td><td>${n.x}, ${n.y}</td><td>${esc(n.state_status||'Live condition unobserved')}</td></tr>`).join('')}</tbody></table><table><thead><tr><th>Interaction</th><th>Destination</th></tr></thead><tbody>${doc.links.map(l=>`<tr><td>${l.index}</td><td>${l.transition.kind==='saved-return'?'Saved return to the previous location':l.destination?`Room ${esc(hex(l.destination.header))} · ${l.destination.x}, ${l.destination.y}`:`Event reference ${esc(hex(l.word))} · not a direct room destination`}</td></tr>`).join('')}</tbody></table></details>`;}
function review(plan){return `<section class="game-review"><h3>Review map changes</h3><p>${plan.edits.length} checked byte spans${plan.integrity_edit_count?` including ${plan.integrity_edit_count} integrity updates`:''}. A separate build needs its own door and story playtests.</p><details><summary>Exact changed bytes</summary><table><thead><tr><th>Offset</th><th>Before</th><th>After</th></tr></thead><tbody>${plan.edits.map(e=>`<tr><td>${hex(e.offset)}</td><td><code>${esc(e.before)}</code></td><td><code>${esc(e.after)}</code></td></tr>`).join('')}</tbody></table></details>${button('Create separate map build','maps-build',{primary:true})}</section>`;}

export function mountGameMaps(ctx){
 const view=ctx.state.gameMapsView;if(!view||view.scope!==selectionKey(ctx.state)||!view.model)return;
 const original=document.getElementById('maps-original'),canvas=document.getElementById('maps-edit');if(!canvas||!original)return;
 const scope=view.scope,epoch=view.epoch,current=()=>scope===selectionKey(ctx.state)&&ctx.state.gameMapsView===view&&view.active&&view.epoch===epoch&&(ctx.state.page===undefined||ctx.state.page==='levels');
 const map=view.model.doc.map,crop=cropMap(view.center,view.overview),pending=view.pending?.revision===view.model.revision?view.pending:null;
 function draw(node,cells,editing){const image=mapPixels(map,crop,cells),g=node.getContext('2d');node.width=image.width;node.height=image.height;node.style.imageRendering='pixelated';node.style.maxWidth='100%';const frame=g.createImageData(image.width,image.height);frame.data.set(image.pixels);g.putImageData(frame,0,0);rememberPreview(node,image.width,image.height,frame.data,{note:'Map tile graphics only; entity markers are separate overlays.'});
  const scale=crop.scale,doc=view.model.doc,objects=editing?(pending?.result.preview_objects||doc.objects.map(n=>view.model.changed(n,'npc'))):doc.objects,arrivals=editing?(pending?.result.preview_arrivals||doc.arrivals.map(a=>view.model.changed(a,'arrival'))):doc.arrivals;
  const mark=(entity,color,label)=>{if(entity.x<crop.x||entity.y<crop.y||entity.x>=crop.x+crop.width||entity.y>=crop.y+crop.height)return;const x=(entity.x-crop.x)*scale,y=(entity.y-crop.y)*scale;g.strokeStyle=color;g.lineWidth=1;g.strokeRect(x+1,y+1,scale-2,scale-2);if(scale>=12&&g.fillText){g.fillStyle=color;g.font='10px sans-serif';g.fillText(label,x+2,y+11);}};
  arrivals.forEach(a=>mark(a,'#3ba9ff','A'));objects.forEach(n=>mark(n,'#ffbc49','N'));const chosen=editing?currentTarget(view):selected(view);if(chosen)mark(chosen.entity,'#f7478c','•');
 }
 draw(original,map.cells,false);draw(canvas,pending?.result.preview_map?.cells||map.cells,true);
 canvas.addEventListener('click',event=>{if(!current())return;const point=mapPoint(crop,canvas.getBoundingClientRect(),{x:event.clientX,y:event.clientY});if(!point)return;const [x,y]=point;if(view.mode==='place'){const chosen=selected(view);if(!canEdit(view,chosen))return ctx.notify('Select an editable existing command, NPC or arrival first.');view.model.stage({kind:chosen.kind,...(chosen.kind==='arrival'?{table:chosen.entity.table,id:chosen.entity.id}:{offset:chosen.entity.offset}),x,y});view.formDirty=false;view.pending=null;view.reviewSerial++;view.persist();}else{const offset=(pending?.result.preview_map?.provenance||map.provenance)[y*64+x];if(map.commands.some(c=>c.offset===offset))view.selection=`command:${offset}`;}view.center=[x,y];ctx.render();});
 for(const [id,action] of [['maps-target','maps-select'],['maps-mode','maps-mode']])document.getElementById(id)?.addEventListener('change',()=>{if(!current())return;if(action==='maps-select'){view.selection=read(id);view.formDirty=false;const chosen=currentTarget(view);if(chosen)view.center=[chosen.entity.x,chosen.entity.y];}else view.mode=read(id);ctx.render();});
 for(const id of ['maps-x','maps-y','maps-tile'])document.getElementById(id)?.addEventListener('input',()=>{if(!current())return;view.formDirty=true;view.pending=null;view.reviewSerial++;document.querySelectorAll?.('[data-action="maps-build"]').forEach(node=>node.disabled=true);const status=document.getElementById('maps-position');if(status)status.textContent='Fields changed. Stage position / tile, then review again.';});
}
