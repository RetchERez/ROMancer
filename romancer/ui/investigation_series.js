import {selectionKey} from './tool_inputs.js';
import {esc,button,field,select,read} from './common.js';

export function seriesNumber(text){
 if(!text.trim())return null;const value=Number(text);
 if(!Number.isSafeInteger(value))throw Error('Enter a whole number, or leave the observed value blank.');return value;
}
function currentResult(state,scope,result){return selectionKey(state)===scope&&result?.source_sha256===state.artifact?.sha256&&result.artifact_id===state.artifact?.artifact_id;}

export async function investigationSeries(ctx){
 const {state}=ctx,scope=selectionKey(state),params={...ctx.sourceParams()};
 let entry=state.investigationSeries;
 if(entry?.scope!==scope)state.investigationSeries=entry={scope,result:null,generation:0,page:0,error:null};
 const owned=()=>selectionKey(state)===scope&&state.investigationSeries===entry;
 const save=async(operation,parameters,native=false)=>{
  if(!owned())throw Error('The selected source changed. Open its investigation again.');
  const runtime=state.runtime;
  if(native&&runtime?.game_sha256!==state.artifact?.sha256)throw Error('Load this source in Playtest first.');
  const generation=++entry.generation;entry.error=null;
  const result=await ctx.api.call(operation,{...params,...parameters});
  if(!owned()||entry.generation!==generation||native&&state.runtime!==runtime)return;
  if(result?.ok===false)throw Error(result.error||'Investigation could not finish.');
  if(!currentResult(state,scope,result))throw Error('Investigation result belongs to another selected source.');
  entry.result=result;entry.loaded=true;entry.page=0;ctx.setDraft('investigation-id',result.investigation_id);await ctx.render();
 };
 const remembered=ctx.draft('investigation-id','');
 if(!entry.loaded&&remembered){
  entry.loaded=true;const generation=++entry.generation;
  try{const result=await ctx.api.call('investigations.get',{...params,investigation_id:remembered});
   if(owned()&&entry.generation===generation){if(result?.ok===false)throw Error(result.error);if(!currentResult(state,scope,result))throw Error('Saved investigation belongs to another source.');entry.result=result;}
  }catch(error){if(owned()&&entry.generation===generation)entry.error=error.message;}
 }
 const result=currentResult(state,scope,entry.result)?entry.result:null;
 ctx.use({
  'series-start':()=>save('investigations.start',{title:read('series-title').trim(),region:2,
   offset:seriesNumber(read('series-offset')),length:seriesNumber(read('series-length')),value:seriesNumber(read('series-value'))},true),
  'series-capture':async()=>{
   if(!owned()||!result)throw Error('Start an investigation for the selected source first.');
   if(!result.runtime_trusted)throw Error('Historical investigations are read-only. Start a fresh investigation.');
   const relation=read('series-relation');return save('investigations.capture',{investigation_id:result.investigation_id,
    label:read('series-label').trim()||'Observation '+(result.observation_count+1),value:seriesNumber(read('series-value')),
    relation,delta:relation==='delta'?seriesNumber(read('series-delta')):null},true);
  },
  'series-refresh':async()=>{if(!owned()||!result)throw Error('Open an investigation for this source first.');return save('investigations.get',{investigation_id:result.investigation_id});},
  'series-page':node=>{if(!owned())return;entry.page=Math.max(0,entry.page+Number(node.dataset.id));return ctx.render();},
  'series-watch':node=>{
   if(!owned()||!result)throw Error('Analyze the current source first.');
   const candidate=result.candidates.find(c=>c.candidate_id===node.dataset.id);if(!candidate)throw Error('Select a current hypothesis.');
   const saved=state.artifact.descriptors?.watches,existing=saved?.source_sha256===state.artifact.sha256?saved.watches:[];
   return ctx.run('watches.save',{...params,watches:[...(existing||[]),{name:'Candidate 0x'+candidate.offset.toString(16),region:2,offset:candidate.offset,length:candidate.width}]});
  }
 });
 const ready=state.runtime?.game_sha256===state.artifact?.sha256,candidates=result?.candidates||[],rows=candidates.slice(entry.page*24,(entry.page+1)*24);
 return `<section class="card investigation-series"><div class="card-heading"><h2>Find out what changes</h2>${result?button('Reopen evidence','series-refresh'):''}</div><p>Pause the game, record a number or change, then repeat. ROMancer tests numeric formats and filters the results. No game profile is required.</p>${entry.error?`<p class="notice warm">${esc(entry.error)}</p>`:''}<div class="field-row">${field('series-title','What are you investigating?',ctx.draft('series-title','A changing number'))}${field('series-value','Value on screen (optional)',ctx.draft('series-value',''),{placeholder:'Leave blank if unknown'})}</div><details><summary>Memory range</summary><div class="field-row">${field('series-offset','System RAM offset',ctx.draft('series-offset','0'))}${field('series-length','Bytes to observe (1–4096)',ctx.draft('series-length','2048'))}</div><p>Offsets refer to the memory region exposed by the emulator. ROMancer does not invent a CPU address from this number.</p></details><div class="actions">${button(result?'Start a separate investigation':'Capture before','series-start',{primary:!result,disabled:!ready})}${button('Open Playtest','navigate',{id:'playtest'})}</div>${!ready?'<p class="subtle">Load the selected ROM in Playtest to record observations. Saved evidence can be read without a running game.</p>':''}${result?`<div class="identity"><strong>${esc(result.title)}</strong><span>${result.observation_count} observations · ${result.unchanged_controls} unchanged controls</span>${result.runtime_trusted?'':'<strong>Historical evidence · read only</strong>'}</div><div class="field-row">${field('series-label','Observation label',ctx.draft('series-label',''))}${select('series-relation','What happened?',[['changed','It changed'],['increased','It increased'],['decreased','It decreased'],['unchanged','It stayed unchanged (control)'],['delta','It changed by an exact amount']],ctx.draft('series-relation','changed'))}${field('series-delta','Exact change, when selected',ctx.draft('series-delta',''),{placeholder:'For example -5'})}</div>${button('Capture & investigate','series-capture',{primary:true,disabled:!ready||!result.runtime_trusted||result.observation_count>=32})}<p class="notice">${esc(result.next_experiment)}</p><details><summary>Observation history · ${result.history.length}</summary><div class="table-wrap"><table><thead><tr><th>Observation</th><th>Number supplied</th><th>Change</th><th>Native sequence</th></tr></thead><tbody>${result.history.map(row=>`<tr><td>${esc(row.label)}</td><td>${esc(row.value??'—')}</td><td>${esc(row.relation)}</td><td>${esc(row.sequence)}</td></tr>`).join('')}</tbody></table></div></details><h3>Correlated hypotheses · ${result.total}</h3><p class="subtle">Agreement across observations does not yet identify a named property, writing instruction or ROM location.</p>${result.truncated?`<p class="notice warm">Showing the best ${candidates.length} of ${result.total} matching hypotheses. Narrow the range or add an observation to separate them.</p>`:''}${rows.length?`<div class="table-wrap"><table><thead><tr><th>RAM offset</th><th>Format tested</th><th>Values observed</th><th>Display relationship</th><th></th></tr></thead><tbody>${rows.map(row=>`<tr><td><code>0x${row.offset.toString(16)}</code></td><td>${row.width*8} bit · ${esc(row.endian)} · ${esc(row.encoding)}${row.signed?' · signed':''}</td><td>${row.values.map(esc).join(' → ')}</td><td>${row.model==='exact'?'Matches supplied numbers':row.model==='constant_offset'?'Stored = displayed '+(row.bias<0?'− '+Math.abs(row.bias):'+ '+row.bias):'Matches change/control observations'}</td><td>${button('Add watch','series-watch',{id:row.candidate_id})}</td></tr>`).join('')}</tbody></table></div><div class="actions">${button('Previous hypotheses','series-page',{id:'-1',disabled:!entry.page})}<span>Page ${entry.page+1}</span>${button('Next hypotheses','series-page',{id:'1',disabled:(entry.page+1)*24>=candidates.length})}</div>`:'<p>No surviving numeric hypotheses yet. Keep the earlier observations and try the suggested next experiment.</p>'}`:''}</section>`;
}
