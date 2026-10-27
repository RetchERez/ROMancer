import {summaryText} from './change_summary.js';
import {icon} from './icons.js';
import {fieldExplanation} from './tool_help.js';
export const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const size=n=>n>=1048576?(n/1048576).toFixed(1)+' MiB':n>=1024?(n/1024).toFixed(1)+' KiB':n+' B';
export const short=value=>String(value||'—').slice(0,12);
export const badge=(text,tone='neutral')=>`<span class="badge ${tone}">${esc(text)}</span>`;
let unavailableSequence=0;
export function unavailableReason(action){
 const reasons={'asset-paste':'Copy a tile first.','asset-font-change':'This glyph has a fixed advance; it has no editable width byte.',
 'configure-layout':'Declare a font for this source first.','configure-menu':'Declare a font for this source first.',
 'hex-review':'Change at least one byte first.','hex-clear':'There are no staged byte edits.',
 'runtime-play':'Load the selected game first.','runtime-save':'Load the selected game first.',
 'runtime-restore':'Load the matching game and choose a saved state.','runtime-close':'No game is loaded.',
 'sound-capture':'Load this exact source in Playtest first.','script-plan':'Load an editable text definition first.',
 'compression-review':'Create a build of the decoded resource first.'};
 if(reasons[action])return reasons[action];
 if(/page|previous|next/.test(action))return 'No more items in this direction.';
 if(/(?:apply|build)$/.test(action))return 'Review the changes first.';
 if(/package|export/.test(action))return 'Prepare and select an export first.';
 if(/state|checkpoint/.test(action))return 'Load the matching ROM and core first.';
 if(/runtime|profile/.test(action))return 'Choose compatible content and a saved core setup.';
 if(/undo|redo/.test(action))return 'No edit history in this direction.';
 if(/stop/.test(action))return 'Start recording first.';
 return 'Complete the required setup for this selection.';
}
export function setUnavailable(node,disabled,reason){
 node.disabled=!!disabled;let wrapper=node.closest('.unavailable-control');
 if(!wrapper&&disabled){wrapper=document.createElement('span');wrapper.className='unavailable-control';node.before(wrapper);wrapper.append(node);const caption=document.createElement('span');caption.className='unavailable-reason';caption.id='unavailable-'+(++unavailableSequence);wrapper.append(caption);}
 if(!wrapper)return;const caption=wrapper.querySelector('.unavailable-reason');caption.hidden=!disabled;wrapper.tabIndex=disabled?0:-1;
 if(disabled){const text=reason||unavailableReason(node.dataset.action);caption.textContent=text;wrapper.setAttribute('role','group');wrapper.setAttribute('aria-label',node.textContent+': '+text);node.setAttribute('aria-describedby',caption.id);}
 else{wrapper.removeAttribute('role');wrapper.removeAttribute('aria-label');node.removeAttribute('aria-describedby');}
}
export function button(label,action,options={}){
 const reason=options.disabled?options.reason||unavailableReason(action):'',id=reason?'unavailable-'+(++unavailableSequence):'';
 const html=`<button type="button" data-action="${esc(action)}" ${options.id?`data-id="${esc(options.id)}"`:''} ${options.name?`data-name="${esc(options.name)}"`:''} class="${options.primary?'primary ':''}${esc(options.class||'')}" ${options.disabled?`disabled aria-describedby="${id}"`:''}>${options.icon?icon(options.icon):''}${esc(label)}</button>`;
 return reason?`<span class="unavailable-control" role="group" tabindex="0" aria-label="${esc(label+': '+reason)}">${html}<span class="unavailable-reason" id="${id}">${esc(reason)}</span></span>`:html;
}
function fieldTitle(id,label){const explanation=fieldExplanation(label);return `<span class="field-title"><span>${esc(label)}</span>${explanation?`<span class="field-help" tabindex="0" aria-label="About ${esc(label)}" aria-describedby="field-help-${esc(id)}">?<span id="field-help-${esc(id)}" role="tooltip" class="field-help-tip">${esc(explanation)}</span></span>`:''}</span>`;}
export const field=(id,label,value='',options={})=>`<label class="field">${fieldTitle(id,label)}<input id="${id}" ${options.type?`type="${options.type}"`:''} value="${esc(value)}" placeholder="${esc(options.placeholder||'')}" ${options.readonly?'readonly':''} ${options.min!==undefined?`min="${options.min}"`:''}>${options.hint?`<small>${esc(options.hint)}</small>`:''}</label>`;
export const area=(id,label,value='',rows=5)=>`<label class="field"><span>${esc(label)}</span><textarea id="${id}" rows="${rows}" spellcheck="false">${esc(value)}</textarea></label>`;
export const select=(id,label,options,value)=>`<label class="field">${fieldTitle(id,label)}<select id="${id}">${options.map(([key,text])=>`<option value="${esc(key)}" ${String(key)===String(value)?'selected':''}>${esc(text)}</option>`).join('')}</select></label>`;
export const jsonEditor=(id,label,value,open=false)=>`<details class="config" ${open?'open':''}><summary>${esc(label)} <span>JSON descriptor</span></summary>${area(id,label,typeof value==='string'?value:JSON.stringify(value,null,2),8)}</details>`;
export const read=id=>{const node=document.getElementById(id);if(!node)throw new Error('This control is no longer visible. Reopen its screen.');return node.value;};
export const json=id=>{try{return JSON.parse(read(id));}catch{throw new Error('Check the JSON in “'+(document.getElementById(id)?.closest('label')?.querySelector('.field-title > span,span')?.textContent||id)+'”.');}};
export function report(result,title='Result'){if(!result)return '';const summary=summaryText(result),tone=result.ok===false||['FAIL','BLOCKED','REGRESSION'].includes(result.status)?'danger':['PASS','BUILT','VERIFIED','SCOPE_COVERED'].includes(result.status)?'good':'neutral';return `<section class="card result"><div class="card-heading"><h3>${esc(title)}</h3>${badge(result.status||'READY',tone)}</div>${summary?`<p class="notice change-summary" role="status">${esc(summary)}</p>`:''}${result.error?`<p class="error">${esc(typeof result.error==='string'?result.error:result.error.message)}</p>`:''}<details><summary>Inspect the full report</summary><pre tabindex="0" role="region" aria-label="${esc(title)} details">${esc(JSON.stringify(result,null,2))}</pre></details></section>`;}
export const empty=(title,message,action='')=>`<div class="empty">${icon('folder')}<h3>${esc(title)}</h3><p>${esc(message)}</p>${action}</div>`;
export function heading(kicker,title,description,actions=''){return `<header class="page-heading"><div><h1>${esc(title)}</h1></div><div class="actions">${actions}${title==='Help'?'':button('Help','help-topic',{icon:'shield'})}</div></header>`;}
export function requireProject(ctx){if(!ctx.state.project)return empty('Open a project to begin','Import your own source or explore the original demonstration fixture.',button('Open demonstration','demo',{primary:true,icon:'arrow'}));return null;}
