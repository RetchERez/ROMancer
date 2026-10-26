import {esc,button,field,select,read,badge,setUnavailable} from './common.js';
import {selectionKey} from './tool_inputs.js';

export class HexDraft{
 constructor(state,data){this.scope=selectionKey(state);this.original=new Map();this.changes=new Map();this.load(data);this.selected=data.offset;}
 load(data){this.data=data;if(!Number.isSafeInteger(this.selected)||this.selected<data.offset||this.selected>=data.offset+data.length)this.selected=data.offset;const bytes=data.hex.match(/../g)||[];for(const offset of this.original.keys())if(!this.changes.has(offset))this.original.delete(offset);bytes.forEach((b,i)=>this.original.set(data.offset+i,b));}
 set(offset,value){if(offset<this.data.offset||offset>=this.data.offset+this.data.length||!this.original.has(offset))throw Error('Choose a visible byte.');if(!/^[\da-f]{2}$/i.test(value))throw Error('Enter two hex digits per byte.');value=value.toLowerCase();if(value===this.original.get(offset))this.changes.delete(offset);else this.changes.set(offset,value);}
 edits(state){if(this.scope!==selectionKey(state))throw Error('The selection changed. Review bytes for the selected ROM.');return [...this.changes].sort(([a],[b])=>a-b).map(([offset,after])=>({offset,before:this.original.get(offset),after}));}
}
const integer=value=>{const n=Number(value);if(!Number.isSafeInteger(n)||n<0)throw Error('Enter a nonnegative decimal or 0x hex offset.');return n;};
export function serializeHexDraft(state,draft){return JSON.stringify({artifact_id:state.artifact.artifact_id,sha256:state.artifact.sha256,edits:draft.edits(state).map(e=>[e.offset,e.before,e.after])});}
export function restoreHexDraft(state,data,stored){
 const draft=new HexDraft(state,data);if(!stored)return draft;
 const value=JSON.parse(stored);if(value.artifact_id!==state.artifact.artifact_id||value.sha256!==state.artifact.sha256)throw Error('Saved byte edits belong to a different source.');
 if(!Array.isArray(value.edits)||value.edits.length>16000)throw Error('Saved byte draft exceeds the editing budget.');
 const seen=new Set();for(const item of value.edits){if(!Array.isArray(item)||item.length!==3)throw Error('Invalid saved byte edit.');const [offset,before,after]=item;
  if(!Number.isSafeInteger(offset)||offset<0||offset>=state.artifact.size||typeof before!=='string'||typeof after!=='string'||!/^[\da-f]{2}$/i.test(before)||!/^[\da-f]{2}$/i.test(after)||seen.has(offset))throw Error('Invalid saved byte edit.');seen.add(offset);
  if(draft.original.has(offset)&&draft.original.get(offset)!==before.toLowerCase())throw Error('Saved original byte no longer matches this source.');
  if(before.toLowerCase()!==after.toLowerCase()){draft.original.set(offset,before.toLowerCase());draft.changes.set(offset,after.toLowerCase());}
 }return draft;
}
export function hexEditor(ctx,data){
 const {state}=ctx;if(data.artifact_id!==state.artifact?.artifact_id||data.sha256!==state.artifact?.sha256)throw Error('The selected ROM changed. Load bytes for the current selection.');const ticket=selectionKey(state);let draftError='';if(state.hexDraft?.scope!==ticket){try{state.hexDraft=restoreHexDraft(state,data,ctx.draft('hex-changes',null));}catch(error){draftError=error.message;state.hexDraft=null;}}else state.hexDraft.load(data);
 if(draftError){ctx.use({'hex-discard-invalid':()=>{ctx.setDraft('hex-changes',null);state.hexDraft=null;return ctx.render();}});return `<section class="card"><h3>Saved byte edits need attention</h3><p class="notice warm">${esc(draftError)}</p><p>Your ROM is unchanged. Discard this saved draft to reopen the editor.</p>${button('Discard invalid byte draft','hex-discard-invalid')}</section>`;}
 if(Number.isSafeInteger(state.resumeHexSelection)&&state.resumeHexSelection>=data.offset&&state.resumeHexSelection<data.offset+data.length){state.hexDraft.selected=state.resumeHexSelection;delete state.resumeHexSelection;}
 const draft=state.hexDraft,current=()=>selectionKey(state)===ticket;
 const scoped=async(op,p)=>{const result=await ctx.run(op,{...ctx.sourceParams(),...p},{render:false});if(!current())throw Error('The selected ROM changed. Repeat this action.');return result;};
 const go=async offset=>{const result=await scoped('resource.inspect',{offset:Math.min(integer(offset),Math.max(0,state.artifact.size-1)),length:256});state.results['resource.inspect']=result;draft.selected=result.offset;ctx.setDraft('hex-offset',String(result.offset));await ctx.render();};
 ctx.use({
  'hex-go':()=>go(read('hex-offset')),'hex-page':node=>go(Math.max(0,data.offset+Number(node.dataset.id))),
  'hex-jump':node=>go(node.dataset.id),'hex-clear':()=>{state.hexDraft=new HexDraft(state,data);ctx.setDraft('hex-changes',serializeHexDraft(state,state.hexDraft));state.hexReview=null;return ctx.render();},
  'hex-search':async()=>{state.hexSearch={scope:ticket,result:await scoped('hex.search',{kind:read('hex-search-kind'),query:read('hex-search-query'),start:integer(read('hex-search-start')),endian:read('hex-endian'),width:Number(read('hex-width')),signed:read('hex-signed')==='true'})};await ctx.render();},
  'hex-search-more':async()=>{const next=state.hexSearch?.result?.next_start;if(next===null||next===undefined)return;ctx.setDraft('hex-search-start',String(next));await ctx.render();},
  'hex-explain':async()=>{state.hexExplanation={scope:ticket,result:await scoped('resources.explain',{offset:draft.selected})};return ctx.render();},
  'hex-numbers':async()=>{state.hexNumbers={scope:ticket,result:await scoped('hex.numbers',{offset:draft.selected})};await ctx.render();},
  'hex-bookmarks':async()=>{state.hexBookmarks={scope:ticket,result:await scoped('hex.bookmarks',{})};await ctx.render();},
  'hex-bookmark':async()=>{state.hexBookmarks={scope:ticket,result:await scoped('hex.bookmark',{offset:draft.selected,name:read('hex-bookmark-name'),remove:false})};await ctx.render();},
  'hex-unbookmark':async node=>{state.hexBookmarks={scope:ticket,result:await scoped('hex.bookmark',{offset:Number(node.dataset.id),name:'',remove:true})};await ctx.render();},
  'hex-review':async()=>{if(document.querySelector('#hex-editor input:invalid'))throw Error('Finish the byte with two hex digits first.');const edits=draft.edits(state);if(!edits.length)throw Error('Change one or more byte cells first.');const signature=JSON.stringify(edits),source=state.artifact;
   const plan=await scoped(source.system_id?'systems.plan_edits':'bytes.plan',{edits});
   if(JSON.stringify(draft.edits(state))!==signature)throw Error('Bytes changed during review. Review them again.');state.hexReview={scope:ticket,signature,plan};await ctx.render();},
  'hex-apply':async()=>{const reviewed=state.hexReview;if(reviewed?.scope!==ticket||reviewed.signature!==JSON.stringify(draft.edits(state)))throw Error('Review the current byte edits first.');
   const built=await ctx.run('build.apply',{...ctx.projectParams(),plan_id:reviewed.plan.plan_id},{render:false});if(!current())return;if(state.hexReview!==reviewed||JSON.stringify(draft.edits(state))!==reviewed.signature){ctx.notify('Build created. Your newer byte edits are still staged.');return;}state.hexReview=null;ctx.setDraft('hex-changes',JSON.stringify({artifact_id:state.artifact.artifact_id,sha256:state.artifact.sha256,edits:[]}));state.hexDraft=null;await ctx.refreshProject();await ctx.setArtifact(built.artifact_id);ctx.notify('Separate build created.');await ctx.navigate('overview');}
 });
 const bytes=data.hex.match(/../g)||[],search=state.hexSearch?.scope===ticket?state.hexSearch.result:null,numbers=state.hexNumbers?.scope===ticket&&state.hexNumbers.result.offset===draft.selected?state.hexNumbers.result:null,marks=state.hexBookmarks?.scope===ticket?state.hexBookmarks.result:null;
 const reviewed=state.hexReview?.scope===ticket&&state.hexReview.signature===JSON.stringify(draft.edits(state));
 return `<section class="card" id="hex-editor"><div class="card-heading"><h3>Hex editor</h3>${badge(`${draft.changes.size} staged bytes`)}</div>
 <div class="toolbar">${field('hex-offset','Offset',ctx.draft('hex-offset',data.offset))}${button('Go','hex-go')}${button('Previous page','hex-page',{id:'-256',disabled:data.offset===0})}${button('Next page','hex-page',{id:'256',disabled:data.offset+data.length>=state.artifact.size})}</div>
 <div class="hex-scroll"><div class="hex-edit-grid" aria-label="Editable hex bytes">${Array.from({length:Math.ceil(bytes.length/16)},(_,row)=>`<div class="hex-edit-row"><code>${(data.offset+row*16).toString(16).padStart(8,'0')}</code><div class="hex-edit-cells">${bytes.slice(row*16,row*16+16).map((b,i)=>{const offset=data.offset+row*16+i;return `<input aria-label="Byte 0x${offset.toString(16)}" data-hex-offset="${offset}" value="${draft.changes.get(offset)||b}" maxlength="2" size="2" spellcheck="false" class="hex-cell ${draft.changes.has(offset)?'changed':''}">`;}).join('')}</div><code>${esc(data.text?.slice(row*16,row*16+16)||'')}</code></div>`).join('')}</div></div>
 <p class="subtle">Edit a byte, then review. Your source stays unchanged. Arrow keys move between bytes.</p><div class="actions">${button('Review byte edits','hex-review',{primary:true,disabled:!draft.changes.size})}${button('Create separate build','hex-apply',{disabled:!reviewed})}${button('Discard byte edits','hex-clear',{disabled:!draft.changes.size})}</div>
 ${reviewed?`<div class="notice">${state.hexReview.plan.changed_bytes} bytes in the reviewed plan, including supported checksum repairs.</div>`:''}
 <details><summary>Search bytes, text or numbers</summary><div class="field-row">${select('hex-search-kind','Search for',[['hex','Hex pattern (?? wildcard)'],['text','UTF-8 text'],['number','Integer']],ctx.draft('hex-search-kind','hex'))}${field('hex-search-query','Pattern or value',ctx.draft('hex-search-query',''))}${field('hex-search-start','Start offset',ctx.draft('hex-search-start','0'))}</div><div class="field-row">${select('hex-endian','Byte order',[['little','Little endian'],['big','Big endian']],ctx.draft('hex-endian','little'))}${select('hex-width','Number width',[[1,'8-bit'],[2,'16-bit'],[4,'32-bit']],ctx.draft('hex-width','2'))}${select('hex-signed','Number sign',[['false','Unsigned'],['true','Signed']],ctx.draft('hex-signed','false'))}</div>${button('Search selected file','hex-search')}
 ${search?`<p>${search.offsets.length} matches · ${search.complete?'Reached end of file':`Scanned through 0x${search.scanned_to.toString(16)}`}</p><div class="actions">${search.offsets.slice(0,1000).map(o=>button('0x'+o.toString(16),'hex-jump',{id:String(o)})).join('')}</div>${search.complete?'':button('Set next search position','hex-search-more')}`:''}</details>
 <details><summary>Number inspector & bookmarks</summary><p>Selected offset: <code id="hex-selected">0x${draft.selected.toString(16)}</code></p>${button('Explain selected bytes','hex-explain')}${button('Inspect selected number','hex-numbers')}<div id="hex-explanation">${state.hexExplanation?.scope===ticket&&state.hexExplanation.result.offset===draft.selected?`<p>${esc(state.hexExplanation.result.note)}</p>${state.hexExplanation.result.interpretations.map(row=>`<dl><dt>${esc(row.name)} · declared</dt><dd>File offset 0x${row.offset.toString(16)} · ${row.length} bytes${row.type?' · '+esc(row.type)+' '+esc(row.endian)+' · value '+esc(row.value)+' · numeric range '+row.minimum+'–'+row.maximum:''}${row.description?'<br>'+esc(row.description):''}</dd></dl>`).join('')}`:''}</div><div id="hex-number-result">${numbers?`<dl>${Object.entries(numbers.values).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`:''}</div>${field('hex-bookmark-name','Bookmark name',ctx.draft('hex-bookmark-name',''))}<div class="actions">${button('Bookmark selected byte','hex-bookmark')}${button('Load bookmarks','hex-bookmarks')}</div>${(marks?.bookmarks||[]).map(r=>`<div class="actions">${button(`${r.name} · 0x${r.offset.toString(16)}`,'hex-jump',{id:String(r.offset)})}${button('Remove','hex-unbookmark',{id:String(r.offset)})}</div>`).join('')}</details></section>`;
}
export async function hexComparison(ctx,data){
 const saved=ctx.state.hexComparison,a=ctx.state.artifact,p=ctx.state.project,scope=selectionKey(ctx.state);
 if(!saved||saved.project_id!==p.project_id||saved.right_id!==a.artifact_id||saved.right_sha256!==a.sha256)return '';
 const left=p.sources.concat(p.builds).find(r=>r.artifact_id===saved.left_id);if(!left||left.sha256!==saved.left_sha256)return '';
 const maximum=Math.max(left.size,a.size),offset=saved.offset??data.offset;
 if(!Number.isSafeInteger(offset)||offset<0||offset>maximum)return '';
 const length=Math.max(1,Math.min(256,maximum-offset));
 const readSide=row=>ctx.api.call('resource.inspect',{project_id:p.project_id,artifact_id:row.artifact_id,offset:Math.min(offset,row.size),length});
 const [original,selected]=await Promise.all([readSide(left),readSide(a)]);
 if(selectionKey(ctx.state)!==scope||ctx.state.hexComparison!==saved)return '';
 if(original.artifact_id!==left.artifact_id||original.sha256!==left.sha256||selected.artifact_id!==a.artifact_id||selected.sha256!==a.sha256)throw Error('The compared source changed. Compare these files again.');
 ctx.use({'hex-diff-page':async node=>{
  if(selectionKey(ctx.state)!==scope||ctx.state.hexComparison!==saved)throw Error('The selected comparison changed. Compare these files again.');
  const delta=Number(node.dataset.id);if(![-256,256].includes(delta))throw Error('Invalid comparison page.');
  saved.offset=Math.max(0,Math.min(Math.max(0,maximum-1),offset+delta));await ctx.render();
 },'hex-diff-follow':async()=>{if(selectionKey(ctx.state)!==scope||ctx.state.hexComparison!==saved)throw Error('The selected comparison changed.');delete saved.offset;await ctx.render();}});
 const x=original.hex.match(/../g)||[],y=selected.hex.match(/../g)||[],span=Math.max(x.length,y.length);
 const cells=(values,other,index)=>Array.from({length:Math.min(16,span-index)},(_,j)=>{const value=values[index+j];return value===undefined?'<span aria-label="No byte in file">—</span>':value!==other[index+j]?`<mark>${value}</mark>`:value;}).join(' ');
 return `<details class="card hex-comparison" open><summary>Compare at 0x${offset.toString(16)}</summary><p>${esc(left.name)} → ${esc(a.name)}</p><p>Changed bytes are highlighted. — means this file has no byte at that offset.</p><div class="actions">${button('Previous comparison page','hex-diff-page',{id:'-256',disabled:offset===0})}${button('Next comparison page','hex-diff-page',{id:'256',disabled:offset+span>=maximum})}${button('Follow hex editor','hex-diff-follow')}</div><div class="hex-scroll"><table><thead><tr><th>Offset</th><th>Earlier bytes</th><th>Selected bytes</th></tr></thead><tbody>${Array.from({length:Math.ceil(span/16)},(_,i)=>`<tr><td><code>${(offset+i*16).toString(16)}</code></td><td><code>${cells(x,y,i*16)}</code></td><td><code>${cells(y,x,i*16)}</code></td></tr>`).join('')}</tbody></table></div></details>`;
}
export function mountHexEditor(ctx){
 const root=document.getElementById('hex-editor');if(!root)return;const draft=ctx.state.hexDraft;
 root.querySelectorAll('[data-hex-offset]').forEach(node=>{
  node.addEventListener('focus',()=>{if(draft.scope!==selectionKey(ctx.state))return;draft.selected=Number(node.dataset.hexOffset);if(ctx.state.hexExplanation?.result.offset!==draft.selected){ctx.state.hexExplanation=null;root.querySelector('#hex-explanation')?.replaceChildren?.();}if(ctx.state.hexNumbers?.result.offset!==draft.selected){ctx.state.hexNumbers=null;root.querySelector('#hex-number-result')?.replaceChildren?.();}const label=root.querySelector('#hex-selected');if(label)label.textContent='0x'+draft.selected.toString(16);node.select();});
  node.addEventListener('input',()=>{ctx.state.hexReview=null;setUnavailable(root.querySelector('[data-action="hex-apply"]'),true);
   try{draft.set(Number(node.dataset.hexOffset),node.value);ctx.setDraft('hex-changes',serializeHexDraft(ctx.state,draft));node.setCustomValidity('');node.classList.toggle('changed',draft.changes.has(Number(node.dataset.hexOffset)));setUnavailable(root.querySelector('[data-action="hex-review"]'),!draft.changes.size);setUnavailable(root.querySelector('[data-action="hex-clear"]'),!draft.changes.size);}catch(error){node.setCustomValidity(error.message);}});
  node.addEventListener('blur',()=>{if(!node.checkValidity()){node.reportValidity();node.value=draft.changes.get(Number(node.dataset.hexOffset))||draft.original.get(Number(node.dataset.hexOffset));node.setCustomValidity('');}});
  node.addEventListener('keydown',event=>{const delta={ArrowLeft:-1,ArrowRight:1,ArrowUp:-16,ArrowDown:16}[event.key];if(delta){const next=root.querySelector(`[data-hex-offset="${Number(node.dataset.hexOffset)+delta}"]`);if(next){event.preventDefault();next.focus();}}});
 });
}
