import {esc,field,button,badge,size,read} from './common.js';
import {selectionKey,fileInput} from './tool_inputs.js';

export function canApplyPatch(state,preview){return !!(preview?.ok&&preview.plan_id&&preview.changed_bytes>0&&
 preview.project_id===state.project?.project_id&&preview.source_id===state.artifact?.artifact_id&&preview.source_sha256===state.artifact?.sha256);}
export async function preparePatch(ctx,file,expectedReference){
 if(!ctx.state.project||!ctx.state.artifact)throw new Error('Select the original ROM in the top bar first.');
 if(!file)throw new Error('Choose a BPS or IPS patch first.');
 const scope=selectionKey(ctx.state),project_id=ctx.state.project.project_id,artifact_id=ctx.state.artifact.artifact_id,request=(ctx.state.patchRequest||0)+1;ctx.state.patchRequest=request;
 const current=()=>selectionKey(ctx.state)===scope&&ctx.state.patchRequest===request;
 const input=await ctx.api.uploadInput(project_id,file,'patch');
 if(!current())throw new Error('The selected file or ROM changed. Preview the patch for the new selection.');
 const preview=await ctx.run('patches.preview',{project_id,artifact_id,input_id:input.input_id,expected_reference:expectedReference},{render:false});
 if(!current())throw new Error('The selection changed while the patch was checked. Preview it again.');
 ctx.state.patchImport={scope,input,preview,file};return preview;
}
export function patchControls(ctx){
 const {state}=ctx,scope=selectionKey(state),selected=state.patchImport?.scope===scope?state.patchImport:null,preview=selected?.preview;
 ctx.use({'patch-preview':async()=>{const file=document.getElementById('patch-file')?.files[0]||(state.patchFile?.scope===scope?state.patchFile.file:null)||selected?.file;await preparePatch(ctx,file,read('patch-reference'));await ctx.render();},
 'patch-apply':async()=>{const saved=state.patchImport;if(saved?.scope!==selectionKey(state)||!canApplyPatch(state,saved.preview))throw new Error('Preview the patch against this exact ROM first.');
   const ticket=selectionKey(state),result=await ctx.run('patches.apply',{project_id:state.project.project_id,plan_id:saved.preview.plan_id,name:read('patch-build-name')},{render:false});
   if(ticket!==selectionKey(state))return;state.patchImport=null;await ctx.refreshProject();await ctx.setArtifact(result.artifact_id);ctx.notify('Patched build created. Your original is unchanged.');await ctx.navigate('playtest');
 }});
 return `<section class="card" id="patch-import"><h3>Apply a downloaded patch</h3><p>Selected original: <strong>${esc(state.artifact?.name||'Choose a ROM in the top bar')}</strong></p>
 ${fileInput('patch-file','Patch file — choose or drop a BPS / IPS patch','.bps,.ips')}${selected?`<p>${esc(selected.input.name)}</p>`:''}
 ${field('patch-reference','Expected original CRC32 or SHA256 (required for IPS)',ctx.draft('patch-reference',''),{hint:'Use the full-file checksum supplied by the patch author. BPS also checks its embedded checksums.'})}
 <div class="actions">${button('Preview patch','patch-preview',{primary:!preview,disabled:!state.artifact})}</div>
 ${preview?`<div class="notice">${badge(preview.format)} ${size(preview.target_size)} · ${preview.changed_bytes.toLocaleString()} changed bytes<p>${esc(preview.reference)}</p></div>
 ${preview.changed_bytes?`${field('patch-build-name','New build name',ctx.draft('patch-build-name','Patched build'))}${button('Create patched build','patch-apply',{primary:true,disabled:!canApplyPatch(state,preview)})}`:'<p>This patch makes no changes to the selected file.</p>'}
 <details><summary>Changed ranges and identities</summary><p>Original SHA256: <code>${esc(preview.source_sha256)}</code></p><p>Target SHA256: <code>${esc(preview.target_sha256)}</code></p><ul>${(preview.ranges||[]).map(r=>`<li>0x${r.offset.toString(16)} · ${r.length} bytes</li>`).join('')}</ul>${preview.ranges_truncated?'<p>More changed ranges exist; the total byte count includes them.</p>':''}</details>`:'<p class="subtle">Preview first. Applying creates a separate build.</p>'}</section>`;
}
export function mountPatchControls(ctx){
 const root=document.getElementById('patch-import');if(!root)return;
 const invalidate=file=>{ctx.state.patchRequest=(ctx.state.patchRequest||0)+1;if(file)ctx.state.patchFile={scope:selectionKey(ctx.state),file};if(ctx.state.patchImport)ctx.state.patchImport.preview=null;const button=root.querySelector('[data-action="patch-apply"]');if(button)button.disabled=true;};
 root.querySelector('#patch-file')?.addEventListener('change',event=>invalidate(event.target.files[0]));
 root.querySelector('#patch-reference')?.addEventListener('input',()=>invalidate());
 root.addEventListener('dragover',event=>{event.preventDefault();event.stopPropagation();});
 root.addEventListener('drop',event=>{event.preventDefault();event.stopPropagation();if(event.dataTransfer.files.length!==1){ctx.notify('Drop one BPS or IPS patch at a time.',true);return;}const file=event.dataTransfer.files[0];invalidate(file);const label=document.createElement('p');label.textContent='Selected patch: '+file.name;root.querySelector('#patch-file').closest('label').append(label);});
}
