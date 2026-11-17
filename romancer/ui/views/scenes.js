// Scenes & colors: pick a color in a recorded moment of the game and see every
// scene the change reaches, re-rendered by the real engine, before saving.
import {playtestCreatedBuild} from '../build_handoff.js';
import {icon} from '../icons.js';
import {esc,button,badge,heading,requireProject,empty} from '../common.js';
import {plural,hex,parseHex,levelIndex,snapColor,pickerSummary,swatchesForPixel,groupSwatches,sameColors,swatchLabel,changeLine,KEY_BUTTONS,offsetText} from '../scene_editor.js';

const pictures=new Map();
const PAD=[['up','Up'],['down','Down'],['left','Left'],['right','Right'],['a','A'],['b','B'],['start','Start'],['select','Select']];
const SLOT_NAMES=['Lightest slot','Light slot','Dark slot','Darkest slot'];

function editorFor(ctx){
 const {state}=ctx,scope=[state.project.project_id,state.artifact.artifact_id,state.artifact.sha256].join(':');
 if(state.sceneEditor?.scope!==scope){stopLoops(state.sceneEditor);state.sceneEditor={scope,params:ctx.sourceParams(),summary:null,sceneId:null,view:null,selected:null,draft:null,proposal:null,inspect:null,matches:[],scopeChoice:'all',playing:false,held:new Set(),ticket:0};}
 return state.sceneEditor;
}
function stopLoops(ed){if(!ed)return;ed.ticket++;ed.playing=false;clearTimeout(ed.poll);clearTimeout(ed.proposeTimer);clearTimeout(ed.lookPoll);clearTimeout(ed.recordPoll);}
const current=(ctx,ed)=>ctx.state.sceneEditor===ed&&ctx.state.page==='scenes';
const call=(ctx,ed,operation,more={})=>ctx.api.call('edits.'+operation,{...ed.params,...more});
function picture(ctx,ed,key){
 const id=ed.scope+'|'+key;let loading=pictures.get(id);
 if(!loading){
  loading=call(ctx,ed,'image',{key}).then(result=>new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('This picture could not be shown.'));image.src='data:image/png;base64,'+result.png_base64;}));
  loading.catch(()=>pictures.delete(id));pictures.set(id,loading);
  if(pictures.size>800)pictures.delete(pictures.keys().next().value);
 }
 return loading;
}
const chips=colors=>`<span class="scene-chips">${colors.map(color=>`<span class="scene-chip" data-color="${hex(color)}"></span>`).join('')}</span>`;
const selectedSwatch=ed=>ed.view?.swatches.find(swatch=>swatch.id===ed.selected)||null;
const shownChange=ed=>ed.proposal||ed.inspect;

// ---- parts of the screen; each is redrawn on its own while replays report in

function galleryPart(ed){
 const summary=ed.summary,recording=summary.recording,running=recording?.state==='running',engine=summary.engine;
 return `<div class="card-heading"><h3>Scenes</h3>${badge(plural(summary.scenes.length,'scene')+' recorded',summary.scenes.length?'good':'neutral')}</div>
 <p class="subtle">A scene is a moment of the game that ROMancer has watched. When you change something, every scene that uses the same data is shown. Scenes you haven't recorded can't be shown, so record the places you care about.</p>
 <div class="actions">${running?button('Stop recording','scene-record-stop'):button('Record more scenes','scene-record',{primary:!summary.scenes.length,icon:'plus',disabled:!engine.installed,reason:engine.reason})}${button(ed.playing?'Stop playing':'Play and capture a moment','scene-play-toggle',{icon:'playtest',disabled:!engine.installed||running,reason:engine.installed?'Wait for recording to finish, or stop it.':engine.reason})}</div>
 ${recording?`<div class="scene-progress" role="status" aria-live="polite">${running?`<progress max="${recording.total}" value="${recording.done}" aria-label="Recording progress"></progress>`:''}<span>${esc(recording.message)}${running&&recording.found?' '+plural(recording.found,'new scene')+' so far.':''}</span></div>`:''}
 <div class="scene-strip" role="group" aria-label="Recorded scenes">${summary.scenes.map(row=>`<button type="button" class="scene-thumb ${row.id===ed.sceneId?'selected':''}" data-action="scene-open" data-id="${row.id}" aria-pressed="${row.id===ed.sceneId}"><img alt="" data-picture="${esc(row.image)}" width="${row.width}" height="${row.height}"><span>${esc(row.label)}</span></button>`).join('')||`<p class="subtle">No scenes yet. Record more scenes lets the game play by itself for a few minutes; Play and capture lets you go where you want.</p>`}</div>`;
}
function playPart(ed){
 if(!ed.playing)return '';
 return `<div class="card-heading"><h3>Play the game</h3>${badge('LIVE','good')}</div><div class="scene-play"><div id="scene-controller" tabindex="0" role="application" aria-label="Game screen. Arrow keys move. Z is the A button, X is B, Enter is Start, Shift is Select."><canvas id="scene-play-canvas" class="scene-canvas" width="160" height="144"></canvas></div><div><p>Click the game, then play with the keyboard: arrow keys, <kbd>Z</kbd> for A, <kbd>X</kbd> for B, <kbd>Enter</kbd> for Start, <kbd>Shift</kbd> for Select. Or tap a button:</p><div class="actions scene-pad">${PAD.map(([id,label])=>button(label,'scene-tap',{id})).join('')}</div><div class="actions">${button('Capture this moment','scene-capture',{primary:true,icon:'plus'})}${button('Stop playing','scene-play-toggle')}</div><p class="subtle" id="scene-play-status" role="status" aria-live="polite">Starting the game…</p></div></div>`;
}
function alsoPart(ed){
 const change=shownChange(ed);if(!change)return '';
 const tone=change.error||(!change.working&&!change.verified)?'notice warm':'notice';
 return `<h4>Also changes <small>${esc(change.title)}</small></h4><p class="${tone}" role="status" aria-live="polite">${esc(change.verdict)}</p>
 <p>${badge(change.badge,change.scene_count>1?'warm':'neutral')} ${esc(change.coverage)}</p>
 <div class="scene-strip" role="group" aria-label="Scenes that use the same data">${change.affected.map((row,index)=>`<button type="button" class="scene-thumb ${row.visible?'flagged':''} ${row.state==='working'?'working':''}" data-action="scene-compare" data-id="${index}"><img alt="" data-picture="${esc(row.after||row.before)}" width="${row.width}" height="${row.height}"><span>${esc(row.label)}${row.edited_here?' (this scene)':''}</span><small>${esc(row.status)}</small></button>`).join('')}</div>
 <p class="subtle">Each picture is the real game replayed with your change. Choose one to compare before and after.</p>
 <details><summary>Details</summary><p>${plural(change.bytes,'byte')} in the ROM ${change.bytes===1?'changes':'change'}.</p><div class="table-wrap"><table><thead><tr><th>Place in the file</th><th>Before</th><th>After</th></tr></thead><tbody>${change.details.map(row=>`<tr><td>${offsetText(row.file_offset)}</td><td>${row.before.toString(16).toUpperCase().padStart(2,'0')}</td><td>${row.after.toString(16).toUpperCase().padStart(2,'0')}</td></tr>`).join('')}</tbody></table></div>${change.notes?.length?`<p>${change.notes.map(esc).join(' ')}</p>`:''}</details>`;
}
function stagePart(ed){
 const view=ed.view;if(!view)return `<h3>Scene</h3><p class="subtle">Record a scene, then choose it above to see its colors.</p>`;
 return `<div class="card-heading"><h3>${esc(view.scene.label)}</h3><span id="scene-look">${ed.showOriginal?badge('ORIGINAL'):''}</span></div>
 <canvas id="scene-canvas" class="scene-canvas scene-pickable" width="${view.scene.width}" height="${view.scene.height}" data-action="scene-pick-pixel" role="img" aria-label="The game screen in this scene. Click a pixel to select its color, or choose a color from the palette list."></canvas>
 <div class="actions">${button(ed.showOriginal?'Show with my changes':'Show original','scene-toggle-original')}${button('Forget this scene','scene-forget')}</div>
 <p class="subtle">Click any pixel to pick the color under it, or choose from the palette.</p><div id="scene-also">${alsoPart(ed)}</div>`;
}
function palettePart(ed){
 const view=ed.view;if(!view)return '';
 const matches=new Set(ed.matches),locked=view.swatches.filter(swatch=>!swatch.editable).length;
 return `<div class="card-heading"><h3>Colors in this scene</h3>${badge(plural(view.swatches.length-locked,'color')+' you can change','good')}</div>
 ${groupSwatches(view.swatches).map(group=>`<div class="scene-palette-group"><h4>${esc(group.name)}</h4><div class="scene-swatches">${group.items.map(swatch=>`<button type="button" class="scene-swatch ${swatch.editable?'':'locked'} ${swatch.id===ed.selected?'selected':''} ${matches.has(swatch.id)?'match':''}" data-action="scene-select" data-id="${esc(swatch.id)}" aria-pressed="${swatch.id===ed.selected}" aria-label="${esc(swatchLabel(swatch))}" title="${esc(swatchLabel(swatch))}">${chips(swatch.pending||swatch.colors)}${swatch.editable?'':icon('lock','scene-lock')}${swatch.pending?'<span class="scene-dot" aria-hidden="true"></span>':''}</button>`).join('')}</div></div>`).join('')}
 ${locked?`<p class="subtle">${icon('lock','scene-lock-inline')} ${plural(locked,'color')} ${locked===1?'is':'are'} locked. Choose one to see why.</p>`:''}`;
}
function pickerControls(ed,swatch,picker){
 const draft=ed.draft;
 if(picker.kind==='master'){const hidden=new Set(picker.hidden);return `<div class="scene-master" role="group" aria-label="${esc(picker.label)}">${picker.colors.map((color,index)=>hidden.has(index)?'':`<button type="button" class="scene-master-color ${sameColors(color,draft[0])?'selected':''}" data-action="scene-master" data-id="${index}" aria-pressed="${sameColors(color,draft[0])}" aria-label="NES color ${index+1}" title="NES color ${index+1}"><span class="scene-chip" data-color="${hex(color)}"></span></button>`).join('')}</div>`;}
 if(picker.kind==='shades')return `<div class="scene-shades">${draft.map((color,slot)=>`<div role="group" aria-label="${SLOT_NAMES[slot]}"><span>${SLOT_NAMES[slot]}</span>${picker.colors.map((shade,index)=>`<button type="button" class="scene-master-color ${sameColors(shade,color)?'selected':''}" data-action="scene-shade" data-id="${index}" data-slot="${slot}" aria-pressed="${sameColors(shade,color)}" aria-label="${SLOT_NAMES[slot]}: ${['white','light gray','dark gray','black'][index]}"><span class="scene-chip" data-color="${hex(shade)}"></span></button>`).join('')}</div>`).join('')}</div>`;
 const top=picker.levels.length-1;
 return `<div class="scene-levels">${['Red','Green','Blue'].map((name,channel)=>`<label><span>${name}</span><input type="range" min="0" max="${top}" step="1" value="${levelIndex(draft[0][channel],picker.levels)}" data-channel="${channel}" aria-label="${name}, 0 to ${top}"><output data-channel-value="${channel}">${levelIndex(draft[0][channel],picker.levels)}</output></label>`).join('')}<label class="scene-any"><span>Or pick any color; it snaps to the nearest one this system can show</span><input type="color" value="${hex(draft[0])}" data-any-color aria-label="Pick any color"></label></div>`;
}
function pickerPart(ed){
 const swatch=selectedSwatch(ed);
 if(!swatch)return `<h3>Change a color</h3><p class="subtle">Choose a color from the palette, or click a pixel in the picture.</p>`;
 if(!swatch.editable)return `<div class="card-heading"><h3>${esc(swatch.name)}</h3>${badge('LOCKED','warm')}</div><p>${chips(swatch.colors)}</p><p class="notice">${icon('lock','scene-lock-inline')} This color can't be changed here. ${esc(swatch.locked_reason)}</p>`;
 const picker=ed.view.pickers[swatch.format],proposal=ed.proposal?.swatch===swatch.id&&ed.proposal.scene_id===ed.sceneId?ed.proposal:null,support=ed.summary.private_copy;
 const unchanged=sameColors(ed.draft,swatch.colors),ready=proposal&&!proposal.working&&!proposal.error;
 return `<div class="card-heading"><h3>${esc(swatch.name)}</h3>${badge('Used in '+plural(swatch.uses,'scene'),swatch.uses>1?'warm':'neutral')}</div>
 <div class="scene-before-after"><div><small>Now</small>${chips(swatch.colors)}</div><div aria-hidden="true">${icon('arrow')}</div><div><small>New</small><span id="scene-draft-chips">${chips(ed.draft)}</span></div></div>
 <p id="scene-draft-text" class="subtle" role="status" aria-live="polite">${esc(pickerSummary(ed.draft,picker))}</p>
 <p class="subtle">${esc(picker.help)}</p>${pickerControls(ed,swatch,picker)}
 <fieldset class="scene-scope"><legend>Where should it change?</legend><label><input type="radio" name="scene-scope" value="all" ${ed.scopeChoice==='all'||!support.available?'checked':''}> Everywhere this color is used (${plural(swatch.uses,'recorded scene')})</label><label class="${support.available?'':'scene-disabled'}"><input type="radio" name="scene-scope" value="only_this" ${support.available?'':'disabled'} ${ed.scopeChoice==='only_this'&&support.available?'checked':''}> Only in this scene</label>${support.available?'<p class="subtle">Only this scene gives it a private copy of the data. ROMancer checks by replay that the other scenes stay as they are.</p>':`<p class="subtle">${esc(support.reason)}</p>`}</fieldset>
 ${proposal?`<p class="${proposal.error||(!proposal.working&&!proposal.verified)?'notice warm':'notice'}" role="status" aria-live="polite">${esc(proposal.verdict)}</p>`:''}
 <div class="actions">${proposal?button('Keep this change','scene-keep',{primary:true,icon:'check',disabled:!ready,reason:proposal.error?'This change could not be made.':'Wait until every scene has been re-rendered.'})+button('Cancel','scene-cancel'):button('Show what changes','scene-propose',{primary:true,disabled:unchanged,reason:'Choose a different color first.'})}</div>
 <details><summary>Details</summary><p>This color is read from ${plural(swatch.details.filter(Boolean).length,'byte')} of the ROM${swatch.status==='code'?', written as a value inside the game code':''}.</p><ul>${swatch.details.filter(Boolean).map(row=>`<li>Place in the file: ${offsetText(row.file_offset)}</li>`).join('')}</ul>${swatch.notes.map(note=>`<p>${esc(note)}</p>`).join('')}</details>`;
}
function changesPart(ed){
 const list=ed.summary.changes;
 return `<div class="card-heading"><h3>Change list</h3>${badge(list.summary,list.changes.length?'good':'neutral')}</div>
 ${list.changes.map(change=>`<div class="scene-change"><div>${change.from_rgb?chips(change.from_rgb)+icon('arrow','scene-arrow')+chips(change.to_rgb):icon('assets')}</div><div><strong>${esc(change.title)}</strong><small>${esc(changeLine(change))}${change.verified||change.working?'':' Not confirmed by replay.'}</small></div><div class="actions">${button(ed.inspect?.id===change.id?'Hide scenes':'Show scenes','scene-inspect',{id:change.id})}${button('Undo','scene-undo',{id:change.id})}</div></div>`).join('')||'<p class="subtle">Changes you keep are listed here. Nothing is written until you review and save.</p>'}
 <div class="actions">${button('Review and save','scene-review',{primary:true,icon:'download',disabled:!list.changes.length||!!ed.summary.preview,reason:list.changes.length?'Keep or cancel the color you are trying first.':'Keep a change first.'})}</div>`;
}
const PARTS={'scene-gallery':galleryPart,'scene-play-panel':playPart,'scene-stage':stagePart,'scene-palette':palettePart,'scene-picker':pickerPart,'scene-changes':changesPart};

function paint(root){for(const node of root.querySelectorAll('[data-color]'))node.style.backgroundColor=node.dataset.color;}
function loadPictures(ctx,ed,root){
 for(const node of root.querySelectorAll('img[data-picture]')){const key=node.dataset.picture;picture(ctx,ed,key).then(image=>{if(node.isConnected&&node.dataset.picture===key)node.src=image.src;}).catch(()=>{});}
}
async function drawStage(ctx,ed){
 const canvas=document.getElementById('scene-canvas');if(!canvas||!ed.view)return;
 const own=ed.proposal?.affected.find(row=>row.scene_id===ed.sceneId&&row.after);
 const key=ed.showOriginal?ed.view.scene.image:own?own.after:ed.view.look.image;
 try{
  const image=await picture(ctx,ed,key);if(!canvas.isConnected)return;
  canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
  if(!ed.pixels||ed.pixels.id!==ed.sceneId){
   const original=await picture(ctx,ed,ed.view.scene.image),buffer=document.createElement('canvas');buffer.width=original.naturalWidth;buffer.height=original.naturalHeight;
   const context=buffer.getContext('2d',{willReadFrequently:true});context.drawImage(original,0,0);ed.pixels={id:ed.sceneId,data:context.getImageData(0,0,buffer.width,buffer.height)};
  }
 }catch{}
}
const PAGE_PARTS=Object.keys(PARTS).filter(id=>id!=='scene-play-panel');
function update(ctx,ed,ids=PAGE_PARTS){
 if(!current(ctx,ed)||!ed.summary)return;
 const focused=document.activeElement,focusKey=focused?.dataset?.action?[focused.dataset.action,focused.dataset.id||'',focused.dataset.slot||''].join('|'):null;
 for(const id of ids){
  const node=document.getElementById(id);if(!node)continue;
  const had=node.contains(focused);node.innerHTML=PARTS[id](ed);node.hidden=!node.innerHTML;paint(node);loadPictures(ctx,ed,node);
  if(had&&focusKey){const [action,key,slot]=focusKey.split('|');[...node.querySelectorAll('[data-action]')].find(candidate=>candidate.dataset.action===action&&(candidate.dataset.id||'')===key&&(candidate.dataset.slot||'')===slot)?.focus({preventScroll:true});}
 }
 if(ids.includes('scene-stage'))void drawStage(ctx,ed);
 watchLook(ctx,ed);
}
// Two or more kept changes in one scene are re-rendered together; fetch that picture when it is ready.
function watchLook(ctx,ed){
 clearTimeout(ed.lookPoll);if(!ed.view||ed.view.look.state!=='working'||ed.proposal)return;
 ed.lookPoll=setTimeout(async()=>{
  if(!current(ctx,ed)||ed.proposal||!ed.sceneId)return;
  try{const id=ed.sceneId,view=await call(ctx,ed,'scene',{scene_id:id});if(!current(ctx,ed)||ed.sceneId!==id||ed.proposal)return;ed.view=view;void drawStage(ctx,ed);watchLook(ctx,ed);}catch{}
 },600);
}
function updateAlso(ctx,ed){
 const node=document.getElementById('scene-also');if(!node||!current(ctx,ed))return update(ctx,ed,['scene-stage']);
 const focused=document.activeElement,index=node.contains(focused)?focused.dataset?.id:null;
 node.innerHTML=alsoPart(ed);paint(node);loadPictures(ctx,ed,node);
 if(index!==null&&index!==undefined)node.querySelector(`[data-action="scene-compare"][data-id="${index}"]`)?.focus({preventScroll:true});
 void drawStage(ctx,ed);
}

// ---- talking to the session

async function loadScene(ctx,ed,sceneId){
 ed.sceneId=sceneId;ed.view=sceneId?await call(ctx,ed,'scene',{scene_id:sceneId}):null;ed.matches=[];
 if(ed.selected&&!selectedSwatch(ed)){ed.selected=null;ed.draft=null;}
 const swatch=selectedSwatch(ed);if(swatch&&!ed.proposal)ed.draft=(swatch.pending||swatch.colors).map(color=>[...color]);
}
async function refresh(ctx,ed,summary){
 ed.summary=summary||await call(ctx,ed,'open');
 if(!ed.summary.scenes.some(row=>row.id===ed.sceneId))ed.sceneId=ed.summary.scenes[0]?.id||null;
 ed.proposal=ed.summary.preview&&ed.proposal?.id===ed.summary.preview.id?ed.proposal:ed.summary.preview;
 if(ed.inspect&&!ed.summary.changes.changes.some(change=>change.id===ed.inspect.id))ed.inspect=null;
 await loadScene(ctx,ed,ed.sceneId);
}
async function dropPreview(ctx,ed){
 clearTimeout(ed.proposeTimer);
 if(ed.proposal&&ed.proposal.state==='preview'){const id=ed.proposal.id;ed.proposal=null;try{ed.summary=await call(ctx,ed,'remove',{change_id:id});}catch{}}
}
function watchProposal(ctx,ed){
 clearTimeout(ed.poll);
 const tick=async()=>{
  if(!current(ctx,ed)||!ed.proposal||!ed.proposal.working)return;
  try{
   const id=ed.proposal.id,change=(await call(ctx,ed,'change',{change_id:id})).change;
   if(!current(ctx,ed)||ed.proposal?.id!==id)return;
   const settled=!change.working;ed.proposal=change;updateAlso(ctx,ed);
   if(settled){ed.summary.preview=change;update(ctx,ed,['scene-picker']);return;}
  }catch(error){ctx.notify(error.message,true);return;}
  ed.poll=setTimeout(tick,400);
 };
 ed.poll=setTimeout(tick,300);
}
async function propose(ctx,ed){
 clearTimeout(ed.proposeTimer);
 const swatch=selectedSwatch(ed);if(!swatch||!swatch.editable||!ed.draft)return;
 if(sameColors(ed.draft,swatch.colors)){await dropPreview(ctx,ed);update(ctx,ed,['scene-stage','scene-picker','scene-changes']);return;}
 const result=await call(ctx,ed,'propose_color',{scene_id:ed.sceneId,domain:swatch.domain,entry:swatch.entry,colors:ed.draft,scope:ed.scopeChoice});
 if(!current(ctx,ed))return;
 ed.proposal=result.change;ed.inspect=null;ed.summary.preview=result.change;ed.showOriginal=false;
 update(ctx,ed,['scene-stage','scene-picker','scene-changes']);watchProposal(ctx,ed);
}
function schedulePropose(ctx,ed){clearTimeout(ed.proposeTimer);ed.proposeTimer=setTimeout(()=>propose(ctx,ed).catch(error=>ctx.notify(error.message,true)),500);}
function setDraft(ctx,ed,colors,{redraw=false}={}){
 ed.draft=colors;const swatch=selectedSwatch(ed),picker=ed.view.pickers[swatch.format];
 if(redraw)update(ctx,ed,['scene-picker']);
 else{const holder=document.getElementById('scene-draft-chips');if(holder){holder.innerHTML=chips(colors);paint(holder);}const text=document.getElementById('scene-draft-text');if(text)text.textContent=pickerSummary(colors,picker);}
 schedulePropose(ctx,ed);
}
function watchRecording(ctx,ed){
 clearTimeout(ed.recordPoll);
 const tick=async()=>{
  if(!current(ctx,ed))return;
  try{
   const before=ed.summary.scenes.length,summary=await call(ctx,ed,'open');if(!current(ctx,ed))return;
   ed.summary=summary;
   if(summary.recording?.state==='running'){update(ctx,ed,['scene-gallery']);ed.recordPoll=setTimeout(tick,500);return;}
   if(!ed.sceneId&&summary.scenes.length)await loadScene(ctx,ed,summary.scenes[0].id);
   update(ctx,ed,before||ed.sceneId?['scene-gallery','scene-stage','scene-palette','scene-picker']:undefined);
   if(summary.recording?.message)ctx.notify(summary.recording.message,summary.recording.state==='failed');
  }catch(error){ctx.notify(error.message,true);}
 };
 ed.recordPoll=setTimeout(tick,400);
}
async function playLoop(ctx,ed){
 const ticket=++ed.ticket;let due=performance.now();
 while(ed.playing&&ed.ticket===ticket&&current(ctx,ed)){
  const status=document.getElementById('scene-play-status');
  try{
   const taps=ed.taps||[];ed.taps=[];
   const packet=await call(ctx,ed,'play',{frames:taps.length?10:4,buttons:[...new Set([...ed.held,...taps])]});
   if(!ed.playing||ed.ticket!==ticket||!current(ctx,ed))break;
   if(packet.busy){if(status)status.textContent=packet.message+(packet.progress?` (${Math.round(100*packet.progress[0]/Math.max(1,packet.progress[1]))}%)`:'');await new Promise(resolve=>setTimeout(resolve,400));due=performance.now();continue;}
   const canvas=document.getElementById('scene-play-canvas');
   if(canvas){if(canvas.width!==packet.width||canvas.height!==packet.height){canvas.width=packet.width;canvas.height=packet.height;}const image=new Image();image.onload=()=>{if(canvas.isConnected)canvas.getContext('2d').drawImage(image,0,0);};image.src='data:image/png;base64,'+packet.png_base64;}
   if(status)status.textContent='Playing. Capture the moment when the screen shows what you want to edit.';
   due=Math.max(due+(taps.length?10:4)*1000/60,performance.now()-50);await new Promise(resolve=>setTimeout(resolve,Math.max(0,due-performance.now())));
  }catch(error){ed.playing=false;ctx.notify(error.message,true);update(ctx,ed,['scene-gallery','scene-play-panel']);break;}
 }
}

// ---- dialogs

function compareDialog(ctx,ed,row){
 ctx.modal(row.label,`<p>${esc(row.status)}${row.note?' '+esc(row.note):''}</p><canvas id="scene-compare-canvas" class="scene-canvas" width="${row.width}" height="${row.height}" role="img" aria-label="Before and after, split at the slider"></canvas><label class="scene-slider"><span>Before</span><input type="range" min="0" max="100" value="50" data-compare aria-label="Slide from before to after"><span>After</span></label><div class="actions">${button('Show before','scene-compare-set',{id:'0'})}${button('Show after','scene-compare-set',{id:'100'})}${button('Close','close-modal')}</div><details><summary>Details</summary><p>${row.replayed_from_frame===null||row.replayed_from_frame===undefined?'The replay did not reach this scene.':'Replayed in the real engine from a savestate '+plural(Math.max(0,Math.round((ed.summary.scenes.find(scene=>scene.id===row.scene_id)?.frame-row.replayed_from_frame)/60)),'second')+' earlier.'} ${plural(row.pixels,'pixel')} changed.</p></details>`);
 const canvas=document.getElementById('scene-compare-canvas'),slider=document.querySelector('#modal [data-compare]');
 const draw=async()=>{
  try{const [before,after]=await Promise.all([picture(ctx,ed,row.before),picture(ctx,ed,row.after||row.before)]);if(!canvas.isConnected)return;
   const context=canvas.getContext('2d'),split=Math.round(canvas.width*Number(slider.value)/100);context.drawImage(before,0,0);
   if(split>0)context.drawImage(after,0,0,split,canvas.height,0,0,split,canvas.height);
   if(split>0&&split<canvas.width){context.fillStyle='#ffffff';context.fillRect(split-1,0,1,canvas.height);}
  }catch{}
 };
 slider.addEventListener('input',draw);ed.compareSet=value=>{slider.value=value;draw();};void draw();
}
function reviewBody(review){
 return `<p class="notice" role="status">${esc(review.headline)}</p><p>${esc(review.coverage)}</p>${review.unverified.length?`<p class="notice warm">Not confirmed by replay: ${review.unverified.map(esc).join('; ')}. These may not do what you expect.</p>`:''}
 <h3>${plural(review.changes.length,'change')}</h3>${review.changes.map(change=>`<div class="scene-change"><div>${change.from_rgb?chips(change.from_rgb)+icon('arrow','scene-arrow')+chips(change.to_rgb):icon('assets')}</div><div><strong>${esc(change.title)}</strong><small>${esc(changeLine(change))}</small></div></div>`).join('')}
 <h3>Everything that changes</h3><div class="scene-review-grid">${review.scenes.map(scene=>`<figure class="${scene.visible?'flagged':''}"><figcaption><strong>${esc(scene.label)}</strong><small>${scene.state==='working'?'Re-rendering…':scene.visible?'Looks different':'Uses changed data; nothing visible at this moment'}</small></figcaption><div class="scene-pair"><div><small>Before</small><img alt="Before" data-picture="${esc(scene.before)}" width="${scene.width}" height="${scene.height}"></div><div><small>After</small><img alt="After" data-picture="${esc(scene.after)}" width="${scene.width}" height="${scene.height}"></div></div></figure>`).join('')}</div>
 <p class="subtle">${esc(review.writes_note)}</p>
 <details><summary>Details</summary><p>${plural(review.bytes,'byte')} will be written.</p>${review.details.map(change=>`<p><strong>${esc(change.title)}</strong></p><div class="table-wrap"><table><thead><tr><th>Place in the file</th><th>Before</th><th>After</th></tr></thead><tbody>${change.writes.map(row=>`<tr><td>${offsetText(row.file_offset)}</td><td>${row.before.toString(16).toUpperCase().padStart(2,'0')}</td><td>${row.after.toString(16).toUpperCase().padStart(2,'0')}</td></tr>`).join('')}</tbody></table></div>`).join('')}</details>
 <div class="actions">${button(review.ready?'Save as a new build':'Re-rendering scenes…','scene-save',{primary:true,icon:'download',disabled:!review.ready,reason:'Every scene is being re-rendered with all changes together.'})}${button('Keep editing','close-modal')}</div>`;
}
async function reviewDialog(ctx,ed){
 let review=await call(ctx,ed,'review'),signature='';
 const show=()=>{const next=JSON.stringify([review.ready,review.scenes.map(scene=>[scene.after,scene.state])]);if(next===signature)return;signature=next;ed.review=review;ctx.modal('Review your changes',reviewBody(review));const modal=document.getElementById('modal');paint(modal);loadPictures(ctx,ed,modal);};
 show();
 while(!review.ready&&current(ctx,ed)&&document.getElementById('modal').open&&ed.review){
  await new Promise(resolve=>setTimeout(resolve,500));
  if(!document.getElementById('modal').open)break;
  review=await call(ctx,ed,'review');show();
 }
}

// ---- the page

export async function render(ctx){
 const {state}=ctx,missing=requireProject(ctx);if(missing)return missing;
 if(!state.artifact)return empty('Import a game first','Open a project and choose the ROM whose colors you want to change.');
 const ed=editorFor(ctx);let failure='';
 try{await refresh(ctx,ed);}catch(error){failure=error.message;ed.summary=null;}
 ctx.use({
  'scene-open':async node=>{if(node.dataset.id===ed.sceneId)return;await dropPreview(ctx,ed);ed.inspect=null;ed.selected=null;ed.draft=null;ed.showOriginal=false;await loadScene(ctx,ed,node.dataset.id);update(ctx,ed);},
  'scene-select':async node=>{const id=node.dataset.id;if(ed.proposal&&ed.proposal.swatch!==id)await dropPreview(ctx,ed);ed.selected=id;ed.matches=[];const swatch=selectedSwatch(ed);ed.draft=(ed.proposal?.swatch===id?ed.proposal.to_rgb:swatch.pending||swatch.colors).map(color=>[...color]);update(ctx,ed,['scene-stage','scene-palette','scene-picker','scene-changes']);},
  'scene-pick-pixel':async(node,event)=>{
   if(!ed.pixels||ed.pixels.id!==ed.sceneId)return;
   const box=node.getBoundingClientRect(),data=ed.pixels.data,x=Math.min(data.width-1,Math.max(0,Math.floor((event.clientX-box.left)*data.width/box.width))),y=Math.min(data.height-1,Math.max(0,Math.floor((event.clientY-box.top)*data.height/box.height))),at=(y*data.width+x)*4;
   const found=swatchesForPixel([data.data[at],data.data[at+1],data.data[at+2]],ed.view.swatches);
   if(!found.length){ctx.notify('No palette color in this scene matches that pixel.');return;}
   const ids=[...new Set(found.map(match=>match.swatch.id))],first=found[0].swatch;
   if(ed.proposal&&ed.proposal.swatch!==first.id)await dropPreview(ctx,ed);
   ed.selected=first.id;ed.matches=ids.length>1?ids:[];ed.draft=(first.pending||first.colors).map(color=>[...color]);
   update(ctx,ed,['scene-stage','scene-palette','scene-picker','scene-changes']);
   ctx.notify(ids.length>1?`${plural(ids.length,'palette color')} look like this pixel. ${first.name} is selected; the others are outlined.`:`That pixel is ${first.name}.`);
  },
  'scene-master':node=>{const picker=ed.view.pickers[selectedSwatch(ed).format];setDraft(ctx,ed,[[...picker.colors[Number(node.dataset.id)]]],{redraw:true});},
  'scene-shade':node=>{const picker=ed.view.pickers[selectedSwatch(ed).format],next=ed.draft.map(color=>[...color]);next[Number(node.dataset.slot)]=[...picker.colors[Number(node.dataset.id)]];setDraft(ctx,ed,next,{redraw:true});},
  'scene-propose':()=>propose(ctx,ed),
  'scene-keep':async()=>{const id=ed.proposal?.id;if(!id)return;clearTimeout(ed.poll);const summary=await call(ctx,ed,'keep',{change_id:id});ed.proposal=null;await refresh(ctx,ed,summary);update(ctx,ed);ctx.notify('Added to the change list. Nothing is written until you review and save.');},
  'scene-cancel':async()=>{await dropPreview(ctx,ed);const swatch=selectedSwatch(ed);if(swatch)ed.draft=(swatch.pending||swatch.colors).map(color=>[...color]);await refresh(ctx,ed);update(ctx,ed);},
  'scene-undo':async node=>{const summary=await call(ctx,ed,'remove',{change_id:node.dataset.id});if(ed.inspect?.id===node.dataset.id)ed.inspect=null;await refresh(ctx,ed,summary);const swatch=selectedSwatch(ed);if(swatch&&!ed.proposal)ed.draft=(swatch.pending||swatch.colors).map(color=>[...color]);update(ctx,ed);ctx.notify('Change undone.');},
  'scene-inspect':async node=>{if(ed.inspect?.id===node.dataset.id)ed.inspect=null;else{await dropPreview(ctx,ed);ed.inspect=(await call(ctx,ed,'change',{change_id:node.dataset.id})).change;}update(ctx,ed,['scene-stage','scene-picker','scene-changes']);document.getElementById('scene-also')?.scrollIntoView({block:'nearest'});},
  'scene-compare':node=>{const row=shownChange(ed)?.affected[Number(node.dataset.id)];if(row)compareDialog(ctx,ed,row);},
  'scene-compare-set':node=>ed.compareSet?.(node.dataset.id),
  'scene-toggle-original':()=>{ed.showOriginal=!ed.showOriginal;update(ctx,ed,['scene-stage']);},
  'scene-forget':async()=>{const summary=await call(ctx,ed,'forget_scene',{scene_id:ed.sceneId});ed.sceneId=null;ed.selected=null;await refresh(ctx,ed,summary);update(ctx,ed);ctx.notify('Scene removed.');},
  'scene-record':async()=>{ed.summary=await call(ctx,ed,'record',{steps:40,restart:false});update(ctx,ed,['scene-gallery']);watchRecording(ctx,ed);},
  'scene-record-stop':async()=>{ed.summary=await call(ctx,ed,'record_stop');update(ctx,ed,['scene-gallery']);},
  'scene-play-toggle':()=>{ed.playing=!ed.playing;ed.held.clear();ed.taps=[];update(ctx,ed,['scene-gallery','scene-play-panel']);if(ed.playing){mountController(ctx,ed);document.getElementById('scene-controller')?.focus();void playLoop(ctx,ed);}else ed.ticket++;},
  'scene-tap':node=>{(ed.taps||=[]).push(node.dataset.id);},
  'scene-capture':async()=>{const result=await call(ctx,ed,'capture',{label:''});await refresh(ctx,ed,result);await dropPreview(ctx,ed);ed.selected=null;await loadScene(ctx,ed,result.scene_id);update(ctx,ed,['scene-gallery','scene-stage','scene-palette','scene-picker','scene-changes']);ctx.notify('Captured. This moment is now a scene you can edit.');},
  'scene-review':()=>reviewDialog(ctx,ed),
  'scene-save':async()=>{
   const result=await call(ctx,ed,'save',{revision:ed.review.revision});ed.review=null;ed.inspect=null;ed.proposal=null;
   state.results['build.apply']=result;await ctx.refreshProject();await refresh(ctx,ed,result.session);update(ctx,ed);
   const patch=result.patch_export;
   ctx.modal('Saved',`<p class="notice" role="status">Saved as <strong>${esc(result.name)}</strong>. Your original ROM is unchanged.</p><p>${esc(result.checksum_note||'')}</p><p class="subtle">Playtest the build to see your colors in the running game. The scenes here belong to the original ROM, so keep editing the original and save again to make another build.</p><div class="actions">${button('Playtest saved build','scene-playtest-build',{id:result.artifact_id,primary:true,icon:'playtest'})}${patch?button('Download patch','download',{id:patch.export_id,name:patch.download_name,icon:'download'}):''}${button('Keep editing','close-modal')}</div>`);
  },
  'scene-playtest-build':node=>{ctx.closeModal();return playtestCreatedBuild(ctx,node.dataset.id);},
 });
 const title=heading('Colors','Scenes & colors','Change a color and see every scene it changes before you save.');
 if(!ed.summary)return `${title}<div class="card"><p class="error">${esc(failure)}</p></div>`;
 const engine=ed.summary.engine;
 return `${title}${engine.installed?'':`<div class="notice warm" role="status">${esc(engine.reason)}</div>`}
 <section class="card" id="scene-gallery" aria-label="Scenes">${galleryPart(ed)}</section>
 <section class="card" id="scene-play-panel" aria-label="Play the game" ${ed.playing?'':'hidden'}>${playPart(ed)}</section>
 <div class="scene-layout"><section class="card" id="scene-stage" aria-label="Scene picture">${stagePart(ed)}</section>
 <div class="scene-side"><section class="card" id="scene-picker" aria-label="Change a color">${pickerPart(ed)}</section><section class="card" id="scene-palette" aria-label="Colors in this scene" ${ed.view?'':'hidden'}>${palettePart(ed)}</section><section class="card" id="scene-changes" aria-label="Change list">${changesPart(ed)}</section></div></div>`;
}
function mountController(ctx,ed){
 const pad=document.getElementById('scene-controller');if(!pad||pad.dataset.mounted)return;pad.dataset.mounted='true';
 const key=event=>KEY_BUTTONS[event.key]||KEY_BUTTONS[event.key.toLowerCase()];
 pad.addEventListener('keydown',event=>{const name=key(event);if(name){event.preventDefault();ed.held.add(name);}});
 pad.addEventListener('keyup',event=>{const name=key(event);if(name){event.preventDefault();ed.held.delete(name);}});
 pad.addEventListener('blur',()=>ed.held.clear());
 pad.addEventListener('pointerdown',()=>pad.focus());
}
export function mount(ctx){
 const ed=ctx.state.sceneEditor,main=document.getElementById('main');if(!ed||!ed.summary||!main)return;
 paint(main);loadPictures(ctx,ed,main);void drawStage(ctx,ed);watchLook(ctx,ed);
 const picker=document.getElementById('scene-picker');
 picker?.addEventListener('input',event=>{
  const node=event.target,swatch=selectedSwatch(ed);if(!swatch||!ed.draft)return;const levels=ed.view.pickers[swatch.format].levels;
  if(node.dataset.channel!==undefined&&levels){const next=[[...ed.draft[0]]];next[0][Number(node.dataset.channel)]=levels[Number(node.value)];const output=picker.querySelector(`[data-channel-value="${node.dataset.channel}"]`);if(output)output.textContent=node.value;setDraft(ctx,ed,next);}
  if(node.dataset.anyColor!==undefined&&levels){const picked=parseHex(node.value);if(!picked)return;const next=[snapColor(picked,ed.view.pickers[swatch.format])];next[0].forEach((value,channel)=>{const range=picker.querySelector(`input[data-channel="${channel}"]`),index=levelIndex(value,levels);if(range)range.value=index;const output=picker.querySelector(`[data-channel-value="${channel}"]`);if(output)output.textContent=index;});setDraft(ctx,ed,next);}
 });
 picker?.addEventListener('change',event=>{if(event.target.name==='scene-scope'){ed.scopeChoice=event.target.value;if(ed.proposal||!sameColors(ed.draft,selectedSwatch(ed)?.colors))schedulePropose(ctx,ed);}});
 if(ed.playing){mountController(ctx,ed);void playLoop(ctx,ed);}
 if(ed.summary.recording?.state==='running')watchRecording(ctx,ed);
 if(ed.proposal?.working)watchProposal(ctx,ed);
}
