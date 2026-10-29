import {select,read} from './common.js';
import {editorPalette} from './edit_preview.js';

export function paletteBankCount(palette){
 if(!palette)return 0;
 const count=palette.banks??Math.max(1,...(palette.entries||[]).map(e=>e.bank+1));
 return Number.isSafeInteger(count)&&count>=1&&count<=4096?count:0;
}
export function previewPaletteBank(ctx,palette){
 const bank=Number(ctx.draft('asset-preview-bank','0'));
 return Number.isSafeInteger(bank)&&bank>=0&&bank<paletteBankCount(palette)?bank:0;
}
export function paletteColor(palette,index,bank=0){
 return palette?.entries.find(entry=>entry.bank===bank&&entry.index===index)?.rgb;
}
export function previewPaletteControls(ctx,palette){
 const count=paletteBankCount(palette);if(count<2)return '';
 return `<section class="card"><h3>Preview colors</h3>${select('asset-preview-bank','ROM palette bank',Array.from({length:count},(_,i)=>[String(i),'Bank '+i]),String(previewPaletteBank(ctx,palette)))}<p class="subtle">Choose the bank used by this graphic. This changes the preview; stored pixels and palette colors stay unchanged.</p></section>`;
}
export function applyPreviewPaletteBank(ctx,palette,value=read('asset-preview-bank')){
 const bank=Number(value);if(!Number.isSafeInteger(bank)||bank<0||bank>=paletteBankCount(palette))throw Error('Choose an existing ROM palette bank.');
 const colors=editorPalette(ctx,palette),prior=colors.entries[Number(ctx.draft('palette-index','0'))],index=colors.entries.findIndex(e=>e.bank===bank&&e.index===(prior?.index??0));
 const selected=index>=0?index:colors.entries.findIndex(e=>e.bank===bank);if(selected<0)throw Error('The selected palette bank has no declared colors.');
 ctx.setDraft('asset-preview-bank',String(bank));ctx.setDraft('palette-index',String(selected));
 for(const channel of ['r','g','b'])ctx.setDraft('palette-'+channel,String(colors.entries[selected].components[channel]));
 ctx.notify('Preview palette updated. Stored pixels are unchanged.');return ctx.render();
}
