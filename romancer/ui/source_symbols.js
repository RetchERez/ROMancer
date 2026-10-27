import {esc,button,field,select,read} from './common.js';
import {selectionKey,fileInput} from './tool_inputs.js';
export async function sourceSymbols(ctx){
 const {state}=ctx,a=state.artifact;if(!['gb','gbc','gba'].includes(a?.system_id))return '';
 const scope=selectionKey(state),params={...ctx.sourceParams()},current=()=>scope===selectionKey(state)&&ctx.isCurrentRender?.()!==false;
 const model=await ctx.api.call('symbols.search',{...params,query:ctx.draft('symbol-query',''),page:state.symbolPage||0});if(!current())return '';
 if(model.source_sha256!==a.sha256||model.artifact_id!==a.artifact_id)return '';
 const packet=state.symbolReview?.scope===scope?state.symbolReview:null;
 ctx.use({'symbol-preview':async()=>{if(!current())return;const file=document.getElementById('symbol-file')?.files[0];if(!file)throw Error('Choose a symbol file.');const format=read('symbol-format');state.symbolReview=null;const item=await ctx.api.uploadInput(state.project.project_id,file,'symbols');if(!current())return;const review=await ctx.run('symbols.preview',{...params,input_id:item.input_id,format},{render:false});if(!current())return;state.symbolReview={scope,input_id:item.input_id,format,review};return ctx.render();},
 'symbol-import':async()=>{if(!current()||!packet?.review?.review_id)throw Error('Review this source’s symbols first.');const acknowledged=!!document.getElementById('symbol-ack')?.checked;await ctx.run('symbols.import',{...params,input_id:packet.input_id,format:packet.format,review_id:packet.review.review_id,acknowledged},{render:false});if(!current())return;state.symbolReview=null;state.symbolPage=0;return ctx.render();},
 'symbol-search':()=>{state.symbolPage=0;return ctx.render();},'symbol-page':node=>{state.symbolPage=Math.max(0,(state.symbolPage||0)+Number(node.dataset.id));return ctx.render();},
 'symbol-bytes':node=>{if(!current())return;const offset=Number(node.dataset.id);if(!model.symbols.some(r=>r.file_offset===offset))throw Error('Reload the symbol list.');state.resourceJump=offset;return ctx.navigate('resources');}});
 const rows=packet?.review?.symbols||model.symbols;
 return '<details class="card" id="source-symbols"><summary>Named addresses from a symbol file</summary><p>Import names from your matching game build. ROM labels open their bytes; RAM labels show their CPU address.</p>'+fileInput('symbol-file','Symbol listing','.sym,.txt,.nm')+select('symbol-format','Format',a.system_id==='gba'?[['gnu-nm','GNU nm (address type name)']]:[['rgbds','RGBDS .sym']],a.system_id==='gba'?'gnu-nm':'rgbds')+button('Review symbol file','symbol-preview')+
 (packet?'<p class="notice">'+esc(packet.review.note)+' '+packet.review.total+' entries; '+packet.review.ignored_lines+' ignored lines.</p><label><input id="symbol-ack" type="checkbox"> This symbol file belongs to this exact ROM build.</label>'+button('Import reviewed names','symbol-import'):'')+
 field('symbol-query','Find a symbol',ctx.draft('symbol-query',''))+button('Find name','symbol-search')+
 rows.map(r=>'<div class="notice"><strong>'+esc(r.name)+'</strong> · '+(r.bank===null?'':r.bank.toString(16)+':')+'0x'+r.address.toString(16)+'<p>'+esc(r.reason)+'</p>'+(!packet&&r.file_offset!==null?button('Inspect bytes at 0x'+r.file_offset.toString(16),'symbol-bytes',{id:String(r.file_offset)}):'')+'</div>').join('')+
 (!packet&&model.configured?'<div class="button-row">'+button('Previous','symbol-page',{id:'-1',disabled:!model.page})+'<span>'+model.total+' matches · page '+(model.page+1)+'</span>'+button('Next','symbol-page',{id:'1',disabled:(model.page+1)*50>=model.total})+'</div>':'')+'</details>';
}
