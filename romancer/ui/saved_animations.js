import {readAnimation} from './animation_studio.js';
import {selectionKey} from './tool_inputs.js';
import {esc,button,field,read} from './common.js';
export async function openSavedAnimation(ctx,id){
 const page=ctx.state.page,scope=selectionKey(ctx.state),params={...ctx.sourceParams()},result=await ctx.api.call('animations.get',{...params,animation_id:id});if(scope!==selectionKey(ctx.state)||ctx.state.page!==page)return;
 if(!result.ok||result.source_sha256!==ctx.state.artifact.sha256||result.artifact_id!==ctx.state.artifact.artifact_id)throw Error(result.error||'Animation source changed.');
 const a=result.animation,inspection=await ctx.api.call('assets.inspect',{...params,schema:a.schema});if(scope!==selectionKey(ctx.state)||ctx.state.page!==page)return;
 if(!inspection.ok||inspection.document_id!==a.document_id)throw Error('The saved animation graphics document changed.');
 ctx.state.researchOpen={scope,kind:'assets',definition:a.schema};
 ctx.state.connectedAssetSetup={scope,result:{schema:a.schema,inspection,bitmap_id:a.bitmap_id,layout:a.frames[0]}};
 ctx.state.connectedAnimation={scope,bitmap_id:a.bitmap_id,frames:a.frames,document_id:a.document_id};return ctx.navigate('assets');
}
export async function savedAnimationControls(ctx,doc,bitmap){
 if(!doc?.ok||!bitmap)return '';
 const page=ctx.state.page,scope=selectionKey(ctx.state),params={...ctx.sourceParams()},current=()=>selectionKey(ctx.state)===scope&&ctx.isCurrentRender?.()!==false;
 let list;try{list=await ctx.api.call('animations.list',params);}catch(e){if(!current())return '';return `<section class="card"><p>Saved animations unavailable: ${esc(e.message)}</p></section>`;}if(!current())return '';
 if(!list?.ok||list.source_sha256!==ctx.state.artifact.sha256||list.artifact_id!==ctx.state.artifact.artifact_id)return '';
 const args=()=>({...params,name:read('animation-save-name'),bitmap_id:bitmap.id,document_id:doc.document_id,frames:readAnimation(doc,bitmap,ctx.draft('animation-frames','null'))});
 const review=ctx.state.animationSaveReview?.scope===scope?ctx.state.animationSaveReview:null;
 ctx.use({'animation-preview-save':async()=>{const p=args(),signature=JSON.stringify(p);if(!current())throw Error('The source changed.');const result=await ctx.run('animations.preview',p,{render:false});if(!current())return;if(signature!==JSON.stringify(args()))throw Error('The animation changed. Preview it again.');ctx.state.animationSaveReview={scope,signature,result};return ctx.render();},
 'animation-save-reviewed':async()=>{const p=args();if(!current()||!review||review.signature!==JSON.stringify(p))throw Error('Preview the current animation before saving.');await ctx.run('animations.save',{...p,review_id:review.result.review_id},{render:false});if(current()){ctx.state.animationSaveReview=null;ctx.notify('Animation arrangement saved. Game timing remains unchanged.');return ctx.render();}},
 'animation-load-saved':node=>{if(!current()||!list.animations.some(a=>a.animation_id===node.dataset.id))throw Error('Choose a current saved animation.');return openSavedAnimation(ctx,node.dataset.id);},
 'animation-delete-saved':async node=>{if(!current()||!list.animations.some(a=>a.animation_id===node.dataset.id))throw Error('Choose a current saved animation.');await ctx.run('animations.delete',{...params,animation_id:node.dataset.id},{render:false});if(current())return ctx.render();}});
 return `<details class="card" ${review?'open':''}><summary>Save & reuse animation layouts</summary><p>Save the frames arranged above for this ROM revision. Research packs include saved layouts. Loading replaces the current arrangement draft; tile edits stay separate.</p><div class="actions">${field('animation-save-name','Animation name',ctx.draft('animation-save-name','Sprite animation'))}${button('Preview saved layout','animation-preview-save')}</div>${review?`<p>${review.result.animation.frames.length} frames · ${review.result.shared_tiles.length} shared tiles. Timing is author-declared.</p>${button('Save reviewed animation','animation-save-reviewed',{primary:true})}`:''}${list.animations.map(a=>`<div class="actions"><span>${esc(a.name)} · ${a.frames} frames</span>${button('Load layout','animation-load-saved',{id:a.animation_id})}${button('Delete saved layout','animation-delete-saved',{id:a.animation_id})}</div>`).join('')}</details>`;
}
