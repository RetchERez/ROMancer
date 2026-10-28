import {parseReferenceOffsets,compressionReferences} from './compression_references.js';
import {selectionKey} from './tool_inputs.js';
import {esc,button,field,select,read,size,report} from './common.js';
function integer(id){const text=read(id).trim(),value=Number(text);if(!text||!Number.isSafeInteger(value))throw new Error('Enter a whole number for '+id+'.');return value;}
export function compressedRoot(state,artifact=state.artifact){
 const rows=new Map([...(state.project?.sources||[]),...(state.project?.builds||[])].map(row=>[row.artifact_id,row]));const seen=new Set();
 for(let i=0;artifact&&i<128;i++){
  if(artifact.compressed_parent)return artifact;
  if(seen.has(artifact.artifact_id))return null;seen.add(artifact.artifact_id);artifact=rows.get(artifact.source_id);
 }
 return null;
}
export function resourceSystem(state){return state.artifact?.system_id||state.artifact?.system_hint||compressedRoot(state)?.system_hint||'nes';}

export function compressionControls(ctx){
 const {state}=ctx,artifact=state.artifact;if(!artifact)return '';
 const scope=selectionKey(state),current=()=>scope===selectionKey(state);
 const root=compressedRoot(state),savedMetadata=root?.compressed_parent;
 const metadata=savedMetadata?{...savedMetadata,codec:({'gba-lz10':'lz10','gba-rle':'rle'})[savedMetadata.codec]||savedMetadata.codec}:null;
 const result=state.results['compression.inspect']?.parent_sha256===artifact.sha256?state.results['compression.inspect']:null;
 const extraction=state.results['compression.extract'];
 const extracted=extraction&&extraction.inspection?.parent_sha256===artifact.sha256?extraction.artifact:null;
 const builds=metadata?state.project.builds.filter(row=>compressedRoot(state,row)?.artifact_id===root.artifact_id):[];
 const parameters=()=>({...ctx.sourceParams(),offset:integer('compression-offset'),allocation:integer('compression-allocation'),codec:read('compression-codec')});
 const reinsertion=()=>{if(!current()||!metadata)throw Error('Select this decoded resource again.');const edited_id=read('compression-edited');if(!edited_id)throw Error('Create an edited decoded build first.');return {...ctx.projectParams(),parent_id:metadata.parent_id,decoded_id:root.artifact_id,edited_id,offset:metadata.offset,allocation:metadata.allocation,codec:metadata.codec};};
 const moveSpec=()=>({source_offset:metadata.offset,source_length:state.compressionPreview?.result.original_stored_size,target_offset:integer('compressed-move-target'),target_capacity:integer('compressed-move-capacity'),fill_byte:integer('compressed-move-fill'),alignment:integer('compressed-move-align'),bank_size:integer('compressed-move-bank'),bank_origin:integer('compressed-move-origin'),references:parseReferenceOffsets(read('compressed-move-pointer'),read('compressed-move-more')).map(offset=>({offset,width:integer('compressed-move-width'),endian:read('compressed-move-order'),base:integer('compressed-move-base'),target_delta:0})),references_complete:!!document.getElementById('compressed-move-complete')?.checked,destination_reserved:!!document.getElementById('compressed-move-reserved')?.checked,replacement_input_id:null});
 const preview=state.compressionPreview?.scope===scope?state.compressionPreview:null;
 ctx.use({
  'compression-inspect':()=>ctx.run('compression.inspect',parameters()),
  'compression-extract':()=>ctx.run('compression.extract',parameters()),
  'compression-open':async node=>{await ctx.setArtifact(node.dataset.id);await ctx.navigate('resources');},
  'compression-preview':async()=>{const args=reinsertion(),signature=JSON.stringify(args);const result=await ctx.run('compression.preview_reinsert',args,{render:false});if(!current())return;if(signature!==JSON.stringify(reinsertion()))throw Error('The selected edited resource changed. Preview it again.');state.compressionPreview={scope,result,signature};return ctx.render();},
  'compression-move':async()=>{const args=reinsertion();if(!preview||preview.signature!==JSON.stringify(args))throw Error('Preview the current recompression first.');const spec=moveSpec(),signature=JSON.stringify({args,spec});const result=await ctx.run('compression.plan_relocate',{...args,spec},{render:false});if(!current())return;if(signature!==JSON.stringify({args:reinsertion(),spec:moveSpec()}))throw Error('The move declaration changed. Review it again.');preview.moveSpec=spec;state.pending={kind:'compression',artifact_id:artifact.artifact_id,plan_id:result.plan_id,signature,relocation:true};return ctx.render();},
  'compression-review':async()=>{
   const args=reinsertion(),signature=JSON.stringify(args);
   const plan=await ctx.run('compression.plan_reinsert',args,{render:false});
   if(!current())return;if(signature!==JSON.stringify(reinsertion()))throw Error('The edited resource changed. Review it again.');
   state.pending={kind:'compression',artifact_id:artifact.artifact_id,plan_id:plan.plan_id,signature};await ctx.render();
  },
  'compression-build':async()=>{
   if(state.pending?.kind!=='compression'||state.pending.artifact_id!==artifact.artifact_id)throw new Error('Review reinsertion for this resource first.');
   if(!current())throw Error('The selected resource changed.');
   const actual=state.pending.relocation?JSON.stringify({args:reinsertion(),spec:moveSpec()}):JSON.stringify(reinsertion());
   if(actual!==state.pending.signature)throw Error('The selected build or move declaration changed. Review it again.');
   const built=await ctx.run('build.apply',{...ctx.projectParams(),plan_id:state.pending.plan_id},{render:false});if(!current())return;state.pending=null;state.compressionPreview=null;
   await ctx.setArtifact(built.artifact_id);ctx.notify('Parent build created and selected. Open Playtest to check it.');
  }
 });
 if(metadata)return `<section class="card"><div class="card-heading"><h3>Compressed resource</h3>${button('Compression help','help-topic',{id:'compression'})}</div><p>${esc(metadata.codec)} at0x${metadata.offset.toString(16)} · ${size(metadata.allocation)} allocated.</p><p>Edit this decoded resource and create a build, then review reinsertion into its parent.</p><div class="actions">${button('Edit graphics','navigate',{id:'assets'})}${button('Edit text','navigate',{id:'scripts'})}${button('Edit tables','navigate',{id:'tables'})}</div>${select('compression-edited','Edited decoded build',builds.map(row=>[row.artifact_id,row.name]),artifact.kind==='build'?artifact.artifact_id:builds.at(-1)?.artifact_id)}<div class="actions">${button('Preview recompression','compression-preview',{disabled:!builds.length,primary:true})}${button('Review reinsertion','compression-review',{primary:true,disabled:!builds.length})}${state.pending?.kind==='compression'?button('Create parent build','compression-build',{primary:true}):''}</div>${preview?compressionCapacity(preview.result)+compressedMove(ctx,preview.result):''}${report(state.results['compression.plan_reinsert'],'Recompression plan')}${report(state.results['compression.plan_relocate'],'Relocation plan')}</section>`;
 return `<details class="card" ${result||extracted?'open':''}><summary>Compressed resources</summary><p>Confirm the codec and allocated space before extracting. Supported formats: LZ10, RLE and SNES LC_LZ2.</p><div class="field-row">${field('compression-offset','Stream offset',ctx.draft('compression-offset','0'))}${field('compression-allocation','Confirmed allocation in bytes (up to48KiB)',ctx.draft('compression-allocation','1024'))}${select('compression-codec','Codec',[['lz10','LZ10'],['rle','RLE'],['snes-lz2','SNES LC_LZ2']],ctx.draft('compression-codec','lz10'))}</div><div class="actions">${button('Inspect stream','compression-inspect')}${button('Extract decoded resource','compression-extract',{primary:true})}${button('Compression help','help-topic',{id:'compression'})}</div>${result?`<p class="notice">${size(result.consumed)} stored → ${size(result.decoded_size)} decoded. Confirmed allocation: ${size(result.allocation)}.</p>`:''}${extracted?`<p>Decoded resource added to this project.</p>${button('Open decoded resource','compression-open',{id:extracted.artifact_id,primary:true})}`:''}</details>`;
}

export function compressionCapacity(r){return '<div class="notice '+(r.fits?'':'warm')+'"><strong>'+r.packed_size+' / '+r.allocation+' bytes</strong><p>'+(r.fits?r.free_bytes+' bytes free.':r.overflow_bytes+' bytes over the confirmed allocation. Reduce the edit or review a reserved move.')+'</p><p>Independent decoder '+(r.independent_decode_verified?'verified the edited data.':'has not verified this output.')+'</p></div>';}
function compressedMove(ctx,r){
 const system=resourceSystem(ctx.state),bank={nes:8192,snes:32768,gb:16384,gbc:16384,sms:16384}[system]||0;
 return '<details><summary>Move to reserved space · Advanced</summary><p>Declare a reserved destination and every external linear reference to this stream. All listed pointers use the encoding below. Mixed encodings can be declared through the automation API.</p><div class="field-row">'+field('compressed-move-target','Reserved destination offset',ctx.draft('compressed-move-target','0'))+field('compressed-move-capacity','Reserved capacity',ctx.draft('compressed-move-capacity',String(r.packed_size)))+field('compressed-move-fill','Expected fill byte',ctx.draft('compressed-move-fill','255'))+select('compressed-move-align','Alignment',[[1,'1'],[2,'2'],[4,'4'],[8,'8'],[16,'16'],[32,'32']],ctx.draft('compressed-move-align','4'))+'</div><div class="field-row">'+field('compressed-move-pointer','Pointer file offset',ctx.draft('compressed-move-pointer','0'))+select('compressed-move-width','Pointer bytes',[[2,'2'],[3,'3'],[4,'4']],ctx.draft('compressed-move-width','4'))+select('compressed-move-order','Byte order',[['little','Little'],['big','Big']],ctx.draft('compressed-move-order',system==='genesis'?'big':'little'))+field('compressed-move-base','Pointer encoding adjustment',ctx.draft('compressed-move-base','0'))+'</div><div class="field-row">'+field('compressed-move-bank','Declared bank bytes (0 for linear)',ctx.draft('compressed-move-bank',String(bank)))+field('compressed-move-origin','Bank file origin',ctx.draft('compressed-move-origin',system==='nes'?'16':'0'))+'</div>'+compressionReferences(ctx,ctx.state.project.sources.concat(ctx.state.project.builds).find(a=>a.artifact_id===compressedRoot(ctx.state).compressed_parent.parent_id),compressedRoot(ctx.state).compressed_parent.offset)+'<label><input type="checkbox" id="compressed-move-complete" ' +(ctx.state.compressionPreview?.moveSpec?.references_complete?'checked':'')+'> This is the complete reference set for this move.</label><label><input type="checkbox" id="compressed-move-reserved" ' +(ctx.state.compressionPreview?.moveSpec?.destination_reserved?'checked':'')+'> I reserved this destination; matching fill does not prove free space.</label>'+button('Review compressed-resource move','compression-move')+'</details>';
}
