import {selectionKey} from './tool_inputs.js';
import {esc,button} from './common.js';
const hex=v=>'0x'+v.toString(16);
export function investigationFollow(ctx,capture,entry){
 if(!capture)return '';
 const {state}=ctx,page=state.page,scope=selectionKey(state),params={...ctx.sourceParams()},id=capture.evidence_id;
 const current=()=>selectionKey(state)===scope&&state.page===page&&capture.evidence_id===id;
 const r=entry.follow?.evidence_id===id&&entry.follow?.source_sha256===state.artifact.sha256&&entry.follow?.artifact_id===state.artifact.artifact_id?entry.follow:null;
 ctx.use({'follow-explain':async()=>{if(!current())throw Error('Select this capture again.');const result=await ctx.run('debugger.follow',{...params,evidence_id:id},{render:false});if(!current())return;if(!result.ok||result.source_sha256!==state.artifact.sha256||result.artifact_id!==state.artifact.artifact_id)throw Error(result.error||'Capture source changed.');entry.follow=result;return ctx.render();},
 'follow-open':node=>{
  const offset=Number(node.dataset.id),rows=node.dataset.name==='writer'?r?.writers:r?.source_reads.concat(r.writers);
  const row=rows?.find(item=>item.file_offset===offset);
  if(!current()||!row||!Number.isSafeInteger(offset)||offset<0||offset>=state.artifact.size)throw Error('Choose a captured mapped location.');
  if(Number.isSafeInteger(row.first_event_id)&&row.first_event_id>0)state.nativeSourceContext={scope,evidence_id:id,
   offset:Math.floor((row.first_event_id-1)/100)*100,event_id:row.first_event_id,source_offset:offset};
  state.resourceJump=offset;return ctx.navigate('resources');
 }});
 const table=(rows,key)=>{
  const writer=key==='sampled_writes';
  const cells=items=>items.map(row=>`<tr><td>${button((writer?'Inspect code ':'Inspect ROM bytes ')+hex(row.file_offset),'follow-open',{id:String(row.file_offset),name:writer?'writer':'read'})}</td><td>${row[key]}</td><td>${row.resources.map(v=>esc(v.name)).join(', ')||'No saved definition'}</td></tr>`).join('');
  const grid=items=>`<div class="table-wrap"><table><thead><tr><th>Source location</th><th>Sampled accesses</th><th>Declared resource</th></tr></thead><tbody>${cells(items)}</tbody></table></div>`;
  return rows.length?grid(rows.slice(0,6))+(rows.length>6?`<details><summary>More mapped locations (${rows.length-6})</summary>${grid(rows.slice(6))}</details>`:''):'<p>No mapped locations in this capture.</p>';
 };
 return `<div class="capture-explanation">${button('Explain this capture','follow-explain')}${r?`<h3>What this capture tells us</h3><p>${esc(r.status)} · ${r.coverage.access_events} retained access events${r.coverage.partial?' · partial capture':''}</p><div class="grid-even"><section><h4>Writer code</h4><p>Instructions active during writes. These locations are code, not editable stats.</p>${table(r.writers,'sampled_writes')}</section><section><h4>Source reads</h4><p>Bytes read from the ROM. Open a location to inspect or define its layout.</p>${table(r.source_reads,'sampled_reads')}</section></div><p>${esc(r.scope)}</p><ul>${r.next_steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>${r.coverage.summary_truncated||false?'<p>The summary budget retains up to 128 locations per group. Narrow the watch to investigate omitted locations.</p>':''}`:''}</div>`;
}
