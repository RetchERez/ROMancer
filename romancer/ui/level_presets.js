import {button,select} from './common.js';
import {selectionKey} from './tool_inputs.js';
export function saveLevelDraft(ctx,model){
 if(!model?.doc?.document_id)return;
 const text=JSON.stringify({document_id:model.doc.document_id,changes:model.values()});
 ctx.setDraft('level-changes',text);ctx.setDraft('level-layout-draft-'+model.doc.document_id,text);
}
export function loadLevelDraft(ctx,doc){
 for(const key of ['level-changes','level-layout-draft-'+doc.document_id]){
  try{const draft=JSON.parse(ctx.draft(key,'{}'));if(draft.document_id===doc.document_id&&Array.isArray(draft.changes))return draft.changes;}catch{}
 }
 return [];
}
export async function checkedLevelChoices(ctx,currentName=''){
 if(ctx.state.artifact?.system_id!=='gb')return '';
 const scope=selectionKey(ctx.state),current=()=>scope===selectionKey(ctx.state)&&ctx.isCurrentRender?.()!==false;
 const source={...ctx.sourceParams()};let packet;
 try{packet=await ctx.api.call('levels.presets',source);}catch{return '';}
 if(!current()||!packet?.ok||packet.source_sha256!==ctx.state.artifact.sha256||!packet.presets?.length)return '';
 const selected=packet.presets.find(p=>p.name===currentName)?.id||packet.presets[0].id;
 ctx.use({'levels-preset-open':async()=>{
  if(!current())return;
  const id=globalThis.document.getElementById('level-preset')?.value;
  if(!packet.presets.some(p=>p.id===id))throw Error('Choose a checked level.');
  saveLevelDraft(ctx,ctx.state.levelEditor?.scope===scope?ctx.state.levelEditor:null);
  const result=await ctx.api.call('levels.preset',{...source,preset_id:id});
  if(!current())return;
  if(!result.ok||result.source_sha256!==ctx.state.artifact.sha256)throw Error('This level does not match the selected source.');
  const inspected=await ctx.api.call('levels.inspect',{...source,definition:result.definition});
  if(!current())return;
  if(!inspected?.ok||inspected.source_sha256!==ctx.state.artifact.sha256)throw Error('The checked layout could not be opened.');
  await ctx.api.call('studio.definition',{...source,kind:'levels',definition:result.definition});
  if(!current())return;
  ctx.state.artifact.descriptors={...ctx.state.artifact.descriptors,levels:result.definition};
  ctx.state.results['levels.inspect']=inspected;ctx.state.pending=null;
  ctx.setDraft('level-definition',JSON.stringify(result.definition,null,2));ctx.setDraft('level-room',inspected.rooms[0]?.id||'');
  ctx.setDraft('level-layer','terrain');ctx.setDraft('level-tool','paint');ctx.state.levelRect=null;
  return ctx.render();
 }});
 return '<section class="card"><div class="field-row">'+select('level-preset','Checked level',packet.presets.map(p=>[p.id,p.name]),selected)+button('Open level','levels-preset-open',{primary:true})+'</div><p class="subtle">Stored terrain and baseline graphics. Each screen is shown once; shared uses are listed below it.</p></section>';
}
