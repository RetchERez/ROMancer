import {cleanPreview} from './clean_preview.js';
export const blinkAllowed=(appReduced,systemReduced)=>!appReduced&&!systemReduced;
export function differencePixels(before,after){
 if(before.length!==after.length||before.length%4||before.length>4*1024*1024)throw Error('Comparison dimensions differ or exceed the preview budget.');
 const pixels=new Uint8ClampedArray(after.length);let changed=0;
 for(let i=0;i<after.length;i+=4)if([0,1,2,3].some(c=>before[i+c]!==after[i+c])){pixels.set(after.subarray(i,i+4),i);changed++;}
 return {pixels,changed};
}
function snapshot(panel){
 const canvas=panel.querySelector('canvas');
 if(canvas)return cleanPreview(canvas);
 const chips=[...panel.querySelectorAll('svg.preview-swatch rect')];
 if(chips.length){const width=16,height=Math.ceil(chips.length/16),pixels=new Uint8ClampedArray(width*height*4);for(const [i,chip] of chips.entries()){const match=/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/.exec(chip.getAttribute('fill'));if(!match)return null;const rgb=match.slice(1).map(Number);if(rgb.some(n=>n>255))return null;pixels.set([...rgb,255],i*4);}return {width,height,pixels,kind:'colors'};}
 return null;
}
export function mountVisualComparisons(root,state,{reduceMotion=false}={}){
 const pairs=new Map(),preferences=state.comparisonModes??=new Map();let stopped=false,scheduled=0;
 const motion=globalThis.matchMedia?.('(prefers-reduced-motion: reduce)');let allowBlink=blinkAllowed(reduceMotion,motion?.matches);
 function attach(pair,key){
  const panels=[...pair.children];if(panels.length!==2)return;
  try{if(!snapshot(panels[0])||!snapshot(panels[1]))return;}catch{return;}
  const controls=document.createElement('div');controls.className='comparison-controls';
  controls.innerHTML='<label>Compare <select aria-label="Comparison view"><option value="side">Side by side</option><option value="original">Original</option><option value="edited">Edited</option><option value="changes">Changes only</option></select></label><label class="comparison-blink"><input type="checkbox" aria-label="Blink original and edited"> Blink slowly</label><span class="subtle comparison-note"></span>';
  const select=controls.querySelector('select'),blink=controls.querySelector('input'),note=controls.querySelector('.comparison-note');
  select.value=preferences.get(key)||'side';blink.disabled=!allowBlink;if(!allowBlink)blink.parentElement.title='Blink follows reduced-motion settings.';
  const difference=document.createElement('div');difference.className='comparison-difference';difference.hidden=true;
  difference.innerHTML='<span>Changes only · read-only</span><div class="comparison-mask"><canvas role="img" aria-label="Changed pixels only"></canvas></div><p class="subtle comparison-count"></p>';
  let holder=null;if(pair.classList.contains('game-map-previews')){holder=document.createElement('div');holder.className='comparison-widget';pair.before(holder);holder.append(controls,pair);}else pair.before(controls);pair.append(difference);const canvas=difference.querySelector('canvas');let timer=null,phase=0,disposed=false;
  const originalInert=panels.map(node=>node.inert);
  const current=()=>!disposed&&!stopped&&root.isConnected&&pair.isConnected;
  function update(){
   if(!current())return;const value=select.value;
   const derived=value==='changes'||blink.checked;
   pair.classList.toggle('comparison-single',value!=='side'||blink.checked);difference.hidden=!derived;
   panels[0].hidden=derived||!['side','original'].includes(value);panels[1].hidden=derived||!['side','edited'].includes(value);
   panels.forEach((panel,i)=>panel.inert=blink.checked||originalInert[i]);note.textContent=blink.checked?'Blink comparison · painting paused':'';
   if(derived)try{
    const a=snapshot(panels[0]),b=snapshot(panels[1]);if(!a||!b||a.width!==b.width||a.height!==b.height)throw Error('Preview dimensions differ. Use side by side.');
    const diff=blink.checked?null:differencePixels(a.pixels,b.pixels),pixels=blink.checked?(phase?b.pixels:a.pixels):diff.pixels;
    canvas.width=b.width;canvas.height=b.height;const context=canvas.getContext('2d'),image=context.createImageData(b.width,b.height);image.data.set(pixels);context.putImageData(image,0,0);canvas.style.width=Math.min(512,b.width*32)+'px';
    difference.querySelector(':scope > span').textContent=blink.checked?(phase?'Edited':'Original')+' · blink preview':'Changes only · read-only';
    difference.querySelector('.comparison-count').textContent=(blink.checked?'Content preview only':diff.changed+' changed '+(b.kind==='colors'?(diff.changed===1?'color':'colors'):(diff.changed===1?'pixel':'pixels'))+' · checkerboard marks unchanged areas')+(b.note?' · '+b.note:'');
   }catch(error){difference.querySelector('.comparison-count').textContent=error.message;canvas.width=1;canvas.height=1;}
  }

  select.addEventListener('change',()=>{preferences.set(key,select.value);while(preferences.size>64)preferences.delete(preferences.keys().next().value);update();});
  blink.addEventListener('change',()=>{clearInterval(timer);timer=null;select.disabled=blink.checked;if(blink.checked){phase=0;timer=setInterval(()=>{if(current()&&!document.hidden){phase=1-phase;update();}},1200);}update();});
  const record={update,setMotion(allowed){blink.disabled=!allowed;if(!allowed){blink.checked=false;select.disabled=false;clearInterval(timer);timer=null;}update();},dispose(){if(disposed)return;disposed=true;clearInterval(timer);controls.remove();difference.remove();if(holder){holder.before(pair);holder.remove();}pair.classList.remove('comparison-single');panels.forEach((node,i)=>{node.hidden=false;node.inert=originalInert[i];});}};
  pairs.set(pair,record);update();
 }
 function scan(){
  scheduled=0;if(stopped||!root.isConnected)return;
  for(const [pair,record] of pairs)if(!pair.isConnected||!root.contains(pair)){record.dispose();pairs.delete(pair);}
  let index=0;for(const pair of root.querySelectorAll('.preview-pair,.game-map-previews')){const key=[state.project?.project_id,state.artifact?.artifact_id,state.page,pair.className,index++].join(':');if(!pairs.has(pair))attach(pair,key);}
  for(const record of pairs.values())record.update();
 }
 const queue=()=>{if(!stopped&&!scheduled)scheduled=requestAnimationFrame(scan);};
 const observer=new MutationObserver(records=>{if(records.some(record=>!record.target.closest?.('.comparison-controls,.comparison-difference')))queue();});observer.observe(root,{childList:true,subtree:true});
 const events=['input','change','pointerup','keydown','sprite-refresh','map-refresh','animation-refresh'];for(const event of events)root.addEventListener(event,queue,true);
 const motionChanged=()=>{allowBlink=blinkAllowed(reduceMotion,motion?.matches);for(const record of pairs.values())record.setMotion(allowBlink);};motion?.addEventListener?.('change',motionChanged);
 scan();return {dispose(){if(stopped)return;stopped=true;motion?.removeEventListener?.('change',motionChanged);observer.disconnect();cancelAnimationFrame(scheduled);for(const event of events)root.removeEventListener(event,queue,true);for(const record of pairs.values())record.dispose();pairs.clear();}};
}
