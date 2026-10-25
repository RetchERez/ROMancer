import {esc,field,select,button,badge,read} from './common.js';
import {selectionKey,fileInput} from './tool_inputs.js';

export function revisionResult(state){const saved=state.revisionLookup;return saved?.scope===selectionKey(state)?saved.result:null;}
export async function identifyRevision(ctx,scope,expected_id){
 const ticket=selectionKey(ctx.state),request=(ctx.state.revisionRequest||0)+1;ctx.state.revisionRequest=request;
 const result=await ctx.run('revision.lookup',{...ctx.sourceParams?.()||{project_id:ctx.state.project.project_id,artifact_id:ctx.state.artifact.artifact_id},scope,expected_id},{render:false});
 if(ticket!==selectionKey(ctx.state)||request!==ctx.state.revisionRequest)throw Error('The selection changed. Identify the selected ROM again.');
 ctx.state.revisionLookup={scope:ticket,result};return result;
}
export function revisionControls(ctx){
 const {state}=ctx,project=state.project?.project_id,result=revisionResult(state),info=state.revisionInfo?.project_id===project?state.revisionInfo:null,list=state.revisionList?.project_id===project?state.revisionList:null;
 ctx.use({
  'revision-info':async()=>{const r=await ctx.run('revision.info',{project_id:project},{render:false});if(state.project?.project_id===project){state.revisionInfo=r;await ctx.render();}},
  'revision-import':async()=>{const file=document.getElementById('revision-file')?.files[0];if(!file)throw Error('Choose a local catalog first.');const scope=read('revision-scope');
   const input=await ctx.api.uploadInput(project,file,'catalog');if(state.project?.project_id!==project)throw Error('The project changed. Import into the selected project again.');
   const r=await ctx.run('revision.import',{project_id:project,input_id:input.input_id,scope},{render:false});if(state.project?.project_id===project){state.revisionInfo=r;state.revisionList=null;state.revisionLookup=null;state.romScans={};ctx.notify(`${r.count} revision references available.`);await ctx.render();}},
  'revision-identify':async()=>{await identifyRevision(ctx,read('revision-scope'),'');await ctx.render();},
  'revision-search':async()=>{const r=await ctx.run('revision.list',{project_id:project,query:read('revision-query')},{render:false});if(state.project?.project_id===project){state.revisionList=r;await ctx.render();}},
  'revision-compare':async()=>{const id=read('revision-expected'),entry=list?.entries?.find(r=>r.id===id);if(!entry)throw Error('Search for and choose a reference first.');await identifyRevision(ctx,entry.scope,id);await ctx.render();}
 });
 const message=result?({MATCHED:'Exact revision matched',UNKNOWN:'No catalog match',MISMATCHED:'Selected reference differs',AMBIGUOUS:'Multiple references match'}[result.status]||result.status):'';
 return `<details class="card"><summary>Identify ROM revision${info?` · ${info.count} references`:''}</summary><p>Compare checksums with a catalog you supply. Unknown files remain unidentified.</p>
 ${select('revision-scope','Checksum scope',[['file','Whole file'],['payload','Cartridge payload (supported layouts)']],ctx.draft('revision-scope','file'))}
 ${fileInput('revision-file','Local JSON, CSV, TSV or XML DAT catalog','.json,.csv,.tsv,.dat,.xml')}<div class="actions">${button('Import catalog','revision-import')}${button('Check catalog size','revision-info')}${button('Identify selected ROM','revision-identify',{disabled:!state.artifact,primary:true})}</div>
 ${result?`<div class="notice">${badge(message,result.status==='MATCHED'?'good':result.status==='MISMATCHED'?'warm':'neutral')}<p>${result.matches.map(r=>esc(r.name)).join('<br>')}</p><p>${esc(result.scope==='file'?'Whole file':'Cartridge payload')} · CRC32 <code>${esc(result.hashes.crc32)}</code></p>${result.status==='MISMATCHED'?'<p>Choose the correct revision or check the checksum scope before applying a patch.</p>':''}</div>`:''}
 <details><summary>Compare a specific reference</summary>${field('revision-query','Reference name',ctx.draft('revision-query',''))}${button('Find references','revision-search')}${list?`${select('revision-expected','Expected reference',list.entries.map(r=>[r.id,`${r.name} · ${r.scope}`]),ctx.draft('revision-expected',''))}${list.truncated?'<p>Narrow your search to see more references.</p>':''}${button('Compare selected reference','revision-compare',{disabled:!list.entries.length||!state.artifact})}`:''}</details></details>`;
}
