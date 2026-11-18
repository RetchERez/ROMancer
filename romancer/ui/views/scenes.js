// Scenes & colors: change a color, a picture or a background cell in a recorded
// moment of the game and see every scene the change reaches, re-rendered by the
// real engine, before saving.
import {playtestCreatedBuild} from '../build_handoff.js';
import {icon} from '../icons.js';
import {esc,button,badge,heading,requireProject,empty} from '../common.js';
import {plural,hex,parseHex,levelIndex,snapColor,pickerSummary,swatchesForPixel,groupSwatches,sameColors,swatchLabel,changeLine,KEY_BUTTONS,offsetText} from '../scene_editor.js';
import {MODES,parsePixels,pixelText,tilePalette,sameTile,flipTile,fillTile,importPixels,tileRgba,howLabel,cellAt,cellRects,bandGrid,sharedCells,cellState,builtCellsNote,layerLabel,bestLayer,checkTone,expandGraphics} from '../scene_graphics.js';

const pictures=new Map();
const PAD=[['up','Up'],['down','Down'],['left','Left'],['right','Right'],['a','A'],['b','B'],['start','Start'],['select','Select']];
const SLOT_NAMES=['Lightest slot','Light slot','Dark slot','Darkest slot'];

function editorFor(ctx){
 const {state}=ctx,scope=[state.project.project_id,state.artifact.artifact_id,state.artifact.sha256].join(':');
 if(state.sceneEditor?.scope!==scope){stopLoops(state.sceneEditor);state.sceneEditor={scope,params:ctx.sourceParams(),summary:null,sceneId:null,view:null,selected:null,draft:null,proposal:null,inspect:null,matches:[],scopeChoice:'all',playing:false,held:new Set(),ticket:0,mode:'colors',gfx:null,tile:null,hits:[],sheetAll:false,brush:{tile:null,hflip:false,vflip:false,line:-1,tool:'paint'},painted:new Map(),layer:0,cursor:null};}
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
const byteText=value=>value===null||value===undefined?'new':value.toString(16).toUpperCase().padStart(2,'0');
function verdictPart(change){
 if(change.checks?.length&&!change.error&&!change.planning)return `<div role="status" aria-live="polite">${change.checks.map(check=>`<p class="${checkTone(check.state)}"><strong>${esc(check.name)}.</strong> ${esc(check.text)}</p>`).join('')}</div>${change.method_text?`<p class="subtle">${esc(change.method_text)}${change.grows?` The ROM file gets ${plural(change.grows,'byte')} longer to make room.`:''}${change.every_scene?' The patch runs all the time, so every recorded scene was re-rendered, not only the ones that show this picture.':''}</p>`:''}`;
 const tone=change.error||(!change.working&&!change.verified)?'notice warm':'notice';
 return `<p class="${tone}" role="status" aria-live="polite">${esc(change.verdict)}${change.planning&&change.progress?.done?` (replay ${change.progress.done})`:''}</p>`;
}
function alsoPart(ed){
 const change=shownChange(ed);if(!change)return '';
 return `<h4>Also changes <small>${esc(change.title)}</small></h4>${verdictPart(change)}
 <p>${badge(change.badge,change.scene_count>1?'warm':'neutral')} ${esc(change.coverage)}</p>
 <div class="scene-strip" role="group" aria-label="Scenes that use the same data">${change.affected.map((row,index)=>`<button type="button" class="scene-thumb ${row.visible?'flagged':''} ${row.state==='working'?'working':''}" data-action="scene-compare" data-id="${index}"><img alt="" data-picture="${esc(row.after||row.before)}" width="${row.width}" height="${row.height}"><span>${esc(row.label)}${row.edited_here?' (this scene)':''}</span><small>${esc(row.status)}</small></button>`).join('')}</div>
 <p class="subtle">Each picture is the real game replayed with your change. Choose one to compare before and after.</p>
 <details><summary>Details</summary><p>${plural(change.bytes,'byte')} in the ROM ${change.bytes===1?'changes':'change'}.</p><div class="table-wrap"><table><thead><tr><th>Place in the file</th><th>Before</th><th>After</th></tr></thead><tbody>${change.details.map(row=>`<tr><td>${offsetText(row.file_offset)}</td><td>${byteText(row.before)}</td><td>${byteText(row.after)}</td></tr>`).join('')}</tbody></table></div>${change.bytes>change.details.length?`<p>Only the first ${change.details.length} are listed.</p>`:''}${change.notes?.length?`<p>${change.notes.map(esc).join(' ')}</p>`:''}${change.tried?.length?`<p>Tried first: ${change.tried.map(esc).join(' ')}</p>`:''}</details>`;
}
const STAGE_LABEL={colors:'The game screen in this scene. Click a pixel to select its color, or choose a color from the palette list.',graphics:'The game screen in this scene. Click a pixel to open the picture under it, or choose a picture from the list.',background:'The game screen in this scene with a grid over its background cells. Click or drag to paint cells with the chosen picture. With the keyboard: arrow keys move, Space paints.'};
const STAGE_HINT={colors:'Click any pixel to pick the color under it, or choose from the palette.',graphics:'Click any pixel to open the 8 by 8 picture under it. The game builds its screen from these pictures, so changing one changes every place it is drawn.',background:'The grid shows the background cells. Choose a picture, then click or drag over cells to paint them. Cells outlined with dashes are stored together with a painted cell and change with it.'};
const modePart=ed=>`<div class="scene-modes" role="group" aria-label="What to change">${MODES.map(([id,label,hint])=>`<button type="button" class="scene-mode ${ed.mode===id?'selected':''}" data-action="scene-mode" data-id="${id}" aria-pressed="${ed.mode===id}" title="${esc(hint)}">${esc(label)}</button>`).join('')}</div>`;
function hitsPart(ed){
 if(ed.mode!=='graphics'||ed.hits.length<2)return '';
 return `<div class="actions" role="group" aria-label="Pictures under that pixel"><span class="subtle">More than one picture is drawn there:</span>${ed.hits.map((hit,index)=>`<button type="button" data-action="scene-hit" data-id="${index}" aria-pressed="${hit.tile===ed.tile?.id}">${esc(hit.label)}</button>`).join('')}</div>`;
}
function stagePart(ed){
 const view=ed.view;if(!view)return `<h3>Scene</h3><p class="subtle">Record a scene, then choose it above to see its colors.</p>`;
 const scale=Math.max(2,Math.floor(1280/view.scene.width));
 return `<div class="card-heading"><h3>${esc(view.scene.label)}</h3><span id="scene-look">${ed.showOriginal?badge('ORIGINAL'):''}</span></div>${modePart(ed)}
 <div class="scene-stagewrap" id="scene-stagewrap" ${ed.mode==='background'?'tabindex="0"':''}><canvas id="scene-canvas" class="scene-canvas scene-pickable" width="${view.scene.width}" height="${view.scene.height}" data-action="scene-pick-pixel" role="img" aria-label="${STAGE_LABEL[ed.mode]}"></canvas><canvas id="scene-overlay" class="scene-overlay" width="${view.scene.width*scale}" height="${view.scene.height*scale}" aria-hidden="true"></canvas></div>
 ${hitsPart(ed)}<div class="actions">${button(ed.showOriginal?'Show with my changes':'Show original','scene-toggle-original')}${button('Forget this scene','scene-forget')}</div>
 <p class="subtle">${STAGE_HINT[ed.mode]}</p><div id="scene-also">${alsoPart(ed)}</div>`;
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
function lockedPart(ed,swatch){
 const elsewhere=swatch.elsewhere||[],proposal=ed.proposal?.swatch===swatch.id&&ed.proposal.scene_id===ed.sceneId&&ed.proposal.found?ed.proposal:null,picker=ed.view.pickers[swatch.format];
 const ready=proposal&&!proposal.working&&!proposal.error;
 return `<div class="card-heading"><h3>${esc(swatch.name)}</h3>${badge(swatch.pending?'CHANGED':'LOCKED','warm')}</div><p>${chips(swatch.pending||swatch.colors)}</p><p class="notice">${icon('lock','scene-lock-inline')} This color can't be changed here. ${esc(swatch.locked_reason)}</p>
 ${elsewhere.length?`<p>The same palette slot is not locked in ${elsewhere.length===1?'this scene':'these scenes'}. If the game shows this color there without the fade, change it there:</p><div class="actions">${elsewhere.map(row=>`<button type="button" data-action="scene-goto" data-id="${esc(row.scene_id)}" data-name="${esc(row.swatch)}">${chips(row.colors)} ${esc(row.label)}</button>`).join('')}</div>`:''}
 ${swatch.findable&&picker&&ed.draft?`<h4>Or let ROMancer look for it</h4><p class="subtle">Pick the color you want. ROMancer then looks for where the game keeps this color: a stored copy of the palette, a place another scene traced it to, or bytes near where it was traced. It replays the game for each one and keeps the change only if a replay shows this color following yours.</p>
 <div class="scene-before-after"><div><small>Now</small>${chips(swatch.colors)}</div><div aria-hidden="true">${icon('arrow')}</div><div><small>New</small><span id="scene-draft-chips">${chips(ed.draft)}</span></div></div>
 <p id="scene-draft-text" class="subtle" role="status" aria-live="polite">${esc(pickerSummary(ed.draft,picker))}</p>${pickerControls(ed,swatch,picker)}
 ${proposal?verdictPart(proposal):''}
 <div class="actions">${proposal?button('Keep this change','scene-keep',{primary:true,icon:'check',disabled:!ready,reason:proposal.error?'This change could not be made.':'Wait until the search and the replays have finished.'})+button('Cancel','scene-cancel'):button('Try to find where this color comes from','scene-find-color',{primary:true})}</div>`:''}`;
}
function pickerPart(ed){
 const swatch=selectedSwatch(ed);
 if(!swatch)return `<h3>Change a color</h3><p class="subtle">Choose a color from the palette, or click a pixel in the picture.</p>`;
 if(!swatch.editable)return lockedPart(ed,swatch);
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
 <div class="actions">${button('Review and save','scene-review',{primary:true,icon:'download',disabled:!list.changes.length||!!ed.summary.preview,reason:list.changes.length?'Keep or cancel the change you are trying first.':'Keep a change first.'})}</div>`;
}
// ---- pictures and backgrounds: what each panel shows

const SHEET_COLS=10,SHEET_CELL=36;
const TOOLS=[['pencil','Pencil'],['pick','Pick color'],['fill','Fill']],BRUSH_TOOLS=[['paint','Paint'],['pick','Pick from the scene'],['erase','Unpaint']];
const READING='<p class="subtle" role="status">Reading the pictures of this scene…</p>';
const tileById=(ed,id)=>ed.gfx?.tiles.find(tile=>tile.id===id)||null;
const selectedTile=ed=>ed.tile?tileById(ed,ed.tile.id):null;
const currentLayer=ed=>ed.gfx?.layers.find(layer=>layer.index===ed.layer)||null;
const tileChange=ed=>ed.proposal&&ed.proposal.kind==='graphics'&&ed.proposal.scene_id===ed.sceneId?ed.proposal:null;
const cellChange=ed=>ed.proposal&&ed.proposal.kind==='background'&&ed.proposal.scene_id===ed.sceneId?ed.proposal:null;
const tilePixels=(tile,original=false)=>parsePixels(!original&&tile.pending?tile.pending.pixels:tile.pixels,tile.bits);
function sheetTiles(ed){
 if(!ed.gfx)return [];
 const layer=ed.mode==='background'?currentLayer(ed):null,chosen=ed.mode==='background'?ed.brush.tile:ed.tile?.id;
 return ed.gfx.tiles.filter(tile=>(!layer||tile.domain===layer.tile_domain&&tile.format===layer.tile_format)&&(ed.sheetAll||tile.on_screen||tile.id===chosen));
}
function sheetPart(ed){
 if(!ed.view)return '';
 if(!ed.gfx)return `<h3>Pictures in this scene</h3>${READING}`;
 const tiles=sheetTiles(ed),rows=Math.max(1,Math.ceil(tiles.length/SHEET_COLS)),chosen=tileById(ed,ed.mode==='background'?ed.brush.tile:ed.tile?.id);
 return `<div class="card-heading"><h3>Pictures in this scene</h3>${badge(plural(tiles.length,'picture'),'neutral')}</div>
 <p class="subtle">${ed.mode==='background'?'Choose the picture to paint with.':'Choose a picture to redraw, or click it in the scene.'} Dimmed pictures are locked; choose one to see why. A dot marks a picture you have changed.</p>
 <div class="scene-sheetwrap"><canvas id="scene-sheet" class="scene-sheet" width="${SHEET_COLS*SHEET_CELL}" height="${rows*SHEET_CELL}" tabindex="0" role="application" data-action="scene-sheet-pick" aria-label="Pictures in this scene, ${SHEET_COLS} across. Arrow keys move from picture to picture; the chosen one ${ed.mode==='background'?'becomes the brush':'opens in the editor'}."></canvas></div>
 <p class="subtle" id="scene-sheet-status" role="status" aria-live="polite">${chosen?esc(chosen.name)+' is chosen.':'No picture chosen.'}</p>
 <label class="scene-check"><input type="checkbox" data-sheet-all ${ed.sheetAll?'checked':''}> Also show pictures that are loaded but not on screen (${ed.gfx.tiles.length} in all)</label>`;
}
function scopePart(ed,uses,what,support){
 return `<fieldset class="scene-scope"><legend>Where should it change?</legend><label><input type="radio" name="scene-scope" value="all" ${ed.scopeChoice==='all'||!support.available?'checked':''}> Everywhere this ${what} is used (${plural(uses,'recorded scene')})</label><label class="${support.available?'':'scene-disabled'}"><input type="radio" name="scene-scope" value="only_this" ${support.available?'':'disabled'} ${ed.scopeChoice==='only_this'&&support.available?'checked':''}> Only in this scene</label>${support.available?'<p class="subtle">Only this scene gives it a private copy of the data. If ROMancer cannot make one, it says why and changes nothing.</p>':`<p class="subtle">${esc(support.reason)}</p>`}</fieldset>`;
}
function keepPart(proposal,propose){
 if(!proposal)return propose;
 const ready=!proposal.working&&!proposal.error;
 return button('Keep this change','scene-keep',{primary:true,icon:'check',disabled:!ready,reason:proposal.error?'This change could not be made.':'Wait until every scene has been re-rendered.'})+button('Cancel','scene-cancel');
}
function tilePart(ed){
 if(!ed.view)return '';
 if(!ed.gfx)return `<h3>Redraw a picture</h3>${READING}`;
 const tile=selectedTile(ed),state=ed.tile;
 if(!tile)return `<h3>Redraw a picture</h3><p class="subtle">Click a pixel in the scene to open the picture under it, or choose one from the pictures below.</p>${ed.hitMessage?`<p class="notice warm" role="status">${esc(ed.hitMessage)}</p>`:''}`;
 if(!tile.editable)return `<div class="card-heading"><h3>${esc(tile.name)}</h3>${badge('LOCKED','warm')}</div><canvas id="scene-tile-now" class="scene-tile-view" width="64" height="64" role="img" aria-label="The picture as it is now"></canvas><p class="notice">${icon('lock','scene-lock-inline')} This picture can't be changed here. ${esc(tile.reason)}</p>`;
 const palette=tilePalette(tile,ed.gfx.colors,state.line),proposal=tileChange(ed),clear=tile.zero==='clear';
 const inkName=index=>`Color ${index+1}${index===0&&clear?', see-through':''}`;
 return `<div class="card-heading"><h3>${esc(tile.name)}</h3>${badge('Used in '+plural(tile.uses,'scene'),tile.uses>1?'warm':'neutral')}</div>
 <p class="subtle">${badge(howLabel(tile),tile.how==='direct'?'good':'warm')} ${esc(tile.reason)}</p>
 <div class="scene-tile-edit"><canvas id="scene-tile-editor" class="scene-tile-editor" width="320" height="320" tabindex="0" role="application" aria-label="Picture editor, 8 by 8 pixels. Arrow keys move. Space or Enter uses the tool. Number keys choose a color. P is the pencil, I picks a color, F fills. Control Z undoes."></canvas>
 <div class="scene-tile-side"><div><small>Now</small><canvas id="scene-tile-now" class="scene-tile-view" width="64" height="64" role="img" aria-label="The picture as it is now"></canvas></div><div><small>New</small><canvas id="scene-tile-new" class="scene-tile-view" width="64" height="64" role="img" aria-label="The picture as you have drawn it"></canvas></div></div></div>
 <p id="scene-tile-status" class="subtle" role="status" aria-live="polite">${esc(tileStatus(ed,tile))}</p>
 <div class="scene-inks" role="group" aria-label="Colors of this picture's palette">${palette.map((color,index)=>`<button type="button" class="scene-ink ${index===state.ink?'selected':''}" data-action="scene-ink" data-id="${index}" aria-pressed="${index===state.ink}" aria-label="${inkName(index)}" title="${inkName(index)}"><span class="scene-chip" data-color="${hex(color)}"></span></button>`).join('')}</div>
 <p class="subtle">A picture can only use the colors of its palette${clear?'; the first one is see-through':''}.</p>
 <div class="actions" role="group" aria-label="Drawing tools">${TOOLS.map(([id,label])=>`<button type="button" class="${state.tool===id?'selected':''}" data-action="scene-tool" data-id="${id}" aria-pressed="${state.tool===id}">${label}</button>`).join('')}${button('Flip sideways','scene-tile-flip',{id:'h'})}${button('Flip upside down','scene-tile-flip',{id:'v'})}${button('Undo','scene-tile-undo')}${button('Start over','scene-tile-reset')}</div>
 ${tile.lines>1?`<label class="scene-line"><span>Shown with palette</span><select data-tile-line aria-label="Palette to show this picture with">${Array.from({length:tile.lines},(_,line)=>`<option value="${line}" ${line===state.line?'selected':''}>Palette ${line+1}</option>`).join('')}</select></label><p class="subtle">This only changes how the picture is shown here. The game chooses the palette wherever it draws the picture.</p>`:''}
 <div class="actions">${button('Save as PNG','scene-tile-export',{icon:'download'})}${button('Load a PNG','scene-tile-import')}<input type="file" id="scene-tile-file" accept="image/png" hidden aria-label="PNG picture to load, 8 by 8 pixels"></div>
 ${scopePart(ed,tile.uses,'picture',ed.gfx.private_copy)}
 ${proposal?verdictPart(proposal):''}
 <div class="actions">${keepPart(proposal,button('Show what changes','scene-tile-propose',{primary:true}))}</div>
 <details><summary>Details</summary><p>${tile.bits} bits per pixel (${1<<tile.bits} colors), held at video memory address ${offsetText(tile.address)}.${tile.details.length?` First byte in the file: ${offsetText(tile.details[0])}.`:''}</p>${tile.notes.map(note=>`<p>${esc(note)}</p>`).join('')}</details>`;
}
function tileStatus(ed,tile){
 const state=ed.tile,changed=!sameTile(state.draft,tilePixels(tile,true));
 return `Pixel ${state.cx+1} across, ${state.cy+1} down is color ${state.draft[state.cy*8+state.cx]+1}. ${changed?'You have changed this picture.':'Not changed yet.'}${tile.pending?' A change to it is already in your change list.':''}`;
}
function brushPart(ed){
 if(!ed.view)return '';
 if(!ed.gfx)return `<h3>Paint the background</h3>${READING}`;
 const layers=ed.gfx.layers,layer=currentLayer(ed);
 if(!layer)return `<h3>Paint the background</h3><p class="notice warm" role="status">ROMancer could not read a background layer in this scene.${ed.summary.system==='snes'?' On Super NES it needs the scroll settings recorded with the scene; record this scene again.':''}</p>`;
 const brush=ed.brush,tile=tileById(ed,brush.tile),proposal=cellChange(ed),painted=[...ed.painted.values()],shared=sharedCells(layer,painted.map(cell=>cell.index)),packed=painted.filter(cell=>cellState(layer,cell.index)==='packed').length;
 const plain=layer.counts.rom+layer.counts.code,toggle=(way,label)=>`<button type="button" class="${brush[way]?'selected':''}" data-action="scene-bg-flip" data-id="${way}" aria-pressed="${brush[way]}">${label}</button>`;
 return `<div class="card-heading"><h3>Paint the background</h3>${badge(plural(painted.length,'cell')+' painted',painted.length?'good':'neutral')}</div>
 ${layers.length>1?`<label class="scene-line"><span>Layer</span><select data-bg-layer aria-label="Background layer">${layers.map(row=>`<option value="${row.index}" ${row.index===layer.index?'selected':''}>${esc(layerLabel(row))}</option>`).join('')}</select></label>`:''}
 ${layer.placed?layer.placed_by==='registers'?`<p class="notice warm">ROMancer did not see this layer in the picture, so the grid is placed from the game's own scroll settings. It may be hidden behind another layer.</p>`:'':`<p class="notice warm" role="status">ROMancer could not find this layer on the recorded screen, so it cannot show which cell is where. Try another layer or another scene.</p>`}
 <div class="scene-brush"><div><small>Brush</small><canvas id="scene-brush-view" class="scene-tile-view" width="64" height="64" role="img" aria-label="${tile?esc(tile.name):'No picture chosen'}"></canvas></div><div><strong>${tile?esc(tile.name):'No picture chosen'}</strong><p class="subtle">Choose a picture below, or use Pick from the scene and click a cell.</p></div></div>
 <div class="actions" role="group" aria-label="Painting tools">${BRUSH_TOOLS.map(([id,label])=>`<button type="button" class="${brush.tool===id?'selected':''}" data-action="scene-bg-tool" data-id="${id}" aria-pressed="${brush.tool===id}">${label}</button>`).join('')}${layer.flips?toggle('hflip','Flip sideways')+toggle('vflip','Flip upside down'):''}</div>
 ${layer.lines>1?`<label class="scene-line"><span>Palette</span><select data-bg-line aria-label="Palette for painted cells"><option value="-1" ${brush.line<0?'selected':''}>Keep each cell's palette</option>${Array.from({length:layer.lines},(_,line)=>`<option value="${line}" ${line===brush.line?'selected':''}>Palette ${line+1}</option>`).join('')}</select></label>${layer.line_note?`<p class="subtle">${esc(layer.line_note)}</p>`:''}`:''}
 ${painted.length?`<p role="status">${plural(painted.length,'cell')} painted.${shared.length?` <strong>${plural(shared.length,'other cell')} in this scene ${shared.length===1?'is':'are'} stored in the same place in the ROM and will change too</strong> (outlined with dashes).`:''}${esc(builtCellsNote(packed))}</p>`:'<p class="subtle">Nothing painted yet.</p>'}
 ${proposal?verdictPart(proposal):''}
 <div class="actions">${keepPart(proposal,button('Show what changes','scene-bg-propose',{primary:true,disabled:!painted.length,reason:'Paint at least one cell first.'})+button('Clear painting','scene-bg-clear',{disabled:!painted.length,reason:'Nothing is painted.'}))}</div>
 <p class="subtle">In this layer ${plural(plain,'cell')} can be changed directly, ${layer.counts.derived} ${layer.counts.derived===1?'is':'are'} built by the game while it runs, and ${layer.counts.unknown} ${layer.counts.unknown===1?'is':'are'} locked (shaded) because ROMancer has not seen where ${layer.counts.unknown===1?'it comes':'they come'} from.</p>
 <details><summary>Details</summary><p>${layer.width} by ${layer.height} cells of ${layer.cell} by ${layer.cell} pixels. ${layer.placed_by==='picture'?'Placed by matching it against the recorded screen.':layer.placed_by==='registers'?"Placed from the game's scroll registers.":'Not placed.'}</p>${layer.notes.map(note=>`<p>${esc(note)}</p>`).join('')}</details>`;
}

// ---- drawing pictures, the sheet and the overlay on the scene

function inkTile(context,pixels,palette,x,y,scale,{hflip=false,vflip=false,clear=false}={}){
 for(let py=0;py<8;py++)for(let px=0;px<8;px++){
  const p=pixels[(vflip?7-py:py)*8+(hflip?7-px:px)];
  if(clear&&p===0){context.fillStyle=(px+py)%2?'#3a3a3a':'#555555';context.fillRect(x+px*scale,y+py*scale,scale,scale);continue;}
  context.fillStyle=hex(palette[p]||[0,0,0]);context.fillRect(x+px*scale,y+py*scale,scale,scale);
 }
}
function drawTileView(id,tile,pixels,line,colors){
 const canvas=document.getElementById(id);if(!canvas||!tile)return;
 inkTile(canvas.getContext('2d'),pixels,tilePalette(tile,colors,line),0,0,canvas.width/8,{clear:tile.zero==='clear'});
}
function drawSheet(ed){
 const canvas=document.getElementById('scene-sheet');if(!canvas||!ed.gfx)return;
 const context=canvas.getContext('2d'),chosen=ed.mode==='background'?ed.brush.tile:ed.tile?.id;context.clearRect(0,0,canvas.width,canvas.height);
 sheetTiles(ed).forEach((tile,index)=>{
  const x=index%SHEET_COLS*SHEET_CELL,y=Math.floor(index/SHEET_COLS)*SHEET_CELL;
  inkTile(context,tilePixels(tile),tilePalette(tile,ed.gfx.colors),x+2,y+2,4,{clear:tile.zero==='clear'});
  if(!tile.editable){context.fillStyle='rgba(0,0,0,.6)';context.fillRect(x+2,y+2,32,32);}
  if(tile.pending){context.fillStyle='#ffffff';context.fillRect(x+3,y+3,8,8);context.fillStyle='#d9480f';context.fillRect(x+4,y+4,6,6);}
  if(tile.id===chosen){context.lineWidth=2;context.strokeStyle='#ffffff';context.strokeRect(x+1,y+1,34,34);context.strokeStyle='#d9480f';context.setLineDash([4,4]);context.strokeRect(x+1,y+1,34,34);context.setLineDash([]);}
 });
}
function drawEditor(ed){
 const tile=selectedTile(ed),canvas=document.getElementById('scene-tile-editor');
 if(tile)drawTileView('scene-tile-now',tile,tilePixels(tile,true),ed.tile.line,ed.gfx.colors);
 if(!tile||!canvas)return;
 const context=canvas.getContext('2d'),state=ed.tile,cell=canvas.width/8;
 inkTile(context,state.draft,tilePalette(tile,ed.gfx.colors,state.line),0,0,cell,{clear:tile.zero==='clear'});
 context.lineWidth=1;context.strokeStyle='rgba(128,128,128,.6)';
 for(let k=1;k<8;k++){context.beginPath();context.moveTo(k*cell+.5,0);context.lineTo(k*cell+.5,canvas.height);context.moveTo(0,k*cell+.5);context.lineTo(canvas.width,k*cell+.5);context.stroke();}
 context.lineWidth=3;context.strokeStyle='#ffffff';context.strokeRect(state.cx*cell+2.5,state.cy*cell+2.5,cell-5,cell-5);context.strokeStyle='#000000';context.setLineDash([6,6]);context.strokeRect(state.cx*cell+2.5,state.cy*cell+2.5,cell-5,cell-5);context.setLineDash([]);
 drawTileView('scene-tile-new',tile,state.draft,state.line,ed.gfx.colors);
 const status=document.getElementById('scene-tile-status');if(status)status.textContent=tileStatus(ed,tile);
}
function drawBrush(ed){
 const canvas=document.getElementById('scene-brush-view'),tile=tileById(ed,ed.brush.tile);if(!canvas)return;
 const context=canvas.getContext('2d'),layer=currentLayer(ed);context.clearRect(0,0,canvas.width,canvas.height);
 if(tile)inkTile(context,tilePixels(tile),tilePalette(layer?{...tile,pal:layer.pal,zero:layer.zero}:tile,ed.gfx.colors,ed.brush.line<0?tile.line:ed.brush.line),0,0,8,{hflip:ed.brush.hflip,vflip:ed.brush.vflip,clear:tile.zero==='clear'});
}
function drawOverlay(ed){
 const overlay=document.getElementById('scene-overlay');if(!overlay||!ed.view)return;
 const context=overlay.getContext('2d'),wide=ed.view.scene.width,tall=ed.view.scene.height,scale=overlay.width/wide;
 context.clearRect(0,0,overlay.width,overlay.height);
 if(ed.showOriginal||!ed.gfx||ed.mode==='colors')return;
 const inBand=(rect,draw)=>{context.save();context.beginPath();context.rect(0,rect.first*scale,overlay.width,(rect.last-rect.first)*scale);context.clip();draw();context.restore();};
 const outline=(rect,color,dash)=>{context.lineWidth=2;context.setLineDash(dash||[]);context.strokeStyle='#000000';context.strokeRect(rect.x*scale+1,rect.y*scale+1,rect.size*scale-2,rect.size*scale-2);context.strokeStyle=color;context.strokeRect(rect.x*scale+2,rect.y*scale+2,rect.size*scale-4,rect.size*scale-4);context.setLineDash([]);};
 if(ed.mode==='graphics'){
  const tile=selectedTile(ed);
  if(tile&&ed.tile&&!tileChange(ed)&&!sameTile(ed.tile.draft,tilePixels(tile)))for(const layer of ed.gfx.layers){
   // Live preview: your drawing, everywhere this picture is on this screen. The real game is replayed when you ask to see what changes.
   if(!layer.placed||layer.cell!==8||layer.tile_domain!==tile.domain||layer.tile_format!==tile.format)continue;
   layer.cells.tile.forEach((address,index)=>{
    if(address!==tile.address)return;
    const flags=layer.cells.flags[index],palette=tilePalette({...tile,pal:layer.pal,zero:layer.zero},ed.gfx.colors,layer.cells.line[index]);
    for(const rect of cellRects(layer,index%layer.width,Math.floor(index/layer.width),wide,tall))inBand(rect,()=>inkTile(context,ed.tile.draft,palette,rect.x*scale,rect.y*scale,scale,{hflip:!!(flags&1),vflip:!!(flags&2),clear:layer.zero==='clear'}));
   });
  }
  if(ed.marker)outline({x:ed.marker[0]-.75,y:ed.marker[1]-.75,size:ed.marker[2]+1.5},'#ffffff',[6,4]);   // around the picture, not over it
  return;
 }
 const layer=currentLayer(ed);if(!layer||!layer.placed)return;
 const size=layer.cell;
 for(const band of layer.bands){
  const [xs,ys]=bandGrid(layer,band,wide);
  context.save();context.beginPath();context.rect(0,band[0]*scale,overlay.width,(band[1]-band[0])*scale);context.clip();
  // Locked cells are shaded.
  for(let top=band[0]-((band[0]+band[3])%size+size)%size;top<band[1];top+=size)for(let left=xs[0]-size;left<wide;left+=size){
   const cell=cellAt(layer,Math.max(0,left),Math.min(tall-1,Math.max(top,band[0])));
   if(cell&&cellState(layer,cell.index)==='locked'){context.fillStyle='rgba(0,0,0,.5)';context.fillRect(cell.left*scale,cell.top*scale,size*scale,size*scale);}
  }
  context.lineWidth=1;context.strokeStyle='rgba(255,255,255,.4)';context.beginPath();
  for(const x of xs){context.moveTo(x*scale+.5,band[0]*scale);context.lineTo(x*scale+.5,band[1]*scale);}
  for(const y of ys){context.moveTo(0,y*scale+.5);context.lineTo(overlay.width,y*scale+.5);}
  context.stroke();context.restore();
 }
 const draft=[...ed.painted.values()];
 for(const index of sharedCells(layer,draft.map(cell=>cell.index)))for(const rect of cellRects(layer,index%layer.width,Math.floor(index/layer.width),wide,tall))inBand(rect,()=>outline(rect,'#ffd24a',[4,4]));
 const shown=cellChange(ed)?[]:draft;
 for(const cell of draft)for(const rect of cellRects(layer,cell.cx,cell.cy,wide,tall))inBand(rect,()=>{
  const tile=tileById(ed,cell.tile),now=layer.cells.flags[cell.index];
  if(tile&&size===8&&shown.length)inkTile(context,tilePixels(tile),tilePalette({...tile,pal:layer.pal,zero:layer.zero},ed.gfx.colors,cell.line<0?layer.cells.line[cell.index]:cell.line),rect.x*scale,rect.y*scale,scale,{hflip:layer.flips?cell.hflip:!!(now&1),vflip:layer.flips?cell.vflip:!!(now&2),clear:layer.zero==='clear'});
  outline(rect,'#ffffff');
 });
 if(ed.cursor)for(const rect of cellRects(layer,ed.cursor.cx,ed.cursor.cy,wide,tall))inBand(rect,()=>outline(rect,'#66d9ff',[2,2]));
}
function drawExtras(ed){drawSheet(ed);drawEditor(ed);drawBrush(ed);drawOverlay(ed);}

const PARTS={'scene-gallery':galleryPart,'scene-play-panel':playPart,'scene-stage':stagePart,'scene-palette':ed=>ed.mode==='colors'?palettePart(ed):sheetPart(ed),'scene-picker':ed=>ed.mode==='graphics'?tilePart(ed):ed.mode==='background'?brushPart(ed):pickerPart(ed),'scene-changes':changesPart};

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
 drawOverlay(ed);
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
 drawExtras(ed);
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
 if(ed.sceneId!==sceneId){ed.gfx=null;ed.tile=null;ed.hits=[];ed.marker=null;ed.hitMessage='';ed.painted=new Map();ed.cursor=null;ed.brush.tile=null;}
 ed.sceneId=sceneId;ed.view=sceneId?await call(ctx,ed,'scene',{scene_id:sceneId}):null;ed.matches=[];
 if(ed.mode!=='colors'&&sceneId)await loadGfx(ctx,ed);
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
   const settled=!change.working,stage=change.planning!==ed.proposal.planning||!!change.error!==!!ed.proposal.error;ed.proposal=change;updateAlso(ctx,ed);
   if(stage&&!settled)update(ctx,ed,['scene-picker']);
   if(settled){ed.summary.preview=change;update(ctx,ed,['scene-picker','scene-changes']);return;}
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

// ---- pictures and backgrounds: what the pointer and the keyboard do

async function loadGfx(ctx,ed){
 const id=ed.sceneId;if(!id){ed.gfx=null;return;}
 const gfx=expandGraphics(await call(ctx,ed,'graphics',{scene_id:id}));if(ed.sceneId!==id)return;
 const first=!ed.gfx||ed.gfx.scene_id!==id;ed.gfx=gfx;
 if(ed.tile&&!tileById(ed,ed.tile.id))ed.tile=null;
 if(ed.brush.tile&&!tileById(ed,ed.brush.tile))ed.brush.tile=null;
 if(first||!currentLayer(ed))ed.layer=bestLayer(gfx.layers)?.index??0;
}
function screenPoint(ed,node,event){
 const box=node.getBoundingClientRect(),wide=ed.view.scene.width,tall=ed.view.scene.height;
 return {x:Math.min(wide-1,Math.max(0,Math.floor((event.clientX-box.left)*wide/box.width))),y:Math.min(tall-1,Math.max(0,Math.floor((event.clientY-box.top)*tall/box.height)))};
}
async function selectTile(ctx,ed,id,line){
 const tile=tileById(ed,id);if(!tile)return;
 if(ed.proposal)await dropPreview(ctx,ed);
 ed.tile={id,draft:tilePixels(tile),undo:[],ink:Math.min(1,(1<<tile.bits)-1),tool:'pencil',line:line??tile.line??0,cx:0,cy:0};
 update(ctx,ed,['scene-stage','scene-picker','scene-palette','scene-changes']);
}
// A drawing made after "Show what changes" replaces that preview; the list of changes is not touched.
function editedTile(ctx,ed){
 if(tileChange(ed))dropPreview(ctx,ed).then(()=>update(ctx,ed,['scene-stage','scene-picker','scene-changes'])).catch(()=>{});
 drawEditor(ed);drawOverlay(ed);
}
function remember(ed){const state=ed.tile;state.undo.push([...state.draft]);if(state.undo.length>64)state.undo.shift();}
function useTool(ctx,ed,x,y,stroke=false){
 const state=ed.tile,tile=selectedTile(ed);if(!state||!tile||!tile.editable)return;
 state.cx=x;state.cy=y;const at=y*8+x;
 if(state.tool==='pick'){state.ink=state.draft[at];state.tool='pencil';update(ctx,ed,['scene-picker']);return;}
 if(state.tool==='fill'){if(state.draft[at]!==state.ink){remember(ed);state.draft=fillTile(state.draft,x,y,state.ink);}}
 else if(state.draft[at]!==state.ink){if(!stroke)remember(ed);state.draft[at]=state.ink;}
 editedTile(ctx,ed);
}
function paintCell(ctx,ed,cell){
 const layer=currentLayer(ed),brush=ed.brush;if(!layer||!cell)return;
 ed.cursor={cx:cell.cx,cy:cell.cy};
 if(brush.tool==='pick'){
  const flags=layer.cells.flags[cell.index],tile=ed.gfx.tiles.find(row=>row.domain===layer.tile_domain&&row.format===layer.tile_format&&row.address===layer.cells.tile[cell.index]);
  if(!tile){ctx.notify('That cell shows an empty picture. Choose a picture from the list instead.');return;}
  Object.assign(brush,{tile:tile.id,hflip:!!(flags&1),vflip:!!(flags&2),tool:'paint'});ed.dragging=false;
  update(ctx,ed,['scene-picker','scene-palette']);ctx.notify(`The brush is now ${tile.name}.`);return;
 }
 if(cellChange(ed)){dropPreview(ctx,ed).then(()=>update(ctx,ed,['scene-stage','scene-picker','scene-changes'])).catch(()=>{});}
 if(brush.tool==='erase'){ed.painted.delete(cell.index);drawOverlay(ed);return;}
 if(cellState(layer,cell.index)==='locked'){if(!ed.dragging||!ed.warned){ed.warned=true;ctx.notify('That cell is locked: ROMancer has not seen where this part of the background comes from.');}return;}
 if(!brush.tile){if(!ed.warned){ed.warned=true;ctx.notify('Choose a picture to paint with first, from the pictures in this scene.');}return;}
 ed.painted.set(cell.index,{index:cell.index,cx:cell.cx,cy:cell.cy,tile:brush.tile,hflip:brush.hflip,vflip:brush.vflip,line:brush.line});
 drawOverlay(ed);
}
function mountGraphics(ctx,ed){
 const stage=document.getElementById('scene-stage'),picker=document.getElementById('scene-picker'),sheet=document.getElementById('scene-palette');
 const editorPoint=event=>{const box=event.target.getBoundingClientRect();return [Math.min(7,Math.max(0,Math.floor((event.clientX-box.left)*8/box.width))),Math.min(7,Math.max(0,Math.floor((event.clientY-box.top)*8/box.height)))];};
 stage?.addEventListener('pointerdown',event=>{
  if(ed.mode!=='background'||event.target.id!=='scene-canvas'||!currentLayer(ed)?.placed)return;
  ed.dragging=true;ed.warned=false;paintCell(ctx,ed,cellAt(currentLayer(ed),...Object.values(screenPoint(ed,event.target,event))));
 });
 stage?.addEventListener('pointermove',event=>{
  if(ed.mode!=='background'||event.target.id!=='scene-canvas'||!currentLayer(ed)?.placed)return;
  const cell=cellAt(currentLayer(ed),...Object.values(screenPoint(ed,event.target,event)));
  if(ed.dragging&&event.buttons)paintCell(ctx,ed,cell);else if(cell&&(ed.cursor?.cx!==cell.cx||ed.cursor?.cy!==cell.cy)){ed.cursor={cx:cell.cx,cy:cell.cy};drawOverlay(ed);}
 });
 const finish=()=>{if(ed.dragging){ed.dragging=false;update(ctx,ed,['scene-picker']);}};
 stage?.addEventListener('pointerup',finish);stage?.addEventListener('pointerleave',finish);
 stage?.addEventListener('keydown',event=>{
  if(ed.mode!=='background'||event.target.id!=='scene-stagewrap')return;
  const layer=currentLayer(ed);if(!layer?.placed)return;
  const move={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
  if(!ed.cursor){const start=cellAt(layer,Math.floor(ed.view.scene.width/2),Math.floor(ed.view.scene.height/2));if(!start)return;ed.cursor={cx:start.cx,cy:start.cy};}
  if(move){event.preventDefault();ed.cursor={cx:(ed.cursor.cx+move[0]+layer.width)%layer.width,cy:(ed.cursor.cy+move[1]+layer.height)%layer.height};drawOverlay(ed);}
  else if(event.key===' '||event.key==='Enter'){event.preventDefault();ed.warned=false;paintCell(ctx,ed,{...ed.cursor,index:ed.cursor.cy*layer.width+ed.cursor.cx});update(ctx,ed,['scene-picker']);document.getElementById('scene-stagewrap')?.focus({preventScroll:true});}
 });
 picker?.addEventListener('pointerdown',event=>{
  if(event.target.id!=='scene-tile-editor'||!ed.tile)return;
  event.preventDefault();event.target.focus({preventScroll:true});const [x,y]=editorPoint(event);ed.tile.stroke=ed.tile.tool==='pencil';if(ed.tile.stroke)remember(ed);useTool(ctx,ed,x,y,ed.tile.stroke);
 });
 picker?.addEventListener('pointermove',event=>{if(event.target.id==='scene-tile-editor'&&ed.tile?.stroke&&event.buttons){const [x,y]=editorPoint(event);useTool(ctx,ed,x,y,true);}});
 const lift=()=>{if(ed.tile)ed.tile.stroke=false;};
 picker?.addEventListener('pointerup',lift);picker?.addEventListener('pointerleave',lift);
 picker?.addEventListener('keydown',event=>{
  if(event.target.id!=='scene-tile-editor'||!ed.tile)return;
  const state=ed.tile,tile=selectedTile(ed),move={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key],key=event.key.toLowerCase();
  const refocus=()=>document.getElementById('scene-tile-editor')?.focus({preventScroll:true});
  if(move){event.preventDefault();state.cx=Math.min(7,Math.max(0,state.cx+move[0]));state.cy=Math.min(7,Math.max(0,state.cy+move[1]));drawEditor(ed);}
  else if(event.key===' '||event.key==='Enter'){event.preventDefault();useTool(ctx,ed,state.cx,state.cy);refocus();}
  else if((event.ctrlKey||event.metaKey)&&key==='z'){event.preventDefault();if(state.undo.length){state.draft=state.undo.pop();editedTile(ctx,ed);}}
  else if(!event.ctrlKey&&!event.metaKey&&!event.altKey&&{p:'pencil',i:'pick',f:'fill'}[key]){event.preventDefault();state.tool={p:'pencil',i:'pick',f:'fill'}[key];update(ctx,ed,['scene-picker']);refocus();}
  else if(/^[1-9]$/.test(event.key)&&tile&&Number(event.key)<=(1<<tile.bits)){event.preventDefault();state.ink=Number(event.key)-1;update(ctx,ed,['scene-picker']);refocus();}
 });
 picker?.addEventListener('change',async event=>{
  const node=event.target;
  if(node.dataset.tileLine!==undefined&&ed.tile){ed.tile.line=Number(node.value);update(ctx,ed,['scene-picker']);}
  if(node.dataset.bgLayer!==undefined){await dropPreview(ctx,ed);ed.layer=Number(node.value);ed.painted=new Map();ed.cursor=null;ed.brush.tile=null;update(ctx,ed,['scene-stage','scene-picker','scene-palette','scene-changes']);}
  if(node.dataset.bgLine!==undefined){ed.brush.line=Number(node.value);drawBrush(ed);}
  if(node.id==='scene-tile-file'&&node.files?.[0]&&ed.tile){
   const tile=selectedTile(ed),url=URL.createObjectURL(node.files[0]),image=new Image();
   image.onload=()=>{
    URL.revokeObjectURL(url);const buffer=document.createElement('canvas');buffer.width=8;buffer.height=8;const context=buffer.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0);
    remember(ed);ed.tile.draft=importPixels(context.getImageData(0,0,8,8).data,tilePalette(tile,ed.gfx.colors,ed.tile.line));editedTile(ctx,ed);
    ctx.notify(image.naturalWidth===8&&image.naturalHeight===8?'Picture loaded. Each pixel took the nearest color of this palette.':'That PNG is not 8 by 8 pixels, so only its top-left 8 by 8 pixels were used. Each pixel took the nearest color of this palette.');
   };
   image.onerror=()=>{URL.revokeObjectURL(url);ctx.notify('That file could not be read as a picture.',true);};image.src=url;node.value='';
  }
 });
 sheet?.addEventListener('change',event=>{if(event.target.dataset.sheetAll!==undefined){ed.sheetAll=event.target.checked;update(ctx,ed,['scene-palette']);}});
 sheet?.addEventListener('keydown',event=>{
  if(event.target.id!=='scene-sheet')return;
  const tiles=sheetTiles(ed),chosen=ed.mode==='background'?ed.brush.tile:ed.tile?.id,at=tiles.findIndex(tile=>tile.id===chosen),step={ArrowLeft:-1,ArrowRight:1,ArrowUp:-SHEET_COLS,ArrowDown:SHEET_COLS}[event.key];
  if(!step||!tiles.length)return;
  event.preventDefault();const next=tiles[Math.min(tiles.length-1,Math.max(0,at<0?0:at+step))];
  chooseFromSheet(ctx,ed,next).then(()=>document.getElementById('scene-sheet')?.focus({preventScroll:true}));
 });
}
async function chooseFromSheet(ctx,ed,tile){
 if(!tile)return;
 if(ed.mode==='background'){ed.brush.tile=tile.id;ed.brush.tool='paint';update(ctx,ed,['scene-picker','scene-palette']);return;}
 ed.marker=null;ed.hits=[];await selectTile(ctx,ed,tile.id);
}
function graphicsHandlers(ctx,ed){
 return {
  'scene-mode':async node=>{
   const mode=node.dataset.id;if(mode===ed.mode)return;
   await dropPreview(ctx,ed);ed.mode=mode;ed.inspect=null;ed.showOriginal=false;
   if(mode!=='colors'&&ed.sceneId&&(!ed.gfx||ed.gfx.scene_id!==ed.sceneId)){ed.gfx=null;update(ctx,ed);await loadGfx(ctx,ed);}
   update(ctx,ed);document.querySelector('#scene-stage [data-action="scene-mode"][aria-pressed="true"]')?.focus({preventScroll:true});
  },
  'scene-sheet-pick':(node,event)=>{
   const box=node.getBoundingClientRect(),column=Math.floor((event.clientX-box.left)*SHEET_COLS/box.width),row=Math.floor((event.clientY-box.top)*node.height/box.height/SHEET_CELL);
   return chooseFromSheet(ctx,ed,sheetTiles(ed)[row*SHEET_COLS+column]);
  },
  'scene-hit':node=>{const hit=ed.hits[Number(node.dataset.id)];if(!hit)return;ed.marker=hit.rect;return selectTile(ctx,ed,hit.tile,hit.line);},
  'scene-ink':node=>{if(!ed.tile)return;ed.tile.ink=Number(node.dataset.id);if(ed.tile.tool==='pick')ed.tile.tool='pencil';update(ctx,ed,['scene-picker']);},
  'scene-tool':node=>{if(!ed.tile)return;ed.tile.tool=node.dataset.id;update(ctx,ed,['scene-picker']);},
  'scene-tile-flip':node=>{if(!ed.tile)return;remember(ed);ed.tile.draft=flipTile(ed.tile.draft,node.dataset.id);editedTile(ctx,ed);},
  'scene-tile-undo':()=>{if(!ed.tile)return;if(!ed.tile.undo.length){ctx.notify('There is nothing to undo in this picture.');return;}ed.tile.draft=ed.tile.undo.pop();editedTile(ctx,ed);},
  'scene-tile-reset':()=>{const tile=selectedTile(ed);if(!tile)return;remember(ed);ed.tile.draft=tilePixels(tile,true);editedTile(ctx,ed);},
  'scene-tile-export':()=>{
   const tile=selectedTile(ed);if(!tile)return;
   const buffer=document.createElement('canvas');buffer.width=8;buffer.height=8;
   buffer.getContext('2d').putImageData(new ImageData(tileRgba(ed.tile.draft,tilePalette(tile,ed.gfx.colors,ed.tile.line),tile.zero==='clear'),8,8),0,0);
   buffer.toBlob(blob=>{if(!blob)return;const link=document.createElement('a'),url=URL.createObjectURL(blob);link.href=url;link.download=tile.name.replace(/[^A-Za-z0-9]+/g,'-').toLowerCase()+'.png';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);ctx.notify('Saved as an 8 by 8 PNG. Edit it in any drawing program and load it back.');},'image/png');
  },
  'scene-tile-import':()=>document.getElementById('scene-tile-file')?.click(),
  'scene-tile-propose':async()=>{
   const tile=selectedTile(ed);if(!tile||!ed.tile)return;
   if(sameTile(ed.tile.draft,tilePixels(tile,true))){ctx.notify('Draw something different first. The picture is still as the game has it.');return;}
   const result=await call(ctx,ed,'propose_tile',{scene_id:ed.sceneId,tile:tile.id,pixels:pixelText(ed.tile.draft,tile.bits),scope:ed.scopeChoice});
   if(!current(ctx,ed))return;
   ed.proposal=result.change;ed.inspect=null;ed.summary.preview=result.change;ed.showOriginal=false;
   update(ctx,ed,['scene-stage','scene-picker','scene-changes']);watchProposal(ctx,ed);
  },
  'scene-bg-tool':node=>{ed.brush.tool=node.dataset.id;update(ctx,ed,['scene-picker']);},
  'scene-bg-flip':node=>{ed.brush[node.dataset.id]=!ed.brush[node.dataset.id];update(ctx,ed,['scene-picker']);},
  'scene-bg-clear':async()=>{await dropPreview(ctx,ed);ed.painted=new Map();update(ctx,ed,['scene-stage','scene-picker','scene-changes']);},
  'scene-bg-propose':async()=>{
   const layer=currentLayer(ed);if(!layer||!ed.painted.size)return;
   const cells=[...ed.painted.values()].map(cell=>({layer:layer.index,x:cell.cx,y:cell.cy,tile:cell.tile,...(layer.flips?{hflip:cell.hflip,vflip:cell.vflip}:{}),...(cell.line>=0?{line:cell.line}:{})}));
   const result=await call(ctx,ed,'propose_cells',{scene_id:ed.sceneId,cells});
   if(!current(ctx,ed))return;
   ed.proposal=result.change;ed.inspect=null;ed.summary.preview=result.change;ed.showOriginal=false;
   update(ctx,ed,['scene-stage','scene-picker','scene-changes']);watchProposal(ctx,ed);
  },
  'scene-find-color':async()=>{
   const swatch=selectedSwatch(ed);if(!swatch||!ed.draft)return;
   if(sameColors(ed.draft,swatch.colors)){ctx.notify('Choose the color you want first.');return;}
   const result=await call(ctx,ed,'find_color',{scene_id:ed.sceneId,domain:swatch.domain,entry:swatch.entry,colors:ed.draft});
   if(!current(ctx,ed))return;
   ed.proposal=result.change;ed.inspect=null;ed.summary.preview=result.change;ed.showOriginal=false;
   update(ctx,ed,['scene-stage','scene-picker','scene-changes']);watchProposal(ctx,ed);
  },
  'scene-goto':async node=>{
   await dropPreview(ctx,ed);ed.inspect=null;ed.showOriginal=false;await loadScene(ctx,ed,node.dataset.id);
   ed.selected=node.dataset.name;const swatch=selectedSwatch(ed);ed.draft=swatch?(swatch.pending||swatch.colors).map(color=>[...color]):null;if(!swatch)ed.selected=null;
   update(ctx,ed);ctx.notify(swatch?`${swatch.name} can be changed in this scene.`:'That scene is open.');
  },
 };
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
 ${review.grows?`<p class="notice">One of these changes needs more room than the ROM has, so the saved build is ${plural(review.grows,'byte')} longer than the original.</p>`:''}<details><summary>Details</summary><p>${plural(review.bytes,'byte')} will be written.</p>${review.details.map(change=>`<p><strong>${esc(change.title)}</strong></p><div class="table-wrap"><table><thead><tr><th>Place in the file</th><th>Before</th><th>After</th></tr></thead><tbody>${change.writes.map(row=>`<tr><td>${offsetText(row.file_offset)}</td><td>${byteText(row.before)}</td><td>${byteText(row.after)}</td></tr>`).join('')}</tbody></table></div>`).join('')}</details>
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
   if(ed.mode==='background')return;      // painting follows the pointer; see mountGraphics
   if(ed.mode==='graphics'){
    if(!ed.gfx)return;
    const point=screenPoint(ed,node,event),found=await call(ctx,ed,'tile_at',{scene_id:ed.sceneId,...point});
    if(!current(ctx,ed))return;
    ed.hits=found.hits;ed.hitMessage=found.message;
    if(!found.hits.length){ed.marker=null;ed.tile=null;update(ctx,ed,['scene-stage','scene-picker','scene-palette']);ctx.notify(found.message);return;}
    const hit=found.hits[0];ed.marker=hit.rect;await selectTile(ctx,ed,hit.tile,hit.line);
    const tile=selectedTile(ed);ctx.notify(tile?`${hit.label}: ${tile.name}.${found.hits.length>1?' Another picture is drawn there too; choose between them under the scene.':''}`:hit.label);
    return;
   }
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
  'scene-keep':async()=>{const id=ed.proposal?.id;if(!id)return;clearTimeout(ed.poll);const summary=await call(ctx,ed,'keep',{change_id:id});if(ed.proposal.kind==='background')ed.painted=new Map();ed.proposal=null;await refresh(ctx,ed,summary);update(ctx,ed);ctx.notify('Added to the change list. Nothing is written until you review and save.');},
  'scene-cancel':async()=>{await dropPreview(ctx,ed);const swatch=selectedSwatch(ed);if(swatch)ed.draft=(swatch.pending||swatch.colors).map(color=>[...color]);await refresh(ctx,ed);update(ctx,ed);},
  'scene-undo':async node=>{const summary=await call(ctx,ed,'remove',{change_id:node.dataset.id});if(ed.inspect?.id===node.dataset.id)ed.inspect=null;await refresh(ctx,ed,summary);if(ed.tile&&selectedTile(ed)&&!tileChange(ed))ed.tile.draft=tilePixels(selectedTile(ed));const swatch=selectedSwatch(ed);if(swatch&&!ed.proposal)ed.draft=(swatch.pending||swatch.colors).map(color=>[...color]);update(ctx,ed);ctx.notify('Change undone.');},
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
   ctx.modal('Saved',`<p class="notice" role="status">Saved as <strong>${esc(result.name)}</strong>. Your original ROM is unchanged.</p><p>${esc(result.checksum_note||'')}</p><p class="subtle">Playtest the build to see your changes in the running game. The scenes here belong to the original ROM, so keep editing the original and save again to make another build.</p><div class="actions">${button('Playtest saved build','scene-playtest-build',{id:result.artifact_id,primary:true,icon:'playtest'})}${patch?button('Download patch','download',{id:patch.export_id,name:patch.download_name,icon:'download'}):''}${button('Keep editing','close-modal')}</div>`);
  },
  'scene-playtest-build':node=>{ctx.closeModal();return playtestCreatedBuild(ctx,node.dataset.id);},
  ...graphicsHandlers(ctx,ed),
 });
 const title=heading('Colors','Scenes & colors','Change a color, a picture or the background, and see every scene it changes before you save.');
 if(!ed.summary)return `${title}<div class="card"><p class="error">${esc(failure)}</p></div>`;
 const engine=ed.summary.engine;
 return `${title}${engine.installed?'':`<div class="notice warm" role="status">${esc(engine.reason)}</div>`}
 <section class="card" id="scene-gallery" aria-label="Scenes">${galleryPart(ed)}</section>
 <section class="card" id="scene-play-panel" aria-label="Play the game" ${ed.playing?'':'hidden'}>${playPart(ed)}</section>
 <div class="scene-layout"><section class="card" id="scene-stage" aria-label="Scene picture">${stagePart(ed)}</section>
 <div class="scene-side"><section class="card" id="scene-picker" aria-label="Editor">${PARTS['scene-picker'](ed)}</section><section class="card" id="scene-palette" aria-label="Colors and pictures in this scene" ${ed.view?'':'hidden'}>${PARTS['scene-palette'](ed)}</section><section class="card" id="scene-changes" aria-label="Change list">${changesPart(ed)}</section></div></div>`;
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
 paint(main);loadPictures(ctx,ed,main);void drawStage(ctx,ed);drawExtras(ed);mountGraphics(ctx,ed);watchLook(ctx,ed);
 const picker=document.getElementById('scene-picker');
 picker?.addEventListener('input',event=>{
  const node=event.target,swatch=selectedSwatch(ed);if(ed.mode!=='colors'||!swatch||!ed.draft)return;const levels=ed.view.pickers[swatch.format].levels;
  if(node.dataset.channel!==undefined&&levels){const next=[[...ed.draft[0]]];next[0][Number(node.dataset.channel)]=levels[Number(node.value)];const output=picker.querySelector(`[data-channel-value="${node.dataset.channel}"]`);if(output)output.textContent=node.value;setDraft(ctx,ed,next);}
  if(node.dataset.anyColor!==undefined&&levels){const picked=parseHex(node.value);if(!picked)return;const next=[snapColor(picked,ed.view.pickers[swatch.format])];next[0].forEach((value,channel)=>{const range=picker.querySelector(`input[data-channel="${channel}"]`),index=levelIndex(value,levels);if(range)range.value=index;const output=picker.querySelector(`[data-channel-value="${channel}"]`);if(output)output.textContent=index;});setDraft(ctx,ed,next);}
 });
 picker?.addEventListener('change',event=>{if(event.target.name==='scene-scope'){ed.scopeChoice=event.target.value;if(ed.mode==='colors'&&(ed.proposal||!sameColors(ed.draft,selectedSwatch(ed)?.colors)))schedulePropose(ctx,ed);else if(ed.mode==='graphics'&&tileChange(ed))dropPreview(ctx,ed).then(()=>update(ctx,ed,['scene-stage','scene-picker','scene-changes']));}});
 if(ed.playing){mountController(ctx,ed);void playLoop(ctx,ed);}
 if(ed.summary.recording?.state==='running')watchRecording(ctx,ed);
 if(ed.proposal?.working)watchProposal(ctx,ed);
}
