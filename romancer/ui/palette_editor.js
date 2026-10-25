import {esc,button,field,select} from './common.js';
import {editedPalette,paletteComparison,quantizeColor,rgbHex,channelMaximum} from './edit_preview.js';
import {selectionKey} from './tool_inputs.js';

export function paletteEditor(ctx,palette){
 if(!palette)return '';
 let after=palette,error='';try{after=editedPalette(palette,JSON.parse(ctx.draft('asset-changes','[]')));}catch(e){error=e.message;}
 let index=Number(ctx.draft('palette-index','1'));if(!Number.isInteger(index)||index<0||index>=palette.entries.length)index=0;
 const entry=after.entries[index];
 return `<section class="card"><h3>Palette colors</h3><div id="palette-comparison">${paletteComparison(palette,after)}</div><div class="palette-picker-row">${select('palette-index','Palette entry',palette.entries.map((e,i)=>[i,'Bank '+e.bank+' · color '+e.index]),index)}<label class="field"><span>Choose color · entry ${index}</span><input id="palette-picker" type="color" value="${rgbHex(entry.rgb)}" aria-label="Choose palette color"></label></div><p id="palette-preview-status" class="${error?'error':'preview-caption'}" role="status" aria-live="polite">${esc(error||'Color picker changes are staged. Review and build to save them.')}</p><details><summary>Color storage values</summary><div class="field-row">${['r','g','b'].map((c,i)=>field('palette-'+c,['Red','Green','Blue'][i]+' (0–'+channelMaximum(palette.channels[c])+')',ctx.draft('palette-'+c,entry.components[c]),{type:'number',min:0})).join('')}</div>${button('Stage storage values','asset-palette-change')}</details></section>`;
}
export function mountPaletteEditor(ctx,doc,palette,redraw){
 const picker=document.getElementById('palette-picker');if(!picker||!palette)return;
 const selector=document.getElementById('palette-index'),selectedIndex=Number(selector?.value);
 const scope=selectionKey(ctx.state),current=()=>scope===selectionKey(ctx.state)&&ctx.state.results['assets.inspect']?.document_id===doc.document_id&&document.getElementById('palette-picker')===picker;
 const stage=()=>{
  if(!current())return;
  try{
   const index=Number(selector?.value),entry=palette.entries[index];if(!Number.isInteger(index)||!entry||index!==selectedIndex)throw Error('Reload the selected palette entry before editing its color.');
   const components=quantizeColor(picker.value,palette.channels),changes=JSON.parse(ctx.draft('asset-changes','[]'));
   editedPalette(palette,changes);
   const next=changes.filter(c=>!(c.kind==='palette'&&c.palette_id===palette.id&&c.index===entry.index&&c.bank===entry.bank));
   if(['r','g','b'].some(c=>components[c]!==entry.components[c]))next.push({kind:'palette',palette_id:palette.id,index:entry.index,bank:entry.bank,before:{...entry.components},after:components});
   const after=editedPalette(palette,next),encoded=JSON.stringify(next,null,2);
   ctx.setDraft('asset-changes',encoded);const raw=document.getElementById('asset-changes');if(raw)raw.value=encoded;
   for(const c of ['r','g','b']){ctx.setDraft('palette-'+c,String(components[c]));const field=document.getElementById('palette-'+c);if(field)field.value=String(components[c]);}
   ctx.state.pending=null;ctx.state.assetAcknowledgements=[];ctx.state.assetEditRevision=(ctx.state.assetEditRevision||0)+1;
   const comparison=document.getElementById('palette-comparison');if(comparison)comparison.innerHTML=paletteComparison(palette,after);
   redraw();const status=document.getElementById('palette-preview-status');if(status)status.textContent='Preview updated · color staged. Review and build to save it.';return true;
  }catch(error){const status=document.getElementById('palette-preview-status');if(status)status.textContent='Preview unavailable: '+error.message;return false;}
 };
 picker.addEventListener('input',stage);picker.addEventListener('change',()=>{if(stage()&&current())ctx.notify('Palette preview updated. Changes are staged.');});
 selector?.addEventListener('change',async()=>{if(!current())return;try{const entry=editedPalette(palette,JSON.parse(ctx.draft('asset-changes','[]'))).entries[Number(selector.value)];if(!entry)return;ctx.setDraft('palette-index',selector.value);for(const c of ['r','g','b'])ctx.setDraft('palette-'+c,String(entry.components[c]));await ctx.render();}catch(error){const status=document.getElementById('palette-preview-status');if(status)status.textContent='Preview unavailable: '+error.message;}});
}
