import {editCheckControls} from '../edit_checks.js';
import {useResearchSetup} from '../research_tools.js';
import {numberComparison,mountNumberPreviews,numericBounds} from '../edit_preview.js';
import {selectionKey} from '../tool_inputs.js';
import {esc,button,field,select,read,heading,requireProject,empty,report} from '../common.js';
const numericTypes=['u8','s8','u16','s16','u24','s24','u32','s32'];
const starter=[{name:'Value',offset:0,type:'u8',endian:'little',pointer_base:null}];
function integer(id){const text=read(id).trim(),value=Number(text);if(!text||!Number.isSafeInteger(value))throw new Error('Enter a whole number for '+id+'.');return value;}
function stored(ctx,key,fallback){try{return JSON.parse(ctx.draft(key,JSON.stringify(fallback)));}catch{return fallback;}}
function bounds(field){return {...numericBounds(field.type),...(field.minimum!==undefined?{minimum:field.minimum}:{}),...(field.maximum!==undefined?{maximum:field.maximum}:{})};}
function recordName(row){return row?.label!==undefined?row.label+' · ID 0x'+row.record_id.toString(16).toUpperCase().padStart(2,'0'):'Row '+row.index;}

export async function render(ctx){const setupReview=useResearchSetup(ctx,'tables');if(setupReview)return setupReview;
 const {state}=ctx,missing=requireProject(ctx);if(missing)return missing;
 const artifact=state.artifact;if(!artifact)return empty('Import a ROM first','A table needs an exact source revision.',button('Import ROM','import',{primary:true}));
 const proposal=state.tableProposal?.scope===selectionKey(state)&&state.tableProposal.result.source_sha256===artifact.sha256?state.tableProposal.result:null;
 if(proposal){
  const staged=stored(ctx,'table-changes',null);
  const prior=state.results['tables.inspect'],reset=prior?Number(ctx.draft('table-reset-'+prior.document_id,'0'))||0:0;
  const typed=prior?.source_sha256===artifact.sha256&&prior.rows?.some(row=>row.cells.some((cell,index)=>String(ctx.draft('table-cell-'+prior.document_id+(reset?'-v'+reset:'')+'-'+row.index+'-'+index,String(cell.value))).trim()!==String(cell.value)));
  if(staged?.changes?.length||typed){
   ctx.use({'table-cancel-proposal':()=>{state.tableProposal=null;return ctx.render();}});
   return empty('Finish the current table edits first','The generated layout is ready. Keep your current staged table edits until you create a build or discard them.',button('Return to the current table','table-cancel-proposal'));
  }
  state.tableProposal=null;state.results['tables.inspect']=proposal.inspection;state.pending=null;
  state.tablePreview={scope:selectionKey(state),document_id:proposal.inspection.document_id};
  const d=proposal.definition;for(const [key,value] of Object.entries({'table-name':d.name,'table-offset':d.offset,'table-count':d.count,'table-stride':d.stride,'table-fields':JSON.stringify(d.fields)}))ctx.setDraft(key,typeof value==='string'?value:String(value));
 }
 if(state.connectedTableJump?.scope===selectionKey(state)){const d=artifact.descriptors?.tables?.definition;if(d){const result=await ctx.api.call('tables.inspect',{...ctx.sourceParams(),definition:d,page:Math.floor(state.connectedTableJump.row/50),limit:50});if(ctx.isCurrentRender?.()===false)return '';state.results['tables.inspect']=result;}state.connectedTableJump=null;}
 const saved=artifact.descriptors?.tables?.source_sha256===artifact.sha256?artifact.descriptors.tables.definition:null;
 let model=state.results['tables.inspect'];if(model?.source_sha256!==artifact.sha256)model=null;
 if(!model&&saved){model=await ctx.api.call('tables.inspect',{...ctx.sourceParams(),definition:saved,page:0,limit:50});state.results['tables.inspect']=model;}
 const columns=stored(ctx,'table-fields',saved?.fields||starter);
 const staged=stored(ctx,'table-changes',null);
 let changes=staged&&model&&staged.document_id===model.document_id?staged.changes:[];
 const catalog=model?.row_catalog||[],queryKey='table-name-query-'+(model?.document_id||''),query=ctx.draft(queryKey,'');
 const matches=catalog.filter(row=>recordName(row).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
 const resetKey='table-reset-'+(model?.document_id||''),reset=Number(ctx.draft(resetKey,'0'))||0;
 const inputId=(row,index)=>'table-cell-'+model.document_id+(reset?'-v'+reset:'')+'-'+row+'-'+index;
 function resetCells(){ctx.setDraft(resetKey,String(reset+1));}
 function saveChanges(next){changes=next;ctx.setDraft('table-changes',JSON.stringify({document_id:model.document_id,changes}));state.pending=null;}
 function collectVisible(){
  if(!model)return [];
  const result=new Map(changes.map(change=>[change.row+':'+change.field,change]));
  for(const row of model.rows)for(const [index,cell] of row.cells.entries()){
   const node=document.getElementById(inputId(row.index,index));if(!node)continue;
   const after=integer(node.id),key=row.index+':'+cell.field;
   if(after===cell.value)result.delete(key);else result.set(key,{row:row.index,field:cell.field,before:cell.value,after});
  }
  return [...result.values()];
 }
 function definition(){const active=model?.definition||saved,names=active?.label_source;return {schema_version:1,name:read('table-name').trim(),offset:integer('table-offset'),count:integer('table-count'),stride:integer('table-stride'),fields:columns,...(names?{label_source:names}:{}),...(active?.row_names?{row_names:active.row_names,row_id_base:active.row_id_base||0}:{})};}
 ctx.use({
  'table-add-field':()=>{
   const name=read('table-field-name').trim();if(!name)throw new Error('Name the field first.');
   const field={name,offset:integer('table-field-offset'),type:read('table-field-type'),endian:read('table-field-endian'),pointer_base:read('table-field-base').trim()?integer('table-field-base'):null};
   ctx.setDraft('table-fields',JSON.stringify([...columns,field]));return ctx.render();
  },
  'table-remove-field':node=>{ctx.setDraft('table-fields',JSON.stringify(columns.filter((_,index)=>index!==Number(node.dataset.id))));return ctx.render();},
  'table-inspect':async()=>{
   const result=await ctx.run('tables.save_definition',{...ctx.sourceParams(),definition:definition()},{render:false});
   state.results['tables.inspect']=result.inspection;state.tablePreview=null;state.pending=null;await ctx.render();
  },
  'table-page':async node=>{
   if(!model)return;saveChanges(collectVisible());
   await ctx.run('tables.inspect',{...ctx.sourceParams(),definition:model.definition,page:Math.max(0,model.page+Number(node.dataset.id)),limit:50});
  },
  'table-search':async()=>{if(!model)return;saveChanges(collectVisible());ctx.setDraft(queryKey,read('table-name-query'));await ctx.render();},
  'table-select-record':async()=>{
   if(!model)return;const index=integer('table-record-choice');
   if(!catalog.some(row=>row.index===index))throw Error('Choose a record from the current table.');
   saveChanges(collectVisible());
   await ctx.run('tables.inspect',{...ctx.sourceParams(),definition:model.definition,page:Math.floor(index/model.limit),limit:model.limit});
  },
  'table-review':async()=>{
   if(!model)throw new Error('Load a table definition first.');saveChanges(collectVisible());
   const signature=JSON.stringify(changes);const plan=await ctx.run('tables.plan',{...ctx.sourceParams(),definition:model.definition,document_id:model.document_id,changes},{render:false});
   if(state.results['tables.inspect']?.document_id!==model.document_id||JSON.stringify(collectVisible())!==signature){ctx.notify('Table values changed during review. Review them again.');return;}
   state.pending={kind:'table',plan_id:plan.plan_id,artifact_id:artifact.artifact_id,document_id:model.document_id,changes:structuredClone(changes)};await ctx.render();
  },
  'table-build':async()=>{
   if(state.pending?.kind!=='table'||state.pending.artifact_id!==artifact.artifact_id||state.pending.document_id!==model?.document_id)throw new Error('Review the table changes for this source first.');
   if(JSON.stringify(collectVisible())!==JSON.stringify(state.pending.changes)){state.pending=null;throw new Error('Table values changed after review. Review the changes again.');}
   const reviewed=state.pending;await ctx.run('build.apply',{...ctx.projectParams(),plan_id:reviewed.plan_id},{render:false});
   if(state.pending!==reviewed||JSON.stringify(collectVisible())!==JSON.stringify(reviewed.changes)){ctx.notify('Build created. Your newer table edits are still staged.');return;}
   state.pending=null;ctx.setDraft('table-changes','null');resetCells();await ctx.render();ctx.notify('Build created. Choose it in the source/build selector to playtest.');
  },
  'table-batch':async()=>{
   if(!model)throw new Error('Load a table definition first.');const current=collectVisible();
   const result=await ctx.run('tables.batch',{...ctx.sourceParams(),definition:model.definition,field:read('table-batch-field'),operation:read('table-batch-operation'),value:integer('table-batch-value'),first:integer('table-batch-first'),count:integer('table-batch-count')},{render:false});
   if(state.results['tables.inspect']?.document_id!==model.document_id||result.document_id!==model.document_id)throw Error('Table definition changed. Repeat the batch preview.');
   const merged=new Map(current.map(change=>[change.row+':'+change.field,change]));
   for(const change of result.changes){merged.set(change.row+':'+change.field,change);const index=model.definition.fields.findIndex(field=>field.name===change.field);ctx.setDraft(inputId(change.row,index),String(change.after));}
   saveChanges([...merged.values()]);await ctx.render();ctx.notify(result.changes.length+' batch changes staged. Review before building.');
  },
  'table-discard':()=>{resetCells();saveChanges([]);return ctx.render();},
  'table-target':async node=>{const offset=Number(node.dataset.id);state.resourceJump=offset;await ctx.run('resource.inspect',{...ctx.sourceParams(),offset,length:Math.min(256,artifact.size-offset)},{render:false});await ctx.navigate('resources');}
 });
 const pending=state.pending?.kind==='table'&&state.pending.artifact_id===artifact.artifact_id;
 return `${heading('','Stats & data','')}${editCheckControls(ctx)}${state.tableOrigin?.scope===selectionKey(state)?'<p class="notice">'+esc(state.tableOrigin.note)+'</p>':''}<section class="card"><div class="card-heading"><h3>${esc(model?.definition.name||'No checked stats layout for this ROM yet')}</h3><span>${model?model.total+' records':'No table loaded'}</span>${model&&state.tablePreview?.scope===selectionKey(state)&&state.tablePreview.document_id===model.document_id?button('Save this layout','table-inspect'):''}</div>${!model?'<p>Open a named value from Overview when one is available. To define a new layout, investigate its bytes first.</p>':''}<details class="config"><summary>Table layout · Advanced</summary><div class="field-row">${field('table-name','Table name',ctx.draft('table-name',saved?.name||'Data table'))}${field('table-offset','First record offset',ctx.draft('table-offset',saved?.offset??'0'))}${field('table-count','Record count',ctx.draft('table-count',saved?.count??'16'))}${field('table-stride','Bytes per record',ctx.draft('table-stride',saved?.stride??'1'))}</div><div class="table-wrap"><table><thead><tr><th>Field</th><th>Offset</th><th>Type</th><th>Order</th><th>Pointer base</th><th></th></tr></thead><tbody>${columns.map((field,index)=>`<tr><td>${esc(field.name)}</td><td>${field.offset}</td><td>${esc(field.type)}</td><td>${esc(field.endian)}</td><td>${field.pointer_base??'None'}</td><td>${button('Remove','table-remove-field',{id:String(index)})}</td></tr>`).join('')}</tbody></table></div><details class="config"><summary>Add a field</summary><div class="field-row">${field('table-field-name','Field name',ctx.draft('table-field-name',''))}${field('table-field-offset','Offset within record',ctx.draft('table-field-offset','0'))}${select('table-field-type','Numeric type',numericTypes.map(type=>[type,type]),ctx.draft('table-field-type','u8'))}${select('table-field-endian','Byte order',[['little','Little endian'],['big','Big endian']],ctx.draft('table-field-endian','little'))}${field('table-field-base','Pointer base (optional)',ctx.draft('table-field-base',''))}</div><p>For a linear pointer: target file offset = stored value − base.</p>${button('Add field','table-add-field')}</details>${button('Load table definition','table-inspect',{primary:!model})}</details></section>${model?`<section class="card"><div class="card-heading"><h3>Records</h3><span>${changes.length} staged changes</span></div>${catalog.length?`<div class="field-row">${field('table-name-query','Search record names or IDs',query)}${button('Find records','table-search')}</div><div class="field-row">${select('table-record-choice','Named record',matches.map(row=>[row.index,recordName(row)]),String(matches[0]?.index??''))}${button('Show selected record','table-select-record',{disabled:!matches.length,reason:'No matching record names.'})}</div><p>${matches.length} matching records. Names use the checked layout’s labels or decoded source text. Review pattern-based labels before editing.</p>`:''}<div class="table-wrap"><table class="numeric-table"><thead><tr><th>Row</th>${model.definition.fields.map(field=>`<th>${esc(field.name)}${Number.isFinite(bounds(field).minimum)&&Number.isFinite(bounds(field).maximum)?`<br><small>Range ${bounds(field).minimum}–${bounds(field).maximum}</small>`:''}</th>`).join('')}</tr></thead><tbody>${model.rows.map(row=>`<tr><td>${esc(recordName(row))}<br>${row.label!==undefined?`<small>Row ${row.index}${row.label_status==='unsupported'?' · Unsupported name bytes':row.label_status==='blank'?' · Blank name':''}</small><br>`:''}<code>0x${row.offset.toString(16)}</code></td>${row.cells.map((cell,index)=>`<td><label class="field"><span class="sr-only">${esc(cell.field)}, ${esc(recordName(row))}</span><input id="${inputId(row.index,index)}" value="${esc(ctx.draft(inputId(row.index,index),changes.find(change=>change.row===row.index&&change.field===cell.field)?.after??cell.value))}" inputmode="numeric" aria-label="${esc(cell.field)}, ${esc(recordName(row))}"></label><div data-number-input="${inputId(row.index,index)}" data-before="${cell.value}" data-compact="true" data-minimum="${bounds(model.definition.fields[index]).minimum}" data-maximum="${bounds(model.definition.fields[index]).maximum}">${numberComparison(cell.value,ctx.draft(inputId(row.index,index),changes.find(change=>change.row===row.index&&change.field===cell.field)?.after??cell.value),{compact:true,...bounds(model.definition.fields[index])})}</div>${cell.target_offset!==null?button('Open target 0x'+cell.target_offset.toString(16),'table-target',{id:String(cell.target_offset)}):cell.pointer_resolution?'<span>Unresolved target</span>':''}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="actions">${button('Previous records','table-page',{id:'-1',disabled:!model.page})}<span>Page ${model.page+1}</span>${button('Next records','table-page',{id:'1',disabled:(model.page+1)*model.limit>=model.total})}${button('Review changes','table-review',{primary:!pending})}${pending?button('Create build','table-build',{primary:true}):''}${button('Discard changes','table-discard')}</div></section>${changes.length?`<details class="card"><summary>Staged changes by record</summary><ul>${changes.map(change=>`<li>${esc(recordName(catalog[change.row]||{index:change.row}))}: ${esc(change.field)} ${change.before} → ${change.after}</li>`).join('')}</ul></details>`:''}<details class="card"><summary>Batch change</summary><p>Preview up to1024 source records. Percent changes round halves away from zero. Numeric overflow is refused; declared field limits are also enforced. First row refers to the row number shown with each record.</p><div class="field-row">${select('table-batch-field','Field',model.definition.fields.map(field=>[field.name,field.name]),ctx.draft('table-batch-field',model.definition.fields[0].name))}${select('table-batch-operation','Operation',[['set','Set value'],['add','Add'],['multiply','Multiply'],['percent','Change by percent']],ctx.draft('table-batch-operation','add'))}${field('table-batch-value','Value',ctx.draft('table-batch-value','1'))}${field('table-batch-first','First row',ctx.draft('table-batch-first','0'))}${field('table-batch-count','Record count',ctx.draft('table-batch-count',String(Math.min(10,model.total))))}</div>${button('Preview batch changes','table-batch')}</details>`:''}${report(state.results['tables.plan'],'Table change plan')}${report(state.results['build.apply'],'Built output')}`;
}

export function mount(){mountNumberPreviews();}
