import {esc,button,field,area,select,read} from './common.js';
import {selectionKey,fileInput} from './tool_inputs.js';
const names=[['all','Everything'],['assets','Graphics'],['script','Text'],['tables','Numbers'],['levels','Levels'],['sound','Sound'],['commands','Event scripts'],['notes','My notes']];
const categories=['graphics','text','numbers','level','sound','code','other'];
const integer=id=>{const text=read(id).trim(),value=Number(text);if(!text||!Number.isSafeInteger(value)||value<0)throw Error('Enter a nonnegative offset or byte length.');return value;};
export function researchNoteHelp(notes=[]){return notes.length?'<h4>User research</h4>'+notes.map(n=>'<dl><dt>'+esc(n.title)+'</dt><dd>'+esc(n.text)+'<br>Reference: '+esc(n.reference||'None supplied')+'</dd></dl>').join('')+'<p class="subtle">User notes are not automatically verified game behavior.</p>':'';}
export function useResearchSetup(ctx,kind){
 const {state}=ctx,scope=selectionKey(state),packet=state.researchOpen,restore=state.researchRestore;
 if(restore?.scope===scope&&restore.kind===kind){state.researchRestore=null;for(const [key,value] of Object.entries(restore.fields))ctx.setDraft(key,value);delete state.results[kind+'.inspect'];state.pending=null;return '';}
 if(packet?.scope!==scope||packet.kind!==kind)return '';
 const d=packet.definition??state.artifact.descriptors?.[kind];if(!d){state.researchOpen=null;return '';}
 const keys={assets:'asset-schema',script:'script-schema',levels:'level-definition',sound:'sound-definition'};
 const wanted=kind==='tables'?{'table-name':d.definition.name,'table-offset':String(d.definition.offset),'table-count':String(d.definition.count),'table-stride':String(d.definition.stride),'table-fields':JSON.stringify(d.definition.fields)}:{[keys[kind]]:JSON.stringify(d,null,2)};
 const prior=Object.fromEntries(Object.keys(wanted).map(key=>[key,ctx.draft(key,null)]));
 const page=state.page,ownsSetup=()=>selectionKey(state)===scope&&state.page===page&&state.researchOpen===packet&&ctx.isCurrentRender?.()!==false&&Object.entries(prior).every(([key,value])=>ctx.draft(key,null)===value);
 const differs=Object.keys(wanted).some(key=>prior[key]!==null&&String(prior[key])!==wanted[key]);
 if(differs&&!packet.confirmed){
  ctx.use({'research-keep-setup':()=>{if(!ownsSetup())return;state.researchOpen=null;for(const key of ['connectedAssetSetup','connectedAnimation','connectedTableJump','connectedLevelJump'])if(state[key]?.scope===scope)state[key]=null;return ctx.render();},
   'research-load-setup':async()=>{if(!ownsSetup())throw Error('The editor changed. Review its setup again.');let backups=[];try{backups=JSON.parse(ctx.draft('research-previous-setup','[]'));}catch{}
    if(!Array.isArray(backups))backups=[];const next=[...backups.slice(-3),{kind,sha256:state.artifact.sha256,at:new Date().toISOString(),fields:prior}];
    const value=JSON.stringify(next);if(new TextEncoder().encode(value).length>60000)throw Error('The current setup is too large for a recovery copy. Export your work before replacing it.');
    const params={...ctx.sourceParams(),key:state.page+':research-previous-setup'},old=await ctx.api.call('drafts.get',params);
    if(!ownsSetup())return;
    await ctx.api.call('drafts.save',{...params,revision:old.revision,value});
    if(!ownsSetup())return;ctx.setDraft('research-previous-setup',value);state.researchOpen={...packet,confirmed:true};return ctx.render();},
   'research-restore-setup':()=>{const backups=JSON.parse(ctx.draft('research-previous-setup','[]')),last=backups.at(-1);if(last?.sha256!==state.artifact.sha256)throw Error('The recovery setup belongs to another ROM.');for(const [key,value] of Object.entries(last.fields))ctx.setDraft(key,value);state.researchOpen=null;return ctx.render();}});
  return '<section class="card"><h2>Load saved resource setup?</h2><p>This editor has a different setup draft. Keep it, or load the checked saved definition after storing a recovery copy. Existing document-specific edits stay separate.</p>'+button('Keep current draft','research-keep-setup')+button('Load saved setup','research-load-setup')+'</section>';
 }
 state.researchOpen=null;for(const [key,value] of Object.entries(wanted))ctx.setDraft(key,value);
 delete state.results[kind+'.inspect'];state.candidateReview=null;state.pending=null;
 if(kind==='assets')state.paint=null;
 return '';
}
export async function researchTools(ctx){
 const {state}=ctx,a=state.artifact;if(!a)return '';
 const scope=selectionKey(state),params={...ctx.sourceParams()},generation=(state.researchGeneration||0)+1;state.researchGeneration=generation;
 const current=()=>scope===selectionKey(state)&&generation===state.researchGeneration&&ctx.isCurrentRender?.()!==false;
 let model;
 try{model=await ctx.api.call('research.inspect',{...params,query:ctx.draft('research-query',''),kind:ctx.draft('research-kind','all'),page:state.researchPage||0});}
 catch(error){if(!current())return '';return '<details class="card"><summary>Resource browser & research</summary><p>'+esc(error.message)+'</p></details>';}
 if(!current())return '';if(!model?.ok||model.artifact_id!==a.artifact_id||model.source_sha256!==a.sha256)return '';
 state.researchBrowser={scope,result:model};const resources=model.resources||[],notes=model.notes||[],saved=state.researchImport?.scope===scope?state.researchImport:null;
 const requireCurrent=()=>{if(!current())throw Error('The selected ROM changed. Reload its research.');};
 const run=async(op,extra)=>{requireCurrent();const result=await ctx.run(op,{...params,...extra},{render:false});requireCurrent();return result;};
 const fill=note=>{state.researchEditing={scope,id:note?.id||null};for(const [key,value] of Object.entries({title:note?.title||'',offset:note?.offset??state.hexDraft?.selected??0,length:note?.length??1,category:note?.category||'other',text:note?.text||'',reference:note?.reference||''}))ctx.setDraft('research-note-'+key,String(value));};
 const showNote=async()=>{await ctx.render();if(selectionKey(state)!==scope)return;const form=document.getElementById('research-note-form');if(form){form.open=true;form.scrollIntoView?.({block:'nearest'});}document.getElementById('research-note-title')?.focus?.();};
 ctx.use({
  'research-search':()=>{state.researchPage=0;return ctx.render();},
  'research-page':node=>{state.researchPage=Math.max(0,(state.researchPage||0)+Number(node.dataset.id));return ctx.render();},
  'research-bytes':node=>{requireCurrent();const offset=Number(node.dataset.id);if(!resources.some(r=>r.offset===offset)&&!notes.some(n=>n.offset===offset))throw Error('Reload the current resource list.');state.resourceJump=offset;return ctx.navigate('resources');},
  'research-editor':node=>{requireCurrent();const editor=node.dataset.id,row=resources.find(r=>r.editor===editor);if(!row)throw Error('Reload the current resource list.');state.researchOpen={scope,kind:row.kind};return ctx.navigate(editor);},
  'research-new':()=>{requireCurrent();fill(null);return showNote();},
  'research-edit':async node=>{requireCurrent();if(!notes.some(n=>n.id===node.dataset.id))throw Error('Reload the note.');const result=await ctx.api.call('research.note_get',{...params,note_id:node.dataset.id});requireCurrent();if(result.source_sha256!==a.sha256||result.artifact_id!==a.artifact_id)throw Error('The note belongs to another ROM.');fill(result.note);return showNote();},
  'research-save':async()=>{const note={id:state.researchEditing?.scope===scope?state.researchEditing.id:null,title:read('research-note-title'),offset:integer('research-note-offset'),length:integer('research-note-length'),category:read('research-note-category'),text:read('research-note-text'),reference:read('research-note-reference')};await run('research.note_save',{revision:model.revision,note});state.researchImport=null;fill(null);await ctx.render();ctx.notify('Research note saved. ROM bytes unchanged.');},
  'research-delete':async node=>{requireCurrent();if(!notes.some(n=>n.id===node.dataset.id))throw Error('Reload the note.');if(!confirm('Remove this research note? ROM bytes will stay unchanged.'))return;await run('research.note_delete',{revision:model.revision,note_id:node.dataset.id});state.researchImport=null;await ctx.render();},
  'research-export':async()=>{const result=await run('research.export',{});state.researchExport={scope,result};await ctx.render();},
  'research-preview':async()=>{requireCurrent();const file=document.getElementById('research-file')?.files[0];if(!file)throw Error('Choose a research JSON file.');if(file.size>1024**2)throw Error('Research packs are limited to 1 MiB.');const documentValue=JSON.parse(await file.text());requireCurrent();state.researchImport=null;const review=await run('research.preview',{document:documentValue});state.researchImport={scope,document:documentValue,review,file,name:file.name};ctx.setDraft('research-replace','');return ctx.render();},
  'research-apply':async()=>{requireCurrent();const packet=state.researchImport;if(packet?.scope!==scope||!packet.review?.review_id)throw Error('Review this research pack first.');const selected=document.getElementById('research-file')?.files[0];if(packet.file&&selected&&packet.file!==selected)throw Error('The file changed. Review the new pack first.');const replace=!!document.getElementById('research-replace')?.checked;if(packet.review.replacements.length&&!replace)throw Error('Acknowledge the listed replacements first.');await run('research.apply',{document:packet.document,review_id:packet.review.review_id,replace});state.researchImport=null;for(const kind of ['assets','script','tables','levels','sound'])delete state.results[kind+'.inspect'];state.pending=null;await ctx.render();ctx.notify('Research imported. Saved editor drafts remain separate.');}
 });
 const exp=state.researchExport?.scope===scope?state.researchExport.result.export:null,review=saved?.review;
 const recovered=[];for(const [kind,page] of [['assets','assets'],['script','scripts'],['tables','tables'],['levels','levels'],['sound','sound']]){try{const list=JSON.parse(state.drafts?.[state.project.project_id+':'+a.artifact_id+':'+page+':research-previous-setup']||'[]');for(const row of list)if(row.sha256===a.sha256&&row.kind===kind&&row.fields)recovered.push({...row,page});}catch{}}
 ctx.use({'research-recover-editor':node=>{requireCurrent();const backup=recovered[Number(node.dataset.id)];if(!backup)throw Error('Reload recovery setups.');state.researchRestore={scope,kind:backup.kind,fields:backup.fields};return ctx.navigate(backup.page);}});
 const results=resources.length||notes.length;
 return '<details class="card" open><summary>Resource browser & research</summary><p class="subtle">Checked saved layouts and your own notes for this exact ROM. Notes do not prove game behavior.</p><div class="field-row">'+field('research-query','Find a resource or note',ctx.draft('research-query',''))+select('research-kind','Show',names,ctx.draft('research-kind','all'))+'</div>'+button('Find','research-search')+
 (model.issues||[]).map(r=>'<p class="notice warm">'+esc(r.kind)+': '+esc(r.message)+'</p>').join('')+
 (model.partial?'<p class="notice warm">Showing the first 4,096 declared ranges. Narrow the source declarations to inspect more.</p>':'')+
 (results?'<div class="table-wrap"><table><thead><tr><th>Name</th><th>Kind</th><th>File range</th><th>Open</th></tr></thead><tbody>'+resources.map(r=>'<tr><td>'+esc(r.name)+'</td><td>'+esc(r.kind)+'</td><td>0x'+r.offset.toString(16)+' · '+r.length+' bytes</td><td>'+button('Bytes','research-bytes',{id:String(r.offset)})+button('Editor','research-editor',{id:r.editor})+'</td></tr>').join('')+
 notes.map(n=>'<tr><td>'+esc(n.title)+'</td><td>User note · '+esc(n.category)+'</td><td>0x'+n.offset.toString(16)+' · '+n.length+' bytes</td><td>'+button('Bytes','research-bytes',{id:String(n.offset)})+button('Edit note','research-edit',{id:n.id})+button('Remove','research-delete',{id:n.id})+'</td></tr>').join('')+'</tbody></table></div>':'<p>No matching saved resources or notes. Open a known resource, save a checked layout, or add a note below.</p>')+
 '<div class="actions">'+button('Previous','research-page',{id:'-1',disabled:!model.page})+'<span>Page '+((model.page||0)+1)+'</span>'+button('Next','research-page',{id:'1',disabled:((model.page||0)+1)*50>=Math.max(model.resources_total||0,model.notes_total||0)})+'</div>'+
 '<details id="research-note-form"><summary>Research note</summary>'+button('New note at selected byte','research-new')+field('research-note-title','Name',ctx.draft('research-note-title',''))+'<div class="field-row">'+field('research-note-offset','File offset',ctx.draft('research-note-offset','0'))+field('research-note-length','Byte length',ctx.draft('research-note-length','1'))+select('research-note-category','Category',categories.map(n=>[n,n]),ctx.draft('research-note-category','other'))+'</div>'+area('research-note-text','What you found',ctx.draft('research-note-text',''),3)+field('research-note-reference','Evidence or source reference',ctx.draft('research-note-reference',''))+button('Save note','research-save')+'<p class="subtle">User-authored research. Save notes separately from ROM builds.</p></details>'+
 (recovered.length?'<details><summary>Previous editor setups</summary><p>Restore an explicitly replaced setup draft. This does not alter saved resource definitions or ROM bytes.</p>'+recovered.map((r,i)=>button(r.kind+' · '+r.at,'research-recover-editor',{id:String(i)})).join('')+'</details>':'')+
 '<details><summary>Share or import research</summary><p>One exact-revision pack carries saved definitions and notes. Review names, references and definition byte guards before sharing. It contains no game saves or emulator states.</p>'+button('Export research pack','research-export')+(exp?button('Download research JSON','download',{id:exp.export_id}):'')+
 fileInput('research-file','Research pack JSON','.json')+button('Review selected pack','research-preview')+(review?'<section class="notice"><h3>Import review</h3><p>'+esc(saved.name||'Research pack')+' · '+review.definitions.length+' definitions · '+review.note_count+' notes</p><p>Replaces: '+esc(review.replacements.join(', ')||'Nothing')+'</p><label><input type="checkbox" id="research-replace"> Replace the listed definitions and matching notes</label><p>Other notes stay. ROM bytes stay unchanged. Existing editor drafts are retained.</p>'+button('Import reviewed research','research-apply')+'</section>':'')+'</details></details>';
}
