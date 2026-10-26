import {selectionKey} from './tool_inputs.js';
import {esc,button,field,select,read} from './common.js';
const hex=v=>Number.isSafeInteger(v)?'0x'+v.toString(16):'Unknown';
const identity=(state,r)=>r?.source_sha256===state.artifact?.sha256&&r.artifact_id===state.artifact?.artifact_id;
function integer(id,min,max){const text=read(id),v=Number(text);if(!text.trim()||!Number.isSafeInteger(v)||v<min||v>max)throw Error('Enter a whole number from '+min+' to '+max+'.');return v;}

export async function executionTrace(ctx){
 const {state}=ctx,scope=selectionKey(state),params={...ctx.sourceParams()};let entry=state.nativeTrace;
 if(entry?.scope!==scope)state.nativeTrace=entry={scope,generation:0,result:null,steps:[{}]};
 const current=()=>selectionKey(state)===scope&&state.nativeTrace===entry;
 const proposal=state.nativeProbe?.scope===scope&&identity(state,state.nativeProbe.result)?state.nativeProbe.result:null;
 if(!entry.checked){
  entry.checked=true;
  try{const r=await ctx.api.call('debugger.capabilities',params);if(current()){
   if(r?.ok===false||!identity(state,r))throw Error(r.error||'Backend identity differs.');entry.capabilities=r;
  }}catch(error){if(current())entry.error=error.message;}
 }
 const remembered=ctx.draft('native-trace-id','');
 if(!entry.loaded&&remembered){
  entry.loaded=true;const generation=++entry.generation;
  try{const r=await ctx.api.call('debugger.get',{...params,evidence_id:remembered,offset:0,limit:100});
   if(current()&&entry.generation===generation){if(r?.ok===false||!identity(state,r))throw Error(r.error||'Capture belongs to another source.');entry.result=r;}
  }catch(error){if(current()&&entry.generation===generation)entry.error=error.message;}
 }
 const result=identity(state,entry.result)?entry.result:null,available=entry.capabilities?.available===true;
 const reason=entry.capabilities?.reason||entry.error||'The native debugger is unavailable for this source or host.';
 const steps=()=>entry.steps.map((_,i)=>({frames:integer('trace-frames-'+i,1,3600),buttons:read('trace-buttons-'+i).split(/[\s,]+/).filter(Boolean),port:0}));
 const accept=async(operation,parameters)=>{
  if(!current())throw Error('The selected source changed. Open its native capture again.');
  const generation=++entry.generation;entry.error=null;
  const r=await ctx.run(operation,{...params,...parameters},{render:false,refresh:false});
  if(!current()||entry.generation!==generation)return;
  if(r?.ok===false||!identity(state,r))throw Error(r.error||'Native capture belongs to another source.');
  entry.result=r;entry.loaded=true;ctx.setDraft('native-trace-id',r.evidence_id);await ctx.render();
 };
 ctx.use({
  'trace-capture':()=>{
   if(!current())throw Error('The selected source changed.');if(!available)throw Error(reason);
   const replay={steps:steps(),start_frame:integer('trace-start',0,3599),event_limit:integer('trace-limit',1,2000),instruction_limit:20000000,timeout:30};
   if(proposal)return accept('debugger.investigate',{investigation_id:proposal.investigation_id,candidate_id:proposal.candidate.candidate_id,replay});
   const start=integer('trace-address',0,0xfffffff),length=integer('trace-length',1,4096);
   return accept('debugger.capture',{config:{...replay,probes:[{kind:read('trace-kind'),start,end:start+length-1}]}});
  },
  'trace-add-step':async()=>{if(!current())throw Error('The source changed.');if(entry.steps.length>=64)throw Error('Use at most 64 input steps.');entry.steps=steps();entry.steps.push({});await ctx.render();},
  'trace-remove-step':async()=>{if(!current())throw Error('The source changed.');if(entry.steps.length>1){entry.steps=steps();entry.steps.pop();await ctx.render();}},
  'trace-manual':()=>{if(!current())throw Error('The source changed.');state.nativeProbe=null;return ctx.render();},
  'trace-recheck':()=>{if(!current())throw Error('The source changed.');entry.checked=false;return ctx.render();},
  'trace-prepare':async()=>{
   if(!current())throw Error('The selected source changed.');
   if(!entry.capabilities?.download?.preparable)throw Error('No pinned preparation is available for this source and host.');
   const r=await ctx.run('debugger.prepare',params,{render:false,refresh:false});
   if(!current())return;if(r?.ok===false||!identity(state,r))throw Error(r.error||'Preparation result belongs to another source.');
   entry.checked=false;entry.error=null;await ctx.render();
  },
  'trace-page':node=>{if(!current()||!result)throw Error('Open a capture first.');return accept('debugger.get',{evidence_id:result.evidence_id,offset:Math.max(0,result.offset+Number(node.dataset.id)*100),limit:100});},
  'trace-open':node=>{
   if(!current()||!result)throw Error('Open a capture for the selected source first.');const offset=Number(node.dataset.id);
   if(!Number.isSafeInteger(offset)||offset<0||offset>=state.artifact.size||!result.events.some(e=>e.file_offset===offset||e.execution_context?.file_offset===offset||e.execution_context?.source_candidate_offset===offset))throw Error('Choose a captured source location.');
   const event=result.events.find(e=>e.file_offset===offset||e.execution_context?.file_offset===offset||e.execution_context?.source_candidate_offset===offset);
   state.nativeSourceContext={scope,evidence_id:result.evidence_id,offset:result.offset,event_id:event.id,source_offset:offset};
   state.resourceJump=offset;return ctx.navigate('resources');
  }
 });
 const open=offset=>Number.isSafeInteger(offset)?button(hex(offset),'trace-open',{id:String(offset)}):'Unresolved';
 const watched=proposal?`<div class="notice"><strong>Investigating RAM ${hex(proposal.candidate.offset)} · ${proposal.candidate.width} bytes</strong><p>Physical watch derived from the observed core buffer, including banked RAM.</p>${button('Use a manual address instead','trace-manual')}</div>`:
  `<details><summary>Manual CPU address watch</summary><div class="field-row">${select('trace-kind','Access type',[['write','Writes'],['read','Reads'],...(state.artifact.system_id==='genesis'?[]:[['exec','Execution']])],ctx.draft('trace-kind','write'))}${field('trace-address','CPU start address',ctx.draft('trace-address','0x100'))}${field('trace-length','Address bytes',ctx.draft('trace-length','1'))}</div></details>`;
 const route=`<h3>Replay input</h3><div class="table-wrap"><table><thead><tr><th>Step</th><th>Frames</th><th>Buttons held</th></tr></thead><tbody>${entry.steps.map((step,i)=>`<tr><td>${i+1}</td><td>${field('trace-frames-'+i,'Frames',ctx.draft('trace-frames-'+i,String(step.frames??120)))}</td><td>${field('trace-buttons-'+i,'Buttons (blank for none)',ctx.draft('trace-buttons-'+i,step.buttons?.join(' ')||''),{placeholder:'For example start or a right'})}</td></tr>`).join('')}</tbody></table></div><div class="actions">${button('Add input step','trace-add-step',{disabled:entry.steps.length>=64})}${button('Remove last step','trace-remove-step',{disabled:entry.steps.length<=1})}</div><div class="field-row">${field('trace-start','Start recording after frame',ctx.draft('trace-start','0'))}${field('trace-limit','Maximum sampled events',ctx.draft('trace-limit','200'))}</div>`;
 const evidence=!result?'':`<h3>Captured evidence · ${esc(result.total_events)} events</h3><p>${esc(result.backend?.backend||'Native debugger')} ${esc(result.backend?.version||'')} · ${result.runtime_trusted?'Authenticated capture':'Historical capture'}</p>${result.status==='BUDGET_EXCEEDED'||result.omitted_events?`<p class="notice warm">Partial capture: an event or instruction limit was reached. ${esc(result.omitted_events??0)} events were omitted. Narrow the watch or recording window.</p>`:''}<p>${result.route_complete?'Replay reached its requested end.':'Replay did not reach its requested end.'}</p>${result.events.length?`<div class="table-wrap"><table><thead><tr><th>Event</th><th>CPU address</th><th>Value</th><th>Execution context</th><th>Context in source</th><th>Access in source</th></tr></thead><tbody>${result.events.map(e=>`<tr><td>${esc(e.id)} · ${esc(e.kind)}</td><td><code>${hex(e.address)}</code></td><td><code>${hex(e.value)}</code></td><td><code>${hex(e.execution_context?.pc)}</code>${e.registers?`<details><summary>Registers</summary><pre>${esc(Object.entries(e.registers).map(([k,v])=>k+' = '+hex(v)).join('\n'))}</pre></details>`:''}</td><td>${Number.isSafeInteger(e.execution_context?.source_candidate_offset)?button('Possible '+hex(e.execution_context.source_candidate_offset),'trace-open',{id:String(e.execution_context.source_candidate_offset)})+'<small>Unique byte-pattern candidate; mapper unresolved.</small>':open(e.execution_context?.file_offset)}</td><td>${open(e.file_offset)}</td></tr>`).join('')}</tbody></table></div>`:'<p>No matching access was sampled. Check the route, start frame and watch range. An empty capture does not prove that the location is unused.</p>'}<div class="actions">${button('Previous events','trace-page',{id:'-1',disabled:result.offset===0})}<span>${result.total_events?result.offset+1:0}–${Math.min(result.offset+result.events.length,result.total_events)} of ${result.total_events}</span>${button('Next events','trace-page',{id:'1',disabled:result.offset+100>=Math.max(result.total_events,result.total_instruction_samples||0)})}</div>`;
 const instructions=!result?.instruction_samples?.length?'':`<details><summary>Native instruction samples · ${esc(result.total_instruction_samples)}</summary><p>Ordered within this instruction sample only. The memory-access sequence has separate ordering.</p><div class="table-wrap"><table><thead><tr><th>Sample</th><th>CPU PC</th><th>Disassembly</th></tr></thead><tbody>${result.instruction_samples.map(row=>`<tr><td>${esc(row.id)}</td><td><code>${hex(row.pc)}</code></td><td><code>${esc(row.assembly)}</code></td></tr>`).join('')}</tbody></table></div></details>`;
 const budget=state.artifact.system_id==='genesis'?'At most 3,600 frames and 30 seconds. Global instruction sampling is separate from read/write watches and stops after at most 2,000 records; it does not count every instruction executed during the rest of the replay.':'At most 3,600 frames, 20 million instruction callbacks and 30 seconds.';
 const download=entry.capabilities?.download,preparation=!available&&download?.preparable?`<div class="notice"><p>Prepare the official debugger once · ${(download.download_bytes/1048576).toFixed(1)} MiB download. Later captures work offline. No ROM data is uploaded.</p><p>External tool license: ${esc(download.license)} · <a href="${esc(download.source_url)}" target="_blank" rel="noopener noreferrer">Upstream source and notices</a></p>${button('Prepare debugger','trace-prepare',{primary:true})}</div>`:'';
 return `<section class="card native-execution-trace" id="native-accesses"><div class="card-heading"><h2>Trace actual accesses</h2>${button('Check debugger','trace-recheck')}</div><p>Replay from power on with normal controller input. Record accesses and their execution context, then inspect mapped source bytes. This is a separate session; it does not resume Playtest.</p>${!available?`<p class="notice warm">${esc(reason)}</p>`:''}${entry.error?`<p class="notice warm">${esc(entry.error)}</p>`:''}${preparation}${watched}${route}${button(proposal?'Replay & investigate this value':'Replay & capture accesses','trace-capture',{primary:true,disabled:!available,reason})}<p class="subtle">${budget} Context is a lead; DMA ownership and the meaning of a value remain unproven.</p>${evidence}${instructions}</section>`;
}

export async function observedSourceContext(ctx){
 const {state}=ctx,scope=selectionKey(state),entry=state.nativeSourceContext;
 if(!entry||entry.scope!==scope)return '';
 const current=()=>selectionKey(state)===scope&&state.nativeSourceContext===entry;
 if(!entry.result){
  try{const r=await ctx.api.call('debugger.get',{...ctx.sourceParams(),evidence_id:entry.evidence_id,offset:entry.offset,limit:100});
   if(!current())return '';
   if(r?.ok===false||!identity(state,r))throw Error(r.error||'Capture belongs to another source.');entry.result=r;
  }catch(error){if(!current())return '';return `<p class="notice warm">Access evidence could not be reopened: ${esc(error.message)}</p>`;}
 }
 const r=entry.result,event=r.events.find(e=>e.id===entry.event_id),context=event?.execution_context;
 if(!event||![event.file_offset,context?.file_offset,context?.source_candidate_offset].includes(entry.source_offset))return '';
 ctx.use({'source-capture-back':()=>{if(!current())throw Error('The selected source changed.');return ctx.navigate('debug');},
  'source-capture-dismiss':()=>{if(!current())return;state.nativeSourceContext=null;return ctx.render();}});
 const candidate=context?.source_candidate_offset===entry.source_offset&&context?.file_offset!==entry.source_offset;
 return `<section class="card observed-source-context"><div class="card-heading"><h3>Why these bytes are open</h3>${button('Dismiss','source-capture-dismiss')}</div><p>${r.runtime_trusted?'Authenticated native capture':'Historical capture'} · ${esc(r.backend?.backend||'Debugger')} ${esc(r.backend?.version||'')} · event ${event.id}</p><p>Observed <strong>${esc(event.kind)}</strong> at CPU address <code>${hex(event.address)}</code>, value <code>${hex(event.value)}</code>. Execution context: <code>${hex(context?.pc)}</code>.</p><p>${candidate?'This source location is a unique byte-pattern candidate. Active mapper state was not established.':'This source location was mapped in the captured native event.'} Game meaning and causal ownership remain separate questions.</p>${button('Back to captured evidence','source-capture-back')}</section>`;
}
