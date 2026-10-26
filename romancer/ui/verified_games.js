import {selectionKey} from './tool_inputs.js';
import {esc,button,badge,select,read} from './common.js';
import {gameVisual} from './game_visuals.js';

export async function gameEdits(ctx){
 const {state}=ctx;if(!state.artifact)return '';
 const scope=selectionKey(state),params={...ctx.sourceParams()},current=()=>scope===selectionKey(state)&&(!ctx.isCurrentRender||ctx.isCurrentRender());
 ctx.use({'game-view-bytes':async node=>{if(!current())throw Error('The selected file changed.');state.resourceJump=Number(node.dataset.id);await ctx.navigate('resources');},'game-investigate':()=>ctx.navigate('resources')});
 let model;
 try{model=await ctx.api.call('games.inspect',params);}catch(error){if(!current())return '';return `<section class="card"><h3>Game edits unavailable</h3><p>${esc(error.message)}</p>${button('Inspect bytes','game-investigate')}</section>`;}
 if(!current())return '';
 state.gameVisualModel={scope,model};
 if(!model.profile)return `<section class="card game-definition"><div class="card-heading"><h3>Investigate this ROM</h3>${button('Open hex editor','game-investigate')}</div><p class="subtle">No verified game definition for this revision. Search bytes, compare builds, and bookmark locations in Resources.</p></section>`;
 const pending=state.gameEditPlan?.scope===scope&&state.gameEditPlan.result.profile_id===model.profile.id?state.gameEditPlan:null;
 function values(){return Object.fromEntries(model.fields.map(f=>{const value=read('game-'+f.id);if(f.type==='integer'){if(!/^\d+$/.test(value)||Number(value)<f.min||Number(value)>f.max)throw Error(`${f.label}: enter ${f.min} to ${f.max}.`);return [f.id,Number(value)];}return [f.id,value];}));}
 function sameValues(chosen){try{return JSON.stringify(values())===JSON.stringify(chosen);}catch{return false;}}
 ctx.use({
  'game-resource':async node=>{if(!current())throw Error('The selected file changed.');const result=await ctx.run('games.configure',{...params,resource_id:node.dataset.id},{refresh:false,render:false});if(!current())return;await ctx.refreshProject();state.results['tables.inspect']=result.inspection;await ctx.navigate('tables');},
  'game-review':async()=>{if(!current())throw Error('The selected file changed.');const chosen=values(),previous=state.gameEditPlan;const result=await ctx.run('games.plan',{...params,profile_id:model.profile.id,values:chosen},{refresh:false,render:false});if(!current())return;if(state.gameEditPlan!==previous||!sameValues(chosen)){ctx.notify('Values changed during review. Review them again.');return;}state.gameEditPlan={scope,values:chosen,result};await ctx.render();},
  'game-cancel':()=>{state.gameEditPlan=null;return ctx.render();},
  'game-apply':async()=>{
   const planned=state.gameEditPlan;
   if(!current()||planned?.scope!==scope)throw Error('Review changes for the selected ROM first.');
   if(!sameValues(planned.values))throw Error('Values changed. Review the changes again.');
   const unchanged=()=>state.gameEditPlan===planned&&sameValues(planned.values);
   let artifactId=planned.result.existing_build_id;
   if(artifactId)await ctx.api.call('games.inspect',{...params,artifact_id:artifactId});
   else{
    const result=await ctx.run('build.apply',{project_id:params.project_id,plan_id:planned.result.plan_id},{refresh:false,render:false});
    artifactId=result.artifact_id;
    await ctx.api.call('builds.annotate',{project_id:params.project_id,artifact_id:artifactId,name:planned.result.build_name,notes:`${model.profile.name}: ${planned.result.preview.map(p=>p.label+' '+p.before+' to '+p.after).join('; ')}. Definition ${model.profile.id}. ${model.profile.reference}`});
   }
   if(!current())return;
   await ctx.refreshProject();
   if(!current())return;
   if(!unchanged()){
    ctx.notify('Build available in history. Your newer game edits are still staged.');
    await ctx.render();return;
   }
   state.gameEditPlan=null;
   await ctx.setArtifact(artifactId);
   ctx.notify(planned.result.existing_build_id?'Opened the matching build from history.':'Build created. Playtest it before exporting a patch.');
  }
 });
 const visualValues=Object.fromEntries(model.fields.map(f=>[f.id,ctx.draft('game-'+f.id,String(f.value))]));
 const inputs=model.fields.map(f=>{const value=ctx.draft('game-'+f.id,String(f.value));if(f.type==='choice')return select('game-'+f.id,f.label,[['',f.id==='room_layout'?'Choose position':'Choose colors'],...f.options],value);return `<label class="field"><span>${esc(f.label)}</span><input id="game-${esc(f.id)}" type="${f.type==='integer'?'number':'text'}" value="${esc(value)}" ${f.type==='integer'?`min="${f.min}" max="${f.max}"`:`maxlength="${f.max_length}"`}><small>${f.type==='integer'?`${f.min}–${f.max}`:'Up to 9 letters, digits, spaces or ?'}</small></label>`;}).join('');
 const plan=pending?.result;
 const review=plan?`<div class="game-review" id="game-edit-review"><h3>Review changes</h3>${plan.preview.map(p=>`<p><strong>${esc(p.label)}</strong> ${esc(p.before)} <span aria-label="changes to">→</span> ${esc(p.after)}</p>`).join('')}${plan.additional_changes.map(note=>`<p class="notice warm">${esc(note)}</p>`).join('')}<details><summary>Byte changes${plan.integrity_edit_count?' and console checksum':''}</summary><table><thead><tr><th>Offset</th><th>Before</th><th>After</th></tr></thead><tbody>${plan.edits.map(e=>`<tr><td><code>0x${e.offset.toString(16).toUpperCase()}</code></td><td><code>${hexPreview(e.before)}</code></td><td><code>${hexPreview(e.after)}</code></td></tr>`).join('')}</tbody></table></details><div class="actions">${button(plan.existing_build_id?'Open existing build':'Create build','game-apply',{primary:true,icon:'check'})}${button('Cancel review','game-cancel')}</div></div>`:'';
 return `<section class="card game-definition"><div class="card-heading"><h3>Game edits</h3>${badge(model.status==='MATCHED'?'Revision matched':'Based on matched source',model.status==='MATCHED'?'good':'warm')}</div><div class="game-definition-grid"><div>${inputs}<div id="game-visual-preview">${gameVisual(model,visualValues)}</div><div class="actions">${button('Review changes','game-review',{primary:!pending})}</div>${review}</div><div><h3>Known locations</h3>${(model.resources||[]).map(r=>`<div class="notice">${button('Open '+r.name,'game-resource',{id:r.id})}<p>${esc(r.scope)}</p></div>`).join('')}<div class="game-locations">${model.locations.map(l=>`<div><span>${esc(l.label)}<small class="subtle">${esc(l.storage||'')}</small></span>${button('View 0x'+l.offset.toString(16).toUpperCase(),'game-view-bytes',{id:String(l.offset)})}</div>`).join('')}</div><details><summary>Definition and tested scope</summary><p>${esc(model.profile.scope)}</p><p>${model.status==='DERIVED'?'This build has a matched original in its history. Its gameplay has not been certified.':'The selected original matches the tested SHA-256 revision.'}</p><a href="${esc(model.profile.reference)}" target="_blank" rel="noreferrer">Source reference</a></details></div></div></section>`;
}

function hexPreview(value){return esc(value.length>32?value.slice(0,32).toUpperCase()+'… ('+(value.length/2)+' bytes)':value.toUpperCase());}

export async function gameByteNotes(ctx,data){
 const scope=selectionKey(ctx.state),params={...ctx.sourceParams()};
 let model;try{model=await ctx.api.call('games.inspect',params);}catch{return '';}
 if(scope!==selectionKey(ctx.state)||ctx.isCurrentRender&&!ctx.isCurrentRender())return '';
 const locations=model.profile?(model.locations||[]).filter(l=>l.offset<data.offset+data.length&&l.offset+l.length>data.offset):[];
 return `<section class="card byte-reference"><div class="card-heading"><h3>Byte reference</h3>${locations.length?badge(model.status==='MATCHED'?'Known location':'Matched source history',model.status==='MATCHED'?'good':'warm'):''}</div>${locations.length?locations.map(l=>`<h4>${esc(l.label)} · <code>0x${l.offset.toString(16).toUpperCase()}</code></h4><p><strong>${esc(l.storage)}</strong> · ${l.length} ${l.length===1?'byte':'bytes'}</p><p>${esc(l.meaning)}</p><p><code>${esc(l.example)}</code></p><details><summary>What was verified</summary><p>${esc(l.evidence)}</p><p>Tested on the exact original revision; this selected build still needs its own playtest.</p><a href="${esc(model.profile.reference)}" target="_blank" rel="noreferrer">Source reference</a></details>`).join(''):'<p class="subtle">No verified game meaning recorded for this byte range. Search matches are candidates until tested.</p>'}<details><summary>How to read these bytes</summary><p><code>0x</code> means hexadecimal. One byte ranges from <code>00</code> to <code>FF</code> (0–255); <code>1E</code> is 30.</p><p>Two-byte number 4660 is <code>34 12</code> in little endian or <code>12 34</code> in big endian. Signed 8-bit <code>FF</code> is −1; unsigned it is 255.</p><p>These are file offsets, including any header. CPU addresses and banked memory need an explicit mapping. On-screen values may be calculated or stored in RAM; game text may use a custom encoding.</p></details></section>`;
}
