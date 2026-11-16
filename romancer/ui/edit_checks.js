import {button,select,read,field} from './common.js';
import {selectionKey} from './tool_inputs.js';
import {checkReport} from './build_checks.js';
export function editCheckSelection(state){
 const rows=[...(state.project?.sources||[]),...(state.project?.builds||[])],byId=new Map(rows.map(r=>[r.artifact_id,r]));
 const chain=artifact=>{const seen=new Set(),list=[];for(let n=0;artifact&&n<128;n++){if(seen.has(artifact.artifact_id))break;seen.add(artifact.artifact_id);list.push(artifact);artifact=byId.get(artifact.source_id);}return list;};
 const baseline=chain(state.artifact).find(r=>r.gameplay_traces?.source_sha256===r.sha256&&r.gameplay_traces.ids?.length);
 if(!baseline)return {baseline:null,targets:[],traces:[]};
 const targets=rows.filter(r=>r.kind==='build'&&r.artifact_id!==baseline.artifact_id&&r.system_id===baseline.system_id&&chain(r).some(a=>a.artifact_id===baseline.artifact_id));
 return {baseline,targets,traces:baseline.gameplay_traces.ids};
}
const modes=[['value','Final value'],['delta','Change during last input'],['same','Same as original']];
function expectationRows(ctx,watches,count){
 return Array.from({length:count},(_,i)=>{
  const key='expect-'+i+'-', draft=(id,fallback)=>ctx.draft(key+id,fallback);
  return '<fieldset class="expectation-fields"><legend>Gameplay check '+(i+1)+'</legend><div class="field-row">'+
   select(key+'watch','Saved RAM watch',[['','No watch selected'],...watches.map((w,j)=>[j,w.name])],draft('watch',''))+
   select(key+'mode','What to compare',modes,draft('mode','value'))+
   select(key+'endian','Byte order',[['little','Little endian'],['big','Big endian']],draft('endian','little'))+
   field(key+'original','Expected original',draft('original',''),{type:'number'})+
   field(key+'build','Expected build',draft('build',''),{type:'number'})+'</div></fieldset>';
 }).join('');
}
function readExpectations(watches,count){
 const rules=[];
 for(let i=0;i<count;i++){
  const key='expect-'+i+'-',index=read(key+'watch');
  if(index==='')continue;
  const watch=watches[Number(index)],mode=read(key+'mode'),endian=read(key+'endian');
  if(!watch)throw Error('Choose a saved RAM watch.');
  const expected=side=>{
   if(mode==='same')return null;
   const raw=read(key+side),value=Number(raw);
   if(!raw.trim()||!Number.isSafeInteger(value))throw Error('Enter a whole number for the original and build, or choose Same as original.');
   return value;
  };
  rules.push({...watch,mode,endian,original:expected('original'),build:expected('build')});
 }
 return rules;
}
function discoveryForm(ctx,baseline,result,current){
 if(!result?.replay_verified||baseline?.kind!=='source'||(!result.gameplay_verified&&!result.changed_pixels))return '';
 const layouts=baseline.descriptors||{},assets=layouts.assets,
       graphics=['bitmaps','palettes','tilemaps'].flatMap(group=>(assets?.[group]||[]).map(a=>[a.id,a.id]));
 const kinds=[...(result.gameplay_verified?[['byte','Named byte'],...(layouts.tables?[['table','Saved numeric table']]:[])]:[]),
              ...(result.changed_pixels&&graphics.length?[['graphics','Graphics resource']]:[])];
 if(!kinds.length)return '';
 ctx.use({
  'discovery-save':async()=>{
   if(!current())throw Error('The selected ROM changed.');
   const name=read('discovery-name').trim(),kind=read('discovery-kind'),raw=read('discovery-offset').trim(),offset=Number(raw);
   if(!name)throw Error('Name this discovery.');
   if(kind==='byte'&&(!raw||!Number.isSafeInteger(offset)||offset<0))throw Error('Enter the changed ROM file offset.');
   await ctx.run('discoveries.save',{project_id:ctx.state.project.project_id,artifact_id:baseline.artifact_id,
      evidence_id:result.evidence_id,name,kind,offset:kind==='byte'?offset:null,resource:kind==='graphics'?read('discovery-resource'):null},{render:false});
   if(current())ctx.notify('Discovery saved. Open the original ROM’s Overview to edit or share it.');
  },
 });
 return '<details class="config"><summary>Save a reusable discovery</summary><p>Name the changed resource on the exact original ROM. Replay evidence covers the tested route.</p><div class="field-row">'+
  field('discovery-name','Discovery name',ctx.draft('discovery-name',''))+
  select('discovery-kind','Kind',kinds,ctx.draft('discovery-kind',kinds[0][0]))+
  (result.gameplay_verified?field('discovery-offset','ROM file offset (named byte only)',ctx.draft('discovery-offset',''),{placeholder:'0x1710'}):'')+
  (graphics.length?select('discovery-resource','Graphics resource',graphics,ctx.draft('discovery-resource',graphics[0][0])):'')+
  '</div>'+button('Save discovery','discovery-save')+'</details>';
}
export function editCheckControls(ctx,{prominent=false}={}){
 const {state}=ctx;if(!state.artifact)return '';
 const scope=selectionKey(state),choice=editCheckSelection(state),current=()=>scope===selectionKey(state);
 const saved=choice.baseline?.descriptors?.watches;
 const watches=saved?.source_sha256===choice.baseline?.sha256?(saved?.watches||[]).filter(w=>[1,2,4].includes(w.length)):[];
 const watchCount=watches.length?Math.min(8,Math.max(1,Number(ctx.draft('expect-count','1'))||1)):0;
 ctx.use({'edit-check-add':()=>{if(!current())return;ctx.setDraft('expect-count',String(watchCount+1));return ctx.render();},'edit-check-run':async()=>{if(!current())throw Error('The selected ROM changed.');const target_id=read('edit-check-target'),trace_id=read('edit-check-trace');if(!choice.baseline||!choice.targets.some(r=>r.artifact_id===target_id)||!choice.traces.includes(trace_id))throw Error('Choose a descendant build and captured trace.');const expectations=readExpectations(watches,watchCount);const result=await ctx.run('checks.from_trace',{project_id:state.project.project_id,source_id:choice.baseline.artifact_id,target_id,trace_id,...(expectations.length?{expectations}:{})},{render:false});if(!current())return;state.editCheckResult=result;return ctx.render();}});
 const result=state.editCheckResult,matching=result&&choice.baseline?.sha256===result.source_sha256&&choice.targets.some(t=>t.sha256===result.target_sha256);
 const reason=!choice.baseline?'Capture a fresh cold-start trace in Playtest first.':!choice.targets.length?'Review your edit and create a separate build first.':'';
 if(prominent&&!choice.traces.length)return '';
 return '<details class="card edit-checks" '+(matching||prominent?'open':'')+'><summary>'+(prominent?'Compare a captured scene':'Test this edit')+'</summary><p>Replay the same inputs on the original and build. Review the pictures to confirm your intended change.</p>'+
 (choice.targets.length?select('edit-check-target','Edited build',choice.targets.map(r=>[r.artifact_id,r.name||r.artifact_id]),ctx.draft('edit-check-target',state.artifact.kind==='build'?state.artifact.artifact_id:choice.targets.at(-1).artifact_id)):'')+
 (choice.traces.length?select('edit-check-trace','Saved trace',choice.traces.map((id,i)=>[id,'Capture '+(i+1)+' · '+id.slice(0,8)]),ctx.draft('edit-check-trace',choice.traces.at(-1))):'')+
 '<details class="config" '+(matching||watchCount>1?'open':'')+'><summary>What should happen?</summary>'+
 (watchCount?'<p>Choose a saved watch. For Same as original, leave the expected numbers blank.</p>'+expectationRows(ctx,watches,watchCount)+
   (watchCount<8?button('Add another check','edit-check-add'):''):'<p>Save a 1-, 2- or 4-byte watch on the original in Playtest. You can still compare pictures without a watch.</p>')+'</details>'+
 button(prominent?'Test captured scene':'Test this edit','edit-check-run',{primary:true,disabled:!!reason,reason})+button('Open Playtest','navigate',{id:'playtest'})+(matching?checkReport(result)+discoveryForm(ctx,choice.baseline,result,current):'')+'</details>';
}
