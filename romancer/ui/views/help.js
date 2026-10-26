import {esc,button,field,heading,read} from '../common.js';
export async function render(ctx){
 const {state}=ctx;
 const result=await ctx.api.call('help.list',{query:state.helpQuery||'',topic:state.helpTopic||'start'});
 ctx.use({'help-search':()=>{state.helpQuery=read('help-query').slice(0,160);state.helpTopic='';return ctx.render();},
  'help-open':node=>{state.helpTopic=node.dataset.id;return ctx.render();}});
 const selected=result.selected||result.topics[0];
 return `${heading('','Help','', '<a class="guide-link" href="/user-guide/index.html" target="_blank" rel="noopener noreferrer">User guide</a>'+button('Tutorials','tutorial-hub',{primary:true})+button('Keyboard shortcuts','shortcut-help'))}<div class="help-layout"><section class="card help-index">${field('help-query','Search offline help',state.helpQuery||'')}${button('Search help','help-search',{primary:true})}<nav aria-label="Help topics">${result.topics.map(row=>button(row.title,'help-open',{id:row.id,class:row.id===selected?.id?'selected-help':''})).join('')||'<p>No matching topics. Try a shorter search.</p>'}</nav></section><article class="card help-article">${selected?`<h2>${esc(selected.title)}</h2><p>${esc(selected.summary)}</p><ol>${selected.steps.map(step=>`<li>${esc(step)}</li>`).join('')}</ol><div class="actions">${button('Open resources','navigate',{id:'resources'})}${button('Playtest','navigate',{id:'playtest'})}${button('Project settings','navigate',{id:'settings'})}</div>`:'<h2>Choose a topic</h2><p>Help is included with ROMancer and works offline.</p>'}</article></div>`;
}
