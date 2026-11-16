import {esc,button,size} from './common.js';
import {selectionKey} from './tool_inputs.js';

export function sourceEvidence(ctx,packet){
 const source=ctx.state.artifact,record=packet?.record;
 if(packet?.status!=='RECORDED_SOURCE_EVIDENCE'||!source||!record||packet.source_sha256!==source.sha256||record.sha256!==source.sha256||record.size!==source.size)return '';
 const scope=selectionKey(ctx.state),related=record.related||[],samples=record.samples||[];
 const valid=r=>Number.isSafeInteger(r.offset)&&Number.isSafeInteger(r.length)&&r.offset>=0&&r.length>0&&r.length<=source.size-r.offset;
 const locations=[...related.flatMap(r=>r.locations||[]),...samples].filter(valid);
 ctx.use({'evidence-location':async node=>{
  if(selectionKey(ctx.state)!==scope||ctx.state.artifact?.size!==record.size)return;
  const offset=Number(node.dataset.id);
  if(!locations.some(r=>r.offset===offset))throw Error('Choose a recorded location for this exact source.');
  ctx.state.resourceJump=offset;await ctx.navigate('resources');
 }});
 const inspect=r=>valid(r)?button('Inspect bytes','evidence-location',{id:String(r.offset)}):'';
 return '<details class="recorded-sample"><summary>Related source evidence · '+Number(packet.related_total)+' related files</summary>'+
 '<p>Measured against '+Number(packet.source_count)+' files. Shared bytes help locate reusable structures; each game format still needs its own checks.</p>'+
 (related.length?'<div class="table-wrap" role="region" tabindex="0" aria-label="Related source evidence"><table><thead><tr><th>Related file</th><th>Shared file bytes</th><th>Sound contexts</th><th></th></tr></thead><tbody>'+related.map(r=>'<tr><td>'+esc(r.label)+'</td><td>'+size(r.shared_file_bytes)+'</td><td>'+esc([r.sound_contexts?r.sound_contexts+' ROM neighborhoods':'',r.loaded_blocks?r.loaded_blocks+' loaded RAM blocks':'',r.sample_streams?r.sample_streams+' BRR streams':''].filter(Boolean).join(' · ')||'None recorded')+'</td><td>'+((r.locations||[]).length?inspect(r.locations[0]):'')+'</td></tr>').join('')+'</tbody></table></div><p class="subtle">Showing '+related.length+' of '+Number(packet.related_total)+' relationships. Sound contexts describe bounded observations, not a decoded music format or ownership.</p>':'<p>No qualifying shared-byte relationship was recorded for this file.</p>')+
 (record.references?.length?'<h4>Reference input matches</h4>'+record.references.map(r=>'<p><code>'+esc(r.id)+'</code> · '+(r.scope==='prg_chr'?'PRG/CHR inputs; container header excluded':'Entire named ROM input')+(r.board?' · '+esc(r.board):'')+(r.nonlinear?' · mapped cartridge layout':'')+'</p>').join('')+'<p class="subtle">Input matches do not certify complete gameplay or editing support. Reference inventories may include separate chip firmware; they do not determine the selected emulator’s requirements.</p>':'')+
 (record.driver_candidates?.length?'<p>Sound-driver pattern candidates: '+record.driver_candidates.map(esc).join(', ')+'. Sequence formats and pointers remain unchecked.</p>':'')+
 (samples.length?'<h4>Captured sample byte matches</h4>'+samples.map(r=>'<p><code>0x'+r.offset.toString(16).toUpperCase()+'</code> · '+size(r.length)+' '+inspect(r)+'</p>').join('')+'<p class="subtle">Showing '+samples.length+' of '+Number(packet.sample_total)+' locations. Exact encoded segments match captured BRR directory references; transfer, playback and safe editing have not been proved.</p>':'')+
 '</details>';
}
