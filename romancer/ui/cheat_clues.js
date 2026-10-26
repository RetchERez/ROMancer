import {esc,button,badge,field,read} from './common.js';
import {fileInput,selectionKey} from './tool_inputs.js';
import {ensureRomScan} from './rom_scan.js';

const hex=value=>'0x'+Number(value).toString(16).toUpperCase();
function documentFor(state){const own=state.results?.['cheats.inspect'];if(own?.scope===selectionKey(state)&&own.source_sha256===state.artifact?.sha256)return own;return state.romScans?.[selectionKey(state)]?.result?.cheat_references;}
export function registerCheatNavigation(ctx){
 const scope=selectionKey(ctx.state);
 ctx.use({'cheat-view-bytes':async node=>{
  if(scope!==selectionKey(ctx.state))throw Error('The selected source changed. Scan it again.');
  const offset=Number(node.dataset.id),doc=documentFor(ctx.state);
  const found=doc?.source_sha256===ctx.state.artifact?.sha256&&doc.entries?.some(row=>row.alternatives?.some(group=>group.some(part=>part.locations?.some(location=>location.offset===offset))));
  if(!Number.isSafeInteger(offset)||offset<0||!found)throw Error('Scan the selected source before opening a code location.');
  ctx.state.resourceJump=offset;await ctx.navigate('resources');
 }});
}

export function cheatClues(doc,{paging=false}={}){
 if(!doc||!doc.catalog_count)return '';
 const rows=doc.entries||[],page=doc.page||0,limit=doc.limit||20,pages=Math.max(1,Math.ceil((doc.total||0)/limit));
 const pager=paging&&pages>1?`<div class="actions">${button('Previous','cheat-page',{id:String(page-1),disabled:page===0})}<span>Page ${page+1} of ${pages}</span>${button('Next','cheat-page',{id:String(page+1),disabled:page+1>=pages})}</div>`:'';
 const limits=doc.response_truncated?'<p class="notice warm">Some reference text or decoded details were shortened for the result limit. Full imported text remains in the local catalog.</p>':'';
 return `<details class="cheat-clues"><summary>Code references · ${doc.total} matching entries</summary><p>Labels describe the source’s claim. Operation on this ROM has not been independently verified. Bank candidates do not establish the active bank.</p>${limits}${!rows.length?`<p>${doc.catalog_count} references imported; no matching references for this ROM. Other games’ offsets are not applied here.</p>`:`<div class="table-wrap"><table><thead><tr><th>Source label</th><th>Revision</th><th>Decoded locations</th></tr></thead><tbody>${rows.map(row=>`<tr><td><strong>${esc(row.label)}</strong><br><code>${esc(row.code_text)}</code>${row.decode_truncated?`<p class="notice warm">${row.omitted_code_parts} code parts omitted by the analysis budget. This is an incomplete combination.</p>`:''}<details><summary>Source</summary><p>${esc(row.game_title)} · ${esc(row.source_location||'Location not recorded')}</p>${row.source_refs_truncated||row.truncated_fields?.length?'<p>Provenance details shortened; full text retained in the catalog.</p>':''}${/^https?:\/\//i.test(row.source_url||'')?`<a href="${esc(row.source_url)}" target="_blank" rel="noreferrer noopener">Reference</a>`:''}</details></td><td>${badge(row.revision_status||'UNSPECIFIED','neutral')}<br><small>Gameplay unverified</small></td><td>${(row.alternatives||[]).map((group,index)=>`<div>${row.alternatives.length>1?`Alternative ${index+1} · `:''}${group.map(part=>`<p><code>${esc(part.code)}</code>${part.decoded?.address!==undefined?' · CPU '+hex(part.decoded.address)+' · replacement '+hex(part.decoded.value)+(part.decoded.compare!==null&&part.decoded.compare!==undefined?' · expected '+hex(part.decoded.compare):''):''}${part.error?'<br>'+esc(part.error):''}${part.mapping_reason?'<br>'+esc(part.mapping_reason):''}${(part.locations||[]).map(location=>`<br>${button('Inspect '+hex(location.offset),'cheat-view-bytes',{id:String(location.offset)})} <small>${esc(location.mapping_status||'candidate')} · ${esc(location.compare_status||'No compare byte')} · stored ${esc(location.before_hex||'')}</small>`).join('')}</p>`).join('')}</div>`).join('')}</td></tr>`).join('')}</tbody></table></div>`}${pager}${!paging&&(doc.total||0)>rows.length?`<p>Showing ${rows.length} of ${doc.total}. Use Code reference catalog in Resources to search or page through the rest.</p>`:''}<p>These references do not create edits or run cheats. Use a checked definition or investigate the bytes before making a separate build.</p></details>`;
}

export function cheatControls(ctx){
 const {state}=ctx;if(!state.project)return '';
 const project=state.project.project_id,scope=selectionKey(state),current=()=>scope===selectionKey(state);
 const doc=documentFor(state);registerCheatNavigation(ctx);
 const inspect=async(page,query)=>{
  if(!current()||!state.artifact)throw Error('The selected source changed. Choose a source first.');
  const generation=state.cheatRequestGeneration=(state.cheatRequestGeneration||0)+1;
  const result=await ctx.api.call('cheats.inspect',{...ctx.sourceParams(),query,page,limit:20});
  if(!current()||state.cheatRequestGeneration!==generation)return;state.results['cheats.inspect']={...result,query,scope};await ctx.render();
 };
 ctx.use({
  'cheat-import':async()=>{
   const file=document.getElementById('cheat-file')?.files[0];if(!file)throw Error('Choose a local code catalog first.');
   const input=await ctx.api.uploadInput(project,file,'catalog');
   if(state.project?.project_id!==project)throw Error('The project changed. Import into the selected project again.');
   const result=await ctx.api.job('cheats.import',{project_id:project,input_id:input.input_id});
   if(state.project?.project_id!==project)return;
   state.cheatRequestGeneration=(state.cheatRequestGeneration||0)+1;
   delete state.results['cheats.inspect'];state.romScans={};
   ctx.notify(`${result.count} code references imported. The source ROM is unchanged.`);
   await ctx.render();if(current()&&state.artifact)await ensureRomScan(ctx,true);
  },
  'cheat-inspect':()=>inspect(0,read('cheat-query').trim()),
  'cheat-page':node=>{const page=Number(node.dataset.id);if(!Number.isInteger(page)||page<0||page>20000)throw Error('Invalid reference page.');return inspect(page,doc?.query||'');}
 });
 return `<details class="card"><summary>Code reference catalog${doc?` · ${doc.catalog_count} entries`:''}</summary><p>Import documented codes as investigation leads. Required combinations and alternate revision codes stay grouped; publication references do not certify gameplay.</p>${fileInput('cheat-file','Local TXT, JSON, JSONL, CSV or TSV catalog','.txt,.json,.jsonl,.csv,.tsv')}${button('Import code references','cheat-import')}<div class="field-row">${field('cheat-query','Find source labels',doc?.query??ctx.draft('cheat-query',''))}${button('Inspect matching references','cheat-inspect',{disabled:!state.artifact})}</div>${cheatClues(state.results?.['cheats.inspect']?.scope===scope&&state.results['cheats.inspect'].source_sha256===state.artifact?.sha256?state.results['cheats.inspect']:null,{paging:true})}</details>`;
}
