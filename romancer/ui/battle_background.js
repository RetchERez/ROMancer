import {badge,button,esc,setUnavailable} from './common.js';
import {playtestCreatedBuild} from './build_handoff.js';
import {loadPlaytestGame} from './runtime_setup.js';
import {selectionKey} from './tool_inputs.js';

const draftKey='battle-background-pixels';
const hexBytes=pixels=>Array.from(pixels,color=>color.toString(16)).join('');
const colorsFromHex=text=>Uint8Array.from(text,color=>Number.parseInt(color,16));

function showReview(review){
 if(!review?.fits)return '<p>ROM byte changes appear here when the draft fits.</p>';
 const rows=review.ranges.map(range=>`<tr><th scope="row">${esc(range.purpose)}</th><td><code>0x${range.offset.toString(16).toUpperCase()}</code></td><td>${range.changed_bytes}</td><td><code>${esc(range.before)}</code></td><td><code>${esc(range.after)}</code></td></tr>`).join('');
 return `<p>${review.tiles_used} of ${review.tiles_limit} tiles · ${review.encoded_bytes.toLocaleString()} of ${review.encoded_limit.toLocaleString()} graphics bytes</p>
  <div class="table-wrap"><table><thead><tr><th scope="col">What changes</th><th scope="col">ROM offset</th><th scope="col">Changed bytes</th><th scope="col">Original · first 16 bytes</th><th scope="col">Draft · first 16 bytes</th></tr></thead><tbody>${rows}</tbody></table></div>
 `;
}

export async function battleBackground(ctx){
 const {state}=ctx,artifact=state.artifact,scope=selectionKey(state);
 if(artifact.system_id!=='genesis'||artifact.size!==786432)return '';
 const current=()=>selectionKey(state)===scope&&ctx.isCurrentRender?.()!==false;
 const saved=ctx.draft(draftKey,'');
 if(state.battleBackground?.scope!==scope){
  const source=await ctx.api.call('backgrounds.inspect',ctx.sourceParams()).catch(error=>({available:false,error:error.message}));
  if(!current())return '';
  state.battleBackground={scope,source,color:1,past:[],future:[],fit:null};
  if(source.available){
   state.battleBackground.base=colorsFromHex(source.pixels);
  }
 }
 const model=state.battleBackground,{source}=model;
 if(!source.available){
  return source.error?`<section class="card"><h3>Battle background</h3><p class="error">${esc(source.error)}</p></section>`:'';
 }
 if(model.saved!==saved){
  model.draft=typeof saved==='string'&&saved.length===model.base.length&&/^[0-9a-f]+$/.test(saved)?colorsFromHex(saved):model.base.slice();
  Object.assign(model,{saved,past:[],future:[],fit:null});
 }
 const params=ctx.sourceParams();
 ctx.use({
  'battle-background-build':async node=>{
   if(model.building||!model.fit?.fits)return;
   const pixels=model.saved;
   model.building=true;
   node.disabled=true;
   let build;
   try{
    const plan=await ctx.api.call('backgrounds.plan',{...params,source_sha256:source.source_sha256,pixels});
    if(!current()||model.saved!==pixels)return;
    build=await ctx.run('build.apply',{project_id:params.project_id,plan_id:plan.plan_id},{render:false});
   }finally{model.building=false;node.disabled=!model.fit?.fits;}
   if(!current())return;
   if(model.saved!==pixels){
    ctx.notify('Playable copy saved. Your newer edits are still in the draft.');
    return;
   }
   ctx.setDraft(draftKey,'');
   const opened=await playtestCreatedBuild(ctx,build.artifact_id);
   if(opened===false||state.page!=='playtest'||state.artifact?.artifact_id!==build.artifact_id)return;
   if(state.profileAvailable)await loadPlaytestGame(ctx,build.system_id,build.artifact_id,'Playable copy loaded. Press Play.');
   else ctx.notify('Playable copy saved. Choose an emulator in Playtest to load it.');
  }
 });
 const swatches=source.palette.map((_,i)=>`<button type="button" class="battle-swatch" data-battle-color="${i}" aria-label="Palette color ${i}" aria-pressed="${i===model.color}"><span>${i.toString(16).toUpperCase()}</span></button>`).join('');
 const canvas=(name,label)=>`<figure><figcaption>${label}</figcaption><canvas width="${source.width}" height="${source.height}" id="battle-${name}" aria-label="${label} of the battle background"></canvas>${name==='draft'?'<div class="battle-fit"><p id="battle-fit" role="status"><strong class="badge"></strong><span></span></p><button id="battle-fit-retry" type="button" hidden>Retry fit check</button></div>':''}</figure>`;
 return `<section class="card battle-background" id="battle-background">
  <div class="card-heading"><h3>Battle background</h3>${badge('Phantasy Star II · Rev A','good')}</div>
  <p>Paint on the draft, or import a 320 × 128 PNG. This backdrop is shared by standard battles.</p>
  <div class="battle-pictures">${canvas('original',artifact.kind==='build'?'Selected build':'Original')}${canvas('draft','Draft')}</div>
  <div class="battle-inputs">
   <div class="battle-swatches" role="group" aria-label="Battle palette">${swatches}</div>
   <label class="field battle-brush"><span>Brush</span><select id="battle-brush"><option value="1">1 pixel</option><option value="4">4 pixels</option><option value="8">8 pixels</option></select></label>
  </div>
  <div class="actions battle-actions">
   <label class="button battle-import">Import backdrop PNG<input id="battle-png" type="file" accept="image/png,.png" aria-label="Import backdrop PNG"></label>
   <button id="battle-save" type="button">Save draft PNG</button>
   <button id="battle-undo" type="button">Undo paint</button><button id="battle-redo" type="button">Redo paint</button>
   <button id="battle-reset" type="button">Reset draft</button>
   ${button('Save playable copy','battle-background-build',{primary:true,icon:'playtest',disabled:!model.fit?.fits||model.building,reason:'Make an edit that fits before saving.'})}
   ${artifact.kind==='build'?button('Open in Playtest','navigate',{id:'playtest',icon:'playtest'}):''}
  </div>
  <p class="preview-caption" id="battle-status" role="status"></p>
  <details class="battle-review" id="battle-technical"><summary>Technical details</summary><div id="battle-byte-review">${showReview(model.fit)}</div></details>
 </section>`;
}

export function mountBattleBackground(ctx){
 const model=ctx.state.battleBackground, root=document.getElementById('battle-background');
 if(!root||!model?.source.available)return;
 const {width,height,palette}=model.source;
 const draft=root.querySelector('#battle-draft'),status=root.querySelector('#battle-status');
 const build=root.querySelector('[data-action="battle-background-build"]');
 const fitLabel=root.querySelector('#battle-fit'),details=root.querySelector('#battle-byte-review');
 const retry=root.querySelector('#battle-fit-retry');
 const undo=root.querySelector('#battle-undo'),redo=root.querySelector('#battle-redo');
 const reset=root.querySelector('#battle-reset'),brush=root.querySelector('#battle-brush');
 const live=()=>root.isConnected&&selectionKey(ctx.state)===model.scope;
 const rgba=palette.map(([r,g,b])=>[r,g,b,255]);
 let previous=null,stroke=null,imageRequest=0,fitTimer;
 function draw(canvas,pixels){
  const graphics=canvas.getContext('2d'),image=graphics.createImageData(width,height);
  pixels.forEach((index,position)=>image.data.set(rgba[index],position*4));
  graphics.putImageData(image,0,0);
 }
 function refresh(message=''){
  draw(draft,model.draft);
  const changed=model.draft.some((color,i)=>color!==model.base[i]);
  undo.disabled=!model.past.length;
  redo.disabled=!model.future.length;
  reset.disabled=!changed;
  status.textContent=message;
  showFit();
 }
 function showFit(){
  const fit=model.fit;
  let title='Original image fits',help='Paint or import an image to create a playable copy.',tone='good';
  if(model.saved){
   if(!fit){title='Checking fit…';help='';tone='';}
   else if(fit.error){title='Couldn’t check fit';help=fit.error;tone='warm';}
   else if(!fit.fits){title='Needs simplification';help=fit.reason;tone='warm';}
   else{title='Fits in the ROM';help='Save a playable copy to try it in Playtest.';}
  }
  const label=fitLabel.querySelector('strong');
  label.textContent=title;
  label.className='badge '+tone;
  fitLabel.querySelector('span').textContent=help;
  details.innerHTML=showReview(fit);
  setUnavailable(build,!fit?.fits||model.building,model.building?'Saving the playable copy.':'Make an edit that fits before saving.');
  retry.hidden=!fit?.error;
 }
 function queueFit(delay=180){
  clearTimeout(fitTimer);
  const pixels=model.saved;
  const ticket=model.fitTicket=(model.fitTicket||0)+1;
  if(!pixels)return;
  const params=ctx.sourceParams();
  fitTimer=setTimeout(async()=>{
   const current=()=>live()&&model.fitTicket===ticket&&model.saved===pixels;
   if(!current())return;
   const fit=await ctx.api.call('backgrounds.fit',{...params,source_sha256:model.source.source_sha256,pixels})
    .catch(error=>({error:error.message}));
   if(!current())return;
   model.fit=fit;
   showFit();
  },delay);
 }
 retry.addEventListener('click',()=>{model.fit=null;showFit();queueFit(0);});
 function commit(before,message){
  if(!model.draft.some((color,i)=>color!==before[i]))return;
  model.past.push(before);
  if(model.past.length>24)model.past.shift();
  model.future=[];
  save(message);
 }
 function save(message){
  imageRequest++;
  model.fit=null;
  model.saved=model.draft.some((color,i)=>color!==model.base[i])?hexBytes(model.draft):'';
  ctx.setDraft(draftKey,model.saved);
  refresh(message);
  queueFit();
 }
 function point(event){
  const bounds=draft.getBoundingClientRect();
  return [
   Math.min(width-1,Math.max(0,Math.floor((event.clientX-bounds.left)*width/bounds.width))),
   Math.min(height-1,Math.max(0,Math.floor((event.clientY-bounds.top)*height/bounds.height)))
  ];
 }
 function paint(x,y){
  const size=Number(brush.value);
  for(let row=y;row<Math.min(height,y+size);row++){
   model.draft.fill(model.color,row*width+x,row*width+Math.min(width,x+size));
  }
 }
 function extend(event){
  const [x,y]=point(event),[fromX,fromY]=previous;
  const steps=Math.max(Math.abs(x-fromX),Math.abs(y-fromY),1);
  for(let step=1;step<=steps;step++){
   paint(Math.round(fromX+(x-fromX)*step/steps),Math.round(fromY+(y-fromY)*step/steps));
  }
  previous=[x,y];
  draw(draft,model.draft);
 }
 draft.addEventListener('pointerdown',event=>{
  if(event.button!==0||stroke)return;
  draft.setPointerCapture(event.pointerId);
  previous=point(event);
  stroke={before:model.draft.slice(),id:event.pointerId};
  paint(...previous);
  draw(draft,model.draft);
 });
 draft.addEventListener('pointermove',event=>{if(stroke?.id===event.pointerId)extend(event);});
 function end(event){
  if(stroke?.id!==event.pointerId)return;
  const {before}=stroke;
  stroke=null;
  commit(before);
 }
 draft.addEventListener('pointerup',end);draft.addEventListener('pointercancel',end);
 draft.addEventListener('lostpointercapture',end);
 const swatches=root.querySelectorAll('[data-battle-color]');
 swatches.forEach((node,index)=>{
  node.style.setProperty('--swatch',`rgb(${palette[index].join(',')})`);
  node.addEventListener('click',()=>{
   model.color=index;
   swatches.forEach(item=>item.setAttribute('aria-pressed',String(item===node)));
  });
 });
 undo.addEventListener('click',()=>{if(model.past.length){model.future.push(model.draft);model.draft=model.past.pop();save();}});
 redo.addEventListener('click',()=>{if(model.future.length){model.past.push(model.draft);model.draft=model.future.pop();save();}});
 reset.addEventListener('click',()=>{const before=model.draft;model.draft=model.base.slice();commit(before);});
 root.querySelector('#battle-save').addEventListener('click',()=>{
  const link=document.createElement('a');
  link.download='Battle-background.png';
  link.href=draft.toDataURL('image/png');
  link.click();
 });
 const picker=root.querySelector('#battle-png');
 picker.addEventListener('change',async()=>{
  const file=picker.files?.[0];
  picker.value='';
  if(!file)return;
  const request=++imageRequest;
  try{
   if(file.size>2*1024*1024)throw Error('Choose a PNG under 2 MiB.');
   const header=new DataView(await file.slice(0,24).arrayBuffer());
   if(header.byteLength!==24||header.getUint32(0)!==0x89504e47||header.getUint32(4)!==0x0d0a1a0a||header.getUint32(12)!==0x49484452)throw Error('Choose a valid PNG image.');
   if(header.getUint32(16)!==width||header.getUint32(20)!==height)throw Error('The battle backdrop must be 320 × 128 pixels.');
   const bitmap=await createImageBitmap(file);
   try{
    if(!live()||request!==imageRequest)return;
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const graphics=canvas.getContext('2d');graphics.drawImage(bitmap,0,0);
    const input=graphics.getImageData(0,0,width,height).data,destination=new Uint8Array(width*height);
    for(let i=0;i<destination.length;i++){
     if(input[i*4+3]<128)continue;
     let best=Infinity;
     palette.forEach(([r,g,b],index)=>{
      const distance=(input[i*4]-r)**2+(input[i*4+1]-g)**2+(input[i*4+2]-b)**2;
      if(distance<best){best=distance;destination[i]=index;}
     });
    }
    const before=model.draft;
    model.draft=destination;
    commit(before,'PNG imported and matched to the battle palette.');
   }finally{bitmap.close();}
  }catch(error){if(live()&&request===imageRequest)status.textContent=error.message;}
 });
 draw(root.querySelector('#battle-original'),model.base);
 refresh();
 if(!model.fit)queueFit(0);
}
