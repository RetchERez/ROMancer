import {selectionKey} from './tool_inputs.js';
import {esc,button,field,select,read} from './common.js';
const hex=v=>'0x'+v.toString(16);
const bound=(state,r)=>r?.source_sha256===state.artifact?.sha256&&r.artifact_id===state.artifact?.artifact_id;
function integer(id,min,max){const text=read(id),value=Number(text);if(!text.trim()||!Number.isSafeInteger(value)||value<min||value>max)throw Error('Choose a whole number from '+min+' to '+max+'.');return value;}

export async function structuralLab(ctx){
 const {state}=ctx,scope=selectionKey(state),params={...ctx.sourceParams()};let entry=state.structuralLab;
 if(entry?.scope!==scope)state.structuralLab=entry={scope,result:null,generation:0};
 const current=()=>selectionKey(state)===scope&&state.structuralLab===entry;
 if(state.structuralPrefill?.scope===scope){const p=state.structuralPrefill;state.structuralPrefill=null;ctx.setDraft('lab-offset',String(p.offset));ctx.setDraft('lab-length',String(p.length));}
 const result=bound(state,entry.result)?entry.result:null;
 ctx.use({
  'lab-survey':async()=>{
   if(!current())throw Error('The selected source changed.');
   const window={offset:integer('lab-offset',0,64*1024**2),length:integer('lab-length',1,65536)},generation=++entry.generation;
   const r=await ctx.run('structures.survey',{...params,...window},{render:false,refresh:false});
   if(!current()||entry.generation!==generation)return;
   if(r?.ok===false||!bound(state,r))throw Error(r.error||'Experiment belongs to another source.');
   entry.result=r;entry.window=window;await ctx.render();
  },
  'lab-open':async node=>{
   if(!current()||!result)throw Error('Run an experiment for the selected source first.');
   if(!result.candidates.some(c=>c.candidate_id===node.dataset.id))throw Error('Choose a current hypothesis.');
   const generation=++entry.generation;
   const r=await ctx.run('structures.definition',{...params,...entry.window,candidate_id:node.dataset.id,interpretation:read('lab-interpretation')},{render:false,refresh:false});
   if(!current()||entry.generation!==generation)return;
   if(r?.ok===false||!bound(state,r))throw Error(r.error||'Definition belongs to another source.');
   state.tableProposal={scope,result:r};await ctx.navigate('tables');
  }
 });
 return `<section class="card structural-lab"><h2>Explore ROM structure</h2><p>Test repeated numeric layouts, inspect sample records, and open a neutral editor. These are hypotheses; game meaning and pointer use need behavioral evidence.</p><div class="field-row">${field('lab-offset','Window file offset',ctx.draft('lab-offset','0'))}${field('lab-length','Window bytes (up to 65536)',ctx.draft('lab-length','4096'))}</div>${button('Test this range','lab-survey',{primary:true})}${result?`<p>${result.coverage.positions_tested} layouts tested · start positions sampled every ${result.coverage.position_stride} bytes · ${result.total_candidates} surviving hypotheses${result.truncated?' · result limit reached':''}</p><p class="notice">${esc(result.next_experiment)}</p>${select('lab-interpretation','Open editor as',[['numeric','Neutral numeric values'],['linear-pointer','An explicit linear-pointer hypothesis']],ctx.draft('lab-interpretation','numeric'))}${result.candidates.length?`<div class="table-wrap"><table><thead><tr><th>First record</th><th>Layout</th><th>Sample values and possible targets</th><th></th></tr></thead><tbody>${result.candidates.slice(0,12).map(c=>`<tr><td><code>${hex(c.offset)}</code></td><td>${c.count} records · ${c.stride} bytes/record<br>${c.width*8} bit · ${esc(c.endian)}<br>Target hypothesis: stored − ${hex(c.base)}</td><td>${c.samples.slice(0,3).map(s=>`<div><code>${hex(s.stored_value)} → ${hex(s.target_offset)}</code>${s.target_preview?' · '+esc(s.target_preview):''}</div>`).join('')}</td><td>${button('Open table editor','lab-open',{id:c.candidate_id})}</td></tr>`).join('')}</tbody></table></div><p class="subtle">Showing ${Math.min(12,result.candidates.length)} of ${result.candidates.length} retained hypotheses. Use a smaller range to separate layouts. Opening an editor does not modify ROM bytes.</p>`:'<p>No repeated layout survived these tests. Try another range or use native access evidence to locate data.</p>'}`:''}</section>`;
}
