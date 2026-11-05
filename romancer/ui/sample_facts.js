import {esc,button,size} from './common.js';
import {selectionKey} from './tool_inputs.js';

const kindLabel=row=>row.kind==='text'?'Possible text':row.kind==='graphics'?(row.confidence==='format-derived'?'Header-declared graphics':'Possible tiles'):'Valid '+row.format.toUpperCase()+' encoding';

export function sampleFacts(ctx,packet){
 const {state}=ctx,record=packet?.record;
 if(packet?.status!=='RECORDED_SAMPLE'||!record||packet.source_sha256!==state.artifact?.sha256||record.sha256!==state.artifact.sha256)return '';
 const scope=selectionKey(state),rows=record.discoveries||[],structures=record.structures||[];
 ctx.use({'sample-location':async node=>{
  if(selectionKey(ctx.state)!==scope)return;
  const offset=Number(node.dataset.id);
  if(!Number.isSafeInteger(offset)||![...rows,...structures].some(r=>r.offset===offset)||offset<0||offset>=state.artifact.size)throw Error('Choose a recorded location for this exact source.');
  ctx.state.resourceJump=offset;await ctx.navigate('resources');
 }});
 const fields=Object.entries(record.header_numbers||{}).slice(0,10);
 return '<div class="recorded-sample"><div class="card-heading"><h4>Recorded sample</h4><span class="badge good">Hash matched</span></div><p><strong>'+esc(record.labels[0])+'</strong> · '+esc(record.system_id.toUpperCase())+' · '+size(record.size)+'</p>'+
 '<p class="subtle">This file matches our offline measurements. The name comes from its supplied filename.</p>'+
 '<details><summary>Measured file facts & locations</summary><p>Checks and offsets describe this exact file. Candidate locations still need investigation before editing.</p>'+
 '<p>CRC32 <code>'+esc(record.crc32)+'</code> · '+esc(record.format)+'</p>'+
 (record.sha1?'<p>SHA-1 <code>'+esc(record.sha1)+'</code></p>':'')+
 (structures.length?'<h4>Measured structures</h4><ul>'+structures.map(row=>'<li>'+esc(row.kind.replaceAll('-',' '))+' · '+row.count+' × '+row.stride+' bytes '+button('Inspect bytes','sample-location',{id:String(row.offset)})+'</li>').join('')+'</ul>':'')+
 (fields.length?'<dl class="field-row">'+fields.map(([key,value])=>'<div><dt>'+esc(key.replaceAll('_',' '))+'</dt><dd>'+esc(String(value))+'</dd></div>').join('')+'</dl>':'')+
 (rows.length?'<div class="table-wrap" role="region" tabindex="0" aria-label="Recorded sample resource locations"><table><thead><tr><th>Offset</th><th>Bytes</th><th>Finding</th><th></th></tr></thead><tbody>'+rows.slice(0,6).map(row=>'<tr><td><code>0x'+row.offset.toString(16).toUpperCase()+'</code></td><td>'+row.length+'</td><td>'+esc(kindLabel(row))+'</td><td>'+button('Inspect bytes','sample-location',{id:String(row.offset)})+'</td></tr>').join('')+'</tbody></table></div><p class="subtle">Showing '+Math.min(6,rows.length)+' recorded locations. The current scan below provides fresh discoveries.</p>':'')+
 '<p class="subtle">Whole-file identity read · graphics sampled · compression '+(record.coverage.compression_work_limited?'work limit reached':'within scan budget')+'. A sample match does not certify an original commercial dump or gameplay behavior.</p></details></div>';
}

