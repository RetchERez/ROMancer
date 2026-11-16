import {badge,button,esc} from './common.js';
import {fileInput,readJsonFile} from './tool_inputs.js';

const statusLabels={REPLAY_CHECKED:'Replay checked here',IMPORTED:'Imported layout',CHECK_AGAIN:'Needs a fresh check'};

export function discoveryControls(ctx,model,scope,current){
 if(ctx.state.artifact?.kind!=='source')return '';
 const rows=model.discoveries||[],params=ctx.sourceParams();
 const chosen=node=>{
  if(!current()||!rows.some(row=>row.id===node.dataset.id))throw Error('The selected ROM changed. Reopen its Overview.');
  return {...params,discovery_id:node.dataset.id};
 };
 ctx.use({
  'discovery-open':async node=>{
   const opened=await ctx.api.call('discoveries.open',chosen(node));
   if(!current()||opened.source_sha256!==ctx.state.artifact.sha256)return;
   const {document,inspection}=opened;
   if(document.kind==='graphics'){
    const paint=ctx.state.paint||JSON.parse(ctx.draft('paint-buffer','null')||'null');
    if(paint||JSON.parse(ctx.draft('asset-changes','[]')||'[]').length)
     throw Error('Finish or discard your staged graphics changes before switching layouts.');
    ctx.state.results['assets.inspect']=inspection;
    const bitmap=inspection.bitmaps.find(b=>b.id===document.resource||b.palette_id===document.resource)||
       inspection.bitmaps.find(b=>b.id===inspection.tilemaps.find(t=>t.id===document.resource)?.bitmap_id);
    ctx.state.assetBitmapId=bitmap?.id;
    ctx.state.assetPage=0;
    ctx.state.pending=null;
    ctx.setDraft('asset-schema',JSON.stringify(document.definition));
    ctx.state.discoveryGraphics={scope,document_id:inspection.document_id,name:document.name};
    return ctx.navigate('assets');
   }
   ctx.state.tableProposal={scope,result:{source_sha256:opened.source_sha256,definition:document.definition,inspection}};
   return ctx.navigate('tables');
  },
  'discovery-export':async node=>{
   const result=await ctx.run('discoveries.export',chosen(node),{render:false});
   if(current())ctx.notify('Discovery JSON is ready in Export.');
   return result;
  },
  'discovery-remove':async node=>{
   const params=chosen(node);
   return ctx.run('discoveries.remove',params);
  },
  'discovery-import':async()=>{
   if(!current())throw Error('The selected ROM changed.');
   const document=await readJsonFile('discovery-file',256*1024);
   if(current())return ctx.run('discoveries.import',{...params,document});
  }
 });
 return '<details class="card" '+(rows.length?'open':'')+'><summary>Saved discoveries</summary>'+
  (rows.length?'<ul class="saved-discoveries">'+rows.map(row=>'<li><div><strong>'+esc(row.name)+'</strong> '+
   badge(statusLabels[row.status]||row.status,row.status==='REPLAY_CHECKED'?'good':'')+'</div><div class="actions">'+
   button('Open editor','discovery-open',{id:row.id})+button('Prepare JSON export','discovery-export',{id:row.id})+
   button('Remove','discovery-remove',{id:row.id})+'</div></li>').join('')+'</ul>':'<p>Save a discovery after a replay check to reopen it here.</p>')+
  '<div class="field-row">'+fileInput('discovery-file','Discovery JSON for this ROM','.json,application/json')+
  button('Import discovery','discovery-import')+'</div><p class="subtle">Imported layouts are checked against the exact ROM hash. Run the gameplay check locally to reproduce the result.</p></details>';
}
