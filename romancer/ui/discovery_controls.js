import {resourceSystem} from './compression_controls.js';
import {esc,field,select,button,read,size} from './common.js';
const systems=[['nes','NES'],['snes','SNES'],['genesis','GEN'],['gb','Game Boy'],['gbc','Game Boy Color'],['gba','GBA']];
function integer(id){const text=read(id).trim(),value=Number(text);if(!text||!Number.isSafeInteger(value))throw new Error('Enter a whole number for '+id+'.');return value;}

export function discoveryControls(ctx){
 const {state}=ctx,artifact=state.artifact;if(!artifact)return '';
 const result=state.results['resources.discover']?.source_sha256===artifact.sha256?state.results['resources.discover']:null;
 ctx.use({
  'discover-scan':async()=>{
   const kind=read('discover-kind');state.discoveryPage=0;
   const kinds=kind==='all'?['text','graphics','compression']:[kind];
   const target=kind==='pointers'?{offset:integer('discover-target'),width:integer('discover-width'),endian:read('discover-endian'),base:integer('discover-base')}:null;
   return ctx.run('resources.discover',{...ctx.sourceParams(),config:{system_id:read('discover-system'),start:integer('discover-start'),length:integer('discover-length'),kinds,target}});
  },
  'discover-compressed':async node=>{
   const row=result?.candidates.find(row=>row.candidate_id===node.dataset.id);if(row?.kind!=='compression')throw new Error('Scan this compressed source again.');
   ctx.setDraft('compression-offset',String(row.offset));ctx.setDraft('compression-allocation',String(row.length));ctx.setDraft('compression-codec',row.format);
   await ctx.run('compression.inspect',{...ctx.sourceParams(),offset:row.offset,allocation:row.length,codec:row.format});
  },
  'discover-page':node=>{state.discoveryPage=Math.max(0,(state.discoveryPage||0)+Number(node.dataset.id));return ctx.render();},
  'discover-inspect':node=>{
   const row=result?.candidates.find(row=>row.candidate_id===node.dataset.id);if(!row)throw new Error('Scan this source revision again.');
   return ctx.run('resource.inspect',{...ctx.sourceParams(),offset:row.offset,length:Math.min(row.length,256)});
  },
  'discover-declare':async node=>{
   const row=result?.candidates.find(row=>row.candidate_id===node.dataset.id);if(!row?.config)throw new Error('This candidate needs a supported resource declaration.');
   const prefix=row.kind==='text'?'text':'gfx';state.candidateReview={artifact_id:artifact.artifact_id,kind:row.kind,reason:row.reason};
   state.resourcePrefill={artifact_id:artifact.artifact_id,prefix,config:row.config};
   delete state.results['script.inspect'];delete state.results['assets.inspect'];state.pending=null;state.paint=null;
   await ctx.navigate(row.kind==='text'?'scripts':'assets');
  }
 });
 const page=state.discoveryPage||0,rows=result?.candidates.slice(page*20,page*20+20)||[];
 return `<section class="card"><div class="card-heading"><h3>Find resources</h3>${button('Discovery help','help-topic',{id:'discovery'})}</div><div class="field-row">${select('discover-system','System',systems,ctx.draft('discover-system',resourceSystem(state)))}${select('discover-kind','Look for',[['all','Text, graphics and known compression'],['text','Printable text'],['graphics','Graphics candidates'],['compression','Known compressed streams'],['pointers','Explicit pointer references']],ctx.draft('discover-kind','all'))}${field('discover-start','Start offset',ctx.draft('discover-start','0'))}${field('discover-length','Bytes to scan (up to16MiB)',ctx.draft('discover-length',String(Math.min(1024*1024,artifact.size))))}</div><details class="config"><summary>Pointer search settings</summary><div class="field-row">${field('discover-target','Target file offset',ctx.draft('discover-target','0'))}${select('discover-width','Pointer bytes',[['2','2'],['3','3'],['4','4']],ctx.draft('discover-width','2'))}${select('discover-endian','Byte order',[['little','Little endian'],['big','Big endian']],ctx.draft('discover-endian','little'))}${field('discover-base','Stored value = file offset + base',ctx.draft('discover-base','0'))}</div></details>${button('Scan selected range','discover-scan',{primary:true,icon:'search'})}${result?`<p class="notice">${result.candidates.length} candidates in${size(result.scanned_length)}. ${result.partial?'Partial scan. ':''}${result.next_offset!==null?'Next range starts at0x'+result.next_offset.toString(16)+'. ':''}${result.results_truncated?'Result limit reached; narrow the range. ':''}Graphics use sampled blocks. Confirm formats before editing.</p>${rows.length?`<div class="table-wrap"><table><thead><tr><th>Resource</th><th>Preview</th><th>Reason</th><th></th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.kind)}<br><code>0x${row.offset.toString(16)}</code><br>${esc(row.confidence)}</td><td>${esc(row.preview)}</td><td>${esc(row.reason)}</td><td><div class="actions">${button('Inspect bytes','discover-inspect',{id:row.candidate_id})}${row.kind==='compression'?button('Inspect stream','discover-compressed',{id:row.candidate_id}):row.config?button('Review declaration','discover-declare',{id:row.candidate_id}):''}</div></td></tr>`).join('')}</tbody></table></div><div class="actions">${button('Previous candidates','discover-page',{id:'-1',disabled:page===0})}<span>Page ${page+1}</span>${button('Next candidates','discover-page',{id:'1',disabled:(page+1)*20>=result.candidates.length})}</div>`:'<p>No candidates in this range. Try a different range or declare a known resource.</p>'}`:''}</section>`;
}
