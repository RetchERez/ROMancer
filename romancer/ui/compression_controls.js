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
 const root=compressedRoot(state),metadata=root?.compressed_parent;
 const result=state.results['compression.inspect']?.parent_sha256===artifact.sha256?state.results['compression.inspect']:null;
 const extraction=state.results['compression.extract'];
 const extracted=extraction&&extraction.inspection?.parent_sha256===artifact.sha256?extraction.artifact:null;
 const builds=metadata?state.project.builds.filter(row=>compressedRoot(state,row)?.artifact_id===root.artifact_id):[];
 const parameters=()=>({...ctx.sourceParams(),offset:integer('compression-offset'),allocation:integer('compression-allocation'),codec:read('compression-codec')});
 ctx.use({
  'compression-inspect':()=>ctx.run('compression.inspect',parameters()),
  'compression-extract':()=>ctx.run('compression.extract',parameters()),
  'compression-open':async node=>{await ctx.setArtifact(node.dataset.id);await ctx.navigate('resources');},
  'compression-review':async()=>{
   if(!metadata)throw new Error('Select an owned extracted resource first.');const edited_id=read('compression-edited');if(!edited_id)throw new Error('Create an edited build of the decoded resource first.');
   const plan=await ctx.run('compression.plan_reinsert',{...ctx.projectParams(),parent_id:metadata.parent_id,decoded_id:root.artifact_id,edited_id,offset:metadata.offset,allocation:metadata.allocation,codec:metadata.codec},{render:false});
   state.pending={kind:'compression',artifact_id:artifact.artifact_id,plan_id:plan.plan_id};await ctx.render();
  },
  'compression-build':async()=>{
   if(state.pending?.kind!=='compression'||state.pending.artifact_id!==artifact.artifact_id)throw new Error('Review reinsertion for this resource first.');
   const built=await ctx.run('build.apply',{...ctx.projectParams(),plan_id:state.pending.plan_id},{render:false});state.pending=null;
   await ctx.setArtifact(built.artifact_id);ctx.notify('Parent build created and selected. Open Playtest to check it.');
  }
 });
 if(metadata)return `<section class="card"><div class="card-heading"><h3>Compressed resource</h3>${button('Compression help','help-topic',{id:'compression'})}</div><p>${esc(metadata.codec)} at0x${metadata.offset.toString(16)} · ${size(metadata.allocation)} allocated.</p><p>Edit this decoded resource and create a build, then review reinsertion into its parent.</p><div class="actions">${button('Edit graphics','navigate',{id:'assets'})}${button('Edit text','navigate',{id:'scripts'})}${button('Edit tables','navigate',{id:'tables'})}</div>${select('compression-edited','Edited decoded build',builds.map(row=>[row.artifact_id,row.name]),artifact.kind==='build'?artifact.artifact_id:builds.at(-1)?.artifact_id)}<div class="actions">${button('Review reinsertion','compression-review',{primary:true,disabled:!builds.length})}${state.pending?.kind==='compression'?button('Create parent build','compression-build',{primary:true}):''}</div>${report(state.results['compression.plan_reinsert'],'Recompression plan')}</section>`;
 return `<details class="card" ${result||extracted?'open':''}><summary>Compressed resources</summary><p>Confirm the codec and allocated space before extracting. Supported formats: GBA LZ10 and RLE.</p><div class="field-row">${field('compression-offset','Stream offset',ctx.draft('compression-offset','0'))}${field('compression-allocation','Confirmed allocation in bytes (up to48KiB)',ctx.draft('compression-allocation','1024'))}${select('compression-codec','Codec',[['gba-lz10','GBA LZ10'],['gba-rle','GBA RLE']],ctx.draft('compression-codec','gba-lz10'))}</div><div class="actions">${button('Inspect stream','compression-inspect')}${button('Extract decoded resource','compression-extract',{primary:true})}${button('Compression help','help-topic',{id:'compression'})}</div>${result?`<p class="notice">${size(result.consumed)} stored → ${size(result.decoded_size)} decoded. Confirmed allocation: ${size(result.allocation)}.</p>`:''}${extracted?`<p>Decoded resource added to this project.</p>${button('Open decoded resource','compression-open',{id:extracted.artifact_id,primary:true})}`:''}</details>`;
}
