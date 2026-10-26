import {rememberPreview} from './clean_preview.js';
import {brushColors,brushSwatches} from './brush_colors.js';
import {selectionKey} from './tool_inputs.js';
import {PixelHistory,pixelBuffer} from './pixel_history.js';
import {stageCurrentPaint} from './asset_controls.js';
import {mergeCellChanges} from './pixel_tools.js';
import {editorPalette} from './edit_preview.js';
import {esc,button,field,select,read} from './common.js';

export function spritePreviewSize(width,height,zoom='fit',available=384){
 const scale=['8','16','32'].includes(String(zoom))?Number(zoom):Math.max(1,Math.min(32,Math.floor(Math.min(Math.max(1,available)/width,384/height))));
 return {width:width*scale,height:height*scale,scale};
}

export function makeAssembly(bitmap,{first=0,columns,rows,order='rows',indices=null,flips=null,colors=null,provenance='declared_layout'}){
 if(![first,columns,rows].every(Number.isSafeInteger)||first<0||columns<1||rows<1||columns>8||rows>8||!['rows','columns'].includes(order))throw Error('Choose a grid of up to 8 × 8 declared tiles.');
 const custom=indices!==null;
 if(custom&&(!Array.isArray(indices)||indices.length!==columns*rows||!indices.some(v=>v!==null)||indices.some(v=>v!==null&&(!Number.isSafeInteger(v)||v<0||v>=bitmap.count))))throw Error('Every mapped tile must be inside the declared tile collection.');
 if(!custom&&first+columns*rows>bitmap.count)throw Error('Choose a grid inside the declared tile collection.');
 const tiles=custom?[...indices]:Array.from({length:columns*rows},(_,i)=>first+(order==='rows'?i:(i%columns)*rows+Math.floor(i/columns)));
 flips=flips??tiles.map(()=>0);if(!Array.isArray(flips)||flips.length!==tiles.length||flips.some(v=>!Number.isSafeInteger(v)||v<0||v>3))throw Error('Tile flips must be0,1(horizontal),2(vertical) or3.');
 if(colors!==null&&(!Array.isArray(colors)||colors.length!==tiles.length||colors.some(group=>group!==null&&(typeof group!=='object'||Array.isArray(group)||Object.entries(group).some(([k,c])=>!/^\d{1,2}$/.test(k)||Number(k)>15||!Array.isArray(c)||c.length!==3||c.some(v=>!Number.isInteger(v)||v<0||v>255))))))throw Error('Observed tile colors are invalid.');
 return {first,columns,rows,order,tiles,indices:custom?[...indices]:null,flips:[...flips],colors,provenance:provenance==='pixel_candidate'?'pixel_candidate':'declared_layout'};
}
function storedPixel(bitmap,layout,part,x,y){const flip=layout.flips?.[part]||0;return (flip&2?bitmap.height-1-y:y)*bitmap.width+(flip&1?bitmap.width-1-x:x);}
export function assemblePixels(bitmap,layout,buffer){
 const width=layout.columns*bitmap.width,height=layout.rows*bitmap.height,pixels=Array(width*height).fill(0);
 layout.tiles.forEach((index,i)=>{if(index===null)return;const tile=buffer(index);if(!tile||tile.length!==bitmap.width*bitmap.height)throw Error('Tile dimensions differ.');for(let y=0;y<bitmap.height;y++)for(let x=0;x<bitmap.width;x++)pixels[(Math.floor(i/layout.columns)*bitmap.height+y)*width+i%layout.columns*bitmap.width+x]=tile[storedPixel(bitmap,layout,i,x,y)];});
 return {width,height,pixels};
}
export function assemblyChanges(bitmap,layout,pixels){
 const width=layout.columns*bitmap.width,height=layout.rows*bitmap.height;if(!Array.isArray(pixels)||pixels.length!==width*height)throw Error('Sprite dimensions differ.');
 const changed=new Map();
 layout.tiles.forEach((index,i)=>{if(index===null)return;const after=Array(bitmap.width*bitmap.height);
  for(let y=0;y<bitmap.height;y++)for(let x=0;x<bitmap.width;x++)after[storedPixel(bitmap,layout,i,x,y)]=pixels[(Math.floor(i/layout.columns)*bitmap.height+y)*width+i%layout.columns*bitmap.width+x];
  if(changed.has(index)&&JSON.stringify(changed.get(index))!==JSON.stringify(after))throw Error('Shared tile copies disagree. Paint the shared tile together.');changed.set(index,after);
 });
 return [...changed].map(([index,after])=>({kind:'cell',bitmap_id:bitmap.id,cell_index:index,before_pixels:bitmap.cells[index].pixels,after_pixels:after})).filter(e=>JSON.stringify(e.before_pixels)!==JSON.stringify(e.after_pixels));
}
export function paintAssemblyPixel(bitmap,layout,pixels,x,y,color){
 const width=layout.columns*bitmap.width,part=Math.floor(y/bitmap.height)*layout.columns+Math.floor(x/bitmap.width),index=layout.tiles[part];
 if(index===null||index===undefined)throw Error('This part has no mapped source tile.');const stored=storedPixel(bitmap,layout,part,x%bitmap.width,y%bitmap.height);
 layout.tiles.forEach((tile,i)=>{if(tile!==index)return;for(let yy=0;yy<bitmap.height;yy++)for(let xx=0;xx<bitmap.width;xx++)if(storedPixel(bitmap,layout,i,xx,yy)===stored)pixels[(Math.floor(i/layout.columns)*bitmap.height+yy)*width+i%layout.columns*bitmap.width+xx]=color;});
}
function mapSettings(text){if(!text.trim())return {indices:null,flips:null};const parts=text.trim().split(/[\s,\/]+/);return {indices:parts.map(token=>token==='.'?null:Number(token.replace(/[hv]/g,''))),flips:parts.map(token=>(token.includes('h')?1:0)|(token.includes('v')?2:0))};}

function layoutFor(ctx,doc,bitmap){try{const saved=JSON.parse(ctx.draft('sprite-layout','null'));if(saved?.document_id===doc.document_id&&saved.bitmap_id===bitmap.id)return makeAssembly(bitmap,saved);}catch{}return null;}
function imageFor(ctx,doc,bitmap,layout){return assemblePixels(bitmap,layout,index=>pixelBuffer(ctx,doc,bitmap,index));}
function history(ctx,doc,bitmap,layout,image){const scope=selectionKey(ctx.state)+doc.document_id+bitmap.id+JSON.stringify(layout);if(ctx.state.spriteHistory?.scope!==scope||JSON.stringify(ctx.state.spriteHistory.current)!==JSON.stringify(image.pixels))ctx.state.spriteHistory=new PixelHistory(scope,image.pixels,32);return ctx.state.spriteHistory;}
function stage(ctx,doc,bitmap,layout,pixels){
 const previous=stageCurrentPaint(ctx,doc),tiles=new Set(layout.tiles);
 const unrelated=previous.filter(c=>c.kind!=='cell'||c.bitmap_id!==bitmap.id||!tiles.has(c.cell_index));
 ctx.setDraft('asset-changes',JSON.stringify(mergeCellChanges(unrelated,assemblyChanges(bitmap,layout,pixels)),null,2));
 ctx.state.paint=null;ctx.setDraft('paint-buffer','');ctx.state.pending=null;ctx.state.assetAcknowledgements=[];
}

export function spriteAssembly(ctx,doc,bitmap,palette=null){
 if(!doc?.ok||!bitmap)return '';
 const scope=selectionKey(ctx.state),current=()=>selectionKey(ctx.state)===scope,layout=layoutFor(ctx,doc,bitmap),image=layout&&imageFor(ctx,doc,bitmap,layout),undo=image&&history(ctx,doc,bitmap,layout,image);
 const checkHistory=()=>{if(JSON.stringify(imageFor(ctx,doc,bitmap,layout).pixels)!==JSON.stringify(undo.current))throw Error('Tiles changed in another editor. Start a fresh sprite stroke before undo or redo.');};
 const colors=brushColors(bitmap,editorPalette(ctx,palette),layout);
 ctx.use({
  'sprite-brush':node=>{if(!current())return;const index=Number(node.dataset.id);if(!colors.some(c=>c.index===index))throw Error('Choose a declared brush index.');ctx.setDraft('sprite-color',String(index));const input=document.getElementById('sprite-color');if(input)input.value=String(index);document.querySelectorAll('[data-brush-index]').forEach(button=>button.setAttribute('aria-pressed',String(Number(button.dataset.brushIndex)===index)));},
  'sprite-assemble':()=>{if(!current())return;const settings={first:Number(read('sprite-first')),columns:Number(read('sprite-columns')),rows:Number(read('sprite-rows')),order:read('sprite-order'),...mapSettings(read('sprite-map'))};makeAssembly(bitmap,settings);ctx.setDraft('sprite-layout',JSON.stringify({document_id:doc.document_id,bitmap_id:bitmap.id,...settings}));ctx.state.spriteHistory=null;return ctx.render();},
  'sprite-undo':()=>{if(!current()||!undo)return;checkHistory();stage(ctx,doc,bitmap,layout,undo.undo());return ctx.render();},
  'sprite-redo':()=>{if(!current()||!undo)return;checkHistory();stage(ctx,doc,bitmap,layout,undo.redo());return ctx.render();},
  'sprite-export':()=>{if(!current())return;const canvas=document.getElementById('sprite-canvas');if(!canvas)throw Error('Assemble a sprite first.');canvas.dispatchEvent(new Event('sprite-refresh'));const link=document.createElement('a');link.href=canvas.toDataURL('image/png');link.download='edited-sprite.png';link.click();}
 });
 return `<section class="card sprite-assembly"><div class="card-heading"><h3>Sprite assembly</h3>${layout?button('Save edited PNG','sprite-export'):''}</div><p class="subtle">Arrange declared tiles, then paint the whole image. Shared tiles update everywhere in this editing layout.</p><div class="field-row">${field('sprite-first','First tile',ctx.draft('sprite-first',layout?.first??0),{type:'number',min:0})}${field('sprite-columns','Tiles across',ctx.draft('sprite-columns',layout?.columns??Math.min(2,bitmap.count)),{type:'number',min:1,max:8})}${field('sprite-rows','Tiles down',ctx.draft('sprite-rows',layout?.rows??Math.min(2,Math.floor(bitmap.count/2)||1)),{type:'number',min:1,max:8})}${select('sprite-order','Tile order',[['rows','Across, then down'],['columns','Down, then across']],ctx.draft('sprite-order',layout?.order||'rows'))}</div><details><summary>Custom tile placement</summary>${field('sprite-map','Tile map',ctx.draft('sprite-map',layout?.indices?layout.indices.map((v,i)=>v===null?'.':String(v)+((layout.flips[i]&1)?'h':'')+((layout.flips[i]&2)?'v':'')).join(', '):''))}<p>One tile per grid position; use h/v for flips and . for an unmapped part.</p></details>${button('Assemble tiles','sprite-assemble',{primary:!layout})}${image?`${layout.provenance==='pixel_candidate'?'<p class="notice warm">Gameplay pixel candidates. Source use still needs native verification.</p>':''}${layout.colors?'<p class="subtle">Gameplay colors are a preview; palette bytes are unchanged.</p>':''}<div id="sprite-brush-palette">${brushSwatches(colors,ctx.draft('sprite-color','1'))}</div><div class="toolbar">${field('sprite-color','Brush index',ctx.draft('sprite-color','1'),{type:'number',min:0,max:Math.max(0,colors.length-1)})}${select('sprite-zoom','Preview size',[['fit','Fit'],['8','8×'],['16','16×'],['32','32×']],ctx.draft('sprite-zoom','fit'))}<span id="sprite-zoom-label" class="subtle" role="status"></span></div><div class="preview-pair sprite-comparison"><div><span>Original</span><div class="sprite-preview"><canvas id="sprite-original" aria-label="Original assembled sprite"></canvas></div></div><div><span>Editing · paint here</span><div class="sprite-preview"><canvas id="sprite-canvas" width="${image.width}" height="${image.height}" tabindex="0" role="application" aria-label="Assembled sprite editor: arrows move, Space paints"></canvas></div></div></div><p id="sprite-difference-count" class="preview-caption" role="status" aria-live="polite"></p><div class="actions">${button('Undo sprite stroke','sprite-undo',{disabled:!undo.canUndo})}${button('Redo sprite stroke','sprite-redo',{disabled:!undo.canRedo})}<span class="subtle">${image.width} × ${image.height} pixels · ${layout.tiles.filter(index=>index!==null).length} tile${layout.tiles.filter(index=>index!==null).length===1?'':'s'}</span></div><p class="subtle">Drag across tile boundaries; review all changed tiles together with Review asset changes.</p><details><summary>Tile placement</summary><p>${layout.tiles.map((index,i)=>esc(`(${i%layout.columns}, ${Math.floor(i/layout.columns)}) → tile ${index}`)).join(' · ')}</p><p>This source-bound layout is explicit. OAM, animation frames and game-specific metasprite tables still need their own declared mapping.</p></details>`:''}</section>`;
}

export function mountSprite(ctx,doc,bitmap,palette){
 const canvas=document.getElementById('sprite-canvas'),layout=layoutFor(ctx,doc,bitmap);if(!canvas||!layout)return;
 const scope=selectionKey(ctx.state),current=()=>selectionKey(ctx.state)===scope;
 const image=imageFor(ctx,doc,bitmap,layout),undo=history(ctx,doc,bitmap,layout,image);let pixels=[...image.pixels],pointer=null,cursor={x:0,y:0};
 const bits={'mono-row-msb-v1':1,'tile8-paired2-msb-v1':2,'tile8-planar2-msb-v1':2,'tile8-paired4-msb-v1':4,'tile8-packed4-high-v1':4,'tile8-packed4-low-v1':4}[bitmap.codec],count=Math.min(2**bits,palette?.colors_per_bank||256);
 const beforeCanvas=document.getElementById('sprite-original'),original=assemblePixels(bitmap,layout,index=>bitmap.cells[index].pixels);
 const rgba=(values,colors)=>{const data=new Uint8ClampedArray(values.length*4);values.forEach((value,i)=>{const part=Math.floor(Math.floor(i/image.width)/bitmap.height)*layout.columns+Math.floor((i%image.width)/bitmap.width),observed=layout.colors?.[part]?.[value],color=colors?.entries.find(e=>e.index===value&&e.bank===0)?.rgb,shade=Math.round(18+value/Math.max(1,count-1)*216);data.set([color?.r??observed?.[0]??shade,color?.g??observed?.[1]??shade,color?.b??observed?.[2]??shade,255],i*4);});return data;};
 const originalPixels=rgba(original.pixels,palette);
 if(beforeCanvas){beforeCanvas.width=image.width;beforeCanvas.height=image.height;const c=beforeCanvas.getContext('2d'),frame=c.createImageData(image.width,image.height);frame.data.set(originalPixels);c.putImageData(frame,0,0);rememberPreview(beforeCanvas,image.width,image.height,frame.data);}
 const draw=()=>{const context=canvas.getContext('2d'),frame=context.createImageData(image.width,image.height);frame.data.set(rgba(pixels,editorPalette(ctx,palette)));context.putImageData(frame,0,0);rememberPreview(canvas,image.width,image.height,frame.data);let changed=0;for(let i=0;i<frame.data.length;i+=4)if([0,1,2].some(c=>frame.data[i+c]!==originalPixels[i+c]))changed++;const n=document.getElementById('sprite-difference-count');if(n)n.textContent=(changed?'Preview updated · '+changed+(changed===1?' pixel differs':' pixels differ')+' · not built':'Unchanged sprite preview');};

 const paint=(x,y)=>{const color=Number(read('sprite-color'));if(!Number.isInteger(color)||color<0||color>=count)throw Error('Choose a palette index inside the declared color count.');paintAssemblyPixel(bitmap,layout,pixels,x,y,color);draw();};
 const at=event=>{const rect=canvas.getBoundingClientRect(),x=Math.floor((event.clientX-rect.left)/rect.width*image.width),y=Math.floor((event.clientY-rect.top)/rect.height*image.height);if(x>=0&&y>=0&&x<image.width&&y<image.height){cursor={x,y};paint(x,y);}};
 const begin=()=>{pixels=[...imageFor(ctx,doc,bitmap,layout).pixels];undo.begin(pixels);};
 const updateSwatches=()=>{const host=document.getElementById('sprite-brush-palette');if(host)host.innerHTML=brushSwatches(brushColors(bitmap,editorPalette(ctx,palette),layout),document.getElementById('sprite-color')?.value??ctx.draft('sprite-color','1'));};
 document.getElementById('sprite-color')?.addEventListener('input',updateSwatches);
 const resize=()=>{if(!current())return;const panes=[beforeCanvas,canvas].filter(Boolean).map(node=>node.parentElement),width=Math.min(...panes.map(node=>Math.max(1,(node?.clientWidth||416)-32)));const size=spritePreviewSize(image.width,image.height,ctx.draft('sprite-zoom','fit'),width);for(const node of [beforeCanvas,canvas].filter(Boolean)){node.style.width=size.width+'px';node.style.height=size.height+'px';}const label=document.getElementById('sprite-zoom-label');if(label)label.textContent=size.scale+'× preview';};
 document.getElementById('sprite-zoom')?.addEventListener('change',event=>{if(!current())return;ctx.setDraft('sprite-zoom',event.target.value);resize();});
 canvas.style.touchAction='none';resize();draw();
 if(typeof ResizeObserver!=='undefined'){const observer=new ResizeObserver(resize);observer.observe(canvas.parentElement);ctx.state.spritePreviewObserver?.disconnect();ctx.state.spritePreviewObserver=observer;}
 canvas.addEventListener('sprite-refresh',()=>{if(current()&&pointer===null){pixels=[...imageFor(ctx,doc,bitmap,layout).pixels];draw();updateSwatches();}});
 canvas.addEventListener('pointerdown',event=>{if(!current()||event.button!==0)return;event.preventDefault();canvas.focus();pointer=event.pointerId;canvas.setPointerCapture(pointer);ctx.state.pending=null;ctx.state.assetEditRevision=(ctx.state.assetEditRevision||0)+1;begin();try{at(event);}catch(error){ctx.notify(error.message,true);}});
 canvas.addEventListener('pointermove',event=>{if(current()&&pointer===event.pointerId)try{at(event);}catch(error){ctx.notify(error.message,true);}});
 canvas.addEventListener('pointerup',async event=>{if(!current()||pointer!==event.pointerId)return;pointer=null;undo.commit(pixels);stage(ctx,doc,bitmap,layout,pixels);await ctx.render();});
 canvas.addEventListener('pointercancel',()=>{pointer=null;pixels=[...undo.current];draw();});
 canvas.addEventListener('keydown',async event=>{if(!current()||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown',' '].includes(event.key))return;event.preventDefault();cursor.x=Math.max(0,Math.min(image.width-1,cursor.x+(event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0)));cursor.y=Math.max(0,Math.min(image.height-1,cursor.y+(event.key==='ArrowDown'?1:event.key==='ArrowUp'?-1:0)));if(event.key===' ')try{begin();paint(cursor.x,cursor.y);undo.commit(pixels);stage(ctx,doc,bitmap,layout,pixels);await ctx.render();}catch(error){ctx.notify(error.message,true);}});
}
