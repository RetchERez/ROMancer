import {selectionKey} from './tool_inputs.js';
import {esc,button,field,select,read} from './common.js';
function integer(id){const text=read(id),value=Number(text);if(!text.trim()||!Number.isSafeInteger(value))throw Error('Enter a whole number for '+id+'.');return value;}
const hex=value=>'0x'+value.toString(16);

export async function relocationControls(ctx){
 const {state}=ctx,scope=selectionKey(state),params={...ctx.sourceParams()};let entry=state.dataRelocation;
 if(entry?.scope!==scope)state.dataRelocation=entry={scope,references:[{}],generation:0,plan:null,replacement:null};
 const current=()=>selectionKey(state)===scope&&state.dataRelocation===entry;
 const bankDefault={nes:8192,snes:32768,gb:16384,gbc:16384}[state.artifact.system_id]||0;
 const assessment=state.artifact.system_assessment;
 const prg=assessment?.source?.sha256===state.artifact.sha256?assessment.candidates?.filter(c=>c.layout_valid).flatMap(c=>c.regions||[]).find(r=>r.id==='prg-rom'):null;
 const originDefault=state.artifact.system_id==='nes'?(prg?.offset??16):0;
 const baseDefault=state.artifact.system_id==='nes'?0x8000-originDefault:0;
 const references=()=>entry.references.map((_,i)=>({offset:integer('reloc-ref-offset-'+i),width:integer('reloc-ref-width-'+i),
  endian:read('reloc-ref-endian-'+i),base:integer('reloc-ref-base-'+i),target_delta:integer('reloc-ref-delta-'+i)}));
 const spec=()=>({source_offset:integer('reloc-source'),source_length:integer('reloc-length'),target_offset:integer('reloc-target'),
  target_capacity:integer('reloc-capacity'),fill_byte:integer('reloc-fill'),alignment:integer('reloc-alignment'),
  bank_size:integer('reloc-bank'),bank_origin:integer('reloc-origin'),references:references(),
  references_complete:document.getElementById('reloc-references-complete').checked,
  destination_reserved:document.getElementById('reloc-destination-reserved').checked,replacement_input_id:entry.replacement?.input_id||null});
 const invalidate=()=>{if(entry.plan&&state.pending===entry.plan)state.pending=null;entry.plan=null;};
 ctx.use({
  'reloc-add-reference':()=>{if(!current())throw Error('The source changed.');if(entry.references.length>=128)throw Error('Use at most 128 references.');entry.references=references();entry.references.push({});invalidate();return ctx.render();},
  'reloc-remove-reference':()=>{if(!current())throw Error('The source changed.');if(entry.references.length>1){entry.references=references().slice(0,-1);invalidate();return ctx.render();}},
  'reloc-upload':async()=>{
   if(!current())throw Error('The source changed.');const file=document.getElementById('reloc-file').files[0];
   if(!file||!file.size||file.size>48*1024)throw Error('Choose edited data up to 48 KiB.');
   const generation=++entry.generation;const result=await ctx.api.uploadInput(params.project_id,file,'resource');
   if(!current()||entry.generation!==generation)return;entry.replacement=result;invalidate();await ctx.render();
  },
  'reloc-copy-original':()=>{if(!current())throw Error('The source changed.');++entry.generation;entry.replacement=null;invalidate();return ctx.render();},
  'reloc-review':async()=>{
   if(!current())throw Error('The selected source changed.');const declaration=spec(),signature=JSON.stringify(declaration),generation=++entry.generation;
   invalidate();const result=await ctx.run('relocation.plan',{...params,spec:declaration},{render:false,refresh:false});
   if(!current()||entry.generation!==generation)return;
   if(result?.ok===false||result.source_sha256!==state.artifact.sha256||result.artifact_id!==state.artifact.artifact_id)throw Error(result.error||'Relocation plan belongs to another source.');
   if(JSON.stringify(spec())!==signature){ctx.notify('The declaration changed during review. Review it again.');return;}
   entry.references=declaration.references;entry.lastSpec=declaration;
   state.pending=entry.plan={kind:'relocation',plan_id:result.plan_id,artifact_id:params.artifact_id,spec:declaration,report:result};await ctx.render();
  },
  'reloc-build':async()=>{
   if(!current()||!entry.plan||state.pending!==entry.plan)throw Error('Review this source relocation first.');
   if(JSON.stringify(spec())!==JSON.stringify(entry.plan.spec)){invalidate();throw Error('The declaration changed. Review it again before building.');}
   const pending=entry.plan,result=await ctx.run('build.apply',{project_id:params.project_id,plan_id:pending.plan_id},{render:false});
   if(!current())return;
   entry.built={artifact_id:result.artifact_id,sha256:result.sha256,offset:pending.report.relocation.target_offset};
   if(entry.plan===pending){
    let latest;try{latest=spec();}catch{latest=null;}
    const changed=!latest||JSON.stringify(latest)!==JSON.stringify(pending.spec);
    if(latest){entry.references=latest.references;entry.lastSpec=latest;}
    else entry.lastSpec={...entry.lastSpec,references_complete:document.getElementById('reloc-references-complete').checked,destination_reserved:document.getElementById('reloc-destination-reserved').checked};
    invalidate();await ctx.render();ctx.notify(changed?'Build created. Your newer declaration remains.':'Separate relocated build created. Playtest it before exporting.');
   }
  },
  'reloc-inspect-build':async()=>{
   if(!current()||!entry.built)throw Error('Create the reviewed relocated build first.');const built=entry.built;
   await ctx.setArtifact(built.artifact_id);
   if(state.artifact?.artifact_id!==built.artifact_id||state.artifact?.sha256!==built.sha256)throw Error('The selection changed. Open the relocated build again.');
   state.resourceJump=built.offset;await ctx.navigate('resources');
  }
 });
 const report=entry.plan?.report?.relocation,pending=entry.plan&&state.pending===entry.plan;
 return `<details class="card data-relocation"><summary>Move declared data · Advanced</summary><p>Move or grow data inside this cartridge and update explicitly declared linear references. The original extent is preserved. This does not move position-dependent code or discover every consumer.</p><div class="field-row">${field('reloc-source','Original data offset',ctx.draft('reloc-source','0'))}${field('reloc-length','Original allocation bytes',ctx.draft('reloc-length','16'))}${field('reloc-target','Reserved destination offset',ctx.draft('reloc-target','0'))}${field('reloc-capacity','Reserved destination bytes',ctx.draft('reloc-capacity','64'))}</div><div class="field-row">${field('reloc-fill','Expected destination fill byte',ctx.draft('reloc-fill','255'))}${select('reloc-alignment','Declared alignment',[[1,'1 byte'],[2,'2 bytes'],[4,'4 bytes'],[8,'8 bytes'],[16,'16 bytes'],[32,'32 bytes']],ctx.draft('reloc-alignment','1'))}${select('reloc-bank','Declared bank bytes',[[0,'Linear (declared)'],[8192,'8192'],[16384,'16384'],[32768,'32768'],[65536,'65536']],ctx.draft('reloc-bank',String(bankDefault)))}${field('reloc-origin','Bank file origin',ctx.draft('reloc-origin',String(originDefault)))}</div><p>Replacement: <strong>${entry.replacement?esc(entry.replacement.name)+' · '+entry.replacement.size+' bytes':'Copy the original allocation'}</strong></p><div class="field-row"><label class="field">Edited data file (optional, up to 48 KiB)<input type="file" id="reloc-file"></label><div class="actions">${button('Use edited data file','reloc-upload')}${button('Copy original data instead','reloc-copy-original')}</div></div>${entry.built?button('Inspect moved data in the new build','reloc-inspect-build'):''}<h3>External linear references</h3><p>Stored pointer = destination file offset + interior offset + encoding adjustment. Before-bytes must already match the original location. Bank constraints are your declarations; an active mapper is not inferred.</p><div class="table-wrap"><table><thead><tr><th>Pointer file offset</th><th>Bytes</th><th>Order</th><th>Encoding adjustment</th><th>Interior offset</th></tr></thead><tbody>${entry.references.map((ref,i)=>`<tr><td>${field('reloc-ref-offset-'+i,'Pointer file offset',ctx.draft('reloc-ref-offset-'+i,String(ref.offset??0)))}</td><td>${select('reloc-ref-width-'+i,'Pointer bytes',[[2,'2'],[3,'3'],[4,'4']],ctx.draft('reloc-ref-width-'+i,String(ref.width??(2))))}</td><td>${select('reloc-ref-endian-'+i,'Byte order',[['little','Little'],['big','Big']],ctx.draft('reloc-ref-endian-'+i,ref.endian||(state.artifact.system_id==='genesis'?'big':'little')))}</td><td>${field('reloc-ref-base-'+i,'Encoding adjustment',ctx.draft('reloc-ref-base-'+i,String(ref.base??baseDefault)))}</td><td>${field('reloc-ref-delta-'+i,'Interior offset',ctx.draft('reloc-ref-delta-'+i,String(ref.target_delta??0)))}</td></tr>`).join('')}</tbody></table></div><div class="actions">${button('Add reference','reloc-add-reference',{disabled:entry.references.length>=128})}${button('Remove last reference','reloc-remove-reference',{disabled:entry.references.length<=1})}</div><label class="settings-check"><input type="checkbox" id="reloc-references-complete" ${entry.lastSpec?.references_complete?'checked':''}><span>I have declared every external reference required by this move.</span></label><label class="settings-check"><input type="checkbox" id="reloc-destination-reserved" ${entry.lastSpec?.destination_reserved?'checked':''}><span>I have reserved this destination. Matching fill bytes alone do not prove unused space.</span></label><div class="actions">${button('Review data move','reloc-review',{primary:!pending})}${pending?button('Create separate build','reloc-build',{primary:true}):''}</div>${report?`<div class="notice"><p>${report.payload_size} bytes proposed at ${hex(report.target_offset)}. ${report.pointer_updates.length} declared references checked. The original data remains at ${hex(report.source_offset)}.</p><p>Reference completeness and reservation are author declarations. Native gameplay verification is still required.</p></div><div class="table-wrap"><table><thead><tr><th>Reference offset</th><th>Before</th><th>After</th></tr></thead><tbody>${report.pointer_updates.slice(0,16).map(r=>`<tr><td>${hex(r.offset)}</td><td>${hex(r.before)}</td><td>${hex(r.after)}</td></tr>`).join('')}</tbody></table></div>`:''}</details>`;
}
