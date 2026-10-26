import {esc} from './common.js';
import {selectionKey} from './tool_inputs.js';

const integer=(value,min,max,label)=>{if(!Number.isSafeInteger(value)||value<min||value>max)throw Error('Invalid declared '+label+'.');return value;};
function setup(ctx){
 const schemaFallback=JSON.stringify(ctx.state.artifact?.descriptors?.script||ctx.state.project?.descriptors?.script||{}),menuFallback=JSON.stringify({profile:{},cases:{},font_artifact_id:'',font_schema:{}}),read=id=>document.getElementById(id)?.value??ctx.draft(id,id==='script-schema'?schemaFallback:menuFallback);
 const schema=read('script-schema'),config=read('menu-config');if(schema.length>1024**2||config.length>1024**2)throw Error('Menu declaration exceeds its preview budget.');
 return {schema:JSON.parse(schema),config:JSON.parse(config)};
}
function names(ctx,doc){return doc.records.map((record,index)=>({record,texts:record.segments.map(segment=>document.getElementById(`script-segment-${index}-${segment.index}`)?.value??ctx.draft(`script-segment-${index}-${segment.index}`,segment.text))}));}
const textSignature=(ctx,doc)=>JSON.stringify(names(ctx,doc).map(row=>[row.record.id,row.texts]));
function current(ctx,owned){
 const {state}=ctx,doc=state.results['script.inspect'];if(!owned||state.menuVisual!==owned||owned.scope!==selectionKey(state)||owned.document_id!==doc?.document_id||doc.source_sha256!==state.artifact?.sha256||state.page&&state.page!=='scripts')return false;
 try{return JSON.stringify(setup(ctx))===owned.signature;}catch{return false;}
}
function fontData(metrics){
 if(!Array.isArray(metrics.glyphs)||!metrics.glyphs.length||metrics.glyphs.length>256)throw Error('Measured font glyphs are unavailable.');
 const result=new Map();let budget=0;
 for(const glyph of metrics.glyphs){
  const bitmap=glyph.bitmap||{},width=integer(bitmap.width,1,32,'glyph width'),height=integer(bitmap.height,1,32,'glyph height'),stride=integer(bitmap.row_stride,1,4,'glyph row stride');
  if(stride!==Math.ceil(width/8)||typeof bitmap.raw_hex!=='string'||bitmap.raw_hex.length!==stride*height*2||!/^[a-f0-9]+$/i.test(bitmap.raw_hex)||result.has(glyph.id))throw Error('Measured glyph bitmap data is unavailable or ambiguous.');
  const raw=Uint8Array.from(bitmap.raw_hex.match(/../g),value=>parseInt(value,16)),mask=(1<<((8-width%8)%8))-1;
  for(let y=0;y<height;y++)if(raw[(y+1)*stride-1]&mask)throw Error('Measured glyph has unsupported padding bits.');
  integer(glyph.bearing?.x,-64,64,'glyph bearing');integer(glyph.bearing?.y,-64,64,'glyph bearing');integer(glyph.advance_pixels,0,128,'glyph advance');
  budget+=raw.length;if(budget>65536)throw Error('Measured font bitmap budget exceeded.');result.set(glyph.id,{...glyph,width,height,stride,raw});
 }
 return result;
}
function mappingFor(preview,font){
 if(!Array.isArray(preview.glyph_map)||preview.glyph_map.length>256)throw Error('Declared menu glyph mapping is unavailable.');const result=new Map();
 for(const row of preview.glyph_map){if(typeof row.scalar!=='string'||Array.from(row.scalar).length!==1||result.has(row.scalar)||!font.has(row.glyph_id))throw Error('Declared menu mapping names an unavailable glyph.');result.set(row.scalar,row.glyph_id);}return result;
}
function validate(preview,metrics,doc,config){
 if(preview.error)throw Error(preview.error.message||preview.error);if(!metrics.ok||metrics.status!=='MEASURED')throw Error(metrics.error?.message||'Declared font measurements are unavailable.');
 if(config.font_schema?.codec!=='mono-row-msb-v1')throw Error('This font storage format has no declared bitmap preview.');
 if(preview.source_sha256!==doc.source_sha256||preview.document_id!==doc.document_id||preview.schema_sha256!==doc.schema_sha256||preview.script?.document_id!==doc.document_id)throw Error('Menu layout belongs to different source text.');
 if(preview.font_sha256!==metrics.source_sha256||metrics.source_sha256!==config.font_schema.source?.sha256||preview.font_schema_sha256!==metrics.font_schema_sha256||preview.metrics_id!==metrics.metrics_id)throw Error('Menu placements and font measurements have different identities.');
 const viewport=preview.profile?.viewport,width=integer(viewport?.width,1,1024,'viewport width'),height=integer(viewport?.height,1,1024,'viewport height');integer(preview.profile.line_height_px,1,64,'line height');
 if(!Array.isArray(preview.cases)||!preview.cases.length||preview.cases.length>32||width*height*preview.cases.length>8*1024**2)throw Error('Declared cases exceed the menu canvas budget.');
 let cells=0,placements=0;for(const row of preview.cases){if(!Array.isArray(row.cells))throw Error('Declared menu case cells are unavailable.');cells+=row.cells.length;for(const cell of row.cells)placements+=cell.placements?.length||0;}if(cells>1024||placements>2048)throw Error('Declared menu placement budget exceeded.');
 const font=fontData(metrics);return {font,mapping:mappingFor(preview,font),width,height};
}

export async function loadMenuPreview(ctx,doc){
 if(!doc?.ok||ctx.state.results['script.inspect']?.document_id!==doc.document_id)throw Error('Inspect declared source text before previewing its menu.');
 const selected=setup(ctx),{config,schema}=selected,{state}=ctx,generation=(state.menuPreviewGeneration||0)+1;state.menuPreviewGeneration=generation;
 const owned={scope:selectionKey(state),document_id:doc.document_id,signature:JSON.stringify(selected),text_signature:textSignature(ctx,doc),generation,status:'loading'};
 state.menuVisual=owned;delete state.results['menu.preview'];await ctx.render();
 const requestCurrent=()=>current(ctx,owned)&&owned.text_signature===textSignature(ctx,doc)&&state.menuPreviewGeneration===generation;
 try{
  if(!requestCurrent())return;
  const [preview,metrics]=await Promise.all([
   ctx.api.call('menu.preview',{...ctx.sourceParams(),schema,profile:config.profile,cases:config.cases,font_artifact_id:config.font_artifact_id,font_schema:config.font_schema}),
   ctx.api.call('font.measure',{project_id:state.project.project_id,artifact_id:config.font_artifact_id,schema:config.font_schema})
  ]);
  if(!requestCurrent()){if(state.menuVisual===owned)state.menuVisual=null;return;}
  const prepared=validate(preview,metrics,doc,config);Object.assign(owned,{status:'ready',preview,metrics,prepared});state.results['menu.preview']=preview;
 }catch(error){if(!requestCurrent())return;Object.assign(owned,{status:'error',message:error.message});}
 if(current(ctx,owned))await ctx.render();
}

function placementsFor(cell,edited,drafts,prepared){
 if(!Array.isArray(cell.placements))throw Error(cell.diagnostics?.[0]?.message||'Declared cell glyph placements are unavailable.');
 if(!edited||cell.kind!=='name')return {placements:cell.placements,advance:cell.advance_px};
 const row=drafts.get(cell.record_id),record=row?.record;
 if(!record||record.read_only_reasons?.length||record.segments.length!==1||record.tokens.some(token=>!['text','terminator','padding'].includes(token.kind)))throw Error('Name preview requires one complete control-free text segment.');
 const text=row.texts[0],scalars=Array.from(text);if(scalars.length>128)throw Error('Name preview exceeds 128 display characters.');
 if(text===cell.text)return {placements:cell.placements,advance:cell.advance_px};
 const run=scalars.map(scalar=>{const id=prepared.mapping.get(scalar),glyph=prepared.font.get(id);if(!glyph)throw Error('No declared glyph for '+JSON.stringify(scalar)+'.');return glyph;});
 const advance=run.reduce((sum,glyph)=>sum+glyph.advance_pixels,0),bounds=cell.box_bounds;let x=cell.align==='right'?bounds[2]-advance:bounds[0];
 return {advance,placements:run.map(glyph=>{const value={glyph_id:glyph.id,x,y:bounds[1]};x+=glyph.advance_pixels;return value;})};
}
function rasterCase(owned,row,drafts,edited){
 const {width,height,font}=owned.prepared,pixels=new Uint8ClampedArray(width*height*4),warnings=new Set();for(let i=0;i<pixels.length;i+=4)pixels.set([16,33,39,255],i);
 for(const cell of row.cells){
  const bounds=cell.box_bounds;if(!Array.isArray(bounds)||bounds.length!==4)throw Error('Declared cell bounds are unavailable.');for(const value of bounds)integer(value,-131072,131072,'cell bounds');
  const {placements,advance}=placementsFor(cell,edited,drafts,owned.prepared);if(Number.isSafeInteger(advance)&&advance>bounds[2]-bounds[0])warnings.add('Text advance exceeds a declared box.');if(owned.preview.profile.line_height_px>bounds[3]-bounds[1])warnings.add('Declared line height exceeds its box.');
  for(const placement of placements){
   const glyph=font.get(placement.glyph_id);if(!glyph)throw Error('A placed glyph is missing from the measured font.');const left=integer(placement.x,-131072,131072,'glyph position')+glyph.bearing.x,top=integer(placement.y,-131072,131072,'glyph position')+glyph.bearing.y;
   for(let y=0;y<glyph.height;y++)for(let x=0;x<glyph.width;x++)if(glyph.raw[y*glyph.stride+(x>>3)]&(128>>(x%8))){const px=left+x,py=top+y;if(px<bounds[0]||px>=bounds[2]||py<bounds[1]||py>=bounds[3])warnings.add('Glyph ink exceeds a declared box.');if(px<0||py<0||px>=width||py>=height){warnings.add('Glyph ink exceeds the declared viewport.');continue;}pixels.set([230,241,235,255],(py*width+px)*4);}
  }
 }
 return {width,height,pixels,warnings:[...warnings]};
}
export function menuPreviewReport(ctx){const owned=ctx.state.menuVisual;return current(ctx,owned)&&owned.status==='ready'?owned.preview:null;}
export function menuPreviewPanel(ctx){
 const owned=ctx.state.menuVisual;if(!current(ctx,owned))return '';
 if(owned.status==='loading')return '<section class="card"><p class="preview-caption" role="status">Measuring declared menu glyphs and layout…</p></section>';
 if(owned.status==='error')return `<section class="card"><p class="error" role="status">Menu preview unavailable: ${esc(owned.message)}</p></section>`;
 const {width,height}=owned.prepared,canvas=(kind,i)=>`<canvas id="menu-${kind}-${i}" width="${width}" height="${height}" aria-label="${kind==='original'?'Original':'Editing'} declared menu case ${i+1}" style="display:block;width:${Math.min(768,width*3)}px;max-width:100%;height:auto;image-rendering:pixelated"></canvas>`;
 return `<section class="card" id="menu-visual-preview"><h3>Declared font &amp; layout preview</h3><p class="preview-caption">Monochrome declared glyphs and boxes; not a captured game scene. Native font use and rendering remain unverified.</p><p>Edit a name above to update its declared menu cases. Control codes stay preserved.</p>${owned.preview.cases.map((row,i)=>`<section><h4>Case ${esc(row.id)}${row.selected_entry==null?'':' · selected '+esc(row.selected_entry)}</h4><div class="preview-pair"><div><span>Original</span>${canvas('original',i)}</div><div><span>Editing</span>${canvas('edited',i)}</div></div><p id="menu-case-status-${i}" class="preview-caption" role="status" aria-live="polite"></p></section>`).join('')}</section>`;
}
export function mountMenuPreview(ctx,doc){
 const owned=ctx.state.menuVisual,root=document.getElementById('menu-visual-preview');if(!root||!current(ctx,owned)||owned.status!=='ready')return;
 const draw=()=>{
  if(!current(ctx,owned)){root.innerHTML='<p class="error" role="status">Menu preview unavailable: source or declarations changed. Preview menu again.</p>';return;}
  const drafts=new Map(names(ctx,doc).map(row=>[row.record.id,row]));
  for(const [i,row] of owned.preview.cases.entries()){
   let before=null,after=null;const errors=[];
   for(const [kind,edited] of [['original',false],['edited',true]]){const canvas=document.getElementById(`menu-${kind}-${i}`);if(!canvas)continue;try{const image=rasterCase(owned,row,drafts,edited),c=canvas.getContext('2d'),data=c.createImageData(image.width,image.height);canvas.width=image.width;canvas.height=image.height;data.data.set(image.pixels);c.putImageData(data,0,0);canvas.hidden=false;if(edited)after=image;else before=image;}catch(error){canvas.hidden=true;canvas.width=1;canvas.height=1;errors.push((edited?'Editing':'Original')+' preview unavailable: '+error.message);}}
   const status=document.getElementById('menu-case-status-'+i);if(status){let changed=0;if(before&&after)for(let n=0;n<before.pixels.length;n+=4)if([0,1,2].some(c=>before.pixels[n+c]!==after.pixels[n+c]))changed++;status.textContent=errors.length?errors.join(' '):(changed?'Preview updated · '+changed+' declared pixels differ · not built.':'Unchanged declared menu preview.')+' '+[...new Set([...(before?.warnings||[]),...(after?.warnings||[])])].join(' ');status.className=errors.length?'error':'preview-caption';}
  }
 };
 for(const [index,record] of doc.records.entries())for(const segment of record.segments){const node=document.getElementById(`script-segment-${index}-${segment.index}`);node?.addEventListener('input',draw);node?.addEventListener('change',draw);}
 for(const id of ['menu-config','script-schema'])document.getElementById(id)?.addEventListener('input',()=>{if(!current(ctx,owned)){draw();if(ctx.state.menuVisual===owned)ctx.state.menuVisual=null;}});
 draw();
}
