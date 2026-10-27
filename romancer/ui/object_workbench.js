import {esc,button,select} from './common.js';
import {selectionKey} from './tool_inputs.js';
import {activateCell} from './asset_controls.js';

export async function openObject(ctx,id){
 const scope=selectionKey(ctx.state),result=await ctx.run('objects.open',{...ctx.sourceParams(),object_id:id},{render:false});
 if(scope!==selectionKey(ctx.state))return;
 ctx.state.connectedAssetSetup={scope,result};ctx.state.researchOpen={scope,kind:'assets'};return ctx.navigate('assets');
}

export async function objectWorkbench(ctx,doc,bitmap){
 const {state}=ctx,scope=selectionKey(state),current=()=>scope===selectionKey(state)&&ctx.isCurrentRender?.()!==false;
 const hasSaved=state.artifact?.object_layouts?.objects?.length||state.objectWorkbench?.scope===scope;
 const listing=hasSaved?await ctx.api.call('objects.list',ctx.sourceParams()):{objects:[]};if(!current())return '';
 let entry=state.objectWorkbench?.scope===scope&&state.objectWorkbench.document_id===doc?.document_id?state.objectWorkbench:null;
 if(entry&&!entry.result){
  entry.result=await ctx.api.call('objects.get',{...ctx.sourceParams(),object_id:entry.object_id});if(!current())return '';
  const trace=entry.result.object.trace_id;
  if(trace){try{entry.trace=await ctx.api.call('traces.get',{...ctx.sourceParams(),trace_id:trace});}catch(error){entry.sceneIssue='Saved scene is unavailable. The exact-revision layout remains available.';}}
 }
 if(!current())return '';
 const obj=entry?.result?.object,layout=obj?.definition.layout;
 ctx.use({
  'object-open':node=>{if(!current())throw Error('The selected ROM changed. Open this object from the current selection.');const id=node?.dataset?.id||document.getElementById('object-choice')?.value;if(!listing.objects.some(o=>o.object_id===id))throw Error('Refresh saved objects first.');return openObject(ctx,id);},
  'object-delete':async node=>{if(!current())throw Error('The selected ROM changed.');const id=node.dataset.id,chosen=listing.objects.find(o=>o.object_id===id);if(!chosen)throw Error('Refresh saved objects first.');if(!confirm('Remove the saved layout “'+chosen.name+'”? ROM bytes and builds stay unchanged.'))return;await ctx.run('objects.delete',{...ctx.sourceParams(),object_id:id},{render:false});if(!current())return;if(state.objectWorkbench?.object_id===id)state.objectWorkbench=null;return ctx.render();},
  'object-source':node=>{if(!current()||!entry||!bitmap)throw Error('The selected source changed.');const index=Number(node.dataset.id);if(!layout.indices.includes(index))throw Error('Choose a source used by this object.');activateCell(ctx,doc,bitmap.id,index);entry.selected=index;return ctx.render();}
 });
 const saved=listing.objects.length?select('object-choice','Saved object',listing.objects.map(o=>[o.object_id,o.name+' · '+o.columns+' × '+o.rows+' tiles']),entry?.object_id||listing.objects[0].object_id)+button('Open object','object-open'): '<p>Save verified parts as an object from a captured trace in Playtest.</p>';
 if(!obj)return '<section class="card object-workbench"><h3>Saved objects</h3>'+saved+'</section>';
 const uses=new Map();layout.indices.forEach((index,place)=>{if(index!==null){if(!uses.has(index))uses.set(index,[]);uses.get(index).push(place);}});
 return '<section class="card object-workbench"><div class="card-heading"><h3>'+esc(obj.name)+'</h3>'+button('Remove layout','object-delete',{id:entry.object_id})+'</div><details><summary>Saved objects</summary>'+saved+'</details><div class="object-scene-source"><figure><figcaption>Captured scene · select a source tile to highlight its uses</figcaption>'+(entry.trace?.crop_png_base64?'<canvas id="object-scene" aria-label="Captured scene with selected tile uses" data-scene="'+esc(entry.trace.crop_png_base64)+'"></canvas>':'<p>'+esc(entry.sceneIssue||'This imported layout has no local captured scene.')+'</p>')+'</figure><div><h4>Source tiles & uses</h4><div class="actions">'+[...uses].map(([index,places])=>button('Tile '+index+' · '+places.length+' use'+(places.length===1?'':'s'),'object-source',{id:String(index),primary:entry.selected===index})).join('')+'</div>'+[...uses].filter(([,p])=>p.length>1).map(([i,p])=>'<p class="subtle">Shared tile '+i+' updates '+p.length+' placements together.</p>').join('')+'<p class="subtle">'+(entry.result.source_dependency_verified?'Source origins verified for the captured placements.':'Saved declaration; imported or historical proof is not fresh execution evidence.')+' '+(obj.definition.complete_parts?'':'Some source pixels remain unresolved. ')+'An object name is your label.</p></div></div></section>';
}

export function mountObjectWorkbench(ctx){
 const canvas=document.getElementById('object-scene'),entry=ctx.state.objectWorkbench;if(!canvas||!entry?.trace)return;
 const scope=selectionKey(ctx.state),image=new Image();image.onload=()=>{
  if(!canvas.isConnected||scope!==selectionKey(ctx.state)||ctx.state.objectWorkbench!==entry)return;
  canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const context=canvas.getContext('2d');context.drawImage(image,0,0);
  const region=entry.result.object.definition.scene_region,crop=entry.trace.region,layout=entry.result.object.definition.layout;
  context.strokeStyle='#ffd36a';context.lineWidth=1;
  layout.indices.forEach((index,part)=>{if(index!==null&&(entry.selected===undefined||index===entry.selected))context.strokeRect(region.x-crop.x+(part%layout.columns)*8+.5,region.y-crop.y+Math.floor(part/layout.columns)*8+.5,7,7);});
 };image.src='data:image/png;base64,'+canvas.dataset.scene;
}
