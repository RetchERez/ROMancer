import {esc,button,badge} from './common.js';
import {selectionKey} from './tool_inputs.js';

export function registerEngineNavigation(ctx){
 const scope=selectionKey(ctx.state);
 ctx.use({'engine-view-bytes':async node=>{
  const doc=ctx.state.romScans?.[scope]?.result?.engine_recognition,offset=Number(node.dataset.id);
  if(scope!==selectionKey(ctx.state)||doc?.source_sha256!==ctx.state.artifact?.sha256||!Number.isSafeInteger(offset)||
     !doc.findings?.some(row=>row.locations?.some(location=>location.offset===offset)))throw Error('Scan the selected source before opening an engine location.');
  ctx.state.resourceJump=offset;await ctx.navigate('resources');
 }});
}

export function engineFindings(doc){
 if(!doc?.findings?.length){
  if(doc?.status==='AMBIGUOUS')return '<p class="notice warm">Multiple engine structures matched. The result is ambiguous; no table was selected.</p>';
  if(doc?.status==='BUDGET_EXCEEDED')return `<p class="notice warm">Engine scan reached its work budget: ${esc(doc.budget_reason||'limit reached')}. No complete finding is reported.</p>`;
  return '';
 }
 return `<details class="engine-findings"><summary>Recognized data structures · ${doc.findings.length}</summary><p>Recognition follows code references and validates linked records in this ROM. Playback and editing support are checked separately.</p>${doc.findings.map(row=>{const evidence=row.evidence||{};return `<div class="notice"><strong>${esc(row.label||row.family)}</strong> ${badge('Code + linked data','good')}<p>${evidence.song_entries!==undefined?`${evidence.song_entries} song-table entries · ${evidence.nonempty_songs} nonempty songs. `:''}${evidence.anchor_count!==undefined?`${evidence.anchor_count} code references agree. `:''}Engine version and gameplay are not certified by this scan.</p><div class="actions">${(row.locations||[]).map(location=>button('View '+location.label,'engine-view-bytes',{id:String(location.offset)})).join('')}</div>${/^https?:\/\//i.test(row.reference||'')?`<a href="${esc(row.reference)}" target="_blank" rel="noreferrer noopener">Format reference</a>`:''}</div>`;}).join('')}</details>`;
}
