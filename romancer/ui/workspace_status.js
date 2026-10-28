import {esc,badge} from './common.js';
import {selectionKey} from './tool_inputs.js';

export function saveStatus(snapshot){return snapshot.failed?{label:'Save failed',tone:'danger'}:snapshot.pending?{label:'Saving…',tone:'warm'}:{label:'Saved',tone:'good'};}
export function guardClose(event,queue,state={}){const active=state.job&&!['COMPLETED','FAILED','CANCELLED','INTERRUPTED'].includes(state.job.status);if(!queue.snapshot().unsafe&&!hasStagedChanges(state)&&!active)return;event.preventDefault();event.returnValue='';}
export function artifactStatus(artifact){return artifact?{label:artifact.kind==='source'?'Original':'Build',tone:artifact.kind==='source'?'neutral':'good'}:{label:'No file',tone:'neutral'};}
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
function changed(items){return Array.isArray(items)&&items.some(c=>c.before_pixels? !equal(c.before_pixels,c.after_pixels):Object.hasOwn(c,'before')?!equal(c.before,c.after):true);}
export function hasStagedChanges(state){
 if(!state.project||!state.artifact)return false;
 if(state.pending?.artifact_id===state.artifact.artifact_id||state.gameEditPlan?.scope===selectionKey(state))return true;
 if(state.gameMapsView?.scope===selectionKey(state)&&[...(state.gameMapsView.models?.values()||[])].some(model=>model.values().length))return true;
 const prefix=state.project.project_id+':'+state.artifact.artifact_id+':';
 for(const [key,value] of Object.entries(state.drafts||{})){
  if(!key.startsWith(prefix))continue;
  if(/:(?:asset-changes|table-changes|level-changes|sound-changes|command-changes)$/.test(key)){try{const data=JSON.parse(value);if(changed(Array.isArray(data)?data:data?.changes))return true;}catch{}}
  if(key.endsWith(':command-sequence')||key.includes(':command-sequence-')){try{if(JSON.parse(value)?.changed)return true;}catch{}}
  if(key.endsWith(':hex-changes')){try{const saved=JSON.parse(value);if(saved.artifact_id===state.artifact.artifact_id&&saved.sha256===state.artifact.sha256&&saved.edits?.length)return true;}catch{}}
  if(key.endsWith(':game-map-changes')){try{const saved=JSON.parse(value);if(saved.source_sha256===state.artifact.sha256&&Object.values(saved.changes_by_header||{}).some(changed))return true;}catch{}}
  if(key.includes(':game-')){const field=state.gameVisualModel?.model?.fields?.find(f=>key.endsWith(':game-'+f.id));if(field&&String(field.value)!==String(value))return true;}
  if(key.endsWith(':paint-buffer')){try{const paint=JSON.parse(value),doc=state.results?.['assets.inspect'];const bitmap=doc?.document_id===paint.document_id?doc.bitmaps.find(b=>b.id===paint.bitmap_id):null;if(bitmap?.cells[paint.cell_index]&&!equal(paint.pixels,bitmap.cells[paint.cell_index].pixels))return true;}catch{}}
  const table=state.results?.['tables.inspect'];
  if(table&&key.includes(':table-cell-'+table.document_id))for(const row of table.rows)for(const [index,cell] of row.cells.entries())if(key.endsWith('-'+row.index+'-'+index)&&String(value)!==String(cell.value))return true;
  const script=state.results?.['script.inspect'];
  if(script?.records&&key.includes(':script-segment-'))for(const [index,record] of script.records.entries())for(const segment of record.segments)if(key.endsWith(':script-segment-'+index+'-'+segment.index)&&String(value)!==String(segment.text))return true;
 }
 return state.hexDraft?.scope===selectionKey(state)&&!!state.hexDraft?.changes?.size;
}
export function workspaceStatus(state,snapshot,includeFile=true){const file=artifactStatus(state.artifact),save=saveStatus(snapshot);return `<div class="workspace-state" aria-label="File and edit status">${includeFile?badge(file.label,file.tone):''}${hasStagedChanges(state)?badge('Edits not built','warm'):''}<span id="draft-save-status" role="status" aria-live="polite" class="save-state ${save.tone}">${esc(hasStagedChanges(state)&&!snapshot.failed&&!snapshot.pending?'Draft saved':save.label)}</span>${snapshot.failed?'<button type="button" data-action="draft-retry">Retry save</button>':''}</div>`;}
