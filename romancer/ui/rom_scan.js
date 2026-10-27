import {verificationResults,registerVerificationNavigation} from './cartridge_verification.js';
import {cheatClues,registerCheatNavigation} from './cheat_clues.js';
import {engineFindings,registerEngineNavigation} from './engine_findings.js';
import {selectionKey} from './tool_inputs.js';
import {getSettings} from './app_settings.js';
import {esc,button,badge,size,read,field} from './common.js';

export async function ensureRomScan(ctx,rescan=false){
 const {state}=ctx;if(!state.artifact||!state.project)return;
 if(!rescan&&!getSettings().autoDeepScan)return;
 const scope=selectionKey(state);state.romScans??={};if(!rescan&&state.romScans[scope])return;
 const params={...ctx.sourceParams()},entry={status:'SCANNING',job_id:null,result:null};state.romScans[scope]=entry;
 while(Object.keys(state.romScans).length>8)delete state.romScans[Object.keys(state.romScans)[0]];
 const repaint=()=>{if(selectionKey(state)!==scope||state.romScans?.[scope]!==entry)return;const node=document.getElementById('rom-scan-panel');if(node)node.outerHTML=panel(ctx,entry);};
 repaint();
 try{
  const start=await ctx.api.call('rom.scan.start',{...params,rescan});entry.job_id=start.job_id;
  if(start.status==='READY')entry.result=start.result;
  else{
   repaint();
   while(!entry.result){
    if(state.romScans?.[scope]!==entry)return;
    const job=await ctx.api.call('jobs.get',{job_id:start.job_id});
    if(['COMPLETED','FAILED','CANCELLED','INTERRUPTED'].includes(job.status)){
     if(job.status!=='COMPLETED'||!job.result?.ok)throw Error(job.result?.error||'Scan '+job.status.toLowerCase());
     entry.result=job.result;break;
    }
    await new Promise(resolve=>setTimeout(resolve,250));
   }
  }
  entry.status='READY';
 }catch(error){entry.status='ERROR';entry.error=error.message;}
 repaint();
}

export function scanControls(ctx){
 if(!ctx.state.artifact)return '';
 registerCheatNavigation(ctx);registerEngineNavigation(ctx);registerVerificationNavigation(ctx);
 const scope=selectionKey(ctx.state),current=()=>selectionKey(ctx.state)===scope;
 ctx.use({
  'documented-scan-tables':()=>{if(!current())return;return ctx.navigate('tables');},
  'graphics-index-play':()=>ctx.navigate('playtest'),
  'structure-inspect':node=>{if(!current())return;const offset=Number(node.dataset.id);if(!ctx.state.romScans?.[scope]?.result?.structures?.candidates.some(c=>c.offset===offset))throw Error('Rescan this ROM first.');ctx.state.resourceJump=offset;return ctx.navigate('resources');},
  'structure-lab-window':node=>{if(!current())return;const candidate=ctx.state.romScans?.[scope]?.result?.structural_lab?.candidates.find(c=>c.offset===Number(node.dataset.id));if(!candidate)throw Error('Rescan this selected ROM first.');ctx.state.structuralPrefill={scope,offset:candidate.offset,length:Math.min(4096,ctx.state.artifact.size-candidate.offset)};return ctx.navigate('debug');},
  'checked-format-open':node=>{if(!current())return;const feature=ctx.state.romScans?.[scope]?.result?.checked_formats?.features.find(row=>row.id===node.dataset.id);if(feature&&['levels','sound'].includes(feature.page))return ctx.navigate(feature.page);},
  'sound-index-open':()=>ctx.navigate('sound'),
  'graphics-index-view':async node=>{if(!current())return;const index=ctx.state.romScans?.[scope]?.result?.graphics_index,offset=Number(node.dataset.id);if(!index||![...index.banks.map(b=>b.offset),...index.repeated_patterns.flatMap(p=>p.offsets)].includes(offset))throw Error('Rescan the graphics index first.');ctx.state.resourceJump=offset;await ctx.navigate('resources');},
  'rom-rescan':()=>{if(!current())return;return ensureRomScan(ctx,true);},
  'rom-scan-cancel':async()=>{if(!current())return;const entry=ctx.state.romScans?.[scope];if(entry?.job_id)await ctx.api.call('jobs.cancel',{job_id:entry.job_id});},
  'rom-scan-filter':()=>{if(!current())return;ctx.state.romScanQuery=read('rom-scan-query').trim();const node=document.getElementById('rom-scan-panel');if(node)node.outerHTML=panel(ctx,ctx.state.romScans?.[scope]);},
  'rom-scan-inspect':async node=>{if(!current())return;const entry=ctx.state.romScans?.[scope],offset=Number(node.dataset.id);if(!entry?.result?.candidates.some(c=>c.offset===offset))throw Error('Rescan this selected ROM first.');ctx.state.resourceJump=offset;await ctx.navigate('resources');}
 });
 return panel(ctx,ctx.state.romScans?.[scope]);
}

function panel(ctx,entry){
 const result=entry?.result,model=result?.identification,known=model?.profile,refs=result?.catalog?.file,matched=refs?.status==='MATCHED'?refs.matches[0]?.name:null;
 const query=ctx.state.romScanQuery?.toLowerCase()||'',candidates=(result?.candidates||[]).filter(c=>!query||[c.kind,c.preview,c.format,c.offset.toString(16)].join(' ').toLowerCase().includes(query));
 return `<section class="card" id="rom-scan-panel"><div class="card-heading"><h3>ROM investigation</h3>${entry?.status==='SCANNING'?badge('Scanning','warm')+button('Cancel scan','rom-scan-cancel',{disabled:!entry.job_id}):button('Rescan ROM','rom-rescan',{icon:'search'})}</div>${entry?.status==='ERROR'?`<p class="notice warm">${esc(entry.error)}</p>`:!result?'<p class="subtle">'+(getSettings().autoDeepScan?'Automatic offline identification and resource scan. You can keep working.':'Automatic deep scan is off in Settings. Choose Rescan ROM to investigate this file.')+'</p>':`<p><strong>${known?esc(known.name)+(model.status==='MATCHED'?' · exact revision':' · based on matched source'):matched?esc(matched)+' · local catalog match':result.documented_tables?.candidates?.some(c=>c.exact_revision)?'Pokemon Emerald · exact original revision':esc(result.system_id?.toUpperCase()||'Unresolved system')+' · game revision unknown'}</strong></p><p class="subtle">${result.health?'CRC32 '+esc(result.health.crc32)+' · ':''}${size(result.coverage.file_bytes_read)} of ${size(result.coverage.file_size)} read. ${result.coverage.whole_file_read?'Whole file covered.':'Partial coverage.'} Candidate meanings need confirmation.</p>${checkedFormatIndex(result.checked_formats)}${documentedIndex(result.documented_tables)}${verificationResults(result.health)}${graphicsIndex(ctx,result.graphics_index)}${soundIndex(result.sound_system,result.engine_recognition)}${engineFindings(result.engine_recognition)}${cheatClues(result.cheat_references)}${structureIndex(result.structures)}${structuralExperiments(result.structural_lab)}<details><summary>Discoveries · ${Object.entries(result.counts).map(([kind,count])=>esc(kind)+' '+count+(result.coverage.segments.some(s=>s[kind]?.results_truncated)?'+':'')).join(' · ')}</summary><p>Showing up to ${result.coverage.result_limit_per_kind} results per kind. Graphics are sampled; compressed streams have work limits. Exact mapped game edits are in Overview.</p><div class="toolbar">${field('rom-scan-query','Filter discoveries',ctx.state.romScanQuery||'',{placeholder:'text, codec, offset or preview'})}${button('Filter','rom-scan-filter')}</div>${candidates.length?`<div class="table-wrap"><table><thead><tr><th>Location</th><th>Candidate</th><th>Preview</th><th></th></tr></thead><tbody>${candidates.slice(0,20).map(c=>`<tr><td><code>0x${c.offset.toString(16).toUpperCase()}</code></td><td>${esc(c.kind)}<br><small>${esc(c.confidence)}</small></td><td>${esc(c.preview)}</td><td>${button('View bytes','rom-scan-inspect',{id:String(c.offset)})}</td></tr>`).join('')}</tbody></table></div><p class="subtle">${Math.min(20,candidates.length)} of ${candidates.length} stored discoveries. Filter to narrow results.</p>`:'<p>No matching candidates. Custom encodings and layouts need a definition.</p>'}<details><summary>Coverage and limits</summary>${result.limits.map(note=>`<p>${esc(note)}</p>`).join('')}<p>${result.coverage.segments.filter(s=>s.compression?.compression?.partial).length} windows reached the compressed-stream work budget.</p></details></details>`}</section>`;
}

function graphicsIndex(ctx,index){
 if(!index||index.status!=='STORAGE_CANDIDATES')return '';
 const scope=selectionKey(ctx.state),observed=ctx.state.graphicsInvestigations?.[scope]?.result;
 return `<div class="graphics-index"><h4>Graphics organization</h4><p>${index.sampled_cells} stored cells sampled · stride ${index.cell_sampling_stride} · ${esc(index.codec)}</p><p>${observed?'Gameplay candidates available':'Waiting for gameplay'} · ${button('Investigate in Playtest','graphics-index-play')}</p><details><summary>Storage banks and repeated patterns</summary><p>Storage groups are candidates. Byte-identical data can suggest reuse; it does not prove shared game objects or palette ownership.</p><table><thead><tr><th>Bank range</th><th>Nonflat samples</th><th></th></tr></thead><tbody>${index.banks.slice(0,8).map(bank=>`<tr><td><code>0x${bank.offset.toString(16).toUpperCase()}</code> · ${size(bank.length)}</td><td>${bank.sampled_nonflat_cells}</td><td>${button('View bank','graphics-index-view',{id:String(bank.offset)})}</td></tr>`).join('')}</tbody></table><p>${index.repeated_patterns.length} repeated-pattern groups stored (up to32).</p>${index.repeated_patterns.slice(0,8).map(pattern=>`<p>${pattern.count} byte-identical cells · ${pattern.offsets.map(offset=>button('0x'+offset.toString(16).toUpperCase(),'graphics-index-view',{id:String(offset)})).join(' ')}</p>`).join('')}<p class="subtle">Initial indexing assumes tile alignment and samples up to65,536cells. Gameplay matching searches every byte alignment in each requested range.</p></details></div>`;
}

function checkedFormatIndex(info){if(!info?.engine)return '';return `<section class="notice"><h4>Known engine: ${esc(info.engine.name)}</h4><p>${esc(info.engine.evidence)}</p>${info.features.map(row=>`<p><strong>${esc(row.name)}</strong> · ${esc(row.detail)} ${button(row.action,'checked-format-open',{id:row.id})}</p>`).join('')}<p>Engine recognition is separate from a native playtest result.</p></section>`;}
function soundIndex(info,recognition){if(!info)return "";const recognized=recognition?.status==='MATCH'?recognition.findings?.[0]:null;return `<div><h4>Sound hardware & driver</h4><p>${esc(info.hardware.name)}</p><p>Driver: ${recognized?esc(recognized.label)+' · structure recognized':esc(info.driver.name)+' · '+esc(info.driver.status)}</p>${button("Open music & sound","sound-index-open")}</div>`;}

function structureIndex(data){if(!data?.candidates?.length)return '';return `<details><summary>Numeric address candidates · ${data.candidates.length}</summary><p>Numeric words that fall inside supported ROM address windows. A pointer dereference or game purpose has not been observed. Showing up to64 results from bounded sampled windows.</p>${data.candidates.slice(0,16).map(c=>`<p>${button('0x'+c.offset.toString(16),'structure-inspect',{id:String(c.offset)})} stores 0x${c.stored_value.toString(16)} · possible file offset 0x${c.target_offset.toString(16)}</p>`).join('')}</details>`;}

function structuralExperiments(lab){if(!lab)return '';return `<details><summary>Repeated layout hypotheses · ${lab.candidates.length}</summary><p>${esc(lab.scope)}</p><p>Numeric patterns can suggest record layouts. Dereferences and gameplay meanings have not been observed.</p>${lab.candidates.slice(0,8).map(c=>`<p><code>0x${c.offset.toString(16)}</code> · ${c.count} records · ${c.stride} bytes each · ${c.width*8} bit ${button('Investigate layout','structure-lab-window',{id:String(c.offset)})}</p>`).join('')||'<p>No repeated layout survived the sampled experiments. Use Investigation to test a focused range.</p>'}</details>`;}

function documentedIndex(data){if(!data?.candidates?.length)return "";return `<div class="notice"><h4>Named game tables found</h4>${data.candidates.map(c=>`<p>${esc(c.name)} · ${c.count} records · 0x${c.offset.toString(16)} · ${c.exact_revision?"exact original":"pattern match"}</p>`).join("")}${button("Open discovered tables","documented-scan-tables")}</div>`;}
