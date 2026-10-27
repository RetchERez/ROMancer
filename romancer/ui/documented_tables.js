import {esc,button} from './common.js';
import {selectionKey} from './tool_inputs.js';
export function documentedTables(ctx){
 const {state}=ctx;if(state.artifact?.system_id!=='gba')return '';
 const scope=selectionKey(state),params={...ctx.sourceParams()},current=()=>scope===selectionKey(state)&&ctx.isCurrentRender?.()!==false;
 const saved=state.documentedTables?.scope===scope?state.documentedTables.result:null,automatic=state.romScans?.[scope]?.result?.documented_tables;
 const result=saved||(automatic?.source_sha256===state.artifact.sha256?automatic:null);
 ctx.use({'documented-scan':async()=>{if(!current())return;const r=await ctx.run('documented.scan',params,{render:false});if(!current())return;if(r.artifact_id!==state.artifact.artifact_id||r.source_sha256!==state.artifact.sha256)throw Error('The ROM changed. Scan its tables again.');state.documentedTables={scope,result:r};return ctx.render();},
 'documented-open':async node=>{if(!current()||!result?.candidates?.some(r=>r.candidate_id===node.dataset.id))throw Error('Find a current table result first.');const r=await ctx.run('documented.open',{...params,candidate_id:node.dataset.id},{render:false,refresh:false});if(!current())return;if(r.artifact_id!==state.artifact.artifact_id||r.source_sha256!==state.artifact.sha256)throw Error('The ROM changed. Scan its tables again.');state.tableOrigin={scope,note:r.note};state.tableProposal={scope,result:r};return ctx.navigate('tables');}});
 return '<section class="card"><h3>Find game tables</h3><p>Locate supported Pokemon species and move layouts without entering offsets. Review each match before editing.</p>'+button('Find stat and move tables','documented-scan')+
 (result?result.candidates.map(r=>'<div class="notice"><strong>'+esc(r.name)+'</strong><p>'+r.count+' records · 0x'+r.offset.toString(16)+' · '+r.stride+' bytes per record</p><p>'+esc(r.note)+'</p>'+button('Open named table','documented-open',{id:r.candidate_id})+'</div>').join('')+(result.candidates.length?'':'<p>No supported pattern matched. Modified or expanded layouts may need a symbol file or a checked declaration.</p>')+(result.truncated?'<p class="notice warm">The result budget was reached; this is a partial search.</p>':''):'')+'</section>';
}
