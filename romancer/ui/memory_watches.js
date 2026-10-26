import {esc,button,field,select,read} from './common.js';
import {selectionKey} from './tool_inputs.js';
export function memoryWatches(ctx){const {state}=ctx,source=state.artifact;if(!source)return '';const watches=source.descriptors?.watches?.source_sha256===source.sha256?source.descriptors.watches.watches:[];
 const scope=selectionKey(state),runtime=state.runtime,params={...ctx.projectParams()},signature=JSON.stringify(watches);
 if(state.watchScope!==scope||state.watchRuntime!==runtime){state.watchScope=scope;state.watchRuntime=runtime;state.watchReadings=null;state.watchBaseline=null;state.watchChanges=null;state.watchGeneration=(state.watchGeneration||0)+1;}
 const current=()=>{const saved=state.artifact?.descriptors?.watches;return selectionKey(state)===scope&&state.runtime===runtime&&JSON.stringify(saved?.source_sha256===state.artifact?.sha256?saved.watches:[])===signature;};
 const save=next=>{if(!current())throw Error('The selected source changed. Add watches again.');state.watchGeneration++;state.watchBaseline=null;state.watchReadings=null;state.watchChanges=null;return ctx.run('watches.save',{...ctx.sourceParams(),watches:next});};
 ctx.use({
 'watch-add':()=>save([...watches,{name:read('watch-name'),region:Number(read('watch-region')),offset:Number(read('watch-offset')),length:Number(read('watch-length'))}]),
 'watch-remove':node=>save(watches.filter((_,i)=>i!==Number(node.dataset.id))),
 'watch-read':async()=>{
  if(!current()||!runtime)throw Error('Load this source in Playtest before reading watches.');
  const generation=++state.watchGeneration,baseline=state.watchBaseline,valid=()=>current()&&state.watchGeneration===generation&&state.watchBaseline===baseline,readings={},changes={};let context=null;
  for(const watch of watches){
   const result=await ctx.api.call('runtime.memory',{...params,region:watch.region,offset:watch.offset,length:watch.length});if(!valid())return;
   if(result.game_sha256!==source.sha256)throw new Error('The loaded game differs from the selected source. Load this source in Playtest.');
   const binding=JSON.stringify([result.worker_session_id,result.epoch,result.game_sha256,result.core_sha256,Object.entries(result.core_options||{}).sort()]);
   if(context!==null&&context!==binding)throw Error('The runtime context changed while reading watches. Read them again.');context=binding;
   readings[watch.name]=result;
  }
  if(baseline)for(const watch of watches){const before=baseline[watch.name];if(before){const compared=await ctx.api.call('watches.compare',{before,after:readings[watch.name]});if(!valid())return;changes[watch.name]=compared;}}
  if(!valid())return;state.watchReadings=readings;state.watchChanges=changes;return ctx.render();
 },
 'watch-baseline':()=>{if(!current()||!state.watchReadings)throw new Error('Read current watches first.');state.watchGeneration++;state.watchBaseline=structuredClone(state.watchReadings);state.watchChanges=null;return ctx.render();}
 });
 return `<section class="card"><h3>Memory watches</h3><div class="field-row">${field('watch-name','Name',ctx.draft('watch-name','Watch '+(watches.length+1)))}${select('watch-region','Memory region',[[2,'System RAM'],[3,'Video RAM'],[0,'Save RAM']],ctx.draft('watch-region','2'))}${field('watch-offset','Region offset',ctx.draft('watch-offset','0'))}${field('watch-length','Bytes (1–256)',ctx.draft('watch-length','1'))}</div>${button('Add watch','watch-add',{disabled:watches.length>=32})}<div class="table-wrap"><table><thead><tr><th>Name</th><th>Range</th><th>Current bytes</th><th>Changes</th><th></th></tr></thead><tbody>${watches.map((watch,i)=>`<tr><td>${esc(watch.name)}</td><td>${watch.region}:0x${watch.offset.toString(16)} · ${watch.length}</td><td><code>${esc(state.watchReadings?.[watch.name]?.raw_hex||'Read to capture')}</code></td><td>${state.watchChanges?.[watch.name]?.changes.map(c=>'0x'+c.offset.toString(16)+': '+c.before+' → '+c.after).join(', ')||'—'}</td><td>${button('Remove','watch-remove',{id:String(i)})}</td></tr>`).join('')}</tbody></table></div><div class="actions">${button('Read watches','watch-read',{disabled:!state.runtime||!watches.length})}${button('Set comparison baseline','watch-baseline',{disabled:!state.watchReadings})}</div><p class="subtle">${state.watchBaseline?'Baseline saved for this session. Advance in Playtest, then read again.':state.runtime?'Read watches, then set a comparison baseline.':'Load this source in Playtest to observe available memory.'}</p></section>`;
}
