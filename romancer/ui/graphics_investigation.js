import {selectionKey} from './tool_inputs.js';
import {getSettings} from './app_settings.js';
import {esc,button,field,select,read,size} from './common.js';
import {stopPlayback} from './playback_controls.js';

export function comparePlacements(before,after){
 if(!before?.matches||!after?.matches||before.coverage?.offset!==after.coverage?.offset||before.coverage?.bytes_scanned!==after.coverage?.bytes_scanned)return null;
 const keys=result=>new Set(result.matches.slice(0,256).map(m=>[m.offset,m.x,m.y,m.height,!!m.flip_x,!!m.flip_y].join(':'))),a=keys(before),b=keys(after);
 return {added:[...b].filter(k=>!a.has(k)).length,absent:[...a].filter(k=>!b.has(k)).length,retained:[...b].filter(k=>a.has(k)).length,semantic_ownership_known:false};
}

export function candidateGroups(result,height){
 const groups=new Map();(result?.matches||[]).forEach((match,index)=>{if(match.height!==height)return;const key=[match.x,match.y,match.height].join(':');if(!groups.has(key))groups.set(key,{x:match.x,y:match.y,height,choices:[]});groups.get(key).choices.push({index,...match});});
 return [...groups.values()].sort((a,b)=>a.y-b.y||a.x-b.x);
}

export async function ensureGraphicsObservation(ctx,{force=false,region=null,offset=0,length=null}={}){
 if(!force&&!getSettings().autoGraphics)return;
 const {state}=ctx;if(state.page!=='playtest'||state.playing||!state.runtime||!state.frame||!state.artifact?.size)return;
 if(state.runtime.game_sha256&&state.runtime.game_sha256!==state.artifact.sha256)return;
 const scope=selectionKey(state),frame=state.frame,session=state.runtime.session_dir,params={...ctx.sourceParams()},sourceSize=state.artifact.size;region=region?{...region}:null;
 state.graphicsInvestigations??={};const previous=state.graphicsInvestigations[scope];
 if(!force&&(previous?.status==='SCANNING'||previous?.frame_sha256===state.frame.sha256))return;
 if(force&&previous?.status==='SCANNING'&&previous.job_id)await ctx.api.call('jobs.cancel',{job_id:previous.job_id});
 if(selectionKey(state)!==scope||state.playing||state.frame?.sha256!==frame.sha256||state.runtime?.session_dir!==session)return;
 const entry={status:'SCANNING',frame_sha256:frame.sha256,result:null,job_id:null,session,region};state.graphicsInvestigations[scope]=entry;
 while(Object.keys(state.graphicsInvestigations).length>8)delete state.graphicsInvestigations[Object.keys(state.graphicsInvestigations)[0]];
 const owned=()=>state.graphicsInvestigations?.[scope]===entry;
 const repaint=()=>{if(!owned()||selectionKey(state)!==scope)return;const node=document.getElementById('graphics-investigation');if(node)node.outerHTML=graphicsInvestigation(ctx);};
 repaint();
 try{
  const submitted=await ctx.api.call('jobs.submit',{operation:'graphics.observe',parameters:{...params,frame_sha256:entry.frame_sha256,region,offset,length:length??sourceSize-offset}});entry.job_id=submitted.job_id;
  if(!owned()){await ctx.api.call('jobs.cancel',{job_id:entry.job_id});return;}
  repaint();
  while(owned()){
   const job=await ctx.api.call('jobs.get',{job_id:entry.job_id});
   if(['COMPLETED','FAILED','CANCELLED','INTERRUPTED'].includes(job.status)){
    if(job.status!=='COMPLETED'||!job.result?.ok)throw Error(job.result?.error||'Graphics scan '+job.status.toLowerCase());
    entry.result=job.result;entry.status='READY';
    if(previous?.session===session&&JSON.stringify(previous.region)===JSON.stringify(region))entry.placementComparison=comparePlacements(previous.result,entry.result);
    break;
   }
   await new Promise(resolve=>setTimeout(resolve,400));
  }
 }catch(error){entry.status='ERROR';entry.error=error.message;}
 repaint();
}

export function graphicsInvestigation(ctx){
 const {state}=ctx;if(!state.artifact)return '';
 const scope=selectionKey(state),current=()=>selectionKey(state)===scope,entry=state.graphicsInvestigations?.[scope],result=entry?.result;
 const partHeight=(result?.matches.some(m=>m.height===state.graphicsPartHeight)?state.graphicsPartHeight:null)||(result?.matches.some(m=>m.height===16)?16:8),allGroups=candidateGroups(result,partHeight),groups=allGroups.slice(0,16),coverage=result?.coverage;
 ctx.use({
  'graphics-show-region':async()=>{if(!current())return;stopPlayback(state);state.graphicsRegionOpen=true;await ctx.render();const node=document.getElementById('visual-checkpoints');if(node){node.open=true;node.scrollIntoView({block:'start'});}},
  'graphics-analyze':()=>{if(!current())return;stopPlayback(state);const selected=state.visualRegion;if(!selected||selected.scope!==scope||selected.frame_sha256!==state.frame?.sha256)throw Error('Select a region in the captured frame below first.');return ensureGraphicsObservation(ctx,{force:true,region:selected.region,offset:Number(read('graphics-offset')),length:Number(read('graphics-length'))});},
  'graphics-analyze-frame':()=>{if(!current())return;stopPlayback(state);return ensureGraphicsObservation(ctx,{force:true,offset:Number(read('graphics-offset')),length:Number(read('graphics-length'))});},
  'graphics-next':()=>{if(!current()||!coverage)return;return ensureGraphicsObservation(ctx,{force:true,offset:coverage.next_offset,length:state.artifact.size-coverage.next_offset});},
  'graphics-cancel':()=>entry?.job_id?ctx.api.call('jobs.cancel',{job_id:entry.job_id}):undefined,
  'graphics-part-height':node=>{state.graphicsPartHeight=Number(node.dataset.id);return ctx.render();},
  'graphics-edit-candidates':async()=>{
   if(!current()||!result?.evidence_id)throw Error('Analyze this selected source first.');
   const matches=groups.map((_,i)=>read('graphics-choice-'+i)).filter(v=>v!=='').map(Number);if(!matches.length)throw Error('Choose candidate source offsets for the parts you want to edit.');
   const declared=await ctx.run('graphics.declare',{...ctx.sourceParams(),evidence_id:result.evidence_id,matches},{render:false});if(!current())return;
   state.results['assets.inspect']=declared.inspection;await ctx.navigate('assets');if(!current())return;
   const bitmap=declared.inspection.bitmaps[0],layout={document_id:declared.inspection.document_id,bitmap_id:bitmap.id,...declared.layout};
   ctx.setDraft('asset-schema',JSON.stringify(declared.schema,null,2));
   ctx.setDraft('sprite-layout',JSON.stringify(layout));ctx.setDraft('sprite-first','0');ctx.setDraft('sprite-columns',String(layout.columns));ctx.setDraft('sprite-rows',String(layout.rows));ctx.setDraft('sprite-order',layout.order||'rows');
   ctx.setDraft('sprite-map',layout.indices.map((v,i)=>v===null?'.':String(v)+((layout.flips[i]&1)?'h':'')+((layout.flips[i]&2)?'v':'')).join(', '));state.spriteHistory=null;await ctx.render();
  }
 });
 return `<section class="card" id="graphics-investigation"><div class="card-heading"><h3>Gameplay graphics</h3>${entry?.status==='SCANNING'?button('Cancel analysis','graphics-cancel',{disabled:!entry.job_id}):''}</div><p>Import scanning indexes tile storage. Paused gameplay adds pixel matches without a game definition.</p>
 ${entry?.status==='SCANNING'?'<p role="status">Analyzing captured pixels and source bytes. Playback and navigation remain available.</p>':entry?.status==='ERROR'?`<p class="notice warm">${esc(entry.error)}</p>`:!result?'<p class="subtle">Play to a useful screen, then pause. A bounded scan starts automatically.</p>':`<p><strong>${result.matches.length} pixel candidates · source use unproven</strong></p><p class="subtle">${size(coverage.bytes_scanned)} examined from 0x${coverage.offset.toString(16).toUpperCase()} · ${coverage.whole_source?'whole source range':'partial source range'}. Frame positions may be sampled; repeated or unseen alternatives remain unresolved.</p>${result.frame?.sha256!==state.frame?.sha256?'<p class="notice warm">These candidates describe an earlier captured frame.</p>':''}
 ${entry.placementComparison?`<p>${entry.placementComparison.added} candidate placements added · ${entry.placementComparison.absent} absent compared with the previous capture. This does not identify animation ownership.</p>`:''}<div class="actions">${button('8 × 8 tiles','graphics-part-height',{id:'8'})}${result.matches.some(m=>m.height===16)?button('8 × 16 parts','graphics-part-height',{id:'16'}):''}${coverage.next_offset<state.artifact.size?button('Continue ROM range','graphics-next',{disabled:state.playing}):''}</div>
 ${groups.length?`<p>${allGroups.length>16?'Select a smaller object region above; this frame contains too many placements for one editing layout.':'Choose source candidates to assemble.'} A single result in this search does not establish a unique source.</p>${allGroups.length>16?'<details><summary>Sample placements</summary>':''}<div class="table-wrap"><table><thead><tr><th>Frame placement</th><th>Candidate source</th></tr></thead><tbody>${groups.slice(0,64).map((group,i)=>`<tr><td>${group.x}, ${group.y} ·8×${group.height}</td><td>${select('graphics-choice-'+i,'Part '+(i+1),[['','Choose a source offset'],...group.choices.map(m=>[String(m.index),'0x'+m.offset.toString(16).toUpperCase()+(m.flip_x?' · flip H':'')+(m.flip_y?' · flip V':'')])],group.choices.length===1?String(group.choices[0].index):'')}</td></tr>`).join('')}</tbody></table></div>${button('Load candidate layout','graphics-edit-candidates',{primary:true,disabled:state.playing||allGroups.length>16})}${allGroups.length>16?'</details>':''}`:'<p>No informative literal parts found. Try a smaller region or another ROM range. Compression and RAM-generated graphics need additional tracing.</p>'}<details><summary>Analysis evidence and limits</summary><p>Frame ${esc(result.frame?.index)} · <code>${esc(result.frame?.sha256)}</code></p>${(result.limits||[]).map(v=>`<p>${esc(v)}</p>`).join('')}</details>`}
 <details><summary>Focused analysis</summary><p>Use the captured-frame region selector above to isolate an object, then analyze that region. Coordinates and source offsets stay explicit.</p><div class="field-row">${field('graphics-offset','ROM start offset',ctx.draft('graphics-offset','0'))}${field('graphics-length','ROM bytes to request',ctx.draft('graphics-length',String(state.artifact.size||1)))}</div><div class="actions">${button('Analyze selected region','graphics-analyze',{disabled:!state.frame})}${button('Analyze whole frame','graphics-analyze-frame',{disabled:!state.frame||entry?.status==='SCANNING'})}</div><p class="subtle">Each background job examines up to512KiB, at every byte alignment. More ranges can be scanned without blocking the editor.</p></details></section>`;
}
